# status.md — llmtop

**Version 2.3.56** · Stand 07.11.2026 · Status: History-Metadatenoverlay ergänzt.

## Aktueller Stand

Beim normalen TUI-Start wird beim ersten Lauf ein Onboarding mit Discovery für
lokale Standardports, veröffentlichte Docker-Ports und begrenzte private
LAN-Nachbarn ausgeführt. Gefundene Ollama- und Open-WebUI-Instanzen werden
vorausgewählt; der Open-WebUI-Admin-Key wird verdeckt abgefragt. Die private
Konfiguration liegt unter `$XDG_STATE_HOME/llmtop/config.json`. Der lokale
Collector wird bei Bedarf automatisch mit zufälligem Token gestartet und kann
für ein ausgewähltes LAN-Ziel an eine lokale private Adresse gebunden werden.
Pi- und Open-WebUI-Adapter bleiben voneinander und von Ollama unabhängig.
Nicht-interaktive Modi starten kein Onboarding.

`llmtop.py` ist der Programmeinstieg einer Python-Standardbibliotheks-Anwendung
mit curses-TUI und `--once`-Ausgabe. Die Datenerfassung liegt in
`llmtop_sources.py`, Run-Metriken, History und Collector in `llmtop_metrics.py`
sowie Rendering und TUI-Sampler in `llmtop_tui.py`. Die TUI zeigt die Bereiche
System, GPU, geladene Modelle, aktuelle Runs und History in dieser Reihenfolge. CPU, RAM, GPU, VRAM und Power verwenden
konsistente Balken, Abstände und eine globale Farbsyntax. Die Sensorquellen
werden herstellerübergreifend zusammengeführt: mehrere DRM-GPUs bleiben
sichtbar, NVIDIA wird per PCI-Bus-ID mit sysfs abgeglichen, AMD nutzt amdgpu-
sysfs, Intel i915/xe bekannte GT-Dateien und Temperaturen/Power werden über
zugeordnete hwmon-Geräte ergänzt. Fehlende Einzelwerte bleiben `n/a`; eine
Power-Prozentanzeige wird nur bei echter gemeldeter Leistungsgrenze berechnet. Struktur ist Cyan,
Statuswerte und Temperaturen verwenden Grün/Gelb/Rot, Sekundärinfos sind
gedimmt. Auslastungsbalken verwenden Grün unter 30 %, Amber von 30 bis 59 %,
Orange von 60 bis 90 % und Rot über 90 %. Balkenklammern sind außerhalb der
History normal cyan; der History-Kontext bleibt statusgrau und übernimmt bei
aktiver Cursorzeile deren durchgehende Hervorhebung. Ollama-Modelle zeigen einen geteilten Speicherbalken im gleichen
Raster wie die Sensoren: GPU/VRAM ist Grün oberhalb 55 %, Gelb bei 45–55 %
und Rot darunter; CPU/RAM bleibt gedimmt grau. Beide Anteile verwenden `#`.
CPU-Power wird zuerst aus dem lokalen AMD-APU-Powerwert von GPU1, danach
über eindeutig zugeordnete CPU-hwmon-Geräte und optional TUXEDO Control Center
per lesendem D-Bus-Fallback gemessen; RAPL bleibt die letzte direkte Instanz.
Der interne GPU1-Wert wird als CPU-/APU-Leistung verwendet und bei
vorhandener CPU-Power nicht zusätzlich unter GPU1 dargestellt. Andere
vorhandene GPU-Powerwerte werden weiterhin angezeigt. Fehlende Berechtigungen oder Zählerstände bleiben als `n/a` sichtbar. History speichert begrenzte,
datensparsame JSONL-Snapshots mit UTC-Zeitstempeln. Die Run-History hält bis zu 500 abgeschlossene Runs als scrollbare und sortierbare Tabelle vor; instrumentierte Runs enthalten optional Kontexttoken und Kontextlimit. Die TUI gruppiert diese Anzeige quellengetrennt nach Session-, Chat- oder Message-ID, lässt Gruppen per Cursor aufklappen und zeigt beim Aufklappen weiterhin jeden einzelnen Run.
Aktive Run-Metriken können über einen token-geschützten lokalen HTTP-Collector
(`POST /v1/runs`) geliefert werden. Er verwaltet mehrere parallele Runs,
dedupliziert finale Einträge nach Quelle und Run-ID und zeigt die Quelle in TUI
und Historie. Schema-1-JSONL bleibt als `legacy` lesbar. Zusätzlich instrumentieren `--chat` und `--generate` eigene direkte
Ollama-Aufrufe ohne Reverse Proxy und schreiben einen finalen Run pro Aufruf in
eine getrennte, begrenzte JSONL-Historie. Während des Streamings sind keine
Ollama-Tokenmetriken verfügbar; sie werden erst aus dem finalen `done`-Objekt
gespeichert. Für dieses Layout gilt eine Mindestgröße von
40×18. Bei dieser Größe verwendet die TUI eine kompakte, überlappungsfreie
Darstellung mit System- und GPU-Kernwerten, Modellanzahl, Ollama-Status und History-Status.

## Neu in 2.3.56

- `Enter` öffnet ein geordnetes, scrollbares Overlay mit den Session- und Laufmetadaten des History-Eintrags.
- `Leertaste` sowie `←`/`→` behalten das Auf- und Zuklappen der Gruppen.

## Neu in 2.3.55

- Die Verbrauchsspalte verwendet `Verbrauch` als Überschrift und `Wh` als Einheit der Werte.

## Neu in 2.3.54

- History-Gruppen summieren jetzt auch die Laufzeit ihrer enthaltenen Läufe.

## Neu in 2.3.53

- Energiewerte laufender Open-WebUI- und Pi-Ollama-Runs werden bereits vor dem Abschluss in der Live-Anzeige aktualisiert.
- Die History übernimmt neue Energie-Werte ohne Neustart der TUI.

## Neu in 2.3.52

- History-Gruppen summieren die Kompaktionszähler ihrer enthaltenen Läufe.

## Neu in 2.3.51

- Der Collector misst neben Open-WebUI-Runs jetzt auch lokale Pi-Ollama-Runs.
- Aktuelle Runs und History zeigen deren Energie in Wh; Pi-Gruppen summieren
  die gemessenen Werte. Cloud-Runs im Pi bleiben ohne Wh-Wert.

## Neu in 2.3.50

- Die Dauerspalte zeigt Laufzeiten als Minuten und bei langen Runs als Stunden, z. B. `12m 04s` oder `2h 07m`.

## Neu in 2.3.49

