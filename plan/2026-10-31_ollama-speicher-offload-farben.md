# Dynamische Ollama-Speicherfarben

## Ziel und Darstellungsidee

Der Ollama-Speicherbalken soll nicht mehr GPU- und CPU-Speicher als feste
Cyan-/Magenta-Kategorien zeigen, sondern den **Offload-Grad** bewerten:

- Viel Modell im VRAM/GPU = gut für GPU-Offload → **Grün**.
- Modellanteil im CPU-RAM = CPU-Fallback → **Rot**.
- Nahezu ausgeglichenes Verhältnis (45–55 % GPU) → **Gelb** als neutraler
  Übergang.

Damit ergibt sich dynamisch ein Balken von überwiegend Rot (0 % GPU / 100 %
CPU) über Gelb bei ausgeglichener Aufteilung bis überwiegend Grün (100 %
GPU). Die aktuelle lokale Situation würde beispielsweise `qwen3.5:9b` mit
rund 88 % GPU-Anteil deutlich grün und ein Modell mit rund 7 % GPU-Anteil
überwiegend rot zeigen.

Die Farben bedeuten in diesem Bereich explizit **Offload-Qualität**, nicht
Temperatur oder Hardwarehersteller. Die Textwerte `GPU x %` und `CPU y %`
bleiben sichtbar und erhalten dieselbe Farbe wie ihr Segment.

## Zielbild

```text
Speicher  [###################### ###]  GPU 88 % 5.6 GiB | CPU 12 % 0.8 GiB
            grün (GPU/VRAM)          rot (CPU/RAM)

Speicher  [## #######################]  GPU  7 % 88 MiB  | CPU 93 % 1.1 GiB
            grün                      rot

Speicher  [##############Y############]  GPU 50 % ...   | CPU 50 % ...
            gelber Übergang bei ausgeglichenem Verhältnis
```

`#` bleibt für beide Segmente erhalten. Die Segmentlängen werden weiterhin
exakt aus `size_vram / size` und `size - size_vram` berechnet; nur die
Farblogik ändert sich.

## Umsetzung

1. **Offload-Farbrolle zentral ergänzen (`otop.py`)**
   - Die globalen Rollen `offload_good` (Grün), `offload_mixed` (Gelb) und
     `offload_cpu` (Rot) aus den vorhandenen Statusfarben ableiten; keine
     zusätzliche Abhängigkeit oder Palette notwendig.
   - Eine kleine Hilfsfunktion bestimmt aus dem GPU-Anteil die Text-/Marker-
     Farbe: Grün oberhalb 55 %, Gelb von 45–55 %, Rot unterhalb 45 %.
   - Diese Regel ist auf `model_card()` begrenzt; CPU-/GPU-Auslastung und
     Temperaturen behalten ihre vorhandene Statussemantik.

2. **Speicherbalken und Text konsistent zeichnen**
   - GPU-`#` grün und CPU-`#` rot zeichnen; bei einem Verhältnis 45–55 % einen
     gelben `#`-Marker an der Segmentgrenze platzieren, ohne die Gesamtbreite
     zu ändern.
   - `GPU x % / Größe` erhält die Offload-Farbe (Grün/Gelb/Rot nach
     GPU-Anteil); `CPU y % / Größe` erhält Rot, bei ausgeglichenem Verhältnis
     Gelb.
   - „Speicher“ und Balkenrahmen bleiben Struktur-Cyan. Fehlende Größen bleiben
     gedimmt mit `GPU/CPU n/a`.

3. **Dokumentation und Versionierung**
   - Patch-Version erhöhen.
   - README, Status und Changelog um die Offload-Farbsemantik und die
     Schwellenwerte 45/55 % ergänzen.
   - Die bisherige GPU-Cyan-/CPU-Magenta-Sonderregel aus der Dokumentation
     entfernen, damit die globale Farblegende eindeutig bleibt.

## Prüfung

- Mock-Rendering für 0/100, 44/56, 50/50, 56/44 und 100/0: Segmentbreite,
  Farben, gelber Übergangsmarker und Textattribute prüfen.
- Fehlende Größe muss weiterhin einen cyanfarbenen Rahmen und gedimmtes `n/a`
  erzeugen.
- Live `--once` und TUI mit mindestens einem stark GPU-offloadeten und einem
  überwiegend CPU-offloadeten Modell visuell prüfen.
