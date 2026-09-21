# Bewertung der beigelegten Recherche

Bezug: „Systems Architecture and Algorithmic Strategy for Against the Storm at
High Prestige" (Gemini, eingegangen 2026-09-21).

## Kurzantwort

Ja, sie hilft — aber nicht als Befund, sondern als Hypothesenliste. Sie ersetzt
Phase 0 nicht um eine Minute, denn sie behauptet genau das, was Phase 0 messen
soll. Nützlich sind drei Dinge: die konkreten JSON-Pfade, die
Kategoriepräfix-Konvention, und eine Namenstabelle mit 125 Einträgen. Alles
davon ist billig überprüfbar, und überprüft gehört es, weil das Dokument an
mehreren Stellen nachweislich rechnet statt zu wissen.

## Was davon trägt

**1. Die Parser-Hypothesen sind konkret genug, um widerlegt zu werden.** Das
Dokument nennt Pfade statt Andeutungen: `gameObjectives.reputationPenalty` für
die Ungeduld, `reputationSources` als Vierervektor, `racesReputationGains`,
`producedGoods`, `storage.goods`, `nextGoodsPerMinTick` als Simulationsuhr. Ob
sie stimmen, entscheidet dein Spielstand in einer Sekunde — deshalb prüft
`tools/phase0_diagnose.py` sie jetzt beim `inspect`-Lauf einzeln mit und meldet
je Pfad *bestätigt*, *anderer Pfad* (Schlüssel existiert woanders, mit Fundort)
oder *nicht gefunden*.

**2. Die Kategoriepräfix-Konvention ist die wichtigste Einzelbehauptung.**
Waren sollen als `[Food Raw] Meat`, `[Mat Processed] Bricks`, `[Metal]
Crystalized Dew` im Save stehen. Trägt das, dann liefert der Save die
Warenkategorie gratis mit — die Unterscheidung Rohnahrung gegen komplexe
Nahrung, an der bei dir die Läufe kippen, wäre damit direkt aus dem Spielstand
ablesbar statt aus der Wissensbasis nachgeschlagen. Das Skript scannt jetzt
Schlüsselnamen *und* Stringwerte auf dieses Muster und listet die gefundenen
Kategorien auf.

