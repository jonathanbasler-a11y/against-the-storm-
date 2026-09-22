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

# Claude Desktop startet den Server mit einem Arbeitsverzeichnis, das
# niemand bestimmt hat. Ein relatives "kb.sqlite" zeigt dann irgendwohin --
# und weil `kb.connect` eine fehlende Datenbank anlegt, entsteht dort eine
# leere. Der Server laeuft, antwortet auf jede Frage "nichts gefunden", und
# nichts sagt einem, warum. Deshalb werden relative Pfade gegen das
# Projektverzeichnis aufgeloest.
def _projektwurzel() -> Path | None:
    wurzel = Path(__file__).resolve().parents[2]
    return wurzel if (wurzel / "pyproject.toml").exists() else None


def aufloesen(pfad: Path | str) -> Path:
    """Relative Pfade gegen das Projekt, nicht gegen das Arbeitsverzeichnis."""
    p = Path(pfad)
    if p.is_absolute():
        return p
    if p.exists():
        return p.resolve()
    wurzel = _projektwurzel()
    return (wurzel / p) if wurzel else p.resolve()


def lage(save_dir: Path, runs_dir: Path, db: Path) -> dict:
    """Was der Server vorfindet -- damit ein leerer Start auffaellt."""
    befund: dict = {
        "spielordner": str(save_dir),
        "spielordner_da": save_dir.is_dir(),
        "mitschriften": str(runs_dir),
        "mitschriften_da": len(list(runs_dir.glob("*.jsonl"))) if runs_dir.is_dir() else 0,
        "wissensbasis": str(db),
        "wissensbasis_da": db.exists(),
    }
    if db.exists():
        from . import kb
        conn = kb.connect(db)
        try:
            abdeckung = kb.coverage(conn)
            befund["namen"] = sum(abdeckung["name_map"].values())
            befund["tabellen"] = {k: v for k, v in abdeckung["tabellen"].items() if v}
        finally:
            conn.close()
    fehlt = []
    if not befund["spielordner_da"]:
        fehlt.append("Spielordner nicht gefunden -- mit --save-dir angeben.")
    if not befund["wissensbasis_da"]:
        fehlt.append("Keine Wissensbasis. Erst `build_kb.py seed` und `namen --write`.")
    elif not befund.get("namen"):
        fehlt.append("Wissensbasis ohne Namen -- `build_kb.py namen --write` fehlt.")
    if not befund["mitschriften_da"]:
        fehlt.append("Keine Mitschriften. Ohne sie bleiben Vorhersagen stumm; "
                     "`ats-watch` legt sie an.")
    befund["fehlt"] = fehlt
    return befund


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
                            "Liest den Bildschirm lokal, gleicht gegen die belegten "
                            "deutschen Namen ab und liefert Namen und Zahlen -- nie "
                            "ein Bild."),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "bild": {"type": "string",
                             "description": "Pfad zu einem Bildschirmfoto; ohne Angabe "
                                            "wird eines aufgenommen"},
                    "text": {"type": "array", "items": {"type": "string"},
                             "description": "bereits gelesene Kartentitel, "
                                            "falls keine Texterkennung da ist"},
                },
            },
            "handler": lambda bild=None, text=None, **kw: tools_api.read_choice(
                bild=bild, text=text, db=db, aufnehmen=bild is None and not text),
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
            "name": "food_advice",
            "description": ("Was gegen den Nahrungsmangel zu bauen wäre: jedes Rezept "
                            "gegen den Lagerbestand gerechnet, nach gewonnener Sättigung "
                            "sortiert. Ergänzung zur Werkzeugliste der Spec."),
            "inputSchema": {"type": "object", "properties": {}},
            "handler": lambda **kw: tools_api.food_advice(runs_dir, db),
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
    ap.add_argument("--pruefen", action="store_true",
                    help="jedes Werkzeug einmal aufrufen und zeigen, was es sagt")
    args = ap.parse_args(argv)

    save_dir = aufloesen(args.save_dir)
    runs_dir = aufloesen(args.runs_dir)
    db = aufloesen(args.db)

    protokoll = aufloesen("logs")
    protokoll.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(protokoll / "mcp_server.log", encoding="utf-8")],
    )

    if args.list_tools:
        for w in werkzeuge(save_dir, runs_dir, db):
            print(f"{w['name']:<22} {w['description']}")
        return 0

    if args.pruefen:
        return _pruefen(save_dir, runs_dir, db)

    befund = lage(save_dir, runs_dir, db)
    log.info("Start mit %s", json.dumps(befund, ensure_ascii=False, default=str))
    for satz in befund["fehlt"]:
        log.warning("%s", satz)

    asyncio.run(serve(save_dir, runs_dir, db))
    return 0


