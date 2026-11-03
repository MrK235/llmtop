# AGENTS.md — llmtop

## Das Projekt

`llmtop` ist eine kleine Python-Terminalanwendung mit `llmtop.py` als Einstieg sowie drei Kernmodulen für Quellen, Metriken und curses-TUI. Sie zeigt über die Ollama-API den Status des geladenen Modells sowie CPU-, RAM-, GPU- und VRAM-Sensoren und bietet `--once`, lokalen Collector und Open-WebUI-Adapter.

**Leitprinzip:** Einfachheit durch Standardbibliothek allein — kein pip, keine System-Packages, keine Konfigurationsdateien neben `.env`. Ausgeführt auf jedem Linux out of the box.

## 1. Grundsätze

### Ausrichtung und Ziele
- **Kleine Kernmodule:** `llmtop.py`, `llmtop_sources.py`, `llmtop_metrics.py` und `llmtop_tui.py` sind die Quellcodedateien im Projektstamm. Keine weitere Aufspaltung ohne konkreten Bedarf.
- **Nur Standardbibliothek:** Keine Pip-Abhängigkeiten, keine System-Packages. Alle Sensoren kommen von `/proc`, sysfs oder den lokalen Binaries `nvidia-smi`.
- **Out-of-the-box auf Linux:** Das Projekt läuft ohne Vorinstallation oder Konfiguration außer optionaler `.env` für Collector und Open-WebUI-Adapter. Es muss keine Installation oder Initialisierung stattfinden.
- **Fehler-tolerant:** Sensoren greifen kettenbasierte Fallbacks (nvidia-smi → sysfs) zurück; fehlende Hardware wird als `n/a` angezeigt statt zu crashen.

### Architektur-Entscheidungen
- `llmtop_sources.py` enthält Sensoren und Ollama-Zugriffe, `llmtop_metrics.py` Run-Schema, History und Collector, `llmtop_tui.py` ausschließlich curses-Rendering und Sampler; `llmtop.py` bleibt CLI-Einstieg.
- Das `open_webui/`-Verzeichnis enthält nur den Open-WebUI-Filteradapter (`llmtop_run_metrics.py`) als zusätzliche Verteilungsschicht; ein späterer Pi-Adapter nutzt dasselbe Schema 2 über den Collector.
- Sensoren greifen auf Systemressourcen zurück: `/proc/stat` (CPU), `/proc/meminfo` (RAM), sysfs oder `nvidia-smi` (GPU/VRAM), `/proc/loadavg` (Load).
- Collector und History nutzen getrennte, begrenzte JSONL-Dateien unter `$XDG_STATE_HOME/llmtop/`.

## 2. Arbeitsweise mit diesem Projekt

### Änderungen an den Kernmodulen
- Fachgrenzen beibehalten: Quellen in `llmtop_sources.py`, Runmetriken und Collector in `llmtop_metrics.py`, curses in `llmtop_tui.py`, CLI in `llmtop.py`.
- Alle neuen Sensoren und Funktionen müssen die Standardbibliothek einhalten. Kein `subprocess` für neue externe Tools außer wo bereits etabliert (`nvidia-smi`).
- Bestehende CLI-Optionen, Tastatürkürzel und Exit-Codes nur erweitern, nicht umbenennen oder löschen.
- Farbschema (Cyan Struktur, abgestufte Auslastungsfarben, Grün/Gelb/Rot für Temperatur und Status) und Balkengeometrie konsistent halten.

### Neue Features — Richtlinien
- Jede neue Option muss dokumentiert werden (`README.md`, `--version`-Hilfe).
- Neue Sensoren brauchen eine Fallback-Kette mit mindestens sysfs-Absicherung.
- History- und Collector-Erweiterungen müssen datensparsam bleiben (keine Prompts, keine vollständigen Modellantworten).
- Mindest-Terminalgröße 40×18 nie unterschreiten.

### Validierung vor jeder Änderung
1. Vor Arbeitsbeginn `git status --short`, aktuellen Branch und vorhandene Tags prüfen.
2. Bestehende, nicht zur Aufgabe gehörende Änderungen weder überschreiben noch zurücksetzen.
3. `python3 -m py_compile llmtop.py` → keine Syntaxfehler.
4. `python3 llmtop.py --once` und `--once --no-nvidia` → fehlerfrei auf beiden Pfaden.
5. `llmtop.py --version` zeigt die korrekte Versionsnummer mit Exit 0.

