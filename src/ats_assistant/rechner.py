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

from . import aktualisieren, berater, lernen, save_reader, tools_api
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


def statistik_satz(statistik: dict | None, lichtungen: int | None = None) -> str:
    """Hunger, Gegangene, Tote, Lichtungen in einer Zeile -- was fuer das
    Scheitern zaehlt, aus dem Reiter „Stadtstatistiken“."""
    statistik = statistik or {}
    teile = []
    if statistik.get("hunger") is not None:
        teile.append(f"Hunger {statistik['hunger']}×")
    if statistik.get("gegangen") is not None:
        teile.append(f"{statistik['gegangen']} gegangen")
    if statistik.get("tot") is not None:
        teile.append(f"{statistik['tot']} tot")
    if lichtungen is not None:
        teile.append(f"{lichtungen} Lichtungen")
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


def erster_satz(text: str, hoechstens: int = 300) -> str:
    """Der erste Satz einer Antwort -- die Empfehlung, ohne Begründung."""
    text = " ".join(text.split())
    for i, zeichen in enumerate(text):
        if zeichen in ".!?" and (i + 1 == len(text) or text[i + 1] == " "):
            return text[:i + 1][:hoechstens]
    return text[:hoechstens]


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
            if zustand.get("verfuegbar") is not False:
                # Nur mit Spielstand, und aus *seiner* Mitschrift: sonst kamen
                # Nahrung und Ungeduld der letzten Siedlung und fuellten die
                # gerade geleerten Felder wieder.
                lauf = zustand.get("mitschrift")
                self.ausgang.put(("nahrung", tools_api.food_forecast(self.runs_dir, lauf)))
                self.ausgang.put(("ungeduld", tools_api.impatience_forecast(self.runs_dir, lauf)))
                self.ausgang.put(("ketten", tools_api.food_advice(self.runs_dir, self.db, lauf)))
                self.ausgang.put(("wissen", tools_api.lage_wissen(self.runs_dir, self.db, lauf)))
            self.ausgang.put(("umgebung", umgebungslage(self.save_dir, self.runs_dir, self.db)))
            # Ob der Reiter "Rat" ueberhaupt fragen kann -- gepruft, bevor
            # jemand fragt. Kostet keine Anfrage, nur einen Blick.
            self.ausgang.put(("anmeldung", berater.anmeldung_gefunden()))
        elif auftrag.art == "auswahl":
            # Das Foto macht das Fenster selbst, in einem eigenen Faden,
            # solange es versteckt ist. Hier wird nur noch gelesen.
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
        elif auftrag.art == "korrektur":
            self.ausgang.put(("korrektur", lernen.korrektur_merken(
                self._korrekturpfad(), auftrag.daten.get("aussage") or "",
                auftrag.daten.get("korrektur") or "")))
        elif auftrag.art == "aktualisieren":
            # Im Arbeits-Thread: git spricht mit dem Netz, das Fenster soll
            # dabei nicht einfrieren.
            self.ausgang.put(("aktualisiert", aktualisieren.aktualisieren()))
        elif auftrag.art == "laeufe":
            berichte = lernen.berichte(self.runs_dir, self._historie())
            self.ausgang.put(("laeufe", {"berichte": berichte,
                                         "lehren": lernen.lehren(berichte)}))

    def _korrekturpfad(self) -> Path:
        return lernen.wissensordner(self.runs_dir) / "korrekturen.jsonl"

    def _historie(self) -> list[dict]:
        """Die Spielhistorie aus MetaSave.save -- leer, wenn es sie nicht gibt."""
        pfad = Path(self.save_dir) / "MetaSave.save"
        if not pfad.exists():
            return []
        meta = save_reader._load(pfad)
        if not isinstance(meta, dict):
            return []
        records = (meta.get("gamesHistory") or {}).get("records")
        return records if isinstance(records, list) else []

    def _gelerntes(self) -> dict:
        """Was der Rat aus frueheren Laeufen und Korrekturen mitbekommt.

        Scheitert hier etwas, fragt der Rat trotzdem -- nur ohne das Gelernte.
        """
        out: dict = {}
        try:
            out["korrekturen"] = lernen.korrekturen(self._korrekturpfad())
            out["lehren"] = lernen.lehren(lernen.berichte(self.runs_dir, self._historie()))
            historie = tools_api.analyze_runs(save_dir=self.save_dir, runs_dir=self.runs_dir)
            if historie.get("verfuegbar"):
                out["laufhistorie"] = historie.get("kurzfassung")
        except Exception:
            log.exception("Gelerntes nicht gelesen")
        return {k: v for k, v in out.items() if v}

    def _merken(self, daten: dict, text: str) -> None:
        """Die Empfehlung als Notiz in die Mitschrift -- das Gedächtnis des Rats."""
        zustand = daten.get("zustand") or {}
        lauf = zustand.get("mitschrift")
        if not lauf or not text:
            return
        satz = erster_satz(text)
        if daten.get("automatisch"):
            satz += " (automatisch zur Bauplanwahl)"
        elif daten.get("frage"):
            satz += f" (Frage: {str(daten['frage'])[:200]})"
        try:
            tools_api.log_event(satz, self.runs_dir, run_id=lauf, art="rat",
                                spielzeit=zustand.get("spielzeit"), jahr=zustand.get("jahr"))
        except Exception:
            log.exception("Empfehlung nicht notiert")

    def _rat(self, daten: dict) -> dict:
        auszug = berater.kontext(
            zustand=daten.get("zustand"), nahrung=daten.get("nahrung"),
            ungeduld=daten.get("ungeduld"), auswahl=daten.get("auswahl"),
            frage=daten.get("frage"), ketten=daten.get("ketten"),
            wissen=daten.get("wissen"), lernen=self._gelerntes())
        try:
            antwort = berater.frage(
                auszug, modell=daten.get("modell", berater.MODELL),
                # Selbst nachsehen statt raten -- lokal, nur Namen und Zahlen.
                nachschlagen=lambda name: tools_api.query_kb(name, db=self.db),
                # Eine offene Bauplanwahl aus dem Spielstand ist eine Wahl,
                # auch ohne Bildschirmlesung.
                wahl_steht_an=bool((daten.get("auswahl") or {}).get("angebot")
                                   or (daten.get("zustand") or {}).get("bauplan_wahl")))
        except berater.KeinZugang as exc:
            return {"ok": False, "text": str(exc), "auszug": auszug, "zugang": False}
        except Exception as exc:
            return {"ok": False, "text": str(exc), "auszug": auszug, "zugang": True}
        self._merken(daten, antwort.text)
        kosten = antwort.kosten_cent
        fuss = f"{antwort.modell}"
        if daten.get("automatisch"):
            fuss = f"automatisch zur Bauplanwahl · {fuss}"
        if kosten is not None:
            fuss += f", rund {kosten:.1f} Cent"
        if antwort.runden > 1:
            fuss += f", {antwort.runden - 1}× nachgeschlagen"
        if antwort.zwischenspeicher_gelesen:
            fuss += f", {antwort.zwischenspeicher_gelesen} Token aus dem Zwischenspeicher"
        return {"ok": True, "text": antwort.text, "fuss": fuss, "auszug": auszug}
