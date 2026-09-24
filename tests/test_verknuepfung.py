"""tools/verknuepfung.py: die Verknüpfung zum Fenster.

Am Spielrechner (24.09.2026) liefen die PowerShell-Zeilen mit
`(Get-Command python).Source` fehlerfrei durch, und die Verknüpfung tat
nichts -- vermutlich der Store-Platzhalter statt des echten Pythons.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import verknuepfung  # noqa: E402


def _python(tmp_path: Path, mit_pythonw: bool = True) -> Path:
    ordner = tmp_path / "Python312"
    ordner.mkdir()
    (ordner / "python.exe").write_bytes(b"")
    if mit_pythonw:
        (ordner / "pythonw.exe").write_bytes(b"")
    return ordner / "python.exe"


class FalschesRun:
    def __init__(self):
        self.aufrufe: list[dict] = []

    def __call__(self, befehl, env=None, **kw):
        self.aufrufe.append({"befehl": befehl, "env": env, **kw})
        pfad = f"C:\\Users\\Joni\\{env['ATS_ORT']}\\{env['ATS_NAME']}.lnk"
        return types.SimpleNamespace(returncode=0, stdout=pfad.encode("utf-8"), stderr=b"")


def test_die_verknuepfung_zeigt_auf_pythonw_neben_dem_laufenden_python(tmp_path, capsys):
    run = FalschesRun()
    python = _python(tmp_path)
    assert verknuepfung.main([], plattform="win32", interpreter=str(python), run=run) == 0
    assert [a["env"]["ATS_ORT"] for a in run.aufrufe] == ["Desktop", "Programs"]
    env = run.aufrufe[0]["env"]
    assert env["ATS_ZIEL"] == str(python.resolve().parent / "pythonw.exe")
    assert env["ATS_ARGS"] == f'"{verknuepfung.STARTER}"'          # Leerzeichen-fest
    assert env["ATS_ORDNER"] == str(verknuepfung.REPO)
    # Pfade nie im Befehlstext -- nur als Umgebungsvariablen.
    assert str(verknuepfung.STARTER) not in " ".join(run.aufrufe[0]["befehl"])
    ausgabe = capsys.readouterr().out
    assert "pythonw.exe" in ausgabe and "An Taskleiste anheften" in ausgabe


def test_nur_desktop(tmp_path):
    run = FalschesRun()
    verknuepfung.main(["--nur-desktop"], plattform="win32",
                      interpreter=str(_python(tmp_path)), run=run)
    assert [a["env"]["ATS_ORT"] for a in run.aufrufe] == ["Desktop"]


def test_ohne_pythonw_wird_nichts_angelegt(tmp_path, capsys):
    run = FalschesRun()
    code = verknuepfung.main([], plattform="win32",
                             interpreter=str(_python(tmp_path, mit_pythonw=False)), run=run)
    assert code == 1 and run.aufrufe == []
    assert "kein pythonw.exe" in capsys.readouterr().out


def test_ausserhalb_von_windows_ein_satz(tmp_path, capsys):
    run = FalschesRun()
    assert verknuepfung.main([], plattform="linux", interpreter=str(_python(tmp_path)),
                             run=run) == 1
    assert run.aufrufe == [] and "Windows" in capsys.readouterr().out


def test_ein_fehler_von_powershell_wird_gesagt(tmp_path, capsys):
    def scheitert(befehl, env=None, **kw):
        return types.SimpleNamespace(returncode=1, stdout=b"", stderr=b"Zugriff verweigert")
    code = verknuepfung.main(["--nur-desktop"], plattform="win32",
                             interpreter=str(_python(tmp_path)), run=scheitert)
    assert code == 1 and "Zugriff verweigert" in capsys.readouterr().out
