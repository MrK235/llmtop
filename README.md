<div align="center">
  <img src="assets/llmtop-logo.svg" alt="llmtop – LLM Terminal Monitor" width="620">
  <p><strong>Terminal-Monitor für Ollama</strong> mit CPU-, RAM-, GPU-, VRAM- und Run-Metriken.</p>
  <p>
    <a href="#start">Schnellstart</a> ·
    <a href="#angezeigte-werte">Messwerte</a> ·
    <a href="#open-webui-adapter">Open WebUI</a> ·
    <a href="#pi-adapter">Pi-Adapter</a>
  </p>
</div>

![llmtop-Beispielansicht](assets/llmtop-screenshot.png)

> **Version 2.2.6** · Python-Terminal-Anwendung aus der Standardbibliothek.
> llmtop liest den Ollama-Status und lokale System-Sensoren direkt aus und
> zeigt laufende sowie abgeschlossene Modell-Runs datensparsam im Terminal.

Die Version wird im TUI-Kopf, in der ersten Zeile von `--once` und über
`--version` angezeigt. Die maßgebliche Versionsnummer steht in `VERSION` in
`llmtop.py`; die vollständige Historie befindet sich in `version.md`.

## Dateien

| Datei | Inhalt |
|-------|--------|
| `llmtop.py` | Programmeinstieg, CLI und Snapshot-Modus |
| `llmtop_sources.py` | Ollama-, CPU-, RAM- und GPU-Datenerfassung |
| `llmtop_metrics.py` | Run-Schema, JSONL-Historie, Collector und Open-WebUI-Integration |
| `llmtop_tui.py` | curses-Rendering und TUI-Hintergrundsampler |
| `README.md` | diese Anleitung |
| `status.md` | Projektstand, bekannte Grenzen und Prüfhinweise |
| `version.md` | Versionsschema, Versionsanzeige, Changelog |
| `pi/llmtop_run_metrics.ts` | optionaler globaler Pi-Adapter für lokale und Cloud-Provider |
| `assets/llmtop-logo.svg` | Projektlogo im aktuellen TUI-Stil |
| `assets/llmtop-screenshot.png` | Beispielansicht der TUI |
| `.gitignore` | lokale Python-Artefakte und Backups ausschließen |
| `plan/` | akzeptierte Arbeitspläne (Plan-Mode-Artefakte) |

## Versionierung

Das Projekt ist als Git-Repository eingerichtet. Der aktuelle Branch ist
`master`. Code, Dokumentation und akzeptierte
Pläne werden gemeinsam versioniert. Vor einem Commit: Tests aus `status.md`
ausführen, `VERSION` sowie `README.md`, `status.md` und `version.md` abgleichen.
Tags verwenden das Format `vX.Y.Z`.

## Umstieg 2.0

Dies ist ein harter Namenswechsel: Der Start erfolgt ausschließlich über
`python3 llmtop.py`; die früheren `otop.py`-Dateien, `OTOP_*`-Variablen und
`$XDG_STATE_HOME/otop/` werden nicht mehr verwendet. Die neuen Pfade und
Variablen beginnen mit `llmtop` beziehungsweise `LLMTOP_`. Nach dem Umstieg
muss der Open-WebUI-Adapter einmal mit
`python3 llmtop.py --install-open-webui-adapter` neu installiert werden.

## Start

```bash
python3 llmtop.py                      # Vollbild-TUI (curses), Refresh alle 0,5 s
python3 llmtop.py --interval 1         # TUI mit 1 s Refresh
python3 llmtop.py --once               # ein Einzel-Snapshot (Skripte / kein Terminal)
python3 llmtop.py --host http://127.0.0.1:11434
python3 llmtop.py --chat '{"model":"qwen3.5:4b","messages":[{"role":"user","content":"Hallo"}]}'
python3 llmtop.py --collector          # Loopback und privates Open-WebUI-Docker-Gateway
python3 llmtop.py --install-open-webui-adapter  # Filter per Open-WebUI-API installieren
python3 llmtop.py --emit event.json    # Schema-2-Testevent an den Collector senden
python3 llmtop.py --no-nvidia          # nvidia-smi überspringen (sysfs-Pfad)
python3 llmtop.py --version            # Versionsnummer, danach Exit 0 (kein TUI)
```

