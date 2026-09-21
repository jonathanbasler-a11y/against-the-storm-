"""Tests des HTML-Tabellenlesers gegen MediaWiki-typische Ausgabe."""

from __future__ import annotations

from ats_assistant.wikihtml import tabellen_aus_html

EINFACH = """
<html><body>
<table class="wikitable sortable">
<tr><th>Name</th><th>Rarity</th><th>Effect</th></tr>
<tr><td><a href="/x">Baptism of Fire</a></td><td>Legendary</td><td>-10 Hostility</td></tr>
<tr><td>Cannibalism</td><td>Epic</td><td>+3 Meat</td></tr>
</table>
</body></html>
"""


def test_kopfzeile_und_zeilen() -> None:
    t = tabellen_aus_html(EINFACH)[0]
    assert t.kopf == ["Name", "Rarity", "Effect"]
    assert t.als_dicts[0] == {"Name": "Baptism of Fire", "Rarity": "Legendary",
                              "Effect": "-10 Hostility"}
    assert len(t.als_dicts) == 2


def test_links_werden_zu_text() -> None:
    """Im gerenderten HTML steht der Name in einem <a>. Der Text zaehlt."""
    t = tabellen_aus_html(EINFACH)[0]
    assert t.als_dicts[0]["Name"] == "Baptism of Fire"


def test_rowspan_wird_ausgeschrieben() -> None:
    """Die Tabellen des Wikis benutzen rowspan. Wer ihn ignoriert, verrutscht
    die Spalten aller folgenden Zeilen."""
    html = """
    <table class="wikitable">
    <tr><th>Biome</th><th>Tree</th><th>Bonus</th></tr>
    <tr><td rowspan="2">Coral Forest</td><td>Mushwood</td><td>Mushrooms</td></tr>
    <tr><td>Musselsprout</td><td>Meat</td></tr>
    </table>
    """
    zeilen = tabellen_aus_html(html)[0].als_dicts
    assert zeilen[0] == {"Biome": "Coral Forest", "Tree": "Mushwood", "Bonus": "Mushrooms"}
    assert zeilen[1]["Biome"] == "Coral Forest"      # aus dem rowspan uebernommen
    assert zeilen[1]["Tree"] == "Musselsprout"


def test_colspan_wird_ausgeschrieben() -> None:
    html = """
    <table class="wikitable">
    <tr><th>A</th><th>B</th><th>C</th></tr>
    <tr><td colspan="2">breit</td><td>schmal</td></tr>
    </table>
    """
    zeile = tabellen_aus_html(html)[0].als_dicts[0]
    assert zeile["A"] == "breit" and zeile["B"] == "breit" and zeile["C"] == "schmal"


def test_nur_wikitables_wenn_vorhanden() -> None:
    """MediaWiki-Seiten stecken voller Layouttabellen. Die interessieren nicht."""
    html = """
    <table class="infobox"><tr><td>Layout</td></tr></table>
    <table class="wikitable"><tr><th>X</th></tr><tr><td>1</td></tr></table>
    """
    tabellen = tabellen_aus_html(html)
    assert len(tabellen) == 1 and tabellen[0].kopf == ["X"]


def test_ohne_wikitable_kommen_alle() -> None:
    html = '<table class="infobox"><tr><th>X</th></tr><tr><td>1</td></tr></table>'
    assert len(tabellen_aus_html(html)) == 1


def test_verschachtelte_tabellen() -> None:
    """Eine Tabelle in einer Zelle darf die aeussere nicht durcheinanderbringen."""
    html = """
    <table class="wikitable"><tr><th>Aussen</th></tr>
    <tr><td><table class="wikitable"><tr><th>Innen</th></tr><tr><td>i</td></tr></table></td></tr>
    </table>
    """
    tabellen = tabellen_aus_html(html)
    koepfe = [t.kopf for t in tabellen]
    assert ["Innen"] in koepfe and ["Aussen"] in koepfe


def test_style_und_script_landen_nicht_in_den_zellen() -> None:
    html = """
    <table class="wikitable"><tr><th>Name</th></tr>
    <tr><td><style>.x{color:red}</style>Jerky</td></tr></table>
    """
    assert tabellen_aus_html(html)[0].als_dicts[0]["Name"] == "Jerky"


def test_gleiche_kopfnamen_ueberschreiben_sich_nicht() -> None:
    html = """
    <table class="wikitable"><tr><th>Wert</th><th>Wert</th></tr>
    <tr><td>a</td><td>b</td></tr></table>
    """
    zeile = tabellen_aus_html(html)[0].als_dicts[0]
    assert set(zeile.values()) == {"a", "b"}


