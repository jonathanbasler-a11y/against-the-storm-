---
name: erst-messen
description: Eine Arbeitsweise für Aufgaben, bei denen eine falsche Annahme teuer wird -- erst messen statt bauen, je Fehler zuerst der Test, der ihn zeigt, Namen und APIs nachschlagen statt erinnern, und am Ende sagen, was nicht geprüft wurde. Nutzen, wenn eine Aufgabe auf Vermutungen über ein fremdes System aufbaut (Dateiformate, APIs, Spieldaten, Fremdsoftware), wenn ein Fehler gesucht wird, wenn "alle Tests grün" behauptet werden soll, oder wenn jemand ein größeres Vorhaben plant und wissen will, womit anzufangen ist. Auch nutzen, wenn ein Plan Schritte enthält, die sich mit einer kurzen Messung erübrigen könnten.
---

# Erst messen, dann bauen

Die teuersten Fehler in einem Vorhaben sind nicht die, die abstürzen. Es sind
die, die ein richtiges Ergebnis vortäuschen: ein grüner Test, der nichts
prüft. Eine Datenbank, die stillschweigend leer angelegt wurde. Ein Name, der
plausibel klingt und falsch ist.

Diese Arbeitsweise ist darauf ausgelegt, genau solche Fehler früh und billig
zu finden. Sie kostet am Anfang Zeit und spart sie danach.

## Die Messung geht dem Bau voraus

Bevor etwas gebaut wird, das auf einer Annahme über ein fremdes System ruht:
**die Annahme prüfen.** Nicht recherchieren, nicht überlegen — messen.

Eine Annahme ist es wert, gemessen zu werden, wenn ihre Widerlegung den Plan
ändern würde. Dafür reicht meist ein Befehl.

> **Beispiel.** Für einen Spielassistenten war eine Texterkennung geplant, um
> den Auswahlbildschirm zu lesen — der teuerste Teil des Plans. Offen war, ob
> die Auswahl nicht schon im Spielstand steht. Zwei Befehle haben es
> entschieden (sie steht nicht drin, das Spiel würfelt sie neu). Danach hatte
> der teure Teil eine Berechtigung statt einer Hoffnung.

Die Messung ist auch dann ein Gewinn, wenn sie die Annahme bestätigt: sie
verwandelt eine Vermutung in einen Befund, auf den sich später berufen lässt.

**Die Umkehrung ist genauso wichtig.** Wenn ein Plan einen Schritt enthält,
der sich durch eine kurze Messung erübrigen könnte, gehört die Messung vor
den Schritt — nicht danach, wenn schon gebaut ist.

## Je Fehler zuerst der Test, der ihn zeigt

Ein Fehler ohne Regressionstest ist ein Fehler, der wiederkommt. Deshalb:
erst den Test schreiben, ihn **fehlschlagen sehen**, dann beheben.

Das Fehlschlagen ist der Punkt. Ein Test, der sofort grün ist, prüft
womöglich etwas anderes als gedacht — und das merkt man nur in diesem einen
Moment.

> **Beispiel.** Beim Abgleich zweier Datenquellen meldete die Gegenprobe
> nichts, obwohl sichtbar Unsinn in der Ausgabe stand. Die beiden Quellen
> berührten sich beim Schlüsselnamen gar nicht — die Prüfung lief ins Leere.
> Ohne den Versuch, sie fehlschlagen zu sehen, hätte ihr Schweigen wie
> Bestätigung ausgesehen.

## Ein grüner Test, der nichts prüft, ist das schlimmste Ergebnis

Schlimmer als ein roter Test, schlimmer als gar kein Test. Er kauft
Zuversicht, die nicht gedeckt ist.

Woran er zu erkennen ist:

- **Er wird nie rot.** Einmal versuchsweise kaputtmachen, was er prüfen soll.
  Bleibt er grün, prüft er es nicht.
