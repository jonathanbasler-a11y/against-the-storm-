#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eine Verknüpfung zum Fenster anlegen -- Desktop und Startmenü.

    python tools\\verknuepfung.py
    python tools\\verknuepfung.py --nur-desktop
    python tools\\verknuepfung.py --testen      # Fenster einmal direkt starten

Warum ein Skript statt ein paar Zeilen PowerShell: am Spielrechner lief
`(Get-Command python).Source` ohne Fehler durch, und die Verknüpfung tat
trotzdem nichts. `Get-Command` findet unter Windows oft den Platzhalter aus
dem Microsoft Store (`…\\WindowsApps\\python.exe`) statt des echten Pythons
unter `…\\Programs\\Python\\Python312\\`. Hier fragt das *laufende* Python nach
seinem Ort -- das ist genau das, mit dem `python tools\\lage.py` funktioniert.

Nur Standardbibliothek. Die Pfade gehen als Umgebungsvariablen an
PowerShell, nicht als eingebauter Text: so stört weder ein Leerzeichen noch
ein `$` im Pfad.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STARTER = REPO / "ats-gui.pyw"
NAME = "ATS Assistent"

# Namen fuer [Environment]::GetFolderPath -- "Desktop" folgt auch einem
# Desktop, den OneDrive verschoben hat; "Programs" ist das Startmenü.
ORTE = {"Desktop": "Desktop", "Startmenü": "Programs"}

_PS = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$d = [Environment]::GetFolderPath($env:ATS_ORT)
$p = Join-Path $d ($env:ATS_NAME + '.lnk')
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($p)
$s.TargetPath = $env:ATS_ZIEL
$s.Arguments = $env:ATS_ARGS
$s.WorkingDirectory = $env:ATS_ORDNER
$s.Description = 'Against the Storm - Assistent'
$s.Save()
Write-Output $p
"""


def pythonw_neben(interpreter: str | Path) -> Path | None:
    """`pythonw.exe` im Ordner des Interpreters -- oder None."""
    kandidat = Path(interpreter).resolve().parent / "pythonw.exe"
    return kandidat if kandidat.exists() else None


def anlegen(pythonw: Path, ort: str, run=subprocess.run) -> Path:
    """Eine Verknüpfung an einem Ort anlegen; liefert ihren Pfad."""
    umgebung = dict(os.environ,
                    ATS_ORT=ORTE[ort], ATS_NAME=NAME, ATS_ZIEL=str(pythonw),
                    ATS_ARGS=f'"{STARTER}"', ATS_ORDNER=str(REPO))
    ergebnis = run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS],
        env=umgebung, capture_output=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    ausgabe = (ergebnis.stdout or b"").decode("utf-8", errors="replace").strip()
    if ergebnis.returncode != 0 or not ausgabe:
        fehler = (ergebnis.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"PowerShell meldete: {fehler or 'nichts'}")
    return Path(ausgabe.splitlines()[-1])


def main(argv: list[str] | None = None, plattform: str = sys.platform,
         interpreter: str = sys.executable, run=subprocess.run) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--nur-desktop", action="store_true",
                    help="nur auf dem Desktop, nicht im Startmenü")
    ap.add_argument("--testen", action="store_true",
                    help="das Fenster einmal direkt mit pythonw starten")
    args = ap.parse_args(argv)

    if not plattform.startswith("win"):
        print("Verknüpfungen legt dieses Skript nur unter Windows an. "
              "Anderswo: python ats-gui.pyw")
        return 1
    pythonw = pythonw_neben(interpreter)
    if pythonw is None:
        print(f"Neben {interpreter} liegt kein pythonw.exe. Mit python.exe bliebe "
              "eine Konsole offen -- deshalb keine Verknüpfung. Python von "
              "python.org installiert? Dann dieses Skript mit genau dem starten.")
        return 1

    print(f"Python:  {pythonw}")
    print(f"Starter: {STARTER}")
    orte = ["Desktop"] if args.nur_desktop else list(ORTE)
    angelegt = 0
    for ort in orte:
        try:
            pfad = anlegen(pythonw, ort, run=run)
        except Exception as exc:
            print(f"{ort}: nicht angelegt -- {exc}")
            continue
        print(f"{ort}: {pfad}")
        angelegt += 1
    if angelegt:
        print(f"\nDoppelklick auf „{NAME}“ startet das Fenster ohne Konsole. "
              "Rechtsklick darauf → „An Taskleiste anheften“ legt es unten ab.")
    if args.testen:
        subprocess.Popen([str(pythonw), str(STARTER)], cwd=str(REPO))
        print("Fenster gestartet -- wenn es nicht erscheint, zeigt "
              "`python ats-gui.pyw` in PowerShell den Grund.")
    return 0 if angelegt == len(orte) else 1


if __name__ == "__main__":
    raise SystemExit(main())
