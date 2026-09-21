# Design-Prompt: Against the Storm Assistant

> Dieses Dokument ist als Startprompt für Claude Code gedacht. Ablegen als
> `SPEC.md` im Projektwurzelverzeichnis, dann Claude Code darauf ansetzen.

---

## Rolle

Du baust mit mir zusammen einen lokalen Spielassistenten für *Against the Storm*
(Version 1.10.4, deutsche Spieloberfläche, Windows, Python 3.12). Ich spiele auf
Prestige 13 und verliere Läufe überwiegend an zwei Dingen: Nahrungsmangel im
ersten Jahr und Fehlentscheidungen bei Grundstein- und Bauplanauswahl.

Arbeite phasenweise. Nach jeder Phase hältst du an, zeigst mir das Ergebnis und
wartest auf Freigabe. Baue nicht auf Verdacht weiter.

## Leitprinzip

**Das Sehen passiert lokal und deterministisch, das Urteilen passiert im Modell.**

Es wird niemals ein Vollbild-Screenshot pro Sekunde an ein Sprachmodell
geschickt. Bildschirminhalte werden lokal in kompaktes JSON übersetzt. Das
Modell bekommt Zahlen und Namen, keine Bilder. Grund: Latenz, Kosten und
Nutzungslimits.

## Nicht-Ziele

- Kein automatisches Klicken oder Steuern des Spiels. Der Assistent beobachtet
  und berät, er spielt nicht.
- Keine Save-Manipulation. Nur lesen.
- Keine Cloud-Abhängigkeit für die Kernfunktionen. Wissensbasis und Parser
  laufen offline.
- Kein Dauerbetrieb mit Modellaufrufen. Das Modell wird punktuell gefragt.

---

## Phase 0 — Machbarkeit klären

**Bevor du Code schreibst, klär diese drei Fragen und berichte mir.**

1. **Save-Format.** Saves liegen unter
   `%USERPROFILE%\AppData\LocalLow\Eremite Games\Against the Storm`.
   Relevant sind `Save.save` (laufende Siedlung) und `MetaSave.save`
   (Metafortschritt). Berichte aus 2023/24 sprechen von unverschlüsseltem,
   textbasiertem Inhalt mit über 300.000 Zeilen. Prüfe für meine Version:
   - Beginnt die Datei mit `{`? Dann direkt JSON.
   - Beginnt sie mit den Bytes `1f 8b`? Dann gzip, danach JSON.
   - Sonst: Hexdump der ersten 256 Bytes zeigen und Formathypothese aufstellen.
2. **Schreibzeitpunkt.** Wann schreibt das Spiel die Datei? Autosave-Intervall
   messen, indem du Änderungszeitpunkte über zehn Minuten protokollierst. Davon
   hängt ab, wie viel der Parser überhaupt abdecken kann.
3. **Sprache.** Prüfe, ob im Save interne englische IDs stehen oder lokalisierte
   deutsche Strings. Falls IDs: Jubel, das löst das Lokalisierungsproblem.

**Ergebnis von Phase 0** ist eine kurze Entscheidungsvorlage: Wie viel schafft
der Parser, wie viel muss über den Bildschirm kommen. Erst danach weiter.

---

## Phase 1 — Wissensbasis

Eine lokale SQLite-Datenbank `kb.sqlite` mit den Spieldaten. Quelle ist das
offizielle Wiki unter `wiki.hoodedhorse.com/Against_the_Storm/`.

**Tabellen (Minimum):**

| Tabelle | Inhalt |
|---|---|
| `resources` | Name, Kategorie, Herkunftsvorkommen, erntendes Lager, Biome |
| `biomes` | Effekte, Baumarten mit Bonusressourcen, Knotengewichtungen, Besonderheiten |
| `cornerstones` | Name, Seltenheit, Effekttext, Quelle (jährlich/Händler/Auftrag/Altar), Preis |
| `buildings` | Name, Kosten, Rezepte, Spezialisierung, Arbeiterplätze |
| `species` | Spezialisierung, Grund-Entschlossenheit, Haustyp, Bedürfnisse |
| `prestige` | Stufe 1–20 mit Modifikatorname und Effekt |
| `recipes` | Eingang, Ausgang, Verhältnis, Gebäude |
| `glade_events` | Name, Anforderungen, Belohnung, Endeffekt bei Versagen |

