"""curses-Oberflaeche fuer llmtop."""
import curses
import os
import sys
import threading
import time
from datetime import datetime

VERSION = "?"
PIXEL_ICON = ("╔══════╗", "║ >▞_  ║", "║  LLM ║", "╚══════╝")

from llmtop_metrics import (
    DEFAULT_RUN_HISTORY_LIMIT, HISTORY_COLUMNS, CollectorService, _parse_time, _token_value,
    backfill_context_limits, compact_tokens, context_values,
    history_header_label, load_run_events, load_run_history, model_for_run,
    run_metric_detail, snapshot_record, sort_run_history, source_label, token_rate, total_tokens,
    write_history,
)
from llmtop_sources import (
    GPU_POWER_BOOST_W, bar, collect_gpus, collect_ollama, cpu_percent,
    cpu_temperature, get_ram_pct, loadavg, read_cpu_totals,
)
def _add(scr, y, x, text, attr=0, indent=True):
    """Zeichnet normalen Inhalt mit einem linken Leerzeichen-Rand."""
    h, w = scr.getmaxyx()
    if indent:
        x += 1
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


def _rate_color(colors, rate):
    """Hebt langsame und sehr schnelle Ausgaberaten eindeutig hervor."""
    if rate is None or rate <= 0:
        return colors["secondary"]
    if rate < 10:
        return colors["rate_error"]
    if rate < 50:
        return colors["rate_yellow"]
    return colors["rate_green"]


