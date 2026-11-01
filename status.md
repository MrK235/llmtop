# status.md — llmtop

**Version 2.1.9** · Stand 01.11.2026 · Status: Pi-Live-Runs aktualisieren bekannte Usage während aktiver Streams.

## Aktueller Stand

`llmtop.py` ist der Programmeinstieg einer Python-Standardbibliotheks-Anwendung
mit curses-TUI und `--once`-Ausgabe. Die Datenerfassung liegt in
`llmtop_sources.py`, Run-Metriken, History und Collector in `llmtop_metrics.py`
sowie Rendering und TUI-Sampler in `llmtop_tui.py`. Die TUI zeigt die Bereiche
System, GPU, aktuelle Runs, geladene Modelle und History in dieser Reihenfolge. CPU, RAM, GPU, VRAM und Power verwenden
konsistente Balken, Abstände und eine globale Farbsyntax. Struktur ist Cyan,
Statuswerte und Temperaturen verwenden Grün/Gelb/Rot, Sekundärinfos sind
gedimmt. Ollama-Modelle zeigen einen geteilten Speicherbalken im gleichen
Raster wie die Sensoren: GPU/VRAM ist Grün oberhalb 55 %, Gelb bei 45–55 %
und Rot darunter; CPU/RAM bleibt gedimmt grau. Beide Anteile verwenden `#`.
CPU-Power wird nicht angezeigt, weil auf diesem Host keine zugängliche,
verlässliche Quelle existiert. History speichert begrenzte, datensparsame JSONL-Snapshots mit UTC-Zeitstempeln. Die Run-History hält bis zu 100 abgeschlossene Runs als scrollbare und sortierbare Tabelle vor; instrumentierte Runs enthalten optional Kontexttoken und Kontextlimit.
Aktive Run-Metriken können über einen token-geschützten lokalen HTTP-Collector
(`POST /v1/runs`) geliefert werden. Er verwaltet mehrere parallele Runs,
dedupliziert finale Einträge nach Quelle und Run-ID und zeigt die Quelle in TUI
und Historie. Schema-1-JSONL bleibt als `legacy` lesbar. Zusätzlich instrumentieren `--chat` und `--generate` eigene direkte
Ollama-Aufrufe ohne Reverse Proxy und schreiben einen finalen Run pro Aufruf in
eine getrennte, begrenzte JSONL-Historie. Während des Streamings sind keine
Ollama-Tokenmetriken verfügbar; sie werden erst aus dem finalen `done`-Objekt
gespeichert. Für dieses Layout gilt eine Mindestgröße von
40×18. Bei dieser Größe verwendet die TUI eine kompakte, überlappungsfreie
Darstellung mit System- und GPU-Kernwerten, Ollama-Status und History-Status.

## Neu in 2.1.9

- Pi sendet bekannte Provider-Usage während aktiver Streams höchstens einmal pro Sekunde sowie nach jedem Modellturn.
- Kontext und Tok/s werden dadurch bereits vor dem finalen Session-Abschluss aktualisiert.

## Neu in 2.1.8

- Bereits gespeicherte Doppelmeldungen mit identischen Open-WebUI-Metriken werden in der History dedupliziert.

## Neu in 2.1.7

- Veraltete globale `otop_run_metrics`-Adapter werden beim Adapter-Setup deaktiviert.
- Dadurch werden Open-WebUI-Runs nicht mehr doppelt an den Collector gesendet.

## Neu in 2.1.6

- Pi überträgt Cache-Input zum Kontextverbrauch, das Modell-Kontextlimit sowie Gesamtdauer und Ausgaberate.
- Ollama-Pi-Runs zeigen dadurch Tok/s und Dauer; ChatGPT-Pi-Runs zeigen Kontextgröße, Prozent und Tok/s.

## Neu in 2.1.5

