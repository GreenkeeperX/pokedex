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
- jede Version mit Tests (`python3 -m unittest tests.test_all`), neuer Nummer in `app/sources.py`,
  aktueller README und ROADMAP.md,
- user.db lädt nach jedem Update weiter: nur neue Tabellen und Spalten, nie löschen (`app/db.py`),
- ändern sich die aufbereiteten Tabellen in `app/importer.py`, `importer.VERSION` erhöhen; dann baut der nächste Abgleich neu.

## Aufbau

- `app/sources.py`: Netzabruf (`request`, `fetch`, nur öffentliche Ziele), `VERSION`
- `app/store.py`: kleine JSON-Dateien im Datenordner (`settings.json`, `sync.json`)
- `app/db.py`: pokeapi.db (Spieldaten, nur lesend) und user.db (Teams, Entscheidungen), tägliche Sicherung
- `app/importer.py`: baut pokeapi.db aus den CSV-Texten der PokéAPI, Showdown und `extra/` (ohne Netz), Selbstprüfung
- `app/showdown.py`: liest `pokedex.ts` und `moves.ts` von Pokémon Showdown (ohne Netz)
- `app/abruf.py`: Abgleich (holen, bauen, Sprites), Zeitplan, Einstellungen, Verbindungstest; siehe `docs/abrufe.md`
- `app/typen.py`, `app/attacken.py`, `app/team.py`: Rechenlogik ohne Datenbank (Typwirkung je Generation,
  Attacken-Wertung und Moveset, Team-Bewertung, Teamsuche, Gegner)
- `app/abfragen.py`: Abfragen für die Oberfläche (Liste, Detailseite, Attacken, Typtabelle, Teams)
- `app/server.py`: Webserver und JSON-Schnittstelle
- `app/static/`: Oberfläche (`index.html`, `style.css`, `js/app.js`); siehe `docs/oberflaeche.md`
- `extra/`: gepflegte Ergänzungen als JSON
- `tests/test_all.py`: Tests ohne Netz; mit `POKEAPI_DB=/pfad/pokeapi.db` auch gegen eine gebaute Datenbank
