# Update-Plan: Run-Historie und Live-Anzeige reparieren

## Befund

Die drei Symptome haben getrennte, belegte Ursachen:

1. **TUI-Historie:** `_draw()` zeichnet im normalen und kompakten Layout ausschließlich `run_history[0]`. `--once` lädt außerdem standardmäßig nur fünf Einträge. Die Datei `runs.jsonl` speichert dagegen bis zu 100 Runs; aktuell enthält sie 42 Einträge.
2. **Falsche Abschlüsse:** Die aktive, global installierte Open-WebUI-Funktion ist **1.3.1**, die Projektdatei `open_webui/otop_run_metrics.py` jedoch **1.1.0** (abweichende SHA-256). Die installierte Fassung startet einen Disconnect-Watcher und sendet bei `request.is_disconnected()` nach rund 0,5 s `cancelled`. Die vorhandenen 30 jüngsten Abbrüche haben genau diese Dauer und keine Usage-Werte.
3. **Kurz sichtbarer Live-Run / `n/a`:** Der `cancelled`-Event wird im Collector sofort finalisiert und mittels `write_live_run()` aus `run.jsonl` entfernt. Deshalb verschwindet der Run nach einem Frame. Die finale Token- und Rate-Anzeige erhält somit nie die erwarteten Providerwerte.

Die vorhandenen, bereits gespeicherten `cancelled`-Einträge werden nicht verändert: Ohne autoritative Abschlussdaten lassen sie sich nicht nachträglich korrekt als erfolgreich umdeklarieren.

## Umsetzung

### 1. Adapterstand vereinheitlichen und falsche Abbrüche beseitigen

- Die im Projekt verwaltete Adapterdatei zur alleinigen, aktuellen Quelle machen; den tatsächlich installierten Stand nur als Analysebasis verwenden, nicht bei späteren Installationen versehentlich auf 1.1.0 zurücksetzen.
- Den Disconnect-Watcher entfernen bzw. die HTTP-Verbindung nicht als Abbruch der Modellgenerierung deuten. Ein Run wird nur bei einem expliziten Fehler-/Abbruchsignal als `error`/`cancelled` finalisiert; sonst bleibt er bis zum finalen Stream-Chunk oder Outlet aktiv.
- Stream und Outlet weiterhin per Run-ID deduplizieren. Das finale Ereignis übernimmt ausschließlich echte `usage`-/Ollama-Felder; fehlen sie, bleibt der Abschluss korrekt `completed` mit transparentem `n/a`, statt fälschlich `cancelled` zu setzen.
- Adapterversion erhöhen und nach der Codeänderung mit `--install-open-webui-adapter` gezielt aktualisieren, damit Projektdatei und aktive Open-WebUI-Funktion identisch sind.

### 2. Anzeige der letzten zehn Runs korrigieren

- `load_run_history()` für die Anzeige auf zehn Einträge erweitern; die Speicherbegrenzung von 100 bleibt unverändert.
- `--once` gibt die zehn neuesten finalen Runs vollständig, neuester zuerst, aus.
- Die normale TUI zeichnet bis zu zehn History-Zeilen und reserviert ihre benötigte Höhe vor dem Modellbereich. Bei kleinen Terminals bleibt die Mindestgröße 40×18 erhalten: Dort ist mindestens der jüngste Run sichtbar; bei größerer Höhe erscheinen so viele der zehn Zeilen wie Platz haben, ohne Überzeichnung. Nicht passende Modellkarten werden wie bisher ausgeblendet.
- Quelle, Modell, Status sowie echte Token-/Ratewerte verwenden weiter die zentrale Formatierung. Während eines aktiven Runs bleibt der klar gekennzeichnete Provider-Wartezustand zulässig, weil Open WebUI/Ollama echte Tokenwerte oft erst am Ende liefert.

### 3. Prüfen, dokumentieren und Version synchronisieren

- Tests im Scratch-Verzeichnis ergänzen: Start → aktiver Run bleibt sichtbar; explizites `cancelled` finalisiert; `completed` mit Usage wird genau einmal in die Historie geschrieben; zehn History-Einträge sind sortiert sichtbar; enge TUI überzeichnet nicht.
- Einen realen Open-WebUI-Chat mit laufender TUI testen: Run bleibt während der Antwort unter **Aktuelle Runs**, wandert anschließend als `completed` in **History** und enthält finale Usage, sofern der Provider sie liefert.
- Vorgeschriebene Checks ausführen: `py_compile`, `--once`, `--once --no-nvidia`, `--version`, gezielter Diff und `git diff --check`.
- Als Patch-Release versionieren und `VERSION`, `README.md`, `status.md` sowie `version.md` synchronisieren. Die alten fehlerhaften History-Zeilen werden als bekannte Altdaten dokumentiert, nicht gelöscht.

## Abnahme

Ein Open-WebUI-Run bleibt bis zum echten Abschluss sichtbar. Ein erfolgreicher Run endet als `completed` und zeigt danach vorhandene finale Token-/Dauerwerte; echte Abbrüche bleiben `cancelled`. `--once` zeigt die letzten zehn finalen Runs, und die TUI zeigt davon abhängig von der verfügbaren Terminalhöhe bis zu zehn ohne Layout-Überlappungen.
