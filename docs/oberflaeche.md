# Oberfläche

Reines JavaScript ohne Build (`app/static/js/`). Die Ansicht steht in der Adresse: `#pokemon`, `#pokemon/<id>`
(`#pokemon/<id>/<platz>` für einen Team-Platz), `#team`, `#attacken`, `#typen`, `#items`, `#karte` (mit
`#karte/mg/<Karte>`, `#karte/gebiete/<Ort>`), `#fehlt`, `#sammeln`, `#vergleich/<A>/<B>`, `#initiative`, `#kampf`,
`#raids`, `#auftraege`, `#einstellungen`. Gewähltes Spiel, Filter, aufgeklappte Kästen und das aktuelle Team merkt sich
der Browser (`store`, `localStorage`); gespeicherte Teams und alle eigenen Daten liegen auf dem Server (user.db).

Aufbau: zuerst die Dateien, dann die Regeln für Gestaltung und Verhalten, die überall gelten, dann die Ansichten
je Reiter zum Nachschlagen.

## Dateien

`index.html` lädt die Teile als gewöhnliche Skripte der Reihe nach; sie teilen sich die globalen Namen.

| Datei | Inhalt |
|---|---|
| `basis.js` | Grundlagen: Zustand `S`, `store`, `api`, Hinweise (`hinweis`, `teil`, `ungespeichert`), Spielprofil (`PROFIL`), Bausteine (Karten, Netzdiagramm, Typwirkung), Tooltips, Kreuz- und sortierbare Tabellen |
| `kopf.js` | Kopf, Reiter, Adresse (`route`), Spielwahl (`setGame`), Favoriten und Haken, `refreshMeta`, Filter |
| `liste.js` | Pokémon-Liste, Team-Leiste (`dock`), Speichern des Teams, Showdown-Export |
| `detail.js` | Detailseite (Werte, Effort Levels, Fangchance, Entwicklung, Attacken), Raids, Aufträge, Forschung |
| `team.js` | Team, Gegner und Trainer, Attacken |
| `karte.js` | Karten, Sammelobjekte, Was fehlt mir noch, Gebiete |
| `items.js` | Items und Typtabelle |
| `kampf.js` | Vergleich, Initiative-Liste, Kampf (Champions), Schadensrechner |
| `einstellungen.js` | Einstellungen, Abgleich, Sicherung, Seite untersuchen, Verbindungstest |
| `start.js` | Klicks und Start (ruft als einziger Teil `refreshMeta()` beim Laden) |

Die Teile sind an Abschnittsgrenzen geschnitten; deshalb steht hier und da etwas nicht beim Reiter (die Merker der
Kreuztabellen am Ende von `team.js`, Raids und Aufträge in `detail.js`).

Regeln für die Dateien:

- Jede Datei beginnt mit `"use strict";`.
- Was beim Laden sofort läuft (nicht erst in einer Funktion), darf nur Namen aus derselben oder einer früheren Datei
  benutzen. Funktionen dürfen alles aufrufen, weil sie erst nach dem Laden laufen.
- Eine neue Datei kommt in `index.html` an ihren Platz. Der Server hängt jeder Adresse eine Kennung aus Version und
  Prüfsumme des Inhalts an (`server.skripte`, `index_page`, `static_tag`); mit dieser Adresse bleiben die Dateien
  unbegrenzt im Browser, der Server liest und packt jede Datei einmal. `Http.test_skripte_der_oberflaeche` prüft, dass
  jede Datei genau einmal geladen wird.
- Die Tests lesen die Teile zusammen (`tests.basis.oberflaeche_js`).

## Gestaltung

### Farben

Farbtokens in `:root` (wie im VR-Navigator), dunkle Ansicht über `prefers-color-scheme` oder den Knopf oben rechts.

- Akzent: Nintendo-Rot (`--brand`).
- Typen: feste Farbe je Typ (`.t1` bis `.t18`), Schrift weiß.
- Typwirkung: rot = schwach (dunkel bei ×4), grün = resistent (dunkel bei ×¼), dunkel = immun.
- Hinweise: blau = Info, gelb = Achtung, rot = Problem, grün = in Ordnung.
- Basiswerte-Summe: Rot (um 200) bis Grün (um 680). Attackenwerte (Stärke, Genauigkeit, Wertung): Rot nach Grün.
  Preise farbig (`priceColor`).
