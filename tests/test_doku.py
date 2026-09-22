"""Die Anleitung muss auf Dateien zeigen, die es gibt.

Eine Installationsanleitung veraltet leise: ein umbenanntes Werkzeug, ein
verschobener Starter, und der Befehl im Text läuft ins Leere -- bemerkt wird
es erst von jemandem, der neu anfängt und nichts vergleichen kann. Dieselbe
Klasse stiller Abweichung, die hier schon mehrfach zugeschlagen hat.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent
ANLEITUNG = WURZEL / "docs" / "INSTALLATION.md"
README = WURZEL / "README.md"

MARKDOWN = sorted(p for p in (WURZEL / "docs").glob("*.md")) + [README]


@pytest.fixture(scope="module")
def anleitung() -> str:
    return ANLEITUNG.read_text(encoding="utf-8")


def test_die_anleitung_gibt_es_und_das_readme_zeigt_darauf() -> None:
    assert ANLEITUNG.exists()
    assert "docs/INSTALLATION.md" in README.read_text(encoding="utf-8")


def test_jeder_genannte_starter_existiert(anleitung: str) -> None:
    """`python tools\\build_kb.py` und Geschwister -- alle, in beiden Schreibweisen."""
    genannt = set(re.findall(r"(?:tools[\\/][\w_]+\.py|ats-gui\.pyw)", anleitung))
    assert genannt, "kein einziger Starter in der Anleitung?"
    for eintrag in sorted(genannt):
        assert (WURZEL / eintrag.replace("\\", "/")).exists(), eintrag


def test_jeder_unterbefehl_von_build_kb_gibt_es(anleitung: str) -> None:
    quelle = (WURZEL / "tools" / "build_kb.py").read_text(encoding="utf-8")
    bekannt = set(re.findall(r'add_parser\(\s*"([\w-]+)"', quelle))
    benutzt = set(re.findall(r"build_kb\.py\s+([\w-]+)", anleitung))
    assert benutzt <= bekannt, sorted(benutzt - bekannt)


def test_jeder_genannte_konsolenbefehl_steht_in_pyproject(anleitung: str) -> None:
    pyproject = (WURZEL / "pyproject.toml").read_text(encoding="utf-8")
    for befehl in re.findall(r"^(ats-[\w-]+)$", anleitung, re.M):
        assert f"{befehl} =" in pyproject, befehl


@pytest.mark.parametrize("pfad", MARKDOWN, ids=lambda p: p.name)
def test_verweise_auf_dateien_im_repo_gehen_ins_leere_nicht(pfad: Path) -> None:
    text = pfad.read_text(encoding="utf-8")
    for ziel in re.findall(r"\]\((?!https?:|#)([^)\s]+)\)", text):
        ziel = ziel.split("#")[0]
        if not ziel:
            continue
        assert (pfad.parent / ziel).resolve().exists(), f"{pfad.name} → {ziel}"
