"""Das HUD über dem Spiel (Runde 21): reine Hilfen und der Kasten unter echtem Tk."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from ats_assistant import engpass, hud

# --------------------------------------------------------------------------
# Reine Hilfen
# --------------------------------------------------------------------------


def test_schrift_waechst_mit_der_breite_in_grenzen() -> None:
    assert hud.schriftgroesse(360) == 10
    assert hud.schriftgroesse(100) == hud.SCHRIFT_MIN
    assert hud.schriftgroesse(5000) == hud.SCHRIFT_MAX


def test_ein_kasten_ausserhalb_kommt_herein() -> None:
    assert hud.in_den_schirm(3000, 2000, 360, 200, 1920, 1080) == (1560, 880)
    assert hud.in_den_schirm(-50, -10, 360, 200, 1920, 1080) == (0, 0)
    assert hud.in_den_schirm(100, 100, 360, 200, 1920, 1080) == (100, 100)
    assert hud.in_den_schirm(0, 0, 3000, 200, 1920, 1080) == (0, 0)   # breiter als der Schirm


def test_tastenkombinationen_lesen() -> None:
    mods, code = hud.kombination("Strg+Umschalt+L")
    assert code == ord("L") and mods == hud.MOD_CONTROL | hud.MOD_SHIFT | hud.MOD_NOREPEAT
    assert hud.kombination("alt+f9")[1] == 0x78
    for falsch in ("L", "Umschalt+L", "Strg+Ä", "Strg+F30", "Hyper+L", ""):
        with pytest.raises(ValueError):
            hud.kombination(falsch)


def test_einstellungen_ueberstehen_eine_kaputte_datei(tmp_path: Path) -> None:
    pfad = tmp_path / "hud.json"
    assert hud.lade_einstellungen(pfad) == hud.VORGABEN
    pfad.write_text("{kaputt", encoding="utf-8")
    assert hud.lade_einstellungen(pfad) == hud.VORGABEN
    pfad.write_text(json.dumps({"x": 50, "breite": 10, "eingeklappt": "ja", "sichtbar": False,
                                "tasten": {"lesen": "Alt+F9", "fremd": "x"}}), encoding="utf-8")
    werte = hud.lade_einstellungen(pfad)
    assert werte["x"] == 50 and werte["breite"] == hud.BREITE_MIN
    assert werte["eingeklappt"] is False and werte["sichtbar"] is False
    assert werte["tasten"] == {"lesen": "Alt+F9", "hud": "Strg+Umschalt+H"}


def test_auswahlzeile_karten_vor_bauplan_mit_tier() -> None:
    zustand = {"bauplan_wahl": {"angebot": ["Kiln", "Workshop"]}}
    wissen = {"bauplan_vergleich": [
        {"gebaeude": "Kiln", "gebaeude_de": "Brennofen", "besser_oder_neu": 2},
        {"gebaeude": "Workshop", "gebaeude_de": "Werkstatt", "schon_freigeschaltet": True}]}
    zeile = hud.auswahlzeile(zustand, wissen, None)
    assert zeile.startswith("Bauplan: Brennofen ") and "↑2" in zeile
    assert "Werkstatt" in zeile and "(schon da)" in zeile
    karten = {"verfuegbar": True, "angebot": [
        {"de": "Verstärkte Äxte", "en": "Reinforced Axes", "kind": "effect", "belegt": True},
        {"de": "Fuchs", "en": "Fox", "kind": "species", "belegt": False}]}
    zeile = hud.auswahlzeile(zustand, wissen, karten)
    assert zeile == "Karten: Verstärkte Äxte S"          # GameRant Platz 1, Oberfläche weg
    assert hud.auswahlzeile(None, None, {"verfuegbar": False}) == ""


def test_kopf_und_info() -> None:
    e = engpass.uhren({"reichweite_sekunden": 240.0}, {})
    assert hud.kopfzeile(e) == ("Engpass: Nahrung 4 min", "rot")
    assert hud.kopfzeile(None) == ("Engpass: –", "unbekannt")
    assert hud.infozeile({"verfuegbar": False}) == "Kein Spielstand"
    assert hud.infozeile({"jahr": 3}) == "Jahr 3"


# --------------------------------------------------------------------------
# Der Kasten unter echtem Tk
# --------------------------------------------------------------------------

tk = pytest.importorskip("tkinter")
braucht_anzeige = pytest.mark.skipif(not os.environ.get("DISPLAY"),
                                     reason="keine Anzeige -- mit `xvfb-run -a pytest` starten")


@pytest.fixture
def wurzel():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def _ereignis(x: int, y: int = 0):
    return SimpleNamespace(x_root=x, y_root=y)


@braucht_anzeige
def test_der_kasten_zeigt_jede_meldung(wurzel, tmp_path: Path) -> None:
    kasten = hud.Hud(wurzel, pfad=tmp_path / "hud.json")
    e = engpass.uhren({"reichweite_sekunden": 240.0}, {"sekunden_bis_verlust": 1200.0},
                      {"zysten": {"entstanden": 4, "verbrannt": 3}})
    meldungen = [
        ("zustand", {"jahr": 3, "gespeichert": "2026-09-26T10:00:00+00:00",
                     "bauplan_wahl": {"angebot": ["Kiln", "Workshop"]}}),
        ("engpass", e), ("wissen", {"bauplan_vergleich": []}),
        ("rat_frage", None), ("rat", {"ok": True, "text": "Nimm den Brennofen. Weil …"}),
        ("lesen", None),
        ("auswahl", {"verfuegbar": True, "belegt": [], "angebot": [
            {"de": "Verstärkte Äxte", "en": "Reinforced Axes", "kind": "effect"}]}),
        ("auswahl", {"verfuegbar": False, "grund": "Nichts erkannt."}),
        ("rat", {"ok": False, "text": "Keine Anmeldung gefunden."}), ("rat_leeren", None),
        ("tastenfehler", "„Strg+Umschalt+L“ ist schon vergeben"),
        ("zustand", None), ("engpass", None), ("wissen", "kaputt"), ("unbekannt", 1),
        ("auswahl", None), ("rat", None)]
    for art, wert in meldungen:
        kasten.zeigen(art, wert)                        # keine darf werfen
        wurzel.update_idletasks()
    kasten.zeigen("zustand", {"jahr": 3, "bauplan_wahl": {"angebot": ["Kiln"]}})
    kasten.zeigen("engpass", e)
    assert kasten.titel.cget("text") == "Engpass: Nahrung 4 min"
    assert kasten.zeilen["pestfaeule"]["text"].cget("text").startswith("Zysten 4, verbrannt 3")
    assert kasten.auswahl.cget("text").startswith("Bauplan: ")
    kasten.zeigen("rat", {"ok": True, "text": "Nimm den Brennofen. Weil er Ziegel macht."})
    wurzel.update_idletasks()
    assert kasten.rat.cget("text") == "Rat: Nimm den Brennofen."
    # Die Auswahl steht über dem Rat, auch wenn sie nach ihm dazukommt.
    ordnung = [w for w in kasten.koerper.pack_slaves() if w in (kasten.auswahl, kasten.rat)]
    assert ordnung == [kasten.auswahl, kasten.rat]


@braucht_anzeige
def test_ziehen_groesse_und_einklappen_werden_gemerkt(wurzel, tmp_path: Path) -> None:
    pfad = tmp_path / "hud.json"
    kasten = hud.Hud(wurzel, pfad=pfad)
    kasten.zeigen("engpass", engpass.uhren({"reichweite_sekunden": 240.0}, {}))

    kasten._zug_anfang(_ereignis(kasten.werte["x"] + 10, kasten.werte["y"] + 5))
    kasten._zug_weiter(_ereignis(210, 105))
    kasten._merken()
    assert (kasten.werte["x"], kasten.werte["y"]) == (200, 100)
    kasten._zug_weiter(_ereignis(-500, -500))          # nicht aus dem Schirm hinaus
    assert (kasten.werte["x"], kasten.werte["y"]) == (0, 0)
    kasten._zug_weiter(_ereignis(210, 105))

    schrift_vorher = str(kasten.titel.cget("font"))
    kasten._griff_anfang(_ereignis(100))
    kasten._griff_weiter(_ereignis(280))
    assert kasten.werte["breite"] == hud.BREITE_VORGABE + 180
    assert str(kasten.titel.cget("font")) != schrift_vorher
    kasten.groesse_aendern(-10_000)
    assert kasten.werte["breite"] == hud.BREITE_MIN
    kasten.groesse_aendern(hud.BREITE_SCHRITT)
    assert kasten.werte["breite"] == hud.BREITE_MIN + hud.BREITE_SCHRITT

    kasten.umklappen()
    wurzel.update_idletasks()
    assert kasten.werte["eingeklappt"] is True
    assert not kasten.koerper.winfo_manager()           # nur die Kopfzeile bleibt
    assert kasten.titel.cget("text") == "Engpass: Nahrung 4 min"

    gemerkt = json.loads(pfad.read_text(encoding="utf-8"))
    assert gemerkt["x"] == 200 and gemerkt["y"] == 100 and gemerkt["eingeklappt"] is True
    assert gemerkt["breite"] == hud.BREITE_MIN + hud.BREITE_SCHRITT

    wieder = hud.Hud(wurzel, pfad=pfad)                 # nach einem Neustart
    assert (wieder.werte["x"], wieder.werte["y"]) == (200, 100)
    assert wieder.werte["eingeklappt"] is True and not wieder.koerper.winfo_manager()
    wieder.umklappen()
    wurzel.update_idletasks()
    assert wieder.koerper.winfo_manager() == "pack"
    assert json.loads(pfad.read_text(encoding="utf-8"))["eingeklappt"] is False


@braucht_anzeige
def test_vorlaeufig_versteckt_kommt_zurueck_ausgeschaltet_nicht(wurzel, tmp_path: Path) -> None:
    geschlossen = []
    kasten = hud.Hud(wurzel, pfad=tmp_path / "hud.json",
                     beim_schliessen=lambda: geschlossen.append(True))
    kasten.verstecken(vorlaeufig=True)
    assert kasten.fenster.state() == "withdrawn" and kasten.sichtbar
    kasten.einblenden(vorlaeufig=True)
    assert kasten.fenster.state() != "withdrawn"

    kasten.schliessen()                                  # „×“
    assert geschlossen and not kasten.sichtbar
    kasten.einblenden(vorlaeufig=True)                   # nach einem Foto: bleibt aus
    assert kasten.fenster.state() == "withdrawn"
    assert json.loads((tmp_path / "hud.json").read_text(encoding="utf-8"))["sichtbar"] is False
    assert kasten.umschalten() is True and kasten.fenster.state() != "withdrawn"


@braucht_anzeige
def test_der_knopf_liest(wurzel, tmp_path: Path) -> None:
    gelesen = []
    kasten = hud.Hud(wurzel, pfad=None, beim_lesen=lambda: gelesen.append(1))
    kasten._lesen()
    assert gelesen == [1]
    kasten.groesse_aendern(60)                           # ohne Pfad: nichts geschrieben
    assert not list(tmp_path.iterdir())


def test_tasten_ausserhalb_von_windows_starten_nicht() -> None:
    if hud._unter_windows():
        pytest.skip("unter Windows startet der Faden wirklich")
    tasten = hud.Tasten({"lesen": "Strg+Umschalt+L"}, lambda art, wert: None)
    assert tasten.starten() is False
    tasten.stoppen()                                     # darf nicht werfen


@braucht_anzeige
def test_die_probe_laeuft_und_merkt_sich_nichts(tmp_path: Path, monkeypatch, capsys) -> None:
    import importlib.util

    pfad = Path(__file__).resolve().parent.parent / "tools" / "hud_probe.py"
    spec = importlib.util.spec_from_file_location("hud_probe", pfad)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    monkeypatch.chdir(tmp_path)
    assert probe.main(["--sekunden", "0.3", "--tasten"]) == 0
    ausgabe = capsys.readouterr().out
    assert "Bildschirm laut Tk" in ausgabe
    assert not list(tmp_path.rglob("hud.json"))


@braucht_anzeige
def test_ein_langer_hinweis_endet_am_satz(wurzel) -> None:
    kasten = hud.Hud(wurzel, pfad=None)
    kasten.zeigen("auswahl", {"verfuegbar": False, "grund": (
        "Keine Aufnahme moeglich. Entweder `pip install mss`, oder ein Bildschirmfoto "
        "von Hand ablegen und mit --bild uebergeben.")})
    assert kasten.auswahl.cget("text") == "Keine Aufnahme moeglich."


# --------------------------------------------------------------------------
# Die Windows-Pfade -- hier nicht ausführbar, also mit einer nachgebauten
# user32. Fängt Tippfehler in Namen und eine Schleife, die nie endet.
# --------------------------------------------------------------------------


class FalscheFunktion:
    def __init__(self, protokoll: list, name: str, antwort=1):
        self.protokoll, self.name, self.antwort = protokoll, name, antwort
        self.argtypes = self.restype = None

    def __call__(self, *args):
        self.protokoll.append((self.name, args))
        return self.antwort(*args) if callable(self.antwort) else self.antwort


class FalscheUser32:
    def __init__(self, protokoll: list, belegt: set[int] = frozenset()):
        import ctypes
        from ctypes import wintypes

        self.nachrichten = [(hud.WM_HOTKEY, 1), (hud.WM_HOTKEY, 2), (hud.WM_HOTKEY, 99)]

        def hole(zeiger, *_):
            if not self.nachrichten:
                return 0                                   # WM_QUIT
            art, nummer = self.nachrichten.pop(0)
            msg = ctypes.cast(zeiger, ctypes.POINTER(wintypes.MSG)).contents
            msg.message, msg.wParam = art, nummer
            return 1

        antworten = {"GetMessageW": hole, "GetWindowLongW": 0x100,
                     "RegisterHotKey": lambda h, nummer, m, c: 0 if nummer in belegt else 1}
        for name in ("GetParent", "GetWindowLongW", "SetWindowLongW", "SetWindowPos",
                     "RegisterHotKey", "UnregisterHotKey", "GetMessageW", "PostThreadMessageW"):
            setattr(self, name, FalscheFunktion(protokoll, name, antworten.get(name, 1)))


def _wie_windows(monkeypatch, user32) -> None:
    import ctypes

    monkeypatch.setattr(hud.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: user32, raising=False)
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(
        kernel32=SimpleNamespace(GetCurrentThreadId=lambda: 4711)), raising=False)


def test_die_tastenschleife_meldet_und_meldet_ab(monkeypatch) -> None:
    protokoll: list = []
    _wie_windows(monkeypatch, FalscheUser32(protokoll, belegt={2}))
    gemeldet: list = []
    tasten = hud.Tasten({"lesen": "Strg+Umschalt+L", "hud": "Strg+Umschalt+H",
                         "kaputt": "L"}, lambda art, wert: gemeldet.append((art, wert)))
    tasten._schleife()                                  # im Test ohne Faden
    assert ("taste", "lesen") in gemeldet
    assert not [g for g in gemeldet if g == ("taste", "hud")]   # belegt: nie angemeldet
    fehler = [w for a, w in gemeldet if a == "tastenfehler"]
    assert any("schon vergeben" in f for f in fehler) and any("„L“" in f for f in fehler)
    assert [n for n, _ in protokoll if n == "UnregisterHotKey"] == ["UnregisterHotKey"]
    tasten.stoppen()
    assert protokoll[-1] == ("PostThreadMessageW", (4711, hud.WM_QUIT, 0, 0))


def test_der_fensterstil_wird_gesetzt(monkeypatch) -> None:
    protokoll: list = []
    _wie_windows(monkeypatch, FalscheUser32(protokoll))
    fenster = SimpleNamespace(update_idletasks=lambda: None, wm_frame=lambda: "0x1a2b",
                              winfo_id=lambda: 7)
    assert hud.windows_stil(fenster) is True
    gesetzt = next(args for name, args in protokoll if name == "SetWindowLongW")
    assert gesetzt[0] == 0x1a2b and gesetzt[1] == hud.GWL_EXSTYLE
    assert gesetzt[2] & hud.WS_EX_TOOLWINDOW and gesetzt[2] & hud.WS_EX_NOACTIVATE
    assert protokoll[-1][0] == "SetWindowPos"
