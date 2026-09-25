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
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import analysis, forecast, kb, nahrung, namen_match, save_reader, screen, watcher
from .forecast import food_forecast as _food_forecast
from .forecast import impatience_forecast as _impatience_forecast
from .paths import strip_prefixes
from .save_reader import GameState, read_state

log = logging.getLogger(__name__)


def _wall(fn):
    """Jede Ausnahme wird ein Dictionary, nie ein Abbruch.

    Diese Funktionen werden aus drei Richtungen gerufen: vom MCP-Server, von
    der Kommandozeile und kuenftig aus dem Fenster. Wer wirft, reisst den
    jeweiligen Aufrufer mit -- beim Fenster hiesse das einen toten
    Arbeits-Thread und eine Oberflaeche, die stehenbleibt, ohne zu sagen
    warum. Ein Dictionary mit `fehler` kommt ueberall an.

    Die Absicherung im MCP-Server bleibt trotzdem: sie faengt auch, was
    ausserhalb dieser Funktionen schiefgeht.
    """
    @wraps(fn)
    def gehuellt(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            log.exception("Werkzeug %s ist gescheitert", fn.__name__)
            return {"verfuegbar": False,
                    "fehler": f"{type(exc).__name__}: {exc}",
                    "werkzeug": fn.__name__}
    return gehuellt


def _verfuegbar(zustand: dict) -> dict[str, str] | None:
    """Was steht und was sich bauen laesst, aus einem Zustand der Mitschrift.

    None, wenn die Mitschrift keins von beiden kennt -- aeltere Zeilen hatten
    weder `blueprints` noch lesbare Gebaeude. Dann bleibt der Rat, wie er war.
    """
    gebaut = [b.get("model") for b in zustand.get("buildings") or []
              if isinstance(b, dict) and isinstance(b.get("model"), str)]
    plaene = [p for p in zustand.get("blueprints") or [] if isinstance(p, str)]
    if not gebaut and not plaene:
        return None
    out = {p: "baubar" for p in plaene}
    out.update({g: "steht" for g in gebaut})
    return out


# Gemessen am 23.09.2026: Index 2 war genau der Zufriedenheitsgewinn der
# Fuechse. Die anderen drei sind nicht belegt und heissen deshalb so --
# bestaetigt werden sie, sobald ein abgeschlossener Auftrag Index 0 hebt.
RUF_QUELLEN = ("Aufträge (vermutet)", "Lichtungen (vermutet)", "Zufriedenheit",
               "Sonstiges (vermutet)")


def _ruf_quellen(werte: list[float]) -> dict[str, float]:
    return {name: wert for name, wert in zip(RUF_QUELLEN, werte)}


def _auftraege(orders: list[dict]) -> dict:
    """Aktive Auftraege und das Angebot einer offenen Wahl.

    Was ein Auftrag verlangt (Ware, Zielmenge), steht nicht im Spielstand --
    je Ziel nur ein Zaehler. Ob der das Ziel oder der Stand ist, ist nicht
    belegt, also heisst er Zaehler und nicht Fortschritt.
    """
    aktiv, zur_wahl = [], []
    for o in orders:
        if o.get("completed") or o.get("isFailed"):
            continue
        if o.get("picked"):
            eintrag = {
                "name": o["model"],
                "belohnungen": [r for r in o.get("rewards") or [] if isinstance(r, str)],
                # Gemessen: `amount` 0 bei "0/2", "0/6", "0/2" im Spiel --
                # der Stand. Das Ziel selbst steht nicht im Spielstand.
                "ziele": [{"typ": z.get("type"), "stand": z.get("amount"),
                           "erledigt": z.get("completed")}
                          for z in o.get("objectives") or [] if isinstance(z, dict)],
            }
            # 0 hiess "keine Uhr laeuft", nicht "abgelaufen".
            zeit = o.get("timeLeft")
            if (o.get("shouldBeFailable") and isinstance(zeit, (int, float))
                    and not isinstance(zeit, bool) and zeit > 0):
                eintrag["zeitlimit_sekunden"] = zeit
            aktiv.append(eintrag)
        else:
            for p in o.get("picks") or []:
                if isinstance(p, dict) and isinstance(p.get("model"), str) and not p.get("failed"):
                    zur_wahl.append({
                        "name": p["model"],
                        "belohnungen": [r for r in p.get("rewards") or []
                                        if isinstance(r, str)]})
    return {"aktiv": aktiv, "zur_wahl": zur_wahl}


def _gebaeude_liste(gebaeude) -> list[dict]:
    """Welche Gebaeude, wie viele, wie viele Arbeiter -- die Zahl allein
    liess den Rat raten, was schon steht."""
    je: dict[str, dict] = {}
    for b in gebaeude:
        if not b.model:
            continue
        eintrag = je.setdefault(b.model, {"gebaeude": b.model, "anzahl": 0, "arbeiter": 0})
        eintrag["anzahl"] += 1
        eintrag["arbeiter"] += b.workers or 0
    return sorted(je.values(), key=lambda e: -e["anzahl"])


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
        "gebaeude_liste": _gebaeude_liste(state.buildings),
        "bauplaene_ungebaut": sorted(
            set(state.blueprints) - {b.model for b in state.buildings if b.model}),
        "ruf_quellen": _ruf_quellen(state.reputation_sources),
        "ruf_je_volk": state.reputation_by_race,
        "auftraege": _auftraege(state.orders),
        **({"bauplan_wahl": state.blueprint_pick} if state.blueprint_pick else {}),
        "lichtungen": state.glades,
        **({"lichtungen_nach_stufe": state.glades_by_level} if state.glades_by_level else {}),
        **({"statistik": state.stats} if state.stats else {}),
        **({"effekte": state.effects} if state.effects else {}),
        "vorkommen": state.deposits,
        "grundsteine": state.cornerstones,
        "gewonnen": state.won,
        "verloren": state.lost,
        "reihen_vorhanden": sorted(state.category_trends),
    }


