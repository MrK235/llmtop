# Plan: Open-WebUI-Adapter für otop-Runmetriken installieren

## Ziel

Open WebUI soll jeden ausgehenden Ollama-Provider-Aufruf als eigenen Schema-2-Run an den vorhandenen `otop`-Collector melden. Der Adapter darf weder Prompts noch Antworten speichern oder übertragen und darf einen Chat bei Collector-Ausfall nicht beeinträchtigen.

## Verifizierter Ist-Stand

- Open WebUI läuft als Docker-Container `open-webui` mit Version `0.12.3` und Image-Revision `91ea4e3421d1d8069f13d4a463fcb5986d94ea60`.
- Der Container hängt im Docker-Netz `ai-net`, Adresse `172.18.0.4`, Gateway `172.18.0.1`.
- Die Compose-Datei liegt außerhalb des Projektordners unter `/home/kajetan/docker/ai/compose.yml`. Änderungen dort benötigen eine ausdrückliche Freigabe.
- Open WebUI erreicht Ollama intern über `http://ollama:11434`.
- Die installierte Version unterstützt dokumentiert `request`, `stream` und `outlet` für Filter Functions:
  - `request` läuft einmal pro tatsächlichem Provider-Aufruf, auch in Tool-Loops.
  - `stream` erhält geparste Stream-Ereignisse.
  - `outlet` erhält die finale Nachrichtenliste einschließlich vorhandener `usage`- und `finish_reason`-Felder.
- Die Funktionsdatenbank ist aktuell leer; es ist noch kein Filter installiert.
- Der `otop`-Collector lauscht standardmäßig nur auf `127.0.0.1:11435`. Diese Adresse ist aus dem Container nicht erreichbar.
- Der Collector unterstützt derzeit einen Bind-Parameter intern, zeigt ihn aber nicht als reguläre dokumentierte CLI-Option. Für Open WebUI muss er gezielt auf der privaten Docker-Gateway-Adresse `172.18.0.1` lauschen. Kein Bind auf `0.0.0.0` und keine Portveröffentlichung.

## Architekturentscheidung

### Adapterform

Eine einzelne Open-WebUI-Filter-Function wird im Projekt als `open_webui/otop_run_metrics.py` gepflegt und anschließend über die Admin-Oberfläche importiert. Eine automatische Installation über die Admin-API wird nicht vorausgesetzt, weil dafür ein Admin-Token erforderlich wäre.

Der Filter ist:

- aktiv und global,
- nicht benutzerseitig abschaltbar (`self.toggle` bleibt ungesetzt),
- für Nicht-Ollama-Modelle ein No-op,
- ausschließlich Metadaten-sammelnd,
- fehlertolerant: Netzwerkfehler werden intern abgefangen.

### Run-Zuordnung

`request()` erzeugt für jeden Provider-Aufruf eine UUID und meldet `started`. Da Stream- und Outlet-Hooks keinen garantierten, vom Filter frei gesetzten Request-Kontext erhalten, wird die Zuordnung innerhalb der gecachten Filterinstanz verwaltet:

- Schlüssel: bevorzugt stabile Metadaten aus `__metadata__` wie `chat_id`, `message_id` und Modell; falls nicht vorhanden ein enger Ersatzschlüssel aus Modell und Laufreihenfolge.
- Pro Schlüssel wird eine FIFO-Liste aktiver Run-IDs geführt, damit Tool-Loops mehrere Provider-Aufrufe nicht überschreiben.
- Ein finaler Ollama-Chunk in `stream()` schließt den ältesten passenden aktiven Run ab.
- `outlet()` dient nur als Fallback für Abschluss, Fehler oder fehlende Stream-Nutzungsdaten und darf einen bereits finalisierten Run nicht doppelt anlegen.
- Verwaiste Zuordnungen werden zeitlich begrenzt entfernt; es werden keine Chat-Inhalte im Speicher gehalten.

Vor endgültiger Aktivierung wird mit einem Pilotlauf geprüft, welche Metadaten in Version 0.12.3 in `request`, `stream` und `outlet` tatsächlich stabil vorhanden sind.

### Metrikextraktion

Der Filter sucht rekursiv nur nach bekannten Ollama-Feldern:

- `done`, `done_reason`
- `prompt_eval_count`, `eval_count`
- `load_duration`, `prompt_eval_duration`, `eval_duration`, `total_duration`
- alternativ normalisierte `usage`-Felder, falls Open WebUI die Ollama-Rohfelder bereits umgebaut hat.

Es werden weder unbekannte Werte noch Textfelder protokolliert. Dauerwerte aus Ollama bleiben als Nanosekundenfelder im Ereignis; der Collector übernimmt die bestehende Normalisierung nach Sekunden.

## Umsetzung

### 1. Collector privat für den Container erreichbar machen

