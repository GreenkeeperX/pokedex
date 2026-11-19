# Spielprofile

Was in welchem Spiel gilt, steht seit 0.60.0 an einer Stelle: `app/spiele.py`. Server und Oberfläche fragen
Eigenschaften des Profils („gibt es Zucht?“), nicht mehr die Kennung des Spiels („ist es Legenden: Arceus?“). Ein Test
(`Spiele.test_server_fragt_das_profil`, `Spiele.test_oberflaeche_fragt_das_profil`) hält das fest.

## Aufbau

- `grund(gen)`: das Übliche einer Generation, ein Hauptspiel ohne Besonderheiten.
- `SPIELE`: je Spiel die Generation und nur, was davon abweicht. Eine Erweiterung (`hauptspiel`) übernimmt zuerst, was
  bei ihrem Hauptspiel steht; `hauptspiel` und `lernliste` erbt sie nicht.
- `profil(kennung, gen=None)`: das fertige Profil mit allen Feldern, nur lesbar. `gen` ist die Generation aus der
  Datenbank; sie geht der des Eintrags vor (wie überall sonst im Server).
- `basis(kennung)`: das Spiel, dessen Texte und Trainer gelten (Hauptspiel einer Erweiterung, sonst das Spiel).
- `OBERFLAECHE`, `fuer_oberflaeche(p)`: die Felder, die `/api/meta` je Spiel unter `profil` mitgibt; `app.js` liest sie
  über `PROFIL()`.
- `EIGENE`: Spiele, die die PokéAPI nicht führt (Feld `eigen` mit dem Namen); der Importer legt sie an
  (`importer.EIGENE_SPIELE` verweist darauf).
- `pruefe()`: Fehler in `SPIELE` als Liste (unbekanntes Feld oder unbekannter Wert, Hauptspiel ohne Eintrag oder selbst
  Erweiterung, andere Generation als das Hauptspiel). Ein Test verlangt eine leere Liste.

In `abfragen.py` gibt `profil(g)` das Profil zu einem Spiel aus `D.games` (ohne Spiel: das Übliche der neuesten
Generation), `profil_von(D, kennung)` zu einer Kennung. Ein Spiel der Datenbank ohne Eintrag läuft als Hauptspiel seiner
Generation und steht im Fehlerregister („Spiel ohne Profil“), ebenso eine abweichende Generation.

## Felder

| Feld | Werte | bedeutet | gelesen von |
|---|---|---|---|
| `gen` | Zahl | Generation (Typtabelle, Basiswerte, Schadensformel, Fangformel der Hauptreihe) | überall; in der Oberfläche `GEN()` aus `gen` des Spiels |
| `hauptspiel` | Kennung oder leer | Erweiterung oder Schwester-Edition: Texte und Trainer vom Hauptspiel, Maschinen dazu | `pick_text`, `trainer_list`, `item_list`, `learn_game` |
| `lernliste` | `eigene`, `hauptspiel` | wessen Lernliste gilt (die PokéAPI führt Lehrer und TMs der Erweiterungen beim Hauptspiel) | `learn_game` |
| `schaden` | `hauptreihe`, `lgpe`, `la` | Schadensformel: die der Generation, Let's Go (AV statt EV, ohne Items und Fähigkeiten), Legenden: Arceus | `damage_view` |
| `typfaktoren` | `hauptreihe`, `la` | ×2 und ×0,5 oder ×2,5 und ×0,4 mit Eigentyp ×1,25 | `chart_of` |
| `fangformel` | `genau`, `gen12`, `letsgo`, `legenden`, `hisui`, `keine` | wie die Fangchance rechnet; `gen12`, `letsgo`, `legenden` sind Richtwerte (`FANG_GROB`), `keine`: keine Tabelle | `_more`, `catchHtml` |
| `baelle` | `standard`, `hisui` | Balltabelle | `_more`, `ballOf` |
| `werte` | `dv`, `ev`, `av`, `el`, `ohne` | Statuswerte: DV und Stat Exp, EV, AV, Effort Levels, nicht gerechnet | `stats_view`, `_more` (EV-Ausbeute), `STATS_OK()`, `LA()`, `statBox` |
| `faehigkeiten` | ja/nein | gibt es Fähigkeiten | `no_abilities`, `noAbil()` |
| `zucht` | ja/nein | Eier und Pension: Weg „Zucht“, Ei-Gruppen und Ei-Zyklen | `missing`, `_more` |
| `tera` | ja/nein | Tera-Typ je Team-Platz | `team_view`, `TERA()` |
| `raids` | Kennung oder leer | Spiel, unter dem die Tera-Raids liegen; Reiter Raids | `detail`, `missing`, `RAIDS()` |
| `auftraege` | Kennung oder leer | Schlüssel, unter dem Aufträge und Haken liegen; Reiter Aufträge | `request_list`, `detail`, `_quests_de`, `REQ_GAME()` |
| `blaubeer` | ja/nein | die Aufträge sind die Blaubeer-Missionen (eigene Tabelle) | `request_list` |
| `forschung` | ja/nein | Forschungsaufgaben | `detail`, `candidates` (Sortierung), Filter der Liste |
| `crypto` | ja/nein | Crypto-Pokémon | `detail` |
| `kampf` | ja/nein | Kampfspiel: Kader statt Sammlung, Reiter Kampf statt Karte, Level 50 fest, Doppelkampf | `damage_view`, `BATTLE()` |
| `spawnkarten` | ja/nein | Einzelkarten mit Spawnpunkten, eigene Punkte auf der Karte von Map Genie | `_mg_map`, `/api/mapgenie/eigene`, Karte in `app.js` |
| `eigene_dexe` | ja/nein | eigene Pokédexe (Tabelle `pokopia`) | `_pokopia` |

