# Roadmap

Was geplant ist, was offen ist und was entschieden wurde. Was sich je Version geändert hat, steht nur in `NEUIGKEITEN`
(`app/sources.py`, in der Oberfläche ein Klick auf die Version) und in Git (Commits und Pull Requests). Die frühere
ausführliche Versionsgeschichte bis 0.64.0, mit den Begründungen für entfernten Code, ist in Git nachlesbar:
`git show cf028e7:ROADMAP.md`.

Leitsätze (Arbeitsauftrag vom 13.11.2026): Richtig vor neu. Lieber melden als raten. Regeln je Spiel zentral und
nachvollziehbar halten. Nutzen belegen. Nutzerdaten haben Vorrang vor jeder technischen Vereinfachung.

## Als Nächstes

In dieser Reihenfolge, nach dem Arbeitsauftrag vom 13.11.2026. Abschnitte 1 bis 4 (Rechenlogik, Betrieb, Tests,
Spielprofil, Aufteilen der großen Dateien, Aufräumen) sind erledigt.

1. **Statuskarte in den Einstellungen.** Kompakt und standardmäßig eingeklappt, keine eigene Gesundheitsseite.
   Eingeklappt zeigt sie den Gesamtstatus (alles in Ordnung, Einschränkungen, Fehler vorhanden). Aufgeklappt: letzter
   Abgleich je Quelle, Ruhezeiten mit Ende, Fehlerregister (Quelle, Zeitpunkt, Art, Anzahl), Datengröße und
   Speicherverbrauch, freier Platz, Version von Anwendung und Daten, letzte Sicherung, letzter Wiederherstellungstest.
   Datenalter höchstens knapp im Tooltip. Fehler beim Aufbau eines Zwischenspeichers (Spieldaten beim Start,
   zusammengeführte Karten) gehen in den Gesamtstatus ein; heute trägt nur die erste Anfrage den Hinweis.
2. **Monatliche Prüfung der Sicherung.** Jüngste Sicherung in ein temporäres Verzeichnis wiederherstellen, Integrität
   und Nutzbarkeit prüfen, Ergebnis in der Statuskarte. Produktivdaten bleiben unberührt.
3. **Leistungstest auf Klick** in der Statuskarte: Speicher nach Start und Vorbereiten, CPU (soweit verlässlich), erste
   und wiederholte Antwortzeiten (`/api/attacken`, `/api/pokemon/…` und weitere), Antwortgrößen. Nicht während eines
   Abgleichs, keine Netzabrufe, keine Änderung an `user.db`, Schreibtests nur mit temporären erfundenen Daten, kein
   Docker-Socket, kein Neustart. Ergebnis mit Version und Zeitpunkt gespeichert. Danach anhand der Messung auf dem
   Heimserver entscheiden, ob der Speicher der Karten verkleinert werden soll (Python-Objekte, fertige und gepackte
   Antworten); ohne Messung keine Optimierung.
4. **Funktionen**, in dieser Reihenfolge:
   1. Fortschritt auf einen Blick: Sammlung je Spiel und für HOME, nach Generation und Typ, mit Sprung zu fehlenden
      Pokémon.
   2. Shiny-Jagd-Zähler: Methode, Pin, Schillerpin, laufende Wahrscheinlichkeit; Quoten als gepflegte Tabelle, Zähler in
      `user.db`.
   3. Tauschliste: Pokémon, die es nur durch Tausch oder in einer anderen Edition gibt, als kopierbare Übersicht.
   4. Ei-Attacken-Kette: kürzeste nachvollziehbare Elternkette für Pokémon und Attacke.
   5. Spielstandimport: Machbarkeit je Konsolengeneration bis zur Switch, Switch 2 gesondert prüfen; Matrix je Spiel und
      Dateiformat (exportierbar und lesbar getrennt); PKHeX und dokumentierte Formate als Referenz, kein Code aus PKHeX
      (GPL-3.0); eigene schlanke Umsetzung prüfen, keine Abhängigkeit ohne nachgewiesenen Nutzen. Dateien automatisch
      erkennen, Team, Boxen und Pokédex lesen, soweit verlässlich enthalten; Vorschau aller Änderungen, ausdrückliche
      Bestätigung, Originaldatei unverändert, Unbekanntes nicht falsch deuten.

