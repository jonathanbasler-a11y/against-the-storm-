"""Phase 3: den Auswahlbildschirm lesen.

Gemessen am 22.09.2026: die angebotenen Grundsteine stehen nicht im
Spielstand, auch nicht als Text. Das Spiel wuerfelt sie aus einem Keim neu.
Damit ist der Bildschirm noetig -- nicht als erste Wahl, sondern als einzige.

Das Leitprinzip bleibt: das Sehen passiert lokal und deterministisch. Es geht
kein Bild an ein Modell. Was dieses Modul liefert, sind Namen und Zahlen.

Drei Stufen, jede einzeln ersetzbar:

    aufnehmen   Bildschirm oder Fenster in eine PNG-Datei
    erkenne     Text mit seinen Kaestchen aus dem Bild
    lies        Text -> belegte Namen (ueber namen_match)

Fuer jede Stufe gibt es mehrere Wege und einen Notausgang. Fehlt die
Texterkennung, laesst sich der gelesene Text von Hand uebergeben; fehlt die
Aufnahme, ein Bildschirmfoto aus der Zwischenablage. Der Rest der Kette
funktioniert dann trotzdem -- eine fehlende Abhaengigkeit legt nicht das
Ganze still.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import threading
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


def im_eigenen_lauf(fabrik):
    """Eine Koroutine ausfuehren, auch wenn schon eine Schleife laeuft.

    `asyncio.run()` wirft in einer laufenden Ereignisschleife. Genau dort
    landet die Texterkennung aber: unter dem MCP-Server sind die Werkzeuge
    Aufrufe innerhalb der Schleife, und aus der Oberflaeche kommen sie aus
    einem Arbeits-Thread. Ohne diesen Umweg bricht `read_choice` in dem
    Moment ab, in dem es zum ersten Mal wirklich den Bildschirm liest --
    dem einen Pfad, den der Prueflauf nicht erreicht.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(fabrik())          # keine Schleife, direkter Weg

    # Eine Schleife laeuft. Ein eigener Thread bekommt seine eigene.
    ergebnis: dict = {}

    def lauf() -> None:
        try:
            ergebnis["wert"] = asyncio.run(fabrik())
        except BaseException as exc:          # der Fehler darf nicht verschwinden
            ergebnis["fehler"] = exc

    t = threading.Thread(target=lauf, name="ats-ocr", daemon=True)
    t.start()
    t.join()
    if "fehler" in ergebnis:
        raise ergebnis["fehler"]
    return ergebnis.get("wert")


@dataclass(frozen=True)
class Zeile:
    """Ein erkannter Textschnipsel mit seinem Ort im Bild."""
    text: str
    x: float = 0.0
    y: float = 0.0
    breite: float = 0.0
    hoehe: float = 0.0
    guete: float | None = None      # was die Erkennung selbst dazu sagt

    @property
    def mitte_x(self) -> float:
        return self.x + self.breite / 2


# --------------------------------------------------------------------------
# Was ist da?
# --------------------------------------------------------------------------


def _hat(modul: str) -> bool:
    try:
        __import__(modul)
        return True
    except Exception:
        return False


# Die Texterkennung von Windows gibt es unter zwei Namen. Gemessen auf PyPI
# am 22.09.2026, nicht erinnert:
#
#   winsdk 1.0.0b10 (2023)        Python 3.8-3.12, ein Paket
#   winrt-Windows.* 3.2.1         Python 3.9-3.13, aufgeteilt
#
# Die Modulpfade sind bis auf den Stamm gleich. Wer auf 3.13 aktualisiert,
# verliert `winsdk` -- ohne etwas geaendert zu haben. Also beide.
OCR_STAEMME = ("winsdk", "winrt")

WINRT_PAKETE = ("winrt-Windows.Media.Ocr", "winrt-Windows.Graphics.Imaging",
                "winrt-Windows.Storage", "winrt-Windows.Globalization")


def _ocr_herkunft() -> str | None:
    """Welcher der beiden Namensraeume da ist -- das aeltere zuerst.

    `winsdk` gewinnt bei Gleichstand, weil es das getestete ist; `winrt` ist
    der Weg nach vorn und der einzige ab 3.13.
    """
    for stamm in OCR_STAEMME:
        if _hat(stamm):
            return stamm
    return None


