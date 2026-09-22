"""Tests der Wiki-Auswertung gegen echte Vorlagenaufrufe aus dem Abzug.

Die Beispiele stammen wörtlich aus `build_kb.py detail` über den Abzug vom
21.09.2026 -- also aus dem echten Wiki, nicht aus einer Annahme darüber.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from build_kb import scan_templates, split_params, template_params  # noqa: E402

from ats_assistant import kb  # noqa: E402


ECHTER_GOODS_AUFRUF = (
    "Dataloader/Goods|page_name=Boots|guid=36425b65ac477dd46bda2394898d4226"
    "|m_Script=558a9e34328cfee034f2e66a4ea42621|m_Name=[Needs] Boots"
    "|category=01f4563332ee590428e448ac985519ca|displayName_key=Good_Boots_Name"
    "|displayName_key_en=Boots|eatable=0|eatingFullness=0|canBeBurned=0"
    "|tradingSellValue=5|tradingBuyValue=10"
)


def test_verschachtelte_vorlagen_werden_nicht_zerschnitten() -> None:
    """{{Recipe|{{rl|Wood}}|5}} enthält geschweifte Klammern. Wer beim ersten
    `}}` aufhört, schneidet mitten im Parameter."""
    text = "{{Buildingbox|Smokehouse|cost={{Construction|Planks=10|Bricks=5}}|workers=3}}"
    vorlagen = dict(scan_templates(text))
    assert "Buildingbox" in vorlagen and "Construction" in vorlagen
    params = template_params(vorlagen["Buildingbox"])
    assert params["cost"] == "{{Construction|Planks=10|Bricks=5}}"
    assert params["workers"] == "3"
    assert params["1"] == "Smokehouse"


def test_parameter_mit_gleichheitszeichen_im_wert() -> None:
    params = template_params("Perks|search=Ale|exclude=Amber for Water,Scales +1")
    assert params["search"] == "Ale"
    assert params["exclude"].startswith("Amber for Water")


def test_eckige_klammern_stoeren_nicht() -> None:
    params = template_params(ECHTER_GOODS_AUFRUF)
    assert params["m_Name"] == "[Needs] Boots"
    assert params["page_name"] == "Boots"
    assert params["displayName_key"] == "Good_Boots_Name"


def test_waren_tragen_die_id_aus_dem_spielstand(tmp_path: Path) -> None:
    """m_Name ist genau die Zeichenkette, die auch im Save steht. Daran haengt,
    ob sich Wissensbasis und Spielstand ohne Raten verbinden lassen."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.import_guid_index(conn, [
        {"guid": "01f4563332ee590428e448ac985519ca", "page_name": "Needs", "domain": "goodsCategories"},
    ])
    kb.import_goods(conn, [template_params(ECHTER_GOODS_AUFRUF)])
    zeile = conn.execute("SELECT * FROM resources WHERE en='Boots'").fetchone()
    assert zeile["save_id"] == "[Needs] Boots"
    assert zeile["category"] == "Needs"          # über den guid-Index aufgelöst
    assert zeile["display_key"] == "Good_Boots_Name"
    assert zeile["sell_value"] == 5.0
    conn.close()


