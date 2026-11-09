# Pokédex

Nachschlagewerk und Team-Planer für alle Pokémon und Spiele, als kleiner Dienst im Heimnetz. Python (nur
Standardbibliothek) mit SQLite, Oberfläche in reinem JavaScript, gehärteter Container. Aufbau und Betrieb nach
dem Vorbild von VR-Navigator und eShopKompass.

## Was es kann

- **Pokémon**: alle Arten mit Regional- und anderen Formen, die eigene Werte haben (Typ, Basiswerte oder
  Fähigkeiten). Filter nach Spiel (Regional-Dex, etwa Hisui für Legenden: Arceus), Typen als Bubbles (und/oder,
  ausschließen) oder „stark gegen Typ“, bis oder nur Generation, Endstufe, Legendäre, Basiswerten, nur Favoriten
  oder Gefangene; Sortierung nach Werten. Hover-Karte mit Artwork, Netzdiagramm (außen = Höchstwert aller Pokémon),
  Schwächen und Typ-Duellen; Karten lassen sich in die Team-Leiste ziehen; Favoriten (Stern) und Gefangene (Pokéball)
  je Spiel.
- **Detailseite**: Basiswerte, Fähigkeiten, Typwirkung (mit Fähigkeiten wie Schwebe), Entwicklung mit Bedingungen,
  „Im Duell gegen Typen“ (klar stark, stark, schwer), Fundorte im Spiel, Links ins PokéWiki.
- **Attacken je Pokémon und Spiel**: Wertung mit Gründen (Stärke, Genauigkeit, Eigentyp-Bonus, passender
  Angriffswert, Aussetzen, Anlauf, Rückstoß, Vorrang), Werte des gewählten Spiels, Filter „bis Level“ und ein
  Vorschlag für vier Attacken mit Typ-Abdeckung. Eigene Auswahl mit Standard-Attacken wie im Spiel, beigebrachten
  Attacken (TM, Lehrer) und Reihenfolge per Ziehen.
- **Attacken**: alle Attacken des gewählten Spiels mit Filtern und sortierbaren Spalten.
- **Team-Leiste** unten in jedem Reiter (Drag & Drop, „+“, Favoriten). Dasselbe Pokémon darf mehrfach ins Team;
  Level und vier Attacken je Platz. Gespeicherte Teams ändern sich erst mit „Speichern“ („Verwerfen“ geht zurück).
  Ein Hinweis zeigt, wenn Mitglieder nicht zum gewählten Spiel passen.
- **Team**: Bewertung nach fünf Kriterien mit einstellbaren Gewichten (Defensive, Abdeckung, Tempo, Stärke,
  Balance), offene Schwächen, Vorschläge für den nächsten Platz mit Gründen, Suche nach dem besten Team mit
  festgesetzten Plätzen und denselben Filtern wie die Liste, Verbesserungsvorschläge zu den gewählten Attacken,
  Gegner-Modus auch gegen ein ganzes Gegner-Team (Vorteil, Nachteil), Empfehlungen aus den Gefangenen (bessere
  Alternative, langfristig mehr Potential) und Teamsuche nur aus Gefangenen.
- **Typtabelle** der Generation des Spiels; Zeile und Spalte lassen sich festhalten.
- **Einstellungen**: Abgleich mit Protokoll, Zeitplan, Verbindungstest (auch für mögliche neue Quellen, mit Probe-Seiten
  zum Herunterladen), „Zu erledigen“ (Abweichungen zwischen
  PokéAPI und Showdown zum Entscheiden), Kopieren und Herunterladen von Protokoll und Test, Sicherung der eigenen
  Daten zum Herunterladen und Einlesen.

## Quellen

| Quelle | Rolle | Lizenz |
|---|---|---|
| [PokéAPI](https://github.com/PokeAPI/pokeapi) (CSV) | Primärquelle: alle Grunddaten, alle Spiele, deutsche Namen | BSD-3 |
| [Pokémon Showdown](https://github.com/smogon/pokemon-showdown) | Gegenprüfung von Werten und Attacken, Merkmale wie „Aufladen“ | MIT |
| [PokéAPI-Sprites](https://github.com/PokeAPI/sprites) | Bilder (Sprites und offizielle Artworks) | siehe dort |
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
- `user.db`: deine Teams, Favoriten, Gefangenen und Entscheidungen; der Abgleich berührt sie nie. Tägliche Kopie in `sicherung/` (14 Tage)
- `sprites/`, `artwork/`: Bilder (Sprites 96 × 96, offizielle Artworks 475 × 475, zusammen gut 180 MB)
- `settings.json`, `sync.json`: Einstellungen und Stand des Abgleichs

## Entwicklung

    python3 -m unittest tests.test_all
    DATA_DIR=./data python3 -m app.server      # http://localhost:8789, holt beim Start die Daten

Mit einer gebauten Datenbank laufen zusätzliche Tests: `POKEAPI_DB=./data/pokeapi.db python3 -m unittest tests.test_all`.
Hinweise zum Arbeiten am Repository: `CLAUDE.md`. Geplantes: `ROADMAP.md`.
