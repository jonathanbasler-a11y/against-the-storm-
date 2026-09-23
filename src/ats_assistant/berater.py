"""Die Frage an Claude -- Namen und Zahlen, nie ein Bild.

SPEC.md: "Das Sehen passiert lokal und deterministisch, das Urteilen passiert
im Modell." Alles bis hierher ist das Sehen. Dies ist das Urteilen, und es
ist der einzige Teil, der das Netz braucht.

Drei Zusagen:

1. Es geht **nie ein Bild** hinaus, auch nicht aus dem Auswahlhelfer -- nur
   die erkannten Namen. Der Auszug wird vor dem Absenden dagegen geprueft.
2. Ohne Anmeldung laeuft alles andere unveraendert weiter.
3. Der Systemtext kommt aus `.claude/skills/ats-advisor/SKILL.md` -- derselben
   Datei, nach der sich Claude Code richtet. Zwei Saetze Heuristiken, die
   auseinanderdriften, waeren der sichere Weg zu widersprüchlichen Raten.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

MODELL = "claude-opus-5"
MODELLE = ("claude-opus-5", "claude-sonnet-5")

# `max_tokens` deckt Nachdenken und Antwort zusammen. Drei Saetze sind kurz,
# das Nachdenken vor einer Grundsteinwahl nicht: 2000 reichten auf hohem
# Aufwand nicht, und die Antwort kam abgeschnitten oder leer. 16 000 ist die
# uebliche Grenze fuer Anfragen ohne Streaming.
MAX_TOKENS = 16_000

# Eine Nahrungsfrage braucht kein tiefes Nachdenken, eine Grundsteinwahl
# schon. `output_config.effort`, nicht `budget_tokens` -- das gibt es auf
# Opus 5 nicht mehr und wird mit 400 abgelehnt.
AUFWAND_LAGE = "medium"
AUFWAND_WAHL = "high"

# Der Auszug ist eine Lage, kein Spielstand. Wer darueber liegt, hat etwas
# hineingeraten, das nicht hineingehoert.
MAX_ZEICHEN = 40_000

# Lange Listen kappen, bevor sie die Grenze reissen: eine grosse Siedlung
# lag mit 60 Waren und 63 Bauplaenen schon bei 16 700 Zeichen.
LISTENGRENZE = 80
GEBAEUDE_GRENZE = 40

SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "ats-advisor" / "SKILL.md"

# Was niemals hinausgeht. Geprueft wird auf den Schluesseln des Auszugs.
VERBOTEN = ("bild", "screenshot", "image", "png", "jpg", "quelle_bild")


class KeinZugang(RuntimeError):
    """Keine Anmeldung gefunden -- kein Fehler, nur ein fehlender Schlüssel."""


# Ein Satz, zwei Stellen. Er steht hier, damit beide woertlich dasselbe sagen.
HINWEIS_ANMELDUNG = (
    "Keine gültige Anmeldung. Entweder ANTHROPIC_API_KEY setzen "
    "(`setx ANTHROPIC_API_KEY ...`, danach neues Fenster) oder "
    "`ant auth login`.")


def _ist_anmeldefehler(exc: BaseException) -> bool:
    """Ob dieses TypeError in Wahrheit eine fehlende Anmeldung ist.

    Gemessen in anthropic 1.7.0: fuer eine fehlende Anmeldung wirft das SDK
    kein `AuthenticationError`, sondern ein schlichtes `TypeError` aus
    `_validate_headers` -- und zwar beim Bauen der Kopfzeilen, also mitten
    in `messages.create()`. Am Spielrechner stand dessen englischer Rohtext
    im Fenster.

    Absichtlich eng: ein `TypeError` ueber ein falsches Schluesselwort --
    `budget_tokens` ging genau so schon einmal daneben -- muss ein
    `TypeError` bleiben. Als Anmeldeproblem verkleidet waere es nicht zu
    finden.
    """
    if not isinstance(exc, TypeError):
        return False
    text = str(exc).lower()
    return "authentication" in text and "api_key" in text


@dataclass
class Antwort:
    text: str
    modell: str
    eingabe_token: int | None = None
    ausgabe_token: int | None = None
    zwischenspeicher_gelesen: int | None = None
    zwischenspeicher_geschrieben: int | None = None

    @property
    def kosten_cent(self) -> float | None:
        """Grobe Schaetzung in Cent, damit niemand raten muss.

        `input_tokens` zaehlt nur, was nicht aus dem Zwischenspeicher kam.
        Schreiben in den Zwischenspeicher kostet das 1,25-fache, Lesen das
        0,1-fache des Eingabepreises -- beides fehlte in der Schaetzung.
        """
        preise = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0)}
        satz = preise.get(self.modell)
        if satz is None or self.eingabe_token is None or self.ausgabe_token is None:
            return None
        ein, aus = satz
        eingabe = (self.eingabe_token
                   + 0.1 * (self.zwischenspeicher_gelesen or 0)
                   + 1.25 * (self.zwischenspeicher_geschrieben or 0))
        return round((eingabe * ein + self.ausgabe_token * aus) / 1e6 * 100, 3)


def systemtext(pfad: Path | None = None) -> str:
    """Die Beraterregeln, aus derselben Datei wie für Claude Code."""
    pfad = Path(pfad) if pfad else SKILL
    try:
        text = pfad.read_text(encoding="utf-8")
    except OSError:
        log.warning("Beraterregeln nicht lesbar: %s", pfad)
        return ("Du berätst einen Spieler von Against the Storm auf Prestige 13, "
                "deutsche Oberfläche. Eine Empfehlung, ein Satz Begründung, ein "
                "Satz zur besten Alternative.")
    # Der Kopfteil (--- name: ... ---) ist Verwaltung, keine Anweisung.
    if text.startswith("---"):
        _, _, rest = text.partition("---")
        _, _, text = rest.partition("---")
    return text.strip()


def kontext(zustand: dict | None = None, nahrung: dict | None = None,
            ungeduld: dict | None = None, auswahl: dict | None = None,
            frage: str | None = None, ketten: dict | None = None,
            wissen: dict | None = None) -> dict:
    """Die kompakte Lage. Zahlen und Namen, sonst nichts."""
    def sauber(quelle: dict | None, felder: tuple[str, ...]) -> dict | None:
        if not quelle:
            return None
        out = {f: quelle[f] for f in felder if quelle.get(f) is not None}
        return out or None

    auszug: dict = {}
    if zustand:
        zustand = _gekappt(zustand)
        auszug["siedlung"] = sauber(zustand, (
            "jahr", "jahreszeit", "biom", "prestige", "bevoelkerung", "spezies",
            "feindseligkeit", "ungeduld", "ungeduld_schwelle", "reputation",
            # Ohne "vorkommen": gemessen sind das alle Rohstoffknoten der
            # Karte (5760 nach 600 Sekunden), nicht die erreichbaren.
            "reputation_ziel", "lager", "gebaeude", "gebaeude_liste", "lichtungen",
            "bauplaene_ungebaut", "bauplaene_ungebaut_weggelassen",
            "gebaeude_liste_weggelassen", "ruf_quellen", "ruf_je_volk", "auftraege",
            "bauplan_wahl",
            "grundsteine", "spielzeit",
            # Was nicht gelesen werden konnte, geht mit. Sonst sieht ein
            # nicht gefundenes Lager aus wie ein leeres -- und das ist der
            # Unterschied zwischen "nichts da" und "nichts gewusst".
            "nicht_gefunden", "form_unbekannt", "fehlende_dateien"))
    if nahrung:
        auszug["nahrung"] = sauber(nahrung, (
            "bestand", "rate_je_spielzeitsekunde", "reichweite_sekunden", "warnung"))
    if ketten and (ketten.get("ketten") or ketten.get("essbar_im_lager")):
        # Die Rechnung aus dem Reiter „Nahrung". Ohne sie riet der Rat am
        # Spielrechner zu Kueche und Paketen, waehrend die Rechnung den Grill
        # mit Faktor 6 zeigte.
        auszug["nahrung_rat"] = {
            "ketten": [
                {k: kette[k] for k in ("gebaeude", "gebaeude_de", "produkt", "produkt_de",
                                       "einsatz", "gewinn", "faktor", "engpass",
                                       "reichweite_plus_sekunden", "status") if k in kette}
                for kette in (ketten.get("ketten") or [])[:3]],
            "essbar_im_lager": ketten.get("essbar_im_lager") or [],
        }
    if wissen and wissen.get("verfuegbar", True):
        # Was die Spieldaten wissen, statt was das Modell erinnert: Kategorie,
        # essbar, Handelswert je Ware; Erzeugnisse je Gebaeude; Trends.
        if wissen.get("waren"):
            auszug["waren"] = wissen["waren"][:LISTENGRENZE]
            if auszug.get("siedlung"):
                auszug["siedlung"].pop("lager", None)     # steht in `waren`
        if wissen.get("gebaeude"):
            # Stehendes zuerst; ohne den englischen Zwecktext und mit hoechstens
            # vier Erzeugnissen -- sonst riss eine grosse Siedlung die Grenze.
            eintraege = sorted(wissen["gebaeude"].items(),
                               key=lambda kv: kv[1].get("status") != "steht")
            auszug["gebaeude_wissen"] = {
                name: {k: (v[:4] if k == "erzeugnisse" else v)
                       for k, v in eintrag.items() if k != "zweck"}
                for name, eintrag in eintraege[:GEBAEUDE_GRENZE]}
        if wissen.get("trends") and (wissen["trends"].get("fallend")
                                     or wissen["trends"].get("steigend")):
            auszug["trends"] = wissen["trends"]
    if ungeduld:
        auszug["ungeduld"] = sauber(ungeduld, (
            "jetzt", "schwelle", "je_spielzeitsekunde", "sekunden_bis_verlust"))
    if auswahl and auswahl.get("angebot"):
        # Was die Wissensbasis als Angebot kennt, zuerst -- und die
        # Kennzeichnung geht mit. Eine Lesung, die nur auf dem Bildschirm
        # stand, darf nicht als Karte durchgehen.
        auszug["auswahl"] = [
            {k: v for k, v in eintrag.items()
             if k in ("de", "en", "seltenheit", "wirkung", "zweck", "guete", "belegt")}
            for eintrag in auswahl["angebot"]
        ]
    if frage:
        auszug["frage"] = frage
    return auszug


def _gekappt(zustand: dict) -> dict:
    """Was nichts sagt, faellt weg; was zu lang ist, wird gekappt."""
    out = dict(zustand)
    if isinstance(out.get("lager"), dict):
        out["lager"] = {k: v for k, v in out["lager"].items() if v}
    for feld in ("bauplaene_ungebaut", "gebaeude_liste"):
        if isinstance(out.get(feld), list) and len(out[feld]) > LISTENGRENZE:
            # Gekappt, aber gesagt: sonst haelt das Modell die Liste fuer vollstaendig.
            out[f"{feld}_weggelassen"] = len(out[feld]) - LISTENGRENZE
            out[feld] = out[feld][:LISTENGRENZE]
    return out


def pruefe_auszug(auszug: dict) -> None:
    """Sicherstellen, dass kein Bild und kein Pfad mitgeht.

    Das ist keine Formsache. Die Spec verbietet Bilder an das Modell, und
    eine Zusage, die niemand prueft, ist eine Hoffnung.
    """
    text = json.dumps(auszug, ensure_ascii=False, default=str)
    if len(text) > MAX_ZEICHEN:
        raise ValueError(
            f"Der Auszug ist {len(text)} Zeichen gross, erlaubt sind {MAX_ZEICHEN}. "
            "Da ist etwas hineingeraten, das nicht hineingehört.")

    def gehe(wert, pfad: str = "") -> None:
        if isinstance(wert, dict):
            for k, v in wert.items():
                if any(v_ in str(k).lower() for v_ in VERBOTEN):
                    raise ValueError(f"Feld '{pfad}{k}' sieht nach einem Bild aus.")
                gehe(v, f"{pfad}{k}.")
        elif isinstance(wert, list):
            for v in wert:
                gehe(v, pfad)
        elif isinstance(wert, str) and wert.lower().endswith((".png", ".jpg", ".jpeg")):
            raise ValueError(f"Unter '{pfad}' steht ein Bildpfad: {wert[:60]}")

    gehe(auszug)


class _NieZutreffend(Exception):
    """Platzhalter: faengt nichts, weil sie nie geworfen wird."""


def _fehlerklassen():
    """Die vier Fehlerklassen des SDK -- oder Platzhalter.

    Das Modul muss sich einlesen lassen, auch wenn `anthropic` fehlt: alles
    ausser dem einen Reiter laeuft ohne. Eine `except`-Klausel braucht ihre
    Klasse aber zur Laufzeit, also gibt es hier entweder die echten oder
    vier, die nie zutreffen.
    """
    try:
        import anthropic
    except ImportError:
        return (_NieZutreffend,) * 4
    return (anthropic.AuthenticationError, anthropic.RateLimitError,
            anthropic.APIConnectionError, anthropic.APIStatusError)


def anmeldung_gefunden() -> bool | None:
    """Ob eine Anmeldung bereitliegt -- ohne eine einzige Anfrage zu senden.

    `True` ja, `False` nein, `None` nicht feststellbar (kein SDK da).
    Ungeprueftes wird nicht behauptet: ohne das Paket laesst es sich nicht
    sagen, und `False` waere dann eine Behauptung.

    Gemessen in anthropic 1.7.0: das SDK zieht die Anmeldung aus drei
    Quellen -- `api_key`, `auth_token` und dem Zwischenspeicher aus
    `ant auth login`. Genau die drei prueft es beim Bauen der Kopfzeilen.
    Hier dieselbe Frage, nur ohne Netz -- damit das Fenster es sagen kann,
    bevor jemand auf "Fragen" drueckt.
    """
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic()
    except Exception:
        return False
    return any(getattr(client, name, None) is not None
               for name in ("api_key", "auth_token", "_token_cache"))


def _client():
    """Der SDK loest die Anmeldung selbst auf -- Variable, Token oder Profil."""
    try:
        import anthropic
    except ImportError as exc:
        raise KeinZugang(
            "Das Paket `anthropic` fehlt. `pip install anthropic` -- alles "
            "andere im Fenster läuft ohne es weiter.") from exc
    try:
        return anthropic, anthropic.Anthropic()
    except TypeError as exc:
        # Aeltere SDK-Fassungen pruefen schon hier, neuere erst beim Senden.
        if not _ist_anmeldefehler(exc):
            raise
        raise KeinZugang(HINWEIS_ANMELDUNG) from exc


def frage(auszug: dict, modell: str = MODELL, wahl_steht_an: bool = False,
          client=None, regeln: str | None = None) -> Antwort:
    """Die Lage vorlegen und drei Sätze zurückbekommen."""
    pruefe_auszug(auszug)

    if client is None:
        _, client = _client()
    Anmeldung, ZuViel, KeinNetz, Status = _fehlerklassen()

    system = [{
        "type": "text",
        "text": regeln if regeln is not None else systemtext(),
        # Der Systemtext ändert sich nicht zwischen zwei Fragen.
        "cache_control": {"type": "ephemeral"},
    }]
    aufwand = AUFWAND_WAHL if wahl_steht_an else AUFWAND_LAGE

    try:
        antwort = client.messages.create(
            model=modell,
            max_tokens=MAX_TOKENS,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": aufwand},
            messages=[{"role": "user", "content": json.dumps(
                auszug, ensure_ascii=False, indent=1, default=str)}],
        )
    except Anmeldung as exc:
        raise KeinZugang(HINWEIS_ANMELDUNG) from exc
    except TypeError as exc:
        if not _ist_anmeldefehler(exc):
            raise
        raise KeinZugang(HINWEIS_ANMELDUNG) from exc
    except ZuViel as exc:
        wartezeit = getattr(getattr(exc, "response", None), "headers", {})
        sekunden = (wartezeit or {}).get("retry-after", "60")
        raise RuntimeError(f"Zu viele Anfragen. In {sekunden} Sekunden nochmal.") from exc
    except KeinNetz as exc:
        raise RuntimeError(
            "Keine Verbindung. Der Rest des Fensters arbeitet ohne Netz weiter.") from exc
    except Status as exc:
        raise RuntimeError(f"Die API antwortet mit {exc.status_code}: {exc.message}") from exc

    text = "\n".join(b.text for b in antwort.content
                     if getattr(b, "type", None) == "text").strip()
    # Warum die Antwort endete, vor dem Text pruefen: sonst stand eine
    # abgeschnittene Antwort da wie eine fertige, und eine Ablehnung als
    # "Keine Antwort erhalten.".
    grund = getattr(antwort, "stop_reason", None)
    if grund == "refusal":
        text = ("Die Anfrage wurde abgelehnt. Mit anderen Worten nochmal fragen, "
                "oder „Lage kopieren“ und in Claude einfügen.")
    elif grund == "max_tokens":
        text = ((text + " …\n\n") if text else "") + (
            "(Die Antwort wurde abgeschnitten – die Grenze war erreicht. "
            "Nochmal fragen, gern mit einer engeren Frage.)")
    nutzung = getattr(antwort, "usage", None)
    return Antwort(
        text=text or "Keine Antwort erhalten.",
        modell=getattr(antwort, "model", modell),
        eingabe_token=getattr(nutzung, "input_tokens", None),
        ausgabe_token=getattr(nutzung, "output_tokens", None),
        zwischenspeicher_gelesen=getattr(nutzung, "cache_read_input_tokens", None),
        zwischenspeicher_geschrieben=getattr(nutzung, "cache_creation_input_tokens", None),
    )
