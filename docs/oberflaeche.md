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
- Titel: führt zur Liste und lädt Spieldaten, Favoriten und Typtabelle neu.
- Team: Mitglieder je Platz (`ids` und parallel `details` mit Level und Attacken), dasselbe Pokémon darf mehrfach
  hinein. Die Detailseite eines Platzes ist `#pokemon/<id>/<platz>`. Ein gespeichertes Team ändert sich auf dem Server
  erst mit „Speichern“; bis dahin steht „nicht gespeichert“ in der Leiste (`dirty`), „Verwerfen“ lädt den Serverstand.
- Favoriten je Spiel (`/api/favoriten`): ☆ auf Karten und der Detailseite; Klick auf einen leeren Platz oder ⇄.
- Neue Mitglieder bekommen die Standard-Attacken (wie im Spiel die letzten vier Level-Attacken bis zum Level, ohne
  Level die ersten vier).
- Sortierbare Tabellen: erster Klick absteigend, zweiter aufsteigend, dritter wieder wie geladen.
- Netzdiagramm: 100 % je Wert = Höchstwert aller Pokémon und Formen ohne Mega und Gigadynamax (`meta.verteilung`);
  Ringe bei 25, 50 (gestrichelt) und 75 %, an den Ecken der Karten eine Skala von 0 bis 10.
- Kopfzeile (`#stick`) und Team-Leiste: nach gut 300 px abwärts gleiten sie weg (`.hid`, die Leiste klappt mit `.fold`
  auf ihre Kopfzeile zu), 40 px aufwärts holt sie zurück. Ziehen klappt die Leiste auf.
- Marken hinter dem Namen (SVG, `icon()`): im Team, gefangen (`/api/gefangen`), Favorit. Der Pokéball wechselt bei
  jedem Klick: nicht gefangen, gefangen, schillernd (`/api/schillernd`, goldener Ball mit Glanz, `ball()`), wieder nicht gefangen. Knöpfe zum Setzen beim
  Hovern unten auf dem Bild (`.acts`); `redrawMarks()` zeichnet sie überall neu, ohne die Seite aufzubauen.
- Typ-Duell (`duel()` in JS und `abfragen.duel`): austeilen = bester eigener Typ gegen den Zieltyp, einstecken =
  Zieltyp gegen beide eigenen Typen. Klar stark: ×2 und höchstens ×½; stark: ×2 und ×1; schwer: ×2 einstecken und
  höchstens ×1 austeilen. Der Filter „stark gegen“ nutzt dieselbe Rechnung („klar“ = nur Stufe 2).
- Hinweise (`data-tip`) erscheinen unter dem Ziel, Hover-Karten daneben.
- Sicherung: `/api/export` lädt herunter, `/api/restore` ersetzt alle eigenen Daten (vorher `vor-einlesen-…` in
  `sicherung/`).
- Fundorte (`encHtml`): mit Daten aus PKHeX (`fundquelle`) Gebiet, Stellen mit Level (ab sechs Stellen gekürzt, alle im
  Hinweis), Art, Level und Alpha-Level; Spalten nur, wo ein Eintrag Daten hat; sonst die Tabelle der PokéAPI. Filter „Gebiet“ (`areaSelect`) nur bei Spielen
  mit Gebieten (`/api/meta`, `spiele[].gebiete`), ohne Massenauftreten.
- Karte (`mapView`, `#karte/<Karte>/<Form>`): Welt 2048 px = Spielkoordinate × 2; Kacheln `karten/<Karte>/<z>-<x>-<y>.png`
  (Zoom 0–2, Stufe nach Maßstab), Punkte behalten ihre Größe (`--inv`). Ziehen mit Pointer-Events, Mausrad und +/−
  zoomen; mit Form werden ihre Punkte gelb hervorgehoben und die Ansicht passt sich ihnen an. Daten: `/api/karte/<Karte>`.
  Symbole (`.mobj`, Zeichen in `MOBJ`) liegen wie die Spawnpunkte in Spielkoordinaten; jede Art ist eine Ebene zum
  Ein- und Ausblenden (gemerkt in `mapHide`, „alle“ und „keine“). Jubeldorf (`jubilifevillage`) hat statt Kacheln ein Bild (`bild.png`).
  Die Daten je Karte bleiben im Browser (`MAPCACHE`), die Wahl eines Pokémon lädt nichts neu.
- Kartenübersicht (`mapHeat`, Schalter „Übersicht mit Bildern“, gemerkt in `mapHeat`): Felder zu 64 Spieleinheiten; je Feld
  bis zu drei Pokémon als Bild im Schwerpunkt ihrer Punkte, Größe nach der Summe der Anteile (Spawnpunkt: höchster Anteil,
  PokéWiki-Stelle: ihr Anteil oder 1). Daneben die häufigsten Pokémon des Gebiets; mit gewähltem Pokémon nur dieses und
  ein Vergleich aller Gebiete (lädt die übrigen Karten einmal).
