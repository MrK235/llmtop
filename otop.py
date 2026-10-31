#!/usr/bin/env python3
"""otop - Ollama Terminal Monitor: geladene Modelle sowie CPU- und GPU-Auslastung.
Nur Python-Standardbibliothek. Ollama-API: /api/version und /api/ps.
"""
import argparse
import csv
import curses
import sqlite3
import glob
import hmac
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


VERSION = "1.8.4"  # Single Source of Truth; History in version.md
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_COLLECTOR_URL = "http://127.0.0.1:11435"
DEFAULT_HISTORY_LIMIT = 500
DEFAULT_RUN_HISTORY_LIMIT = 100
DEFAULT_RUN_MAX_AGE = 90.0
MAX_COLLECTOR_BODY = 32 * 1024
ALLOWED_RUN_SOURCES = {"pi", "open-webui", "ollama-cli", "legacy"}
FINAL_RUN_EVENTS = {"completed", "error", "cancelled"}
GPU_POWER_BOOST_W = 115.0
VENDOR_NAMES = {"0x10de": "NVIDIA", "0x1002": "AMD", "0x8086": "Intel"}
RUN_FILE_LOCK = threading.RLock()


def http_json(host, path, timeout=2.0):
    with urllib.request.urlopen(host.rstrip("/") + path, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} liefert kein JSON-Objekt")
    return payload


def normalize_host(value):
    """Normalisiert OLLAMA_HOST und CLI-Werte auf eine API-Basisadresse."""
    host = value.strip()
    if host.startswith(":"):
        host = "localhost" + host
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host.rstrip("/")


def collect_ollama(host):
    st = {"ok": False, "version": None, "models": [], "error": None}
    try:
        st["version"] = http_json(host, "/api/version").get("version")
        st["ok"] = True
        models = http_json(host, "/api/ps").get("models", [])
        if not isinstance(models, list):
            raise ValueError("/api/ps liefert keine Modellliste")
        st["models"] = models
    except Exception as exc:
        st["error"] = f"{type(exc).__name__}: {exc}"
    return st


def history_path():
    """Liefert den konfigurierbaren JSONL-Pfad ohne Verzeichnis anzulegen."""
    return os.environ.get(
        "OTOP_HISTORY_FILE",
        os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
                     "otop", "history.jsonl"),
    )


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return None


def run_path():
    return os.path.expanduser(os.environ.get(
        "OTOP_RUN_FILE", os.path.join(os.path.dirname(history_path()), "run.jsonl")))


def run_history_path():
    return os.path.expanduser(os.environ.get(
        "OTOP_RUN_HISTORY_FILE", os.path.join(os.path.dirname(history_path()), "runs.jsonl")))


