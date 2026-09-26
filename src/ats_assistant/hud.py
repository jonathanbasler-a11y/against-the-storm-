"""Das HUD: ein kleiner Kasten über dem Spiel.

Wunsch vom Spielrechner (26.09.2026): nicht mehr aus dem Spiel wechseln, um
zu sehen, was gerade drängt oder was zur Wahl steht. Das HUD zeigt dasselbe
wie das Hauptfenster, nur knapp:

* was entscheidet -- Nahrung, Ungeduld, Pestfäule (`engpass.uhren`),
* die offene Wahl -- Bauplanwahl aus dem Spielstand oder gelesene Karten,
  je mit Tier, und darunter den ersten Satz des Rats,
* einen Knopf, der die Karten liest, ohne das Spiel zu verlassen.

Es rechnet nichts: `App._anzeigen` reicht jede Meldung durch (`zeigen`).

**Bedienung** (Wunsch des Spielers): an der Kopfzeile verschieben, am Griff
„◢“ unten rechts größer und kleiner ziehen (die Schrift wächst mit), „−“ und
„+“ für feste Stufen, „▁“ oder Doppelklick auf die Kopfzeile klappt ein und
aus, „×“ blendet aus. Platz, Breite und Zustand bleiben in `hud.json`.

**Über dem Spiel.** Ein Fenster ohne Rahmen, immer oben. Unter Windows
kommen zwei Stile dazu: `WS_EX_TOOLWINDOW` (nicht in Alt-Tab und Taskleiste)
und `WS_EX_NOACTIVATE` -- ein Klick ins HUD nimmt dem Spiel nicht den Fokus.
Über exklusivem Vollbild kann kein Fenster liegen; dann im Spiel das
randlose Fenster wählen.

**Tastenkombinationen** über `RegisterHotKey`: Windows meldet genau diese
Kombinationen und nichts sonst. Kein Tastatur-Hook, kein Mitlesen.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from typing import Callable

from . import tierlisten
from .rechner import alter as _alter, erster_satz

log = logging.getLogger(__name__)

# Unter dem Stellvertreter der Fenstertests gibt es kein `TclError`.
_TK_FEHLER = getattr(tk, "TclError", Exception)

# Farben: dunkler Grund, damit es über jedem Biom lesbar bleibt.
GRUND = "#16171b"
KOPF = "#26282f"
TEXT = "#eceef2"
LEISE = "#a2a5b0"
FARBEN = {"rot": "#ef4d52", "gelb": "#f2a93b", "ruhig": "#4cae63", "unbekannt": "#6f7280"}
FAMILIE = "Segoe UI"

BREITE_VORGABE = 360
BREITE_MIN = 220
BREITE_SCHRITT = 60
SCHRIFT_MIN, SCHRIFT_MAX = 8, 18
BALKEN_VOLL_SEKUNDEN = 1800.0     # voller Balken: eine halbe Stunde Spielzeit

VORGABEN: dict = {"x": 24, "y": 24, "breite": BREITE_VORGABE, "eingeklappt": False,
                  "sichtbar": True,
                  "tasten": {"lesen": "Strg+Umschalt+L", "hud": "Strg+Umschalt+H"}}

# Windows-Konstanten (winuser.h)
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
SWP_STIL = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020   # NOSIZE NOMOVE NOZORDER NOACTIVATE FRAMECHANGED
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
_MODS = {"strg": MOD_CONTROL, "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
         "umschalt": MOD_SHIFT, "shift": MOD_SHIFT, "alt": MOD_ALT, "win": MOD_WIN}


# --------------------------------------------------------------------------
# Reine Hilfen -- ohne Tk prüfbar
# --------------------------------------------------------------------------


def schriftgroesse(breite: int) -> int:
    """Die Schrift wächst mit der Breite: 360 px sind 10 pt."""
    return max(SCHRIFT_MIN, min(SCHRIFT_MAX, round(breite / 36)))


def in_den_schirm(x: int, y: int, breite: int, hoehe: int,
                  schirm_b: int, schirm_h: int) -> tuple[int, int]:
    """Ein Kasten, der nach einem Auflösungswechsel draußen läge, kommt herein."""
    x = min(max(int(x), 0), max(int(schirm_b) - int(breite), 0))
    y = min(max(int(y), 0), max(int(schirm_h) - int(hoehe), 0))
    return x, y


def kombination(text: str) -> tuple[int, int]:
    """„Strg+Umschalt+L“ -> (Modifikatoren, virtueller Tastencode).

    Ohne Strg, Alt oder Win keine Kombination: eine nackte Taste gehört dem
    Spiel.
    """
    teile = [t.strip().lower() for t in (text or "").split("+") if t.strip()]
    if len(teile) < 2:
        raise ValueError("braucht Strg, Alt oder Win und eine Taste")
    *mods, taste = teile
    maske = 0
    for m in mods:
        if m not in _MODS:
            raise ValueError(f"unbekannte Umschalttaste {m!r}")
        maske |= _MODS[m]
    if not maske & (MOD_CONTROL | MOD_ALT | MOD_WIN):
        raise ValueError("braucht Strg, Alt oder Win")
    if len(taste) == 1 and taste.isascii() and taste.isalnum():
        code = ord(taste.upper())
    elif taste[:1] == "f" and taste[1:].isdigit() and 1 <= int(taste[1:]) <= 24:
        code = 0x70 + int(taste[1:]) - 1
    else:
        raise ValueError(f"unbekannte Taste {taste!r}")
    return maske | MOD_NOREPEAT, code


def lade_einstellungen(pfad: Path | str | None) -> dict:
    """Was gemerkt ist, über den Vorgaben -- eine kaputte Datei stört nicht."""
    werte = json.loads(json.dumps(VORGABEN))
    if pfad is None:
        return werte
    try:
        roh = json.loads(Path(pfad).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return werte
    if not isinstance(roh, dict):
        return werte
    for k in ("x", "y", "breite"):
        if isinstance(roh.get(k), (int, float)) and not isinstance(roh.get(k), bool):
            werte[k] = int(roh[k])
    for k in ("eingeklappt", "sichtbar"):
        if isinstance(roh.get(k), bool):
            werte[k] = roh[k]
    if isinstance(roh.get("tasten"), dict):
        for name in werte["tasten"]:
            if isinstance(roh["tasten"].get(name), str):
                werte["tasten"][name] = roh["tasten"][name]
    werte["breite"] = max(BREITE_MIN, werte["breite"])
    return werte


def speichere_einstellungen(pfad: Path | str | None, werte: dict) -> None:
    if pfad is None:
        return
    pfad = Path(pfad)
    try:
        pfad.parent.mkdir(parents=True, exist_ok=True)
        zwischen = pfad.with_name(pfad.name + ".tmp")
        zwischen.write_text(json.dumps(werte, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(zwischen, pfad)
    except OSError as exc:
        log.warning("HUD-Einstellungen nicht gespeichert: %s", exc)


def tierbuchstabe(art: str, en: str | None) -> str:
    """Die Stufe der neuesten Quelle -- „S“, „A“ … oder „–“."""
    stufen = tierlisten.nachsehen(art, en) if en else []
    return stufen[0]["stufe"] if stufen else "–"


def kopfzeile(engpass: dict | None) -> tuple[str, str]:
    if not isinstance(engpass, dict) or not engpass.get("uhren"):
        return "Engpass: –", "unbekannt"
    return f"Engpass: {engpass.get('kurz') or '–'}", engpass.get("stufe") or "unbekannt"


def infozeile(zustand: dict | None) -> str:
    z = zustand if isinstance(zustand, dict) else {}
    if not z or z.get("verfuegbar") is False:
        return "Kein Spielstand"
    teile = []
    if z.get("jahr") is not None:
        teile.append(f"Jahr {z['jahr']}")
    if z.get("gespeichert"):
        teile.append(_alter(z["gespeichert"], "gespeichert"))
    return " · ".join(teile) or "Spielstand gelesen"


def auswahlzeile(zustand: dict | None, wissen: dict | None, auswahl: dict | None) -> str:
    """Gelesene Karten vor der Bauplanwahl aus dem Spielstand -- je mit Tier."""
    if isinstance(auswahl, dict) and auswahl.get("verfuegbar") and auswahl.get("angebot"):
        karten = [e for e in auswahl["angebot"] if e.get("belegt", True)] or auswahl["angebot"]
        teile = []
        for e in karten[:4]:
            art = {"effect": "grundstein", "building": "gebaeude"}.get(e.get("kind"),
                                                                        "grundstein")
            teile.append(f"{e.get('de') or e.get('en')} {tierbuchstabe(art, e.get('en'))}")
        return "Karten: " + " · ".join(teile)
    wahl = ((zustand or {}).get("bauplan_wahl") or {}) if isinstance(zustand, dict) else {}
    if not wahl.get("angebot"):
        return ""
    vergleich = {v.get("gebaeude"): v for v in ((wissen or {}).get("bauplan_vergleich") or [])
                 if isinstance(v, dict)}
    teile = []
    for name in wahl["angebot"][:4]:
        v = vergleich.get(name, {})
        text = f"{v.get('gebaeude_de') or name} {tierbuchstabe('gebaeude', name)}"
        if v.get("schon_freigeschaltet"):
            text += " (schon da)"
        elif v.get("besser_oder_neu"):
            text += f" ↑{v['besser_oder_neu']}"
        teile.append(text)
    return "Bauplan: " + " · ".join(teile)


# --------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------


def _unter_windows() -> bool:
    return sys.platform.startswith("win")


def _user32():
    """Eine eigene Bibliotheksinstanz mit festen Argumenttypen.

    Ohne `argtypes` reicht ctypes ein Fensterhandle als 32-Bit-Zahl weiter;
    ein Handle darüber gibt auf 64-Bit-Python einen `ArgumentError`. Eine
    eigene `WinDLL` statt `windll.user32`, damit die Typen nichts anderes im
    Prozess verändern.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                   wintypes.UINT, wintypes.UINT]
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM,
                                          wintypes.LPARAM]
    return user32


