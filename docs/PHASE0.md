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

## Danach

Erst wenn die Vorlage ausgefüllt ist und du sie freigegeben hast, fange ich mit
Phase 1 an. Kein Produktcode vorher.
