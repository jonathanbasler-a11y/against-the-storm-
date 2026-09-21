"""Wissensbasis: Aufbau, Befüllung und Nachschlag.

Das Wiki ist eine Quelle unter mehreren. Phase 0 hat gezeigt, dass der
Spielstand das Vokabular selbst mitbringt -- 169 Gebäude, 65 Effekte, die
vollständige Warenliste. Deshalb gibt es `save_ids`: was dort steht, ist
belegt, und was das Wiki nicht liefert, fällt damit auf.
"""

from __future__ import annotations

import csv
import json
import re
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA = Path(__file__).with_name("kb_schema.sql")

# Reihenfolge nach Belastbarkeit: eine bestätigte Zeile darf nie von einer
# geratenen überschrieben werden.
CONFIDENCE_RANK = {
    "screenshot+save": 5,
    "screenshot": 4,
    "save_id": 3,
    "spec_seed": 2,
    "observed": 1,
    "guessed": 0,
}


# CREATE TABLE IF NOT EXISTS legt nur neue Tabellen an. Kommt spaeter eine
# Spalte dazu, bleibt eine bestehende Datenbank unveraendert -- und der naechste
# Schreibzugriff scheitert mit "table species has no column named resilience".
# Deshalb wird nach dem Schema geprueft, was fehlt, und ergaenzt.
SPALTEN_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);", re.DOTALL | re.IGNORECASE)
CONSTRAINT_ANFAENGE = ("primary", "foreign", "unique", "check", "constraint")


def _erwartete_spalten(schema: str) -> dict[str, list[tuple[str, str]]]:
    """Aus dem Schema lesen, welche Spalten eine Tabelle haben soll."""
    out: dict[str, list[tuple[str, str]]] = {}
    for tabelle, koerper in SPALTEN_RE.findall(schema):
        spalten: list[tuple[str, str]] = []
        for zeile in koerper.split("\n"):
            zeile = zeile.split("--", 1)[0].strip().rstrip(",")
            if not zeile or zeile.lower().startswith(CONSTRAINT_ANFAENGE):
                continue
            teile = zeile.split()
            if len(teile) < 2:
                continue
            # Typ ohne Zusaetze: ALTER TABLE ADD COLUMN vertraegt kein
            # PRIMARY KEY und keine Fremdschluesselangabe.
            spalten.append((teile[0], teile[1]))
        out[tabelle] = spalten
    return out


def migrate(conn: sqlite3.Connection, schema: str | None = None) -> list[str]:
    """Fehlende Spalten ergaenzen. Nur additiv -- nichts wird geloescht."""
    schema = schema if schema is not None else SCHEMA.read_text(encoding="utf-8")
    ergaenzt: list[str] = []
    for tabelle, spalten in _erwartete_spalten(schema).items():
        try:
            vorhanden = {r[1] for r in conn.execute(f"PRAGMA table_info({tabelle})")}
        except sqlite3.DatabaseError:
            continue
        if not vorhanden:
            continue    # Tabelle gibt es nicht, das Schema legt sie gleich an
        for name, typ in spalten:
            if name in vorhanden:
                continue
            conn.execute(f"ALTER TABLE {tabelle} ADD COLUMN {name} {typ}")
            ergaenzt.append(f"{tabelle}.{name}")
    if ergaenzt:
        conn.commit()
        log.info("Wissensbasis ergaenzt: %s", ", ".join(ergaenzt))
    return ergaenzt


def connect(path: Path | str = "kb.sqlite") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    schema = SCHEMA.read_text(encoding="utf-8")
    conn.executescript(schema)
    migrate(conn, schema)
    return conn


