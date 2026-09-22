---
name: spielassistent-bauen
description: Einen lokalen Assistenten für ein Computerspiel aufbauen -- Spielstand lesen, Wissensbasis aus Spieldaten und Wiki, Vorhersagen, Bildschirm lesen, Anbindung an ein Modell. Nutzen, wenn jemand für ein Spiel ein Hilfsprogramm, einen Berater, einen Overlay, ein Dashboard oder eine Auswertung bauen will -- auch wenn nur gesagt wird "ich verliere immer an X, kann man da was bauen" oder "kann man den Spielstand auslesen". Enthält die Reihenfolge, die sich bewährt hat, und die Fallen, die Zeit kosten. Nicht nutzen für das Spielen selbst oder für Spielregelfragen ohne Bauvorhaben.
---

# Einen Spielassistenten bauen

Aufgebaut aus einem Assistenten für *Against the Storm*, der vom leeren
Verzeichnis bis zum laufenden Fenster gebaut wurde. Die Reihenfolge unten ist
nicht die naheliegende — sie ist die, die am wenigsten Arbeit wegwirft.

## Das Leitprinzip

**Das Sehen passiert lokal und deterministisch, das Urteilen im Modell.**

Alles, was sich ausrechnen lässt, wird ausgerechnet: Bestände, Raten,
Reichweiten, Namen. Was daraus folgt — welcher von drei Bauplänen jetzt der
richtige ist — entscheidet ein Modell, und zwar auf Zahlen und Namen, nie auf
einem Bild.

Das ist keine Sparsamkeit, sondern Verlässlichkeit: eine Reichweite von
340 Sekunden ist eine Reichweite von 340 Sekunden, jedes Mal.

## Phase 0: messen, bevor irgendetwas gebaut wird

Drei Fragen entscheiden die Architektur. Alle drei sind in einer Stunde
beantwortet, und jede falsche Annahme kostet Tage.

**In welchem Format liegt der Spielstand?** Erste Bytes ansehen, nicht raten.
JSON, gzip, ein Container, ein eigenes Binärformat? Ist es Klartext, ist alles
Weitere einfach.

**Wann wird geschrieben?** Über Minuten die Änderungszeiten mitschreiben und
die Abstände auswerten. Drei Dinge fallen dabei auf, die später alles
bestimmen: der **Takt** (hier: alle 300 Spielzeitsekunden), ob mehrere Dateien
ein **Bündel** bilden, und ob sie **atomar** geschrieben werden. Beim
gemessenen Spiel lagen 2,02 Sekunden zwischen erster und letzter Datei — wer
beim ersten Signal liest, liest ein halbes Bündel.

**Welche Sprache steht drin?** Englische Bezeichner oder lokalisierte Texte?
Das entscheidet, ob eine Übersetzungstabelle nötig ist.

> Diese Messung ergab nebenbei den wichtigsten Fund des ganzen Projekts: der
> Spielstand führte **Zeitreihen** — 180 Stützstellen je Ware im
> Zehnsekundentakt, eine halbe Stunde Vorgeschichte. Damit ließ sich die
> Verbrauchsrate aus dem Spielstand selbst ableiten, statt sie aus zwei
> Momentaufnahmen zu schätzen. Geplant war das nicht.

## Die Namen kommen aus dem Spiel, nicht aus dem Wiki

Spiele liefern ihre Texte in allen Sprachen mit — bei Unity in
`resources.assets`, sonst in ähnlichen Bündeln. Je Schlüssel eine Zeichenkette
je Sprache. **Das ist die Wahrheit**, und sie ist vollständig.

Wer stattdessen übersetzt oder recherchiert, liegt verlässlich daneben: von
124 sorgfältig recherchierten Namen waren **36 falsch**, und zwei zeigten auf
ein anderes Gebäude als gemeint.

Dabei gilt:

- **Jede Zeile trägt ihre Belastbarkeit.** `localization` über `screenshot`
  über `geraten`. Eine geratene Zeile darf eine belegte nie überschreiben.
- **Widerlegte Zeilen nicht löschen, sondern beiseitelegen.** Was falsch war,
  sagt etwas darüber, wie weit der Quelle zu trauen ist.
- **Den ganzen Schlüsselraum ansehen.** Der erste Blick greift zu kurz: die
  Kategorie, um die es ging, lag unter einem Präfix, das nicht nach ihr aussah
  — 429 Einträge, fast übersehen.

## Ein Wiki ist eine Quelle unter mehreren

