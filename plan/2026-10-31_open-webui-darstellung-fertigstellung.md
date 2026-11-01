# Plan: Open-WebUI-Runmetriken in llmtop dauerhaft darstellen

## Ziel

Ein laufendes `llmtop` soll Open-WebUI-Ollama-Aufrufe ohne zweiten manuellen Collector-Prozess sofort unter **Aktuelle Runs** zeigen und nach Abschluss zuverlässig unter **History** historisieren. Quelle, Modell, Status, Token, Rate und verfügbare Dauerwerte bleiben in kleinen Terminals sichtbar.

## Geprüfter Ist-Stand

- Der Open-WebUI-Filter `llmtop_run_metrics` ist über die API installiert, aktiv und global.
- Die API-Valves `collector_url` und `collector_token` sind gesetzt; Werte wurden nicht ausgegeben.
- Ein echter Chat über `/api/chat/completions` mit `qwen3.5:4b` lieferte HTTP 200 und erzeugte einen finalen Run mit Quelle `open-webui`, Prompt- und Ausgabe-Token.
- Der Collector ist aus dem Container über die private Gateway-Adresse erreichbar.
- Der aktuelle TUI-Renderer kann aktive Runs und finale History grundsätzlich anzeigen.
- Die erfolgreichen Live-Tests verwendeten absichtlich temporäre State-Dateien. Im regulären State-Verzeichnis liegen daher momentan keine Run-Einträge; die TUI zeigt folgerichtig keine Open-WebUI-Runs.
- Der Collector läuft bisher nur bei explizitem `--collector` als separater, blockierender Prozess. Das ist die letzte praktische Lücke: Startet nur die TUI, läuft kein HTTP-Eingang für Open WebUI.
- Open WebUI reicht in diesem Ablauf Tokenwerte durch, aber keine Gesamtdauer. `n/a` ist dafür korrekt und darf nicht geschätzt werden.

## Umsetzung

### 1. Collector in den normalen TUI-Start integrieren

1. Die bisherige Collector-Erzeugung in eine kleine, wiederverwendbare `CollectorService`-Klasse zerlegen:
   - Server auf Loopback und erkannter privater Open-WebUI-Gateway-Adresse erzeugen,
   - im Hintergrund starten,
   - sauber herunterfahren,
   - gebundene Adressen und Fehlerstatus bereitstellen.
2. Die TUI startet den Service automatisch, wenn `LLMTOP_COLLECTOR_TOKEN` konfiguriert ist.
3. `--collector` bleibt als expliziter, dauerhaft blockierender Dienstmodus erhalten und verwendet dieselbe Klasse.
4. Ist bereits ein Collector aktiv und der Port belegt, beendet die TUI sich nicht. Sie zeigt einen nicht störenden Hinweis, dass kein eigener Listener gestartet werden konnte; vorhandene Run-Dateien werden weiter gelesen.
5. Fehlt der Token, bleibt die TUI funktionsfähig und zeigt klar „Collector nicht konfiguriert“ statt eines Fehlers beim Start.

### 2. Darstellung und Status vervollständigen

1. Im Ollama-Bereich eine kurze Collector-Zeile ergänzen:
   - `Collector: aktiv · 127.0.0.1, 172.18.0.1`,
   - `Collector: extern/Port belegt`,
   - oder `Collector: nicht konfiguriert`.
2. **Aktuelle Runs** behält maximal drei neueste Einträge; jede Zeile enthält Quelle, Modell, Status und Alter. Tokenwerte werden nur gezeigt, wenn echt vorhanden.
3. **History** behält die Quellen-Spalte auch bei reduziertem Layout. Bei geringer Höhe darf sie Modellkarten überlagern bzw. kürzen, aber weder Quelle noch jüngsten History-Eintrag verlieren.
4. `--once` zeigt den Collector-Status und maximal fünf finale Runs mit derselben Quelleninformation.
5. Die vorhandene System-Snapshot-History bleibt unverändert getrennt von `runs.jsonl`.

### 3. Metrikrobustheit des Filters abschließen

1. Die Filterfunktion akzeptiert zusätzlich bekannte Dauerfelder innerhalb von Open-WebUI-`usage`, ohne unbekannte Felder oder Inhalte zu übernehmen.
2. Finale Stream- und Outlet-Ereignisse bleiben dedupliziert.
3. Fehlen Dauerwerte weiterhin, speichert der Filter keine Ersatzwerte; Ausgabe bleibt `n/a`.
4. Kein Debug-Logging von Payloads, Nachrichten oder Tokens außerhalb der bestehenden Runmetrik.

## Tests

| Fall | Erwartung |
|---|---|
| `python3 llmtop.py` mit Token | startet TUI und privaten Collector automatisch |
| Open-WebUI-Chat während TUI läuft | aktiver `Open WebUI`-Run sichtbar, dann ein History-Eintrag |
| `--once` nach Chat | Quelle, Modell und echte Tokenwerte sichtbar |
| fehlender Token | TUI läuft, Collector-Status klar als nicht konfiguriert |
| bereits laufender `--collector` | TUI bleibt funktionsfähig, Status zeigt extern/Port belegt |
| enge Terminalhöhe | jüngster History-Run inklusive Quelle sichtbar |
| fehlende Dauerwerte aus Open WebUI | Dauer und Rate `n/a`, keine Schätzung |
| Stream plus Outlet | genau ein finaler History-Eintrag |
| Collector-Ausfall | Open-WebUI-Antwort bleibt unverändert funktionsfähig |

## Nichtziele

- Kein Systemdienst, Autostart oder Änderung außerhalb des Projektordners.
- Keine Änderung an Docker Compose, Open-WebUI oder Ollama.
- Keine Erfassung fremder, nicht instrumentierter Ollama-Clients.
- Keine Prompt-, Antwort- oder Benutzerinhalte in Dateien oder Logs.

## Abnahme

Nach Start von `python3 llmtop.py` erscheint ein realer Open-WebUI-Ollama-Chat ohne zusätzlichen Collector-Befehl zunächst unter **Aktuelle Runs** und nach Abschluss genau einmal mit Quelle `Open WebUI` in **History**. Fehlende serverseitige Dauerwerte sind erkennbar als `n/a` markiert.
