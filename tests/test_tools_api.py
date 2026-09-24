"""Tests der Werkzeuge aus Phase 4 -- ohne MCP, damit sie testbar bleiben."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ats_assistant import kb, tools_api
from ats_assistant.mcp_server import werkzeuge


def buendel(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    save = {
        "time": 8746.9, "year": 13, "season": 0,
        "hostility": {"level": 3, "points": 72, "sources": {}},
        "reputation": 18.0, "reputationToWin": 18,
        "reputationPenalty": 6.6, "reputationPenaltyToLoose": 14,
        "reputationPenaltyPerSec": 0.00425,
        "storage": {"goods": [{"Key": "[Food Raw] Meat", "Value": 42}]},
        "trends": {"goodsCategoriesTrends": {"Food": [97.0] * 180}},
    }
    meta = {
        "gameConditions": {"biome": "Coral Forest", "difficulty": "Prestige 16 Ascension XIII",
                           "races": ["Human", "Beaver"]},
        "reputationPenaltyBonusRate": -0.4,
        "gamesHistory": {"records": [
            {"hasWon": True, "years": 8, "biome": "Coral Forest", "endTimestamp": i,
             "cornerstones": ["Baptism of Fire"]} for i in range(4)
        ] + [
            {"hasWon": False, "years": 5, "biome": "Coral Forest", "endTimestamp": 10 + i,
             "cornerstones": ["Cannibalism"]} for i in range(4)
        ]},
    }
    world = {"population": 13}
    for name, inhalt in (("Save.save", save), ("MetaSave.save", meta), ("WorldSave.save", world)):
        (tmp_path / name).write_text(json.dumps(inhalt), encoding="utf-8")
    return tmp_path


def test_get_state_liefert_zahlen_und_namen_ohne_zeitreihen(tmp_path: Path) -> None:
    """Die Reihen haben 180 Stützstellen je Ware. Die gehören nicht ins Modell."""
    save_dir = buendel(tmp_path / "save")
    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    assert out["jahr"] == 13 and out["biom"] == "Coral Forest"
    assert out["prestige"] == 13 and out["prestige_roh"] == "Prestige 16 Ascension XIII"
    assert out["lager"] == {"Meat": 42}
    assert out["gewonnen"] is True
    assert "category_trends" not in json.dumps(out)
    assert out["reihen_vorhanden"] == ["Food"]        # nur die Namen, nicht die Werte


def test_get_state_schreibt_die_mitschrift(tmp_path: Path) -> None:
    save_dir = buendel(tmp_path / "save")
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, run_id="testlauf", auf_ruhe_warten=False)
    zeilen = (runs / "testlauf.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(zeilen) == 1 and json.loads(zeilen[0])["year"] == 13


def test_get_state_meldet_ein_lager_in_fremder_form(tmp_path: Path) -> None:
    """`lager: {}` ohne jede Meldung kam am Spielrechner aus einem vollen
    Lagerhaus. Gefunden-aber-unlesbar muss mit seiner Form heraus."""
    save_dir = buendel(tmp_path / "save")
    pfad = save_dir / "Save.save"
    save = json.loads(pfad.read_text(encoding="utf-8"))
    save["storage"] = {"goods": {"[Food Raw] Meat": {"amount": 42}}}
    pfad.write_text(json.dumps(save), encoding="utf-8")

    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    assert out["lager"] == {}
    assert "amount" in out["form_unbekannt"]["storage"]
    assert "storage" not in out.get("nicht_gefunden", [])


def test_get_state_ohne_formfehler_hat_kein_feld_dafuer(tmp_path: Path) -> None:
    out = tools_api.get_state(buendel(tmp_path / "save"), tmp_path / "runs",
                              auf_ruhe_warten=False)
    assert "form_unbekannt" not in out


def test_food_forecast_braucht_zwei_spielstaende(tmp_path: Path) -> None:
    save_dir = buendel(tmp_path / "save")
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, run_id="lauf", auf_ruhe_warten=False)
    out = tools_api.food_forecast(runs, run_id="lauf")
    assert out["verfuegbar"] is False and "zwei Spielstände" in out["grund"]


def test_food_forecast_rechnet_mit_zwei_spielstaenden(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    vorher = {"game_time": 1000.0, "category_trends": {"Food": [0.0] * 180}}
    reihe = [0.0] * 180
    reihe[40:70] = [100.0 - 2 * i for i in range(30)]
    nachher = {"game_time": 1300.0, "category_trends": {"Food": reihe}}
    with (runs / "lauf.jsonl").open("w", encoding="utf-8") as fh:
        for z in (vorher, nachher):
            fh.write(json.dumps(z) + "\n")
    out = tools_api.food_forecast(runs, run_id="lauf", jahreszeit_sekunden=180.0)
    assert out["verfuegbar"] is True
    assert out["rate_je_spielzeitsekunde"] == pytest.approx(-0.2)
    assert out["reichweite_sekunden"] == pytest.approx(210.0)


def test_impatience_forecast_aus_der_mitschrift(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "lauf.jsonl").write_text(json.dumps({
        "game_time": 1000.0, "impatience": 13.9, "impatience_to_lose": 14.0,
        "impatience_per_second": 0.00425, "impatience_bonus_rate": -0.4,
    }) + "\n", encoding="utf-8")
    out = tools_api.impatience_forecast(runs, run_id="lauf")
    assert out["verfuegbar"] is True
    assert out["sekunden_bis_verlust"] == pytest.approx(0.1 / 0.00255, rel=1e-6)
    assert "Schwelle" in out["warnung"]


def test_log_event_haengt_an_die_mitschrift(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    out = tools_api.log_event("Erste gefährliche Lichtung geöffnet", runs, run_id="lauf")
    assert out["eintrag"]["typ"] == "notiz"
    assert "Lichtung" in (runs / "lauf.jsonl").read_text(encoding="utf-8")


def test_notizen_stoeren_die_vorhersage_nicht(tmp_path: Path) -> None:
    """Eine Freitextnotiz in derselben Datei darf nicht als Zustand gelesen werden."""
    runs = tmp_path / "runs"
    runs.mkdir()
    with (runs / "lauf.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"game_time": 1000.0, "impatience": 5.0,
                             "impatience_per_second": 0.00425}) + "\n")
    tools_api.log_event("Notiz", runs, run_id="lauf")
    out = tools_api.impatience_forecast(runs, run_id="lauf")
    assert out["jetzt"] == 5.0


def test_analyze_runs_liest_die_laufhistorie(tmp_path: Path) -> None:
    save_dir = buendel(tmp_path / "save")
    out = tools_api.analyze_runs(10, save_dir, tmp_path / "runs")
    assert out["verfuegbar"] is True and out["siege"] == 4 and out["niederlagen"] == 4
    assert out["belastbar"] is True
    namen = [m["name"] for m in out["grundsteine"]]
    assert "Baptism of Fire" in namen


def test_analyze_runs_ohne_historie(tmp_path: Path) -> None:
    out = tools_api.analyze_runs(10, tmp_path, tmp_path / "runs")
    assert out["verfuegbar"] is False and "gamesHistory" in out["grund"]


def test_query_kb_nimmt_deutsch_und_englisch(tmp_path: Path) -> None:
    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    kb.import_goods(conn, [{"page_name": "Jerky", "m_Name": "[Food Processed] Jerky",
                            "eatable": "1", "eatingFullness": "2"}])
    conn.execute("INSERT INTO name_map (en, de, kind, confidence) VALUES (?,?,?,?)",
                 ("Jerky", "Dörrfleisch", "resource", "guessed"))
    conn.commit()
    conn.close()

    aus_de = tools_api.query_kb("Dörrfleisch", db=db)
    assert aus_de["ware"]["save_id"] == "[Food Processed] Jerky"
    assert aus_de["ware"]["eating_fullness"] == 2.0
    aus_save_id = tools_api.query_kb("[Food Processed] Jerky", db=db)
    assert aus_save_id["ware"]["en"] == "Jerky"


def test_query_kb_sagt_wenn_nichts_da_ist(tmp_path: Path) -> None:
    out = tools_api.query_kb("Gibtsnicht", db=tmp_path / "kb.sqlite")
    assert "hinweis" in out


def test_read_choice_ohne_eingabe_sagt_was_fehlt() -> None:
    """Kein Bild, kein Text -- dann steht da, was zu tun waere."""
    out = tools_api.read_choice()
    assert out["verfuegbar"] is False
    assert "Bildschirmfoto" in out["grund"]
    # Und was die Umgebung hergibt, statt nur dass etwas fehlt.
    assert "erkennung" in out["umgebung"] and "rat" in out["umgebung"]


def test_read_choice_bildet_gelesene_titel_auf_belegte_namen_ab(tmp_path: Path) -> None:
    """Der Weg ohne Texterkennung: die gelesenen Titel direkt uebergeben.

    Die zwei Namen standen am 22.09.2026 auf dem Auswahlbildschirm; die
    Grossschrift und der fehlende Umlaut sind das, was eine Texterkennung
    daraus macht.
    """
    from ats_assistant import localization

    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    localization.import_localization(conn, [
        localization.Eintrag("Reward_MushroomSpecialization_Name",
                             "Fungal Guide", "Pilzführer", "effect"),
        localization.Eintrag("Reward_PacksRawProd_Name", "Export Specialization",
                             "Exportspezialisierung", "effect"),
    ])
    conn.execute("INSERT INTO cornerstones (en, rarity, effect_text) "
                 "VALUES ('Fungal Guide', 'Epic', '+1 Pilze je 25 Produktion')")
    conn.commit()
    conn.close()

    out = tools_api.read_choice(text=["PlLZFUHRER", "EXPORTSPEZIALISIERUNG"], db=db)
    assert out["verfuegbar"] is True
    assert [a["en"] for a in out["angebot"]] == ["Fungal Guide", "Export Specialization"]
    assert out["angebot"][0]["de"] == "Pilzführer"
    # Die Wissensbasis haengt dran, was sie weiss.
    assert out["angebot"][0]["seltenheit"] == "Epic"


def test_read_choice_findet_auftraege(tmp_path: Path) -> None:
    """Die drei Namen standen am 23.09.2026 auf „Wähle einen Auftrag aus"."""
    from ats_assistant import localization

    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    localization.import_localization(conn, [
        localization.Eintrag("Order_BeaverInflux_Name", "Beaver Influx",
                             "Biber-Zustrom", "order"),
        localization.Eintrag("Order_AncientArtifacts_Name", "Ancient Artifacts",
                             "Uralte Artefakte", "order"),
        localization.Eintrag("Building_Smokehouse_Name", "Smokehouse",
                             "Räucherei", "building"),
    ])
    conn.close()
    out = tools_api.read_choice(text=["BIBER-ZUSTROM", "URALTE ARTEFAKTE", "Räucherei"],
                                db=db, arten=("order",))
    assert [a["de"] for a in out["angebot"]] == ["Biber-Zustrom", "Uralte Artefakte"]


