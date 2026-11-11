# Roadmap

## 0.23.0 (Rückmeldung zu 0.22.0, 11.11.2026)

- Kachelvorrat: `abruf.mg_stock` (Thread nach jedem Abgleich und beim Start), `mapgenie.tile_list`, `mapgenie.bounds_of`
  (Grenzen aus den Orten), `tile_ok` mit getrennter Endung; einzelnes 403 einer Kachel = fehlt, erst `MG_403_MAX` nacheinander
  oder 429 lassen Map Genie ruhen. Oberfläche: Ebene `.mgold`, Anzeige `.mgload`, Vorladen der Nachbarstufen
- Schadensrechner: `schaden.calc` mit `crit_mult` und `d_level`, ab Gen 3; `abfragen.damage_matrix` (`/api/schaden/uebersicht`);
  `calcBox` im Reiter Team (`calcT`) und in Champions (`calc`), eigene Gegner `calcFoes:<Spiel>`
- Frühere Basiswerte: `showdown.mod_stats`, Mods `gen1`–`gen8` im Abgleich, Tabelle `werte_alt`, `abfragen.form_stats`
  (Gen 1: Spezial); `importer.VERSION` 16
- Typen: `typeFilter` je Tabelle (`chartPick`, `combosPick`, `ttPickd`, `ttPicka`), `cntTd` farbige Zählspalten
- `team_caught`: Endstufen fallen weg, wenn eine Zwischenstufe schon gefangen ist (`_evolves_from`, `_between`)
- Einstellungen: `details.sub` für Quellen, Verbindungstest und Protokoll im Kasten Abgleich
- Offen: Abklingzeiten in Legenden: Z-A (Proben im Verbindungstest), Karten älterer Spiele (Proben: Serebii PokéEarth, pret,
  Bulbapedia-Archiv), Fangformel und Partner-Techniken in Let's Go, Effort Levels in Legenden: Arceus, Fähigkeiten und Items
  im Schadensrechner, Schadensrechner für Gen 1–2

## 0.22.0 (Sonderspiele Schritt 2, Auftrag 11.11.2026)

- `abfragen.tera_effect` (Team-Bewertung, nur Verteidigung), `#formsel` tauscht die Form eines Team-Platzes
- `app/schaden.py` (rein, Formel ab Gen 5), `/api/schaden`, `calcBox` in der Kampfansicht
- user.db: neue Tabelle `kampf` (Kampftagebuch), `/api/kampftagebuch`, in Export und Sicherung
- PKHeX: Tera-Raids (`encounter_gem_*`, `dist_paldea`, `might_paldea`; `importer.pkhex_raids`, Tabelle `raid`), Reiter `#raids`;
  Crypto-Pokémon aus `Encounters3Colo.cs`/`Encounters3XD.cs` (`importer.pkhex_shadow`, Tabelle `crypto`); `importer.VERSION` 15
- Offen: Effort Levels in Legenden: Arceus (Umfang noch offen), Fähigkeiten und Items im Schadensrechner, deutsche Orte für
  Colosseum/XD, Spezial-Wert der Generation 1, Abklingzeiten in Legenden: Z-A, Karten für ältere Spiele

## 0.21.0 (Sonderspiele Schritt 1, Gegner aus Smogon; Auftrag 11.11.2026)

- `app/smogon.py` (rein): Monat, Format (Champions-Doppel vor VGC Gen 9), Grenze, Kurzfassung der chaos-Datei;
  `abruf._smogon` legt `smogon.json` an, `/api/smogon`, `usageBox` in der Kampfansicht
- `abfragen.no_abilities` (Gen 1–2, Let's Go, Legenden: Arceus), `old_class` (bis Gen 3 physisch/speziell nach Typ, in
  `move_view`, damit auch in der Wertung)
- Tera-Typ je Platz (`details.tera`) auf der Detailseite in Karmesin/Purpur
- Offen: Spezial-Wert der Generation 1 (Quelle für alte Basiswerte), Abklingzeiten in Legenden: Z-A (Quelle), Karten für
  ältere Spiele (pokemoncompletion liefert nur eine JS-Hülle), Tera in der Team-Bewertung

## 0.20.0 (Rückmeldung zu 0.19.0, 11.11.2026)

- `abruf._parallel` und globale Pause je Server (`_HOST_LAST`, eine Sperre je Server): `_build` holt Showdown, PKHeX,
  Spawnpunkte, PokéWiki, Altissimo und Companion gleichzeitig; danach Bilder, Kacheln, Map Genie und `itemhq` (eigene Quelle)
