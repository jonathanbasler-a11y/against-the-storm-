"""Tests der Nahrungsempfehlung.

Gerechnet wird gegen eine kleine, von Hand gesetzte Wissensbasis: zwei
essbare Rohwaren, zwei Rezepte, ein Lager. Die Zahlen stammen aus den
Spieldaten (Rohnahrung 1,0, verarbeitete 2,0 bis 3,0), die Mengen sind
gewaehlt, damit die Faelle unterscheidbar bleiben.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ats_assistant import kb, nahrung


def wissensbasis(tmp_path: Path):
    conn = kb.connect(tmp_path / "kb.sqlite")
    for en, save_id, fuelle in (("Meat", "[Food Raw] Meat", 1.0),
                                ("Insects", "[Food Raw] Insects", 1.0),
                                ("Berries", "[Food Raw] Berries", 1.0),
                                ("Jerky", "[Food Processed] Jerky", 2.0),
                                ("Pickled Goods", "[Food Processed] Pickled Goods", 3.0),
                                ("Wood", "[Mat Raw] Wood", 0.0)):
        conn.execute(
            "INSERT INTO resources (en, save_id, eatable, eating_fullness) "
            "VALUES (?,?,?,?)", (en, save_id, 1 if fuelle else 0, fuelle))

    def rezept(id_, gebaeude, gruppen, produkt, menge, sekunden, sterne=1):
        conn.execute(
            "INSERT INTO recipes (id, building, inputs, stars, seconds, product, "
            " product_amount) VALUES (?,?,?,?,?,?,?)",
            (id_, gebaeude, json.dumps(gruppen), sterne, sekunden, produkt, menge))

    # Doerrfleisch: 5 Fleisch ODER 5 Insekten -> 10 Doerrfleisch (Faktor 4)
    rezept(1, "Smokehouse", [[{"menge": 5, "ware": "Meat"},
                              {"menge": 5, "ware": "Insects"}]], "Jerky", 10, 60)
    # Eingelegte Nahrung: 5 Beeren -> 10 Stueck (Faktor 6), aber langsamer
    rezept(2, "Cellar", [[{"menge": 5, "ware": "Berries"}]],
           "Pickled Goods", 10, 120)
    # Die Produktionstabelle fuehrt die verarbeiteten Waren. Ohne sie gilt
    # ein Erzeugnis als nicht belegt und faellt aus dem Rat.
    for produkt, gebaeude, sterne in (("Jerky", "Smokehouse", 3),
                                      ("Pickled Goods", "Cellar", 3)):
        conn.execute("INSERT INTO production (product, building, stars) VALUES (?,?,?)",
                     (produkt, gebaeude, sterne))
    conn.commit()
    return conn


def test_rezepte_werden_gegen_den_bestand_gerechnet(tmp_path: Path) -> None:
    conn = wissensbasis(tmp_path)
    liste = nahrung.vorschlaege(conn, {"[Food Raw] Meat": 20, "[Food Raw] Berries": 10})
    nach_produkt = {v.produkt: v for v in liste}

    doerr = nach_produkt["Jerky"]
    assert doerr.zyklen == 4                       # 20 Fleisch, 5 je Durchlauf
    assert doerr.saettigung_rein == 20             # 20 Fleisch a 1,0
    assert doerr.saettigung_raus == 80             # 40 Doerrfleisch a 2,0
    assert doerr.faktor == pytest.approx(4.0)

    eingelegt = nach_produkt["Pickled Goods"]
    assert eingelegt.zyklen == 2
    assert eingelegt.faktor == pytest.approx(6.0)
    # Der groessere Gewinn steht vorn, nicht der groessere Faktor.
    assert liste[0].produkt == "Jerky"
    conn.close()


def test_ohne_vollen_satz_zutaten_kein_vorschlag(tmp_path: Path) -> None:
    conn = wissensbasis(tmp_path)
    assert nahrung.vorschlaege(conn, {"[Food Raw] Meat": 4}) == []
    assert nahrung.vorschlaege(conn, {"[Mat Raw] Wood": 500}) == []
    conn.close()


def test_alternative_zutat_wird_genommen_wenn_die_erste_fehlt(tmp_path: Path) -> None:
    conn = wissensbasis(tmp_path)
    liste = nahrung.vorschlaege(conn, {"[Food Raw] Insects": 15})
    assert [z.ware for z in liste[0].zutaten] == ["Insects"]
    assert liste[0].zyklen == 3
    conn.close()


def test_engpass_ist_die_knappste_zutat(tmp_path: Path) -> None:
    conn = wissensbasis(tmp_path)
    conn.execute(
        "INSERT INTO recipes (id, building, inputs, stars, seconds, product, "
        " product_amount) VALUES (?,?,?,?,?,?,?)",
        (3, "Cookhouse", json.dumps([[{"menge": 2, "ware": "Meat"}],
                                     [{"menge": 8, "ware": "Berries"}]]),
         2, 30, "Pickled Goods", 6))
    conn.commit()
    liste = nahrung.vorschlaege(conn, {"[Food Raw] Meat": 40, "[Food Raw] Berries": 16})
    # Das Gebaeude im Vorschlag kommt aus der Produktionstabelle; welche
    # Seite das Rezept lieferte, steht daneben.
    kochhaus = [v for v in liste if v.gebaeude_laut_seite == "Cookhouse"][0]
    assert kochhaus.engpass == "Berries"           # 16/8 = 2 gegen 40/2 = 20
    assert kochhaus.zyklen == 2
    conn.close()


def test_reichweite_kommt_aus_dem_gemessenen_verbrauch(tmp_path: Path) -> None:
    conn = wissensbasis(tmp_path)
    # 0,1 Saettigung je Spielzeitsekunde -> 60 Saettigung sind 600 Sekunden.
    liste = nahrung.vorschlaege(conn, {"[Food Raw] Meat": 20},
                                verbrauch_pro_sekunde=-0.1)
    assert liste[0].gewinn == 60
    assert liste[0].reichweite_plus == pytest.approx(600.0)
    # Ohne Messung bleibt die Reichweite offen, die Rangfolge steht trotzdem.
    ohne = nahrung.vorschlaege(conn, {"[Food Raw] Meat": 20})
    assert ohne[0].reichweite_plus is None
    conn.close()


def test_rat_haelt_die_form_der_spec(tmp_path: Path) -> None:
    conn = wissensbasis(tmp_path)
    r = nahrung.rat(conn, {"[Food Raw] Meat": 20, "[Food Raw] Berries": 10},
                    verbrauch_pro_sekunde=-0.1, reichweite_sekunden=300)
    assert r.text().count("\n") == 2               # drei Saetze, nicht mehr
    assert "Smokehouse" in r.empfehlung
    assert "Faktor 4" in r.begruendung
    assert "300" not in r.empfehlung               # keine Aufzaehlung von Zahlen
    assert "5 auf 15 Minuten" in r.begruendung     # 300s + 600s
    assert "Cellar" in r.alternative
    conn.close()


def test_rat_sagt_auch_wenn_nichts_geht(tmp_path: Path) -> None:
    conn = wissensbasis(tmp_path)
    r = nahrung.rat(conn, {"[Mat Raw] Wood": 300})
    assert "Kein Verarbeitungsschritt" in r.empfehlung
    assert r.vorschlaege == []
    conn.close()


def test_deutsche_namen_kommen_aus_der_namenstabelle(tmp_path: Path) -> None:
    from ats_assistant import localization

    conn = wissensbasis(tmp_path)
    localization.import_localization(conn, [
        localization.Eintrag("Building_Smokehouse_Name", "Smokehouse",
                             "Räucherei", "building"),
        localization.Eintrag("Good_Jerky_Name", "Jerky", "Dörrfleisch", "resource"),
    ])
    r = nahrung.rat(conn, {"[Food Raw] Meat": 20})
    assert "Räucherei" in r.empfehlung and "Dörrfleisch" in r.empfehlung
    conn.close()


def test_produktionstabelle_schlaegt_den_seitentitel(tmp_path: Path) -> None:
    """"Dörrfleisch in der Makellosen Schmelzerei" war der Seitentitel."""
    conn = wissensbasis(tmp_path)
    conn.execute("UPDATE recipes SET building = 'Flawless Smelter' WHERE product = 'Jerky'")
    conn.execute("INSERT INTO production (product, building, stars) "
                 "VALUES ('Jerky', 'Butcher', 1)")
    conn.commit()
    v = [x for x in nahrung.vorschlaege(conn, {"[Food Raw] Meat": 20})][0]
    assert v.gebaeude == "Smokehouse"            # drei Sterne gewinnen
    assert v.sterne == 3
    assert v.gebaeude_laut_seite == "Flawless Smelter"   # der Widerspruch bleibt sichtbar
    conn.close()


def test_dasselbe_rezept_auf_mehreren_seiten_steht_nur_einmal_im_rat(tmp_path: Path) -> None:
    conn = wissensbasis(tmp_path)
    conn.execute("INSERT INTO recipes (id, building, inputs, stars, seconds, product, "
                 " product_amount) VALUES (9, 'Butcher', ?, 1, 90, 'Jerky', 10)",
                 (json.dumps([[{"menge": 5, "ware": "Meat"}]]),))
    conn.commit()
    doerr = [v for v in nahrung.vorschlaege(conn, {"[Food Raw] Meat": 20})
             if v.produkt == "Jerky"]
    assert len(doerr) == 1
    assert doerr[0].sekunden == 60               # der schnellere Eintrag gewinnt
    conn.close()


def test_rohnahrung_und_scheinrezepte_fallen_heraus(tmp_path: Path) -> None:
    """Zwei Arten von Zeilen, die kein Rat sind."""
    conn = wissensbasis(tmp_path)
    # Rohnahrung: die Produktionstabelle kennt sie nicht, weil sie aus
    # Lagern und Vorkommen kommt, nicht aus einem Rezept.
    conn.execute("INSERT INTO recipes (id, building, inputs, seconds, product, "
                 " product_amount) VALUES (20, 'Trappers Camp', ?, 60, 'Meat', 30)",
                 (json.dumps([[{"menge": 3, "ware": "Berries"}]]),))
    # Ein Erzeugnis unter seinen eigenen Zutaten: Lesefehler, kein Rezept.
    conn.execute("INSERT INTO recipes (id, building, inputs, seconds, product, "
                 " product_amount) VALUES (21, 'Flawless Smelter', ?, 60, 'Jerky', 30)",
                 (json.dumps([[{"menge": 3, "ware": "Jerky"}]]),))
    conn.commit()
    produkte = [v.produkt for v in nahrung.vorschlaege(
        conn, {"[Food Raw] Berries": 40, "[Food Processed] Jerky": 40})]
    assert "Meat" not in produkte
    assert produkte.count("Jerky") == 0 or all(
        v.zutaten[0].ware != "Jerky"
        for v in nahrung.vorschlaege(conn, {"[Food Processed] Jerky": 40}))
    # Mit nur_belegt=False kommt die Rohnahrung zurueck -- fuer die Nachschau,
    # nicht fuer den Rat.
    ohne = [v.produkt for v in nahrung.vorschlaege(
        conn, {"[Food Raw] Berries": 40}, nur_belegt=False)]
    assert "Meat" in ohne
    conn.close()


def test_ohne_tragende_kette_wird_die_fehlende_zutat_genannt(tmp_path: Path) -> None:
    """Der Fall vom Spielrechner: "lohnt sich nicht" und sonst nichts.

    Dörrfleisch braucht Fleisch **und** einen Brennstoff. Liegt nur Fleisch
    da, ist die Auskunft nicht "verarbeiten lohnt nicht", sondern welche
    Zutat fehlt — alles andere schickt den Spieler in dieselbe Sackgasse
    zurück.
    """
    conn = wissensbasis(tmp_path)
    for w in ("Coal", "Oil"):
        conn.execute("INSERT INTO resources (en, eatable) VALUES (?, 0)", (w,))
    conn.execute("DELETE FROM recipes")
    conn.execute(
        "INSERT INTO recipes (id, building, inputs, seconds, product, product_amount) "
        "VALUES (1, 'Smokehouse', ?, 60, 'Jerky', 10)",
        (json.dumps([[{"menge": 5, "ware": "Meat"}],
                     [{"menge": 2, "ware": "Coal"}, {"menge": 2, "ware": "Oil"}]]),))
    conn.commit()

    r = nahrung.rat(conn, {"[Food Raw] Meat": 40})
    assert "Kein Verarbeitungsschritt" in r.empfehlung
    assert "Jerky" in r.begruendung
    assert "Coal" in r.begruendung and "Oil" in r.begruendung
    assert "2 " in r.begruendung                     # die Menge steht dabei
    conn.close()


def test_huerden_bleiben_aus_wenn_niemand_danach_fragt(tmp_path: Path) -> None:
    """Die Liste wird nur gefüllt, wenn ein Aufrufer sie mitgibt."""
    conn = wissensbasis(tmp_path)
    huerden: list[dict] = []
    nahrung.vorschlaege(conn, {"[Food Raw] Meat": 2}, huerden=huerden)
    assert huerden                                   # mit Liste: gefüllt
    assert nahrung.vorschlaege(conn, {"[Food Raw] Meat": 2}) == []   # ohne: still
    conn.close()


# --------------------------------------------------------------------------
# Wenn die Rohware fehlt: womit beschaffen?
#
# Am Spielrechner, Jahr 1, Prestige 15, Nahrung für 103 Spielzeitsekunden:
# "Kein Verarbeitungsschritt lohnt sich. Kekse scheitert an einer Zutat: es
# fehlt 6 Mehl. Dasselbe gilt für Dörrfleisch, Paste, Pastete — erst Rohware
# sammeln, dann verarbeiten."
#
# Richtig, und genau dort hört die Auskunft auf. *Womit* sammeln steht in der
# Wissensbasis: Gebäude, deren Erzeugnis essbar ist, mit ihren Baukosten.
# --------------------------------------------------------------------------


def mit_sammelgebaeuden(conn):
    for en, kosten, produkte, plaetze in (
            ("Forager's Camp", '{"Wood": 3}', "Berries", 2),
            ("Trappers' Camp", '{"Wood": 5, "Planks": 3}', "Meat Leather", 2),
            ("Herbalists' Camp", '{"Planks": 6}', "Roots Herbs", 3),
            ("Woodcutters' Camp", '{"Wood": 3}', "Wood", 2)):
        conn.execute(
            "INSERT INTO buildings (en, cost, products, worker_slots, category) "
            "VALUES (?,?,?,?,'Gathering')", (en, kosten, produkte, plaetze))
    for en, essbar in (("Roots", 1), ("Herbs", 0), ("Leather", 0)):
        conn.execute("INSERT INTO resources (en, eatable, eating_fullness) "
                     "VALUES (?,?,?)", (en, essbar, 1.0 if essbar else 0.0))
    conn.commit()
    return conn


def test_rohquellen_nennt_nur_gebaeude_mit_essbarem_erzeugnis(tmp_path: Path) -> None:
    conn = mit_sammelgebaeuden(wissensbasis(tmp_path))
    quellen = nahrung.rohquellen(conn)
    namen = [q.gebaeude for q in quellen]

    assert "Forager's Camp" in namen and "Trappers' Camp" in namen
    assert "Woodcutters' Camp" not in namen        # Holz sättigt niemanden
    # Das Billigste zuerst: drei Holz vor fünf Holz und drei Brettern.
    assert namen[0] == "Forager's Camp"
    conn.close()


def test_rohquellen_traegt_waren_und_kosten_mit(tmp_path: Path) -> None:
    conn = mit_sammelgebaeuden(wissensbasis(tmp_path))
    quelle = {q.gebaeude: q for q in nahrung.rohquellen(conn)}["Trappers' Camp"]

    assert quelle.waren == ["Meat"]                # Leder ist nicht essbar
    assert quelle.kosten == {"Wood": 5.0, "Planks": 3.0}
    assert quelle.plaetze == 2
    conn.close()


def test_ohne_rohware_steht_im_rat_womit_sie_zu_holen_ist(tmp_path: Path) -> None:
    """Der eigentliche Fund: „erst Rohware sammeln" sagt nicht, womit."""
    conn = mit_sammelgebaeuden(wissensbasis(tmp_path))
    r = nahrung.rat(conn, {"[Food Raw] Meat": 2})

    assert "Kein Verarbeitungsschritt" in r.empfehlung
    assert "Sammellager" in r.alternative or "Forager" in r.alternative or \
           "Sammler" in r.alternative
    # Ein Name, eine Ware, ein Preis -- keine Gattungsbegriffe.
    assert "3 Wood" in r.alternative or "3 Holz" in r.alternative
    conn.close()


