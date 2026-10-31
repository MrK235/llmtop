# status.md — otop

**Version 1.7.3** · Stand 31.10.2026 · Status: Live-Run-Bereinigung und parallele Collector-Schreibzugriffe korrigiert.

## Aktueller Stand

`otop.py` ist eine einzelne Python-Standardbibliotheks-Anwendung mit curses-TUI
und `--once`-Ausgabe. Die TUI zeigt die Bereiche System, GPU, Ollama und
History in dieser Reihenfolge. CPU, RAM, GPU, VRAM und Power verwenden
konsistente Balken, Abstände und eine globale Farbsyntax. Struktur ist Cyan,
Statuswerte und Temperaturen verwenden Grün/Gelb/Rot, Sekundärinfos sind
gedimmt. Ollama-Modelle zeigen einen geteilten Speicherbalken im gleichen
Raster wie die Sensoren: GPU/VRAM ist Grün oberhalb 55 %, Gelb bei 45–55 %
und Rot darunter; CPU/RAM bleibt gedimmt grau. Beide Anteile verwenden `#`.
CPU-Power wird nicht angezeigt, weil auf diesem Host keine zugängliche,
verlässliche Quelle existiert. History speichert begrenzte, datensparsame JSONL-Snapshots mit UTC-Zeitstempeln. Die Run-History zeigt bis zu zehn abgeschlossene Runs; instrumentierte Runs enthalten optional Kontexttoken und Kontextlimit; die TUI visualisiert den Verbrauch als Balken.
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
- Es gibt keinen Scroll-Modus. Passen Modellkarten nicht vollständig in den
verfügbaren Bereich, zeigt die TUI ihre Anzahl als ausgeblendet an.
- Power-Limits sind nur verfügbar, wenn die jeweilige Quelle sie meldet.
- Langsame HTTP- oder `nvidia-smi`-Abfragen blockieren derzeit kurzzeitig die
  TUI-Eingabe; eine Entkopplung ist eine spätere technische Verbesserung.
- Die TUI arbeitet weiterhin synchron; langsame API- oder Sensorabfragen können
  kurzzeitig die Eingabe blockieren.
- Git ist im Projektverzeichnis initialisiert; Branch `master`, erster Commit
  steht noch aus.
- Der direkte Client-Modus instrumentiert nur Aufrufe, die über `otop` selbst
  erfolgen; fremde Ollama-Clients bleiben ohne Adapter unsichtbar.
- Der Open-WebUI-Adapter wird mit `--install-open-webui-adapter` per Admin-API
  installiert, konfiguriert und global aktiviert. Dafür muss ausschließlich
  `OPEN_WEBUI_API_KEY` in der lokalen otop-`.env` gesetzt sein. Der Pi-Adapter
  ist weiterhin offen.

## Prüfung am 31.10.2026

- Run-History zeigt in `--once` zehn Einträge; bestehende ältere `cancelled`-Einträge bleiben als historische Altdaten unverändert.
- Lokaler und global installierter Open-WebUI-Adapter sind identisch, aktiv und global aktiviert; der Disconnect-Watcher ist entfernt.
- `python3 otop.py --install-open-webui-adapter`: erfolgreich.
- `python3 -m py_compile`, beide otop-Testmodule, `--once`, `--once --no-nvidia` und `--version`: erfolgreich.
- Paralleler Live-Run-Test: keine verwaisten Einträge nach konkurrierenden Start-/Abschlussupdates.


- `python3 -m py_compile otop.py`: OK.
- `python3 otop.py --version`: `otop 1.7.3`.
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
