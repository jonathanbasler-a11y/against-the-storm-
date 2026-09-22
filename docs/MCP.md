# Den Server starten

Die Werkzeuge stehen in `tools_api` als gewöhnliche Funktionen. Der MCP-Server
ist nur die Hülle — und diese Hülle hängt an Claude, nicht am Spiel.

## Erst prüfen, dann einhängen

```powershell
python tools\mcp_start.py --pruefen
```

Ruft jedes Werkzeug einmal auf und zeigt, was es *jetzt gerade* sagen würde:

```
Was der Server vorfindet:
  Spielordner   C:\Users\Joni\AppData\LocalLow\...   gefunden
  Mitschriften  C:\Users\Joni\against-the-storm-\runs   2 Datei(en)
  Wissensbasis  C:\Users\Joni\against-the-storm-\kb.sqlite   2266 Namen
                biomes=10, buildings=117, cornerstones=398, ...

Werkzeuge:
  ok      get_state            24 Felder
  ok      query_kb             2 Felder
  stumm   food_forecast        Es braucht zwei Spielstände
  --      log_event            schreibt in die Mitschrift
```

**`stumm` heißt nicht kaputt.** Es heißt, dass eine Eingabe fehlt — meistens
eine zweite Mitschrift, denn `food_forecast` braucht zwei Zustände, um eine
Rate zu bilden. Nach dem nächsten Speichervorgang des Spiels geht es.

Ein Server, der läuft und auf jede Frage „nichts gefunden" antwortet, ist
schwerer zu finden als einer, der gar nicht startet. Deshalb dieser Lauf.

## Was schiefgehen kann, und warum es das nicht mehr tut

**Das Arbeitsverzeichnis.** Claude startet den Server als eigenen Prozess, mit
einem Arbeitsverzeichnis, das niemand bestimmt hat. Ein relatives
`kb.sqlite` zeigt dann irgendwohin — und weil `kb.connect` eine fehlende
Datenbank anlegt, entsteht dort eine leere. Der Server läuft, antwortet auf
alles „nichts gefunden", und nichts sagt einem, warum. Deshalb löst
`aufloesen()` relative Pfade gegen das Projektverzeichnis auf, und `--pruefen`
schreibt hin, welche Datei tatsächlich benutzt wird.

**Der fehlende Spielordner.** `read_state` wirft absichtlich nicht, wenn
Dateien fehlen — ein halbes Bündel ist besser als ein Absturz. Bei einem
leeren Ordner ist das aber kein halbes Bündel, sondern gar keins, und ein
leerer Zustand sieht aus wie eine Siedlung ohne Bevölkerung. `get_state` sagt
das jetzt: `verfuegbar: false` mit dem Ordner, unter dem nichts lag.

## Einhängen

Voraussetzung: `pip install mcp`

### Claude Code im Projektordner

`.mcp.json` liegt im Repo und wird von selbst gefunden:

```json
{
  "mcpServers": {
    "ats": { "command": "python", "args": ["tools/mcp_start.py"] }
  }
}
```

Das ist der kürzere Weg: der Berater-Skill unter `.claude/skills/ats-advisor`
wird im selben Zug mitgeladen.

### Claude Desktop

`%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ats": {
      "command": "C:\\Pfad\\zu\\python.exe",
      "args": ["C:\\Users\\Joni\\against-the-storm-\\tools\\mcp_start.py"]
    }
  }
}
```

Den Pfad zu `python.exe` liefert `python -c "import sys; print(sys.executable)"`.
Er muss ausgeschrieben sein: der Fensterprozess erbt den PATH der Konsole
nicht.

`tools/mcp_start.py` legt das Paket selbst in den Suchpfad, deshalb braucht
die Konfiguration keine Umgebungsvariablen und kein installiertes Paket.

## Was der Server protokolliert

`logs/mcp_server.log` im Projektordner, unabhängig vom Arbeitsverzeichnis.
Beim Start steht dort, was gefunden wurde und was fehlt — das ist die erste
Stelle, an der man nachsieht, wenn die Antworten leer bleiben.