- Hover-Karte und Hinweise: `--hcbg`/`--tipbg`, in der dunklen Ansicht etwas heller als die Karten. Auswahl (`--sel`)
  und Hover (`--hov`) nie dunkler als der Seitenhintergrund (Team-Plätze).
- Typ-Bubbles: gewählt = heller Rahmen mit Schein, ausgeschlossen = roter Rahmen und durchgestrichen (ohne Zeichen,
  gleiche Größe).
- Marken: im Team grüner Rahmen (Häkchen grün nur im Team), festgesetzt (📌) grün, passt nicht zum Spiel gelb, Favorit
  gelber Stern, gefangen roter Pokéball, schillernd goldener Ball mit Glanz. Gegner: Karten mit rotem Rahmen.
- Hinterlegt (blau getönt): wo Verbesserungen vom Team abweichen; grün getönt: neu gegenüber dem Team.
- Typtabelle: festgehaltene Zeile und Spalte in Grau, dunkler als beim Hovern.
- „Spielwert“: Attackenwerte, die im gewählten Spiel anders sind als heute.

### Anordnung

- Maßstab ist ein Bildschirm mit 1366 × 768 Bildpunkten. Bis 600 px Breite einspaltig (Telefon). Keine Seite scrollt
  waagerecht, breite Tabellen scrollen in ihrem Kasten.
- Fester Tabellenkopf: `.scroll.sticky` (Attacken, Items) mit `top: var(--stick)`; auf schmalen Bildschirmen scrollt die
  Tabelle seitlich ohne festen Kopf.
- Zentrierte Spalten mit `thc(…)` im Kopf und `td.c` in den Zellen: Zahlen, Typ und Klasse mittig, Text links.
- Klapp-Pfeile: ein CSS-Dreieck für jedes `details>summary` und `[data-fold]` (gleiche Größe und Farbe, dreht beim
  Öffnen), keine eigenen Pfeile je Kasten. Klapp-Titel einheitlich `--ink-hi`.
- Typwirkung (`defHtml`, `duelHtml`): eine Zeile je Multiplikator (`.er`), Faktor vorn, Typen dahinter; im Duell ↑ für
  austeilen und ↓ für einstecken.
- Netzdiagramm: 100 % je Wert = Höchstwert aller Pokémon und Formen ohne Mega und Gigadynamax (`meta.verteilung`);
  Ringe bei 25, 50 (gestrichelt) und 75 %, an den Ecken der Karten eine Skala von 0 bis 10.
- Marken sind SVG (`icon()`); auf den Karten der Liste stehen sie in einer Zeile unter dem Bild (`.acts`), anderswo
  hinter dem Namen (`marks`).
- PokéWiki-Links (`wikiLink`, `a.wl`): der Name selbst ist der Link, unterstrichen nur beim Hovern, kein Pfeil.

## Verhalten

### Allgemein

- Jede Karte ist ein echter Link (`#pokemon/<id>`); Mittelklick und „In neuem Tab öffnen“ gehen.
- Rückfragen nie mit `confirm()` oder `prompt()`, sondern `await ask(titel, text, knopf, gefährlich)` und
  `await askText(…)`.
- Laden: Beim Wechsel der Ansicht (`VIEW`) steht sofort „Lädt …“; dauert es länger als 120 ms, zeigt `body.busy` oben
  einen Balken. Eine überholte Ansicht schreibt nichts mehr über die neue.
- Kopfzeile (`#stick`) und Team-Leiste: nach gut 300 px abwärts gleiten sie weg (`.hid`, die Leiste klappt mit `.fold`
  auf ihre Kopfzeile zu), 40 px aufwärts holt sie zurück. Ziehen klappt die Leiste auf.
