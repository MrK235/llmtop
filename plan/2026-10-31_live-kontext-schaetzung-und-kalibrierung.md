# Plan: Live-Kontextschätzung mit automatischer Kalibrierung

## Ziel

Während eines laufenden Open-WebUI- oder direkten Ollama-Runs soll der
Kontextbalken sichtbar wachsen, obwohl Ollama seine autoritativen
`prompt_eval_count`- und `eval_count`-Werte erst im finalen Stream-Chunk
liefert.

Die Anzeige unterscheidet klar zwischen:

- **geschätzt**: einfache, noch nicht kalibrierte Berechnung,
- **kalibriert**: modellbezogene Schätzung anhand vorheriger finaler Runs,
- **final**: autoritative Providerwerte nach Abschluss.

Prompts und Antworten werden weiterhin weder in `run.jsonl` noch in
`runs.jsonl` gespeichert. Persistiert werden nur Zähler, Faktoren und technische
Metadaten.

## Technischer Befund

- Ollama liefert bei Streaming-Aufrufen Usage-Metriken nur im finalen
  `done`-Chunk.
- Der bestehende Open-WebUI-Filter sieht beim Request den vollständigen Body
  und während der Antwort Streamereignisse mit `content`, `thinking` oder
  vergleichbaren Textfragmenten.
- Open WebUIs `/status` ist ebenfalls keine exakte Tokenisierung. Es verwendet
  die letzte Provider-Usage und schätzt neuere Inhalte mit ungefähr
  `Zeichen / 4`.
- Ein Filter kann deshalb dieselbe Grundidee lokal anwenden, anschließend aber
  mit den finalen Ollama-Zählern pro Modell kalibriert werden.
- Ein transparenter Proxy könnte native Ollama-Chunks genauer beobachten, wäre
  aber invasiver und ist für den ersten Schritt nicht nötig.

## Messmodell

### Prompt beim Start

Der Adapter berechnet ausschließlich im Arbeitsspeicher eine reproduzierbare
Zeichenanzahl des tatsächlich an den Provider gehenden Request-Kontexts:

- Systemnachrichten,
- Benutzer- und Assistentennachrichten,
- Tooldefinitionen und Toolargumente,
- Toolresultate,
- RAG-/Filterkontext, soweit im finalen Request-Body enthalten,
- Text- und Thinking-Inhalte früherer Nachrichten.

Technische Felder wie IDs, Modellname, Streamschalter und Zeitstempel werden
nicht mitgezählt. Binäre/Base64-Inhalte werden nicht als Text gezählt; für
Bilder und andere multimodale Inhalte bleibt der Verbrauch unbekannt oder wird
separat als unvollständig markiert.

Berechnung:

```text
prompt_estimate = prompt_chars / prompt_chars_per_token
```

Priorität für `prompt_chars_per_token`:

1. modellbezogener kalibrierter Faktor,
2. quellenbezogener Faktor,
3. konservativer Startwert `4.0 Zeichen/Token`.

### Ausgabe während des Streams

Der Open-WebUI-Adapter summiert die Zeichen aller neu eintreffenden sichtbaren
Antwort- und Thinking-Fragmente. Wiederholte Events müssen anhand des bereits
gesehenen Textstands dedupliziert werden, da Hooks sowohl Deltas als auch
kumulative Inhalte liefern können.

```text
output_estimate = streamed_output_chars / output_chars_per_token
context_estimate = prompt_estimate + output_estimate
```

Wenn der Hook eindeutig native Ollama-Deltas liefert, kann zusätzlich die Zahl
nichtleerer Chunks mitgeführt werden. Sie dient nur als Diagnose und nicht als
alleinige Tokenzahl, weil Open WebUI Chunks zusammenfassen oder teilen kann.

Nicht sichtbares und nicht gestreamtes Thinking kann nicht geschätzt werden.
Der Run erhält dann einen Hinweis wie `estimate_partial=true`.

### Abschluss und Kalibrierung

Beim finalen Providerereignis werden Schätzwerte durch
`prompt_eval_count`/`eval_count` beziehungsweise deren Usage-Aliase ersetzt.
Danach werden neue Faktoren berechnet:

```text
prompt_ratio = prompt_chars / prompt_tokens
output_ratio = streamed_output_chars / output_tokens
```

Nur plausible Messungen werden übernommen:

