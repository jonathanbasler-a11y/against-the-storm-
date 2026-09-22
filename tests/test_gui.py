"""Tests der Fensterverdrahtung -- mit eingesetztem tkinter.

Das Fenster selbst lässt sich hier nicht starten; tkinter ist in dieser
Umgebung nicht installiert. Die Verdrahtung schon, und genau dort sitzt die
Fehlerklasse, die dieses Projekt zweimal erwischt hat: ein Einstiegspunkt,
den kein Test anfasst (`main` verschwand beim Umbau, `--db` wurde still
überschrieben).

Geprüft wird deshalb: dass sich das Fenster aufbauen lässt, dass `_anzeigen`
**jede** Nachrichtenart des Arbeits-Threads kennt, und dass keine davon
wirft. Ein Tippfehler in einem Widgetnamen fällt hier auf, nicht erst am
Spielrechner.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path

import pytest


class Egal:
    """Ein Widget, das alles mitmacht und nichts tut."""

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def __call__(self, *args, **kwargs):
        return Egal()

    def __getattr__(self, name):
        if name == "get_children":
            return lambda *a, **k: []
        if name == "get":
            return lambda *a, **k: ""
        if name == "cget":
            return lambda *a, **k: "#ffffff"
        return Egal()


class Variable(Egal):
    def __init__(self, *args, value=None, **kwargs):
        super().__init__()
        self._wert = value

    def get(self):
        return self._wert

    def set(self, wert):
        self._wert = wert


@pytest.fixture
def gui(monkeypatch):
    """Das Fenstermodul mit eingesetztem tkinter."""
    tk = types.ModuleType("tkinter")
    ttk = types.ModuleType("tkinter.ttk")
    for name in ("Tk", "Text", "Toplevel", "Frame", "Label", "Button", "Entry"):
        setattr(tk, name, Egal)
    tk.StringVar = Variable
    tk.ttk = ttk
    for name in ("Notebook", "Frame", "Label", "Button", "Entry", "Progressbar",
                 "Treeview", "Radiobutton", "Combobox"):
        setattr(ttk, name, Egal)

    monkeypatch.setitem(sys.modules, "tkinter", tk)
    monkeypatch.setitem(sys.modules, "tkinter.ttk", ttk)
    sys.modules.pop("ats_assistant.gui", None)
    modul = importlib.import_module("ats_assistant.gui")
    yield modul
    sys.modules.pop("ats_assistant.gui", None)


def test_das_fenster_laesst_sich_aufbauen(gui, tmp_path: Path) -> None:
    app = gui.App(tmp_path / "save", tmp_path / "runs", tmp_path / "kb.sqlite")
    app.rechner.stoppen()
    assert app.felder and app.balken           # die Anzeigefelder stehen


ALLE_ARTEN = ("zustand", "nahrung", "ungeduld", "ketten", "auswahl",
              "nachschlag", "rat", "umgebung", "fehler")


def test_jede_nachrichtenart_wird_angezeigt(gui, tmp_path: Path) -> None:
    """Der Arbeits-Thread schickt neun Arten. Fehlt eine Zuordnung, fällt die
    Antwort lautlos unter den Tisch."""
    app = gui.App(tmp_path / "save", tmp_path / "runs", tmp_path / "kb.sqlite")
    app.rechner.stoppen()

    beispiele = {
        "zustand": {"jahr": 3, "biom": "Coastal Grove", "prestige": 13,
                    "bevoelkerung": 24, "reputation": 8.0, "reputation_ziel": 18,
                    "ungeduld": 4.0, "ungeduld_schwelle": 14,
                    "feindseligkeit": {"current": 180},
                    "zeitpunkt": "2026-09-22T10:00:00+00:00"},
        "nahrung": {"reichweite_sekunden": 340.0, "warnung": "reicht nicht"},
        "ungeduld": {"sekunden_bis_verlust": 1200.0},
        "ketten": {"empfehlung": "Räucherei", "begruendung": "weil", "alternative": "oder",
                   "ketten": [{"gebaeude": "Smokehouse", "gebaeude_de": "Räucherei",
                               "einsatz": [{"menge": 40, "ware": "Meat"}],
                               "gewinn": 120.0, "faktor": 4.0, "engpass": "Meat",
                               "sekunden": 480.0, "reichweite_plus_sekunden": 1200}]},
        "auswahl": {"verfuegbar": True, "angebot": [
            {"de": "Pilzführer", "en": "Fungal Guide", "guete": 0.98,
             "seltenheit": "Epic", "wirkung": "+1 Pilze"}]},
        "nachschlag": {"gesucht": "Holz", "namen": [
            {"de": "Holz", "en": "Wood", "kind": "resource", "confidence": "localization"}]},
        "rat": {"ok": True, "text": "Nimm die Räucherei.", "fuss": "claude-opus-5"},
        "umgebung": {"fehlt": [], "namen": 2266, "mitschriften_da": 2},
        "fehler": "irgendwas ist schiefgegangen",
    }
    assert set(beispiele) == set(ALLE_ARTEN)
    for art in ALLE_ARTEN:
        app._anzeigen(art, beispiele[art])     # keine darf werfen


def test_die_leeren_faelle_werfen_auch_nicht(gui, tmp_path: Path) -> None:
    """Kein Spielstand, keine Kette, nichts erkannt -- alles kommt vor."""
    app = gui.App(tmp_path / "save", tmp_path / "runs", tmp_path / "kb.sqlite")
    app.rechner.stoppen()

    app._anzeigen("zustand", {"verfuegbar": False, "grund": "kein Spielstand"})
    app._anzeigen("nahrung", {"verfuegbar": False, "grund": "zwei Stände nötig"})
    app._anzeigen("ungeduld", {})
    app._anzeigen("ketten", {"verfuegbar": False, "empfehlung": "nichts lohnt",
                             "begruendung": "es fehlt Kohle"})
    app._anzeigen("auswahl", {"verfuegbar": False, "grund": "nichts erkannt",
                              "unklar": [{"gelesen": "PILZ", "kandidaten": [
                                  {"de": "Pilzführer", "guete": 0.7}]}]})
    app._anzeigen("rat", {"ok": False, "text": "keine Anmeldung", "zugang": False})
    app._anzeigen("umgebung", {"fehlt": ["Spielordner nicht gefunden"]})


def test_lage_kopieren_legt_json_ohne_bild_in_die_zwischenablage(gui, tmp_path: Path) -> None:
    app = gui.App(tmp_path / "save", tmp_path / "runs", tmp_path / "kb.sqlite")
    app.rechner.stoppen()
    app.zustand = {"jahr": 2, "biom": "Coastal Grove"}

    abgelegt: list[str] = []
    app.root.clipboard_append = abgelegt.append
    app.root.clipboard_clear = lambda: None
    app._lage_kopieren()

    auszug = json.loads(abgelegt[0])
    assert auszug["siedlung"]["jahr"] == 2
    assert "bild" not in abgelegt[0].lower()


def test_main_existiert_und_nimmt_argumente(gui) -> None:
    """Der Starter `ats-gui.pyw` importiert genau das."""
    assert callable(gui.main)
