"""pokeapi.db bauen, ohne Netz: alle PokéAPI-Tabellen 1:1, dazu aufbereitete Tabellen, Showdown und die
gepflegten Ergänzungen. Abgerufen wird in abruf.py; hier kommen nur fertige Texte an.

Aufbereitete Tabellen (deutsche Namen, Sprache 6, sonst Englisch 9):
- spiel: Editionsgruppen (Karmesin / Purpur …) mit Generation und Reihenfolge
- form: jede Form mit eigenen Werten (Typ, Basiswerte oder Fähigkeiten anders als die Standardform)
- attacke: Attacken mit deutschem Namen, Werten, Zusatzangaben und Showdown-Merkmalen
- pruefung: Abweichungen zwischen PokéAPI und Showdown für „Zu erledigen“
- fundort: Begegnungen aus den Spieldaten (PKHeX) je Spiel, Form, Gebiet und Art, mit Level und Alpha
- spawnpunkt, spawn: Spawnpunkte mit Koordinaten und wer dort bei welcher Tageszeit und welchem Wetter erscheint
- item: Items der PokéAPI, dazu die Itemlisten von PKHeX für Spiele ohne eigene Liste (Namen aus den Spieltexten)
- kartenobjekt, rezept, zutat: Kartensymbole, Sammelobjekte und Rezepte in Legenden: Arceus (Altissimo)
"""
import csv
import io
import json
import os
import re
import sqlite3

from . import altissimo, companion, pokewiki, showdown

VERSION = "12"                 # erhöhen, wenn sich die aufbereiteten Tabellen ändern: dann baut der nächste Abgleich neu
DE, EN = 6, 9
_INT = re.compile(r"-?\d+")

