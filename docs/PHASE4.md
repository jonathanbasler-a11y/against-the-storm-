# Phase 4 — MCP-Server

Die Werkzeuge stehen in `src/ats_assistant/tools_api.py` als gewöhnliche
Funktionen. `mcp_server.py` ist nur die Hülle darum. Das hat einen Grund: so
sind sie ohne MCP aufrufbar und testbar, und der Server enthält keine Logik,
die sich nur im laufenden Betrieb prüfen ließe.

```powershell
uv run ats-mcp --save-dir "%USERPROFILE%\AppData\LocalLow\Eremite Games\Against the Storm"
uv run ats-mcp --list-tools          # ohne MCP, nur die Liste
```

## Werkzeuge

| Werkzeug | Zustand | Quelle |
|---|---|---|
| `get_state` | fertig | Spielstand |
| `query_kb` | fertig, Waren vollständig | `kb.sqlite` |
| `food_forecast` | fertig | Zeitreihe aus zwei Spielständen |
| `impatience_forecast` | fertig | gemessenes Modell |
| `log_event` | fertig | `runs/*.jsonl` |
| `analyze_runs` | fertig | `MetaSave.gamesHistory` |
| `read_choice` | **fehlt** | Phase 3 |

`impatience_forecast` steht nicht in der Spec. Es ist dazugekommen, weil das
Modell aus Phase 0 vollständig bestimmt ist und die Ungeduld neben der Nahrung
die zweite Verlustbedingung ist.

## Was das Modell zu sehen bekommt

`get_state` gibt Zahlen und Namen — **nie die Zeitreihen**. Die haben 180
Stützstellen je Ware, also zehntausende Zahlen, und haben im Kontext eines
Sprachmodells nichts verloren. Was aus ihnen folgt, rechnet `food_forecast`
aus und gibt drei Zahlen zurück. Das ist das Leitprinzip der Spec, an der
Schnittstelle durchgesetzt statt nur beschrieben.

Ein Test hält das fest: im Ergebnis von `get_state` darf keine Zeitreihe
auftauchen, nur die Liste ihrer Namen.

## Was `analyze_runs` kann und was nicht

Es liest die Laufhistorie, die das Spiel selbst führt: Sieg oder Niederlage,
Biom, Schwierigkeit, Jahre, verwendete Gebäude und Grundsteine. Daraus wird
eine Gegenüberstellung — welche Grundsteine kommen in Siegen häufiger vor als
in Niederlagen.

Es sagt dazu, **worauf die Aussage beruht**. Unter drei Läufen je Seite gilt
sie als nicht belastbar, und die Kurzfassung endet dann mit „Diese
Gegenüberstellung ist ein Hinweis, kein Befund." Bei zwanzig Läufen, von denen
fünf verloren sind, ist jede Aussage über die Niederlagen dünn — das gehört
dazugesagt, nicht weggelassen.

Den Zustand zwei Minuten vor dem Kipppunkt, den die Spec verlangt, kann erst
die eigene Mitschrift liefern: die Laufhistorie des Spiels kennt nur
Endzustände. `analysis.tipping_point()` ist dafür da und gibt `None` zurück,
solange die Spieluhr in den Einträgen fehlt — statt eine Zahl zu erfinden.
