"""Biom-Namen: die Kennung aus dem Spielstand -> der Name im Spiel.

Gemessen am 27.09.2026 an der Spielhistorie vom Spielrechner: der Spielstand
führt Biome unter ihrer Modellkennung -- „Poro Biome“, „Bay“, „Cave“,
„Moorlands“, „Sealed Biome“, „The Marshlands“ --, das Spiel zeigt
„Bambusebene“, „Küstenhain“, „Felsschlucht“, „Scharlachroter Obstgarten“,
„Versiegelter Wald“, „Sümpfe“. Mit der Kennung fand die Tierliste nichts, und
die Laufhistorie sprach von Bioms, die niemand so kennt.

Die Brücke ist der Lokalisierungsschlüssel `Biome_<Kennung ohne Leerzeichen>_Name`
in `data/name_map_localized.csv` (aus den Spieldaten, nicht geraten). Wo er
nicht passt („The Marshlands“ heißt dort `Biome_Mushroom_Name`), hilft der
englische Name selbst.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

log = logging.getLogger(__name__)

PFAD = Path(__file__).resolve().parents[2] / "data" / "name_map_localized.csv"

_speicher: dict[str, tuple[float, dict[str, dict], dict[str, dict]]] = {}


def _schluessel(text: str | None) -> str:
    text = (text or "").casefold().strip()
    if text.startswith("the "):
        text = text[4:]
    return "".join(c for c in text if c.isalnum())


def _tabellen(pfad: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    """(nach Lokalisierungsschlüssel, nach englischem Namen) -- nur Biome."""
    try:
        stand = pfad.stat().st_mtime
    except OSError:
        return {}, {}
    alt = _speicher.get(str(pfad))
    if alt and alt[0] == stand:
        return alt[1], alt[2]
    nach_schluessel: dict[str, dict] = {}
    nach_name: dict[str, dict] = {}
    try:
        with pfad.open(encoding="utf-8", newline="") as fh:
            for z in csv.DictReader(fh):
                if z.get("kind") != "biome" or not z.get("en"):
                    continue
                eintrag = {"en": z["en"], "de": z.get("de") or z["en"]}
                if z.get("loc_key"):
                    nach_schluessel[_schluessel(z["loc_key"])] = eintrag
                nach_name.setdefault(_schluessel(z["en"]), eintrag)
    except (OSError, csv.Error) as exc:
        log.warning("Biom-Namen nicht lesbar: %s", exc)
        return {}, {}
    _speicher[str(pfad)] = (stand, nach_schluessel, nach_name)
    return nach_schluessel, nach_name


def nachsehen(roh: str | None, pfad: Path | str = PFAD) -> dict | None:
    """{"en", "de"} zu einer Kennung aus dem Spielstand -- None, wenn unbekannt."""
    if not roh:
        return None
    nach_schluessel, nach_name = _tabellen(Path(pfad))
    kern = _schluessel(roh)
    return nach_schluessel.get(f"biome{kern}name") or nach_name.get(kern)


def englisch(roh: str | None) -> str | None:
    treffer = nachsehen(roh)
    return treffer["en"] if treffer else roh


def deutsch(roh: str | None) -> str | None:
    treffer = nachsehen(roh)
    return treffer["de"] if treffer else roh
