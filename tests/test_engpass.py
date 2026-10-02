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


# --------------------------------------------------------------------------
# Ruf-Tempo und Biom-Namen (Runde 22, nach der Spielhistorie vom 27.09.2026)
# --------------------------------------------------------------------------


def test_ruf_tempo_misst_gegen_sieben_jahre() -> None:
    langsam = engpass.ruf_tempo(6.5, 18, 5, 0)           # vier Jahre vorbei
    assert langsam["tempo_je_jahr"] == 1.62 and langsam["noetig_je_jahr"] == 3.83
    assert langsam["sieg_etwa_jahr"] == 12 and langsam["stufe"] == "rot"
    assert langsam["text"] == "6,5 von 18 · 1,6/Jahr → Sieg etwa Jahr 12"
    assert langsam["zusatz"] == "für Jahr 7: 3,8/Jahr"
    schnell = engpass.ruf_tempo(9, 18, 4, 0)
    assert schnell["stufe"] == "ruhig" and schnell["sieg_etwa_jahr"] == 7
    knapp = engpass.ruf_tempo(7, 18, 4, 0)              # 2,33 gegen 2,75
    assert knapp["stufe"] == "gelb"


def test_ruf_tempo_urteilt_nicht_vor_jahr_vier() -> None:
    # Am Spielrechner, 28.09.2026: Jahr 3, Ruf 2 -- stand rot mit „Sieg etwa Jahr 25“.
    frueh = engpass.ruf_tempo(2.0, 18, 3, 0)
    assert frueh["stufe"] == "unbekannt" and frueh["zusatz"] == "Urteil ab Jahr 4"
    assert frueh["text"] == "2,0 von 18 · 1,0/Jahr"
    assert "sieg_etwa_jahr" not in frueh and "noetig_je_jahr" not in frueh
    assert engpass.ruf_tempo(2.0, 18, 4, 0)["stufe"] == "rot"


def test_ruf_tempo_grenzfaelle() -> None:
    assert engpass.ruf_tempo(1.2, 18, 1, 1)["zusatz"] == "Tempo ab Jahr 2"
    assert engpass.ruf_tempo(18, 18, 9, 2)["stufe"] == "ruhig"
    spaet = engpass.ruf_tempo(12, 18, 9, 0)
    assert spaet["noetig_je_jahr"] is None and spaet["zusatz"] == "Jahr 7 ist vorbei"
    assert engpass.ruf_tempo(0, 18, 4, 0)["text"].endswith("kein Zuwachs")
    for kaputt in ((None, 18, 3, 0), (5, 0, 3, 0), (5, 18, None, 0), ("x", 18, 3, 0)):
        assert engpass.ruf_tempo(*kaputt) is None


def test_der_engpass_bringt_das_tempo_mit(tmp_path: Path) -> None:
    zeilen = [{"game_time": 100.0, "year": 4, "season": 1, "reputation": 5.0,
               "reputation_to_win": 18}]
    (tmp_path / "lauf.jsonl").write_text(json.dumps(zeilen[0]) + "\n", encoding="utf-8")
    e = tools_api.engpass(tmp_path, "lauf", nahrung={}, ungeduld={})
    assert e["ruf"]["sieg_etwa_jahr"] == 13               # 3,33 Jahre vorbei, 1,5/Jahr
    auszug = berater.kontext(zustand={"jahr": 4}, engpass=e)
    assert auszug["engpass"]["ruf"]["noetig_je_jahr"] == e["ruf"]["noetig_je_jahr"]
    assert "`engpass.ruf`" in " ".join(berater.systemtext().split())


def test_biome_aus_dem_spielstand_bekommen_ihren_namen() -> None:
    from ats_assistant import biome, tierlisten

    assert biome.nachsehen("Poro Biome") == {"en": "Bamboo Flats", "de": "Bambusebene"}
    assert biome.deutsch("Moorlands") == "Scharlachroter Obstgarten"
    assert biome.deutsch("The Marshlands") == "Sümpfe"
    assert biome.deutsch("Unbekannt") == "Unbekannt" and biome.deutsch(None) is None
    # Die Tierliste führt „Scarlet Orchard“, der Spielstand sagt „Moorlands“.
    assert tierlisten.nachsehen("biom", "Moorlands")[0]["stufe"] == "A"
    assert tierlisten.nachsehen("biom", "The Marshlands")[0]["stufe"] == "B"


