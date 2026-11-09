"""Abfragen für die Oberfläche: Pokémon-Liste mit Filtern, Detailseite, Attacken je Spiel, Typtabelle, Teams.

Was oft gebraucht wird (Typen, Formen, Attacken, Spiele), hält Daten im Speicher und lädt neu, sobald der
Abgleich eine neue pokeapi.db gebaut hat. Lernlisten, Fundorte und Entwicklungen kommen je Anfrage aus der Datenbank.
"""
import json
import os
import threading

from . import attacken, db, team, typen

LA = "legends-arceus"          # Legenden: Arceus kennt keine Fähigkeiten und eigene Attackenwerte
NO_ABILITIES = {LA}
WIKI = "https://www.pokewiki.de/"
_lock = threading.Lock()
_cache = {"stamp": None}


def _stamp():
    try:
        st = os.stat(db.pokeapi_path())
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _names(con, table, key, col="name", lang_col="local_language_id"):
    out = {}
    try:
        rows = con.execute(f'SELECT "{key}", {lang_col}, "{col}" FROM "{table}" WHERE {lang_col} IN (6, 9)').fetchall()
    except Exception:
        return out
    for k, lang, n in rows:
        if n and (lang == 6 or k not in out):
            out[k] = n
    return out


class Data:
    def __init__(self, con):
        self.types = {r[0]: r[1] for r in con.execute(
            "SELECT t.id, COALESCE(n.name, t.identifier) FROM types t LEFT JOIN type_names n ON n.type_id = t.id AND n.local_language_id = 6 "
            "WHERE t.id <= 18 ORDER BY t.id")}
        self.type_key = {r[0]: r[1] for r in con.execute("SELECT id, identifier FROM types WHERE id <= 18")}
        self.type_gen = {r[0]: r[1] for r in con.execute("SELECT id, generation_id FROM types WHERE id <= 18")}
        self.eff = [tuple(r) for r in con.execute("SELECT damage_type_id, target_type_id, damage_factor FROM type_efficacy")]
        try:
            self.past = [tuple(r) for r in con.execute("SELECT damage_type_id, target_type_id, damage_factor, generation_id FROM type_efficacy_past")]
        except Exception:
            self.past = []
        self.games = [dict(r) for r in con.execute("SELECT id, kennung, name, gen, reihenfolge FROM spiel ORDER BY reihenfolge")]
        self.game_by = {g["kennung"]: g for g in self.games}
        self.forms = {}
        for r in con.execute("SELECT * FROM form"):
            f = dict(r)
            f["typen"] = [t for t in (f["typ1"], f["typ2"]) if t]
            f["werte"] = [f["kp"], f["ang"], f["vert"], f["spang"], f["spvert"], f["init"]]
            f["faehigkeiten"] = json.loads(f["faehigkeiten"] or "[]")
            self.forms[f["id"]] = f
        self.abilities = {r[0]: (r[1], r[2]) for r in con.execute(
            "SELECT a.id, a.identifier, COALESCE(n.name, a.identifier) FROM abilities a "
            "LEFT JOIN ability_names n ON n.ability_id = a.id AND n.local_language_id = 6")}
        self.moves = {}
        for r in con.execute("SELECT * FROM attacke"):
            m = dict(r)
            m["merkmale"] = json.loads(m["merkmale"] or "[]")
            m["selbst"] = json.loads(m["selbst"] or "{}")
            m["mehrfach"] = json.loads(m["mehrfach"]) if m["mehrfach"] else None
            self.moves[m["id"]] = m
        order = {g["id"]: g["reihenfolge"] for g in self.games}
        self.changes = {}
        for mid, vg, typ, power, pp, acc, prio in con.execute(
                "SELECT move_id, changed_in_version_group_id, type_id, power, pp, accuracy, priority FROM move_changelog"):
            self.changes.setdefault(mid, []).append((order.get(vg, 0), typ, power, pp, acc, prio))
        self.types_past = {}
        try:
            for pid, gen, tid, slot in con.execute("SELECT pokemon_id, generation_id, type_id, slot FROM pokemon_types_past ORDER BY slot"):
                self.types_past.setdefault(pid, {}).setdefault(gen, []).append(tid)
        except Exception:
            pass
        self.in_game = {}
        for sp, fid, nr in con.execute("SELECT spiel, form, nr FROM spiel_form"):
            self.in_game.setdefault(sp, {})[fid] = nr
        self.methods = _names(con, "pokemon_move_method_prose", "pokemon_move_method_id")
        self.method_key = dict(con.execute("SELECT id, identifier FROM pokemon_move_methods"))
        self.charts = {}
        self.max_gen = max((g["gen"] for g in self.games), default=9)

    def chart(self, gen):
        if gen not in self.charts:
            self.charts[gen] = typen.chart(self.eff, self.past, self.type_gen, gen)
        return self.charts[gen]

    def tname(self, t):
        return self.types.get(t, str(t))


