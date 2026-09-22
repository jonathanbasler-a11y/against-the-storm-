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
