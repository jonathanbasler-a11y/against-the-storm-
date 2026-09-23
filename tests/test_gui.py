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
    _vergiss_das_fenstermodul()
    modul = importlib.import_module("ats_assistant.gui")
    yield modul
    # Aufräumen ist hier keine Höflichkeit. Bliebe das mit Stubs gebaute
    # Modul liegen, prüfte der Test mit echtem Tk (test_gui_echt.py) in
    # Wahrheit dieselben Attrappen -- und wäre grün, ohne etwas zu zeigen.
    _vergiss_das_fenstermodul()


def _vergiss_das_fenstermodul() -> None:
    """Modul **und** Paketattribut entfernen.

    `sys.modules.pop` allein genügt nicht: nach dem ersten Import hängt
    `gui` auch als Attribut am Paket, und `from ats_assistant import gui`
    holt es von dort -- am Importsystem vorbei.
    """
    import ats_assistant

    sys.modules.pop("ats_assistant.gui", None)
    if hasattr(ats_assistant, "gui"):
        delattr(ats_assistant, "gui")


def test_das_fenster_laesst_sich_aufbauen(gui, tmp_path: Path) -> None:
    app = gui.App(tmp_path / "save", tmp_path / "runs", tmp_path / "kb.sqlite")
    app.rechner.stoppen()
    assert app.felder and app.balken           # die Anzeigefelder stehen


ALLE_ARTEN = ("zustand", "nahrung", "ungeduld", "ketten", "auswahl",
              "nachschlag", "rat", "umgebung", "anmeldung", "fehler")


