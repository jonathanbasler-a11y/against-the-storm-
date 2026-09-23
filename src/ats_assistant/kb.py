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

from .wikihtml import entdoppeln

log = logging.getLogger(__name__)

SCHEMA = Path(__file__).with_name("kb_schema.sql")

# Reihenfolge nach Belastbarkeit: eine bestätigte Zeile darf nie von einer
# geratenen überschrieben werden. `localization` steht obenauf, weil es die
# Zeichenkette selbst ist, die das Spiel anzeigt -- ein Screenshot ist eine
# Aufnahme davon und kann sich verlesen, die Tabelle nicht.
CONFIDENCE_RANK = {
    "localization": 6,
    "screenshot+save": 5,
    "screenshot": 4,
    "save_id": 3,
    "spec_seed": 2,
    "observed": 1,
    "guessed": 0,
}


_NICHT_WORT = re.compile(r"[^a-z0-9]+")


def _normalform(name: str) -> str:
    """"Alchemist's Hut" -> alchemists_hut. Siehe localization.normalisieren."""
    ohne = (name or "").lower().replace("'", "").replace("’", "")
    return _NICHT_WORT.sub("_", ohne).strip("_")


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


INDEX_RE = re.compile(r"CREATE\s+INDEX[^;]*;", re.IGNORECASE)


