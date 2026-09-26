"""Community-Tierlisten: Laden, Schreibweisen, mehrere Quellen, echte Datei."""

from __future__ import annotations

import csv
from pathlib import Path

from ats_assistant import berater, tierlisten


def _csv(pfad: Path, zeilen: list[dict]) -> Path:
    felder = ["kategorie", "en", "stufe", "quelle", "url", "stand", "kontext", "notiz"]
    with pfad.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=felder)
        w.writeheader()
        for z in zeilen:
            w.writerow({f: z.get(f, "") for f in felder})
    return pfad


def test_schreibweisen_und_mehrere_quellen(tmp_path: Path) -> None:
    pfad = _csv(tmp_path / "t.csv", [
        {"kategorie": "gebaeude", "en": "Trappers' Camp", "stufe": "A", "quelle": "X",
         "stand": "2026-09", "kontext": "Prestige 9"},
        {"kategorie": "gebaeude", "en": "Trappers' Camp", "stufe": "C", "quelle": "Y"},
        {"kategorie": "biom", "en": "Marshlands", "stufe": "B", "quelle": "Z"},
        {"kategorie": "unsinn", "en": "Egal", "stufe": "A", "quelle": "Z"},
        {"kategorie": "volk", "en": "Harpy", "stufe": "Q", "quelle": "Z"}])
    lager = tierlisten.nachsehen("gebaeude", "Trapper's Camp", pfad)
    assert [s["stufe"] for s in lager] == ["A", "C"]
    assert lager[0]["kontext"] == "Prestige 9" and lager[1]["stand"] == "unbekannt"
    assert tierlisten.nachsehen("biom", "The Marshlands", pfad)[0]["stufe"] == "B"
    assert tierlisten.nachsehen("volk", "Harpy", pfad) == []      # Stufe ungültig
    assert tierlisten.kurz(lager) == "A (X, 2026-09, Prestige 9) / C (Y)"


def test_fehlende_datei_ist_leer(tmp_path: Path) -> None:
    assert tierlisten.nachsehen("volk", "Harpy", tmp_path / "fehlt.csv") == []


def test_die_echte_datei_ist_sauber() -> None:
    with tierlisten.PFAD.open(encoding="utf-8", newline="") as fh:
        zeilen = list(csv.DictReader(fh))
    assert zeilen
    gesehen = set()
    for z in zeilen:
        assert z["kategorie"] in tierlisten.KATEGORIEN, z
        assert z["stufe"] in tierlisten.STUFEN, z
        assert z["url"].startswith("https://") and z["stand"] and z["quelle"], z
        schluessel = (z["kategorie"], tierlisten.schluessel(z["en"]), z["quelle"])
        assert schluessel not in gesehen, z
        gesehen.add(schluessel)


def test_der_rat_bekommt_die_stufen() -> None:
    auszug = berater.kontext(
        zustand={"jahr": 1, "spezies": ["Harpy", "Lizard"], "biom": "The Marshlands"},
        auswahl={"angebot": [{"de": "Verlorene Vorräte", "en": "Lost Supplies",
                              "kind": "effect", "guete": 1.0, "belegt": True},
                             {"de": "Unbekannt", "en": "Nichts", "kind": "effect",
                              "guete": 1.0, "belegt": True}]},
        wissen={"bauplan_vergleich": [{"gebaeude": "Ranch", "waren": []}]})
    assert auszug["auswahl"][0]["tier"][0]["stufe"] == "B"
    assert "tier" not in auszug["auswahl"][1]
    assert auszug["bauplan_vergleich"][0]["tier"][0]["stufe"] == "A"
    assert list(auszug["siedlung"]["voelker_tier"]) == ["Harpy"]
    assert auszug["siedlung"]["biom_tier"][0]["stufe"] == "B"
    berater.pruefe_auszug(auszug)
    text = " ".join(berater.systemtext().split())
    assert "die Stufe nennen" in text and "sag in einem Satz warum" in text