- Titel: führt zur Liste und lädt Spieldaten, Favoriten und Typtabelle neu.
- Regeln je Spiel kommen aus dem Spielprofil (`PROFIL()`, in `/api/meta` je Spiel unter `profil`; Felder in
  `docs/spiele.md`), nie aus einem Vergleich mit der Kennung (Test `Spiele`). Helfer: `GEN()`, `noAbil()`
  (`faehigkeiten`), `TERA()` (`tera`, Tera-Typ je Platz über `#terasel`), `RAIDS()` (`raids`, Reiter Raids),
  `REQ_GAME()` (`auftraege`, Reiter Aufträge), `BATTLE()` (`kampf`), `LA()` (`werte` „el“: Effort Levels),
  `STATS_OK()` (`werte` dv, ev oder av).

### Hover und Tooltips

- Karten zeigen nach kurzer Pause eine Hover-Karte neben sich (rechts, sonst links, sonst darunter), nie darüber.
  Hinweise (`data-tip`) erscheinen unter dem Ziel.
- `data-tip-type`: Typ-Hinweise rechnet die Oberfläche aus der Typtabelle des Spiels.
- Rechenwege (Schaden, Werte, Effort Levels, Fangchance) liegen als HTML in `TIPM`; das Element trägt nur
  `data-tip-calc="n"` (`tipRef(html)`), gebaut von `partsTip`, `dmgTip`, `catchTip` und `speedTip`. Lange Listen
  (Initiative) tragen statt dessen `data-tip-speed` und rechnen den Tooltip erst beim Hovern.
- Das Alter von Daten steht, wenn überhaupt, knapp am Ende eines passenden Tooltips, nicht als eigene Spalte.

### Tabellen

- Sortierbar (`table.sort`, Kopf mit `data-sort`): sortiert nach `data-s` der Zellen, sonst nach dem Text. Text erst
  aufsteigend, Zahlen erst absteigend, zweiter Klick umgekehrt, dritter Klick wieder wie geladen.
- Fadenkreuz (`crossTable(table, pin, onChange, marks)`): Tabellen mit `data-r` an Zeilen, `data-c` an Zellen und
  `data-pr`/`data-pc` an den Köpfen; Hover `.hl`, festgehalten `.fix`. Sortierbare und nicht sortierbare Köpfe bekommen
  ein kleines ▯ (`.pinc`) vor dem Titel, das die Spalte festhält, ohne zu sortieren. Zellen mit `data-pr` (etwa der Name
  in der Attacken-Liste) und Zellen ohne `data-c` (Wirkung, Beschreibung) markieren nur die Zeile. Mit `marks=false`
  ohne Markierungszeichen (Typtabellen). Genutzt von Typtabelle, Typwirkung je Mitglied, „Gegen Gegner“, Attacken und
  Items. Zeilenköpfe (`th[data-pr]`) und Spaltenköpfe mit `data-pc` bekommen ihr Zeichen von `crossTable`.

### Einklappen und Merken

- `<h2 data-fold="…">` klappt die Box zu, `<div class="fsec"><h3 data-fold="…">` nur den Abschnitt; der Zustand steht
  unter `zu:<Schlüssel>` (`applyFolds` über einen MutationObserver auf `#main`).
- Kästen, die beim Aufklappen erst laden (Speicherplatz, Werte, Effort Levels, Showdown-Text, Raids), merken ihren
  Zustand je Kasten (`diskOpen`, `stOpen`, `elOpen`, `elTeamOpen`, `sdOpen`, `raidOpen`, `combosOpen`, `ttOpen` und
  ähnliche).

### Marken und Team-Leiste

- Marken: im Team, gefangen (`/api/gefangen`), Favorit. Der Pokéball wechselt bei jedem Klick: nicht gefangen, gefangen,
  schillernd (`/api/schillernd`, `ball()`), wieder nicht gefangen. `redrawMarks()` zeichnet sie überall neu, ohne die
  Seite aufzubauen. α (`alphaBtn`, `/api/alpha`): bündig über dem Pokéball, nur für mögliche Alphas des Spiels; setzt
  auch gefangen.
- Karten der Liste: unter dem Bild eine Zeile (`acts`) mit Team-Häkchen, Stern und Pokéball; gesetzte Marken sind immer
  zu sehen, die übrigen Knöpfe beim Hovern, alles an derselben Stelle. Ins Team geht es über das Häkchen, bei vollem
  Team mit der Wahl, wen es ersetzt (`favswap`). `favStar(id)`: Stern an Team-Karten und Vorschlägen.