### Dokumentation
- Bei jeder funktionalen Änderung: `VERSION` (in `llmtop.py`), `README.md`, `status.md` und `version.md` synchronisieren.
- Neue Sensoren in `README.md → Angezeigte Werte` dokumentieren.
- Bekannte Grenzen in `status.md` dokumentieren, nicht Code als Workaround verbergen.

## 3. Was NICHT geändert wird (ohne expliziten Auftrag)

- Keine neuen Dateien unter `/` außer der Python-Datei und den vier Versionsdokumenten.
- Keine pip-Installationen oder neue System-Packages.
- Keine Konverter, keine Umstellung auf andere Ausgabeformate neben TUI und `--once`.
- Keine Änderungen an der sourceset-Kette (nvidia-smi → sysfs), bestehenden Exit-Codes, Tastaturbefehlen oder Refresh-Grenzen (0.2–60 s).
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
- Path: `$XDG_STATE_HOME/llmtop/history.jsonl` (fallback `~/.local/state/llmtop/history.jsonl`).
- Begrenzte JSONL-Snapshots mit UTC-Zeitstempeln; atomisches Schreiben.
- Alte Zeilen werden beim Überschreiten der Maximalgröße automatisch abgeschnitten.

## 6. Versions- und Git-Management

### GitHub-Nutzung
- Das private GitHub-Repository ist `git@github.com:MrK235/llmtop.git`.
- Der Standard-Remote heißt `origin`; der Hauptbranch ist `master`.
- Der Zugriff erfolgt global über SSH, bevorzugt mit `~/.ssh/github_llmtop_ed25519` und einem entsprechenden `Host github.com`-Eintrag in `~/.ssh/config`.
- Zugangsdaten, private Schlüssel und Tokens niemals ins Repository übernehmen. GitHub-Zugriff mit `ssh -T git@github.com` prüfen.
- Änderungen werden erst nach Prüfung committed und anschließend mit `git push` zu `origin/master` übertragen.
- `backup/` bleibt ein lokaler Arbeitsordner und wird über `.gitignore` ausgeschlossen. `plan/` wird dagegen versioniert und nach Änderungen mit committed.

- Git ist die verbindliche Grundlage für nachvollziehbare Projektstände und Vergleiche zwischen Versionen.
- Vor Änderungen den Ausgangsstand mit `git status --short`, `git branch --show-current` und passenden Tags prüfen.
- Nach Änderungen `git diff --check`, einen gezielten `git diff` und die vorgeschriebenen Tests ausführen.
- Semantische Versionierung (`MAJOR.MINOR.PATCH`) in `llmtop.py`, `version.md` und `README.md` synchronisieren.
- Standardmäßig nur den Patchstand erhöhen, auch bei kleinen Anzeige- oder Bedienverbesserungen. Einen Minor- oder Major-Sprung nur auf ausdrücklichen Benutzerwunsch verwenden.
- Jeder vollständig implementierte und erfolgreich geprüfte Versionsstand mit erhöhter `VERSION` wird zum Abschluss der Aufgabe als Git-Commit gesichert; dafür ist keine zusätzliche Freigabe erforderlich.
- Tags und Releases (`vX.Y.Z`) weiterhin nur nach ausdrücklicher Freigabe erstellen.
- Unfertige Arbeitsstände oder Änderungen ohne Versionsanhebung nicht eigenmächtig committen; ohne Freigabe nur Änderungen und Prüfresultate zusammenfassen.
- `PATCH`: Standard für normale Fehlerkorrekturen und kleine Erweiterungen.
- `MINOR`: nur auf ausdrücklichen Wunsch für einen größeren, abwärtskompatiblen Funktionsstand.
- `MAJOR`: nur auf ausdrücklichen Wunsch für inkompatible Änderungen.

---

**Zusammenfassung in drei Zeilen:**
Vier kleine Kernmodule, nur Standardbibliothek, läuft ohne Setup auf jedem aktuellen Linux. Keine Pip-, keine Systempaketinstallationen, keine Konfiguration außer optionaler `.env`. Alle Sensoren mit sysfs-Fallback.
