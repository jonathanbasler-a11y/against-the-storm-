"""MCP-Server: die Hülle um tools_api.

Die Werkzeuge selbst stehen in `tools_api` und sind ohne MCP aufrufbar und
testbar. Hier steht nur die Anbindung -- Schemata, Namen, Weiterreichen.

    uv run python -m ats_assistant.mcp_server --save-dir "%USERPROFILE%\\AppData\\LocalLow\\Eremite Games\\Against the Storm"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from . import tools_api

log = logging.getLogger(__name__)

STANDARD_SAVE_DIR = (
    Path(os.environ.get("USERPROFILE", Path.home()))
    / "AppData" / "LocalLow" / "Eremite Games" / "Against the Storm"
)


def werkzeuge(save_dir: Path, runs_dir: Path, db: Path) -> list[dict]:
    """Die Werkzeugliste nach SPEC.md Phase 4, mit ihren Schemata."""
    return [
        {
            "name": "get_state",
            "description": ("Aktueller Zustand der Siedlung aus dem Spielstand: Jahr, "
                            "Jahreszeit, Bevölkerung, Feindseligkeit, Ungeduld, Reputation, "
                            "Lagerbestand, Grundsteine. Zahlen und Namen, keine Zeitreihen."),
            "inputSchema": {"type": "object", "properties": {}},
            "handler": lambda **kw: tools_api.get_state(save_dir, runs_dir),
        },
        {
            "name": "read_choice",
            "description": ("Aktueller Auswahlbildschirm (Grundsteine, Baupläne). "
                            "Kommt aus Phase 3 und ist noch nicht gebaut."),
            "inputSchema": {"type": "object", "properties": {}},
            "handler": lambda **kw: tools_api.read_choice(),
        },
        {
            "name": "query_kb",
            "description": ("Nachschlag in der Wissensbasis. Nimmt deutsche und englische "
                            "Namen. Liefert bei Waren auch Sättigung, Brenndauer und "
                            "Handelswerte aus den Spieldaten."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name, deutsch oder englisch"},
                    "entity": {"type": "string",
                               "description": "optional: resource, building, cornerstone"},
                },
                "required": ["name"],
            },
            "handler": lambda name, entity=None, **kw: tools_api.query_kb(name, entity, db),
        },
        {
            "name": "food_forecast",
            "description": ("Nahrungsreichweite. Reine Arithmetik aus der Zeitreihe des "
                            "Spielstands, kein Modell beteiligt."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "jahreszeit_sekunden": {
                        "type": "number",
                        "description": "Länge der laufenden Jahreszeit in Spielzeitsekunden, "
                                       "falls bekannt -- bestimmt die Warnschwelle",
                    },
                },
            },
            "handler": lambda jahreszeit_sekunden=None, **kw: tools_api.food_forecast(
                runs_dir, jahreszeit_sekunden=jahreszeit_sekunden),
        },
        {
            "name": "impatience_forecast",
            "description": ("Ungeduldsvorhersage. Das Modell ist an drei Messintervallen "
                            "geprüft: Zuwachs je Spielzeitsekunde, Abzug von 1,0 je "
                            "überschrittenem ganzen Reputationspunkt."),
            "inputSchema": {
                "type": "object",
                "properties": {"sekunden": {"type": "number", "default": 300}},
            },
            "handler": lambda sekunden=300.0, **kw: tools_api.impatience_forecast(
                runs_dir, sekunden=sekunden),
        },
        {
            "name": "log_event",
            "description": "Freitextnotiz in den laufenden Lauf schreiben.",
            "inputSchema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            "handler": lambda text, **kw: tools_api.log_event(text, runs_dir),
        },
        {
            "name": "analyze_runs",
            "description": ("Die letzten n abgeschlossenen Läufe gegenüberstellen: was "
                            "unterschied gewonnene von verlorenen."),
            "inputSchema": {
                "type": "object",
                "properties": {"n": {"type": "integer", "default": 10}},
            },
            "handler": lambda n=10, **kw: tools_api.analyze_runs(n, save_dir, runs_dir),
        },
    ]


async def serve(save_dir: Path, runs_dir: Path, db: Path) -> None:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    liste = werkzeuge(save_dir, runs_dir, db)
    nach_name = {w["name"]: w for w in liste}
    server = Server("ats-assistant")

    @server.list_tools()
    async def _list() -> list[Tool]:
        return [Tool(name=w["name"], description=w["description"],
                     inputSchema=w["inputSchema"]) for w in liste]

    @server.call_tool()
    async def _call(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        werkzeug = nach_name.get(name)
        if werkzeug is None:
            return [TextContent(type="text", text=json.dumps(
                {"fehler": f"Unbekanntes Werkzeug: {name}"}, ensure_ascii=False))]
        try:
            ergebnis = werkzeug["handler"](**(arguments or {}))
        except Exception as exc:  # ein Werkzeugfehler darf den Server nicht beenden
            log.exception("Werkzeug %s ist gescheitert", name)
            ergebnis = {"fehler": f"{type(exc).__name__}: {exc}"}
        return [TextContent(type="text", text=json.dumps(ergebnis, ensure_ascii=False,
                                                         indent=2, default=str))]

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-dir", default=str(STANDARD_SAVE_DIR))
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--db", default="kb.sqlite")
    ap.add_argument("--log-level", default="INFO")
    ap.add_argument("--list-tools", action="store_true",
                    help="Werkzeuge auflisten und beenden, ohne MCP zu starten")
    args = ap.parse_args(argv)

    Path("logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(Path("logs") / "mcp_server.log", encoding="utf-8")],
    )

    if args.list_tools:
        for w in werkzeuge(Path(args.save_dir), Path(args.runs_dir), Path(args.db)):
            print(f"{w['name']:<22} {w['description']}")
        return 0

    asyncio.run(serve(Path(args.save_dir), Path(args.runs_dir), Path(args.db)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
