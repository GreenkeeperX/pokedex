# Pokédex

Nachschlagewerk und Team-Planer für alle Pokémon und Spiele, als kleiner Dienst im Heimnetz. Python (nur
Standardbibliothek) mit SQLite, Oberfläche in reinem JavaScript, gehärteter Container. Aufbau und Betrieb nach
dem Vorbild von VR-Navigator und eShopKompass.

## Was es kann

- **Pokémon**: alle Arten mit Regional- und anderen Formen, die eigene Werte haben (Typ, Basiswerte oder
  Fähigkeiten). Filter nach Spiel (Regional-Dex, etwa Hisui für Legenden: Arceus), Typ, Generation, Endstufe,
  Legendäre, Basiswerten; Sortierung nach Werten.
- **Detailseite**: Basiswerte, Fähigkeiten, Typwirkung (mit Fähigkeiten wie Schwebe), Entwicklung mit Bedingungen,
  Fundorte im Spiel, Link ins PokéWiki.
- **Attacken je Pokémon und Spiel**: Wertung mit Gründen (Stärke, Genauigkeit, Eigentyp-Bonus, passender
  Angriffswert, Aussetzen, Anlauf, Rückstoß, Vorrang), Werte des gewählten Spiels, Filter „bis Level“ und ein
  Vorschlag für vier Attacken mit Typ-Abdeckung.
- **Beste Attacken je Typ** im gewählten Spiel.
- **Team**: Bewertung nach fünf Kriterien mit einstellbaren Gewichten (Defensive, Abdeckung, Tempo, Stärke,
  Balance), offene Schwächen, Vorschläge für den nächsten Platz mit Gründen, Suche nach dem besten Team mit
  festgesetzten Plätzen, Gegner-Modus (wen schicken, wen schonen). Teams lassen sich speichern.
- **Typtabelle** der Generation des Spiels.
- **Einstellungen**: Abgleich mit Protokoll, Zeitplan, Verbindungstest, „Zu erledigen“ (Abweichungen zwischen
  PokéAPI und Showdown zum Entscheiden).

## Quellen

| Quelle | Rolle | Lizenz |
|---|---|---|
| [PokéAPI](https://github.com/PokeAPI/pokeapi) (CSV) | Primärquelle: alle Grunddaten, alle Spiele, deutsche Namen | BSD-3 |
| [Pokémon Showdown](https://github.com/smogon/pokemon-showdown) | Gegenprüfung von Werten und Attacken, Merkmale wie „Aufladen“ | MIT |
| [PokéAPI-Sprites](https://github.com/PokeAPI/sprites) | Bilder | siehe dort |
| [PokéWiki](https://www.pokewiki.de) | Links; geplant: Legenden: Arceus (Fundorte, Elite-Pokémon, Edelhorden, Karten) | CC BY-SA 3.0 DE |

Pokémon und alle Namen sind Marken von Nintendo, Creatures und GAME FREAK. Dies ist ein privates Nachschlage-Tool.

## Betrieb auf dem Heimserver

1. Ein Push auf `main` baut per GitHub Actions das Image `ghcr.io/greenkeeperx/pokedex` (Tags `latest`, Version, Commit).
   Das Paket unter *Packages* einmalig auf „public“ stellen oder Portainer Zugang zu GHCR geben.
2. In Portainer einen Stack mit dem Inhalt von `docker-compose.yml` anlegen. Port 8789, Volume `pokedex-daten`,
   Watchtower holt neue Images selbst.
3. Beim ersten Start holt der Container die Daten (einige Minuten, danach die Sprites). Danach gleicht er
   nach Zeitplan ab (Standard: alle 7 Tage), fünf Minuten nach jedem Neustart prüft er, ob ein Lauf fällig ist.

Aufruf über IP-Adresse oder Namen im eigenen Netz. Für eine Domain `ALLOWED_HOSTS` setzen (siehe Compose-Datei).

### Datenordner (`/data`)

- `pokeapi.db`: Spieldaten, baut jeder Abgleich neu, wenn sich eine Quelle geändert hat
- `user.db`: deine Teams und Entscheidungen; der Abgleich berührt sie nie. Tägliche Kopie in `sicherung/` (14 Tage)
- `sprites/`: Bilder
- `settings.json`, `sync.json`: Einstellungen und Stand des Abgleichs

## Entwicklung

    python3 -m unittest tests.test_all
    DATA_DIR=./data python3 -m app.server      # http://localhost:8789, holt beim Start die Daten

Mit einer gebauten Datenbank laufen zusätzliche Tests: `POKEAPI_DB=./data/pokeapi.db python3 -m unittest tests.test_all`.
Hinweise zum Arbeiten am Repository: `CLAUDE.md`. Geplantes: `ROADMAP.md`.
