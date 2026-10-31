# Versionsgeschichte — otop

## Schema

`VERSION = "X.Y.Z"` in `otop.py` ist die maßgebliche Versionsquelle. Bei einem
Release werden diese Datei, `README.md` und `status.md` auf denselben Stand
gebracht.

- **Patch** (`X.Y.Z+1`): Fehlerkorrekturen ohne neue Bedienfunktion.
- **Minor** (`X.Y+1.0`): neue, abwärtskompatible Anzeige- oder CLI-Funktion.
- **Major**: inkompatible Bedien- oder Schnittstellenänderung.

## Changelog

### 1.8.4 — 31.10.2026

- Unterstreichung der aktiven Sortierspalte auf die Textlänge begrenzt.
- Leere Zeile zwischen History-Tabelle und Statusleiste ergänzt; kompakte
  40×18-Ansicht dafür ohne Informationsverlust verdichtet.

### 1.8.3 — 31.10.2026

- Kontextzelle auf Prozentwert vor Verbrauch/Limit umgestellt.
- Redundante Sortieranzeige aus der History-Überschrift entfernt; aktiver
  Spaltenkopf wird unterstrichen und behält den Richtungspfeil.

### 1.8.2 — 31.10.2026

- Kontextsortierung verwendet den tatsächlichen prozentualen Verbrauch statt
  der absoluten Tokengröße; fehlende Limits folgen zuletzt.
- Aktive Sortierspalte im Tabellenkopf mit `▾` beziehungsweise `▴` markiert.

### 1.8.1 — 31.10.2026

- TUI-Abbruch auf Python-curses-Varianten ohne `KEY_TAB` behoben. Die
  portable Tab-Taste (Code `9`) steuert die History-Sortierspalte.

### 1.8.0 — 31.10.2026

- Run-History als scrollbare, sortierbare TUI-Tabelle für bis zu 100 finale
  Einträge ergänzt.
- Sortierung nach Abschlusszeit, Quelle, Modell, Status, Tokens,
  Kontextverbrauch, Ausgabe-Rate und Dauer; fehlende Werte folgen zuletzt.
- Kontextspalte zeigt Verbrauch, Limit und Prozentwert. JSONL bleibt für diese
  begrenzte Datenmenge die Datenquelle; keine Datenbank erforderlich.

### 1.7.4 — 31.10.2026

- Wiederholte Open-WebUI-`request`-Filteraufrufe mit derselben Nachrichten-
  Identität werden als ein aktiver Run behandelt.
- Tool- und Fortsetzungsrunden erzeugen dadurch keine zusätzlichen Einträge
  unter „Aktuelle Runs“; echte parallele Nachrichten bleiben getrennt.

### 1.7.3 — 31.10.2026

- Verwaiste Live-Runs werden nach 90 Sekunden ohne Lebenszeichen aus
  `run.jsonl` entfernt und nicht angezeigt.
- Lange Open-WebUI-Streams senden regelmäßig Lebenszeichen, auch wenn der
  Provider noch keine Tokenwerte liefert.
- Parallele JSONL-Updates im Collector werden synchronisiert.
- Run-Zuordnung des Open-WebUI-Adapters spekuliert bei widersprüchlichen
  Identitäten nicht mehr auf einen anderen parallelen Run.

### 1.7.2 — 31.10.2026

- Run-History zeigt bis zu zehn abgeschlossene Runs in `--once` und TUI.
- History-Zeilen werden im großen TUI-Layout reserviert, damit Modellkarten
  und Fußzeile nicht überzeichnet werden.
- Open-WebUI-Adapter beendet Runs nicht mehr fälschlich beim normalen
  Request-/Stream-Lebenszyklus als `cancelled`; echte Abbrüche bleiben möglich.

### 1.7.1 — 31.10.2026

- TUI bei 40×18 auf eine kompakte, überlappungsfreie Darstellung umgestellt;
  unvollständige Modellkarten werden nicht mehr von History-Zeilen überschrieben.
- Kopfzeile bei schmalen Terminalbreiten gezielt verdichtet statt mit der
  Intervallanzeige zu kollidieren.
