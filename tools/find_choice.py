#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die angebotene Auswahl im Spielstand suchen -- statt sie vom Bildschirm zu lesen.

Die Spec sieht fuer `read_choice` Phase 3 vor: Bildschirmfoto, Zuschnitt,
Texterkennung. Das ist der teuerste Weg im ganzen Plan und der einzige, der
nicht deterministisch ist.

Phase 0 hat aber gezeigt, dass der Spielstand sein Vokabular selbst mitbringt
-- 169 Gebaeude, 65 Effekte, die vollstaendige Warenliste, alle als Klartext.
Wenn das Spiel die drei angebotenen Grundsteine ebenfalls im Zustand haelt --
und irgendwo muss es sie halten, sonst ueberstuende die Auswahl kein Laden --
dann ist `read_choice` kein Bildschirmproblem, sondern eine Zeile in
`save_reader.py`.

Dieses Werkzeug beantwortet die Frage, statt sie zu vermuten. Zwei Befehle:

    scan   Einen Spielstand durchsuchen, waehrend eine Auswahl offen ist.
           Listet jede Liste kurzer Bezeichner, die wie ein Angebot aussieht,
           mit ihrem Pfad und den deutschen Namen dazu.

    diff   Zwei Spielstaende vergleichen -- einen mit offener Auswahl, einen
           danach. Der staerkste Beleg: die Liste, die schrumpft, waehrend
           genau einer ihrer Eintraege anderswo auftaucht, ist das Angebot.

Beides liest nur. Nur Standardbibliothek.

    python tools/find_choice.py scan --save "C:/.../Save.save"
    python tools/find_choice.py diff --before vorher/Save.save --after nachher/Save.save
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ats_assistant import kb  # noqa: E402

# Ein Angebot ist klein: drei Grundsteine, vier Bauplaene, ein paar Waren.
MIN_LAENGE = 2
MAX_LAENGE = 8

# Schluesselnamen, die auf eine Auswahl hindeuten. Das ist nur die Rangfolge
# der Ausgabe -- gefunden wird auch, was keinen dieser Namen traegt.
HINWEISE = (
    "pick", "picked", "offer", "offered", "choice", "choices", "option",
    "options", "available", "draw", "drawn", "reward", "rewards", "current",
    "pending", "toChoose", "cornerstone", "blueprint", "effect", "perk",
    "slots", "proposal",
)

# Bezeichner des Spiels: "Beanery", "RainCollectorBig", "[Food Raw] Meat".
ID_RE = re.compile(r"^(\[[^\]]+\]\s*)?[A-Za-z][A-Za-z0-9_' \-]{1,48}$")

# Felder, unter denen eine Liste von Dictionaries ihren Bezeichner fuehrt.
NAMENSFELDER = ("name", "id", "Name", "m_Name", "modelName", "effectName",
                "buildingName", "goodName")


def ist_bezeichner(wert) -> str | None:
    """Aus einem Listenelement den Bezeichner holen, falls es einer ist."""
    if isinstance(wert, str):
        return wert if ID_RE.match(wert) else None
    if isinstance(wert, dict):
        for feld in NAMENSFELDER:
            innen = wert.get(feld)
            if isinstance(innen, str) and ID_RE.match(innen):
                return innen
    return None


def listen(obj, pfad: str = "", tiefe: int = 0, grenze: int = 14):
    """Jede Liste im Baum, die ausschliesslich Bezeichner enthaelt."""
    if tiefe > grenze:
        return
    if isinstance(obj, dict):
        for schluessel, wert in obj.items():
            yield from listen(wert, f"{pfad}.{schluessel}" if pfad else str(schluessel),
                              tiefe + 1, grenze)
    elif isinstance(obj, list):
        namen = [ist_bezeichner(e) for e in obj]
        if obj and all(n is not None for n in namen):
            yield pfad, [n for n in namen if n is not None]
        else:
            for i, e in enumerate(obj):
                if isinstance(e, (dict, list)):
                    yield from listen(e, f"{pfad}[{i}]", tiefe + 1, grenze)


