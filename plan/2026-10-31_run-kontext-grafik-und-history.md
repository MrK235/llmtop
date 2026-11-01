# Plan: Kontext des aktuellen Runs grafisch darstellen und historisieren

## Ziel

Den **Kontextverbrauch eines instrumentierten Runs** als Balken im Bereich
„Aktuelle Runs“ darstellen und den Abschlusswert mit der bestehenden
Run-Historie (`runs.jsonl`) speichern. Die Anzeige bleibt datensparsam: Es
werden ausschließlich Tokenzähler, Kontextlimit und technische Herkunft
persistiert – niemals Prompt, Chatverlauf oder Antworttext.

„Kontext“ bedeutet dabei transparent: **Prompt-Token plus erzeugte Token des
jeweiligen Requests**, bezogen auf das für diesen Run bekannte Kontextlimit.
Das ist kein verlässlicher Zähler eines eventuell serverseitig wiederverwendeten
KV-Caches; ohne explizite Metrik wird kein solcher Wert behauptet.

## Bestand und Quellenbewertung

| Wert | Bestehende Quelle | Verfügbarkeit | Umgang |
|---|---|---|---|
| Modell-Kontextlimit | Ollama `/api/ps` → `models[].context_length` | beim TUI-Refresh, modellbezogen | Anzeige-Fallback für aktive Runs; nicht rückwirkend für History geeignet |
| Prompt-Token | Ollama-finales `prompt_eval_count`; Open-WebUI-`usage` | bei den derzeitigen Quellen erst zum Abschluss zuverlässig | als `prompt_tokens` übernehmen |
| Ausgabe-Token | Ollama-finales `eval_count`; Open-WebUI-`usage` | bei den derzeitigen Quellen erst zum Abschluss zuverlässig | als `output_tokens` übernehmen |
| explizites Kontextlimit | optionales Schema-2-Runereignis | nur wenn der Sender es wirklich kennt | höchste Priorität und in History persistieren |
| angefordertes Limit | direkter Ollama-Request `options.num_ctx` | nur `--chat`/`--generate`, falls gesetzt | als Run-Limit mit Herkunft `request` verwenden |

Aktuell kann weder `/api/ps` noch die passive Ollama-API einen aktiven Request
mit einem exakten Kontextverbrauch oder Live-Tokenfortschritt verknüpfen.
Der Open-WebUI-Adapter sieht ebenfalls vor allem finale Usage. Deshalb zeigt
llmtop während eines Runs zunächst einen klaren Wartezustand, statt Fortschritt
zu schätzen. Sobald finale Zähler vorliegen, ist der Balken vollständig.

## Datenmodell und Prioritäten

`normalize_run()` erhält zwei optionale, numerisch validierte Felder:

```json
{
  "context_tokens": 10240,
  "context_limit": 32768,
  "context_limit_source": "event|request|model"
}
```

- `context_tokens` wird nur explizit akzeptiert oder aus vorhandenen,
  autoritativen `prompt_tokens + output_tokens` abgeleitet. Fehlt einer der
  Tokenzähler, bleibt der Wert unbekannt.
- Ein explizites `context_limit` im Schema-2-Event hat Vorrang.
- Beim direkten Clientmodus wird `options.num_ctx` nur dann als Limit
  gespeichert, wenn es eine positive Zahl ist (`context_limit_source=request`).
- Fehlt ein persistiertes Limit, ergänzt der Renderer **nur für aktive Runs**
  das `context_length` des gleichnamigen geladenen `/api/ps`-Modells
  (`context_limit_source=model`). Dieser abgeleitete Wert wird nicht als
  historischer Fakt nachträglich in alte Run-Einträge geschrieben.
- Ohne beide Werte: `Kontext [leer] n/a / <Limit>` beziehungsweise
  `Kontext: warten auf Provider`. Bei unbekanntem Limit gibt es keinen
  Prozentwert.
- Für die Balkenrechnung wird der Wert auf 100 % begrenzt; bei
  `context_tokens > context_limit` erscheint der Wert rot mit sichtbarem
  `über Limit`.

Damit bleiben bestehende Schema-1-Dateien und Schema-2-Sender kompatibel:
alle Kontextfelder sind optional. Die vorhandene Begrenzung und
Deduplizierung der Run-History bleibt unverändert.

## Darstellung

### TUI: direkt unter der aktuellen Run-Zeile

