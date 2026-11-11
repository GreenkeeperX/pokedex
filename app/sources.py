"""Netzabrufe: eine Stelle für alle Quellen (PokéAPI, Pokémon Showdown, Sprites, PokéWiki).

Übernommen aus dem VR-Navigator: ehrliche Kennung, nur öffentliche Ziele, Grenzen für Antwortgröße
und Zeit. Alle Abrufe laufen über `fetch(url)`, damit Tests eine Attrappe einsetzen können.
"""
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
import zlib

VERSION = "0.27.2"

# Was sich je Version ändert, für den Hinweis in der Oberfläche. Neueste zuerst; der erste Eintrag
# muss VERSION sein (Test). Ausführlich steht es in ROADMAP.md.
NEUIGKEITEN = [
    ("0.27.2", "11.11.2026", [
        "Karten älterer Spiele: der Abgleich fragt Map Genie jetzt auch für Rot/Blau/Gelb bis Ultrasonne/Ultramond "
        "(und SwSh, BDSP, Let’s Go unter weiteren Schreibweisen); Schwester-Editionen zeigen anfangs ihre eigene Karte",
        "Verbindungstest: pokemoncompletion (Gelb, Kristall, Smaragd, Platin: Kartenpunkte als JSON, Karte als Bild und Kacheln)",
    ]),
    ("0.27.1", "11.11.2026", [
        "Langfristig mehr Potential: zählt, was die Endstufe dem Team bringt, nicht der Abstand zur heutigen Stufe; "
        "Kadabra steht damit nie schlechter da als Abra. Mitglieder im Team zeigen ihre Endstufe schon ab +0,5",
        "Eigentyp-Bonus: „Gegen Gegner“ rechnet ihn bei gewählten Attacken ein (ohne ihn zählt eine Attacke ein Drittel weniger, "
        "mit Hinweis); der Schadensrechner nennt ihn",
        "Verbindungstest: Kartenquellen für Schwert/Schild, Strahlender Diamant/Leuchtende Perle und Let’s Go "
        "(Map Genie unter anderen Namen, IGN, Serebii, Bulbapedia-Archiv, pokemoncompletion)",
    ]),
    ("0.27.0", "11.11.2026", [
        "Karten: Kacheln von Karmesin/Purpur und Legenden: Z-A laden wieder (Z-A nennt erst y, dann x; keine Anfragen mehr unter der "
        "kleinsten Zoomstufe, und viele fehlende Randkacheln lassen Map Genie nicht mehr ruhen). Menü und Details mit Hintergrund, "
        "ohne Springen, auch in den Einzelkarten; die Oberfläche fasst bei kurzen Netzfehlern zweimal nach",
        "Effort Levels: Balken und Netz zeigen live, woraus jeder Wert besteht (Basiswert, Level, Effort Levels, Wesen, bis zum Ziel); "
        "Rechnung im Tooltip; das Ziel folgt der Stufe, bis du es eigens setzt",
        "Detailseite: Entwicklungsäste untereinander (Waumpel), größeres α, „⚖ Vergleichen“ und „merken“ nebeneinander",
        "Vergleich: Hover-Karten an der Schnellwahl, sofort neu gezeichnet, lesbare Verteidigungstabelle, „Kurz gesagt“ mit Farben und Typ",
        "Team: Teamsuche einklappbar unter den Effort Levels, Angreifer im Schadensrechner mit Bildern, „zurück“ zur vorigen Gegnerwahl, "
        "Spaltenwahl in „Gegen Gegner“ richtig, Löschen rot umrandet, Potential zeigt auch knappere Entwicklungen (Kadabra → Simsala)",
        "Attacken und Items: Namensspalte markierbar; Typen: dezentere Zählspalten mit Tooltip; Einstellungen neu geordnet; "
        "Champions: Hover-Karten im Kampftagebuch, Anteil als Balken bei den häufigen Gegnern",
    ]),
    ("0.26.0", "11.11.2026", [
        "Legenden: Arceus: Effort Levels im Reiter Team: je Mitglied Stand und Ziel, was dem ganzen Team an Leistungs-Items "
        "fehlt; nicht eingetragene Mitglieder rechnen vorsichtig mit Stufe 0 und sind markiert",
        "Legenden: Arceus: Initiative-Liste mit der Formel des Spiels (Effort Level 0 und 10 statt EVs und DVs); dein Team mit seinen Stufen. "
        "Andere Spiele bleiben, wie sie waren",
    ]),
    ("0.25.0", "11.11.2026", [
        "Legenden: Arceus: Effort Levels auf der Detailseite. Je Wert die Stufe 0 bis 10 und ein Ziel, dazu Wesen und Level; "
        "die Werte rechnen sich mit (jetzt, am Ziel, höchstens), und der Planer sagt, wie viel Leistungssand, -kies, -stein und "
        "-fels bis zum Ziel fehlen. Im Team merkt sich jeder Platz seine Stufen",
    ]),
    ("0.24.0", "11.11.2026", [
        "Karten ganz offline: Der Server holt im Hintergrund alle Kacheln aller Zoomstufen jeder Karte und hebt sie auf; "
        "Orte, Punkte und Texte liegen ohnehin seit dem Abgleich bei ihm. Danach braucht die Karte kein Internet mehr",
        "Eine Datenbank statt zwei Quellen: Map Genie und die Spieldaten sind auf der großen Karte zusammengeführt. Was an derselben "
        "Stelle dasselbe ist (Geisterlicht, Beerenbaum, Erzbrocken, Alpha …), ist ein Punkt mit allen Angaben: Text von Map Genie, "
        "Items aus den Spieldaten, Pokémon im Baum oder Kristallbrocken. Ebenen nach Bedeutung und auf Deutsch, die Herkunft steht "
        "nur noch klein in den Details",
        "Schadensrechner: Favoriten als Gegner (Champions und Reiter Team)",
        "Let’s Go: Fangen ohne Kampf (Beeren, Würfe, Bälle, Wurfkreis), Fang-Kombo (schillernd, selten, perfekte Werte) auf der "
        "Detailseite; Partner-Pikachu und Partner-Evoli zeigen ihre Partner-Techniken und die Geheimen Techniken",
        "Karte: die Anzeige „Kacheln laden“ zählt nicht mehr ins Minus",
    ]),
    ("0.23.0", "11.11.2026", [
        "Karten: Der Server legt einen Vorrat an Kartenkacheln an (im Hintergrund, mit Pause, weite Stufen zuerst); beim Zoomen "
        "bleibt das alte Bild vergrößert stehen, bis die neuen Kacheln da sind, mit Anzeige „Kacheln laden … noch n“; "
        "Nachbarn und die nächste Stufe lädt der Browser still vor. Fehlende Kacheln lassen die Quelle nicht mehr gleich einen Tag ruhen",
        "Karten: robuster bei Karten ohne Grenzen oder mit getrennt angegebener Bildendung (Legenden: Z-A); der Verbindungstest "
        "zeigt je Karte Muster, Zoom, Grenzen und Vorrat",
        "Schadensrechner jetzt im Reiter Team für alle Spiele ab Generation 3: gegen die Gegner aus „Gegen Gegner“, das eigene Team "
        "oder eine eigene Auswahl, mit Level für beide Seiten; „Übersicht“ zeigt jedes Mitglied gegen jeden Gegner mit seiner "
        "stärksten Attacke. Bis Generation 5 zählt ein Volltreffer doppelt",
        "Champions: eigene Gegner im Schadensrechner, größere Bilder, Schadensbalken in eigener Spalte und farbig",
        "Generation 1: Spezial-Wert statt Sp.-Angriff und Sp.-Verteidigung; ältere Spiele zeigen die Basiswerte von damals "
        "(aus den Generations-Mods von Showdown)",
        "Typen: eigener Filter für jede Tabelle (auch die Team-Tabellen); Zählspalten (Schwächen, ×4, Resistenzen, Immunitäten "
        "bzw. stark, schwach, ohne Wirkung) farbig, jetzt auch in der Typtabelle und den Team-Tabellen",
        "Vergleich: Auswahl unter dem Vergleich mit größeren Bildern, „Zum Vergleich gemerkt“ getrennt von den Favoriten, "
        "„alle entfernen“, Verteidigung besser lesbar und mit Tooltips",
        "Team: „Team als Text“ erklärt und über den Favoriten, ⇄ bei Favoriten tauscht ins Team, Sterne nur beim Darüberfahren; "
        "„Langfristig mehr Potential“ zeigt keine Vorstufe mehr, wenn eine spätere Stufe schon gefangen ist",
        "Einstellungen wie im VR-Navigator: Quellen, Verbindungstest und Protokoll aufklappbar im Abgleich, Spieldaten und "
        "Sicherung in einem Kasten",
        "Detailseite wieder zweispaltig; α in der Knopfreihe; breitere Spalten bei Attacken und Items, Statusfarben in den Items",
        "Verbindungstest: neue Proben für Abklingzeiten in Legenden: Z-A und Karten älterer Spiele",
    ]),
    ("0.22.0", "11.11.2026", [
        "Karmesin/Purpur: Tera-Typen zählen in der Team-Bewertung (welche Schwächen die Terakristallisierung nimmt und welche sie bringt)",
        "Neuer Reiter „Raids“ in Karmesin/Purpur: alle Tera-Raids aus den Spieldaten (1 bis 7 Sterne, Paldea, Kitakami, "
        "Blaubeer-Akademie, Events) mit Tera-Typ, Attacken, Konter und Gefahr aus dem eigenen Team; auch auf der Detailseite",
        "Colosseum und XD: Crypto-Pokémon auf der Detailseite (Trainer, Orte, Level, Attacken, Läuterung)",
        "Team: Form je Platz tauschen, etwa Mega-Entwicklung für den Kampf (Detailseite eines Mitglieds, „Platz … als“)",
        "Champions: Schadensrechner in der Kampfansicht (gewählte Attacke gegen die häufigsten Gegner oder das eigene Team, "
        "Level 50, Fläche, Volltreffer, Tera, Investition der Gegner)",
        "Champions: Kampftagebuch mit Ergebnis, Gegnern und Notiz, Bilanz und häufigsten Gegnern; steckt in der Sicherung",
    ]),
    ("0.21.0", "11.11.2026", [
        "Champions: „Häufige Gegner“ in der Kampfansicht aus der Nutzungsstatistik von Smogon (monatlich beim Abgleich): Anteil, "
        "Attacken, Items, Fähigkeit und Tera-Typen, dazu wer im Team gefährdet ist und wer antwortet; „Top 6 als Gegner“ für den Team-Reiter",
        "Karmesin/Purpur: Tera-Typ je Team-Platz auf der Detailseite, mit der Typwirkung nach der Terakristallisierung",
        "Generation 1 und 2 sowie Let’s Go ohne Fähigkeiten; bis Generation 3 gilt physisch oder speziell nach dem Typ der Attacke "
        "(auch in der Wertung)",
        "Let’s Go: Hinweis zur eigenen Fangformel (Beeren, Wurfkreis, Fangkombo)",
    ]),
    ("0.20.0", "11.11.2026", [
        "Abgleich parallel: Quellen an verschiedenen Servern laufen gleichzeitig (Showdown, PKHeX, PokéWiki, Altissimo …, danach "
        "Bilder, Kartenkacheln, Map Genie und große Item-Bilder); die Pause je Server gilt weiter für alle zusammen",
        "Detailseite mit festem Raster aus drei Spalten: Stammdaten, Typwirkung, Entwicklung und Fang; die Fundorte folgen direkt darunter",
        "Vergleich: „Zum Vergleich merken“ auf der Detailseite, Schnellwahl aus Gemerkten und Favoriten, Artworks, großes Netz wie auf der "
        "Hover-Karte, „Kurz gesagt“ (wer schneller ist, wer wen härter trifft) und mehr Tooltips",
        "Team: „Langfristig mehr Potential“ nimmt die weiteste Stufe, auch aus dem Team (Kadabra statt Abra); Sterne an Vorschlägen und "
        "Team-Karten; „Team als Text“ erklärt, weiter unten und mit „Team kopieren“ im Kopf",
        "Typen: Filter nach Typen, Kombinationen als Verteidiger oder Angreifer, Spalten markierbar; „Mein Team“ ohne Kombinationen und mit "
        "Hinweis auf Mitglieder, die es im Spiel nicht gibt",
        "Spalten markieren über ein Spaltensymbol vor dem Titel, jetzt auch bei Beschreibungen",
        "Pokémon-Karten: Knöpfe ohne Rahmen, leuchten beim Hovern; α steht rechts neben dem Pokéball",
        "Feste Tabellenköpfe gleiten so schnell wie die Kopfzeile",
        "Große Item-Bilder auch für Namen mit Bindestrich oder Apostroph (Königsblatt, Selfe-Kralle, Doppelrettich …)",
        "„Zu erledigen“ sagt, dass der neueste Stand der Hauptspiele verglichen wird, nicht ein einzelnes Spiel",
        "Champions: Kampfansicht erklärt Doppelkampf, Rollen und Tempo; beim Wechsel in ein anderes Spiel geht es zur Karte",
    ]),
    ("0.19.1", "11.11.2026", [
        "Karten von Map Genie laden wieder ganz: Kacheln außerhalb der Karte werden nicht mehr angefragt (Map Genie "
        "antwortete dort mit 403, und der Pokédex ließ die Quelle daraufhin einen Tag ruhen); fehlen Kacheln, sagt die Karte warum",
        "Beschreibungen auf der Karte gegliedert (Absätze, Listen, Links zu anderen Orten), Begriffe deutsch; „erledigt“ statt „gefunden“; "
        "die eigenen Punkte heißen „Aus dem Pokédex“ und erklären sich per Tooltip",
    ]),
    ("0.19.0", "11.11.2026", [
        "Champions: Reiter „Kampf“ statt „Karte“, „im Kader“ statt gefangen, ohne Schillernd und Fangchance",
        "Doppelkampf-Bewertung (Reiter Kampf): Rollen wie Schutz, Tempo-Kontrolle, Störer, Umlenken und Unterstützung mit "
        "Vorschlägen, wer sie lernen kann; Flächenattacken und ob sie den Partner treffen; Rat zu Rückenwind oder Bizarroraum",
    ]),
    ("0.18.0", "11.11.2026", [
        "Team als Showdown-Text: übernehmen (auch PokePaste, deutsche Namen gehen ebenfalls) und weitergeben, mit Item, "
        "Fähigkeit, Wesen, EVs, IVs und Tera-Typ; die Plätze zeigen Item, Fähigkeit und Wesen",
        "Initiative-Liste: alle Pokémon des Spiels nach Initiative (minimal, neutral, maximal, mit Wesen), Level 50 oder 100, "
        "mit Rückenwind und Wahlschal; dein Team steht mit seinem eigenen Wert dazwischen",
    ]),
    ("0.17.0", "11.11.2026", [
        "Große Karte: Legenden: Arceus zeigt ganz Hisui mit den eigenen Spawnpunkten und Symbolen (an Geisterlichtern "
        "und Icognito ausgerichtet); „Gehe zu“ für Gebiete, Suche nach Ort, Symbol oder Pokémon mit Trefferliste, ein Klick zoomt hin",
        "Vergleich zweier Pokémon nebeneinander: Werte mit Unterschied, Typwirkung, Fähigkeiten, Attacken (Detailseite → Vergleichen)",
        "Typen: alle 171 Typkombinationen als Verteidiger, sortierbar nach Schwächen und Resistenzen, Filter auf einen Typ",
    ]),
    ("0.16.0", "11.11.2026", [
        "Karten von Map Genie für jedes Spiel, das es dort gibt: Orte, Sammelobjekte und Materialien als Ebenen, "
        "Suche, Kacheln lädt der Server beim ersten Ansehen (Karte → Map Genie)",
        "Kartensymbole als gefunden markieren (Rechtsklick oder ✓ in den Details), Zähler je Ebene, „gefundene ausblenden“",
        "Erweiterungen (Die Insel der Rüstung, Die Schneelande der Krone, Die türkisblaue Maske, Die Indigoblaue Scheibe) "
        "zeigen die Lernliste ihres Hauptspiels mit den Lehrer-Attacken und TMs der Erweiterung",
        "Verbindungstest: Map Genie je Spiel, pokemoncompletion für ältere Spiele",
    ]),
    ("0.15.0", "11.11.2026", [
        "Gebiete für alle Spiele: Ort wählen, alle Pokémon dort als Bilder mit Methode, Level, Anteil und Edition; "
        "Gefangene blass, auf Wunsch nur die fehlenden (Karte → Gebiete)",
        "Strahlender Diamant/Leuchtende Perle: Fundorte aus den Spieldaten (PKHeX)",
        "Ortsnamen ohne doppelten Ort („Dunkelhöhle (Viola City Eingang)“)",
    ]),
    ("0.14.0", "11.11.2026", [
        "Legenden: Z-A und Mega-Dimension: eigene Lernlisten (Level und TMs) aus den Spieldaten (PKHeX)",
        "Detailseite: „Formen zum Ansehen“ für Pokémon mit Formen ohne eigene Werte (Burmy, Vivillon, Icognito …)",
        "Verbindungstest: mögliche Kartenquellen für Karmesin/Purpur und Legenden: Z-A",
    ]),
    ("0.13.0", "11.11.2026", [
        "Karte: Schnellreise und Lager (PLA Companion), Filter für Tageszeit und Wetter, Ebenen in Gruppen; "
        "Ziehen geht auch über Bildern und Symbolen, die Bilder der Übersicht ohne dunklen Hintergrund",
        "Pokémon: α über dem Pokéball markiert ein Pokémon als Alpha gefangen (nur, wo es Alphas gibt)",
        "Team: „Langfristig mehr Potential“ zeigt je Endstufe nur die weiteste gefangene Form, nichts schon Vorgeschlagenes",
        "Attacken und Items: Tabellenkopf bleibt beim Scrollen stehen; Items mit Linien und markierbaren Spalten, "
        "Herstellen mit Zutaten untereinander und farbigen Orten",
        "Typen: im Angriff je Mitglied ist ×2 grün und ½ rot (aus Sicht des Mitglieds)",
        "Bilder: mehr Item-Bilder je Lauf, Ersatz aus anderen Ordnern; getragene Items finden ihr Bild im Spiel",
    ]),
    ("0.12.0", "10.11.2026", [
        "Karte: Übersicht mit Pokémon-Bildern (je größer, desto wahrscheinlicher) und Vergleich der Gebiete je Pokémon",
        "Karte: Kristallbrocken, Raum-Zeit-Verzerrungen, Massenauftreten, Pokémon in Bäumen, feste Alphas, Items am Boden "
        "und die Items der Grabstellen (PokéWiki); Ebenen „alle“ und „keine“; die Wahl eines Pokémon geht schneller",
        "Pokéball: dritter Klick markiert das Pokémon als schillernd gefangen",
        "Typen: Filter „Mein Team“ mit Verteidigung und Angriff je Mitglied; Attacken: Filter „Team-Attacken“, "
        "Spalten lassen sich markieren, der Name markiert nur die Zeile",
        "Items: große Bilder, Spalten für KP, AP, EP und Statusprobleme, Fangfaktor der Bälle, Preise farbig",
        "Detailseite: Gebiete farbig, Fangchance von Rot über Gelb nach Grün; Einstellungen kompakter, Zeiten deutsch",
    ]),
    ("0.11.0", "10.11.2026", [
        "Fundorte aus den Spieldaten auch für Karmesin/Purpur (mit beiden Erweiterungen), Legenden: Z-A (mit Alpha) "
        "und Mega-Dimension, dazu Filter „Gebiet“ für diese Spiele",
        "Fundorte: Spalten nur, wo es Daten gibt (Stellen, Tageszeit, Wetter, Alpha)",
        "Einstellungen: Lesezeichen „Seite untersuchen“ liest Seiten, deren Karten erst im Browser laden (etwa das PokéWiki), als Datei",
        "Verbindungstest: Karten von GamerGuides und Pokébip zum Vergleich",
    ]),
    ("0.10.1", "10.11.2026", [
        "Karte: Geisterlichter und Gedichte heißen jetzt wie im Spiel",
        "Verbindungstest: mögliche Quellen für bessere Item-Bilder (Serebii, PokéWiki) sowie Lager und Schnellreise "
        "(Serebii-Karte, PokéWiki) mit Probe-Seiten",
    ]),
    ("0.10.0", "10.11.2026", [
        "Karte: Jubeldorf mit eigenem Kartenbild, Irrlichtern und Icognito",
        "Karte: Aprikoko- und Beerenbäume, Erzbrocken, Laub- und Heuhaufen, Kisten, Irrlichter, Icognito, alte Verse und "
        "Grabstellen als Symbole, jede Art einzeln ein- und ausblendbar, mit den Items und ihrem Anteil",
        "Items: Legenden: Arceus, Karmesin/Purpur, Legenden: Z-A, Strahlender Diamant/Leuchtende Perle und die Erweiterungen "
        "von Schwert/Schild mit eigener Item-Liste (deutsche Namen aus den Spieltexten)",
        "Items in Legenden: Arceus: „Herstellen“ zeigt die Rezepte mit Zutaten, Zutaten zeigen, wo sie zu finden sind",
    ]),
    ("0.9.1", "10.11.2026", [
        "Pokémon-Liste: wieder vier Spalten, Symbole mittig, Pokéball beim Aktivieren gleich groß",
        "Sammlung übertragen: ⇄ auf der unteren Kartenlinie, Ziel wie die Spielauswahl, neu „Freilassen“ zum Aufräumen",
        "Detailseite: „Deine Auswahl“ und „Vorschlag“ gleich aufgebaut und auf gleicher Höhe",
        "Team: Hinweis bei gewählten Attacken, die es im Spiel für dieses Pokémon nicht gibt",
        "Attacken: Zeilen und Spalten markieren wie in den anderen Tabellen, Filter „bis/nur Gen …“",
        "Items: Anzahl steht in der Leiste, nichts springt mehr",
        "Abgleich: PokéAPI-Dateien werden zwischengespeichert, Nachläufe ohne neuen Stand sind deutlich schneller",
    ]),
    ("0.9.0", "10.11.2026", [
        "PokéWiki-Leser: Stärke, Genauigkeit und AP der Attacken in Legenden: Arceus mit Kraft- und Tempostil (unter der Stärke)",
        "Detailseite: getragene Items wilder Pokémon in Legenden: Arceus, mit Anteil und „Elite“",
        "Pokémon HOME in der Spielauswahl: eigene Sammlung mit allen Pokémon",
        "Sammlung übertragen: bei „nur aus deiner Sammlung“ mit ⇄ auswählen und nach HOME oder in ein anderes Spiel übertragen",
        "Verbindungstest prüft den gebündelten Abruf aus dem PokéWiki",
    ]),
    ("0.8.2", "10.11.2026", [
        "Liste: Nummer oben links, Netz mit allen Zahlen, Häkchen, Stern, Pokéball und + an festen Plätzen, Pokéball größer, kein Rand beim Hovern; Typen nebeneinander",
        "Detailseite: Netz-Hinweis als Tabelle mit Balken, Fangchance farbig, Fundort-Art farbig (frei grün, Verzerrung violett, Massenauftreten blau …)",
        "PokéWiki-Links ohne Pfeil: der Name selbst ist der Link, unterstrichen beim Hovern",
        "Attacken-Tabellen bündig und zentriert, Level und Beherrschung in zwei Zeilen, Status-Attacken mit denselben Spalten; Statuswörter wie „paralysiert“ farbig",
        "Artwork: beim Zurückschalten kein altes Bild mehr",
        "Team: „Gegen Gegner“ nur mit farbiger Schrift; eigene Rückfragen statt Browser-Dialogen; Pin und Tauschen mit mehr Abstand",
        "Items: große Bilder, Preis an zweiter Stelle, alle Einträge ohne Grenze",
    ]),
    ("0.8.1", "10.11.2026", [
        "Dunkle Ansicht: Hover-Karte und Hinweise wieder wie vor 0.7.1; nichts ist dunkler als die Team-Plätze, Festhalten macht nichts heller",
        "Liste: größere Bilder und Netze; Stern, Pokéball und Team-Häkchen stehen genau dort, wo die Knöpfe sind, und sind größer",
        "Hover-Karte: Angriff (mit den eigenen Typen), Verteidigung und „gut einzusetzen gegen“ statt doppelter Listen",
        "Detailseite: Fangchance sortierbar und mit Paralyse, Gift und Verbrennung; „Alle entfernen“ für die eigene Attacken-Auswahl",
        "Sortieren überall: Text erst A–Z, Zahlen erst absteigend, dann umgekehrt, beim dritten Klick wie am Anfang",
        "Artworks: alte Ersatzbilder aus dem Browser-Speicher werden ersetzt",
        "Team: „aus deiner Sammlung“ statt „Gefangene“, Verbesserungen untereinander mit der zu ersetzenden Attacke fett, Gegner beim Ziehen mit Zielrahmen",
        "Attacken: Beschreibung erscheint am Namen, nicht mehr bei der Klasse",
    ]),
    ("0.8.0", "10.11.2026", [
        "Items: Bilder (nach dem nächsten Abgleich), Spalte „Art“ mit Filter, sortierbare Spalten, gemerkte Tasche",
        "Items je Tasche: Medizin und Bälle mit Wirkung (etwa „KP +20“, „Fangfaktor ×1,5“), Maschinen mit Attacke, Typ, Stärke und AP",
        "Unfertige Einträge mit Platzhaltern wie [VAR] sind ausgeblendet und nur auf Wunsch zu sehen",
        "Attacken: Kurz-Info jetzt für alle Status-Attacken (147 gepflegte Texte, etwa für Schutzschild, Tarnsteine, Delegator)",
        "Einstellungen: Spieldaten als ZIP herunterladen (Datenbank, Protokoll, Übersicht fehlender Bilder)",
        "„Zu erledigen“: Auftrag für einen KI-Chat kopieren, Antwort einlesen mit Vorschau, Liste als CSV",
        "Karte: Pokémon-Auswahl mit Bildern und Suche",
    ]),
    ("0.7.1", "10.11.2026", [
        "Fehler behoben: Ovale an den Pin-Nadeln und in der Typtabelle, verschobene Spalte beim Festhalten",
        "Liste: Marken auf der Bildecke statt hinter dem Namen, richtiger Pokéball, Knöpfe unter dem Bild",
        "Hover-Karte breiter und dunkler; Schwächen und Duelle als Zeilen je Multiplikator; „im Vorteil“ und „im Nachteil“ "
        "statt „stark“ und „schwer“, mit ↑ austeilen und ↓ einstecken",
        "Dunkle Ansicht: Auswahl, Verbesserungen und Hinweise dunkler abgesetzt statt heller",
        "Detailseite: Verteidigung, Duell, Entwicklung und Fangchance als eigene Karten; Fangchance offen, solange nicht gefangen; "
        "eigene Attacken-Auswahl nach Spalten sortierbar; schillernd als Artwork (nach dem nächsten Abgleich)",
        "Team: Typwirkung je Mitglied und „Gegen Gegner“ mit Linien, Fadenkreuz und Festhalten; Gegner per Ziehen umsortieren",
        "Attacken: Kurz-Info zur Wirkung (etwa „Angriff −1 (Gegner)“), Beschreibung beim Hovern, feste Spaltenbreiten; "
        "keine Texte „kann nicht eingesetzt werden“ mehr, wenn es einen älteren Text gibt",
        "Typtabelle größer; Karte lädt nur den sichtbaren Ausschnitt, Zoom-Knöpfe auf der Karte",
        "Nach einem Update mit neuen Tabellen startet der Abgleich von selbst",
    ]),
    ("0.7.0", "10.11.2026", [
        "Attacken: bewährte Sets aus Pokémon Showdown (Random Battle) für die Generation des Spiels, mit Rolle und "
        "Fähigkeit; „Übernehmen“ setzt die vier stärksten lernbaren als eigene Auswahl",
        "Attacken: Marken für Lehrer-Attacken und Beherrschung (Legenden: Arceus) hinter dem Namen",
    ]),
    ("0.6.1", "10.11.2026", [
        "Neuer Reiter „Items“: alle Items des Spiels mit Tasche, Beschreibung und Preis, mit Suche",
        "Detailseite: „Mehr Details“ zum Aufklappen mit Fangchance je Ball (volle KP, 1 KP, schlafend), Geschlecht, "
        "Wachstum, Ei-Gruppen und EV-Ausbeute, je nach Spiel",
        "Detailseite: schillerndes und animiertes Sprite zum Umschalten, Ruf zum Anhören (lädt der Abgleich mit den Bildern)",
        "Attacken: TM-Nummer des Spiels statt nur „TM“",
    ]),
    ("0.6.0", "09.11.2026", [
        "Neuer Reiter „Karte“ für Legenden: Arceus: alle Spawnpunkte je Gebiet zum Ziehen und Zoomen, Alpha rot, "
        "beim Hovern wer dort erscheint, beim Klick mit Anteil, Tageszeit und Wetter",
        "Fundorte mit Tageszeit und Wetter (aus den Spawn-Tabellen) und Link „Karte“, der die Spawnpunkte des Pokémon hervorhebt",
        "Feste Begegnungen (Geschenke, Legendäre, einmalige Pokémon) als eigene Zeilen in den Fundorten",
        "Abgleich lädt die Kartenbilder einmal und hält sie im Datenordner",
    ]),
    ("0.5.1", "09.11.2026", [
        "Verbindungstest prüft weitere Quellen: feste Begegnungen (Geschenke, Legendäre) und Raids aus PKHeX, "
        "Werte je Form in Legenden: Arceus, schillernde und animierte Sprites, Rufe, Showdown-Stufen und Random-Battle-Sets",
        "Verbindungstest zeigt, was die Datenbank schon hat, aber noch nicht nutzt (TM, Wesen, Ei-Gruppen, Fangraten, Beeren)",
        "Abgleich holt TM-Listen, Wesen, Ei-Gruppen und Beeren auch ohne Dateiliste von GitHub",
    ]),
    ("0.5.0", "09.11.2026", [
        "Fundorte in Legenden: Arceus aus den Spieldaten (PKHeX): je Gebiet die Stellen mit Level, Alpha-Level und Art "
        "(frei, Raum-Zeit-Verzerrung, Baum oder Erzbrocken, Massenauftreten)",
        "Filter „Gebiet“ in der Liste und bei der Teamsuche: nur Pokémon, die dort frei vorkommen",
        "PKHeX als neue Quelle im Abgleich und unter „Quellen und Lizenzen“",
    ]),
    ("0.4.2", "09.11.2026", [
        "Verbindungstest prüft auch mögliche neue Quellen: Items (PokéAPI, Showdown, PKHeX), Fundorte aus den Spieldaten "
        "(PKHeX für Legenden: Arceus, Karmesin/Purpur, Legenden: Z-A), Wikis (PokéWiki, Bulbapedia, Serebii, Pokémon Database), "
        "Karten (Map Genie) und Kampfdaten (Smogon)",
        "Probe-Seiten der Quellen zum Herunterladen, damit sich Leser für sie bauen lassen",
    ]),
    ("0.4.1", "09.11.2026", [
        "Hover-Karte mit eigenem, getöntem Hintergrund und kräftigerem Rahmen, damit sie sich von den Karten abhebt",
    ]),
    ("0.4.0", "09.11.2026", [
        "Kopfzeile und Team-Leiste gleiten beim Scrollen sanft weg und kommen beim Hochscrollen zurück",
        "Gefangen (Pokéball) je Spiel: Empfehlungen daraus im Team, Filter „nur Gefangene“ oder „nur Favoriten“, Teamsuche nur aus Gefangenen",
        "„Im Duell gegen Typen“ auf Hover-Karte und Detailseite: klar stark, stark, schwer, mit der Rechnung beim Hovern",
        "Marken (im Team, gefangen, Favorit) direkt hinter dem Namen; Knöpfe zum Setzen beim Hovern auf dem Bild",
        "Filter: „bis“ oder „nur“ Generation, „stark gegen“ wahlweise nur klar",
        "Deine Attacken als feste Liste mit vier Zeilen, Auswahl in der Tabelle hinterlegt, Status-Attacken offen mit Wirkung",
        "Team: Sortierung bleibt sichtbar, Abweichungen in Verbesserungen und Teamsuche hinterlegt, volles Team fragt nach dem Platz",
        "Ziehen aus der Suche ins Team und auf Favoriten oder Gefangene; Gegner mit rotem Rahmen und Namen; Vorteil, Nachteil, ausgeglichen",
        "Attacken mit Farben für die Werte, Hinweise zu Vorrang und Kontakt; PokéWiki-Links an Attacken, Fähigkeiten und Orten",
        "Ansicht per rundem Knopf (System, Hell, Dunkel), Version rechts daneben, Stand des letzten Abgleichs in der Kopfzeile",
        "Spielauswahl nach Generationen gruppiert; Versionen schließen per Klick daneben",
        "Einstellungen: Sicherung herunterladen und wieder einlesen, Kopieren erst, wenn es etwas gibt",
    ]),
    ("0.3.0", "09.11.2026", [
        "Nintendo-Rot, dezentere Linien; Klick auf den Titel lädt alles neu",
        "Netzdiagramm mit Speichen und Ringen; außen = Höchstwert aller Pokémon, an den Ecken eine Skala von 0 bis 10",
        "Team: dasselbe Pokémon darf mehrfach hinein, Plätze per Drag & Drop umsortieren, Sortieren nach Werten",
        "Gespeicherte Teams ändern sich erst mit „Speichern“; bis dahin „Verwerfen“ möglich",
        "Favoriten je Spiel (☆): Klick auf einen leeren Platz oder ⇄ tauscht schnell ein",
        "Hinweis, wenn Team-Mitglieder nicht zum gewählten Spiel passen",
        "Hover-Karten auch im Team, in der Team-Leiste, bei Verbesserungen und Gegnern",
        "Filter „stark gegen Typ“; ausgeschlossene Typen rot umrandet und durchgestrichen; Festgesetzte grün",
        "Attacken: Reihenfolge per Ziehen, Standard-Attacken wie im Spiel, beigebrachte Attacken (TM, Lehrer) hinzufügen",
        "„Zurück“ führt dorthin, woher du kamst; Tabellen: dritter Klick stellt die ursprüngliche Reihenfolge her",
        "Typtabelle: Zeile und Spalte per Klick festhalten, Hinweise mit Typ-Bubbles",
        "Protokoll und Verbindungstest kopieren oder herunterladen; eigene Daten als JSON herunterladen",
    ]),
    ("0.2.1", "09.11.2026", [
        "Version in der Kopfzeile; nach einem Update erscheint einmal ein Hinweis, was neu ist",
    ]),
    ("0.2.0", "09.11.2026", [
        "Liste: Hover-Karte mit Artwork, Netzdiagramm und Schwächen, Typ-Filter als Bubbles (und/oder, ausschließen), "
        "Zurücksetzen, Nachladen beim Scrollen, Links lassen sich in neuem Tab öffnen",
        "Team-Leiste unten in jedem Reiter mit Drag & Drop und „+“ auf jeder Karte",
        "Teams je Spiel speichern sich selbst, mit Level und vier Attacken je Mitglied und Verbesserungsvorschlägen",
        "Detailseite: Spielwahl, Level ohne Neuladen, eigene Attacken-Auswahl, mehr Hover-Infos",
        "Team-Ansicht: alle Filter, Gegner-Team mit bis zu sechs Pokémon",
        "Attacken: alle Attacken je Spiel inklusive Status, mehr Filter, sortierbare Spalten",
        "Typtabelle: lesbare Kopfzeile, Linien, Legende, Hervorhebung von Zeile und Spalte",
        "Offizielle Artworks in 475 × 475 zusätzlich zu den Sprites",
    ]),
    ("0.1.0", "09.11.2026", [
        "Erste Version als Dienst: Abgleich mit PokéAPI und Showdown, Liste, Detailseite, Team-Planer, Typtabelle",
    ]),
]