def test_read_choice_raet_nicht_bei_unlesbarem(tmp_path: Path) -> None:
    """Von Hand getippt und nichts getroffen -- dann sagt das auch der Grund.

    Am Spielrechner stand im Feld `handelsverhandlungen`, und die Ausgabe
    riet zu `pip install winsdk`. Die Frage nach dem Bildschirmfoto passt
    zum Bildweg; wer tippt, hat keines gemacht.
    """
    out = tools_api.read_choice(text=["~~~~~", ""], db=tmp_path / "leer.sqlite")
    assert out["verfuegbar"] is False
    assert out["angebot"] == []
    assert out["quelle"] == "hand"
    assert "eingetippt" in out["grund"]
    assert "Bild" not in out["grund"]


def test_read_choice_nimmt_eine_zeichenkette_als_eine_zeile(tmp_path: Path) -> None:
    """Sonst wird aus einem Namen eine Liste von Buchstaben.

    Das Fenster übergibt immer eine Liste, der MCP-Server und die
    Kommandozeile nicht zwingend.
    """
    out = tools_api.read_choice(text="Pilzführer", db=tmp_path / "leer.sqlite")
    assert out["gelesene_zeilen"] == 1


def test_read_choice_nennt_das_bild_als_quelle(tmp_path: Path, monkeypatch) -> None:
    """Welcher Weg gelaufen ist, muss am Ergebnis stehen -- in beiden Fällen."""
    bild = tmp_path / "schirm.png"
    bild.write_bytes(b"kein echtes PNG")
    monkeypatch.setattr(tools_api.screen, "erkenne", lambda pfad, **kw: [])
    monkeypatch.setattr(tools_api.screen, "sortiere_nach_karten", lambda zeilen: [])
    out = tools_api.read_choice(bild=bild, db=tmp_path / "leer.sqlite")
    assert out["quelle"] == str(bild)
    assert "Bild" in out["grund"]


