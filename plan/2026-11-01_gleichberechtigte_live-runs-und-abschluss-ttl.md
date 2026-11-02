# Plan: Gleichberechtigte Pi-/Open-WebUI-Live-Runs mit 10-Sekunden-Abschlussanzeige

## Ziel

Die Anzeige **Aktuelle Runs** soll ausschließlich den aktuellen Arbeitszustand
zeigen:

- aktive Pi- und Open-WebUI-Runs laufen gleichberechtigt und parallel,
- ein Abschluss bleibt nur **10 Sekunden** als Ergebnis sichtbar,
- danach verschwindet er aus `run.jsonl`, bleibt aber dauerhaft in der
  begrenzten Run-History,
- ein WebUI-Abschluss darf weder einen aktiven noch einen gerade abgeschlossenen
  Pi-Run visuell verdrängen – und umgekehrt.

## Vorbefund

Der Collector trennt seit 2.1.2 die HTTP-Eingänge korrekt in
`/v1/runs/pi` und `/v1/runs/open-webui`; beide nutzen denselben Bearer-Token
und erzwingen die passende `source`. Die Run-History dedupliziert bereits nach
`(source, run_id)`.

Die aktuelle Überlagerung entsteht im Live-Pfad:

1. `write_live_run()` behält den letzten finalen Run je Quelle unbegrenzt.
2. `load_run_events()` verwirft nur nicht-finale, verwaiste Runs nach 90 s.
   Finale Ergebnisse haben keine Ablaufzeit.
3. Der Renderer gruppiert Pi vor WebUI. Das schützt Pi zwar vor Verdrängung,
   gibt Pi aber eine andere Darstellungspriorität und verdeckt bei kleiner
   Terminalhöhe WebUI-Einträge hinter den Pi-Zeilen.
4. Jeder Run benötigt derzeit zwei Zeilen. Bei geringer Höhe passen aktive und
   finale Einträge beider Quellen nicht gleichzeitig in den sichtbaren Bereich.

Die Datenquellen sind daher nicht das Hauptproblem; Retention und Layout sind
es.

## Architekturentscheidung

Keine neuen Dateien, keine neue Datenbank und keine Änderungen an den
Collector-Authentifizierungsregeln.

### Einheitliche Zustandsregel

`llmtop_metrics.py` erhält zusätzlich zu `DEFAULT_RUN_MAX_AGE` die feste
Konstante:

```python
DEFAULT_FINAL_RUN_AGE = 10.0
```

- **Aktiv** (`running`): sichtbar bis zum letzten Heartbeat plus 90 s.
- **Final** (`completed`, `error`, `cancelled`): sichtbar bis `finished_at`
  plus 10 s.
- Fehlende oder ungültige Abschlusszeit bei finalen Daten wird beim bisherigen
  Normalisieren mit der Empfangszeit ergänzt und kann daher ebenfalls sauber
  ablaufen.
- Das Entfernen passiert ausschließlich beim Laden von `run.jsonl` unter der
  bestehenden Sperre und schreibt die bereinigte Datei atomar zurück.
- `runs.jsonl` und seine Retention von 100 Einträgen bleiben unverändert.

Damit erhalten Pi und Open WebUI exakt dieselben Rechte: Beide dürfen aktive
Runs und ein frisches Abschlussresultat liefern; keines erhält eine dauerhafte
Live-Position.

### Gleichberechtigte Darstellung

`llmtop_tui.py` teilt die geladenen Live-Runs zuerst nach Status und dann nach
Quelle auf:

1. aktive Pi-Runs,
2. aktive Open-WebUI-Runs,
3. sonstige aktive Quellen,
4. frische finale Pi-Runs,
5. frische finale Open-WebUI-Runs,
6. sonstige frische finale Quellen.

Die Reihenfolge **aktiv vor final** ist die einzige Priorität. Pi und Open
WebUI erhalten innerhalb derselben Statusklasse keine Sonderbehandlung; bei
identischer Zeit entscheidet nur die stabile Quelle/Run-ID als Sortierschlüssel.

Die Anzeige erhält zwei gleichartige Unterüberschriften:

```text
── Aktuelle Runs ───────────────────────────────────────────
 Pi (aktiv 1 · Ergebnis 1)
   Pi/ollama      qwen3.5:4b       aktiv
   Pi/ollama      qwen3.5:4b       erledigt · vor 6 s
 Open WebUI (aktiv 1 · Ergebnis 1)
   Open WebUI/... qwen3.5:9b       aktiv
   Open WebUI/... qwen3.5:9b       erledigt · vor 4 s
```

- Vollansicht: Detail-/Kontextzeile nur, wenn nach beiden Quellen noch Platz
  vorhanden ist. Sonst bleibt die einzeilige Quelle-Modell-Status-Zeile.
