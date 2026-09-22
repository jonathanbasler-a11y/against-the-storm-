# Phase 3, bevor sie gebaut wird (2026-09-22)

SPEC.md beschreibt Phase 3 als Bildschirmauslesung: Fenster finden,
ausschneiden, Text erkennen, gegen die Namenstabelle halten. Das ist der
teuerste Teil des Plans und der einzige, der nicht deterministisch arbeitet —
eine Texterkennung liest sich verlesen, und zwar lautlos.

Dabei ist gar nicht geprüft, ob es sie braucht.

## Die Frage

Eine offene Grundsteinwahl übersteht das Speichern und Laden. Wer mitten in
der Auswahl speichert, beendet und wieder lädt, steht wieder vor denselben
drei Karten. Also **muss** der Spielstand die angebotenen Grundsteine
mitführen — sonst könnte das Spiel sie nach dem Laden nicht wiederherstellen.

Phase 0 hat gezeigt, dass der Spielstand sein Vokabular im Klartext führt:
169 Gebäude, 65 Effekte, die vollständige Warenliste, alles als englische
Bezeichner. Wenn die angebotene Auswahl dort ebenso steht, ist `read_choice`
keine Bildschirmaufgabe, sondern eine Abfrage — und die ganze Phase schrumpft
auf ein paar Zeilen in `save_reader.py`.

Das ist eine Behauptung, keine Messung. Deshalb gibt es ein Werkzeug, das sie
prüft, statt sie zu glauben.

## Das Werkzeug

    python tools/find_choice.py scan --save "C:/.../Save.save"

Zu laufen, **während der Auswahlbildschirm offen ist** — also: Grundsteinwahl
erscheint, Spiel manuell speichern (F5 oder Menü), dann den Befehl.

Das Werkzeug durchsucht den ganzen Baum nach Listen, die ausschließlich aus
Bezeichnern bestehen, und bewertet sie: drei bis acht Einträge, ein
Schlüsselname wie `options`, `picked`, `available`, `rewards`, und Einträge,
die die Wissensbasis kennt. Die deutschen Namen stehen daneben, damit sich
ein Treffer mit einem Blick prüfen lässt:

    [ 14] effects.currentOptions
          Beanery = Imbiss, Cellar = Weinkeller, Tavern = Schänke
          Pfad nennt current/option; 3 Eintraege; 3 davon bekannt

Wenn dort die drei Namen stehen, die im Spiel zur Wahl standen, ist die Frage
beantwortet.

## Der stärkere Beleg

Ein einzelner Spielstand zeigt nur Kandidaten. Zwei zeigen die Mechanik:

    python tools/find_choice.py diff --before vorher/Save.save --after nachher/Save.save

Vorher mit offener Wahl, nachher nach dem Zugriff. Gesucht wird das Paar, bei
dem eine Liste schrumpft und genau einer ihrer Einträge woanders auftaucht —
das Angebot und die getroffene Wahl. Ein Fund dieser Art ist kein Verdacht
mehr.

`tools/snapshot_saves.py` legt beide Stände weg, ohne den Spielordner
anzufassen.

## Was daraus folgt

| Ausgang | Phase 3 |
|---|---|
| Auswahl steht im Spielstand | entfällt. `read_choice` liest mit, wie alles andere. Kein Bildschirmfoto, keine Texterkennung, keine neue Abhängigkeit. |
| Auswahl steht nicht im Spielstand | wird gebaut wie in der Spec — aber dann mit den richtigen deutschen Namen, denn die kommen seit `localization.py` aus dem Spiel selbst statt aus der Recherche. |

Die zweite Möglichkeit ist unwahrscheinlich, aber nicht ausgeschlossen: das
Spiel könnte die Auswahl aus einem Zufallskeim neu würfeln statt sie zu
speichern. Dann stünde im Spielstand der Keim und nicht das Ergebnis, und
`diff` fände kein Paar. Auch das wäre eine Antwort.

## Warum das hier steht und nicht schon gebaut ist

SPEC.md sagt: „Arbeite Phase für Phase. Baue nicht auf Verdacht weiter."
Phase 3 auf Verdacht zu bauen hieße, eine Texterkennung zu schreiben, die
vielleicht nichts zu tun hat. Der Befehl oben kostet zwei Minuten am
Spielrechner und entscheidet es.