**Kritisch: Tabelle `name_map`.** Spalten `en`, `de`, `kind`, `confidence`,
`source`. Die deutschen Namen stehen nirgends öffentlich. Sie werden aus meinen
Screenshots befüllt (siehe Phase 3) und zunächst als `guessed` markiert. Bestätigt
wird ein Eintrag erst, wenn er aus einem Screenshot gelesen wurde. Alle Ausgaben
an mich nutzen die deutschen Namen, intern wird englisch gerechnet.

**Bekannt gesicherte deutsche Begriffe zum Seed:** Entschlossenheit (Resolve),
Ungeduld (Impatience), Grundstein (Cornerstone), Bernstein (Amber), Teile (Parts),
Schwelende Stadt (Smoldering City), Uralte Feuerstelle (Ancient Hearth), Gefährliche
Lichtung (Dangerous Glade), Komplexe Nahrung, Dienste, Königswälder, Felsschlucht,
Bambusebene, Sägewerk, Primitive Werkbank, Trapperlager, Fluffschnabel, Gutsgericht.

**Scraper-Regeln:** höflich crawlen (1 Anfrage pro Sekunde), Rohseiten in
`cache/` ablegen, Wiki-Versionsstand pro Seite mitspeichern. Das Wiki ist
stellenweise auf Spielversion 1.8 bis 1.9 — bei Abweichung zur Spielversion
einen Warnhinweis an den Datensatz hängen, nicht stillschweigend ausliefern.

---

## Phase 2 — Save-Parser

Modul `save_reader.py`.

- Beobachtet die Save-Datei mit `watchdog`, parst bei jeder Änderung.
- Liefert ein normalisiertes `GameState`-Objekt: Biom, Jahr, Jahreszeit,
  Prestige-Stufe, aktive Weltmodifikatoren, Bevölkerung je Spezies,
  Entschlossenheit je Spezies, Feindseligkeit, Ungeduld, Reputation,
  Lagerbestände, gebaute Gebäude mit Arbeiterzahl, entdeckte Lichtungen,
  bekannte Vorkommen mit Restladungen, gewählte Grundsteine.
- Schreibt jeden Zustand als Zeile in `runs/<run_id>.jsonl`. Das ist die
  Grundlage für die spätere Auswertung.
- Robust gegen Formatänderungen: unbekannte Felder werden ignoriert, fehlende
  Felder machen `None`, kein harter Abbruch.

**Akzeptanzkriterium:** Ich lade einen Spielstand, du gibst mir den Zustand als
lesbare Tabelle aus, und die Zahlen stimmen mit dem überein, was ich im Spiel
sehe.

---

## Phase 3 — Bildschirmauslesung

Modul `screen_reader.py`. Nur für das, was der Parser nicht liefert.

- `mss` für Screenshots, ausgelöst per globalem Hotkey, nicht per Timer.
- **Template-Matching mit OpenCV für Symbole.** Die Spielsymbole sind ein fester
  Sprite-Satz. Lege ein Verzeichnis `templates/` mit je einem Ausschnitt pro
  Ressource, Spezies und Gebäude an und erkenne per Kreuzkorrelation. Das ist
  deterministisch und kostet nichts — im Gegensatz zu Bilderkennung durch ein
  Modell, die genau hier Fehler macht.
- Tesseract nur für Zahlen und für Textzeilen, die ich als neue deutsche Namen
  in `name_map` aufnehmen will. Deutsches Sprachmodell laden.
- Regionen werden einmalig kalibriert und in `regions.yaml` gespeichert, relativ
  zur Auflösung. Ein Kalibrier-Assistent führt mich durch: „klick auf die
  Feindseligkeitsanzeige" und so weiter.

**Zwei Erfassungsmodi:**

1. `read_hud()` — die Live-Leiste: Jahreszeit, Restzeit, Feindseligkeit,
   Ungeduld, Entschlossenheit je Spezies, Bevölkerung.
2. `read_choice_screen()` — Auswahlbildschirme: Grundsteine, Baupläne,
   Karawanen, Warenangebote. Liest Optionstitel und Effekttexte.

