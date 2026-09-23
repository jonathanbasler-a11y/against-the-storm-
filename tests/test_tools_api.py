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
    assert kette["durchlaeufe"] == 8.4             # 42 Fleisch, 5 je Durchlauf
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
