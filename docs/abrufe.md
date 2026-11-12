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
   PokéAPI dort keine hat. Seit 0.22.0 auch die Tera-Raids von Karmesin/Purpur (`legality/wild/Gen9/encounter_<Datei>.pkl`,
   `importer.PKHEX_RAIDS`: Sätze zu 0x18 bzw. 0x3E Bytes mit Art, Form, Level, Sternen, Tera-Typ und Attacken; Tabelle `raid`)
   und die Crypto-Pokémon aus `Gen3/Encounters3Colo.cs` und `Encounters3XD.cs` (Liste `Shadow`, `importer.pkhex_shadow`;
   Trainer und Ort aus dem Kommentar, englisch; Tabelle `crypto`).
   **PokéWiki**: je Spiel in `abruf.WIKI_GAMES` die Seiten der Attacken, die dort jemand lernt (nur die Infobox,
   `rvsection=0`), und der Arten im Spiel, gebündelt zu 50 Seiten je Anfrage mit 2 Sekunden Pause. `app/pokewiki.py`
   liest Attackenwerte (Legenden: Arceus mit Kraft- und Tempostil) und getragene Items, dazu je Gebiet die Kartendateien
   `extensions/PwMapHisui/data/{pokemon,items}/ha_area01…05.json` (`pokewiki.map_pokemon`, `pokewiki.map_items`; gleiche
   Spielkoordinaten wie JS-Finder). `importer._derive_wiki_karte` ordnet jede Datei der Karte zu, deren Spawnpunkte sie am
   häufigsten genau trifft, und legt Kristallbrocken, Verzerrungen, Massenauftreten, Bäume, feste Alphas und Items am Boden
   in `kartenobjekt` (ohne Stellen, die Altissimo schon führt; viele Items an einer Stelle gehen an die nächste Grabstelle).
   Dazu deutsche Texte je Spiel (`abruf._wiki_texts`): die Seiten aller Arten, Attacken und Fähigkeiten (ganze Seiten,
   20 je Anfrage), alle 30 Tage komplett, sonst nur neue Namen; was in einer Antwort fehlt, kommt in einer zweiten
   Runde, Attacken und Fähigkeiten ohne Text noch einmal als „Name (Attacke)“ bzw. „Name (Fähigkeit)“. Gespeichert in
   `pokewiki_texte.json` mit den Kürzeln der Vorlagen; `importer._derive_texts` ordnet sie über `pokewiki.per_game` den
   Spielen zu (Tabellen `spieltext` und `forschung`) und meldet unbekannte Kürzel im Protokoll.
   **BisaFans** (`app/bisafans.py`): die Seite der Nebenmissionen von Legenden: Arceus, einmal je Abgleich mit
   3 Sekunden Pause; ohne Treffer gilt `bisafans.json` vom letzten Lauf. `importer._derive_auftrag` legt die Aufträge in
   `auftrag` und sucht darin die Namen der Arten aus dem Hisui-Pokédex.
   **PLA Companion** (software-notion.de, `app/companion.py`): je Karte `/apps/pla-companion/map/<Karte>/data?lang=de`
   mit 2 Sekunden Pause; Schnellreise und Lager, ausgerichtet an Geisterlichtern und Icognito von Altissimo
   (`companion.fit`, `importer._derive_companion`). Das Protokoll zählt alle Arten von Einträgen.
   Das Ergebnis liegt in
   `pokewiki.json` im Datenordner und gilt weiter, wenn das Wiki ruht. Die Namen stammen aus der bisherigen Datenbank.
   **Serebii** (`abruf._serebii`, `app/serebii.py`, 2 Sekunden Pause): die Attackenliste von Legenden: Z-A
   (`serebii.za_cooldowns`: Abklingzeit, Stärke, Typ) und die drei Pokédexe von Pokopia (`serebii.pokopia_dex`: Nummer,
   nationale Nummer aus dem Bild, Name, Spezialitäten). Ergebnis in `serebii.json`; was ein Lauf nicht bekommt, gilt vom
   letzten weiter. Beim Bauen läuft es mit dem PokéWiki zusammen (`importer._derive_serebii`).
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
7. **IGN** (`app/ign.py`, Quelle „ign“): je Spiel in `ign.GAMES` die Kartenseite; aus `__NEXT_DATA__` Kachelmuster, Zoom,
   Größe und die mitgelieferten Punkte; alle übrigen Punkte über die GraphQL-Abfrage der Seite (`ign.query`, POST an
   `ign.GRAPH`), gespeichert unter `mapgenie/<Spiel>.ign.json`. Die Kacheln holt der Kachelvorrat.