def test_ohne_sammelgebaeude_in_der_wissensbasis_bleibt_der_satz_ehrlich(
        tmp_path: Path) -> None:
    """Keine erfundenen Gebäude. Steht nichts da, wird nichts genannt."""
    conn = wissensbasis(tmp_path)
    r = nahrung.rat(conn, {"[Food Raw] Meat": 2})
    assert "Forager" not in r.alternative
    assert r.alternative                            # aber ein Satz steht da
    conn.close()


def test_ein_leer_gelesenes_lager_ist_kein_urteil(tmp_path: Path) -> None:
    """Der Fund vom 22.09.2026, Jahr 1, Prestige 15.

    Der Auszug trug `"lager": {}` und `"gebaeude": 0` — bei 600
    Spielzeitsekunden und einem vollen Lagerhaus auf dem Bildschirm. Die
    Auskunft „Kein Verarbeitungsschritt lohnt sich" war also gar keine
    Aussage über das Lager, sondern über ein leeres Dictionary. Das muss
    dastehen, statt als Urteil durchzugehen.
    """
    conn = mit_sammelgebaeuden(wissensbasis(tmp_path))
    r = nahrung.rat(conn, {})

    assert "gelesen" in r.empfehlung or "leer" in r.empfehlung
    assert "Verarbeitungsschritt" not in r.empfehlung
    assert "kb_probe" in r.alternative or "lage.py" in r.alternative
    conn.close()