## Danach: Backlog

Erwünscht, aber erst nach den Funktionen oben und dann neu zu ordnen.

- **Pokémon HOME, Boxenansicht** als eigener HOME-Reiter (keine Boxenverwaltung für alle Spiele): Boxen zu 30, Living
  Dex, Formen und Shinys, fehlende Einträge und freie Plätze, Hilfe beim Verteilen.
- **Erweiterter Schadensrechner**, einfache Bedienung bleibt Standard: Statusstufen, Wetter, Felder, Schilde und
  Schadensreduktionen, Doppelkämpfe mit mehreren Beteiligten; nur, was es im Spiel gibt, nichts doppelt. Dazu
  Fähigkeiten mit Bedingung.
- **Kompetitive Sets und Nutzungsstatistiken**, nicht nur Smogon: Nutzung, redaktionelle Empfehlung und veröffentlichte
  Beispielteams getrennt; nach dem Abgleich offline; Qualität und Aktualität prüfen.
- **Ereignisse und Geheimgeschenke**: Verteilungen je Spiel mit Zeitraum, Belohnung, abgeholt, verpasst, laufend;
  Quellen und Lizenzen vorher prüfen.
- **Nuzlocke und Duo-Challenges** (ausdrücklich erwünscht): Solo, Soul-Link mit zwei Spielern, gekoppelte Begegnungen,
  Team, Friedhof, Levelgrenzen vor wichtigen Kämpfen, Routen und erste Begegnungen, eigene Regelprofile; nicht auf eine
  Variante festgelegt.

## Offene Befunde

Gefunden und nicht behoben; in Klammern die Version, in der der Befund aufgenommen wurde.

- Die Entwicklungsreihe auf der Detailseite zeigt die heutigen Typen, die Kopfzeile die der gewählten Generation
  (0.59.0).
- „Was fehlt mir noch“: Ist keine Stufe einer Reihe im Spiel zu bekommen, verweisen die Wege im Kreis („Ei von X“, „aus Y
  entwickeln“) (0.59.0).
- `importer.NEEDED` nennt `time_of_day_prose`; die Datei gibt es bei der PokéAPI nicht mehr (404). Wirkt nur ohne
  Dateiliste und dann als ein gemeldeter Fehler (0.59.0).
- `blocked_target` prüft die Adresse vor dem Verbinden; löst ein Name zwischen Prüfung und Verbindung anders auf (DNS
  Rebinding), greift die Prüfung nicht. Abhilfe wäre, auf die geprüfte Adresse zu verbinden (0.59.0).
- Die Tests melden `ResourceWarning` (nicht geschlossene Dateien in zwei Tests, nicht geschlossene Datenbanken in den
  Kartentests) (0.59.0).
- Die Mini-Datenbank der Tests enthält nur, was aus PokéAPI, Showdown und `extra/` kommt; Raids, Aufträge, Spawnpunkte
  und Karten sind dort leer, ihre Antworten haben im Vertrag keine Form (0.59.0).
- Die engen `except` (`OSError`, `TypeError`, `ValueError` bei Eingaben und Dateien, rund 75 Stellen) sind nicht
  durchgesehen (0.58.1).
- Die Stelle im Fehlerhinweis ist der Name der Funktion (`shiny_locks`), kein deutscher Begriff (0.58.1).
- Der Browser-Selbsttest lieferte in der CI einmal in 180 Sekunden kein Ergebnis; der zweite Lauf ohne Änderung war
  grün. Bei einer Zeitüberschreitung meldet der Test nur die Ausgabe von Chrome, nicht den letzten Schritt der Seite;
  das sollte er nachholen (0.64.0).
