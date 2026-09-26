"""Was gerade entscheidet: Nahrung, Ungeduld oder Pestfäule.

Wunsch vom Spielrechner (26.09.2026): auf einen Blick sehen, welche der
Gefahren zuerst zuschlägt. Drei Uhren, jede aus dem, was schon gerechnet
wird -- nichts Neues geraten:

* **Nahrung**: `food_forecast.reichweite_sekunden`, bis das Lager leer ist.
* **Ungeduld**: `impatience_forecast.sekunden_bis_verlust`.
* **Pestfäule**: gemessen ist bisher nur, wie viele Zysten entstanden,
  entfernt und verbrannt sind (`stats`). Wie schnell der Herd verseucht, ist
  nicht gemessen -- also steht dort keine Zeit, und es wird keine erfunden.

Regel des Spielers: Hunger allein ist kein Alarm, erst wenn Leute gehen.
Hunger und Abgänge seit dem letzten Speichern heben deshalb die Stufe der
Nahrung, Hunger allein nicht.

Reine Rechnung ohne Fenster und ohne Import aus dem Fenster -- das HUD und der
Rat lesen dasselbe Ergebnis.
"""

from __future__ import annotations

import math
from typing import Any

from .forecast import SAVE_INTERVAL_SECONDS

# Rot: kürzer als ein Speicherintervall -- bis das Spiel wieder schreibt, kann
# es vorbei sein. Gelb: drei Speicherintervalle, eine Viertelstunde Spielzeit.
ROT_SEKUNDEN = SAVE_INTERVAL_SECONDS
GELB_SEKUNDEN = 900.0

STUFEN = ("unbekannt", "ruhig", "gelb", "rot")
NAMEN = {"nahrung": "Nahrung", "ungeduld": "Ungeduld", "pestfaeule": "Pestfäule"}


def _zahl(wert: Any) -> float | None:
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        return None
    return float(wert) if math.isfinite(wert) else None


def dauer(sekunden: float | None) -> str:
    """Spielzeit lesbar -- dieselbe Form wie `rechner.minuten`."""
    if sekunden is None:
        return "–"
    if sekunden < 60:
        return f"{sekunden:.0f} s"
    return f"{sekunden / 60:.0f} min"


def stufe(sekunden: float | None) -> str:
    if sekunden is None:
        return "unbekannt"
    if sekunden < ROT_SEKUNDEN:
        return "rot"
    return "gelb" if sekunden < GELB_SEKUNDEN else "ruhig"


def _hoeher(s: str) -> str:
    return {"unbekannt": "gelb", "ruhig": "gelb", "gelb": "rot"}.get(s, "rot")


def _seit(jetzt: dict, vorher: dict | None, schluessel: str) -> float | None:
    """Wie viel seit dem letzten Speichern dazugekommen ist -- None ohne Vorgänger."""
    a, b = _zahl(jetzt.get(schluessel)), _zahl((vorher or {}).get(schluessel))
    if a is None or b is None or vorher is None:
        return None
    return max(a - b, 0.0)


def _nahrung(nahrung: dict, statistik: dict, vorher: dict | None) -> dict:
    sekunden = _zahl(nahrung.get("reichweite_sekunden"))
    rate = _zahl(nahrung.get("rate_je_spielzeitsekunde"))
    if sekunden is not None:
        text, s = f"leer in {dauer(sekunden)}", stufe(sekunden)
    elif rate is not None and rate > 0:
        text, s = "wächst", "ruhig"
    elif rate is not None and rate == 0:
        text, s = "hält sich", "ruhig"
    else:
        text, s = "nicht gerechnet", "unbekannt"

    zusatz = []
    hunger, gegangen = _zahl(statistik.get("hunger")), _zahl(statistik.get("gegangen"))
    hunger_neu = _seit(statistik, vorher, "hunger")
    gegangen_neu = _seit(statistik, vorher, "gegangen")
    if hunger:
        zusatz.append(f"Hunger {hunger:.0f}×" + (f" (+{hunger_neu:.0f})" if hunger_neu else ""))
    if gegangen:
        zusatz.append(f"{gegangen:.0f} gegangen" + (f" (+{gegangen_neu:.0f})" if gegangen_neu else ""))
    if hunger_neu and gegangen_neu:
        # Beides seit dem letzten Speichern: jetzt kostet der Hunger Leute.
        s = _hoeher(s)
    return {"art": "nahrung", "sekunden": sekunden, "text": text, "stufe": s,
            "zusatz": " · ".join(zusatz)}


