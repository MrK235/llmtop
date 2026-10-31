# status.md — otop

**Version 1.10.9** · Stand 01.11.2026 · Status: Linker Inhaltsrand, durchgehende Bereichslinien und kompaktere Modellmetadaten.

## Aktueller Stand

`otop.py` ist der Programmeinstieg einer Python-Standardbibliotheks-Anwendung
mit curses-TUI und `--once`-Ausgabe. Die Datenerfassung liegt in
`otop_sources.py`, Run-Metriken, History und Collector in `otop_metrics.py`
sowie Rendering und TUI-Sampler in `otop_tui.py`. Die TUI zeigt die Bereiche System, GPU, Ollama und
History in dieser Reihenfolge. CPU, RAM, GPU, VRAM und Power verwenden
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
  überschaubare Kernmodule aufgeteilt; `otop.py` bleibt der kompatible Einstieg.
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

- Der Kontextbalken verwendet Prompt- plus Ausgabetoken. Das Limit stammt aus `options.num_ctx` oder wird für passende Runs zuverlässig aus `context_length` des aktuell geladenen Modells in `/api/ps` übernommen und in der Run-History nachgetragen. Ein serverseitiger KV-Cache oder ein exakter Liveverbrauch ist nicht sichtbar; während des Streamings bleibt der Verbrauchswert daher unbekannt.

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
- Der direkte Client-Modus instrumentiert nur Aufrufe, die über `otop` selbst
  erfolgen; fremde Ollama-Clients bleiben ohne Adapter unsichtbar.
- Der Open-WebUI-Adapter wird mit `--install-open-webui-adapter` per Admin-API
  installiert, konfiguriert und global aktiviert. Dafür muss ausschließlich
  `OPEN_WEBUI_API_KEY` in der lokalen otop-`.env` gesetzt sein. Der Pi-Adapter
  ist weiterhin offen.

## Prüfung am 31.10.2026

- Pseudo-TTY-Prüfung: Bei 120×40 erscheinen Tabellenkopf, Sortierstatus und Kontextspalte; bei 40×18 bleibt die kompakte Tabellenansicht sichtbar. Normaler `q`-Exit ist auf beiden Größen Code 0.
- Sortier- und Kontexttests: alle acht Spalten, fehlende Werte und 100 geladene Historieneinträge erfolgreich.
- Visuelles Live-Debugging mit drei `request`-Aufrufen derselben Open-WebUI-Identität: Die Anzeige blieb durchgehend bei genau einem aktuellen Run; das finale Outlet entfernte ihn und erzeugte genau einen History-Eintrag.
- Installierter Open-WebUI-Filter und lokale Version sind identisch (`1.3.2`), aktiv und global. Ein echter Streaming-Aufruf über `/api/chat/completions` zeigte maximal einen Live-Eintrag.
- Run-History zeigt in `--once` zehn Einträge; bestehende ältere `cancelled`-Einträge bleiben als historische Altdaten unverändert.
- Lokaler und global installierter Open-WebUI-Adapter sind identisch, aktiv und global aktiviert; der Disconnect-Watcher ist entfernt.
- `python3 otop.py --install-open-webui-adapter`: erfolgreich.
- `python3 -m py_compile`, beide otop-Testmodule, `--once`, `--once --no-nvidia` und `--version`: erfolgreich.
- Paralleler Live-Run-Test: keine verwaisten Einträge nach konkurrierenden Start-/Abschlussupdates.


- `python3 -m py_compile otop.py`: OK.
- `python3 otop.py --version`: `otop 1.10.9`.
- `python3 otop.py --once` und `--once --no-nvidia`: OK.
- Mock-Rendering: 0/100-, 44/56-, 50/50-, 56/44-, 100/0- und fehlende
  Speichergrößen nutzen erwartete Segmentbreiten, Offload-Farben,
  Übergangsmarker sowie gedimmtes `n/a`: OK.
- Pseudo-TTY mit Beenden: OK; bei 80×24 vollständige Ansicht, bei 40×18 kompakte Ansicht ohne überzeichnete Modell- oder History-Zeilen.
- Git-Repository: initialisiert, Arbeitsbaum vor dem ersten Commit ungeordnet.
- Open-WebUI-Filtertest: Start, finaler Stream-Chunk, Outlet-Deduplizierung,
  parallele Metadaten-Schlüssel und datensparsame Ereignisse: OK.
- Container-Netz geprüft: `open-webui` nutzt `ai-net`, Gateway `172.18.0.1`.
- API-Installation mit lokalem Admin-Key: Filter `otop_run_metrics` erfolgreich
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
