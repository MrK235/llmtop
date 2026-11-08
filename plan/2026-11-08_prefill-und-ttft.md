# Plan: Prefill und Zeit bis zum ersten Token

## Ziel

Für alle instrumentierten Runquellen sollen zwei klar getrennte Startmetriken
erfasst und dargestellt werden:

- **Prefill:** serverseitige Verarbeitung des Eingabekontexts, soweit der
  Provider dafür einen echten Dauerwert liefert.
- **TTFT (Time to First Token):** clientseitig gemessene Zeit vom unmittelbar
  bevorstehenden Provider-Aufruf bis zum ersten beobachtbaren generierten
  Delta.

Es werden keine Zeiten aus Textlängen, Tokenmengen oder Gesamtdauer geschätzt.
Fehlt eine belastbare Quelle, bleibt der Wert `n/a`.

## Prüfergebnis

### Bereits vorhandene Daten

Das persistierte Schema unterstützt schon:

- `prompt_tokens`
- `prompt_eval_duration_s`
- `load_duration_s`
- `eval_duration_s`
- `total_duration_s`

Ollama liefert im finalen `done`-Objekt außerdem die Rohfelder
`prompt_eval_count`, `prompt_eval_duration`, `load_duration`, `eval_duration`
und `total_duration`. Der direkte Ollama-Client und der Open-WebUI-Adapter
übernehmen diese Werte bereits grundsätzlich. Eine Prefill-Rate kann daher
rein aus vorhandenen finalen Werten berechnet werden:

```text
prefill_rate = prompt_tokens / prompt_eval_duration_s
```

Eine eigene TTFT-Metrik existiert bisher nicht.

### Direkter Ollama-Client (`--chat` / `--generate`)

- Der Code liest den NDJSON-Stream selbst und kann den Zeitpunkt jedes Chunks
  unmittelbar beobachten.
- Der Messbeginn kann direkt vor `urlopen()` gesetzt werden.
- Als erstes Token zählt der erste nichtleere generierte Inhalt:
  - `/api/chat`: `message.content`, `message.thinking` oder ein Tool-Call-Delta,
  - `/api/generate`: `response`.
- Leere Start-/Ladechunks dürfen TTFT nicht beenden.
- Exakte Prefill-Dauer und Prompt-Token kommen final von Ollama.

**Ergebnis:** TTFT und Prefill sind vollständig und sinnvoll erfassbar.

### Open WebUI

- `request()` läuft unmittelbar vor jedem Provider-Aufruf.
- `stream()` erhält die ausgehenden Streamereignisse.
- Der erste nichtleere Modellinhalt kann dort erkannt werden. Reine Status-,
  Usage- oder Abschlussereignisse zählen nicht als erstes Token.
- Tool-Loops können mehrere Provider-Aufrufe innerhalb eines angezeigten Runs
  erzeugen. Die Startmessung muss deshalb bei einem tatsächlich neuen
  Provider-Aufruf zurückgesetzt werden, nicht bei einem doppelten Filteraufruf.
- Ein kleiner Request-Fingerprint kann nur im Arbeitsspeicher unterscheiden,
  ob derselbe Hook erneut oder ein neuer Tool-/Fortsetzungsaufruf verarbeitet
  wird. Inhalte oder Fingerprints werden nicht persistiert.
- Ollama-Prefillwerte sind final verfügbar, wenn Open WebUI die nativen Felder
  weiterreicht. Andere Provider liefern meistens nur Token-Usage ohne separate
  Promptdauer.

**Ergebnis:** TTFT ist adapterseitig messbar. Prefill ist für Ollama exakt,
für andere Provider nur bei ausdrücklich gelieferter Promptdauer verfügbar.

### Pi-Adapter

Die installierte Pi-Version bietet geeignete Ereignisse:

- `before_provider_request`: unmittelbar vor jedem Provider-Aufruf,
- `message_update`: normalisierte Streamingupdates,
- `assistantMessageEvent` mit `text_delta`, `thinking_delta` und
  `toolcall_delta`,