Für jeden der bereits maximal drei aktiven Runs folgt bei ausreichender Höhe
eine kompakte zweite Zeile mit derselben Balkengeometrie wie CPU/RAM/GPU:

```text
Open WebUI  qwen3.5:4b  running  Tokens: warten auf Provider · vor 0.3s
Kontext     [###########         ]  10.2k / 32.8k Token  31.1 %
```

- Grün unter 70 %, gelb ab 70 %, rot ab 90 %; die Farbgrenzen gelten nur für
  einen bekannten Zähler *und* ein bekanntes Limit.
- Die Textwerte bleiben auch ohne Farbe verständlich und werden mit
  `compact_tokens()` formatiert.
- Ist die Terminalhöhe zu klein, hat die bestehende garantierte
  History-Zeile Vorrang: Kontext-Unterzeilen werden zuerst ausgelassen; die
  aktuelle Run-Hauptzeile und die History bleiben sichtbar.
- `--once` verwendet die gleiche formatierende Hilfsfunktion und schreibt
  weiterhin vor der Ausgabe einen Snapshot.

### History: Abschlussläufe

Die vorhandenen Zeilen im Abschnitt „History“ sowie in `--once` erhalten
hinter Token/Rate einen knappen Kontextzusatz, zum Beispiel:

```text
14:30  Ollama CLI  qwen3.5:4b  completed  Tokens: 10.2k … · Kontext 10.2k/32.8k (31 %)
```

Fehlt ein historisch gespeichertes Limit, steht `Kontext n/a`; es wird dort
nicht anhand eines aktuell geladenen, möglicherweise inzwischen anders
konfigurierten Modells ergänzt.

## Umsetzung in drei Schritten

1. **Reine Kontextfunktionen und Rendering**
   - Kleine Hilfsfunktionen für Kontexttoken, Limitauflösung, Prozentwert,
     Ampelfarbe und kompakten Text in `llmtop.py` ergänzen.
   - Aktive Runs gegen die bereits abgefragte `/api/ps`-Modellliste abgleichen
     und TUI/`--once` mit dem Balken erweitern.
   - Höhenberechnung so anpassen, dass der Mindestmodus 40×18 und die
     sichtbare History-Garantie erhalten bleiben.

2. **Erfassung und Persistenz**
   - Die optionalen Kontextfelder in `normalize_run()`, Live-Datei und
     `runs.jsonl` erhalten.
   - `--chat`/`--generate`: gültiges `options.num_ctx` beim Runstart erfassen;
     nach finaler Ollama-Antwort Kontexttoken aus den finalen Zählern ableiten.
   - Open-WebUI-Adapter: ein ausdrücklich vorhandenes numerisches
     `options.num_ctx` als `context_limit` in Started-/Finalevent weitergeben;
     ohne solche Angabe nichts raten. Sender können künftig optional
     `context_tokens`/`context_limit` liefern.

3. **Gezielte Validierung und Dokumentation**
   - Mock-JSONL-Ereignisse für unbekannte Werte, 0 %, 69 %, 70 %, 90 %, über
     Limit, mehrere Runs und alte Schema-1-Einträge prüfen.
   - Einen finalen Direktrun mit und ohne `options.num_ctx` prüfen und
     verifizieren, dass in `runs.jsonl` nur erlaubte Metrikfelder stehen.
   - `py_compile`, `--once`, `--once --no-nvidia` und `--version` ausführen.
   - Versionsnummer als Minor-Release erhöhen sowie README, status.md und
     version.md zu Quellen, Datenschutz, Anzeige und Grenzen synchronisieren.

## Abnahmekriterien

- Ein aktiver instrumentierter Run zeigt bei verfügbaren Daten einen
  farbigen Kontextbalken mit Tokenwert, Limit und Prozentzahl.
- Fehlende Live-Daten werden als Wartezustand/`n/a`, niemals als geschätzter
  Verbrauch oder `0 %`, dargestellt.
- Ein finaler Run mit bekanntem Limit speichert `context_tokens` und
  `context_limit` in der begrenzten Run-History und zeigt sie dort wieder an.
- Alte History- und Ereignisdateien bleiben lesbar; Prompts und Antworten
  gelangen weder in JSONL noch in die TUI.
- Bei zu kleinen Terminals bleiben mindestens aktuelle Run-Hauptzeile,
  Fußzeile und History sichtbar.
