# Roadmap

## 0.48.5 (12.11.2026)

- Schadensrechner: `.seg.cslots button.on` mit `--hcbg`; Zeilenumbruch (`.brk`) vor „gegen …“

## 0.48.4 (12.11.2026)

- Proben für Shiny-Sperren: Bulbapedia „List of unobtainable Shiny Pokémon“, „Shiny-locked“, „Shiny Pokémon“ und PokéWiki
  „Schillernde Pokémon“, „Shiny-Lock“ (Wikitext). Nächster Schritt: Leser je Spiel mit drei Stufen (fangbar, nur per Übertragung,
  gar nicht); der Pokéball lässt „schillernd“ nur dort aus, wo es das im Spiel auf keinem Weg gibt

## 0.48.3 (12.11.2026)

- Schadensrechner: Regel `#calc .seg button.on` aus 0.46 entfernt. Sie setzte eine schon in 0.43 erledigte Rückmeldung erneut um
  und überschrieb Ansicht und Angreifer; es gilt wieder `.seg button.on` (kräftig) und `.seg.cslots button.on` (ruhiger)

## 0.48.2 (12.11.2026)

- `_optik`: Formen aus `formen_fehlen.json` (404 bei den PokéAPI-Sprites, z. B. `414-sandy`) weglassen; bleibt nur eine Form, kein Kasten

## 0.48.1 (12.11.2026)

- MewMaps verlinkt die Karten nur auf Google Drive/Photos (darum 0 Bilder im HTML); neue Proben laden die Inselkarten
  (SM und USUM) und lesen die Größe. FrontierNav ist eine Skript-Seite: Proben der Skripte suchen die Datenadressen

## 0.48.0 (12.11.2026)

- Auswertung des Verbindungstests vom 12.11. (Kartenbilder): Serebii hat für Kalos und Alola keine Bildkarte, X/Y, SM und
  USUM hatten keine Karte. Bulbapedia `Kalos XY.png` 1032×676 (Seitenverhältnis wie `XY-Map Kalos.png` 320×210 im
  PokéWiki), Inselkarten Alola dort 654–752 px; PokéWiki `USUM-Map …` 270×270 je Insel, `USUM-Global-Map …` 400×240;
  Fan-Karten (zombiecrisis) 4414 px mit Beschriftung; MewMaps, japanische Übersicht und FrontierNav ohne Bilder im HTML
- Kalos: Orte aus `Vorlage:XY-Map Kalos` (54 Flächen, `pokearth.pw_areas`), Bild groß von Bulbapedia (`pw_map`, nur bei
  gleichem Seitenverhältnis); Pokémon je Ort über die deutschen Ortsnamen (`_pokearth_mons`)
- Alola: Entscheidung offen (PokéWiki-Inselkarten, Fan-Karte oder Bulbapedia-Inselkarten)

## 0.47.12 (12.11.2026)

- `.sp` streckt sich über die Kartenhöhe, Bild mittig darüber, Knöpfe unten; Bild `top:5px`, Knöpfe `top:1px`; α-Hover weiß

## 0.47.11 (12.11.2026)

- Bild `top:7px`, Knopfzeile `top:3px`; in Spielen mit Alphas ein unsichtbarer Platzhalter statt des α-Knopfs
- Geprüft: 228 von 248 Formen in LA gibt es als Alpha (PKHeX-Spieldaten, z. B. Massenausbrüche); ohne Alpha sind nur Legendäre/Mysteriöse und Alola-Vulpix/-Vulnona

## 0.47.10 (12.11.2026)

- `.mon .acts` mit z-index über `.spr` (seit `top:4px` überdeckte das Bild etwa 40 % der Knopffläche)

## 0.47.9 (12.11.2026)

- `#pick`: Hintergrund `--hcbg`; `flex:1` nur für den Namen, nicht für die Typ-Schilder

## 0.47.8 (12.11.2026)

- Bild in den Karten 4 px tiefer (Entscheidung 12.11.2026; 6 und 8 px waren zu tief)

## 0.47.7 (12.11.2026)

- Favoriten-Karten ohne ⇄, Reihenabstand 8 px wie die Liste (Entscheidung 12.11.2026, ersetzt die 11 px aus 0.47.1)

## 0.47.6 (12.11.2026)

- Bild 6 px tiefer (8 px war zu viel, Entscheidung 12.11.2026); Häkchen bei vollem Team öffnet die Ersetzen-Wahl (`favswap`)

## 0.47.5 (12.11.2026)

- Karten ohne „+“-Knopf (Entscheidung 12.11.2026); Häkchen grau, im Team grün. „Noch einmal ins Team“ bleibt auf der Detailseite

## 0.47.4 (12.11.2026)

- Haken „Im Team“ auf Karten trägt die Pokémon-Nummer; `teamChanged` zeichnet die Marken auch im Team-Reiter neu
  (die Favoriten-Karten behielten sonst den alten Platz und den Haken)

