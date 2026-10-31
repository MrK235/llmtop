# Review der aktuellen Version

## Befund
`otop.py` ist funktional als Einzeldatei angelegt, doch die vorliegende Implementierung und die Dokumentation sind nicht konsistent: Code und README nennen 1.1.0, `status.md` beschreibt 1.0.0; zudem fehlt die in README/Status referenzierte `prompt-1.1.0.md`.

## Priorisierte Verbesserungsvorschläge
1. **GPU-Erfassung und Anzeige vor neuen Funktionen stabilisieren.** `collect_gpus()` filtert Nicht-NVIDIA-GPUs heraus, wählt bei mehreren NVIDIA-GPUs willkürlich den zweiten Eintrag und fällt bei leerem `nvidia-smi` nicht auf sysfs zurück. Das widerspricht der dokumentierten Quellenkette und macht `--no-nvidia` praktisch wirkungslos. Einheiten für NVIDIA (bereits MiB) und sysfs (Bytes) müssen vor der Ausgabe vereinheitlicht werden. Nicht-numerische Auslastung sowie Datei-Lesefehler müssen ohne TUI-Absturz behandelt werden.
2. **TUI-/Snapshot-Logik korrigieren.** Bei erfolgreichem `/api/version` und fehlgeschlagenem `/api/ps` darf nicht gleichzeitig „kein Modell geladen“ erscheinen. Die CPU-Vorwerte müssen nach jedem Refresh aktualisiert werden. VRAM-/Power-Zeilen sollten aus tatsächlich verwendeten, formatierten Werten entstehen; derzeit bleiben Teile der berechneten Snapshot-Information ungenutzt. Das Hilfe-Overlay zeichnet gegenwärtig nur den Rahmen, nicht den Hilfetext.
3. **Dokumentation auf einen Release-Stand bringen.** Eine Versionsquelle festlegen (`VERSION`), `README.md`, `status.md` und `version.md` darauf abgleichen, nicht vorhandene Dateien aus Verweisen entfernen oder gezielt nachliefern sowie Beispiele und Changelog korrigieren. Dokumentierte Tests erst nach Wiederholung gegen den tatsächlichen Code als gültig markieren.

## Betroffene Dateien
- `otop.py`: Punkte 1 und 2.
- `README.md`, `status.md`, `version.md`: Punkt 3.

## Prüfung nach Umsetzung
- Syntaxcheck und `--version`.
- `--once` mit Mock-Antworten für `/api/ps`-Fehler, nicht-numerische NVIDIA-Werte und sysfs-Fallback.
- Pseudo-TTY-Test für CPU-Refresh, VRAM-/Power-Ausgabe und sichtbares Hilfe-Overlay.
- Dokumentationsabgleich aller Versions- und Dateiverweise.
