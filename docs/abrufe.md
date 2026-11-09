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

Fragt jede Quelle einmal an (GitHub-API, eine CSV, Showdown, ein Sprite, PokéWiki-API und eine PokéWiki-Seite) und
beschreibt die Antwort. Speichert nichts.

## Gegenprüfung

Beim Bau vergleicht der Importer Basiswerte, Typen und Attackenwerte mit Showdown (Tabelle `pruefung`). Jede
Abweichung steht unter Einstellungen → „Zu erledigen“; deine Wahl liegt in user.db (`entscheidung`) und bleibt
über neue Abgleiche erhalten.
