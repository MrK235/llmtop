# Buganalyse v1.2.0

## Geprüfter Stand
Statische Analyse von `llmtop.py` sowie Abgleich mit README und `status.md`.
Ausführungstests waren in diesem Modus nicht möglich.

## Priorisierte Befunde

1. **Kleines Terminal überdeckt Inhalte (hoch)**
   Bei der weiterhin erlaubten Mindestgröße 40×8 benötigt das neue Vierbereiche-
   Layout deutlich mehr Zeilen. Der feste Footer auf `h - 1` überschreibt dann
   GPU-, Ollama- oder History-Inhalt. Die Mindestgröße und die dokumentierte
   Darstellung sind damit nicht konsistent.
   - Entscheidung für die Umsetzung: Mindesthöhe passend anheben oder einen
     kompakten, expliziten Fallback ohne alle Detailzeilen zeichnen.

2. **TUI kann während Messungen nicht reagieren (mittel)**
   HTTP-Abfragen (je bis zu 2 s) und `nvidia-smi` (bis zu 4 s) laufen im
   Eingabe-/Render-Loop. Dadurch reagieren `q`, `r` und Resize während einer
   langsamen Messung erst nach deren Ende.
   - Für eine spätere technische Version: Messung vom Render-/Input-Loop
     entkoppeln oder Timeouts und Refreshablauf gezielt überarbeiten.

3. **`OLLAMA_HOST`-Bindeadressen sind keine Client-URLs (mittel)**
   Werte wie `:11434` oder `0.0.0.0:11434` werden zu nicht erreichbaren URLs.
   - Bei einer Fehlerkorrektur: diese Formen normalisieren, etwa auf
     `127.0.0.1:11434`, und dokumentieren.

4. **Modellanzeige vertraut unvalidierten API-Typen (niedrig)**
   Ein unerwarteter Typ in `expires_at` kann in `model_lines()` bei
   `exp.replace(...)` einen `AttributeError` auslösen; nur `ValueError` wird
   behandelt.
   - Bei einer Fehlerkorrektur: Typ prüfen oder `TypeError`/`AttributeError`
     auffangen.

5. **Ausführung von v1.2.0 noch nicht bestätigt (hoch)**
   Der letzte erfolgreiche Lauf war vor dem Layout-Umbau. Syntax, TUI-Rendering
   mit 80×24/40×8, Farben und die beiden GPU-Pfade müssen gegen den aktuellen
   Stand geprüft werden.

## Nicht als Bug eingestuft
- Kein Scrollen bei vielen Modellen und der reine History-Platzhalter sind
  dokumentierte Grenzen beziehungsweise bewusster Scope.
- Host-GPU-Werte sind nicht ausschließlich Ollama zurechenbar.

## Empfohlenes Vorgehen
1. Zuerst die Tests aus dem folgenden Abschnitt ausführen und Befunde 1 sowie 5
   verifizieren.
2. Danach ausschließlich den bestätigten Layoutfehler für kleine Terminals
   beheben; die übrigen Punkte als getrennte technische Fehlerkorrektur planen.
3. `README.md` und `status.md` nach der Entscheidung zu Mindestgröße/Fallback
   aktualisieren.

## Prüfung
```bash
python3 -m py_compile llmtop.py
python3 llmtop.py --version
python3 llmtop.py --once
python3 llmtop.py --once --no-nvidia
```
Zusätzlich TUI im Pseudo-TTY bei 80×24 und 40×8 starten, `h`, `r`, `+`, `-` und
`q` prüfen sowie den TUI-Lauf in einem echten Terminal visuell abnehmen.
