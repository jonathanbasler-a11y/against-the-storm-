# Die deutschen Namen (2026-09-22)

SPEC.md verlangt deutsche Namen in der Ausgabe und englische IDs im Inneren,
und sieht für die deutsche Seite die Stufe `guessed` vor — weil sie nirgends
öffentlich steht. Das Wiki ist englisch, die Oberfläche deutsch, dazwischen
lag Raten.

Das war eine Lücke, kein Naturgesetz. Das Spiel trägt seine Texte selbst mit:
`Against the Storm_Data/resources.assets` enthält je Sprache eine Tabelle aus
Schlüssel und Zeichenkette. `Good_PickledGoods_Name` steht dort englisch wie
deutsch. Damit wird aus dem Raten ein Nachschlag.

## Was daraus geworden ist

| | |
|---|---|
| Namen übernommen | 1641 |
| geratene Zeilen gegengeprüft | 124 |
| davon **falsch** | **36 (29 Prozent)** |
| bestätigt | 88 |
| beobachtete Zeilen um die englische Seite ergänzt | 4 |
| beobachtete Zeilen mit anderem Wortlaut (stehen geblieben) | 2 |

Die Stufe heißt `localization` und steht über allem anderen, auch über
`screenshot`: ein Screenshot ist eine Aufnahme dieser Zeichenkette und kann
sich verlesen, die Tabelle nicht.

## Die Fehler, die etwas gekostet hätten

| geraten | tatsächlich |
|---|---|
| Eingelegte Waren | Eingelegte Nahrung |
| Brei | Haferbrei |
| Spieße | Fleischspieße |
| Bohnenküche | Imbiss |
| Taverne | Schänke |
| Keller | Weinkeller |
| Zimmerei | Tischler |
| Moorlande | Sümpfe |
| Kristalltau | Kristallisierter Tau |
| Auslichtung | **Sommer** |

Zwei stechen heraus.

**Sammlerlager** ist im Spiel das *Scavengers' Camp*. Die Recherche hatte es
dem *Foragers' Camp* zugeordnet — das heißt **Nahrungssammlerlager**. Ein Rat
„bau ein Sammlerlager" hätte auf das falsche Gebäude gezeigt, und zwar genau
in der Lage, um die es hier geht: Nahrungsmangel im ersten Jahr.

**Clearance** heißt auf Deutsch **Sommer**, nicht „Auslichtung". Wer nach der
Jahreszeit fragt, bekommt sonst eine Antwort, die im Spiel nicht vorkommt.

## Wie der Abgleich arbeitet

`src/ats_assistant/localization.py`, aufgerufen über

    python tools/build_kb.py namen --dir <verzeichnis>          # nur zeigen
    python tools/build_kb.py namen --dir <verzeichnis> --write  # übernehmen

Ohne `--dir` liest derselbe Befehl `data/name_map_localized.csv`, die
abgelegte Fassung — dafür braucht es die Spieldateien nicht.

Vier Durchgänge:

1. **Namen.** Alles, was auf `_Name` oder `_DisplayName` endet und dessen
   Präfix bekannt ist: `Good_`, `Building_`, `Effect_`, `Relic_`, `Biome_`,
   `Race_`, `Order_`, `Profession_` und ein paar mehr. Dialogzeilen und
   Menütexte bleiben draußen.
2. **Begriffe.** Ungeduld, Entschlossenheit, Pestfäule, Lichtungsereignis —
   die führt das Spiel nicht als Namen, sondern nur in der Oberfläche
   (`Label_`, `GameUI_`). Gesucht wird über die englische Seite, exakt.
   Etwas aus einem Satz herauszufischen wäre wieder Raten.
3. **Lücken rückwärts schließen.** Sechs Zeilen standen mit deutschem Namen
   und offener englischer Seite in der Tabelle, aus Screenshots. Vier ließen
   sich auflösen: Komfort = Comfort, Erntelager = Harvesters' Camp,
   Loyalität = Loyalty, Stadtgebäude = City Buildings. Aufgelöst wird nur,
   wo genau ein englischer Begriff passt.
4. **Abgleich.** Gleicher Name, gleiches Wort: die geratene Zeile war richtig
   und wird durch die belegte ersetzt, Kategorie und Save-ID wandern mit.
   Anderes Wort: die geratene Zeile geht nach `retired_names` — gelöscht,
   aber nachlesbar. Beobachtetes wird nicht angetastet, sondern gemeldet;
   die zwei Abweichungen dort sind Ein- gegen Mehrzahl.

Der Bezeichner aus der Recherche trifft den Namen des Spiels nicht immer:
`reeds` heißt dort „Reed", `simple_tools` schlicht „Tools", `storm_season`
nur „Storm". Dafür gibt es `ALIASE`. Ohne diese Brücke stünde die falsche
Zeile unwidersprochen neben der richtigen — und genau so eine bleibt in der
Auskunft stehen.

## Was offen bleibt

Vier Begriffe hat das Spiel nicht als Vokabel, nur im Satz. Sie stehen
deshalb auf `observed` statt `localization`, mit dem Fundort in der Notiz:

- **Feindseligkeit** (aus `Building_HearthBuildable_Description`)
- **Entwurf** (als Vokabel nur im Plural: `Label_MetaReward_Blueprint`
  = „Gebäude-Entwürfe"; die Einzahl aus `News_RandomBlueprint_Name`)
- **Fluffschnabel** (einzeln führt das Spiel nur „Giant Fluffbeak")
- „Lagergebäude" und „Lagerhaus" aus zwei Screenshots, zu denen mehr als
  ein englischer Begriff passt

## Herkunft

Die drei Auszüge (`de_translations.json`, `de_en_mapping.json`,
`de_en_names.json`) stammen aus der eigenen Spielinstallation und gehören
nicht ins Repo. Was hier liegt, ist das Abgeleitete: `data/name_map_localized.csv`,
1641 Zeilen, Name gegen Name. Nach einem Spiel-Update erzeugt derselbe
Befehl sie neu.
