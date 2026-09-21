#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sonde: taugt der Spielstand als Quelle fuer kb.sqlite?

Die Phase-0-Messung hat in MetaSave.save eine Liste content.buildings mit 169
Eintraegen gefunden. Falls das der Gebaeudekatalog des Spiels ist, waere er
eine bessere Quelle als das Wiki: aktuell zur installierten Version, in
denselben IDs wie der Rest des Saves, ohne Crawlen. Falls es nur
Freischaltmarker sind, bleibt das Wiki noetig.

Die Sonde sucht katalogartige Strukturen in allen drei Spielstandsdateien und
beantwortet fuer jede Tabelle aus SPEC.md Phase 1 drei Fragen:

    1. Stehen die IDs im Save?      -> dann liefert der Save das Vokabular
    2. Stehen auch Zahlen dabei?    -> dann ersetzt der Save das Wiki
    3. Oder gar nichts?             -> dann bleibt es beim Scraper

Nur Standardbibliothek. Oeffnet die Dateien ausschliesslich lesend.

    python tools/kb_probe.py
    python tools/kb_probe.py --dump-ids
    python tools/kb_probe.py --dir "D:/pfad/zum/ordner"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase0_diagnose import (  # noqa: E402
    decode_container,
    list_save_files,
    preview,
    resolve_dir,
)

# Ab wie vielen Eintraegen eine Struktur als Katalog gilt. Darunter ist es
# Zustand (die drei Spezies dieser Siedlung), darueber Vokabular (alle
# Spezies des Spiels).
MIN_CATALOG = 12

# Zahlenfelder: daran haengt, ob der Save das Wiki ersetzen kann. Ein Eintrag
# mit Kosten und Rezept ist ein Datensatz, einer ohne ist ein Marker.
NUMERIC_KEYS = (
    "cost", "price", "value", "amount", "required", "capacity",
    "recipe", "recipes", "production", "produced", "ingredient", "input", "output",
    "workplace", "worker", "workers", "slots", "resolve",
)

# Attributfelder: keine Zahlen, aber Einordnung, die die Wissensbasis braucht --
# die Tabelle cornerstones will ausdruecklich Seltenheit und Quelle.
# "biome" steht bewusst in keiner der beiden Listen: ein Feld namens biome ist
# ein Verweis, kein Datum.
ATTRIBUTE_KEYS = (
    "rarity", "tier", "category", "specialization", "requirement",
    "effect", "effects", "bonus", "modifier", "need", "needs", "source",
)

ECONOMIC_KEYS = NUMERIC_KEYS + ATTRIBUTE_KEYS

# Tabellen aus SPEC.md Phase 1 und woran man ihren Katalog erkennt.
KB_TABLES: dict[str, tuple[str, ...]] = {
    "buildings": ("building", "construction"),
    "resources": ("good", "resource", "item"),
    "recipes": ("recipe", "production"),
    "species": ("race", "species", "villager"),
    "biomes": ("biome", "field", "world"),
    "cornerstones": ("cornerstone", "perk", "effect", "sse"),
    "prestige": ("difficulty", "prestige", "modifier"),
    "glade_events": ("glade", "event", "mystery"),
}


def catalogs(data, min_len: int, max_nodes: int) -> list[dict]:
    """Sammelt katalogartige Listen und Zuordnungen samt Form ihrer Eintraege."""
    found: list[dict] = []
    stack = [(data, "$", 0)]
    nodes = 0
    while stack:
        node, path, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            break

        if isinstance(node, list) and len(node) >= min_len:
            found.append(describe(node, path, depth))
        elif isinstance(node, dict) and len(node) >= min_len:
            vals = list(node.values())[:50]
            if vals and all(isinstance(v, list) for v in vals):
                found.append(
                    {
                        "path": path, "depth": depth, "kind": "Schluesselmenge",
                        "length": len(node), "entry_keys": [],
                        "examples": list(node)[:6],
                        "economic": [], "ids": [k for k in node if isinstance(k, str)],
                    }
                )
            elif vals and all(isinstance(v, (int, float, str, bool)) for v in vals):
                # Zuordnung ID -> Zahl, z. B. Lagerbestand oder Statistik
                found.append(
                    {
                        "path": path, "depth": depth, "kind": "Zuordnung",
                        "length": len(node), "entry_keys": [],
                        "examples": [f"{k}={preview(v, 40)}" for k, v in list(node.items())[:6]],
                        "economic": [],
                    }
                )

        if isinstance(node, dict):
            for k, v in node.items():
                stack.append((v, f"{path}.{k}", depth + 1))
        elif isinstance(node, list):
            for i, v in enumerate(node[:60]):
                stack.append((v, f"{path}[{i}]", depth + 1))

    found.sort(key=lambda c: (-c["length"], c["path"]))
    return found