def load_dotenv(path=".env"):
    """Liest einfache KEY=VALUE-Einträge, ohne bestehende Umgebung zu überschreiben."""
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                if value[:1] == value[-1:] and value[:1] in ("'", '"'):
                    value = value[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        pass


def normalize_run(run, final=False):
    """Validiert Schema 1/2 und normalisiert auf das persistierte Schema 2."""
    if not isinstance(run, dict) or not isinstance(run.get("run_id"), str) or not run["run_id"]:
        return None
    if not isinstance(run.get("model"), str) or not run["model"]:
        return None
    schema = run.get("schema", 1)
    if schema not in (1, 2):
        return None
    event = str(run.get("event") or run.get("status") or "unknown")
    status = {"started": "running", "updated": "running"}.get(event, event)
    source = run.get("source", "legacy" if schema == 1 else None)
    if source not in ALLOWED_RUN_SOURCES:
        return None
    out = {"schema": 2, "run_id": run["run_id"], "source": source,
           "model": run["model"], "status": status}
    if isinstance(run.get("source_run_id"), str) and run["source_run_id"]:
        out["source_run_id"] = run["source_run_id"]
    for key in ("started_at", "updated_at", "finished_at"):
        if _parse_time(run.get(key)):
            out[key] = run[key]
    for key in ("prompt_tokens", "output_tokens", "context_tokens", "context_limit",
                "load_duration_s", "prompt_eval_duration_s", "eval_duration_s",
                "total_duration_s"):
        value = run.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            out[key] = value
    for source_key, target in (("prompt_eval_count", "prompt_tokens"),
                               ("eval_count", "output_tokens")):
        value = run.get(source_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            out[target] = value
    for source_key, target in (("load_duration", "load_duration_s"),
                               ("prompt_eval_duration", "prompt_eval_duration_s"),
                               ("eval_duration", "eval_duration_s"),
                               ("total_duration", "total_duration_s")):
        value = duration_seconds(run.get(source_key))
        if value is not None:
            out[target] = value
    for key in ("status_detail", "error", "context_limit_source"):
        if isinstance(run.get(key), str):
            out[key] = run[key]
    if "context_tokens" not in out and "prompt_tokens" in out and "output_tokens" in out:
        out["context_tokens"] = out["prompt_tokens"] + out["output_tokens"]
    if final and (status not in FINAL_RUN_EVENTS or not _parse_time(out.get("finished_at"))):
        return None
    return out


def read_jsonl(path):
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    yield item
    except OSError:
        return


def write_jsonl(records, path):
    """Schreibt JSONL atomar mit privaten Dateirechten."""
    directory = os.path.dirname(path) or "."
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".otop-", dir=directory, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for item in records:
                    fh.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
    except OSError:
        return False
    return True


def write_live_run(run, path=None):
    normalized = normalize_run(run)
    if not normalized:
        return False
    if not _parse_time(normalized.get("updated_at")):
        normalized["updated_at"] = _utc_now()
    target = os.path.expanduser(path or run_path())
    # Collector-Requests laufen parallel. Lesen, Ändern und Ersetzen muss
    # deshalb eine unteilbare Operation sein, sonst können Abschlüsse verloren
    # gehen und alte Runs in run.jsonl zurückbleiben.
    with RUN_FILE_LOCK:
        runs = {}
        for item in read_jsonl(target):
            candidate = item.get("run") if isinstance(item.get("run"), dict) else item
            candidate = normalize_run(candidate)
            if candidate:
                runs[(candidate["source"], candidate["run_id"])] = candidate
        key = (normalized["source"], normalized["run_id"])
        if normalized["status"] in FINAL_RUN_EVENTS:
            runs.pop(key, None)
        else:
            runs[key] = normalized
        records = [{"timestamp": item.get("updated_at") or item.get("started_at"), "run": item}
                   for item in sorted(runs.values(), key=lambda value: _parse_time(
                       value.get("updated_at") or value.get("started_at")) or datetime.min.replace(tzinfo=timezone.utc))]
        return write_jsonl(records, target)


def load_run_events(path=None, max_age=DEFAULT_RUN_MAX_AGE, limit=3):
    """Liest aktive Runs und entfernt verwaiste Einträge aus der Live-Datei.

    Ein Run ohne Update bleibt für lange Anfragen bis zum Sicherheits-Timeout
    sichtbar. Danach wird er nicht als aktueller Run dargestellt und aus der
    Live-Datei entfernt; er wird nicht nachträglich historisiert.
    """
    target = os.path.expanduser(path or run_path())
    with RUN_FILE_LOCK:
        runs = {}
        for item in read_jsonl(target):
            candidate = item.get("run") if isinstance(item.get("run"), dict) else item
            candidate = normalize_run(candidate)
            if candidate and candidate["status"] not in FINAL_RUN_EVENTS:
                runs[(candidate["source"], candidate["run_id"])] = candidate
        now = datetime.now(timezone.utc)
        fresh = {}
        for key, run in runs.items():
            stamp = _parse_time(run.get("updated_at") or run.get("started_at"))
            if stamp:
                age = max(0.0, (now - stamp).total_seconds())
                if age > max_age:
                    continue
                run["age_seconds"] = age
            else:
                run["age_seconds"] = None
            fresh[key] = run
        if len(fresh) != len(runs):
            records = [{"timestamp": item.get("updated_at") or item.get("started_at"), "run": item}
                       for item in sorted(fresh.values(), key=lambda value: _parse_time(
                           value.get("updated_at") or value.get("started_at")) or datetime.min.replace(tzinfo=timezone.utc))]
            write_jsonl(records, target)
        ordered = sorted(fresh.values(), key=lambda item: _parse_time(
            item.get("updated_at") or item.get("started_at")) or datetime.min.replace(tzinfo=timezone.utc),
                         reverse=True)
        return ordered[:limit]


def load_run_history(path=None, limit=DEFAULT_RUN_HISTORY_LIMIT):
    """Liest finale Runs, dedupliziert per Quelle und Run-ID."""
    runs = {}
    for item in read_jsonl(os.path.expanduser(path or run_history_path())):
        run = normalize_run(item, final=True)
        if run:
            key = (run["source"], run["run_id"])
            prior = runs.get(key)
            if not prior or _parse_time(run["finished_at"]) >= _parse_time(prior["finished_at"]):
                runs[key] = run
    return sorted(runs.values(), key=lambda item: _parse_time(item["finished_at"]), reverse=True)[:limit]


def append_run_history(run, path=None, limit=DEFAULT_RUN_HISTORY_LIMIT):
    """Fügt einen finalen Run dedupliziert zur begrenzten Run-Historie hinzu."""
    normalized = normalize_run(run, final=True)
    if not normalized:
        return False
    target = os.path.expanduser(path or run_history_path())
    with RUN_FILE_LOCK:
        runs = {(item["source"], item["run_id"]): item
                for item in load_run_history(target, limit=10 ** 9)}
        runs[(normalized["source"], normalized["run_id"])] = normalized
        records = sorted(runs.values(), key=lambda item: _parse_time(item["finished_at"]))[-max(1, int(limit)):]
        return write_jsonl(records, target)


def _token_value(run, key):
    value = run.get(key)
    return value if isinstance(value, (int, float)) and value >= 0 else None


def token_rate(run):
    tokens = _token_value(run, "output_tokens")
    duration = _token_value(run, "eval_duration_s")
    if tokens is None or not duration:
        duration = _token_value(run, "eval_duration")
    return tokens / duration if tokens is not None and duration else None


def total_tokens(run):
    prompt = _token_value(run, "prompt_tokens")
    output = _token_value(run, "output_tokens")
    if prompt is None and output is None:
        return None
    return (prompt or 0) + (output or 0)


def compact_tokens(value):
    if value is None:
        return "n/a"
    if value >= 1000:
        return f"{value / 1000:.1f}k"
    return f"{value:.0f}"


def duration_seconds(value):
    return value / 1_000_000_000 if isinstance(value, (int, float)) and value >= 0 else None


def source_label(source):
    return {"pi": "Pi", "open-webui": "Open WebUI", "ollama-cli": "Ollama CLI",
            "legacy": "Legacy"}.get(source, source or "?")


def run_metric_detail(run):
    total = total_tokens(run)
    rate = token_rate(run)
    if total is None:
        return "Tokens: warten auf Provider · Tok/s: n/a"
    token_text = (f"Tokens: {compact_tokens(total)} "
                  f"(Prompt {compact_tokens(_token_value(run, 'prompt_tokens'))}, "
                  f"Ausgabe {compact_tokens(_token_value(run, 'output_tokens'))})")
    return f"{token_text} · {rate:.1f} Tok/s" if rate is not None else f"{token_text} · Tok/s: n/a"


def context_values(run, model=None):
    used = _token_value(run, "context_tokens")
    limit = _token_value(run, "context_limit")
    if limit is None and model:
        limit = model.get("context_length")
    if not isinstance(limit, (int, float)) or isinstance(limit, bool) or limit <= 0:
        limit = None
    pct = min(100.0, 100.0 * used / limit) if used is not None and limit else None
    return used, limit, pct


def context_text(run, model=None):
    used, limit, pct = context_values(run, model)
    if used is None:
        return "Kontext: warten auf Provider"
    if limit is None:
        return f"Kontext {compact_tokens(used)}/n/a"
    suffix = " · über Limit" if used > limit else f" ({pct:.0f} %)"
    return f"Kontext {compact_tokens(used)}/{compact_tokens(limit)}{suffix}"


HISTORY_COLUMNS = ("zeit", "quelle", "modell", "status", "tokens", "kontext", "rate", "dauer")
HISTORY_COLUMN_LABELS = {
    "zeit": "Zeit", "quelle": "Quelle", "modell": "Modell", "status": "Status",
    "tokens": "Tokens", "kontext": "Kontext", "rate": "Tok/s", "dauer": "Dauer",
}


def history_sort_value(run, column):
    """Liefert einen stabil vergleichbaren Sortierwert; fehlende Werte folgen zuletzt."""
    if column == "zeit":
        value = _parse_time(run.get("finished_at"))
        return (value is None, value or datetime.min.replace(tzinfo=timezone.utc))
    if column == "quelle":
        return (False, source_label(run.get("source")).casefold())
    if column == "modell":
        return (False, str(run.get("model", "")).casefold())
    if column == "status":
        return (False, str(run.get("status", "")).casefold())
    if column == "tokens":
        value = total_tokens(run)
        return (value is None, value if value is not None else 0)
    if column == "kontext":
        used, limit, _pct = context_values(run)
        value = 100.0 * used / limit if used is not None and limit else None
        return (value is None, value if value is not None else 0)
    if column == "rate":
        value = token_rate(run)
        return (value is None, value if value is not None else 0)
    if column == "dauer":
        value = _token_value(run, "total_duration_s")
        return (value is None, value if value is not None else 0)
    raise ValueError(f"unbekannte History-Spalte: {column}")


def sort_run_history(runs, column="zeit", descending=True):
    """Sortiert Runs stabil; gleiche Werte bleiben nach Zeit und ID eindeutig."""
    if column not in HISTORY_COLUMNS:
        column = "zeit"
    present = [run for run in runs if not history_sort_value(run, column)[0]]
    missing = [run for run in runs if history_sort_value(run, column)[0]]
    present.sort(key=lambda run: (history_sort_value(run, column)[1],
                                  _parse_time(run.get("finished_at")) or datetime.min.replace(tzinfo=timezone.utc),
                                  str(run.get("run_id", ""))), reverse=descending)
    missing.sort(key=lambda run: (_parse_time(run.get("finished_at")) or datetime.min.replace(tzinfo=timezone.utc),
                                  str(run.get("run_id", ""))), reverse=True)
    return present + missing


def history_header_label(column, active_column, descending):
    """Markiert die aktive Sortierspalte direkt mit einem kleinen Pfeil."""
    label = HISTORY_COLUMN_LABELS[column]
    return label + ("▾" if descending else "▴") if column == active_column else label


def history_context_cell(run, model=None):
    """Kompakte Kontextzelle mit Prozentwert vor Verbrauch und Limit."""
    used, limit, _pct = context_values(run, model)
    if used is None:
        return "n/a"
    if limit is None:
        return f"n/a {compact_tokens(used)}/n/a"
    pct = 100.0 * used / limit
    return f"{pct:.0f}% {compact_tokens(used)}/{compact_tokens(limit)}"


def model_for_run(run, models):
    """Liefert das aktuell von Ollama gemeldete Modell zum Run."""
    name = run.get("model") if isinstance(run, dict) else None
    return next((model for model in models or []
                 if isinstance(model, dict) and
                 (model.get("name") == name or model.get("model") == name)), None)


def backfill_context_limits(runs, models):
    """Übernimmt das aktuelle, explizit von /api/ps gelieferte Modelllimit."""
    for run in runs:
        if _token_value(run, "context_limit") is not None:
            continue
        model = model_for_run(run, models)
        limit = model.get("context_length") if model else None
        if isinstance(limit, (int, float)) and not isinstance(limit, bool) and limit > 0:
            run["context_limit"] = limit
            run["context_limit_source"] = "model"
            if run.get("status") in FINAL_RUN_EVENTS:
                append_run_history(run)
    return runs


def format_run_line(run, prefix="", model=None):
    """Einheitliche Darstellung für aktuelle Runs, History und --once."""
    return f"{prefix}{run_metric_detail(run)} · {context_text(run, model)}"


def _usage_metrics(value):
    if not isinstance(value, dict):
        return {}
    usage = value.get("usage") if isinstance(value.get("usage"), dict) else value
    result = {}
    aliases = (("input_tokens", "prompt_tokens"), ("prompt_tokens", "prompt_tokens"),
               ("prompt_eval_count", "prompt_tokens"), ("output_tokens", "output_tokens"),
               ("completion_tokens", "output_tokens"), ("eval_count", "output_tokens"))
    for source, target in aliases:
        item = usage.get(source)
        if isinstance(item, (int, float)) and not isinstance(item, bool) and item >= 0:
            result[target] = item
    for source, target in (("eval_duration", "eval_duration_s"),
                           ("total_duration", "total_duration_s")):
        item = duration_seconds(usage.get(source))
        if item is not None:
            result[target] = item
    return result


class OpenWebUIFinalMetricsReader:
    """Liest nur explizit konfigurierte finale Usage aus einer Open-WebUI-DB."""
    def __init__(self, path=None):
        self.path = os.path.expanduser(path or os.environ.get("OTOP_OPEN_WEBUI_DB", ""))

    def read(self, model, started_at=None, message_id=None):
        if not self.path or not os.path.isfile(self.path):
            return {}
        try:
            with sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=0.5) as db:
                if message_id:
                    rows = db.execute("SELECT usage FROM chat_message WHERE id=?", (message_id,)).fetchall()
                else:
                    start = int((_parse_time(started_at).timestamp() if _parse_time(started_at) else 0) * 1000)
                    rows = db.execute(
                        "SELECT usage FROM chat_message WHERE model_id=? AND done=1 "
                        "AND updated_at>=? ORDER BY updated_at DESC LIMIT 2", (model, start)).fetchall()
                candidates = [_usage_metrics(json.loads(row[0])) for row in rows if row[0]]
                candidates = [item for item in candidates if item]
                return candidates[0] if len(candidates) == 1 else {}
        except (OSError, sqlite3.Error, TypeError, ValueError, json.JSONDecodeError):
            return {}


def process_run_event(event):
    """Validiert ein Collector-Ereignis und aktualisiert Live- und History-Datei."""
    run = normalize_run(event)
    if not run or event.get("schema") != 2 or event.get("event") not in {
            "started", "updated", "completed", "error", "cancelled"}:
        return False
    now = _utc_now()
    if event["event"] == "started" and not _parse_time(run.get("started_at")):
        return False
    run.setdefault("updated_at", now)
    if run["status"] in FINAL_RUN_EVENTS:
        run.setdefault("finished_at", now)
        missing = {key for key in ("prompt_tokens", "output_tokens", "eval_duration_s") if key not in run}
        if missing and run.get("source") == "open-webui":
            run.update({key: value for key, value in OpenWebUIFinalMetricsReader().read(
                run.get("model"), run.get("started_at"), run.get("source_run_id")).items()
                       if key in missing})
        if not append_run_history(run):
            return False
    return write_live_run(run)


def collector_config():
    load_dotenv()
    return (os.environ.get("OTOP_COLLECTOR_TOKEN", ""),
            os.environ.get("OTOP_COLLECTOR_URL", DEFAULT_COLLECTOR_URL))


def collector_listen_address(bind=None, port=None):
    """Ermittelt die Listen-Adresse, ohne den sicheren Loopback-Default zu ändern."""
    load_dotenv()
    bind = bind or os.environ.get("OTOP_COLLECTOR_BIND", "127.0.0.1")
    raw_port = port if port is not None else os.environ.get("OTOP_COLLECTOR_PORT", "11435")
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        raise ValueError("OTOP_COLLECTOR_PORT muss eine Zahl sein")
    if not 1 <= port <= 65535:
        raise ValueError("Collector-Port außerhalb 1..65535")
    return bind, port


def collector_handler(token):
    class Handler(BaseHTTPRequestHandler):
        server_version = "otop-collector"
        sys_version = ""

        def log_message(self, _format, *_args):
            return

        def _reply(self, code):
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            if self.path != "/v1/runs":
                self._reply(400)
                return
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied, "Bearer " + token):
                self._reply(401)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._reply(400)
                return
            if length <= 0 or length > MAX_COLLECTOR_BODY:
                self._reply(413 if length > MAX_COLLECTOR_BODY else 400)
                return
            try:
                event = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._reply(400)
                return
            self._reply(202 if process_run_event(event) else 400)

    return Handler


