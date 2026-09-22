"""Tests der Wissensbasis: Aufbau, Belastbarkeit, Nachschlag."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from ats_assistant import kb


def schreibe_csv(pfad: Path, zeilen: list[dict]) -> Path:
    felder = ["en", "de", "kind", "category", "confidence", "source", "verified_at", "note"]
    with pfad.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        for z in zeilen:
            w.writerow({f: z.get(f, "") for f in felder})
    return pfad


def test_schema_laesst_sich_mehrfach_anlegen(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    conn.close()
    conn = kb.connect(tmp_path / "kb.sqlite")   # zweites Mal darf nicht scheitern
    assert kb.coverage(conn)["tabellen"]["buildings"] == 0
    conn.close()


def test_belegtes_wird_nicht_von_geratenem_ueberschrieben(tmp_path: Path) -> None:
    """Der Kern der Namenstabelle: eine Screenshot-Bestaetigung ist mehr wert
    als eine Zeile aus der Recherche, egal in welcher Reihenfolge sie kommen."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.seed_name_map(conn, schreibe_csv(tmp_path / "a.csv", [
        {"en": "bricks", "de": "Ziegel", "kind": "resource", "confidence": "screenshot"},
    ]))
    kb.seed_name_map(conn, schreibe_csv(tmp_path / "b.csv", [
        {"en": "bricks", "de": "Ziegel", "kind": "resource", "confidence": "guessed"},
    ]))
    zeile = conn.execute("SELECT confidence FROM name_map WHERE en='bricks'").fetchone()
    assert zeile["confidence"] == "screenshot"
    conn.close()


