# Plan: Einfache Mehrdateien-Struktur mit Vorbereitung für Pi-Metriken

## Ziel

Die 1.757 Zeilen große `llmtop.py` soll übersichtlicher werden, ohne daraus ein
komplexes Paket oder Framework zu machen. Bestehende CLI-Aufrufe, Exit-Codes,
Tasten, Datenformate und Anzeigen bleiben erhalten.

Die Aufteilung soll außerdem den nächsten Schritt vorbereiten: Pi soll seine
Run-Metriken über den bereits vorhandenen Collector an `llmtop` melden können.
Dafür wird kein Plugin-System benötigt. Das bestehende Schema-2-Ereignisformat
und `POST /v1/runs` bleiben die gemeinsame Schnittstelle für Pi, Open WebUI und
den direkten Ollama-Client.

## Befund

Die Dateigröße selbst verursacht keinen wesentlichen Laufzeitverlust. Die
relevanten Verzögerungen entstehen durch synchrone Arbeit im TUI-Thread:

- Ollama-HTTP-Abfragen können bis zum Timeout blockieren.
- `nvidia-smi` benötigt auf dem aktuellen System rund 25 ms pro Aufruf.
- sysfs ist schnell, wird aber bei jedem Refresh erneut durchsucht.
- Snapshot-History wird vollständig und mit `fsync` neu geschrieben.
- `--version` lädt derzeit auch Module, die dafür nicht benötigt werden;
  gemessener Median: rund 69 ms.

Die Strukturänderung schafft daher vor allem klare Zuständigkeiten. Der
spürbare Performancegewinn entsteht durch einen einfachen Hintergrund-Sampler
und verzögerte Imports, nicht durch möglichst viele Dateien.

## Vereinfachte Zielstruktur

```text
llmtop.py                 # VERSION, CLI, Moduswahl, Snapshot-Orchestrierung
llmtop_sources.py         # Ollama-Abfragen sowie CPU-, RAM- und GPU-Sensoren
llmtop_metrics.py         # Run-Schema, History, Collector und Metrik-Hilfen
llmtop_tui.py             # curses-Rendering, Eingaben und TUI-Ablauf
open_webui/
    llmtop_run_metrics.py # bestehender Open-WebUI-Adapter

# Im nächsten Schritt, nicht Teil dieser Umstrukturierung:
pi/
    llmtop_run_metrics.py # optionaler Pi-Adapter für dasselbe Schema 2
```

Es werden nur drei neue Kernmodule eingeführt. Kein `src/`-Layout, kein
installierbares Paket, keine abstrakten Basisklassen und keine dynamische
Plugin-Erkennung. Der Start bleibt:

```bash
python3 llmtop.py
```

## Zuständigkeiten

### `llmtop.py`

- einzige Versionsquelle `VERSION`;
- ArgumentParser und unveränderte CLI-Optionen;
- Auswahl von `--once`, TUI, Collector, Emit, Chat/Generate und Installation;
- Aufbau eines vollständigen Snapshots aus Quellen und Run-Metriken;
- einfacher Hintergrund-Sampler für die TUI;
- Lazy Imports: schwere Module erst nach Auswahl des CLI-Modus laden.

`llmtop.py` bleibt damit der gut lesbare Programmeinstieg und enthält weiterhin
die übergeordnete Ablaufsteuerung.

### `llmtop_sources.py`

- `normalize_host`, Ollama `/api/version` und `/api/ps`;
- direkter `/api/chat`- und `/api/generate`-Client;
- CPU, RAM, Load und Temperaturen;
- NVIDIA- und sysfs-GPU-Erfassung;
- ausschließlich Datenerfassung, keine curses-Ausgabe und kein Collector.

### `llmtop_metrics.py`