# Womit ein Werkzeug beim Pruefen aufgerufen wird. Ohne das faende der
# Lauf nur heraus, dass query_kb einen Namen braucht -- was im Schema steht.
PRUEFARGUMENTE: dict[str, dict] = {
    "query_kb": {"name": "Holz"},
    # Ohne Text wuerde read_choice ein Bildschirmfoto aufnehmen. Beim
    # Pruefen geht es um die Kette dahinter, nicht um den Bildschirm.
    "read_choice": {"text": ["PILZFÜHRER"]},
}

# Was beim Pruefen nicht aufgerufen wird, weil es schreibt.
UEBERSPRUNGEN = {
    "log_event": "schreibt in die Mitschrift, deshalb nicht im Prueflauf",
}


def _pruefen(save_dir: Path, runs_dir: Path, db: Path) -> int:
    """Jedes Werkzeug einmal aufrufen, bevor der Server in Claude haengt.

    Ein Server, der laeuft und auf alles "nichts gefunden" antwortet, ist
    schwerer zu finden als einer, der gar nicht startet. Deshalb dieser
    Lauf: er zeigt, was jedes Werkzeug jetzt gerade sagen wuerde.
    """
    befund = lage(save_dir, runs_dir, db)
    print("Was der Server vorfindet:")
    print(f"  Spielordner   {befund['spielordner']}"
          f"   {'gefunden' if befund['spielordner_da'] else 'NICHT GEFUNDEN'}")
    print(f"  Mitschriften  {befund['mitschriften']}   {befund['mitschriften_da']} Datei(en)")
    print(f"  Wissensbasis  {befund['wissensbasis']}"
          f"   {befund.get('namen', 0)} Namen")
    if befund.get("tabellen"):
        print("                " + ", ".join(f"{k}={v}" for k, v in
                                             sorted(befund["tabellen"].items())))
    if befund["fehlt"]:
        print("\nOffen:")
        for satz in befund["fehlt"]:
            print(f"  - {satz}")

    print("\nWerkzeuge:")
    fehler = 0
    for w in werkzeuge(save_dir, runs_dir, db):
        if w["name"] in UEBERSPRUNGEN:
            print(f"  --      {w['name']:<20} {UEBERSPRUNGEN[w['name']]}")
            continue
        try:
            ergebnis = w["handler"](**PRUEFARGUMENTE.get(w["name"], {}))
        except Exception as exc:
            print(f"  FEHLER  {w['name']:<20} {type(exc).__name__}: {exc}")
            fehler += 1
            continue
        if isinstance(ergebnis, dict) and ergebnis.get("verfuegbar") is False:
            grund = (ergebnis.get("grund") or "").split(".")[0]
            print(f"  stumm   {w['name']:<20} {grund}")
        else:
            umfang = len(ergebnis) if hasattr(ergebnis, "__len__") else "?"
            print(f"  ok      {w['name']:<20} {umfang} Felder")
    if fehler:
        print(f"\n{fehler} Werkzeug(e) mit Fehler -- die gehoeren vor dem Start behoben.")
        return 1
    print("\nKein Werkzeug ist abgestuerzt. 'stumm' heisst: es fehlt eine Eingabe,")
    print("nicht dass etwas kaputt ist -- meist eine zweite Mitschrift.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
