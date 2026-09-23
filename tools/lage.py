#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Lage auf einen Blick, ohne Installation und ohne MCP.

    python tools/lage.py                    Zustand, Nahrung, Ungeduld, Rat
    python tools/lage.py nahrung            alle Ketten, ausfuehrlich
    python tools/lage.py nachschlag Imbiss  ein Name, deutsch oder englisch
    python tools/lage.py form               Aufbau von Lager und Gebaeuden im Save

Wie `tools/mcp_start.py`: das Skript findet seinen eigenen Ort und legt das
Paket selbst in den Suchpfad. `python -m ats_assistant.cli` taete das nicht --
das Paket liegt unter src/ und ist nicht installiert.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ats_assistant.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
