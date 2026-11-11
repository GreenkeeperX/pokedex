# Abrufe

Alle Abrufe laufen über `app/sources.py`: ehrliche Kennung `pokedex/<Version> (privates Nachschlage-Tool)`, nur
öffentliche Ziele, Grenzen für Größe und Zeit. Der Abgleich in `app/abruf.py` hält je Server eine Pause ein
(`PAUSE`, Sprites 0,2 s) und versucht es nach einem Netzfehler einmal erneut. Die Pause gilt je Server für alle Quellen
zusammen (`_HOST_LAST`, eine Sperre je Server): Quellen ohne Abhängigkeit laufen gleichzeitig (`_parallel`), Abrufe am
selben Server aber nie. Antwortet eine Quelle mit 403, 429
oder einer Prüfseite, hört sie für diesen Lauf auf und ruht 24 Stunden.

## Ablauf eines Laufs

1. Sicherung von user.db (einmal am Tag, 14 bleiben).
2. **PokéAPI**: Dateiliste und letzter Commit von `data/v2/csv` über die GitHub-API. Ohne Antwort (etwa
   Ratenlimit) die feste Liste `importer.NEEDED`.
3. **Showdown**: `data/pokedex.ts` und `data/moves.ts`, dazu die Random-Battle-Sets je Generation
   (`abruf.sets_url`, Generation 1 nur `data.json`) für die bewährten Sets (Tabelle `moveset`).
   **PKHeX**: Begegnungsdatei, deutsche Ortsnamen (dazu die Liste ab 30000 für Geschenke) und feste Begegnungen je
   Spiel in `abruf.PKHEX_GAMES`: Legenden: Arceus, Karmesin/Purpur, Legenden: Z-A und Mega-Dimension (Hyperspace).
   `importer.pkhex_areas` erkennt das Format an der Kennung („la“, „sv“, „za“; bei „za“ BinLinker16 mit 16-Bit-Offsets).
   Karmesin/Purpur: Gebiete mit Herkunft (Pokémon aus dem Nachbargebiet) sind Doppel und fallen weg. Erweiterungen
   bekommen die Fundorte ihres Hauptspiels dazu (`importer.PKHEX_SHARE`). In Legenden: Arceus liest es je Gebiet die
   Ortsnummern (die erste ist das Gebiet, die übrigen die Stellen),
   die Art (frei, Raum-Zeit-Verzerrung, Baum oder Erzbrocken, Massenauftreten) und Plätze mit Art, Form, Level und
   Alpha. Die Formnummer im Spiel wird über `pokemon_forms.form_order` zur Form der PokéAPI (Tabelle `fundort`).
   Dazu die festen Begegnungen aus der Quelldatei (`Encounters8a.cs`, `importer.pkhex_static`). Strahlender Diamant und
   Leuchtende Perle haben je eine Datei (`encounter_bd.pkl`, `encounter_sp.pkl`); beide zusammen ergeben die Fundorte.
   **Spawnpunkte** (Legenden: Arceus): Koordinaten je Karte von JS-Finder, die Tabellen je Punkt nach Tageszeit und
   Wetter von PLA-Live-Map (`abruf.PLA_MAPS`); `importer._derive_spawn` rechnet Gewichte in Anteile je Bedingung um.
   **Altissimo** (Legenden: Arceus, `app/altissimo.py`): je Gebiet Bäume, Erzbrocken, Haufen und Kisten
   (`Landmarks/json/<Gebiet>-spawns.json`) und Sammelobjekte (`Collectibles/json/<Gebiet>.json`, auch Jubeldorf), dazu
   `recipes.html` und einmal das Kartenbild von Jubeldorf (`karten/jubilifevillage/bild.png` im Datenordner). Die Lage
   steht in Prozent des Kartenbilds; `altissimo.FIT` rechnet sie in Spielkoordinaten um (Geraden aus den Bäumen und
   Erzbrocken, die auch JS-Finder hat). **PKHeX** liefert außerdem die Itemnamen (deutsch, englisch) und die Itemlisten
   je Spiel (`ItemStorage<Kürzel>.cs`, `importer.ITEM_LISTS`) für Spiele ohne Liste in der PokéAPI, dazu die Lernlisten
   von Legenden: Z-A (`byte/levelup/lvlmove_za.pkl`, `byte/personal/personal_za`; `importer.PKHEX_LEARN`), solange die
   PokéAPI dort keine hat.
   **PokéWiki**: je Spiel in `abruf.WIKI_GAMES` die Seiten der Attacken, die dort jemand lernt (nur die Infobox,
   `rvsection=0`), und der Arten im Spiel, gebündelt zu 50 Seiten je Anfrage mit 2 Sekunden Pause. `app/pokewiki.py`
   liest Attackenwerte (Legenden: Arceus mit Kraft- und Tempostil) und getragene Items, dazu je Gebiet die Kartendateien
   `extensions/PwMapHisui/data/{pokemon,items}/ha_area01…05.json` (`pokewiki.map_pokemon`, `pokewiki.map_items`; gleiche
   Spielkoordinaten wie JS-Finder). `importer._derive_wiki_karte` ordnet jede Datei der Karte zu, deren Spawnpunkte sie am
   häufigsten genau trifft, und legt Kristallbrocken, Verzerrungen, Massenauftreten, Bäume, feste Alphas und Items am Boden
   in `kartenobjekt` (ohne Stellen, die Altissimo schon führt; viele Items an einer Stelle gehen an die nächste Grabstelle).
   **PLA Companion** (software-notion.de, `app/companion.py`): je Karte `/apps/pla-companion/map/<Karte>/data?lang=de`
   mit 2 Sekunden Pause; Schnellreise und Lager, ausgerichtet an Geisterlichtern und Icognito von Altissimo
   (`companion.fit`, `importer._derive_companion`). Das Protokoll zählt alle Arten von Einträgen.
   Das Ergebnis liegt in
   `pokewiki.json` im Datenordner und gilt weiter, wenn das Wiki ruht. Die Namen stammen aus der bisherigen Datenbank.
