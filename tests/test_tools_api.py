"""Tests der Werkzeuge aus Phase 4 -- ohne MCP, damit sie testbar bleiben."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ats_assistant import kb, tools_api
from ats_assistant.mcp_server import werkzeuge


def buendel(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    save = {
        "time": 8746.9, "year": 13, "season": 0,
        "hostility": {"current": 180},
        "reputation": 18.0, "reputationToWin": 18,
        "reputationPenalty": 6.6, "reputationPenaltyToLoose": 14,
        "reputationPenaltyPerSec": 0.00425,
        "storage": {"goods": [{"Key": "[Food Raw] Meat", "Value": 42}]},
        "trends": {"goodsCategoriesTrends": {"Food": [97.0] * 180}},
    }
    meta = {
        "gameConditions": {"biome": "Coral Forest", "difficulty": "Prestige 16 Ascension XIII",
                           "races": ["Human", "Beaver"]},
        "reputationPenaltyBonusRate": -0.4,
        "gamesHistory": {"records": [
            {"hasWon": True, "years": 8, "biome": "Coral Forest", "endTimestamp": i,
             "cornerstones": ["Baptism of Fire"]} for i in range(4)
        ] + [
            {"hasWon": False, "years": 5, "biome": "Coral Forest", "endTimestamp": 10 + i,
             "cornerstones": ["Cannibalism"]} for i in range(4)
        ]},
    }
    world = {"population": 13}
    for name, inhalt in (("Save.save", save), ("MetaSave.save", meta), ("WorldSave.save", world)):
        (tmp_path / name).write_text(json.dumps(inhalt), encoding="utf-8")
    return tmp_path


def test_get_state_liefert_zahlen_und_namen_ohne_zeitreihen(tmp_path: Path) -> None:
    """Die Reihen haben 180 Stützstellen je Ware. Die gehören nicht ins Modell."""
    save_dir = buendel(tmp_path / "save")
    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    assert out["jahr"] == 13 and out["biom"] == "Coral Forest"
    assert out["prestige"] == 13 and out["prestige_roh"] == "Prestige 16 Ascension XIII"
    assert out["lager"] == {"Meat": 42}
    assert out["gewonnen"] is True
    assert "category_trends" not in json.dumps(out)
    assert out["reihen_vorhanden"] == ["Food"]        # nur die Namen, nicht die Werte


def test_get_state_schreibt_die_mitschrift(tmp_path: Path) -> None:
    save_dir = buendel(tmp_path / "save")
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, run_id="testlauf", auf_ruhe_warten=False)
    zeilen = (runs / "testlauf.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(zeilen) == 1 and json.loads(zeilen[0])["year"] == 13


def test_food_forecast_braucht_zwei_spielstaende(tmp_path: Path) -> None:
    save_dir = buendel(tmp_path / "save")
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, run_id="lauf", auf_ruhe_warten=False)
    out = tools_api.food_forecast(runs, run_id="lauf")
    assert out["verfuegbar"] is False and "zwei Spielstände" in out["grund"]


def test_food_forecast_rechnet_mit_zwei_spielstaenden(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    vorher = {"game_time": 1000.0, "category_trends": {"Food": [0.0] * 180}}
    reihe = [0.0] * 180
    reihe[40:70] = [100.0 - 2 * i for i in range(30)]
    nachher = {"game_time": 1300.0, "category_trends": {"Food": reihe}}
    with (runs / "lauf.jsonl").open("w", encoding="utf-8") as fh:
        for z in (vorher, nachher):
            fh.write(json.dumps(z) + "\n")
    out = tools_api.food_forecast(runs, run_id="lauf", jahreszeit_sekunden=180.0)
    assert out["verfuegbar"] is True
    assert out["rate_je_spielzeitsekunde"] == pytest.approx(-0.2)
    assert out["reichweite_sekunden"] == pytest.approx(210.0)


def test_impatience_forecast_aus_der_mitschrift(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "lauf.jsonl").write_text(json.dumps({
        "game_time": 1000.0, "impatience": 13.9, "impatience_to_lose": 14.0,
        "impatience_per_second": 0.00425, "impatience_bonus_rate": -0.4,
    }) + "\n", encoding="utf-8")
    out = tools_api.impatience_forecast(runs, run_id="lauf")
    assert out["verfuegbar"] is True
    assert out["sekunden_bis_verlust"] == pytest.approx(0.1 / 0.00255, rel=1e-6)
    assert "Schwelle" in out["warnung"]


def test_log_event_haengt_an_die_mitschrift(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    out = tools_api.log_event("Erste gefährliche Lichtung geöffnet", runs, run_id="lauf")
    assert out["eintrag"]["typ"] == "notiz"
    assert "Lichtung" in (runs / "lauf.jsonl").read_text(encoding="utf-8")


def test_notizen_stoeren_die_vorhersage_nicht(tmp_path: Path) -> None:
    """Eine Freitextnotiz in derselben Datei darf nicht als Zustand gelesen werden."""
    runs = tmp_path / "runs"
    runs.mkdir()
    with (runs / "lauf.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"game_time": 1000.0, "impatience": 5.0,
                             "impatience_per_second": 0.00425}) + "\n")
    tools_api.log_event("Notiz", runs, run_id="lauf")
    out = tools_api.impatience_forecast(runs, run_id="lauf")
    assert out["jetzt"] == 5.0


def test_analyze_runs_liest_die_laufhistorie(tmp_path: Path) -> None:
    save_dir = buendel(tmp_path / "save")
    out = tools_api.analyze_runs(10, save_dir, tmp_path / "runs")
    assert out["verfuegbar"] is True and out["siege"] == 4 and out["niederlagen"] == 4
    assert out["belastbar"] is True
    namen = [m["name"] for m in out["grundsteine"]]
    assert "Baptism of Fire" in namen


def test_analyze_runs_ohne_historie(tmp_path: Path) -> None:
    out = tools_api.analyze_runs(10, tmp_path, tmp_path / "runs")
    assert out["verfuegbar"] is False and "gamesHistory" in out["grund"]


def test_query_kb_nimmt_deutsch_und_englisch(tmp_path: Path) -> None:
    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    kb.import_goods(conn, [{"page_name": "Jerky", "m_Name": "[Food Processed] Jerky",
                            "eatable": "1", "eatingFullness": "2"}])
    conn.execute("INSERT INTO name_map (en, de, kind, confidence) VALUES (?,?,?,?)",
                 ("Jerky", "Dörrfleisch", "resource", "guessed"))
    conn.commit()
    conn.close()

    aus_de = tools_api.query_kb("Dörrfleisch", db=db)
    assert aus_de["ware"]["save_id"] == "[Food Processed] Jerky"
    assert aus_de["ware"]["eating_fullness"] == 2.0
    aus_save_id = tools_api.query_kb("[Food Processed] Jerky", db=db)
    assert aus_save_id["ware"]["en"] == "Jerky"


def test_query_kb_sagt_wenn_nichts_da_ist(tmp_path: Path) -> None:
    out = tools_api.query_kb("Gibtsnicht", db=tmp_path / "kb.sqlite")
    assert "hinweis" in out


def test_read_choice_sagt_klar_dass_phase_3_fehlt() -> None:
    """Und nennt den Weg, auf dem sich klaeren laesst, was Phase 3 braucht."""
    out = tools_api.read_choice()
    assert out["verfuegbar"] is False and "Phase 3" in out["grund"]
    assert "find_choice.py" in out["grund"]


def test_werkzeugliste_entspricht_der_spec(tmp_path: Path) -> None:
    namen = {w["name"] for w in werkzeuge(tmp_path, tmp_path, tmp_path / "kb.sqlite")}
    assert {"get_state", "read_choice", "query_kb", "food_forecast",
            "log_event", "analyze_runs"} <= namen


def test_jedes_werkzeug_hat_ein_schema(tmp_path: Path) -> None:
    for w in werkzeuge(tmp_path, tmp_path, tmp_path / "kb.sqlite"):
        assert w["inputSchema"]["type"] == "object"
        assert w["description"]