def seed_name_map(conn: sqlite3.Connection, csv_path: Path) -> dict[str, int]:
    """Namenstabelle aus der CSV übernehmen, ohne Belegtes zu überschreiben."""
    zaehler: dict[str, int] = {}
    with Path(csv_path).open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            de = (row.get("de") or "").strip()
            en = (row.get("en") or "").strip()
            if not de and not en:
                continue
            conf = (row.get("confidence") or "guessed").strip()
            kind = (row.get("kind") or "").strip()
            vorhanden = conn.execute(
                "SELECT confidence FROM name_map WHERE en = ? AND de = ? AND kind = ?",
                (en, de, kind),
            ).fetchone()
            if vorhanden and CONFIDENCE_RANK.get(vorhanden["confidence"], 0) > CONFIDENCE_RANK.get(conf, 0):
                continue
            conn.execute(
                "INSERT OR REPLACE INTO name_map "
                "(en, de, kind, category, confidence, source, verified_at, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (en, de, kind, row.get("category"), conf, row.get("source"),
                 row.get("verified_at"), row.get("note")),
            )
            zaehler[conf] = zaehler.get(conf, 0) + 1
    conn.commit()
    return zaehler


def import_save_ids(conn: sqlite3.Connection, ids_dir: Path) -> dict[str, int]:
    """Die Textdateien aus `kb_probe.py --dump-ids` einlesen.

    Dateinamen sehen aus wie `MetaSave__root_content_buildings.txt`; daraus
    lassen sich Quelldatei, Pfad und Art ableiten.
    """
    ids_dir = Path(ids_dir)
    now = datetime.now(timezone.utc).isoformat()
    zaehler: dict[str, int] = {}
    for datei in sorted(ids_dir.glob("*.txt")):
        stem = datei.stem
        quelle, _, pfad = stem.partition("__")
        art = _art_aus_pfad(pfad)
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            wert = zeile.strip()
            if not wert:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO save_ids (id, kind, source_file, source_path, imported_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (wert, art, quelle, pfad.replace("_", "."), now),
            )
            zaehler[art] = zaehler.get(art, 0) + 1
    conn.commit()
    return zaehler


def _art_aus_pfad(pfad: str) -> str:
    p = pfad.lower()
    for hinweis, art in (
        ("building", "building"), ("effect", "effect"), ("good", "good"),
        ("modifier", "modifier"), ("event", "event"), ("relic", "relic"),
        ("upgrade", "upgrade"), ("race", "species"),
    ):
        if hinweis in p:
            return art
    return "unbekannt"


def record_page(conn: sqlite3.Connection, title: str, revision_id: int | None,
                revised_at: str | None, game_version: str | None,
                expected_version: str) -> str | None:
    """Wiki-Versionsstand festhalten und bei Abweichung warnen."""
    warnung = None
    if game_version and not expected_version.startswith(game_version):
        warnung = (f"Seite beschreibt Spielversion {game_version}, "
                   f"gespielt wird {expected_version}")
    conn.execute(
        "INSERT OR REPLACE INTO source_pages "
        "(title, revision_id, revised_at, fetched_at, game_version, warning) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (title, revision_id, revised_at, datetime.now(timezone.utc).isoformat(),
         game_version, warnung),
    )
    conn.commit()
    return warnung


def lookup(conn: sqlite3.Connection, name: str) -> list[dict]:
    """Nachschlag, der deutsche und englische Namen akzeptiert."""
    treffer = conn.execute(
        "SELECT en, de, kind, category, confidence, source, note FROM name_map "
        "WHERE de = ? COLLATE NOCASE OR en = ? COLLATE NOCASE "
        "ORDER BY CASE confidence "
        "  WHEN 'screenshot+save' THEN 0 WHEN 'screenshot' THEN 1 WHEN 'save_id' THEN 2 "
        "  WHEN 'spec_seed' THEN 3 WHEN 'observed' THEN 4 ELSE 5 END",
        (name, name),
    ).fetchall()
    return [dict(r) for r in treffer]


def coverage(conn: sqlite3.Connection) -> dict:
    """Was steckt drin, und wie belastbar ist es?"""
    out: dict = {"name_map": {}, "save_ids": {}, "tabellen": {}}
    for row in conn.execute("SELECT confidence, COUNT(*) n FROM name_map GROUP BY confidence"):
        out["name_map"][row["confidence"]] = row["n"]
    for row in conn.execute("SELECT kind, COUNT(*) n FROM save_ids GROUP BY kind"):
        out["save_ids"][row["kind"]] = row["n"]
    for tabelle in ("resources", "biomes", "cornerstones", "buildings",
                    "recipes", "species", "prestige", "glade_events", "source_pages"):
        out["tabellen"][tabelle] = conn.execute(f"SELECT COUNT(*) n FROM {tabelle}").fetchone()["n"]
    return out


