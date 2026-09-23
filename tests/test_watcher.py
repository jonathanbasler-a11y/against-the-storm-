"""Tests des Mitschreibers."""

from __future__ import annotations

import json
from pathlib import Path

from ats_assistant.save_reader import GameState, read_state
from ats_assistant.watcher import (Mitschreiber, lauf_kennung, mitschreiben,
                                   run_id_fuer)


def buendel(pfad: Path, spielzeit: float, jahr: int = 5, biom: str = "Coral Forest") -> Path:
    pfad.mkdir(parents=True, exist_ok=True)
    (pfad / "Save.save").write_text(json.dumps({
        "time": spielzeit, "year": jahr, "season": 1,
        "reputation": 5.0, "reputationPenalty": 3.0,
    }), encoding="utf-8")
    (pfad / "MetaSave.save").write_text(json.dumps({
        "gameConditions": {"biome": biom, "difficulty": "Prestige 16 Ascension XIII"},
    }), encoding="utf-8")
    return pfad


def test_erster_zustand_wird_mitgeschrieben(tmp_path: Path) -> None:
    save = buendel(tmp_path / "save", 1000.0)
    mit = Mitschreiber(save, tmp_path / "runs")
    assert mit.einmal_lesen(wait=False) is not None
    assert mit.geschrieben == 1
    assert mit.run_id and "Coral_Forest" in mit.run_id


def test_gleiche_spielzeit_wird_nicht_doppelt_geschrieben(tmp_path: Path) -> None:
    """Eine Datei kann angefasst werden, ohne dass sich etwas ändert -- im
    Messlauf gab es Schreibvorgänge mit null Byte Unterschied."""
    save = buendel(tmp_path / "save", 1000.0)
    mit = Mitschreiber(save, tmp_path / "runs")
    mit.einmal_lesen(wait=False)
    assert mit.einmal_lesen(wait=False) is None
    assert mit.geschrieben == 1