- Pi meldet erfolgreiche automatische und manuelle Compactions pro Run.
- Open WebUI übernimmt Compaction-Events und neue Summary-Checkpoints pro Run.
- Aktuelle Runs und History zeigen die Anzahl in der Spalte `Komp.`.

## Neu in 2.3.48

- Die Tokenspalte zeigt Kontextwerte platzsparend als `16.7/32.8k` mit nur einem `k`.

## Neu in 2.3.47

- Kontextverbrauch und Kontextlimit stehen in Aktuelle Runs und History gemeinsam in der Tokenspalte.
- Der Kontextbalken zeigt den Prozentwert ohne separates Limit direkt neben dem Balken.

## Neu in 2.3.46

- Aktuelle Runs werden unabhängig von der History-Sortierung nach unveränderlicher Startzeit angeordnet.
- Ein Run behält beim laufenden Aktualisieren und beim Abschluss seine Position.

## Neu in 2.3.45

- Run-Zeilen unter „Aktuelle Runs“ werden cyan dargestellt.
- Gruppenüberschriften erscheinen grau und unterstrichen; Kontext und Tok/s behalten ihre dynamischen Farben.

## Neu in 2.3.43

- Lokalen Collector im normalen TUI-Start automatisch starten und bei fehlendem
  Token ein zufälliges lokales Token erzeugen.
- Pi-Adapter und Collector-Laufzeitdaten ohne Ollama- oder Open-WebUI-Setup
  einrichten.

## Neu in 2.3.44

- Interaktives Erststart-Onboarding mit `--setup`, `--discover` und
  `--reset-setup` ergänzt.
- Ollama und Open WebUI werden lokal, über veröffentlichte Docker-Ports und bei
  fehlenden lokalen Treffern begrenzt im privaten LAN gesucht.
- Open-WebUI-Adapter funktionieren auch ohne Docker-Gateway bei lokaler
  Installation; LAN-Ziele erhalten eine passende Collector-Adresse.

## Neu in 2.3.42

- Die interne GPU1-/APU-Powerzeile wird unterdrückt, sobald der zugehörige
  CPU-Powerwert verfügbar ist.
- Andere GPU-Powerwerte bleiben unabhängig davon sichtbar.

## Neu in 2.3.41

- Der Pi-Adapter aktualisiert den Session-Kontext unmittelbar vor dem
  Abschlussereignis erneut.
- Dadurch übernimmt die History den letzten Live-Kontext statt eines älteren,
  zu kleinen Zwischenstands.

## Neu in 2.3.40

- Fehlende GPU1-Power wird explizit als gedimmtes `n/a` angezeigt.
- Andere GPU-Powerwerte bleiben sichtbar, sobald die jeweilige Quelle Daten liefert.

## Neu in 2.3.39

- Die lokale AMD-APU-Leistung von GPU1 wird für die CPU-Power-Abfrage verwendet.
- GPU1-Power wird in der TUI gedimmt dargestellt; direkte RAPL-Abfrage bleibt
  als letzte CPU-Power-Instanz erhalten.

## Neu in 2.3.38

- Pi-Runs verwenden für `eval_duration_s` jetzt die von Pi gemessene Dauer der einzelnen Provider-Antwort (`message.durationMs`).
- Die gesamte Agentenlaufzeit bleibt separat als `total_duration_s` erhalten; Tool-Aufrufe und Folgeturns drücken die Tok/s-Anzeige nicht mehr künstlich.
- Während eines laufenden Turns wird nur dessen eigene verstrichene Zeit als Fallback verwendet.

## Neu in 2.3.37

- Open-WebUI-Usage aus Tool-Loops bevorzugt jetzt die Token des aktuellen Modellaufrufs (`prompt_tokens`/`completion_tokens` beziehungsweise Ollama-Felder).
- Kumulierte `input_tokens`/`output_tokens` werden nur noch als Fallback verwendet und nicht mehr fälschlich als Kontext eines einzelnen Aufrufs angezeigt.
- Der reproduzierte Tool-Use-Fall mit über 100 % Kontext ist durch einen Adapter-Regressionstest abgesichert.

## Neu in 2.3.36

- Der Collector startet für neue Open-WebUI-Runs einen lokalen Energie-Sampler und speichert die Messung beim Abschluss.
- Dadurch können neue WebUI-Runs in der TUI einen Wh-Wert anzeigen; ältere Runs ohne Messdaten bleiben `n/a`.
- Verwaiste WebUI-Energiesampler werden nach dem bestehenden Run-TTL beendet.

## Neu in 2.3.35

- Breite TUI-Tabellen zeigen `Wh` für Open-WebUI-Runs in Aktuelle Runs und History.
- History-Gruppen summieren die Energiewerte aller enthaltenen Open-WebUI-Runs.
- Andere Run-Quellen bleiben in dieser ersten Anzeige ohne Wh-Wert.

## Neu in 2.3.34

- `--energy-rapl-sudo` ermöglicht bei direkten Runs den CPU-RAPL-Zugriff über eine vorhandene nicht-interaktive sudo-Anmeldung.
- Der bestehende privilegierte RAPL-Helper liefert dafür kumulative Energiezähler; ohne Berechtigung bleiben CPU-RAPL-Werte `n/a`.

## Neu in 2.3.33

- Direkte `--chat`-/`--generate`-Runs erfassen verfügbare Komponentenenergie zeitlich begrenzt.
- CPU-RAPL-Zähler, AMD-sysfs-Leistung und kontinuierliche NVIDIA-`nvidia-smi`-Leistung werden als getrennte Quellen gespeichert.
- Benchmarkkennzahlen wie Joule pro Ausgabe- oder Gesamttoken stehen über `energy_metrics()` bereit.
- Überlappende CPU-/integrierte-GPU-Messbereiche werden nicht zu einer irreführenden Gesamtsumme addiert; Steckdosenmessung bleibt außerhalb des Umfangs.

## Neu in 2.3.32

- System-Snapshot-History im TUI-Modus auf höchstens einen Schreibvorgang je fünf Sekunden gedrosselt; `--once` bleibt sofortig.
- Stabile sysfs-/PCI-/hwmon-GPU-Metadaten werden zwischen Samples wiederverwendet; bei geänderter GPU-Topologie wird neu erkannt.
- Wiederkehrende Debugmeldungen werden gedrosselt; Logdateien rotieren mit privaten Dateirechten.
- Unbenutzte Imports und dynamische CLI-Imports bereinigt.

## Neu in 2.3.31

