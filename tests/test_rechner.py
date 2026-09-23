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

import pytest

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
    assert arten == ["zustand", "nahrung", "ungeduld", "ketten", "wissen", "umgebung",
                     "anmeldung"]


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


# Der Wortlaut des SDK bei fehlender Anmeldung -- gemessen in anthropic 1.7.0.
SDK_WORTLAUT = ('"Could not resolve authentication method. Expected one of '
                'api_key, auth_token, or credentials to be set."')


@pytest.fixture
def ohne_anmeldung(monkeypatch):
    """Kein Aufruf hinaus, auch wenn auf diesem Rechner ein Schlüssel liegt.

    Vorher hing dieser Test daran, dass die Umgebung keine Anmeldung hat --
    auf einem Rechner mit Schlüssel hätte er Geld gekostet.
    """
    class OhneSchluessel:
        """So verhält sich das SDK gemessen: es wirft erst beim Senden."""

        def __init__(self):
            self.messages = self

        def create(self, **kwargs):
            raise TypeError(SDK_WORTLAUT)

    monkeypatch.setattr(rechner.berater, "_client", lambda: (None, OhneSchluessel()))


def test_der_rat_reicht_die_lage_weiter_ohne_bild(tmp_path: Path, ohne_anmeldung) -> None:
    ausgang: queue.Queue = queue.Queue()
    r = rechner.Rechner(tmp_path / "save", tmp_path / "runs",
                        tmp_path / "kb.sqlite", ausgang)
    antwort = r._rat({"zustand": {"jahr": 3, "biom": "Coastal Grove"},
                      "auswahl": {"angebot": [{"de": "Pilzführer", "en": "Fungal Guide"}]}})
    # Ohne Anmeldung: ein Satz statt eines Absturzes, und die Lage liegt bei.
    assert antwort["ok"] is False
    assert antwort["auszug"]["siedlung"]["jahr"] == 3
    assert "bild" not in json.dumps(antwort["auszug"]).lower()


def test_ohne_anmeldung_steht_der_deutsche_satz_da(tmp_path: Path, ohne_anmeldung) -> None:
    """Am Spielrechner stand im Reiter „Rat" der englische Rohtext des SDK.

    `zugang` ist der Schalter, an dem das Fenster entscheidet, ob es auf
    „Lage kopieren" hinweist. Er stand auf True, weil das TypeError des SDK
    an allen except-Zweigen vorbeilief.
    """
    ausgang: queue.Queue = queue.Queue()
    r = rechner.Rechner(tmp_path / "save", tmp_path / "runs",
                        tmp_path / "kb.sqlite", ausgang)
    antwort = r._rat({"zustand": {"jahr": 3}})
    assert antwort["zugang"] is False
    assert "ANTHROPIC_API_KEY" in antwort["text"]
    assert "Could not resolve" not in antwort["text"]


# --------------------------------------------------------------------------
# Feindseligkeit
#
# Am Spielrechner stand im Feld: {'level': 3, 'points': 72, 'sources':
# -- abgeschnitten am rechten Rand. Das Fenster suchte nach 'current', ein
# Schlüssel aus der erfundenen Testvorlage; das Spiel schreibt 'level' und
# 'points'. Die Vorlage war die Quelle des Irrtums, nicht das Fenster.
# --------------------------------------------------------------------------


def test_feindseligkeit_wird_zum_satz() -> None:
    assert rechner.feindseligkeit({"level": 3, "points": 72,
                                   "sources": {"a": 1}}) == "Stufe 3 · 72 Punkte"


def test_feindseligkeit_ohne_stufe_zeigt_die_punkte() -> None:
    assert rechner.feindseligkeit({"points": 180}) == "180 Punkte"


def test_feindseligkeit_kennt_auch_die_alte_form() -> None:
    assert rechner.feindseligkeit({"current": 180}) == "180 Punkte"


def test_feindseligkeit_zeigt_nie_ein_dictionary() -> None:
    """Was auch kommt -- eine geschweifte Klammer im Fenster ist ein Fehler."""
    for wert in ({"unbekannt": 7}, {}, None, 4, "hoch"):
        assert "{" not in rechner.feindseligkeit(wert)


def test_der_handweg_fasst_den_bildschirm_nie_an(tmp_path: Path, monkeypatch) -> None:
    """Am Spielrechner riet der Auswahlreiter zur Texterkennung, obwohl im
    Feld getippter Text stand. Wer tippt, braucht keine."""
    def nicht_anfassen(*args, **kwargs):
        raise AssertionError("Der Handweg hat den Bildschirm angefasst.")

    monkeypatch.setattr(rechner.tools_api.screen, "aufnehmen", nicht_anfassen)
    monkeypatch.setattr(rechner.tools_api.screen, "erkenne", nicht_anfassen)

    ausgang: queue.Queue = queue.Queue()
    r = rechner.Rechner(tmp_path / "save", tmp_path / "runs",
                        tmp_path / "kb.sqlite", ausgang)
    r._ausfuehren(rechner.Auftrag("auswahl", {"text": ["handelsverhandlungen"]}))
    art, wert = ausgang.get_nowait()
    assert art == "auswahl"
    assert wert["quelle"] == "hand"