- Der Pi-Adapter fasst alle Modell- und Tool-Folgeturns einer bearbeiteten Anfrage zu einem Live-Run zusammen.
- Erst der finale `agent_settled`-Abschluss schreibt das Ergebnis der sichtbaren Antwort in die Run-History.

## Neu in 2.1.4

- Finale Live-Runs laufen zehn Sekunden nach `finished_at` ab und werden atomar aus `run.jsonl` bereinigt; die begrenzte Run-History bleibt erhalten.
- Aktive Pi- und Open-WebUI-Runs stehen vor Ergebnissen und werden in gleichartigen Quellenblöcken mit sichtbaren Zählern dargestellt.

## Neu in 2.1.3

- Ein neuer Pi- oder WebUI-Run entfernt den letzten Abschluss derselben Quelle nicht mehr aus der Live-Anzeige.
- Aktuelle Runs priorisieren Pi vor WebUI und kennzeichnen Quelle getrennt nach aktiv und erledigt.

## Neu in 2.1.2

- Pi und Open WebUI senden auf getrennte Collector-Pfade; der Collector erzwingt die passende Quelle.
- Letzte Abschlüsse bleiben je Quelle in der Live-Datei erhalten, und die Kompaktansicht sowie schmale History zeigen die Quelle zwingend.
- Aktive ältere Open-WebUI-Filter werden anhand ihres Inhalts erkannt und beim TUI-Start aktualisiert.

## Neu in 2.1.1

- Normaler TUI-Start installiert oder aktualisiert den globalen Pi-Adapter und schreibt dessen private Collector-Laufzeitdaten mit Modus `0600` unter dem bestehenden llmtop-State-Pfad.
- Neue Pi-Prozesse benötigen keine manuell exportierten Collector-Variablen mehr; bereits laufende Instanzen werden einmal neu geladen oder gestartet.

## Neu in 2.1.0

- Pi-Adapter meldet lokale und Cloud-Modellturns datensparsam über den bestehenden Collector.
- Run-Schema, TUI, `--once` und History unterscheiden Quelle und optionalen Provider; parallele Runs bleiben erhalten und der aktive Bereich ist scrollbar.
- Open-WebUI-Filter überträgt verifizierte Provider nicht mehr nur für Ollama.

## Neu in 2.0.7

- Intervallanzeige mit der `-/+`-Legende rechtsbündig in die Statusleiste
  verschoben.

## Neu in 2.0.6

- „LLM Terminal Monitor“ in jeder gültigen Terminalbreite horizontal mittig
  in der ersten Kopfzeile platziert.

## Neu in 2.0.5

- Kopf-Logo als Terminalfenster gestaltet: Prompt, Aktivitätspixel und
  LLM-Kennung verbinden den Monitor mit seinem Einsatzzweck.

## Neu in 2.0.4

- Logo auf acht Zeichen Breite erweitert, damit es im üblichen Terminalraster
  optisch quadratisch erscheint.
- Zwei freie Spalten zwischen Logo und Kopftext ergänzt.

## Neu in 2.0.3

- Vierzeiliges Kopf-Icon durch ein quadratisches Pixel-Logo ersetzt.
- Leerzeile nach dem Kopf ergänzt und die Ollama-Version direkt an den Namen
  gesetzt.

## Neu in 2.0.2

- Kopfbereich als vierzeilige Produktidentität mit Pixel-Icon, Version,
  Verbindungsstati, Autor, Technik und Refresh-Intervall gestaltet.
- Die 40×18-Kompaktansicht lässt VRAM- und Power-Zeilen weg, damit der größere
  Kopf ohne Überlappung Platz findet.

## Neu in 2.0.1

- Normaler TUI-Start prüft den global aktiven Open-WebUI-Filter asynchron und
  installiert ihn bei Fehlen oder Deaktivierung automatisch.
- Ohne vollständige lokale Konfiguration, bei API-Fehlern sowie in `--once`-
  und Skriptmodi bleibt die Adapter-Konfiguration unverändert.

## Neu in 2.0.0

