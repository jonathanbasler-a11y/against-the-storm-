# Prüfrunde vor der Oberfläche (2026-09-22)

Eine Oberfläche legt bestehende Fehler nicht offen, sie versteckt sie hinter
einem hübscheren Fenster. Deshalb ging eine Prüfrunde voraus.

**Sechs Funde, sechs Regressionstests.** Vier davon wären nie aufgefallen,
bevor das Fenster sie an die Oberfläche geholt hätte — und drei sind meine
eigenen, aus derselben Woche.

## Gefunden und behoben

### 1. `read_choice` wäre abgestürzt, sobald es wirklich liest

`screen._erkenne_windows` ruft `asyncio.run()`. Unter dem MCP-Server laufen
die Werkzeuge **in** einer Ereignisschleife, und dort wirft das ein
`RuntimeError`. Aus dem Arbeits-Thread des Fensters dasselbe.

Der Prüflauf hat es nicht gemerkt, weil er die Texterkennung mit
`text=["PILZFÜHRER"]` überspringt. **Genau der Pfad, den die Prüfung nicht
erreicht, war der kaputte** — und der einzige, für den Phase 3 überhaupt
gebaut wurde.

`im_eigenen_lauf()` nimmt einen eigenen Thread, wenn schon eine Schleife
läuft, und lässt Fehler nicht verschwinden.

### 2. Der neue MCP-Weg hatte die Absicherung des alten verloren

`_serve_alt` fing jeden Werkzeugfehler ab — „ein Werkzeugfehler darf den
Server nicht beenden". Der 2.x-Weg fing nichts. Es hätte an der installierten
MCP-Fassung gehangen, ob ein Fehler eine Antwort oder einen Abbruch ergibt.

### 3. Der Prüflauf hatte eine Nebenwirkung, die er anderswo vermeidet

`log_event` wird übersprungen, **weil** es schreibt. `get_state` schrieb eine
Mitschrift und lief trotzdem. Das erklärte auch die merkwürdige Zeile im
ersten echten Lauf: „0 Mitschriften", und `impatience_forecast` trotzdem grün.

### 4. Läufe ohne Ausgang zählten als Niederlage

`compare_runs` behandelte jeden Eintrag ohne `hasWon` als verloren. Ein
abgebrochener Eintrag ist aber kein verlorener Lauf; ihn dazuzuschlagen
verschiebt jeden Vergleich in dieselbe Richtung, lautlos. Jetzt zählen nur
`True` und `False`, und der Rest wird genannt.

### 5. „Kein Verarbeitungsschritt lohnt sich" sagte nicht, woran es liegt

Der Befund vom Spielrechner. Ein Satz, der den Spieler in dieselbe Sackgasse
zurückschickt. Jetzt nennt `rat()` die fehlende Zutat mit Menge: Dörrfleisch
scheitert am Brennstoff, nicht am Fleisch.

### 6. `tools_api` warf statt zu antworten

Kein einzelner Fund, sondern eine Lücke in der Zusage. Dieselben Funktionen
werden aus drei Richtungen gerufen — MCP, Kommandozeile, Fenster. Wer wirft,
reißt den Aufrufer mit; beim Fenster einen toten Arbeits-Thread und eine
Oberfläche, die stehenbleibt, ohne zu sagen warum. Jede Ausnahme wird jetzt
ein Dictionary mit `fehler` und `werkzeug`.

## Geprüft, nichts gefunden

**Zahlen am Rand.** Zwanzig Fälle einzeln durchgegangen: leere Reihen, eine
einzige Stützstelle, Zeit läuft rückwärts, Schwelle null, Bonusrate −1,
Rezept ohne Zutaten, Menge null, negativer Bestand, Bestand als Text, leere
Namenstabelle, 5000 Zeichen Eingabe, leere Laufhistorie. **Keine einzige
werfende Stelle.** Die Rechenschicht hält.

**Dateisperren.** `_load` fängt `OSError` und meldet es — beim Lesen während
des Speicherns genau das Richtige.

**SQL.** Tabellennamen in f-Strings stehen alle in festen Listen im Code;
alles, was aus dem Wiki oder aus der Lokalisierung kommt, läuft über
Parameter.

## Steht bewusst so

**Zeit rückwärts ergibt Rate 0 statt „nicht vergleichbar".** `food_forecast`
nimmt die letzten zwei Einträge derselben Mitschrift, und der Beobachter legt
bei einem neuen Lauf eine neue an — die Lage kann also nicht auftreten. Eine
Behandlung dafür wäre toter Code mit einem Test, der nichts beweist.

**16 Stellen fangen ab, ohne etwas zu sagen.** Einzeln durchgesehen: jede
schweigt über etwas Erwartbares — eine halb geschriebene Datei, eine Tabelle,
die es noch nicht gibt, ein Wikiabschnitt ohne Zahlen. Wo das Schweigen etwas
verdeckt hätte, steht jetzt eine Meldung.

