# Plan: History-Gruppen mit neuesten Ergebniswerten

## Ziel

Die eingeklappte Gruppenzeile einer Pi-Session oder eines Open-WebUI-Chats soll
ausschließlich den neuesten **abgeschlossenen** Run repräsentieren. Laufende
Runs dürfen die History nicht verändern. Ältere Runs bleiben nur nach dem
Aufklappen sichtbar.

Fehlende Werte werden nur dann berechnet, wenn die Berechnung aus Daten desselben
neuesten Runs eindeutig und fachlich sinnvoll ist. Werte verschiedener Runs
werden weder summiert noch miteinander vermischt.

## Analyse des Ist-Zustands

Die History selbst enthält bereits nur finale Runs:

- `process_run_event()` schreibt ausschließlich `completed`, `error` oder
  `cancelled` in die Run-History.
- `load_run_history()` normalisiert mit `final=True` und verwirft nicht finale
  Einträge.
- Laufende Runs stehen getrennt in `run.jsonl` und beeinflussen die persistierte
  History nicht.

Der Fehler liegt in `llmtop_tui.py → aggregate_history_group()`:

1. Der neueste Run wird zunächst korrekt über `finished_at` gewählt.
2. Danach überschreibt die Funktion dessen Ergebniswerte mit Summen aller Runs:
   Tokens, Kontext, Kontextlimit sowie Auswertungs- und Gesamtdauer.
3. Tok/s wird dadurch aus künstlich summierten Werten neu berechnet.
4. Ein älterer Fehler oder Abbruch überschreibt den Status eines neueren,
   erfolgreichen Ergebnisses.
5. Bei verschiedenen Modellen wird statt des aktuellen Modells eine Modellanzahl
   angezeigt.

Das ist besonders beim Kontext falsch:

- Open WebUI liefert beim neuesten Request in der Regel bereits den bis dahin
  relevanten Chat-Kontext.
- Pi liefert `context_tokens` aus dem aktuellen Session-Kontext.
- Eine Summe mehrerer solcher Stände zählt vorherigen Kontext mehrfach.

## Fachliche Regeln

### Repräsentativer Run

- Pro Gruppe wird der finale Run mit dem neuesten `finished_at` verwendet.
- Bei identischem oder fehlendem Abschlusszeitpunkt dienen anschließend
  `updated_at`, `started_at` und `run_id` als stabile Tie-Breaker.
- Alle nicht abgeleiteten Felder stammen ausschließlich aus diesem Run:
  Quelle, Provider, Modell, Status, Zeit, Tokenwerte, Kontextlimit und Dauer.
- Die Run-Anzahl darf weiterhin als `×N` am Modell erscheinen; sie ist nur eine
  Gruppenmetadatenangabe und kein Metrikwert.

### Zulässige Berechnungen bei fehlenden Werten

Berechnungen erfolgen ausschließlich aus Feldern des repräsentativen Runs:

1. `context_tokens = prompt_tokens + output_tokens`, wenn beide Werte vorhanden
   sind und `context_tokens` fehlt. Diese Normalisierung existiert bereits.
2. Gesamttokens werden nur aus `prompt_tokens + output_tokens` gebildet, wenn
   beide Werte vorhanden sind. Ein einzelner vorhandener Teilwert darf nicht als
   Gesamtwert ausgegeben werden.
3. `total_duration_s = finished_at - started_at`, wenn keine gemeldete
   Gesamtdauer vorhanden ist und beide Zeitstempel gültig sind.
4. Tok/s wird bevorzugt aus `output_tokens / eval_duration_s` berechnet.
   Fehlt nur die Auswertungsdauer, darf ersatzweise die vorhandene oder aus den
   Zeitstempeln berechnete Gesamtdauer verwendet werden.
5. Kontextprozent wird wie bisher aus `context_tokens / context_limit`
   berechnet. Das Kontextlimit darf wie bisher aus einem eindeutig passenden,
   aktuell geladenen Modell ergänzt werden.

Nicht zulässig:

- Übernahme fehlender Werte aus älteren Runs.
- Summieren oder Mitteln mehrerer Runs.
- Ableitung eines fehlenden Prompt- oder Ausgabewerts aus dem Session-Kontext,
  weil Pi-Session-Kontext und Provider-Usage unterschiedliche Bedeutungen haben.
- Schätzung aus Prompt-, Antwort- oder Toolinhalten.

Bleibt ein Wert danach unbekannt, zeigt die Gruppenzeile `n/a`.

### Sortierung

- Die Reihenfolge der Gruppen soll auf denselben repräsentativen Werten beruhen,
  die in der Gruppenzeile sichtbar sind.
- Innerhalb einer aufgeklappten Gruppe bleibt die bestehende Sortierung der
  Einzelruns erhalten.
- Einzelruns ohne Gruppierungsidentität verhalten sich unverändert.

## Umsetzung in drei Schritten

### 1. Repräsentatives Gruppenmodell korrigieren

Betroffene Dateien: `llmtop_tui.py`, bei sinnvoller Wiederverwendung
`llmtop_metrics.py`.

- `aggregate_history_group()` durch eine Funktion ersetzen, die eine Kopie des
  neuesten finalen Runs als Gruppenzeile erzeugt.
- Sämtliche Summen und die Status-Priorisierung über ältere Runs entfernen.
- Kleine Hilfsfunktionen für stabile Neueste-Auswahl und eindeutig ableitbare
  Dauer-/Tokenwerte ergänzen.
- Gruppenlabel, Kurzkennung, Aufklappmarker und `×N` beibehalten.
- Gruppen anhand des repräsentativen Runs sortieren; Einzelruns innerhalb der
  Gruppe weiterhin nach der gewählten Spalte sortieren.

**Abnahme:** Ein älterer Run mit höheren Tokens oder Fehlerstatus verändert die
Kopfzeile nicht; diese entspricht dem neuesten Abschluss.

### 2. Regressionsfälle für Pi und Open WebUI abdecken

Betroffene Datei: `test_llmtop.py`; zusätzliche Laufzeitprüfungen nur im
Scratch-Verzeichnis.

Tests für beide Quellen:

- Neuer erfolgreicher Run nach älterem Fehler.
- Neuer kleinerer Kontext nach älterem größerem Kontext.
- Modell- und Providerwechsel innerhalb derselben Gruppe.
- Fehlender Kontext mit vorhandenen Prompt- und Ausgabetokens.
- Fehlende Gesamtdauer mit gültigen Start-/Endzeiten.
- Fehlende Auswertungsdauer mit sinnvoller Gesamtdauer-Rate.
- Unvollständige Tokenwerte bleiben `n/a` statt ältere Werte zu übernehmen.
- Ein laufender Run in der Live-Datei verändert die History-Gruppe nicht.
- Aufgeklappte Gruppe zeigt weiterhin sämtliche unveränderten Einzelruns.

**Abnahme:** Gruppenzeile und Sortierwert entsprechen in jedem Fall demselben
neuesten finalen Run.

### 3. Dokumentation, Version und Gesamtprüfung

Betroffene Dateien: `README.md`, `status.md`, `version.md`, `llmtop.py` und nur
bei tatsächlicher Adapteränderung die Adapter-Versionszeilen.

- Aussagen über summierte Gruppenwerte entfernen.
- Dokumentieren, dass Gruppen den neuesten Abschluss zeigen und nur eindeutig
  ableitbare Werte berechnet werden.
- Patch-Version erhöhen.
- `git diff --check`, Syntaxcheck, Gesamttests, `--once`,
  `--once --no-nvidia`, `--version` und Pseudo-TTY-Prüfung ausführen.

## Nichtziele

- Laufende Runs in die History oder Gruppenzeile mischen.
- Alte History-Daten verändern oder löschen.
- Prompts, Antworten oder Tooldaten zur Schätzung auswerten.
- Werte zwischen verschiedenen Runs fortschreiben.
- Änderungen an Collector-Pfaden, Schema oder dem 100-Run-Limit.