- Harter Namenswechsel von otop zu llmtop: Kommando, Python-Module,
  Open-WebUI-Filter, `LLMTOP_*`-Umgebungsvariablen und State-Pfad sind umgestellt.
- Kopfzeile und `--once` verwenden das neue Pixel-Icon.
- Alte otop-Dateien, Variablen und State-Pfade werden nicht mehr unterstützt;
  der neue Open-WebUI-Filter muss einmal installiert werden.

## Korrekturen in 1.10.12

- Namen Ollama und Open-WebUI Collector in der Kopfzeile gedimmt grau gesetzt.
- Redundanten Ollama-Abschnitt samt Collector-Zeile entfernt.

## Korrekturen in 1.10.11

- Collector als „Open-WebUI Collector“ bezeichnet.
- Namen der Verbindungen Cyan, aktive Stati Grün und nicht aktive Stati Rot.

## Neu in 1.10.10

- Kopfzeile zeigt Ollama- und Collector-Verbindungsstatus, auch verdichtet bei
  schmalem Terminal.
- TUI-Standardintervall auf 0,5 s und Untergrenze auf 0,2 s gesetzt.

## Korrekturen in 1.10.9

- Bereichslinien beginnen in Spalte 0; alle Inhalte haben einen Zeichenabstand links.
- Tabulatorposition zwischen Modellname und Metadaten auf 16 Spalten verkürzt.

## Korrekturen in 1.10.8

- Tok/s-Farben ohne Fettdruck dargestellt.

## Korrekturen in 1.10.7

- Nur der VRAM-Prozentwert bleibt farbig; `/RAM%` und Größen bleiben grau.
- Tok/s aktueller Runs ist rot unter 10, gelb unter 50 und grün ab 50 Tok/s.

## Korrekturen in 1.10.6

- Modell-VRAM/RAM zeigt nach dem Balken erst die Prozentwerte `%/%` und danach
  gedimmt die VRAM- und RAM-Größen in GiB.

## Korrekturen in 1.10.5

- Kontextanzeige auf das Raster von CPU und GPU ausgerichtet: Prozentwert
  rechtsbündig nach dem Balken, Verbrauch/Limit gedimmt grau danach.

## Korrekturen in 1.10.4

- Kontextanzeige aktueller Runs zeigt Prozent vor Verbrauch und Limit.
- Bereichsüberschriften sind eingerückt und besitzen Linien vor und nach dem Titel.

## Korrekturen in 1.10.3

- Modellnamen grau und unterstrichen dargestellt.
- Aktuelle Runs verwenden Tabulatoren für Quelle, Modell, Status und Metriken.

## Korrekturen in 1.10.2

- Modellnamen wieder Cyan und unterstrichen dargestellt.
- Folgende Modellinformationen beginnen an einer festen Tabulatorposition.

## Korrekturen in 1.10.1

- Kontextlabel vor dem Balken auf Cyan statt Dunkelgrün gesetzt.
- Kleinere Änderungen erhöhen künftig standardmäßig nur die Patchversion.

## Neu in 1.10.0

- Modell-Speicheranzeige unter „Geladene Modelle“ als VRAM/RAM beschriftet.
- Modellnamen sind grau und unterstrichen; das Kontextlabel vor seinem Balken ist Cyan.

## Neu in 1.9.0

- Der letzte abgeschlossene aktuelle Run bleibt mit seinen finalen Token- und
  Zeitwerten sichtbar, bis ein neuer Run beginnt.
- Finale Ereignisse ergänzen zuvor bekannte Start- und Kontextwerte vor der
  Persistierung in die Run-History.

## Korrekturen in 1.8.8

- TUI-Start mit Run-History inklusive Tokenwerten repariert: `total_tokens`
  wird im herausgelösten curses-Modul wieder aus den Metriken importiert.

## Korrekturen in 1.8.7

- TUI-Start mit geladenem Modell repariert: `datetime` für die Unload-Zeit ist
  im herausgelösten curses-Modul wieder verfügbar.

