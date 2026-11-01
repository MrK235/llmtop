# Versionsgeschichte — llmtop

## Schema

`VERSION = "X.Y.Z"` in `llmtop.py` ist die maßgebliche Versionsquelle. Bei einem
Release werden diese Datei, `README.md` und `status.md` auf denselben Stand
gebracht.

- **Patch** (`X.Y.Z+1`): Fehlerkorrekturen ohne neue Bedienfunktion.
- **Minor** (`X.Y+1.0`): neue, abwärtskompatible Anzeige- oder CLI-Funktion.
- **Major**: inkompatible Bedien- oder Schnittstellenänderung.

## Changelog

### 2.1.12 — 01.11.2026

- Tok/s und Laufalter in Run-Zeilen rechtsbündig und kollisionsfrei dargestellt.
- `0,0 Tok/s` neutral grau dargestellt.

### 2.1.11 — 01.11.2026

- Kontextverbrauch aktiver Runs in der kompakten TUI-Ansicht sichtbar gemacht.

### 2.1.10 — 01.11.2026

- Pi-Session-Kontext über `sessionManager` gelesen und während aktiver Runs regelmäßig aktualisiert.

### 2.1.9 — 01.11.2026

- Bekannte Pi-Provider-Usage während aktiver Streams höchstens einmal pro Sekunde an den Collector übertragen.
- Kontext und Tok/s bereits vor `agent_settled` aktualisiert.

### 2.1.8 — 01.11.2026

- Bereits gespeicherte Doppelmeldungen mit identischen Open-WebUI-Metriken in der History dedupliziert.

### 2.1.7 — 01.11.2026

- Veraltete globale `otop_run_metrics`-Adapter beim Open-WebUI-Setup deaktiviert, um doppelte Runs zu verhindern.

### 2.1.6 — 01.11.2026

- Pi-Adapter überträgt Cache-Input, Kontextlimit, Gesamtdauer und Ausgaberate.
- Ollama-Pi-Runs zeigen Tok/s und Dauer; ChatGPT-Pi-Runs Kontextgröße, Prozent und Tok/s.

### 2.1.5 — 01.11.2026

- Pi-Modell- und Tool-Folgeturns je bearbeiteter Anfrage zu einem Live-Run zusammengefasst.
- Run-History schreibt nur den finalen `agent_settled`-Abschluss der sichtbaren Antwort.

### 2.1.4 — 01.11.2026

- Finale Pi- und Open-WebUI-Live-Runs nach zehn Sekunden atomar aus `run.jsonl` entfernen, bei unveränderter begrenzter Run-History.
- Aktive Runs und frische Ergebnisse quellenneutral in gleichartigen Pi-/Open-WebUI-Blöcken darstellen.

### 2.1.3 — 01.11.2026

- Letzte Pi- und WebUI-Abschlüsse auch neben neuen aktiven Runs behalten und Pi in der Live-Anzeige priorisieren.

### 2.1.2 — 01.11.2026

- Quellenseparate Pi- und Open-WebUI-Collector-Pfade sowie letzte Live-Abschlüsse je Quelle ergänzt.
- Quelle in Kompaktansicht und schmaler History priorisiert; alte aktive Open-WebUI-Filter werden automatisch aktualisiert.

### 2.1.1 — 01.11.2026

- Pi-Adapter beim normalen TUI-Start automatisch global aktualisieren und private Collector-Laufzeitdaten bereitstellen.

### 2.1.0 — 01.11.2026

- Optionalen globalen Pi-Adapter für lokale und Cloud-Provider ergänzt.
- Quelle und Provider in Live-Runs, `--once` und History ergänzt; aktuelle Runs sind nicht mehr auf drei Einträge begrenzt und separat scrollbar.
- Open-WebUI-Adapter auf providerneutrale Erfassung erweitert.

### 2.0.7 — 01.11.2026

- Intervallanzeige samt `-/+`-Legende rechtsbündig in der unteren Statusleiste
  angeordnet.