def data():
    """Daten im Speicher; None, solange es noch keine pokeapi.db gibt."""
    st = _stamp()
    if st is None:
        return None
    with _lock:
        if _cache["stamp"] != st:
            con = db.game()
            try:
                _cache["data"] = Data(con)
            finally:
                con.close()
            _cache["stamp"] = st
        return _cache["data"]


# ------------------------------------------------------------------ Spiel und Formen

def game_of(D, kennung):
    """(Spiel oder None, Generation, Typtabelle)."""
    g = D.game_by.get(kennung or "")
    gen = g["gen"] if g else D.max_gen
    return g, gen, D.chart(gen)


def form_types(D, f, gen):
    """Typen einer Form in einer Generation (Pixi war bis Generation 5 Normal)."""
    past = D.types_past.get(f["id"])
    if past:
        for until in sorted(past):
            if until >= gen:
                return past[until]
    return f["typen"]


def ability_of(D, f, g):
    """Fähigkeit für die Typwirkung: die erste normale; in Legenden: Arceus gibt es keine."""
    if g and g["kennung"] in NO_ABILITIES:
        return None
    for aid, hidden in f["faehigkeiten"]:
        if not hidden:
            return D.abilities.get(aid, (None,))[0]
    return None


def member(D, f, g, gen, ability=None, attack_types=None):
    return {"id": f["id"], "art": f["art"], "name": f["name"], "typen": form_types(D, f, gen), "werte": f["werte"],
            "summe": f["summe"], "faehigkeit": ability if ability is not None else ability_of(D, f, g),
            "angriffstypen": attack_types}


def row(D, f, g, gen, nr=None):
    """Kurzform für Listen."""
    return {"id": f["id"], "art": f["art"], "nr": nr if nr is not None else f["art"], "name": f["name"],
            "typen": form_types(D, f, gen), "werte": f["werte"], "summe": f["summe"], "gen": f["gen"],
            "legendaer": f["legendaer"] or f["mysterioes"], "endstufe": f["endstufe"], "kampfform": f["kampfform"],
            "standard": f["standard"], "relevant": f["relevant"]}


SORTS = {"nr": lambda r: (r["nr"] or 99999, r["id"]), "name": lambda r: (r["name"].lower(), r["id"]),
         "summe": lambda r: (-r["summe"], r["id"]), "init": lambda r: (-r["werte"][5], r["id"]),
         "ang": lambda r: (-r["werte"][1], r["id"]), "spang": lambda r: (-r["werte"][3], r["id"]),
         "kp": lambda r: (-r["werte"][0], r["id"]), "vert": lambda r: (-r["werte"][2] - r["werte"][4], r["id"])}


