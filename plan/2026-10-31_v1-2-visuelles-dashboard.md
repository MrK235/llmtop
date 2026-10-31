# v1.2 – Visuelles Terminal-Dashboard

## Abgrenzung
Die Version verändert ausschließlich das TUI-Layout und dessen Farben. API-
Abfragen, Sensorberechnung, CLI-Optionen, Tastatursteuerung und die `--once`-
Textausgabe bleiben unverändert. Es werden keine Abhängigkeiten ergänzt.

Eine projektlokale `AGENTS.md` ist **nicht erforderlich**: Die vorhandenen
übergeordneten Arbeitsregeln gelten bereits, und für diese klar abgegrenzte
Layout-Änderung wären zusätzliche Anweisungen redundant.

## Zielbild
Die Vollbild-TUI folgt dem Muster von htop/glances: kurze Statuskopfleiste,
darunter vier vertikal angeordnete, klar getrennte Bereiche mit einheitlichem
linken Rand und ruhiger Informationshierarchie:

```text
 otop 1.2.0  •  Ollama 0.x  •  verbunden                 [Intervall 2.0 s]
 ── System ─────────────────────────────────────────────────────────────────
 CPU   [████████░░░░░░░░░░░░]  42.1 %    Load 1.24    24 Kerne
 RAM   [██████░░░░░░░░░░░░░░]  28.7 %    21.7 / 30.5 GiB frei
 ── GPU ────────────────────────────────────────────────────────────────────
 GPU0  [████░░░░░░░░░░░░░░░░]  17 %      NVIDIA …  (nvidia-smi)
 VRAM  [████████████░░░░░░░░]  61.4 %    5000 / 8151 MiB
 Power [██████░░░░░░░░░░░░░░]  28.0 %    32.2 / 115 W
 ── Ollama ─────────────────────────────────────────────────────────────────
 qwen…  35.5B Q4_K_M  ctx 32768  llamacpp  unload in 19:36
 Speicher 5.1 GiB VRAM / 5.3 GiB gesamt  •  GPU 96 %  CPU 4 %
 ── History ────────────────────────────────────────────────────────────────
 Noch nicht verfügbar – Zeitreihen folgen in einer späteren Version.
 q quit  r refresh  h Hilfe  -/+ Intervall
```

Die konkreten Texte dürfen bei schmalen Terminals abgeschnitten werden; die
bestehende Mindestgröße 40×8 bleibt erhalten.

## Umsetzungsschritte

1. **TUI-Struktur in `otop.py` ordnen**
   - `_draw()` erhält kleine lokale Hilfsfunktionen zum Zeichnen einer
     Abschnittsüberschrift und einer Sensorzeile; keine neue Modulstruktur.
   - Reihenfolge stets: Kopfzeile → System → GPU → Ollama → History → Fußzeile.
   - Die vorhandenen Datenstrukturen (`state`, `gpus`, `models`) und alle
     Messfunktionen bleiben unverändert.
   - Der History-Bereich enthält ausschließlich den gedimmten Platzhalter;
     weder Speicherung noch Sampling oder neue Tasten werden eingeführt.

2. **Balken, Ausrichtung und Farben vereinheitlichen**
   - CPU, RAM, GPU-Auslastung, VRAM und Power verwenden dieselbe, aus der
     Terminalbreite abgeleitete Balkenbreite. Labels belegen eine feste Spalte,
     Prozentwerte sind rechtsbündig; Detailwerte folgen ab einer festen
     Textspalte.
   - Auslastungsbalken und Prozentwert verwenden die bestehende Ampelskala:
     grün unter 60 %, gelb ab 60 %, rot ab 85 %. Fehlt ein Wert, erscheinen
     leerer Balken und `n/a` gedimmt.
   - Abschnittsüberschriften und Kopfzeile sind Cyan/fett, normale Texte
     neutral, Quellen und sekundäre Informationen gedimmt. Der Text wird nicht
     allein über Farbe unterschieden.
   - Mehrere GPUs erhalten jeweils eine GPU-Zeile und die zugehörigen VRAM- /
     Power-Zeilen im selben Raster.

3. **Ollama- und Hilfe-Darstellung anpassen**
   - Ollama-Modelle werden unter ihrer Abschnittsüberschrift kompakt belassen;
     Verbindungs- und API-Fehler werden dort rot sichtbar, statt einen
     Modelleintrag vorzutäuschen.
   - Das bestehende Hilfe-Overlay bleibt funktional, erhält aber die neuen
     Begriffe für Bereiche und Farben nicht als zusätzliche Bedienfunktion.
   - Sind nicht alle Bereiche sichtbar, verhindert `_add()` weiterhin einen
     Absturz; System- und GPU-Werte stehen vor Modell- und History-Inhalten.

4. **Versions- und Projektdokumentation angleichen**
   - `VERSION` wird auf `1.2.0` gesetzt.
   - `README.md` beschreibt die vier TUI-Bereiche, die einheitlichen Balken und
     den nicht implementierten History-Platzhalter.
   - `status.md` dokumentiert Umfang, visuelle Prüfung und verbleibende Grenze
     bei kleinen Terminals.
   - `version.md` erhält den Changelog-Eintrag 1.2.0. Bestehende Funktionen
     werden nicht als neu dokumentiert.

## Betroffene Dateien
- `otop.py`
- `README.md`
- `status.md`
- `version.md`

## Prüfung
1. `python3 -m py_compile otop.py`, `--version` und `--once`: unveränderte
   Einzel-Snapshot-Funktion sicherstellen.
2. Pseudo-TTY mit 80×24 und 40×8: Reihenfolge und alle Bereichsüberschriften,
   einheitliche Balkenbreite, Hilfe-Overlay und fehlertolerantes Rendering
   prüfen.
3. Echter Terminaltest: NVIDIA- und `--no-nvidia`-/sysfs-Pfad auf Lesbarkeit,
   Farben und Ausrichtung prüfen.