- Standard-Logging mit `--debug` und optionalem `--log-file` ergänzt.
- Im TUI-Modus werden Debugmeldungen standardmäßig in `$XDG_STATE_HOME/llmtop/llmtop.log` geschrieben, damit die curses-Anzeige sauber bleibt.
- Logs enthalten nur technische Diagnoseinformationen und keine Prompts, Modellantworten oder API-Schlüssel.

## Neu in 2.3.30

- Die zusätzliche Breite der eingerückten Zeitfelder wird jetzt auch bei der
  gemeinsamen Tabellenberechnung berücksichtigt; Uhrzeiten werden nicht mehr abgeschnitten.

## Neu in 2.3.29

- Das Zeitfeld aufgeklappter History-Unterzeilen wird innerhalb seiner eigenen
  Spalte um zwei Zeichen eingerückt; die übrigen Spaltenabstände bleiben stabil.

## Neu in 2.3.28

- Die Zwischenräume der History-Spalten erhalten bei der aktiven Zeile jetzt
  ebenfalls den Cursorhintergrund; die Hervorhebung ist dadurch durchgehend.

## Neu in 2.3.27

- Die aktive History-Cursorzeile wird wieder durchgehend hervorgehoben; der
  Kontext bleibt dabei statusgrau und wechselt nicht in eine Live-Auslastungsfarbe.

## Neu in 2.3.26

- Der History-Kontext wird vollständig grau gezeichnet, auch wenn die
  History-Zeile gerade aktiv markiert ist.
- Die Dokumentation nennt jetzt die aktuelle Aktivierungstaste `x`/`X` und die
  vier Auslastungsfarbstufen konsistent.

## Neu in 2.3.25

- Balkenklammern sind außerhalb der History jetzt cyan und normal dargestellt.
  Der Kontext in der History bleibt vollständig grau.

## Neu in 2.3.24

- Die Klammern aller Auslastungs-, Kontext- und Modellbalken sind jetzt immer
  grün und normal statt statusabhängig oder fett dargestellt.

## Neu in 2.3.23

- Die helle mittlere Balkenstufe verwendet nun ein nur wenig helleres Amber
  statt des zu hellen Orange-Tons.

## Neu in 2.3.22

- Auslastungsbalken verwenden nun vier Stufen: Grün unter 30 %, Hell-Orange von
  30 bis 59 %, Orange von 60 bis 90 % und Rot über 90 %.

## Neu in 2.3.21

- Die mittlere Auslastungsfarbe wurde auf 40 bis unter 80 % erweitert; dadurch
  sind CPU-, RAM-, GPU- und Power-Balken häufiger gelb/orange statt grün oder rot.

## Neu in 2.3.20

- TCC-D-Bus wird nach direktem RAPL und CPU-hwmon, aber vor dem optionalen sudo-RAPL-Helper verwendet, sofern gültige Werte verfügbar sind.

## Neu in 2.3.19

- CPU-hwmon wird nach direktem RAPL und vor dem optionalen sudo-RAPL-Helper ausgewertet.

## Neu in 2.3.18

- Die CPU-Power-Quelle wird im Help-Overlay kompakt und vollständig lesbar dargestellt, etwa als `RAPL sudo pkg-0`.

## Neu in 2.3.17

- Die WebUI-Quellenzeile im Help-Overlay wurde auf `WebUI` plus Status verkürzt.

## Neu in 2.3.16

- Das Help-Overlay zeigt zusätzlich die aktuellen Quellen-/Statusinformationen für Open WebUI Collector und Pi Adapter.

## Neu in 2.3.15

- Bedienungseinträge im Help-Overlay sinnvoll nach Beenden, Hilfe, Systemaktionen, Navigation und Sortierung geordnet und ausführlicher beschrieben.

## Neu in 2.3.14

- Jeder Bedienungseintrag steht im Help-Overlay in einer eigenen Tabellenzeile.

## Neu in 2.3.13

- Help-Bedienung und Sensorquellen verwenden jetzt dieselben festen Schlüssel-/Wertspalten; dadurch bleiben CPU/RAM und alle Quellen ausgerichtet.

## Neu in 2.3.12

- Bedienungstabelle auf die verfügbare Help-Breite verdichtet; Slash-Schreibweise und Pfeil-/Pos1-/Ende-Einträge bleiben vollständig lesbar.

## Neu in 2.3.11

- Tastenangaben im Help-Overlay ohne Leerzeichen um `/` formatiert und an die verfügbare Breite angepasst.
- Pfeilnavigation, separate `Pos1`-/`Ende`-Einträge und Quellenzeilen bleiben vollständig lesbar.

## Neu in 2.3.10

- Bedienung im Help-Overlay verwendet durchgehend getrennte Tastenangaben mit `/`, einschließlich `s / S`, `↑ / ↓`, `Pos1` und `Ende`.
- Die Gruppe-Aktion steht direkt hinter den Pfeiltasten; Enter/Space wird dort nicht mehr angezeigt.

## Neu in 2.3.09

- Bedienungszeilen im Help-Overlay tabellarisch mit festen Tasten-/Aktionsblöcken angeordnet.
- Rahmen-Seiten und Ecken werden durchgehend cyan gezeichnet.

## Neu in 2.3.08

- Das Help-Overlay verwendet einen klaren Titelrahmen, getrennte Bedienungs- und Sensorquellenbereiche sowie ausgerichtete Quellwerte.

## Neu in 2.3.07

- Die Help-Seite wurde in Bedienung und Sensorquellen gegliedert und zeigt aktuelle CPU-Power-, CPU-Temperatur-, GPU-, RAM- und Ollama-Quellen.
- `h`/`H` ist in der Fußzeile ausdrücklich als Help-Taste sichtbar.

## Neu in 2.3.06

- Die Tastenbuchstaben der Fußzeile werden wie die Steuersymbole cyan dargestellt.

## Neu in 2.3.05

- `c`/`C` verlangt vor dem atomaren Leeren der Run-History die Bestätigung `j`/`y`; jede andere Eingabe bricht ab.

## Neu in 2.3.04

- Die TUI weist in der Power-Zeile auf `x: sudo aktivieren` hin; die Fußzeile verwendet `x sudo`.
- Die Aktivierungstaste wurde von `p` auf `x` geändert.

## Neu in 2.3.3

- CPU-Power-Balken ohne gemeldete Leistungsgrenze verwenden eine reine 65-W-Darstellungsskala und bleiben als Wattwert gekennzeichnet.

## Neu in 2.3.2

