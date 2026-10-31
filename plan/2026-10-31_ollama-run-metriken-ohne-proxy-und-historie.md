# Plan: Ollama-Run-Metriken ohne Reverse Proxy und Run-Historie

## Ziel

`otop` soll den **aktuellen** Ollama-Run mit belastbaren Token- und Zeitmetriken
anzeigen und abgeschlossene Runs als einzelne Einträge in der TUI-Historie
auflisten. Die Ollama-API wird dabei weiterhin direkt angesprochen; es gibt
keinen Reverse Proxy und keinen Eingriff in den Datenstrom anderer Clients.

## Befund und Entscheidung

- `/api/ps` zeigt ausschließlich geladene Modelle, keine aktiven Requests.
- Die abschließenden Antworten von `/api/chat` und `/api/generate` enthalten
  die autoritativen Zähler (`prompt_eval_count`, `eval_count`) und Zeiten
  (`load_duration`, `prompt_eval_duration`, `eval_duration`,
  `total_duration`) in Nanosekunden. Ein Live-Test mit `/api/chat` bestätigte
  diese Felder im `done:true`-Objekt; die sechs vorherigen Streaming-Objekte
  enthielten nur `model`, `created_at`, `message` und `done`. Während eines
  Streamings sind Tokenzähler und Zeiten daher nicht verfügbar.
- Der bestehende Eingang `OTOP_RUN_FILE` liefert zwar den aktuellen Zustand,
  aber die bestehende Snapshot-History schreibt ihn bei jedem Refresh erneut.
  Sie ist deshalb keine Historie einzelner Runs.

**Gewählte Lösung:** Der aufrufende Client instrumentiert seinen eigenen,
direkten Ollama-Aufruf mit einem kleinen optionalen Adapter (Bibliothek oder
Client-Wrapper). Der Adapter schreibt ausschließlich lokal Run-Ereignisse;
er akzeptiert keine HTTP-Anfragen anderer Clients und leitet keinen fremden
Datenstrom weiter. Damit entsteht weder ein lokaler HTTP-Server noch ein
Reverse Proxy. Clients ohne Adapter bleiben nutzbar; `otop` zeigt dann
weiterhin „nicht instrumentiert“.

## Datenhaltung und Schnittstelle

Zwei getrennte lokale JSONL-Dateien verhindern Duplikate und vereinfachen die
Aufbewahrung:

- **Live-Zustand**: `OTOP_RUN_FILE` (wie bisher, Standard neben der History).
  Der Adapter aktualisiert pro aktivem Run einen Zustand mit `status=running`.
  `otop` liest daraus den jüngsten frischen Zustand.
- **Run-Historie**: neuer, konfigurierbarer Pfad `OTOP_RUN_HISTORY_FILE`,
  Standard `$XDG_STATE_HOME/otop/runs.jsonl`. Der Adapter schreibt beim
  Abschluss oder Fehler exakt einen finalen Datensatz pro `run_id`.
  `otop` liest diese Datei nur; periodische System-Snapshots werden dort nie
  abgelegt.
- Die vorhandene `history.jsonl` bleibt eine begrenzte System-Snapshotreihe
  und enthält höchstens eine Referenz (`run_id`) auf den aktuellen Run. Damit
  bleibt ihre bisherige Funktion und Kompatibilität erhalten.

Vorgeschlagenes minimales Ereignisformat:

```json
{
  "schema": 1,
  "run_id": "uuid",
  "status": "completed",
  "model": "qwen3.5:4b",
  "started_at": "2026-10-31T14:30:00Z",
  "finished_at": "2026-10-31T14:30:19Z",
  "prompt_tokens": 2100,
  "output_tokens": 8100,
  "context_limit": 32768,
  "load_duration_s": 0.4,
  "prompt_eval_duration_s": 1.2,
  "eval_duration_s": 17.1,
  "total_duration_s": 19.0,
  "error": null
}
```

Regeln:

- `run_id` wird vor dem Request erzeugt und für Live- und Abschlussereignis
  verwendet. Ein Abschluss wird beim Einlesen anhand der ID dedupliziert.
- Dauerangaben werden intern als Sekunden gespeichert; Werte aus der
  Ollama-Antwort werden dafür von Nanosekunden umgerechnet.
- `total_tokens` und `output_tokens_per_second` werden beim Einlesen aus den
  Rohwerten berechnet. Fehlende Werte bleiben `n/a`, nicht `0`.
- `context_limit` kann aus dem zugehörigen Modell in `/api/ps` übernommen
  werden. Einen belastbaren aktuellen Kontextverbrauch liefert der getestete
  Streaming-Endpunkt nicht; ein Kontextbalken bleibt während des Runs deshalb
  `n/a`. `prompt_eval_count` wird nach Abschluss als Prompttokenzahl gezeigt,
  aber nicht als Kontextverbrauch umgedeutet.
- Keine Prompts, Antworten, Nachrichten, Optionen mit Geheimnissen oder
  Benutzerinhalte speichern.
- Schreibvorgänge erfolgen atomar mit Eigentümerrechten `0600`. Die
  Run-Historie wird analog zur bestehenden History auf eine feste, per
  Konstante konfigurierbare Anzahl finaler Einträge begrenzt.

## Anzeige

### Aktueller Run

