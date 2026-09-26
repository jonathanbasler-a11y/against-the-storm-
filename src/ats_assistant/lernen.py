"""Lernen von Lauf zu Lauf -- und aus dem, was der Spieler korrigiert.

Wunsch vom Spielrechner (23.09.2026): "wir sollten auch von Run zu Run
lernen und besser werden und verstehen, woran wir gescheitert sind."

Drei Quellen, alle lokal:

- **Laufberichte** aus den eigenen Mitschriften: wann die Nahrung knapp
  wurde, wie hoch die Ungeduld stieg, wie viel Ruf nach Jahr 1 und 2 da war,
  was der Rat empfohlen hat. Den Ausgang kennt der Spielstand nur bei Sieg
  oder Niederlage durch Ungeduld; sonst hilft die Spielhistorie aus
  MetaSave -- zugeordnet ueber Biom und Jahre, und nur, wenn eindeutig.
- **Lehren**: die Berichte der Niederlagen gegen die der Siege. Unter drei
  Laeufen je Seite ist das ein Hinweis, kein Befund.
- **Korrekturen**: was der Spieler dem Rat widersprochen hat ("Pakete kann
  man nicht oeffnen"). Sie gehen bei jeder Frage mit und gelten vor dem
  Gedaechtnis des Modells.

Was hier abgelegt wird, liegt unter `runs/wissen/` -- nicht direkt in
`runs/`, dort ist jede .jsonl eine Mitschrift.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from . import analysis, forecast, save_reader

log = logging.getLogger(__name__)

# Unter zwei Minuten Reichweite im ersten Jahr: so sah es am Spielrechner aus
# (103 Spielzeitsekunden), bevor jemand gegensteuerte.
KNAPP_SEKUNDEN = 120.0
LEHREN_HOECHSTENS = 5
# Aendert sich, was ein Bericht enthaelt, wird der Zwischenspeicher neu
# gerechnet -- sonst fehlten den alten Berichten die neuen Felder.
BERICHT_FASSUNG = 2


def wissensordner(runs_dir: Path | str) -> Path:
    return Path(runs_dir) / "wissen"


# --------------------------------------------------------------------------
# Laufbericht
# --------------------------------------------------------------------------


def _zahl(wert: Any) -> float | None:
    if isinstance(wert, (int, float)) and not isinstance(wert, bool):
        return float(wert)
    return None


def _ausgang(zustaende: list[dict]) -> str:
    for z in reversed(zustaende):
        if z.get("won") is True:
            return "gewonnen"
        if z.get("lost") is True:
            return "verloren"
        ruf, ziel = _zahl(z.get("reputation")), _zahl(z.get("reputation_to_win"))
        if ruf is not None and ziel and ruf >= ziel:
            return "gewonnen"
        ung, grenze = _zahl(z.get("impatience")), _zahl(z.get("impatience_to_lose"))
        if ung is not None and grenze and ung >= grenze:
            return "verloren"
    return "offen"


def laufbericht(zustaende: list[dict], kennung: str,
                notizen: list[dict] | None = None) -> dict:
    """Was eine Mitschrift ueber ihre Siedlung erzaehlt."""
    zustaende = sorted((z for z in zustaende if _zahl(z.get("game_time")) is not None),
                       key=lambda z: z["game_time"])
    bericht: dict[str, Any] = {"kennung": kennung, "zustaende": len(zustaende)}
    if not zustaende:
        bericht["ausgang"] = "offen"
        return bericht
    letzter = zustaende[-1]
    bericht.update({
        "biom": letzter.get("biome"),
        "prestige": letzter.get("prestige"),
        "jahre": max((z.get("year") or 0) for z in zustaende) or None,
        "spielzeit_ende": letzter["game_time"],
        "ausgang": _ausgang(zustaende),
        "ungeduld_max": max((_zahl(z.get("impatience")) or 0.0) for z in zustaende),
    })

    ruf: dict[str, float] = {}
    gebaeude: dict[str, int] = {}
    for z in zustaende:
        jahr = z.get("year")
        if jahr is None:
            continue
        if _zahl(z.get("reputation")) is not None:
            ruf[str(jahr)] = round(float(z["reputation"]), 2)
        gebaeude[str(jahr)] = len(z.get("buildings") or [])
    bericht["ruf_nach_jahr"] = ruf
    bericht["gebaeude_nach_jahr"] = gebaeude
    bericht["auftraege_erledigt"] = sum(
        1 for o in letzter.get("orders") or [] if isinstance(o, dict) and o.get("completed"))

    # Nahrung: je zwei aufeinanderfolgende Staende eine Reichweite, dieselbe
    # Rechnung wie im Fenster.
    tiefster = None
    knapp_ab = None
    knapp_jahr1 = False
    for vorher, jetzt in zip(zustaende, zustaende[1:]):
        f = forecast.food_forecast(
            SimpleNamespace(category_trends=jetzt.get("category_trends") or {},
                            game_time=jetzt["game_time"]),
            SimpleNamespace(category_trends=vorher.get("category_trends") or {},
                            game_time=vorher["game_time"]))
        if f.runway_seconds is None:
            continue
        if tiefster is None or f.runway_seconds < tiefster["sekunden"]:
            tiefster = {"sekunden": round(f.runway_seconds, 1),
                        "spielzeit": jetzt["game_time"], "jahr": jetzt.get("year")}
        if f.runway_seconds < KNAPP_SEKUNDEN:
            knapp_ab = knapp_ab if knapp_ab is not None else jetzt["game_time"]
            if jetzt.get("year") == 1:
                knapp_jahr1 = True
    bericht["nahrung_min_reichweite"] = tiefster
    bericht["nahrung_knapp_ab"] = knapp_ab
    bericht["nahrung_knapp_jahr1"] = knapp_jahr1

    kipp = analysis.tipping_point(zustaende)
    if kipp:
        bericht["kipppunkt"] = {k: kipp.get(k) for k in
                                ("game_time", "year", "reputation", "impatience",
                                 "_abstand_zum_ende")}
    bericht["empfehlungen"] = [
        {"spielzeit": n.get("spielzeit"), "jahr": n.get("jahr"), "text": n.get("text")}
        for n in notizen or [] if n.get("art") == "rat" and n.get("text")]

    # Aus `stats` (gemessen am 23.09.2026): Summen seit Siedlungsbeginn, also
    # zaehlt der letzte Stand -- in Jahr 1 der letzte Stand von Jahr 1.
    mit_statistik = [z for z in zustaende if isinstance(z.get("stats"), dict) and z["stats"]]
    if mit_statistik:
        statistik = mit_statistik[-1]["stats"]
        for feld in ("hunger", "tot", "gegangen"):
            if _zahl(statistik.get(feld)) is not None:
                bericht[feld] = statistik[feld]
        jahr1 = [z["stats"].get("hunger") for z in mit_statistik
                 if z.get("year") == 1 and _zahl(z["stats"].get("hunger")) is not None]
        if jahr1:
            bericht["hunger_jahr1"] = max(jahr1)
    bericht["ungeduld_ende"] = _zahl(letzter.get("impatience"))
    bericht["ungeduld_schwelle"] = _zahl(letzter.get("impatience_to_lose"))
    bericht["ursache"] = ursache(bericht)
    return bericht


def ursache(bericht: dict) -> str | None:
    """Woran ein verlorener Lauf gescheitert ist -- eine Regel ueber
    gemessene Felder, keine Deutung. Nur bei `verloren`."""
    if bericht.get("ausgang") != "verloren":
        return None
    ende, schwelle = bericht.get("ungeduld_ende"), bericht.get("ungeduld_schwelle")
    if ende is not None and schwelle and ende >= schwelle:
        return "Ungeduld"
    if (bericht.get("hunger") or 0) > 0 or (bericht.get("gegangen") or 0) > 0:
        return "Hunger/Abwanderung"
    return "unklar"


# --------------------------------------------------------------------------
# Alle Berichte, mit Zwischenspeicher
# --------------------------------------------------------------------------


def _aus_historie(bericht: dict, historie: list[dict]) -> str | None:
    """Den Ausgang aus MetaSave.gamesHistory -- nur bei eindeutiger Zuordnung."""
    jahre = bericht.get("jahre")
    if not jahre or not bericht.get("biom"):
        return None
    passend = [r for r in historie
               if isinstance(r, dict) and r.get("biome") == bericht["biom"]
               and r.get("years") in (jahre, jahre + 1)
               and isinstance(r.get("hasWon"), bool)]
    if len(passend) != 1:
        return None
    return "gewonnen" if passend[0]["hasWon"] else "verloren"


def berichte(runs_dir: Path | str, historie: list[dict] | None = None) -> list[dict]:
    """Ein Bericht je Mitschrift, aelteste zuerst.

    Mitschriften sind gross (ein Zustand gut 200 kB). Berichte werden deshalb
    je Datei nach Groesse und Aenderungszeit zwischengespeichert.
    """
    runs = Path(runs_dir)
    if not runs.is_dir():
        return []
    speicher_pfad = wissensordner(runs) / "berichte.json"
    try:
        speicher = json.loads(speicher_pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        speicher = {}
    neu: dict[str, Any] = {}
    out = []
    for datei in sorted(runs.glob("*.jsonl"), key=lambda p: p.stat().st_mtime):
        st = datei.stat()
        marke = [st.st_size, st.st_mtime_ns]
        alt = speicher.get(datei.name)
        if (isinstance(alt, dict) and alt.get("marke") == marke
                and alt.get("fassung") == BERICHT_FASSUNG):
            bericht = alt["bericht"]
        else:
            eintraege = analysis.read_run_log(datei)
            zustaende = [save_reader.zustand_bereinigen(e) for e in eintraege
                         if e.get("typ") != "notiz"]
            notizen = [e for e in eintraege if e.get("typ") == "notiz"]
            bericht = laufbericht(zustaende, datei.stem, notizen)
        neu[datei.name] = {"marke": marke, "fassung": BERICHT_FASSUNG, "bericht": bericht}
        bericht = dict(bericht)
        if bericht.get("ausgang") == "offen" and historie:
            aus_historie = _aus_historie(bericht, historie)
            if aus_historie:
                bericht["ausgang"] = aus_historie
                bericht["ausgang_quelle"] = "Spielhistorie"
                bericht["ursache"] = ursache(bericht)
        out.append(bericht)
    try:
        speicher_pfad.parent.mkdir(parents=True, exist_ok=True)
        # Erst daneben schreiben, dann ersetzen: Lage und Rat rufen das aus
        # zwei Faeden, und ein halb geschriebener Speicher waere verloren.
        zwischen = speicher_pfad.with_name(
            f"{speicher_pfad.name}.{threading.get_ident()}.tmp")
        zwischen.write_text(json.dumps(neu, ensure_ascii=False), encoding="utf-8")
        os.replace(zwischen, speicher_pfad)
    except OSError as exc:
        log.warning("Berichte nicht zwischengespeichert: %s", exc)
    return out


# --------------------------------------------------------------------------
# Lehren
# --------------------------------------------------------------------------


def lehren(berichte_: list[dict]) -> list[str]:
    """Was Niederlagen von Siegen unterscheidet -- hoechstens fuenf Saetze."""
    siege = [b for b in berichte_ if b.get("ausgang") == "gewonnen"]
    niederlagen = [b for b in berichte_ if b.get("ausgang") == "verloren"]
    if not siege and not niederlagen:
        return ["Noch kein abgeschlossener Lauf mitgeschrieben – Lehren folgen."]
    vorbehalt = ("Hinweis, kein Befund: "
                 if min(len(siege), len(niederlagen)) < analysis.MINDEST_LAEUFE else "")
    saetze: list[str] = []

    def anteil(gruppe: list[dict], feld: str) -> int:
        return sum(1 for b in gruppe if b.get(feld) is True)

    if siege and niederlagen:
        n_k, s_k = anteil(niederlagen, "nahrung_knapp_jahr1"), anteil(siege, "nahrung_knapp_jahr1")
        if abs(n_k / len(niederlagen) - s_k / len(siege)) >= 0.34:
            saetze.append(
                f"In {n_k} von {len(niederlagen)} Niederlagen fiel die Nahrung in Jahr 1 "
                f"unter {KNAPP_SEKUNDEN / 60:.0f} Minuten, in {s_k} von {len(siege)} Siegen.")

        def median(gruppe: list[dict], wert) -> float | None:
            return analysis._median([v for v in (wert(b) for b in gruppe) if v is not None])

        # Hunger und Abwanderung zuerst: das ist das Kernproblem, und es sind
        # hoechstens fuenf Saetze.
        for titel, wert, einheit in (
                ("Hungerereignisse", lambda b: _zahl(b.get("hunger")), ""),
                ("Gegangene Bewohner", lambda b: _zahl(b.get("gegangen")), ""),
                ("Ruf nach Jahr 1", lambda b: _zahl((b.get("ruf_nach_jahr") or {}).get("1")), ""),
                ("Gebäude nach Jahr 1",
                 lambda b: _zahl((b.get("gebaeude_nach_jahr") or {}).get("1")), ""),
                ("Höchste Ungeduld", lambda b: _zahl(b.get("ungeduld_max")), ""),
                ("Erledigte Aufträge", lambda b: _zahl(b.get("auftraege_erledigt")), "")):
            n_m, s_m = median(niederlagen, wert), median(siege, wert)
            if n_m is None or s_m is None:
                continue
            groesser = max(abs(n_m), abs(s_m))
            if groesser and abs(n_m - s_m) / groesser >= 0.2:
                saetze.append(f"{titel}: im Mittel {n_m:.1f}{einheit} bei Niederlagen, "
                              f"{s_m:.1f}{einheit} bei Siegen.")
    else:
        fehlt = "gewonnener" if not siege else "verlorener"
        saetze.append(f"Noch kein {fehlt} Lauf mitgeschrieben – der Vergleich fehlt.")

    return [vorbehalt + s for s in saetze[:LEHREN_HOECHSTENS]]


# --------------------------------------------------------------------------
# Korrekturen
# --------------------------------------------------------------------------


def korrektur_merken(pfad: Path | str, aussage: str, korrektur: str) -> dict:
    """Was der Spieler dem Rat widersprochen hat -- eine Zeile je Korrektur."""
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    eintrag = {"zeitpunkt": datetime.now(timezone.utc).isoformat(),
               "aussage": (aussage or "")[:300], "korrektur": korrektur.strip()}
    with pfad.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    return eintrag


def korrekturen(pfad: Path | str, hoechstens: int = 30) -> list[str]:
    """Die Korrekturen, neueste zuerst, jede einmal."""
    try:
        # Nur an "\n" trennen -- siehe `analysis.read_run_log`.
        zeilen = Path(pfad).read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError:
        return []
    out: list[str] = []
    for zeile in reversed(zeilen):
        try:
            text = (json.loads(zeile).get("korrektur") or "").strip()
        except (ValueError, AttributeError):
            continue
        if text and text not in out:
            out.append(text)
        if len(out) >= hoechstens:
            break
    return out