def test_food_advice_rechnet_gegen_den_lagerbestand(tmp_path: Path) -> None:
    """Die Antwort auf "was soll ich bauen" -- aus Rezepten, Bestand, Verbrauch."""
    save_dir = buendel(tmp_path / "save")
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, run_id="lauf", auf_ruhe_warten=False)

    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    for en, save_id, fuelle in (("Meat", "[Food Raw] Meat", 1.0),
                                ("Jerky", "[Food Processed] Jerky", 2.0)):
        conn.execute("INSERT INTO resources (en, save_id, eatable, eating_fullness) "
                     "VALUES (?,?,1,?)", (en, save_id, fuelle))
    conn.execute(
        "INSERT INTO recipes (id, building, inputs, stars, seconds, product, "
        " product_amount) VALUES (1, 'Smokehouse', ?, 1, 60, 'Jerky', 10)",
        (json.dumps([[{"menge": 5, "ware": "Meat"}]]),))
    conn.execute("INSERT INTO production (product, building, stars) "
                 "VALUES ('Jerky', 'Smokehouse', 3)")
    conn.commit()
    conn.close()

    out = tools_api.food_advice(runs, db, run_id="lauf")
    assert out["verfuegbar"] is True
    kette = out["ketten"][0]
    assert kette["gebaeude"] == "Smokehouse"
    # 42 Fleisch, 5 je Durchlauf: acht ganze. Hier stand 8,4 -- das war der
    # Fehler, den QA-Runde 1 fand, als Erwartung festgeschrieben.
    assert kette["durchlaeufe"] == 8
    assert kette["faktor"] == 4.0
    assert "Smokehouse" in out["empfehlung"]
    # Ein Zustand reicht fuer den Rat, aber nicht fuer den Verbrauch.
    assert out["verbrauch_je_spielzeitsekunde"] is None


def test_food_advice_ohne_mitschrift_sagt_das(tmp_path: Path) -> None:
    out = tools_api.food_advice(tmp_path / "leer", tmp_path / "kb.sqlite")
    assert out["verfuegbar"] is False and "Mitschrift" in out["grund"]


def test_werkzeugliste_entspricht_der_spec(tmp_path: Path) -> None:
    namen = {w["name"] for w in werkzeuge(tmp_path, tmp_path, tmp_path / "kb.sqlite")}
    assert {"get_state", "read_choice", "query_kb", "food_forecast",
            "log_event", "analyze_runs"} <= namen
    # Ergaenzung ueber die Spec hinaus, mit demselben Leitprinzip: gerechnet
    # wird hier, geurteilt im Modell.
    assert "food_advice" in namen


def test_jedes_werkzeug_hat_ein_schema(tmp_path: Path) -> None:
    for w in werkzeuge(tmp_path, tmp_path, tmp_path / "kb.sqlite"):
        assert w["inputSchema"]["type"] == "object"
        assert w["description"]


def test_get_state_sagt_wenn_kein_spielstand_da_ist(tmp_path: Path) -> None:
    """Ein leerer Zustand sieht aus wie eine Siedlung ohne Bevölkerung.

    `read_state` wirft absichtlich nicht, wenn Dateien fehlen -- ein halbes
    Bündel ist besser als ein Absturz. Beim leeren Ordner ist das aber kein
    halbes Bündel, sondern gar keins, und das muss dastehen.
    """
    out = tools_api.get_state(tmp_path / "leer", tmp_path / "runs",
                              auf_ruhe_warten=False)
    assert out["verfuegbar"] is False
    assert "kein Spielstand" in out["grund"]


def test_get_state_meldet_ein_halbes_buendel(tmp_path: Path) -> None:
    save_dir = buendel(tmp_path / "save")
    (save_dir / "MetaSave.save").unlink()
    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    assert out["verfuegbar"] is True            # Save.save reicht fuer den Kern
    assert out["fehlende_dateien"] == ["MetaSave.save"]
    assert out["jahr"] == 13


def test_zwei_aufrufe_landen_in_einer_mitschrift(tmp_path: Path) -> None:
    """Der Fehler vom Spielrechner: 22 Dateien mit je einem Eintrag.

    `get_state` baute die Kennung aus der Spielzeit, also bekam jeder
    Aufruf eine eigene Datei -- und `food_forecast`, das zwei Stände
    braucht, blieb stumm, solange das Fenster lief.
    """
    save_dir = buendel(tmp_path / "save")
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, auf_ruhe_warten=False)

    inhalt = json.loads((save_dir / "Save.save").read_text(encoding="utf-8"))
    inhalt["time"] = 9046.9
    (save_dir / "Save.save").write_text(json.dumps(inhalt), encoding="utf-8")
    zweiter = tools_api.get_state(save_dir, runs, auf_ruhe_warten=False)

    dateien = sorted(runs.glob("*.jsonl"))
    assert len(dateien) == 1, [p.name for p in dateien]
    assert len(dateien[0].read_text(encoding="utf-8").strip().splitlines()) == 2
    assert zweiter["mitschrift"] == dateien[0].stem


def test_zwei_aufrufe_auf_demselben_stand_verlaengern_nichts(tmp_path: Path) -> None:
    save_dir = buendel(tmp_path / "save")
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, auf_ruhe_warten=False)
    tools_api.get_state(save_dir, runs, auf_ruhe_warten=False)
    dateien = sorted(runs.glob("*.jsonl"))
    assert len(dateien) == 1
    assert len(dateien[0].read_text(encoding="utf-8").strip().splitlines()) == 1