def _init_colors():
    """Zentrale Farbrollen: Struktur, Status, Offload und Sekundärtext."""
    c = {"structure": curses.A_BOLD, "secondary": curses.A_DIM,
         "model_name": curses.A_DIM | curses.A_UNDERLINE, "context_label": curses.A_BOLD,
         "status_green": curses.A_BOLD, "status_yellow": curses.A_BOLD,
         "rate_green": 0, "rate_yellow": 0, "rate_error": 0,
         "error": curses.A_BOLD, "offload_good": curses.A_BOLD,
         "offload_mixed": curses.A_BOLD, "offload_cpu": curses.A_BOLD}
    if curses.COLORS >= 8:
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        c["status_green"] = curses.color_pair(1) | curses.A_BOLD
        c["context_label"] = curses.color_pair(4) | curses.A_BOLD
        c["status_yellow"] = curses.color_pair(2) | curses.A_BOLD
        c["rate_green"] = curses.color_pair(1)
        c["rate_yellow"] = curses.color_pair(2)
        c["rate_error"] = curses.color_pair(3)
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
        x = 0
        prefix = f"── {title} "
        _add(scr, row, x, prefix + "─" * max(0, w - len(prefix) - 1),
             colors["structure"], indent=False)
        return row + 1

    def run_status(run):
        return {"running": "aktiv", "completed": "erledigt",
                "cancelled": "abgebrochen", "error": "Fehler"}.get(
                    str(run.get("status", "unknown")), str(run.get("status", "unknown")))

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
        """Zeichnet die vierzeilige llmtop-Identität und Verbindungsstati."""
        ollama_state = "verbunden" if ollama["ok"] else "OFFLINE"
        ollama_short = "OK" if ollama["ok"] else "OFF"
        ollama_attr = colors["status_green"] if ollama["ok"] else colors["error"]
        version = ollama["version"] if ollama["ok"] else "?"
        collector_status = st.get("collector_status", "nicht aktiv")
        collector_active = collector_status.startswith("aktiv")
        collector_state = "aktiv" if collector_active else "nicht aktiv"
        collector_short = "OK" if collector_active else "OFF"
        collector_attr = colors["status_green"] if collector_active else colors["error"]
        icon = tuple(PIXEL_ICON) if isinstance(PIXEL_ICON, (tuple, list)) else (PIXEL_ICON,) * 4
        icon = (icon + (icon[-1],) * 4)[:4]
        for row, pixel in enumerate(icon):
            _add(scr, row, 1, pixel, colors["structure"], indent=False)

        # Acht Zeichen Breite gleichen bei Terminal-Zeichen annähernd vier Zeilen Höhe aus.
        # Das Logo kombiniert einen Terminal-Prompt mit einer LLM-Kennung.
        # Zwei freie Spalten trennen das Logo vom Textblock.
        x = 11
        title = "LLM Terminal Monitor"
        _add(scr, 0, max(0, (w - len(title)) // 2), title, colors["secondary"], indent=False)
        if w >= 72:
            label_width = 22
            _add(scr, 0, x, f"llmtop {VERSION}", colors["structure"], indent=False)
            ollama_label = f"Ollama v{version}"
            _add(scr, 1, x, ollama_label.ljust(label_width), colors["secondary"], indent=False)
            _add(scr, 1, x + label_width, ollama_state, ollama_attr, indent=False)
            _add(scr, 2, x, "Open-WebUI Collector".ljust(label_width), colors["secondary"], indent=False)
            _add(scr, 2, x + label_width, collector_state, collector_attr, indent=False)
            _add(scr, 3, x, "Autor: llmtop  ·  Python-Standardbibliothek",
                 colors["secondary"], indent=False)
        else:
            ollama_label = f"Ollama v{version} "
            _add(scr, 1, x, ollama_label, colors["secondary"], indent=False)
            _add(scr, 1, x + len(ollama_label), ollama_short, ollama_attr, indent=False)
            _add(scr, 2, x, "OW Collector ", colors["secondary"], indent=False)
            _add(scr, 2, x + 13, collector_short, collector_attr, indent=False)
            _add(scr, 3, x, f"llmtop {VERSION}", colors["secondary"], indent=False)

    def draw_footer(text):
        """Zeichnet Navigation links und Intervall-Steuerung rechtsbündig."""
        interval_text = f"-/+ Intervall {interval:.1f}s"
        interval_x = max(0, w - len(interval_text) - 1)
        _add(scr, h - 1, 0, text[:max(0, interval_x - 1)], colors["structure"], indent=False)
        _add(scr, h - 1, interval_x, interval_text, colors["structure"], indent=False)

    def history_columns():
        # Quelle/Provider bleibt in jeder Breite sichtbar; Detailspalten sind
        # nachrangig, weil nur so Pi- und WebUI-Runs unterscheidbar sind.
        if w >= 118:
            return (("zeit", 12), ("quelle", 12), ("modell", 16), ("status", 10),
                    ("tokens", 8), ("kontext", 30), ("rate", 8), ("dauer", 8))
        if w >= 80:
            return (("zeit", 8), ("quelle", 10), ("modell", 12), ("status", 8),
                    ("tokens", 7), ("kontext", 30))
        if w >= 60:
            return (("zeit", 11), ("quelle", 14), ("modell", 16), ("status", 10))
        return (("zeit", 8), ("quelle", 9), ("modell", 11), ("status", 8))

    def context_table_cell(run, model=None):
        used, limit, pct = context_values(run, model)
        if used is None:
            return "n/a"
        pct_text = f"{pct:.0f}%" if pct is not None else "n/a"
        meter = bar(pct, 12)
        limit_text = compact_tokens(limit) if limit is not None else "n/a"
        return f"{pct_text} {meter} {compact_tokens(used)}/{limit_text}"

    def history_cell(run, column):
        model = model_for_run(run, oll.get("models", [])) if oll else None
        if column == "zeit":
            finished = _parse_time(run.get("finished_at"))
            if not finished:
                return "n/a"
            return finished.strftime("%d.%m %H:%M") if w >= 118 else finished.strftime("%H:%M")
        if column == "quelle":
            return source_label(run.get("source"), run.get("provider"))
        if column == "modell":
            return str(run.get("model", "?"))
        if column == "status":
            return run_status(run)
        if column == "tokens":
            return compact_tokens(total_tokens(run))
        if column == "kontext":
            return context_table_cell(run, model)
        if column == "rate":
            rate = token_rate(run)
            return f"{rate:.1f}" if rate is not None else "n/a"
        if column == "dauer":
            duration = _token_value(run, "total_duration_s")
            return f"{duration:.1f}s" if duration is not None else "n/a"
        return ""

    def current_run_cell(run, column):
        if column == "zeit":
            stamp = _parse_time(run.get("finished_at") or run.get("started_at"))
            return stamp.strftime("%d.%m %H:%M") if stamp else "n/a"
        return history_cell(run, column)

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
        row = 5
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
            # In der kompakten Ansicht bleibt nach dem vierzeiligen Kopf nur
            # die GPU-Auslastung sichtbar; VRAM und Leistung folgen im großen Layout.
        else:
            _add(scr, row, 0, st["gpu_err"] or "Keine GPU-Daten", colors["secondary"])
            row += 1
        row += 1
        model_count = len(oll.get("models", []))
        _add(scr, row, 0, f"Geladene Modelle: {model_count}", colors["secondary"])
        row += 1
        active_runs = st.get("runs", [])
        source_order = ("pi", "open-webui")
        compact_groups = [(source, [item for item in active_runs if item.get("source") == source])
                          for source in source_order]
        compact_groups = [(source, items) for source, items in compact_groups if items]
        if not compact_groups:
            _add(scr, row, 0, f"Modelle {model_count}  ·  Keine Pi-/WebUI-Runs", colors["secondary"])
            row += 1
        else:
            # In der Kompaktansicht erhält jede vorhandene Quelle exakt eine
            # Kurzzeile; keine Quelle kann die andere aus dieser Ansicht drängen.
            for source, items in compact_groups[:max(1, h - row - 2)]:
                active = [item for item in items if item.get("status") not in ("completed", "error", "cancelled")]
                finished = len(items) - len(active)
                text = f"{source_label(source)}  aktiv {len(active)} · Ergebnis {finished}"
                if len(items) == 1:
                    item = items[0]
                    text += f"  {item.get('model', '?')} · {run_status(item)}"
                _add(scr, row, 0, text, colors["secondary"])
                row += 1
        if row < h - 2:
            draw_history_table(row, h - row - 2)
        draw_footer("q quit  Tab/s sortieren  ↑↓ scrollen  h Hilfe")
        scr.refresh()
        return

    def model_card(row, model):
        details = model.get("details") or {}
        size = max(0, model.get("size") or 0)
        vram = max(0, min(size, model.get("size_vram") or 0)) if size else 0
        cpu_mem = max(0, size - vram)
        gpu_pct = 100.0 * vram / size if size else None
        name = model.get("name", "?")
        meta = "\t".join((str(details.get("parameter_size", "-")),
                          str(details.get("quantization_level", "-")),
                          f"ctx {model.get('context_length', '-')}",
                          str(model.get("runner", "-"))))
        meta_x = max(16, ((len(name) + 9) // 8) * 8)
        _add(scr, row, 0, name, colors["model_name"])
        _add(scr, row, meta_x, meta, colors["secondary"])
        exp = model.get("expires_at")
        if exp:
            try:
                dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                secs = int((dt - datetime.now(dt.tzinfo)).total_seconds())
                unload = "unload jetzt" if secs < 0 else f"unload in {secs // 60}:{secs % 60:02d}"
                attr = colors["error"] if secs < 0 else colors["status_yellow"] if secs < 300 else colors["secondary"]
                _add(scr, row, max(2, w - len(unload) - 2), unload, attr)
            except (AttributeError, TypeError, ValueError):
                pass
        row += 1
        x = 0
        _add(scr, row, x, "VRAM/RAM ".ljust(label_w), colors["structure"])
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
        x += len(bar(None, bar_w)) + 1
        if gpu_pct is None:
            _add(scr, row, x, "n/a".rjust(7), colors["secondary"])
            _add(scr, row, x + 8, "VRAM/RAM n/a", colors["secondary"])
        else:
            # Prozentwert exakt auf der Sensor-Flucht; der CPU/RAM-Anteil
            # bleibt ausschließlich als grauer Balkenanteil und Größenangabe.
            _add(scr, row, x, f"{gpu_pct:.0f} %".rjust(7), gpu_attr)
            sizes = (f"{vram / (1024 ** 2):.0f} / "
                     f"{cpu_mem / (1024 ** 2):.0f} MiB")
            _add(scr, row, x + 8, sizes, colors["secondary"])
        return row + 1

    oll = st["ollama"]
    active_runs = st.get("runs", [])
    runs = st.get("run_history", [])
    draw_header(oll)

    row = 5
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
    # Geladene Modelle stehen direkt unter GPU. Für Runs und History wird
    # bewusst Platz reserviert, damit die Bereiche nicht überzeichnen.
    row = section(row, "Geladene Modelle")
    history_rows = 5
    run_reserved_rows = 6
    model_end = h - 1 - history_rows - 2 - run_reserved_rows
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
    final_statuses = ("completed", "error", "cancelled")

    def run_sort_key(run):
        stamp = _parse_time(run.get("updated_at") or run.get("finished_at") or run.get("started_at"))
        return (stamp or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo),
                str(run.get("source", "")), str(run.get("run_id", "")))

    sources = ["pi", "open-webui"]
    sources.extend(sorted({run.get("source", "legacy") for run in active_runs
                           if run.get("source") not in sources}))
    groups = []
    for source in sources:
        source_runs = [run for run in active_runs if run.get("source") == source]
        if not source_runs:
            continue
        running = sorted((run for run in source_runs if run.get("status") not in final_statuses), key=run_sort_key)
        finished = sorted((run for run in source_runs if run.get("status") in final_statuses), key=run_sort_key)
        groups.append((source, running, finished))
    row = section(row, "Aktuelle Runs")
    grouped_runs = ([run for _source, running, _finished in groups for run in running] +
                    [run for _source, _running, finished in groups for run in finished])
    columns = history_columns()
    total_run_rows = max(3, min(12, h - row - history_rows - 2))
    visible_runs = max(1, total_run_rows - 1 - len(groups))
    max_run_offset = max(0, len(grouped_runs) - visible_runs)
    st["run_offset"] = min(max(0, st.get("run_offset", 0)), max_run_offset)
    visible = grouped_runs[st["run_offset"]:st["run_offset"] + visible_runs]
    if visible:
        for x, (name, width) in enumerate(columns):
            offset = sum(item[1] + 1 for item in columns[:x])
            _add(scr, row, offset, name, colors["structure"])
        row += 1
        visible_sources = [source for source, running, finished in groups
                           if any(run in visible for run in running + finished)]
        for source in visible_sources:
            source_visible = [run for run in visible if run.get("source") == source]
            source_all = next((item for item in groups if item[0] == source), None)
            running, finished = source_all[1], source_all[2]
            _add(scr, row, 0, f"{source_label(source)} (aktiv {len(running)} · Ergebnis {len(finished)})",
                 colors["structure"])
            row += 1
            for run in source_visible:
                cells = [current_run_cell(run, name)[:width].ljust(width) for name, width in columns]
                _add(scr, row, 0, " ".join(cells), colors["secondary"])
                rate_column = next((index for index, (name, _width) in enumerate(columns) if name == "rate"), None)
                if rate_column is not None:
                    rate_x = sum(width + 1 for _name, width in columns[:rate_column])
                    rate_value = current_run_cell(run, "rate")[:columns[rate_column][1]].rjust(columns[rate_column][1])
                    _add(scr, row, rate_x, rate_value, _rate_color(colors, token_rate(run)))
                row += 1
        if len(grouped_runs) > visible_runs:
            _add(scr, row, 0, f"Runs {st['run_offset'] + 1}-{min(len(grouped_runs), st['run_offset'] + visible_runs)} von {len(grouped_runs)}  ·  a/↑↓ scrollen",
                 colors["secondary"])
            row += 1
    else:
        _add(scr, row, 0, "Keine instrumentierten Requests", colors["secondary"])
        row += 1
    row += 1
    draw_history_table(row, h - row - 2)

    draw_footer("q quit  r neu laden  a Runs/History  Tab/s sortieren  ↑↓ scrollen")
    if st["help"]:
        sources = ", ".join(sorted(set(g.get("source", "?") for g in st["gpus"]))) or "keine"
        box = ["Hilfe", "", "q  Q  beenden", "r  Programm neu laden",
               "h  Hilfe ein/aus", "-  Intervall halbieren (min 0.2s)",
               "+  Intervall verdoppeln (max 60s)",
               "a  Aktuelle Runs oder History fokussieren",
               "Tab / Shift-Tab  History-Spalte wechseln", "s  History-Sortierrichtung",
               "↑/↓ Bild↑/Bild↓ Pos1/Ende  fokussierten Bereich scrollen", "",
               "System / GPU / Ollama / History", "GPU-Quelle: " + sources]
        bh = len(box) + 2
        bw = max(len(b) for b in box) + 4
        y0 = max(1, (h - bh) // 2)
        x0 = max(0, (w - bw) // 2)
        if bw <= w and y0 + bh <= h - 1:
            for j in range(bh):
                if j == 0 or j == bh - 1:
                    _add(scr, y0 + j, x0, "+" + "-" * (bw - 2) + "+", colors["structure"], indent=False)
                else:
                    text = box[j - 1]
                    _add(scr, y0 + j, x0, "| " + text.ljust(bw - 4) + " |", colors["structure"], indent=False)
    scr.refresh()




def _run_tui(host, interval, use_nvidia, version, pixel_icon):
    """Fuehrt curses im Hauptthread und die Erfassung im Hintergrund aus."""
    global VERSION, PIXEL_ICON
    VERSION = version
    PIXEL_ICON = pixel_icon
    collector = CollectorService()
    collector.start()
    state = {"colors": None, "help": False, "prev_cpu": read_cpu_totals(),
             "ollama": {"ok": False, "version": None, "models": [], "error": "Messung"},
             "cpu": None, "cpu_temp": None, "cpu_temp_source": None,
             "gpus": [], "gpu_err": None, "ram": (None, None, None),
             "history_ok": None, "runs": [], "run_history": [],
             "collector_status": collector.status(), "history_sort": "zeit",
             "history_desc": True, "history_offset": 0, "run_offset": 0,
             "run_focus": False}
    lock = threading.Lock()
    stop = threading.Event()
    refresh = threading.Event()

    def sample():
        nonlocal interval
        while not stop.is_set():
            ollama = collect_ollama(host)
            runs = load_run_events()
            run_history = load_run_history()
            backfill_context_limits(run_history, ollama.get("models", []))
            gpus, gpu_err = collect_gpus(use_nvidia)
            cur = read_cpu_totals()
            with lock:
                previous = state["prev_cpu"]
            cpu = cpu_percent(previous, cur)
            ram = get_ram_pct()
            cpu_temp, cpu_temp_source = cpu_temperature()
            history_ok = write_history(snapshot_record(
                host, ollama, cpu, ram, gpus, gpu_err, runs[0] if runs else None))
            with lock:
                state.update({"ollama": ollama, "runs": runs, "run_history": run_history,
                              "gpus": gpus, "gpu_err": gpu_err, "prev_cpu": cur,
                              "cpu": cpu, "ram": ram, "cpu_temp": cpu_temp,
                              "cpu_temp_source": cpu_temp_source, "history_ok": history_ok,
                              "collector_status": collector.status()})
                delay = interval
            refresh.wait(max(0.2, delay))
            refresh.clear()

    worker = threading.Thread(target=sample, name="llmtop-sampler", daemon=True)
    worker.start()

    def session(scr):
        nonlocal interval
        curses.curs_set(0)
        scr.keypad(True)
        with lock:
            state["colors"] = _init_colors()
        while True:
            with lock:
                view = dict(state)
            _draw(scr, view, host, interval)
            scr.timeout(250)
            key = scr.getch()
            if key == -1:
                continue
            if key in (ord("q"), ord("Q")):
                return 0
            if key in (ord("r"), ord("R")):
                return "reload"
            with lock:
                if key in (ord("h"), ord("H")):
                    state["help"] = not state["help"]
                elif key in (ord("+"), ord("=")):
                    interval = min(60.0, interval * 2)
                    refresh.set()
                elif key == ord("-"):
                    interval = max(0.2, interval / 2)
                    refresh.set()
                elif key in (ord("a"), ord("A")):
                    state["run_focus"] = not state["run_focus"]
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
                    target = "run_offset" if state["run_focus"] else "history_offset"
                    state[target] = max(0, state[target] - 1)
                elif key == curses.KEY_DOWN:
                    target = "run_offset" if state["run_focus"] else "history_offset"
                    state[target] += 1
                elif key == curses.KEY_PPAGE:
                    target = "run_offset" if state["run_focus"] else "history_offset"
                    state[target] = max(0, state[target] - 5)
                elif key == curses.KEY_NPAGE:
                    target = "run_offset" if state["run_focus"] else "history_offset"
                    state[target] += 5
                elif key == curses.KEY_HOME:
                    state["run_offset" if state["run_focus"] else "history_offset"] = 0
                elif key == curses.KEY_END:
                    target = "run_offset" if state["run_focus"] else "history_offset"
                    state[target] = max(0, (len(state["runs"]) if state["run_focus"] else len(state["run_history"])) - 1)
        return 0

    try:
        result = curses.wrapper(session)
    finally:
        stop.set()
        refresh.set()
        worker.join(timeout=0.2)
        collector.stop()
    if result == "reload":
        os.execv(sys.executable, [sys.executable, *sys.argv])
    return result
