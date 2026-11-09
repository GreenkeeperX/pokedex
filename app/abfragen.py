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
    """Kurzform für Listen. nr: Nummer im Regional-Dex des Spiels, sonst die nationale."""
    if nr is None and g:
        nr = D.in_game.get(g["id"], {}).get(f["id"])
    return {"id": f["id"], "art": f["art"], "nr": nr if nr is not None else f["art"], "name": f["name"],
            "typen": form_types(D, f, gen), "werte": f["werte"], "summe": f["summe"], "gen": f["gen"],
            "legendaer": f["legendaer"] or f["mysterioes"], "endstufe": f["endstufe"], "kampfform": f["kampfform"],
            "standard": f["standard"], "relevant": f["relevant"]}


SORTS = {"nr": lambda r: (r["nr"] or 99999, r["id"]), "name": lambda r: (r["name"].lower(), r["id"]),
         "summe": lambda r: (-r["summe"], r["id"]), "init": lambda r: (-r["werte"][5], r["id"]),
         "ang": lambda r: (-r["werte"][1], r["id"]), "spang": lambda r: (-r["werte"][3], r["id"]),
         "kp": lambda r: (-r["werte"][0], r["id"]), "vert": lambda r: (-r["werte"][2] - r["werte"][4], r["id"])}


def duel(own, target, ch):
    """Typ-Duell gegen einen Typ: (austeilen, einstecken, Stufe). austeilen = bester eigener Typ gegen den Zieltyp,
    einstecken = Attacken des Zieltyps gegen beide eigenen Typen (multipliziert). Stufe 2 = klar stark (trifft ×2 und
    steckt höchstens ×½ ein), 1 = stark (trifft ×2, steckt ×1 ein), 0 = ausgeglichen, -1 = schwach (steckt ×2 ein und
    trifft höchstens normal). Tentoxa (Wasser/Gift) gegen Pflanze: Gift trifft ×2, Pflanze trifft Wasser ×2, Gift ×½,
    zusammen ×1: Stufe 1. Gegen Feuer: Wasser trifft ×2, Feuer trifft ×½: Stufe 2."""
    dealt = max(((ch.get(a) or {}).get(target, 1) for a in own), default=1)
    taken = 1.0
    for d in own:
        taken *= (ch.get(target) or {}).get(d, 1)
    if dealt > 1 and taken <= 0.5:
        level = 2
    elif dealt > 1 and taken <= 1:
        level = 1
    elif taken > 1 and dealt <= 1:
        level = -1
    else:
        level = 0
    return dealt, taken, level


def strong_against(own, target, ch, clear=False):
    """Stark gegen einen Typ: ein eigener Typ trifft ihn sehr effektiv, und seine Attacken treffen nicht sehr effektiv
    (clear: höchstens ×½)."""
    return duel(own, target, ch)[2] >= (2 if clear else 1)


def own_marks(table, spiel):
    """IDs mit Marke (favorit oder gefangen) aus user.db."""
    if table not in ("favorit", "gefangen"):
        return set()
    con = db.user()
    try:
        return {r[0] for r in con.execute(f"SELECT form FROM {table} WHERE spiel = ?", (str(spiel or ""),))}
    except Exception:
        return set()
    finally:
        con.close()


def candidates(D, p):
    """Formen nach Filtern. p: spiel, q, typ, typ2, gen (genmodus bis|nur), endstufe, ohne_leg, min,
    formen (relevant|standard|alle), kampf, gegen (klar: nur klar stark), nur (fav|gef: Favoriten oder Gefangene)."""
    g, gen, ch = game_of(D, p.get("spiel"))
    in_game = D.in_game.get(g["id"], {}) if g else None
    q = str(p.get("q") or "").strip().lower()
    want = _ints(p.get("typen")) + [t for t in (_int(p.get("typ")), _int(p.get("typ2"))) if t]
    against = _ints(p.get("gegen"))
    drop = set(_ints(p.get("ohne")))
    mode_and = (p.get("modus") or "und") == "und"
    max_gen = _int(p.get("gen"))
    only_gen = p.get("genmodus") == "nur"
    clear = bool(p.get("klar"))
    nur = {"fav": "favorit", "gef": "gefangen"}.get(p.get("nur"))
    mine = own_marks(nur, p.get("spiel")) if nur else None
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
        if mine is not None and f["id"] not in mine:
            continue
        if max_gen and (f["gen"] != max_gen if only_gen else f["gen"] > max_gen):
            continue
        if p.get("endstufe") and not f["endstufe"]:
            continue
        if p.get("ohne_leg") and (f["legendaer"] or f["mysterioes"]):
            continue
        if f["summe"] < mn:
            continue
        ts = form_types(D, f, gen)
        if want and (not all(t in ts for t in want) if mode_and else not any(t in ts for t in want)):
            continue
        if against:
            hits = [strong_against(ts, t, ch, clear) for t in against]
            if not (all(hits) if mode_and else any(hits)):
                continue
        if drop and drop & set(ts):
            continue
        nr = in_game.get(f["id"]) if in_game else None
        if q:
            hit = q in f["name"].lower() or q in f["kennung"] or (q.isdigit() and int(q) in (f["art"], nr))
            if not hit:
                continue
        out.append((f, nr))
    return g, gen, out


