"""Tests des Save-Parsers gegen einen nachgebauten Spielstand.

Die Struktur folgt dem, was Phase 0 im echten Spielstand gemessen hat:
Spieluhr `time`, Ungeduld `reputationPenalty`, `hostility` als Dictionary
(am 22.09.2026 im laufenden Spiel gesehen: level, points, sources),
`difficulty` als String, gestapelte Kategoriepraefixe, Zeitreihen unter
`trends`. Die Zahlen sind erfunden, die Form nicht.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ats_assistant.paths import index_keys, resolve, strip_prefixes
from ats_assistant.save_reader import (
    GameState,
    append_run_log,
    parse_prestige,
    read_state,
)


def schreibe_buendel(tmp_path: Path, **abweichungen) -> Path:
    save = {
        "time": 8746.994,
        "year": 13,
        "season": 0,
        "hostility": {"level": 3, "points": 72, "sources": {}},
        "reputation": 18.0,
        "reputationToWin": 18,
        "reputationPenalty": 6.636307,
        "reputationPenaltyToLoose": 14,
        "reputationPenaltyPerSec": 0.00425,
        "storage": {"goods": [
            {"Key": "[Food Raw] Meat", "Value": 42},
            {"Key": "[Mat Processed] Planks", "Value": 14},
            {"Key": "[SSE] [BIOME] Storm Penalty", "Value": 1},
        ]},
        "buildings": {"buildings": [
            {"model": "Smokehouse", "workers": 2, "finished": True},
            {"model": "Bakery", "workers": 0, "finished": False},
        ]},
        "world": {
            "glades": [{"id": i} for i in range(9)],
            "naturalResources": [{"Key": {"x": i}, "Value": {"isActive": True}} for i in range(120)],
        },
        "trends": {
            "goodsCategoriesTrends": {"Food": [97.0] * 180, "Fuel": [20.0] * 180},
            "goodsTrends": {"[Crafting] Oil": [4.0] * 180},
        },
        "unbekanntes_feld": {"nichts": "davon faellt uns auf die Fuesse"},
    }
    meta = {
        "gameConditions": {
            "biome": "Coral Forest",
            "difficulty": "Prestige 16 Ascension XIII",
            "races": ["Human", "Beaver", "Lizard"],
        },
        "reputationPenaltyBonusRate": -0.400000036,
        "gameplay": {"playedWorldEffects": ["[Map Mod] No Control", "[BIOME] Giant Organisms"]},
    }
    world = {"cycle": {"year": 39}, "population": 13, "wonFieldPopulation": 31}

    save.update(abweichungen.get("save", {}))
    for name, inhalt in (("Save.save", save), ("MetaSave.save", meta), ("WorldSave.save", world)):
        if name in abweichungen.get("weglassen", ()):
            continue
        (tmp_path / name).write_text(json.dumps(inhalt), encoding="utf-8")
    return tmp_path


def test_liest_die_gemessenen_felder(tmp_path: Path) -> None:
    state, _ = read_state(schreibe_buendel(tmp_path), wait=False)
    assert state.game_time == pytest.approx(8746.994)
    assert state.year == 13 and state.season == 0
    assert state.biome == "Coral Forest"
    assert state.impatience == pytest.approx(6.636307)
    assert state.impatience_to_lose == 14
    assert state.impatience_bonus_rate == pytest.approx(-0.4, abs=1e-6)
    assert state.reputation == 18.0
    assert isinstance(state.hostility, dict)
    assert state.population == 13
    assert state.species == ["Human", "Beaver", "Lizard"]


def test_prestige_kommt_als_string_und_wird_zur_stufe(tmp_path: Path) -> None:
    state, _ = read_state(schreibe_buendel(tmp_path), wait=False)
    assert state.prestige_raw == "Prestige 16 Ascension XIII"
    assert state.prestige == 13


@pytest.mark.parametrize("roh,erwartet", [
    ("Prestige 16 Ascension XIII", 13),
    ("Ascension VII", 7),
    ("Prestige 13", 13),
    (13, 13),
    ("Adept", None),
    (None, None),
])
def test_prestige_stufen(roh, erwartet) -> None:
    assert parse_prestige(roh) == erwartet


def test_kategoriepraefixe_werden_geschleift(tmp_path: Path) -> None:
    state, _ = read_state(schreibe_buendel(tmp_path), wait=False)
    # Ein einmaliges Abschneiden liesse "[BIOME] Storm Penalty" stehen.
    assert "Storm Penalty" in state.storage
    assert not any(name.startswith("[") for name in state.storage)
    assert state.storage["Meat"] == 42


def test_zeitreihen_landen_im_zustand(tmp_path: Path) -> None:
    state, _ = read_state(schreibe_buendel(tmp_path), wait=False)
    assert len(state.category_trends["Food"]) == 180
    assert "Oil" in state.goods_trends      # Praefix abgeschnitten


def test_sieg_und_niederlage_sind_ablesbar(tmp_path: Path) -> None:
    state, _ = read_state(schreibe_buendel(tmp_path), wait=False)
    assert state.won is True      # Reputation 18 von 18
    assert state.lost is False    # Ungeduld 6,6 von 14


def test_fehlende_dateien_ergeben_none_statt_abbruch(tmp_path: Path) -> None:
    pfad = schreibe_buendel(tmp_path, weglassen=("WorldSave.save", "MetaSave.save"))
    state, notes = read_state(pfad, wait=False)
    assert state.game_time is not None      # Save.save war da
    assert state.biome is None and state.population is None
    assert any(n.how == "fehlt" for n in notes) or all(n.field != "biome" for n in notes)


def test_kaputtes_json_bricht_nicht_ab(tmp_path: Path) -> None:
    pfad = schreibe_buendel(tmp_path)
    (pfad / "Save.save").write_text('{"time": 1.0, "year":', encoding="utf-8")
    state, _ = read_state(pfad, wait=False)
    assert state.game_time is None
    assert state.biome == "Coral Forest"    # die anderen Dateien tragen weiter


def test_leeres_verzeichnis_bricht_nicht_ab(tmp_path: Path) -> None:
    state, _ = read_state(tmp_path, wait=False)
    assert isinstance(state, GameState) and state.game_time is None


def test_feldherkunft_wird_protokolliert(tmp_path: Path) -> None:
    _, notes = read_state(schreibe_buendel(tmp_path), wait=False)
    herkunft = {n.field: n for n in notes}
    assert herkunft["game_time"].how == "pfad"        # time steht an der Wurzel
    assert herkunft["impatience"].how == "suche"      # Pfad unbekannt, Name bekannt
    assert herkunft["impatience"].path.endswith("reputationPenalty")


def test_lauf_protokoll_haengt_zeilen_an(tmp_path: Path) -> None:
    state, _ = read_state(schreibe_buendel(tmp_path), wait=False)
    ziel = append_run_log(state, "testlauf", runs_dir=tmp_path / "runs")
    append_run_log(state, "testlauf", runs_dir=tmp_path / "runs")
    zeilen = ziel.read_text(encoding="utf-8").strip().splitlines()
    assert len(zeilen) == 2
    assert json.loads(zeilen[0])["year"] == 13


def test_flachster_fund_gewinnt() -> None:
    """Ein 'season' tief in einer Vorlage darf den geführten Wert nicht verdecken."""
    data = {"vorlagen": {"a": {"b": {"c": {"season": 0}}}}, "welt": {"season": 2}}
    idx = index_keys(data)
    wert, note = resolve(data, idx, "season", (), ("season",), int)
    assert wert == 2 and note.path == "$.welt.season"


def test_praefixe_stapeln_sich() -> None:
    assert strip_prefixes("[SSE] [BIOME] Storm Penalty") == ("Storm Penalty", ["SSE", "BIOME"])
    assert strip_prefixes("Hearth Parts") == ("Hearth Parts", [])
