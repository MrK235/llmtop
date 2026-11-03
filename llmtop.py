#!/usr/bin/env python3
"""llmtop - LLM Terminal Monitor für Ollama."""
import argparse
import os
import sys
import urllib.error

VERSION = "2.3.24"  # Single Source of Truth; History in version.md
PIXEL_ICON = ("╔══════╗", "║ >▞_  ║", "║  LLM ║", "╚══════╝")  # Terminal-Prompt und LLM als quadratisches Logo.
DEFAULT_HOST = "http://localhost:11434"


def snapshot_lines(host, use_nvidia, cpu_measure=1.0):
    """Erstellt einen einmaligen, vollstaendigen Snapshot ohne curses."""
    from llmtop_metrics import (backfill_context_limits, collector_config, context_text,
                              format_run_line, load_run_events, load_run_history,
                              model_for_run, run_metric_detail, snapshot_record,
                              source_label, token_rate, write_history)
    from llmtop_sources import (CPU_POWER_DISPLAY_SCALE_W, GPU_POWER_DISPLAY_SCALE_W,
                              bar, collect_gpus,
                              collect_ollama, cpu_count, cpu_name, cpu_percent,
                              cpu_temperature, collect_cpu_power, get_ram_pct,
                              model_lines, read_cpu_totals)
    lines = []
    st = collect_ollama(host)
    active_runs = load_run_events()
    run = active_runs[0] if active_runs else None
    runs = load_run_history(limit=10)
    backfill_context_limits(runs, st.get("models", []))
    lines.append(f"{PIXEL_ICON[0]} llmtop {VERSION}  Ollama {st['version'] if st['ok'] else 'nicht erreichbar'}  {host}")
    token, _collector_url = collector_config()
    lines.append("Collector: " + ("konfiguriert" if token else "nicht konfiguriert"))
    if st["error"]:
        lines.append(f"Fehler: {st['error']}")
    prev = read_cpu_totals()
    cpu_power = collect_cpu_power()
    import time
    time.sleep(cpu_measure)
    cpu = cpu_percent(prev, read_cpu_totals())
    cpu_power = collect_cpu_power()
    lines.append(f"CPU {bar(cpu, 20)} {cpu:.1f}%" if cpu is not None else "CPU (Messung)")
    power_watt = cpu_power.get("watt")
    power_limit = cpu_power.get("limit")
    power_source = cpu_power.get("source", "keine CPU-Powerquelle")
    if power_watt is not None and power_limit and power_limit > 0:
        power_pct = min(100.0, 100.0 * power_watt / power_limit)
        lines.append(f"Power {bar(power_pct, 20)} {power_pct:.1f}%  "
                     f"{power_watt:.1f} W / {power_limit:.1f} W ({power_source})")
    elif power_watt is not None:
        display_pct = min(100.0, 100.0 * power_watt / CPU_POWER_DISPLAY_SCALE_W)
        lines.append(f"Power {bar(display_pct, 20)} {power_watt:.1f} W  ({power_source}; keine Grenze)")
    else:
        lines.append(f"Power {bar(None, 20)} n/a  ({power_source})")
    lines.append(f"CPU {cpu_name()}  ·  Kerne {cpu_count()}")
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
        if i:
            lines.append("  ─────────────── weitere GPU ───────────────")
        util = g["util"]
        util_text = f"{util:3d}%" if util is not None else " n/a"
        lines.append(f"GPU{i} {g['name']} {bar(util, 20)} {util_text} ({g['source']})")
        if g.get("temp_c") is not None:
            lines.append(f"  Temp {g['temp_c']:.1f} °C ({g.get('temp_source') or g['source']})")
        if g["mem_total"] is not None and g["mem_used"] is not None:
            vram_pct = g["vram_pct"]
            pct_text = f"{vram_pct:.1f}%" if vram_pct is not None else "n/a"
            lines.append(f"  VRAM {bar(vram_pct, 12)} {pct_text}  {g['mem_used']:.0f} / {g['mem_total']:.0f} MiB")
        if g["power_watt"] is not None:
            limit = g.get("power_limit")
            if limit and limit > 0:
                power_pct = min(100.0, 100.0 * g["power_watt"] / limit)
                lines.append(f"  Power {bar(power_pct, 12)} {power_pct:.1f}%  {g['power_watt']:.1f} W / {limit:.0f} W")
            else:
                power_pct = min(100.0, 100.0 * g["power_watt"] / GPU_POWER_DISPLAY_SCALE_W)
                lines.append(f"  Power {bar(power_pct, 12)} {g['power_watt']:.1f} W (keine Grenze)")
    if st["ok"] and not st["error"]:
        if st["models"]:
            for m in st["models"]:
                lines.extend(model_lines(m))
        else:
            lines.append("Kein Modell geladen (/api/ps ist leer)")
    history_ok = write_history(snapshot_record(
        host, st, cpu, ram_data or (None, None, None), gpus, gerr, run, cpu_power))
    if active_runs:
        for item in active_runs:
            detail = run_metric_detail(item)
            lines.append(f"Aktueller Run {source_label(item.get('source'), item.get('provider'))}  {item.get('model', '?')}  "
                         f"{item.get('status', 'unknown')}  {detail} · "
                         f"{context_text(item, model_for_run(item, st.get('models', [])))}")
    else:
        lines.append("Aktuelle Runs: keine instrumentierten Requests")
    lines.append(f"History-Snapshots {'aktiv' if history_ok else 'nicht verfügbar'}")
    for item in runs:
        finished = __import__('llmtop_metrics')._parse_time(item.get("finished_at"))
        when = finished.strftime("%H:%M") if finished else "?"
        lines.append(format_run_line(item, f"Run-History {when}  {source_label(item.get('source'), item.get('provider'))}  "
                                     f"{item['model']}  {item['status']}  ",
                                     model_for_run(item, st.get("models", []))))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(prog="llmtop", description="LLM Terminal Monitor für Ollama")
    ap.add_argument("--version", action="version", version=f"llmtop {VERSION}")
    ap.add_argument("--host", default=os.environ.get("OLLAMA_HOST", DEFAULT_HOST))
    ap.add_argument("--interval", type=float, default=0.5, help="Refresh-Sekunden (TUI)")
    request_group = ap.add_mutually_exclusive_group()
    request_group.add_argument("--chat", metavar="JSON", help="direkter /api/chat-Request mit Run-Metriken")
    request_group.add_argument("--generate", metavar="JSON", help="direkter /api/generate-Request mit Run-Metriken")
    request_group.add_argument("--collector", action="store_true", help="lokalen Run-Metrik-Collector starten")
    request_group.add_argument("--emit", metavar="DATEI", help="Schema-2-Testevent an Collector senden ('-' für stdin)")
    request_group.add_argument("--install-open-webui-adapter", action="store_true", help="Open-WebUI-Adapter per API installieren und aktivieren")
    ap.add_argument("--collector-bind", help="Collector-Bind-Adresse (Default 127.0.0.1)")
    ap.add_argument("--collector-port", type=int, help="Collector-Port (Default 11435)")
    ap.add_argument("--once", action="store_true", help="ein Einzel-Snapshot, kein Vollbild")
    ap.add_argument("--no-nvidia", action="store_true", help="nvidia-smi nicht verwenden")
    ap.add_argument("--rapl-helper", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.rapl_helper:
        from llmtop_sources import run_rapl_helper
        return run_rapl_helper()
    from llmtop_sources import normalize_host
    host = normalize_host(args.host)
    from llmtop_metrics import (emit_run_event, ensure_open_webui_adapter,
                                ensure_pi_adapter, install_open_webui_adapter,
                                read_request_payload, run_collector, run_ollama_request)
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
        except (OSError, ValueError, urllib.error.URLError, __import__('json').JSONDecodeError) as exc:
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
    # Adapter bleiben ohne lokale Collector-Konfiguration No-ops. Der Pi-Adapter
    # wird global aktualisiert und erhält private Laufzeitdaten für neue Pi-Prozesse.
    pi_adapter_active = ensure_pi_adapter()
    from threading import Thread
    Thread(target=ensure_open_webui_adapter, name="llmtop-open-webui", daemon=True).start()
    from llmtop_tui import _run_tui
    return _run_tui(host, max(0.2, args.interval), not args.no_nvidia, VERSION,
                    PIXEL_ICON, pi_adapter_active)


if __name__ == "__main__":
    sys.exit(main())