**Das Fenster ist inzwischen gestartet worden** — siehe die zweite Runde
unten. Was weiter offen bleibt, ist die Windows-Seite: der Doppelklick auf
`.pyw`, die Bildschirmaufnahme über PowerShell, die Texterkennung über
`winsdk`.

## Warum diese Tests und nicht mehr

Je Fund **erst der Test, der ihn zeigt**, dann die Behebung. Ein Fehler ohne
Regressionstest ist ein Fehler, der wiederkommt — in diesem Projekt zweimal
belegt: `main()` verschwand beim Umbau, und `--db` wurde von der Vorgabe des
Unterbefehls still überschrieben. Beide Male waren alle Tests grün, und beide
Male hat es der Nutzer beim Start gemerkt.

Dazu drei Tests auf Einstiegspunkte — `mcp_start`, `lage`, `ats-gui` —, weil
genau das die Lücke war.

**Stand: 217 Tests, alle grün.**


---

# Zweite Runde: das Fenster wirklich starten (2026-09-22)

Die Frage war, ob eine neue Sitzung mit tkinter nötig sei. Nein — und der
Grund war ein Befund für sich.

## Die Suite lief gegen die falsche Python-Version

| | |
|---|---|
| `python3` (Vorgabe) | **3.11.15**, kein tkinter |
| `/usr/bin/python3.12` | **3.12.3, tkinter 8.6** |
| `pyproject.toml` | `requires-python = ">=3.12"` |

**217 Tests liefen wochenlang auf einer Version, die das Projekt nicht
unterstützt.** Jedes „alle Tests grün" sprach über die falsche Laufzeit. Nicht
die Umgebung fehlte, sondern der Blick darauf, welchen Interpreter ich
benutze.

`tests/test_laufzeit.py` macht daraus eine rote Zeile statt einer stillen
Abweichung: er liest `requires-python` und vergleicht mit `sys.version_info`.
Auf 3.11 schlägt **er** fehl, mit den Versionen und dem Pfad des Interpreters
im Text.

## Der Stub-Test lief in den echten aus

`tests/test_gui_echt.py` (echtes Tk unter `xvfb-run`) war allein grün und in
der Gesamtsuite achtmal rot: `Egal has no len()`.

Grund: `sys.modules.pop("ats_assistant.gui")` entfernt das Modul aus der
Tabelle, **aber nicht das Attribut am Paket**. `from ats_assistant import gui`
holt es von dort — am Importsystem vorbei. Die echte Fassung prüfte also
dieselben Attrappen wie die Stub-Fassung.

Das ist die unangenehmste Sorte Fehler: ein Test, der grün ist, ohne etwas zu
prüfen. Jetzt räumt die Vorrichtung beides ab, und ein eigener Test wacht
darüber.

## Was echtes Tk gezeigt hat

Sieben von acht Prüfungen liefen auf Anhieb durch — die Oberfläche hält, was
der Stub versprochen hatte. Zwei Funde kamen vom Hinsehen:

**Die Statuszeile lief rechts aus dem Bild.** Drei offene Punkte nebeneinander
werden abgeschnitten, und zwar am Ende — dort, wo steht, was zu tun ist. Jetzt
steht einer da, der Rest gezählt, alle beim Überfahren.

**Waren standen englisch neben deutschen Gebäuden.** „Räucherei: 40 **Meat**",
Engpass „**Meat**" — ausgerechnet dort, wofür die 2266 Namen belegt wurden.
`Zutat` trägt jetzt ihren deutschen Namen mit, `food_advice` gibt beides
zurück (`ware` deutsch, `ware_en` daneben).

## Bilder

Drei Aufnahmen des laufenden Fensters unter Xvfb: Lage mit Balken für
Reputation, Ungeduld und Nahrungsreichweite; Nahrung mit drei Sätzen und der
Kettentabelle; Auswahl mit zwei erkannten Grundsteinen samt Güte und Wirkung.

**Stand: 228 Tests, alle grün, auf Python 3.12 mit echtem Tk.**

---

# Der erste Lauf am Spielrechner (2026-09-22)

Das Fenster lief zum ersten Mal dort, wo das Spiel läuft: Windows, Python
3.12, vier Reiter, `Alles bereit – 2273 Namen`. **Vier Funde in zwei
Sitzungen — und der schwerste war der unauffälligste.**

Keiner davon wäre hier aufgefallen. Drei brauchten einen echten Spielstand,
einer eine fehlende Anmeldung. Alle vier liegen in Code, den die 228 Tests
umrundet haben.

## 1. Die Nahrungsvorhersage war tot, und nichts sagte es

Im Fenster: „Nahrung reicht **–**", daneben rot „Es braucht zwei
Spielstände". In der Statuszeile: **22 Mitschriften**. Beides stand da
gleichzeitig, und beides stimmte.

