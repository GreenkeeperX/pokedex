# Abrufe

Alle Abrufe laufen über `app/sources.py`: ehrliche Kennung `pokedex/<Version> (privates Nachschlage-Tool)`, nur
öffentliche Ziele, Grenzen für Größe und Zeit. Der Abgleich in `app/abruf.py` hält je Server eine Pause ein
(`PAUSE`, Sprites 0,2 s) und versucht es nach einem Netzfehler einmal erneut. Antwortet eine Quelle mit 403, 429
oder einer Prüfseite, hört sie für diesen Lauf auf und ruht 24 Stunden.

## Ablauf eines Laufs

1. Sicherung von user.db (einmal am Tag, 14 bleiben).
2. **PokéAPI**: Dateiliste und letzter Commit von `data/v2/csv` über die GitHub-API. Ohne Antwort (etwa
   Ratenlimit) die feste Liste `importer.NEEDED`.
3. **Showdown**: `data/pokedex.ts` und `data/moves.ts`, dazu die Random-Battle-Sets je Generation
   (`abruf.sets_url`, Generation 1 nur `data.json`) für die bewährten Sets (Tabelle `moveset`).
   **PKHeX**: Begegnungsdatei und deutsche Ortsnamen je Spiel in `abruf.PKHEX_GAMES` (bisher Legenden: Arceus).
   `importer.pkhex_areas` liest sie: je Gebiet die Ortsnummern (die erste ist das Gebiet, die übrigen die Stellen),
   die Art (frei, Raum-Zeit-Verzerrung, Baum oder Erzbrocken, Massenauftreten) und Plätze mit Art, Form, Level und
   Alpha. Die Formnummer im Spiel wird über `pokemon_forms.form_order` zur Form der PokéAPI (Tabelle `fundort`).
   Dazu die festen Begegnungen aus der Quelldatei (`Encounters8a.cs`, `importer.pkhex_static`).
   **Spawnpunkte** (Legenden: Arceus): Koordinaten je Karte von JS-Finder, die Tabellen je Punkt nach Tageszeit und
   Wetter von PLA-Live-Map (`abruf.PLA_MAPS`); `importer._derive_spawn` rechnet Gewichte in Anteile je Bedingung um.
   **PokéWiki**: je Spiel in `abruf.WIKI_GAMES` die Seiten der Attacken, die dort jemand lernt (nur die Infobox,
   `rvsection=0`), und der Arten im Spiel, gebündelt zu 50 Seiten je Anfrage mit 2 Sekunden Pause. `app/pokewiki.py`
   liest Attackenwerte (Legenden: Arceus mit Kraft- und Tempostil) und getragene Items; das Ergebnis liegt in
   `pokewiki.json` im Datenordner und gilt weiter, wenn das Wiki ruht. Die Namen stammen aus der bisherigen Datenbank.
4. Hat sich nichts geändert (Commit, Prüfsumme von Showdown, PKHeX, PokéWiki und `extra/`, `importer.VERSION`), bleibt die
   Datenbank. Sonst alle CSV-Dateien holen (raw.githubusercontent.com; bei unverändertem Commit aus
   `pokeapi-csv.json.gz` im Datenordner), in `pokeapi.db.neu` bauen und nach
   bestandener Selbstprüfung (Mindestzahl Arten, Attacken, Spiele, 18 Typen) austauschen. Scheitert etwas,
   bleibt die alte Datenbank.
5. **Bilder**: fehlende Sprites (96 × 96) und danach offizielle Artworks (475 × 475) je Form, je Art höchstens 1500 je Lauf. Gibt es ein Bild nicht (404), fragt der
   Abgleich 30 Tage nicht erneut. Danach die Extras (`abruf.EXTRAS`, Quelle „extras“): schillernde Sprites nach
   `shiny/`, animierte (Showdown-Stil, GIF) nach `anim/`, Rufe nach `rufe/`. Die Endung richtet sich nach dem Inhalt
   (`abruf.file_kind`): Die Rufe der PokéAPI heißen `.ogg`, sind aber MP3.
6. **Kartenkacheln** (Legenden: Arceus): fehlende Kacheln von Serebii (`abruf.MAP_TILES`, 5 Karten × 84 Kacheln) nach
   `karten/<Karte>/<z>-<x>-<y>.png`, eine Sekunde Pause je Kachel; fehlende (404) 30 Tage nicht erneut.

## Item-Bilder

Extra `itembild`: `sprites/items/<Kennung>.png` aus dem Sprite-Repository der PokéAPI, gespeichert als
`itembild/<Nummer>.png`. Ohne Maschinen und unfertige Einträge; was es nicht gibt (404), wird 30 Tage nicht erneut gefragt.

## Zeitplan

Prüfung jede Minute, erster Blick fünf Minuten nach dem Start (ohne Datenbank sofort). Passt `importer.VERSION`
nicht mehr zum gebauten Stand (nach einem Update mit neuen Tabellen), ist der Abgleich sofort fällig. Fällig nach dem
eingestellten Abstand (1 bis 30 Tage, Standard 7); nach einem Fehlschlag frühestens nach einer Stunde.

## Verbindungstest

Fragt jede Quelle einmal an und beschreibt die Antwort, in Gruppen:

- heutige Quellen: GitHub-API, eine CSV der PokéAPI, Showdown, ein Sprite,
- Items: `items.csv` und `item_flavor_text.csv` der PokéAPI, `items.ts` von Showdown, deutsche Itemnamen aus PKHeX,
- Fundorte aus den Spieldaten: Begegnungsdateien von PKHeX (GPL-3.0) für Legenden: Arceus (mit Alpha und Level
  von–bis, `abruf.pkhex_areas` liest sie), Karmesin/Purpur und Legenden: Z-A, dazu deutsche Ortsnamen, Beherrschung
  und Level-Attacken für Legenden: Arceus,
- Wikis und Datenbanken: PokéWiki (API und Beispielseiten), Bulbapedia, Serebii, Pokémon Database, Map Genie,
- weitere Spieldaten: feste Begegnungen aus den Quelldateien von PKHeX (`importer.pkhex_static`), Raids in
  Karmesin/Purpur, Werte je Form in Legenden: Arceus,
- Bilder und Rufe: schillernde und animierte Sprites, Rufe (PokéAPI-Repos),
- schon geladen, noch ungenutzt: TM, Wesen, Ei-Gruppen, Fangraten, Beeren und EV-Ausbeute in pokeapi.db,
- Kampfdaten: Smogon-Sets (data.pkmn.cc), Smogon-Nutzungsstatistik, `learnsets.ts`, `formats-data.ts`,
  Random-Battle-Sets und `abilities.ts` von Showdown.

Speichert nichts. Wiki- und Datenbankseiten bleiben gekürzt (60 000 Zeichen) als Proben im Speicher;
`/api/diag/proben` lädt sie als JSON herunter, damit sich Leser für neue Quellen bauen lassen.

## Gegenprüfung

Beim Bau vergleicht der Importer Basiswerte, Typen und Attackenwerte mit Showdown (Tabelle `pruefung`). Jede
Abweichung steht unter Einstellungen → „Zu erledigen“; deine Wahl liegt in user.db (`entscheidung`) und bleibt
über neue Abgleiche erhalten.