def test_die_lage_sagt_auch_ob_eine_anmeldung_da_ist(tmp_path: Path, monkeypatch) -> None:
    """Damit der Reiter „Rat" es sagen kann, bevor jemand fragt."""
    monkeypatch.setattr(rechner.berater, "anmeldung_gefunden", lambda: False)
    ausgang: queue.Queue = queue.Queue()
    r = rechner.Rechner(tmp_path / "save", tmp_path / "runs",
                        tmp_path / "kb.sqlite", ausgang)
    r._ausfuehren(rechner.Auftrag("lage"))
    arten = {art: wert for art, wert in list(ausgang.queue)}
    assert arten["anmeldung"] is False


def test_der_rat_bekommt_die_nahrungsketten(tmp_path: Path, ohne_anmeldung) -> None:
    ausgang: queue.Queue = queue.Queue()
    r = rechner.Rechner(tmp_path / "save", tmp_path / "runs",
                        tmp_path / "kb.sqlite", ausgang)
    antwort = r._rat({"zustand": {"jahr": 1},
                      "ketten": {"ketten": [{"gebaeude": "Grill", "faktor": 6.0}]}})
    assert antwort["auszug"]["nahrung_rat"]["ketten"][0]["gebaeude"] == "Grill"


def test_das_erste_lesen_passiert_einmal(tmp_path: Path) -> None:
    """`run()` bat um die Lage, und drei Sekunden später sah `_nachsehen`
    eine neue Signatur (von None aus) und bat ein zweites Mal."""
    save_dir = buendel(tmp_path / "save")
    r = rechner.Rechner(save_dir, tmp_path / "runs", tmp_path / "kb.sqlite", queue.Queue())
    r._anfangen()
    r._nachsehen()
    assert r.eingang.qsize() == 1


def test_der_bildweg_reicht_das_foto_durch(tmp_path: Path, monkeypatch) -> None:
    gesehen = {}

    def lesen(**kw):
        gesehen.update(kw)
        return {"verfuegbar": False}

    monkeypatch.setattr(rechner.tools_api, "read_choice", lesen)
    r = rechner.Rechner(tmp_path, tmp_path / "runs", tmp_path / "kb.sqlite", queue.Queue())
    r._ausfuehren(rechner.Auftrag("auswahl", {"bild": "foto.png", "arten": ("order",)}))
    assert gesehen["bild"] == "foto.png" and gesehen["aufnehmen"] is False


def test_ohne_spielstand_gehen_keine_alten_vorhersagen_hinaus(tmp_path: Path) -> None:
    """Nahrung, Ungeduld und Ketten kamen aus der Mitschrift der letzten
    Siedlung und füllten die gerade geleerten Felder wieder."""
    ausgang: queue.Queue = queue.Queue()
    r = rechner.Rechner(tmp_path / "weg", tmp_path / "runs", tmp_path / "kb.sqlite", ausgang)
    r._ausfuehren(rechner.Auftrag("lage"))
    arten = [a for a, _ in list(ausgang.queue)]
    assert "zustand" in arten
    assert not {"nahrung", "ungeduld", "ketten"} & set(arten)


def test_eine_offene_bauplanwahl_gilt_als_wahl(tmp_path: Path, monkeypatch) -> None:
    gesehen = {}

    def frage(auszug, modell=None, wahl_steht_an=False, **kw):
        gesehen["wahl"] = wahl_steht_an
        raise rechner.berater.KeinZugang("x")

    monkeypatch.setattr(rechner.berater, "frage", frage)
    r = rechner.Rechner(tmp_path, tmp_path / "runs", tmp_path / "kb.sqlite", queue.Queue())
    r._rat({"zustand": {"jahr": 1, "bauplan_wahl": {"angebot": ["Smokehouse"]}}})
    assert gesehen["wahl"] is True


def test_die_lage_liefert_auch_das_wissen(tmp_path: Path) -> None:
    ausgang: queue.Queue = queue.Queue()
    r = rechner.Rechner(buendel(tmp_path / "save"), tmp_path / "runs",
                        tmp_path / "kb.sqlite", ausgang)
    r._ausfuehren(rechner.Auftrag("lage"))
    assert "wissen" in [a for a, _ in list(ausgang.queue)]


def test_der_rat_bekommt_das_nachschlagen(tmp_path: Path, monkeypatch) -> None:
    gesehen = {}

    def frage(auszug, modell=None, wahl_steht_an=False, nachschlagen=None, **kw):
        gesehen["nachschlagen"] = nachschlagen
        raise rechner.berater.KeinZugang("x")

    monkeypatch.setattr(rechner.berater, "frage", frage)
    r = rechner.Rechner(tmp_path, tmp_path / "runs", tmp_path / "kb.sqlite", queue.Queue())
    r._rat({"zustand": {"jahr": 1}})
    assert callable(gesehen["nachschlagen"])
    assert "hinweis" in gesehen["nachschlagen"]("Gibtsnicht")
