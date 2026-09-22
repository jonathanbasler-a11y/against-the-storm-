"""Die Fehlerrunde vor der Oberfläche.

Drei Fehler, die beim Planen aufgefallen sind — alle drei unsichtbar für die
187 Tests, die es vorher gab. Jeder bekommt hier zuerst einen Test, der ihn
zeigt.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ats_assistant import mcp_server, screen


# --------------------------------------------------------------------------
# 1. asyncio.run in einer laufenden Schleife
# --------------------------------------------------------------------------


def test_erkennung_laeuft_auch_in_einer_laufenden_schleife() -> None:
    """`read_choice` läuft unter MCP in einer Ereignisschleife.

    `asyncio.run()` wirft dort `RuntimeError: cannot be called from a running
    event loop`. Der Prüflauf hat es nicht gemerkt, weil er die Texterkennung
    mit `text=[...]` überspringt — genau der Pfad, den die Prüfung nicht
    erreicht, war der kaputte.
    """
    async def arbeit() -> str:
        await asyncio.sleep(0)
        return "gelesen"

    # Ohne laufende Schleife: der einfache Weg.
    assert screen.im_eigenen_lauf(arbeit) == "gelesen"

    # Mit laufender Schleife: früher RuntimeError, jetzt ein eigener Thread.
    async def unter_mcp() -> str:
        return screen.im_eigenen_lauf(arbeit)

    assert asyncio.run(unter_mcp()) == "gelesen"


def test_fehler_aus_der_erkennung_gehen_nicht_verloren() -> None:
    """Ein Fehler im Thread darf nicht stillschweigend zu None werden."""
    async def scheitert():
        raise RuntimeError("keine Sprache installiert")

    async def unter_mcp():
        return screen.im_eigenen_lauf(scheitert)

    with pytest.raises(RuntimeError, match="keine Sprache"):
        asyncio.run(unter_mcp())


# --------------------------------------------------------------------------
# 2. Fehlerabsicherung auf beiden MCP-Wegen
# --------------------------------------------------------------------------


def test_ein_scheiterndes_werkzeug_beendet_den_server_nicht() -> None:
    """Der alte Weg fing jeden Werkzeugfehler ab, der neue nicht.

    Zwei Wege, eine Absicherung — sonst hängt es vom Zufall der installierten
    MCP-Fassung ab, ob ein Fehler eine Antwort oder einen Abbruch ergibt.
    """
    werkzeug = {
        "name": "kaputt",
        "description": "wirft immer",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": lambda **kw: (_ for _ in ()).throw(ValueError("kaputtgegangen")),
    }
    ergebnis = mcp_server.funktion_aus_schema(werkzeug)()
    assert isinstance(ergebnis, dict)
    assert "kaputtgegangen" in ergebnis["fehler"]
    assert ergebnis["werkzeug"] == "kaputt"


# --------------------------------------------------------------------------
# 3. Der Prüflauf schreibt nicht
# --------------------------------------------------------------------------


def test_pruefen_legt_keine_mitschrift_an(tmp_path: Path) -> None:
    """`log_event` wird übersprungen, weil es schreibt — `get_state` schrieb
    trotzdem. Das erklärte auch, warum im Prüflauf "0 Mitschriften" stand und
    `impatience_forecast` danach grün war.
    """
    import json

    save_dir = tmp_path / "save"
    save_dir.mkdir()
    (save_dir / "Save.save").write_text(
        json.dumps({"time": 100.0, "year": 1, "storage": {"goods": []}}),
        encoding="utf-8")
    runs = tmp_path / "runs"

    mcp_server.main(["--pruefen", "--save-dir", str(save_dir),
                     "--runs-dir", str(runs), "--db", str(tmp_path / "kb.sqlite")])
    assert list(runs.glob("*.jsonl")) == []


# --------------------------------------------------------------------------
# 4. tools_api als Wall
# --------------------------------------------------------------------------


def test_jedes_werkzeug_liefert_ein_dictionary_statt_zu_werfen(tmp_path: Path) -> None:
    """Drei Aufrufer, eine Zusage.

    MCP, Kommandozeile und Fenster rufen dieselben Funktionen. Wer wirft,
    reisst den Aufrufer mit -- beim Fenster einen toten Arbeits-Thread und
    eine Oberfläche, die stehenbleibt, ohne zu sagen warum.
    """
    from ats_assistant import tools_api

    # Eine Wissensbasis, die keine ist: die Datei ist kein SQLite.
    kaputt = tmp_path / "kb.sqlite"
    kaputt.write_bytes(b"das ist keine Datenbank")

    out = tools_api.query_kb("Holz", db=kaputt)
    assert isinstance(out, dict)
    assert out["verfuegbar"] is False
    assert out["werkzeug"] == "query_kb"
    assert "fehler" in out


def test_die_wall_laesst_erfolgreiche_antworten_unveraendert(tmp_path: Path) -> None:
    from ats_assistant import kb, tools_api

    db = tmp_path / "kb.sqlite"
    kb.connect(db).close()
    out = tools_api.query_kb("Gibtsnicht", db=db)
    assert "fehler" not in out          # kein Treffer ist kein Fehler
    assert out["gesucht"] == "Gibtsnicht"


# --------------------------------------------------------------------------
# 5. Ein Lauf ohne Ausgang ist keine Niederlage
# --------------------------------------------------------------------------


def test_laeufe_ohne_ausgang_zaehlen_nicht_als_niederlage() -> None:
    """Sonst verschiebt sich jeder Vergleich in dieselbe Richtung, lautlos."""
    from ats_assistant import analysis

    vergleich = analysis.compare_runs([
        {"hasWon": True, "years": 8, "biome": "Coastal Grove"},
        {"hasWon": False, "years": 5, "biome": "Coastal Grove"},
        {"years": 3},                      # abgebrochen, kein Ausgang verzeichnet
        {},                                # leerer Eintrag
    ])
    assert vergleich.siege == 1
    assert vergleich.niederlagen == 1      # nicht 3
    assert vergleich.laeufe == 4
    assert "ohne verzeichneten Ausgang" in vergleich.hinweis
