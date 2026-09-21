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

Zusätzlich, sobald du die ID-Listen aus der KB-Sonde hast:

```powershell
python tools\build_kb.py seed --ids diagnostics\ids-20260921-223605
```