def unmatched_save_ids(conn: sqlite3.Connection, kind: str | None = None) -> list[str]:
    """IDs aus dem Spielstand, zu denen die Wissensbasis nichts weiss.

    Das ist die Sollvorgabe für den Scraper: was hier steht, hat das Wiki
    nicht geliefert.
    """
    sql = ("SELECT s.id FROM save_ids s "
           "LEFT JOIN name_map n ON n.en = s.id "
           "LEFT JOIN buildings b ON b.en = s.id "
           "WHERE n.en IS NULL AND b.en IS NULL")
    params: tuple = ()
    if kind:
        sql += " AND s.kind = ?"
        params = (kind,)
    return [r["id"] for r in conn.execute(sql + " ORDER BY s.id", params)]


# --------------------------------------------------------------------------
# Datenseiten des Wikis
# --------------------------------------------------------------------------
#
# Die Vorlage Dataloader/Goods traegt die Spieldaten selbst: m_Name ist genau
# die Zeichenkette, die auch im Spielstand steht, displayName_key ist der
# Lokalisierungsschluessel, und eatable/eatingFullness/canBeBurned sind das
# Nahrungs- und Brennstoffmodell in Zahlen. Das ist keine Wiki-Prosa und wird
# deshalb auch nicht wie solche behandelt.


def _zahl(wert: str | None) -> float | None:
    if wert is None:
        return None
    try:
        return float(str(wert).strip())
    except (TypeError, ValueError):
        return None


def _flag(wert: str | None) -> int | None:
    zahl = _zahl(wert)
    return None if zahl is None else int(bool(zahl))


def import_guid_index(conn: sqlite3.Connection, eintraege: list[dict]) -> int:
    n = 0
    for e in eintraege:
        guid = (e.get("guid") or "").strip()
        if not guid:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO guid_index (guid, page_name, domain) VALUES (?, ?, ?)",
            (guid, (e.get("page_name") or "").strip(), (e.get("domain") or "").strip()),
        )
        n += 1
    conn.commit()
    return n


def import_goods(conn: sqlite3.Connection, eintraege: list[dict],
                 source_page: str | None = None) -> int:
    """Waren aus Dataloader/Goods uebernehmen, Kategorie ueber guid_index."""
    n = 0
    for e in eintraege:
        name = (e.get("page_name") or "").strip()
        if not name:
            continue
        cat_guid = (e.get("category") or "").strip() or None
        kategorie = None
        if cat_guid:
            zeile = conn.execute(
                "SELECT page_name FROM guid_index WHERE guid = ?", (cat_guid,)).fetchone()
            if zeile:
                kategorie = zeile["page_name"]
        conn.execute(
            "INSERT OR REPLACE INTO resources "
            "(en, save_id, category, category_guid, guid, display_name_en, display_key, "
            " description_en, eatable, eating_fullness, burnable, burning_time, "
            " sell_value, buy_value, source_page) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, (e.get("m_Name") or "").strip() or None, kategorie, cat_guid,
             (e.get("guid") or "").strip() or None,
             e.get("displayName_key_en"), e.get("displayName_key"),
             e.get("description_key_en"),
             _flag(e.get("eatable")), _zahl(e.get("eatingFullness")),
             _flag(e.get("canBeBurned")), _zahl(e.get("burningTime")),
             _zahl(e.get("tradingSellValue")), _zahl(e.get("tradingBuyValue")),
             source_page),
        )
        n += 1
    conn.commit()
    return n


