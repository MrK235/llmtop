"""curses-Oberflaeche fuer llmtop."""
import curses
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime

VERSION = "?"
PIXEL_ICON = ("╔══════╗", "║ >▞_  ║", "║  LLM ║", "╚══════╝")
HISTORY_WRITE_INTERVAL = 5.0

from llmtop_metrics import (
    DEFAULT_RUN_HISTORY_LIMIT, HISTORY_COLUMNS, CollectorService, _parse_time, _token_value,
    backfill_context_limits, clear_run_history, compact_tokens, context_values,
    history_header_label, load_run_events, load_run_history, model_for_run,
    run_group_key, run_identity_label, snapshot_record, sort_run_history,
    source_label, token_rate, total_tokens,
    write_history,
)
log = logging.getLogger(__name__)

from llmtop_sources import (
    CPU_POWER_DISPLAY_SCALE_W, GPU_POWER_DISPLAY_SCALE_W, PrivilegedRaplReader,
    bar, collect_cpu_power,
    collect_gpus, collect_ollama, cpu_count, cpu_name, cpu_percent,
    cpu_temperature, get_ram_pct, read_cpu_totals,
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
    """Färbt Auslastungsbalken in vier abgestuften Statusfarben."""
    if pct is None:
        return colors["secondary"]
    if pct > 90:
        return colors["error"]
    if pct >= 60:
        return colors["status_orange"]
    if pct >= 30:
        return colors["status_amber"]
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


def history_group_key(run):
    """Liefert den quellengetrennten, stabilen Schlüssel einer History-Gruppe."""
    return (run.get("source", "legacy"), run_group_key(run))


def _history_time(value):
    return _parse_time(value) or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)


def _latest_history_run(runs):
    """Wählt den neuesten Abschluss mit stabilen Zeit- und ID-Tie-Breakern."""
    return max(runs, key=lambda run: (_history_time(run.get("finished_at")),
                                      _history_time(run.get("updated_at")),
                                      _history_time(run.get("started_at")),
                                      str(run.get("run_id", ""))))


def _webui_energy_wh(run):
    """Liefert Energie nur für Open-WebUI-Runs in Wh."""
    if not isinstance(run, dict) or run.get("source") != "open-webui":
        return None
    energy = run.get("energy")
    value = energy.get("energy_j") if isinstance(energy, dict) else None
    return value / 3600.0 if isinstance(value, (int, float)) and value >= 0 else None


def aggregate_history_group(group):
    """Erzeugt die Gruppenzeile ausschließlich aus dem neuesten finalen Run."""
    latest = _latest_history_run(group["runs"])
    aggregate = dict(latest)
    aggregate["run_id"] = f"group:{group['key']}"
    aggregate["model"] = f"{latest.get('model', '?')} ×{len(group['runs'])}"

    # Nur Werte desselben repräsentativen Runs dürfen normalisiert werden.
    if (aggregate.get("context_tokens") is None and
            _token_value(aggregate, "prompt_tokens") is not None and
            _token_value(aggregate, "output_tokens") is not None):
        aggregate["context_tokens"] = (aggregate["prompt_tokens"] +
                                        aggregate["output_tokens"])
    if aggregate.get("total_duration_s") is None:
        started = _parse_time(aggregate.get("started_at"))
        finished = _parse_time(aggregate.get("finished_at"))
        if started and finished and finished >= started:
            aggregate["total_duration_s"] = (finished - started).total_seconds()

    if aggregate.get("source") == "open-webui":
        energies = [_webui_energy_wh(run) for run in group["runs"]]
        if all(value is not None for value in energies):
            aggregate["energy"] = {"energy_j": sum(energies) * 3600.0,
                                     "energy_scope": "group-sum"}
        else:
            aggregate.pop("energy", None)
    else:
        aggregate.pop("energy", None)
    source = source_label(aggregate.get("source"), aggregate.get("provider"))
    if aggregate.get("source") == "open-webui":
        source = source.replace("Open WebUI", "WebUI", 1)
    identity = run_identity_label(aggregate)
    aggregate["_source_label"] = f"{source} · {identity}"
    return aggregate


def indented_history_run(run):
    """Rückt ausschließlich die Quelle eines untergeordneten History-Runs ein."""
    child = dict(run)
    # Die Gruppenzeile beginnt bereits mit dem zweistelligen Aufklappmarker.
    # Vier Leerzeichen setzen den eigentlichen Quelltext zwei Spalten dahinter.
    child["_source_label"] = "    " + source_label(run.get("source"), run.get("provider"))
    # Das Zeitfeld wird innerhalb seiner eigenen Spalte um zwei Zeichen
    # eingerückt; die Spaltenberechnung berücksichtigt diese Breite.
    child["_history_child"] = True
    return child


def build_history_groups(sorted_runs, column="zeit", descending=True):
    """Baut Gruppen nach den sichtbaren Werten ihrer neuesten Runs."""
    groups = {}
    for run in sorted_runs:
        key = history_group_key(run)
        group = groups.setdefault(key, {"key": key, "runs": [], "first": run})
        group["runs"].append(run)
    result = []
    for group in groups.values():
        field, _value = group["key"][1]
        group["grouped"] = len(group["runs"]) > 1 or field != "run_id"
        group["aggregate"] = aggregate_history_group(group)
        result.append(group)
    # Die Kopfzeilen und ihre Sortierung verwenden dieselben repräsentativen
    # Werte. Die Reihenfolge der Einzelruns innerhalb einer Gruppe bleibt dabei
    # unverändert.
    aggregates = sort_run_history([group["aggregate"] for group in result], column, descending)
    by_id = {id(group["aggregate"]): group for group in result}
    return [by_id[id(aggregate)] for aggregate in aggregates]