def rows_of(ids, spiel):
    """Kurzformen zu IDs (für Favoriten), in der Reihenfolge der IDs."""
    D = data()
    if not D:
        return []
    g, gen, _ = game_of(D, spiel)
    in_game = D.in_game.get(g["id"], {}) if g else {}
    return [row(D, D.forms[i], g, gen, in_game.get(i)) for i in ids if i in D.forms]


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


def _ints(v):
    """Liste von Zahlen aus "1,2" oder [1, 2]."""
    items = v if isinstance(v, (list, tuple)) else str(v or "").split(",")
    return [i for i in (_int(x) for x in items) if i is not None]


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
    # Wie im Spiel: ein Pokémon kennt die letzten vier Level-Attacken bis zu seinem Level; ohne Level die ersten vier
    lvl_moves = sorted(((lv or 0, mid) for mid, meth, lv, _ in ls if D.method_key.get(meth) == "level-up" and mid in D.moves),
                       key=lambda x: (x[0], x[1]))
    seen_std = []
    for lv, mid in (lvl_moves if level is None else [x for x in lvl_moves if x[0] <= level]):
        if mid in seen_std:
            seen_std.remove(mid)
        seen_std.append(mid)
    standard = seen_std[:4] if level is None else seen_std[-4:]
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
        hint = ("Stärke und Genauigkeit stammen aus den Hauptspielen: die PokéAPI hat für Legenden: Arceus keine eigenen Werte. "
                "Dort weichen sie teils ab (Kraft- und Tempostil); die echten Werte kommen mit dem PokéWiki-Abruf.")
    return {"spiel": used["kennung"] if used else "", "spiel_name": used["name"] if used else "", "attacken": out,
            "moveset": moveset, "status": status, "hinweis": hint, "standard": standard}


def move_list(p):
    """Alle Attacken im Spiel mit Werten des Spiels und Wertung (Stärke × Genauigkeit mit Zu- und Abschlägen, ohne
    Eigentyp-Bonus). Filter: typen (Liste), klasse, q, lernbar (nur Attacken, die im Spiel jemand lernt). Die
    Oberfläche sortiert und filtert weiter."""
    D = data()
    if not D:
        return {"rows": []}
    g, gen, ch = game_of(D, p.get("spiel"))
    want = set(_ints(p.get("typen")) + ([_int(p.get("typ"))] if _int(p.get("typ")) else []))
    cls = _int(p.get("klasse"))
    q = str(p.get("q") or "").strip().lower()
    learners = {}
    if g:
        con = db.game()
        try:
            learners = dict(con.execute("SELECT move_id, COUNT(DISTINCT pokemon_id) FROM pokemon_moves WHERE version_group_id = ? "
                                        "GROUP BY move_id", (g["id"],)).fetchall())
        finally:
            con.close()
    rows = []
    for m in D.moves.values():
        if m["gen"] and m["gen"] > gen:
            continue
        if g and p.get("lernbar", 1) not in (0, "0", "") and m["id"] not in learners:
            continue
        v = move_view(D, m, g)
        if (want and v["typ"] not in want) or (cls and v["klasse"] != cls) or (q and q not in (v["name"] or "").lower()):
            continue
        if v["klasse"] != attacken.STATUS and v["staerke"] and v["staerke"] > 1:
            sc, why = attacken.score(v, {"typen": [v["typ"]], "ang": 1, "spang": 1}, ch)
            sc = round(sc / 1.5, 1)
            why = [w for w in why if w not in ("Eigentyp-Bonus", "passt zum stärkeren Angriffswert")]
        else:
            sc, why = 0, []
        rows.append({"id": v["id"], "name": v["name"], "typ": v["typ"], "klasse": v["klasse"], "staerke": v["staerke"],
                     "genauigkeit": v["genauigkeit"], "ap": v["ap"], "prio": v["prio"], "wertung": sc, "gruende": why,
                     "geaendert": bool(v.get("geaendert")), "text": v.get("text"), "gen": m["gen"], "lernen": learners.get(m["id"], 0),
                     "merkmale": [x for x in (v.get("merkmale") or []) if x in ("contact", "punch", "bite", "sound", "pulse", "slicing")],
                     "effekt": v.get("effekt")})
    rows.sort(key=lambda x: (-x["wertung"], x["name"]))
    return {"rows": rows, "spiel": g["kennung"] if g else ""}


