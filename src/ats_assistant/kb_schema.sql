-- Wissensbasis für den Against-the-Storm-Assistenten.
-- Tabellen nach SPEC.md Phase 1, plus zwei, die aus Phase 0 dazugekommen sind:
-- source_pages (Wiki-Versionsstand je Seite) und save_ids (das Vokabular, das
-- der Spielstand selbst liefert).

PRAGMA journal_mode = WAL;

-- Die Spalten stammen aus der Vorlage Dataloader/Goods des Wikis. Das sind
-- die Spieldaten selbst, nicht Fliesstext: save_id traegt genau die
-- Zeichenkette, die auch im Spielstand steht ("[Needs] Boots"), und
-- display_key ist der Lokalisierungsschluessel, ueber den der deutsche Name
-- zu holen waere.
CREATE TABLE IF NOT EXISTS resources (
    en           TEXT PRIMARY KEY,   -- page_name, z. B. "Boots"
    save_id      TEXT,               -- m_Name, z. B. "[Needs] Boots"
    category     TEXT,               -- Kategorie, ueber guid_index aufgeloest
    category_guid TEXT,
    guid         TEXT,
    display_name_en TEXT,
    display_key  TEXT,               -- z. B. "Good_Boots_Name"
    description_en TEXT,
    eatable      INTEGER,
    eating_fullness REAL,
    burnable     INTEGER,
    burning_time REAL,
    sell_value   REAL,
    buy_value    REAL,
    deposit      TEXT,               -- Herkunftsvorkommen
    camp         TEXT,               -- erntendes Lager
    biomes       TEXT,
    source_page  TEXT REFERENCES source_pages(title)
);

CREATE INDEX IF NOT EXISTS resources_save_id ON resources(save_id);

-- guid -> Seitenname, aus Dataloader/guid_index. Loest die Fremdschluessel
-- auf, mit denen die Datenseiten untereinander verweisen.
CREATE TABLE IF NOT EXISTS guid_index (
    guid         TEXT PRIMARY KEY,
    page_name    TEXT,
    domain       TEXT
);

CREATE INDEX IF NOT EXISTS guid_index_page ON guid_index(page_name);

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
    unlock       TEXT,          -- "(always available)", "Unlocked on Level 3"
    category     TEXT,          -- die Ueberschrift, unter der der Entwurf steht
    purpose      TEXT,          -- Zweck in einem Satz
    products     TEXT,          -- was es herstellt oder erntet
    near         TEXT
    source_page  TEXT REFERENCES source_pages(title)
);

-- inputs ist eine Liste von Listen: je Zutat die Alternativen, unter denen
-- das Spiel waehlen laesst. "5 Insects 5 Meat" sind nicht zwei Zutaten,
-- sondern zwei Moeglichkeiten fuer eine.
CREATE TABLE IF NOT EXISTS recipes (
    id           INTEGER PRIMARY KEY,
    building     TEXT REFERENCES buildings(en),
    inputs       TEXT,          -- JSON: [[{menge, ware}, ...], ...]
    outputs      TEXT,          -- JSON
    ratio        TEXT,
    stars        INTEGER,
    seconds      REAL,          -- Produktionsdauer
    product      TEXT,
    product_amount REAL,
    source_page  TEXT REFERENCES source_pages(title)
);

CREATE INDEX IF NOT EXISTS recipes_product ON recipes(product);

-- Die Seite "List of Resources" fuehrt je Erzeugnis, in welchen Gebaeuden es
-- entsteht und mit welchem Sterngrad -- "Smokehouse (***) Apothecary (**)
-- Butcher (*)". Das ist die belastbare Zuordnung Produkt -> Gebaeude; die
-- Rezepte von den Gebaeudeseiten tragen die Mengen, aber nicht zuverlaessig
-- das Gebaeude. Dazu die Spezies, die das Erzeugnis bevorzugen.
CREATE TABLE IF NOT EXISTS production (
    product      TEXT,
    building     TEXT,
    stars        INTEGER,        -- 3 = beste Rezeptstufe im Gebaeude
    category     TEXT,           -- "Complex Food", "Building Material", ...
    inputs       TEXT,           -- JSON: Liste von Alternativlisten
    species_pref TEXT,           -- Spezies, die es bevorzugen
    source_page  TEXT REFERENCES source_pages(title),
    PRIMARY KEY (product, building)
);

CREATE INDEX IF NOT EXISTS production_building ON production(building);

CREATE TABLE IF NOT EXISTS species (
    en            TEXT PRIMARY KEY,
    specialization TEXT,        -- Proficiency
    comfort       TEXT,
    base_resolve  REAL,
    house_type    TEXT,
    needs         TEXT,         -- JSON
    break_seconds REAL,
    hunger_tolerance INTEGER,
    decadence     REAL,
    resilience    TEXT,         -- low / medium / high
    demand        REAL,         -- Resolve Threshold
    reputation_ratio REAL,      -- Species Resolve to Reputation Ratio
    source_page   TEXT REFERENCES source_pages(title)
);

-- Die Seite "Difficulty" fuehrt je Schwierigkeitsgrad Multiplikatoren, unter
-- anderem den Hostility Multiplier. Das passt nicht in die Tabelle prestige,
-- die je Stufe einen Modifikatornamen erwartet -- also eine eigene.
CREATE TABLE IF NOT EXISTS difficulty (
    en            TEXT PRIMARY KEY,
    rewards_multiplier REAL,
    seal_fragments REAL,
    tile_reach_max REAL,
    experience_multiplier REAL,
    score_multiplier REAL,
    blight_footprint_rate REAL,
    blight_corruption_rate REAL,
    hostility_multiplier REAL,
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

-- Die deutschen Namen standen nirgends öffentlich -- bis auf das Spiel selbst.
-- resources.assets traegt je Schluessel eine englische und eine deutsche
-- Zeichenkette; was daher kommt, ist nachgeschlagen statt geraten und traegt
-- confidence = localization. Darunter erst das Beobachtete, zuletzt das Geratene.
CREATE TABLE IF NOT EXISTS name_map (
    en           TEXT,
    de           TEXT,
    kind         TEXT,          -- resource, building, concept, biome, species
    category     TEXT,
    confidence   TEXT NOT NULL, -- localization | screenshot | save_id | spec_seed | observed | guessed
    source       TEXT,
    verified_at  TEXT,
    note         TEXT,
    loc_key      TEXT,          -- Lokalisierungsschluessel, z. B. Good_PickledGoods_Name
    en_id        TEXT,          -- "Pickled Goods" -> pickled_goods, fuer den Nachschlag
    PRIMARY KEY (en, de, kind)
);

CREATE INDEX IF NOT EXISTS name_map_en_id ON name_map(en_id);

-- Was die Lokalisierung widerlegt hat, wird nicht still geloescht. Eine
-- geratene Zeile, die sich als falsch erweist, ist ein Befund: sie sagt,
-- wie weit der Recherche zu trauen war.
CREATE TABLE IF NOT EXISTS retired_names (
    en           TEXT,
    de           TEXT,          -- der widerlegte deutsche Name
    kind         TEXT,
    confidence   TEXT,          -- womit die Zeile angetreten war
    source       TEXT,
    replaced_by  TEXT,          -- der belegte deutsche Name
    retired_at   TEXT,
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
