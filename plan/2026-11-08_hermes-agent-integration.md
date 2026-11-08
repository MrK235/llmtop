# Plan: Hermes Agent vollständig in llmtop integrieren

## Ziel

`llmtop` erfasst Hermes-Agent-Läufe genauso datensparsam und fehlertolerant wie
Pi- und Open-WebUI-Läufe. Sichtbar werden:

- Hauptläufe je Hermes-Nutzerturn aus CLI, TUI, Gateway, Cron, ACP und Webhook,
- delegierte Subagent-Läufe, mit Zuordnung zum Elternlauf,
- Hilfsmodellaufrufe (z. B. Kompaktierung, Titel, MoA, Vision) als eigene,
  klar markierte Läufe,
- Modell, Provider, Plattform, Laufstatus, echte Token, Kontextlimit/-stand,
  Providerzeit, TTFT, Tool-/API-Anzahl, erfolgreiche Compactions sowie bei
  lokaler Inferenz die vorhandene Energie-Messung.

Prompts, Antworten, Toolargumente/-ergebnisse, Chat-/Sender-IDs, URLs,
Zugangsdaten und Providerfehlertexte werden weder an llmtop übertragen noch
persistiert.

## Prüfung und Machbarkeit

Die Integration ist mit der lokal installierten Hermes-Version **0.23.0**
machbar, ohne Hermes-Core zu patchen oder zusätzliche Abhängigkeiten
hinzuzufügen:

1. Hermes unterstützt native Python-Plugins unter
   `~/.hermes/plugins/<name>/` mit `plugin.yaml`, `__init__.py` und
   `register(ctx)`. `hermes plugins doctor` und `validate` prüfen genau diesen
   offiziellen Weg.
2. Die Observer-Hooks liefern die notwendigen stabilen Grenzen:
   `pre_llm_call`/`post_llm_call`, `pre_api_request`/`post_api_request`,
   `api_request_error`, `post_compaction`, `pre_tool_call`/`post_tool_call`,
   `subagent_start`/`subagent_stop`, `on_session_end` und
   `agent_loop_stopped`.
3. `post_api_request` enthält normalisierte Usage, tatsächliche Providerdauer,
   Kontextlimit und `first_chunk_at`. Damit sind Token, Tok/s und TTFT ohne
   Textschätzung möglich. `post_compaction` wird nur nach einer tatsächlich
   übernommenen Compaction ausgelöst.
4. Der laufende Gateway-Prozess und lokale llama.cpp-Runtimes können so
   instrumentiert werden, ohne Prozesslisten, Kommandozeilen oder deren
   Secrets auszulesen. Die bestehende GPU-/CPU-/Power-Erfassung bleibt
   unverändert.
5. Nicht instrumentierbar bleibt der veraltete separate Befehl `hermes-agent`.
   Er lädt keine native Hermes-Plugin-Schnittstelle. Unterstützt werden der
   aktuelle Befehl `hermes` und dessen Gateway-/Server-Prozesse.

## Architekturentscheidung

### Adapter und Installation

- Ein dependency-freies natives Hermes-Plugin liegt versioniert unter
  `hermes/llmtop-hermes-metrics/`:

  ```text
  hermes/llmtop-hermes-metrics/
  ├── plugin.yaml
  └── __init__.py
  ```

- Es registriert ausschließlich Observer-Hooks; keine Tools, Middleware,
  Shell-Hooks oder Core-Overrides.
- Der Versand erfolgt über eine begrenzte interne Queue und einen Daemon-Worker
  mit `urllib.request`, 500-ms-Timeout und Fail-open-Verhalten. Ein voller
  Puffer verwirft nur alte Live-Updates, niemals Hermes-Antworten oder
  Abschlüsse. Der Netzversand läuft nie im Token- oder Toolpfad.
- Das Plugin liest nur eine private llmtop-Laufzeitdatei unter
  `$XDG_STATE_HOME/llmtop/hermes-collector.json` (Fallback
  `~/.local/state/llmtop/`), mit Collector-URL und -Token, Rechten `0600`.
  Es liest weder `~/.hermes/config.yaml` noch Provider-Credentials.
- `llmtop` aktualisiert diese Datei beim Start des lokalen Collectors. Damit
  erreicht auch der bereits als systemd-Service laufende Hermes-Gateway einen
  neu erzeugten lokalen Collector ohne Service-Neustart.