- `abruf.serebii_key`: Serebii-Namen behalten Bindestrich und Apostroph; Fehlliste neu (`itemhq3_fehlen.json`)
- `team_caught`: Potential auch für Mitglieder (`im_team`), gefangene niedrigere Stufen einer Kette im Team fallen weg
- Oberfläche: `.dgrid` (Detailseite), Vergleich mit `cmpMerk` und Kurzfazit, Typfilter `chartPick`, `combosSicht`,
  `favStar`, Spaltensymbol `.pinc` vor dem Titel, Champions-Erklärung (`dblHelp`)

## 0.19.1 (Karten reparieren; Rückmeldung 11.11.2026)

- `mapgenie.tile_range` aus den Kartengrenzen: Server (`abruf.mg_tile`) und Oberfläche fragen nur Kacheln innerhalb an.
  Vorher löste die erste Kachel außerhalb (403 vom Kachelspeicher) die 24-Stunden-Ruhe aus. `abruf.mg_status` und eine
  Kachel-Probe im Verbindungstest zeigen den Zustand
- Beschreibungen behalten ihr Markdown (`mapgenie._text`), `mgMd` setzt es sicher um und übersetzt die Feldnamen

## 0.19.0 (Champions Schritt 2: Kampfansicht, Doppelkampf-Bewertung; Entscheidung 11.11.2026)

- `app/doppel.py` (rein): Rollen über Attacken-Kennungen und Fähigkeiten, Flächenattacken über das Ziel der PokéAPI
  (9 = alle anderen, 11 = alle Gegner), Partner-Immunität auch über Fähigkeiten (Schwebe, H2O-Absorber …), Tempo-Rat.
  `abfragen.team_doubles` (`/api/team/doppel`) liefert Mitglieder samt lernbarer Rollen-Attacken im Spiel
- Oberfläche: `battleView` (`#kampf`); in Champions (`BATTLE()`) heißt der Reiter „Kampf“, `#karte` leitet dorthin,
  „im Kader“ nutzt die Tabelle `gefangen`
- Danach: Champions Schritt 3 (Regeln je Saison, Nutzungszahlen) nach den Proben, dann Schadensrechner

## 0.18.0 (Champions Schritt 1: Showdown-Text, Initiative-Liste; Entscheidung 11.11.2026)

- `app/paste.py` liest und schreibt das Textformat von Showdown; `abfragen.paste_import` ordnet Namen zu (Showdown-Kennungen,
  englische und deutsche Namen aus der PokéAPI), `abfragen.paste_export` schreibt englische Namen
  (`/api/team/import`, `/api/team/export`). Team-Plätze tragen dazu `item`, `faehigkeit`, `wesen`, `tera`, `evs`, `ivs`,
  `geschlecht`, `schillernd`, `spitzname` (JSON in `team.details`, keine neue Spalte)
- Initiative-Liste (`speedView`, `#initiative`): Werte im Browser gerechnet, bis Generation 2 mit DV und Stat Exp
- Quellenprotokoll (Pokémon Database, Dittobase) und Kurzkonzept Sonderspiele liegen als Dokumente vor; Übernahme-Plan:
  Werte-Spanne Level 50/100, Moveset-Suche, Editionsexklusive, Abdeckungs-Prüfer, Vergleich bis 4, Wesen/Item/EVs im Team
- Danach: Champions Schritt 2 (Kampfansicht, Doppelkampf-Bewertung)

## 0.17.0 (große Karte, Vergleich, Typkombinationen; Entscheidung 11.11.2026)

- Eigene Punkte auf Map Genie (`abfragen.mg_overlay`, `/api/mapgenie/eigene`): je Gebiet von Legenden: Arceus richtet
  `mapgenie.align` die Spielkoordinaten an Geisterlichtern und Icognito aus (Abstimmung über Maßstab und Verschiebung,
  dann Ausgleich je Achse; Abweichung um 15 Pixel auf Zoomstufe 14). „Karte“ öffnet in jedem Spiel zuerst die große Karte
- „Gehe zu“ aus den Gebieten von Map Genie (`gebiete` in `mapgenie.parse`), Trefferliste der Suche, `#karte/mg/<Karte>/<Ort>`
- Vergleich (`compareView`, `#vergleich/<A>/<B>`), Typkombinationen (`combosHtml` im Reiter Typen)
- Danach: Leser für pokemoncompletion (ältere Spiele), Champions nach Rückmeldung zum Kurzkonzept

