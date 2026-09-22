"""Die Werkzeuge aus SPEC.md Phase 4 als gewoehnliche Funktionen.

Getrennt vom MCP-Server, damit sie ohne ihn aufrufbar und testbar sind. Der
Server ist nur die Huelle.

Ausgaben sind Dictionaries aus Zahlen und Namen -- nie Bilder, nie Rohtext aus
dem Spielstand. Das ist das Leitprinzip: das Sehen passiert hier, das Urteilen
im Modell.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import analysis, kb
from .forecast import food_forecast as _food_forecast
from .forecast import impatience_forecast as _impatience_forecast
from .save_reader import GameState, append_run_log, read_state

log = logging.getLogger(__name__)


def _zustand_als_dict(state: GameState) -> dict:
    """Der Zustand fuer das Modell: Zahlen und Namen, keine Zeitreihen.

    Die Reihen haben 180 Stuetzstellen je Ware -- das sind zehntausende Zahlen
    und hat im Kontext eines Sprachmodells nichts verloren. Was daraus folgt,
    rechnet food_forecast aus.
    """
    return {
        "zeitpunkt": state.captured_at,
        "spielzeit": state.game_time,
        "jahr": state.year,
        "jahreszeit": state.season,
        "biom": state.biome,
        "prestige": state.prestige,
        "prestige_roh": state.prestige_raw,
        "bevoelkerung": state.population,
        "spezies": state.species,
        "feindseligkeit": state.hostility,
        "ungeduld": state.impatience,
        "ungeduld_schwelle": state.impatience_to_lose,
        "reputation": state.reputation,
        "reputation_ziel": state.reputation_to_win,
        "lager": state.storage,
        "gebaeude": len(state.buildings),
        "lichtungen": state.glades,
        "vorkommen": state.deposits,
        "grundsteine": state.cornerstones,
        "gewonnen": state.won,
        "verloren": state.lost,
        "reihen_vorhanden": sorted(state.category_trends),
    }


def get_state(save_dir: str | Path, runs_dir: str | Path = "runs",
              run_id: str | None = None, protokollieren: bool = True,
              auf_ruhe_warten: bool = True) -> dict:
    """Aktueller Zustand aus dem Spielstand.

    `auf_ruhe_warten` deckt den Regelfall ab: das Buendel ist nicht atomar,
    also wird gewartet, bis sich nichts mehr ruehrt. Wer weiss, dass gerade
    nicht geschrieben wird, spart sich das.
    """
    state, notes = read_state(Path(save_dir), wait=auf_ruhe_warten)
    if protokollieren and state.game_time is not None:
        kennung = run_id or f"{state.biome or 'lauf'}-{int(state.game_time)}"
        append_run_log(state, kennung, Path(runs_dir))
    fehlend = [n.field for n in notes if n.how == "fehlt"]
    out = _zustand_als_dict(state)
    if fehlend:
        out["nicht_gefunden"] = fehlend
    return out


def read_choice() -> dict:
    """Auswahlbildschirm -- noch nicht gebaut, und die Frage ist offen.

    Die Spec sieht dafuer Bildschirmauslesung vor. Ob es die braucht, ist
    aber nicht geprueft: das Spiel muss die angebotenen Grundsteine
    irgendwo im Zustand halten, sonst ueberstuende eine offene Auswahl
    kein Laden. `tools/find_choice.py` beantwortet das an einem echten
    Spielstand, statt es zu vermuten.
    """
    return {
        "verfuegbar": False,
        "grund": ("Noch nicht gebaut. Ob der Spielstand die Auswahl mitfuehrt, "
                  "klaert `python tools/find_choice.py scan --save <Save.save>` "
                  "bei offenem Auswahlbildschirm -- erst danach steht fest, ob "
                  "Phase 3 Bildschirmauslesung braucht."),
    }


def query_kb(name: str, entity: str | None = None, db: str | Path = "kb.sqlite") -> dict:
    """Nachschlag in der Wissensbasis, deutsch oder englisch."""
    conn = kb.connect(db)
    try:
        namen = kb.lookup(conn, name)
        treffer: dict[str, Any] = {"gesucht": name, "namen": namen}

        # Ware? Dann die Zahlen aus den Spieldaten dazu.
        kandidaten = {name} | {n["en"] for n in namen if n["en"]}
        for kandidat in kandidaten:
            zeile = conn.execute(
                "SELECT en, save_id, category, eatable, eating_fullness, burnable, "
                "burning_time, sell_value, buy_value, display_key, source_page "
                "FROM resources WHERE en = ? COLLATE NOCASE OR save_id = ?",
                (kandidat, kandidat),
            ).fetchone()
            if zeile:
                treffer["ware"] = dict(zeile)
                seite = conn.execute(
                    "SELECT game_version, warning FROM source_pages WHERE title = ?",
                    (zeile["source_page"] or "",),
                ).fetchone()
                if seite and seite["warning"]:
                    treffer["warnung"] = seite["warning"]
                break

        if entity == "building" or "ware" not in treffer:
            zeile = conn.execute(
                "SELECT en, cost, worker_slots, source_page FROM buildings "
                "WHERE en = ? COLLATE NOCASE", (name,)).fetchone()
            if zeile:
                treffer["gebaeude"] = dict(zeile)

        if not namen and "ware" not in treffer and "gebaeude" not in treffer:
            treffer["hinweis"] = (
                "Nichts gefunden. Die Wissensbasis ist erst teilweise gefüllt: "
                "Waren stehen drin, Grundsteine und Rezepte noch nicht.")
        return treffer
    finally:
        conn.close()


def food_forecast(runs_dir: str | Path = "runs", run_id: str | None = None,
                  kategorie: str = "Food", jahreszeit_sekunden: float | None = None) -> dict:
    """Nahrungsreichweite aus den letzten beiden Mitschriften."""
    zustaende, quelle = _letzte_zustaende(runs_dir, run_id)
    if len(zustaende) < 2:
        return {"verfuegbar": False,
                "grund": ("Es braucht zwei Spielstände. Das Spiel schreibt etwa alle 300 "
                          "Spielzeitsekunden -- nach dem nächsten Schreibvorgang geht es.")}

    vorher, aktuell = _als_zustand(zustaende[-2]), _als_zustand(zustaende[-1])
    f = _food_forecast(aktuell, vorher, category=kategorie,
                       season_seconds=jahreszeit_sekunden)
    return {
        "verfuegbar": f.rate_per_second is not None,
        "quelle": quelle,
        "bestand": f.stock,
        "rate_je_spielzeitsekunde": f.rate_per_second,
        "reichweite_sekunden": f.runway_seconds,
        "stuetzstellen": f.samples_used,
        "warnung": f.warning,
    }


def impatience_forecast(runs_dir: str | Path = "runs", run_id: str | None = None,
                        sekunden: float = 300.0) -> dict:
    """Ungeduldsvorhersage -- das Modell ist gegen Messungen geprueft."""
    zustaende, quelle = _letzte_zustaende(runs_dir, run_id)
    if not zustaende:
        return {"verfuegbar": False, "grund": "Keine Mitschrift vorhanden."}
    f = _impatience_forecast(_als_zustand(zustaende[-1]), seconds_ahead=sekunden)
    return {
        "verfuegbar": f.per_second is not None,
        "quelle": quelle,
        "jetzt": f.current,
        "je_spielzeitsekunde": f.per_second,
        "schwelle": f.threshold,
        "sekunden_bis_verlust": f.seconds_until_loss,
        "in_zukunft": f.projected,
        "warnung": f.warning,
    }


def log_event(text: str, runs_dir: str | Path = "runs", run_id: str | None = None) -> dict:
    """Freitextnotiz in den Lauf schreiben."""
    runs = Path(runs_dir)
    runs.mkdir(parents=True, exist_ok=True)
    kennung = run_id or _neueste_mitschrift(runs) or "notizen"
    ziel = runs / f"{kennung}.jsonl"
    eintrag = {"typ": "notiz", "zeitpunkt": datetime.now(timezone.utc).isoformat(), "text": text}
    with ziel.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    return {"geschrieben": str(ziel), "eintrag": eintrag}


def analyze_runs(n: int = 10, save_dir: str | Path | None = None,
                 runs_dir: str | Path = "runs") -> dict:
    """Die letzten n Laeufe gegenueberstellen."""
    records: list[dict] = []
    quelle = None
    if save_dir:
        meta_pfad = Path(save_dir) / "MetaSave.save"
        if meta_pfad.exists():
            try:
                meta = json.loads(meta_pfad.read_text(encoding="utf-8", errors="replace"))
                records = ((meta.get("gamesHistory") or {}).get("records")) or []
                quelle = "MetaSave.gamesHistory"
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("MetaSave nicht lesbar: %s", exc)

    if not records:
        return {"verfuegbar": False,
                "grund": ("Keine Laufhistorie gefunden. Sie steht in MetaSave.save unter "
                          "gamesHistory.records -- dafür muss save_dir gesetzt sein.")}

    vergleich = analysis.compare_runs(records, n)
    return {
        "verfuegbar": True,
        "quelle": quelle,
        "laeufe": vergleich.laeufe,
        "siege": vergleich.siege,
        "niederlagen": vergleich.niederlagen,
        "belastbar": vergleich.belastbar,
        "hinweis": vergleich.hinweis,
        "jahre_median": {"sieg": vergleich.jahre_sieg, "niederlage": vergleich.jahre_niederlage},
        "nach_biom": vergleich.nach_biom,
        "nach_schwierigkeit": vergleich.nach_schwierigkeit,
        "grundsteine": [vars(m) for m in vergleich.grundsteine[:10]],
        "gebaeude": [vars(m) for m in vergleich.gebaeude[:10]],
        "kurzfassung": analysis.summarise(vergleich),
    }


# --------------------------------------------------------------------------


class _Zustand:
    """Minimalhuelle, damit forecast auf Mitschriften wie auf GameState arbeitet."""

    def __init__(self, daten: dict) -> None:
        self.game_time = daten.get("game_time")
        self.impatience = daten.get("impatience")
        self.impatience_to_lose = daten.get("impatience_to_lose")
        self.impatience_per_second = daten.get("impatience_per_second")
        self.impatience_bonus_rate = daten.get("impatience_bonus_rate")
        self.category_trends = daten.get("category_trends") or {}
        self.goods_trends = daten.get("goods_trends") or {}


def _als_zustand(daten: dict) -> _Zustand:
    return _Zustand(daten)


def _neueste_mitschrift(runs: Path) -> str | None:
    dateien = sorted(runs.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return dateien[0].stem if dateien else None


def _letzte_zustaende(runs_dir: str | Path, run_id: str | None) -> tuple[list[dict], str | None]:
    runs = Path(runs_dir)
    kennung = run_id or _neueste_mitschrift(runs)
    if not kennung:
        return [], None
    eintraege = [e for e in analysis.read_run_log(runs / f"{kennung}.jsonl")
                 if e.get("typ") != "notiz"]
    return eintraege, kennung
