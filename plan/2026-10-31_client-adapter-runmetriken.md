# Plan: Quellenadapter für Ollama-Runmetriken

## Ziel

`otop` soll Metriken laufender und abgeschlossener Ollama-Requests erfassen,
in der TUI darstellen und dauerhaft historisieren. Jeder Eintrag muss seine
Quelle ausweisen:

- `pi` – Pi Coding Agent,
- `open-webui` – Open WebUI,
- `ollama-cli` – instrumentierter Terminal-Aufruf.

Die Modellanfrage läuft weiterhin direkt vom jeweiligen Client zu Ollama. Der
neue Mechanismus überträgt ausschließlich Metadaten an `otop`; er ist kein
Reverse Proxy und verändert keine Request- oder Antwortdaten.

## Verifizierte technische Grundlage

- Ollama 0.40.6 liefert Nutzungsmetriken ausschließlich im finalen
  `done: true`-Objekt von `/api/chat` beziehungsweise `/api/generate`:
  `prompt_eval_count`, `eval_count`, `load_duration`,
  `prompt_eval_duration`, `eval_duration` und `total_duration`.
  Dauerwerte sind Nanosekunden.
- `/api/ps` beschreibt nur geladene Modelle. Ein Test während eines langen
  Runs zeigte keine aktiven Requests, Tokenzähler oder Zeitwerte.
- Es gibt auf diesem Server weder `/metrics` noch `/api/metrics`,
  `/api/running` oder `/api/requests`.
- Open WebUI stellt dokumentierte Filter-Hooks vor dem Request sowie für
  Stream- und Abschlussverarbeitung bereit. Pi stellt Erweiterungs- und
  Provider-Hooks bereit. Beide sind geeignete, clientseitige
  Instrumentierungspunkte; die konkreten Nutzungsfelder ihrer installierten
  Versionen müssen vor dem jeweiligen Adapter mit einem Testlauf bestätigt
  werden.
- Das native Programm `ollama run` hat keine dokumentierte Hook- oder
  Metrik-Ausgabe-Schnittstelle. Beliebige bestehende `ollama run`-Prozesse
  bleiben daher ohne Proxy, Serveränderung oder Wrapper nicht beobachtbar.

## Architekturentscheidung

### Lokaler Metrik-Kollektor

`otop.py` erhält einen optionalen Modus `--collector`, der ausschließlich auf
`127.0.0.1` lauscht. Er nimmt `POST /v1/runs` mit einem kleinen JSON-Ereignis
entgegen, validiert es und schreibt die vorhandenen Dateien atomar:

- `run.jsonl`: die neuesten aktiven Runs, nicht nur ein einzelner Run;
- `runs.jsonl`: genau ein finaler, deduplizierter Eintrag je `run_id`;
- `history.jsonl`: bleibt ausschließlich System-Snapshot-Historie.

Der Kollektor leitet niemals HTTP nach Ollama weiter und kennt weder Prompt noch
Antwortinhalt. Er kann deshalb unabhängig vom gewählten Client laufen.

Ein lokaler HTTP-Eingang ist gegenüber gemeinsam beschreibbaren Dateien die
robustere Basis: Pi läuft am Host, Open WebUI häufig in einem Container, und
beide müssen keine Host-Verzeichnisse mounten. Die Implementierung verwendet
nur `http.server`, `json` und weitere Python-Standardbibliothek.

### Zugangsdaten

Ein Bearer-Token schützt den Collector gegen fremde lokale Prozesse und gegen
einen versehentlich erreichbaren Container-Port:

```dotenv
# .env – nur lokal, Modus 0600, niemals committen
OTOP_COLLECTOR_TOKEN=<zufälliger-langer-wert>
OTOP_COLLECTOR_URL=http://127.0.0.1:11435
```

- `.env` wird beim Start von `otop` mit einem kleinen eigenen Parser gelesen;
  keine neue Abhängigkeit.
- `.env` und lokale Run-Dateien werden in `.gitignore` aufgenommen.
- `.env.example` enthält nur Namen und Platzhalter, nie einen Token.
- Der Kollektor startet nicht ohne gesetzten Token, außer ein expliziter
  Entwicklungs-Schalter ist gesetzt.
