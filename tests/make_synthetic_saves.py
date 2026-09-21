#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Erzeugt synthetische Save-Dateien, um tools/phase0_diagnose.py zu pruefen,
solange keine echten Spielstaende vorliegen.

Die Struktur ist erfunden und bildet nur die Form ab, die das Diagnoseskript
erkennen koennen muss: gzip-JSON mit englischen IDs, unkomprimiertes JSON mit
lokalisierten Strings, und ein undekodierbarer Binaerklumpen.

    python tests/make_synthetic_saves.py /tmp/fake-saves
"""

from __future__ import annotations

import gzip
import json
import os
import random
import sys
from pathlib import Path

RESOURCES = ["Amber", "Parts", "Berries", "Jerky", "Wood", "Planks", "Ale", "Incense"]
RACES = ["Human", "Beaver", "Lizard", "Harpy", "Fox", "Frog"]
BUILDINGS = ["Sawmill", "Woodcutters Camp", "Trapper Camp", "Makeshift Post", "Manor House"]
PREFIXED_GOODS = [
    ("Mat Raw", "Wood"), ("Mat Processed", "Bricks"), ("Food Raw", "Meat"),
    ("Food Raw", "Vegetables"), ("Food Complex", "Jerky"), ("Metal", "Crystalized Dew"),
    ("Crafting", "Coal"), ("Trade", "Amber"),
]


def english_state(seed: int = 7) -> dict:
    """Form nach den Behauptungen der beigelegten Recherche.

    Kategoriepraefixe vor den Waren-IDs, gameObjectives.reputationPenalty fuer
    die Ungeduld, reputationSources als Vierervektor. Das ist erfunden und
    belegt nichts ueber das echte Spiel; es sorgt nur dafuer, dass die
    Gegenprobe im Diagnoseskript beide Ausgaenge zeigt: bestaetigt und
    nicht gefunden.
    """
    rng = random.Random(seed)
    return {
        "saveVersion": "1.10.4",
        "gameId": "9f2c1a44-1d0e-4f21-9b6b-7a0b2f3c4d55",
        "nextGoodsPerMinTick": 4821.5,
        "gameObjectives": {"reputationPenalty": 8.5, "reputationPoints": 11.0},
        "reputationSources": [0.5, 2.0, 1.25, 0.0],
        "racesReputationGains": {"Human": 2.45, "Beaver": 1.1, "Harpy": 3.0},
        "producedGoods": {"[Mat Processed] Planks": 240, "[Food Complex] Jerky": 180},
        "worldState": {
            "biome": "Coral Forest",
            "year": 2,
            "season": "Storm",
            "seasonTimeLeft": 118.5,
            "prestigeLevel": 13,
            "worldModifiers": [{"name": "DoubledBlightrot", "value": 2.0}],
        },
        "settlementState": {
            "hostility": 7,
            "impatience": 21,
            "reputation": 4.25,
            "villagers": [
                {"race": rng.choice(RACES), "resolve": rng.randint(8, 22), "workplaceId": rng.randint(1, 40)}
                for _ in range(60)
            ],
            "storage": {
                "goods": [
                    {"Key": f"[{cat}] {name}", "Value": rng.randint(0, 250)}
                    for cat, name in PREFIXED_GOODS
                ]
            },
            "buildings": [
                {"model": b, "workers": rng.randint(0, 3), "buildingProgress": 1.0,
                 "position": {"x": rng.randint(0, 60), "y": rng.randint(0, 60)}}
                for b in BUILDINGS
            ],
            "glades": [{"id": i, "type": rng.choice(["Small", "Dangerous", "Forbidden"]), "discovered": i < 5} for i in range(12)],
            "deposits": [{"model": "BerryBush", "charges": rng.randint(0, 8), "gladeId": i} for i in range(12)],
            "cornerstones": ["AmberFever", "TradersLuck"],
            "orders": [{"id": "Order_Food_01", "completed": False}],
        },
    }


def german_state() -> dict:
    return {
        "saveVersion": "1.10.4",
        "worldState": {"biome": "Königswälder", "year": 1, "season": "Sturm"},
        "settlementState": {
            "hostility": 3,
            "impatience": 5,
            "villagers": [{"race": "Biber", "resolve": 12, "note": "Entschlossenheit stabil"}],
            "storage": {"Bernstein": 40, "Teile": 12, "Nahrung": 210},
            "buildings": [{"model": "Sägewerk", "workers": 2}, {"model": "Primitive Werkbank", "workers": 1}],
            "cornerstones": ["Gutsgericht"],
        },
    }


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fake-saves")
    out.mkdir(parents=True, exist_ok=True)

    (out / "Save.save").write_bytes(
        gzip.compress(json.dumps(english_state(), ensure_ascii=False, indent=1).encode("utf-8"))
    )
    (out / "MetaSave.save").write_bytes(
        json.dumps(german_state(), ensure_ascii=False, indent=1).encode("utf-8")
    )
    (out / "Opaque.save").write_bytes(bytes(os.urandom(4096)))
    print(f"Synthetische Saves in {out}: " + ", ".join(sorted(p.name for p in out.iterdir())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
