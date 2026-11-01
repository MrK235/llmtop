"""Run-Metriken, JSONL-Historie, Collector und Open-WebUI-Integration."""
import hmac
import json
import os
import sqlite3
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

from llmtop_sources import normalize_host

DEFAULT_COLLECTOR_URL = "http://127.0.0.1:11435"
DEFAULT_HISTORY_LIMIT = 500
DEFAULT_RUN_HISTORY_LIMIT = 100
DEFAULT_RUN_MAX_AGE = 90.0
MAX_COLLECTOR_BODY = 32 * 1024
ALLOWED_RUN_SOURCES = {"pi", "open-webui", "ollama-cli", "legacy"}
FINAL_RUN_EVENTS = {"completed", "error", "cancelled"}
RUN_FILE_LOCK = threading.RLock()
OPEN_WEBUI_FUNCTION_ID = "llmtop_run_metrics"
PI_ADAPTER_FILENAME = "llmtop_run_metrics.ts"


def history_path():
    """Liefert den konfigurierbaren JSONL-Pfad ohne Verzeichnis anzulegen."""
    return os.environ.get(
        "LLMTOP_HISTORY_FILE",
        os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
                     "llmtop", "history.jsonl"),
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
        "LLMTOP_RUN_FILE", os.path.join(os.path.dirname(history_path()), "run.jsonl")))


def run_history_path():
    return os.path.expanduser(os.environ.get(
        "LLMTOP_RUN_HISTORY_FILE", os.path.join(os.path.dirname(history_path()), "runs.jsonl")))


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
    for key in ("status_detail", "error", "context_limit_source", "provider", "provider_model"):
        value = run.get(key)
        if isinstance(value, str) and value:
            # Provider-Metadaten bleiben klein und enthalten keine Inhalte.
            out[key] = value[:120]
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
        fd, temporary = tempfile.mkstemp(prefix=".llmtop-", dir=directory, text=True)
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
            # Der letzte Abschluss bleibt als aktueller Run sichtbar, bis ein
            # neuer Run beginnt. Seine finalen Werte ersetzen Zwischenstände.
            prior = runs.get(key)
            if prior:
                merged = dict(prior)
                merged.update(normalized)
                normalized = normalize_run(merged) or normalized
            # Letzten Abschluss je Quelle behalten: Pi und Open WebUI dürfen
            # einander in der Live-Ansicht nie verdrängen.
            runs = {item_key: item for item_key, item in runs.items()
                    if item_key == key or item["status"] not in FINAL_RUN_EVENTS
                    or item["source"] != normalized["source"]}
            runs[key] = normalized
        else:
            # Ein neuer aktiver Run ergänzt den letzten Abschluss derselben
            # Quelle. So bleibt dessen Ergebnis sichtbar, während Pi oder
            # WebUI bereits den nächsten Run verarbeitet.
            runs[key] = normalized
        records = [{"timestamp": item.get("updated_at") or item.get("started_at"), "run": item}
                   for item in sorted(runs.values(), key=lambda value: _parse_time(
                       value.get("updated_at") or value.get("started_at")) or datetime.min.replace(tzinfo=timezone.utc))]
        return write_jsonl(records, target)


def load_run_events(path=None, max_age=DEFAULT_RUN_MAX_AGE, limit=None):
    """Liest aktive Runs plus den letzten Abschluss aus der Live-Datei.

    Ein Run ohne Update bleibt für lange Anfragen bis zum Sicherheits-Timeout
    sichtbar. Danach wird er nicht als aktueller Run dargestellt und aus der
    Live-Datei entfernt; er wird nicht nachträglich historisiert. Der letzte
    finale Run bleibt dagegen sichtbar, bis ein neuer Run beginnt.
    """
    target = os.path.expanduser(path or run_path())
    with RUN_FILE_LOCK:
        runs = {}
        for item in read_jsonl(target):
            candidate = item.get("run") if isinstance(item.get("run"), dict) else item
            candidate = normalize_run(candidate)
            if candidate:
                runs[(candidate["source"], candidate["run_id"])] = candidate
        now = datetime.now(timezone.utc)
        fresh = {}
        for key, run in runs.items():
            stamp = _parse_time(run.get("updated_at") or run.get("finished_at") or run.get("started_at"))
            if run["status"] not in FINAL_RUN_EVENTS and stamp:
                age = max(0.0, (now - stamp).total_seconds())
                if age > max_age:
                    continue
                run["age_seconds"] = age
            elif run["status"] not in FINAL_RUN_EVENTS:
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
        return ordered if limit is None else ordered[:max(0, int(limit))]


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