4. Hat sich nichts geändert (Commit, Prüfsumme von Showdown, PKHeX, PokéWiki, Altissimo und `extra/`, `importer.VERSION`), bleibt die
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
7. **Map Genie** (`app/mapgenie.py`, Quelle „mapgenie“): je Spiel in `mapgenie.GAMES` die Spielseite, daraus die Karten
   (`/<Spiel>/maps/<Karte>`), je Karte die Seite (`window.mapData`) und `/api/v1/maps/<Nummer>/data`, 3 Sekunden Pause.
   Ergebnis kompakt in `mapgenie/<Spiel>.json` im Datenordner; Spiele, die es dort nicht gibt, melden 404 und fallen weg.
   Die Kacheln holt erst die Oberfläche über `/mgkachel/…` (`abruf.mg_tile`): eine Anfrage zur Zeit, 0,3 Sekunden
   Pause, abgelegt unter `mapgenie/kacheln/`; bei 403 oder 429 ruht das 24 Stunden.

## Item-Bilder

Extra `itembild`: `sprites/items/<Kennung>.png` aus dem Sprite-Repository der PokéAPI, gespeichert als
`itembild/<Nummer>.png`. Ohne Maschinen und unfertige Einträge; was es nicht gibt (404), wird 30 Tage nicht erneut gefragt.
Items, die nur PKHeX kennt, haben dort kein Bild.

Extra `itemhq`: größere Bilder von Serebii (`itemdex/sprites/legends/<name>.png` für Legenden: Arceus, sonst
`itemdex/sprites/sv/<name>.png` für Karmesin/Purpur, Legenden: Z-A und Mega-Dimension; Name = englischer Name klein ohne
Zeichen, `importer.en_key`, und wie bei Serebii mit Bindestrich und Apostroph, `serebii_key`), gespeichert als `itemhq/<Nummer>.png`, eine Sekunde Pause, höchstens 1500 je Lauf. Fehlt es
im Ordner des Spiels, versucht der Abgleich den anderen Ordner und dann das kleine Bild (`itemdex/sprites/<name>.png`);
dazu kommen die Items, die nur PKHeX kennt. Fehlende stehen in `itemhq3_fehlen.json`. Läuft als eigene Quelle `itemhq` neben den anderen Bildern. `/itembild/<Nummer>` liefert zuerst
das große Bild.

Extra `formen`: Formen nur zum Ansehen (gleiche Werte, eigenes Aussehen) aus `sprites/pokemon/<Art>-<Form>.png`,
gespeichert als `formen/<Nummer aus pokemon_forms>.png`.

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
- mögliche Quellen zum Testen: Item-Bilder (Serebii, PokéWiki), Kartenseiten von Serebii, GamerGuides (Lager,
  Schnellreise) und Pokébip (Stichwörter und Skripte, als Probe bis 400 000 Zeichen),
- weitere Spieldaten: feste Begegnungen aus den Quelldateien von PKHeX (`importer.pkhex_static`), Raids in
  Karmesin/Purpur, Werte je Form in Legenden: Arceus,
- Bilder und Rufe: schillernde und animierte Sprites, Rufe (PokéAPI-Repos),
- schon geladen, noch ungenutzt: TM, Wesen, Ei-Gruppen, Fangraten, Beeren und EV-Ausbeute in pokeapi.db,
- Kampfdaten: Smogon-Sets (data.pkmn.cc), Smogon-Nutzungsstatistik, `learnsets.ts`, `formats-data.ts`,
  Random-Battle-Sets und `abilities.ts` von Showdown.

Speichert nichts. Wiki- und Datenbankseiten bleiben gekürzt (60 000 Zeichen) als Proben im Speicher;
`/api/diag/proben` lädt sie als JSON herunter, damit sich Leser für neue Quellen bauen lassen.

Seiten, die ihre Daten erst im Browser per Skript laden (Karten im PokéWiki), sieht der Server nur als Hülle. Dafür
gibt es in den Einstellungen das Lesezeichen „Seite untersuchen“ (`probeHelper` in `app.js`, wie im VR-Navigator):
es läuft auf der fremden Seite, holt die nachgeladenen Daten-Dateien (`performance`-Einträge vom Typ fetch/xhr und
`.json`, höchstens 40 und 6 MB) samt Inhalt, Daten in globalen Variablen, Kartenmarker, Skripte und das HTML und
speichert alles als `pokedex-probe-<Seite>.json`. Benutzername und Schlüssel der Seite werden entfernt.

## Gegenprüfung

Beim Bau vergleicht der Importer Basiswerte, Typen und Attackenwerte mit Showdown (Tabelle `pruefung`). Jede
Abweichung steht unter Einstellungen → „Zu erledigen“; deine Wahl liegt in user.db (`entscheidung`) und bleibt
über neue Abgleiche erhalten.