def candidates(D, p):
    """Formen nach Filtern. p: spiel, q, typ, typ2, gen, endstufe, ohne_leg, min, formen (relevant|standard|alle), kampf."""
    g, gen, _ = game_of(D, p.get("spiel"))
    in_game = D.in_game.get(g["id"], {}) if g else None
    q = str(p.get("q") or "").strip().lower()
    t1, t2 = _int(p.get("typ")), _int(p.get("typ2"))
    max_gen = _int(p.get("gen"))
    mn = _int(p.get("min")) or 0
    formen = p.get("formen") or "relevant"
    out = []
    for f in D.forms.values():
        if in_game is not None and f["id"] not in in_game:
            continue
        if formen == "relevant" and not f["relevant"]:
            continue
        if formen == "standard" and not f["standard"]:
            continue
        if not p.get("kampf") and f["kampfform"] and formen != "alle":
            continue
        if max_gen and f["gen"] > max_gen:
            continue
        if p.get("endstufe") and not f["endstufe"]:
            continue
        if p.get("ohne_leg") and (f["legendaer"] or f["mysterioes"]):
            continue
        if f["summe"] < mn:
            continue
        ts = form_types(D, f, gen)
        if t1 and t1 not in ts or t2 and t2 not in ts:
            continue
        nr = in_game.get(f["id"]) if in_game else None
        if q:
            hit = q in f["name"].lower() or q in f["kennung"] or (q.isdigit() and int(q) in (f["art"], nr))
            if not hit:
                continue
        out.append((f, nr))
    return g, gen, out


def search(p):
    D = data()
    if not D:
        return {"rows": [], "n": 0, "ohne_daten": True}
    g, gen, found = candidates(D, p)
    rows = [row(D, f, g, gen, nr) for f, nr in found]
    rows.sort(key=SORTS.get(p.get("sort") or "nr", SORTS["nr"]))
    lim = min(_int(p.get("limit")) or 60, 2000)
    off = _int(p.get("offset")) or 0
    return {"rows": rows[off:off + lim], "n": len(rows), "spiel": g["kennung"] if g else ""}


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ Attacken

def move_view(D, m, g):
    order = g["reihenfolge"] if g else 10 ** 6
    v = attacken.in_game(m, D.changes.get(m["id"], []), order)
    return v


def learnset(con, D, f, g):
    """Erlernbare Attacken im Spiel: [(Attacke, Methode, Level, Beherrschung)]; ohne Spiel das neueste mit Liste."""
    vg = g["id"] if g else None
    if vg is not None and not con.execute("SELECT 1 FROM pokemon_moves WHERE pokemon_id = ? AND version_group_id = ? LIMIT 1",
                                          (f["id"], vg)).fetchone():
        vg = None          # nicht im Spiel: Liste aus dem neuesten Spiel, die Oberfläche sagt dazu
    if vg is None:
        r = con.execute("SELECT version_group_id FROM pokemon_moves pm JOIN spiel s ON s.id = pm.version_group_id "
                        "WHERE pokemon_id = ? ORDER BY s.reihenfolge DESC LIMIT 1", (f["id"],)).fetchone()
        if not r:
            return [], None
        vg = r[0]
    pid = f["id"]
    rows = con.execute("SELECT move_id, pokemon_move_method_id, level, mastery FROM pokemon_moves WHERE pokemon_id = ? AND version_group_id = ?",
                       (pid, vg)).fetchall()
    if not rows and not f["standard"]:
        # Form ohne eigene Liste (Mega-Entwicklungen): die der Standardform
        base = next((x for x in D.forms.values() if x["art"] == f["art"] and x["standard"]), None)
        if base:
            rows = con.execute("SELECT move_id, pokemon_move_method_id, level, mastery FROM pokemon_moves WHERE pokemon_id = ? "
                               "AND version_group_id = ?", (base["id"], vg)).fetchall()
    best = {}
    for mid, meth, lv, mastery in rows:
        k = (mid, meth)
        if k not in best or (lv or 0) < (best[k][2] or 0):
            best[k] = (mid, meth, lv, mastery)
    used = next((x for x in D.games if x["id"] == vg), None)
    return list(best.values()), used