`$OLLAMA_HOST` wird als Default übernommen; `--host` ohne Protokoll wird zu
`http://<host>`. Für einen optionalen, ausschließlich lesenden Open-WebUI-
Datenbank-Fallback kann `LLMTOP_OPEN_WEBUI_DB` auf einen zugänglichen Pfad zu
`webui.db` gesetzt werden. Ohne stabile Zuordnung werden keine Daten ergänzt.

| Option | Verhalten |
|--------|-----------|
| `--host` | Ollama-URL; Default `$OLLAMA_HOST`, sonst `http://localhost:11434` |
| `--interval` | Refresh-Sekunden im TUI; Default 0,5 s, **auf 0,2–60 s begrenzt** (`--interval 0.1` → 0,2 s) |
| `--once` | ein Snapshot, kein Vollbild; ignoriert `--interval` (CPU-Messung 1 s) |
| `--no-nvidia` | `nvidia-smi` nicht aufrufen, sysfs benutzen |
| `--chat JSON` | direkter Streaming-Aufruf an `/api/chat`, Abschlussmetriken lokal speichern |
| `--generate JSON` | direkter Streaming-Aufruf an `/api/generate`, Abschlussmetriken lokal speichern |
| `--collector` | lokalen, token-geschützten Collector für `POST /v1/runs` starten |
| `--collector-bind` / `--collector-port` | Listen-Adresse und Port; Default bleibt `127.0.0.1:11435` |
| `--emit DATEI` | Schema-2-Event aus Datei oder `-` für stdin an den Collector senden |
| `--install-open-webui-adapter` | Filter per Open-WebUI-Admin-API installieren, konfigurieren und global aktivieren |
| `--version` | Versionsnummer ausgeben und beenden |

## Exit-Codes

| Fall | Code |
|------|------|
| normal (`--once`, TUI mit `q`) | 0 |
| kein TTY (Vollbild ohne Terminal) | 1, Hinweis auf `--once` auf stderr |

## Tasten im TUI

| Taste | Wirkung |
|-------|---------|
| `q` / `Q` | beenden |
| `r` / `R` | Programm mit denselben Optionen neu laden |
| `h` / `H` | Hilfe ein/aus (wird ignoriert, wenn das Overlay nicht ins Terminal passt) |
| `-` | Intervall halbieren (min. 0,2 s) |
| `+` / `=` | Intervall verdoppeln (max. 60 s) |
| `Tab` / `Shift-Tab` | nächste / vorherige Sortierspalte der Run-History |
| `s` / `S` | Sortierrichtung der Run-History umschalten |
| `a` / `A` | Fokus zwischen aktuellen Runs und Run-History wechseln |
| `↑` / `↓`, `Bild↑` / `Bild↓`, `Pos1` / `Ende` | fokussierten Run-Bereich scrollen |

## TUI-Layout