- Formeln, die so umgesetzt, aber nicht belegt sind (Legenden: Z-A und Mega-Dimension wie die Hauptreihe, Fangtabelle
  für Pokopia, Federball): `docs/formeln.md`, Abschnitte „Offen“.

## Zu entscheiden

- **Federball in Legenden: Arceus:** Grundwert 0,5 oder 1 (`docs/formeln.md`). Bis zur Entscheidung gilt 1.
- **Ruhe je Server statt je Quelle auch im Abgleich:** Heute fragt eine zweite Quelle am selben Server weiter, wenn die
  erste gesperrt wurde. Der Verbindungstest ruht schon je Server.
- **Verpasster Termin:** Heute holt der Abgleich einen verpassten Termin (Server aus) am selben Tag nach; alternativ in
  der nächsten Nacht.

## Ältere Wünsche und offene Punkte

Gesammelt aus den Abschnitten der früheren ROADMAP bis 0.56.2 (vor dem Arbeitsauftrag). Erledigtes ist weggelassen, der
Rest ist nicht einzeln gegen den Code geprüft. Vor der Umsetzung prüfen, ob der Punkt noch gilt und noch gewünscht ist.
In Klammern die Version, in der er zuletzt als offen genannt war.

Karten:

- Let's Go: Punkte von IGN (die Abfrage der Punkte antwortet nicht) (0.56.2).
- Eine bessere Karte für Strahlender Diamant/Leuchtende Perle (0.56.2).
- Größere Alola-Inselbilder (Bulbapedia, 650 bis 750 px) mit anderem Ausschnitt; bräuchten eine Ausrichtung (0.56.0).
- Freie englische Sätze in Kartentexten (0.43.0); deutsche Kartentexte für Legenden: Z-A und Karmesin/Purpur (0.40.0).
- Aufträge 95 bis 122 von Legenden: Arceus auf der Karte; BisaFans nennt den Ort ohne Koordinaten (0.40.0).
- Eigene Punkte mit Map Genie auch in anderen Spielen zusammenführen, sobald es eigene Punkte gibt (0.24.0); die Punkte
  für Gelb aus pokemoncompletion und Map Genie zusammenführen (0.28.0).
- Bewertung je Kartenquelle (Auflösung, Zoom, Abdeckung, Punkte) und Wahl der Grundkarte; Leser für PokéTools (0.29.0);
  RankedBoost für weitere Spiele (0.40.0).

Fundorte und Sammlung:

- Safari-Zone: Fangen folgt dort eigenen Regeln, bisher gibt es nur die Fundorte (0.56.2).
- „Was fehlt mir noch“: Editionsexklusive in Spielen nur mit PKHeX-Daten (Karmesin/Purpur, Strahlender
  Diamant/Leuchtende Perle); Raid-Nester von Schwert/Schild als Weg (0.54.0).
- Fundorte von Schwert/Schild aus Serebii (0.40.0); in Karmesin/Purpur Tageszeit, Wetter, Massenauftreten und feste
  Pokémon aus PKHeX (0.5.0).
- Deutsche Ortsnamen für Colosseum und XD (0.22.0).
- Formen-Galerie für Pokémon wie Burmy und Shellos (0.13.0).
- PokéWiki-Leser: Edelhorden, getragene Items weiterer Spiele (0.5.0).

Werte, Kampf und Attacken:

- Champions: eigenes Werte-System, Regeln je Saison (0.32.0, 0.19.0).
- Let's Go: Freundschafts-Bonus der Werte (bis × 1,1), heute nicht eingerechnet (0.32.0).
- Legenden: Arceus: Kraft- und Tempostil im Schadensrechner (0.32.0).
- Legenden: Z-A: Plus-Attacken (0.30.0). Pokopia: deutsche Namen der Spezialitäten (0.30.0).
- Effort Levels: Anfangsstufe aus eingegebenen DVs; `effort.start_level` rechnet sie, die Oberfläche fragt sie nicht ab
  (0.25.0).