def history_display_items(runs, column="zeit", descending=True, expanded=()):
    """Liefert den sichtbaren History-Strom aus Gruppen- und Run-Zeilen."""
    sorted_runs = sort_run_history(runs, column, descending)
    expanded = set(expanded or ())
    items = []
    for group in build_history_groups(sorted_runs, column, descending):
        group_key = group["key"]
        if group["grouped"]:
            items.append({"kind": "group", "key": ("group", group_key), "group": group})
            if group_key not in expanded:
                continue
        for run in group["runs"]:
            items.append({"kind": "run", "key": ("run", group_key, run.get("run_id")),
                          "group_key": group_key, "grouped": group["grouped"], "run": run})
    return sorted_runs, items


def normalize_history_state(state):
    """Korrigiert Cursor, aufgeklappte Gruppen und leere History-Zustände."""
    sorted_runs, items = history_display_items(
        state.get("run_history", []), state.get("history_sort", "zeit"),
        state.get("history_desc", True), state.get("history_expanded", ()))
    group_keys = {group["key"] for group in build_history_groups(
        sorted_runs, state.get("history_sort", "zeit"), state.get("history_desc", True))
        if group["grouped"]}
    state["history_expanded"] = set(state.get("history_expanded", ())) & group_keys
    item_keys = [item["key"] for item in items]
    if state.get("history_cursor") not in item_keys:
        state["history_cursor"] = item_keys[0] if item_keys else None
    return sorted_runs, items


