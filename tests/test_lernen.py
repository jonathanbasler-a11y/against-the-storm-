"""Lernen von Lauf zu Lauf: Laufberichte, Lehren, Korrekturen.

Wunsch vom Spielrechner (23.09.2026): „wir sollten auch von Run zu Run
lernen und besser werden und verstehen, woran wir gescheitert sind" -- und
der Rat soll sich merken, was der Spieler korrigiert hat („Pakete kann man
nicht öffnen").
"""

from __future__ import annotations

import json
from pathlib import Path

from ats_assistant import lernen


def _stand(zeit, jahr, food, *, ruf=0.0, ungeduld=1.0, gebaeude=5, won=None, lost=None,
           biome="Royal Woodlands", orders=()):
    """Ein Zustand, wie er in der Mitschrift steht (verkleinert)."""
    return {"game_time": zeit, "year": year_or(jahr), "biome": biome, "prestige": 15,
            "reputation": ruf, "reputation_to_win": 18, "impatience": ungeduld,
            "impatience_to_lose": 14, "won": won, "lost": lost,
            "buildings": [{"model": f"B{i}"} for i in range(gebaeude)],
            "orders": list(orders),
            "category_trends": {"Food": food}}


def year_or(j):
    return j


def _fallend(start, schritt, n=180, frisch=(40, 70)):
    """Ein Ringpuffer, in dem der Block `frisch` fällt."""
    reihe = [float(start)] * n
    a, b = frisch
    reihe[a:b] = [start - schritt * i for i in range(b - a)]
    return reihe


def _mitschrift(runs: Path, name: str, zustaende: list[dict], notizen=()) -> None:
    runs.mkdir(parents=True, exist_ok=True)
    zeilen = [json.dumps(z) for z in zustaende] + [json.dumps(n) for n in notizen]
    (runs / f"{name}.jsonl").write_text("\n".join(zeilen) + "\n", encoding="utf-8")


def test_ein_laufbericht_sagt_wann_die_nahrung_knapp_wurde(tmp_path: Path) -> None:
    zustaende = [
        _stand(300.0, 1, [100.0] * 180),
        _stand(600.0, 1, _fallend(100, 3.0), ruf=0.5, ungeduld=2.0),   # fällt 0,3/s
        _stand(900.0, 2, _fallend(10, 0.1, frisch=(70, 100)), ruf=2.0, ungeduld=4.0),
    ]
    bericht = lernen.laufbericht(zustaende, "lauf-a")
    assert bericht["kennung"] == "lauf-a"
    assert bericht["jahre"] == 2
    assert bericht["ungeduld_max"] == 4.0
    assert bericht["ruf_nach_jahr"]["1"] == 0.5
    assert bericht["nahrung_min_reichweite"]["sekunden"] < 120
    assert bericht["nahrung_knapp_jahr1"] is True
    assert bericht["ausgang"] == "offen"


def test_der_ausgang_kommt_aus_dem_spielstand(tmp_path: Path) -> None:
    sieg = lernen.laufbericht([_stand(300.0, 1, [1.0] * 180),
                               _stand(9000.0, 8, [1.0] * 180, ruf=18.0, won=True)], "s")
    assert sieg["ausgang"] == "gewonnen"


def test_der_ausgang_kommt_sonst_aus_der_spielhistorie(tmp_path: Path) -> None:
    """Wer aufgibt oder verliert, hinterlässt oft kein `lost` in der Mitschrift.
    Die Spielhistorie (MetaSave) kennt den Ausgang; zugeordnet über Biom und
    Jahre, nur wenn eindeutig."""
    runs = tmp_path / "runs"
    _mitschrift(runs, "alt", [_stand(300.0, 1, [1.0] * 180), _stand(2000.0, 3, [1.0] * 180)])
    historie = [{"hasWon": False, "years": 3, "biome": "Royal Woodlands"}]
    berichte = lernen.berichte(runs, historie=historie)
    assert berichte[0]["ausgang"] == "verloren"


