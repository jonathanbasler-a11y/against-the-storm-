---
name: ats-werkzeuge
description: Die Werkzeugkette des Against-the-Storm-Assistenten bedienen -- Wissensbasis bauen und auffrischen, Mitschrift starten, Fenster und MCP-Server prüfen, Auswahlbildschirm lesen, Namen nachschlagen. Nutzen, sobald jemand in diesem Repo etwas aufbauen, aktualisieren, starten oder prüfen will, auch wenn nur "die Datenbank ist leer", "der Server antwortet nichts", "das Fenster geht nicht auf" oder "nach dem Spiel-Update stimmen die Namen nicht" gesagt wird. Auch nutzen, wenn ein Befehl fehlschlägt und die Fehlermeldung nach Pfad, Python-Version oder leerer Wissensbasis klingt.
---

# Die Werkzeugkette bedienen

Der Assistent besteht aus Teilen, die einander brauchen. Wer sie in der
falschen Reihenfolge ruft, bekommt keine Fehlermeldung, sondern ein leeres
Ergebnis — und das ist schwerer zu finden. Dieser Skill sagt, was wann läuft
und woran es hakt, wenn es hakt.

## Vier Fallstricke, die jeden Befehl betreffen

**Python 3.12, nicht `python`.** `pyproject.toml` verlangt `>=3.12`. Wo mehrere
Versionen installiert sind, meint `python3` womöglich eine ältere — und dann
fehlt tkinter, und die Testsuite sagt trotzdem "grün". `tests/test_laufzeit.py`
wacht darüber; schlägt er fehl, ist es die Version, nicht der Code.

**`python -m ats_assistant.x` findet nichts.** Das Paket liegt unter `src/`
und ist nicht installiert. Es gibt für jeden Einstieg einen Starter, der
seinen eigenen Ort findet:

| statt | nimm |
|---|---|
| `python -m ats_assistant.mcp_server` | `python tools/mcp_start.py` |
| `python -m ats_assistant.cli` | `python tools/lage.py` |
| `python -m ats_assistant.gui` | `python ats-gui.pyw` |

**Relative Pfade zeigen ins Projekt, nicht ins Arbeitsverzeichnis.**
`aufloesen()` in `mcp_server.py` sorgt dafür. Grund: Claude startet den
Server mit einem Arbeitsverzeichnis, das niemand bestimmt hat — ein relatives
`kb.sqlite` legte dort sonst eine **leere** Datenbank an, und der Server
antwortete auf alles "nichts gefunden".

**Nach einem Squash-Merge kein `git pull`.** Der Branch wird neu auf `main`
aufgesetzt; ein Merge versucht dann, dieselbe Arbeit in zwei Formen zu
vereinen, und hinterlässt Konfliktmarkierungen mitten im Code.
`git fetch origin && git reset --hard origin/<branch>`.

## Wissensbasis aufbauen

Die Reihenfolge ist nicht beliebig — jeder Schritt braucht den vorigen.

```
python tools/build_kb.py seed                    # Saat-Namen und Save-Vokabular
python tools/build_kb.py namen --write           # 2266 belegte Namen aus der Lokalisierung
python tools/build_kb.py html --wiki-dir "<abzug>" --write   # Sachtabellen
python tools/build_kb.py build --wiki-dir "<abzug>"          # Waren aus den Datenseiten
python tools/build_kb.py status                  # was drinsteht und wie belastbar
```

`namen` **vor** `html`: der HTML-Import prüft über `name_map`, ob ein
Seitentitel wirklich ein Gebäude ist, bevor er ihn einem Rezept zuordnet.
Ohne die Namen landen Rezepte unter Biomnamen.

**Hakt es, `kb.sqlite` löschen und neu bauen.** Die Tabellen wachsen
additiv; `migrate()` ergänzt fehlende Spalten, aber Altlasten aus einem
früheren Lauf bleiben. Die Mitschriften in `runs/` sind davon nicht betroffen.

### Nach einem Spiel-Update

Die Namen kommen aus `resources.assets` der eigenen Installation. Ändert das
Spiel sie, ist `data/name_map_localized.csv` veraltet:

```
python tools/build_kb.py namen --dir "<verzeichnis mit de_translations.json>"          # zeigt nur
python tools/build_kb.py namen --dir "<verzeichnis>" --write                            # übernimmt
```

Der Trockenlauf sagt, wie viele Namen sich geändert haben. Widerlegte Zeilen
wandern nach `retired_names` statt gelöscht zu werden — was falsch war, bleibt
nachlesbar.

## Die Lage abfragen

