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

## Korrektur: die Spielgeschwindigkeit wurde zwischendurch verändert

Damit sind die Abstände 116 s, 833 s und 26 s **Wanduhrabstände bei
unbekannter und teils unterschiedlicher Geschwindigkeit**. Sie dürfen nicht
miteinander verglichen werden, und die Einordnung „Szenario B" von oben steht
auf schwächeren Füßen, als sie dort klingt.

Was unberührt bleibt: das Bündel. Dass `Save.save`, `MetaSave.save` und
`MetaSave_Backup.save` auf dieselbe Sekunde schreiben, hängt nicht an der
Geschwindigkeit.

Was sich ändert: „kein Heartbeat" gilt weiterhin für einen Takt nach
**Wanduhr** — ein solcher wäre geschwindigkeitsunabhängig und hätte
regelmäßige Abstände ergeben. Ein Takt nach **Spielzeit** ist dagegen
weiterhin möglich und würde die Streuung erklären. 26 Sekunden bei
dreifacher Geschwindigkeit sind 78 Sekunden Spielzeit; 116 Sekunden bei
einfacher sind 116. Das ist dieselbe Größenordnung, und der Unterschied
zwischen beiden Lesarten entscheidet Phase 3.

Praktisch heißt das: wer auf x3 spielt, bekommt dreimal so frische Daten wie
die Wanduhrmessung nahelegt. Das spricht eher für den Parser als gegen ihn.

### Gegenmaßnahme im Skript

Die Sonde liest jetzt zusätzlich eine möglichst monotone Spieluhr aus dem
Spielstand (`gameTime`, `totalTime`, `playTime`, in dieser Reihenfolge;
`seasonTimeLeft` zählt rückwärts und springt, taugt also nicht) und die
Auswertung setzt Spielzeit ins Verhältnis zur Wanduhr:

```
Save.save   3 Schreibvorgaenge  -> ...
            Spielzeit je Wanduhrsekunde: 3.0, 2.25 -- Abstaende in Spielzeit
            umrechnen, bevor sie verglichen werden (Uhr: gameTime)
```

Damit ist egal, wie oft du die Geschwindigkeit umstellst: der Bericht rechnet
die Abstände selbst um. `Spielgeschwindigkeit` ist außerdem als gesuchtes
Feld in der Feldsuche aufgenommen — falls das Spiel die eingestellte Stufe im
Save ablegt, taucht sie künftig direkt im Bericht auf.

---

# Entscheidungsvorlage (Messung vom 2026-09-21, 15 Minuten, mit Sonde)

## Frage 2 ist beantwortet: Autosave alle 300 Spielzeitsekunden

Drei Schreibvorgänge, zwei Abstände:

| | Spielzeit (`time` aus `Save.save`) | Wanduhr | Spielzeit je Wanduhrsekunde |
|---|---|---|---|
| 1 → 2 | **300,827 s** | 252,2 s | 1,19 |
| 2 → 3 | **300,857 s** | 300,857 / 222,2 | 1,35 |

Auf drei Nachkommastellen dasselbe Intervall, bei zwei verschiedenen
Wanduhrabständen. Der Auslöser ist die Spieluhr, nicht die Wanduhr, nicht der
Jahreszeitenwechsel: das Spiel schreibt alle 300 Spielzeitsekunden. Die
Normalisierung hat sich damit sofort bezahlt gemacht — ohne sie stünden hier
252 und 222 Sekunden und die Schlussfolgerung wäre „unregelmäßig".

Die beiden Schreibvorgänge im Abstand von 26 Sekunden aus dem vorherigen Lauf
waren dein manuelles Speichern. Autosave und manuelles Speichern sind also zu
unterscheiden.

Die Heartbeat-These der Recherche (120 bis 180 Sekunden) ist damit endgültig
widerlegt — in Wanduhrsekunden und in Spielzeit gleichermaßen.

## Das Bündel umfasst vier Dateien

`Save.save`, `WorldSave.save`, `MetaSave.save` und `MetaSave_Backup.save`
ändern sich bei jedem der drei Schreibvorgänge innerhalb derselben Sekunde.
`WorldSave.save` blieb dabei jedes Mal **exakt gleich groß** (+0 B) — sie wird
angefasst, aber inhaltlich kaum verändert.