## Korrekturen in 1.8.6

- TUI-Start mit vorhandener Run-History repariert: `_parse_time` wird im
  herausgelösten curses-Modul wieder aus den Metriken importiert.

## Neu in 1.8.5

- Sensoren, Ollama-Zugriffe, Run-Metriken/Collector und curses-TUI sind in drei
  überschaubare Kernmodule aufgeteilt; `llmtop.py` bleibt der kompatible Einstieg.
- Die TUI erfasst Daten in einem einzelnen Hintergrund-Thread. HTTP-,
  `nvidia-smi`-, sysfs- und History-Schreibzugriffe blockieren die Tastatur und
  das Rendering nicht mehr.
- Schema-2-Ereignisse mit Quelle `pi` werden durch denselben Collector wie Open
  WebUI verarbeitet und sind damit für den späteren optionalen Pi-Adapter
  vorbereitet.

## Korrekturen in 1.8.4

- Die Unterstreichung der aktiven Sortierspalte endet direkt mit dem Spaltentext und umfasst keine Auffüllung mehr.
- Zwischen History-Tabelle und Statusleiste bleibt eine vollständig leere Zeile; die 40×18-Ansicht fasst dafür Modell- und Run-Anzahl in einer Zeile zusammen.

## Korrekturen in 1.8.3

- Die Kontextzelle zeigt den Prozentwert vor Verbrauch und Limit, zum Beispiel `33% 10.9k/32.8k`.
- Die History-Überschrift enthält keine redundante Sortieranzeige mehr; stattdessen ist der aktive Spaltenkopf unterstrichen und trägt den Richtungspfeil.

## Korrekturen in 1.8.2

- Die History-Spalte Kontext wird nach dem tatsächlichen prozentualen Verbrauch sortiert, nicht nach der absoluten Zahl genutzter Token; Einträge ohne Limit folgen zuletzt.
- Die aktive Sortierspalte ist direkt im Tabellenkopf mit `▾` oder `▴` markiert.

## Korrekturen in 1.8.1

- TUI-Abbruch nach Start oder bei History-Navigation behoben: `curses.KEY_TAB` ist nicht auf allen Python-curses-Versionen vorhanden; die Tab-Taste verwendet nun den portablen Code `9`.

## Neu in 1.8.0

- Die Run-History ist eine scrollbare TUI-Tabelle für bis zu 100 finale Einträge und kann nach allen angezeigten Spalten sortiert werden.
- Die Kontextspalte zeigt Verbrauch, Limit und Prozentwert beziehungsweise transparent `n/a`; fehlende Werte werden beim Sortieren zuletzt geführt.
- Die bestehende begrenzte JSONL-Datei bleibt die Datenquelle. Eine Datenbank ist für höchstens 100 kleine, atomar geschriebene Einträge nicht erforderlich.

## Korrekturen in 1.7.4

- Wiederholte `request`-Filteraufrufe derselben Open-WebUI-Nachricht erzeugen bei Tool- und Fortsetzungsrunden keinen zusätzlichen aktuellen Run mehr.
- Parallele Open-WebUI-Anfragen mit unterschiedlichen Nachrichten-Identitäten bleiben weiterhin getrennte Runs; API-Aufrufe ohne stabile Identität werden nicht pauschal zusammengeführt.

## Korrekturen in 1.7.3

- Aktive Runs werden nach 90 Sekunden ohne Update als verwaist entfernt; lange Tool-Use-Anfragen senden während des Streams regelmäßig Lebenszeichen und werden dadurch nicht fälschlich entfernt.
- Verwaiste Live-Einträge erscheinen nicht mehr unter „Aktuelle Runs“ und werden nicht historisiert.
- Parallele Collector-Schreibzugriffe auf Live- und Run-History-Dateien sind synchronisiert; abgeschlossene Runs können nicht mehr durch konkurrierende Updates wieder auftauchen.
- Der Open-WebUI-Adapter ordnet Runs bei fehlender oder widersprüchlicher Identität nicht spekulativ einem anderen parallelen Tool-Use-Run zu.