def how(D, meth, lv, mastery):
    key = D.method_key.get(meth, "")
    if key == "level-up":
        txt = f"Level {lv}" if lv and lv > 1 else "Level 1" if lv == 1 else "Start"
        return txt + (f", Beherrschung ab {mastery}" if mastery else "")
    return {"machine": "TM", "egg": "Ei", "tutor": "Lehrer"}.get(key) or D.methods.get(meth) or key


def ranked_moves(con, D, f, g, gen, level=None):
    """Bewertete Schadens-Attacken einer Form im Spiel, mit Gründen, dazu Moveset und Status-Attacken."""
    ls, used = learnset(con, D, f, g)
    ch = D.chart(gen)
    mon = {"typen": form_types(D, f, gen), "ang": f["ang"], "spang": f["spang"], "faehigkeit": ability_of(D, f, used)}
    by_move = {}
    for mid, meth, lv, mastery in ls:
        m = D.moves.get(mid)
        if not m:
            continue
        entry = by_move.setdefault(mid, {"m": m, "wege": []})
        entry["wege"].append((D.method_key.get(meth, ""), lv, mastery, how(D, meth, lv, mastery)))
    out, status = [], []
    for mid, e in by_move.items():
        v = move_view(D, e["m"], used)
        wege = sorted(e["wege"], key=lambda w: (w[0] != "level-up", w[1] or 0))
        now = level is None or any(w[0] != "level-up" or (w[1] or 0) <= level for w in wege)
        base = {"id": mid, "name": v["name"], "typ": v["typ"], "klasse": v["klasse"], "staerke": v["staerke"],
                "genauigkeit": v["genauigkeit"], "ap": v["ap"], "prio": v["prio"], "wege": [w[3] for w in wege],
                "jetzt": now, "geaendert": bool(v.get("geaendert")), "text": v.get("text")}
        if v["klasse"] == attacken.STATUS or not v["staerke"]:
            status.append(base)
            continue
        sc, why = attacken.score(v, mon, ch)
        extra = attacken.coverage_note(v["typ"], mon["typen"], ch)
        if extra and v["typ"] not in mon["typen"]:
            why = why + ["trifft zusätzlich " + ", ".join(D.tname(t) for t in extra[:4])]
        out.append(dict(base, wertung=sc, gruende=why, _v=v))
    out.sort(key=lambda x: (-x["wertung"], x["name"]))
    pick = attacken.moveset([(x["wertung"], dict(x["_v"], _row=x)) for x in out if x["jetzt"]], mon, ch)
    moveset = [{"id": m["_row"]["id"], "name": m["_row"]["name"], "typ": m["_row"]["typ"], "grund": why} for m, why in pick]
    for x in out:
        x.pop("_v", None)
    status.sort(key=lambda x: x["name"])
    hint = ""
    if g and used and used["id"] != g["id"]:
        hint = f"Im gewählten Spiel ohne Lernliste; gezeigt ist {used['name']}."
    elif used and used["kennung"] == LA:
        hint = "Stärke und Genauigkeit stammen aus den Hauptspielen; in Legenden: Arceus weichen sie teils ab (Kraft- und Tempostil)."
    return {"spiel": used["kennung"] if used else "", "spiel_name": used["name"] if used else "", "attacken": out,
            "moveset": moveset, "status": status, "hinweis": hint}


