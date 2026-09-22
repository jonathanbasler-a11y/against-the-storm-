"""Deutsche Namen aus der Lokalisierungstabelle des Spiels.

Bis hierher waren die deutschen Namen geraten. SPEC.md sieht dafür die Stufe
`guessed` vor, und die Recherche hat 136 Zeilen beigesteuert -- gut gemeint,
aber ungedeckt: das Wiki ist englisch, und die deutsche Oberfläche steht
nirgends öffentlich.

Das Spiel trägt die Antwort allerdings selbst mit. In `resources.assets`
liegen die Textbausteine je Sprache, Schlüssel für Schlüssel, und
`Good_PickledGoods_Name` heißt dort "Eingelegte Nahrung" -- nicht "Eingelegte
Waren", wie geraten. Damit wird aus dem Raten ein Nachschlag, und die
geratenen Zeilen werden nicht still überschrieben, sondern nach
`retired_names` verschoben: was falsch war, bleibt sichtbar.

Gelesen werden drei Dateien, die aus dem Spielordner extrahiert wurden:

    de_translations.json   {"strings": {schluessel: {"en": ..., "de": ...}}}
    de_en_mapping.json     Wikiseite -> {en, de, key, alt_keys}
    de_en_names.json       de -> en, flach (nur zur Gegenprobe)

Keine dieser Dateien gehört ins Repo -- sie stammen aus der eigenen
Spielinstallation. Ins Repo geht nur, was daraus abgeleitet wird: die
Namenstabelle in `data/name_map_localized.csv`.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

QUELLE = "resources.assets"
CONFIDENCE = "localization"

# Nur diese Stufen werden bei Widerspruch ersetzt. Eine beobachtete Zeile
# stammt aus der Oberflaeche des Spielers -- weicht sie ab, ist das meist
# Ein- gegen Mehrzahl oder eine andere Stelle im Menue, und dann ist nicht
# sie falsch, sondern der Vergleich zu grob. Sie bleibt stehen und wird
# gemeldet.
ERSETZBAR = ("guessed", "spec_seed")

# Die drei Dateien, unter ihren Namen aus dem Extraktionslauf. Gesucht wird
# nachsichtig: ein Praefix genuegt, damit auch "1ba510b1-de_en_mapping.json"
# gefunden wird.
DATEINAMEN = {
    "strings": "de_translations.json",
    "mapping": "de_en_mapping.json",
    "namen": "de_en_names.json",
}

NAME_SUFFIXE = ("_Name", "_DisplayName")

# Schluesselpraefix -> kind. Was hier nicht steht, wird nicht uebernommen:
# Dialogzeilen, Nachrichten und Oberflaechentexte sind keine Namen, auf die
# der Berater zeigen koennte.
PRAEFIX_ART = {
    "Good": "resource",
    "Resource": "resource_node",
    "GoodCategory": "category",
    "BuildingCategory": "category",
    "NeedCategory": "category",
    "Building": "building",
    "BuildingPerk": "perk",
    "Biome": "biome",
    "Race": "species",
    "Effect": "effect",
    # Der grosse Teil der Grundsteine steht unter Reward_, nicht unter
    # Effect_: "Pilzfuehrer" ist Reward_MushroomSpecialization_Name. Das
    # aufzulassen hiess, ausgerechnet die Kategorie auszulassen, um die es
    # in der Spec geht.
    "Reward": "effect",
    "MetaReward": "meta",
    "CycleReward": "effect",
    "ResolveEffect": "effect",
    "ConditionalNeedEffect": "effect",
    "SeasonalEffect": "effect",
    "ModifierEffect": "effect",
    "CycleEffect": "effect",
    "EffectModel": "effect",
    "Relic": "glade_event",
    "Perk": "perk",
    "VillagerPerk": "perk",
    "Profession": "profession",
    "Trader": "trader",
    "WorldEvent": "world_event",
    "Order": "order",
    "UniqueGoal": "order",
    "ScalingGoal": "order",
    "TimedGoal": "order",
    "Seal": "concept",
}

# Begriffe, die das Spiel nicht unter einem *_Name-Schluessel fuehrt, sondern
# nur in der Oberflaeche: "Ungeduld" steht unter Label_Reward_Impatience.
# Gerade die braucht der Berater aber, denn in ihnen redet der Spieler ueber
# seine Lage. Gesucht wird ueber die englische Seite, und zwar exakt -- aus
# einem Satz etwas herauszufischen waere geraten, nicht nachgeschlagen.
# Wert ist die Art -- oder (Art, Schluessel), wo die Rangfolge danebengreift.
KONZEPTE: dict[str, str | tuple[str, str]] = {
    "Impatience": "concept",
    "Resolve": "concept",
    "Reputation": "concept",
    "Hunger": "concept",
    "Storm": "season",
    "Drizzle": "season",
    "Clearance": "season",
    "Seasons": "concept",
    "Blightrot": "concept",
    "Blightrot Cysts": "concept",
    "Cornerstone": "concept",
    "Cornerstones": "concept",
    "Glades": "concept",
    "Glade Event": "concept",
    "Glade Events": "concept",
    "Dangerous Glade": "concept",
    "Forbidden Glade": "concept",
    "Smoldering City": "concept",
    "Trade Route": "concept",
    "Building Blueprints": "concept",
    "Tools": "resource",
    "Reed": "resource",
    "Smithy": "building",
    "Comfort": "concept",
    "Loyalty": "concept",
    # Label_BuildingDisplayLabel_Hearth sagt "Herd", die Gebaeudenamen sagen
    # "Feuerstelle" (Uralte Feuerstelle, Kleine Feuerstelle). Die Oberflaeche
    # entscheidet, denn darauf zeigt der Spieler.
    "Hearth": ("building", "GameUI_BuildingPanel_Tabs_Main_Hearth"),
    "Needs": "concept",
    "Need": "concept",
    "Housing": "category",
    "Complex Food": "category",
    "Food": "category",
    "Production": "concept",
    "Sacrifice": "concept",
    "Villagers": "concept",
    "Break Interval": "concept",
    "Fuel Reserves": "concept",
    "Forest Mystery": "concept",
    "Forest Mysteries": "concept",
    "Seasonal Effect": "concept",
    "Camp": "concept",
    "Upgrade": "concept",
}

# Die geratene Namenstabelle fuehrt eigene Bezeichner, die es im Spiel so
# nicht gibt: `reeds` heisst dort "Reed", `simple_tools` schlicht "Tools",
# `storm_season` nur "Storm". Ohne diese Bruecke stuenden die Zeilen
# nebeneinander, ohne sich je zu widersprechen -- und eine falsche Zeile,
# die nie widerlegt wird, bleibt in der Auskunft stehen.
ALIASE = {
    "blacksmith": "Smithy",
    "blightrot_cyst": "Blightrot Cysts",
    "blueprint": "Building Blueprints",
    "clearance_season": "Clearance",
    "crystallized_dew": "Crystalized Dew",     # das Spiel schreibt ein l
    "drizzle_season": "Drizzle",
    "food_complex": "Complex Food",
    "reeds": "Reed",
    "simple_tools": "Tools",
    "storm_season": "Storm",
    "trade_routes": "Trade Route",
}

# Steht derselbe englische Begriff unter mehreren Schluesseln, entscheidet
# der Praefix: Common_ ist die allgemeine Form, Label_ die Beschriftung,
# GameUI_ eine Stelle in der Oberflaeche. Was weiter hinten steht, verliert.
SCHLUESSEL_RANG = ("Common_", "Label_", "NeedCategory_", "GoodCategory_",
                   "BuildingCategory_", "GameUI_", "WorldUI_", "Score_",
                   "ReputationSource_", "Content_")


# Die Sachtabellen der Wissensbasis, je Tabelle die Art, die eine Zeile
# daraus bekommt. Steht ein Name dort, gilt diese Art -- der Praefix des
# Schluessels ist nur die Rueckfallebene.
TABELLEN_ART = {
    "resources": "resource",
    "buildings": "building",
    "species": "species",
    "biomes": "biome",
    "cornerstones": "effect",
    "glade_events": "glade_event",
}

_NICHT_WORT = re.compile(r"[^a-z0-9]+")


def normalisieren(name: str) -> str:
    """"Alchemist's Hut" -> alchemists_hut.

    Die Namenstabelle aus der Recherche fuehrt kleingeschriebene Bezeichner
    (`pickled_goods`), das Wiki und die Lokalisierung fuehren Anzeigenamen
    ("Pickled Goods"). Verglichen wird auf dieser Normalform, sonst stuenden
    beide nebeneinander, ohne sich je zu widersprechen.
    """
    ohne = (name or "").lower().replace("'", "").replace("’", "")
    return _NICHT_WORT.sub("_", ohne).strip("_")


def _de_gleich(a: str | None, b: str | None) -> bool:
    return " ".join((a or "").split()).casefold() == " ".join((b or "").split()).casefold()


@dataclass(frozen=True)
class Eintrag:
    """Ein Name, wie das Spiel ihn führt."""
    key: str
    en: str
    de: str
    kind: str

    @property
    def en_id(self) -> str:
        return normalisieren(self.en)


@dataclass
class Bericht:
    """Was der Abgleich ergeben hat.

    `geprueft` zaehlt nur Zeilen, die eine deutsche Seite behauptet haben --
    eine Zeile ohne deutschen Namen kann nicht falsch liegen, sie war eine
    Luecke. Die zaehlt `ergaenzt`.
    """
    uebernommen: int = 0
    bestaetigt: list[tuple[str, str]] = field(default_factory=list)
    widerlegt: list[tuple[str, str, str, str]] = field(default_factory=list)
    ergaenzt: int = 0
    abweichend: list[tuple[str, str, str, str]] = field(default_factory=list)
    geschlossen: list[tuple[str, str]] = field(default_factory=list)
    unberuehrt: int = 0
    quelle: str = QUELLE

    @property
    def geprueft(self) -> int:
        return len(self.bestaetigt) + len(self.widerlegt)

    def zusammenfassung(self) -> list[str]:
        zeilen = [f"Namen aus der Lokalisierung: {self.uebernommen}"]
        if self.geprueft:
            anteil = len(self.widerlegt) * 100 // self.geprueft
            zeilen.append(
                f"Geratene Zeilen gegengeprüft: {self.geprueft}, "
                f"davon {len(self.widerlegt)} falsch ({anteil} Prozent), "
                f"{len(self.bestaetigt)} bestätigt")
        if self.ergaenzt:
            zeilen.append(f"Leere deutsche Seite gefüllt: {self.ergaenzt}")
        if self.geschlossen:
            zeilen.append(
                f"Beobachtete Namen um die englische Seite ergänzt: "
                f"{len(self.geschlossen)} ("
                + ", ".join(f"{de} = {en}" for de, en in self.geschlossen[:4])
                + (", ..." if len(self.geschlossen) > 4 else "") + ")")
        if self.abweichend:
            zeilen.append(
                f"Beobachtete Zeilen mit anderem Wortlaut: {len(self.abweichend)} "
                "(stehen geblieben, nachsehen lohnt: "
                + ", ".join(f"{en}: {alt} statt {neu}"
                            for en, alt, neu, _ in self.abweichend[:3]) + ")")
        if self.unberuehrt:
            zeilen.append(f"Ohne Gegenstück in der Lokalisierung: {self.unberuehrt}")
        return zeilen


# --------------------------------------------------------------------------
# Einlesen
# --------------------------------------------------------------------------


def datei_finden(verzeichnis: Path, name: str) -> Path | None:
    """Die Datei unter ihrem Namen suchen, auch mit vorangestelltem Kürzel."""
    verzeichnis = Path(verzeichnis)
    direkt = verzeichnis / name
    if direkt.exists():
        return direkt
    treffer = sorted(verzeichnis.glob(f"*{name}"))
    return treffer[0] if treffer else None


def lade_strings(pfad: Path) -> dict[str, dict[str, str]]:
    """Die Schlüsseltabelle lesen. `strings` liegt eine Ebene tief."""
    roh = json.loads(Path(pfad).read_text(encoding="utf-8"))
    strings = roh.get("strings", roh) if isinstance(roh, dict) else {}
    return {k: v for k, v in strings.items() if isinstance(v, dict)}


def lade_mapping(pfad: Path) -> dict[str, dict]:
    """Wikiseite -> {en, de, key}. Fehlt die Datei, ist das kein Fehler."""
    roh = json.loads(Path(pfad).read_text(encoding="utf-8"))
    if not isinstance(roh, dict):
        return {}
    return {k: v for k, v in roh.get("wiki_en_to_de", {}).items() if isinstance(v, dict)}


def art_fuer(key: str) -> str | None:
    """Die Art aus dem Schlüsselpräfix. Unbekannt heißt: nicht übernehmen."""
    return PRAEFIX_ART.get(key.split("_", 1)[0])


def eintraege(strings: dict[str, dict[str, str]],
              mapping: dict[str, dict] | None = None) -> list[Eintrag]:
    """Aus der Schlüsseltabelle die Namen herausziehen.

    Uebernommen wird, was auf `_Name` oder `_DisplayName` endet und dessen
    Praefix in PRAEFIX_ART steht. Das Mapping liefert die Art fuer Seiten,
    deren Schluessel sonst durchfielen -- eine Wikiseite ist ein Beleg, dass
    der Name einer ist.
    """
    aus_mapping: dict[str, str] = {}
    for seite, wert in (mapping or {}).items():
        schluessel = (wert.get("key") or "").strip()
        if schluessel:
            aus_mapping.setdefault(schluessel, seite)

    out: list[Eintrag] = []
    gesehen: set[tuple[str, str]] = set()
    for key, wert in strings.items():
        if not key.endswith(NAME_SUFFIXE):
            continue
        en = (wert.get("en") or "").strip()
        de = (wert.get("de") or "").strip()
        if not en or not de:
            continue
        art = art_fuer(key)
        if art is None:
            if key not in aus_mapping:
                continue
            art = "concept"
        marke = (normalisieren(en), art)
        if marke in gesehen:
            continue
        gesehen.add(marke)
        out.append(Eintrag(key=key, en=en, de=de, kind=art))
    out.sort(key=lambda e: (e.kind, e.en))
    return out


def _rang(key: str) -> tuple[int, str]:
    for i, praefix in enumerate(SCHLUESSEL_RANG):
        if key.startswith(praefix):
            return (i, key)
    return (len(SCHLUESSEL_RANG), key)


def konzepte(strings: dict[str, dict[str, str]],
             begriffe: dict[str, str | tuple[str, str]] | None = None
             ) -> tuple[list[Eintrag], list[str]]:
    """Begriffe über die englische Seite nachschlagen.

    Zurück kommen die gefundenen Einträge und die Begriffe, die offen
    blieben -- letztere sind kein Fehler, sondern eine Ansage: dieser
    Begriff steht im Spiel nur im Satz, nicht als Vokabel.
    """
    begriffe = begriffe if begriffe is not None else KONZEPTE
    nach_en: dict[str, list[tuple[str, str]]] = {}
    for key, wert in strings.items():
        en = (wert.get("en") or "").strip()
        de = (wert.get("de") or "").strip()
        if en and de:
            nach_en.setdefault(en, []).append((key, de))

    gefunden: list[Eintrag] = []
    offen: list[str] = []
    for begriff, wert in begriffe.items():
        art, fest = wert if isinstance(wert, tuple) else (wert, None)
        kandidaten = sorted(nach_en.get(begriff, []), key=lambda kv: _rang(kv[0]))
        if fest:
            kandidaten = [k for k in kandidaten if k[0] == fest] or kandidaten
        if not kandidaten:
            offen.append(begriff)
            continue
        key, de = kandidaten[0]
        gefunden.append(Eintrag(key=key, en=begriff, de=de, kind=art))
    return gefunden, offen


def lade(verzeichnis: Path) -> list[Eintrag]:
    """Alles aus einem Verzeichnis lesen, in dem die Auszüge liegen."""
    verzeichnis = Path(verzeichnis)
    pfad = datei_finden(verzeichnis, DATEINAMEN["strings"])
    if pfad is None:
        raise FileNotFoundError(
            f"{DATEINAMEN['strings']} fehlt unter {verzeichnis}")
    strings = lade_strings(pfad)
    mapping_pfad = datei_finden(verzeichnis, DATEINAMEN["mapping"])
    mapping = lade_mapping(mapping_pfad) if mapping_pfad else {}
    posten = eintraege(strings, mapping)
    bekannt = {(e.en_id, e.kind) for e in posten}
    begriffe, offen = konzepte(strings)
    if offen:
        log.info("Ohne eigenen Eintrag in der Lokalisierung: %s", ", ".join(offen))
    posten.extend(e for e in begriffe if (e.en_id, e.kind) not in bekannt)
    posten.sort(key=lambda e: (e.kind, e.en))
    return posten


# --------------------------------------------------------------------------
# Abgleich mit der Wissensbasis
# --------------------------------------------------------------------------


def _arten_aus_tabellen(conn: sqlite3.Connection) -> dict[str, str]:
    """en_id -> Art, so wie die Sachtabellen sie fuehren."""
    out: dict[str, str] = {}
    for tabelle, art in TABELLEN_ART.items():
        try:
            zeilen = conn.execute(f"SELECT en FROM {tabelle}").fetchall()
        except sqlite3.DatabaseError:
            continue
        for zeile in zeilen:
            out.setdefault(normalisieren(zeile[0]), art)
    return out


def _schliesse_luecken(conn: sqlite3.Connection, posten: list[Eintrag],
                       stand: str) -> list[tuple[str, str]]:
    """Beobachtete deutsche Namen ohne englische Seite nachtragen.

    Sechs Zeilen stammen aus Screenshots: "Erntelager" stand im Auftrag, die
    englische Entsprechung war offen. Die Lokalisierung kann das rückwärts
    aufloesen -- aber nur, wenn genau ein englischer Begriff dazu passt.
    Bei mehreren bleibt die Zeile, wie sie ist: raten waere hier dasselbe
    Uebel in der anderen Richtung.
    """
    nach_de: dict[str, set[tuple[str, str]]] = {}
    for e in posten:
        nach_de.setdefault(" ".join(e.de.split()).casefold(), set()).add((e.en, e.key))

    geschlossen: list[tuple[str, str]] = []
    offene = conn.execute(
        "SELECT en, de, kind, confidence, source, note FROM name_map "
        "WHERE en IS NULL OR TRIM(en) = ''").fetchall()
    for zeile in offene:
        treffer = nach_de.get(" ".join((zeile["de"] or "").split()).casefold(), set())
        if len(treffer) != 1:
            continue
        en, key = next(iter(treffer))
        conn.execute("DELETE FROM name_map WHERE (en IS NULL OR TRIM(en) = '') "
                     "AND de = ? AND kind IS ?", (zeile["de"], zeile["kind"]))
        conn.execute(
            "INSERT OR REPLACE INTO name_map "
            "(en, de, kind, category, confidence, source, verified_at, note, loc_key, en_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (en, zeile["de"], zeile["kind"], None, CONFIDENCE, QUELLE, stand,
             zeile["note"], key, normalisieren(en)),
        )
        geschlossen.append((zeile["de"], en))
    return geschlossen


def import_localization(conn: sqlite3.Connection, posten: list[Eintrag],
                        quelle: str = QUELLE, stand: str | None = None,
                        commit: bool = True) -> Bericht:
    """Die Namen übernehmen und die geratenen Zeilen dagegen halten.

    Gleicher Name, gleiche deutsche Seite -> die geratene Zeile war richtig
    und wird durch die belegte ersetzt. Gleicher Name, andere deutsche Seite
    -> die geratene Zeile wandert nach `retired_names`. Alles andere bleibt,
    wo es ist.
    """
    stand = stand or date.today().isoformat()
    bericht = Bericht(quelle=quelle)
    tabellen_art = _arten_aus_tabellen(conn)
    bericht.geschlossen = _schliesse_luecken(conn, posten, stand)

    # Bestand einmal einlesen: der Vergleich laeuft ueber die Normalform,
    # dafuer taugt kein Index.
    bestand: dict[str, list[sqlite3.Row]] = {}
    for zeile in conn.execute(
            "SELECT en, de, kind, category, confidence, source, note, en_id "
            "FROM name_map"):
        bestand.setdefault(normalisieren(zeile["en_id"] or zeile["en"]), []).append(zeile)

    # Bezeichner der Saat-Tabelle, die auf einen Begriff des Spiels zeigen.
    alias_rueck: dict[str, list[str]] = {}
    for eigen, spiel in ALIASE.items():
        alias_rueck.setdefault(normalisieren(spiel), []).append(normalisieren(eigen))

    beruehrt: set[str] = set()
    # Ein englischer Name kann mehrfach vorkommen -- "Carpenter" ist Gebaeude
    # und Beruf. Die alte Zeile darf davon nur einmal erfasst werden, sonst
    # stuende dieselbe Widerlegung zweimal im Bericht.
    erledigt: set[int] = set()
    for e in posten:
        art = tabellen_art.get(e.en_id, e.kind)
        # Was die alte Zeile an Beiwerk trug -- Kategorie und die Save-ID in
        # der Notiz -- ist unabhaengig davon richtig, ob der deutsche Name
        # stimmte. Bestaetigte Zeilen geben es weiter.
        kategorie: str | None = None
        notiz: str | None = None
        alte = list(bestand.get(e.en_id, []))
        for eigen in alias_rueck.get(e.en_id, []):
            alte.extend(bestand.get(eigen, []))
        for alt in alte:
            if id(alt) in erledigt:
                continue
            if alt["confidence"] == CONFIDENCE:
                # Schon nachgeschlagen -- etwa von _schliesse_luecken. Das
                # Beiwerk der Zeile darf der naechste Schreibzugriff nicht
                # wegwerfen.
                kategorie = kategorie or alt["category"]
                notiz = notiz or alt["note"]
                continue
            erledigt.add(id(alt))
            beruehrt.add(normalisieren(alt["en_id"] or alt["en"]))
            if not (alt["de"] or "").strip():
                # Keine Behauptung, nur eine Luecke.
                bericht.ergaenzt += 1
            elif _de_gleich(alt["de"], e.de):
                bericht.bestaetigt.append((e.en, e.de))
                kategorie = kategorie or alt["category"]
                notiz = notiz or alt["note"]
            elif alt["confidence"] not in ERSETZBAR:
                bericht.abweichend.append(
                    (e.en, alt["de"], e.de, alt["confidence"]))
                continue
            else:
                bericht.widerlegt.append((e.en, alt["de"], e.de, alt["confidence"]))
                conn.execute(
                    "INSERT OR REPLACE INTO retired_names "
                    "(en, de, kind, confidence, source, replaced_by, retired_at, note) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (alt["en"], alt["de"], alt["kind"], alt["confidence"],
                     alt["source"], e.de, stand, alt["note"]),
                )
            conn.execute(
                "DELETE FROM name_map WHERE en = ? AND de = ? AND kind IS ?",
                (alt["en"], alt["de"], alt["kind"]),
            )
        conn.execute(
            "INSERT OR REPLACE INTO name_map "
            "(en, de, kind, category, confidence, source, verified_at, note, loc_key, en_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (e.en, e.de, art, kategorie, CONFIDENCE, quelle, stand, notiz,
             e.key, e.en_id),
        )
        bericht.uebernommen += 1

    bericht.unberuehrt = sum(
        1 for schluessel, zeilen in bestand.items()
        if schluessel not in beruehrt
        for z in zeilen if z["confidence"] != CONFIDENCE and (z["de"] or "").strip())
    if commit:
        conn.commit()
    return bericht


# --------------------------------------------------------------------------
# Ablage im Repo
# --------------------------------------------------------------------------

CSV_SPALTEN = ["en", "de", "kind", "category", "confidence", "source",
               "verified_at", "note", "loc_key", "en_id"]


def schreibe_csv(posten: list[Eintrag], pfad: Path, stand: str | None = None) -> int:
    """Die Namenstabelle ablegen, im Format der Saat-CSV."""
    stand = stand or date.today().isoformat()
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with pfad.open("w", encoding="utf-8", newline="") as fh:
        schreiber = csv.DictWriter(fh, fieldnames=CSV_SPALTEN)
        schreiber.writeheader()
        for e in posten:
            schreiber.writerow({
                "en": e.en, "de": e.de, "kind": e.kind, "category": "",
                "confidence": CONFIDENCE, "source": QUELLE,
                "verified_at": stand, "note": "", "loc_key": e.key,
                "en_id": e.en_id,
            })
    return len(posten)


def lade_csv(pfad: Path) -> list[Eintrag]:
    """Die abgelegte Namenstabelle zurücklesen."""
    out: list[Eintrag] = []
    with Path(pfad).open(encoding="utf-8", newline="") as fh:
        for zeile in csv.DictReader(fh):
            en = (zeile.get("en") or "").strip()
            de = (zeile.get("de") or "").strip()
            if not en or not de:
                continue
            out.append(Eintrag(key=(zeile.get("loc_key") or "").strip(),
                               en=en, de=de,
                               kind=(zeile.get("kind") or "concept").strip()))
    return out
