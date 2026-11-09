# Roadmap

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
