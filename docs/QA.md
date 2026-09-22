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

**Das Fenster selbst ist hier nicht gestartet worden.** In dieser Umgebung
gibt es kein tkinter und keine Möglichkeit, es nachzuinstallieren. Geprüft ist
die Verdrahtung mit eingesetztem tkinter: dass sich das Fenster aufbaut, dass
`_anzeigen` **jede** der neun Nachrichtenarten kennt, und dass auch die leeren
Fälle nicht werfen. Was offen bleibt, ist das Aussehen und die
Selbstaktualisierung am echten Spielstand — die stehen in `docs/APP.md` als
Schritte, die am Spielrechner zu gehen sind.

## Warum diese Tests und nicht mehr

Je Fund **erst der Test, der ihn zeigt**, dann die Behebung. Ein Fehler ohne
Regressionstest ist ein Fehler, der wiederkommt — in diesem Projekt zweimal
belegt: `main()` verschwand beim Umbau, und `--db` wurde von der Vorgabe des
Unterbefehls still überschrieben. Beide Male waren alle Tests grün, und beide
Male hat es der Nutzer beim Start gemerkt.

Dazu drei Tests auf Einstiegspunkte — `mcp_start`, `lage`, `ats-gui` —, weil
genau das die Lücke war.

**Stand: 217 Tests, alle grün.**