# Ohne Liste der Pokémon-API (GitHub) holt der Abgleich wenigstens diese Dateien
NEEDED = (
    "abilities", "ability_names", "ability_flavor_text", "encounter_condition_value_map", "encounter_condition_value_prose",
    "encounter_method_prose", "encounter_methods", "encounter_slots", "encounters", "evolution_chains", "evolution_trigger_prose",
    "generations", "item_names", "items", "location_area_prose", "location_areas", "location_names", "locations", "move_changelog",
    "move_damage_class_prose", "move_flavor_text", "move_meta", "move_meta_stat_changes", "move_names", "moves", "pokedex_prose", "pokedex_version_groups",
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


# Kurz-Info einer Attacke aus den Metadaten der PokéAPI (Statuswirkung, Wertänderung, Heilung)
AILMENT = {1: "paralysiert", 2: "schläfert ein", 3: "friert ein", 4: "verbrennt", 5: "vergiftet", 6: "verwirrt", 7: "macht verliebt",
           8: "hält fest", 9: "Albtraum", 12: "verhindert Wiederholung", 13: "blockiert eine Attacke", 14: "macht müde (schläft nächste Runde ein)",
           15: "verhindert Heilung", 18: "Egelsamen: saugt jede Runde KP ab", 19: "verhindert Items", 20: "alle gehen in 3 Runden k. o.",
           21: "Verwurzler: heilt jede Runde"}
STAT_KURZ = {1: "KP", 2: "Angriff", 3: "Verteidigung", 4: "Sp.-Angriff", 5: "Sp.-Verteidigung", 6: "Initiative", 7: "Genauigkeit",
             8: "Fluchtwert"}
SELF_TARGETS = (3, 4, 5, 7, 13, 15)        # Ziel der Attacke: Anwender oder eigene Seite
UNUSABLE = "kann nicht eingesetzt werden"  # Beschreibung gestrichener Attacken in neueren Spielen


def move_short(cat, ailment, ail_chance, stat_chance, changes, healing, drain, target, status):
    """Kurz-Info wie „Verteidigung −1 (Gegner)“ oder „paralysiert (30 %)“; leer, wenn die Metadaten nichts hergeben.
    cat: Kategorie der PokéAPI (2 Werte ändern, 6 Schaden und Gegner senken, 7 Schaden und selbst erhöhen); changes: [(Wert, Stufen)]."""
    parts = []
    if ailment in AILMENT:
        parts.append(AILMENT[ailment] + (f" ({ail_chance} %)" if ail_chance and ail_chance < 100 else ""))
    if changes:
        self_side = cat == 7 or (cat not in (5, 6) and target in SELF_TARGETS)
        for up in (True, False):
            xs = [(STAT_KURZ.get(s, "?"), c) for s, c in changes if (c > 0) == up]
            if not xs:
                continue
            who = "Gegner" if cat == 5 or not self_side else "selbst"       # Angeberei, Schmeichler erhöhen den Gegner
            sign = "+" if up else "−"
            steps = {abs(c) for _, c in xs}
            txt = f"{', '.join(n for n, _ in xs)} {sign}{min(steps)}" if len(steps) == 1 \
                else ", ".join(f"{n} {sign}{abs(c)}" for n, c in xs)
            parts.append(f"{txt} ({who}{f', {stat_chance} %' if stat_chance and stat_chance < 100 else ''})")
    if healing and healing > 0:
        parts.append(f"heilt {healing} % der KP")
    if drain and drain > 0:
        parts.append(f"saugt {drain} % des Schadens als KP ab")
    if cat == 9:
        parts.append("K.-o.-Attacke")
    if cat == 12 and status:
        parts.append("erzwingt einen Wechsel")
    return " · ".join(parts)


def _derive_attacke(con, sd_moves, kurz_extra=None):
    kurz_extra = kurz_extra or {}
    names = _names(con, "move_names", "move_id")
    meta = {}
    if _has(con, "move_meta"):
        for r in con.execute("SELECT move_id, min_hits, max_hits, drain, healing, crit_rate, flinch_chance, meta_category_id, "
                             "meta_ailment_id, ailment_chance, stat_chance FROM move_meta"):
            meta[r[0]] = r[1:]
    changes = {}
    if _has(con, "move_meta_stat_changes"):
        for mid, stat, change in con.execute("SELECT move_id, stat_id, change FROM move_meta_stat_changes"):
            changes.setdefault(mid, []).append((stat, change))
    targets = dict(con.execute("SELECT id, target_id FROM moves"))
    text = {}
    if _has(con, "move_flavor_text"):
        # Neuester deutscher Text; „kann nicht eingesetzt werden“ (gestrichene Attacke) nur, wenn es keinen anderen gibt
        for mid, txt in con.execute("SELECT move_id, flavor_text FROM move_flavor_text WHERE language_id = ? ORDER BY version_group_id", (DE,)):
            txt = " ".join(str(txt).split())
            if UNUSABLE not in txt or mid not in text:
                text[mid] = txt
    rows = []
    for mid, ident, gen, typ, power, pp, acc, prio, cls, eff in con.execute(
            "SELECT id, identifier, generation_id, type_id, power, pp, accuracy, priority, damage_class_id, effect_id FROM moves"):
        if mid >= 10000:            # Z- und Dyna-Attacken der Spieldaten-Sonderfälle
            continue
        m = meta.get(mid, (None,) * 10)
        kurz = move_short(m[6], m[7], m[8], m[9], changes.get(mid), m[3], m[2], targets.get(mid), cls == 1) if m[6] is not None else ""
        kurz = kurz or str(kurz_extra.get(ident) or "")        # gepflegt in extra/attacken_kurz.json, wo die Metadaten nichts hergeben
        sd = sd_moves.get(showdown.sd_id(ident), {})
        flags = sorted(f for f in (sd.get("flags") or {}) if f in SD_FLAGS)
        hits = sd.get("multihit")
        rows.append((mid, ident, names.get(mid) or ident, gen, typ, power, acc, pp, prio, cls, eff,
                     m[0], m[1], m[2], m[3], m[4], m[5], json.dumps(flags), json.dumps(sd.get("selfBoosts") or {}),
                     json.dumps(hits) if hits else None, text.get(mid), kurz))
    con.execute("""CREATE TABLE attacke (id INTEGER PRIMARY KEY, kennung TEXT, name TEXT, gen INTEGER, typ INTEGER, staerke INTEGER,
        genauigkeit INTEGER, ap INTEGER, prio INTEGER, klasse INTEGER, effekt INTEGER, min_treffer INTEGER, max_treffer INTEGER,
        entzug INTEGER, heilung INTEGER, krit INTEGER, zurueckschrecken INTEGER, merkmale TEXT, selbst TEXT, mehrfach TEXT, text TEXT,
        kurz TEXT)""")
    con.executemany(f"INSERT INTO attacke VALUES ({', '.join('?' * 22)})", rows)


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
# Erweiterungen teilen die Begegnungen ihres Hauptspiels (PKHeX führt sie in einer Datei)
PKHEX_SHARE = {"scarlet-violet": ("the-teal-mask", "the-indigo-disk"), "legends-za": ("mega-dimension",)}


def pkhex_areas(data):
    """Begegnungen aus einer PKHeX-Datei, nach der Kennung am Anfang: „la“ (Legenden: Arceus), „sv“ (Karmesin/Purpur)
    oder „za“ (Legenden: Z-A). Gibt [(orte, art, [(nr, form, min, max, alpha)])] zurück; orte: das erste ist das Gebiet,
    die übrigen die Stellen darin. Alpha: 0 nie, 1 möglich, 2 immer."""
    if len(data) < 4:
        return []
    kind = data[:2]
    if kind == b"sv":
        return _areas_sv(data)
    if kind == b"za":
        return _areas_za(data)
    return _areas_la(data)


def _binlinker(data):
    """Einträge einer BinLinker-Datei (2 Byte Kennung, u16 Anzahl, u32-Offsets)."""
    import struct
    n = struct.unpack_from("<H", data, 2)[0]
    offs = [struct.unpack_from("<I", data, 4 + 4 * i)[0] for i in range(n + 1)]
    return [data[offs[i]:offs[i + 1]] for i in range(n)]


def _areas_sv(data):
    """Karmesin/Purpur (encounter_wild_paldea.pkl): Ort (Byte 0), Herkunft (Byte 2, nur bei Pokémon aus dem Nachbargebiet),
    dann Plätze zu 8 Bytes (u16 Art, Form, Geschlecht, Level von, bis, Tageszeit, Wetter). Gebiete mit Herkunft sind
    Doppel der Nachbargebiete und fallen weg."""
    import struct
    out = []
    for a in _binlinker(data):
        if a[2]:
            continue
        slots = [(struct.unpack_from("<H", a, k)[0], a[k + 2], a[k + 4], a[k + 5], 0) for k in range(4, len(a) - 7, 8)]
        out.append(([a[0]], 0, slots))
    return out


def _areas_za(data):
    """Legenden: Z-A (encounter_za.pkl, encounter_hyperspace_za.pkl; BinLinker16: u16 Anfang und Ende je Eintrag):
    Ort (u16), 2 Bytes frei, dann Plätze zu 8 Bytes (u16 Art, Form, Geschlecht, Level von, bis, Alpha, Schillernd)."""
    import struct
    n = struct.unpack_from("<H", data, 2)[0]
    out = []
    for i in range(n):
        s, e = struct.unpack_from("<HH", data, 4 + 2 * i)
        a = data[s:e]
        slots = [(struct.unpack_from("<H", a, k)[0], a[k + 2], a[k + 4], a[k + 5], 2 if a[k + 6] == 1 else 0)
                 for k in range(4, len(a) - 7, 8)]
        out.append(([struct.unpack_from("<H", a)[0]], 0, slots))
    return out


def _areas_la(data):
    """Legenden: Arceus (encounter_la.pkl): Ortsnummern, Art und Plätze mit Art, Form, Alpha und Level."""
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
        if spiel.startswith("_"):           # _items: Itemlisten, keine Begegnungen
            continue
        names, names3 = pkhex_names(src.get("orte")), pkhex_names(src.get("orte3"))

        def name(i):
            lst, k = (names3, i - 30000) if i >= 30000 else (names, i)
            return lst[k] if 0 <= k < len(lst) and lst[k].strip() else f"Ort {i}"
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
        for sp in (spiel, *PKHEX_SHARE.get(spiel, ())):
            con.executemany("INSERT INTO fundort VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(sp, *r[1:]) for r in rows])
            n += len(rows)
    con.execute("CREATE INDEX fundort_form ON fundort(form, spiel)")
    return n


TASCHEN = {1: "Items", 2: "Medizin", 3: "Bälle", 4: "Maschinen", 5: "Beeren", 6: "Briefe", 7: "Kampf-Items", 8: "Basis-Items"}
UNUSED_CATEGORY = 23
# Gleichnamige Items unterscheiden: Kennung → Zusatz zum Namen
ITEM_SUFFIX = ((re.compile(r"^la[a-z]+-ball$"), "Hisui"), (re.compile(r"--letsgo$"), "Let’s Go"), (re.compile(r"--galar$"), "Galar"),
               (re.compile(r"--pikachu$"), "Pikachu"), (re.compile(r"--eevee$"), "Evoli"))


# Art eines Items: Kategorie der PokéAPI auf Deutsch
ITEM_ART = {1: "Kampf-Verstärker", 2: "FP senken", 3: "Medizin", 4: "Sonstige Beere", 5: "Beere für die Not", 6: "Heilbeere mit Geschmack",
            7: "Beere gegen Typ", 8: "Backzutat", 9: "Sammelstück", 10: "Entwicklung", 11: "Erkundung", 12: "Getragenes Item",
            13: "Wahl-Item", 14: "FP-Training", 15: "Getragenes Item mit Nachteil", 16: "Training", 17: "Tafel", 18: "Nur für eine Art",
            19: "Typ-Verstärker", 20: "Ereignis", 21: "Spielablauf", 22: "Handlung", 24: "Wertsache", 25: "Brief", 26: "Nährstoff",
            27: "Heilung", 28: "AP-Heilung", 29: "Beleber", 30: "Statusheilung", 32: "Mulch", 33: "Spezialball", 34: "Standardball",
            35: "Pokédex", 36: "Schal", 37: "Maschine", 38: "Flöte", 39: "Aprikoko-Ball", 40: "Aprikoko", 41: "Datenkarte",
            42: "Juwel", 43: "Wundereinsatz", 44: "Mega-Stein", 45: "Erinnerung", 46: "Z-Kristall", 47: "Bonbon für eine Art",
            48: "Fangbonus", 49: "Dyna-Kristall", 50: "Minze", 51: "Curry-Zutat", 52: "Tera-Stück", 53: "Sandwich-Zutat",
            54: "TM-Material", 55: "Picknick"}
ODD_TEXT = "[VAR"           # Platzhalter aus den Spieltexten: unfertiger Eintrag
_CURE = (("poison", "Gift"), ("burn", "Verbrennung"), ("freez", "Einfrieren"), ("sleep", "Schlaf"), ("paralysis", "Paralyse"),
         ("confusion", "Verwirrung"), ("infatuation", "Anziehung"))


def item_effect(eff):
    """Kurz-Wirkung eines Items aus dem englischen Kurztext der PokéAPI: (Text, Zahl zum Sortieren). Nur, was sich sicher
    lesen lässt (Heilung, AP, Beleben, Statusheilung, Fangfaktor); sonst ("", None)."""
    e = " ".join(str(eff or "").split())
    parts, val = [], None
    if m := re.search(r"Restores (\d+) HP", e):
        val = int(m.group(1))
        parts.append(f"KP +{val}")
    elif m := re.search(r"Restores (\d+)% (?:of )?(?:max )?HP|Restores 1/(\d+) (?:of )?(?:max )?HP", e):
        pct = int(m.group(1)) if m.group(1) else round(100 / int(m.group(2)))
        parts.append(f"KP +{pct} %")
    elif re.search(r"Restores HP to full|Fully restores HP", e):
        val = 999
        parts.append("KP voll")
    if m := re.search(r"Restores (\d+) PP for (one|each) move", e):
        val = int(m.group(1))
        parts.append(f"AP +{val} ({'eine Attacke' if m.group(2) == 'one' else 'alle Attacken'})")
    elif m := re.search(r"Restores PP to full for (one|each) move", e):
        val = 99
        parts.append(f"AP voll ({'eine Attacke' if m.group(1) == 'one' else 'alle Attacken'})")
    if m := re.search(r"Revives with (half|full) HP", e):
        val = 50 if m.group(1) == "half" else 100
        parts.append("belebt mit halben KP" if m.group(1) == "half" else "belebt mit vollen KP")
    if re.search(r"[Cc]ures any (major )?status ailment", e):
        parts.append("heilt alle Statusprobleme" + (" und Verwirrung" if "confusion" in e else ""))
    elif m := re.search(r"[Cc]ures ([a-z ,]+?)(?:\.|,? but|$)", e):
        names = [de for en, de in _CURE if en in m.group(1)]
        if names:
            parts.append("heilt " + ", ".join(names))
    if m := re.search(r"Success rate is (\d+(?:\.\d+)?)×", e):
        val = float(m.group(1))
        parts.append("Fangfaktor ×" + m.group(1).replace(".", ","))
    elif e.startswith("Catches a wild Pokémon every time"):
        val = 255.0
        parts.append("fängt immer")
    elif e.rstrip(".") == "Tries to catch a wild Pokémon":
        val = 1.0
        parts.append("Fangfaktor ×1")
    if parts and "lowers happiness" in e:
        parts.append("senkt die Freundschaft")
    return ", ".join(parts), val


def item_name(ident, name):
    for rx, suffix in ITEM_SUFFIX:
        if rx.search(ident or ""):
            return f"{name} ({suffix})"
    return name


# Itemlisten von PKHeX (PKHeX.Core/Items/ItemStorage<Datei>.cs) für Spiele, zu denen die PokéAPI keine Liste hat
ITEM_LISTS = {"8LA": ("legends-arceus",), "8BDSP": ("brilliant-diamond-shining-pearl",),
              "8SWSH": ("the-isle-of-armor", "the-crown-tundra"),
              "9SV": ("scarlet-violet", "the-teal-mask", "the-indigo-disk"), "9ZA": ("legends-za", "mega-dimension")}
SPAN_POCKET = {"Medicine": "Medizin", "Balls": "Bälle", "Battle": "Kampf-Items", "Berry": "Beeren", "Machine": "Maschinen",
               "MachineRecord": "Maschinen", "TM": "Maschinen", "Key": "Basis-Items", "Event": "Basis-Items"}
PKHEX_ITEM = 100000         # eigene Nummern für Items, die die PokéAPI nicht kennt: 100000 + Nummer im Spiel
_SPAN = re.compile(r"public static ReadOnlySpan<ushort> (\w+) =>[^\[\n]*(?://[^\n]*)?\s*\[([^\]]*)\]")


def pkhex_spans(text):
    """{Name: [Itemnummern]} aus einer ItemStorage-Datei; nur ausgeschriebene Listen, ohne Unveröffentlichtes."""
    out = {}
    for m in _SPAN.finditer(text or ""):
        name = m.group(1)
        if name.startswith(("Unreleased", "Disallow")):
            continue
        out[name] = [int(x) for x in re.findall(r"\b\d+\b", re.sub(r"//[^\n]*", "", m.group(2)))]
    return out


def item_texts(text):
    """Zeilen einer Textdatei von PKHeX (eine Zeile je Itemnummer)."""
    return [x.strip() for x in (text or "").lstrip("\ufeff").split("\n")]


def en_key(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower().replace("é", "e"))


def item_en_de(pkx):
    """{englischer Name (vereinfacht): deutscher Name} aus den Spieltexten (PKHeX)."""
    de, en = item_texts((pkx or {}).get("de")), item_texts((pkx or {}).get("en"))
    out = {}
    for e, d in zip(en, de):
        if e and d and en_key(e) not in out:
            out[en_key(e)] = d
    return out


def _base(name):
    return re.sub(r"\s*\([^)]*\)$", "", name or "")


def _pkhex_items(con, pkx, rows):
    """Itemlisten aus PKHeX zu den Zeilen der PokéAPI legen: bekannte Items bekommen das Spiel dazu, unbekannte
    eine eigene Zeile mit deutschem Namen. Zuordnung über den Spielindex der PokéAPI (gleiche Generation), sonst über den
    englischen Namen. Gleichnamige Einträge desselben Spiels (etwa Rezept-Fassungen) bleiben weg."""
    de, en = item_texts(pkx.get("de")), item_texts(pkx.get("en"))
    if not de:
        return 0
    vg_of = {k: (i, g) for i, k, g in con.execute("SELECT id, kennung, gen FROM spiel")}
    by_index = {}
    if _has(con, "item_game_indices"):
        for iid, g, idx in con.execute("SELECT item_id, generation_id, game_index FROM item_game_indices"):
            by_index.setdefault(g, {})[idx] = iid
    en_names = {}
    if _has(con, "item_names"):
        en_names = {en_key(n): i for i, n in con.execute("SELECT item_id, name FROM item_names WHERE local_language_id = ?", (EN,))}
    by_id = {r[0]: r for r in rows}
    extra = {}                  # id → [Spiele], [Generationen]
    new = {}
    for key, games in ITEM_LISTS.items():
        spans = pkhex_spans(pkx.get(key))
        gs = [vg_of[k] for k in games if k in vg_of]
        if not spans or not gs:
            continue
        gen = int(key[0])
        vgs = [i for i, _ in gs]
        listed = set()
        for span, ids in spans.items():
            for idx in ids:
                name = de[idx] if idx < len(de) else ""
                if not name or name.startswith("???") or idx == 0:
                    continue
                iid = by_index.get(gen, {}).get(idx)
                if iid is None and idx < len(en):
                    iid = en_names.get(en_key(en[idx]))
                if iid in by_id:
                    e = extra.setdefault(iid, [set(), set()])
                    e[0].update(vgs)
                    e[1].add(gen)
                    listed.add(_base(by_id[iid][2]))
                    continue
                if _base(name) in listed:
                    continue
                listed.add(_base(name))
                e = new.setdefault(idx, {"name": name, "tasche": SPAN_POCKET.get(span, "Items"), "vgs": set(), "gens": set()})
                e["vgs"].update(vgs)
                e["gens"].add(gen)
    for iid, (vgs, gens) in extra.items():
        r = by_id[iid]
        con.execute("UPDATE item SET spiele = ?, gens = ? WHERE id = ?",
                    (json.dumps(sorted(set(json.loads(r[8])) | vgs)), json.dumps(sorted(set(json.loads(r[7])) | gens)), iid))
    con.executemany("INSERT INTO item VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(PKHEX_ITEM + idx, f"pkhex-{idx}", e["name"], e["tasche"], "", "de", 0, json.dumps(sorted(e["gens"])),
                      json.dumps(sorted(e["vgs"])), "", "", None, 0, en[idx] if idx < len(en) else "") for idx, e in sorted(new.items())])
    return len(new)


