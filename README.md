# otop — Ollama Terminal Monitor mit GPU-, RAM- und VRAM-Sensoren

**Version 1.10.8 · Python-Terminal-Anwendung (nur Python-Standardbibliothek),
die über die Ollama-API das **geladene Modell** sowie **CPU-/RAM/GPU-Auslastung**
anzeigt. Versionsgeschichte und Versionsschema: `version.md`.

Die Version wird angezeigt: in der TUI-Kopfzeile (`otop 1.10.8 • Ollama …`), in der
ersten Zeile von `--once`, und über `--version`. Maßgebliche Zahl ist `VERSION`
in `otop.py`.

## Dateien

| Datei | Inhalt |
|-------|--------|
| `otop.py` | Programmeinstieg, CLI und Snapshot-Modus |
| `otop_sources.py` | Ollama-, CPU-, RAM- und GPU-Datenerfassung |
| `otop_metrics.py` | Run-Schema, JSONL-Historie, Collector und Open-WebUI-Integration |
| `otop_tui.py` | curses-Rendering und TUI-Hintergrundsampler |
| `README.md` | diese Anleitung |
| `status.md` | Projektstand, bekannte Grenzen und Prüfhinweise |
| `version.md` | Versionsschema, Versionsanzeige, Changelog |
| `.gitignore` | lokale Python-Artefakte ausschließen |
| `plan/` | akzeptierte Arbeitspläne (Plan-Mode-Artefakte) |

## Versionierung

Das Projekt ist als Git-Repository eingerichtet. Der aktuelle Branch ist
`master`. Code, Dokumentation und akzeptierte
Pläne werden gemeinsam versioniert. Vor einem Commit: Tests aus `status.md`
ausführen, `VERSION` sowie `README.md`, `status.md` und `version.md` abgleichen.
Tags verwenden das Format `vX.Y.Z`.

## Start

```bash
python3 otop.py                      # Vollbild-TUI (curses), Refresh alle 2 s
python3 otop.py --interval 1         # TUI mit 1 s Refresh
python3 otop.py --once               # ein Einzel-Snapshot (Skripte / kein Terminal)
python3 otop.py --host http://127.0.0.1:11434
python3 otop.py --chat '{"model":"qwen3.5:4b","messages":[{"role":"user","content":"Hallo"}]}'
python3 otop.py --collector          # Loopback und privates Open-WebUI-Docker-Gateway
python3 otop.py --install-open-webui-adapter  # Filter per Open-WebUI-API installieren
python3 otop.py --emit event.json    # Schema-2-Testevent an den Collector senden
python3 otop.py --no-nvidia          # nvidia-smi überspringen (sysfs-Pfad)
python3 otop.py --version            # Versionsnummer, danach Exit 0 (kein TUI)
```

`$OLLAMA_HOST` wird als Default übernommen; `--host` ohne Protokoll wird zu
`http://<host>`. Für einen optionalen, ausschließlich lesenden Open-WebUI-
Datenbank-Fallback kann `OTOP_OPEN_WEBUI_DB` auf einen zugänglichen Pfad zu
`webui.db` gesetzt werden. Ohne stabile Zuordnung werden keine Daten ergänzt.

| Option | Verhalten |
|--------|-----------|
| `--host` | Ollama-URL; Default `$OLLAMA_HOST`, sonst `http://localhost:11434` |
| `--interval` | Refresh-Sekunden im TUI; Default 2 s, **auf 0.5–60 s begrenzt** (`--interval 0.1` → 0.5 s) |
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
| `-` | Intervall halbieren (min. 0.5 s) |
| `+` / `=` | Intervall verdoppeln (max. 60 s) |
| `Tab` / `Shift-Tab` | nächste / vorherige Sortierspalte der Run-History |
| `s` / `S` | Sortierrichtung der Run-History umschalten |
| `↑` / `↓`, `Bild↑` / `Bild↓`, `Pos1` / `Ende` | Run-History scrollen |

