#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase-0-Diagnose fuer den Against-the-Storm-Assistenten.

Beantwortet die drei Fragen aus SPEC.md Phase 0:

  1. Save-Format    -> Container erkennen (JSON / gzip / zip / zlib / unbekannt),
                       bei unbekannt Hexdump der ersten 256 Bytes + Formathypothese.
  2. Schreibzeitpunkt -> mtime-Protokoll ueber N Minuten, Intervalle auswerten.
  3. Sprache        -> stehen im Save englische IDs oder lokalisierte deutsche Strings?

Zusaetzlich (kostet nichts, spart spaeter Arbeit): Schluesselindex und Feldsuche
fuer die GameState-Felder aus Phase 2, damit die Entscheidungsvorlage beziffern
kann, wie viel der Parser ueberhaupt abdeckt.

Nur Standardbibliothek, keine Abhaengigkeiten. Laeuft unter Windows und Linux.
Schreibt nichts in den Spielordner, oeffnet die Dateien ausschliesslich lesend.

Beispiele:
    python tools/phase0_diagnose.py inspect
    python tools/phase0_diagnose.py watch --minutes 10
    python tools/phase0_diagnose.py all --minutes 10
    python tools/phase0_diagnose.py inspect --dir "D:/pfad/zum/ordner"
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import re
import statistics
import sys
import time
import zlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

# --------------------------------------------------------------------------
# Fundorte
# --------------------------------------------------------------------------

SAVE_SUBPATH = Path("AppData") / "LocalLow" / "Eremite Games" / "Against the Storm"

# Steam-AppID von Against the Storm, fuer Proton-Praefixe unter Linux.
PROTON_APPID = "1336490"


def candidate_dirs() -> list[Path]:
    """Mutmassliche Speicherorte, plattformabhaengig, ohne Existenzpruefung."""
    out: list[Path] = []
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        out.append(Path(userprofile) / SAVE_SUBPATH)
    out.append(Path.home() / SAVE_SUBPATH)

    if platform.system() != "Windows":
        # Proton/Wine: das Spiel liegt im Windows-Praefix.
        for steam_root in (
            Path.home() / ".steam" / "steam",
            Path.home() / ".local" / "share" / "Steam",
            Path.home() / "snap" / "steam" / "common" / ".steam" / "steam",
        ):
            out.append(
                steam_root
                / "steamapps"
                / "compatdata"
                / PROTON_APPID
                / "pfx"
                / "drive_c"
                / "users"
                / "steamuser"
                / SAVE_SUBPATH
            )
        out.append(Path.home() / ".wine" / "drive_c" / "users" / os.environ.get("USER", "user") / SAVE_SUBPATH)

    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        key = str(p)
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def resolve_dir(explicit: str | None) -> tuple[Path | None, list[dict]]:
    """Liefert den ersten existierenden Kandidaten plus Protokoll aller Versuche."""
    tried: list[dict] = []
    cands = [Path(explicit).expanduser()] if explicit else candidate_dirs()
    found: Path | None = None
    for c in cands:
        exists = c.is_dir()
        tried.append({"path": str(c), "exists": exists})
        if exists and found is None:
            found = c
    return found, tried


# Die drei Dateien, um die es geht: laufende Siedlung, Weltkarte,
# Metafortschritt. Alles andere ist Beiwerk und darf sie nicht aus der
# Auswahl draengen -- alphabetisch stehen CustomGamesLayout und die neun
# MetaSave-Varianten vor Save.save.
PRIORITY_NAMES = ("save.save", "worldsave.save", "metasave.save")


def select_targets(files: list[Path], max_files: int) -> tuple[list[Path], list[Path]]:
    """Wichtige Dateien zuerst, Rest bis zur Obergrenze, Weggelassene zurueck."""
    prio = [p for p in files if p.name.lower() in PRIORITY_NAMES]
    rest = [p for p in files if p.name.lower() not in PRIORITY_NAMES]
    ordered = prio + rest
    cap = max(max_files, len(prio))
    return ordered[:cap], ordered[cap:]


def list_save_files(directory: Path) -> list[Path]:
    """Alle Save-artigen Dateien, bis zwei Ebenen tief (Profile/Backups)."""
    hits: list[Path] = []
    for pattern in ("*", "*/*", "*/*/*"):
        for p in sorted(directory.glob(pattern)):
            if p.is_file():
                hits.append(p)
    interesting = [p for p in hits if p.suffix.lower() in {".save", ".json", ".dat", ".bak"} or "save" in p.name.lower()]
    return interesting or hits


# --------------------------------------------------------------------------
# Frage 1: Container erkennen
# --------------------------------------------------------------------------

MAGIC = [
    (b"\x1f\x8b", "gzip"),
    (b"PK\x03\x04", "zip"),
    (b"\x04\x22\x4d\x18", "lz4-frame"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"BZh", "bzip2"),
    (b"\x28\xb5\x2f\xfd", "zstd"),
    (b"\x5d\x00\x00", "lzma-alone"),
    (b"UnityFS", "unity-bundle"),
    (b"\x00\x01\x00\x00", "unity-serialized?"),
]

ZLIB_FIRST_BYTES = {b"\x78\x01", b"\x78\x5e", b"\x78\x9c", b"\x78\xda"}


def hexdump(data: bytes, length: int = 256) -> str:
    lines = []
    chunk = data[:length]
    for off in range(0, len(chunk), 16):
        row = chunk[off : off + 16]
        hexpart = " ".join(f"{b:02x}" for b in row)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        lines.append(f"{off:08x}  {hexpart:<47}  |{asc}|")
    return "\n".join(lines)


def printable_ratio(data: bytes) -> float:
    if not data:
        return 0.0
    ok = sum(1 for b in data if 32 <= b < 127 or b in (9, 10, 13))
    return ok / len(data)