- Ein explizites `--install-hermes-adapter` kopiert/aktualisiert die beiden
  Plugin-Dateien atomar nach `~/.hermes/plugins/llmtop-hermes-metrics/`, führt
  anschließend `hermes plugins doctor … --ci` aus und aktiviert das Plugin
  erst nach erfolgreicher Prüfung. Der normale TUI-Start verändert das
  Hermes-Benutzerprofil nicht.
- Nach einem Adapterupdate wird der laufende Gateway einmal kontrolliert
  neugestartet; der Plan verändert weder dessen systemd-Unit noch
  Hermes-Konfiguration automatisch.

### Datenvertrag

`source: "hermes"` wird als vierte instrumentierte Quelle in Schema 2 ergänzt.
Bestehende JSONL-Einträge und Quellen bleiben unverändert lesbar.

Zusätzliche optionale, strikt normalisierte Felder:

```json
{
  "source": "hermes",
  "session_id": "opaque-hermes-session-id",
  "lineage_id": "erste-session-id-der-konversation",
  "parent_session_id": "opaque-parent-session-id",
  "source_run_id": "opaque-turn-id",
  "run_kind": "main|subagent|auxiliary|maintenance",
  "platform": "cli|telegram|cron|…",
  "activity": "context_compaction|title_generation|…",
  "api_attempts": 3,
  "api_errors": 1,
  "tool_calls": 2,
  "tool_errors": 0,
  "execution_scope": "local|remote|unknown"
}
```

Regeln:

- Alle Textwerte sind kurze, kontrollierte Metadaten (maximal 120 Zeichen);
  `run_kind` und `execution_scope` stammen aus geschlossenen Mengen.
- `session_id`, `lineage_id`, `parent_session_id` und `source_run_id` bleiben
  opake technische IDs; sie werden weder aus Prompt noch Chat-Adresse
  abgeleitet. In der TUI erscheinen nur gekürzte Kennungen.
- `platform` beschreibt nur die Hermes-Oberfläche, niemals Nutzer oder Chat.
- `activity` ist ausschließlich der von Hermes gelieferte Aux-/Wartungstyp;
  unbekannte oder zu lange Werte werden zu `other` normalisiert.
- `execution_scope` wird im Plugin aus der tatsächlich genutzten Route als
  `local` (nur Loopback/lokaler Provider), `remote` oder `unknown` bestimmt.
  Die Basis-URL selbst wird nie gesendet.
- Geschätzte Kosten werden nicht integriert: Der öffentliche Observer-Vertrag
  liefert keinen belastbaren Kostenwert. Ein späterer Hermes-Hook kann das
  additiv nachreichen; llmtop liest bis dahin keine Hermes-Sessionsdatenbank.

### Laufsemantik

| Hermes-Ereignis | llmtop-Ereignis | Bedeutung |
|---|---|---|
| `pre_llm_call` | `started` | Ein Hauptlauf je Nutzerturn; Schlüssel `(session_id, turn_id)` |
| `pre_api_request` | `updated` | aktueller Provider, Modell, Kontextlimit, lokaler/entfernter Scope und API-Versuch |
| `post_api_request` | `updated` | echte Usage, Providerdauer und TTFT; Tokens/Providerzeit werden über erfolgreiche Haupt-API-Aufrufe aggregiert |
| `api_request_error` | `updated` | nur `api_errors` erhöhen; ein möglicher Fallback beendet den Hauptlauf nicht |
| `pre/post_tool_call` | `updated` | ausschließlich Anzahl, Fehleranzahl und gemessene Tooldauer; keine Toolnamen |
| `post_compaction` | `updated` | Zähler nur für committed Compactions; bei Sessionrotation Lineage fortschreiben |
| `post_llm_call` | `completed` | genau ein finaler Hauptlauf |
| `agent_loop_stopped` / abgebrochener `on_session_end` | `cancelled` bzw. `error` | genau ein finaler Abbruch ohne erfundene Usage |
| `subagent_start/stop` | eigener `started`/finaler Run | `run_kind=subagent`, Beziehung über `parent_session_id` |
| `pre/post_auxiliary_call` | eigener `started`/finaler Run | `run_kind=auxiliary`, Aktivität z. B. `context_compaction` |
| `post_compaction` ohne aktiven Turn | eigener finaler Wartungsrun | `run_kind=maintenance`, damit Idle-Compactions sichtbar bleiben |

Für Haupt- und Subagent-Läufe gelten folgende eindeutige Werte:

- `prompt_tokens` und `output_tokens` sind Summen aller erfolgreichen
  Haupt-Providerantworten eines logischen Agentenlaufs, einschließlich
  Tool-Schleifen und erfolgreichem Fallback.