def test_die_historie_nennt_biome_wie_im_spiel() -> None:
    from ats_assistant import analysis

    laeufe = ([{"hasWon": False, "biome": "Poro Biome", "years": j, "endTimestamp": j}
               for j in (2, 4, 7, 9, 13)]
              + [{"hasWon": True, "biome": "Poro Biome", "years": 13, "endTimestamp": 20}]
              + [{"hasWon": True, "biome": "Moorlands", "years": 11, "endTimestamp": 30 + i}
                 for i in range(2)])
    text = analysis.summarise(analysis.compare_runs(laeufe, n=100))
    assert "Gewonnen nach Biom: Bambusebene 1 von 6, Scharlachroter Obstgarten 2 von 2." in text



def test_bei_knapper_nahrung_schlaegt_ein_nahrungsgebaeude_die_tierliste() -> None:
    """P17: Weber und Manufaktur nach Tierliste, die Kleinfarm erst in Jahr 6."""
    text = " ".join(berater.systemtext().split())
    assert "Nahrung zuerst — wenn der Mangel strukturell ist" in text
    assert "schlägt ein Nahrungsgebäude jede Tier-Stufe" in text
    assert "Äcker (`Farmfield`) ohne Farm" in text
    # … aber nicht binär: mit Quellen und Verarbeitung darf anderes vorgehen.
    assert "darf ein anderer Engpass vorgehen" in text


def test_eine_schwankende_nahrungsuhr_ist_kein_absturz() -> None:
    """P17: die Uhr sprang zwischen 6 min, „wächst“ und 90 min. Hält sich der
    Vorrat über drei Speicherstände, eine Stufe weniger."""
    kurz = {"reichweite_sekunden": 200.0}
    stabil = engpass.uhren(kurz, {}, nahrung_verlauf=[20.0, 35.0, 22.0])
    nahrung = _uhr(stabil, "nahrung")
    assert nahrung["stufe"] == "gelb" and nahrung["zusatz"].startswith("über 15 min stabil")
    faellt = engpass.uhren(kurz, {}, nahrung_verlauf=[60.0, 40.0, 22.0])
    assert _uhr(faellt, "nahrung")["stufe"] == "rot"
    zu_kurz = engpass.uhren(kurz, {}, nahrung_verlauf=[20.0, 22.0])
    assert _uhr(zu_kurz, "nahrung")["stufe"] == "rot"      # erst ab drei Ständen
    gelb = engpass.uhren({"reichweite_sekunden": 600.0}, {}, nahrung_verlauf=[20, None, 30, 25])
    assert _uhr(gelb, "nahrung")["stufe"] == "ruhig"
    # Hunger mit Abgängen hebt die Stufe trotzdem wieder.
    mit_abgang = engpass.uhren(kurz, {}, {"hunger": 5, "gegangen": 2},
                               {"hunger": 3, "gegangen": 1}, nahrung_verlauf=[20.0, 30.0, 25.0])
    assert _uhr(mit_abgang, "nahrung")["stufe"] == "rot"


def test_tools_api_reicht_den_vorratsverlauf_herein(tmp_path: Path) -> None:
    """Vier Stände, der Vorrat hält sich: die kurze Reichweite wird gelb, nicht rot."""
    def reihe(werte):
        return {"Food": [float(w) for w in werte]}
    basis = [30.0] * 180
    stände = []
    for i, ende in enumerate((30.0, 25.0, 40.0, 30.0)):   # Vorrat 27 → 42 → 32
        werte = list(basis)
        for k in range(30):                       # 30 frische Stützstellen je Speichern
            werte[(i * 30 + k) % 180] = ende + (k % 3)
        basis = werte
        stände.append({"game_time": 300.0 * (i + 1), "category_trends": reihe(werte)})
    (tmp_path / "lauf.jsonl").write_text("\n".join(json.dumps(s) for s in stände) + "\n",
                                         encoding="utf-8")
    e = tools_api.engpass(tmp_path, "lauf", nahrung={"reichweite_sekunden": 200.0}, ungeduld={})
    assert _uhr(e, "nahrung")["stufe"] == "gelb"
    # Derselbe Verlauf, aber fallend: bleibt rot.
    for k in range(30):                           # nur die frischen Werte: Vorrat 10
        stände[-1]["category_trends"]["Food"][(3 * 30 + k) % 180] = 10.0 + (k % 3)
    (tmp_path / "lauf.jsonl").write_text("\n".join(json.dumps(s) for s in stände) + "\n",
                                         encoding="utf-8")
    e = tools_api.engpass(tmp_path, "lauf", nahrung={"reichweite_sekunden": 200.0}, ungeduld={})
    assert _uhr(e, "nahrung")["stufe"] == "rot"


