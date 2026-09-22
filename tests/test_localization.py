"""Tests der Lokalisierung: nachgeschlagene Namen schlagen geratene."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from ats_assistant import kb, localization


def schreibe_saat(pfad: Path, zeilen: list[dict]) -> Path:
    felder = ["en", "de", "kind", "category", "confidence", "source",
              "verified_at", "note"]
    with pfad.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        for z in zeilen:
            w.writerow({f: z.get(f, "") for f in felder})
    return pfad


def schreibe_strings(verzeichnis: Path, strings: dict[str, dict[str, str]],
                     mapping: dict | None = None) -> Path:
    verzeichnis.mkdir(parents=True, exist_ok=True)
    (verzeichnis / "de_translations.json").write_text(
        json.dumps({"strings": strings}), encoding="utf-8")
    if mapping is not None:
        (verzeichnis / "de_en_mapping.json").write_text(
            json.dumps({"wiki_en_to_de": mapping}), encoding="utf-8")
    return verzeichnis


STRINGS = {
    "Good_PickledGoods_Name": {"en": "Pickled Goods", "de": "Eingelegte Nahrung"},
    "Good_Wood_Name": {"en": "Wood", "de": "Holz"},
    "Good_Reed_Name": {"en": "Reed", "de": "Schilf"},
    "Building_Beanery_Name": {"en": "Beanery", "de": "Imbiss"},
    "Building_HarvesterCamp_Name": {"en": "Harvesters' Camp", "de": "Erntelager"},
    "Common_Clearance": {"en": "Clearance", "de": "Sommer"},
    "Label_Reward_Impatience": {"en": "Impatience", "de": "Ungeduld"},
    # Kein Name, sondern Fliesstext -- darf nicht in die Tabelle geraten.
    "Dialogue_Trader_Hello": {"en": "Good day!", "de": "Guten Tag!"},
}


def test_nur_namen_werden_uebernommen() -> None:
    posten = localization.eintraege(STRINGS)
    en = {e.en for e in posten}
    assert "Pickled Goods" in en and "Beanery" in en
    assert "Good day!" not in en          # Dialog ist kein Name
    assert "Clearance" not in en          # steht unter Common_, nicht _Name


def test_konzepte_kommen_ueber_die_englische_seite() -> None:
    gefunden, offen = localization.konzepte(
        STRINGS, {"Clearance": "season", "Impatience": "concept",
                  "Hostility": "concept"})
    nach_en = {e.en: e.de for e in gefunden}
    assert nach_en == {"Clearance": "Sommer", "Impatience": "Ungeduld"}
    # Hostility steht im Spiel nur im Satz. Das wird gemeldet, nicht geraten.
    assert offen == ["Hostility"]


def test_geratenes_wird_ersetzt_und_bleibt_nachlesbar(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.seed_name_map(conn, schreibe_saat(tmp_path / "saat.csv", [
        {"en": "pickled_goods", "de": "Eingelegte Waren", "kind": "resource",
         "confidence": "guessed", "source": "research"},
        {"en": "wood", "de": "Holz", "kind": "resource", "confidence": "save_id",
         "note": "Save-ID: [Mat Raw] Wood"},
    ]))
    bericht = localization.import_localization(
        conn, localization.eintraege(STRINGS), stand="2026-09-22")

    assert [w[:3] for w in bericht.widerlegt] == [
        ("Pickled Goods", "Eingelegte Waren", "Eingelegte Nahrung")]
    assert ("Wood", "Holz") in bericht.bestaetigt

    # Die falsche Zeile ist weg -- aber nicht spurlos.
    assert kb.lookup(conn, "Eingelegte Waren") == []
    treffer = kb.lookup(conn, "pickled_goods")
    assert treffer and treffer[0]["de"] == "Eingelegte Nahrung"
    assert treffer[0]["confidence"] == "localization"
    alt = conn.execute("SELECT de, replaced_by FROM retired_names").fetchone()
    assert (alt["de"], alt["replaced_by"]) == ("Eingelegte Waren", "Eingelegte Nahrung")

    # Was die bestaetigte Zeile an Beiwerk trug, geht nicht verloren.
    holz = kb.lookup(conn, "Holz")[0]
    assert holz["note"] == "Save-ID: [Mat Raw] Wood"
    conn.close()


def test_eigene_bezeichner_treffen_ueber_aliase(tmp_path: Path) -> None:
    """`reeds` heisst im Spiel "Reed" -- sonst bliebe Schilfrohr stehen."""
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.seed_name_map(conn, schreibe_saat(tmp_path / "saat.csv", [
        {"en": "reeds", "de": "Schilfrohr", "kind": "resource", "confidence": "guessed"},
    ]))
    bericht = localization.import_localization(conn, localization.eintraege(STRINGS))
    assert [w[1:3] for w in bericht.widerlegt] == [("Schilfrohr", "Schilf")]
    assert kb.lookup(conn, "reeds")[0]["de"] == "Schilf"
    conn.close()


def test_beobachtetes_wird_nicht_geloescht_sondern_gemeldet(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.seed_name_map(conn, schreibe_saat(tmp_path / "saat.csv", [
        {"en": "Beanery", "de": "Imbissbude", "kind": "building",
         "confidence": "screenshot"},
    ]))
    bericht = localization.import_localization(conn, localization.eintraege(STRINGS))
    assert bericht.widerlegt == []
    assert [a[1:3] for a in bericht.abweichend] == [("Imbissbude", "Imbiss")]
    # Beide Zeilen stehen, die nachgeschlagene zuerst.
    treffer = kb.lookup(conn, "Beanery")
    assert [t["confidence"] for t in treffer] == ["localization", "screenshot"]
    conn.close()


def test_beobachteter_deutscher_name_bekommt_seine_englische_seite(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    kb.seed_name_map(conn, schreibe_saat(tmp_path / "saat.csv", [
        {"en": "", "de": "Erntelager", "kind": "building", "confidence": "observed",
         "note": "Auftrag LAGER: 0/1 Erntelager"},
    ]))
    bericht = localization.import_localization(conn, localization.eintraege(STRINGS))
    assert bericht.geschlossen == [("Erntelager", "Harvesters' Camp")]
    treffer = kb.lookup(conn, "Erntelager")[0]
    assert treffer["en"] == "Harvesters' Camp"
    assert treffer["note"] == "Auftrag LAGER: 0/1 Erntelager"   # Beleg bleibt
    conn.close()


def test_zweiter_lauf_aendert_nichts(tmp_path: Path) -> None:
    conn = kb.connect(tmp_path / "kb.sqlite")
    posten = localization.eintraege(STRINGS)
    localization.import_localization(conn, posten)
    vorher = conn.execute("SELECT COUNT(*) FROM name_map").fetchone()[0]
    bericht = localization.import_localization(conn, posten)
    assert conn.execute("SELECT COUNT(*) FROM name_map").fetchone()[0] == vorher
    assert bericht.widerlegt == [] and bericht.bestaetigt == []
    conn.close()


def test_csv_hin_und_zurueck(tmp_path: Path) -> None:
    posten = localization.eintraege(STRINGS)
    pfad = tmp_path / "namen.csv"
    assert localization.schreibe_csv(posten, pfad) == len(posten)
    zurueck = localization.lade_csv(pfad)
    assert {(e.en, e.de, e.kind) for e in zurueck} == {(e.en, e.de, e.kind) for e in posten}


def test_lade_findet_dateien_mit_vorangestelltem_kuerzel(tmp_path: Path) -> None:
    verzeichnis = tmp_path / "abzug"
    verzeichnis.mkdir()
    (verzeichnis / "1ba510b1-de_translations.json").write_text(
        json.dumps({"strings": STRINGS}), encoding="utf-8")
    posten = localization.lade(verzeichnis)
    assert any(e.en == "Pickled Goods" for e in posten)
    assert any(e.en == "Impatience" for e in posten)     # Konzeptdurchgang lief


def test_grundsteine_unter_reward_werden_mitgenommen() -> None:
    """"Pilzführer" ist Reward_MushroomSpecialization_Name, nicht Effect_.

    Der grosse Teil der Grundsteine steht unter diesem Praefix. Es
    auszulassen hiess, ausgerechnet die Kategorie auszulassen, um die es in
    SPEC.md geht -- aufgefallen an einem Auswahlbildschirm, auf dem beide
    angebotenen Namen in der Tabelle fehlten.
    """
    strings = {
        "Reward_MushroomSpecialization_Name": {"en": "Fungal Guide", "de": "Pilzführer"},
        "Reward_PacksRawProd_Name": {"en": "Export Specialization",
                                     "de": "Exportspezialisierung"},
        "MetaReward_HearthServices_Name": {"en": "The Commons", "de": "Das Gemeindeland"},
    }
    nach_art = {e.en: e.kind for e in localization.eintraege(strings)}
    assert nach_art["Fungal Guide"] == "effect"
    assert nach_art["Export Specialization"] == "effect"
    assert nach_art["The Commons"] == "meta"