**Akzeptanzkriterium:** Ein Auswahlbildschirm wird in unter einer Sekunde in
korrektes JSON überführt, inklusive der deutschen Optionsnamen.

---

## Phase 4 — MCP-Server

Modul `mcp_server.py`, Anbindung an Claude Code, gleiche Bauart wie mein
bestehender ComfyUI-Server.

**Tools:**

- `get_state()` — aktueller Zustand aus Parser plus HUD.
- `read_choice()` — aktueller Auswahlbildschirm als strukturierte Optionen.
- `query_kb(entity, name)` — Nachschlag in der Wissensbasis, akzeptiert
  deutsche und englische Namen.
- `food_forecast()` — reine Arithmetik, kein Modell: Verbrauchsrate gegen
  Produktionsrate, Vorhersage des Bestands zum nächsten Sturmbeginn,
  Warnschwelle bei Reichweite unter einer Jahreszeit.
- `log_event(text)` — Freitextnotiz in den Lauf schreiben.
- `analyze_runs(n)` — die letzten n Läufe gegenüberstellen: Zustand zwei Minuten
  vor dem Kipppunkt, was unterschied gewonnene von verlorenen Läufen.

---

## Phase 5 — Entscheidungslogik

Als Claude-Code-Skill `ats-advisor` mit folgenden Heuristiken, die aus der
aktuellen Spielsituation heraus angewandt, nicht stur abgearbeitet werden:

- **Nahrung schlägt alles im ersten Jahr.** Nahrungsmangel ist die einzige
  Situation ohne Ausweichweg. Vor jeder Empfehlung prüfen, ob die
  Nahrungsversorgung für die nächsten zwei Jahreszeiten steht.
- **Ab Prestige 10 schlägt Feindseligkeitssenkung fast jeden Wirtschaftsbonus.**
- **Ein Produktionsbonus auf etwas, das ich nicht herstelle, ist wertlos.** Immer
  gegen die tatsächlich gebauten Gebäude und die Vorkommen auf der Karte prüfen.
- **Biomspezifika berücksichtigen:** Korallenwald hat keine Getreideknoten;
  Bambusebene hat keinen natürlichen fruchtbaren Boden; Felsschlucht liefert kein
  Holz aus Bäumen.
- **Prestige-Modifikatoren einrechnen:** auf 13 sind zwei Bauplan- und zwei
  Grundsteinoptionen weniger verfügbar, Waren sind beim Verkauf 50 Prozent
  weniger wert, die Zystenrate ist verdoppelt, Späher arbeiten an Ereignissen
  33 Prozent langsamer.
- **Jährliche Grundsteine sind in Jahr 2, 4 und 6 Legendary.** Rerolls dafür
  aufheben.

**Ausgabeformat für eine Auswahlempfehlung:** eine Empfehlung, ein Satz
Begründung, ein Satz zur besten Alternative und wann sie besser wäre. Keine
Aufzählung aller Optionen, keine Vorrede.

---

## Technische Vorgaben

- Python 3.12, `uv` für Abhängigkeiten, alles in einem Repo.
- Keine Abhängigkeit, die einen laufenden Dienst im Hintergrund braucht, außer
  dem MCP-Server selbst.
- Tests für Parser und Wissensbasis mit echten Beispieldaten in `tests/fixtures/`.
- Logging nach `logs/`, standardmäßig auf INFO, keine Screenshots persistieren
  außer im Debug-Modus.

## Reihenfolge und Abbruchkriterium

Phase 0 → 1 → 2 → 4 (mit `query_kb` und `food_forecast`) → 3 → 5.

Die Bildschirmauslesung kommt bewusst spät: Wenn Phase 0 ergibt, dass der Save
lesbar ist und häufig genug geschrieben wird, schrumpft Phase 3 auf wenige
Live-Zahlen. Fällt Phase 0 negativ aus, wird Phase 3 zur Hauptarbeit — dann
reden wir vorher noch einmal über den Zuschnitt.

## Erste Aufgabe

Beantworte Phase 0. Schreibe dafür ein kleines Diagnoseskript, lass es laufen,
und leg mir das Ergebnis samt Empfehlung vor. Schreib noch keinen Produktcode.
