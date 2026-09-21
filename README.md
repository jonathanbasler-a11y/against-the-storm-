# Against the Storm Assistant

Lokaler Spielassistent für *Against the Storm* 1.10.4 (deutsche Oberfläche,
Windows, Python 3.12). Er beobachtet und berät, er spielt nicht.

Der vollständige Entwurf steht in [SPEC.md](SPEC.md). Leitprinzip: das Sehen
passiert lokal und deterministisch, das Urteilen im Modell — es geht nie ein
Screenshot an ein Sprachmodell, nur kompaktes JSON.

## Stand

| Phase | Inhalt | Status |
|---|---|---|
| 0 | Machbarkeit: Save-Format, Schreibzeitpunkt, Sprache | Skript fertig, **Messung steht aus** |
| 1 | Wissensbasis `kb.sqlite` | offen |
| 2 | Save-Parser | offen |
| 3 | Bildschirmauslesung | offen |
| 4 | MCP-Server | offen |
| 5 | Entscheidungslogik `ats-advisor` | offen |

## Phase 0 ausführen

```powershell
python tools\phase0_diagnose.py all --minutes 10
```

Nur Standardbibliothek, keine Installation. Liest den Spielordner
ausschließlich, schreibt nur nach `diagnostics/`. Details und die
Entscheidungsvorlage: [docs/PHASE0.md](docs/PHASE0.md).

Selbsttest ohne echte Spielstände:

```bash
python tests/make_synthetic_saves.py /tmp/fake-saves
python tools/phase0_diagnose.py inspect --dir /tmp/fake-saves
```