def hinweis_treffer(pfad: str) -> list[str]:
    klein = pfad.lower()
    return [h for h in HINWEISE if h.lower() in klein]


class Namen:
    """Bezeichner zu deutschen Namen aufloesen, soweit die Wissensbasis reicht."""

    def __init__(self, db: str | None) -> None:
        self.tabelle: dict[str, tuple[str, str]] = {}
        if not db or not Path(db).exists():
            return
        conn = kb.connect(db)
        try:
            for zeile in conn.execute(
                    "SELECT en, de, kind, en_id FROM name_map "
                    "WHERE confidence = 'localization'"):
                for form in (zeile["en"], zeile["en_id"]):
                    if form:
                        self.tabelle.setdefault(
                            form.lower().replace(" ", "").replace("'", ""),
                            (zeile["de"], zeile["kind"]))
        finally:
            conn.close()

    def __bool__(self) -> bool:
        return bool(self.tabelle)

    def auf(self, bezeichner: str) -> tuple[str, str] | None:
        roh = re.sub(r"^\[[^\]]*\]\s*", "", bezeichner)
        return self.tabelle.get(roh.lower().replace(" ", "").replace("'", ""))


def bewerte(pfad: str, eintraege: list[str], namen: Namen) -> tuple[int, list[str], int]:
    """Punkte, Gruende, Zahl der aufgeloesten Eintraege."""
    gruende: list[str] = []
    punkte = 0
    treffer = hinweis_treffer(pfad)
    if treffer:
        punkte += 2 * len(treffer)
        gruende.append("Pfad nennt " + "/".join(sorted(set(treffer))))
    if MIN_LAENGE <= len(eintraege) <= MAX_LAENGE:
        punkte += 2
        gruende.append(f"{len(eintraege)} Eintraege")
    aufgeloest = sum(1 for e in eintraege if namen.auf(e))
    if namen and aufgeloest:
        punkte += 3 * aufgeloest
        gruende.append(f"{aufgeloest} davon bekannt")
    if len(set(eintraege)) != len(eintraege):
        punkte -= 2
        gruende.append("enthaelt Wiederholungen")
    return punkte, gruende, aufgeloest


def lade(pfad: Path) -> dict:
    roh = pfad.read_bytes().lstrip(b" \t\r\n")
    if roh.startswith(b"\xef\xbb\xbf"):
        roh = roh[3:].lstrip(b" \t\r\n")
    return json.loads(roh.decode("utf-8", errors="replace"))


def zeige(eintraege: list[str], namen: Namen, breite: int = 4) -> str:
    teile = []
    for e in eintraege[:breite]:
        treffer = namen.auf(e)
        teile.append(f"{e} = {treffer[0]}" if treffer else e)
    if len(eintraege) > breite:
        teile.append(f"... (+{len(eintraege) - breite})")
    return ", ".join(teile)


def cmd_scan(args) -> int:
    pfad = Path(args.save)
    if not pfad.exists():
        print(f"Kein Spielstand unter {pfad}")
        return 1
    namen = Namen(args.db)
    daten = lade(pfad)

    funde = []
    for ort, eintraege in listen(daten):
        if not (args.min <= len(eintraege) <= args.max):
            continue
        punkte, gruende, aufgeloest = bewerte(ort, eintraege, namen)
        funde.append((punkte, ort, eintraege, gruende, aufgeloest))
    funde.sort(key=lambda f: (-f[0], f[1]))

    print(f"Spielstand: {pfad}  ({pfad.stat().st_size / 1e6:.1f} MB)")
    print(f"Wissensbasis: {'ja, ' + str(len(namen.tabelle)) + ' Namen' if namen else 'keine'}")
    print(f"Listen aus lauter Bezeichnern, Laenge {args.min} bis {args.max}: {len(funde)}\n")
    if not funde:
        print("Nichts gefunden. Stand die Auswahl offen, als der Spielstand entstand?")
        return 0

    for punkte, ort, eintraege, gruende, _ in funde[:args.zeigen]:
        print(f"[{punkte:>3}] {ort}")
        print(f"      {zeige(eintraege, namen)}")
        if gruende:
            print(f"      {'; '.join(gruende)}")
    if len(funde) > args.zeigen:
        print(f"\n... und {len(funde) - args.zeigen} weitere. Mit --zeigen mehr.")

    print("\nSo liest sich das: ein Treffer taugt, wenn seine Eintraege genau die")
    print("Namen sind, die im Spiel zur Wahl standen. Stimmt einer, ist Phase 3")
    print("fuer diese Auswahl erledigt -- ohne Bildschirm, ohne Texterkennung.")
    return 0