- `--once` ordnet RAM direkt bei CPU ein und gibt danach GPU, Ollama und
  History aus.
- README und Status auf die maßgebliche Version 1.7.1 synchronisiert.

### 1.7.0 — 31.10.2026

- Kontextverbrauch instrumentierter Runs aus Prompt- und Ausgabetoken als Balken dargestellt.
- Kontextlimit aus Run-Request (`options.num_ctx`) und optionalen Schema-2-Feldern historisiert.
- Fehlende Limits werden bei passendem Modell aus Ollamas `/api/ps` (`context_length`) ergänzt und in der Run-History nachgetragen.
- Kontextmetrik bleibt datensparsam und verwendet keine Prompt- oder Antwortinhalte.

### 1.6.1 — 31.10.2026

- Open-WebUI-Adapterinstallation über die Admin-API ergänzt.
- API-Valves korrekt als direkter Request-Body übertragen; bestehende Aktivierungs-
  und Globalzustände bleiben bei Updates erhalten.
- Alte Einzelrun- und Kontextanzeige-Hilfen entfernt; Filter instrumentiert nur
  noch eindeutig als Ollama erkannte Provider.

### 1.6.0 — 31.10.2026

- Open-WebUI-Filteradapter für datensparsame Ollama-Runmetriken ergänzt.
- Collector-Bind-Adresse und Port für private Docker-Netze konfigurierbar gemacht;
  sicherer Loopback-Default bleibt erhalten.
- Token-geschützten lokalen Collector für Schema-2-Runereignisse ergänzt.
- Mehrere parallele aktive Runs, Quellenlabels und Deduplizierung nach Quelle
  und Run-ID ergänzt; Schema-1-Einträge bleiben als `legacy` lesbar.
- Generischen Testsender `--emit` und lokale `.env`-Konfiguration ergänzt.

### 1.5.0 — 31.10.2026

- Direkten opt-in-Clientmodus `--chat` und `--generate` ergänzt; er ruft
  Ollama ohne Reverse Proxy auf und zeichnet ausschließlich eigene Runs auf.
- Finale Ollama-Metriken werden aus dem `done`-Objekt übernommen, von
  Nanosekunden in Sekunden umgerechnet und als begrenzte, deduplizierte
  `runs.jsonl` gespeichert.
- History zeigt die letzten abgeschlossenen instrumentierten Runs; System-
  Snapshots bleiben getrennt erhalten.

### 1.4.1 — 31.10.2026

- Ollama-Bereich in „Aktueller Run“ und „Geladene Modelle“ geteilt.
- Optionalen JSONL-Run-Eingang über `OTOP_RUN_FILE` ergänzt.
- Kontextbalken, Prompt-/Ausgabe-/Gesamttoken und Ausgabe-Rate ergänzt.
- Nicht instrumentierte oder veraltete Runs werden eindeutig angezeigt.

### 1.4.0 — 31.10.2026

- Lokale, begrenzte JSONL-History mit UTC-Zeitstempeln, atomischem Schreiben
  und tolerierter Beschädigung einzelner Zeilen ergänzt.
- Snapshot-Schema für Ollama-, System-, GPU- und Fehlerdaten eingeführt.
- History-Pfad über `OTOP_HISTORY_FILE` beziehungsweise `XDG_STATE_HOME`
  konfigurierbar; Standardpfad ist `~/.local/state/otop/history.jsonl`.

### 1.3.5 — 31.10.2026

- Hostwerte aus `OLLAMA_HOST` und `--host` werden zuverlässig normalisiert.
- JSON-Antworten und `/api/ps`-Modelllisten werden validiert.
- CSV-Ausgaben von `nvidia-smi` werden robust geparst; Prozentwerte und
  Modell-Offload bleiben innerhalb sinnvoller Grenzen.

### 1.3.4 — 31.10.2026

- Ollama-Speicherfarben bewerten den Offload-Grad der GPU/VRAM-Anzeige: Grün
  oberhalb 55 %, Gelb bei 45–55 % und Rot unterhalb 45 % GPU-Anteil.
