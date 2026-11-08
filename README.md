<div align="center">
  <img src="assets/llmtop-logo.svg" alt="llmtop – LLM Terminal Monitor" width="620">
  <p><strong>Terminal-Monitor für Ollama</strong> mit System-, GPU- und Run-Metriken.</p>
</div>

![llmtop-Beispielansicht](assets/llmtop-screenshot.png)

> **Version 2.3.81** · Python-Anwendung aus der Standardbibliothek für Linux.

`llmtop` zeigt den Ollama-Status, lokale CPU-/RAM-/GPU-Sensoren sowie laufende
und abgeschlossene Modell-Runs in einer curses-TUI oder als einmaligen
Text-Snapshot. Run-Daten bleiben datensparsam: Prompts, Antworten und Tooldaten
werden nicht gespeichert.

## Eigenschaften

- keine pip-Abhängigkeiten und keine Konfigurationsdatei außer der optionalen
  `.env`
- TUI mit Live-Sensoren, Modellstatus, aktuellen Runs und Run-History
- `--once` für Skripte, SSH-Sitzungen und Diagnose ohne curses
- GPU-Erfassung über `nvidia-smi` und sysfs-Fallbacks
- token-geschützter lokaler Collector für Pi und Open WebUI
- JSONL-Speicherung mit begrenzter Größe und atomarem Schreiben
- optionale Run-Energiequellen: CPU-RAPL, AMD-sysfs und NVIDIA-`nvidia-smi`

## Voraussetzungen

- Linux
- Python 3.9 oder neuer
- ein erreichbarer Ollama-Server für Modellstatus und Modellliste
- optional: `nvidia-smi` für detaillierte NVIDIA-Werte

Fehlende Hardware, Berechtigungen oder Sensoren führen nicht zum Abbruch;
nicht verfügbare Einzelwerte erscheinen als `n/a`.

## Schnellstart

```bash
python3 llmtop.py                  # Vollbild-TUI
python3 llmtop.py --interval 1    # TUI mit 1 s Aktualisierung
python3 llmtop.py --once          # einmaliger Snapshot
python3 llmtop.py --version
```

`OLLAMA_HOST` wird als Standard übernommen. Ohne Angabe gilt
`http://localhost:11434`; Hostwerte ohne Protokoll werden zu `http://...`
ergänzt.

## Kommandozeile

| Option | Funktion |
|---|---|
| `--host URL` | Ollama-Adresse; Standard `$OLLAMA_HOST` oder `http://localhost:11434` |
| `--interval SEKUNDEN` | TUI-Aktualisierung; Standard `0.5`, mindestens `0.2` |
| `--once` | einen Snapshot ausgeben und ohne Vollbild beenden; CPU-Messung 1 s |
| `--no-nvidia` | `nvidia-smi` überspringen und sysfs verwenden |
| `--chat JSON` | direkten Streaming-Request an `/api/chat` instrumentieren |
| `--generate JSON` | direkten Streaming-Request an `/api/generate` instrumentieren |
| `--energy-rapl-sudo` | bei `--chat`/`--generate` CPU-RAPL über vorhandenes sudo-Caching lesen |
| `--collector` | lokalen Collector als blockierenden Dienst starten |
| `--collector-bind ADRESSE` | Collector-Bind-Adresse; Standard `127.0.0.1` |
| `--collector-port PORT` | Collector-Port; Standard `11435` |
| `--emit DATEI` | Schema-2-Ereignis aus Datei oder `-` an den Collector senden |
| `--install-open-webui-adapter` | Open-WebUI-Filter per Admin-API installieren und aktivieren |
| `--setup` | interaktives Onboarding für erkannte Dienste starten |
| `--discover` | lokale, Docker- und LAN-Dienste anzeigen |
| `--reset-setup` | gespeicherte Onboarding-Konfiguration nach Bestätigung löschen |
| `--debug` | technische Diagnosemeldungen aktivieren |
| `--log-file DATEI` | Diagnosemeldungen in eine private Logdatei schreiben |
| `--version` | Versionsnummer ausgeben und beenden |

