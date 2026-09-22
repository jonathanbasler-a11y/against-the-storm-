"""Gelesenen Text auf belegte Namen abbilden.

Phase 3 ist entschieden: die angebotenen Grundsteine stehen nicht im
Spielstand, auch nicht als Text (gemessen am 22.09.2026 an einer offenen
Grundsteinwahl). Der Bildschirm ist also noetig.

Das macht die Texterkennung aber nicht zum schwachen Glied. Sie muss den
Namen nicht richtig lesen -- sie muss ihn nur nah genug lesen, dass der
Abgleich eindeutig wird. Und dagegen steht eine Tabelle mit 2266 belegten
deutschen Namen aus der Lokalisierung des Spiels.

"PlLZFUHRER" ohne Umlaut, mit l statt i: 0,87 Aehnlichkeit zu "Pilzführer",
und der naechste Kandidat liegt weit darunter. Genau das ist der Grund, die
Namen vorher zu belegen statt sie zu raten.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

# Die Oberflaeche schreibt Karten in Grossbuchstaben, die Texterkennung
# verwechselt I/l/1 und verliert Umlautpunkte. All das faellt weg, bevor
# verglichen wird -- was bleibt, ist das Geruest des Wortes.
_NICHT_WORT = re.compile(r"[^a-z0-9]+")
_VERWECHSLUNG = str.maketrans({"l": "i", "1": "i", "0": "o", "5": "s", "8": "b"})


def falte(text: str) -> str:
    """'PlLZFÜHRER' -> 'piizfuhrer'. Klein, ohne Umlaute, ohne Zierrat."""
    zerlegt = unicodedata.normalize("NFKD", (text or "").replace("ß", "ss"))
    ohne_akzent = "".join(z for z in zerlegt if not unicodedata.combining(z))
    return _NICHT_WORT.sub("", ohne_akzent.lower()).translate(_VERWECHSLUNG)


@dataclass(frozen=True)
class Treffer:
    gelesen: str
    de: str
    en: str
    kind: str | None
    guete: float          # 1,0 = Zeichen fuer Zeichen gleich

    @property
    def sicher(self) -> bool:
        return self.guete >= 0.95


def kandidaten(conn: sqlite3.Connection,
               arten: tuple[str, ...] | None = None) -> list[tuple[str, str, str]]:
    """(de, en, kind) aus der Namenstabelle, nur Belegtes."""
    sql = ("SELECT de, en, kind FROM name_map "
           "WHERE confidence = 'localization' AND de IS NOT NULL")
    params: tuple = ()
    if arten:
        sql += " AND kind IN (%s)" % ",".join("?" * len(arten))
        params = arten
    return [(r["de"], r["en"], r["kind"]) for r in conn.execute(sql, params)]


def passe(gelesen: str, tabelle: list[tuple[str, str, str]],
          mindest: float = 0.72, anzahl: int = 3) -> list[Treffer]:
    """Den gelesenen Text auf die naechsten Namen abbilden.

    Zurueck kommen bis zu `anzahl` Kandidaten, der beste zuerst. Mehrere
    zu liefern ist Absicht: wenn zwei dicht beieinanderliegen, ist die
    Lesung nicht eindeutig, und das soll sichtbar sein statt geraten.
    """
    ziel = falte(gelesen)
    if not ziel:
        return []
    bewertet: list[Treffer] = []
    for de, en, kind in tabelle:
        kandidat = falte(de)
        if not kandidat:
            continue
        # Schneller Vorfilter: Laengen, die weit auseinanderliegen, koennen
        # die Schwelle nicht mehr erreichen.
        kurz, lang = sorted((len(ziel), len(kandidat)))
        if lang and kurz / lang < mindest:
            continue
        guete = SequenceMatcher(None, ziel, kandidat).ratio()
        if guete >= mindest:
            bewertet.append(Treffer(gelesen, de, en, kind, round(guete, 3)))
    bewertet.sort(key=lambda t: (-t.guete, t.de))
    return bewertet[:anzahl]


def eindeutig(treffer: list[Treffer], abstand: float = 0.06) -> Treffer | None:
    """Der beste Treffer, wenn er sich deutlich genug abhebt.

    Ohne Abstand keine Auskunft: zwei Namen, die gleich nah liegen, sind
    eine Lesung, die nicht entschieden ist. Die Spec verlangt eine
    Empfehlung, nicht eine Vermutung ueber den Text.
    """
    if not treffer:
        return None
    if len(treffer) == 1 or treffer[0].guete - treffer[1].guete >= abstand:
        return treffer[0]
    return None


def lies_auswahl(conn: sqlite3.Connection, zeilen: list[str],
                 arten: tuple[str, ...] = ("effect",),
                 mindest: float = 0.72) -> list[dict]:
    """Mehrere gelesene Kartentitel auf einmal abbilden.

    Ausgabe ist das, was aus Phase 3 in das Modell geht: Namen und Zahlen,
    kein Bild und kein Rohtext.
    """
    tabelle = kandidaten(conn, arten)
    out: list[dict] = []
    for zeile in zeilen:
        text = " ".join((zeile or "").split())
        if not text:
            continue
        treffer = passe(text, tabelle, mindest=mindest)
        beste = eindeutig(treffer)
        out.append({
            "gelesen": text,
            "de": beste.de if beste else None,
            "en": beste.en if beste else None,
            "kind": beste.kind if beste else None,
            "guete": beste.guete if beste else None,
            "eindeutig": beste is not None,
            "kandidaten": [{"de": t.de, "en": t.en, "guete": t.guete}
                           for t in treffer] if beste is None else [],
        })
    return out
