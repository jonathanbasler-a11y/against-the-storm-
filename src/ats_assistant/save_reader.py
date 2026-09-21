"""Phase 2: den Spielstand lesen und als GameState normalisieren.

Was Phase 0 gemessen hat und was hier deshalb so und nicht anders steht:

* Das Spiel schreibt vier Dateien als Buendel, aber **nicht atomar** -- einmal
  lag `Save.save` 2,02 Sekunden hinter `MetaSave.save`. Wer auf die erste
  Aenderung reagiert, liest eine Datei neu und die andere alt. Deshalb
  `wait_for_quiet()`.
* Warennamen tragen gestapelte Kategoriepraefixe (`[SSE] [BIOME] Storm
  Penalty`). Das Abschneiden schleift, siehe `paths.strip_prefixes`.
* Die Ungeduld heisst `reputationPenalty`, die Spieluhr `time`, und
  `hostility` ist ein Dictionary, kein Skalar.
* `Save.save` sind 8,5 MB und wird von `json.loads` in 0,1 Sekunden gelesen.
  Es braucht kein ijson und kein mmap.
* Die Pfade sind nur teilweise bekannt, deshalb loest `paths.resolve` jedes
  Feld zweistufig auf und protokolliert, woher es kam.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import KeyIndex, Resolution, index_keys, resolve, strip_prefixes

log = logging.getLogger(__name__)

SAVE_FILES = ("Save.save", "WorldSave.save", "MetaSave.save")

# Nach dem ersten erkannten Schreibvorgang so lange warten, bis sich nichts
# mehr rührt. Gemessener Versatz im Buendel: bis 2,02 Sekunden.
SETTLE_SECONDS = 3.0


@dataclass
class Building:
    model: str | None
    workers: int | None
    finished: bool | None


@dataclass
class GameState:
    """Ein Zustand der Siedlung, so weit der Spielstand ihn hergibt."""

    captured_at: str
    game_time: float | None = None
    year: int | None = None
    season: int | None = None

    biome: str | None = None
    # Der Snapshot vom gewonnenen Lauf zeigte: difficulty ist ein String wie
    # "Prestige 16 Ascension XIII", kein Integer. Beides wird behalten -- der
    # Rohwert, weil er die Wahrheit ist, und die Stufe, weil damit gerechnet wird.
    prestige_raw: str | None = None
    prestige: int | None = None
    world_modifiers: list[str] = field(default_factory=list)

    population: int | None = None
    species: list[str] = field(default_factory=list)

    hostility: dict[str, Any] | None = None
    impatience: float | None = None
    impatience_to_lose: float | None = None
    impatience_per_second: float | None = None
    impatience_bonus_rate: float | None = None
    reputation: float | None = None
    reputation_to_win: float | None = None

    storage: dict[str, float] = field(default_factory=dict)
    buildings: list[Building] = field(default_factory=list)
    glades: int | None = None
    deposits: int | None = None
    cornerstones: list[str] = field(default_factory=list)

    # Zeitreihen: 180 Stuetzstellen à rund 10 Spielzeitsekunden, je Ware und
    # je Warenkategorie. Daraus kommt die Steigung fuer food_forecast.
    goods_trends: dict[str, list[float]] = field(default_factory=dict)
    category_trends: dict[str, list[float]] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @property
    def won(self) -> bool | None:
        """Sieg: Reputation hat die Siegschwelle erreicht."""
        if self.reputation is None or self.reputation_to_win is None:
            return None
        return self.reputation >= self.reputation_to_win

    @property
    def lost(self) -> bool | None:
        if self.impatience is None or self.impatience_to_lose is None:
            return None
        return self.impatience >= self.impatience_to_lose


def wait_for_quiet(directory: Path, settle: float = SETTLE_SECONDS,
                   timeout: float = 30.0, poll: float = 0.5) -> bool:
    """Wartet, bis sich im Spielordner `settle` Sekunden nichts mehr ruehrt.

    Das Buendel ist nicht atomar. Ohne dieses Warten liest der Parser eine
    Datei aus dem neuen und eine aus dem alten Schreibvorgang.
    """
    deadline = time.monotonic() + timeout
    last_sig: tuple | None = None
    quiet_since = time.monotonic()
    while time.monotonic() < deadline:
        sig = tuple(
            (p.stat().st_mtime_ns, p.stat().st_size)
            for p in (directory / n for n in SAVE_FILES) if p.exists()
        )
        now = time.monotonic()
        if sig != last_sig:
            last_sig, quiet_since = sig, now
        elif now - quiet_since >= settle:
            return True
        time.sleep(poll)
    log.warning("Spielordner kam in %.0fs nicht zur Ruhe, lese trotzdem", timeout)
    return False


def _load(path: Path) -> Any | None:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        log.warning("%s nicht lesbar: %s", path.name, exc)
        return None
    text = raw.lstrip(b" \t\r\n")
    if text.startswith(b"\xef\xbb\xbf"):
        text = text[3:]
    try:
        return json.loads(text.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        # Halb geschriebene Datei: kein harter Abbruch, der naechste
        # Schreibvorgang kommt in 300 Spielzeitsekunden.
        log.warning("%s ist kein vollstaendiges JSON: %s", path.name, exc.msg)
        return None


def _normalise_goods(raw: Any) -> dict[str, float]:
    """Warenbestand aus den Formen holen, in denen das Spiel ihn ablegt."""
    out: dict[str, float] = {}
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = []
        for entry in raw:
            if isinstance(entry, dict):
                key = entry.get("Key") or entry.get("name") or entry.get("model")
                val = entry.get("Value") if "Value" in entry else entry.get("amount")
                if isinstance(key, str):
                    items.append((key, val))
    else:
        return out
    for key, val in items:
        if not isinstance(key, str) or not isinstance(val, (int, float)) or isinstance(val, bool):
            continue
        name, _prefixes = strip_prefixes(key)
        out[name] = out.get(name, 0) + float(val)
    return out


def _series(raw: Any) -> dict[str, list[float]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[float]] = {}
    for key, values in raw.items():
        if not isinstance(key, str) or not isinstance(values, list):
            continue
        if not values or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                 for v in values[:5]):
            continue
        name, _ = strip_prefixes(key)
        out[name] = [float(v) for v in values]
    return out


def read_state(directory: Path, wait: bool = True) -> tuple[GameState, list[Resolution]]:
    """Liest das Buendel und baut den GameState. Wirft nicht, wenn Teile fehlen."""
    directory = Path(directory)
    if wait:
        wait_for_quiet(directory)

    save = _load(directory / "Save.save")
    world = _load(directory / "WorldSave.save")
    meta = _load(directory / "MetaSave.save")

    state = GameState(captured_at=datetime.now(timezone.utc).isoformat())
    notes: list[Resolution] = []

    def pick(data: Any, idx: KeyIndex, name: str, paths=(), keys=(), want=None):
        value, note = resolve(data, idx, name, paths, keys, want)
        notes.append(note)
        return value

    if save is not None:
        idx = index_keys(save)
        state.game_time = pick(save, idx, "game_time", ("time",), ("time", "gameTime"), (int, float))
        state.year = pick(save, idx, "year", ("year",), ("year",), int)
        state.season = pick(save, idx, "season", ("season",), ("season",), int)
        state.hostility = pick(save, idx, "hostility", ("hostility",), ("hostility",), dict)
        state.impatience = pick(save, idx, "impatience", (), ("reputationPenalty",), (int, float))
        state.impatience_to_lose = pick(save, idx, "impatience_to_lose", (),
                                        ("reputationPenaltyToLoose",), (int, float))
        state.impatience_per_second = pick(save, idx, "impatience_per_second", (),
                                           ("reputationPenaltyPerSec",), (int, float))
        state.reputation = pick(save, idx, "reputation", (), ("reputation",), (int, float))
        state.reputation_to_win = pick(save, idx, "reputation_to_win", (),
                                       ("reputationToWin",), (int, float))
        state.storage = _normalise_goods(
            pick(save, idx, "storage", ("storage.goods",), ("goods", "storage", "resources")))
        state.goods_trends = _series(
            pick(save, idx, "goods_trends", ("trends.goodsTrends",), ("goodsTrends",), dict))
        state.category_trends = _series(
            pick(save, idx, "category_trends", ("trends.goodsCategoriesTrends",),
                 ("goodsCategoriesTrends",), dict))
        state.cornerstones = [
            c for c in (pick(save, idx, "cornerstones", (), ("cornerstones", "effects"), list) or [])
            if isinstance(c, str)
        ]
        glades = pick(save, idx, "glades", ("world.glades",), ("glades",), list)
        state.glades = len(glades) if isinstance(glades, list) else None
        deposits = pick(save, idx, "deposits", ("world.naturalResources",),
                        ("naturalResources", "deposits"), list)
        state.deposits = len(deposits) if isinstance(deposits, list) else None

        raw_buildings = pick(save, idx, "buildings", ("buildings.buildings",), ("buildings",))
        state.buildings = _buildings(raw_buildings)

    if meta is not None:
        midx = index_keys(meta)
        state.biome = pick(meta, midx, "biome", ("gameConditions.biome",), ("biome",), str)
        raw_diff = pick(meta, midx, "prestige", ("gameConditions.difficulty",),
                        ("difficulty",), (str, int))
        state.prestige_raw = str(raw_diff) if raw_diff is not None else None
        state.prestige = parse_prestige(raw_diff)
        state.impatience_bonus_rate = pick(meta, midx, "impatience_bonus_rate", (),
                                           ("reputationPenaltyBonusRate",), (int, float))
        races = pick(meta, midx, "species", ("gameConditions.races",), ("races",), list)
        state.species = [r for r in (races or []) if isinstance(r, str)]
        mods = pick(meta, midx, "world_modifiers", (), ("modifiers", "playedWorldEffects"), list)
        state.world_modifiers = [m for m in (mods or []) if isinstance(m, str)]

    if world is not None:
        widx = index_keys(world)
        state.population = pick(world, widx, "population", (), ("population",), int)

    for n in notes:
        log.debug("Feld %s: %s (%s)", n.field, n.path, n.how)
    return state, notes


ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def _roman(text: str) -> int | None:
    total, prev = 0, 0
    for ch in reversed(text.upper()):
        val = ROMAN.get(ch)
        if val is None:
            return None
        total = total - val if val < prev else total + val
        prev = max(prev, val)
    return total or None


def parse_prestige(raw: Any) -> int | None:
    """Stufe aus 'Prestige 16 Ascension XIII' herausholen.

    Der Spielstand nennt zwei Zahlen. Die roemische hinter "Ascension" ist die,
    die im Spiel angezeigt wird -- XIII bei einem Spieler, der auf Prestige 13
    spielt. Die arabische davor sieht nach einem internen Index aus. Im Zweifel
    gewinnt die angezeigte, und prestige_raw behaelt beide.
    """
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if not isinstance(raw, str):
        return None
    m = re.search(r"Ascension\s+([IVXLC]+)", raw, re.IGNORECASE)
    if m:
        level = _roman(m.group(1))
        if level is not None:
            return level
    m = re.search(r"(?:Prestige|Ascension)\s+(\d+)", raw, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\d+", raw)
    return int(m.group()) if m else None


def _buildings(raw: Any) -> list[Building]:
    out: list[Building] = []
    if not isinstance(raw, list):
        return out
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        workers = entry.get("workers")
        if isinstance(workers, list):
            workers = sum(1 for w in workers if w)
        out.append(Building(
            model=entry.get("model") if isinstance(entry.get("model"), str) else None,
            workers=workers if isinstance(workers, int) else None,
            finished=entry.get("finished") if isinstance(entry.get("finished"), bool) else None,
        ))
    return out


def append_run_log(state: GameState, run_id: str, runs_dir: Path = Path("runs")) -> Path:
    """Jeden Zustand als Zeile in runs/<run_id>.jsonl -- Grundlage fuer analyze_runs."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    target = runs_dir / f"{run_id}.jsonl"
    with target.open("a", encoding="utf-8") as fh:
        fh.write(state.to_json() + "\n")
    return target