def source_label(source, provider=None):
    """Kurzlabel aus Clientquelle und optionalem Modellprovider."""
    label = {"pi": "Pi", "open-webui": "Open WebUI", "ollama-cli": "Ollama CLI",
             "legacy": "Legacy"}.get(source, source or "?")
    return f"{label}/{provider}" if provider else label


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
        return (False, source_label(run.get("source"), run.get("provider")).casefold())
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
        self.path = os.path.expanduser(path or os.environ.get("LLMTOP_OPEN_WEBUI_DB", ""))

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
        # Finale Adapter-Ereignisse duerfen nur die am Ende verfuegbaren Werte
        # enthalten. Bereits bekannte Start-/Kontextdaten bleiben erhalten.
        prior = next((item for item in load_run_events(limit=DEFAULT_RUN_HISTORY_LIMIT)
                      if item["source"] == run["source"] and item["run_id"] == run["run_id"]), None)
        if prior:
            merged = dict(prior)
            merged.update(run)
            run = normalize_run(merged) or run
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
    return (os.environ.get("LLMTOP_COLLECTOR_TOKEN", ""),
            os.environ.get("LLMTOP_COLLECTOR_URL", DEFAULT_COLLECTOR_URL))


def pi_adapter_state_path():
    """Privater Laufzeitpfad für die globale Pi-Erweiterung."""
    return os.path.join(os.path.dirname(history_path()), "pi-collector.json")


def pi_adapter_source_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "pi", PI_ADAPTER_FILENAME)


def ensure_pi_adapter():
    """Installiert den Pi-Adapter und dessen private Collector-Laufzeitdaten.

    Nur ein konfigurierter Collector aktiviert den Adapter. Fehler bleiben ein
    No-op, damit der Monitor ohne Pi-Installation unverändert startet.
    """
    token, url = collector_config()
    if not token:
        return False
    target_dir = os.path.expanduser("~/.pi/agent/extensions")
    target = os.path.join(target_dir, PI_ADAPTER_FILENAME)
    state = pi_adapter_state_path()
    try:
        with open(pi_adapter_source_path(), encoding="utf-8") as fh:
            source = fh.read()
        os.makedirs(target_dir, mode=0o700, exist_ok=True)
        os.makedirs(os.path.dirname(state), mode=0o700, exist_ok=True)
        for path, content in ((target, source),
                              (state, json.dumps({"collector_url": url,
                                                  "collector_token": token}, separators=(",", ":")))):
            directory = os.path.dirname(path)
            fd, temporary = tempfile.mkstemp(prefix=".llmtop-", dir=directory, text=True)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(content)
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


def collector_listen_address(bind=None, port=None):
    """Ermittelt die Listen-Adresse, ohne den sicheren Loopback-Default zu ändern."""
    load_dotenv()
    bind = bind or os.environ.get("LLMTOP_COLLECTOR_BIND", "127.0.0.1")
    raw_port = port if port is not None else os.environ.get("LLMTOP_COLLECTOR_PORT", "11435")
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        raise ValueError("LLMTOP_COLLECTOR_PORT muss eine Zahl sein")
    if not 1 <= port <= 65535:
        raise ValueError("Collector-Port außerhalb 1..65535")
    return bind, port


