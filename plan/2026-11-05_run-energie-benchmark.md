# Plan: Energiebedarf lokaler Modell-Runs

## Ziel

llmtop soll den softwareseitig messbaren Energiebedarf eines lokalen Modell-Runs erfassen und für reproduzierbare Benchmarks auswertbar machen. Eine Steckdosen- oder externe Gesamtverbrauchsmessung ist ausdrücklich nicht Bestandteil dieses Plans.

Die Messung bleibt auf lokale Komponenten beschränkt und weist Quelle sowie Messbereich aus. CPU-, AMD-GPU- und NVIDIA-GPU-Werte werden nicht ungeprüft zu einer Gesamtsumme addiert, wenn sich Messbereiche überschneiden können.

## Geprüfte Messquellen

- **CPU:** Intel-RAPL `energy_uj` als kumulativer Energiezähler. Auf dem aktuellen System vorhanden, aber nur für root lesbar; der bestehende privilegierte RAPL-Helper ist dafür vorgesehen.
- **NVIDIA:** `nvidia-smi --query-gpu=timestamp,power.draw --format=csv,noheader,nounits --loop-ms=200` funktioniert. Die Leistungswerte werden zeitlich integriert; ein dauernd laufender Prozess vermeidet den Startaufwand pro Messpunkt.
- **AMD:** `/sys/class/hwmon/.../power1_average` funktioniert und liefert auf dem aktuellen System ungefähr 4 W. Auch dieser Leistungswert wird zeitlich integriert.
- **Ollama:** Die lokale API ist erreichbar und liefert finale Dauer- und Tokenfelder. Ein Modell war zum Prüfzeitpunkt nicht geladen, daher wurde kein echter Run-Energiebezug gemessen.

## Messdefinition

Für jede Quelle werden erfasst:

```text
energy_j
energy_source
energy_scope
energy_sample_count
measurement_started_at
measurement_finished_at
baseline_power_w
```

Bei Leistungs-Samplern gilt die Trapezregel:

```text
E = Summe(((P_alt + P_neu) / 2) * Zeitdifferenz)
```

Bei RAPL gilt der Zählerdeltawert:

```text
E = (energy_uj_end - energy_uj_start) / 1_000_000
```

Zusätzlich werden Run-Dauer, Prompt-Tokens, Ausgabe-Tokens und Tokens pro Sekunde aus dem bestehenden Schema verwendet.

## Umsetzung in höchstens drei Schritten

### 1. Energie-Sampler ohne Run-Kopplung

- Einen kleinen, standardbibliotheksbasierten Sampler innerhalb der bestehenden Quellen-/Metrikgrenzen ergänzen.
- RAPL als kumulativen Zähler über den privilegierten Helper lesbar machen, ohne die bestehende CPU-Power-Anzeige zu verändern.
- NVIDIA-Leistung über einen langlebigen `nvidia-smi --loop-ms=200`-Prozess lesen und sauber beenden.
- AMD-`power1_average` in einem festen Intervall, vorgeschlagen 200 ms, lesen.
- Ungültige, fehlende oder nicht berechtigte Quellen als `n/a` melden; keine Abstürze.
- Messwerte intern mit monotonicen Zeitstempeln versehen.

### 2. Energie an direkte lokale Ollama-Runs koppeln

- Messung unmittelbar vor dem direkten `/api/chat`- beziehungsweise `/api/generate`-Request starten.
- Messung nach dem finalen Ollama-`done`-Objekt beenden.
- Kaltstart und Warmbetrieb durch getrennte Kennzeichnung unterscheidbar machen.
- Bruttoenergie und optional idle-bereinigte Energie speichern. Für die Baseline zunächst die mittlere Leerlaufleistung vor dem Run verwenden.
- Energie je Quelle und Messbereich in das vorhandene Schema 2 aufnehmen, ohne Prompts oder Modellantworten zu speichern.
- Bestehende Collector-, Pi- und Open-WebUI-Runs bleiben unverändert, solange keine verlässliche Run-Zeitbasis vorliegt.

### 3. Benchmark-Auswertung und Absicherung

- Auswertung für folgende Werte ergänzen:
  - Joule pro Run
  - Joule pro 1.000 Ausgabe-Tokens
  - Joule pro 1.000 Gesamt-Tokens
  - Tokens pro Sekunde
  - Laufzeit
- Mindestens fünf Wiederholungen mit identischem Modell, Prompt, Kontextlimit, Ausgabeziel, Temperatur und `keep_alive` vergleichen.
- Warm-up-Runs separat behandeln und nicht mit Kaltstart-Runs vermischen.
- CPU-RAPL, AMD-GPU und NVIDIA-GPU als getrennte Quellen anzeigen; keine Gesamtsumme bilden, wenn eine Überlappung nicht ausgeschlossen ist.
- Tests mit simulierten Zählern, fehlenden Dateien, Prozessabbruch, monotonen Zeitstempeln und unvollständigen Ollama-Antworten ergänzen.
- `README.md`, `status.md`, `version.md` und `VERSION` synchronisieren.
- Syntaxcheck, bestehende Tests und ein echter lokaler Modellrun ausführen, sobald ein Modell verfügbar ist.

## Nicht im Umfang

- keine Steckdosenmessung oder externe Gesamtverbrauchsmessung
- keine neuen Python- oder Systemabhängigkeiten
- keine Energie-Schätzung aus CPU-Auslastung allein
- keine Energieerfassung für Open-WebUI-/Pi-Runs ohne stabile Start-/Endereignisse
- keine Addition überlappender Messbereiche
- keine Änderung bestehender CLI-, TUI- oder Collector-Verträge ohne gesonderte Prüfung

## Akzeptanzkriterien

- Fehlende Berechtigungen oder Sensoren bleiben als `n/a` sichtbar.
- Ein direkter lokaler Ollama-Run erhält reproduzierbare Energie- und Laufzeitdaten.
- RAPL wird als Zählerdelta, GPU-Leistung als zeitliches Integral berechnet.
- Samplerprozesse werden bei Erfolg, Fehler und Abbruch beendet.
- Energiequellen und Messbereiche sind in den Daten eindeutig erkennbar.
- Bestehende Run-Metriken, History, TUI und Fallback-Ketten funktionieren unverändert.