Die bestehende Ansicht bleibt erhalten und verwendet den Live-Zustand:
Modell, Status, Kontextlimit, Prompt-/Ausgabe-/Gesamttoken, Ausgabe-Rate und
Alter der letzten Aktualisierung. Während des Streamings zeigt die Anzeige für
Token, Rate und Kontextverbrauch `n/a`; Zeichen- oder Chunk-Zahlen werden nicht
fälschlich als Token ausgegeben. Nach `done:true` ersetzt das finale
Ollama-Objekt diese Felder durch die autoritativen Abschlussmetriken.

### History

Der Bereich `History` wird von der reinen Statuszeile zu einer kompakten Liste
der letzten abgeschlossenen Runs (neuester zuerst), zum Beispiel:

```text
History – letzte 5 Runs
  14:30  qwen3.5:4b       fertig  10.2k Tok  473.7 Tok/s  19.0 s
  14:21  qwen3.5:4b       Fehler  0.8k Tok  —            3.1 s
```

- Zeilen enthalten Abschlusszeit, Modell, Status, Gesamttoken, Ausgabe-Rate
  und Gesamtdauer; fehlende Metriken sind `n/a`.
- Die Liste wird auf den verfügbaren Terminalraum begrenzt. Falls die Höhe
  nicht reicht, zeigt sie mindestens die jüngste Zeile plus Anzahl weiterer
  Einträge; die Mindesthöhe der TUI wird entsprechend geprüft und angepasst.
- Die System-Snapshot-History bleibt unsichtbar beziehungsweise nur als
  Schreibstatus erhalten, damit sie nicht mit Run-Historie verwechselt wird.

## Umsetzung in drei Schritten

### 1. Run-Schema und persistente Historie in `otop.py`

- Validierungs- und Normalisierungsfunktionen für Live- und finale
  Run-Ereignisse ergänzen.
- `load_run_event()` kompatibel zum vorhandenen `OTOP_RUN_FILE` halten.
- Leser für `runs.jsonl` implementieren: defekte Zeilen überspringen,
  finale Zustände validieren, nach `finished_at` sortieren und per `run_id`
  deduplizieren.
- Begrenztes, atomisches Anhängen finaler Ereignisse als gemeinsam nutzbare
  Hilfsfunktion vorbereiten; keinen periodischen Eintrag in dieser Datei
  erzeugen.

### 2. Direkter Client-Adapter ohne Proxy

- Einen kleinen, dokumentierten Adapter mit Python-Standardbibliothek in
  `otop.py` oder nur bei Bedarf als zweite Python-Datei ergänzen; die
  bestehende Ein-Datei-Entscheidung hat Vorrang, solange die CLI übersichtlich
  bleibt.
- Der Adapter wird im aufrufenden Client ausgeführt und instrumentiert dessen
  direkten `/api/chat`- oder `/api/generate`-Aufruf gegen den mit `--host`
  beziehungsweise `OLLAMA_HOST` bestimmten Ollama-Host. Er stellt keinen
  Weiterleitungsendpunkt bereit.
- Vor Start ein Live-Ereignis mit Modell und Zeit schreiben. Während des
  Streamings höchstens Status und Aktualisierungszeit fortschreiben, weil der
  getestete Endpunkt keine Tokenmetriken je Chunk liefert. Aus dem finalen
  `done:true`-Objekt wird ein einziges Abschlussereignis erzeugt; dabei werden
  Nanosekunden in Sekunden umgerechnet. Netzwerk-, Abbruch- und JSON-Fehler
  werden als finaler Fehlerstatus ohne erfundene Zähler gespeichert.
- Der Adapter bleibt opt-in: Bestehende direkte Ollama-Clients und `otop`
  funktionieren unverändert ohne ihn.

### 3. TUI, `--once`, Dokumentation und Tests

- Historienliste in `_draw()` und eine knappe äquivalente Ausgabe bei `--once`
  ergänzen; Zeilen gegen enge Terminals absichern.
- README, `status.md` und `version.md` mit Umgebungsvariablen, Schema,
  Datenschutz und Adapter-Beispiel aktualisieren; als neue Funktion einen
  Minor-Release eintragen.
- Gezielte Tests mit temporären JSONL-Dateien: fehlende/defekte Ereignisse,
  stale Live-Run, Duplikat-ID, abgeschlossener und fehlerhafter Run,
  Begrenzung sowie Darstellung bei geringer Terminalhöhe.
- Danach `python3 -m py_compile otop.py`, `--version`, `--once` und ein
  Pseudo-TTY-Rendering ausführen. Einen direkten Test gegen laufendes Ollama
  nur durchführen, wenn die lokale Instanz verfügbar ist.

## Abnahmekriterien

- Ein instrumentierter direkter `/api/chat`- oder `/api/generate`-Run erscheint
  während der Ausführung als aktueller Run, ohne dass ein Reverse Proxy läuft.
- Die finale Anzeige nutzt die von Ollama gelieferten Abschlussmetriken und
  berechnet Token/s nach Umrechnung von Nanosekunden korrekt aus
  `eval_count / eval_duration`.
- Jeder beendete oder fehlgeschlagene Run erscheint höchstens einmal in der
  Run-Historie, auch wenn `otop` mehrfach refresht oder neu gestartet wird.
- Eine fehlende, alte oder beschädigte Ereignisdatei führt weder zu erfundenen
  Metriken noch zu einem TUI-Absturz.
- Bestehende System-Snapshots, GPU-/Modellanzeige und nicht instrumentierte
  Clients bleiben funktionsfähig.
