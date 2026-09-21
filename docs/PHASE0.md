# Phase 0 — Machbarkeit klären

Status: **Skript fertig und getestet, Messung steht aus.** Die Messung muss auf
deinem Windows-Rechner laufen, nicht hier.

## Warum ich das nicht selbst ausführen kann

Diese Sitzung läuft in einem Linux-Container in der Cloud. Der Container hat
weder deinen `%USERPROFILE%` noch eine Against-the-Storm-Installation. Es gibt
keinen Weg, von hier aus `Save.save` zu lesen. Wer dir an dieser Stelle ein
Ergebnis präsentiert, hat geraten.

Was ich stattdessen gemacht habe: das Diagnoseskript geschrieben und gegen
synthetische Spielstände geprüft, so dass alle drei Erkennungspfade — gzip-JSON,
unkomprimiertes JSON, undekodierbarer Binärklumpen — nachweislich das Richtige
tun. Du startest es, schickst mir den Textbericht, ich lege dir die
Entscheidungsvorlage vor.

Bewusst nicht beantwortet habe ich die drei Fragen aus dem Gedächtnis. Zu
Save-Formaten kursieren Angaben aus mehreren Spielversionen; 1.10.4 ist neuer
als das meiste davon, und die ganze Phase 0 existiert genau deshalb.

## Was du ausführst

Python 3.12 auf dem Windows-Rechner, sonst nichts — das Skript benutzt nur die
Standardbibliothek, keine Installation nötig.

```powershell
# 1. Format und Sprache (Sekunden, Spiel darf laufen oder zu sein)
python tools\phase0_diagnose.py inspect

# 2. Schreibzeitpunkt (zehn Minuten, dabei ganz normal weiterspielen)
python tools\phase0_diagnose.py watch --minutes 10

# beides am Stück:
python tools\phase0_diagnose.py all --minutes 10
```

Findet das Skript den Ordner nicht, listet es auf, wo es gesucht hat. Dann:

```powershell
python tools\phase0_diagnose.py inspect --dir "$env:USERPROFILE\AppData\LocalLow\Eremite Games\Against the Storm"
```

**Wichtig für Schritt 2:** während der zehn Minuten wirklich spielen, und wenn
möglich einen Jahreszeitenwechsel mitnehmen. Die Vermutung ist, dass das Spiel
nicht auf Zuruf schreibt, sondern an festen Punkten. Ob das stimmt, entscheidet
über Phase 3.

Das Skript öffnet ausschließlich lesend und schreibt nur in `diagnostics/`.
Schick mir die `.txt` daraus. Sie enthält eine Stichprobe von Strings aus dem
Spielstand und Pfadangaben deines Benutzerordners — falls dich Letzteres stört,
vorher überschreiben.

## Entscheidungsvorlage (wird nach der Messung ausgefüllt)

| Frage | Befund | Quelle |
|---|---|---|
| Container (JSON / gzip / anderes) | offen | `inspect` |
| Größe entpackt, Zeilenzahl | offen | `inspect` |
| Sprache im Save (IDs oder lokalisiert) | offen | `inspect` |
| Schreibintervall | offen | `watch` |
| Abgedeckte GameState-Felder von 15 | offen | `inspect`, Abschnitt Feldsuche |

Je nach Ausgang greift eines von drei Szenarien.

**A — Save ist JSON und wird häufig geschrieben (Intervall unter ~2 Minuten).**
Der Parser trägt Phase 2 praktisch allein. Phase 3 schrumpft auf zwei Dinge, die
im Save nicht stehen können: die Restzeit der laufenden Jahreszeit und die
Auswahlbildschirme für Grundsteine und Baupläne. Template-Matching für Symbole
entfällt größtenteils, Tesseract bleibt für die Optionstexte. Reihenfolge wie in
SPEC.md: 1 → 2 → 4 → 3 → 5.

