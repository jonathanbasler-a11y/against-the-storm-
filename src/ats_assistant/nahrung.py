"""Was soll ich bauen? -- die Frage, an der SPEC.md haengt.

`food_forecast` sagt, wann die Nahrung leer ist. Das ist die Diagnose. Sie
sagt nicht, was dagegen zu tun waere, und genau daran scheitern die Laeufe:
Nahrungsmangel im ersten Jahr.

Der Hebel steht in den Spieldaten. Rohnahrung saettigt 1,0, verarbeitete 2,0
bis 3,0 -- ein Rezept, das aus 5 roh 10 verarbeitete macht, vervierfacht die
Saettigung des Bestands. Diese Rechnung laesst sich fuer jeden Bestand
durchziehen, und heraus kommt keine Faustregel, sondern eine Zahl: wie viele
Spielzeitsekunden Reichweite ein bestimmtes Gebaeude diesem Lager hinzufuegt.

Kein Modell beteiligt. Was hier steht, ist Arithmetik auf den Rezepten aus
`kb.sqlite` und dem Verbrauch, den die Zeitreihe des Spielstands hergibt.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from .paths import strip_prefixes


@dataclass
class Zutat:
    menge: float
    ware: str
    bestand: float

    @property
    def zyklen(self) -> float:
        return self.bestand / self.menge if self.menge > 0 else 0.0


@dataclass
class Vorschlag:
    """Ein Rezept, gegen den vorhandenen Bestand durchgerechnet."""

    gebaeude: str | None
    produkt: str
    zutaten: list[Zutat]
    zyklen: float                    # wie oft der Bestand das Rezept traegt
    saettigung_rein: float           # was die eingesetzte Rohware saettigen wuerde
    saettigung_raus: float           # was daraus wird
    sterne: int | None
    sekunden: float | None           # Dauer eines Durchlaufs
    engpass: str | None              # die Zutat, die zuerst ausgeht

    gebaeude_de: str | None = None
    produkt_de: str | None = None
    verbrauch: float | None = None   # Saettigung je Spielzeitsekunde
    # Was die Gebaeudeseite behauptet hat. Weicht es von `gebaeude` ab, hat
    # die Produktionstabelle widersprochen -- und die gilt, denn sie fuehrt
    # die Zuordnung ausdruecklich statt aus dem Seitentitel geraten.
    gebaeude_laut_seite: str | None = None

    @property
    def gewinn(self) -> float:
        """Zusaetzliche Saettigung gegenueber dem Rohverzehr."""
        return self.saettigung_raus - self.saettigung_rein

    @property
    def faktor(self) -> float | None:
        if self.saettigung_rein <= 0:
            return None
        return self.saettigung_raus / self.saettigung_rein

    @property
    def dauer(self) -> float | None:
        """Wie lange ein Arbeiter braucht, bis der Bestand durch ist."""
        if self.sekunden is None:
            return None
        return self.sekunden * self.zyklen

    @property
    def reichweite_plus(self) -> float | None:
        """Gewonnene Spielzeitsekunden beim jetzigen Verbrauch."""
        if not self.verbrauch or self.verbrauch <= 0:
            return None
        return self.gewinn / self.verbrauch

    def satz(self) -> str:
        """Ein Satz, wie ihn die Ausgabe der Spec verlangt."""
        name = self.gebaeude_de or self.gebaeude or "?"
        produkt = self.produkt_de or self.produkt
        eingesetzt = ", ".join(
            f"{z.menge * self.zyklen:.0f} {z.ware}" for z in self.zutaten)
        text = (f"{name}: {eingesetzt} werden zu {produkt}, "
                f"{self.gewinn:.0f} Sättigung mehr")
        if self.faktor:
            text += f" (Faktor {self.faktor:.1f})"
        if self.reichweite_plus:
            text += f", rund {self.reichweite_plus / 60:.0f} Minuten Reichweite"
        return text


def _bestand_auf_waren(conn: sqlite3.Connection,
                       bestand: dict[str, float]) -> dict[str, float]:
    """Die Schluessel des Spielstands auf Warennamen bringen.

    Der Spielstand fuehrt "[Food Raw] Meat", die Wissensbasis "Meat". Beide
    Formen werden akzeptiert, und zwar unabhaengig davon, wie viele Praefixe
    gestapelt sind.
    """
    nach_save_id = {
        (r["save_id"] or ""): r["en"]
        for r in conn.execute("SELECT en, save_id FROM resources") if r["save_id"]
    }
    out: dict[str, float] = {}
    for schluessel, menge in (bestand or {}).items():
        if not isinstance(menge, (int, float)):
            continue
        name = nach_save_id.get(schluessel) or strip_prefixes(schluessel)[0]
        out[name] = out.get(name, 0.0) + float(menge)
    return out


def _produktionsgebaeude(conn: sqlite3.Connection) -> dict[str, tuple[str, int | None]]:
    """Produkt -> das Gebaeude mit dem hoechsten Sterngrad.

    Die Rezepte von den Gebaeudeseiten tragen die Mengen, aber ihr Gebaeude
    ist der Seitentitel -- das ergab "Doerrfleisch in der Makellosen
    Schmelzerei". Die Seite "List of Resources" fuehrt die Zuordnung
    ausdruecklich, also gilt sie. Drei Sterne heisst: beste Ausbeute.
    """
    out: dict[str, tuple[str, int | None]] = {}
    try:
        zeilen = conn.execute(
            "SELECT product, building, stars FROM production "
            "ORDER BY stars DESC NULLS LAST, building").fetchall()
    except sqlite3.DatabaseError:
        return out
    for z in zeilen:
        out.setdefault(z["product"], (z["building"], z["stars"]))
    return out


def _deutsch(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        r["en"]: r["de"]
        for r in conn.execute(
            "SELECT en, de FROM name_map WHERE confidence = 'localization'")
        if r["en"]
    }


def vorschlaege(conn: sqlite3.Connection, bestand: dict[str, float],
                verbrauch_pro_sekunde: float | None = None,
                mindestgewinn: float = 1.0) -> list[Vorschlag]:
    """Jedes Rezept gegen den Bestand rechnen, nach Gewinn sortiert.

    `verbrauch_pro_sekunde` kommt aus `food_forecast().rate_per_second` --
    als positive Zahl. Fehlt er, bleibt die Reichweite offen; die Rangfolge
    steht auch ohne ihn.
    """
    saettigung = {
        r["en"]: float(r["eating_fullness"] or 0.0)
        for r in conn.execute(
            "SELECT en, eating_fullness FROM resources WHERE eatable = 1")
    }
    lager = _bestand_auf_waren(conn, bestand)
    namen = _deutsch(conn)
    zustaendig = _produktionsgebaeude(conn)
    verbrauch = abs(verbrauch_pro_sekunde) if verbrauch_pro_sekunde else None

    out: list[Vorschlag] = []
    for r in conn.execute("SELECT * FROM recipes WHERE product IS NOT NULL"):
        je_stueck = saettigung.get(r["product"])
        if not je_stueck:
            continue                      # das Rezept macht keine Nahrung

        zutaten: list[Zutat] = []
        rein_je_zyklus = 0.0
        vollstaendig = True
        for gruppe in json.loads(r["inputs"] or "[]"):
            # Das Spiel laesst die Wahl zwischen den Alternativen einer
            # Zutat. Gewaehlt wird, was da ist -- und darunter das, was roh
            # am wenigsten saettigt: es kostet am wenigsten, es zu verarbeiten.
            moeglich = [z for z in gruppe
                        if lager.get(z["ware"], 0.0) >= z["menge"] > 0]
            if not moeglich:
                vollstaendig = False
                break
            gewaehlt = min(moeglich,
                           key=lambda z: (saettigung.get(z["ware"], 0.0) * z["menge"],
                                          -lager.get(z["ware"], 0.0)))
            zutaten.append(Zutat(float(gewaehlt["menge"]), gewaehlt["ware"],
                                 lager.get(gewaehlt["ware"], 0.0)))
            rein_je_zyklus += saettigung.get(gewaehlt["ware"], 0.0) * gewaehlt["menge"]
        if not vollstaendig or not zutaten:
            continue

        zyklen = min(z.zyklen for z in zutaten)
        if zyklen < 1:
            continue
        engpass = min(zutaten, key=lambda z: z.zyklen).ware
        raus_je_zyklus = je_stueck * float(r["product_amount"] or 1.0)

        belegt, grad = zustaendig.get(r["product"], (None, None))
        gebaeude = belegt or r["building"]
        vorschlag = Vorschlag(
            gebaeude=gebaeude, produkt=r["product"], zutaten=zutaten,
            zyklen=zyklen,
            saettigung_rein=rein_je_zyklus * zyklen,
            saettigung_raus=raus_je_zyklus * zyklen,
            sterne=grad if grad is not None else r["stars"],
            sekunden=r["seconds"], engpass=engpass,
            gebaeude_de=namen.get(gebaeude or ""),
            produkt_de=namen.get(r["product"]), verbrauch=verbrauch,
            gebaeude_laut_seite=(r["building"]
                                 if r["building"] and r["building"] != gebaeude
                                 else None),
        )
        if vorschlag.gewinn >= mindestgewinn:
            out.append(vorschlag)

    # Dasselbe Rezept steht auf mehreren Gebaeudeseiten. Nach der Umstellung
    # auf die Produktionstabelle stuende es sonst mehrfach im Rat.
    einmalig: dict[tuple, Vorschlag] = {}
    for v in out:
        schluessel = (v.produkt, v.gebaeude,
                      tuple((z.menge, z.ware) for z in v.zutaten))
        vorhanden = einmalig.get(schluessel)
        if vorhanden is None or (v.sekunden or 0) < (vorhanden.sekunden or 0):
            einmalig[schluessel] = v
    out = sorted(einmalig.values(),
                 key=lambda v: (-v.gewinn, v.dauer or 0.0, v.produkt))
    return out


@dataclass
class Rat:
    """Ein Vorschlag, eine Begruendung, eine Alternative -- wie in SPEC.md."""

    empfehlung: str
    begruendung: str
    alternative: str
    vorschlaege: list[Vorschlag] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join([self.empfehlung, self.begruendung, self.alternative])


def rat(conn: sqlite3.Connection, bestand: dict[str, float],
        verbrauch_pro_sekunde: float | None = None,
        reichweite_sekunden: float | None = None) -> Rat:
    """Aus den Vorschlaegen die Ausgabe bauen, die die Spec verlangt."""
    liste = vorschlaege(conn, bestand, verbrauch_pro_sekunde)
    if not liste:
        return Rat(
            empfehlung="Kein Verarbeitungsschritt lohnt sich mit diesem Lager.",
            begruendung=("Für kein Nahrungsrezept liegt ein voller Satz Zutaten "
                         "bereit — es fehlt an Rohware, nicht an Verarbeitung."),
            alternative=("Sammellager erweitern oder eine Farm setzen; verarbeiten "
                         "lohnt erst, wenn ein Rezept einen Durchlauf trägt."),
        )

    bester = liste[0]
    zweiter = liste[1] if len(liste) > 1 else None

    empfehlung = bester.satz()
    begruendung = (
        f"Roh verzehrt sättigt der Einsatz {bester.saettigung_rein:.0f}, "
        f"verarbeitet {bester.saettigung_raus:.0f}"
        + (f" — Faktor {bester.faktor:.1f}" if bester.faktor else "")
        + f"; {bester.engpass} geht zuerst aus.")
    if reichweite_sekunden is not None and bester.reichweite_plus:
        begruendung += (f" Das verschiebt das Ende von {reichweite_sekunden / 60:.0f} "
                        f"auf {(reichweite_sekunden + bester.reichweite_plus) / 60:.0f} Minuten.")

    if zweiter is None:
        alternative = ("Keine zweite Kette trägt einen vollen Durchlauf — "
                       "diese ist ohne Alternative.")
    elif bester.dauer and zweiter.dauer and zweiter.dauer < bester.dauer:
        alternative = (
            f"{zweiter.gebaeude_de or zweiter.gebaeude} bringt "
            f"{zweiter.gewinn:.0f} statt {bester.gewinn:.0f} Sättigung, ist aber "
            f"{(bester.dauer - zweiter.dauer) / 60:.0f} Minuten früher fertig — "
            "besser, wenn der Bestand vor der Fertigstellung leer wäre.")
    else:
        alternative = (
            f"{zweiter.gebaeude_de or zweiter.gebaeude} bringt "
            f"{zweiter.gewinn:.0f} Sättigung — besser, wenn "
            f"{bester.engpass} anderswo gebraucht wird.")

    return Rat(empfehlung, begruendung, alternative, liste)
