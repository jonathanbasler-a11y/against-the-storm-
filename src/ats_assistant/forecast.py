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


def fresh_samples(before: list[float], after: list[float],
                  expected: int | None = None) -> list[float]:
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
    verlaengern: `expected`.
    """
    if len(before) != len(after) or not after:
        return list(after)
    n = len(after)
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    if not changed:
        return []
    if len(changed) == n:
        return list(after)

    # Groesste Luecke im Ring suchen: direkt dahinter faengt der frische Block an.
    luecken = [((changed[(k + 1) % len(changed)] - changed[k]) % n, k)
               for k in range(len(changed))]
    _, letzter = max(luecken)
    start = changed[(letzter + 1) % len(changed)]
    ende = changed[letzter]
    laenge = (ende - start) % n + 1
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
        # Aus der vergangenen Spielzeit folgt, wie viele Stuetzstellen
        # dazugekommen sein muessen -- rund eine je zehn Sekunden.
        erwartet = None
        t0 = getattr(previous, "game_time", None)
        t1 = getattr(current, "game_time", None)
        if isinstance(t0, (int, float)) and isinstance(t1, (int, float)) and t1 > t0:
            erwartet = max(round((t1 - t0) / SAMPLE_SECONDS), 0) or None
        vorher = previous.category_trends[category]
        if len(vorher) == len(series) and (
                (erwartet is not None and erwartet >= len(series))
                or all(a != b for a, b in zip(vorher, series, strict=True))):
            # Jede Stuetzstelle ist neu. Der Ringpuffer verraet seinen
            # Schreibzeiger nicht, also ist die Reihenfolge nicht mehr
            # herzustellen -- die Reihe roh zu nehmen ergab am Rechner ein
            # steigendes Lager, wo es fiel.
            return FoodForecast(
                None, None, None, 0,
                "Zwischen den zwei Spielständen liegt zu viel Spielzeit, um den "
                "Verbrauch zu rechnen -- beim nächsten Speichern geht es wieder")
        values = fresh_samples(vorher, series, erwartet)
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