def test_nach_zwei_staenden_sagt_die_nahrungsvorhersage_etwas(tmp_path: Path) -> None:
    """Der Weg, der beim Nutzer tot war: lesen, lesen, vorhersagen."""
    save_dir = buendel(tmp_path / "save")
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, auf_ruhe_warten=False)

    inhalt = json.loads((save_dir / "Save.save").read_text(encoding="utf-8"))
    inhalt["time"] = 9046.9
    inhalt["trends"]["goodsCategoriesTrends"]["Food"] = [97.0 - i * 0.1 for i in range(180)]
    (save_dir / "Save.save").write_text(json.dumps(inhalt), encoding="utf-8")
    tools_api.get_state(save_dir, runs, auf_ruhe_warten=False)

    out = tools_api.food_forecast(runs)
    assert out.get("grund") is None, out.get("grund")
    assert out["verfuegbar"] is True


def _auswahl_wissensbasis(db: Path) -> None:
    """Zwei echte Grundsteine, dazu drei Namen, die nur auf dem Bildschirm stehen."""
    from ats_assistant import localization

    conn = kb.connect(db)
    localization.import_localization(conn, [
        localization.Eintrag("Reward_CrystalCathode_Name", "Crystal Cathode",
                             "Kristallkathode", "effect"),
        localization.Eintrag("Reward_TradeHub_Name", "Trade Hub",
                             "Handelsposten", "effect"),
        localization.Eintrag("Effect_Usury_Name", "Usury", "Wucher", "effect"),
        localization.Eintrag("Effect_Fox_Name", "Fox", "Fuchs", "effect"),
        localization.Eintrag("Effect_Beaver_Name", "Beaver", "Biber", "effect"),
    ])
    for en, rarity, text in (
            ("Crystal Cathode", "Legendary", "Produktionsboni in Regenmaschinen …"),
            ("Trade Hub", "Legendary", "Jedes Mal, wenn du Waren verkaufst …")):
        conn.execute("INSERT INTO cornerstones (en, rarity, effect_text) VALUES (?, ?, ?)",
                     (en, rarity, text))
    conn.commit()
    conn.close()


def test_nur_belegte_grundsteine_gelten_als_angebot(tmp_path: Path) -> None:
    """Gemessen am 22.09.2026 an einer offenen Grundsteinwahl.

    Die Aufnahme nimmt den ganzen Bildschirm, also steht neben den zwei
    Karten auch die Oberfläche darin: `Fuchs`, `Biber` -- die Spezies
    oben links -- und `Wucher` mit Güte 0,727, geraten. Alle vier standen
    gleichberechtigt im Angebot. Was eine Karte ist, sagt die
    Wissensbasis: ein Grundstein hat dort Seltenheit und Wirkung.
    """
    db = tmp_path / "kb.sqlite"
    _auswahl_wissensbasis(db)

    out = tools_api.read_choice(
        text=["KRISTALLKATHODE", "HANDELSPOSTEN", "FUCHS", "BIBER", "WUGHER"],
        db=db, arten=("effect",))

    # Belegtes zuerst -- was die Wissensbasis als Grundstein kennt, steht oben.
    assert [a["de"] for a in out["belegt"]] == ["Kristallkathode", "Handelsposten"]
    sonst = [s["de"] for s in out["sonst_gesehen"]]
    assert "Fuchs" in sonst and "Biber" in sonst
    assert [a["de"] for a in out["angebot"][:2]] == ["Kristallkathode", "Handelsposten"]
    assert out["verfuegbar"] is True


def test_eine_karte_ohne_eintrag_faellt_nicht_unter_den_tisch(tmp_path: Path) -> None:
    """Die Wissensbasis kennt 398 Grundsteine bei 2273 Namen.

    „Exportspezialisierung" stand am 22.09. wirklich zur Wahl, ohne in der
    Tabelle zu stehen. Ein harter Filter hätte die Karte verschluckt -- und
    eine fehlende Karte ist schlimmer als eine Spezies daneben. Also
    sortiert, nicht gefiltert.
    """
    db = tmp_path / "kb.sqlite"
    _auswahl_wissensbasis(db)
    out = tools_api.read_choice(text=["FUCHS"], db=db, arten=("effect",))
    assert [a["de"] for a in out["angebot"]] == ["Fuchs"]
    assert out["belegt"] == []
    assert [s["de"] for s in out["sonst_gesehen"]] == ["Fuchs"]
    assert out["verfuegbar"] is True


def test_eine_unsichere_lesung_steht_nicht_im_angebot(tmp_path: Path) -> None:
    """Güte 0,727 ist eine Vermutung über den Text, keine Lesung."""
    db = tmp_path / "kb.sqlite"
    _auswahl_wissensbasis(db)
    out = tools_api.read_choice(text=["KRISTALLKATHODE", "WUCHEX"],
                                db=db, arten=("effect",))
    namen = [a["de"] for a in out["angebot"]]
    assert namen == ["Kristallkathode"]
    assert any(u["de"] == "Wucher" for u in out["unsicher"])


def test_die_lesereihenfolge_bleibt_erhalten(tmp_path: Path) -> None:
    """„Die linke" muss dieselbe bleiben. Beide Karten haben Güte 1,0 --
    ein Sortieren nach Namen hätte sie vertauscht."""
    db = tmp_path / "kb.sqlite"
    _auswahl_wissensbasis(db)
    out = tools_api.read_choice(text=["KRISTALLKATHODE", "HANDELSPOSTEN"],
                                db=db, arten=("effect",))
    assert [a["de"] for a in out["angebot"]] == ["Kristallkathode", "Handelsposten"]

    andersherum = tools_api.read_choice(text=["HANDELSPOSTEN", "KRISTALLKATHODE"],
                                        db=db, arten=("effect",))
    assert [a["de"] for a in andersherum["angebot"]] == ["Handelsposten", "Kristallkathode"]


def test_get_state_nennt_die_gebaeude_nicht_nur_ihre_zahl(tmp_path: Path) -> None:
    """„Weiß der Rat nicht, welche Gebäude ich habe?" -- er wusste nur,
    wie viele."""
    save_dir = buendel(tmp_path / "save")
    pfad = save_dir / "Save.save"
    save = json.loads(pfad.read_text(encoding="utf-8"))
    save["buildings"] = {
        "houses": [{"model": "Beaver House"}, {"model": "Beaver House"}],
        "camps": [{"model": "Foragers' Camp", "workers": [7, 0]}],
        "roads": [{"model": "Road"}]}
    pfad.write_text(json.dumps(save), encoding="utf-8")
    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    assert out["gebaeude"] == 3
    assert out["gebaeude_liste"] == [
        {"gebaeude": "Beaver House", "anzahl": 2, "arbeiter": 0},
        {"gebaeude": "Foragers' Camp", "anzahl": 1, "arbeiter": 1}]