def _ocr_befehl() -> str:
    """Der Installationsbefehl, der auf *dieser* Python-Fassung etwas findet."""
    if sys.version_info >= (3, 13):
        return "pip install " + " ".join(WINRT_PAKETE)
    return "pip install winsdk"


def verfuegbar() -> dict:
    """Welche Wege offenstehen -- und welche fehlen, mit dem Befehl dazu.

    Eine Fehlermeldung, die nur sagt, dass etwas fehlt, kostet den Nutzer
    eine Suche. Hier steht, was zu tun waere.
    """
    windows = sys.platform.startswith("win")
    return {
        "plattform": sys.platform,
        "aufnahme": {
            "mss": _hat("mss"),
            "pillow": _hat("PIL"),
            "gdi": windows,             # ctypes gegen die Windows-API
        },
        "erkennung": {
            "herkunft": _ocr_herkunft() if windows else None,
            "winsdk": windows and _hat("winsdk"),
            "winrt": windows and _hat("winrt"),
            "pytesseract": _hat("pytesseract") and bool(shutil.which("tesseract")),
        },
        "rat": _rat(windows),
    }


def _rat(windows: bool) -> str:
    if windows and _ocr_herkunft() is None:
        return (f"Fuer die Texterkennung: {_ocr_befehl()}. Das nutzt die "
                "Texterkennung, die in Windows schon eingebaut ist -- lokal, "
                "ohne Konto, ohne Netz.")
    if not windows and not _hat("pytesseract"):
        return "Fuer die Texterkennung: pip install pytesseract, dazu das Programm tesseract."
    return "Alles da."


# --------------------------------------------------------------------------
# Aufnehmen
# --------------------------------------------------------------------------


def neuer_bildpfad() -> Path:
    """Je Aufnahme eine eigene Datei: ein zweites Lesen, waehrend das erste
    noch wartet, ueberschrieb sonst dessen Bild."""
    fd, name = tempfile.mkstemp(prefix="ats-auswahl-", suffix=".png")
    import os
    os.close(fd)
    return Path(name)


def aufnehmen(ziel: Path | str | None = None, fenster: str | None = None) -> Path:
    """Ein Bildschirmfoto ablegen und den Pfad liefern.

    `fenster` waehlt unter Windows ein Fenster nach Titel; ohne Angabe wird
    der ganze Bildschirm genommen. Das Spiel laeuft im Vollbild, deshalb ist
    das der Regelfall.
    """
    ziel = Path(ziel) if ziel else Path(tempfile.gettempdir()) / "ats-auswahl.png"
    ziel.parent.mkdir(parents=True, exist_ok=True)

    if _hat("mss"):
        import mss                                     # type: ignore
        import mss.tools                               # type: ignore
        with mss.mss() as sct:
            schirm = sct.monitors[1]
            bild = sct.grab(schirm)
            mss.tools.to_png(bild.rgb, bild.size, output=str(ziel))
        return ziel

    if sys.platform.startswith("win"):
        return _aufnehmen_powershell(ziel)

    raise RuntimeError(
        "Keine Aufnahme moeglich. Entweder `pip install mss`, oder ein "
        "Bildschirmfoto von Hand ablegen und mit --bild uebergeben.")


_PS_AUFNAHME = r"""
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
$bmp.Save("{ziel}", [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"""


def _aufnehmen_powershell(ziel: Path) -> Path:
    """Ohne Zusatzpaket: Windows bringt die Bildschirmaufnahme selbst mit."""
    skript = _PS_AUFNAHME.replace("{ziel}", str(ziel).replace("\\", "\\\\"))
    # Unter pythonw hat der Aufrufer keine Konsole; ohne CREATE_NO_WINDOW
    # oeffnet Windows fuer PowerShell eine -- und die landete im Foto.
    ergebnis = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", skript],
        capture_output=True, text=True, timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if ergebnis.returncode != 0 or not ziel.exists():
        raise RuntimeError(f"Aufnahme fehlgeschlagen: {ergebnis.stderr.strip()[:300]}")
    return ziel


# --------------------------------------------------------------------------
# Erkennen
# --------------------------------------------------------------------------


def erkenne(bild: Path | str, sprache: str = "de") -> list[Zeile]:
    """Text aus dem Bild, mit Ort. Leere Liste heisst: nichts gelesen."""
    bild = Path(bild)
    if not bild.exists():
        raise FileNotFoundError(bild)
    stamm = _ocr_herkunft() if sys.platform.startswith("win") else None
    if stamm:
        return _erkenne_windows(bild, sprache, stamm)
    if _hat("pytesseract") and shutil.which("tesseract"):
        return _erkenne_tesseract(bild, sprache)
    raise RuntimeError(_rat(sys.platform.startswith("win")))