def best_of_type(p):
    """Kompatibel zu 0.1: die besten Schadens-Attacken eines Typs."""
    r = move_list(dict(p, lernbar=1))
    r["rows"] = [x for x in r["rows"] if x["wertung"] > 0][: min(_int(p.get("limit")) or 30, 1000)]
    return r


def moves_of(fid, p):
    """Attacken einer Form im Spiel (für die Detailseite, ohne den Rest neu zu laden)."""
    D = data()
    if not D or fid not in D.forms:
        return None
    g, gen, _ = game_of(D, p.get("spiel"))
    con = db.game()
    try:
        return ranked_moves(con, D, D.forms[fid], g, gen, _int(p.get("level")))
    finally:
        con.close()


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


def slot_details(details, ids):
    """Level und Attacken je Platz als Liste. Seit 0.3.0 eine Liste parallel zu den Mitgliedern (dasselbe Pokémon darf
    zweimal ins Team); ältere Teams haben {id: {...}}."""
    ids = list(ids or [])
    if isinstance(details, list):
        out = [d if isinstance(d, dict) else {} for d in details[:len(ids)]]
        return out + [{}] * (len(ids) - len(out))
    details = details if isinstance(details, dict) else {}
    out = []
    for i in ids:
        d = details.get(str(i)) or details.get(i)
        out.append(d if isinstance(d, dict) else {})
    return out


def _members(D, ids, g, gen, details=None):
    """Mitglieder für die Rechnung, je Platz. details: Liste je Platz (oder alt: {id: ...}) mit "level" und "attacken";
    gewählte Schadens-Attacken bestimmen dann die Angriffstypen (sonst die Eigentypen)."""
    out = []
    ids = [_int(x) for x in ids or []]
    per = slot_details(details, ids)
    for slot, i in enumerate(ids):
        f = D.forms.get(i)
        if not f:
            continue
        d = per[slot]
        atk = []
        for mid in _ints(d.get("attacken")):
            m = D.moves.get(mid)
            if m and m["klasse"] != attacken.STATUS and m["staerke"]:
                v = move_view(D, m, g)
                if v["typ"] not in atk:
                    atk.append(v["typ"])
        out.append(dict(member(D, f, g, gen, attack_types=atk or None), slot=slot))
    return out


def improvements(D, ms, details, g, gen):
    """Je Mitglied mit gewählten Attacken: stärkere Attacken bis zu seinem Level, die es noch nicht nutzt, und Lücken
    (keine Schadens-Attacke mit Eigentyp, doppelte Typen)."""
    out = []
    con = db.game()
    try:
        for m in ms:
            d = details[m["slot"]] if m["slot"] < len(details) else {}
            chosen = _ints(d.get("attacken"))
            level = _int(d.get("level"))
            f = D.forms[m["id"]]
            r = ranked_moves(con, D, f, g, gen, level)
            by = {x["id"]: x for x in r["attacken"]}
            hints = []
            if not chosen:
                hints.append("noch keine Attacken gewählt; Vorschlag: " + ", ".join(x["name"] for x in r["moveset"]))
                out.append({"id": m["id"], "slot": m["slot"], "name": m["name"], "hinweise": hints, "besser": [],
                            "standard": r["standard"]})
                continue
            dmg = [by[i] for i in chosen if i in by]
            weakest = min((x["wertung"] for x in dmg), default=0)
            types = [x["typ"] for x in dmg]
            if dmg and not any(t in m["typen"] for t in types):
                hints.append("keine Schadens-Attacke mit Eigentyp-Bonus")
            dup = sorted({t for t in types if types.count(t) > 1})
            if dup:
                hints.append("mehrere Attacken desselben Typs: " + ", ".join(D.tname(t) for t in dup))
            if len(chosen) < 4:
                hints.append(f"nur {len(chosen)} von 4 Plätzen belegt")
            better = [{"id": x["id"], "name": x["name"], "typ": x["typ"], "wertung": x["wertung"], "gruende": x["gruende"][:3]}
                      for x in r["attacken"] if x["jetzt"] and x["id"] not in chosen and x["wertung"] > weakest * 1.15][:3]
            out.append({"id": m["id"], "slot": m["slot"], "name": m["name"], "hinweise": hints, "besser": better,
                        "schwaechste": min(dmg, key=lambda x: x["wertung"])["name"] if dmg else ""})
    finally:
        con.close()
    return out