## 0.16.0 (Map Genie, gefundene Symbole; Entscheidung 11.11.2026)

- Map Genie (`app/mapgenie.py`, `abruf._mapgenie`): je Spiel in `mapgenie.GAMES` die Kartenseiten (`window.mapData`:
  Gruppen, Kategorien, Kachelsatz) und `/api/v1/maps/<Nummer>/data` (Orte) nach `data/mapgenie/<Spiel>.json`;
  Kacheln holt `abruf.mg_tile` beim ersten Ansehen (`/mgkachel/…`, eine Anfrage zur Zeit, Pause, Sperre ruht 24 Stunden).
  Oberfläche `mgView` (`#karte/mg/<Karte>`), Spiele ohne eigene Karte öffnen sie unter „Karte“, ohne Map Genie die Gebiete
- Gefunden (user.db `gefunden`, `/api/gefunden`): Schlüssel Art:x:z (Legenden: Arceus) oder `mg:<Ort>`; Sicherung und Einlesen
- Lernlisten der Erweiterungen: `abfragen.LEARN_PARENT`; vorher zeigte etwa Die Insel der Rüstung die Liste von Champions
- Ältere Spiele: Proben von pokemoncompletion (Yellow, Crystal …) im Verbindungstest; danach ein Leser für Symbole
  (Items, Trainer) und Ortskarten, angelehnt an die Ortsseiten der Spieleberater (Karte mit nummerierten Fundstellen)
- Champions: Kurzkonzept (Kampfansicht statt Karte, Doppelkampf-Bewertung, Regeln je Saison, Schadensrechner)

## 0.15.0 (Gebiete für alle Spiele, BDSP; Entscheidung 11.11.2026)

- Gebiete (`abfragen.areas`, `/api/gebiete`, `areasView`, `#karte/gebiete/<Ort>`): je Ort alle Pokémon nach Methode,
  aus `fundort` (PKHeX) oder den Begegnungen der PokéAPI; Spiele ohne Karte öffnen unter „Karte“ die Gebiete
- Strahlender Diamant/Leuchtende Perle: `encounter_bd.pkl` und `encounter_sp.pkl` (Kennung „bs“, `importer._areas_bdsp`),
  Orte `text_bdsp_00000_de.txt`, feste Begegnungen `Encounters8b.cs`; Methoden als `PKHEX_ART` 101–108.
  `importer.VERSION` 14
- Offen: Tutor-Attacken der Erweiterungen (Schwert/Schild, Karmesin/Purpur) aus PKHeX; Karte Karmesin/Purpur (Tera-Raid-Höhlen)

## 0.14.0 (Lernlisten Z-A, Formen zum Ansehen; Entscheidung 11.11.2026)

- `importer.pkhex_learnsets` liest `byte/levelup/lvlmove_za.pkl` (BinLinker16: n Attacken als u16, dann n Level als
  Byte) und `byte/personal/personal_za` (0x50 Bytes je Eintrag, Formen ab FormStatsIndex, TM-Flags ab 0x2C, TMs in
  `importer.ZA_TM`). `importer._derive_lernen` schreibt sie in `pokemon_moves` für Legenden: Z-A und Mega-Dimension
  (TMs ab `ZA_TM_BASE` nur dort), solange die PokéAPI für das Spiel keine Lernliste hat. `importer.VERSION` 13
- Formen zum Ansehen: Extra `formen` (`sprites/pokemon/<Art>-<Form>.png`), `/formen/<Formnummer>`, `detail.optik`
- Verbindungstest: Dateilisten von sv-live-map und Altissimo, Tera-Raid-Höhlen von sv-live-map (300 Höhlen in
  Spielkoordinaten, GPL-3.0) als Grundlage für eine Karte von Karmesin/Purpur

## 0.13.0 (Rückmeldung zu 0.12.0; Entscheidung 11.11.2026)

- `app/companion.py` liest den PLA Companion (software-notion.de, `/apps/pla-companion/map/<Karte>/data?lang=de`):
  Schnellreise und Lager je Karte. Die Lage richtet `companion.fit` an Geisterlichtern und Icognito von Altissimo aus
  (je Achse eine Gerade aus zwei Paaren, es gilt die mit den meisten Treffern). `importer._derive_companion` legt die Orte
  als `reise` und `lager` in `kartenobjekt`. `importer.VERSION` 12. Das Protokoll nennt alle Arten von Einträgen, die der
  Companion führt, damit sich weitere Ebenen planen lassen
