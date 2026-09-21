-- Wissensbasis für den Against-the-Storm-Assistenten.
-- Tabellen nach SPEC.md Phase 1, plus zwei, die aus Phase 0 dazugekommen sind:
-- source_pages (Wiki-Versionsstand je Seite) und save_ids (das Vokabular, das
-- der Spielstand selbst liefert).

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS resources (
    en           TEXT PRIMARY KEY,
    category     TEXT,          -- Food Raw, Mat Processed, Crafting, ...
    deposit      TEXT,          -- Herkunftsvorkommen
    camp         TEXT,          -- erntendes Lager
    biomes       TEXT,          -- kommaseparierte Biomnamen
    source_page  TEXT REFERENCES source_pages(title)
);

CREATE TABLE IF NOT EXISTS biomes (
    en           TEXT PRIMARY KEY,
    effects      TEXT,
    tree_species TEXT,          -- Baumarten mit Bonusressourcen
    node_weights TEXT,          -- Knotengewichtungen als JSON
    notes        TEXT,          -- Besonderheiten
    source_page  TEXT REFERENCES source_pages(title)
);

CREATE TABLE IF NOT EXISTS cornerstones (
    en           TEXT PRIMARY KEY,
    rarity       TEXT,
    effect_text  TEXT,
    origin       TEXT,          -- jährlich / Händler / Auftrag / Altar
    price        TEXT,
    source_page  TEXT REFERENCES source_pages(title)
);

CREATE TABLE IF NOT EXISTS buildings (
    en           TEXT PRIMARY KEY,
    cost         TEXT,          -- JSON: {"Planks": 5, ...}
    specialization TEXT,
    worker_slots INTEGER,
    source_page  TEXT REFERENCES source_pages(title)
);

CREATE TABLE IF NOT EXISTS recipes (
    id           INTEGER PRIMARY KEY,
    building     TEXT REFERENCES buildings(en),
    inputs       TEXT,          -- JSON
    outputs      TEXT,          -- JSON
    ratio        TEXT,
    stars        INTEGER,
    source_page  TEXT REFERENCES source_pages(title)
);

CREATE TABLE IF NOT EXISTS species (
    en            TEXT PRIMARY KEY,
    specialization TEXT,
    base_resolve  REAL,
    house_type    TEXT,
    needs         TEXT,         -- JSON
    break_seconds REAL,
    hunger_tolerance INTEGER,
    decadence     REAL,
    source_page   TEXT REFERENCES source_pages(title)
);

CREATE TABLE IF NOT EXISTS prestige (
    level        INTEGER PRIMARY KEY,
    modifier_en  TEXT,
    effect       TEXT,
    source_page  TEXT REFERENCES source_pages(title)
);

CREATE TABLE IF NOT EXISTS glade_events (
    en           TEXT PRIMARY KEY,
    requirements TEXT,
    reward       TEXT,
    failure      TEXT,          -- Endeffekt bei Versagen
    source_page  TEXT REFERENCES source_pages(title)
);

-- Die deutschen Namen stehen nirgends öffentlich. confidence sagt, wie weit
-- eine Zeile trägt: screenshot und save_id sind belegt, guessed ist geraten.
CREATE TABLE IF NOT EXISTS name_map (
    en           TEXT,
    de           TEXT,
    kind         TEXT,          -- resource, building, concept, biome, species
    category     TEXT,
    confidence   TEXT NOT NULL, -- screenshot | save_id | spec_seed | observed | guessed
    source       TEXT,
    verified_at  TEXT,
    note         TEXT,
    PRIMARY KEY (en, de, kind)
);

CREATE INDEX IF NOT EXISTS name_map_de ON name_map(de);
CREATE INDEX IF NOT EXISTS name_map_conf ON name_map(confidence);

-- Das Wiki steht stellenweise auf Spielversion 1.8 bis 1.9. Bei Abweichung
-- zur Spielversion hängt eine Warnung am Datensatz, statt still ausgeliefert
-- zu werden.
CREATE TABLE IF NOT EXISTS source_pages (
    title        TEXT PRIMARY KEY,
    revision_id  INTEGER,
    revised_at   TEXT,
    fetched_at   TEXT,
    game_version TEXT,          -- die im Seitentext genannte Version
    warning      TEXT
);

-- Vokabular aus dem Spielstand: 169 Gebäude, 65 Effekte, die Warenliste.
-- Damit ist prüfbar, was das Wiki nicht liefert.
CREATE TABLE IF NOT EXISTS save_ids (
    id           TEXT,
    kind         TEXT,          -- building, effect, good, modifier, event
    source_file  TEXT,
    source_path  TEXT,
    imported_at  TEXT,
    PRIMARY KEY (id, kind)
);
