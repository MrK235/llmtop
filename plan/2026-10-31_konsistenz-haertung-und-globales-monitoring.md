# Plan: Konsistenz, Härtung und Grundlagen für globales Monitoring

## Ziel

`otop` soll als lokaler, verlässlicher Sensor-Endpunkt stabil bleiben und später
Zeitreihen sowie mehrere LLM-Quellen (Ollama, Open WebUI, Pi, Strata) in einem
globalen Monitoring zusammenführen. Dieser Plan trennt die bereits umgesetzte
Soforthärtung von den nächsten, komplexeren Schritten.

## Review-Befund

### Behoben in 1.3.5

- **Versionsinkonsistenz:** `VERSION` war 1.3.4, `status.md` dokumentierte noch
  den Testwert 1.3.3. Code, README, Status und Changelog sind jetzt auf 1.3.5.
- **Host-Normalisierung:** Werte wie `:11434` oder `0.0.0.0:11434` aus
  `OLLAMA_HOST` wurden nicht zuverlässig als URL behandelt. `--host` und die
  Umgebungsvariable werden jetzt mit `http://` und ohne abschließenden Slash
  normalisiert.
- **Ungeprüfte API-Struktur:** Nicht-Objekte als JSON und eine nicht-listenartige
  `/api/ps.models`-Antwort konnten später zu irreführender Anzeige oder Fehlern
  führen. Solche Antworten werden jetzt als Ollama-Fehler dargestellt.
- **NVIDIA-CSV:** GPU-Namen mit Kommas konnten durch `split(",")` falsch zerlegt
  werden. Der Parser verwendet jetzt den Standard-CSV-Parser.
- **Unplausible Werte:** CPU-, GPU- und VRAM-Prozente sowie Modell-Offload werden
  begrenzt. Ein fehlerhaftes Verhältnis kann dadurch keine negativen CPU-Anteile
  oder Balken außerhalb des zulässigen Bereichs erzeugen.

### Offen / bekannte Risiken

- Die TUI fragt Netzwerk, `nvidia-smi` und sysfs synchron ab; ein Timeout kann
  die Bedienung kurz blockieren.
- Viele Modelle können den unteren TUI-Bereich beziehungsweise die Fußzeile
  überlaufen; es gibt keinen Scroll- oder Priorisierungsmodus.
- History ist nur ein Platzhalter. Es gibt keine persistente Zeitreihe, keine
  Retention und keine Export-Schnittstelle.
- GPU-Werte sind hostweit und nicht sicher einem Modell oder einer Quelle
  zuordenbar.
- Es existieren noch keine automatisierten Regressionstests; `git` ist im
  Projektverzeichnis derzeit nicht initialisiert, obwohl README eine spätere
  Versionierung beschreibt.
- Die Single-File-Struktur ist für lokale Nutzung passend, erschwert aber die
  Trennung von Sensoren, Adaptern, Speicherung und Darstellung.

## Bereits umgesetzte Härtung

1. Kleine Eingangs- und Antwortvalidierung in `otop.py`.
2. Plausibilisierung der Sensor- und Offload-Prozentwerte.
3. Dokumentationsabgleich auf Version 1.3.5.
4. Syntax-, Versions- und Live-`--once`-Prüfung mit Ollama sowie sysfs-Fallback.

## Nächste Schritte in sicherer Reihenfolge

### 1. Vertrauenswürdige lokale Basis

- Reine Funktionen für Host-Normalisierung, CPU-Prozent, Offload und Formatierung
  mit Standardbibliotheks-Tests abdecken.
- Mock-Tests für Ollama-Timeout, HTTP-Fehler, ungültiges JSON, fehlerhafte
  Modelllisten, NVIDIA-CSV, fehlende Sensoren und Terminalgrößen ergänzen.
- TUI-Datenabruf von Rendering und Tastatur entkoppeln, ohne neue Abhängigkeit:
  letzter gültiger Snapshot, Zeitstempel und sichtbarer Fehlerstatus.
- Bei vielen Modellen eine begrenzte Ansicht mit Zähler („weitere Modelle …“)
  oder einen einfachen Scrollmodus einführen.

### 2. History als lokales, append-only Ereignismodell

- Ein internes Snapshot-Schema definieren: `timestamp`, `source`, `host`,
  `ollama_version`, `models`, `cpu`, `ram`, `gpus`, `errors`.
- Zeitstempel ausschließlich in UTC als ISO-8601 speichern; Messwert und
  Erfassungszeit getrennt von Anzeigeformaten halten.
- Zunächst JSONL im konfigurierbaren Benutzerdatenverzeichnis verwenden,
  standardmäßig mit begrenzter Größe/Retention. Atomisches Schreiben und
  beschädigte letzte Zeilen tolerieren.
- Keine Prompts, Inhalte oder Zugangsdaten speichern; Modellnamen und technische
  Metriken nur soweit erforderlich. Export später als JSONL/CSV.
- History-Anzeige zunächst aus dem Ringpuffer im Prozess speisen; Persistenz und
  Anzeige getrennt testen.

### 3. Quellenadapter für globales Monitoring

- Gemeinsames Adapter-Interface definieren: `collect() -> SnapshotPart` mit
  `source_id`, `kind`, `timestamp`, `status`, `metrics`, `errors`.
- Bestehenden Ollama-Adapter als Referenz verwenden.
- Open WebUI zunächst als optionalen HTTP-Adapter behandeln: Erreichbarkeit,
  Version/Health und – nur nach dokumentierter API-Prüfung – Modell-/Request-
  Metriken. Keine Annahmen über private oder versionsabhängige Endpunkte.
- Pi und Strata als weitere optionale Quellen mit eigener Authentifizierung,
  Timeouts und Capability-Liste integrieren. Ein Ausfall einer Quelle darf
  andere Quellen und die lokale TUI nicht ausblenden.
- Quellen-IDs, Host, Modell-ID und Request-ID normalisieren, damit ein späterer
  globaler Aggregator keine Daten nur anhand von Anzeigenamen zusammenführt.

### 4. Globaler Aggregator und Sicherheit

- Ein lokaler Collector sammelt Quellen, versieht Daten mit `source_id` und
  schreibt ein einheitliches Ereignisformat. Erst danach eine Remote-Ausleitung
  planen.
- Queue mit begrenzter Größe, Retry-Backoff und sichtbarem „stale“-Status statt
  unendlicher Wiederholungen.
- Authentifizierung nur über Umgebungsvariablen oder sichere lokale Konfigura-
  tion; Tokens niemals loggen oder in History schreiben.
- Netzwerkziele explizit konfigurieren und standardmäßig lokal/deaktiviert
  halten. TLS-Zertifikatsprüfung nicht abschalten.
- Korrelation von Prompts, Antworten und Nutzerdaten standardmäßig deaktiviert;
  Monitoring bleibt metrisch und datensparsam.

## Abnahmekriterien

- `python3 -m py_compile otop.py`, `--version`, `--once` und `--once --no-nvidia`
  funktionieren.
- Ungültige API-Daten und Sensorwerte führen zu einer verständlichen Anzeige,
  nicht zu einem Traceback.
- Ein einzelner Quellenausfall lässt die übrigen Quellen sichtbar.
- History kann begrenzt, UTC-sortiert und ohne Geheimnisse gespeichert werden.
- Jede neue Quelle besitzt eigene Mock-Tests sowie eine dokumentierte
  Capability-/Fehlerstrategie.