## TUI-Layout

Die Vollbildansicht gliedert sich von oben nach unten in **System**, **GPU**,
**Ollama** und **History**. Bereichsüberschriften sind eingerückt und von
horizontalen Linien vor und nach dem Titel eingerahmt. Bei 40×18 verwendet sie eine kompakte Ansicht mit
Kernwerten, Modellanzahl und History-Status, damit sich keine Bereiche überzeichnen.
CPU, RAM, GPU-Auslastung, VRAM und Power verwenden
pro Terminal dieselbe Balkenbreite; Label, Prozentwert und Detailwert sind
spaltenweise ausgerichtet. Die Farbsyntax ist global: Struktur (Überschriften,
Labels und Rahmen) ist Cyan, Auslastungs- und Temperaturstatus Grün/Gelb/Rot,
Sekundärinfos gedimmt. Im Ollama-Speicherbalken bedeuten die Farben explizit
den Offload-Grad der GPU/VRAM-Anzeige: Grün oberhalb 55 %, Gelb bei 45–55 %
und Rot unterhalb 45 % GPU-Anteil. CPU/RAM bleibt gedimmt grau. Beide Anteile
nutzen `#` und zeigen zusätzlich Textwerte. Eine
Leerzeile trennt jeweils System, GPU, Ollama und History. **History** zeigt
eine scrollbare Tabelle mit bis zu 100 abgeschlossenen instrumentierten Runs.
Sie kann nach Abschlusszeit, Quelle, Modell, Status, Tokens, Kontextverbrauch,
Ausgaberate und Dauer sortiert werden. Die aktive Sortierspalte ist im
Tabellenkopf exakt über die Länge ihres Textes unterstrichen und mit `▾`
beziehungsweise `▴` markiert; die History-Überschrift bleibt frei von
Sortierdetails. Eine Leerzeile trennt die History von der Statusleiste.
Kontext wird nach dem prozentualen Verbrauch sortiert, nicht nach der absoluten
Tokengröße. Die Kontextspalte zeigt zuerst den Prozentwert und danach genutzte
Token sowie das Limit; fehlende Providerwerte bleiben `n/a`. Die Daten bleiben
als begrenzte JSONL-Datei gespeichert; eine Datenbank ist bei 100 Einträgen
nicht nötig. Zusätzlich speichert otop lokale, begrenzte System-Snapshots. Der
Snapshot-Pfad kann über `OTOP_HISTORY_FILE`, die Run-Historie über
`OTOP_RUN_HISTORY_FILE` oder `XDG_STATE_HOME` angepasst werden.

## Angezeigte Werte

* **Kopfzeile**: `otop <VERSION>`, Ollama-Version und Erreichbarkeit
  (`/api/version`), `verbunden` / `OFFLINE` sowie bei ausreichender Breite das
  Refresh-Intervall; bei 40 Spalten wird sie gezielt verdichtet.
