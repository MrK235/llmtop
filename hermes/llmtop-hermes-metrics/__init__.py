"""Native Hermes observer plugin for llmtop.

The plugin deliberately sends only bounded, normalized metadata. It never reads Hermes
sessions, credentials, prompts, responses, tool names, URLs or provider error text.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

log = logging.getLogger(__name__)

_QUEUE_LIMIT = 256
_MAX_TEXT = 120
_FINAL = {"completed", "error", "cancelled"}
_PLATFORMS = {"cli", "tui", "gateway", "telegram", "cron", "acp", "webhook"}

_lock = threading.RLock()
_runs = {}
_finished = set()
_closed_keys = set()
_lineages = {}
_queue = queue.Queue(maxsize=_QUEUE_LIMIT)
_pending_finals = {}
_worker = None


def _text(value, default=""):
    if not isinstance(value, str):
        return default
    return value.strip()[:_MAX_TEXT]


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def _int(value):
    value = _number(value)
    return int(value) if value is not None and float(value).is_integer() else None


def _now():
    return time.time()


def _iso(timestamp=None):
    value = timestamp if isinstance(timestamp, (int, float)) else _now()
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))


def _state_path():
    root = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(root, "llmtop", "hermes-collector.json")


def _state():
    try:
        with open(_state_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return None
        token = data.get("collector_token")
        url = data.get("collector_url")
        if not isinstance(token, str) or not token or not isinstance(url, str) or not url:
            return None
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        return url.rstrip("/"), token
    except (OSError, ValueError, TypeError):
        return None


def _scope(base_url):
    if not isinstance(base_url, str) or not base_url:
        return "unknown"
    try:
        host = (urllib.parse.urlparse(base_url).hostname or "").casefold()
    except ValueError:
        return "unknown"
    if host in {"localhost", "127.0.0.1", "::1"} or host.startswith("127."):
        return "local"
    return "remote" if host else "unknown"


def _platform(value):
    value = _text(value, "other").casefold()
    return value if value in _PLATFORMS else "other"


def _usage(payload):
    usage = payload.get("usage") if isinstance(payload, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    result = {}
    for names, target in ((("input_tokens", "prompt_tokens"), "prompt_tokens"),
                          (("prompt_tokens", "prompt_tokens"), "prompt_tokens"),
                          (("output_tokens", "output_tokens"), "output_tokens"),
                          (("completion_tokens", "output_tokens"), "output_tokens")):
        for name in names:
            value = _number(usage.get(name))
            if value is not None:
                result[target] = value
                break
    return result


def _identity(kwargs):
    session = _text(kwargs.get("session_id"))
    task = _text(kwargs.get("task_id"))
    turn = _text(kwargs.get("turn_id"))
    return session, task, turn


def _key(session, task="", turn=""):
    return (session or "session", turn or task or "turn")


def _find(session="", task="", turn="", request_id="", kinds=None):
    with _lock:
        for key, run in list(_runs.items()):
            if kinds and run.get("run_kind") not in kinds:
                continue
            if request_id and run.get("_request_id") == request_id:
                return key, run
            if session and run.get("session_id") != session:
                continue
            if turn and run.get("source_run_id") == turn:
                return key, run
            if task and run.get("_task_id") == task:
                return key, run
            if session and not task and not turn:
                return key, run
    return None, None


def _safe_event(run, event):
    result = {key: value for key, value in run.items() if not key.startswith("_")}
    result["schema"] = 2
    result["source"] = "hermes"
    result["event"] = event
    result["updated_at"] = _iso()
    return result


def _enqueue(event, final=False):
    # The queue is intentionally best effort. On saturation, discard an older live
    # update. Final events are retained in a small keyed side buffer instead.
    try:
        _queue.put_nowait((event, final))
        _ensure_worker()
    except queue.Full:
        if final:
            with _lock:
                _pending_finals[event.get("run_id", str(uuid.uuid4()))] = event
            _ensure_worker()
            return
        try:
            removed = _queue.get_nowait()
            if removed[1]:
                with _lock:
                    _pending_finals[removed[0].get("run_id", str(uuid.uuid4()))] = removed[0]
            _queue.put_nowait((event, False))
            _ensure_worker()
        except queue.Full:
            log.debug("llmtop Hermes queue full; live update dropped")
        except queue.Empty:
            pass
    except Exception:
        log.debug("llmtop Hermes enqueue failed", exc_info=True)


def _ensure_worker():
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_worker_loop, name="llmtop-hermes", daemon=True)
            _worker.start()


def _worker_loop():
    while True:
        from_queue = False
        try:
            with _lock:
                event = next(iter(_pending_finals.values()), None)
                if event is not None:
                    _pending_finals.pop(event.get("run_id"), None)
            if event is None:
                event, _final = _queue.get()
                from_queue = True
            config = _state()
            if config:
                base, token = config
                request = urllib.request.Request(
                    base + "/v1/runs/hermes",
                    data=json.dumps(event, separators=(",", ":")).encode("utf-8"),
                    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                    method="POST")
                try:
                    with urllib.request.urlopen(request, timeout=0.5):
                        pass
                except (OSError, urllib.error.URLError, ValueError):
                    pass
        except Exception:
            log.debug("llmtop Hermes worker failed", exc_info=True)
        finally:
            if from_queue:
                try:
                    _queue.task_done()
                except ValueError:
                    pass


def _new_run(kind, kwargs, *, parent_session_id="", activity=""):
    session, task, turn = _identity(kwargs)
    session = session or _text(kwargs.get("child_session_id")) or "unknown"
    lineage = _text(kwargs.get("lineage_id")) or _lineages.get(session) or session
    _lineages[session] = lineage
    run = {
        "run_id": str(uuid.uuid4()),
        "session_id": session,
        "lineage_id": lineage,
        "source_run_id": turn or task or str(uuid.uuid4()),
        "run_kind": kind,
        "platform": _platform(kwargs.get("platform")),
        "model": _text(kwargs.get("model"), "unknown") or "unknown",
        "provider": _text(kwargs.get("provider")),
        "execution_scope": _scope(kwargs.get("base_url")),
        "status": "running",
        "started_at": _iso(kwargs.get("started_at")),
        "api_attempts": 0,
        "api_errors": 0,
        "tool_calls": 0,
        "tool_errors": 0,
        "compactions": 0,
        "_task_id": task,
        "_turn_id": turn,
    }
    if parent_session_id:
        run["parent_session_id"] = _text(parent_session_id)
    if activity:
        run["activity"] = _text(activity, "other") or "other"
    return run


def _start_main(**kwargs):
    session, task, turn = _identity(kwargs)
    key = _key(session, task, turn)
    with _lock:
        existing = _runs.get(key)
        if existing and existing.get("status") not in _FINAL:
            return
        if key in _closed_keys:
            return
        run = _new_run("main", kwargs)
        _runs[key] = run
    _enqueue(_safe_event(run, "started"))


def _update(run, **values):
    for key, value in values.items():
        if value is not None:
            run[key] = value


def _api_target(kwargs):
    session, task, turn = _identity(kwargs)
    return _find(session, task, turn, kinds={"main", "subagent"})


def _pre_api(**kwargs):
    key, run = _api_target(kwargs)
    if run is None:
        return
    with _lock:
        run["api_attempts"] = int(run.get("api_attempts", 0)) + 1
        _update(run, provider=_text(kwargs.get("provider")),
                provider_model=_text(kwargs.get("model")),
                model=_text(kwargs.get("model"), run.get("model", "unknown")),
                context_limit=_number(kwargs.get("context_length") or kwargs.get("context_limit")),
                execution_scope=_scope(kwargs.get("base_url")))
        event = _safe_event(run, "updated")
    _enqueue(event)


def _post_api(**kwargs):
    key, run = _api_target(kwargs)
    if run is None:
        return
    usage = _usage(kwargs)
    duration = _number(kwargs.get("api_duration"))
    first = None
    started = kwargs.get("started_at")
    first_at = kwargs.get("first_chunk_at")
    if isinstance(started, (int, float)) and isinstance(first_at, (int, float)):
        first = max(0.0, first_at - started)
    with _lock:
        for name in ("prompt_tokens", "output_tokens"):
            value = _number(usage.get(name))
            if value is not None:
                run[name] = run.get(name, 0) + value
        # Provider input usage is the last confirmed context, not an aggregate.
        if _number(usage.get("prompt_tokens")) is not None:
            run["context_tokens"] = usage["prompt_tokens"]
        if duration is not None:
            run["eval_duration_s"] = run.get("eval_duration_s", 0.0) + duration
        _update(run, context_limit=_number(kwargs.get("context_length") or kwargs.get("context_limit")),
                provider=_text(kwargs.get("provider")),
                provider_model=_text(kwargs.get("response_model") or kwargs.get("model")),
                model=_text(kwargs.get("response_model") or kwargs.get("model"), run.get("model", "unknown")),
                execution_scope=_scope(kwargs.get("base_url")),
                first_token_duration_s=first)
        event = _safe_event(run, "updated")
    _enqueue(event)


def _api_error(**kwargs):
    key, run = _api_target(kwargs)
    if run is None:
        return
    with _lock:
        run["api_errors"] = int(run.get("api_errors", 0)) + 1
        _enqueue(_safe_event(run, "updated"))


def _tool_pre(**kwargs):
    key, run = _find(*_identity(kwargs), kinds={"main", "subagent"})
    if run is None:
        return
    with _lock:
        run["tool_calls"] = int(run.get("tool_calls", 0)) + 1
        _enqueue(_safe_event(run, "updated"))


def _tool_post(**kwargs):
    key, run = _find(*_identity(kwargs), kinds={"main", "subagent"})
    if run is None:
        return
    duration = _number(kwargs.get("duration_ms"))
    failed = kwargs.get("error") is not None or kwargs.get("status") in {"error", "failed"}
    with _lock:
        if failed:
            run["tool_errors"] = int(run.get("tool_errors", 0)) + 1
        if duration is not None:
            run["tool_duration_s"] = run.get("tool_duration_s", 0.0) + duration / 1000.0
        _enqueue(_safe_event(run, "updated"))


def _finish(key, run, status="completed"):
    with _lock:
        if not run or run.get("run_id") in _finished:
            return
        status = status if status in _FINAL else "error"
        run["status"] = status
        run["finished_at"] = _iso()
        _finished.add(run.get("run_id"))
        _closed_keys.add(key)
        if len(_closed_keys) > 2048:
            _closed_keys.pop()
        _runs.pop(key, None)
        event = _safe_event(run, status)
    _enqueue(event, final=True)


def _post_main(**kwargs):
    session, task, turn = _identity(kwargs)
    key, run = _find(session, task, turn)
    if run is not None:
        _finish(key, run, "completed")


def _session_end(**kwargs):
    session, task, turn = _identity(kwargs)
    key, run = _find(session, task, turn, kinds={"main", "subagent"})
    if run is None:
        return
    if kwargs.get("interrupted") or kwargs.get("failed"):
        _finish(key, run, "cancelled" if kwargs.get("interrupted") else "error")
    elif kwargs.get("completed"):
        _finish(key, run, "completed")
    else:
        _finish(key, run, "cancelled")


def _loop_stopped(**kwargs):
    session = _text(kwargs.get("session_key") or kwargs.get("session_id"))
    key, run = _find(session, kinds={"main", "subagent"})
    if run is not None:
        _finish(key, run, "cancelled")


def _subagent_start(**kwargs):
    child = _text(kwargs.get("child_session_id")) or _text(kwargs.get("child_subagent_id"))
    if not child:
        return
    run = _new_run("subagent", kwargs, parent_session_id=_text(kwargs.get("parent_session_id")))
    run["session_id"] = child
    run["lineage_id"] = _text(kwargs.get("parent_session_id")) or child
    run["source_run_id"] = child
    key = ("subagent", child)
    with _lock:
        if key in _closed_keys:
            return
        _runs[key] = run
    _enqueue(_safe_event(run, "started"))


def _subagent_stop(**kwargs):
    child = _text(kwargs.get("child_session_id"))
    key, run = _find(child, kinds={"subagent"})
    if run is None:
        return
    status = _text(kwargs.get("child_status"), "completed").casefold()
    _finish(key, run, "completed" if status == "completed" else "cancelled" if status == "interrupted" else "error")


def _aux_start(**kwargs):
    request = _text(kwargs.get("api_request_id")) or str(uuid.uuid4())
    run = _new_run("auxiliary", kwargs, activity=_text(kwargs.get("aux_task"), "other"))
    run["api_attempts"] = 1
    run["_request_id"] = request
    run["source_run_id"] = request
    key = ("auxiliary", request)
    with _lock:
        if key in _closed_keys:
            return
        _runs[key] = run
    _enqueue(_safe_event(run, "started"))


def _aux_stop(**kwargs):
    request = _text(kwargs.get("api_request_id"))
    key, run = _find(request_id=request)
    if run is None:
        return
    usage = _usage(kwargs)
    duration = _number(kwargs.get("api_duration"))
    with _lock:
        run.update(usage)
        if duration is not None:
            run["eval_duration_s"] = duration
        _update(run, provider=_text(kwargs.get("provider")),
                provider_model=_text(kwargs.get("response_model") or kwargs.get("model")),
                model=_text(kwargs.get("response_model") or kwargs.get("model"), run.get("model", "unknown")),
                execution_scope=_scope(kwargs.get("base_url")))
    _finish(key, run, "error" if kwargs.get("error") else "completed")


def _compaction(**kwargs):
    session = _text(kwargs.get("session_id"))
    key, run = _find(session, kinds={"main", "subagent"})
    if run is not None:
        with _lock:
            run["compactions"] = int(run.get("compactions", 0)) + 1
            _enqueue(_safe_event(run, "updated"))
        return
    run = _new_run("maintenance", kwargs, activity="context_compaction")
    prior_session = _text(kwargs.get("previous_session_id") or kwargs.get("old_session_id"))
    lineage = (_lineages.get(prior_session) if prior_session else None) or _lineages.get(session) or session
    if session:
        _lineages[session] = lineage
    run["session_id"] = session or run["session_id"]
    run["lineage_id"] = lineage or run["lineage_id"]
    key = ("maintenance", run["run_id"])
    with _lock:
        _runs[key] = run
        run["compactions"] = 1
    _enqueue(_safe_event(run, "started"))
    _finish(key, run, "completed")


def register(ctx) -> None:
    """Register observer-only callbacks; all failures are intentionally fail-open."""
    hooks = {
        "pre_llm_call": _start_main,
        "post_llm_call": _post_main,
        "pre_api_request": _pre_api,
        "post_api_request": _post_api,
        "api_request_error": _api_error,
        "pre_auxiliary_call": _aux_start,
        "post_auxiliary_call": _aux_stop,
        "pre_tool_call": _tool_pre,
        "post_tool_call": _tool_post,
        "post_compaction": _compaction,
        "subagent_start": _subagent_start,
        "subagent_stop": _subagent_stop,
        "on_session_end": _session_end,
        "agent_loop_stopped": _loop_stopped,
    }
    for name, callback in hooks.items():
        try:
            ctx.register_hook(name, callback)
        except Exception:
            log.debug("llmtop Hermes hook registration failed: %s", name, exc_info=True)