def decode_container(raw: bytes) -> dict:
    """Erkennt den Container und liefert, falls moeglich, die Nutzdaten."""
    result: dict = {"container": "unbekannt", "payload": None, "notes": []}
    head = raw[:16]

    stripped = raw.lstrip(b" \t\r\n")
    if stripped.startswith(b"\xef\xbb\xbf"):  # UTF-8-BOM
        stripped = stripped[3:].lstrip(b" \t\r\n")
    if stripped[:1] in (b"{", b"["):
        result["container"] = "plain-json"
        result["payload"] = raw
        return result

    for magic, name in MAGIC:
        if raw.startswith(magic):
            result["container"] = name
            break

    if result["container"] == "gzip":
        try:
            result["payload"] = gzip.decompress(raw)
        except OSError as exc:  # defekt oder mehrteilig
            result["notes"].append(f"gzip.decompress fehlgeschlagen: {exc}")
    elif result["container"] == "zip":
        try:
            import zipfile
            import io as _io

            with zipfile.ZipFile(_io.BytesIO(raw)) as zf:
                names = zf.namelist()
                result["notes"].append(f"Zip-Eintraege: {names[:10]}")
                if names:
                    result["payload"] = zf.read(names[0])
        except Exception as exc:
            result["notes"].append(f"Zip-Lesen fehlgeschlagen: {exc}")
    elif result["container"] == "unbekannt":
        if head[:2] in ZLIB_FIRST_BYTES:
            try:
                result["payload"] = zlib.decompress(raw)
                result["container"] = "zlib"
            except zlib.error as exc:
                result["notes"].append(f"zlib.decompress fehlgeschlagen: {exc}")
        if result["payload"] is None:
            # roher Deflate-Strom ohne Header
            try:
                result["payload"] = zlib.decompressobj(-zlib.MAX_WBITS).decompress(raw)
                if result["payload"]:
                    result["container"] = "raw-deflate"
            except zlib.error:
                result["payload"] = None
        if result["payload"] is None:
            # Unity/Eremite legen manchmal einen kleinen Header vor den Strom.
            for off in range(1, min(64, len(raw))):
                if raw[off : off + 2] == b"\x1f\x8b":
                    try:
                        result["payload"] = gzip.decompress(raw[off:])
                        result["container"] = f"gzip+{off}-byte-header"
                        result["notes"].append(f"gzip-Magic erst ab Offset {off}")
                        break
                    except OSError:
                        continue

    if result["payload"] is None and result["container"] == "unbekannt":
        result["notes"].append(
            "Kein bekannter Container. Hypothese anhand Hexdump und Druckbarkeitsanteil bilden."
        )
    return result


def format_hypothesis(raw: bytes) -> list[str]:
    """Formathypothesen fuer den Fall, dass nichts dekodiert werden konnte."""
    out: list[str] = []
    ratio = printable_ratio(raw[:4096])
    out.append(f"Druckbarkeitsanteil der ersten 4 KiB: {ratio:.0%}")
    if ratio > 0.85:
        out.append("Hoher Textanteil: vermutlich Text/JSON mit Praefix oder eigenem Textformat.")
    else:
        out.append("Ueberwiegend Binaer: Kompression oder binaere Serialisierung wahrscheinlich.")
    if b"UnityFS" in raw[:4096]:
        out.append("Unity-Assetbundle-Magic gefunden.")
    if re.search(rb"[A-Za-z]{4,}\.[A-Za-z]{4,}", raw[:8192]):
        out.append("Namensraum-artige ASCII-Laeufe: moeglicherweise .NET/Unity-Binaerserialisierung.")
    if raw[:1] in (b"\x82", b"\x83", b"\x84", b"\xde", b"\xdf"):
        out.append("Erstes Byte passt zu MessagePack-Map.")
    if len(raw) > 4 and int.from_bytes(raw[:4], "little") in range(len(raw) - 64, len(raw) + 64):
        out.append("Erste 4 Bytes entsprechen etwa der Dateilaenge: Laengenpraefix wahrscheinlich.")
    return out


# --------------------------------------------------------------------------
# JSON-Analyse: Schluesselindex, Feldsuche, Sprachprobe
# --------------------------------------------------------------------------

GERMAN_SEEDS = [
    "Entschlossenheit", "Ungeduld", "Grundstein", "Bernstein", "Teile",
    "Schwelende Stadt", "Uralte Feuerstelle", "Gefaehrliche Lichtung", "Gefährliche Lichtung",
    "Komplexe Nahrung", "Dienste", "Koenigswaelder", "Königswälder", "Felsschlucht",
    "Bambusebene", "Saegewerk", "Sägewerk", "Primitive Werkbank", "Trapperlager",
    "Fluffschnabel", "Gutsgericht", "Nahrung", "Jahreszeit", "Lichtung",
]

ENGLISH_SEEDS = [
    "Resolve", "Impatience", "Cornerstone", "Amber", "Parts", "Hostility",
    "Reputation", "Sawmill", "Woodcutter", "Beaver", "Harpy", "Lizard",
    "Human", "Fox", "Frog", "Glade", "Hearth", "Blightrot", "Smoldering City",
]

# Welche GameState-Felder aus Phase 2 finden wir im Save wieder?
FIELD_HINTS: dict[str, list[str]] = {
    "Biom": ["biome"],
    "Jahr / Jahreszeit / Restzeit": ["year", "season", "gametime", "timeleft", "daytime", "cycle"],
    "Prestige-Stufe": ["prestige", "difficulty"],
    "Weltmodifikatoren": ["modifier", "worldmodifier", "worldevent"],
    "Bevoelkerung je Spezies": ["villager", "population", "race", "species"],
    "Entschlossenheit": ["resolve"],
    "Feindseligkeit": ["hostility"],
    # Das Spiel nennt die Ungeduld "reputationPenalty" -- mit "impatience"
    # allein findet die Feldsuche sie nicht.
    "Ungeduld": ["impatience", "reputationpenalty"],
    "Reputation": ["reputation"],
    "Lagerbestaende": ["storage", "goods", "resourcesamount", "stock", "warehouse"],
    "Gebaeude + Arbeiter": ["building", "worker", "workplace", "employee"],
    "Entdeckte Lichtungen": ["glade", "field", "clearing"],
    "Vorkommen + Restladungen": ["deposit", "node", "charges", "resourcedeposit"],
    "Gewaehlte Grundsteine": ["cornerstone", "perk"],
    "Auftraege / Orders": ["order", "quest", "goal"],
    "Spielgeschwindigkeit": ["speed", "timescale"],
}