- CPU/RAM bleibt gedimmt grau; Rahmen und Label des Speicherbalkens bleiben
  Cyan, fehlende Größen gedimmt als `GPU/CPU n/a`.

### 1.3.3 — 31.10.2026

- Globale Farbrollen für Struktur, Status, GPU-/CPU-Speicher, Sekundärtext
  und Fehler eingeführt.
- Ollama-Speicherbalken an Sensorgeometrie angepasst; GPU und CPU sind mit
  durchgehenden, unterschiedlich gefärbten `#`-Segmenten dargestellt.

### 1.3.2 — 31.10.2026

- Modellname, „Speicher“, Balkenklammern und GPU-Anteil im Ollama-Bereich
  konsequent Cyan dargestellt.
- `r` / `R` startet das Programm nach sauberem curses-Cleanup mit denselben
  Kommandozeilenoptionen neu.

### 1.3.0 — 31.10.2026

- CPU- und GPU-Temperatursensoren ergänzt, inklusive farbiger Textanzeige und
  sysfs-/NVIDIA-Quellen.
- Ollama-Modelle mit hervorgehobenem Namen, gedimmten Metadaten und geteiltem
  GPU-/CPU-Speicherbalken dargestellt.
- Mindesthöhe auf 40×20 angepasst, um zusätzliche Temperaturzeilen zu sichern.

### 1.2.3 — 31.10.2026

- GPU-Power-Balken auf mindestens 115 W Boost-Skala vereinheitlicht; höhere
  gemeldete Grenzen bleiben maßgeblich.
- Leerzeilen zwischen System, GPU, Ollama und History ergänzt; Mindesthöhe auf
  40×18 angepasst.
- CPU-Power nicht ergänzt: Auf dem Zielhost existiert keine zugängliche,
  verlässliche Datenquelle.

### 1.2.2 — 31.10.2026

- GPU-Poweranzeige verwendet bei NVIDIA die effektive Leistungsgrenze als
  Fallback und liest im sysfs-Pfad eine vorhandene Power-Cap.
- Ohne Leistungsgrenze wird die tatsächliche Leistung in Watt als primärer
  Sensorwert statt als gedimmtes Detail hinter `n/a` angezeigt.

### 1.2.1 — 31.10.2026

- Mindesthöhe der Vierbereiche-TUI von 8 auf 14 Zeilen angehoben, damit die
  feste Fußzeile keine Bereichsinhalte überdeckt.

### 1.2.0 — 31.10.2026

- TUI als vierteilige, htop/glances-orientierte Ansicht strukturiert:
  System, GPU, Ollama und History.
- Sensorzeilen für CPU, RAM, GPU, VRAM und Power mit einheitlicher
  Balkenbreite, ausgerichteten Werten und Ampelfarben versehen.
- History als visuellen, gedimmten Platzhalter vorbereitet; keine Speicherung
  oder neue Bedienfunktion.

### 1.1.0 — 31.10.2026

- GPU-Erfassung stabilisiert: Rückgabecode von `nvidia-smi`, sysfs-Fallback,
  mehrere NVIDIA-Geräte und `--no-nvidia` funktionieren konsistent.
- VRAM-Werte auf MiB vereinheitlicht; VRAM- und Power-Anzeige in TUI sowie
  Einzel-Snapshot ergänzt.
- TUI gegen nicht-numerische GPU-Auslastung abgesichert, CPU-Intervallmessung
  korrigiert und Hilfe-Text sichtbar gemacht.
- Fehler von `/api/ps` eindeutig angezeigt.
- README, Status und Code-Docstring bereinigt.

### 1.0.0 — Ausgangsversion

- Ollama-Modellstatus, CPU-, RAM- und GPU-Anzeige in einer curses-TUI.
- Optionen `--host`, `--interval`, `--once`, `--no-nvidia` und `--version`.

## Release-Checkliste

1. `python3 -m py_compile otop.py` ausführen.
2. `python3 otop.py --version`, `--once` und `--once --no-nvidia` prüfen.
3. TUI in einem echten Terminal sowie Fehlerfälle mit Mock-Ollama prüfen.
4. Dokumentation und `VERSION` abgleichen.
