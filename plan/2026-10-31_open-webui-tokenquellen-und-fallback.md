# Plan: Open-WebUI-Tokenmetriken aus API, Datenbank und nativem Filter

## Ziel

Die bestmöglichen **echten** Tokenmetriken für Open-WebUI-Ollama-Runs
bereitstellen und klar sichtbar machen, wann laufende Werte technisch nicht
verfügbar sind. Schätzungen aus Zeichen, Wörtern oder Laufzeit sind ausdrücklich
ausgeschlossen.

## Prüfungsergebnis

### 1. Open-WebUI-API

- Das Modell `qwen3.6:35b-a3b` hat die Open-WebUI-Fähigkeit `usage: true`.
- Open WebUI ergänzt deshalb beim Streaming korrekt
  `stream_options: {"include_usage": true}`.
- Der installierte Backend-Code konvertiert einen Ollama-Stream aber so, dass
  `usage` ausschließlich beim finalen Chunk (`done: true`) erzeugt wird.
  Nicht-finale Chunks enthalten nur Text-/Thinking-Deltas.
- Ein realer langer Chat wurde beobachtet: Der aktive Collector-Eintrag enthielt
  über mehr als eine Minute ausschließlich Status und Zeitstempel. Die finalen
  `prompt_tokens` und `output_tokens` wurden erst nach Ende geliefert.
- Ergebnis: Die API liefert in dieser Kombination echte Zähler und Dauerwerte
  nur am Ende. `include_usage` kann das nicht ändern, weil Ollama selbst keine
  Zwischenstände sendet.

### 2. Open-WebUI-Datenbank

- Die SQLite-Datenbank liegt im Docker-Volume als `webui.db`; die Tabelle
  `chat_message` enthält eine JSON-Spalte `usage`.
- Das Backend befüllt und normalisiert diese Usage für persistierte
  Antwortnachrichten. Sie ist daher eine brauchbare, unabhängige Quelle für
  nachträgliche finale Werte.
- Sie ist kein Live-Kanal: Der Datensatz entsteht bzw. erhält die finale Usage
  erst beim Abschluss. Direkte API-Chats ohne persistierte Chat-ID erzeugen
  zudem nicht zwingend einen zuordenbaren Chat-Datensatz.
- Ein Polling der Datenbank erfordert Zugriff auf das Docker-Volume und darf nur
  lesend erfolgen. Es ergänzt den Filter, ersetzt ihn aber nicht.

### 3. Nativer Filter

- Der native Filter erhält während des Streams nur die von Open WebUI
  weitergereichten Deltas. Ohne `usage` kann er keine echten Output-Token
  zählen.
- Der Filter erhält am Ende die vom Backend normalisierten finalen Usage-Werte
  und ist damit die schnellste und datensparsamste finale Quelle.
- Die lokale Ollama-Version ist `0.40.6`; ein Test von `/api/tokenize` ergab
  HTTP 404. Ein modellgenauer, nachträglicher Tokenzähler als Workaround steht
  somit nicht bereit.
- Ein Tokenzähler aus Textfragmenten wäre ohne Modelltokenizer nur eine
  Schätzung und wird nicht implementiert.

## Entscheidung

Keine der drei Quellen kann mit dem geprüften Open-WebUI-/Ollama-Pfad echte
laufende Output-Token oder `Token/s` liefern. Der sinnvolle Ausbau ist daher:

1. native Filter-Events als primäre Quelle für Start und finalen Abschluss,
2. API-/Datenbank-Abgleich als finale Fallback- und Korrekturquelle,
3. eindeutige TUI-Anzeige, dass Live-Token vom Provider erst beim Abschluss
   geliefert werden.

Damit sind nach Abschluss Token und Rate vollständig und robust; während der
Generierung wird kein falscher Live-Wert angezeigt.

## Umsetzung

### 1. Native Filter als Primärquelle vervollständigen

- Den Filter bei Start wie bisher `started`, bei vorhandenen echten
  Zwischenmetriken `updated` und bei Abschluss `completed` senden lassen.
