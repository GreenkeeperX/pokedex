# Formeln: Schaden, Statuswerte, Typwirkung, Fangchance

Was der Pokédex rechnet, woher die Formel stammt und wie sie abgesichert ist. Regel: keine Formel aus dem Gedächtnis.
Jede steht hier mit Quelle; wo eine Quelle etwas offenlässt, steht das unter „Offen“.

Die Rechnung liegt in `app/schaden.py` (Schaden), `app/effort.py` (Werte in Legenden: Arceus), `app/typen.py`
(Typwirkung) und `app/abfragen.py` (`catch_chance`, `catch_chance_la`). Tests: Klasse `Rechnen` und `test_fangchance` in
`tests/test_all.py`.

## Schaden je Generation

Quelle für die Reihenfolge und die Rundung: [smogon/damage-calc](https://github.com/smogon/damage-calc) (MIT-Lizenz),
Paket `@smogon/calc` 0.12.0, Dateien `mechanics/gen12.ts`, `gen3.ts`, `gen4.ts`, `gen56.ts`, `gen789.ts`, `util.ts`. Der Code
ist nachgeschrieben, nicht übernommen; der Pokédex braucht das Paket nicht.

`⌊x⌋` heißt abrunden. „Runden“ heißt hier die Rundung des Spiels ab Generation 5: ab mehr als ,5 auf, genau ,5 ab.

| | Grundschaden | danach der Reihe nach |
|---|---|---|
| Gen. 1 | `min(⌊⌊(2·L/5 + 2) · S · A / V⌋ / 50⌋, 997) + 2`; Volltreffer: Level doppelt; A oder V über 255: beide geviertelt | Eigentyp ⌊× 1,5⌋, Typ 1 ⌊⌋, Typ 2 ⌊⌋, Zufall 217–255 von 255 |
| Gen. 2 | wie Gen. 1; vor dem Deckel: Volltreffer × 2, dann Typ-Item ⌊× 1,1⌋ | Wetter ⌊⌋, Eigentyp ⌊× 1,5⌋, beide Typen als ein Produkt ⌊⌋, Zufall |
| Gen. 3 | `⌊⌊(2·L/5 + 2) · A · S / V⌋ / 50⌋`; Typ-Item ⌊× 1,1⌋ und Wahlband am Angriffswert | Fläche ⌊÷ 2⌋, Wetter ⌊⌋, physisch mindestens 1, + 2, Volltreffer × 2, Eigentyp ⌊× 1,5⌋, Typ 1 ⌊⌋, Typ 2 ⌊⌋, zuletzt Zufall 85–100 % ⌊⌋ |
| Gen. 4 | `⌊⌊(2·L/5 + 2) · S · A / 50⌋ / V⌋`; Typ-Item ⌊× 1,2⌋ und Techniker an der Stärke | Fläche ⌊× ¾⌋, Wetter ⌊⌋, + 2, Volltreffer × 2, Leben-Orb ⌊× 1,3⌋, Zufall ⌊⌋, Eigentyp ⌊× 1,5⌋ (Anpassung × 2), Typ 1 ⌊⌋, Typ 2 ⌊⌋, Expertengurt ⌊× 1,2⌋ |
| ab Gen. 5 | `⌊⌊(2·L/5 + 2) · S · A / V⌋ / 50⌋ + 2`; Faktoren an Stärke und Angriff in 4096steln verkettet und gerundet | Fläche (3072), Wetter (6144 oder 2048), Volltreffer × 2 (Gen. 5) oder ⌊× 1,5⌋, Zufall ⌊⌋, Eigentyp (gerundet), Wirkung ⌊⌋, Items am Schluss (Leben-Orb 5324, Expertengurt 4915; gerundet, mindestens 1) |

Sonderfälle, die das Review vom 13.11.2026 genannt hat, und was jetzt gilt:

- **Generation 3 und 4** rechneten bis 0.56.2 in der Reihenfolge ab Generation 5. Jetzt eigene Funktionen
  (`rolls_gen3`, `rolls_gen4`).
- **Generation 2:** Der Drachenzahn wirkt nicht, die Drachenhaut verstärkt Drache (im Spiel vertauscht;
  `TYPE_ITEMS_GEN2`). Der Volltreffer steht vor dem Typ-Item. Beide Typen des Ziels zählen als ein Produkt.
- **Tera:** Eigentyp-Bonus in 4096steln: 4096, + 2048 für einen ursprünglichen Typ, + 2048 für den Tera-Typ. Anpassung:
  + 2048, oder + 1024, wenn der Tera-Typ auch ein ursprünglicher Typ ist. Tera-Typ gleich Originaltyp mit Anpassung ergibt
  also 9216 / 4096 = × 2,25 (`stab_of`). Attacken des Tera-Typs unter Stärke 60 zählen mit 60, nach Techniker und Typ-Item,
  nicht bei Mehrfach-Treffern und Attacken mit Erstschlag.
- **Fähigkeiten des Verteidigers** wirken dort, wo das Spiel sie einrechnet (`DEF_ABILITY_WHERE`): Speckschicht am
  Angriffswert (Gen. 4: an der Stärke), Hitzeschutz und Trockenheit an der Stärke (Hitzeschutz ab Gen. 9 am Angriffswert),
  Flauschigkeit am Schluss. Vorher zählten sie alle wie ein weiterer Typ.
- **Wesen:** ganzzahlig × 110 / 100 oder × 90 / 100, abgerundet (`nature_amp`; so auch PKHeX, `NatureAmp.AmplifyStat`).
- **Was es in einer Generation nicht gibt, wirkt nicht:** Leben-Orb, Expertengurt, Wahlglas, Anpassung und Techniker
  erst ab Generation 4.

**Vergleichswerte.** `tests/schaden_referenz.json` enthält 550 Fälle aus `@smogon/calc` 0.12.0, erzeugt mit
`tools/schaden_referenz.js` (fester Startwert, ein neuer Lauf ergibt dieselbe Datei): Generation 1: 30, 2: 60, 3: 80,
4: 100, 5: 60, 6 bis 8: je 40, 9: 100. Der Test vergleicht je Fall alle 16 Schadenswerte (bis Generation 2: 39) und die
KP. Mit dem Stand 0.56.2 wichen bei Minimum oder Maximum ab: Generation 2: 6 von 60, Generation 3: 20 von 80,
Generation 4: 11 von 100, Generation 5 bis 9: 15 von 280.

Nicht eingerechnet (wie bisher): Statusprobleme, Statusstufen, Schilde, Felder, Fähigkeiten mit Bedingung. Das ist der
geplante „erweiterte Modus“ des Schadensrechners.

## Legenden: Arceus

### Schaden

    Grundschaden = ⌊ ⌊ ⌊(100 + Angriff + 15 × Level) × Stärke⌋ / (Verteidigung + 50) ⌋ / 5 ⌋

Danach der Reihe nach: Volltreffer × 1,5, Zufall 85 bis 100 % (ganzzahlig, abgerundet), Eigentyp × 5120 / 4096 = × 1,25
(genau ,5 rundet ab), Wirkung × 2,5 / × 2 / × 0,5 / × 0,4 (abgerundet). `schaden.rolls_la`, `schaden.calc_la`.

Quellen:

1. Smogon-Forum, „Legends: Arceus Battle Mechanics Research“
   (https://www.smogon.com/forums/threads/legends-arceus-battle-mechanics-research.3696826/), Beitrag 110 (31.07.2022):
   Rechnung aus dem zerlegten Spiel (Version 1.1.1), mit der Reihenfolge Grundschaden, Statusstufen, Regen/Feuer,
   Volltreffer, Zufall, Eigentyp (5120/4096), Wirkung (0,4 / 0,5 / 1 / 2 / 2,5), Statusprobleme.
2. Die Zerlegung selbst: https://gist.github.com/Lusamine/eae5afb01ad6cf3fe11e76bec8e3de17 mit den Funktionen
   `calc_initial_damage_LA` (dreimal abschneiden: nach × Stärke, nach ÷ (Verteidigung + 50), nach ÷ 5),
   `calc_attack_damage` (Faktoren in 4096steln: bis genau zur Hälfte ab, darüber auf; Zufall `Schaden × Wurf / 100`
   ganzzahlig) und `apply_damage_effectiveness_modifier` (Stufen: 0 = keine Wirkung, 1 bis 5 = × 0,4, 6 = × 0,5,
   7 = × 1, 8 = × 2, 9 bis 13 = × 2,5; abgeschnitten). Die Beiwerte 100, 15, 50 und 5 liest das Spiel aus einer
   Tabelle; sie stehen im Forum (Beiträge vom 12. bis 14.02.2022) und ergeben das Beispiel unten.
3. **Messung im Spiel** (Beitrag 107): Level 70, Angriff 204, Stärke 100 mit Eigentyp gegen Verteidigung 44 ergab
   305, 309, 312, 316, 320, 324, 327, 330, 334, 337, 341, 345, 349, 352, 356, 360. Die Formel oben liefert genau diese
   16 Werte (Test `test_legenden_arceus_schaden`); die Rundung der Hauptreihe läge bei fünf davon um 1 daneben. Der
   Pokédex rechnet für diese Werte (Basis 110 und 10, Level 70, Effort Level 0) auch Angriff 204 und Verteidigung 44.

Offen (so umgesetzt, aber nicht belegt):

- **Mindestens 1 Schaden.** Die gelesenen Funktionen kappen nicht nach unten; ob der Aufrufer es tut, steht nicht in den
  Quellen. Angenommen wie in der Hauptreihe. Betrifft nur Treffer, die rechnerisch 0 ergäben.
- **Nicht eingerechnet:** starker und schneller Stil, Statusstufen (× 1,5 und × 0,66), „Wilde Macht“ der Alpha-Pokémon
  (Werte × 1,5), Regen, Verbrennung, Frostbeule, Schläfrigkeit, Fixierung. Die Werte dazu stehen im Beitrag 110.

### Statuswerte und Effort Levels

    KP          = ⌊(Level/100 + 1) × Basis + Level⌋ + Bonus
    andere      = Wesen(⌊(Level/50 + 1) × Basis / 1,5⌋) + Bonus        Wesen: × 110 / 100 oder × 90 / 100, abgerundet
    Bonus       = (√Basis × Faktor + Level) / 2,5, kaufmännisch gerundet
    Faktor je Stufe 0–10: 0, 2, 3, 4, 7, 8, 9, 14, 15, 16, 25

Quelle: PKHeX, `PKHeX.Core/PKM/PA8.cs` (`GetStatHp`, `GetStat`, `GetGanbaruStat`) und `IGanbaru.cs` (Faktoren; Stufe aus
den DVs: 31 → 3, ab 26 → 2, ab 20 → 1). PKHeX prüft damit, ob die Werte eines Pokémon zum Spiel passen, und rechnet
deshalb wie das Spiel mit einfacher Genauigkeit; `effort.f32` bildet das nach. Dieselben Formeln nennen Bulbapedia
(„Effort level“) und Pokébip. Nur die Formel ist nachgeschrieben, kein Code übernommen (PKHeX steht unter GPL-3.0).

Geändert mit 0.57.0: Das Wesen wirkt auf den abgerundeten Grundwert (vorher auf den ungerundeten), und die Rechnung
folgt der einfachen Genauigkeit. Über alle Basiswerte 1 bis 255 und Level 1 bis 100 ändert sich damit bei neutralem
Wesen etwa 3 von 1000 Werten um 1, mit förderndem oder hemmendem Wesen gut 4 von 10.

### Typwirkung

Doppelt sehr effektiv × 2,5 statt × 4, doppelt nicht sehr effektiv × 0,4 statt × ¼, Eigentyp × 1,25 statt × 1,5
(`typen.for_la`, `typen.combine`). Quelle: `apply_damage_effectiveness_modifier` (oben) und der Forschungsfaden. Die
Regel hängt an der Typtabelle des Spiels (`typen.Chart.doppelt`, `.stab`); Detailseite, Typtabelle, Teambewertung,
Typ-Duell, Attacken-Wertung und Schadensrechner lesen sie von dort, die Oberfläche bekommt sie über `/api/typen`
(`doppelt`) und rechnet nur in `effMul` zusammen.

## Fangchance

Quelle: Bulbapedia, „Catch rate“ (https://bulbapedia.bulbagarden.net/wiki/Catch_rate).

    a = (3 × KPmax − 2 × KP) / (3 × KPmax) × Fangrate × Ball × Status        ab a = 255 fängt der Ball immer

| | Probe | Zahl der Proben |
|---|---|---|
| Gen. 1 und 2 | eigene Formeln; der Pokédex zeigt `a / 255` als Richtwert (`fang_grob`) | |
| Gen. 3 und 4 | `b = ⌊1048560 / ⌊√⌊√⌊16711680 / ⌊a⌋⌋⌋⌋⌋`, a mindestens 1 | 4 |
| Gen. 5 | `b = ⌊65536 × (a / 255)^0,25⌋` | 3 |
| ab Gen. 6 | `b = ⌊65536 × (a / 255)^0,1875⌋` | 4 |

Jede Probe gelingt mit `b / 65536`. Generation 5 und spätere kommen beide auf `(a/255)^0,75`. Bis 0.56.2 rechnete
Generation 5 mit dem Exponenten 0,1875 und drei Proben: Fangrate 45, volle KP, Pokéball zeigte 20,3 % statt 11,9 %.
Generation 3 und 4 rechneten mit `a / 255` (5,9 % statt 6,2 % im selben Fall).

Nicht eingerechnet: kritischer Fang (ab Generation 5), dunkles Gras, Fangkraft, Boni durch Level und Pokédex.

**Legenden: Arceus** (`catch_chance_la`, in der Oberfläche `fangLA`):

    a = 0,75 × Fangrate (+ 10 im Massenausbruch) + 30 × (Rang + KP-Faktor × Status × Ball × Verhalten × Rücken × Beere)
    b = 65535 × (1 − √(1 − a/255)), zwei Proben, eine muss gelingen

**Bälle aus Hisui.** Eine Tabelle, `abfragen.HISUI_BALLS`; die Oberfläche bekommt sie über `/api/meta` (`hisui_baelle`)
und führt keine eigene mehr (ein Test prüft das). Vorher gab es drei Tabellen mit verschiedenen Werten (Zentnerball 1,75
oder 1,25, Flügelball 1,25 oder 1,5, Pokéball 0,75 oder 1).

| Ball | Faktor | verstärkt | wann |
|---|---|---|---|
| Pokéball / Superball / Hyperball | 0,75 / 1,5 / 2,25 | | |
| Schwerball / Zentnerball / Tonnenball | 1 / 1,75 / 2,5 | 1,25 / 2 / 2,75 | Pokémon hat dich nicht bemerkt, oder im Kampf |
| Federball / Flügelball / Düsenball | 1 / 1,25 / 2 | 1,25 / 2 / 2,75 | Pokémon fliegt |

Offen: **Federball.** Die Tabelle im Artikel „Catch rate“ nennt 0,5 als Grundwert, der Artikel „Feather Ball“ nennt × 1
und × 1,25 nur „bei bestimmten fliegenden Begegnungen“. Der Pokédex nimmt wie bisher 1. Wer es im Spiel prüfen kann:
Ein Federball auf ein Pokémon am Boden entscheidet es.