- Bonbons und Minzen (0.27.0).
- Tutor-Attacken der Erweiterungen von Schwert/Schild und Karmesin/Purpur aus PKHeX (0.15.0).
- Fähigkeiten, die im Kampf zählen (Einschüchterung, Wetter, Typ-Verstärker, Immunitäten), knapp in der Teambewertung
  (0.5.0).
- Aus dem Quellenprotokoll vom 11.11.2026: Werte-Spanne Level 50 und 100, Moveset-Suche, Abdeckungs-Prüfer, Vergleich
  bis vier Pokémon (0.18.0).

Items und Sonstiges:

- Wirkung auch für Beeren und getragene Items; Fundorte der Items; Bilder in besserer Auflösung; Beschreibungen für
  Items, die es nur in PKHeX gibt (0.5.0).
- Links auf die Gebietsseiten im PokéWiki statt eigener Bilder, wo Bildrechte es verlangen (0.5.0).
- Als App auf dem Handy installierbar (PWA) (0.1.0).

## Entscheidungen, die weiter gelten

- **Eine Datenbank** (11.11.2026): Alle Quellen werden zu einem Bestand zusammengeführt, keine Ebenen nach Herkunft.
  Ziel ist die Nutzung ohne Netz nach dem Abgleich: Karten, Kacheln und Kartenpunkte liegen im Datenordner.
- **Widersprechen sich Quellen** (11.11.2026): Spieldaten gehen vor Wikis; PokéAPI gegen Showdown landet unter „Zu
  erledigen“. Eine Mehrheit zählt erst ab drei unabhängigen Quellen.
- **Teambewertung mit Basiswerten** (11.11.2026): Sie vergleicht Pokémon untereinander; Effort Levels und ähnliche
  Werte ändern daran wenig.
- **Quellenzuordnung bleibt bei der Quelle** (19.11.2026): Welche Seite einer Quelle zu welchem Spiel gehört (Map Genie,
  PokéWiki, PKHeX, Serebii und andere), steht beim Leser der Quelle, nicht im Spielprofil; die Einstiegswerte der Karten
  (`MGSTART`, `MG_EDITION`) stehen in `karte.js`.
- **Reddit ist keine Quelle** (12.11.2026): keine strukturierten Daten.
- **Kartenbilder nie im Repository**, nur im Datenordner.
- **Benachrichtigungen:** keine ntfy-Meldungen; Störungen zeigt die Oberfläche.

## Von den Geschwistern

Was beim Arbeiten am Pokédex auffällt und für eShopKompass oder VR-Navigator taugen könnte. Nur Empfehlungen; die
anderen Repositories ändert niemand von hier aus.

- **19.11.2026, große Dateien mit Werkzeug teilen.** Im Pokédex wurden `app.js`, `abfragen.py` und `abruf.py` an
  Abschnittsgrenzen geschnitten und alt gegen neu geprüft: bei JavaScript Byte für Byte, bei Python über den Syntaxbaum
  (jede Anweisung genau einmal), dazu die Antworten des Servers mit echten Daten. Empfehlung: dasselbe Vorgehen, wenn
  dort Dateien zu groß werden; Handarbeit beim Schneiden vermeiden.
- **19.11.2026, Ersatz in Tests nach einer Paketteilung.** Ersetzt ein Test einen Namen nur im Paket, merken die Module
  nichts davon; der Test bleibt grün und prüft nichts mehr. Abhilfe: ein Helfer, der den Namen im Paket und in jedem
  Modul mit demselben Objekt ersetzt (`tests.basis.im_paket`), und ein Test gegen die alte Schreibweise. Empfehlung:
  übernehmen, sobald dort ein Modul zum Paket wird.
- **19.11.2026, Wege des Servers ohne Aufrufer.** Ein Test gleicht jeden Weg des Servers mit den Aufrufen der Oberfläche
  ab (`Vertrag.test_wege`) und fand so toten Code. Empfehlung: für beide Geschwister übernehmbar.
- **19.11.2026, jedes Skript mit Kennung seines Inhalts.** Nach der Teilung der Oberfläche lädt ein Update nur die
  geänderten Teile neu. Empfehlung: übernehmen, wo die Oberfläche aus mehreren Dateien besteht.
