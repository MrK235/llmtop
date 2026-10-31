# otop — Ollama-Terminal-Monitor (Kurzplan)

## Ziel
Eine einzelne Python-Datei (`otop.py`), reine Standardbibliothek, startet eine
Terminal-Anwendung (TUI), die zeigt:
1. das aktuell in Ollama **geladene Modell** (über die Ollama-API),
2. **CPU-Auslastung**,
3. **GPU-Auslastung**.

Weitere Dateien: nur `README.md` und `status.md`. Keine weiteren Dateien.

## Live-Umgebung (verifiziert)
- Ollama läuft lokal im Docker-Container: `http://localhost:11434` → `Ollama is running`, Version **0.40.6**.
- `/api/ps` → aktuell geladen: `qwen3.5:4b`, `size=3.9 GB`, `size_vram=341 MB`, `ctx=32768`, `runner=llamacpp`, `expires_at` (Auto-Unload).
- `/api/tags` → Modellliste (u. a. `qwen3.6:35b-a3b`).
- GPU: NVIDIA **RTX 5070 Laptop** (`/proc/driver/nvidia`, `nvidia-smi` vorhanden) + AMD iGPU (`/sys/class/drm/card2/device/gpu_busy_percent` → 2 %).
- CPU: `/proc/stat` (25 CPU-Zeilen, `nproc` = 24), `/proc/loadavg`, `/proc/meminfo`.
- Python 3.12, `curses` vorhanden.

## Datenquellen (nur Stdlib)
- **Ollama**: `urllib.request` + `json` → `/api/version` (Erreichbarkeit), `/api/ps`
  (geladene Modelle), `/api/tags` (verfügbar). Timeout 2 s, saubere Fehleranzeige.
  GPU-Anteil des Modells: `size_vram / size` → „x % auf GPU / y % auf CPU“.
- **CPU**: Differenz zweier `/proc/stat`-Reads pro Refresh → Gesamt-% (Kernel-Zeilen: user, nice, system, idle, iowait, irq, softirq, steal).
- **GPU**: Kette von Quellen, erste gewinnt:
  1. `nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total` via `subprocess`
     (Nvidia: keine sysfs-Auslastungsdatei vorhanden),
  2. `/sys/class/drm/card*/device/gpu_busy_percent` (AMD iGPU funktioniert hier),
  3. sonst „n/a“ — App läuft trotzdem weiter.
- Ollama-API selbst liefert **keine** CPU-/GPU-Auslastung (nur `size_vram`). /metrics ist 404.

## TUI (curses, Stdlib)
Aktualisierung alle 2 s, nicht-blockierender Input, Resize-Handling:
```
 otop · Ollama 0.40.6 · http://localhost:11434 · verbunden · Last: 1.8
 Geladene Modelle (/api/ps)
   qwen3.5:4b   4.2B Q4_K_M   ctx 32768   unload in 3:12   runner llamacpp
   Speicher: 341 MB VRAM / 3.9 GB gesamt  → 9 % GPU, 91 % CPU
 CPU [#####-----]  12 %  (24 Kerne)
 GPU0 RTX 5070    [#-------] 100 %   VRAM 7284 / 8151 MiB
 GPU1 AMD iGPU    [--------]   2 %
 Tasten: q quit · r refresh jetzt · h Hilfe   (Intervall: - / +)
```
Keine weiteren Funktionen (kein Modell-Laden/-entladen, kein Ranking, kein Logging in Dateien).

## CLI (argparse, Stdlib)
`--host` (Default `http://localhost:11434`), `--interval` (Default 2 s),
`--once` (ein Einzel-Snapshot für Skripte/Nicht-TTY; hilft beim Testen),
`--no-nvidia` (Nvidia-Abfrage überspringen). Nur diese Optionen.

## Dateien
- `otop.py` — komplette Anwendung (ca. 250–300 Zeilen).
- `README.md` — Start, Optionen, Datenquellen, Tasten, bekannte Grenzen (GPU-Auslastung = Geräte-global, nicht ollama-exklusiv; Container-GPU-Metrik nur via Host).
- `status.md` — Verlaufsprotokoll: Schritte, Testergebnisse, offene Punkte.

## Testvorgehen
1. `python3 otop.py --once` → prüft API-Daten und Systemwerte gegen live Ollama.
2. Direct-Module-Test: CPU-Diff, GPU-Quellen (nvidia-smi + sysfs) einzeln aufrufen.
3. TUI-Rendering in einer Pseudo-TTY testen (`pty`/`script -q -c`), 2–3 Frames einfangen,
   auf Ausnahmen prüfen (curses, Resize, Verbindungsabbruch).
4. Visuelle Kontrolle im echten Terminal machst du — ich melde das Ergebnis und stoppe bei Fehlern.

## Offene Punkte (bitte kurz beantworten)
1. **GPU-Auslastung**: Ollama-API liefert sie nicht. Lösungsweg: `nvidia-smi` per `subprocess`
   (Stdlib, keine Fremd-Bibliothek, existiert auf dem Host). Ok für dich? (Alternative: nur AMD-sysfs
   → für die RTX wäre die Anzeige leer.)
2. **Host-RAM-Anzeige** gewünscht? Nicht gefordert → lasse ich standardmäßig weg (VRAM-Anzeige kommt aus Ollama/`nvidia-smi`).
3. TUI-Bibliothek: **curses** (Stdlib) ok, oder lieber Plain-ANSI ohne Vollbild?

## Reihenfolge der Umsetzung
1. `otop.py` mit Datenerfassung + `--once`.
2. Live-Test `--once`, Fehler beheben.
3. TUI-Teil, Test in Pseudo-TTY.
4. `README.md` + `status.md` schreiben und Status eintragen.
5. Kurze Zusammenfassung; bei Fehlern/Fragen: stoppen und warten.
