"""Tests der Auswahlsuche im Spielstand.

Ob das Spiel die angebotenen Grundsteine wirklich im Zustand haelt, kann nur
ein echter Spielstand zeigen. Pruefbar ist hier, dass das Werkzeug ein
Angebot findet, wenn eines da ist -- und dass es nicht jede Liste im Baum
fuer eines haelt.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import find_choice                                            # noqa: E402


def zustand(angeboten: list[str], gewaehlt: list[str]) -> dict:
    return {
        "time": 1234.5,
        "difficulty": "Prestige 16 Ascension XIII",
        "effects": {
            "pickedEffects": gewaehlt,
            "currentOptions": angeboten,
        },
        "goods": {"[Food Raw] Meat": 40, "[Mat Raw] Wood": 120},
        "villagers": [
            {"name": "Beaver", "resolve": 12.0},
            {"name": "Human", "resolve": 9.5},
        ],
        "log": ["Jahr 1 begonnen", "Sturm ueberstanden"],
    }


def schreibe(pfad: Path, daten: dict) -> Path:
    pfad.write_text(json.dumps(daten), encoding="utf-8")
    return pfad


def test_listen_findet_nur_reine_bezeichnerlisten() -> None:
    daten = zustand(["Beanery", "Cellar"], [])
    gefunden = dict(find_choice.listen(daten))
    assert gefunden["effects.currentOptions"] == ["Beanery", "Cellar"]
    # Dictionaries mit Namensfeld zaehlen auch -- das Spiel fuehrt beides.
    assert gefunden["villagers"] == ["Beaver", "Human"]
    # Zahlen sind keine Bezeichner, Freitext faellt durch das Muster.
    assert "goods" not in gefunden


def test_pfadhinweis_und_bekannte_namen_heben_die_punktzahl() -> None:
    class Leer:
        def __bool__(self) -> bool:
            return False

        def auf(self, _):
            return None

    hoch, _, _ = find_choice.bewerte(
        "effects.currentOptions", ["Beanery", "Cellar", "Tavern"], Leer())
    niedrig, _, _ = find_choice.bewerte(
        "log.entries", ["Beanery", "Cellar", "Tavern"], Leer())
    assert hoch > niedrig


def test_scan_zeigt_das_angebot_zuoberst(tmp_path: Path, capsys) -> None:
    pfad = schreibe(tmp_path / "Save.save",
                    zustand(["Beanery", "Cellar", "Tavern"], ["Granary"]))
    assert find_choice.main(["scan", "--save", str(pfad), "--db",
                             str(tmp_path / "fehlt.sqlite")]) == 0
    ausgabe = capsys.readouterr().out
    erste = [z for z in ausgabe.splitlines() if z.startswith("[")][0]
    assert "effects.currentOptions" in erste


def test_diff_findet_angebot_und_wahl(tmp_path: Path, capsys) -> None:
    vorher = schreibe(tmp_path / "vorher.save",
                      zustand(["Beanery", "Cellar", "Tavern"], ["Granary"]))
    nachher = schreibe(tmp_path / "nachher.save",
                       zustand([], ["Granary", "Cellar"]))
    assert find_choice.main(["diff", "--before", str(vorher), "--after",
                             str(nachher), "--db", str(tmp_path / "fehlt.sqlite")]) == 0
    ausgabe = capsys.readouterr().out
    assert "Angebot und Wahl gefunden" in ausgabe
    assert "effects.currentOptions" in ausgabe
    assert "Cellar" in ausgabe.split("Gewaehlt:")[1]


def test_deutsche_namen_kommen_aus_der_wissensbasis(tmp_path: Path, capsys) -> None:
    from ats_assistant import kb, localization

    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    localization.import_localization(conn, [
        localization.Eintrag("Building_Beanery_Name", "Beanery", "Imbiss", "building"),
        localization.Eintrag("Building_Cellar_Name", "Cellar", "Weinkeller", "building"),
    ])
    conn.close()

    pfad = schreibe(tmp_path / "Save.save", zustand(["Beanery", "Cellar"], []))
    assert find_choice.main(["scan", "--save", str(pfad), "--db", str(db)]) == 0
    ausgabe = capsys.readouterr().out
    assert "Beanery = Imbiss" in ausgabe
    assert "Cellar = Weinkeller" in ausgabe


def test_find_zeigt_jede_stelle_mit_dem_namen(tmp_path: Path, capsys) -> None:
    """Die Gegenrichtung zu `scan`: nicht die Form suchen, sondern den Namen.

    `scan` sucht eine Gestalt und findet nichts, wenn die Gestalt anders
    ist -- und sagt dann nicht, warum. `find` nimmt einen Namen, von dem
    feststeht, dass er zur Wahl stand, und zeigt jede Fundstelle.
    """
    daten = zustand([], [])
    daten["reputationRewards"] = {
        "pending": {"slot1": {"effect": "Fungal Guide", "taken": False}},
    }
    pfad = schreibe(tmp_path / "Save.save", daten)
    assert find_choice.main(["find", "--save", str(pfad), "--term", "Fungal Guide",
                             "--db", str(tmp_path / "fehlt.sqlite")]) == 0
    ausgabe = capsys.readouterr().out
    assert "reputationRewards.pending.slot1.effect" in ausgabe


def test_find_sagt_klar_wenn_der_name_gar_nicht_vorkommt(tmp_path: Path, capsys) -> None:
    pfad = schreibe(tmp_path / "Save.save", zustand(["Beanery"], []))
    assert find_choice.main(["find", "--save", str(pfad), "--term", "Fungal Guide",
                             "--db", str(tmp_path / "fehlt.sqlite")]) == 0
    ausgabe = capsys.readouterr().out
    assert "Phase 3 braucht" in ausgabe        # die andere Antwort, aber eine