- Die CPU-Power-Systemzeile heißt nun `Power`; bei echter Leistungsgrenze verwenden Balken und Wert dynamische Grün-/Gelb-/Rot-Farben.
- Ohne Leistungsgrenze wird ein gültiger Wattwert grün dargestellt, ohne eine künstliche Prozentgrenze zu verwenden.

## Neu in 2.3.1

- CPU-Power-Wert und Balken werden im TUI auch ohne gemeldete Leistungsgrenze farbig dargestellt, ohne eine Prozentgrenze zu erfinden.

## Neu in 2.3.0

- Die TUI-Taste `p`/`P` startet nach expliziter `sudo -v`-Bestätigung einen begrenzten Root-Helper für nur lesende RAPL-Zähler.
- Die laufende llmtop-Sitzung bleibt erhalten; der Helper liefert JSONL-Messpunkte und wird beim Beenden beendet.
- Ohne explizite Aktivierung bleiben sudo und Root-Prozesse unberührt; bei Fehlern bleiben die bisherigen CPU-Power-Fallbacks aktiv.

## Neu in 2.2.37

- CPU-Package-Power nutzt dynamische powercap-/RAPL-Zonen mit Zählerüberlaufbehandlung.
- CPU-nahe hwmon-Leistungswerte werden von GPU-hwmon getrennt; TUXEDO Control Center bleibt ein optionaler, rein lesender D-Bus-Fallback.
- CPU-Power erscheint in `--once`, TUI und System-Snapshots mit Quelle und echter Leistungsgrenze.

## Neu in 2.2.36

- cgroup-Mounts werden über `/proc/self/mountinfo` und `/proc/self/cgroup` ermittelt, einschließlich nichtstandardmäßiger Mountpfade.
- Intel-GPUs prüfen zusätzliche generische GT-/Busy-sysfs-Pfade; nicht vorhandene Kernelzähler bleiben `n/a`.
- PCI-Namen und GPU-Sensoren bleiben ohne neue externe Abhängigkeiten.

## Korrektur in 2.2.35

- Integrierte Radeon-Zusatzbezeichnungen werden aus dem CPU-Modellnamen entfernt; angezeigt wird nur der CPU-Name.

## Korrektur in 2.2.34

- Die Load-Anzeige wurde aus der CPU-Modellzeile entfernt; sichtbar bleiben Modellname und nutzbare Kernanzahl.

## Neu in 2.2.33

- CPU-Modellnamen aus `/proc/cpuinfo` werden neben der nutzbaren Kernanzahl angezeigt.

## Korrektur in 2.2.32

- DRM-GPUs verwenden nun den Modellnamen aus `product_name` oder der lokalen PCI-ID-Datenbank statt der technischen `cardN`-Bezeichnung.

## Korrektur in 2.2.31

- Mehrere GPUs werden in TUI und `--once` durch sichtbare Trennzeilen klar voneinander getrennt.

## Korrektur in 2.2.30

- GPU-Power ohne gemeldete Leistungsgrenze verwendet wieder eine grafische 115-W-Darstellungsskala; der Wattwert bleibt der primäre Textwert.

## Korrektur in 2.2.29

- GPU-Power ohne gemeldete Leistungsgrenze zeigt den gemessenen Wattwert nun im primären Wertefeld statt nur in der grauen Detailspalte.

## Neu in 2.2.28

- Mehrere GPUs und gemischte AMD-/NVIDIA-Systeme werden nicht mehr durch eine einzelne Quellenkette verdeckt.
- DRM-Geräte werden exakt als `cardN` erkannt; GPUs ohne Auslastungsdatei bleiben mit verfügbaren Teilwerten sichtbar.
- NVIDIA-Werte werden über `pci.bus_id` mit sysfs-Geräten verbunden; hwmon wird über reale Gerätepfade zugeordnet.
- CPU-Temperaturen nutzen zusätzlich generische Thermal-Zones und ältere hwmon-Fallbacks.
- RAM berücksichtigt endliche cgroup-v1/v2-Limits; die nutzbare CPU-Anzahl folgt der Prozessaffinität.
- Power ohne gemeldete Leistungsgrenze wird nicht mehr als Prozentwert einer festen 115-W-Skala dargestellt.

## Korrektur in 2.2.18

- Fettdarstellung aus Gruppen- und Cursorfarbe entfernt: Gruppen erscheinen weniger hell, Cursortext bleibt tatsächlich schwarz auf Cyan.
- Ohne Farbsupport verwendet der Cursor weiterhin inverse Darstellung, aber nicht mehr fett.

## Neu in 2.2.17

- History-Gruppen werden in hellem Grau statt Struktur-Cyan dargestellt.
- Die Cursorzeile verwendet kontrastreiche schwarze Schrift auf Cyan; ohne Farbsupport bleibt die inverse Fettdarstellung erhalten.

## Korrektur in 2.2.16

- Der Quelltext einzelner Runs beginnt nun sichtbar zwei Spalten hinter dem Quelltext der Gruppenzeile; der zweistellige Aufklappmarker wird dabei berücksichtigt.

## Neu in 2.2.15

- In aufgeklappten History-Gruppen wird ausschließlich die Quelle der einzelnen Runs eingerückt; alle anderen Tabellenspalten bleiben ausgerichtet.

## Neu in 2.2.14

- `c` oder `C` leert die persistierte Run-History atomar und setzt Cursor, Scrollposition und aufgeklappte Gruppen zurück.
- Aktuelle Runs und die getrennte System-Snapshot-History werden nicht gelöscht.

## Neu in 2.2.13

- Der Pi-Adapter merkt sich die Session-ID bereits beim `session_start` und überträgt sie bei jedem Collector-Run.
- Pi-Sessions verwenden dieselbe Kopfzeile wie Open-WebUI-Chats: Werte des neuesten abgeschlossenen Runs, eindeutig abgeleitete Ergänzungen sowie aufklappbare Einzelruns.

## Neu in 2.2.12

- Open-WebUI-History verwendet `chat_id` vor `session_id`; verschiedene Chats derselben Browser-Session bleiben getrennt.
- Gruppenzeilen zeigen alle Tabellenspalten des neuesten abgeschlossenen Runs. Fehlende Kontext-, Gesamt- und Ratenwerte werden nur eindeutig aus diesem Run abgeleitet; ältere Runs werden weder summiert noch zur Status- oder Modellbestimmung verwendet.
- Aufklappen zeigt weiterhin sämtliche einzelnen Runs des Chats.

## Neu in 2.2.11

