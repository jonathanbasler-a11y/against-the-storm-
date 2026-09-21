# Beobachteter Zustand, 2026-09-21

Quelle: zwei Screenshots derselben laufenden Siedlung, unmittelbar vor einem
angekündigten Speichervorgang. Alles hier ist vom Bild abgelesen, nicht
gemessen — die Ziffern im Lagerraster sind klein, also vor Gebrauch gegen den
Diagnosebericht halten und Abweichungen hier korrigieren.

**Nachtrag:** Dieser Lauf wurde später **gewonnen** — auf Prestige 13, im
Korallenwald. Die Zahlen unten sind also ein Zwischenstand einer erfolgreich
beendeten Partie, kein beliebiger Moment. Sobald die nächste Siedlung
gegründet wird, überschreibt das Spiel `Save.save`; wer diesen Zustand später
noch parsen können will, braucht eine Kopie (`tools/snapshot_saves.py`).

Zweck: **Abnahmekriterium für Phase 2.** Die Spec verlangt, dass der Parser
einen Spielstand lädt und Zahlen liefert, die mit dem übereinstimmen, was im
Spiel steht. Das hier ist die Vergleichsseite.

## Bevölkerung und Entschlossenheit

| Spezies | Bevölkerung | Entschlossenheit |
|---|---|---|
| Menschen | 2 | 14 → 15 |
| Biber | 6 | 5 → 8 |
| Echsen | 2 | 9 → 15 |

Gesamtanzeige oben links: 10 Siedler. Summe der drei Zeilen ist ebenfalls 10 —
die erste interne Konsistenzprüfung, die der Parser bestehen muss.

Der zweite Wert je Spezies (der Pfeil) ist die Zielentschlossenheit, auf die
sich der aktuelle Wert zubewegt. Beides gehört getrennt ins `GameState`, sonst
sieht die Beratung eine Zahl, die das Spiel gerade erst anstrebt.

## Aufträge (aus dem ersten Screenshot)

| Kategorie | Auftrag | Stand |
|---|---|---|
| Lager | Erntelager | 0/1 |
| Lager | Steinmetzlager | 0/1 |
| Lager | Ziegel | 2/10 |
| Lieferung | Handelswege | 4/3 |
| Lieferung | Feldfruchtpaket | 2/5 |
| Erntesegen | Feldfruchtpaket | 2/7 |
| Hilfe für die Menschen-Fraktion | Feldfruchtpaket | ?/10 |
| Hilfe für die Menschen-Fraktion | Komfort | 4/12 |
| Festmahl | Beliebiges „Komplexe Nahrung"-Bedürfnis erfüllt | 0/14 |
| Festmahl | Öl | 42/25 |
| Menschliche Dorfbewohner | Menschen | ?/12 |
| Menschliche Dorfbewohner | Bedürfnis nach Mäntel erfüllt | 4/10 |
| Geschenke für die Königin | „Loyalität"-Entscheidungen | 0/3 |

**„4/3 Handelswege" und „42/25 Öl" sind der wichtigste Fund hier:** Aufträge
zählen über ihr Soll hinaus. Ein Parser, der `soll - ist` rechnet, produziert
negative Restmengen, und eine Beratung, die daraus „noch 1 Handelsweg nötig"
macht, schickt mich in die falsche Richtung. Restmenge gehört bei null
abgeschnitten, der Rohwert bleibt erhalten.

## Lagerbestand (Hauptlager, zweiter Screenshot)

Das Raster zeigt **Symbole und Zahlen, keine Namen** — Namen erscheinen nur
beim Überfahren mit der Maus. Abgelesene Werte, zeilenweise:

```
Zeile 1:  42    0    0    5    5   10    2
Zeile 2:  10    3  152   28   15    0    0
Zeile 3:  32   35   14   23    0    0    2
Zeile 4:  10   50    5    2   12
```

Die 152 taucht auch in der oberen Leiste des ersten Screenshots auf, die beiden
Bilder sind also derselbe Zustand.

## Wofür das gut ist

1. **Abnahmetest Phase 2.** Die Multimenge der Lagerwerte und die sechs Zahlen
   aus der Speziestabelle müssen im geparsten `GameState` wieder auftauchen.
   Das ist ein Test, der ohne jede Namenszuordnung funktioniert.
2. **Automatische Beschriftung der Symbole für Phase 3.** Save und Screenshot
   stammen aus demselben Moment. Werte wie 152, 50, 42, 35 und 32 kommen je
   nur einmal vor, sind also eindeutig. Damit lässt sich jedes Rastersymbol
   ohne Handarbeit dem Waren-Identifikator aus dem Spielstand zuordnen — der
   Grundstock für `templates/` fällt als Nebenprodukt ab, statt einzeln
   ausgeschnitten werden zu müssen.
3. **Negativbefund zur Namensernte.** Das Lager ist die falsche Quelle für
   deutsche Namen: dort steht keiner. Ergiebig sind die Auftragsleiste (siehe
   oben, dreizehn Begriffe aus einem Bild) und das Baumenü.