Beispiele:

```bash
python3 llmtop.py --host http://127.0.0.1:11434 --once
python3 llmtop.py --once --no-nvidia
python3 llmtop.py --chat @request.json
python3 llmtop.py --generate '{"model":"qwen3.5:4b","prompt":"Hallo"}'
python3 llmtop.py --emit event.json
```

`--energy-rapl-sudo` ist ausschließlich mit `--chat` oder `--generate`
erlaubt. Ohne TTY beendet sich der normale Vollbildmodus mit Exit-Code `1`;
verwende dann `--once`.

## TUI-Bedienung

| Taste | Wirkung |
|---|---|
| `q` / `Q` | beenden |
| `r` / `R` | Programm mit denselben Optionen neu laden |
| `o` / `O` | Onboarding nach Bestätigung neu starten und die Konfiguration neu laden |
| `x` / `X` | sichtbare sudo-Abfrage für CPU-RAPL öffnen |
| `h` / `H` | Hilfe und Sensorquellen ein-/ausblenden |
| `-` | Aktualisierungsintervall halbieren, mindestens `0.2 s` |
| `+` / `=` | Aktualisierungsintervall verdoppeln, höchstens `60 s` |
| `a` / `A` | Fokus zwischen aktuellen Runs und History wechseln |
| `Tab` / `Shift-Tab` | History-Sortierspalte wechseln |
| `s` / `S` | Sortierrichtung wechseln |
| `Enter` | Metadaten des History-Eintrags als Overlay anzeigen |
| `Leertaste` | History-Gruppe auf- oder zuklappen |
| `←` / `→` | Gruppe zu- oder aufklappen |
| `↑` / `↓` | Cursor bewegen |
| `Bild↑` / `Bild↓` | seitenweise bewegen |
| `Pos1` / `Ende` | ersten oder letzten History-Eintrag wählen |
| `c` / `C` | Run-History nach Bestätigung leeren |

Die Mindestgröße beträgt `40×18`. Kleine Terminals verwenden eine kompakte
Ansicht, damit Bereiche nicht überzeichnet werden.

## Angezeigte Werte

### System

- CPU-Auslastung aus `/proc/stat`
- CPU-Modell, nutzbare logische Kerne und CPU-Temperatur
- CPU-Power mit Fallback-Kette:
  1. interne AMD-APU-Leistung von GPU1, wenn als CPU-/SoC-Wert erkannt
  2. eindeutig zugeordnetes CPU-hwmon
  3. TUXEDO Control Center über lesendes D-Bus
  4. optionaler privilegierter RAPL-Helper
  5. direkter RAPL-Zähler als letzte Instanz
- RAM-Auslastung und verfügbarer Speicher aus `/proc/meminfo`, unter
  Berücksichtigung geeigneter cgroup-Grenzen

Wenn die interne GPU1-/APU-Leistung als CPU-Power verwendet wird, wird sie
nicht zusätzlich als GPU1-Power dargestellt. Andere GPUs zeigen ihre eigenen
verfügbaren Powerwerte weiterhin an.

### GPU und Modelle

- mehrere DRM-GPUs bleiben sichtbar und werden über PCI-Bus-ID bzw. sysfs
  zusammengeführt
- NVIDIA bevorzugt `nvidia-smi`; AMD nutzt amdgpu-sysfs; Intel verwendet
  bekannte i915-/xe- und generische GT-Busy-Dateien
- GPU-Auslastung, Temperatur, VRAM und verfügbare Powerwerte
- GPU1-/APU-Power wird nicht doppelt als GPU-Leistung angezeigt, wenn sie
  bereits die CPU-Power liefert
- geladene Ollama-Modelle aus `/api/ps` mit Name, Größe, VRAM-Anteil,
  Quantisierung, Kontextlimit, Runner und Ablaufzeit

