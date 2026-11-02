# Plan: Konsistente finale Tokenanzeige

## Ziel

Aktive und abgeschlossene Runs sollen einheitlich und verständlich dargestellt
werden. Finale Open-WebUI-Runs zeigen immer echte Prompt-/Ausgabetoken und –
sofern eine echte Evaluierungsdauer vorhanden ist – die daraus berechnete Rate.

## Ist-Befund

- Die finalen Open-WebUI-Daten werden korrekt in `runs.jsonl` gespeichert.
- `Aktuelle Runs` verwendet bereits teilweise eine detaillierte Tokenanzeige.
- `History` verwendet noch eine eigene, verkürzte und inkonsistente Formatierung.
- Bei fehlender Dauer wird in History teils nur `Dauer` angezeigt, während die
  aktuelle Run-Anzeige `Tok/s: n/a` verwendet.
- Dadurch wirkt die Darstellung so, als würden finale Tokenwerte fehlen, obwohl
  sie vorhanden sind.

## Umsetzung

### 1. Gemeinsame Formatierungsfunktionen

- Eine zentrale Funktion für Token-/Ratenwerte verwenden, die für aktuelle Runs,
  History und `--once` dieselbe Ausgabe erzeugt.
- Format:
  - vollständig:
    `Tokens: 11.4k (Prompt 10.1k, Ausgabe 1.3k) · 34.9 Tok/s`
  - Token vorhanden, Dauer fehlt:
    `Tokens: 11.4k (Prompt 10.1k, Ausgabe 1.3k) · Tok/s: n/a`
  - noch keine Token vorhanden:
    `Tokens: warten auf Provider · Tok/s: n/a`
- `n/a` nur bei tatsächlich fehlenden Werten verwenden; keine Schätzungen.
- Die vorhandene `token_rate()`-Berechnung weiter ausschließlich auf
  `output_tokens / eval_duration` stützen.

### 2. History-Darstellung vereinheitlichen

- TUI-History auf die zentrale Formatierung umstellen.
- `--once`-History ebenfalls auf dieselbe Formatierung umstellen.
- Quelle, Modell, Status und Uhrzeit unverändert beibehalten.
- Die Anzeige bei kleinen Terminalhöhen weiterhin kürzen dürfen, aber Quelle
  und finaler jüngster Run müssen sichtbar bleiben.
- Keine Änderung an der getrennten System-Snapshot-History.

### 3. Datenvalidierung

- Vor der Ausgabe nur normalisierte, nichtnegative numerische Token- und
  Dauernwerte verwenden.
- Prompt- und Ausgabetoken getrennt ausgeben, wenn mindestens einer der Werte
  vorhanden ist.
- Gesamttoken weiterhin aus Prompt plus Ausgabe berechnen.
- Finale Runs mit Tokenwerten, aber ohne Dauer, ausdrücklich als
  `Tok/s: n/a` darstellen.

### 4. Tests

- Unit-Tests für die zentrale Formatierung ergänzen:
  - beide Tokenwerte plus Dauer,
  - beide Tokenwerte ohne Dauer,
  - nur Prompttoken,
  - nur Ausgabetoken,
  - keine Tokenwerte.
- Test sicherstellen, dass TUI-History und `--once` dieselbe Formatfunktion
  verwenden.
- Mit den vorhandenen finalen `runs.jsonl`-Einträgen prüfen, dass beispielsweise
  Prompttoken, Ausgabetoken und `Tok/s` gemeinsam sichtbar sind.
- Syntaxcheck, vorhandene Filtertests und `--once --no-nvidia` ausführen.

## Abnahme

Ein abgeschlossener Open-WebUI-Run wird in TUI-History und `--once` identisch
angezeigt, beispielsweise:

`Open WebUI qwen3.6:35b-a3b completed · Tokens: 11.4k (Prompt 10.1k, Ausgabe 1.3k) · 34.9 Tok/s`

Fehlt die Evaluierungsdauer, bleiben Token sichtbar und nur die Rate wird als
`n/a` markiert.

## Nichtziele

- Keine Änderung an Open WebUI, Ollama oder dem Filterprotokoll.
- Keine Token-Schätzungen.
- Keine Speicherung oder Ausgabe von Prompt- oder Antwortinhalten.