## 0.47.3 (12.11.2026)

- Sprite der Pokémon-Karten 8 px statt 5 px tiefer

## 0.47.2 (12.11.2026)

- Verbindungstest mit den Kandidaten der Recherche „Kartenalternativen für Kalos und Alola“: Fan-Karten Kalos
  (4414×2924) und Alola (4414×3144) als PNG, MewMaps Sonne/Mond und USUM (Insel- und Gebietsbilder), japanische
  X/Y-Kartenübersicht mit Bildkarte; aus der Cloud nicht erreichbar, daher erst über die Proben bewertbar

## 0.47.1 (12.11.2026)

- Favoriten-Reihen wieder 11 px, ⇄ wieder 24 px (Entscheidung 12.11.2026: so war es richtig)

## 0.47.0 (12.11.2026)

- Auswertung des Verbindungstests vom 12.11.: Pokédens deckt nur die Naturzone ab; den Inhalt aller Nester liefert
  schon das PKHeX Raid Plugin (`Nests/RaidTables.cs`, je Tabelle Art, Sterne, Form, Gigadynamax für Schwert und
  Schild). `raidnester.tables`, `den_text`; je Nest normaler und seltener Strahl, deutsche Namen aus pokeapi.db, die
  Pokémon erscheinen als Bilder im Kartenpunkt. Gamer Guides lieferte keine Punkte (GeoJSON leer), Pokémon Database 404
- PokéWiki-Bildkarten: es gibt `XY-Map Kalos`, `USUM-Map Alola` (je Insel), `ORAS-Map Hoenn`; die Bilder sind nach den
  Flächen nur etwa 312×200 bzw. 384×256 Pixel groß (Touchscreen-Karten). Neue Proben fragen die Größe aller Bilder
  dazu ab und bei Bulbapedia die Regionskarten (`Kalos XY.png`, die Inselkarten Alolas, `Sinnoh BDSP.png`, `UGMAP.png`
  u. a.); danach Entscheidung, welche Karte X/Y, SM und USUM bekommen

## 0.46.0 (12.11.2026)

- Rückmeldung vom 12.11. zur Oberfläche: ein Klapp-Pfeil für `details>summary` und `[data-fold]` (CSS-Dreieck, gleiche
  Größe und Farbe, dreht beim Öffnen), Klapp-Titel einheitlich `--ink-hi`; Sprite der Pokémon-Karten 5 px tiefer;
  Favoriten-Reihen mit 8 px Abstand (⇄ kleiner); Forschungsstufen in festen Spalten (`td.rst`)
- Gegen Gegner: `✕ entfernen` im Kopf der Trainerwahl, `#foeclr` wird in `matchup()` ein- und ausgeblendet, Ecke der
  Tabelle „Dein Team“; `crossTable(…, marks=false)` ohne Markierungszeichen für die Typtabellen
- Aufträge: Erklärung als `details.reqinfo`, Tabellen `vlines`; Einstellungen: Speicherplatz als `#diskd` in der Sicherung

## 0.45.0 (12.11.2026)

- Speicherplatz in den Einstellungen: `abruf.disk_usage` zählt den Datenordner (je Eintrag Bytes und Dateien, `mapgenie`
  nach `kacheln/<Quelle>/<Karte>` aufgeschlüsselt, Kleines als „Sonstiges“, freier Platz per `shutil.disk_usage`), fünf
  Minuten zwischengespeichert; `/api/speicher` (`?neu=1` zählt neu). Das Feld ist zu, bis man es aufklappt, und zählt erst dann

## 0.44.1 (12.11.2026)

- Verbindungstest für Karten von X/Y, Sonne/Mond, Ultrasonne/Ultramond (bisher keine) und Einall, ORAS, BDSP (bisher nur
  die grobe Serebii-Übersicht): Vorlagen `XY-Map Kalos`, `SM-Map Alola`, `USUM-Map Alola` u. a. im PokéWiki (Bildkarten mit
  Flächen je Ort, deutsche Namen), Kategorie `Game maps` im Bulbapedia-Archiv, Regionskarten von Pokémon Database; die
  Antworten bleiben in den Proben für die Auswertung

## 0.44.0 (12.11.2026)

- Auswertung der Kartenrecherche vom 12.11. (21 Spielgruppen): brauchbar sind die HGSS IronMON Map und die Raid-Nester
  aus dem PKHeX Raid Plugin; Gamer Guides und Pokédens erreicht nur der Heimserver (Verbindungstest, Daten mit `keep`)
- `app/ironmon.py`, `abruf._ironmon`, `mapgenie/<Spiel>.im.json`: Johto und Kanto als ganze Welt (WebP 13712×5893 und
  9736×6994), Trainer (Klasse eingedeutscht, Level) und Items (sichtbar, versteckt, TM) aus TypeScript, je Ort ein Punkt.
  WebP kann der Server ohne Bibliothek nicht zerlegen: der Browser wandelt das Bild beim ersten Öffnen in PNG-Kacheln um
  (`mgConvert`, `/api/kacheln/umwandeln`, `abruf.tile_upload` prüft Karte, Lage und PNG); Test: Johto 1733 Kacheln in
  gut 30 Sekunden, 114 MB