def team_view(body):
    """Bewertung eines Teams: Kriterien, offene Schwächen, Matrix."""
    D = data()
    if not D:
        return {}
    g, gen, ch = game_of(D, body.get("spiel"))
    ctx = team.Ctx(ch, _int(body.get("tempo")) or team.SPEED)
    ms = _members(D, body.get("ids"), g, gen, body.get("details"))
    details = slot_details(body.get("details"), _ints(body.get("ids")))
    ev = team.evaluate(ms, ctx, body.get("gewichte"))
    ev["verbesserungen"] = improvements(D, ms, details, g, gen) if any(details) and not body.get("kurz") else []
    in_game = D.in_game.get(g["id"], {}) if g else None
    ev["nicht_im_spiel"] = [m["slot"] for m in ms if in_game is not None and m["id"] not in in_game]
    names = {}
    for d in details:
        for mid in _ints((d or {}).get("attacken")):
            if mid in D.moves:
                v = move_view(D, D.moves[mid], g)
                names[str(mid)] = {"name": v["name"], "typ": v["typ"], "klasse": v["klasse"], "staerke": v["staerke"]}
    ev["attacken"] = names
    ev["matrix"] = {str(m["id"]): {str(a): f for a, f in ctx.dvec(m).items()} for m in ms}
    ev["mitglieder"] = [row(D, D.forms[m["id"]], g, gen) for m in ms]
    return ev


def _pool(D, body, g, gen):
    p = dict(body.get("filter") or {}, spiel=body.get("spiel"))
    p.setdefault("formen", "relevant")
    _, _, found = candidates(D, p)
    return [member(D, f, g, gen) for f, _ in found]


def team_suggest(body):
    D = data()
    if not D:
        return {"rows": []}
    g, gen, ch = game_of(D, body.get("spiel"))
    ctx = team.Ctx(ch, _int(body.get("tempo")) or team.SPEED)
    ms = _members(D, body.get("ids"), g, gen, body.get("details"))
    pool = _pool(D, body, g, gen)
    rows = team.suggest(ms, pool, ctx, body.get("gewichte"), n=12, tname=D.tname)
    species = {m["art"] for m in ms}
    return {"rows": [dict(r, **row(D, D.forms[r["id"]], g, gen)) for r in rows],
            "schon_im_team": sum(1 for c in pool if c["art"] in species)}


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


