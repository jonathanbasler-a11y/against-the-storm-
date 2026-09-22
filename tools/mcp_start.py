#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Starter fuer den MCP-Server.

Claude startet den Server als eigenen Prozess, mit einem Arbeitsverzeichnis
und einem PYTHONPATH, die niemand bestimmt hat. Dieses Skript findet seinen
eigenen Ort und legt das Paket selbst in den Pfad -- damit die Konfiguration
nur den Befehl braucht und keine Umgebungsvariablen.

    python tools/mcp_start.py
    python tools/mcp_start.py --pruefen
    python tools/mcp_start.py --save-dir "D:/woanders/Against the Storm"
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ats_assistant.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