## Der Parser ist schnell genug, Punkt

**0,1 Sekunden** für 8,5 MB `Save.save`, 0,02 s für `WorldSave.save`, 0,01 s
für `MetaSave.save` — gemessen mit `json.loads` aus der Standardbibliothek.
Die Empfehlung der Recherche, wegen 30-MB-Dateien auf `ijson` oder `mmap`
auszuweichen, ist damit gegenstandslos.

## Entscheidung: Szenario B

Ein Zustand alle 300 Spielzeitsekunden. Zwischen dem ersten und zweiten
Schreibvorgang ist das Spieljahr von 5 auf 6 gesprungen — in einem einzigen
Intervall vergeht also fast ein ganzes Jahr. Der Parser sieht die Siedlung
damit etwa einmal pro Jahr.

- Für `analyze_runs` und die Grundstein- und Bauplanberatung reicht das
  vollkommen. Diese Entscheidungen fallen ohnehin an Jahresgrenzen.
- Für `food_forecast` reicht es nicht. Eine Nahrungswarnung, die bis zu 300
  Spielzeitsekunden alt sein kann, kommt nach dem Sturm.

**Folge für den Zuschnitt:** `read_hud()` aus Phase 3 wird Pflicht und rückt
vor Phase 5. Die Reihenfolge lautet damit 1 → 2 → 4 → **3** → 5, wie in der
Spec für diesen Fall vorgesehen. `runs/*.jsonl` bekommt zwei Quellen mit
verschiedener Aktualität; welcher Wert woher stammt, gehört ins Datenmodell,
sonst rechnet die Nahrungsvorschau mit Zahlen von vorletztem Jahr.

Der Umfang von Phase 3 bleibt trotzdem klein: gebraucht werden nur die Zahlen,
die sich schnell ändern — Restzeit der Jahreszeit, Lagerbestand Nahrung,
Entschlossenheit — plus die Auswahlbildschirme. Alles Langsame liefert der
Parser.

## Gefundene Feldnamen

Die Sonde hat nebenbei die Vokabeln geliefert, nach denen Phase 2 suchen muss:

| Gesucht | Heißt im Save | Anmerkung |
|---|---|---|
| Spieluhr | `time` in `Save.save` | `gameTime` in `MetaSave.save` steht still (dreimal 7527,31738) und taugt nicht |
| Ungeduld | `reputationPenalty` | **nicht** `impatience` — die Feldsuche fand sie deshalb nie |
| Verlustschwelle | `reputationPenaltyToLoose` = 14 | deckt sich mit der Recherche |
| Siegschwelle | `reputationToWin` = 18 | passt zum Prestige-1-Modifikator |
| Reputation | `reputation` | lebendig: 2,718 → 3,570 → 4,239 |
| Feindseligkeit | `hostility` | **ein Dictionary mit drei Schlüsseln**, kein Skalar |
| Spezies | `races` (Länge 3) | passt zu Menschen, Biber, Echsen |
| Weltbevölkerung | `population` = 13 in `WorldSave.save` | passt zur Anzeige |

Zwei Werte sind noch verdächtig: `season=0` und `timeLeft=0.0` standen in
allen drei Schreibvorgängen unverändert da. Das riecht nach einem Vorgabewert
tief in einer Vorlage statt nach dem geführten Wert. Deshalb bevorzugt die
Feldsuche jetzt den **flachsten** Fund eines Schlüsselnamens und weist die
Tiefe mit aus — der nächste Lauf zeigt, ob dann die echten Werte erscheinen.

## Was Phase 0 damit abschließt

| Frage | Befund |
|---|---|
| Container | `plain-json`, unkomprimiert |
| Größe | `Save.save` 8,5 MB, 359.438 Zeilen, in 0,1 s geparst |
| Sprache | englische IDs, null Umlaute in 400 Strings |
| Schreibtakt | alle 300 Spielzeitsekunden, als Bündel aus vier Dateien |
| Zuschnitt | **Szenario B** — Parser trägt Phase 2, `read_hud()` wird Pflicht |