def collector_handler(token):
    class Handler(BaseHTTPRequestHandler):
        server_version = "llmtop-collector"
        sys_version = ""

        def log_message(self, _format, *_args):
            return

        def _reply(self, code):
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self):
            # Eigene Adapterwege verhindern Quellverwechslungen. Der alte
            # generische Pfad bleibt für den kompatiblen Ollama-CLI-Modus.
            expected_source = {"/v1/runs/pi": "pi",
                               "/v1/runs/open-webui": "open-webui",
                               "/v1/runs": None}.get(self.path)
            if self.path not in ("/v1/runs", "/v1/runs/pi", "/v1/runs/open-webui"):
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
            if expected_source and event.get("source") != expected_source:
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
        if not self.token and os.environ.get("LLMTOP_COLLECTOR_INSECURE") != "1":
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
            raise ValueError("LLMTOP_COLLECTOR_TOKEN fehlt (.env oder Umgebung)")
        raise OSError(service.error)
    for address in service.addresses:
        print(f"llmtop Collector lauscht auf http://{address}:{service.port}/v1/runs", flush=True)
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
        raise ValueError("LLMTOP_COLLECTOR_TOKEN fehlt (.env oder Umgebung)")
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
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "open_webui", "llmtop_run_metrics.py")


def open_webui_adapter_ready():
    """Prüft, ob der llmtop-Filter vorhanden, aktiv und global ist."""
    url, key, _collector_token = open_webui_config()
    try:
        _status, function = open_webui_api(
            url, key, "GET", f"/api/v1/functions/id/{OPEN_WEBUI_FUNCTION_ID}")
    except ValueError as exc:
        # Die geprüften Open-WebUI-Versionen antworten bei fehlender Function
        # teils mit 401 statt 404. Beide Fälle bedeuten hier: installieren.
        if "HTTP 401" in str(exc) or "HTTP 404" in str(exc):
            return False
        raise
    if not isinstance(function, dict) or not function.get("is_active") or not function.get("is_global"):
        return False
    try:
        with open(filter_source_path(), encoding="utf-8") as fh:
            return function.get("content") == fh.read()
    except OSError:
        return False


def ensure_open_webui_adapter():
    """Installiert den Filter nur bei vorhandener lokaler Konfiguration.

    Diese Funktion ist für den asynchronen TUI-Start gedacht. Fehler bleiben
    absichtlich lokal: Ein nicht erreichbares Open WebUI beeinträchtigt weder
    den Monitor noch den Collector.
    """
    try:
        if open_webui_adapter_ready():
            return "bereit"
        action, _function_id = install_open_webui_adapter()
        return action
    except (OSError, ValueError, urllib.error.URLError):
        return None


def install_open_webui_adapter():
    """Installiert Filter, Valves und Aktivierung idempotent über die Admin-API."""
    url, key, collector_token = open_webui_config()
    gateway = open_webui_gateway()
    if not gateway:
        raise ValueError("private Docker-Gateway-Adresse von open-webui nicht ermittelbar")
    with open(filter_source_path(), encoding="utf-8") as fh:
        content = fh.read()
    function_id = OPEN_WEBUI_FUNCTION_ID
    try:
        _status, function = open_webui_api(url, key, "GET", f"/api/v1/functions/id/{function_id}")
    except ValueError as exc:
        if "HTTP 401" not in str(exc) and "HTTP 404" not in str(exc):
            raise
        function = None
    if function is None:
        _status, function = open_webui_api(url, key, "POST", "/api/v1/functions/create", {
            "id": function_id, "name": "llmtop Run Metrics", "content": content,
            "meta": {"description": "Datensparsame Ollama-Runmetriken für llmtop"}})
        action = "installiert"
    else:
        _status, function = open_webui_api(url, key, "POST", f"/api/v1/functions/id/{function_id}/update", {
            "id": function_id, "name": "llmtop Run Metrics", "content": content,
            "meta": {"description": "Datensparsame Ollama-Runmetriken für llmtop"}})
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
        raise ValueError("LLMTOP_COLLECTOR_TOKEN fehlt (.env oder Umgebung)")
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
        "source": "llmtop",
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
