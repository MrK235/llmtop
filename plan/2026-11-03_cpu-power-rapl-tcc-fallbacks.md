# Plan: CPU-Power über RAPL und TUXEDO-Fallbacks

## Ergebnis der neuen Prüfung

Das TUXEDO Control Center 3.0.10 verwendet für die CPU-Power selbst den
Intel-RAPL-Energiezähler:

```text
/sys/devices/virtual/powercap/intel-rapl/intel-rapl:0/energy_uj
```

Die Zone heißt `package-0`. TCC liest den Zähler ungefähr alle zwei Sekunden
und berechnet die Leistung aus der Energieänderung:

```text
Watt = Delta(energy_uj) / Delta(Zeit) / 1_000_000
```

Auf diesem System ist der direkte Zugriff für normale Benutzer wegen
`-r-------- root root` gesperrt. Der TCC-Dienst `tccd` läuft als root und
stellt die Werte optional über D-Bus als `GetCpuPowerValuesJSON()` bereit.

Dieser Plan ersetzt die frühere Einschätzung, dass CPU-Power auf diesem Host
nicht sinnvoll erfassbar sei.

## Ziel

CPU-Package-Power anzeigen, ohne Werte zu schätzen oder die Anwendung von TCC
abhängig zu machen. Die Anzeige muss Quelle, Messbereich und fehlende
Berechtigungen sauber berücksichtigen.

## Quellen- und Fallback-Kette

### 1. Direkte Linux-powercap/RAPL-Quelle

- `powercap` dynamisch unter `/sys/class/powercap` und
  `/sys/devices/virtual/powercap` suchen.
- Zonen anhand von `name` priorisieren: `package-0`, danach vergleichbare
  Package-/Socket-Zonen.
- `energy_uj` als monotonen Zähler lesen und über zwei Messpunkte in Watt
  umrechnen.
- `max_energy_range_uj` für Zählerüberläufe berücksichtigen.
- Optional vorhandene `power_uw`-Dateien direkt bevorzugen.
- Intel-RAPL und kompatible AMD-/andere powercap-Zonen generisch behandeln,
  aber die Quelle und Zone im Ergebnis speichern.
- Unlesbare Dateien, fehlende Zonen und Berechtigungsfehler ergeben `n/a`,
  keinen Programmfehler.

### 2. Zugeordnete CPU-hwmon-Quelle

- CPU-nahe hwmon-Geräte über reale Sysfs-Pfade erkennen.
- `power*_input` und `power*_average` in µW lesen.
- GPU-hwmon-Geräte ausdrücklich ausschließen, damit AMD-GPU-Power nicht als
  CPU-Power erscheint.
- Diese Quelle nur verwenden, wenn Label, Gerätename oder Pfad eindeutig auf
  CPU/Package/SoC hinweist.

### 3. Optionaler TUXEDO-Control-Center-Fallback

- TCC nur erkennen, wenn der D-Bus-Dienst
  `com.tuxedocomputers.tccd` vorhanden ist.
- `GetCpuPowerValuesJSON()` mit kurzem Timeout lesen und `powerDraw` sowie
  `maxPowerLimit` validieren.
- Den Fallback standardmäßig nicht zwingend aktivieren: Kein TCC darf nötig
  sein, damit llmtop startet.
- Da Python-Standardbibliothek keinen D-Bus-Client enthält, zwei Varianten
  getrennt bewerten:
  1. optionales `busctl`/`dbus-send` als klar gekennzeichneter System-Fallback;
  2. ein kleiner nativer D-Bus-Aufruf nur, falls er ohne neue Abhängigkeit,
     Architektur-Hacks und Sicherheitsrisiko wartbar umgesetzt werden kann.
- `SetSensorDataCollectionStatus(true)` nicht ungefragt aufrufen; llmtop soll
  keine TCC-Sensordatensammlung global aktivieren.
- Bei TCC `powerDraw == -1` oder deaktivierter Datensammlung zur nächsten Quelle
  zurückfallen.

## Anzeige und Datenmodell

- Neue interne Werte `cpu_power_watt`, `cpu_power_limit` und
  `cpu_power_source` ergänzen.
- CPU-Power in `--once` und TUI als eigene Zeile anzeigen.
- Einen Prozent-/Balkenwert nur bei echter Leistungsgrenze verwenden.
- Ohne Grenze den Wattwert und eine leere beziehungsweise neutrale Grafik
  anzeigen; keine feste CPU-Leistungsgrenze erfinden.
- Quellen beispielsweise als `RAPL package-0`, `hwmon` oder `TCC D-Bus`
  ausgeben.
- Erste RAPL-Messung bleibt `n/a`, bis ein gültiges Zeitintervall vorliegt.

## Umsetzung in drei Schritten

1. **Powercap/RAPL und hwmon:** dynamische Zonen-Erkennung, Sampling,
   Überlaufbehandlung, Berechtigungsfehler und CPU-/GPU-Zuordnung.
2. **TCC-Fallback:** D-Bus-Verfügbarkeit und die technisch zulässige optionale
   Zugriffsmethode untersuchen; nur bei belastbarer Lösung integrieren.
3. **Anzeige, Tests und Dokumentation:** TUI/`--once`, Fixture-Tests für
   RAPL-Zähler und Überlauf, fehlende Rechte, hwmon sowie TCC-`-1`; Live-Test
   mit TCC und Synchronisierung von README, status.md, version.md.

## Abnahmekriterien

- Direkter lesbarer RAPL-Zähler liefert nach zwei Messungen realistische Watt.
- Zählerüberlauf und rückwärts laufende/ungültige Werte führen nicht zu
  negativen oder extremen Wattwerten.
- GPU-Power wird niemals als CPU-Power übernommen.
- Ohne Rootrechte bleibt llmtop stabil und zeigt nachvollziehbar `n/a` oder
  nutzt TCC, sofern dieser Fallback ausdrücklich verfügbar ist.
- TCC ist optional; ohne TCC funktionieren Start, TUI und `--once` unverändert.
- Keine pip-Abhängigkeit und keine verpflichtende Installation zusätzlicher
  Software.

## Bewusste Grenzen

RAPL misst CPU-Package-/SoC-Energie, nicht ausschließlich die Rechenkerne.
TCC-D-Bus ist herstellerspezifisch und darf daher nur ein optionaler Fallback
sein. Die frühere Ablehnung einer CPU-Poweranzeige in
`plan/2026-10-31_gpu-cpu-power-und-abstaende.md` gilt für den damaligen Stand
und wird durch diesen Befund aktualisiert.
