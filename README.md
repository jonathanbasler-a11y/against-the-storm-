# Against the Storm Assistant

Lokaler Spielassistent für *Against the Storm* 1.10.4 (deutsche Oberfläche,
Windows, Python 3.12). Er beobachtet und berät, er spielt nicht.

Der vollständige Entwurf steht in [SPEC.md](SPEC.md). Leitprinzip: das Sehen
passiert lokal und deterministisch, das Urteilen im Modell — es geht nie ein
Screenshot an ein Sprachmodell, nur kompaktes JSON.

## Stand

| Phase | Inhalt | Status |
|---|---|---|
| 0 | Machbarkeit: Save-Format, Schreibzeitpunkt, Sprache | **beantwortet** |
| 1 | Wissensbasis `kb.sqlite` | Waren vollständig, Grundsteine und Rezepte offen |
| 2 | Save-Parser und Mitschrift | **fertig** |
| 3 | Bildschirmauslesung | offen — nur noch Auswahlbildschirme |
| 4 | MCP-Server | **fertig** bis auf `read_choice` |
| 5 | Entscheidungslogik `ats-advisor` | **fertig**, wächst mit der Wissensbasis |

## Im Betrieb

```powershell
uv run ats-watch     # läuft mit und schreibt jeden Zustand mit
uv run ats-mcp       # MCP-Server für Claude Code
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