Ein vierzeiliger Kopfbereich zeigt ein optisch quadratisches Terminal-Logo mit
Prompt und LLM-Kennung. Der Schriftzug **LLM Terminal Monitor** steht stets
mittig in der ersten Zeile; zwei Zeichen trennen Logo und Produkttext.
Ollama- und Open-WebUI-Collector-Status
sowie Autor und Technik. Die rechtsbündige Statusleiste enthält das Intervall
und die Legende `-/+`. Eine Leerzeile trennt ihn von den Messwerten. Die
Vollbildansicht
gliedert sich danach von oben nach unten in **System**, **GPU**,
**Geladene Modelle**, **Aktuelle Runs** und **History**. Bereichslinien beginnen am linken Rand und laufen
vor sowie nach dem Titel; alle übrigen Inhalte haben einen Leerzeichen-Rand
links. Bei 40×18 verwendet sie eine kompakte Ansicht mit
Kernwerten, Modellanzahl und History-Status, damit sich keine Bereiche
überzeichnen.
CPU, RAM, GPU-Auslastung, VRAM und Power verwenden
pro Terminal dieselbe Balkenbreite; Label, Prozentwert und Detailwert sind
spaltenweise ausgerichtet. Die Farbsyntax ist global: Struktur (Überschriften,
Labels und Rahmen) ist Cyan, Auslastungs- und Temperaturstatus Grün/Gelb/Rot,
Sekundärinfos gedimmt. Im Ollama-Speicherbalken bedeuten die Farben explizit
den Offload-Grad der GPU/VRAM-Anzeige: Grün oberhalb 55 %, Gelb bei 45–55 %
und Rot unterhalb 45 % GPU-Anteil. CPU/RAM bleibt gedimmt grau. Beide Anteile
nutzen `#` und zeigen zusätzlich Textwerte. Eine
Leerzeile trennt System, GPU, geladene Modelle, aktuelle Runs und History.
**Aktuelle Runs** und **History** verwenden dieselben Spalten und Werte für
Zeit, Quelle, Modell, Status, Tokens, Kontext, Tok/s und Dauer. Die Breite jeder
sichtbaren Spalte richtet sich dynamisch nach Überschrift und Inhalt; aktuelle
Runs und History nutzen dabei dieselben Spaltenbreiten. Die History berücksichtigt
dafür stets ihre gesamte Liste. Die Kontextspalte
zeigt den Fortschritt als farbigen Prozent-/Balkenwert sowie danach nur das graue Kontextlimit; der Prozentwert ist fest vier Zeichen breit und rechtsbündig, damit der Balken unabhängig von seiner Stellenzahl fluchtet. **History** zeigt
eine scrollbare Tabelle mit bis zu 100 abgeschlossenen instrumentierten Runs.
Sie kann nach Abschlusszeit, Quelle, Modell, Status, Tokens, Kontextverbrauch,
Ausgaberate und Dauer sortiert werden. Die aktive Sortierspalte ist im
Tabellenkopf exakt über die Länge ihres Textes unterstrichen und mit `▾`
beziehungsweise `▴` markiert; die History-Überschrift bleibt frei von
Sortierdetails. Eine Leerzeile trennt die History von der Statusleiste.
Kontext wird nach dem prozentualen Verbrauch sortiert, nicht nach der absoluten
Tokengröße. Die Kontextspalte zeigt Prozentwert, Fortschrittsbalken und danach
nur das Limit im Format `42% [######      ] 16.4k`; fehlende Providerwerte
bleiben `n/a`. Die Daten bleiben
als begrenzte JSONL-Datei gespeichert; eine Datenbank ist bei 100 Einträgen
nicht nötig. Zusätzlich speichert llmtop lokale, begrenzte System-Snapshots. Der
Snapshot-Pfad kann über `LLMTOP_HISTORY_FILE`, die Run-Historie über
`LLMTOP_RUN_HISTORY_FILE` oder `XDG_STATE_HOME` angepasst werden.

## Angezeigte Werte

* **Kopfbereich**: vierzeiliges, optisch quadratisches Terminal-Logo mit
  Prompt und LLM-Kennung sowie zwei freien Spalten zum Textblock. **LLM Terminal
  Monitor** ist stets mittig in der ersten Zeile platziert; `llmtop <VERSION>`
  und Produktname,
  `Ollama v<VERSION>` mit Erreichbarkeit (`/api/version`) sowie **Open-WebUI
  Collector**-Status (`aktiv` / `nicht aktiv`). Eine Leerzeile
  folgt vor den Messwerten. Die vierte Zeile nennt Autor und
  Python-Standardbibliothek. Rechts unten steht `-/+ Intervall <SEKUNDEN>` als
  Anzeige und Legende. Namen und Metadaten sind
  gedimmt grau; verbundene/aktive Stati sind Grün und OFFLINE/nicht aktive
  Stati Rot. Bei 40 Spalten werden die Verbindungsstati als `Ollama OK/OFF` und
  `OW Collector OK/OFF` verdichtet.