def test_empfehlungen_des_rats_stehen_im_bericht(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _mitschrift(runs, "lauf", [_stand(300.0, 1, [1.0] * 180), _stand(600.0, 1, [1.0] * 180)],
                notizen=[{"typ": "notiz", "art": "rat", "spielzeit": 600.0, "jahr": 1,
                          "text": "Nimm das Nahrungssammlerlager."}])
    bericht = lernen.berichte(runs)[0]
    assert bericht["empfehlungen"] == [{"spielzeit": 600.0, "jahr": 1,
                                        "text": "Nimm das Nahrungssammlerlager."}]


def _bericht(ausgang, knapp, ruf1):
    return {"ausgang": ausgang, "nahrung_knapp_jahr1": knapp, "ruf_nach_jahr": {"1": ruf1},
            "ungeduld_max": 5.0, "gebaeude_nach_jahr": {"1": 10}, "auftraege_erledigt": 3}


def test_lehren_stellen_niederlagen_gegen_siege() -> None:
    berichte = ([_bericht("verloren", True, 0.5)] * 3 + [_bericht("verloren", False, 1.0)]
                + [_bericht("gewonnen", False, 3.0)] * 3)
    lehren = lernen.lehren(berichte)
    text = " ".join(lehren)
    assert "3 von 4 Niederlagen" in text and "0 von 3 Siegen" in text
    assert "Hinweis" not in text                        # genug Läufe je Seite
    assert len(lehren) <= 5


def test_wenige_laeufe_sind_ein_hinweis_kein_befund() -> None:
    lehren = lernen.lehren([_bericht("verloren", True, 0.5), _bericht("gewonnen", False, 3.0)])
    assert lehren and all(s.startswith("Hinweis") for s in lehren)


def test_ohne_abgeschlossene_laeufe_sagt_es_das() -> None:
    lehren = lernen.lehren([_bericht("offen", True, 0.5)])
    assert lehren == ["Noch kein abgeschlossener Lauf mitgeschrieben – Lehren folgen."]


def test_korrekturen_werden_gemerkt_und_gelesen(tmp_path: Path) -> None:
    pfad = tmp_path / "wissen" / "korrekturen.jsonl"
    lernen.korrektur_merken(pfad, "Pakete öffnest du im Hauptlager",
                            "Pakete kann man nicht öffnen")
    lernen.korrektur_merken(pfad, "…", "Der Händler kauft Pakete")
    assert lernen.korrekturen(pfad) == ["Der Händler kauft Pakete",
                                        "Pakete kann man nicht öffnen"]      # neueste zuerst
    assert lernen.korrekturen(tmp_path / "gibtsnicht.jsonl") == []


def test_der_zwischenspeicher_liegt_nicht_zwischen_den_mitschriften(tmp_path: Path) -> None:
    """In `runs/` ist jede .jsonl eine Mitschrift -- was das Lernen ablegt,
    darf dort nicht dazwischengeraten."""
    runs = tmp_path / "runs"
    _mitschrift(runs, "lauf", [_stand(300.0, 1, [1.0] * 180)])
    lernen.berichte(runs)
    assert sorted(p.name for p in runs.glob("*.jsonl")) == ["lauf.jsonl"]


# --------------------------------------------------------------------------
# Runde 8: woran ein Lauf gescheitert ist
# --------------------------------------------------------------------------


def _mit_statistik(stand: dict, hunger: int, gegangen: int = 0, tot: int = 0) -> dict:
    stand["stats"] = {"hunger": hunger, "gegangen": gegangen, "tot": tot}
    return stand


def test_die_ursache_ist_die_ungeduld() -> None:
    b = lernen.laufbericht([_stand(300.0, 1, [100.0] * 180),
                            _stand(600.0, 2, [100.0] * 180, ungeduld=14.0, lost=True)], "a")
    assert b["ausgang"] == "verloren" and b["ursache"] == "Ungeduld"


def test_die_ursache_ist_hunger_und_die_statistik_steht_im_bericht() -> None:
    b = lernen.laufbericht([
        _mit_statistik(_stand(300.0, 1, [100.0] * 180), hunger=2),
        _mit_statistik(_stand(600.0, 1, [100.0] * 180), hunger=4, gegangen=1),
        _mit_statistik(_stand(900.0, 2, [100.0] * 180, lost=True), hunger=9, gegangen=3, tot=1),
    ], "b")
    assert (b["hunger"], b["gegangen"], b["tot"], b["hunger_jahr1"]) == (9, 3, 1, 4)
    assert b["ursache"] == "Hunger/Abwanderung"


def test_ein_offener_lauf_hat_keine_ursache() -> None:
    b = lernen.laufbericht([_stand(300.0, 1, [100.0] * 180)], "c")
    assert b["ursache"] is None


def test_eine_lehre_ueber_hungerereignisse() -> None:
    siege = [{"ausgang": "gewonnen", "hunger": 0} for _ in range(3)]
    niederlagen = [{"ausgang": "verloren", "hunger": 8} for _ in range(3)]
    lehren = lernen.lehren(siege + niederlagen)
    assert any("Hungerereignisse" in s for s in lehren)
    assert not any(s.startswith("Hinweis") for s in lehren)


def test_ein_alter_zwischenspeicher_wird_neu_gerechnet(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _mitschrift(runs, "lauf", [_mit_statistik(_stand(300.0, 1, [100.0] * 180), hunger=5)])
    datei = runs / "lauf.jsonl"
    st = datei.stat()
    speicher = lernen.wissensordner(runs) / "berichte.json"
    speicher.parent.mkdir(parents=True)
    speicher.write_text(json.dumps({"lauf.jsonl": {
        "marke": [st.st_size, st.st_mtime_ns], "bericht": {"kennung": "lauf", "alt": True}}}),
        encoding="utf-8")
    bericht = lernen.berichte(runs)[0]
    assert "alt" not in bericht and bericht["hunger"] == 5


def test_korrektur_mit_zeilentrenner_geht_nicht_verloren(tmp_path: Path) -> None:
    pfad = tmp_path / "k.jsonl"
    lernen.korrektur_merken(pfad, "Aussage", "Hunger\u2028ist nur schlimm, wenn Leute gehen")
    assert lernen.korrekturen(pfad) == ["Hunger\u2028ist nur schlimm, wenn Leute gehen"]
