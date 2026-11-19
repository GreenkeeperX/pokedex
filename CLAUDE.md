# Hinweise für die Arbeit am Repository

**Dieses Repository ist öffentlich.** Vor jedem Commit und jedem Push prüfen, dass nirgends private Angaben
stehen: nicht im Code, in Kommentaren, Tests, Beispielen, in der README, der ROADMAP.md oder in Commit-Texten.

Nicht hinein gehören:
- Namen von Personen, auch Vornamen und Benutzernamen. Wer das Tool nutzt, heißt „User“ oder gar nicht;
  Entscheidungen stehen mit Datum („Entscheidung 09.11.2026“), ohne Herkunft,
- Hostnamen, interne Domains, IP-Adressen, Zugangsdaten, API-Schlüssel,
- eigene Daten: eigene Teams, Spielstände, Listen und Exporte. Testdaten sind erfunden.

Prüfung vor dem Push, zum Beispiel:

    git diff origin/main --stat
    git grep -n -i -E "192\.168\.|10\.0\.|@[a-z0-9-]+\.(de|com)|token|passw"

Ein Name fällt mit grep nicht sicher auf. Deshalb den eigenen Diff vor dem Push lesen.

Feste Regeln (wie im VR-Navigator und im eShopKompass):
- nur die Python-Standardbibliothek und reines JavaScript ohne Build, keine Abhängigkeiten,
- Quellen schonend abrufen: Pausen je Server, Abbruch bei 403 und 429 (Quelle ruht 24 Stunden), ehrliche Kennung,
- die Härtung des Containers bleibt (read_only, cap_drop ALL, no-new-privileges, Benutzer 10001),
- keine Formel aus dem Gedächtnis: Quelle und Herleitung nach `docs/formeln.md`, Angenommenes dort unter „Offen“,
  Vergleichswerte als Test,
- jede Version mit Tests (`python3 -m unittest tests.test_all`), neuer Nummer und Eintrag in `NEUIGKEITEN` in `app/sources.py`,
  aktueller README und ROADMAP.md. Die ROADMAP führt nur Geplantes, Offenes und Entscheidungen, keine Abschnitte je Version;
  was sich geändert hat und warum (auch bei Entferntem: was, wo, wer griff zu, Ersatz, Tests), steht in Commit und Pull Request,
- kein stiller Ersatzwert: `except Exception` meldet mit `fehler.melden(e)` und macht dann weiter; in der Oberfläche
  `.catch(teil("Was", Ersatz))` beim Laden und `.catch(ungespeichert(zurück))` beim Speichern. Ausnahmen stehen mit
  Grund in `test_keine_stillen_ersatzwerte`,
- user.db lädt nach jedem Update weiter: nur neue Tabellen und Spalten, nie löschen (`app/db.py`),
- ändern sich die aufbereiteten Tabellen in `app/importer.py`, `importer.VERSION` erhöhen; dann baut der nächste Abgleich neu,
- eine Regel je Spiel gehört ins Spielprofil (`app/spiele.py`), nicht als Vergleich mit einer Kennung in Server oder
  Oberfläche (Test `Spiele`),
- ändert sich eine Antwort des Servers mit Absicht, `python3 -m tests.vertrag` ausführen; liest eine Abfrage eine neue
  Tabelle der PokéAPI, gehört sie in `importer.NEEDED` (Test).

## Aufbau

- `app/sources.py`: Netzabruf (`request`, `fetch`, nur öffentliche Ziele), `VERSION`
- `app/store.py`: kleine JSON-Dateien im Datenordner (`settings.json`, `sync.json`, `ruhe.json`, `fehler.json`, `bedarf.json`)
- `app/fehler.py`: Fehlerregister (`melden` für Ausnahmen, `notiere` für Ereignisse; eine fehlende Tabelle ist kein Fehler)
- `app/statuskarte.py`: Statuskarte der Einstellungen (Gesamtstatus und Gründe, ohne Netz); Regeln in `docs/abrufe.md`
- `app/jagd.py`: Shiny-Jagd (Quoten aus `extra/shiny_quoten.json`, Wahrscheinlichkeit, Zähler in user.db); Formel in `docs/formeln.md`
- `app/nuzlocke.py`: Nuzlocke-Läufe (Regeln, erste Begegnung je Gebiet, Levelgrenze; Läufe in user.db); Regeln in `docs/formeln.md`
- `app/leistung.py`: Leistungstest auf Klick (eigene Schnittstelle über 127.0.0.1, ohne Netz, user.db unberührt)
- `app/wiederherstellung.py`: monatlicher Wiederherstellungstest der jüngsten Sicherung (temporärer Ordner, Produktivdaten unberührt)
- `app/db.py`: pokeapi.db (Spieldaten, nur lesend) und user.db (Teams, Entscheidungen), tägliche Sicherung
- `app/importer.py`: baut pokeapi.db aus den CSV-Texten der PokéAPI, Showdown und `extra/` (ohne Netz), Selbstprüfung
- `app/showdown.py`: liest `pokedex.ts` und `moves.ts` von Pokémon Showdown (ohne Netz)
- `app/smogon.py`: Nutzungsstatistik von Smogon kürzen (ohne Netz), für „Häufige Gegner“
- `app/schaden.py`: Schadensrechnung je Generation und für Legenden: Arceus (ohne Netz); Formeln und Quellen in
  `docs/formeln.md`, Vergleichswerte in `tests/schaden_referenz.json` (erzeugt mit `tools/schaden_referenz.js`)
