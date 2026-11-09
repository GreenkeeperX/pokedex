# Abrufe

Alle Abrufe laufen über `app/sources.py`: ehrliche Kennung `pokedex/<Version> (privates Nachschlage-Tool)`, nur
öffentliche Ziele, Grenzen für Größe und Zeit. Der Abgleich in `app/abruf.py` hält je Server eine Pause ein
(`PAUSE`, Sprites 0,2 s) und versucht es nach einem Netzfehler einmal erneut. Antwortet eine Quelle mit 403, 429
oder einer Prüfseite, hört sie für diesen Lauf auf und ruht 24 Stunden.

## Ablauf eines Laufs

1. Sicherung von user.db (einmal am Tag, 14 bleiben).
2. **PokéAPI**: Dateiliste und letzter Commit von `data/v2/csv` über die GitHub-API. Ohne Antwort (etwa
   Ratenlimit) die feste Liste `importer.NEEDED`.
3. **Showdown**: `data/pokedex.ts` und `data/moves.ts`.
4. Hat sich nichts geändert (Commit, Prüfsumme von Showdown und `extra/`, `importer.VERSION`), bleibt die
   Datenbank. Sonst alle CSV-Dateien holen (raw.githubusercontent.com), in `pokeapi.db.neu` bauen und nach
   bestandener Selbstprüfung (Mindestzahl Arten, Attacken, Spiele, 18 Typen) austauschen. Scheitert etwas,
   bleibt die alte Datenbank.
5. **Bilder**: fehlende Sprites (96 × 96) und danach offizielle Artworks (475 × 475) je Form, je Art höchstens 1500 je Lauf. Gibt es ein Bild nicht (404), fragt der
   Abgleich 30 Tage nicht erneut.

## Zeitplan

Prüfung jede Minute, erster Blick fünf Minuten nach dem Start (ohne Datenbank sofort). Fällig nach dem
eingestellten Abstand (1 bis 30 Tage, Standard 7); nach einem Fehlschlag frühestens nach einer Stunde.

## Verbindungstest

Fragt jede Quelle einmal an und beschreibt die Antwort, in Gruppen:

- heutige Quellen: GitHub-API, eine CSV der PokéAPI, Showdown, ein Sprite,
- Items: `items.csv` und `item_flavor_text.csv` der PokéAPI, `items.ts` von Showdown, deutsche Itemnamen aus PKHeX,
- Fundorte aus den Spieldaten: Begegnungsdateien von PKHeX (GPL-3.0) für Legenden: Arceus (mit Alpha und Level
  von–bis, `abruf.pkhex_areas` liest sie), Karmesin/Purpur und Legenden: Z-A, dazu deutsche Ortsnamen, Beherrschung
  und Level-Attacken für Legenden: Arceus,
- Wikis und Datenbanken: PokéWiki (API und Beispielseiten), Bulbapedia, Serebii, Pokémon Database, Map Genie,
- Kampfdaten: Smogon-Sets (data.pkmn.cc), Smogon-Nutzungsstatistik, `learnsets.ts` von Showdown.

Speichert nichts. Wiki- und Datenbankseiten bleiben gekürzt (60 000 Zeichen) als Proben im Speicher;
`/api/diag/proben` lädt sie als JSON herunter, damit sich Leser für neue Quellen bauen lassen.

## Gegenprüfung

Beim Bau vergleicht der Importer Basiswerte, Typen und Attackenwerte mit Showdown (Tabelle `pruefung`). Jede
Abweichung steht unter Einstellungen → „Zu erledigen“; deine Wahl liegt in user.db (`entscheidung`) und bleibt
über neue Abgleiche erhalten.