- Favoriten je Spiel (`/api/favoriten`): ☆ auf Karten und der Detailseite; ein Klick auf einen leeren Platz bietet sie
  zur Wahl an.
- Team-Leiste (`#dock`): Karten und Vorschläge lassen sich auf einen Platz ziehen, Plätze untereinander tauschen. Auf
  der Karte ist sie beim Betreten zugeklappt (`MAPFOLD`), die gemerkte Einstellung bleibt.

### Fehler und Hinweise

Leitsatz: lieber melden als raten. Ein Fehler darf nicht aussehen wie „keine Daten“.

- `api()` wirft bei jeder Antwort, die nicht 2xx ist, und bei einer Antwort 200, die sich nicht als JSON lesen lässt.
  Der Fehler trägt `status`; 404 heißt „gibt es hier nicht“ und ist kein Fehler.
- Über der Ansicht steht `#hinweise` (`hinweis`, `drawNotes`): eine Zeile je Ursache, gleiche zählen hoch, ein Wechsel
  der Ansicht räumt ab (`route`), das Kreuz blendet aus.
- Beim Laden eines Teils: `.catch(teil("Was fehlt", Ersatzwert))`. Die Ansicht zeichnet mit dem Ersatzwert weiter und
  nennt den Teil. Beim Speichern: `.catch(ungespeichert(zurück))` nimmt die Anzeige zurück und sagt es.
- Antwortet der Server, konnte aber einen Teil nicht lesen, trägt die Antwort die Kopfzeile `X-Pokedex-Fehler`
  (`[[Stelle, Art], …]`, höchstens fünf). `api()` sammelt sie in einer Zeile mit Verweis auf Einstellungen, Fehler.
- Was nirgends abgefangen wird (`unhandledrejection`), erscheint ebenfalls als Hinweis.
- Stellen, die ihren Fehler schon selbst anzeigen (Speicherplatz, Verbindungstest, Sicherung einlesen, `alert` beim
  Ziehen), bleiben, wie sie sind: kein zweiter Hinweis.

### Stand, Version und Neuigkeiten

- Während eines Abgleichs fragt die Kopfzeile alle 5 Sekunden `/api/stand` ab (`syncPoll`; Version, `has_data`, der
  Lauf in wenigen Feldern). Meldet der Server das Ende, verschwindet „Abgleich läuft“ sofort; danach lädt die Seite
  einmal `/api/meta`. Andere Zeitgeber für den Stand gibt es nicht, außer dem Protokoll in den Einstellungen.
- Die Seite merkt sich die Version beim Laden (`LOADED_VER`); meldet der Server später eine andere, lädt sie neu.
- Die Version steht rechts neben dem Ansicht-Knopf; ein Klick zeigt alle Versionen (`NEUIGKEITEN` in `app/sources.py`,
  geholt bei Bedarf über `/api/neuigkeiten`). Nach einem Update erscheint einmal ein Hinweis mit dem Eintrag der
  Version; der Browser merkt sich die gesehene Version (`px.version`). Beim ersten Besuch gibt es keinen Hinweis.

## Ansichten

### Liste

- Karten mit Bild, Mini-Netz und Marken (`monCard`, dritter Parameter `extra`: eine eigene Zeile). Hover-Karte
  (`glanceHtml`): Angriff (bester eigener Typ je Ziel), Verteidigung (beide Typen), „gut einzusetzen gegen“ (trifft ×2
  oder mehr, steckt höchstens ×½ ein); lädt fehlende Pokémon einmal nach (`HCLOAD`).
- Typ-Duell (`duel()` in JS und `abfragen.duel`): austeilen = bester eigener Typ gegen den Zieltyp, einstecken =
  Zieltyp gegen beide eigenen Typen. Klar stark: ×2 und höchstens ×½; stark: ×2 und ×1; schwer: ×2 einstecken und
  höchstens ×1 austeilen. Der Filter „stark gegen“ nutzt dieselbe Rechnung („klar“ = nur Stufe 2).
- Filter „Gebiet“ (`areaSelect`) nur bei Spielen mit Gebieten (`/api/meta`, `spiele[].gebiete`), ohne Massenauftreten.

### Detailseite

