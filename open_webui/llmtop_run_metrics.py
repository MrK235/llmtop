"""
title: llmtop Run Metrics
author: llmtop
version: 2.2.16
required_open_webui_version: 0.12.3
description: Meldet datensparsame Provider-Runmetriken an den lokalen llmtop-Collector.
"""

import asyncio
import hashlib
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


def _context_usage(value: Any) -> Optional[float]:
    """Liest vorhandene Kontextzähler, ohne Nachrichteninhalte auszuwerten."""
    if not isinstance(value, dict):
        return None
    for key in ("context_tokens", "contextTokens", "context_token_count", "contextTokenCount"):
        tokens = number(value.get(key))
        if tokens is not None and tokens > 0:
            return tokens
    usage = value.get("usage")
    if not isinstance(usage, dict):
        usage = value
    for key in ("total_tokens", "totalTokens", "context_tokens", "contextTokens"):
        tokens = number(usage.get(key))
        if tokens is not None and tokens > 0:
            return tokens
    prompt = next((number(usage.get(key)) for key in
                   ("prompt_tokens", "promptTokens", "prompt_eval_count", "input_tokens", "inputTokens")
                   if number(usage.get(key)) is not None), None)
    output = next((number(usage.get(key)) for key in
                   ("completion_tokens", "completionTokens", "eval_count", "output_tokens", "outputTokens")
                   if number(usage.get(key)) is not None), None)
    if prompt is not None and output is not None and prompt + output > 0:
        return prompt + output
    return prompt if prompt is not None and prompt > 0 else None


def session_context_tokens(body: dict) -> Optional[float]:
    """Liefert vorhandene Session-Kontextwerte aus dem Request vor dem Stream.

    Open WebUI stellt diese Werte nicht in jedem Request bereit. Es werden
    deshalb ausschließlich explizite Usage-/Kontextfelder verwendet; aus
    Textlängen wird kein Schätzwert erzeugt.
    """
    direct = _context_usage(body)
    if direct is not None:
        return direct
    messages = body.get("messages") if isinstance(body, dict) else None
    for message in reversed(messages if isinstance(messages, list) else ()):
        value = _context_usage(message)
        if value is not None:
            return value
    return None


def has_generated_delta(value: Any) -> bool:
    """Erkennt nur inhaltliche Modell-Deltas für die TTFT-Messung."""
    if isinstance(value, dict):
        for key in ("content", "response", "text", "thinking", "reasoning", "delta"):
            item = value.get(key)
            if isinstance(item, str) and item:
                return True
        for key in ("tool_calls", "toolCalls"):
            items = value.get(key)
            if isinstance(items, list) and items:
                return True
        for key in ("choices", "message", "output", "delta"):
            if has_generated_delta(value.get(key)):
                return True
    elif isinstance(value, list):
        return any(has_generated_delta(item) for item in value)
    return False


def _compaction_marker(value: Any) -> Optional[str]:
    """Erkennt einen abgeschlossenen Open-WebUI-Compaction-Marker."""
    if not isinstance(value, dict):
        return None
    event_type = value.get("type")
    payload = value
    if event_type == "context_compaction":
        payload = value.get("data") if isinstance(value.get("data"), dict) else value
        if payload.get("done") is not True or payload.get("error"):
            return None
    elif event_type == "open_webui:context_compaction":
        if value.get("done") is False or value.get("error"):
            return None
    elif value.get("action") == "context_compaction":
        if value.get("done") is not True or value.get("error"):
            return None
    else:
        return None
    marker = (payload.get("id") or payload.get("call_id") or
              payload.get("checkpoint_message_id"))
    if isinstance(marker, str) and marker:
        return marker[:120]
    summary = payload.get("summary") or payload.get("context_summary")
    if isinstance(summary, str) and summary:
        return "summary:" + hashlib.sha256(summary.encode("utf-8")).hexdigest()
    return None


