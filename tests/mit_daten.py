"""Tests mit Spieldaten (seit 0.59.0): die Mini-Datenbank aus tests/minidb.py, gebaut vom echten Importer. Sie laufen
überall, auch in der CI; `tests/test_all.py` lädt die Klassen mit (ein Aufruf: python3 -m unittest tests.test_all).

Erwartet wird, was in tests/minidb.py steht: Die Tests rechnen die Antworten des Programms gegen die Angaben der Welt
nach, statt Zahlen abzuschreiben. Was die Mini-Datenbank nicht enthält (Spieldaten aus PKHeX, PokéWiki, Karten), prüfen
die Leser-Tests mit erfundenen Ausschnitten und lokal die Klasse `MitDatenbank` mit einer echten Datenbank.
"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
import urllib.parse
from unittest import mock

from app import abfragen, db, fehler, importer, server, sources, spiele
from tests import minidb, vertrag
from tests.basis import HttpMitDaten, MitMiniDatenbank, app_quellen, im_paket, oberflaeche_js

SPIELE = ("red-blue", "gold-silver", "emerald", "platinum", "black-white", "x-y", "sword-shield", "legends-arceus",
          "scarlet-violet", "the-teal-mask")
OHNE_DATEN = ("sun-moon", "legends-za", "pokopia")          # im Gerüst, aber ohne Arten: Die Abfragen antworten leer
TYP = minidb.TYP


def lernspiel_von(spiel):
    """Spiel, dessen Lernliste gilt: bei Erweiterungen ohne eigene Liste das Hauptspiel (Spielprofil)."""
    pr = spiele.profil(spiel)
    return pr["hauptspiel"] if pr["lernliste"] == "hauptspiel" else spiel


def erwartete_liste(spiel):
    """[(Pokémon, Nummer, Dex 0/1 …)] eines Spiels in der Reihenfolge der Liste: Dex für Dex, darin nach Nummer."""
    vg = minidb.SPIEL[spiel]
    dexe = sorted((d for d in minidb.DEXE if vg in minidb.dex_spiele(d)), key=lambda d: minidb.DEX[d])
    out, seen = [], set()
    for k, dex in enumerate(dexe):
        for n, art in enumerate(minidb.DEXE[dex]):
            if art not in seen:
                seen.add(art)
                out.append((minidb.NUR_FORM.get((spiel, art), art), n + 1, k))
    return out


class MiniBau(unittest.TestCase):
    """Der Importer baut die erfundene Welt: dieselben Schritte und dieselbe Selbstprüfung wie beim Abgleich."""

    def test_importer_baut_die_welt(self):
        z = minidb.zahlen()
        self.assertEqual(z["check"], [])
        self.assertEqual((z["species"], z["moves"], z["items"]), (len(minidb.ARTEN), len(minidb.ATTACKEN), len(minidb.ITEMS)))
        self.assertEqual(z["forms"], len(minidb.ARTEN) + 2)                 # Mega- und Hisui-Form; die blaue ist nur Optik
        self.assertEqual(z["games"], len(minidb.SPIEL) + len(importer.EIGENE_SPIELE))
        self.assertEqual((z["sd_pokemon"], z["sd_moves"]), (len(minidb.ARTEN) + len(minidb.FORMEN), len(minidb.ATTACKEN)))
        self.assertEqual(z["tables"], len(minidb.csvs()))
        self.assertEqual(z["diff"], len(minidb.SD_ANDERS_ART) + len(minidb.SD_ANDERS_ATTACKE))
        self.assertEqual(z["sets"], 1)

    def test_selbstpruefung_greift(self):
        """Mit den echten Mindestmengen gilt die Mini-Datenbank nicht; ohne Pflichtdatei wird gar nicht gebaut."""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "pokeapi.db")
            with self.assertRaises(ValueError) as e:
                importer.build(p, minidb.csvs(), minidb.sd_texts())
            self.assertIn("Selbstprüfung", str(e.exception))
            self.assertIn(f"nur {len(minidb.ARTEN)} Arten", str(e.exception))
            csvs = minidb.csvs()
            del csvs["moves"]
            with self.assertRaises(ValueError) as e:
                importer.build(p, csvs)
            self.assertIn("moves", str(e.exception))
            # 17 statt 18 Typen: Die Selbstprüfung meldet es, auch wenn die Mengen stimmen
            csvs = minidb.csvs()
            csvs["types"] = "\n".join(z for z in csvs["types"].split("\n") if not z.startswith("18,")) + "\n"
            with mock.patch.multiple(importer, MIN_SPECIES=1, MIN_MOVES=1), self.assertRaises(ValueError) as e:
                importer.build(p, csvs)
            self.assertIn("17 statt 18 Typen", str(e.exception))

    def test_aufbereitete_tabellen(self):
        con = sqlite3.connect(minidb.pfad())
        try:
            form = {r[0]: r[1:] for r in con.execute("SELECT id, name, typ1, typ2, summe, gen, relevant, standard, mega, kampfform FROM form")}
            for a in minidb.ARTEN:
                t = [TYP[x] for x in a[5]] + [None]
                self.assertEqual(form[a[0]], (a[2], t[0], t[1], sum(a[6]), a[4], 1, 1, 0, 0), a[1])
            mega, hisui, blau = form[10001], form[10002], form[10003]
            self.assertEqual((mega[0], mega[4], mega[5], mega[7], mega[8]), ("Mega-Dornwald", 6, 1, 1, 1))
            self.assertEqual((hisui[0], hisui[4], hisui[5], hisui[6]), ("Hisui-Flutor", 8, 1, 0))
            self.assertEqual(blau[5], 0)                    # gleiche Werte wie Zappel: nicht relevant
            # Spiel und Form: Nummer im ersten Dex des Spiels, in dem die Art steht; zweiter Dex mit Kürzel
            for spiel in SPIELE:
                got = [tuple(r) for r in con.execute(
                    "SELECT sf.form, sf.nr, sf.dex FROM spiel_form sf JOIN spiel s ON s.id = sf.spiel WHERE s.kennung = ? "
                    "ORDER BY sf.dex, sf.nr", (spiel,))]
                self.assertEqual(got, erwartete_liste(spiel), spiel)
            self.assertEqual(con.execute("SELECT DISTINCT dexk FROM spiel_form sf JOIN spiel s ON s.id = sf.spiel "
                                         "WHERE s.kennung = 'x-y' AND sf.dex = 1").fetchall(), [("K",)])
            # Kurz-Info und Merkmale der Attacken
            att = {r[0]: r[1:] for r in con.execute("SELECT kennung, kurz, merkmale, mehrfach FROM attacke")}
            self.assertEqual(att["giftranke"][0], "vergiftet (30 %)")
            self.assertEqual(att["schattenhauch"][0], "Sp.-Verteidigung −1 (Gegner, 20 %)")
            self.assertEqual(att["kraftschub"][0], "Angriff +2 (selbst)")
            self.assertEqual(att["saugwurzel"][0], "saugt 50 % des Schadens als KP ab")
            self.assertEqual(json.loads(att["frostbiss"][1]), ["bite", "contact"])
            self.assertEqual(att["zwillingstritt"][2], "2")
            # Abweichungen zu Showdown und frühere Basiswerte
            self.assertEqual(sorted(con.execute("SELECT art, name, feld, pokeapi, showdown FROM pruefung")),
                             [("attacke", "Geröllwurf", "Stärke", "75", "80"), ("form", "Steinchen", "Initiative", "30", "35")])
            self.assertEqual(con.execute("SELECT form, gen, spang FROM werte_alt ORDER BY gen").fetchall(),
                             [(6, g, 50) for g in range(1, 6)])
            # Items: Tasche, Wirkung aus dem englischen Kurztext, Spiele mit Beschreibung
            item = {r[0]: r[1:] for r in con.execute("SELECT kennung, name, tasche, wirkung, wert, spiele, en FROM item")}
            self.assertEqual(item["net-ball"][:4], ("Netzball", "Bälle", "Fangfaktor ×3", 3.0))
            self.assertEqual(item["kraeutersaft"][:4], ("Kräutersaft", "Medizin", "KP +20", 20.0))
            self.assertEqual(item["tm03"][1], "Maschinen")
            self.assertEqual(item["blattamulett"][5], "Blattamulett")
            self.assertNotIn(minidb.SPIEL["red-blue"], json.loads(item["dusk-ball"][4]))
            self.assertEqual([i for i in item if minidb.SPIEL["legends-arceus"] in json.loads(item[i][4])],
                             ["poke-ball", "great-ball", "ultra-ball"])
        finally:
            con.close()

    def test_geruest(self):
        """Das Gerüst enthält nur die Tabellen des Werkzeugs, nur Deutsch und Englisch, und die Welt überschreibt keine davon."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("minidb_geruest", os.path.join(minidb.HIER, "..", "tools", "minidb_geruest.py"))
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        self.assertEqual(sorted(minidb.GERUEST), sorted(set(tool.GANZ) | set(tool.BIS) | set(tool.NAMEN) | {"growth_rates"}))
        for name, rows in minidb.GERUEST.items():
            if "local_language_id" in rows[0]:
                i = rows[0].index("local_language_id")
                self.assertLessEqual({r[i] for r in rows[1:]}, set(tool.SPRACHEN), name)
        self.assertEqual(set(minidb.GERUEST) & set(minidb._welt()), set())
        self.assertLessEqual(set(importer.REQUIRED), set(minidb.csvs()))
        self.assertTrue(os.path.isfile(os.path.join(minidb.HIER, "minidb_LIZENZ.txt")))