**3. Englische IDs trotz deutscher Oberfläche.** Deckt sich mit deiner
Vermutung in Phase 0 („Falls IDs: Jubel"). Wird von der Sprachprobe ohnehin
geprüft.

**4. Der Schreibtakt ordnet das Projekt ein.** Behauptet werden Flushes bei
Jahreszeitenwechsel, Aufträgen, Lichtungsereignissen, manueller Pause und ein
Heartbeat alle 120 bis 180 Sekunden. Das wäre **Szenario A** aus
`docs/PHASE0.md`: Parser trägt Phase 2 allein, Phase 3 schrumpft auf Restzeit
und Auswahlbildschirme. `watch` prüft die Heartbeat-Spanne jetzt explizit.

**5. Die Namenstabelle spart einen Abend Screenshot-Sammeln.** 125 Paare liegen
jetzt als `data/name_map_seed.csv` vor, mit Spalten `confidence` und `source`.
Siehe aber die Zirkularitätswarnung unten.

## Was daran nicht trägt

**Die Übereinstimmung mit deinen gesicherten Begriffen beweist nichts.** 16 der
18 in `SPEC.md` als gesichert markierten deutschen Begriffe kommen in der
Recherche vor, und alle 16 stimmen überein. Das klingt nach Bestätigung, ist
aber vermutlich zirkulär: das Dokument zitiert durchgängig eine Quelle `[cite:
1]` für Dinge, die nur in deiner Spec stehen — Python 3.12, `kb.sqlite`,
`food_forecast`, `runs/<run_id>.jsonl`, Prestige 13. Quelle 1 ist deine Spec.
Ein Modell, dem man eine Begriffsliste gibt, gibt sie zurück; das ist kein
zweiter Zeuge. Die übrigen 109 Paare sind damit unbelegt, nicht halbbelegt.

**Eine ganze Tabellenspalte ist nachgerechnet statt erhoben.** Die Spalte
„Elapsed Time to Starvation Death" ist für alle sieben Spezies exakt
Hungertoleranz × Pausentakt:

| Spezies | Toleranz | Takt | Produkt | angegebene Untergrenze |
|---|---|---|---|---|
| Füchse | 3 | 120 s | 360 | 360 |
| Harpien | 4 | 100 s | 400 | 400 |
| Echsen | 12 | 100 s | 1200 | 1200 |
| Frösche | 5 | 150 s | 750 | 750 |
| Fledermäuse | 4 | 100 s | 400 | 400 |
| Menschen | 6 | 120 s | 720 | 720 |
| Biber | 6 | 120 s | 720 | 720 |

Sieben von sieben. Die Obergrenzen liegen 60, 60, 120, 100, 60, 80, 80 Sekunden
darüber und folgen keiner erkennbaren Regel. Die Spalte ist also keine zweite
Messung, sondern eine Multiplikation mit angehängtem Zuschlag — sie sieht in
der Tabelle aber aus wie unabhängige Evidenz. Genau so entstehen Zahlen, die
sich später in `kb.sqlite` nicht mehr von echten unterscheiden lassen.

**Die Warnschwelle für `food_forecast` stammt von einem Modifikator, der bei
dir nicht gilt.** Das Dokument setzt den Alarm bei 240 Sekunden Reichweite und
begründet das mit der Sturmdauer. Die verdoppelte Sturmdauer ist aber laut
derselben Tabelle die Prestige-**15**-Modifikation; auf 13 gilt nach den
eigenen Zahlen des Dokuments die Hälfte. Prestige-Modifikatoren sind kumulativ
bis zur gespielten Stufe, nicht darüber hinaus. Deine Spec formuliert die Regel
richtig: Warnschwelle bei Reichweite unter einer Jahreszeit. Die Schwelle gehört
also aus der gemessenen Jahreszeitenlänge berechnet, nicht als Konstante
hineingeschrieben.

**Die Zystenrate widerspricht deiner Spec.** Deine Spec sagt für Prestige 13
„die Zystenrate ist verdoppelt" (+100 %), die Recherche sagt zweimal +150 %.
Einer von beiden irrt. Das ist kein Detail, denn daran hängt, ob im dritten
Jahr ein oder zwei Fäulniskämpfer eingeplant werden. Das Wiki entscheidet, in
Phase 1.

**Die Feindseligkeitsformel ist als Formel unsauber notiert.** Der
Faktor 3,0 steht vor der Klammer, der Holzfällerterm mit 24 = 8 × 3,0
dahinter — rechnerisch dasselbe, aber ein Hinweis darauf, dass hier
zusammengeschriebenes Wissen steht, kein hergeleitetes. Außerdem wird 3,0 als
„difficulty multiplier across all Prestige levels" bezeichnet, also als
Konstante, die nicht von der Prestige-Stufe abhängt. Das ist in einem Dokument
über Prestige-Skalierung zumindest erklärungsbedürftig.

Der gute Teil daran: diese Formel ist **automatisch testbar**. Feindseligkeit,
Bevölkerung, Jahr, geöffnete Lichtungen und zugewiesene Holzfäller stehen alle
im `GameState`. Sobald `runs/*.jsonl` läuft, lässt sich die Formel über hundert
Zustände gegen die tatsächlich angezeigte Feindseligkeit prüfen. Das gehört als
kleine Funktion in Phase 4, nicht als Glaubenssatz in Phase 5.

**Das Dokument widerspricht sich zwischen Strategie und Formel.** Es empfiehlt,
Rohnahrung per Konsumsteuerung komplett zu sperren und ausschließlich über
komplexe Nahrung zu ernähren — und rechnet die Nahrungsreichweite dann als
Bestand geteilt durch Verbrauchsrate, also so, als wäre der Bestand
verfügbar. Bei gesperrter Rohnahrung ist nicht der Bestand die Schranke,
sondern der Durchsatz der Feldküche. Für `food_forecast` heißt das: die Formel
taugt als Fassung 1, muss aber zwischen essbarem und gesperrtem Bestand
unterscheiden, sonst meldet sie Sicherheit, während die Leute hungern.

## Was ich daraus gemacht habe

- `tools/phase0_diagnose.py` prüft die sieben behaupteten Pfade, die
  Präfix-Konvention, Container und Zeilenzahl gegen den echten Spielstand und
  meldet Treffer und Fehlschläge einzeln. Der Bericht sagt damit nicht nur
  „Save lesbar", sondern auch „Recherche in vier von sieben Punkten richtig".
- `data/name_map_seed.csv`: 125 Paare, jede Zeile mit `confidence` — 16
  `spec_seed` (aus deiner Spec), 109 `guessed` (aus der Recherche). Keine Zeile
  gilt als bestätigt, bis sie aus einem Screenshot gelesen wurde. Die Datei ist
  Rohmaterial für die `name_map` aus Phase 1, nicht deren Inhalt.
- Die Strategieregeln (Rohnahrungssperre, Feindseligkeit vor Wirtschaft, kleine
  Lichtungen nie, erste gefährliche Lichtung zu Beginn Jahr 2 Nieselregen,
  Holzfäller fünf Sekunden vor dem Sturm abziehen) decken sich mit deinen
  eigenen Leitsätzen und mit dem, was in der Community zirkuliert. Sie gehören
  als Kandidaten in Phase 5 — und als Erstes in die Laufauswertung, wo sie an
  deinen eigenen Läufen bestehen oder fallen.

## Vorschlag für die Überprüfung der Namenstabelle

Drei Screenshots reichen für eine belastbare Fehlerquote: Lagerübersicht,
ein Bauplan-Auswahlbildschirm, Speziesübersicht. Daraus lassen sich etwa
zwanzig Begriffe gegen die Tabelle halten. Stimmen achtzehn, ist der Rest
brauchbares Rohmaterial. Stimmen zwölf, wird die Tabelle verworfen und Phase 3
sammelt die Namen so ein, wie deine Spec es ohnehin vorsieht.

## Erste Stichprobe an der Namenstabelle (2026-09-21)

Grundlage: ein Screenshot der laufenden Siedlung, Auftragsleiste rechts,
Speziesleiste links. Daraus waren sieben Behauptungen der Tabelle prüfbar.

| Behauptung | UI zeigt | Ergebnis |
|---|---|---|
| `bricks` → Ziegel | „2/10 Ziegel" | richtig |
| `stonecutters_camp` → Steinmetzlager | „0/1 Steinmetzlager" | richtig |
| `coats` → Mäntel | „Bedürfnis nach Mäntel erfüllt" | richtig |
| `human` → Mensch | „MENSCHEN" | richtig (UI im Plural) |
| `beaver` → Biber | „BIBER" | richtig |
| `lizard` → Echse | „ECHSEN" | richtig (UI im Plural) |
| `pack_of_crops` → Erntepaket | „Feldfruchtpaket" | **falsch** |

Sechs von sieben. Dazu vier Begriffe, die im Bild stehen und in der Tabelle
überhaupt nicht vorkommen: **Öl**, **Komfort**, **Erntelager**,
**Handelswege**. Öl ist eine Ware und fehlt ersatzlos — die Recherche listet
über vierzig Ressourcen und hat sie nicht.

Zwei Folgerungen:

1. Die Tabelle ist brauchbares Rohmaterial, aber keine Quelle. Eine
   Fehlerquote in dieser Größenordnung heißt: jede Zeile, die in eine Ausgabe
   an den Spieler geht, muss vorher aus einem Screenshot bestätigt sein.
2. Der Fehler sitzt ausgerechnet in der Paketfamilie. Wenn `pack_of_crops`
   falsch ist, sind Proviantpaket, Baumaterialpaket, Handelswarenpaket und
   Luxuswarenpaket erst einmal genauso verdächtig — und die Recherche baut
   ihre ganze Prestige-9-Handelsstrategie auf Proviantpakete. Diese vier
   Zeilen sind in `data/name_map_seed.csv` entsprechend markiert.

Stand der Datei: 16 `spec_seed`, 10 `screenshot`, 3 `observed` (im Bild
gelesen, englische Entsprechung noch offen), 102 `guessed`.

## Was die Messung ergeben hat (2026-09-21)

| Behauptung | Messung | Ergebnis |
|---|---|---|
| unkomprimiertes JSON | `plain-json` | richtig |
| 250.000 bis 350.000 Zeilen | 359.438 | knapp daneben, Größenordnung stimmt |
| Kategoriepräfix `[Food Raw] Meat` | 112 Treffer | richtig |
| Kategorie `Food Complex` | heißt `Food Processed` | falsch |
| Kategorie `Trade Packs` | heißt `Packs` | falsch |
| Heartbeat 120 bis 180 s | nicht gemessen (Skriptfehler) | offen |

Die tragende Behauptung stimmt also: der Save ist lesbares JSON mit
kategorisierten Waren-IDs. Die Detailvokabeln stimmen teilweise nicht, und
vier Kategorien kennt die Recherche gar nicht — `Needs`, `SSE`, `Crafting`,
`BIOME`. Dasselbe Muster wie bei der Namenstabelle: das Gerüst trägt, die
Einzelangaben sind Behauptungen mit Fehlerquote.

Bemerkenswert ist die Lücke bei `SSE`. Falls das die Effektkategorie ist, ist
es die Kategorie, in der Grundsteine stehen — also genau das, worum sich das
halbe Dokument dreht, und es kennt den Schlüssel nicht.