- Karte: Filter für Tageszeit und Wetter (Anteil je Bedingung als `c` in `/api/karte`), Ebenen in Gruppen
  (`MGROUPS`), Ziehen auch über Bildern und Symbolen (ein Klick nach dem Ziehen zählt nicht)
- Alpha gefangen: Tabelle `alpha` in user.db (neu, nichts gelöscht), `/api/alpha` mit den möglichen Alphas
  (`abfragen.alpha_possible` aus `fundort` und `spawn`), Sicherung und Übertragen
- Team: `abfragen._furthest` hält je Endstufe nur die weiteste gefangene Stufe
- Fester Tabellenkopf (`.scroll.sticky`, `--stick` wie im VR-Navigator), Items mit `crossTable`
- Item-Bilder: höchstens 1500 je Lauf, Ersatz aus dem anderen Serebii-Ordner und dem kleinen Bild; PKHeX-Items dabei.
  Getragene Items nehmen das Item im Spiel (`importer._item_ids`)
- Verbindungstest: Hisui-Bälle bei Bulbapedia und im PokéWiki (Grundlage für die Fangfaktoren), PLA Companion
- Widersprechen sich Quellen: Spieldaten vor Wikis; PokéAPI gegen Showdown landet unter „Zu erledigen“. Eine Mehrheit
  zählt erst ab drei unabhängigen Quellen. Fangfaktoren der Hisui-Bälle: stimmen Bulbapedia und PokéWiki überein, gilt
  der Wert, sonst stehen beide markiert da (sobald die Proben vom Server da sind)
- Offen: Karten weiterer Spiele (Karmesin/Purpur, Legenden: Z-A), Formen-Galerie (Burmy, Shellos und ähnliche)

## 0.12.0 (Rückmeldung zu 0.11.0, Kartenübersicht; Entscheidung 10.11.2026)

- PokéWiki-Karte (`pokewiki.map_pokemon`, `pokewiki.map_items`, Dateien `PwMapHisui/data/{pokemon,items}/ha_area0N.json`,
  gleiche Spielkoordinaten wie JS-Finder): `importer._derive_wiki_karte` legt Kristallbrocken, Raum-Zeit-Verzerrungen,
  Massenauftreten, Pokémon in Bäumen, feste Alphas und Items am Boden in `kartenobjekt`; Stellen mit vielen Items gehen
  an die nächste Grabstelle von Altissimo. Die Datei gehört zur Karte mit den meisten genau getroffenen Spawnpunkten.
  `importer.VERSION` 11, Item-Tabelle mit englischem Namen (`en`)
- Große Item-Bilder von Serebii (`itemhq`, nach dem englischen Namen, höchstens 400 je Lauf); `/itembild/<id>` nimmt sie zuerst
- Karte: Übersicht mit Pokémon-Bildern je Feld (`mapHeat`, 64 Spieleinheiten), Liste der häufigsten Pokémon im Gebiet,
  mit gewähltem Pokémon der Vergleich aller Gebiete; Kartendaten bleiben im Browser (`MAPCACHE`)
- Schillernd gefangen: Tabelle `schillernd` in user.db (neu, nichts gelöscht), `/api/schillernd`, Sicherung und Übertragen
- Typen „Mein Team“, Team-Attacken, Spalten markieren (`.pinc` in `crossTable`), Items mit Wirkungsspalten und Fangfaktor,
  Einstellungen mit Abschnittsleiste und einklappbaren Kästen (wie im VR-Navigator), Zeiten deutsch (`deTime`)
- Offen: Lager und Schnellreise (nur MapGenie und PLA Companion haben sie; MapGenie verbietet das Auslesen; erledigt in 0.13.0)

## 0.11.0 (Fundorte weiterer Spiele, Lesezeichen; Entscheidung 10.11.2026)

- `importer.pkhex_areas` liest auch Karmesin/Purpur („sv“) und Legenden: Z-A („za“, BinLinker16), dazu Mega-Dimension
  (Hyperspace) und Orte ab 30000; Erweiterungen teilen die Fundorte des Hauptspiels (`importer.PKHEX_SHARE`).
  `importer.VERSION` 10
- Lesezeichen „Seite untersuchen“ nach Vorbild VR-Navigator: liest Seiten, deren Karten erst im Browser laden, als Datei
- Verbindungstest: GamerGuides (Lager, Schnellreise) und Pokébip zum Vergleich

## 0.10.1