## Korrekturen in 1.7.2

- Die Run-History rendert bis zu zehn abgeschlossene Runs statt nur des jüngsten.
- Der Open-WebUI-Adapter finalisiert einen Run nicht mehr automatisch als `cancelled`, wenn nur der Request-/Stream-Kontext endet; echte Abbrüche werden ausschließlich über explizite Abbruchsignale übernommen.
- Aktive Runs bleiben bis zum finalen Stream- oder Outlet-Ereignis in der Live-Datei.

## Vorherige technische Korrekturen (1.1.0)

- `/api/ps`-Fehler werden nicht mehr gleichzeitig als „kein Modell geladen“
dargestellt.
- Nicht-numerische NVIDIA-Auslastung wird als `n/a` angezeigt statt eine
Formatierungs-Ausnahme in der TUI auszulösen.
- Ein nicht erfolgreicher `nvidia-smi`-Prozess liefert keine scheinbaren
Messwerte; bei fehlenden NVIDIA-Daten erfolgt der sysfs-Fallback.
- `--no-nvidia` verwendet sysfs und behält dort AMD- und Intel-Geräte bei.
Mehrere NVIDIA-Geräte werden nicht mehr verworfen.
- VRAM-Werte werden intern einheitlich in MiB ausgegeben: `nvidia-smi` liefert
bereits MiB, sysfs-Werte werden von Bytes umgerechnet.
- CPU-Auslastung wird pro Refresh-Intervall berechnet.
- VRAM- und Power-Zeilen erscheinen in TUI und `--once`; der Hilfe-Dialog zeigt
nun auch seinen Text.
- Docstring und Projektdokumentation verweisen nur auf tatsächlich verwendete
Ollama-Endpunkte beziehungsweise vorhandene Dateien.

## Weiterhin bekannte Grenzen

- Der Kontextbalken verwendet Prompt- plus Ausgabetoken. Das Limit stammt aus `options.num_ctx` oder wird für passende Runs zuverlässig aus `context_length` des aktuell geladenen Modells in `/api/ps` übernommen und in der Run-History nachgetragen. Ein serverseitiger KV-Cache ist nicht separat sichtbar. Wenn der Provider Usage bereits während des Streams liefert, wird der Liveverbrauch aktualisiert; andernfalls bleibt er bis zum Abschluss unbekannt.

- GPU-Auslastung ist geräteweit und nicht exklusiv Ollama zurechenbar.
- `nvidia-smi` und sysfs werden als Fallback, nicht parallel, abgefragt.
- Für Modellkarten gibt es keinen Scroll-Modus. Passen sie nicht vollständig
  in den verfügbaren Bereich, zeigt die TUI ihre Anzahl als ausgeblendet an;
  die Run-History ist unabhängig davon scrollbar.
- Power-Limits sind nur verfügbar, wenn die jeweilige Quelle sie meldet.
- Die TUI zeigt während einer langsamen Quelle den letzten vollständigen
  Snapshot. Der Hintergrund-Sampler selbst wartet weiterhin auf den jeweiligen
  HTTP- oder `nvidia-smi`-Timeout; es gibt bewusst noch keine Parallelabfragen.
- Git ist im Projektverzeichnis initialisiert; Entwicklungsbranch ist `master`.
- Der direkte Client-Modus instrumentiert nur Aufrufe, die über `llmtop` selbst
  erfolgen; fremde Ollama-Clients bleiben ohne Adapter unsichtbar.
- Der Open-WebUI-Adapter wird mit `--install-open-webui-adapter` per Admin-API
  installiert, konfiguriert und global aktiviert. Dafür muss ausschließlich
  `OPEN_WEBUI_API_KEY` in der lokalen llmtop-`.env` gesetzt sein. Der Pi-Adapter
  ist weiterhin offen.

