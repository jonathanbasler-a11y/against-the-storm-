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
import math
import sqlite3
from dataclasses import dataclass, field

from .paths import strip_prefixes


@dataclass
class Zutat:
    menge: float
    ware: str
    bestand: float
    de: str | None = None        # der Name, den die Oberflaeche anzeigt

    @property
    def name(self) -> str:
        return self.de or self.ware

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
    engpass_de: str | None = None
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
            f"{z.menge * self.zyklen:.0f} {z.name}" for z in self.zutaten)
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


@dataclass
class Rohquelle:
    """Ein Gebaeude, dessen Erzeugnis jemand essen kann."""

    gebaeude: str
    waren: list[str]
    kosten: dict[str, float]
    plaetze: int | None = None
    gebaeude_de: str | None = None
    waren_de: list[str] = field(default_factory=list)

    @property
    def preis(self) -> float:
        return sum(self.kosten.values()) if self.kosten else 0.0

    def satz(self) -> str:
        namen = self.gebaeude_de or self.gebaeude
        waren = ", ".join(self.waren_de or self.waren)
        kosten = " ".join(f"{m:.0f} {w}" for w, m in sorted(self.kosten.items()))
        return f"{namen} ({waren}" + (f", {kosten}" if kosten else "") + ")"


def rohquellen(conn: sqlite3.Connection, grenze: int = 4) -> list[Rohquelle]:
    """Gebaeude, die Essbares liefern -- das Billigste zuerst.

    Die Auskunft "erst Rohware sammeln" sagt nicht, womit. Das steht hier:
    jedes Gebaeude, dessen `products` eine Ware nennt, die `resources` als
    essbar fuehrt. Beides ist gemessen -- `eatable` kommt aus den Spieldaten,
    nicht aus einer Vermutung darueber, was Nahrung ist.

    Nichts wird erfunden: fehlen die Gebaeudeseiten in der Wissensbasis,
    kommt eine leere Liste zurueck, und der Rat sagt dann weniger statt
    falsches.
    """
    try:
        essbar = {r["en"] for r in conn.execute(
            "SELECT en FROM resources WHERE eatable = 1")}
        zeilen = conn.execute(
            "SELECT en, cost, products, worker_slots FROM buildings "
            "WHERE products IS NOT NULL").fetchall()
    except sqlite3.DatabaseError:
        return []
    if not essbar:
        return []

    namen = _deutsch(conn)
    bekannt = sorted(essbar | {r["en"] for r in conn.execute(
        "SELECT en FROM resources")}, key=len, reverse=True)
    out: list[Rohquelle] = []
    for z in zeilen:
        from .kb import zerlege_waren

        # Wiki-Zellen wiederholen den Alt-Text der Symbole: "Meat Meat".
        waren = list(dict.fromkeys(
            w for w in zerlege_waren(z["products"], bekannt) if w in essbar))
        if not waren:
            continue
        try:
            kosten = {k: float(v) for k, v in json.loads(z["cost"] or "{}").items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            kosten = {}
        out.append(Rohquelle(
            gebaeude=z["en"], waren=waren, kosten=kosten,
            plaetze=z["worker_slots"], gebaeude_de=namen.get(z["en"]),
            waren_de=[namen.get(w, w) for w in waren]))
    # Das Billigste zuerst: in Jahr 1 entscheidet, was sofort steht.
    out.sort(key=lambda q: (q.preis or 1e9, q.gebaeude))
    return out[:grenze]


def essbar_im_lager(conn: sqlite3.Connection, bestand: dict[str, float]) -> list[dict]:
    """Was im Lager essbar ist, mit Saettigung je Stueck -- meiste zuerst."""
    saettigung = {
        r["en"]: float(r["eating_fullness"] or 0.0)
        for r in conn.execute(
            "SELECT en, eating_fullness FROM resources WHERE eatable = 1")
    }
    namen = _deutsch(conn)
    out = [{"ware": ware, "ware_de": namen.get(ware, ware), "menge": menge,
            "saettigung": saettigung[ware]}
           for ware, menge in _bestand_auf_waren(conn, bestand).items()
           if ware in saettigung and menge > 0]
    return sorted(out, key=lambda e: -e["menge"])


def _deutsch(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        r["en"]: r["de"]
        for r in conn.execute(
            "SELECT en, de FROM name_map WHERE confidence = 'localization'")
        if r["en"]
    }


def vorschlaege(conn: sqlite3.Connection, bestand: dict[str, float],
                verbrauch_pro_sekunde: float | None = None,
                mindestgewinn: float = 1.0,
                nur_belegt: bool = True,
                huerden: list[dict] | None = None) -> list[Vorschlag]:
    """Jedes Rezept gegen den Bestand rechnen, nach Gewinn sortiert.

    `verbrauch_pro_sekunde` kommt aus `food_forecast().rate_per_second` --
    als positive Zahl. Fehlt er, bleibt die Reichweite offen; die Rangfolge
    steht auch ohne ihn.

    `nur_belegt` laesst nur Erzeugnisse zu, die die Produktionstabelle
    kennt. Das ist keine Vorsicht, sondern eine Sortierung nach Art: die
    Tabelle fuehrt genau die verarbeiteten Waren, und nur um deren
    Herstellung geht es hier. Was von den Gebaeudeseiten kam und dort
    fehlt, sind Rohnahrung -- Fleisch, Fisch, Eier -- und die kommt aus
    Lagern und Vorkommen, nicht aus einem Rezept. Ein "Rezept", das aus
    3 Fleisch 30 Fleisch macht, ist ein Lesefehler und kein Rat.
    """
    saettigung = {
        r["en"]: float(r["eating_fullness"] or 0.0)
        for r in conn.execute(
            "SELECT en, eating_fullness FROM resources WHERE eatable = 1")
    }
    lager = _bestand_auf_waren(conn, bestand)
    namen = _deutsch(conn)
    zustaendig = _produktionsgebaeude(conn)
    # Die Rate kommt mit Vorzeichen aus der Vorhersage. Nur ein fallender
    # Bestand ist Verbrauch; `abs()` machte aus einem wachsenden einen.
    verbrauch = (-verbrauch_pro_sekunde
                 if verbrauch_pro_sekunde is not None and verbrauch_pro_sekunde < 0
                 else None)

    out: list[Vorschlag] = []
    gescheitert: list[dict] = []
    for r in conn.execute("SELECT * FROM recipes WHERE product IS NOT NULL"):
        je_stueck = saettigung.get(r["product"])
        if not je_stueck:
            continue                      # das Rezept macht keine Nahrung
        if nur_belegt and r["product"] not in zustaendig:
            continue

        zutaten: list[Zutat] = []
        rein_je_zyklus = 0.0
        vollstaendig = True
        # Was fruehere Gruppen schon je Durchlauf beanspruchen. Dieselbe Ware
        # in zwei Gruppen wurde sonst doppelt gezaehlt.
        bedarf: dict[str, float] = {}
        for gruppe in json.loads(r["inputs"] or "[]"):
            # Das Spiel laesst die Wahl zwischen den Alternativen einer
            # Zutat. Gewaehlt wird, was die meisten Durchlaeufe traegt, und
            # bei Gleichstand, was roh am wenigsten saettigt. Vorher gewann
            # das Billigste fuer einen Durchlauf: am Spielrechner standen so
            # "2 Insekten, 3 Eier" im Rat, waehrend Fleisch fuer zwanzig
            # Durchlaeufe im Lager lag.
            def durchlaeufe(z: dict, bedarf: dict = bedarf) -> float:
                return lager.get(z["ware"], 0.0) / (bedarf.get(z["ware"], 0.0) + z["menge"])

            moeglich = [z for z in gruppe
                        if z.get("menge", 0) > 0 and durchlaeufe(z) >= 1]
            if not moeglich:
                # Woran es scheitert, ist die eigentliche Auskunft: "lohnt
                # sich nicht" schickt den Spieler in dieselbe Sackgasse
                # zurueck, "es fehlt der Brennstoff" nicht.
                gescheitert.append({
                    "produkt": r["product"],
                    "fehlt": [z["ware"] for z in gruppe if z.get("ware")],
                    "menge": min((z["menge"] for z in gruppe if z.get("menge")),
                                 default=None),
                })
                vollstaendig = False
                break
            gewaehlt = max(moeglich,
                           key=lambda z: (math.floor(durchlaeufe(z)),
                                          -saettigung.get(z["ware"], 0.0) * z["menge"]))
            bedarf[gewaehlt["ware"]] = bedarf.get(gewaehlt["ware"], 0.0) + gewaehlt["menge"]
            zutaten.append(Zutat(float(gewaehlt["menge"]), gewaehlt["ware"],
                                 lager.get(gewaehlt["ware"], 0.0),
                                 namen.get(gewaehlt["ware"])))
            rein_je_zyklus += saettigung.get(gewaehlt["ware"], 0.0) * gewaehlt["menge"]
        if not vollstaendig or not zutaten:
            continue

        if any(z.ware == r["product"] for z in zutaten):
            # Aus Fleisch wird kein Fleisch. Solche Zeilen entstehen, wenn
            # die Gebaeudeseite eine Zutatenliste als Rezept fuehrt.
            continue
        # Nur ganze Durchlaeufe: 7 Fleisch sind einer zu 5, nicht 1,4.
        tragweite = {ware: lager.get(ware, 0.0) / menge for ware, menge in bedarf.items()}
        zyklen = float(math.floor(min(tragweite.values())))
        if zyklen < 1:
            continue
        engpass = min(tragweite, key=tragweite.get)
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
            produkt_de=namen.get(r["product"]), engpass_de=namen.get(engpass),
            verbrauch=verbrauch,
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
        # Das ergiebigere Rezept bleibt; bei gleichem Gewinn das schnellere,
        # und eine unbekannte Dauer schlaegt keine bekannte.
        if vorhanden is None or _besser(v, vorhanden):
            einmalig[schluessel] = v
    out = sorted(einmalig.values(),
                 key=lambda v: (-v.gewinn, v.dauer if v.dauer is not None else math.inf,
                                v.produkt))
    if huerden is not None:
        # Nur die knappsten: wer zwanzig Rezepte aufzaehlt, sagt nichts.
        gesehen: set[str] = set()
        for e in sorted(gescheitert, key=lambda e: len(e["fehlt"])):
            if e["produkt"] in gesehen:
                continue
            gesehen.add(e["produkt"])
            huerden.append(e)
    return out


def _besser(neu: Vorschlag, alt: Vorschlag) -> bool:
    if neu.gewinn != alt.gewinn:
        return neu.gewinn > alt.gewinn
    a = neu.sekunden if neu.sekunden is not None else math.inf
    b = alt.sekunden if alt.sekunden is not None else math.inf
    return a < b


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
    if not bestand:
        # Leer gelesen heisst nicht leer. Am 22.09.2026 kam `lager: {}` aus
        # einem Spielstand mit vollem Lagerhaus -- und die Auskunft "kein
        # Verarbeitungsschritt lohnt sich" war dann eine Aussage ueber ein
        # leeres Dictionary, nicht ueber die Siedlung. Der Unterschied
        # gehoert hingeschrieben.
        return Rat(
            empfehlung="Der Lagerbestand kam leer aus dem Spielstand.",
            begruendung=("Entweder ist das Lager wirklich leer, oder die Stelle "
                         "im Spielstand wurde nicht gefunden. Gerechnet werden "
                         "kann auf beidem nicht."),
            alternative=("`python tools/lage.py` zeigt unter „nicht "
                         "gefunden“, welche Felder fehlen; `python "
                         "tools/kb_probe.py --dump-ids` zeigt, wie die "
                         "Warenschluessel in diesem Spielstand heissen."),
        )

    huerden: list[dict] = []
    liste = vorschlaege(conn, bestand, verbrauch_pro_sekunde, huerden=huerden)
    if not liste:
        namen = _deutsch(conn)

        def deutsch(ware: str) -> str:
            return namen.get(ware, ware)

        if huerden:
            naechste = huerden[0]
            fehlt = " oder ".join(deutsch(w) for w in naechste["fehlt"][:5])
            produkt = deutsch(naechste["produkt"])
            menge = f"{naechste['menge']:.0f} " if naechste.get("menge") else ""
            begruendung = (f"{produkt} scheitert an einer Zutat: es fehlt "
                           f"{menge}{fehlt} im Lager.")
            weitere = {deutsch(h["produkt"]) for h in huerden[1:4]}
            alternative = (
                f"Dasselbe gilt für {', '.join(sorted(weitere))} — "
                "erst Rohware sammeln, dann verarbeiten."
                if weitere else
                "Erst die fehlende Zutat beschaffen, dann trägt die Kette.")
        else:
            begruendung = ("Für kein Nahrungsrezept liegt ein voller Satz Zutaten "
                           "bereit — es fehlt an Rohware, nicht an Verarbeitung.")
            alternative = ("Sammellager erweitern oder eine Farm setzen; verarbeiten "
                           "lohnt erst, wenn ein Rezept einen Durchlauf trägt.")

        # "Erst Rohware sammeln" sagt nicht, womit. Das steht in der
        # Wissensbasis -- und wenn nicht, wird nichts erfunden.
        quellen = rohquellen(conn)
        if quellen:
            alternative += (" Rohnahrung liefern: "
                            + "; ".join(q.satz() for q in quellen[:3]) + ".")
        return Rat(
            empfehlung="Kein Verarbeitungsschritt lohnt sich mit diesem Lager.",
            begruendung=begruendung, alternative=alternative,
        )

    bester = liste[0]
    zweiter = liste[1] if len(liste) > 1 else None

    empfehlung = bester.satz()
    begruendung = (
        f"Roh verzehrt sättigt der Einsatz {bester.saettigung_rein:.0f}, "
        f"verarbeitet {bester.saettigung_raus:.0f}"
        + (f" — Faktor {bester.faktor:.1f}" if bester.faktor else "")
        + f"; {bester.engpass_de or bester.engpass} geht zuerst aus.")
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
            f"{bester.engpass_de or bester.engpass} anderswo gebraucht wird.")

    return Rat(empfehlung, begruendung, alternative, liste)