Die Modellkarte zeigt die Aufteilung von VRAM und CPU/RAM. GPU-Auslastungs- und
Temperaturfarben dienen der Orientierung; nicht verfügbare Einzelwerte bleiben
`n/a`.

### Runs und Kontext

Instrumentierte Runs zeigen, soweit vom Provider geliefert:

- Quelle und Provider
- Modell, Status und Identität
- Prompt-, Ausgabe- und Gesamttoken
- Kontextverbrauch und Kontextlimit
- Ausgabe-Rate und Dauer
- Anzahl erfolgreicher Kontext-Compactions für Pi und Open WebUI
- Dauer kompakt in Minuten und Stunden, sofern verfügbar
- bei Open WebUI und lokalen Pi-Ollama-Runs zusätzlich Verbrauch in Wh, sofern gemessen; laufende
instrumentierte Runs aktualisieren den Wert bereits während des Laufs

Aktuelle Runs und History verwenden dieselben Tabellenwerte. In Aktuelle Runs
werden die Run-Zeilen cyan dargestellt; Gruppenüberschriften sind grau und
unterstrichen. Kontext und Tok/s behalten ihre dynamischen Statusfarben. Die
aktuellen Runs bleiben unabhängig von der History-Sortierung nach unveränderlicher
Startzeit angeordnet. In der Tokenspalte werden Kontextverbrauch und Limit als
`16.7/32.8k` zusammengefasst; der Kontextbalken zeigt daneben nur den Prozentwert.
Die History kann nach Zeit, Quelle, Modell, Status, Tokens, Kontextverbrauch, Tok/s
und Dauer sortiert werden; zusätzlich kann nach `Komp.` sortiert werden. Pi-Runs werden nach `session_id`, Open-WebUI-Runs bevorzugt
nach `chat_id` gruppiert. Eingeklappte Gruppen repräsentieren den neuesten
abgeschlossenen Run; die Gruppenzeile summiert Komp.-Zähler und Dauer aller enthaltenen
Runs. Bei mehreren Läufen zeigt das Overlay zusätzlich ein gefülltes Token-Stufendiagramm über die Session; Kompaktierungen werden im
Diagramm markiert. Run-Nummern stehen zentriert unter dem Diagramm; bei langen
Sessions fasst das Diagramm die Runs in nummerierte Zeitabschnitte zusammen. Das
Einzelne Runs belegen im Diagramm höchstens vier Zeichen; bei einem breiten Terminal
nutzt das Overlay die verfügbare Breite für weitere Runs. Aufgeklappt erscheinen die Einzelruns.

Der Pi-Adapter aktualisiert den Session-Kontext während des laufenden Agenten-
Laufs und unmittelbar vor dem Abschluss erneut. Open-WebUI-Runs übernehmen einen
bereits im Request vorhandenen Session-Kontext vor dem ersten Provider-Chunk;
die Startmeldung zeigt zunächst `n/a`, danach wird der Wert aktualisiert. Es
werden nur explizite Usage-/Kontextzähler verwendet, keine Textschätzungen.
Dadurch übernimmt die History
den letzten verfügbaren Live-Stand. Fehlen Providerwerte, zeigt llmtop `n/a`
statt einer Schätzung.

## Collector und Adapter

### Collector

Der Collector empfängt Schema-2-Ereignisse über:

- `POST /v1/runs`
- `POST /v1/runs/pi`
- `POST /v1/runs/open-webui`

Standardmäßig lauscht er auf `127.0.0.1:11435` und – wenn erkannt – zusätzlich
auf dem privaten Docker-Gateway von Open WebUI. Ein Bearer-Token ist
standardmäßig erforderlich. Für isolierte lokale Tests kann ausnahmsweise
`LLMTOP_COLLECTOR_INSECURE=1` verwendet werden.