- Deutsche Namen wie im Spiel: Geisterlichter, Gedichte
- Verbindungstest: Item-Bilder von Serebii (`itemdex/sprites/…`) und aus dem PokéWiki (`list=allimages`), Serebii-Kartenseite
  (Probe bis 400 000 Zeichen) und PokéWiki-Suche nach Lager und Schnellreise, damit sich neue Leser bauen lassen

## 0.10.0 (Kartensymbole, Jubeldorf, Items weiterer Spiele, Rezepte; Entscheidung 10.11.2026)

- `app/altissimo.py` liest Altissimo (GPL-3.0): Bäume, Erzbrocken, Laub- und Heuhaufen, Kisten und Truhen mit Items
  und Anteil, Irrlichter, Icognito, alte Verse und Grabstellen, Rezepte mit Zutaten und Fundorten der Zutaten;
  `FIT` je Karte aus den gemeinsamen Punkten mit JS-Finder bestimmt. Tabellen `kartenobjekt`, `rezept`, `zutat`
- Jubeldorf als eigene Karte mit dem Kartenbild von Altissimo (nur im Datenordner); Symbole je Art ein- und ausblendbar
- Items: Itemlisten von PKHeX (`importer.ITEM_LISTS`, Itemnamen aus den Spieltexten) für Legenden: Arceus,
  Karmesin/Purpur, Legenden: Z-A, SDLP und die Erweiterungen von Schwert/Schild; unbekannte Items mit eigener Nummer
  ab `importer.PKHEX_ITEM`. `importer.VERSION` 9

## 0.9.1 (Rückmeldung zu 0.9.0, Entscheidung 10.11.2026)

- Liste: Kartenbreite wieder 300 px (vier Spalten), Symbole mittig, Pokéball aktiv nur umgefärbt; ⇄ auf der unteren
  Kartenlinie; Übertragen-Ziel aus `gameOptions`, dazu `freilassen` (`server.FREE`, nur löschen)
- Detail: Vorschlag als Tabelle wie „Deine Auswahl“; Team: `abfragen.foreign_moves` → `fremde_attacken`
- Attacken: `crossTable` (Zeilen und Spalten), Filter Generation bis/nur
- Abgleich: `pokeapi-csv.json.gz` im Datenordner nach Commit der PokéAPI (`abruf.cached_csvs`), damit Läufe ohne
  neuen Stand (neue Quelle, Lücken füllen) die 187 Dateien nicht erneut holen
- Ansichten, die inzwischen überholt sind, schreiben keine Fehlermeldung mehr über die neue

## 0.9.0 (PokéWiki-Leser und Pokémon HOME, Entscheidung 10.11.2026)

- `app/pokewiki.py`: Antworten der MediaWiki-API (`action=query`, bis zu 50 Seiten je Anfrage) und Vorlagen lesen;
  `la_move` (Infobox Attacke: PLStärke, PLStärkeKraft, PLStärkeTempo, PLGenauigkeit, PLAP), `held_items` (Getragene Items)
- `abruf._pokewiki`: Namen aus der bisherigen Datenbank, Pause 2 s, Ergebnis in `pokewiki.json` im Datenordner
  (bei Sperre gilt der letzte Stand); Tabellen `attacke_spiel` und `getragen`, `importer.VERSION` 8
- `move_view` nimmt die Werte des Spiels aus `attacke_spiel` (Wertung rechnet damit)
- „Pokémon HOME“ (`abfragen.HOME`) als Eintrag der Spielauswahl; `/api/uebertragen` (Sammlung in ein anderes Spiel,
  ohne „behalten“ verschoben)

## 0.8.2 (Rückmeldung zu 0.8.1, Entscheidung 10.11.2026)

- Liste: `.nr` oben links, Netz 100 px mit Rand nach Größe, `acts` mit festen Plätzen (`.a.ph` unsichtbar), Raster ab 320 px
- Netz-Hinweis `data-tip-stats` (HTML-Tabelle), `kurzHtml` für Statuswörter, `artCell` für die Fundort-Art
- `thc` und `td.c` für zentrierte Spalten; `MVCOLS` gleiche Spalten für Schadens- und Status-Attacken
- `ask`/`askText`: eigener Dialog statt `confirm()` und `prompt()`
- Items ohne Grenze von 400 Zeilen (Bilder laden erst beim Scrollen), Bilder 64 px


## 0.8.1 (Rückmeldung zu 0.7.1, Entscheidung 10.11.2026)

