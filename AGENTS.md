# AGENTS.md — otop

## Das Projekt

`otop` ist eine **Single-File-Python-Terminalanwendung** (nur `otop.py`) die über die Ollama-API den Status des geladenen Modells anzeigt sowie CPU-, RAM-, GPU- und VRAM-Sensoren in einer curses-basierten TUI darstellt. Sie ist als `--once`-Snapshotmodi, lokaler Collector-Modus und Open-WebUI-Adapter-Erweiterung ergänzt.

**Leitprinzip:** Einfachheit durch Standardbibliothek allein — kein pip, keine System-Packages, keine Konfigurationsdateien neben `.env`. Ausgeführt auf jedem Linux out of the box.

## 1. Grundsätze

### Ausrichtung und Ziele
- **Einzelne Datei:** `otop.py` ist die alleinige Quellcodedatei im Projektstamm (außer `README.md`, `status.md`, `version.md`, `.env.example`, `open_webui/`).
- **Nur Standardbibliothek:** Keine Pip-Abhängigkeiten, keine System-Packages. Alle Sensoren kommen von `/proc`, sysfs oder den lokalen Binaries `nvidia-smi`.
- **Out-of-the-box auf Linux:** Das Projekt läuft ohne Vorinstallation oder Konfiguration außer optionaler `.env` für Collector und Open-WebUI-Adapter. Es muss keine Installation oder Initialisierung stattfinden.
- **Fehler-tolerant:** Sensoren greifen kettenbasierte Fallbacks (nvidia-smi → sysfs) zurück; fehlende Hardware wird als `n/a` angezeigt statt zu crashen.

### Architektur-Entscheidungen
- Alle Sensorabfragen, Ollama-API-Kommunikation und Terminal-Rendering erfolgen in `otop.py`.
- Das `open_webui/`-Verzeichnis enthält nur den Open-WebUI-Filteradapter (`otop_run_metrics.py`) als zusätzliche Verteilungsschicht.
- Sensoren greifen auf Systemressourcen zurück: `/proc/stat` (CPU), `/proc/meminfo` (RAM), sysfs oder `nvidia-smi` (GPU/VRAM), `/proc/loadavg` (Load).
- Collector und History nutzen getrennte, begrenzte JSONL-Dateien unter `$XDG_STATE_HOME/otop/`.

## 2. Arbeitsweise mit diesem Projekt

### Änderungen an `otop.py`
- Immer die **einige** Code-Datenquelle; keine Datei-Zersplitterung ohne ausdrücklichen Auftrag.
- Alle neuen Sensoren und Funktionen müssen die Standardbibliothek einhalten. Kein `subprocess` für neue externe Tools außer wo bereits etabliert (`nvidia-smi`).
- Bestehende CLI-Optionen, Tastatürkürzel und Exit-Codes nur erweitern, nicht umbenennen oder löschen.
- Farbschema (Cyan Struktur, Grün/Gelb/Rot Status) und Balkengeometrie konsistent halten.

### Neue Features — Richtlinien
- Jede neue Option muss dokumentiert werden (`README.md`, `--version`-Hilfe).
- Neue Sensoren brauchen eine Fallback-Kette mit mindestens sysfs-Absicherung.
- History- und Collector-Erweiterungen müssen datensparsam bleiben (keine Prompts, keine vollständigen Modellantworten).
- Mindest-Terminalgröße 40×18 nie unterschreiten.

### Validierung vor jeder Änderung
1. Vor Arbeitsbeginn `git status --short`, aktuellen Branch und vorhandene Tags prüfen.
2. Bestehende, nicht zur Aufgabe gehörende Änderungen weder überschreiben noch zurücksetzen.
3. `python3 -m py_compile otop.py` → keine Syntaxfehler.
4. `python3 otop.py --once` und `--once --no-nvidia` → fehlerfrei auf beiden Pfaden.
5. `otop.py --version` zeigt die korrekte Versionsnummer mit Exit 0.