def test_unbekannte_kategorie_bleibt_leer_statt_zu_scheitern(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.import_goods(conn, [template_params(ECHTER_GOODS_AUFRUF)])   # ohne guid_index
    zeile = conn.execute("SELECT category, category_guid FROM resources WHERE en='Boots'").fetchone()
    assert zeile["category"] is None
    assert zeile["category_guid"] == "01f4563332ee590428e448ac985519ca"
    conn.close()


def test_essbare_waren_mit_saettigung(tmp_path: Path) -> None:
    """food_forecast braucht zu wissen, was zählt und wie viel es sättigt."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.import_goods(conn, [
        {"page_name": "Jerky", "m_Name": "[Food Processed] Jerky", "eatable": "1",
         "eatingFullness": "1.5"},
        {"page_name": "Coal", "m_Name": "[Crafting] Coal", "eatable": "0",
         "canBeBurned": "1", "burningTime": "120"},
    ])
    essbar = kb.food_goods(conn)
    assert [w["en"] for w in essbar] == ["Jerky"]
    assert essbar[0]["eating_fullness"] == 1.5
    conn.close()


def test_leere_und_kaputte_zahlen_ergeben_none(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.import_goods(conn, [
        {"page_name": "Kaputt", "eatingFullness": "", "tradingSellValue": "n/a"},
    ])
    zeile = conn.execute("SELECT * FROM resources WHERE en='Kaputt'").fetchone()
    assert zeile["eating_fullness"] is None and zeile["sell_value"] is None
    conn.close()


def test_eintrag_ohne_seitennamen_wird_uebergangen(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    assert kb.import_goods(conn, [{"m_Name": "[X] Y"}, {"page_name": " "}]) == 0
    conn.close()


@pytest.mark.parametrize("version,warnt", [
    ("1.8.10", True), ("1.9", True), ("1.9.8", True), ("1.10.4", False), ("1.10", False),
])
def test_versionswarnung_trifft_die_haeufigen_faelle(tmp_path: Path, version, warnt) -> None:
    """Im Abzug kommt 1.10 gar nicht vor -- häufigste sind 1.8.10, 1.9, 1.9.8."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    warnung = kb.record_page(conn, f"Seite {version}", None, None, version, "1.10.4")
    assert (warnung is not None) is warnt
    conn.close()


def test_speziesdaten_aus_mehreren_tabellen_ergaenzen_sich(tmp_path: Path) -> None:
    """Drei Tabellen tragen Spezieswerte. Die zweite darf die erste nicht
    leerräumen -- INSERT OR REPLACE tut genau das, wenn man nicht aufpasst."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.import_species(conn, [{"Species": "Beavers", "Base Resolve": "10",
                              "Break Interval": "02:00", "Decadence": "2"}])
    kb.import_species(conn, [{"Species": "Beavers", "Comfort": "Engineering",
                              "Proficiency": "Woodworking"}])
    kb.import_species(conn, [{"Species": "Beavers",
                              "Species Resolve to Reputation Ratio": "0.000013"}])
    zeile = conn.execute("SELECT * FROM species WHERE en='Beavers'").fetchone()
    assert zeile["base_resolve"] == 10.0          # aus der ersten Tabelle
    assert zeile["break_seconds"] == 120.0        # "02:00" umgerechnet
    assert zeile["comfort"] == "Engineering"      # aus der zweiten
    assert zeile["reputation_ratio"] == 1.3e-05   # aus der dritten
    conn.close()


def test_wiederholte_kopfzeile_im_koerper_wird_uebersprungen(tmp_path: Path) -> None:
    """Die Grundsteinlisten wiederholen ihre Kopfzeile als erste Datenzeile."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    n = kb.import_cornerstones(conn, [
        {"Name": "Name", "Rarity": "Rarity", "Description": "Description"},
        {"Name": "Advanced Herbalism", "Rarity": "Epic", "Description": "+50%"},
    ])
    assert n == 1
    assert conn.execute("SELECT COUNT(*) c FROM cornerstones").fetchone()["c"] == 1
    conn.close()


def test_herkunft_sammelt_sich_statt_sich_zu_ueberschreiben(tmp_path: Path) -> None:
    """Ein Grundstein kann jährlich UND beim Händler vorkommen."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    zeile = [{"Name": "Dye Extractor", "Rarity": "Epic", "Description": "x"}]
    kb.import_cornerstones(conn, zeile, origin="jährlich")
    kb.import_cornerstones(conn, zeile, origin="Auftrag")
    herkunft = conn.execute("SELECT origin FROM cornerstones WHERE en='Dye Extractor'").fetchone()
    assert "jährlich" in herkunft["origin"] and "Auftrag" in herkunft["origin"]
    conn.close()


def test_rarity_none_wird_zu_null(tmp_path: Path) -> None:
    """Effekte ohne Seltenheit stehen mit 'None' in der Tabelle."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.import_cornerstones(conn, [{"Name": "Abyssal Revenge", "Rarity": "None",
                                   "Description": "x"}])
    assert conn.execute(
        "SELECT rarity FROM cornerstones WHERE en='Abyssal Revenge'").fetchone()["rarity"] is None
    conn.close()


