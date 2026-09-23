"""Das Fenster.

Es rechnet nichts. Jede Zahl kommt aus `tools_api`, jeder Satz aus
`nahrung.rat` oder `berater`. Hier steht nur, wie es aussieht und wann es
sich erneuert.

**Nebenlaeufigkeit.** Tkinter ist nicht threadsicher. Ein einzelner
Arbeits-Thread rechnet, legt Ergebnisse in eine Warteschlange, und der
UI-Thread holt sie ueber `after()` ab. Kein Werkzeugaufruf im UI-Thread:
`get_state` wartet bis zu drei Sekunden auf Ruhe, das Fenster wuerde
sichtbar haengen.

**Selbstaktualisierung.** Der Arbeits-Thread vergleicht die Signatur des
Spielordners. Aendert sie sich, wird auf Ruhe gewartet -- das Buendel ist
nicht atomar, 2,02 s Versatz gemessen -- und neu gerechnet. Das Spiel
schreibt etwa alle 300 Spielzeitsekunden; dazwischen steht im Fenster, wie
alt die Zahlen sind.
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import berater, screen
from .mcp_server import aufloesen
from .orte import finde_spielordner
from .rechner import (ABHOLEN_MS, Rechner, alter as _alter,
                      feindseligkeit as _feindseligkeit, minuten as _minuten)

# Wie lange das Fenster weg ist, bevor der Bildschirm aufgenommen wird --
# lang genug, dass Windows es wirklich aus dem Bild genommen hat.
VERSTECKT_MS = 250
# Und wann es spaetestens zurueckkommt, auch wenn keine Antwort kaeme.
SICHERUNG_MS = 8000

# Wie lange eine gelesene Auswahl gilt, gemessen in Spielzeit. Die
# Grundsteinwahl haelt das Spiel nicht an: ein Speichern kurz nach dem Lesen
# darf sie nicht verwerfen, eine lange weitergespielte Siedlung schon.
AUSWAHL_GILT_S = 600

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Das Fenster
# --------------------------------------------------------------------------


def _eigenes_foto_loeschen(quelle: str | None) -> None:
    """Nur was `screen.neuer_bildpfad` angelegt hat, nie ein fremdes Bild."""
    if not quelle:
        return
    pfad = Path(quelle)
    import tempfile
    if pfad.name.startswith("ats-auswahl-") and pfad.parent == Path(tempfile.gettempdir()):
        try:
            pfad.unlink()
        except OSError:
            pass


def _anmeldehinweis(gefunden: bool | None) -> str:
    """Was im Reiter „Rat" steht, bevor jemand fragt.

    Am Spielrechner kam die Auskunft erst nach „Fragen" -- eine Runde zu
    spät. Sie lässt sich vorher haben, ohne eine einzige Anfrage.
    """
    if gefunden is None:
        return ("Für Antworten hier: pip install anthropic. "
                "Alles andere im Fenster läuft ohne.")
    if gefunden is False:
        return ("Keine Anmeldung gefunden – ANTHROPIC_API_KEY setzen "
                "(`setx ANTHROPIC_API_KEY ...`, danach neues Fenster), oder "
                "„Lage kopieren“ und in Claude einfügen.")
    return ""


def _laeufe_text(wert: dict) -> str:
    """Lehren oben, darunter je Siedlung eine kurze Zeile -- neueste zuerst."""
    zeilen = ["Lehren:"] + [f"  • {s}" for s in wert.get("lehren") or []]
    berichte = list(reversed(wert.get("berichte") or []))
    zeilen.append("")
    zeilen.append(f"Mitgeschriebene Läufe ({len(berichte)}):" if berichte
                  else "Noch keine Mitschrift.")
    for b in berichte:
        teile = [b.get("biom") or "Biom unbekannt"]
        if b.get("jahre"):
            teile.append(f"{b['jahre']} Jahre")
        teile.append(b.get("ausgang") or "offen")
        knapp = b.get("nahrung_min_reichweite") or {}
        if knapp.get("sekunden") is not None:
            teile.append(f"Nahrung min. {_minuten(knapp['sekunden'])}"
                         + (f" (Jahr {knapp['jahr']})" if knapp.get("jahr") else ""))
        if isinstance(b.get("ungeduld_max"), (int, float)):
            teile.append(f"Ungeduld max. {b['ungeduld_max']:.1f}")
        zeilen.append(f"\n{b.get('kennung', '?')}: " + " · ".join(teile))
        for e in b.get("empfehlungen") or []:
            jahr = f"Jahr {e['jahr']}: " if e.get("jahr") else ""
            zeilen.append(f"    Rat {jahr}{e.get('text', '')}")
    return "\n".join(zeilen)


def _herkunft(a: dict) -> str:
    """Welcher Weg diese Zeilen geliefert hat.

    Am Spielrechner stand im Auswahlreiter der Rat zur Texterkennung,
    während im Handfeld getippter Text stand -- und nirgends stand, welcher
    Weg überhaupt gelaufen war. Seitdem steht es in beiden Fällen oben.
    """
    quelle = a.get("quelle")
    zeilen = a.get("gelesene_zeilen")
    woher = ("Von Hand abgeglichen" if quelle == "hand"
             else "Vom Bildschirmfoto gelesen" if quelle
             else "Nichts gelesen")
    return f"{woher} – {zeilen} Zeile(n)" if zeilen else woher


class App:
    def __init__(self, save_dir: Path, runs_dir: Path, db: Path) -> None:
        self.save_dir, self.runs_dir, self.db = save_dir, runs_dir, db
        self.zustand: dict = {}
        self.nahrung: dict = {}
        self.ungeduld: dict = {}
        self.auswahl: dict = {}

        self.root = tk.Tk()
        self.root.title("Against the Storm – Assistent")
        self.root.geometry("980x640")
        self.root.minsize(760, 520)

        self.ausgang: queue.Queue = queue.Queue()
        self.rechner = Rechner(save_dir, runs_dir, db, self.ausgang)

        self._bauen()
        self.rechner.start()
        self.root.after(ABHOLEN_MS, self._abholen)
        self.root.protocol("WM_DELETE_WINDOW", self._schliessen)

    # -- Aufbau ------------------------------------------------------------

    def _bauen(self) -> None:
        self.reiter = ttk.Notebook(self.root)
        self.reiter.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self._reiter_lage()
        self._reiter_nahrung()
        self._reiter_auswahl()
        self._reiter_rat()
        self._reiter_laeufe()

        leiste = ttk.Frame(self.root)
        leiste.pack(fill="x", padx=8, pady=6)
        self.status = ttk.Label(leiste, text="wird gelesen …", anchor="w")
        self.status.pack(side="left", fill="x", expand=True)
        self.status_alles = ""
        # Was nicht in die Zeile passt, steht im Kurzhinweis.
        self.status.bind("<Enter>", self._status_hinweis)
        ttk.Button(leiste, text="Neu lesen",
                   command=lambda: self.rechner.bitte("lage")).pack(side="right")
        self.suche = ttk.Entry(leiste, width=22)
        self.suche.pack(side="right", padx=(0, 6))
        self.suche.bind("<Return>", lambda e: self._nachschlagen())
        ttk.Button(leiste, text="Nachschlagen",
                   command=self._nachschlagen).pack(side="right", padx=(0, 4))

    def _reiter_lage(self) -> None:
        rahmen = ttk.Frame(self.reiter, padding=12)
        self.reiter.add(rahmen, text="Lage")

        self.kopf = ttk.Label(rahmen, text="–", font=("", 14, "bold"))
        self.kopf.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        self.felder: dict[str, ttk.Label] = {}
        self.balken: dict[str, ttk.Progressbar] = {}
        zeilen = [("Bevölkerung", "bevoelkerung"), ("Feindseligkeit", "feindseligkeit"),
                  ("Reputation", "reputation"), ("Ungeduld", "ungeduld"),
                  ("Nahrung reicht", "reichweite"), ("Niederlage in", "verlust")]
        for i, (titel, schluessel) in enumerate(zeilen, start=1):
            ttk.Label(rahmen, text=titel).grid(row=i, column=0, sticky="w", pady=3)
            wert = ttk.Label(rahmen, text="–", width=28, anchor="w")
            wert.grid(row=i, column=1, sticky="w", padx=12)
            self.felder[schluessel] = wert
            if schluessel in ("reputation", "ungeduld", "reichweite"):
                balken = ttk.Progressbar(rahmen, length=260, maximum=100)
                balken.grid(row=i, column=2, sticky="w")
                self.balken[schluessel] = balken
        rahmen.columnconfigure(2, weight=1)

        self.warnung = ttk.Label(rahmen, text="", foreground="#b00020", wraplength=880)
        self.warnung.grid(row=len(zeilen) + 1, column=0, columnspan=3,
                          sticky="w", pady=(12, 0))

    def _reiter_nahrung(self) -> None:
        rahmen = ttk.Frame(self.reiter, padding=12)
        self.reiter.add(rahmen, text="Nahrung")
        self.nahrung_text = tk.Text(rahmen, height=5, wrap="word", relief="flat",
                                    background=self.root.cget("background"))
        self.nahrung_text.pack(fill="x")
        self.nahrung_text.configure(state="disabled")

        spalten = ("gebaeude", "einsatz", "gewinn", "faktor", "engpass", "dauer", "plus")
        titel = ("Gebäude", "Einsatz", "+Sättigung", "Faktor", "Engpass",
                 "Arbeit", "+Reichweite")
        self.ketten = ttk.Treeview(rahmen, columns=spalten, show="headings", height=12)
        for s, t in zip(spalten, titel):
            self.ketten.heading(s, text=t)
            self.ketten.column(s, width=110 if s != "einsatz" else 200, anchor="w")
        self.ketten.pack(fill="both", expand=True, pady=(10, 0))

    def _reiter_auswahl(self) -> None:
        rahmen = ttk.Frame(self.reiter, padding=12)
        self.reiter.add(rahmen, text="Auswahl")

        oben = ttk.Frame(rahmen)
        oben.pack(fill="x")
        self.art = tk.StringVar(value="effect")
        ttk.Radiobutton(oben, text="Grundsteine", variable=self.art,
                        value="effect").pack(side="left")
        ttk.Radiobutton(oben, text="Baupläne", variable=self.art,
                        value="building").pack(side="left", padx=(8, 0))
        ttk.Radiobutton(oben, text="Aufträge", variable=self.art,
                        value="order").pack(side="left", padx=(8, 16))
        ttk.Button(oben, text="Bildschirm lesen",
                   command=self._auswahl_lesen).pack(side="left")

        hand = ttk.Frame(rahmen)
        hand.pack(fill="x", pady=(8, 0))
        ttk.Label(hand, text="oder von Hand (mit Komma trennen):").pack(side="left")
        self.hand = ttk.Entry(hand)
        self.hand.pack(side="left", fill="x", expand=True, padx=6)
        self.hand.bind("<Return>", lambda e: self._auswahl_lesen(von_hand=True))
        ttk.Button(hand, text="Abgleichen",
                   command=lambda: self._auswahl_lesen(von_hand=True)).pack(side="left")

        self.auswahl_text = tk.Text(rahmen, wrap="word", height=18)
        self.auswahl_text.pack(fill="both", expand=True, pady=(10, 0))
        self.auswahl_text.configure(state="disabled")

    def _reiter_rat(self) -> None:
        rahmen = ttk.Frame(self.reiter, padding=12)
        self.reiter.add(rahmen, text="Rat")

        oben = ttk.Frame(rahmen)
        oben.pack(fill="x")
        ttk.Label(oben, text="Frage (frei lassen für die Lage):").pack(side="left")
        self.rat_frage = ttk.Entry(oben)
        self.rat_frage.pack(side="left", fill="x", expand=True, padx=6)
        self.rat_frage.bind("<Return>", lambda e: self._rat_holen())
        self.modell = tk.StringVar(value=berater.MODELL)
        ttk.Combobox(oben, textvariable=self.modell, values=list(berater.MODELLE),
                     width=18, state="readonly").pack(side="left", padx=(0, 6))
        ttk.Button(oben, text="Fragen", command=self._rat_holen).pack(side="left")
        ttk.Button(oben, text="Lage kopieren",
                   command=self._lage_kopieren).pack(side="left", padx=(6, 0))

        self.rat_text = tk.Text(rahmen, wrap="word", height=18)
        self.rat_text.pack(fill="both", expand=True, pady=(10, 0))
        self.rat_text.configure(state="disabled")
        self.rat_fuss = ttk.Label(rahmen, text="", anchor="w")
        self.rat_fuss.pack(fill="x")

        # Widerspruch zur letzten Antwort. Er geht bei jeder spaeteren Frage
        # als gepruefte Tatsache mit -- so wird aus "Pakete oeffnen" einmal
        # ein Fehler und nicht jedes Mal wieder.
        unten = ttk.Frame(rahmen)
        unten.pack(fill="x", pady=(6, 0))
        ttk.Label(unten, text="Was stimmt nicht?").pack(side="left")
        self.korrektur = tk.StringVar(value="")
        feld = ttk.Entry(unten, textvariable=self.korrektur)
        feld.pack(side="left", fill="x", expand=True, padx=6)
        feld.bind("<Return>", lambda e: self._korrektur_senden())
        ttk.Button(unten, text="Stimmt nicht",
                   command=self._korrektur_senden).pack(side="left")
        self.rat_letzte = ""

    def _reiter_laeufe(self) -> None:
        rahmen = ttk.Frame(self.reiter, padding=12)
        self.reiter.add(rahmen, text="Läufe")
        oben = ttk.Frame(rahmen)
        oben.pack(fill="x")
        ttk.Label(oben, text="Was die mitgeschriebenen Läufe zeigen:").pack(side="left")
        ttk.Button(oben, text="Auswerten",
                   command=lambda: self.rechner.bitte("laeufe")).pack(side="right")
        self.laeufe_text = tk.Text(rahmen, wrap="word", height=20)
        self.laeufe_text.pack(fill="both", expand=True, pady=(10, 0))
        self.laeufe_text.configure(state="disabled")

    # -- Ereignisse --------------------------------------------------------

    def _auswahl_lesen(self, von_hand: bool = False) -> None:
        if von_hand:
            roh = self.hand.get().strip()
            text = [t.strip() for t in roh.split(",") if t.strip()] or None
            if not text:
                return
            self._schreiben(self.auswahl_text, "wird abgeglichen …")
            self.rechner.bitte("auswahl", arten=(self.art.get(),), text=text)
            return

        # Bildweg. `aufnehmen()` nimmt den ganzen Bildschirm -- mit diesem
        # Fenster darauf. Am Spielrechner lag es über dem Auswahldialog; ein
        # Stück weiter rechts, und die Texterkennung läse sauber die eigene
        # Oberfläche statt der Karten. Also geht es kurz aus dem Weg.
        self._schreiben(self.auswahl_text, "wird gelesen …")
        self.root.withdraw()
        self._foto_zu_spaet = False
        self._sicherung = self.root.after(SICHERUNG_MS, self._sicherheitsnetz)
        self.root.after(VERSTECKT_MS, self._foto_machen)

    def _foto_machen(self) -> None:
        """Das Foto in einem eigenen Faden, solange das Fenster weg ist.

        Nicht über den Arbeits-Thread: der stand hinter allem, was gerade
        lief -- eine Rat-Frage dauert bis zu einer Minute --, und fotografiert
        wurde am Ende das Fenster selbst. Und nicht im Hauptthread: die
        PowerShell-Aufnahme dauert Sekunden, und solange konnte das
        Sicherheitsnetz nicht feuern.
        """
        threading.Thread(target=self._foto_aufnehmen, args=(self.art.get(),),
                         daemon=True).start()

    def _foto_aufnehmen(self, art: str) -> None:
        """Im Faden: nur aufnehmen und das Ergebnis in die Warteschlange legen.
        Tk wird von hier aus nicht angefasst."""
        try:
            pfad = screen.aufnehmen(screen.neuer_bildpfad())
        except Exception as exc:
            self.ausgang.put(("foto", {"fehler": str(exc)}))
            return
        self.ausgang.put(("foto", {"bild": str(pfad), "art": art}))

    def _sicherheitsnetz(self) -> None:
        # Kommt das Foto erst danach, ist das Fenster womoeglich mit drauf.
        self._foto_zu_spaet = True
        self._fenster_zurueck()

    def _fenster_zurueck(self) -> None:
        """Zurückholen, was der Bildweg versteckt hat -- auch nach einem Fehler.

        Ein Fenster, das unsichtbar bleibt, weil die Aufnahme scheiterte,
        wäre schlimmer als eines, das im Bild steht. Deshalb hängt das
        Zurückholen an jedem Ausgang: am Ergebnis, an der Fehlermeldung und
        an einer Zeitschranke.
        """
        kennung, self._sicherung = getattr(self, "_sicherung", None), None
        if kennung is not None:
            try:
                self.root.after_cancel(kennung)
            except Exception:          # eine abgelaufene Kennung ist kein Fehler
                pass
        # Nur ein verstecktes Fenster zurueckholen: `deiconify` auf einem
        # sichtbaren hebt es ueber das Spiel und nimmt ihm den Fokus.
        try:
            versteckt = self.root.state() == "withdrawn"
        except Exception:
            versteckt = True
        if versteckt:
            self.root.deiconify()

    def _rat_holen(self) -> None:
        self._schreiben(self.rat_text, "wird gefragt …")
        self.rechner.bitte("rat", zustand=self.zustand, nahrung=self.nahrung,
                           ungeduld=self.ungeduld, auswahl=self.auswahl,
                           ketten=getattr(self, "nahrungsrat", None),
                           wissen=getattr(self, "wissen", None),
                           frage=self.rat_frage.get().strip() or None,
                           modell=self.modell.get())

    def _lage_kopieren(self) -> None:
        import json
        auszug = berater.kontext(zustand=self.zustand, nahrung=self.nahrung,
                                 ungeduld=self.ungeduld, auswahl=self.auswahl,
                                 frage=self.rat_frage.get().strip() or None,
                                 ketten=getattr(self, "nahrungsrat", None),
                                 wissen=getattr(self, "wissen", None))
        self.root.clipboard_clear()
        self.root.clipboard_append(json.dumps(auszug, ensure_ascii=False, indent=1))
        self.rat_fuss.configure(text="Lage in der Zwischenablage – in Claude einfügen.")

    def _status_hinweis(self, _ereignis=None) -> None:
        if self.status_alles and "\n" in self.status_alles:
            self.status.configure(text=self.status_alles.replace("\n", "   ·   ")[:200])

    def _nachschlagen(self) -> None:
        name = self.suche.get().strip()
        if name:
            self.rechner.bitte("nachschlag", name=name)

    def _korrektur_senden(self) -> None:
        korrektur = (self.korrektur.get() or "").strip()
        if not korrektur:
            return
        self.rechner.bitte("korrektur", aussage=getattr(self, "rat_letzte", ""),
                           korrektur=korrektur)
        self.korrektur.set("")

    def _schliessen(self) -> None:
        self.rechner.stoppen()
        self.root.destroy()

    # -- Anzeige -----------------------------------------------------------

    def _schreiben(self, feld: tk.Text, text: str) -> None:
        feld.configure(state="normal")
        feld.delete("1.0", "end")
        feld.insert("1.0", text)
        feld.configure(state="disabled")

    def _abholen(self) -> None:
        # Eine Ausnahme beim Anzeigen beendete das Abholen fuer immer: das
        # Fenster zeigte danach nichts Neues mehr. Unter pythonw steht sie
        # auch nirgends -- also ins Protokoll, und weiter.
        try:
            while True:
                try:
                    art, wert = self.ausgang.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._anzeigen(art, wert)
                except Exception:
                    log.exception("Anzeige von %s gescheitert", art)
            self._kopf_auffrischen()
        finally:
            self.root.after(ABHOLEN_MS, self._abholen)

    def _anzeigen(self, art: str, wert) -> None:
        if art == "zustand":
            self._alte_lage_verwerfen(wert or {})
            self.zustand = wert
            self._zeige_zustand(wert)
        elif art == "foto":
            if getattr(self, "_foto_zu_spaet", False):
                self._schreiben(self.auswahl_text,
                                "Das Foto dauerte zu lange – das Fenster war schon wieder "
                                "zu sehen. Bitte nochmal „Bildschirm lesen“.")
                return
            self._fenster_zurueck()
            if wert.get("fehler"):
                self._schreiben(self.auswahl_text, f"Keine Aufnahme: {wert['fehler']}")
                return
            self.rechner.bitte("auswahl", arten=(wert.get("art") or self.art.get(),),
                               bild=wert["bild"])
        elif art == "nahrung":
            self.nahrung = wert
            self._zeige_nahrung(wert)
        elif art == "ungeduld":
            self.ungeduld = wert
            self.felder["verlust"].configure(
                text=_minuten(wert.get("sekunden_bis_verlust")))
        elif art == "ketten":
            self.nahrungsrat = wert
            self._zeige_ketten(wert)
        elif art == "wissen":
            self.wissen = wert
            self._zeige_trends(wert)
        elif art == "auswahl":
            _eigenes_foto_loeschen(wert.get("quelle"))
            self.auswahl = wert
            jetzt = getattr(self, "zustand", None) or {}
            self._auswahl_lauf = jetzt.get("mitschrift")
            self._auswahl_zeit = jetzt.get("spielzeit")
            self._fenster_zurueck()
            self._zeige_auswahl(wert)
        elif art == "nachschlag":
            self._zeige_nachschlag(wert)
        elif art == "anmeldung":
            # Nur solange noch nichts Besseres dasteht: nach einer Antwort
            # gehoert dort deren Fusszeile hin, nicht wieder ein Hinweis.
            if not getattr(self, "_rat_gefragt", False):
                self.rat_fuss.configure(text=_anmeldehinweis(wert))
        elif art == "rat":
            # Erst eine echte Antwort ersetzt den Anmeldehinweis; nach einer
            # gescheiterten darf ein spaeter gesetzter Schluessel ihn loeschen.
            self._rat_gefragt = bool(wert.get("ok"))
            self._schreiben(self.rat_text, wert.get("text", ""))
            if wert.get("ok"):
                self.rat_letzte = wert.get("text", "")
                fuss = wert.get("fuss", "")
            elif not wert.get("zugang"):
                fuss = "Ohne Anmeldung: „Lage kopieren“ und in Claude einfügen."
            else:
                fuss = ""
            self.rat_fuss.configure(text=fuss)
        elif art == "korrektur":
            self.rat_fuss.configure(
                text=f"Gemerkt, gilt ab der nächsten Frage: {wert.get('korrektur', '')}")
        elif art == "laeufe":
            self._schreiben(self.laeufe_text, _laeufe_text(wert))
        elif art == "umgebung":
            offen = wert.get("fehlt") or []
            if not offen:
                text = (f"Alles bereit – {wert.get('namen', 0)} Namen, "
                        f"{wert.get('mitschriften_da', 0)} Mitschriften")
            else:
                # Drei Sätze nebeneinander laufen rechts aus dem Fenster und
                # werden abgeschnitten -- dann fehlt ausgerechnet das Ende,
                # in dem steht, was zu tun ist. Einer steht da, der Rest
                # gezählt; alle zusammen im Kurzhinweis.
                text = offen[0]
                if len(offen) > 1:
                    text += f"   (+{len(offen) - 1} weitere)"
            self.status.configure(text=text)
            self.status_alles = "\n".join(offen)
        elif art == "fehler":
            self.status.configure(text=f"Fehler: {wert}")

    def _alte_lage_verwerfen(self, neu: dict) -> None:
        """Was zur vorigen Lage gehoert, geht nicht mehr an den Rat.

        Ohne Spielstand gehen Nahrung, Ungeduld, Ketten und Auswahl der
        letzten Siedlung. Eine Auswahl verfaellt ausserdem mit einer neuen
        Siedlung oder wenn lange weitergespielt wurde -- sonst ging eine alte
        Grundsteinwahl bei jeder spaeteren Frage mit.
        """
        if neu.get("verfuegbar") is False:
            self.nahrung = self.ungeduld = self.nahrungsrat = self.wissen = None
            verfallen = True
        else:
            lauf, zeit = neu.get("mitschrift"), neu.get("spielzeit")
            start = getattr(self, "_auswahl_zeit", None)
            verfallen = (
                (lauf is not None and getattr(self, "_auswahl_lauf", None) is not None
                 and lauf != self._auswahl_lauf)
                or (zeit is not None and start is not None
                    and (zeit < start or zeit - start > AUSWAHL_GILT_S)))
        if verfallen and getattr(self, "auswahl", None):
            self.auswahl = None
            self._schreiben(self.auswahl_text,
                            "Die gelesene Auswahl ist verfallen – das Spiel lief weiter. "
                            "Neu lesen, falls sie noch offen ist.")

    def _kopf_auffrischen(self) -> None:
        """Das Alter im Kopf laeuft mit -- sonst stand "gerade eben" ewig."""
        z = getattr(self, "zustand", None)
        if not z or z.get("verfuegbar") is False:
            return
        if z.get("gespeichert"):
            wann = _alter(z["gespeichert"], "gespeichert")
        else:
            wann = _alter(z.get("zeitpunkt"))
        text = (f"Jahr {z.get('jahr', '?')} · {z.get('biom') or '?'} · "
                f"Prestige {z.get('prestige', '?')} · {wann}")
        if text != getattr(self, "_kopf_text", None):
            self._kopf_text = text
            self.kopf.configure(text=text)

    def _warnung_zeigen(self) -> None:
        """Zustand und Nahrung warnen beide in dieselbe Zeile. Vorher
        ueberschrieb die Nahrung im selben Durchgang, was der Zustand sagte."""
        teile = [t for t in (getattr(self, "_warn_zustand", ""),
                             getattr(self, "_warn_nahrung", ""),
                             getattr(self, "_warn_trends", "")) if t]
        self.warnung.configure(text="  ·  ".join(teile))

    def _zeige_zustand(self, z: dict) -> None:
        if z.get("verfuegbar") is False:
            self.kopf.configure(text="Kein Spielstand")
            self._warn_zustand = z.get("grund") or z.get("fehler", "")
            self._warn_nahrung = ""
            # Die Werte der letzten Siedlung sind keine Aussage ueber jetzt.
            for feld in self.felder.values():
                feld.configure(text="–")
            for balken in self.balken.values():
                balken.configure(value=0)
            self._warnung_zeigen()
            return
        self._kopf_auffrischen()
        # Ein stiller Ausfall ist schlimmer als ein lauter: `lager: {}` sah
        # aus wie ein leeres Lager und war ein nicht gefundenes Feld.
        fehlend = z.get("nicht_gefunden") or []
        unlesbar = list(z.get("form_unbekannt") or {})
        saetze = []
        if fehlend:
            saetze.append("Im Spielstand nicht gefunden: " + ", ".join(fehlend[:6]) + ".")
        if unlesbar:
            # Etwas anderes als „fehlt": das Feld ist da, nur in einer Form,
            # die der Leser nicht kennt. `tools\lage.py form` zeigt sie.
            saetze.append("Gefunden, aber nicht lesbar: " + ", ".join(unlesbar[:6])
                          + " (python tools\\lage.py form zeigt den Aufbau).")
        self._warn_zustand = (" ".join(saetze) + " Was darauf rechnet, rechnet auf nichts."
                              if saetze else "")
        self._warnung_zeigen()
        self.felder["bevoelkerung"].configure(text=str(z.get("bevoelkerung") or "–"))
        self.felder["feindseligkeit"].configure(
            text=_feindseligkeit(z.get("feindseligkeit")))

        for schluessel, jetzt, ziel in (
                ("reputation", z.get("reputation"), z.get("reputation_ziel")),
                ("ungeduld", z.get("ungeduld"), z.get("ungeduld_schwelle"))):
            if jetzt is None:
                self.felder[schluessel].configure(text="–")
                self.balken[schluessel].configure(value=0)
                continue
            self.felder[schluessel].configure(
                text=f"{jetzt:.1f} von {ziel}" if ziel else f"{jetzt:.1f}")
            self.balken[schluessel].configure(
                value=min(jetzt / ziel * 100, 100) if ziel else 0)

    def _zeige_nahrung(self, n: dict) -> None:
        self.felder["reichweite"].configure(text=_minuten(n.get("reichweite_sekunden")))
        reichweite = n.get("reichweite_sekunden")
        # Voll ist der Balken bei einer Stunde Reichweite. Ohne Wert leer --
        # sonst stand er voll neben "0 s".
        self.balken["reichweite"].configure(
            value=min(reichweite / 3600 * 100, 100) if reichweite else 0)
        self._warn_nahrung = n.get("warnung") or n.get("grund") or ""
        self._warnung_zeigen()

    def _zeige_trends(self, wissen: dict) -> None:
        """Die Waren, die am schnellsten fallen -- wie „Verlauf" im Spiel,
        nur alle auf einmal."""
        fallend = ((wissen or {}).get("trends") or {}).get("fallend") or []
        teile = [f"{t.get('ware_de') or t['ware']} {t['rate_je_minute']:+.1f}/min"
                 for t in fallend[:4]]
        self._warn_trends = ("Fällt: " + ", ".join(teile)) if teile else ""
        self._warnung_zeigen()

    def _zeige_ketten(self, rat: dict) -> None:
        saetze = [rat.get(k) for k in ("empfehlung", "begruendung", "alternative")]
        self._schreiben(self.nahrung_text, "\n".join(s for s in saetze if s)
                        or rat.get("grund") or rat.get("fehler", ""))
        self.ketten.delete(*self.ketten.get_children())
        for k in rat.get("ketten", []):
            einsatz = ", ".join(f"{e['menge']:.0f} {e['ware']}" for e in k["einsatz"])
            name = k.get("gebaeude_de") or k.get("gebaeude") or "?"
            # Steht es, laesst es sich bauen, oder fehlt es? Am Spielrechner
            # stand hier ein Grill, den es in der Siedlung nicht gab.
            if k.get("status") in ("steht", "baubar", "fehlt"):
                name += f" ({k['status']})"
            self.ketten.insert("", "end", values=(
                name, einsatz,
                f"{k['gewinn']:.0f}", k.get("faktor") or "–", k.get("engpass") or "–",
                _minuten(k.get("sekunden")),
                _minuten(k.get("reichweite_plus_sekunden"))))

    def _zeige_auswahl(self, a: dict) -> None:
        zeilen = [_herkunft(a), ""]
        if not a.get("verfuegbar"):
            zeilen.append(a.get("grund") or a.get("fehler", "Nichts erkannt."))
            for u in a.get("unklar", []):
                nahe = ", ".join(f"{k['de']} ({k['guete']})" for k in u["kandidaten"])
                zeilen.append(f"  gelesen {u['gelesen']!r} → {nahe}")
            # Der Bildweg ist gescheitert, während im Handfeld etwas steht.
            # Der Knopf bleibt, was er heißt -- aber es darf nicht daran
            # liegen, dass niemand den zweiten Weg sieht.
            if a.get("quelle") != "hand" and self.hand.get().strip():
                zeilen.append("")
                zeilen.append("Im Feld unten steht Text -- „Abgleichen“ nimmt ihn, "
                              "ganz ohne Texterkennung.")
            self._schreiben(self.auswahl_text, "\n".join(zeilen))
            return
        belegt = [e for e in a["angebot"] if e.get("belegt", True)]
        sonst = [e for e in a["angebot"] if not e.get("belegt", True)]
        for eintrag in belegt:
            kopf = f"{eintrag['de']}  ({eintrag['en']}"
            if eintrag.get("seltenheit"):
                kopf += f", {eintrag['seltenheit']}"
            zeilen.append(kopf + f", Güte {eintrag['guete']})")
            for feld in ("wirkung", "zweck"):
                if eintrag.get(feld):
                    zeilen.append(f"    {eintrag[feld]}")
            zeilen.append("")

        # Die Aufnahme nimmt den ganzen Bildschirm. Was die Wissensbasis
        # nicht als Angebot kennt, ist meist Oberfläche -- am Spielrechner
        # die Spezies oben links. Weggeworfen wird es trotzdem nicht: die
        # Tabelle kennt 398 Grundsteine bei 2273 Namen.
        if sonst:
            zeilen.append("Auch erkannt, aber nicht als Angebot belegt "
                          "(meist Oberfläche):")
            zeilen.append("    " + ", ".join(
                f"{e['de']} ({e['guete']})" for e in sonst))
            zeilen.append("")
        if a.get("unsicher"):
            zeilen.append("Unsicher gelesen – stand das so da?")
            zeilen.append("    " + ", ".join(
                f"{e['de']} ({e['guete']})" for e in a["unsicher"]))
            zeilen.append("")
        self._schreiben(self.auswahl_text, "\n".join(zeilen))

    def _zeige_nachschlag(self, out: dict) -> None:
        fenster = tk.Toplevel(self.root)
        fenster.title(f"Nachschlag: {out.get('gesucht', '')}")
        text = tk.Text(fenster, wrap="word", width=90, height=20)
        text.pack(fill="both", expand=True)
        zeilen = []
        for n in out.get("namen", []):
            zeilen.append(f"{n['de']:<28} {n['en']:<28} {n.get('kind') or '':<12} "
                          f"{n['confidence']}")
        for schluessel in ("ware", "gebaeude", "grundstein", "hinweis", "fehler"):
            if out.get(schluessel):
                zeilen.append(f"\n{schluessel}: {out[schluessel]}")
        text.insert("1.0", "\n".join(zeilen) or "Nichts gefunden.")
        text.configure(state="disabled")

    def laufen(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save-dir", default=None)
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--db", default="kb.sqlite")
    args = ap.parse_args(argv)

    protokoll = aufloesen("logs")
    protokoll.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.FileHandler(protokoll / "gui.log", encoding="utf-8")])

    save_dir = Path(args.save_dir) if args.save_dir else finde_spielordner()
    if save_dir is None:
        save_dir = Path("kein-spielordner")
    App(save_dir, aufloesen(args.runs), aufloesen(args.db)).laufen()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
