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
    tk.BooleanVar = Variable
    tk.ttk = ttk
    for name in ("Notebook", "Frame", "Label", "Button", "Entry", "Progressbar",
                 "Treeview", "Radiobutton", "Combobox", "Checkbutton"):
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

    # Das HUD ebenso: es bindet tkinter beim Import. Hatte ein Test mit echtem
    # Tk es vorher geladen, baute das Fenster mit Stubs ein echtes Toplevel
    # auf einer Attrappe -- einzeln grün, in der Gesamtsuite rot.
    for name in ("gui", "hud"):
        sys.modules.pop(f"ats_assistant.{name}", None)
        if hasattr(ats_assistant, name):
            delattr(ats_assistant, name)


def test_das_fenster_laesst_sich_aufbauen(gui, tmp_path: Path) -> None:
    app = gui.App(tmp_path / "save", tmp_path / "runs", tmp_path / "kb.sqlite")
    app.rechner.stoppen()
    assert app.felder and app.balken           # die Anzeigefelder stehen


ALLE_ARTEN = ("zustand", "nahrung", "ungeduld", "ketten", "auswahl",
              "nachschlag", "rat", "umgebung", "anmeldung", "fehler", "engpass",
              "tastenfehler")


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
        "engpass": {"verfuegbar": True, "entscheidend": "nahrung", "stufe": "rot",
                    "kurz": "Nahrung 4 min", "uhren": [
                        {"art": "nahrung", "name": "Nahrung", "sekunden": 240.0,
                         "text": "leer in 4 min", "stufe": "rot", "zusatz": ""}]},
        "tastenfehler": "„Strg+Umschalt+L“ ist schon vergeben",
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
    assert "ats_assistant.hud" not in sys.modules


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
        self._zustand = "withdrawn"

    def deiconify(self):
        self.protokoll.append("deiconify")
        self._zustand = "normal"

    def state(self):
        return getattr(self, "_zustand", "normal")

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
    # Eine eigene Warteschlange: der echte Arbeits-Thread aus dem Aufbau kann
    # sonst noch Meldungen hineinlegen, und ein Test liest die falsche.
    import queue
    app.ausgang = queue.Queue()
    return app


def _gleichlaufend(monkeypatch, gui) -> None:
    """Der Foto-Faden läuft im Test sofort, damit die Reihenfolge feststeht."""
    class Faden:
        def __init__(self, target, args=(), daemon=None):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(gui.threading, "Thread", Faden)


def _foto_und_abholen(app) -> None:
    """Nur den Foto-Aufruf (250 ms) ausführen, dann die Warteschlange leeren."""
    min(app.root.auftraege, key=lambda a: a[0])[1]()
    while not app.ausgang.empty():
        app._anzeigen(*app.ausgang.get_nowait())


def test_bildweg_versteckt_das_fenster(gui, tmp_path: Path, monkeypatch) -> None:
    app = _vorbereitet(gui, tmp_path)
    _gleichlaufend(monkeypatch, gui)
    monkeypatch.setattr(gui.screen, "aufnehmen", lambda *a, **k: tmp_path / "foto.png")
    app._auswahl_lesen()

    assert "withdraw" in app.root.protokoll
    # Der Auftrag geht erst los, wenn das Fenster weg ist -- nicht sofort.
    assert app.rechner.gebeten == []
    assert app.root.auftraege, "kein verzögerter Auftrag"
    _foto_und_abholen(app)
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
    _gleichlaufend(monkeypatch, gui)
    _foto_und_abholen(app)
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
    app.root.withdraw()
    app._foto_aufnehmen("effect")
    app._anzeigen(*app.ausgang.get_nowait())
    assert reihenfolge[:3] == ["foto", "zurück", f"bitte auswahl {tmp_path / 'foto.png'}"]