**B — Save ist JSON, wird aber nur selten geschrieben (etwa nur bei
Jahreszeitenwechsel).** Der Parser liefert dann ein Standbild pro Jahreszeit.
Das reicht für `analyze_runs` und für die Grundsteinberatung, nicht für
`food_forecast` in Echtzeit. Folge: `read_hud()` aus Phase 3 wird Pflicht und
muss vor Phase 5 stehen. Die Läufe in `runs/*.jsonl` bekommen zwei Quellen mit
unterschiedlicher Aktualität — das gehört ins Datenmodell, sonst rechnet der
Nahrungsvorschau-Code mit Zahlen aus der letzten Jahreszeit.

**C — Save ist nicht lesbar (Binärformat, verschlüsselt, proprietär).** Dann
wird Phase 3 die Hauptarbeit, und wir reden vorher über den Zuschnitt. Mein
Vorschlag für diesen Fall, damit die Diskussion nicht bei null anfängt: Phase 2
entfällt ersatzlos, `read_hud()` wird die einzige Zustandsquelle, und der
Funktionsumfang schrumpft auf Nahrungsvorschau plus Auswahlberatung. Die
Laufauswertung `analyze_runs` fällt weg oder wird auf das reduziert, was beim
Hotkey-Druck erfasst wurde. Der Hexdump aus dem Bericht sagt dann, ob es sich
lohnt, das Format zu knacken, statt es zu umgehen.

## Was ich aus dem Bericht herauslese

Das Skript beantwortet nebenbei mehr als die drei Fragen, weil es beim JSON-Lauf
ohnehin alles anfassen muss:

- **Feldsuche.** Für jedes der fünfzehn GameState-Felder aus Phase 2 sucht es
  passende Schlüsselnamen und zeigt Pfad, Trefferzahl und einen Beispielwert.
  Daraus wird direkt die Abdeckungszahl für die Entscheidungsvorlage.
- **Schlüsselindex und Strukturskizze.** Spart in Phase 2 das Herumraten im
  300.000-Zeilen-Dokument.
- **Sprachprobe.** Zählt Umlaute, ID-artige Strings und Treffer gegen die
  bekannten deutschen und englischen Begriffe aus SPEC.md. Stehen im Save
  englische IDs, ist das Lokalisierungsproblem auf die Ausgabeseite beschränkt
  und `name_map` muss nur noch für die Bildschirmauslesung befüllt werden.
- **Gegenprobe zur Recherche.** Die beigelegte Gemini-Recherche behauptet
  konkrete JSON-Pfade, eine Kategoriepräfix-Konvention (`[Food Raw] Meat`),
  unkomprimiertes JSON mit 250.000 bis 350.000 Zeilen und einen Heartbeat alle
  120 bis 180 Sekunden. Der Bericht prüft jede dieser Behauptungen einzeln und
  meldet bestätigt, abweichend oder nicht gefunden. Bewertung der Recherche:
  [RESEARCH-REVIEW.md](RESEARCH-REVIEW.md).

## Danach

Erst wenn die Vorlage ausgefüllt ist und du sie freigegeben hast, fange ich mit
Phase 1 an. Kein Produktcode vorher.

---

# Messung vom 2026-09-21

Gelaufen auf dem Spielrechner, Windows, Siedlung aktiv. Ausgewertet ist
bisher nur das Ende des Berichts — der Kopf mit Pfadprüfung, Feldsuche und
Sprachprobe steht noch aus.

## Entscheidungsvorlage, Stand jetzt

| Frage | Befund | Quelle |
|---|---|---|
| Container | **plain-json**, unkomprimiert | gemessen |
| Zeilenzahl | **359.438** | gemessen |
| Kategoriepräfix | **bestätigt**, 112 Treffer | gemessen |
| Sprache im Save | offen | Berichtskopf fehlt |
| Abgedeckte GameState-Felder | offen | Berichtskopf fehlt |
| Schreibintervall `Save.save` | **nicht gemessen** — Fehler im Skript, siehe unten | — |

## Was der Save preisgibt

