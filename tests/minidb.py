"""Mini-Datenbank für die Tests: eine erfundene Welt, gebaut vom echten Importer (app/importer.py).

Zwei Teile:

- das Gerüst (`minidb_geruest.json`, geschnitten mit `tools/minidb_geruest.py` aus den CSV-Dateien der PokéAPI): Bezeichner,
  an denen die Regeln des Programms hängen: Generationen, Spiele und Editionen, Regional-Dexe, Typen mit Typtabelle,
  Statuswerte, Lernwege, Ei-Gruppen, Wesen, Taschen der Items,
- die Welt unten: 14 erfundene Arten mit Formen, 25 erfundene Attacken, Items, Orte und Begegnungen. Nichts davon gibt
  es im Spiel; Zahlen und Namen sind ausgedacht und so gewählt, dass jede Regel wenigstens einen Fall hat (zwei Typen,
  frühere Typen, Mega- und Regionalform, rein optische Form, Baby, legendär, zwei Dexe in einem Spiel, Attacke mit
  geänderter Stärke, TM-Nummern je Spiel, Begegnung nur nachts, Abweichung zwischen PokéAPI und Showdown).

Wenige Bezeichner der Welt sind echt, weil Regeln im Programm an ihnen hängen: die Fähigkeiten `levitate` und
`adaptability` (app/typen.py, app/schaden.py) und die Namen der Bälle (Fangtabelle in app/abfragen/fangen.py).

Wer im Regional-Dex eines Spiels steht, hat dort eine Lernliste. Die Tests kennen die Welt aus diesem Modul und prüfen
gegen die Angaben hier, nicht gegen abgeschriebene Zahlen.

    from tests import minidb
    pfad = minidb.pfad()        # einmal je Testlauf gebaut, danach nur lesen oder kopieren
"""
import atexit
import csv
import io
import json
import os
import shutil
import tempfile
from unittest import mock

from app import importer

HIER = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HIER, "minidb_geruest.json"), encoding="utf-8") as _f:
    GERUEST = json.load(_f)

DE, EN = 6, 9
TYP = {r[2]: int(r[0]) for r in GERUEST["type_names"][1:] if r[1] == str(DE)}           # „Pflanze“ → 12
TYP_EN = {int(r[0]): r[1].capitalize() for r in GERUEST["types"][1:]}                   # 12 → „Grass“
SPIEL = {r[1]: int(r[0]) for r in GERUEST["version_groups"][1:]}                        # „emerald“ → 6
SPIEL_GEN = {int(r[0]): int(r[2]) for r in GERUEST["version_groups"][1:]}
EDITION = {r[2]: int(r[0]) for r in GERUEST["versions"][1:]}                            # „emerald“ → 9
EDITIONEN = {}                                                                          # Spiel → [Edition]
for _r in GERUEST["versions"][1:]:
    EDITIONEN.setdefault(int(_r[1]), []).append(int(_r[0]))
DEX = {r[2]: int(r[0]) for r in GERUEST["pokedexes"][1:]}                               # „hoenn“ → 4
DEX_SPIELE = {}                                                                         # Dex → [Spiel]
for _d, _vg in GERUEST["pokedex_version_groups"][1:]:
    DEX_SPIELE.setdefault(int(_d), []).append(int(_vg))