def test_bei_vollem_ruf_ist_der_lauf_gewonnen() -> None:
    # P17 gewonnen, 28.09.2026: Ruf 18 von 18, Ungeduld 13,2 von 14 stand rot.
    e = engpass.uhren({"reichweite_sekunden": None, "rate_je_spielzeitsekunde": 0.01},
                      {"sekunden_bis_verlust": 297.0, "jetzt": 13.2, "schwelle": 14})
    assert e["entscheidend"] == "ungeduld"
    fertig = engpass.mit_ruf(e, engpass.ruf_tempo(18.0, 18, 11, 1))
    assert fertig["gewonnen"] and fertig["entscheidend"] is None
    assert fertig["kurz"] == "Ruf voll – gewonnen" and fertig["stufe"] == "ruhig"
    ungeduld = next(u for u in fertig["uhren"] if u["art"] == "ungeduld")
    assert ungeduld["stufe"] == "ruhig" and "Ruf voll" in ungeduld["zusatz"]
    assert e["entscheidend"] == "ungeduld"               # das Original bleibt
    offen = engpass.mit_ruf(e, engpass.ruf_tempo(12.0, 18, 9, 0))
    assert offen["entscheidend"] == "ungeduld" and "gewonnen" not in offen
    assert engpass.mit_ruf(e, None) is e


# --------------------------------------------------------------------------
# Ruf steht still -- der gewonnene P17-Lauf, Spalten aus tools/verlauf.py
# (am Spielrechner, 28.09.2026)
# --------------------------------------------------------------------------

P17 = [(1, 0, 0.0), (1, 1, 0.0), (1, 2, 0.0), (2, 0, 2.0), (2, 1, 4.0), (3, 0, 4.0),
       (3, 1, 4.1), (3, 2, 4.3), (4, 1, 4.7), (4, 2, 5.2), (5, 0, 5.4), (5, 1, 7.1),
       (6, 0, 8.7), (6, 1, 9.1), (6, 1, 9.3), (6, 2, 9.9), (7, 0, 9.9), (7, 2, 10.0),
       (8, 0, 10.1), (8, 1, 10.4), (8, 2, 11.2), (9, 1, 11.7), (9, 2, 13.3),
       (10, 1, 15.0), (10, 2, 15.4), (11, 0, 16.6), (11, 1, 18.0)]


def _bis(jahr: int, zeit: int) -> list:
    return P17[:P17.index(next(p for p in P17 if p[:2] == (jahr, zeit))) + 1]


def test_der_stillstand_im_p17_lauf_waere_zweimal_aufgefallen() -> None:
    frueh = engpass.ruf_stillstand(_bis(3, 1))
    assert frueh["seit_jahr"] == 2 and frueh["text"] == "steht seit Jahr 2 (4,0 → 4,1)"
    mitte = engpass.ruf_stillstand(_bis(7, 2))
    assert mitte["text"] == "steht seit Jahr 6 (9,1 → 10,0)" and mitte["jahre"] == 1.3
    assert engpass.ruf_stillstand(_bis(8, 1))["seit_jahr"] == 6
    # Sobald der Ruf wieder zieht, ist die Warnung weg.
    for jahr, zeit in ((5, 1), (8, 2), (9, 2), (11, 1)):
        assert engpass.ruf_stillstand(_bis(jahr, zeit)) is None, (jahr, zeit)


def test_stillstand_grenzfaelle() -> None:
    assert engpass.ruf_stillstand([]) is None
    assert engpass.ruf_stillstand([(3, 0, 4.0)]) is None
    assert engpass.ruf_stillstand([(3, 0, 4.0), ("x", 1, 4.0), (3, 1, None), "kaputt"]) is None
    # Weniger als ein Jahr ohne Zuwachs ist noch kein Stillstand.
    assert engpass.ruf_stillstand([(3, 0, 4.0), (3, 2, 4.5)]) is None
    assert engpass.ruf_stillstand([(3, 0, 4.0), (4, 0, 4.5)])["jahre"] == 1.0