Die Kategoriepräfixe sind da, und zwar reichlich. Gefundene Kategorien mit
Trefferzahl:

```
Food Raw 15, Food Processed 13, Mat Processed 10, Needs 10, Mat Raw 9,
SSE 8, Crafting 6, Packs 5, Metal 4, BIOME 4
```

Drei Dinge daran sind für Phase 2 wichtiger, als sie aussehen:

1. **Präfixe können doppelt auftreten.** Beispiel aus dem Bericht:
   `[SSE] [BIOME] Storm Penalty`. Ein Abschneider, der genau ein `[...]`
   entfernt, lässt `[BIOME] Storm Penalty` stehen und legt damit zwei
   verschiedene Schlüssel für dieselbe Sache an. Das Abschneiden muss
   schleifen, nicht einmal zuschlagen.
2. **`SSE` ist vermutlich die Effektkategorie.** `[SSE] Gift for Reputation`,
   `[SSE] Corruption Favoring Block`, `[SSE] FuelRateHostility` lesen sich wie
   Grundstein- und Modifikatoreffekte. Wenn das trägt, liegt hier die Antwort
   auf „gewählte Grundsteine" aus dem `GameState`. Zu prüfen am Berichtskopf.
3. **`[Crafting] Oil` schließt den Kreis zum Screenshot.** Die Auftragsleiste
   zeigte „42/25 Öl", der Save kennt `Oil` in der Kategorie `Crafting`. Damit
   ist das erste Namenspaar nicht geraten, sondern aus zwei unabhängigen
   Quellen belegt — genau das Verfahren, das für die restliche `name_map`
   gedacht ist.

## Fehler im Skript, behoben

Der `watch`-Lauf hat `Save.save` nie beobachtet. Die Dateiauswahl war
alphabetisch und bei vier Dateien gedeckelt — `CustomGamesLayout.save`,
`MetaSave.save`, `MetaSave_Backup.save` und `MetaSave_GameWonBackup.save`
stehen im Alphabet vor `Save.save` und haben den Platz belegt. Gemessen wurde
damit der Metafortschritt, nicht die laufende Siedlung. Frage 2 ist also
unbeantwortet, nicht beantwortet.

Behoben: `Save.save` und `MetaSave.save` werden jetzt vorrangig ausgewählt, der
Bericht nennt die weggelassenen Dateien, und fehlt `Save.save` ganz, steht eine
Warnung im Bericht.

Zweiter Fehler, ebenfalls behoben: aus zwei Schreibvorgängen wurde ein
„schreibt etwa alle 116s" gemacht. Zwei Ereignisse ergeben einen Abstand, und
ein Abstand ist kein Takt. Ab jetzt braucht eine Taktaussage mindestens drei
Abstände, darunter weist der Bericht die Einzelwerte aus.

## Was noch fehlt

