# Plan: Ollama-Bereich mit aktuellem Run, Kontextfenster und Tokenmetriken

## Auftrag

Den bisherigen Ollama-Bereich in zwei klar getrennte Teile aufteilen:

1. **Aktueller Run** – laufende Anfrage beziehungsweise zuletzt gemessener Run.
2. **Geladene Modelle** – Modelle aus `/api/ps` mit Speicher- und Offload-Daten.

Zusätzlich sollen Kontextfenster, Tokenanzahl und Tokenrate verständlich und
terminaltauglich visualisiert werden.

## Vorprüfung der verfügbaren Sensoren

### Live geprüft

- Ollama-Version: `0.40.6`
- `/api/ps`: verfügbar und liefert je Modell unter anderem:
  - `name`
  - `context_length`
  - `size`, `size_vram`
  - `expires_at`
  - `runner`
- `/metrics`: **404**, daher keine verwertbare Prometheus- oder laufende
  Request-Metrik verfügbar.

### Verfügbare Tokenmetriken der Ollama-Request-API

Die Endpunkte `/api/generate` und `/api/chat` liefern im abschließenden
Streaming-Objekt typischerweise:

- `prompt_eval_count`: Eingabetoken
- `eval_count`: erzeugte Token
- `prompt_eval_duration`: Zeit für die Eingabeauswertung
- `eval_duration`: Zeit für die Generierung
- `load_duration`: Modell-Ladezeit
- `total_duration`: Gesamtdauer

Daraus lassen sich nach Abschluss berechnen:

- **Gesamttoken:** `prompt_eval_count + eval_count`
- **Generierungsrate:** `eval_count / eval_duration`
- **Prompt-Rate:** `prompt_eval_count / prompt_eval_duration`
- **Gesamtrate:** Gesamttoken / relevante Gesamtdauer

### Wichtige Einschränkung

Ein passiver Client kann den aktuellen Run nicht zuverlässig aus `/api/ps`
ablesen. `/api/ps` beschreibt geladene Modelle, nicht aktive Requests. Die
Tokenwerte werden erst in der abschließenden Antwort des jeweiligen Requests
übermittelt. Für echte Live-Werte gibt es deshalb drei mögliche Quellen:

1. **Empfohlen:** Der Client, der `/api/chat` oder `/api/generate` aufruft,
   schreibt seine Streaming- und Abschlussmetriken in ein lokales Ereignis-
   format, das `otop` liest.
2. **Optional:** Ein lokaler, transparenter Ollama-Proxy beobachtet Requests
   und Streaming-Antworten. Das ist invasiver und muss Authentifizierung,
   Streaming und Fehlerfälle korrekt durchreichen.
3. **Nur Anzeige:** Ohne Instrumentierung zeigt `otop` `kein aktiver Run` und
   weiterhin das bekannte Kontextlimit aus `/api/ps`; erfundene Livewerte werden
   ausdrücklich vermieden.

Die aktuelle Ollama-Installation stellt keine zusätzliche Metrikquelle bereit.

## Visualisierungsskizze

Beispiel für einen ausreichend breiten Terminalbereich:

```text
Ollama  verbunden · 0.40.6

  Aktueller Run
  Modell       ministral-3:3b                 Status  läuft
  Kontext      [##########------]  10.2k / 32.8k Token   31.1 %
  Tokens       Prompt  2.1k · Ausgabe  8.1k · Gesamt 10.2k
  Rate         Ausgabe 42.5 Token/s · Prompt 310 Token/s
  Dauer        00:00:19 · letzte Messung vor 0.2 s

  Geladene Modelle (2)
  ministral-3:3b  3.8B Q4_K_M  ctx 32768  GPU 90 %  unload 26:19
    Speicher [##################--] GPU 90 % · 5.6 GiB / 6.2 GiB
  bge-m3:latest  566.70M F16  ctx 8192  GPU 7 %
    Speicher [##------------------] GPU 7 % · 88 MiB / 1.2 GiB
```

### Kontextbalken

- Balkenbreite identisch zu den bestehenden Sensorbalken.
- Grün bis 70 %, Gelb ab 70 %, Rot ab 90 %.
- Anzeige immer als `verbraucht / limit`.
- Wenn nur das Limit bekannt ist: leerer Balken mit `n/a` statt Schätzung.
- Wenn der Kontext überläuft oder die Quelle ungültig ist: auf 100 % begrenzen
  und Fehler-/Warnstatus sichtbar machen.