# ---- Arten ---------------------------------------------------------------------------------------------------------------
# Nummer, Kennung, Name, Gattung, Generation, Typen, Basiswerte (KP, Angriff, Verteidigung, Sp.-Angriff, Sp.-Verteidigung,
# Initiative), Fähigkeiten (die letzte mit „*“ ist versteckt), Ei-Gruppen, entwickelt sich aus, Kette, Fangrate, Merkmale
ARTEN = (
    (1, "keimling", "Keimling", "Spross", 1, ("Pflanze",), (45, 49, 49, 65, 65, 45), ("blattwerk", "*sonnenkind"), (1, 7), None, 1, 45, ""),
    (2, "rankel", "Rankel", "Ranke", 1, ("Pflanze",), (60, 62, 63, 80, 80, 60), ("blattwerk", "*sonnenkind"), (1, 7), 1, 1, 45, ""),
    (3, "dornwald", "Dornwald", "Dickicht", 1, ("Pflanze", "Gift"), (80, 82, 83, 100, 100, 80), ("blattwerk", "*sonnenkind"), (1, 7), 2, 1, 45, ""),
    (4, "glutli", "Glutli", "Funke", 1, ("Feuer",), (39, 52, 43, 60, 50, 65), ("glutherz",), (5,), None, 2, 45, ""),
    (5, "lohrax", "Lohrax", "Lohe", 1, ("Feuer", "Kampf"), (78, 104, 78, 84, 70, 100), ("glutherz", "*adaptability"), (5,), 4, 2, 45, ""),
    (6, "tropfi", "Tropfi", "Tropfen", 1, ("Wasser",), (44, 48, 65, 60, 64, 43), ("tauperle",), (2,), None, 3, 190, ""),
    (7, "flutor", "Flutor", "Brandung", 1, ("Wasser", "Eis"), (95, 85, 100, 85, 95, 60), ("tauperle",), (2,), 6, 3, 60, ""),
    (8, "zappel", "Zappel", "Funkenfell", 1, ("Elektro",), (35, 55, 40, 50, 50, 90), ("funkenfell",), (5, 6), 13, 4, 190, ""),
    (9, "donnrik", "Donnrik", "Gewitter", 1, ("Elektro", "Flug"), (60, 90, 55, 90, 80, 110), ("funkenfell",), (5, 6), 8, 4, 75, ""),
    (10, "steinchen", "Steinchen", "Kiesel", 2, ("Gestein", "Boden"), (50, 80, 100, 30, 30, 30), ("steinhaut",), (10,), None, 5, 255, ""),
    (11, "nebula", "Nebula", "Schleier", 6, ("Geist", "Fee"), (60, 50, 70, 110, 110, 85), ("levitate",), (11,), None, 6, 60, "geschlechtslos"),
    (12, "urdrache", "Urdrache", "Urzeit", 3, ("Drache", "Psycho"), (105, 150, 90, 150, 90, 95), ("steinhaut", "*adaptability"), (15,), None, 7, 3, "legendaer"),
    (13, "funkel", "Funkel", "Fünkchen", 2, ("Elektro",), (20, 40, 15, 35, 35, 60), ("funkenfell",), (15,), None, 4, 190, "baby"),
    (14, "hisuling", "Hisuling", "Nebelgeist", 8, ("Normal", "Geist"), (70, 75, 60, 75, 60, 80), ("blattwerk",), (5,), None, 8, 120, ""),
)
# Weitere Formen: Pokémon-Nummer, Kennung, Art, Formkennung, Formname, Name, eingeführt in, Typen, Basiswerte, Fähigkeiten,
# Kampfform, Mega. Die blaue Form von Zappel ist rein optisch (gleiche Werte): Sie fällt beim Aufbereiten weg.
FORMEN = (
    (10001, "dornwald-mega", 3, "mega", "Mega", "Mega-Dornwald", "x-y", ("Pflanze", "Unlicht"), (80, 112, 113, 120, 120, 80), ("adaptability",), 1, 1),
    (10002, "flutor-hisui", 7, "hisui", "Hisui-Form", "Hisui-Flutor", "legends-arceus", ("Wasser", "Geist"), (95, 95, 90, 95, 85, 60), ("tauperle",), 0, 0),
    (10003, "zappel-blau", 8, "blau", "Blaue Form", "Zappel (Blaue Form)", "x-y", ("Elektro",), (35, 55, 40, 50, 50, 90), ("funkenfell",), 0, 0),
)
# Steinchen war bis Generation 5 nur Gestein
TYPEN_FRUEHER = ((10, 5, ("Gestein",)),)
# Kennung, Name, Text; `levitate` und `adaptability` sind echte Kennungen (siehe oben)
FAEHIGKEITEN = (("blattwerk", "Blattwerk"), ("sonnenkind", "Sonnenkind"), ("glutherz", "Glutherz"), ("tauperle", "Tauperle"),
                ("funkenfell", "Funkenfell"), ("levitate", "Schwebe"), ("adaptability", "Anpassung"), ("steinhaut", "Steinhaut"))
# Entwicklungen: Art, Auslöser (1 Levelaufstieg, 3 Gegenstand), Level, Item, Freundschaft
ENTWICKLUNG = ((2, 1, 16, None, None), (3, 1, 32, None, None), (5, 1, 36, None, None), (7, 1, 30, None, None),
               (8, 1, None, None, 160), (9, 3, None, "donnerkiesel", None))

# ---- Spiele: Regional-Dex → Arten in der Reihenfolge des Dex --------------------------------------------------------------
# X/Y hat zwei Dexe (Zentral und Küste), Legenden: Arceus die Hisui-Form von Flutor und eine Art, die es nur dort gibt.
DEXE = {
    "kanto": (1, 2, 3, 4, 5, 6, 7, 8, 9),
    "original-johto": (1, 2, 3, 4, 5, 6, 7, 13, 8, 9, 10),
    "hoenn": (1, 2, 3, 4, 5, 6, 7, 13, 8, 9, 10, 12),
    "extended-sinnoh": (4, 5, 6, 7, 13, 8, 9, 10, 12),
    "original-unova": (4, 5, 6, 7, 10),
    "kalos-central": (1, 2, 3, 4, 5, 11),
    "kalos-coastal": (6, 7, 13, 8, 9),
    "galar": (1, 2, 3, 13, 8, 9, 11),
    "hisui": (1, 2, 3, 6, 7, 13, 8, 9, 14),
    "paldea": (1, 2, 3, 4, 5, 6, 7, 13, 8, 9, 11, 12),
    "kitakami": (10, 12),
}
# In diesen Spielen hat nur die genannte Form eine Lernliste (so erkennt der Importer die Form des Spiels)
NUR_FORM = {("legends-arceus", 7): 10002}