def connect(path: Path | str = "kb.sqlite") -> sqlite3.Connection:
    """Oeffnen, Schema anlegen, fehlende Spalten ergaenzen, dann Indizes.

    Die Reihenfolge ist nicht beliebig: ein Index auf einer neuen Spalte
    scheitert an einer bestehenden Datenbank, solange die Spalte fehlt --
    "no such column: product". Erst die Tabellen, dann die Wanderung, dann
    die Indizes.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # Damit auch SQL auf der Normalform vergleichen kann: "Pickled Goods"
    # und pickled_goods sind derselbe Eintrag.
    conn.create_function("normalform", 1, _normalform)
    schema = SCHEMA.read_text(encoding="utf-8")

    indizes = INDEX_RE.findall(schema)
    conn.executescript(INDEX_RE.sub("", schema))
    migrate(conn, schema)
    for anweisung in indizes:
        conn.execute(anweisung.rstrip(";"))
    conn.commit()
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
                "(en, de, kind, category, confidence, source, verified_at, note, "
                " loc_key, en_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (en, de, kind, row.get("category"), conf, row.get("source"),
                 row.get("verified_at"), row.get("note"),
                 (row.get("loc_key") or "").strip() or None,
                 (row.get("en_id") or "").strip() or _normalform(en)),
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
    """Nachschlag, der deutsche und englische Namen akzeptiert.

    Auch der Bezeichner trifft: die Saat-Tabelle fuehrt `pickled_goods`, die
    Lokalisierung "Pickled Goods". Gesucht wird deshalb zusaetzlich auf der
    Normalform in en_id.
    """
    # Die Saat-Tabelle fuehrt Bezeichner, die es im Spiel nicht gibt --
    # `reeds` heisst dort "Reed". Der Nachschlag muss beide Wege kennen,
    # sonst findet der alte Bezeichner seine eigene Zeile nicht mehr.
    from . import localization      # lokal: kb ist die untere Schicht
    kennung = _normalform(name)
    kennung = _normalform(localization.ALIASE.get(kennung, kennung))
    # Nur aus Zeichen ("?", "—") wird die Kennung leer -- und traf dann jede
    # Zeile mit leerer en_id.
    kennung = kennung or None
    treffer = conn.execute(
        "SELECT en, de, kind, category, confidence, source, note, loc_key, en_id "
        "FROM name_map "
        "WHERE de = ? COLLATE NOCASE OR en = ? COLLATE NOCASE OR en_id = ? "
        "ORDER BY CASE confidence "
        "  WHEN 'localization' THEN 0 WHEN 'screenshot+save' THEN 1 "
        "  WHEN 'screenshot' THEN 2 WHEN 'save_id' THEN 3 "
        "  WHEN 'spec_seed' THEN 4 WHEN 'observed' THEN 5 ELSE 6 END",
        (name, name, kennung),
    ).fetchall()
    if not treffer and name.strip():
        # SQLite faltet mit NOCASE nur ASCII: "öl" fand "Öl" nicht.
        gefaltet = name.strip().casefold()
        treffer = [r for r in conn.execute(
            "SELECT en, de, kind, category, confidence, source, note, loc_key, en_id "
            "FROM name_map")
            if (r["de"] or "").casefold() == gefaltet or (r["en"] or "").casefold() == gefaltet]
    return [dict(r) for r in treffer]


def coverage(conn: sqlite3.Connection) -> dict:
    """Was steckt drin, und wie belastbar ist es?"""
    out: dict = {"name_map": {}, "save_ids": {}, "tabellen": {}}
    for row in conn.execute("SELECT confidence, COUNT(*) n FROM name_map GROUP BY confidence"):
        out["name_map"][row["confidence"]] = row["n"]
    for row in conn.execute("SELECT kind, COUNT(*) n FROM save_ids GROUP BY kind"):
        out["save_ids"][row["kind"]] = row["n"]
    for tabelle in ("resources", "biomes", "cornerstones", "buildings",
                    "recipes", "species", "prestige", "glade_events",
                    "source_pages", "retired_names"):
        out["tabellen"][tabelle] = conn.execute(f"SELECT COUNT(*) n FROM {tabelle}").fetchone()["n"]
    return out


def unmatched_save_ids(conn: sqlite3.Connection, kind: str | None = None) -> list[str]:
    """IDs aus dem Spielstand, zu denen die Wissensbasis nichts weiss.

    Das ist die Sollvorgabe für den Scraper: was hier steht, hat das Wiki
    nicht geliefert.
    """
    sql = ("SELECT s.id FROM save_ids s "
           "LEFT JOIN name_map n ON n.en = s.id OR n.en_id = normalform(s.id) "
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
        "FROM resources r LEFT JOIN name_map n "
        "  ON n.en = r.en OR n.en = LOWER(r.en) OR n.en_id = normalform(r.en) "
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
        # `or alt` machte aus einer echten 0 ein NULL oder den alten Wert.
        def neu_oder_alt(wert, feld, alt=alt):
            return wert if wert is not None else alt.get(feld)

        werte = {
            "base_resolve": neu_oder_alt(_zahl(_spalte(z, "Base Resolve")), "base_resolve"),
            "break_seconds": neu_oder_alt(
                _dauer(_spalte(z, "Break Interval", "Break interval")), "break_seconds"),
            "hunger_tolerance": neu_oder_alt(
                _zahl(_spalte(z, "Hunger Tolerance", "Hunger threshold")), "hunger_tolerance"),
            "decadence": neu_oder_alt(_zahl(_spalte(z, "Decadence")), "decadence"),
            "resilience": _spalte(z, "Resilience") or alt.get("resilience"),
            "demand": neu_oder_alt(
                _zahl(_spalte(z, "Demand", "Demand (Resolve Threshold)")), "demand"),
            "comfort": _spalte(z, "Comfort") or alt.get("comfort"),
            "specialization": _spalte(z, "Proficiency", "Specialization")
                              or alt.get("specialization"),
            "reputation_ratio": neu_oder_alt(
                _zahl(_spalte(z, "Species Resolve to Reputation Ratio")), "reputation_ratio"),
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


# --------------------------------------------------------------------------
# Rezepte
# --------------------------------------------------------------------------
#
# Eine Zutatenspalte sieht so aus: "5 Insects 5 Meat". Das sind keine zwei
# Zutaten, sondern zwei Alternativen fuer dieselbe -- das Spiel laesst die
# Wahl. Die zweite Spalte fuehrt die Alternativen der zweiten Zutat.

ZUTAT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s+([A-Za-z][A-Za-z' \-]*?)(?=\s+\d|$)")
STERNE_RE = re.compile(r"[★*]")
ZEIT_RE = re.compile(r"(\d+):(\d{2})")


def parse_zutaten(text: str | None) -> list[dict]:
    """'5 Insects 5 Meat' -> [{'menge': 5, 'ware': 'Insects'}, ...]."""
    if not text:
        return []
    out: list[dict] = []
    for menge, ware in ZUTAT_RE.findall(text.strip()):
        name = ware.strip()
        if not name:
            continue
        out.append({"menge": float(menge.replace(",", ".")), "ware": name})
    return out


def parse_grad(text: str | None) -> tuple[int | None, float | None]:
    """'★★ 2:06' -> (2, 126.0)."""
    if not text:
        return None, None
    sterne = len(STERNE_RE.findall(text)) or None
    m = ZEIT_RE.search(text)
    sekunden = float(m.group(1)) * 60 + float(m.group(2)) if m else None
    return sterne, sekunden


def _ist_gebaeude(conn: sqlite3.Connection, name: str) -> bool:
    """Kennt die Wissensbasis diesen Namen als Gebaeude?

    Seit die Namen aus der Lokalisierung kommen, stehen 226 Gebaeudenamen
    belegt in name_map. Damit laesst sich pruefen, ob eine Seite ein Gebaeude
    ist -- und nur dann darf ihr Titel als Gebaeude eines Rezepts gelten.
    """
    if not name:
        return False
    if conn.execute("SELECT 1 FROM buildings WHERE en = ?", (name,)).fetchone():
        return True
    return bool(conn.execute(
        "SELECT 1 FROM name_map WHERE kind = 'building' AND (en = ? OR en_id = ?)",
        (name, _normalform(name))).fetchone())


def import_prestige(conn: sqlite3.Connection, zeilen: list[dict],
                    source_page: str | None = None) -> int:
    """Die Prestigestufen von der Seite Difficulty.

    Der Tabellenkopf heisst dort zweimal "Description": die erste Spalte ist
    die Stufe, die zweite der Satz dazu. Der Leser des HTML haengt an den
    zweiten ein _2, und genau darueber wird sie geholt.
    """
    n = 0
    for z in zeilen:
        stufe = _zahl(_spalte(z, "Description", "Level", "Prestige"))
        modifikator = _spalte(z, "Modifier")
        if stufe is None or not modifikator:
            continue
        wirkung = _spalte(z, "Description_2", "Effect") or ""
        erklaerung = _spalte(z, "Explanation") or ""
        if erklaerung and erklaerung not in wirkung:
            wirkung = f"{wirkung} {erklaerung}".strip()
        conn.execute(
            "INSERT OR REPLACE INTO prestige (level, modifier_en, effect, source_page) "
            "VALUES (?,?,?,?)",
            (int(stufe), modifikator, wirkung or None, source_page),
        )
        n += 1
    conn.commit()
    return n


def import_blueprints(conn: sqlite3.Connection, zeilen: list[dict],
                      kategorie: str | None = None,
                      source_page: str | None = None) -> int:
    """Die Entwurfsliste: welches Gebaeude ab welcher Stufe zur Wahl steht.

    Das ist die halbe Antwort auf die zweite Frage der Spec. Ein Entwurf, den
    es auf dieser Stufe noch gar nicht gibt, kann nicht im Angebot stehen --
    und was immer verfuegbar ist, ist nie eine Ueberraschung.

    Ergaenzend, nicht ersetzend: die Baukosten kommen aus dem Wikitext und
    duerfen hier nicht verlorengehen.
    """
    n = 0
    for z in zeilen:
        name = _spalte(z, "Blueprint", "Building", "Name")
        if not name or name.lower() in ("blueprint", "building", "name"):
            continue
        freischaltung = _spalte(z, "Unlock or Upgrade", "Unlock", "Upgrade")
        conn.execute(
            "INSERT INTO buildings (en, unlock, category, source_page) VALUES (?,?,?,?) "
            "ON CONFLICT(en) DO UPDATE SET "
            "  unlock = COALESCE(excluded.unlock, buildings.unlock), "
            "  category = COALESCE(excluded.category, buildings.category), "
            "  source_page = COALESCE(buildings.source_page, excluded.source_page)",
            (name, freischaltung, kategorie, source_page),
        )
        n += 1
    conn.commit()
    return n


def import_recipes(conn: sqlite3.Connection, zeilen: list[dict],
                   source_page: str | None = None,
                   gebaeude_default: str | None = None) -> int:
    """Rezepte uebernehmen.

    Auf einer Gebaeudeseite steht keine Spalte "Building" -- das Gebaeude ist
    die Seite. Ohne diesen Rueckgriff haetten 193 von 193 Rezepten kein
    Gebaeude, und `food_advice` koennte sagen, was zu kochen waere, aber
    nicht worin. Gegriffen wird nur, wenn der Seitentitel wirklich ein
    Gebaeude ist; sonst stuenden Rezepte unter Biomnamen.
    """
    rueckgriff = (gebaeude_default
                  if gebaeude_default and _ist_gebaeude(conn, gebaeude_default)
                  else None)
    n = 0
    for z in zeilen:
        gebaeude = _spalte(z, "Building") or rueckgriff
        produkt = _spalte(z, "Product")
        if not produkt or (gebaeude or "").lower() == "building":
            continue
        menge = _zahl(_spalte(z, "#", "Amount", "Quantity")) or 1.0
        sterne, sekunden = parse_grad(_spalte(z, "Grade", "Stars"))
        eingaben = [parse_zutaten(_spalte(z, f"Ingredient #{i}")) for i in (1, 2, 3)]
        eingaben = [e for e in eingaben if e]
        conn.execute(
            "INSERT INTO recipes (building, inputs, outputs, ratio, stars, seconds, "
            "product, product_amount, source_page) VALUES (?,?,?,?,?,?,?,?,?)",
            (gebaeude, json.dumps(eingaben, ensure_ascii=False),
             json.dumps([{"menge": menge, "ware": produkt}], ensure_ascii=False),
             None, sterne, sekunden, produkt, menge, source_page),
        )
        n += 1
    conn.commit()
    return n


def food_amplification(conn: sqlite3.Connection) -> list[dict]:
    """Wie viel Saettigung ein Rezept aus der eingesetzten macht.

    Das ist die Zahl, an der SPEC.md haengt: Nahrungsmangel im ersten Jahr ist
    das Problem, und die Umwandlung ist der Hebel. Gerechnet wird mit der
    guenstigsten Alternative je Zutat -- das Spiel laesst die Wahl, und wer
    plant, waehlt die billigste.
    """
    saettigung = {
        r["en"]: r["eating_fullness"] or 0.0
        for r in conn.execute("SELECT en, eating_fullness FROM resources WHERE eatable = 1")
    }
    out: list[dict] = []
    for r in conn.execute("SELECT * FROM recipes WHERE product IS NOT NULL"):
        aus = saettigung.get(r["product"])
        if not aus:
            continue      # kein Nahrungsmittel
        raus = aus * (r["product_amount"] or 1.0)
        rein = 0.0
        eingesetzt: list[str] = []
        for gruppe in json.loads(r["inputs"] or "[]"):
            essbar = [(z["menge"] * saettigung[z["ware"]], z)
                      for z in gruppe if z["ware"] in saettigung]
            if not essbar:
                continue
            wert, zutat = min(essbar, key=lambda p: p[0])
            rein += wert
            eingesetzt.append(f"{zutat['menge']:.0f} {zutat['ware']}")
        if rein <= 0:
            continue
        if any(z["ware"] == r["product"] for gruppe in json.loads(r["inputs"] or "[]")
               for z in gruppe):
            # "3 Fleisch -> 30 Fleisch": eine Zutatenliste, die als Rezept
            # gelesen wurde. Kein Umwandlungsschritt.
            continue
        belegt = conn.execute(
            "SELECT building, stars FROM production WHERE product = ? "
            "ORDER BY stars DESC, building LIMIT 1", (r["product"],)).fetchone()
        out.append({
            "rezept": r["product"],
            # Die Produktionstabelle nennt das Gebaeude ausdruecklich; der
            # Seitentitel war nur ein Rueckgriff.
            "gebaeude": (belegt["building"] if belegt else r["building"]),
            "gebaeude_laut_seite": r["building"],
            "belegt": bool(belegt),
            "eingesetzt": " + ".join(eingesetzt),
            "saettigung_rein": rein, "saettigung_raus": raus,
            "faktor": round(raus / rein, 2),
            "sterne": r["stars"], "sekunden": r["seconds"],
        })
    out.sort(key=lambda e: -e["faktor"])
    return out


# --------------------------------------------------------------------------
# "List of Resources": Produkt -> Gebaeude, Zutaten, Speziesvorliebe
# --------------------------------------------------------------------------
#
# Die Rezepte von den Gebaeudeseiten tragen die Mengen, aber nicht das
# Gebaeude -- der Rueckgriff auf den Seitentitel hat "Jerky in Flawless
# Smelter" ergeben, was Unsinn ist. Diese Seite fuehrt die Zuordnung
# ausdruecklich, mitsamt Sterngrad, und daran laesst sich das pruefen.

# "Smokehouse (★★★) Apothecary (★★) Butcher (★)" -- der Name steht vor der
# Klammer, die Sterne darin. Auch ☆ kommt vor (Grad null).
GEBAEUDE_GRAD_RE = re.compile(r"([A-Z][A-Za-z'’\- ]*?)\s*\(\s*([★☆]+)\s*\)")


def parse_gebaeude_grade(text: str | None) -> list[tuple[str, int]]:
    """'Smokehouse (★★★) Butcher (★)' -> [('Smokehouse', 3), ('Butcher', 1)]."""
    out: list[tuple[str, int]] = []
    for name, sterne in GEBAEUDE_GRAD_RE.findall(text or ""):
        name = name.strip()
        if name:
            out.append((name, sterne.count("★")))
    return out


def _waren_namen(conn: sqlite3.Connection) -> list[str]:
    """Alle bekannten Warennamen, laengste zuerst -- fuer gierige Zerlegung."""
    namen = {r["en"] for r in conn.execute("SELECT en FROM resources") if r["en"]}
    namen |= {r["en"] for r in conn.execute(
        "SELECT en FROM name_map WHERE kind IN ('resource', 'resource_node')")
        if r["en"]}
    return sorted(namen, key=len, reverse=True)


def zerlege_waren(text: str | None, bekannt: list[str]) -> list[str]:
    """'Coal Oil Salt Sea Marrow Wood' -> die fuenf Waren, nicht sechs Woerter.

    Ohne die Liste der bekannten Namen waere "Sea Marrow" zwei Waren und
    "Plant Fiber" auch. Gesucht wird deshalb gierig nach den laengsten
    Namen zuerst.
    """
    rest = " ".join((text or "").split())
    out: list[str] = []
    while rest:
        for name in bekannt:
            if rest.startswith(name) and (len(rest) == len(name)
                                          or rest[len(name)] == " "):
                out.append(name)
                rest = rest[len(name):].lstrip()
                break
        else:
            # Unbekanntes Wort: ueberspringen, aber nicht haengenbleiben.
            _, _, rest = rest.partition(" ")
    return out


def import_production(conn: sqlite3.Connection, zeilen: list[dict],
                      kategorie: str | None = None,
                      produktspalte: str | None = None,
                      source_page: str | None = None) -> int:
    """Eine Tabelle von "List of Resources" uebernehmen."""
    bekannt = _waren_namen(conn)
    n = 0
    for z in zeilen:
        spalte = produktspalte or next(iter(z), "")
        produkt = _spalte(z, spalte)
        if not produkt or produkt.strip().lower() == spalte.strip().lower():
            continue        # Kopfzeile, die als Datenzeile durchgereicht wurde
        gebaeude = parse_gebaeude_grade(_spalte(z, "Production Buildings"))
        if not gebaeude:
            continue
        gruppen = [
            zerlege_waren(wert, bekannt)
            for schluessel, wert in z.items()
            if schluessel.startswith(("Ingredients and Options",
                                      "Recipe Ingredients and Options"))
        ]
        gruppen = [g for g in gruppen if g]
        vorliebe = _spalte(z, "Species Preferences")
        for name, sterne in gebaeude:
            conn.execute(
                "INSERT OR REPLACE INTO production "
                "(product, building, stars, category, inputs, species_pref, source_page) "
                "VALUES (?,?,?,?,?,?,?)",
                (produkt.strip(), name, sterne, kategorie,
                 json.dumps(gruppen, ensure_ascii=False), vorliebe, source_page),
            )
            n += 1
    conn.commit()
    return n


def pruefe_rezept_gebaeude(conn: sqlite3.Connection) -> list[dict]:
    """Rezepte, deren Gebaeude die Produktionstabelle nicht bestaetigt.

    Ein Befund, keine Korrektur: wo beide Quellen sich widersprechen, steht
    die Frage offen, und still das eine dem anderen anzugleichen hiesse,
    den Widerspruch zu verstecken.
    """
    bekannt: dict[str, set[str]] = {}
    for r in conn.execute("SELECT product, building FROM production"):
        bekannt.setdefault(r["product"], set()).add(r["building"])
    out: list[dict] = []
    for r in conn.execute(
            "SELECT id, product, building FROM recipes WHERE building IS NOT NULL"):
        erlaubt = bekannt.get(r["product"])
        if erlaubt and r["building"] not in erlaubt:
            out.append({"id": r["id"], "produkt": r["product"],
                        "gebaeude": r["building"], "laut_liste": sorted(erlaubt)})
    return out


# --------------------------------------------------------------------------
# Biomseiten
# --------------------------------------------------------------------------
#
# Jede Biomseite fuehrt drei Tabellen: die Biomeffekte (ohne Kopfzeile), die
# Baumarten mit ihren Bonusressourcen, und die Rohstoffe mit Vorkommen,
# erntendem Lager und Tempo. Zusammen beantworten sie die Frage, die jede
# Bauplanempfehlung braucht: gibt dieses Biom das ueberhaupt her?
#
# Die Namen stehen doppelt -- "Roots Roots Vegetables Vegetables" --, weil im
# HTML das Symbol seinen Namen als alt-Text traegt und der Verweis daneben
# denselben Namen noch einmal.

PROZENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


def _einfach(namen: list[str]) -> list[str]:
    """Aufeinanderfolgende Wiederholungen zusammenziehen."""
    out: list[str] = []
    for n in namen:
        if not out or out[-1] != n:
            out.append(n)
    return out


def parse_bonus(text: str | None, bekannt: list[str]) -> list[dict]:
    """'Algae Algae 30% + Vegetables Vegetables 20%' -> zwei Eintraege."""
    out: list[dict] = []
    for teil in (text or "").split("+"):
        waren = _einfach(zerlege_waren(PROZENT_RE.sub(" ", teil), bekannt))
        anteile = [float(p.replace(",", ".")) for p in PROZENT_RE.findall(teil)]
        for i, ware in enumerate(waren):
            out.append({"ware": ware,
                        "anteil": anteile[i] if i < len(anteile) else (
                            anteile[0] if anteile else None)})
    return out


def import_biome(conn: sqlite3.Connection, name: str,
                 effekte: list[list[str]] | None = None,
                 baeume: list[dict] | None = None,
                 rohstoffe: list[dict] | None = None,
                 source_page: str | None = None) -> bool:
    """Eine Biomseite uebernehmen. Fehlende Tabellen sind kein Fehler."""
    bekannt = _waren_namen(conn)

    wirkungen = [{"name": z[0].strip(), "text": (z[1] if len(z) > 1 else "").strip()}
                 for z in (effekte or []) if z and z[0].strip()]

    arten = []
    for z in (baeume or []):
        baum = _spalte(z, "Trees")
        if not baum:
            continue
        arten.append({
            "baum": " ".join(dict.fromkeys(baum.split())),
            "ladungen": _zahl(_spalte(z, "Charges")),
            "bonus": parse_bonus(_spalte(z, "Bonus Resources"), bekannt),
        })

    knoten = []
    for z in (rohstoffe or []):
        roh = _spalte(z, "Primary Resources")
        if not roh:
            continue
        # "Herbalists' Camp Herbalists' Camp ★★" -- Symbolname und Verweis.
        # Hier hilft kein Wortvergleich, sondern der Haelftenvergleich aus
        # dem HTML-Leser: die eine Haelfte ist die andere.
        lager = entdoppeln((_spalte(z, "Gathering Building") or "").split("★")[0].strip())
        knoten.append({
            "ressourcen": _einfach(zerlege_waren(roh, bekannt)),
            "vorkommen": _spalte(z, "Charges → Resource Deposits"),
            "anteil": _spalte(z, "Bonus Resources"),
            "lager": lager or None,
            "tempo": _spalte(z, "Speed per Unit"),
        })

    if not (wirkungen or arten or knoten):
        return False

    vorhanden = sorted({w for k in knoten for w in k["ressourcen"]}
                       | {b["ware"] for a in arten for b in a["bonus"]})
    conn.execute(
        "INSERT OR REPLACE INTO biomes (en, effects, tree_species, node_weights, "
        " notes, source_page) VALUES (?,?,?,?,?,?)",
        (name, json.dumps(wirkungen, ensure_ascii=False),
         json.dumps(arten, ensure_ascii=False),
         json.dumps(knoten, ensure_ascii=False),
         ", ".join(vorhanden) or None, source_page),
    )
    conn.commit()
    return True


def biom_hat(conn: sqlite3.Connection, biom: str, ware: str) -> bool | None:
    """Gibt dieses Biom diese Ware her? None heisst: nicht erfasst.

    Die Spec fuehrt drei solche Faustregeln -- kein Getreide im Korallenwald,
    kein fruchtbarer Boden in der Bambusebene, kein Holz aus Baeumen in der
    Felsschlucht. Nachschlagen ist besser als sich erinnern.
    """
    zeile = conn.execute("SELECT notes FROM biomes WHERE en = ? COLLATE NOCASE",
                         (biom,)).fetchone()
    if zeile is None or not zeile["notes"]:
        return None
    return ware.lower() in [w.strip().lower() for w in zeile["notes"].split(",")]


MENGE_WARE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s+([A-Z][A-Za-z'’ \-]*?)(?=\s+\d|$)")


def parse_kosten(text: str | None, bekannt: list[str]) -> dict[str, float]:
    """'3 Parts 10 Wood' -> {'Parts': 3.0, 'Wood': 10.0}.

    Die Warennamen werden gegen die bekannten geprueft, sonst wuerde
    "10 Sea Marrow" zu "Sea" und "Marrow" zerfallen.
    """
    out: dict[str, float] = {}
    for menge, roh in MENGE_WARE_RE.findall(" ".join((text or "").split())):
        waren = _einfach(zerlege_waren(roh, bekannt)) or [roh.strip()]
        out[waren[0]] = float(menge.replace(",", "."))
    return out


def import_buildings_list(conn: sqlite3.Connection, zeilen: list[dict],
                          source_page: str | None = None) -> int:
    """Die Seite "List of Buildings": Arbeitsplaetze, Spezialisierung, Baukosten.

    Die Baukosten kamen bisher aus dem Wikitext und ergaben zwei Zeilen. Hier
    stehen sie in der Spalte "Cost to build", je Gebaeude eine Zeile.
    Ergaenzend geschrieben: was schon dasteht, bleibt.
    """
    bekannt = _waren_namen(conn)
    n = 0
    for z in zeilen:
        name = _spalte(z, "Building")
        if not name or name.strip().lower() == "building":
            continue
        kosten = parse_kosten(_spalte(z, "Cost to build"), bekannt)
        spezialisierung = _spalte(z, "Specialization")
        if (spezialisierung or "").strip().lower() == "none":
            spezialisierung = None
        conn.execute(
            "INSERT INTO buildings (en, cost, specialization, worker_slots, "
            " purpose, products, near, source_page) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(en) DO UPDATE SET "
            "  cost = COALESCE(excluded.cost, buildings.cost), "
            "  specialization = COALESCE(excluded.specialization, buildings.specialization), "
            "  worker_slots = COALESCE(excluded.worker_slots, buildings.worker_slots), "
            "  purpose = COALESCE(excluded.purpose, buildings.purpose), "
            "  products = COALESCE(excluded.products, buildings.products), "
            "  near = COALESCE(excluded.near, buildings.near), "
            "  source_page = COALESCE(buildings.source_page, excluded.source_page)",
            (name.strip(),
             json.dumps(kosten, ensure_ascii=False) if kosten else None,
             spezialisierung,
             int(_zahl(_spalte(z, "Workplaces")) or 0) or None,
             _spalte(z, "Purpose"),
             _spalte(z, "Products", "Primary resource gathered"),
             _spalte(z, "Place near this"),
             source_page),
        )
        n += 1
    conn.commit()
    return n