7. **DittoBase** (`app/dittobase.py`, Quelle „dittobase“): je Spiel in `dittobase.GAMES` (Kristall) die Kartenseite
   (`/<Spiel>/map`, 3 Sekunden Pause), daraus Karte und Punkte nach `mapgenie/<Spiel>.db.json`. Die Kachelsätze (PNG) kommen
   einmal nach `mapgenie/kacheln/db/_saetze/`; daraus zeichnet der Abgleich alle Kacheln selbst nach
   `mapgenie/kacheln/db/<Spiel>/<z>/<x>-<y>.png` (`app/png.py`), neu nur, wenn sich Daten oder Kachelsätze ändern
   (`stand.json`). Gold/Silber hat eine eigene Karte; von Kristall kommt dort nur die Karte von pokemoncompletion dazu.
7. **pokemoncompletion** (`app/pkcompletion.py`, Quelle „pkcompletion“): für Kristall, Smaragd und Platin die Spieldaten
   aus dem Repository (raw.githubusercontent.com), umgerechnet in eine Karte wie bei Map Genie und unter `mapgenie/<Spiel>.pc.json`
   gespeichert; Gold/Silber, Rubin/Saphir und Diamant/Perl zeigen sie mit. Die Kacheln (512 Pixel, `{z}_{x}_{y}.png`) holt
   der Kachelvorrat vom CDN; nach 403 oder 429 ruht nur diese Quelle.
7. **Map Genie** (`app/mapgenie.py`, Quelle „mapgenie“): je Spiel in `mapgenie.GAMES` (Legenden: Arceus, Karmesin/Purpur, Legenden: Z-A, Feuerrot/Blattgrün, Rot/Blau/Gelb) die Spielseite, daraus die Karten
   (`/<Spiel>/maps/<Karte>`), je Karte die Seite (`window.mapData`) und `/api/v1/maps/<Nummer>/data`, 3 Sekunden Pause.
   Ergebnis kompakt in `mapgenie/<Spiel>.json` im Datenordner; Spiele, die es dort nicht gibt, melden 404 und fallen weg.
   Kacheln (`abruf.mg_tile`) liegen unter `mapgenie/kacheln/`: Die Oberfläche fragt sie über `/mgkachel/…` an (0,3 Sekunden
   Pause), der Kachelvorrat (`abruf.mg_stock`, eigener Thread nach jedem Abgleich und beim Start) holt im Hintergrund alle
   Kacheln aller Stufen (erst für alle Karten bis eine unter der größten, dann die größte), 0,6 Sekunden Pause; was da ist,
   bleibt. Danach braucht die Karte kein Netz; ohne Vorrat holt das Ansehen eine fehlende Kachel einmal. Eine Anfrage zur
   Zeit. Ein einzelnes 403 heißt bei Map Genie „Kachel gibt es nicht“ (kommt außerhalb der Karte); nach 8 nacheinander fragt
   der Dienst eine Kachel an, die es sicher gibt: kommt sie, fehlen nur Randkacheln; sonst (oder bei 429) ruht die Quelle 24
   Stunden. Gefragt wird nur ab der kleinsten Zoomstufe der Karte (darunter gibt es keine Kacheln). Fehlende Kacheln
   stehen mit Datum in `mapgenie/kacheln/fehlt.json` (30 Tage), der Stand des Vorrats in `vorrat.json`; ist eine Karte ganz
   durchgesehen, fragt die Oberfläche nicht mehr bei der Quelle nach. Z-A nennt im Muster erst y,
   dann x. Fehlen die Grenzen einer Karte, gelten die der Orte (`mapgenie.bounds_of`).
