"""Tests der Kommandozeile.

Der MCP-Server hatte denselben Fehler zweimal: eine Einstiegsfunktion, die
kein Test aufruft. Beim Server hat es der Nutzer gemerkt, hier hätte es
dasselbe gegeben -- also werden die Befehle aufgerufen, nicht nur importiert.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ats_assistant import cli, kb, localization


def kleine_basis(pfad: Path) -> Path:
    conn = kb.connect(pfad)
    localization.import_localization(conn, [
        localization.Eintrag("Good_Wood_Name", "Wood", "Holz", "resource"),
        localization.Eintrag("Building_Smokehouse_Name", "Smokehouse",
                             "Räucherei", "building"),
    ])
    conn.close()
    return pfad


def test_starter_findet_die_einstiegsfunktion() -> None:
    """tools/lage.py importiert genau das hier."""
    assert callable(cli.main)


def test_globale_optionen_gelten_auch_nach_dem_unterbefehl(tmp_path: Path, capsys) -> None:
    """`lage.py nachschlag Holz --db andere.sqlite` muss gehen.

    argparse nimmt Optionen des Hauptparsers sonst nur davor an -- und
    scheitert an einer Stelle, an der niemand einen Fehler erwartet.
    """
    db = kleine_basis(tmp_path / "kb.sqlite")
    assert cli.main(["nachschlag", "Holz", "--db", str(db)]) == 0
    assert "Wood" in capsys.readouterr().out


def test_nachschlag_nimmt_deutsch_und_englisch(tmp_path: Path, capsys) -> None:
    db = kleine_basis(tmp_path / "kb.sqlite")
    cli.main(["--db", str(db), "nachschlag", "Räucherei"])
    deutsch = capsys.readouterr().out
    cli.main(["--db", str(db), "nachschlag", "Smokehouse"])
    englisch = capsys.readouterr().out
    assert "Smokehouse" in deutsch and "Räucherei" in englisch


def test_ohne_spielstand_kommt_ein_satz_statt_lauter_none(tmp_path: Path, capsys) -> None:
    """Sonst stünde da "Jahr None, ?, Prestige None"."""
    db = kleine_basis(tmp_path / "kb.sqlite")
    code = cli.main(["--save-dir", str(tmp_path / "kein-spiel"),
                     "--runs", str(tmp_path / "runs"), "--db", str(db), "--sofort"])
    ausgabe = capsys.readouterr().out
    assert code == 1
    assert "kein Spielstand" in ausgabe
    assert "None" not in ausgabe


def test_nahrung_sagt_woran_es_liegt(tmp_path: Path, capsys) -> None:
    db = kleine_basis(tmp_path / "kb.sqlite")
    assert cli.main(["--runs", str(tmp_path / "leer"), "--db", str(db), "nahrung"]) == 0
    assert "Mitschrift" in capsys.readouterr().out


def test_nahrung_zeigt_die_ketten(tmp_path: Path, capsys) -> None:
    db = tmp_path / "kb.sqlite"
    conn = kb.connect(db)
    for en, save_id, fuelle in (("Meat", "[Food Raw] Meat", 1.0),
                                ("Jerky", "[Food Processed] Jerky", 2.0)):
        conn.execute("INSERT INTO resources (en, save_id, eatable, eating_fullness) "
                     "VALUES (?,?,1,?)", (en, save_id, fuelle))
    conn.execute("INSERT INTO recipes (id, building, inputs, seconds, product, "
                 " product_amount) VALUES (1, 'Smokehouse', ?, 60, 'Jerky', 10)",
                 (json.dumps([[{"menge": 5, "ware": "Meat"}]]),))
    conn.execute("INSERT INTO production (product, building, stars) "
                 "VALUES ('Jerky', 'Smokehouse', 3)")
    conn.commit()
    conn.close()

    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "lauf.jsonl").write_text(
        json.dumps({"game_time": 1000.0, "storage": {"Meat": 40}}) + "\n",
        encoding="utf-8")

    assert cli.main(["--runs", str(runs), "--db", str(db), "nahrung"]) == 0
    ausgabe = capsys.readouterr().out
    assert "Smokehouse" in ausgabe
    assert "Meat" in ausgabe


def _buendel_mit_fremdem_lager(ordner: Path) -> Path:
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "Save.save").write_text(json.dumps({
        "time": 600.0, "year": 1, "season": 2,
        "storage": {"goods": {"[Food Raw] Berries": {"amount": 16}}},
        "mainStorage": {"storedGoods": [{"name": "[Food Raw] Berries", "amount": 16}]},
    }), encoding="utf-8")
    return ordner


def test_lage_sagt_was_nicht_gelesen_wurde(tmp_path: Path, capsys) -> None:
    """Ich hatte am Spielrechner gesagt, `lage.py` zeige die nicht gefundenen
    Felder. Es zeigte sie nicht."""
    db = kleine_basis(tmp_path / "kb.sqlite")
    ordner = _buendel_mit_fremdem_lager(tmp_path / "save")
    cli.main(["--save-dir", str(ordner), "--runs", str(tmp_path / "runs"),
              "--db", str(db), "--sofort"])
    ausgabe = capsys.readouterr().out
    assert "nicht gefunden" in ausgabe                 # MetaSave fehlt: biome u. a.
    assert "nicht lesbar" in ausgabe and "storage" in ausgabe


def test_form_zeigt_den_aufbau_ohne_werte(tmp_path: Path, capsys) -> None:
    ordner = _buendel_mit_fremdem_lager(tmp_path / "save")
    assert cli.main(["form", "--save-dir", str(ordner), "--sofort"]) == 0
    ausgabe = capsys.readouterr().out
    assert "$.storage.goods" in ausgabe and "storedGoods" in ausgabe
    # Schluesselnamen bleiben -- ob das Spiel nach Warennamen ablegt, ist
    # genau die Frage. Die Mengen gehen nicht mit.
    assert "16" not in ausgabe


def test_form_ohne_spielstand_kommt_ein_satz(tmp_path: Path, capsys) -> None:
    assert cli.main(["form", "--save-dir", str(tmp_path / "weg"), "--sofort"]) == 1
    assert "kein spielstand" in capsys.readouterr().out.lower()
