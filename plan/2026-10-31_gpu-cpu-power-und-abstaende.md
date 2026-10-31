# GPU-Boost-Skala und Bereichsabstände

## Ergebnis der Machbarkeitsanalyse: CPU-Power entfällt

Auf dem aktuellen Host läuft ein **AMD Ryzen AI 9 HX 370**. Die verfügbaren
CPU-Sensoren enthalten nur `k10temp` mit Temperaturwerten. Es gibt keinen
CPU-hwmon-Powersensor; der einzige sichtbare `power*_input`-Sensor gehört zu
`amdgpu` und misst daher nicht die CPU.

Zwar existieren RAPL-Dateien, deren `energy_uj`-Werte sind für den laufenden
Benutzer aber nur für root lesbar (`-r--------`; Leseversuch: „Keine
Berechtigung“). `turbostat` und `sensors` sind keine zulässigen Datenquellen
für die Standardbibliotheks-Anwendung und liefern hier ebenfalls keine
zugängliche CPU-Package-Leistung.

Eine CPU-Poweranzeige wäre damit aktuell entweder immer `n/a` oder eine
unzuverlässige Schätzung. Sie wird gemäß Auftrag **nicht** umgesetzt und aus
diesem Plan entfernt. Sobald der Host einen lesbaren CPU-Power-Sensor
bereitstellt (z. B. `zenpower`-hwmon oder lesbares RAPL), kann das als separate
Funktion geplant werden.

## Ziel
Die GPU-Poweranzeige verwendet für dieses Gerät eine Maximalleistung inklusive
Boost von **115 W**. Zwischen System, GPU, Ollama und History stehen
Leerzeilen, damit die TUI klarer gegliedert ist.

## Umsetzung

1. **GPU-Boost-Skala in `otop.py`**
   - Eine klar benannte Konstante für die lokale GPU-Boost-Obergrenze von 115 W
     ergänzen.
   - Den GPU-Power-Prozentwert gegen mindestens 115 W berechnen. Meldet die
     GPU eine höhere belastbare Grenze, hat diese Vorrang.
   - Rechts weiterhin den gemessenen Wattwert und die tatsächlich verwendete
     Skala ausgeben, z. B. `4.0 W / 115 W`.
   - Bei fehlendem Wattwert bleibt `n/a`; bei Wattwert ohne Geräte-Limit ist
     die 115-W-Boost-Skala dennoch verfügbar.

2. **Bereichsabstände und Mindestgröße**
   - Nach System, GPU und Ollama jeweils exakt eine Leerzeile einfügen.
   - Mindesthöhe von 40×14 auf **40×18** anheben, damit Kopfzeile, Bereiche
     und Fußzeile nicht kollidieren.
   - Unterhalb der Mindestgröße weiterhin nur den eindeutigen Hinweis zeichnen.

3. **Dokumentation und Versionierung**
   - Patch-Version erhöhen.
   - README, Status und Changelog um 115-W-Boost-Skala, Bereichsabstände und
     Mindestgröße 40×18 ergänzen.
   - Keine CPU-Power-Funktion, keine neue Abhängigkeit und keine Änderung an
     `--once`, API-Abfragen oder Tasten.

## Prüfung
- Mock-Test für GPU-Power mit 100-W-Limit (Balken und Text müssen 115 W als
  Skala verwenden), höherem GPU-Limit und fehlendem Geräte-Limit.
- Live `--once` und TUI: NVIDIA-Power muss `W / 115 W` zeigen; sysfs-Power
  ohne Limit nutzt ebenfalls die 115-W-Skala.
- TUI bei 80×24 und 40×18: Leerzeilen, Ausrichtung und Footer prüfen; bei
  40×17 muss der Mindestgrößenhinweis erscheinen.
- Syntaxcheck und Pseudo-TTY-Test ausführen.