def test_fortschreitende_spielzeit_wird_geschrieben(tmp_path: Path) -> None:
    save = buendel(tmp_path / "save", 1000.0)
    mit = Mitschreiber(save, tmp_path / "runs")
    mit.einmal_lesen(wait=False)
    buendel(save, 1300.0)
    assert mit.einmal_lesen(wait=False) is not None
    assert mit.geschrieben == 2
    zeilen = (tmp_path / "runs" / f"{mit.run_id}.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert [json.loads(z)["game_time"] for z in zeilen] == [1000.0, 1300.0]


def test_zurueckspringende_spielzeit_beginnt_einen_neuen_lauf(tmp_path: Path) -> None:
    """Nach einem gewonnenen Lauf folgt eine neue Siedlung -- die Spieluhr
    fängt wieder von vorn an und darf die alte Mitschrift nicht verlängern."""
    save = buendel(tmp_path / "save", 8000.0, biom="Coral Forest")
    mit = Mitschreiber(save, tmp_path / "runs")
    mit.einmal_lesen(wait=False)
    erster = mit.run_id

    buendel(save, 40.0, jahr=1, biom="Rocky Ravine")
    mit.einmal_lesen(wait=False)
    assert mit.run_id != erster
    assert "Rocky_Ravine" in mit.run_id


def test_unlesbarer_spielstand_wird_uebersprungen(tmp_path: Path) -> None:
    save = tmp_path / "save"
    save.mkdir()
    (save / "Save.save").write_text("{kaputt", encoding="utf-8")
    mit = Mitschreiber(save, tmp_path / "runs")
    assert mit.einmal_lesen(wait=False) is None
    assert mit.geschrieben == 0


def test_run_id_enthaelt_biom_und_stufe() -> None:
    state = GameState(captured_at="x", biome="Rocky Ravine", prestige=13)
    kennung = run_id_fuer(state)
    assert "Rocky_Ravine" in kennung and "p13" in kennung


def test_zwei_laeufe_am_selben_tag_bekommen_verschiedene_kennungen() -> None:
    """Sonst landen beide in einer Datei und die Spieluhr springt mittendrin
    zurück -- damit ist jede Auswertung über den Verlauf hinüber."""
    import time as _t
    state = GameState(captured_at="x", biome="Coral Forest", prestige=13)
    erste = run_id_fuer(state)
    _t.sleep(1.05)
    assert run_id_fuer(state) != erste


# --------------------------------------------------------------------------
# Welche Mitschrift ein Zustand fortschreibt
#
# Gemessen am Spielrechner: 22 Dateien in `runs/`, jede mit einem einzigen
# Eintrag, und `food_forecast` meldete dauerhaft "Es braucht zwei
# Spielstände". Die Kennung enthielt die Spielzeit, also bekam jeder Aufruf
# eine eigene Datei. Kein Test hat das gesehen, weil jeder seine Kennung
# selbst mitgab.
# --------------------------------------------------------------------------


def test_lauf_kennung_schreibt_dieselbe_siedlung_fort(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    save = buendel(tmp_path / "save", 1000.0)
    mit = Mitschreiber(save, runs)
    mit.einmal_lesen(wait=False)

    spaeter, _ = read_state(buendel(save, 1300.0), wait=False)
    assert lauf_kennung(spaeter, runs) == mit.run_id


def test_lauf_kennung_beginnt_neu_wenn_die_uhr_zurueckspringt(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    save = buendel(tmp_path / "save", 8000.0)
    mit = Mitschreiber(save, runs)
    mit.einmal_lesen(wait=False)

    neue_siedlung, _ = read_state(buendel(save, 120.0), wait=False)
    assert lauf_kennung(neue_siedlung, runs) != mit.run_id


def test_lauf_kennung_beginnt_neu_in_einem_anderen_biom(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    save = buendel(tmp_path / "save", 1000.0, biom="Coral Forest")
    mit = Mitschreiber(save, runs)
    mit.einmal_lesen(wait=False)

    anderswo, _ = read_state(buendel(save, 1100.0, biom="Marshlands"), wait=False)
    assert lauf_kennung(anderswo, runs) != mit.run_id


def test_lauf_kennung_ohne_mitschrift_legt_eine_an(tmp_path: Path) -> None:
    zustand, _ = read_state(buendel(tmp_path / "save", 500.0), wait=False)
    kennung = lauf_kennung(zustand, tmp_path / "runs")
    assert "Coral_Forest" in kennung


def test_ein_neu_gestarteter_mitschreiber_verlaengert_den_lauf(tmp_path: Path) -> None:
    """Wer `ats-watch` neu startet, soll nicht in einer neuen Datei landen --
    sonst fehlt der Vorhersage nach jedem Neustart wieder der zweite Stand."""
    runs = tmp_path / "runs"
    save = buendel(tmp_path / "save", 1000.0)
    erster = Mitschreiber(save, runs)
    erster.einmal_lesen(wait=False)

    buendel(save, 1300.0)
    zweiter = Mitschreiber(save, runs)
    zweiter.einmal_lesen(wait=False)

    assert zweiter.run_id == erster.run_id
    assert len(list(runs.glob("*.jsonl"))) == 1


def test_dieselbe_spielzeit_verlaengert_die_datei_nicht(tmp_path: Path) -> None:
    """Zwei Aufrufe auf demselben Spielstand sind ein Zustand, kein zweiter --
    sonst rechnet die Vorhersage eine Steigung über null Sekunden."""
    runs = tmp_path / "runs"
    save = buendel(tmp_path / "save", 1000.0)
    zustand, _ = read_state(save, wait=False)

    kennung, geschrieben = mitschreiben(zustand, runs)
    assert geschrieben is True
    kennung_2, nochmal = mitschreiben(zustand, runs)
    assert (kennung_2, nochmal) == (kennung, False)

    zeilen = (runs / f"{kennung}.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(zeilen) == 1


def test_ein_besser_gelesener_stand_ersetzt_die_letzte_zeile(tmp_path: Path) -> None:
    """Am Spielrechner: das Spiel stand in der Pause, der Leser war
    inzwischen repariert -- aber die Mitschrift behielt die alte Zeile mit
    `lager: {}`, weil die Spielzeit dieselbe war. Der Reiter „Nahrung"
    rechnete weiter auf leer, während der Rat das Lager schon kannte."""
    runs = tmp_path / "runs"
    save = buendel(tmp_path / "save", 500.0)
    frueher, _ = read_state(save, wait=False)
    kennung, _ = mitschreiben(frueher, runs)

    save = buendel(tmp_path / "save", 600.0)
    alt, _ = read_state(save, wait=False)              # so las der alte Leser
    mitschreiben(alt, runs)
    neu, _ = read_state(save, wait=False)
    neu.storage = {"Berries": 16.0, "Eggs": 14.0}      # so liest der neue
    _, geschrieben = mitschreiben(neu, runs)

    assert geschrieben is True
    zeilen = (runs / f"{kennung}.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(zeilen) == 2                             # ersetzt, nicht angehängt
    assert json.loads(zeilen[0])["game_time"] == 500.0  # Früheres bleibt
    assert json.loads(zeilen[1])["storage"] == {"Berries": 16.0, "Eggs": 14.0}


def test_nur_der_zeitstempel_anders_ist_kein_neuer_stand(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    save = buendel(tmp_path / "save", 600.0)
    erster, _ = read_state(save, wait=False)
    kennung, _ = mitschreiben(erster, runs)
    zweiter, _ = read_state(save, wait=False)
    zweiter.captured_at = "2099-01-01T00:00:00+00:00"
    assert mitschreiben(zweiter, runs) == (kennung, False)
    zeilen = (runs / f"{kennung}.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(zeilen[0])["captured_at"] == erster.captured_at


# --------------------------------------------------------------------------
# QA-Runde 2 (23.09.2026): Mitschrift
# --------------------------------------------------------------------------


def _zeilen(runs: Path, kennung: str) -> list[dict]:
    return [json.loads(z) for z in
            (runs / f"{kennung}.jsonl").read_text(encoding="utf-8").splitlines() if z.strip()]


def test_eine_notiz_am_ende_zerteilt_die_mitschrift_nicht(tmp_path: Path) -> None:
    """`log_event` hängt eine Notiz an. Danach begann der nächste Stand eine
    neue Datei -- die Notiz hat keine Spielzeit -- oder derselbe Stand
    wurde ein zweites Mal geschrieben."""
    runs = tmp_path / "runs"
    zustand, _ = read_state(buendel(tmp_path / "save", 500.0), wait=False)
    kennung, _ = mitschreiben(zustand, runs)
    with (runs / f"{kennung}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"typ": "notiz", "text": "Grundstein gewählt"}) + "\n")

    nochmal, _ = read_state(buendel(tmp_path / "save", 500.0), wait=False)
    assert mitschreiben(nochmal, runs) == (kennung, False)        # kein Doppel
    spaeter, _ = read_state(buendel(tmp_path / "save", 800.0), wait=False)
    assert mitschreiben(spaeter, runs) == (kennung, True)         # dieselbe Datei
    assert [z.get("game_time") for z in _zeilen(runs, kennung)] == [500.0, None, 800.0]


def test_ein_halb_gelesenes_buendel_beginnt_keinen_neuen_lauf(tmp_path: Path) -> None:
    """MetaSave kurz gesperrt: Biom und Stufe fehlen. Das ist keine neue
    Siedlung, sondern ein unvollständiger Blick auf dieselbe."""
    runs = tmp_path / "runs"
    zustand, _ = read_state(buendel(tmp_path / "save", 500.0), wait=False)
    kennung, _ = mitschreiben(zustand, runs)

    save = buendel(tmp_path / "save", 800.0)
    (save / "MetaSave.save").unlink()
    halb, _ = read_state(save, wait=False)
    assert halb.biome is None
    assert lauf_kennung(halb, runs) == kennung


def test_ein_schlechter_gelesener_stand_ersetzt_keinen_besseren(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    zustand, _ = read_state(buendel(tmp_path / "save", 500.0), wait=False)
    kennung, _ = mitschreiben(zustand, runs)
    schlechter, _ = read_state(buendel(tmp_path / "save", 500.0), wait=False)
    schlechter.biome = None
    schlechter.prestige = None
    assert mitschreiben(schlechter, runs) == (kennung, False)
    assert _zeilen(runs, kennung)[-1]["biome"] == "Coral Forest"


def test_leerzeilen_am_ende_werden_gleich_gezaehlt(tmp_path: Path) -> None:
    """`_letzte_zeile` übersprang alle Umbrüche, das Ersetzen nur einen: bei
    `A\\nB\\n\\n` wurde eine dritte Zeile angehängt statt B ersetzt."""
    from ats_assistant.watcher import _letzte_zeile, _letzte_zeile_ersetzen
    datei = tmp_path / "lauf.jsonl"
    datei.write_bytes(b'{"a":1}\n{"b":2}\n\n')
    assert _letzte_zeile(datei) == '{"b":2}'
    _letzte_zeile_ersetzen(datei, '{"c":3}')
    assert datei.read_bytes() == b'{"a":1}\n{"c":3}\n'


def test_der_waechter_schreibt_nicht_doppelt_neben_dem_fenster(tmp_path: Path) -> None:
    """Das Fenster schreibt denselben Spielstand zuerst; `ats-watch` hängte
    ihn danach ein zweites Mal an -- die Vorhersage hatte null Sekunden."""
    runs = tmp_path / "runs"
    save = buendel(tmp_path / "save", 500.0)
    zustand, _ = read_state(save, wait=False)
    kennung, _ = mitschreiben(zustand, runs)           # das Fenster
    waechter = Mitschreiber(save, runs)
    waechter.einmal_lesen(wait=False)
    assert waechter.run_id == kennung
    assert len(_zeilen(runs, kennung)) == 1


def test_der_waechter_ueberlebt_einen_fehler(tmp_path: Path, monkeypatch) -> None:
    from ats_assistant import watcher
    aufrufe = []

    def platzt(self, wait=True):
        aufrufe.append(wait)
        raise PermissionError("vom Spiel gesperrt")

    monkeypatch.setattr(watcher.Mitschreiber, "einmal_lesen", platzt)
    monkeypatch.setattr(watcher, "ABTASTUNG_SEKUNDEN", 0.0)
    signaturen = iter([("a",), ("b",), ("c",)] + [("c",)] * 1000)
    monkeypatch.setattr(watcher, "_signatur", lambda _: next(signaturen))
    watcher.beobachten(tmp_path / "save", tmp_path / "runs", minuten=0.0005)
    assert len(aufrufe) >= 2                           # weitergelaufen