def test_leere_zeilen_fallen_weg() -> None:
    html = """
    <table class="wikitable"><tr><th>X</th></tr>
    <tr><td></td></tr><tr><td>1</td></tr></table>
    """
    assert tabellen_aus_html(html)[0].als_dicts == [{"X": "1"}]


def test_br_wird_zu_leerzeichen() -> None:
    html = '<table class="wikitable"><tr><th>X</th></tr><tr><td>a<br/>b</td></tr></table>'
    assert tabellen_aus_html(html)[0].als_dicts[0]["X"] == "a b"


def test_symbole_zaehlen_als_zellinhalt() -> None:
    """Rezeptzellen enthalten nur Icons. Ohne alt-Text gilt die Zeile als leer,
    und genau so kamen "Complex Food" und "Recipes" mit null Zeilen zurück."""
    html = """
    <table class="wikitable">
    <tr><th>Complex Food</th><th>Ingredients</th></tr>
    <tr><td><a href="/Jerky"><img src="j.png" alt="Jerky"></a></td>
        <td><img src="m.png" alt="Meat"> 5</td></tr>
    </table>
    """
    zeile = tabellen_aus_html(html)[0].als_dicts[0]
    assert zeile["Complex Food"] == "Jerky"
    assert zeile["Ingredients"] == "Meat 5"


def test_dateinamen_gelten_nicht_als_beschriftung() -> None:
    html = """
    <table class="wikitable"><tr><th>X</th></tr>
    <tr><td><img src="a.png" alt="File:Icon_Resource_Meat.png">Fleisch</td></tr></table>
    """
    assert tabellen_aus_html(html)[0].als_dicts[0]["X"] == "Fleisch"


def test_title_wird_genommen_wenn_alt_fehlt() -> None:
    html = ('<table class="wikitable"><tr><th>X</th></tr>'
            '<tr><td><img src="a.png" title="Planks"></td></tr></table>')
    assert tabellen_aus_html(html)[0].als_dicts[0]["X"] == "Planks"


def test_name_aus_bild_und_linktext_wird_nicht_verdoppelt() -> None:
    """<a href="/Bats"><img alt="Bats">Bats</a> liefert den Namen zweimal."""
    html = ('<table class="wikitable"><tr><th>Species</th></tr>'
            '<tr><td><a href="/Bats"><img src="b.png" alt="Bats">Bats</a></td></tr></table>')
    assert tabellen_aus_html(html)[0].als_dicts[0]["Species"] == "Bats"


def test_mehrwortiger_name_wird_nicht_verdoppelt() -> None:
    html = ('<table class="wikitable"><tr><th>X</th></tr>'
            '<tr><td><img alt="Royal Treasure Stag">Royal Treasure Stag</td></tr></table>')
    assert tabellen_aus_html(html)[0].als_dicts[0]["X"] == "Royal Treasure Stag"


def test_zwei_echte_werte_bleiben_stehen() -> None:
    """Nur die exakte Verdopplung der ganzen Zelle wird zusammengezogen."""
    html = ('<table class="wikitable"><tr><th>X</th></tr>'
            '<tr><td>5 Meat 5 Fuel</td></tr></table>')
    assert tabellen_aus_html(html)[0].als_dicts[0]["X"] == "5 Meat 5 Fuel"


def test_verschachtelte_tabelle_landet_in_der_zelle() -> None:
    """Die Rezeptseite legt die Zutaten in Tabellen INNERHALB der Zellen ab.

    Wer sie nur herauszieht, bekommt eine äussere Tabelle mit leeren Zellen --
    genau so kamen "Recipes" und "Complex Food" mit null Zeilen zurück.
    """
    html = """
    <table class="wikitable">
    <tr><th>Building</th><th>Ingredients</th><th>Product</th></tr>
    <tr><td>Smokehouse</td>
        <td><table class="wikitable"><tr><td>5</td><td>Meat</td></tr>
                                     <tr><td>2</td><td>Fuel</td></tr></table></td>
        <td>10 Jerky</td></tr>
    </table>
    """
    tabellen = tabellen_aus_html(html)
    aussen = next(t for t in tabellen if "Building" in t.kopf)
    zeile = aussen.als_dicts[0]
    assert zeile["Building"] == "Smokehouse"
    assert zeile["Ingredients"] == "5 Meat 2 Fuel"
    assert zeile["Product"] == "10 Jerky"


def test_innere_tabelle_bleibt_auch_einzeln_lesbar() -> None:
    html = """
    <table class="wikitable"><tr><th>A</th></tr>
    <tr><td><table class="wikitable"><tr><th>Innen</th></tr><tr><td>i</td></tr></table></td></tr>
    </table>
    """
    koepfe = [t.kopf for t in tabellen_aus_html(html)]
    assert ["Innen"] in koepfe and ["A"] in koepfe