# ---- Attacken -------------------------------------------------------------------------------------------------------------
PHYS, SPEZ, STATUS = 2, 3, 1
GEGNER, SELBST, ALLE = 10, 7, 9          # Ziel: ein Pokémon, der Anwender, alle anderen
# Nummer, Kennung, Name, Generation, Typ, Klasse, Stärke, Genauigkeit, AP, Priorität, Ziel, Metadaten (PokéAPI move_meta:
# kat, leiden, leiden_chance, wert_chance, treffer, entzug, heilung, krit, schreck, werte), Merkmale bei Showdown
ATTACKEN = (
    (1, "rempler", "Rempler", 1, "Normal", PHYS, 40, 100, 35, 0, GEGNER, {}, ("contact",)),
    (2, "blattschlag", "Blattschlag", 1, "Pflanze", PHYS, 55, 95, 25, 0, GEGNER, {}, ("contact", "slicing")),
    (3, "giftranke", "Giftranke", 1, "Gift", PHYS, 60, 100, 20, 0, GEGNER, {"kat": 4, "leiden": 5, "leiden_chance": 30}, ("contact",)),
    (4, "glutstoss", "Glutstoß", 1, "Feuer", SPEZ, 50, 100, 25, 0, GEGNER, {"kat": 4, "leiden": 4, "leiden_chance": 10}, ()),
    (5, "flammenwand", "Flammenwand", 1, "Feuer", SPEZ, 90, 100, 15, 0, GEGNER, {}, ()),
    (6, "wasserstrahl", "Wasserstrahl", 1, "Wasser", SPEZ, 45, 100, 30, 0, GEGNER, {}, ()),
    (7, "flutwelle", "Flutwelle", 1, "Wasser", SPEZ, 90, 100, 15, 0, ALLE, {}, ()),
    (8, "frostbiss", "Frostbiss", 1, "Eis", PHYS, 65, 95, 15, 0, GEGNER, {"schreck": 10}, ("contact", "bite")),
    (9, "funkenschlag", "Funkenschlag", 1, "Elektro", PHYS, 60, 100, 20, 0, GEGNER, {}, ("contact", "punch")),
    (10, "donnerkeil", "Donnerkeil", 1, "Elektro", SPEZ, 95, 100, 15, 0, GEGNER, {"kat": 4, "leiden": 1, "leiden_chance": 10}, ()),
    (11, "boeenhieb", "Böenhieb", 1, "Flug", PHYS, 60, 100, 35, 0, GEGNER, {}, ("contact",)),
    (12, "geroellwurf", "Geröllwurf", 1, "Gestein", PHYS, 75, 90, 10, 0, GEGNER, {}, ()),
    (13, "erdstoss", "Erdstoß", 1, "Boden", PHYS, 100, 100, 10, 0, ALLE, {}, ()),
    (14, "schattenhauch", "Schattenhauch", 1, "Geist", SPEZ, 80, 100, 15, 0, GEGNER, {"kat": 6, "wert_chance": 20, "werte": ((5, -1),)}, ()),
    (15, "feenglanz", "Feenglanz", 6, "Fee", SPEZ, 80, 100, 10, 0, GEGNER, {}, ()),
    (16, "drachenschwinge", "Drachenschwinge", 1, "Drache", PHYS, 85, 100, 15, 0, GEGNER, {}, ("contact",)),
    (17, "geistesblitz", "Geistesblitz", 1, "Psycho", SPEZ, 90, 100, 10, 0, GEGNER, {}, ()),
    (18, "nachtklaue", "Nachtklaue", 2, "Unlicht", PHYS, 70, 100, 15, 0, GEGNER, {"krit": 1}, ("contact", "slicing")),
    (19, "schnellhieb", "Schnellhieb", 1, "Normal", PHYS, 40, 100, 30, 1, GEGNER, {}, ("contact",)),
    (20, "zwillingstritt", "Zwillingstritt", 1, "Kampf", PHYS, 30, 100, 30, 0, GEGNER, {"treffer": (2, 2)}, ("contact",)),
    (21, "kraftschub", "Kraftschub", 1, "Normal", STATUS, None, None, 20, 0, SELBST, {"kat": 2, "werte": ((2, 2),)}, ()),
    (22, "heilruf", "Heilruf", 1, "Normal", STATUS, None, None, 10, 0, SELBST, {"kat": 3, "heilung": 50}, ("sound",)),
    (23, "saugwurzel", "Saugwurzel", 1, "Pflanze", SPEZ, 75, 100, 10, 0, GEGNER, {"kat": 8, "entzug": 50}, ()),
    (24, "schlummerpollen", "Schlummerpollen", 1, "Pflanze", STATUS, None, 75, 15, 0, GEGNER, {"kat": 1, "leiden": 2}, ()),
    (25, "urknall", "Urknall", 1, "Normal", SPEZ, 150, 90, 5, 0, GEGNER, {}, ("recharge",)),
)
# Urknall hatte vor Schwarz/Weiß Stärke 120 (move_changelog: Stand bis zu diesem Spiel)
ATTACKE_FRUEHER = (("urknall", "black-white", 120),)
# Showdown weicht hier absichtlich ab, damit die Prüfliste (Tabelle pruefung) etwas zu zeigen hat
SD_ANDERS_ATTACKE = {"geroellwurf": {"basePower": 80}}
SD_ANDERS_ART = {"steinchen": {"spe": 35}}
# Frühere Basiswerte (Showdown-Mod der Generation 5): Tropfi hatte bis Generation 5 Sp.-Angriff 50
SD_MOD = {5: {"tropfi": {"spa": 50}}}

