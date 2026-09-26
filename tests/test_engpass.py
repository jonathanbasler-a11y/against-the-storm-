"""Was gerade entscheidet: Nahrung, Ungeduld oder Pestfäule (Runde 21)."""

from __future__ import annotations

import json
from pathlib import Path

from ats_assistant import berater, engpass, tools_api


def _uhr(ergebnis: dict, art: str) -> dict:
    return next(u for u in ergebnis["uhren"] if u["art"] == art)


def test_die_kuerzeste_akute_uhr_entscheidet() -> None:
    e = engpass.uhren({"reichweite_sekunden": 700.0, "rate_je_spielzeitsekunde": -0.1},
                      {"sekunden_bis_verlust": 240.0, "je_spielzeitsekunde": 0.01,
                       "jetzt": 6.6, "schwelle": 14})
    assert e["entscheidend"] == "ungeduld" and e["stufe"] == "rot"
    assert e["kurz"] == "Ungeduld 4 min"
    assert _uhr(e, "nahrung")["stufe"] == "gelb"
    assert _uhr(e, "ungeduld")["zusatz"] == "6,6 von 14"


def test_rot_schlaegt_gelb_auch_bei_laengerer_zeit_nicht_umgekehrt() -> None:
    e = engpass.uhren({"reichweite_sekunden": 200.0}, {"sekunden_bis_verlust": 100.0})
    assert e["entscheidend"] == "ungeduld"          # beide rot: die kürzere
    e = engpass.uhren({"reichweite_sekunden": 200.0}, {"sekunden_bis_verlust": 800.0})
    assert e["entscheidend"] == "nahrung"           # rot vor gelb


def test_wachsende_nahrung_ist_keine_uhr_und_nichts_ist_akut() -> None:
    e = engpass.uhren({"rate_je_spielzeitsekunde": 0.2, "reichweite_sekunden": None},
                      {"je_spielzeitsekunde": -0.001})
    assert _uhr(e, "nahrung")["text"] == "wächst"
    assert _uhr(e, "ungeduld")["text"] == "sinkt"
    assert e["entscheidend"] is None and e["kurz"] == "nichts akut"


def test_hunger_allein_ist_kein_alarm_erst_mit_abgaengen() -> None:
    """Regel des Spielers: Hunger ist nur schlimm, wenn Leute gehen."""
    nahrung = {"reichweite_sekunden": 2000.0}
    nur_hunger = engpass.uhren(nahrung, {}, {"hunger": 5, "gegangen": 1},
                               {"hunger": 2, "gegangen": 1})
    assert _uhr(nur_hunger, "nahrung")["stufe"] == "ruhig"
    assert "Hunger 5× (+3)" in _uhr(nur_hunger, "nahrung")["zusatz"]
    mit_abgang = engpass.uhren(nahrung, {}, {"hunger": 5, "gegangen": 3},
                               {"hunger": 2, "gegangen": 1})
    assert _uhr(mit_abgang, "nahrung")["stufe"] == "gelb"
    assert mit_abgang["entscheidend"] == "nahrung"
    assert "3 gegangen (+2)" in _uhr(mit_abgang, "nahrung")["zusatz"]


def test_pestfaeule_ohne_messung_hat_keine_zeit() -> None:
    e = engpass.uhren({}, {}, {"zysten": {"entstanden": 12, "verbrannt": 9, "entfernt": 1}},
                      {"zysten": {"entstanden": 9, "verbrannt": 9}})
    pest = _uhr(e, "pestfaeule")
    assert pest["sekunden"] is None and pest["stufe"] == "unbekannt"
    assert pest["text"] == "Zysten 12, verbrannt 9, entfernt 1 (+3 neu)"
    assert pest["zusatz"] == "keine Zeit gemessen"
    assert e["entscheidend"] is None and e["kurz"] == "–"


def test_fremde_formen_werfen_nicht() -> None:
    for kaputt in (None, [], "x", {"reichweite_sekunden": "bald"}, {"jetzt": True}):
        e = engpass.uhren(kaputt, kaputt, kaputt, kaputt, kaputt)
        assert [u["art"] for u in e["uhren"]] == ["nahrung", "ungeduld", "pestfaeule"]


def test_verlustschwelle_erreicht_ist_null_sekunden() -> None:
    e = engpass.uhren({}, {"warnung": "Verlustschwelle erreicht", "jetzt": 14, "schwelle": 14})
    assert _uhr(e, "ungeduld")["sekunden"] == 0.0 and e["entscheidend"] == "ungeduld"


def test_tools_api_rechnet_seit_dem_letzten_speichern(tmp_path: Path) -> None:
    zeilen = [{"game_time": 100.0, "stats": {"hunger": 1, "gegangen": 0}},
              {"typ": "notiz", "text": "x"},
              {"game_time": 400.0, "stats": {"hunger": 3, "gegangen": 2}}]
    (tmp_path / "lauf.jsonl").write_text("\n".join(json.dumps(z) for z in zeilen) + "\n",
                                         encoding="utf-8")
    e = tools_api.engpass(tmp_path, "lauf", nahrung={"reichweite_sekunden": 5000.0},
                          ungeduld={})
    assert e["verfuegbar"] is True and e["entscheidend"] == "nahrung"
    assert tools_api.engpass(tmp_path, "fehlt")["verfuegbar"] is False


def test_der_rat_bekommt_den_engpass() -> None:
    e = engpass.uhren({"reichweite_sekunden": 120.0}, {"sekunden_bis_verlust": 5000.0})
    auszug = berater.kontext(zustand={"jahr": 2}, engpass=e)
    assert auszug["engpass"]["entscheidend"] == "nahrung"
    assert {u["art"] for u in auszug["engpass"]["uhren"]} == {"nahrung", "ungeduld",
                                                                 "pestfaeule"}
    berater.pruefe_auszug(auszug)
    text = " ".join(berater.systemtext().split())
    assert "`engpass`" in text and "zuerst darauf eingehen" in text
