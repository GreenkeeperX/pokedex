"""Tests ohne Netz: Rechenlogik, Leser, Abgleich mit Attrappe, Server-Hilfen. Start: python -m unittest discover -s tests"""
import json
import os
import shutil
import tempfile
import time
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import abruf, attacken, aufgaben, db, importer, server, showdown, sources, store, team, typen
from app.typen import BODEN, DRACHE, EIS, ELEKTRO, FEE, FEUER, FLUG, GEIST, KAMPF, NORMAL, PFLANZE, PSYCHO, STAHL, UNLICHT, WASSER

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
        self.assertEqual([x["faktor"] for x in t], [1, 1.5, 2])                    # für den Rechenweg im Tooltip
        self.assertEqual(t[1]["schlaf"], 73.4)                                   # Fangrate 45, Superball, 1 KP, Schlaf: b = 60654, vier Proben
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

    def test_0_36_0_texte_je_spiel(self):
        from app import pokewiki
        wt = ("{{Pokédex-Einträge\n|typ1=Normal\n|diamond=Text D mit [[Link|Wort]].\n|pearl=Text P.\n|platinum=Text Pt.\n"
              "|sw=Text SW.\n|SW=Text Schwert.\n|SH=Text Schwert.\n|pla=Text LA{{Anmerkung|x}}.\n|neu=Unbekannt.\n}}\n"
              "{{Pokédex-Einträge/Spin-offs\n|go=Spin-off.\n}}\n"
              "{{Pokédex-Aufgaben\n|Exemplare gefangen/1/3/6/12/25|double1=1\n|Registrierte Formen/2/0/0/0/0\n}}")
        tx = pokewiki.dex_texts(wt)
        self.assertNotIn("typ1", tx)
        self.assertNotIn("go", tx)
        self.assertEqual(tx["diamond"], "Text D mit Wort.")
        self.assertEqual(tx["pla"], "Text LA.")
        per = pokewiki.per_game("pokemon", tx)
        self.assertEqual(per["diamond-pearl"], [("Diamant", "Text D mit Wort."), ("Perl", "Text P.")])
        self.assertEqual(per["black-white"], [("", "Text SW.")])                 # „sw“ ist Schwarz/Weiß, „SW“ Schwert
        self.assertEqual(per["sword-shield"], [("Schwert / Schild", "Text Schwert.")])     # gleicher Text zusammengefasst
        self.assertEqual(pokewiki.unknown_keys("pokemon", tx), ["neu"])
        self.assertEqual(pokewiki.research_tasks(wt), [
            {"aufgabe": "Exemplare gefangen", "stufen": ["1", "3", "6", "12", "25"], "doppelt": True},
            {"aufgabe": "Registrierte Formen", "stufen": ["2", "0", "0", "0", "0"], "doppelt": False}])
        # Attacken: das genaueste Kürzel gewinnt (gen3 gilt für alle Spiele der Generation, frbg nur für Feuerrot/Blattgrün)
        mv = pokewiki.move_texts("{{Atk-Beschreibung\n|gen3=Alt.\n|frbg=FRBG.\n|pmd=Dungeon.\n|kapu=KP.\n}}")
        per = pokewiki.per_game("attacken", mv)
        self.assertEqual(per["emerald"], [("", "Alt.")])
        self.assertEqual(per["firered-leafgreen"], [("", "FRBG.")])
        self.assertEqual(per["scarlet-violet"], [("", "KP.")])
        self.assertEqual(pokewiki.unknown_keys("attacken", mv), [])             # Spin-offs fallen still weg
        ab = pokewiki.ability_texts("{{Fähigkeit/Infobox\n|Name_en=Static\n|Gen3=Drei.\n|Gen9=Neun.\n}}")
        self.assertEqual(ab, {"gen3": "Drei.", "gen9": "Neun."})
        self.assertEqual(pokewiki.per_game("faehigkeiten", ab)["legends-za"], [("", "Neun.")])
        self.assertEqual(pokewiki.clean("A{{tt|B|Hinweis}}<br />C<ref>Fuß</ref>"), "AB C")

    def test_0_36_0_texte_in_der_datenbank(self):
        import sqlite3
        from types import SimpleNamespace
        from app import abfragen
        con = sqlite3.connect(":memory:")
        csvs = {"pokemon_species_names": "pokemon_species_id,local_language_id,name\n399,6,Bidiza\n",
                "version_groups": "id,identifier,generation_id,order\n8,diamond-pearl,4,8\n15,x-y,6,15\n",
                "versions": "id,version_group_id,identifier\n12,8,diamond\n13,8,pearl\n23,15,x\n24,15,y\n",
                "version_names": "version_id,local_language_id,name\n23,6,X\n24,6,Y\n",
                "pokemon_species_flavor_text": "species_id,version_id,language_id,flavor_text\n399,23,6,Gleich.\n399,24,6,Gleich.\n",
                "ability_names": "ability_id,local_language_id,name\n9,6,Statik\n"}
        for n, t in csvs.items():
            importer.import_csv(con, n, t)
        con.execute("CREATE TABLE attacke (id INTEGER, name TEXT)")
        con.execute("INSERT INTO attacke VALUES (33, 'Tackle')")
        wiki = {"texte": {"pokemon": {"Bidiza": {"texte": {"diamond": "D.", "pearl": "P.", "x": "Wiki X."},
                                                 "aufgaben": [{"aufgabe": "Exemplare gefangen", "stufen": ["1", "3"], "doppelt": True}]},
                                      "Gibtsnicht": {"texte": {"x": "?"}}},
                          "attacken": {"Tackle": {"texte": {"gen4": "Vier.", "neu": "?"}}},
                          "faehigkeiten": {"Statik": {"texte": {"gen3": "Drei."}}}}}
        n, tasks, unknown = importer._derive_texts(con, wiki)
        self.assertEqual((n, tasks, unknown), ({"pokemon": 1, "attacken": 1, "faehigkeiten": 1}, 1, {"attacken": ["neu"]}))
        rows = con.execute("SELECT spiel, edition, text, quelle FROM spieltext WHERE art = 'pokemon' ORDER BY spiel, edition").fetchall()
        # PokéAPI vor PokéWiki (X/Y), gleicher Text beider Editionen einmal
        self.assertEqual(rows, [("diamond-pearl", "Diamant", "D.", "PokéWiki"), ("diamond-pearl", "Perl", "P.", "PokéWiki"),
                                ("x-y", "X / Y", "Gleich.", "PokéAPI")])
        games = [{"kennung": k, "name": k.upper(), "reihenfolge": i} for i, k in enumerate(
            ("red-blue", "diamond-pearl", "platinum", "x-y", "the-crown-tundra", "sword-shield"))]
        D = SimpleNamespace(games=games)
        per = abfragen.text_rows(con, "pokemon", 399)
        t = abfragen.pick_text(D, per, games[2])                              # Platin ohne Text: das Spiel davor
        self.assertEqual((t["aus"], abfragen.joined(t)), ("DIAMOND-PEARL", "Diamant: D. · Perl: P."))
        self.assertEqual(abfragen.pick_text(D, per, games[0])["aus"], "DIAMOND-PEARL")     # nichts davor: das erste
        self.assertEqual(abfragen.pick_text(D, per, games[3])["aus"], "")
        self.assertEqual(abfragen.pick_text(D, {"sword-shield": [("", "S.", "PokéAPI")]}, games[4])["aus"], "")  # Erweiterung
        self.assertEqual(abfragen._research(con, 399), [{"aufgabe": "Exemplare gefangen", "stufen": ["1", "3"], "doppelt": True}])
        con.close()

    def test_0_38_0_png(self):
        import struct
        import zlib
        from app import png
        w, h = 5, 3
        rgba = b"".join(bytes([x * 40, y * 80, (x + y) * 20, 255 if x % 2 else 128]) for y in range(h) for x in range(w))
        self.assertEqual(png.decode(png.encode(w, h, rgba)), (w, h, rgba))

        def chunk(k, b):
            return struct.pack(">I", len(b)) + k + b + struct.pack(">I", zlib.crc32(k + b))

        def make(ctype, depth, rows, pal=b"", trns=b""):
            body = png.SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, 0))
            if pal:
                body += chunk(b"PLTE", pal)
            if trns:
                body += chunk(b"tRNS", trns)
            return body + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")
        # RGB mit allen Filtern: Zeile 0 Sub, Zeile 1 Up, Zeile 2 Paeth (Durchschnitt in einer eigenen Zeile unten)
        rgb = [bytes([x * 40, y * 80, (x + y) * 20]) for y in range(h) for x in range(w)]
        line = lambda y: b"".join(rgb[y * w:(y + 1) * w])

        def sub(cur):
            return bytes([cur[i] if i < 3 else (cur[i] - cur[i - 3]) & 255 for i in range(len(cur))])

        def up(cur, prev):
            return bytes([(a - b) & 255 for a, b in zip(cur, prev)])

        def paeth(cur, prev):
            out = []
            for i in range(len(cur)):
                a = cur[i - 3] if i >= 3 else 0
                b = prev[i]
                c = prev[i - 3] if i >= 3 else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                out.append((cur[i] - (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255)
            return bytes(out)

        def avg(cur, prev):
            return bytes([(cur[i] - (((cur[i - 3] if i >= 3 else 0) + prev[i]) >> 1)) & 255 for i in range(len(cur))])
        rows = [b"\1" + sub(line(0)), b"\2" + up(line(1), line(0)), b"\4" + paeth(line(2), line(1))]
        want = b"".join(px + b"\xff" for px in rgb)
        self.assertEqual(png.decode(make(2, 8, rows))[2], want)
        rows = [b"\0" + line(0), b"\3" + avg(line(1), line(0)), b"\0" + line(2)]
        self.assertEqual(png.decode(make(2, 8, rows))[2], want)
        # Palette mit 4 Bit und Transparenz: Index = x
        pal = b"".join(bytes([i * 10, i * 20, i * 30]) for i in range(5))
        rows = [b"\0" + bytes([0x01, 0x23, 0x40]) for _ in range(h)]
        out = png.decode(make(3, 4, rows, pal, b"\0"))[2]
        self.assertEqual(out[:8], bytes([0, 0, 0, 0, 10, 20, 30, 255]))
        self.assertEqual(out[16:20], bytes([40, 80, 120, 255]))
        with self.assertRaises(png.PNGError):
            png.decode(b"kein Bild")

    def test_0_38_0_dittobase(self):
        import base64
        from app import dittobase, mapgenie as _mg
        mon = {"species": "ONIX", "slug": "onix", "name": "Onix", "level": 11, "moves": [{"name": "Tackle"}]}
        props = {"data": {"overworld": {"width": 128, "height": 64}, "maps": {
            "Stadt": {"name": "Erfundenstadt", "width": 2, "height": 1, "overworld": {"x": 0, "y": 0}},
            "Weg": {"name": "Erfundenweg", "width": 2, "height": 2, "overworld": {"x": 64, "y": 0}},
            "Hoehle": {"name": "Erfundenhöhle", "width": 2, "height": 2, "overworld": None},
            "Tief": {"name": "Erfundenhöhle UG", "width": 2, "height": 2, "overworld": None}},
            "markers": {"Stadt": [{"kind": "item", "x": 1, "y": 0, "name": "Potion"},
                                  {"kind": "door", "x": 2, "y": 1, "name": "Höhle", "door": {"to": "Hoehle"}},
                                  {"kind": "sign", "x": 0, "y": 0, "name": "Sign"}],
                        "Hoehle": [{"kind": "door", "x": 0, "y": 0, "name": "zurück", "door": {"to": "Stadt"}},
                                   {"kind": "door", "x": 1, "y": 1, "name": "tiefer", "door": {"to": "Tief"}},
                                   {"kind": "trainer", "x": 1, "y": 1, "name": "Wanderer Erfunden",
                                    "trainer": {"team": [mon, mon], "prize": 352}}],
                        "Tief": [{"kind": "hidden-item", "x": 0, "y": 0, "name": "Ether"}],
                        "Weg": [{"kind": "npc", "x": 0, "y": 0, "name": "Fruit Tree"}]}},
            "pixi": {"tilesets": {"satz": {"image": "https://assets.dittobase.com/game-maps/crystal-maps/pixi/tilesets/satz.png",
                                           "columns": 2}},
                     "maps": {"Stadt": {"tileset": "satz", "blocks": base64.b64encode(bytes([0, 1])).decode()},
                              "Weg": {"tileset": "satz", "blocks": base64.b64encode(bytes([1, 0, 0, 1])).decode()}}},
            "wild": {"Weg": [{"name": "Rattata", "method": "grass", "times": ["night"], "minLevel": 4, "maxLevel": 6, "chance": 40}]}}
        row = json.dumps(["$", "$L24", None, props])
        chunk = json.dumps([1, "1:\"$Sreact.fragment\"\n14:" + row + "\n"])
        page = f"<html><script>self.__next_f.push({chunk})</script></html>"
        d = dittobase.extract(page)
        self.assertEqual(sorted(d), ["data", "pixi", "wild"])
        self.assertEqual(dittobase.anchors(d["data"])["Tief"][2], ("Erfundenhöhle", "Erfundenhöhle UG"))
        m, draw = dittobase.parse(d, "crystal")
        self.assertEqual((m["slug"], m["quelle"], m["min_zoom"], m["max_zoom"]), ("db-crystal", "dittobase", -5, 1))
        names = {o[4]: o for o in m["orte"]}
        self.assertEqual(sorted(names), ["Beerenbaum", "Erfundenweg", "Ether", "Potion", "Wanderer Erfunden"])
        x, y = _mg.project(names["Potion"][2], names["Potion"][3], 0)
        self.assertAlmostEqual(x, 16 + 8, places=2)                      # Schritt 1 = 16 Pixel, Mitte des Felds
        self.assertAlmostEqual(y, 8, places=2)
        self.assertIn("In: Erfundenhöhle\n2× «Onix» Lv. 11 (Tackle)\nPreisgeld 352", names["Wanderer Erfunden"][5])
        self.assertIn("In: Erfundenhöhle → Erfundenhöhle UG", names["Ether"][5])
        self.assertIn("«Rattata» Lv. 4–6, Gras (nachts), 40 %", names["Erfundenweg"][5])
        x, y = _mg.project(names["Ether"][2], names["Ether"][3], 0)
        self.assertLess(abs(x - 40) + abs(y - 24), 30)                   # am Eingang der Höhle (Tür bei 2, 1)
        self.assertEqual([g[0] for g in m["gebiete"]], ["Erfundenstadt", "Erfundenweg"])
        self.assertEqual(len(draw["karten"]), 2)
        self.assertTrue(dittobase.tileset_ok(draw["saetze"]["satz"]["bild"]))
        self.assertFalse(dittobase.tileset_ok("https://example.com/satz.png"))
        # Zeichnen: Kachelsatz 64 × 32 (Block 0 rot, Block 1 blau)
        red, blue = bytes([255, 0, 0, 255]), bytes([0, 0, 255, 255])
        rgba = b"".join((red * 32 + blue * 32) for _ in range(32))
        got = {}
        n = dittobase.render_tiles(draw, {"satz": (64, 32, rgba)}, lambda z, x, y, b: got.__setitem__((z, x, y), b))
        self.assertEqual(n, len(dittobase.tile_list(m)))
        t0 = got[(0, 0, 0)]                                             # volle Auflösung, eine Kachel
        px = lambda t, x, y: t[(y * 256 + x) * 4:(y * 256 + x) * 4 + 4]
        self.assertEqual((px(t0, 5, 5), px(t0, 40, 5), px(t0, 70, 40), px(t0, 100, 40), px(t0, 5, 40)),
                         (red, blue, red, blue, bytes(4)))
        t1 = got[(1, 0, 0)]                                              # doppelt so groß
        self.assertEqual((px(t1, 70, 10), px(t1, 130, 70), px(t1, 200, 70)), (blue, red, blue))
        self.assertEqual(px(got[(-1, 0, 0)], 20, 5), blue)              # halb so groß
        self.assertEqual(dittobase.tile(m, 0, 0, 0), ("db/crystal/0/0-0.png", None))
        self.assertIsNone(dittobase.tile(m, 0, 1, 0))
        self.assertEqual(dittobase.parse(None, "crystal"), (None, None))
        # Texte: Pokémon-Namen werden in der Datenbank übersetzt
        r = _mg.merge(m, None, {"Onix": "Onix", "Rattata": "Rattfratz", "Potion": "Trank"})
        texts = {p["name"]: p for p in r["punkte"]}
        self.assertIn("Rattfratz Lv. 4–6", texts["Erfundenweg"]["text"])
        self.assertEqual((texts["Trank"]["q"], texts["Trank"].get("en")), (["DittoBase"], "Potion"))

    def test_0_38_0_ign_abfrage(self):
        from app import ign as _ign
        nd = {"props": {"pageProps": {"page": {"map": {
            "width": 0.5, "height": 1, "minZoom": 2, "maxZoom": 3, "mapName": "Erfunden", "mapSlug": "karte", "objectSlug": "spiel",
            "tilesets": ["https://oyster.ignimgs.com/ignmedia/wikimaps/spiel/karte/{z}/{x}-{y}.jpg"],
            "types": [{"typeSlug": "location", "typeName": "Location", "markers": [
                {"id": 1, "lat": -0.25, "lng": 0.25, "markerName": "Erfundenstadt"}]},
                {"typeSlug": "technical-machine", "typeName": "TM", "markers": []}]}}}}}
        page = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(nd)}</script></html>'
        g = _ign.parse(page, "galar")
        q = _ign.query(g)
        self.assertEqual(q["variables"], {"objectSlug": "spiel", "mapSlug": "karte", "typeSlugs": ["location", "technical-machine"]})
        self.assertIn("markersMultiple(objectSlug: $objectSlug", q["query"])
        answer = json.dumps({"data": {"markersMultiple": [
            {"id": 1, "lat": -0.25, "lng": 0.25, "markerName": "Erfundenstadt", "typeSlug": "location"},
            {"id": 2, "lat": -0.5, "lng": 0.1, "markerName": "TM01", "typeSlug": "technical-machine"},
            {"id": 3, "lat": None, "lng": 0.1, "markerName": "kaputt", "typeSlug": "technical-machine"}]}})
        more = _ign.markers(answer)
        self.assertEqual(len(more), 2)
        g2 = _ign.parse(page, "galar", more)
        self.assertEqual(sorted(o[4] for o in g2["orte"]), ["Erfundenstadt", "TM01"])      # gleiche id nur einmal
        self.assertIn("TMs", [c["titel"] for x in g2["gruppen"] for c in x["kategorien"]])
        self.assertEqual(_ign.markers("kein JSON"), [])
        self.assertIsNone(_ign.query(None))

    def test_0_37_1_kachelmuster_schnell(self):
        import time
        from app import abruf
        page = ("A" * 200_000 + " ") * 30 + 'x "https://a.example/tiles/{z}/{x}/{y}.png" ' + "B" * 100_000
        t = time.monotonic()
        self.assertEqual(abruf.tile_patterns(page), ["https://a.example/tiles/{z}/{x}/{y}.png"])
        self.assertLess(time.monotonic() - t, 1)          # das alte Muster brauchte für so eine Seite Stunden
        self.assertEqual(abruf.tile_patterns("nichts"), [])

    def test_0_37_0_auftraege(self):
        import sqlite3
        from app import bisafans
        page = ("<ul><li><a href='#n1'>Nebenmission 1: Ein Testauftrag</a></li></ul>"
                "<h3>Nebenmission 1: Ein Testauftrag</h3><ul><li><b>Beschreibung:</b> Jemand will ein <a>Bidiza</a> sehen.</li>"
                "<li><b>Aufgabe:</b> Ein Bidiza zeigen</li><li><b>Wo:</b> <a>Jubeldorf</a></li>"
                "<li><b>Lösung:</b> Bidiza lebt im Grasland, Bidifas auch.</li><li><b>Belohnung:</b> 3x Trank</li></ul><hr>"
                "<h3>Nebenmission 2 – Zweiter Auftrag</h3><table><tr><td>Aufgabe</td><td>Etwas tun</td></tr>"
                "<tr><td>Belohnung</td><td>10x Pokéball</td></tr><tr><td>2x Trank</td></tr></table>"
                "<footer>Impressum &amp; mehr</footer>")
        rows = bisafans.la_requests(page)
        self.assertEqual([r["nr"] for r in rows], [1, 2])
        self.assertEqual(rows[0], {"nr": 1, "name": "Ein Testauftrag", "beschreibung": "Jemand will ein Bidiza sehen.",
                                   "aufgabe": "Ein Bidiza zeigen", "ort": "Jubeldorf",
                                   "loesung": "Bidiza lebt im Grasland, Bidifas auch.", "belohnung": "3x Trank"})
        self.assertEqual(rows[1]["belohnung"], "10x Pokéball 2x Trank")            # Fußzeile gehört nicht dazu
        self.assertEqual(bisafans.la_requests(""), [])
        con = sqlite3.connect(":memory:")
        importer.import_csv(con, "pokemon_species_names",
                            "pokemon_species_id,local_language_id,name\n399,6,Bidiza\n400,6,Bidifas\n25,6,Pikachu\n")
        con.execute("CREATE TABLE spiel (id INTEGER, kennung TEXT)")
        con.execute("INSERT INTO spiel VALUES (24, 'legends-arceus')")
        con.execute("CREATE TABLE form (id INTEGER, art INTEGER)")
        con.executemany("INSERT INTO form VALUES (?, ?)", [(399, 399), (400, 400), (25, 25)])
        con.execute("CREATE TABLE spiel_form (spiel INTEGER, form INTEGER, nr INTEGER)")
        con.executemany("INSERT INTO spiel_form VALUES (24, ?, 1)", [(399,), (400,)])
        self.assertEqual(importer._derive_auftrag(con, {"la_auftraege": rows}), 2)
        arten = con.execute("SELECT arten FROM auftrag WHERE nr = 1").fetchone()[0]
        self.assertEqual(json.loads(arten), [399, 400])                          # Aufgabe zuerst, dann Lösung
        self.assertEqual(importer._derive_auftrag(sqlite3.connect(":memory:"), None), 0)
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

    def test_mapgenie_eine_datenbank(self):
        from app import mapgenie
        # erfundene Karte: ein Geisterlicht, ein Beerenbaum, ein Erzbrocken und ein Ort ohne Gegenstück
        m = {"gruppen": [{"id": 1, "titel": "Collectibles", "farbe": "#aa0000", "kategorien": [{"id": 10, "titel": "Wisp", "n": 1}]},
                         {"id": 2, "titel": "Materials", "farbe": "#00aa00", "kategorien": [{"id": 20, "titel": "Oran Berry", "n": 1},
                                                                                             {"id": 21, "titel": "Tumblestone", "n": 1}]},
                         {"id": 3, "titel": "Locations", "farbe": "#0000aa", "kategorien": [{"id": 30, "titel": "Cave", "n": 1}]}],
                "orte": [[1, 10, 0.5, 0.5, "Wisp #1", "Text"], [2, 20, 0.6, 0.6, "Oran Berry Tree", ""],
                         [3, 21, 0.7, 0.7, "Tumblestone", ""], [4, 30, 0.8, 0.8, "Höhle X", ""]]}
        de = {"Oran Berry": "Sinelbeere", "Tumblestone": "Glanzstein"}
        near = lambda la, lo, d=0.00005: (la + d, lo + d)
        ob = lambda art, la, lo, items: dict(zip(("la", "lo"), near(la, lo)), art=art, nr=None, menge="", items=items, k="gebiet", x=1.0, z=2.0)
        own = {"gebiete": {"gebiet": "Gebiet"}, "arten": {"irrlicht": ("Geisterlicht", "Geisterlichter"), "kristall": ("Kristallbrocken", "Kristallbrocken"),
                                                          "erz": ("Erzbrocken", "Erzbrocken"), "beere": ("Beerenbaum", "Beerenbäume")},
               "objekte": [ob("irrlicht", 0.5, 0.5, []), ob("beere", 0.6, 0.6, [["Sinelbeere", "100%"]]),
                           ob("erz", 0.7, 0.7, [["Glanzstein", "50%"]]), ob("kristall", 0.7, 0.7, [["Georok", "100%", 74]]),
                           ob("irrlicht", -0.5, -0.5, []), ob("erz", -0.6, -0.6, [["Seltenstein", "5%"]])],
               "punkte": [{"la": 0.1, "lo": 0.1, "alpha": False, "mons": [{"name": "Bidiza"}], "k": "gebiet"}]}
        r = mapgenie.merge(m, own, de)
        by = {p.get("id"): p for p in r["punkte"] if p.get("id")}
        self.assertEqual(by[1]["o"]["art"], "irrlicht")                       # gleiche Stelle: ein Punkt mit beidem
        self.assertEqual(by[1]["q"], ["Map Genie", "Spieldaten"])
        self.assertEqual(by[2]["o"]["items"][0][0], "Sinelbeere")            # Beere über ihr Item zugeordnet
        self.assertEqual(by[2]["name"], "Beerenbaum (Sinelbeere)")
        self.assertEqual(by[3]["drin"][0]["items"][0][0], "Georok")          # Pokémon im Erzbrocken an dieselbe Stelle
        self.assertNotIn("o", by[4])
        rest = [p for p in r["punkte"] if not p.get("id")]
        self.assertIn(10, [p["c"] for p in rest])                            # weiteres Geisterlicht: in die Ebene von Map Genie
        self.assertIn("o:erz", [p["c"] for p in rest])                       # Erz ohne Gegenstück: eigene Ebene
        self.assertIn("sp", [p["c"] for p in rest])
        titel = {g["titel"]: [c["titel"] for c in g["kategorien"]] for g in r["gruppen"]}
        self.assertEqual(titel["Sammelobjekte"], ["Geisterlichter"])
        self.assertIn("Sinelbeere", titel["Materialien und Fundstellen"])
        self.assertEqual(titel["Pokémon"], ["Spawnpunkte"])
        self.assertEqual(r["gebiete_eigen"], {"gebiet": "Gebiet"})
        self.assertEqual(sum(c["n"] for g in r["gruppen"] for c in g["kategorien"]), len(r["punkte"]))
        # ohne eigene Daten: nur übersetzt
        r = mapgenie.merge(m, None, de)
        self.assertEqual(len(r["punkte"]), 4)
        self.assertEqual(mapgenie.name_de("Wisp #12", {}), "Geisterlicht #12")
        self.assertEqual(mapgenie.name_de("Unbekannt", {}), "Unbekannt")

    def test_matchup_eigentyp(self):
        # mit gewählten Attacken zählt der Eigentyp-Bonus: Feuer-Attacke eines Wasser-Pokémon trifft Pflanze schwächer
        ctx = team.Ctx(ch())
        mk = lambda ts, at: {"id": 1, "name": "x", "typen": ts, "werte": [80] * 6, "angriffstypen": at}
        foe = {"typen": [PFLANZE]}
        a = team.matchup([mk([FEUER], [FEUER])], foe, ctx)[0]
        b = team.matchup([mk([WASSER], [FEUER])], foe, ctx)[0]
        self.assertGreater(a["austeilen"], b["austeilen"])
        self.assertTrue(any("ohne Eigentyp-Bonus" in g for g in b["gruende"]))

    def test_effort_levels(self):
        from app import effort
        # Knakrack (108/130/95/80/85/102) auf Level 100: KP 316 + Bonus 144 bei Stufe 10, Angriff 260 + 154
        self.assertEqual(effort.stat(108, 100, 10, 0), 460)
        self.assertEqual(effort.stat(130, 100, 10, 1), 414)
        self.assertEqual(effort.stat(130, 100, 0, 1), 260 + 40)
        self.assertEqual(effort.stat(130, 100, 0, 1, 1.1), 286 + 40)
        # Bestandteile für das Diagramm ergeben zusammen den Wert; Wesen − zieht ab
        for i, nat in ((0, 1.0), (1, 0.9), (3, 1.1)):
            t = effort.parts(80, 37, 6, i, nat)
            self.assertEqual(sum(t.values()), effort.stat(80, 37, 6, i, nat))
        self.assertLess(effort.parts(80, 50, 0, 1, 0.9)["wesen"], 0)
        self.assertEqual(effort.parts(80, 50, 0, 2)["el"], 0)
        self.assertEqual(effort.cost(0, 10), [3, 3, 3, 1])
        self.assertEqual(effort.cost(3, 7), [0, 3, 1, 0])
        self.assertEqual(effort.cost(5, 5), [0, 0, 0, 0])
        self.assertEqual([effort.start_level(v) for v in (31, 28, 20, 19)], [3, 2, 1, 0])
        v = effort.view([108, 130, 95, 80, 85, 102], 50, [0, 3, 0, 0, 0, 0], [10] * 6, (1, 3))
        self.assertEqual(v["bonbons"], [15, 18, 18, 6])
        self.assertEqual((v["rows"][1]["wesen"], v["rows"][3]["wesen"]), (1.1, 0.9))
        self.assertEqual(effort.view([50] * 6, 50, [5] * 6, [2] * 6)["rows"][0]["ziel"], 5)      # Ziel nie unter der Stufe
        from app import server
        d = server._details([{"el": [0, 1, 2, 3, 4, 10], "el_ziel": [0, 1, 2, 3, 4, 11]}], [445])
        self.assertEqual(d[0]["el"], [0, 1, 2, 3, 4, 10])
        self.assertNotIn("el_ziel", d[0])                                        # Stufe 11 gibt es nicht

    def test_spielwissen(self):
        import json
        from app import abfragen
        with open(abfragen.WISSEN, encoding="utf-8") as fh:
            w = json.load(fh)
        lg = w["lets-go-pikachu-lets-go-eevee"]
        self.assertEqual(len(lg["kombo"]["schillernd_kopf"]), len(lg["kombo"]["schillernd"][0]))
        self.assertIn("pika-papow", lg["partner"]["10158"])
        self.assertTrue(all(len(t) == 3 for t in lg["techniken"]["liste"]))
        self.assertTrue(all(u.startswith("https://") for _, u in lg["quellen"]))

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

    def test_verbindungstest_parallel(self):
        # alle Server gleichzeitig, jeder für sich nacheinander; Zeilen in der Reihenfolge der Abfragen, Fortschritt zählt mit
        seen = []
        def fake(url, timeout=40, encoding="", headers=None, raw=False, limit=None, data=None):
            self.assertTrue(limit)                          # jede Abfrage hat eine Gesamtzeit
            seen.append(url)
            return {"error": "", "status": 404, "server": "x", "text": "nicht da", "body": b""}
        stand, proben = {}, {}
        with mock.patch.object(sources, "request", fake), mock.patch.object(abruf, "sleep", lambda s: None):
            lines = abruf.diagnose(proben, stand)
        self.assertEqual(stand["fertig"], stand["gesamt"])
        self.assertEqual(stand["laeuft"], [])
        self.assertEqual(len(seen), stand["gesamt"])
        self.assertGreater(stand["gesamt"], 100)
        heute = lines.index("== Heutige Quellen")
        self.assertTrue(lines[heute + 1].startswith("GitHub-API, Dateiliste PokéAPI: HTTP 404"))
        self.assertFalse(any(x.endswith(": keine Antwort") for x in lines))

    def test_verbindungstest_endet_trotz_haenger(self):
        stop = threading.Event()
        def fake(url, timeout=40, encoding="", headers=None, raw=False, limit=None):
            if "types.csv" in url:
                stop.wait(30)                               # hängt, bis der Test fertig ist
            return {"error": "", "status": 404, "server": "x", "text": "", "body": b""}
        try:
            with mock.patch.object(sources, "request", fake), mock.patch.object(abruf, "sleep", lambda s: None), \
                 mock.patch.object(abruf, "DIAG_HANG", 0.3):
                lines = abruf.diagnose({}, {})
        finally:
            stop.set()
        self.assertTrue(any(x.startswith("PokéAPI, types.csv") and "hängt" in x for x in lines))
        self.assertTrue(lines[-1].startswith("Abgebrochen:"))

    def test_lesen_wartet_nicht_auf_volle_stuecke(self):
        class R:                                        # read1 gibt, was da ist; read(n) würde warten
            def __init__(self):
                self.parts = [b"a", b"b", b""]
            def read1(self, n):
                return self.parts.pop(0)
            def read(self, n):
                raise AssertionError("read statt read1")
        self.assertEqual(sources._read(R(), None), (b"ab", True))

    def test_tropfende_antwort_bricht_ab(self):
        class Slow:                                     # sendet endlos kleine Stücke, nie einen Abschluss
            def read(self, n):
                return b"x" * 10
        with mock.patch.object(sources.time, "monotonic", side_effect=[0, 1, 2, 100]):
            self.assertEqual(sources._read(Slow(), 50), (b"x" * 40, False))     # was bis dahin kam, als Teil
        class Done:
            def __init__(self):
                self.parts = [b"ab", b"cd", b""]
            def read(self, n):
                return self.parts.pop(0)
        self.assertEqual(sources._read(Done(), None), (b"abcd", True))

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

    def test_werte_alt(self):
        # frühere Basiswerte aus den Showdown-Mods: Gen 1 mit Spezial, Gen 5 erbt den Wert aus Gen 5, Gen 6 ist heute
        import sqlite3
        from app import abfragen, importer, showdown
        gen1 = "export const Pokedex = {\n\terfundon: {\n\t\tinherit: true,\n\t\tbaseStats: { hp: 40, atk: 50, def: 60, spa: 70, spd: 70, spe: 80 },\n\t},\n};"
        gen5 = "export const Pokedex = {\n\terfundon: {\n\t\tinherit: true,\n\t\tbaseStats: { hp: 40, atk: 50, def: 60, spa: 65, spd: 75, spe: 80 },\n\t},\n};"
        self.assertEqual(showdown.mod_stats(gen1)["erfundon"]["spa"], 70)
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE form (id INTEGER, kennung TEXT, kp INTEGER, ang INTEGER, vert INTEGER, spang INTEGER, spvert INTEGER, init INTEGER)")
        con.execute("INSERT INTO form VALUES (1, 'erfundon', 40, 50, 60, 85, 75, 80)")
        n = importer._derive_werte_alt(con, {1: showdown.mod_stats(gen1), 2: {}, 5: showdown.mod_stats(gen5)})
        got = {g: v for _, g, *v in con.execute("SELECT * FROM werte_alt")}
        self.assertEqual(n, 5)                                   # Gen 1, 2, 3, 4, 5; Gen 6 bis 8 wie heute
        self.assertEqual(got[1], [40, 50, 60, 70, 70, 80])
        self.assertEqual(got[3], [40, 50, 60, 65, 75, 80])
        D = type("D", (), {"stats_past": {1: got}})()
        f = {"id": 1, "werte": [40, 50, 60, 85, 75, 80], "summe": 390}
        self.assertEqual(abfragen.form_stats(D, f, 1), ([40, 50, 60, 70, 70, 80], 300))     # Spezial zählt einmal
        self.assertEqual(abfragen.form_stats(D, f, 9), (f["werte"], 390))
        con.close()

    def test_mapgenie_karte(self):
        os.makedirs(os.path.join(self.dir, "mapgenie"))
        abruf.store.save_json("mapgenie/scarlet-violet.json", {"spiel": "scarlet-violet", "am": "2026-11-11", "karten": [
            {"slug": "erfunden", "titel": "Erfunden", "kacheln": "spiel/erfunden/{z}/{x}/{y}.png", "min_zoom": 9, "max_zoom": 12, "orte": []}]})
        self.assertEqual(abruf.mg_maps("the-teal-mask")["karten"][0]["slug"], "erfunden")       # Erweiterung: Karte des Hauptspiels
        self.assertIsNone(abruf.mg_maps("red-blue"))                                              # noch nicht geladen
        from app import mapgenie as _mg
        self.assertEqual(_mg.slugs("red-blue"), ("pokemon-red-blue-yellow",))
        self.assertEqual(_mg.slugs("sword-shield"), ())                                          # gibt es dort nicht
        self.assertEqual(_mg.SHARE["yellow"], "red-blue")
        # pokemoncompletion: Karte in derselben Form, Schwester-Edition sieht sie, Kacheln zu 512 auf eigener Stufe
        from app import pkcompletion as _pc
        data = {"interactiveMap": {"dim": {"w": 2048, "h": 1024}, "cropSize": 512},
                "locations": [{"name": "Erfundenstadt", "pos": [-64, 128]}],
                "categories": [{"id": "battle", "list": [{"uid": 7, "name": "Trainer Test", "location": "Route 1", "pos": [[-32, 64], [-96, 192]]}]}]}
        m = _pc.parse(json.dumps(data), "crystal")
        self.assertEqual((m["min_zoom"], m["max_zoom"], m["kachel"]), (2, 3, 512))
        self.assertEqual(sorted(o[0] for o in m["orte"]), [7000, 7001, 10_000_000])
        x, y = _mg.project(*[o for o in m["orte"] if o[0] == 7000][0][2:4], 3)
        self.assertAlmostEqual(x, 64 * 2, places=2)            # M = 1: ein Kartenpunkt sind zwei Pixel
        self.assertAlmostEqual(y, 32 * 2, places=2)
        self.assertEqual(_pc.tile(m, 3, 3, 1)[0], "pc/crystal/1_3_1.png")
        self.assertIsNone(_pc.tile(m, 3, 4, 0))
        self.assertEqual(_pc.tile(m, 2, 1, 0)[0], "pc/crystal/2_1_0.png")
        self.assertEqual(len(_pc.tile_list(m)), 8 + 2)
        abruf.store.save_json("mapgenie/crystal.json", {"spiel": "crystal", "am": "2026-11-11", "quelle": "pokemoncompletion", "karten": [m]})
        self.assertEqual(abruf.mg_maps("gold-silver")["karten"][0]["quelle"], "pokemoncompletion")
        self.assertEqual(abruf._tile_of(m, 3, 0, 0)[1], "https://pokemonmap.b-cdn.net/crystal/1_0_0.png?v=1")
        # IGN: Einheitsquadrat auf der ganzen Welt, Kacheln {z}/{x}-{y}; Punkte aus __NEXT_DATA__
        from app import ign as _ign
        nd = {"props": {"pageProps": {"page": {"map": {
            "width": 0.5, "height": 1, "minZoom": 2, "maxZoom": 3, "mapName": "Erfunden",
            "tilesets": ["https://oyster.ignimgs.com/ignmedia/wikimaps/spiel/karte/{z}/{x}-{y}.jpg"],
            "types": [{"typeSlug": "location", "typeName": "Location", "markers": [
                {"lat": -0.25, "lng": 0.25, "markerName": "Erfundenstadt"}]}, {"typeSlug": "gym", "typeName": "Gym", "markers": []}]}}}}}
        page = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(nd)}</script></html>'
        g = _ign.parse(page, "galar")
        self.assertEqual((g["slug"], g["min_zoom"], g["max_zoom"], len(g["orte"])), ("ign-galar", 2, 3, 1))
        self.assertEqual(g["gruppen"][0]["kategorien"][0]["titel"], "Orte")
        x, y = _mg.project(g["orte"][0][2], g["orte"][0][3], 2)
        self.assertAlmostEqual(x, 0.25 * 1024, places=1)
        self.assertAlmostEqual(y, 0.25 * 1024, places=1)
        self.assertEqual(_ign.tile(g, 2, 1, 3), ("ign/galar/2/1-3.jpg", "https://oyster.ignimgs.com/ignmedia/wikimaps/spiel/karte/2/1-3.jpg"))
        self.assertIsNone(_ign.tile(g, 2, 2, 0))                 # Breite 0,5: bei Stufe 2 nur zwei Kacheln quer
        self.assertEqual(len(_ign.tile_list(g)), 2 * 4 + 4 * 8)
        self.assertIsNone(_ign.parse("<html></html>", "galar"))
        # Pokopia: eigenes Spiel ohne PokéAPI-Eintrag, Karte bei Map Genie
        import sqlite3
        from app import importer as _imp
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE versions (id INTEGER, version_group_id INTEGER, identifier TEXT)")
        con.execute('CREATE TABLE version_groups (id INTEGER, identifier TEXT, generation_id INTEGER, "order" INTEGER)')
        con.execute("INSERT INTO versions VALUES (1, 1, 'red')")
        con.execute("INSERT INTO version_groups VALUES (1, 'red-blue', 1, 1)")
        _imp._derive_spiel(con)
        self.assertEqual(con.execute("SELECT id, name, reihenfolge FROM spiel WHERE kennung = 'pokopia'").fetchone(), (1000, "Pokopia", 2))
        self.assertEqual(_mg.slugs("pokopia"), ("pokopia",))
        # mehrere Quellen je Spiel: Map Genie und IGN erscheinen zusammen
        abruf._save_maps("sword-shield", "ign", [g])
        self.assertEqual([k["slug"] for k in abruf.mg_maps("sword-shield")["karten"]], ["ign-galar"])
        f = os.path.join(self.dir, "mapgenie", "kacheln", "spiel", "erfunden", "10", "1", "2.png")
        os.makedirs(os.path.dirname(f))
        open(f, "wb").write(b"\x89PNG\r\n\x1a\n")
        self.assertEqual(abruf.mg_tile("scarlet-violet", "erfunden", 10, 1, 2), f)
        self.assertIsNone(abruf.mg_tile("scarlet-violet", "erfunden", 3, 1, 2))                   # Zoom außerhalb
        self.assertIsNone(abruf.mg_tile("scarlet-violet", "andere", 10, 1, 2))
        from app import mapgenie
        # Endung getrennt angegeben; Grenzen fehlen: aus den Orten; Kachelliste weite Stufen zuerst
        self.assertEqual(mapgenie.tile_ok("spiel/k/{z}/{x}/{y}", 9, 1, 2, "webp"), "spiel/k/9/1/2.webp")
        b = mapgenie.bounds_of({"orte": [[1, 1, 0.5, -0.5, "", ""], [2, 1, 1.0, -0.2, "", ""]]})
        self.assertTrue(b[0] < -0.5 and b[1] < 0.5 and b[2] > -0.2 and b[3] > 1.0)
        ts = mapgenie.tile_list({"bounds": [-1.4, 0, 0, 1.4], "min_zoom": 9, "max_zoom": 12}, 11)
        self.assertEqual((ts[0][0], ts[-1][0], len(ts)), (9, 11, 4 + 16 + 64))
        self.assertEqual(mapgenie.tile_ok("za/lumiose/day-v2/{z}/{y}/{x}.jpg", 9, 1, 2), "za/lumiose/day-v2/9/2/1.jpg")
        # ein einzelnes 403 heißt „Kachel gibt es nicht“, erst viele nacheinander lassen Map Genie ruhen
        calls = []
        def deny(url, **kw):
            calls.append(url)
            raise abruf.sources.FetchError("verboten", 403)
        with mock.patch.object(abruf.sources, "fetch", deny), mock.patch.object(abruf, "MG_TILE_PAUSE", 0):
            self.assertIsNone(abruf.mg_tile("scarlet-violet", "erfunden", 10, 3, 3, pause=0))
            self.assertEqual(abruf.mg_status()["ruht"], "")
            for x in range(4, 4 + abruf.MG_403_MAX):
                abruf.mg_tile("scarlet-violet", "erfunden", 10, x, 3, pause=0)
            self.assertNotEqual(abruf.mg_status()["ruht"], "")
        abruf._mg.update(rest="", n403=0, miss=set())
        # kommt eine bekannte Kachel noch, fehlen nur Kacheln am Rand: keine Pause
        def edge(url, **kw):
            if url.endswith("/ok.png"):
                return b"\x89PNG\r\n\x1a\n"
            raise abruf.sources.FetchError("verboten", 403)
        abruf._mg["ok"] = "spiel/ok.png"
        with mock.patch.object(abruf.sources, "fetch", edge):
            for x in range(20, 20 + 2 * abruf.MG_403_MAX):
                abruf.mg_tile("scarlet-violet", "erfunden", 10, x % 1024, 5, pause=0)
            self.assertEqual(abruf.mg_status()["ruht"], "")
        abruf._mg.update(rest="", n403=0, miss=set(), ok="")
        # der Vorrat holt alle Stufen: erst bis eine unter der größten, dann die größte
        abruf.store.save_json("mapgenie/scarlet-violet.json", {"spiel": "scarlet-violet", "am": "2026-11-11", "karten": [
            {"slug": "erfunden", "titel": "Erfunden", "kacheln": "spiel/erfunden/{z}/{x}/{y}.png", "min_zoom": 9, "max_zoom": 10,
             "bounds": [-1.4, 0, 0, 1.4], "orte": []}]})
        asked = []
        with mock.patch.object(abruf, "mg_tile", lambda s, k, z, x, y, **kw: asked.append(z)), mock.patch.object(abruf, "sleep", lambda t: None):
            abruf.mg_stock()
        self.assertEqual(max(asked), 10)
        self.assertTrue(abruf.mg_status()["vorrat"]["scarlet-violet/erfunden"]["ganz"])
        # 0.39: der Stand übersteht den Neustart; ist die Karte ganz durchgesehen, fragt die Oberfläche nicht mehr nach
        self.assertIn("scarlet-violet/erfunden", abruf.store.load_json(abruf.VORRAT_FILE, {}))
        abruf._mg["vorrat"]["scarlet-violet/erfunden"]["fertig"] = True
        with mock.patch.object(abruf.sources, "fetch", deny):
            calls.clear()
            self.assertIsNone(abruf.mg_tile("scarlet-violet", "erfunden", 10, 510, 510))
            self.assertEqual(calls, [])
        abruf._mg["vorrat"].clear()
        # fehlende Kacheln (einzelnes 403) stehen mit Datum in fehlt.json; bei einer Sperre werden sie wieder vergessen
        abruf._mg.update(rest="", n403=0, miss=set(), miss_am={}, r403=[])
        with mock.patch.object(abruf.sources, "fetch", deny):
            abruf.mg_tile("scarlet-violet", "erfunden", 10, 508, 508, pause=0)
            self.assertIn("spiel/erfunden/10/508/508.png", abruf._mg["miss_am"])
            for x in range(abruf.MG_403_MAX):
                abruf.mg_tile("scarlet-violet", "erfunden", 10, 508 + x % 4, 509 + x // 4, pause=0)
        self.assertNotEqual(abruf.mg_status()["ruht"], "")
        self.assertEqual(abruf._mg["miss_am"], {})
        abruf._mg.update(rest="", n403=0, miss=set(), miss_am={}, r403=[])

    def test_0_39_0_schwester_karten(self):
        # Gold/Silber: eigene Karte von DittoBase vorn, von Kristall nur die Karten anderer Quellen
        os.makedirs(os.path.join(self.dir, "mapgenie"), exist_ok=True)

        def save(spiel, suf, slug, quelle):
            abruf.store.save_json(f"mapgenie/{spiel}{suf}.json", {"am": "2026-11-12", "karten": [
                {"slug": slug, "titel": slug, "quelle": quelle, "orte": []}]})
        save("crystal", ".pc", "pc-crystal", "pokemoncompletion")
        save("crystal", ".db", "db-crystal", "dittobase")
        self.assertEqual([k["slug"] for k in abruf.mg_maps("gold-silver")["karten"]], ["pc-crystal", "db-crystal"])
        save("gold-silver", ".db", "db-gold-silver", "dittobase")
        d = abruf.mg_maps("gold-silver")
        self.assertEqual((d["spiel"], [k["slug"] for k in d["karten"]]), ("gold-silver", ["db-gold-silver", "pc-crystal"]))
        self.assertEqual([k["slug"] for k in abruf.mg_maps("crystal")["karten"]], ["pc-crystal", "db-crystal"])
        # Item-Namen aus dem PokéWiki ohne Vorlage, auch wenn sie groß geschrieben ist
        from app import pokewiki
        self.assertEqual(pokewiki.plain("{{Item|Sinelbeere|sp=PLA}}"), "Sinelbeere")

    def test_0_40_0_auftraege_und_karte(self):
        from app import bisafans, mapgenie, abfragen as _q
        page = """<h2>Kapitel 1</h2><ul><li>Mission 1: Erfundener Anfang</li></ul>
          <h3>Mission 1: Erfundener Anfang</h3><p>Sprich mit der erfundenen Person.</p><p>Geh nach Norden.</p>
          <h3>Mission 2: Erfundene Prüfung</h3><p>Fange drei erfundene Pokémon.</p>"""
        ms = bisafans.la_missions([page, "<h3>Mission 3: Ende</h3><p>Fertig.</p>"])
        self.assertEqual([(x["nr"], x["name"], x["kapitel"]) for x in ms], [(1, "Erfundener Anfang", 1), (2, "Erfundene Prüfung", 1), (3, "Ende", 2)])
        self.assertEqual(ms[0]["text"], "Sprich mit der erfundenen Person.\nGeh nach Norden.")
        m = {"gruppen": [{"titel": "Quests", "kategorien": [{"id": 1, "titel": "Request"}, {"id": 2, "titel": "Story Mission"}]}],
             "orte": [[11, 1, 0.1, 0.1, "#5: Made Up", ""], [12, 2, 0.2, 0.2, "#2: Story", ""], [13, 1, 0.3, 0.3, "Blackboard", ""]]}
        self.assertEqual(_q.quest_points(m), {"auftrag": {5: 11}, "mission": {2: 12}})
        # Doppeltes: gleiche Pflanze dreifach an einer Stelle wird ein Punkt, Massenauftreten legen ihre Pokémon zusammen
        pts = [{"id": i, "c": 7, "la": 0.5, "lo": 0.5, "name": "Kraut", "q": ["Map Genie"]} for i in range(3)]
        pts += [{"c": "o:massen", "la": 0.1, "lo": 0.1, "name": "Massenauftreten", "o": {"art": "massen", "items": [[n, "Lv 1", 1]]}, "q": ["Spieldaten"]}
                for n in ("A", "B")]
        pts += [{"id": 9, "c": 8, "la": 0.2, "lo": 0.2, "name": "Alpha-A", "q": ["Map Genie"]}, {"id": 10, "c": 8, "la": 0.2, "lo": 0.2, "name": "Alpha-B", "q": ["Map Genie"]}]
        out = mapgenie._dedupe(pts)
        self.assertEqual(len(out), 4)
        self.assertEqual(out[0]["mal"], 3)
        self.assertEqual([i[0] for i in out[1]["o"]["items"]], ["A", "B"])

    def test_0_41_0_missionen_za(self):
        """Z-A: Nebenmissionen von BisaFans (zwei Seiten), Missionen aus dem PokéWiki, Nummern auf der Karte (erfunden)."""
        from app import bisafans, pokewiki, abfragen as _q
        p1 = "<h3>Nebenmission 1: Erfundene Suche</h3><ul><li><b>Beschreibung:</b> Etwas fehlt.</li><li><b>Aufgabe:</b> Finde es.</li>" \
             "<li><b>Wo:</b> Erfundener Platz</li><li><b>Belohnung:</b> 1x Trank</li></ul>"
        p2 = "<h3>Nebenmission 120: Erfundene Erweiterung PLZA MD</h3><ul><li><b>Aufgabe:</b> Mehr finden.</li></ul>"
        rows = bisafans.merged_requests([p1, p2])
        self.assertEqual([(r["nr"], r["name"], r["ort"]) for r in rows], [(1, "Erfundene Suche", "Erfundener Platz"), (120, "Erfundene Erweiterung", "")])
        wt = """__TOC__
== Hauptmissionen ==
{| class="spiele__table"
! Nr. !! Name !! Inhalt
|-
| 01
| <span id="A">Erfundener Anfang</span>
| Du kommst an.<br />Dann geht es los.
|-
| 02
| Erfundene Flucht
| Weg hier.
|}
== Dimensions-Missionen ==
{| class="x"
|-
| 01
| Erfundene Dimension
| Ein Ring {{tt|leuchtet|hell}}.
|}
== Nebenmissionen ==
{| class="x"
|-
| 001
| Erfundene Suche
| Etwas fehlt.
| 400 Pokédollar<br />{{Item|Trank|sp=PLZA}}
| am Anfang
|-
| 110
| Ohne Belohnung
| Text.
| | [[Datei:Bild.png]]
| später
|}"""
        za = pokewiki.za_missions(wt)
        self.assertEqual([(x["nr"], x["name"]) for x in za["haupt"]], [(1, "Erfundener Anfang"), (2, "Erfundene Flucht")])
        self.assertEqual(za["haupt"][0]["text"], "Du kommst an.\nDann geht es los.")
        self.assertEqual(za["dimension"][0]["text"], "Ein Ring leuchtet.")
        self.assertEqual(za["neben"][0]["belohnung"], "400 Pokédollar, Trank")
        self.assertEqual(za["neben"][1]["nr"], 110)
        for name, nr in (("#5: Made Up", 5), ("Side Mission 12: Made Up", 12), ("Main Mission 3 - Made Up", 3), ("12 Made Up", None)):
            self.assertEqual(_q.quest_nr(name), nr)
        self.assertEqual((_q.quest_kind("Side Missions"), _q.quest_kind("Main Mission"), _q.quest_kind("Shop")), ("auftrag", "mission", None))

    def test_0_42_0_trainer_und_blaubeer(self):
        """PokéWiki: Trainerteams (Team/Kopf, Team/Zeile) und Blaubeer-Missionen mit rowspan (erfundene Seiten)."""
        import sqlite3
        from app import pokewiki, importer
        wt = """== In den Spielen ==
{{Team/Kopf|Überschrift={{sk|FR|BG}} [[Erfundene Arena]]}}
{{Team/Zeile|Edition=FRBG|Trainerklasse=Leiter|Trainername=Erfundo|Gewinn=1400
|id1=074|lvl1=12|atk1_1=Tackle|atk1_2=[[Steinwurf]]
|id2=095|lvl2=14|item2={{Item|Tsitrubeere|sp=FRBG}}|fähigkeit2=Steinhaupt}}
</div>
{{Team/Kopf|Überschrift={{sk|Stadium}} Arena}}
{{Team/Zeile|Edition=Sta|Trainername=Erfundo|id1=074|lvl1=50}}
{{Team/Kopf|Überschrift={{sk|HG|SS}} [[Erfundene Arena]] (Rückkampf)}}
{{Team/Zeile|Edition=HGSS|Trainerklasse=Arenaleiter|Trainername=Erfundo|Rückkampf=ja|id1=076|lvl1=60}}"""
        ts = pokewiki.trainer_teams(wt, "Erfundo", "Arenaleiter")
        self.assertEqual([(t["spiele"], t["rolle"], t["rueckkampf"]) for t in ts],
                         [(["firered-leafgreen"], "Arenaleiter", False), (["heartgold-soulsilver"], "Arenaleiter", True)])
        self.assertEqual(ts[0]["titel"], "Erfundene Arena")
        self.assertEqual(ts[0]["team"][0], {"nr": 74, "lvl": 12, "item": "", "faehigkeit": "", "attacken": ["Tackle", "Steinwurf"]})
        self.assertEqual((ts[0]["team"][1]["item"], ts[0]["team"][1]["faehigkeit"]), ("Tsitrubeere", "Steinhaupt"))
        self.assertEqual(pokewiki.ed_games("DPPt"), ["diamond-pearl", "platinum"])
        self.assertEqual(pokewiki.category_members('{"query": {"categorymembers": [{"title": "A"}]}, "continue": {"cmcontinue": "x"}}'), (["A"], "x"))
        bbq = """== Blaubeer-Missionen ==
{| class="spiele__table"
! colspan="2" | Art
! Beschreibung
! Belohnung
|-
! style="x" colspan="4" | Solo-Missionen
|-
| rowspan="2" | [[Datei:Fang.png]]
| rowspan="2" | Erfundene Fang-Mission
| Fange 1 Pokémon vom Typ Normal!
| rowspan="2" | 40 BP
|-
| Fange 1 Pokémon vom Typ Feuer!
|-
! colspan="4" | Gruppen-Missionen
|-
| [[Datei:X.png]]
| Erfundene Gruppen-Mission
| Macht etwas zusammen!
| 500 BP
|}
== Verwendungszwecke ==
"""
        xs = pokewiki.bbq_missions(bbq)
        self.assertEqual([(x["bereich"], x["art"], x["text"], x["bp"]) for x in xs],
                         [("Solo-Missionen", "Erfundene Fang-Mission", "Fange 1 Pokémon vom Typ Normal!", 40),
                          ("Solo-Missionen", "Erfundene Fang-Mission", "Fange 1 Pokémon vom Typ Feuer!", 40),
                          ("Gruppen-Missionen", "Erfundene Gruppen-Mission", "Macht etwas zusammen!", 500)])
        con = sqlite3.connect(":memory:")
        self.assertEqual(importer._derive_trainer(con, ts + [dict(ts[0], spiele=["red-blue", "yellow"])]), 4)
        self.assertEqual(con.execute("SELECT spiel, level FROM trainer ORDER BY id").fetchall(),
                         [("firered-leafgreen", 14), ("heartgold-soulsilver", 60), ("red-blue", 14), ("yellow", 14)])
        self.assertEqual(importer._derive_blaubeer(con, {"blaubeer": xs}), 3)

    def test_0_48_0_pokewiki_bildkarte(self):
        """Regionen ohne Bildkarte bei Serebii: Orte aus einer PokéWiki-Vorlage, großes Bild nur bei gleichem
        Seitenverhältnis (erfundene Vorlage und Bilder), Abgleich ohne Netz."""
        from app import pokearth
        wt = """<div>Lage der Orte:</div>{{#tag:imagemap|Datei:{{fileexist|XY-Map {{PAGENAME}}.gif|XY-Map Erfunden.png}}
rect 10 20 30 40 [[Erfundstadt]]
poly 50 50 70 50 70 60 [[Route 1 (Kalos)|Route 1 (Erfund-Weg)]]
circle 100 80 5 [[Erfundhöhle]]
rect 1 1 2 2 [[Erfundstadt]]
desc none
}}
rect 0 0 9 9 [[Außerhalb]]"""
        orte = pokearth.pw_areas(wt)
        self.assertEqual([(o["name"], o["x"], o["y"], o["w"], o["h"]) for o in orte],
                         [("Erfundstadt", 10, 20, 20, 20), ("Route 1", 50, 50, 20, 10), ("Erfundhöhle", 95, 75, 10, 10)])
        small = ("https://www.pokewiki.de/images/a/ab/XY-Map_Erfunden.png", 320, 210)
        big = ("https://archives.bulbagarden.net/media/upload/a/ab/Erfunden.png", 960, 630)
        d = pokearth.pw_map(orte, small, big)
        self.assertEqual((d["bild"], d["w"], d["orte"][0]["x"], d["orte"][0]["w"]), (big[0], 960, 30, 60))
        self.assertEqual(pokearth.pw_map(orte, small, (big[0], 960, 960))["bild"], small[0])     # anderes Seitenverhältnis
        info = json.dumps({"query": {"pages": [{"title": "Datei:X", "imageinfo": [{"url": small[0], "width": 320, "height": 210}]}]}})
        self.assertEqual(pokearth.imageinfo(info), small)
        self.assertIsNone(pokearth.imageinfo(info.replace("https://www.pokewiki.de", "https://boese.example")))
        m = pokearth.parse(d, "kalos")
        self.assertEqual((m["titel"], m["bilder"][0][3:]), ("Kalos (PokéWiki)", [960, 630, "se/kalos.png"]))
        self.assertEqual([o[1] for o in m["orte"]], [1, 2, 1])
        png = b"\x89PNG\r\n\x1a\nerfunden"
        page = json.dumps({"query": {"pages": [{"title": "Vorlage:XY-Map Kalos", "revisions": [{"slots": {"main": {"content": wt}}}]}]}})

        def fake(self_, u, raw=False, absent=(), data=None):
            if "Vorlage" in u:
                return page
            if "imageinfo" in u:
                return info if "pokewiki" in u else json.dumps({"query": {"pages": [{"imageinfo": [{"url": big[0], "width": 960, "height": 630}]}]}})
            return png if u == big[0] else None
        with mock.patch.object(abruf._Source, "get", fake):
            abruf._pokearth(lambda *a: None)
        k = next(k for k in abruf.mg_maps("x-y")["karten"] if k.get("quelle") == "pokearth")
        self.assertEqual((k["slug"], len(k["orte"])), ("se-kalos", 3))
        with open(abruf.mg_image("x-y", "se-kalos", 0), "rb") as fh:
            self.assertEqual(fh.read(), png)

    def test_0_41_0_pokearth(self):
        """Serebii PokéEarth: Bildkarte der Region → Karte mit einem Bild und einem Punkt je Ort (erfundene Seite)."""
        from app import pokearth
        page = """<img border="0" src="/pokearth/erfunden.png" usemap="#erf" width="200" height="100">
          <map name="erf"><area href="/pokearth/erf/stadt.shtml" shape="rect" coords="10, 10, 20, 20" title="Erfundene Stadt">
          <area href="/pokearth/erf/route1.shtml" shape="poly" coords="30,40,50,40,50,60" title="Route 1">
          <area href="/x" shape="circle" coords="100,50,10" title="Erfundene Höhle"></map>
          <img src="https://boese.example/x.png" usemap="#b" width="5" height="5">"""
        d = pokearth.extract(page)
        self.assertEqual(d["bild"], "https://www.serebii.net/pokearth/erfunden.png")
        self.assertEqual([(o["name"], o["x"], o["y"], o["w"]) for o in d["orte"]],
                         [("Erfundene Stadt", 10, 10, 10), ("Route 1", 30, 40, 20), ("Erfundene Höhle", 90, 40, 20)])
        m = pokearth.parse(d, "johto")
        self.assertEqual(m["bilder"], [[0, 0, 0, 200, 100, "se/johto.png"]])
        self.assertEqual([o[1] for o in m["orte"]], [1, 2, 1])
        self.assertIsNone(pokearth.extract("<img src='/pokearth/x.png' width='5' height='5'>"))
        png = b"\x89PNG\r\n\x1a\nerfunden"

        def fake(self_, u, raw=False, absent=(), data=None):
            return page if u == pokearth.page_url("johto") else png if u.endswith(".png") else None
        with mock.patch.object(abruf._Source, "get", fake):
            abruf._pokearth(lambda *a: None)
        k = next(k for k in abruf.mg_maps("heartgold-soulsilver")["karten"] if k.get("quelle") == "pokearth")
        self.assertEqual(k["slug"], "se-johto")
        with open(abruf.mg_image("heartgold-soulsilver", "se-johto", 0), "rb") as fh:
            self.assertEqual(fh.read(), png)
        self.assertIsNone(abruf._tile_of(k, 1, 0, 0)[0])
        self.assertEqual(abruf.mg_maps("the-crown-tundra"), abruf.mg_maps("sword-shield"))    # Erweiterungen zeigen Galar

    def test_0_40_0_rankedboost(self):
        """RankedBoost: Seite → JSON → Orte und Ortsbilder (erfundene Daten), Abgleich ohne Netz, Bild über den Server."""
        from app import rankedboost as rb
        spiel = "lets-go-pikachu-lets-go-eevee"
        url = rb.CDN + "/wp-content/plugins/k-Pokemon/assets/cache/megamap-lets-go-pikachu-eevee-0123abcd.json"
        self.assertEqual(rb.json_url(f'<script>var u="{url}";</script>'), url)
        self.assertIsNone(rb.image_ok("https://boese.example/x.webp"))
        self.assertEqual(rb.mon_name("/sprites/mr-erfund.png"), "Mr Erfund")
        mega = {"bounds": {"x": 100, "y": 50, "w": 2000, "h": 1000}, "maps": [
            {"slug": "route-erf", "name": "Route Erfunden", "x": 300, "y": 150, "w": 200, "h": 100, "type": "route",
             "url": "/wp-content/plugins/k-Pokemon/assets/location-maps/route-erf.webp", "minLv": 3, "maxLv": 5,
             "methods": [{"l": "Grass", "s": ["/s/erfundmon.png", "/s/zweitmon.png"]}, {"l": "Surf", "s": []}]},
            {"slug": "hoehle", "name": "Erfundene Höhle", "x": 900, "y": 600, "w": 50, "h": 50, "type": "cave",
             "url": "https://boese.example/h.webp", "methods": [{"l": "Walking", "s": ["/s/drittmon.png"]}]},
            {"name": "kaputt", "x": "a"}]}
        text = json.dumps({"megaMap": json.dumps(mega)})
        m, bilder = rb.parse(rb.extract(text), spiel)
        self.assertEqual([o[4] for o in m["orte"]], ["Route Erfunden", "Erfundene Höhle"])
        self.assertEqual(m["orte"][0][5], "Gras: «Erfundmon», «Zweitmon»\nLevel 3–5")
        self.assertEqual(len(bilder), 1)                 # nur Bilder vom CDN
        self.assertEqual(bilder[0][1:], [rb.CDN + "/wp-content/plugins/k-Pokemon/assets/location-maps/route-erf.webp", 200, 100, 200, 100])
        self.assertEqual([c["titel"] for c in m["gruppen"][0]["kategorien"]], ["Orte und Routen", "Höhlen und Gebäude"])
        self.assertIsNone(rb.extract("kein json"))
        webp = b"RIFF\x10\x00\x00\x00WEBPVP8 erfunden"
        page = f'<a href="{url}">'

        def fake(self_, u, raw=False, absent=(), data=None):
            if u == rb.page_urls(spiel)[0]:
                return page
            if u == url:
                return text
            if u.endswith(".webp"):
                return webp
            return None
        with mock.patch.object(abruf._Source, "get", fake), mock.patch.object(rb, "GAMES", {spiel: rb.GAMES[spiel]}):
            abruf._rankedboost(lambda *a: None)
        d = abruf.mg_maps(spiel)
        k = next(k for k in d["karten"] if k.get("quelle") == "rankedboost")
        self.assertEqual(k["bilder"], [[0, 200, 100, 200, 100]])
        f = abruf.mg_image(spiel, k["slug"], 0)
        with open(f, "rb") as fh:
            self.assertEqual(fh.read(), webp)
        self.assertIsNone(abruf.mg_image(spiel, k["slug"], 1))
        self.assertIsNone(abruf._tile_of(k, 3, 0, 0)[0])         # keine Kacheln

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

    def test_schaden(self):
        from app import schaden
        self.assertEqual(schaden.stat(130, 50, 31, 252), 182)                  # Angriff 130, voll investiert, Level 50
        self.assertEqual(schaden.stat(95, 50, 31, 0, hp=True), 170)            # KP 95 ohne Investition
        r = schaden.rolls(50, 100, 182, 110, spread=True, stab=1.5)
        self.assertEqual((r[0], r[-1], len(r)), (69, 82, 16))                  # Flächenattacke mit Eigentyp
        self.assertEqual(schaden.rolls(50, 100, 182, 110, eff=0), [0] * 16)
        self.assertEqual(schaden.stab_of(10, [10, 3], tera=10), 2.0)           # Tera-Typ gleich eigenem Typ
        self.assertEqual(schaden.stab_of(11, [10], tera=11), 1.5)
        self.assertEqual(schaden.stab_of(10, [10], tera=11), 1.5)
        self.assertEqual(schaden.hits(170, 69, 82), (3, 3))
        c = schaden.calc(50, 100, 2, WASSER, [80, 130, 95, 80, 85, 102], [WASSER], [95, 115, 90, 80, 90, 60], [FEUER], ch(),
                         spread=True)
        self.assertEqual((c["min"], c["max"], c["eff"]), (138, 164, 2.0))
        c2 = schaden.calc(50, 100, 2, BODEN, [80, 130, 95, 80, 85, 102], [BODEN], [95, 115, 90, 80, 90, 60], [FEUER], ch(),
                          d_tera=FLUG)
        self.assertEqual((c2["max"], c2["sicher"]), (0, None))                # Tera Flug: Boden wirkt nicht
        # Fähigkeiten, Items, Wetter (0.30.0)
        m = schaden.modifiers(2, 100, "water", 2.0, "huge-power", "life-orb", "regen")
        self.assertEqual((m["wert"], m["ende"], m["wetter"], len(m["texte"])), (2.0, 1.3, 1.5, 3))
        self.assertEqual(schaden.modifiers(3, 100, "water", 1.0, "huge-power", "expert-belt")["texte"], [])   # Kraftkoloss nur physisch, Gurt nur sehr effektiv
        self.assertEqual(schaden.modifiers(2, 60, "normal", 1.0, "technician", "silk-scarf")["staerke"], 1.5 * 1.2)
        self.assertEqual(schaden.modifiers(2, 60, "normal", 1.0, "technician", "silk-scarf", gen=3)["staerke"], 1.1)  # Techniker ab Gen. 4
        self.assertEqual(schaden.modifiers(2, 90, "fire", 1.0, "adaptability")["stab"], 2.0)
        c3 = schaden.calc(50, 100, 2, WASSER, [80, 130, 95, 80, 85, 102], [WASSER], [95, 115, 90, 80, 90, 60], [FEUER], ch(),
                          spread=True, mods=schaden.modifiers(2, 100, "water", 2.0, None, "life-orb", "regen"))
        self.assertGreater(c3["min"], c["min"] * 1.9)
        self.assertEqual(schaden.calc(50, 100, 2, BODEN, [80, 130, 95, 80, 85, 102], [BODEN], [95, 115, 90, 80, 90, 60], [FEUER], ch(),
                                      d_mod=0)["max"], 0)                     # Schwebe
        # Generation 1 und 2: DV, Stat Exp (Wurzel bei 255 gekappt), Zufall 217 bis 255
        self.assertEqual((schaden.stat_old(106, 100, hp=True), schaden.stat_old(154, 100), schaden.stat_old(250, 100, hp=True)), (415, 406, 703))
        self.assertEqual(schaden.stat_old(100, 50, 0, 0), 105)
        r1 = schaden.rolls_old(1, 50, 100, 150, 100)
        self.assertEqual((len(r1), r1[-1], r1[0]), (39, 68, 57))             # (22 · 100 · 150 / 100) / 50 + 2 = 68
        self.assertEqual(schaden.rolls_old(1, 50, 100, 150, 100, stab=1.5)[-1], 102)
        self.assertEqual(schaden.rolls_old(1, 50, 100, 150, 100, crit=True)[-1], 128)   # Gen. 1: Level doppelt (42 · 100 · 150 / 100) / 50 + 2
        self.assertEqual(schaden.rolls_old(2, 50, 100, 150, 100, crit=True)[-1], 134)   # Gen. 2: Schaden doppelt (66 · 2 + 2)
        self.assertEqual(schaden.rolls_old(1, 50, 100, 600, 400)[-1], 68)    # über 255: beide geviertelt
        self.assertEqual(schaden.rolls_old(1, 50, 100, 150, 100, effs=(2.0, 0.5))[-1], 68)
        self.assertEqual(schaden.rolls_old(1, 50, 100, 150, 100, effs=(0,)), [0] * 39)
        # Werte-Diagramm: Teile ergeben den Wert, Ziel-EVs, bis Gen. 2 DVs und Stat Exp
        v = schaden.stat_view([78, 84, 78, 109, 85, 100], 50, 9, [31] * 6, [0, 0, 0, 252, 4, 252], [0, 0, 0, 252, 4, 252], (5, 1))
        self.assertEqual([x["wert"] for x in v["rows"]], [153, 93, 98, 161, 106, 167])        # Glurak, scheu
        self.assertTrue(all(sum(x["teile"].values()) == x["wert"] for x in v["rows"]))
        self.assertEqual((v["ev_summe"], v["ev_gesamt"], v["rows"][5]["max"]), (508, 510, 167))
        v = schaden.stat_view([78, 84, 78, 109, 85, 100], 50, 9, None, None, [252, 0, 0, 0, 0, 0])
        self.assertEqual((v["rows"][0]["wert"], v["rows"][0]["wert_ziel"], v["rows"][0]["ev_ziel_teil"]), (153, 185, 32))
        v = schaden.stat_view([106, 110, 90, 154, 154, 130], 100, 1, None, [65535] * 6)
        self.assertEqual((v["rows"][0]["wert"], v["rows"][3]["wert"], v["ev_gesamt"]), (415, 406, None))
        self.assertEqual((schaden.stat_lgpe(100, 50, 31, 200), schaden.stat_lgpe(100, 50, 31, 0, hp=True)), (320, 175))
        v = schaden.stat_view([35, 55, 40, 50, 50, 90], 50, 7, None, [0, 0, 0, 0, 0, 200], None, None, lgpe=True)
        self.assertEqual((v["art"], v["ev_max"], v["ev_gesamt"], v["rows"][5]["wert"], v["rows"][5]["teile"]["ev"]), ("lgpe", 200, None, 310, 200))
        self.assertTrue(all(sum(x["teile"].values()) == x["wert"] for x in v["rows"]))
        from app import attacken
        fast = attacken.score({"staerke": 80, "klasse": 2, "genauigkeit": 100, "abkling": 3, "typ": WASSER}, {"typen": [], "ang": 1, "spang": 1})
        slow = attacken.score({"staerke": 80, "klasse": 2, "genauigkeit": 100, "abkling": 14, "typ": WASSER}, {"typen": [], "ang": 1, "spang": 1})
        self.assertGreater(fast[0], slow[0])
        self.assertTrue(any("Abklingzeit 3 s" in w for w in fast[1]))
        self.assertEqual(schaden.calc(50, 100, 2, WASSER, [80, 130, 95, 80, 85, 102], [WASSER], [95, 115, 90, 80, 90, 60], [FEUER], ch(),
                                      a_stat=100, d_stats=(100, 300))["kp"], 300)
        o = schaden.calc_old(1, 50, 90, 3, PSYCHO, [106, 110, 90, 154, 154, 130], [PSYCHO], [250, 5, 5, 105, 105, 50], [NORMAL], ch())
        self.assertEqual((o["angriff"], o["verteidigung"], o["kp"]), (schaden.stat_old(154, 50), schaden.stat_old(105, 50, exp=0), schaden.stat_old(250, 50, exp=0, hp=True)))
        self.assertEqual(o["stab"], 1.5)

    def test_serebii(self):
        import sqlite3
        from app import importer as _imp, serebii
        za = ('<table><tr><td>Name</td><td>Type</td><td>Cat</td><td>Cooldown</td><td>Base Power</td><td>Effect</td></tr>'
              '<tr><td class="fooinfo"><a href="/attackdex-sv/aquajet.shtml">Aqua Jet</a></td><td><img src="/pokedex-bw/type/water.gif"></td>'
              '<td><img src="/pokedex-bw/type/physical.png"></td><td>3</td><td>30</td><td>Hits 2 times in 10 seconds.</td></tr>'
              '<tr><td><a href="https://www.serebii.net/attackdex-sv/acidarmor.shtml">Acid Armor</a></td><td><img src="/pokedex-bw/type/poison.gif"></td>'
              '<td><img src="/pokedex-bw/type/other.png"></td><td>9</td><td>--</td><td>Raises Defense.</td></tr></table>'
              '<a href="/attackdex-sv/">Gen 9 Attackdex</a>')
        m = serebii.za_cooldowns(za)
        self.assertEqual(m["aquajet"], {"name": "Aqua Jet", "abkling": 3, "staerke": 30, "typ": "water", "klasse": "physical"})
        self.assertEqual((m["acidarmor"]["abkling"], m["acidarmor"]["staerke"]), (9, None))
        self.assertEqual(len(m), 2)
        pk = ('<style>a{color:#507C36}</style><table><tr><td>No.</td><td>Pic</td><td>Name</td><td>Specialty</td></tr>'
              '<tr><td class="cen">#001</td><td><a href="/pokemonpokopia/pokedex/bulbasaur.shtml"><img src="/pokemonpokopia/pokemon/small/001.png"></a></td>'
              '<td><a href="/pokemonpokopia/pokedex/bulbasaur.shtml">Bulbasaur</a></td><td><table><tr><td><img src="/pokemonpokopia/pokedex/specialty/grow.png"></td>'
              '<td><a href="/pokemonpokopia/pokedex/specialty/grow.shtml">Grow</a></td></tr></table></td></tr>'
              '<tr><td class="cen">#079</td><td><img src="/pokemonpokopia/pokemon/small/025-peakychu.png"></td>'
              '<td><a href="/pokemonpokopia/pokedex/peakychu.shtml">Peakychu</a></td><td><a href="/pokemonpokopia/pokedex/specialty/generate.shtml">Generate</a>'
              '<a href="/pokemonpokopia/pokedex/specialty/litter.shtml">Litter</a></td></tr></table>')
        rows = serebii.pokopia_dex(pk)
        self.assertEqual([(r["nr"], r["national"], r["form"], r["name"], r["spezial"]) for r in rows],
                         [(1, 1, "", "Bulbasaur", ["grow"]), (79, 25, "peakychu", "Peakychu", ["generate", "litter"])])
        self.assertEqual((serebii.spezial_de("grow"), serebii.spezial_de("neu-art")), ("Wachsen lassen", "Neu Art"))
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE attacke (id INTEGER, kennung TEXT)")
        con.execute("INSERT INTO attacke VALUES (453, 'aqua-jet'), (151, 'acid-armor')")
        con.execute("CREATE TABLE spiel (id INTEGER, kennung TEXT)")
        con.execute("INSERT INTO spiel VALUES (1000, 'pokopia')")
        con.execute("CREATE TABLE form (id INTEGER, art INTEGER, kennung TEXT, standard INTEGER)")
        con.execute("INSERT INTO form VALUES (1, 1, 'bulbasaur', 1), (25, 25, 'pikachu', 1)")
        con.execute("CREATE TABLE spiel_form (spiel INTEGER, form INTEGER, nr INTEGER, dex INTEGER DEFAULT 0, dexk TEXT DEFAULT '', PRIMARY KEY (spiel, form))")
        con.execute("CREATE TABLE attacke_spiel (spiel TEXT, attacke INTEGER, staerke INTEGER, kraft INTEGER, tempo INTEGER, "
                    "genauigkeit INTEGER, ap INTEGER, abklingzeit INTEGER, PRIMARY KEY (spiel, attacke))")
        self.assertEqual(_imp._derive_serebii(con, {"za": m, "pokopia": {"haupt": rows}}), (2, 2))
        self.assertEqual(con.execute("SELECT attacke, abklingzeit FROM attacke_spiel ORDER BY attacke").fetchall(), [(151, 9), (453, 3)])
        self.assertEqual(con.execute("SELECT form, nr FROM spiel_form ORDER BY nr").fetchall(), [(1, 1), (25, 79)])
        self.assertEqual(con.execute("SELECT name, spezial FROM pokopia WHERE nr = 79").fetchone(), ("Peakychu", '["generate", "litter"]'))

    def test_0_43_0_karten_dex_und_routentrainer(self):
        """Kartenpunkte eindeutschen und Bilder herauslösen, Nummer je Regional-Dex, Trainer von Ortsseiten (erfunden)."""
        import sqlite3
        from app import pokewiki, mapgenie, abfragen
        de = {"Potion": "Trank", "Fakemon": "Erfundemon"}
        self.assertEqual(mapgenie.text_de("Find a Potion near [Potion](https://x.test/Potion)", de),
                         "Find a Trank near [Trank](https://x.test/Potion)")
        mons, items = {"Erfundemon": 9001, "Zweitmon": 9002}, {"Supertrank": 26}
        pk, it, rest = abfragen.point_pics("**Zu Fuß:**\nErfundemon (Lv. 5), Zweitmon\nHier liegt ein Supertrank.", "",
                                           mons, abfragen.names_rx(mons, True), items, abfragen.names_rx(items))
        self.assertEqual([(x[0], x[2], x[3]) for x in pk], [(9001, "Zu Fuß", "Lv. 5"), (9002, "Zu Fuß", "")])
        self.assertEqual((it, rest), ([[26, "Supertrank"]], "**Zu Fuß:**\nHier liegt ein Supertrank."))
        pk, it, rest = abfragen.point_pics("**Bäume:**\nErfundemon", "", mons, abfragen.names_rx(mons, True), items, None)
        self.assertEqual((len(pk), rest), (1, ""))                      # Überschrift ohne übrigen Inhalt fällt weg

        con = sqlite3.connect(":memory:")
        con.executescript("""CREATE TABLE pokemon_moves (pokemon_id INTEGER, version_group_id INTEGER);
            CREATE TABLE form (id INTEGER, art INTEGER, standard INTEGER, relevant INTEGER);
            INSERT INTO form VALUES (1, 1, 1, 1), (2, 2, 1, 1), (3, 3, 1, 1);
            CREATE TABLE spiel (id INTEGER); INSERT INTO spiel VALUES (15);
            CREATE TABLE pokedexes (id INTEGER, identifier TEXT);
            INSERT INTO pokedexes VALUES (1, 'national'), (12, 'kalos-central'), (13, 'kalos-coastal');
            CREATE TABLE pokedex_version_groups (pokedex_id INTEGER, version_group_id INTEGER);
            INSERT INTO pokedex_version_groups VALUES (1, 15), (12, 15), (13, 15);
            CREATE TABLE pokemon_dex_numbers (species_id INTEGER, pokedex_id INTEGER, pokedex_number INTEGER);
            INSERT INTO pokemon_dex_numbers VALUES (1, 1, 1), (2, 1, 2), (3, 1, 3), (1, 12, 80), (1, 13, 5), (2, 13, 7);""")
        importer._derive_spiel_form(con)
        self.assertEqual(con.execute("SELECT form, nr, dex, dexk FROM spiel_form ORDER BY form").fetchall(),
                         [(1, 80, 0, ""), (2, 7, 1, "K")])                # erst der erste Dex, sonst Kürzel; 3 fehlt im Spiel

        wt = """==== Trainer ====
{{Team/Kopf|Überschrift=Trainer}}
{{Team/Zeile|Edition=FRBG|Trainerklasse=Käfersammler|Trainername=Käfersammler|Name=Erfo|id1=010|lvl1=6|id2=013|lvl2=6}}
{{Team/Zeile|Edition=FRBG|Trainerklasse=Arenaleiter|Trainername=Arenaleiter|Name=Erfundo|id1=074|lvl1=12}}"""
        ts = pokewiki.trainer_teams(wt, "Route 99 (Erfunden)", pokewiki.ORT_ROLLE)
        self.assertEqual([(t["name"], t["rolle"], t["titel"]) for t in ts],
                         [("Käfersammler Erfo", "Trainer", "Route 99 (Erfunden)"), ("Arenaleiter Erfundo", "Arenaleiter", "Route 99 (Erfunden)")])
        own = pokewiki.trainer_teams("""{{Team/Kopf|Überschrift=Arena}}
{{Team/Zeile|Edition=FRBG|Trainerklasse=Arenaleiter|Trainername=Erfundo|id1=074|lvl1=12}}""", "Erfundo", "Arenaleiter")
        both = pokewiki.dedupe_teams(ts + own)
        self.assertEqual([t["name"] for t in both], ["Erfundo", "Käfersammler Erfo"])   # die Trainerseite gilt
        self.assertNotIn("seite_rolle", both[0])

    def test_0_44_0_ironmon_und_raidnester(self):
        """HGSS-Weltkarte (TypeScript-Punkte, WebP-Kopf, Kacheln aus dem Browser) und Raid-Nester (erfundene Daten)."""
        import base64
        from app import ironmon, raidnester
        ts = """export const trainers = [
  // Rt 30
  {
    name: "Bug Catcher Erfo",
    numPokemon: 2,
    pokemonLevels: [3, 6],
    x: 700,
    y: 400,
  },
  // {
  //   name: "Lass Alt",
  //   x: 0,
  // },
  // Erfundener Turm
  // 2F
  {
    name: "Sage Testo",
    pokemonLevels: [9],
    x: 900,
    y: 300,
    tooltipPosition: TooltipPosition.Bottom,
  },
];"""
        tr = ironmon.objects(ts)
        self.assertEqual([(t["name"], t["ort"], t["teil"], t["pokemonLevels"]) for t in tr],
                         [("Bug Catcher Erfo", "Rt 30", "", [3, 6]), ("Sage Testo", "Erfundener Turm", "2F", [9])])
        it = ironmon.objects("  // Rt 30\n  {\n    x: 710,\n    y: 410,\n    type: ItemType.Hidden,\n  },")
        self.assertEqual(it[0]["type"], "Hidden")
        self.assertEqual((ironmon.trainer_name("Bug Catcher Erfo"), ironmon.trainer_name("Unbekannt X")), ("Käfersammler Erfo", "Unbekannt X"))
        head = b"RIFF\0\0\0\0WEBPVP8X\x0a\0\0\0\0\0\0\0" + (1999).to_bytes(3, "little") + (999).to_bytes(3, "little")
        self.assertEqual(ironmon.webp_size(head), (2000, 1000))
        m = ironmon.parse("johto", 2000, 1000, tr, it)
        self.assertEqual((m["bild_z"], m["min_zoom"], m["max_zoom"]), (3, 0, 3))
        self.assertEqual(sorted(o[4] for o in m["orte"] if o[1] == 1), ["Erfundener Turm", "Route 30"])
        self.assertIn("**Pokémon:** 2, Level 3, 6", next(o[5] for o in m["orte"] if o[4] == "Käfersammler Erfo"))
        self.assertEqual((ironmon.tile_range(m, 3), ironmon.tile_range(m, 1), ironmon.tile_range(m, 4)), ((8, 4), (2, 1), None))
        self.assertEqual(ironmon.tile(m, 3, 7, 3), ("im/johto/3/7-3.png", None))
        self.assertIsNone(ironmon.tile(m, 3, 8, 0))
        with mock.patch.object(abruf, "_mg_map", lambda s, k: m if k == "im-johto" else None):
            png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + bytes(20)).decode()
            self.assertEqual(abruf.tile_upload({"spiel": "x", "karte": "im-johto", "kacheln": [[3, 0, 0, png]]}), {"gespeichert": 1})
            f = abruf.mg_dir("kacheln", "im", "johto", "3", "0-0.png")
            self.assertTrue(os.path.isfile(f))
            os.remove(f)
            for bad in ([[3, 9, 0, png]], [[3, 0, 0, base64.b64encode(b"GIF89a").decode()]], [["3", 0, 0, png]]):
                with self.assertRaises(ValueError):
                    abruf.tile_upload({"spiel": "x", "karte": "im-johto", "kacheln": bad})
            with self.assertRaises(ValueError):
                abruf.tile_upload({"spiel": "x", "karte": "rn-ct", "kacheln": []})
            st = abruf.tile_convert_state("x", "im-johto")
            self.assertEqual((st["fertig"], st["fehlen"], st["bild"]), (False, 32 + 8 + 2 + 1, False))

        cs = """        private static readonly string[] LocationNames =
        [
            "Erfundenes Feld",
        ];"""
        names = raidnester.location_names(cs)
        self.assertEqual(names, ["Erfundenes Feld"])
        ns = raidnester.nests("""            new NestHashDetail(0x1, 0x2, 0, 185, 977), //16 52
//            new NestHashDetail(0x1, 0x2, 0, 1, 1),
            new NestHashDetail(0x3, 0x4, 33, 500, 800),""", names)
        self.assertEqual(ns, [("wa", 185, 977, "Erfundenes Feld", 1, 2), ("ct", 500, 800, "", 3, 4)])
        self.assertEqual((raidnester.area_of(16), raidnester.area_of(17), raidnester.area_of(43)), ("wa", "ioa", "ct"))
        r = raidnester.parse(ns, "wa", 458, 1064)
        self.assertEqual((r["slug"], len(r["orte"]), r["bilder"][0][5]), ("rn-wa", 2, "rn/wa.png"))
        self.assertTrue(r["gruppen"][0]["titel"].startswith("Orte"))
        self.assertEqual(raidnester.png_size(b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR" + (458).to_bytes(4, "big") + (1064).to_bytes(4, "big")), (458, 1064))

    def test_raids_und_crypto_lesen(self):
        rec = (25).to_bytes(2, "little") + bytes([0, 0, 1, 2, 0, 35]) + b"".join(m.to_bytes(2, "little") for m in (85, 609, 0, 0)) \
            + bytes([12, 0, 3, 100]) + bytes(4)
        self.assertEqual(len(rec), 0x18)
        self.assertEqual(importer.pkhex_raids(rec + bytes(0x18), 0x18), [(25, 0, 35, 3, 11, [85, 609], 100, 2)])  # Tera 12 → Wasser (11)
        text = """internal static readonly EncounterShadow3Colo[] Shadow =
    [
        new(01, 03000, Erfunden) { Species = 296, Level = 30, Moves = new(193,116,233,238), Location = 005 }, // Erfundenmon: Peon Erfunden @ Testdorf
        new(02, 04000, First)    { Species = 153, Level = 30, Location = 003 }, // Zweitmon: Peon Zwei @ Testburg -- Hinweis
    ];"""
        self.assertEqual(importer.pkhex_shadow(text), [(1, 296, 30, [193, 116, 233, 238], 3000, "Peon Erfunden", "Testdorf"),
                                                      (2, 153, 30, [], 4000, "Peon Zwei", "Testburg")])

    def test_kampftagebuch(self):
        db.migrate()
        server.add_battle({"spiel": "champions", "ergebnis": "niederlage", "team": [1, 2], "gegner": [3, 4], "notiz": " erfunden "})
        server.add_battle({"spiel": "champions", "ergebnis": "sieg", "team": [1, 2], "gegner": [3]})
        server.add_battle({"spiel": "anderes", "ergebnis": "sieg", "gegner": [9]})
        with self.assertRaises(ValueError):
            server.add_battle({"spiel": "champions", "ergebnis": "unentschieden"})
        log = server.battle_log("champions")
        self.assertEqual((log["kaempfe"], log["siege"]), (2, 1))
        self.assertEqual(log["gegner"][0], {"id": 3, "kaempfe": 2, "siege": 1})
        self.assertEqual(log["rows"][-1]["notiz"], "erfunden")
        dump = json.loads(json.dumps(server.export()))
        self.assertEqual(len(dump["kampftagebuch"]), 3)
        server.delete_battle({"id": log["rows"][0]["id"]})
        self.assertEqual(server.battle_log("champions")["kaempfe"], 1)
        server.restore(dump)
        self.assertEqual(server.battle_log("champions")["kaempfe"], 2)
        del dump["kampftagebuch"]                       # ältere Sicherung ohne Tagebuch lässt es stehen
        server.restore(dump)
        self.assertEqual(server.battle_log("champions")["kaempfe"], 2)

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

    def test_0_22_0(self):
        from app import abfragen
        kn = abfragen.search({"spiel": "scarlet-violet", "q": "Knakrack"})["rows"][0]["id"]
        ga = abfragen.search({"spiel": "scarlet-violet", "q": "Garados"})["rows"][0]["id"]
        ev = abfragen.team_view({"spiel": "scarlet-violet", "ids": [kn, ga], "details": [{"tera": WASSER}, {}]})
        self.assertEqual([t["slot"] for t in ev["tera"]], [0])
        self.assertIn(EIS, ev["tera"][0]["weg"])          # Tera Wasser nimmt die 4-fache Eis-Schwäche
        self.assertIn(ELEKTRO, ev["tera"][0]["neu"])
        self.assertEqual(abfragen.team_view({"spiel": "legends-arceus", "ids": [kn], "details": [{"tera": WASSER}]})["tera"], [])
        erd = next(m["id"] for m in abfragen.move_list({"q": "Erdbeben"})["rows"] if m["name"] == "Erdbeben")
        r = abfragen.damage_view({"spiel": "champions", "ids": [kn], "details": [{"attacken": [erd]}], "slot": 0, "attacke": erd,
                                  "verteidiger": [kn, ga]})
        self.assertTrue(r["flaeche"])
        self.assertEqual(r["level"], 50)
        self.assertEqual(r["rows"][1]["max"], 0)          # Garados fliegt
        self.assertGreater(r["rows"][0]["max"], r["rows"][0]["min"])
        self.assertEqual(abfragen.damage_view({"spiel": "champions", "ids": [kn], "slot": 3, "attacke": erd})["rows"], [])
        # 0.30.0: Item des Platzes und Wetter zählen; Generation 1 rechnet mit eigener Formel
        lo = abfragen._calc_names(abfragen.data())["items"]
        orb = next(i for i, (k, _) in lo.items() if k == "life-orb")
        r2 = abfragen.damage_view({"spiel": "champions", "ids": [kn], "details": [{"attacken": [erd], "item": orb}], "slot": 0,
                                   "attacke": erd, "verteidiger": [kn]})
        self.assertGreater(r2["rows"][0]["max"], r["rows"][0]["max"])
        self.assertTrue(any("1,3" in x for x in r2["eingerechnet"]))
        bi = abfragen.search({"spiel": "red-blue", "q": "Bisaflor"})["rows"][0]["id"]
        rb = abfragen.damage_view({"spiel": "red-blue", "ids": [kn], "details": [{"attacken": [erd]}], "slot": 0, "attacke": erd,
                                   "verteidiger": [bi]})
        self.assertEqual((rb["gen"], len(rb["rows"])), (1, 1))
        self.assertGreater(rb["rows"][0]["max"], 0)
        # Items der Verteidiger (Gegner „mein Team“): Offensivweste, Fokusgurt
        weste = next(i for i, (k, _) in lo.items() if k == "assault-vest")
        sash = next(i for i, (k, _) in lo.items() if k == "focus-sash")
        rw = abfragen.damage_view({"spiel": "scarlet-violet", "ids": [kn], "details": [{"attacken": [erd]}], "slot": 0, "attacke": erd,
                                   "verteidiger": [kn], "verteidiger_details": [{"item": weste}]})
        self.assertNotIn("item_vert", rw["rows"][0])                            # Offensivweste hilft nicht gegen physische Attacken
        r3 = abfragen.damage_view({"spiel": "scarlet-violet", "ids": [kn], "details": [{"attacken": [erd]}], "slot": 0, "attacke": erd,
                                   "verteidiger": [kn, kn], "verteidiger_details": [{}, {"item": sash}], "level": 100, "level_vert": 5})
        self.assertEqual((r3["rows"][0]["sicher"], r3["rows"][1]["sicher"]), (1, 2))
        self.assertIn("Fokusgurt", r3["rows"][1]["item_vert"])
        # Legenden: Arceus rechnet mit Effort Levels, Let's Go mit AVs
        la = abfragen.damage_view({"spiel": "legends-arceus", "ids": [kn], "details": [{"attacken": [erd], "el": [0, 10, 0, 0, 0, 0]}], "slot": 0,
                                   "attacke": erd, "verteidiger": [kn]})
        la0 = abfragen.damage_view({"spiel": "legends-arceus", "ids": [kn], "details": [{"attacken": [erd]}], "slot": 0, "attacke": erd, "verteidiger": [kn]})
        self.assertEqual((la["art"], la["el"]), ("la", 10))
        self.assertGreater(la["rows"][0]["angriff"], la0["rows"][0]["angriff"])
        lg = abfragen.stats_view({"spiel": "lets-go-pikachu-lets-go-eevee", "id": bi, "level": 50, "evs": [200, 0, 0, 0, 0, 0]})
        self.assertEqual((lg["art"], lg["rows"][0]["ev"]), ("lgpe", 200))
        sv = abfragen.stats_view({"spiel": "scarlet-violet", "id": kn, "level": 100, "evs": [0, 252, 0, 0, 4, 252]})
        self.assertEqual((len(sv["rows"]), sv["gen"], sv["minzen"]), (6, 9, True))
        self.assertEqual(sv["rows"][1]["wert"], 359)                            # Knakrack, Angriff 130, 252 EVs, Level 100
        self.assertEqual(abfragen.stats_view({"spiel": "legends-arceus", "id": kn})["rows"], [])

    def test_0_33_0(self):
        from app import abfragen
        kn = abfragen.search({"spiel": "scarlet-violet", "q": "Knakrack"})["rows"][0]["id"]
        erd = next(m["id"] for m in abfragen.move_list({"q": "Erdbeben"})["rows"] if m["name"] == "Erdbeben")
        r = abfragen.damage_view({"spiel": "scarlet-violet", "ids": [kn], "details": [{"attacken": [erd]}], "slot": 0, "attacke": erd,
                                  "verteidiger": [kn]})
        x = r["rows"][0]
        self.assertEqual((x["staerke"], x["grund"]), (100, (22 * 100 * x["angriff"] // x["verteidigung"]) // 50 + 2))
        self.assertIn("Zufall", [f[0] for f in x["faktoren"]])
        self.assertIn("Basis 130", x["a_info"])
        # getragene Items aus der PokéAPI: Chaneira trägt in Feuerrot und Blattgrün zu 5 % ein Glücks-Ei
        ch = abfragen.search({"spiel": "firered-leafgreen", "q": "Chaneira"})["rows"][0]["id"]
        held = abfragen.detail(ch, {"spiel": "firered-leafgreen"})["getragen"]
        ei = next(h for h in held if h["item"] == "Glücks-Ei")
        self.assertEqual((ei["prozent"], ei["quelle"]), ("5 %", "PokéAPI"))

    def test_0_45_0_speicherplatz(self):
        """Speicherplatz des Datenordners: Teile nach Größe, Karten nach Quelle und Karte, Kleines als Sonstiges (erfundene Dateien)."""
        import tempfile
        with tempfile.TemporaryDirectory() as d, mock.patch.object(abruf.db, "data_dir", lambda: d):
            def put(rel, n):
                p = os.path.join(d, *rel.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as f:
                    f.write(bytes(n))
            put("pokeapi.db", 2_000_000)
            put("user.db", 5000)
            put("sync.json", 100)
            put("mapgenie/test.im.json", 300)
            put("mapgenie/kacheln/im/johto/3/0-0.png", 1_500_000)
            put("mapgenie/kacheln/im/johto/3/1-0.png", 500)
            put("mapgenie/kacheln/erfundenes-spiel/a/1-1.jpg", 40)
            r = abruf.disk_usage(force=True)
            self.assertEqual(r["gesamt"], 2_000_000 + 5000 + 100 + 300 + 1_500_500 + 40)
            self.assertEqual([t["name"] for t in r["teile"]], ["pokeapi.db", "mapgenie", "user.db", "sonst"])
            mg = r["teile"][1]
            self.assertEqual((mg["bytes"], mg["dateien"]), (1_500_840, 4))
            self.assertEqual([(t["titel"], t["bytes"]) for t in mg["teile"]],
                             [("HeartGold/SoulSilver: Weltkarten (im Browser umgewandelt)", 1_500_500),
                              ("Kartendaten (Punkte, Orte)", 300), ("Map Genie: erfundenes-spiel", 40)])
            self.assertEqual(mg["teile"][0]["teile"][0]["name"], "johto")
            self.assertIs(abruf.disk_usage(), r)            # zwischengespeichert
        abruf._disk.update(at=0.0, data=None)

    def test_0_47_0_inhalt_der_raid_nester(self):
        """Raid-Nester: Pokémon je Nest aus RaidTables.cs (erfundene Tabelle), als Bilder im Kartenpunkt."""
        from app import abfragen, raidnester
        cs = """        public readonly RaidTemplateTable[] SwordNests = {
new RaidTemplateTable(0x1, 1, new []{
new RaidTemplate(25, new[]{35u, 20u, 0u, 0u, 0u}, 1, 0, 3, 0, false, 0),
new RaidTemplate(77, new[]{0u, 0u, 0u, 0u, 10u}, 4, 1, 4, 0, 25, true, 0),
}),
new RaidTemplateTable(0x2, 1, new []{
new RaidTemplate(26, new[]{0u, 0u, 5u, 0u, 0u}, 3, 0, 3, 0, false, 0),
}),
 };
        public readonly RaidTemplateTable[] ShieldNests = {
new RaidTemplateTable(0x1, 2, new []{
new RaidTemplate(25, new[]{35u, 20u, 0u, 0u, 0u}, 1, 0, 3, 0, false, 0),
new RaidTemplate(77, new[]{0u, 0u, 0u, 0u, 10u}, 4, 1, 4, 0, 25, true, 0),
}),
new RaidTemplateTable(0x2, 2, new []{
new RaidTemplate(25, new[]{0u, 0u, 5u, 0u, 0u}, 3, 0, 3, 0, false, 0),
}),
 };
        public readonly RaidTemplateTable[] SwordNestsEvent =
        {
new RaidTemplateTable(0x1, 1, new []{
new RaidTemplate(150, new[]{0u, 0u, 0u, 0u, 1u}, 5, 0, 3, 0, false, 0),
}),
 };"""
        t = raidnester.tables(cs)
        self.assertEqual(t["sw"][1], [(25, 0, 1, 2, False), (77, 1, 5, 5, True)])
        self.assertNotIn(150, [r[0] for v in t["sw"].values() for r in v])          # Event-Tabellen zählen nicht
        names = {25: "Pikachu", 26: "Raichu", 77: "Ponita"}
        txt = raidnester.den_text(t, 1, 2, names)
        self.assertEqual(txt.split("\n"), ["**Schwert und Schild:**", "Pikachu (1–2★), Ponita (Galar-Form, 5★, Gigadynamax)",
                                           "**Schwert, seltener Strahl:**", "Raichu (3★)", "**Schild, seltener Strahl:**", "Pikachu (3★)"])
        r = raidnester.parse([("wa", 10, 20, "Erfundenes Feld", 1, 2)], "wa", 458, 1064, tabs=t, names=names)
        self.assertIn("Ponita (Galar-Form", r["orte"][0][5])
        mons = {v: k for k, v in names.items()}
        pk, _, rest = abfragen.point_pics(r["orte"][0][5], "", mons, abfragen.names_rx(mons, True), {}, None)
        self.assertEqual(pk[1], [77, "Ponita", "Schwert und Schild", "Galar-Form, 5★, Gigadynamax"])
        self.assertEqual(rest, "**Ort:** Erfundenes Feld")


if __name__ == "__main__":
    unittest.main()