class Welt(MitMiniDatenbank):
    """Die Abfragen der Oberfläche gegen die Mini-Datenbank."""

    def test_liste_je_spiel(self):
        for spiel in SPIELE:
            r = abfragen.search({"spiel": spiel, "limit": 500})
            self.assertEqual([(x["id"], x["nr"], x["dex"]) for x in r["rows"]], erwartete_liste(spiel), spiel)
            self.assertEqual((r["n"], r["spiel"]), (len(erwartete_liste(spiel)), spiel))
        for spiel in OHNE_DATEN:
            self.assertEqual(abfragen.search({"spiel": spiel})["rows"], [], spiel)
        # zwei Dexe in einem Spiel: der zweite mit Kürzel vor der Nummer
        xy = {x["name"]: (x["nr"], x["dexk"]) for x in abfragen.search({"spiel": "x-y"})["rows"]}
        self.assertEqual((xy["Nebula"], xy["Tropfi"]), ((6, ""), (1, "K")))
        # Legenden: Arceus zeigt die Hisui-Form statt der Standardform, mit deren Typen
        la = {x["art"]: x for x in abfragen.search({"spiel": "legends-arceus"})["rows"]}
        self.assertEqual((la[7]["id"], la[7]["name"], la[7]["typen"]), (10002, "Hisui-Flutor", [TYP["Wasser"], TYP["Geist"]]))
        self.assertEqual(la[14]["name"], "Hisuling")
        self.ohne_fehler()

    def test_filter(self):
        sv = lambda **p: [x["name"] for x in abfragen.search({"spiel": "scarlet-violet", **p})["rows"]]
        self.assertEqual(sv(typen=f"{TYP['Pflanze']},{TYP['Gift']}", modus="und"), ["Dornwald"])
        self.assertEqual(sv(typen=f"{TYP['Pflanze']},{TYP['Feuer']}", modus="oder"), ["Keimling", "Rankel", "Dornwald", "Glutli", "Lohrax"])
        self.assertEqual(sv(typen=f"{TYP['Pflanze']},{TYP['Feuer']}", modus="oder", ohne=str(TYP["Gift"])),
                         ["Keimling", "Rankel", "Glutli", "Lohrax"])
        self.assertEqual(sv(q="Urdr"), ["Urdrache"])
        self.assertEqual(sv(gen=6, genmodus="nur"), ["Nebula"])
        stark = abfragen.search({"spiel": "scarlet-violet", "gegen": str(TYP["Wasser"])})["rows"]
        tafel = abfragen.data().chart(9)
        self.assertTrue(stark and all(abfragen.strong_against(x["typen"], TYP["Wasser"], tafel) for x in stark))
        self.assertNotIn("Glutli", [x["name"] for x in stark])
        self.assertEqual([x["name"] for x in abfragen.search({"spiel": "legends-arceus", "q": "Flutor"})["rows"]], ["Hisui-Flutor"])
        self.ohne_fehler()

    def test_detail_je_generation(self):
        # Steinchen war bis Generation 5 nur Gestein; Fee gibt es erst ab Generation 6
        alt, neu = abfragen.detail(10, {"spiel": "emerald"}), abfragen.detail(10, {"spiel": "the-teal-mask"})
        self.assertEqual((alt["typen"], neu["typen"]), ([TYP["Gestein"]], [TYP["Gestein"], TYP["Boden"]]))
        self.assertEqual((len(alt["wirkung"]), len(neu["wirkung"])), (17, 18))
        self.assertEqual((alt["wirkung"][str(TYP["Wasser"])], neu["wirkung"][str(TYP["Wasser"])]), (2.0, 4.0))
        self.assertEqual(neu["wirkung"][str(TYP["Elektro"])], 0.0)
        # Tropfi hatte bis Generation 5 Sp.-Angriff 50
        t3, t9 = abfragen.detail(6, {"spiel": "emerald"}), abfragen.detail(6, {"spiel": "scarlet-violet"})
        self.assertEqual((t3["werte"][3], t3["werte_alt"], t3["summe"]), (50, True, sum(minidb.ART[6][6]) - 10))
        self.assertEqual((t9["werte"], t9["werte_alt"]), (list(minidb.ART[6][6]), False))
        # Schwebe: Boden trifft nicht, die Detailseite nennt die Fähigkeit
        n = abfragen.detail(11, {"spiel": "x-y"})
        self.assertEqual((n["wirkung"][str(TYP["Boden"])], n["faehigkeit_wirkt"]), (0.0, "levitate"))
        self.assertEqual([(f["name"], f["versteckt"], f["wirkt"]) for f in n["faehigkeiten"]], [("Schwebe", False, True)])
        # Entwicklungen mit Bedingung, Formen, Kategorie und Text
        d = abfragen.detail(9, {"spiel": "x-y"})
        self.assertEqual({e["name"]: (e["von"], e["bedingungen"]) for e in d["entwicklung"]},
                         {"Funkel": (None, []), "Zappel": (13, ["Freundschaft ab 160"]), "Donnrik": (8, ["mit Donnerkiesel"])})
        self.assertEqual(d["kategorie"], "Gewitter-Pokémon")
        self.assertIn("Donnrik ist erfunden", d["text"])
        self.assertEqual(abfragen.detail(3, {"spiel": "x-y"})["formen"], [{"id": 10001, "name": "Mega-Dornwald", "kampf": True}])
        self.assertEqual([f["name"] for f in abfragen.detail(5, {"spiel": "x-y"})["faehigkeiten"] if f["versteckt"]], ["Anpassung"])
        # nicht im Spiel: die Seite kommt trotzdem und sagt es; Legenden: Arceus kennt keine Fähigkeiten
        self.assertFalse(abfragen.detail(14, {"spiel": "red-blue"})["im_spiel"])
        la = abfragen.detail(14, {"spiel": "legends-arceus"})
        self.assertEqual((la["im_spiel"], la["faehigkeiten"]), (True, []))
        self.assertIsNone(abfragen.detail(999, {"spiel": "x-y"}))
        self.ohne_fehler()

    def test_lernlisten(self):
        """Jede Lernliste der Welt kommt so an, wie sie in minidb.LERNEN steht: Attacken, Wege, TM-Nummer des Spiels."""
        n = 0
        for spiel in SPIELE:
            lernspiel = lernspiel_von(spiel)
            self.assertEqual(lernspiel, minidb.ERWEITERUNG.get(spiel, spiel))
            for pid, _, _ in erwartete_liste(spiel):
                soll = minidb.lernt(pid, lernspiel)
                r = abfragen.moves_of(pid, {"spiel": spiel})
                self.assertEqual(r["spiel"], lernspiel)
                got = {m["id"]: m for m in r["attacken"] + r["status"]}
                self.assertTrue(soll, (pid, spiel))
                self.assertEqual(set(got), {minidb.ATTACKE[m][0] for m, _, _ in soll}, (pid, spiel))
                for move, weg, level in soll:
                    wege = " / ".join(got[minidb.ATTACKE[move][0]]["wege"])
                    if weg == 1:
                        self.assertIn(f"Level {level}", wege, (pid, spiel, move))
                    elif weg == 4:
                        self.assertIn(f"TM{minidb.tm_nummer(move, lernspiel):02d}", wege, (pid, spiel, move))
                n += 1
        self.assertEqual(n, sum(len(erwartete_liste(s)) for s in SPIELE))
        # dieselbe TM, andere Nummer je Spiel; Feenglanz erst ab Generation 6; Beherrschung in Legenden: Arceus
        wege = lambda pid, spiel: {m["name"]: m["wege"] for m in abfragen.moves_of(pid, {"spiel": spiel})["attacken"]}
        self.assertEqual((wege(10, "emerald")["Erdstoß"], wege(10, "the-teal-mask")["Erdstoß"]), (["Level 20", "TM04"], ["Level 20", "TM02"]))
        self.assertNotIn("Feenglanz", wege(9, "emerald"))
        self.assertIn("Feenglanz", wege(9, "x-y"))
        self.assertEqual(wege(14, "legends-arceus")["Schattenhauch"], ["Level 9, Beherrschung ab 19"])
        # Urknall hatte vor Schwarz/Weiß Stärke 120
        urknall = lambda spiel: next((m["staerke"], m["geaendert"]) for m in abfragen.moves_of(3, {"spiel": spiel})["attacken"] if m["name"] == "Urknall")
        self.assertEqual((urknall("emerald"), urknall("scarlet-violet")), ((120, True), (150, False)))
        # Standard-Attacken wie im Spiel: höchstens vier, mit Level die letzten bis dahin
        ohne = abfragen.moves_of(3, {"spiel": "scarlet-violet"})["standard"]
        mit = abfragen.moves_of(3, {"spiel": "scarlet-violet", "level": 40})["standard"]
        self.assertEqual((len(ohne), len(mit)), (4, 4))
        self.assertIn(minidb.ATTACKE["urknall"][0], mit)
        self.assertNotIn(minidb.ATTACKE["urknall"][0], ohne)
        # bewährtes Set aus Showdown für Generation 9
        sets = abfragen.moves_of(3, {"spiel": "scarlet-violet"})["sets"]
        self.assertEqual([[a["name"] for a in s["attacken"]] for s in sets], [["Saugwurzel", "Giftranke", "Erdstoß", "Kraftschub"]])
        self.assertTrue(all(a["lernbar"] for a in sets[0]["attacken"]))
        self.ohne_fehler()

    def test_attackenliste(self):
        for spiel in SPIELE:
            gen = minidb.SPIEL_GEN[minidb.SPIEL[spiel]]
            lernbar = {minidb.ATTACKE[m][0] for pid in minidb.LERNEN for m, _, _ in minidb.lernt(pid, lernspiel_von(spiel))}
            rows = abfragen.move_list({"spiel": spiel})["rows"]
            self.assertTrue(all(m["gen"] <= gen for m in rows), spiel)
            self.assertLessEqual(lernbar, {m["id"] for m in rows}, spiel)
        rows = {m["name"]: m for m in abfragen.move_list({"spiel": "emerald"})["rows"]}
        self.assertNotIn("Feenglanz", rows)
        self.assertEqual((rows["Urknall"]["staerke"], rows["Urknall"]["geaendert"]), (120, True))
        self.assertEqual(rows["Giftranke"]["kurz"], "vergiftet (30 %)")
        self.assertLess(rows["Urknall"]["wertung"], rows["Flammenwand"]["wertung"])     # muss danach aussetzen
        self.ohne_fehler()

    def test_gebiete_und_fundorte(self):
        """0.59.0: Die Häufigkeit zählt jeden Platz einmal. Vorher zählte jede Zeile der PokéAPI: doppelt in Spielen mit
        zwei Editionen (Nebula stand mit 40 % statt 20 % da)."""
        abfragen._AREAS.clear()
        xy = abfragen.areas({"spiel": "x-y"})
        self.assertEqual(xy["quelle"], "PokéAPI")
        self.assertEqual([g["ort"] for g in xy["gebiete"]], ["Lichterhain"])
        mons = {m["name"]: m for m in xy["gebiete"][0]["mons"]}
        self.assertEqual({k: (m["anteil"], m["editionen"], m["level"]) for k, m in mons.items()},
                         {"Nebula": (20, [], "20–22"), "Keimling": (10, ["X"], "18–20"), "Glutli": (10, ["Y"], "18–20")})
        em = {g["ort"]: {m["name"]: (m["anteil"], m["methode"]) for m in g["mons"]} for g in abfragen.areas({"spiel": "emerald"})["gebiete"]}
        self.assertEqual(em["Nebelwiese"], {"Keimling": (20, "Im hohen Gras oder in einer Höhle laufen"),
                                            "Zappel": (10, "Im hohen Gras oder in einer Höhle laufen")})
        self.assertEqual(em["Kieselbucht"], {"Tropfi": (60, "Surfen")})
        pt = {g["ort"]: g["mons"] for g in abfragen.areas({"spiel": "platinum"})["gebiete"]}
        self.assertEqual(sorted(pt), ["Frosthang", "Frosthang (Höhle)"])
        self.assertEqual(pt["Frosthang (Höhle)"][0]["bedingungen"], ["In der Nacht"])
        # dieselben Begegnungen auf der Detailseite
        self.assertEqual(abfragen.detail(13, {"spiel": "platinum"})["fundorte"],
                         [{"ort": "Frosthang (Höhle)", "methode": "Im hohen Gras oder in einer Höhle laufen", "level": "8",
                           "bedingungen": ["In der Nacht"], "editionen": []}])
        self.assertEqual([f["editionen"] for f in abfragen.detail(4, {"spiel": "x-y"})["fundorte"]], [["Y"]])
        self.assertEqual(abfragen.detail(4, {"spiel": "emerald"})["fundorte"], [])
        self.ohne_fehler()

    def test_gebiete_je_spiel(self):
        """0.58.0: Die Gebiete zweier Spiele bleiben nebeneinander bereit; das am längsten nicht gefragte fällt weg."""
        abfragen._AREAS.clear()
        a = abfragen.areas({"spiel": "emerald"})
        b = abfragen.areas({"spiel": "platinum"})
        self.assertTrue(a["gebiete"] and b["gebiete"])
        self.assertIs(abfragen.areas({"spiel": "emerald"}), a)
        self.assertIs(abfragen.areas({"spiel": "platinum"}), b)
        self.assertEqual(len(abfragen._AREAS), 2)
        for g in ("ruby-sapphire", "firered-leafgreen", "diamond-pearl", "heartgold-soulsilver", "black-white", "x-y"):
            abfragen.areas({"spiel": g})
        self.assertEqual(len(abfragen._AREAS), abfragen.AREAS_MAX)
        abfragen._AREAS.clear()

    def test_getragene_items(self):
        """Getragene Items wilder Pokémon (PokéAPI, pokemon_items): je Spiel, mit Edition nur, wenn sie sich unterscheiden."""
        traegt = lambda pid, spiel: [(h["item"], h["prozent"], h["quelle"], h["editionen"]) for h in abfragen.detail(pid, {"spiel": spiel})["getragen"]]
        self.assertEqual(traegt(6, "emerald"), [("Kräutersaft", "50 %", "PokéAPI", [])])
        self.assertEqual(traegt(11, "x-y"), [("Glücksfeder", "5 %", "PokéAPI", [])])            # in X und Y gleich
        self.assertEqual(traegt(1, "x-y"), [("Blattamulett", "5 %", "PokéAPI", ["X"])])
        self.assertEqual(traegt(6, "platinum"), [])
        self.ohne_fehler()
        # die Tabelle gehört zu den Dateien, die der Abgleich auch ohne die Liste der PokéAPI holt (fehlte bis 0.58.1)
        self.assertIn("pokemon_items", importer.NEEDED)

    def test_tabellen_der_abfragen_werden_geholt(self):
        """Jede Tabelle, die eine Abfrage liest, baut der Importer selbst oder steht in importer.NEEDED. Sonst fehlt sie,
        sobald der Abgleich die Liste der PokéAPI nicht bekommt, und die Abfrage antwortet still leer."""
        quelltext = app_quellen()                                   # auch in Paketen (app/abfragen/)
        alles = "".join(quelltext.values())
        gebaut = set(re.findall(r"CREATE (?:TEMP )?(?:TABLE|VIEW) (?:IF NOT EXISTS )?([a-z_0-9]+)", alles))
        gelesen = {}
        for name, text in quelltext.items():
            for m in re.finditer(r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", text):
                gelesen.setdefault(m.group(1), set()).add(name)
        self.assertGreater(len(gelesen), 60)
        fehlt = {t: sorted(wo) for t, wo in gelesen.items() if t not in gebaut and t not in importer.NEEDED and t != "sqlite_master"}
        self.assertEqual(fehlt, {})

    def test_items(self):
        # Mit wenigen Beschreibungen je Spiel gilt die Liste als ungenau: Items der Generation, mit Hinweis
        grob = abfragen.item_list({"spiel": "emerald"})
        self.assertIn("keine eigene Item-Liste", grob["hinweis"])
        # ab ITEMS_GENAU Beschreibungen sind es genau die Items des Spiels
        with im_paket(abfragen, "ITEMS_GENAU", 3):
            for spiel in SPIELE:
                vg = minidb.SPIEL[spiel]
                r = abfragen.item_list({"spiel": spiel})
                soll = {i[2] for i in minidb.ITEMS if (i[0] <= 3 if spiel == "legends-arceus" else i[6] <= minidb.SPIEL_GEN[vg])}
                self.assertEqual({i["name"] for i in r["items"]}, soll, spiel)
                self.assertEqual(r["hinweis"], "", spiel)
                for i in r["items"]:
                    # die TM trägt die Attacke dieses Spiels; in Erweiterungen die des Hauptspiels (die PokéAPI führt die
                    # Maschinen dort; bis 0.59.0 fehlte die Attacke, in der Welt hat die Erweiterung keine eigenen)
                    if i["tasche"] == "Maschinen":
                        nr = int(i["name"][2:])
                        soll_att = next(m for m in minidb.TM if minidb.tm_nummer(m, minidb.ERWEITERUNG.get(spiel, spiel)) == nr)
                        self.assertEqual(i["attacke"]["name"], minidb.ATTACKE[soll_att][2], (spiel, i["name"]))
            em = abfragen.item_list({"spiel": "emerald"})
            self.assertEqual(em["taschen"], ["Items", "Medizin", "Bälle", "Maschinen"])
            saft = next(i for i in em["items"] if i["name"] == "Kräutersaft")
            self.assertEqual((saft["wirkung"], saft["preis"], saft["englisch"]), ("KP +20", 300, False))
        self.ohne_fehler()

    def test_fangtabelle(self):
        baelle = lambda pid, spiel: {x["ball"].split(" (")[0]: x["faktor"] for x in abfragen.detail(pid, {"spiel": spiel})["mehr"]["fangen"]}
        self.assertEqual(baelle(6, "emerald"), {"Pokéball": 1, "Superball": 1.5, "Hyperball": 2, "Netzball": 3})
        self.assertEqual(baelle(6, "scarlet-violet"), {"Pokéball": 1, "Superball": 1.5, "Hyperball": 2, "Netzball": 3.5, "Finsterball": 3})
        self.assertNotIn("Netzball", baelle(4, "scarlet-violet"))               # Glutli ist weder Wasser noch Käfer
        self.assertEqual(baelle(6, "red-blue"), {"Pokéball": 1, "Superball": 1.5, "Hyperball": 2})
        mehr = abfragen.detail(10, {"spiel": "emerald"})["mehr"]
        self.assertEqual((mehr["fangrate"], mehr["eigruppen"], mehr["fang_gen"]), (minidb.ART[10][11], ["Mineral"], 3))
        # je höher der Faktor, desto höher die Chance; mit Status höher als ohne
        f = abfragen.detail(12, {"spiel": "scarlet-violet"})["mehr"]["fangen"]
        self.assertEqual([x["voll"] for x in f[:3]], sorted(x["voll"] for x in f[:3]))
        self.assertTrue(all(x["schlaf"] >= x["voll"] for x in f))
        # Legenden: Arceus hat eigene Bälle (eine Tabelle: abfragen.HISUI_BALLS über /api/meta)
        la = abfragen.detail(14, {"spiel": "legends-arceus"})["mehr"]
        self.assertEqual([x["ball"] for x in la["fangen"]], [b[0] for b in la["fang_hisui"]])
        self.assertEqual([b[:2] for b in la["fang_hisui"]], [b[:2] for b in server.meta()["hisui_baelle"]][:len(la["fang_hisui"])])
        self.ohne_fehler()

    def test_spielprofil(self):
        """0.60.0: Was die Detailseite zeigt, folgt dem Spielprofil (app/spiele.py), nicht mehr der Kennung des Spiels."""
        D = abfragen.data()
        self.assertEqual(len(D.games), len(minidb.SPIEL) + len(spiele.EIGENE))
        for g in D.games:                                                       # jedes Spiel hat einen Eintrag, dieselbe Generation
            self.assertTrue(spiele.bekannt(g["kennung"]), g["kennung"])
            self.assertEqual(spiele.profil(g["kennung"])["gen"], g["gen"], g["kennung"])
        mehr = lambda spiel: abfragen.detail(1, {"spiel": spiel})["mehr"]
        hat = lambda spiel, *felder: [f in mehr(spiel) for f in felder]
        # Ei-Gruppen nur, wo es Zucht gibt; EV-Ausbeute nur, wo es EVs gibt
        self.assertEqual(hat("emerald", "eigruppen", "eizyklen", "ev"), [True, True, True])
        self.assertEqual(hat("gold-silver", "eigruppen", "ev"), [True, False])
        self.assertEqual(hat("red-blue", "eigruppen", "ev"), [False, False])
        self.assertEqual(hat("legends-za", "eigruppen", "eizyklen", "ev"), [False, False, True])
        for spiel in ("colosseum", "xd", "lets-go-pikachu-lets-go-eevee", "legends-arceus", "mega-dimension", "champions"):
            self.assertEqual(hat(spiel, "eigruppen", "eizyklen"), [False, False], spiel)
        for spiel in ("lets-go-pikachu-lets-go-eevee", "legends-arceus", "champions", "pokopia"):
            self.assertEqual(hat(spiel, "ev"), [False], spiel)
        # Fangchance: genau, als Richtwert (auch in der Erweiterung von Legenden: Z-A) oder gar nicht (Kampfspiel)
        self.assertEqual({s_: mehr(s_)["fang_grob"] for s_ in ("emerald", "scarlet-violet", "gold-silver", "legends-za", "mega-dimension",
                                                             "lets-go-pikachu-lets-go-eevee", "legends-arceus")},
                         {"emerald": False, "scarlet-violet": False, "gold-silver": True, "legends-za": True, "mega-dimension": True,
                          "lets-go-pikachu-lets-go-eevee": True, "legends-arceus": False})
        self.assertEqual(hat("champions", "fangrate", "fangen", "fang_grob", "fang_gen", "schlaf_faktor"), [True, False, False, False, False])
        self.assertEqual(hat("legends-arceus", "fangen", "fang_hisui"), [True, True])
        self.assertEqual(hat("emerald", "fangen", "fang_hisui"), [True, False])
        # die Oberfläche bekommt je Spiel genau ihre Felder, auch für Pokémon HOME
        sp = {g["kennung"]: g["profil"] for g in server.meta()["spiele"]}
        self.assertEqual(set(sp), set(minidb.SPIEL) | {"pokopia", spiele.HOME})
        for kennung, pr in sp.items():
            self.assertEqual(pr, spiele.fuer_oberflaeche(spiele.profil(kennung)), kennung)
        self.assertEqual((sp["champions"]["kampf"], sp["the-teal-mask"]["auftraege"], sp["mega-dimension"]["auftraege"],
                          sp["legends-arceus"]["werte"], sp[spiele.HOME]["werte"]), (True, "the-indigo-disk", "legends-za", "el", "ev"))
        # Aufträge: die Erweiterung fragt unter dem Schlüssel ihres Hauptspiels, Karmesin/Purpur die Blaubeer-Missionen
        self.assertEqual([abfragen.request_list({"spiel": s_}).get("spiel") for s_ in
                          ("legends-arceus", "legends-za", "mega-dimension", "the-teal-mask", "the-indigo-disk", "emerald", "")],
                         ["legends-arceus", "legends-za", "legends-za", "the-indigo-disk", "the-indigo-disk", None, "legends-arceus"])
        self.ohne_fehler()

    def test_spiel_ohne_profil_steht_im_register(self):
        """Ein Spiel der Datenbank ohne Eintrag in app/spiele.py läuft als Hauptspiel seiner Generation und wird gemeldet."""
        os.remove(db.pokeapi_path())
        shutil.copy(minidb.pfad(), db.pokeapi_path())
        con = sqlite3.connect(db.pokeapi_path())
        con.execute("INSERT INTO spiel VALUES (2000, 'legends-morgen', 'Legenden: Morgen', 2, 99)")
        con.execute("UPDATE spiel SET gen = 4 WHERE kennung = 'emerald'")
        con.commit()
        con.close()
        D = abfragen.data()
        self.assertEqual(dict(abfragen.profil(D.game_by["legends-morgen"])), spiele.grund(2))
        self.assertTrue(abfragen.no_abilities(D.game_by["legends-morgen"]))
        self.assertEqual(abfragen.profil(D.game_by["emerald"])["gen"], 4)       # wie überall sonst gilt die Generation der Datenbank
        self.assertEqual(sorted((e["wo"], e["art"], e["text"]) for e in fehler.liste()),
                         [("spiele.profil", "Generation weicht ab", "emerald: Datenbank 4, Profil 3; es gilt die der Datenbank"),
                          ("spiele.profil", "Spiel ohne Profil",
                           "legends-morgen gilt als Hauptspiel der Generation 2; Eintrag in app/spiele.py fehlt")])
        self.assertIn("legends-morgen", [g["kennung"] for g in server.meta()["spiele"]])

    def test_team(self):
        ev = abfragen.team_view({"spiel": "scarlet-violet", "ids": [3, 5, 7], "details": [{}, {}, {"tera": TYP["Elektro"]}]})
        self.assertEqual([m["name"] for m in ev["mitglieder"]], ["Dornwald", "Lohrax", "Flutor"])
        self.assertEqual([v["slot"] for v in ev["verbesserungen"]], [0, 1, 2])
        self.assertEqual(ev["nicht_im_spiel"], [])
        self.assertEqual(set(ev["abgedeckt"]) | set(ev["nicht_abgedeckt"]), set(range(1, 19)))
        self.assertEqual(ev["matrix"]["3"][str(TYP["Pflanze"])], 0.25)          # Pflanze/Gift gegen Pflanze
        self.assertEqual([t["slot"] for t in ev["tera"]], [2])
        self.assertIn(TYP["Boden"], ev["tera"][0]["neu"])                       # Tera Elektro: neu schwach gegen Boden
        # Tera gibt es nur in Karmesin/Purpur; wer nicht im Spiel ist, wird genannt
        la = abfragen.team_view({"spiel": "legends-arceus", "ids": [14, 14, 12], "details": [{"tera": TYP["Elektro"]}, {}, {}]})
        self.assertEqual((la["tera"], la["nicht_im_spiel"]), ([], [2]))
        best = abfragen.team_optimize({"spiel": "scarlet-violet", "filter": {"ohne_leg": 1, "endstufe": 1}})["teams"][0]
        self.assertEqual(len(best["ids"]), 6)
        self.assertNotIn(12, best["ids"])                                       # Urdrache ist legendär
        self.assertTrue(all(m["endstufe"] for m in best["mitglieder"]))
        vor = abfragen.team_suggest({"spiel": "scarlet-violet", "ids": [3]})["rows"]
        self.assertTrue(vor and 3 not in [r["id"] for r in vor])
        self.assertEqual([r["plus"] for r in vor], sorted((r["plus"] for r in vor), reverse=True))
        mu = abfragen.team_matchup({"spiel": "scarlet-violet", "ids": [3], "gegner": [5, 7]})
        self.assertEqual([e["gegner"]["name"] for e in mu["einzeln"]], ["Lohrax", "Flutor"])
        self.assertEqual(mu["einzeln"][1]["rows"][0]["austeilen"], 2.0)         # Pflanze trifft Wasser/Eis doppelt
        # Gefangene: Filter und Empfehlungen
        server.set_mark("gefangen", {"spiel": "scarlet-violet", "id": [1]})
        self.assertEqual([x["name"] for x in abfragen.search({"spiel": "scarlet-violet", "nur": "gef"})["rows"]], ["Keimling"])
        r = abfragen.team_caught({"spiel": "scarlet-violet", "ids": [5, 7]})
        self.assertEqual(r["gefangen"], 1)
        self.assertTrue(r["alternativen"] or r["potential"])
        self.ohne_fehler()

    def test_schaden_und_werte(self):
        erd = minidb.ATTACKE["erdstoss"][0]
        r = abfragen.damage_view({"spiel": "scarlet-violet", "ids": [10], "details": [{"attacken": [erd]}], "slot": 0, "attacke": erd,
                                  "verteidiger": [5, 9, 11]})
        self.assertEqual((r["angreifer"], r["attacke"], r["staerke"], r["stab"], r["level"], r["gen"]), ("Steinchen", "Erdstoß", 100, 1.5, 50, 9))
        lohrax, donnrik, nebula = r["rows"]
        self.assertEqual(lohrax["eff"], 2.0)
        self.assertEqual(lohrax["grund"], (22 * 100 * lohrax["angriff"] // lohrax["verteidigung"]) // 50 + 2)
        self.assertEqual(len(lohrax["werte"]), 16)
        self.assertEqual((lohrax["min"], lohrax["max"]), (min(lohrax["werte"]), max(lohrax["werte"])))
        self.assertIn("Basis 80", lohrax["a_info"])
        self.assertEqual((donnrik["eff"], donnrik["max"]), (0.0, 0))            # Flug
        self.assertEqual((nebula["max"], nebula["faehigkeit_vert"]), (0, "Schwebe"))
        self.assertEqual(abfragen.damage_view({"spiel": "scarlet-violet", "ids": [10], "slot": 3, "attacke": erd})["rows"], [])
        # Generation 1 rechnet mit eigener Formel; Legenden: Arceus mit Effort Levels
        rb = abfragen.damage_view({"spiel": "red-blue", "ids": [5], "details": [{"attacken": [erd]}], "slot": 0, "attacke": erd, "verteidiger": [3]})
        self.assertEqual((rb["gen"], len(rb["rows"])), (1, 1))
        self.assertGreater(rb["rows"][0]["max"], 0)
        kw = {"spiel": "legends-arceus", "ids": [14], "slot": 0, "attacke": 1, "verteidiger": [8]}
        la0 = abfragen.damage_view({**kw, "details": [{"attacken": [1]}]})
        la10 = abfragen.damage_view({**kw, "details": [{"attacken": [1], "el": [0, 10, 0, 0, 0, 0]}]})
        self.assertEqual((la10["art"], la10["el"]), ("la", 10))
        self.assertGreater(la10["rows"][0]["angriff"], la0["rows"][0]["angriff"])
        # Statuswerte: Urdrache, Angriff 150, 252 EV, Level 100, neutrales Wesen: ⌊(2·150 + 31 + 63) · 100 / 100⌋ + 5 = 399
        sv = abfragen.stats_view({"spiel": "scarlet-violet", "id": 12, "level": 100, "evs": [0, 252, 0, 0, 4, 252]})
        self.assertEqual((len(sv["rows"]), sv["gen"], sv["rows"][1]["wert"]), (6, 9, 399))
        self.assertEqual(sv["rows"][0]["wert"], 2 * 105 + 31 + 100 + 10)        # KP ohne EV
        self.assertEqual(abfragen.stats_view({"spiel": "legends-arceus", "id": 14})["rows"], [])
        self.ohne_fehler()

    def test_import_und_export(self):
        r = abfragen.paste_import({"text": "Dornwald @ Blattamulett\nAbility: Blattwerk\nModest Nature\n- Saugwurzel\n\n"
                                           "Lohrax\n- Erdstoß\n\nFlutor-Hisui\n- Flutwelle\n\nGibtsnicht\n"})
        self.assertEqual(r["ids"], [3, 5, 10002])
        self.assertEqual(r["hinweise"], ["„Gibtsnicht“ nicht gefunden"])
        self.assertEqual(r["details"][0]["attacken"], [minidb.ATTACKE["saugwurzel"][0]])
        self.assertEqual(r["details"][0]["item"], minidb.ITEM["blattamulett"][0])
        text = abfragen.paste_export({"ids": r["ids"], "details": r["details"]})["text"]
        self.assertIn("Dornwald @ Blattamulett\nAbility: Blattwerk\nModest Nature\n- Saugwurzel", text)
        self.assertIn("- Erdstoss", text)                   # englischer Name der Attacke
        self.assertIn("Flutor-Hisui", text)
        self.ohne_fehler()

    def test_was_fehlt(self):
        server.set_mark("gefangen", {"spiel": "emerald", "id": 1, "an": True})
        d = abfragen.missing({"spiel": "emerald"})
        arten = len(erwartete_liste("emerald"))
        self.assertEqual((d["arten"], d["gefangen"], len(d["fehlt"])), (arten, 1, arten - 1))
        by = {x["name"]: x for x in d["fehlt"]}
        self.assertNotIn("Keimling", by)
        self.assertEqual((by["Rankel"]["weg"], by["Rankel"]["wege"][0]["hast_name"]), ("jetzt", "Keimling"))
        self.assertEqual(by["Dornwald"]["weg"], "jetzt")                    # die Vorstufe der Vorstufe zählt
        self.assertEqual(by["Tropfi"]["weg"], "wild")
        self.assertIn("Kieselbucht", by["Tropfi"]["wege"][0]["text"])
        self.assertIn("zucht", [w["art"] for w in by["Funkel"]["wege"]])    # Baby: Ei von Zappel
        self.assertEqual((len(by["Rankel"]["werte"]), by["Rankel"]["summe"]), (6, sum(by["Rankel"]["werte"])))
        # Editionen: Glutli gibt es wild nur in Y
        x = {m["name"]: m for m in abfragen.missing({"spiel": "x-y", "edition": "X"})["fehlt"]}
        self.assertIn("edition", [w["art"] for w in x["Glutli"]["wege"]])
        self.assertEqual(x["Keimling"]["weg"], "wild")
        la = abfragen.missing({"spiel": "legends-arceus"})
        self.assertNotIn("zucht", {w["art"] for m in la["fehlt"] for w in m["wege"]})       # keine Zucht in Legenden: Arceus
        self.assertIsNone(abfragen.missing({"spiel": "gibt-es-nicht"}))
        self.ohne_fehler()

    def test_typtabelle_und_pruefliste(self):
        rb, xy = abfragen.type_chart({"spiel": "red-blue"}), abfragen.type_chart({"spiel": "x-y"})
        self.assertEqual((rb["gen"], len(rb["typen"]), len(xy["typen"])), (1, 15, 18))
        self.assertNotIn("Fee", [t["name"] for t in rb["typen"]])
        self.assertEqual(xy["tabelle"][str(TYP["Fee"])][str(TYP["Drache"])], 2.0)
        self.assertEqual(xy["tabelle"][str(TYP["Geist"])][str(TYP["Normal"])], 0.0)
        p = abfragen.pruefung()
        self.assertEqual([(x["name"], x["feld"], x["pokeapi"], x["showdown"], x["entscheidung"]) for x in p],
                         [("Geröllwurf", "Stärke", "75", "80", ""), ("Steinchen", "Initiative", "30", "35", "")])
        m = server.meta()
        self.assertEqual((m["has_data"], m["formen"], m["attacken"], m["max_gen"]), (True, len(minidb.ARTEN) + 2, len(minidb.ATTACKEN), 9))
        spiele = {s["kennung"]: s for s in m["spiele"]}
        self.assertEqual(spiele["x-y"]["pokemon"], len(erwartete_liste("x-y")))
        self.assertEqual(spiele["pokopia"]["pokemon"], 0)
        self.ohne_fehler()

    def test_keine_abfrage_weicht_still_aus(self):
        """Jede Abfrage für jedes Spiel und jedes Pokémon, auch für Spiele ohne Daten: nichts wirft, und das Fehlerregister
        bleibt leer. Die Abfragen fangen Ausnahmen und melden sie (seit 0.58.1); hier darf keine Meldung entstehen."""
        ids = [a[0] for a in minidb.ARTEN] + [f[0] for f in minidb.FORMEN]
        n = 0
        for spiel in SPIELE + OHNE_DATEN + ("", "gibt-es-nicht"):
            q = {"spiel": spiel}
            for fn in (abfragen.search, abfragen.move_list, abfragen.item_list, abfragen.type_chart, abfragen.missing, abfragen.areas,
                       abfragen.raid_list, abfragen.trainer_list, abfragen.request_list):
                fn(dict(q))
                n += 1
            for fn in (abfragen.shiny_locks, abfragen.alpha_possible, abfragen.smogon_view):
                fn(spiel)
                n += 1
            for pid in ids:
                abfragen.detail(pid, dict(q))
                abfragen.moves_of(pid, dict(q))
                n += 2
            abfragen.team_view({**q, "ids": ids[:6]})
            abfragen.team_suggest({**q, "ids": ids[:2]})
            abfragen.team_matchup({**q, "ids": ids[:3], "gegner": ids[3:6]})
            abfragen.team_doubles({**q, "ids": ids[:4]})
            abfragen.damage_matrix({**q, "ids": ids[:3], "details": [{"attacken": [1, 13]}] * 3, "verteidiger": ids[3:6]})
            abfragen.effort_view({**q, "id": 14})
            abfragen.stats_view({**q, "id": 3})
            n += 7
        self.assertGreater(n, 600)
        self.ohne_fehler()


class ServerMitDaten(HttpMitDaten):
    """Der Server über HTTP mit der Mini-Datenbank: derselbe Weg wie die Oberfläche."""

    def test_alle_wege_mit_daten(self):
        """Jeder lesende Weg für jedes Spiel: 200 oder ein begründetes 404, immer JSON, nie 500, kein Hinweis auf fehlende Teile."""
        wege = ["/api/meta", "/api/stand", "/api/status", "/api/neuigkeiten", "/api/teams", "/api/pruefung", "/api/aufgabe",
                "/api/export", "/api/fehler", "/api/typen", "/api/diag", "/api/speicher", "/healthz"]
        je_spiel = ("pokemon", "attacken", "items", "typen", "fehlt", "gebiete", "favoriten", "gefangen", "schillernd", "alpha",
                    "gefunden", "shinysperre", "raids", "trainer", "auftraege", "kampftagebuch", "smogon", "mapgenie", "sammeln",
                    "tmorte")
        ids = [a[0] for a in minidb.ARTEN] + [f[0] for f in minidb.FORMEN]
        for spiel in SPIELE + OHNE_DATEN:
            wege += [f"/api/{w}?spiel={spiel}" for w in je_spiel]
            wege += [f"/api/pokemon/{i}{x}?spiel={spiel}" for i in ids for x in ("", "/attacken")]
        codes = {}
        for weg in wege:
            code, kopf, rumpf = self.get(weg)
            self.assertIn(code, (200, 404), weg)
            self.assertNotIn(server.FEHLER_KOPF, kopf, weg)
            self.assertEqual(kopf["Content-Type"], "application/json; charset=utf-8", weg)
            self.assertEqual(kopf["X-Content-Type-Options"], "nosniff", weg)
            json.loads(rumpf)
            codes.setdefault(code, []).append(weg)
        self.assertGreater(len(codes[200]), 600)
        # 404 nur dort, wo es für das Spiel nichts gibt (kein Dex, keine Gebiete), nie für ein Pokémon der Welt
        self.assertFalse([w for w in codes.get(404, []) if not re.match(r"/api/(fehlt|gebiete)\?", w)], codes.get(404))
        self.ohne_fehler()

    def test_unbekanntes(self):
        self.assertEqual(self.json("/api/pokemon/999?spiel=x-y", status=404), {"error": "Pokémon nicht gefunden"})
        self.assertEqual(self.json("/api/pokemon/999/attacken", status=404), {"error": "Pokémon nicht gefunden"})
        self.assertEqual(self.json("/api/gibt-es-nicht", status=404), {"error": "nicht gefunden"})
        self.assertEqual(self.json("/api/gibt-es-nicht", {}, status=404), {"error": "nicht gefunden"})
        # 0.64.0 entfernt (ohne Aufrufer; die eigenen Punkte stehen in der zusammengeführten Karte von /api/mapgenie)
        self.assertEqual(self.json("/api/mapgenie/eigene?spiel=legends-arceus&karte=x", status=404), {"error": "nicht gefunden"})
        self.assertEqual(self.json("/api/fehlt?spiel=gibt-es-nicht", status=404), {"error": "kein Spiel"})
        # falsche Eingaben: 400 mit Grund, kein 500
        self.assertEqual(self.json("/api/werte", {"spiel": "scarlet-violet", "id": 999}, status=400)["error"], "Pokémon nicht gefunden")
        self.assertIn("Namen", self.json("/api/teams", {"mitglieder": [3]}, status=400)["error"])
        code, _, rumpf = self._request("POST", "/api/gefangen", b"spiel=x", {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual((code, json.loads(rumpf)), (400, {"error": "nur application/json"}))
        code, _, rumpf = self._request("POST", "/api/gefangen", b"[1]", {"Content-Type": "application/json"})
        self.assertEqual((code, json.loads(rumpf)), (400, {"error": "JSON-Objekt erwartet"}))
        # fremder Hostname (DNS-Rebinding): abgelehnt, bevor irgendetwas gelesen wird
        code, _, rumpf = self.get("/api/pokemon?spiel=x-y", Host="boese.example.org")
        self.assertEqual(code, 421)
        self.ohne_fehler()

    def test_eigene_daten_ueber_http(self):
        """Merken, Team speichern, Sicherung und Wiederherstellen über die Schnittstelle: Eigenes bleibt, was der User setzt."""
        self.assertEqual(self.json("/api/gefangen?spiel=emerald"), [])
        self.json("/api/gefangen", {"spiel": "emerald", "id": [1, 6]})
        self.json("/api/schillernd", {"spiel": "emerald", "id": 8})                # schillernd heißt auch gefangen
        self.assertEqual(sorted(self.json("/api/gefangen?spiel=emerald")), [1, 6, 8])
        self.assertEqual(self.json("/api/gefangen?spiel=platinum"), [])            # je Spiel getrennt
        fehlt = self.json("/api/fehlt?spiel=emerald")
        self.assertEqual((fehlt["gefangen"], len(fehlt["fehlt"])), (3, fehlt["arten"] - 3))
        self.json("/api/gefangen", {"spiel": "emerald", "id": 8, "an": False})    # nicht mehr gefangen nimmt schillernd mit
        self.assertEqual(self.json("/api/schillernd?spiel=emerald"), [])
        self.json("/api/favoriten", {"spiel": "x-y", "id": 11})
        self.assertEqual([f["name"] for f in self.json("/api/favoriten?spiel=x-y")], ["Nebula"])
        tid = self.json("/api/teams", {"name": "  Probe   Team ", "spiel": "scarlet-violet", "mitglieder": [3, 5, 7], "fest": [3, 99],
                                       "details": {"3": {"level": 50, "attacken": [23, 13]}}})["id"]
        team = self.json("/api/teams")[0]
        self.assertEqual((team["id"], team["name"], team["mitglieder"], team["fest"]), (tid, "Probe Team", [3, 5, 7], [3]))
        # Sicherung, alles löschen, wiederherstellen: derselbe Stand
        code, kopf, rumpf = self.get("/api/export")
        self.assertIn("attachment", kopf["Content-Disposition"])
        sicherung = json.loads(rumpf)
        self.json("/api/teams/loeschen", {"id": tid})
        self.json("/api/gefangen", {"spiel": "emerald", "id": [1, 6], "an": False})
        self.assertEqual((self.json("/api/teams"), self.json("/api/gefangen?spiel=emerald")), ([], []))
        self.json("/api/restore", sicherung)
        self.assertEqual(sorted(self.json("/api/gefangen?spiel=emerald")), [1, 6])
        self.assertEqual([t["name"] for t in self.json("/api/teams")], ["Probe Team"])
        self.assertEqual(json.loads(self.get("/api/export")[2])["teams"][0]["mitglieder"], sicherung["teams"][0]["mitglieder"])
        # die Mini-Datenbank selbst bleibt unberührt (pokeapi.db ist nur lesend)
        self.assertTrue(os.path.islink(db.pokeapi_path()))
        self.ohne_fehler()

    def test_antworten_cache(self):
        """Antworten mit Daten sind frisch (no-store); große Antworten kommen gepackt, wenn der Browser es annimmt."""
        code, kopf, rumpf = self.get("/api/pokemon/3?spiel=x-y", **{"Accept-Encoding": "gzip"})
        self.assertEqual((code, kopf["Cache-Control"]), (200, "no-store"))
        code, kopf, gepackt = self.get("/api/pokemon/3/attacken?spiel=scarlet-violet", **{"Accept-Encoding": "gzip"})
        if kopf.get("Content-Encoding") == "gzip":
            import gzip
            self.assertEqual(json.loads(gzip.decompress(gepackt)), self.json("/api/pokemon/3/attacken?spiel=scarlet-violet"))
        with im_paket(abfragen, "detail", side_effect=RuntimeError("Probe")):
            code, kopf, rumpf = self.get("/api/pokemon/3?spiel=x-y")
        self.assertEqual(code, 500)
        self.assertIn("RuntimeError", json.loads(rumpf)["error"])
        self.assertEqual([(e["quelle"], e["wo"]) for e in fehler.liste()], [("server", "/api/pokemon/N")])


class Vertrag(HttpMitDaten):
    """Vertrag zwischen Server und Oberfläche (0.59.0, nach dem Muster der Geschwister): Die Antworten haben die Form aus
    tests/vertrag.json, die Oberfläche kennt jedes Feld, und beide Seiten kennen dieselben Wege. Mit Absicht geändert:
    `python3 -m tests.vertrag` schreibt die Datei neu, die Änderung steht dann im Diff."""
    # Felder, die der Server liefert und die Oberfläche (noch) nicht liest. Kein Fehler, aber sichtbar: Kandidaten für das
    # Aufräumen der Abfragen. Ein Eintrag, der nicht mehr stimmt, lässt den Test scheitern.
    UNGELESEN = {"max_gen", "kampfform", "formname", "effekt", "abgedeckt", "ev_summe"}
    # Wege des Servers ohne Aufruf in der Oberfläche, mit Grund
    OHNE_AUFRUFER = {"/healthz": "Lebenszeichen für Docker (HEALTHCHECK) und den Menschen"}

    def js(self):
        return oberflaeche_js()

    def test_form_der_antworten(self):
        soll, ist = vertrag.lesen(), vertrag.messen(self)
        self.assertEqual(list(soll), list(ist), "Aufrufe in tests/vertrag.py und tests/vertrag.json gehen auseinander")
        anders = [f"{name} ({ist[name]['aufruf']}){z}" for name in soll for z in vertrag.unterschiede(soll[name]["form"], ist[name]["form"])]
        self.assertEqual(anders, [], "Antworten haben eine andere Form als vereinbart. Mit Absicht? Dann: python3 -m tests.vertrag")
        self.assertEqual({n: v["aufruf"] for n, v in soll.items()}, {n: v["aufruf"] for n, v in ist.items()})
        self.ohne_fehler()

    def test_oberflaeche_kennt_die_felder(self):
        js = self.js()
        kennt = lambda feld: re.search(r"(?<![A-Za-z0-9_])" + re.escape(feld) + r"(?![A-Za-z0-9_])", js) is not None
        alle = {f for v in vertrag.lesen().values() for f in vertrag.felder(v["form"])}
        self.assertGreater(len(alle), 250)
        self.assertEqual({f for f in alle if not kennt(f)}, self.UNGELESEN)

    def test_wege(self):
        """Jeder Weg, den die Oberfläche ruft, wird vom Server beantwortet, und jeder Weg des Servers hat einen Aufrufer."""
        with open(os.path.join(minidb.HIER, "..", "app", "server.py"), encoding="utf-8") as f:
            src = f.read()
        get = set(re.findall(r'path == "(/[^"]+)"', src))
        muster = [m for m in re.findall(r're\.fullmatch\(r"(/api/[^"]+)", path\)', src)]
        post = set(server.Handler.POST)
        ruft = set(re.findall(r'["`](/api/[A-Za-z/]+)', self.js()))
        self.assertGreater(len(ruft), 50)
        offen = []
        for weg in sorted(ruft):
            if weg in get or weg in post:
                continue
            if weg.endswith("/") and any(m.startswith(weg) for m in muster):       # zusammengesetzt: `/api/pokemon/${id}`
                continue
            offen.append(weg)
        self.assertEqual(offen, [], "Die Oberfläche ruft Wege, die der Server nicht kennt")
        ohne = {w for w in get | post if w not in ruft}
        ohne |= {m for m in muster if not any(m.startswith(w) for w in ruft if w.endswith("/"))}
        self.assertEqual(ohne, set(self.OHNE_AUFRUFER))
        # jeder Aufruf des Vertrags ist ein Weg, den die Oberfläche wirklich ruft
        for name, (weg, rumpf) in vertrag.AUFRUFE.items():
            pfad = weg.split("?")[0]
            self.assertTrue(pfad in ruft or any(pfad.startswith(w) for w in ruft if w.endswith("/")), name)
            self.assertTrue(pfad in post if rumpf is not None else pfad in get or any(re.fullmatch(m, pfad) for m in muster), name)


def browser():
    """Pfad eines Chromium oder Chrome für den Selbsttest: POKEDEX_BROWSER, sonst was im Pfad liegt; sonst None."""
    env = os.environ.get("POKEDEX_BROWSER")
    if env:
        return env if os.path.isfile(env) else shutil.which(env)
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    return None


class _SelbsttestHandler(server.Handler):
    """Der Server des Tests liefert zusätzlich die Seite des Selbsttests und seinen Plan aus und nimmt das Ergebnis an."""
    plan, ergebnis, fertig = {}, {}, threading.Event()

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/selbsttest":
            with open(os.path.join(minidb.HIER, "ui_selbsttest.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/selbsttest/plan":
            self._send(200, type(self).plan)
        else:
            super().do_GET()

    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path == "/selbsttest/ergebnis":
            type(self).ergebnis.update(self._body(2_000_000))
            self._send(200, {"ok": True})
            type(self).fertig.set()
        else:
            super().do_POST()

    def log_message(self, *a):
        pass


class Selbsttest(HttpMitDaten):
    """0.59.0: Selbsttest der Oberfläche im Browser (tests/ui_selbsttest.html), nach dem Muster der Geschwister. Chromium
    ohne Fenster lädt die echte Oberfläche gegen den Server mit der Mini-Datenbank, bei 1366 × 768 Bildpunkten, und geht alle
    Reiter für mehrere Spiele durch. Ohne Browser wird der Test übersprungen; mit POKEDEX_SELBSTTEST=muss (so in der CI)
    scheitert er dann, damit er nicht still ausfällt."""
    HANDLER = _SelbsttestHandler
    BREITE, HOEHE = 1366, 768
    GRENZE = 15000              # so viele Millisekunden darf eine Ansicht höchstens laden
    SPIELE = ("red-blue", "emerald", "x-y", "legends-arceus", "scarlet-violet")

    def plan(self):
        schritte = []
        for spiel in self.SPIELE:
            liste = erwartete_liste(spiel)
            name = lambda pid: next(f[5] for f in minidb.FORMEN if f[0] == pid) if pid not in minidb.ART else minidb.ART[pid][2]
            lernspiel = lernspiel_von(spiel)
            add = lambda ansicht, sieht=(), **k: schritte.append({"spiel": spiel, "ansicht": ansicht, "sieht": list(sieht), **k})
            add("#pokemon", [name(pid) for pid, _, _ in liste], sieht_nicht=["Noch keine Spieldaten"])
            for pid in (liste[0][0], liste[-1][0]):
                attacken = [minidb.ATTACKE[m][2] for m, _, _ in minidb.lernt(pid, lernspiel) if minidb.ATTACKE[m][5] != minidb.STATUS]
                add(f"#pokemon/{pid}", [name(pid)] + attacken[:3])
            add("#team", ["Team"])
            add("#attacken", ["Rempler"], sieht_nicht=["Feenglanz"] if minidb.SPIEL_GEN[minidb.SPIEL[spiel]] < 6 else [])
            add("#typen", ["Pflanze", "Wasser"], sieht_nicht=["Fee"] if minidb.SPIEL_GEN[minidb.SPIEL[spiel]] < 6 else [])
            add("#items", ["Pokéball"])
            add("#vergleich", [])
            add("#initiative", [])
            add("#fehlt", [name(liste[0][0])])
            add("#karte/gebiete", [g[3] for g in minidb.ORTE if spiel == "emerald" and g[1] == 3])
            # die Mini-Datenbank hat keine Spawnpunkte für Legenden: Arceus: die Ansicht sagt es, statt einen Fehler zu zeigen
            add("#karte", ["noch keine Kartendaten"] if spiel == "legends-arceus" else [])
            add("#sammeln", [])
            if spiel == "emerald":
                add("#home", ["HOME-Boxen", "Box 1", "Plätzen belegt"])
            if spiel == "legends-arceus":
                add("#auftraege", [])
            if spiel == "scarlet-violet":
                add("#raids", [])
            add("#einstellungen", ["Abgleich", sources.VERSION])
        # 0.60.0: Reiter nach dem Spielprofil: Kampf statt Karte im Kampfspiel, Aufträge und Raids in der Erweiterung über das
        # Hauptspiel, Aufträge in Mega-Dimension unter Legenden: Z-A; wo das Profil sie nicht nennt, führt der Reiter zur Karte
        for spiel, ansicht, sieht, wechselt in (("the-teal-mask", "#auftraege", ["Blaubeer"], False),
                                                ("the-teal-mask", "#raids", [], False),
                                                ("mega-dimension", "#auftraege", [], False),
                                                ("champions", "#kampf", ["Schadensrechner"], False),
                                                ("champions", "#karte", ["Schadensrechner"], True),
                                                ("emerald", "#auftraege", [], True),
                                                ("emerald", "#raids", [], True)):
            schritte.append({"spiel": spiel, "ansicht": ansicht, "sieht": sieht, "wechselt": wechselt})
        return {"breite": self.BREITE, "hoehe": self.HOEHE, "grenze": self.GRENZE, "ruhe": 60, "version": sources.VERSION,
                "schritte": schritte}

    def test_oberflaeche_im_browser(self):
        exe = browser()
        if not exe:
            grund = "kein Chromium oder Chrome gefunden (POKEDEX_BROWSER=/pfad setzt einen)"
            if os.environ.get("POKEDEX_SELBSTTEST") == "muss":
                self.fail(grund)
            self.skipTest(grund)
        h = _SelbsttestHandler
        h.plan, h.ergebnis = self.plan(), {}
        h.fertig.clear()
        profil = tempfile.mkdtemp(prefix="pokedex-selbsttest-")
        cmd = [exe, "--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--no-first-run", "--disable-extensions",
               "--disable-background-networking", "--disable-component-update", "--disable-sync", "--mute-audio",
               f"--user-data-dir={profil}", f"--window-size={self.BREITE + 60},{self.HOEHE + 400}",
               f"http://127.0.0.1:{self.port}/selbsttest"]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            fertig = h.fertig.wait(180)
        finally:
            proc.terminate()
            try:
                err = proc.communicate(timeout=10)[1]
            except subprocess.TimeoutExpired:
                proc.kill()
                err = proc.communicate()[1]
            shutil.rmtree(profil, ignore_errors=True)
        self.assertTrue(fertig, "Der Browser hat kein Ergebnis geliefert: " + err.decode("utf-8", "replace")[-600:])
        r = h.ergebnis
        self.assertEqual(r["probleme"], [], f"{len(r['probleme'])} Probleme in {len(r['schritte'])} Schritten")
        self.assertEqual(len(r["schritte"]), len(h.plan["schritte"]))
        self.assertTrue(all(s["ok"] for s in r["schritte"]))
        # Der Inhalt folgt den Kopfzeilen sofort: Bis 0.58.1 kam er bei fast jeder zweiten Antwort rund 40 ms später (Nagle)
        self.assertGreater(len(r["rumpf"]), 100)
        spaet = [ms for ms in r["rumpf"] if ms > 30]
        self.assertLess(len(spaet), len(r["rumpf"]) / 10, f"Inhalt später als 30 ms nach den Kopfzeilen: {len(spaet)} von {len(r['rumpf'])}")
        self.ohne_fehler()
        type(self).letztes = r          # für den Nachweis: Dauer je Schritt
