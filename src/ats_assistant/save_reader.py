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

    # Gemessen am 23.09.2026 (1.10.4). Der Ruf je Quelle ist ein Vektor aus
    # vier Zahlen; belegt ist nur Index 2 (Zufriedenheit, gleich dem Gewinn
    # der Fuechse). Die Auftraege bleiben Dicts in der Form des Spielstands.
    reputation_sources: list[float] = field(default_factory=list)
    reputation_by_race: dict[str, float] = field(default_factory=dict)
    blueprints: list[str] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)

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
                if not isinstance(key, str) or val is None:
                    key, val = _name_und_zahl(entry)
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


def _name_und_zahl(entry: dict) -> tuple[str | None, Any]:
    """Zwei Schluessel, einer ein Name, einer eine Zahl -- so sah eine Ware
    im Lager aus; welche Schluessel es genau sind, zeigte die Messung nicht."""
    namen = [v for v in entry.values() if isinstance(v, str)]
    zahlen = [v for v in entry.values()
              if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if len(namen) == 1 and len(zahlen) == 1:
        return namen[0], zahlen[0]
    return None, None


def _entdeckte(glades: Any) -> int | None:
    """Gemessen: `world.glades` ist die ganze Karte (42 nach 600 Sekunden).
    Wo `wasDiscovered` steht, zaehlen nur die entdeckten."""
    if not isinstance(glades, list):
        return None
    if any(isinstance(g, dict) and "wasDiscovered" in g for g in glades):
        return sum(1 for g in glades if isinstance(g, dict) and g.get("wasDiscovered") is True)
    return len(glades)


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
        # Gemessen am 23.09.2026 (1.10.4): `goods.goods.goods`. Kein
        # Namensrueckfall -- jedes Gebaeude hat ein eigenes `storage.goods`,
        # und der flachste Treffer war nicht das Hauptlager.
        raw_storage = pick(save, idx, "storage", ("goods.goods.goods", "storage.goods"))
        state.storage = _normalise_goods(raw_storage)
        _form_pruefen(notes[-1], raw_storage, state.storage)
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
        state.glades = _entdeckte(glades)
        deposits = pick(save, idx, "deposits", ("world.naturalResources",),
                        ("naturalResources", "deposits"), list)
        state.deposits = len(deposits) if isinstance(deposits, list) else None

        quellen = pick(save, idx, "reputation_sources", ("gameObjectives.reputationSources",),
                       want=list)
        state.reputation_sources = [float(q) for q in (quellen or [])
                                    if isinstance(q, (int, float)) and not isinstance(q, bool)]
        voelker = pick(save, idx, "reputation_by_race", ("actors.racesReputationGains",),
                       want=dict)
        state.reputation_by_race = {k: float(v) for k, v in (voelker or {}).items()
                                    if isinstance(v, (int, float)) and not isinstance(v, bool)}
        plaene = pick(save, idx, "blueprints", ("content.buildings",), want=list)
        state.blueprints = [b for b in (plaene or []) if isinstance(b, str)]
        raw_orders = pick(save, idx, "orders", ("orders.currentOrders",), want=list)
        state.orders = [o for o in (raw_orders or [])
                        if isinstance(o, dict) and isinstance(o.get("model"), str)]
        _form_pruefen(notes[-1], raw_orders, state.orders)

        raw_buildings = pick(save, idx, "buildings", ("buildings.buildings", "buildings"))
        state.buildings = _buildings(raw_buildings)
        _form_pruefen(notes[-1], raw_buildings, state.buildings)

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


GEBAEUDE_OHNE = frozenset({"roads"})


def _buildings(raw: Any) -> list[Building]:
    out: list[Building] = []
    # Ein Dictionary nach Kennung ist die naheliegende zweite Form -- aber
    # nur, wenn jeder Wert ein Eintrag ist. Sonst waeren es Gruppen, und die
    # zu zaehlen ergaebe eine falsche Zahl statt einer Meldung.
    if isinstance(raw, dict) and raw and all(isinstance(v, dict) for v in raw.values()):
        raw = list(raw.values())
    elif isinstance(raw, dict):
        # Gemessen am 23.09.2026 (1.10.4): nach Art sortiert -- houses,
        # workshops, camps, storages, roads ... Strassen sind keine Gebaeude
        # im Sinne der Frage "was steht"; 38 Stueck wuerden die Zahl fluten.
        raw = [e for art, liste in raw.items()
               if art not in GEBAEUDE_OHNE and isinstance(liste, list)
               for e in liste if isinstance(e, dict)]
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


def form_skizze(wert: Any, tiefe: int = 3, breite: int | None = 6) -> str:
    """Schluessel und Typen, nie Werte: {goods: [12x {Key: str, Value: int}]}."""
    if isinstance(wert, dict):
        if not wert:
            return "{}"
        if tiefe <= 0:
            return f"{{{len(wert)} Schlüssel}}"
        teile = [f"{k}: {form_skizze(v, tiefe - 1, breite)}"
                 for k, v in list(wert.items())[:breite]]
        if breite is not None and len(wert) > breite:
            teile.append(f"… +{len(wert) - breite}")
        return "{" + ", ".join(teile) + "}"
    if isinstance(wert, list):
        if not wert:
            return "[]"
        if tiefe <= 0:
            return f"[{len(wert)}x]"
        return f"[{len(wert)}x {form_skizze(wert[0], tiefe - 1, breite)}]"
    return "null" if wert is None else type(wert).__name__


def _form_pruefen(note: Resolution, roh: Any, gelesen: Any) -> None:
    """Gefunden, aber leer gelesen, obwohl etwas da war: das ist eine
    unbekannte Form, kein leeres Lager. Am 22.09.2026 sah genau das am
    Spielrechner aus wie `lager: {}` -- ohne jede Meldung."""
    if gelesen or not roh or note.how == "fehlt":
        return
    note.how = "form_unbekannt"
    note.form = form_skizze(roh)


# Die Felder, deren Form am ersten echten Lauf nicht stimmte oder
# zweifelhaft ist (42 Lichtungen und 5760 Vorkommen nach 600 Sekunden).
FORM_FELDER = ("storage", "buildings", "glades", "deposits")
FORM_STICHWORTE = ("goods", "storage", "building", "glade", "resource", "deposit")


def formbericht(directory: Path, wait: bool = True, grenze: int | None = 30,
                stichworte: tuple[str, ...] = (), pfad: str | None = None) -> list[str]:
    """Wie das Spiel die fraglichen Felder wirklich ablegt -- zum Einfuegen
    in den Chat. Nur Pfade, Schluessel und Typen; keine Werte.

    Mit Stichworten wird stattdessen in allen drei Dateien nach Schluesseln
    gesucht, die eines davon enthalten: so war das Lager gefunden, und so
    werden Auftraege, Ruf und Bauplaene gefunden.
    """
    directory = Path(directory)
    if not (directory / "Save.save").exists():
        return [f"Kein Spielstand unter {directory}."]
    if pfad:
        return _knoten_zeigen(directory, pfad)
    if stichworte:
        return _stichwortsuche(directory, tuple(w.lower() for w in stichworte), grenze)
    _, notes = read_state(directory, wait=wait)
    save = _load(directory / "Save.save")
    zeilen = ["Gelesen:"]
    for note in notes:
        if note.field not in FORM_FELDER:
            continue
        zeilen.append(f"  {note.field}: {note.path or '-'} ({note.how})")
        if note.path and save is not None:
            wert = _an_pfad(save, note.path)
            zeilen.append(f"    {form_skizze(wert)}")
    if save is None:
        return zeilen
    idx = index_keys(save)
    kandidaten = sorted(
        (pfad, name, idx.counts.get(name, 0), wert)
        for name, (pfad, wert, _tiefe) in idx.by_name.items()
        if any(w in name.lower() for w in FORM_STICHWORTE))
    zeilen.append(f"Kandidaten im Save.save ({len(kandidaten)}):")
    for pfad, name, anzahl, wert in kandidaten[:grenze]:
        mal = f" ({anzahl}x)" if anzahl > 1 else ""
        zeilen.append(f"  {pfad}{mal}: {form_skizze(wert, tiefe=2)}")
    if grenze is not None and len(kandidaten) > grenze:
        zeilen.append(f"  … und {len(kandidaten) - grenze} weitere")
    return zeilen


def _knoten_zeigen(directory: Path, pfad: str) -> list[str]:
    """Einen Knoten ganz: jeder Schluessel eine Zeile, ohne Breitengrenze.

    `$` vorn ist freiwillig -- in PowerShell ist es der Beginn einer
    Variablen, und `$.content` ohne Anfuehrungszeichen waere eine Falle.
    """
    if not pfad.startswith("$"):
        pfad = "$." + pfad.lstrip(".")
    for datei in ("Save.save", "WorldSave.save", "MetaSave.save"):
        data = _load(directory / datei)
        if data is None:
            continue
        gefunden, wert = _an_pfad_gefunden(data, pfad)
        if not gefunden:
            continue
        zeilen = [f"{datei} {pfad}: {form_skizze(wert, tiefe=0)}"]
        if isinstance(wert, dict):
            for k, v in wert.items():
                zeilen.append(f"  {k}: {form_skizze(v, tiefe=2)}")
        else:
            zeilen.append(f"  {form_skizze(wert, tiefe=3, breite=None)}")
        return zeilen
    return [f"{pfad} nicht gefunden, in keiner der drei Dateien."]


def _an_pfad_gefunden(data: Any, pfad: str) -> tuple[bool, Any]:
    cur = data
    for schluessel, stelle in re.findall(r"\.([^.\[]+)|\[(\d+)\]", pfad):
        if schluessel and isinstance(cur, dict) and schluessel in cur:
            cur = cur[schluessel]
        elif stelle and isinstance(cur, list) and int(stelle) < len(cur):
            cur = cur[int(stelle)]
        else:
            return False, None
    return True, cur


def _stichwortsuche(directory: Path, woerter: tuple[str, ...], grenze: int | None) -> list[str]:
    zeilen: list[str] = []
    for datei in ("Save.save", "WorldSave.save", "MetaSave.save"):
        data = _load(directory / datei)
        if data is None:
            continue
        idx = index_keys(data)
        kandidaten = sorted(
            (pfad, name, idx.counts.get(name, 0), wert)
            for name, (pfad, wert, _tiefe) in idx.by_name.items()
            if any(w in name.lower() for w in woerter))
        zeilen.append(f"{datei} ({len(kandidaten)}):")
        for pfad, name, anzahl, wert in kandidaten[:grenze]:
            mal = f" ({anzahl}x)" if anzahl > 1 else ""
            zeilen.append(f"  {pfad}{mal}: {form_skizze(wert, tiefe=3)}")
        if grenze is not None and len(kandidaten) > grenze:
            zeilen.append(f"  … und {len(kandidaten) - grenze} weitere")
    return zeilen


def _an_pfad(data: Any, pfad: str) -> Any:
    """'$.a.b[3].c' zurueck zum Wert -- die Pfade aus `index_keys`."""
    return _an_pfad_gefunden(data, pfad)[1]


def append_run_log(state: GameState, run_id: str, runs_dir: Path = Path("runs")) -> Path:
    """Jeden Zustand als Zeile in runs/<run_id>.jsonl -- Grundlage fuer analyze_runs."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    target = runs_dir / f"{run_id}.jsonl"
    with target.open("a", encoding="utf-8") as fh:
        fh.write(state.to_json() + "\n")
    return target