def _derive_item(con, pkx=None):
    """Items: deutscher Name, Tasche, Beschreibung (deutsch aus dem neuesten Spiel mit deutschem Text, sonst englisch),
    die Spiele mit Beschreibung (genau: dort gibt es das Item) und die Generationen laut Spielindex der PokéAPI (grob).
    pkx: Itemlisten und -namen von PKHeX ({"de", "en", Dateikürzel aus ITEM_LISTS: Text}) für Spiele ohne eigene Liste.
    Ohne items.csv bleibt die Tabelle leer."""
    con.execute("CREATE TABLE item (id INTEGER PRIMARY KEY, kennung TEXT, name TEXT, tasche TEXT, text TEXT, sprache TEXT, "
                "preis INTEGER, gens TEXT, spiele TEXT, art TEXT, wirkung TEXT, wert REAL, unfertig INTEGER, en TEXT)")
    if not _has(con, "items"):
        return 0
    names = _names(con, "item_names", "item_id")
    en_names = dict(con.execute("SELECT item_id, name FROM item_names WHERE local_language_id = ?", (EN,))) if _has(con, "item_names") else {}
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
    effects = {}
    if _has(con, "item_prose"):
        for iid, eff in con.execute("SELECT item_id, short_effect FROM item_prose WHERE local_language_id = 9"):
            effects[iid] = item_effect(eff)
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
        eff = effects.get(iid, ("", None))
        rows.append((iid, ident, item_name(ident, names[iid]), pockets.get(cat, ""), t[1] if t else "", t[2] if t else "", cost or 0,
                     json.dumps(sorted(gens.get(iid, ()))), json.dumps(sorted(games.get(iid, ()))), ITEM_ART.get(cat, ""),
                     eff[0], eff[1], int(ODD_TEXT in (t[1] if t else "")), en_names.get(iid, "")))
    con.executemany("INSERT INTO item VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows) + (_pkhex_items(con, pkx, rows) if pkx else 0)


def _derive_karte(con, alt, en_de):
    """Kartensymbole und Sammelobjekte (Altissimo): Tabelle kartenobjekt mit Spielkoordinaten wie spawnpunkt und den
    Items samt Anteil auf Deutsch (unbekannte Namen bleiben englisch)."""
    con.execute("CREATE TABLE kartenobjekt (spiel TEXT, karte TEXT, gebiet TEXT, art TEXT, nr INTEGER, x REAL, z REAL, "
                "menge TEXT, items TEXT)")
    n = 0
    for spiel, src in (alt or {}).items():
        for kind, parse in (("symbole", altissimo.landmarks), ("sammeln", altissimo.collectibles)):
            for karte, text in (src.get(kind) or {}).items():
                fit = altissimo.VILLAGE_FIT if karte == altissimo.VILLAGE else altissimo.FIT.get(karte)
                if not fit:
                    continue
                try:
                    objs = parse(text, fit)
                except ValueError:
                    continue
                gebiet = altissimo.GEBIETE.get(karte, karte)
                con.executemany("INSERT INTO kartenobjekt VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                [(spiel, karte, gebiet, o["art"], o.get("nr"), o["x"], o["z"], o["menge"],
                                  json.dumps([[en_de.get(en_key(i), i), p] for i, p in o["items"]], ensure_ascii=False)) for o in objs])
                n += len(objs)
    return n


