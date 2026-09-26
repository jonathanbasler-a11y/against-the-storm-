"""Community-Tierlisten -- Meinungen, keine Spieldaten.

Wunsch vom Spielrechner (26.09.2026): „Der Ratgeber soll die Tiers sagen
und, falls er anders rät, erklären warum.“ Die Stufen stehen in
`data/tierlisten.csv`, von Hand aus den Quellen gepflegt, je Zeile mit
Quelle, Stand und Kontext (viele Listen gelten fuer Prestige 9 und aeltere
Versionen). Mehrere Quellen je Eintrag sind gewollt: Widersprueche sollen
sichtbar bleiben.

Kein Schaber zur Laufzeit -- die Seiten aendern ihr Format, und an den Rat
geht nur, was jemand gelesen hat.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

log = logging.getLogger(__name__)

PFAD = Path(__file__).resolve().parents[2] / "data" / "tierlisten.csv"
KATEGORIEN = ("grundstein", "gebaeude", "volk", "biom")
STUFEN = ("S", "A", "B", "C", "D")

_speicher: dict[str, tuple[float, list[dict]]] = {}


def schluessel(name: str | None) -> str:
    """„The Marshlands“ = „Marshlands“, „Trapper's Camp“ = „Trappers' Camp“."""
    text = (name or "").casefold().strip()
    if text.startswith("the "):
        text = text[4:]
    return "".join(c for c in text if c.isalnum())


def laden(pfad: Path | str = PFAD) -> list[dict]:
    """Alle Zeilen; leer, wenn die Datei fehlt oder nicht lesbar ist."""
    pfad = Path(pfad)
    try:
        stand = pfad.stat().st_mtime
    except OSError:
        return []
    alt = _speicher.get(str(pfad))
    if alt and alt[0] == stand:
        return alt[1]
    try:
        with pfad.open(encoding="utf-8", newline="") as fh:
            zeilen = [{k: (v or "").strip() for k, v in z.items()}
                      for z in csv.DictReader(fh)]
    except (OSError, csv.Error) as exc:
        log.warning("Tierlisten nicht lesbar: %s", exc)
        return []
    zeilen = [z for z in zeilen if z.get("kategorie") in KATEGORIEN
              and z.get("stufe") in STUFEN and z.get("en")]
    _speicher[str(pfad)] = (stand, zeilen)
    return zeilen


def nachsehen(kategorie: str, name: str | None, pfad: Path | str = PFAD) -> list[dict]:
    """Die Stufen eines Eintrags, je Quelle eine -- kompakt fuer den Rat."""
    if not name:
        return []
    ziel = schluessel(name)
    out = []
    for z in laden(pfad):
        if z["kategorie"] == kategorie and schluessel(z["en"]) == ziel:
            eintrag = {"stufe": z["stufe"], "quelle": z.get("quelle") or "?",
                       "stand": z.get("stand") or "unbekannt"}
            for feld in ("kontext", "notiz"):
                if z.get(feld):
                    eintrag[feld] = z[feld]
            out.append(eintrag)
    return out


def kurz(stufen: list[dict]) -> str:
    """„A (ClashiVerse 2026-09, Prestige 9)“ -- fuer das Fenster."""
    teile = []
    for s in stufen:
        zusatz = ", ".join(x for x in (s.get("stand") if s.get("stand") != "unbekannt" else None,
                                       s.get("kontext")) if x)
        teile.append(f"{s['stufe']} ({s['quelle']}{', ' + zusatz if zusatz else ''})")
    return " / ".join(teile)
