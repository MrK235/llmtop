# Plan: Live-Tokenzähler und Tokenrate für Open-WebUI-Runs

## Ziel

Während eines laufenden Open-WebUI-Runs sollen unter **Aktuelle Runs** echte
Tokenwerte und eine Tokenrate erscheinen, sobald Open WebUI diese Werte bereits
in einem Stream-/Usage-Ereignis liefert. Ohne echte Werte bleibt die Anzeige
`n/a`; es werden keine Token oder Raten geschätzt.

## Befund

- Der Collector legt beim Request nur einen `started`-Run ohne Tokenwerte an.
- `token_rate()` kann nur aus `output_tokens` und `eval_duration_s` berechnen.
- Der Filter verarbeitet Metriken aus `stream()` derzeit direkt als Abschluss
  und sendet danach keinen Live-Update-Event.
- Dadurch wird ein finaler Stream-Chunk entweder zu spät für eine laufende
  Anzeige verarbeitet oder der aktive Run sofort aus `run.jsonl` entfernt.
- Die bestehende Anzeige kann Token und Rate bereits darstellen; die Datenzufuhr
  und die Trennung von Update und Abschluss fehlen.

## Umsetzung

### 1. Open-WebUI-Filter: Fortschrittsmetriken als Update senden

- Bekannte Felder aus `usage` weiter datensparsam extrahieren, einschließlich
  Prompt-/Output-Token und kompatibler Dauerfelder.
- Bei einem Stream-Ereignis mit Nutzungswerten ein Schema-2-Event `updated`
  an den Collector senden, statt den Run sofort abzuschließen.
- Den zuletzt bekannten Metrikstand pro Run im Filter zwischenspeichern, damit
  wiederholte identische Stream-Ereignisse nicht unnötig gesendet werden.
- Einen Stream-Chunk nur dann als Abschluss behandeln, wenn er eindeutig final
  ist (`done`, bekanntes Abschlussereignis oder vorhandener Abschlussgrund).
- `outlet()` bleibt als Abschluss-Fallback erhalten und verwendet die zuletzt
  bekannten Metriken, falls das finale Outlet keine Usage-Werte enthält.
- Keine Payload-, Prompt-, Antwort- oder Tokeninhalte loggen; nur erlaubte
  numerische Metrikfelder übertragen.

### 2. Collector und Live-Run-Normalisierung prüfen/ergänzen

- Sicherstellen, dass `updated`-Events denselben Run anhand von Quelle und
  `run_id` aktualisieren und nicht als neuer Run erscheinen.
- Bei einem Update `updated_at` setzen und vorhandene Token-/Dauerwerte
  überschreiben bzw. ergänzen.
- Finale Events weiterhin genau einmal in `runs.jsonl` schreiben und den
  aktiven Eintrag entfernen.
- Bei fehlenden Dauerwerten keine künstliche Rate aus der TUI-Laufzeit bilden;
  `Token/s` bleibt `n/a`, auch wenn Tokenwerte bereits vorhanden sind.

### 3. Darstellung und Tests

- Aktuelle Runs explizit im Format `Tokens: <gesamt> · <output> Tok/s`
  darstellen, sobald Werte vorhanden sind; sonst die bestehende kompakte
  `Token n/a`-Darstellung beibehalten.
- Prompt- und Output-Token getrennt berücksichtigen; die Rate basiert nur auf
  Output-Tokens und einer echten Evaluierungsdauer.
- `--once` und History auf unveränderte, konsistente Quellen-/Tokenanzeige
  prüfen.
- Filtertests ergänzen für:
  - `started` → `updated` mit Tokenwerten,
  - mehrere identische Updates ohne unnötige Duplikate,
  - finales Stream-Ereignis plus Outlet genau einmal,
  - Outlet ohne Usage übernimmt letzte bekannte Werte,
  - fehlende Dauer ergibt `n/a` bei `Token/s`.
- Collector-/Renderer-Test mit temporären JSONL-Dateien ergänzen.
- Syntaxcheck und vorhandene Open-WebUI-Filtertests ausführen.

## Abnahme

Während eines echten längeren Open-WebUI-Chats erscheint der laufende Eintrag
unter **Aktuelle Runs** mit einem echten Tokenzähler, sobald Open WebUI Usage-
Daten liefert. Bei vorhandener Evaluierungsdauer erscheint zusätzlich die echte
Rate in `Token/s`. Nach Abschluss bleibt genau ein History-Eintrag bestehen;
fehlende Dauerwerte werden weiterhin als `n/a` angezeigt.

## Nichtziele

- Keine Schätzung von Tokenzahlen oder Tokenraten aus Zeit, Textlänge oder
  Modellparametern.
- Keine Änderung an Open WebUI, Docker Compose oder Ollama.
- Keine Speicherung von Prompts, Antworten, Nachrichten oder Benutzerinhalten.
