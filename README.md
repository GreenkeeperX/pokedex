# Pokédex

Elektronisches Nachschlagewerk und Team-Planer für alle Pokémon (inkl. Formen): Typ-Matrix, Teamoptimierung, beste Attacken je Spiel, beste Typ-Attacken.

Alle Daten (PokéAPI) und Sprites werden beim Docker-Build einmalig geholt und ins Image gebacken. Im Browser läuft danach nichts mehr über fremde Server, das Tool funktioniert also auch ohne Internet.

## Aufbau
- `index.html`: die komplette App (Vanilla-JS, kein Build-Schritt)
- `scripts/build-data.mjs`: lädt die PokéAPI-CSVs und schreibt `data/core.json` (Typen, Pokémon, Attacken, Editionen) und `data/learn/<id>.json` (erlernbare Attacken je Edition)
- `Dockerfile`: Stufe 1 baut Daten und holt die Sprites, Stufe 2 liefert alles per nginx aus
- `docker-compose.yml`: Stack für Portainer

## Lokal starten
```sh
node scripts/build-data.mjs data          # Node 18+
# Sprites optional: ohne Ordner sprites/ bleiben die Bilder leer
python3 -m http.server 8000
```
Oder komplett per Docker: `docker build -t pokedex . && docker run -p 8788:80 pokedex`

## Betrieb auf hq
1. Push auf `main` baut per GitHub Actions das Image `ghcr.io/greenkeeperx/pokedex:latest` (amd64). Montags baut die Action automatisch neu, damit neue PokéAPI-Daten ankommen.
2. In Portainer: Stacks → Add stack → Inhalt von `docker-compose.yml` einfügen → Deploy. Erreichbar unter `http://hq:8788`.
3. Watchtower holt neue Images automatisch (Label `com.centurylinklabs.watchtower.enable=true` ist gesetzt).