# Das Tool gibt sich immer als es selbst zu erkennen. Antwortet eine Quelle mit einer Sperre
# (403, 429) oder einer Prüfseite, hört es auf, statt sich zu tarnen.
USER_AGENT = f"pokedex/{VERSION} (privates Nachschlage-Tool)"
BLOCKED = (403, 429)
MAX_BODY = 40 << 20      # größte Antwort: pokemon_moves.csv hat gut 10 MB


def blocked_target(url):
    """Grund, warum das Tool eine Adresse nicht abruft, sonst "". Abgerufen wird nur das
    öffentliche Internet, damit nie Geräte im Heimnetz angesprochen werden."""
    p = urllib.parse.urlsplit(str(url or ""))
    if p.scheme not in ("http", "https"):
        return "nur http und https"
    if p.username or p.password:
        return "Adresse mit Zugangsdaten"
    try:
        port = p.port or (443 if p.scheme == "https" else 80)
        infos = socket.getaddrinfo(p.hostname or "", port, proto=socket.IPPROTO_TCP)
    except (OSError, ValueError, UnicodeError):
        return ""
    for info in infos:
        try:
            ip = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        except ValueError:
            continue
        if not ip.is_global:
            return "Adresse nicht öffentlich"
    return ""


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nur ins öffentliche Internet."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        why = blocked_target(newurl)
        if why:
            raise urllib.error.URLError(f"Weiterleitung abgelehnt: {why}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirect)


class FetchError(Exception):
    def __init__(self, url, status, detail=""):
        super().__init__(f"{status} bei {url} {detail}".strip())
        self.url, self.status = url, status


def _inflate(raw, wbits):
    d = zlib.decompressobj(wbits)
    out = d.decompress(raw, MAX_BODY + 1)
    if len(out) > MAX_BODY:
        raise ValueError("Antwort zu groß")
    return out


def _decode(raw, enc):
    if enc == "gzip":
        return _inflate(raw, 16 + zlib.MAX_WBITS)
    if enc == "deflate":
        try:
            return _inflate(raw, zlib.MAX_WBITS)
        except zlib.error:
            return _inflate(raw, -zlib.MAX_WBITS)
    return raw


def request(url, timeout=40, encoding="gzip, deflate", headers=None, raw=False):
    """HTTP GET ohne Ausnahme: liefert Status, Text (mit raw die Bytes unter „body“) und Kopfdaten
    für den Verbindungstest."""
    head = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
        "Accept-Encoding": encoding,
        **(headers or {}),
    }
    out = {"url": url, "status": 0, "text": "", "enc": "", "server": "", "error": blocked_target(url)}
    if out["error"]:
        return out
    try:
        try:
            resp = _opener.open(urllib.request.Request(url, headers=head), timeout=timeout)
        except urllib.error.HTTPError as e:
            resp = e                      # Fehlerseiten haben auch einen Inhalt
        with resp:
            body = resp.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise ValueError("Antwort zu groß")
            out["status"] = getattr(resp, "status", None) or resp.getcode()
            out["enc"] = (resp.headers.get("Content-Encoding") or "").lower()
            out["server"] = resp.headers.get("Server") or ""
            if out["enc"] not in ("", "identity", "gzip", "deflate") and encoding != "identity":
                return request(url, timeout, "identity", headers, raw)
            data = _decode(body, out["enc"])
            if raw:
                out["body"] = data
            else:
                out["text"] = data.decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
    except Exception as e:                # Zeitüberschreitung, DNS, TLS
        out["error"] = str(e)[:160]
    return out


def fetch(url, timeout=40, headers=None, raw=False):
    """HTTP GET, gibt Text zurück, mit raw die Bytes. Wirft FetchError mit Statuscode."""
    r = request(url, timeout, headers=headers, raw=raw)
    if r["error"]:
        raise FetchError(url, 0, r["error"])
    if r["status"] >= 400:
        raise FetchError(url, r["status"])
    return r.get("body", b"") if raw else r["text"]


def challenge(text):
    """Prüfseite statt Inhalt (Cloudflare „Just a moment…“), sonst ""."""
    t = str(text or "")[:200_000]
    if "cf_chl_opt" in t or "<title>Just a moment" in t:
        return "Prüfseite von Cloudflare"
    return ""