- Bei Docker-Open-WebUI wird die URL erst nach Prüfung der lokalen
  Docker-Netzwerkanbindung festgelegt. `127.0.0.1` im Container ist nicht der
  Host. Es wird kein Port nach außen veröffentlicht; möglich sind
  `host.docker.internal` mit Host-Gateway oder eine bewusst eng begrenzte
  Docker-Bridge-Adresse. Diese Entscheidung wird vor der Installation
  verifiziert.

## Einheitliches Ereignisformat

Alle Adapter senden dasselbe datensparsame Format. Eine Nutzerfrage, Chat-ID,
Antwort oder ein API-Key wird nicht gespeichert.

```json
{
  "schema": 2,
  "event": "started|updated|completed|error|cancelled",
  "run_id": "uuid-v4",
  "source": "pi|open-webui|ollama-cli",
  "source_run_id": "optionale-client-id",
  "model": "qwen3.5:4b",
  "started_at": "2026-10-31T15:00:00Z",
  "updated_at": "2026-10-31T15:00:03Z",
  "finished_at": "2026-10-31T15:00:12Z",
  "prompt_tokens": 42,
  "output_tokens": 125,
  "load_duration_s": 0.3,
  "prompt_eval_duration_s": 0.4,
  "eval_duration_s": 8.1,
  "total_duration_s": 9.0,
  "status_detail": "length",
  "error": null
}
```

Regeln:

1. `started` ist beim Beginn verpflichtend und enthält Quelle, `run_id`, Modell
   und Zeit.
2. `updated` ist optional. Ohne echte serverseitige Tokenwerte darf es nur
   Status und Zeit, niemals geschätzte Token enthalten.
3. `completed`, `error` und `cancelled` sind final. Sie werden per
   `(source, run_id)` dedupliziert und ersetzen einen vorherigen finalen
   Zustand derselben ID.
4. Ein fehlender oder unbekannter Zähler bleibt `null` und wird als `n/a`
   dargestellt.
5. Der Collector rechnet Nanosekunden nur dann um, wenn ein Adapter explizit
   rohe Ollama-Felder sendet; das persistierte Format verwendet Sekunden.
6. Gleichzeitige Requests sind erlaubt. Ein Run wird nach konfigurierbarer
   Frist ohne Update als `stale` markiert, aber nicht als erfolgreich
   abgeschlossen historisiert.
7. Der Collector antwortet nur mit HTTP 202, 400, 401, 413 oder 429 und
   protokolliert keine geheimen Header oder Bodies.

## Darstellung in `otop`

### Aktuelle Runs

Der einzelne Block „Aktueller Run“ wird zu „Aktuelle Runs“. Er zeigt die drei
zuletzt aktualisierten aktiven Runs, getrennt nach Quelle:

```text
Aktuelle Runs (2)
  Pi          qwen3.5:4b       läuft     Token n/a · vor 0.3 s
  Open WebUI  qwen3.5:4b       läuft     Token n/a · vor 1.1 s
```

Nach finalen Metriken sind Prompt, Ausgabe, Gesamt, Ausgabe-Token/s und Dauer
sichtbar. Für enge Terminals wird zuerst auf eine einzeilige Kurzform pro Run
gekürzt; niemals werden Quelle oder Status weggelassen.

### Run-History

Die Run-History zeigt Quelle als feste Spalte und speichert den gleichen Wert:

```text
15:03  Pi          qwen3.5:4b  fertig  1.4k Tok  41.2 Tok/s  34.1 s
15:00  Open WebUI  qwen3.5:4b  Fehler  n/a       n/a         1.2 s
```

Filter- oder Sortierbedienung wird **nicht** Teil des ersten Inkrements. Die
Liste bleibt neuester zuerst und begrenzt sich auf Terminalhöhe; `--once`
gibt die letzten fünf Einträge aus. System-Snapshot-Status bleibt getrennt
und klar beschriftet.

## Quellenadapter

### Pi

**Ziel:** Ein lokales Pi-Extension-Modul meldet jeden Provider-Request, der
Ollama verwendet.

- Vor dem Request erzeugt die Extension eine UUID und sendet `started`.
- Sie lauscht auf den Provider-Stream beziehungsweise den finalen
  Response-Hook und überträgt, falls verfügbar, die normalisierten
  Nutzungsdaten.
- Für Pi-Tool-Loops ist jeder Provider-Request ein eigener Run; optional wird
  später eine Sitzungs-/Turn-ID nur als nicht sensibler Gruppenschlüssel
  ergänzt.
