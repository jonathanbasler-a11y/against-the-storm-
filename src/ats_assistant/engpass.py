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


def _nahrung(nahrung: dict, statistik: dict, vorher: dict | None,
             verlauf: list[float] | None = None) -> dict:
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
    if s in ("gelb", "rot") and verlauf and len(verlauf) >= 3 and verlauf[-1] >= verlauf[0]:
        # Die Uhr rechnet über die letzten fünf Minuten, und Sammler liefern
        # in Schüben -- in P17 sprang sie zwischen „6 min“, „wächst“ und
        # „90 min“. Hat sich der Vorrat über drei Speicherstände (rund eine
        # Viertelstunde) gehalten, ist die kurze Reichweite Schwankung, kein
        # Absturz: eine Stufe weniger. Wunsch des Spielers: nicht so binär.
        s = "gelb" if s == "rot" else "ruhig"
        zusatz.insert(0, "über 15 min stabil")
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


# Gemessen am 27.09.2026 an der Spielhistorie des Spielers: 15 Siege, alle
# nach 9 bis 13 Jahren, im Median 11. Die Community nennt auf hohem Prestige
# 6 bis 8 Jahre üblich (Steam-Diskussionen, gefunden per Suche). Sieben Jahre
# sind deshalb das Ziel, gegen das das Tempo gemessen wird.
ZIEL_JAHRE = 7
# Vor Jahr 4 kein Urteil: am 28.09.2026 stand in Jahr 3 bei Ruf 2 „Sieg etwa
# Jahr 25“ in Rot, und der Rat drängte deshalb zum Markt. Aus zwei Jahren
# Aufbau lässt sich kein Tempo für elf hochrechnen.
FRUEH_JAHRE = 3


def ruf_tempo(ruf, ziel, jahr, jahreszeit, ziel_jahre: int = ZIEL_JAHRE) -> dict | None:
    """Wie schnell der Ruf wächst -- und ob das für einen Sieg in `ziel_jahre` reicht.

    Die vergangene Zeit ist `(Jahr - 1) + Jahreszeit / 3`: die Jahreszeiten
    sind nicht gleich lang, also ist das Tempo eine Näherung -- genau genug,
    um zu sehen, ob ein Lauf auf sieben oder auf elf Jahre zuläuft.
    """
    ruf, ziel, jahr = _zahl(ruf), _zahl(ziel), _zahl(jahr)
    if ruf is None or not ziel or jahr is None:
        return None
    zeit = _zahl(jahreszeit)
    vergangen = (jahr - 1) + (min(max(zeit, 0.0), 2.0) / 3 if zeit is not None else 0.0)
    stand = f"{ruf:.1f} von {ziel:g}".replace(".", ",")
    out: dict[str, Any] = {"ruf": ruf, "ziel": ziel, "jahre_vergangen": round(vergangen, 2)}
    if ruf >= ziel:
        return {**out, "text": f"{stand} – voll", "stufe": "ruhig", "zusatz": ""}
    if vergangen < 1:
        return {**out, "text": stand, "stufe": "unbekannt", "zusatz": "Tempo ab Jahr 2"}
    tempo = ruf / vergangen
    if vergangen < FRUEH_JAHRE:
        return {**out, "tempo_je_jahr": round(tempo, 2),
                "text": f"{stand} · {tempo:.1f}/Jahr".replace(".", ","),
                "stufe": "unbekannt", "zusatz": f"Urteil ab Jahr {FRUEH_JAHRE + 1}"}
    rest = ziel - ruf
    noetig = rest / (ziel_jahre - vergangen) if vergangen < ziel_jahre - 0.5 else None
    sieg_jahr = int(vergangen + rest / tempo) + 1 if tempo > 0 else None
    if noetig is None:
        s = "rot"
    elif tempo >= noetig:
        s = "ruhig"
    else:
        s = "gelb" if tempo >= 0.75 * noetig else "rot"
    text = f"{stand} · {tempo:.1f}/Jahr".replace(".", ",")
    text += f" → Sieg etwa Jahr {sieg_jahr}" if sieg_jahr else " → kein Zuwachs"
    zusatz = (f"für Jahr {ziel_jahre}: {noetig:.1f}/Jahr".replace(".", ",")
              if noetig is not None else f"Jahr {ziel_jahre} ist vorbei")
    return {**out, "tempo_je_jahr": round(tempo, 2), "noetig_je_jahr": (
        round(noetig, 2) if noetig is not None else None), "sieg_etwa_jahr": sieg_jahr,
        "ziel_jahre": ziel_jahre, "text": text, "stufe": s, "zusatz": zusatz}


def uhren(nahrung: dict | None, ungeduld: dict | None, statistik: dict | None = None,
          statistik_vorher: dict | None = None, pestfaeule: dict | None = None,
          nahrung_verlauf: list[float] | None = None) -> dict:
    """Die drei Uhren und welche davon entscheidet.

    Entscheidend ist die dringendste Uhr, die gelb oder rot steht: rot vor
    gelb, bei gleicher Stufe die kürzere Zeit. Steht keine so, ist nichts akut.
    """
    statistik = statistik if isinstance(statistik, dict) else {}
    vorher = statistik_vorher if isinstance(statistik_vorher, dict) else None
    liste = [
        _nahrung(nahrung if isinstance(nahrung, dict) else {}, statistik, vorher,
                 [v for v in (nahrung_verlauf or []) if _zahl(v) is not None]),
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


def mit_ruf(engpass: dict, ruf: dict | None) -> dict:
    """Das Ruf-Tempo daneben -- und bei vollem Ruf ist der Lauf gewonnen.

    Gesehen am 28.09.2026 (P17 gewonnen): Ruf 18 von 18, und das HUD stand
    rot „Ungeduld voll in 5 min“. Mit dem Sieg entscheidet keine Uhr mehr.
    """
    if not isinstance(ruf, dict):
        return engpass
    out = {**engpass, "ruf": ruf}
    wert, ziel = _zahl(ruf.get("ruf")), _zahl(ruf.get("ziel"))
    if wert is None or not ziel or wert < ziel:
        return out
    out["uhren"] = [{**u, "stufe": "ruhig", "zusatz": "Ruf voll – zählt nicht mehr"}
                    if isinstance(u, dict) and u.get("stufe") in ("gelb", "rot") else u
                    for u in (engpass.get("uhren") or [])]
    out.update(entscheidend=None, stufe="ruhig", kurz="Ruf voll – gewonnen", gewonnen=True)
    return out
