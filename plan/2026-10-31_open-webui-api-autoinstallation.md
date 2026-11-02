# Plan: Open-WebUI-Adapter vollständig über llmtop installieren

## Ziel

`llmtop` installiert und aktualisiert den Open-WebUI-Filter selbst über die vorhandene Open-WebUI-API. Nach einmaligem Start von `llmtop` sind weder Import noch Valves noch Modellzuordnung in der Open-WebUI-Oberfläche erforderlich.

## Befund

- Open WebUI läuft lokal unter `http://127.0.0.1:3000`, Version `0.12.3`.
- Die API ist erreichbar: `GET /api/version` liefert HTTP 200.
- Der relevante API-Endpunkt ist vorhanden: `POST /api/v1/functions/create`; Aktivierung und globale Aktivierung erfolgen über `POST /api/v1/functions/id/{id}/toggle` beziehungsweise `/toggle/global`.
- `GET /api/v1/functions/` liefert ohne Authentifizierung erwartungsgemäß HTTP 401.
- Die lokale Function-Tabelle ist leer; der Filter wurde noch nicht installiert.
- Weder die Projekt-`.env` (sie existiert derzeit nicht) noch `/home/kajetan/docker/ai/.env` enthalten einen Open-WebUI-Benutzer-API-Key. Dort liegen nur Infrastruktur-Secrets (`WEBUI_SECRET_KEY`, SearXNG- und Terminal-Secret).
- `WEBUI_SECRET_KEY` ist **kein** API-Key eines Open-WebUI-Administrators und kann die Functions-API nicht autorisieren. Ein API-Test mit Bearer-Token ist deshalb aktuell nicht möglich.

## Korrektur

### 1. Konfiguration ausschließlich in llmtop

`llmtop` verwendet eine lokale `.env` im Projekt oder explizite Umgebungsvariablen:

```dotenv
LLMTOP_COLLECTOR_TOKEN=<bestehender-langer-token>
OPEN_WEBUI_URL=http://127.0.0.1:3000
OPEN_WEBUI_API_KEY=<Admin-API-Key-aus-Open-WebUI>
```

- Der Wert wird ausschließlich aus der llmtop-Umgebung gelesen und nie ausgegeben, geloggt oder in die Function-Datei geschrieben.
- `.env.example` erhält nur die Variablennamen und Platzhalter.
- Der benötigte Key ist ein API-Key eines Open-WebUI-Administrators. Falls noch keiner existiert, muss er **einmalig** über Open WebUI erzeugt werden; das ist eine Berechtigungsgrenze der Open-WebUI-API, keine zusätzliche Laufzeitkonfiguration.

### 2. Privater Collector-Zugang ohne Open-WebUI-Konfiguration

`llmtop --collector` startet zusätzlich zum Loopback-Listener einen Listener auf der privaten Docker-Gateway-Adresse des Open-WebUI-Netzes.

- Die Gateway-Adresse wird für den bekannten Container `open-webui` über `docker inspect` ermittelt, nicht fest auf `172.18.0.1` kodiert.
- Der Listener bleibt auf genau diese private Gateway-IP begrenzt; kein `0.0.0.0`, keine Docker-Portfreigabe, keine Compose-Änderung.
- Der Adapter erhält über die API-Valves automatisch die ermittelte URL `http://<gateway>:11435` und den Collector-Token.
- Ist Docker oder Open WebUI nicht verfügbar, läuft der bisherige Loopback-Collector unverändert weiter; die zusätzliche Adresse wird nur als Hinweis protokolliert.

### 3. API-gesteuerte Installation

Ein neuer expliziter llmtop-Modus, beispielsweise `--install-open-webui-adapter`, führt diese Schritte idempotent aus:

1. `.env` laden, URL und Admin-API-Key prüfen.
2. `GET /api/v1/functions/id/llmtop_run_metrics` mit `Authorization: Bearer ...` prüfen.
3. Fehlt die Function: Filterquelle aus `open_webui/llmtop_run_metrics.py` mit `POST /api/v1/functions/create` anlegen.
4. Existiert sie: über `POST /api/v1/functions/id/llmtop_run_metrics/update` aktualisieren.
5. Valves über `POST /api/v1/functions/id/llmtop_run_metrics/valves/update` setzen:
   - ermittelte private Collector-URL,
   - Collector-Token,
   - Ollama-Service-URL aus Open-WebUI-Konfiguration, sofern über die API verfügbar, sonst `http://ollama:11434`.
6. Function aktivieren und global aktivieren, aber nur wenn der aktuelle API-Zustand dies noch nicht ist.
7. Nur IDs, HTTP-Status und nicht-geheime Endpunkte ausgeben; keine Secrets und keine Function-Inhalte loggen.

Der bisherige Filter bleibt datensparsam, nicht abschaltbar und fehlertolerant.

### 4. Tests

1. Ohne `OPEN_WEBUI_API_KEY`: klarer Exit-Code und Hinweis, keine API-Schreiboperation.
2. Mit ungültigem Key: erwartetes HTTP 401, keine Änderung.
3. Mit gültigem Admin-Key: Function anlegen, Valves setzen, aktiv/global schalten.
4. Zweiter identischer Lauf: Update ohne doppelte Function und ohne Toggle zurück auf inaktiv.
5. Collector aus Container erreichbar: ohne Bearer 401, mit Bearer 202.
6. Realer kurzer Open-WebUI-Ollama-Chat: genau ein `open-webui`-Start und ein finaler Historieneintrag; keine Prompt-/Antwortinhalte in JSONL.
7. Collector beenden: Open-WebUI-Chat bleibt funktionsfähig.

## Nicht Teil der Änderung

- Keine Änderung an `/home/kajetan/docker/ai/compose.yml`.
- Keine Portveröffentlichung oder externer Netzwerkzugang.
- Keine Datenbankdirektmanipulation in Open WebUI.
- Keine automatische Erzeugung eines Open-WebUI-Admin-Keys, da dies eine interaktive Admin-Anmeldung und eine explizite Berechtigungsentscheidung voraussetzt.

## Abnahme

Nach `python3 llmtop.py --collector` und `python3 llmtop.py --install-open-webui-adapter` ist der Filter über die Open-WebUI-API installiert, konfiguriert, aktiv und global. Ein Open-WebUI-Ollama-Chat wird ohne weitere Aktion in Open WebUI als Quelle `Open WebUI` in llmtop angezeigt.