def describe(items: list, path: str, depth: int) -> dict:
    sample = items[:60]
    if all(isinstance(x, str) for x in sample):
        return {
            "path": path, "depth": depth, "kind": "ID-Liste", "length": len(items),
            "entry_keys": [], "examples": sample[:8], "economic": [],
            "ids": [x for x in items if isinstance(x, str)],
        }
    if all(isinstance(x, dict) for x in sample):
        keys: Counter = Counter()
        for x in sample:
            keys.update(x.keys())
        key_names = [k for k, _ in keys.most_common(40)]
        numeric = sorted({k for k in key_names if any(e in k.lower() for e in NUMERIC_KEYS)})
        attrs = sorted({k for k in key_names if any(e in k.lower() for e in ATTRIBUTE_KEYS)})
        economic = sorted(set(numeric) | set(attrs))
        ids = []
        for x in items:
            if not isinstance(x, dict):
                continue
            for cand in ("name", "id", "model", "key", "good", "building"):
                if isinstance(x.get(cand), str):
                    ids.append(x[cand])
                    break
        return {
            "path": path, "depth": depth, "kind": "Objektliste", "length": len(items),
            "entry_keys": key_names,
            "examples": [json.dumps(x, ensure_ascii=False)[:160] for x in sample[:3]],
            "economic": economic, "numeric": numeric, "attributes": attrs, "ids": ids,
        }
    return {
        "path": path, "depth": depth, "kind": "gemischte Liste", "length": len(items),
        "entry_keys": [], "examples": [preview(x, 60) for x in sample[:4]], "economic": [],
    }


# Felder, an denen eine Instanz kenntlich ist: etwas, das auf der Karte steht
# und einen Zustand hat. Ein Katalogeintrag hat so etwas nicht.
INSTANCE_KEYS = ("position", "field", "placed", "lifted", "finished", "rotation",
                 "buildingprogress", "lastupdate", "isactive", "key", "value")

# Pfadwurzeln, unter denen kein Vokabular steht, sondern Zustand, Verlauf oder
# Statistik. Die Laufhistorie ist der haeufigste Fehlalarm: sie enthaelt
# Felder wie buildingsMovedAmount, die nach Gebaeudedaten klingen und keine
# sind.
NON_CATALOG_ROOTS = (
    "$.world", "$.buildings", "$.actors", "$.trends", "$.stats", "$.analytics",
    "$.gamesHistory", "$.goals", "$.marketing", "$.tutorial", "$.rewards",
    "$.capitalState", "$.fields", "$.modifiers", "$.worldEvents",
    "$.gameConditions", "$.gameplay",
)


def classify(c: dict) -> str:
    """Katalog, Datensatz, Zustand, Verlauf oder Statistik."""
    path = c["path"]
    keys_low = " ".join(c.get("entry_keys") or []).lower()

    if c["kind"] == "Schluesselmenge":
        # Zuordnung ID -> Zeitreihe: der Inhalt ist Verlauf, die SCHLUESSEL
        # sind Vokabular. goodsTrends liefert so die vollstaendige Warenliste.
        return "Vokabular"
    if path.startswith("$.trends"):
        return "Verlauf"
    if any(path.startswith(r) for r in ("$.stats", "$.analytics", "$.gamesHistory", "$.goals",
                                        "$.marketing", "$.tutorial", "$.rewards")):
        return "Statistik"
    if c["kind"] == "gemischte Liste":
        return "Verlauf"
    if any(path.startswith(r) for r in NON_CATALOG_ROOTS):
        return "Zustand"
    if c["kind"] == "Objektliste" and any(k in keys_low for k in INSTANCE_KEYS):
        return "Zustand"
    if c["kind"] == "ID-Liste":
        # Eine reine Namensliste ist Vokabular -- ausser sie steht unter einer
        # Wurzel, die Zustand oder Historie fuehrt.
        return "Zustand" if any(path.startswith(r) for r in NON_CATALOG_ROOTS) else "Katalog"
    if c["kind"] == "Objektliste":
        return "Datensatz"
    return "Zuordnung"