Die Spiele mit Abweichungen: Rot/Grün und Blau (Japan) mit Hauptspiel Rot/Blau; Colosseum und XD (Crypto, keine Zucht);
Let's Go (Formel `lgpe`, AV, keine Fähigkeiten, keine Zucht); die Erweiterungen von Schwert/Schild und Karmesin/Purpur
(Lernliste vom Hauptspiel); Legenden: Arceus (eigene Schadens-, Typ- und Fangformel, Hisui-Bälle, Effort Levels,
Aufträge, Forschung, Spawnkarten); Karmesin/Purpur (Tera, Raids, Blaubeer-Missionen); Legenden: Z-A (Richtwert beim
Fangen, keine Zucht, Aufträge) und Mega-Dimension als seine Erweiterung (eigene Lernliste); Champions (Kampfspiel, keine
Fangtabelle, keine Werte); Pokopia (von der PokéAPI nicht geführt, eigene Dexe, keine Werte).

## Ein neues Spiel

1. Eintrag in `SPIELE` mit der Generation; bei einer Erweiterung `hauptspiel` (und `lernliste: "hauptspiel"`, wenn die
   PokéAPI für sie keine eigene Lernliste hat). Führt die PokéAPI das Spiel nicht, `eigen` mit dem Namen.
2. Nur, was abweicht, als Feld. Passt ein Feld nicht, kommt ein neuer Wert in `FELDER` und die Stelle, die ihn liest.
3. `python3 -m unittest tests.test_all`: `Spiele` prüft den Eintrag, `Welt.test_spielprofil` jedes Spiel der
   Mini-Datenbank. Ändert sich, was die Oberfläche bekommt, `python3 -m tests.vertrag`.
4. Was das Spiel wirklich Neues kann (eigene Formel, eigene Tabelle), bleibt eine eigene Funktion; das Profil sagt nur,
   dass sie gilt.

## Was nicht im Profil steht

- Regeln, die nur an der Generation hängen: Schaden je Generation (`schaden.py`), Typtabelle (`typen.py`), physisch
  oder speziell nach Typ bis Generation 3, Kritfaktor, Wetter ab Generation 2, Wesen ab Generation 3, Minzen ab
  Generation 8. Sie fragen `gen`.
- Welche Seite oder Datei einer Quelle zu welchem Spiel gehört (Map Genie, PokéWiki, Serebii, PKHeX, Bulbapedia,
  RankedBoost, IGN, PokéEarth, Raid-Nester): Das bleibt bei der Quelle, weil es zur Quelle gehört und sich mit ihr ändert.
- Schlüssel von Tabellen, die genau einem Spiel gehören (`fangrate`, Forschung, Aufträge von Legenden: Arceus):
  `abfragen.LA` und `abfragen.ZA` nennen sie; die Oberfläche speichert Haken der Spawnkarten unter `MAPSPIEL`.
- Einstiegswerte der Karten je Spiel (`MGSTART`, `MGFIRST`, `MG_EDITION` in `app.js`): Darstellung, keine Spielregel.

## Offen

Angenommen statt belegt (Einzelheiten in `docs/formeln.md`, „Spiele ohne eigene Formel“): Legenden: Z-A und
Mega-Dimension rechnen wie die Hauptreihe der Generation 9; Pokopia bekommt die Fangtabelle der Generation 9.
