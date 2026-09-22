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

## Die Antwort (22.09.2026)

Gemessen an einer offenen Grundsteinwahl — angeboten waren **Pilzführer**
(`Fungal Guide`) und **Exportspezialisierung** (`Export Specialization`),
gespeichert mit offenem Auswahlbildschirm:

```
python tools/find_choice.py scan --save "...\Save.save"
  31 Listen aus lauter Bezeichnern -- keine davon das Angebot

python tools/find_choice.py find --save "...\Save.save" \
    --term "Pilzführer" "Exportspezialisierung"
  Gesucht: Pilzführer, Fungal Guide, Reward_MushroomSpecialization_Name,
           MushroomSpecialization, Exportspezialisierung, Export Specialization,
           Reward_PacksRawProd_Name, PacksRawProd
  Keiner dieser Namen steht im Spielstand -- auch nicht als Text.
```

**Die Auswahl steht nicht im Spielstand.** Das Spiel würfelt sie aus einem
Keim neu, statt sie zu speichern. Phase 3 braucht den Bildschirm — nicht als
erste Wahl, sondern als einzige.

Das kostete zwei Befehle. Auf Verdacht gebaut hätte es eine Texterkennung
gekostet, die vielleicht nichts zu tun hat.

## Was den Bildschirm billig macht

Die Texterkennung muss den Namen nicht richtig lesen. Sie muss ihn nur nah
genug lesen, dass der Abgleich eindeutig wird — und dagegen stehen **2266
belegte deutsche Namen** aus der Lokalisierung des Spiels.

`PlLZFUHRER`, ohne Umlaut und mit l statt i, hat 0,87 Ähnlichkeit zu
„Pilzführer"; der nächste Kandidat liegt weit darunter. Genau dafür wurden
die Namen vorher belegt statt geraten.

Liegen zwei Kandidaten dicht beieinander, gibt es **keine** Auskunft, sondern
die Kandidatenliste. Eine unentschiedene Lesung ist keine Empfehlung.

## Die Kette

| Stufe | Modul | Notausgang |
|---|---|---|
| Aufnehmen | `screen.aufnehmen` — `mss`, sonst PowerShell (in Windows eingebaut) | Bildschirmfoto von Hand, `--bild` |
| Erkennen | `screen.erkenne` — Windows-Texterkennung über `winsdk`, sonst Tesseract | Titel abtippen, `--text` |
| Abgleichen | `namen_match` gegen die belegten Namen | — |

Jede Stufe ist einzeln ersetzbar, und jede hat einen Ausgang. Eine fehlende
Abhängigkeit legt nicht die ganze Kette still: wer keine Texterkennung
installiert hat, tippt zwei Wörter ab und bekommt dieselbe Auskunft.

    python tools/read_choice.py pruefen
    python tools/read_choice.py lesen
    python tools/read_choice.py lesen --text "PILZFÜHRER" "EXPORTSPEZIALISIERUNG"

`winsdk` nutzt die Texterkennung, die in Windows schon steckt — lokal, ohne
Konto, ohne Netz. Das ist der einzige Weg, der das Leitprinzip der Spec hält,
ohne ein weiteres Programm zu verlangen.

## Was daraus folgt

Es ist der zweite Fall eingetreten. Phase 3 ist gebaut wie in der Spec — aber
mit den belegten deutschen Namen, die seit `localization.py` aus dem Spiel
selbst kommen statt aus der Recherche. Ohne sie wäre der Abgleich auf 136
geratene Zeilen angewiesen, von denen sich 36 als falsch erwiesen haben.

Was der Bildschirm **nicht** liefert und weiter offen ist: die Baupläne. Der
Bauplanbildschirm hat dieselbe Form, also greift dieselbe Kette — aber
abgeglichen wird dann gegen `kind = building` statt `effect`. Das steht schon
im Werkzeug (`--arten building`), ist aber an keinem echten Bildschirm
geprüft.
