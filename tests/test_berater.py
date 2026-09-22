"""Tests des Beraters -- ohne echten Aufruf, ohne Geld.

Der Client wird eingesetzt statt gerufen. Geprüft wird das, was dem Projekt
gehört: was hinausgeht, was nicht hinausgehen darf, und was aus einem Fehler
wird.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ats_assistant import berater


class FalscherClient:
    """Nimmt den Aufruf entgegen und merkt sich, was ankam."""

    def __init__(self, text: str = "Nimm die Räucherei.", fehler: Exception | None = None):
        self.text = text
        self.fehler = fehler
        self.gesehen: dict = {}
        self.messages = self

    def create(self, **kwargs):
        self.gesehen = kwargs
        if self.fehler is not None:
            raise self.fehler

        class Block:
            type = "text"

        block = Block()
        block.text = self.text

        class Nutzung:
            input_tokens = 2300
            output_tokens = 150
            cache_read_input_tokens = 1800

        class Antwort:
            content = [block]
            model = kwargs["model"]
            usage = Nutzung()

        return Antwort()


def test_der_systemtext_kommt_aus_der_skill_datei() -> None:
    """Dieselbe Datei wie für Claude Code -- sonst driften die Regeln."""
    text = berater.systemtext()
    assert "Eine Empfehlung" in text
    assert "Prestige 13" in text
    assert not text.startswith("---")        # der Kopfteil ist Verwaltung


def test_systemtext_faellt_zurueck_wenn_die_datei_fehlt(tmp_path: Path) -> None:
    text = berater.systemtext(tmp_path / "gibtsnicht.md")
    assert "Against the Storm" in text and "Empfehlung" in text


def test_kontext_traegt_zahlen_und_namen(tmp_path: Path) -> None:
    auszug = berater.kontext(
        zustand={"jahr": 3, "biom": "Coastal Grove", "bevoelkerung": 24,
                 "lager": {"Meat": 40}, "unbekanntes_feld": "wird nicht mitgenommen"},
        nahrung={"reichweite_sekunden": 340.0, "warnung": "reicht nicht"},
        auswahl={"angebot": [{"de": "Pilzführer", "en": "Fungal Guide",
                              "seltenheit": "Epic", "guete": 0.98,
                              "bild": "C:/foto.png"}]},
    )
    assert auszug["siedlung"]["jahr"] == 3
    assert "unbekanntes_feld" not in auszug["siedlung"]
    assert auszug["auswahl"][0]["en"] == "Fungal Guide"
    # Das Bildfeld wird nicht einmal übernommen.
    assert "bild" not in auszug["auswahl"][0]


def test_kein_bild_geht_hinaus() -> None:
    """Die Zusage der Spec, geprüft statt gehofft."""
    with pytest.raises(ValueError, match="Bild"):
        berater.pruefe_auszug({"auswahl": {"screenshot": "abc"}})
    with pytest.raises(ValueError, match="Bildpfad"):
        berater.pruefe_auszug({"quelle": "C:/Users/Joni/foto.png"})


def test_ein_zu_grosser_auszug_wird_abgewiesen() -> None:
    with pytest.raises(ValueError, match="Zeichen"):
        berater.pruefe_auszug({"lager": {f"Ware{i}": "x" * 100 for i in range(300)}})


def test_frage_setzt_die_richtigen_einstellungen() -> None:
    client = FalscherClient()
    antwort = berater.frage({"siedlung": {"jahr": 1}}, client=client, regeln="REGELN")

    gesehen = client.gesehen
    assert gesehen["model"] == "claude-opus-5"
    assert gesehen["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in json.dumps(gesehen)     # gibt es auf Opus 5 nicht
    assert gesehen["max_tokens"] == berater.MAX_TOKENS
    assert gesehen["system"][0]["text"] == "REGELN"
    assert gesehen["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert antwort.text.startswith("Nimm die Räucherei")


def test_eine_anstehende_wahl_hebt_den_aufwand() -> None:
    """Eine Nahrungsfrage braucht kein tiefes Nachdenken, eine Wahl schon."""
    lage = FalscherClient()
    berater.frage({"siedlung": {}}, client=lage, regeln="x")
    wahl = FalscherClient()
    berater.frage({"siedlung": {}}, client=wahl, regeln="x", wahl_steht_an=True)

    assert lage.gesehen["output_config"]["effort"] == berater.AUFWAND_LAGE
    assert wahl.gesehen["output_config"]["effort"] == berater.AUFWAND_WAHL
    assert lage.gesehen["output_config"]["effort"] != wahl.gesehen["output_config"]["effort"]


def test_die_kosten_stehen_dabei() -> None:
    antwort = berater.frage({"siedlung": {}}, client=FalscherClient(), regeln="x")
    # 2300 Eingabe zu 5 $/1M, 150 Ausgabe zu 25 $/1M -> rund 1,5 Cent.
    assert 1.0 < antwort.kosten_cent < 2.0
    assert antwort.zwischenspeicher_gelesen == 1800


def test_fehlende_anmeldung_ist_kein_absturz() -> None:
    anthropic = pytest.importorskip("anthropic")
    httpx = pytest.importorskip("httpx")

    antwort = httpx.Response(401, request=httpx.Request("POST", "https://api.anthropic.com"))
    fehler = anthropic.AuthenticationError("nein", response=antwort, body=None)
    with pytest.raises(berater.KeinZugang, match="ANTHROPIC_API_KEY"):
        berater.frage({"siedlung": {}}, client=FalscherClient(fehler=fehler), regeln="x")


def test_kein_netz_sagt_dass_der_rest_weiterlaeuft() -> None:
    anthropic = pytest.importorskip("anthropic")

    fehler = anthropic.APIConnectionError(request=None)
    with pytest.raises(RuntimeError, match="ohne Netz weiter"):
        berater.frage({"siedlung": {}}, client=FalscherClient(fehler=fehler), regeln="x")


def test_das_modul_laesst_sich_ohne_das_sdk_einlesen(monkeypatch) -> None:
    """Alles außer dem einen Reiter läuft ohne `anthropic`.

    Eine `except`-Klausel braucht ihre Klasse zur Laufzeit -- fehlt das SDK,
    treten vier Platzhalter an, die nie zutreffen.
    """
    import builtins

    echtes_import = builtins.__import__

    def ohne_anthropic(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("nicht installiert")
        return echtes_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", ohne_anthropic)
    klassen = berater._fehlerklassen()
    assert len(klassen) == 4
    # Der eingesetzte Client funktioniert trotzdem.
    antwort = berater.frage({"siedlung": {}}, client=FalscherClient(), regeln="x")
    assert antwort.text
    # Und ohne Client kommt ein Satz, der sagt, was zu tun ist.
    with pytest.raises(berater.KeinZugang, match="pip install anthropic"):
        berater.frage({"siedlung": {}}, regeln="x")