def test_scheitert_das_foto_kommt_das_fenster_mit_einem_satz_zurueck(
        gui, tmp_path: Path, monkeypatch) -> None:
    app = _vorbereitet(gui, tmp_path)

    def geht_nicht(*a, **k):
        raise RuntimeError("Keine Aufnahme moeglich")

    monkeypatch.setattr(gui.screen, "aufnehmen", geht_nicht)
    geschrieben: list[str] = []
    app._schreiben = lambda feld, text: geschrieben.append(text)
    app.root.withdraw()
    app._foto_aufnehmen("effect")
    app._anzeigen(*app.ausgang.get_nowait())
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
    app._anzeigen("zustand", {"verfuegbar": True, "spielzeit": 1500.0})
    assert not app.auswahl                              # lange weitergespielt


def test_der_anmeldehinweis_bleibt_bis_zur_ersten_antwort(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app.rat_fuss = Wurzel()
    fuss: list[str] = []
    app.rat_fuss.configure = lambda **kw: fuss.append(kw.get("text", ""))
    app._anzeigen("rat", {"ok": False, "zugang": False, "text": "Keine Anmeldung"})
    assert "Ohne Anmeldung" in fuss[-1]
    app._anzeigen("anmeldung", True)                  # Schlüssel inzwischen gesetzt
    assert fuss[-1] == ""                             # der alte Hinweis ist weg


# --------------------------------------------------------------------------
# QA-Runde 5: Nachprüfung
# --------------------------------------------------------------------------


def test_das_foto_blockiert_den_hauptthread_nicht(gui, tmp_path: Path, monkeypatch) -> None:
    """Die PowerShell-Aufnahme dauert Sekunden. Im Hauptthread fror sie das
    Fenster ein, und das Sicherheitsnetz konnte nicht feuern."""
    app = _vorbereitet(gui, tmp_path)
    gestartet = []

    class Faden:
        def __init__(self, target, args=(), daemon=None):
            gestartet.append((target, args))

        def start(self):
            pass

    monkeypatch.setattr(gui.threading, "Thread", Faden)
    aufgenommen = []
    monkeypatch.setattr(gui.screen, "aufnehmen", lambda *a, **k: aufgenommen.append(1))
    app._auswahl_lesen()
    for _, fn in sorted(app.root.auftraege, key=lambda a: a[0])[:1]:
        fn()                                           # nur das Foto, nicht das Netz
    assert gestartet and not aufgenommen               # im Faden, nicht hier


def test_das_foto_kommt_ueber_die_warteschlange(gui, tmp_path: Path, monkeypatch) -> None:
    app = _vorbereitet(gui, tmp_path)
    monkeypatch.setattr(gui.screen, "aufnehmen", lambda *a, **k: tmp_path / "foto.png")
    app.root.withdraw()
    app._foto_aufnehmen("order")
    art, wert = app.ausgang.get_nowait()
    assert art == "foto"
    app._anzeigen(art, wert)
    assert "deiconify" in app.root.protokoll
    assert app.rechner.gebeten[-1][0] == "auswahl"
    assert app.rechner.gebeten[-1][1]["arten"] == ("order",)


def test_ein_zu_spaetes_foto_wird_verworfen(gui, tmp_path: Path) -> None:
    """Holte das Sicherheitsnetz das Fenster zurück, bevor das Foto kam,
    ist es womöglich mit drauf."""
    app = _vorbereitet(gui, tmp_path)
    geschrieben: list[str] = []
    app._schreiben = lambda feld, text: geschrieben.append(text)
    app._auswahl_lesen()
    netz = max(app.root.auftraege, key=lambda a: a[0])[1]
    netz()                                             # nach acht Sekunden
    app._anzeigen("foto", {"bild": str(tmp_path / "foto.png"), "art": "effect"})
    assert app.rechner.gebeten == []
    assert any("zu lange" in t for t in geschrieben)


def test_ein_sichtbares_fenster_wird_nicht_nochmal_nach_vorn_geholt(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app._anzeigen("auswahl", {"verfuegbar": False, "quelle": "x.png", "gelesene_zeilen": 0,
                              "grund": "Nichts erkannt."})
    assert "deiconify" not in app.root.protokoll


def test_kein_spielstand_leert_auch_nahrung_und_auswahl(gui, tmp_path: Path) -> None:
    """Die Werte der letzten Siedlung gingen sonst weiter an den Rat."""
    app = _vorbereitet(gui, tmp_path)
    app.nahrung = {"bestand": 16}
    app.ungeduld = {"jetzt": 1.5}
    app.nahrungsrat = {"ketten": [{"gebaeude": "Grill"}]}
    app.auswahl = {"angebot": [{"de": "Wucher"}]}
    app._anzeigen("zustand", {"verfuegbar": False, "grund": "Kein Spielstand"})
    assert app.nahrung is None and app.ungeduld is None
    assert app.nahrungsrat is None and app.auswahl is None


def test_eine_auswahl_ueberlebt_ein_speichern_aber_keine_neue_siedlung(
        gui, tmp_path: Path) -> None:
    """Die Grundsteinwahl hält das Spiel nicht an; ein Speichern kurz nach
    dem Lesen darf sie nicht verwerfen. Eine neue Siedlung schon."""
    app = _vorbereitet(gui, tmp_path)
    geschrieben: list[str] = []
    app._schreiben = lambda feld, text: geschrieben.append(text)
    app._anzeigen("zustand", {"verfuegbar": True, "spielzeit": 600.0, "mitschrift": "a"})
    app._anzeigen("auswahl", {"verfuegbar": True, "quelle": "hand", "gelesene_zeilen": 1,
                              "angebot": [{"de": "Wucher", "en": "Usury", "guete": 1.0}]})
    app._anzeigen("zustand", {"verfuegbar": True, "spielzeit": 900.0, "mitschrift": "a"})
    assert app.auswahl
    app._anzeigen("zustand", {"verfuegbar": True, "spielzeit": 50.0, "mitschrift": "b"})
    assert not app.auswahl
    assert any("verfallen" in t for t in geschrieben)


def test_das_eigene_foto_wird_nach_dem_lesen_geloescht(gui, tmp_path: Path) -> None:
    """Je Aufnahme eine Datei im Temp-Ordner -- ohne Aufräumen sammelten sie
    sich an. Fremde Bilder (`--bild`) bleiben unberührt."""
    app = _vorbereitet(gui, tmp_path)
    eigen = gui.screen.neuer_bildpfad()
    fremd = tmp_path / "mein-bild.png"
    fremd.write_bytes(b"x")
    for pfad in (eigen, fremd):
        app._anzeigen("auswahl", {"verfuegbar": False, "quelle": str(pfad),
                                  "gelesene_zeilen": 0, "grund": "Nichts erkannt."})
    assert not eigen.exists() and fremd.exists()


def test_die_kettentabelle_zeigt_ob_das_gebaeude_fehlt(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    zeilen = []
    app.ketten = Wurzel()
    app.ketten.get_children = lambda: []
    app.ketten.delete = lambda *a: None
    app.ketten.insert = lambda *a, values=(), **k: zeilen.append(values)
    app._zeige_ketten({"empfehlung": "x", "ketten": [
        {"gebaeude": "Grill", "einsatz": [], "gewinn": 25, "faktor": 6.0, "status": "fehlt"}]})
    assert zeilen[0][0] == "Grill (fehlt)"


def test_fallende_waren_stehen_in_der_lage(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    gesagt: list[str] = []
    app.warnung = Wurzel()
    app.warnung.configure = lambda **kw: gesagt.append(kw.get("text", ""))
    app._anzeigen("wissen", {"verfuegbar": True, "trends": {"fallend": [
        {"ware": "Eggs", "ware_de": "Eier", "rate_je_minute": -6.0}], "steigend": []}})
    assert "Eier -6.0/min" in gesagt[-1]
    app._rat_holen()
    assert app.rechner.gebeten[-1][1]["wissen"]["trends"]["fallend"][0]["ware"] == "Eggs"


def test_stimmt_nicht_merkt_sich_die_korrektur(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app._anzeigen("rat", {"ok": True, "text": "Pakete öffnest du im Hauptlager.", "fuss": ""})
    app.korrektur = Variable(value="Pakete kann man nicht öffnen")
    app._korrektur_senden()
    art, daten = app.rechner.gebeten[-1]
    assert art == "korrektur"
    assert daten == {"aussage": "Pakete öffnest du im Hauptlager.",
                     "korrektur": "Pakete kann man nicht öffnen"}


def test_der_reiter_laeufe_zeigt_berichte_und_lehren(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    geschrieben: list[str] = []
    app._schreiben = lambda feld, text: geschrieben.append(text)
    app._anzeigen("laeufe", {"lehren": ["In 3 von 4 Niederlagen …"], "berichte": [
        {"kennung": "lauf-a", "biom": "Royal Woodlands", "jahre": 3, "ausgang": "verloren",
         "nahrung_min_reichweite": {"sekunden": 43.0, "jahr": 1}, "ungeduld_max": 9.5,
         "empfehlungen": [{"jahr": 1, "text": "Nimm das Nahrungssammlerlager."}]}]})
    text = geschrieben[-1]
    assert "In 3 von 4 Niederlagen" in text and "lauf-a" in text and "verloren" in text
    assert "Nahrungssammlerlager" in text


def test_laeufe_text_nennt_hunger_und_ursache(gui) -> None:
    text = gui._laeufe_text({"lehren": [], "berichte": [
        {"kennung": "lauf-b", "ausgang": "verloren", "hunger": 9, "gegangen": 3,
         "ursache": "Hunger/Abwanderung"}]})
    assert "Hunger 9× · 3 gegangen" in text and "Ursache: Hunger/Abwanderung" in text


def test_statistik_steht_in_der_lage(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    gesetzt = {}
    app.felder["statistik"] = types.SimpleNamespace(
        configure=lambda **kw: gesetzt.update(kw))
    app._zeige_zustand({"jahr": 1, "statistik": {"hunger": 2, "gegangen": 0, "tot": 0},
                        "lichtungen": 3})
    assert gesetzt["text"] == "Hunger 2× · 0 gegangen · 0 tot · 3 Lichtungen"


# --------------------------------------------------------------------------
# Runde 11: Bauplanwahl automatisch
# --------------------------------------------------------------------------

VERGLEICH = [{"gebaeude": "Stamping Mill", "gebaeude_de": "Pochwerk", "besser_oder_neu": 1,
              "nahrung": 0, "zutaten_im_lager": True, "waren": [
                  {"ware": "Bricks", "ware_de": "Ziegel", "sterne": 2, "besser": False,
                   "bisher": {"sterne": 2, "gebaeude": "Workshop", "gebaeude_de": "Werkstatt",
                              "status": "baubar"},
                   "zutaten": [{"ware": "Clay", "ware_de": "Lehm", "im_lager": 58}]},
                  {"ware": "Copper Bar", "ware_de": "Kupferbarren", "sterne": 2,
                   "besser": True, "bisher": None}]}]


def _mit_wahl(app, angebot=("Stamping Mill", "Rain Mill"), wahl_id=7):
    app.zustand = {"mitschrift": "lauf", "bauplan_wahl": {"angebot": list(angebot),
                                                          "id": wahl_id}}
    app.wissen = {"bauplan_vergleich": VERGLEICH}
    geschrieben: list[str] = []
    app._schreiben = lambda feld, text: geschrieben.append(text)
    return geschrieben


def test_eine_neue_bauplanwahl_fragt_genau_einmal(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    geschrieben = _mit_wahl(app)
    app._anzeigen("anmeldung", True)
    app._anzeigen("anmeldung", True)                 # derselbe Durchgang noch einmal
    gefragt = [d for art, d in app.rechner.gebeten if art == "rat"]
    assert len(gefragt) == 1 and gefragt[0]["automatisch"] is True
    assert "Baupläne" in gefragt[0]["frage"]
    tabelle = next(t for t in geschrieben if t.startswith("Bauplanwahl"))
    assert "Ziegel ★★ – bisher ★★ (Werkstatt, freigeschaltet)" in tabelle
    assert "↑ Kupferbarren ★★ – neu" in tabelle
    assert "Pochwerk" in app._warn_bauplan
    # Neu gewürfelt: anderes Angebot, neue Wahl.
    app.zustand["bauplan_wahl"]["angebot"] = ["Kiln", "Workshop"]
    app._anzeigen("anmeldung", True)
    assert len([1 for art, _ in app.rechner.gebeten if art == "rat"]) == 2


def test_ohne_anmeldung_oder_haekchen_nur_die_tabelle(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    geschrieben = _mit_wahl(app)
    app._anzeigen("anmeldung", False)
    app.bauplan_auto = Variable(value=False)
    _mit_wahl(app, wahl_id=8)
    app._anzeigen("anmeldung", True)
    assert not [1 for art, _ in app.rechner.gebeten if art == "rat"]
    assert any(t.startswith("Bauplanwahl") for t in geschrieben)


def test_ist_die_wahl_vorbei_verschwindet_der_hinweis(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    _mit_wahl(app)
    app._anzeigen("anmeldung", False)
    assert app._warn_bauplan
    app.zustand = {"mitschrift": "lauf"}
    app._anzeigen("anmeldung", False)
    assert app._warn_bauplan == ""


# --------------------------------------------------------------------------
# Runde 13: Knopf „Aktualisieren“
# --------------------------------------------------------------------------


def _neustart_beobachten(app, monkeypatch, antwort: bool):
    passiert = []
    app._neustart_fragen = lambda text: passiert.append(("gefragt", text)) or antwort
    monkeypatch.setattr(gui_modul(app).aktualisieren, "neu_starten",
                        lambda: passiert.append(("neu_gestartet",)))
    app._schliessen = lambda: passiert.append(("geschlossen",))
    return passiert


def gui_modul(app):
    return sys.modules[type(app).__module__]


def test_der_knopf_bittet_um_aktualisieren(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app._aktualisieren()
    assert app.rechner.gebeten[-1][0] == "aktualisieren"


def test_neue_version_mit_ja_startet_neu(gui, tmp_path: Path, monkeypatch) -> None:
    app = _vorbereitet(gui, tmp_path)
    passiert = _neustart_beobachten(app, monkeypatch, antwort=True)
    app._anzeigen("aktualisiert", {"ok": True, "neu": True, "text": "Neue Version geladen (abc1234)."})
    assert [p[0] for p in passiert] == ["gefragt", "neu_gestartet", "geschlossen"]


def test_neue_version_mit_nein_bleibt(gui, tmp_path: Path, monkeypatch) -> None:
    app = _vorbereitet(gui, tmp_path)
    passiert = _neustart_beobachten(app, monkeypatch, antwort=False)
    app._anzeigen("aktualisiert", {"ok": True, "neu": True, "text": "Neue Version geladen."})
    assert [p[0] for p in passiert] == ["gefragt"]


def test_ohne_neue_version_oder_mit_fehler_keine_frage(gui, tmp_path: Path, monkeypatch) -> None:
    app = _vorbereitet(gui, tmp_path)
    passiert = _neustart_beobachten(app, monkeypatch, antwort=True)
    app._anzeigen("aktualisiert", {"ok": True, "neu": False, "text": "Schon aktuell (abc1234)."})
    app._anzeigen("aktualisiert", {"ok": False, "neu": False,
                                   "text": "git pull ging nicht: local changes"})
    assert passiert == []
    assert "local changes" in app.status_alles


def test_schon_freigeschaltet_steht_in_der_tabelle(gui) -> None:
    text = gui._bauplan_text({"angebot": ["Trapper's Camp"]}, [
        {"gebaeude": "Trapper's Camp", "gebaeude_de": "Fallenstellerlager",
         "schon_freigeschaltet": "baubar", "besser_oder_neu": 0, "nahrung": 0, "waren": []}])
    assert "SCHON FREIGESCHALTET" in text


def test_bauplantabelle_nennt_die_stufe(gui) -> None:
    text = gui._bauplan_text({"angebot": ["Ranch"]}, [
        {"gebaeude": "Ranch", "gebaeude_de": "Ranch", "besser_oder_neu": 1, "nahrung": 0,
         "waren": []}])
    assert "Tier B (GameRant, 2023-05, Early Access)" in text


# --------------------------------------------------------------------------
# Runde 21: HUD über dem Spiel
# --------------------------------------------------------------------------


class HudProtokoll:
    """Ein HUD, das mitschreibt."""

    def __init__(self, sichtbar: bool = True):
        self.protokoll: list = []
        self.sichtbar = sichtbar
        self.werte = {"tasten": {}}

    def zeigen(self, art, wert=None):
        self.protokoll.append(("zeigen", art))

    def verstecken(self, vorlaeufig=False):
        self.protokoll.append(("verstecken", vorlaeufig))

    def einblenden(self, vorlaeufig=False):
        self.protokoll.append(("einblenden", vorlaeufig))

    def umschalten(self):
        self.sichtbar = not self.sichtbar
        return self.sichtbar

    def auffrischen(self):
        self.protokoll.append(("auffrischen",))


def test_das_hud_wird_gebaut_und_gespeist(gui, tmp_path: Path) -> None:
    app = gui.App(tmp_path / "save", tmp_path / "runs", tmp_path / "kb.sqlite")
    app.rechner.stoppen()
    assert app.hud is not None
    app.hud = HudProtokoll()
    for art, wert in (("zustand", {"jahr": 2}), ("engpass", {"verfuegbar": True, "uhren": []}),
                      ("wissen", {}), ("rat", {"ok": True, "text": "Nimm X."})):
        app._anzeigen(art, wert)
    assert [p[1] for p in app.hud.protokoll if p[0] == "zeigen"] == [
        "zustand", "engpass", "wissen", "rat"]
    assert ("auffrischen",) in app.hud.protokoll          # das Alter läuft mit


def test_die_taste_liest_und_versteckt_nur_das_hud(gui, tmp_path: Path, monkeypatch) -> None:
    """Aus dem Spiel heraus darf das Hauptfenster nicht vor das Spiel springen."""
    app = _vorbereitet(gui, tmp_path)
    app.hud = HudProtokoll()
    _gleichlaufend(monkeypatch, gui)
    monkeypatch.setattr(gui.screen, "aufnehmen", lambda *a, **k: tmp_path / "foto.png")
    app.zustand = {"bauplan_wahl": {"angebot": ["Kiln", "Workshop"]}}
    app._anzeigen("taste", "lesen")
    assert "withdraw" not in app.root.protokoll
    assert ("verstecken", True) in app.hud.protokoll
    _foto_und_abholen(app)
    assert app.rechner.gebeten[-1][1]["arten"] == ("building",)   # offene Bauplanwahl
    assert ("einblenden", True) in app.hud.protokoll
    assert "deiconify" not in app.root.protokoll


def test_ein_ausgeschaltetes_hud_bleibt_nach_dem_foto_aus(gui, tmp_path: Path,
                                                         monkeypatch) -> None:
    app = _vorbereitet(gui, tmp_path)
    app.hud = HudProtokoll(sichtbar=False)
    _gleichlaufend(monkeypatch, gui)
    monkeypatch.setattr(gui.screen, "aufnehmen", lambda *a, **k: tmp_path / "foto.png")
    app._auswahl_lesen()                                  # Knopf im Hauptfenster
    assert "withdraw" in app.root.protokoll
    _foto_und_abholen(app)
    assert not [p for p in app.hud.protokoll if p[0] in ("verstecken", "einblenden")]
    assert "deiconify" in app.root.protokoll
    assert app.rechner.gebeten[-1][1]["arten"] == ("effect",)


def test_die_taste_hud_schaltet_um(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app.hud = HudProtokoll()
    app._anzeigen("taste", "hud")
    assert app.hud.sichtbar is False and app.hud_an.get() is False
    app._anzeigen("taste", "hud")
    assert app.hud.sichtbar is True and app.hud_an.get() is True


GELESEN = {"verfuegbar": True, "quelle": "foto.png", "gelesene_zeilen": 4,
           "angebot": [{"de": "Verstärkte Äxte", "en": "Reinforced Axes", "guete": 0.97,
                        "belegt": True, "kind": "effect"}],
           "belegt": [{"de": "Verstärkte Äxte", "en": "Reinforced Axes", "guete": 0.97,
                       "belegt": True, "kind": "effect"}]}


def test_gelesene_karten_fragen_den_rat_einmal_je_angebot(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app.hud = HudProtokoll()
    app.zustand = {"mitschrift": "lauf"}
    app._anzeigen("anmeldung", True)
    app._anzeigen("auswahl", GELESEN)
    app._anzeigen("auswahl", GELESEN)                     # dieselben Karten noch einmal
    gefragt = [d for art, d in app.rechner.gebeten if art == "rat"]
    assert len(gefragt) == 1 and gefragt[0]["automatisch"] is True
    assert "Karten" in gefragt[0]["frage"]
    # Erst die Auswahl ins HUD, dann „Rat wird gefragt“ -- sonst löschte die
    # Auswahl den Hinweis gleich wieder.
    arten = [p[1] for p in app.hud.protokoll if p[0] == "zeigen"]
    assert arten.index("auswahl") < arten.index("rat_frage")


def test_ohne_haekchen_oder_anmeldung_fragen_karten_nicht(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    app._anzeigen("anmeldung", False)
    app._anzeigen("auswahl", GELESEN)
    app._anmeldung = True
    app.bauplan_auto = Variable(value=False)
    app._anzeigen("auswahl", dict(GELESEN, belegt=[dict(GELESEN["belegt"][0], en="Other")]))
    assert not [1 for art, _ in app.rechner.gebeten if art == "rat"]


def test_der_rat_bekommt_den_engpass(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    e = {"verfuegbar": True, "entscheidend": "ungeduld", "uhren": [
        {"art": "ungeduld", "sekunden": 100.0, "stufe": "rot", "text": "voll in 2 min"}]}
    app._anzeigen("engpass", e)
    app._rat_holen()
    assert app.rechner.gebeten[-1][1]["engpass"] == e
    app._anzeigen("zustand", {"verfuegbar": False, "grund": "weg"})
    assert app.engpass is None


def test_ein_tastenfehler_steht_in_der_statuszeile(gui, tmp_path: Path) -> None:
    app = _vorbereitet(gui, tmp_path)
    gesetzt = []
    app.status = Egal()
    app.status.configure = lambda **kw: gesetzt.append(kw.get("text"))
    app._anzeigen("tastenfehler", "„Strg+Umschalt+L“ ist schon vergeben")
    assert gesetzt and "vergeben" in gesetzt[-1]


def test_ein_kaputtes_hud_nimmt_das_fenster_nicht_mit(gui, tmp_path: Path,
                                                    monkeypatch) -> None:
    def platzt(*a, **k):
        raise RuntimeError("kein HUD")

    monkeypatch.setattr(gui, "Hud", platzt)
    app = gui.App(tmp_path / "save", tmp_path / "runs", tmp_path / "kb.sqlite")
    app.rechner.stoppen()
    assert app.hud is None and app.tasten is None
    app._anzeigen("engpass", {"verfuegbar": True, "uhren": []})
    app._anzeigen("taste", "hud")
    app._hud_schalter()