- `provider_stream_event`: rohe Providerereignisse vor der Normalisierung.

Damit kann TTFT pro Modellturn belastbar von `before_provider_request` bis zum
ersten nichtleeren Delta gemessen werden. Die Metrik des angezeigten
Agenten-Runs folgt wie die bestehenden Token- und Ratenwerte dem jeweils
aktuellen beziehungsweise letzten Modellturn.

Die normalisierte Pi-Usage enthält Tokenzahlen und Gesamtdauer, aber keine
allgemeine Prefill-Dauer. Für Ollama kann `provider_stream_event` die finalen
nativen `prompt_eval_*`-Felder liefern. Cloudprovider bleiben bei Prefill
`n/a`, sofern deren Rohereignis keine explizite Eingabedauer enthält.

**Ergebnis:** TTFT ist vollständig messbar. Prefill ist providerabhängig und
für Ollama gezielt ergänzbar.

## Einheitliche Semantik

### TTFT

Neues optionales Schemafeld:

```json
{
  "first_token_duration_s": 1.27
}
```

Definition:

- monotone Zeitmessung,
- Start unmittelbar vor dem Provider-Aufruf,
- Ende beim ersten nichtleeren, vom Modell erzeugten Text-, Thinking- oder
  Tool-Call-Delta,
- keine Status-, Header-, Usage- oder leeren Startchunks,
- Messwert wird sofort als `updated` gesendet und final beibehalten.

Damit ist TTFT eine **adapterbeobachtete Providerlatenz**. Nicht sichtbares,
vom Provider nicht gestreamtes Reasoning kann nicht früher erkannt werden.

### Prefill

Es bleibt beim vorhandenen Feld:

```json
{
  "prompt_eval_duration_s": 0.84,
  "prompt_tokens": 16384
}
```

Darauf aufbauend wird ausschließlich abgeleitet:

```text
Prefill-Rate = prompt_tokens / prompt_eval_duration_s
```

Regeln:

- nur echte Providerdauer verwenden,
- keine Ableitung aus `TTFT - load_duration`, weil darin Netzwerk, Queueing und
  erster Decode-Schritt enthalten sein können,
- kein Fallback auf Gesamtdauer,
- Null oder fehlende Dauer ergibt `n/a`.

## Darstellung

Die bestehende Tabelle ist bereits dicht. Die Mindestgröße `40×18` darf nicht
steigen.

### Breite TUI

Ab ausreichend großer Breite erhält die Tabelle eine kompakte Spalte
`Start`:

```text
Start
P 0.8s/19.5k · T 1.2s
```

- `P`: Prefill-Dauer und optional Rate in Token/s,
- `T`: TTFT,
- laufende Runs zeigen TTFT sofort nach dem ersten Delta,
- Prefill erscheint normalerweise erst mit finaler Provider-Usage.

Bei mittlerer Breite wird gekürzt:

```text
P 0.8s · T 1.2s
```

Bei schmaler Breite wird die Spalte ausgeblendet. Die Werte bleiben im
History-Overlay und in `--once` sichtbar.

### `--once`

Zusatz zum Runtext:

```text
Prefill 0.8s · 19.5k Tok/s · 1. Token 1.2s
```

Fehlende Einzelwerte werden unabhängig als `n/a` dargestellt.

### History-Overlay

Neben den Rohfeldern wird eine kurze lesbare Timing-Zusammenfassung ergänzt.
Eine neue Sortierspalte ist im ersten Schritt nicht erforderlich.

## Umsetzung in drei Schritten

### 1. Schema und gemeinsame Berechnungen

Betroffene Dateien: `llmtop_metrics.py`, `test_llmtop.py`.

- `normalize_run()` um `first_token_duration_s` erweitern.
- Merge-, Live- und History-Persistenz unverändert über Schema 2 nutzen.
- Reine Helfer für Prefill-Rate und kompakte Timingformatierung ergänzen.
- Ungültige, negative und nichtnumerische Werte verwerfen.
- Tests für Schema, Merge, fehlende Werte und Einheiten ergänzen.