### 2.0.6 — 01.11.2026

- „LLM Terminal Monitor“ unabhängig von der Terminalbreite horizontal mittig
  in der ersten Kopfzeile positioniert.

### 2.0.5 — 01.11.2026

- Kopf-Logo als kompaktes Terminalfenster mit Prompt, Aktivitätspixel und
  LLM-Kennung gestaltet.

### 2.0.4 — 01.11.2026

- Pixel-Logo auf acht Zeichen Breite erweitert, damit es im Terminalraster
  optisch quadratisch ist.
- Zwei freie Spalten zwischen Logo und Kopftext ergänzt.

### 2.0.3 — 01.11.2026

- Quadratisches Pixel-Logo für den vierzeiligen TUI-Kopf gestaltet.
- Eine Leerzeile trennt den Kopf von den Messwerten; die Ollama-Version steht
  direkt hinter dem Namen.

### 2.0.2 — 01.11.2026

- TUI-Kopfbereich als vierzeilige Produktidentität mit Pixel-Icon, Version,
  Ollama- und Open-WebUI-Collector-Status sowie Autor, Technik und Intervall
  gestaltet.
- Kompaktansicht priorisiert bei 40×18 den neuen Kopf und die Kernwerte; VRAM
  und Leistung werden dort ausgeblendet.

### 2.0.1 — 01.11.2026

- TUI-Start prüft den global aktiven Open-WebUI-Filter `llmtop_run_metrics`
  asynchron und installiert ihn bei Fehlen oder Deaktivierung automatisch.
- Ohne lokale Zugangsdaten, bei API-Fehlern sowie in `--once`- und Skriptmodi
  bleibt die Adapter-Konfiguration unverändert.

### 2.0.0 — 01.11.2026

- Projekt hart von **otop** zu **llmtop** umbenannt: Startdatei, Module,
  Tests, Open-WebUI-Adapter, Konfigurationspräfix und State-Pfad migriert.
- `OTOP_*` und `$XDG_STATE_HOME/otop/` werden nicht mehr gelesen.
- Neues Pixel-Icon in TUI-Kopfzeile und `--once` ergänzt.
- Open-WebUI-Filter-ID lautet nun `llmtop_run_metrics` und wird separat neu
  installiert.

### 1.10.12 — 01.11.2026

- Verbindungsnamen Ollama und Open-WebUI Collector gedimmt grau dargestellt.
- Redundanten Ollama-Abschnitt und seine Collector-Zeile entfernt.

### 1.10.11 — 01.11.2026

- Collector als „Open-WebUI Collector“ bezeichnet.
- Verbindungsnamen Cyan sowie aktive/inaktive Stati Grün/Rot dargestellt.

### 1.10.10 — 01.11.2026

- Kopfzeile um Ollama- und Collector-Verbindungsstatus erweitert.
- TUI-Standardintervall auf 0,5 s und Untergrenze auf 0,2 s reduziert.

### 1.10.9 — 01.11.2026

- Bereichslinien bis zum linken Rand gezogen und Inhalte um ein Zeichen
  eingerückt.
- Tabulatorposition zwischen Modellname und Metadaten von 24 auf 16 verkürzt.

### 1.10.8 — 01.11.2026

- Tok/s-Farben ohne Fettdruck dargestellt.

### 1.10.7 — 01.11.2026

- Nur VRAM-Prozent farbig, `/RAM%` und Größen gedimmt grau dargestellt.
- Tok/s aktueller Runs farbig bewertet: rot unter 10, gelb unter 50, grün ab 50.

### 1.10.6 — 01.11.2026

- Modell-VRAM/RAM nach Sensorraster formatiert: Prozentwerte `%/%` nach dem
  Balken, danach gedimmte VRAM-/RAM-Größen in GiB.

### 1.10.5 — 01.11.2026

- Kontextanzeige an CPU-/GPU-Raster angepasst: Prozentwert rechtsbündig nach
  dem Balken, gedimmter Verbrauch danach.

