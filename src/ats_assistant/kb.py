"""Wissensbasis: Aufbau, Befüllung und Nachschlag.

Das Wiki ist eine Quelle unter mehreren. Phase 0 hat gezeigt, dass der
Spielstand das Vokabular selbst mitbringt -- 169 Gebäude, 65 Effekte, die
vollständige Warenliste. Deshalb gibt es `save_ids`: was dort steht, ist
belegt, und was das Wiki nicht liefert, fällt damit auf.
"""

from __future__ import annotations

import csv
import json
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


def connect(path: Path | str = "kb.sqlite") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
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
