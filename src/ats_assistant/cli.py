"""Ein Befehl fuer die Lage, ohne MCP-Server.

Die Werkzeuge aus Phase 4 sind gewoehnliche Funktionen -- das war Absicht.
Hier bekommen sie eine Kommandozeile: wer schnell wissen will, wie es steht
und was zu bauen waere, soll dafuer keinen Server starten muessen.

    ats-lage                      Zustand, Nahrung, Ungeduld auf einen Blick
    ats-lage nahrung              nur die Ketten, ausfuehrlich
    ats-lage nachschlag Imbiss    ein Name, deutsch oder englisch
    ats-lage form                 wie Lager und Gebaeude im Spielstand liegen
    ats-lage form order relic     Schluessel mit diesen Woertern, in allen Dateien
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import tools_api
from .mcp_server import aufloesen
from .orte import finde_spielordner
from .rechner import feindseligkeit, statistik_satz


def _minuten(sekunden: float | None) -> str:
    if sekunden is None:
        return "--"
    return f"{sekunden / 60:.0f} min"


def _zeile(titel: str, wert) -> str:
    return f"  {titel:<24} {wert}"


def cmd_lage(args) -> int:
    zustand = tools_api.get_state(args.save_dir, args.runs, auf_ruhe_warten=not args.sofort)
    if zustand.get("verfuegbar") is False:
        # Sonst stuende hier "Jahr None, ?, Prestige None" -- das sieht aus
        # wie eine Siedlung ohne Eigenschaften statt wie ein fehlender
        # Spielstand.
        print(zustand.get("fehler") or zustand.get("grund") or "Kein Spielstand lesbar.")
        return 1
    print(f"Jahr {zustand.get('jahr')}, {zustand.get('biom') or '?'}, "
          f"Prestige {zustand.get('prestige')}")
    print(_zeile("Bevölkerung", zustand.get("bevoelkerung")))
    print(_zeile("Feindseligkeit", feindseligkeit(zustand.get("feindseligkeit"))))
    print(_zeile("Reputation", f"{zustand.get('reputation')} von "
                               f"{zustand.get('reputation_ziel')}"))
    print(_zeile("Ungeduld", f"{zustand.get('ungeduld')} von "
                             f"{zustand.get('ungeduld_schwelle')}"))
    if zustand.get("ruf_quellen"):
        print(_zeile("Ruf-Quellen", ", ".join(
            f"{name} {wert:.2f}" for name, wert in zustand["ruf_quellen"].items())))
    if zustand.get("statistik") or zustand.get("lichtungen") is not None:
        print(_zeile("Statistik", statistik_satz(zustand.get("statistik"),
                                                 zustand.get("lichtungen"))))
    effekte = zustand.get("effekte") or {}
    if effekte.get("aktiv"):
        print(_zeile("Aktive Effekte", ", ".join(
            e.get("name") or e["modell"] for e in effekte["aktiv"])))
    if effekte.get("hunger_multiplikator") is not None:
        print(_zeile("Hungermultiplikator", effekte["hunger_multiplikator"]))
    if effekte.get("abweichungen"):
        abw = effekte["abweichungen"]
        text = ", ".join(f"{a.get('name') or a['feld']} {a['wert']} (sonst {a['grundwert']})"
                         for a in abw[:6])
        if len(abw) > 6:
            text += f"  (+{len(abw) - 6})"
        print(_zeile("Abweichende Effekte", text))
    # Ein leeres Lager und ein nicht gelesenes sehen sonst gleich aus.
    if zustand.get("nicht_gefunden"):
        print(_zeile("Im Spielstand nicht gefunden",
                     ", ".join(zustand["nicht_gefunden"])))
    if zustand.get("form_unbekannt"):
        print(_zeile("Gefunden, aber nicht lesbar",
                     ", ".join(zustand["form_unbekannt"])
                     + "  -> python tools\\lage.py form"))

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
    if rat.get("fehler"):
        print(rat["fehler"])
        return 1
    if not rat.get("verfuegbar"):
        if rat.get("grund"):
            print(rat["grund"])
            return 0
        # Auch ohne tragende Kette gibt es etwas zu sagen -- und der zweite
        # Satz ist der, der weiterhilft.
        for schluessel in ("empfehlung", "begruendung", "alternative"):
            if rat.get(schluessel):
                print(rat[schluessel])
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


def cmd_form(args) -> int:
    from .save_reader import formbericht
    zeilen = formbericht(Path(args.save_dir), wait=not args.sofort,
                         stichworte=tuple(args.stichworte), pfad=args.pfad,
                         grenze=None if args.alle else 30,
                         werte=getattr(args, "werte", False))
    for zeile in zeilen:
        print(zeile)
    return 1 if zeilen[0].startswith("Kein Spielstand") else 0


def cmd_nachschlag(args) -> int:
    out = tools_api.query_kb(" ".join(args.name), db=args.db)
    if out.get("fehler"):
        print(out["fehler"])
        return 1
    for n in out.get("namen", []):
        herkunft = n.get("loc_key") or n.get("source") or ""
        print(f"  {n['de']:<28} {n['en']:<28} {n['kind'] or '':<12} "
              f"{n['confidence']:<14} {herkunft}")
    for schluessel in ("ware", "gebaeude", "grundstein", "hinweis"):
        if out.get(schluessel):
            print(f"\n{schluessel}: {out[schluessel]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Die gemeinsamen Optionen kommen als Elternteil an jeden Unterbefehl:
    # sonst nimmt argparse sie nur vor dem Unterbefehl an, und
    # "lage.py nachschlag Holz --db andere.sqlite" scheitert an einer
    # Stelle, an der niemand einen Fehler erwartet.
    # Und zwar ohne Vorgaben: haette der Unterbefehl welche, wuerden sie die
    # Angabe vor dem Unterbefehl ueberschreiben -- argparse setzt die
    # Vorgaben des Unterparsers, nachdem der Hauptparser seine Werte schon
    # eingetragen hat. "lage.py --db andere.sqlite nachschlag Holz" haette
    # dann still die falsche Wissensbasis gelesen. SUPPRESS heisst: nur was
    # wirklich dasteht, landet im Ergebnis.
    gemeinsam = argparse.ArgumentParser(add_help=False)
    gemeinsam.add_argument("--save-dir", default=argparse.SUPPRESS,
                           help="Spielordner; ohne Angabe wird gesucht")
    gemeinsam.add_argument("--runs", default=argparse.SUPPRESS)
    gemeinsam.add_argument("--db", default=argparse.SUPPRESS)
    gemeinsam.add_argument("--sofort", action="store_true",
                           default=argparse.SUPPRESS,
                           help="nicht auf Ruhe warten -- nur wenn gerade "
                                "nicht gespeichert wird")

    ap = argparse.ArgumentParser(
        description=__doc__, parents=[gemeinsam],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("nahrung", parents=[gemeinsam],
                       help="alle Nahrungsketten, ausführlich")
    s.set_defaults(func=cmd_nahrung)

    s = sub.add_parser("nachschlag", parents=[gemeinsam],
                       help="einen Namen nachschlagen")
    s.add_argument("name", nargs="+")
    s.set_defaults(func=cmd_nachschlag)

    s = sub.add_parser("form", parents=[gemeinsam],
                       help="Aufbau von Lager und Gebäuden im Spielstand, "
                            "ohne Werte -- zum Einfügen in den Chat")
    s.add_argument("stichworte", nargs="*",
                   help="statt Lager und Gebäuden: Schlüssel suchen, die eines "
                        "dieser Wörter enthalten, z. B. order reputation blueprint")
    s.add_argument("--alle", action="store_true",
                   help="keine Grenze von 30 Zeilen je Datei")
    s.add_argument("--pfad", default=None,
                   help="einen Knoten ganz zeigen, z. B. content oder "
                        "goods.goods -- ohne $ vorn, das stört PowerShell")
    s.add_argument("--werte", action="store_true",
                   help="mit --pfad: Zahlen und Wahrheitswerte zeigen (keine Texte), "
                        "z. B. --pfad effects --werte")
    s.set_defaults(func=cmd_form)

    args = ap.parse_args(argv)
    for name, vorgabe in (("save_dir", None), ("runs", "runs"),
                          ("db", "kb.sqlite"), ("sofort", False)):
        if not hasattr(args, name):
            setattr(args, name, vorgabe)
    # Wie beim Server: ein relatives "kb.sqlite" soll die Wissensbasis des
    # Projekts meinen, nicht eine leere im Arbeitsverzeichnis.
    args.runs = aufloesen(args.runs)
    args.db = aufloesen(args.db)
    if getattr(args, "func", None) is None:
        args.func = cmd_lage
    if args.func in (cmd_lage, cmd_form) and not args.save_dir:
        gefunden = finde_spielordner()
        if gefunden is None:
            print("Kein Spielordner gefunden. Mit --save-dir angeben.")
            return 1
        args.save_dir = gefunden
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
