"""Tests der Vorhersagen gegen echte Messwerte aus dem Spielstand."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ats_assistant import forecast
from ats_assistant.forecast import (
    SAMPLE_SECONDS,
    fresh_samples,
    impatience_forecast,
    impatience_rate,
    project_impatience,
    slope_per_second,
    food_forecast,
)


# Gemessen am 2026-09-21, dritter watch-Lauf, vier Schreibvorgaenge.
# (Spieluhr, Reputation, Ungeduld) -- siehe docs/PHASE0.md.
ECHTE_MESSPUNKTE = [
    (7964.39453, 13.0042973, 9.630633),
    (8263.794, 13.6093655, 10.3969851),
    (8562.617, 14.6364851, 10.16339),
    (8746.994, 18.0, 6.636307),
]
PER_SEC = 0.00425
BONUS = -0.400000036


@pytest.mark.parametrize("i", [0, 1, 2])
def test_ungeduldsmodell_trifft_die_messung(i: int) -> None:
    """Das Modell muss alle drei gemessenen Intervalle treffen.

    Das ist der eigentliche Beleg: drei unabhaengige Intervalle, darunter
    eines ohne ueberschrittenen Reputationspunkt und eines mit vieren.
    """
    (t0, r0, u0), (t1, r1, u1) = ECHTE_MESSPUNKTE[i], ECHTE_MESSPUNKTE[i + 1]
    vorhergesagt = project_impatience(
        impatience=u0, per_second=PER_SEC, bonus_rate=BONUS,
        seconds=t1 - t0, reputation_from=r0, reputation_to=r1,
    )
    assert vorhergesagt == pytest.approx(u1, abs=0.005)


def test_anteilige_reputation_trifft_nicht() -> None:
    """Gegenprobe: anteilig gerechnet ergibt sich kein konstanter Faktor.

    Wenn dieser Test einmal fehlschlaegt, war die Unterscheidung zwischen
    ganzen und anteiligen Punkten doch nicht noetig.
    """
    faktoren = []
    for (t0, r0, u0), (t1, r1, u1) in zip(ECHTE_MESSPUNKTE, ECHTE_MESSPUNKTE[1:]):
        zuwachs = impatience_rate(PER_SEC, BONUS) * (t1 - t0)
        faktoren.append((zuwachs - (u1 - u0)) / (r1 - r0))
    assert max(faktoren) - min(faktoren) > 0.5


def test_zuwachsrate_rechnet_die_bonusrate_ein() -> None:
    assert impatience_rate(0.00425, -0.4) == pytest.approx(0.00255)
    assert impatience_rate(0.00425, None) == pytest.approx(0.00425)
    assert impatience_rate(None, -0.4) is None


def test_ganze_punkte_statt_anteilig() -> None:
    # 13,0 -> 13,6 ueberschreitet keinen ganzen Punkt
    ohne = project_impatience(10.0, 0.0, 0.0, 0.0, reputation_from=13.0, reputation_to=13.6)
    assert ohne == pytest.approx(10.0)
    # 13,6 -> 14,6 ueberschreitet genau einen
    einer = project_impatience(10.0, 0.0, 0.0, 0.0, reputation_from=13.6, reputation_to=14.6)
    assert einer == pytest.approx(9.0)
    # 14,6 -> 18,0 ueberschreitet vier
    vier = project_impatience(10.0, 0.0, 0.0, 0.0, reputation_from=14.6, reputation_to=18.0)
    assert vier == pytest.approx(6.0)


@dataclass
class FakeState:
    game_time: float | None = None
    impatience: float | None = None
    impatience_to_lose: float | None = None
    impatience_per_second: float | None = None
    impatience_bonus_rate: float | None = None
    category_trends: dict | None = None

    def __post_init__(self) -> None:
        if self.category_trends is None:
            self.category_trends = {}


def test_ungeduldsvorhersage_warnt_vor_der_schwelle() -> None:
    state = FakeState(impatience=13.9, impatience_to_lose=14.0,
                      impatience_per_second=PER_SEC, impatience_bonus_rate=BONUS)
    f = impatience_forecast(state, seconds_ahead=300.0)
    assert f.seconds_until_loss == pytest.approx(0.1 / 0.00255, rel=1e-6)
    assert f.warning is not None and "Schwelle" in f.warning


def test_ungeduldsvorhersage_ohne_felder_bricht_nicht_ab() -> None:
    f = impatience_forecast(FakeState())
    assert f.warning is not None and f.seconds_until_loss is None


# --------------------------------------------------------------------------
# Nahrung
# --------------------------------------------------------------------------


def test_frische_stuetzstellen_ohne_ueberlauf() -> None:
    vorher = [0.0] * 180
    nachher = list(vorher)
    nachher[40:70] = [float(i) for i in range(30)]
    # Der erste neue Wert ist zufaellig 0.0 und damit gleich dem alten -- die
    # Stelle sieht unveraendert aus und fehlt ohne weitere Information.
    assert fresh_samples(vorher, nachher) == [float(i) for i in range(1, 30)]
    # Mit der erwarteten Blocklaenge aus der Spielzeit ist sie wieder da.
    assert fresh_samples(vorher, nachher, expected=30) == [float(i) for i in range(30)]


def test_frische_stuetzstellen_ueberstehen_gleiche_werte() -> None:
    """Schreibt das Spiel denselben Wert noch einmal, sieht die Stelle
    unveraendert aus. Sie gehoert trotzdem in den Block."""
    vorher = [0.0] * 20
    nachher = list(vorher)
    nachher[5:11] = [3.0, 0.0, 4.0, 0.0, 5.0, 6.0]   # zwei Kollisionen mittendrin
    assert fresh_samples(vorher, nachher) == [3.0, 0.0, 4.0, 0.0, 5.0, 6.0]


def test_frische_stuetzstellen_mit_ueberlauf() -> None:
    """Laeuft der Schreibzeiger ueber das Feldende, liegen die Indizes in zwei
    Bloecken -- die Reihenfolge muss trotzdem stimmen."""
    vorher = [0.0] * 20
    nachher = list(vorher)
    nachher[18:20] = [1.0, 2.0]   # Ende des Feldes
    nachher[0:3] = [3.0, 4.0, 5.0]  # und weiter vorn
    assert fresh_samples(vorher, nachher) == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_steigung_je_spielzeitsekunde() -> None:
    # Bestand faellt um 2 je Stuetzstelle, also 0,2 je Sekunde bei 10s Abstand
    werte = [100.0 - 2 * i for i in range(30)]
    assert slope_per_second(werte) == pytest.approx(-2.0 / SAMPLE_SECONDS)


def test_nahrungsvorhersage_rechnet_reichweite() -> None:
    vorher = FakeState(category_trends={"Food": [0.0] * 180})
    reihe = [0.0] * 180
    reihe[40:70] = [100.0 - 2 * i for i in range(30)]   # Ende: 42
    aktuell = FakeState(category_trends={"Food": reihe})
    f = food_forecast(aktuell, vorher, season_seconds=180.0)
    assert f.samples_used == 30
    assert f.stock == pytest.approx(42.0)
    assert f.rate_per_second == pytest.approx(-0.2)
    assert f.runway_seconds == pytest.approx(210.0)
    assert f.warning is None   # 210s Reichweite bei 180s Jahreszeit: reicht


def test_nahrungsvorhersage_warnt_unter_einer_jahreszeit() -> None:
    vorher = FakeState(category_trends={"Food": [0.0] * 180})
    reihe = [0.0] * 180
    reihe[40:70] = [70.0 - 2 * i for i in range(30)]    # Ende: 12 -> reicht 60s
    aktuell = FakeState(category_trends={"Food": reihe})
    f = food_forecast(aktuell, vorher, season_seconds=600.0)
    assert f.warning is not None and "Jahreszeit" in f.warning


def test_nahrungsvorhersage_ohne_zweiten_spielstand() -> None:
    aktuell = FakeState(category_trends={"Food": [1.0] * 180})
    f = food_forecast(aktuell, None)
    assert f.rate_per_second is None
    assert "zweiter Spielstand" in f.warning


def test_ein_ganz_erneuerter_ringpuffer_ergibt_keine_falsche_rate() -> None:
    """Liegen 1800 Spielzeitsekunden oder mehr zwischen zwei Ständen, ist
    jede Stützstelle neu -- und ohne Schreibzeiger ist die Reihenfolge nicht
    mehr herzustellen. Vorher kam hier ein steigender Bestand heraus, wo er
    fiel, und keine Warnung."""
    n, zeiger = 180, 120
    wahr = [2000.0 - 0.1 * SAMPLE_SECONDS * i for i in range(200)]   # fällt stetig
    ring = [0.0] * n
    for i, wert in enumerate(wahr):
        ring[(zeiger - len(wahr) + 1 + i) % n] = wert
    vorher = FakeState(category_trends={"Food": [1.0] * n}, game_time=600.0)
    aktuell = FakeState(category_trends={"Food": ring}, game_time=2600.0)
    f = food_forecast(aktuell, vorher)
    assert f.rate_per_second is None
    assert "Spielzeit" in f.warning


# --------------------------------------------------------------------------
# Runde 7: Trends je Ware -- dieselben Reihen wie „Verlauf" im Spiel.
# --------------------------------------------------------------------------


def test_trends_je_ware_aus_den_frischen_stuetzstellen() -> None:
    from ats_assistant.forecast import waren_trends
    n = 180
    holz_vorher, holz = [100.0] * n, [100.0] * n
    holz[40:70] = [100.0 + 3 * i for i in range(30)]          # steigt 0,3/s
    eier_vorher, eier = [50.0] * n, [50.0] * n
    eier[40:70] = [50.0 - 1 * i for i in range(30)]           # fällt 0,1/s
    trends = waren_trends({"Wood": holz, "Eggs": eier}, {"Wood": holz_vorher, "Eggs": eier_vorher},
                          t0=600.0, t1=900.0)
    nach = {t["ware"]: t for t in trends}
    assert nach["Wood"]["rate_je_minute"] == pytest.approx(18.0)
    assert nach["Eggs"]["rate_je_minute"] == pytest.approx(-6.0)
    assert nach["Eggs"]["reichweite_sekunden"] == pytest.approx(21 / 0.1)
    assert "reichweite_sekunden" not in nach["Wood"]


def test_trends_je_ware_verweigern_einen_ganz_erneuerten_puffer() -> None:
    from ats_assistant.forecast import waren_trends
    assert waren_trends({"Wood": [float(i) for i in range(180)]}, {"Wood": [0.5] * 180},
                        t0=600.0, t1=3000.0) == []


def _ring(werte_vorher: list[float], neu: list[float], zeiger: int) -> list[float]:
    ring = list(werte_vorher)
    for i, v in enumerate(neu):
        ring[(zeiger + i) % len(ring)] = v
    return ring


def test_gleicher_neuester_wert_verschiebt_den_block_nicht() -> None:
    """QA 26.09.2026: Gleicht der neueste Wert dem von vor einer halben Stunde,
    rückte der Block um eins nach hinten -- ein alter Wert kam hinein, der
    neueste fiel weg. Alle Reihen teilen den Schreibzeiger; zusammen sehen
    sie den Block richtig."""
    from types import SimpleNamespace
    alt_food = [100.0] * 15 + [50.0] + [100.0] * 164        # Stelle 15: alt, vor dem Block
    neu_food = [90.0, 80.0, 70.0, 60.0, 100.0]              # Stellen 16-20; 100 wie vorher
    jetzt_food = _ring(alt_food, neu_food, 16)
    alt_holz = [5.0] * 180
    jetzt_holz = _ring(alt_holz, [6.0, 7.0, 8.0, 9.0, 10.0], 16)
    vorher = SimpleNamespace(category_trends={"Food": alt_food}, goods_trends={"Wood": alt_holz},
                             game_time=1000.0)
    jetzt = SimpleNamespace(category_trends={"Food": jetzt_food}, goods_trends={"Wood": jetzt_holz},
                            game_time=1050.0)
    allein = forecast.frische_werte(alt_food, jetzt_food, 1000.0, 1050.0)
    assert allein == [50.0, 90.0, 80.0, 70.0, 60.0]           # der alte Fehler
    f = forecast.food_forecast(jetzt, vorher)
    assert f.stock == 100.0 and f.samples_used == 5


def test_eine_reihe_mit_eigenem_zeiger_verdirbt_den_block_nicht() -> None:
    """Passt der gemeinsame Block nicht zur Spielzeit, gilt die Einzelreihe."""
    alt = [float(i) for i in range(180)]
    jetzt = _ring(alt, [500.0, 501.0, 502.0], 40)
    fremd_alt = [0.0] * 180
    fremd_jetzt = _ring(fremd_alt, [1.0, 2.0, 3.0], 120)       # anderer Zeiger
    geaendert = forecast.geaenderte_stellen([(alt, jetzt), (fremd_alt, fremd_jetzt)])
    assert forecast.frische_werte(alt, jetzt, 0.0, 30.0, geaendert) == [500.0, 501.0, 502.0]
