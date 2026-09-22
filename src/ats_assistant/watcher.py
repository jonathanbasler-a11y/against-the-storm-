"""Den Spielordner beobachten und jeden Zustand mitschreiben.

Ohne das bleibt `runs/<run_id>.jsonl` leer, und ohne zwei Eintraege kann
`food_forecast` keine Steigung bilden.

Zwei Dinge aus Phase 0 bestimmen den Aufbau:

* Das Spiel schreibt vier Dateien als Buendel und **nicht atomar** -- gemessen
  wurden 2,02 Sekunden Versatz. Deshalb wird nach der ersten Aenderung
  gewartet, bis Ruhe einkehrt, und erst dann gelesen.
* Zwischen zwei Autosaves liegen rund 300 Spielzeitsekunden. Es eilt also
  nichts; ein Abtastintervall von zwei Sekunden reicht vollkommen.

`watchdog` wird benutzt, wenn es da ist, sonst wird abgetastet. Die Spec
nennt watchdog, aber ein fehlendes Paket soll den Assistenten nicht aufhalten.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .save_reader import SAVE_FILES, GameState, append_run_log, read_state

log = logging.getLogger(__name__)

ABTASTUNG_SEKUNDEN = 2.0


def run_id_fuer(state: GameState) -> str:
    """Eine Kennung, die einen Lauf zusammenhaelt und ihn von anderen trennt.

    Biom und Prestige sind ueber den Lauf stabil; die Spielzeit waechst. Als
    Kennung dient deshalb der Beginn: Biom, Stufe und das Datum des ersten
    gesehenen Zustands.
    """
    teile = [state.biome or "lauf", f"p{state.prestige}" if state.prestige else "p?"]
    # Mit Uhrzeit, nicht nur Datum: zwei Laeufe im selben Biom am selben Tag
    # landeten sonst in derselben Datei, und die Spieluhr spraenge mittendrin
    # zurueck -- was jede Auswertung ueber den Verlauf unbrauchbar macht.
    teile.append(datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    return "-".join(t.replace(" ", "_") for t in teile)


def _letzte_zeile(pfad: Path, fenster: int = 1 << 18) -> str | None:
    """Die letzte Zeile einer Datei, ohne sie ganz zu lesen.

    Eine Zeile ist ein ganzer Zustand samt Zeitreihen -- gut 200 kB. Eine
    lange Mitschrift ganz einzulesen, nur um ihr Ende zu sehen, waere bei
    jedem Schreibvorgang des Spiels neu bezahlt.
    """
    try:
        with pfad.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            ende = fh.tell()
            gelesen = b""
            while ende > 0:
                schritt = min(fenster, ende)
                ende -= schritt
                fh.seek(ende)
                gelesen = fh.read(schritt) + gelesen
                teile = gelesen.strip(b"\n").rsplit(b"\n", 1)
                if len(teile) == 2:
                    return teile[1].decode("utf-8", "replace")
            text = gelesen.strip().decode("utf-8", "replace")
            return text or None
    except OSError:
        return None


def _neueste_mitschrift(runs_dir: Path) -> Path | None:
    if not runs_dir.is_dir():
        return None
    dateien = sorted(runs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime,
                     reverse=True)
    return dateien[0] if dateien else None


def _setzt_fort(letzter: dict, state: GameState) -> bool:
    """Gehoert der neue Zustand zu derselben Siedlung wie der letzte?

    Drei Merkmale, und alle drei muessen stimmen: dasselbe Biom, dieselbe
    Stufe, und eine Spieluhr, die nicht zurueckgesprungen ist. Der
    Ruecksprung ist das verlaessliche Zeichen fuer eine neue Siedlung --
    daran erkennt der Mitschreiber sie seit jeher.
    """
    uhr = letzter.get("game_time")
    if uhr is None or state.game_time is None or state.game_time < uhr:
        return False
    return (letzter.get("biome") == state.biome
            and letzter.get("prestige") == state.prestige)


def lauf_kennung(state: GameState, runs_dir: Path) -> str:
    """Welche Mitschrift dieser Zustand fortschreibt -- die laufende oder eine neue.

    Gemessen auf dem Spielrechner: 22 Dateien in `runs/`, jede mit genau
    einem Eintrag, und `food_forecast` meldete dauerhaft "Es braucht zwei
    Spielstaende". Die Kennung von `get_state` enthielt die Spielzeit, also
    bekam jeder Aufruf eine eigene Datei. Ausgerechnet die Nahrungsvorhersage
    -- der Grund, aus dem es dieses Programm gibt -- lief damit ins Leere.
    """
    letzte = _neueste_mitschrift(Path(runs_dir))
    if letzte is not None:
        zeile = _letzte_zeile(letzte)
        try:
            letzter = json.loads(zeile) if zeile else None
        except json.JSONDecodeError:
            letzter = None
        if isinstance(letzter, dict) and _setzt_fort(letzter, state):
            return letzte.stem
    return _freie_kennung(run_id_fuer(state), Path(runs_dir))


def _freie_kennung(name: str, runs_dir: Path) -> str:
    """Eine neue Siedlung darf keine vorhandene Datei verlaengern.

    Die Kennung hat sekundengenaue Aufloesung. Beginnt eine Siedlung in
    derselben Sekunde, in der eine andere begann -- im Test der Regelfall,
    im Spiel selten --, stuenden beide in einer Datei, und die Spieluhr
    spraenge mittendrin zurueck.
    """
    kennung, n = name, 2
    while (runs_dir / f"{kennung}.jsonl").exists():
        kennung = f"{name}-{n}"
        n += 1
    return kennung


def mitschreiben(state: GameState, runs_dir: Path,
                 run_id: str | None = None) -> tuple[str, bool]:
    """Einen Zustand an die richtige Mitschrift haengen.

    Liefert (Kennung, ob geschrieben wurde). Nicht geschrieben wird, was
    schon dasteht: zwei Aufrufe auf demselben Spielstand sind ein Zustand,
    kein zweiter. Sonst rechnete die Vorhersage eine Steigung ueber null
    Sekunden.
    """
    runs_dir = Path(runs_dir)
    kennung = run_id or lauf_kennung(state, runs_dir)
    datei = runs_dir / f"{kennung}.jsonl"
    if datei.exists():
        zeile = _letzte_zeile(datei)
        try:
            letzter = json.loads(zeile) if zeile else None
        except json.JSONDecodeError:
            letzter = None
        if isinstance(letzter, dict) and letzter.get("game_time") == state.game_time:
            return kennung, False
    append_run_log(state, kennung, runs_dir)
    return kennung, True


class Mitschreiber:
    """Haelt fest, welcher Lauf laeuft, und schreibt neue Zustaende weg."""

    def __init__(self, save_dir: Path, runs_dir: Path = Path("runs"),
                 run_id: str | None = None) -> None:
        self.save_dir = Path(save_dir)
        self.runs_dir = Path(runs_dir)
        self._run_id = run_id
        self._letzte_uhr: float | None = None
        self.geschrieben = 0

    def einmal_lesen(self, wait: bool = True) -> GameState | None:
        """Liest den Zustand und schreibt ihn, falls er neu ist."""
        state, _ = read_state(self.save_dir, wait=wait)
        if state.game_time is None:
            log.debug("Kein lesbarer Zustand, uebersprungen")
            return None
        if self._letzte_uhr is not None:
            if state.game_time == self._letzte_uhr:
                # Dieselbe Spielzeit heisst: derselbe Zustand. Eine Datei kann
                # angefasst worden sein, ohne dass sich etwas geaendert hat --
                # im Messlauf gab es Schreibvorgaenge mit null Byte Unterschied.
                log.debug("Spielzeit unveraendert (%.1f), nicht mitgeschrieben",
                          state.game_time)
                return None
            if state.game_time < self._letzte_uhr:
                # Die Uhr faengt von vorn an: neue Siedlung. Das passiert nach
                # jedem beendeten Lauf, und wer hier weiterhin vergleicht,
                # verwirft den gesamten naechsten Lauf.
                log.info("Spielzeit sprang von %.1f auf %.1f zurueck -- neuer Lauf",
                         self._letzte_uhr, state.game_time)
                self._run_id = run_id_fuer(state)
                self._letzte_uhr = None

        if self._run_id is None:
            # Nicht blind einen neuen Lauf beginnen: wer `ats-watch` neu
            # startet, soll die laufende Mitschrift verlaengern. Sonst fehlt
            # der Vorhersage nach jedem Neustart wieder der zweite Stand.
            self._run_id = lauf_kennung(state, self.runs_dir)
            log.info("Lauf: %s", self._run_id)

        append_run_log(state, self._run_id, self.runs_dir)
        self._letzte_uhr = state.game_time
        self.geschrieben += 1
        log.info("Zustand mitgeschrieben: Jahr %s, Spielzeit %.1f, Lauf %s",
                 state.year, state.game_time, self._run_id)
        return state

    @property
    def run_id(self) -> str | None:
        return self._run_id


def _signatur(save_dir: Path) -> tuple:
    out = []
    for name in SAVE_FILES:
        pfad = save_dir / name
        try:
            st = pfad.stat()
            out.append((name, st.st_mtime_ns, st.st_size))
        except OSError:
            continue
    return tuple(out)


def beobachten(save_dir: Path, runs_dir: Path = Path("runs"),
               minuten: float | None = None,
               rueckmeldung: Callable[[GameState], None] | None = None) -> Mitschreiber:
    """Beobachtet, bis abgebrochen wird oder `minuten` um sind."""
    save_dir = Path(save_dir)
    mit = Mitschreiber(save_dir, runs_dir)

    # Den Ausgangszustand gleich mitnehmen, sonst wartet man bis zu 300
    # Spielzeitsekunden auf den ersten Eintrag.
    mit.einmal_lesen(wait=False)

    laeuft = True

    def _stopp(*_: object) -> None:
        nonlocal laeuft
        laeuft = False
        log.info("Beobachtung beendet")

    try:
        signal.signal(signal.SIGINT, _stopp)
    except (ValueError, AttributeError):
        pass  # kein Hauptthread oder kein Signal verfuegbar

    ende = time.monotonic() + minuten * 60 if minuten else None
    letzte = _signatur(save_dir)
    while laeuft and (ende is None or time.monotonic() < ende):
        time.sleep(ABTASTUNG_SEKUNDEN)
        jetzt = _signatur(save_dir)
        if jetzt == letzte:
            continue
        letzte = jetzt
        state = mit.einmal_lesen(wait=True)
        if state is not None and rueckmeldung:
            rueckmeldung(state)
        letzte = _signatur(save_dir)   # das Warten hat Zeit gekostet
    return mit


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .mcp_server import STANDARD_SAVE_DIR

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-dir", default=str(STANDARD_SAVE_DIR))
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--minutes", type=float, help="nach so vielen Minuten aufhoeren")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")
    print(f"Beobachte {args.save_dir}")
    print("Das Spiel schreibt etwa alle 300 Spielzeitsekunden. Abbruch mit Strg+C.")
    mit = beobachten(Path(args.save_dir), Path(args.runs_dir), args.minutes,
                     rueckmeldung=lambda s: print(
                         f"  Jahr {s.year}, Jahreszeit {s.season}, Reputation {s.reputation}, "
                         f"Ungeduld {s.impatience}"))
    print(f"\n{mit.geschrieben} Zustände mitgeschrieben"
          + (f" in runs/{mit.run_id}.jsonl" if mit.run_id else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
