"""Tabellen aus gerendertem MediaWiki-HTML lesen.

Der Wikitext der Listenseiten hilft nicht weiter: `{{Perks|search=...}}` ist
eine Abfrage, die Daten stehen nicht drin. Im **gerenderten** HTML stehen sie
-- die Lua-Module laufen auf dem Server und klappen die Tabelle aus. `List of
Perks.html` hat 745 KB, der zugehoerige Wikitext eine Zeile.

Nur Standardbibliothek: `html.parser`. Keine Fremdbibliothek, weil das Ganze
auf dem Spielrechner laufen soll und die Spec Abhaengigkeiten knapp haelt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

LEER = re.compile(r"\s+")


@dataclass
class Tabelle:
    kopf: list[str] = field(default_factory=list)
    zeilen: list[list[str]] = field(default_factory=list)
    css: str = ""

    @property
    def als_dicts(self) -> list[dict[str, str]]:
        """Zeilen als Dictionaries, Kopfzeile als Schluessel."""
        out: list[dict[str, str]] = []
        for zeile in self.zeilen:
            if not any(z.strip() for z in zeile):
                continue
            eintrag = {}
            for i, wert in enumerate(zeile):
                schluessel = self.kopf[i] if i < len(self.kopf) else f"spalte_{i + 1}"
                # Gleiche Kopfnamen kommen vor; der erste gewinnt, der zweite
                # bekommt eine Nummer, statt den ersten zu ueberschreiben.
                if schluessel in eintrag:
                    schluessel = f"{schluessel}_{i + 1}"
                eintrag[schluessel] = wert
            out.append(eintrag)
        return out


@dataclass
class _Rahmen:
    """Der Zustand einer Tabelle. Verschachtelte Tabellen bekommen je einen.

    Ohne eigenen Rahmen ueberschreibt eine Tabelle in einer Zelle die Zeile
    der aeusseren -- und die aeussere Zelle bleibt leer. Genau so kamen
    "Recipes" und "Complex Food" mit null Zeilen zurueck, obwohl ihre Zutaten
    in verschachtelten Tabellen daneben standen.
    """

    tabelle: Tabelle
    zeile: list[str | None] | None = None
    zelle: list[str] | None = None
    ist_kopf: bool = False
    span: list[tuple[int, int, str]] = field(default_factory=list)
    colspan: int = 1
    rowspan: int = 1


def entdoppeln(text: str) -> str:
    """'Bats Bats' -> 'Bats'.

    Eine Zelle wie <a href="/Bats"><img alt="Bats">Bats</a> liefert den Namen
    zweimal: einmal aus dem alt-Attribut, einmal als Linktext. Nur die exakte
    Verdopplung wird zusammengezogen -- ein "5 5" mit zwei echten Werten
    bliebe stehen, wenn es nicht die ganze Zelle ausmacht.
    """
    woerter = text.split()
    n = len(woerter)
    if n >= 2 and n % 2 == 0 and woerter[: n // 2] == woerter[n // 2:]:
        return " ".join(woerter[: n // 2])
    return text


class _TabellenLeser(HTMLParser):
    """Sammelt Tabellen samt Kopfzeilen, Zellen und ausgeschriebenen Spannen."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tabellen: list[Tabelle] = []
        self._rahmen: list[_Rahmen] = []
        self._unterdruecken = 0

    @property
    def _oben(self) -> _Rahmen | None:
        return self._rahmen[-1] if self._rahmen else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "table":
            self._rahmen.append(_Rahmen(Tabelle(css=a.get("class", ""))))
            return
        rahmen = self._oben
        if rahmen is None:
            return
        if tag == "tr":
            rahmen.zeile = []
            for _rest, spalte, wert in rahmen.span:
                while len(rahmen.zeile) <= spalte:
                    rahmen.zeile.append(None)
                rahmen.zeile[spalte] = wert
            rahmen.span = [(r - 1, sp, w) for r, sp, w in rahmen.span if r - 1 > 0]
            rahmen.ist_kopf = False
        elif tag in ("td", "th") and rahmen.zeile is not None:
            rahmen.zelle = []
            rahmen.ist_kopf = rahmen.ist_kopf or tag == "th"
            rahmen.colspan = _zahl(a.get("colspan"), 1)
            rahmen.rowspan = _zahl(a.get("rowspan"), 1)
        elif tag in ("style", "script"):
            self._unterdruecken += 1
        elif tag == "br" and rahmen.zelle is not None:
            rahmen.zelle.append(" ")
        elif tag == "img" and rahmen.zelle is not None:
            # Viele Zellen enthalten nur ein Symbol: die Zutat eines Rezepts,
            # das Produkt eines Gebaeudes. Der Name steht im alt-Attribut.
            beschriftung = (a.get("alt") or a.get("title") or "").strip()
            if beschriftung and not beschriftung.lower().startswith("file:"):
                rahmen.zelle.append(f" {beschriftung} ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._rahmen:
            innen = self._rahmen.pop()
            if innen.zeile is not None:
                self._zeile_abschliessen(innen)
            self.tabellen.append(innen.tabelle)
            aussen = self._oben
            if aussen is not None and aussen.zelle is not None:
                # Die innere Tabelle gehoert in die Zelle, die sie enthaelt.
                aussen.zelle.append(" " + _flach(innen.tabelle) + " ")
            return

        rahmen = self._oben
        if rahmen is None:
            if tag in ("style", "script") and self._unterdruecken:
                self._unterdruecken -= 1
            return

        if tag == "tr" and rahmen.zeile is not None:
            self._zeile_abschliessen(rahmen)
        elif tag in ("td", "th") and rahmen.zelle is not None and rahmen.zeile is not None:
            wert = entdoppeln(LEER.sub(" ", "".join(rahmen.zelle)).strip())
            for _ in range(max(rahmen.colspan, 1)):
                spalte = self._naechste_freie(rahmen)
                rahmen.zeile[spalte] = wert
                if rahmen.rowspan > 1:
                    rahmen.span.append((rahmen.rowspan - 1, spalte, wert))
            rahmen.zelle = None
        elif tag in ("style", "script") and self._unterdruecken:
            self._unterdruecken -= 1

    def handle_data(self, data: str) -> None:
        if self._unterdruecken:
            return
        rahmen = self._oben
        if rahmen is not None and rahmen.zelle is not None:
            rahmen.zelle.append(data)

    @staticmethod
    def _naechste_freie(rahmen: _Rahmen) -> int:
        zeile = rahmen.zeile
        assert zeile is not None
        for i, wert in enumerate(zeile):
            if wert is None:
                return i
        zeile.append(None)
        return len(zeile) - 1

    @staticmethod
    def _zeile_abschliessen(rahmen: _Rahmen) -> None:
        zeile = [w if w is not None else "" for w in (rahmen.zeile or [])]
        if rahmen.ist_kopf and not rahmen.tabelle.kopf:
            rahmen.tabelle.kopf = zeile
        elif any(z.strip() for z in zeile):
            rahmen.tabelle.zeilen.append(zeile)
        rahmen.zeile = None


def _flach(tabelle: Tabelle) -> str:
    """Eine Tabelle als eine Zeile Text, fuer die Zelle, die sie enthaelt."""
    teile: list[str] = []
    for zeile in tabelle.zeilen:
        teile.append(" ".join(z for z in zeile if z))
    return LEER.sub(" ", " ".join(teile)).strip()


def _zahl(wert: str | None, vorgabe: int) -> int:
    try:
        return max(int(str(wert).strip()), 1)
    except (TypeError, ValueError):
        return vorgabe


def tabellen_aus_html(text: str, nur_wikitable: bool = True) -> list[Tabelle]:
    leser = _TabellenLeser()
    leser.feed(text)
    leser.close()
    out = leser.tabellen
    if nur_wikitable:
        gefiltert = [t for t in out if "wikitable" in t.css]
        if gefiltert:
            return gefiltert
    return out


def tabellen_aus_datei(pfad: Path, nur_wikitable: bool = True) -> list[Tabelle]:
    return tabellen_aus_html(
        Path(pfad).read_text(encoding="utf-8", errors="replace"), nur_wikitable)


def html_dateien(wiki_dir: Path) -> list[Path]:
    for muster in ("html/*.html", "*.html", "**/*.html"):
        treffer = sorted(Path(wiki_dir).glob(muster))
        if treffer:
            return treffer
    return []