1. `otop.py` erhält dokumentierte Collector-Optionen für Bind-Adresse und Port oder entsprechende Umgebungsvariablen.
2. Zulässig ist für diese Installation ausschließlich `172.18.0.1:11435`; der Default bleibt `127.0.0.1:11435`.
3. Den Collector mit vorhandenem Token starten und aus dem Container einen anonymen Test-POST senden:
   - ohne Token: HTTP 401,
   - mit Token und gültigem Testevent: HTTP 202.
4. Keine Firewall-, Docker-Port- oder Compose-Änderung vornehmen, solange die Gateway-Adresse direkt funktioniert.

### 2. Filter implementieren und lokal testen

1. `open_webui/otop_run_metrics.py` mit Frontmatter, `Valves` und den Hooks `request`, `stream`, `outlet` anlegen.
2. Valves:
   - `collector_url`, Default `http://172.18.0.1:11435`,
   - `collector_token`, leerer Secret-Wert,
   - `ollama_base_url` oder Modell-/Provider-Erkennungswert, passend zur installierten Instanz,
   - kurzer Timeout, maximal etwa 0,5 Sekunden.
3. HTTP-Versand nur mit Python-Standardbibliothek oder bereits in Open WebUI vorhandener Bibliothek; keine neue Container-Abhängigkeit.
4. Unit-nahe lokale Tests mit künstlichen `request`-, Stream- und Outlet-Objekten:
   - Start ohne Inhalte,
   - finaler Ollama-Chunk,
   - normalisierte Usage,
   - doppelte Finalisierung,
   - parallele Runs,
   - Collector nicht erreichbar.

### 3. Pilot installieren und reale Datenform verifizieren

1. Filter über **Admin Panel → Functions** importieren.
2. Token ausschließlich in den Filter-Valves setzen; nicht in Quelltext, Plan oder Shell-Ausgabe übernehmen.
3. Zunächst aktiv, aber nicht global schalten und nur einem Testmodell zuordnen.
4. Einen kurzen normalen Chat ausführen und prüfen:
   - genau ein aktiver `Open WebUI`-Run,
   - nach Abschluss genau ein History-Eintrag,
   - Modell, Token und Dauer plausibel,
   - Chatantwort unverändert.
5. Einen Tool-Loop und einen abgebrochenen Stream prüfen. Falls die Hook-Daten keine exakten Finalmetriken enthalten, bleibt der Pilot bei Start-/Statusdaten; es werden keine Token geschätzt.
6. Erst nach erfolgreichem Pilot den Filter global aktivieren.

## Testmatrix

| Fall | Erwartung |
|---|---|
| Container → Collector ohne Token | 401, keine Dateiänderung |
| Container → Collector mit gültigem Event | 202, Quelle `open-webui` |
| normaler Chat | ein Start, ein Abschluss |
| Tool-Loop | ein Run je Provider-Aufruf |
| parallele Chats | getrennte Run-IDs, keine Kollision |
| finaler Ollama-Chunk | exakte Token- und Dauerwerte |
| finaler Chunk ohne Usage | Abschluss mit `n/a`, keine Schätzung |
| Abbruch | `cancelled` oder später `stale`, niemals `completed` geraten |
| Collector offline | Chat funktioniert unverändert |
| Nicht-Ollama-Modell | kein Event |
| doppelter Outlet-/Stream-Abschluss | ein History-Eintrag je Run |

## Sicherheitsregeln

- Kein Prompt, keine Antwort, kein Benutzername, keine E-Mail und kein API-Key im Ereignis oder Log.
- Collector nur auf Loopback oder der privaten Docker-Gateway-Adresse binden.
- Token nur in `.env` und Open-WebUI-Valves speichern.
- Keine Änderung oder Löschung des Open-WebUI-Datenvolumes.
- Keine direkte SQLite-Manipulation zur Installation; die Admin-Oberfläche/API übernimmt Validierung und Cache-Aktualisierung.
- Keine Änderung an `/home/kajetan/docker/ai/compose.yml` ohne separate Freigabe.

## Abnahme

Die Installation ist abgeschlossen, wenn ein realer Open-WebUI-Ollama-Chat ohne Änderung der Antwort als aktiver Run mit Quelle `Open WebUI` erscheint und nach Abschluss genau einmal mit den tatsächlich verfügbaren Token- und Dauerwerten in `runs.jsonl` steht. Bei ausgeschaltetem Collector bleibt derselbe Chat funktionsfähig.

## Offene Entscheidung vor Implementierung

Für die reale Installation ist eine Benutzeraktion erforderlich: Import und Aktivierung in der Open-WebUI-Adminoberfläche oder Bereitstellung eines kurzlebigen Admin-API-Tokens. Der Adaptercode und die Container-Erreichbarkeit können vorher vollständig vorbereitet und getestet werden.
