"""Der Arbeits-Thread hinter dem Fenster -- ohne ein einziges Widget.

Getrennt, weil es zwei verschiedene Dinge sind: welches Werkzeug wann
gerufen wird, und wie das Ergebnis aussieht. Die Trennung hat einen
praktischen Grund -- so laesst sich der Teil pruefen, der entscheidet, auch
wo kein tkinter installiert ist. Ein ungeprueftes Stueck an genau dieser
Stelle war in diesem Projekt schon zweimal der Fehler.

Tkinter ist nicht threadsicher. Deshalb fasst dieser Thread nie ein Widget
an: er legt (art, wert) in eine Warteschlange, und der UI-Thread holt es ab.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import berater, tools_api
from .mcp_server import lage as umgebungslage
from .watcher import _signatur

log = logging.getLogger(__name__)

TAKT_SEKUNDEN = 3.0          # wie oft nach einem neuen Spielstand gesehen wird
ABHOLEN_MS = 150             # wie oft der UI-Thread die Warteschlange leert


def minuten(sekunden: float | None) -> str:
    if sekunden is None:
        return "–"
    if sekunden < 60:
        return f"{sekunden:.0f} s"
    return f"{sekunden / 60:.0f} min"


def feindseligkeit(wert) -> str:
    """Die Feindseligkeit als Satz -- nie als Dictionary.

    Gemessen im laufenden Spiel: `{"level": 3, "points": 72, "sources": {...}}`.
    Die Testvorlage dieses Projekts hatte `{"current": 180}` -- erfunden, nicht
    gemessen, und deshalb stand am Spielrechner das rohe Dictionary im Fenster,
    rechts abgeschnitten. Beide Formen werden gelesen; was keine ist, wird zur
    Zeichenkette, aber nie zu geschweiften Klammern.
    """
    if wert is None:
        return "–"
    if not isinstance(wert, dict):
        return str(wert)
    stufe = wert.get("level")
    punkte = wert.get("points", wert.get("current"))
    teile = []
    if stufe is not None:
        teile.append(f"Stufe {stufe}")
    if punkte is not None:
        teile.append(f"{punkte:g} Punkte" if isinstance(punkte, (int, float))
                     else f"{punkte} Punkte")
    return " · ".join(teile) or "–"


def alter(zeitpunkt: str | None, wort: str = "gelesen") -> str:
    """Wie alt die Zahlen sind. Ohne das wird aus einem fünf Minuten alten
    Bestand eine Behauptung über jetzt."""
    if not zeitpunkt:
        return "unbekannt"
    try:
        gelesen = datetime.fromisoformat(zeitpunkt)
    except ValueError:
        return zeitpunkt
    sekunden = (datetime.now(gelesen.tzinfo) - gelesen).total_seconds()
    if sekunden < 90:
        return "gerade eben"
    if sekunden < 5400:
        return f"vor {sekunden / 60:.0f} min {wort}"
    return f"vor {sekunden / 3600:.0f} h {wort}"


# --------------------------------------------------------------------------
# Der Arbeits-Thread
# --------------------------------------------------------------------------


@dataclass
class Auftrag:
    art: str
    daten: dict = field(default_factory=dict)


class Rechner(threading.Thread):
    """Rechnet, wenn sich der Spielstand ändert oder jemand fragt.

    Jedes Ergebnis geht als (art, wert) in die Warteschlange. Ausnahmen
    landen als ("fehler", text) dort -- ein toter Arbeits-Thread wäre eine
    Oberfläche, die stehenbleibt, ohne zu sagen warum.
    """

    def __init__(self, save_dir: Path, runs_dir: Path, db: Path,
                 ausgang: queue.Queue) -> None:
        super().__init__(daemon=True, name="ats-rechner")
        self.save_dir = save_dir
        self.runs_dir = runs_dir
        self.db = db
        self.ausgang = ausgang
        self.eingang: queue.Queue[Auftrag] = queue.Queue()
        self._ende = threading.Event()
        self._signatur = None

    def stoppen(self) -> None:
        self._ende.set()

    def bitte(self, art: str, **daten) -> None:
        self.eingang.put(Auftrag(art, daten))

    def _anfangen(self) -> None:
        # Die Signatur gleich merken: sonst sah `_nachsehen` drei Sekunden
        # spaeter eine "neue" (von None aus) und las ein zweites Mal.
        try:
            self._signatur = _signatur(self.save_dir)
        except Exception:
            pass
        self.bitte("lage")

    def run(self) -> None:
        self._anfangen()
        while not self._ende.is_set():
            try:
                auftrag = self.eingang.get(timeout=TAKT_SEKUNDEN)
            except queue.Empty:
                self._nachsehen()
                continue
            try:
                self._ausfuehren(auftrag)
            except Exception as exc:                  # nie sterben
                log.exception("Auftrag %s gescheitert", auftrag.art)
                self.ausgang.put(("fehler", f"{type(exc).__name__}: {exc}"))

    def _nachsehen(self) -> None:
        """Hat das Spiel geschrieben?"""
        try:
            jetzt = _signatur(self.save_dir)
        except Exception:
            return
        if jetzt != self._signatur:
            self._signatur = jetzt
            self.bitte("lage")

    def _ausfuehren(self, auftrag: Auftrag) -> None:
        if auftrag.art == "lage":
            zustand = tools_api.get_state(self.save_dir, self.runs_dir)
            self.ausgang.put(("zustand", zustand))
            self.ausgang.put(("nahrung", tools_api.food_forecast(self.runs_dir)))
            self.ausgang.put(("ungeduld", tools_api.impatience_forecast(self.runs_dir)))
            self.ausgang.put(("ketten", tools_api.food_advice(self.runs_dir, self.db)))
            self.ausgang.put(("umgebung", umgebungslage(self.save_dir, self.runs_dir, self.db)))
            # Ob der Reiter "Rat" ueberhaupt fragen kann -- gepruft, bevor
            # jemand fragt. Kostet keine Anfrage, nur einen Blick.
            self.ausgang.put(("anmeldung", berater.anmeldung_gefunden()))
        elif auftrag.art == "auswahl":
            # Das Foto macht das Fenster selbst, im Hauptthread, solange es
            # versteckt ist. Hier wird nur noch gelesen.
            bild = auftrag.daten.get("bild")
            text = auftrag.daten.get("text")
            self.ausgang.put(("auswahl", tools_api.read_choice(
                bild=bild, db=self.db, arten=auftrag.daten.get("arten", ("effect",)),
                text=text, aufnehmen=not text and not bild)))
        elif auftrag.art == "nachschlag":
            self.ausgang.put(("nachschlag", tools_api.query_kb(
                auftrag.daten["name"], db=self.db)))
        elif auftrag.art == "rat":
            self.ausgang.put(("rat", self._rat(auftrag.daten)))

    def _rat(self, daten: dict) -> dict:
        auszug = berater.kontext(
            zustand=daten.get("zustand"), nahrung=daten.get("nahrung"),
            ungeduld=daten.get("ungeduld"), auswahl=daten.get("auswahl"),
            frage=daten.get("frage"), ketten=daten.get("ketten"))
        try:
            antwort = berater.frage(
                auszug, modell=daten.get("modell", berater.MODELL),
                wahl_steht_an=bool((daten.get("auswahl") or {}).get("angebot")))
        except berater.KeinZugang as exc:
            return {"ok": False, "text": str(exc), "auszug": auszug, "zugang": False}
        except Exception as exc:
            return {"ok": False, "text": str(exc), "auszug": auszug, "zugang": True}
        kosten = antwort.kosten_cent
        fuss = f"{antwort.modell}"
        if kosten is not None:
            fuss += f", rund {kosten:.1f} Cent"
        if antwort.zwischenspeicher_gelesen:
            fuss += f", {antwort.zwischenspeicher_gelesen} Token aus dem Zwischenspeicher"
        return {"ok": True, "text": antwort.text, "fuss": fuss, "auszug": auszug}
