#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wissensbasis aufbauen -- aus dem lokalen Wiki-Abzug und aus dem Spielstand.

Drei Unterbefehle:

    survey   Bestandsaufnahme des Wiki-Abzugs: welche Seiten, welche Vorlagen,
             welche Tabellenkoepfe. Daraus werden die Extraktoren geschrieben --
             gegen Belege, nicht gegen Vermutungen.
    seed     Namenstabelle aus data/name_map_seed.csv und das Vokabular aus
             kb_probe.py --dump-ids in kb.sqlite uebernehmen. Braucht kein Wiki.
    build    Wikitext auswerten und die Sachtabellen fuellen. Erst sinnvoll,
             wenn survey gelaufen ist.

    python tools/build_kb.py seed
    python tools/build_kb.py survey --wiki-dir "C:/Users/Joni/.cursor/wiki/against-the-storm-wiki"
    python tools/build_kb.py build  --wiki-dir "..."

Nur Standardbibliothek. Liest den Abzug ausschliesslich lesend.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ats_assistant import kb  # noqa: E402

GESPIELTE_VERSION = "1.10.4"

# {{Vorlagenname|...}} und {| class="wikitable" ... |}
TEMPLATE_RE = re.compile(r"\{\{\s*([^|}\n]+)")
TABLE_START_RE = re.compile(r"^\s*\{\|")
HEADER_RE = re.compile(r"^\s*!\s*(.+)$")
VERSION_RE = re.compile(r"\b(\d+\.\d+(?:\.\d+)?)\b")


def wikitext_dateien(wiki_dir: Path) -> list[Path]:
    """Findet die Wikitext-Dateien, egal wie der Abzug sie benannt hat."""
    for muster in ("wikitext/*.wiki", "wikitext/*.txt", "*.wiki", "**/*.wiki"):
        treffer = sorted(wiki_dir.glob(muster))
        if treffer:
            return treffer
    return []