Offen bleibt einzig der `### Save.save`-Block des ersten Berichts mit der
vollständigen Feldsuche über alle fünfzehn Felder. Für die Entscheidung ist er
nicht mehr nötig, für den Zuschnitt von Phase 2 schon.

---

# Zweiter watch-Lauf (12 Minuten, mit Zeitreihen-Fühler)

Drei Korrekturen an dem, was ich oben geschrieben habe.

## 1. Der Takt ist ungefähr 300 Sekunden, nicht exakt

Ich hatte „auf drei Nachkommastellen dasselbe Intervall" geschrieben. Das
stimmte für zwei Messwerte aus einem Lauf. Mit vier Messwerten aus zwei Läufen
sieht es so aus:

| Lauf | Abstände in Spielzeit |
|---|---|
| 1 | 300,827 s · 300,857 s |
| 2 | 298,676 s · 298,734 s |

Mittel 299,77 s, Spanne 298,68 bis 300,86, Streuung 2,18 s. Innerhalb eines
Laufs sind die beiden Werte fast gleich, zwischen den Läufen unterscheiden sie
sich um gut zwei Sekunden. Die Aussage lautet also: **Autosave etwa alle 300
Spielzeitsekunden, mit rund einer Sekunde Spiel nach oben und unten.** Für den
Parser ändert das nichts, für eine Behauptung über den Auslöser schon — eine
exakte Konstante wäre ein Zähler, ein schwankender Wert eher eine Prüfung im
Spieltakt.

## 2. Das Bündel ist nicht atomar

Im dritten Schreibvorgang lagen die Dateien so:

```
MetaSave.save         +0,000 s
WorldSave.save        +0,007 s
MetaSave_Backup.save  +0,023 s
Save.save             +2,024 s
```

`Save.save` kam zwei Sekunden nach den anderen — und fiel damit aus meinem
Zweisekundenfenster, weshalb der Bericht dort nur drei Dateien als Bündel
auswies.

**Das ist ein Entwurfsdetail für Phase 2, kein Schönheitsfehler.** Ein Parser,
der auf die erste Änderung reagiert, liest `MetaSave` neu und `Save.save` noch
alt. Er muss auf Ruhe warten: nach der ersten Änderung ein paar Sekunden
nichts tun und erst lesen, wenn sich eine Weile nichts mehr rührt. Das Fenster
im Skript steht jetzt auf fünf Sekunden und der Bericht weist die Spanne je
Bündel aus.

## 3. Mein Zeitreihen-Fühler war am falschen Ende

Das Ende der Reihen hat sich über drei Schreibvorgänge und rund 600
Spielzeitsekunden **nicht um einen Wert verändert** — `Food` blieb bei
`[97, 94, 92, 100]`, `[Crafting] Oil` bei `[8, 4, 4, 4]`. Gleichzeitig wuchs
`Save.save` um 38 KB, das Jahr sprang von 9 auf 10 und die Reputation stieg um
zwei Punkte. Die Siedlung ändert sich also sehr wohl.

Die wahrscheinliche Erklärung: **ein Ringpuffer.** 180 feste Plätze und ein
Schreibzeiger, der mitten durch das Feld wandert. Wer auf die letzten vier
Plätze schaut, sieht jahrelang nichts.

Der Fühler merkt sich jetzt die ganze Reihe und vergleicht zwei
aufeinanderfolgende Schreibvorgänge Stelle für Stelle. Geprüft gegen einen
nachgebauten Ringpuffer:

```
$.trends.goodsTrends: 6 Stellen geaendert (Index [46, 47, 48, 49, 50, 51])
in 300.0s Spielzeit -> etwa 50.0s je Stuetzstelle
```

Damit beantwortet der nächste Lauf die Frage, an der Phase 3 hängt.

## Was der Lauf bestätigt hat

**Die Feldsuche liest jetzt die richtigen Werte.** Nach der Umstellung auf den
flachsten Fund stehen dort lebendige Zahlen statt Vorgabewerte:

| Feld | Verlauf über drei Schreibvorgänge |
|---|---|
| `year` / `season` | 9/2 → 10/1 → 10/2 |
| `reputation` | 8,832 → 9,418 → 10,852 |
| `reputationPenalty` (Ungeduld) | 10,809 → 10,573 → 10,336 |