# --------------------------------------------------------------------------
# QA-Runde 1 (23.09.2026). Am Spielrechner stand im Reiter „Nahrung":
# „Grill: 2 Insekten, 3 Eier werden zu Fleischspieße, 25 Sättigung mehr
# (Faktor 6.0)" -- ein Durchlauf, weil je Zutatengruppe die billigste
# Alternative für einen Durchlauf gewählt wurde.
# --------------------------------------------------------------------------


def _rezept(conn, id_, gebaeude, gruppen, produkt, menge, sekunden, sterne=1):
    conn.execute(
        "INSERT INTO recipes (id, building, inputs, stars, seconds, product, "
        " product_amount) VALUES (?,?,?,?,?,?,?)",
        (id_, gebaeude, json.dumps(gruppen), sterne, sekunden, produkt, menge))


def _grill(conn):
    conn.execute("INSERT INTO resources (en, save_id, eatable, eating_fullness) "
                 "VALUES ('Eggs', '[Food Raw] Eggs', 1, 1.0)")
    conn.execute("INSERT INTO resources (en, save_id, eatable, eating_fullness) "
                 "VALUES ('Skewers', '[Food Processed] Skewers', 1, 3.0)")
    _rezept(conn, 20, "Grill", [[{"menge": 2, "ware": "Insects"},
                                 {"menge": 3, "ware": "Meat"}],
                                [{"menge": 3, "ware": "Eggs"}]], "Skewers", 10, 60)
    conn.execute("INSERT INTO production (product, building, stars) "
                 "VALUES ('Skewers', 'Grill', 3)")
    conn.commit()