- mindestens 32 gemessene Zeichen,
- mindestens 8 autoritative Token,
- Faktor innerhalb eines Schutzbereichs, beispielsweise `0.5–12.0`,
- kein erkennbar unvollständiger Stream für den jeweiligen Faktor.

Geglättete Aktualisierung pro Modell:

```text
neuer_faktor = 0.8 * alter_faktor + 0.2 * aktuelle_messung
```

Zusätzlich wird die prozentuale Abweichung der letzten Schätzung gespeichert,
um die Anzeigequalität bewerten zu können.

## Ereignisschema

Schema 2 wird ausschließlich um optionale numerische Felder erweitert:

```json
{
  "prompt_tokens_estimate": 10120,
  "output_tokens_estimate": 438,
  "context_tokens_estimate": 10558,
  "estimate_quality": "estimated|calibrated|partial|final",
  "estimate_error_percent": 6.2,
  "context_limit": 32768
}
```

Regeln:

- Live-Datei und Collector dürfen geschätzte Zwischenstände enthalten.
- Die finale Run-History speichert primär autoritative Tokenwerte.
- Schätzwerte dürfen optional zur Qualitätsdiagnose gespeichert werden, aber
  keine Zeichenanzahlen und keine Textinhalte.
- Alte Schema-1- und Schema-2-Ereignisse bleiben lesbar.
- Collector-Ereignisse werden gedrosselt, beispielsweise maximal vier Updates
  pro Sekunde und nur bei einer sichtbaren Tokenänderung.

## Kalibrierungsspeicher

Die modellbezogenen Faktoren werden getrennt von Run- und System-History als
kleine, begrenzte JSON-Datei unter dem bestehenden otop-State-Verzeichnis
geführt, zum Beispiel `context-calibration.json`.

Beispiel:

```json
{
  "qwen3.6:35b-a3b": {
    "prompt_chars_per_token": 3.42,
    "output_chars_per_token": 3.08,
    "prompt_samples": 12,
    "output_samples": 11,
    "updated_at": "2026-10-31T17:00:00Z"
  }
}
```

- maximal ein Eintrag pro Modell,
- atomisches Schreiben und Dateirechte `0600`,
- keine Requesttexte oder Textauszüge,
- alte beziehungsweise nicht mehr verwendete Modelle begrenzen,
- ungültige oder beschädigte Werte ignorieren.

Da der Open-WebUI-Filter in einem anderen Prozess läuft, sind zwei Varianten zu
prüfen:

1. **Bevorzugt:** Der Collector berechnet und speichert Kalibrierungsfaktoren aus
   Start-, Update- und Finalevents. Der Filter übermittelt nur temporäre
   Zeichenanzahlen; der Collector persistiert davon ausschließlich Faktoren.
2. **Fallback:** Der Filter hält Faktoren nur im Speicher. Nach einem
   Open-WebUI-Neustart beginnt die Schätzung wieder mit dem Standardfaktor.

Die bevorzugte Variante erfordert, dass temporäre Zeichenanzahlen im
Collector-Ereignis transportiert, aber niemals in Run-History geschrieben
werden.

## TUI- und `--once`-Darstellung

### Laufender Run

```text
Open WebUI  qwen3.6:35b-a3b  running  Ausgabe ≈438 · ≈28 Tok/s
Kontext     [########            ]  ≈10.6k / 32.8k  32 %  kalibriert
```

Darstellungsregeln:

- `≈` kennzeichnet jeden nicht finalen Wert.
- `geschätzt`, `kalibriert` oder `teilweise` steht sichtbar hinter dem Balken.
- Farbe nach Kontextbelegung: Grün unter 70 %, Gelb ab 70 %, Rot ab 90 %.
- Schätzwerte werden niemals ohne Kennzeichnung als exakte Token ausgegeben.
- Falls noch kein Textfragment eingetroffen ist, wird wenigstens der
  geschätzte Promptverbrauch angezeigt.
- Ist auch der Prompt nicht auswertbar, bleibt der bestehende Wartezustand.

### Finaler Run

```text
Kontext     [########            ]   10.9k / 32.8k  33 %  final
Schätzung   10.6k · Abweichung -2.8 %
```

Die zusätzliche Fehlerzeile erscheint nur bei ausreichend breitem/hohem
Terminal oder in `--once`. In der kompakten History genügt `final` und optional
ein kurzer Fehlerwert.

### Layout-Priorität

Bei wenig Terminalhöhe werden in dieser Reihenfolge ausgeblendet:

