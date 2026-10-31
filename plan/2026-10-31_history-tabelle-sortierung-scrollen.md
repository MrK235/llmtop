# Plan: Scrollbare, sortierbare Run-History als Tabelle

## Ziel

Die Run-History wird in der normalen curses-TUI als kompakte Tabelle angezeigt.
Sie hält weiterhin höchstens 100 finale Runs vor, lässt sich per Tastatur durch
alle sichtbaren Spalten auf- und absteigend sortieren und innerhalb der
Ergebnisliste scrollen. `--once` bleibt eine einfache, nicht-interaktive
Snapshot-Ausgabe.

## Befund und Datenhaltungsentscheidung

- Die Persistenz ist bereits passend begrenzt: `DEFAULT_RUN_HISTORY_LIMIT =
  100`; `append_run_history()` dedupliziert nach Quelle und Run-ID und schreibt
  atomar nach `runs.jsonl`.
- Die Anzeige beschränkt `load_run_history()` momentan auf zehn Datensätze und
  `_draw()` rendert davon ebenfalls zehn Zeilen. Es gibt keinen UI-Zustand für
  Sortierung oder Scrollposition.
- Bei höchstens 100 kleinen, datensparsamen JSON-Objekten sind Laden,
  Deduplizieren und Sortieren in Python praktisch sofort erledigt. JSONL ist
  zudem bereits fehlertolerant, atomar geschrieben und benötigt keine
  zusätzliche Installation oder Migration.

**Entscheidung: keine Datenbank.** SQLite wäre zwar Teil der Standardbibliothek,
brächte für 100 Zeilen aber unnötige Schema-, Migrations- und
Nebenläufigkeitskomplexität. Die bestehende JSONL-Datei bleibt die alleinige
Datenquelle.

## Tabellendesign und Bedienung

Die Tabelle enthält nur bereits datensparsam gespeicherte bzw. daraus
berechnete Werte:

```text
History (37/100)  Sortierung: Ende ↓
Zeit              Quelle       Modell              Status      Tokens   Kontext       Tok/s   Dauer
31.10 22:38       Open WebUI   ministral-3:3b      completed      875    875/32.8k 3%  86.8    3.5 s
```

- Sortierbare Spalten: Abschlusszeit, Quelle, Modell, Status, Gesamttoken,
  Kontextverbrauch, Ausgabe-Rate und Gesamtdauer.
- Die Spalte **Kontext** zeigt `genutzt/Limit` plus Prozentwert, etwa
  `875/32.8k 3 %`. Fehlt der Verbrauch oder das Limit, zeigt sie transparent
  `n/a` beziehungsweise `875/n/a`; ein Verbrauch über dem Limit wird wie in
  der bisherigen Anzeige als `über Limit` markiert. Das Limit stammt weiter
  aus dem Run oder dem zugehörigen geladenen Modell, es werden keine Werte
  geschätzt.
- Fehlende numerische Werte sortieren stets hinter vorhandenen Werten; bei
  Textwerten wird stabil und ohne Beachtung der Groß-/Kleinschreibung
  sortiert. Gleiche Werte werden zuverlässig über Abschlusszeit und Run-ID
  aufgelöst.
- Standard bleibt Abschlusszeit absteigend (neuester zuerst).
- `Tab` / `Shift-Tab`: nächste/vorherige Sortierspalte; `s`: Richtung
  umschalten. Die Kopfzeile zeigt aktive Spalte und Richtung.
- `↑` / `↓`, `Bild↑` / `Bild↓`, `Pos1` / `Ende`: innerhalb der Tabelle
  scrollen. Beim Wechsel der Sortierung springt die Anzeige zum ersten
  Eintrag.
- Die Fußzeile und das Hilfe-Overlay dokumentieren die neuen Tasten. Bestehende
  Tasten bleiben unverändert.

Bei 40×18 bleibt die kompakte Ansicht überlappungsfrei: Sie zeigt eine
gekürzte Tabellenansicht mit Kopfzeile und so vielen Datenzeilen wie passen.
Bei noch engerer Breite werden weniger prioritäre Spalten gezielt ausgelassen,
nicht umgebrochen; Zeit, Modell, Status und Kontext behalten Vorrang vor
Quelle, Tokens, Rate und Dauer. Die Mindestgröße 40×18 bleibt unverändert.

## Umsetzung

### 1. History-Lesen und Sortierung in `otop.py`

- `load_run_history()` für die interaktive Ansicht bis zu 100 finale,
  deduplizierte Einträge laden lassen; die Speicherung bleibt unverändert auf
  100 begrenzt.
- Kleine Hilfsfunktionen für Sortierschlüssel und stabile Sortierung ergänzen;
  vorhandene Formatierungs-, Metrik- und Kontextfunktionen weiterverwenden.
  Der Kontextsortierschlüssel verwendet zunächst den prozentualen Verbrauch
  bei vorhandenem Limit, sonst die genutzten Token; fehlende Werte folgen
  zuletzt.
- Keinen Datenbankcode, keine Abhängigkeiten und keine Änderung am
  Collector-/JSONL-Schema einführen.

### 2. Tabellenrenderer und TUI-Zustand

- Im TUI-State Sortierspalte, Sortierrichtung und Scrolloffset ergänzen.
- Den bisherigen History-Block durch einen spaltenausgerichteten Renderer mit
  Tabellenkopf, sichtbarem Ausschnitt und Anzeige von Position/Gesamtzahl
  ersetzen.
- Höhe dynamisch aus dem verbleibenden Platz bestimmen; Modellkarten weiter
  nur so weit zeichnen, dass History und Fußzeile nicht überzeichnet werden.
- Tastaturbehandlung für Navigation und Sortierung ergänzen, Offsets auf
  gültige Grenzen begrenzen und bei Refresh/Sortrichtungswechsel konsistent
  halten.
- `--once` weiterhin neuester zuerst und ohne interaktive Tabellensteuerung
  ausgeben; seine bisherige Detailausgabe bleibt lesbar.

### 3. Tests, Dokumentation und Versionierung

- Scratch-Tests für alle Sortierschlüssel einschließlich Kontextverbrauch,
  fehlende Kontextwerte, stabile Gleichstände, Scrollgrenzen und die
  Begrenzung auf 100 Einträge ausführen.
- Pseudo-TTY-Tests für mindestens 80×24 und 40×18 durchführen: Tabellenkopf,
  Scrollen, Sortierwechsel, Fußzeile und Hilfe dürfen sich nicht überzeichnen.
- `README.md` (History-Anzeige und Tasten), `status.md` und `version.md`
  aktualisieren; `VERSION` als Minor-Release synchronisieren.
- Vorgeschriebene Prüfungen ausführen: `python3 -m py_compile otop.py`,
  `python3 otop.py --once`, `python3 otop.py --once --no-nvidia`,
  `python3 otop.py --version`, gezielter Diff und `git diff --check`.

## Abnahme

- Die Datei `runs.jsonl` enthält höchstens 100 finale Runs; keine Datenbank
  wird angelegt oder benötigt.
- Die TUI zeigt die History als ausgerichtete Tabelle und kann alle bis zu 100
  Einträge erreichen.
- Jede aufgeführte Spalte ist auf- und absteigend sortierbar; fehlende Werte
  verursachen weder Absturz noch eine irreführende Sortierung.
- Navigation, Sortierung, bestehende TUI-Tasten und das 40×18-Layout bleiben
  ohne Überzeichnung funktionsfähig.
