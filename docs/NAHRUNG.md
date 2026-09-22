# Vom Befund zur Empfehlung (2026-09-22)

`food_forecast` sagt: „Die Nahrung reicht noch 340 Spielzeitsekunden." Das ist
richtig und nützt wenig. SPEC.md nennt als Problem **Nahrungsmangel im ersten
Jahr** — und die Diagnose davon ist nicht die Antwort darauf.

`food_advice` rechnet die Antwort aus. Keine Faustregel, keine Schätzung: jedes
Rezept der Wissensbasis gegen den tatsächlichen Lagerbestand, mit dem
tatsächlichen Verbrauch aus der Zeitreihe.

## Die Rechnung

Für jedes Rezept, dessen Produkt essbar ist:

1. **Zutaten prüfen.** Das Spiel lässt bei jeder Zutat die Wahl zwischen
   Alternativen („5 Insekten *oder* 5 Fleisch"). Genommen wird, was im Lager
   liegt — und darunter das, was roh am wenigsten sättigt. Fehlt für eine
   Zutat jede Alternative, fällt das Rezept weg.
2. **Durchläufe zählen.** Wie oft trägt der Bestand das Rezept? Es entscheidet
   die knappste Zutat, und die wird als **Engpass** benannt.
3. **Sättigung gegenrechnen.** Was der Einsatz roh verzehrt gäbe, gegen das,
   was er verarbeitet gibt. Die Differenz ist der **Gewinn**.
4. **In Zeit umrechnen.** Gewinn geteilt durch den gemessenen Verbrauch je
   Spielzeitsekunde ergibt die gewonnene Reichweite.

Sortiert wird nach Gewinn, bei Gleichstand nach Dauer. Nicht nach Faktor: ein
Faktor 6 auf zehn Beeren ist weniger wert als ein Faktor 4 auf vierzig Fleisch,
und satt wird die Siedlung von Sättigung, nicht von Verhältnissen.

## Was dabei herauskommt

    Räucherei: 40 Meat werden zu Dörrfleisch, 120 Sättigung mehr
    (Faktor 4), rund 20 Minuten Reichweite

    Roh verzehrt sättigt der Einsatz 40, verarbeitet 160 — Faktor 4;
    Meat geht zuerst aus. Das verschiebt das Ende von 6 auf 26 Minuten.

    Weinkeller bringt 50 statt 120 Sättigung, ist aber 8 Minuten früher
    fertig — besser, wenn der Bestand vor der Fertigstellung leer wäre.

Drei Sätze: Empfehlung, Begründung, Alternative. Genau die Form, die SPEC.md
für die Ausgabe verlangt — nur dass hier nichts davon geschätzt ist.

## Warum es dieses Werkzeug in der Spec nicht gibt

Die Werkzeugliste in Phase 4 nennt `food_forecast`, nicht `food_advice`. Das
ist eine Ergänzung, und sie ist als solche gekennzeichnet — im Docstring, in
der Werkzeugbeschreibung und hier.

Sie hält sich an das Leitprinzip: gerechnet wird lokal und deterministisch,
geurteilt im Modell. `food_advice` entscheidet nichts. Es legt die Zahlen hin,
an denen sich entscheiden lässt — welche Kette wie viel Zeit kauft, woran sie
hängt, was sie kostet. Ob die Räucherei jetzt gebaut wird oder erst nach dem
Lagerhaus, bleibt eine Frage der Lage.

## Grenzen

- **Nur der Bestand zählt.** Was noch auf der Karte steht — Beerenbüsche,
  Wildtiere, ein ungenutzter fruchtbarer Boden —, geht nicht ein. Ein Rezept
  ohne Zutaten im Lager fällt weg, auch wenn die Zutaten in Reichweite wachsen.
- **Ein Arbeiter.** Die Dauer rechnet mit einem Produktionsplatz. Zwei
  Arbeiter halbieren sie, drei dritteln sie; Boni tun es nicht linear.
- **Der Verbrauch ist der von gerade eben.** Er steigt mit der Bevölkerung und
  springt bei Feindseligkeitsstufen. Für die nächste halbe Stunde taugt er,
  für das nächste Jahr nicht.
- **Ohne Rezepte in `kb.sqlite` sagt es nichts.** Das Werkzeug ist so gut wie
  die Wissensbasis darunter — `build_kb.py html --write` füllt sie.