def test_die_alternative_mit_den_meisten_durchlaeufen_gewinnt(tmp_path: Path) -> None:
    """2 Insekten tragen einen Durchlauf, 60 Fleisch zwanzig."""
    conn = wissensbasis(tmp_path)
    _grill(conn)
    grill = [v for v in nahrung.vorschlaege(
        conn, {"[Food Raw] Insects": 2, "[Food Raw] Meat": 60, "[Food Raw] Eggs": 60})
        if v.produkt == "Skewers"][0]
    assert [z.ware for z in grill.zutaten] == ["Meat", "Eggs"]
    assert grill.zyklen == 20
    assert grill.gewinn == 600 - 120               # 200 Spieße à 3 gegen 60+60 roh
    conn.close()


def test_dieselbe_ware_in_zwei_gruppen_wird_nicht_doppelt_gezaehlt(tmp_path: Path) -> None:
    conn = wissensbasis(tmp_path)
    _rezept(conn, 21, "Cellar", [[{"menge": 2, "ware": "Insects"}, {"menge": 2, "ware": "Meat"}],
                                 [{"menge": 2, "ware": "Insects"}, {"menge": 2, "ware": "Berries"}]],
            "Pickled Goods", 10, 60)
    conn.commit()
    liste = nahrung.vorschlaege(conn, {"[Food Raw] Insects": 2})
    assert [v for v in liste if v.produkt == "Pickled Goods"] == []   # braucht 4 Insekten
    conn.close()


