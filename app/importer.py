"""pokeapi.db bauen, ohne Netz: alle PokéAPI-Tabellen 1:1, dazu aufbereitete Tabellen, Showdown und die
gepflegten Ergänzungen. Abgerufen wird in abruf.py; hier kommen nur fertige Texte an.

Aufbereitete Tabellen (deutsche Namen, Sprache 6, sonst Englisch 9):
- spiel: Editionsgruppen (Karmesin / Purpur …) mit Generation und Reihenfolge
- form: jede Form mit eigenen Werten (Typ, Basiswerte oder Fähigkeiten anders als die Standardform)
- attacke: Attacken mit deutschem Namen, Werten, Zusatzangaben und Showdown-Merkmalen
- pruefung: Abweichungen zwischen PokéAPI und Showdown für „Zu erledigen“
- fundort: Begegnungen aus den Spieldaten (PKHeX) je Spiel, Form, Gebiet und Art, mit Level und Alpha
- spawnpunkt, spawn: Spawnpunkte mit Koordinaten und wer dort bei welcher Tageszeit und welchem Wetter erscheint
"""
import csv
import io
import json
import os
import re
import sqlite3

from . import showdown

VERSION = "5"                  # erhöhen, wenn sich die aufbereiteten Tabellen ändern: dann baut der nächste Abgleich neu
DE, EN = 6, 9
_INT = re.compile(r"-?\d+")

# Ohne Liste der Pokémon-API (GitHub) holt der Abgleich wenigstens diese Dateien
NEEDED = (
    "abilities", "ability_names", "ability_flavor_text", "encounter_condition_value_map", "encounter_condition_value_prose",
    "encounter_method_prose", "encounter_methods", "encounter_slots", "encounters", "evolution_chains", "evolution_trigger_prose",
    "generations", "item_names", "items", "location_area_prose", "location_areas", "location_names", "locations", "move_changelog",
    "move_damage_class_prose", "move_flavor_text", "move_meta", "move_names", "moves", "pokedex_prose", "pokedex_version_groups",
    "pokedexes", "pokemon", "pokemon_abilities", "pokemon_dex_numbers", "pokemon_evolution", "pokemon_form_names", "pokemon_forms",
    "pokemon_move_method_prose", "pokemon_move_methods", "pokemon_moves", "pokemon_species", "pokemon_species_flavor_text",
    "pokemon_species_names", "pokemon_stats", "pokemon_types", "pokemon_types_past", "regions", "stat_names", "stats",
    "time_of_day_prose", "type_efficacy", "type_efficacy_past", "type_names", "types", "version_group_regions", "version_groups",
    "version_names", "versions",
    # Mehr Details, TM-Nummern und Items
    "egg_group_prose", "growth_rates", "item_categories", "item_flavor_text", "item_game_indices", "item_prose", "machines",
    "pokemon_egg_groups",
    # noch ungenutzt, für Wesen und Beeren
    "berries", "nature_names", "natures",
)
# Ohne diese Dateien ist die Datenbank unbrauchbar: Der Abgleich bricht ab und die alte bleibt
REQUIRED = ("pokemon", "pokemon_species", "pokemon_species_names", "pokemon_types", "pokemon_stats", "types", "type_names",
            "type_efficacy", "moves", "move_names", "pokemon_moves", "version_groups", "versions", "version_names")

# Mindestmengen für die Selbstprüfung
MIN_SPECIES, MIN_MOVES, MIN_GAMES = 1025, 900, 25


def _table_name(name):
    if not re.fullmatch(r"[a-z0-9_]+", name):
        raise ValueError(f"ungültiger Tabellenname {name!r}")
    return name