def _ungeduld(ungeduld: dict) -> dict:
    sekunden = _zahl(ungeduld.get("sekunden_bis_verlust"))
    je_sekunde = _zahl(ungeduld.get("je_spielzeitsekunde"))
    jetzt, schwelle = _zahl(ungeduld.get("jetzt")), _zahl(ungeduld.get("schwelle"))
    if ungeduld.get("warnung") == "Verlustschwelle erreicht":
        sekunden = 0.0
    if sekunden is not None:
        text, s = f"voll in {dauer(sekunden)}", stufe(sekunden)
    elif je_sekunde is not None and je_sekunde <= 0:
        text, s = "sinkt", "ruhig"
    else:
        text, s = "nicht gerechnet", "unbekannt"
    zusatz = (f"{jetzt:.1f} von {schwelle:g}".replace(".", ",")
              if jetzt is not None and schwelle is not None else "")
    return {"art": "ungeduld", "sekunden": sekunden, "text": text, "stufe": s,
            "zusatz": zusatz}


def _pestfaeule(statistik: dict, vorher: dict | None, gemessen: dict | None) -> dict:
    if gemessen and _zahl(gemessen.get("sekunden")) is not None:
        # Erst nach der Messung am Spielrechner: Zeit bis der Herd verseucht.
        sekunden = _zahl(gemessen["sekunden"])
        return {"art": "pestfaeule", "sekunden": sekunden,
                "text": f"Herd verseucht in {dauer(sekunden)}", "stufe": stufe(sekunden),
                "zusatz": str(gemessen.get("zusatz") or "")}
    zysten = statistik.get("zysten") if isinstance(statistik.get("zysten"), dict) else {}
    # Knapp, weil es im HUD in eine Zeile passen soll: „Zysten 6, verbrannt 4“.
    teile = [f"{wort} {_zahl(zysten[k]):.0f}" for k, wort in (
        ("entstanden", "Zysten"), ("verbrannt", "verbrannt"), ("entfernt", "entfernt"))
        if _zahl(zysten.get(k)) is not None]
    if not teile:
        return {"art": "pestfaeule", "sekunden": None, "text": "keine Zysten gezählt",
                "stufe": "unbekannt", "zusatz": ""}
    neu = _seit(zysten, (vorher or {}).get("zysten") if vorher else None, "entstanden")
    text = ", ".join(teile) + (f" (+{neu:.0f} neu)" if neu else "")
    return {"art": "pestfaeule", "sekunden": None, "text": text, "stufe": "unbekannt",
            "zusatz": "keine Zeit gemessen"}


def uhren(nahrung: dict | None, ungeduld: dict | None, statistik: dict | None = None,
          statistik_vorher: dict | None = None, pestfaeule: dict | None = None) -> dict:
    """Die drei Uhren und welche davon entscheidet.

    Entscheidend ist die dringendste Uhr, die gelb oder rot steht: rot vor
    gelb, bei gleicher Stufe die kürzere Zeit. Steht keine so, ist nichts akut.
    """
    statistik = statistik if isinstance(statistik, dict) else {}
    vorher = statistik_vorher if isinstance(statistik_vorher, dict) else None
    liste = [
        _nahrung(nahrung if isinstance(nahrung, dict) else {}, statistik, vorher),
        _ungeduld(ungeduld if isinstance(ungeduld, dict) else {}),
        _pestfaeule(statistik, vorher, pestfaeule if isinstance(pestfaeule, dict) else None),
    ]
    for u in liste:
        u["name"] = NAMEN[u["art"]]
    akut = [u for u in liste if u["stufe"] in ("gelb", "rot")]
    akut.sort(key=lambda u: (-STUFEN.index(u["stufe"]),
                             u["sekunden"] if u["sekunden"] is not None else math.inf))
    entscheidend = akut[0] if akut else None
    if entscheidend is None:
        kurz = "nichts akut" if any(u["stufe"] == "ruhig" for u in liste) else "–"
    elif entscheidend["sekunden"] is not None:
        kurz = f"{entscheidend['name']} {dauer(entscheidend['sekunden'])}"
    else:
        kurz = entscheidend["name"]
    return {"uhren": liste, "entscheidend": entscheidend["art"] if entscheidend else None,
            "stufe": entscheidend["stufe"] if entscheidend else (
                "ruhig" if kurz == "nichts akut" else "unbekannt"),
            "kurz": kurz}