`timeLeft` steht weiterhin konstant auf 0,0 — das ist also immer noch nicht das
geführte Feld, sondern ein Namensvetter. `MetaSave.gameTime` steht ebenfalls
still; die Spieluhr ist `time` in `Save.save`.

Nebenbei: `goodsTrends` wuchs von 51 auf 54 Reihen. Das Spiel legt eine Reihe
offenbar erst an, wenn die Ware zum ersten Mal auftaucht.

## Ein Modell für die Ungeduld, das sich rechnen lässt

Die Ungeduld **fiel** über den Messzeitraum, obwohl sie laufend zunimmt. Der
Save nennt beide Größen: `reputationPenaltyPerSec = 0,00425` und
`reputationPenaltyBonusRate = −0,4`. Damit lässt sich prüfen, wie viel ein
Reputationspunkt wegnimmt:

| Annahme | Zuwachs über 597,41 s | Ungeduld je Reputationspunkt |
|---|---|---|
| Bonusrate ignoriert | 2,539 | 1,491 |
| Bonusrate angewandt | 1,523 | **0,988** |

Mit angewandter Bonusrate kommt fast genau **1,0** heraus — der Wert, den die
Recherche für Prestige unter 14 nennt (ab Prestige 14 halbiert er sich auf
0,5). Zwei Dinge fallen damit zusammen, die unabhängig voneinander sind: eine
Behauptung aus dem Dokument und eine Rechnung aus meinem Spielstand.

Das ist noch keine Gewissheit — ein einziges Intervall, und die Werte stammen
aus Schreibzeitpunkten, nicht aus exakten Momentaufnahmen. Aber es ist ein
Modell für die Ungeduldsvorhersage, das aus dem Save allein gefüttert werden
kann, und der nächste Lauf prüft es mit.

---

# Dritter watch-Lauf: der Siegmoment, und die letzte offene Frage ist beantwortet

## Die Zeitreihen haben eine Auflösung von 10 Spielzeitsekunden

| Intervall | geänderte Stellen | Spielzeit | je Stützstelle |
|---|---|---|---|
| 1 | 29 (ab Index 75) | 299,4 s | 10,3 s |
| 2 | 30 (ab Index 104) | 298,8 s | 10,0 s |
| 3 | 19 (ab Index 134) | 184,4 s | 9,7 s |

Der Schreibzeiger wandert um 29 bis 30 Stellen je Schreibvorgang durch das
Feld — genau das Ringpufferverhalten, das die Vermutung nahegelegt hatte.
**180 Plätze mal 10 Sekunden sind 1800 Spielzeitsekunden, also eine halbe
Stunde Spielzeit Vorgeschichte in jeder geschriebenen Datei.**

## Das kippt die Einordnung: Szenario B war zu pessimistisch

Meine Begründung für Szenario B lautete: der Parser sieht nur alle 300
Spielzeitsekunden einen Zustand und kann deshalb keine Verbrauchsrate bilden.
Das war falsch. Jeder Schreibvorgang liefert **dreißig frische Stützstellen im
Zehnsekundentakt**. `food_forecast` braucht eine Steigung, und die steht damit
präzise in der Datei — genauer, als zwei Momentaufnahmen im Abstand von 300
Sekunden es je hergäben.

Was bleibt: der **Pegel** ist bis zu 300 Spielzeitsekunden alt. Die Rate ist es
nicht. Aus letztem bekannten Bestand plus bekannter Rate mal verstrichener Zeit
lässt sich der aktuelle Stand fortschreiben, und der Fehler dieser
Fortschreibung ist klein, weil die Rate aus dreißig Messpunkten kommt.

**Folge für den Zuschnitt:** `read_hud()` ist keine Voraussetzung mehr, sondern
eine Verbesserung. Die Reihenfolge bleibt wie in der Spec vorgesehen:
**1 → 2 → 4 → 3 → 5.** Phase 3 schrumpft auf das, was wirklich nicht im Save
steht — die Auswahlbildschirme für Grundsteine und Baupläne — plus, wenn es
sich lohnt, die Restzeit der laufenden Jahreszeit.

## Der Siegmoment ist im Save sichtbar