# Arten der Kartensymbole: Altissimo und dazu die Ebenen aus der Karte des PokéWiki (Schlüssel → Name, Mehrzahl)
KARTE_ARTEN = {**altissimo.ARTEN, **companion.NAMEN, "kristall": ("Kristallbrocken", "Kristallbrocken"),
               "verzerrung": ("Raum-Zeit-Verzerrung", "Raum-Zeit-Verzerrungen"), "massen": ("Massenauftreten", "Massenauftreten"),
               "baumpkmn": ("Pokémon im Baum", "Pokémon in Bäumen"), "alpha": ("festes Alpha-Pokémon", "feste Alphas"),
               "boden": ("Fundstelle", "Items am Boden")}
NEAR = 2.0                  # so nah (Spieleinheiten) gilt ein Item als dasselbe Symbol wie bei Altissimo
DIG_ITEMS, DIG_NEAR = 5, 16.0   # Stelle mit so vielen Items = Grabstelle; so weit darf die Grabstelle bei Altissimo weg sein


def _wiki_forms(con, spiel):
    """Name im PokéWiki („Fukano“, „Hisui-Baldorfish“, „Burmy (Pflanzenumhang)“, „Icognito E“) → Form. Ohne Zusatz gilt
    die Form, die laut PKHeX im Spiel vorkommt (in Legenden: Arceus oft die Hisui-Form), sonst die Standardform."""
    species = {n: k for k, n in _names(con, "pokemon_species_names", "pokemon_species_id").items()}
    by_art, hisui = {}, {}
    for pid, ident, art, default in con.execute('SELECT id, identifier, species_id, is_default FROM pokemon'):
        if default:
            by_art[art] = pid
        if str(ident).endswith("-hisui"):
            hisui[art] = pid
    in_game = {}
    if _has(con, "fundort"):
        for art, pid in con.execute("SELECT DISTINCT p.species_id, f.form FROM fundort f JOIN pokemon p ON p.id = f.form "
                                    "WHERE f.spiel = ?", (spiel,)):
            in_game.setdefault(art, set()).add(pid)

    def form(name):
        base = re.sub(r"\s*\(.*\)\s*$", "", str(name)).strip()
        base = re.sub(r"^(Icognito) \S$", r"\1", base)
        h = base.startswith("Hisui-")
        art = species.get(base[6:] if h else base)
        if not art:
            return None
        if h and art in hisui:
            return hisui[art]
        seen = in_game.get(art, set())
        return next(iter(seen)) if len(seen) == 1 else by_art.get(art)
    return form