def _mit(save_dir: Path, **felder) -> Path:
    pfad = save_dir / "Save.save"
    save = json.loads(pfad.read_text(encoding="utf-8"))
    save.update(felder)
    pfad.write_text(json.dumps(save), encoding="utf-8")
    return save_dir


def _auftrag(model: str, **felder) -> dict:
    eintrag = {"model": model, "picked": False, "shouldBeFailable": False,
               "timeLeft": 0.0, "isFailed": False, "rewards": [], "picks": [],
               "started": False, "completed": False,
               "objectives": [{"type": 2, "amount": 3, "completed": False}]}
    eintrag.update(felder)
    return eintrag


def test_get_state_ruf_quellen_nennen_nur_das_belegte_sicher(tmp_path: Path) -> None:
    """Index 2 entsprach am Spielrechner genau dem Gewinn der Füchse -- also
    Zufriedenheit. Die anderen drei sind nicht belegt und heißen so."""
    save_dir = _mit(buendel(tmp_path / "save"),
                    gameObjectives={"reputationSources": [1.0, 0.0, 0.5, 0.0]},
                    actors={"racesReputationGains": {"Foxes": 0.5}})
    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    assert out["ruf_quellen"]["Zufriedenheit"] == 0.5
    assert out["ruf_quellen"]["Aufträge (vermutet)"] == 1.0
    assert out["ruf_je_volk"] == {"Foxes": 0.5}


def test_get_state_bauplaene_ungebaut(tmp_path: Path) -> None:
    save_dir = _mit(buendel(tmp_path / "save"),
                    content={"buildings": ["Grill", "Smokehouse", "Beaver House"]},
                    buildings={"workshops": [{"model": "Smokehouse"}]})
    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    assert out["bauplaene_ungebaut"] == ["Beaver House", "Grill"]


def test_get_state_auftraege_aktiv_und_zur_wahl(tmp_path: Path) -> None:
    save_dir = _mit(buendel(tmp_path / "save"), orders={"currentOrders": [
        _auftrag("Order A", picked=True, started=True, rewards=["Planks x10"]),
        _auftrag("Order B", picks=[
            {"model": "Beaver Influx", "failed": False, "rewards": ["Resin x15"]},
            {"model": "Beaver Colony", "failed": False, "rewards": ["Amber x40"]}]),
        _auftrag("Order C", picked=True, completed=True),
        _auftrag("Order D", picked=True, started=True, shouldBeFailable=True,
                 timeLeft=480.0),
        _auftrag("Order E", picked=True, isFailed=True),
        _auftrag("Order F"),                         # weder gewählt noch angeboten
    ]})
    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    auftraege = out["auftraege"]
    assert [a["name"] for a in auftraege["aktiv"]] == ["Order A", "Order D"]
    assert auftraege["aktiv"][0]["belohnungen"] == ["Planks x10"]
    assert "zeitlimit_sekunden" not in auftraege["aktiv"][0]
    assert auftraege["aktiv"][1]["zeitlimit_sekunden"] == 480.0
    # Ein Zähler, kein Fortschritt: ob `amount` Ziel oder Stand ist, ist nicht belegt.
    assert auftraege["aktiv"][0]["ziele"] == [{"typ": 2, "stand": 3, "erledigt": False}]
    assert [a["name"] for a in auftraege["zur_wahl"]] == ["Beaver Influx", "Beaver Colony"]
    assert auftraege["zur_wahl"][1]["belohnungen"] == ["Amber x40"]


def test_food_advice_nennt_was_im_lager_essbar_ist(tmp_path: Path) -> None:
    """Der Rat empfahl am Spielrechner, Vorratspakete zu öffnen. Was essbar
    ist, steht in den Spieldaten -- das soll er bekommen, nicht erraten."""
    save_dir = buendel(tmp_path / "save")
    pfad = save_dir / "Save.save"
    save = json.loads(pfad.read_text(encoding="utf-8"))
    save["storage"]["goods"].append({"Key": "[Packs] Pack of Provisions", "Value": 5})
    pfad.write_text(json.dumps(save), encoding="utf-8")
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, run_id="lauf", auf_ruhe_warten=False)

    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    conn.execute("INSERT INTO resources (en, save_id, eatable, eating_fullness) "
                 "VALUES ('Meat', '[Food Raw] Meat', 1, 1.0)")
    conn.execute("INSERT INTO resources (en, save_id, eatable, eating_fullness) "
                 "VALUES ('Pack of Provisions', '[Packs] Pack of Provisions', 0, NULL)")
    conn.commit()
    conn.close()

    out = tools_api.food_advice(runs, db, run_id="lauf")
    assert out["essbar_im_lager"] == [
        {"ware": "Meat", "ware_de": "Meat", "menge": 42.0, "saettigung": 1.0}]


def test_analyze_runs_liest_metasave_mit_bom(tmp_path: Path) -> None:
    save_dir = buendel(tmp_path / "save")
    pfad = save_dir / "MetaSave.save"
    pfad.write_bytes(b"\xef\xbb\xbf" + pfad.read_bytes())
    out = tools_api.analyze_runs(save_dir=save_dir)
    assert out["verfuegbar"] is True


def test_read_choice_belegt_auftraege(tmp_path: Path) -> None:
    """Aufträge landeten alle unter „meist Oberfläche": `_belegt` suchte sie
    unter den Grundsteinen."""
    from ats_assistant import localization

    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    localization.import_localization(conn, [
        localization.Eintrag("Order_BeaverInflux_Name", "Beaver Influx",
                             "Biber-Zustrom", "order")])
    conn.close()
    out = tools_api.read_choice(text=["BIBER-ZUSTROM"], db=db, arten=("order",))
    assert [a["de"] for a in out["belegt"]] == ["Biber-Zustrom"]


