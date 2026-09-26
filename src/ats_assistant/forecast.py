"""Reine Arithmetik: Nahrungs- und Ungeduldsvorhersage. Kein Modell beteiligt.

Beide Modelle stammen aus Messungen an echten Spielstaenden (Phase 0,
dokumentiert in docs/PHASE0.md), nicht aus dem Wiki und nicht aus der
beigelegten Recherche.

**Ungeduld.** Ueber drei Messintervalle auf vier Tausendstel genau:

    Ungeduld += reputationPenaltyPerSec * (1 + reputationPenaltyBonusRate) * dt
    Ungeduld -= 1,0 je UEBERSCHRITTENEM ganzen Reputationspunkt

Der zweite Teil ist der wichtige: die Gutschrift kommt je vollem Punkt, nicht
anteilig. Anteilig gerechnet ergibt sich kein konstanter Faktor.

**Nahrung.** Der Spielstand fuehrt je Warenkategorie eine Zeitreihe mit 180
Stuetzstellen im Abstand von rund 10 Spielzeitsekunden -- eine halbe Stunde
Vorgeschichte. Die Reihe ist ein Ringpuffer: der Schreibzeiger wandert mitten
durch das Feld. Welche Stellen frisch sind, verraet der Vergleich zweier
aufeinanderfolgender Spielstaende, und genau daraus kommt die Steigung.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Gemessen: 10,3 / 10,0 / 9,7 Spielzeitsekunden je Stuetzstelle.
SAMPLE_SECONDS = 10.0

# Gemessen: Autosave etwa alle 300 Spielzeitsekunden. So alt kann der
# Bestandswert hoechstens sein, wenn nichts dazwischen gespeichert wurde.
SAVE_INTERVAL_SECONDS = 300.0


@dataclass
class FoodForecast:
    stock: float | None
    rate_per_second: float | None      # negativ heisst: Bestand schrumpft
    runway_seconds: float | None       # bis leer, None wenn der Bestand waechst
    samples_used: int
    warning: str | None


@dataclass
class ImpatienceForecast:
    current: float | None
    per_second: float | None
    threshold: float | None
    seconds_until_loss: float | None
    projected: float | None
    warning: str | None


# --------------------------------------------------------------------------
# Ungeduld
# --------------------------------------------------------------------------


def impatience_rate(per_second: float | None, bonus_rate: float | None) -> float | None:
    """Zuwachs je Spielzeitsekunde, Bonusrate eingerechnet."""
    if per_second is None:
        return None
    return per_second * (1.0 + (bonus_rate or 0.0))


def project_impatience(
    impatience: float,
    per_second: float,
    bonus_rate: float | None,
    seconds: float,
    reputation_from: float = 0.0,
    reputation_to: float | None = None,
) -> float:
    """Ungeduld nach `seconds`, optional mit erwartetem Reputationszuwachs.

    Die Gutschrift zaehlt ueberschrittene GANZE Reputationspunkte -- von 13,6
    auf 14,6 ist ein Punkt, von 13,0 auf 13,6 keiner.
    """
    rate = impatience_rate(per_second, bonus_rate) or 0.0
    value = impatience + rate * seconds
    if reputation_to is not None:
        points = math.floor(reputation_to) - math.floor(reputation_from)
        value -= 1.0 * max(points, 0)
    return value


def impatience_forecast(state, seconds_ahead: float = SAVE_INTERVAL_SECONDS) -> ImpatienceForecast:
    rate = impatience_rate(state.impatience_per_second, state.impatience_bonus_rate)
    if state.impatience is None or rate is None:
        return ImpatienceForecast(state.impatience, rate, state.impatience_to_lose,
                                  None, None, "Ungeduldsfelder fehlen im Spielstand")

    until = None
    if state.impatience_to_lose is not None and rate > 0:
        until = max((state.impatience_to_lose - state.impatience) / rate, 0.0)

    projected = project_impatience(state.impatience, state.impatience_per_second,
                                   state.impatience_bonus_rate, seconds_ahead)

    warning = None
    if state.impatience_to_lose is not None:
        if state.impatience >= state.impatience_to_lose:
            warning = "Verlustschwelle erreicht"
        elif projected >= state.impatience_to_lose:
            warning = (f"Ungeduld erreicht die Schwelle in {until:.0f} Spielzeitsekunden, "
                       "ohne weiteren Reputationsgewinn")
    return ImpatienceForecast(state.impatience, rate, state.impatience_to_lose,
                              until, projected, warning)


# --------------------------------------------------------------------------
# Nahrung
# --------------------------------------------------------------------------


def geaenderte_stellen(paare) -> set[int] | None:
    """Die Stellen, an denen sich irgendeine Reihe geaendert hat.

    Alle Zeitreihen eines Spielstands -- jede Ware, jede Kategorie -- teilen
    denselben Schreibzeiger. Eine einzelne Reihe verraet den frischen Block
    nicht, wenn ihr neuester Wert zufaellig dem von vor einer halben Stunde
    gleicht: dann rueckte der Block um eine Stelle nach hinten, ein alter
    Wert kam hinein und der neueste fiel weg. Gemessen an Zufallsreihen:
    1,7 % der Vorhersagen falsch, Ratenfehler im Median 18 %, bis 300 %.
    Ueber alle Reihen zusammen muesste der Zufall ueberall gleichzeitig
    treffen.

    `paare` sind (vorher, jetzt); gezaehlt wird nur die haeufigste Laenge.
    None, wenn kein Paar vergleichbar ist.
    """
    laengen: dict[int, int] = {}
    brauchbar = []
    for vorher, jetzt in paare:
        if isinstance(vorher, list) and isinstance(jetzt, list) and jetzt \
                and len(vorher) == len(jetzt):
            brauchbar.append((vorher, jetzt))
            laengen[len(jetzt)] = laengen.get(len(jetzt), 0) + 1
    if not brauchbar:
        return None
    n = max(laengen, key=laengen.get)
    out: set[int] = set()
    for vorher, jetzt in brauchbar:
        if len(jetzt) == n:
            out.update(i for i, (a, b) in enumerate(zip(vorher, jetzt)) if a != b)
    return out


def _alle_paare(jetzt, vorher) -> list[tuple]:
    """Je Reihe (vorher, jetzt) aus Waren- und Kategorienreihen zweier Staende."""
    paare = []
    for feld in ("category_trends", "goods_trends"):
        alt = getattr(vorher, feld, None) or {}
        for name, reihe in (getattr(jetzt, feld, None) or {}).items():
            if name in alt:
                paare.append((alt[name], reihe))
    return paare


def _block(changed: list[int], n: int) -> tuple[int, int, int]:
    """Anfang, Ende und Laenge des Blocks, den die geaenderten Stellen im Ring
    aufspannen: hinter der groessten Luecke faengt er an."""
    luecken = [((changed[(k + 1) % len(changed)] - changed[k]) % n, k)
               for k in range(len(changed))]
    _, letzter = max(luecken)
    start = changed[(letzter + 1) % len(changed)]
    ende = changed[letzter]
    return start, ende, (ende - start) % n + 1


def fresh_samples(before: list[float], after: list[float],
                  expected: int | None = None,
                  geaendert: set[int] | None = None) -> list[float]:
    """Die Stuetzstellen, die zwischen zwei Spielstaenden neu geschrieben wurden.

    Der Ringpuffer laesst den Schreibzeiger wandern; frisch ist ein
    zusammenhaengender Block, der ueber das Feldende hinauslaufen kann.

    Ein Vergleich Stelle fuer Stelle reicht dafuer nicht: schreibt das Spiel
    denselben Wert noch einmal -- der Nahrungsbestand kann in einer halben
    Stunde zweimal 97 betragen --, sieht die Stelle unveraendert aus. Einzeln
    genommen reisst das Loecher in den Block, und ein Loch ist von einem
    Feldumbruch nicht zu unterscheiden.

    Deshalb wird nicht die Menge der geaenderten Stellen genommen, sondern der
    Block, den sie aufspannen: Anfang und Ende im Ring bestimmen, alles
    dazwischen mitnehmen. Kollisionen fallen damit an ihren richtigen Platz.

    Bleibt die Kollision genau am Rand des Blocks, hilft auch das nicht -- dann
    fehlt vorn oder hinten eine Stuetzstelle. Wer die vergangene Spielzeit
    kennt, kennt aber die erwartete Blocklaenge und kann den Block nach hinten
    verlaengern: `expected`. Sicherer ist `geaendert`: die Stellen, an denen
    sich irgendeine Reihe desselben Spielstands geaendert hat.
    """
    if len(before) != len(after) or not after:
        return list(after)
    n = len(after)
    if geaendert is not None:
        changed = sorted(i for i in geaendert if 0 <= i < n)
    else:
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    if not changed:
        return []
    if len(changed) == n:
        return list(after)

    start, ende, laenge = _block(changed, n)
    if expected is not None and 0 < laenge < expected <= n:
        # Der juengste Wert liegt am Blockende. Fehlt vorn etwas, nach hinten
        # verlaengern, statt die Reihe kuerzer zu nehmen als sie ist.
        start = (ende - (expected - 1)) % n
        laenge = expected
    return [after[(start + off) % n] for off in range(laenge)]


def slope_per_second(values: list[float], sample_seconds: float = SAMPLE_SECONDS) -> float | None:
    """Steigung je Spielzeitsekunde, kleinste Quadrate ueber die Stuetzstellen."""
    n = len(values)
    if n < 3:
        return None
    xs = [i * sample_seconds for i in range(n)]
    mx = sum(xs) / n
    my = sum(values) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, values)) / denom


def frische_werte(vorher: list[float], reihe: list[float],
                  t0: float | None, t1: float | None,
                  geaendert: set[int] | None = None) -> list[float] | None:
    """Die neuen Stuetzstellen zwischen zwei Staenden -- oder None, wenn sich
    ihre Reihenfolge nicht mehr herstellen laesst.

    Aus der vergangenen Spielzeit folgt, wie viele Stuetzstellen dazugekommen
    sein muessen -- rund eine je zehn Sekunden. Ist jede Stelle neu, verraet
    der Ringpuffer seinen Schreibzeiger nicht; die Reihe roh zu nehmen ergab
    am Rechner ein steigendes Lager, wo es fiel.
    """
    erwartet = None
    if isinstance(t0, (int, float)) and isinstance(t1, (int, float)) and t1 > t0:
        erwartet = max(round((t1 - t0) / SAMPLE_SECONDS), 0) or None
    if geaendert is not None:
        # Nur wenn der gemeinsame Block zur vergangenen Spielzeit passt. Dass
        # alle Reihen einen Zeiger teilen, zeigen die Messungen (29-30 Stellen
        # je Speichern), belegt ist es nicht fuer jede Reihe -- und eine Reihe
        # mit eigenem Zeiger machte den gemeinsamen Block zu lang.
        stellen = sorted(i for i in geaendert if 0 <= i < len(reihe))
        if (erwartet is None or not stellen or len(stellen) >= len(reihe)
                or abs(_block(stellen, len(reihe))[2] - erwartet) > 2):
            geaendert = None
    if len(vorher) == len(reihe) and reihe and (
            (erwartet is not None and erwartet >= len(reihe))
            or (len(geaendert) >= len(reihe) if geaendert is not None
                else all(a != b for a, b in zip(vorher, reihe, strict=True)))):
        return None
    return fresh_samples(vorher, reihe, erwartet, geaendert)


def waren_trends(aktuell: dict[str, list[float]], vorher: dict[str, list[float]],
                 t0: float | None, t1: float | None) -> list[dict]:
    """Je Ware Rate und, wenn sie faellt, Reichweite -- dieselben Reihen wie
    „Verlauf" im Spiel, dieselbe Rechnung wie bei der Nahrung."""
    out = []
    geaendert = geaenderte_stellen((vorher[w], r) for w, r in aktuell.items() if w in vorher)
    for ware, reihe in aktuell.items():
        alt = vorher.get(ware)
        if not alt:
            continue
        werte = frische_werte(alt, reihe, t0, t1, geaendert)
        if not werte:
            continue
        rate = slope_per_second(werte)
        if rate is None or rate == 0:
            continue
        eintrag = {"ware": ware, "bestand": werte[-1],
                   "rate_je_minute": round(rate * 60, 2)}
        if rate < 0 and werte[-1] > 0:
            eintrag["reichweite_sekunden"] = round(werte[-1] / -rate, 1)
        out.append(eintrag)
    return out