- Finale Usage aus allen bekannten Open-WebUI-Formen übernehmen:
  `input_tokens`/`output_tokens`, `prompt_tokens`/`completion_tokens` sowie
  Ollama-Rohfelder und echte Dauerfelder.
- Den bekannten Metrikstand im Run halten, damit ein Outlet ohne Usage die
  letzten echten Werte finalisiert.
- Filterversion erhöhen und über den vorhandenen Installationsbefehl
  aktualisieren.

### 2. Finale API- und Datenbank-Fallbacks ergänzen

- Einen kleinen, optionalen `OpenWebUIFinalMetricsReader` in `llmtop.py`
  ergänzen, der nur bei einem unvollständigen finalen Open-WebUI-Run aktiv wird.
- **API-Pfad:** Vorhandene Chat-/Nachrichten-Endpunkte nur nutzen, wenn eine
  stabile Chat- oder Message-ID aus Filter-Metadaten verfügbar ist. Ausschließlich
  `usage`, Modell, Zeit und IDs lesen; keine Inhalte übernehmen.
- **Datenbank-Pfad:** Optionaler, explizit konfigurierter Nur-Lese-Pfad
  `LLMTOP_OPEN_WEBUI_DB` zum SQLite-Volume. Abfrage ausschließlich gegen
  `chat_message` nach passender Message-ID und/oder sicherer Zeit-/Modell-
  Korrelation innerhalb eines engen Zeitfensters.
- Keine Docker-Exec-Aufrufe und keine Mount- oder Compose-Änderungen durch
  `llmtop`; der Pfad wird vom Betreiber explizit bereitgestellt.
- Der Abgleich läuft begrenzt im Hintergrund (z. B. wenige Wiederholungen nach
  Abschluss), aktualisiert nur fehlende Felder und kann niemals einen bestehenden
  echten Wert überschreiben.
- Ohne ID oder eindeutige Korrelation wird nichts ergänzt, um Verwechslungen
  paralleler Runs auszuschließen.

### 3. TUI und `--once` transparent machen

- Bei laufendem Run ohne echte Tokenwerte anzeigen:
  `Tokens: warten auf Provider · Token/s: n/a`.
- Falls echte Prompt-Token vorliegen, aber keine Output-Token:
  `Prompt: <n> · Ausgabe: warten auf Provider · Token/s: n/a`.
- Nach finaler Usage darstellen:
  `Tokens: <gesamt> (Prompt <n>, Ausgabe <n>) · <rate> Tok/s`.
- Fehlt eine echte Evaluierungsdauer, trotz finaler Tokens `Token/s: n/a`
  zeigen.
- Die Quelle des finalen Werts intern als `filter`, `api` oder `db` führen,
  aber keine Chatinhalte speichern oder anzeigen.

### 4. Prüfung

- Unit-Tests für alle unterstützten Usage-Feldnamen, Update-Deduplizierung und
  Outlet-Fallback.
- SQLite-Testdatenbank mit finaler Usage: eindeutige Zuordnung ergänzt nur
  fehlende Werte; mehrdeutige Treffer werden verworfen.
- API-Reader mit Mock-Antworten: keine Abfrage ohne stabile ID, Timeout- und
  Fehlerfall ohne Auswirkung auf den Run.
- Realer Open-WebUI-Chat: aktiver Run zeigt transparent den Provider-Wartezustand;
  nach Abschluss erscheinen genau ein finaler History-Eintrag, Token und – falls
  von Ollama gemeldet – Rate.
- Syntaxcheck, Filtertests und `--once` ausführen.

## Nichtziele

- Keine geschätzten Tokenzähler oder Tokenraten.
- Kein Zugriff auf Prompts, Antworten oder Benutzerinhalte.
- Kein Ändern von Open-WebUI, dessen Datenbank, Docker Compose oder Ollama.
- Kein Tokenizer-Paket und keine neue Abhängigkeit.

## Abnahme

Ein aktiver Open-WebUI-Run zeigt entweder echte vom Provider gemeldete Werte
oder eindeutig den Wartezustand. Nach Abschluss werden finale Token und
Tokenrate zuverlässig aus dem nativen Filter übernommen und bei fehlenden
Filterwerten nur bei sicherer Zuordnung über API oder Datenbank ergänzt.
