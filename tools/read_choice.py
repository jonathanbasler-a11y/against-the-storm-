#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Den Auswahlbildschirm lesen -- Phase 3.

    python tools/read_choice.py pruefen     Was die Umgebung hergibt
    python tools/read_choice.py lesen       Aufnehmen, erkennen, abgleichen
    python tools/read_choice.py lesen --bild foto.png
    python tools/read_choice.py lesen --text "PILZFÜHRER" "EXPORTSPEZIALISIERUNG"

Es geht kein Bild an ein Modell. Was herauskommt, sind Namen und Zahlen.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ats_assistant import screen, tools_api  # noqa: E402


def cmd_pruefen(args) -> int:
    lage = screen.verfuegbar()
    print(f"Plattform: {lage['plattform']}\n")
    print("Aufnahme:")
    for name, da in lage["aufnahme"].items():
        print(f"  {'ja ' if da else 'nein'}  {name}")
    print("\nTexterkennung:")
    for name, da in lage["erkennung"].items():
        print(f"  {'ja ' if da else 'nein'}  {name}")
    print(f"\n{lage['rat']}")
    if not any(lage["erkennung"].values()):
        print("\nOhne Texterkennung geht es trotzdem: die Kartentitel abtippen und")
        print('  python tools/read_choice.py lesen --text "PILZFÜHRER" "..."')
        print("Der Abgleich gegen die belegten Namen ist derselbe.")
    return 0


def cmd_lesen(args) -> int:
    out = tools_api.read_choice(bild=args.bild, text=args.text, db=args.db,
                                arten=tuple(args.arten),
                                aufnehmen=not args.bild and not args.text)
    if not out["verfuegbar"]:
        print(out.get("grund") or "Nichts gelesen.")
        if out.get("unklar"):
            print("\nNah dran, aber nicht eindeutig:")
            for u in out["unklar"]:
                nahe = ", ".join(f"{k['de']} ({k['guete']})" for k in u["kandidaten"])
                print(f"  gelesen {u['gelesen']!r} -> {nahe}")
        return 1

    print(f"Quelle: {out['quelle']}, {out['gelesene_zeilen']} Zeilen gelesen\n")
    print(f"Im Angebot ({len(out['angebot'])}):")
    for a in out["angebot"]:
        zeile = f"  {a['de']}  ({a['en']}"
        if a.get("seltenheit"):
            zeile += f", {a['seltenheit']}"
        zeile += f", Güte {a['guete']})"
        print(zeile)
        if a.get("wirkung"):
            print(f"      {a['wirkung'][:150]}")
    if out.get("unklar"):
        print("\nNicht eindeutig, deshalb nicht im Angebot:")
        for u in out["unklar"]:
            nahe = ", ".join(f"{k['de']} ({k['guete']})" for k in u["kandidaten"])
            print(f"  {u['gelesen']!r} -> {nahe}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("pruefen", help="zeigen, was die Umgebung hergibt")
    s.set_defaults(func=cmd_pruefen)

    s = sub.add_parser("lesen", help="den Auswahlbildschirm lesen")
    s.add_argument("--bild", help="Bildschirmfoto; ohne Angabe wird eines aufgenommen")
    s.add_argument("--text", nargs="*", help="Kartentitel von Hand, ohne Texterkennung")
    s.add_argument("--db", default="kb.sqlite")
    s.add_argument("--arten", nargs="*", default=["effect"],
                   help="worauf abgeglichen wird: effect, building, ...")
    s.set_defaults(func=cmd_lesen)

    args = ap.parse_args(argv)
    if getattr(args, "func", None) is None:
        return cmd_pruefen(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
