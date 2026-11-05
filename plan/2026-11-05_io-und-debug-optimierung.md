# Plan: I/O-, Sensor- und Debug-Optimierung

## Anlass und Ziel

Die bestehende Mehrdateien-Struktur bleibt unverändert. Dieser Plan ergänzt den bereits umgesetzten Architekturplan `2026-11-01_mehrdateien-architektur-und-performance.md` gezielt um die im Code-Review festgestellten Laufzeitkosten.

Ziel ist eine spürbar geringere Hintergrund-I/O bei identischer TUI, denselben CLI-Optionen, Datenformaten und Sensor-Fallbacks. Neue Abhängigkeiten oder eine weitere Modulaufteilung sind nicht vorgesehen.

## Befund

- Der TUI-Sampler schreibt derzeit bei jedem Refresh einen Snapshot: Die begrenzte JSONL-Datei wird vollständig gelesen, atomar neu geschrieben und per `fsync()` gesichert.
- Bei 0,5 s Intervall sind dies 120 Schreibvorgänge pro Minute; die 500 Snapshot-Zeilen umfassen nur rund vier Minuten.
- Sensor-Topologie und PCI-/hwmon-Zuordnung werden in jedem Sampling-Zyklus neu ermittelt, obwohl sie im Normalfall stabil sind.
- `--debug` schreibt eine GPU-Quellenzeile pro Sampling-Zyklus. Bei nicht erreichbarem Ollama kann zusätzlich pro Zyklus ein Traceback anfallen. Eine Logrotation fehlt.
- Drei Imports sind nach statischer Prüfung unbenutzt: `token_rate` in `llmtop.py`, `time` und `run_metric_detail` in `llmtop_tui.py`. Zwei dynamische `__import__`-Aufrufe im CLI-Einstieg sind unnötig kompliziert.

## Umsetzung in höchstens drei Schritten

### 1. Snapshot-History begrenzen, ohne Anzeige oder Dateiformat zu ändern

- Die TUI erfasst weiterhin bei jedem Refresh alle aktuellen Werte, schreibt Snapshot-History aber höchstens in einem festen, dokumentierten Intervall (Vorschlag: 5 s).
- Der erste vollständige Snapshot wird sofort gespeichert; weitere Werte innerhalb des Intervalls bleiben ausschließlich im TUI-Zustand.
- `--once` schreibt weiterhin genau einen Snapshot.
- Das JSONL-Format, Pfad, Dateirechte, atomische Schreibweise, Retention von 500 Zeilen und Fehlertoleranz bleiben erhalten.
- Tests prüfen unmittelbaren ersten Write, zeitlich gedrosselte Folge-Updates und unveränderte Retention.

### 2. Statische Sensorerkennung und Debug-Ausgaben drosseln

- Stabile Metadaten zwischenspeichern: DRM-/PCI-Geräte, GPU-Name, hwmon-Zuordnung und verfügbare Power-Quellen.
- Messwerte bleiben dynamisch und werden weiterhin je Sampling-Zyklus aus sysfs gelesen.
- Bei Leseproblemen wird der betreffende Cache gezielt verworfen und automatisch neu ermittelt; die bestehende Fallback-Kette `nvidia-smi → sysfs` bleibt unverändert.
- Debugmeldungen nur bei Zustandswechseln, neu gewählten Fallbacks oder Fehlern ausgeben; wiederkehrende identische Fehler zeitlich drosseln.
- Logdateien begrenzen: Standardbibliotheks-`RotatingFileHandler`, kleine feste Anzahl rotierter Dateien und private Dateirechte.
- Keine Hosts, Tokens, Prompts, Modellantworten oder vollständigen Request-/Response-Payloads loggen.

### 3. Kleine Bereinigung, Dokumentation und Regression

- Die drei unbenutzten Imports entfernen.
- Dynamische `__import__`-Aufrufe durch explizite lokale Imports ersetzen, ohne das Lazy-Import-Verhalten von `--version` zu verschlechtern.
- README, `status.md`, `version.md` und `VERSION` aktualisieren; Patch-Version erhöhen.
- Tests ergänzen bzw. gezielt ausführen für Snapshot-Takt, Cache-Invalidierung, Log-Drosselung, Rotation und sensible Log-Inhalte.
- Abschließend Syntaxcheck, vorhandene Tests, `--version`, `--once`, `--once --no-nvidia`, TUI mit und ohne `--debug` sowie `git diff --check` ausführen.
- Den erfolgreich geprüften Patchstand committen; kein Tag und kein Release.

## Nicht im Umfang

- keine weitere Aufteilung von `llmtop_tui.py` oder `llmtop_metrics.py`
- keine Änderung von CLI-Namen, Tasten, Exit-Codes, JSONL-Schema oder Fallback-Reihenfolge
- keine Datenbank, kein Hintergrunddienst, kein Thread-Pool
- keine Entfernung der Schema-1-/`legacy`-Kompatibilität oder alten Adapterbereinigung
- keine Bereinigung historischer Pläne oder von `bug-report.md` ohne separaten Auftrag

## Akzeptanzkriterien

- Die TUI stellt Sensorwerte weiterhin mit dem konfigurierten Refreshintervall dar.
- Snapshot-History verursacht höchstens einen Write je festgelegtem Snapshotintervall, außer bei `--once`.
- Bei stabiler Hardware erfolgt keine vollständige Topologie-Suche je Refresh; nach einem sysfs-Fehler greift die Neuerkennung.
- `--debug` erzeugt bei unverändertem Normalbetrieb keine Logzeile pro Frame und die Loggröße bleibt begrenzt.
- Alle Logdateien bleiben privat lesbar und enthalten keine sensitiven Daten.
- Bestehende CLI-Pfade, UI-Darstellung, Sensor-Fallbacks und History-Dateiformate bleiben kompatibel.
