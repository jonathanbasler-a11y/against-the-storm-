"""Tests des Namensabgleichs.

Die Texterkennung muss den Namen nicht richtig lesen -- nur nah genug,
dass der Abgleich eindeutig wird. Die Beispiele sind die zwei Namen, die
am 22.09.2026 tatsaechlich auf dem Auswahlbildschirm standen, mit den
Lesefehlern, die eine Texterkennung typischerweise macht.
"""

from __future__ import annotations

from pathlib import Path

from ats_assistant import kb, localization, namen_match


def tabelle(tmp_path: Path):
    conn = kb.connect(tmp_path / "kb.sqlite")
    localization.import_localization(conn, [
        localization.Eintrag("Reward_MushroomSpecialization_Name",
                             "Fungal Guide", "Pilzführer", "effect"),
        localization.Eintrag("Reward_PacksRawProd_Name",
                             "Export Specialization", "Exportspezialisierung", "effect"),
        localization.Eintrag("Effect_MushroomInFarms_Name",
                             "Mushroom Seedlings", "Pilzsämlinge", "effect"),
        localization.Eintrag("Building_Smokehouse_Name",
                             "Smokehouse", "Räucherei", "building"),
    ])
    return conn


def test_grossschrift_und_fehlender_umlaut_treffen_trotzdem(tmp_path: Path) -> None:
    conn = tabelle(tmp_path)
    kand = namen_match.kandidaten(conn, ("effect",))
    for gelesen in ("PILZFÜHRER", "Pilzfuhrer", "PlLZFUHRER", "PILZFÜHRER "):
        beste = namen_match.eindeutig(namen_match.passe(gelesen, kand))
        assert beste is not None and beste.en == "Fungal Guide", gelesen
    conn.close()


def test_zwei_aehnliche_namen_bleiben_unentschieden(tmp_path: Path) -> None:
    """"Pilzführer" und "Pilzsämlinge" fangen gleich an -- das genügt nicht."""
    conn = tabelle(tmp_path)
    kand = namen_match.kandidaten(conn, ("effect",))
    treffer = namen_match.passe("Pilz", kand, mindest=0.3)
    assert len(treffer) >= 2
    # Wer zu wenig gelesen hat, bekommt keine Auskunft, sondern die Kandidaten.
    assert namen_match.eindeutig(treffer, abstand=0.3) is None
    conn.close()


def test_falte_zieht_zusammen_was_die_erkennung_verwechselt() -> None:
    assert namen_match.falte("PILZFÜHRER") == namen_match.falte("pilzfuhrer")
    assert namen_match.falte("PlLZFUHRER") == namen_match.falte("Pilzführer")
    assert namen_match.falte("Straße") == namen_match.falte("STRASSE")
    assert namen_match.falte("") == ""


def test_die_art_grenzt_ein(tmp_path: Path) -> None:
    """Auf dem Grundsteinbildschirm stehen keine Gebäudenamen."""
    conn = tabelle(tmp_path)
    nur_effekte = namen_match.kandidaten(conn, ("effect",))
    assert all(k[2] == "effect" for k in nur_effekte)
    assert namen_match.passe("Räucherei", nur_effekte) == []
    conn.close()


def test_lies_auswahl_liefert_namen_statt_rohtext(tmp_path: Path) -> None:
    conn = tabelle(tmp_path)
    out = namen_match.lies_auswahl(conn, ["PILZFÜHRER", "EXPORTSPEZIALISIERUNG", "~~~"])
    assert [o["en"] for o in out[:2]] == ["Fungal Guide", "Export Specialization"]
    assert all(o["eindeutig"] for o in out[:2])
    # Unlesbares wird nicht geraten.
    assert out[2]["eindeutig"] is False and out[2]["en"] is None
    conn.close()