# Lernlisten: Pokémon → (Level-up als (Level, Attacke), TM, Ei, Attacken-Lehrer). Attacken, die jünger sind als das Spiel,
# fallen weg (Feenglanz erst ab Generation 6). In Legenden: Arceus gibt es weder TMs noch Ei-Attacken.
_GRAS = ((1, "rempler"), (5, "blattschlag"), (9, "schlummerpollen"), (13, "giftranke"), (20, "saugwurzel"))
_FEUER = ((1, "rempler"), (6, "glutstoss"), (12, "schnellhieb"), (18, "zwillingstritt"), (30, "flammenwand"))
_WASSER = ((1, "rempler"), (5, "wasserstrahl"), (11, "frostbiss"), (25, "flutwelle"))
LERNEN = {
    1: (_GRAS, ("erdstoss",), ("kraftschub",), ("heilruf",)),
    2: (_GRAS + ((25, "kraftschub"),), ("erdstoss",), (), ("heilruf",)),
    3: (_GRAS + ((25, "kraftschub"), (32, "nachtklaue"), (40, "urknall")), ("erdstoss", "geistesblitz"), (), ("heilruf",)),
    4: (_FEUER, ("flammenwand", "erdstoss"), ("nachtklaue",), ()),
    5: (_FEUER + ((36, "kraftschub"), (45, "urknall")), ("flammenwand", "erdstoss"), (), ()),
    6: (_WASSER, ("flutwelle",), ("heilruf",), ()),
    7: (_WASSER + ((38, "urknall"),), ("flutwelle", "geistesblitz"), (), ()),
    8: (((1, "rempler"), (4, "funkenschlag"), (10, "schnellhieb"), (22, "donnerkeil")), ("donnerkeil",), (), ()),
    9: (((1, "funkenschlag"), (1, "boeenhieb"), (30, "donnerkeil"), (44, "feenglanz")), ("donnerkeil", "geistesblitz"), (), ()),
    10: (((1, "rempler"), (8, "geroellwurf"), (20, "erdstoss"), (33, "kraftschub")), ("erdstoss",), (), ()),
    11: (((1, "schattenhauch"), (10, "feenglanz"), (20, "geistesblitz"), (30, "heilruf")), ("geistesblitz",), (), ()),
    12: (((1, "drachenschwinge"), (1, "geistesblitz"), (50, "urknall"), (70, "heilruf")),
         ("flammenwand", "flutwelle", "donnerkeil", "erdstoss", "geistesblitz"), (), ()),
    13: (((1, "rempler"), (4, "funkenschlag")), (), ("heilruf",), ()),
    14: (((1, "rempler"), (9, "schattenhauch"), (18, "schnellhieb")), (), (), ("heilruf",)),
    10002: (((1, "rempler"), (5, "wasserstrahl"), (15, "schattenhauch"), (29, "flutwelle")), (), (), ("heilruf",)),
}
# TMs: bis Generation 7 TM01 bis TM05 in dieser Reihenfolge, ab Generation 8 umgekehrt (TM-Nummern gelten je Spiel)
TM = ("flammenwand", "flutwelle", "donnerkeil", "erdstoss", "geistesblitz")
OHNE_TM = ("legends-arceus",)
# Erweiterungen haben wie bei der PokéAPI keine eigene Lernliste und keine eigenen TMs: Es gilt das Hauptspiel
ERWEITERUNG = {"the-teal-mask": "scarlet-violet"}

# ---- Items ----------------------------------------------------------------------------------------------------------------
# Nummer, Kennung, Name, Kategorie (item_categories), Preis, englischer Kurztext (daraus liest der Importer die Wirkung),
# ab Generation
ITEMS = (
    (1, "poke-ball", "Pokéball", 34, 200, "Tries to catch a wild Pokémon.", 1),
    (2, "great-ball", "Superball", 34, 600, "Tries to catch a wild Pokémon. Success rate is 1.5×.", 1),
    (3, "ultra-ball", "Hyperball", 34, 1200, "Tries to catch a wild Pokémon. Success rate is 2×.", 1),
    (4, "net-ball", "Netzball", 33, 1000, "Tries to catch a wild Pokémon. Success rate is 3× for water and bug Pokémon.", 3),
    (5, "dusk-ball", "Finsterball", 33, 1000, "Tries to catch a wild Pokémon. Success rate is 3.5× at night and in caves.", 4),
    (6, "kraeutersaft", "Kräutersaft", 27, 300, "Restores 20 HP.", 1),
    (7, "donnerkiesel", "Donnerkiesel", 10, 3000, "Evolves certain Pokémon.", 1),
    (8, "gluecksfeder", "Glücksfeder", 12, 4000, "Held: Does nothing in the tests.", 2),
    (9, "blattamulett", "Blattamulett", 19, 1000, "Held: Grass-type moves from the holder do 20% more damage.", 2),
) + tuple((10 + k, f"tm{k + 1:02d}", f"TM{k + 1:02d}", 37, 3000, "Teaches a move to a compatible Pokémon.", 1) for k in range(len(TM)))

# ---- Orte und Begegnungen -------------------------------------------------------------------------------------------------
# Ort: Nummer, Region (regions), Kennung, Name; Gebiet: Nummer, Ort, Kennung, Name (leer = der Ort selbst)
ORTE = ((1, 3, "nebelwiese", "Nebelwiese"), (2, 3, "kieselbucht", "Kieselbucht"), (3, 4, "frosthang", "Frosthang"),
        (4, 6, "lichterhain", "Lichterhain"))
GEBIETE = ((1, 1, "nebelwiese-area", ""), (2, 2, "kieselbucht-area", ""), (3, 3, "frosthang-area", ""),
           (4, 4, "lichterhain-area", ""), (5, 3, "frosthang-hoehle", "Höhle"))