- `app/effort.py`: Effort Levels in Legenden: Arceus (Werte, Kosten bis zum Ziel, ohne Netz)
- `app/abruf/`: Abgleich, ein Paket mit Modulen nach Thema (`grundlage`: Pausen, Ruhezeiten, Stand, Einstellungen,
  Zeitplan, Zugriff auf eine Quelle; `medien` (Bilder, Platz), `quellen` (PKHeX, Spawnpunkte, Altissimo, Begleiter),
  `wiki`, `seiten` (Serebii, BisaFans, Bulbapedia), `karten`, `lauf` (run, Bau der Datenbank, Zeitplan im Hintergrund),
  `verbindungstest`); siehe `docs/abrufe.md`. Tests ersetzen Namen beider Pakete mit `tests.basis.im_paket`
- `app/spiele.py`: Spielprofil, was in welchem Spiel gilt (ohne Datenbank); Server und Oberfläche fragen das Profil, nicht
  die Kennung des Spiels. Felder und „ein neues Spiel“: `docs/spiele.md`
- `app/typen.py`, `app/attacken.py`, `app/team.py`: Rechenlogik ohne Datenbank (Typwirkung je Generation,
  Attacken-Wertung und Moveset, Team-Bewertung, Teamsuche, Gegner)
- `app/abfragen/`: Abfragen für die Oberfläche, ein Paket mit Modulen nach Thema (`basis`: Daten im Speicher, Spiel und
  Formen; `liste`, `lernen` (Attacken), `karten` (Fundorte, Karten, Gebiete), `fangen`, `detailseite`, `auftraege`,
  `items` (mit Typtabelle), `fortschritt`, `teams` (mit Showdown-Text), `tausch`, `eikette`, `kampf`, `raids`). Alle Namen sind unter `app.abfragen`
  erreichbar (Übersicht in `app/abfragen/__init__.py`)
- `app/server.py`: Webserver und JSON-Schnittstelle
- `app/static/`: Oberfläche (`index.html`, `style.css`, `js/*.js` in Teilen nach Reitern, Reihenfolge in `index.html`);
  siehe `docs/oberflaeche.md`
- `extra/`: gepflegte Ergänzungen als JSON (`spielwissen.json`: Spielwissen für die Detailseite, `shiny_quoten.json`: Quoten
  der Shiny-Jagd; beide liest der Server direkt)
- `app/mapgenie.py`: Karten von Map Genie lesen, eigene Punkte ausrichten und mit ihnen zu einer Datenbank zusammenführen
- `app/pkcompletion.py`, `app/ign.py`, `app/dittobase.py`: weitere Kartenquellen in derselben Form wie Map Genie
  (DittoBase: Kacheln selbst gezeichnet mit `app/png.py`, PNG lesen und schreiben ohne Abhängigkeit)
- `app/rankedboost.py`: Megakarten von RankedBoost (Ortsbilder statt Kacheln, Pokémon je Ort), ohne Netz
- `app/ironmon.py`: Weltkarten HeartGold/SoulSilver (HGSS IronMON Map, Trainer und Items), ohne Netz; Kacheln macht der Browser
- `app/raidnester.py`: Raid-Nester Schwert/Schild (PKHeX Raid Plugin, Bildkarten je Teil), ohne Netz
- `app/pokearth.py`: Regionskarten von Serebii (PokéEarth, ein Bild und ein Punkt je Ort) für die übrigen Spiele, für Kalos
  aus einer PokéWiki-Bildkarte mit großem Bild von Bulbapedia, für Alola je Insel aus den PokéWiki-Bildkarten, ohne Netz
- `app/bisafans.py`: Seiten von BisaFans lesen (Aufträge und Hauptmissionen in Legenden: Arceus, Nebenmissionen in Z-A), ohne Netz
- `app/shiny.py`: Shiny-Sperren aus Bulbapedia lesen (je Spiel „nur per Tausch“ oder „nie“), ohne Netz
- `app/serebii.py`: Seiten von Serebii lesen (Abklingzeiten in Legenden: Z-A, Pokédexe von Pokopia), ohne Netz
- `app/pokewiki.py`: Antworten der MediaWiki-API des PokéWiki zerlegen und Werte aus dem Wikitext holen, ohne Netz
- `app/altissimo.py`, `app/companion.py`: Kartensymbole von Legenden: Arceus (Altissimo: Bäume, Erz, Kisten, Rezepte;
  PLA Companion: Schnellreise und Lager), ohne Netz
- `app/paste.py` (Showdown-Textformat lesen und schreiben), `app/doppel.py` (Doppelkampf-Bewertung), `app/aufgaben.py`
  (Auftrag und Antwort zu „Zu erledigen“): ohne Datenbank
- `tests/test_all.py`: Tests ohne Netz (ein Aufruf für alles); mit `POKEAPI_DB=/pfad/pokeapi.db` auch gegen eine gebaute
  Datenbank. Was in der CI läuft und was nur lokal: `docs/tests.md`
- `tests/minidb.py`, `tests/minidb_geruest.json`: Mini-Datenbank der Tests (erfundene Welt, vom Importer gebaut; Gerüst aus
  der PokéAPI, erzeugt mit `tools/minidb_geruest.py`); neue Fälle kommen in die Welt, nicht als Zahl in den Test
- `tests/mit_daten.py`: Tests mit der Mini-Datenbank (Abfragen, Server über HTTP, Vertrag, Selbsttest im Browser);
  `tests/basis.py`: gemeinsame Grundklassen
- `tests/vertrag.py`, `tests/vertrag.json`: Form der Antworten für die Oberfläche; nach gewollter Änderung
  `python3 -m tests.vertrag`
- `tests/ui_selbsttest.html`: Selbsttest der Oberfläche (nur der Test liefert die Seite aus)