- `.dgrid` mit zwei Spalten (links Stammdaten, rechts der Rest gestapelt), am Telefon eine. Generation 1: Spezial
  statt Sp.-Angriff/Sp.-Verteidigung; `werte_alt` sagt, dass es die Werte von damals sind.
- Texte: `dexTextHtml` (Pokédex-Eintrag des Spiels, bei zwei Editionen beide), `fromHtml` (Marke „aus <Spiel>“, wenn
  der Text aus einem anderen Spiel stammt, sonst die Quelle, wenn es nicht die PokéAPI ist).
- Fundorte (`encHtml`): mit Daten aus PKHeX (`fundquelle`) Gebiet, Stellen mit Level (ab sechs Stellen gekürzt, alle
  im Hinweis), Art, Level und Alpha-Level; Spalten nur, wo ein Eintrag Daten hat; sonst die Tabelle der PokéAPI.
- Entwicklung: `evoHtml` (Raster, ein Ast je Zeile).
- Fangchance (`catchHtml`, in Legenden: Arceus `catchHtmlLA`): eigene Karte unter der Entwicklung, offen, solange das
  Pokémon nicht als gefangen markiert ist; ohne kritischen Fang und Boni, in Generation 1 und 2 und den Legenden-Spielen
  nur als Richtung (`fang_grob`). Dazu `wissenHtml` (gepflegtes Spielwissen) und `partnerHtml` (Partner-Techniken,
  Geheime Techniken in Let's Go).
- Werte `statBox` (`#stbox`, wenn `STATS_OK()`): `/api/werte`, Team-Platz `ivs`, `evs`, `ev_ziel`, `wesen` (bis
  Generation 2 `dvs`, `exp`, `exp_ziel`; Let's Go `avs`, `av_ziel`), ohne Team `statBox.tmp`.
- Effort Levels `elBox` (`#elbox`, wenn `LA()`): `/api/effort`, Team-Platz `el`, `el_ziel`, `wesen`; ohne Team ein
  Zwischenstand nur für die Seite (`elBox.tmp`). Diagramm `elChart` (Balken und Netz aus `teile`), Rechenweg
  `elTipHtml`.
- Mehr Details (`moreHtml`, `detail.mehr`): eingeklappt; Eier und EVs nur, wo das Spielprofil sie kennt.
- Formen zum Ansehen (`optikHtml`, `detail.optik`): eingeklappt unter den getragenen Items, nur bei Pokémon mit mehreren
  Formen gleicher Werte; die Standardform zuerst.
- Extras (`extrasHtml`, `detail.extras`): Knöpfe nur für schon geladene Dateien; `/shiny/<id>`, `/anim/<id>`,
  `/rufe/<id>`.
- Attacken: `moveMarks` setzt Marken für Lehrer und Beherrschung nach den Wegen; `setsHtml` zeigt die bewährten Sets
  (`sets`, `sets_gen` aus `/api/pokemon/<id>/attacken`), grau, was nicht in der Lernliste steht. „Übernehmen“ nimmt
  `vorschlag` (die vier lernbaren mit der höchsten Wertung, Status zuletzt). Eigene Auswahl: im Team in `details`,
  sonst je Spiel und Pokémon im Browser.
- Forschungsaufgaben (`researchHtml`, Legenden: Arceus, Punkte als Rechen-Tooltip), Aufträge (`requestsHtml`), Raids
  (`raidHtml`), in Colosseum/XD Crypto-Pokémon (`cryptoHtml`).
- Detailseite eines Team-Platzes: `#formsel` tauscht die Form des Platzes.
- „Zurück“ (`backLink`) führt in die Ansicht, aus der man kam.

### Team

- Mitglieder je Platz (`ids` und parallel `details` mit Level, Attacken, Item, Fähigkeit, Wesen, Tera-Typ, Werten);
  dasselbe Pokémon darf mehrfach hinein. Neue Mitglieder bekommen die Standard-Attacken (wie im Spiel die letzten vier
  Level-Attacken bis zum Level, ohne Level die ersten vier).
- Ein gespeichertes Team ändert sich auf dem Server erst mit „Speichern“ (`POST /api/teams`); bis dahin steht „nicht
  gespeichert“ in der Leiste (`dirty`), „Verwerfen“ lädt den Serverstand.
- Showdown-Text (`#sdbox`): `sdExport` und `sdImport` (ersetzt das Team nach Rückfrage); `slotExtra` zeigt Item,
  Fähigkeit, Wesen und Tera-Typ aus `plaetze` der Bewertung.
- Bewertung mit Tera-Hinweis (`ev.tera`); Effort Levels des Teams `elTeam` (`#elteam`, `/api/effort/team`, wenn `LA()`).
- Gegner und Trainer als Gegner; Schadensrechner `calcBox` im Reiter Team (`#calcbox`, `calcT`, Gegner aus `S.foes`,
  Team, Favoriten des Spiels `favs` oder eigene, Level beider Seiten), eigene Gegner `calcFoes:<Spiel>`; Ansicht
  „Übersicht“ über `/api/schaden/uebersicht` (`.dmgx`). Balken `.dbar` (kleinster Wurf kräftig, größter blass).

### Typen

- Typtabelle des Spiels; Typfilter je Tabelle (`typeFilter`: `chartPick` Zeilen der Typtabelle, `combosPick`
  Kombinationen mit allen gewählten Typen, `ttPick<d|a>` Spalten der Team-Tabellen); Zählspalten farbig (`cntTd`,
  `DEFC`, `ATTC`).
- „Mein Team“ (`chartTeam`): nur die Typen des Teams als Zeilen, dazu `teamTypeHtml` (Verteidigung und Angriff je
  Mitglied, einklappbar).
- Typkombinationen (`combosHtml`, unter der Typtabelle, aufklappbar, nicht bei „Mein Team“): Sicht `combosSicht` als
  Verteidiger (Faktoren multipliziert) oder Angreifer (bester der beiden Typen), sortierbar, Zeilen und Spalten
  markierbar (`CPIN`).

### Items

- `itemsView` (`#items`): Daten aus `/api/items?spiel=…`; Suche, Tasche und Art filtern im Browser, Bilder laden erst
  beim Scrollen. Spalten je Tasche (`COLS`): KP, AP, EP und Statusprobleme bei Medizin und Beeren (`itemFx`, aus
  Kurztext und Beschreibung des Spiels), Fangfaktor und Bedingung bei Bällen (`BALL`; in Legenden: Arceus die Tabelle
  des Servers, `hisui_baelle` aus `/api/meta`, gelesen von `ballHisui`), die Attacke des Spiels bei Maschinen.
- Bilder unter `itembild/<Nummer>`; unfertige Einträge (`unfertig`) nur mit dem Schalter. In Legenden: Arceus
  Rezepte mit Haken (in `gefunden` unter Karte `rezept`).

### Karte

- Große Karte (`mgView`, `#karte/mg/<Karte>`, `/api/mapgenie`, Kacheln `/mgkachel/<Spiel>/<Karte>/<z>/<x>/<y>`): eigene
  Kachelanzeige (Web-Mercator), gebrochener Zoom (Kachelstufe `tz()`, Kacheln per CSS skaliert), Regler `#mgz`, Mausrad
  in halben Stufen. Nur Kacheln innerhalb von `bounds`; `#mgwarn` erklärt fehlende Kacheln (`kacheln` in der Antwort).
  Kachelebene `.mgtiles`; beim Zoomen bleibt das alte Bild in `.mgold`, bis alle neuen Kacheln da sind; `.mgload` zählt
  offene Kacheln, danach lädt der Browser Nachbarn und die Stufen ±1 vor. `#mgstock` zeigt den Vorrat. Bildebenen nur im
  sichtbaren Bereich.
- Einstieg je Karte in `MGSTART` (Zahl: Stufen näher als „ganze Karte im Bild“; als Liste mit der Mitte in Anteilen von
  links und von oben; Schlüssel `spiel/karte`, `/karte`, Spiel), erste Karte in `MGFIRST`, Karten nur für ein Spiel in
  `MG_EDITION`.
- Punkte aus einer Datenbank (`d.punkte` aus `mapgenie.merge`): `t` "mg" (Ort von Map Genie, vielleicht mit `o` und
  `drin` aus den Spieldaten), "ob" (nur Spieldaten), "sp" (Spawnpunkt); Kategorien mit `art` zeigen das Symbol der
  Einzelkarten. Punkte bringen `pk`/`it` mit (Bilder in der Seitenleiste). Beschreibungen über `mgMd` (Markdown,
  Feldnamen deutsch über `MGWORDS`, Werte über `MGVALS`).
- Ebenen: Gruppen in der Seitenleiste `.mgside` (Details oben fest, Ebenen darunter), offene Gruppen in `mgOpen`,
  sichtbare Ebenen je Karte in `mgEbenen3:<Spiel>/<Karte>`; am Anfang nur Orte, Schnellreise und Lager, zusammen
  höchstens 150 Punkte (`mgStartHide`). Suche auch in ausgeblendeten Ebenen; „Gehe zu“ und `#karte/mg/<Karte>/<Ort>`
  springen zu einem Ort, `#karte/mg/<Karte>/k:<Kategorie>` zeigt nur diese Ebene.
- Gefunden: Rechtsklick (`/api/gefunden`, ausblenden mit `mapGotHide`); Schlüssel von Map Genie, alte Marken am eigenen
  Symbol gelten mit (`isGot`).
- Übersicht mit Bildern (`#mgheat`, `heatCells`): Raster fest auf der Karte je ganzer Zoomstufe; wer im Elternfeld
  gezeigt wurde, bleibt im Teilfeld. Auf der Gesamtkarte „Häufig auf dieser Karte“.
- Karten der Quelle „ironmon“ wandelt `mgConvert` beim ersten Öffnen in Kacheln um (Stufe für Stufe halb so groß, je
  bis 60 Kacheln als Base64 an `/api/kacheln/umwandeln`), Meldung mit Fortschritt in `#mgwarn`.
- Einzelkarten von Legenden: Arceus (`mapView`, `#karte/<Karte>/<Form>`, `/api/karte/<Karte>`): Welt 2048 px =
  Spielkoordinate × 2; Kacheln `karten/<Karte>/<z>-<x>-<y>.png` (Zoom 0–2), Punkte behalten ihre Größe (`--inv`). Mit
  Form werden ihre Punkte gelb hervorgehoben und die Ansicht passt sich ihnen an. Symbole (`.mobj`, Zeichen in `MOBJ`)
  sind Ebenen in Gruppen (`MGROUPS`, gemerkt in `mapHide`, „alle“ und „keine“). Filter Tageszeit und Wetter (`mapZeit`,
  `mapWetter`; Anteil je Bedingung `c`, Tageszeit × 9 + Wetter), Punkte ohne Pokémon unter der Bedingung sind blass.
  Übersicht `mapHeat` (Felder zu 64 Spieleinheiten, je Feld bis zu drei Pokémon) mit den häufigsten Pokémon des Gebiets
  und dem Vergleich aller Gebiete. Ziehen beginnt überall (ab 4 px, danach zählt kein Klick); der Ausschnitt bleibt beim
  Filtern (`MAPPOS`); die Daten bleiben im Browser (`MAPCACHE`). Jubeldorf (`jubilifevillage`) hat statt Kacheln ein
  Bild (`bild.png`).
- Gebiete (`areasView`, `#karte/gebiete/<Ort>`, `/api/gebiete`): links die Orte mit „noch nicht gefangen / alle“, rechts
  das Bildergitter nach Methode; Spiele ohne Karte landen unter „Karte“ direkt hier. Ort je Spiel gemerkt
  (`gebiet:<Spiel>`), Filter `gebietFehlend`.
- Auswahl mit Bildern (`.pick`): Knopf, darunter Suche und Liste aus echten Links; Enter nimmt den ersten Treffer.

### Was fehlt mir noch und Sammelobjekte

- `missingView` (`#fehlt`, `/api/fehlt?spiel=…&edition=…`): Standard-Karten (`monCard` mit `extra`), Gruppen nach `weg`
  in der Reihenfolge von `WEG` (wie `abfragen.WAYS`), darunter der Weg als Marke, alle Wege im Hinweis. Knöpfe `#fseg`
  filtern, Edition je Spiel im Browser (`edition:<Spiel>`). Der Pokéball auf einer Karte (`.fmon .gball`,
  `data-act="caught"`) macht sie
  blass; aus der Liste fällt sie erst beim nächsten Öffnen.
- Sammelobjekte (`collectView`, `#sammeln`, `/api/sammeln?spiel=…`): Tabelle mit Balken (`.cbar`) und Links auf die
  Karte mit nur dieser Ebene.

### Vergleich, Initiative und Kampf

- Vergleich (`compareView`, `#vergleich/<A>/<B>`, „-“ = leer): zwei Suchfelder mit Schnellwahl (gemerkte `cmpMerk`,
  bis 8, und Favoriten), Artwork und Netz wie die Hover-Karte, Werte mit Unterschied, „Kurz gesagt“ (Initiative Lv 50,
  bester Eigentyp-Faktor, physisch/speziell, Schwächen), Verteidigung je Angriffstyp, Fähigkeiten, Attacken (nur A,
  beide, nur B).
- Initiative-Liste (`speedView`, `#initiative`): Spalten minimal, neutral, maximal, maximal mit Wesen; Team-Zeilen
  (`tr.mine`) mit eigenem Wert an ihrer Stelle; in Legenden: Arceus mit `laStat` und `EL_FAKTOR`. Einstellungen in
  `speed`.
- Kampf (`battleView`, `#kampf`, wenn `BATTLE()`): Der Reiter „Karte“ heißt „Kampf“, `#karte` leitet dorthin, aus
  „gefangen“ wird „im Kader“ (ohne Schillernd, ohne Fangchance). Doppelkampf-Bewertung aus `/api/team/doppel`, `calcBox`
  (Schadensrechner, `/api/schaden`, Einstellungen in `calc`, Gegner aus Smogon, Team oder eigene), `logBox`
  (Kampftagebuch, `/api/kampftagebuch`, Auswahl `LOGPICK`), `usageBox` (Tabelle aus `/api/smogon`, Anzahl `usageN`),
  „Gefahr für“ und „Antwort“ über die Typtabelle, „Top 6 als Gegner“ setzt `S.foes`.

### Raids und Aufträge

- Raids (`raidsView`, `#raids/<Sterne>`, wenn `RAIDS()`, Reiter neben der Karte): `/api/raids`, Konter und Gefahr aus
  dem Team.
- Aufträge (`requestsView`, `#auftraege`, wenn `REQ_GAME()`): Suche, Offen/Alle/Erledigt, Haken `reqdone` (`toggleReq`,
  `/api/gefunden` mit Karte `auftrag`), 📍 springt zum Ort auf der Karte.

### Einstellungen

- `foldBoxes` macht aus jedem Kasten ein `details.fold` mit Leiste oben (`.jump`, „alle auf“, „alle zu“); zugeklappte
  merkt sich `setShut`. Zeiten mit `deTime` (deutsch, Zeit des Browsers), Protokollzeilen mit `logLocal`.
- Abgleich: oben der Zeitplan (Abstand in Tagen und feste Uhrzeit, `uhrLocal`/`uhrUtc` rechnen zwischen Ortszeit und der
  Weltzeit des Servers um; darüber der nächste Lauf), dann `details.sub` (Quellen mit farbigen Zählern `.badge`,
  Verbindungstest mit Fortschrittsbalken, Protokoll); „kopieren“ und „herunterladen“ stehen im Kopf (`.slinks`), Knöpfe
  dort klappen nicht. Ein laufender Verbindungstest wird beim Öffnen wieder aufgenommen.
- Sicherung: `/api/export` lädt herunter, `/api/restore` ersetzt alle eigenen Daten (vorher `vor-einlesen-…` in
  `sicherung/`); Spieldaten als ZIP unter `/api/spieldaten`. Speicherplatz (`diskBox`): `/api/speicher` erst beim
  Aufklappen von `#diskd` (anfangs zu); Balken je Teil im Verhältnis zum Ganzen.
- Fehler: die Liste des Servers (`/api/fehler`), eingeklappt, mit Anzahl; „leeren“ ruft `/api/fehler/leeren`.
- „Zu erledigen“: „Auftrag kopieren“ (`/api/aufgabe`), „Antwort einlesen“ mit Vorschau (`/api/antwort`, erst mit `dry`),
  „herunterladen“ als CSV.
- Seite untersuchen: Lesezeichen, das Seiten, deren Karten erst im Browser laden, als Datei liest.