- `app/raidnester.py`, `abruf._raidnester`, `mapgenie/<Spiel>.rn.json`: 276 Raid-Nester auf den Karten des Plugins
  (Naturzone, Insel der Rüstung, Schneelande; pkTeraRaid rechnet die Schneelande falsch um). Insel der Rüstung und
  Schneelande haben damit eigene Karten vor Galar
- Offen: Inhalt je Nest (Pokédens oder die Nest-Tabellen des Plugins), Karten für X/Y, Sonne/Mond, Ultrasonne/Ultramond
  (keine Karte) und bessere für Einall, ORAS, BDSP, Orre (nur grobe Serebii-Übersicht)

## 0.43.0 (12.11.2026)

- Karten (`mgView`): gebrochener Zoom (Kacheln der nächsten Stufe, per CSS skaliert), Regler, Mausrad in halben Stufen,
  Startausschnitt je Spiel (`MGSTART`), untere Grenze je Sitzung, wenn eine Stufe keine Kachel lädt (Pokopia); Bildebenen
  nur im sichtbaren Bereich; Standard-Ebenen nur Orte, Schnellreise und Lager (`mgEbenen2`)
- Kartenpunkte: `mapgenie.text_de` (Namen, häufige Sätze, Überschriften), `abfragen.point_pics` (Pokémon und Items als
  Bilder, `pk`/`it`); Übersicht mit Bildern und „Häufig auf dieser Karte“ auf der Gesamtkarte
- RankedBoost nur noch Let's Go und Feuerrot/Blattgrün (`rankedboost.GAMES`); Karmesin/Purpur und Z-A zurück zu Map Genie
- `spiel_form.dex`/`dexk` (`importer.DEX_KURZ`, `importer.VERSION` 25): Nummer aus dem ersten Regional-Dex, in dem die Art
  steht (vorher das Minimum über alle Dexe); Sortierung `nr` je Dex, neu `nat`
- Trainer von Ortsseiten (Kategorie „Ort aus einem Hauptspiel“, Rolle Trainer, `pokewiki.dedupe_teams`); Schadensrechner
  als Unterabschnitt von „Gegen Gegner“
- Oberfläche: Klapppfeile vor dem Text, Effort-Diagramm im Stil der Basiswerte mit Summe, Favoriten-Haken setzt ins Team,
  Rückgängig beim Entfernen eines Favoriten, Wirkung/Beschreibung markieren nur die Zeile (`nohc`), „Gegen Gegner“ ohne
  Zeilen-Pins (`data-rowpin="0"`), Aufträge mit Kartenspalte; Aktiv-Markierung der Knöpfe wieder wie vorher, nur die
  Teamplätze eigen
- Offen: freie englische Sätze in Kartentexten, bessere Karten für Kalos und Alola

## 0.42.0 (12.11.2026)

- Trainerteams aus dem PokéWiki (`abruf._trainer`, `pokewiki.trainer_teams`, Vorlagen `Team/Kopf` und `Team/Zeile`,
  Kategorien Arenaleiter, Top Vier, Champ, Rivale; `pokewiki_trainer.json`, alle 7 Tage neu), Tabelle `trainer`
  (`importer.VERSION` 24), `/api/trainer` (`abfragen.trainer_list`, Erweiterungen zeigen ihr Hauptspiel)
- Reiter Team, „Gegen Gegner“: Auswahl „Trainer als Gegner“ (eine Rolle zur Zeit, nach Level, Rückkämpfe ausgeblendet,
  Suche über alle Rollen); `team_matchup` nimmt `gegner_attacken` (Typen der Schadensattacken), der Schadensrechner
  das Level je Gegner (`verteidiger_details[].level`)
- Blaubeer-Missionen (PokéWiki, Seite Blaubeer-Punkte, `pokewiki.bbq_missions` mit rowspan), Tabelle `blaubeer`,
  im Reiter Aufträge für Karmesin/Purpur und die Erweiterungen (ohne Haken, weil wiederholbar)
- RankedBoost für Karmesin/Purpur und Legenden: Z-A
- Verbindungstest: Trainerteams, Blaubeer-Missionen, Kategorie Arenaleiter
- Recherche bessere Karten: Auftrag an einen Recherche-Agenten vorbereitet (nicht im Repo)
- Offen: Inhalte der Raid-Nester in Schwert/Schild, Aufträge 95 bis 122 auf der Karte von Legenden: Arceus

## 0.41.0 (12.11.2026)