def test_get_state_nennt_wann_das_spiel_gespeichert_hat(tmp_path: Path) -> None:
    """„gerade eben" war die Lesezeit, nicht die Speicherzeit -- auch bei
    einem Spielstand von vor Stunden."""
    import os
    save_dir = buendel(tmp_path / "save")
    alt = 1_700_000_000
    os.utime(save_dir / "Save.save", (alt, alt))
    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    assert out["gespeichert"].startswith("2023-11-14")


def test_bei_doppeltem_deutschem_namen_gilt_der_belegte_eintrag(tmp_path: Path) -> None:
    """„Glücksbringer" steht für zwei englische Einträge; welcher zuerst kam,
    hing an der Tabellenreihenfolge. Ist nur einer als Grundstein belegt,
    gilt der."""
    from ats_assistant import localization

    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    localization.import_localization(conn, [
        localization.Eintrag("Effect_A_Name", "Lucky Charm", "Glücksbringer", "effect"),
        localization.Eintrag("Effect_B_Name", "Lucky Talisman", "Glücksbringer", "effect"),
    ])
    conn.execute("INSERT INTO cornerstones (en, rarity, effect_text) "
                 "VALUES ('Lucky Talisman', 'Rare', '+5 Glück')")
    conn.commit()
    conn.close()
    out = tools_api.read_choice(text=["GLUCKSBRINGER"], db=db)
    assert [a["en"] for a in out["belegt"]] == ["Lucky Talisman"]


# --------------------------------------------------------------------------
# Runde 6 (23.09.2026)
# --------------------------------------------------------------------------


def test_food_advice_kennt_gebautes_und_freigeschaltetes(tmp_path: Path) -> None:
    save_dir = _mit(buendel(tmp_path / "save"),
                    content={"buildings": ["Field Kitchen"]},
                    buildings={"camps": [{"model": "Primitive Forager's Camp"}]})
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, run_id="lauf", auf_ruhe_warten=False)

    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    for en, save_id, fuelle in (("Meat", "[Food Raw] Meat", 1.0),
                                ("Jerky", "[Food Processed] Jerky", 2.0)):
        conn.execute("INSERT INTO resources (en, save_id, eatable, eating_fullness) "
                     "VALUES (?,?,1,?)", (en, save_id, fuelle))
    conn.execute(
        "INSERT INTO recipes (id, building, inputs, stars, seconds, product, product_amount) "
        "VALUES (1, 'Smokehouse', ?, 1, 60, 'Jerky', 10)",
        (json.dumps([[{"menge": 5, "ware": "Meat"}]]),))
    for gebaeude, sterne in (("Smokehouse", 3), ("Field Kitchen", 1)):
        conn.execute("INSERT INTO production (product, building, stars) VALUES ('Jerky',?,?)",
                     (gebaeude, sterne))
    conn.commit()
    conn.close()

    kette = tools_api.food_advice(runs, db, run_id="lauf")["ketten"][0]
    assert kette["gebaeude"] == "Field Kitchen" and kette["status"] == "baubar"


def test_auftraege_zeigen_den_stand_und_kein_leeres_zeitlimit(tmp_path: Path) -> None:
    """Gemessen: `amount` 0 bei „0/2", „0/6", „0/2" im Spiel -- der Stand.
    `timeLeft` 0 bei einem Auftrag ohne laufende Uhr sah aus wie abgelaufen."""
    save_dir = _mit(buendel(tmp_path / "save"), orders={"currentOrders": [
        _auftrag("I Cysts", picked=True, started=True, shouldBeFailable=True, timeLeft=0.0)]})
    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    aktiv = out["auftraege"]["aktiv"][0]
    assert aktiv["ziele"] == [{"typ": 2, "stand": 3, "erledigt": False}]
    assert "zeitlimit_sekunden" not in aktiv


def test_read_choice_nennt_ein_angebot_nur_einmal(tmp_path: Path) -> None:
    """Auftragsübersicht: jeder Name stand in der Seitenleiste und auf der Karte."""
    from ats_assistant import localization

    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    localization.import_localization(conn, [
        localization.Eintrag("Order_IThePurge_Name", "The Purge", "Die Läuterung", "order")])
    conn.close()
    out = tools_api.read_choice(text=["Die Läuterung", "DIE LÄUTERUNG"], db=db, arten=("order",))
    assert [a["de"] for a in out["angebot"]] == ["Die Läuterung"]


def test_get_state_liest_die_bauplanwahl_aus_dem_spielstand(tmp_path: Path) -> None:
    """Gemessen: `reputationRewards.currentPick.options` hatte zwei Einträge,
    als Nahrungssammlerlager und Räucherei zur Wahl standen. Welche zwei
    Schlüssel ein Eintrag hat, zeigte die Messung nicht -- also der Text."""
    save_dir = _mit(buendel(tmp_path / "save"), reputationRewards={
        "currentRerolls": 1, "currentPick": {"isWild": False, "id": 3, "options": [
            {"building": "Foragers' Camp", "cost": 0},
            {"building": "Smokehouse", "cost": 0}]}})
    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    # `id` erkennt eine neue Wahl (Runde 11).
    assert out["bauplan_wahl"] == {"angebot": ["Foragers' Camp", "Smokehouse"],
                                   "neu_wuerfeln": 1, "joker": False, "id": 3}


def test_ohne_offene_bauplanwahl_kein_feld(tmp_path: Path) -> None:
    save_dir = _mit(buendel(tmp_path / "save"), reputationRewards={
        "currentPick": {"isWild": False, "id": 0, "options": []}})
    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    assert "bauplan_wahl" not in out


# --------------------------------------------------------------------------
# Runde 7a: Wissen zur Lage -- Eigenschaften und Trends aus den Spieldaten
# --------------------------------------------------------------------------