- Der Adapter sendet mit kurzem Timeout. Ein Collector-Ausfall darf Pi weder
  blockieren noch den Modell-Request beeinflussen.
- Vor Implementierung: installierte Pi-Version, Erweiterungs-API und reale
  finale Nutzungsevents mit einem Test-Prompt ermitteln. Falls Pi die
  Ollama-Finalfelder nicht durchreicht, ist ein Pi-Provider-Adapter mit
  Stream-Beobachtung nötig; keine unbestätigten privaten Hooks verwenden.

### Open WebUI

**Ziel:** Eine globale, immer aktive Filter Function meldet jeden Modellaufruf,
der an lokales Ollama geht.

- `request()` meldet einen Start pro Provider-Aufruf, nicht nur pro
  Benutzerturn (entscheidend bei Tool-Loops).
- `stream()` und/oder `outlet()` sucht ausschließlich nach finalen
  Nutzungsfeldern und meldet dann `completed`.
- Der Filter wird für andere Provider zum No-op und speichert weder Inhalte
  noch Benutzerinformationen.
- Die Collector-URL und der Token liegen als Open-WebUI-Filter-Valves oder
  Container-Umgebungsvariablen vor, nicht im Python-Quelltext.
- Vor Implementierung: Version, Container-Netzwerk, tatsächliche Shape der
  Stream-/Outlet-Daten und Verhalten bei Abbruch testen. Falls Open WebUI die
  finalen Ollama-Felder vor dem Filter verwirft, kann dieser Adapter nur
  Start-/Fehlerzustände liefern; exakte Abschlussmetriken erfordern dann eine
  Open-WebUI-Erweiterung näher am Provider oder bleiben offen.

### Ollama-Terminal

**Ziel:** Ein expliziter `otop ask`- beziehungsweise `otop generate`-Modus
führt einfache direkte Requests aus und ist mit Quelle `ollama-cli` markiert.

- Er nutzt `/api/chat` oder `/api/generate`, gibt NDJSON unverändert auf stdout
  aus und meldet Start sowie das finale `done`-Objekt an den Collector.
- Er ist für Einmalprompts und Skripte geeignet; vorhandene `ollama run`
  Interaktivität wird nicht nachgebaut.
- Ein Shell-Alias kann später freiwillig auf diesen Modus zeigen. Ohne Alias
  oder Wrapper bleiben fremde native `ollama run`-Aufrufe technisch unsichtbar.
- Der vorhandene `--chat`/`--generate`-Code wird dabei nicht parallel
  fortgeführt, sondern nach erfolgreicher Migration als kompatible Kurzform
  auf den neuen Eventweg umgestellt.

## Umsetzungsphasen

### Phase 0 – Vorprüfung und Sicherheitsbasis

1. Bestehendes Run-Schema, TUI-Renderer und aktuelle JSONL-Dateien sichern;
   keine bestehenden System-Snapshots migrieren oder löschen.
2. `.gitignore` um `.env` und lokale State-Dateien ergänzen; `.env.example`
   ohne Geheimnisse anlegen.
3. Collector-Token erzeugen lassen oder vom Benutzer übernehmen; Wert nie in
   Ausgaben, Tests oder Dokumentation ausgeben.
4. Pi- und Open-WebUI-Versionen sowie Erreichbarkeit vom jeweiligen Prozess
   zum geplanten Collector testen.

**Entscheidungspunkt:** Kann Open WebUI den loopback-Collector nicht erreichen,
wird ausschließlich die Collector-Adresse in der lokalen Docker-Bridge
freigegeben; kein öffentlicher Bind und kein Reverse Proxy.

### Phase 1 – Erste sinnvolle Grundfunktion: Collector und generischer Run

1. Versioniertes Schema-2-Parsing und Eventzustandsmaschine in `otop.py`
   ergänzen.
2. `--collector` mit Token-Prüfung, restriktiver Requestgröße, kurzem
   Logging und sauberem Beenden implementieren.
3. Aktive Runs als Liste und finalisierte Run-History mit Quellenlabel
   implementieren; Schema-1-Einträge weiter lesbar halten, Quelle dort als
   `legacy` markieren.
4. Einen rein lokalen Testsender `otop emit --file event.json` ergänzen. Er
   ist Testwerkzeug, keine neue Clientintegration.
5. Tests: Authentifizierung, ungültiges Schema, parallele Starts, doppelte
   Abschlussereignisse, `stale`, JSONL-Recovery, enge Terminalhöhe und
   `--once`.