- Aufträge für mehrere Spiele (`abfragen.QUEST_GAMES`: Legenden: Arceus, Legenden: Z-A, Mega-Dimension teilt mit Z-A):
  Nebenmissionen Z-A von BisaFans (`bisafans.ZA_REQUESTS`, `merged_requests`), Haupt- und Dimensions-Missionen aus dem
  PokéWiki (`pokewiki.za_missions`, Dimensions-Missionen als 101 …, angezeigt als D1 …); `importer.VERSION` 23.
  Kategorien von Map Genie über `quest_kind`/`quest_nr` („Request“, „Side Mission“, „#N:“, „Side Mission N:“)
- Neue Kartenquelle Serebii PokéEarth (`app/pokearth.py`, `abruf._pokearth`, `mapgenie/<Spiel>.se.json`): Regionsbild als
  Bildebene (`kacheln/se/<Region>.png`), je Ort ein Punkt; die Pokémon je Ort aus den Fundorten des Spiels
  (`abfragen._pokearth_mons`, englischer Ortsname → PokéAPI → deutsch). Mit Probedaten: HG/SS 39 von 45 Orten mit Pokémon,
  BDSP 49 von 68, ORAS 21 von 53 (die PokéAPI kennt in ORAS wenige Fundorte)
- `mapgenie.SHARE`: Insel der Rüstung und Schneelande der Krone zeigen Galar
- Verbindungstest: Bildkarten von Serebii für Einall, Kalos, Alola, Orre
- Stand je Spiel (12.11.): jedes Spiel außer Champions hat eine Karte. Aufträge gibt es nur in Legenden: Arceus und Z-A;
  vergleichbar wären noch die Blaubeer-Aufgaben in der Indigoblauen Scheibe (offen)

## 0.40.0 (12.11.2026)

- Aufträge und Karte: Haken unter denselben Schlüsseln (`auftrag|Nr`, `mission|Nr`); Punkte der Kategorien „Request“ und
  „Story Mission“ tragen `aq` (`abfragen._quests_de`) und den deutschen Text von BisaFans. `request_list` liefert dazu die
  Hauptmissionen und je Nummer den Ort auf der Karte (`abfragen.quest_points`, 📍 im Reiter Aufträge)
- Geprüft (Daten 12.11.): Map Genie hat 94 Aufträge ohne Lücke und Doppel, BisaFans 122 (95 bis 122 aus dem Update, nicht
  auf der Karte); 17 Aufträge ohne Ort bei BisaFans verweisen auf die Karte
- Hauptmissionen aus der Komplettlösung von BisaFans (`bisafans.la_missions`, Tabelle `mission`, `importer.VERSION` 22)
- Karte: `mapgenie._dedupe` legt gleiche Punkte an derselben Stelle (3 Weltpixel) zusammen; eigene Symbole gleicher Art
  vereinen ihre Items. Spawnpunkte und verschiedene Namen bleiben (Legenden: Arceus 5905 → 5863 Punkte)
- Neue Quelle RankedBoost (`app/rankedboost.py`, `abruf._rankedboost`, `mapgenie/<Spiel>.rb.json`): Fundortseite → JSON
  `megamap-*.json` (zuletzt bekannte Adresse als Ersatz) → je Ort ein Punkt und ein Ortsbild (webp, `kacheln/rb/<Karte>/<Nr>.webp`,
  `/mgbild/…`). Keine Kacheln: die Karte legt die Bilder an ihre Stelle (`d.bilder`, `bild_z`)
- Offen: Aufträge 95 bis 122 auf der Karte (Ort von BisaFans ohne Koordinaten), SwSh-Fundorte von Serebii, Trainer-Teams
  als Gegner, Raid-Nester, deutsche Texte für Z-A und Karmesin/Purpur, RankedBoost für weitere Spiele (SV-JSON bekannt)

## 0.39.0 (12.11.2026)

- Ladezeiten: `route` leert beim Wechsel der Ansicht sofort (`VIEW`), `body.busy` zeigt nach 120 ms einen Balken;
  `loadReqDone` einmal je Seitenaufruf. Server mit HTTP/1.1 (offene Verbindungen, `timeout` 60 s, `Connection: close`
  bei POST-Fehlern), zusammengeführte Karten bis zu 12 im Speicher (`abfragen.MERGED_MAX`), JSON und gzip einmal je Karte
  (`server._packed`, `_GZ`), Vorbereiten aller Karten eines Spiels, sobald die Liste kommt (`_prewarm`)
- Kacheln: fehlende Kacheln mit Datum in `mapgenie/kacheln/fehlt.json` (30 Tage), Stand des Vorrats in `vorrat.json`;
  ist eine Karte ganz durchgesehen, fragt `mg_tile` für die Oberfläche nicht mehr nach. Einzelne 403 bei Map Genie werden
  bei einer Sperre wieder vergessen. Der Vorrat wartet außerhalb der Sperre. 404 bei Kacheln eine Stunde im Browser
- Einklappen allgemein: `data-fold` an `h2` (Box) oder `h3` in `.fsec` (Abschnitt), Zustand `zu:<Schlüssel>`
- Detailseite: rechte Spalte ein Stapel (der Abstand zu „Entwicklung“ hing an der Höhe links); `statNet` für Werte und
  Effort Levels im Stil von `radar`
- `crossTable`: Markierzeichen auch an Zeilenköpfen und an Spaltenköpfen mit `data-pc`; Zellen ohne `data-c` markieren
  nur die Zeile
- `abruf.mg_maps`: Schwester-Edition mit eigener Karte (Gold/Silber, DittoBase) vorn, vom Hauptspiel nur andere Quellen
- `pokewiki.plain`: `{{Item|…}}` auch groß geschrieben; `importer.VERSION` 21

## 0.38.0 (12.11.2026)

- Neue Quelle DittoBase (`app/dittobase.py`, `abruf._dittobase`, `mapgenie/<Spiel>.db.json`): Kristall. Die Kartenseite
  bringt im React-Server-Datenstrom (`self.__next_f.push`) die ganze Welt mit: Blöcke je Karte, Kachelsätze (PNG zu 16
  Blöcken je Zeile, Block 32 Pixel), Lage der Karten in der Oberwelt, Punkte (Schritt 16 Pixel) und wilde Pokémon je Karte.
  Es gibt keine fertigen Kacheln; `dittobase.render_tiles` zeichnet sie beim Abgleich (Stufen Z1 − 5 bis Z1 + 1, nächster
  Nachbar) nach `mapgenie/kacheln/db/<Spiel>/`, neu nur bei geänderten Daten (`stand.json`)
- `app/png.py`: PNG lesen (8 Bit, Palette auch 1/2/4 Bit, alle Filter) und schreiben mit zlib, ohne Abhängigkeit
- Häuser, Höhlen und Etagen: `dittobase.anchors` sucht über die Türen den Eingang in der Oberwelt; die Punkte stehen dort im
  Kreis, „In: Höhle → Etage“ im Text. Namen in «…» übersetzt `mapgenie.merge` mit der Datenbank (Pokémon, Items)
- IGN: alle Punkte über die GraphQL-Abfrage der Seite (`ign.query`, `MapMarkersMultiple` bei mollusk.apis.ign.com, POST);
  `sources.request`/`fetch` und `_Source.get` nehmen dafür `data` (JSON). Ohne Antwort bleibt es bei den Punkten der Seite
- `mapgenie.QUELLE`: Punkte tragen die Quelle ihrer Karte
- Verbindungstest: IGN-Abfrage je Spiel, DittoBase je Spiel (Kartendaten?), zwei Kachelsätze (PNG-Kopf),
  RankedBoost-Kartendaten (Let’s Go, als Probe behalten) und Kartencode, PokéTools-Skripte (Stellen mit „tile“)

## 0.37.1 (12.11.2026)

- Verbindungstest: `abruf.tile_patterns` sucht Kachelmuster nur rund um „{z}“. Das alte Muster `[\w/.:-]*\{z\}…` über
  die ganze Seite lief bei langen Wortketten (RankedBoost HG/SS, rund 6 MB) quadratisch, hielt den GIL und damit den
  Webserver und alle anderen Abfragen fest; der Wächter brach dann 110 Abfragen ab

## 0.37.0 (12.11.2026)

- Neue Quelle BisaFans (`app/bisafans.py`, `abruf._bisafans`, `bisafans.json` im Datenordner): die Nebenmissionen von
  Legenden: Arceus von einer Seite. Der Leser arbeitet auf Textzeilen (Überschrift „Nebenmission N: Name“, Abschnitte
  Beschreibung, Aufgabe, Wo, Lösung, Belohnung) und hängt nicht an der HTML-Form
- Tabelle `auftrag` (`importer._derive_auftrag`) mit den Arten aus dem Hisui-Pokédex, deren Name im Text steht;
  `/api/auftraege`, Reiter „Aufträge“ (nur in Legenden: Arceus), Kasten auf der Detailseite. Erledigt liegt in
  user.db in `gefunden` unter der Karte `auftrag` (Export und Import nehmen es mit). `importer.VERSION` 20
- Verbindungstest: Probe „BisaFans, Aufträge in Legenden: Arceus“ (wird als Probe behalten)

## 0.36.0 (12.11.2026)

- Deutsche Texte je Spiel aus dem PokéWiki (`abruf._wiki_texts`, `pokewiki_texte.json` im Datenordner): Seiten aller
  Arten, Attacken und Fähigkeiten, 20 je Anfrage, alle `WIKI_TEXT_TAGE` (30) Tage komplett, neue Namen beim nächsten
  Abgleich. Gelesen werden die Vorlagen „Pokédex-Einträge“, „Atk-Beschreibung“ und „Fähigkeit/Infobox“ (Gen3 … Gen9);
  die Kürzel bleiben roh, `pokewiki.DEX_KEYS` und `ATK_KEYS` ordnen sie beim Bauen den Spielen zu (das genaueste gewinnt)
- Tabelle `spieltext` (Art, ID, Spiel, Edition, Text, Quelle): zuerst die PokéAPI, wo sie nichts hat, das PokéWiki;
  `abfragen.pick_text` nimmt das gewählte Spiel (Erweiterungen: Hauptspiel), sonst das Spiel davor, sonst das danach
- Legenden: Arceus: Forschungsaufgaben aus der Vorlage „Pokédex-Aufgaben“ (Tabelle `forschung`), Kasten auf der
  Detailseite mit Punkten je Stufe
- Verbindungstest: Probe „PokéWiki, Texte je Spiel“ meldet abgedeckte Spiele und unbekannte Kürzel; das Protokoll
  des Abgleichs nennt unbekannte Kürzel ebenfalls. `importer.VERSION` 19
- Nächster Schritt: Aufträge in Legenden: Arceus auf Deutsch

## 0.35.4 (12.11.2026)

- Oberfläche: die Abfrage des Teststands versucht es nach einem Fehler weiter (bisher blieb die Anzeige stehen)
- `abruf.diagnose`: höchstens `DIAG_PARALLEL` (6) Abfragen gleichzeitig; „Errno -3 Try again“ (DNS überlastet) bekommt
  einen zweiten Versuch; fehlende Wiki-Seiten heißen „Seite gibt es nicht“

## 0.35.3 (12.11.2026)

- `sources._read` liest mit `read1`: `read(n)` wartete, bis n Bytes beisammen waren, und umging so das Gesamtlimit
- `abruf.diagnose`: Wächter, nach `DIAG_HANG` (120 s) ohne Fortschritt endet der Test, offene Abfragen stehen als
  „hängt“ im Ergebnis

## 0.35.2 (12.11.2026)

- `sources.request(limit=…)` gibt nach Ablauf den Anfang zurück (`teil`), der Verbindungstest wertet ihn aus und behält
  ihn als Probe. Der Abgleich selbst hat weiter kein Gesamtlimit

## 0.35.1 (12.11.2026)

- `sources.request(limit=…)`: Gesamtzeit je Abfrage; `timeout` galt nur je Lesevorgang, ein tröpfelnder Server hielt den
  Verbindungstest fest. Der Test nimmt `DIAG_TIMEOUT` 20 s und `DIAG_LIMIT` 60 s

## 0.35.0 (12.11.2026)

- Verbindungstest parallel je Server (`abruf.diagnose(proben, stand)`, ein Thread je Server, Pausen aus `DIAG_PAUSE`),
  Fortschritt über `/api/diag` (`gesamt`, `fertig`, `laeuft`, `start`, `dauer`); die Oberfläche nimmt einen laufenden
  Test beim Öffnen der Einstellungen wieder auf
- Einstellungen: Zeitplan oben, farbige Zähler bei den Quellen, „kopieren“ im Kopf von Protokoll und Verbindungstest

## 0.34.0 (12.11.2026)

- Rechenweg-Tooltips für die Fangchance (`catchTip`, Zeilen tragen `faktor`, `mehr.fang_gen`) und die Initiative-Liste
  (`speedTip`; die Liste rechnet die Tooltips erst beim Hovern über `data-tip-speed="Basis:Spalte"`, weil sie über
  tausend Zeilen hat)

## 0.33.0 (11.11.2026)

- Getragene Items: `abfragen._held` nimmt das PokéWiki (Legenden: Arceus), sonst `pokemon_items` der PokéAPI je Editionsgruppe
  (Generation 3 bis 7), mit Editionen, wenn sie sich unterscheiden. Ohne Daten: Generation 2, ab Schwert/Schild (außer
  Legenden: Arceus), Z-A; Let's Go und Legenden: Arceus kennen keine getragenen Items im Kampf
- Rechenweg-Tooltips: `tipRef` (HTML in `TIPM`, Element trägt `data-tip-calc`), `partsTip` (Anteile, Summe, Formel), `dmgTip`
  (aus `grund`, `staerke`, `faktoren`, `a_info`, `d_info` von `abfragen._calc_steps`)

## 0.32.0 (11.11.2026)

- Schadensrechner: `abfragen.damage_view` mit `art` „la“ (Werte über `effort.stat`, Team-Platz `el`, Gegner Stufe 0 oder 10)
  und „lgpe“ (`schaden.stat_lgpe`, Team-Platz `avs`, Gegner 0 oder 200 AVs); `verteidiger_details` für Items der Verteidiger
  (`schaden.DEF_ITEMS`, Fokusgurt)
- `attacken.score`: Abklingzeit (Z-A) als Faktor, Wurzel aus 7 s / Abklingzeit, 0,6 bis 1,5
- Offen: Werte und Schaden in Champions (eigenes Werte-System), Freundschafts-Bonus in Let's Go, Kraft- und Tempostil in
  Legenden: Arceus, Felder

## 0.31.0 (11.11.2026)

- Werte-Diagramm `statBox` (`#stbox`) für alle Spiele außer Legenden: Arceus (Effort Levels), Let's Go (AVs), Champions und
  Pokopia: `/api/werte` → `schaden.stat_view` (Teile je Wert, Ziel-EVs, höchstens). Team-Platz `ivs`, `evs`, `ev_ziel`, `wesen`;
  bis Generation 2 `dvs`, `exp`, `exp_ziel` (Showdown schreibt dort EVs)
- Offen: Let's Go mit AVs und Freundschaft, Champions-Werte

## 0.30.0 (11.11.2026)

- `app/serebii.py`: Z-A-Attackenliste (`legendsz-a/attacks.shtml`) → `attacke_spiel.abklingzeit`; Pokédexe von Pokopia
  (`pokemonpokopia/availablepokemon.shtml`, Sprudelbecken, Event) → Tabelle `pokopia` und `spiel_form`. Der Leser schneidet an
  Links und Bildern, nicht an der Tabellenform; der Verbindungstest prüft ihn an den echten Seiten
- Schadensrechner: `schaden.calc_old` für Generation 1 und 2, `schaden.modifiers` für Item, Fähigkeit und Wetter,
  Fähigkeit der Verteidiger über `typen.ABILITY_DEFENSE`; `importer.VERSION` 18
- Offen: Abklingzeit in der Attacken-Wertung von Z-A (Stärke je Sekunde), Plus-Attacken, deutsche Namen der
  Pokopia-Spezialitäten, Felder und Fähigkeiten mit Bedingung im Schadensrechner

## 0.29.0 (11.11.2026)

- `app/ign.py`: Kartenseite von IGN → Karte wie `mapgenie.parse` (Einheitsquadrat auf der ganzen Mercator-Welt, Kacheln
  `{z}/{x}-{y}.jpg` zu 256 Pixeln, Punkte aus `__NEXT_DATA__`). Schwert/Schild (Galar) und Let's Go (Kanto)
- Karten je Quelle in eigener Datei: `mapgenie/<Spiel>.json` (Map Genie), `.pc.json` (pokemoncompletion), `.ign.json` (IGN);
  `abruf.mg_maps` fügt sie zusammen, `TILE_SRC` und `_cdn_tile` holen Kacheln anderer Quellen mit eigener Ruhezeit
- Pokopia: `importer.EIGENE_SPIELE` legt Spiele an, die die PokéAPI nicht führt (id ab 1000, ohne Pokédex); Karte von Map Genie
  (`mapgenie.GAMES["pokopia"]`, Kennung dort ohne „pokemon-“). `importer.VERSION` 17
- Offen: übrige IGN-Punkte (GraphQL, Abfrage aus dem Verbindungstest), Leser für RankedBoost, DittoBase, PokéTools,
  Bewertung je Kartenquelle (Auflösung, Zoom, Abdeckung, Punkte) und Wahl der Grundkarte, Punkte über gemeinsame Orte ausrichten

## 0.28.3 (11.11.2026)

- Verbindungstest „Kartenquellen im Detail“: IGN-Seiten ganz (Karte, Kacheln `oyster.ignimgs.com/ignmedia/wikimaps/<slug>/{z}/{x}-{y}.jpg`,
  Punkte zum Teil in `__NEXT_DATA__`), IGN-Skripte nach GraphQL-Abfragen mit „marker“ durchsucht, RankedBoost, DittoBase, PokéTools ganz

## 0.28.2 (11.11.2026)

- Verbindungstest: `Kachelpfad` für Map Genie wieder über `tile_ok` (0.28.0 prüfte die Ecke 0/0, die außerhalb liegt); Kartenseiten nennen eingebettete Daten

## 0.28.1 (11.11.2026)

- Verbindungstest nach der Prüfung vom 11.11.: Serebii-Ortsseiten unter `pokearth/galar|sinnoh/…`, Bulbapedia `Category:Game maps`; IGN nur Galar und Let's Go (DLC- und BDSP-Pfade 404)

## 0.28.0 (11.11.2026)

- `app/pkcompletion.py`: Spieldaten von pokemoncompletion (GPL-3.0) → Karte in der Form von `mapgenie.parse` (Leaflet-CRS.Simple
  in die linke obere Ecke der Mercator-Welt, Kacheln zu 512 Pixeln, `kachel` in der Karte), gespeichert unter `mapgenie/<Spiel>.json`.
  `abruf._pkcompletion` holt die Daten, `mg_tile`/`mg_stock` die Kacheln vom CDN (eigene Ruhezeit `pc_rest`).
  Gelb bleibt bei Map Genie; Zusammenführen der Gelb-Punkte offen
- Verbindungstest: Funde vom 11.11. (IGN, RankedBoost, MewMaps, Poké Atlas, FrontierNav, SimplyBLG, Ironmon-Karten, PokéMaps,
  PokéTools, PKMNMap, DittoBase, PokémonRNG, Bulbapedia-Kategorie Let's Go, GitHub-Bäume)

## 0.27.3 (11.11.2026)

- `mapgenie.GAMES` auf die Spiele, die Map Genie hat (LA, SV, Z-A, FRLG, RBY); SwSh, BDSP, Let's Go und Gen 2 bis 7 fehlen dort,
  dafür bleiben pokemoncompletion, IGN, Serebii und Bulbapedia im Verbindungstest

## 0.27.2 (11.11.2026)

- `mapgenie.GAMES` mit allen Hauptspielen ab Generation 1, mehrere Schreibweisen je Spiel (`mapgenie.slugs`), `SHARE` für
  Schwester-Editionen. pokemoncompletion (GPL-3.0) als zweite Quelle für Gelb, Kristall, Smaragd, Platin im Verbindungstest;
  Leser folgt, wenn die Proben vom Server da sind (Punkte in Leaflet-CRS.Simple, Bild `full.png`)

## 0.27.1 (11.11.2026)

- Potential: Endstufe zählt, wenn sie das Team um ≥ 1 hebt und besser ist als die heutige Stufe (kein Mindestabstand mehr);
  Mitglieder ab +0,5. `team.matchup`: Eigentyp-Bonus bei gewählten Attacken (ohne Bonus × 2/3), `damage_view` liefert `stab`
- Verbindungstest: Kartenquellen für SwSh, BDSP, Let's Go (Map-Genie-Slugs, IGN-Karten, Serebii, Bulbapedia-Archiv)

## 0.27.0 (11.11.2026)

- Kacheln: `mapgenie.tile_ok` nimmt `{z}/{y}/{x}` (Z-A), `tile_list` und `mg_tile` ab `min_zoom`; nach 8 × 403 prüft
  `abruf._mg_probe` eine bekannte Kachel (`_mg["ok"]`), erst wenn auch die fehlt, ruht Map Genie. `api()` fasst bei Netzfehlern nach
- Effort Levels: `effort.parts` (Basiswert, Level, Effort Levels, Wesen), Diagramm `elChart`, Tooltip `elTip`
- Entwicklung als Baum (`evoHtml`, Raster je Ast), Hover-Karte lädt fehlende Pokémon nach (`HCLOAD`), Vergleich mit Zwischenspeicher `CMPC`
- Potential: Endstufe zählt ab +0,5 über der heutigen Stufe (vorher +1; Kadabra → Simsala fiel heraus)
- Offen: Live-Werte-Diagramm auch für andere Spiele (EVs/DVs), Bonbons/Minzen; Abklingzeiten Z-A (Bulbapedia „Cooldown“, Z-A-Projekte
  auf GitHub im Verbindungstest); Karten älterer Spiele (Bulbapedia-Archiv, PokéEarth, Altissimo im Verbindungstest)

## 0.26.0 (11.11.2026)

- Effort Levels nur in Legenden: Arceus (`LA()`): `abfragen.effort_team` (`/api/effort/team`), Kasten `#elteam` im Reiter Team
  (`elTeam`); nicht eingetragen = Stufe 0 und markiert. Initiative-Liste mit `laStat` (wie `effort.stat`)
- Teambewertung bleibt bei Basiswerten (vergleicht Pokémon untereinander; Effort Levels ändern daran wenig)

## 0.25.0 (Entscheidung 11.11.2026: Effort Levels mit Anzeige und Planer)

- `app/effort.py` (Formel nach Bulbapedia, `FAKTOR`, `STEINE`, `cost`, `view`), `abfragen.effort_view` (`/api/effort`),
  Team-Platz speichert `el` und `el_ziel`; Oberfläche `elBox` auf der Detailseite (Legenden: Arceus)
- Offen: Anfangsstufe aus eingegebenen DVs

## 0.24.0 (Rückmeldung zu 0.23.0, 11.11.2026)

- Offline: `abruf.mg_stock` holt alle Zoomstufen (erst bis `max_zoom − 1` für alle Karten, dann `max_zoom`), Vorrat mit `ganz`
- Eine Datenbank (Entscheidung 11.11.2026: keine Ebenen nach Herkunft): `mapgenie.merge` führt Orte von Map Genie und
  `abfragen.mg_overlay` zusammen (`GLEICH`, `NACH_ITEM`, `DRIN`, `MERGE_TOL`, `MERGE_WIDE`), deutsche Gruppen, Kategorien und
  Namen (`GRUPPEN_DE`, `KAT_DE`, `name_de`, `abfragen.mg_names`); `/api/mapgenie?karte` liefert `punkte` (`abfragen.mg_map`)
- Schadensrechner: Gegner „Favoriten“
- Let's Go: `extra/spielwissen.json` (Fangen, Fang-Kombo, Partner-Techniken, Geheime Techniken, Quellen), `abfragen.knowledge`,
  auf der Detailseite `wissenHtml`, `partnerHtml`
- Offen: Abklingzeiten in Legenden: Z-A, Karten älterer
  Spiele, Zusammenführen auch für andere Spiele, sobald es eigene Punkte gibt, Fähigkeiten und Items im Schadensrechner

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