- Schema-2-Validierung und Normalisierung;
- aktive Runs, Run-History und System-Snapshot-History;
- Token-, Kontext-, Rate- und Sortierfunktionen;
- Collector `POST /v1/runs` und Eventverarbeitung;
- Open-WebUI-Installation und derzeitiger DB-Fallback;
- gemeinsame Dateisperre und atomische JSONL-Schreibvorgänge.

Dieses Modul ist die stabile Grenze für Pi. Es verarbeitet ausschließlich das
gemeinsame Ereignisformat und kennt keine Pi-interne API.

### `llmtop_tui.py`

- Balken- und Textformatierung;
- vollständiges curses-Rendering;
- Tastatursteuerung, History-Sortierung und Scrollen;
- Anzeige des jeweils letzten fertigen Snapshots;
- keine direkten HTTP-, Sensor- oder JSONL-Schreibzugriffe.

## Vorbereitung für Pi-Metriken

Der nächste Schritt soll ohne erneuten Umbau des Kerns möglich sein:

1. Der spätere Pi-Adapter sendet dieselben Ereignisse wie Open WebUI an
   `POST /v1/runs`.
2. `source` bleibt `pi`; `run_id`, `source_run_id`, Modell, Status, Zeiten,
   Token und Dauern werden bereits vom vorhandenen Schema unterstützt.
3. Pi-spezifische Feldnamen werden ausschließlich im Pi-Adapter normalisiert.
   Der Collector erhält weiterhin nur Schema 2.
4. Ein Provider-Aufruf ist ein Run. Tool- oder Fortsetzungsrunden können über
   ihre eigene `run_id` beziehungsweise eine vorhandene `source_run_id`
   eindeutig zugeordnet werden. Eine zusätzliche Sitzungslogik wird erst
   eingeführt, wenn reale Pi-Ereignisse sie nachweislich benötigen.
5. Der Adapter verwendet einen kurzen Timeout. Ein nicht erreichbarer Collector
   darf Pi oder den Modellaufruf nicht blockieren.
6. Prompts, Antworten, Tool-Inhalte und Zugangsdaten werden nicht übertragen.
7. Der Pi-Adapter bleibt eine optionale einzelne Datei unter `pi/`, analog zum
   bestehenden Open-WebUI-Adapter. Der Kern importiert Pi nicht.

Damit ist keine allgemeine Adapter-Architektur nötig. Der Collector und das
bereits etablierte Ereignisschema sind die Adapter-Schnittstelle.

## Implementierung in drei Schritten

### 1. Datenerfassung und Metriken sicher auslagern

1. Vor dem Verschieben gezielte Charakterisierungstests ergänzen:
   - CLI-Modi und Exit-Codes;
   - Ollama-Fehler und ungültige Antworten;
   - NVIDIA-CSV und sysfs-Fallback;
   - Schema-2-Events für `pi`, `open-webui` und `ollama-cli`;
   - History-Retention, Deduplizierung und parallele Collector-Updates.
2. Sensor- und Ollama-Funktionen nach `llmtop_sources.py` verschieben.
3. Run-, History- und Collector-Funktionen nach `llmtop_metrics.py` verschieben.
4. `llmtop.py` importiert die verschobenen Funktionen zunächst direkt, damit das
   Verhalten unverändert bleibt.
5. Nach jeder Verschiebung Syntaxcheck und betroffene Tests ausführen.

**Zwischenabnahme:** Alle bestehenden Befehle und Tests funktionieren; es wurde
nur Code verschoben, noch kein Ablauf geändert.

### 2. TUI trennen und blockierende Abfragen entkoppeln

1. Rendering und Tastaturbehandlung nach `llmtop_tui.py` verschieben.
2. In `llmtop.py` einen einzelnen Hintergrund-Thread für die Datenerfassung
   einführen. Er erstellt pro Intervall einen vollständigen Snapshot.
3. Die TUI liest nur den zuletzt vollständig veröffentlichten Snapshot. curses
   bleibt vollständig im Hauptthread.