def test_stillstand_faerbt_die_ruf_zeile() -> None:
    still = engpass.ruf_stillstand(_bis(7, 2))
    ruf = engpass.mit_stillstand(engpass.ruf_tempo(10.0, 18, 7, 2), still)
    assert ruf["stufe"] == "rot" and ruf["zusatz"] == still["text"]      # rot bleibt rot
    frueh = engpass.mit_stillstand(engpass.ruf_tempo(4.1, 18, 3, 1),
                                   engpass.ruf_stillstand(_bis(3, 1)))
    assert frueh["stufe"] == "gelb" and "seit Jahr 2" in frueh["zusatz"]  # gemessen, auch früh
    voll = engpass.ruf_tempo(18.0, 18, 11, 1)
    assert engpass.mit_stillstand(voll, still) is voll
    assert engpass.mit_stillstand(None, still) is None
    assert engpass.mit_stillstand(voll, None) is voll


def test_der_engpass_liest_den_stillstand_aus_der_mitschrift(tmp_path: Path) -> None:
    zeilen = [{"game_time": 300.0 * i, "year": j, "season": s, "reputation": r,
               "reputation_to_win": 18} for i, (j, s, r) in enumerate(_bis(7, 2))]
    zeilen.insert(5, {"typ": "notiz", "text": "Rat"})
    pfad = tmp_path / "lauf.jsonl"
    pfad.write_text("".join(json.dumps(z) + "\n" for z in zeilen) + "{abgerissen\n",
                    encoding="utf-8")
    e = tools_api.engpass(tmp_path, "lauf", nahrung={}, ungeduld={})
    assert e["ruf"]["stillstand"]["seit_jahr"] == 6
    assert e["ruf"]["zusatz"] == "steht seit Jahr 6 (9,1 → 10,0)"
    # Nur bis zum letzten Stand gelesen, der einen Punkt tiefer lag.
    assert tools_api._ruf_verlauf(tmp_path, "lauf")[0] == (6, 0, 8.7)
    auszug = berater.kontext(zustand={"jahr": 7}, engpass=e)
    assert auszug["engpass"]["ruf"]["stillstand"]["seit_jahr"] == 6
    assert tools_api._ruf_verlauf(tmp_path, None) == []
    assert tools_api._ruf_verlauf(tmp_path, "fehlt") == []


def test_der_ruf_verlauf_liest_nach_einem_neuen_stand_nur_das_neue(tmp_path: Path,
                                                                   monkeypatch) -> None:
    pfad = tmp_path / "lauf.jsonl"
    zeilen = [{"year": j, "season": s, "reputation": r} for j, s, r in _bis(7, 0)]
    pfad.write_text("".join(json.dumps(z) + "\n" for z in zeilen), encoding="utf-8")
    assert tools_api._ruf_verlauf(tmp_path, "lauf")[-1] == (7, 0, 9.9)
    gelesen = []
    echt = json.loads
    monkeypatch.setattr(tools_api.json, "loads", lambda t: gelesen.append(1) or echt(t))
    with pfad.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"year": 7, "season": 2, "reputation": 10.0}) + "\n")
    verlauf = tools_api._ruf_verlauf(tmp_path, "lauf")
    assert len(gelesen) == 1                             # nur die neue Zeile
    assert verlauf[0] == (6, 0, 8.7) and verlauf[-1] == (7, 2, 10.0)
    assert engpass.ruf_stillstand(verlauf)["seit_jahr"] == 6
    # Ein Sprung nach oben schneidet vorn ab -- bis auf ein Jahr fürs Tempo.
    with pfad.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"year": 8, "season": 0, "reputation": 12.0}) + "\n")
    assert tools_api._ruf_verlauf(tmp_path, "lauf")[0] == (7, 0, 9.9)


def test_der_skill_kennt_den_stillstand() -> None:
    assert "`engpass.ruf.stillstand`" in " ".join(berater.systemtext().split())


