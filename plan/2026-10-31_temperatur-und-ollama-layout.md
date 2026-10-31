# Temperaturen und Ollama-Anzeige

## Rechercheergebnis

### Lokal verfügbare Temperatursensoren

| Bereich | Quelle | Aktueller Wert | Eignung |
|---|---|---:|---|
| CPU | `/sys/class/hwmon/...` mit Name `k10temp`, `temp1_input` / Label `Tctl` | 43,6 °C | zuverlässig für den AMD Ryzen AI 9 HX 370 |
| NVIDIA-GPU | `nvidia-smi --query-gpu=temperature.gpu` | 37 °C | bevorzugte Quelle bei NVIDIA |
| NVIDIA-VRAM | `temperature.memory` | `N/A` | aktuell nicht verfügbar |
| AMD-GPU | zugehöriges amdgpu-hwmon, `temp*_input` / Label `edge` | 39 °C | sysfs-Fallback bei `--no-nvidia` |

Die vorhandenen ACPI-, NVMe-, WLAN- und RAM-Temperaturen sind keine CPU-/GPU-
Sensoren und werden nicht aufgenommen. Alle sysfs-Temperaturen liegen in
Milligrad Celsius vor und werden in °C umgerechnet.

### Verfügbare Ollama-Daten

`/api/ps` liefert für **geladene** Modelle (ohne weitere API-Abfrage):

| Datenpunkt | Im aktuellen Projekt vorhanden | Empfehlungswert für die TUI |
|---|---|---|
| Modellname / interne Modellkennung | `name`, `model` | Name anzeigen, interne Kennung nicht doppeln |
| Gesamtgröße / VRAM-Größe | `size`, `size_vram` | **grafische GPU-/CPU-Aufteilung** |
| GPU-/CPU-Anteil | aus `size_vram / size` | **farbiger, geteilter Balken** |
| Kontextfenster | `context_length` | kompakte Detailinfo |
| Runner | `runner` | gedimmte Detailinfo |
| Restzeit bis Unload | `expires_at` | Highlight bei kurzem Ablauf |
| Parameter / Quantisierung | `details.parameter_size`, `quantization_level` | kompakte Detailinfo |
| Format / Familie | `details.format`, `family`, `families` | optional, nur bei Platz |
| Parent-Modell / Digest | `details.parent_model`, `digest` | nicht anzeigen; technische Metadaten |

Zusätzlich verfügbar, aber nicht Teil dieses Plans:
- `/api/version`: laufende Ollama-Version (bereits Kopfzeile).
- `/api/tags`: installierte, nicht zwingend geladene Modelle sowie Größe,
  Änderungszeit und Metadaten; zusätzliche API-Abfrage nötig.
- `/api/show`: Modellmetadaten, Template, Parameter, Capabilities und
  `model_info`; zusätzliche Anfrage je Modell, keine Laufzeitmetrik.
- `/api/generate` und `/api/chat`: pro tatsächlich ausgeführter Anfrage
  `total_duration`, `load_duration`, Prompt-/Eval-Token und -Dauer. Diese
  Werte entstehen nur beim Inferenzaufruf und sind für den passiven Monitor
  ohne Eingriff nicht verfügbar.

**Empfehlung:** Für die nächste Version ausschließlich `/api/ps` verwenden.
Das liefert alle Daten für eine bessere Anzeige ohne zusätzliche Latenz und
ohne neue API-Aufrufe.

## Zielbild

- Im **System**-Bereich steht eine farbige Textzeile `CPU Temp 43.6 °C`
  unter CPU/RAM; kein Temperaturbalken.
- Im **GPU**-Bereich folgt pro Gerät eine farbige Textzeile `Temp 37 °C`
  direkt nach dessen Auslastungszeile und vor VRAM/Power.
- Im **Ollama**-Bereich erhält jedes geladene Modell eine kompakte Karte:
  hervorgehobener Name, graue Metadaten und ein geteilter Speicherbalken.
  Der linke, cyan/farbige Teil repräsentiert GPU/VRAM; der rechte, gedimmte
  Teil CPU/RAM. Rechts stehen `GPU 88 % · CPU 12 %` und die absoluten Größen.

## Umsetzung

1. **Temperaturerfassung in `otop.py`**
   - `cpu_temperature()` für bekannte CPU-hwmon-Namen (`k10temp`, bei anderen
     Linux-Systemen optional `coretemp`/`zenpower`) ergänzen; fehlende oder
     ungültige Werte ergeben `None`.
   - `nvidia_gpus()` um `temperature.gpu` ergänzen.
   - `sysfs_gpus()` liest das zum jeweiligen DRM-Gerät gehörende hwmon-
     Temperaturlabel und `temp*_input`.
   - Temperaturen als °C und Quelle im TUI-State führen; `--once` bleibt bei
     seinen bisherigen Textzeilen, ergänzt aber Temperatur nur, wenn vorhanden.

2. **Farbige Temperaturtexte zeichnen**
   - Eine Temperatur-Farbregel getrennt von Auslastung ergänzen:
     CPU grün unter 70 °C, gelb ab 70 °C, rot ab 85 °C; GPU grün unter 70 °C,
     gelb ab 70 °C, rot ab 85 °C.
   - Fehlende Werte als gedimmtes `n/a` mit Quellenhinweis anzeigen.
   - Keine Balken und keine geschätzten Temperaturen.

3. **Ollama-Bereich visuell verbessern**
   - Modellname als Highlight, Parameter/Quantisierung/Kontext/Runner
     gedimmt und gruppiert ausrichten.
   - Eine lokale Zeichenhilfe für den geteilten GPU-/CPU-Speicherbalken
     ergänzen. Sie nutzt `size_vram / size`; bei fehlenden Größen zeigt sie
     einen neutralen, gedimmten Fallback.
   - Mit segmentweisem curses-Zeichnen GPU-Anteil farbig (Cyan) und
     CPU-Anteil gedimmt darstellen; Prozent- und Größenwerte bleiben als Text
     verfügbar, damit die Anzeige nicht nur über Farbe verständlich ist.
   - Restzeit bis Unload dezent hervorheben, bei weniger als fünf Minuten gelb
     und bei abgelaufener Zeit rot.

4. **Dokumentation und Prüfung**
   - Patch-Version erhöhen; README, Status und Changelog um Sensorquellen,
     Schwellenwerte und den Speicherbalken ergänzen.
   - Keine zusätzliche Ollama-API, keine Abhängigkeit und keine neue Taste.

## Entscheidungen des Nutzers (optional)

Die vorgeschlagenen Schwellenwerte sind konservativ. Falls gewünscht, bitte
bestätigen oder ändern:
1. CPU/GPU: Gelb ab **70 °C**, Rot ab **85 °C**.
2. Speicherbalken: **Cyan = GPU/VRAM**, gedimmt = CPU/RAM.
3. Format/Familie: nur anzeigen, wenn genug Platz vorhanden (Empfehlung), oder
   immer anzeigen.

## Prüfung

- Mock-Tests: CPU-/GPU-Temperatur normal, gelb, rot und fehlend; NVIDIA- und
  amdgpu-sysfs-Pfad.
- Mock-Rendering: geteilter Speicherbalken mit 0 %, 50 %, 100 % und fehlender
  Größe; Unload-Zeit unter fünf Minuten und abgelaufen.
- Live `--once`, `--no-nvidia`, Pseudo-TTY und visuelle Kontrolle bei 80×24.