### 2. Messung in allen Adaptern

Betroffene Dateien: `llmtop_metrics.py`, `open_webui/llmtop_run_metrics.py`,
`pi/llmtop_run_metrics.ts` und Adaptertests.

- Direkter Ollama-Client: monotone Startzeit vor `urlopen()`, erstes nichtleeres
  Chat-/Generate-Delta erkennen und Live-Run sofort aktualisieren.
- Open WebUI: Messanker unmittelbar vor Rückgabe aus `request()`, erstes
  inhaltliches `stream()`-Delta erkennen und genau einmal melden.
- Open-WebUI-Tool-Loops durch einen ausschließlich im Arbeitsspeicher gehaltenen
  Request-Fingerprint unterscheiden; doppelte Filterdurchläufe dürfen TTFT
  nicht zurücksetzen.
- Pi: `before_provider_request` als Startanker, erstes nichtleeres
  `text_delta`/`thinking_delta`/`toolcall_delta` als Ende verwenden.
- Pi-Ollama: finale native `prompt_eval_count` und
  `prompt_eval_duration` aus `provider_stream_event` übernehmen.
- Finale Events behalten den schnell gemeldeten TTFT-Wert bei.

### 3. Anzeige und Dokumentation

Betroffene Dateien: `llmtop_tui.py`, `llmtop.py`, `README.md`, `status.md`,
`version.md`.

- Dynamische `Start`-Spalte nur bei ausreichender Breite ergänzen.
- `--once` und History-Overlay um Prefill-Dauer, Prefill-Rate und TTFT ergänzen.
- Aktuelle Runs zeigen TTFT unmittelbar nach dem ersten Delta; fehlendes Prefill
  bleibt bis zum finalen Providerwert `n/a`.
- Dokumentieren, dass TTFT adapterbeobachtet und Prefill providerseitig ist.
- Versionsstand als Patch erhöhen und Adapterversionen synchronisieren.

## Tests und Abnahme

### Automatisierte Tests

- Leere Streamchunks beenden TTFT nicht.
- Erstes Text-, Thinking- oder Tool-Delta setzt TTFT genau einmal.
- Spätere Deltas überschreiben TTFT nicht.
- Doppelte Open-WebUI-Request-Hooks setzen den Messbeginn nicht zurück.
- Ein echter Tool-Folgeaufruf erhält eine neue Turnmessung.
- Ollama-Nanosekunden werden korrekt in Sekunden normalisiert.
- Prefill-Rate wird nur mit Prompttoken und positiver Promptdauer berechnet.
- Cloudprovider ohne Promptdauer bleiben bei Prefill `n/a`.
- TUI bleibt bei 40×18 überlappungsfrei; breite Ansicht und `--once` zeigen die
  neuen Werte.

### Reale Prüfung

Je ein ausreichend langer Lauf über:

1. `--chat` oder `--generate`,
2. Open WebUI mit Ollama,
3. Pi mit Ollama,
4. Pi mit einem Cloudprovider.

Erwartung:

- TTFT erscheint kurz nach dem ersten Streamdelta.
- Ollama zeigt nach Abschluss Prefill-Dauer und Prefill-Rate.
- Cloudprovider zeigen Prefill nur, wenn eine echte Promptdauer geliefert wird.
- History enthält dieselben finalen Werte wie der aktuelle Run.

## Nichtziele

- Keine Schätzung der Prefill-Dauer aus TTFT, Tokenzahl oder Gesamtdauer.
- Keine Tokenisierung von Prompt- oder Antworttexten.
- Keine Speicherung von Streaminhalten, Request-Fingerprints oder Rohpayloads.
- Keine Erhöhung der Mindest-Terminalgröße.
- Keine neue Abhängigkeit und kein Proxy vor Ollama.