def test_nur_ganze_durchlaeufe_zaehlen(tmp_path: Path) -> None:
    """7 Fleisch sind ein Durchlauf zu 5, nicht 1,4."""
    conn = wissensbasis(tmp_path)
    doerr = [v for v in nahrung.vorschlaege(conn, {"[Food Raw] Meat": 7})
             if v.produkt == "Jerky"][0]
    assert doerr.zyklen == 1
    assert doerr.saettigung_rein == 5 and doerr.saettigung_raus == 20
    assert "5 Meat" in doerr.satz()
    conn.close()


def test_ein_wachsender_bestand_ist_kein_verbrauch(tmp_path: Path) -> None:
    conn = wissensbasis(tmp_path)
    liste = nahrung.vorschlaege(conn, {"[Food Raw] Meat": 20}, verbrauch_pro_sekunde=0.5)
    assert liste[0].reichweite_plus is None
    assert "Reichweite" not in liste[0].satz()
    conn.close()


def test_bei_doppelten_rezepten_bleibt_das_ergiebigere(tmp_path: Path) -> None:
    """Zwei Gebäude, ein Erzeugnis: das mit dem größeren Gewinn bleibt, und
    eine unbekannte Dauer schlägt keine bekannte."""
    conn = wissensbasis(tmp_path)
    _rezept(conn, 22, "Field Kitchen", [[{"menge": 5, "ware": "Meat"}]], "Jerky", 5, 30)
    _rezept(conn, 23, "Grill", [[{"menge": 5, "ware": "Meat"}]], "Jerky", 10, None)
    conn.commit()
    doerr = [v for v in nahrung.vorschlaege(conn, {"[Food Raw] Meat": 10})
             if v.produkt == "Jerky"]
    assert len(doerr) == 1
    assert doerr[0].gewinn == 30                   # 20 Dörrfleisch à 2 gegen 10 roh
    assert doerr[0].sekunden == 60                 # bekannt schlägt unbekannt
    conn.close()


