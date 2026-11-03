# Plan: Weitere Linux-Sensor-Fallbacks

## Ziel

llmtop soll auf unterschiedlichen Linux-Installationen, Kernelversionen,
Containern und GPU-Herstellern möglichst viele belastbare Werte anzeigen,
ohne neue Pflichtabhängigkeiten einzuführen. Nicht sicher ermittelbare Werte
bleiben ausdrücklich `n/a`.

## Aktueller Befund

- AMD und NVIDIA funktionieren auf dem geprüften Mischsystem.
- CPU-Modell, CPU-Temperatur, RAM, GPU-Namen und GPU-Power besitzen bereits
  mehrere Fallbacks.
- Intel-GPU-Auslastung ist nicht universell über sysfs verfügbar.
- cgroup-Erkennung verwendet derzeit hauptsächlich die üblichen Pfade unter
  `/sys/fs/cgroup`.
- Tests decken aktuell den Kern und das AMD-/NVIDIA-Live-System ab, nicht aber
  reale Intel-, ARM-, ältere Kernel- oder alternative Containerumgebungen.

## Umsetzung in drei Schritten

### 1. Generische Linux-Pfade vervollständigen

- cgroup-Mounts aus `/proc/self/mountinfo` und `/proc/self/cgroup` ermitteln,
  statt nur feste v1-/v2-Pfade anzunehmen.
- `memory.current`/`memory.max` sowie v1-
  `memory.usage_in_bytes`/`memory.limit_in_bytes` sicher priorisieren.
- hwmon- und Thermal-Zone-Zuordnung anhand realer Gerätepfade und Labels
  weiter absichern.
- GPU-Namen zusätzlich aus vorhandenen PCI-/udev-Sysfs-Daten lesen; `pci.ids`
  bleibt optional.
- Keine Schätzwerte als echte Messwerte ausgeben.

### 2. Intel- und Hersteller-Fallbacks prüfen und gezielt ergänzen

- i915: vorhandene PMU-Eventdateien unter
  `/sys/bus/event_source/devices/i915/events` erkennen.
- Eine Auslastungsmessung nur implementieren, wenn `perf_event_open` ohne
  Rootzugriff und mit stabiler Eventbeschreibung möglich ist.
- xe: aktuelle GT-/DRM-Statistiken und verfügbare `fdinfo`-Zähler untersuchen;
  keine unsichere globale Auslastung aus einzelnen Prozessen ableiten.
- AMD: weitere dokumentierte amdgpu-Sysfs-Pfade für VRAM, GTT, Power und
  Auslastung ergänzen, sofern Einheit und Bedeutung eindeutig sind.
- NVIDIA: sysfs-/`/proc/driver/nvidia`-Fallbacks nur für Name, Temperatur und
  statische Geräteinformationen verwenden; für echte Auslastung bleibt
  `nvidia-smi` die Primärquelle.
- `amd-smi`, `rocm-smi`, `intel_gpu_top` und Python-NVML nicht als Pflicht-
  abhängigkeiten einführen. Optionale Adapter erst nach gesonderter Freigabe.

### 3. Testmatrix und Dokumentation

- Scratch-Fixtures für fehlende Dateien, alte hwmon-Namen, cgroup v1/v2,
  fehlende `pci.ids`, mehrere GPUs und unbekannte Vendor-IDs erstellen.
- Vorhandene Live-Prüfung auf AMD-/NVIDIA-Mischbetrieb wiederholen.
- Intel i915/xe, ARM-CPU und Container mit nichtstandardmäßigem cgroup-Mount
  gezielt prüfen, sofern entsprechende Systeme verfügbar sind.
- Für jede Quelle Einheit, Berechtigung, Kernelabhängigkeit und Fallbackstatus
  dokumentieren.
- `README.md`, `status.md`, `version.md` und Versionsnummer synchronisieren.

## Abnahmekriterien

- Keine Sensorquelle darf bei fehlender Hardware oder fehlenden Rechten den
  Prozess beenden.
- Mehrere GPUs werden unabhängig voneinander erkannt und nicht doppelt gezählt.
- CPU-/RAM-/GPU-Werte zeigen ihre Quelle oder bleiben nachvollziehbar `n/a`.
- Intel-Werte werden nur angezeigt, wenn der zugrunde liegende Kernelzähler
  eindeutig identifiziert und messbar ist.
- Keine neuen pip-, Systempaket- oder externen Dienstabhängigkeiten.
- Syntaxprüfung, Core-Tests, `--once`, `--once --no-nvidia` und `--version`
  bleiben erfolgreich.

## Bewusste Grenzen

Eine vollständig herstellerunabhängige GPU-Auslastung ist unter Linux nicht
möglich. Bei Intel xe/i915 und proprietären NVIDIA-Treibern können Kernel,
Treiber, Berechtigungen und Desktop-/Container-Isolation die verfügbaren
Zähler begrenzen. In diesen Fällen ist ein korrektes `n/a` besser als eine
scheinpräzise Schätzung.