# Eine moeglichst monoton laufende Spieluhr. seasonTimeLeft zaehlt rueckwaerts
# und springt beim Jahreszeitenwechsel -- als Uhr taugt es nicht, deshalb
# steht es hinten.
CLOCK_KEYS = ("gametime", "totalgametime", "totaltime", "playtime", "elapsedtime", "time")


def walk_json(obj, max_nodes: int, max_strings: int) -> dict:
    """Ein Durchlauf, iterativ: Schluesselzaehlung, Beispielpfade, Stringprobe."""
    key_counts: Counter = Counter()
    key_example: dict[str, dict] = {}
    strings: list[str] = []
    seen_strings: set[str] = set()
    max_depth = 0
    nodes = 0
    truncated = False

    stack = [(obj, "$", 0)]
    while stack:
        node, path, depth = stack.pop()
        nodes += 1
        max_depth = max(max_depth, depth)
        if nodes > max_nodes:
            truncated = True
            break
        if isinstance(node, dict):
            for k, v in node.items():
                key_counts[k] += 1
                # Flachster Fund gewinnt: ein "season" tief in einer Vorlage
                # sagt nichts, ein "season" nahe der Wurzel ist der Wert, den
                # das Spiel fuehrt.
                seen = key_example.get(k)
                if seen is None or depth + 1 < seen["depth"]:
                    key_example[k] = {"path": f"{path}.{k}", "preview": preview(v),
                                      "depth": depth + 1}
                stack.append((v, f"{path}.{k}", depth + 1))
        elif isinstance(node, list):
            for i, v in enumerate(node[:200]):
                stack.append((v, f"{path}[{i}]", depth + 1))
            if len(node) > 200:
                truncated = True
        elif isinstance(node, str):
            s = node.strip()
            if 2 <= len(s) <= 80 and s not in seen_strings and len(strings) < max_strings:
                seen_strings.add(s)
                strings.append(s)

    return {
        "nodes_visited": nodes,
        "max_depth": max_depth,
        "truncated": truncated,
        "key_counts": key_counts,
        "key_example": key_example,
        "strings": strings,
    }


def preview(value, limit: int = 120) -> str:
    try:
        if isinstance(value, (dict, list)):
            kind = "dict" if isinstance(value, dict) else "list"
            return f"<{kind} len={len(value)}>"
        text = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def sketch(obj, depth: int = 0, max_depth: int = 3) -> object:
    """Kompakte Strukturskizze der obersten Ebenen."""
    if depth >= max_depth:
        return preview(obj, 60)
    if isinstance(obj, dict):
        out = {}
        for i, (k, v) in enumerate(obj.items()):
            if i >= 40:
                out["..."] = f"+{len(obj) - 40} weitere Schluessel"
                break
            out[k] = sketch(v, depth + 1, max_depth)
        return out
    if isinstance(obj, list):
        if not obj:
            return "<list len=0>"
        return {"<list>": len(obj), "[0]": sketch(obj[0], depth + 1, max_depth)}
    return preview(obj, 60)


def field_report(key_counts: Counter, key_example: dict) -> dict:
    lowered = {k.lower(): k for k in key_counts}
    report: dict = {}
    for label, hints in FIELD_HINTS.items():
        hits = []
        for low, orig in lowered.items():
            matched = [h for h in hints if h in low]
            if not matched:
                continue
            # Ein Schluessel, der genau so heisst wie der Hinweis, ist
            # aussagekraeftiger als einer, der ihn nur enthaelt.
            exact = 0 if low in hints else (1 if any(low.startswith(h) for h in matched) else 2)
            hits.append(
                {
                    "key": orig,
                    "count": key_counts[orig],
                    "path": key_example[orig]["path"],
                    "preview": key_example[orig]["preview"],
                    "depth": key_example[orig]["depth"],
                    "_rank": exact,
                }
            )
        hits.sort(key=lambda h: (h["_rank"], h["depth"], -h["count"]))
        report[label] = hits[:6]
    return report


def language_probe(strings: list[str]) -> dict:
    blob = "\n".join(strings)
    de_hits = sorted({s for s in GERMAN_SEEDS if s in blob})
    en_hits = sorted({s for s in ENGLISH_SEEDS if re.search(rf"\b{re.escape(s)}\b", blob)})
    umlauts = sum(1 for s in strings if re.search(r"[äöüÄÖÜß]", s))
    id_like = sum(1 for s in strings if re.fullmatch(r"[A-Za-z][A-Za-z0-9_\- ]{2,40}", s))
    guid_like = sum(1 for s in strings if re.fullmatch(r"[0-9a-fA-F\-]{16,40}", s))

    if de_hits and not en_hits:
        verdict = "lokalisierte deutsche Strings"
    elif en_hits and not de_hits:
        verdict = "englische IDs"
    elif en_hits and de_hits:
        verdict = "gemischt (englische IDs plus lokalisierte Texte)"
    else:
        verdict = "unklar, zu wenig Treffer in der Stringprobe"

    return {
        "verdict": verdict,
        "german_hits": de_hits,
        "english_hits": en_hits,
        "strings_sampled": len(strings),
        "strings_with_umlauts": umlauts,
        "id_like_strings": id_like,
        "guid_like_strings": guid_like,
        "sample": strings[:40],
    }


# --------------------------------------------------------------------------
# Gegenprobe zur Recherche
# --------------------------------------------------------------------------
#
# Die beigelegte Recherche (Bewertung in docs/RESEARCH-REVIEW.md) behauptet
# konkrete Pfade, ein konkretes Format und einen konkreten Schreibtakt. Das
# sind Hypothesen, keine Messungen. Der Spielstand kann sie selbst
# bestaetigen oder widerlegen, also prueft der inspect-Lauf sie gleich mit.