# Begegnung: Edition, Gebiet, Art des Fundes (1 Gras, 5 Surfen), Häufigkeit in %, Pokémon, Level von bis, Bedingung
# (encounter_condition_value: 5 = in der Nacht). Glutli gibt es im Lichterhain nur in Y, Keimling nur in X.
BEGEGNUNGEN = (
    ("emerald", 1, 1, 20, 1, 3, 5, None), ("emerald", 1, 1, 10, 8, 4, 6, None), ("emerald", 2, 5, 60, 6, 10, 20, None),
    ("platinum", 3, 1, 20, 10, 12, 14, None), ("platinum", 5, 1, 10, 13, 8, 8, 5),
    ("x", 4, 1, 20, 11, 20, 22, None), ("y", 4, 1, 20, 11, 20, 22, None), ("x", 4, 1, 10, 1, 18, 20, None),
    ("y", 4, 1, 10, 4, 18, 20, None),
)
# Getragene Items wilder Pokémon: Edition, Pokémon, Item, Anteil in %. Nebula trägt die Glücksfeder in X und Y, Keimling das
# Blattamulett nur in X.
GETRAGEN = (("emerald", 6, "kraeutersaft", 50), ("x", 11, "gluecksfeder", 5), ("y", 11, "gluecksfeder", 5), ("x", 1, "blattamulett", 5))
# Bewährte Sets (Showdown, Random Battle) für Generation 9
SETS = {9: {"dornwald": {"level": 84, "sets": [{"role": "Bulky Attacker", "movepool": ["Saugwurzel", "Giftranke", "Erdstoss", "Kraftschub"],
                                                 "abilities": ["Blattwerk"], "teraTypes": ["Grass"]}]}}}      # englische Namen

ART = {a[0]: a for a in ARTEN}
ART_NR = {a[1]: a[0] for a in ARTEN}
ATTACKE = {a[1]: a for a in ATTACKEN}
ITEM = {i[1]: i for i in ITEMS}
FAEHIGKEIT = {k: n + 1 for n, (k, _) in enumerate(FAEHIGKEITEN)}


def englisch(kennung):
    """Der englische Name eines Eintrags der Welt: aus der Kennung („poke-ball“ → „Poke Ball“). So heißt er auch bei Showdown."""
    return kennung.replace("-", " ").title()


def dex_spiele(dex):
    """Die Spiele (Nummern) eines Regional-Dex."""
    return DEX_SPIELE[DEX[dex]]


def spiele_von(art):
    """{Spiel: (Dex, Nummer im Dex)}: der erste Dex des Spiels, in dem die Art steht."""
    out = {}
    for dex in sorted(DEXE, key=lambda d: DEX[d]):
        if art in DEXE[dex]:
            for vg in dex_spiele(dex):
                out.setdefault(vg, (dex, DEXE[dex].index(art) + 1))
    return out


def lernt(pokemon, spiel):
    """Was ein Pokémon in einem Spiel lernt: [(Attacke, Lernweg 1 Level, 2 Ei, 3 Lehrer, 4 TM, Level)]. Leer, wenn die Art
    nicht im Dex des Spiels steht, dort eine andere Form gilt oder das Spiel eine Erweiterung ist."""
    vg = SPIEL[spiel]
    if spiel in ERWEITERUNG:
        return []
    art = pokemon if pokemon in ART else next(f[2] for f in FORMEN if f[0] == pokemon)
    if pokemon not in LERNEN or vg not in spiele_von(art) or NUR_FORM.get((spiel, art), pokemon) != pokemon:
        return []
    if pokemon not in ART and (spiel, art) not in NUR_FORM:
        return []
    up, tm, ei, lehrer = LERNEN[pokemon]
    if spiel in OHNE_TM:
        tm, ei = (), ()
    rows = [(m, 1, lv) for lv, m in up] + [(m, 4, 0) for m in tm] + [(m, 2, 0) for m in ei] + [(m, 3, 0) for m in lehrer]
    return [r for r in rows if ATTACKE[r[0]][3] <= SPIEL_GEN[vg]]


def tm_nummer(attacke, spiel):
    """Nummer der TM im Spiel: bis Generation 7 in der Reihenfolge von TM, danach umgekehrt."""
    k = TM.index(attacke)
    return k + 1 if SPIEL_GEN[SPIEL[spiel]] <= 7 else len(TM) - k


def _spiele_mit_daten():
    return sorted({vg for dex in DEXE for vg in dex_spiele(dex)})


def _csv(head, rows):
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(head)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return out.getvalue()