8. **Showdown-Mods** (mit Showdown): `data/mods/gen{1,2,4,5,6,7,8}/pokedex.ts` für frühere Basiswerte (Tabelle `werte_alt`,
   Generation 1 mit Spezial-Wert); fehlende Mods (404) fallen weg.

## Nutzungsstatistik (Smogon)

`_smogon` (parallel zu den Bildern, 2 Sekunden Pause): Übersicht `https://www.smogon.com/stats/`, im neuesten Monat
(oder dem davor) die Liste `chaos/`, daraus `smogon.pick`: ein Format mit „champions“ im Namen (Doppel zuerst), sonst
die neueste VGC-Regel der Generation 9; Grenze 1630, sonst 1500, 1760 oder die höchste. Die chaos-Datei wird auf die
60 häufigsten Pokémon gekürzt (`smogon.digest`) und als `smogon.json` gespeichert. Gleicher Monat und gleiches Format:
kein neuer Abruf der großen Datei.

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

Fragt jede Quelle einmal an und beschreibt die Antwort, in Gruppen. Verschiedene Server fragt er gleichzeitig an, jeden
Server für sich nacheinander mit Pause (`abruf.DIAG_PAUSE`, sonst `PAUSE`); die Zeilen bleiben in der Reihenfolge der
Abfragen. Der Test läuft im Dienst und geht weiter, wenn die Oberfläche den Reiter wechselt; `GET /api/diag` liefert
den Fortschritt (`gesamt`, `fertig`, `laeuft`) und am Ende Start, Dauer und Zeilen. Ergebnis und Probe-Seiten liegen nur
im Speicher; jeder neue Test ersetzt sie, auf der Platte sammelt sich nichts. Jede Abfrage gibt nach 20 Sekunden ohne
Antwort (`DIAG_TIMEOUT`) auf; nach 60 Sekunden insgesamt (`DIAG_LIMIT`) wertet er aus, was bis dahin kam („nur der
Anfang“). Der Abgleich selbst wartet ohne Gesamtlimit, bis eine Datei ganz da ist. Geht 120 Sekunden lang
gar nichts voran (`DIAG_HANG`), endet der Test trotzdem und nennt die hängenden Abfragen. Höchstens sechs Abfragen
laufen gleichzeitig (`DIAG_PARALLEL`); mehr überlastete auf dem Heimserver die Namensauflösung.

- heutige Quellen: GitHub-API, eine CSV der PokéAPI, Showdown, ein Sprite,
- Items: `items.csv` und `item_flavor_text.csv` der PokéAPI, `items.ts` von Showdown, deutsche Itemnamen aus PKHeX,
- Fundorte aus den Spieldaten: Begegnungsdateien von PKHeX (GPL-3.0) für Legenden: Arceus (mit Alpha und Level
  von–bis, `abruf.pkhex_areas` liest sie), Karmesin/Purpur und Legenden: Z-A, dazu deutsche Ortsnamen, Beherrschung
  und Level-Attacken für Legenden: Arceus,
- Wikis und Datenbanken: PokéWiki (API und Beispielseiten), Bulbapedia, Serebii, Pokémon Database, Map Genie,
- mögliche Quellen zum Testen: Item-Bilder (Serebii, PokéWiki), Kartenseiten von Serebii, GamerGuides (Lager,
  Schnellreise) und Pokébip (Stichwörter und Skripte, als Probe bis 400 000 Zeichen),
- weitere Spieldaten: feste Begegnungen aus den Quelldateien von PKHeX (`importer.pkhex_static`), Werte je Form in
  Legenden: Arceus (Raids in Karmesin/Purpur und Crypto-Pokémon sind seit 0.22.0 eingebaut),
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