def link_name_map_to_resources(conn: sqlite3.Connection) -> int:
    """Die englischen IDs der Namenstabelle an die Warentabelle binden.

    Die Namenstabelle kennt `oil`, die Warentabelle `Oil` mit save_id
    `[Crafting] Oil`. Wo sich beides trifft, ist die englische Seite belegt --
    und es faellt auf, wo die deutsche Seite noch fehlt.
    """
    n = 0
    for zeile in conn.execute("SELECT en, save_id, display_name_en FROM resources"):
        kandidaten = {zeile["en"], zeile["display_name_en"] or "",
                      (zeile["en"] or "").lower().replace(" ", "_")}
        for kandidat in kandidaten:
            if not kandidat:
                continue
            n += conn.execute(
                "UPDATE name_map SET note = COALESCE(note || '; ', '') || ? "
                "WHERE en = ? AND (note IS NULL OR note NOT LIKE '%Save-ID:%')",
                (f"Save-ID: {zeile['save_id']}", kandidat),
            ).rowcount
    conn.commit()
    return n


def food_goods(conn: sqlite3.Connection) -> list[dict]:
    """Essbare Waren mit ihrer Saettigung -- Eingang fuer food_forecast."""
    return [dict(r) for r in conn.execute(
        "SELECT en, save_id, category, eating_fullness FROM resources "
        "WHERE eatable = 1 ORDER BY eating_fullness DESC, en")]


def missing_german(conn: sqlite3.Connection) -> list[dict]:
    """Waren, für die der deutsche Name noch fehlt oder nur geraten ist.

    display_key ist der Lokalisierungsschluessel des Spiels -- damit waere der
    deutsche Name ein Nachschlag statt einer Vermutung.
    """
    return [dict(r) for r in conn.execute(
        "SELECT r.en, r.save_id, r.display_key, n.de, n.confidence "
        "FROM resources r LEFT JOIN name_map n ON n.en = r.en OR n.en = LOWER(r.en) "
        "WHERE n.de IS NULL OR n.confidence IN ('guessed', 'observed') "
        "ORDER BY r.en")]


# --------------------------------------------------------------------------
# Tabellen aus dem gerenderten HTML
# --------------------------------------------------------------------------

def _spalte(zeile: dict, *namen: str) -> str | None:
    """Erste passende Spalte, unabhaengig von Gross- und Kleinschreibung.

    Die Seiten benennen dieselbe Sache verschieden: "Hunger threshold" auf
    einer, "Hunger Tolerance" auf der anderen.
    """
    klein = {k.lower().strip(): v for k, v in zeile.items() if isinstance(k, str)}
    for name in namen:
        wert = klein.get(name.lower())
        if wert not in (None, ""):
            return str(wert).strip()
    return None


def _dauer(wert: str | None) -> float | None:
    """'02:00' -> 120.0, '120' -> 120.0."""
    if not wert:
        return None
    text = wert.strip()
    if ":" in text:
        teile = text.split(":")
        try:
            return float(teile[0]) * 60 + float(teile[1])
        except (ValueError, IndexError):
            return None
    return _zahl(text)


def import_species(conn: sqlite3.Connection, zeilen: list[dict],
                   source_page: str | None = None) -> int:
    n = 0
    for z in zeilen:
        name = _spalte(z, "Species")
        if not name or name.lower() == "species":
            continue
        vorhanden = conn.execute("SELECT * FROM species WHERE en = ?", (name,)).fetchone()
        alt = dict(vorhanden) if vorhanden else {}
        werte = {
            "base_resolve": _zahl(_spalte(z, "Base Resolve")) or alt.get("base_resolve"),
            "break_seconds": _dauer(_spalte(z, "Break Interval", "Break interval"))
                             or alt.get("break_seconds"),
            "hunger_tolerance": _zahl(_spalte(z, "Hunger Tolerance", "Hunger threshold"))
                                or alt.get("hunger_tolerance"),
            "decadence": _zahl(_spalte(z, "Decadence")) or alt.get("decadence"),
            "resilience": _spalte(z, "Resilience") or alt.get("resilience"),
            "demand": _zahl(_spalte(z, "Demand", "Demand (Resolve Threshold)"))
                      or alt.get("demand"),
            "comfort": _spalte(z, "Comfort") or alt.get("comfort"),
            "specialization": _spalte(z, "Proficiency", "Specialization")
                              or alt.get("specialization"),
            "reputation_ratio": _zahl(_spalte(z, "Species Resolve to Reputation Ratio"))
                                or alt.get("reputation_ratio"),
        }
        conn.execute(
            "INSERT OR REPLACE INTO species (en, base_resolve, break_seconds, "
            "hunger_tolerance, decadence, resilience, demand, comfort, specialization, "
            "reputation_ratio, source_page) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, werte["base_resolve"], werte["break_seconds"], werte["hunger_tolerance"],
             werte["decadence"], werte["resilience"], werte["demand"], werte["comfort"],
             werte["specialization"], werte["reputation_ratio"],
             source_page or alt.get("source_page")),
        )
        n += 1
    conn.commit()
    return n