def test_lage_wissen_nennt_eigenschaften_der_waren(tmp_path: Path) -> None:
    """„Pakete öffnen" war erfundene Mechanik. Was eine Ware ist, steht in den
    Spieldaten -- das soll mitgehen."""
    save_dir = _mit(buendel(tmp_path / "save"), goods={"goods": {"goods": [
        {"name": "[Packs] Pack of Provisions", "amount": 5},
        {"name": "[Food Raw] Eggs", "amount": 14}]}})
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, run_id="lauf", auf_ruhe_warten=False)
    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    conn.execute("INSERT INTO resources (en, save_id, category, eatable, eating_fullness, "
                 "sell_value) VALUES ('Pack of Provisions', '[Packs] Pack of Provisions', "
                 "'Packs', 0, NULL, 12.5)")
    conn.execute("INSERT INTO resources (en, save_id, category, eatable, eating_fullness) "
                 "VALUES ('Eggs', '[Food Raw] Eggs', 'Food Raw', 1, 1.0)")
    conn.commit()
    conn.close()
    out = tools_api.lage_wissen(runs, db, run_id="lauf")
    waren = {w["ware"]: w for w in out["waren"]}
    assert waren["Pack of Provisions"]["essbar"] is False
    assert waren["Pack of Provisions"]["kategorie"] == "Packs"
    assert waren["Pack of Provisions"]["verkaufswert"] == 12.5
    assert waren["Eggs"]["essbar"] is True and waren["Eggs"]["menge"] == 14


def test_lage_wissen_nennt_was_gebaeude_herstellen(tmp_path: Path) -> None:
    save_dir = _mit(buendel(tmp_path / "save"),
                    content={"buildings": ["Field Kitchen"]},
                    buildings={"camps": [{"model": "Primitive Forager's Camp"}]})
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, run_id="lauf", auf_ruhe_warten=False)
    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    conn.execute("INSERT INTO buildings (en, category, worker_slots, cost) "
                 "VALUES ('Field Kitchen', 'Food Production', 2, '{\"Planks\": 5}')")
    conn.execute("INSERT INTO production (product, building, stars) "
                 "VALUES ('Skewers', 'Field Kitchen', 1)")
    conn.commit()
    conn.close()
    gebaeude = tools_api.lage_wissen(runs, db, run_id="lauf")["gebaeude"]
    assert gebaeude["Field Kitchen"]["erzeugnisse"] == [{"ware": "Skewers", "sterne": 1}]
    assert gebaeude["Field Kitchen"]["arbeitsplaetze"] == 2
    assert gebaeude["Field Kitchen"]["status"] == "baubar"


def test_lage_wissen_ohne_mitschrift_sagt_das(tmp_path: Path) -> None:
    out = tools_api.lage_wissen(tmp_path / "leer", tmp_path / "kb.sqlite")
    assert out["verfuegbar"] is False


def test_log_event_nimmt_art_und_spielzeit(tmp_path: Path) -> None:
    out = tools_api.log_event("Rat: Sammlerlager", tmp_path / "runs", run_id="lauf",
                              art="rat", spielzeit=600.0, jahr=1)
    assert out["eintrag"]["art"] == "rat" and out["eintrag"]["spielzeit"] == 600.0


def test_get_state_liefert_statistik_und_effekte(tmp_path: Path) -> None:
    save_dir = _mit(buendel(tmp_path / "save"),
                    stats={"hungerGained": 3, "leftVillagers": 1,
                           "gladesDiscovered": [{"level": 0}, {"level": 2}]},
                    effects={"perks": {"Frog Newcomer Bonus": {"name": "Frog Newcomer Bonus",
                                                               "stacks": 1, "hidden": False}}})
    out = tools_api.get_state(save_dir, tmp_path / "runs", auf_ruhe_warten=False)
    assert out["statistik"]["hunger"] == 3 and out["lichtungen"] == 2
    assert out["lichtungen_nach_stufe"] == {"0": 1, "2": 1}
    assert out["effekte"]["aktiv"][0]["modell"] == "Frog Newcomer Bonus"


def test_lage_wissen_nennt_deutsche_namen_fuer_bauplan_und_effekte(tmp_path: Path) -> None:
    save_dir = _mit(buendel(tmp_path / "save"),
                    reputationRewards={"currentPick": {"options": [
                        {"building": "Smokehouse", "set": "S"}]}},
                    effects={"perks": {"[Biome] Wood in Woodlands": {
                        "name": "[Biome] Wood in Woodlands", "stacks": 1, "hidden": False}}})
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, run_id="lauf", auf_ruhe_warten=False)
    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    conn.execute("INSERT INTO name_map (en, de, kind, confidence) "
                 "VALUES ('Smokehouse', 'Räucherei', 'building', 'localization')")
    conn.execute("INSERT INTO name_map (en, de, kind, confidence) "
                 "VALUES ('Wood in Woodlands', 'Holz im Königswald', 'effect', 'localization')")
    conn.commit()
    conn.close()
    namen = tools_api.lage_wissen(runs, db, run_id="lauf")["namen_de"]
    assert namen == {"Smokehouse": "Räucherei",
                     "[Biome] Wood in Woodlands": "Holz im Königswald"}


# --------------------------------------------------------------------------
# 23.09.2026: Randleisten, Rezepte beim Nachschlagen, angebotene Baupläne
# --------------------------------------------------------------------------


def test_read_choice_uebergeht_die_randleisten(tmp_path: Path, monkeypatch) -> None:
    from ats_assistant import localization
    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    localization.import_localization(conn, [
        localization.Eintrag("Reward_BedAndBreakfast_Name", "Bed and Breakfast",
                             "Frühstückspension", "effect"),
        localization.Eintrag("Reward_BuildingMaterials_Name", "Building Materials",
                             "Baumaterialien", "effect")])
    for en in ("Bed and Breakfast", "Building Materials"):
        conn.execute("INSERT INTO cornerstones (en, rarity) VALUES (?, 'Epic')", (en,))
    conn.commit()
    conn.close()
    bild = tmp_path / "schirm.png"
    bild.write_bytes(b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR"
                     + (2000).to_bytes(4, "big") + (1125).to_bytes(4, "big") + b"\x08\x02\0\0\0")
    monkeypatch.setattr(tools_api.screen, "erkenne", lambda pfad, **kw: [
        tools_api.screen.Zeile("FRÜHSTÜCKSPENSION", 618, 635, 200, 20),
        tools_api.screen.Zeile("BAUMATERIALIEN", 1737, 408, 130, 15)])
    out = tools_api.read_choice(bild=bild, db=db)
    assert [a["en"] for a in out["angebot"]] == ["Bed and Breakfast"]
    assert out["am_rand_verworfen"] == 1