1. Diagnosezeile zur Schätzabweichung,
2. Kontext-Unterzeilen älterer paralleler Runs,
3. zusätzliche Modellkarten.

Aktuelle Run-Hauptzeile, erster Kontextbalken, History und Fußzeile bleiben
sichtbar. Die Mindestgröße 40×18 wird nicht erhöht.

## Umsetzung in drei Schritten

### Schritt 1 – Schätzung im Open-WebUI-Adapter

- Reine Standardbibliotheksfunktionen zur stabilen Zeichenmessung des finalen
  Request-Bodys ergänzen.
- Streamfragmente für sichtbare Antwort und Thinking dedupliziert zählen.
- Prompt-, Ausgabe- und Kontextschätzung mit Qualitätskennzeichen erzeugen.
- Update-Ereignisse gedrosselt an den bestehenden Collector senden.
- Finale Providerwerte weiterhin unverändert bevorzugen.

### Schritt 2 – Collector, Kalibrierung und Darstellung

- Optionale Schätzfelder validieren, ohne temporäre Zeichenanzahlen in
  `runs.jsonl` zu übernehmen.
- Pro Modell plausible Zeichen/Token-Faktoren aus finalen Runs lernen und
  atomisch speichern.
- Kalibrierungswerte für neue Runs anwendbar machen; dafür entweder beim
  Started-Event einen Faktor zurückgeben oder eine kleine lesbare
  Collector-Schnittstelle für den lokalen Adapter definieren.
- TUI, `--once` und History zwischen `geschätzt`, `kalibriert`, `teilweise` und
  `final` unterscheiden lassen.

### Schritt 3 – Messung und Fehlergrenzen

- Kontrollierte Streams mit Fließtext, deutschem Text, Code, JSON und Thinking
  ausführen.
- Pro Run Live-Schätzung und finale Ollama-Werte vergleichen.
- Standardfaktor und Glättung nur anhand tatsächlich gemessener Abweichungen
  anpassen.
- Tests für Delta- und kumulative Streamereignisse, doppelte Chunks,
  abgebrochene Runs, Toolloops, Parallelität und Collector-Ausfall ergänzen.
- README, status.md und version.md zu Schätzverfahren, Datenschutz und Grenzen
  synchronisieren; Minor-Version erhöhen.

## Alternative, falls der Filter nicht genügend Streamdaten liefert

Erst wenn ein Live-Test zeigt, dass Open WebUI dem Filter keine nutzbaren
Textdeltas übergibt, wird ein optionaler transparenter Ollama-Proxy neu
bewertet. Dieser könnte native NDJSON-/SSE-Chunks beobachten, live zählen und
am Ende mit den autoritativen Werten korrigieren. Er bleibt zweite Wahl, weil
er Open WebUIs Ollama-Zieladresse verändert und den Netzwerkpfad erweitert.

Die Open-WebUI-Chat-API beziehungsweise `/status` wird nicht als primäre Quelle
verwendet: Sie liefert ebenfalls geschätzte Werte, benötigt Chat-ID und
Authentifizierung und misst gegebenenfalls gegen die Compaction-Schwelle statt
gegen Ollamas tatsächliches Kontextlimit.

## Abnahmekriterien

- Direkt nach Runstart erscheint ein geschätzter Promptverbrauch, sofern der
  Adapter Textkontext erhält.
- Während sichtbare oder gestreamte Thinking-Fragmente eintreffen, wachsen
  Ausgabe- und Kontextwert ohne Warten auf den finalen Chunk.
- Jede nicht autoritative Zahl ist sichtbar mit `≈` und Qualitätsstatus
  gekennzeichnet.
- Nach Abschluss ersetzt otop die Schätzung durch echte Providerwerte und
  berechnet die Abweichung.
- Wiederholte Runs desselben Modells verwenden einen kalibrierten Faktor und
  zeigen gegenüber `Zeichen / 4` messbar geringere mittlere Abweichung.
- Abgebrochene, parallele oder unvollständige Streams erzeugen keine falschen
  finalen Werte und beschädigen die Kalibrierung nicht.
- Weder Requesttexte noch Antworttexte oder temporäre Zeicheninhalte werden in
  Run-History oder Kalibrierungsdatei gespeichert.
- Bestehende Sensoren, Collector-Sicherheit, alte Ereignisschemata und die
  Mindestterminalgröße bleiben funktionsfähig.