def _derive_wiki_karte(con, wiki):
    """Karte des PokéWiki (pokewiki.map_*): Kristallbrocken, Raum-Zeit-Verzerrungen, Massenauftreten, Pokémon in Bäumen
    und feste Alphas mit Pokémon und Level, dazu Items am Boden mit Anteil (ohne die Stellen, die Altissimo schon als
    Baum, Erzbrocken, Kiste oder Sammelobjekt führt). Welche Datei zu welcher Karte gehört: die Karte, deren Spawnpunkte
    (JS-Finder) die meisten Punkte der Datei genau treffen. Gibt die Zahl der Symbole zurück."""
    maps = ((wiki or {}).get("karte") or {})
    if not maps or not _has(con, "spawnpunkt"):
        return 0
    n = 0
    names = {pokewiki.item_key(x): x for (x,) in con.execute("SELECT name FROM item")} if _has(con, "item") else {}
    for spiel, areas in maps.items():
        pts = {}
        for karte, x, z in con.execute("SELECT karte, x, z FROM spawnpunkt WHERE spiel = ?", (spiel,)):
            pts.setdefault(karte, set()).add((round(x, 1), round(z, 1)))
        if not pts:
            continue
        form = _wiki_forms(con, spiel)
        for area, src in sorted(areas.items()):
            try:
                mons = pokewiki.map_pokemon(src.get("pokemon"))
                items = pokewiki.map_items(src.get("items"))
            except (ValueError, TypeError, AttributeError):
                continue
            own = {(round(m["x"], 1), round(m["z"], 1)) for m in mons if m["typ"] == "default"}
            karte, hit = max(((k, len(own & v)) for k, v in pts.items()), key=lambda kv: kv[1], default=(None, 0))
            if not karte or hit < 5:
                continue
            gebiet = altissimo.GEBIETE.get(karte, karte)
            groups = {}
            for m in mons:
                art = pokewiki.MAP_TYPES.get(m["typ"])
                if not art:
                    continue
                if art == "alpha":
                    text = f"Alpha, Lv {_lv(m['alv'])}" if m["alv"] else "Alpha"
                else:
                    text = (f"Lv {_lv(m['lv'])}" if m["lv"] else "") + (f", {m['max']:g} %".replace(".", ",") if m["max"] and m["max"] < 99 else "")
                fid = form(m["name"])
                groups.setdefault((art, m["x"], m["z"]), []).append([m["name"], text, fid])
            old = con.execute("SELECT rowid, art, x, z FROM kartenobjekt WHERE spiel = ? AND karte = ?", (spiel, karte)).fetchall()
            verse = any(r[1] == "vers" for r in old)
            for it in items:
                if any(abs(it["x"] - x) <= NEAR and abs(it["z"] - z) <= NEAR for _, _, x, z in old):
                    continue
                name = names.get(pokewiki.item_key(it["name"]), it["name"].replace("-", ""))
                if verse and name.startswith("Altes Gedicht"):        # Gedichte führt Altissimo schon (etwas andere Lage)
                    continue
                groups.setdefault(("boden", round(it["x"], 1), round(it["z"], 1)), []).append(
                    [name, f"{it['anteil']} %" if it["anteil"] else ""])
            # Stellen mit vielen Items sind Grabstellen (Ursaluna): Items zur nächsten Grabstelle von Altissimo legen
            digs = [r for r in old if r[1] == "graben"]
            for key in [k for k, v in groups.items() if k[0] == "boden" and len(v) >= DIG_ITEMS]:
                near = min(digs, key=lambda r: (r[2] - key[1]) ** 2 + (r[3] - key[2]) ** 2, default=None)
                v = sorted(groups.pop(key), key=lambda e: e[0])
                if near and (near[2] - key[1]) ** 2 + (near[3] - key[2]) ** 2 <= DIG_NEAR ** 2:
                    con.execute("UPDATE kartenobjekt SET items = ? WHERE rowid = ?", (json.dumps(v, ensure_ascii=False), near[0]))
                    digs.remove(near)
                else:
                    groups[("graben", key[1], key[2])] = v
            rows = [(spiel, karte, gebiet, art, None, x, z, "", json.dumps(sorted(v, key=lambda e: e[0]), ensure_ascii=False))
                    for (art, x, z), v in groups.items()]
            con.executemany("INSERT INTO kartenobjekt VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            n += len(rows)
    return n


def _derive_companion(con, alt):
    """Schnellreise und Lager aus dem PLA Companion (alt[Spiel]["companion"] = {Karte: Text}), in Spielkoordinaten
    ausgerichtet an den Geisterlichtern und Icognito von Altissimo (companion.places). Gibt die Zahl der Orte zurück."""
    n = 0
    for spiel, src in (alt or {}).items():
        for karte, text in sorted((src.get("companion") or {}).items()):
            anchors = {}
            for a, x, z in con.execute("SELECT art, x, z FROM kartenobjekt WHERE spiel = ? AND karte = ? AND art IN ('irrlicht', 'icognito')",
                                       (spiel, karte)):
                anchors.setdefault(a, []).append((x, z))
            try:
                ps = companion.places(text, anchors)
            except (ValueError, TypeError, AttributeError):
                continue
            con.executemany("INSERT INTO kartenobjekt VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            [(spiel, karte, altissimo.GEBIETE.get(karte, karte), p["art"], None, p["x"], p["z"], "",
                              json.dumps([[p["name"], ""]], ensure_ascii=False)) for p in ps])
            n += len(ps)
    return n