- Dunkle Farben: `--hcbg` und `--tipbg` #253033, `--sel` gleich dem Seitenhintergrund; nichts dunkler als die Team-Plätze
- Liste: Marken und Knöpfe in einer Zeile unter dem Bild (`acts`), Bild 84 px, Netz 92 px
- Hover-Karte: `glanceHtml` (Angriff, Verteidigung, gut einzusetzen gegen)
- Sortieren: Text erst aufsteigend, Zahlen erst absteigend, dritter Klick neutral (auch eigene Attacken-Auswahl)
- Artworks mit neuer Adresse (`?v=2`), weil das Ersatz-Sprite sieben Tage im Browser lag

## 0.8.0 (Rückmeldung zu 0.7.0, zweiter Teil)

- Tabelle `item` mit `art` (Kategorie der PokéAPI auf Deutsch, `importer.ITEM_ART`), `wirkung` und `wert` (aus dem Kurztext
  gelesen, `importer.item_effect`) und `unfertig` (Platzhalter im Text); `importer.VERSION` 7
- Item-Bilder als Extra `itembild` (Datei bei der Quelle nach Kennung, gespeichert nach Nummer)
- `extra/attacken_kurz.json`: gepflegte Kurz-Infos für Status-Attacken, zu denen die Metadaten nichts hergeben
- `/api/spieldaten`: ZIP mit pokeapi.db, Stand des Abgleichs, Einstellungen und `medien.json` (da, fehlt, gibt es nicht)
- `app/aufgaben.py`: Auftrag zu „Zu erledigen“ und Antwort mit Vorschau (`/api/aufgabe`, `/api/antwort`)
- Karte: Pokémon-Auswahl mit Bildern und Suche

## 0.7.1 (Rückmeldung zu 0.7.0, Entscheidung 10.11.2026)

- Kartenpunkte heißen `.mpin`, festgehaltene Zellen `.fix`: die Klasse `.pin` der Karte traf auch Pin-Nadel und Typtabelle
- Farben der dunklen Ansicht: `--sel` (Auswahl), `--tipbg` (Hinweise), `--hcbg` (Hover-Karte) dunkler als die Karten
- `crossTable` (Fadenkreuz, Festhalten) für Typtabelle, Typwirkung je Mitglied und „Gegen Gegner“
- Kurz-Info je Attacke aus `move_meta` und `move_meta_stat_changes` (`importer.move_short`, Spalte `kurz`, `importer.VERSION` 6)
- Abgleich ist fällig, sobald `importer.VERSION` nicht mehr zum gebauten Stand passt
- Schillernde Artworks (`shinyart/`)

## 0.7.0

- Bewährte Sets: Random-Battle-Sets von Showdown je Generation im Abgleich (Tabelle `moveset`, `importer.VERSION` 5),
  nur für die Generation des Spiels, nicht für die Legenden-Spiele
- Marken für Lehrer-Attacken und Beherrschung in der Attacken-Tabelle

## 0.6.1

- Reiter „Items“ (Tabelle `item`, `importer.VERSION` 4): je Spiel genau, wo die PokéAPI Beschreibungen für das Spiel
  hat, sonst die Items der Generation mit Hinweis
- Detailseite: „Mehr Details“ (Fangchance nach der Formel ab Generation 3 bzw. mit Rüttelproben ab Generation 5,
  Geschlecht, Wachstum, Ei-Gruppen, EV-Ausbeute), schillernde und animierte Sprites, Rufe
- TM-Nummern je Spiel aus `machines`

## 0.6.0 (Fundorte und Karte, Entscheidung 09.11.2026)

- Spawnpunkte (JS-Finder) und Tabellen nach Tageszeit und Wetter (PLA-Live-Map) im Abgleich; Tabellen `spawnpunkt` und
  `spawn` (`importer.VERSION` 3)
- Feste Begegnungen aus PKHeX in `fundort` (Art 9)
- Reiter „Karte“ ohne fremde Bibliothek; Kartenkacheln von Serebii im Datenordner (`karten/`), nie im Repo

## 0.5.1

- Verbindungstest: feste Begegnungen und Raids (PKHeX), Werte je Form in Legenden: Arceus, Sprites schillernd und
  animiert, Rufe, Showdown-Stufen und Random-Battle-Sets, ungenutzte Tabellen der PokéAPI

## 0.5.0 (Fundorte aus den Spieldaten)

- Abgleich holt die Begegnungsdatei und die deutschen Ortsnamen von PKHeX für Legenden: Arceus; neue Tabelle
  `fundort` in pokeapi.db (`importer.VERSION` 2)
- Detailseite: Gebiet, Stellen mit Level, Art und Alpha-Level; Filter „Gebiet“

