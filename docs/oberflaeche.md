# Oberfläche

Reines JavaScript ohne Build (`app/static/js/app.js`), Reiter über die Adresse: `#pokemon`, `#pokemon/<id>`,
`#team`, `#attacken`, `#typen`, `#einstellungen`. Gewähltes Spiel, Filter und das aktuelle Team merkt sich der
Browser; gespeicherte Teams liegen auf dem Server (user.db).

## Bedienung

- Jede Karte ist ein echter Link (`#pokemon/<id>`), Mittelklick und „In neuem Tab öffnen“ gehen.
- Hover: Karten zeigen nach kurzer Pause eine Hover-Karte neben sich (rechts, sonst links, sonst darunter), nie
  darüber. Elemente mit `data-tip` oder `data-tip-type` zeigen einen Hinweis; Typ-Hinweise rechnet die Oberfläche aus
  der Typtabelle des Spiels.
- Team-Leiste (`#dock`): Karten und Vorschläge lassen sich auf einen Platz ziehen; Plätze untereinander tauschen.
  Ein gespeichertes Team speichert jede Änderung selbst (`POST /api/teams`), Level und Attacken liegen unter `details`.
- Tabellen mit `class="sort"` sortieren per Klick auf die Kopfzeile, nach `data-s` der Zellen.
- Eigene Attacken-Auswahl: im Team in `details`, sonst je Spiel und Pokémon im Browser.

## Farben

Wie im VR-Navigator: Farbtokens in `:root`, dunkle Ansicht über `prefers-color-scheme` oder den Knopf oben rechts.

- Typen: feste Farbe je Typ (`.t1` bis `.t18`), Schrift weiß
- Typwirkung: rot = schwach (dunkel bei ×4), grün = resistent (dunkel bei ×¼), dunkel = immun
- Hinweise: blau = Info, gelb = Achtung, rot = Problem, grün = in Ordnung
- Basiswerte-Summe: Rot (um 200) bis Grün (um 680)
- Gegner: rötlich getönte Leiste über der Auswertung
- „Spielwert“: Attackenwerte, die im gewählten Spiel anders sind als heute

## Telefon

Ab 600 px Breite einspaltig; keine Seite scrollt waagerecht, breite Tabellen scrollen in ihrem Kasten.
