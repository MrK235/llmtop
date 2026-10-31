# Ollama-Cyan und Programm-Reload

## Ziel

1. Im Ollama-Bereich werden Modellname, das Wort **„Speicher“** sowie die
   öffnende und schließende Klammer des geteilten Speicherbalkens cyan
   dargestellt. Der GPU-Anteil bleibt cyan, der CPU-Anteil weiterhin gedimmt.
2. Die Taste **`r` / `R`** aktualisiert nicht mehr nur Messwerte, sondern
   startet `otop` mit denselben Kommandozeilenargumenten neu.

## Umsetzung

1. **Ollama-Farben in `otop.py`**
   - `model_card()` für den Modellnamen das vorhandene Cyan-Attribut
     `colors["gpu"]` verwenden.
   - `Speicher ` und beide Balkenklammern `[` / `]` mit demselben
     Cyan-Attribut zeichnen.
   - GPU-Blöcke und GPU-Text bleiben Cyan; CPU-Punkte und CPU-Text bleiben
     gedimmt. Fehlende Speicherwerte verwenden den cyanfarbenen Rahmen, aber
     gedimmten Leerinhalt und `GPU/CPU n/a`.
   - Bereichsüberschriften und übrige Farbrollen bleiben unverändert.

2. **Sicheren Reload für `r` / `R`**
   - Im curses-Loop bei `r`/`R` nicht länger `next_refresh = 0` setzen,
     sondern einen Reload-Rückgabewert an `_run_tui()` geben.
   - Nach dem Rücksprung aus `curses.wrapper()` (also nach Terminal-Cleanup)
     `os.execv()` mit dem aktuellen Python-Interpreter und `sys.argv`
     aufrufen. Dadurch bleiben `--host`, `--interval` und `--no-nvidia`
     erhalten.
   - `q`/`Q` bleibt normales Beenden. `--once` bleibt unverändert, da dort
     keine Tasteneingabe existiert.
   - Fußzeile, Hilfe-Overlay und README ändern den Text von „refresh“ zu
     „Programm neu laden“.

3. **Version und Dokumentation**
   - Patch-Version erhöhen.
   - README, `status.md` und `version.md` auf Cyan-Rollen und Reload-Taste
     abgleichen.

## Prüfung

- Mock-Rendering: Modellname, `Speicher`, `[` und `]` tragen Cyan; CPU-Segment
  bleibt gedimmt.
- Pseudo-TTY: `r` führt zu einem Neustart ohne curses-Artefakte; `q` beendet
  weiterhin normal. Die Ausführung wird mit einem kurzen Timeout begrenzt.
- Syntaxcheck sowie `--version`, `--once` und `--once --no-nvidia` ausführen.