Der letzte Schreibvorgang kam nach 184 statt 300 Spielzeitsekunden: das Spiel
war zu Ende. `reputation` stand auf **exakt 18,0**, `reputationToWin` auf 18.
Die Siegbedingung ist also direkt ablesbar, ohne Bildschirmauslesung.

Gleichzeitig schrieb `WorldSave.save` erstmals mehr als null Bytes (+628),
`cycle.year` sprang von 26 auf 39 und `wonFieldPopulation` von 0 auf 31.
`MetaSave_GameWonBackup.save` wurde im selben Bündel angelegt.

Und `MetaSave.gameTime` steht doch nicht still: es sprang von 7527,31738 auf
7144,5083 — beim Spielende. Meine frühere Aussage war in der Sache richtig
(als Uhr während eines Laufs unbrauchbar), in der Begründung falsch: das Feld
wird am Laufende geschrieben, nicht nie.

## Das Ungeduldsmodell steht — und es rechnet in ganzen Punkten

Drei Intervalle, drei Treffer:

| Intervall | Spielzeit | Δ Reputation | volle Punkte | Δ Ungeduld | erwartet | Abweichung |
|---|---|---|---|---|---|---|
| 1 | 299,40 s | +0,6051 | 0 | +0,7664 | +0,7635 | 0,0029 |
| 2 | 298,82 s | +1,0271 | 1 | −0,2336 | −0,2380 | 0,0044 |
| 3 | 184,38 s | +3,3635 | 4 | −3,5271 | −3,5298 | 0,0028 |

Das Modell:

```
Ungeduld += reputationPenaltyPerSec * (1 + reputationPenaltyBonusRate) * Δt
Ungeduld -= 1,0 * (Anzahl überschrittener ganzer Reputationspunkte)
```

Mit `0,00425 * 0,6 = 0,00255` je Spielzeitsekunde. Entscheidend ist der zweite
Teil: die Gutschrift kommt **je vollem Punkt**, nicht anteilig. Rechnet man
anteilig, kommen 0,00 · 0,97 · 1,19 heraus — kein konstanter Faktor. Rechnet
man in ganzen Punkten, stimmt es dreimal auf vier Tausendstel.

Damit ist `impatience_forecast()` für Phase 4 vollständig bestimmt, aus dem
Save allein, ohne Wiki. Und es bestätigt beiläufig die Recherche, die 1,0 für
Prestige unter 14 nennt.

## Zwei Fehler im Werkzeug, die dieser Lauf aufgedeckt hat

**Mein eigenes Werkzeug hat eine These bestätigt, die es selbst widerlegt
hatte.** Der Bericht meldete „Recherche behauptet 120 bis 180s: bestaetigt".
Die Prüfung lief gegen den **Wanduhr**-Median, und bei 1,74- bis 2,23-facher
Geschwindigkeit landen 300 Spielzeitsekunden bei 134 bis 172 Wanduhrsekunden —
zufällig mitten im behaupteten Fenster. Die Prüfung läuft jetzt gegen die
Spielzeit und sagt dazu, warum der Wanduhrwert dafür nichts taugt.

**Der Zeitreihen-Fühler nahm die erste Reihe als Beispiel.** Das war
`[Crafting] Oil`, konstant auf 4 — also meldete er „unveraendert", während
sich 56 andere Reihen bewegten. Er nimmt jetzt die lebendigste Reihe und
bildet zusätzlich eine Prüfsumme über alle; ändert sich die Beispielreihe
nicht, sagt der Bericht, ob die Prüfsumme sich trotzdem geändert hat.

## Phase 0 ist abgeschlossen

| Frage | Befund |
|---|---|
| Container | `plain-json`, unkomprimiert, 8,5 MB, in 0,1 s geparst |
| Sprache | englische IDs, null Umlaute in 400 Strings |
| Schreibtakt | ~300 Spielzeitsekunden, plus manuelles Speichern und Spielende |
| Bündel | vier Dateien, nicht atomar (bis 2 s Versatz) |
| Vorgeschichte | 180 Stützstellen à 10 Spielzeitsekunden je Ware und Kategorie |
| Zuschnitt | **Parser trägt Phase 2 und die Nahrungsvorschau**, Phase 3 nur Auswahlbildschirme |