def test_jahr_eins_ist_kein_stillstand() -> None:
    # P18, 28.09.2026: Jahr 2 beginnt mit Ruf 0 -- das ist Aufbau, kein Stillstand.
    assert engpass.ruf_stillstand([(1, 0, 0.0), (1, 1, 0.0), (1, 2, 0.0), (2, 0, 0.0)]) is None
    # Bleibt es das ganze Jahr 2 bei 0, steht der Ruf -- seit Jahr 2.
    still = engpass.ruf_stillstand([(1, 0, 0.0), (1, 2, 0.0), (2, 0, 0.0), (2, 2, 0.0),
                                    (3, 0, 0.0)])
    assert still["seit_jahr"] == 2 and still["jahre"] == 1.0



# --------------------------------------------------------------------------
# Nach Jahr 7: das Rennen gegen die Ungeduld (P18-Sieg, 28.09.2026)
# --------------------------------------------------------------------------

# Ungeduld je Stand im P17-Lauf, Spalte aus tools/verlauf.py; Spielzeit dazu.
P17_UNGEDULD = {(8, 2): (12.1, 5731), (9, 1): (13.9, 6029), (9, 2): (13.6, 6328),
                (10, 1): (13.2, 6627), (10, 2): (13.9, 6926), (11, 0): (14.0, 7225)}


def _p17_urteil(jahr: int, zeit: int) -> dict:
    ruf = engpass.ruf_tempo(_bis(jahr, zeit)[-1][2], 18, jahr, zeit)
    ungeduld, spielzeit = P17_UNGEDULD[(jahr, zeit)]
    return engpass.ruf_gegen_ungeduld(
        ruf, {"jetzt": ungeduld, "schwelle": 14, "je_spielzeitsekunde": 0.00255},
        spielzeit, engpass.entlastung(0.5), engpass.tempo_letztes_jahr(_bis(jahr, zeit)))


def test_der_p17_sieg_war_bei_diesem_tempo_knapp() -> None:
    # Gewonnen mit 14,0 von 14 in Jahr 11 -- „knapp“ ab Jahr 9/2, nicht „nein“.
    for stand in ((9, 2), (10, 1), (10, 2), (11, 0)):
        assert _p17_urteil(*stand)["urteil"] == "knapp", stand
    # Jahr 8/2: ein Jahr fast ohne Ruf dahinter -- bei diesem Tempo verloren.
    assert _p17_urteil(8, 2)["urteil"] == "nein"


def test_tempo_des_letzten_jahres() -> None:
    assert round(engpass.tempo_letztes_jahr(_bis(9, 2)), 2) == 2.1    # 11,2 → 13,3
    assert engpass.tempo_letztes_jahr(_bis(1, 2)) is None             # noch kein Jahr
    assert engpass.tempo_letztes_jahr([]) is None
    assert engpass.entlastung(0.5) == 0.5 and engpass.entlastung(None) == 1.0
    assert engpass.entlastung(3) == 0.0


def test_nach_jahr_sieben_zaehlt_das_rennen_gegen_die_ungeduld() -> None:
    ruf = engpass.ruf_tempo(16.5, 18, 12, 0)                          # P18, Jahr 12
    assert ruf["zusatz"] == "Jahr 7 ist vorbei" and ruf["stufe"] == "rot"
    gegen = engpass.ruf_gegen_ungeduld(
        ruf, {"jetzt": 10.4, "schwelle": 14, "je_spielzeitsekunde": 0.00255}, 8000,
        engpass.entlastung(0.5), 2.5)
    assert gegen["urteil"] == "ja"
    neu = engpass.mit_ungeduld(ruf, gegen)
    assert neu["stufe"] == "ruhig" and neu["zusatz"].startswith("vor der Ungeduld: ja (Rest +")
    # Vor Jahr 7 bleibt das Sieben-Jahres-Ziel -- nur ein „nein“ färbt rot.
    frueh = engpass.ruf_tempo(9, 18, 4, 0)
    assert engpass.mit_ungeduld(frueh, {**gegen, "urteil": "knapp"})["stufe"] == "ruhig"
    nein = {"urteil": "nein", "rest": -5.0, "text": "vor der Ungeduld: nein (Rest −5,0)"}
    assert engpass.mit_ungeduld(frueh, nein)["stufe"] == "rot"
    assert engpass.mit_ungeduld(None, gegen) is None
    assert engpass.mit_ungeduld(ruf, None) is ruf


