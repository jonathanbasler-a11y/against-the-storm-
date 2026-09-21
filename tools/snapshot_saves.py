#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sichert den aktuellen Spielstand als Testdatensatz, bevor er ueberschrieben wird.

SPEC.md verlangt fuer Phase 2 Tests mit echten Beispieldaten und als
Abnahmekriterium einen geladenen Spielstand, dessen Zahlen mit dem
uebereinstimmen, was im Spiel steht. Dafuer braucht es echte Dateien -- und
Save.save ueberlebt die naechste Einschiffung nicht.

Kopiert Save.save, WorldSave.save, MetaSave.save und die zugehoerigen Backups
in einen Ordner mit Zeitstempel und legt eine Beschreibung dazu: Groessen,
Aenderungszeitpunkte, Pruefsummen und die Kennzahlen des Laufs, damit spaeter
erkennbar ist, was dieser Datensatz ueberhaupt zeigt.

    python tools/snapshot_saves.py
    python tools/snapshot_saves.py --label prestige13-gewonnen
    python tools/snapshot_saves.py --out D:/ats-fixtures

Kopiert nur, aendert nichts im Spielordner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase0_diagnose import decode_container, list_save_files, resolve_dir  # noqa: E402

WANTED = (
    "save.save", "save_backup.save",
    "worldsave.save", "worldsave_backup.save",
    "metasave.save", "metasave_backup.save",
    "metasave_gamewonbackup.save", "metasave_lastsuccessful.save",
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def load(path: Path):
    dec = decode_container(path.read_bytes())
    if dec["payload"] is None:
        return None
    try:
        return json.loads(dec["payload"].decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def describe_run(saves: dict[str, Path]) -> dict:
    """Kennzahlen, die den Datensatz spaeter wiedererkennbar machen."""
    out: dict = {}

    save = saves.get("Save.save")
    if save:
        data = load(save)
        if isinstance(data, dict):
            out["siedlung"] = {
                k: data.get(k) for k in ("time", "year", "season") if k in data
            }
            for key in ("reputation", "reputationPenalty", "reputationToWin"):
                if key in data:
                    out.setdefault("siedlung", {})[key] = data[key]

    meta = saves.get("MetaSave.save")
    if meta:
        data = load(meta)
        records = (((data or {}).get("gamesHistory") or {}).get("records")) or []
        if records:
            newest = max(records, key=lambda r: r.get("endTimestamp") or 0)
            out["letzter_lauf"] = {
                k: newest.get(k) for k in
                ("hasWon", "difficulty", "biome", "years", "gameTime",
                 "tradeValueInAmbers", "hearthCorruptedAmount", "endTimestamp")
                if k in newest
            }
            out["laeufe_gesamt"] = len(records)
            out["davon_gewonnen"] = sum(1 for r in records if r.get("hasWon"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", help="Save-Verzeichnis explizit angeben")
    ap.add_argument("--out", default="snapshots", help="Zielverzeichnis (Vorgabe: snapshots/)")
    ap.add_argument("--label", default="", help="Kurzer Name, der in den Ordnernamen wandert")
    args = ap.parse_args(argv)

    directory, tried = resolve_dir(args.dir)
    if directory is None:
        print("Kein Save-Verzeichnis gefunden. Gesucht in:")
        for t in tried:
            print(f"  [{'x' if t['exists'] else ' '}] {t['path']}")
        return 1

    found = {p.name: p for p in list_save_files(directory) if p.name.lower() in WANTED}
    if not found:
        print(f"Keine Spielstandsdateien in {directory}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-{args.label}" if args.label else stamp
    target = Path(args.out) / name
    target.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "erstellt": datetime.now(timezone.utc).isoformat(),
        "quelle": str(directory),
        "label": args.label,
        "dateien": [],
    }
    total = 0
    for fname, src in sorted(found.items()):
        stat = src.stat()
        shutil.copy2(src, target / fname)
        total += stat.st_size
        manifest["dateien"].append({
            "name": fname,
            "bytes": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "sha256_16": digest(src),
        })
        print(f"  kopiert  {fname:<34} {stat.st_size:>12,} B")

    manifest["kennzahlen"] = describe_run(found)
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{len(found)} Dateien, {total / 1024 / 1024:.1f} MB nach {target}")
    k = manifest["kennzahlen"]
    if k.get("letzter_lauf"):
        r = k["letzter_lauf"]
        print(f"Letzter abgeschlossener Lauf: {'GEWONNEN' if r.get('hasWon') else 'verloren'}, "
              f"Biom {r.get('biome')}, Prestige {r.get('difficulty')}, {r.get('years')} Jahre")
        print(f"Laufhistorie: {k.get('laeufe_gesamt')} Eintraege, davon {k.get('davon_gewonnen')} gewonnen")
    if k.get("siedlung"):
        print(f"Laufende Siedlung: {k['siedlung']}")
    print("\nDie Kopien bleiben lokal. Sie enthalten deine Spieldaten -- vor einem")
    print("Commit ins oeffentliche Repo ueberlegen, was davon hineingehoert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
