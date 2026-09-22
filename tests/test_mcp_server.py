"""Tests der MCP-Hülle.

Das Paket `mcp` ist hier nicht installiert und soll es auch nicht sein --
die Werkzeuge stehen in `tools_api` und sind ohne MCP testbar. Geprüft wird
deshalb das Stück, das der Hülle gehört: aus der Werkzeugliste eine Funktion
zu bauen, deren Signatur das Schema trägt.

Das ist kein Selbstzweck. mcp 2.x hat die Dekoratoren fallen lassen und
leitet das Schema aus der Signatur ab; 1.x nahm das Schema als Dictionary.
Beide Wege müssen aus derselben Quelle kommen, sonst laufen sie auseinander.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from ats_assistant import mcp_server


def test_signatur_traegt_das_schema() -> None:
    gerufen = {}
    werkzeug = {
        "name": "query_kb",
        "description": "Nachschlag",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "entity": {"type": "string"},
                "n": {"type": "number"},
            },
            "required": ["name"],
        },
        "handler": lambda **kw: gerufen.update(kw) or {"ok": True},
    }
    fn = mcp_server.funktion_aus_schema(werkzeug)
    sig = inspect.signature(fn)

    assert fn.__name__ == "query_kb"
    assert sig.parameters["name"].default is inspect.Parameter.empty
    assert sig.parameters["entity"].default is None
    # Pflichtfelder zuerst: eine Signatur mit Vorgabe vor einer ohne ist ungueltig.
    namen = list(sig.parameters)
    assert namen[0] == "name"
    assert fn.__annotations__["name"] is str
    assert fn.__annotations__["n"] == (float | None)


def test_nicht_gesetzte_felder_werden_nicht_weitergereicht() -> None:
    """None ist nicht dasselbe wie "nicht angegeben".

    Die Werkzeuge haben eigene Vorgaben -- `analyze_runs(n=10)`. Wer None
    durchreicht, ueberschreibt sie mit nichts.
    """
    gerufen: dict = {}

    def handler(**kw):
        gerufen.clear()
        gerufen.update(kw)
        return {}

    fn = mcp_server.funktion_aus_schema({
        "name": "analyze_runs", "description": "",
        "inputSchema": {"type": "object", "properties": {"n": {"type": "number"}}},
        "handler": handler,
    })
    fn(n=None)
    assert gerufen == {}
    fn(n=3)
    assert gerufen == {"n": 3}


def test_jedes_werkzeug_laesst_sich_umbauen(tmp_path: Path) -> None:
    """Keine Werkzeugbeschreibung darf beim Umbau durchfallen."""
    for w in mcp_server.werkzeuge(tmp_path, tmp_path, tmp_path / "kb.sqlite"):
        fn = mcp_server.funktion_aus_schema(w)
        sig = inspect.signature(fn)
        pflicht = set((w["inputSchema"].get("required") or ()))
        for name, p in sig.parameters.items():
            assert (p.default is inspect.Parameter.empty) == (name in pflicht), name


def test_relative_pfade_zeigen_ins_projekt(tmp_path: Path, monkeypatch) -> None:
    """Der Fehler, der den Server stumm gemacht haette.

    Claude startet ihn mit einem fremden Arbeitsverzeichnis. Ein relatives
    "kb.sqlite" wuerde dort eine leere Datenbank anlegen, und der Server
    antwortete auf alles "nichts gefunden".
    """
    monkeypatch.chdir(tmp_path)
    aufgeloest = mcp_server.aufloesen("kb.sqlite")
    assert aufgeloest.is_absolute()
    assert (aufgeloest.parent / "pyproject.toml").exists()
    # Ein absoluter Pfad bleibt, wie er ist.
    assert mcp_server.aufloesen(tmp_path / "x.sqlite") == tmp_path / "x.sqlite"


def test_lage_benennt_was_fehlt(tmp_path: Path) -> None:
    befund = mcp_server.lage(tmp_path / "kein-spiel", tmp_path / "keine-runs",
                             tmp_path / "keine.sqlite")
    text = " ".join(befund["fehlt"])
    assert "Spielordner" in text and "Wissensbasis" in text and "Mitschriften" in text
