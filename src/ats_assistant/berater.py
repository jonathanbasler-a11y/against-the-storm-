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

# Drei Saetze sind ein absichtlich kurzes Ergebnis -- das ist hier der Grund,
# niedrig zu gehen, nicht Sparsamkeit.
MAX_TOKENS = 2000

# Eine Nahrungsfrage braucht kein tiefes Nachdenken, eine Grundsteinwahl
# schon. `output_config.effort`, nicht `budget_tokens` -- das gibt es auf
# Opus 5 nicht mehr und wird mit 400 abgelehnt.
AUFWAND_LAGE = "medium"
AUFWAND_WAHL = "high"

# Der Auszug ist eine Lage, kein Spielstand. Wer darueber liegt, hat etwas
# hineingeraten, das nicht hineingehoert.
MAX_ZEICHEN = 20_000

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

    @property
    def kosten_cent(self) -> float | None:
        """Grobe Schaetzung in Cent, damit niemand raten muss."""
        preise = {"claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0)}
        satz = preise.get(self.modell)
        if satz is None or self.eingabe_token is None or self.ausgabe_token is None:
            return None
        ein, aus = satz
        return round((self.eingabe_token * ein + self.ausgabe_token * aus) / 1e6 * 100, 3)


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
            frage: str | None = None) -> dict:
    """Die kompakte Lage. Zahlen und Namen, sonst nichts."""
    def sauber(quelle: dict | None, felder: tuple[str, ...]) -> dict | None:
        if not quelle:
            return None
        out = {f: quelle[f] for f in felder if quelle.get(f) is not None}
        return out or None

    auszug: dict = {}
    if zustand:
        auszug["siedlung"] = sauber(zustand, (
            "jahr", "jahreszeit", "biom", "prestige", "bevoelkerung", "spezies",
            "feindseligkeit", "ungeduld", "ungeduld_schwelle", "reputation",
            "reputation_ziel", "lager", "gebaeude", "lichtungen", "vorkommen",
            "grundsteine", "spielzeit"))
    if nahrung:
        auszug["nahrung"] = sauber(nahrung, (
            "bestand", "rate_je_spielzeitsekunde", "reichweite_sekunden", "warnung"))
    if ungeduld:
        auszug["ungeduld"] = sauber(ungeduld, (
            "jetzt", "schwelle", "je_spielzeitsekunde", "sekunden_bis_verlust"))
    if auswahl and auswahl.get("angebot"):
        auszug["auswahl"] = [
            {k: v for k, v in eintrag.items()
             if k in ("de", "en", "seltenheit", "wirkung", "guete")}
            for eintrag in auswahl["angebot"]
        ]
    if frage:
        auszug["frage"] = frage
    return auszug


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
    nutzung = getattr(antwort, "usage", None)
    return Antwort(
        text=text or "Keine Antwort erhalten.",
        modell=getattr(antwort, "model", modell),
        eingabe_token=getattr(nutzung, "input_tokens", None),
        ausgabe_token=getattr(nutzung, "output_tokens", None),
        zwischenspeicher_gelesen=getattr(nutzung, "cache_read_input_tokens", None),
    )