- Der Pi-Adapter übernimmt die Session-ID auch bei älteren Session-Manager-Objekten zuverlässig aus Session-Header oder Sessiondatei; neue Pi-Runs werden dadurch tatsächlich gruppierbar.
- Bereits gespeicherte Runs ohne Identitätsfeld bleiben absichtlich einzelne Runs; nach dem Adapter-Update ist für laufende Pi-Prozesse einmal `/reload` erforderlich.

## Neu in 2.2.10

- Die Run-History gruppiert Runs quellengetrennt nach `session_id`, ersatzweise `chat_id` und danach `message_id`.
- Gruppen sind standardmäßig eingeklappt, zeigen Anzahl, Kurzkennung und letzten Abschluss und lassen sich per Cursor, Enter, Leertaste oder Links/Rechts öffnen.
- Einzelne Runs ohne stabile Identität bleiben einzeln; Persistenz und Sortierung bleiben unverändert.

## Neu in 2.2.9

- Schema-2-Runs speichern optional `session_id`, `chat_id` und `message_id`.
- Pi überträgt die stabile Session-ID; Open WebUI überträgt die vorhandenen Metadaten-IDs.
- Aktuelle Runs werden anhand vorhandener Session-/Chat-IDs gruppiert und mit einer kurzen Kennung wiedererkennbar dargestellt.

## Neu in 2.2.8

- Die Kontextanzeige in aktuellen Runs und History stellt den Balken vor den Prozentwert: `[######      ] 42% 16.4k`.

## Neu in 2.2.7

- Der Pi-Adapter-Status wird in der Kopfzeile angezeigt; die bisherige Autoren- und Python-Standardbibliothekszeile entfällt.

## Neu in 2.2.6

- Geladene Modelle verwenden eine gemeinsame Metadaten-Startspalte und feste Spalten für Parametergröße, Quantisierung, Kontext und Runner.

## Neu in 2.2.5

- Prozentwerte in aktuellen Runs und History sind fest vier Zeichen breit und rechtsbündig; dadurch beginnt der Kontextbalken unabhängig von ein-, zwei- oder dreistelligen Werten.

## Neu in 2.2.4

- Kontextspalten zeigen nach dem Fortschrittsbalken nur noch das maximale Kontextlimit.

## Neu in 2.2.3

- Bereits gemeldete Tokenstände aktiver Runs bleiben erhalten, wenn ein Provider in einer Zwischenmeldung vorübergehend `0` liefert.

## Neu in 2.2.2

- Aktuelle Runs und History verwenden nun dieselbe dynamisch aus beiden Listen bestimmte Spaltenbreite und fluchten dadurch exakt.

## Neu in 2.2.1

- Sichtbare Spalten der aktuellen Runs und der History richten ihre Breite dynamisch nach Überschrift und Inhalt aus; die History wertet dafür alle gespeicherten Zeilen aus.

## Neu in 2.2.0

- Live-Run-Tabelle verwendet dieselben Überschriften und Spaltenpositionen wie die History.
- Tok/s wird direkt in der gemeinsamen Tok/s-Spalte gezeichnet.
- Der Live-Kontextbalken steht ausschließlich in der Kontextspalte und ist statusabhängig farbig; Verbrauch und Limit bleiben grau.

## Neu in 2.1.20

- Kontextspalte in History und aktuellen Runs auf `42% [######      ] 6.8k/16.4k` vereinheitlicht.
- Live-Kontextbalken ausschließlich innerhalb der Tabellenspalte dargestellt.

## Neu in 2.1.19

- Unter jedem aktuellen Run eine zusätzliche Kontextzeile mit Fortschrittsbalken ergänzt.
- Platzberechnung auf zwei Zeilen pro aktuellem Run angepasst.

## Neu in 2.1.18

- Kontextspalte in aktueller Run- und History-Tabelle ab 80 Terminalspalten wieder aktiviert.

## Neu in 2.1.17

- Aktuelle Runs übernehmen die History-Spalten und Werte einschließlich Zeit, Tokens, Kontext, Tok/s und Dauer.

## Neu in 2.1.16

- Modell-Speichergrößen in MiB dargestellt; die Einheit erscheint nur einmal nach dem zweiten Wert.

## Neu in 2.1.15

- Modell-Speichergrößen ohne Bezeichner im kompakten Format `GiB / GiB` dargestellt.

## Neu in 2.1.14

- Modell-Prozentwert auf die Sensor-Flucht ausgerichtet.
- Zweiten CPU/RAM-Prozentwert entfernt; der CPU/RAM-Anteil bleibt grau im Balken und in der Größenangabe.

## Neu in 2.1.13

- TUI-Reihenfolge auf System, GPU, geladene Modelle, aktuelle Runs und History umgestellt.
- Modell-, Run- und History-Bereiche erhalten feste Platzreservierungen gegen Überlappung.

## Neu in 2.1.12

- Tok/s und Laufalter werden in Run-Zeilen rechtsbündig und kollisionsfrei dargestellt.
- `0,0 Tok/s` wird als neutraler grauer Sekundärwert dargestellt.

## Neu in 2.1.11

- Kontextverbrauch aktiver Runs bleibt in der kompakten TUI-Ansicht sichtbar.

## Neu in 2.1.10

- Der Pi-Adapter liest den kompaktionsbereinigten Session-Kontext über `sessionManager`.
- Der Kontextverbrauch wird während aktiver Runs einmal pro Sekunde aktualisiert, ohne Sessioninhalte zu übertragen.

## Neu in 2.1.9

- Pi sendet bekannte Provider-Usage während aktiver Streams höchstens einmal pro Sekunde sowie nach jedem Modellturn.
- Kontext und Tok/s werden dadurch bereits vor dem finalen Session-Abschluss aktualisiert.

## Neu in 2.1.8

- Bereits gespeicherte Doppelmeldungen mit identischen Open-WebUI-Metriken werden in der History dedupliziert.

## Neu in 2.1.7

- Veraltete globale `otop_run_metrics`-Adapter werden beim Adapter-Setup deaktiviert.
- Dadurch werden Open-WebUI-Runs nicht mehr doppelt an den Collector gesendet.

## Neu in 2.1.6

- Pi überträgt Cache-Input zum Kontextverbrauch, das Modell-Kontextlimit sowie Gesamtdauer und Ausgaberate.
- Ollama-Pi-Runs zeigen dadurch Tok/s und Dauer; ChatGPT-Pi-Runs zeigen Kontextgröße, Prozent und Tok/s.

## Neu in 2.1.5

- Der Pi-Adapter fasst alle Modell- und Tool-Folgeturns einer bearbeiteten Anfrage zu einem Live-Run zusammen.
- Erst der finale `agent_settled`-Abschluss schreibt das Ergebnis der sichtbaren Antwort in die Run-History.