- **19.11.2026, Regeln je Gegenstand an einer Stelle.** Im Pokédex hingen Regeln je Spiel an Listen von Kennungen in
  Server und Oberfläche (elf Listen, rund 50 Vergleiche); eine neue Erweiterung musste an jede Stelle. Jetzt ein Profil je
  Spiel mit Vorgaben je Generation, die Oberfläche bekommt es über die Grunddaten, ein Test verbietet den Vergleich mit
  Kennungen. Empfehlung: in den Geschwistern suchen, wo Regeln an Kennungen hängen (etwa je Shop oder je Gerät), und
  erst dann entscheiden; ob es dort solche Listen gibt, ist von hier aus nicht geprüft.
- **19.11.2026, Selbsttest im Rahmen: Aufrufe im Rahmen laufen lassen.** Ruft die Testseite eine Funktion der Oberfläche
  direkt auf und diese setzt `location.replace("#…")`, löst der Browser den Weg gegen die Testseite auf und lädt sie in
  den Rahmen. Abhilfe: die Funktion über den Zeitgeber des Rahmens starten (`win.setTimeout(new win.Function(…))`).
  Empfehlung: in den Selbsttests der Geschwister prüfen, ob sie Funktionen der Oberfläche direkt aufrufen.
- **16.11.2026, `TCP_NODELAY` am Webserver.** Wer mit `http.server` Kopfzeilen und Inhalt getrennt schreibt und
  Verbindungen offen hält (HTTP/1.1), verliert je Antwort rund 40 ms (Nagle trifft auf verzögerte Bestätigung). Eine
  Zeile behebt es: `disable_nagle_algorithm = True` am Handler. Ob die Geschwister betroffen sind, ist von hier aus
  nicht geprüft. Empfehlung: im Browser-Selbsttest messen (Zeit zwischen Kopfzeilen und Inhalt) und bei Befund übernehmen.
- **16.11.2026, Selbsttest: eine Anfrage ist erst fertig, wenn ihr Inhalt da ist.** Zählt der Selbsttest laufende
  Anfragen nur bis zu den Kopfzeilen, hält er eine Ansicht für fertig, während der Inhalt noch unterwegs ist (hier:
  leere Liste in einem von drei Läufen). Empfehlung: in den Selbsttests der Geschwister prüfen, woran „fertig“ hängt.
- **16.11.2026, Testdaten durch den echten Importer.** Eine kleine erfundene Welt als Eingabe des echten Imports statt
  einer von Hand gebauten Testdatenbank: prüft den Import mit und hält die Tests ehrlich. Dazu die Form der Antworten
  als Datei und der Abgleich „die Oberfläche kennt jedes Feld“. Empfehlung: für beide Geschwister prüfen, wo Tests mit
  Daten heute nur lokal laufen.
- **16.11.2026, Ziele im Heimnetz.** `ipaddress.is_global` lässt Multicast und NAT64 durch. Empfehlung: Wo die
  Geschwister dieselbe Prüfung haben, `public_ip` übernehmen und die Fälle der Klasse `Heimnetz` als Test.
- **16.11.2026, Fehlerregister statt stiller Ersatzwerte.** Eine kleine Datei je Dienst: je Fehler (Quelle, Stelle, Art)
  ein Eintrag mit Anzahl, erstem und letztem Zeitpunkt, begrenzt; der Traceback einmal je Fehler und Start im Protokoll.
  `except Exception` meldet dorthin und macht mit dem Ersatzwert weiter; „Tabelle fehlt in älterer Datenbank“ ist
  ausdrücklich kein Fehler. Ein Test sucht stille Stellen im Quelltext. Das Review nennt stille `except` und `.catch`
  für beide Geschwister. Empfehlung: übernehmen, je mit eigener Liste begründeter Ausnahmen.