def _lv(r):
    return f"{r[0]}" if r[0] == r[1] else f"{r[0]}–{r[1]}"


def _derive_rezept(con, alt, en_de):
    """Rezepte zum Herstellen (Altissimo): Tabelle rezept mit Zutaten [Anzahl, Name, Item] und Tabelle zutat mit den
    Fundorten der Zutaten (englisch). Items werden über den deutschen Namen unter den Items des Spiels gesucht."""
    con.execute("CREATE TABLE rezept (spiel TEXT, item_id INTEGER, item TEXT, zutaten TEXT, ort TEXT, hinweis TEXT)")
    con.execute("CREATE TABLE zutat (spiel TEXT, item_id INTEGER, item TEXT, fundorte TEXT)")
    n = 0
    for spiel, src in (alt or {}).items():
        try:
            recs, mats = altissimo.recipes(src.get("rezepte") or "")
        except Exception:
            continue
        g = con.execute("SELECT id FROM spiel WHERE kennung = ?", (spiel,)).fetchone()
        ids = {}
        for iid, name, spiele in con.execute("SELECT id, name, spiele FROM item"):
            if g and g[0] in json.loads(spiele or "[]"):
                ids.setdefault(_base(name), iid)
        de = lambda en: en_de.get(en_key(en), en)
        find = lambda en: ids.get(_base(de(en)))
        for r in recs:
            con.execute("INSERT INTO rezept VALUES (?, ?, ?, ?, ?, ?)",
                        (spiel, find(r["item"]), de(r["item"]),
                         json.dumps([[k, de(z), find(z)] for k, z in r["zutaten"]], ensure_ascii=False),
                         altissimo.place(r["ort"].split(" - ")[0]) + (" – " + r["ort"].split(" - ", 1)[1] if " - " in r["ort"] else ""),
                         r["hinweis"]))
            n += 1
        con.executemany("INSERT INTO zutat VALUES (?, ?, ?, ?)",
                        [(spiel, find(m), de(m), json.dumps(where, ensure_ascii=False)) for m, where in mats.items()])
    return n


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


