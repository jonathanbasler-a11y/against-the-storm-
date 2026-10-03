---
name: ats-laufauswertung
description: Einen Lauf von Against the Storm auswerten und das Gelernte dauerhaft machen -- warum er so lange dauerte, wo er gekippt ist, was ihn gedreht hat, und was davon in die Regeln des Rats oder in einen Test gehört. Nutzen, sobald ein Lauf gewonnen oder verloren ist ("won 17", "did p19", "hab verloren wegen Nahrung"), wenn gefragt wird, warum ein Lauf lange gedauert hat, wenn eine Ausgabe von tools/verlauf.py oder aus dem Reiter „Läufe“ eingefügt wird, oder wenn alle Läufe zusammengefasst werden sollen. Nicht nutzen für eine Wahl im laufenden Spiel -- dafür gilt ats-advisor.
---

# Einen Lauf auswerten

Bis Oktober 2026 kam die Frage nach einem Lauf mindestens fünfmal —
„wieder lange gebraucht“, „did p19!“, „fasse alle Läufe zusammen“ —, und
jedes Mal wurde das Vorgehen neu erfunden. Zweimal lag die Auswertung
daneben, weil sie einen einzelnen Spielstand für den ganzen Lauf nahm. Dieser
Skill legt fest, was angesehen wird, wogegen verglichen wird und wohin das
Ergebnis gehört.

Die Läufe liegen auf dem Spielrechner, nicht hier. Was nicht eingefügt ist,
wird erfragt, nicht geraten.

## 1. Die Daten holen

Am Spielrechner, im Projektordner:

```
python tools\verlauf.py --liste                  # alle Mitschriften mit Namen
python tools\verlauf.py --lauf <Name>            # je Speicherstand eine Zeile + Rat-Notizen
```

Der Name steht hinter `--lauf`, nicht als eigene Option (`--Poro_Biome-…`
schlug am 27.09.2026 fehl). Dazu, wenn vorhanden:

- **Reiter „Läufe“ → „Auswerten“**: Lehren, Spielhistorie (alle Läufe aus dem
  Spielstand, auch die nicht mitgeschriebenen), je Mitschrift eine Zeile.
- **Der letzte Lagestand** („Lage kopieren“): Ruf-Quellen je Volk, Aufträge,
  Effekte, Gebäude mit Arbeitern.
- **Der Siegbildschirm**: abgeschlossene Aufträge und gelöste Ereignisse —
  im Spielstand stehen Auftrags-Ruf und Lichtungs-Ruf nur als „(vermutet)“.

## 2. Worauf geschaut wird — in dieser Reihenfolge

| Was | Woher | Wonach |
|---|---|---|
| Ausgang, Jahre, Prestige | Kopfzeile von `verlauf.py` | gegen den Median 11 Jahre |
| Ruf je Jahr | Spalte „Ruf“ | Stillstand (ein Jahr unter einem Punkt) und das Tempo danach |
| Nahrung je Stand | „Nahrung“, „reicht“ | Phasen um 0, gleichzeitig Hunger/gegangen/tot |
| Ungeduld | „Ungeduld“ | Spitze, Ende, Rest bis 14 |
| Ruf-Quellen am Ende | `ruf_quellen`, `ruf_je_volk` | welches Volk nichts beitrug |
| Aufträge | Siegbildschirm, `auftraege` | wann die ersten fertig wurden |
| Leere Gebäude | `gebaeude_liste` (`arbeiter: 0`) | Werk- und Dienstgebäude, nicht Häuser/Äcker |
| Ausgegangene Waren | `trends.fallend`, Bestand 0 | Stein, Mäntel, Holz — was den Bau stoppte |
| Rat-Notizen | Ende von `verlauf.py` | welche Wahl wann; was die Krise früher gelöst hätte |

Ein Lauf hat **Phasen**. Die Antwort beschreibt sie mit Zahlen („Jahr 2–8:
Nahrung meist 0–25, Ruf 1,0/Jahr; ab Jahr 8: Nahrung wächst, Ruf 2,4/Jahr“),
nicht einen Durchschnitt über alles.

## 3. Wogegen verglichen wird