def open_webui_gateway():
    """Liest ausschließlich die private Gateway-Adresse des Open-WebUI-Netzes."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "open-webui", "--format", "{{json .NetworkSettings.Networks}}"],
            capture_output=True, text=True, timeout=3, check=True)
        networks = json.loads(result.stdout)
        gateways = {item.get("Gateway") for item in networks.values() if item.get("Gateway")}
        return sorted(gateways)[0] if len(gateways) == 1 else None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


class CollectorService:
    """Gemeinsam genutzter Collector für Dienstmodus und TUI."""
    def __init__(self, bind=None, port=None):
        self.token, _url = collector_config()
        self.bind, self.port = collector_listen_address(bind, port)
        self.addresses = []
        self.servers = []
        self.error = None

    def start(self):
        if not self.token and os.environ.get("OTOP_COLLECTOR_INSECURE") != "1":
            self.error = "nicht konfiguriert"
            return False
        addresses = [self.bind]
        gateway = open_webui_gateway()
        if self.bind == "127.0.0.1" and gateway and gateway not in addresses:
            addresses.append(gateway)
        try:
            for address in addresses:
                self.servers.append(ThreadingHTTPServer((address, self.port), collector_handler(self.token)))
                self.addresses.append(address)
        except OSError as exc:
            self.error = "extern/Port belegt" if getattr(exc, "errno", None) == 98 else f"Fehler: {exc}"
            self.stop()
            return False
        for server in self.servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        return True

    def stop(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()
        self.servers.clear()

    def status(self):
        if self.servers:
            return "aktiv · " + ", ".join(self.addresses)
        return self.error or "nicht aktiv"


def run_collector(bind=None, port=None):
    service = CollectorService(bind, port)
    if not service.start():
        if service.error == "nicht konfiguriert":
            raise ValueError("OTOP_COLLECTOR_TOKEN fehlt (.env oder Umgebung)")
        raise OSError(service.error)
    for address in service.addresses:
        print(f"otop Collector lauscht auf http://{address}:{service.port}/v1/runs", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()


def open_webui_config():
    load_dotenv()
    url = normalize_host(os.environ.get("OPEN_WEBUI_URL", "http://127.0.0.1:3000"))
    key = os.environ.get("OPEN_WEBUI_API_KEY", "")
    token, _ = collector_config()
    if not key:
        raise ValueError("OPEN_WEBUI_API_KEY fehlt (.env oder Umgebung)")
    if not token:
        raise ValueError("OTOP_COLLECTOR_TOKEN fehlt (.env oder Umgebung)")
    return url, key, token


def open_webui_api(url, key, method, path, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url.rstrip("/") + path, data=data,
                                     headers={"Authorization": "Bearer " + key,
                                              "Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw).get("detail", "")
        except (json.JSONDecodeError, AttributeError):
            detail = ""
        raise ValueError(f"Open-WebUI-API HTTP {exc.code}{': ' + str(detail) if detail else ''}")


def filter_source_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "open_webui", "otop_run_metrics.py")


def install_open_webui_adapter():
    """Installiert Filter, Valves und Aktivierung idempotent über die Admin-API."""
    url, key, collector_token = open_webui_config()
    gateway = open_webui_gateway()
    if not gateway:
        raise ValueError("private Docker-Gateway-Adresse von open-webui nicht ermittelbar")
    with open(filter_source_path(), encoding="utf-8") as fh:
        content = fh.read()
    function_id = "otop_run_metrics"
    try:
        _status, function = open_webui_api(url, key, "GET", f"/api/v1/functions/id/{function_id}")
    except ValueError as exc:
        if "HTTP 401" not in str(exc):
            raise
        function = None
    if function is None:
        _status, function = open_webui_api(url, key, "POST", "/api/v1/functions/create", {
            "id": function_id, "name": "otop Run Metrics", "content": content,
            "meta": {"description": "Datensparsame Ollama-Runmetriken für otop"}})
        action = "installiert"
    else:
        _status, function = open_webui_api(url, key, "POST", f"/api/v1/functions/id/{function_id}/update", {
            "id": function_id, "name": "otop Run Metrics", "content": content,
            "meta": {"description": "Datensparsame Ollama-Runmetriken für otop"}})
        action = "aktualisiert"
    port = collector_listen_address()[1]
    open_webui_api(url, key, "POST", f"/api/v1/functions/id/{function_id}/valves/update", {
        "collector_url": f"http://{gateway}:{port}", "collector_token": collector_token})
    if not function.get("is_active"):
        _status, function = open_webui_api(url, key, "POST", f"/api/v1/functions/id/{function_id}/toggle")
    if not function.get("is_global"):
        _status, function = open_webui_api(url, key, "POST", f"/api/v1/functions/id/{function_id}/toggle/global")
    return action, function_id


def emit_run_event(path):
    token, url = collector_config()
    if not token:
        raise ValueError("OTOP_COLLECTOR_TOKEN fehlt (.env oder Umgebung)")
    with (sys.stdin if path == "-" else open(path, encoding="utf-8")) as fh:
        event = json.load(fh)
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/runs", data=json.dumps(event).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(request, timeout=2.0) as response:
        return response.status == 202


def final_run(run, response=None, error=None):
    """Erzeugt aus der finalen Ollama-Antwort ein persistierbares Run-Ereignis."""
    result = dict(run)
    options = run.get("options") if isinstance(run.get("options"), dict) else {}
    num_ctx = options.get("num_ctx")
    if isinstance(num_ctx, (int, float)) and not isinstance(num_ctx, bool) and num_ctx > 0:
        result["context_limit"] = num_ctx
        result["context_limit_source"] = "request"
    result["finished_at"] = _utc_now()
    result["updated_at"] = result["finished_at"]
    if error:
        result["status"] = "error"
        result["error"] = str(error)
        return result
    result["status"] = "completed"
    response = response or {}
    for source, target in (("prompt_eval_count", "prompt_tokens"),
                           ("eval_count", "output_tokens")):
        value = response.get(source)
        if isinstance(value, (int, float)) and value >= 0:
            result[target] = value
    for source, target in (("load_duration", "load_duration_s"),
                           ("prompt_eval_duration", "prompt_eval_duration_s"),
                           ("eval_duration", "eval_duration_s"),
                           ("total_duration", "total_duration_s")):
        value = duration_seconds(response.get(source))
        if value is not None:
            result[target] = value
    if "prompt_tokens" in result and "output_tokens" in result:
        result["context_tokens"] = result["prompt_tokens"] + result["output_tokens"]
    return result


def run_ollama_request(host, endpoint, payload):
    """Direkter opt-in Ollama-Client; kein Server und kein Reverse Proxy."""
    model = payload.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("--chat/--generate benötigt ein Modell im JSON-Payload")
    run = {"schema": 2, "run_id": str(uuid.uuid4()), "source": "ollama-cli",
           "status": "running", "model": model, "started_at": _utc_now(),
           "options": payload.get("options") if isinstance(payload.get("options"), dict) else {}}
    write_live_run(run)
    payload = dict(payload)
    payload["stream"] = True
    request = urllib.request.Request(
        host.rstrip("/") + endpoint, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    final = None
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            for raw in response:
                sys.stdout.buffer.write(raw)
                sys.stdout.buffer.flush()
                try:
                    item = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if item.get("done"):
                    final = item
                    break
        if final is None:
            raise ValueError("Ollama lieferte kein finales done-Objekt")
        result = final_run(run, final)
        append_run_history(result)
        write_live_run(result)
        return result
    except Exception as exc:
        result = final_run(run, error=exc)
        append_run_history(result)
        write_live_run(result)
        raise


def read_request_payload(value):
    """Liest JSON von einem Argument, einer Datei oder stdin ('-')."""
    if value == "-":
        raw = sys.stdin.read()
    elif value.startswith("@"):
        with open(value[1:], encoding="utf-8") as fh:
            raw = fh.read()
    else:
        raw = value
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Request-Payload muss ein JSON-Objekt sein")
    return payload


def snapshot_record(host, ollama, cpu, ram, gpus, gpu_error, run=None):
    """Erzeugt ein datensparsames, JSON-serialisierbares History-Ereignis."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "otop",
        "host": host,
        "ollama_version": ollama.get("version"),
        "ollama_ok": bool(ollama.get("ok")),
        "models": ollama.get("models", []),
        "cpu_percent": cpu,
        "ram": {"percent": ram[0], "total_gib": ram[1], "available_gib": ram[2]},
        "gpus": gpus,
        "errors": ([ollama["error"]] if ollama.get("error") else []) +
                  ([gpu_error] if gpu_error else []),
        "run": run,
    }