def food_forecast(
    current,
    previous=None,
    category: str = "Food",
    season_seconds: float | None = None,
) -> FoodForecast:
    """Reichweite der Nahrung, aus der Zeitreihe statt aus zwei Momentaufnahmen."""
    series = current.category_trends.get(category)
    if not series:
        return FoodForecast(None, None, None, 0,
                            f"Keine Zeitreihe '{category}' im Spielstand")

    if previous is not None and previous.category_trends.get(category):
        values = frische_werte(previous.category_trends[category], series,
                               getattr(previous, "game_time", None),
                               getattr(current, "game_time", None),
                               geaenderte_stellen(_alle_paare(current, previous)))
        if values is None:
            return FoodForecast(
                None, None, None, 0,
                "Zwischen den zwei Spielständen liegt zu viel Spielzeit, um den "
                "Verbrauch zu rechnen -- beim nächsten Speichern geht es wieder")
    else:
        values = []

    stock = values[-1] if values else None
    rate = slope_per_second(values)
    if rate is None:
        return FoodForecast(stock, None, None, len(values),
                            "Zu wenige frische Stuetzstellen -- zweiter Spielstand noetig")

    runway = None
    if rate < 0 and stock is not None:
        runway = max(stock / -rate, 0.0)

    warning = None
    if runway is not None:
        schwelle = season_seconds if season_seconds else SAVE_INTERVAL_SECONDS
        if runway < schwelle:
            grund = ("unter einer Jahreszeit" if season_seconds
                     else "unter einem Speicherintervall (Jahreszeitenlaenge unbekannt)")
            warning = f"Nahrung reicht noch {runway:.0f} Spielzeitsekunden -- {grund}"
    return FoodForecast(stock, rate, runway, len(values), warning)
