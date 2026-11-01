# Globale Farbsyntax und Ollama-Sensorraster

## Ziel
Eine einheitliche, globale Farbsyntax macht die TUI unabhängig vom Bereich
lesbar. Der Ollama-Bereich übernimmt das Raster der CPU-/GPU-Sensorzeilen.
Sein Speicherbalken wird vollständig mit `#`-Segmenten dargestellt: GPU und
CPU erhalten unterschiedliche, konsistente Farben statt Cyan und grauer
Punkte.

## Globale Farbsyntax

| Rolle | Farbe / Attribut | Verwendung |
|---|---|---|
| Struktur | Cyan, fett | Kopfzeile, Bereichsüberschriften, feste Labels, Balkenrahmen |
| Live-Auslastung normal/warnend/kritisch | Grün / Gelb / Rot, fett | CPU, RAM, GPU, VRAM, Power nach vorhandenen Schwellenwerten |
| Temperatur normal/warnend/kritisch | Grün / Gelb / Rot, fett | Temperaturwerte nach 70/85 °C |
| GPU-Speicheranteil | Cyan, fett | GPU/VRAM-`#` und zugehöriger Wert im Ollama-Balken |
| CPU-Speicheranteil | Magenta, fett | CPU/RAM-`#` und zugehöriger Wert im Ollama-Balken |
| Sekundärinformation | Gedimmt | Quellen, Größen, Modellmetadaten, nicht aktive Bereiche |
| Fehler | Rot, fett | API- und Sensorfehler |

Grün, Gelb und Rot werden ausschließlich als Statusfarben verwendet. Cyan und
Magenta kennzeichnen ausschließlich die Speicherzuordnung. Jeder farbige Wert
bleibt zusätzlich mit Text (`GPU`, `CPU`, Prozent und Größe) verständlich.

## Zielbild

```text
 CPU       [#####---------------]  24.1 %  Load 1.80 · 24 Kerne · Temp 42.0 °C
 GPU0      [##------------------]  11.0 %  NVIDIA RTX 5070 · Temp 38.0 °C

 Ollama ─────────────────────────────────────────────────────────────────────
 qwen3.5:9b  9.0B Q4_K_M · ctx 32768 · llamacpp              unload in 22:23
 Speicher  [###################### ###]  GPU 88 % 5.6 GiB | CPU 12 % 0.8 GiB
```

- `Speicher`, `[` und `]` folgen der Strukturfarbe Cyan.
- Linke `#` stehen für GPU/VRAM (Cyan), rechte `#` für CPU/RAM (Magenta).
- Der Ollama-Speicherbalken hat dieselbe Breite und dieselben Ausrichtungs-
  spalten wie die übrigen Sensorbalken.

## Umsetzung

1. **Farbrollen zentralisieren (`llmtop.py`)**
   - `_init_colors()` auf die oben definierten semantischen Rollen reduzieren:
     `structure`, `status_*`, `gpu_memory`, `cpu_memory`, `secondary`,
     `error`.
   - Bestehende Zeichnungshelfer (`section`, `sensor`, Temperatur- und
     Fehleranzeige) ausschließlich über diese Rollen ansprechen. Keine
     zusätzlichen lokalen Farbentscheidungen in einzelnen Bereichen.
   - Magenta als zusätzliche curses-Farbpaarung einrichten; ohne
     Farbfähigkeit bleiben die Rollen durch Fett/Dimmung unterscheidbar.

2. **Ollama auf Sensorgeometrie ausrichten**
   - Modellname als strukturelles Label und Parameter, Kontext, Runner sowie
     Unload als Sekundärinformation zeichnen.
   - Die Speicherzeile nutzt dieselbe Labelbreite, Balkenbreite und
     Wertspaltenlogik wie `sensor()`.
   - GPU-Anteil aus `size_vram / size`, CPU-Anteil aus `size - size_vram`
     berechnen. Beide Segmente bestehen aus `#`; nur ihre Farbrolle
     unterscheidet sich.
   - GPU- und CPU-Prozent mit jeweiliger Größe rechts als getrennte,
     farbkonsistente Textsegmente zeichnen. Fehlende Größen behalten den
     cyanfarbenen Rahmen und zeigen gedimmtes `n/a`.

3. **Dokumentation und Prüfung**
   - Patch-Version erhöhen und README, Status sowie Changelog mit der
     Farblegende und dem vollständigen GPU-/CPU-`#`-Balken aktualisieren.
   - Mock-Rendering für 0/100, 50/50, 100/0 und fehlende Modellgröße prüfen:
     Segmentbreite, `#`-Füllung und Farbattribute müssen jeweils stimmen.
   - Pseudo-TTY und Live-TUI für NVIDIA- und sysfs-Pfad auf konsistente Farben,
     Ausrichtung und Mindestgröße prüfen.
