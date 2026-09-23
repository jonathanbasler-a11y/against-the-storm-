"""Tests des Save-Parsers gegen einen nachgebauten Spielstand.

Die Struktur folgt dem, was Phase 0 im echten Spielstand gemessen hat:
Spieluhr `time`, Ungeduld `reputationPenalty`, `hostility` als Dictionary
(am 22.09.2026 im laufenden Spiel gesehen: level, points, sources),
`difficulty` als String, gestapelte Kategoriepraefixe, Zeitreihen unter
`trends`. Die Zahlen sind erfunden, die Form nicht.

Lager, Gebaeude und Lichtungen am 23.09.2026 mit `lage.py form` am
Spielrechner gemessen (1.10.4): das Lager unter `goods.goods.goods`, die
Gebaeude nach Art sortiert unter `buildings`, die Lichtungen mit
`wasDiscovered`. Vorher stand hier eine erfundene Form, und der Leser las
aus einem vollen Lagerhaus `lager: {}`.
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


def _auftrag(model: str, **felder) -> dict:
    """Ein Eintrag aus `orders.currentOrders` in der gemessenen Form."""
    eintrag = {
        "model": model, "tierModel": "Tier 1", "setIndex": 0, "seed": 1, "difficulty": 1,
        "id": 1, "picked": False, "seen": True, "tracked": False,
        "shouldBeFailable": False, "timeLeft": 0.0, "isFailed": False,
        "analyticsType": None, "rewards": [], "picks": [], "startTime": 0.0,
        "completedTime": 0.0, "started": False, "complied": False, "completed": False,
        "anyObjectiveTimed": False,
        "objectives": [{"type": 2, "amount": 3, "initTime": 0.0, "floatAmount": 0.0,
                        "completed": False, "canCount": True, "complying": False,
                        "complyTime": 0.0}],
    }
    eintrag.update(felder)
    return eintrag


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
        # Zwei Schluessel je Ware; welche, zeigte die Messung nicht --
        # `name`/`amount` wie bei `conditions.embarkGoods` im selben Save.
        "goods": {"goods": {"locks": [], "goods": [
            {"name": "[Food Raw] Meat", "amount": 42},
            {"name": "[Mat Processed] Planks", "amount": 14},
            {"name": "[SSE] [BIOME] Storm Penalty", "amount": 1},
        ]}},
        "buildings": {
            "houses": [{"model": "Beaver House", "residents": [1, 2, 3]}],
            "workshops": [
                {"model": "Smokehouse", "workers": [4, 5], "finished": True},
                {"model": "Bakery", "workers": [0, 0], "finished": False},
            ],
            "farms": [],
            "roads": [{"id": i, "model": "Road"} for i in range(38)],
            "goodsToBuildingsMap": {},
            "workplacesPerks": {"Main Storage (not-buildable)": []},
        },
        "world": {
            "glades": [{"model": "Glade", "wasDiscovered": i < 4} for i in range(9)],
            "naturalResources": [{"Key": {"x": i}, "Value": {"isActive": True}} for i in range(120)],
        },
        "trends": {
            "goodsCategoriesTrends": {"Food": [97.0] * 180, "Fuel": [20.0] * 180},
            "goodsTrends": {"[Crafting] Oil": [4.0] * 180},
        },
        "unbekanntes_feld": {"nichts": "davon faellt uns auf die Fuesse"},
        # Gemessen am 23.09.2026 (1.10.4) mit `lage.py form --pfad`.
        "gameObjectives": {"reputation": 0.07539226,
                           "reputationSources": [0.0, 0.0, 0.07539226, 0.0]},
        "actors": {"racesReputationGains": {"Beaver": 0.0, "Foxes": 0.07539226, "Frog": 0.0}},
        "content": {"buildings": ["Smokehouse", "Bakery", "Grill", "Beaver House"],
                    "essentialBuildings": ["Main Storage"] * 3},
        "orders": {"currentOrders": [
            _auftrag("Order A", picked=True, started=True, rewards=["Planks x10"]),
            _auftrag("Order B", picked=False, picks=[
                {"model": "Beaver Influx", "setIndex": 0, "firstSeenTime": 500.0,
                 "failed": False, "rewards": ["Villagers Beaver x5", "Planks x10", "Resin x15"]},
                {"model": "Beaver Colony", "setIndex": 1, "firstSeenTime": 500.0,
                 "failed": False, "rewards": ["Amber x40"]}]),
            _auftrag("Order C", picked=True, started=True, completed=True),
            _auftrag("Order D", picked=True, started=True, shouldBeFailable=True,
                     timeLeft=480.0, anyObjectiveTimed=True),
            _auftrag("Order E", picked=True, isFailed=True),
        ]},
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


# --------------------------------------------------------------------------
# Gefunden, aber nicht lesbar
#
# Am 22.09.2026 kam aus einem Spielstand mit vollem Lagerhaus `lager: {}`
# und `gebaeude: 0` -- ohne dass `nicht_gefunden` etwas meldete. Die Form
# `storage.goods` als Liste von Key/Value stammt aus einer Hypothese im
# Recherchedokument, gemessen wurde sie nie. Findet der Leser das Feld,
# kennt aber die Form nicht, darf er es nicht still leeren.
# --------------------------------------------------------------------------


def _note(notes, feld):
    return next(n for n in notes if n.field == feld)


def test_lager_in_fremder_form_wird_gemeldet_statt_geleert(tmp_path: Path) -> None:
    ordner = schreibe_buendel(tmp_path, save={"goods": {"goods": {
        "locks": [], "goods": {"[Food Raw] Meat": {"amount": 42}}}}})
    state, notes = read_state(ordner, wait=False)
    assert state.storage == {}
    note = _note(notes, "storage")
    assert note.how == "form_unbekannt"
    assert "amount" in note.form                      # die Form steht da ...
    assert "42" not in note.form                      # ... die Werte nicht


def test_ein_wirklich_leeres_lager_ist_kein_formfehler(tmp_path: Path) -> None:
    ordner = schreibe_buendel(tmp_path, save={"goods": {"goods": {"locks": [], "goods": []}}})
    _, notes = read_state(ordner, wait=False)
    assert _note(notes, "storage").how == "pfad"


def test_gebaeude_als_dictionary_nach_kennung(tmp_path: Path) -> None:
    ordner = schreibe_buendel(tmp_path, save={"buildings": {"buildings": {
        "17": {"model": "Smokehouse", "workers": 2, "finished": True},
        "18": {"model": "Bakery", "workers": 0, "finished": False}}}})
    state, notes = read_state(ordner, wait=False)
    assert [b.model for b in state.buildings] == ["Smokehouse", "Bakery"]
    assert _note(notes, "buildings").how == "pfad"


def test_gebaeude_in_fremder_form_werden_gemeldet(tmp_path: Path) -> None:
    ordner = schreibe_buendel(tmp_path, save={"buildings": {
        "houses": 6, "workshops": "zwei"}})
    state, notes = read_state(ordner, wait=False)
    assert state.buildings == []
    note = _note(notes, "buildings")
    assert note.how == "form_unbekannt" and "houses" in note.form


def test_die_gemessene_form_meldet_nichts(tmp_path: Path) -> None:
    _, notes = read_state(schreibe_buendel(tmp_path), wait=False)
    assert not [n for n in notes if n.how == "form_unbekannt"]


def test_formskizze_zeigt_schluessel_und_typen_aber_keine_werte() -> None:
    from ats_assistant.save_reader import form_skizze
    skizze = form_skizze({"goods": [{"Key": "[Food Raw] Meat", "Value": 42}],
                          "slots": 7, "name": "Hauptlager"})
    assert "goods" in skizze and "Key" in skizze and "Value" in skizze
    assert "int" in skizze and "str" in skizze
    for wert in ("42", "7", "Hauptlager", "Meat"):
        assert wert not in skizze


def test_formskizze_bleibt_kurz() -> None:
    from ats_assistant.save_reader import form_skizze
    riesig = {f"feld{i}": {"a": {"b": {"c": {"d": 1}}}} for i in range(500)}
    assert len(form_skizze(riesig)) < 400


def test_formbericht_nennt_pfad_und_kandidaten(tmp_path: Path) -> None:
    from ats_assistant.save_reader import formbericht
    ordner = schreibe_buendel(tmp_path, save={
        "goods": {"goods": {"goods": {"[Food Raw] Meat": {"amount": 42}}}},
        "mainStorage": {"storedGoods": [{"name": "[Food Raw] Meat", "amount": 42}]}})
    text = "\n".join(formbericht(ordner, wait=False))
    assert "storage" in text and "form_unbekannt" in text
    assert "$.goods.goods.goods" in text
    assert "storedGoods" in text                      # der Kandidat, den es wohl ist
    assert "42" not in text


# --------------------------------------------------------------------------
# Die gemessene Form (23.09.2026, `lage.py form` am Spielrechner)
# --------------------------------------------------------------------------


def test_das_lager_liegt_unter_goods_goods_goods(tmp_path: Path) -> None:
    state, notes = read_state(schreibe_buendel(tmp_path), wait=False)
    assert state.storage["Meat"] == 42 and state.storage["Planks"] == 14
    assert _note(notes, "storage").path == "$.goods.goods.goods"


def test_das_lager_greift_nicht_zum_lager_eines_sammlerlagers(tmp_path: Path) -> None:
    """Der Namensrueckfall nahm den flachsten Schluessel `goods` -- und im
    Save hat jedes Gebaeude sein eigenes `storage.goods`. Ein Sammlerlager
    mit vier Beeren ist nicht das Hauptlager."""
    ordner = schreibe_buendel(tmp_path, save={
        "goods": None,
        "camps": [{"storage": {"goods": [{"name": "[Food Raw] Berries", "amount": 4}]}}]})
    state, notes = read_state(ordner, wait=False)
    assert state.storage == {}
    assert _note(notes, "storage").how == "fehlt"


@pytest.mark.parametrize("eintrag", [
    {"name": "[Food Raw] Meat", "amount": 42},
    {"Key": "[Food Raw] Meat", "Value": 42},
    {"good": "[Food Raw] Meat", "count": 42},       # zwei Schluessel, andere Namen
])
def test_eine_ware_mit_zwei_schluesseln_wird_gelesen(tmp_path: Path, eintrag) -> None:
    """Die Messung zeigte je Ware zwei Schluessel, aber nicht welche. Ein
    Name und eine Zahl -- mehr braucht es nicht."""
    ordner = schreibe_buendel(tmp_path, save={"goods": {"goods": {"goods": [eintrag]}}})
    state, _ = read_state(ordner, wait=False)
    assert state.storage == {"Meat": 42}


def test_gebaeude_nach_art_ohne_strassen(tmp_path: Path) -> None:
    """38 Strassen sind keine 38 Gebaeude."""
    state, notes = read_state(schreibe_buendel(tmp_path), wait=False)
    assert sorted(b.model for b in state.buildings) == [
        "Bakery", "Beaver House", "Smokehouse"]
    assert _note(notes, "buildings").how == "pfad"
    smokehouse = next(b for b in state.buildings if b.model == "Smokehouse")
    assert smokehouse.workers == 2


def test_lichtungen_zaehlen_nur_entdeckte(tmp_path: Path) -> None:
    """42 Lichtungen nach 600 Sekunden waren die ganze Karte."""
    state, _ = read_state(schreibe_buendel(tmp_path), wait=False)
    assert state.glades == 4


def test_lichtungen_ohne_entdeckt_feld_zaehlen_alle(tmp_path: Path) -> None:
    ordner = schreibe_buendel(tmp_path, save={"world": {"glades": [{"id": 1}, {"id": 2}]}})
    state, _ = read_state(ordner, wait=False)
    assert state.glades == 2


def test_formbericht_sucht_nach_stichworten_in_allen_dateien(tmp_path: Path) -> None:
    """Für Aufträge, Ruf und Baupläne ist die Stelle im Spielstand nicht
    bekannt. Gesucht wird in allen drei Dateien -- wo sie liegen, weiß
    niemand, bevor gemessen ist."""
    from ats_assistant.save_reader import formbericht
    ordner = schreibe_buendel(tmp_path, save={
        "orders": {"orders": [{"model": "Order_A", "tasks": [{"progress": 3}],
                               "reward": {"reputation": 1.0}}]}})
    (ordner / "MetaSave.save").write_text(json.dumps({
        "unlockedBlueprints": ["Smokehouse"]}), encoding="utf-8")
    text = "\n".join(formbericht(ordner, wait=False, stichworte=("order", "blueprint")))
    assert "Save.save" in text and "$.orders" in text and "tasks" in text
    assert "MetaSave.save" in text and "unlockedBlueprints" in text
    assert "Order_A" not in text and "Smokehouse" not in text      # keine Werte
    assert "glades" not in text                                      # nur Gesuchtes


def test_stichwortsuche_mit_alle_zeigt_auch_den_rest(tmp_path: Path) -> None:
    """Am Spielrechner schnitt die Grenze von 30 Zeilen genau die Pfade ab,
    um die es ging: alphabetisch nach `$.effects` kamen `$.orders` und
    `$.reputation`."""
    from ats_assistant.save_reader import formbericht
    viele = {f"effects{i:02d}Order": 1 for i in range(40)}
    ordner = schreibe_buendel(tmp_path, save={**viele, "zzOrders": [{"model": "x"}]})
    kurz = "\n".join(formbericht(ordner, wait=False, stichworte=("order",)))
    lang = "\n".join(formbericht(ordner, wait=False, stichworte=("order",), grenze=None))
    assert "zzOrders" not in kurz and "weitere" in kurz
    assert "zzOrders" in lang and "weitere" not in lang


def test_ein_pfad_wird_ganz_gezeigt(tmp_path: Path) -> None:
    """Die Skizze zeigt sonst sechs Schlüssel je Knoten -- die gesuchten
    Baupläne können der siebte sein."""
    from ats_assistant.save_reader import formbericht
    inhalt = {f"feld{i}": [f"wert{i}"] for i in range(10)}
    ordner = schreibe_buendel(tmp_path, save={"content": inhalt})
    for pfad in ("$.content", "content"):              # PowerShell mag kein $
        text = "\n".join(formbericht(ordner, wait=False, pfad=pfad))
        assert "feld9" in text and "[1x str]" in text
        assert "wert" not in text


def test_ein_fehlender_pfad_ergibt_einen_satz(tmp_path: Path) -> None:
    from ats_assistant.save_reader import formbericht
    text = "\n".join(formbericht(schreibe_buendel(tmp_path), wait=False, pfad="gibtsnicht"))
    assert "nicht gefunden" in text.lower()


# --------------------------------------------------------------------------
# Ruf, Baupläne, Aufträge -- gemessen am 23.09.2026
# --------------------------------------------------------------------------


def test_ruf_je_quelle_und_je_volk(tmp_path: Path) -> None:
    state, _ = read_state(schreibe_buendel(tmp_path), wait=False)
    assert state.reputation_sources == [0.0, 0.0, 0.07539226, 0.0]
    assert state.reputation_by_race == {"Beaver": 0.0, "Foxes": 0.07539226, "Frog": 0.0}


def test_bauplaene_aus_content_buildings(tmp_path: Path) -> None:
    state, _ = read_state(schreibe_buendel(tmp_path), wait=False)
    assert state.blueprints == ["Smokehouse", "Bakery", "Grill", "Beaver House"]


def test_auftraege_in_der_gemessenen_form(tmp_path: Path) -> None:
    state, notes = read_state(schreibe_buendel(tmp_path), wait=False)
    assert [o["model"] for o in state.orders] == [
        "Order A", "Order B", "Order C", "Order D", "Order E"]
    assert state.orders[1]["picks"][0]["model"] == "Beaver Influx"
    assert _note(notes, "orders").how == "pfad"


def test_auftraege_in_fremder_form_werden_gemeldet(tmp_path: Path) -> None:
    ordner = schreibe_buendel(tmp_path, save={"orders": {"currentOrders": ["Order A"]}})
    state, notes = read_state(ordner, wait=False)
    assert state.orders == []
    assert _note(notes, "orders").how == "form_unbekannt"