- `context_tokens` ist ausschließlich der letzte bestätigte Providerkontext
  dieses Laufs, nicht die Summe mehrerer API-Aufrufe.
- `eval_duration_s` ist die Summe der tatsächlichen Providerzeiten;
  `total_duration_s` ist die gesamte Agentenlaufzeit. Tok/s nutzt weiter die
  Providerzeit und wird nicht durch Tools oder Wartezeiten verfälscht.
- `first_token_duration_s` stammt aus
  `first_chunk_at - started_at` des letzten sichtbaren Antwort-Streams.
  Bei fehlendem Chunk bleibt der Wert `n/a`.
- Hilfsaufrufe bleiben separat, damit deren Token nicht still in der
  Nutzerantwort doppelt gezählt werden.

Der Collector startet eine Energie-Messung für Hermes nur bei
`execution_scope=local`; sie endet mit dem zugehörigen Run. Bei einer Route,
die von lokal auf remote wechselt, bleibt die bereits gestartete Messung bis
zum Abschluss erhalten; eine Remote-Route startet keine Messung.

## Darstellung

- `source_label()` ergänzt `Hermes/<Provider>`; `Hermes` wird in der kompakten
  Ansicht neben Pi und WebUI als eigene Quelle geführt.
- History gruppiert Hermes nach `lineage_id`, ersatzweise `session_id`.
  Subagent-Gruppen bleiben getrennt, tragen im Overlay aber die gekürzte
  Elternkennung. Eine Sessionrotation durch Compaction zerreißt damit keine
  Konversation.
- `run_kind`, Plattform, Aktivität, API-/Toolzähler und Elternkennung stehen
  im History-Overlay und in `--once`, nicht als neue breite Pflichtspalten.
  Die bestehende 40×18-Darstellung bleibt dadurch stabil.
- Die Token-/Timing-Spalten behalten ihre bisherige Bedeutung. Der Overlaytext
  kennzeichnet bei Hermes explizit „Agenten-Summe“ und „letzter Kontext“, damit
  aggregierte Tokens nicht als einzelner Providerrequest missverstanden werden.
- Energie in Wh wird wie bisher nur angezeigt, wenn der Collector eine echte
  lokale Messung besitzt.

## Umsetzung in drei überprüfbaren Schritten

### 1. Schema, Collector und Anzeige

Betroffene Dateien: `llmtop_metrics.py`, `llmtop_tui.py`, `llmtop.py`,
`README.md`, `status.md`, `version.md`.

1. Quelle `hermes`, die genannten optionalen Metadaten und die sichere
   Normalisierung ergänzen; alte Schema-1/2-Daten unverändert lesen.
2. `POST /v1/runs/hermes` ergänzen und die Quelle serverseitig erzwingen.
   Live-/History-Deduplizierung bleibt `(source, run_id)`.
3. Hermes-Lineage-Gruppierung, Labels, Overlay/`--once`, Kompaktansicht und
   lokale Energiebedingung ergänzen. Keine bestehende Taste oder Spalte wird
   entfernt.
4. Private `hermes-collector.json` beim lokalen Collector schreiben und nur
   lesend durch Adapter/Tests verwenden.
5. Manuelle Schema-2-Events für Haupt-, Subagent-, Hilfs- und Wartungslauf
   testen; insbesondere Parallelität, Sessionrotation, lokale/Remote-Energie
   und History-Gruppen.

**Abnahme:** Vier parallele Hermes-Ereignisse bleiben neben Pi und WebUI in
TUI, `--once`, `run.jsonl` und History unterscheidbar. Ein lokaler Hermes-Run
hat Wh, ein Cloud-Run nicht; alte Daten bleiben lesbar.

### 2. Native Hermes-Plugin-Adapter

Betroffene Dateien: neu `hermes/llmtop-hermes-metrics/plugin.yaml`,
`hermes/llmtop-hermes-metrics/__init__.py`, lokale Tests ausschließlich unter
`/tmp/pi/...`.

1. Einen kleinen Plugin-Spike gegen die installierte Hermes-Version ausführen:
   Hook-Signaturen und reale Payloads für CLI-, Gateway-, Tool-, Fallback-,
   Subagent- und Compaction-Pfade prüfen. Nur Feldnamen, Typen und Zähler
   protokollieren; kein Text oder Secret in Testausgaben.
2. Adapter mit Run-Registry, Lineage-Map, bounded Versandqueue und
   idempotentem Finalisieren implementieren. Alle Callbacks akzeptieren
   `**kwargs`; Versand- und Parsingfehler bleiben fail-open.
