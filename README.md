# Pokédex

Elektronisches Nachschlagewerk und Team-Planer für alle Pokémon (inkl. Formen): Typ-Matrix, Teamoptimierung, beste Attacken je Spiel, beste Typ-Attacken. Daten aus der PokéAPI (Browser-Cache).

## Betrieb auf hq
1. Push auf `main` baut per GitHub Actions das Image `ghcr.io/greenkeeperx/pokedex:latest`.
2. Paket unter Packages einmalig auf "public" stellen.
3. In Portainer Container aus dem Image starten, Port 80 auf freien Host-Port (z. B. 8788) legen, Watchtower wie beim eshop-kompass.