## Neu in 2.1.4

- Finale Live-Runs laufen zehn Sekunden nach `finished_at` ab und werden atomar aus `run.jsonl` bereinigt; die begrenzte Run-History bleibt erhalten.
- Aktive Pi- und Open-WebUI-Runs stehen vor Ergebnissen und werden in gleichartigen Quellenblöcken mit sichtbaren Zählern dargestellt.

## Neu in 2.1.3

- Ein neuer Pi- oder WebUI-Run entfernt den letzten Abschluss derselben Quelle nicht mehr aus der Live-Anzeige.
- Aktuelle Runs priorisieren Pi vor WebUI und kennzeichnen Quelle getrennt nach aktiv und erledigt.

## Neu in 2.1.2

- Pi und Open WebUI senden auf getrennte Collector-Pfade; der Collector erzwingt die passende Quelle.
- Letzte Abschlüsse bleiben je Quelle in der Live-Datei erhalten, und die Kompaktansicht sowie schmale History zeigen die Quelle zwingend.
- Aktive ältere Open-WebUI-Filter werden anhand ihres Inhalts erkannt und beim TUI-Start aktualisiert.

## Neu in 2.1.1

- Normaler TUI-Start installiert oder aktualisiert den globalen Pi-Adapter und schreibt dessen private Collector-Laufzeitdaten mit Modus `0600` unter dem bestehenden llmtop-State-Pfad.
- Neue Pi-Prozesse benötigen keine manuell exportierten Collector-Variablen mehr; bereits laufende Instanzen werden einmal neu geladen oder gestartet.

## Neu in 2.1.0

- Pi-Adapter meldet lokale und Cloud-Modellturns datensparsam über den bestehenden Collector.
- Run-Schema, TUI, `--once` und History unterscheiden Quelle und optionalen Provider; parallele Runs bleiben erhalten und der aktive Bereich ist scrollbar.
- Open-WebUI-Filter überträgt verifizierte Provider nicht mehr nur für Ollama.

## Neu in 2.0.7

- Intervallanzeige mit der `-/+`-Legende rechtsbündig in die Statusleiste
  verschoben.

## Neu in 2.0.6

- „LLM Terminal Monitor“ in jeder gültigen Terminalbreite horizontal mittig
  in der ersten Kopfzeile platziert.

## Neu in 2.0.5

- Kopf-Logo als Terminalfenster gestaltet: Prompt, Aktivitätspixel und
  LLM-Kennung verbinden den Monitor mit seinem Einsatzzweck.

## Neu in 2.0.4

- Logo auf acht Zeichen Breite erweitert, damit es im üblichen Terminalraster
  optisch quadratisch erscheint.
- Zwei freie Spalten zwischen Logo und Kopftext ergänzt.

## Neu in 2.0.3

- Vierzeiliges Kopf-Icon durch ein quadratisches Pixel-Logo ersetzt.
- Leerzeile nach dem Kopf ergänzt und die Ollama-Version direkt an den Namen
  gesetzt.

## Neu in 2.0.2

- Kopfbereich als vierzeilige Produktidentität mit Pixel-Icon, Version,
  Verbindungsstati, Autor, Technik und Refresh-Intervall gestaltet.
- Die 40×18-Kompaktansicht lässt VRAM- und Power-Zeilen weg, damit der größere
  Kopf ohne Überlappung Platz findet.

## Neu in 2.0.1

- Normaler TUI-Start prüft den global aktiven Open-WebUI-Filter asynchron und
  installiert ihn bei Fehlen oder Deaktivierung automatisch.
- Ohne vollständige lokale Konfiguration, bei API-Fehlern sowie in `--once`-
  und Skriptmodi bleibt die Adapter-Konfiguration unverändert.

## Neu in 2.0.0

- Harter Namenswechsel von otop zu llmtop: Kommando, Python-Module,
  Open-WebUI-Filter, `LLMTOP_*`-Umgebungsvariablen und State-Pfad sind umgestellt.
- Kopfzeile und `--once` verwenden das neue Pixel-Icon.
- Alte otop-Dateien, Variablen und State-Pfade werden nicht mehr unterstützt;
  der neue Open-WebUI-Filter muss einmal installiert werden.

## Korrekturen in 1.10.12

- Namen Ollama und Open-WebUI Collector in der Kopfzeile gedimmt grau gesetzt.
- Redundanten Ollama-Abschnitt samt Collector-Zeile entfernt.

## Korrekturen in 1.10.11

- Collector als „Open-WebUI Collector“ bezeichnet.
- Namen der Verbindungen Cyan, aktive Stati Grün und nicht aktive Stati Rot.

## Neu in 1.10.10

- Kopfzeile zeigt Ollama- und Collector-Verbindungsstatus, auch verdichtet bei
  schmalem Terminal.
- TUI-Standardintervall auf 0,5 s und Untergrenze auf 0,2 s gesetzt.

## Korrekturen in 1.10.9

- Bereichslinien beginnen in Spalte 0; alle Inhalte haben einen Zeichenabstand links.
- Tabulatorposition zwischen Modellname und Metadaten auf 16 Spalten verkürzt.

## Korrekturen in 1.10.8

- Tok/s-Farben ohne Fettdruck dargestellt.

## Korrekturen in 1.10.7

- Nur der VRAM-Prozentwert bleibt farbig; `/RAM%` und Größen bleiben grau.
- Tok/s aktueller Runs ist rot unter 10, gelb unter 50 und grün ab 50 Tok/s.

## Korrekturen in 1.10.6

- Modell-VRAM/RAM zeigt nach dem Balken erst die Prozentwerte `%/%` und danach
  gedimmt die VRAM- und RAM-Größen in GiB.

## Korrekturen in 1.10.5

- Kontextanzeige auf das Raster von CPU und GPU ausgerichtet: Prozentwert
  rechtsbündig nach dem Balken, Verbrauch/Limit gedimmt grau danach.

## Korrekturen in 1.10.4

- Kontextanzeige aktueller Runs zeigt Prozent vor Verbrauch und Limit.
- Bereichsüberschriften sind eingerückt und besitzen Linien vor und nach dem Titel.

## Korrekturen in 1.10.3

- Modellnamen grau und unterstrichen dargestellt.
- Aktuelle Runs verwenden Tabulatoren für Quelle, Modell, Status und Metriken.

## Korrekturen in 1.10.2

- Modellnamen wieder Cyan und unterstrichen dargestellt.
- Folgende Modellinformationen beginnen an einer festen Tabulatorposition.

