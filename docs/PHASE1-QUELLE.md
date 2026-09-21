# Vor Phase 1: taugt der Spielstand als Quelle für `kb.sqlite`?

Die Phase-0-Messung hat in `MetaSave.save` eine Liste `content.buildings` mit
169 Einträgen gefunden. Das ist ungefähr die Größenordnung des gesamten
Gebäudebestands von *Against the Storm* — also möglicherweise der Katalog des
Spiels und nicht nur der Freischaltstand.

Falls ja, wäre das die bessere Quelle als das Wiki: aktuell zur installierten
Version 1.10.4, in denselben IDs wie der Rest des Saves, ohne Crawlen, ohne
den Versionsvorbehalt, den die Spec für das Wiki verlangt („stellenweise auf
Spielversion 1.8 bis 1.9"). Falls nein, bleibt der Scraper.

Diese Frage entscheidet den Zuschnitt von Phase 1, deshalb wird sie vorher
geklärt und nicht nebenbei.

## Ausführen

```powershell
python tools\kb_probe.py --dump-ids
```

Liest `Save.save`, `WorldSave.save` und `MetaSave.save` ausschließlich lesend,
schreibt nur nach `diagnostics\`. Dauert Sekunden. `--dump-ids` legt die
gefundenen ID-Listen zusätzlich als Textdateien ab — falls der Save das
Vokabular hergibt, ist das direkt der Grundstock für die Wissensbasis.

## Was die Sonde beantwortet

Sie sucht katalogartige Strukturen — Listen ab zwölf Einträgen, Zuordnungen
mit vielen Schlüsseln — und meldet je Struktur den Pfad, die Länge, die Felder
je Eintrag und ein paar echte Beispieleinträge. Daraus fällt für jede Tabelle
aus SPEC.md Phase 1 ein Befund in einer von vier Stufen:

| Befund | Bedeutung für Phase 1 |
|---|---|
| **IDs und Zahlen** | Der Save ersetzt das Wiki für diese Tabelle. Kosten, Rezepte, Arbeitsplätze stehen drin. |
| **IDs und Attribute** | Vokabular und Einordnung (Seltenheit, Kategorie) kommen aus dem Save, Kosten und Rezepte aus dem Wiki. |
| **nur IDs** | Der Save liefert die verbindliche ID-Liste, alle Zahlen kommen aus dem Wiki. |
| **nicht gefunden** | Diese Tabelle kommt vollständig aus dem Wiki. |

## Was ich erwarte

Meine Vermutung, damit sie überprüfbar ist statt hinterher plausibel: **für
die meisten Tabellen „nur IDs"**. Definitionen wie Kosten und Rezepte liegen
bei Unity-Spielen üblicherweise in den Asset-Bundles, nicht im Spielstand; der
Save verweist nur auf IDs. `content.buildings` wäre dann eine Liste von
Gebäudenamen, keine Datensätze.

Das wäre trotzdem ein Gewinn, nur ein kleinerer: die verbindliche ID-Liste
fixiert die Schlüssel von `kb.sqlite` und die `en`-Spalte von `name_map`,
womit das Wiki nur noch Zahlen liefern muss und keine Namen mehr raten kann.
Aus 109 geratenen Namenspaaren würden geprüfte Schlüssel.

Die Gegenprobe sind die Gebäudeinstanzen in `Save.save`. Die tragen Rezepte
und Arbeiterzahlen — aber als Zustand dieser Siedlung, nicht als Definition.
Die Sonde meldet beides getrennt, damit der Unterschied nicht verwischt.

## Danach

Der Befund entscheidet, wie Phase 1 zugeschnitten wird:

- Überwiegend „IDs und Zahlen" → der Scraper entfällt weitgehend, Phase 1
  wird zum Import aus dem Save plus Lückenfüllung aus dem Wiki.
- Überwiegend „nur IDs" → der Scraper bleibt, bekommt aber die ID-Liste als
  Sollvorgabe. Das macht ihn prüfbar: was das Wiki nicht liefert, fällt auf.
- Überwiegend „nicht gefunden" → Phase 1 wie in der Spec beschrieben.

---

# Antwort (Lauf vom 2026-09-21)

**Meine Vermutung war richtig: nur IDs.** Nirgends im Spielstand steht eine
Gebäudedefinition mit Kosten oder Rezept. Was dort steht, sind Instanzen
dieser Siedlung — `$.buildings.roads` mit 193 Wegstücken samt Position und
Baufortschritt — und Kataloge, die nur aus Namen bestehen.

Der Scraper wird also gebraucht. Aber er bekommt eine Sollvorgabe, und das
ändert seinen Charakter: was das Wiki nicht liefert, fällt künftig auf.

## Vokabular, das der Save liefert

| Fundort | Einträge | Beispiele |
|---|---|---|
| `MetaSave.content.buildings` | **169** | Bakery, Beaver House, Brewery, Brickyard |
| `MetaSave.content.essentialBuildings` | 182 | Bank, Small Hearth, Biome Poro, AncientShrine_T1 |
| `MetaSave.content.effects` | **65** | Insect for tree, Crystaline Water, LessHostilityPerWoodcutter, RawDepositsCharges_10 |
| `MetaSave.gameplay.playedWorldEffects` | 62 | [Biome] Wood in Woodlands, [Map Mod] No Control, [BIOME] Giant Organisms |
| `Save.trends.goodsTrends` (Schlüssel) | alle Waren | [Crafting] Oil, [Food Processed] Jerky, Hearth Parts, Blight Fuel |
| `Save.trends.goodsCategoriesTrends` (Schlüssel) | 7 | Building Materials, Consumable Items, Crafting, Food, Fuel, Others, Trade Goods |
| `WorldSave.cycle.seenModifiers` | 24 | Modifier_OnePerk, Modifier_NoOrders, Modifier_NoGoodsRefund |
| `WorldSave.cycle.seenEvents` | 12 | Gambler, Loremaster, Mosquito Nest, Hanged Viceroy |

**Wichtiger Vorbehalt:** `seenModifiers` und `seenEvents` heißen so, weil sie
festhalten, was *ich* gesehen habe. Das sind Teilmengen, keine vollständigen
Listen. `content.buildings` und `content.effects` sehen dagegen nach dem
vollständigen Bestand aus — 169 Gebäude ist ungefähr die richtige
Größenordnung —, aber auch das ist eine Vermutung, solange kein zweiter
Spielstand mit anderem Fortschritt danebenliegt.

## Was das für Phase 1 heißt

| Tabelle | Vokabular aus dem Save | Zahlen |
|---|---|---|
| `buildings` | ja, 169 | Wiki |
| `resources` | ja, über die Reihenschlüssel | Wiki |
| `cornerstones` | ja, 65 Effekte | Wiki |
| `prestige` | teilweise, 24 gesehene Modifikatoren | Wiki |
| `glade_events` | teilweise, 12 gesehene Ereignisse | Wiki |
| `recipes` | nein | Wiki |
| `species` | nein | Wiki |
| `biomes` | nein | Wiki |

Der Gewinn ist trotzdem konkret: die `en`-Spalte von `name_map` steht jetzt
für 16 Waren nicht mehr auf Verdacht, sondern auf der ID aus dem Spielstand.
Und die Kategorie `Food Complex`, die die Recherche erfunden hatte, heißt im
Spiel `Food Processed` — in der Tabelle korrigiert.

---

# Der wichtigere Fund: `trends.goodsTrends`

Der Spielstand führt **je Ware eine Zeitreihe mit 180 Werten**, dazu dieselbe
Reihe je Warenkategorie. `$.trends.goodsCategoriesTrends.Food` ist damit
wörtlich die Vorgeschichte des Nahrungsbestands.

Das rührt an der Einordnung aus Phase 0. Szenario B beruhte darauf, dass der
Parser nur alle 300 Spielzeitsekunden einen Zustand sieht und deshalb keine
Verbrauchsrate bilden kann. Aber `food_forecast` braucht keine Momentaufnahme,
es braucht eine **Steigung** — und die steht mit 180 Stützstellen in jeder
geschriebenen Datei. Ein Spielstand liefert also nicht einen Punkt, sondern
eine Kurve.

Was damit noch offen ist: der Abstand zwischen zwei Stützstellen. 180 Werte
können zehn Minuten oder das ganze Spiel abdecken, und davon hängt ab, wie fein
die Vorhersage wird.

**Das misst der nächste `watch`-Lauf von selbst.** Die Sonde hält bei jedem
Schreibvorgang Länge und Ende der Reihen fest; wie weit die Reihe zwischen zwei
Schreibvorgängen weiterrückt, ergibt den Abstand — bei bekannten 300
Spielzeitsekunden dazwischen.

Fällt der Abstand fein genug aus, schrumpft Phase 3 womöglich wieder auf die
Auswahlbildschirme zusammen, und die Nahrungswarnung kommt doch aus dem Parser.
Vor dieser Messung wird an Phase 3 nichts entschieden.

# Zwei Funde nebenbei

**`MetaSave.gamesHistory.records`** führt zwanzig abgeschlossene Läufe mit
`hasWon`, `difficulty`, `biome`, `years`, `gameTime`, `tradeValueInAmbers`,
`hearthCorruptedAmount` und je Lauf den verwendeten Gebäuden. Das ist genau
die Gegenüberstellung, die `analyze_runs` leisten soll — gewonnene gegen
verlorene Läufe —, und sie existiert schon, bevor die erste eigene Zeile in
`runs/*.jsonl` steht.

**`Save.world.naturalResources`** hat 6.067 Einträge mit Position und
`isActive`, `Save.world.glades[n].fields` beschreibt die Lichtungen. Die beiden
GameState-Felder „entdeckte Lichtungen" und „Vorkommen mit Restladungen" liegen
damit dort, wo man sie erwartet.

Und eine Kleinigkeit, die Vertrauen schafft:
`MetaSave.gameConditions.embarkGoods` enthält `{"name": "[Crafting] Oil",
"amount": 42}` — dieselben 42 Öl, die im Auftragsfenster als „42/25 Öl" und im
Lagerraster als 42 stehen. Screenshot und Spielstand sagen dasselbe.