def leaf(path: str) -> str:
    """Letztes benanntes Segment eines Pfades, ohne Indizes.

    Gross-/Kleinschreibung bleibt erhalten -- tokens() braucht das camelCase,
    um seenModifiers in seen + modifiers zu zerlegen.
    """
    seg = path.rstrip("]").split(".")[-1]
    return seg.split("[")[0]


def tokens(name: str) -> list[str]:
    """Zerlegt goodsTrends oder essential_buildings in ihre Woerter."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return [t for t in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if t]


def hit(name: str, hints: tuple[str, ...]) -> int:
    """0 = Wort trifft genau, 1 = Wort faengt so an, 2 = kein Treffer."""
    toks = tokens(name)
    if any(t == h for t in toks for h in hints):
        return 0
    if any(t.startswith(h) for t in toks for h in hints):
        return 1
    return 2


def verdict(all_catalogs: list[dict]) -> dict:
    """Pro SPEC-Tabelle: Vokabular da? Zahlen da? Sonst Wiki."""
    out: dict = {}
    for table, hints in KB_TABLES.items():
        # Der Hinweis muss im letzten Pfadsegment oder in den Feldnamen stehen.
        # Sonst zieht "$.gamesHistory.records" jede Tabelle an sich, weil
        # irgendwo darunter ein passendes Wort vorkommt.
        matches = []
        for c in all_catalogs:
            rank = min(hit(leaf(c["path"]), hints),
                       min((hit(k, hints) for k in c.get("entry_keys") or []), default=2))
            if rank < 2:
                c = dict(c, _hit=rank)
                matches.append(c)
        for c in matches:
            c["class"] = classify(c)
        usable = [c for c in matches if c["class"] in ("Katalog", "Datensatz", "Vokabular")]
        usable.sort(key=lambda c: (c["_hit"], -len(c.get("numeric") or []), -c["length"]))

        if not usable:
            other = ", ".join(sorted({c["class"] for c in matches}))
            reason = (f"nur {other} gefunden, kein Katalog" if other
                      else "kein passender Eintrag im Save")
            out[table] = {
                "status": "nicht gefunden",
                "note": f"{reason} -- Wiki bleibt noetig",
                "matches": [{k: v for k, v in m.items() if k != "ids"} for m in matches[:3]],
            }
            continue
        best = usable[0]
        if best["class"] == "Datensatz" and best.get("numeric"):
            status = "IDs und Zahlen"
            note = f"Zahlenfelder: {', '.join(best['numeric'][:8])}"
        elif best["class"] == "Datensatz" and best.get("attributes"):
            status = "IDs und Attribute"
            note = f"ohne Zahlen, aber: {', '.join(best['attributes'][:8])}"
        else:
            status, note = "nur IDs", "Vokabular aus dem Save, Zahlen aus dem Wiki"
        matches = usable
        out[table] = {
            "status": status, "note": note,
            "matches": [{k: v for k, v in m.items() if k != "ids"} for m in matches[:4]],
        }
    return out


def probe_file(path: Path, args) -> dict:
    raw = path.read_bytes()
    dec = decode_container(raw)
    info: dict = {"file": path.name, "size_mb": round(len(raw) / 1024 / 1024, 2),
                  "container": dec["container"]}
    if dec["payload"] is None:
        info["error"] = "nicht dekodierbar"
        return info
    try:
        data = json.loads(dec["payload"].decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        info["error"] = f"kein JSON: {exc.msg}"
        return info

    found = catalogs(data, args.min_len, args.max_nodes)
    info["catalogs"] = found
    info["top_level_keys"] = list(data)[:40] if isinstance(data, dict) else None
    return info


def render(report: dict) -> str:
    L: list[str] = []
    add = L.append
    add("=" * 78)
    add("KB-SONDE  taugt der Spielstand als Quelle fuer kb.sqlite?")
    add("=" * 78)
    add(f"Verzeichnis: {report.get('dir')}")
    add(f"Zeitpunkt  : {report['timestamp']}")

    for f in report["files"]:
        add("")
        add("-" * 78)
        add(f"{f['file']}  ({f.get('size_mb', '?')} MB, {f.get('container', '?')})")
        add("-" * 78)
        if "error" in f:
            add(f"  {f['error']}")
            continue
        cats = f["catalogs"]
        add(f"  {len(cats)} Strukturen mit mindestens {report['min_len']} Eintraegen")
        for c in cats[:25]:
            add("")
            add(f"  {c['path'][:70]}")
            add(f"    {c['kind']} [{classify(c)}], {c['length']} Eintraege, Tiefe {c['depth']}")
            if c["entry_keys"]:
                add(f"    Felder je Eintrag: {', '.join(c['entry_keys'][:14])}")
            if c["economic"]:
                add(f"    davon Zahlen/Wirtschaft: {', '.join(c['economic'][:10])}")
            for ex in c["examples"][:4]:
                add(f"    z. B. {ex}")

    add("")
    add("=" * 78)
    add("BEFUND JE TABELLE AUS SPEC.md PHASE 1")
    add("=" * 78)
    for table, v in report["verdict"].items():
        add(f"  {table:<14} {v['status']:<16} {v['note']}")
        for m in v["matches"][:2]:
            add(f"                 {m['path'][:64]}  ({m['length']} Eintraege)")
    add("")
    add("Lesart: 'IDs und Zahlen' heisst, der Save ersetzt das Wiki fuer diese")
    add("Tabelle. 'IDs und Attribute' heisst, er liefert Vokabular und Einordnung,")
    add("aber keine Kosten oder Rezepte. 'nur IDs' heisst, er liefert das")
    add("Vokabular und die IDs, die Zahlen kommen vom Wiki. 'nicht gefunden'")
    add("heisst: diese Tabelle muss ganz aus dem Wiki kommen.")
    add("=" * 78)
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", help="Save-Verzeichnis explizit angeben")
    ap.add_argument("--min-len", type=int, default=MIN_CATALOG, help=f"ab wie vielen Eintraegen ein Katalog (Vorgabe {MIN_CATALOG})")
    ap.add_argument("--max-nodes", type=int, default=3_000_000, help="Knotenobergrenze")
    ap.add_argument("--dump-ids", action="store_true", help="gefundene ID-Listen als Textdateien ablegen")
    ap.add_argument("--out", default="diagnostics", help="Ausgabeverzeichnis")
    args = ap.parse_args(argv)

    directory, tried = resolve_dir(args.dir)
    if directory is None:
        print("Kein Save-Verzeichnis gefunden. Gesucht in:")
        for t in tried:
            print(f"  [{'x' if t['exists'] else ' '}] {t['path']}")
        return 1

    wanted = {"save.save", "worldsave.save", "metasave.save"}
    targets = [p for p in list_save_files(directory) if p.name.lower() in wanted]
    report: dict = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "dir": str(directory),
        "min_len": args.min_len,
        "files": [],
    }
    for p in targets:
        try:
            report["files"].append(probe_file(p, args))
        except Exception as exc:
            report["files"].append({"file": p.name, "error": f"{type(exc).__name__}: {exc}"})

    every = [c for f in report["files"] for c in f.get("catalogs", [])]
    report["verdict"] = verdict(every)

    text = render(report)
    print(text)

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (outdir / f"kb-probe-{stamp}.txt").write_text(text, encoding="utf-8")
    slim = json.loads(json.dumps(report, default=str))
    for f in slim["files"]:
        for c in f.get("catalogs", []):
            c.pop("ids", None)
    (outdir / f"kb-probe-{stamp}.json").write_text(
        json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nBericht geschrieben: {outdir / f'kb-probe-{stamp}.txt'}")

    if args.dump_ids:
        iddir = outdir / f"ids-{stamp}"
        iddir.mkdir(parents=True, exist_ok=True)
        written = 0
        for f in report["files"]:
            for c in f.get("catalogs", []):
                ids = [i for i in (c.get("ids") or []) if isinstance(i, str)]
                if len(ids) < args.min_len:
                    continue
                safe = c["path"].replace("$", "root").replace(".", "_").replace("[", "_").replace("]", "")
                name = f"{Path(f['file']).stem}__{safe[:80]}.txt"
                (iddir / name).write_text("\n".join(dict.fromkeys(ids)), encoding="utf-8")
                written += 1
        print(f"ID-Listen abgelegt: {written} Dateien in {iddir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