* **Aktuelle Runs**: Pi und Open WebUI senden auf getrennten Collector-Pfaden (`/v1/runs/pi`, `/v1/runs/open-webui`) mit demselben Bearer-Token. Quelle und Provider (etwa `Pi/OpenAI`, `Pi/Ollama`, `Open WebUI/Ollama`), Status, Modell und verfügbare Token-/Dauerwerte bleiben getrennt. Aktive Runs beider Quellen stehen vor frischen Ergebnissen; gleichartige Quellenblöcke zeigen jeweils `aktiv N · Ergebnis N`, ohne eine Quelle vorzuziehen. Ein Abschluss bleibt höchstens zehn Sekunden sichtbar und wird danach atomar aus `run.jsonl` entfernt, bleibt aber in der begrenzten Run-History erhalten. Bei mehr Runs als sichtbaren Zeilen ist der Bereich mit `a` und den Scrolltasten erreichbar. Verwaiste nicht-finale Live-Einträge werden nach 90 Sekunden ohne Lebenszeichen entfernt und nicht als aktuelle Runs angezeigt. Lange Streams senden regelmäßig Lebenszeichen. Schema-1-Daten bleiben als `Legacy` lesbar. Status, Modell, Kontextlimit und grafischer Kontextverbrauch (Prompt- plus Ausgabetoken),
  Prompt-/Ausgabe-/Gesamttoken und Ausgabe-Rate. `--chat` und `--generate`
  instrumentieren eigene direkte Ollama-Aufrufe ohne Reverse Proxy. Während
  des Streamings liefert Ollama keine Tokenwerte; bis zum Abschluss stehen sie
  daher als `n/a` da. Ohne Ereignis wird nichts geschätzt.
* **Geladene Modelle** (`/api/ps`): Name, Parametergröße, Quantisierung,
  `context_length`, Runner, Restzeit bis Auto-Unload (`expires_at`),
  `size_vram` / `size` → Aufteilung GPU % / CPU %. Der Ollama-Bereich ist in
  „Aktuelle Runs“ und „Geladene Modelle“ unterteilt.
* **CPU**: Gesamt-% aus `/proc/stat`-Differenz zwischen zwei Refreshes, dazu
  Load Average (`/proc/loadavg`), Kernanzahl (`os.cpu_count()`) und Temperatur
  aus `k10temp`, `coretemp` oder `zenpower`, sofern verfügbar.
* **RAM**: Auslastung `%`, Größe `GiB`, Zeile direkt nach CPU-Balken
  (aus `/proc/meminfo`).
* **GPU**: Auslastung %, Temperatur und VRAM-belegt/%. Quellenkette: zunächst `nvidia-smi`
  (via `subprocess`, Power W und Leistungsgrenze), bei fehlenden NVIDIA-Daten
  `/sys/class/drm/card*/device/gpu_busy_percent` (sysfs); sonst
  `keine GPU-Quelle gefunden`. `--no-nvidia` verwendet unmittelbar sysfs.
  Der Power-Balken verwendet mindestens die lokale Boost-Skala von 115 W;
  eine höhere gemeldete Leistungsgrenze hat Vorrang.