def write_history(record, path=None, limit=DEFAULT_HISTORY_LIMIT):
    """Schreibt atomar begrenzte JSONL-History; defekte Zeilen werden verworfen."""
    target = os.path.expanduser(path or history_path())
    directory = os.path.dirname(target) or "."
    records = []
    try:
        with open(target, encoding="utf-8") as fh:
            for line in fh:
                try:
                    item = json.loads(line)
                    if isinstance(item, dict):
                        records.append(item)
                except (json.JSONDecodeError, TypeError):
                    continue
    except FileNotFoundError:
        pass
    except OSError:
        return False
    records = (records + [record])[-max(1, int(limit)):]
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".history-", dir=directory, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for item in records:
                    fh.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temporary, target)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    except OSError:
        return False
    return True


def read_cpu_totals():
    with open("/proc/stat") as fh:
        parts = [int(v) for v in fh.readline().split()[1:]]
    return sum(parts), parts[3] + parts[4]


def cpu_percent(prev, cur):
    dt = cur[0] - prev[0]
    di = cur[1] - prev[1]
    if dt <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * (1.0 - di / dt)))


def loadavg():
    try:
        return open("/proc/loadavg").read().split()[:3]
    except OSError:
        return ["-", "-", "-"]


def _to_int(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def cpu_temperature():
    """Liest die CPU-Temperatur aus bekannten Linux-hwmon-Treibern."""
    for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            name = open(os.path.join(hwmon, "name")).read().strip().lower()
        except OSError:
            continue
        if name not in ("k10temp", "coretemp", "zenpower"):
            continue
        for path in sorted(glob.glob(os.path.join(hwmon, "temp*_input"))):
            try:
                value = float(open(path).read().strip()) / 1000.0
            except (OSError, ValueError):
                continue
            label_path = path.replace("_input", "_label")
            try:
                label = open(label_path).read().strip()
            except OSError:
                label = os.path.basename(path).replace("_input", "")
            return value, f"{name}/{label}"
    return None, "keine CPU-Temperaturquelle"


def get_ram_pct():
    """RAM % aus /proc/meminfo: (MemTotal - MemAvailable) / MemTotal * 100"""
    mem_total_kb = mem_available_kb = None
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    mem_total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available_kb = int(line.split()[1])
        if mem_total_kb and mem_available_kb:
            ram_pct = (mem_total_kb - mem_available_kb) / mem_total_kb * 100.0
            return ram_pct, mem_total_kb / 1024.0 / 1024.0, mem_available_kb / 1024.0 / 1024.0
    except (OSError, ValueError, IndexError):
        pass
    return None, None, None


def nvidia_gpus():
    cmd = ["nvidia-smi",
           "--query-gpu=name,utilization.gpu,memory.total,memory.used,power.draw,power.limit,enforced.power.limit,temperature.gpu",
           "--format=csv,noheader,nounits"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if res.returncode != 0:
        return []

    def number(text):
        try:
            return float(text) if text not in ("", "N/A", "[N/A]") else None
        except ValueError:
            return None

    gpus = []
    for row in csv.reader(io.StringIO(res.stdout)):
        f = [x.strip() for x in row]
        if len(f) != 8:
            continue
        mem_total, mem_used = _to_int(f[2]), _to_int(f[3])
        vram_pct = (max(0.0, min(100.0, 100.0 * mem_used / mem_total))
                    if mem_total and mem_used is not None else None)
        power_limit = number(f[5]) or number(f[6])
        util = _to_int(f[1])
        gpus.append({"name": f[0], "util": max(0, min(100, util)) if util is not None else None,
                     "mem_total": mem_total, "mem_used": mem_used,
                     "vram_pct": vram_pct, "power_watt": number(f[4]),
                     "power_limit": power_limit, "temp_c": number(f[7]),
                     "temp_source": "nvidia-smi", "source": "nvidia-smi"})
    return gpus


def sysfs_gpus():
    gpus = []
    for card in sorted(glob.glob("/sys/class/drm/card[0-9]*")):
        busy_path = os.path.join(card, "device", "gpu_busy_percent")
        if not os.path.exists(busy_path):
            continue
        try:
            busy = int(open(busy_path).read().strip())
        except (OSError, ValueError):
            continue
        vendor = "GPU"
        vfile = os.path.join(card, "device", "vendor")
        try:
            vendor = VENDOR_NAMES.get(open(vfile).read().strip().lower(), vendor)
        except OSError:
            pass
        
        # sysfs VRAM (MiB)
        mem_info_used = None
        mem_info_total = None
        mem_path = os.path.join(card, "device", "mem_info_vram_used")
        total_path = os.path.join(card, "device", "mem_info_vram_total")
        if os.path.exists(mem_path):
            try:
                mem_info_used = int(open(mem_path).read().strip())
            except (OSError, ValueError):
                pass
        if os.path.exists(total_path):
            try:
                mem_info_total = int(open(total_path).read().strip())
            except (OSError, ValueError):
                pass
        
        vram_pct = None
        if mem_info_total:
            vram_pct = (max(0.0, min(100.0, 100.0 * mem_info_used / mem_info_total))
                    if mem_info_used is not None else None)
        # sysfs liefert Bytes, die restliche Anzeige verwendet MiB.
        if mem_info_used is not None:
            mem_info_used /= 1024 * 1024
        if mem_info_total is not None:
            mem_info_total /= 1024 * 1024
        
        # hwmon Power für AMD/NVIDIA (sysfs unter card/*/device/hwmon*)
        power_watt = None
        power_limit = None
        temp_c = None
        temp_source = None
        hwmon_path = os.path.join(card, "device", "hwmon")
        if not hwmon_path or not os.path.isdir(hwmon_path):
            pass
        else:
            for hwmon_dir in sorted(glob.glob(os.path.join(hwmon_path, "hwmon*")), reverse=True):
                name_file = os.path.join(hwmon_dir, "name")
                if not os.path.exists(name_file):
                    continue
                try:
                    name = open(name_file).read().strip()
                except (OSError, ValueError):
                    pass
                if temp_c is None:
                    for temp_path in sorted(glob.glob(os.path.join(hwmon_dir, "temp*_input"))):
                        try:
                            temp_c = float(open(temp_path).read().strip()) / 1000.0
                        except (OSError, ValueError):
                            continue
                        label_path = temp_path.replace("_input", "_label")
                        try:
                            label = open(label_path).read().strip()
                        except OSError:
                            label = os.path.basename(temp_path).replace("_input", "")
                        temp_source = f"sysfs/{label}"
                        break
                # Suche Power-Input in diesem hwmon-Verzeichnis
                for num in range(1, 6):
                    inp_path = os.path.join(hwmon_dir, f"power{num}_input")
                    try:
                        content = open(inp_path).read().strip()
                        watt = float(content) / 1e6  # µW -> W
                        power_watt = watt
                        cap_path = os.path.join(hwmon_dir, f"power{num}_cap")
                        try:
                            power_limit = float(open(cap_path).read().strip()) / 1e6
                        except (OSError, ValueError):
                            pass
                        break
                    except (OSError, ValueError):
                        pass
        
        gpus.append({
            "name": f"{vendor} {os.path.basename(card)}",
            "util": max(0, min(100, busy)),
            "mem_used": mem_info_used,
            "mem_total": mem_info_total,
            "vram_pct": vram_pct,
            "power_watt": power_watt,
            "power_limit": power_limit,
            "temp_c": temp_c,
            "temp_source": temp_source,
            "source": "sysfs"
        })
    return gpus


def collect_gpus(use_nvidia):
    gpus = nvidia_gpus() if use_nvidia else []
    if not gpus:
        gpus = sysfs_gpus()
    if not gpus:
        return [], "keine GPU-Quelle gefunden"
    return gpus, None


def fmt_bytes(n):
    if n is None:
        return "-"
    step = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if step < 1024 or unit == "TiB":
            return f"{step:.1f} {unit}"
        step /= 1024.0


def model_lines(model):
    d = model.get("details") or {}
    size = max(0, model.get("size") or 0)
    vram = max(0, min(size, model.get("size_vram") or 0)) if size else 0
    offload = (100.0 * vram / size) if size else 0.0
    unload = "unload ?"
    exp = model.get("expires_at")
    if exp:
        try:
            dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            secs = int((dt - datetime.now(dt.tzinfo)).total_seconds())
            unload = f"unload in {secs // 60}:{secs % 60:02d}" if secs >= 0 else "unload jetzt"
        except ValueError:
            pass
    line1 = (f"{model.get('name', '?')}  {d.get('parameter_size', '-')} "
             f"{d.get('quantization_level', '-')}  ctx {model.get('context_length', '-')}  "
             f"{model.get('runner', '-')}  {unload}")
    line2 = (f"Speicher {fmt_bytes(vram)} VRAM / {fmt_bytes(size)} gesamt  "
             f"GPU {offload:.0f}%  CPU {100 - offload:.0f}%")
    return [line1, line2]


def bar(pct, width):
    if pct is None:
        return "[" + " " * width + "]"
    n = max(0, min(width, int(round(pct * width / 100.0))))
    return "[" + "#" * n + " " * (width - n) + "]"


def snapshot_lines(host, use_nvidia, cpu_measure=1.0):
    lines = []
    st = collect_ollama(host)
    active_runs = load_run_events()
    run = active_runs[0] if active_runs else None
    runs = load_run_history(limit=10)
    backfill_context_limits(runs, st.get("models", []))
    lines.append(f"otop {VERSION}  Ollama {st['version'] if st['ok'] else 'nicht erreichbar'}  {host}")
    token, _collector_url = collector_config()
    lines.append("Collector: " + ("konfiguriert" if token else "nicht konfiguriert"))
    if st["error"]:
        lines.append(f"Fehler: {st['error']}")
    
    prev = read_cpu_totals()
    time.sleep(cpu_measure)
    cpu = cpu_percent(prev, read_cpu_totals())
    lines.append(f"CPU {bar(cpu, 20)} {cpu:.1f}%" if cpu is not None else "CPU (Messung)")
    lines.append(f"Load {loadavg()[0]}  Kerne {os.cpu_count()}")
    cpu_temp, cpu_temp_source = cpu_temperature()
    if cpu_temp is not None:
        lines.append(f"CPU Temp {cpu_temp:.1f} °C ({cpu_temp_source})")
    ram_data = get_ram_pct()
    if ram_data and ram_data[0] is not None:
        ram_pct, ram_total_gib, ram_avail_gib = ram_data
        lines.append(f"RAM  {bar(ram_pct, 24)} {ram_pct:.1f}%  {ram_avail_gib:.1f} GiB / {ram_total_gib:.1f} GiB")

    gpus, gerr = collect_gpus(use_nvidia)
    if gerr:
        lines.append(f"GPU {gerr}")
    for i, g in enumerate(gpus):
        util = g["util"]
        util_text = f"{util:3d}%" if util is not None else " n/a"
        lines.append(f"GPU{i} {g['name']} {bar(util, 20)} {util_text} ({g['source']})")
        if g.get("temp_c") is not None:
            lines.append(f"  Temp {g['temp_c']:.1f} °C ({g.get('temp_source') or g['source']})")
        if g["mem_total"] is not None and g["mem_used"] is not None:
            vram_pct = g["vram_pct"]
            pct_text = f"{vram_pct:.1f}%" if vram_pct is not None else "n/a"
            lines.append(f"  VRAM {bar(vram_pct, 12)} {pct_text}  "
                         f"{g['mem_used']:.0f} / {g['mem_total']:.0f} MiB")
        if g["power_watt"] is not None:
            limit = max(g["power_limit"] or 0.0, GPU_POWER_BOOST_W)
            power_pct = min(100.0, 100.0 * g["power_watt"] / limit)
            lines.append(f"  Power {bar(power_pct, 12)} {power_pct:.1f}%  "
                         f"{g['power_watt']:.1f} W / {limit:.0f} W")

    if st["ok"] and not st["error"]:
        if st["models"]:
            for m in st["models"]:
                lines.extend(model_lines(m))
        else:
            lines.append("Kein Modell geladen (/api/ps ist leer)")

    history_ok = write_history(snapshot_record(
        host, st, cpu, ram_data or (None, None, None), gpus, gerr, run))
    if active_runs:
        for item in active_runs:
            rate = token_rate(item)
            detail = run_metric_detail(item)
            lines.append(f"Aktueller Run {source_label(item.get('source'))}  {item.get('model', '?')}  "
                         f"{item.get('status', 'unknown')}  {detail} · "
                         f"{context_text(item, model_for_run(item, st.get('models', [])))}")
    else:
        lines.append("Aktuelle Runs: keine instrumentierten Requests")
    lines.append(f"History-Snapshots {'aktiv' if history_ok else 'nicht verfügbar'}")
    for item in runs:
        rate = token_rate(item)
        finished = _parse_time(item.get("finished_at"))
        when = finished.strftime("%H:%M") if finished else "?"
        duration = _token_value(item, "total_duration_s")
        lines.append(format_run_line(
            item, f"Run-History {when}  {source_label(item.get('source'))}  "
                  f"{item['model']}  {item['status']}  ",
            model_for_run(item, st.get("models", []))))
    return lines


def _add(scr, y, x, text, attr=0):
    h, w = scr.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    s = text[: w - x - 1]
    if not s:
        return
    try:
        scr.addstr(y, x, s, attr)
    except curses.error:
        pass


def _temp_color(colors, temp_c):
    if temp_c is None:
        return colors["secondary"]
    if temp_c >= 85:
        return colors["error"]
    if temp_c >= 70:
        return colors["status_yellow"]
    return colors["status_green"]


def _util_color(colors, pct):
    if pct is None:
        return colors["secondary"]
    if pct >= 85:
        return colors["error"]
    if pct >= 60:
        return colors["status_yellow"]
    return colors["status_green"]


def _offload_color(colors, gpu_pct):
    """Farbe des Modell-Offloads: GPU gut, ausgeglichen neutral, CPU-Fallback."""
    if gpu_pct is None:
        return colors["secondary"]
    if gpu_pct > 55:
        return colors["offload_good"]
    if gpu_pct >= 45:
        return colors["offload_mixed"]
    return colors["offload_cpu"]


def _init_colors():
    """Zentrale Farbrollen: Struktur, Status, Offload und Sekundärtext."""
    c = {"structure": curses.A_BOLD, "secondary": curses.A_DIM,
         "status_green": curses.A_BOLD, "status_yellow": curses.A_BOLD,
         "error": curses.A_BOLD, "offload_good": curses.A_BOLD,
         "offload_mixed": curses.A_BOLD, "offload_cpu": curses.A_BOLD}
    if curses.COLORS >= 8:
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        c["status_green"] = curses.color_pair(1) | curses.A_BOLD
        c["status_yellow"] = curses.color_pair(2) | curses.A_BOLD
        c["error"] = curses.color_pair(3) | curses.A_BOLD
        c["structure"] = curses.color_pair(4) | curses.A_BOLD
        c["offload_good"] = curses.color_pair(1) | curses.A_BOLD
        c["offload_mixed"] = curses.color_pair(2) | curses.A_BOLD
        c["offload_cpu"] = curses.color_pair(3) | curses.A_BOLD
    return c


def _draw(scr, st, host, interval):
    scr.erase()
    h, w = scr.getmaxyx()
    if h < 18 or w < 40:
        _add(scr, 0, 0, "Terminal zu klein (min. 40x18)", st["colors"]["error"])
        scr.refresh()
        return
    colors = st["colors"]
    label_w = 9
    bar_w = max(8, min(24, w - 50))

    def section(row, title):
        prefix = f" {title} "
        _add(scr, row, 0, prefix + "─" * max(0, w - len(prefix) - 1), colors["structure"])
        return row + 1

    def sensor(row, label, pct, value, detail="", value_attr=None, accent="", accent_attr=None):
        x = 0
        _add(scr, row, x, label.ljust(label_w), colors["structure"])
        x += label_w
        attr = _util_color(colors, pct)
        meter = bar(pct, bar_w)
        _add(scr, row, x, meter, attr)
        x += len(meter) + 1
        _add(scr, row, x, value.rjust(7), value_attr if value_attr is not None else attr)
        x += 8
        _add(scr, row, x, detail, colors["secondary"])
        if accent:
            _add(scr, row, x + len(detail), accent, accent_attr or colors["secondary"])
        return row + 1

    def draw_header(ollama):
        conn = "verbunden" if ollama["ok"] else "OFFLINE"
        ver = ollama["version"] if ollama["ok"] else "?"
        header = f"otop {VERSION}  •  Ollama {ver}  •  {conn}"
        interval_text = f"Intervall {interval:.1f}s"
        if len(header) + len(interval_text) + 2 <= w:
            _add(scr, 0, 0, header, colors["structure"])
            _add(scr, 0, w - len(interval_text) - 1, interval_text, colors["secondary"])
        else:
            _add(scr, 0, 0, f"otop {VERSION}  •  Ollama {conn}", colors["structure"])

    def history_columns():
        if w >= 118:
            return (("zeit", 17), ("quelle", 12), ("modell", 21), ("status", 11),
                    ("tokens", 8), ("kontext", 15), ("rate", 8), ("dauer", 8))
        if w >= 88:
            return (("zeit", 14), ("modell", 19), ("status", 10), ("tokens", 8),
                    ("kontext", 15), ("rate", 8), ("dauer", 8))
        return (("zeit", 11), ("modell", 14), ("status", 10), ("kontext", 14))

    def history_cell(run, column):
        model = model_for_run(run, oll.get("models", [])) if oll else None
        if column == "zeit":
            finished = _parse_time(run.get("finished_at"))
            return finished.strftime("%d.%m %H:%M") if finished else "n/a"
        if column == "quelle":
            return source_label(run.get("source"))
        if column == "modell":
            return str(run.get("model", "?"))
        if column == "status":
            return str(run.get("status", "?"))
        if column == "tokens":
            return compact_tokens(total_tokens(run))
        if column == "kontext":
            return history_context_cell(run, model)
        if column == "rate":
            rate = token_rate(run)
            return f"{rate:.1f}" if rate is not None else "n/a"
        if column == "dauer":
            duration = _token_value(run, "total_duration_s")
            return f"{duration:.1f}s" if duration is not None else "n/a"
        return ""

    def draw_history_table(row, max_rows):
        columns = history_columns()
        sorted_runs = sort_run_history(st.get("run_history", []), st["history_sort"],
                                       st["history_desc"])
        total = len(sorted_runs)
        data_rows = max(1, max_rows - 2)
        show_position = total > data_rows and data_rows >= 2
        visible = data_rows - 1 if show_position else data_rows
        max_offset = max(0, total - visible)
        st["history_offset"] = min(max(0, st["history_offset"]), max_offset)
        row = section(row, f"History ({total}/{DEFAULT_RUN_HISTORY_LIMIT})")
        x = 0
        for name, width in columns:
            label = history_header_label(name, st["history_sort"], st["history_desc"])
            attr = colors["structure"] | curses.A_UNDERLINE if name == st["history_sort"] else colors["structure"]
            _add(scr, row, x, label[:width], attr)
            x += width + 1
        row += 1
        for item in sorted_runs[st["history_offset"]:st["history_offset"] + visible]:
            cells = []
            for name, width in columns:
                text = history_cell(item, name)
                cells.append(text[:width].ljust(width))
            _add(scr, row, 0, " ".join(cells), colors["secondary"])
            row += 1
        if not sorted_runs:
            _add(scr, row, 0, "Keine abgeschlossenen instrumentierten Runs", colors["secondary"])
            row += 1
        elif show_position:
            _add(scr, row, 0, f"Zeilen {st['history_offset'] + 1}-{min(total, st['history_offset'] + visible)} von {total}",
                 colors["secondary"])
            row += 1
        return row

    if h < 26:
        oll = st["ollama"]
        draw_header(oll)
        row = 1
        row = section(row, "System")
        cpu = st["cpu"]
        cpu_value = f"{cpu:.1f} %" if cpu is not None else "n/a"
        row = sensor(row, "CPU", cpu, cpu_value)
        ram_pct, ram_total, ram_avail = st["ram"]
        ram_value = f"{ram_pct:.1f} %" if ram_pct is not None else "n/a"
        row = sensor(row, "RAM", ram_pct, ram_value)
        row += 1
        row = section(row, "GPU")
        if st["gpus"]:
            g = st["gpus"][0]
            util = g["util"]
            row = sensor(row, "GPU0", util, f"{util:d} %" if util is not None else "n/a")
            if g["mem_total"] is not None and g["mem_used"] is not None:
                vram_pct = g["vram_pct"]
                row = sensor(row, "VRAM", vram_pct,
                             f"{vram_pct:.1f} %" if vram_pct is not None else "n/a")
            if g["power_watt"] is not None:
                limit = max(g["power_limit"] or 0.0, GPU_POWER_BOOST_W)
                power_pct = min(100.0, 100.0 * g["power_watt"] / limit)
                row = sensor(row, "Power", power_pct, f"{power_pct:.1f} %")
        else:
            _add(scr, row, 0, st["gpu_err"] or "Keine GPU-Daten", colors["secondary"])
            row += 1
        row += 1
        row = section(row, "Ollama")
        _add(scr, row, 0, "Collector: " + st.get("collector_status", "nicht konfiguriert"),
             colors["secondary"])
        row += 1
        model_count = len(oll.get("models", []))
        active_runs = st.get("runs", [])
        _add(scr, row, 0, f"Geladene Modelle: {model_count}  ·  Aktuelle Runs: {len(active_runs)}",
             colors["secondary"])
        row += 1
        draw_history_table(row, h - row - 2)
        _add(scr, h - 1, 0, "q quit  Tab/s sortieren  ↑↓ scrollen  h Hilfe", colors["structure"])
        scr.refresh()
        return

    def model_card(row, model):
        details = model.get("details") or {}
        size = max(0, model.get("size") or 0)
        vram = max(0, min(size, model.get("size_vram") or 0)) if size else 0
        cpu_mem = max(0, size - vram)
        gpu_pct = 100.0 * vram / size if size else None
        name = model.get("name", "?")
        meta = (f"{details.get('parameter_size', '-')} {details.get('quantization_level', '-')}  "
                f"ctx {model.get('context_length', '-')}  {model.get('runner', '-')}")
        _add(scr, row, 0, name, colors["structure"])
        _add(scr, row, len(name) + 2, meta, colors["secondary"])
        exp = model.get("expires_at")
        if exp:
            try:
                dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                secs = int((dt - datetime.now(dt.tzinfo)).total_seconds())
                unload = "unload jetzt" if secs < 0 else f"unload in {secs // 60}:{secs % 60:02d}"
                attr = colors["error"] if secs < 0 else colors["status_yellow"] if secs < 300 else colors["secondary"]
                _add(scr, row, max(2, w - len(unload) - 1), unload, attr)
            except (AttributeError, TypeError, ValueError):
                pass
        row += 1
        x = 0
        _add(scr, row, x, "Speicher ".ljust(label_w), colors["structure"])
        x += label_w
        if gpu_pct is None:
            _add(scr, row, x, "[", colors["structure"])
            _add(scr, row, x + 1, " " * bar_w, colors["secondary"])
            _add(scr, row, x + bar_w + 1, "]", colors["structure"])
        else:
            gpu_width = max(0, min(bar_w, int(round(gpu_pct * bar_w / 100.0))))
            cpu_width = bar_w - gpu_width
            gpu_attr = _offload_color(colors, gpu_pct)
            _add(scr, row, x, "[", colors["structure"])
            _add(scr, row, x + 1, "#" * gpu_width, gpu_attr)
            _add(scr, row, x + 1 + gpu_width, "#" * cpu_width, colors["secondary"])
            _add(scr, row, x + bar_w + 1, "]", colors["structure"])
        x += bar_w + 3
        if gpu_pct is None:
            _add(scr, row, x, "GPU/CPU n/a", colors["secondary"])
        else:
            gpu_text = f"GPU {gpu_pct:.0f} % {fmt_bytes(vram)}"
            _add(scr, row, x, gpu_text, gpu_attr)
            _add(scr, row, x + len(gpu_text) + 3,
                 f"CPU {100 - gpu_pct:.0f} % {fmt_bytes(cpu_mem)}", colors["secondary"])
        return row + 1

    oll = st["ollama"]
    active_runs = st.get("runs", [])
    runs = st.get("run_history", [])
    draw_header(oll)

    row = 1
    row = section(row, "System")
    cpu = st["cpu"]
    cpu_value = f"{cpu:.1f} %" if cpu is not None else "n/a"
    cpu_temp = st["cpu_temp"]
    cpu_source = st["cpu_temp_source"] or "keine Quelle"
    cpu_detail = f"Load {loadavg()[0]}  •  {os.cpu_count()} Kerne  ·  Temp "
    cpu_accent = f"{cpu_temp:.1f} °C" if cpu_temp is not None else "n/a"
    row = sensor(row, "CPU", cpu, cpu_value, cpu_detail, accent=cpu_accent,
                 accent_attr=_temp_color(colors, cpu_temp))
    ram_pct, ram_total, ram_avail = st["ram"]
    ram_value = f"{ram_pct:.1f} %" if ram_pct is not None else "n/a"
    ram_detail = (f"{ram_avail:.1f} / {ram_total:.1f} GiB frei"
                  if ram_total is not None and ram_avail is not None else "")
    row = sensor(row, "RAM", ram_pct, ram_value, ram_detail)

    row += 1
    row = section(row, "GPU")
    if st["gpu_err"]:
        _add(scr, row, 0, st["gpu_err"], colors["status_yellow"])
        row += 1
    for i, g in enumerate(st["gpus"]):
        util = g["util"]
        util_value = f"{util:d} %" if util is not None else "n/a"
        temp_c = g.get("temp_c")
        gpu_name = g["name"].replace("NVIDIA GeForce ", "NVIDIA ").replace(" Laptop GPU", "")
        gpu_detail = f"{gpu_name}  ·  Temp "
        gpu_accent = f"{temp_c:.1f} °C" if temp_c is not None else "n/a"
        row = sensor(row, f"GPU{i}", util, util_value, gpu_detail, accent=gpu_accent,
                     accent_attr=_temp_color(colors, temp_c))
        if g["mem_total"] is not None and g["mem_used"] is not None:
            vram_pct = g["vram_pct"]
            vram_value = f"{vram_pct:.1f} %" if vram_pct is not None else "n/a"
            row = sensor(row, "VRAM", vram_pct, vram_value,
                         f"{g['mem_used']:.0f} / {g['mem_total']:.0f} MiB")
        if g["power_watt"] is not None:
            limit = max(g["power_limit"] or 0.0, GPU_POWER_BOOST_W)
            power_pct = min(100.0, 100.0 * g["power_watt"] / limit)
            power_value = f"{power_pct:.1f} %"
            power_detail = f"{g['power_watt']:.1f} W / {limit:.0f} W"
            row = sensor(row, "Power", power_pct, power_value, power_detail)

    row += 1
    row = section(row, "Ollama")
    _add(scr, row, 0, "Collector: " + st.get("collector_status", "nicht konfiguriert"),
         colors["secondary"])
    row += 2
    row = section(row, f"Aktuelle Runs ({len(active_runs)})")
    if active_runs:
        for run in active_runs[:3]:
            source = source_label(run.get("source")).ljust(11)
            age = (f"vor {run['age_seconds']:.1f}s" if run.get("age_seconds") is not None else "")
            details = run_metric_detail(run)
            _add(scr, row, 0, f"{source} {run.get('model', '?')}  {run.get('status', 'unknown')}  "
                 f"{details} · {age}", colors["secondary"])
            row += 1
            used, limit, pct = context_values(run, model_for_run(run, oll["models"]))
            value = (f"{compact_tokens(used)} / {compact_tokens(limit)}"
                     if used is not None else "warten auf Provider")
            pct_text = f"{pct:.1f} %" if pct is not None else "n/a"
            _add(scr, row, 0, f"{'Kontext'.ljust(9)}{bar(pct, bar_w)} {value}  {pct_text}",
                 _util_color(colors, pct))
            row += 1
    else:
        _add(scr, row, 0, "Keine instrumentierten Requests", colors["secondary"])
        row += 1
    row += 1
    row = section(row, "Geladene Modelle")
    # Die History ist scrollbar; der Modellbereich erhält den verbleibenden
    # Platz oberhalb einer kompakten Tabellenansicht.
    history_rows = 5
    model_end = h - 1 - history_rows - 2
    if not oll["ok"] or oll["error"]:
        _add(scr, row, 0, oll["error"] or "Ollama nicht erreichbar", colors["error"])
        row += 1
    elif not oll["models"]:
        _add(scr, row, 0, "Kein Modell geladen (/api/ps ist leer)", colors["secondary"])
        row += 1
    else:
        shown_models = 0
        while shown_models < len(oll["models"]) and row + 2 <= model_end:
            row = model_card(row, oll["models"][shown_models])
            shown_models += 1
        remaining_models = len(oll["models"]) - shown_models
        if remaining_models and row < model_end:
            _add(scr, row, 0, f"… {remaining_models} weitere Modelle ausgeblendet", colors["secondary"])
            row += 1

    row += 1
    draw_history_table(row, h - row - 2)

    _add(scr, h - 1, 0, "q quit  r neu laden  Tab/Shift-Tab Spalte  s Richtung  ↑↓ scrollen", colors["structure"])
    if st["help"]:
        sources = ", ".join(sorted(set(g.get("source", "?") for g in st["gpus"]))) or "keine"
        box = ["Hilfe", "", "q  Q  beenden", "r  Programm neu laden",
               "h  Hilfe ein/aus", "-  Intervall halbieren (min 0.5s)",
               "+  Intervall verdoppeln (max 60s)",
               "Tab / Shift-Tab  History-Spalte wechseln", "s  History-Sortierrichtung",
               "↑/↓ Bild↑/Bild↓ Pos1/Ende  History scrollen", "",
               "System / GPU / Ollama / History", "GPU-Quelle: " + sources]
        bh = len(box) + 2
        bw = max(len(b) for b in box) + 4
        y0 = max(1, (h - bh) // 2)
        x0 = max(0, (w - bw) // 2)
        if bw <= w and y0 + bh <= h - 1:
            for j in range(bh):
                if j == 0 or j == bh - 1:
                    _add(scr, y0 + j, x0, "+" + "-" * (bw - 2) + "+", colors["structure"])
                else:
                    text = box[j - 1]
                    _add(scr, y0 + j, x0, "| " + text.ljust(bw - 4) + " |", colors["structure"])
    scr.refresh()


def _run_tui(host, interval, use_nvidia):
    collector = CollectorService()
    collector.start()
    state = {"colors": None, "help": False, "prev_cpu": read_cpu_totals(),
             "ollama": None, "cpu": None, "cpu_temp": None,
             "cpu_temp_source": None, "gpus": [], "gpu_err": None,
             "ram": None, "gpu_mode_vram": False, "gpu_mode_power": False,
             "history_ok": None, "runs": [], "run_history": [], "collector_status": "nicht konfiguriert",
             "history_sort": "zeit", "history_desc": True, "history_offset": 0}

    def session(scr):
        nonlocal interval
        curses.curs_set(0)
        scr.keypad(True)
        state["colors"] = _init_colors()
        next_refresh = 0.0
        while True:
            if time.time() >= next_refresh:
                state["ollama"] = collect_ollama(host)
                state["runs"] = load_run_events()
                state["run_history"] = load_run_history()
                backfill_context_limits(state["run_history"], state["ollama"].get("models", []))
                state["gpus"], state["gpu_err"] = collect_gpus(use_nvidia)
                cur = read_cpu_totals()
                state["cpu"] = cpu_percent(state["prev_cpu"], cur)
                state["prev_cpu"] = cur
                ram_pct, ram_total, ram_avail = get_ram_pct()
                state["ram"] = (ram_pct, ram_total, ram_avail)
                state["cpu_temp"], state["cpu_temp_source"] = cpu_temperature()
                state["history_ok"] = write_history(snapshot_record(
                    host, state["ollama"], state["cpu"], state["ram"],
                    state["gpus"], state["gpu_err"], state["runs"][0] if state["runs"] else None))
                next_refresh = time.time() + interval
            _draw(scr, state, host, interval)
            delay = int(max(0.0, next_refresh - time.time()) * 1000)
            scr.timeout(delay)
            key = scr.getch()
            if key in (ord("q"), ord("Q")):
                return 0
            if key in (ord("r"), ord("R")):
                return "reload"
            elif key in (ord("h"), ord("H")):
                state["help"] = not state["help"]
            elif key in (ord("+"), ord("=")):
                interval = min(60.0, interval * 2)
            elif key == ord("-"):
                interval = max(0.5, interval / 2)
            elif key == 9:
                index = HISTORY_COLUMNS.index(state["history_sort"])
                state["history_sort"] = HISTORY_COLUMNS[(index + 1) % len(HISTORY_COLUMNS)]
                state["history_offset"] = 0
            elif key == curses.KEY_BTAB:
                index = HISTORY_COLUMNS.index(state["history_sort"])
                state["history_sort"] = HISTORY_COLUMNS[(index - 1) % len(HISTORY_COLUMNS)]
                state["history_offset"] = 0
            elif key in (ord("s"), ord("S")):
                state["history_desc"] = not state["history_desc"]
                state["history_offset"] = 0
            elif key == curses.KEY_UP:
                state["history_offset"] = max(0, state["history_offset"] - 1)
            elif key == curses.KEY_DOWN:
                state["history_offset"] += 1
            elif key == curses.KEY_PPAGE:
                state["history_offset"] = max(0, state["history_offset"] - 5)
            elif key == curses.KEY_NPAGE:
                state["history_offset"] += 5
            elif key == curses.KEY_HOME:
                state["history_offset"] = 0
            elif key == curses.KEY_END:
                state["history_offset"] = max(0, len(state["run_history"]) - 1)
            elif key == curses.KEY_RESIZE:
                pass
        return 0

    try:
        state["collector_status"] = collector.status()
        result = curses.wrapper(session)
    finally:
        collector.stop()
    if result == "reload":
        os.execv(sys.executable, [sys.executable, *sys.argv])
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(prog="otop", description="Ollama Terminal Monitor")
    ap.add_argument("--version", action="version", version=f"otop {VERSION}")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", DEFAULT_HOST))
    ap.add_argument("--interval", type=float, default=2.0, help="Refresh-Sekunden (TUI)")
    request_group = ap.add_mutually_exclusive_group()
    request_group.add_argument("--chat", metavar="JSON", help="direkter /api/chat-Request mit Run-Metriken")
    request_group.add_argument("--generate", metavar="JSON", help="direkter /api/generate-Request mit Run-Metriken")
    request_group.add_argument("--collector", action="store_true", help="lokalen Run-Metrik-Collector starten")
    request_group.add_argument("--emit", metavar="DATEI", help="Schema-2-Testevent an Collector senden ('-' für stdin)")
    request_group.add_argument("--install-open-webui-adapter", action="store_true",
                               help="Open-WebUI-Adapter per API installieren und aktivieren")
    ap.add_argument("--collector-bind", help="Collector-Bind-Adresse (Default 127.0.0.1)")
    ap.add_argument("--collector-port", type=int, help="Collector-Port (Default 11435)")
    ap.add_argument("--once", action="store_true", help="ein Einzel-Snapshot, kein Vollbild")
    ap.add_argument("--no-nvidia", action="store_true", help="nvidia-smi nicht verwenden")
    args = ap.parse_args(argv)
    host = normalize_host(args.host)

    if args.install_open_webui_adapter:
        try:
            action, function_id = install_open_webui_adapter()
            print(f"Open-WebUI-Adapter {function_id} {action} und global aktiviert")
            return 0
        except (OSError, ValueError, urllib.error.URLError) as exc:
            sys.stderr.write(f"Open-WebUI-Adapter fehlgeschlagen: {type(exc).__name__}: {exc}\n")
            return 2

    if args.collector:
        try:
            run_collector(args.collector_bind, args.collector_port)
            return 0
        except (OSError, ValueError) as exc:
            sys.stderr.write(f"Collector fehlgeschlagen: {type(exc).__name__}: {exc}\n")
            return 2

    if args.emit:
        try:
            return 0 if emit_run_event(args.emit) else 2
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"Event konnte nicht gesendet werden: {type(exc).__name__}: {exc}\n")
            return 2

    if args.chat or args.generate:
        try:
            payload = read_request_payload(args.chat or args.generate)
            run_ollama_request(host, "/api/chat" if args.chat else "/api/generate", payload)
            return 0
        except (OSError, ValueError, urllib.error.URLError) as exc:
            sys.stderr.write(f"Ollama-Run fehlgeschlagen: {type(exc).__name__}: {exc}\n")
            return 2

    if args.once:
        print("\n".join(snapshot_lines(host, not args.no_nvidia)))
        return 0
    
    if not sys.stdout.isatty():
        sys.stderr.write("kein Terminal gefunden; bitte --once verwenden\n")
        return 1
    
    return _run_tui(host, max(0.5, args.interval), not args.no_nvidia)


if __name__ == "__main__":
    sys.exit(main())
