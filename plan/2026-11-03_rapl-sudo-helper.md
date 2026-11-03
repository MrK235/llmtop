# Plan: Privilegierter RAPL-Leser ohne llmtop-Neustart

## Ziel

llmtop soll die CPU-Package-Power auch dann anzeigen können, wenn der direkte
RAPL-Zähler nur für root lesbar ist. Die Aktivierung erfolgt ausschließlich auf
ausdrücklichen Wunsch während einer laufenden TUI-Sitzung; llmtop wird dabei
nicht neu gestartet und fragt nicht automatisch nach einem Passwort.

## Ausgangslage

Auf dem Zielsystem existiert:

```text
/sys/devices/virtual/powercap/intel-rapl/intel-rapl:0/name
package-0
```

`energy_uj` ist jedoch `root:root` mit Modus `0400`. Der TUXEDO-Dienst läuft
als root, liefert bei deaktivierter Sensordatensammlung aber `powerDraw: -1`.
Die bestehende Fallback-Kette bleibt unverändert, wenn der privilegierte Leser
nicht aktiviert wird.

## Umsetzung

### 1. Explizite Aktivierung in der TUI

- Neue Taste, beispielsweise `p`, zum Aktivieren des privilegierten RAPL-
  Lesers.
- Vor der Aktivierung kurz die curses-Anzeige verlassen und `sudo -v`
  interaktiv im Vordergrund ausführen.
- Bei fehlendem TTY, abgelehnter Authentifizierung oder fehlendem `sudo` eine
  verständliche Statusmeldung anzeigen und die Anwendung unverändert
  weiterlaufen lassen.
- Keine automatische Passwortabfrage beim Start und keine Abfrage aus dem
  Hintergrund-Sampler.

### 2. Eng begrenzter Root-Helper

- Keinen Neustart von llmtop und keinen privilegierten Hauptprozess starten.
- Den bestehenden Programmeinstieg um einen internen Helper-Modus ergänzen,
  der mit einer festen Argumentliste über `sudo -n` gestartet wird.
- Der Helper liest ausschließlich die benötigten RAPL-Dateien:
  `name`, `energy_uj`, `max_energy_range_uj` und eine vorhandene
  Leistungsgrenze.
- Ausgabe über eine einfache JSONL-Leitung auf stdout; keine Shell-Auswertung,
  keine Netzwerkverbindung und keine Schreibzugriffe auf Sysfs.
- Der unprivilegierte Prozess übernimmt weiterhin die Zählerdifferenz- und
  Zeitberechnung oder erhält bereits validierte Messpunkte vom Helper.
- Helper beim Beenden der TUI zuverlässig terminieren; abgebrochene oder
  getrennte Prozesse dürfen llmtop nicht blockieren.

### 3. Integration in die bestehende Messkette

- Direkter unprivilegierter RAPL-Zugriff bleibt erste Quelle.
- Nach expliziter Aktivierung wird der privilegierte RAPL-Leser für dieselbe
  `package-0`-/Package-Zone verwendet.
- Danach folgen weiterhin CPU-hwmon und optional TCC D-Bus.
- Erste Messung bleibt `n/a`; Überlauf, rückwärts laufende Zähler, ungültige
  JSONL-Daten und Helper-Abbruch werden verworfen.
- Interne Werte `cpu_power_watt`, `cpu_power_limit` und
  `cpu_power_source` erhalten den Status beispielsweise `RAPL (sudo)
  package-0`.
- Die bestehende Anzeige in TUI, `--once` und Snapshot-History bleibt erhalten;
  die Aktivierung verändert nur die laufende TUI-Sitzung.

## Sicherheit und Grenzen

- Root-Ausführung nur für den fest definierten Helper, niemals für die gesamte
  Anwendung.
- Keine Passwortspeicherung, kein `sudo -S`, keine Shell und keine frei
  veränderbaren Root-Befehle.
- Aktivierung nur über explizite Benutzeraktion.
- Falls die lokale sudo-Konfiguration den Helper nicht erlaubt, bleibt die
  Anwendung stabil und zeigt weiter `n/a` beziehungsweise die nächste Quelle.
- RAPL bleibt eine Package-/SoC-Messung und ist keine reine Kern-Leistung.

## Tests

- Fixture-Test mit simuliertem Helper-JSONL für zwei Messpunkte und
  Zählerüberlauf.
- Tests für ungültige Daten, EOF, Timeout, Prozessabbruch und verweigerte
  sudo-Authentifizierung.
- Test, dass ohne Taste `p` kein sudo-Prozess gestartet wird.
- Test, dass TCC `powerDraw == -1` weiterhin auf die nächste Quelle fällt.
- Syntaxprüfung sowie die bestehenden Pfade `--once`, `--once --no-nvidia`
  und `--version`.
- Kein Root-Test und keine neue Testdatei im Projektverzeichnis; Tests bleiben
  im Scratch-Verzeichnis.

## Dokumentation und Abschluss

Bei der Implementierung werden `VERSION`, `README.md`, `status.md` und
`version.md` synchron auf den nächsten Patchstand erhöht. Die neue Taste, die
explizite sudo-Aktivierung, die Sicherheitsgrenzen und der Status
`RAPL (sudo)` werden dokumentiert. Der vollständig geprüfte Versionsstand wird
als Git-Commit gesichert; ein Tag oder Release wird nicht erstellt.

## Offene Entscheidung vor der Umsetzung

Vor dem Coding ist festzulegen, ob der interne Helper-Modus als versteckte
interne CLI-Option oder als klar dokumentierter technischer Modus im bestehenden
`llmtop.py` umgesetzt wird. Die bevorzugte Variante ist der interne Modus im
bestehenden Einstieg, damit keine zusätzliche Datei und keine neue Abhängigkeit
entsteht.
