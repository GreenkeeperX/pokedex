# Tests

Ein Aufruf führt alles aus, was ohne Netz und ohne echte Spieldaten prüfbar ist:

    python3 -m unittest tests.test_all

Stand 0.59.0: 186 Tests in rund 15 Sekunden, davon 8 nur mit einer echten Datenbank (sonst übersprungen). Die Tests
brauchen nur die Python-Standardbibliothek; der Selbsttest der Oberfläche zusätzlich ein Chromium oder Chrome.

## Was wo läuft

| Klasse (Datei) | prüft | CI | lokal |
|---|---|---|---|
| `Typen`, `Attacken`, `Team`, `TeamPlaetze`, `Rechnen`, `Version` (`tests/test_all.py`) | Rechenlogik ohne Datenbank; Schaden gegen `tests/schaden_referenz.json` | ja | ja |
| `Leser` | Leser der Quellen mit erfundenen Ausschnitten (Showdown, Smogon, Wikis, Karten) | ja | ja |
| `Abgleich`, `Betrieb`, `Fehler` | Abgleich mit Attrappe statt Netz, Neustart mitten im Lauf, Ruhezeiten, Fehlerregister | ja | ja |
| `Wiederherstellung`, `WiederherstellungHttp` | Wiederherstellungstest: bestanden mit unberührtem Datenordner, alte Sicherung lädt, kaputte Sicherung und unlesbare Einträge, monatlich im Zeitplan, „jetzt prüfen“ | ja | ja |
| `Leistung`, `LeistungOhneDaten` | Leistungstest über HTTP: alle Wege beantwortet, kein Netz, `user.db` unverändert, kein temporärer Ordner übrig, gespeichert (die letzten zehn); gesperrt während eines Abgleichs und doppelt; gescheiterter Weg | ja | ja |
| `Tausch` | Tauschliste: Editionen der Mini-Welt (Suche, Biete, gefangen), ohne Edition, HOME, Fundorte ohne Editionen; Gruppen mit erfundener Antwort von „Was fehlt“ (Kette über Ei, Tausch-Entwicklung, ohne Weg nicht zum Kopieren) | ja | ja |
| `Eikette` | Ei-Attacken-Kette in der Mini-Welt: selbst, Kette über eine Ei-Gruppe, Vater derselben Familie, Gefangene zuerst, geschlechtslos (nur Ditto), keine Ei-Attacke, Spiegelkraut (auch geschlechtslos), falsche Parameter; mit echter Datenbank Glumanda (Prügler) über zwei Schritte und Volttackle-Pichu | ja | ja |
| `Jagd`, `JagdHttp` | Shiny-Quoten gegen die Werte der Quellen (Legenden: Arceus, Karmesin/Purpur, SOS-Kette, Fang-Kombo wie in `spielwissen.json`, Schwert/Schild), Brüche der Quelle, „bis jetzt“ über Stufen; Jagd anlegen, zählen, ändern, abschließen (setzt schillernd), Shiny-Sperre, Sicherung und Rückspielen | ja | ja |
| `Fortschritt` | Fortschritt je Spiel und in HOME mit denselben Zahlen wie „Was fehlt mir noch“, Summen nach Generation, Was fehlt in HOME | ja | ja |
| `Statuskarte`, `StatuskarteHttp` | Gesamtstatus und Gründe der Statuskarte (Stufen, Grenzen für Platz und Sicherung, nicht lesbarer Platz), `/api/statuskarte` ohne Spieldaten | ja | ja |
| `Server`, `Http` | Server-Hilfen und der Server über HTTP auf einem freien Port, ohne Spieldaten; dazu die Skripte der Oberfläche (jede Datei genau einmal in `index.html`, Kennung je Datei) | ja | ja |
| `Heimnetz` | `sources.blocked_target`: keine Abrufe an private, lokale, reservierte Adressen, auch nicht über Weiterleitung | ja | ja |
| `Spiele` | Spielprofile: Einträge in Ordnung, dieselben Aussagen wie die früheren Listen je Spiel, Server und Oberfläche fragen das Profil statt der Kennung | ja | ja |
| `Pakete` | jeder Name der Module in `app/abfragen/` und `app/abruf/` ist unter dem Paket dasselbe Objekt; Importe im Paket zeigen auf `app`; Tests ersetzen Namen nur mit `im_paket` | ja | ja |
| `Oeffentlich` | nichts Privates im Repository (Dateiliste, Muster für Adressen und Zugangsdaten) | ja | ja |
| `MiniBau` (`tests/mit_daten.py`) | der Importer baut die Mini-Datenbank, Selbstprüfung greift | ja | ja |
| `Welt` | Abfragen der Oberfläche gegen die Mini-Datenbank (Liste, Detail, Lernlisten, Fundorte, Items, Team, Schaden, Import und Export) | ja | ja |
| `ServerMitDaten` | alle Wege des Servers über HTTP mit Spieldaten, eigene Daten, Zwischenspeicher | ja | ja |
| `Vertrag` | Form der Antworten (`tests/vertrag.json`), die Oberfläche kennt jedes Feld, jeder Weg hat einen Aufrufer | ja | ja |
| `Selbsttest` | die echte Oberfläche im Browser ohne Fenster: 79 Schritte, 5 Spiele mit allen Reitern, dazu die Reiter je Spielprofil in 4 weiteren, 1366 × 768 | ja, Pflicht | ja, wenn ein Browser da ist |
| `MitDatenbank` (`tests/test_all.py`) | Stichproben gegen echte Spieldaten (Namen, Zahlen, Fundorte echter Pokémon) | nein | nur mit `POKEAPI_DB` |