3. Main-, Subagent-, Aux- und Wartungsläufe gemäß Datenvertrag erzeugen.
   Doppelte Hooks, Retry/Fallback und verspätete Events dürfen weder einen
   zweiten Abschluss noch zusätzliche Compactions erzeugen.
4. Mit einem lokalen sowie einem Cloud-Run testen, dazu Tool-Loop,
   Kontextcompaction, Delegation, `/stop`, Gateway-Neustart und nicht
   erreichbaren Collector.

**Abnahme:** Das Hermes-Plugin passiert `hermes plugins doctor … --ci` und
`validate`. Bei Collector-Ausfall bleiben Hermes-Antwort, Gateway und Exit-Code
unverändert; pro logischem Run entsteht genau ein finaler History-Eintrag.

### 3. Explizite Installation, Dokumentation und Release

Betroffene Dateien: `llmtop.py`, `llmtop_metrics.py`, `README.md`, `status.md`,
`version.md`.

1. `--install-hermes-adapter` implementieren: Dateien atomar installieren,
   mit Hermes Doctor prüfen und erst danach aktivieren. Bestehende andere
   Plugins bleiben unangetastet.
2. Adapterstatus im Hilfebereich aus installierter/validierter Konfiguration
   ableiten, niemals aus Provider- oder Gateway-Secrets.
3. README dokumentiert Voraussetzungen, explizite Installation,
   Gateway-Neustart, Datenminimierung, die erfassten Hermes-Surfaces und die
   Grenze des Legacy-Befehls `hermes-agent`.
4. Patchversion in `llmtop.py`, Adaptermanifest, README, `status.md` und
   `version.md` synchron erhöhen. Anschließend `git diff --check`,
   Python-Syntaxcheck, Adaptertests, `--version`, `--once` und
   `--once --no-nvidia` ausführen.

**Abnahme:** Nach `python3 llmtop.py --install-hermes-adapter` und einmaligem
Gateway-Neustart erscheinen echte Telegram-/CLI-Hermes-Läufe live und final in
llmtop; der Collector kann dabei ausfallen, ohne Hermes zu beeinflussen.

## Testmatrix

| Fall | Erwartung |
|---|---|
| CLI/TUI/Gateway/cron/ACP/Webhook | jeweils ein Hermes-Hauptlauf mit korrekter Plattform, ohne Nachrichteninhalt |
| Tool-Loop | ein Hauptlauf, aggregierte echte Providerusage, Toolzähler ohne Tooldaten |
| Providerretry/Fallback | ein Hauptlauf, `api_errors` erhöht, finaler Provider/Modellstand sichtbar |
| lokaler llama.cpp-Route | `execution_scope=local`, reale Wh-Messung wenn Sensor verfügbar |
| Cloudroute | `execution_scope=remote`, kein erfundener Wh-Wert |
| Subagent | eigener Run plus Elternkennung, keine Doppelsumme im Elternlauf |
| Hilfs-Compaction | eigener Auxiliary-Run und genau ein Compaction-Zähler des betroffenen Laufs |
| Idle-Compaction | finaler Wartungsrun statt Verlust des Ereignisses |
| Sessionrotation | gemeinsame Lineage-Gruppe über alte/neue Session-ID |
| `/stop`, Fehler, Gateway-Prozessende | genau ein `cancelled`/`error`, keine erfundenen Tokens |
| Collector aus / Queue voll | Hermes läuft unverändert weiter; höchstens Live-Updates fehlen |
| alte JSONL und 40×18 | rückwärtskompatibel, keine Layoutüberlappung |

## Nichtziele und Grenzen

- Kein Core-Patch, keine Auswertung von Hermes-Logs, Sessionsdatenbank,
  Prozesskommandozeilen oder Providercredentials.
- Kein Mitschnitt von Prompt, Antwort, Denken, Toolname, Toolargument,
  Toolresultat, Sender, Chat-ID, URL oder Fehlernachricht.
- Keine automatische Installation oder Aktivierung eines Hermes-Plugins beim
  bloßen TUI-Start.
- Keine Anzeige eines idle geladenen llama.cpp-Modells als Ollama-Modellkarte;
  die vorhandene Modellkarte bleibt korrekt Ollama-spezifisch. Hermes-Modelle
  erscheinen ausschließlich als tatsächlich instrumentierte Runs.
- Keine Kostenschätzung, bis Hermes dafür einen stabilen, content-freien
  Observerwert bereitstellt.