def import_difficulty(conn: sqlite3.Connection, zeilen: list[dict],
                      source_page: str | None = None) -> int:
    n = 0
    for z in zeilen:
        name = _spalte(z, "Difficulty")
        if not name or name.lower() == "difficulty":
            continue
        conn.execute(
            "INSERT OR REPLACE INTO difficulty (en, rewards_multiplier, seal_fragments, "
            "tile_reach_max, experience_multiplier, score_multiplier, blight_footprint_rate, "
            "blight_corruption_rate, hostility_multiplier, source_page) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (name, _zahl(_spalte(z, "Rewards Multiplier")),
             _zahl(_spalte(z, "Seal Fragments Rewarded")),
             _zahl(_spalte(z, "Tile Reach Max")),
             _zahl(_spalte(z, "Experience Multiplier")),
             _zahl(_spalte(z, "Score Multiplier")),
             _zahl(_spalte(z, "Blight Footprint Rate")),
             _zahl(_spalte(z, "Blight Corruption Rate")),
             _zahl(_spalte(z, "Hostility Multiplier")),
             source_page),
        )
        n += 1
    conn.commit()
    return n


def import_cornerstones(conn: sqlite3.Connection, zeilen: list[dict],
                        origin: str | None = None,
                        source_page: str | None = None) -> int:
    """Grundsteine aus einer Listenseite.

    `origin` kommt aus der Seite, nicht aus einer Spalte: die Ankreuzspalten
    heissen alle "Sources" und sind ohne ihre Unterueberschriften nicht zu
    deuten. Welche Liste einen Namen fuehrt, sagt dagegen eindeutig, woher er
    kommt -- und dafuer gibt es je Herkunft eine eigene Seite.
    """
    n = 0
    for z in zeilen:
        name = _spalte(z, "Name")
        if not name or name.lower() == "name":
            continue      # die Tabellen wiederholen ihre Kopfzeile im Koerper
        rarity = _spalte(z, "Rarity")
        if rarity and rarity.lower() in ("rarity", "none"):
            rarity = None
        beschreibung = _spalte(z, "Description")
        vorhanden = conn.execute(
            "SELECT origin FROM cornerstones WHERE en = ?", (name,)).fetchone()
        herkunft = origin
        if vorhanden and vorhanden["origin"] and origin and origin not in vorhanden["origin"]:
            herkunft = f"{vorhanden['origin']}, {origin}"
        elif vorhanden and vorhanden["origin"] and not origin:
            herkunft = vorhanden["origin"]
        conn.execute(
            "INSERT OR REPLACE INTO cornerstones (en, rarity, effect_text, origin, source_page) "
            "VALUES (?,?,?,?,?)",
            (name, rarity, beschreibung, herkunft, source_page),
        )
        n += 1
    conn.commit()
    return n


def import_glade_events(conn: sqlite3.Connection, zeilen: list[tuple[str, str]],
                        source_page: str | None = None) -> int:
    """Lichtungsereignisse samt Reputationsbelohnung.

    Die Seite gruppiert sie in Tabellen, deren Kopfzeile die Belohnung ist
    ("1 Reputation Points"). Der Kopf ist also der Wert, nicht der Spaltenname.
    """
    n = 0
    for name, belohnung in zeilen:
        name = (name or "").strip()
        if not name:
            continue
        conn.execute(
            "INSERT OR REPLACE INTO glade_events (en, reward, source_page) VALUES (?,?,?)",
            (name, belohnung, source_page),
        )
        n += 1
    conn.commit()
    return n