def best_of_type(p):
    """Beste Attacken eines Typs im Spiel (Stärke × Genauigkeit), optional nur eine Klasse."""
    D = data()
    if not D:
        return {"rows": []}
    g, gen, _ = game_of(D, p.get("spiel"))
    t = _int(p.get("typ"))
    cls = _int(p.get("klasse"))
    allowed = None
    if g:
        con = db.game()
        try:
            allowed = {r[0] for r in con.execute("SELECT DISTINCT move_id FROM pokemon_moves WHERE version_group_id = ?", (g["id"],))}
        finally:
            con.close()
    rows = []
    for m in D.moves.values():
        if allowed is not None and m["id"] not in allowed:
            continue
        if m["gen"] and m["gen"] > gen:
            continue
        v = move_view(D, m, g)
        if (t and v["typ"] != t) or (cls and v["klasse"] != cls) or v["klasse"] == attacken.STATUS or not v["staerke"] or v["staerke"] <= 1:
            continue
        sc, why = attacken.score(v, {"typen": [v["typ"]], "ang": 1, "spang": 1}, D.chart(gen))
        why = [w for w in why if w not in ("Eigentyp-Bonus", "passt zum stärkeren Angriffswert")]
        rows.append({"id": v["id"], "name": v["name"], "typ": v["typ"], "klasse": v["klasse"], "staerke": v["staerke"],
                     "genauigkeit": v["genauigkeit"], "ap": v["ap"], "prio": v["prio"], "wertung": round(sc / 1.5, 1),
                     "gruende": why, "geaendert": bool(v.get("geaendert")), "text": v.get("text")})
    rows.sort(key=lambda x: (-x["wertung"], x["name"]))
    return {"rows": rows[: min(_int(p.get("limit")) or 30, 300)], "spiel": g["kennung"] if g else ""}


# ------------------------------------------------------------------ Detailseite

def _evolutions(con, D, f):
    """Entwicklungskette der Art mit Bedingungen in Worten."""
    if not f.get("kette"):
        return []
    species = con.execute("SELECT id, evolves_from_species_id FROM pokemon_species WHERE evolution_chain_id = ? ORDER BY id",
                          (f["kette"],)).fetchall()
    items = _names(con, "item_names", "item_id")
    trig = _names(con, "evolution_trigger_prose", "evolution_trigger_id")
    locs = _names(con, "location_names", "location_id")
    std = {x["art"]: x for x in D.forms.values() if x["standard"]}
    by_key = {x["kennung"]: x for x in D.forms.values()}
    base = std.get(f["art"])
    # Regionalform (zoroark-hisui): die Kette in derselben Region zeigen, soweit es die Formen gibt
    suffix = f["kennung"][len(base["kennung"]):] if base and f["kennung"].startswith(base["kennung"] + "-") else ""
    out = []
    for sp, frm in species:
        conds = []
        for r in con.execute("SELECT * FROM pokemon_evolution WHERE evolved_species_id = ?", (sp,)):
            c = evo_text(dict(r), D, items, trig, locs)
            if c and c not in conds:
                conds.append(c)
        x = std.get(sp)
        if x and suffix and (x["kennung"] + suffix) in by_key:
            x = by_key[x["kennung"] + suffix]
        out.append({"art": sp, "von": frm, "id": x["id"] if x else None, "name": x["name"] if x else str(sp),
                    "typen": x["typen"] if x else [], "bedingungen": [c for c in conds if c]})
    return out