def test_rohquellen_nennen_jede_ware_einmal(tmp_path: Path) -> None:
    """Wiki-Zellen wiederholen den Alt-Text der Symbole: „Meat Meat"."""
    conn = mit_sammelgebaeuden(wissensbasis(tmp_path))
    conn.execute("UPDATE buildings SET products = 'Meat Meat Leather Leather' "
                 "WHERE en = 'Trappers'' Camp'")
    conn.commit()
    quelle = {q.gebaeude: q for q in nahrung.rohquellen(conn)}["Trappers' Camp"]
    assert quelle.waren == ["Meat"]
    conn.close()


# --------------------------------------------------------------------------
# QA-Runde 5: Nachprüfung der eigenen Korrekturen
# --------------------------------------------------------------------------


def _keller_mit_zwei_gruppen(conn):
    _rezept(conn, 30, "Cellar", [[{"menge": 2, "ware": "Insects"}, {"menge": 2, "ware": "Meat"}],
                                 [{"menge": 2, "ware": "Insects"}, {"menge": 2, "ware": "Berries"}]],
            "Pickled Goods", 10, 60)
    conn.commit()


def test_eine_spaetere_gruppe_wird_bei_der_wahl_mitgedacht(tmp_path: Path) -> None:
    """Gruppe 1 nahm die Insekten, Gruppe 2 fand keine mehr -- obwohl Fleisch
    für Gruppe 1 und die Insekten für Gruppe 2 einen Durchlauf trugen."""
    conn = wissensbasis(tmp_path)
    _keller_mit_zwei_gruppen(conn)
    keller = [v for v in nahrung.vorschlaege(conn, {"[Food Raw] Insects": 2, "[Food Raw] Meat": 2})
              if v.gebaeude_laut_seite == "Cellar" or v.produkt == "Pickled Goods"]
    assert keller and keller[0].zyklen == 1
    assert sorted(z.ware for z in keller[0].zutaten) == ["Insects", "Meat"]
    conn.close()


def test_bei_gleichstand_zaehlt_die_ganze_kombination(tmp_path: Path) -> None:
    """20 Insekten, 20 Fleisch: Insekten+Insekten tragen 5, Fleisch+Insekten 10."""
    conn = wissensbasis(tmp_path)
    _keller_mit_zwei_gruppen(conn)
    keller = [v for v in nahrung.vorschlaege(conn, {"[Food Raw] Insects": 20, "[Food Raw] Meat": 20})
              if v.produkt == "Pickled Goods"][0]
    assert keller.zyklen == 10
    conn.close()


def test_dieselbe_ware_steht_im_satz_einmal(tmp_path: Path) -> None:
    conn = wissensbasis(tmp_path)
    _keller_mit_zwei_gruppen(conn)
    keller = [v for v in nahrung.vorschlaege(conn, {"[Food Raw] Insects": 20})
              if v.produkt == "Pickled Goods"][0]
    assert keller.satz().count("Insects") == 1
    assert "20 Insects" in keller.satz()
    conn.close()
