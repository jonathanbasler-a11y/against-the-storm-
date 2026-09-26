# Against the Storm Assistant

Lokaler Spielassistent für *Against the Storm* 1.10.4 (deutsche Oberfläche,
Windows, Python 3.12). Er beobachtet und berät, er spielt nicht.

Der vollständige Entwurf steht in [SPEC.md](SPEC.md). Leitprinzip: das Sehen
passiert lokal und deterministisch, das Urteilen im Modell — es geht nie ein
Screenshot an ein Sprachmodell, nur kompaktes JSON.

## Einrichten

Von Null auf dem Spielrechner: **[docs/INSTALLATION.md](docs/INSTALLATION.md)**
— Python 3.12, Projekt holen, Wissensbasis bauen, Fenster starten, und was zu
tun ist, wenn etwas klemmt.

Kurzfassung für alle, die schon alles haben:

```powershell
git clone https://github.com/jonathanbasler-a11y/against-the-storm-.git
cd against-the-storm-
python -m pip install -e .
python tools\build_kb.py seed
python tools\build_kb.py namen --write
python ats-gui.pyw
```

Auffrischen mit `git fetch origin` und `git reset --hard origin/main` — **nicht**
mit `git pull`, die Arbeit kommt per Squash-Merge herein.

## Stand

| Phase | Inhalt | Status |
|---|---|---|
| 0 | Machbarkeit: Save-Format, Schreibzeitpunkt, Sprache | **beantwortet** |
| 1 | Wissensbasis `kb.sqlite` | **fertig**, soweit das Wiki trägt: 2273 Namen, 117 Gebäude, 398 Grundsteine, 193 Rezepte |
| 2 | Save-Parser und Mitschrift | **fertig** |
| 3 | Bildschirmauslesung | **fertig** für Auswahlbildschirme (Windows-Texterkennung über `winsdk`) |
| 4 | MCP-Server | **fertig**, acht Werkzeuge |
| 5 | Entscheidungslogik `ats-advisor` | **fertig**, wächst mit der Wissensbasis |
| — | Desktop-Fenster | **fertig**, fünf Reiter, siehe [docs/APP.md](docs/APP.md) |
| — | HUD über dem Spiel | **neu**: Engpass (Nahrung, Ungeduld, Pestfäule), Auswahl mit Tiers, Karten lesen mit Strg+Umschalt+L — siehe [docs/APP.md](docs/APP.md#das-hud-über-dem-spiel) |

## Im Betrieb

```powershell
python ats-gui.pyw   # das Fenster neben dem Spiel
python tools\verknuepfung.py   # einmalig: Verknüpfung auf Desktop und Startmenü
ats-watch            # läuft mit und schreibt jeden Zustand mit
ats-mcp              # MCP-Server für Claude Code
```

Befunde aus Phase 0 stehen in [docs/PHASE0.md](docs/PHASE0.md): der Spielstand
ist unkomprimiertes JSON mit englischen IDs, wird alle 300 Spielzeitsekunden
als Bündel aus vier Dateien geschrieben und trägt je Ware 180 Stützstellen
Vorgeschichte im Zehnsekundentakt.

## Phase 0 ausführen

```powershell
python tools\phase0_diagnose.py all --minutes 10
```

Nur Standardbibliothek, keine Installation. Liest den Spielordner
ausschließlich, schreibt nur nach `diagnostics/`. Details und die
Entscheidungsvorlage: [docs/PHASE0.md](docs/PHASE0.md).

Der Lauf prüft nebenbei die Behauptungen aus der beigelegten Recherche gegen
den echten Spielstand — Pfade, Kategoriepräfixe, Container, Zeilenzahl und
Schreibtakt. Bewertung der Recherche:
[docs/RESEARCH-REVIEW.md](docs/RESEARCH-REVIEW.md), daraus abgeleitetes
Rohmaterial: `data/name_map_seed.csv` (125 Paare, 109 davon unbestätigt).

Vor Phase 1 steht noch eine Frage: liefert der Spielstand selbst genug für
`kb.sqlite`, oder braucht es den Wiki-Scraper?

```powershell
python tools\kb_probe.py --dump-ids
```

Details: [docs/PHASE1-QUELLE.md](docs/PHASE1-QUELLE.md).

Selbsttest ohne echte Spielstände:

```bash
python tests/make_synthetic_saves.py /tmp/fake-saves
python tools/phase0_diagnose.py inspect --dir /tmp/fake-saves
```

## Tests

Das Projekt verlangt **Python 3.12** (`requires-python` in `pyproject.toml`).
`tests/test_laufzeit.py` besteht darauf: läuft die Suite auf einer älteren
Version, wird **dieser** Test rot statt alle anderen grün zu schweigen.

```
python -m pytest tests/ -q                 # ohne Anzeige: Fenstertests werden übersprungen
xvfb-run -a python -m pytest tests/ -q     # unter Linux mit echtem Tk
```

Die Fenstertests gibt es zweimal, mit Absicht:

| | |
|---|---|
| `test_gui.py` | mit eingesetztem tkinter — läuft überall, auch ohne Anzeige und ohne tcl/tk. Prüft die Verdrahtung: kommt jede Nachrichtenart an, wirft keine |
| `test_gui_echt.py` | mit echtem Tk unter `xvfb-run`. Prüft, was ein Stub nicht kann: ob `ttk` jede Option annimmt, ob die Rasteraufteilung aufgeht, ob nach dem Anzeigen auch etwas dasteht |

Der Stub-Test räumt am Ende nicht nur aus `sys.modules` auf, sondern auch das
Attribut am Paket — sonst prüfte die echte Fassung in Wahrheit dieselben
Attrappen und wäre grün, ohne etwas zu zeigen. Genau das war einmal der Fall.