- Karte, seit 0.13.0: Filter Tageszeit und Wetter (`mapZeit`, `mapWetter`; Anteil je Bedingung `c`, Tageszeit × 9 + Wetter),
  Punkte ohne Pokémon unter der Bedingung sind blass; Ebenen in Gruppen (`MGROUPS`, Klick auf den Gruppennamen schaltet alle);
  Ziehen beginnt überall (ab 4 px, danach zählt kein Klick); der Ausschnitt bleibt beim Filtern (`MAPPOS`).
- α (`alphaBtn`, `/api/alpha`): bündig über dem Pokéball, nur für mögliche Alphas des Spiels; setzt auch gefangen.
- Fester Tabellenkopf: `.scroll.sticky` (Attacken, Items) mit `top: var(--stick)`; auf schmalen Bildschirmen scrollt die
  Tabelle seitlich ohne festen Kopf.
- Team: „Showdown-Text“ (`#sdbox`, offen gemerkt als `sdOpen`) mit `sdExport` und `sdImport` (ersetzt das Team nach
  Rückfrage); `slotExtra` zeigt Item, Fähigkeit, Wesen und Tera-Typ aus `plaetze` der Bewertung.
- Initiative-Liste (`speedView`, `#initiative`, Einstellungen in `speed`): Spalten minimal, neutral, maximal, maximal mit
  Wesen; Team-Zeilen (`tr.mine`) mit eigenem Wert an ihrer Stelle in der Liste.
- Vergleich (`compareView`, `#vergleich/<A>/<B>`, „-“ = leer): zwei Suchfelder, Werte mit Unterschied, Verteidigung je
  Angriffstyp (grün = steckt weniger ein), Fähigkeiten, Attacken (nur A, beide, nur B).
- Typkombinationen (`combosHtml`, unter der Typtabelle, aufklappbar `combosOpen`): Verteidigung je Kombination, sortierbar.
- Map Genie: eigene Ebenen „Aus den Spieldaten“ (Legenden: Arceus, `/api/mapgenie/eigene`), „Gehe zu“, Trefferliste der
  Suche, `#karte/mg/<Karte>/<Ort>` springt zu einem Ort. Gefunden gilt auf der großen Karte und den Einzelkarten gleich.
- Map Genie (`mgView`, `#karte/mg/<Karte>`, `/api/mapgenie`, Kacheln `/mgkachel/<Spiel>/<Karte>/<z>/<x>/<y>`): eigene
  Kachelanzeige (Web-Mercator, ganze Zoomstufen), Punkte je Kategorie in der Farbe der Gruppe, Ebenen rechts zum
  Auf- und Zuklappen (`mgHide:<Spiel>`, `mgOpen`), Suche, Rechtsklick = gefunden (`/api/gefunden`, `mapGotHide`).
  Auf der Karte von Legenden: Arceus gilt dasselbe für die Symbole (Schlüssel Art:x:z).
- Gebiete (`areasView`, `#karte/gebiete/<Ort>`, `/api/gebiete`): links die Orte mit „noch nicht gefangen / alle“,
  rechts das Bildergitter nach Methode; Spiele ohne Karte landen unter „Karte“ direkt hier. Ort je Spiel gemerkt
  (`gebiet:<Spiel>`), Filter „nur noch nicht gefangene“ (`gebietFehlend`).
- Formen zum Ansehen (`optikHtml`, `detail.optik`): eingeklappt unter den getragenen Items, nur bei Pokémon mit mehreren
  Formen gleicher Werte; die Standardform zuerst.
- Fangchance (`catchHtml`): eigene Karte unter der Entwicklung, offen, solange das Pokémon nicht als gefangen markiert
  ist; ohne kritischen Fang und Boni, in Generation 1 und 2 und den Legenden-Spielen nur als Richtung (`fang_grob`).
- Mehr Details (`moreHtml`, `detail.mehr`): eingeklappt; keine Eier und EVs in Legenden: Arceus.
- Typwirkung und Duell (`defHtml`, `duelHtml`): eine Zeile je Multiplikator (`.er`), Faktor vorn, Typen dahinter. Im
  Duell steht ↑ für austeilen und ↓ für einstecken.
- Fadenkreuz (`crossTable`): Tabellen mit `data-r` an Zeilen, `data-c` an Zellen und `data-pr`/`data-pc` an den Köpfen;
  Hover `.hl`, festgehalten `.fix`. Genutzt von Typtabelle, Typwirkung je Mitglied und „Gegen Gegner“. Sortierbare
  Köpfe bekommen ein kleines ▯ (`.pinc`), das die Spalte festhält, ohne zu sortieren; Zellen mit `data-pr` (etwa der Name
  in der Attacken-Liste) markieren nur die Zeile.
- Typtabelle „Mein Team“ (`chartTeam`): nur die Typen des Teams als Zeilen, dazu `teamTypeHtml` (Verteidigung und Angriff
  je Mitglied, einklappbar, gemerkt in `ttOpen`).
- Karten der Liste: unter dem Bild eine Zeile (`acts`) mit Team-Häkchen, Stern und Pokéball; gesetzte Marken sind immer
  zu sehen, die übrigen Knöpfe und „+“ beim Hovern, alles an derselben Stelle. Anderswo stehen Marken (`marks`) hinter dem Namen.