CLAIMED_PATHS: dict[str, str] = {
    "Ungeduld": "gameObjectives.reputationPenalty",
    "Reputationskanaele": "reputationSources",
    "Reputation je Spezies": "racesReputationGains",
    "Lagerbestand": "storage.goods",
    "Produktionshistorie": "producedGoods",
    "Gebaeude": "buildings",
    "Simulationsuhr": "nextGoodsPerMinTick",
}

# "250.000 bis 350.000 Zeilen unkomprimiertes UTF-8-JSON, rund 30 MB"
CLAIMED_LINES = (250_000, 350_000)
CLAIMED_CONTAINER = "plain-json"

# "rollender Heartbeat alle 120 bis 180 Sekunden"
CLAIMED_HEARTBEAT = (120.0, 180.0)

# "[Food Raw] Meat", "[Mat Processed] Bricks": Kategoriepraefix vor der ID.
# Traegt die Behauptung, wird der Parser genau hier ansetzen.
PREFIX_RE = re.compile(r"^\[([A-Za-z][A-Za-z ]*)\]\s*(\S.*)$")


def path_lookup(data, dotted: str) -> tuple[bool, object]:
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


def prefix_scan(key_counts: Counter, strings: list[str]) -> dict:
    cats: Counter = Counter()
    examples: list[str] = []
    for text in list(key_counts) + strings:
        m = PREFIX_RE.match(text)
        if m:
            cats[m.group(1)] += 1
            if len(examples) < 12:
                examples.append(text)
    return {
        "matches": sum(cats.values()),
        "categories": cats.most_common(20),
        "examples": examples,
        "verdict": "bestaetigt" if cats else "nicht gefunden",
    }


def check_research_claims(data, walked: dict, info: dict) -> dict:
    lowered = {k.lower(): k for k in walked["key_counts"]}
    paths: dict[str, dict] = {}
    for label, dotted in CLAIMED_PATHS.items():
        exact, value = path_lookup(data, dotted)
        leaf = dotted.split(".")[-1]
        if exact:
            paths[label] = {"claim": dotted, "status": "bestaetigt", "evidence": preview(value)}
        elif leaf.lower() in lowered:
            orig = lowered[leaf.lower()]
            ex = walked["key_example"][orig]
            paths[label] = {
                "claim": dotted,
                "status": "anderer Pfad",
                "evidence": f"{ex['path']} = {ex['preview']}",
            }
        else:
            paths[label] = {"claim": dotted, "status": "nicht gefunden", "evidence": ""}

    lines = info.get("payload_lines")
    if lines is None:
        size_status = "nicht pruefbar"
    elif CLAIMED_LINES[0] <= lines <= CLAIMED_LINES[1]:
        size_status = "bestaetigt"
    else:
        size_status = "abweichend"

    container_status = "bestaetigt" if info.get("container") == CLAIMED_CONTAINER else "abweichend"

    confirmed = sum(1 for v in paths.values() if v["status"] == "bestaetigt")
    return {
        "paths": paths,
        "paths_confirmed": confirmed,
        "paths_total": len(paths),
        "prefix_convention": prefix_scan(walked["key_counts"], walked["strings"]),
        "size": {
            "claim": f"{CLAIMED_LINES[0]:,} bis {CLAIMED_LINES[1]:,} Zeilen",
            "measured": lines,
            "status": size_status,
        },
        "container": {"claim": CLAIMED_CONTAINER, "measured": info.get("container"), "status": container_status},
    }


# --------------------------------------------------------------------------
# Frage 1 + 3: inspect
# --------------------------------------------------------------------------