def evo_text(r, D, items, trig, locs):
    """Bedingung einer Entwicklung in Worten, aus den gefüllten Spalten von pokemon_evolution."""
    parts = []
    t = r.get("evolution_trigger_id")
    if r.get("minimum_level"):
        parts.append(f"ab Level {r['minimum_level']}")
    if r.get("trigger_item_id"):
        parts.append(f"mit {items.get(r['trigger_item_id'], 'Item')}")
    if r.get("held_item_id"):
        parts.append(f"hält {items.get(r['held_item_id'], 'Item')}")
    if r.get("time_of_day"):
        parts.append({"day": "tagsüber", "night": "nachts", "dusk": "in der Dämmerung", "full-moon": "bei Vollmond"}.get(r["time_of_day"], r["time_of_day"]))
    if r.get("minimum_happiness"):
        parts.append(f"Freundschaft ab {r['minimum_happiness']}")
    if r.get("minimum_affection"):
        parts.append(f"Zuneigung ab {r['minimum_affection']}")
    if r.get("minimum_beauty"):
        parts.append(f"Schönheit ab {r['minimum_beauty']}")
    if r.get("known_move_id") and r["known_move_id"] in D.moves:
        parts.append(f"kennt {D.moves[r['known_move_id']]['name']}")
    if r.get("known_move_type_id"):
        parts.append(f"kennt eine {D.tname(r['known_move_type_id'])}-Attacke")
    if r.get("location_id"):
        parts.append(f"in/an {locs.get(r['location_id'], 'besonderem Ort')}")
    if r.get("gender_id"):
        parts.append({1: "nur weiblich", 2: "nur männlich"}.get(r["gender_id"], ""))
    if r.get("relative_physical_stats") is not None:
        parts.append({1: "Angriff > Verteidigung", -1: "Angriff < Verteidigung", 0: "Angriff = Verteidigung"}.get(r["relative_physical_stats"], ""))
    if r.get("party_species_id"):
        x = next((f for f in D.forms.values() if f["art"] == r["party_species_id"] and f["standard"]), None)
        parts.append(f"mit {x['name'] if x else 'bestimmtem Pokémon'} im Team")
    if r.get("party_type_id"):
        parts.append(f"mit {D.tname(r['party_type_id'])}-Pokémon im Team")
    if r.get("trade_species_id"):
        x = next((f for f in D.forms.values() if f["art"] == r["trade_species_id"] and f["standard"]), None)
        parts.append(f"Tausch gegen {x['name'] if x else 'bestimmtes Pokémon'}")
    if r.get("needs_overworld_rain"):
        parts.append("bei Regen")
    if r.get("turn_upside_down"):
        parts.append("Konsole umdrehen")
    if r.get("used_move_id") and r["used_move_id"] in D.moves:
        parts.append(f"{D.moves[r['used_move_id']]['name']} {r.get('minimum_move_count') or ''}-mal einsetzen".replace("  ", " "))
    if r.get("minimum_steps"):
        parts.append(f"{r['minimum_steps']} Schritte")
    if r.get("minimum_damage_taken"):
        parts.append(f"{r['minimum_damage_taken']} Schaden genommen")
    head = trig.get(t, "")
    if head and not parts:
        return head
    key = {1: "", 2: "Tausch", 3: "", 4: "", 5: "", 6: "", 7: ""}.get(t, "")
    return ", ".join(x for x in ([key] if key else []) + parts if x) or head


def _enc(con, g, pid):
    """Fundorte im Spiel: Ort, Methode, Level, Bedingungen."""
    if not g:
        return []
    try:
        rows = con.execute(
            """SELECT e.location_area_id la, l.id loc, es.encounter_method_id meth, MIN(e.min_level) lo, MAX(e.max_level) hi,
                      GROUP_CONCAT(DISTINCT v.id) vers, GROUP_CONCAT(DISTINCT m.encounter_condition_value_id) cond,
                      SUM(es.rarity) rar
               FROM encounters e JOIN versions v ON v.id = e.version_id JOIN location_areas la ON la.id = e.location_area_id
               JOIN locations l ON l.id = la.location_id JOIN encounter_slots es ON es.id = e.encounter_slot_id
               LEFT JOIN encounter_condition_value_map m ON m.encounter_id = e.id
               WHERE e.pokemon_id = ? AND v.version_group_id = ?
               GROUP BY e.location_area_id, es.encounter_method_id ORDER BY l.id""", (pid, g["id"])).fetchall()
    except Exception:
        return []
    if not rows:
        return []
    locs = _names(con, "location_names", "location_id")
    areas = _names(con, "location_area_prose", "location_area_id")
    meths = _names(con, "encounter_method_prose", "encounter_method_id")
    conds = _names(con, "encounter_condition_value_prose", "encounter_condition_value_id")
    vn = _names(con, "version_names", "version_id")
    nv = con.execute("SELECT COUNT(*) FROM versions WHERE version_group_id = ?", (g["id"],)).fetchone()[0]
    out = []
    for r in rows:
        area = areas.get(r["la"]) or ""
        place = locs.get(r["loc"]) or ""
        vs = [int(v) for v in str(r["vers"] or "").split(",") if v]
        out.append({"ort": place + (f" ({area})" if area and area.lower() not in place.lower() else ""),
                    "methode": meths.get(r["meth"], ""), "level": f"{r['lo']}" if r["lo"] == r["hi"] else f"{r['lo']}–{r['hi']}",
                    "bedingungen": [conds[int(c)] for c in str(r["cond"] or "").split(",") if c and int(c) in conds],
                    "editionen": [vn.get(v, "") for v in vs] if len(vs) < nv else []})
    return out


