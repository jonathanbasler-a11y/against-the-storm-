#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Liegt das HUD über dem Spiel? -- eine Probe mit Beispielwerten.

    python tools\\hud_probe.py                 20 Sekunden, dann zu
    python tools\\hud_probe.py --sekunden 60
    python tools\\hud_probe.py --tasten        dazu Strg+Umschalt+L/H ausprobieren

Das Spiel starten, dieses Skript starten und ins Spiel wechseln. Sichtbar
oben links sollte ein dunkler Kasten stehen. Drei Dinge prüfen:

1. Steht der Kasten über dem Spiel? Wenn nicht, läuft das Spiel im
   exklusiven Vollbild -- in den Spieleinstellungen das randlose Fenster
   wählen.
2. Nimmt ein Klick in den Kasten (verschieben, „+“, „▁“) dem Spiel den Fokus?
   Er soll es nicht.
3. Mit `--tasten`: kommt „Strg+Umschalt+L“ an, während das Spiel vorn ist?

Die Probe merkt sich nichts -- das echte HUD im Fenster behält seinen Platz.
"""

from __future__ import annotations

import argparse
import queue
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def beispiel(kasten) -> None:
    from ats_assistant import engpass

    kasten.zeigen("zustand", {"jahr": 3, "bauplan_wahl": {"angebot": ["Kiln", "Workshop"]}})
    kasten.zeigen("wissen", {"bauplan_vergleich": [
        {"gebaeude": "Kiln", "gebaeude_de": "Brennofen", "besser_oder_neu": 2},
        {"gebaeude": "Workshop", "gebaeude_de": "Werkstatt"}]})
    kasten.zeigen("engpass", engpass.uhren(
        {"reichweite_sekunden": 240.0},
        {"sekunden_bis_verlust": 780.0, "jetzt": 9.2, "schwelle": 14},
        {"hunger": 3, "gegangen": 1, "zysten": {"entstanden": 6, "verbrannt": 4}}))
    kasten.zeigen("rat", {"ok": True, "text": "Beispiel: Nimm den Brennofen. Er macht Ziegel."})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sekunden", type=float, default=20.0)
    ap.add_argument("--tasten", action="store_true",
                    help="Strg+Umschalt+L und Strg+Umschalt+H ausprobieren (nur Windows)")
    args = ap.parse_args(argv)

    import tkinter as tk

    from ats_assistant import hud

    root = tk.Tk()
    root.withdraw()
    kasten = hud.Hud(root, pfad=None,
                     beim_lesen=lambda: print("Knopf „Karten lesen“ gedrückt."))
    beispiel(kasten)
    print(f"Bildschirm laut Tk: {root.winfo_screenwidth()} × {root.winfo_screenheight()}")
    print(f"Das HUD steht oben links, {args.sekunden:.0f} Sekunden lang. Jetzt ins Spiel wechseln.")

    meldungen: queue.Queue = queue.Queue()
    tasten = None
    if args.tasten:
        tasten = hud.Tasten(hud.VORGABEN["tasten"], lambda art, wert: meldungen.put((art, wert)))
        if not tasten.starten():
            print("Tastenkombinationen gibt es nur unter Windows.")

    def abholen() -> None:
        while not meldungen.empty():
            art, wert = meldungen.get_nowait()
            print(f"{art}: {wert}")
            if art == "taste" and wert == "hud":
                kasten.umschalten()
            elif art == "taste":
                kasten.zeigen("lesen", None)           # im Fenster läse es jetzt die Karten
            else:
                kasten.zeigen(art, wert)
        root.after(100, abholen)

    root.after(100, abholen)
    root.after(int(args.sekunden * 1000), root.destroy)
    root.mainloop()
    if tasten is not None:
        tasten.stoppen()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