## Als Nächstes

- Karte wie im PokéWiki, noch offen: Kristallsteine, Massenauftreten, Raum-Zeit-Verzerrungen, Items am Boden. Karten
  für weitere Spiele
- Items: Wirkung auch für Beeren und getragene Items; Fundorte der Items
- Fähigkeiten, die im Kampf zählen (etwa Typ-Verstärker, Immunitäten, Kontakt-Fähigkeiten), knapp in der Teambewertung
- Smogon-Sets (Wettkampf, mit Items und Wesen), sobald vom Server aus erreichbar
- Fundorte Karmesin/Purpur: Tageszeit und Wetter (stehen in PKHeX je Platz), Massenauftreten und feste Pokémon
  (`fixed_paldea.pkl`, `outbreak_paldea.pkl`), Tera-Raids
- Karte Legenden: Arceus: Ebenen von Serebii (Bäume, Erz, Verzerrungen, Massenauftreten, Items am Boden), sobald die
  Proben des Verbindungstests vorliegen; PokéWiki-Karten über das Lesezeichen
- Lernlisten für Legenden: Z-A und Mega-Dimension (fehlen in der PokéAPI; PKHeX prüfen)
- PokéWiki-Leser erweitern: Edelhorden, getragene Items weiterer Spiele (Kürzel der Vorlage `sk` prüfen)
- Karte für Karmesin/Purpur und Legenden: Z-A, danach Regionskarten der älteren Spiele
- Karte Legenden: Arceus: Lager und Schnellreise-Punkte (Kandidaten: GamerGuides, PokéWiki per Lesezeichen)
- Items: Bilder in besserer Auflösung (PokéAPI hat nur 30 px, PKHeX ähnlich klein), Beschreibungen für Items, die es
  nur in PKHeX gibt
- Abgleich: Quellen auf verschiedenen Servern (PokéWiki, GitHub) parallel holen
- Karten: Links auf die Gebietsseiten im PokéWiki statt eigener Bilder (Bildrechte)

## 0.4.2

- Verbindungstest für mögliche neue Quellen (Items, PKHeX-Begegnungen, Wikis, Karten, Kampfdaten) mit Probe-Seiten

## 0.4.1

- Hover-Karte hebt sich mit getöntem Hintergrund und Rahmen von den Karten ab

## 0.4.0 (Rückmeldung zu 0.3, Entscheidung 09.11.2026)

- Kopfzeile und Team-Leiste beim Scrollen sanft weg und zurück (wie im VR-Navigator), Leiste klappt nur zu
- Gefangen je Spiel (user.db, neue Tabelle `gefangen`): bessere Alternativen und langfristiges Potential im Team,
  Filter „nur Gefangene/Favoriten“, Teamsuche nur aus Gefangenen
- Typ-Duell statt bloßem „stark gegen“: austeilen (bester eigener Typ) und einstecken (beide Typen zusammen) getrennt,
  Stufen klar stark, stark, schwer; Filter wahlweise nur klar
- Marken als SVG hinter dem Namen, Knöpfe beim Hovern auf dem Bild; Bubbles ohne Zeichen; Hinweise unter dem Ziel
- Filter „bis/nur Generation“; Detailseite ohne Neuaufbau beim Favorisieren; Attacken-Auswahl als feste Liste
- Team: Sortierung sichtbar, Abweichungen hinterlegt, volles Team fragt, Ziehen aus der Suche, Favoriten und Gefangene
  als Ablage; Gegner mit Rahmen und Namen; Standard-Attacken auch für Mitglieder ohne Attacken
- Attacken mit Farben und Erklärungen; Typtabelle in Grautönen; PokéWiki-Links an Attacken, Fähigkeiten und Orten
- Ansicht-Menü, Version rechts, Stand des Abgleichs; Spielauswahl nach Generationen; Sicherung mit Einlesen

## 0.3.0 (Rückmeldung zu 0.2, Entscheidung 09.11.2026)