### Dokumentation
- Bei jeder funktionalen Änderung: `VERSION` (in `otop.py`), `README.md`, `status.md` und `version.md` synchronisieren.
- Neue Sensoren in `README.md → Angezeigte Werte` dokumentieren.
- Bekannte Grenzen in `status.md` dokumentieren, nicht Code als Workaround verbergen.

## 3. Was NICHT geändert wird (ohne expliziten Auftrag)

- Keine neuen Dateien unter `/` außer der Python-Datei und den vier Versionsdokumenten.
- Keine pip-Installationen oder neue System-Packages.
- Keine Konverter, keine Umstellung auf andere Ausgabeformate neben TUI und `--once`.
- Keine Änderungen an der sourceset-Kette (nvidia-smi → sysfs), bestehenden Exit-Codes, Tastaturbefehlen oder Refresh-Grenzen (0.5–60 s).
- Keine destruktiven Git-Befehle wie `reset --hard`, `clean`, erzwungenes Checkout oder Rebase ohne ausdrücklichen Auftrag.
- Commits, Tags, Branchwechsel und Releases nur nach ausdrücklicher Freigabe; lesende Git-Befehle und `git diff` gehören zum normalen Arbeitsablauf.

## 4. Testing

### Minimaltests (im Scratch-Verzeichnis)
Tests laufen ausschließlich im temp-Verzeichnis: `python` aus `/tmp/pi/...`. Mock-Ollama-Ergebnisse über Pipes. Keine neuen Testdateien im Projektverzeichnis.

### Bekannte Randfälle — nicht ändern, nur kennen
- CPU-Balken zeigt beim ersten Frame „Messung".
- Der API-Aufruf an Ollama blockiert die GUI kurzzeitig wenn das Netzwerk langsam ist (bekannt).
- Viele geladene Modelle schieben Teile der TUI aus dem Terminalfenster.
- `--once` ohne funktionierende Ollama-Verbindung zeigt Sensorwerte, aber keinen Modellstatus.

## 5. Collector und History

### Collector
- Token-geschützter lokaler HTTP-Server. Default `127.0.0.1:11435`.
- Empfängt Schema-2-Events über `POST /v1/runs`; speichert begrenzte, datensparsame Runs in JSONL.
- Schlägt der Collector fehl, bricht die Anwendung nicht ab — Sensoren und TUI funktionieren unverändert weiter.

### History
- Path: `$XDG_STATE_HOME/otop/history.jsonl` (fallback `~/.local/state/otop/history.jsonl`).
- Begrenzte JSONL-Snapshots mit UTC-Zeitstempeln; atomisches Schreiben.
- Alte Zeilen werden beim Überschreiten der Maximalgröße automatisch abgeschnitten.

## 6. Versions- und Git-Management

- Git ist die verbindliche Grundlage für nachvollziehbare Projektstände und Vergleiche zwischen Versionen.
- Vor Änderungen den Ausgangsstand mit `git status --short`, `git branch --show-current` und passenden Tags prüfen.
- Nach Änderungen `git diff --check`, einen gezielten `git diff` und die vorgeschriebenen Tests ausführen.
- Semantische Versionierung (`MAJOR.MINOR.PATCH`) in `otop.py`, `version.md` und `README.md` synchronisieren.
- Veröffentlichte Versionen sollen nach ausdrücklicher Freigabe als Commit gesichert und mit `vX.Y.Z` getaggt werden.
- Arbeitsstände nicht eigenmächtig committen oder taggen. Ohne Freigabe nur Änderungen und Prüfresultate zusammenfassen.
- `PATCH`: Fehlerkorrekturen ohne neue Bedienfunktion.
- `MINOR`: Neue abwärtskompatible Anzeige- oder CLI-Funktion.
- `MAJOR`: Inkompatible Änderungen an Schnittstelle oder Layout (selten).

---

**Zusammenfassung in drei Zeilen:**
Single File, nur Standardbibliothek, läuft ohne Setup auf jedem aktuellen Linux. Keine Pip-, keine Systempaketinstallationen, keine Konfiguration außer optionaler `.env`. Alle Sensoren mit sysfs-Fallback.
