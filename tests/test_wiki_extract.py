"""Tests der Wiki-Auswertung gegen echte Vorlagenaufrufe aus dem Abzug.

Die Beispiele stammen wörtlich aus `build_kb.py detail` über den Abzug vom
21.09.2026 -- also aus dem echten Wiki, nicht aus einer Annahme darüber.
"""

from __future__ import annotations

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