- **Er läuft allein anders als in der Suite.** Dann laufen Zustände zwischen
  den Tests aus. Attrappen in `sys.modules`, gemeinsame Verzeichnisse,
  Klassenvariablen.
- **Er fasst keinen Einstiegspunkt an.** Was kein Test ruft, kann beim Umbau
  spurlos verschwinden — und die Suite bleibt grün.

> **Beispiel.** Ein Attrappen-Test entfernte sein Modul aus `sys.modules`,
> aber nicht das Attribut am Paket. Der Test mit der echten Bibliothek
> bekam danach dieselben Attrappen: allein grün, in der Suite rot, und
> dazwischen eine Weile grün, ohne etwas zu prüfen.

## Nachschlagen schlägt erinnern

Bei allem, was ein anderes System festlegt — Namen, API-Parameter,
Dateiformate, Versionsnummern —: nachsehen. Auch und gerade, wenn die
Erinnerung sicher wirkt.

> **Beispiel.** Aus einer sorgfältigen Recherche stammten 124 Übersetzungen.
> Gegen die Datei des Programms gehalten waren **36 davon falsch** — und zwei
> hätten auf das falsche Gebäude gezeigt. Dieselbe Recherche hatte einen
> ganzen Namensraum übersehen: 429 Einträge, ausgerechnet in der Kategorie,
> um die es ging.

Das gilt auch für sich selbst: eine eigene Angabe von gestern ist eine
Erinnerung, keine Quelle.

## Widersprüche nicht glätten

Wenn zwei Quellen sich widersprechen, ist der Widerspruch die Information.
Ihn still zugunsten einer Seite aufzulösen, versteckt ihn nur.

Stattdessen: die belastbarere Quelle gewinnen lassen, **und die andere
sichtbar danebenstehen lassen**. Wer später nachsieht, findet beides.

Dasselbe gilt für Belastbarkeit allgemein: wo Daten aus verschiedenen Quellen
zusammenlaufen, gehört an jede Zeile, woher sie kommt. Dann lässt sich später
entscheiden, was eine Auskunft trägt und was nicht.

## Sagen, was nicht geprüft wurde

Am Ende einer Arbeit steht nicht nur, was läuft, sondern auch, was nicht
geprüft werden konnte — und warum.

Das ist keine Bescheidenheit. Wer die Lücke kennt, kann sie schließen; wer sie
nicht kennt, verlässt sich auf etwas, das niemand angesehen hat.

> **Beispiel.** "228 Tests grün" und "das Fenster wurde hier nie unter
> Windows gestartet" sind beide wahr und gehören beide in denselben Bericht.

## Woran der eigene Lauf zu prüfen ist

Bevor "alle Tests grün" behauptet wird:

- **Welche Laufzeit?** Version, Interpreter, Abhängigkeiten. Eine Suite kann
  lange gegen eine Version laufen, die das Projekt gar nicht unterstützt.
  Ein Test, der die verlangte Version gegen die laufende hält, macht daraus
  eine rote Zeile statt einer stillen Abweichung.
- **Welcher Pfad?** Relative Pfade zeigen auf das Arbeitsverzeichnis, und das
  bestimmt beim Start oft jemand anderes. Wo eine fehlende Datei
  stillschweigend neu angelegt wird, entsteht aus einem Pfadfehler eine leere
  Antwort statt eines Fehlers.
- **Welcher Pfad durch den Code?** Wenn eine Prüfung den teuren Weg
  überspringt (Attrappe, Kurzschluss, Zwischenspeicher), prüft sie ihn nicht.
  Genau dort sitzen die Fehler, die erst der Nutzer findet.

## Wenn etwas doch erst beim Nutzer auffällt

Dann fehlte ein Test, nicht Sorgfalt. Die Behebung ist zweiteilig: der Fehler
**und** der Test, der ihn gezeigt hätte. Ohne den zweiten Teil ist es
Flickwerk.

Und es gehört gesagt — klar, einmal, ohne Umschweife und ohne Aufhebens.
Dann weiter.