* **Aktuelle Runs**: bis zu drei aktive Schema-2-Runs aus `OTOP_RUN_FILE`, jeweils mit Quelle (`Pi`, `Open WebUI`, `Ollama CLI`), Status, Modell und verfügbaren Token-/Dauerwerten. Nach dem Abschluss bleibt der letzte Run mit den finalen Token- und Zeitwerten sichtbar, bis ein neuer Run startet. Eine Open-WebUI-Chat-Anfrage bleibt auch bei internen Tool- oder Fortsetzungsrunden genau ein aktueller Run. Verwaiste nicht-finale Live-Einträge werden nach 90 Sekunden ohne Lebenszeichen entfernt und nicht als aktuelle Runs angezeigt. Lange Streams senden regelmäßig Lebenszeichen. Schema-1-Daten bleiben als `Legacy` lesbar. Status, Modell, Kontextlimit und grafischer Kontextverbrauch (Prompt- plus Ausgabetoken),
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
  festen Tabulatorposition. Auch Quelle, Modell, Status und Metriken aktueller
  Runs sind per Tabulator ausgerichtet. Label und Klammern sind Cyan. VRAM ist oberhalb 55 % Grün,
  bei 45–55 % Gelb und darunter Rot. Nach dem Balken stehen zuerst die
  VRAM/RAM-Prozentwerte im Format `%/%`; nur der VRAM-Wert ist farbig, der
  Trennstrich samt RAM-Wert sowie beide Größen sind gedimmt grau in GiB. Beide
  Anteile verwenden `#`.
  Das Label „Kontext“ vor dem Balken eines aktuellen Runs ist Cyan. Die
  Kontextanzeige folgt dem CPU-/GPU-Raster: Balken, rechtsbündiger Prozentwert
  und danach gedimmt grau Verbrauch/Limit. Tok/s aktueller Runs ist rot unter
  10, gelb von 10 bis unter 50 und grün ab 50 Tok/s; diese Tok/s-Farbe ist
  nicht fett.

## Open-WebUI-Adapter

Der Filter liegt in `open_webui/otop_run_metrics.py` und wird ausschließlich über die Open-WebUI-API installiert. Die lokale `.env` benötigt zusätzlich zu `OTOP_COLLECTOR_TOKEN` einen Admin-API-Key:

```dotenv
OPEN_WEBUI_URL=http://127.0.0.1:3000
OPEN_WEBUI_API_KEY=<Open-WebUI-Admin-API-Key>
```

Danach genügt der normale TUI-Start; der Collector wird bei konfiguriertem
`OTOP_COLLECTOR_TOKEN` automatisch im Hintergrund gestartet:

```bash
python3 otop.py
python3 otop.py --install-open-webui-adapter
```

`--collector` bleibt für einen separat laufenden, blockierenden Dienstmodus
verfügbar.

Der Installationsbefehl erkennt die private Docker-Gateway-Adresse, setzt die Filter-Valves, aktiviert den Filter und schaltet ihn global. Der Filter überträgt ausschließlich Quelle, UUID, Modell, Zeit- und Nutzungswerte. Collector-Fehler werden abgefangen und beeinflussen die Chatantwort nicht. Die gleiche Schema-2-Schnittstelle (`POST /v1/runs`, `source: "pi"`) ist für einen optionalen Pi-Adapter vorgesehen; der Kern benötigt dafür keine Pi-Abhängigkeit.

## Bekannte Grenzen

* Die Ollama-API selbst liefert **keine** CPU-/GPU-Auslastung (nur `size_vram`);
  `/metrics` gibt es hier nicht (404). GPU-Auslastung kommt vom **Host**, sie ist
  geräte-global und nicht exklusiv Ollama zurechenbar.
* Ollama läuft im Docker-Container; die GPU-Messung erfolgt am Host (NVIDIA-Binary
  `nvidia-smi` bzw. sysfs), nicht im Container.
* Der Collector lauscht standardmäßig auf `127.0.0.1:11435` und zusätzlich auf dem erkannten privaten Docker-Gateway von `open-webui`. Er benötigt `OTOP_COLLECTOR_TOKEN`; `.env.example` zeigt die lokalen Variablennamen.
* Run-Historien speichern nur IDs, Quelle, Modell, Status, Zeit- und Tokenzähler
  sowie optional Kontexttoken und Kontextlimit; keine Prompts oder Modellantworten.
  Das Kontextlimit wird bevorzugt aus dem Run (`options.num_ctx`) übernommen und
  ersatzweise aus dem aktuell geladenen Modell in `/api/ps` ergänzt. Open-WebUI
  liefert bei Ollama-Streaming echte Usage-Werte häufig erst im Abschluss;
  währenddessen zeigt otop deshalb einen eindeutigen Wartezustand statt Schätzungen.
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