def _compaction_metrics(value: Any) -> Optional[dict]:
    """Sammelt alle abgeschlossenen Compactions aus einem WebUI-Payload."""
    markers = []

    def visit(item: Any) -> None:
        marker = _compaction_marker(item)
        if marker and marker not in markers:
            markers.append(marker)
        if isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    if not markers:
        return None
    return {"_compaction_delta": len(markers), "_compaction_markers": markers,
            "_compaction_marker": markers[0]}


def _find_metrics(value: Any) -> Optional[dict]:
    """Sucht Nutzungsfelder ohne Compaction-Marker."""
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

            def first_number(*names: str) -> Optional[float]:
                for name in names:
                    value = number(usage.get(name))
                    if value is not None:
                        return value
                return None

            # Open WebUI summiert input/output bei Tool-Loops über mehrere
            # Modellaufrufe. prompt/completion beziehungsweise die Ollama-
            # Felder beschreiben dagegen den jeweils aktuellen Aufruf und
            # müssen deshalb für den Kontext Vorrang haben.
            prompt = first_number("prompt_tokens", "prompt_eval_count", "input_tokens")
            output = first_number("completion_tokens", "eval_count", "output_tokens")
            if prompt is not None:
                result["prompt_tokens"] = prompt
            if output is not None:
                result["output_tokens"] = output
            for source, target in (("load_duration", "load_duration"),
                                   ("prompt_eval_duration", "prompt_eval_duration"),
                                   ("prompt_duration", "prompt_eval_duration"),
                                   ("total_duration", "total_duration"),
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
            result = _find_metrics(child)
            if result is not None:
                return result
    elif isinstance(value, list):
        for child in reversed(value):
            result = _find_metrics(child)
            if result is not None:
                return result
    return None


def find_metrics(value: Any) -> Optional[dict]:
    """Sucht bekannte Usage und abgeschlossene Compactions; Inhalte bleiben außen vor."""
    result = _find_metrics(value) or {}
    compactions = _compaction_metrics(value)
    if compactions:
        result.update(compactions)
    return result or None


def _consume_compaction_metrics(run: dict, metrics: dict) -> int:
    """Übernimmt Compaction-Marker genau einmal in den laufenden Run."""
    raw_markers = metrics.pop("_compaction_markers", [])
    marker = metrics.pop("_compaction_marker", None)
    markers = list(raw_markers) if isinstance(raw_markers, list) else []
    if isinstance(marker, str) and marker and marker not in markers:
        markers.append(marker)
    delta = int(metrics.pop("_compaction_delta", 0) or 0)
    if markers:
        known = run.setdefault("_compaction_markers", set())
        delta = sum(1 for item in markers if item not in known)
        known.update(markers)
    if delta:
        run["compactions"] = run.get("compactions", 0) + delta
    return delta


class Filter:
    class Valves(BaseModel):
        priority: int = 0
        collector_url: str = Field(default_factory=lambda: os.getenv("LLMTOP_COLLECTOR_URL", "http://172.18.0.1:11435"))
        collector_token: str = Field(default_factory=lambda: os.getenv("LLMTOP_COLLECTOR_TOKEN", ""))
        ollama_base_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"))
        timeout_seconds: float = 0.5
        stale_seconds: float = 900.0
        duplicate_request_seconds: float = 0.5

    def __init__(self):
        self.valves = self.Valves()
        self._runs: dict[str, deque[dict]] = defaultdict(deque)
        self._completed_runs: dict[str, tuple[dict, float]] = {}
        self._session_context: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def _provider(self, model: Optional[dict]) -> Optional[str]:
        """Liefert nur vorhandene, kurze Provider-Metadaten ohne Chatinhalte."""
        if not isinstance(model, dict):
            return None
        owned_by = str(model.get("owned_by", "")).strip()
        if owned_by:
            return owned_by[:120]
        base_url = str(model.get("base_url", "")).rstrip("/")
        if base_url == self.valves.ollama_base_url.rstrip("/"):
            return "ollama"
        return "unknown"

    @staticmethod
    def _key(model: str, metadata: Optional[dict]) -> str:
        metadata = metadata or {}
        # Tool- und Fortsetzungsrunden können neue message_id-Werte erhalten,
        # gehören innerhalb desselben Chats aber weiterhin zum selben Run.
        stable = metadata.get("chat_id") or metadata.get("session_id") or metadata.get("message_id") or "api"
        return f"{stable}:{model}"

    @staticmethod
    def _identity(metadata: Optional[dict]) -> dict[str, str]:
        metadata = metadata or {}
        return {name: value.strip()[:120] for name in ("session_id", "chat_id", "message_id")
                if isinstance(value := metadata.get(name), str) and value.strip()}

    @staticmethod
    def _context_key(metadata: Optional[dict]) -> Optional[str]:
        """Schlüssel für den letzten Kontext einer WebUI-Konversation."""
        metadata = metadata or {}
        for name in ("chat_id", "session_id"):
            value = metadata.get(name)
            if isinstance(value, str) and value.strip():
                return name + ":" + value.strip()[:120]
        return None

    @staticmethod
    def _identity_event(run: dict) -> dict[str, str]:
        return {name: run[name] for name in ("session_id", "chat_id", "message_id") if name in run}

    @staticmethod
    def _context_summary_markers(body: dict) -> set[str]:
        """Erkennt Open-WebUI-Summary-Checkpoints ohne deren Inhalt zu speichern."""
        markers = set()
        messages = body.get("messages") if isinstance(body, dict) else None
        for message in messages if isinstance(messages, list) else ():
            if not isinstance(message, dict):
                continue
            summary = message.get("contextSummary") or message.get("context_summary")
            if isinstance(summary, str) and summary:
                digest = hashlib.sha256(summary.encode("utf-8")).hexdigest()
                markers.add("summary:" + digest)
            output = message.get("output")
            if isinstance(output, list):
                for item in output:
                    marker = _compaction_marker(item)
                    if marker:
                        markers.add(marker)
        return markers

    def _cleanup(self) -> None:
        cutoff = time.monotonic() - max(30.0, self.valves.stale_seconds)
        for key in list(self._runs):
            self._runs[key] = deque(run for run in self._runs[key] if run["created"] >= cutoff)
            if not self._runs[key]:
                del self._runs[key]
        self._completed_runs = {
            key: item for key, item in self._completed_runs.items() if item[1] >= cutoff
        }

    def _send_sync(self, event: dict) -> None:
        if not self.valves.collector_token or not self.valves.collector_url:
            return
        request = urllib.request.Request(
            self.valves.collector_url.rstrip("/") + "/v1/runs/open-webui",
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
        provider = self._provider(__model__)
        if provider is None:
            return body
        model = str(body.get("model") or (__model__ or {}).get("id") or "unknown")
        now = utc_now()
        now_mono = time.monotonic()
        options = body.get("options") if isinstance(body.get("options"), dict) else {}
        num_ctx = options.get("num_ctx")
        summary_markers = self._context_summary_markers(body)
        key = self._key(model, __metadata__)
        metadata = __metadata__ or {}
        identity = self._identity(metadata)
        has_identity = bool(identity)
        context_tokens = session_context_tokens(body)
        context_key = self._context_key(metadata)
        context_changed = False
        compaction_changed = False
        async with self._lock:
            self._cleanup()
            queue = self._runs.get(key)
            duplicate = (queue and len(queue) == 1 and
                         now_mono - queue[0].get("last_request", 0.0) <=
                         max(0.05, self.valves.duplicate_request_seconds))
            if (has_identity and queue) or duplicate:
                # Identische Filter-Durchläufe treffen teils ohne Metadaten
                # ein. Nur ein direkter Doppelaufruf innerhalb eines kurzen
                # Fensters wird zusammengelegt; parallele Chats bleiben Runs.
                run = queue[0]
                run["created"] = now_mono
                run["last_request"] = now_mono
                is_new = False
            else:
                run = {
                    "run_id": str(uuid.uuid4()),
                    "model": model,
                    "started_at": now,
                    "started_mono": now_mono,
                    "created": now_mono,
                    "last_request": now_mono,
                    "last_heartbeat": now_mono,
                    "provider_started_mono": now_mono,
                    "provider_first_token_seen": False,
                    "provider": provider,
                    "compactions": len(summary_markers),
                    "_compaction_markers": set(summary_markers),
                    **identity,
                }
                self._runs[key].append(run)
                is_new = True
            if is_new or not duplicate:
                run["provider_started_mono"] = now_mono
                run["provider_first_token_seen"] = False
            if not is_new and summary_markers:
                known = run.setdefault("_compaction_markers", set())
                new_markers = summary_markers - known
                if new_markers:
                    known.update(new_markers)
                    run["compactions"] = run.get("compactions", 0) + len(new_markers)
                    compaction_changed = True
            if isinstance(num_ctx, (int, float)) and not isinstance(num_ctx, bool) and num_ctx > 0:
                run["context_limit"] = num_ctx
                run["context_limit_source"] = "request"
            previous_context = self._session_context.get(context_key) if context_key else None
            if is_new and previous_context is not None:
                run["context_tokens"] = previous_context
            if not is_new and context_tokens is not None and run.get("context_tokens") != context_tokens:
                run["context_tokens"] = context_tokens
                context_changed = True
        if not is_new:
            if compaction_changed or context_changed:
                update = {
                    "schema": 2, "event": "updated", "run_id": run["run_id"],
                    "source": "open-webui", "provider": provider, "model": run["model"],
                    "started_at": run["started_at"], "updated_at": now,
                    "compactions": run.get("compactions", 0),
                    **self._identity_event(run),
                }
                if context_changed:
                    update["context_tokens"] = run["context_tokens"]
                await self._send(update)
            await self._heartbeat(model, __metadata__)
            return body
        await self._send({
            "schema": 2,
            "event": "started",
            "run_id": run["run_id"],
            "source": "open-webui",
            "provider": provider,
            "model": model,
            "started_at": now,
            "updated_at": now,
            "total_duration_s": 0.0,
            "compactions": run.get("compactions", 0),
            **self._identity_event(run),
            **{key: run[key] for key in ("context_tokens", "context_limit", "context_limit_source") if key in run},
        })
        # Ein bekannter Kontext des vorherigen Runs steht sofort zur Verfügung.
        # Der aktuelle Request-Kontext ersetzt ihn noch vor dem Provider-Stream,
        # sofern Open WebUI ihn bereits explizit mitliefert.
        if context_tokens is not None and run.get("context_tokens") != context_tokens:
            run["context_tokens"] = context_tokens
            await self._send({
                "schema": 2, "event": "updated", "run_id": run["run_id"],
                "source": "open-webui", "provider": provider, "model": run["model"],
                "started_at": run["started_at"], "updated_at": now,
                "context_tokens": context_tokens,
                **self._identity_event(run),
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

    async def _mark_first_token(self, model: str, metadata: Optional[dict]) -> None:
        run = await self._find_run(model, metadata)
        if not run or run.get("provider_first_token_seen"):
            return
        started = run.get("provider_started_mono")
        if not isinstance(started, (int, float)):
            return
        duration = max(0.0, time.monotonic() - started)
        run["provider_first_token_seen"] = True
        run["first_token_duration_s"] = duration
        now = utc_now()
        await self._send({
            "schema": 2, "event": "updated", "run_id": run["run_id"],
            "source": "open-webui", "provider": run.get("provider", "unknown"),
            "model": run["model"], "started_at": run["started_at"], "updated_at": now,
            "first_token_duration_s": duration,
            **self._identity_event(run),
        })

    async def _update(self, model: str, metadata: Optional[dict], metrics: dict) -> None:
        run = await self._find_run(model, metadata)
        if not run:
            return
        metrics = dict(metrics)
        delta = _consume_compaction_metrics(run, metrics)
        prompt = metrics.get("prompt_tokens")
        output = metrics.get("output_tokens")
        if prompt is not None and output is not None and prompt + output > 0:
            metrics["context_tokens"] = prompt + output
        metrics.setdefault("total_duration_s", max(
            0.0, time.monotonic() - run.get("started_mono", time.monotonic())))
        changed = {key: value for key, value in metrics.items() if run.get(key) != value}
        if delta:
            changed["compactions"] = run.get("compactions", 0) + delta
        if not changed:
            return
        run.update(changed)
        if "context_tokens" in changed:
            context_key = self._context_key(run)
            if context_key:
                self._session_context[context_key] = run["context_tokens"]
        now = utc_now()
        await self._send({
            "schema": 2, "event": "updated", "run_id": run["run_id"],
            "source": "open-webui", "provider": run.get("provider", "unknown"),
            "model": run["model"], "started_at": run["started_at"], "updated_at": now,
            **self._identity_event(run), **changed,
        })

    async def _heartbeat(self, model: str, metadata: Optional[dict]) -> None:
        """Hält lange Streams ohne Provider-Usage als aktiv erkennbar."""
        run = await self._find_run(model, metadata)
        if not run:
            return
        now_mono = time.monotonic()
        if now_mono - run.get("last_heartbeat", 0.0) < 1.0:
            return
        run["last_heartbeat"] = now_mono
        now = utc_now()
        await self._send({
            "schema": 2, "event": "updated", "run_id": run["run_id"],
            "source": "open-webui", "provider": run.get("provider", "unknown"),
            "model": run["model"], "started_at": run["started_at"], "updated_at": now,
            "total_duration_s": max(0.0, now_mono - run.get("started_mono", now_mono)),
            **self._identity_event(run),
        })

    async def _complete(self, model: str, metadata: Optional[dict], metrics: Optional[dict]) -> None:
        key = self._key(model, metadata)
        context_key = self._context_key(metadata)
        metrics = dict(metrics or {})
        has_compaction = bool(metrics.get("_compaction_delta") or
                              metrics.get("_compaction_marker") or
                              metrics.get("_compaction_markers"))
        cached_completion = False
        async with self._lock:
            self._cleanup()
            queue = self._runs.get(key)
            if not queue:
                candidates = [candidate for candidate in self._runs if candidate.endswith(":" + model)]
                queue = self._runs[candidates[0]] if len(candidates) == 1 else None
            if not queue:
                cached = self._completed_runs.get(key)
                if not cached or not has_compaction:
                    return
                run = cached[0]
                cached_completion = True
            else:
                run = queue.popleft()
                if not queue:
                    for candidate_key, candidate_queue in list(self._runs.items()):
                        if candidate_queue is queue:
                            self._runs.pop(candidate_key, None)
                            break
                self._completed_runs[key] = (run, time.monotonic())
        delta = _consume_compaction_metrics(run, metrics)
        if cached_completion and not delta:
            return
        prompt = metrics.get("prompt_tokens")
        output = metrics.get("output_tokens")
        if prompt is None:
            prompt = metrics.get("prompt_eval_count")
        if output is None:
            output = metrics.get("eval_count")
        if prompt is not None and output is not None and prompt + output > 0:
            run["context_tokens"] = prompt + output
        metrics.setdefault("total_duration_s", max(
            0.0, time.monotonic() - run.get("started_mono", time.monotonic())))
        if context_key and run.get("context_tokens") is not None:
            self._session_context[context_key] = run["context_tokens"]
        now = utc_now()
        event = {
            "schema": 2,
            "event": "completed",
            "run_id": run["run_id"],
            "source": "open-webui",
            "provider": run.get("provider", "unknown"),
            "model": run["model"],
            "started_at": run["started_at"],
            "updated_at": now,
            "finished_at": now,
            "compactions": run.get("compactions", 0),
            **self._identity_event(run),
            **{key: run[key] for key in ("context_tokens", "first_token_duration_s", "context_limit", "context_limit_source") if key in run},
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
        if (not event.get("done") and not event.get("done_reason")
                and has_generated_delta(event)):
            await self._mark_first_token(model, __metadata__)
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
