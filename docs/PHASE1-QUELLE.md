# Vor Phase 1: taugt der Spielstand als Quelle für `kb.sqlite`?

Die Phase-0-Messung hat in `MetaSave.save` eine Liste `content.buildings` mit
169 Einträgen gefunden. Das ist ungefähr die Größenordnung des gesamten
Gebäudebestands von *Against the Storm* — also möglicherweise der Katalog des
Spiels und nicht nur der Freischaltstand.

Falls ja, wäre das die bessere Quelle als das Wiki: aktuell zur installierten
Version 1.10.4, in denselben IDs wie der Rest des Saves, ohne Crawlen, ohne
den Versionsvorbehalt, den die Spec für das Wiki verlangt („stellenweise auf
Spielversion 1.8 bis 1.9"). Falls nein, bleibt der Scraper.

Diese Frage entscheidet den Zuschnitt von Phase 1, deshalb wird sie vorher
geklärt und nicht nebenbei.

## Ausführen

```powershell
python tools\kb_probe.py --dump-ids
```

Liest `Save.save`, `WorldSave.save` und `MetaSave.save` ausschließlich lesend,
schreibt nur nach `diagnostics\`. Dauert Sekunden. `--dump-ids` legt die
gefundenen ID-Listen zusätzlich als Textdateien ab — falls der Save das
Vokabular hergibt, ist das direkt der Grundstock für die Wissensbasis.

## Was die Sonde beantwortet

Sie sucht katalogartige Strukturen — Listen ab zwölf Einträgen, Zuordnungen
mit vielen Schlüsseln — und meldet je Struktur den Pfad, die Länge, die Felder
je Eintrag und ein paar echte Beispieleinträge. Daraus fällt für jede Tabelle
aus SPEC.md Phase 1 ein Befund in einer von vier Stufen:

| Befund | Bedeutung für Phase 1 |
|---|---|
| **IDs und Zahlen** | Der Save ersetzt das Wiki für diese Tabelle. Kosten, Rezepte, Arbeitsplätze stehen drin. |
| **IDs und Attribute** | Vokabular und Einordnung (Seltenheit, Kategorie) kommen aus dem Save, Kosten und Rezepte aus dem Wiki. |
| **nur IDs** | Der Save liefert die verbindliche ID-Liste, alle Zahlen kommen aus dem Wiki. |
| **nicht gefunden** | Diese Tabelle kommt vollständig aus dem Wiki. |

## Was ich erwarte

Meine Vermutung, damit sie überprüfbar ist statt hinterher plausibel: **für
die meisten Tabellen „nur IDs"**. Definitionen wie Kosten und Rezepte liegen
bei Unity-Spielen üblicherweise in den Asset-Bundles, nicht im Spielstand; der
Save verweist nur auf IDs. `content.buildings` wäre dann eine Liste von
Gebäudenamen, keine Datensätze.

Das wäre trotzdem ein Gewinn, nur ein kleinerer: die verbindliche ID-Liste
fixiert die Schlüssel von `kb.sqlite` und die `en`-Spalte von `name_map`,
womit das Wiki nur noch Zahlen liefern muss und keine Namen mehr raten kann.
Aus 109 geratenen Namenspaaren würden geprüfte Schlüssel.

Die Gegenprobe sind die Gebäudeinstanzen in `Save.save`. Die tragen Rezepte
und Arbeiterzahlen — aber als Zustand dieser Siedlung, nicht als Definition.
Die Sonde meldet beides getrennt, damit der Unterschied nicht verwischt.

## Danach

Der Befund entscheidet, wie Phase 1 zugeschnitten wird:

- Überwiegend „IDs und Zahlen" → der Scraper entfällt weitgehend, Phase 1
  wird zum Import aus dem Save plus Lückenfüllung aus dem Wiki.
- Überwiegend „nur IDs" → der Scraper bleibt, bekommt aber die ID-Liste als
  Sollvorgabe. Das macht ihn prüfbar: was das Wiki nicht liefert, fällt auf.
- Überwiegend „nicht gefunden" → Phase 1 wie in der Spec beschrieben.
