# Pokédex

Nachschlagewerk und Team-Planer für alle Pokémon und Spiele, als kleiner Dienst im Heimnetz. Python (nur
Standardbibliothek) mit SQLite, Oberfläche in reinem JavaScript, gehärteter Container. Aufbau und Betrieb nach
dem Vorbild von VR-Navigator und eShopKompass.

## Was es kann

- **Pokémon**: alle Arten mit Regional- und anderen Formen, die eigene Werte haben (Typ, Basiswerte oder
  Fähigkeiten). Filter nach Spiel (Regional-Dex, etwa Hisui für Legenden: Arceus), Typen als Bubbles (und/oder,
  ausschließen) oder „stark gegen Typ“, bis oder nur Generation, Endstufe, Legendäre, Basiswerten, nur Favoriten
  oder Gefangene, Gebiet (Legenden: Arceus); Sortierung nach Werten. Hover-Karte mit Artwork, Netzdiagramm (außen = Höchstwert aller Pokémon),
  Schwächen und Typ-Duellen; Karten lassen sich in die Team-Leiste ziehen; „Pokémon HOME“ als eigene Sammlung,
  Übertragen der Sammlung mit ⇄ (nach HOME, in ein anderes Spiel oder freilassen); Favoriten (Stern) und Gefangene (Pokéball)
  je Spiel.
- **Detailseite**: Basiswerte, Fähigkeiten, Typwirkung (mit Fähigkeiten wie Schwebe), Entwicklung mit Bedingungen,
  „Im Duell gegen Typen“ (klar im Vorteil, im Vorteil, im Nachteil; ↑ austeilen, ↓ einstecken), Fangchance je Ball
  (offen, solange nicht gefangen), Fundorte im Spiel (Legenden: Arceus aus den Spieldaten mit Stellen, Level und
  Alpha), „Mehr Details“ zum Aufklappen (Geschlecht, Wachstum, Ei-Gruppen, EV-Ausbeute, je nach Spiel),
  schillerndes Artwork und animiertes Sprite, Ruf, getragene Items, Links ins PokéWiki.
- **Attacken je Pokémon und Spiel**: Wertung mit Gründen (Stärke, Genauigkeit, Eigentyp-Bonus, passender
  Angriffswert, Aussetzen, Anlauf, Rückstoß, Vorrang), Werte des gewählten Spiels, Filter „bis Level“ und ein
  Vorschlag für vier Attacken mit Typ-Abdeckung. Eigene Auswahl mit Standard-Attacken wie im Spiel, beigebrachten
  Attacken (TM, Lehrer) und Reihenfolge per Ziehen. TM-Nummern des Spiels, Marken für Lehrer-Attacken und
  Beherrschung, bewährte Sets aus Pokémon Showdown (Random Battle) zum Übernehmen.
- **Attacken**: alle Attacken des gewählten Spiels mit Filtern und sortierbaren Spalten.
- **Team-Leiste** unten in jedem Reiter (Drag & Drop, „+“, Favoriten). Dasselbe Pokémon darf mehrfach ins Team;
  Level und vier Attacken je Platz. Gespeicherte Teams ändern sich erst mit „Speichern“ („Verwerfen“ geht zurück).
  Ein Hinweis zeigt, wenn Mitglieder nicht zum gewählten Spiel passen.
- **Team**: Bewertung nach fünf Kriterien mit einstellbaren Gewichten (Defensive, Abdeckung, Tempo, Stärke,
  Balance), offene Schwächen, Vorschläge für den nächsten Platz mit Gründen, Suche nach dem besten Team mit
  festgesetzten Plätzen und denselben Filtern wie die Liste, Verbesserungsvorschläge zu den gewählten Attacken,
  Gegner-Modus auch gegen ein ganzes Gegner-Team (Vorteil, Nachteil), Empfehlungen aus den Gefangenen (bessere
  Alternative, langfristig mehr Potential) und Teamsuche nur aus Gefangenen.
- **Items** des Spiels mit Bild, Tasche, Art, Beschreibung (deutsch, wo vorhanden) und Preis; je Tasche passende
  Spalten (Wirkung bei Medizin und Bällen, die Attacke bei Maschinen), Suche und Filter nach Art. Spiele ohne Liste in
  der PokéAPI (Legenden: Arceus, Karmesin/Purpur, Legenden: Z-A, SDLP) nach PKHeX; in Legenden: Arceus „Herstellen“
  mit Rezepten und Zutaten.
- **Typtabelle** der Generation des Spiels; Zeile und Spalte lassen sich festhalten.
- **Attacken-Liste** mit Kurz-Info zur Wirkung von Status-Attacken (etwa „Angriff −1 (Gegner)“).
- **Karte** (Legenden: Arceus): Jubeldorf und die fünf Gebiete zum Ziehen und Zoomen; Spawnpunkte (Alpha hervorgehoben,
  wer dort wann erscheint), Bäume, Erzbrocken, Haufen, Kisten, Irrlichter, Icognito, alte Verse und Grabstellen als
  Ebenen zum Ein- und Ausblenden; von der Detailseite aus mit den Spawnpunkten des Pokémon.
- **Einstellungen**: Abgleich mit Protokoll, Zeitplan, Verbindungstest (auch für mögliche neue Quellen, mit Probe-Seiten
  zum Herunterladen), „Zu erledigen“ (Abweichungen zwischen
  PokéAPI und Showdown zum Entscheiden), Kopieren und Herunterladen von Protokoll und Test, Sicherung der eigenen
  Daten zum Herunterladen und Einlesen. „Zu erledigen“ lässt sich als Auftrag für einen KI-Chat kopieren, die Antwort
  mit Vorschau einlesen. Die Spieldaten (Datenbank, Protokoll, Übersicht fehlender Bilder) gibt es als ZIP.

## Quellen

| Quelle | Rolle | Lizenz |
|---|---|---|
| [PokéAPI](https://github.com/PokeAPI/pokeapi) (CSV) | Primärquelle: alle Grunddaten, alle Spiele, deutsche Namen | BSD-3 |
| [Pokémon Showdown](https://github.com/smogon/pokemon-showdown) | Gegenprüfung von Werten und Attacken, Merkmale wie „Aufladen“ | MIT |
| [PokéAPI-Sprites](https://github.com/PokeAPI/sprites) | Bilder (Sprites und offizielle Artworks) | siehe dort |
| [PKHeX](https://github.com/kwsch/PKHeX) | Fundorte aus den Spieldaten (Legenden: Arceus: Gebiet, Stellen, Level, Alpha, feste Begegnungen); Item-Listen und Itemnamen je Spiel | GPL-3.0 |
| [Altissimo](https://github.com/Altissimo1/altissimo1.github.io) | Legenden: Arceus: Kartensymbole, Irrlichter, Icognito, alte Verse, Grabstellen, Kartenbild Jubeldorf, Rezepte | GPL-3.0 (Kartenbild nur im Datenordner) |
| [PLA-Live-Map](https://github.com/Lincoln-LM/PLA-Live-Map), [JS-Finder](https://github.com/Lincoln-LM/JS-Finder) | Spawnpunkte mit Koordinaten, Tageszeit und Wetter (Legenden: Arceus) | GPL-3.0 |
| [Serebii](https://www.serebii.net) | Kartenbilder (Kacheln, nur im Datenordner auf dem Server) | Bilder von Serebii, Spielgrafik von Nintendo |
| [PokéWiki](https://www.pokewiki.de) | Links; Attackenwerte in Legenden: Arceus (Kraft- und Tempostil), getragene Items; geplant: Edelhorden | CC BY-SA 3.0 DE |

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