## Prüfung am 31.10.2026

- Pseudo-TTY-Prüfung: Bei 120×40 erscheinen Tabellenkopf, Sortierstatus und Kontextspalte; bei 40×18 bleibt die kompakte Tabellenansicht sichtbar. Normaler `q`-Exit ist auf beiden Größen Code 0.
- Sortier- und Kontexttests: alle acht Spalten, fehlende Werte und 100 geladene Historieneinträge erfolgreich.
- Visuelles Live-Debugging mit drei `request`-Aufrufen derselben Open-WebUI-Identität: Die Anzeige blieb durchgehend bei genau einem aktuellen Run; das finale Outlet entfernte ihn und erzeugte genau einen History-Eintrag.
- Vor dem 2.0-Umstieg waren installierter Open-WebUI-Filter und lokale Version
  `1.3.2` identisch. Der neue llmtop-Filter trägt `2.0.0` und wird separat
  installiert; ein echter Streaming-Aufruf über `/api/chat/completions` zeigte
  zuvor maximal einen Live-Eintrag.
- Run-History zeigt in `--once` zehn Einträge; bestehende ältere `cancelled`-Einträge bleiben als historische Altdaten unverändert.
- Lokaler und global installierter Open-WebUI-Adapter sind identisch, aktiv und global aktiviert; der Disconnect-Watcher ist entfernt.
- `python3 llmtop.py --install-open-webui-adapter`: erfolgreich.
- `python3 -m py_compile`, beide llmtop-Testmodule, `--once`, `--once --no-nvidia` und `--version`: erfolgreich.
- Paralleler Live-Run-Test: keine verwaisten Einträge nach konkurrierenden Start-/Abschlussupdates.


- `python3 -m py_compile llmtop.py`: OK.
- `python3 llmtop.py --version`: `llmtop 2.0.1`.
- `python3 llmtop.py --once` und `--once --no-nvidia`: OK.
- Mock-Rendering: 0/100-, 44/56-, 50/50-, 56/44-, 100/0- und fehlende
  Speichergrößen nutzen erwartete Segmentbreiten, Offload-Farben,
  Übergangsmarker sowie gedimmtes `n/a`: OK.
- Pseudo-TTY mit Beenden: OK; bei 80×24 vollständige Ansicht, bei 40×18 kompakte Ansicht ohne überzeichnete Modell- oder History-Zeilen.
- Git-Repository: initialisiert, Arbeitsbaum vor dem ersten Commit ungeordnet.
- Open-WebUI-Filtertest: Start, finaler Stream-Chunk, Outlet-Deduplizierung,
  parallele Metadaten-Schlüssel und datensparsame Ereignisse: OK.
- Container-Netz geprüft: `open-webui` nutzt `ai-net`, Gateway `172.18.0.1`.
- API-Installation mit lokalem Admin-Key: Filter `llmtop_run_metrics` erfolgreich
  angelegt, Valves gesetzt sowie aktiv und global geschaltet.
- Live-Chat über `/api/chat/completions` mit `qwen3.5:4b`: HTTP 200, ein
  finaler `open-webui`-Run mit Prompt- und Ausgabe-Token in `runs.jsonl`.
  Die von Open WebUI durchgereichte finale Datenform enthielt keine
  Gesamtdauer; sie bleibt erwartungsgemäß `n/a`.
- Collector-Test mit `started` und `completed`: HTTP 202, aktiver Run entfernt,
  finaler Schema-2-Eintrag inklusive Quelle und umgerechneter Dauern gespeichert.
- Direkter Live-Test: `--chat` gegen `qwen3.5:4b` lieferte finale
  `prompt_eval_count`, `eval_count` sowie Dauerwerte; der Abschlusslauf wurde
  in `runs.jsonl` geschrieben.

Eine visuelle Kontrolle in einem echten interaktiven Terminal bleibt sinnvoll.
