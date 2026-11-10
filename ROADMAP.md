# Roadmap

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

- Smogon-Sets (Wettkampf, mit Items und Wesen), sobald vom Server aus erreichbar
- Fundorte aus PKHeX auch für Karmesin/Purpur und Legenden: Z-A (Format der Dateien lesen)
- PokéWiki-Leser (vom Heimserver aus erreichbar, Proben aus dem Verbindungstest) für das, was PKHeX nicht hat:
  Tageszeit und Wetter, Edelhorden, Attackenwerte (Kraft- und Tempostil) und Lehrer-Attacken in Legenden: Arceus
- Items: Bilder, genaue Listen für Karmesin/Purpur und die Legenden-Spiele (PKHeX), Fundorte der Items
- Karte für Karmesin/Purpur und Legenden: Z-A, danach Regionskarten der älteren Spiele
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