```
python tools/lage.py                      # Zustand, Nahrung, Ungeduld, Rat
python tools/lage.py nahrung              # alle Ketten mit Engpass
python tools/lage.py nachschlag Imbiss    # ein Name, deutsch oder englisch
python tools/lage.py form                 # Aufbau von Lager/Gebäuden, ohne Mengen
python tools/lage.py form order relic     # Schlüssel mit diesen Wörtern suchen
python ats-gui.pyw                        # dasselbe als Fenster
```

**"Es braucht zwei Spielstände"** ist meist kein Fehler. `food_forecast` bildet
eine Rate aus zwei Zuständen; das Spiel schreibt etwa alle 300
Spielzeitsekunden. Nach dem nächsten Speichern geht es. `ats-watch` sammelt sie
von selbst.

Bleibt die Meldung dauerhaft stehen, dann in `runs/` nachsehen: **eine
Siedlung ist eine Datei.** Viele Dateien mit je einer Zeile heißen, dass die
Kennung nicht hält — genau das war bis zum 22.09.2026 der Fall, weil sie die
Spielzeit enthielt. `watcher.lauf_kennung` entscheidet das jetzt an Biom,
Stufe und Spieluhr; ein Rücksprung der Uhr beginnt eine neue Datei.

**"Kein Verarbeitungsschritt lohnt sich"** nennt inzwischen die fehlende
Zutat. Steht sie nicht dabei, fehlen Rezepte in `kb.sqlite` — `html --write`
nachholen.

## Den MCP-Server prüfen, bevor er in Claude hängt

```
python tools/mcp_start.py --pruefen
```

Ruft jedes Werkzeug einmal auf und zeigt, was es *jetzt* sagen würde. Ein
Server, der läuft und auf alles "nichts gefunden" antwortet, ist schwerer zu
finden als einer, der gar nicht startet.

`stumm` heißt nicht kaputt, sondern: es fehlt eine Eingabe. Die Zeile nennt
welche.

`.mcp.json` hängt den Server in Claude Code ein, sobald man im Projektordner
startet; `docs/MCP.md` beschreibt daneben den Weg über Claude Desktop.

## Den Auswahlbildschirm lesen

Gemessen am 22.09.2026: die angebotenen Grundsteine stehen **nicht** im
Spielstand, auch nicht als Text — das Spiel würfelt sie aus einem Keim neu.
Deshalb der Bildschirm.

```
python tools/read_choice.py pruefen       # was die Umgebung hergibt
python tools/read_choice.py lesen         # aufnehmen, erkennen, abgleichen
python tools/read_choice.py lesen --text "PILZFÜHRER" "EXPORTSPEZIALISIERUNG"
```

Der letzte Weg braucht keine Texterkennung. Der Abgleich gegen die belegten
Namen ist derselbe, und er verzeiht viel: `PlLZFUHRER` ohne Umlaut und mit l
statt i hat 0,87 Ähnlichkeit zu "Pilzführer". Liegen zwei Kandidaten dicht
beieinander, kommt **keine** Auskunft, sondern die Kandidatenliste — eine
unentschiedene Lesung ist keine Empfehlung.

Fehlt die Erkennung unter Windows: `pip install winsdk` nutzt die, die in
Windows schon steckt — lokal, ohne Konto, ohne Netz. **Ab Python 3.13** gibt es
`winsdk` nicht mehr (Wheels bis 3.12); dort die Nachfolgepakete
`winrt-Windows.Media.Ocr`, `-Graphics.Imaging`, `-Storage`, `-Globalization`.
`screen._ocr_herkunft()` nimmt, was da ist; `screen.verfuegbar()["rat"]` nennt
den Befehl, der zur laufenden Fassung passt.

Beim Bildweg versteckt sich das Fenster für einen Augenblick selbst: die
Aufnahme nimmt den ganzen Bildschirm, und ein Assistent über den Karten wäre
das, was die Texterkennung dann liest.

## Prüfen, ob noch alles hält

```
python -m pytest tests/ -q                 # ohne Anzeige: Fenstertests übersprungen
xvfb-run -a python -m pytest tests/ -q     # unter Linux mit echtem Tk
```

Die Fenstertests gibt es zweimal mit Absicht: `test_gui.py` mit eingesetztem
tkinter (läuft überall), `test_gui_echt.py` mit echtem Tk unter Xvfb (prüft,
was ein Stub nicht kann).

## Was der Assistent nicht tut

Er klickt nichts, verändert keinen Spielstand, liest nur. Das ist kein Zufall,
sondern steht so in SPEC.md — und jede Erweiterung hat sich daran zu halten.