def test_bruchteil_einer_minute_wird_umgerechnet(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.import_species(conn, [{"Species": "Bats", "Break Interval": "01:40"}])
    assert conn.execute(
        "SELECT break_seconds FROM species WHERE en='Bats'").fetchone()["break_seconds"] == 100.0
    conn.close()


# Wörtlich aus dem HTML-Abzug, Seite "Recipes", Tabelle 3.
ECHTE_REZEPTZEILE = {
    "Building": "Butcher", "Grade": "★★ 2:06",
    "Ingredient #1": "5 Insects 5 Meat",
    "Ingredient #2": "5 Wood 2 Oil 2 Salt 1 Coal 1 Sea Marrow",
    "#": "10", "Product": "Jerky",
}


def test_zutaten_sind_alternativen_keine_liste() -> None:
    """'5 Insects 5 Meat' heisst: 5 Insekten ODER 5 Fleisch."""
    zutaten = kb.parse_zutaten("5 Insects 5 Meat")
    assert zutaten == [{"menge": 5.0, "ware": "Insects"}, {"menge": 5.0, "ware": "Meat"}]


def test_zutaten_mit_zweiwortigen_namen() -> None:
    zutaten = kb.parse_zutaten("5 Wood 2 Oil 1 Sea Marrow")
    assert {"menge": 1.0, "ware": "Sea Marrow"} in zutaten


def test_grad_traegt_sterne_und_dauer() -> None:
    assert kb.parse_grad("★★ 2:06") == (2, 126.0)
    assert kb.parse_grad("★★★ 0:45") == (3, 45.0)
    assert kb.parse_grad(None) == (None, None)
    assert kb.parse_grad("ohne alles") == (None, None)


def test_rezept_landet_vollstaendig_in_der_datenbank(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    assert kb.import_recipes(conn, [ECHTE_REZEPTZEILE]) == 1
    z = conn.execute("SELECT * FROM recipes").fetchone()
    assert z["building"] == "Butcher" and z["product"] == "Jerky"
    assert z["product_amount"] == 10.0 and z["stars"] == 2 and z["seconds"] == 126.0
    gruppen = json.loads(z["inputs"])
    assert len(gruppen) == 2          # zwei Zutaten, je mit Alternativen
    assert {"menge": 5.0, "ware": "Meat"} in gruppen[0]
    conn.close()


def test_nahrungsverstaerkung_rechnet_mit_saettigung(tmp_path: Path) -> None:
    """Der Kern der Spec: 5 Fleisch mit Sättigung 1 werden zu 10 Dörrfleisch
    mit Sättigung 2 -- fünf Punkte rein, zwanzig raus."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.import_goods(conn, [
        {"page_name": "Meat", "eatable": "1", "eatingFullness": "1"},
        {"page_name": "Insects", "eatable": "1", "eatingFullness": "1"},
        {"page_name": "Jerky", "eatable": "1", "eatingFullness": "2"},
    ])
    kb.import_recipes(conn, [ECHTE_REZEPTZEILE])
    verstaerkung = kb.food_amplification(conn)
    assert len(verstaerkung) == 1
    assert verstaerkung[0]["saettigung_rein"] == 5.0
    assert verstaerkung[0]["saettigung_raus"] == 20.0
    assert verstaerkung[0]["faktor"] == 4.0
    conn.close()


def test_nicht_essbare_produkte_zaehlen_nicht(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.import_goods(conn, [{"page_name": "Planks", "eatable": "0"},
                           {"page_name": "Wood", "eatable": "0"}])
    kb.import_recipes(conn, [{"Building": "Lumber Mill", "Ingredient #1": "2 Wood",
                              "#": "1", "Product": "Planks"}])
    assert kb.food_amplification(conn) == []
    conn.close()


def test_billigste_alternative_wird_gerechnet(tmp_path: Path) -> None:
    """Das Spiel lässt die Wahl; wer plant, nimmt die günstigste."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.import_goods(conn, [
        {"page_name": "Berries", "eatable": "1", "eatingFullness": "1"},
        {"page_name": "Pie", "eatable": "1", "eatingFullness": "3"},
        {"page_name": "Meat", "eatable": "1", "eatingFullness": "1"},
    ])
    kb.import_recipes(conn, [{"Building": "Bakery", "Ingredient #1": "2 Berries 8 Meat",
                              "#": "10", "Product": "Pie"}])
    e = kb.food_amplification(conn)[0]
    assert e["saettigung_rein"] == 2.0      # Beeren, nicht Fleisch
    assert e["faktor"] == 15.0
    conn.close()
