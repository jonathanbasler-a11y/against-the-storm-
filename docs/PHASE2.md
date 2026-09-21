# Phase 2 — Save-Parser und Mitschrift

## Ausführen

```powershell
uv run ats-watch --save-dir "%USERPROFILE%\AppData\LocalLow\Eremite Games\Against the Storm"
```

Läuft mit, während du spielst, und schreibt jeden neuen Zustand als Zeile nach
`runs/<lauf>.jsonl`. Das ist die Grundlage für `food_forecast` (braucht zwei
Zustände) und für `analyze_runs`.

## Was aus den Messungen in den Code geflossen ist

**Das Bündel ist nicht atomar.** Gemessen wurden 2,02 Sekunden Versatz
zwischen `MetaSave.save` und `Save.save`. Wer auf die erste Änderung reagiert,
liest eine Datei neu und die andere alt. `wait_for_quiet()` wartet deshalb, bis
sich drei Sekunden nichts mehr rührt.

**Präfixe stapeln sich.** `[SSE] [BIOME] Storm Penalty` stand so im
Spielstand. Das Abschneiden schleift, sonst entstehen zwei Schlüssel für
dieselbe Sache.

**Die Pfade sind nur teilweise bekannt.** Jedes Feld wird zweistufig
aufgelöst — erst bekannter Pfad, dann flachster Schlüssel mit passendem Namen
— und es wird protokolliert, woher der Wert kam. Der flachste Fund gewinnt,
weil ein `season` tief in einer Vorlage nichts über den geführten Wert sagt.

**`difficulty` ist ein String.** `"Prestige 16 Ascension XIII"`. Der Rohwert
bleibt erhalten, die Stufe kommt aus der römischen Zahl.

## Zwei Fehler, die Tests gefunden haben

**Der Beobachter hätte den nächsten Lauf komplett verschluckt.** Nach einem
beendeten Lauf fängt die Spieluhr wieder bei null an. Meine Prüfung lautete
„Spielzeit kleiner oder gleich der letzten → überspringen", und damit wäre
jeder Zustand der neuen Siedlung verworfen worden, dauerhaft. Jetzt wird
unterschieden: gleiche Zeit heißt derselbe Zustand, zurückgesprungene Zeit
heißt neuer Lauf.

**Zwei Läufe am selben Tag hätten sich eine Datei geteilt.** Die Kennung
enthielt nur das Datum. Damit läge in einer Mitschrift ein Zeitsprung
rückwärts, und jede Auswertung über den Verlauf wäre hinüber. Die Kennung
trägt jetzt die Uhrzeit.

Beide Fehler wären im Betrieb erst aufgefallen, wenn schon Daten verloren
gewesen wären.