def team_caught(body):
    """Empfehlungen aus den gefangenen Pokémon des Spiels: bessere Alternativen (Tausch mit einem Mitglied hebt die
    Wertung jetzt) und langfristig mehr Potential (ein gefangenes Pokémon, dessen Endstufe das Team heben würde)."""
    D = data()
    if not D:
        return {"alternativen": [], "potential": [], "gefangen": 0}
    g, gen, ch = game_of(D, body.get("spiel"))
    ctx = team.Ctx(ch, _int(body.get("tempo")) or team.SPEED)
    ms = _members(D, body.get("ids"), g, gen, body.get("details"))
    w = body.get("gewichte")
    in_game = D.in_game.get(g["id"], {}) if g else None
    caught = [D.forms[i] for i in sorted(own_marks("gefangen", body.get("spiel"))) if i in D.forms]
    base = team.evaluate(ms, ctx, w)["wertung"] if ms else 0.0
    ids = {m["id"] for m in ms}

    def best_place(cand):
        """Bester Platz für einen Kandidaten: (Zugewinn, Platz oder None = freier Platz)."""
        c = member(D, cand, g, gen)
        best = (-1e9, None)
        if len(ms) < team.SIZE:
            best = (team.evaluate(ms + [c], ctx, w)["wertung"] - base, None)
        for k in range(len(ms)):
            sc = team.evaluate(ms[:k] + [c] + ms[k + 1:], ctx, w)["wertung"] - base
            if sc > best[0]:
                best = (sc, k)
        return best

    alt, pot = [], []
    for f in caught:
        if f["id"] in ids:
            continue
        gain, k = best_place(f)
        if gain >= 1:
            alt.append(dict(row(D, f, g, gen), plus=round(gain, 1), slot=ms[k]["slot"] if k is not None else None,
                            statt=ms[k]["name"] if k is not None else ""))
        if f["endstufe"] or not f.get("kette"):
            continue
        finals = [x for x in D.forms.values() if x.get("kette") == f["kette"] and x["endstufe"] and x["relevant"] and not x["kampfform"]
                  and x["id"] not in ids and (in_game is None or x["id"] in in_game)]
        best = None
        for x in finals:
            gain2, k2 = best_place(x)
            if gain2 >= 1 and gain2 > max(gain, 0) + 1 and (not best or gain2 > best[0]):
                best = (gain2, k2, x)
        if best:
            gain2, k2, x = best
            pot.append(dict(row(D, f, g, gen), plus=round(gain2, 1), wird=row(D, x, g, gen),
                            slot=ms[k2]["slot"] if k2 is not None else None, statt=ms[k2]["name"] if k2 is not None else ""))
    alt.sort(key=lambda r: -r["plus"])
    pot.sort(key=lambda r: -r["plus"])
    return {"alternativen": alt[:8], "potential": pot[:8], "gefangen": len(caught), "wertung": base}


def team_matchup(body):
    """Wer im Team gegen einen Gegner passt. gegner: eine ID oder eine Liste (Gegner-Team); typen: nur Typen."""
    D = data()
    if not D:
        return {"rows": []}
    g, gen, ch = game_of(D, body.get("spiel"))
    ctx = team.Ctx(ch)
    ms = _members(D, body.get("ids"), g, gen, body.get("details"))
    foes = []
    raw = body.get("gegner")
    for i in _ints(raw if isinstance(raw, list) else [raw] if raw is not None else []):
        if i in D.forms:
            ef = D.forms[i]
            foes.append({"id": i, "typen": form_types(D, ef, gen), "init": ef["init"], "name": ef["name"]})
    if not foes and _ints(body.get("typen")):
        foes.append({"id": None, "typen": _ints(body.get("typen")), "init": None, "name": "Typen"})
    out = []
    for e in foes:
        rows = team.matchup(ms, e, ctx, D.tname)
        out.append({"gegner": e, "rows": [dict(r, name=D.forms[r["id"]]["name"]) for r in rows]})
    # Gesamtbild gegen das Gegner-Team: je Mitglied, gegen wie viele es gut oder schlecht steht
    summary = []
    for m in ms:
        good = [x["gegner"]["name"] for x in out for r in x["rows"] if r["id"] == m["id"] and r["urteil"] == "schicken"]
        bad = [x["gegner"]["name"] for x in out for r in x["rows"] if r["id"] == m["id"] and r["urteil"] == "schonen"]
        summary.append({"id": m["id"], "name": m["name"], "gut": good, "schlecht": bad})
    uncovered = [x["gegner"]["name"] for x in out if not any(r["urteil"] == "schicken" for r in x["rows"])]
    first = out[0] if out else {"gegner": None, "rows": []}
    return {"rows": first["rows"], "gegner": first["gegner"], "einzeln": out, "uebersicht": summary, "ohne_antwort": uncovered}


def games():
    D = data()
    return [{"kennung": g["kennung"], "name": g["name"], "gen": g["gen"], "pokemon": len(D.in_game.get(g["id"], {}))}
            for g in reversed(D.games)] if D else []


def meta():
    D = data()
    if not D:
        return {}
    rel = [f for f in D.forms.values() if f["relevant"] and not f["kampfform"]]
    return {"typen": [{"id": t, "name": n, "kennung": D.type_key.get(t)} for t, n in D.types.items()],
            "formen": len([f for f in D.forms.values() if f["relevant"]]), "attacken": len(D.moves), "max_gen": D.max_gen,
            "verteilung": {"werte": [sorted(f["werte"][i] for f in rel) for i in range(6)], "summe": sorted(f["summe"] for f in rel)}}


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
