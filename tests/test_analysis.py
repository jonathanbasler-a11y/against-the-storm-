"""Tests der Laufauswertung."""

from __future__ import annotations

import json
from pathlib import Path

from ats_assistant import analysis


def lauf(won: bool, jahre: int, biom: str = "Coral Forest",
         grundsteine: list[str] | None = None, zeit: int = 0) -> dict:
    return {
        "hasWon": won, "years": jahre, "biome": biom, "endTimestamp": zeit,
        "difficulty": "Prestige 16 Ascension XIII",
        "cornerstones": grundsteine or [],
        "buildings": ["Smokehouse"] if won else ["Crude Workstation"],
    }


def test_wenige_laeufe_gelten_nicht_als_belastbar() -> None:
    """Aus zwei Siegen und einer Niederlage folgt nichts, und das muss dastehen."""
    v = analysis.compare_runs([lauf(True, 8), lauf(True, 9), lauf(False, 5)])
    assert v.belastbar is False
    assert v.hinweis is not None and "zu wenige" in v.hinweis.lower()
    assert "Hinweis, kein Befund" in analysis.summarise(v)


def test_genug_laeufe_gelten_als_belastbar() -> None:
    laeufe = [lauf(True, 8, zeit=i) for i in range(4)] + [lauf(False, 5, zeit=10 + i) for i in range(4)]
    v = analysis.compare_runs(laeufe)
    assert v.belastbar is True and v.hinweis is None
    assert v.jahre_sieg == 8 and v.jahre_niederlage == 5


def test_merkmale_zeigen_den_unterschied() -> None:
    laeufe = ([lauf(True, 8, grundsteine=["Baptism of Fire"], zeit=i) for i in range(4)]
              + [lauf(False, 5, grundsteine=["Cannibalism"], zeit=10 + i) for i in range(4)])
    v = analysis.compare_runs(laeufe)
    nach_name = {m.name: m for m in v.grundsteine}
    assert nach_name["Baptism of Fire"].differenz == 1.0     # nur in Siegen
    assert nach_name["Cannibalism"].differenz == -1.0        # nur in Niederlagen


def test_nur_die_letzten_n_laeufe() -> None:
    laeufe = [lauf(True, 8, zeit=i) for i in range(20)]
    assert analysis.compare_runs(laeufe, n=5).laeufe == 5


def test_nach_biom_und_schwierigkeit_aufgeschluesselt() -> None:
    laeufe = [lauf(True, 8, biom="Coral Forest", zeit=1),
              lauf(False, 4, biom="Rocky Ravine", zeit=2)]
    v = analysis.compare_runs(laeufe)
    assert v.nach_biom["Coral Forest"] == {"siege": 1, "niederlagen": 0}
    assert v.nach_biom["Rocky Ravine"] == {"siege": 0, "niederlagen": 1}


def test_kipppunkt_braucht_die_spieluhr() -> None:
    ohne = [{"year": 1}, {"year": 2}]
    assert analysis.tipping_point(ohne) is None


def test_kipppunkt_findet_den_zustand_davor() -> None:
    zustaende = [{"game_time": t, "reputation": t / 100} for t in (0, 100, 200, 300, 400)]
    treffer = analysis.tipping_point(zustaende, vorlauf_sekunden=120)
    assert treffer["game_time"] == 200          # 400 minus 120 ist 280, davor liegt 200
    assert treffer["_abstand_zum_ende"] == 200.0


def test_mitschrift_ueberspringt_kaputte_zeilen(tmp_path: Path) -> None:
    pfad = tmp_path / "lauf.jsonl"
    pfad.write_text('{"game_time": 1}\nkaputt\n\n{"game_time": 2}\n', encoding="utf-8")
    assert [z["game_time"] for z in analysis.read_run_log(pfad)] == [1, 2]


def test_fehlende_mitschrift_ergibt_leere_liste(tmp_path: Path) -> None:
    assert analysis.read_run_log(tmp_path / "gibtsnicht.jsonl") == []


def test_gemischte_zeitstempel_werfen_nicht() -> None:
    from ats_assistant.analysis import compare_runs
    compare_runs([{"hasWon": True, "endTimestamp": "2026-09-20"},
                  {"hasWon": False}, {"hasWon": True, "endTimestamp": 5}], n=2)


def test_zerrissene_zeile_in_der_mitschrift(tmp_path) -> None:
    """Fenster während des Schreibens geschlossen: die letzte Zeile endet
    mitten in einem Umlaut. Vorher fiel damit jede Vorhersage aus."""
    from ats_assistant.analysis import read_run_log
    datei = tmp_path / "lauf.jsonl"
    datei.write_bytes(b'{"game_time": 1}\n{"biome": "K\xc3')
    assert read_run_log(datei) == [{"game_time": 1}]


def test_zeilentrenner_im_text_zerreissen_die_notiz_nicht(tmp_path: Path) -> None:
    """`ensure_ascii=False` schreibt U+2028 und U+0085 roh; `splitlines()`
    trennte daran, und die Notiz ging in zwei unlesbaren Haelften verloren."""
    from ats_assistant import tools_api
    tools_api.log_event("Brennofen zweite Zeile\x85", tmp_path, run_id="lauf")
    eintraege = analysis.read_run_log(tmp_path / "lauf.jsonl")
    assert [e["text"] for e in eintraege] == ["Brennofen zweite Zeile\x85"]


def test_merkmale_ohne_liste_werfen_nicht() -> None:
    v = analysis.compare_runs([{"hasWon": True, "cornerstones": 3, "buildings": "Kiln"},
                               {"hasWon": False, "cornerstones": ["A"]},
                               {"hasWon": False, "cornerstones": ["A"]}], n=5)
    assert [m.name for m in v.grundsteine] == ["A"]