def test_jede_nachrichtenart_wird_angezeigt(gui, tmp_path: Path) -> None:
    """Der Arbeits-Thread schickt zehn Arten. Fehlt eine Zuordnung, fällt die
    Antwort lautlos unter den Tisch."""
    app = gui.App(tmp_path / "save", tmp_path / "runs", tmp_path / "kb.sqlite")
    app.rechner.stoppen()

    beispiele = {
        "zustand": {"jahr": 3, "biom": "Coastal Grove", "prestige": 13,
                    "bevoelkerung": 24, "reputation": 8.0, "reputation_ziel": 18,
                    "ungeduld": 4.0, "ungeduld_schwelle": 14,
                    "feindseligkeit": {"level": 3, "points": 72},
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
        "anmeldung": False,
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


def test_der_stub_laeuft_nicht_in_andere_tests_aus() -> None:
    """Nach der Vorrichtung muss wieder das echte tkinter gelten.

    Genau das war kaputt: die Tests mit echtem Tk liefen allein durch und
    scheiterten in der Gesamtsuite an `Egal has no len()`.
    """
    import ats_assistant

    assert "ats_assistant.gui" not in sys.modules
    assert not hasattr(ats_assistant, "gui")


# --------------------------------------------------------------------------
# Der Bildweg darf nicht das eigene Fenster fotografieren
#
# Am Spielrechner lag der Assistent über dem Auswahldialog. `aufnehmen()`
# nimmt den ganzen Bildschirm -- ein Stück weiter rechts, und die
# Texterkennung liest sauber die eigene Oberfläche statt der Karten.
# --------------------------------------------------------------------------


class Wurzel(Egal):
    """Ein Fenster, das mitschreibt, was mit ihm geschieht."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.protokoll: list[str] = []
        self.auftraege: list = []

    def withdraw(self):
        self.protokoll.append("withdraw")

    def deiconify(self):
        self.protokoll.append("deiconify")

    def after(self, ms, fn=None):
        if fn is not None:
            self.auftraege.append((ms, fn))
        return f"nach-{len(self.auftraege)}"

    def after_cancel(self, kennung):
        self.protokoll.append(f"abbruch {kennung}")


class Rechner:
    def __init__(self):
        self.gebeten: list = []

    def bitte(self, art, **daten):
        self.gebeten.append((art, daten))

    def stoppen(self):
        pass


def _vorbereitet(gui, tmp_path: Path):
    app = gui.App(tmp_path / "save", tmp_path / "runs", tmp_path / "kb.sqlite")
    app.rechner.stoppen()
    app.root = Wurzel()
    app.rechner = Rechner()
    return app


def test_bildweg_versteckt_das_fenster(gui, tmp_path: Path, monkeypatch) -> None:
    app = _vorbereitet(gui, tmp_path)
    monkeypatch.setattr(gui.screen, "aufnehmen", lambda *a, **k: tmp_path / "foto.png")
    app._auswahl_lesen()

    assert "withdraw" in app.root.protokoll
    # Der Auftrag geht erst los, wenn das Fenster weg ist -- nicht sofort.
    assert app.rechner.gebeten == []
    verzoegert = [fn for _, fn in app.root.auftraege]
    assert verzoegert, "kein verzögerter Auftrag"
    for fn in verzoegert:
        fn()
    assert [a for a, _ in app.rechner.gebeten] == ["auswahl"]


def test_das_ergebnis_holt_das_fenster_zurueck(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app._auswahl_lesen()
    app._anzeigen("auswahl", {"verfuegbar": False, "quelle": "/tmp/x.png",
                              "gelesene_zeilen": 0, "grund": "Nichts erkannt."})
    assert "deiconify" in app.root.protokoll


def test_ein_fremder_fehler_holt_das_fenster_nicht_vor_dem_foto(
        gui, tmp_path: Path, monkeypatch) -> None:
    """Ein Fenster, das unsichtbar bleibt, ist schlimmer als eines im Bild --
    aber ein Fehler aus einem anderen Auftrag durfte es vor dem Foto
    zurückholen, und fotografiert wurde es selbst. Zurück kommt es mit dem
    Foto, oder spätestens über das Sicherheitsnetz."""
    app = _vorbereitet(gui, tmp_path)
    monkeypatch.setattr(gui.screen, "aufnehmen", lambda *a, **k: tmp_path / "foto.png")
    app._auswahl_lesen()
    app._anzeigen("fehler", "Ein anderer Auftrag scheiterte")
    assert "deiconify" not in app.root.protokoll
    for _, fn in sorted(app.root.auftraege, key=lambda a: a[0]):
        fn()
    assert "deiconify" in app.root.protokoll


def test_handweg_versteckt_nichts(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app.hand = Variable(value="pilzfuehrer")
    app._auswahl_lesen(von_hand=True)

    assert app.root.protokoll == []
    assert app.rechner.gebeten[0][1]["text"] == ["pilzfuehrer"]


def test_ohne_anmeldung_steht_es_im_reiter_bevor_jemand_fragt(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app.rat_fuss = Wurzel()
    app.rat_fuss.configure = lambda **kw: app.rat_fuss.protokoll.append(kw.get("text", ""))

    app._anzeigen("anmeldung", False)
    assert any("ANTHROPIC_API_KEY" in z for z in app.rat_fuss.protokoll)
    assert any("Lage kopieren" in z for z in app.rat_fuss.protokoll)


def test_ohne_sdk_steht_der_installationsbefehl_da(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app.rat_fuss = Wurzel()
    app.rat_fuss.configure = lambda **kw: app.rat_fuss.protokoll.append(kw.get("text", ""))

    app._anzeigen("anmeldung", None)
    assert any("pip install anthropic" in z for z in app.rat_fuss.protokoll)


def test_eine_vorhandene_anmeldung_schreibt_nichts_hin(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app.rat_fuss = Wurzel()
    app.rat_fuss.configure = lambda **kw: app.rat_fuss.protokoll.append(kw.get("text", ""))

    app._anzeigen("anmeldung", True)
    assert app.rat_fuss.protokoll == [""]


def test_eine_antwort_ueberschreibt_den_hinweis_nicht_rueckwaerts(gui, tmp_path: Path) -> None:
    """Nach einer echten Antwort gehört dort die Fußzeile der Antwort hin,
    nicht wieder der Anmeldehinweis des nächsten Durchlaufs."""
    app = _vorbereitet(gui, tmp_path)
    app.rat_fuss = Wurzel()
    app.rat_fuss.configure = lambda **kw: app.rat_fuss.protokoll.append(kw.get("text", ""))

    app._anzeigen("rat", {"ok": True, "text": "Nimm die Räucherei.", "fuss": "claude-opus-5"})
    app._anzeigen("anmeldung", False)
    assert app.rat_fuss.protokoll[-1] == "claude-opus-5"


def test_die_spezies_stehen_getrennt_vom_angebot(gui, tmp_path: Path) -> None:
    """Am Spielrechner standen Fuchs, Frosch und Biber gleichberechtigt
    neben den zwei echten Karten -- es sind die Symbole oben links."""
    app = _vorbereitet(gui, tmp_path)
    geschrieben: list[str] = []
    app._schreiben = lambda feld, text: geschrieben.append(text)

    app._anzeigen("auswahl", {
        "verfuegbar": True, "quelle": "/tmp/x.png", "gelesene_zeilen": 54,
        "angebot": [
            {"de": "Kristallkathode", "en": "Crystal Cathode", "guete": 1.0,
             "belegt": True, "seltenheit": "Legendary", "wirkung": "Regenmaschinen …"},
            {"de": "Biber", "en": "Beaver", "guete": 1.0, "belegt": False},
        ],
        "belegt": [{"de": "Kristallkathode"}],
        "sonst_gesehen": [{"de": "Biber", "en": "Beaver", "guete": 1.0, "belegt": False}],
        "unsicher": [{"de": "Wucher", "en": "Usury", "guete": 0.727, "belegt": False}],
    })

    text = geschrieben[-1]
    kopf, rest = text.split("Biber", 1)
    assert "Kristallkathode" in kopf
    assert "Wissensbasis" in text or "belegt" in text
    assert "Wucher" in text and "0.727" in text


def test_nicht_gefundene_felder_stehen_in_der_warnung(gui, tmp_path: Path) -> None:
    """Ein stiller Ausfall ist schlimmer als ein lauter: `lager: {}` sah aus
    wie ein leeres Lager und war ein nicht gefundenes Feld."""
    app = _vorbereitet(gui, tmp_path)
    gesagt: list[str] = []
    app.warnung = Wurzel()
    app.warnung.configure = lambda **kw: gesagt.append(kw.get("text", ""))

    app._anzeigen("zustand", {"verfuegbar": True, "jahr": 1, "biom": "Royal Woodlands",
                              "lager": {}, "nicht_gefunden": ["storage", "buildings"]})
    assert any("storage" in z and "nicht gefunden" in z.lower() for z in gesagt)


def test_unlesbare_felder_stehen_in_der_warnung(gui, tmp_path: Path) -> None:
    """Gefunden, aber in fremder Form -- das ist etwas anderes als „fehlt"
    und muss auch anders heißen, sonst sucht man am falschen Ende."""
    app = _vorbereitet(gui, tmp_path)
    gesagt: list[str] = []
    app.warnung = Wurzel()
    app.warnung.configure = lambda **kw: gesagt.append(kw.get("text", ""))

    app._anzeigen("zustand", {"verfuegbar": True, "jahr": 1, "biom": "Royal Woodlands",
                              "lager": {}, "nicht_gefunden": ["biome"],
                              "form_unbekannt": {"storage": "{…}", "buildings": "{…}"}})
    text = " ".join(gesagt)
    assert "nicht lesbar" in text and "storage" in text and "buildings" in text
    assert "nicht gefunden" in text.lower() and "biome" in text


def test_die_ketten_gehen_mit_in_den_rat(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    ketten = {"empfehlung": "Grill", "ketten": [{"gebaeude": "Grill", "einsatz": [],
                                                 "gewinn": 25, "faktor": 6.0}]}
    app._anzeigen("ketten", ketten)
    app._rat_holen()
    art, daten = app.rechner.gebeten[-1]
    assert art == "rat" and daten["ketten"] == ketten


# --------------------------------------------------------------------------
# QA-Runde 3 (23.09.2026): Fenster
# --------------------------------------------------------------------------


def test_das_foto_entsteht_bevor_das_fenster_zurueckkommt(gui, tmp_path: Path,
                                                          monkeypatch) -> None:
    """Vorher wartete das Foto hinter laufenden Aufträgen -- eine Rat-Frage
    dauert bis zu einer Minute. Nach acht Sekunden holte das Sicherheitsnetz
    das Fenster zurück, und fotografiert wurde es selbst."""
    app = _vorbereitet(gui, tmp_path)
    reihenfolge: list[str] = []
    monkeypatch.setattr(gui.screen, "aufnehmen",
                        lambda *a, **k: reihenfolge.append("foto") or tmp_path / "foto.png")
    app.root.deiconify = lambda: reihenfolge.append("zurück")
    app.rechner.bitte = lambda art, **d: reihenfolge.append(f"bitte {art} {d.get('bild')}")
    app._auswahl_lesen()
    for _, fn in sorted(app.root.auftraege, key=lambda a: a[0]):
        fn()
    assert reihenfolge[:3] == ["foto", "zurück", f"bitte auswahl {tmp_path / 'foto.png'}"]


def test_scheitert_das_foto_kommt_das_fenster_mit_einem_satz_zurueck(
        gui, tmp_path: Path, monkeypatch) -> None:
    app = _vorbereitet(gui, tmp_path)

    def geht_nicht(*a, **k):
        raise RuntimeError("Keine Aufnahme moeglich")

    monkeypatch.setattr(gui.screen, "aufnehmen", geht_nicht)
    geschrieben: list[str] = []
    app._schreiben = lambda feld, text: geschrieben.append(text)
    app._auswahl_lesen()
    for _, fn in list(app.root.auftraege):
        fn()
    assert "deiconify" in app.root.protokoll
    assert app.rechner.gebeten == []
    assert any("Keine Aufnahme" in t for t in geschrieben)


def test_ein_fehler_beim_anzeigen_haelt_das_abholen_nicht_an(gui, tmp_path: Path) -> None:
    """Eine Ausnahme in `_anzeigen` beendete das Abholen für immer: das
    Fenster zeigte nie wieder etwas Neues."""
    app = _vorbereitet(gui, tmp_path)
    gezeigt: list[str] = []

    def anzeigen(art, wert):
        if art == "kaputt":
            raise ValueError("unerwartete Form")
        gezeigt.append(art)

    app._anzeigen = anzeigen
    import queue
    app.ausgang = queue.Queue()                        # nichts vom Aufbau dazwischen
    app.ausgang.put(("kaputt", None))
    app.ausgang.put(("zustand", {}))
    app._abholen()
    assert gezeigt == ["zustand"]
    assert any(fn == app._abholen for _, fn in app.root.auftraege)


def test_die_zustandswarnung_bleibt_neben_der_nahrungswarnung(gui, tmp_path: Path) -> None:
    """„Nicht gefunden" wurde im selben Durchgang von der Nahrungswarnung
    überschrieben -- der stille Ausfall, den die Zeile verhindern sollte."""
    app = _vorbereitet(gui, tmp_path)
    gesagt: list[str] = []
    app.warnung = Wurzel()
    app.warnung.configure = lambda **kw: gesagt.append(kw.get("text", ""))
    app._anzeigen("zustand", {"verfuegbar": True, "jahr": 1,
                              "nicht_gefunden": ["cornerstones"]})
    app._anzeigen("nahrung", {"warnung": "Nahrung reicht noch 103 Spielzeitsekunden"})
    assert "cornerstones" in gesagt[-1] and "103" in gesagt[-1]


def test_eine_alte_auswahl_verfaellt_wenn_das_spiel_weiterlaeuft(gui, tmp_path: Path) -> None:
    """Eine gelesene Grundsteinwahl ging bei jeder späteren Frage mit --
    mit `wahl_steht_an`, also höherem Aufwand und falschem Rat."""
    app = _vorbereitet(gui, tmp_path)
    app._anzeigen("zustand", {"verfuegbar": True, "spielzeit": 600.0})
    app._anzeigen("auswahl", {"verfuegbar": True, "quelle": "hand", "gelesene_zeilen": 1,
                              "angebot": [{"de": "Wucher", "en": "Usury", "guete": 1.0}]})
    app._anzeigen("zustand", {"verfuegbar": True, "spielzeit": 600.0})
    assert app.auswahl                                  # dieselbe Spielzeit: bleibt
    app._anzeigen("zustand", {"verfuegbar": True, "spielzeit": 900.0})
    assert not app.auswahl


def test_der_anmeldehinweis_bleibt_bis_zur_ersten_antwort(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app.rat_fuss = Wurzel()
    fuss: list[str] = []
    app.rat_fuss.configure = lambda **kw: fuss.append(kw.get("text", ""))
    app._anzeigen("rat", {"ok": False, "zugang": False, "text": "Keine Anmeldung"})
    assert "Ohne Anmeldung" in fuss[-1]
    app._anzeigen("anmeldung", True)                  # Schlüssel inzwischen gesetzt
    assert fuss[-1] == ""                             # der alte Hinweis ist weg