def test_geratenes_wird_von_belegtem_ueberschrieben(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.seed_name_map(conn, schreibe_csv(tmp_path / "a.csv", [
        {"en": "oil", "de": "Öl", "kind": "resource", "confidence": "guessed"},
    ]))
    kb.seed_name_map(conn, schreibe_csv(tmp_path / "b.csv", [
        {"en": "oil", "de": "Öl", "kind": "resource", "confidence": "screenshot+save"},
    ]))
    zeile = conn.execute("SELECT confidence FROM name_map WHERE en='oil'").fetchone()
    assert zeile["confidence"] == "screenshot+save"
    conn.close()


def test_nachschlag_nimmt_deutsch_und_englisch(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.seed_name_map(conn, schreibe_csv(tmp_path / "a.csv", [
        {"en": "lumber_mill", "de": "Sägewerk", "kind": "building", "confidence": "spec_seed"},
    ]))
    assert kb.lookup(conn, "Sägewerk")[0]["en"] == "lumber_mill"
    assert kb.lookup(conn, "lumber_mill")[0]["de"] == "Sägewerk"
    assert kb.lookup(conn, "sägewerk")[0]["en"] == "lumber_mill"   # Schreibweise egal
    assert kb.lookup(conn, "gibtsnicht") == []
    conn.close()


def test_nachschlag_sortiert_belegtes_nach_vorn(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.seed_name_map(conn, schreibe_csv(tmp_path / "a.csv", [
        {"en": "pack_of_crops", "de": "Erntepaket", "kind": "resource", "confidence": "guessed"},
        {"en": "pack_of_crops", "de": "Feldfruchtpaket", "kind": "resource", "confidence": "screenshot"},
    ]))
    treffer = kb.lookup(conn, "pack_of_crops")
    assert treffer[0]["de"] == "Feldfruchtpaket"
    conn.close()


def test_save_ids_werden_nach_art_einsortiert(tmp_path: Path) -> None:
    ids = tmp_path / "ids"
    ids.mkdir()
    (ids / "MetaSave__root_content_buildings.txt").write_text(
        "Bakery\nBeaver House\nBrewery\n", encoding="utf-8")
    (ids / "MetaSave__root_content_effects.txt").write_text(
        "Crystaline Water\nLessHostilityPerWoodcutter\n", encoding="utf-8")
    (ids / "WorldSave__root_cycle_seenEvents.txt").write_text(
        "Gambler\nLoremaster\n", encoding="utf-8")

    conn = kb.connect(tmp_path / "kb.sqlite")
    zaehler = kb.import_save_ids(conn, ids)
    assert zaehler["building"] == 3
    assert zaehler["effect"] == 2
    assert zaehler["event"] == 2
    conn.close()


def test_offene_ids_sind_die_sollvorgabe_fuer_den_scraper(tmp_path: Path) -> None:
    """Was der Spielstand kennt und die Wissensbasis nicht, muss auffallen."""
    ids = tmp_path / "ids"
    ids.mkdir()
    (ids / "MetaSave__root_content_buildings.txt").write_text(
        "Bakery\nBrewery\n", encoding="utf-8")

    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.import_save_ids(conn, ids)
    kb.seed_name_map(conn, schreibe_csv(tmp_path / "a.csv", [
        {"en": "Bakery", "de": "Bäckerei", "kind": "building", "confidence": "guessed"},
    ]))
    offen = kb.unmatched_save_ids(conn)
    assert offen == ["Brewery"]
    conn.close()


def test_versionsabweichung_haengt_eine_warnung_an(tmp_path: Path) -> None:
    """Die Spec verlangt: bei Abweichung warnen, nicht stillschweigend ausliefern."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    ohne = kb.record_page(conn, "Bakery", 123, "2026-01-01", "1.10", "1.10.4")
    mit = kb.record_page(conn, "Smokehouse", 124, "2025-01-01", "1.9", "1.10.4")
    assert ohne is None
    assert mit is not None and "1.9" in mit
    zeile = conn.execute("SELECT warning FROM source_pages WHERE title='Smokehouse'").fetchone()
    assert zeile["warning"] == mit
    conn.close()


def test_fehlende_spalten_werden_ergaenzt(tmp_path: Path) -> None:
    """Eine Datenbank aus einer früheren Fassung muss weiterbenutzbar sein.

    CREATE TABLE IF NOT EXISTS ändert an einer bestehenden Tabelle nichts --
    ohne Wanderung scheitert der nächste Schreibzugriff mit
    "table species has no column named resilience".
    """
    import sqlite3

    pfad = tmp_path / "alt.sqlite"
    alt = sqlite3.connect(pfad)
    alt.execute("CREATE TABLE species (en TEXT PRIMARY KEY, base_resolve REAL)")
    alt.execute("INSERT INTO species (en, base_resolve) VALUES ('Beavers', 10)")
    alt.commit()
    alt.close()

    conn = kb.connect(pfad)
    spalten = {r[1] for r in conn.execute("PRAGMA table_info(species)")}
    assert {"resilience", "demand", "decadence", "comfort"} <= spalten
    # Die vorhandene Zeile überlebt die Wanderung
    assert conn.execute("SELECT base_resolve FROM species WHERE en='Beavers'"
                        ).fetchone()["base_resolve"] == 10
    kb.import_species(conn, [{"Species": "Beavers", "Resilience": "Low"}])
    assert conn.execute("SELECT resilience FROM species WHERE en='Beavers'"
                        ).fetchone()["resilience"] == "Low"
    conn.close()


def test_wanderung_laeuft_zweimal_ohne_schaden(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    assert kb.migrate(conn) == []      # frisch angelegt, nichts zu ergänzen
    conn.close()


def test_wanderung_fasst_fremde_tabellen_nicht_an(tmp_path: Path) -> None:
    import sqlite3

    pfad = tmp_path / "fremd.sqlite"
    fremd = sqlite3.connect(pfad)
    fremd.execute("CREATE TABLE notizen (text TEXT)")
    fremd.execute("INSERT INTO notizen VALUES ('bleibt')")
    fremd.commit()
    fremd.close()

    conn = kb.connect(pfad)
    assert conn.execute("SELECT text FROM notizen").fetchone()["text"] == "bleibt"
    conn.close()


def test_index_auf_neuer_spalte_scheitert_nicht(tmp_path: Path) -> None:
    """Das Schema legt einen Index auf recipes(product) an. An einer
    bestehenden Datenbank ohne diese Spalte scheiterte das mit
    "no such column: product" -- die Wanderung lief erst danach."""
    import sqlite3

    pfad = tmp_path / "alt.sqlite"
    alt = sqlite3.connect(pfad)
    alt.execute("CREATE TABLE recipes (id INTEGER PRIMARY KEY, building TEXT)")
    alt.execute("INSERT INTO recipes (building) VALUES ('Butcher')")
    alt.commit()
    alt.close()

    conn = kb.connect(pfad)       # darf nicht werfen
    spalten = {r[1] for r in conn.execute("PRAGMA table_info(recipes)")}
    assert {"product", "stars", "seconds"} <= spalten
    assert conn.execute("SELECT building FROM recipes").fetchone()["building"] == "Butcher"
    indizes = {r["name"] for r in conn.execute("PRAGMA index_list(recipes)")}
    assert "recipes_product" in indizes
    conn.close()


# --------------------------------------------------------------------------
# Tabellen von der Seite Difficulty und der Seite Buildings
#
# Die Zeilen unten sind woertlich aus dem Bericht vom 22.09.2026 uebernommen
# (diagnostics/wiki-html-20260922-065530.txt). Geschrieben wird gegen Belege,
# nicht gegen vermutete Spaltennamen.
# --------------------------------------------------------------------------


def test_prestige_kommt_von_der_seite_difficulty(tmp_path: Path) -> None:
    """Der Kopf heisst dort zweimal "Description" -- Stufe und Satz."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    n = kb.import_prestige(conn, [
        {"Description": "1", "Description_2": "More Reputation required to win.",
         "Modifier": "Prestigious Expedition",
         "Explanation": "Only the best Viceroys can embark on a Prestigious Expedition."},
        {"Description": "2", "Description_2": "The Storm Season lasts longer.",
         "Modifier": "Crumbling Seal", "Explanation": "One of the seals is loosening."},
        {"Description": "Level", "Modifier": "Modifier"},      # Kopfzeile
    ], source_page="Difficulty")
    assert n == 2
    zeile = conn.execute("SELECT * FROM prestige WHERE level = 2").fetchone()
    assert zeile["modifier_en"] == "Crumbling Seal"
    assert zeile["effect"].startswith("The Storm Season lasts longer.")
    assert "loosening" in zeile["effect"]                       # Erklaerung haengt dran
    conn.close()


def test_entwuerfe_ergaenzen_die_baukosten_statt_sie_zu_loeschen(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    conn.execute("INSERT INTO buildings (en, cost) VALUES ('Smokehouse', '{\"Planks\": 5}')")
    conn.commit()
    n = kb.import_blueprints(conn, [
        {"Blueprint": "Smokehouse", "Unlock or Upgrade": "Unlocked on Level 3"},
        {"Blueprint": "Woodcutters' Camp", "Unlock or Upgrade": "(always available)"},
        {"Blueprint": "Blueprint", "Unlock or Upgrade": "Unlock or Upgrade"},
    ], source_page="Buildings")
    assert n == 2
    zeile = conn.execute("SELECT * FROM buildings WHERE en = 'Smokehouse'").fetchone()
    assert zeile["unlock"] == "Unlocked on Level 3"
    assert zeile["cost"] == '{"Planks": 5}'                     # nicht verloren
    conn.close()


def test_rezept_ohne_gebaeudespalte_bekommt_die_seite(tmp_path: Path) -> None:
    """193 Rezepte standen ohne Gebaeude da -- sie stehen auf Gebaeudeseiten."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.seed_name_map(conn, schreibe_csv(tmp_path / "namen.csv", [
        {"en": "Smokehouse", "de": "Räucherei", "kind": "building",
         "confidence": "localization"},
    ]))
    zeilen = [{"Ingredient #1": "5 Meat", "Product": "Jerky", "#": "10",
               "Grade": "★★ 2:06"}]
    assert kb.import_recipes(conn, zeilen, source_page="Smokehouse",
                             gebaeude_default="Smokehouse") == 1
    assert conn.execute("SELECT building FROM recipes").fetchone()[0] == "Smokehouse"

    # Eine Seite, die kein Gebaeude ist, darf nicht als eines durchgehen.
    conn.execute("DELETE FROM recipes")
    kb.import_recipes(conn, zeilen, source_page="Coastal Grove",
                      gebaeude_default="Coastal Grove")
    assert conn.execute("SELECT building FROM recipes").fetchone()[0] is None
    conn.close()
