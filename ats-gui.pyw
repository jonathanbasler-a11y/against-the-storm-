#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Starter fuer das Fenster.

Die Endung .pyw ist der Punkt: Windows startet sie mit pythonw.exe, also
ohne Konsolenfenster daneben. Doppelklick genuegt.

Wie tools/mcp_start.py findet das Skript seinen eigenen Ort und legt das
Paket selbst in den Suchpfad -- `python -m ats_assistant.gui` taete das
nicht, das Paket liegt unter src/ und ist nicht installiert.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

try:
    from ats_assistant.gui import main
except ImportError as exc:
    # Ohne Konsole sieht niemand einen Stapelauszug. Also ein Fenster.
    if "tkinter" in str(exc):
        hinweis = ("Diesem Python fehlt tkinter.\n\n"
                   "Python-Installer erneut starten, \"Modify\" waehlen und\n"
                   "\"tcl/tk and IDLE\" ankreuzen.")
    else:
        hinweis = f"Das Paket liess sich nicht laden:\n\n{exc}"
    try:
        import tkinter.messagebox as mb
        import tkinter as tk
        wurzel = tk.Tk()
        wurzel.withdraw()
        mb.showerror("Against the Storm – Assistent", hinweis)
    except Exception:
        print(hinweis, file=sys.stderr)
    raise SystemExit(1)

if __name__ == "__main__":
    raise SystemExit(main())
