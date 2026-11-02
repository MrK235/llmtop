# Plan: Session-, Chat- und Message-IDs für Pi und Open WebUI

## Ziel

Jeder instrumentierte Run soll neben der technischen `run_id` optionale
Identitätsdaten für spätere Gruppierung und Wiedererkennung erhalten:

- `session_id`: stabile Pi-Session beziehungsweise vorhandene WebUI-Session
- `chat_id`: Open-WebUI-Konversation
- `message_id`: konkrete Open-WebUI-Nachricht beziehungsweise Request

Die IDs werden datensparsam als Metadaten gespeichert. Prompts, Antworten,
Sessionpfade und Credentials bleiben ausgeschlossen.

## Vorbefund

- Pi erzeugt bereits eine zufällige `run_id` pro Agentenlauf. Die stabile
  Session-ID ist über `ctx.sessionManager.getSessionId()` verfügbar.
- Der Pi-Adapter fasst mehrere Modell- und Toolturns zu einem Run zusammen;
  alle Ereignisse desselben Runs können daher dieselbe `session_id` tragen.
- Der Open-WebUI-Adapter erhält `message_id`, `chat_id` und `session_id` bereits
  in `__metadata__`. Diese Werte werden derzeit nur für `_key()` und die
  Zuordnung laufender Runs verwendet und nicht an den Collector weitergegeben.
- `normalize_run()` verwirft unbekannte Felder. Ohne Erweiterung des Schema-2-
  Normalisierers würden die neuen IDs im Collector verloren gehen.
- Die bestehende Identität `(source, run_id)` bleibt die eindeutige
  Run-Identität. Session- und Chat-IDs dienen nur der Gruppierung.

## Datenmodell

Schema 2 erhält drei optionale, kurze Stringfelder:

```json
{
  "run_id": "technisch-eindeutiger-run",
  "source": "pi",
  "session_id": "pi-session-id",
  "chat_id": "optional",
  "message_id": "optional"
}
```

- Fehlende Werte werden nicht künstlich erzeugt.
- Werte werden validiert und wie andere Metadaten auf maximal 120 Zeichen
  begrenzt.
- Pi liefert zunächst nur `session_id`; `chat_id` und `message_id` bleiben
  dort leer.
- Open WebUI übernimmt jedes vorhandene Feld separat. `chat_id` wird nicht
  stillschweigend als `session_id` umbenannt.
- Bereits vorhandene Runs bleiben gültig, enthalten aber keine nachträglich
  rekonstruierbaren IDs.

## Geplante Live-Verwendung

Die Anzeige darf Runs nicht allein wegen gleicher Modelle oder gleicher
Provider zusammenlegen.

1. Primäre Gruppierung: `source` plus vorhandene `session_id`.
2. Open WebUI ohne `session_id`: `chat_id` als Konversationsgruppe verwenden.
3. `message_id` dient zur Wiedererkennung des einzelnen Requests innerhalb
   einer Gruppe.
4. Fehlende IDs führen zu keiner spekulativen Gruppierung; der bestehende
   `run_id` bleibt die einzige sichere Identität.
5. Die vollständigen IDs bleiben intern. Für die TUI wird später nur ein
   kompakter, stabiler Wiedererkennungswert oder Gruppenindex angezeigt, damit
   die Tabellenbreite nicht unnötig wächst.

Die Anzeigeerweiterung wird getrennt von der Datenerfassung umgesetzt, damit
zuerst belastbare Ereignisdaten vorliegen und keine falschen Gruppen entstehen.

## Umsetzung in drei Schritten

### 1. Schema und Persistenz erweitern

Betroffene Datei: `llmtop_metrics.py`.

- `normalize_run()` um `session_id`, `chat_id` und `message_id` erweitern.
- Stringprüfung und Längenbegrenzung zentral an einer Stelle durchführen.
- Live- und History-Persistenz unverändert über das bestehende JSONL-Schema
  weiterverwenden.
- Bestehende Deduplizierung weiterhin ausschließlich über
  `(source, run_id)` durchführen.

**Abnahme:** Ein Testevent mit allen drei IDs bleibt nach Normalisierung,
Live-Schreiben und History-Schreiben vollständig erhalten.

### 2. Pi- und Open-WebUI-Ereignisse ergänzen

Betroffene Dateien: `pi/llmtop_run_metrics.ts`,
`open_webui/llmtop_run_metrics.py`.

- Pi liest die Session-ID beim `agent_start` über
  `ctx.sessionManager.getSessionId()`; bei nicht verfügbaren älteren APIs wird
  das Feld weggelassen.
- Pi sendet die ID in `started`, `updated` und finalen Ereignissen.
- Open WebUI übernimmt die drei vorhandenen Metadatenfelder beim Erzeugen des
  internen Runs und sendet sie in Start-, Update- und Abschlussereignissen.
- Interne Zuordnung über `_key()` bleibt bestehen; parallele Runs mit
  unterschiedlichen `message_id`/`chat_id` dürfen nicht zusammenfallen.

**Abnahme:** Adaptertests prüfen einzelne, parallele und fehlende IDs sowie,
dass keine Nachrichteninhalte übertragen werden.

### 3. Gruppierung und Wiedererkennung in der Live-Anzeige vorbereiten

Betroffene Dateien: `llmtop_tui.py`, bei Bedarf `llmtop_metrics.py`,
`README.md`, `status.md`, `version.md`.

- Gemeinsame Hilfsfunktion für eine sichere Gruppen-/Identitätskennung
  definieren.
- Aktuelle Runs nach Quelle und vorhandener Session-/Chat-Identität gruppieren,
  ohne Runs mit fehlenden oder unterschiedlichen IDs zu verschmelzen.
- Einen kompakten Wiedererkennungswert nur in ausreichend breiten Ansichten
  anzeigen; Kompaktansicht und bestehende Tabellenbreiten bleiben stabil.
- History zunächst ohne neue Pflichtspalte lassen; die gespeicherten IDs stehen
  für spätere Filter- oder Gruppierungsfunktionen bereit.
- Dokumentation und Versionsstand synchron aktualisieren.

**Abnahme:** Pseudo-TTY-Tests mit zwei Runs derselben Gruppe, zwei parallelen
Gruppen und fehlenden IDs zeigen korrekte Gruppen, unveränderte Run-Zeilen und
keine falsche Zusammenlegung.

## Nichtziele

- Keine Speicherung von Prompt-, Antwort-, Tool- oder Sessiondateiinhalten.
- Keine Änderung der bestehenden `run_id`-Semantik.
- Keine Gruppierung ausschließlich nach Modell, Provider oder Zeit.
- Keine neue Datenbank, keine neue Abhängigkeit und kein verpflichtender
  Anzeigeumbau der History.