def test_rennen_gegen_die_ungeduld_grenzfaelle() -> None:
    ruf = engpass.ruf_tempo(10, 18, 8, 0)
    ung = {"jetzt": 9.0, "schwelle": 14, "je_spielzeitsekunde": 0.00255}
    assert engpass.ruf_gegen_ungeduld(ruf, ung, 5000, tempo_jetzt=0)["urteil"] == "nein"
    assert engpass.ruf_gegen_ungeduld(None, ung, 5000) is None
    assert engpass.ruf_gegen_ungeduld(ruf, {}, 5000) is None
    assert engpass.ruf_gegen_ungeduld(ruf, ung, None) is None
    assert engpass.ruf_gegen_ungeduld(engpass.ruf_tempo(18, 18, 9, 0), ung, 5000) is None


def test_der_engpass_misst_nach_jahr_sieben_gegen_die_ungeduld(tmp_path: Path) -> None:
    zeilen = [{"game_time": 700.0 * i, "year": j, "season": s, "reputation": r,
               "reputation_to_win": 18,
               "effects": {"abweichungen": [{"feld": "bonusReputationPenaltyPerReputation",
                                            "wert": 0.5}]}}
              for i, (j, s, r) in enumerate(_bis(10, 1), start=1)]
    (tmp_path / "lauf.jsonl").write_text("".join(json.dumps(z) + "\n" for z in zeilen),
                                         encoding="utf-8")
    e = tools_api.engpass(tmp_path, "lauf", nahrung={},
                          ungeduld={"jetzt": 13.2, "schwelle": 14,
                                    "je_spielzeitsekunde": 0.00255})
    assert e["ruf"]["gegen_ungeduld"]["urteil"] == "knapp"
    assert e["ruf"]["stufe"] == "gelb" and "vor der Ungeduld: knapp" in e["ruf"]["zusatz"]
    auszug = berater.kontext(zustand={"jahr": 10}, engpass=e)
    assert auszug["engpass"]["ruf"]["gegen_ungeduld"]["urteil"] == "knapp"


def test_der_skill_kennt_das_rennen_gegen_die_ungeduld() -> None:
    assert "`engpass.ruf.gegen_ungeduld`" in " ".join(berater.systemtext().split())



def test_der_sturmwert_der_ungeduld_je_ruf_gilt_nicht_fuers_ganze_rennen(tmp_path: Path) -> None:
    """P19, 02.10.2026: im Sturm von Jahr 7 stand der Zusatz auf 1,5, sonst
    auf 0,5. Mit 1,5 hieß es „nein (Rest −13,5)“ -- gewonnen in Jahr 11."""
    def stand(i, jahr, zeit, ruf, zusatz):
        return {"game_time": 740.0 * i, "year": jahr, "season": zeit, "reputation": ruf,
                "reputation_to_win": 18,
                "effects": {"abweichungen": [{"feld": "bonusReputationPenaltyPerReputation",
                                              "wert": zusatz}]}}
    zeilen = [stand(1, 6, 2, 4.4, 1.5), stand(2, 7, 0, 4.9, 0.5), stand(3, 7, 1, 5.3, 0.5),
              stand(4, 7, 2, 5.85, 1.5)]
    (tmp_path / "lauf.jsonl").write_text("".join(json.dumps(z) + "\n" for z in zeilen),
                                         encoding="utf-8")
    ungeduld = {"jetzt": 9.3, "schwelle": 14, "je_spielzeitsekunde": 0.00255}
    mit_sturm = engpass.ruf_gegen_ungeduld(
        engpass.ruf_tempo(5.85, 18, 7, 2), ungeduld, 2960, engpass.entlastung(1.5), 1.45)
    e = tools_api.engpass(tmp_path, "lauf", nahrung={}, ungeduld=ungeduld)
    assert e["ruf"]["gegen_ungeduld"]["rest"] > mit_sturm["rest"] + 5
    assert tools_api._ausserhalb_sturm(zeilen)["season"] == 1
    nur_sturm = [stand(1, 7, 2, 5.0, 1.5)]
    assert tools_api._ausserhalb_sturm(nur_sturm) is nur_sturm[0]
