"""Laufauswertung: was unterschied gewonnene von verlorenen Laeufen?

Zwei Quellen, die sich ergaenzen:

* `MetaSave.gamesHistory.records` -- das Spiel fuehrt selbst Buch ueber
  abgeschlossene Laeufe: Sieg oder Niederlage, Biom, Schwierigkeit, Jahre,
  Spielzeit, verwendete Gebaeude und Grundsteine. Das sind Endzustaende, keine
  Verlaeufe, aber es liegt ab dem ersten Tag vor.
* `runs/<run_id>.jsonl` -- die eigenen Mitschriften. Die haben den Verlauf und
  damit den Kipppunkt, brauchen aber erst gesammelte Laeufe.

Was aus wenigen Laeufen folgt, folgt nur schwach. Deshalb gibt jede Aussage
mit, auf wie vielen Laeufen sie beruht.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# Unter dieser Zahl von Laeufen je Seite ist ein Unterschied Rauschen.
MINDEST_LAEUFE = 3


@dataclass
class Merkmal:
    """Ein Merkmal, das in gewonnenen und verlorenen Laeufen verschieden haeufig ist."""

    name: str
    in_siegen: int
    in_niederlagen: int
    anteil_siege: float
    anteil_niederlagen: float

    @property
    def differenz(self) -> float:
        return self.anteil_siege - self.anteil_niederlagen


@dataclass
class Laufvergleich:
    laeufe: int
    siege: int
    niederlagen: int
    belastbar: bool
    hinweis: str | None
    jahre_sieg: float | None = None
    jahre_niederlage: float | None = None
    nach_biom: dict[str, dict[str, int]] = field(default_factory=dict)
    nach_schwierigkeit: dict[str, dict[str, int]] = field(default_factory=dict)
    grundsteine: list[Merkmal] = field(default_factory=list)
    gebaeude: list[Merkmal] = field(default_factory=list)


def _median(werte: list[float]) -> float | None:
    if not werte:
        return None
    s = sorted(werte)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _merkmale(siege: list[dict], niederlagen: list[dict], feld: str,
              mindestens: int = 2) -> list[Merkmal]:
    """Welche Eintraege im Feld kommen in Siegen anders oft vor als in Niederlagen?"""
    s_zaehler: Counter = Counter()
    n_zaehler: Counter = Counter()
    for lauf in siege:
        s_zaehler.update({x for x in lauf.get(feld) or [] if isinstance(x, str)})
    for lauf in niederlagen:
        n_zaehler.update({x for x in lauf.get(feld) or [] if isinstance(x, str)})

    out: list[Merkmal] = []
    for name in set(s_zaehler) | set(n_zaehler):
        in_s, in_n = s_zaehler[name], n_zaehler[name]
        if in_s + in_n < mindestens:
            continue
        out.append(Merkmal(
            name=name, in_siegen=in_s, in_niederlagen=in_n,
            anteil_siege=in_s / len(siege) if siege else 0.0,
            anteil_niederlagen=in_n / len(niederlagen) if niederlagen else 0.0,
        ))
    out.sort(key=lambda m: -abs(m.differenz))
    return out


def compare_runs(records: Iterable[dict], n: int | None = None) -> Laufvergleich:
    """Die letzten n abgeschlossenen Laeufe gegenueberstellen."""
    alle = [r for r in records if isinstance(r, dict)]
    alle.sort(key=lambda r: r.get("endTimestamp") or 0, reverse=True)
    if n:
        alle = alle[:n]

    siege = [r for r in alle if r.get("hasWon")]
    niederlagen = [r for r in alle if not r.get("hasWon")]

    belastbar = len(siege) >= MINDEST_LAEUFE and len(niederlagen) >= MINDEST_LAEUFE
    hinweis = None
    if not belastbar:
        knapp = "Siege" if len(siege) < MINDEST_LAEUFE else "Niederlagen"
        hinweis = (f"Nur {len(siege)} Siege und {len(niederlagen)} Niederlagen in dieser "
                   f"Auswahl -- zu wenige {knapp}, um Unterschiede von Zufall zu trennen.")

    nach_biom: dict[str, dict[str, int]] = {}
    nach_schwierigkeit: dict[str, dict[str, int]] = {}
    for lauf in alle:
        for schluessel, ziel in (("biome", nach_biom), ("difficulty", nach_schwierigkeit)):
            wert = lauf.get(schluessel)
            if not isinstance(wert, str):
                continue
            eintrag = ziel.setdefault(wert, {"siege": 0, "niederlagen": 0})
            eintrag["siege" if lauf.get("hasWon") else "niederlagen"] += 1

    return Laufvergleich(
        laeufe=len(alle), siege=len(siege), niederlagen=len(niederlagen),
        belastbar=belastbar, hinweis=hinweis,
        jahre_sieg=_median([float(r["years"]) for r in siege
                            if isinstance(r.get("years"), (int, float))]),
        jahre_niederlage=_median([float(r["years"]) for r in niederlagen
                                  if isinstance(r.get("years"), (int, float))]),
        nach_biom=nach_biom, nach_schwierigkeit=nach_schwierigkeit,
        grundsteine=_merkmale(siege, niederlagen, "cornerstones"),
        gebaeude=_merkmale(siege, niederlagen, "buildings"),
    )


def read_run_log(pfad: Path) -> list[dict]:
    """Eine Mitschrift lesen, kaputte Zeilen ueberspringen statt abzubrechen."""
    out: list[dict] = []
    if not Path(pfad).exists():
        return out
    for zeile in Path(pfad).read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            eintrag = json.loads(zeile)
        except json.JSONDecodeError:
            continue
        if isinstance(eintrag, dict):
            out.append(eintrag)
    return out


def tipping_point(zustaende: list[dict], vorlauf_sekunden: float = 120.0) -> dict | None:
    """Der Zustand `vorlauf_sekunden` Spielzeit vor dem letzten Eintrag.

    Die Spec fragt nach dem Zustand zwei Minuten vor dem Kipppunkt. Ohne
    Spieluhr im Eintrag ist die Frage nicht zu beantworten -- dann kommt None
    zurueck statt eines geratenen Werts.
    """
    mit_uhr = [z for z in zustaende if isinstance(z.get("game_time"), (int, float))]
    if len(mit_uhr) < 2:
        return None
    mit_uhr.sort(key=lambda z: z["game_time"])
    ende = mit_uhr[-1]["game_time"]
    ziel = ende - vorlauf_sekunden
    passend = [z for z in mit_uhr if z["game_time"] <= ziel]
    if not passend:
        return None
    treffer = passend[-1]
    return {**treffer, "_abstand_zum_ende": round(ende - treffer["game_time"], 1)}


def summarise(vergleich: Laufvergleich, top: int = 5) -> str:
    """Kurzfassung in Prosa -- das, was der Assistent zeigt."""
    L = [f"{vergleich.laeufe} Läufe: {vergleich.siege} gewonnen, "
         f"{vergleich.niederlagen} verloren."]
    if vergleich.hinweis:
        L.append(vergleich.hinweis)
    if vergleich.jahre_sieg is not None and vergleich.jahre_niederlage is not None:
        L.append(f"Dauer im Mittel: {vergleich.jahre_sieg:.0f} Jahre bei Sieg, "
                 f"{vergleich.jahre_niederlage:.0f} bei Niederlage.")
    for titel, merkmale in (("Grundsteine", vergleich.grundsteine),
                            ("Gebäude", vergleich.gebaeude)):
        auffaellig = [m for m in merkmale if abs(m.differenz) >= 0.25][:top]
        if not auffaellig:
            continue
        L.append(f"{titel} mit dem größten Unterschied:")
        for m in auffaellig:
            richtung = "häufiger bei Siegen" if m.differenz > 0 else "häufiger bei Niederlagen"
            L.append(f"  {m.name}: {m.in_siegen}/{vergleich.siege} gegen "
                     f"{m.in_niederlagen}/{vergleich.niederlagen} -- {richtung}")
    if not vergleich.belastbar:
        L.append("Diese Gegenüberstellung ist ein Hinweis, kein Befund.")
    return "\n".join(L)
