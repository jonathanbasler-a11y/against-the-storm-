"""Die Texterkennung: welches Paket, und was steht da, wenn keines da ist.

Gemessen am 22.09.2026 auf PyPI, nicht erinnert:

| Paket | Fassung | Python |
|---|---|---|
| `winsdk` | 1.0.0b10 (2023) | 3.8-3.12 |
| `winrt-Windows.Media.Ocr` | 3.2.1 | 3.9-3.13 |

`winsdk` hat kein Wheel für 3.13. Wer dorthin aktualisiert, verlöre die
Texterkennung, ohne etwas geändert zu haben -- und der Hinweis im Fenster
riete weiter zu einem Paket, das sich nicht installieren lässt. Deshalb
beide Namensräume, und ein Rat, der zur laufenden Python-Fassung passt.
"""

from __future__ import annotations

import sys
import types

import pytest

from ats_assistant import screen


def _paket(monkeypatch, name: str) -> None:
    """Ein Paket vortäuschen, das sich importieren lässt."""
    monkeypatch.setitem(sys.modules, name, types.ModuleType(name))


def _ohne(monkeypatch, *namen: str) -> None:
    """Und eines, das es nicht gibt -- auch wenn es echt installiert wäre."""
    echt = screen._hat

    def gefiltert(modul: str) -> bool:
        return False if modul in namen else echt(modul)

    monkeypatch.setattr(screen, "_hat", gefiltert)


def test_winsdk_wird_bevorzugt(monkeypatch) -> None:
    """Beide da: das ältere gewinnt, denn es ist das getestete."""
    _paket(monkeypatch, "winsdk")
    _paket(monkeypatch, "winrt")
    assert screen._ocr_herkunft() == "winsdk"


def test_winrt_taets_auch(monkeypatch) -> None:
    _ohne(monkeypatch, "winsdk")
    _paket(monkeypatch, "winrt")
    assert screen._ocr_herkunft() == "winrt"


def test_ohne_beide_gibt_es_keine_herkunft(monkeypatch) -> None:
    _ohne(monkeypatch, "winsdk", "winrt")
    assert screen._ocr_herkunft() is None


def test_der_rat_nennt_ein_paket_das_es_fuer_dieses_python_gibt() -> None:
    """Auf 3.13 wäre `pip install winsdk` ein Rat ins Leere."""
    rat = screen._ocr_befehl()
    if sys.version_info >= (3, 13):
        assert "winrt-Windows.Media.Ocr" in rat
        assert "winsdk" not in rat
    else:
        assert "winsdk" in rat


def test_verfuegbar_nennt_die_gefundene_herkunft(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    _ohne(monkeypatch, "winsdk")
    _paket(monkeypatch, "winrt")
    out = screen.verfuegbar()
    assert out["erkennung"]["winrt"] is True
    assert out["erkennung"]["herkunft"] == "winrt"
    assert out["rat"] == "Alles da."


def test_ohne_erkennung_steht_der_befehl_im_rat(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    _ohne(monkeypatch, "winsdk", "winrt")
    out = screen.verfuegbar()
    assert out["erkennung"]["herkunft"] is None
    assert "pip install" in out["rat"]


def test_erkenne_ohne_jedes_paket_sagt_was_zu_tun_ist(monkeypatch, tmp_path) -> None:
    bild = tmp_path / "schirm.png"
    bild.write_bytes(b"kein echtes PNG")
    monkeypatch.setattr(sys, "platform", "win32")
    _ohne(monkeypatch, "winsdk", "winrt", "pytesseract")
    with pytest.raises(RuntimeError, match="pip install"):
        screen.erkenne(bild)