def _init_colors():
    """Zentrale Farbrollen: Struktur, Status, Offload und Sekundärtext."""
    c = {"structure": curses.A_BOLD, "secondary": curses.A_DIM,
         "group": curses.A_NORMAL, "cursor": curses.A_REVERSE,
         "model_name": curses.A_DIM | curses.A_UNDERLINE, "context_label": curses.A_BOLD,
         "bar_bracket": curses.A_NORMAL,
         "status_green": curses.A_BOLD, "status_yellow": curses.A_BOLD,
         "status_amber": curses.A_BOLD, "status_orange": curses.A_BOLD,
         "rate_green": 0, "rate_yellow": 0, "rate_error": 0,
         "error": curses.A_BOLD, "offload_good": curses.A_BOLD,
         "offload_mixed": curses.A_BOLD, "offload_cpu": curses.A_BOLD}
    if curses.COLORS >= 8:
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_CYAN)
        c["status_green"] = curses.color_pair(1) | curses.A_BOLD
        c["bar_bracket"] = curses.color_pair(4)
        c["context_label"] = curses.color_pair(4) | curses.A_BOLD
        c["status_yellow"] = curses.color_pair(2) | curses.A_BOLD
        # 256-Farbterminals erhalten Orange und ein nur wenig helleres Amber.
        # Im 8-Farb-Fallback unterscheiden sich beide über die Fettdarstellung.
        c["status_amber"] = curses.color_pair(2) | curses.A_BOLD
        c["status_orange"] = curses.color_pair(2)
        if curses.COLORS >= 256:
            curses.init_pair(8, 214, curses.COLOR_BLACK)
            curses.init_pair(9, 208, curses.COLOR_BLACK)
            c["status_amber"] = curses.color_pair(8) | curses.A_BOLD
            c["status_orange"] = curses.color_pair(9) | curses.A_BOLD
        c["rate_green"] = curses.color_pair(1)
        c["rate_yellow"] = curses.color_pair(2)
        c["rate_error"] = curses.color_pair(3)
        c["error"] = curses.color_pair(3) | curses.A_BOLD
        c["structure"] = curses.color_pair(4) | curses.A_BOLD
        # Gedimmtes Weiß ergibt die gewünschte graue Gruppenzeile, ohne
        # terminalspezifische Fettdarstellung.
        c["group"] = curses.color_pair(6) | curses.A_DIM
        c["cursor"] = curses.color_pair(7)
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
    history_runs, history_items = normalize_history_state(st)
    cursor_attr = colors["cursor"]
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

    def draw_meter(row, x, pct, width, fill_attr, bracket_attr=None):
        """Zeichnet den Inhalt farbig und erlaubt eine gedimmte Sonderzeile."""
        meter = bar(pct, width)
        bracket_attr = (bracket_attr if bracket_attr is not None else
                        colors.get("bar_bracket", colors["structure"]))
        _add(scr, row, x, "[", bracket_attr)
        _add(scr, row, x + 1, meter[1:-1], fill_attr)
        _add(scr, row, x + len(meter) - 1, "]", bracket_attr)
        return meter

    def sensor(row, label, pct, value, detail="", value_attr=None, accent="", accent_attr=None,
               meter_attr=None, label_attr=None, bracket_attr=None):
        x = 0
        _add(scr, row, x, label.ljust(label_w),
             label_attr if label_attr is not None else colors["structure"])
        x += label_w
        attr = _util_color(colors, pct)
        meter = draw_meter(row, x, pct, bar_w,
                           meter_attr if meter_attr is not None else attr,
                           bracket_attr=bracket_attr)
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
        pi_active = bool(st.get("pi_adapter_active"))
        pi_state = "aktiv" if pi_active else "nicht aktiv"
        pi_short = "OK" if pi_active else "OFF"
        pi_attr = colors["status_green"] if pi_active else colors["error"]
        icon = tuple(PIXEL_ICON) if isinstance(PIXEL_ICON, (tuple, list)) else (PIXEL_ICON,) * 4
        icon = (icon + (icon[-1],) * 4)[:4]
        for row, pixel in enumerate(icon):
            _add(scr, row, 1, pixel, colors["structure"], indent=False)

        # Acht Zeichen Breite gleichen bei Terminal-Zeichen annähernd vier Zeilen Höhe aus.
        # Das Logo kombiniert einen Terminal-Prompt mit einer LLM-Kennung.
        # Zwei freie Spalten trennen das Logo vom Textblock.
        x = 11
        if w >= 72:
            label_width = 22
            _add(scr, 0, x, f"llmtop {VERSION}", colors["structure"], indent=False)
            ollama_label = f"Ollama v{version}"
            _add(scr, 1, x, ollama_label.ljust(label_width), colors["secondary"], indent=False)
            _add(scr, 1, x + label_width, ollama_state, ollama_attr, indent=False)
            _add(scr, 2, x, "Open-WebUI Collector".ljust(label_width), colors["secondary"], indent=False)
            _add(scr, 2, x + label_width, collector_state, collector_attr, indent=False)
            _add(scr, 3, x, "Pi Adapter".ljust(label_width), colors["secondary"], indent=False)
            _add(scr, 3, x + label_width, pi_state, pi_attr, indent=False)
        else:
            ollama_label = f"Ollama v{version} "
            _add(scr, 1, x, ollama_label, colors["secondary"], indent=False)
            _add(scr, 1, x + len(ollama_label), ollama_short, ollama_attr, indent=False)
            _add(scr, 2, x, "OW Collector ", colors["secondary"], indent=False)
            _add(scr, 2, x + 13, collector_short, collector_attr, indent=False)
            compact_label = f"llmtop {VERSION} · Pi "
            _add(scr, 3, x, compact_label, colors["secondary"], indent=False)
            _add(scr, 3, x + len(compact_label), pi_short, pi_attr, indent=False)

    def draw_footer(text):
        """Zeichnet Navigation grau; Tasten und Steuersymbole bleiben Cyan."""
        interval_text = f"-/+ intervall {interval:.1f}s"
        interval_x = max(0, w - len(interval_text) - 1)

        def footer_part(value, x):
            _add(scr, h - 1, x, value, colors["secondary"], indent=False)
            for offset, char in enumerate(value):
                is_key = (char in "qrxch" and
                          (offset == 0 or value[offset - 1].isspace()) and
                          (offset + 1 == len(value) or value[offset + 1].isspace()))
                if char in "▴▾↑↓-/+" or is_key:
                    _add(scr, h - 1, x + offset, char, colors["structure"], indent=False)

        footer_part(text[:max(0, interval_x - 1)], 0)
        footer_part(interval_text, interval_x)

    def table_columns(runs, cell):
        """Ermittelt Breiten aus allen Zeilen der jeweiligen Tabelle."""
        # Quelle/Provider bleibt auch in schmalen Ansichten sichtbar; weitere
        # Spalten folgen, sobald der verfügbare Platz dies zulässt.
        if w >= 118:
            names = ("zeit", "quelle", "modell", "status", "tokens", "kontext", "rate", "dauer", "wh")
        elif w >= 80:
            names = ("zeit", "quelle", "modell", "status", "tokens", "kontext")
        else:
            names = ("zeit", "quelle", "modell", "status")

        widths = []
        for name in names:
            header = history_header_label(name, st["history_sort"], st["history_desc"])
            values = [cell(run, name) for run in runs]
            widths.append(max(len(header), *(len(value) for value in values), 1))

        # Inhalt wird nur dann gekürzt, wenn er nicht ins Terminal passt.
        # Die Mindestbreite schützt Überschriften und die Kontextkennung. Die
        # Quellenkennung wird zuletzt gekürzt, damit ihr verfügbarer Platz
        # möglichst vollständig erhalten bleibt.
        minimums = [max(len(history_header_label(name, st["history_sort"], st["history_desc"])),
                        9 if name == "kontext" else 1)
                    for name in names]
        overflow = sum(widths) + len(widths) - 1 - max(1, w - 2)
        while overflow > 0:
            candidates = [index for index, width in enumerate(widths)
                          if width > minimums[index] and names[index] != "quelle"]
            if not candidates:
                candidates = [index for index, width in enumerate(widths)
                              if width > minimums[index]]
            if not candidates:
                break
            index = max(candidates, key=lambda item: widths[item] - minimums[item])
            widths[index] -= 1
            overflow -= 1
        return tuple(zip(names, widths))

    def context_table_cell(run, model=None):
        used, limit, pct = context_values(run, model)
        if used is None:
            return "n/a"
        pct_text = f"{pct:.0f}%" if pct is not None else "n/a"
        meter = bar(pct, 12)
        limit_text = compact_tokens(limit) if limit is not None else "n/a"
        # Der Balken steht zuerst; der Prozentwert folgt rechtsbündig auf
        # einer festen Breite und kann dadurch die Balkenposition nicht verschieben.
        return f"{meter} {pct_text.rjust(4)} {limit_text}"

    def history_cell(run, column):
        model = model_for_run(run, oll.get("models", [])) if oll else None
        if column == "zeit":
            finished = _parse_time(run.get("finished_at"))
            if not finished:
                value = "n/a"
            else:
                value = finished.strftime("%d.%m %H:%M") if w >= 118 else finished.strftime("%H:%M")
            return "  " + value if run.get("_history_child") else value
        if column == "quelle":
            return run.get("_source_label") or source_label(run.get("source"), run.get("provider"))
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
        if column == "wh":
            value = _webui_energy_wh(run)
            return f"{value:.3f}" if value is not None else "n/a" if run.get("source") == "open-webui" else ""
        return ""

    def current_run_cell(run, column):
        if column == "zeit":
            stamp = _parse_time(run.get("finished_at") or run.get("started_at"))
            value = stamp.strftime("%d.%m %H:%M") if stamp else "n/a"
            return "  " + value if run.get("_history_child") else value
        return history_cell(run, column)

    def draw_history_context_cell(row, x, width, run, row_attr):
        """Hält den History-Kontext statusgrau und übernimmt die Cursorhervorhebung."""
        text = history_cell(run, "kontext")
        _add(scr, row, x, text[:width].ljust(width), row_attr)

    def draw_live_context_cell(row, x, width, run):
        used, limit, pct = context_values(run, model_for_run(run, oll.get("models", [])))
        if used is None:
            _add(scr, row, x, "n/a".ljust(width), colors["secondary"])
            return
        pct_text = f"{pct:.0f}%" if pct is not None else "n/a"
        meter = draw_meter(row, x, pct, 12, _util_color(colors, pct))
        percentage = f" {pct_text.rjust(4)}"
        limit = f" {compact_tokens(limit) if limit is not None else 'n/a'}"
        available = max(0, width - len(meter) - len(percentage) - len(limit))
        _add(scr, row, x + len(meter), percentage[:max(0, width - len(meter))],
             _util_color(colors, pct))
        limit_x = x + len(meter) + len(percentage) + available
        if limit_x < x + width:
            _add(scr, row, limit_x, limit[:max(0, x + width - limit_x)], colors["secondary"])

    def draw_history_table(row, max_rows, columns=None):
        sorted_runs = history_runs
        items = history_items
        groups = build_history_groups(sorted_runs, st["history_sort"], st["history_desc"])
        # Der Aufklappmarker wird erst beim Rendern ergänzt; für die
        # Spaltenberechnung muss er dennoch berücksichtigt werden.
        aggregate_runs = [dict(group["aggregate"], _source_label="▸ " +
                               group["aggregate"]["_source_label"])
                          for group in groups if group["grouped"]]
        child_runs = [indented_history_run(run) for group in groups if group["grouped"]
                      for run in group["runs"]]
        columns = columns or table_columns(sorted_runs + aggregate_runs + child_runs, history_cell)
        total = len(sorted_runs)
        group_count = len(groups)
        data_rows = max(1, max_rows - 2)
        show_position = len(items) > data_rows and data_rows >= 2
        visible = data_rows - 1 if show_position else data_rows
        max_offset = max(0, len(items) - visible)
        cursor_keys = [item["key"] for item in items]
        cursor_index = cursor_keys.index(st["history_cursor"]) if st.get("history_cursor") in cursor_keys else 0
        offset = min(max(0, st.get("history_offset", 0)), max_offset)
        if items:
            if cursor_index < offset:
                offset = cursor_index
            elif cursor_index >= offset + visible:
                offset = cursor_index - visible + 1
        st["history_offset"] = offset
        row = section(row, f"History ({total}/{DEFAULT_RUN_HISTORY_LIMIT} Runs · {group_count} Gruppen)")
        x = 0
        for name, width in columns:
            label = history_header_label(name, st["history_sort"], st["history_desc"])
            attr = colors["structure"] | curses.A_UNDERLINE if name == st["history_sort"] else colors["structure"]
            _add(scr, row, x, label[:width], attr)
            x += width + 1
        row += 1
        for item in items[offset:offset + visible]:
            active = item["key"] == st.get("history_cursor")
            if item["kind"] == "group":
                group = item["group"]
                marker = "▾" if group["key"] in st.get("history_expanded", set()) else "▸"
                run = dict(group["aggregate"])
                run["_source_label"] = f"{marker} {run['_source_label']}"
            else:
                run = (indented_history_run(item["run"])
                       if item.get("grouped") else item["run"])
            cells = []
            for name, width in columns:
                text = history_cell(run, name)
                cells.append(text[:width].ljust(width))
            attr = cursor_attr if active else (colors["group"] if item["kind"] == "group"
                                                else colors["secondary"])
            # Die Zwischenräume zwischen Spalten brauchen ebenfalls den
            # Cursorhintergrund, sonst wirkt die aktive Zeile unterbrochen.
            if active:
                _add(scr, row, 0, " " * len(" ".join(cells)), attr)
            # History-Kontext bleibt statusgrau; die aktive Cursorzeile bleibt
            # für eine durchgehende Hervorhebung vollständig markiert.
            x = 0
            for index, (name, width) in enumerate(columns):
                if name == "kontext":
                    draw_history_context_cell(row, x, width, run, attr)
                else:
                    _add(scr, row, x, cells[index], attr)
                x += width + 1
            row += 1
        if not sorted_runs:
            _add(scr, row, 0, "Keine abgeschlossenen instrumentierten Runs", colors["secondary"])
            row += 1
        elif show_position:
            _add(scr, row, 0,
                 f"Einträge {offset + 1}-{min(len(items), offset + visible)} von {len(items)} · "
                 f"{total} Runs · {group_count} Gruppen", colors["secondary"])
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
        power_watt = st.get("cpu_power_watt")
        power_limit = st.get("cpu_power_limit")
        power_pct = (min(100.0, 100.0 * power_watt / power_limit)
                     if power_watt is not None and power_limit and power_limit > 0 else None)
        power_meter_pct = (power_pct if power_pct is not None else
                           min(100.0, 100.0 * power_watt / CPU_POWER_DISPLAY_SCALE_W)
                           if power_watt is not None else None)
        power_value = (f"{power_pct:.1f} %" if power_pct is not None else
                       f"{power_watt:.1f} W" if power_watt is not None else "n/a")
        power_detail = st.get("cpu_power_source") or "keine CPU-Powerquelle"
        if power_watt is not None and power_limit and power_limit > 0:
            power_detail = f"{power_watt:.1f} W / {power_limit:.1f} W  ·  {power_detail}"
        rapl_status = st.get("rapl_status")
        if power_watt is None and rapl_status == "nicht aktiviert":
            power_detail += "  ·  x: sudo aktivieren"
        elif power_watt is None and rapl_status:
            power_detail += f"  ·  {rapl_status}"
        power_attr = (_util_color(colors, power_pct) if power_pct is not None else
                      colors["status_green"] if power_watt is not None else colors["secondary"])
        row = sensor(row, "Power", power_meter_pct, power_value, power_detail,
                     value_attr=power_attr, meter_attr=power_attr)
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
        draw_footer("q quit   r reload   x sudo   c clear   ▴▾ return   ↑↓ cursor   h help")
        scr.refresh()
        return

    def model_card(row, model, meta_x):
        details = model.get("details") or {}
        size = max(0, model.get("size") or 0)
        vram = max(0, min(size, model.get("size_vram") or 0)) if size else 0
        cpu_mem = max(0, size - vram)
        gpu_pct = 100.0 * vram / size if size else None
        name = str(model.get("name", "?"))
        meta_fields = (
            (0, str(details.get("parameter_size", "-"))),
            (8, str(details.get("quantization_level", "-"))),
            (20, f"ctx {model.get('context_length', '-')}"),
            (32, str(model.get("runner", "-"))),
        )
        _add(scr, row, 0, name, colors["model_name"])
        for offset, value in meta_fields:
            _add(scr, row, meta_x + offset, value, colors["secondary"])
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
            bracket_attr = colors.get("bar_bracket", colors["structure"])
            _add(scr, row, x, "[", bracket_attr)
            _add(scr, row, x + 1, " " * bar_w, colors["secondary"])
            _add(scr, row, x + bar_w + 1, "]", bracket_attr)
        else:
            gpu_width = max(0, min(bar_w, int(round(gpu_pct * bar_w / 100.0))))
            cpu_width = bar_w - gpu_width
            gpu_attr = _offload_color(colors, gpu_pct)
            bracket_attr = colors.get("bar_bracket", colors["structure"])
            _add(scr, row, x, "[", bracket_attr)
            _add(scr, row, x + 1, "#" * gpu_width, gpu_attr)
            _add(scr, row, x + 1 + gpu_width, "#" * cpu_width, colors["secondary"])
            _add(scr, row, x + bar_w + 1, "]", bracket_attr)
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
    cpu_detail = f"{cpu_name()}  •  {cpu_count()} Kerne  ·  Temp "
    cpu_accent = f"{cpu_temp:.1f} °C" if cpu_temp is not None else "n/a"
    row = sensor(row, "CPU", cpu, cpu_value, cpu_detail, accent=cpu_accent,
                 accent_attr=_temp_color(colors, cpu_temp))
    power_watt = st.get("cpu_power_watt")
    power_limit = st.get("cpu_power_limit")
    power_pct = (min(100.0, 100.0 * power_watt / power_limit)
                 if power_watt is not None and power_limit and power_limit > 0 else None)
    power_meter_pct = (power_pct if power_pct is not None else
                       min(100.0, 100.0 * power_watt / CPU_POWER_DISPLAY_SCALE_W)
                       if power_watt is not None else None)
    power_value = (f"{power_pct:.1f} %" if power_pct is not None else
                   f"{power_watt:.1f} W" if power_watt is not None else "n/a")
    power_detail = st.get("cpu_power_source") or "keine CPU-Powerquelle"
    if power_watt is not None and power_limit and power_limit > 0:
        power_detail = f"{power_watt:.1f} W / {power_limit:.1f} W  ·  {power_detail}"
    rapl_status = st.get("rapl_status")
    if power_watt is None and rapl_status == "nicht aktiviert":
        power_detail += "  ·  x: sudo aktivieren"
    elif power_watt is None and rapl_status:
        power_detail += f"  ·  {rapl_status}"
    power_attr = (_util_color(colors, power_pct) if power_pct is not None else
                  colors["status_green"] if power_watt is not None else colors["secondary"])
    row = sensor(row, "Power", power_meter_pct, power_value, power_detail,
                 value_attr=power_attr, meter_attr=power_attr)
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
        if i:
            _add(scr, row, 0, "  ··· weitere GPU ···", colors["secondary"])
            row += 1
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
        # Die interne GPU1/AMD-APU liefert denselben CPU-Powerwert; bei
        # vorhandener CPU-Power wird die doppelte GPU1-Zeile unterdrückt.
        if (g.get("power_scope") == "cpu"
                and st.get("cpu_power_watt") is not None):
            continue
        if g["power_watt"] is not None or g.get("power_scope") == "cpu":
            power_attr = (colors["secondary"]
                          if g.get("power_scope") == "cpu" else None)
            if g["power_watt"] is None:
                power_pct = None
                power_value = "n/a"
                power_detail = "keine GPU-Powerquelle"
            else:
                limit = g.get("power_limit")
                if limit and limit > 0:
                    power_pct = min(100.0, 100.0 * g["power_watt"] / limit)
                    power_value = f"{power_pct:.1f} %"
                    power_detail = f"{g['power_watt']:.1f} W / {limit:.0f} W"
                else:
                    power_pct = min(100.0, 100.0 * g["power_watt"] / GPU_POWER_DISPLAY_SCALE_W)
                    power_value = f"{g['power_watt']:.1f} W"
                    power_detail = "keine Leistungsgrenze"
            row = sensor(row, "Power", power_pct, power_value, power_detail,
                         value_attr=power_attr, meter_attr=power_attr,
                         label_attr=power_attr, bracket_attr=power_attr)

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
        # Alle Modellkarten teilen sich dieselbe Startspalte und feste
        # Metadaten-Spalten; dadurch bleiben Name, Quantisierung, Kontext und
        # Runner unabhängig von Namens- und Kontextlängen untereinander.
        model_name_lengths = [len(str(model.get("name", "?"))) for model in oll["models"]]
        model_meta_x = max(16, ((max(model_name_lengths) + 9) // 8) * 8)
        shown_models = 0
        while shown_models < len(oll["models"]) and row + 2 <= model_end:
            row = model_card(row, oll["models"][shown_models], model_meta_x)
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
        source_runs = sorted((run for run in active_runs if run.get("source") == source),
                             key=run_sort_key, reverse=True)
        if not source_runs:
            continue
        identity_groups = {}
        for run in source_runs:
            identity_groups.setdefault(run_group_key(run), []).append(run)
        for identity_runs in identity_groups.values():
            running = sorted((run for run in identity_runs
                              if run.get("status") not in final_statuses), key=run_sort_key)
            finished = sorted((run for run in identity_runs
                              if run.get("status") in final_statuses), key=run_sort_key)
            groups.append((source, identity_runs[0], running, finished))
    row = section(row, "Aktuelle Runs")
    grouped_runs = ([run for _source, _identity, running, _finished in groups for run in running] +
                    [run for _source, _identity, _running, finished in groups for run in finished])
    # Beide Tabellen teilen eine Breitenberechnung, damit aktuelle Runs und
    # History unabhängig vom sichtbaren Ausschnitt exakt untereinander stehen.
    sorted_history = sort_run_history(runs, st["history_sort"], st["history_desc"])
    history_groups = build_history_groups(sorted_history, st["history_sort"], st["history_desc"])
    history_aggregates = [dict(group["aggregate"], _source_label="▸ " +
                               group["aggregate"]["_source_label"])
                          for group in history_groups if group["grouped"]]
    history_children = [indented_history_run(run) for group in history_groups if group["grouped"]
                        for run in group["runs"]]
    columns = table_columns(runs + history_aggregates + history_children + grouped_runs,
                            current_run_cell)
    total_run_rows = max(3, min(12, h - row - history_rows - 2))
    visible_runs = max(1, total_run_rows - 1 - len(groups))
    max_run_offset = max(0, len(grouped_runs) - visible_runs)
    st["run_offset"] = min(max(0, st.get("run_offset", 0)), max_run_offset)
    visible = grouped_runs[st["run_offset"]:st["run_offset"] + visible_runs]
    if visible:
        for index, (name, width) in enumerate(columns):
            offset = sum(item[1] + 1 for item in columns[:index])
            _add(scr, row, offset, history_header_label(name, st["history_sort"], st["history_desc"]),
                 colors["structure"])
        row += 1
        visible_groups = [(source, identity, running, finished) for source, identity, running, finished in groups
                          if any(run in visible for run in running + finished)]
        for source, identity, running, finished in visible_groups:
            source_visible = [run for run in visible if run in running + finished]
            group_label = f"{source_label(source)} · {run_identity_label(identity)}"
            _add(scr, row, 0, f"{group_label} (aktiv {len(running)} · Ergebnis {len(finished)})",
                 colors["structure"])
            row += 1
            for run in source_visible:
                for index, (name, width) in enumerate(columns):
                    column_x = sum(item[1] + 1 for item in columns[:index])
                    if name == "kontext":
                        draw_live_context_cell(row, column_x, width, run)
                        continue
                    value = current_run_cell(run, name)[:width].ljust(width)
                    attr = _rate_color(colors, token_rate(run)) if name == "rate" else colors["secondary"]
                    _add(scr, row, column_x, value, attr)
                row += 1
        if len(grouped_runs) > visible_runs:
            _add(scr, row, 0, f"Runs {st['run_offset'] + 1}-{min(len(grouped_runs), st['run_offset'] + visible_runs)} von {len(grouped_runs)}  ·  a/↑↓ scrollen",
                 colors["secondary"])
            row += 1
    else:
        _add(scr, row, 0, "Keine instrumentierten Requests", colors["secondary"])
        row += 1
    row += 1
    draw_history_table(row, h - row - 2, columns)

    draw_footer("q quit   r reload   x sudo   c clear   ▴▾ return   ↑↓ cursor   h help")
    if st["help"]:
        def short_source(value, limit=28):
            value = str(value or "n/a")
            return value if len(value) <= limit else value[:limit - 1] + "…"

        gpu_sources = ", ".join(
            f"GPU{i} {g.get('source') or 'n/a'}" for i, g in enumerate(st["gpus"])) or "keine"
        power_source = str(st.get("cpu_power_source") or "n/a")
        power_source = (power_source.replace("RAPL (sudo)", "RAPL sudo")
                        .replace("package-", "pkg-"))
        if power_source == "keine CPU-Powerquelle":
            power_source = "n/a"
        temp_source = short_source(st.get("cpu_temp_source"), 18)
        host_source = short_source(host.replace("http://", "").replace("https://", ""), 20)
        power_status = st.get("rapl_status")
        if power_status and power_status != "nicht aktiviert":
            power_source = f"{power_source} · {short_source(power_status, 20)}"
        bw = min(w - 2, 50)
        body_width = max(0, bw - 4)
        key_width = 13
        source_limit = max(8, body_width - key_width - 3)
        control_rows = (
            ("q/Q", "Beenden"),
            ("h/H", "Hilfe ein/aus"),
            ("r/R", "Neu laden"),
            ("x/X", "CPU-Power mit sudo"),
            ("c/C", "History löschen"),
            ("+/-", "Intervall ändern"),
            ("a/A", "Fokus Runs/History"),
            ("↑/↓", "Cursor bewegen"),
            ("Bild↑/Bild↓", "Seiten scrollen"),
            ("Pos1", "Erster Eintrag"),
            ("Ende", "Letzter Eintrag"),
            ("←/→", "Gruppe auf/zu"),
            ("Tab/Shift-Tab", "Sortierspalte"),
            ("s/S", "Sortierrichtung"),
        )
        collector_source = short_source(st.get("collector_status", "nicht aktiv"), source_limit)
        pi_source = "aktiv" if st.get("pi_adapter_active") else "nicht aktiv"
        source_rows = (
            ("CPU Power", power_source),
            ("CPU Temp", temp_source),
            ("CPU/RAM", "/proc/stat + meminfo"),
            ("GPU", short_source(gpu_sources, source_limit)),
            ("Ollama", host_source),
            ("WebUI", collector_source),
            ("Pi Adapter", pi_source),
        )
        box = [("Bedienung", colors["structure"])]
        box.extend((f"  {key:<{key_width}} {action}", colors["secondary"])
                   for key, action in control_rows)
        box.append(("Sensorquellen", colors["structure"]))
        box.extend((f"  {label:<{key_width}} {short_source(source, source_limit)}",
                    colors["secondary"]) for label, source in source_rows)
        bh = len(box) + 2
        y0 = max(1, (h - bh) // 2)
        x0 = max(0, (w - bw) // 2)
        if bw >= 8 and y0 + bh <= h - 1:
            inner_width = bw - 2
            title = " Hilfe "
            top = "╭" + title + "─" * max(0, inner_width - len(title)) + "╮"
            bottom = "╰" + "─" * inner_width + "╯"
            _add(scr, y0, x0, top[:bw], colors["structure"], indent=False)
            for j, (text, attr) in enumerate(box, 1):
                body = text[:max(0, inner_width - 2)].ljust(max(0, inner_width - 2))
                _add(scr, y0 + j, x0, "│ " + body + " │", attr, indent=False)
                _add(scr, y0 + j, x0, "│", colors["structure"], indent=False)
                _add(scr, y0 + j, x0 + bw - 1, "│", colors["structure"], indent=False)
            _add(scr, y0 + bh - 1, x0, bottom[:bw], colors["structure"], indent=False)
    scr.refresh()




def _run_tui(host, interval, use_nvidia, version, pixel_icon, pi_adapter_active=False):
    """Fuehrt curses im Hauptthread und die Erfassung im Hintergrund aus."""
    global VERSION, PIXEL_ICON
    VERSION = version
    PIXEL_ICON = pixel_icon
    collector = CollectorService()
    collector.start()
    state = {"colors": None, "help": False, "prev_cpu": read_cpu_totals(),
             "ollama": {"ok": False, "version": None, "models": [], "error": "Messung"},
             "cpu": None, "cpu_power_watt": None, "cpu_power_limit": None,
             "cpu_power_source": "keine CPU-Powerquelle",
             "rapl_reader": None, "rapl_status": "nicht aktiviert",
             "cpu_temp": None, "cpu_temp_source": None,
             "gpus": [], "gpu_err": None, "ram": (None, None, None),
             "history_ok": None, "runs": [], "run_history": [],
             "collector_status": collector.status(), "pi_adapter_active": pi_adapter_active,
             "history_sort": "zeit", "history_desc": True, "history_offset": 0,
             "history_cursor": None, "history_expanded": set(), "history_generation": 0,
             "run_offset": 0,
             "run_focus": False}
    lock = threading.Lock()
    stop = threading.Event()
    refresh = threading.Event()
    last_history_write = None

    def sample():
        nonlocal interval, last_history_write
        while not stop.is_set():
            with lock:
                history_generation = state["history_generation"]
            ollama = collect_ollama(host)
            runs = load_run_events()
            run_history = load_run_history()
            backfill_context_limits(run_history, ollama.get("models", []))
            gpus, gpu_err = collect_gpus(use_nvidia)
            with lock:
                rapl_reader = state.get("rapl_reader")
            cpu_power = collect_cpu_power(rapl_reader, gpus)
            cur = read_cpu_totals()
            with lock:
                previous = state["prev_cpu"]
            cpu = cpu_percent(previous, cur)
            ram = get_ram_pct()
            cpu_temp, cpu_temp_source = cpu_temperature()
            now = time.monotonic()
            if (last_history_write is None
                    or now - last_history_write >= HISTORY_WRITE_INTERVAL):
                history_ok = write_history(snapshot_record(
                    host, ollama, cpu, ram, gpus, gpu_err, runs[0] if runs else None,
                    cpu_power))
                last_history_write = now
            else:
                with lock:
                    history_ok = state["history_ok"]
            with lock:
                state.update({"ollama": ollama, "runs": runs,
                              "gpus": gpus, "gpu_err": gpu_err, "prev_cpu": cur,
                              "cpu": cpu, "ram": ram,
                              "cpu_power_watt": cpu_power.get("watt"),
                              "cpu_power_limit": cpu_power.get("limit"),
                              "cpu_power_source": cpu_power.get("source"),
                              "cpu_temp": cpu_temp,
                              "cpu_temp_source": cpu_temp_source, "history_ok": history_ok,
                              "collector_status": collector.status()})
                if history_generation == state["history_generation"]:
                    state["run_history"] = run_history
                delay = interval
            refresh.wait(max(0.2, delay))
            refresh.clear()

    worker = threading.Thread(target=sample, name="llmtop-sampler", daemon=True)
    worker.start()

    def activate_rapl(scr):
        """Authentifiziert sudo sichtbar und startet den begrenzten Helper."""
        with lock:
            if state.get("rapl_reader") is not None:
                state["rapl_status"] = "bereits aktiv"
                return
            state["rapl_status"] = "Authentifizierung läuft"
        sudo = shutil.which("sudo")
        suspended = False
        try:
            if os.geteuid() != 0 and not sudo:
                raise OSError("sudo nicht gefunden")
            curses.def_prog_mode()
            curses.endwin()
            suspended = True
            print("llmtop: privilegierten RAPL-Leser aktivieren (sudo -v)", flush=True)
            if os.geteuid() != 0:
                result = subprocess.run([sudo, "-v"], timeout=120)
                if result.returncode != 0:
                    raise PermissionError("sudo-Authentifizierung abgelehnt")
            script = os.path.join(os.path.dirname(__file__), "llmtop.py")
            reader = PrivilegedRaplReader.start(script)
            with lock:
                state["rapl_reader"] = reader
                state["rapl_status"] = "aktiviert, Messung folgt"
            print("llmtop: RAPL-Leser aktiviert; zurück zur TUI.", flush=True)
        except (OSError, PermissionError, subprocess.SubprocessError) as exc:
            with lock:
                state["rapl_status"] = f"Fehler: {exc}"
            log.warning("RAPL-Leser nicht aktiviert: %s", exc, exc_info=True)
            print(f"llmtop: RAPL-Leser nicht aktiviert: {exc}", file=sys.stderr, flush=True)
        finally:
            if suspended:
                try:
                    curses.reset_prog_mode()
                    scr.keypad(True)
                    scr.clear()
                    scr.refresh()
                except curses.error:
                    pass

    def confirm_clear_history(scr):
        """Verlangt eine explizite Bestätigung vor dem Löschen der History."""
        h, w = scr.getmaxyx()
        prompt = "Run-History wirklich löschen? [j/N]"
        row = max(0, h - 2)
        try:
            scr.move(row, 0)
            scr.clrtoeol()
            scr.addstr(row, 0, prompt[:max(0, w - 1)], state["colors"]["error"])
            scr.refresh()
            scr.timeout(-1)
            return scr.getch() in (ord("j"), ord("J"), ord("y"), ord("Y"))
        except curses.error:
            return False
        finally:
            scr.timeout(250)
            try:
                scr.move(row, 0)
                scr.clrtoeol()
                scr.refresh()
            except curses.error:
                pass

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
            with lock:
                state["history_offset"] = view.get("history_offset", 0)
                state["history_cursor"] = view.get("history_cursor")
                state["history_expanded"] = view.get("history_expanded", set())
            scr.timeout(250)
            key = scr.getch()
            if key == -1:
                continue
            if key in (ord("q"), ord("Q")):
                return 0
            if key in (ord("r"), ord("R")):
                return "reload"
            if key in (ord("x"), ord("X")):
                activate_rapl(scr)
                refresh.set()
                continue
            if key in (ord("c"), ord("C")):
                if confirm_clear_history(scr) and clear_run_history():
                    with lock:
                        state["run_history"] = []
                        state["history_offset"] = 0
                        state["history_cursor"] = None
                        state["history_expanded"].clear()
                        state["history_generation"] += 1
                    refresh.set()
                continue
            with lock:
                normalize_history_state(state)
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
                    state["history_cursor"] = None
                elif key == curses.KEY_BTAB:
                    index = HISTORY_COLUMNS.index(state["history_sort"])
                    state["history_sort"] = HISTORY_COLUMNS[(index - 1) % len(HISTORY_COLUMNS)]
                    state["history_offset"] = 0
                    state["history_cursor"] = None
                elif key in (ord("s"), ord("S")):
                    state["history_desc"] = not state["history_desc"]
                    state["history_offset"] = 0
                    state["history_cursor"] = None
                elif key in (10, 13, getattr(curses, "KEY_ENTER", 343), ord(" ")):
                    if not state["run_focus"]:
                        _sorted, items = normalize_history_state(state)
                        selected = next((item for item in items
                                         if item["key"] == state.get("history_cursor")), None)
                        if selected and selected["kind"] == "group":
                            group_key = selected["group"]["key"]
                            if group_key in state["history_expanded"]:
                                state["history_expanded"].discard(group_key)
                            else:
                                state["history_expanded"].add(group_key)
                elif key in (curses.KEY_LEFT, curses.KEY_RIGHT):
                    if not state["run_focus"]:
                        _sorted, items = normalize_history_state(state)
                        selected = next((item for item in items
                                         if item["key"] == state.get("history_cursor")), None)
                        if selected:
                            group_key = selected.get("group_key") or selected.get("group", {}).get("key")
                            if group_key:
                                if key == curses.KEY_LEFT:
                                    state["history_expanded"].discard(group_key)
                                    if selected["kind"] == "run" and selected.get("grouped"):
                                        state["history_cursor"] = ("group", group_key)
                                else:
                                    state["history_expanded"].add(group_key)
                elif key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_PPAGE, curses.KEY_NPAGE):
                    if state["run_focus"]:
                        delta = {curses.KEY_UP: -1, curses.KEY_DOWN: 1,
                                 curses.KEY_PPAGE: -5, curses.KEY_NPAGE: 5}[key]
                        state["run_offset"] = max(0, state["run_offset"] + delta)
                    else:
                        _sorted, items = normalize_history_state(state)
                        if items:
                            keys = [item["key"] for item in items]
                            index = keys.index(state["history_cursor"])
                            delta = {curses.KEY_UP: -1, curses.KEY_DOWN: 1,
                                     curses.KEY_PPAGE: -5, curses.KEY_NPAGE: 5}[key]
                            state["history_cursor"] = keys[max(0, min(len(keys) - 1, index + delta))]
                elif key in (curses.KEY_HOME, curses.KEY_END):
                    if state["run_focus"]:
                        target = "run_offset"
                        if key == curses.KEY_HOME:
                            state[target] = 0
                        else:
                            state[target] = max(0, len(state["runs"]) - 1)
                    else:
                        _sorted, items = normalize_history_state(state)
                        if items:
                            state["history_cursor"] = items[0 if key == curses.KEY_HOME else -1]["key"]
        return 0

    try:
        result = curses.wrapper(session)
    finally:
        stop.set()
        refresh.set()
        worker.join(timeout=0.2)
        with lock:
            rapl_reader = state.get("rapl_reader")
        if rapl_reader is not None:
            rapl_reader.stop()
        collector.stop()
    if result == "reload":
        os.execv(sys.executable, [sys.executable, *sys.argv])
    return result
