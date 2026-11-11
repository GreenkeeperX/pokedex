"""Tests ohne Netz: Rechenlogik, Leser, Abgleich mit Attrappe, Server-Hilfen. Start: python -m unittest discover -s tests"""
import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import abruf, attacken, aufgaben, db, importer, server, showdown, sources, store, team, typen
from app.typen import BODEN, DRACHE, EIS, ELEKTRO, FEE, FEUER, FLUG, GEIST, KAMPF, NORMAL, PFLANZE, STAHL, UNLICHT, WASSER

# Kleine Typtabelle: alle 18 Typen, dazu die Werte, die die Tests brauchen
EFF = [(a, d, 100) for a in range(1, 19) for d in range(1, 19)]
SPECIAL = {(FEUER, PFLANZE): 200, (WASSER, FEUER): 200, (FEUER, WASSER): 50, (PFLANZE, WASSER): 200, (ELEKTRO, WASSER): 200,
           (BODEN, ELEKTRO): 200, (ELEKTRO, BODEN): 0, (EIS, DRACHE): 200, (EIS, FLUG): 200, (EIS, BODEN): 200, (NORMAL, GEIST): 0,
           (GEIST, NORMAL): 0, (KAMPF, GEIST): 0, (GEIST, STAHL): 100, (UNLICHT, STAHL): 100, (DRACHE, FEE): 0, (BODEN, FLUG): 0}
EFF = [(a, d, SPECIAL.get((a, d), f)) for a, d, f in EFF]
PAST = [(GEIST, STAHL, 50, 5), (UNLICHT, STAHL, 50, 5)]
TYPE_GEN = {t: 1 for t in range(1, 19)} | {STAHL: 2, UNLICHT: 2, FEE: 6}


def ch(gen=9):
    return typen.chart(EFF, PAST, TYPE_GEN, gen)


class Typen(unittest.TestCase):
    def test_generationen(self):
        self.assertNotIn(FEE, ch(5))
        self.assertNotIn(STAHL, ch(1))
        self.assertEqual(ch(5)[GEIST][STAHL], 0.5)      # bis Gen 5 resistiert Stahl gegen Geist
        self.assertEqual(ch(6)[GEIST][STAHL], 1.0)

    def test_doppeltyp_und_faehigkeit(self):
        d = typen.defense([DRACHE, FLUG], ch())
        self.assertEqual(d[EIS], 4.0)
        self.assertEqual(d[BODEN], 0.0)
        self.assertEqual(typen.defense([ELEKTRO], ch(), "levitate")[BODEN], 0.0)
        self.assertEqual(typen.defense([WASSER], ch(), "dry-skin")[FEUER], 0.625)

    def test_wirkung(self):
        self.assertEqual(typen.attack(EIS, [DRACHE, FLUG], ch()), 4.0)
        self.assertEqual(typen.super_effective(ELEKTRO, ch()), {WASSER})
        self.assertEqual(typen.label(0.25), "¼")


class Attacken(unittest.TestCase):
    MON = {"typen": [FEUER], "ang": 60, "spang": 120}

    def test_wertung(self):
        s, why = attacken.score({"staerke": 90, "genauigkeit": 100, "klasse": attacken.SPEZ, "typ": FEUER}, self.MON)
        self.assertEqual(s, 135.0)
        self.assertIn("Eigentyp-Bonus", why)
        s, why = attacken.score({"staerke": 90, "genauigkeit": 100, "klasse": attacken.PHYS, "typ": FEUER}, self.MON)
        self.assertEqual(s, 67.5)                        # nutzt den halb so hohen Angriff
        s, _ = attacken.score({"staerke": 150, "genauigkeit": 90, "klasse": attacken.SPEZ, "typ": NORMAL, "merkmale": ["recharge"]}, self.MON)
        self.assertEqual(s, 81.0)
        self.assertEqual(attacken.score({"staerke": None, "klasse": attacken.STATUS}, self.MON)[0], 0)
        s, why = attacken.score({"staerke": 250, "genauigkeit": 100, "klasse": attacken.SPEZ, "typ": NORMAL, "kennung": "explosion"}, self.MON)
        self.assertEqual(s, 75.0)
        self.assertIn("Anwender wird danach kampfunfähig", why)

    def test_anpassung_und_mehrfach(self):
        s, _ = attacken.score({"staerke": 25, "genauigkeit": 100, "klasse": attacken.SPEZ, "typ": FEUER, "mehrfach": [2, 5]},
                              dict(self.MON, faehigkeit="adaptability"))
        self.assertAlmostEqual(s, 25 * 3.1 * 2, places=1)

    def test_werte_im_spiel(self):
        move = {"typ": FEE, "staerke": 95, "ap": 15, "genauigkeit": 100, "prio": 0}
        # Eintrag: bis Spiel Nr. 10 (vor der Änderung) war die Attacke Normal mit 80 Stärke
        changes = [(10, NORMAL, 80, None, None, None)]
        self.assertEqual(attacken.in_game(move, changes, 5)["typ"], NORMAL)
        self.assertEqual(attacken.in_game(move, changes, 5)["staerke"], 80)
        self.assertEqual(attacken.in_game(move, changes, 12)["staerke"], 95)

    def test_moveset_mit_abdeckung(self):
        ranked = [(100, {"typ": FEUER, "n": 1}), (95, {"typ": FEUER, "n": 2}), (80, {"typ": ELEKTRO, "n": 3}), (70, {"typ": EIS, "n": 4})]
        got = [m["n"] for m, _ in attacken.moveset(ranked, {}, ch())]
        self.assertEqual(got[:3], [1, 4, 3])             # die zweite Feuer-Attacke rutscht nach hinten


def mon(i, name, types, werte=(80, 100, 80, 60, 80, 95), art=None):
    return {"id": i, "art": art or i, "name": name, "typen": types, "werte": list(werte), "summe": sum(werte)}


class Team(unittest.TestCase):
    def test_offene_schwaeche(self):
        ctx = team.Ctx(ch())
        ev = team.evaluate([mon(1, "A", [PFLANZE]), mon(2, "B", [PFLANZE])], ctx)
        self.assertIn(FEUER, ev["offen"])
        ev2 = team.evaluate([mon(1, "A", [PFLANZE]), mon(3, "C", [WASSER])], ctx)
        self.assertNotIn(FEUER, ev2["offen"])

    def test_vorschlag_und_suche(self):
        ctx = team.Ctx(ch())
        pool = [mon(i, f"P{i}", [t]) for i, t in enumerate(range(1, 19), start=1)]
        rows = team.suggest([pool[PFLANZE - 1]], pool, ctx, n=3)
        self.assertEqual(len(rows), 3)
        self.assertNotIn(PFLANZE, [r["id"] for r in rows])
        best = team.optimize(pool, ctx, fixed=[pool[0]], beam=5)
        self.assertTrue(best and len(best[0][1]) == 6)
        self.assertEqual(best[0][1][0]["id"], 1)
        self.assertEqual(len({m["art"] for m in best[0][1]}), 6)

    def test_gegner(self):
        ctx = team.Ctx(ch())
        rows = team.matchup([mon(1, "W", [WASSER]), mon(2, "P", [PFLANZE])], {"typen": [FEUER], "init": 200}, ctx)
        self.assertEqual(rows[0]["name"] if "name" in rows[0] else rows[0]["id"], 1)
        self.assertEqual(rows[0]["urteil"], "schicken")
        self.assertEqual(rows[1]["urteil"], "schonen")


class Version(unittest.TestCase):
    def test_neuigkeiten(self):
        from app import sources
        self.assertEqual(sources.NEUIGKEITEN[0][0], sources.VERSION)
        for v, datum, punkte in sources.NEUIGKEITEN:
            self.assertRegex(v, r"^\d+\.\d+\.\d+$")
            self.assertRegex(datum, r"^\d\d\.\d\d\.\d{4}$")
            self.assertTrue(punkte)


class TeamPlaetze(unittest.TestCase):
    def test_details_je_platz(self):
        from app import abfragen
        self.assertEqual(abfragen.slot_details({"25": {"level": 9}}, [25, 25, 6]), [{"level": 9}, {"level": 9}, {}])
        self.assertEqual(abfragen.slot_details([{"level": 9}], [25, 6]), [{"level": 9}, {}])
        self.assertEqual(abfragen.slot_details(None, [1]), [{}])

    def test_showdown_text(self):
        from app import paste
        txt = ("Flitzer (Garchomp) (F) @ Choice Scarf\r\nAbility: Rough Skin\nLevel: 50\nShiny: Yes\nTera Type: Fire\n"
               "EVs: 252 Atk / 4 SpD / 252 Spe\nJolly Nature\nIVs: 0 SpA\n- Earthquake\n- Outrage\n\n\n"
               "=== [gen9] Team ===\n\nPikachu\n- Thunderbolt\n- Quick Attack\n- Iron Tail\n- Volt Tackle\n- Surf\n")
        a, b = paste.parse(txt)
        self.assertEqual((a["spitzname"], a["name"], a["geschlecht"], a["item"]), ("Flitzer", "Garchomp", "F", "Choice Scarf"))
        self.assertEqual((a["faehigkeit"], a["level"], a["schillernd"], a["tera"], a["wesen"]), ("Rough Skin", 50, True, "Fire", "Jolly"))
        self.assertEqual(a["evs"], [0, 252, 0, 0, 4, 252])
        self.assertEqual(a["ivs"], [31, 31, 31, 0, 31, 31])
        self.assertEqual(len(b["attacken"]), 4)                  # höchstens vier Attacken
        self.assertEqual(paste.parse(paste.dump([a, b])), [a, b])  # Hin und zurück ohne Verlust
        self.assertEqual(paste.parse("Mr. Mime (M)\n- Psychic")[0]["name"], "Mr. Mime")
        self.assertEqual(paste.parse(""), [])

    def test_doppelkampf(self):
        from app import doppel
        ch = {"boden": {"feuer": 2.0, "flug": 0.0}}
        mv = lambda k, n, typ="normal", ziel=10, schaden=True: {"kennung": k, "name": n, "typ": typ, "ziel": ziel, "schaden": schaden}
        ms = [{"name": "A", "typen": ["drache"], "init": 102, "faehigkeit": None,
               "attacken": [mv("earthquake", "Erdbeben", "boden", 9), mv("protect", "Schutzschild", schaden=False)], "lernbar": {}},
              {"name": "B", "typen": ["feuer"], "init": 60, "faehigkeit": "intimidate", "faehigkeit_name": "Bedroher",
               "attacken": [mv("fake-out", "Mogelhieb")], "lernbar": {"helping-hand": "Rechte Hand"}},
              {"name": "C", "typen": ["wasser"], "init": 86, "faehigkeit": "levitate", "attacken": [], "lernbar": {}},
              {"name": "D", "typen": ["flug"], "init": 30, "faehigkeit": None, "attacken": [], "lernbar": {}}]
        r = doppel.evaluate(ms, ch, {"boden": "ground"})
        roles = {x["key"]: x for x in r["rollen"]}
        self.assertEqual(roles["schutz"]["wer"], [["A", "Schutzschild"]])
        self.assertEqual(roles["stoerer"]["wer"], [["B", "Mogelhieb, Bedroher"]])
        self.assertEqual(roles["hilfe"]["kann"], [["B", "Rechte Hand"]])
        self.assertEqual(r["flaeche"], [["A", "Erdbeben", True]])
        p = r["partner"][0]
        self.assertEqual(p["trifft"], [["B", 2.0]])
        self.assertEqual(sorted(n for n, _ in p["immun"]), ["C", "D"])       # Schwebe und Flug
        self.assertEqual(r["tempo"]["langsam"], ["B", "D"])
        self.assertTrue(0 < r["wertung"] <= 100)

    def test_team_details_extras(self):
        d = server._details([{"level": 50, "attacken": [1], "item": 264, "wesen": 16, "evs": [0, 252, 0, 0, 4, 252],
                              "ivs": [31] * 5, "geschlecht": "X", "spitzname": "  A   B ", "schillernd": "ja", "fremd": 1}], [445])
        self.assertEqual(d, [{"level": 50, "attacken": [1], "item": 264, "wesen": 16, "evs": [0, 252, 0, 0, 4, 252], "spitzname": "A B"}])

    def test_stark_gegen(self):
        from app import abfragen
        ch = {10: {12: 2, 11: 0.5}, 11: {10: 2, 12: 0.5}, 12: {11: 2, 10: 0.5}}     # Feuer, Wasser, Pflanze
        self.assertTrue(abfragen.strong_against([10], 12, ch))      # Feuer gegen Pflanze
        self.assertFalse(abfragen.strong_against([10], 11, ch))     # Feuer gegen Wasser
        self.assertFalse(abfragen.strong_against([12], 12, ch))

    def test_duell_doppeltyp(self):
        from app import abfragen
        # Wasser (11) / Gift (4) gegen Feuer (10) und Pflanze (12)
        ch = {10: {12: 2, 11: 0.5, 4: 1}, 11: {10: 2, 12: 0.5, 4: 1}, 12: {11: 2, 10: 0.5, 4: 0.5}, 4: {12: 2, 4: 0.5}}
        self.assertEqual(abfragen.duel([11, 4], 10, ch), (2, 0.5, 2))      # klar stark
        self.assertEqual(abfragen.duel([11, 4], 12, ch), (2, 1.0, 1))      # stark: Pflanze trifft ×2 · ×½
        self.assertTrue(abfragen.strong_against([11, 4], 12, ch))
        self.assertFalse(abfragen.strong_against([11, 4], 12, ch, clear=True))
        self.assertEqual(abfragen.duel([12], 10, ch)[2], -1)               # Pflanze gegen Feuer: schwer


