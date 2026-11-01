# Bug Report: Fehlende Live-Metriken in Pi-Runs

**Status:** Behoben mit Version 2.1.9  
**Bereich:** Pi-Adapter / Run-Collector / TUI  
**Betroffene Version:** 2.1.5–2.1.8

## Beschreibung

Während eines laufenden Pi-Agentenlaufs wurden Kontextverbrauch und Tok/s für
ChatGPT nicht beziehungsweise erst nach Abschluss angezeigt. Bei Ollama fehlten
zusätzlich Tok/s und Laufzeit in den Pi-Run-Metriken.

## Erwartetes Verhalten

Während ein Run aktiv ist, sollen bekannte Provider-Metriken laufend angezeigt
werden:

- Kontextverbrauch und Kontextlimit einschließlich Prozentwert
- Ausgabe-Tok/s
- bisherige Laufzeit

Nach Abschluss sollen die finalen Werte in der Run-History gespeichert werden.

## Tatsächliches Verhalten

Der Pi-Adapter sendete Token- und Nutzungsdaten im Wesentlichen erst beim
`agent_settled`-Ereignis. Während des laufenden Runs wurden daher keine
fortlaufenden Metrik-Updates übertragen. Außerdem wurden Cache-Input,
Kontextlimit und Laufzeit nicht vollständig berücksichtigt.

## Ursache

- Usage-Daten wurden nur beim finalen Agentenabschluss verarbeitet.
- `cacheRead` wurde nicht zum Kontextverbrauch addiert.
- Das Kontextfenster des aktiven Pi-Modells wurde nicht als `context_limit`
  übertragen.
- Laufzeit und Ausgaberate wurden nicht aus dem laufenden Agentenlauf berechnet.

## Lösung

Der Pi-Adapter wurde angepasst:

- Usage wird bei `message_update` höchstens einmal pro Sekunde übertragen.
- Nach jedem Modellturn wird ein zusätzliches Update gesendet.
- Input- und Cache-Input-Token werden für den Kontextverbrauch kombiniert.
- Das Modell-Kontextfenster wird als Kontextlimit übertragen.
- Laufzeit und Tok/s werden während des aktiven Runs berechnet.
- Der finale `agent_settled`-Datensatz bleibt weiterhin der einzige
  History-Eintrag pro Agentenlauf.

## Einschränkung

Einige Provider liefern Usage erst mit der finalen Antwort. In diesem Fall sind
exakte Tokenwerte, Kontextverbrauch und Tok/s während des Streams technisch
nicht verfügbar und bleiben bis dahin `n/a`. Eine Schätzung aus Antworttexten
wird bewusst nicht verwendet.

## Prüfung

- Python-Syntax und CLI-Pfade erfolgreich geprüft.
- Pi-Live-Update mit Kontextlimit, Kontextverbrauch und Tok/s per Mock getestet.
- Implementierung in Commit `b524dfe` enthalten.

## Reproduktion nach Aktivierung

1. `python3 llmtop.py` neu starten.
2. In Pi `/reload` ausführen.
3. Einen neuen Agentenlauf starten.
4. Während des Laufs den Bereich „Aktuelle Runs“ beobachten.
