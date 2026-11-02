# Plan: Aufklappbare History-Gruppen mit Cursor-Navigation

## Ziel

Die Run-History soll Sessions und Open-WebUI-Konversationen komprimiert als
Gruppen darstellen, ohne einzelne Runs zu verlieren:

- Gruppen sind standardmäßig eingeklappt und zeigen Anzahl sowie eine kurze
  Identitätskennung.
- Ein Cursor markiert die aktuelle Gruppe oder einen einzelnen Run.
- `Enter` klappt die markierte Gruppe auf beziehungsweise zu.
- Die aufgeklappte Gruppe zeigt alle enthaltenen Runs weiterhin in der
  bestehenden Tabelle.
- Sortierung, Quellen-Trennung und die Begrenzung auf 100 History-Runs bleiben
  erhalten.

## Machbarkeitsprüfung

Die Umsetzung ist mit der bestehenden curses-TUI und dem aktuellen Schema 2
machbar. Die Identitätsfelder sind bereits vorhanden:

- Pi: `session_id`
- Open WebUI: bevorzugt `session_id`, ersatzweise `chat_id`
- `message_id`: eindeutige Wiedererkennung eines einzelnen WebUI-Requests
- fehlende Identität: Fallback auf eindeutige `run_id`, daher keine falsche
  Zusammenfassung

Die aktuelle History ist noch eine flache Liste. `history_offset` scrollt
heute direkt über Run-Indizes; ein Cursor und ein expandierter Zeilenstrom sind
noch nicht vorhanden. Das ist die wesentliche, aber lokal begrenzte Änderung.

## Gruppierungsregeln

1. Gruppenschlüssel ist immer `(source, run_group_key(run))`.
2. `run_group_key()` verwendet `session_id`, danach `chat_id`, danach
   `message_id`.
3. Ohne diese Felder bleibt `run_id` der Gruppenschlüssel; solche Runs werden
   nicht mit anderen zusammengelegt.
4. Die Reihenfolge der Gruppen folgt dem ersten Run in der bereits sortierten
   History. Dadurch bleibt die aktive Sortierspalte verständlich, ohne für
   Gruppen künstliche Summen oder Mittelwerte zu erfinden.
5. Innerhalb einer aufgeklappten Gruppe bleibt die bestehende Sortierung
   unverändert.
6. Die Gruppierung ist nur eine Anzeigeebene. Persistenz, Deduplizierung und
   die technische `run_id` bleiben unverändert.

## Anzeige und Bedienung

### Eingeklappte Gruppe

Beispiel:

```text
Pi · Session 01a2b3c4  (5 Runs · zuletzt 02.11 21:14)
Open WebUI · Chat 9f8e7d6c  (3 Runs · zuletzt 02.11 21:10)
```

Die vollständigen IDs bleiben intern; die TUI zeigt nur die stabile Kurzkennung
zur Wiedererkennung. Gruppen ohne externe Identität werden als einzelne Runs
mit kurzem `Run <id>`-Hinweis dargestellt oder bei nur einem Eintrag direkt als
normale Zeile gerendert.

### Cursor

- `a` fokussiert weiterhin zwischen aktuellen Runs und History.
- Im History-Fokus bewegen `↑`/`↓` den Cursor durch sichtbare Gruppen- und
  Run-Zeilen und scrollen bei Bedarf automatisch nach.
- `Enter` oder `Space` klappt die markierte Gruppe auf/zu.
- `←` klappt die Gruppe zu, `→` klappt sie auf.
- `Pos1`/`Ende` springen zum ersten/letzten sichtbaren History-Eintrag.
- Im Fokus auf aktuellen Runs bleiben die bisherigen Scrollfunktionen erhalten.
- Die aktive Zeile erhält eine dezente Status-/Strukturfarbe; die bestehenden
  Ampelfarben für Run-Metriken bleiben unverändert.

Die Hilfezeile wird um Cursor- und Aufklappbedienung ergänzt. Bei 40×18 bleibt
an Stelle eines vollständigen Cursor-Overlays die kompakte Gruppenzeile sichtbar;
die Mindestgröße und vorhandene Quellenkurzansicht bleiben erhalten.

## Umsetzung in drei Schritten

### 1. Gruppiertes History-Modell im Renderer

Betroffene Datei: `llmtop_tui.py`, bei Bedarf `llmtop_metrics.py`.

- Aus der sortierten flachen History einen stabilen Gruppenstrom erzeugen.
- Pro Gruppe Schlüssel, Kurzlabel, Mitglieder und expandierten Zustand halten.
- Aus dem Gruppenstrom sichtbare Zeilen für Kopf, Gruppe und Runs erzeugen.
- `history_offset` von der Rohdatenliste auf diesen sichtbaren Zeilenstrom
  umstellen.
- Gruppen-/Run-Anzahl und Positionsanzeige getrennt ausgeben, damit `100 Runs`
  nicht fälschlich als `100 sichtbare Zeilen` erscheint.

**Abnahme:** 100 History-Runs mit mehreren Sessions zeigen zunächst wenige
Gruppen; beim Expandieren erscheinen alle zugehörigen Einzelzeilen ohne Verlust.

### 2. Cursor und Expand/Collapse in der TUI

Betroffene Dateien: `llmtop_tui.py` sowie vorhandene TUI-Tests/Scratch-Tests.

- `history_cursor` und `history_expanded` im TUI-State ergänzen.
- Cursor nach Sortierung, Refresh und Collapse auf einen gültigen sichtbaren
  Eintrag korrigieren.
- `Enter`/Leertaste sowie Links/Rechts implementieren und vorhandene
  `run_focus`-Navigation nicht verändern.
- Beim Verlassen des History-Fokus Zustand beibehalten; beim Wechsel der
  Sortierspalte Cursor und sichtbaren Offset sicher neu berechnen.
- Pseudo-TTY-Prüfung für 40×18, 80×24 und 120×40 durchführen.

**Abnahme:** Eine Gruppe lässt sich per Cursor öffnen und schließen; alle
Pfeil-/Scrollfunktionen für aktuelle Runs funktionieren weiterhin.

### 3. Dokumentation und Regressionsprüfung

Betroffene Dateien: `README.md`, `status.md`, `version.md`, `llmtop.py` für
die Patch-Version.

- Bedienung, Gruppierungsregeln und Verhalten ohne IDs dokumentieren.
- Tests für gleiche Session, verschiedene Sessions, Chat-Fallback,
  Message-Fallback und fehlende IDs ergänzen beziehungsweise im Scratch
  ausführen.
- Sortierung nach Zeit, Tokens, Kontext, Rate und Dauer mit eingeklappten und
  aufgeklappten Gruppen prüfen.
- Keine Inhalte aus Prompts oder Antworten in Gruppenlabels übernehmen.
- `git diff --check`, Syntaxcheck, `--once`, `--once --no-nvidia` und
  `--version` ausführen.

## Nichtziele

- Keine Löschung oder dauerhafte Änderung der History-Daten.
- Keine Gruppierung über unterschiedliche Quellen hinweg.
- Keine künstlichen Summen oder Durchschnittswerte, die die aktive Sortierung
  verfälschen.
- Keine Pflichtspalte für vollständige IDs in schmalen Tabellen.
- Keine neue Abhängigkeit und keine neue Datenbank.