Im normalen TUI-Start werden ein lokaler Collector mit zufälligem Token und
– sofern Pi installiert ist – der Pi-Adapter automatisch eingerichtet. Dafür
sind weder Ollama noch Open WebUI erforderlich. Die private Verbindung wird in
`$XDG_STATE_HOME/llmtop/pi-collector.json` gespeichert.

Für einen separat betriebenen oder entfernten Collector kann weiterhin
`.env` verwendet werden:

```bash
cp .env.example .env
# LLMTOP_COLLECTOR_TOKEN in .env setzen
python3 llmtop.py --collector
```

Collector-Fehler stoppen weder Sensoren noch TUI.

### Onboarding und Erkennung

Beim ersten interaktiven TUI-Start sucht llmtop nach Ollama und Open WebUI auf
lokalen Standardports, veröffentlichten Docker-Ports und – wenn lokal nichts
gefunden wurde – begrenzt im privaten LAN. Gefundene URLs werden vorausgewählt.
Für Open WebUI kann der Admin-API-Key verdeckt eingegeben werden; anschließend
wird der Filter automatisch installiert und aktiviert.

```bash
python3 llmtop.py --setup
python3 llmtop.py --discover
```

Die Konfiguration liegt privat unter
`$XDG_STATE_HOME/llmtop/config.json` (sonst `~/.local/state/llmtop/config.json`)
mit Dateirechten `0600`. Umgebungsvariablen und `.env` haben Vorrang. API-Keys
werden nicht geloggt und nicht in History-Dateien gespeichert. Nicht-interaktive
Aufrufe wie `--once` starten kein Onboarding.

### Open WebUI

Der Filter `open_webui/llmtop_run_metrics.py` wird ausschließlich über die
Open-WebUI-API installiert. Für automatische Installation in `.env` setzen:

```dotenv
LLMTOP_COLLECTOR_TOKEN=<langer-zufälliger-wert>
LLMTOP_COLLECTOR_URL=http://127.0.0.1:11435
OPEN_WEBUI_URL=http://127.0.0.1:3000
OPEN_WEBUI_API_KEY=<Open-WebUI-Admin-API-Key>
```

Danach genügt ein normaler TUI-Start:

```bash
python3 llmtop.py
```

Oder die Installation wird explizit ausgelöst:

```bash
python3 llmtop.py --install-open-webui-adapter
```

Der Filter überträgt keine Chatinhalte. Bei Tool-Loops werden die Usage-Werte
des aktuellen Modellaufrufs gegenüber kumulierten Zwischenwerten bevorzugt.

### Pi

`pi/llmtop_run_metrics.ts` ist ein dependency-freier Pi-Adapter. Bei
konfiguriertem Collector wird er beim normalen TUI-Start automatisch nach
`~/.pi/agent/extensions/llmtop_run_metrics.ts` kopiert.

Nach einem Update:

1. `python3 llmtop.py` starten oder die TUI mit `r` neu laden.
2. In einem bereits laufenden Pi-Prozess `/reload` ausführen oder Pi neu starten.

Der Adapter überträgt nur Quelle, Provider, Session-ID, Modell, UUID,
Zeitstempel und Nutzungsmetriken. Prompts, Antworten, Tooldaten, Sessionpfade
und Zugangsdaten bleiben lokal in Pi.

## Konfiguration und Dateien

Die Kernanwendung benötigt keine Initialisierung. Optionale Einstellungen
kommen aus `.env` oder der Umgebung:

| Variable | Zweck |
|---|---|
| `OLLAMA_HOST` | Standardadresse des Ollama-Servers |
| `LLMTOP_COLLECTOR_TOKEN` | Bearer-Token für den Collector |
| `LLMTOP_COLLECTOR_URL` | Collector-Adresse; Standard `http://127.0.0.1:11435` |
| `LLMTOP_COLLECTOR_BIND` | Collector-Bind-Adresse |
| `LLMTOP_COLLECTOR_PORT` | Collector-Port |
| `LLMTOP_COLLECTOR_INSECURE` | nur mit Wert `1` tokenlosen lokalen Test erlauben |
| `LLMTOP_HISTORY_FILE` | System-Snapshot-Datei überschreiben |
| `LLMTOP_RUN_FILE` | Live-Run-Datei überschreiben |
| `LLMTOP_RUN_HISTORY_FILE` | Run-History-Datei überschreiben |
| `LLMTOP_OPEN_WEBUI_DB` | optionaler lesender Open-WebUI-Datenbank-Fallback |
| `XDG_STATE_HOME` | Basisverzeichnis für llmtop-Zustandsdaten |
| `OPEN_WEBUI_URL` | Open-WebUI-Adresse; wird beim Onboarding automatisch ermittelt |
| `OPEN_WEBUI_API_KEY` | Open-WebUI-Admin-Key; wird beim Onboarding verdeckt abgefragt |

Standardpfade:

```text
$XDG_STATE_HOME/llmtop/history.jsonl
$XDG_STATE_HOME/llmtop/run.jsonl
$XDG_STATE_HOME/llmtop/runs.jsonl
$XDG_STATE_HOME/llmtop/pi-collector.json
$XDG_STATE_HOME/llmtop/config.json
$XDG_STATE_HOME/llmtop/llmtop.log       # nur bei --debug im TUI-Modus
```

Ohne `XDG_STATE_HOME` verwendet llmtop `~/.local/state/llmtop/`. Dateien werden
begrenzt, atomar und – soweit von llmtop erstellt – mit privaten Rechten
geschrieben. Die System-Snapshot-History ist auf 500 Einträge begrenzt; die
Run-History ebenfalls auf 500 abgeschlossene Runs. Aktive Runs verfallen nach
90 Sekunden ohne Lebenszeichen, abgeschlossene Live-Einträge nach 10 Sekunden;
die dauerhafte Run-History bleibt erhalten.

## Bekannte Grenzen

- Ollama liefert keine Host-CPU-/GPU-Auslastung; diese Werte stammen vom lokalen
  Linux-System und sind nicht exklusiv einem Modell zuordenbar.
- GPU-Sensoren hängen von Kernel, Treiber, sysfs und Berechtigungen ab.
- Die erste CPU-%-Anzeige lautet `Messung`, weil ein Differenzwert benötigt wird.
- Die Ollama-Abfrage kann die TUI bei langsamer Netzwerkverbindung kurzzeitig
  blockieren.
- Viele geladene Modelle können auf kleinen Terminals aus dem sichtbaren Bereich
  laufen; es gibt keinen separaten Modell-Scrollmodus.
- Run-History und System-History enthalten keine Prompts oder vollständigen
  Modellantworten.
- Der Datenbank-Fallback für Open WebUI ergänzt nur eindeutig zuordenbare Werte.

## Projektstruktur

| Datei | Zweck |
|---|---|
| `llmtop.py` | CLI, TUI-Start und `--once` |
| `llmtop_sources.py` | Ollama-, CPU-, RAM- und GPU-Quellen |
| `llmtop_metrics.py` | Run-Schema, Collector, History und Adapterintegration |
| `llmtop_tui.py` | curses-Rendering und Sampler |
| `open_webui/llmtop_run_metrics.py` | Open-WebUI-Filter |
| `pi/llmtop_run_metrics.ts` | Pi-Adapter |
| `status.md` | aktueller Projektstand und Grenzen |
| `version.md` | Versionsschema und Changelog |
| `.env.example` | Beispielkonfiguration |

## Prüfen

Die kleinsten Projektprüfungen sind:

```bash
python3 -m py_compile llmtop.py llmtop_sources.py llmtop_metrics.py llmtop_tui.py
python3 llmtop.py --version
python3 llmtop.py --once
python3 llmtop.py --once --no-nvidia
python3 open_webui/test_llmtop_run_metrics.py
```

Die maßgebliche Versionsnummer steht in `VERSION` in `llmtop.py`. Bei einem
Release werden `README.md`, `status.md` und `version.md` synchron gehalten.