Die CI (`.github/workflows/tests.yml`) läuft bei jedem Pull Request. Sie setzt `POKEDEX_SELBSTTEST=muss`: Fehlt dort
der Browser, scheitert der Lauf, statt den Selbsttest still zu überspringen. Lokal wird der Selbsttest ohne Browser
übersprungen; `POKEDEX_BROWSER=/pfad/zu/chromium` nennt einen.

## Nur lokal

- **Echte Datenbank.** `POKEAPI_DB=./data/pokeapi.db python3 -m unittest tests.test_all` führt zusätzlich `MitDatenbank`
  aus. Die CI hat keine echte Datenbank (kein Netz in den Tests, keine fremden Spieldaten im Repository). Vor einer
  Version, die Abfragen oder den Importer ändert, gehört dieser Lauf dazu.
- **Vertrag neu schreiben.** Ändert sich eine Antwort mit Absicht: `python3 -m tests.vertrag`, die Änderung steht dann im
  Diff von `tests/vertrag.json`.
- **Gerüst der Mini-Datenbank.** `python3 tools/minidb_geruest.py /pfad/zu/den/csv` schneidet es neu aus den
  CSV-Dateien der PokéAPI; nötig, wenn ein Spiel dazukommt.
- **Vergleichswerte der Schadensrechnung.** `tools/schaden_referenz.js` (braucht Node und `@smogon/calc`).

## Was kein Test abdeckt

- Die Quellen selbst: ob eine Seite noch so aussieht, wie der Leser sie erwartet, zeigt der Verbindungstest in den
  Einstellungen und die Gegenprüfung nach dem Abgleich (`docs/abrufe.md`).
- Daten, die nicht aus PokéAPI, Showdown oder `extra/` kommen (PKHeX, Wikis, Karten): Die Mini-Datenbank enthält sie
  nicht. Ihre Leser haben eigene Tests mit erfundenen Ausschnitten; das Zusammenspiel prüft nur `MitDatenbank` und
  auch das nur, soweit die lokale Datenbank diese Quellen enthält.
- Der Container (Härtung, Rechte am Datenordner) und die Geschwindigkeit auf dem Server.

## Namen in Paketen ersetzen

`app.abfragen` und `app.abruf` sind Pakete: Jede Funktion liest Namen aus ihrem eigenen Modul. Ein
`mock.patch.object(abruf, "sleep", …)` ersetzte nur den Namen im Paket, die Funktionen sähen weiter das Original. Tests
nehmen deshalb `tests.basis.im_paket(paket, name, neu)`; es ersetzt den Namen im Paket und in jedem Modul, das ihn
definiert oder importiert hat. `Pakete.test_ersatz_im_paket` lässt einen Test scheitern, der es anders versucht.

## Mini-Datenbank

`tests/minidb.py` beschreibt eine erfundene Welt: 14 Arten mit Formen, 25 Attacken, Items, Orte, Begegnungen, getragene
Items. Nichts davon gibt es im Spiel. Dazu kommt ein Gerüst echter Bezeichner (`tests/minidb_geruest.json`: Spiele,
Editionen, Dexe, Typen mit Typtabelle, Statuswerte), an denen die Regeln des Programms hängen; es stammt aus der PokéAPI
(BSD-3-Clause, `tests/minidb_LIZENZ.txt`). Der echte Importer baut daraus in rund 0,2 Sekunden eine `pokeapi.db`, einmal
je Testlauf.

Die Tests erwarten, was in `tests/minidb.py` steht, und rechnen die Antworten dagegen nach. Braucht eine neue Regel
einen neuen Fall, kommt er in die Welt, nicht als abgeschriebene Zahl in den Test.

## Vertrag zwischen Server und Oberfläche

`tests/vertrag.json` hält für 33 Aufrufe fest, welche Felder eine Antwort hat und von welcher Art sie sind. Der Test
`Vertrag` prüft drei Dinge: Die Antworten haben diese Form; die Oberfläche (alle Skripte in `app/static/js/`) kennt jedes Feld; jeder Weg des
Servers hat einen Aufrufer in der Oberfläche. Ausnahmen stehen mit Namen in der Klasse (`UNGELESEN`, `OHNE_AUFRUFER`).
Leere Listen haben keine Form: Was die Mini-Datenbank nicht enthält, sichert der Vertrag nicht.

## Selbsttest der Oberfläche

`tests/ui_selbsttest.html` lädt die Oberfläche in einen Rahmen von 1366 × 768 Bildpunkten und geht einen Plan durch,
den der Test aus der Welt ableitet: je Spiel alle Reiter, zwei Detailseiten, Karte, Einstellungen; dazu die Reiter, die
es nur nach dem Spielprofil gibt (Kampf, Aufträge, Raids), und dass sie in anderen Spielen zur Karte führen. Das Spiel
wechselt die Seite im Rahmen selbst (wie eine Auswahl in der Liste), danach öffnet sie die Ansicht. Je Schritt gilt:
keine Ausnahme, kein `console.error`, keine Antwort ab 500, kein Hinweis über der Ansicht, keine Fehlermeldung in der
Ansicht, der erwartete Text steht da, nichts ragt seitlich aus dem Fenster. Die Seite misst nebenbei, wie lange der
Inhalt einer Antwort nach ihren Kopfzeilen braucht. Sie liegt nicht im Image; nur der Test liefert sie aus.
