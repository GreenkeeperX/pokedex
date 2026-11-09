"""Tests ohne Netz: Rechenlogik, Leser, Abgleich mit Attrappe, Server-Hilfen. Start: python -m unittest discover -s tests"""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import abruf, attacken, db, importer, server, showdown, sources, store, team, typen
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


if __name__ == "__main__":
    unittest.main()