| Lauf | Ruf in Jahr 7 | Ende | Was drehte |
|---|---|---|---|
| P17 Bambusebene | 9,9 | Sieg Jahr 11, Ungeduld 13,2 (Spitze 14,0) | Nahrung ab Jahr 8 (Kleinfarm, Kochhaus), danach 2,4 Ruf/Jahr |
| P17 Scharlachroter Obstgarten | — | Niederlage Jahr 7, Ungeduld | — Nahrung leer in Jahr 5, 15 gegangen |
| P18 Scharlachroter Obstgarten | 5,4 | Sieg Jahr 12, Ungeduld 10,4 | 7 Aufträge, Pastete/Kekse/Mäntel, ~2,5 Ruf/Jahr |
| P19 Königswälder | 5,9 | Sieg Jahr 11, Ungeduld 9,6 | Zufriedenheit 9,1 aus allen drei Völkern, 7 Aufträge |

Neue Läufe kommen in diese Tabelle (dieselbe Datei, eine Zeile).

**Jede Zahl über mehrere Läufe nennt ihre Stichprobe.** Unter drei Läufen je
Seite ist sie ein Hinweis, kein Befund — „Hunger im Median 156 bei
Niederlagen“ kam am 28.09.2026 aus einem einzigen Lauf.

## 4. Die Antwort an den Spieler

1. Das Ergebnis in einem Satz, mit Jahr und Rest-Ungeduld.
2. Die zwei, drei Phasen mit Zahlen — gern als Tabelle.
3. Was den Lauf gedreht hat.
4. **Eine** Lehre für die nächste Stufe, höchstens drei.
5. Eigene Fehleinschätzungen offen nennen. P19, Jahr 7: „kaum noch zu
   gewinnen“ — gewonnen in Jahr 11. Ein Urteil gilt für das Tempo von jetzt,
   nicht als Prognose.

Deutsch, die Spielnamen aus der Wissensbasis (Bambusebene, nicht Poro Biome).

## 5. Dauerhaft machen — der eigentliche Zweck

Eine Auswertung, die nur im Gespräch steht, ist beim nächsten Lauf vergessen.

| Gelernt | Wohin |
|---|---|
| Gemessene Mechanik (Zahl mit Herkunft) | `ats-advisor`, Tabelle „Mechanik — nur Belegtes“, mit Datum |
| Widerspricht sie einer Zeile dort | die alte Zeile **ersetzen**, nicht daneben stellen (Ungeduld „genau 1,0“ stand bis 03.10.2026 neben „netto 0,5“) |
| Korrektur des Spielers | Feld „Korrektur“ im Fenster (`lernen.korrekturen`); ist sie allgemein, zusätzlich in die Mechanik-Tabelle mit „Spieler, Datum“ |
| HUD oder Rat lagen falsch | erst ein Test mit den echten Zahlen, der es zeigt, dann der Fix (`erst-messen`) |
| Eine Heuristik | nur, wenn mindestens zwei Läufe sie tragen; sonst als Hinweis mit dem Lauf benennen |
| Ein neuer Vergleichslauf | Tabelle in Abschnitt 3 |

**Nicht in `ats-advisor`:** lange Laufgeschichten. Der Text geht als
Systemtext mit jeder Rat-Frage der App mit; dort steht die Regel und ein
Halbsatz Anlass, die Geschichte steht hier.

Beispiele, wie es lief: der Sturmwert der Ungeduld (P19) wurde ein Test in
`tests/test_engpass.py` und ein Fix in `tools_api._ausserhalb_sturm`; die
zerstückelten Mitschriften (24 Dateien, zwei falsche Niederlagen) wurden
`lernen.zusammenfuehren`; „Rohre gehen in Regenmaschinen“ wurde eine Zeile
der Mechanik-Tabelle.

## Was der Spielstand nicht sagt

- woran Siedler gestorben sind,
- was ein Auftrag verlangt (nur der `stand` je Ziel),
- Auftrags- und Lichtungs-Ruf genau (nur „vermutet“; der Siegbildschirm zählt),
- bei älteren Läufen aus der Spielhistorie: nur Biom, Jahre, Ausgang,
  Grundsteine und Gebäude — keinen Verlauf.

Das wird in der Auswertung gesagt, nicht ergänzt.