def cmd_diff(args) -> int:
    a, b = Path(args.before), Path(args.after)
    for p in (a, b):
        if not p.exists():
            print(f"Kein Spielstand unter {p}")
            return 1
    namen = Namen(args.db)
    vor = {ort: eintraege for ort, eintraege in listen(lade(a))}
    nach = {ort: eintraege for ort, eintraege in listen(lade(b))}

    geschrumpft = []
    gewachsen = []
    for ort, eintraege in vor.items():
        danach = nach.get(ort, [])
        weg = [e for e in eintraege if e not in danach]
        if weg and len(danach) < len(eintraege):
            geschrumpft.append((ort, eintraege, danach, weg))
    for ort, eintraege in nach.items():
        davor = vor.get(ort, [])
        neu = [e for e in eintraege if e not in davor]
        if neu:
            gewachsen.append((ort, neu))

    print(f"vorher:  {a}")
    print(f"nachher: {b}\n")
    print(f"Listen, die geschrumpft sind: {len(geschrumpft)}")
    print(f"Listen, die gewachsen sind:   {len(gewachsen)}\n")

    # Der eigentliche Beleg: was aus der einen Liste verschwand, taucht in
    # einer anderen auf. Das ist die getroffene Wahl.
    belege = []
    for ort, eintraege, danach, weg in geschrumpft:
        for ziel, neu in gewachsen:
            gemeinsam = [e for e in weg if e in neu]
            if gemeinsam:
                belege.append((ort, ziel, gemeinsam, eintraege))

    if belege:
        print("Angebot und Wahl gefunden:\n")
        for ort, ziel, gemeinsam, angebot in belege[:args.zeigen]:
            print(f"  Angebot:  {ort}")
            print(f"            {zeige(angebot, namen, breite=8)}")
            print(f"  Gewaehlt: {zeige(gemeinsam, namen, breite=8)}")
            print(f"            landet in {ziel}\n")
        print("Damit ist `read_choice` eine Abfrage auf dem Spielstand,")
        print("kein Bildschirmfoto.")
        return 0

    print("Kein Paar gefunden, bei dem ein Eintrag von der einen Liste in eine")
    print("andere gewandert ist. Was trotzdem hilft:\n")
    for ort, eintraege, danach, weg in geschrumpft[:args.zeigen]:
        print(f"  {ort}: {len(eintraege)} -> {len(danach)}, weg: {zeige(weg, namen)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="einen Spielstand mit offener Auswahl durchsuchen")
    s.add_argument("--save", required=True)
    s.add_argument("--db", default="kb.sqlite")
    s.add_argument("--min", type=int, default=MIN_LAENGE)
    s.add_argument("--max", type=int, default=MAX_LAENGE)
    s.add_argument("--zeigen", type=int, default=25)
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("diff", help="zwei Spielstaende vergleichen, vor und nach der Wahl")
    s.add_argument("--before", required=True)
    s.add_argument("--after", required=True)
    s.add_argument("--db", default="kb.sqlite")
    s.add_argument("--zeigen", type=int, default=10)
    s.set_defaults(func=cmd_diff)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