def windows_stil(fenster) -> bool:
    """Nicht in Alt-Tab, und ein Klick nimmt dem Spiel nicht den Fokus."""
    if not _unter_windows():
        return False
    try:
        user32 = _user32()
        fenster.update_idletasks()
        try:
            hwnd = int(fenster.wm_frame(), 16)
        except (_TK_FEHLER, ValueError, TypeError):
            hwnd = user32.GetParent(fenster.winfo_id()) or fenster.winfo_id()
        stil = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        stil = (stil | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE) & ~WS_EX_APPWINDOW
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, stil)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_STIL)
        return True
    except Exception:                                  # ein HUD mit Fokus ist besser als keins
        log.exception("Fensterstil nicht gesetzt")
        return False


class Tasten:
    """Tastenkombinationen über `RegisterHotKey`, in einem eigenen Faden.

    Der Faden fasst Tk nie an: jeder Treffer geht als (art, wert) an
    `melden`, das Fenster holt ihn aus seiner Warteschlange.
    """

    def __init__(self, kombis: dict[str, str], melden: Callable[[str, str], None]) -> None:
        self.kombis = dict(kombis)
        self.melden = melden
        self._faden_id: int | None = None

    def starten(self) -> bool:
        if not _unter_windows():
            return False
        threading.Thread(target=self._schleife, daemon=True, name="ats-tasten").start()
        return True

    def _schleife(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = _user32()
        self._faden_id = ctypes.windll.kernel32.GetCurrentThreadId()
        namen: dict[int, str] = {}
        for nummer, (name, text) in enumerate(self.kombis.items(), start=1):
            try:
                mods, code = kombination(text)
            except ValueError as exc:
                self.melden("tastenfehler", f"Tastenkombination „{text}“: {exc}.")
                continue
            if user32.RegisterHotKey(None, nummer, mods, code):
                namen[nummer] = name
            else:
                self.melden("tastenfehler",
                            f"„{text}“ ist schon vergeben – in hud.json eine andere eintragen.")
        nachricht = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(nachricht), None, 0, 0) > 0:
                if nachricht.message == WM_HOTKEY and nachricht.wParam in namen:
                    self.melden("taste", namen[nachricht.wParam])
        finally:
            for nummer in namen:
                user32.UnregisterHotKey(None, nummer)

    def stoppen(self) -> None:
        if self._faden_id and _unter_windows():
            _user32().PostThreadMessageW(self._faden_id, WM_QUIT, 0, 0)