Community-Wikis sind unschätzbar und veraltet. Beim gemessenen Spiel trugen
**95 Prozent der Seiten mit Versionsangabe eine ältere Version** als die
gespielte.

Deshalb:

- **Spieldaten schlagen Fließtext.** Viele Wikis haben Datenseiten, auf denen
  die Zahlen des Spiels selbst stehen — die sind belastbar, der Prosatext
  daneben nicht.
- **Die Versionsangabe je Seite mitschreiben.** Dann kann eine Auskunft
  sagen, worauf sie beruht.
- **Listenseiten liefern im Quelltext oft nichts.** `{{Perks|search=...}}` ist
  eine Abfrage; das Ergebnis steht nur im gerenderten HTML.
- **Zwei Quellen für dasselbe gegeneinander halten.** Wo sie sich
  widersprechen, gewinnt die ausdrückliche vor der abgeleiteten — und der
  Widerspruch bleibt sichtbar.

## Die Werkzeuge sind Funktionen, der Server ist eine Hülle

Jedes Werkzeug als gewöhnliche Funktion, die ein Dictionary zurückgibt. Die
Anbindung — MCP, Kommandozeile, Fenster — ist nur Verdrahtung darum herum.

Das zahlt sich dreifach: die Werkzeuge sind ohne Server testbar, eine zweite
Oberfläche kostet fast nichts, und ein Wechsel der Anbindungsbibliothek
berührt die Logik nicht.

Zwei Regeln, die sich als nötig erwiesen haben:

- **Keine Ausnahme verlässt ein Werkzeug.** Sie wird ein Dictionary mit
  `fehler`. Wer wirft, reißt den Aufrufer mit — bei einer Oberfläche einen
  toten Arbeits-Thread und ein Fenster, das stehenbleibt, ohne zu sagen warum.
- **Fragen schreibt nicht.** Ein Werkzeug, das beim Abfragen mitprotokolliert,
  verfälscht jede Prüfung, die es aufruft.

## Was zurückgeht, sind Namen und Zahlen

Nie Rohdaten. Die Zeitreihen des Spielstands sind zehntausende Zahlen; in
einem Modellkontext haben sie nichts verloren. Was daraus folgt, rechnet der
Code aus, und nur das Ergebnis geht weiter.

Dasselbe für Bilder: geht ein Bildschirmfoto an ein Modell, ist das Sehen
nicht mehr deterministisch. Wenn ein Bildschirm gelesen werden muss, dann
lokal — und hinausgehen die erkannten **Namen**.

## Wenn der Bildschirm doch nötig ist

Erst prüfen, ob er es ist. Steht die gesuchte Information im Spielstand? Zwei
gezielte Suchen beantworten das und ersparen im besten Fall die ganze Strecke.

Ist er nötig, macht die Namenstabelle ihn billig: die Texterkennung muss den
Namen nicht richtig lesen, nur **nah genug**. Gegen 2266 belegte Namen
gehalten hat `PlLZFUHRER` — ohne Umlaut, mit l statt i — 0,87 Ähnlichkeit zu
"Pilzführer", und der nächste Kandidat liegt weit darunter.

Liegen zwei Kandidaten dicht beieinander: **keine** Auskunft, sondern die
Kandidatenliste. Eine unentschiedene Lesung ist keine Empfehlung.

Unter Windows steckt eine brauchbare Texterkennung im System (`winsdk`,
`Windows.Media.Ocr`) — lokal, ohne Konto, ohne Netz. Und ein Weg, die Namen
von Hand einzugeben, hält die Kette am Leben, wenn nichts installiert ist.

## Reihenfolge

1. **Messen** (Format, Takt, Sprache) — entscheidet alles Weitere
2. **Namen** aus den Spieldateien — jede spätere Ausgabe hängt daran
3. **Spielstand lesen**, robust gegen fehlende Felder und halbe Bündel
4. **Mitschreiben** — Vorhersagen brauchen zwei Zustände, Auswertungen viele
5. **Werkzeuge als Funktionen**, dann die Anbindung
6. **Bildschirm** — nur, wenn Schritt 1 ihn nicht erübrigt hat
7. **Oberfläche** — zuletzt, und sie rechnet nichts

Schritt 7 erst am Ende, weil eine Oberfläche bestehende Fehler nicht offenlegt,
sondern hinter einem hübscheren Fenster versteckt.

## Was ein solcher Assistent nicht tut

Nicht klicken, nicht in den Spielstand schreiben, nichts am Spielprozess
verändern. Lesen und rechnen. Das hält ihn auf der richtigen Seite jeder
Nutzungsbedingung — und es ist ohnehin der nützlichere Teil.
