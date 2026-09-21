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


class _TabellenLeser(HTMLParser):
    """Sammelt Tabellen samt Kopfzeilen, Zellen und ausgeschriebenen Spannen.

    rowspan und colspan kommen in diesen Tabellen vor ("rowspan=2 | Amber
    value"). Wer sie ignoriert, bekommt verrutschte Spalten -- deshalb werden
    sie ausgeschrieben, statt sie wegzulassen.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tabellen: list[Tabelle] = []
        self._stapel: list[Tabelle] = []
        self._zeile: list[str | None] | None = None
        self._zelle: list[str] | None = None
        self._ist_kopf = False
        self._span: list[tuple[int, int, str]] = []   # (Restzeilen, Spalte, Wert)
        self._colspan = 1
        self._rowspan = 1
        self._unterdruecken = 0

    # -- Tabellen ---------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "table":
            self._stapel.append(Tabelle(css=a.get("class", "")))
        elif tag == "tr" and self._stapel:
            # Offene rowspans belegen ihre Spalte, BEVOR die eigenen Zellen
            # einsortiert werden. Wer sie hinterher einsetzt, findet die
            # Spalte besetzt und verschiebt die ganze Zeile.
            self._zeile = []
            for rest, spalte, wert in self._span:
                while len(self._zeile) <= spalte:
                    self._zeile.append(None)
                self._zeile[spalte] = wert
            self._span = [(rest - 1, spalte, wert) for rest, spalte, wert in self._span
                          if rest - 1 > 0]
            self._ist_kopf = False
        elif tag in ("td", "th") and self._zeile is not None:
            self._zelle = []
            self._ist_kopf = self._ist_kopf or tag == "th"
            self._colspan = _zahl(a.get("colspan"), 1)
            self._rowspan = _zahl(a.get("rowspan"), 1)
        elif tag in ("style", "script"):
            self._unterdruecken += 1
        elif tag == "br" and self._zelle is not None:
            self._zelle.append(" ")
        elif tag == "img" and self._zelle is not None:
            # Viele Zellen des Wikis enthalten nur ein Symbol: die Zutat eines
            # Rezepts, das Produkt eines Gebaeudes. Der Name steht dann im
            # alt- oder title-Attribut. Wer nur Text sammelt, haelt solche
            # Tabellen fuer leer -- "Complex Food" und "Recipes" kamen so mit
            # null Zeilen zurueck, obwohl sie gefuellt sind.
            beschriftung = (a.get("alt") or a.get("title") or "").strip()
            if beschriftung and not beschriftung.lower().startswith("file:"):
                self._zelle.append(f" {beschriftung} ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._stapel:
            fertig = self._stapel.pop()
            self.tabellen.append(fertig)
        elif tag == "tr" and self._zeile is not None and self._stapel:
            self._zeile_abschliessen()
        elif tag in ("td", "th") and self._zelle is not None and self._zeile is not None:
            wert = LEER.sub(" ", "".join(self._zelle)).strip()
            for _ in range(max(self._colspan, 1)):
                spalte = self._naechste_freie()
                self._zeile[spalte] = wert
                if self._rowspan > 1:
                    self._span.append((self._rowspan - 1, spalte, wert))
            self._zelle = None
        elif tag in ("style", "script") and self._unterdruecken:
            self._unterdruecken -= 1

    def handle_data(self, data: str) -> None:
        if self._unterdruecken:
            return
        if self._zelle is not None:
            self._zelle.append(data)

    def _naechste_freie(self) -> int:
        """Erste Spalte, die weder von einer Zelle noch von einem rowspan belegt ist."""
        zeile = self._zeile
        assert zeile is not None
        for i, wert in enumerate(zeile):
            if wert is None:
                return i
        zeile.append(None)
        return len(zeile) - 1

    def _zeile_abschliessen(self) -> None:
        tabelle = self._stapel[-1]
        zeile = [w if w is not None else "" for w in (self._zeile or [])]

        if self._ist_kopf and not tabelle.kopf:
            tabelle.kopf = zeile
        else:
            tabelle.zeilen.append(zeile)
        self._zeile = None


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