def detail(fid, p):
    D = data()
    if not D or fid not in D.forms:
        return None
    f = D.forms[fid]
    g, gen, ch = game_of(D, p.get("spiel"))
    con = db.game()
    try:
        ts = form_types(D, f, gen)
        ab = ability_of(D, f, g)
        dvec = typen.defense(ts, ch, ab)
        flavor = con.execute("SELECT flavor_text FROM pokemon_species_flavor_text WHERE species_id = ? AND language_id = 6 "
                             "ORDER BY version_id DESC LIMIT 1", (f["art"],)).fetchone()
        genus = con.execute("SELECT genus FROM pokemon_species_names WHERE pokemon_species_id = ? AND local_language_id = 6", (f["art"],)).fetchone()
        abil = []
        if not (g and g["kennung"] in NO_ABILITIES):
            for aid, hidden in f["faehigkeiten"]:
                k, n = D.abilities.get(aid, ("", str(aid)))
                txt = con.execute("SELECT flavor_text FROM ability_flavor_text WHERE ability_id = ? AND language_id = 6 "
                                  "ORDER BY version_group_id DESC LIMIT 1", (aid,)).fetchone()
                abil.append({"name": n, "versteckt": bool(hidden), "text": " ".join(str(txt[0]).split()) if txt else "",
                             "wirkt": k in typen.ABILITY_DEFENSE})
        siblings = [{"id": x["id"], "name": x["name"]} for x in D.forms.values()
                    if x["art"] == f["art"] and x["id"] != f["id"] and (x["relevant"] or x["standard"])]
        moves = ranked_moves(con, D, f, g, gen, _int(p.get("level")))
        nr = D.in_game.get(g["id"], {}).get(fid) if g else None
        return dict(row(D, f, g, gen, nr), formname=f["formname"], kategorie=genus[0] if genus else "",
                    text=" ".join(str(flavor[0]).split()) if flavor else "", faehigkeiten=abil,
                    wirkung={str(a): v for a, v in dvec.items()}, faehigkeit_wirkt=ab if ab in typen.ABILITY_DEFENSE else "",
                    entwicklung=_evolutions(con, D, f), fundorte=_enc(con, g, fid), formen=siblings, attacken=moves,
                    im_spiel=(fid in D.in_game.get(g["id"], {})) if g else True,
                    wiki=WIKI + _wiki_title(D, f))
    finally:
        con.close()


def _wiki_title(D, f):
    base = next((x for x in D.forms.values() if x["art"] == f["art"] and x["standard"]), f)
    return base["name"].replace(" ", "_")


# ------------------------------------------------------------------ Typen und Teams

def type_chart(p):
    D = data()
    if not D:
        return {}
    g, gen, ch = game_of(D, p.get("spiel"))
    return {"gen": gen, "typen": [{"id": t, "name": D.tname(t)} for t in ch],
            "tabelle": {str(a): {str(d): f for d, f in ch[a].items()} for a in ch}}


def _members(D, ids, g, gen):
    out = []
    for i in ids or []:
        f = D.forms.get(_int(i))
        if f:
            out.append(member(D, f, g, gen))
    return out


def team_view(body):
    """Bewertung eines Teams: Kriterien, offene Schwächen, Matrix."""
    D = data()
    if not D:
        return {}
    g, gen, ch = game_of(D, body.get("spiel"))
    ctx = team.Ctx(ch, _int(body.get("tempo")) or team.SPEED)
    ms = _members(D, body.get("ids"), g, gen)
    ev = team.evaluate(ms, ctx, body.get("gewichte"))
    ev["matrix"] = {str(m["id"]): {str(a): f for a, f in ctx.dvec(m).items()} for m in ms}
    ev["mitglieder"] = [row(D, D.forms[m["id"]], g, gen) for m in ms]
    return ev