- Farben: Nintendo-Rot statt Blassrot, Linien an Spielauswahl und Team-Leiste dezent; Titel lädt neu
- Netzdiagramm: Speichen, Ringe bei 25/50/75 %, 100 % = Höchstwert aller Pokémon je Wert, Skala 0–10 an den Ecken
- Team je Platz statt je Pokémon (dasselbe Pokémon mehrfach), Umsortieren per Drag & Drop, Sortieren
- Gespeicherte Teams: Änderungen bleiben im Browser, bis „Speichern“ oder „Verwerfen“
- Favoriten je Spiel (user.db, neue Tabelle `favorit`), Auswahl beim Klick auf einen Platz
- Hinweis bei Mitgliedern, die nicht im gewählten Spiel vorkommen
- Hover-Karten im Team, in der Leiste, bei Verbesserungen und Gegnern; Hinweise immer dunkel
- Filter „stark gegen Typ“; deutlichere Ausschluss-Bubbles; festgesetzte Mitglieder grün
- Attacken: Reihenfolge ziehen, Standard-Attacken (die letzten vier bis zum Level), beigebrachte Attacken
- Typtabelle: Zeile/Spalte festhalten, reichere Hinweise; Tabellen mit neutraler dritter Sortierung
- Protokoll und Verbindungstest kopieren und herunterladen, eigene Daten als JSON
- Spieldaten werden beim Start vorgeladen (erste Anfrage nach einem Update wartet nicht)

## 0.2.1

- Version in der Kopfzeile, Liste aller Versionen per Klick, einmaliger Hinweis nach einem Update

## 0.2.0 (Oberfläche nach erster Nutzung, Entscheidung 09.11.2026)

- Liste: Hover-Karte mit Artwork, Netzdiagramm und Schwächen (verdeckt die Karte nie), Mini-Netzdiagramm je Karte,
  echte Links (neuer Tab), Typ-Filter als Bubbles (und/oder, ausschließen), Zurücksetzen, Nachladen beim Scrollen
- Team-Leiste unten in jedem Reiter: Drag & Drop, „+“ auf jeder Karte, Plätze tauschen
- Teams je Spiel, die sich selbst speichern, mit Level und vier Attacken je Mitglied; Verbesserungsvorschläge
  (stärkere Attacken bis zum Level, fehlender Eigentyp-Bonus, doppelte Typen); Abdeckung nach gewählten Attacken
- Detailseite: Hover-Infos (Typen, Werte mit Rang unter allen Pokémon, Typwirkung, Fähigkeiten, Attacken),
  Netzdiagramm, Spielwahl, Level ohne Neuladen der Seite, eigene Attacken-Auswahl
- Team-Ansicht: alle Filter für Vorschläge und Teamsuche, Gegner-Team (bis zu sechs) mit Übersicht
- Attacken: alle Attacken je Spiel inklusive Status, Filter (Typ, Klasse, Vorrang, Kontakt, Stärke), sortierbare Spalten
- Typtabelle: lesbare Kopfzeile, Linien, Legende, Hervorhebung von Zeile und Spalte
- Offizielle Artworks (475 × 475) zusätzlich zu den Sprites
- Wertung: Attacken, nach denen der Anwender kampfunfähig ist (Finale, Explosion), zählen nur noch 30 %

## 0.1.0 (Stufe 1: Gerüst)

- Dienst mit SQLite: pokeapi.db aus PokéAPI und Showdown, user.db für Teams und Entscheidungen
- Abgleich mit Zeitplan, Selbstprüfung, Protokoll, Verbindungstest, Sprites
- Pokémon-Liste mit Filtern und Spiel-Auswahl (Regional-Dex), Detailseite, Attacken je Spiel mit Wertung und Gründen
- Team: Bewertung, Vorschläge, beste Team-Suche, Gegner-Modus, gespeicherte Teams
- Beste Attacken je Typ, Typtabelle je Generation

## Stufe 2: Legenden: Arceus vollständig

- PokéWiki-Leser über die MediaWiki-API (schonend, mit Quellenangabe): Fundorte je Gebiet mit Tageszeit und Wetter,
  Elite-Pokémon, Edelhorden-Bosse, Attackenwerte in Legenden: Arceus (Kraft- und Tempostil)
- Karten der Gebiete mit Fundorten (Lizenz der Kartenbilder prüfen, Namensnennung)
- Bulbapedia als Ersatz, wenn das PokéWiki nicht antwortet
- Abweichungen zwischen den Quellen unter „Zu erledigen“

## Stufe 3: eigene Sammlung

- Pokémon als gefangen, entwickelt, im Team markieren; Vorschläge aus dem eigenen Bestand
- Fortschritt im Pokédex je Spiel

## Später

- Items (Fundorte, Wirkung, Entwicklungs-Items)
- Fähigkeiten in der Teamwertung (Einschüchterung, Wetter)
- Weitere Spiele mit eigenen Daten (Karmesin / Purpur, Legenden: Z-A), sobald eine Quelle sie liefert
- Installierbar als App auf dem Handy (PWA)