**Abnahme Phase 1:** Ein manueller `started`- und `completed`-Event erscheint
sofort mit Quelle in TUI und genau einmal in der History, auch über Neustarts
des Monitors hinweg.

### Phase 2 – Pi als erster echter Adapter

1. Extension anhand der installierten, dokumentierten Pi-API erstellen.
2. Start, Erfolg, Modell, Fehler und soweit vorhanden finale Token- und
   Dauerwerte an den Collector senden.
3. Mit einem kurzen und einem Tool-Loop-Prompt prüfen: keine Blockade bei
   Collector-Ausfall, korrekte Anzahl von Provider-Runs, korrekte Quelle und
   Deduplizierung.
4. Die Extension lokal dokumentieren und nur für Ollama-Modelle aktivieren.

**Abnahme Phase 2:** Ein normaler Pi-Ollama-Request erscheint ohne Änderung
am Prompt als aktiver Run und nach Abschluss mit Quelle `Pi` in der History.

### Phase 3 – Open-WebUI-Pilot

1. Filter als einzelne, prüfbare Python-Datei erstellen und zunächst nur für
   ein Testmodell aktivieren.
2. Container-zu-Collector-Verbindung mit einem Testevent verifizieren.
3. Realen Chat, Streaming, Abbruch und Tool-Loop testen; die reale
   Abschlussdatenform protokolliert nur Feldnamen und Typen, niemals Inhalte.
4. Erst bei korrekt erhaltenen Abschlussmetriken global aktivieren.

**Abnahme Phase 3:** Ein Open-WebUI-Ollama-Request ist als `Open WebUI`
markiert, und er kann nicht mit gleichzeitigem Pi-Run kollidieren.

### Phase 4 – instrumentiertes Ollama-Terminal und Konsolidierung

1. `otop ask`/`generate` auf Collector migrieren und Quelle `ollama-cli`
   sicherstellen.
2. Skript-, Fehler- und Abbruchverhalten testen.
3. README, `status.md`, `version.md` und Bedienhilfe aktualisieren.
4. Erst nach allen Quellen eine Quellenfilterung oder Langzeit-Auswertung
   bewerten; sie gehört nicht in diese Umsetzung.

## Testmatrix

| Fall | Erwartung |
|---|---|
| ungültiger/fehlender Token | Collector: 401, keine Dateiänderung |
| ungültiges Event | 400, TUI bleibt stabil |
| Start ohne Abschluss | aktiver Run, später `stale`, kein History-Erfolg |
| doppeltes `completed` | genau ein History-Eintrag |
| paralleler Pi- und WebUI-Run | beide aktiv mit eigener Quelle |
| Ollama-finaler Chunk | Token und Nanosekunden korrekt übernommen/umgerechnet |
| Collector nicht erreichbar | Clientantwort bleibt funktional, nur Metrik fehlt |
| Neustart von `otop` | finale History bleibt lesbar |
| Terminal mit geringer Höhe | jüngster History-Eintrag und Quelle bleiben sichtbar |

## Nichtziele der ersten Umsetzung

- Kein Mitschneiden von Prompts, Antworten oder HTTP-Streams.
- Kein Reverse Proxy und kein Eingriff in Ollama selbst.
- Keine Erkennung beliebiger, nicht instrumentierter Clients.
- Kein Nachbau des vollständigen interaktiven `ollama run`-Clients.
- Keine externe Datenbank, keine neue Python-Abhängigkeit und keine
  Veröffentlichung des Collector-Ports im Netzwerk.

## Risiken und offene Entscheidungen

1. **Open WebUI:** Es muss getestet werden, ob Filter den finalen
   Ollama-Nutzungsblock tatsächlich erreichen. Ohne ihn ist nur
   Start-/Enderkennung möglich.
2. **Pi:** Die Erweiterung wird gegen die lokal installierte API umgesetzt,
   nicht gegen angenommene Hook-Namen aus Webquellen.
3. **Docker-Netz:** Die genaue, private Host-Erreichbarkeit für Open WebUI
   ist installationsabhängig und wird vor Änderungen geprüft.
4. **API-Key:** Für lokale Pi- und Terminaladapter genügt der Collector-Token.
   Ein Open-WebUI-Admin-API-Key wird nur benötigt, falls die Filterverwaltung
   automatisiert werden soll; die erste Installation kann manuell über die
   Admin-Oberfläche erfolgen.
