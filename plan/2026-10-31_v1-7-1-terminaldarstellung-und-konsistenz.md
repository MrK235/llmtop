# Plan: otop 1.7.1 – terminalfeste Darstellung und Datenkonsistenz

## Ziel

Version 1.7.1 ist ein Patch-Release. Sie beseitigt nachweisbare Darstellungsfehler der TUI bei der dokumentierten Mindestgröße von 40×18, ordnet den `--once`-Snapshot entsprechend der Dokumentation und synchronisiert veraltete Versionsangaben. Es kommen keine neuen Sensoren, Optionen oder Abhängigkeiten hinzu.

## Geprüfter Ist-Stand

- Arbeitsbaum und Repository sind noch unversioniert (keine Commits, keine Tags); alle vorhandenen Dateien sind als `??` gelistet.
- `VERSION`, `README.md`, `status.md` und `version.md` nennen überwiegend 1.7.0. `README.md` nennt in der Beschreibung der TUI-Kopfzeile noch 1.6.1; `status.md` protokolliert für den Versionsaufruf ebenfalls fälschlich 1.6.1.
- Syntaxcheck, `--version`, `--once`, `--once --no-nvidia` und der vorhandene Test `test_otop.py` waren erfolgreich. Der Live-Snapshot liefert plausible Hostwerte; die sysfs-Variante zeigt erwartungsgemäß die AMD-iGPU statt der per `nvidia-smi` erfassten NVIDIA-GPU.
- Ein Pseudo-TTY bei 80×24 zeigt die Werte vollständig und ohne Überlappung.
- Ein Pseudo-TTY bei der zugesagten Mindestgröße 40×18 zeigt jedoch einen fehlerhaften Bildschirm: Die fest unten platzierte History wird über bereits gezeichnete Modellzeilen gelegt. Dadurch entsteht beispielsweise eine Mischzeile aus Modellname, `System-Snapshots` und Rest von `unload in …`.
- Bei 40 Spalten wird zusätzlich der Intervalltext in die Kopfzeile geschrieben, bevor diese endet; dadurch ist die Kopfzeile inhaltlich abgeschnitten statt gezielt verdichtet.
- `snapshot_lines()` fügt RAM entgegen Kommentar und README erst nach Modellen, Runs und Historie ein. Der `--once`-Ausgabeblock ist damit nicht in der dokumentierten Reihenfolge System → GPU → Ollama → History und RAM steht nicht direkt bei CPU.

## Umsetzung

### 1. TUI-Layout vor dem Zeichnen vollständig einpassen

1. Die benötigten Zeilen je Bereich vorab berechnen und Footer sowie History-Zeilen verbindlich reservieren.
2. Modellkarten nur zeichnen, wenn für die vollständige Karte mit zwei Zeilen Platz vorhanden ist. Nicht passende Karten nicht teilweise zeichnen; ein kurzer, klarer Hinweis benennt ausgeblendete Modelle.
3. Für 40×18 einen kompakten, aber konsistenten Fallback verwenden: System- und GPU-Kernwerte, Ollama-Status sowie History/Fußzeile bleiben ohne Überschneidung sichtbar. Metadaten dürfen hierfür gezielt gekürzt werden.
4. Die bisherige nachträgliche Verschiebung von `history_row`, die bereits gezeichnete Modellzeilen überschreibt, entfernen.

### 2. Schmale Zeilen gezielt verdichten

1. Die Kopfzeile und den Intervalltext nur dann nebeneinander ausgeben, wenn beide vollständig passen; sonst eine definierte Kurzform verwenden oder die sekundäre Intervallanzeige ausblenden.
2. Sensor- und Modellzeilen weiterhin über die vorhandene sichere Ausgabefunktion kürzen, jedoch keine unabhängig positionierten Textteile mehr in denselben Platz schreiben.
3. Die Mindestgröße 40×18 beibehalten. Unterhalb davon bleibt der bestehende eindeutige Hinweis maßgeblich.

### 3. `--once` und Dokumentation konsistent machen

1. Die Snapshot-Erzeugung in die dokumentierte Reihenfolge bringen: System mit CPU und RAM zusammen, GPU, Ollama mit Runs und Modellen, danach History. Dabei keine Messwerte, Datenquellen oder Formeln ändern.
2. `VERSION` auf 1.7.1 erhöhen und `README.md`, `status.md` sowie `version.md` auf denselben Release-Stand bringen.
3. Veraltete 1.6.1-Beispiele und den unzutreffenden Prüfvermerk ersetzen; den Befund zur behobenen 40×18-Darstellung im Changelog und Status knapp festhalten.

## Tests

| Fall | Erwartung |
|---|---|
| `python3 -m py_compile otop.py` | fehlerfrei |
| `python3 otop.py --version` | `otop 1.7.1`, Exit 0 |
| `python3 otop.py --once` | CPU und RAM zusammen im Systemblock; keine Ausnahme |
| `python3 otop.py --once --no-nvidia` | fehlerfrei über den sysfs-Pfad |
| vorhandener Test in temporärem Verzeichnis | Run-Metrikformatierung weiterhin korrekt |
| Pseudo-TTY 80×24 | vollständige reguläre Ansicht ohne Regression |
| Pseudo-TTY 40×18 mit mindestens zwei geladenen Modellen | keine gemischten oder überzeichneten Zeilen; Footer und History bleiben lesbar |
| Pseudo-TTY 40×17 | ausschließlich der Mindestgrößenhinweis |
| schmale Breite 40 Spalten | Kopfzeile enthält keine kollidierenden Textteile |
| `git diff --check` | keine Whitespace-Fehler |

## Nichtziele

- Keine Änderung an Sensorquellen, GPU-/VRAM-Formeln, Offload-Farben, Collector, History-Schema oder Ollama-API.
- Keine neuen CLI-Optionen, Tastenkürzel, Dateien, Abhängigkeiten oder Installation.
- Keine Änderungen außerhalb des Projektordners und kein Commit oder Tag ohne gesonderte Freigabe.

## Abnahme

Die TUI ist bei 40×18 lesbar und frei von Überlappungen, auch wenn mehr Modellkarten vorhanden sind als Platz. `--once` gruppiert RAM direkt bei CPU. Alle sichtbaren Versionsangaben und der dokumentierte Prüfstatus entsprechen 1.7.1.