### Tokenzeilen

- `Prompt`, `Ausgabe` und `Gesamt` getrennt anzeigen, damit die Summe
  nachvollziehbar bleibt.
- Aktive Rate aus einem gleitenden Delta der Streamingdaten berechnen.
- Nach Abschluss die autoritativen Ollama-Werte verwenden.
- Fehlende Werte als `n/a`, niemals als `0` ausgeben.
- Bei mehreren parallelen Runs eine kurze Liste mit Run-ID und Modell anzeigen;
  in der ersten Umsetzung maximal ein aktiver Run plus Zähler für weitere.

## Geplante Datenstruktur

Das bestehende History-Ereignis wird um einen optionalen Run-Block erweitert:

```json
{
  "timestamp": "2026-10-31T14:30:00Z",
  "source": "otop",
  "run": {
    "id": "client-defined-id",
    "status": "running|completed|error|unknown",
    "model": "ministral-3:3b",
    "context_used": 10240,
    "context_limit": 32768,
    "prompt_tokens": 2100,
    "output_tokens": 8100,
    "total_tokens": 10200,
    "tokens_per_second": 42.5,
    "started_at": "...",
    "updated_at": "..."
  }
}
```

Regeln:

- `run` ist optional und darf bei rein passiver Überwachung fehlen.
- Keine Prompts, Antwortinhalte oder Tokens selbst speichern; nur Zähler und
  technische Metadaten.
- Run-IDs müssen aus der Quelle stammen oder lokal eindeutig erzeugt werden.
- Ein stale Run wird nach konfigurierbarer Zeit als `unknown` markiert.

## Umsetzung in Schritten

### Schritt 1 – Anzeige und Datenmodell ohne externe Integration

- Ollama-TUI in „Aktueller Run“ und „Geladene Modelle“ aufteilen.
- Kontextlimit aus `/api/ps` weiterhin bei jedem geladenen Modell anzeigen.
- Für den aktuellen Run zunächst den Zustand `nicht instrumentiert` sauber
  anzeigen; keine falschen Tokenwerte ableiten.
- Renderer für Kontextbalken, Tokenformatierung und Ampelgrenzen als reine
  Funktionen ergänzen.

### Schritt 2 – Lokale Run-Ereignisse

- Einen kleinen, dokumentierten JSONL-Eingang ergänzen, zunächst über eine
  Datei oder einen lokalen Unix-Socket.
- Ein optionales Hilfsmodul/CLI kann Streaming-Fortschritt und Abschlussmetriken
  aus Ollama-Responses in diesen Eingang schreiben.
- `otop` liest das letzte gültige Run-Ereignis, prüft Alter und Schema und zeigt
  bei Fehlern den letzten Zustand mit `stale` an.

### Schritt 3 – Client-Integration und Parallelität

- Adapter für den konkret eingesetzten LLM-Client definieren.
- Open WebUI, Pi und Strata nicht über angenommene private Endpunkte anbinden,
  sondern über explizite Adapter oder den gemeinsamen Ereigniseingang.
- Mehrere Runs mit begrenzter Liste, Quelle, Modell und Run-ID darstellen.
- Erst danach einen Proxy prüfen; Proxy-Betrieb bleibt optional.

## Abnahmekriterien

- Der Ollama-Bereich enthält sichtbar getrennte Blöcke für aktuellen Run und
  geladene Modelle.
- Ein nicht instrumentierter Run wird als unbekannt/nicht verfügbar angezeigt,
  nicht als „0 Token/s“.
- `/api/ps`-Kontextlimits werden korrekt und begrenzt visualisiert.
- Prompt-, Ausgabe- und Gesamttoken sowie Token/s werden bei einem gültigen
  Run-Ereignis korrekt berechnet und dargestellt.
- Stale, fehlerhafte oder unvollständige Run-Ereignisse führen nicht zum
  Absturz und überschreiben keine gültigen Modell-Sensoren.
- Bestehende GPU-, RAM-, History- und Ollama-Fehleranzeigen bleiben erhalten.
