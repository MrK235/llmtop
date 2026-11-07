# Plan: Automatisches llmtop-Onboarding und Instanzerkennung

## Ziel

Beim ersten interaktiven Start von `llmtop` soll ein geführtes Onboarding erscheinen.
Es erkennt verfügbare Ollama- und Open-WebUI-Instanzen automatisch und fragt nur
noch fehlende Angaben wie Open-WebUI-URL und Admin-API-Key ab. Lokale,
Docker-basierte und erreichbare LAN-Installationen sollen unterstützt werden,
ohne Ollama oder Open WebUI vorauszusetzen.

Bestehende Aufrufe wie `--once`, `--version`, `--collector`, `--chat` und
`--generate` dürfen nicht interaktiv blockieren.

## Aktueller Befund

- Ollama wird derzeit nur über `--host`, `OLLAMA_HOST` oder `localhost:11434`
  angesprochen.
- Open WebUI wird nur mit expliziter URL und Admin-API-Key eingerichtet.
- Die Open-WebUI-Installation erwartet aktuell eine Docker-Gateway-Adresse und
  behandelt lokal installierte WebUI dadurch nicht gleichwertig.
- Der Pi-Adapter und der lokale Collector sind ab Version 2.3.43 autonomer
  eingerichtet, besitzen aber noch kein Benutzer-Onboarding.
- Das Projekt verwendet ausschließlich die Python-Standardbibliothek.

## Umsetzung in drei Schritten

### 1. Erkennung und Konfigurationsmodell

Eine neue, zentrale Discovery-Funktion in `llmtop_sources.py` oder einem kleinen
Bereich des bestehenden Moduls ermittelt Kandidaten mit kurzen Timeouts und
ohne externe Scanner.

Reihenfolge:

1. explizite CLI- und Umgebungswerte (`--host`, `OLLAMA_HOST`,
   `OPEN_WEBUI_URL`),
2. lokale Adressen und Standardports,
3. Docker-/Container-Adressen,
4. begrenzte LAN-Nachbarn.

#### Ollama-Kandidaten

- `OLLAMA_HOST`
- `localhost` und `127.0.0.1` auf Port `11434`
- IPv6-Loopback
- Docker-Service-/Gateway-Adressen, sofern aus vorhandenen Docker-Netzdaten
  ermittelbar
- erreichbare LAN-Adressen auf Port `11434`

Validierung über `GET /api/version`; optional anschließend `GET /api/ps`.
Ollama benötigt keinen Adapter und normalerweise keinen API-Key.

#### Open-WebUI-Kandidaten

- `OPEN_WEBUI_URL`
- lokale Standardports `3000` und `8080`
- Docker-Port-Mappings und private Docker-Gateways
- erreichbare LAN-Adressen auf den Standardports

Validierung über eine unkritische Open-WebUI-API-Anfrage. HTTP-401/403 gilt als
„Instanz vorhanden, Zugangsdaten fehlen“ und nicht als Nichterreichbarkeit.

#### LAN-Begrenzung

Kein unkontrollierter Gesamtnetz-Scan. Automatisch geprüft werden zunächst:

- bekannte Nachbarn aus `/proc/net/arp`,
- lokale private Netze, soweit sie ohne zusätzliche Pakete aus Linux-
  Systeminformationen ermittelbar sind,
- maximal eine begrenzte Zahl von Hosts parallel,
- nur die bekannten Ollama-/WebUI-Ports,
- kurze Verbindungs- und Gesamt-Timeouts.

Gefundene URLs, Antwortstatus und technische Fehler werden nur im Debug-Log
protokolliert; keine Zugangsdaten oder Inhalte.

#### Konfigurationsspeicher

Neue Onboarding-Daten werden atomar und mit Dateirechten `0600` gespeichert:

```text
$XDG_STATE_HOME/llmtop/config.json
```

Die bestehende `.env` und Umgebungsvariablen bleiben kompatibel und haben
Vorrang. API-Keys werden nicht in Logs, TUI, Fehlermeldungen oder History
übernommen.

Das Konfigurationsmodell soll mindestens enthalten:

- gewählte Ollama-URL,
- gewählte Open-WebUI-URL,
- Open-WebUI-API-Key,
- Collector-URL und Tokenreferenz,
- erkannte Installationsart (`local`, `docker`, `lan`),
- Zeitstempel und optional zuletzt erfolgreiche Prüfung.

### 2. Erststart-Onboarding

Das Onboarding wird automatisch gestartet, wenn:

- `llmtop` interaktiv im TUI-Modus läuft,
- noch keine gültige Onboarding-Konfiguration existiert,
- kein vollständiger expliziter Umgebungs-/`.env`-Setup vorliegt.

Nicht-interaktive Modi starten niemals den Dialog. Sie verwenden weiterhin
Defaults und melden fehlende Verbindungen nur als Status.

#### Dialogablauf

1. Begrüßung und kurzer Hinweis zu Datenschutz und LAN-Erkennung.
2. Automatische Suche mit sichtbarem Fortschritt.
3. Kandidaten gruppiert nach:
   - lokal installiert,
   - Docker/Container,
   - LAN.
4. Beste Ollama-Instanz vorauswählen; Auswahl, URL-Eingabe oder Überspringen
   anbieten.
5. Open-WebUI-Instanz auswählen oder URL manuell eingeben.
6. Admin-API-Key verdeckt abfragen; bei 401/403 erneut fragen oder WebUI
   überspringen.
7. Collector automatisch lokal starten oder vorhandene Remote-Konfiguration
   übernehmen.
8. Open-WebUI-Adapter über die Admin-API installieren/aktualisieren und global
   aktivieren.
9. Pi-Adapter und private Laufzeitdaten aktualisieren.
10. Verbindungstest für alle gewählten Komponenten durchführen und Ergebnis
    zusammenfassen.
11. Konfiguration speichern und TUI starten.

Ein erneuter Start zeigt bei vorhandener Konfiguration nur eine kurze Status-
prüfung. Eine spätere Neukonfiguration erfolgt über `--setup`.

Vorgesehene Optionen:

```text
--setup          Onboarding erneut starten oder Konfiguration ändern
--discover       erkannte Kandidaten anzeigen, ohne Konfiguration zu ändern
--reset-setup    Onboarding-Konfiguration nach Bestätigung entfernen
```

### 3. Adapter, Collector und Tests integrieren

`llmtop_metrics.py` wird so erweitert, dass:

- lokale Open-WebUI-Installationen ohne Docker-Gateway funktionieren,
- Docker-Gateway nur für Container-Ziele verwendet wird,
- ein explizit konfigurierter Remote-Collector Vorrang vor einem lokalen
  Collector hat,
- Adapterinstallation und Collector-Verbindung getrennte, fehlertolerante
  Schritte bleiben,
- ein fehlender Ollama-Server Open-WebUI-/Pi-Metriken nicht blockiert,
- ein fehlendes Open WebUI Ollama-Sensorik und TUI nicht blockiert.

`llmtop.py` übernimmt den Erststart-Dialog nur im interaktiven Modus.
`README.md`, `status.md`, `version.md` und die Versionsnummer werden synchron
aktualisiert.

## Sicherheits- und Bedienregeln

- Keine automatische Übernahme oder Anzeige von API-Keys aus fremden Quellen.
- LAN-Erkennung standardmäßig nur privat und begrenzt.
- Keine Prompts, Antworten oder WebUI-Inhalte speichern.
- Vor jeder Adapterinstallation Ziel-URL und erkannte Instanz anzeigen.
- Schreibvorgänge atomar, Konfigurationsdatei `0600`, Verzeichnis `0700`.
- Discovery-Fehler dürfen den TUI-Start nicht verhindern.
- Bestehende explizite Konfiguration nie ungefragt überschreiben.

## Validierung

Gezielte Tests im Scratch-Verzeichnis:

- Discovery mit lokalen Mock-HTTP-Servern für Ollama und Open WebUI.
- Ollama vorhanden, Open WebUI fehlend.
- Open WebUI vorhanden, Ollama fehlend.
- beide lokal vorhanden.
- Docker-Gateway vorhanden und nicht vorhanden.
- LAN-Kandidat erreichbar, nicht erreichbar und mit HTTP-401.
- Erststart im TTY, Wiederholungsstart und nicht-interaktiver `--once`-Start.
- falscher API-Key und übersprungene WebUI-Konfiguration.
- `python3 -m py_compile ...`
- `--version`, `--once` und `--once --no-nvidia`.
- bestehende Open-WebUI-Adapter- und Collector-Tests.

## Ergebnisdefinition

Die Umsetzung ist abgeschlossen, wenn ein neuer interaktiver Start ohne
Ollama-/WebUI-Konfiguration automatisch Kandidaten findet, fehlende sichere
Angaben abfragt, den passenden Adapter installiert, den Pi-Adapter aktiviert
und danach auch bei fehlender Einzelkomponente ohne Absturz weiterläuft.
