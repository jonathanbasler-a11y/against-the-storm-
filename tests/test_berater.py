"""Tests des Beraters -- ohne echten Aufruf, ohne Geld.

Der Client wird eingesetzt statt gerufen. Geprüft wird das, was dem Projekt
gehört: was hinausgeht, was nicht hinausgehen darf, und was aus einem Fehler
wird.
"""

from __future__ import annotations

import json
import sys
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
        berater.pruefe_auszug({"lager": {f"Ware{i}": "x" * 100
                                         for i in range(berater.MAX_ZEICHEN // 50)}})


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


# --------------------------------------------------------------------------
# Der Fehler, der am Spielrechner im Reiter "Rat" stand
#
# Das SDK wirft für eine fehlende Anmeldung kein AuthenticationError,
# sondern ein schlichtes TypeError -- nachgesehen in anthropic 1.7.0,
# _client.py, geworfen aus _validate_headers beim Bauen der Kopfzeilen.
# Es lief deshalb an allen vier except-Zweigen vorbei, und im Fenster stand
# der englische Rohtext statt des Satzes, der weiterhilft.
# --------------------------------------------------------------------------

SDK_WORTLAUT = ('"Could not resolve authentication method. Expected one of '
                'api_key, auth_token, or credentials to be set. Or for one of '
                'the `X-Api-Key` or `Authorization` headers to be explicitly '
                'omitted"')


def test_anmeldefehler_des_sdk_wird_zu_keinzugang() -> None:
    with pytest.raises(berater.KeinZugang, match="ANTHROPIC_API_KEY"):
        berater.frage({"siedlung": {}},
                      client=FalscherClient(fehler=TypeError(SDK_WORTLAUT)), regeln="x")


def test_ein_anderer_typfehler_bleibt_ein_typfehler() -> None:
    """Sonst sähe ein falsches Schlüsselwort wie ein fehlender Schlüssel aus.

    `budget_tokens` ist genau so schon einmal danebengegangen; als
    Anmeldeproblem verkleidet wäre es nicht zu finden gewesen.
    """
    fehler = TypeError("create() got an unexpected keyword argument 'output_config'")
    with pytest.raises(TypeError, match="output_config"):
        berater.frage({"siedlung": {}}, client=FalscherClient(fehler=fehler), regeln="x")


def test_client_ohne_anmeldung_wirft_keinzugang(monkeypatch) -> None:
    """Ältere SDK-Fassungen prüfen schon beim Anlegen, neuere erst beim Senden."""
    import types as _types

    modul = _types.ModuleType("anthropic")

    def Anthropic(*args, **kwargs):
        raise TypeError(SDK_WORTLAUT)

    modul.Anthropic = Anthropic
    monkeypatch.setitem(sys.modules, "anthropic", modul)
    with pytest.raises(berater.KeinZugang, match="ant auth login"):
        berater._client()


# --------------------------------------------------------------------------
# Ist überhaupt eine Anmeldung da? -- gefragt, bevor jemand fragt
#
# Am Spielrechner stand die Fehlermeldung erst da, nachdem "Fragen" gedrückt
# war. Eine Runde zu spät: das Fenster kann es vorher wissen, ohne eine
# einzige Anfrage zu senden. Gemessen in anthropic 1.7.0 zieht das SDK die
# Anmeldung aus drei Quellen -- api_key, auth_token, credentials --, und
# genau die drei prüft es beim Bauen der Kopfzeilen.
# --------------------------------------------------------------------------


def _sdk(monkeypatch, **felder):
    import types as _types

    modul = _types.ModuleType("anthropic")

    class Anthropic:
        def __init__(self, *args, **kwargs):
            for name, wert in felder.items():
                setattr(self, name, wert)

    modul.Anthropic = Anthropic
    monkeypatch.setitem(sys.modules, "anthropic", modul)


def test_ein_schluessel_zaehlt_als_anmeldung(monkeypatch) -> None:
    _sdk(monkeypatch, api_key="sk-ant-xyz", auth_token=None, _token_cache=None)
    assert berater.anmeldung_gefunden() is True


def test_auch_ein_profil_zaehlt(monkeypatch) -> None:
    """`ant auth login` legt keinen Schlüssel ab, sondern einen Zwischenspeicher."""
    _sdk(monkeypatch, api_key=None, auth_token=None, _token_cache=object())
    assert berater.anmeldung_gefunden() is True


def test_ohne_jede_quelle_ist_keine_da(monkeypatch) -> None:
    _sdk(monkeypatch, api_key=None, auth_token=None, _token_cache=None)
    assert berater.anmeldung_gefunden() is False


def test_ein_werfendes_sdk_heisst_keine_anmeldung(monkeypatch) -> None:
    import types as _types

    modul = _types.ModuleType("anthropic")

    def Anthropic(*args, **kwargs):
        raise TypeError('"Could not resolve authentication method … api_key …"')

    modul.Anthropic = Anthropic
    monkeypatch.setitem(sys.modules, "anthropic", modul)
    assert berater.anmeldung_gefunden() is False


def test_ohne_sdk_laesst_es_sich_nicht_sagen(monkeypatch) -> None:
    """Nicht False -- das wäre eine Behauptung über etwas Ungeprüftes."""
    import builtins

    echt = builtins.__import__

    def ohne(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("kein anthropic")
        return echt(name, *args, **kwargs)

    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.setattr(builtins, "__import__", ohne)
    assert berater.anmeldung_gefunden() is None


def test_nicht_gefundene_felder_gehen_mit(tmp_path: Path) -> None:
    """`lager: {}` heißt entweder leer oder nicht gefunden.

    Am 22.09.2026 kam genau das aus einem Spielstand mit vollem Lagerhaus.
    Ein leeres Lager als Tatsache weiterzugeben, wäre eine Behauptung über
    etwas Ungeprüftes — die Liste der fehlenden Felder gehört daneben.
    """
    auszug = berater.kontext(zustand={
        "jahr": 1, "biom": "Royal Woodlands", "lager": {}, "gebaeude": 0,
        "nicht_gefunden": ["storage", "buildings"]})
    assert auszug["siedlung"]["nicht_gefunden"] == ["storage", "buildings"]


def test_unlesbare_felder_gehen_mit_ihrer_form_mit() -> None:
    form = {"storage": "{[Food Raw] Meat: {amount: int}}"}
    auszug = berater.kontext(zustand={"jahr": 1, "lager": {}, "form_unbekannt": form})
    assert auszug["siedlung"]["form_unbekannt"] == form


def test_vorkommen_der_ganzen_karte_gehen_nicht_mit() -> None:
    """5760 `naturalResources` nach 600 Sekunden sind jeder Baum der Karte.
    Dem Modell diese Zahl als Vorkommen zu geben, wäre eine falsche Angabe."""
    auszug = berater.kontext(zustand={"jahr": 1, "vorkommen": 5760})
    assert "vorkommen" not in auszug["siedlung"]


def test_die_gebaeudeliste_geht_an_den_rat() -> None:
    liste = [{"gebaeude": "Foragers' Camp", "anzahl": 1, "arbeiter": 1}]
    auszug = berater.kontext(zustand={"jahr": 1, "gebaeude": 1, "gebaeude_liste": liste})
    assert auszug["siedlung"]["gebaeude_liste"] == liste


def test_nahrungsketten_und_essbares_gehen_an_den_rat() -> None:
    """Der Reiter „Nahrung" rechnete den Grill aus, der Rat riet zu Küche
    und Paketen -- er hatte die Rechnung nie bekommen."""
    ketten = {
        "ketten": [{"gebaeude": "Grill", "gebaeude_de": "Grill", "produkt": "Skewers",
                    "produkt_de": "Fleischspieße",
                    "einsatz": [{"menge": 2, "ware": "Insekten", "ware_en": "Insects"}],
                    "gewinn": 25.0, "faktor": 6.0, "engpass": "Insekten",
                    "reichweite_plus_sekunden": 180, "durchlaeufe": 1.0,
                    "saettigung_rein": 5, "saettigung_raus": 30, "sekunden": 120,
                    "engpass_en": "Insects"}] * 5,
        "essbar_im_lager": [{"ware": "Eggs", "ware_de": "Eier", "menge": 14.0,
                             "saettigung": 1.0}],
    }
    auszug = berater.kontext(zustand={"jahr": 1}, ketten=ketten)
    rat = auszug["nahrung_rat"]
    assert len(rat["ketten"]) == 3
    assert rat["ketten"][0]["gebaeude"] == "Grill" and rat["ketten"][0]["faktor"] == 6.0
    assert "saettigung_rein" not in rat["ketten"][0]
    assert rat["essbar_im_lager"][0]["ware_de"] == "Eier"


def test_bauplaene_ruf_und_auftraege_gehen_an_den_rat() -> None:
    zustand = {"jahr": 1, "bauplaene_ungebaut": ["Grill"],
               "ruf_quellen": {"Zufriedenheit": 0.07}, "ruf_je_volk": {"Foxes": 0.07},
               "auftraege": {"aktiv": [], "zur_wahl": [{"name": "Beaver Influx"}]}}
    siedlung = berater.kontext(zustand=zustand)["siedlung"]
    for feld in ("bauplaene_ungebaut", "ruf_quellen", "ruf_je_volk", "auftraege"):
        assert siedlung[feld] == zustand[feld]


def test_der_systemtext_sagt_was_als_nahrung_zaehlt() -> None:
    text = berater.systemtext()
    assert "essbar_im_lager" in text
    assert "bauplaene_ungebaut" in text and "auftraege" in text


# --------------------------------------------------------------------------
# QA-Runde 3 (23.09.2026): Anbindung
# --------------------------------------------------------------------------


class Abgebrochen(FalscherClient):
    def __init__(self, grund: str, text: str = ""):
        super().__init__(text=text)
        self.grund = grund

    def create(self, **kwargs):
        antwort = super().create(**kwargs)
        antwort.stop_reason = self.grund
        if not self.text:
            antwort.content = []
        return antwort


def test_nachdenken_und_antwort_haben_platz() -> None:
    """`max_tokens` deckt Nachdenken und Antwort zusammen. 2000 reichten bei
    einer Grundsteinwahl auf hohem Aufwand nicht."""
    client = FalscherClient()
    berater.frage({"siedlung": {}}, client=client, regeln="x", wahl_steht_an=True)
    assert client.gesehen["max_tokens"] >= 16000


def test_eine_abgeschnittene_antwort_sagt_das() -> None:
    antwort = berater.frage({"siedlung": {}}, client=Abgebrochen("max_tokens", "Nimm die"),
                            regeln="x")
    assert "Nimm die" in antwort.text and "abgeschnitten" in antwort.text


def test_eine_ablehnung_sagt_das() -> None:
    antwort = berater.frage({"siedlung": {}}, client=Abgebrochen("refusal"), regeln="x")
    assert "abgelehnt" in antwort.text.lower()
    assert antwort.text != "Keine Antwort erhalten."


def test_die_kosten_rechnen_den_zwischenspeicher_ein() -> None:
    """Schreiben kostet 1,25-fach, Lesen 0,1-fach -- beides fehlte."""
    ohne = berater.Antwort("", "claude-opus-5", eingabe_token=1000, ausgabe_token=0)
    mit = berater.Antwort("", "claude-opus-5", eingabe_token=1000, ausgabe_token=0,
                          zwischenspeicher_gelesen=10_000, zwischenspeicher_geschrieben=2000)
    assert mit.kosten_cent == pytest.approx(
        ohne.kosten_cent + (10_000 * 0.1 + 2000 * 1.25) * 5.0 / 1e6 * 100)


def test_echte_daten_passen_in_den_auszug() -> None:
    """Mit 60 Waren, 63 Bauplänen und 15 Aufträgen lag der Auszug bei
    16 700 von 20 000 Zeichen -- eine große Siedlung, und jede Frage wäre
    gescheitert. Nullmengen gehen nicht mit, lange Listen werden gekappt."""
    zustand = {
        "jahr": 5,
        "lager": {f"Ware {i}": (0 if i % 2 else i) for i in range(120)},
        "bauplaene_ungebaut": [f"Ein recht langer Gebäudename {i}" for i in range(200)],
        "gebaeude_liste": [{"gebaeude": f"Gebäude {i}", "anzahl": 1, "arbeiter": 2}
                           for i in range(120)],
    }
    auszug = berater.kontext(zustand=zustand)
    berater.pruefe_auszug(auszug)
    assert all(v for v in auszug["siedlung"]["lager"].values())
    assert len(auszug["siedlung"]["bauplaene_ungebaut"]) <= 80
    assert berater.MAX_ZEICHEN >= 40_000


def test_die_bauplanwahl_aus_dem_spielstand_geht_mit() -> None:
    wahl = {"angebot": ["Foragers' Camp", "Smokehouse"], "neu_wuerfeln": 1, "joker": False}
    auszug = berater.kontext(zustand={"jahr": 1, "bauplan_wahl": wahl})
    assert auszug["siedlung"]["bauplan_wahl"] == wahl


def test_der_systemtext_verbietet_erfundene_bedienschritte() -> None:
    """„Pakete öffnest du im Hauptlager … ‚Öffnen'" -- am Spielrechner
    geprüft: das gibt es nicht."""
    text = " ".join(berater.systemtext().split())      # Zeilenumbrüche egal
    assert "Bedienschritte" in text
    assert "noch zu öffnen" in text
    assert "fehlt" in text and "bauplan_wahl" in text


def test_das_wissen_zur_lage_geht_mit_und_ersetzt_die_blosse_lagerliste() -> None:
    wissen = {"waren": [{"ware": "Pack of Provisions", "menge": 5, "essbar": False,
                         "kategorie": "Packs"}],
              "gebaeude": {"Field Kitchen": {"status": "baubar"}},
              "trends": {"fallend": [{"ware": "Eggs", "rate_je_minute": -6.0}], "steigend": []}}
    auszug = berater.kontext(zustand={"jahr": 1, "lager": {"Pack of Provisions": 5}},
                             wissen=wissen)
    assert auszug["waren"] == wissen["waren"]
    assert auszug["gebaeude_wissen"] == wissen["gebaeude"]
    assert auszug["trends"] == wissen["trends"]
    assert "lager" not in auszug["siedlung"]            # nicht doppelt


def test_der_systemtext_nennt_die_mechanik_mit_herkunft() -> None:
    text = berater.systemtext()
    assert "## Mechanik" in text and "Herkunft" in text
    assert "gebaeude_wissen" in text and "trends" in text


def test_eine_grosse_siedlung_mit_wissen_passt_in_den_auszug() -> None:
    """60 Waren mit Eigenschaften und 80 Gebäude mit Erzeugnissen lagen bei
    48 000 Zeichen -- über der Grenze, und jede Frage wäre gescheitert."""
    wissen = {
        "waren": [{"ware": f"Ware {i}", "ware_de": f"Ware {i}", "menge": 10,
                   "kategorie": "Food Raw", "essbar": True, "saettigung": 1.0,
                   "verkaufswert": 2.5, "kaufwert": 5.0} for i in range(60)],
        "gebaeude": {f"Gebäude {i}": {"status": "baubar", "zweck": "x" * 120,
                                      "arbeitsplaetze": 2, "kosten": {"Planks": 5},
                                      "erzeugnisse": [{"ware": "Skewers", "sterne": 1}] * 8}
                     for i in range(80)}}
    auszug = berater.kontext(zustand={"jahr": 1}, wissen=wissen)
    berater.pruefe_auszug(auszug)
    assert len(auszug["gebaeude_wissen"]) <= berater.GEBAEUDE_GRENZE
