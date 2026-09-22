"""Tests des Arbeits-Threads hinter dem Fenster.

Ohne Widgets, ohne tkinter. Geprüft wird das, was entscheidet: wann neu
gerechnet wird, was in die Warteschlange geht, und dass ein Fehler den
Thread nicht umbringt.
"""

from __future__ import annotations

import json
import queue
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ats_assistant import rechner


def buendel(pfad: Path) -> Path:
    pfad.mkdir(parents=True, exist_ok=True)
    (pfad / "Save.save").write_text(json.dumps({
        "time": 500.0, "year": 2, "season": 1,
        "storage": {"goods": [{"Key": "[Food Raw] Meat", "Value": 40}]},
        "trends": {"goodsCategoriesTrends": {"Food": [90.0] * 180}},
    }), encoding="utf-8")
    return pfad


def test_minuten_und_alter_lesen_sich_wie_saetze() -> None:
    assert rechner.minuten(None) == "–"
    assert rechner.minuten(45) == "45 s"
    assert rechner.minuten(340) == "6 min"
    assert rechner.alter(None) == "unbekannt"
    assert rechner.alter(datetime.now(timezone.utc).isoformat()) == "gerade eben"
    alt = (datetime.now(timezone.utc) - timedelta(minutes=7)).isoformat()
    assert rechner.alter(alt) == "vor 7 min gelesen"
    assert rechner.alter("kein Zeitstempel") == "kein Zeitstempel"


def test_ein_auftrag_legt_jede_antwort_in_die_warteschlange(tmp_path: Path) -> None:
    ausgang: queue.Queue = queue.Queue()
    r = rechner.Rechner(buendel(tmp_path / "save"), tmp_path / "runs",
                        tmp_path / "kb.sqlite", ausgang)
    r._ausfuehren(rechner.Auftrag("lage"))

    arten = []
    while not ausgang.empty():
        arten.append(ausgang.get_nowait()[0])
    assert arten == ["zustand", "nahrung", "ungeduld", "ketten", "umgebung"]


def test_ein_fehler_bringt_den_thread_nicht_um(tmp_path: Path) -> None:
    """Ein toter Arbeits-Thread wäre eine Oberfläche, die stehenbleibt,
    ohne zu sagen warum."""
    ausgang: queue.Queue = queue.Queue()
    r = rechner.Rechner(tmp_path / "weg", tmp_path / "runs",
                        tmp_path / "kb.sqlite", ausgang)
    def platzt(auftrag):
        r.stoppen()                           # nach diesem einen Durchlauf ist Schluss
        raise RuntimeError("geplatzt")

    r._ausfuehren = platzt
    r.bitte("lage")
    r.run()                                   # die Schleife fängt und läuft weiter

    meldungen = []
    while not ausgang.empty():
        meldungen.append(ausgang.get_nowait())
    assert any(art == "fehler" and "geplatzt" in wert for art, wert in meldungen)


def test_neu_gerechnet_wird_nur_wenn_das_spiel_geschrieben_hat(tmp_path: Path) -> None:
    """Das Spiel schreibt etwa alle 300 Spielzeitsekunden. Dazwischen wäre
    jedes Neulesen verschwendet -- und `get_state` wartet drei Sekunden
    auf Ruhe."""
    save_dir = buendel(tmp_path / "save")
    ausgang: queue.Queue = queue.Queue()
    r = rechner.Rechner(save_dir, tmp_path / "runs", tmp_path / "kb.sqlite", ausgang)

    r._nachsehen()                            # erstes Mal: Signatur ist neu
    assert r.eingang.qsize() == 1
    r._nachsehen()                            # nichts geschrieben
    assert r.eingang.qsize() == 1

    (save_dir / "Save.save").write_text('{"time": 800.0}', encoding="utf-8")
    r._nachsehen()
    assert r.eingang.qsize() == 2


def test_ein_fehlender_spielordner_laesst_den_takt_weiterlaufen(tmp_path: Path) -> None:
    r = rechner.Rechner(tmp_path / "gibtsnicht", tmp_path / "runs",
                        tmp_path / "kb.sqlite", queue.Queue())
    r._nachsehen()                            # darf nicht werfen
    r._nachsehen()


def test_der_rat_reicht_die_lage_weiter_ohne_bild(tmp_path: Path) -> None:
    ausgang: queue.Queue = queue.Queue()
    r = rechner.Rechner(tmp_path / "save", tmp_path / "runs",
                        tmp_path / "kb.sqlite", ausgang)
    antwort = r._rat({"zustand": {"jahr": 3, "biom": "Coastal Grove"},
                      "auswahl": {"angebot": [{"de": "Pilzführer", "en": "Fungal Guide"}]}})
    # Ohne Anmeldung: ein Satz statt eines Absturzes, und die Lage liegt bei.
    assert antwort["ok"] is False
    assert antwort["auszug"]["siedlung"]["jahr"] == 3
    assert "bild" not in json.dumps(antwort["auszug"]).lower()