1. Der Kopf des Berichts (`diagnostics\phase0-*.txt`, alles oberhalb von
   „Kategoriepraefix"): Pfadprüfung, Feldsuche, Sprachprobe.
2. Ein zweiter `watch`-Lauf mit der korrigierten Auswahl:
   `python tools\phase0_diagnose.py watch --minutes 10`

## Nachtrag: Berichtskopf, `MetaSave.save` und der Dateibestand

### Frage 3 ist beantwortet: englische IDs

400 Strings geprobt, **null mit Umlauten**, 356 davon ID-artig. Stichprobe:
`[Mat Raw] Leather`, `[Food Raw] Mushrooms`, `[Food Processed] Jerky`,
`[Crafting] Coal`, `[Map Mod] Trader Attack`, `[Embark] Cornerstone Reroll +3`.

Damit ist der Fall eingetreten, auf den die Spec gehofft hat. Die deutsche
Oberfläche ist reine Präsentation, im Save steht Englisch. `name_map` wird
nur für die Ausgabe an mich und für die Bildschirmauslesung gebraucht, nicht
fürs Rechnen. Zwei weitere Kategorien tauchen hier auf, die im Save der
Siedlung nicht vorkamen: `Map Mod` und `Embark`.

### Der Dateibestand ist aufschlussreicher als erwartet

Sechzehn Dateien im Ordner. Drei davon tragen die laufende Partie:

| Datei | Größe | Geschrieben |
|---|---|---|
| `Save.save` | 8,47 MB | 19:07:29.538 |
| `WorldSave.save` | 1,52 MB | 19:07:29.086 |
| `MetaSave.save` | 0,18 MB | 19:07:28.934 |

**Alle drei innerhalb von 0,6 Sekunden.** Die zugehörigen `_Backup`-Dateien
ebenso, geschlossen um 15:52:11. Das Spiel schreibt also nicht eine Datei,
sondern ein Bündel — und der Parser muss entsprechend auf das Bündel
reagieren, sonst liest er `Save.save` neu und `WorldSave.save` noch alt.

`WorldSave.save` kommt in der Recherche überhaupt nicht vor. 1,5 MB Weltkarte,
und der Verdacht liegt nahe, dass dort die entdeckten Lichtungen und die
Vorkommen mit Restladungen stehen — zwei der fünfzehn GameState-Felder.

Nebenbei: `Save.save` ist **8,5 MB**, nicht die von der Recherche genannten
30 MB. Die daraus abgeleitete Warnung, `json.loads` sei zu langsam und man
brauche `ijson` oder `mmap`, schrumpft damit erheblich. 8 MB liest die
Standardbibliothek in Bruchteilen einer Sekunde.

### `MetaSave.save` enthält zwei Dinge, die Arbeit sparen könnten

1. **Eine Laufhistorie.** `$.gamesHistory.records[19]` — also mindestens
   zwanzig Einträge, je mit `gameTime`, `modifiers`, `cornerstones` und
   `lakeChargesUsed`. Das ist die Vorgeschichte meiner Läufe, die das Spiel
   selbst führt. `analyze_runs(n)` aus Phase 4 bekommt damit einen Sockel,
   noch bevor `runs/*.jsonl` den ersten Eintrag hat. Ob dort mehr steht als
   Endzustände, muss der Berichtskopf zu `Save.save` zeigen.
2. **Möglicherweise den Inhaltskatalog des Spiels.**
   `$.content.buildings` ist eine Liste mit **169 Einträgen**. Falls das die
   Gebäudeliste des Spiels ist und nicht nur Freischaltmarker, wäre das eine
   bessere Quelle für `kb.sqlite` als das Wiki: aktuell zur installierten
   Version, in denselben IDs wie der Rest des Saves, und ohne Crawlen. Das
   ist die einzige offene Frage, die Phase 1 im Zuschnitt verändern könnte —
   deshalb steht sie hier und nicht in einer Fußnote.

Ebenfalls in `MetaSave`: `$.gameConditions.{biome, difficulty, races,
reputationToWin, worldField}`. Die Laufbedingungen samt Prestige-Stufe stehen
also im Metafortschritt, nicht nur im Siedlungs-Save.

### Was die 0 von 7 Pfaden *nicht* bedeutet

Der Abschnitt zu `MetaSave.save` meldet null bestätigte Pfade. Das ist kein
Urteil über die Recherche: sie hat ihre Pfade für `Save.save` behauptet,
geprüft wurden sie hier gegen die falsche Datei. Die Bewertung steht im
Abschnitt zu `Save.save`, der noch fehlt.

### Skript nachgezogen

`WorldSave.save` gehört jetzt zu den vorrangig ausgewählten Dateien,
`--max-files` steht auf 6, und `watch` meldet gemeinsame Schreibvorgänge:
ändern sich mehrere Dateien innerhalb von zwei Sekunden, steht das als Gruppe
im Bericht. Damit beantwortet der nächste Lauf nicht nur „wie oft", sondern
auch „was zusammen".

## Frage 2, erste echte Daten (Messung 19:29 bis 19:39)

Diesmal war `Save.save` dabei. Zwei Schreibvorgänge in zehn Minuten Spielzeit:

| Zeit | Seit dem letzten | `Save.save` | `MetaSave.save` | `MetaSave_Backup.save` |
|---|---|---|---|---|
| 19:31:56 | 170 s | −3.081 B | −1 B | −4 B |
| 19:32:22 | 26 s | −6.351 B | −1 B | −1 B |

Danach sieben Minuten nichts. Zusammen mit dem ersten Lauf (`MetaSave` um
19:16:07 und 19:18:03, Abstand 116 s) ergibt das die Abstände 116 s, 833 s,
26 s.

**Das ist kein Heartbeat.** Die Recherche behauptet einen rollenden
Schreibvorgang alle 120 bis 180 Sekunden; gemessen sind zwei Schreibvorgänge
im Abstand von 26 Sekunden und danach sieben Minuten Stille. Das Muster ist
ereignisgetrieben, nicht getaktet. Die Screenshots rund um die Messung zeigen
den Übergang von Jahr IV auf Jahr V — der naheliegende Verdacht ist, dass die
beiden Schreibvorgänge zum Jahreszeitenwechsel gehören.

**Bestätigt ist dagegen das Bündel:** `Save.save`, `MetaSave.save` und
`MetaSave_Backup.save` ändern sich auf dieselbe Sekunde. Das war bisher nur
aus den Änderungszeitpunkten der Dateiliste geschlossen, jetzt ist es
beobachtet.

### Vorläufige Einordnung: Szenario B

Zwei Zustände in zehn Minuten, zu unvorhersehbaren Zeitpunkten. Für
`analyze_runs` und für die Grundsteinberatung reicht das. Für
`food_forecast` in Echtzeit reicht es nicht — eine Nahrungswarnung, die
sieben Minuten alt sein kann, kommt bei einer Jahreszeit von wenigen Minuten
zu spät. Damit wird `read_hud()` aus Phase 3 Pflicht und muss vor Phase 5
stehen, und `runs/*.jsonl` bekommt zwei Quellen mit unterschiedlicher
Aktualität, die im Datenmodell auseinandergehalten werden müssen.

Endgültig ist das erst, wenn der Auslöser feststeht. Deshalb die Sonde.

### Neu: Sonde bei jedem Schreibvorgang

`watch` liest den Spielstand jetzt bei jeder erkannten Änderung und
protokolliert Jahr, Jahreszeit, Restzeit, Feindseligkeit, Ungeduld,
Reputation und Bevölkerung mit. Aus „hat um 19:31:56 geschrieben" wird damit
„hat beim Wechsel in die Auslichtung geschrieben" — und erst das beantwortet,
ob der Auslöser der Jahreszeitenwechsel ist, ein Auftrag, ein
Lichtungsereignis oder schlicht die Pausetaste. Abschaltbar mit `--no-probe`.

### Zwei Fehler im Skript, behoben

1. **`SyntaxWarning: invalid escape sequence '\u'`** — in `decode_container`
   stand `raw.lstrip(b" \t\r\n﻿")`. In einem Bytes-Literal ist `﻿`
   kein BOM, sondern die ASCII-Zeichen `\`, `u`, `f`, `e`. Das Skript hat
   also Backslash, u, f und e vom Dateianfang abgeschnitten und ein echtes
   BOM stehen lassen — eine JSON-Datei mit BOM wäre als „unbekannt"
   durchgefallen. Jetzt wird das BOM als `\xef\xbb\xbf` geprüft.
2. **`+-3081 Bytes`** in der Ausgabe: das Vorzeichen stand doppelt.

### Noch offen

- `WorldSave.save` fehlt weiterhin in der Messung. Der Lauf lief auf dem
  Stand vor dem Commit, der sie aufgenommen hat — ein `git pull` fehlt.
- Der `### Save.save`-Block aus dem ersten Bericht: Sprachprobe, Feldsuche
  über die fünfzehn Felder, die sieben Pfadprüfungen.
