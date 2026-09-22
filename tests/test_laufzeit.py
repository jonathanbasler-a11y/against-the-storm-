"""Die Suite besteht auf der Python-Version, die das Projekt nennt.

Hintergrund: 217 Tests liefen wochenlang gegen Python 3.11, während
`pyproject.toml` `>=3.12` verlangt. Aufgefallen ist es erst, als das Fenster
nicht startete — 3.11 hatte in dieser Umgebung kein tkinter, 3.12 schon.
Jedes „alle Tests grün" sprach bis dahin über die falsche Laufzeit.

Dieser Test macht daraus eine rote Zeile statt einer stillen Abweichung.
Dieselbe Sorte Lücke hat hier schon zweimal zugeschlagen: `main()`
verschwand beim Umbau, `--db` wurde von der Vorgabe des Unterbefehls
überschrieben — beide Male waren alle Tests grün.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def verlangte_version() -> tuple[int, int]:
    """`requires-python = ">=3.12"` -> (3, 12)."""
    text = PYPROJECT.read_text(encoding="utf-8")
    treffer = re.search(r'requires-python\s*=\s*"[^0-9]*(\d+)\.(\d+)', text)
    assert treffer, "requires-python steht nicht in pyproject.toml"
    return int(treffer.group(1)), int(treffer.group(2))


def test_die_suite_laeuft_auf_der_verlangten_version() -> None:
    verlangt = verlangte_version()
    laeuft = sys.version_info[:2]
    assert laeuft >= verlangt, (
        f"Diese Suite läuft auf Python {laeuft[0]}.{laeuft[1]}, "
        f"das Projekt verlangt >= {verlangt[0]}.{verlangt[1]}. "
        f"Ein grüner Lauf sagt dann nichts über die Version, die der Nutzer "
        f"tatsächlich hat. Interpreter: {sys.executable}")


def test_tkinter_fehlt_nicht_unbemerkt() -> None:
    """Fehlt tkinter, steht hier warum — statt acht rätselhafter Fehler.

    Kein harter Fehlschlag: auf einem Rechner ohne tcl/tk soll der Rest der
    Suite durchlaufen. Die Fenstertests überspringen sich dann selbst.
    """
    try:
        import tkinter                                  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("Kein tkinter. Unter Windows: Python-Installer, Modify, "
                    "\"tcl/tk and IDLE\" ankreuzen. Unter Linux: python3-tk.")