- Hover-Karte (`glanceHtml`): Angriff (bester eigener Typ je Ziel), Verteidigung (beide Typen), „gut einzusetzen gegen“
  (trifft ×2 oder mehr, steckt höchstens ×½ ein). Das ausführliche Duell steht auf der Detailseite.
- PokéWiki-Links (`wikiLink`, `a.wl`): der Name selbst ist der Link, unterstrichen nur beim Hovern, kein Pfeil.
- Zentrierte Spalten mit `thc(…)` im Kopf und `td.c` in den Zellen; Zahlen, Typ und Klasse stehen mittig, Text links.
- Rückfragen nie mit `confirm()` oder `prompt()`: `await ask(titel, text, knopf, gefährlich)` und `await askText(…)`.
- Sortierbare Tabellen (`table.sort`): Text erst aufsteigend, Zahlen erst absteigend, dann umgekehrt, dritter Klick neutral.
- Extras (`extrasHtml`, `detail.extras`): Knöpfe nur für schon geladene Dateien; `/shiny/<id>`, `/anim/<id>`, `/rufe/<id>`.
- Attacken: `moveMarks` setzt Marken für Lehrer und Beherrschung nach den Wegen; `setsHtml` zeigt die bewährten
  Sets (`sets`, `sets_gen` aus `/api/pokemon/<id>/attacken`), grau, was nicht in der Lernliste steht. „Übernehmen“
  nimmt `vorschlag` (die vier lernbaren mit der höchsten Wertung, Status zuletzt).
- Items (`itemsView`, `#items`): Daten aus `/api/items?spiel=…`; Suche, Tasche und Art filtern im Browser, höchstens 400
  Zeilen auf einmal. Spalten je Tasche (`COLS`): KP, AP, EP und Statusprobleme bei Medizin und Beeren (`itemFx`, aus Kurztext
  und Beschreibung des Spiels), Fangfaktor und Bedingung bei Bällen (`BALL`, in Legenden: Arceus `BALL_HISUI` als
  Richtwerte), die Attacke des Spiels bei Maschinen. Preise farbig (`priceColor`).
  Bilder unter `itembild/<Nummer>`; unfertige Einträge (`unfertig`) nur mit dem Schalter.
- Auswahl mit Bildern (`.pick`, Karte): Knopf, darunter Suche und Liste aus echten Links; Enter nimmt den ersten Treffer.
- Einstellungen: `foldBoxes` macht aus jedem Kasten ein `details.fold` mit Leiste oben (`.jump`, „alle auf“, „alle zu“);
  zugeklappte merkt sich `setShut`. Zeiten mit `deTime` (deutsch, Zeit des Browsers), Protokollzeilen mit `logLocal`.
- „Zu erledigen“: „Auftrag kopieren“ (`/api/aufgabe`), „Antwort einlesen“ mit Vorschau (`/api/antwort`, erst mit `dry`),
  „herunterladen“ als CSV. Spieldaten als ZIP unter `/api/spieldaten`.
- Version: steht rechts neben dem Ansicht-Knopf, ein Klick zeigt alle Versionen (`NEUIGKEITEN` in `app/sources.py`).
  Nach einem Update erscheint einmal ein Hinweis, was neu ist; der Browser merkt sich die gesehene Version
  (`px.version`). Beim ersten Besuch gibt es keinen Hinweis.

## Farben

Wie im VR-Navigator: Farbtokens in `:root`, dunkle Ansicht über `prefers-color-scheme` oder den Knopf oben rechts.

- Typen: feste Farbe je Typ (`.t1` bis `.t18`), Schrift weiß
- Typwirkung: rot = schwach (dunkel bei ×4), grün = resistent (dunkel bei ×¼), dunkel = immun
- Hinweise: blau = Info, gelb = Achtung, rot = Problem, grün = in Ordnung
- Basiswerte-Summe: Rot (um 200) bis Grün (um 680)
- Hover-Karte und Hinweise: `--hcbg`/`--tipbg`, in der dunklen Ansicht etwas heller als die Karten. Auswahl (`--sel`)
  und Hover (`--hov`) nie dunkler als der Seitenhintergrund (Team-Plätze).
- Gegner: Karten mit rotem Rahmen
- Akzent: Nintendo-Rot (`--brand`); Typ-Bubbles: gewählt = heller Rahmen mit Schein, ausgeschlossen = roter Rahmen und
  durchgestrichen (ohne Zeichen, gleiche Größe); im Team: grüner Rahmen; festgesetzt (📌): grün; passt nicht zum
  Spiel: gelb; Favorit: gelber Stern; gefangen: roter Pokéball
- Hinterlegt (blau getönt): wo Verbesserungen vom Team abweichen; grün getönt: neu gegenüber dem Team
- Attackenwerte: Stärke, Genauigkeit und Wertung von Rot nach Grün
- Typtabelle: festgehaltene Zeile und Spalte in Grau, dunkler als beim Hovern
- „Spielwert“: Attackenwerte, die im gewählten Spiel anders sind als heute

## Telefon

Ab 600 px Breite einspaltig; keine Seite scrollt waagerecht, breite Tabellen scrollen in ihrem Kasten.
