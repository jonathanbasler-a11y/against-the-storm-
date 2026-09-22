"""Ein Befehl fuer die Lage, ohne MCP-Server.

Die Werkzeuge aus Phase 4 sind gewoehnliche Funktionen -- das war Absicht.
Hier bekommen sie eine Kommandozeile: wer schnell wissen will, wie es steht
und was zu bauen waere, soll dafuer keinen Server starten muessen.

    ats-lage                      Zustand, Nahrung, Ungeduld auf einen Blick
    ats-lage nahrung              nur die Ketten, ausfuehrlich
    ats-lage nachschlag Imbiss    ein Name, deutsch oder englisch
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import tools_api


def _minuten(sekunden: float | None) -> str:
    if sekunden is None:
        return "--"
    return f"{sekunden / 60:.0f} min"


def _zeile(titel: str, wert) -> str:
    return f"  {titel:<24} {wert}"


def cmd_lage(args) -> int:
    zustand = tools_api.get_state(args.save_dir, args.runs, auf_ruhe_warten=not args.sofort)
    print(f"Jahr {zustand.get('jahr')}, {zustand.get('biom') or '?'}, "
          f"Prestige {zustand.get('prestige')}")
    print(_zeile("Bevölkerung", zustand.get("bevoelkerung")))
    print(_zeile("Feindseligkeit", zustand.get("feindseligkeit")))
    print(_zeile("Reputation", f"{zustand.get('reputation')} von "
                               f"{zustand.get('reputation_ziel')}"))
    print(_zeile("Ungeduld", f"{zustand.get('ungeduld')} von "
                             f"{zustand.get('ungeduld_schwelle')}"))

    nahrung = tools_api.food_forecast(args.runs)
    print("\nNahrung")
    if nahrung.get("verfuegbar"):
        print(_zeile("Bestand", nahrung.get("bestand")))
        print(_zeile("Reichweite", _minuten(nahrung.get("reichweite_sekunden"))))
        if nahrung.get("warnung"):
            print(_zeile("Warnung", nahrung["warnung"]))
    else:
        print(_zeile("", nahrung.get("grund", "unbekannt")))

    ungeduld = tools_api.impatience_forecast(args.runs)
    if ungeduld.get("verfuegbar"):
        print("\nUngeduld")
        print(_zeile("bis zur Niederlage", _minuten(ungeduld.get("sekunden_bis_verlust"))))

    rat = tools_api.food_advice(args.runs, args.db)
    print("\nRat")
    if rat.get("verfuegbar"):
        for satz in (rat["empfehlung"], rat["begruendung"], rat["alternative"]):
            print(f"  {satz}")
    else:
        print(_zeile("", rat.get("grund") or rat.get("empfehlung", "--")))
    return 0


def cmd_nahrung(args) -> int:
    rat = tools_api.food_advice(args.runs, args.db)
    if not rat.get("verfuegbar"):
        print(rat.get("grund") or rat.get("empfehlung", "Nichts zu sagen."))
        return 0
    for satz in (rat["empfehlung"], rat["begruendung"], rat["alternative"]):
        print(satz)
    print(f"\nAlle Ketten, die der Bestand trägt ({len(rat['ketten'])}):")
    for k in rat["ketten"]:
        einsatz = ", ".join(f"{e['menge']:.0f} {e['ware']}" for e in k["einsatz"])
        print(f"  {k['gebaeude_de'] or k['gebaeude']:<24} {einsatz:<28} "
              f"+{k['gewinn']:.0f} Sättigung  "
              f"(Faktor {k['faktor']}, Engpass {k['engpass']}, "
              f"{_minuten(k['sekunden'])} Arbeit)")
    return 0


def cmd_nachschlag(args) -> int:
    out = tools_api.query_kb(" ".join(args.name), db=args.db)
    for n in out.get("namen", []):
        herkunft = n.get("loc_key") or n.get("source") or ""
        print(f"  {n['de']:<28} {n['en']:<28} {n['kind'] or '':<12} "
              f"{n['confidence']:<14} {herkunft}")
    for schluessel in ("ware", "gebaeude", "grundstein", "hinweis"):
        if out.get(schluessel):
            print(f"\n{schluessel}: {out[schluessel]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--save-dir", default=None,
                    help="Spielordner; ohne Angabe wird gesucht")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--db", default="kb.sqlite")
    ap.add_argument("--sofort", action="store_true",
                    help="nicht auf Ruhe warten -- nur wenn gerade nicht gespeichert wird")
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("nahrung", help="alle Nahrungsketten, ausführlich")
    s.set_defaults(func=cmd_nahrung)

    s = sub.add_parser("nachschlag", help="einen Namen nachschlagen")
    s.add_argument("name", nargs="+")
    s.set_defaults(func=cmd_nachschlag)

    args = ap.parse_args(argv)
    if getattr(args, "func", None) is None:
        args.func = cmd_lage
    if args.func is cmd_lage and not args.save_dir:
        from .save_reader import finde_spielordner
        gefunden = finde_spielordner()
        if gefunden is None:
            print("Kein Spielordner gefunden. Mit --save-dir angeben.")
            return 1
        args.save_dir = gefunden
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