* **VRAM**: VRAM-Auslastung `%` und Größe in MiB
  (`VRAM [##########  ] 96.5 %  7864 / 8151 MiB`). Im Ollama-Bereich zeigt ein
  geteilter Balken die Modellaufteilung als „VRAM/RAM“: Der Modellname ist
  grau und unterstrichen; die folgenden Modellinformationen beginnen an einer
  verkürzten festen Tabulatorposition. Auch Quelle, Modell, Status und Metriken aktueller
  Runs sind per Tabulator ausgerichtet. Label und Klammern sind Cyan. VRAM ist oberhalb 55 % Grün,
  bei 45–55 % Gelb und darunter Rot. Der VRAM-Prozentwert steht auf derselben Flucht wie die Prozentwerte von System
  und GPU. Der CPU/RAM-Anteil bleibt ausschließlich als grauer Balkenanteil und
  in der gedimmten Größenangabe im Format `MiB / MiB` mit einmaliger Einheit sichtbar; ein zweiter
  RAM-Prozentwert wird nicht angezeigt.
  Der Kontextbalken aktueller Runs steht ausschließlich in der Kontextspalte.
  Prozentwert und Balken sind statusabhängig farbig; Verbrauch und Limit bleiben
  gedimmt grau. Tok/s aktueller Runs ist rot unter
  10, gelb von 10 bis unter 50 und grün ab 50 Tok/s; diese Tok/s-Farbe ist
  nicht fett.

## Open-WebUI-Adapter

Der Filter liegt in `open_webui/llmtop_run_metrics.py` und wird ausschließlich über die Open-WebUI-API installiert. Er überträgt über den eigenen Collector-Pfad verifizierte Modellprovider neutral; fehlende finale Usage bleibt sichtbar als `n/a`. Der TUI-Start aktualisiert auch bereits aktive ältere Filterversionen. Die lokale `.env` benötigt zusätzlich zu `LLMTOP_COLLECTOR_TOKEN` einen Admin-API-Key:

```dotenv
OPEN_WEBUI_URL=http://127.0.0.1:3000
OPEN_WEBUI_API_KEY=<Open-WebUI-Admin-API-Key>
```

Beim normalen TUI-Start prüft llmtop bei vorhandenem `OPEN_WEBUI_API_KEY` und
`LLMTOP_COLLECTOR_TOKEN` asynchron, ob der globale aktive Filter
`llmtop_run_metrics` installiert ist. Alte globale Adapter wie
`otop_run_metrics` werden dabei deaktiviert, damit ein Request nicht doppelt
registriert wird. Fehlt oder deaktiviert der Filter, wird ersatzweise die
bestehende Installationsroutine ausgeführt. Ohne vollständige
lokale Konfiguration und bei API-Fehlern bleibt der Start unverändert; `--once`
und die Skriptmodi führen keine Adapter-Änderung aus.

Danach genügt der normale TUI-Start; der Collector wird bei konfiguriertem
`LLMTOP_COLLECTOR_TOKEN` automatisch im Hintergrund gestartet:

```bash
python3 llmtop.py
python3 llmtop.py --install-open-webui-adapter
```

`--collector` bleibt für einen separat laufenden, blockierenden Dienstmodus
verfügbar.

Der Installationsbefehl erkennt die private Docker-Gateway-Adresse, setzt die Filter-Valves, aktiviert den Filter und schaltet ihn global. Der Filter überträgt ausschließlich Quelle, Provider, UUID, Modell, Zeit- und Nutzungswerte. Collector-Fehler werden abgefangen und beeinflussen die Chatantwort nicht. Die gleiche Schema-2-Schnittstelle verarbeitet auch den optionalen Pi-Adapter; der Kern benötigt dafür keine Pi-Abhängigkeit.

## Pi-Adapter

Der dependency-freie Adapter unter `pi/llmtop_run_metrics.ts` wird beim normalen TUI-Start automatisch nach `~/.pi/agent/extensions/` aktualisiert. Nach einem Update muss eine bereits laufende llmtop-TUI einmal mit `r` neu geladen werden, damit ihr Collector die getrennten Adapterpfade übernimmt. Dabei legt llmtop die Collector-URL und den Token ausschließlich mit Dateimodus `0600` unter `$XDG_STATE_HOME/llmtop/pi-collector.json` (Fallback `~/.local/state/llmtop/`) ab; neue Pi-Prozesse lesen diese private Laufzeitdatei automatisch. Für bereits laufende Pi-Prozesse einmal `/reload` ausführen oder Pi neu starten.

