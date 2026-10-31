"""
title: otop Run Metrics
author: otop
version: 1.3.2
required_open_webui_version: 0.12.3
description: Meldet datensparsame Ollama-Runmetriken an den lokalen otop-Collector.
"""

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


FINAL_FIELDS = {
    "prompt_eval_count",
    "eval_count",
    "load_duration",
    "prompt_eval_duration",
    "eval_duration",
    "total_duration",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def number(value: Any) -> Optional[float]:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def find_metrics(value: Any) -> Optional[dict]:
    """Sucht nur bekannte Nutzungsfelder; Textinhalte werden nie übernommen."""
    if isinstance(value, dict):
        if value.get("done") is True or FINAL_FIELDS.intersection(value):
            result = {key: value[key] for key in FINAL_FIELDS if number(value.get(key)) is not None}
            if isinstance(value.get("done_reason"), str):
                result["status_detail"] = value["done_reason"]
            if result or value.get("done") is True:
                return result
        usage = value.get("usage")
        if isinstance(usage, dict):
            result = {}
            prompt = number(usage.get("input_tokens") or usage.get("prompt_tokens") or usage.get("prompt_eval_count"))
            output = number(usage.get("output_tokens") or usage.get("completion_tokens") or usage.get("eval_count"))
            if prompt is not None:
                result["prompt_tokens"] = prompt
            if output is not None:
                result["output_tokens"] = output
            for source, target in (("total_duration", "total_duration"),
                                   ("total_time", "total_duration"),
                                   ("duration", "total_duration"),
                                   ("eval_duration", "eval_duration"),
                                   ("completion_duration", "eval_duration"),
                                   ("response_token/s", "output_rate"),
                                   ("response_tokens_per_second", "output_rate")):
                duration = number(usage.get(source))
                if duration is not None:
                    result[target] = duration
            if result:
                return result
        for child in value.values():
            result = find_metrics(child)
            if result is not None:
                return result
    elif isinstance(value, list):
        for child in reversed(value):
            result = find_metrics(child)
            if result is not None:
                return result
    return None


class Filter:
    class Valves(BaseModel):
        priority: int = 0
        collector_url: str = Field(default_factory=lambda: os.getenv("OTOP_COLLECTOR_URL", "http://172.18.0.1:11435"))
        collector_token: str = Field(default_factory=lambda: os.getenv("OTOP_COLLECTOR_TOKEN", ""))
        ollama_base_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"))
        timeout_seconds: float = 0.5
        stale_seconds: float = 900.0

    def __init__(self):
        self.valves = self.Valves()
        self._runs: dict[str, deque[dict]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    def _is_ollama(self, _body: dict, model: Optional[dict]) -> bool:
        """Ohne verifizierten Provider nie instrumentieren."""
        if not isinstance(model, dict):
            return False
        owned_by = str(model.get("owned_by", "")).lower()
        base_url = str(model.get("base_url", ""))
        return (owned_by == "ollama" or
                base_url.rstrip("/") == self.valves.ollama_base_url.rstrip("/"))

    @staticmethod
    def _key(model: str, metadata: Optional[dict]) -> str:
        metadata = metadata or {}
        stable = metadata.get("message_id") or metadata.get("chat_id") or metadata.get("session_id") or "api"
        return f"{stable}:{model}"

    def _cleanup(self) -> None:
        cutoff = time.monotonic() - max(30.0, self.valves.stale_seconds)
        for key in list(self._runs):
            self._runs[key] = deque(run for run in self._runs[key] if run["created"] >= cutoff)
            if not self._runs[key]:
                del self._runs[key]

    def _send_sync(self, event: dict) -> None:
        if not self.valves.collector_token or not self.valves.collector_url:
            return
        request = urllib.request.Request(
            self.valves.collector_url.rstrip("/") + "/v1/runs",
            data=json.dumps(event, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.valves.collector_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(0.05, self.valves.timeout_seconds)) as response:
                response.read(1)
        except (OSError, urllib.error.URLError, ValueError):
            pass

    async def _send(self, event: dict) -> None:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._send_sync, event),
                timeout=max(0.1, self.valves.timeout_seconds + 0.2),
            )
        except (asyncio.TimeoutError, OSError):
            pass

    async def request(
        self,
        body: dict,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __request__: Any = None,
    ) -> dict:
        if not self._is_ollama(body, __model__):
            return body
        model = str(body.get("model") or (__model__ or {}).get("id") or "unknown")
        now = utc_now()
        now_mono = time.monotonic()
        options = body.get("options") if isinstance(body.get("options"), dict) else {}
        num_ctx = options.get("num_ctx")
        key = self._key(model, __metadata__)
        metadata = __metadata__ or {}
        has_identity = any(metadata.get(name) for name in ("message_id", "chat_id", "session_id"))
        async with self._lock:
            self._cleanup()
            queue = self._runs.get(key)
            if has_identity and queue:
                # Open WebUI ruft den Request-Filter bei Tool- und anderen
                # Fortsetzungsrunden erneut auf. Diese Aufrufe gehören zum
                # selben sichtbaren Chat-Request und dürfen keinen zweiten
                # Live-Run erzeugen.
                run = queue[0]
                run["created"] = now_mono
                is_new = False
            else:
                run = {
                    "run_id": str(uuid.uuid4()),
                    "model": model,
                    "started_at": now,
                    "created": now_mono,
                    "last_heartbeat": now_mono,
                }
                self._runs[key].append(run)
                is_new = True
            if isinstance(num_ctx, (int, float)) and not isinstance(num_ctx, bool) and num_ctx > 0:
                run["context_limit"] = num_ctx
                run["context_limit_source"] = "request"
        if not is_new:
            await self._heartbeat(model, __metadata__)
            return body
        await self._send({
            "schema": 2,
            "event": "started",
            "run_id": run["run_id"],
            "source": "open-webui",
            "model": model,
            "started_at": now,
            "updated_at": now,
            **{key: run[key] for key in ("context_limit", "context_limit_source") if key in run},
        })
        return body

    async def _find_run(self, model: str, metadata: Optional[dict]) -> Optional[dict]:
        metadata = metadata or {}
        key = self._key(model, metadata)
        has_identity = any(metadata.get(name) for name in ("message_id", "chat_id", "session_id"))
        async with self._lock:
            self._cleanup()
            queue = self._runs.get(key)
            if not queue and not has_identity:
                # Nur ohne widersprüchliche Identität darf ein einzelner
                # Modell-Run ersatzweise zugeordnet werden. Bei mehreren
                # parallelen Tool-Use-Runs wird nichts geraten.
                candidates = [candidate for candidate in self._runs if candidate.endswith(":" + model)]
                queue = self._runs[candidates[0]] if len(candidates) == 1 else None
            return queue[0] if queue else None

    async def _update(self, model: str, metadata: Optional[dict], metrics: dict) -> None:
        run = await self._find_run(model, metadata)
        if not run:
            return
        changed = {key: value for key, value in metrics.items() if run.get(key) != value}
        if not changed:
            return
        run.update(changed)
        now = utc_now()
        await self._send({
            "schema": 2, "event": "updated", "run_id": run["run_id"],
            "source": "open-webui", "model": run["model"],
            "started_at": run["started_at"], "updated_at": now, **changed,
        })

    async def _heartbeat(self, model: str, metadata: Optional[dict]) -> None:
        """Hält lange Streams ohne Provider-Usage als aktiv erkennbar."""
        run = await self._find_run(model, metadata)
        if not run:
            return
        now_mono = time.monotonic()
        if now_mono - run.get("last_heartbeat", 0.0) < 10.0:
            return
        run["last_heartbeat"] = now_mono
        now = utc_now()
        await self._send({
            "schema": 2, "event": "updated", "run_id": run["run_id"],
            "source": "open-webui", "model": run["model"],
            "started_at": run["started_at"], "updated_at": now,
        })

    async def _complete(self, model: str, metadata: Optional[dict], metrics: Optional[dict]) -> None:
        key = self._key(model, metadata)
        async with self._lock:
            self._cleanup()
            queue = self._runs.get(key)
            if not queue:
                candidates = [candidate for candidate in self._runs if candidate.endswith(":" + model)]
                queue = self._runs[candidates[0]] if len(candidates) == 1 else None
            if not queue:
                return
            run = queue.popleft()
            if not queue:
                for candidate_key, candidate_queue in list(self._runs.items()):
                    if candidate_queue is queue:
                        self._runs.pop(candidate_key, None)
                        break
        now = utc_now()
        event = {
            "schema": 2,
            "event": "completed",
            "run_id": run["run_id"],
            "source": "open-webui",
            "model": run["model"],
            "started_at": run["started_at"],
            "updated_at": now,
            "finished_at": now,
            **{key: run[key] for key in ("context_limit", "context_limit_source") if key in run},
        }
        if metrics:
            event.update(metrics)
            detail = metrics.get("status_detail")
            if detail in ("cancelled", "canceled"):
                event["event"] = "cancelled"
            elif detail == "error":
                event["event"] = "error"
        await self._send(event)

    async def stream(
        self,
        event: dict,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __request__: Any = None,
    ) -> dict:
        model = str(event.get("model") or (__model__ or {}).get("id") or "unknown")
        metrics = find_metrics(event)
        if event.get("error") or event.get("cancelled"):
            await self._complete(model, __metadata__, {
                "status_detail": "error" if event.get("error") else "cancelled"})
            return event
        if metrics is None:
            await self._heartbeat(model, __metadata__)
        if metrics is not None:
            if event.get("done") is True or event.get("done_reason"):
                await self._complete(model, __metadata__, metrics)
            else:
                await self._update(model, __metadata__, metrics)
        return event

    async def outlet(
        self,
        body: dict,
        __metadata__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __request__: Any = None,
    ) -> dict:
        model = str(body.get("model") or (__model__ or {}).get("id") or "unknown")
        metrics = find_metrics(body)
        run = await self._find_run(model, __metadata__)
        if run and not metrics:
            metrics = {key: run[key] for key in (
                "prompt_tokens", "output_tokens", "total_duration", "eval_duration",
                "prompt_eval_duration", "load_duration") if key in run}
        await self._complete(model, __metadata__, metrics)
        return body