### 1.10.4 — 01.11.2026

- Kontextanzeige aktueller Runs ordnet Prozent vor Verbrauch und Limit an.
- Bereichsüberschriften eingerückt und mit Linien vor sowie nach dem Titel
  dargestellt.

### 1.10.3 — 01.11.2026

- Modellnamen grau und unterstrichen dargestellt.
- Aktuelle Run-Zeilen per Tabulator für Quelle, Modell, Status und Metriken
  ausgerichtet.

### 1.10.2 — 01.11.2026

- Modellnamen wieder Cyan und unterstrichen dargestellt.
- Modellinformationen folgen ab fester Tabulatorposition mit gleichmäßigen
  Abständen.

### 1.10.1 — 01.11.2026

- Kontextlabel vor dem Balken in Cyan statt Dunkelgrün dargestellt.
- Projektregel auf Patch-Sprünge für normale Änderungen umgestellt.

### 1.10.0 — 01.11.2026

- Modell-Speicheranzeige in „VRAM/RAM“ umbenannt und Werte entsprechend
  beschriftet.
- Modellnamen hellgrün sowie Kontextlabel vor dem Balken dunkelgrün dargestellt.

### 1.9.0 — 01.11.2026

- Letzten abgeschlossenen Run weiterhin im Bereich „Aktuelle Runs“ anzeigen,
  bis ein neuer Run startet.
- Finale Metriken ergänzen zuvor erfasste Run-Daten vor Live-Anzeige und
  History-Persistierung.

### 1.8.8 — 01.11.2026

- TUI-Abbruch beim Anzeigen von History-Token behoben; `total_tokens` wird im
  ausgelagerten curses-Modul korrekt importiert und getestet.

### 1.8.7 — 01.11.2026

- TUI-Abbruch bei geladenen Modellen behoben; `datetime` für die Unload-Anzeige
  wird im ausgelagerten curses-Modul korrekt importiert.

### 1.8.6 — 01.11.2026

- TUI-Abbruch beim Formatieren vorhandener Run-History behoben; das ausgelagerte
  curses-Modul importiert `_parse_time` wieder korrekt.

### 1.8.5 — 01.11.2026

- `llmtop.py` auf Programmeinstieg, CLI und Snapshot-Orchestrierung reduziert.
- Datenerfassung in `llmtop_sources.py`, Run-Metriken, History und Collector in
  `llmtop_metrics.py` sowie curses-Rendering und Hintergrundsampler in
  `llmtop_tui.py` getrennt.
- Langsame Erfassung läuft außerhalb des curses-Hauptthreads; die bestehende
  Schema-2-Quelle `pi` ist für einen späteren optionalen Pi-Adapter getestet.

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
- Optionalen JSONL-Run-Eingang über `LLMTOP_RUN_FILE` ergänzt.
- Kontextbalken, Prompt-/Ausgabe-/Gesamttoken und Ausgabe-Rate ergänzt.
- Nicht instrumentierte oder veraltete Runs werden eindeutig angezeigt.

### 1.4.0 — 31.10.2026

- Lokale, begrenzte JSONL-History mit UTC-Zeitstempeln, atomischem Schreiben
  und tolerierter Beschädigung einzelner Zeilen ergänzt.
- Snapshot-Schema für Ollama-, System-, GPU- und Fehlerdaten eingeführt.
- History-Pfad über `LLMTOP_HISTORY_FILE` beziehungsweise `XDG_STATE_HOME`
  konfigurierbar; Standardpfad ist `~/.local/state/llmtop/history.jsonl`.

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

1. `python3 -m py_compile llmtop.py` ausführen.
2. `python3 llmtop.py --version`, `--once` und `--once --no-nvidia` prüfen.
3. TUI in einem echten Terminal sowie Fehlerfälle mit Mock-Ollama prüfen.
4. Dokumentation und `VERSION` abgleichen.