## Korrekturen in 1.10.1

- Kontextlabel vor dem Balken auf Cyan statt Dunkelgrün gesetzt.
- Kleinere Änderungen erhöhen künftig standardmäßig nur die Patchversion.

## Neu in 1.10.0

- Modell-Speicheranzeige unter „Geladene Modelle“ als VRAM/RAM beschriftet.
- Modellnamen sind grau und unterstrichen; das Kontextlabel vor seinem Balken ist Cyan.

## Neu in 1.9.0

- Der letzte abgeschlossene aktuelle Run bleibt mit seinen finalen Token- und
  Zeitwerten sichtbar, bis ein neuer Run beginnt.
- Finale Ereignisse ergänzen zuvor bekannte Start- und Kontextwerte vor der
  Persistierung in die Run-History.

## Korrekturen in 1.8.8

- TUI-Start mit Run-History inklusive Tokenwerten repariert: `total_tokens`
  wird im herausgelösten curses-Modul wieder aus den Metriken importiert.

## Korrekturen in 1.8.7

- TUI-Start mit geladenem Modell repariert: `datetime` für die Unload-Zeit ist
  im herausgelösten curses-Modul wieder verfügbar.

## Korrekturen in 1.8.6

- TUI-Start mit vorhandener Run-History repariert: `_parse_time` wird im
  herausgelösten curses-Modul wieder aus den Metriken importiert.

## Neu in 1.8.5

- Sensoren, Ollama-Zugriffe, Run-Metriken/Collector und curses-TUI sind in drei
  überschaubare Kernmodule aufgeteilt; `llmtop.py` bleibt der kompatible Einstieg.
- Die TUI erfasst Daten in einem einzelnen Hintergrund-Thread. HTTP-,
  `nvidia-smi`-, sysfs- und History-Schreibzugriffe blockieren die Tastatur und
  das Rendering nicht mehr.
- Schema-2-Ereignisse mit Quelle `pi` werden durch denselben Collector wie Open
  WebUI verarbeitet und sind damit für den späteren optionalen Pi-Adapter
  vorbereitet.

## Korrekturen in 1.8.4

- Die Unterstreichung der aktiven Sortierspalte endet direkt mit dem Spaltentext und umfasst keine Auffüllung mehr.
- Zwischen History-Tabelle und Statusleiste bleibt eine vollständig leere Zeile; die 40×18-Ansicht fasst dafür Modell- und Run-Anzahl in einer Zeile zusammen.

## Korrekturen in 1.8.3

- Die Kontextzelle zeigt den Prozentwert vor Verbrauch und Limit, zum Beispiel `33% 10.9k/32.8k`.
- Die History-Überschrift enthält keine redundante Sortieranzeige mehr; stattdessen ist der aktive Spaltenkopf unterstrichen und trägt den Richtungspfeil.

## Korrekturen in 1.8.2

- Die History-Spalte Kontext wird nach dem tatsächlichen prozentualen Verbrauch sortiert, nicht nach der absoluten Zahl genutzter Token; Einträge ohne Limit folgen zuletzt.
- Die aktive Sortierspalte ist direkt im Tabellenkopf mit `▾` oder `▴` markiert.

## Korrekturen in 1.8.1

- TUI-Abbruch nach Start oder bei History-Navigation behoben: `curses.KEY_TAB` ist nicht auf allen Python-curses-Versionen vorhanden; die Tab-Taste verwendet nun den portablen Code `9`.

## Neu in 1.8.0

- Die Run-History ist eine scrollbare TUI-Tabelle für bis zu 100 finale Einträge und kann nach allen angezeigten Spalten sortiert werden.
- Die Kontextspalte zeigt Verbrauch, Limit und Prozentwert beziehungsweise transparent `n/a`; fehlende Werte werden beim Sortieren zuletzt geführt.
- Die bestehende begrenzte JSONL-Datei bleibt die Datenquelle. Eine Datenbank ist für höchstens 100 kleine, atomar geschriebene Einträge nicht erforderlich.

## Korrekturen in 1.7.4

- Wiederholte `request`-Filteraufrufe derselben Open-WebUI-Nachricht erzeugen bei Tool- und Fortsetzungsrunden keinen zusätzlichen aktuellen Run mehr.
- Parallele Open-WebUI-Anfragen mit unterschiedlichen Nachrichten-Identitäten bleiben weiterhin getrennte Runs; API-Aufrufe ohne stabile Identität werden nicht pauschal zusammengeführt.

## Korrekturen in 1.7.3

- Aktive Runs werden nach 90 Sekunden ohne Update als verwaist entfernt; lange Tool-Use-Anfragen senden während des Streams regelmäßig Lebenszeichen und werden dadurch nicht fälschlich entfernt.
- Verwaiste Live-Einträge erscheinen nicht mehr unter „Aktuelle Runs“ und werden nicht historisiert.
- Parallele Collector-Schreibzugriffe auf Live- und Run-History-Dateien sind synchronisiert; abgeschlossene Runs können nicht mehr durch konkurrierende Updates wieder auftauchen.
- Der Open-WebUI-Adapter ordnet Runs bei fehlender oder widersprüchlicher Identität nicht spekulativ einem anderen parallelen Tool-Use-Run zu.

## Korrekturen in 1.7.2

- Die Run-History rendert bis zu zehn abgeschlossene Runs statt nur des jüngsten.
- Der Open-WebUI-Adapter finalisiert einen Run nicht mehr automatisch als `cancelled`, wenn nur der Request-/Stream-Kontext endet; echte Abbrüche werden ausschließlich über explizite Abbruchsignale übernommen.
- Aktive Runs bleiben bis zum finalen Stream- oder Outlet-Ereignis in der Live-Datei.

## Vorherige technische Korrekturen (1.1.0)

- `/api/ps`-Fehler werden nicht mehr gleichzeitig als „kein Modell geladen“
dargestellt.
- Nicht-numerische NVIDIA-Auslastung wird als `n/a` angezeigt statt eine
Formatierungs-Ausnahme in der TUI auszulösen.
- Ein nicht erfolgreicher `nvidia-smi`-Prozess liefert keine scheinbaren
Messwerte; bei fehlenden NVIDIA-Daten erfolgt der sysfs-Fallback.
- `--no-nvidia` verwendet sysfs und behält dort AMD- und Intel-Geräte bei.
Mehrere NVIDIA-Geräte werden nicht mehr verworfen.
- VRAM-Werte werden intern einheitlich in MiB ausgegeben: `nvidia-smi` liefert
bereits MiB, sysfs-Werte werden von Bytes umgerechnet.
- CPU-Auslastung wird pro Refresh-Intervall berechnet.
- VRAM- und Power-Zeilen erscheinen in TUI und `--once`; der Hilfe-Dialog zeigt
nun auch seinen Text.
- Docstring und Projektdokumentation verweisen nur auf tatsächlich verwendete
Ollama-Endpunkte beziehungsweise vorhandene Dateien.