def _pool(D, body, g, gen):
    p = dict(body.get("filter") or {}, spiel=body.get("spiel"))
    _, _, found = candidates(D, p)
    return [member(D, f, g, gen) for f, _ in found]


def team_suggest(body):
    D = data()
    if not D:
        return {"rows": []}
    g, gen, ch = game_of(D, body.get("spiel"))
    ctx = team.Ctx(ch, _int(body.get("tempo")) or team.SPEED)
    ms = _members(D, body.get("ids"), g, gen)
    pool = _pool(D, body, g, gen)
    rows = team.suggest(ms, pool, ctx, body.get("gewichte"), n=12, tname=D.tname)
    return {"rows": [dict(r, **row(D, D.forms[r["id"]], g, gen)) for r in rows]}


def team_optimize(body):
    D = data()
    if not D:
        return {"teams": []}
    g, gen, ch = game_of(D, body.get("spiel"))
    ctx = team.Ctx(ch, _int(body.get("tempo")) or team.SPEED)
    fixed = _members(D, body.get("fest"), g, gen)
    pool = _pool(D, body, g, gen)
    best = team.optimize(pool, ctx, body.get("gewichte"), fixed=fixed)
    out = []
    for sc, ms in best:
        ev = team.evaluate(ms, ctx, body.get("gewichte"))
        out.append({"wertung": sc, "ids": [m["id"] for m in ms], "kriterien": ev["kriterien"], "offen": ev["offen"],
                    "nicht_abgedeckt": ev["nicht_abgedeckt"], "mitglieder": [row(D, D.forms[m["id"]], g, gen) for m in ms]})
    return {"teams": out, "pool": len(pool)}


def team_matchup(body):
    D = data()
    if not D:
        return {"rows": []}
    g, gen, ch = game_of(D, body.get("spiel"))
    ctx = team.Ctx(ch)
    ms = _members(D, body.get("ids"), g, gen)
    enemy = {"typen": [t for t in (body.get("typen") or []) if _int(t)], "init": None}
    if _int(body.get("gegner")) in D.forms:
        ef = D.forms[_int(body["gegner"])]
        enemy = {"typen": form_types(D, ef, gen), "init": ef["init"], "name": ef["name"]}
    enemy["typen"] = [int(t) for t in enemy["typen"]]
    if not enemy["typen"]:
        return {"rows": []}
    rows = team.matchup(ms, enemy, ctx, D.tname)
    return {"rows": [dict(r, name=D.forms[r["id"]]["name"]) for r in rows], "gegner": enemy}


def games():
    D = data()
    return [{"kennung": g["kennung"], "name": g["name"], "gen": g["gen"], "pokemon": len(D.in_game.get(g["id"], {}))}
            for g in reversed(D.games)] if D else []


def meta():
    D = data()
    if not D:
        return {}
    return {"typen": [{"id": t, "name": n, "kennung": D.type_key.get(t)} for t, n in D.types.items()],
            "formen": len([f for f in D.forms.values() if f["relevant"]]), "attacken": len(D.moves), "max_gen": D.max_gen}


def pruefung():
    """Abweichungen PokéAPI und Showdown samt deiner Entscheidung."""
    if not db.has_data():
        return []
    con = db.game()
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM pruefung ORDER BY art, name")]
    finally:
        con.close()
    u = db.user()
    try:
        dec = {r["schluessel"]: r["wert"] for r in u.execute("SELECT schluessel, wert FROM entscheidung WHERE art = 'pruefung'")}
    finally:
        u.close()
    for r in rows:
        r["key"] = f"{r['art']}:{r['schluessel']}:{r['feld']}"
        r["entscheidung"] = dec.get(r["key"], "")
    return rows