class Leser(unittest.TestCase):
    def test_pkhex_begegnungen(self):
        import struct
        # ein Gebiet: Ort 4, Art 0, zwei Plätze (Bidiza Lv 2–4, Alpha-Bidiza Lv 17–19)
        area = bytes([1, 4, 0, 2]) + struct.pack("<HBBBBBB", 399, 0, 0, 2, 4, 0, 0) + struct.pack("<HBBBBBB", 399, 0, 1, 17, 19, 0, 3)
        data = b"la" + struct.pack("<H", 1) + struct.pack("<II", 12, 12 + len(area)) + area
        self.assertEqual(abruf.pkhex_areas(data), [([4], 0, [(399, 0, 2, 4, 0), (399, 0, 17, 19, 1)])])

    def test_pkhex_begegnungen_sv_za(self):
        import sqlite3
        import struct
        # Karmesin/Purpur: Ort 5 mit Pamo Lv 2–8; Ort 6 mit Herkunft 5 (Doppel aus dem Nachbargebiet) fällt weg
        own = bytes([5, 0, 0, 0]) + struct.pack("<HBBBBBB", 921, 0, 0, 2, 8, 0xF, 0xF)
        cross = bytes([6, 0, 5, 0]) + struct.pack("<HBBBBBB", 921, 0, 0, 2, 8, 0xF, 0xF)
        sv = b"sv" + struct.pack("<H", 2) + struct.pack("<III", 16, 16 + len(own), 16 + len(own) + len(cross)) + own + cross
        self.assertEqual(importer.pkhex_areas(sv), [([5], 0, [(921, 0, 2, 8, 0)])])
        # Legenden: Z-A (BinLinker16): Ort 300 mit Flabébé Lv 5–8 und Alpha Lv 15–16
        area = struct.pack("<HH", 300, 0) + struct.pack("<HBBBBBB", 669, 0, 0, 5, 8, 0, 0) + struct.pack("<HBBBBBB", 669, 0, 0, 15, 16, 1, 0)
        za = b"za" + struct.pack("<H", 1) + struct.pack("<HH", 8, 8 + len(area)) + area
        self.assertEqual(importer.pkhex_areas(za), [([300], 0, [(669, 0, 5, 8, 0), (669, 0, 15, 16, 2)])])
        self.assertEqual(importer.pkhex_areas(b""), [])
        # Erweiterungen bekommen die Fundorte des Hauptspiels; Orte ab 30000 aus der zweiten Namensliste
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE pokemon (id INTEGER, species_id INTEGER, is_default INTEGER)")
        con.executemany("INSERT INTO pokemon VALUES (?, ?, 1)", [(921, 921), (669, 669)])
        orte = "\n".join(["Ort"] * 5 + ["Zone A"])
        n = importer._derive_fundort(con, {"scarlet-violet": {"begegnungen": sv, "orte": orte,
                                                              "fest": "new(SV) { Species = 0921, Level = 05, Location = 30002 },"},
                                           "legends-za": {"begegnungen": za, "orte": "", "orte3": "\n\nStadt B",
                                                          "fest": "new(0669,0,05,128) { Location = 30002 },"}})
        self.assertEqual(n, 2 * 3 + 3 * 2)
        rows = con.execute("SELECT spiel, gebiet, art FROM fundort WHERE form = 921 ORDER BY spiel, art").fetchall()
        self.assertEqual(rows, [("scarlet-violet", "Zone A", 0), ("scarlet-violet", "Ort 30002", importer.FEST),
                                ("the-indigo-disk", "Zone A", 0), ("the-indigo-disk", "Ort 30002", importer.FEST),
                                ("the-teal-mask", "Zone A", 0), ("the-teal-mask", "Ort 30002", importer.FEST)])
        self.assertEqual(con.execute("SELECT DISTINCT gebiet, spiel FROM fundort WHERE form = 669 ORDER BY spiel, art").fetchall(),
                         [("Ort 300", "legends-za"), ("Stadt B", "legends-za"), ("Ort 300", "mega-dimension"), ("Stadt B", "mega-dimension")])
        con.close()

    def test_pkhex_feste_begegnungen(self):
        src = """
        new(722,000,05,M,M) { Location = 006, FixedBall = Ball.LAPoke }, // erfunden
        new(SV) { Species = 0978, Level = 45, Location = 040, Form = 2, IVs = new(30,30,30,30,30,30) },
        new(SV) { Species = 0001, Level = 5 },
        """
        self.assertEqual(importer.pkhex_static(src), [(722, 0, 5, 6), (978, 2, 45, 40)])

    def test_spawnpunkte(self):
        import sqlite3
        from app import abfragen
        cells = importer.spawn_cells({"Any Time/All Weather": {"Bidoof": 3, "AlphaBidoof": 1, " None": 5}})
        self.assertEqual(len(cells), 36)
        self.assertEqual(cells[("Night", "Rain")], {"Bidoof": 75.0, "AlphaBidoof": 25.0})
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE pokemon (id INTEGER, species_id INTEGER, is_default INTEGER)")
        con.executemany("INSERT INTO pokemon VALUES (?, ?, 1)", [(399, 399), (58, 58), (10229, 58)])
        con.execute("CREATE TABLE pokemon_forms (pokemon_id INTEGER, form_order INTEGER)")
        con.executemany("INSERT INTO pokemon_forms VALUES (?, ?)", [(399, 1), (58, 1), (10229, 2)])
        con.execute("CREATE TABLE pokemon_species (id INTEGER, identifier TEXT)")
        con.executemany("INSERT INTO pokemon_species VALUES (?, ?)", [(399, "bidoof"), (58, "growlithe")])
        punkte = json.dumps({"0": {"coords": [100.0, 5.0, 200.0], "icon": "x/alpha.png", "name": "a"},
                             "1": {"coords": [300.0, 5.0, 400.0], "icon": "x/pokeball.png", "name": "b"}})
        plaetze = json.dumps({"a": {"Night/All Weather": {"Growlithe-1": 1}},
                              "b": {"Any Time/All Weather": {"Bidoof": 1, "AlphaBidoof": 0}}})
        n = importer._derive_spawn(con, {"legends-arceus": {"karte": {"gebiet": "Gebiet A", "punkte": punkte, "plaetze": plaetze}}})
        self.assertEqual(n, 2)
        self.assertEqual(len(abruf.map_tiles()), 5 * (4 + 16 + 64))
        self.assertEqual(con.execute("SELECT COUNT(*) FROM spawnpunkt WHERE alpha = 1").fetchone()[0], 1)
        s = abfragen.spawn_summary(con, "legends-arceus", 10229)["Gebiet A"]
        self.assertEqual((s["zeit"], s["wetter"], s["punkte"], s["karte"]), ("Nacht 100 %", "jedes", 1, "karte"))
        self.assertEqual(abfragen.spawn_summary(con, "legends-arceus", 399)["Gebiet A"]["zeit"], "immer")
        self.assertEqual(abfragen._cond_text({"Dawn": 20, "Day": 20, "Dusk": 20, "Night": 80}, importer.ZEITEN, abfragen.ZEIT_DE, "immer"),
                         "Nacht 80 %, sonst 20 %")

    def test_pkhex_fundorte(self):
        import sqlite3
        import struct
        from app import abfragen
        # Gebiet 7 mit Stellen 8 und 9: Bidiza Lv 2–4 (Alpha 17–19), Fukano Form 1 (Hisui) Lv 5–6
        slots = [(399, 0, 0, 2, 4), (399, 0, 1, 17, 19), (58, 1, 0, 5, 6)]
        area = bytes([3, 7, 8, 9, 0, len(slots)]) + b"".join(struct.pack("<HBBBBBB", s, f, a, lo, hi, 0, 0) for s, f, a, lo, hi in slots)
        data = b"la" + struct.pack("<H", 1) + struct.pack("<II", 12, 12 + len(area)) + area
        orte = "\n".join(["", "", "", "", "", "", "", "Gebiet A", "Stelle B", "Stelle C"])
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE pokemon (id INTEGER, species_id INTEGER, is_default INTEGER)")
        con.executemany("INSERT INTO pokemon VALUES (?, ?, 1)", [(399, 399), (58, 58), (10229, 58)])
        con.execute("CREATE TABLE pokemon_forms (pokemon_id INTEGER, form_order INTEGER)")
        con.executemany("INSERT INTO pokemon_forms VALUES (?, ?)", [(399, 1), (58, 1), (10229, 2)])
        self.assertEqual(importer._derive_fundort(con, {"legends-arceus": {"begegnungen": data, "orte": orte}}), 3)
        self.assertEqual([r[0] for r in con.execute("SELECT DISTINCT form FROM fundort ORDER BY form")], [399, 10229])
        g = {"kennung": "legends-arceus"}
        e = abfragen._enc_pkhex(con, g, 399)
        self.assertEqual(len(e), 1)
        self.assertEqual((e[0]["ort"], e[0]["methode"], e[0]["level"], e[0]["alpha"]), ("Gebiet A", "frei", "2–4", "17–19"))
        self.assertEqual([x["name"] for x in e[0]["stellen"]], ["Stelle B", "Stelle C"])
        self.assertEqual(abfragen._enc_pkhex(con, g, 25), [])                 # Spiel mit Daten, Pokémon ohne Fundort
        self.assertIsNone(abfragen._enc_pkhex(con, {"kennung": "x"}, 399))    # Spiel ohne Daten: PokéAPI

    def test_fangchance(self):
        from app import abfragen
        self.assertLess(abfragen.catch_chance(255, gen=9), 100.0)             # volle KP: a = 85, kein sicherer Fang
        self.assertEqual(abfragen.catch_chance(255, hp_share=0, gen=9), 100.0)  # 1 KP: a = 255
        self.assertEqual(abfragen.catch_chance(3, gen=4), round(100 * 1 / 255, 1))
        low = abfragen.catch_chance(3, gen=9)
        self.assertTrue(1 < low < 2)                                          # Rüttelproben: gut 1,5 %, nicht 0,4 %
        self.assertGreater(abfragen.catch_chance(45, 2, gen=9), abfragen.catch_chance(45, 1, gen=9))
        self.assertGreater(abfragen.catch_chance(45, gen=5), abfragen.catch_chance(45, gen=6))   # drei statt vier Proben
        t = abfragen.catch_table(45, 9)
        self.assertEqual([x["ball"] for x in t], ["Pokéball", "Superball", "Hyperball"])
        self.assertTrue(all(x["voll"] <= x["rot"] <= x["status"] <= x["schlaf"] for x in t))
        self.assertEqual((abfragen.sleep_factor(4), abfragen.sleep_factor(5)), (2, 2.5))

    def test_tm_und_extras(self):
        from app import abfragen
        self.assertEqual(abfragen.machine_label("tm12"), "TM12")
        self.assertEqual(abfragen.machine_label("tm68", 3), "TM068")
        self.assertEqual(abfragen.machine_label("hm03"), "VM03")
        self.assertEqual(abfragen.machine_label("tr05"), "TP05")
        self.assertEqual(abfragen.machine_label("potion"), "")
        self.assertEqual(abruf.file_kind(b"\x89PNG\r\n\x1a\nxx"), ".png")
        self.assertEqual(abruf.file_kind(b"GIF89a"), ".gif")
        self.assertEqual(abruf.file_kind(b"\xff\xfb\x90"), ".mp3")     # die Rufe der PokéAPI heißen .ogg, sind aber MP3
        self.assertEqual(abruf.file_kind(b"OggS\x00"), ".ogg")
        self.assertIsNone(abruf.file_kind(b"<html>"))

    def test_items(self):
        import sqlite3
        con = sqlite3.connect(":memory:")
        csvs = {
            "items": "id,identifier,category_id,cost,fling_power,fling_effect_id\n1,master-ball,34,0,,\n4,poke-ball,34,200,,\n"
                     "2220,lapoke-ball,34,0,,\n9,old-thing,23,0,,\n",
            "item_names": "item_id,local_language_id,name\n1,6,Meisterball\n4,6,Pokéball\n4,9,Poké Ball\n2220,6,Pokéball\n9,9,Old\n",
            "item_categories": "id,pocket_id,identifier\n34,3,standard-balls\n23,8,unused\n",
            "item_flavor_text": "item_id,version_group_id,language_id,flavor_text\n1,1,9,The best\n1,2,6,Der beste\n1,3,9,Best ever\n",
            "item_prose": "item_id,local_language_id,short_effect,effect\n4,9,Catches.,Catches a lot.\n",
            "item_game_indices": "item_id,generation_id,game_index\n1,1,1\n1,9,1\n4,1,4\n2220,8,1\n",
            "version_groups": "id,identifier,generation_id,order\n1,a,1,1\n2,b,1,2\n3,c,2,3\n",
        }
        for n, t in csvs.items():
            importer.import_csv(con, n, t)
        con.execute("CREATE TABLE spiel (id INTEGER, kennung TEXT, name TEXT, gen INTEGER, reihenfolge INTEGER)")
        con.executemany("INSERT INTO spiel VALUES (?, ?, ?, ?, ?)", [(1, "a", "A", 1, 1), (2, "b", "B", 1, 2), (3, "c", "C", 2, 3)])
        self.assertEqual(importer._derive_item(con), 3)                       # ohne das ungenutzte Item
        rows = {r[0]: r for r in con.execute("SELECT kennung, name, tasche, text, sprache, gens, spiele FROM item")}
        self.assertEqual(rows["master-ball"][1:5], ("Meisterball", "Bälle", "Der beste", "de"))   # Deutsch vor neuerem Englisch
        self.assertEqual(json.loads(rows["master-ball"][6]), [1, 2, 3])
        self.assertEqual(rows["poke-ball"][3:5], ("Catches.", "en"))
        self.assertEqual(rows["lapoke-ball"][1], "Pokéball (Hisui)")

    def test_pokewiki(self):
        from app import pokewiki
        wt_move = ("{{Infobox Attacke\n|Typ=Normal\n|Stärke=40 (ab Gen. 7)\n|Bildunterschrift=[[Krokel]] setzt [[Tackle|es]] ein.\n"
                   "|PLStärke=40\n|PLStärkeKraft=50\n|PLStärkeTempo=30\n|PLGenauigkeit=100&nbsp;%\n|PLAP=30\n}}\nText")
        wt_mon = ("{{Getragene Items\n|Spiele1={{sk|PLA}}\n|Item1={{item|Sinelbeere|sp=PLA}}<br />{{item|Meistersamen|sp=PLA}}"
                  "{{Anmerkung|Nur Elite-Pokémon}}\n|Prozent1=35&nbsp;%<br />10&nbsp;%{{Anmerkung|Nur Elite-Pokémon}}\n"
                  "|Spiele2={{sk|SW|SH}}\n|Item2={{item|Tsitrubeere}}\n|Prozent2=5&nbsp;%\n}}")
        answer = json.dumps({"batchcomplete": True, "query": {
            "normalized": [{"from": "tackle", "to": "Tackle"}], "redirects": [{"from": "Bidiza (Pokémon)", "to": "Bidiza"}],
            "pages": [{"title": "Tackle", "revisions": [{"slots": {"main": {"content": wt_move}}}]},
                      {"title": "Bidiza", "revisions": [{"slots": {"main": {"content": wt_mon}}}]},
                      {"title": "Fehlt", "missing": True}]}})
        got = pokewiki.pages(answer)
        self.assertEqual(sorted(got), ["Bidiza (Pokémon)", "tackle"])
        self.assertEqual(pokewiki.la_move(got["tackle"]), {"staerke": 40, "kraft": 50, "tempo": 30, "genauigkeit": 100, "ap": 30})
        self.assertIsNone(pokewiki.la_move("{{Infobox Attacke\n|Stärke=40\n}}"))
        self.assertEqual(pokewiki.held_items(got["Bidiza (Pokémon)"]), [
            {"spiel": "legends-arceus", "item": "Sinelbeere", "prozent": "35 %", "elite": False},
            {"spiel": "legends-arceus", "item": "Meistersamen", "prozent": "10 %", "elite": True}])
        with self.assertRaises(ValueError):
            pokewiki.pages(json.dumps({"error": {"code": "x", "info": "kaputt"}}))
        self.assertIn("titles=Tackle%7CDonnerblitz", pokewiki.batch_url(["Tackle", "Donnerblitz"], True))

    def test_pokewiki_in_der_datenbank(self):
        import sqlite3
        from types import SimpleNamespace
        from app import abfragen
        con = sqlite3.connect(":memory:")
        importer.import_csv(con, "pokemon_species_names", "pokemon_species_id,local_language_id,name\n399,6,Bidiza\n399,9,Bidoof\n")
        con.execute("CREATE TABLE attacke (id INTEGER, name TEXT)")
        con.execute("INSERT INTO attacke VALUES (33, 'Tackle')")
        con.execute("CREATE TABLE item (id INTEGER, name TEXT)")
        con.execute("INSERT INTO item VALUES (155, 'Sinelbeere')")
        wiki = {"attacken": {"legends-arceus": {"Tackle": {"staerke": 40, "kraft": 50, "tempo": 30, "genauigkeit": 100, "ap": 30},
                                                "Gibtsnicht": {"staerke": 1}}},
                "items": {"legends-arceus": {"Bidiza": [{"item": "Sinelbeere", "prozent": "35 %", "elite": False},
                                                        {"item": "Meistersamen", "prozent": "10 %", "elite": True}]}}}
        self.assertEqual(importer._derive_wiki(con, wiki), (1, 2))
        self.assertEqual(con.execute("SELECT item_id, elite FROM getragen ORDER BY item").fetchall(), [(None, 1), (155, 0)])
        D = SimpleNamespace(changes={}, game_moves={("legends-arceus", 33): {"staerke": 40, "kraft": 50, "tempo": 30,
                                                                              "genauigkeit": 100, "ap": 30}})
        m = {"id": 33, "typ": 1, "staerke": 40, "genauigkeit": 100, "ap": 35, "prio": 0}
        v = abfragen.move_view(D, m, {"kennung": "legends-arceus", "reihenfolge": 20})
        self.assertEqual((v["ap"], v["kraft"], v["tempo"], v["geaendert"]), (30, 50, 30, True))
        self.assertNotIn("kraft", abfragen.move_view(D, m, {"kennung": "scarlet-violet", "reihenfolge": 21}))
        con.close()

    def test_pokewiki_karte(self):
        from app import pokewiki
        mons = json.dumps({"Fukano": {"10.5,20.25": {"t": "default", "LvlMin": "3", "LvlMax": "5", "ALvlMin": "18", "ALvlMax": "20",
                                                     "0": [{"d": 12.5, "a": 1}], "1": [{"d": 40, "a": 2}]}},
                           "Hisui-Fukano": {"100,200": {"t": "alpha", "ALvlMin": "30", "ALvlMax": "30"}},
                           "Kaputt": {"x,y": {"t": "crystal"}}, "Liste": []})
        got = pokewiki.map_pokemon(mons)
        self.assertEqual(got, [{"name": "Fukano", "x": 10.5, "z": 20.25, "typ": "default", "lv": (3, 5), "alv": (18, 20), "max": 40},
                               {"name": "Hisui-Fukano", "x": 100.0, "z": 200.0, "typ": "alpha", "lv": None, "alv": (30, 30), "max": None}])
        items = pokewiki.map_items(json.dumps({"Apri-ko-ko": [{"p": "1,2", "c": "30", "u": 1}, {"p": "kaputt"}], "Nichts": "x"}))
        self.assertEqual(items, [{"name": "Apri-ko-ko", "x": 1.0, "z": 2.0, "anteil": "30"}])
        self.assertEqual(pokewiki.item_key("Apri-ko-ko"), pokewiki.item_key("Aprikoko"))
        self.assertTrue(pokewiki.map_url("pokemon", "ha_area01").endswith("/pokemon/ha_area01.json"))

    def test_pokewiki_karte_in_der_datenbank(self):
        import sqlite3
        con = sqlite3.connect(":memory:")
        importer.import_csv(con, "pokemon_species_names", "pokemon_species_id,local_language_id,name\n58,6,Fukano\n41,6,Zubat\n")
        con.execute("CREATE TABLE pokemon (id INTEGER, identifier TEXT, species_id INTEGER, is_default INTEGER)")
        con.executemany("INSERT INTO pokemon VALUES (?, ?, ?, ?)", [(58, "growlithe", 58, 1), (10229, "growlithe-hisui", 58, 0), (41, "zubat", 41, 1)])
        con.execute("CREATE TABLE spawnpunkt (spiel TEXT, karte TEXT, gebiet TEXT, nr INTEGER, name TEXT, x REAL, z REAL, alpha INTEGER)")
        con.executemany("INSERT INTO spawnpunkt VALUES ('legends-arceus', 'obsidianfieldlands', 'Obsidian-Grasland', ?, '', ?, ?, 0)",
                        [(i, 10.0 * i, 20.0 * i) for i in range(6)])
        con.execute("CREATE TABLE kartenobjekt (spiel TEXT, karte TEXT, gebiet TEXT, art TEXT, nr INTEGER, x REAL, z REAL, menge TEXT, items TEXT)")
        con.execute("INSERT INTO kartenobjekt VALUES ('legends-arceus', 'obsidianfieldlands', 'Obsidian-Grasland', 'baum', NULL, 300, 300, '', '[]')")
        con.execute("INSERT INTO kartenobjekt VALUES ('legends-arceus', 'obsidianfieldlands', 'Obsidian-Grasland', 'graben', NULL, 500, 500, '', '[]')")
        con.execute("CREATE TABLE item (id INTEGER, name TEXT)")
        con.execute("INSERT INTO item VALUES (1, 'Aprikoko')")
        mons = {"Zubat": {f"{10 * i},{20 * i}": {"t": "default", "LvlMin": "1", "LvlMax": "2", "0": [{"d": 100}]} for i in range(6)}}
        mons["Hisui-Fukano"] = {"400,400": {"t": "alpha", "ALvlMin": "30", "ALvlMax": "31"}}
        mons["Zubat"]["700,700"] = {"t": "crystal", "LvlMin": "5", "LvlMax": "5", "0": [{"d": 25.5}]}
        dig = {f"Erfunden {k}": [{"p": "505,505", "c": "10"}] for k in range(5)}
        items = {"Apri-ko-ko": [{"p": "300.5,300.5", "c": "50"}, {"p": "800,800", "c": "20"}], **dig}
        wiki = {"karte": {"legends-arceus": {"ha_area01": {"pokemon": json.dumps(mons), "items": json.dumps(items)},
                                             "ha_area09": {"pokemon": json.dumps({"Zubat": {"1,1": {"t": "default"}}}), "items": "{}"}}}}
        self.assertEqual(importer._derive_wiki_karte(con, wiki), 3)
        rows = {r[0]: (r[1], r[2], json.loads(r[3])) for r in con.execute(
            "SELECT art, x, z, items FROM kartenobjekt WHERE art NOT IN ('baum') ORDER BY art")}
        self.assertEqual(rows["alpha"][2], [["Hisui-Fukano", "Alpha, Lv 30–31", 10229]])
        self.assertEqual(rows["kristall"][2], [["Zubat", "Lv 5, 25,5 %", 41]])
        self.assertEqual(rows["boden"], (800.0, 800.0, [["Aprikoko", "20 %"]]))       # die Stelle am Baum fällt weg
        self.assertEqual(len(rows["graben"][2]), 5)                                    # an die Grabstelle von Altissimo gelegt
        con.close()

    def test_companion(self):
        from app import companion
        # erfundene Karte: Companion-Koordinaten = (Spiel − 100) / 0,5 in x, z gespiegelt
        game = [(120.0, 300.0), (400.0, 80.0), (650.0, 520.0), (900.0, 910.0), (210.0, 760.0)]
        to_c = lambda x, z: ((x - 100) / 0.5, (1000 - z) / 0.5)
        es = [{"t": "wisp", "n": "", "x": to_c(*g)[0], "y": to_c(*g)[1]} for g in game]
        es += [{"t": "fast-travel", "n": "Erfundener Hof", "x": to_c(500, 500)[0], "y": to_c(500, 500)[1]},
               {"t": "base-camp", "n": "Lager Eins", "x": to_c(300, 200)[0], "y": to_c(300, 200)[1]},
               {"t": "request", "n": "Auftrag", "x": 0, "y": 0}, {"t": "unown", "n": "A", "x": "kaputt"}]
        text = json.dumps({"entries": es})
        self.assertEqual(len(companion.entries(text)), 7)            # ohne Lage und kaputt fallen weg
        self.assertEqual(companion.art("highland-camp"), "lager")
        ps = companion.places(text, {"irrlicht": game[::-1]})
        self.assertEqual(sorted((p["art"], p["name"], p["x"], p["z"]) for p in ps),
                         [("lager", "Lager Eins", 300.0, 200.0), ("reise", "Erfundener Hof", 500.0, 500.0)])
        self.assertEqual(companion.places(text, {"irrlicht": game[:1]}), [])      # zu wenig gemeinsame Punkte
        self.assertTrue(companion.url("obsidianfieldlands").endswith("/obsidian-fieldlands/data?lang=de"))
        import sqlite3
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE kartenobjekt (spiel TEXT, karte TEXT, gebiet TEXT, art TEXT, nr INTEGER, x REAL, z REAL, menge TEXT, items TEXT)")
        con.executemany("INSERT INTO kartenobjekt VALUES ('legends-arceus', 'obsidianfieldlands', 'Obsidian-Grasland', 'irrlicht', NULL, ?, ?, '', '[]')", game)
        self.assertEqual(importer._derive_companion(con, {"legends-arceus": {"companion": {"obsidianfieldlands": text, "crimsonmirelands": "kaputt"}}}), 2)
        self.assertEqual(json.loads(con.execute("SELECT items FROM kartenobjekt WHERE art = 'reise'").fetchone()[0]), [["Erfundener Hof", ""]])
        con.close()

    def test_lernlisten_za(self):
        import struct
        import sqlite3
        # erfundene Daten: 4 Einträge (0 leer, Art 1, Art 2 mit zwei Formen; die zweite Form liegt bei Index 3)
        size = importer.PERSONAL_SIZE
        per = bytearray(size * 4)

        def entry(i, fsi=0, fc=1, tms=()):
            o = i * size
            per[o + 0x1C] = 1
            struct.pack_into("<H", per, o + 0x18, fsi)
            per[o + 0x1A] = fc
            for b in tms:
                per[o + importer.PERSONAL_TM + (b >> 3)] |= 1 << (b & 7)
        entry(1, tms=(0, importer.ZA_TM_BASE))
        entry(2, fsi=3, fc=2)
        entry(3, fsi=3, fc=2, tms=(2,))

        def learn(moves):
            b = b"".join(struct.pack("<H", m) for m, _ in moves) + bytes(lv for _, lv in moves)
            return b + (b"\0" if len(b) % 2 else b"")
        sets = [b"", learn([(33, 1), (22, 7)]), learn([(10, 1)]), learn([(52, 0), (53, 30)])]
        offs, pos = [], 4 + 2 * (len(sets) + 1)
        for x in sets:
            offs.append(pos)
            pos += len(x)
        lvl = b"za" + struct.pack("<H", len(sets)) + b"".join(struct.pack("<H", o) for o in offs + [pos]) + b"".join(sets)
        got = importer.pkhex_learnsets(lvl, bytes(per))
        self.assertEqual(got[(1, 0)], ([(33, 1), (22, 7)], [0, importer.ZA_TM_BASE]))
        self.assertEqual(got[(2, 1)], ([(52, 0), (53, 30)], [2]))
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE version_groups (id INTEGER, identifier TEXT)")
        con.executemany("INSERT INTO version_groups VALUES (?, ?)", [(30, "legends-za"), (31, "mega-dimension")])
        con.execute("CREATE TABLE pokemon (id INTEGER, species_id INTEGER, is_default INTEGER)")
        con.executemany("INSERT INTO pokemon VALUES (?, ?, ?)", [(1, 1, 1), (2, 2, 1), (10002, 2, 0)])
        con.execute("CREATE TABLE pokemon_forms (pokemon_id INTEGER, form_order INTEGER)")
        con.executemany("INSERT INTO pokemon_forms VALUES (?, ?)", [(1, 1), (2, 1), (10002, 2)])
        con.execute('CREATE TABLE pokemon_moves (pokemon_id INTEGER, version_group_id INTEGER, move_id INTEGER, '
                    'pokemon_move_method_id INTEGER, level INTEGER, "order" INTEGER, mastery INTEGER)')
        n = importer._derive_lernen(con, {"_lernen_za": {"lvl": lvl, "personal": bytes(per)}})
        self.assertEqual(n, 7 + 8)
        za = sorted(con.execute("SELECT pokemon_id, move_id, pokemon_move_method_id, level FROM pokemon_moves WHERE version_group_id = 30"))
        self.assertEqual(za, [(1, 22, 1, 7), (1, 29, 4, 0), (1, 33, 1, 1), (2, 10, 1, 1), (10002, 52, 1, 0), (10002, 53, 1, 30),
                              (10002, importer.ZA_TM[2], 4, 0)])                 # TM der Erweiterung nur in Mega-Dimension
        self.assertIn((1, importer.ZA_TM[importer.ZA_TM_BASE]), list(con.execute(
            "SELECT pokemon_id, move_id FROM pokemon_moves WHERE version_group_id = 31")))
        self.assertEqual(importer._derive_lernen(con, {"_lernen_za": {"lvl": lvl, "personal": bytes(per)}}), 0)   # schon da
        con.close()

    def test_formen_zum_ansehen(self):
        import sqlite3
        from app import abfragen
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE pokemon_forms (id INTEGER, form_identifier TEXT, pokemon_id INTEGER, is_default INTEGER, form_order INTEGER)")
        con.executemany("INSERT INTO pokemon_forms VALUES (?, ?, ?, ?, ?)", [(412, "plant", 412, 1, 1), (10034, "sandy", 412, 0, 2), (25, "", 25, 1, 1)])
        con.execute("CREATE TABLE pokemon_form_names (pokemon_form_id INTEGER, local_language_id INTEGER, form_name TEXT)")
        con.execute("INSERT INTO pokemon_form_names VALUES (10034, 6, 'Sandumhang')")
        got = abfragen._optik(con, {"id": 412})
        self.assertEqual([(x["id"], x["name"]) for x in got], [(None, "Plant"), (10034, "Sandumhang")])
        self.assertEqual(abfragen._optik(con, {"id": 25}), [])             # nur eine Form: nichts zu zeigen
        con.close()

    def test_bdsp_fundorte(self):
        import struct
        import sqlite3

        def area(loc, kind, slots):
            return struct.pack("<HBB", loc, kind, 0) + b"".join(struct.pack("<HBB", sp | form << 11, lo, hi) for sp, form, lo, hi in slots)
        # erfundene Gebiete: Ort 1 Gras (Art 25, Form 0, Art 412 Form 1), Ort 2 Surfer; leere Gebiete fallen weg
        entries = [area(1, 1, [(25, 0, 3, 5), (412, 1, 4, 4)]), area(2, 2, [(72, 0, 20, 30)]), area(3, 1, [])]
        offs, pos = [], 4 + 4 * (len(entries) + 1)
        for e in entries:
            offs.append(pos)
            pos += len(e)
        data = b"bs" + struct.pack("<H", len(entries)) + b"".join(struct.pack("<I", o) for o in offs + [pos]) + b"".join(entries)
        got = importer.pkhex_areas(data)
        self.assertEqual(got, [([1], 101, [(25, 0, 3, 5, 0), (412, 1, 4, 4, 0)]), ([2], 102, [(72, 0, 20, 30, 0)])])
        self.assertEqual(importer.PKHEX_ART[102], "Surfer")
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE pokemon (id INTEGER, species_id INTEGER, is_default INTEGER)")
        con.executemany("INSERT INTO pokemon VALUES (?, ?, ?)", [(25, 25, 1), (72, 72, 1), (412, 412, 1)])
        orte = "Nirgends\nErfundener Wald\nErfundener See\n"
        n = importer._derive_fundort(con, {"brilliant-diamond-shining-pearl": {"begegnungen": data, "begegnungen2": data, "orte": orte}})
        self.assertEqual(n, 3)                                   # die zweite Edition bringt hier nichts Neues
        self.assertEqual(sorted(r[0] for r in con.execute("SELECT gebiet FROM fundort")), ["Erfundener See", "Erfundener Wald", "Erfundener Wald"])
        con.close()

    def test_mapgenie_lesen(self):
        from app import mapgenie
        md = {"map": {"id": 7, "title": "Erfundene Region", "slug": "erfundene-region"},
              "mapConfig": {"tile_sets": [{"pattern": "spiel/erfundene-region/v1/{z}/{x}/{y}.png", "extension": "png", "min_zoom": 9,
                                           "max_zoom": 14, "tiles_max_zoom": 13, "order": 0}]},
              "groups": [{"id": 1, "title": "Sammeln", "color": "89418F", "order": 2, "categories": [
                  {"id": 10, "title": "Licht", "icon": "wisp", "order": 1}, {"id": 11, "title": "Leer", "order": 2}]},
                         {"id": 2, "title": "Orte", "color": "3F7791", "order": 1, "categories": [{"id": 20, "title": "Lager", "order": 1}]}]}
        page = ('<a href="/spiel/maps/erfundene-region">x</a><a href="\\/spiel\\/maps\\/zweite">y</a>'
                '<script>window.mapData = ' + json.dumps(md) + ';window.user = null;</script>')
        regions = [{"title": "Nordwald", "order": 1, "features": [{"geometry": {"type": "Polygon", "coordinates": [[[-1, 0.5], [-0.5, 0.5], [-0.5, 1], [-1, 1]]]}}]}]
        data = json.dumps({"regions": regions, "locations": [
            {"id": 1, "category_id": 10, "latitude": "0.5", "longitude": "-0.25", "title": "Licht 1", "description": "<p>Am <b>Felsen</b></p><p>oben</p>"},
            {"id": 2, "category_id": 20, "latitude": "0.75", "longitude": "-1", "title": "Lager"},
            {"id": 3, "category_id": 10, "latitude": "kaputt", "longitude": "0"}],
            "styles": {"mapStyle": {"bounds": [-1.4, 0, 0, 1.4]}}})
        self.assertEqual(mapgenie.map_slugs(page, "spiel"), ["erfundene-region", "zweite"])
        m = mapgenie.parse(page, data)
        self.assertEqual((m["id"], m["titel"], m["max_zoom"], m["bounds"]), (7, "Erfundene Region", 13, [-1.4, 0, 0, 1.4]))
        self.assertEqual([g["titel"] for g in m["gruppen"]], ["Orte", "Sammeln"])            # nach Reihenfolge, leere Kategorien fallen weg
        self.assertEqual(m["gruppen"][1]["kategorien"], [{"id": 10, "titel": "Licht", "icon": "wisp", "n": 1}])
        self.assertEqual(m["orte"][0], [1, 10, 0.5, -0.25, "Licht 1", "Am Felsen\noben"])
        self.assertEqual(m["gebiete"], [["Nordwald", -1, 0.5, -0.5, 1]])
        self.assertEqual(len(m["orte"]), 2)
        self.assertEqual(mapgenie.tile_ok(m["kacheln"], 10, 508, 509), "spiel/erfundene-region/v1/10/508/509.png")
        self.assertIsNone(mapgenie.tile_ok("../x/{z}/{x}/{y}.png", 1, 1, 1))
        self.assertIsNone(mapgenie.parse("<html></html>", data))

    def test_mapgenie_ausrichten(self):
        import random
        from app import mapgenie
        rnd = random.Random(7)
        game = [(rnd.uniform(0, 1000), rnd.uniform(0, 1000)) for _ in range(20)]
        # erfundene Karte: Maßstab 2,03 und 1,97, verschoben, Symbole von Hand gesetzt (±8 Pixel), dazu fremde Punkte
        mg = [(2.03 * x + 5000 + rnd.uniform(-8, 8), 1.97 * z + 9000 + rnd.uniform(-8, 8)) for x, z in game]
        mg += [(rnd.uniform(0, 12000), rnd.uniform(0, 12000)) for _ in range(60)]
        ax, bx, az, bz = mapgenie.align(game, mg)
        self.assertAlmostEqual(ax, 2.03, delta=0.03)
        self.assertAlmostEqual(az, 1.97, delta=0.03)
        self.assertAlmostEqual(bx, 5000, delta=25)
        self.assertIsNone(mapgenie.align(game[:3], mg))
        # Kacheln innerhalb der Karte wie bei Map Genie (Zoom 11: x und y 1016–1023)
        self.assertEqual(mapgenie.tile_range([-1.4, 0, 0, 1.4], 11), (1016, 1023, 1016, 1023))
        self.assertIsNone(mapgenie.tile_range(None, 11))
        from app import abruf
        self.assertEqual(abruf.serebii_key("King’s Leaf"), "king'sleaf")              # Item-Bilder bei Serebii
        self.assertEqual(abruf.serebii_key("Twice-Spiced Radish"), "twice-spicedradish")
        lat, lng = mapgenie.unproject(*mapgenie.project(0.75, -0.5))
        self.assertAlmostEqual(lat, 0.75, places=6)
        self.assertAlmostEqual(lng, -0.5, places=6)

    def test_lernliste_erweiterung(self):
        from app import abfragen
        D = type("D", (), {})()
        D.games = [{"id": 20, "kennung": "sword-shield"}, {"id": 21, "kennung": "the-isle-of-armor"}, {"id": 32, "kennung": "champions"}]
        self.assertEqual(abfragen.learn_game(D, D.games[1])["id"], 20)        # nicht die Liste des neuesten Spiels
        self.assertEqual(abfragen.learn_game(D, D.games[2])["id"], 32)
        self.assertIsNone(abfragen.learn_game(D, None))

    def test_gebiet_namen(self):
        from app import abfragen
        self.assertEqual(abfragen._place("Dunkelhöhle", "Dunkelhöhle (Viola City Eingang)"), "Dunkelhöhle (Viola City Eingang)")
        self.assertEqual(abfragen._place("Eispfad", "1.UG"), "Eispfad (1.UG)")
        self.assertEqual(abfragen._place("Route 1", ""), "Route 1")

    def test_getragen_item_im_spiel(self):
        import sqlite3
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE spiel (id INTEGER, kennung TEXT)")
        con.execute("INSERT INTO spiel VALUES (24, 'legends-arceus')")
        con.execute("CREATE TABLE item (id INTEGER, name TEXT, spiele TEXT)")
        con.executemany("INSERT INTO item VALUES (?, ?, ?)", [(5, "Erfundsamen", "[1]"), (100002, "Erfundsamen", "[24]"), (7, "Apri-ko-ko", "[24]")])
        ids = importer._item_ids(con, "legends-arceus")
        self.assertEqual(ids["erfundsamen"], 100002)                 # das Item im Spiel gewinnt
        self.assertEqual(ids["aprikoko"], 7)
        con.close()

    def test_altissimo(self):
        import json as js
        from app import altissimo
        lm = js.dumps([
            {"tag": "0", "full": [{"itemName": ["Apricorn"], "spawn": ["100%"]}],
             "groups": [{"conditions": ["apricorn", "tree"], "display": ["Items: 5", "Apricorn: 100%"], "iconLeft": "10%", "iconTop": "20%"}]},
            {"tag": "1", "full": [{"itemName": ["Oran Berry", "Sitrus Berry"], "spawn": ["70%", "30%"]}],
             "groups": [{"conditions": ["oran-berry", "sitrus-berry", "tree"], "display": ["Items: 2-4"], "iconLeft": "50%", "iconTop": "50%"}]},
            {"tag": "2", "full": [{"itemName": ["Iron Chunk"], "spawn": ["100%"]}],
             "groups": [{"conditions": ["iron-chunk", "ore"], "display": [], "iconLeft": "x", "iconTop": "1%"}]},
            {"tag": "3", "full": [{"itemName": ["Nugget"], "spawn": ["1%"]}],
             "groups": [{"conditions": ["nugget", "chest"], "display": ["Items: 3"], "iconLeft": "90%", "iconTop": "5%"}]}])
        objs = altissimo.landmarks(lm, (0.1, 0.0, 0.1, 0.0))
        self.assertEqual([(o["art"], o["x"], o["z"], o["menge"]) for o in objs],
                         [("aprikoko", 100.0, 200.0, "5"), ("beere", 500.0, 500.0, "2-4"), ("truhe", 900.0, 50.0, "3")])
        self.assertEqual(objs[1]["items"], [["Oran Berry", "70%"], ["Sitrus Berry", "30%"]])
        col = js.dumps([{"type": "wisp", "iconLeft": "50%", "iconTop": "25%"}, {"type": "wisp", "iconLeft": "1%", "iconTop": "1%"},
                        {"type": "unown", "iconLeft": "2%", "iconTop": "2%"}, {"type": "unbekannt", "iconLeft": "3%", "iconTop": "3%"}])
        got = altissimo.collectibles(col, altissimo.VILLAGE_FIT)
        self.assertEqual([(o["art"], o["nr"]) for o in got], [("irrlicht", 1), ("irrlicht", 2), ("icognito", 1)])
        self.assertEqual((got[0]["x"], got[0]["z"]), (512.0, 256.0))
        page = """<table><thead><tr><th>Item</th><th>Materials</th><th>Location</th><th>Notes</th></tr></thead><tbody>
          <tr><td>Poké Ball</td><td>1x Apricorn<br>2x Tumblestone</td><td><a href="#">Jubilife Village</a></td><td>Rank 1</td></tr>
          <tr><td>Leer</td><td></td><td></td><td></td></tr></tbody></table>
          <table><thead><tr><th>Material</th><th>Used in</th><th>Locations</th></tr></thead><tbody>
          <tr><td>Apricorn</td><td>Poké Ball recipe</td><td>On trees<br>Sold at the shop</td></tr></tbody></table>"""
        recs, mats = altissimo.recipes(page)
        self.assertEqual(recs, [{"item": "Poké Ball", "zutaten": [[1, "Apricorn"], [2, "Tumblestone"]], "ort": "Jubilife Village", "hinweis": "Rank 1"}])
        self.assertEqual(mats, {"Apricorn": ["On trees", "Sold at the shop"]})
        self.assertEqual(altissimo.place("Jubilife Village"), "Jubeldorf")

    def test_itemlisten_und_rezepte(self):
        import sqlite3
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE spiel (id INTEGER, kennung TEXT, gen INTEGER, reihenfolge INTEGER)")
        con.execute("INSERT INTO spiel VALUES (24, 'legends-arceus', 8, 24)")
        importer.import_csv(con, "items", "id,identifier,category_id,cost,fling_power,fling_effect_id\n"
                                          "17,potion,27,200,30,\n1,fake,23,0,,\n")
        importer.import_csv(con, "item_names", "item_id,local_language_id,name\n17,6,Trank\n17,9,Potion\n")
        importer.import_csv(con, "item_game_indices", "item_id,generation_id,game_index\n17,8,17\n")
        con.execute("CREATE TABLE item_categories (id INTEGER, pocket_id INTEGER)")
        con.execute("INSERT INTO item_categories VALUES (27, 2)")
        de = "\n".join(["???"] * 17 + ["Trank"] + ["???"] * 82 + ["Aprikoko", "Glanzstein", "Pokéball", "Trank"])
        en = "\n".join(["???"] * 17 + ["Potion"] + ["???"] * 82 + ["Apricorn", "Tumblestone", "Poké Ball", "Potion"])
        storage = """public static ReadOnlySpan<ushort> General =>
        [
            017, 100, 101, // Zutaten
        ];
        public static ReadOnlySpan<ushort> Recipe => [ 102, 103 ];
        private static ReadOnlySpan<ushort> Unreleased => [ 999 ];"""
        self.assertEqual(importer.pkhex_spans(storage), {"General": [17, 100, 101], "Recipe": [102, 103]})
        pkx = {"de": "\ufeff" + de, "en": en, "8LA": storage}
        self.assertEqual(importer._derive_item(con, pkx), 4)       # Trank aus der PokéAPI, dazu drei neue (Trank doppelt fällt weg)
        rows = {r[0]: r for r in con.execute("SELECT id, name, tasche, spiele FROM item")}
        self.assertEqual(rows[17][3], "[24]")
        self.assertEqual(rows[importer.PKHEX_ITEM + 100][1:], ("Aprikoko", "Items", "[24]"))
        self.assertNotIn(importer.PKHEX_ITEM + 103, rows)
        page = """<table><tr><th>Item</th><th>Materials</th><th>Location</th><th>Notes</th></tr>
          <tr><td>Poké Ball</td><td>1x Apricorn<br>1x Tumblestone</td><td>Jubilife Village - Craftworks</td><td>Rank 1</td></tr></table>"""
        alt = {"legends-arceus": {"rezepte": page, "symbole": {"obsidianfieldlands": "[]"},
                                  "sammeln": {"jubilifevillage": '[{"type": "wisp", "iconLeft": "10%", "iconTop": "10%"}]'}}}
        en_de = importer.item_en_de(pkx)
        self.assertEqual(importer._derive_rezept(con, alt, en_de), 1)
        r = con.execute("SELECT item_id, item, zutaten, ort FROM rezept").fetchone()
        self.assertEqual(r, (importer.PKHEX_ITEM + 102, "Pokéball",
                             '[[1, "Aprikoko", %d], [1, "Glanzstein", %d]]' % (importer.PKHEX_ITEM + 100, importer.PKHEX_ITEM + 101),
                             "Jubeldorf – Craftworks"))
        self.assertEqual(importer._derive_karte(con, alt, en_de), 1)
        self.assertEqual(con.execute("SELECT karte, gebiet, art, nr FROM kartenobjekt").fetchone(),
                         ("jubilifevillage", "Jubeldorf", "irrlicht", 1))
        con.close()

    def test_bewaehrte_sets(self):
        import sqlite3
        con = sqlite3.connect(":memory:")
        sets = {9: {"pikachu": {"level": 93, "sets": [{"role": "Fast Attacker", "movepool": ["Fake Out", "Volt Tackle"],
                                                        "abilities": ["Lightning Rod"], "teraTypes": ["Water"]}]},
                    "kaputt": "kein Eintrag"},
                1: {"pikachu": {"level": 91, "moves": ["surf", "thunderbolt"]}}}
        self.assertEqual(importer._derive_moveset(con, sets), 2)
        rows = {r[0]: r for r in con.execute("SELECT gen, pokemon, rolle, attacken, faehigkeiten, level FROM moveset")}
        self.assertEqual(rows[9][1:], ("pikachu", "Fast Attacker", '["fakeout", "volttackle"]', '["Lightning Rod"]', 93))
        self.assertEqual(rows[1][2:4], ("", '["surf", "thunderbolt"]'))
        self.assertTrue(abruf.sets_url(1).endswith("random-battles/gen1/data.json"))
        self.assertTrue(abruf.sets_url(9).endswith("random-battles/gen9/sets.json"))

    def test_attacken_kurz_und_text(self):
        import sqlite3
        f = importer.move_short
        self.assertEqual(f(2, 0, 0, 0, [(2, 2)], 0, 0, 7, True), "Angriff +2 (selbst)")                 # Schwerttanz
        self.assertEqual(f(2, 0, 0, 0, [(2, -1)], 0, 0, 11, True), "Angriff −1 (Gegner)")              # Heuler
        self.assertEqual(f(6, 0, 0, 10, [(5, -1)], 0, 0, 10, False), "Sp.-Verteidigung −1 (Gegner, 10 %)")
        self.assertEqual(f(4, 4, 10, 0, None, 0, 0, 10, False), "verbrennt (10 %)")
        self.assertEqual(f(5, 6, 0, 0, [(2, 2)], 0, 0, 10, True), "verwirrt · Angriff +2 (Gegner)")     # Angeberei
        self.assertEqual(f(3, 0, 0, 0, None, 50, 0, 7, True), "heilt 50 % der KP")
        self.assertEqual(f(0, 0, 0, 0, None, 0, 0, 10, False), "")
        # Beschreibung: der neueste Text, aber nicht „kann nicht eingesetzt werden“, wenn es einen älteren gibt
        con = sqlite3.connect(":memory:")
        importer.import_csv(con, "moves", "id,identifier,generation_id,type_id,power,pp,accuracy,priority,target_id,damage_class_id,effect_id\n"
                                          "1,pound,1,1,40,35,100,0,10,2,1\n2,cut-move,1,1,50,30,100,0,10,2,1\n")
        importer.import_csv(con, "move_names", "move_id,local_language_id,name\n1,6,Klaps\n2,6,Alt\n")
        importer.import_csv(con, "move_flavor_text", "move_id,version_group_id,language_id,flavor_text\n1,18,6,Alter Text\n1,20,6,Neuer Text\n"
                                                     "2,18,6,Ein Hieb\n2,20,6,Diese Attacke kann nicht eingesetzt werden.\n")
        importer._derive_attacke(con, {})
        self.assertEqual(dict(con.execute("SELECT id, text FROM attacke")), {1: "Neuer Text", 2: "Ein Hieb"})

    def test_item_wirkung(self):
        f = importer.item_effect
        self.assertEqual(f("Restores 20 HP."), ("KP +20", 20))
        self.assertEqual(f("Restores HP to full and cures any status ailment and confusion."),
                         ("KP voll, heilt alle Statusprobleme und Verwirrung", 999))
        self.assertEqual(f("Revives with half HP, but lowers happiness."), ("belebt mit halben KP, senkt die Freundschaft", 50))
        self.assertEqual(f("Restores 10 PP for each move."), ("AP +10 (alle Attacken)", 10))
        self.assertEqual(f("Cures paralysis."), ("heilt Paralyse", None))
        self.assertEqual(f("Tries to catch a wild Pokémon.  Success rate is 1.5×."), ("Fangfaktor ×1,5", 1.5))
        self.assertEqual(f("Held: boosts Fire moves."), ("", None))

    def test_attacken_kurz_extra(self):
        """extra/attacken_kurz.json: Kennung → kurzer Text; gilt nur, wo die Metadaten nichts hergeben."""
        import sqlite3
        extra = importer.load_extra(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extra"))
        kurz = extra["attacken_kurz"]
        self.assertGreater(len(kurz), 100)
        for k, v in kurz.items():
            self.assertRegex(k, r"^[a-z0-9-]+$")
            self.assertTrue(isinstance(v, str) and 3 < len(v) < 110, k)
        con = sqlite3.connect(":memory:")
        importer.import_csv(con, "moves", "id,identifier,generation_id,type_id,power,pp,accuracy,priority,target_id,damage_class_id,effect_id\n"
                                          "1,protect,2,1,,10,,4,7,1,112\n2,swords-dance,1,1,,20,,0,7,1,51\n")
        importer.import_csv(con, "move_names", "move_id,local_language_id,name\n1,6,Schutzschild\n2,6,Schwerttanz\n")
        importer.import_csv(con, "move_meta", "move_id,meta_category_id,meta_ailment_id,min_hits,max_hits,min_turns,max_turns,drain,healing,"
                                              "crit_rate,ailment_chance,flinch_chance,stat_chance\n1,13,0,,,,,0,0,0,0,0,0\n2,2,0,,,,,0,0,0,0,0,0\n")
        importer.import_csv(con, "move_meta_stat_changes", "move_id,stat_id,change\n2,2,2\n")
        importer._derive_attacke(con, {}, {"protect": "schützt", "swords-dance": "gepflegt, gilt nicht"})
        self.assertEqual(dict(con.execute("SELECT id, kurz FROM attacke")), {1: "schützt", 2: "Angriff +2 (selbst)"})

    def test_auftrag(self):
        rows = [{"key": "attacke:1:AP", "name": "Klaps", "feld": "AP", "pokeapi": "35", "showdown": "40", "entscheidung": ""},
                {"key": "attacke:2:AP", "name": "Hieb", "feld": "AP", "pokeapi": "1", "showdown": "2", "entscheidung": ""},
                {"key": "attacke:3:AP", "name": "Alt", "feld": "AP", "pokeapi": "1", "showdown": "2", "entscheidung": "egal"}]
        t = aufgaben.task(rows)
        self.assertEqual((t["offen"], t["im_auftrag"]), (2, 2))
        self.assertIn("Kennung attacke:1:AP | Klaps | AP | PokéAPI: 35 | Showdown: 40", t["text"])
        self.assertNotIn("attacke:3:AP", t["text"])
        self.assertEqual(aufgaben.task(rows[2:])["text"], "")
        ans = 'Gern:\n```json\n{"pokedex-aufgaben": 1, "antworten": [{"key": "attacke:1:AP", "wert": "Showdown", "grund": "g"}, ' \
              '{"key": "attacke:2:AP", "wert": "unklar"}, {"key": "attacke:3:AP", "wert": "pokeapi"}, {"key": "x", "wert": "egal"}]}\n```'
        res = aufgaben.parse(ans, rows)
        self.assertEqual([(r["key"], r["wert"]) for r in res["uebernehmen"]], [("attacke:1:AP", "showdown")])
        self.assertEqual([r["warum"] for r in res["liegen"]], ["unklar", "schon entschieden", "unbekannte Kennung"])
        with self.assertRaises(ValueError):
            aufgaben.parse('{"antworten": []}', rows)

    def test_showdown(self):
        text = ("export const Moves = {\n\thyperbeam: {\n\t\tnum: 63,\n\t\taccuracy: 90,\n\t\tbasePower: 150,\n\t\tcategory: \"Special\",\n"
                "\t\tname: \"Hyper Beam\",\n\t\tpp: 5,\n\t\tpriority: 0,\n\t\tflags: {recharge: 1, protect: 1},\n\t\ttype: \"Normal\",\n\t},\n"
                "\tswift: {\n\t\tnum: 129,\n\t\taccuracy: true,\n\t\tbasePower: 60,\n\t\tcategory: \"Special\",\n\t\tname: \"Swift\",\n"
                "\t\tpp: 20,\n\t\tpriority: 0,\n\t\tflags: {},\n\t\ttype: \"Normal\",\n\t},\n};\n")
        mv = showdown.moves(text)
        self.assertEqual(mv["hyperbeam"]["basePower"], 150)
        self.assertIn("recharge", mv["hyperbeam"]["flags"])
        self.assertIs(mv["swift"]["accuracy"], True)
        self.assertEqual(showdown.sd_id("raichu-alola"), "raichualola")

    def test_spielname(self):
        self.assertEqual(importer.game_name(["Schwert: Die Insel der Rüstung", "Schild: Die Insel der Rüstung"]),
                         "Schwert / Schild: Die Insel der Rüstung")
        self.assertEqual(importer.game_name(["Rot", "Blau"]), "Rot / Blau")

    def test_csv_typen(self):
        import sqlite3
        con = sqlite3.connect(":memory:")
        importer.import_csv(con, "types", "id,identifier,generation_id,damage_class_id\n1,normal,1,2\n10002,shadow,3,\n")
        rows = con.execute("SELECT id, identifier, damage_class_id FROM types ORDER BY id").fetchall()
        self.assertEqual(rows, [(1, "normal", 2), (10002, "shadow", None)])


class TempData(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._old = store.DATA_DIR
        store.DATA_DIR = self.dir

    def tearDown(self):
        store.DATA_DIR = self._old
        shutil.rmtree(self.dir, ignore_errors=True)


class Abgleich(TempData):
    def test_faellig(self):
        self.assertTrue(abruf.due())                     # ohne Datenbank immer
        open(db.pokeapi_path(), "w").close()
        at = datetime(2026, 11, 9, tzinfo=timezone.utc)
        store.save_json("sync.json", {"started": (at - timedelta(days=2)).isoformat(), "ok": True})
        self.assertFalse(abruf.due(at=at))
        self.assertTrue(abruf.due(at=at + timedelta(days=6)))
        abruf.save_settings({"auto": False})
        self.assertFalse(abruf.due(at=at + timedelta(days=30)))
        with self.assertRaises(ValueError):
            abruf.save_settings({"tage": "x"})

    def test_dateiliste_ohne_github(self):
        def fake(url, timeout=40, headers=None, raw=False):
            raise sources.FetchError(url, 403)
        log = []
        with mock.patch.object(sources, "fetch", fake), mock.patch.object(abruf, "sleep", lambda s: None):
            src = abruf._Source("pokeapi", log.append)
            names, sha = abruf.csv_list(src, log.append)
        self.assertEqual(names, list(importer.NEEDED))
        self.assertEqual(sha, "")
        self.assertFalse(src.blocked)                    # 403 der GitHub-API heißt nur: keine Liste

    def test_sperre(self):
        def fake(url, timeout=40, headers=None, raw=False):
            raise sources.FetchError(url, 429)
        log = []
        with mock.patch.object(sources, "fetch", fake), mock.patch.object(abruf, "sleep", lambda s: None):
            src = abruf._Source("showdown", log.append)
            self.assertIsNone(src.get("https://example.org/a"))
            self.assertIsNone(src.get("https://example.org/b"))
        self.assertTrue(src.blocked)
        self.assertEqual(src.n, 1)                       # nach der Sperre keine weitere Anfrage

    def test_lauf_ohne_quellen_behaelt_alte_daten(self):
        def fake(url, timeout=40, headers=None, raw=False):
            raise sources.FetchError(url, 404)
        with mock.patch.object(sources, "fetch", fake), mock.patch.object(abruf, "sleep", lambda s: None):
            self.assertTrue(abruf.run())
        st = store.load_json("sync.json", {})
        self.assertFalse(st["ok"])
        self.assertFalse(db.has_data())
        self.assertTrue(any("es fehlen" in x for x in st["log"]))


    def test_csv_zwischenspeicher(self):
        self.assertEqual(abruf.cached_csvs("abc"), {})
        abruf.save_csv_cache("abc", {"types": "id\n1\n"})
        self.assertEqual(abruf.cached_csvs("abc"), {"types": "id\n1\n"})
        self.assertEqual(abruf.cached_csvs("neu"), {})


class Server(TempData):
    def test_host(self):
        for h in ("127.0.0.1:8789", "server", "server:8789", "pokedex.home.arpa", "localhost", "[::1]:8789"):
            self.assertTrue(server.host_allowed(h, ""), h)
        self.assertFalse(server.host_allowed("evil.example.com", ""))
        self.assertTrue(server.host_allowed("dex.example.com", ".example.com"))

    def test_teams(self):
        db.migrate()
        with self.assertRaises(ValueError):
            server.save_team({"name": "", "mitglieder": [1]})
        r = server.save_team({"name": "  Hisui  Team ", "mitglieder": [1, 2, "3", 4, 5, 6, 7], "fest": [2, 9], "gewichte": {"tempo": 5, "x": 1}})
        t = server.teams()[0]
        self.assertEqual((t["id"], t["name"], t["mitglieder"], t["fest"], t["gewichte"]), (r["id"], "Hisui Team", [1, 2, 3, 4, 5, 6], [2], {"tempo": 5.0}))
        server.delete_team({"id": r["id"]})
        self.assertEqual(server.teams(), [])

    def test_alte_userdb_bekommt_neue_spalten(self):
        import sqlite3
        os.makedirs(self.dir, exist_ok=True)
        con = sqlite3.connect(db.user_path())
        con.execute("CREATE TABLE team (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spiel TEXT, mitglieder TEXT NOT NULL, fest TEXT, gewichte TEXT, geaendert TEXT)")
        con.execute("INSERT INTO team (name, mitglieder) VALUES ('alt', '[25]')")
        con.commit()
        con.close()
        db.migrate()
        t = server.teams()[0]
        self.assertEqual((t["name"], t["mitglieder"], t["details"]), ("alt", [25], {}))

    def test_team_mit_level_und_attacken(self):
        db.migrate()
        r = server.save_team({"name": "A", "mitglieder": [1, 2], "details": {"1": {"level": "250", "attacken": [5, 6, 7, 8, 9]}, "3": {"level": 5}}})
        t = server.teams()[0]
        # alte Form {id: ...} wird zur Liste je Platz
        self.assertEqual(t["details"], [{"level": 100, "attacken": [5, 6, 7, 8]}, {"level": None, "attacken": []}])
        with self.assertRaises(ValueError):
            server.save_team({"id": r["id"], "name": "A", "mitglieder": [1], "details": {"1": {"level": "x"}}})
        # dasselbe Pokémon zweimal, mit eigenem Level je Platz
        server.save_team({"id": r["id"], "name": "A", "mitglieder": [1, 1], "details": [{"level": 5}, {"level": 50, "attacken": [3]}]})
        t = server.teams()[0]
        self.assertEqual((t["mitglieder"], [d["level"] for d in t["details"]]), ([1, 1], [5, 50]))

    def test_favoriten(self):
        db.migrate()
        server.set_favorite({"spiel": "legends-arceus", "id": 25})
        server.set_favorite({"spiel": "legends-arceus", "id": 25})
        server.set_favorite({"spiel": "red-blue", "id": 1})
        con = db.user()
        try:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM favorit").fetchone()[0], 2)
        finally:
            con.close()
        server.set_favorite({"spiel": "legends-arceus", "id": 25, "an": False})
        self.assertEqual([f["form"] for f in server.export()["favoriten"]], [1])

    def test_gefangen_und_einlesen(self):
        db.migrate()
        server.set_mark("gefangen", {"spiel": "legends-arceus", "id": [403, 404, 25]})
        server.set_mark("gefangen", {"spiel": "legends-arceus", "id": 25, "an": False})
        self.assertEqual(server.marked("gefangen", "legends-arceus"), [403, 404])
        server.save_team({"name": "Erfunden", "spiel": "legends-arceus", "mitglieder": [1, 4], "details": [{"level": 7}, {}]})
        dump = json.loads(json.dumps(server.export()))
        self.assertEqual(len(dump["gefangen"]), 2)
        server.set_mark("gefangen", {"spiel": "x", "id": 9})
        server.delete_team({"id": server.teams()[0]["id"]})
        r = server.restore(dump)
        self.assertEqual((r["teams"], r["gefangen"]), (1, 2))
        self.assertEqual(server.marked("gefangen", "x"), [])
        self.assertEqual(server.teams()[0]["details"][0]["level"], 7)
        self.assertTrue(any(f.startswith("vor-einlesen-") for f in os.listdir(os.path.join(self.dir, "sicherung"))))
        with self.assertRaises(ValueError):
            server.restore({"teams": []})

    def test_schillernd(self):
        db.migrate()
        server.set_mark("schillernd", {"spiel": "legends-arceus", "id": 25})
        self.assertEqual(server.marked("gefangen", "legends-arceus"), [25])          # schillernd heißt auch gefangen
        self.assertEqual(server.marked("schillernd", "legends-arceus"), [25])
        server.set_mark("gefangen", {"spiel": "legends-arceus", "id": 403})
        server.transfer({"von": "legends-arceus", "nach": "pokemon-home", "ids": [25, 403]})
        self.assertEqual(server.marked("schillernd", "pokemon-home"), [25])
        self.assertEqual(server.marked("schillernd", "legends-arceus"), [])
        dump = json.loads(json.dumps(server.export()))
        self.assertEqual([r["form"] for r in dump["schillernd"]], [25])
        server.set_mark("gefangen", {"spiel": "pokemon-home", "id": 25, "an": False})
        self.assertEqual(server.marked("schillernd", "pokemon-home"), [])            # nicht mehr gefangen: auch nicht schillernd
        server.restore(dump)
        self.assertEqual(server.marked("schillernd", "pokemon-home"), [25])

    def test_grosse_itembilder(self):
        import sqlite3
        con = sqlite3.connect(os.path.join(self.dir, "pokeapi.db"))
        con.execute("CREATE TABLE spiel (id INTEGER, kennung TEXT)")
        con.executemany("INSERT INTO spiel VALUES (?, ?)", [(24, "legends-arceus"), (25, "scarlet-violet"), (1, "red-blue")])
        con.execute("CREATE TABLE item (id INTEGER, en TEXT, spiele TEXT, tasche TEXT, unfertig INTEGER, kennung TEXT)")
        con.executemany("INSERT INTO item VALUES (?, ?, ?, ?, 0, ?)", [
            (1, "Poké Ball", "[1, 24, 25]", "Bälle", "poke-ball"), (2, "Gigaton Ball", "[24]", "Bälle", "pkhex-1"),
            (3, "Potion", "[1]", "Medizin", "potion"), (4, "TM01", "[25]", "Maschinen", "tm01"), (5, "", "[25]", "Medizin", "x")])
        con.commit()
        con.close()
        self.assertEqual(abruf.media_ids("itemhq"), {1: ("sv/pokeball", "legends/pokeball", "pokeball"),
                                                     2: ("legends/gigatonball", "sv/gigatonball", "gigatonball")})
        self.assertEqual(sorted(abruf.media_ids("itembild")), [1, 3, 5])           # PKHeX-Items haben kein Bild bei der PokéAPI

    def test_gefunden(self):
        db.migrate()
        server.set_found({"spiel": "legends-arceus", "karte": "erfundene-karte", "objekt": ["irrlicht:1:2", "vers:3:4"]})
        server.set_found({"spiel": "legends-arceus", "karte": "erfundene-karte", "objekt": "vers:3:4", "an": False})
        server.set_found({"spiel": "scarlet-violet", "karte": "mg-erfunden", "objekt": "mg:7"})
        self.assertEqual(server.found("legends-arceus"), {"erfundene-karte": ["irrlicht:1:2"]})
        with self.assertRaises(ValueError):
            server.set_found({"spiel": "x", "karte": "", "objekt": "a"})
        dump = json.loads(json.dumps(server.export()))
        self.assertEqual(len(dump["gefunden"]), 2)
        old = {k: v for k, v in dump.items() if k != "gefunden"}           # ältere Sicherung ohne gefundene Symbole
        server.restore(old)
        self.assertEqual(server.found("scarlet-violet", "mg-erfunden"), {"mg-erfunden": ["mg:7"]})
        server.set_found({"spiel": "x", "karte": "k", "objekt": "o"})
        server.restore(dump)
        self.assertEqual(server.found("x"), {})

    def test_mapgenie_karte(self):
        os.makedirs(os.path.join(self.dir, "mapgenie"))
        abruf.store.save_json("mapgenie/scarlet-violet.json", {"spiel": "scarlet-violet", "am": "2026-11-11", "karten": [
            {"slug": "erfunden", "titel": "Erfunden", "kacheln": "spiel/erfunden/{z}/{x}/{y}.png", "min_zoom": 9, "max_zoom": 12, "orte": []}]})
        self.assertEqual(abruf.mg_maps("the-teal-mask")["karten"][0]["slug"], "erfunden")       # Erweiterung: Karte des Hauptspiels
        self.assertIsNone(abruf.mg_maps("red-blue"))
        f = os.path.join(self.dir, "mapgenie", "kacheln", "spiel", "erfunden", "10", "1", "2.png")
        os.makedirs(os.path.dirname(f))
        open(f, "wb").write(b"\x89PNG\r\n\x1a\n")
        self.assertEqual(abruf.mg_tile("scarlet-violet", "erfunden", 10, 1, 2), f)
        self.assertIsNone(abruf.mg_tile("scarlet-violet", "erfunden", 3, 1, 2))                   # Zoom außerhalb
        self.assertIsNone(abruf.mg_tile("scarlet-violet", "andere", 10, 1, 2))

    def test_alpha(self):
        db.migrate()
        server.set_mark("alpha", {"spiel": "legends-arceus", "id": 59})
        self.assertEqual(server.marked("gefangen", "legends-arceus"), [59])          # Alpha heißt auch gefangen
        server.transfer({"von": "legends-arceus", "nach": "pokemon-home", "ids": [59]})
        self.assertEqual(server.marked("alpha", "pokemon-home"), [59])
        dump = json.loads(json.dumps(server.export()))
        self.assertEqual([r["form"] for r in dump["alpha"]], [59])
        server.set_mark("gefangen", {"spiel": "pokemon-home", "id": 59, "an": False})
        self.assertEqual(server.marked("alpha", "pokemon-home"), [])
        server.restore(dump)
        self.assertEqual(server.marked("alpha", "pokemon-home"), [59])

    def test_smogon(self):
        from app import smogon
        self.assertEqual(smogon.months('<a href="2026-09/">x</a><a href="2026-10/">x</a><a href="2026-10-DLC1/">x</a>')[0], "2026-10-DLC1")
        files = smogon.chaos_files('<a href="gen9ou-1695.json"></a><a href="gen9vgc2026regf-1500.json"></a><a href="gen9vgc2026regf-1630.json"></a>'
                                   '<a href="gen9vgc2026regg-1760.json"></a>')
        self.assertEqual(smogon.pick(files), ("gen9vgc2026regg", 1760))      # neueste Regel, dann die verfügbare Grenze
        files["gen9championsvgc"] = [0, 1500, 1630]
        self.assertEqual(smogon.pick(files), ("gen9championsvgc", 1630))     # Champions zuerst
        chaos = {"info": {"metagame": "gen9erfunden", "number of battles": 1234},
                 "data": {"Erfundenmon": {"usage": 0.5, "Moves": {"protect": 30, "tackle": 10, "": 5}, "Items": {"leftovers": 2},
                                          "Abilities": {"intimidate": 1}, "Tera Types": {"fairy": 3}, "Teammates": {"Zweitmon": 4}},
                          "Zweitmon": {"usage": 0.25}, "Kaputt": "x"}}
        d = smogon.digest(chaos, "gen9erfunden", 1630, "2026-10")
        self.assertEqual([r["name"] for r in d["pokemon"]], ["Erfundenmon", "Zweitmon"])
        self.assertEqual(d["pokemon"][0]["anteil"], 50.0)
        self.assertEqual(d["pokemon"][0]["attacken"][0], ["protect", 100.0])  # vier Plätze je Pokémon, höchstens 100 %
        self.assertEqual(d["kaempfe"], 1234)

    def test_alte_generationen(self):
        from app import abfragen
        self.assertTrue(abfragen.no_abilities({"kennung": "crystal", "gen": 2}))
        self.assertTrue(abfragen.no_abilities({"kennung": "lets-go-pikachu-lets-go-eevee", "gen": 7}))
        self.assertFalse(abfragen.no_abilities({"kennung": "emerald", "gen": 3}))
        self.assertEqual(abfragen.old_class({"klasse": 3, "typ": 1}, 3)["klasse"], 2)    # Normal ist bis Gen 3 physisch
        self.assertEqual(abfragen.old_class({"klasse": 2, "typ": 10}, 1)["klasse"], 3)   # Feuer speziell
        self.assertEqual(abfragen.old_class({"klasse": 2, "typ": 10}, 4)["klasse"], 2)   # ab Gen 4 je Attacke
        self.assertEqual(abfragen.old_class({"klasse": 1, "typ": 1}, 1)["klasse"], 1)    # Status bleibt

    def test_abgleich_parallel(self):
        from app import abruf, sources
        # Ergebnisse und Fehler je Aufgabe
        r = abruf._parallel({"a": lambda: 1, "b": lambda: 1 / 0})
        self.assertEqual(r["a"], 1)
        self.assertIsInstance(r["b"], ZeroDivisionError)
        # zwei Quellen am selben Server: Abrufe nie gleichzeitig, die Pause gilt für beide zusammen
        busy, over = [0], []
        def fake(url, timeout=40, headers=None, raw=False):
            busy[0] += 1
            over.append(busy[0])
            time.sleep(0.01)
            busy[0] -= 1
            return "x"
        old = sources.fetch
        sources.fetch = fake
        try:
            a, b = abruf._Source("pkhex", lambda m: None, pause=0), abruf._Source("spawns", lambda m: None, pause=0)
            abruf._parallel({"a": lambda: [a.get("https://erfunden.example/1") for _ in range(5)],
                             "b": lambda: [b.get("https://erfunden.example/2") for _ in range(5)]})
        finally:
            sources.fetch = old
        self.assertEqual(max(over), 1)
        self.assertEqual(a.n + b.n, 10)

    def test_potential_weiteste_form(self):
        from app import abfragen
        D = type("D", (), {})()
        D.forms = {1: {"art": 1}, 2: {"art": 2}, 3: {"art": 3}, 10: {"art": 10}, 11: {"art": 11}}
        stages = {1: 0, 2: 1, 3: 2, 10: 0, 11: 1}
        old = abfragen._stage
        abfragen._stage = lambda D, arten: {a: stages[a] for a in arten}
        try:
            pot = [{"id": 1, "plus": 9.0, "wird": {"id": 3}}, {"id": 2, "plus": 8.0, "wird": {"id": 3}}, {"id": 10, "plus": 5.0, "wird": {"id": 11}}]
            got = abfragen._furthest(pot, D, set())
            self.assertEqual(sorted(r["id"] for r in got), [2, 10])       # je Endstufe nur die weiteste gefangene Stufe
            self.assertEqual([r["id"] for r in abfragen._furthest(pot, D, {11})], [2])   # Endstufe schon gefangen oder vorgeschlagen
            # gleiche Stufe: das Mitglied im Team geht dem gefangenen vor
            pot2 = [{"id": 2, "plus": 9.0, "wird": {"id": 3}}, {"id": 2, "plus": 4.0, "wird": {"id": 3}, "im_team": True}]
            self.assertTrue(abfragen._furthest(pot2, D, set())[0].get("im_team"))
        finally:
            abfragen._stage = old

    def test_uebertragen(self):
        db.migrate()
        server.set_mark("gefangen", {"spiel": "legends-arceus", "id": [403, 404, 25]})
        server.transfer({"von": "legends-arceus", "nach": "pokemon-home", "ids": [403, 404]})
        self.assertEqual(server.marked("gefangen", "legends-arceus"), [25])
        self.assertEqual(sorted(server.marked("gefangen", "pokemon-home")), [403, 404])
        server.transfer({"von": "legends-arceus", "nach": "pokemon-home", "ids": [25], "behalten": True})
        self.assertEqual(server.marked("gefangen", "legends-arceus"), [25])
        server.transfer({"von": "pokemon-home", "nach": "freilassen", "ids": [403], "behalten": True})
        self.assertEqual(sorted(server.marked("gefangen", "pokemon-home")), [25, 404])
        with self.assertRaises(ValueError):
            server.transfer({"von": "pokemon-home", "nach": "pokemon-home", "ids": [25]})

    def test_entscheidung(self):
        db.migrate()
        server.decide({"art": "pruefung", "schluessel": "form:25:KP", "wert": "showdown"})
        con = db.user()
        self.assertEqual(con.execute("SELECT wert FROM entscheidung").fetchone()[0], "showdown")
        con.close()
        with self.assertRaises(ValueError):
            server.decide({"art": "anders", "schluessel": "x", "wert": "pokeapi"})

    def test_sicherung(self):
        db.migrate()
        for d in range(20):
            db.backup(datetime(2026, 1, 1).date() + timedelta(days=d))
        self.assertEqual(len(os.listdir(os.path.join(self.dir, "sicherung"))), db.BACKUP_KEEP)


@unittest.skipUnless(os.environ.get("POKEAPI_DB"), "POKEAPI_DB: Pfad zu einer gebauten pokeapi.db")
class MitDatenbank(TempData):
    """Gegen eine echte Datenbank (lokal, nicht in CI): POKEAPI_DB=/pfad/pokeapi.db python -m unittest tests.test_all"""

    def setUp(self):
        super().setUp()
        os.symlink(os.environ["POKEAPI_DB"], db.pokeapi_path())
        db.migrate()

    def test_showdown_import_export(self):
        from app import abfragen
        r = abfragen.paste_import({"text": "Rotom-Wash @ Sitrus Berry\nAbility: Levitate\nModest Nature\n- Hydro Pump\n\n"
                                           "Knakrack\n- Erdbeben\n\nGiratina-Origin\n\nGibtsnicht\n"})
        self.assertEqual(len(r["ids"]), 3)
        self.assertEqual(r["hinweise"], ["„Gibtsnicht“ nicht gefunden"])
        text = abfragen.paste_export({"ids": r["ids"], "details": r["details"]})["text"]
        self.assertIn("Rotom-Wash @ Sitrus Berry", text)
        self.assertIn("Modest Nature", text)
        self.assertIn("Garchomp", text)
        self.assertIn("- Earthquake", text)
        self.assertIn("Giratina-Origin", text)

    def test_hisui(self):
        from app import abfragen
        r = abfragen.search({"spiel": "legends-arceus", "limit": 3})
        self.assertGreaterEqual(r["n"], 240)
        z = abfragen.search({"spiel": "legends-arceus", "q": "Zoroark"})["rows"][0]
        self.assertEqual(z["name"], "Hisui Zoroark")
        d = abfragen.detail(z["id"], {"spiel": "legends-arceus"})
        self.assertEqual(d["faehigkeiten"], [])
        self.assertEqual(d["entwicklung"][0]["name"], "Hisui Zorua")
        self.assertEqual(len(d["attacken"]["moveset"]), 4)
        best = abfragen.team_optimize({"spiel": "legends-arceus", "filter": {"ohne_leg": 1, "endstufe": 1}})
        self.assertEqual(len(best["teams"][0]["ids"]), 6)
        both = abfragen.search({"spiel": "legends-arceus", "typen": "10,8", "modus": "und"})["rows"]
        self.assertTrue(all({10, 8} <= set(r["typen"]) for r in both))
        either = abfragen.search({"spiel": "legends-arceus", "typen": "10,8", "modus": "oder", "ohne": "3"})["rows"]
        self.assertTrue(all((10 in r["typen"] or 8 in r["typen"]) and 3 not in r["typen"] for r in either))
        moves = abfragen.move_list({"spiel": "legends-arceus"})["rows"]
        self.assertTrue(any(m["klasse"] == 1 for m in moves))
        self.assertLess(next(m for m in moves if m["name"] == "Finale")["wertung"], 100)
        mv = abfragen.moves_of(z["id"], {"spiel": "legends-arceus", "level": 30})
        ev = abfragen.team_view({"spiel": "legends-arceus", "ids": [z["id"]], "details": {str(z["id"]): {"level": 30, "attacken": [mv["moveset"][0]["id"]]}}})
        self.assertEqual(ev["verbesserungen"][0]["id"], z["id"])
        self.assertIn(str(mv["moveset"][0]["id"]), ev["attacken"])
        mu = abfragen.team_matchup({"spiel": "legends-arceus", "ids": [z["id"]], "gegner": [z["id"], 6]})
        self.assertEqual(len(mu["einzeln"]), 2)

    def test_0_3_0(self):
        from app import abfragen
        bauz = abfragen.search({"spiel": "legends-arceus", "q": "Bauz"})["rows"][0]
        self.assertEqual(bauz["nr"], 1)
        # Standard-Attacken wie im Spiel: höchstens vier, ohne Level die ersten, mit Level die letzten bis dahin
        first = abfragen.moves_of(bauz["id"], {"spiel": "legends-arceus"})["standard"]
        late = abfragen.moves_of(bauz["id"], {"spiel": "legends-arceus", "level": 50})["standard"]
        self.assertEqual(len(first), 4)
        self.assertNotEqual(first, late)
        # stark gegen Feuer: kein Feuer-schwaches Pokémon dabei
        rows = abfragen.search({"spiel": "legends-arceus", "gegen": "10", "limit": 500})["rows"]
        self.assertTrue(rows)
        D = abfragen.data()
        ch = D.chart(8)
        self.assertTrue(all(abfragen.strong_against(r["typen"], 10, ch) for r in rows))
        # dasselbe Pokémon zweimal, Level je Platz; Hinweis, wenn ein Mitglied nicht im Spiel ist
        ev = abfragen.team_view({"spiel": "legends-arceus", "ids": [bauz["id"], bauz["id"], 1],
                                 "details": [{"level": 5, "attacken": first}, {"level": 50, "attacken": late}, {}]})
        self.assertEqual([v["slot"] for v in ev["verbesserungen"]], [0, 1, 2])
        self.assertEqual(ev["nicht_im_spiel"], [2])
        sg = abfragen.team_suggest({"spiel": "legends-arceus", "ids": [bauz["id"]], "filter": {"q": "Bauz"}})
        self.assertGreaterEqual(sg["schon_im_team"], 1)

    def test_0_4_0(self):
        from app import abfragen
        db.migrate()
        alle = abfragen.search({"spiel": "legends-arceus", "gen": 4})["n"]
        nur = abfragen.search({"spiel": "legends-arceus", "gen": 4, "genmodus": "nur", "limit": 500})
        self.assertLess(nur["n"], alle)
        self.assertTrue(all(r["gen"] == 4 for r in nur["rows"]))
        klar = abfragen.search({"spiel": "legends-arceus", "gegen": "10", "klar": 1})["n"]
        self.assertLessEqual(klar, abfragen.search({"spiel": "legends-arceus", "gegen": "10"})["n"])
        # Gefangene: Filter und Empfehlungen (Staralili entwickelt sich zu Staraptor)
        star = abfragen.search({"spiel": "legends-arceus", "q": "Staralili"})["rows"][0]["id"]
        karp = abfragen.search({"spiel": "legends-arceus", "q": "Karpador"})["rows"][0]["id"]
        server.set_mark("gefangen", {"spiel": "legends-arceus", "id": [star]})
        self.assertEqual(abfragen.search({"spiel": "legends-arceus", "nur": "gef"})["n"], 1)
        r = abfragen.team_caught({"spiel": "legends-arceus", "ids": [karp, karp]})
        self.assertEqual(r["gefangen"], 1)
        self.assertTrue(r["alternativen"] or r["potential"])
        # Steht Staravia schon im Team, bringt das gefangene Staralili kein eigenes Potential mehr
        via = abfragen.search({"spiel": "legends-arceus", "q": "Staravia"})["rows"][0]["id"]
        r = abfragen.team_caught({"spiel": "legends-arceus", "ids": [karp, via]})
        self.assertFalse([x for x in r["potential"] if x["id"] == star])


if __name__ == "__main__":
    unittest.main()
