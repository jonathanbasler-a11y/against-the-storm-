"""Die neue Version holen und das Fenster neu starten -- ohne Konsole.

Anlass (24.09.2026): Das Fenster startet per Verknuepfung, aber fuer jedes
Update brauchte es noch `git pull` in PowerShell und einen Neustart. Einmal
lief danach das alte Programm weiter, und die Bauplanwahl wurde nicht
gelesen, obwohl der Fehler laengst behoben war.

`git pull --ff-only`: nur vorspulen, nie zusammenfuehren. Ist lokal etwas
geaendert, bricht git ab und sagt warum -- und genau das steht dann im
Fenster. Neue Python-Pakete holt das nicht.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ZEITGRENZE_S = 60


def _git(args: list[str], repo: Path, run) -> subprocess.CompletedProcess:
    return run(["git", *args], cwd=str(repo), capture_output=True, text=True,
               timeout=ZEITGRENZE_S,
               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def aktualisieren(repo: Path = REPO, run=subprocess.run, which=shutil.which) -> dict:
    """`git pull --ff-only` im Projektordner. Wirft nie."""
    repo = Path(repo)
    if which("git") is None:
        return {"ok": False, "neu": False,
                "text": "git ist nicht installiert oder nicht im PATH."}
    if not (repo / ".git").exists():
        return {"ok": False, "neu": False,
                "text": f"{repo} ist kein git-Ordner -- aktualisieren geht nur dort."}
    try:
        vorher = _git(["rev-parse", "HEAD"], repo, run).stdout.strip()
        zug = _git(["pull", "--ff-only"], repo, run)
        if zug.returncode != 0:
            meldung = (zug.stderr or zug.stdout or "").strip()
            return {"ok": False, "neu": False,
                    "text": "git pull ging nicht: " + (meldung or f"Code {zug.returncode}")}
        nachher = _git(["rev-parse", "HEAD"], repo, run).stdout.strip()
    except subprocess.TimeoutExpired:
        return {"ok": False, "neu": False,
                "text": f"git pull brauchte länger als {ZEITGRENZE_S} s -- Netz?"}
    except OSError as exc:
        return {"ok": False, "neu": False, "text": f"git ließ sich nicht starten: {exc}"}
    neu = bool(nachher) and nachher != vorher
    return {"ok": True, "neu": neu, "stand": nachher[:7],
            "text": (f"Neue Version geladen ({nachher[:7]})." if neu
                     else f"Schon aktuell ({nachher[:7]}).")}


def neu_starten(popen=subprocess.Popen) -> None:
    """Dasselbe Programm noch einmal -- unter der Verknuepfung ist das
    `pythonw.exe ats-gui.pyw`, also wieder ohne Konsole."""
    popen([sys.executable, *sys.argv], cwd=str(REPO))
