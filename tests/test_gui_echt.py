"""Das Fenster unter echtem Tk.

Die Stub-Fassung in `test_gui.py` prüft die Verdrahtung: kommt jede
Nachrichtenart an, wirft keine. Was sie nicht kann, ist Tk widersprechen zu
lassen — ob `ttk` jede Option annimmt, ob die Rasteraufteilung aufgeht, ob
nach dem Anzeigen auch etwas dasteht.

Läuft nur, wo tkinter und eine Anzeige da sind (`xvfb-run` genügt). Sonst
übersprungen, nicht rot: auf dem Spielrechner soll die Suite ohne
Bildschirm durchlaufen.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")
ttk = pytest.importorskip("tkinter.ttk")

pytestmark = pytest.mark.skipif(
    not os.environ.get("DISPLAY"),
    reason="keine Anzeige -- mit `xvfb-run -a pytest` starten")


@pytest.fixture
def app(tmp_path: Path):
    from ats_assistant import gui

    fenster = gui.App(tmp_path / "save", tmp_path / "runs", tmp_path / "kb.sqlite")
    fenster.rechner.stoppen()                 # kein Thread, der weiterläuft
    fenster.root.update_idletasks()
    yield fenster
    fenster.root.destroy()


BEISPIELE = {
    "zustand": {"jahr": 3, "biom": "Coastal Grove", "prestige": 13,
                "bevoelkerung": 24, "reputation": 8.0, "reputation_ziel": 18,
                "ungeduld": 4.0, "ungeduld_schwelle": 14,
                "feindseligkeit": {"level": 3, "points": 72},
                "zeitpunkt": "2026-09-22T10:00:00+00:00"},
    "nahrung": {"reichweite_sekunden": 340.0, "warnung": "Nahrung reicht 340 s"},
    "ungeduld": {"sekunden_bis_verlust": 1200.0},
    "ketten": {"empfehlung": "Räucherei: 40 Meat werden zu Dörrfleisch",
               "begruendung": "Faktor 4", "alternative": "oder Weinkeller",
               "ketten": [{"gebaeude": "Smokehouse", "gebaeude_de": "Räucherei",
                           "einsatz": [{"menge": 40, "ware": "Meat"}],
                           "gewinn": 120.0, "faktor": 4.0, "engpass": "Meat",
                           "sekunden": 480.0, "reichweite_plus_sekunden": 1200}]},
    "auswahl": {"verfuegbar": True, "quelle": "hand", "gelesene_zeilen": 2,
                "angebot": [
        {"de": "Pilzführer", "en": "Fungal Guide", "guete": 0.98,
         "seltenheit": "Epic", "wirkung": "+1 Pilze je 25 Produktion"}]},
    "rat": {"ok": True, "text": "Nimm die Räucherei.", "fuss": "claude-opus-5"},
    "umgebung": {"fehlt": [], "namen": 2266, "mitschriften_da": 2},
    "anmeldung": False,
    "fehler": "irgendwas ist schiefgegangen",
}


def test_das_fenster_baut_sich_wirklich_auf(app) -> None:
    """Jede Option muss Tk gefallen, nicht nur einem Stub."""
    assert app.root.winfo_exists()
    assert len(app.reiter.tabs()) == 5
    assert [app.reiter.tab(t, "text") for t in app.reiter.tabs()] == [
        "Lage", "Nahrung", "Auswahl", "Rat", "Läufe"]


def test_laeufe_und_korrektur_mit_echtem_tk(app) -> None:
    app._anzeigen("laeufe", {"lehren": ["Hinweis, kein Befund: x"], "berichte": [
        {"kennung": "lauf-a", "ausgang": "verloren", "ungeduld_max": "kaputt",
         "empfehlungen": [{"text": "Nimm das Lager."}]}]})
    text = app.laeufe_text.get("1.0", "end")
    assert "lauf-a" in text and "Nimm das Lager." in text
    gebeten = []
    app.rechner.bitte = lambda art, **d: gebeten.append((art, d))
    app.korrektur.set("  Geht nicht  ")
    app._korrektur_senden()
    assert gebeten == [("korrektur", {"aussage": "", "korrektur": "Geht nicht"})]
    assert app.korrektur.get() == ""


def test_nach_dem_anzeigen_steht_auch_etwas_da(app) -> None:
    """Der Stub prüft, dass nichts wirft. Hier zählt das Ergebnis."""
    app._anzeigen("zustand", BEISPIELE["zustand"])
    app.root.update_idletasks()

    kopf = app.kopf.cget("text")
    assert "Jahr 3" in kopf and "Coastal Grove" in kopf and "Prestige 13" in kopf
    assert app.felder["bevoelkerung"].cget("text") == "24"
    # Nicht das rohe Dictionary: am Spielrechner stand hier
    # {'level': 3, 'points': 72, 'sources': -- rechts abgeschnitten.
    assert app.felder["feindseligkeit"].cget("text") == "Stufe 3 · 72 Punkte"
    assert "8.0 von 18" in app.felder["reputation"].cget("text")
    # 8 von 18 sind rund 44 Prozent.
    assert 43 < float(app.balken["reputation"]["value"]) < 46


def test_die_ketten_landen_in_der_tabelle(app) -> None:
    app._anzeigen("ketten", BEISPIELE["ketten"])
    app.root.update_idletasks()

    zeilen = app.ketten.get_children()
    assert len(zeilen) == 1
    werte = app.ketten.item(zeilen[0], "values")
    assert werte[0] == "Räucherei"
    assert "40 Meat" in werte[1]
    assert werte[2] == "120"
    assert werte[4] == "Meat"                      # Engpass
    assert werte[6] == "20 min"                    # gewonnene Reichweite

    # Ein zweiter Durchgang darf nicht anhängen, sondern ersetzt.
    app._anzeigen("ketten", BEISPIELE["ketten"])
    assert len(app.ketten.get_children()) == 1


def test_jede_nachrichtenart_am_lebenden_fenster(app) -> None:
    for art, wert in BEISPIELE.items():
        app._anzeigen(art, wert)
        app.root.update_idletasks()
    assert "Nimm die Räucherei" in app.rat_text.get("1.0", "end")
    assert "Pilzführer" in app.auswahl_text.get("1.0", "end")
    # `fehler` kam zuletzt und steht deshalb in der Leiste -- so gehört es
    # sich: die jüngste Meldung gewinnt.
    assert "irgendwas ist schiefgegangen" in app.status.cget("text")

    # Und die nächste Runde stellt den Normalzustand wieder her.
    app._anzeigen("umgebung", BEISPIELE["umgebung"])
    app.root.update_idletasks()
    assert "2266 Namen" in app.status.cget("text")


def test_die_leeren_faelle_auch(app) -> None:
    app._anzeigen("zustand", {"verfuegbar": False, "grund": "kein Spielstand"})
    app.root.update_idletasks()
    assert app.kopf.cget("text") == "Kein Spielstand"
    assert "kein Spielstand" in app.warnung.cget("text")

    app._anzeigen("auswahl", {"verfuegbar": False, "grund": "nichts erkannt",
                              "unklar": [{"gelesen": "PILZ", "kandidaten": [
                                  {"de": "Pilzführer", "guete": 0.7}]}]})
    text = app.auswahl_text.get("1.0", "end")
    assert "nichts erkannt" in text and "Pilzführer (0.7)" in text


def test_die_warteschlange_wird_geleert_ohne_die_schleife_zu_verlieren(app) -> None:
    """`_abholen` ruft sich selbst über `after()` wieder auf."""
    app.ausgang.put(("zustand", BEISPIELE["zustand"]))
    app.ausgang.put(("ketten", BEISPIELE["ketten"]))
    app._abholen()
    app.root.update_idletasks()

    assert app.ausgang.empty()
    assert "Jahr 3" in app.kopf.cget("text")
    assert len(app.ketten.get_children()) == 1


def test_der_nachschlag_oeffnet_ein_fenster_und_schliesst_es_wieder(app) -> None:
    vorher = len(app.root.winfo_children())
    app._anzeigen("nachschlag", {"gesucht": "Holz", "namen": [
        {"de": "Holz", "en": "Wood", "kind": "resource", "confidence": "localization"}]})
    app.root.update_idletasks()
    assert len(app.root.winfo_children()) > vorher
    for kind in app.root.winfo_children():
        if isinstance(kind, tk.Toplevel):
            kind.destroy()


def test_lage_kopieren_benutzt_die_echte_zwischenablage(app) -> None:
    app.zustand = {"jahr": 2, "biom": "Coastal Grove"}
    app._lage_kopieren()
    app.root.update_idletasks()
    import json

    auszug = json.loads(app.root.clipboard_get())
    assert auszug["siedlung"]["jahr"] == 2


# --------------------------------------------------------------------------
# Welcher Weg gelaufen ist
#
# Am Spielrechner stand im Auswahlreiter der Rat zu `pip install winsdk`,
# während im Handfeld `handelsverhandlungen` stand. Es war der Bildweg --
# nur stand das nirgends. Ein Feld, das nicht sagt, woher seine Zeilen
# kommen, macht aus einem Bedienfehler einen Programmfehler.
# --------------------------------------------------------------------------


def _auswahlfeld(app) -> str:
    app.root.update_idletasks()
    return app.auswahl_text.get("1.0", "end")


def test_der_handweg_steht_ueber_dem_ergebnis(app) -> None:
    app._anzeigen("auswahl", BEISPIELE["auswahl"])
    text = _auswahlfeld(app)
    assert "Von Hand abgeglichen" in text
    assert "Pilzführer" in text


def test_der_bildweg_nennt_sich_auch_so(app) -> None:
    app._anzeigen("auswahl", {"verfuegbar": False, "quelle": "/tmp/schirm.png",
                              "gelesene_zeilen": 0, "grund": "Nichts erkannt."})
    assert "Vom Bildschirmfoto gelesen" in _auswahlfeld(app)


def test_gescheiterter_bildweg_weist_auf_das_handfeld(app) -> None:
    """Der Fall vom Spielrechner: Text im Feld, gelaufen ist der Bildweg."""
    app.hand.insert(0, "handelsverhandlungen")
    app._anzeigen("auswahl", {
        "verfuegbar": False, "quelle": "/tmp/schirm.png", "gelesene_zeilen": 0,
        "grund": "Fuer die Texterkennung: pip install winsdk."})
    text = _auswahlfeld(app)
    assert "Abgleichen" in text


def test_der_handweg_weist_nicht_auf_sich_selbst(app) -> None:
    app.hand.insert(0, "handelsverhandlungen")
    app._anzeigen("auswahl", {"verfuegbar": False, "quelle": "hand",
                              "gelesene_zeilen": 1, "grund": "Nichts getroffen."})
    assert "Abgleichen" not in _auswahlfeld(app)


def test_das_fenster_geht_wirklich_weg_und_kommt_wieder(app) -> None:
    """Am echten Tk, nicht am Stub: `withdraw` und `deiconify` greifen.

    Der Bildweg nimmt den ganzen Bildschirm auf. Läge dieses Fenster dabei
    über den Karten, läse die Texterkennung die eigene Oberfläche.
    """
    app._auswahl_lesen()
    app.root.update_idletasks()
    assert app.root.state() == "withdrawn"

    app._fenster_zurueck()
    app.root.update_idletasks()
    assert app.root.state() == "normal"


def _alle_widgets(w):
    yield w
    for kind in w.winfo_children():
        yield from _alle_widgets(kind)


def test_der_auswahlreiter_kennt_auftraege(app) -> None:
    """Am Spielrechner stand „Wähle einen Auftrag aus" offen, und der Reiter
    konnte nur Grundsteine oder Baupläne suchen -- er las das Hauptlager im
    Hintergrund statt der drei Aufträge."""
    werte = {str(w.cget("value")) for w in _alle_widgets(app.root)
             if w.winfo_class() == "TRadiobutton"}
    assert {"effect", "building", "order"} <= werte
