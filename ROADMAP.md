# Roadmap

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

- Karte wie im PokéWiki: Symbole für gewöhnliche Fundorte, Alpha, Aprikoko- und Beerenbäume, Kisten, Kristallsteine,
  Massenauftreten, Raum-Zeit-Verzerrungen, Items mit Bild und Irrlichter. Quelle klären: die PokéWiki-Karte lädt ihre
  Daten per JavaScript; der Abruf kommt mit dem PokéWiki-Leser. Karten für weitere Spiele
- Items: Wirkung auch für Beeren und getragene Items; Fundorte der Items; Zutaten zum Herstellen (Legenden: Arceus,
  aus dem PokéWiki)
- Fähigkeiten, die im Kampf zählen (etwa Typ-Verstärker, Immunitäten, Kontakt-Fähigkeiten), knapp in der Teambewertung
- Smogon-Sets (Wettkampf, mit Items und Wesen), sobald vom Server aus erreichbar
- Fundorte aus PKHeX auch für Karmesin/Purpur und Legenden: Z-A (Format der Dateien lesen)
- PokéWiki-Leser erweitern: Edelhorden, Herstell-Zutaten, Kartensymbole (Bäume, Kisten, Kristallsteine, Irrlichter),
  getragene Items weiterer Spiele (Kürzel der Vorlage `sk` prüfen)
- Items: Bilder, genaue Listen für Karmesin/Purpur und die Legenden-Spiele (PKHeX), Fundorte der Items
- Karte für Karmesin/Purpur und Legenden: Z-A, danach Regionskarten der älteren Spiele
- Karte Legenden: Arceus: Jubeldorf, Schnellreise-Punkte und weitere Symbole neben Pokémon
- Items: Bilder in besserer Auflösung (PokéAPI hat nur 30 px), Items weiterer Spiele
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
