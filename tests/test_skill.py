"""Der Berater-Skill muss die Form einhalten, die die Spec vorgibt."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parent.parent / ".claude" / "skills"
SKILL = SKILLS / "ats-advisor" / "SKILL.md"
ALLE = sorted(SKILLS.glob("*/SKILL.md"))


@pytest.fixture(scope="module")
def text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_skill_existiert() -> None:
    assert SKILL.exists()


def test_kopf_hat_name_und_beschreibung(text: str) -> None:
    kopf = text.split("---")[1]
    assert re.search(r"^name:\s*ats-advisor", kopf, re.M)
    assert re.search(r"^description:\s*\S", kopf, re.M)


def test_ausgabeformat_steht_drin(text: str) -> None:
    """Eine Empfehlung, ein Satz Begründung, ein Satz Alternative."""
    assert "Eine Empfehlung" in text
    assert "Alternative" in text
    assert "Keine Aufzählung" in text


def test_alle_heuristiken_der_spec_kommen_vor(text: str) -> None:
    for begriff in ("Nahrung schlägt alles", "Feindseligkeitssenkung",
                    "wertlos", "Korallenwald", "Bambusebene", "Felsschlucht",
                    "Legendary", "Rerolls"):
        assert begriff in text, begriff


def test_gemessene_zahlen_statt_behaupteter(text: str) -> None:
    """Die Sättigungswerte stammen aus den Spieldaten, nicht aus der Recherche."""
    assert "1,0" in text and "2,0" in text and "3,0" in text
    assert "300 Spielzeitsekunden" in text


def test_werkzeuge_sind_benannt(text: str) -> None:
    for werkzeug in ("get_state", "food_forecast", "impatience_forecast",
                     "query_kb", "analyze_runs"):
        assert werkzeug in text, werkzeug


def test_unsicheres_wird_als_unsicher_benannt(text: str) -> None:
    """Der Berater darf eine Lesung nicht als Wissen ausgeben.

    Frueher stand hier, dass `read_choice` fehlt. Es gibt es jetzt -- und
    damit verschiebt sich die Pflicht: nicht mehr "sag, dass du nichts
    siehst", sondern "sag, wenn du dir beim Gelesenen nicht sicher bist".
    """
    assert "read_choice" in text
    assert "unklar" in text and "gefragt, nicht geraten" in text
    assert "erfundene Zahl" in text


# --------------------------------------------------------------------------
# Alle Skills, nicht nur der Berater
#
# Ein Skill mit falschem Kopfteil wird stillschweigend nicht geladen -- er
# fehlt dann einfach, ohne Fehlermeldung. Dieselbe Klasse von Fehler, die
# dieses Projekt schon zweimal erwischt hat.
# --------------------------------------------------------------------------


def test_es_gibt_mehr_als_einen_skill() -> None:
    assert len(ALLE) >= 4, [p.parent.name for p in ALLE]


@pytest.mark.parametrize("pfad", ALLE, ids=lambda p: p.parent.name)
def test_jeder_skill_hat_einen_gueltigen_kopfteil(pfad: Path) -> None:
    text = pfad.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{pfad.parent.name}: kein Kopfteil"
    kopf = text.split("---")[1]

    name = re.search(r"^name:\s*(\S+)", kopf, re.M)
    assert name, f"{pfad.parent.name}: kein name"
    assert name.group(1) == pfad.parent.name, (
        f"{name.group(1)} steht in {pfad.parent.name}/ -- geladen wird nach Ordner")

    beschreibung = re.search(r"^description:\s*(.+)", kopf, re.M)
    assert beschreibung, f"{pfad.parent.name}: keine description"
    # Die Beschreibung entscheidet, ob der Skill ueberhaupt gefunden wird.
    assert 40 < len(beschreibung.group(1)) < 1024, len(beschreibung.group(1))


@pytest.mark.parametrize("pfad", ALLE, ids=lambda p: p.parent.name)
def test_jeder_skill_sagt_wann_er_gilt(pfad: Path) -> None:
    """Eine Beschreibung ohne Anlass wird nie gezogen."""
    kopf = pfad.read_text(encoding="utf-8").split("---")[1].lower()
    assert "nutzen" in kopf or "verwenden" in kopf, pfad.parent.name
