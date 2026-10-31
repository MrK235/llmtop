"""curses-Oberflaeche fuer otop."""
import curses
import os
import sys
import threading
import time
from datetime import datetime

VERSION = "?"

from otop_metrics import (
    DEFAULT_RUN_HISTORY_LIMIT, HISTORY_COLUMNS, CollectorService, _parse_time, _token_value,
    backfill_context_limits, compact_tokens, context_values, history_context_cell,
    history_header_label, load_run_events, load_run_history, model_for_run,
    run_metric_detail, snapshot_record, sort_run_history, source_label, token_rate, total_tokens,
    write_history,
)
from otop_sources import (
    GPU_POWER_BOOST_W, bar, collect_gpus, collect_ollama, cpu_percent,
    cpu_temperature, get_ram_pct, loadavg, read_cpu_totals,
)
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
         "model_name": curses.A_DIM | curses.A_UNDERLINE, "context_label": curses.A_BOLD,
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
        c["context_label"] = curses.color_pair(4) | curses.A_BOLD
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
        x = 2
        prefix = f"── {title} "
        _add(scr, row, x, prefix + "─" * max(0, w - x - len(prefix) - 1), colors["structure"])
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
        meta = "\t".join((str(details.get("parameter_size", "-")),
                          str(details.get("quantization_level", "-")),
                          f"ctx {model.get('context_length', '-')}",
                          str(model.get("runner", "-"))))
        meta_x = max(24, ((len(name) + 9) // 8) * 8)
        _add(scr, row, 0, name, colors["model_name"])
        _add(scr, row, meta_x, meta, colors["secondary"])
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
        x += bar_w + 3
        if gpu_pct is None:
            _add(scr, row, x, "VRAM/RAM n/a", colors["secondary"])
        else:
            pct_text = f"{gpu_pct:.0f}%/{100 - gpu_pct:.0f}%"
            sizes = (f"VRAM {vram / (1024 ** 3):.1f} GiB / "
                     f"RAM {cpu_mem / (1024 ** 3):.1f} GiB")
            _add(scr, row, x, pct_text.rjust(7), gpu_attr)
            _add(scr, row, x + 8, sizes, colors["secondary"])
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
            age = (f"vor {run['age_seconds']:.1f}s" if run.get("age_seconds") is not None else "")
            details = run_metric_detail(run)
            columns = (source_label(run.get("source")), str(run.get("model", "?")),
                       str(run.get("status", "unknown")), details)
            text = "\t".join(columns) + (f"\t{age}" if age else "")
            _add(scr, row, 0, text, colors["secondary"])
            row += 1
            used, limit, pct = context_values(run, model_for_run(run, oll["models"]))
            value = (f"{compact_tokens(used)} / {compact_tokens(limit)}"
                     if used is not None else "warten auf Provider")
            pct_text = f"{pct:.1f} %" if pct is not None else "n/a"
            x = 0
            _add(scr, row, x, "Kontext".ljust(label_w), colors["context_label"])
            x += label_w
            meter = bar(pct, bar_w)
            _add(scr, row, x, meter, _util_color(colors, pct))
            x += len(meter) + 1
            _add(scr, row, x, pct_text.rjust(7), _util_color(colors, pct))
            x += 8
            _add(scr, row, x, value, colors["secondary"])
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




def _run_tui(host, interval, use_nvidia, version):
    """Fuehrt curses im Hauptthread und die Erfassung im Hintergrund aus."""
    global VERSION
    VERSION = version
    collector = CollectorService()
    collector.start()
    state = {"colors": None, "help": False, "prev_cpu": read_cpu_totals(),
             "ollama": {"ok": False, "version": None, "models": [], "error": "Messung"},
             "cpu": None, "cpu_temp": None, "cpu_temp_source": None,
             "gpus": [], "gpu_err": None, "ram": (None, None, None),
             "history_ok": None, "runs": [], "run_history": [],
             "collector_status": collector.status(), "history_sort": "zeit",
             "history_desc": True, "history_offset": 0}
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
            refresh.wait(max(0.5, delay))
            refresh.clear()

    worker = threading.Thread(target=sample, name="otop-sampler", daemon=True)
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
                    interval = max(0.5, interval / 2)
                    refresh.set()
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