- 40×18-/80×24-Kompaktansicht: genau eine Kurzzeile je vorhandener Quelle mit
  `aktiv N · Ergebnis N`; bei einem einzigen Run zusätzlich Modell und Status.
  Es gibt keine Pi-Vorziehung.
- `a` und die bestehenden Scrolltasten scrollen weiterhin nur den Live-Bereich,
  wenn er größer als der reservierte Bereich ist. Die Zähler bleiben sichtbar.
- Die History bleibt eine gemeinsame Tabelle; ihre bereits eingeführte
  Quellen-/Provider-Spalte bleibt in jeder Breite erhalten.

## Adapter-Gleichheit

Die vorhandenen Adapter werden nur auf gemeinsame Minimalgarantien geprüft,
nicht architektonisch umgebaut:

| Eigenschaft | Pi | Open WebUI |
|---|---|---|
| Collector-Pfad | `/v1/runs/pi` | `/v1/runs/open-webui` |
| Authentifizierung | gleicher Bearer-Token | gleicher Bearer-Token |
| Start, Heartbeat, Abschluss | ja | ja |
| Datensparsame Felder | Quelle, Provider, Modell, Zeiten, explizite Usage | identisch |
| Collector-Ausfall | No-op | No-op |

Der Pi-Adapter darf weiter pro Modellturn senden; der Open-WebUI-Adapter darf
identische direkte Filterdurchläufe innerhalb seines kurzen Debounce-Fensters
zusammenlegen. Beide schicken keinen Prompt, keine Antwort, keine Session-ID
und keine Credentials.

## Umsetzung in drei Schritten

### 1. Finale Live-Retention auf 10 Sekunden begrenzen

Betroffene Datei: `llmtop_metrics.py`.

1. Konstante `DEFAULT_FINAL_RUN_AGE = 10.0` ergänzen.
2. In `load_run_events()` finale Runs anhand von `finished_at` berechnen und
   nach 10 Sekunden aus `fresh` entfernen.
3. Die bestehende atomare Bereinigung von `run.jsonl` verwenden.
4. `write_live_run()` behält weiterhin den letzten Abschluss je Quelle; ein
   neuer aktiver Run entfernt ihn nicht vorzeitig.

**Abnahme:** Ein Pi- und ein WebUI-Abschluss sind unmittelbar sichtbar, nach
11 Sekunden aus `run.jsonl` entfernt und weiterhin beide in `runs.jsonl`.

### 2. Status- und quellenneutrales TUI-Layout

Betroffene Datei: `llmtop_tui.py`.

1. Lokale Statuspartition `aktiv` versus `Ergebnis` erstellen.
2. Zwei gleich formatierte Quellenblöcke für Pi und Open WebUI zeichnen.
3. Sichtbare Zeilen zunächst fair je Quelle reservieren; danach freien Platz
   mit weiteren Runs belegen.
4. Kompaktansicht auf Quellensummen umstellen, ohne eine Quelle vorzuziehen.
5. Scroll-Offset gegen die tatsächlich gerenderte Reihenfolge begrenzen.

**Abnahme:** Bei gleichzeitigem Pi- und WebUI-Run zeigt die TUI beide aktiven
Runs; bei einem neuen Pi-Run bleibt sein vorheriges Ergebnis höchstens zehn
Sekunden sichtbar und verdrängt keinen WebUI-Run.

### 3. Adapter-, TTY- und Regressionsprüfung

Betroffene Dateien: `pi/llmtop_run_metrics.ts`,
`open_webui/llmtop_run_metrics.py`, `README.md`, `status.md`, `version.md`,
`llmtop.py` nur für die Versionsanhebung auf `2.1.4`.

1. In Scratch-Dateien Ereignisse für Pi und WebUI mit aktiven/finalen Zuständen
   und kontrollierten UTC-Zeitstempeln erzeugen.
2. Collector-Endpunkte erneut gegen falsche Quelle prüfen.
3. Mit Pseudo-TTY bei 40×18, 80×24 und mindestens 120×32 prüfen, dass Quelle,
   Status und beide parallelen aktiven Runs sichtbar sind.
4. Einen echten Pi-Ollama-Run und einen echten Open-WebUI-Run parallel starten;
   ausschließlich Feldnamen, Status und Zähler prüfen.
5. Nach 11 Sekunden `run.jsonl`, nach TUI-Refresh die Anzeige und danach die
   weiterhin vorhandene History prüfen.
6. Dokumentation, Changelog und `VERSION` auf `2.1.4` synchronisieren;
   `git diff --check`, Syntax- und Standard-CLI-Tests ausführen.

## Nichtziele

- Keine dauerhafte Live-Anzeige finaler Runs.
- Keine neue Quelle, kein Reverse Proxy und keine zusätzliche Abhängigkeit.
- Keine Änderung der History-Retention oder Speicherung von Prompt-/Antworttext.
- Keine unterschiedliche Priorität, Berechtigung oder Geheimnisverwaltung für
  Pi und Open WebUI.
