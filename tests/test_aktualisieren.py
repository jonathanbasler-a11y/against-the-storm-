"""Der Knopf „Aktualisieren“: git pull --ff-only und Neustart."""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

from ats_assistant import aktualisieren


def _repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


def _git(koepfe: list[str], pull_code: int = 0, pull_fehler: str = ""):
    aufrufe: list[list[str]] = []

    def run(befehl, **kw):
        aufrufe.append(befehl)
        if befehl[1] == "rev-parse":
            return types.SimpleNamespace(returncode=0, stdout=koepfe.pop(0) + "\n", stderr="")
        return types.SimpleNamespace(returncode=pull_code, stdout="", stderr=pull_fehler)
    return run, aufrufe


def test_neue_version(tmp_path):
    run, aufrufe = _git(["a" * 40, "b" * 40])
    out = aktualisieren.aktualisieren(_repo(tmp_path), run=run, which=lambda n: "git")
    assert out == {"ok": True, "neu": True, "stand": "bbbbbbb",
                   "text": "Neue Version geladen (bbbbbbb)."}
    assert ["git", "pull", "--ff-only"] in aufrufe


def test_schon_aktuell(tmp_path):
    run, _ = _git(["a" * 40, "a" * 40])
    out = aktualisieren.aktualisieren(_repo(tmp_path), run=run, which=lambda n: "git")
    assert out["ok"] is True and out["neu"] is False and "Schon aktuell" in out["text"]


def test_lokale_aenderungen_werden_gesagt(tmp_path):
    run, _ = _git(["a" * 40], pull_code=1,
                  pull_fehler="error: Your local changes would be overwritten")
    out = aktualisieren.aktualisieren(_repo(tmp_path), run=run, which=lambda n: "git")
    assert out["ok"] is False and "local changes" in out["text"]


def test_ohne_git_kein_aufruf(tmp_path):
    run, aufrufe = _git([])
    out = aktualisieren.aktualisieren(_repo(tmp_path), run=run, which=lambda n: None)
    assert out["ok"] is False and aufrufe == []


def test_ohne_git_ordner(tmp_path):
    run, aufrufe = _git([])
    out = aktualisieren.aktualisieren(tmp_path, run=run, which=lambda n: "git")
    assert out["ok"] is False and "kein git-Ordner" in out["text"] and aufrufe == []


def test_zeitueberschreitung_wirft_nicht(tmp_path):
    def run(befehl, **kw):
        raise subprocess.TimeoutExpired(befehl, 60)
    out = aktualisieren.aktualisieren(_repo(tmp_path), run=run, which=lambda n: "git")
    assert out["ok"] is False and "länger" in out["text"]


def test_neu_starten_nimmt_dasselbe_programm():
    gestartet = []
    aktualisieren.neu_starten(popen=lambda befehl, cwd=None: gestartet.append((befehl, cwd)))
    assert gestartet == [([sys.executable, *sys.argv], str(aktualisieren.REPO))]