- **16.11.2026, Antwort mit Lücke kennzeichnen.** Eine Kopfzeile an der Antwort, wenn beim Rechnen ein Teil gescheitert
  ist; die Oberfläche zeigt einen Hinweis über der Ansicht, und die Antwort ist nicht zwischenspeicherbar. In der
  Oberfläche zwei Helfer für `.catch` (Teil nicht geladen, Änderung nicht gespeichert und zurückgenommen), 404 bleibt
  still. Empfehlung: für beide Geschwister übernehmbar.
- **14.11.2026, Stand des Abgleichs nach jeder Quelle speichern.** Teile des Zustands, die sich im Lauf ändern (Quellen,
  Ruhezeiten), als Wörterbuch, das bei jeder Änderung speichert; ein Kennzeichen „läuft“ im Stand, an dem der Dienst
  nach dem Start einen unterbrochenen Lauf erkennt und fortsetzt (begrenzt oft). Das Review nennt denselben Befund für
  den VR-Navigator (Fehler außerhalb der Stränge überspringt das Speichern). Empfehlung: dort übernehmen; im
  eShopKompass prüfen, ob der Stand mitten im Lauf geschrieben wird.
- **14.11.2026, Ruhezeiten in eigener kleiner Datei, geschrieben im Augenblick der Sperre.** Im Pokédex lag eine
  Ruhezeit nur im Speicher (Kartenkacheln). Das Review nennt für den eShopKompass, dass die Ruhe nur für zwei Quellen
  dauerhaft gemerkt wird. Empfehlung: in beiden Geschwistern jede Stelle suchen, die nach 403 oder 429 eine Ruhe nur im
  Speicher setzt.
- **14.11.2026, Verbindungstest und Ruhezeit.** Der Test fragt keinen Server, der nach einer Sperre ruht, und teilt
  Sperre und Pause je Server mit dem Abgleich. Das Review nennt den Befund für beide Geschwister. Empfehlung: übernehmen.
- **14.11.2026, schlanker Stand und Adressen mit Prüfsumme.** Ein Endpunkt nur für den Stand des Abgleichs; Dateien der
  Oberfläche mit der Prüfsumme des Inhalts in der Adresse und unbegrenzter Haltbarkeit, einmal gepackt. Die Prüfsumme
  statt der Versionsnummer schützt davor, dass eine geänderte Datei bei gleicher Nummer ein Jahr im Browser bleibt.
  Empfehlung: für beide Geschwister übernehmbar.
- **14.11.2026, feste Uhrzeit als Weltzeit.** Der Container kennt keine Zeitzone; die Oberfläche rechnet in die
  Ortszeit des Browsers um. Nur übernehmen, wo ein Zeitplan nach dem letzten Lauf stört; kein Handlungsbedarf erkannt.
- **13.11.2026, Test gegen Privates im Repository.** Der Test liest `git ls-files` und scheitert bei Dateien, die nicht
  in eine erlaubte Liste passen (Wurzelverzeichnis, `*.log`, `*.db`, Bilder außerhalb von `app/static`), und bei Mustern
  für private Adressen und Zugangsdaten im Inhalt. Anlass war eine versehentlich eingecheckte `srv.log` im Pokédex.
  Empfehlung: in beiden Geschwistern übernehmen, mit je eigener Liste erlaubter Dateien.
- **13.11.2026, Vergleichswerte aus einer fremden Referenz.** Für Rechenlogik eine Datei mit Fällen aus einer
  anerkannten Referenz erzeugen (festes Werkzeug unter `tools/`, fester Startwert) und nur die Datei im Test lesen. Das
  Werkzeug ist keine Abhängigkeit. Für die Geschwister nur dort sinnvoll, wo es eine solche Referenz gibt (etwa
  Preis- und Währungsumrechnung im eShopKompass); kein Handlungsbedarf erkannt.
- **13.11.2026, Formeln mit Quelle in einer eigenen Datei** (`docs/formeln.md`, mit dem Abschnitt „Offen“ für alles, was
  angenommen statt belegt ist). Entspricht dem Leitsatz „Lieber melden als raten“ des eShopKompass; dort und im
  VR-Navigator für Bewertungs- und Sortierregeln denkbar.
