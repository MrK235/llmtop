# GPU-Poweranzeige korrigieren

## Analyse
In `_draw()` wird für Power nur dann ein Prozentwert berechnet, wenn
`g["power_limit"]` vorhanden ist:

```python
power_pct = ... if limit else None
```

Bei fehlendem Limit zeichnet `sensor()` daher absichtlich einen leeren,
gedimmten Balken und `n/a`. Der tatsächlich vorhandene Wert
`power_watt` landet lediglich als gedimmte Detailinformation rechts. Das
beobachtete Verhalten ist damit ein Darstellungsfehler, keine fehlende
Watt-Messung.

## Ziel
Die gemessene Leistung wird stets als primärer, ausgerichteter Sensorwert
angezeigt. Ein farbiger Prozentbalken erscheint nur, wenn eine belastbare
Leistungsgrenze verfügbar ist; es wird keine willkürliche Watt-Skala erfunden.

## Umsetzung
1. **Leistungsgrenze besser ermitteln (`otop.py`)**
   - NVIDIA-Abfrage um die verfügbare effektive Leistungsgrenze (z. B.
     `enforced.power.limit`) ergänzen und als Fallback zur bisherigen Grenze
     verwenden.
   - Im sysfs-Pfad eine vorhandene `power*_cap`-Datei passend zum gelesenen
     `power*_input` prüfen und von µW nach W umrechnen.
   - Nicht verfügbare oder ungültige Limits bleiben `None`; Messwerte in Watt
     werden dadurch nicht verworfen.

2. **Power-Sensor korrekt zeichnen (`otop.py`)**
   - Mit Limit: Balken, Prozentwert und Ampelfarbe aus `power_watt / limit`
     berechnen; Detailwert zeigt `X W / Y W`.
   - Ohne Limit: `X.X W` als primären Sensorwert in der Wertspalte anzeigen,
     den leeren Balken als „keine Skala“ behandeln und diese Information
     gedimmt rechts ausweisen. `n/a` erscheint nur, wenn auch der Wattwert
     fehlt.
   - Dieselbe Regel in der `--once`-Ausgabe anwenden, damit TUI und Snapshot
     übereinstimmen.

3. **Dokumentation und Versionierung**
   - Patch-Version erhöhen, Changelog, README und Status auf das Verhalten bei
     fehlender Leistungsgrenze abgleichen.
   - Keine Änderungen an anderen Sensoren, API-Endpunkten oder Tasten.

## Prüfung
- Mock-Daten für: Watt plus Limit, Watt ohne Limit und fehlenden Wattwert.
  Erwartet werden farbiger Prozentbalken, primärer Wattwert ohne Limit und
  `n/a` nur ohne Messwert.
- Live `--once` und TUI für NVIDIA sowie `--no-nvidia`/sysfs prüfen.
- Syntaxcheck und Pseudo-TTY-Test ausführen.