def _welt():
    """Die Tabellen der Welt als {Name: (Kopf, Zeilen)}."""
    t = {}
    vgs = _spiele_mit_daten()
    kennung = {v: k for k, v in SPIEL.items()}
    pokemon = [(a[0], a[1], a[0], a[5], a[6], a[7], 1) for a in ARTEN] + [(f[0], f[1], f[2], f[7], f[8], f[9], 0) for f in FORMEN]
    erstes_spiel = {g: min(v for v, gg in SPIEL_GEN.items() if gg == g) for g in set(SPIEL_GEN.values())}
    t["pokemon_species"] = (
        "id,identifier,generation_id,evolves_from_species_id,evolution_chain_id,color_id,shape_id,habitat_id,gender_rate,"
        "capture_rate,base_happiness,is_baby,hatch_counter,has_gender_differences,growth_rate_id,forms_switchable,is_legendary,"
        "is_mythical,order,conquest_order".split(","),
        [(a[0], a[1], a[4], a[9], a[10], 1, 1, None, -1 if "geschlechtslos" in a[12] or "legendaer" in a[12] else 4, a[11], 70,
          int("baby" in a[12]), 20, 0, 2 + a[0] % 3, int(any(f[2] == a[0] for f in FORMEN)), int("legendaer" in a[12]), 0,
          a[0], None) for a in ARTEN])
    t["pokemon_species_names"] = ("pokemon_species_id,local_language_id,name,genus".split(","),
                                  [(a[0], DE, a[2], a[3] + "-Pokémon") for a in ARTEN]
                                  + [(a[0], EN, englisch(a[1]), a[3] + " Pokémon") for a in ARTEN])
    t["pokemon_species_flavor_text"] = (
        "species_id,version_id,language_id,flavor_text".split(","),
        [(a[0], ed, DE, f"{a[2]} ist erfunden. Eintrag {n + 1} für die Tests.")
         for a in ARTEN for n, ed in enumerate(e for vg in sorted(spiele_von(a[0])) for e in EDITIONEN[vg][:1])])
    t["pokemon"] = ("id,identifier,species_id,height,weight,base_experience,order,is_default".split(","),
                    [(p[0], p[1], p[2], 5 + p[2], 60 + 55 * p[2], 60 + p[2], n + 1, p[6]) for n, p in enumerate(pokemon)])
    t["pokemon_types"] = ("pokemon_id,type_id,slot".split(","),
                          [(p[0], TYP[ty], n + 1) for p in pokemon for n, ty in enumerate(p[3])])
    t["pokemon_types_past"] = ("pokemon_id,generation_id,type_id,slot".split(","),
                               [(pid, gen, TYP[ty], n + 1) for pid, gen, typen in TYPEN_FRUEHER for n, ty in enumerate(typen)])
    t["pokemon_stats"] = ("pokemon_id,stat_id,base_stat,effort".split(","),
                          [(p[0], n + 1, v, int(v == max(p[4]))) for p in pokemon for n, v in enumerate(p[4])])
    t["pokemon_abilities"] = ("pokemon_id,ability_id,is_hidden,slot".split(","),
                              [(p[0], FAEHIGKEIT[ab.lstrip("*")], int(ab.startswith("*")), 3 if ab.startswith("*") else n + 1)
                               for p in pokemon for n, ab in enumerate(p[5])])
    t["pokemon_egg_groups"] = ("species_id,egg_group_id".split(","), [(a[0], g) for a in ARTEN for g in a[8]])
    t["pokemon_forms"] = (
        "id,identifier,form_identifier,pokemon_id,introduced_in_version_group_id,is_default,is_battle_only,is_mega,form_order,order".split(","),
        [(a[0], a[1], None, a[0], erstes_spiel[a[4]], 1, 0, 0, 1, a[0]) for a in ARTEN]
        + [(f[0], f[1], f[3], f[0], SPIEL[f[6]], 1, f[10], f[11], 2, f[0]) for f in FORMEN])
    t["pokemon_form_names"] = ("pokemon_form_id,local_language_id,form_name,pokemon_name".split(","),
                               [(f[0], DE, f[4], f[5]) for f in FORMEN])
    t["pokemon_dex_numbers"] = ("species_id,pokedex_id,pokedex_number".split(","),
                                [(a[0], DEX["national"], a[0]) for a in ARTEN]
                                + [(art, DEX[dex], n + 1) for dex, arten in DEXE.items() for n, art in enumerate(arten)])
    t["evolution_chains"] = ("id,baby_trigger_item_id".split(","), [(k, None) for k in sorted({a[10] for a in ARTEN})])
    kopf = ("id,evolved_species_id,evolution_trigger_id,version_group_id,is_default,trigger_item_id,minimum_level,gender_id,"
            "location_id,held_item_id,time_of_day,known_move_id,known_move_type_id,minimum_happiness,minimum_beauty,"
            "minimum_affection,relative_physical_stats,party_species_id,party_type_id,trade_species_id,needs_overworld_rain,"
            "turn_upside_down,needs_multiplayer,near_special_rock,region_id,required_pokemon_form_id,evolved_pokemon_form_id,"
            "used_move_id,minimum_move_count,minimum_steps,minimum_damage_taken,nature_bitmask,condition_expression,"
            "percentage_chance").split(",")
    zeilen = []
    for n, (art, wie, level, item, freund) in enumerate(ENTWICKLUNG):
        z = dict.fromkeys(kopf)
        z.update(id=n + 1, evolved_species_id=art, evolution_trigger_id=wie, is_default=1, minimum_level=level,
                 trigger_item_id=ITEM[item][0] if item else None, minimum_happiness=freund, needs_overworld_rain=0,
                 turn_upside_down=0, needs_multiplayer=0)
        zeilen.append([z[k] for k in kopf])
    t["pokemon_evolution"] = (kopf, zeilen)
    t["abilities"] = ("id,identifier,generation_id,is_main_series".split(","), [(FAEHIGKEIT[k], k, 3, 1) for k, _ in FAEHIGKEITEN])
    t["ability_names"] = ("ability_id,local_language_id,name".split(","), [(FAEHIGKEIT[k], DE, n) for k, n in FAEHIGKEITEN]
                          + [(FAEHIGKEIT[k], EN, englisch(k)) for k, _ in FAEHIGKEITEN])
    t["ability_flavor_text"] = ("ability_id,version_group_id,language_id,flavor_text".split(","),
                                [(FAEHIGKEIT[k], SPIEL["scarlet-violet"], DE, f"{n}: erfundene Fähigkeit für die Tests.")
                                 for k, n in FAEHIGKEITEN])
    # Attacken
    t["moves"] = ("id,identifier,generation_id,type_id,power,pp,accuracy,priority,target_id,damage_class_id,effect_id,effect_chance,"
                  "contest_type_id,contest_effect_id,super_contest_effect_id".split(","),
                  [(m[0], m[1], m[3], TYP[m[4]], m[6], m[8], m[7], m[9], m[10], m[5], 1,
                    m[11].get("leiden_chance") or m[11].get("wert_chance"), None, None, None) for m in ATTACKEN])
    t["move_names"] = ("move_id,local_language_id,name".split(","), [(m[0], DE, m[2]) for m in ATTACKEN] + [(m[0], EN, englisch(m[1])) for m in ATTACKEN])
    t["move_flavor_text"] = ("move_id,version_group_id,language_id,flavor_text".split(","),
                             [(m[0], vg, DE, f"{m[2]}: erfundene Attacke für die Tests.") for m in ATTACKEN
                              for vg in (SPIEL["red-blue"], SPIEL["scarlet-violet"]) if m[3] <= SPIEL_GEN[vg]])
    t["move_meta"] = (
        "move_id,meta_category_id,meta_ailment_id,min_hits,max_hits,min_turns,max_turns,drain,healing,crit_rate,ailment_chance,"
        "flinch_chance,stat_chance".split(","),
        [(m[0], x.get("kat", 0), x.get("leiden", 0), *(x.get("treffer") or (None, None)), None, None, x.get("entzug", 0),
          x.get("heilung", 0), x.get("krit", 0), x.get("leiden_chance", 0), x.get("schreck", 0), x.get("wert_chance", 0))
         for m in ATTACKEN for x in (m[11],)])
    t["move_meta_stat_changes"] = ("move_id,stat_id,change".split(","),
                                   [(m[0], s, c) for m in ATTACKEN for s, c in m[11].get("werte", ())])
    t["move_changelog"] = ("move_id,changed_in_version_group_id,type_id,power,pp,accuracy,priority,target_id,effect_id,effect_chance".split(","),
                           [(ATTACKE[k][0], SPIEL[vg], None, staerke, None, None, None, None, None, None) for k, vg, staerke in ATTACKE_FRUEHER])
    lern, maschinen = [], []
    for vg in vgs:
        for pid in LERNEN:
            order = 0
            for move, weg, level in lernt(pid, kennung[vg]):
                order += weg == 1
                lern.append((pid, vg, ATTACKE[move][0], weg, level, order if weg == 1 else None,
                             level + 10 if weg == 1 and kennung[vg] == "legends-arceus" else None))
        if kennung[vg] not in OHNE_TM and kennung[vg] not in ERWEITERUNG:
            maschinen += [(tm_nummer(m, kennung[vg]), vg, ITEM[f"tm{tm_nummer(m, kennung[vg]):02d}"][0], ATTACKE[m][0]) for m in TM]
    t["pokemon_moves"] = ("pokemon_id,version_group_id,move_id,pokemon_move_method_id,level,order,mastery".split(","), lern)
    t["machines"] = ("machine_number,version_group_id,item_id,move_id".split(","), maschinen)
    # Items: Beschreibung in jedem Spiel mit Daten ab der Generation des Items; in Legenden: Arceus nur die drei Grundbälle
    def hat(item, vg):
        if kennung[vg] == "legends-arceus":
            return item[0] <= 3
        return item[6] <= SPIEL_GEN[vg]
    t["items"] = ("id,identifier,category_id,cost,fling_power,fling_effect_id".split(","),
                  [(i[0], i[1], i[3], i[4], None, None) for i in ITEMS])
    t["item_names"] = ("item_id,local_language_id,name".split(","), [(i[0], DE, i[2]) for i in ITEMS] + [(i[0], EN, englisch(i[1])) for i in ITEMS])
    t["item_prose"] = ("item_id,local_language_id,short_effect,effect".split(","), [(i[0], EN, i[5], i[5]) for i in ITEMS])
    t["item_flavor_text"] = ("item_id,version_group_id,language_id,flavor_text".split(","),
                             [(i[0], vg, DE, f"{i[2]}: erfundenes Item für die Tests.") for i in ITEMS for vg in vgs if hat(i, vg)])
    t["item_game_indices"] = ("item_id,generation_id,game_index".split(","),
                              [(i[0], g, i[0]) for i in ITEMS for g in range(i[6], 10)])
    # Orte und Begegnungen
    t["locations"] = ("id,region_id,identifier".split(","), [(o[0], o[1], o[2]) for o in ORTE])
    t["location_names"] = ("location_id,local_language_id,name,subtitle".split(","), [(o[0], DE, o[3], None) for o in ORTE])
    t["location_areas"] = ("id,location_id,game_index,identifier".split(","), [(g[0], g[1], g[0], g[2]) for g in GEBIETE])
    t["location_area_prose"] = ("location_area_id,local_language_id,name".split(","), [(g[0], DE, g[3]) for g in GEBIETE if g[3]])
    # wie bei der PokéAPI: ein Platz (Slot) gilt je Spiel, beide Editionen verweisen auf denselben; eine Begegnung je Edition
    slots, funde, bedingungen, platz = {}, [], [], {}
    for n, (ed, gebiet, wie, prozent, pid, von, bis, bed) in enumerate(BEGEGNUNGEN):
        vg = next(v for v, eds in EDITIONEN.items() if EDITION[ed] in eds)
        k = platz[ed, gebiet, wie] = platz.get((ed, gebiet, wie), 0) + 1
        slot = slots.setdefault((vg, gebiet, wie, k), (len(slots) + 1, vg, wie, k, prozent))
        funde.append((n + 1, EDITION[ed], gebiet, slot[0], pid, von, bis))
        if bed:
            bedingungen.append((n + 1, bed))
    slots = list(slots.values())
    t["encounter_slots"] = ("id,version_group_id,encounter_method_id,slot,rarity".split(","), slots)
    t["pokemon_items"] = ("pokemon_id,version_id,item_id,rarity".split(","), [(p, EDITION[ed], ITEM[item][0], anteil) for ed, p, item, anteil in GETRAGEN])
    t["encounters"] = ("id,version_id,location_area_id,encounter_slot_id,pokemon_id,min_level,max_level".split(","), funde)
    t["encounter_condition_value_map"] = ("encounter_id,encounter_condition_value_id".split(","), bedingungen)
    return t