Er fasst alle Modell- und Tool-Folgeturns einer bearbeiteten Pi-Anfrage zu einem Live-Run zusammen. Erst wenn Pi den Agentenlauf als erledigt meldet, wird genau ein Datensatz für dessen finale Antwort in der Run-History gespeichert. Dabei werden Input-/Cache-/Ausgabetoken, Kontextlimit, Gesamtdauer und Ausgaberate übertragen. Der Session-Kontext wird während aktiver Runs aus Pi gelesen und höchstens einmal pro Sekunde als Tokenzahl aktualisiert; bekannte Provider-Usage ergänzt diese Werte. Unvollständige Zwischenmeldungen mit `0` überschreiben bereits bekannte Tokenstände nicht. Steht weder Session-Kontext noch Usage bereit, bleiben Tokenwerte bis dahin `n/a`. Er sendet ausschließlich Quelle, Provider, Modell, UUID, Zeit und Nutzungsmetriken. Prompt, Antwort, Tooldaten, Sessionpfade und Credentials bleiben lokal in Pi.

## Bekannte Grenzen

* Die Ollama-API selbst liefert **keine** CPU-/GPU-Auslastung (nur `size_vram`);
  `/metrics` gibt es hier nicht (404). GPU-Auslastung kommt vom **Host**, sie ist
  geräte-global und nicht exklusiv Ollama zurechenbar.
* Ollama läuft im Docker-Container; die GPU-Messung erfolgt am Host (NVIDIA-Binary
  `nvidia-smi` bzw. sysfs), nicht im Container.
* Der Collector lauscht standardmäßig auf `127.0.0.1:11435` und zusätzlich auf dem erkannten privaten Docker-Gateway von `open-webui`. Er benötigt `LLMTOP_COLLECTOR_TOKEN`; `.env.example` zeigt die lokalen Variablennamen.
* Run-Historien speichern nur IDs, Quelle, Modell, Status, Zeit- und Tokenzähler
  sowie optional Kontexttoken und Kontextlimit; keine Prompts oder Modellantworten.
  Das Kontextlimit wird bevorzugt aus dem Run (`options.num_ctx`) übernommen und
  ersatzweise aus dem aktuell geladenen Modell in `/api/ps` ergänzt. Open-WebUI
  liefert bei Ollama-Streaming echte Usage-Werte häufig erst im Abschluss;
  währenddessen zeigt llmtop deshalb einen eindeutigen Wartezustand statt Schätzungen.
* CPU-% ist ein Differenzwert über ein Refresh-Intervall — der erste Frame zeigt
  „Messung“.
* Ist `nvidia-smi` erfolgreich, werden sysfs-GPUs nicht zusätzlich gezeigt.
  Bei mehreren NVIDIA-GPUs werden alle von `nvidia-smi` gemeldeten Geräte gezeigt.
* Schlägt `/api/ps` fehl, zeigt die Anwendung den Fehler statt „kein Modell geladen“.
* Modelle ohne Scrollen: Passen nicht alle vollständigen Modellkarten in den
  verfügbaren Bereich, zeigt die TUI ihre Anzahl als ausgeblendet an; es gibt
  keinen Scroll-Modus.
* TUI braucht ein echtes Terminal (TTY). Ohne TTY: `--once` verwenden.
* Mindest-Terminalgröße 40×18. Darunter zeigt die TUI einen Hinweis, damit
  Fußzeile oder Bereiche nicht überdeckt werden.

## Testumgebung (live)

Ollama 0.40.6 im Docker-Container unter `http://localhost:11434`, GPU NVIDIA
RTX 5070 Laptop (8151 MiB) + AMD iGPU (`card2`), 24 Kerne, Python 3.12.
Aktueller Prüfstatus und bekannte Grenzen: siehe `status.md`.