`get_state` baute die Kennung der Mitschrift so:

```python
kennung = run_id or f"{state.biome or 'lauf'}-{int(state.game_time)}"
```

Die Spielzeit steht in der Kennung. Also bekam **jeder Aufruf eine eigene
Datei** — 22 Dateien mit je einer Zeile. `food_forecast` nimmt die letzten
zwei Einträge *derselben* Mitschrift und fand nie einen zweiten.

Der Grund, aus dem es dieses Programm gibt, ist der Nahrungsmangel im ersten
Jahr. Genau der lief ins Leere, während alles andere grün aussah:
`impatience_forecast` braucht nur einen Zustand und lieferte brav
„Niederlage in 9 min".

Behoben in `watcher.lauf_kennung`: Biom, Stufe und eine nicht
zurückgesprungene Spieluhr heißen dieselbe Siedlung, also dieselbe Datei.
Gelesen wird dafür nur die letzte Zeile, rückwärts in Blöcken — eine Zeile
ist ein ganzer Zustand samt Zeitreihen, gut 200 kB. Dazu schreibt
`mitschreiben` nichts, was schon dasteht, und ein neu gestarteter
`ats-watch` verlängert den laufenden Lauf, statt einen neuen zu beginnen.

**Warum kein Test das sah:** jeder Test gab seine Kennung selbst mit
(`run_id="testlauf"`). Was ohne sie passiert, hat nie jemand geprüft.

## 2. Die Feindseligkeit stand als rohes Dictionary im Fenster

`{'level': 3, 'points': 72, 'sources':` — am rechten Rand abgeschnitten.

Das Fenster suchte `feind.get("current")`. Dieser Schlüssel stammt aus der
Testvorlage dieses Projekts, und die war **erfunden, nicht gemessen**. Das
Spiel schreibt `level` und `points`.

`rechner.feindseligkeit` liest beide Formen; die Vorlagen tragen jetzt die
gemessene; und ein Test besteht darauf, dass nie eine geschweifte Klammer im
Fenster landet, was auch kommt.

## 3. Der Anmeldefehler ging an allen vier `except`-Zweigen vorbei

Im Reiter „Rat" stand der englische Rohtext des SDK: *Could not resolve
authentication method…*

Nachgesehen in anthropic 1.7.0 statt vermutet: für eine fehlende Anmeldung
wirft das SDK **kein** `AuthenticationError`, sondern ein schlichtes
`TypeError` aus `_validate_headers` — und zwar beim Bauen der Kopfzeilen,
mitten in `messages.create()`. `rechner._rat` fing es als `Exception` und
setzte `zugang=True`; deshalb fehlte der Satz mit `setx ANTHROPIC_API_KEY`
und der Hinweis auf „Lage kopieren".

`_ist_anmeldefehler` erkennt es, absichtlich eng: ein `TypeError` über ein
falsches Schlüsselwort — `budget_tokens` ging genau so schon einmal daneben —
bleibt ein `TypeError`. Als Anmeldeproblem verkleidet wäre es nicht zu
finden.

Nebenbei aufgefallen: der vorhandene Test des Ratwegs hätte auf einem Rechner
**mit** Schlüssel wirklich angefragt. Er setzt jetzt einen Client ein.

## 4. Der Auswahlreiter sagte nicht, welcher Weg gelaufen ist

Im Handfeld stand `handelsverhandlungen`, in der Ausgabe der Rat zu
`pip install winsdk`. Gelaufen war der Bildweg — nur stand das nirgends.

Kein Programmfehler im engeren Sinn: der Knopf „Bildschirm lesen" liest den
Bildschirm. Aber ein Feld, das nicht sagt, woher seine Zeilen kommen, macht
aus einem Bedienfehler einen Programmfehler. Jetzt steht die Herkunft in
beiden Fällen oben, der Grund passt zum Weg (wer tippt, wird nicht nach dem
Bildschirmfoto gefragt), und scheitert der Bildweg, während im Handfeld Text
steht, weist ein Satz auf „Abgleichen".

## Was das über die Prüfrunde sagt

Die Prüfrunde hat sechs Fehler gefunden, ohne das Spiel zu starten. Diese
vier brauchten es. Das ist keine Schwäche der Runde — es ist die Grenze, die
sie selbst benannt hat: *„Ein Tk-Fenster unter Xvfb beweist die Verdrahtung,
nicht die Windows-Seite."* Was sie nicht benannt hatte: dass auch ein echter
**Spielstand** Dinge zeigt, die keine Vorlage zeigt. Zwei der vier Funde
hängen an genau dem — einer erfundenen Testvorlage und einer Kennung, die
kein Test je selbst bilden ließ.

**Stand: 260 Tests, alle grün, auf Python 3.12 mit echtem Tk.**