def csvs():
    """{Tabelle: CSV-Text}: Gerüst und Welt, so wie der Abgleich die Dateien der PokéAPI an den Importer gibt."""
    out = {name: _csv(rows[0], rows[1:]) for name, rows in GERUEST.items()}
    out.update({name: _csv(head, rows) for name, (head, rows) in _welt().items()})
    return out


def _ts(eintraege):
    zeilen = ["export const Daten: {[k: string]: object} = {"]
    for key, felder in eintraege:
        zeilen.append(f"\t{key}: {{")
        zeilen += [f"\t\t{k}: {v}," for k, v in felder]
        zeilen.append("\t},")
    return "\n".join(zeilen + ["};", ""])


def _obj(d):
    return "{ " + ", ".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in d.items()) + " }"


def sd_texts():
    """Dateien von Pokémon Showdown für dieselbe Welt: pokedex.ts, moves.ts und der Mod der Generation 5."""
    dex = []
    for pid, ident, typen, werte, faeh in ([(a[0], a[1], a[5], a[6], a[7]) for a in ARTEN]
                                           + [(f[2], f[1], f[7], f[8], f[9]) for f in FORMEN]):
        bs = dict(zip(importer.SD_STATS, werte))
        bs.update(SD_ANDERS_ART.get(ident, {}))
        ab = {("H" if a.startswith("*") else str(n)): englisch(a.lstrip("*")) for n, a in enumerate(faeh)}
        dex.append((importer.showdown.sd_id(ident), (("num", pid), ("name", json.dumps(ident.title())),
                                                     ("types", json.dumps([TYP_EN[TYP[x]] for x in typen])),
                                                     ("baseStats", _obj(bs)), ("abilities", _obj(ab)))))
    moves = []
    for m in ATTACKEN:
        f = {"basePower": m[6] or 0, **SD_ANDERS_ATTACKE.get(m[1], {})}
        felder = [("num", m[0]), ("accuracy", "true" if m[7] is None else m[7]), ("basePower", f["basePower"]),
                  ("category", json.dumps({PHYS: "Physical", SPEZ: "Special", STATUS: "Status"}[m[5]])),
                  ("name", json.dumps(englisch(m[1]))), ("pp", m[8]), ("priority", m[9]),
                  ("flags", _obj({k: 1 for k in m[12]} | {"protect": 1}))]
        if m[11].get("treffer"):
            felder.append(("multihit", m[11]["treffer"][0]))
        felder.append(("type", json.dumps(TYP_EN[TYP[m[4]]])))
        moves.append((importer.showdown.sd_id(m[1]), felder))
    out = {"pokedex": _ts(dex), "moves": _ts(moves)}
    for gen, arten in SD_MOD.items():
        out[f"gen{gen}"] = _ts([(k, (("inherit", "true"), ("baseStats", _obj({**dict(zip(importer.SD_STATS, ART[ART_NR[k]][6])), **v}))))
                                for k, v in arten.items()])
    return out


def bauen(path):
    """Die Mini-Datenbank unter path bauen: der echte Importer mit Selbstprüfung, nur die Mindestmengen sind die der Welt.
    Gibt die Zahlen des Importers zurück."""
    extra = importer.load_extra(os.path.join(HIER, "..", "extra"))
    with mock.patch.multiple(importer, MIN_SPECIES=len(ARTEN), MIN_MOVES=len(ATTACKEN)):
        return importer.build(path, csvs(), sd_texts(), extra, sets=SETS)


_fertig = {}


def pfad():
    """Pfad der gebauten Mini-Datenbank (einmal je Testlauf, in einem eigenen Ordner; nur lesen oder kopieren)."""
    if "pfad" not in _fertig:
        d = tempfile.mkdtemp(prefix="pokedex-minidb-")
        atexit.register(shutil.rmtree, d, True)
        _fertig["zahlen"] = bauen(os.path.join(d, "pokeapi.db"))
        _fertig["pfad"] = os.path.join(d, "pokeapi.db")
    return _fertig["pfad"]


def zahlen():
    """Die Zahlen, die der Importer beim Bauen gemeldet hat."""
    pfad()
    return _fertig["zahlen"]
