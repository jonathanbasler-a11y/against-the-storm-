"""Tests des Mitschreibers."""

from __future__ import annotations

import json
from pathlib import Path

from ats_assistant.save_reader import GameState
from ats_assistant.watcher import Mitschreiber, run_id_fuer


def buendel(pfad: Path, spielzeit: float, jahr: int = 5, biom: str = "Coral Forest") -> Path:
    pfad.mkdir(parents=True, exist_ok=True)
    (pfad / "Save.save").write_text(json.dumps({
        "time": spielzeit, "year": jahr, "season": 1,
        "reputation": 5.0, "reputationPenalty": 3.0,
    }), encoding="utf-8")
    (pfad / "MetaSave.save").write_text(json.dumps({
        "gameConditions": {"biome": biom, "difficulty": "Prestige 16 Ascension XIII"},
    }), encoding="utf-8")
    return pfad


def test_erster_zustand_wird_mitgeschrieben(tmp_path: Path) -> None:
    save = buendel(tmp_path / "save", 1000.0)
    mit = Mitschreiber(save, tmp_path / "runs")
    assert mit.einmal_lesen(wait=False) is not None
    assert mit.geschrieben == 1
    assert mit.run_id and "Coral_Forest" in mit.run_id


def test_gleiche_spielzeit_wird_nicht_doppelt_geschrieben(tmp_path: Path) -> None:
    """Eine Datei kann angefasst werden, ohne dass sich etwas ändert -- im
    Messlauf gab es Schreibvorgänge mit null Byte Unterschied."""
    save = buendel(tmp_path / "save", 1000.0)
    mit = Mitschreiber(save, tmp_path / "runs")
    mit.einmal_lesen(wait=False)
    assert mit.einmal_lesen(wait=False) is None
    assert mit.geschrieben == 1


def test_fortschreitende_spielzeit_wird_geschrieben(tmp_path: Path) -> None:
    save = buendel(tmp_path / "save", 1000.0)
    mit = Mitschreiber(save, tmp_path / "runs")
    mit.einmal_lesen(wait=False)
    buendel(save, 1300.0)
    assert mit.einmal_lesen(wait=False) is not None
    assert mit.geschrieben == 2
    zeilen = (tmp_path / "runs" / f"{mit.run_id}.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert [json.loads(z)["game_time"] for z in zeilen] == [1000.0, 1300.0]


def test_zurueckspringende_spielzeit_beginnt_einen_neuen_lauf(tmp_path: Path) -> None:
    """Nach einem gewonnenen Lauf folgt eine neue Siedlung -- die Spieluhr
    fängt wieder von vorn an und darf die alte Mitschrift nicht verlängern."""
    save = buendel(tmp_path / "save", 8000.0, biom="Coral Forest")
    mit = Mitschreiber(save, tmp_path / "runs")
    mit.einmal_lesen(wait=False)
    erster = mit.run_id

    buendel(save, 40.0, jahr=1, biom="Rocky Ravine")
    mit.einmal_lesen(wait=False)
    assert mit.run_id != erster
    assert "Rocky_Ravine" in mit.run_id


def test_unlesbarer_spielstand_wird_uebersprungen(tmp_path: Path) -> None:
    save = tmp_path / "save"
    save.mkdir()
    (save / "Save.save").write_text("{kaputt", encoding="utf-8")
    mit = Mitschreiber(save, tmp_path / "runs")
    assert mit.einmal_lesen(wait=False) is None
    assert mit.geschrieben == 0


def test_run_id_enthaelt_biom_und_stufe() -> None:
    state = GameState(captured_at="x", biome="Rocky Ravine", prestige=13)
    kennung = run_id_fuer(state)
    assert "Rocky_Ravine" in kennung and "p13" in kennung


def test_zwei_laeufe_am_selben_tag_bekommen_verschiedene_kennungen() -> None:
    """Sonst landen beide in einer Datei und die Spieluhr springt mittendrin
    zurück -- damit ist jede Auswertung über den Verlauf hinüber."""
    import time as _t
    state = GameState(captured_at="x", biome="Coral Forest", prestige=13)
    erste = run_id_fuer(state)
    _t.sleep(1.05)
    assert run_id_fuer(state) != erste
