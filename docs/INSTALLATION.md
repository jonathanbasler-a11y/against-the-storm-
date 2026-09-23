# Herunterladen und einrichten

Von Null auf dem Spielrechner: Windows 11, Python 3.12, *Against the Storm*
1.10.4 mit deutscher Oberfläche. Ein Durchlauf dauert rund zehn Minuten, das
meiste davon wartet auf `pip`.

Wer das Projekt schon hat, braucht nur [Auffrischen](#auffrischen).

---

## 1. Python 3.12

```powershell
python --version
```

Steht dort **3.12** oder höher, weiter zu Schritt 2. Sonst von
[python.org/downloads](https://www.python.org/downloads/) holen und beim
Installieren **„Add python.exe to PATH"** ankreuzen.

Das ist keine Formsache: `pyproject.toml` verlangt `>=3.12`, und unter 3.11
fehlt in vielen Installationen `tkinter` — dann geht das Fenster nicht auf,
ohne zu sagen warum. Ein Test im Projekt (`tests/test_laufzeit.py`) besteht
genau darauf und nennt beide Versionen, wenn es klemmt.

Beim Installieren „tcl/tk and IDLE" **angehakt lassen** — das ist das Fenster.

## 2. Das Projekt holen

```powershell
cd $HOME
git clone https://github.com/jonathanbasler-a11y/against-the-storm-.git
cd against-the-storm-
```

Ohne Git: auf GitHub *Code → Download ZIP*, auspacken, und in den Ordner
wechseln. Zum Auffrischen ist Git allerdings deutlich bequemer.

## 3. Abhängigkeiten

```powershell
python -m pip install -e .
```

Das holt `watchdog` (sieht zu, wann das Spiel schreibt) und `mcp` (für den
Server an Claude Code). Mehr braucht der Grundbetrieb nicht.

Zwei Zusätze, beide **freiwillig**:

```powershell
python -m pip install anthropic     # für den Reiter "Rat"
python -m pip install winsdk        # für "Bildschirm lesen" im Reiter "Auswahl"
```

Beide nutzen die Texterkennung, die in Windows schon eingebaut ist — lokal,
ohne Konto, ohne Netz. Ohne sie bleibt der Handweg: Namen eintippen und
„Abgleichen" drücken.

**Auf Python 3.13 und neuer** gibt es `winsdk` nicht mehr (letzte Fassung
1.0.0b10 von 2023, Wheels bis 3.12). Dort die aufgeteilten Nachfolgepakete:

```powershell
python -m pip install winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging winrt-Windows.Storage winrt-Windows.Globalization
```

Der Assistent nimmt, was da ist, und nennt im Reiter „Auswahl" den Befehl, der
zur laufenden Python-Fassung passt.

## 4. Die Wissensbasis bauen

`kb.sqlite` liegt **nicht** im Repo — sie entsteht aus den Daten der eigenen
Installation. Die Reihenfolge ist nicht beliebig; jeder Schritt braucht den
vorigen.

```powershell
python tools\build_kb.py seed
python tools\build_kb.py namen --write
python tools\build_kb.py status
```

Danach stehen rund **2270 belegte deutsche Namen** drin. Das reicht für Lage,
Nahrungsreichweite, Ungeduld und den Namensabgleich im Auswahlhelfer.

Für Rezepte, Gebäudekosten und Grundsteintexte kommt ein lokaler Wiki-Abzug
dazu:

```powershell
python tools\build_kb.py html  --wiki-dir "C:\Users\Joni\.cursor\wiki\against-the-storm-wiki" --write
python tools\build_kb.py build --wiki-dir "C:\Users\Joni\.cursor\wiki\against-the-storm-wiki"
python tools\build_kb.py status
```

`namen` läuft **vor** `html`: der HTML-Import prüft über die Namenstabelle, ob
ein Seitentitel wirklich ein Gebäude ist. Ohne die Namen landen Rezepte unter
Biomnamen.

Hakt etwas, `kb.sqlite` löschen und neu bauen. Die Mitschriften in `runs/`
sind davon nicht betroffen.

## 5. Starten

```powershell
python ats-gui.pyw
```

Die Endung ist der Punkt: Windows startet `.pyw` mit `pythonw.exe`, also
**ohne Konsolenfenster daneben**. Auf den Desktop legen: Rechtsklick auf
`ats-gui.pyw` → *Senden an* → *Desktop (Verknüpfung erstellen)*.

Fehlt tkinter, sagt der Starter das in einem eigenen kleinen Fenster — ohne
Konsole sähe sonst niemand den Grund. Bleibt es aus anderen Gründen zu, einmal
`python ats-gui.pyw` in PowerShell starten; dort steht es im Klartext.

Der Spielordner wird selbst gefunden
(`%USERPROFILE%\AppData\LocalLow\Eremite Games\Against the Storm`). Liegt er
anderswo:

```powershell
python ats-gui.pyw --save-dir "D:\Pfad\zum\Spielordner"
```

## 6. Der Reiter „Rat" (freiwillig)

Er schickt eine kompakte Lage als JSON an Claude — Zahlen und Namen, **nie ein
Bild**. Voraussetzung ist `anthropic` aus Schritt 3 und eine Anmeldung:

```powershell
setx ANTHROPIC_API_KEY sk-ant-...
```

Danach ein **neues** PowerShell-Fenster öffnen — `setx` wirkt nicht
rückwirkend. Alternativ `ant auth login`; das SDK findet beides von selbst.

Ohne Anmeldung läuft alles andere unverändert weiter, und der Reiter sagt in
einem Satz, was fehlt. „Lage kopieren" legt dieselbe JSON in die
Zwischenablage — die lässt sich in jedes Claude-Fenster einfügen.

Kosten: rund **1,5 Cent je Frage** mit `claude-opus-5`, rund 0,6 Cent mit
`claude-sonnet-5` (oben im Reiter umschaltbar).

---

## Auffrischen

```powershell
cd $HOME\against-the-storm-
git fetch origin
git reset --hard origin/main
```

**`reset --hard`, nicht `pull`.** Die Arbeit kommt per Squash-Merge in `main`;
ein `pull` versucht dann, dieselbe Änderung in zwei Formen zu vereinen, und
hinterlässt Konfliktmarkierungen mitten im Code. Das ist hier schon zweimal
passiert.

Eigene Dateien bleiben unberührt: `kb.sqlite`, `runs/` und `.env` stehen in
`.gitignore`.

Nach einem **Spiel-Update** stimmen womöglich die Namen nicht mehr:

```powershell
python tools\build_kb.py namen --dir "<Verzeichnis mit de_translations.json>"
python tools\build_kb.py namen --dir "<dasselbe>" --write
```

Der erste Aufruf zeigt nur, wie viele Namen sich geändert haben. Widerlegte
Zeilen wandern nach `retired_names` statt gelöscht zu werden.

## Mitschreiben im Hintergrund

Das Fenster schreibt selbst mit, solange es offen ist. Wer ohne Fenster
sammeln will:

```powershell
python -m pip install -e .
ats-watch
```

Eine Siedlung ist **eine** Datei in `runs/`. Wächst die Zahl der Dateien bei
jedem Lesen, ist der Stand älter als der 22.09.2026 — dann auffrischen.

## Wenn etwas klemmt

| Was dasteht | Was es heißt |
|---|---|
| „Es braucht zwei Spielstände" | Noch kein zweiter Zustand. Das Spiel schreibt etwa alle 300 Spielzeitsekunden; nach dem nächsten Mal geht es. Bleibt es stehen, in `runs/` nachsehen: eine Siedlung ist eine Datei |
| „Keine Wissensbasis" | Schritt 4 fehlt |
| „Wissensbasis ohne Namen" | `namen --write` fehlt |
| „Spielordner nicht gefunden" | `--save-dir` mitgeben, siehe Schritt 5 |
| „Kein Verarbeitungsschritt lohnt sich" | Es fehlt die genannte Zutat — oder Rezepte fehlen in `kb.sqlite`, dann `html --write` nachholen |
| Das Fenster geht nicht auf | `python ats-gui.pyw` in PowerShell starten; meist fehlt tkinter, also Python ohne tcl/tk installiert |
| „Gefunden, aber nicht lesbar: storage" oder Lager leer, obwohl voll | Das Spiel legt das Feld anders ab als erwartet. `python tools\lage.py form` zeigt den Aufbau (Schlüssel und Typen, keine Mengen) — die Ausgabe in den Chat einfügen |
| `&&` wird nicht angenommen | Windows PowerShell 5.1 kennt das nicht. Befehle einzeln in je eine Zeile |

## Prüfen, dass alles steht

```powershell
python tools\lage.py                 # Zustand, Nahrung, Ungeduld, ein Rat
python tools\mcp_start.py --pruefen  # jedes Werkzeug einmal, ohne Server
python -m pytest tests\ -q           # braucht: pip install pytest
```

`--pruefen` ruft jedes Werkzeug genau einmal auf und schreibt dabei nichts.
Was stumm bleibt, steht mit Grund dabei.