## Weiterhin bekannte Grenzen

- Der Kontextbalken verwendet Prompt- plus Ausgabetoken. Das Limit stammt aus `options.num_ctx` oder wird für passende Runs zuverlässig aus `context_length` des aktuell geladenen Modells in `/api/ps` übernommen und in der Run-History nachgetragen. Ein serverseitiger KV-Cache ist nicht separat sichtbar. Wenn der Provider Usage bereits während des Streams liefert, wird der Liveverbrauch aktualisiert; andernfalls bleibt er bis zum Abschluss unbekannt.

- GPU-Auslastung ist geräteweit und nicht exklusiv Ollama zurechenbar.
- NVIDIA-SMI und sysfs werden parallel als ergänzende Quellen abgefragt und über
  PCI-Bus-ID beziehungsweise Hersteller-Reihenfolge zusammengeführt. Sehr alte
  NVIDIA-Treiber ohne `pci.bus_id` können bei mehreren identischen Karten nur
  best-effort zugeordnet werden.
- Für Modellkarten gibt es keinen Scroll-Modus. Passen sie nicht vollständig
  in den verfügbaren Bereich, zeigt die TUI ihre Anzahl als ausgeblendet an;
  die Run-History ist unabhängig davon scrollbar.
- Power-Limits sind nur verfügbar, wenn die jeweilige Quelle sie meldet.
- Die TUI zeigt während einer langsamen Quelle den letzten vollständigen
  Snapshot. Der Hintergrund-Sampler selbst wartet weiterhin auf den jeweiligen
  HTTP- oder `nvidia-smi`-Timeout; es gibt bewusst noch keine Parallelabfragen.
- Git ist im Projektverzeichnis initialisiert; Entwicklungsbranch ist `master`.
- Der direkte Client-Modus instrumentiert nur Aufrufe, die über `llmtop` selbst
  erfolgen; fremde Ollama-Clients bleiben ohne Adapter unsichtbar.
- Der Open-WebUI-Adapter wird mit `--install-open-webui-adapter` per Admin-API
  installiert, konfiguriert und global aktiviert. Dafür muss ausschließlich
  `OPEN_WEBUI_API_KEY` in der lokalen llmtop-`.env` gesetzt sein. Der Pi-Adapter
  ist weiterhin offen.

## Prüfung am 31.10.2026

- Pseudo-TTY-Prüfung: Bei 120×40 erscheinen Tabellenkopf, Sortierstatus und Kontextspalte; bei 40×18 bleibt die kompakte Tabellenansicht sichtbar. Normaler `q`-Exit ist auf beiden Größen Code 0.
- Sortier- und Kontexttests: alle acht Spalten, fehlende Werte und 100 geladene Historieneinträge erfolgreich.
- Visuelles Live-Debugging mit drei `request`-Aufrufen derselben Open-WebUI-Identität: Die Anzeige blieb durchgehend bei genau einem aktuellen Run; das finale Outlet entfernte ihn und erzeugte genau einen History-Eintrag.
- Vor dem 2.0-Umstieg waren installierter Open-WebUI-Filter und lokale Version
  `1.3.2` identisch. Der neue llmtop-Filter trägt `2.0.0` und wird separat
  installiert; ein echter Streaming-Aufruf über `/api/chat/completions` zeigte
  zuvor maximal einen Live-Eintrag.
- Run-History zeigt in `--once` zehn Einträge; bestehende ältere `cancelled`-Einträge bleiben als historische Altdaten unverändert.
- Lokaler und global installierter Open-WebUI-Adapter sind identisch, aktiv und global aktiviert; der Disconnect-Watcher ist entfernt.
- `python3 llmtop.py --install-open-webui-adapter`: erfolgreich.
- `python3 -m py_compile`, beide llmtop-Testmodule, `--once`, `--once --no-nvidia` und `--version`: erfolgreich.
- Paralleler Live-Run-Test: keine verwaisten Einträge nach konkurrierenden Start-/Abschlussupdates.


- `python3 -m py_compile llmtop.py`: OK.
- `python3 llmtop.py --version`: `llmtop 2.0.1`.
- `python3 llmtop.py --once` und `--once --no-nvidia`: OK.
- Mock-Rendering: 0/100-, 44/56-, 50/50-, 56/44-, 100/0- und fehlende
  Speichergrößen nutzen erwartete Segmentbreiten, Offload-Farben,
  Übergangsmarker sowie gedimmtes `n/a`: OK.
- Pseudo-TTY mit Beenden: OK; bei 80×24 vollständige Ansicht, bei 40×18 kompakte Ansicht ohne überzeichnete Modell- oder History-Zeilen.
- Git-Repository: initialisiert, Arbeitsbaum vor dem ersten Commit ungeordnet.
- Open-WebUI-Filtertest: Start, finaler Stream-Chunk, Outlet-Deduplizierung,
  parallele Metadaten-Schlüssel und datensparsame Ereignisse: OK.
- Container-Netz geprüft: `open-webui` nutzt `ai-net`, Gateway `172.18.0.1`.
- API-Installation mit lokalem Admin-Key: Filter `llmtop_run_metrics` erfolgreich
  angelegt, Valves gesetzt sowie aktiv und global geschaltet.
- Live-Chat über `/api/chat/completions` mit `qwen3.5:4b`: HTTP 200, ein
  finaler `open-webui`-Run mit Prompt- und Ausgabe-Token in `runs.jsonl`.
  Die von Open WebUI durchgereichte finale Datenform enthielt keine
  Gesamtdauer; sie bleibt erwartungsgemäß `n/a`.
- Collector-Test mit `started` und `completed`: HTTP 202, aktiver Run entfernt,
  finaler Schema-2-Eintrag inklusive Quelle und umgerechneter Dauern gespeichert.
- Direkter Live-Test: `--chat` gegen `qwen3.5:4b` lieferte finale
  `prompt_eval_count`, `eval_count` sowie Dauerwerte; der Abschlusslauf wurde
  in `runs.jsonl` geschrieben.

Eine visuelle Kontrolle in einem echten interaktiven Terminal bleibt sinnvoll.