def import_csv(con, name, text):
    """Eine CSV-Datei als Tabelle; Spalten nur aus Zahlen werden INTEGER, alles andere TEXT."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return 0
    head, body = rows[0], [r for r in rows[1:] if r]
    if not all(re.fullmatch(r"[a-z0-9_]+", h) for h in head):
        raise ValueError(f"{name}: unerwartete Kopfzeile")
    width = len(head)
    body = [r + [""] * (width - len(r)) if len(r) < width else r[:width] for r in body]
    kinds = []
    for i in range(width):
        vals = [r[i] for r in body if r[i] != ""]
        kinds.append("INTEGER" if vals and all(_INT.fullmatch(v) for v in vals) else "TEXT")
    t = _table_name(name)
    cols = ", ".join(f'"{h}" {k}' for h, k in zip(head, kinds))
    con.execute(f'DROP TABLE IF EXISTS "{t}"')
    con.execute(f'CREATE TABLE "{t}" ({cols})')
    conv = [(lambda v: int(v) if v != "" else None) if k == "INTEGER" else (lambda v: v if v != "" else None) for k in kinds]
    con.executemany(f'INSERT INTO "{t}" VALUES ({", ".join("?" * width)})',
                    ([c(v) for c, v in zip(conv, r)] for r in body))
    return len(body)


def _has(con, table):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _names(con, table, key, col="name"):
    """{id: deutscher Name, sonst englischer} aus einer *_names- oder *_prose-Tabelle."""
    out = {}
    if not _has(con, table):
        return out
    for k, lang, n in con.execute(f'SELECT "{key}", local_language_id, "{col}" FROM "{table}" WHERE local_language_id IN (?, ?)', (DE, EN)):
        if n and (lang == DE or k not in out):
            out[k] = n
    return out


def _derive_spiel(con):
    vn = _names(con, "version_names", "version_id")
    groups = {}
    for vid, vg, ident in con.execute("SELECT id, version_group_id, identifier FROM versions ORDER BY id"):
        groups.setdefault(vg, []).append(vn.get(vid) or ident)
    con.execute("CREATE TABLE spiel (id INTEGER PRIMARY KEY, kennung TEXT, name TEXT, gen INTEGER, reihenfolge INTEGER)")
    con.executemany("INSERT INTO spiel VALUES (?, ?, ?, ?, ?)",
                    [(i, k, game_name(groups.get(i) or [k]), g, o)
                     for i, k, g, o in con.execute('SELECT id, identifier, generation_id, "order" FROM version_groups')])


def game_name(names):
    """„Schwert: Die Insel der Rüstung“ und „Schild: Die Insel der Rüstung“ → „Schwert / Schild: Die Insel der Rüstung“."""
    parts = [n.split(": ", 1) for n in names]
    if len(names) > 1 and all(len(p) == 2 for p in parts) and len({p[1] for p in parts}) == 1:
        return " / ".join(p[0] for p in parts) + ": " + parts[0][1]
    return " / ".join(names)


def _derive_spiel_form(con):
    """Welche Formen es in welchem Spiel gibt, mit Nummer im Regional-Dex. Grundlage: die Regional-Dexe des Spiels;
    je Art die Formen mit eigener Lernliste im Spiel, sonst die Standardform. Spiele ohne Regional-Dex
    (Colosseum, XD …): alle Formen mit Lernliste im Spiel."""
    learn = set(con.execute("SELECT DISTINCT pokemon_id, version_group_id FROM pokemon_moves"))
    forms = {}
    for fid, art, std in con.execute("SELECT id, art, standard FROM form WHERE relevant = 1"):
        forms.setdefault(art, []).append((fid, std))
    dex = {}
    if _has(con, "pokedex_version_groups") and _has(con, "pokemon_dex_numbers"):
        q = ("SELECT pvg.version_group_id, n.species_id, MIN(n.pokedex_number) FROM pokedex_version_groups pvg "
             "JOIN pokemon_dex_numbers n ON n.pokedex_id = pvg.pokedex_id JOIN pokedexes d ON d.id = pvg.pokedex_id "
             "WHERE d.identifier != 'national' GROUP BY pvg.version_group_id, n.species_id")
        for vg, sp, nr in con.execute(q):
            dex.setdefault(vg, {})[sp] = nr
    rows = []
    for vg, in con.execute("SELECT id FROM spiel"):
        species = dex.get(vg)
        if species:
            for sp, nr in species.items():
                fs = forms.get(sp) or []
                own = [f for f, _ in fs if (f, vg) in learn]
                for f in own or [f for f, std in fs if std]:
                    rows.append((vg, f, nr))
        else:
            for sp, fs in forms.items():
                for f, _ in fs:
                    if (f, vg) in learn:
                        rows.append((vg, f, None))
    con.execute("CREATE TABLE spiel_form (spiel INTEGER, form INTEGER, nr INTEGER, PRIMARY KEY (spiel, form))")
    con.executemany("INSERT OR IGNORE INTO spiel_form VALUES (?, ?, ?)", rows)


def _derive_form(con):
    """Formen mit eigenen Werten. Rein optische Formen und Formen, die sich nur im Aussehen unterscheiden
    (Gigadynamax, Pikachu mit Kappe), fallen weg: gleiche Typen, Werte und Fähigkeiten wie die Standardform."""
    species = {r[0]: r for r in con.execute(
        "SELECT id, identifier, generation_id, evolves_from_species_id, is_legendary, is_mythical, is_baby, evolution_chain_id "
        "FROM pokemon_species")}
    sname = _names(con, "pokemon_species_names", "pokemon_species_id")
    parents = {r[3] for r in species.values() if r[3]}
    types, stats, abil = {}, {}, {}
    for pid, tid, slot in con.execute("SELECT pokemon_id, type_id, slot FROM pokemon_types ORDER BY slot"):
        types.setdefault(pid, []).append(tid)
    for pid, sid, val in con.execute("SELECT pokemon_id, stat_id, base_stat FROM pokemon_stats ORDER BY stat_id"):
        if 1 <= sid <= 6:
            stats.setdefault(pid, [0] * 6)[sid - 1] = val
    for pid, aid, hidden in con.execute("SELECT pokemon_id, ability_id, is_hidden FROM pokemon_abilities ORDER BY slot"):
        abil.setdefault(pid, []).append([aid, hidden])
    form = {}           # Standardform je Pokémon: Name, Formname, Einführung, Kampfform
    fnames = {}
    if _has(con, "pokemon_form_names"):
        for fid, lang, fn, pn in con.execute("SELECT pokemon_form_id, local_language_id, form_name, pokemon_name FROM pokemon_form_names "
                                             "WHERE local_language_id IN (?, ?)", (DE, EN)):
            if lang == DE or fid not in fnames:
                fnames[fid] = (fn, pn)
    vg_gen = dict(con.execute("SELECT id, generation_id FROM version_groups"))
    if _has(con, "pokemon_forms"):
        for fid, pid, vg, battle, mega in con.execute(
                "SELECT id, pokemon_id, introduced_in_version_group_id, is_battle_only, is_mega FROM pokemon_forms WHERE is_default = 1"):
            form[pid] = (fnames.get(fid, (None, None)), vg_gen.get(vg), battle, mega)
    rows = []
    pokemon = list(con.execute("SELECT id, identifier, species_id, is_default FROM pokemon ORDER BY id"))
    default = {sp: pid for pid, _, sp, d in pokemon if d}
    for pid, ident, sp, is_def in pokemon:
        s = species.get(sp)
        if not s or pid not in types or pid not in stats:
            continue
        base = default.get(sp)
        same = (not is_def and base in types and types[pid] == types.get(base) and stats[pid] == stats.get(base)
                and sorted(a for a, _ in abil.get(pid, [])) == sorted(a for a, _ in abil.get(base, [])))
        (fname, pname), fgen, battle, mega = form.get(pid, ((None, None), None, 0, 0))
        name = sname.get(sp) or s[1]
        if not is_def:
            name = pname or (f"{name} ({fname})" if fname else f"{name} ({ident[len(s[1]) + 1:] or ident})")
        t = types[pid] + [None]
        rows.append((pid, sp, ident, name, fname if not is_def else None, t[0], t[1], *stats[pid], sum(stats[pid]),
                     max(s[2] or 0, fgen or 0), int(bool(s[4])), int(bool(s[5])), int(bool(s[6])), int(sp not in parents),
                     int(bool(is_def)), int(bool(battle)), int(bool(mega)), int(not same), json.dumps(abil.get(pid, [])), s[7]))
    con.execute("""CREATE TABLE form (id INTEGER PRIMARY KEY, art INTEGER, kennung TEXT, name TEXT, formname TEXT, typ1 INTEGER, typ2 INTEGER,
        kp INTEGER, ang INTEGER, vert INTEGER, spang INTEGER, spvert INTEGER, init INTEGER, summe INTEGER, gen INTEGER,
        legendaer INTEGER, mysterioes INTEGER, baby INTEGER, endstufe INTEGER, standard INTEGER, kampfform INTEGER, mega INTEGER,
        relevant INTEGER, faehigkeiten TEXT, kette INTEGER)""")
    con.executemany(f"INSERT INTO form VALUES ({', '.join('?' * 25)})", rows)
    con.execute("CREATE INDEX form_art ON form(art)")


# Merkmale aus Showdown, die die Attackenwertung braucht
SD_FLAGS = ("recharge", "charge", "contact", "punch", "bite", "sound", "pulse", "slicing")


def _derive_attacke(con, sd_moves):
    names = _names(con, "move_names", "move_id")
    meta = {}
    if _has(con, "move_meta"):
        for r in con.execute("SELECT move_id, min_hits, max_hits, drain, healing, crit_rate, flinch_chance FROM move_meta"):
            meta[r[0]] = r[1:]
    text = {}
    if _has(con, "move_flavor_text"):
        for mid, txt in con.execute("SELECT move_id, flavor_text FROM move_flavor_text WHERE language_id = ? ORDER BY version_group_id", (DE,)):
            text[mid] = " ".join(str(txt).split())
    rows = []
    for mid, ident, gen, typ, power, pp, acc, prio, cls, eff in con.execute(
            "SELECT id, identifier, generation_id, type_id, power, pp, accuracy, priority, damage_class_id, effect_id FROM moves"):
        if mid >= 10000:            # Z- und Dyna-Attacken der Spieldaten-Sonderfälle
            continue
        m = meta.get(mid, (None,) * 6)
        sd = sd_moves.get(showdown.sd_id(ident), {})
        flags = sorted(f for f in (sd.get("flags") or {}) if f in SD_FLAGS)
        hits = sd.get("multihit")
        rows.append((mid, ident, names.get(mid) or ident, gen, typ, power, acc, pp, prio, cls, eff,
                     m[0], m[1], m[2], m[3], m[4], m[5], json.dumps(flags), json.dumps(sd.get("selfBoosts") or {}),
                     json.dumps(hits) if hits else None, text.get(mid)))
    con.execute("""CREATE TABLE attacke (id INTEGER PRIMARY KEY, kennung TEXT, name TEXT, gen INTEGER, typ INTEGER, staerke INTEGER,
        genauigkeit INTEGER, ap INTEGER, prio INTEGER, klasse INTEGER, effekt INTEGER, min_treffer INTEGER, max_treffer INTEGER,
        entzug INTEGER, heilung INTEGER, krit INTEGER, zurueckschrecken INTEGER, merkmale TEXT, selbst TEXT, mehrfach TEXT, text TEXT)""")
    con.executemany(f"INSERT INTO attacke VALUES ({', '.join('?' * 21)})", rows)


def _sd_tables(con, sd_dex, sd_moves):
    con.execute("CREATE TABLE sd_pokemon (id TEXT PRIMARY KEY, num INTEGER, name TEXT, typen TEXT, werte TEXT)")
    con.executemany("INSERT INTO sd_pokemon VALUES (?, ?, ?, ?, ?)",
                    [(k, v.get("num"), v.get("name"), json.dumps(v.get("types") or []), json.dumps(v.get("baseStats") or {}))
                     for k, v in sd_dex.items()])
    con.execute("CREATE TABLE sd_attacke (id TEXT PRIMARY KEY, num INTEGER, name TEXT, typ TEXT, staerke INTEGER, genauigkeit INTEGER, "
                "ap INTEGER, prio INTEGER, klasse TEXT)")
    con.executemany("INSERT INTO sd_attacke VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(k, v.get("num"), v.get("name"), v.get("type"), v.get("basePower"),
                      v.get("accuracy") if isinstance(v.get("accuracy"), int) and v.get("accuracy") is not True else None,
                      v.get("pp"), v.get("priority"), v.get("category")) for k, v in sd_moves.items()])


SD_STATS = ("hp", "atk", "def", "spa", "spd", "spe")
STAT_DE = ("KP", "Angriff", "Verteidigung", "Sp.-Angriff", "Sp.-Verteidigung", "Initiative")


def _derive_pruefung(con, sd_dex, sd_moves):
    """Abweichungen zwischen PokéAPI und Showdown: Basiswerte und Typen je Form, Stärke, Genauigkeit, AP,
    Priorität und Typ je Attacke. Nur was in beiden Quellen steht, wird verglichen."""
    tname = dict(con.execute("SELECT id, identifier FROM types"))
    out = []
    for fid, ident, name, t1, t2, *st in con.execute(
            "SELECT id, kennung, name, typ1, typ2, kp, ang, vert, spang, spvert, init FROM form"):
        sd = sd_dex.get(showdown.sd_id(ident))
        if not sd:
            continue
        bs = sd.get("baseStats") or {}
        for i, k in enumerate(SD_STATS):
            if k in bs and bs[k] != st[i]:
                out.append(("form", str(fid), name, STAT_DE[i], str(st[i]), str(bs[k])))
        mine = [tname.get(t, "").lower() for t in (t1, t2) if t]
        theirs = [str(t).lower() for t in sd.get("types") or []]
        if theirs and mine != theirs:
            out.append(("form", str(fid), name, "Typen", " / ".join(mine), " / ".join(theirs)))
    for mid, ident, name, typ, power, acc, pp, prio in con.execute(
            "SELECT id, kennung, name, typ, staerke, genauigkeit, ap, prio FROM attacke"):
        sd = sd_moves.get(showdown.sd_id(ident))
        if not sd or sd.get("isNonstandard") in ("CAP", "LGPE", "Custom"):
            continue
        sacc = sd.get("accuracy")
        pairs = [("Stärke", power or 0, sd.get("basePower") or 0),
                 ("Genauigkeit", acc, None if sacc is True else sacc),
                 ("AP", pp, sd.get("pp")),
                 ("Priorität", prio, sd.get("priority")),
                 ("Typ", (tname.get(typ) or "").lower(), str(sd.get("type") or "").lower())]
        for feld, a, b in pairs:
            if b is not None and a != b:
                out.append(("attacke", str(mid), name, feld, "–" if a is None else str(a), str(b)))
    con.execute("CREATE TABLE pruefung (art TEXT, schluessel TEXT, name TEXT, feld TEXT, pokeapi TEXT, showdown TEXT)")
    con.executemany("INSERT INTO pruefung VALUES (?, ?, ?, ?, ?, ?)", out)
    return len(out)


# Arten der Begegnung in Legenden: Arceus (SlotType8a in PKHeX)
PKHEX_ART = {0: "frei", 1: "Raum-Zeit-Verzerrung", 2: "Baum oder Erzbrocken", 3: "Massenauftreten", 4: "Massives Massenauftreten",
             9: "fest (Geschenk oder einmalig)"}
FEST = 9


def pkhex_areas(data):
    """Begegnungen aus einer PKHeX-Datei encounter_la.pkl (BinLinker „la“): je Gebiet Ortsnummern (das erste ist das
    Gebiet, die übrigen die Stellen darin), Art und Plätze mit Art, Form, Level von–bis und Alpha (0 nie, 1 möglich,
    2 immer). Gibt [(orte, art, [(nr, form, min, max, alpha)])] zurück."""
    import struct
    n = struct.unpack_from("<H", data, 2)[0]
    offs = [struct.unpack_from("<I", data, 4 + 4 * i)[0] for i in range(n + 1)]
    out = []
    for i in range(n):
        a = data[offs[i]:offs[i + 1]]
        lc = a[0]
        locs = list(a[1:1 + lc])
        al = lc + 1
        al += al & 1
        kind, count, rest = a[al], a[al + 1], a[al + 2:]
        slots = []
        for k in range(count):
            e = rest[8 * k:8 * k + 8]
            slots.append((struct.unpack_from("<H", e)[0], e[2], e[4], e[5], e[3]))
        out.append((locs, kind, slots))
    return out


_STATIC = re.compile(r"new\(([^)]*)\)\s*\{([^}]*)\}")
_FIELD = re.compile(r"\b(Species|Form|Level|Location)\s*=\s*(\d+)")


def pkhex_static(text):
    """Feste Begegnungen aus einer PKHeX-Quelldatei (Encounters8a.cs, Encounters9.cs …): Geschenke, Legendäre und
    feste Pokémon. Gibt [(nr, form, level, ort)] zurück; Einträge ohne Ort fehlen."""
    out = []
    for m in _STATIC.finditer(text or ""):
        args = [int(x) for x in re.findall(r"\d+", m.group(1))]
        f = {k: int(v) for k, v in _FIELD.findall(m.group(2))}
        if len(args) >= 3:                  # new(Art, Form, Level, …) { Location = … }
            f.setdefault("Species", args[0]), f.setdefault("Form", args[1]), f.setdefault("Level", args[2])
        if "Species" in f and "Location" in f:
            out.append((f["Species"], f.get("Form", 0), f.get("Level", 0), f["Location"]))
    return out


def pkhex_names(text):
    """Ortsnamen aus einer PKHeX-Textdatei: Zeile = Ortsnummer."""
    return (text or "").lstrip("\ufeff").splitlines()


def _form_maps(con):
    """({(Art, Formnummer im Spiel): Form}, {Art: Standardform}) aus pokemon_forms (form_order) und pokemon."""
    by_form, by_art = {}, {}
    if _has(con, "pokemon_forms"):
        for art, order, pid in con.execute("SELECT p.species_id, f.form_order, f.pokemon_id FROM pokemon_forms f "
                                           "JOIN pokemon p ON p.id = f.pokemon_id ORDER BY f.form_order"):
            by_form.setdefault((int(art), int(order or 1) - 1), int(pid))
    for art, pid in con.execute("SELECT species_id, id FROM pokemon WHERE is_default = 1"):
        by_art[int(art)] = int(pid)
    return by_form, by_art


# Spawnpunkte in Legenden: Arceus (PLA-Live-Map und JS-Finder, GPL-3.0): Tageszeiten und Wetter der Tabellen
ZEITEN = ("Dawn", "Day", "Dusk", "Night")
WETTER = ("None", "Sunny", "Cloudy", "Rain", "Snow", "Drought", "Fog", "Rainstorm", "Snowstorm")


def spawn_cells(conds):
    """Tabelle eines Spawnpunkts {"Day/Rain": {Name: Gewicht}} → {(Zeit, Wetter): {Name: Anteil in %}}; „Any Time“
    und „All Weather“ gelten für alle Tageszeiten und jedes Wetter."""
    cells = {}
    for key, weights in (conds or {}).items():
        t, _, w = key.partition("/")
        for zt in (ZEITEN if t == "Any Time" else (t,)):
            for wt in (WETTER if w in ("All Weather", "") else (w,)):
                cells[(zt, wt)] = weights
    out = {}
    for cell, weights in cells.items():
        total = sum(v for k, v in weights.items() if v > 0 and k.strip() != "None")
        if total:
            out[cell] = {k: round(100 * v / total, 1) for k, v in weights.items() if v > 0 and k.strip() != "None"}
    return out


def _spawn_name(name, by_name):
    """„AlphaGrowlithe-1“ → (Art, Formnummer, Alpha) über die Kennung der PokéAPI; None, wenn unbekannt."""
    alpha = name.startswith("Alpha")
    base = name[5:] if alpha else name
    base, _, form = base.partition("-") if re.search(r"-\d+$", base) else (base, "", "")
    key = re.sub(r"[^a-z0-9]+", "-", base.strip().lower().replace("♀", "-f").replace("♂", "-m")).strip("-")
    art = by_name.get(key)
    return (art, int(form or 0), alpha) if art else None


def _derive_spawn(con, spawns):
    """spawns: {Spielkennung: {Karte: {"gebiet": Name, "punkte": Text, "plaetze": Text}}}. Tabellen spawnpunkt
    (Koordinaten) und spawn (wer an welchem Punkt bei welcher Tageszeit und welchem Wetter, Anteil in %)."""
    con.execute("CREATE TABLE spawnpunkt (spiel TEXT, karte TEXT, gebiet TEXT, nr INTEGER, name TEXT, x REAL, z REAL, alpha INTEGER)")
    con.execute("CREATE TABLE spawn (spiel TEXT, karte TEXT, gebiet TEXT, name TEXT, form INTEGER, alpha INTEGER, anteile TEXT)")
    by_form, by_art = _form_maps(con)
    by_name = dict(con.execute("SELECT identifier, id FROM pokemon_species")) if _has(con, "pokemon_species") else {}
    n = 0
    for spiel, maps in (spawns or {}).items():
        for karte, src in maps.items():
            punkte = json.loads(src.get("punkte") or "{}")
            con.executemany("INSERT INTO spawnpunkt VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            [(spiel, karte, src["gebiet"], int(k), p.get("name", ""), p["coords"][0], p["coords"][2],
                              int("alpha" in str(p.get("icon", "")))) for k, p in punkte.items() if len(p.get("coords", [])) == 3])
            for name, conds in json.loads(src.get("plaetze") or "{}").items():
                per = {}
                for (zt, wt), shares in spawn_cells(conds).items():
                    for mon, pct in shares.items():
                        per.setdefault(mon, {})[f"{zt}/{wt}"] = pct
                for mon, cells in per.items():
                    hit = _spawn_name(mon, by_name)
                    if not hit:
                        continue
                    art, form, alpha = hit
                    pid = by_form.get((art, form)) or by_art.get(art)
                    if pid:
                        con.execute("INSERT INTO spawn VALUES (?, ?, ?, ?, ?, ?, ?)",
                                    (spiel, karte, src["gebiet"], name, pid, int(alpha), json.dumps(cells, separators=(",", ":"))))
                        n += 1
    con.execute("CREATE INDEX spawn_form ON spawn(form, spiel)")
    return n


def _derive_fundort(con, pkhex):
    """pkhex: {Spielkennung: {"begegnungen": Bytes, "orte": Text, "fest": Quelltext der festen Begegnungen}}. Art und Formnummer im Spiel werden über
    pokemon_forms (form_order) zur Form der PokéAPI; ohne Treffer zählt die Standardform der Art."""
    con.execute("CREATE TABLE fundort (spiel TEXT, form INTEGER, gebiet TEXT, gebiet_nr INTEGER, stellen TEXT, art INTEGER, "
                "min INTEGER, max INTEGER, alpha INTEGER, quelle TEXT)")
    by_form, by_art = _form_maps(con)
    n = 0
    for spiel, src in (pkhex or {}).items():
        names = pkhex_names(src.get("orte"))
        name = lambda i: names[i] if 0 <= i < len(names) and names[i].strip() else f"Ort {i}"
        rows = []
        for locs, kind, slots in pkhex_areas(src.get("begegnungen") or b""):
            if not locs:
                continue
            gebiet = name(locs[0])
            stellen = json.dumps([name(x) for x in locs[1:] if name(x) != gebiet], ensure_ascii=False)
            for nr, form, lo, hi, alpha in slots:
                pid = by_form.get((nr, form)) or by_art.get(nr)
                if pid:
                    rows.append((spiel, pid, gebiet, locs[0], stellen, kind, lo, hi, alpha, "PKHeX"))
        for nr, form, level, loc in pkhex_static(src.get("fest")):
            pid = by_form.get((nr, form)) or by_art.get(nr)
            if pid:
                rows.append((spiel, pid, name(loc), loc, "[]", FEST, level, level, 0, "PKHeX"))
        con.executemany("INSERT INTO fundort VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        n += len(rows)
    con.execute("CREATE INDEX fundort_form ON fundort(form, spiel)")
    return n


TASCHEN = {1: "Items", 2: "Medizin", 3: "Bälle", 4: "Maschinen", 5: "Beeren", 6: "Briefe", 7: "Kampf-Items", 8: "Basis-Items"}
UNUSED_CATEGORY = 23
# Gleichnamige Items unterscheiden: Kennung → Zusatz zum Namen
ITEM_SUFFIX = ((re.compile(r"^la[a-z]+-ball$"), "Hisui"), (re.compile(r"--letsgo$"), "Let’s Go"), (re.compile(r"--galar$"), "Galar"),
               (re.compile(r"--pikachu$"), "Pikachu"), (re.compile(r"--eevee$"), "Evoli"))


def item_name(ident, name):
    for rx, suffix in ITEM_SUFFIX:
        if rx.search(ident or ""):
            return f"{name} ({suffix})"
    return name


def _derive_item(con):
    """Items: deutscher Name, Tasche, Beschreibung (deutsch aus dem neuesten Spiel mit deutschem Text, sonst englisch),
    die Spiele mit Beschreibung (genau: dort gibt es das Item) und die Generationen laut Spielindex der PokéAPI (grob).
    Ohne items.csv bleibt die Tabelle leer."""
    con.execute("CREATE TABLE item (id INTEGER PRIMARY KEY, kennung TEXT, name TEXT, tasche TEXT, text TEXT, sprache TEXT, "
                "preis INTEGER, gens TEXT, spiele TEXT)")
    if not _has(con, "items"):
        return 0
    names = _names(con, "item_names", "item_id")
    pockets = {}
    if _has(con, "item_categories"):
        pockets = {c: TASCHEN.get(p, "") for c, p in con.execute("SELECT id, pocket_id FROM item_categories")}
    order = {r[0]: r[1] for r in con.execute("SELECT id, reihenfolge FROM spiel")}
    texts, games = {}, {}
    if _has(con, "item_flavor_text"):
        for iid, vg, lang, txt in con.execute("SELECT item_id, version_group_id, language_id, flavor_text FROM item_flavor_text "
                                              "WHERE language_id IN (6, 9)"):
            games.setdefault(iid, set()).add(vg)
            key = (lang == 6, order.get(vg, vg or 0))
            if txt and (iid not in texts or key > texts[iid][0]):
                texts[iid] = (key, " ".join(txt.split()), "de" if lang == 6 else "en")
    if _has(con, "item_prose"):
        for iid, eff in con.execute("SELECT item_id, short_effect FROM item_prose WHERE local_language_id = 9"):
            if eff and iid not in texts:
                texts[iid] = (None, " ".join(eff.split()), "en")
    gens = {}
    if _has(con, "item_game_indices"):
        for iid, g in con.execute("SELECT item_id, generation_id FROM item_game_indices"):
            gens.setdefault(iid, set()).add(g)
    rows = []
    for iid, ident, cat, cost in con.execute("SELECT id, identifier, category_id, cost FROM items"):
        if cat == UNUSED_CATEGORY or not names.get(iid):
            continue
        t = texts.get(iid)
        rows.append((iid, ident, item_name(ident, names[iid]), pockets.get(cat, ""), t[1] if t else "", t[2] if t else "", cost or 0,
                     json.dumps(sorted(gens.get(iid, ()))), json.dumps(sorted(games.get(iid, ())))))
    con.executemany("INSERT INTO item VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


def load_extra(folder):
    """Gepflegte Ergänzungen: jede JSON-Datei in extra/ als {Name: Inhalt}. Kaputte Dateien brechen ab."""
    out = {}
    if not os.path.isdir(folder):
        return out
    for fn in sorted(os.listdir(folder)):
        if fn.endswith(".json"):
            with open(os.path.join(folder, fn), encoding="utf-8") as f:
                out[fn[:-5]] = json.load(f)
    return out


def check(con):
    """Selbstprüfung: Gründe, warum die neue Datenbank nicht gilt, sonst leere Liste."""
    why = []
    n_sp = con.execute("SELECT COUNT(DISTINCT art) FROM form").fetchone()[0]
    n_mv = con.execute("SELECT COUNT(*) FROM attacke").fetchone()[0]
    n_vg = con.execute("SELECT COUNT(*) FROM spiel").fetchone()[0]
    n_ty = con.execute("SELECT COUNT(*) FROM types WHERE id <= 18").fetchone()[0]
    if n_sp < MIN_SPECIES:
        why.append(f"nur {n_sp} Arten (erwartet mindestens {MIN_SPECIES})")
    if n_mv < MIN_MOVES:
        why.append(f"nur {n_mv} Attacken (erwartet mindestens {MIN_MOVES})")
    if n_vg < MIN_GAMES:
        why.append(f"nur {n_vg} Spiele (erwartet mindestens {MIN_GAMES})")
    if n_ty != 18:
        why.append(f"{n_ty} statt 18 Typen")
    return why


def _sd_key(text):
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _derive_moveset(con, sets):
    """Bewährte Sets (Showdown, Random Battle) je Generation: sets = {Generation: {Showdown-Kennung: {"sets": [{"role",
    "movepool", "abilities", "teraTypes"}], "level"}}}; Generation 1 hat {"moves": [...]} ohne Rolle.
    Attacken und Pokémon als Showdown-Kennung (klein, nur Buchstaben und Ziffern)."""
    con.execute("CREATE TABLE moveset (gen INTEGER, pokemon TEXT, rolle TEXT, attacken TEXT, faehigkeiten TEXT, tera TEXT, "
                "level INTEGER)")
    rows = []
    for gen, data in (sets or {}).items():
        for mon, entry in data.items():
            if not isinstance(entry, dict):
                continue
            variants = entry.get("sets") or ([{"role": "", "movepool": entry["moves"]}] if entry.get("moves") else [])
            for v in variants:
                moves = [_sd_key(m) for m in v.get("movepool") or []]
                if moves:
                    rows.append((int(gen), _sd_key(mon), v.get("role") or "", json.dumps(moves), json.dumps(v.get("abilities") or []),
                                 json.dumps(v.get("teraTypes") or []), entry.get("level")))
    con.executemany("INSERT INTO moveset VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    con.execute("CREATE INDEX moveset_pokemon ON moveset(pokemon, gen)")
    return len(rows)


def build(path, csvs, sd_texts=None, extra=None, strict=True, pkhex=None, spawns=None, sets=None):
    """Baut die Datenbank unter path (wird überschrieben). csvs: {Name: Text}; sd_texts: {"pokedex": Text,
    "moves": Text}; extra: {Name: Inhalt} aus extra/; pkhex: Begegnungen je Spiel (siehe _derive_fundort);
    spawns: Spawnpunkte je Spiel und Karte (siehe _derive_spawn).
    Gibt Zahlen zurück; mit strict wirft die Selbstprüfung."""
    missing = [n for n in REQUIRED if n not in csvs]
    if missing:
        raise ValueError("Es fehlen Dateien: " + ", ".join(missing))
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    try:
        rows = 0
        for name in sorted(csvs):
            rows += import_csv(con, name, csvs[name])
        sd_texts = sd_texts or {}
        sd_dex = showdown.pokedex(sd_texts.get("pokedex", ""))
        sd_moves = showdown.moves(sd_texts.get("moves", ""))
        _derive_spiel(con)
        _derive_form(con)
        _derive_spiel_form(con)
        _derive_attacke(con, sd_moves)
        _sd_tables(con, sd_dex, sd_moves)
        n_check = _derive_pruefung(con, sd_dex, sd_moves) if sd_dex or sd_moves else 0
        n_fund = _derive_fundort(con, pkhex)
        n_spawn = _derive_spawn(con, spawns)
        n_item = _derive_item(con)
        n_sets = _derive_moveset(con, sets)
        con.execute("CREATE TABLE extra (name TEXT PRIMARY KEY, inhalt TEXT)")
        con.executemany("INSERT INTO extra VALUES (?, ?)", [(k, json.dumps(v, ensure_ascii=False)) for k, v in (extra or {}).items()])
        for sql in ("CREATE INDEX pm_pokemon ON pokemon_moves(pokemon_id, version_group_id)",
                    "CREATE INDEX pm_move ON pokemon_moves(move_id, version_group_id)"):
            con.execute(sql)
        if _has(con, "encounters"):
            con.execute("CREATE INDEX enc_pokemon ON encounters(pokemon_id)")
        why = check(con)
        if why and strict:
            raise ValueError("Selbstprüfung: " + "; ".join(why))
        con.commit()
        stats = {"tables": len(csvs), "rows": rows,
                 "forms": con.execute("SELECT COUNT(*) FROM form WHERE relevant = 1").fetchone()[0],
                 "species": con.execute("SELECT COUNT(DISTINCT art) FROM form").fetchone()[0],
                 "moves": con.execute("SELECT COUNT(*) FROM attacke").fetchone()[0],
                 "games": con.execute("SELECT COUNT(*) FROM spiel").fetchone()[0],
                 "sd_pokemon": len(sd_dex), "sd_moves": len(sd_moves), "diff": n_check, "fundorte": n_fund, "spawns": n_spawn, "items": n_item, "sets": n_sets, "check": why}
    finally:
        con.close()
    return stats