def _item_ids(con, spiel):
    """Deutscher Item-Name (pokewiki.item_key) → ID. Gibt es einen Namen mehrfach (etwa aus PKHeX und der PokéAPI), gilt
    das Item im Spiel, dann das der PokéAPI (kleinere ID, hat ein Bild)."""
    try:
        gid = (con.execute("SELECT id FROM spiel WHERE kennung = ?", (spiel,)).fetchone() or [None])[0]
        rows = con.execute("SELECT id, name, spiele FROM item").fetchall()
    except sqlite3.Error:
        rows, gid = [(i, n, "[]") for i, n in con.execute("SELECT id, name FROM item")], None
    best = {}
    for i, n, sp in rows:
        try:
            inside = gid is not None and gid in json.loads(sp or "[]")
        except (TypeError, ValueError):
            inside = False
        k = pokewiki.item_key(n or "")
        rank = (not inside, i)
        if k and (k not in best or rank < best[k][0]):
            best[k] = (rank, i)
    return {k: v[1] for k, v in best.items()}


def _derive_wiki(con, wiki):
    """Aus dem PokéWiki (abruf._pokewiki): Attackenwerte je Spiel (attacke_spiel) und getragene Items wilder Pokémon
    (getragen). Namen werden über die deutschen Namen der Datenbank zugeordnet; Unbekanntes bleibt weg.
    Gibt (Attacken, Items) zurück."""
    con.execute("CREATE TABLE attacke_spiel (spiel TEXT, attacke INTEGER, staerke INTEGER, kraft INTEGER, tempo INTEGER, "
                "genauigkeit INTEGER, ap INTEGER, PRIMARY KEY (spiel, attacke))")
    con.execute("CREATE TABLE getragen (spiel TEXT, art INTEGER, item TEXT, item_id INTEGER, prozent TEXT, elite INTEGER)")
    wiki = wiki or {}
    moves = {n: i for i, n in con.execute("SELECT id, name FROM attacke")}
    n_moves = 0
    for spiel, vals in (wiki.get("attacken") or {}).items():
        for name, v in vals.items():
            mid = moves.get(name)
            if mid and isinstance(v, dict):
                con.execute("INSERT OR REPLACE INTO attacke_spiel VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (spiel, mid, v.get("staerke"), v.get("kraft"), v.get("tempo"), v.get("genauigkeit"), v.get("ap")))
                n_moves += 1
    species = {n: k for k, n in _names(con, "pokemon_species_names", "pokemon_species_id").items()}
    n_items = 0
    for spiel, per in (wiki.get("items") or {}).items():
        items = _item_ids(con, spiel)
        for name, xs in per.items():
            art = species.get(name)
            if not art:
                continue
            for x in xs:
                con.execute("INSERT INTO getragen VALUES (?, ?, ?, ?, ?, ?)",
                            (spiel, art, x["item"], items.get(pokewiki.item_key(x["item"])), x.get("prozent", ""), int(bool(x.get("elite")))))
                n_items += 1
    return n_moves, n_items


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


def build(path, csvs, sd_texts=None, extra=None, strict=True, pkhex=None, spawns=None, sets=None, wiki=None, alt=None):
    """Baut die Datenbank unter path (wird überschrieben). csvs: {Name: Text}; sd_texts: {"pokedex": Text,
    "moves": Text}; extra: {Name: Inhalt} aus extra/; pkhex: Begegnungen je Spiel (siehe _derive_fundort);
    spawns: Spawnpunkte je Spiel und Karte (siehe _derive_spawn); pkhex["_items"]: Itemlisten (siehe _derive_item);
    alt: Altissimo je Spiel {"symbole": {Karte: Text}, "sammeln": {Karte: Text}, "rezepte": HTML}.
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
        _derive_attacke(con, sd_moves, (extra or {}).get("attacken_kurz"))
        _sd_tables(con, sd_dex, sd_moves)
        n_check = _derive_pruefung(con, sd_dex, sd_moves) if sd_dex or sd_moves else 0
        n_fund = _derive_fundort(con, pkhex)
        n_spawn = _derive_spawn(con, spawns)
        pkx = (pkhex or {}).get("_items")
        n_item = _derive_item(con, pkx)
        en_de = item_en_de(pkx)
        n_obj = _derive_karte(con, alt, en_de)
        n_rez = _derive_rezept(con, alt, en_de)
        n_sets = _derive_moveset(con, sets)
        n_wiki_moves, n_wiki_items = _derive_wiki(con, wiki)
        n_wiki_karte = _derive_wiki_karte(con, wiki)
        n_orte = _derive_companion(con, alt)
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
                 "sd_pokemon": len(sd_dex), "sd_moves": len(sd_moves), "diff": n_check, "fundorte": n_fund, "spawns": n_spawn, "items": n_item, "sets": n_sets, "wiki_attacken": n_wiki_moves, "wiki_items": n_wiki_items,
                 "kartenobjekte": n_obj, "wiki_karte": n_wiki_karte, "orte": n_orte, "rezepte": n_rez, "check": why}
    finally:
        con.close()
    return stats
