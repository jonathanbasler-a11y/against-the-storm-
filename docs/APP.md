# Das Fenster

Ein Doppelklick, und die Lage steht neben dem Spiel: Jahr, Bevölkerung,
Reputation und Ungeduld mit Balken, Nahrungsreichweite in Minuten, die
Verarbeitungsketten mit Engpass — und auf Wunsch eine Empfehlung von Claude.

```powershell
python ats-gui.pyw
```

Die Endung ist der Punkt: Windows startet `.pyw` mit `pythonw.exe`, also
**ohne Konsolenfenster daneben**.

## Auf den Desktop legen

```powershell
python tools\verknuepfung.py
```

Legt „ATS Assistent“ auf den Desktop und ins Startmenü. Die Verknüpfung
zeigt auf `pythonw.exe` neben genau dem Python, das den Befehl ausführt —
nicht auf den Platzhalter aus dem Microsoft Store (`…\WindowsApps\python.exe`),
den `Get-Command python` oft findet. Mit `--nur-desktop` nur auf den Desktop,
mit `--testen` startet das Fenster gleich einmal. Danach: Rechtsklick auf die
Verknüpfung → *An Taskleiste anheften*.

Ohne Skript: Rechtsklick auf `ats-gui.pyw` → *Senden an* → *Desktop
(Verknüpfung erstellen)*. Das geht nur, wenn `.pyw` bei dir mit Python
verknüpft ist.

Wenn das Fenster kommentarlos nicht aufgeht: `python ats-gui.pyw` einmal in
PowerShell starten — dort steht der Grund.

## Aktualisieren

Der Knopf „Aktualisieren“ unten rechts holt die neue Version
(`git pull --ff-only`) und fragt, ob das Fenster neu starten soll — ohne
Konsole. Ist lokal etwas geändert, bricht git ab und der Grund steht in der
Statuszeile. Neue Python-Pakete holt der Knopf nicht; dafür bleibt
`pip install` in PowerShell.

## Was drin ist

| Reiter | |
|---|---|
| **Lage** | Jahr, Biom, Prestige, Bevölkerung, Feindseligkeit; Reputation und Ungeduld als Balken gegen ihre Schwelle; wie lange die Nahrung reicht und wie lange bis zur Niederlage |
| **Nahrung** | Die drei Sätze — Empfehlung, Begründung, Alternative — darunter jede Kette, die der Bestand trägt: Gebäude, Einsatz, gewonnene Sättigung, Faktor, Engpass, Arbeitszeit, gewonnene Reichweite |
| **Auswahl** | „Bildschirm lesen" bei offener Grundstein- oder Bauplanwahl; oder die Namen von Hand eintippen, mit Komma getrennt |
| **Rat** | Claude bekommt die Lage als JSON und antwortet in drei Sätzen |

Unten steht, was fehlt, und ein Suchfeld für den Nachschlag.

## Es aktualisiert sich selbst

Das Fenster sieht alle drei Sekunden nach, ob das Spiel geschrieben hat, und
rechnet dann neu. Das Spiel speichert etwa alle **300 Spielzeitsekunden** —
dazwischen passiert nichts, und in der Kopfzeile steht, wie alt die Zahlen
sind („gerade eben", „vor 4 min gelesen"). Ohne diese Angabe würde aus einem
fünf Minuten alten Bestand eine Behauptung über jetzt.

## Der Reiter „Rat"

Er schickt eine **kompakte Lage als JSON** an Claude — Zahlen und Namen.
**Nie ein Bild**, auch nicht aus dem Auswahlhelfer: dort gehen nur die
erkannten Namen mit. Das wird vor jedem Absenden geprüft, nicht gehofft.

| | |
|---|---|
| Modell | `claude-opus-5`, rund **1,5 Cent je Frage**. Umschaltbar auf `claude-sonnet-5` (~0,6 Cent) |
| Aufwand | Höher, wenn eine Wahl ansteht — eine Nahrungsfrage braucht kein tiefes Nachdenken, eine Grundsteinwahl schon |
| Regeln | Aus `.claude/skills/ats-advisor/SKILL.md`, derselben Datei, nach der sich Claude Code richtet |

Voraussetzung: `pip install anthropic`, dazu eine Anmeldung. Entweder

```powershell
setx ANTHROPIC_API_KEY sk-ant-...
```

(danach ein **neues** PowerShell-Fenster, `setx` wirkt nicht rückwirkend),
oder `ant auth login` — das SDK findet beides von selbst.

Ob eine Anmeldung da ist, steht **unter dem Reiter, bevor man fragt**. Früher
kam die Auskunft erst nach dem Druck auf „Fragen" — eine Runde zu spät, und am
Spielrechner stand dort der englische Rohtext des SDK. Geprüft wird ohne eine
einzige Anfrage: dieselben drei Quellen, die das SDK selbst nimmt
(`api_key`, `auth_token`, das Profil aus `ant auth login`).

**Ohne Anmeldung läuft alles andere unverändert.** Der Knopf „Lage kopieren"
legt dasselbe JSON in die Zwischenablage; das fügst du in Claude ein und
bekommst dieselbe Auskunft, nur von Hand.

## Wenn tkinter fehlt

Der Starter sagt es in einem Fenster statt in einer Konsole, die niemand
sieht. Behebung: Python-Installer erneut starten, *Modify* wählen und
**„tcl/tk and IDLE"** ankreuzen.

## Was es nicht tut

Es klickt nichts, es ändert keinen Spielstand, es liest nur. Und es rechnet
selbst nichts aus — jede Zahl kommt aus denselben Werkzeugen, die auch der
MCP-Server und die Kommandozeile benutzen. Das Fenster ist eine Ansicht,
keine zweite Wahrheit.