def _erkenne_windows(bild: Path, sprache: str, stamm: str = "winsdk") -> list[Zeile]:
    """Die Texterkennung, die in Windows eingebaut ist.

    Lokal, ohne Konto, ohne Netz -- und damit das einzige, was zum
    Leitprinzip der Spec passt, ohne ein weiteres Programm zu verlangen.

    `stamm` ist `winsdk` oder `winrt`. Die Modulpfade dahinter sind gleich;
    nur der Stamm wechselt, deshalb `import_module` statt vier festen
    `from`-Zeilen.
    """
    from importlib import import_module

    def hol(pfad: str, *namen: str):
        modul = import_module(f"{stamm}.windows.{pfad}")
        return [getattr(modul, n) for n in namen]

    (Language,) = hol("globalization", "Language")
    (BitmapDecoder,) = hol("graphics.imaging", "BitmapDecoder")
    (OcrEngine,) = hol("media.ocr", "OcrEngine")
    FileAccessMode, StorageFile = hol("storage", "FileAccessMode", "StorageFile")

    async def lauf() -> list[Zeile]:
        datei = await StorageFile.get_file_from_path_async(str(bild.resolve()))
        strom = await datei.open_async(FileAccessMode.READ)
        decoder = await BitmapDecoder.create_async(strom)
        bitmap = await decoder.get_software_bitmap_async()
        maschine = (OcrEngine.try_create_from_language(Language(sprache))
                    or OcrEngine.try_create_from_user_profile_languages())
        if maschine is None:
            raise RuntimeError(
                f"Windows hat keine Texterkennung fuer '{sprache}' installiert. "
                "Einstellungen > Zeit und Sprache > Sprache > Optionen > "
                "Texterkennung nachinstallieren.")
        ergebnis = await maschine.recognize_async(bitmap)
        zeilen: list[Zeile] = []
        for zeile in ergebnis.lines:
            worte = list(zeile.words)
            if not worte:
                continue
            links = min(w.bounding_rect.x for w in worte)
            oben = min(w.bounding_rect.y for w in worte)
            rechts = max(w.bounding_rect.x + w.bounding_rect.width for w in worte)
            unten = max(w.bounding_rect.y + w.bounding_rect.height for w in worte)
            zeilen.append(Zeile(zeile.text, links, oben, rechts - links, unten - oben))
        return zeilen

    return im_eigenen_lauf(lauf)


def _erkenne_tesseract(bild: Path, sprache: str) -> list[Zeile]:
    import pytesseract                                   # type: ignore
    from PIL import Image                                # type: ignore

    code = {"de": "deu", "en": "eng"}.get(sprache, sprache)
    daten = pytesseract.image_to_data(Image.open(bild), lang=code,
                                      output_type=pytesseract.Output.DICT)
    nach_zeile: dict[tuple, list[int]] = {}
    for i, text in enumerate(daten["text"]):
        if not (text or "").strip():
            continue
        schluessel = (daten["block_num"][i], daten["par_num"][i], daten["line_num"][i])
        nach_zeile.setdefault(schluessel, []).append(i)
    zeilen: list[Zeile] = []
    for indizes in nach_zeile.values():
        text = " ".join(daten["text"][i] for i in indizes)
        links = min(daten["left"][i] for i in indizes)
        oben = min(daten["top"][i] for i in indizes)
        rechts = max(daten["left"][i] + daten["width"][i] for i in indizes)
        unten = max(daten["top"][i] + daten["height"][i] for i in indizes)
        guete = sum(float(daten["conf"][i]) for i in indizes) / len(indizes) / 100
        zeilen.append(Zeile(text, links, oben, rechts - links, unten - oben, guete))
    return zeilen


# --------------------------------------------------------------------------
# Zusammensetzen
# --------------------------------------------------------------------------


def sortiere_nach_karten(zeilen: list[Zeile]) -> list[Zeile]:
    """Von links nach rechts, so wie die Karten stehen.

    Die Reihenfolge ist nicht Zierrat: der Spieler sagt "die linke", und die
    Auskunft muss dieselbe meinen.
    """
    return sorted(zeilen, key=lambda z: (z.mitte_x, z.y))
