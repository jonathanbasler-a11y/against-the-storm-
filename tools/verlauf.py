#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Verlauf eines Laufs aus seiner Mitschrift -- eine Zeile je Speicherstand.

    python tools\\verlauf.py                  der zuletzt geschriebene Lauf
    python tools\\verlauf.py --liste          alle Mitschriften
    python tools\\verlauf.py --lauf <Name>    ein bestimmter Lauf

Gebaut nach einer Niederlage an der Nahrung (P17, 27.09.2026): Wann kippte
die Reichweite, wann kam Hunger, wann gingen Leute? Nur lesen, nichts ändern.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ats_assistant import analysis, biome, forecast, lernen, save_reader, tools_api  # noqa: E402
from ats_assistant.mcp_server import aufloesen  # noqa: E402


def _zahl(wert, muster: str = "{:.1f}") -> str:
    """Formatiert -- und hält die Spaltenbreite auch ohne Wert."""
    if isinstance(wert, (int, float)) and not isinstance(wert, bool):
        return muster.format(wert)
    breite = re.search(r">(\d+)", muster)
    return "–".rjust(int(breite.group(1))) if breite else "–"


def zeilen(datei: Path) -> list[str]:
    eintraege = analysis.read_run_log(datei)
    zustaende = [save_reader.zustand_bereinigen(e) for e in eintraege if e.get("typ") != "notiz"]
    notizen = [e for e in eintraege if e.get("typ") == "notiz"]
    b = lernen.laufbericht(zustaende, datei.stem, notizen)
    out = [f"{datei.stem} | {biome.deutsch(b.get('biom')) or '?'} | Prestige "
           f"{b.get('prestige') or '?'} | {b.get('jahre') or '?'} Jahre | {b.get('ausgang')}"
           + (f" | Ursache: {b['ursache']}" if b.get("ursache") else ""),
           "Jahr/Zeit  Spielzeit  Nahrung  reicht    Hunger  gegangen  tot  Ungeduld  Ruf   Bev."]
    for i, z in enumerate(zustaende):
        st = z.get("stats") or {}
        f = (forecast.food_forecast(tools_api._als_zustand(z), tools_api._als_zustand(zustaende[i - 1]))
             if i else None)
        if f is None or f.rate_per_second is None:
            reicht = "–"
        elif f.runway_seconds is not None:
            reicht = f"{f.runway_seconds / 60:.0f} min"
        else:
            reicht = "wächst"
        out.append(
            f"J{z.get('year', '?')}/{z.get('season', '?'):<7} {_zahl(z.get('game_time'), '{:>8.0f}')}  "
            f"{_zahl(f.stock if f else None, '{:>7.0f}')}  {reicht:<8}  "
            f"{_zahl(st.get('hunger'), '{:>6.0f}')}  {_zahl(st.get('gegangen'), '{:>8.0f}')}  "
            f"{_zahl(st.get('tot'), '{:>3.0f}')}  {_zahl(z.get('impatience'), '{:>8.1f}')}  "
            f"{_zahl(z.get('reputation'), '{:>4.1f}')}  {_zahl(z.get('population'), '{:>4.0f}')}")
    for n in b.get("empfehlungen") or []:
        out.append(f"Rat (Jahr {n.get('jahr') or '?'}): {n.get('text')}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--lauf", default=None, help="Name der Mitschrift (ohne .jsonl)")
    ap.add_argument("--liste", action="store_true", help="alle Mitschriften zeigen")
    args = ap.parse_args(argv)
    runs = aufloesen(args.runs)
    dateien = sorted(runs.glob("*.jsonl"), key=lambda p: p.stat().st_mtime) if runs.is_dir() else []
    if not dateien:
        print(f"Keine Mitschrift unter {runs}.")
        return 1
    if args.liste:
        for d in dateien:
            print(d.stem)
        return 0
    datei = runs / f"{args.lauf}.jsonl" if args.lauf else dateien[-1]
    if not datei.exists():
        print(f"Keine Mitschrift {datei.name}. `--liste` zeigt, welche es gibt.")
        return 1
    print("\n".join(zeilen(datei)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