def inspect_file(path: Path, args) -> dict:
    stat = path.stat()
    info: dict = {
        "file": str(path),
        "name": path.name,
        "size_bytes": stat.st_size,
        "size_mb": round(stat.st_size / 1024 / 1024, 2),
        "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }
    with path.open("rb") as fh:
        raw = fh.read()

    dec = decode_container(raw)
    info["container"] = dec["container"]
    info["container_notes"] = dec["notes"]
    info["first_256_bytes_hex"] = hexdump(raw, 256)

    payload = dec["payload"]
    if payload is None:
        info["decoded"] = False
        info["hypothesis"] = format_hypothesis(raw)
        return info

    info["decoded"] = True
    info["payload_bytes"] = len(payload)
    info["payload_mb"] = round(len(payload) / 1024 / 1024, 2)
    info["compression_ratio"] = round(len(payload) / max(stat.st_size, 1), 2)

    try:
        text = payload.decode("utf-8")
        info["encoding"] = "utf-8"
    except UnicodeDecodeError:
        text = payload.decode("utf-8", errors="replace")
        info["encoding"] = "utf-8 mit Ersetzungen"
    info["payload_lines"] = text.count("\n") + 1
    info["payload_head"] = text[:400]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        info["json"] = False
        info["json_error"] = f"{exc.msg} (Zeile {exc.lineno}, Spalte {exc.colno})"
        return info

    info["json"] = True
    info["top_level_keys"] = list(data)[:60] if isinstance(data, dict) else f"<{type(data).__name__}>"
    info["structure_sketch"] = sketch(data, max_depth=args.sketch_depth)

    walked = walk_json(data, args.max_nodes, args.max_strings)
    info["nodes_visited"] = walked["nodes_visited"]
    info["max_depth"] = walked["max_depth"]
    info["walk_truncated"] = walked["truncated"]
    info["distinct_keys"] = len(walked["key_counts"])
    info["most_common_keys"] = walked["key_counts"].most_common(30)
    info["fields"] = field_report(walked["key_counts"], walked["key_example"])
    info["language"] = language_probe(walked["strings"])
    info["research"] = check_research_claims(data, walked, info)
    return info


def cmd_inspect(args) -> dict:
    directory, tried = resolve_dir(args.dir)
    out: dict = {"tried_dirs": tried, "dir": str(directory) if directory else None, "files": []}
    if directory is None:
        out["error"] = (
            "Kein Save-Verzeichnis gefunden. Mit --dir einen Pfad angeben, z. B. "
            r'--dir "%USERPROFILE%\AppData\LocalLow\Eremite Games\Against the Storm"'
        )
        return out

    files = list_save_files(directory)
    out["dir_listing"] = [
        {"name": str(p.relative_to(directory)), "size_bytes": p.stat().st_size,
         "mtime": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}
        for p in files
    ]
    targets, skipped = select_targets(files, args.max_files)
    out["skipped"] = [p.name for p in skipped]
    for p in targets:
        try:
            out["files"].append(inspect_file(p, args))
        except Exception as exc:  # Diagnose darf nie hart abbrechen
            out["files"].append({"file": str(p), "error": f"{type(exc).__name__}: {exc}"})
    return out


# --------------------------------------------------------------------------
# Frage 2: watch
# --------------------------------------------------------------------------


# Welche Werte bei jedem Schreibvorgang mitprotokolliert werden. Damit wird
# aus "hat um 19:31:56 geschrieben" ein "hat beim Wechsel in die Auslichtung
# geschrieben" -- und erst das beantwortet, ob der Parser einen Live-Strom
# bekommt oder Standbilder.
PROBE_LABELS = (
    "Jahr / Jahreszeit / Restzeit",
    "Feindseligkeit",
    "Ungeduld",
    "Reputation",
    "Bevoelkerung je Spezies",
)

PROBE_MAX_BYTES = 64 * 1024 * 1024

# Wie weit Schreibvorgaenge auseinanderliegen duerfen und noch als ein Bündel
# gelten. Gemessen wurden 2,02 Sekunden zwischen MetaSave und Save -- mit zwei
# Sekunden Fenster faellt genau die Datei heraus, um die es geht.
CO_WRITE_WINDOW = 5.0


def series_fingerprint(data, max_depth: int = 4) -> dict:
    """Findet Zeitreihen und merkt sich Laenge und Ende.

    Save.save fuehrt unter trends.goodsTrends je Ware eine Reihe von 180
    Werten. Wie schnell die weiterrueckt, entscheidet, wie fein
    food_forecast rechnen kann -- also wird bei jedem Schreibvorgang das
    Ende der Reihe festgehalten und beim naechsten verglichen.
    """
    out: dict = {}
    stack = [(data, "$", 0)]
    while stack and len(out) < 4:
        node, path, depth = stack.pop()
        if depth > max_depth or not isinstance(node, dict):
            continue
        vals = list(node.values())
        if len(node) >= 3 and vals and all(
            isinstance(v, list) and len(v) >= 10 and all(isinstance(x, (int, float)) for x in v[:5])
            for v in vals[:8]
        ):
            # Nicht die erste Reihe als Beispiel nehmen, sondern die
            # lebendigste: eine Ware, die nie produziert wird, steht konstant
            # auf einem Wert und meldet faelschlich "unveraendert".
            def liveliness(k):
                v = node[k]
                return len(set(v)) if isinstance(v, list) else 0

            example = max(node, key=liveliness)
            series = node[example]
            # Pruefsumme ueber alle Reihen: erkennt jede Aenderung, auch wenn
            # die Beispielreihe zufaellig stillsteht.
            checksum = hashlib.sha256(
                json.dumps(node, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()[:16]
            out[path] = {
                "keys": len(node),
                "length": len(series),
                "example_key": example,
                "distinct_values": liveliness(example),
                "tail": series[-4:],
                "checksum": checksum,
                # Die ganze Reihe, damit zwei aufeinanderfolgende
                # Schreibvorgaenge stellenweise verglichen werden koennen.
                "sample": list(series[:400]),
            }
            continue
        for k, v in node.items():
            stack.append((v, f"{path}.{k}", depth + 1))
    return out


def probe_savestate(path: Path, max_nodes: int = 400_000) -> dict:
    """Liest den geschriebenen Spielstand und zieht ein paar Kennzahlen heraus."""
    started = time.time()
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return {"error": f"nicht lesbar: {exc}"}
    if len(raw) > PROBE_MAX_BYTES:
        return {"error": f"uebersprungen, {len(raw) // 1024 // 1024} MB"}

    dec = decode_container(raw)
    if dec["payload"] is None:
        return {"error": f"Container {dec['container']} nicht dekodierbar"}
    try:
        data = json.loads(dec["payload"].decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        # Halb geschriebene Datei beim Zugriff mitten im Schreibvorgang.
        return {"error": f"JSON unvollstaendig: {exc.msg}"}

    walked = walk_json(data, max_nodes, 0)
    report = field_report(walked["key_counts"], walked["key_example"])
    values = {}
    for label in PROBE_LABELS:
        hits = report.get(label) or []
        if hits:
            values[label] = ", ".join(f"{h['key']}={h['preview']}" for h in hits[:3])
    # Spieluhr als Zahl, damit sich Wanduhr und Spielzeit ins Verhaeltnis
    # setzen lassen. Ohne das sind Messungen bei verschiedenen
    # Spielgeschwindigkeiten nicht vergleichbar.
    lowered = {k.lower(): k for k in walked["key_counts"]}
    for cand in CLOCK_KEYS:
        if cand in lowered:
            orig = lowered[cand]
            try:
                val = json.loads(walked["key_example"][orig]["preview"])
            except (ValueError, TypeError):
                continue
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                values["_clock_key"] = orig
                values["_clock"] = float(val)
                break

    series = series_fingerprint(data)
    if series:
        values["_series"] = series

    values["_parse_seconds"] = round(time.time() - started, 2)
    return values


def cmd_watch(args) -> dict:
    directory, tried = resolve_dir(args.dir)
    out: dict = {"tried_dirs": tried, "dir": str(directory) if directory else None}
    if directory is None:
        out["error"] = "Kein Save-Verzeichnis gefunden, --dir angeben."
        return out

    files = [p for p in list_save_files(directory) if p.suffix.lower() == ".save"] or list_save_files(directory)
    files, skipped = select_targets(files, args.max_files)
    out["watched"] = [str(p) for p in files]
    out["skipped"] = [p.name for p in skipped]
    if not any(p.name.lower() == "save.save" for p in files):
        out["warning"] = (
            "Save.save liegt nicht im beobachteten Verzeichnis. Ohne diese Datei "
            "beantwortet die Messung Frage 2 nicht -- MetaSave ist der Metafortschritt, "
            "nicht die laufende Siedlung."
        )
    out["interval_seconds"] = args.interval
    out["duration_minutes"] = args.minutes

    last: dict[str, tuple[float, int]] = {}
    events: list[dict] = []
    deadline = time.time() + args.minutes * 60
    started = time.time()

    print(f"Beobachte {len(files)} Datei(en) fuer {args.minutes} Minuten, Abtastung alle {args.interval}s.")
    print("Spiel laufen lassen und normal weiterspielen. Abbruch mit Strg+C.\n")

    try:
        while time.time() < deadline:
            for p in files:
                try:
                    st = p.stat()
                except FileNotFoundError:
                    continue
                key = str(p)
                sig = (st.st_mtime, st.st_size)
                if key not in last:
                    last[key] = sig
                    continue
                if sig != last[key]:
                    now = time.time()
                    prev_evt = [e for e in events if e["file"] == key]
                    gap = round(now - (prev_evt[-1]["wall_clock_epoch"] if prev_evt else started), 1)
                    evt = {
                        "file": key,
                        "at": datetime.now(timezone.utc).isoformat(),
                        "wall_clock_epoch": now,
                        "seconds_since_previous": gap,
                        "size_bytes": st.st_size,
                        "size_delta": st.st_size - last[key][1],
                    }
                    if args.probe and p.name.lower() in PRIORITY_NAMES:
                        evt["probe"] = probe_savestate(p, args.max_nodes)
                    events.append(evt)
                    print(f"[{evt['at']}] Schreibvorgang {Path(key).name}: "
                          f"{evt['size_delta']:+,} Bytes, {gap}s seit dem letzten")
                    for k, v in (evt.get("probe") or {}).items():
                        if not k.startswith("_"):
                            print(f"    {k}: {v}")
                    for spath, s in ((evt.get("probe") or {}).get("_series") or {}).items():
                        print(f"    Zeitreihe {spath}: {s['keys']} Reihen, Laenge {s['length']}, "
                              f"Ende von {s['example_key']}: {s['tail']}")
                    last[key] = sig
            time.sleep(args.interval)
    except KeyboardInterrupt:
        out["interrupted"] = True
        print("\nAbgebrochen.")

    out["events"] = events
    out["observed_minutes"] = round((time.time() - started) / 60, 2)

    per_file: dict[str, dict] = {}
    for p in files:
        key = str(p)
        gaps = [e["seconds_since_previous"] for e in events if e["file"] == key][1:]
        entry: dict = {"writes": len([e for e in events if e["file"] == key])}
        # Ein einzelner Abstand ist kein Intervall. Erst ab drei Abstaenden
        # laesst sich von einem Takt reden; darunter wird ausgewiesen, was es
        # ist: Einzelbeobachtungen.
        if len(gaps) >= 3:
            median = statistics.median(gaps)
            entry["gap_seconds"] = {"min": min(gaps), "median": round(median, 1), "max": max(gaps)}
            entry["verdict"] = f"schreibt etwa alle {round(median)}s ({len(gaps)} Abstaende)"
            lo, hi = CLAIMED_HEARTBEAT
            game_gaps = []
            clocked = [e for e in events if e["file"] == key
                       and (e.get("probe") or {}).get("_clock") is not None]
            for prev, cur in zip(clocked, clocked[1:]):
                d = cur["probe"]["_clock"] - prev["probe"]["_clock"]
                if d > 0:
                    game_gaps.append(d)
            if game_gaps:
                gmed = statistics.median(game_gaps)
                entry["game_gap_median"] = round(gmed, 1)
                entry["heartbeat_claim"] = (
                    f"Recherche behauptet {lo:.0f} bis {hi:.0f}s; in Spielzeit gemessen "
                    f"{gmed:.0f}s: " + ("bestaetigt" if lo <= gmed <= hi else "abweichend")
                    + " (der Wanduhr-Median haengt an der Spielgeschwindigkeit und "
                      "taugt fuer diese Pruefung nicht)"
                )
            else:
                entry["heartbeat_claim"] = (
                    f"Recherche behauptet {lo:.0f} bis {hi:.0f}s -- ohne Spieluhr nicht pruefbar, "
                    "der Wanduhr-Median haengt an der Spielgeschwindigkeit"
                )
        elif gaps:
            entry["gap_seconds"] = {"raw": gaps}
            entry["verdict"] = (
                f"nur {len(gaps)} Abstand(e) gemessen ({', '.join(f'{g:.0f}s' for g in gaps)}) -- "
                "zu wenig fuer eine Taktaussage, laenger messen"
            )
        elif entry["writes"] == 1:
            entry["verdict"] = "genau ein Schreibvorgang im Messfenster, Intervall nicht bestimmbar"
        else:
            entry["verdict"] = "kein Schreibvorgang im Messfenster"

        # Zeitreihen: welche Stellen ruecken zwischen zwei Schreibvorgaengen
        # weiter? Die Zahl der geaenderten Stellen geteilt in die vergangene
        # Spielzeit ergibt den Abstand der Stuetzstellen.
        with_series = [e for e in events if e["file"] == key and (e.get("probe") or {}).get("_series")]
        shifts: list[dict] = []
        for prev, cur in zip(with_series, with_series[1:]):
            for spath, s_cur in cur["probe"]["_series"].items():
                s_prev = prev["probe"]["_series"].get(spath)
                if not s_prev or not s_cur.get("sample") or not s_prev.get("sample"):
                    continue
                a, b = s_prev["sample"], s_cur["sample"]
                changed = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
                d_game = None
                if (prev["probe"].get("_clock") is not None
                        and cur["probe"].get("_clock") is not None):
                    d_game = round(cur["probe"]["_clock"] - prev["probe"]["_clock"], 1)
                entry_shift = {
                    "series": spath, "key": s_cur["example_key"],
                    "changed_indices": changed[:12], "changed_count": len(changed),
                    "length_before": len(a), "length_after": len(b),
                    "game_seconds": d_game,
                    "other_series_changed": s_prev.get("checksum") != s_cur.get("checksum"),
                }
                if changed and d_game:
                    entry_shift["seconds_per_step"] = round(d_game / len(changed), 1)
                shifts.append(entry_shift)
        if shifts:
            entry["series_shifts"] = shifts

        # Spielzeit gegen Wanduhr: verraet die effektive Geschwindigkeit und
        # macht Messungen ueber Geschwindigkeitswechsel hinweg vergleichbar.
        clocked = [e for e in events if e["file"] == key and (e.get("probe") or {}).get("_clock") is not None]
        factors = []
        for prev, cur in zip(clocked, clocked[1:]):
            d_wall = cur["wall_clock_epoch"] - prev["wall_clock_epoch"]
            d_game = cur["probe"]["_clock"] - prev["probe"]["_clock"]
            if d_wall > 0:
                factors.append(round(d_game / d_wall, 2))
        if factors:
            entry["game_seconds_per_wall_second"] = factors
            entry["clock_key"] = clocked[0]["probe"].get("_clock_key")
            entry["speed_note"] = (
                "Spielzeit je Wanduhrsekunde: " + ", ".join(f"{f}" for f in factors)
                + " -- Abstaende in Spielzeit umrechnen, bevor sie verglichen werden"
            )
        per_file[Path(key).name] = entry
    out["summary"] = per_file

    # Schreibt das Spiel mehrere Dateien im selben Zug? Das entscheidet, ob
    # der Parser eine Datei beobachten muss oder drei.
    groups: list[dict] = []
    for e in sorted(events, key=lambda x: x["wall_clock_epoch"]):
        if groups and e["wall_clock_epoch"] - groups[-1]["epoch"] <= CO_WRITE_WINDOW:
            groups[-1]["files"].append(Path(e["file"]).name)
            groups[-1]["last"] = e["wall_clock_epoch"]
        else:
            groups.append({"epoch": e["wall_clock_epoch"], "at": e["at"],
                           "last": e["wall_clock_epoch"],
                           "files": [Path(e["file"]).name]})
    out["co_writes"] = [
        {"at": g["at"], "files": g["files"], "spread_seconds": round(g["last"] - g["epoch"], 2)}
        for g in groups if len(g["files"]) > 1
    ]
    return out


# --------------------------------------------------------------------------
# Bericht
# --------------------------------------------------------------------------


def render(report: dict) -> str:
    L: list[str] = []
    add = L.append
    add("=" * 78)
    add("PHASE-0-DIAGNOSE  Against the Storm Assistant")
    add("=" * 78)
    env = report["environment"]
    add(f"System     : {env['platform']}  Python {env['python']}")
    add(f"Zeitpunkt  : {env['timestamp']}")

    ins = report.get("inspect")
    if ins:
        add("")
        add("-" * 78)
        add("FRAGE 1+3: SAVE-FORMAT UND SPRACHE")
        add("-" * 78)
        if ins.get("error"):
            add(f"FEHLER: {ins['error']}")
            add("Gesuchte Pfade:")
            for t in ins["tried_dirs"]:
                add(f"  [{'x' if t['exists'] else ' '}] {t['path']}")
        else:
            add(f"Verzeichnis: {ins['dir']}")
            if ins.get("skipped"):
                add(f"Nicht untersucht (Obergrenze --max-files): {', '.join(ins['skipped'])}")
            add("")
            add("Dateien:")
            for f in ins.get("dir_listing", [])[:30]:
                add(f"  {f['name']:<40} {f['size_bytes']:>12,} B   {f['mtime']}")
            for f in ins["files"]:
                add("")
                add(f"### {f.get('name', f['file'])}")
                if "error" in f:
                    add(f"  Fehler: {f['error']}")
                    continue
                add(f"  Groesse     : {f['size_mb']} MB")
                add(f"  Container   : {f['container']}")
                for n in f.get("container_notes", []):
                    add(f"                {n}")
                if not f.get("decoded"):
                    add("  Dekodierung : FEHLGESCHLAGEN")
                    add("  Hexdump der ersten 256 Bytes:")
                    for line in f["first_256_bytes_hex"].splitlines():
                        add("    " + line)
                    add("  Hypothesen:")
                    for h in f.get("hypothesis", []):
                        add(f"    - {h}")
                    continue
                add(f"  Nutzdaten   : {f['payload_mb']} MB, {f.get('payload_lines', '?'):,} Zeilen, "
                    f"Faktor {f.get('compression_ratio', '?')}")
                if not f.get("json"):
                    add(f"  JSON        : NEIN ({f.get('json_error')})")
                    add(f"  Anfang      : {f.get('payload_head', '')[:200]!r}")
                    continue
                add(f"  JSON        : ja, {f['distinct_keys']:,} verschiedene Schluessel, "
                    f"Tiefe {f['max_depth']}, {f['nodes_visited']:,} Knoten besucht"
                    + ("  (Durchlauf gekappt)" if f.get("walk_truncated") else ""))
                tl = f.get("top_level_keys")
                if isinstance(tl, list):
                    add(f"  Oberste Ebene: {', '.join(tl[:20])}")
                lang = f["language"]
                add("")
                add(f"  Sprache     : {lang['verdict']}")
                add(f"                {lang['strings_sampled']} Strings geprobt, "
                    f"{lang['strings_with_umlauts']} mit Umlauten, {lang['id_like_strings']} ID-artig")
                if lang["english_hits"]:
                    add(f"                englische Treffer: {', '.join(lang['english_hits'][:12])}")
                if lang["german_hits"]:
                    add(f"                deutsche Treffer : {', '.join(lang['german_hits'][:12])}")
                add(f"                Stringprobe: {', '.join(lang['sample'][:12])}")
                add("")
                add("  GameState-Felder (Phase 2) im Save:")
                for label, hits in f["fields"].items():
                    if hits:
                        h = hits[0]
                        add(f"    [ja  ] {label:<28} {h['key']} x{h['count']} (Tiefe {h['depth']})  {h['path'][:52]}")
                    else:
                        add(f"    [nein] {label:<28} kein passender Schluessel gefunden")

                r = f.get("research")
                if r:
                    add("")
                    add(f"  Gegenprobe zur Recherche: {r['paths_confirmed']} von {r['paths_total']} "
                        f"behaupteten Pfaden woertlich bestaetigt")
                    for label, c in r["paths"].items():
                        mark = {"bestaetigt": "ja", "anderer Pfad": "teils", "nicht gefunden": "nein"}[c["status"]]
                        add(f"    [{mark:<5}] {label:<24} {c['claim']}")
                        if c["evidence"]:
                            add(f"            -> {c['evidence'][:90]}")
                    pc = r["prefix_convention"]
                    add(f"    Kategoriepraefix '[Food Raw] Meat': {pc['verdict']}"
                        + (f", {pc['matches']} Treffer" if pc["matches"] else ""))
                    if pc["categories"]:
                        add("      Kategorien: " + ", ".join(f"{c} x{n}" for c, n in pc["categories"][:10]))
                        add("      Beispiele : " + ", ".join(pc["examples"][:6]))
                    add(f"    Container  : behauptet {r['container']['claim']}, gemessen "
                        f"{r['container']['measured']} -> {r['container']['status']}")
                    add(f"    Zeilenzahl : behauptet {r['size']['claim']}, gemessen "
                        f"{r['size']['measured']:,} -> {r['size']['status']}"
                        if isinstance(r["size"]["measured"], int) else
                        f"    Zeilenzahl : {r['size']['status']}")

    w = report.get("watch")
    if w:
        add("")
        add("-" * 78)
        add("FRAGE 2: SCHREIBZEITPUNKT")
        add("-" * 78)
        if w.get("error"):
            add(f"FEHLER: {w['error']}")
        else:
            add(f"Messdauer: {w.get('observed_minutes')} Minuten, Abtastung alle {w['interval_seconds']}s")
            if w.get("warning"):
                add(f"ACHTUNG: {w['warning']}")
            if w.get("skipped"):
                add(f"Nicht beobachtet (Obergrenze --max-files): {', '.join(w['skipped'])}")
            for name, s in w.get("summary", {}).items():
                add(f"  {name:<24} {s['writes']} Schreibvorgaenge  -> {s['verdict']}")
                if s.get("heartbeat_claim"):
                    add(f"  {'':<24} {s['heartbeat_claim']}")
                for sh in s.get("series_shifts", [])[:6]:
                    if sh["changed_count"] == 0:
                        rest = ("andere Reihen darin haben sich aber geaendert"
                                if sh.get("other_series_changed")
                                else "auch die Pruefsumme ueber alle Reihen ist gleich")
                        add(f"  {'':<24} {sh['series']}: Beispielreihe {sh['key']} unveraendert "
                            f"ueber {sh['game_seconds']}s Spielzeit -- {rest}")
                    else:
                        add(f"  {'':<24} {sh['series']}: {sh['changed_count']} Stellen geaendert "
                            f"(Index {sh['changed_indices']}) in {sh['game_seconds']}s Spielzeit"
                            + (f" -> etwa {sh['seconds_per_step']}s je Stuetzstelle"
                               if sh.get("seconds_per_step") else ""))
                if s.get("speed_note"):
                    add(f"  {'':<24} {s['speed_note']} (Uhr: {s.get('clock_key')})")
            if w.get("co_writes"):
                add(f"  Gemeinsame Schreibvorgaenge (innerhalb von {CO_WRITE_WINDOW:.0f}s):")
                for g in w["co_writes"][:20]:
                    add(f"    {g['at']}  {', '.join(g['files'])}"
                        f"   (Spanne {g['spread_seconds']}s)")
            if w.get("events"):
                add("  Ereignisse:")
                for e in w["events"][:40]:
                    add(f"    {e['at']}  {Path(e['file']).name:<16} {e['size_delta']:+,} B  "
                        f"(+{e['seconds_since_previous']}s)")
                    for k, v in (e.get("probe") or {}).items():
                        if k == "_parse_seconds":
                            add(f"        (Spielstand in {v}s gelesen)")
                        elif k == "_series":
                            for spath, s in v.items():
                                add(f"        Zeitreihe {spath}: {s['keys']} Reihen, "
                                    f"Laenge {s['length']}, Ende von {s['example_key']}: {s['tail']}")
                        else:
                            add(f"        {k}: {v}")
    add("")
    add("=" * 78)
    return "\n".join(L)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["inspect", "watch", "all"], nargs="?", default="inspect")
    ap.add_argument("--dir", help="Save-Verzeichnis explizit angeben")
    ap.add_argument("--minutes", type=float, default=10.0, help="Messdauer fuer watch (Vorgabe 10)")
    ap.add_argument("--interval", type=float, default=2.0, help="Abtastintervall in Sekunden (Vorgabe 2)")
    ap.add_argument("--max-files", type=int, default=6, help="Hoechstzahl untersuchter Dateien")
    ap.add_argument("--probe", dest="probe", action="store_true", default=True,
                    help="bei jedem Schreibvorgang Kennzahlen aus dem Spielstand lesen (Vorgabe)")
    ap.add_argument("--no-probe", dest="probe", action="store_false",
                    help="Sonde abschalten, nur Zeitpunkte protokollieren")
    ap.add_argument("--max-nodes", type=int, default=3_000_000, help="Knotenobergrenze beim JSON-Durchlauf")
    ap.add_argument("--max-strings", type=int, default=400, help="Groesse der Stringprobe")
    ap.add_argument("--sketch-depth", type=int, default=3, help="Tiefe der Strukturskizze")
    ap.add_argument("--out", default="diagnostics", help="Ausgabeverzeichnis fuer den Bericht")
    args = ap.parse_args(argv)

    report: dict = {
        "schema_version": SCHEMA_VERSION,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    if args.mode in ("inspect", "all"):
        report["inspect"] = cmd_inspect(args)
    if args.mode in ("watch", "all"):
        report["watch"] = cmd_watch(args)

    text = render(report)
    print(text)

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = outdir / f"phase0-{stamp}.json"
    txt_path = outdir / f"phase0-{stamp}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    txt_path.write_text(text, encoding="utf-8")
    print(f"\nBericht geschrieben: {json_path}\n                     {txt_path}")
    print("Die Dateien bleiben lokal. Fuer die Auswertung reicht mir der .txt-Bericht.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