@_wall
def get_state(save_dir: str | Path, runs_dir: str | Path = "runs",
              run_id: str | None = None, protokollieren: bool = True,
              auf_ruhe_warten: bool = True) -> dict:
    """Aktueller Zustand aus dem Spielstand.

    `auf_ruhe_warten` deckt den Regelfall ab: das Buendel ist nicht atomar,
    also wird gewartet, bis sich nichts mehr ruehrt. Wer weiss, dass gerade
    nicht geschrieben wird, spart sich das.
    """
    ordner = Path(save_dir)
    # `read_state` wirft nicht, wenn Dateien fehlen -- das ist richtig, denn
    # ein halbes Buendel ist besser als ein Absturz. Ein leerer Zustand sieht
    # dann aber aus wie eine Siedlung ohne Bevoelkerung, und niemand sagt,
    # dass in Wahrheit der Ordner fehlt. Also wird es hier gesagt.
    fehlende_dateien = [name for name in ("Save.save", "WorldSave.save", "MetaSave.save")
                        if not (ordner / name).exists()]
    if len(fehlende_dateien) == 3:
        return {
            "verfuegbar": False,
            "grund": (f"Unter {ordner} liegt kein Spielstand. "
                      "Mit --save-dir den Spielordner angeben."),
            "spielordner": str(ordner),
        }

    state, notes = read_state(ordner, wait=auf_ruhe_warten)
    kennung = None
    if protokollieren and state.game_time is not None:
        # Die Kennung darf die Spielzeit nicht enthalten -- sonst bekommt
        # jeder Aufruf seine eigene Datei, und alles, was zwei Staende
        # braucht, bleibt stumm. Genau das war auf dem Spielrechner der Fall.
        kennung, _ = watcher.mitschreiben(state, Path(runs_dir), run_id)
    fehlend = [n.field for n in notes if n.how == "fehlt"]
    # Gefunden, aber in fremder Form -- sieht sonst aus wie ein leeres Lager.
    unlesbar = {n.field: n.form for n in notes if n.how == "form_unbekannt"}
    out = _zustand_als_dict(state)
    # Wann das Spiel gespeichert hat, nicht wann gelesen wurde: das Fenster
    # zeigte sonst auch bei einem Stand von vor Stunden "gerade eben".
    try:
        from datetime import datetime, timezone
        out["gespeichert"] = datetime.fromtimestamp(
            (ordner / "Save.save").stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        pass
    if kennung:
        out["mitschrift"] = kennung
    out["verfuegbar"] = state.game_time is not None
    if fehlende_dateien:
        out["fehlende_dateien"] = fehlende_dateien
    if fehlend:
        out["nicht_gefunden"] = fehlend
    if unlesbar:
        out["form_unbekannt"] = unlesbar
    if not out["verfuegbar"]:
        out["grund"] = ("Der Spielstand liess sich lesen, enthaelt aber keine "
                        "Spielzeit. Laeuft gerade eine Siedlung?")
    return out


@_wall
def read_choice(bild: str | Path | None = None, text: list[str] | None = None,
                db: str | Path = "kb.sqlite", arten: tuple[str, ...] = ("effect",),
                aufnehmen: bool = False) -> dict:
    """Der Auswahlbildschirm als Namen und Zahlen -- nie als Bild.

    Gemessen am 22.09.2026: die angebotenen Grundsteine stehen nicht im
    Spielstand, auch nicht als Text. Deshalb der Bildschirm. Das Lesen
    passiert hier, lokal und deterministisch; was zurueckgeht, sind
    belegte Namen und die Angaben aus der Wissensbasis dazu.

    Drei Eingaenge, damit eine fehlende Abhaengigkeit nicht die ganze
    Kette stilllegt: ein aufgenommenes Bild, eine vorhandene Bilddatei,
    oder der bereits gelesene Text.
    """
    zeilen: list[str] = []
    quelle = "hand"
    am_rand = 0
    if text:
        # Eine einzelne Zeichenkette ist ein Name, keine Liste von Buchstaben.
        # Das Fenster uebergibt eine Liste, die Kommandozeile nicht zwingend.
        if isinstance(text, str):
            text = [text]
        zeilen = [t for t in text if (t or "").strip()]
    else:
        pfad = Path(bild) if bild else None
        if pfad is None and aufnehmen:
            try:
                pfad = screen.aufnehmen()
            except Exception as exc:
                return {"verfuegbar": False, "grund": str(exc),
                        "umgebung": screen.verfuegbar()}
        if pfad is None:
            return {
                "verfuegbar": False,
                "grund": ("Kein Bild und kein Text. Entweder `bild` auf ein "
                          "Bildschirmfoto zeigen lassen, `aufnehmen=True` setzen, "
                          "oder die gelesenen Kartentitel als `text` uebergeben."),
                "umgebung": screen.verfuegbar(),
            }
        quelle = str(pfad)
        try:
            erkannt, am_rand = screen.nur_mitte(screen.erkenne(pfad), screen.bildbreite(pfad))
            erkannt = screen.sortiere_nach_karten(erkannt)
        except Exception as exc:
            return {"verfuegbar": False, "grund": str(exc),
                    "umgebung": screen.verfuegbar()}
        zeilen = [z.text for z in erkannt]

    conn = kb.connect(db)
    try:
        gelesen = namen_match.lies_auswahl(conn, zeilen, arten=arten)
        getroffen = [g for g in gelesen if g["eindeutig"]]
        for eintrag in getroffen:
            eintrag["belegt"] = _belegt(conn, eintrag, arten)
            if not eintrag["belegt"]:
                # Derselbe deutsche Name fuer mehrere Eintraege ("Glücksbringer"):
                # belegt ist vielleicht ein anderer. Dann gilt der.
                for (andere,) in conn.execute(
                        "SELECT en FROM name_map WHERE de = ? AND en != ? AND "
                        "confidence = 'localization' ORDER BY en",
                        (eintrag["de"], eintrag["en"])):
                    probe = dict(eintrag, en=andere)
                    if _belegt(conn, probe, arten):
                        eintrag.update(probe, belegt=True)
                        break
    finally:
        conn.close()

    # Drei Toepfe statt einem. Die Aufnahme nimmt den ganzen Bildschirm, also
    # steht neben den Karten auch die Oberflaeche darin -- am 22.09.2026 an
    # einer offenen Grundsteinwahl gemessen: `Fuchs`, `Frosch`, `Biber` (die
    # Spezies oben links) und `Wucher` mit Guete 0,727. Alle vier standen
    # gleichberechtigt neben den beiden echten Karten.
    # Einmal je Name: in der Auftragsuebersicht stand jeder Auftrag in der
    # Seitenleiste und auf der Karte. Die erste Lesung bleibt.
    gesehen: set[str] = set()
    sicher = []
    for g in getroffen:
        if g["guete"] >= SICHER and g["en"] not in gesehen:
            gesehen.add(g["en"])
            sicher.append(g)
    # Belegtes zuerst, dann nach Guete. Sortiert, nicht gefiltert: die
    # Wissensbasis kennt 398 Grundsteine bei 2273 Namen, und
    # "Exportspezialisierung" stand am 22.09. wirklich zur Wahl, ohne
    # dort zu stehen. Ein harter Filter haette die Karte verschluckt --
    # und das waere schlimmer als die Spezies daneben.
    # Stabil und nur nach einem Schluessel: innerhalb der beiden Gruppen
    # bleibt die Lesereihenfolge von links nach rechts stehen. Der Spieler
    # sagt "die linke", und die Auskunft muss dieselbe meinen.
    sicher.sort(key=lambda g: not g["belegt"])
    unsicher = [g for g in getroffen if g["guete"] < SICHER]
    unklar = [g for g in gelesen if not g["eindeutig"] and g["kandidaten"]]
    return {
        "verfuegbar": bool(sicher),
        "quelle": quelle,
        "angebot": sicher,
        "belegt": [g for g in sicher if g["belegt"]],
        "sonst_gesehen": [g for g in sicher if not g["belegt"]][:8],
        "unsicher": unsicher[:5],
        "unklar": unklar[:5],
        "gelesene_zeilen": len(zeilen),
        # Zeilen aus den Randleisten (Voelker, Auftraege), nicht gelesen.
        "am_rand_verworfen": am_rand,
        "grund": None if sicher else _nichts_erkannt(quelle, [], unsicher),
    }


# Ab hier ist eine Lesung eine Lesung. Darunter ist sie eine Vermutung ueber
# den Text und gehoert benannt, nicht behauptet: "Wucher" kam mit Guete 0,727
# aus einem Bildschirm, auf dem das Wort gar nicht stand.
SICHER = 0.90


def _belegt(conn, eintrag: dict, arten: tuple[str, ...]) -> bool:
    """Kennt die Wissensbasis das als das, was zur Wahl steht?

    Ein Name allein reicht nicht: `Fuchs` und `Biber` stehen als Effekt in
    der Namenstabelle, sind aber Spezies in der Oberflaeche. Ein Grundstein
    hat eine Zeile in `cornerstones`, ein Bauplan eine in `buildings`. Was
    dort fehlt, ist Bildschirmtext, bis das Gegenteil dasteht.
    """
    if "order" in arten:
        # Auftraege haben keine eigene Tabelle -- belegt ist, was die
        # Lokalisierung als Auftrag fuehrt. Vorher wurden sie unter den
        # Grundsteinen gesucht und landeten alle unter "meist Oberflaeche".
        zeile = conn.execute(
            "SELECT 1 FROM name_map WHERE en = ? AND kind = 'order'",
            (eintrag["en"],)).fetchone()
        return zeile is not None

    if "building" in arten:
        zeile = conn.execute(
            "SELECT category, purpose, cost FROM buildings WHERE en = ?",
            (eintrag["en"],)).fetchone()
        if zeile:
            eintrag.update({"kategorie": zeile["category"], "zweck": zeile["purpose"],
                            "kosten": zeile["cost"]})
            return True
        return False

    zeile = conn.execute(
        "SELECT rarity, effect_text, origin FROM cornerstones WHERE en = ?",
        (eintrag["en"],)).fetchone()
    if zeile:
        eintrag.update({"seltenheit": zeile["rarity"], "wirkung": zeile["effect_text"],
                        "herkunft": zeile["origin"]})
        return True
    return False


def _nichts_erkannt(quelle: str, sonst: list | None = None,
                   unsicher: list | None = None) -> str:
    """Warum nichts herauskam -- je nach Weg eine andere Frage.

    Am Spielrechner stand im Handfeld `handelsverhandlungen`, und die
    Ausgabe fragte nach dem Bildschirmfoto und riet zu `pip install
    winsdk`. Beides gehoert zum Bildweg. Wer tippt, hat kein Bild gemacht
    und braucht keine Texterkennung.
    """
    if unsicher:
        namen = ", ".join(f"{u['de']} ({u['guete']})" for u in unsicher[:3])
        return (f"Gelesen, aber nicht sicher genug: {namen}. "
                "Stand das so da? Dann von Hand eintippen.")
    if sonst:
        namen = ", ".join(s["de"] for s in sonst[:4])
        return ("Erkannt wurden nur Namen, die die Wissensbasis nicht als "
                f"Angebot kennt: {namen}. Das ist Oberflaeche, keine Karte -- "
                "oder die Karte fehlt in der Wissensbasis.")
    if quelle == "hand":
        return ("Keiner der eingetippten Namen kommt einem belegten nahe. "
                "Grundsteine und Baupläne stehen unter verschiedenen Arten -- "
                "oben umschalten, oder den Namen so tippen, wie er auf der "
                "Karte steht.")
    return ("Nichts erkannt, was einem belegten Namen nahekommt. Stand der "
            "Auswahlbildschirm offen, als das Bild entstand?")


REZEPTE_HOECHSTENS = 8


def _zutaten(roh: Any) -> list[list[dict]]:
    """`inputs` aus der Wissensbasis: je Gruppe die Alternativen, kompakt."""
    try:
        gruppen = json.loads(roh) if isinstance(roh, str) else roh
    except (json.JSONDecodeError, TypeError):
        return []
    out = []
    for gruppe in gruppen if isinstance(gruppen, list) else []:
        wahl = [{"menge": z.get("menge"), "ware": z.get("ware")}
                for z in (gruppe if isinstance(gruppe, list) else [])
                if isinstance(z, dict) and z.get("ware")]
        if wahl:
            out.append(wahl)
    return out


def _kb_gebaeude(conn, name: str) -> str:
    """Der Gebaeudename, wie die Wissensbasis ihn schreibt -- ueber
    `nahrung._schluessel` (Gross-/Kleinschreibung, Apostroph, Leerzeichen)."""
    schluessel = nahrung._schluessel(name)
    for (kandidat,) in conn.execute(
            "SELECT building FROM production UNION SELECT building FROM recipes "
            "UNION SELECT en FROM buildings"):
        if kandidat and nahrung._schluessel(kandidat) == schluessel:
            return kandidat
    return name


def _deutsch_fuer(namen: dict[str, str], name: str) -> str | None:
    """Deutscher Name, auch wenn Spielstand und Lokalisierung verschieden schreiben."""
    if name in namen:
        return namen[name]
    schluessel = nahrung._schluessel(name)
    for en, de in namen.items():
        if nahrung._schluessel(en) == schluessel:
            return de
    return None


def _rezepte(conn, gebaeude: str | None = None, produkt: str | None = None) -> list[dict]:
    """Rezepte eines Gebaeudes oder fuer eine Ware -- mit Sternen und Zutaten.

    `production` ist die belastbare Zuordnung Ware -> Gebaeude mit Sternen;
    `recipes` traegt die Mengen. Beides zusammen, `production` zuerst.
    """
    out: list[dict] = []
    gesehen: set[tuple] = set()
    if gebaeude:
        # Spielstand und Wiki schreiben verschieden: „Trapper's Camp“ gegen
        # „Trappers' Camp“ -- am 25.09.2026 kam der Fallenstellerlager-Bauplan
        # deshalb ohne ein einziges Rezept beim Rat an.
        gebaeude = _kb_gebaeude(conn, gebaeude)
        zeilen = conn.execute(
            "SELECT product, building, stars, inputs FROM production "
            "WHERE building = ? COLLATE NOCASE ORDER BY stars DESC, product", (gebaeude,))
    else:
        zeilen = conn.execute(
            "SELECT product, building, stars, inputs FROM production "
            "WHERE product = ? COLLATE NOCASE ORDER BY stars DESC, building", (produkt,))
    for r in zeilen:
        eintrag = {"produkt": r["product"], "gebaeude": r["building"], "sterne": r["stars"]}
        # Zuerst das Rezept von der Seite *dieses* Gebaeudes. `production.inputs`
        # kommt aus der Warenuebersicht und gilt fuer die Ware, nicht fuer das
        # Gebaeude; ein Rezept ohne Gebaeude kann jedem gehoeren. Am 25.09.2026
        # zeigte die Kueferei dadurch falsche Zutaten.
        rezept = conn.execute(
            "SELECT inputs FROM recipes WHERE product = ? COLLATE NOCASE "
            "AND building = ? COLLATE NOCASE LIMIT 1",
            (r["product"], r["building"])).fetchone()
        zutaten = _zutaten(rezept["inputs"]) if rezept else []
        if not zutaten:
            zutaten = _zutaten(r["inputs"])
        if zutaten:
            eintrag["zutaten"] = zutaten
        gesehen.add((str(r["product"]).lower(), str(r["building"]).lower()))
        out.append(eintrag)
    # Rezepte, die `production` nicht kennt (nur von der Gebaeudeseite).
    if gebaeude:
        rest = conn.execute(
            "SELECT product, building, stars, inputs FROM recipes "
            "WHERE building = ? COLLATE NOCASE AND product IS NOT NULL", (gebaeude,))
    else:
        rest = conn.execute(
            "SELECT product, building, stars, inputs FROM recipes "
            "WHERE product = ? COLLATE NOCASE AND building IS NOT NULL", (produkt,))
    for r in rest:
        if (str(r["product"]).lower(), str(r["building"]).lower()) in gesehen:
            continue
        gesehen.add((str(r["product"]).lower(), str(r["building"]).lower()))
        eintrag = {"produkt": r["product"], "gebaeude": r["building"], "sterne": r["stars"]}
        if _zutaten(r["inputs"]):
            eintrag["zutaten"] = _zutaten(r["inputs"])
        out.append(eintrag)
    return [{k: v for k, v in e.items() if v is not None} for e in out[:REZEPTE_HOECHSTENS]]


@_wall
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
            for kandidat in kandidaten:
                zeile = conn.execute(
                    "SELECT en, cost, worker_slots, source_page FROM buildings "
                    "WHERE en = ? COLLATE NOCASE", (_kb_gebaeude(conn, kandidat),)).fetchone()
                if zeile:
                    treffer["gebaeude"] = dict(zeile)
                    break

        # Rezepte mit Zutaten. Ohne sie riet der Rat am 23.09.2026, woraus
        # ein Baumaterialpaket entsteht, und was ein angebotener Brennofen
        # herstellt.
        if "gebaeude" in treffer:
            rezepte = _rezepte(conn, gebaeude=treffer["gebaeude"]["en"])
            if rezepte:
                treffer["rezepte"] = rezepte
        if "ware" in treffer:
            rezepte = _rezepte(conn, produkt=treffer["ware"]["en"])
            if rezepte:
                treffer["hergestellt_in"] = rezepte

        if not namen and "ware" not in treffer and "gebaeude" not in treffer:
            treffer["hinweis"] = (
                "Nichts gefunden. Die Wissensbasis ist erst teilweise gefüllt: "
                "Waren, Gebäude und Rezepte stehen drin, Grundsteine nur als Namen.")
        return treffer
    finally:
        conn.close()


def _bauplan_vergleich(conn, aktuell: dict, verfuegbar: dict[str, str],
                       namen: dict[str, str]) -> list[dict]:
    """Je angebotenem Bauplan: was er herstellt, gegen das, was schon da ist.

    Sehen, nicht urteilen: Sterne des Angebots gegen die besten Sterne eines
    Gebaeudes, das steht *oder freigeschaltet ist* -- am 23.09.2026 bot das
    Spiel ein Pochwerk mit Ziegeln ★★ an, waehrend die Werkstatt (Ziegel ★★)
    aus dem vorigen Pick schon freigeschaltet war. Dazu je Zutatengruppe die
    Alternative mit dem groessten Lagerbestand und ob die Ware essbar ist.
    """
    angebot = [n for n in (aktuell.get("blueprint_pick") or {}).get("angebot") or []
               if isinstance(n, str)]
    if not angebot:
        return []
    je_schluessel = {nahrung._schluessel(n): (n, st) for n, st in (verfuegbar or {}).items()}
    bisher: dict[str, dict] = {}
    for r in conn.execute("SELECT product, building, stars FROM production"):
        treffer = je_schluessel.get(nahrung._schluessel(r["building"]))
        if treffer is None:
            continue
        ware = str(r["product"]).casefold()
        sterne = r["stars"] or 0
        if ware not in bisher or sterne > bisher[ware]["sterne"]:
            bisher[ware] = {"sterne": sterne, "gebaeude": treffer[0],
                            "gebaeude_de": namen.get(treffer[0]), "status": treffer[1]}
    lager = nahrung._bestand_auf_waren(conn, aktuell.get("storage") or {})
    lager_klein = {k.casefold(): v for k, v in lager.items()}
    essbar = {r["en"].casefold(): r["eating_fullness"] for r in conn.execute(
        "SELECT en, eating_fullness FROM resources WHERE eatable = 1") if r["en"]}

    out = []
    for name in angebot:
        waren = []
        for rezept in _rezepte(conn, gebaeude=name):
            ware = rezept["produkt"]
            sterne = rezept.get("sterne") or 0
            vorher = bisher.get(str(ware).casefold())
            zeile: dict[str, Any] = {"ware": ware, "ware_de": namen.get(ware, ware),
                                     "sterne": sterne,
                                     "bisher": {k: v for k, v in (vorher or {}).items()
                                                if v is not None} or None,
                                     "besser": vorher is None or sterne > vorher["sterne"]}
            zutaten = []
            for gruppe in rezept.get("zutaten") or []:
                beste = max(gruppe, key=lambda z: lager_klein.get(str(z["ware"]).casefold(), 0))
                zutaten.append({"ware": beste["ware"],
                                "ware_de": namen.get(beste["ware"], beste["ware"]),
                                "je_durchlauf": beste.get("menge"),
                                "im_lager": lager_klein.get(str(beste["ware"]).casefold(), 0)})
            if zutaten:
                zeile["zutaten"] = zutaten
            if str(ware).casefold() in essbar:
                zeile["nahrung"] = essbar[str(ware).casefold()]
            waren.append(zeile)
        schon = (verfuegbar or {}).get(name) or next(
            (st for n, st in (verfuegbar or {}).items()
             if nahrung._schluessel(n) == nahrung._schluessel(name)), None)
        out.append({
            # Schon freigeschaltet (etwa beim Einbetten gewaehlt) und trotzdem
            # angeboten: dann bringt die Wahl kein neues Gebaeude.
            **({"schon_freigeschaltet": schon} if schon else {}),
            "gebaeude": name, "gebaeude_de": _deutsch_fuer(namen, name),
            "besser_oder_neu": sum(1 for w in waren if w["besser"]),
            "nahrung": sum(1 for w in waren if "nahrung" in w),
            "zutaten_im_lager": all(z["im_lager"] > 0 for w in waren
                                    for z in w.get("zutaten", [])) if waren else None,
            "waren": waren})
    return out


@_wall
def lage_wissen(runs_dir: str | Path = "runs", db: str | Path = "kb.sqlite",
                run_id: str | None = None) -> dict:
    """Was die Spieldaten zur Lage wissen: Waren, Gebaeude, Trends je Ware.

    Der Rat riet einmal, Pakete zu "oeffnen" -- erfundene Mechanik. Was eine
    Ware ist (Kategorie, essbar, brennbar, Handelswert) und was ein Gebaeude
    herstellt, steht in der Wissensbasis. Das geht jetzt mit, statt dass das
    Modell es aus dem Gedaechtnis ergaenzt.
    """
    zustaende, quelle = _letzte_zustaende(runs_dir, run_id)
    if not zustaende:
        return {"verfuegbar": False, "grund": "Keine Mitschrift vorhanden."}
    aktuell = zustaende[-1]
    conn = kb.connect(db)
    try:
        namen = nahrung._deutsch(conn)
        waren = []
        for ware, menge in nahrung._bestand_auf_waren(conn, aktuell.get("storage") or {}).items():
            if not menge:
                continue
            zeile = conn.execute(
                "SELECT category, eatable, eating_fullness, burnable, burning_time, "
                "sell_value, buy_value FROM resources WHERE en = ? COLLATE NOCASE",
                (ware,)).fetchone()
            eintrag: dict[str, Any] = {"ware": ware, "ware_de": namen.get(ware, ware),
                                       "menge": menge}
            if zeile:
                eintrag.update({
                    "kategorie": zeile["category"],
                    "essbar": bool(zeile["eatable"]) if zeile["eatable"] is not None else None,
                    "saettigung": zeile["eating_fullness"],
                    "brennbar": bool(zeile["burnable"]) if zeile["burnable"] is not None else None,
                    "brenndauer": zeile["burning_time"],
                    "verkaufswert": zeile["sell_value"],
                    "kaufwert": zeile["buy_value"]})
            waren.append({k: v for k, v in eintrag.items() if v is not None})

        verfuegbar = _verfuegbar(aktuell) or {}
        kb_gebaeude = {nahrung._schluessel(r["en"]): r for r in conn.execute(
            "SELECT en, category, purpose, worker_slots, cost, products FROM buildings")}
        erzeugt: dict[str, list[dict]] = {}
        for r in conn.execute("SELECT product, building, stars FROM production "
                              "ORDER BY stars DESC NULLS LAST, product"):
            erzeugt.setdefault(nahrung._schluessel(r["building"]), []).append(
                {"ware": r["product"], "sterne": r["stars"]})
        gebaeude = {}
        for name, status in list(verfuegbar.items())[:150]:
            s = nahrung._schluessel(name)
            zeile = kb_gebaeude.get(s)
            if zeile is None and s not in erzeugt:
                continue
            eintrag = {"status": status, "gebaeude_de": _deutsch_fuer(namen, name)}
            if zeile is not None:
                try:
                    kosten = json.loads(zeile["cost"]) if zeile["cost"] else None
                except (json.JSONDecodeError, TypeError):
                    kosten = zeile["cost"]
                eintrag.update({"kategorie": zeile["category"], "zweck": zeile["purpose"],
                                "arbeitsplaetze": zeile["worker_slots"], "kosten": kosten})
            if s in erzeugt:
                eintrag["erzeugnisse"] = erzeugt[s][:8]
            elif status != "steht":
                # Baubar, aber stellt nichts her: Zaun, Lampe, Weg. Fuer den
                # Rat ohne Belang, und der Auszug bleibt klein.
                continue
            if isinstance(eintrag.get("zweck"), str) and len(eintrag["zweck"]) > 120:
                eintrag["zweck"] = eintrag["zweck"][:117] + "…"
            gebaeude[name] = {k: v for k, v in eintrag.items() if v is not None}

        # Was die offene Bauplanwahl anbietet: mit Rezepten und Zutaten. Am
        # 23.09.2026 riet der Rat, was ein angebotener Brennofen herstellt --
        # die Wissensbasis wusste es, der Auszug nicht.
        for name in (aktuell.get("blueprint_pick") or {}).get("angebot") or []:
            if not isinstance(name, str):
                continue
            eintrag = dict(gebaeude.get(name) or {})
            eintrag["status"] = "angeboten"
            if not eintrag.get("gebaeude_de"):
                eintrag["gebaeude_de"] = _deutsch_fuer(namen, name)
            zeile = kb_gebaeude.get(nahrung._schluessel(name))
            if zeile is not None:
                eintrag.setdefault("arbeitsplaetze", zeile["worker_slots"])
            rezepte = _rezepte(conn, gebaeude=name)
            if rezepte:
                eintrag["rezepte"] = [{k: v for k, v in r.items() if k != "gebaeude"}
                                      for r in rezepte]
            eintrag.pop("erzeugnisse", None)       # stehen in `rezepte`
            gebaeude[name] = {k: v for k, v in eintrag.items() if v is not None}

        vergleich = _bauplan_vergleich(conn, aktuell, verfuegbar, namen)
    finally:
        conn.close()

    trends = {"fallend": [], "steigend": []}
    if len(zustaende) >= 2:
        vorher = zustaende[-2]
        alle = forecast.waren_trends(aktuell.get("goods_trends") or {},
                                     vorher.get("goods_trends") or {},
                                     vorher.get("game_time"), aktuell.get("game_time"))
        for t in alle:
            t["ware_de"] = namen.get(t["ware"], t["ware"])
        trends["fallend"] = sorted((t for t in alle if t["rate_je_minute"] < 0),
                                   key=lambda t: t["rate_je_minute"])[:5]
        trends["steigend"] = sorted((t for t in alle if t["rate_je_minute"] > 0),
                                    key=lambda t: -t["rate_je_minute"])[:3]
    # Deutsche Namen fuer Bauplanangebot und aktive Effekte -- sonst kaemen
    # sie als Modellkennung beim Rat an. Was die Wissensbasis nicht kennt,
    # fehlt hier und bleibt englisch.
    gesucht = list((aktuell.get("blueprint_pick") or {}).get("angebot") or [])
    gesucht += [e.get("modell") for e in ((aktuell.get("effects") or {}).get("aktiv") or [])
                if isinstance(e, dict)]
    namen_de = {}
    for name in gesucht:
        if not isinstance(name, str):
            continue
        de = _deutsch_fuer(namen, name) or namen.get(strip_prefixes(name)[0])
        if de and de != name:
            namen_de[name] = de
    out = {"verfuegbar": True, "quelle": quelle, "waren": waren,
           "gebaeude": gebaeude, "trends": trends, "namen_de": namen_de}
    if vergleich:
        out["bauplan_vergleich"] = vergleich
    return out


@_wall
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
    out: dict[str, Any] = {}
    if f.rate_per_second is None:
        # Sonst stand am Spielrechner nur „unbekannt" -- nach dem Sieg, als
        # das Spiel nicht mehr lief und die Reihe sich nicht bewegte.
        # Zwei Staende sind da; ohne frische Stuetzstellen hat sich die Reihe
        # nicht bewegt. Die Warnung aus der Rechnung ("zweiter Spielstand
        # noetig") fuehrte dann in die Irre.
        out["grund"] = ("Zwischen den letzten beiden Spielständen hat sich die "
                        "Nahrungsreihe nicht bewegt -- Spiel pausiert oder Lauf beendet."
                        if not f.samples_used else
                        (f.warning or "Aus den letzten Spielständen lässt sich keine Rate rechnen."))
    return {
        **out,
        "verfuegbar": f.rate_per_second is not None,
        "quelle": quelle,
        "bestand": f.stock,
        "rate_je_spielzeitsekunde": f.rate_per_second,
        "reichweite_sekunden": f.runway_seconds,
        "stuetzstellen": f.samples_used,
        "warnung": f.warning,
    }


@_wall
def food_advice(runs_dir: str | Path = "runs", db: str | Path = "kb.sqlite",
                run_id: str | None = None, kategorie: str = "Food") -> dict:
    """Was gegen den Nahrungsmangel zu bauen waere -- nicht nur, wann er kommt.

    Das ist eine Ergaenzung zur Werkzeugliste der Spec. Sie steht dort nicht,
    aber die Spec nennt den Nahrungsmangel im ersten Jahr als das Problem,
    und `food_forecast` beantwortet nur dessen Diagnose. Gerechnet wird auf
    denselben Grundlagen: die Rezepte aus der Wissensbasis, der Bestand aus
    dem Spielstand, der Verbrauch aus der Zeitreihe. Kein Modell beteiligt.
    """
    zustaende, quelle = _letzte_zustaende(runs_dir, run_id)
    if not zustaende:
        return {"verfuegbar": False, "grund": "Keine Mitschrift vorhanden."}

    aktuell = _als_zustand(zustaende[-1])
    verbrauch = None
    reichweite = None
    if len(zustaende) >= 2:
        f = _food_forecast(aktuell, _als_zustand(zustaende[-2]), category=kategorie)
        verbrauch = f.rate_per_second
        reichweite = f.runway_seconds

    conn = kb.connect(db)
    try:
        r = nahrung.rat(conn, aktuell.storage or {}, verbrauch, reichweite,
                        verfuegbar=_verfuegbar(zustaende[-1]))
        essbar = nahrung.essbar_im_lager(conn, aktuell.storage or {})
    finally:
        conn.close()

    return {
        "verfuegbar": bool(r.vorschlaege),
        "quelle": quelle,
        "empfehlung": r.empfehlung,
        "begruendung": r.begruendung,
        "alternative": r.alternative,
        "verbrauch_je_spielzeitsekunde": verbrauch,
        "reichweite_sekunden": reichweite,
        # Was im Lager ueberhaupt Nahrung ist -- aus `eatable` der Spieldaten.
        # Der Rat riet sonst, Vorratspakete zu oeffnen.
        "essbar_im_lager": essbar,
        "ketten": [
            {
                "gebaeude": v.gebaeude,
                "gebaeude_de": v.gebaeude_de,
                "produkt": v.produkt,
                "produkt_de": v.produkt_de,
                # Deutsch nach aussen, englische ID daneben -- so verlangt
                # es SPEC.md, und dafuer wurden die 2266 Namen belegt.
                "einsatz": [{"menge": z.menge * v.zyklen, "ware": z.name,
                             "ware_en": z.ware} for z in v.zutaten],
                "durchlaeufe": round(v.zyklen, 1),
                "saettigung_rein": round(v.saettigung_rein, 1),
                "saettigung_raus": round(v.saettigung_raus, 1),
                "gewinn": round(v.gewinn, 1),
                "faktor": round(v.faktor, 2) if v.faktor else None,
                "sekunden": v.dauer,
                "engpass": v.engpass_de or v.engpass,
                "engpass_en": v.engpass,
                "reichweite_plus_sekunden": (round(v.reichweite_plus)
                                             if v.reichweite_plus else None),
                "status": v.status,
            }
            for v in r.vorschlaege[:6]
        ],
    }


@_wall
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


@_wall
def log_event(text: str, runs_dir: str | Path = "runs", run_id: str | None = None,
              art: str | None = None, spielzeit: float | None = None,
              jahr: int | None = None) -> dict:
    """Freitextnotiz in den Lauf schreiben.

    `art="rat"` markiert eine Empfehlung des Rats; der Laufbericht stellt sie
    spaeter neben den Ausgang.
    """
    runs = Path(runs_dir)
    runs.mkdir(parents=True, exist_ok=True)
    kennung = run_id or _neueste_mitschrift(runs) or "notizen"
    ziel = runs / f"{kennung}.jsonl"
    eintrag = {"typ": "notiz", "zeitpunkt": datetime.now(timezone.utc).isoformat(), "text": text}
    for feld, wert in (("art", art), ("spielzeit", spielzeit), ("jahr", jahr)):
        if wert is not None:
            eintrag[feld] = wert
    with ziel.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    return {"geschrieben": str(ziel), "eintrag": eintrag}


@_wall
def analyze_runs(n: int = 10, save_dir: str | Path | None = None,
                 runs_dir: str | Path = "runs") -> dict:
    """Die letzten n Laeufe gegenueberstellen."""
    records: list[dict] = []
    quelle = None
    if save_dir:
        meta_pfad = Path(save_dir) / "MetaSave.save"
        if meta_pfad.exists():
            # `_load` kennt BOM und halb geschriebene Dateien; ein eigenes
            # json.loads meldete bei einer BOM "keine Laufhistorie".
            meta = save_reader._load(meta_pfad)
            if isinstance(meta, dict):
                records = ((meta.get("gamesHistory") or {}).get("records")) or []
                quelle = "MetaSave.gamesHistory"

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
        self.storage = daten.get("storage") or {}


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
