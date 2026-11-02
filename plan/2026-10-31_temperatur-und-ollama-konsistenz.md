# Visuelle Konsolidierung: Temperaturen und Ollama

## Befund aus dem aktuellen TUI-Lauf

Die TUI wurde mit zwei geladenen Modellen, NVIDIA-GPU und 80 Spalten erfasst.
Dabei zeigen sich zwei visuelle Brüche:

1. **Temperaturwerte** belegen zusätzliche eigene Zeilen ohne Balken. Zwischen
   RAM und GPU beziehungsweise GPU und VRAM entsteht dadurch ein anderer
   Rhythmus als bei den übrigen Sensorzeilen.
2. **Ollama-Speicher** verwendet Cyan (`head`) für GPU-Balken und GPU-Prozent,
   gedimmtes Grau für CPU-Balken und CPU-Prozent, während Modellname,
   Überschriften und weitere Informationen dieselbe Cyan-Farbe verwenden.
   Die Farbsemantik ist dadurch nicht klar genug. Außerdem zeigt der Text nur
   VRAM und Gesamtgröße, nicht den tatsächlichen CPU-RAM-Anteil.

## Zielbild

Temperaturen werden als farbige Zusatzwerte in bestehende Sensorzeilen
integriert, nicht als eigenständige Zeilen:

```text
 System ────────────────────────────────────────────────────────────────────
 CPU       [████░░░░░░░░░░░░]   4.7 %  Load 1.80 · 24 Kerne · Temp 41.9 °C
 RAM       [█████░░░░░░░░░░░]  27.7 %  22.0 / 30.5 GiB frei

 GPU ───────────────────────────────────────────────────────────────────────
 GPU0      [░░░░░░░░░░░░░░░]   0.0 %  NVIDIA RTX 5070 · Temp 38.0 °C
 VRAM      [██████████████░░]  86.7 %  7068 / 8151 MiB
 Power     [█░░░░░░░░░░░░░░░]   3.4 %  4.0 W / 115 W

 Ollama ────────────────────────────────────────────────────────────────────
 qwen3.5:9b       9.0B Q4_K_M · ctx 32768 · llamacpp       unload in 22:23
 Speicher  [█████████████████████░░░]  GPU 88 % 5.6 GiB | CPU 12 % 0.8 GiB
```

Die Beispielzeichen stehen nur für die Geometrie. Die bestehende
Terminal-kompatible Balkendarstellung bleibt ASCII-basiert.

## Farbregeln

| Element | Darstellung |
|---|---|
| Bereichsüberschrift | Cyan, fett |
| Modellname | neutral/fett, **nicht** Cyan |
| GPU-/VRAM-Anteil des Ollama-Modells | Cyan, Balken und Textwert identisch |
| CPU/RAM-Anteil des Ollama-Modells | gedimmt, Balken und Textwert identisch |
| Statische Metadaten, Quellen, Größen | gedimmt |
| Auslastungsbalken | bestehende Grün/Gelb/Rot-Skala |
| Temperaturwert | Grün <70 °C, Gelb ab 70 °C, Rot ab 85 °C |
| Unload unter 5 Minuten / abgelaufen | Gelb / Rot |

Damit unterscheiden Farbe und Text jeweils klar zwischen Titel, Sensorwert,
GPU- und CPU-Anteil sowie Sekundärinformation.

## Umsetzung

1. **Temperaturzeilen einordnen (`llmtop.py`)**
   - Die separate lokale Zeichenhilfe `temperature()` entfernen.
   - `sensor()` um optionale, segmentweise gerenderte Zusatzinformation
     erweitern (Text plus Attribut), damit `Temp X °C` am Ende der CPU- und
     GPU-Zeile erscheint.
   - CPU-Quelle in den gedimmten Zusatztext aufnehmen; GPU-Name für die
     Darstellung auf eine kompakte Form kürzen, falls die Temperatur sonst
     nicht mehr in die Zeile passt. Die volle Quelle bleibt in `--once`.
   - Die Temperaturerfassung und die farbigen Schwellenwerte bleiben
     unverändert.

2. **Ollama-Modellkarte vereinheitlichen (`llmtop.py`)**
   - Farbrollen in `_init_colors()` trennen: Bereichstitel, Modellname und
     GPU-Anteil erhalten unterschiedliche Attribute.
   - Geteilten Speicherbalken und Textwerte aus derselben Berechnung speisen.
     Neben `size_vram` wird `size - size_vram` als CPU-Anteil formatiert.
   - GPU-Segment und `GPU x % / y GiB` konsequent Cyan zeichnen; CPU-Segment
     und `CPU x % / y GiB` konsequent gedimmt. Bei fehlender Größe neutralen
     Fallback verwenden.
   - Metadaten und Unload-Status mit reserviertem Abstand zeichnen, damit sie
     bei mittleren Breiten nicht optisch aneinanderstoßen.

3. **Layout und Dokumentation**
   - Nach dem Wegfall der zwei Temperaturzeilen die Mindesthöhe wieder auf
     40×18 reduzieren, sofern die TUI bei 40×18 alle Grundbereiche einschließlich
     Footer ohne Überdeckung zeigt.
   - Patch-Version erhöhen; README, Status und Changelog auf die integrierten
     Temperaturen, Farbrollen und CPU-RAM-Größe abgleichen.
   - Keine Änderung an Sensorquellen, API-Abfragen, CLI oder `--once` außer
     einer möglichen Textformatierung der schon vorhandenen Temperaturen.

## Prüfung

- Mock-Rendering: CPU- und GPU-Temperatur stehen auf den jeweiligen
  Sensorzeilen; es entstehen keine eigenständigen Temperaturzeilen.
- Mock-Modell mit 50/50, 100/0, 0/100 und fehlender Größe: Segmentbreiten,
  Farbattribute sowie GPU-/CPU-Größen prüfen.
- Pseudo-TTY bei 80×24 und 40×18 auf Freiraum, Lesbarkeit und Footer prüfen.
- Live TUI mit NVIDIA und `--no-nvidia`; `--once` weiter auf Temperaturwerte
  und unveränderte Informationsvollständigkeit prüfen.