# --------------------------------------------------------------------------
# Der Kasten
# --------------------------------------------------------------------------


def _ganz(wert, vorgabe: int) -> int:
    try:
        return int(wert)
    except (TypeError, ValueError):
        return vorgabe


class Hud:
    """Der Kasten selbst. Alles, was er zeigt, kommt über `zeigen`."""

    UHREN = ("nahrung", "ungeduld", "pestfaeule")

    def __init__(self, root, pfad: Path | str | None = None,
                 beim_lesen: Callable[[], None] | None = None,
                 beim_schliessen: Callable[[], None] | None = None) -> None:
        self.pfad = pfad
        self.werte = lade_einstellungen(pfad)
        self.beim_lesen = beim_lesen
        self.beim_schliessen = beim_schliessen
        self._daten: dict = {"zustand": None, "engpass": None, "wissen": None,
                             "auswahl": None, "rat": "", "hinweis": ""}
        self._zug: tuple[int, int] | None = None
        self._griff: tuple[int, int] | None = None
        self._texte: list[tuple[object, str]] = []     # (Widget, Gewicht) für die Schrift
        self._info_text = ""

        self.fenster = tk.Toplevel(root)
        self.fenster.overrideredirect(True)
        self.fenster.configure(background=GRUND)
        try:
            self.fenster.attributes("-topmost", True)
            self.fenster.attributes("-alpha", 0.9)
        except _TK_FEHLER:
            pass
        self._bauen()
        windows_stil(self.fenster)
        self._schrift_setzen()
        self._neu_zeichnen()
        if not self.werte["sichtbar"]:
            self.fenster.withdraw()

    # -- Aufbau ------------------------------------------------------------

    def _label(self, eltern, text="", farbe=TEXT, grund=GRUND, gewicht="normal", **kw):
        w = tk.Label(eltern, text=text, foreground=farbe, background=grund,
                     anchor="w", justify="left", **kw)
        self._texte.append((w, gewicht))
        return w

    def _knopf(self, eltern, text, befehl):
        w = self._label(eltern, text=text, grund=KOPF, gewicht="bold", padx=5, cursor="hand2")
        w.bind("<Button-1>", lambda e: befehl())
        return w

    def _bauen(self) -> None:
        f = self.fenster
        self.kopf = tk.Frame(f, background=KOPF)
        self.kopf.pack(fill="x")
        self.titel = self._label(self.kopf, "Engpass: –", grund=KOPF, gewicht="bold", padx=6)
        self.titel.pack(side="left", fill="x", expand=True)
        for text, befehl in (("×", self.schliessen), ("▁", self.umklappen),
                             ("+", lambda: self.groesse_aendern(BREITE_SCHRITT)),
                             ("−", lambda: self.groesse_aendern(-BREITE_SCHRITT))):
            self._knopf(self.kopf, text, befehl).pack(side="right")
        for w in (self.kopf, self.titel):
            w.bind("<ButtonPress-1>", self._zug_anfang)
            w.bind("<B1-Motion>", self._zug_weiter)
            w.bind("<ButtonRelease-1>", lambda e: self._merken())
            w.bind("<Double-Button-1>", lambda e: self.umklappen())

        self.koerper = tk.Frame(f, background=GRUND, padx=6, pady=4)
        self.info = self._label(self.koerper, "", farbe=LEISE)
        self.info.pack(fill="x")
        self.zeilen: dict[str, dict] = {}
        for art in self.UHREN:
            zeile = tk.Frame(self.koerper, background=GRUND)
            zeile.pack(fill="x", pady=1)
            name = self._label(zeile, "", width=9)
            name.pack(side="left")
            balken = tk.Frame(zeile, background="#33353d", height=8, width=90)
            balken.pack(side="left", padx=(0, 6))
            balken.pack_propagate(False)
            fuellung = tk.Frame(balken, background=FARBEN["unbekannt"])
            text = self._label(zeile, "")
            text.pack(side="left", fill="x", expand=True)
            self.zeilen[art] = {"name": name, "balken": balken, "fuellung": fuellung,
                                "text": text}
        self.auswahl = self._label(self.koerper, "", gewicht="bold")
        self.rat = self._label(self.koerper, "", farbe=LEISE)
        unten = tk.Frame(self.koerper, background=GRUND)
        unten.pack(fill="x", pady=(4, 0))
        self._unten = unten
        self.lesen = self._label(unten, "▶ Karten lesen", farbe=TEXT, grund=KOPF,
                                 padx=6, cursor="hand2")
        self.lesen.bind("<Button-1>", lambda e: self._lesen())
        self.lesen.pack(side="left")
        # `size_nw_se` kennt nur Windows; anderswo scheiterte daran der ganze Kasten.
        self.griff = self._label(unten, "◢", farbe=LEISE, cursor=(
            "size_nw_se" if _unter_windows() else "bottom_right_corner"))
        self.griff.pack(side="right")
        self.griff.bind("<ButtonPress-1>", self._griff_anfang)
        self.griff.bind("<B1-Motion>", self._griff_weiter)
        self.griff.bind("<ButtonRelease-1>", lambda e: self._merken())
        if not self.werte["eingeklappt"]:
            self.koerper.pack(fill="both", expand=True)

    # -- Anzeige -----------------------------------------------------------

    def zeigen(self, art: str, wert) -> None:
        """Jede Meldung des Fensters -- was das HUD nicht braucht, fällt durch."""
        if art in ("zustand", "engpass", "wissen"):
            self._daten[art] = wert if isinstance(wert, dict) else None
        elif art == "auswahl":
            # Eine neue Lesung ist eine neue Frage: der Satz zur alten gilt nicht.
            self._daten["auswahl"] = wert if isinstance(wert, dict) else None
            self._daten["rat"] = ""
            if isinstance(wert, dict) and wert.get("verfuegbar") is False:
                # Der erste Satz, nicht die ersten 120 Zeichen -- sonst endete
                # der Hinweis mitten im Wort.
                self._daten["hinweis"] = erster_satz(wert.get("grund") or "Keine Karten erkannt.",
                                                     140)
            else:
                self._daten["hinweis"] = ""
        elif art == "lesen":
            self._daten["hinweis"] = "Karten werden gelesen …"
        elif art == "rat_frage":
            self._daten["rat"] = "Rat wird gefragt …"
        elif art == "rat_leeren":
            self._daten["rat"] = ""
        elif art == "rat" and isinstance(wert, dict):
            text = wert.get("text") or ""
            self._daten["rat"] = ("Rat: " + erster_satz(text, 180) if wert.get("ok")
                                  else "Rat: " + erster_satz(text, 90) if text else "")
        elif art == "tastenfehler":
            self._daten["hinweis"] = erster_satz(str(wert), 160)
        else:
            return
        self._neu_zeichnen()

    def auffrischen(self) -> None:
        """Nur das Alter -- läuft mit dem Takt des Fensters, kostet fast nichts."""
        text = infozeile(self._daten["zustand"])
        if text != self._info_text:
            self._info_text = text
            self.info.configure(text=text)

    def _neu_zeichnen(self) -> None:
        titel, stufe = kopfzeile(self._daten["engpass"])
        self.titel.configure(text=titel, foreground=FARBEN.get(stufe, TEXT)
                             if stufe in ("rot", "gelb") else TEXT)
        self._info_text = infozeile(self._daten["zustand"])
        self.info.configure(text=self._info_text)
        uhren = {u.get("art"): u for u in ((self._daten["engpass"] or {}).get("uhren") or [])
                 if isinstance(u, dict)}
        for art, teile in self.zeilen.items():
            u = uhren.get(art) or {}
            farbe = FARBEN.get(u.get("stufe"), FARBEN["unbekannt"])
            teile["name"].configure(text=u.get("name") or art.capitalize())
            text = u.get("text") or "–"
            if u.get("zusatz"):
                text += f" · {u['zusatz']}"
            teile["text"].configure(text=text, foreground=farbe if u.get("stufe") in (
                "rot", "gelb") else TEXT)
            sekunden = u.get("sekunden")
            anteil = (min(max(sekunden / BALKEN_VOLL_SEKUNDEN, 0.03), 1.0)
                      if isinstance(sekunden, (int, float)) else 0.0)
            teile["fuellung"].configure(background=farbe)
            teile["fuellung"].place(relx=0, rely=0, relheight=1, relwidth=anteil)
        auswahl = auswahlzeile(self._daten["zustand"], self._daten["wissen"],
                               self._daten["auswahl"])
        rat = self._daten["rat"] if auswahl else ""
        if auswahl and self._daten["hinweis"]:
            rat = (rat + "  " if rat else "") + self._daten["hinweis"]
        # Eine leere Zeile nimmt trotzdem eine Zeile Platz -- also weg damit.
        # Beide neu einreihen, sonst stünde der Rat über der Auswahl, sobald
        # die Auswahl nach ihm wieder dazukommt.
        for widget in (self.auswahl, self.rat):
            widget.pack_forget()
        for widget, text in ((self.auswahl, auswahl or self._daten["hinweis"]),
                             (self.rat, rat)):
            widget.configure(text=text)
            if text:
                widget.pack(fill="x", before=self._unten)
        self._umbruch_setzen()
        self._groesse_anwenden()

    # -- Größe und Schrift -------------------------------------------------

    def _schrift_setzen(self) -> None:
        groesse = schriftgroesse(self.werte["breite"])
        for widget, gewicht in self._texte:
            try:
                widget.configure(font=(FAMILIE, groesse, gewicht))
            except _TK_FEHLER:
                pass
        for teile in self.zeilen.values():
            teile["balken"].configure(width=max(40, int(self.werte["breite"] * 0.2)),
                                      height=max(6, groesse - 2))
        self._umbruch_setzen()

    def _umbruch_setzen(self) -> None:
        """Umbrechen, wo der Platz endet -- nicht bei einer festen Breite.

        Das Foto unter xvfb zeigte „9,2 von 1“: der Umbruch lag hinter dem
        rechten Rand, weil Name und Balken davor mehr Platz nahmen als
        angenommen. Jetzt wird gemessen, was links schon steht.
        """
        breite = self.werte["breite"]
        self.fenster.update_idletasks()
        for teile in self.zeilen.values():
            links = (_ganz(teile["name"].winfo_reqwidth(), 80)
                     + _ganz(teile["balken"].winfo_reqwidth(), 60) + 6)
            teile["text"].configure(wraplength=max(60, breite - links - 20))
        for w in (self.auswahl, self.rat):
            w.configure(wraplength=max(60, breite - 16))

    def _schirm(self) -> tuple[int, int]:
        return (_ganz(self.fenster.winfo_screenwidth(), 1920),
                _ganz(self.fenster.winfo_screenheight(), 1080))

    def _hoehe(self) -> int:
        self.fenster.update_idletasks()
        teil = self.kopf if self.werte["eingeklappt"] else self.fenster
        return max(_ganz(teil.winfo_reqheight(), 120), 20)

    def _groesse_anwenden(self) -> None:
        schirm_b, schirm_h = self._schirm()
        breite = min(max(self.werte["breite"], BREITE_MIN), schirm_b)
        self.werte["breite"] = breite
        hoehe = self._hoehe()
        x, y = in_den_schirm(self.werte["x"], self.werte["y"], breite, hoehe,
                             schirm_b, schirm_h)
        self.werte["x"], self.werte["y"] = x, y
        self.fenster.geometry(f"{breite}x{hoehe}+{x}+{y}")

    def groesse_aendern(self, um: int) -> None:
        self.breite_setzen(self.werte["breite"] + um)
        self._merken()

    def breite_setzen(self, breite: int) -> None:
        self.werte["breite"] = min(max(int(breite), BREITE_MIN), self._schirm()[0])
        self._schrift_setzen()
        self._neu_zeichnen()

    # -- Ziehen ------------------------------------------------------------

    def _zug_anfang(self, ereignis) -> None:
        self._zug = (ereignis.x_root - self.werte["x"], ereignis.y_root - self.werte["y"])

    def _zug_weiter(self, ereignis) -> None:
        if self._zug is None:
            return
        schirm_b, schirm_h = self._schirm()
        x, y = in_den_schirm(ereignis.x_root - self._zug[0], ereignis.y_root - self._zug[1],
                             self.werte["breite"], self._hoehe(), schirm_b, schirm_h)
        self.werte["x"], self.werte["y"] = x, y
        self.fenster.geometry(f"+{x}+{y}")

    def _griff_anfang(self, ereignis) -> None:
        self._griff = (ereignis.x_root, self.werte["breite"])

    def _griff_weiter(self, ereignis) -> None:
        if self._griff is None:
            return
        start_x, start_breite = self._griff
        self.breite_setzen(start_breite + ereignis.x_root - start_x)

    # -- Zustände ----------------------------------------------------------

    @property
    def sichtbar(self) -> bool:
        return bool(self.werte["sichtbar"])

    def umklappen(self) -> None:
        self.werte["eingeklappt"] = not self.werte["eingeklappt"]
        if self.werte["eingeklappt"]:
            self.koerper.pack_forget()
        else:
            self.koerper.pack(fill="both", expand=True)
        self._neu_zeichnen()
        self._merken()

    def verstecken(self, vorlaeufig: bool = False) -> None:
        """Vorläufig: fürs Foto. Sonst gemerkt, bis es wieder eingeschaltet wird."""
        if not vorlaeufig:
            self.werte["sichtbar"] = False
            self._merken()
        self.fenster.withdraw()

    def einblenden(self, vorlaeufig: bool = False) -> None:
        if vorlaeufig:
            if not self.werte["sichtbar"]:          # vom Spieler ausgeschaltet: bleibt aus
                return
        else:
            self.werte["sichtbar"] = True
            self._merken()
        self.fenster.deiconify()
        try:
            self.fenster.attributes("-topmost", True)
        except _TK_FEHLER:
            pass
        windows_stil(self.fenster)
        self._neu_zeichnen()

    def umschalten(self) -> bool:
        if self.sichtbar:
            self.verstecken()
        else:
            self.einblenden()
        return self.sichtbar

    def schliessen(self) -> None:
        self.verstecken()
        if self.beim_schliessen:
            self.beim_schliessen()

    def _lesen(self) -> None:
        if self.beim_lesen:
            self.beim_lesen()

    def _merken(self) -> None:
        speichere_einstellungen(self.pfad, self.werte)
