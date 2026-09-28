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
