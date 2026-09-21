# Phase 1 — Wissensbasis

## Stand

| Teil | Status |
|---|---|
| Schema `kb.sqlite` | fertig, neun Tabellen plus zwei, die aus Phase 0 dazukamen |
| `name_map` befüllt | 136 Zeilen, nach Belastbarkeit gestaffelt |
| Vokabular aus dem Spielstand | Import fertig, wartet auf deine `--dump-ids`-Dateien |
| Wiki-Auswertung | **wartet auf die Bestandsaufnahme** |

## Warum das Wiki nicht von hier kommt

Der Egress-Proxy dieser Sitzung beantwortet `CONNECT wiki.hoodedhorse.com:443`
mit 403 — eine Richtlinienentscheidung, kein technischer Fehler. Ich melde
das, statt es zu umgehen. Du hast den Abzug inzwischen lokal (589 Seiten,
HTML und Wikitext), damit ist die Frage praktisch gelöst: der Aufbau liest
einen **lokalen Abzug** statt zu crawlen. Das ist ohnehin die bessere Lösung —
keine Höflichkeitspausen, keine Cloudflare-Hürde, und der Stand ist
reproduzierbar.

## Zwei Tabellen, die nicht in der Spec stehen

**`source_pages`** hält je Seite Revisionsnummer, Abrufzeitpunkt und die im
Text genannte Spielversion. Weicht sie von 1.10.4 ab, hängt eine Warnung am
Datensatz — die Spec verlangt das ausdrücklich, weil das Wiki stellenweise auf
1.8 bis 1.9 steht.

**`save_ids`** nimmt das Vokabular auf, das der Spielstand selbst liefert: 169
Gebäude, 65 Effekte, die Warenliste, 24 Modifikatoren, 12 Lichtungsereignisse.
Daraus wird die Sollvorgabe für die Wiki-Auswertung. `unmatched_save_ids()`
beantwortet die Frage, die sonst niemand stellt: **was kennt das Spiel, das
die Wissensbasis nicht kennt?**

## Die Namenstabelle staffelt nach Belastbarkeit

`screenshot+save` > `screenshot` > `save_id` > `spec_seed` > `observed` >
`guessed`. Eine belegte Zeile wird nie von einer geratenen überschrieben, egal
in welcher Reihenfolge die Quellen eingelesen werden — dafür gibt es einen
Test. Aktuell: 1 doppelt belegt, 10 aus Screenshots, 16 mit ID aus dem
Spielstand, 15 aus der Spec, 6 beobachtet, 88 geraten.

## Nächster Schritt: erst sehen, dann parsen

Ich schreibe keine Wikitext-Parser gegen Text, den ich nie gesehen habe — das
ist genau der Fehler, den ich der beigelegten Recherche vorgeworfen habe.
Stattdessen:

```powershell
python tools\build_kb.py survey --wiki-dir "C:\Users\Joni\.cursor\wiki\against-the-storm-wiki"
```

Das liest deinen Abzug und berichtet, was drinsteht: wie viele Seiten, welche
Vorlagen (daran hängen die Infoboxen), welche Tabellenköpfe (daran hängen die
Sachtabellen), welche Spielversionen im Text genannt werden, und welche Seiten
für welche Tabelle aus der Spec in Frage kommen — nach Titel **und** nach
verwendeter Vorlage, weil die Seite „Bakery" nicht nach Gebäude heißt, aber
`Building infobox` benutzt.

Schick mir den `.txt`, dann schreibe ich die Extraktoren gegen Belege.

### Was die Bestandsaufnahme ergeben hat (587 Seiten, 3,5 MB Wikitext)

Drei Befunde, die den Zuschnitt bestimmen:

1. **Das Wiki hält strukturierte Datenseiten.** `Dataloader/guid_index`
   erscheint 6469-mal, dazu `Dataloader/Goods` und `Dataloader/Deeds`, und es
   gibt Seiten wie `Data_Goods_1`. Das ist deutlich besser als
   Fließtexttabellen — falls diese Seiten maschinenlesbar sind, kommt die
   Wissensbasis daher und nicht aus Prosa.
2. **Die tragenden Vorlagen sind identifiziert:** `Recipe` (435 Aufrufe),
   `Perk` (320, mit Farbvarianten für die Seltenheit), `Buildingbox` (96),
   `Construction` (96), `Goodbox` (70), `Deposit` (43), `Version` (237) sowie
   die Kurzverweise `rl`, `bl`, `sl`, `pl`. Und die Seiten *List of annual
   Cornerstones*, *… available for purchase from traders*, *… available from
   Orders* liefern genau das Feld `origin`, das die Spec für Grundsteine will.
3. **1.10 kommt in den Versionsangaben überhaupt nicht vor.** Häufigste sind
   1.8.10 (57×), 1.9 (20×), 1.9.8 (17×), dazu viel 1.3 bis 1.5. Der
   Versionsvorbehalt der Spec ist damit nicht die Ausnahme, sondern der
   Normalfall — `source_pages.warning` wird an fast jedem Datensatz hängen.

### Nächster Schritt: Vorlagen aufschlüsseln

```powershell
python tools\build_kb.py detail --wiki-dir "C:\Users\Joni\.cursor\wiki\against-the-storm-wiki"
```

Das zeigt je Vorlage die verwendeten Parameter mit Häufigkeit und drei echte
Beispielaufrufe — verschachtelte Vorlagen werden dabei korrekt behandelt,
`cost={{Construction|Planks|10}}` wird also nicht mitten im Parameter
zerschnitten. Dazu die Liste der Datenseiten.

Einzelne Seiten im Rohzustand, falls etwas offenbleibt:

```powershell
python tools\build_kb.py page --wiki-dir "..." --title "Data_Goods_1" "List of annual Cornerstones"
```

Zusätzlich, sobald du die ID-Listen aus der KB-Sonde hast:

```powershell
python tools\build_kb.py seed --ids diagnostics\ids-20260921-223605
```
