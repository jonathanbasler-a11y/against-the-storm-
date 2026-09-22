"""Wo der Spielstand liegt.

Diese Suche stand bisher nur im Diagnosewerkzeug. Damit musste jeder andere
Einstieg -- `ats-watch`, die Kommandozeile -- den Pfad wissen, obwohl er
herauszufinden ist. Also steht sie jetzt hier, einmal.

Windows ist der Regelfall (AppData/LocalLow). Unter Linux laeuft das Spiel im
Proton-Praefix, und dort liegt derselbe Pfad noch einmal unter
`steamapps/compatdata/<appid>/pfx/drive_c/users/steamuser`.

Nur Standardbibliothek. Es wird nichts geoeffnet, nur nachgesehen, was
existiert.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

SAVE_SUBPATH = Path("AppData") / "LocalLow" / "Eremite Games" / "Against the Storm"

# Steam-AppID von Against the Storm, fuer Proton-Praefixe unter Linux.
PROTON_APPID = "1336490"


def candidate_dirs() -> list[Path]:
    """Mutmassliche Speicherorte, plattformabhaengig, ohne Existenzpruefung."""
    out: list[Path] = []
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        out.append(Path(userprofile) / SAVE_SUBPATH)
    out.append(Path.home() / SAVE_SUBPATH)

    if platform.system() != "Windows":
        # Proton/Wine: das Spiel liegt im Windows-Praefix.
        for steam_root in (
            Path.home() / ".steam" / "steam",
            Path.home() / ".local" / "share" / "Steam",
            Path.home() / "snap" / "steam" / "common" / ".steam" / "steam",
        ):
            out.append(
                steam_root / "steamapps" / "compatdata" / PROTON_APPID / "pfx"
                / "drive_c" / "users" / "steamuser" / SAVE_SUBPATH
            )
        out.append(Path.home() / ".wine" / "drive_c" / "users"
                   / os.environ.get("USER", "user") / SAVE_SUBPATH)

    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        if str(p) not in seen:
            seen.add(str(p))
            uniq.append(p)
    return uniq


def resolve_dir(explicit: str | None) -> tuple[Path | None, list[dict]]:
    """Der erste existierende Kandidat, plus Protokoll aller Versuche.

    Das Protokoll ist kein Beiwerk: wenn nichts gefunden wird, ist die Liste
    der abgesuchten Pfade die Antwort auf die Frage, warum.
    """
    tried: list[dict] = []
    cands = [Path(explicit).expanduser()] if explicit else candidate_dirs()
    found: Path | None = None
    for c in cands:
        exists = c.is_dir()
        tried.append({"path": str(c), "exists": exists})
        if exists and found is None:
            found = c
    return found, tried


def finde_spielordner(explicit: str | None = None) -> Path | None:
    """Kurzform fuer den Regelfall: den Ordner oder nichts."""
    return resolve_dir(explicit)[0]