def _rezept_basis(db: Path) -> None:
    conn = kb.connect(db)
    conn.execute("INSERT INTO buildings (en, worker_slots) VALUES ('Kiln', 2)")
    conn.execute("INSERT INTO name_map (en, de, kind, confidence) "
                 "VALUES ('Kiln', 'Brennofen', 'building', 'localization')")
    conn.execute("INSERT INTO production (product, building, stars, inputs) VALUES "
                 "('Coal', 'Kiln', 3, ?)", (json.dumps([[{"menge": 5, "ware": "Wood"}]]),))
    conn.execute("INSERT INTO production (product, building, stars) VALUES "
                 "('Bricks', 'Kiln', 1)")
    conn.execute("INSERT INTO recipes (building, inputs, stars, product) VALUES "
                 "('Kiln', ?, 1, 'Bricks')",
                 (json.dumps([[{"menge": 3, "ware": "Clay"}, {"menge": 3, "ware": "Stone"}]]),))
    conn.execute("INSERT INTO resources (en, save_id, category) "
                 "VALUES ('Coal', '[Fuel] Coal', 'Fuel')")
    conn.commit()
    conn.close()


def test_nachschlagen_nennt_rezepte_mit_zutaten(tmp_path: Path) -> None:
    db = tmp_path / "kb.sqlite"
    _rezept_basis(db)
    out = tools_api.query_kb("Brennofen", db=db)          # deutsch gesucht
    assert out["gebaeude"]["en"] == "Kiln"
    rezepte = {r["produkt"]: r for r in out["rezepte"]}
    assert rezepte["Coal"]["sterne"] == 3
    assert rezepte["Coal"]["zutaten"] == [[{"menge": 5, "ware": "Wood"}]]
    # Zutaten aus `recipes`, wo `production` keine hat.
    assert rezepte["Bricks"]["zutaten"][0][1] == {"menge": 3, "ware": "Stone"}
    ware = tools_api.query_kb("Coal", db=db)
    assert ware["hergestellt_in"][0]["gebaeude"] == "Kiln"


def test_angebotene_bauplaene_kommen_mit_rezepten_in_den_auszug(tmp_path: Path) -> None:
    save_dir = _mit(buendel(tmp_path / "save"), reputationRewards={"currentPick": {
        "options": [{"building": "Kiln", "set": "S"}]}})
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, run_id="lauf", auf_ruhe_warten=False)
    db = tmp_path / "kb.sqlite"
    _rezept_basis(db)
    gebaeude = tools_api.lage_wissen(runs, db, run_id="lauf")["gebaeude"]
    ofen = gebaeude["Kiln"]
    assert ofen["status"] == "angeboten" and ofen["gebaeude_de"] == "Brennofen"
    assert ofen["rezepte"][0] == {"produkt": "Coal", "sterne": 3,
                                  "zutaten": [[{"menge": 5, "ware": "Wood"}]]}
    from ats_assistant import berater
    wissen = {"gebaeude": {**{f"G{i}": {"status": "steht"} for i in range(60)},
                           "Kiln": ofen}}
    auszug = berater.kontext(zustand={"jahr": 1}, wissen=wissen)
    assert next(iter(auszug["gebaeude_wissen"])) == "Kiln"     # nicht weggekappt



def test_der_bauplanvergleich_kennt_freigeschaltetes(tmp_path: Path) -> None:
    """Am 23.09.2026: Pochwerk mit Ziegeln ★★ angeboten, die Werkstatt (Ziegel
    ★★) war aus dem vorigen Pick schon freigeschaltet, aber nicht gebaut."""
    save_dir = _mit(buendel(tmp_path / "save"),
                    goods={"goods": {"goods": [{"name": "[Mat Raw] Clay", "amount": 58},
                                               {"name": "[Food Raw] Insects", "amount": 3}]}},
                    content={"buildings": ["Workshop"]},
                    buildings={"workshops": [{"model": "Crude Workstation"}]},
                    reputationRewards={"currentPick": {"id": 3, "options": [
                        {"building": "Stamping Mill", "set": "S"},
                        {"building": "Kiln", "set": "S"}]}})
    runs = tmp_path / "runs"
    tools_api.get_state(save_dir, runs, run_id="lauf", auf_ruhe_warten=False)
    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    for produkt, gebaeude, sterne in (("Bricks", "Crude Workstation", 0),
                                      ("Bricks", "Workshop", 2),
                                      ("Bricks", "Stamping Mill", 2),
                                      ("Copper Bar", "Stamping Mill", 2),
                                      ("Coal", "Kiln", 3), ("Jerky", "Kiln", 1)):
        conn.execute("INSERT INTO production (product, building, stars) VALUES (?, ?, ?)",
                     (produkt, gebaeude, sterne))
    conn.execute("INSERT INTO recipes (building, inputs, stars, product) VALUES "
                 "('Stamping Mill', ?, 2, 'Bricks')",
                 (json.dumps([[{"menge": 2, "ware": "Stone"}, {"menge": 3, "ware": "Clay"}]]),))
    conn.execute("INSERT INTO resources (en, save_id, eatable, eating_fullness) VALUES "
                 "('Jerky', '[Food Processed] Jerky', 1, 2.0)")
    conn.execute("INSERT INTO resources (en, save_id) VALUES ('Clay', '[Mat Raw] Clay')")
    conn.commit()
    conn.close()
    vergleich = {v["gebaeude"]: v for v in
                 tools_api.lage_wissen(runs, db, run_id="lauf")["bauplan_vergleich"]}
    muehle = {w["ware"]: w for w in vergleich["Stamping Mill"]["waren"]}
    assert muehle["Bricks"]["besser"] is False
    assert muehle["Bricks"]["bisher"]["gebaeude"] == "Workshop"
    assert muehle["Bricks"]["bisher"]["status"] == "baubar"
    assert muehle["Bricks"]["zutaten"][0]["ware"] == "Clay"          # größter Bestand
    assert muehle["Bricks"]["zutaten"][0]["im_lager"] == 58
    assert muehle["Copper Bar"]["besser"] is True and muehle["Copper Bar"]["bisher"] is None
    assert vergleich["Stamping Mill"]["besser_oder_neu"] == 1
    ofen = {w["ware"]: w for w in vergleich["Kiln"]["waren"]}
    assert ofen["Jerky"]["nahrung"] == 2.0 and vergleich["Kiln"]["nahrung"] == 1