def cmd_survey(args) -> int:
    wiki_dir = Path(args.wiki_dir)
    dateien = wikitext_dateien(wiki_dir)
    if not dateien:
        print(f"Keine Wikitext-Dateien unter {wiki_dir}")
        print("Erwartet wird ein Unterordner wikitext/ mit .wiki-Dateien.")
        return 1

    vorlagen: Counter = Counter()
    kopfzeilen: Counter = Counter()
    seiten: list[dict] = []
    versionen: Counter = Counter()

    for pfad in dateien:
        text = pfad.read_text(encoding="utf-8", errors="replace")
        eigene_vorlagen = [m.strip() for m in TEMPLATE_RE.findall(text)]
        vorlagen.update(eigene_vorlagen)

        eigene_kopf: list[str] = []
        in_tabelle = False
        for zeile in text.splitlines():
            if TABLE_START_RE.match(zeile):
                in_tabelle = True
                continue
            if in_tabelle:
                if zeile.strip().startswith("|}"):
                    in_tabelle = False
                    continue
                m = HEADER_RE.match(zeile)
                if m:
                    for teil in m.group(1).split("!!"):
                        sauber = teil.strip().strip("'").strip()
                        if sauber and len(sauber) < 40:
                            eigene_kopf.append(sauber)
        kopfzeilen.update(eigene_kopf)

        # "Version 1.9" oder ein Versionsbaustein im Text
        for v in VERSION_RE.findall(text[:4000]):
            if v.startswith("1."):
                versionen[v] += 1

        seiten.append({
            "titel": pfad.stem,
            "bytes": pfad.stat().st_size,
            "zeilen": text.count("\n") + 1,
            "vorlagen": sorted(set(eigene_vorlagen))[:8],
            "tabellenkoepfe": sorted(set(eigene_kopf))[:12],
        })

    L: list[str] = []
    add = L.append
    add("=" * 78)
    add("WIKI-ABZUG: BESTANDSAUFNAHME")
    add("=" * 78)
    add(f"Verzeichnis: {wiki_dir}")
    add(f"Seiten     : {len(dateien)}")
    add(f"Gesamt     : {sum(s['bytes'] for s in seiten) / 1024 / 1024:.1f} MB Wikitext")
    add("")
    add("Haeufigste Vorlagen (daran haengen die Infoboxen):")
    for name, n in vorlagen.most_common(40):
        add(f"  {n:>5}  {name}")
    add("")
    add("Haeufigste Tabellenkoepfe (daran haengen die Sachtabellen):")
    for name, n in kopfzeilen.most_common(50):
        add(f"  {n:>5}  {name}")
    add("")
    add("Im Text genannte Spielversionen:")
    for v, n in versionen.most_common(10):
        add(f"  {n:>5}  {v}" + ("   <- gespielt" if v == GESPIELTE_VERSION else ""))
    add("")
    add("Seiten, die fuer die Tabellen aus SPEC.md in Frage kommen:")
    for tabelle, hinweise in (
        ("buildings", ("building", "camp", "house", "workshop")),
        ("resources", ("resource", "good", "food", "material")),
        ("species", ("villager", "human", "beaver", "lizard", "harpy", "fox", "frog", "bat")),
        ("biomes", ("biome", "woodland", "forest", "marshland", "ravine", "thicket")),
        ("cornerstones", ("cornerstone", "perk", "effect")),
        ("prestige", ("prestige", "ascension", "difficulty")),
        ("glade_events", ("glade", "event", "mystery")),
    ):
        # Nach Titel UND nach Vorlage suchen: die Seite "Bakery" heisst nicht
        # nach Gebaeude, benutzt aber die Vorlage "Building infobox".
        nach_titel = [s["titel"] for s in seiten
                      if any(h in s["titel"].lower() for h in hinweise)]
        nach_vorlage = [s["titel"] for s in seiten
                        if any(h in v.lower() for v in s["vorlagen"] for h in hinweise)]
        passend = list(dict.fromkeys(nach_titel + nach_vorlage))
        add(f"  {tabelle:<14} {len(passend)} Treffer "
            f"({len(nach_titel)} per Titel, {len(nach_vorlage)} per Vorlage): "
            f"{', '.join(passend[:10]) if passend else '--'}")

    text = "\n".join(L)
    print(text)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / f"wiki-survey-{stamp}.txt").write_text(text, encoding="utf-8")
    (out / f"wiki-survey-{stamp}.json").write_text(
        json.dumps({"seiten": seiten,
                    "vorlagen": vorlagen.most_common(200),
                    "tabellenkoepfe": kopfzeilen.most_common(200)},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nBericht geschrieben: {out / f'wiki-survey-{stamp}.txt'}")
    print("Schick mir den .txt -- daraus schreibe ich die Extraktoren.")
    return 0


def scan_templates(text: str) -> list[tuple[str, str]]:
    """Alle {{Vorlage|...}} mit Inhalt, auch verschachtelt.

    Ein einfacher regulaerer Ausdruck reicht nicht: {{Recipe|{{rl|Wood}}|...}}
    enthaelt geschweifte Klammern, und wer beim ersten `}}` aufhoert,
    zerschneidet den Aufruf mitten im Parameter.
    """
    out: list[tuple[str, str]] = []
    i = 0
    while True:
        start = text.find("{{", i)
        if start < 0:
            return out
        tiefe, j = 0, start
        while j < len(text) - 1:
            if text[j:j + 2] == "{{":
                tiefe += 1
                j += 2
            elif text[j:j + 2] == "}}":
                tiefe -= 1
                j += 2
                if tiefe == 0:
                    break
            else:
                j += 1
        if tiefe != 0:
            return out
        inhalt = text[start + 2:j - 2]
        name = inhalt.split("|", 1)[0].strip()
        out.append((name, inhalt))
        i = start + 2


def split_params(inhalt: str) -> list[str]:
    """Parameter trennen, ohne in verschachtelten Vorlagen zu schneiden."""
    teile, tiefe, puffer = [], 0, []
    i = 0
    while i < len(inhalt):
        zwei = inhalt[i:i + 2]
        if zwei == "{{" or zwei == "[[":
            tiefe += 1
            puffer.append(zwei)
            i += 2
            continue
        if zwei == "}}" or zwei == "]]":
            tiefe -= 1
            puffer.append(zwei)
            i += 2
            continue
        if inhalt[i] == "|" and tiefe == 0:
            teile.append("".join(puffer))
            puffer = []
            i += 1
            continue
        puffer.append(inhalt[i])
        i += 1
    teile.append("".join(puffer))
    return teile[1:]   # der erste Teil ist der Vorlagenname


def cmd_detail(args) -> int:
    """Vorlagen aufschluesseln: welche Parameter, mit echten Beispielen."""
    wiki_dir = Path(args.wiki_dir)
    dateien = wikitext_dateien(wiki_dir)
    if not dateien:
        print(f"Keine Wikitext-Dateien unter {wiki_dir}")
        return 1

    gesucht = {n.lower() for n in args.name}
    treffer: dict[str, dict] = {}
    datenseiten: list[str] = []

    for pfad in dateien:
        text = pfad.read_text(encoding="utf-8", errors="replace")
        if pfad.stem.lower().startswith("data") or "dataloader" in text.lower()[:2000]:
            datenseiten.append(pfad.stem)
        for name, inhalt in scan_templates(text):
            if name.lower() not in gesucht:
                continue
            eintrag = treffer.setdefault(name, {"anzahl": 0, "params": Counter(), "beispiele": []})
            eintrag["anzahl"] += 1
            benannt = []
            for teil in split_params(inhalt):
                schluessel = teil.split("=", 1)[0].strip() if "=" in teil else "(unbenannt)"
                if len(schluessel) < 30:
                    benannt.append(schluessel)
            eintrag["params"].update(benannt)
            if len(eintrag["beispiele"]) < args.examples:
                gekuerzt = " ".join(inhalt.split())
                eintrag["beispiele"].append(f"[{pfad.stem}] {{{{{gekuerzt[:600]}}}}}")

    L: list[str] = []
    add = L.append
    add("=" * 78)
    add("VORLAGEN IM DETAIL")
    add("=" * 78)
    for name in args.name:
        eintrag = next((v for k, v in treffer.items() if k.lower() == name.lower()), None)
        add("")
        add("-" * 78)
        if not eintrag:
            add(f"{name}: nicht gefunden")
            continue
        add(f"{name}: {eintrag['anzahl']} Aufrufe")
        add("-" * 78)
        add("  Parameter:")
        for schluessel, n in eintrag["params"].most_common(30):
            add(f"    {n:>5}  {schluessel}")
        add("  Beispiele:")
        for b in eintrag["beispiele"]:
            add(f"    {b}")

    add("")
    add("-" * 78)
    add(f"Datenseiten (Dataloader): {len(datenseiten)}")
    add("-" * 78)
    for t in sorted(datenseiten)[:40]:
        add(f"  {t}")

    text = "\n".join(L)
    print(text)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / f"wiki-detail-{stamp}.txt").write_text(text, encoding="utf-8")
    print(f"\nBericht geschrieben: {out / f'wiki-detail-{stamp}.txt'}")
    return 0


def cmd_page(args) -> int:
    """Eine Seite im Rohzustand zeigen -- fuer alles, was die Aufschluesselung offen laesst."""
    wiki_dir = Path(args.wiki_dir)
    for titel in args.title:
        kandidaten = [p for p in wikitext_dateien(wiki_dir)
                      if p.stem.lower().replace("_", " ") == titel.lower().replace("_", " ")]
        print("=" * 78)
        if not kandidaten:
            print(f"{titel}: nicht gefunden")
            continue
        text = kandidaten[0].read_text(encoding="utf-8", errors="replace")
        print(f"{kandidaten[0].stem}  ({len(text)} Zeichen)")
        print("=" * 78)
        print(text[:args.chars])
        if len(text) > args.chars:
            print(f"\n[... {len(text) - args.chars} Zeichen gekuerzt]")
    return 0


def cmd_seed(args) -> int:
    conn = kb.connect(args.db)
    csv_pfad = Path(args.names)
    if csv_pfad.exists():
        zaehler = kb.seed_name_map(conn, csv_pfad)
        gesamt = sum(zaehler.values())
        print(f"name_map: {gesamt} Zeilen aus {csv_pfad.name}")
        for conf, n in sorted(zaehler.items(), key=lambda kv: -kv[1]):
            print(f"  {conf:<18} {n}")
    else:
        print(f"Keine Namenstabelle unter {csv_pfad}")

    if args.ids:
        ids_dir = Path(args.ids)
        if ids_dir.is_dir():
            zaehler = kb.import_save_ids(conn, ids_dir)
            print(f"\nsave_ids: {sum(zaehler.values())} IDs aus {ids_dir.name}")
            for art, n in sorted(zaehler.items(), key=lambda kv: -kv[1]):
                print(f"  {art:<18} {n}")
        else:
            print(f"\nKein ID-Verzeichnis unter {ids_dir}")

    print("\nAbdeckung:")
    for bereich, werte in kb.coverage(conn).items():
        if werte:
            print(f"  {bereich}: " + ", ".join(f"{k}={v}" for k, v in sorted(werte.items())))
    conn.close()
    return 0


def template_params(inhalt: str) -> dict[str, str]:
    """{{Vorlage|a|b|k=v}} -> {"1": "a", "2": "b", "k": "v"}."""
    out: dict[str, str] = {}
    pos = 0
    for teil in split_params(inhalt):
        if "=" in teil:
            schluessel, _, wert = teil.partition("=")
            schluessel = schluessel.strip()
            # "cost={{Construction|Wood=10}}" -- der aeussere Schluessel steht
            # vor dem ersten Gleichheitszeichen auf Ebene null, das hat
            # split_params schon sichergestellt.
            if schluessel and len(schluessel) < 40:
                out[schluessel] = wert.strip()
                continue
        pos += 1
        out[str(pos)] = teil.strip()
    return out


def cmd_build(args) -> int:
    """Datenseiten auswerten: Waren, guid-Index, Versionsstand, Baukosten."""
    wiki_dir = Path(args.wiki_dir)
    dateien = wikitext_dateien(wiki_dir)
    if not dateien:
        print(f"Keine Wikitext-Dateien unter {wiki_dir}")
        return 1

    conn = kb.connect(args.db)
    guids: list[dict] = []
    waren: list[dict] = []
    versionen = 0
    warnungen = 0
    baukosten = 0

    for pfad in dateien:
        text = pfad.read_text(encoding="utf-8", errors="replace")
        titel = pfad.stem
        seiten_version: str | None = None
        kosten: dict[str, float] = {}

        for name, inhalt in scan_templates(text):
            klein = name.lower()
            if klein == "dataloader/guid_index":
                guids.append(template_params(inhalt))
            elif klein == "dataloader/goods":
                p = template_params(inhalt)
                p["_seite"] = titel
                waren.append(p)
            elif klein == "version":
                p = template_params(inhalt)
                seiten_version = p.get("1") or seiten_version
            elif klein == "construction":
                for schluessel, wert in template_params(inhalt).items():
                    if schluessel.isdigit():
                        continue
                    try:
                        kosten[schluessel] = float(wert)
                    except ValueError:
                        pass

        if seiten_version:
            warnung = kb.record_page(conn, titel, None, None, seiten_version, GESPIELTE_VERSION)
            versionen += 1
            warnungen += 1 if warnung else 0
        if kosten:
            conn.execute(
                "INSERT INTO buildings (en, cost, source_page) VALUES (?, ?, ?) "
                "ON CONFLICT(en) DO UPDATE SET cost = excluded.cost, "
                "source_page = excluded.source_page",
                (titel, json.dumps(kosten, ensure_ascii=False), titel),
            )
            baukosten += 1

    conn.commit()

    # Erst der Index, dann die Waren -- die Kategorie wird ueber ihn aufgeloest.
    n_guids = kb.import_guid_index(conn, guids)
    n_waren = kb.import_goods(conn, waren, source_page="Data_Goods_1")
    kb.link_name_map_to_resources(conn)

    print(f"guid_index : {n_guids} Einträge")
    print(f"resources  : {n_waren} Waren aus Dataloader/Goods")
    print(f"buildings  : {baukosten} Baukosten aus {{{{Construction}}}}")
    print(f"source_pages: {versionen} Seiten mit Versionsangabe, davon {warnungen} mit Warnung")

    essbar = kb.food_goods(conn)
    print(f"\nEssbare Waren: {len(essbar)}")
    for w in essbar[:12]:
        print(f"  {w['en']:<22} {w['save_id'] or '':<28} Sättigung {w['eating_fullness']}")

    offen = kb.missing_german(conn)
    print(f"\nWaren ohne belegten deutschen Namen: {len(offen)}")
    for w in offen[:10]:
        print(f"  {w['en']:<22} Schlüssel {w['display_key'] or '--'}")
    if offen:
        print("\n  display_key ist der Lokalisierungsschlüssel des Spiels. Findet sich")
        print("  im Spielordner eine deutsche Sprachtabelle, sind diese Namen ein")
        print("  Nachschlag statt einer Vermutung.")

    print("\nAbdeckung:")
    for bereich, werte in kb.coverage(conn).items():
        if werte:
            print(f"  {bereich}: " + ", ".join(f"{k}={v}" for k, v in sorted(werte.items())))
    conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("survey", help="Bestandsaufnahme des Wiki-Abzugs")
    s.add_argument("--wiki-dir", required=True)
    s.add_argument("--out", default="diagnostics")
    s.set_defaults(func=cmd_survey)

    s = sub.add_parser("seed", help="Namenstabelle und Save-Vokabular einlesen")
    s.add_argument("--db", default="kb.sqlite")
    s.add_argument("--names", default="data/name_map_seed.csv")
    s.add_argument("--ids", help="Verzeichnis aus kb_probe.py --dump-ids")
    s.set_defaults(func=cmd_seed)

    s = sub.add_parser("detail", help="Vorlagen aufschluesseln: Parameter und Beispiele")
    s.add_argument("--wiki-dir", required=True)
    s.add_argument("--name", nargs="+", default=[
        "Buildingbox", "Goodbox", "Recipe", "Construction", "Perk", "Perks",
        "Version", "Deposit", "Dataloader/Goods", "Dataloader/guid_index",
    ])
    s.add_argument("--examples", type=int, default=3)
    s.add_argument("--out", default="diagnostics")
    s.set_defaults(func=cmd_detail)

    s = sub.add_parser("page", help="eine Wikiseite im Rohzustand zeigen")
    s.add_argument("--wiki-dir", required=True)
    s.add_argument("--title", nargs="+", required=True)
    s.add_argument("--chars", type=int, default=3000)
    s.set_defaults(func=cmd_page)

    s = sub.add_parser("build", help="Wikitext auswerten (noch nicht fertig)")
    s.add_argument("--wiki-dir", required=True)
    s.add_argument("--db", default="kb.sqlite")
    s.set_defaults(func=cmd_build)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