4. Netzwerk, `nvidia-smi`, sysfs-Suche und History-Schreiben laufen nicht mehr
   im Eingabe-/Renderingpfad.
5. Zunächst keinen Thread-Pool einsetzen. Ollama und GPU werden erst parallel
   abgefragt, wenn eine spätere Messung einen klaren Nutzen zeigt.
6. Unveränderliche hwmon-/DRM-Pfade dürfen zwischengespeichert und bei Fehlern
   neu entdeckt werden. Messwerte selbst werden weiterhin je Refresh gelesen.
7. `/api/version` kann seltener als `/api/ps` aktualisiert werden.

**Zwischenabnahme:** Bei künstlich verzögerten Ollama- oder GPU-Abfragen reagiert
die TUI weiterhin auf `q`, Hilfe, Sortierung und Resize.

### 3. Einstieg verschlanken und Pi-Schnittstelle absichern

1. In `llmtop.py` schwere Module erst im tatsächlich gewählten Modus importieren.
   `--version` darf weder curses, sqlite3, HTTP-Server noch Sensorcode laden.
2. Einen Collector-Test mit Quelle `pi` ergänzen, der `started`, `updated` und
   `completed` prüft. Dabei werden keine Pi-Bibliotheken benötigt.
3. Sicherstellen, dass unbekannte optionale Felder ignoriert werden und fehlende
   Metriken als `n/a` erhalten bleiben. So kann der spätere Pi-Adapter mit einem
   minimalen Ereignis beginnen.
4. `AGENTS.md`, `README.md`, `status.md` und `version.md` auf die vier Kernmodule
   und die weiterhin reine Standardbibliothek aktualisieren.
5. Vollständige Regression und Vorher-/Nachher-Messung durchführen.

Der eigentliche Pi-Adapter wird erst im anschließenden Auftrag anhand der real
installierten Pi-Erweiterungs-API umgesetzt. So werden keine unbestätigten Hooks
oder Felder vorweggenommen.

## Performance-Abnahmekriterien

- Keine langsame Abfrage oder Schreiboperation läuft im curses-Thread.
- Die TUI bleibt bei simulierten zwei Sekunden Ollama-Verzögerung bedienbar.
- Pro Refresh wird ein vollständiger, konsistenter Snapshot veröffentlicht.
- `--version` startet nicht langsamer als der bisherige Median von rund 69 ms
  und lädt nur den CLI-Einstieg.
- History-Sortierung mit 100 Einträgen bleibt ohne sichtbare Verzögerung.
- Kein Thread-Pool, keine Queue und kein Cache-System ohne gemessene
  Notwendigkeit.

## Funktionale Abnahmekriterien

Unverändert funktionieren:

- `python3 llmtop.py --version`
- `python3 llmtop.py --once`
- `python3 llmtop.py --once --no-nvidia`
- TUI inklusive aller Tasten und 40×18-Mindestlayout
- `--chat`, `--generate`, `--collector`, `--emit`
- `--install-open-webui-adapter`

Zusätzlich gilt:

- Exit-Codes, JSONL-Schema 2, Dateipfade, Dateirechte und Retention bleiben
  kompatibel.
- Der vorhandene Open-WebUI-Adapter bleibt unverändert installierbar.
- Ein gültiges Ereignis mit `source: "pi"` durchläuft Collector, Live-Anzeige
  und History ohne Sonderbehandlung.
- Keine neue Abhängigkeit und kein Installationsschritt.

## Empfohlener erster Umsetzungsschritt

Zuerst nur Schritt 1 umsetzen: Tests für die bestehenden Grenzen ergänzen und
anschließend `llmtop_sources.py` sowie `llmtop_metrics.py` extrahieren. Die TUI und
die Nebenläufigkeit bleiben dabei zunächst unverändert. So entsteht ein kleiner,
prüfbarer Umbau und gleichzeitig die stabile Grundlage für den späteren
Pi-Adapter.
