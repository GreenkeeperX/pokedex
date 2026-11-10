"""Abfragen für die Oberfläche: Pokémon-Liste mit Filtern, Detailseite, Attacken je Spiel, Typtabelle, Teams.

Was oft gebraucht wird (Typen, Formen, Attacken, Spiele), hält Daten im Speicher und lädt neu, sobald der
Abgleich eine neue pokeapi.db gebaut hat. Lernlisten, Fundorte und Entwicklungen kommen je Anfrage aus der Datenbank.
"""
import json
import os
import re
import threading

from . import attacken, db, importer, showdown, team, typen

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
        # Gebiete je Spiel (PKHeX) mit den Formen, die dort fest vorkommen (ohne Massenauftreten)
        self.areas = {}
        try:
            for sp, gebiet, nr, fid in con.execute("SELECT spiel, gebiet, MIN(gebiet_nr), form FROM fundort WHERE art IN (0, 1, 2) "
                                                   "GROUP BY spiel, gebiet, form ORDER BY 3"):
                self.areas.setdefault(sp, {}).setdefault(gebiet, set()).add(fid)
        except Exception:
            pass
        self.methods = _names(con, "pokemon_move_method_prose", "pokemon_move_method_id")
        self.method_key = dict(con.execute("SELECT id, identifier FROM pokemon_move_methods"))
        # TM-Nummern je Spiel und Attacke: tm012 → TM012, hm03 → VM03, tr05 → TP05
        self.machines = {}
        try:
            rows = con.execute("SELECT m.version_group_id, m.move_id, i.identifier FROM machines m JOIN items i ON i.id = m.item_id").fetchall()
            wide = {vg for vg, _, ident in rows if re.fullmatch(r"tm\d{3,}", ident or "")}
            for vg, mid, ident in rows:
                self.machines[(vg, mid)] = machine_label(ident, 3 if vg in wide else 2)
        except Exception:
            pass
        # Attackenwerte je Spiel aus dem PokéWiki (Legenden: Arceus mit Kraft- und Tempostil)
        self.game_moves = {}
        try:
            for r in con.execute("SELECT * FROM attacke_spiel"):
                self.game_moves[(r["spiel"], r["attacke"])] = dict(r)
        except Exception:
            pass
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
    formen (relevant|standard|alle), kampf, gegen (klar: nur klar stark), nur (fav|gef: Favoriten oder Gefangene),
    gebiet (kommt dort im Spiel vor, aus PKHeX)."""
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
    area = D.areas.get(g["kennung"] if g else "", {}).get(str(p.get("gebiet") or ""))
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
        if area is not None and f["id"] not in area:
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
    w = D.game_moves.get((g["kennung"], m["id"])) if g else None
    if w:
        v = dict(v, kraft=w["kraft"], tempo=w["tempo"], quelle="PokéWiki")
        for k in ("staerke", "genauigkeit", "ap"):
            if w[k] is not None and w[k] != v.get(k):
                v[k], v["geaendert"] = w[k], True
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


def machine_label(ident, width=2):
    """tm12 → TM12, hm03 → VM03, tr05 → TP05; width: Stellen (Karmesin/Purpur zählt dreistellig)."""
    m = re.match(r"(tm|hm|tr)(\d+)$", ident or "")
    return {"tm": "TM", "hm": "VM", "tr": "TP"}[m.group(1)] + m.group(2).zfill(width) if m else ""


def how(D, meth, lv, mastery, mid=None, vg=None):
    key = D.method_key.get(meth, "")
    if key == "machine" and (vg, mid) in D.machines:
        return D.machines[(vg, mid)]
    if key == "level-up":
        txt = f"Level {lv}" if lv and lv > 1 else "Level 1" if lv == 1 else "Start"
        return txt + (f", Beherrschung ab {mastery}" if mastery else "")
    return {"machine": "TM", "egg": "Ei", "tutor": "Lehrer"}.get(key) or D.methods.get(meth) or key


ROLLEN = {"Fast Attacker": "schneller Angreifer", "Bulky Attacker": "robuster Angreifer", "Setup Sweeper": "Aufbau und Angriff",
          "Bulky Setup": "robuster Aufbau", "Fast Bulky Setup": "schneller, robuster Aufbau", "Bulky Support": "robuste Unterstützung",
          "Fast Support": "schnelle Unterstützung", "Wallbreaker": "Mauerbrecher", "Staller": "Hinhalten", "Tera Blast user": "Tera-Blast",
          "AV Pivot": "Wechsler mit Offensivweste", "Generalist": "Allrounder", "Berry Sweeper": "Angriff mit Beere",
          "Z-Move user": "Z-Attacke", "Dynamax User": "Dynamax", "Thief user": "mit Raub"}


def _sd_move_map(D, con):
    """{Showdown-Kennung: Attacken-ID}; Kraftreserve-Varianten (hiddenpowerfire) zählen als Kraftreserve."""
    if getattr(D, "sd_moves", None) is None:
        D.sd_moves = {importer._sd_key(k): i for i, k in con.execute("SELECT id, kennung FROM attacke")}
    return D.sd_moves


def proven_sets(con, D, f, g, gen, rows):
    """Bewährte Sets aus Showdown (Random Battle) für die Generation des Spiels: Rolle, Attacken (lernbar oder nicht),
    Vorschlag für vier (Schaden nach Wertung, dann Status), Fähigkeiten. Nur Sets derselben Generation; nicht für die
    Legenden-Spiele (andere Kämpfe)."""
    if g and g["kennung"].startswith("legends-"):
        return [], None
    names = [showdown.sd_id(f["kennung"])]
    base = next((x for x in D.forms.values() if x["art"] == f["art"] and x["standard"]), None)
    if base and base["id"] != f["id"] and base["typen"] == f["typen"]:
        names.append(showdown.sd_id(base["kennung"]))        # Form ohne eigene Sets, gleiche Typen: die der Standardform
    try:
        found = []
        for name in names:
            found = con.execute("SELECT gen, rolle, attacken, faehigkeiten, tera, level FROM moveset WHERE pokemon = ? AND gen = ?",
                                (name, gen)).fetchall()
            if found:
                break
    except Exception:
        return [], None
    if not found:
        return [], None
    use = found[0]["gen"]
    mm = _sd_move_map(D, con)
    score = {r["id"]: r.get("wertung", 0) for r in rows}
    out = []
    for r in found:
        if r["gen"] != use:
            continue
        moves = []
        for k in json.loads(r["attacken"]):
            mid = mm.get(k) or (mm.get("hiddenpower") if k.startswith("hiddenpower") else None)
            m = D.moves.get(mid)
            if m and all(x["id"] != mid for x in moves):
                moves.append({"id": mid, "name": m["name"], "typ": m["typ"], "lernbar": mid in score})
        pick = sorted((x for x in moves if x["lernbar"]), key=lambda x: -(score.get(x["id"]) or 0))
        out.append({"rolle": ROLLEN.get(r["rolle"], r["rolle"]), "attacken": moves, "vorschlag": [x["id"] for x in pick[:4]],
                    "faehigkeiten": json.loads(r["faehigkeiten"] or "[]"), "level": r["level"]})
    return out, use


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
        entry["wege"].append((D.method_key.get(meth, ""), lv, mastery, how(D, meth, lv, mastery, mid, used["id"] if used else None)))
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
                "jetzt": now, "geaendert": bool(v.get("geaendert")), "text": v.get("text"), "kurz": v.get("kurz") or "",
                "kraft": v.get("kraft"), "tempo": v.get("tempo")}
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
    elif used and used["kennung"] == LA and any(k[0] == LA for k in D.game_moves):
        hint = ("Stärke, Genauigkeit und AP für Legenden: Arceus aus dem PokéWiki; unter der Stärke stehen Kraftstil "
                "und Tempostil (Kraft / Tempo).")
    elif used and used["kennung"] == LA:
        hint = ("Stärke und Genauigkeit stammen aus den Hauptspielen: die PokéAPI hat für Legenden: Arceus keine eigenen Werte. "
                "Dort weichen sie teils ab (Kraft- und Tempostil); die echten Werte kommen mit dem PokéWiki-Abruf.")
    sets, sets_gen = proven_sets(con, D, f, g, gen, out + status)
    return {"spiel": used["kennung"] if used else "", "spiel_name": used["name"] if used else "", "attacken": out,
            "moveset": moveset, "status": status, "hinweis": hint, "standard": standard, "sets": sets, "sets_gen": sets_gen}


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
                     "geaendert": bool(v.get("geaendert")), "text": v.get("text"), "kurz": v.get("kurz") or "", "gen": m["gen"], "lernen": learners.get(m["id"], 0),
                     "kraft": v.get("kraft"), "tempo": v.get("tempo"),
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


def _range(xs):
    lo, hi = min(a for a, _ in xs), max(b for _, b in xs)
    return f"{lo}" if lo == hi else f"{lo}–{hi}"


ZEIT_DE = {"Dawn": "Morgen", "Day": "Tag", "Dusk": "Abend", "Night": "Nacht"}
WETTER_DE = {"None": "klar", "Sunny": "sonnig", "Cloudy": "bewölkt", "Rain": "Regen", "Snow": "Schnee", "Drought": "starke Sonne",
             "Fog": "Nebel", "Rainstorm": "Gewitter", "Snowstorm": "Schneesturm"}


def _pct(x):
    return f"{x:.0f} %" if x >= 10 else f"{x:.1f} %".replace(".", ",")


def _cond_text(d, order, names, all_label):
    """Anteile je Tageszeit oder Wetter als kurzer Text: „immer“, „Nacht 88 %“ oder „Regen 45 %, sonst 20 %“."""
    present = [k for k in order if d.get(k)]
    vals = sorted(d[k] for k in present)
    if not vals:
        return ""
    if len(present) == len(order) and vals[0] >= 0.8 * vals[-1]:
        return all_label
    if len(present) < len(order):
        return ", ".join(f"{names[k]} {_pct(d[k])}" for k in present)
    base = vals[len(vals) // 2]
    special = [k for k in present if abs(d[k] - base) > 0.2 * base]
    return ", ".join(f"{names[k]} {_pct(d[k])}" for k in special) + f", sonst {_pct(base)}"


def spawn_summary(con, spiel, pid):
    """Je Gebiet: höchster Anteil an Spawnpunkten je Tageszeit und je Wetter (Alpha nur, wenn es sonst nichts gibt),
    als Text, dazu Höchstwert und Zahl der Punkte."""
    try:
        rows = con.execute("SELECT gebiet, karte, name, alpha, anteile FROM spawn WHERE spiel = ? AND form = ?", (spiel, pid)).fetchall()
    except Exception:
        return {}
    has_normal = {r["gebiet"] for r in rows if not r["alpha"]}
    out = {}
    for r in rows:
        if r["alpha"] and r["gebiet"] in has_normal:
            continue
        e = out.setdefault(r["gebiet"], {"z": {}, "w": {}, "max": 0, "punkte": set(), "karte": r["karte"]})
        e["punkte"].add(r["name"])
        for cell, pct in json.loads(r["anteile"]).items():
            zt, _, wt = cell.partition("/")
            e["z"][zt] = max(e["z"].get(zt, 0), pct)
            e["w"][wt] = max(e["w"].get(wt, 0), pct)
            e["max"] = max(e["max"], pct)
    return {k: {"zeit": _cond_text(e["z"], importer.ZEITEN, ZEIT_DE, "immer"),
                "wetter": _cond_text(e["w"], importer.WETTER, WETTER_DE, "jedes"),
                "max": e["max"], "punkte": len(e["punkte"]), "karte": e["karte"]} for k, e in out.items()}


def map_data(karte, p):
    """Karte eines Gebiets: Spawnpunkte (x, z in Spielkoordinaten) mit den Pokémon dort, Tageszeit und Anteil.
    p: spiel (bisher nur legends-arceus)."""
    D = data()
    if not D:
        return None
    spiel = "legends-arceus"
    con = db.game()
    try:
        try:
            pts = con.execute("SELECT nr, name, x, z, alpha, gebiet FROM spawnpunkt WHERE spiel = ? AND karte = ?", (spiel, karte)).fetchall()
            rows = con.execute("SELECT name, form, alpha, anteile FROM spawn WHERE spiel = ? AND karte = ?", (spiel, karte)).fetchall()
            maps = [dict(r) for r in con.execute("SELECT karte, gebiet, COUNT(*) n FROM spawnpunkt WHERE spiel = ? GROUP BY karte "
                                                  "ORDER BY MIN(rowid)", (spiel,))]
        except Exception:
            return None
    finally:
        con.close()
    if not pts:
        return None
    mons = {}
    for r in rows:
        f = D.forms.get(r["form"])
        cells = json.loads(r["anteile"])
        z, w = {}, {}
        for cell, pct in cells.items():
            zt, _, wt = cell.partition("/")
            z[zt] = max(z.get(zt, 0), pct)
            w[wt] = max(w.get(wt, 0), pct)
        mons.setdefault(r["name"], []).append({
            "id": r["form"], "name": f["name"] if f else str(r["form"]), "alpha": bool(r["alpha"]), "max": max(cells.values()),
            "zeit": _cond_text(z, importer.ZEITEN, ZEIT_DE, "immer"), "wetter": _cond_text(w, importer.WETTER, WETTER_DE, "jedes")})
    for v in mons.values():
        v.sort(key=lambda m: (m["alpha"], -m["max"]))
    folder = os.path.join(db.data_dir(), "karten", karte)
    return {"karte": karte, "gebiet": pts[0]["gebiet"], "karten": maps,
            "kacheln": len(os.listdir(folder)) if os.path.isdir(folder) else 0,
            "punkte": [{"nr": r["nr"], "x": r["x"], "z": r["z"], "alpha": bool(r["alpha"]), "mons": mons.get(r["name"], [])}
                       for r in pts]}


def _enc_pkhex(con, g, pid):
    """Fundorte aus den Spieldaten (PKHeX): je Gebiet und Art die Stellen, Level und Alpha-Level. None ohne Daten."""
    try:
        rows = con.execute("SELECT gebiet, gebiet_nr, stellen, art, min, max, alpha FROM fundort WHERE spiel = ? AND form = ?",
                           (g["kennung"], pid)).fetchall()
        if not rows and not con.execute("SELECT 1 FROM fundort WHERE spiel = ? LIMIT 1", (g["kennung"],)).fetchone():
            return None
    except Exception:
        return None
    groups = {}
    for r in rows:
        e = groups.setdefault((r["gebiet_nr"], r["art"]), {"gebiet": r["gebiet"], "stellen": {}, "lv": [], "alpha": [], "immer": False})
        lv = (r["min"], r["max"])
        (e["alpha"] if r["alpha"] else e["lv"]).append(lv)
        e["immer"] = e["immer"] or r["alpha"] == 2
        for x in (json.loads(r["stellen"] or "[]") or [""]) if r["art"] != importer.FEST else []:
            st = e["stellen"].setdefault(x, {"lv": [], "alpha": []})
            (st["alpha"] if r["alpha"] else st["lv"]).append(lv)
    spawn = spawn_summary(con, g["kennung"], pid)
    out = []
    for (nr, art), e in sorted(groups.items()):
        sp = spawn.get(e["gebiet"]) if art == 0 else None
        places = [{"name": k, "level": _range(v["lv"]) if v["lv"] else "", "alpha": _range(v["alpha"]) if v["alpha"] else ""}
                  for k, v in e["stellen"].items()]
        places.sort(key=lambda x: (int((x["level"] or x["alpha"]).split("–")[0] or 0), x["name"]))
        out.append({"ort": e["gebiet"], "stellen": places, "methode": importer.PKHEX_ART.get(art, str(art)),
                    "level": _range(e["lv"]) if e["lv"] else "", "alpha": _range(e["alpha"]) if e["alpha"] else "",
                    "nur_alpha": not e["lv"] and bool(e["alpha"]), "bedingungen": [], "editionen": [],
                    "zeit": sp["zeit"] if sp else "", "wetter": sp["wetter"] if sp else "",
                    "chance": sp["max"] if sp else 0, "punkte": sp["punkte"] if sp else 0, "karte": sp["karte"] if sp else ""})
    return out


def _enc(con, g, pid):
    """Fundorte im Spiel: Ort, Methode, Level, Bedingungen. Aus den Spieldaten (PKHeX), wo es sie gibt."""
    if not g:
        return []
    own = _enc_pkhex(con, g, pid)
    if own is not None:
        return own
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


BALLS = (("Pokéball", 1), ("Superball", 1.5), ("Hyperball", 2))
GROWTH_DE = {"slow": "langsam", "medium": "mittel", "fast": "schnell", "medium-slow": "mittel-langsam",
             "slow-then-very-fast": "erratisch", "fast-then-very-slow": "fluktuierend"}
STAT_KEYS = ("kp", "ang", "vert", "spang", "spvert", "init")


def catch_chance(rate, ball=1.0, hp_share=1.0, status=1.0, gen=9):
    """Fangchance in % (ohne kritischen Fang und Level-Boni): a = (3 − 2·KP-Anteil)/3 · Fangrate · Ball · Status.
    Bis Generation 4 gelingt der Fang mit a/255; ab Generation 5 muss jede Rüttelprobe mit (65536 / (255/a)^0.1875)
    / 65536 gelingen, in Generation 5 dreimal, ab Generation 6 viermal."""
    a = (3 - 2 * hp_share) / 3 * rate * ball * status
    if a >= 255:
        return 100.0
    if a <= 0:
        return 0.0
    if gen <= 4:
        return round(100 * a / 255, 1)
    b = int(65536 / (255 / a) ** 0.1875)
    return round(100 * (b / 65536) ** (3 if gen == 5 else 4), 1)


def catch_table(rate, gen):
    """Fangchance je Ball bei vollen KP, bei 1 KP, bei 1 KP mit Paralyse, Gift oder Verbrennung (×1,5) und bei 1 KP mit
    Schlaf oder Einfrieren (ab Generation 5 ×2,5, sonst ×2)."""
    sleep = sleep_factor(gen)
    return [{"ball": n, "voll": catch_chance(rate, f, gen=gen), "rot": catch_chance(rate, f, 0, gen=gen),
             "status": catch_chance(rate, f, 0, 1.5, gen=gen), "schlaf": catch_chance(rate, f, 0, sleep, gen=gen)} for n, f in BALLS]


def sleep_factor(gen):
    return 2.5 if gen >= 5 else 2


def _more(con, f, g, gen):
    """Mehr Details: Fangrate mit Fangchance, Geschlecht, Wachstum, Ei-Gruppen, Ei-Zyklen, EV-Ausbeute. Was es im Spiel
    nicht gibt, bleibt weg (Legenden: Arceus: keine Eier, keine EVs)."""
    out = {}
    try:
        sp = con.execute("SELECT capture_rate, gender_rate, hatch_counter, base_happiness, growth_rate_id FROM pokemon_species "
                         "WHERE id = ?", (f["art"],)).fetchone()
    except Exception:
        return out
    if not sp:
        return out
    kennung = g["kennung"] if g else ""
    if sp["capture_rate"] is not None:
        out["fangrate"] = sp["capture_rate"]
        out["fangen"] = catch_table(sp["capture_rate"], gen)
        out["schlaf_faktor"] = str(sleep_factor(gen)).replace(".", ",")
        out["fang_grob"] = gen <= 2 or kennung.startswith("legends-")
    if sp["gender_rate"] is not None and gen >= 2:
        gr = sp["gender_rate"]
        out["geschlecht"] = "geschlechtslos" if gr < 0 else f"{100 - gr * 12.5:g} % männlich, {gr * 12.5:g} % weiblich"
    try:
        gk = con.execute("SELECT identifier FROM growth_rates WHERE id = ?", (sp["growth_rate_id"],)).fetchone()
        if gk:
            out["wachstum"] = GROWTH_DE.get(gk[0], gk[0])
    except Exception:
        pass
    if kennung != "legends-arceus":
        try:
            eg = [r[0] for r in con.execute(
                "SELECT COALESCE(p.name, pe.egg_group_id) FROM pokemon_egg_groups pe LEFT JOIN egg_group_prose p "
                "ON p.egg_group_id = pe.egg_group_id AND p.local_language_id = 6 WHERE pe.species_id = ?", (f["art"],))]
        except Exception:
            eg = []
        if eg and gen >= 2:
            out["eigruppen"] = eg
            if sp["hatch_counter"] is not None:
                out["eizyklen"] = sp["hatch_counter"]
        if gen >= 3:
            try:
                ev = [(r[0], r[1]) for r in con.execute("SELECT stat_id, effort FROM pokemon_stats WHERE pokemon_id = ? AND effort > 0",
                                                         (f["id"],))]
                out["ev"] = [{"wert": STAT_KEYS[s - 1], "punkte": e} for s, e in ev if 1 <= s <= 6]
            except Exception:
                pass
    return out


def _extras(fid):
    """Welche Extras (schillernd, animiert, Ruf) für eine Form schon geladen sind."""
    out = {}
    for kind in ("shiny", "shinyart", "anim", "rufe"):
        folder = os.path.join(db.data_dir(), kind)
        out[kind] = any(os.path.isfile(os.path.join(folder, f"{fid}{e}")) for e in (".png", ".gif", ".mp3", ".ogg"))
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
                    entwicklung=_evolutions(con, D, f), fundorte=_enc(con, g, fid), fundquelle="PKHeX" if g and g["kennung"] in D.areas else "PokéAPI", formen=siblings, attacken=moves,
                    im_spiel=(fid in D.in_game.get(g["id"], {})) if g else True, mehr=_more(con, f, g, gen), extras=_extras(fid),
                    wiki=WIKI + _wiki_title(D, f), getragen=_held(con, g, f))
    finally:
        con.close()


def _held(con, g, f):
    """Getragene Items wilder Pokémon im Spiel (PokéWiki): [{item, bild, prozent, elite}]."""
    if not g:
        return []
    try:
        rows = con.execute("SELECT item, item_id, prozent, elite FROM getragen WHERE spiel = ? AND art = ?", (g["kennung"], f["art"])).fetchall()
    except Exception:
        return []
    return [{"item": r[0], "id": r[1], "prozent": r[2], "elite": bool(r[3])} for r in rows]


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


def item_list(p):
    """Items im Spiel, sortiert nach Tasche und Name. Hat die PokéAPI Beschreibungen für das Spiel, sind das genau seine
    Items; sonst die Items der Generation laut Spielindex, mit Hinweis (zu viele, aber keins fehlt). Maschinen tragen die
    Attacke des Spiels, Items mit Bild die Marke `bild`; unfertige Einträge (Platzhalter im Text) sind markiert."""
    D = data()
    if not D:
        return {}
    g, gen, _ = game_of(D, p.get("spiel"))
    vg = g["id"] if g else None
    con = db.game()
    try:
        try:
            rows = con.execute("SELECT * FROM item").fetchall()
        except Exception:
            rows = []
        tms = {}
        if vg:
            try:
                for r in con.execute("SELECT m.item_id, a.name, a.typ, a.klasse, a.staerke, a.genauigkeit, a.ap, a.kurz FROM machines m "
                                     "JOIN attacke a ON a.id = m.move_id WHERE m.version_group_id = ?", (vg,)):
                    tms[r[0]] = {"name": r[1], "typ": r[2], "klasse": r[3], "staerke": r[4], "genauigkeit": r[5], "ap": r[6], "kurz": r[7] or ""}
            except Exception:
                tms = {}
    finally:
        con.close()
    folder = os.path.join(db.data_dir(), "itembild")
    have = {os.path.splitext(x)[0] for x in os.listdir(folder)} if os.path.isdir(folder) else set()
    exact = bool(vg) and sum(1 for r in rows if vg in json.loads(r["spiele"] or "[]")) >= 50
    out = []
    for r in rows:
        if exact and vg not in json.loads(r["spiele"] or "[]"):
            continue
        if g and not exact and gen not in json.loads(r["gens"] or "[]"):
            continue
        if g and not exact and not tms and r["tasche"] == "Maschinen":       # Spiel ohne Maschinen (etwa Legenden: Arceus)
            continue
        keys = r.keys()
        e = {"id": r["id"], "name": r["name"], "tasche": r["tasche"], "text": r["text"], "englisch": r["sprache"] == "en",
             "preis": r["preis"], "art": r["art"] if "art" in keys else "", "wirkung": r["wirkung"] if "wirkung" in keys else "",
             "wert": r["wert"] if "wert" in keys else None, "unfertig": bool(r["unfertig"]) if "unfertig" in keys else "[VAR" in (r["text"] or ""),
             "bild": str(r["id"]) in have}
        if r["id"] in tms:
            e["attacke"] = tms[r["id"]]
        out.append(e)
    order = list(importer.TASCHEN.values())
    out.sort(key=lambda x: (order.index(x["tasche"]) if x["tasche"] in order else 99, x["name"].lower()))
    note = "" if exact or not g else (f"Die PokéAPI hat für dieses Spiel keine eigene Item-Liste; gezeigt sind alle Items "
                                      f"der Generation {gen}, darunter auch welche, die es hier nicht gibt.")
    return {"gen": gen, "items": out, "taschen": [t for t in order if any(x["tasche"] == t for x in out)], "hinweis": note}


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


def foreign_moves(D, ms, details, g):
    """{Platz: [Attacken-IDs]}: gewählte Attacken, die das Pokémon im Spiel nicht lernen kann (nur mit eigener Lernliste)."""
    if not g:
        return {}
    out = {}
    con = db.game()
    try:
        for m in ms:
            chosen = _ints((details[m["slot"]] if m["slot"] < len(details) else {}).get("attacken"))
            if not chosen:
                continue
            ls, used = learnset(con, D, D.forms[m["id"]], g)
            if not used or used["id"] != g["id"]:
                continue
            known = {x[0] for x in ls}
            bad = [i for i in chosen if i not in known]
            if bad:
                out[str(m["slot"])] = bad
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
    ev["fremde_attacken"] = foreign_moves(D, ms, details, g)
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


HOME = "pokemon-home"       # kein Spiel der PokéAPI: alle Pokémon mit den neuesten Werten, eigene Sammlung


def games():
    D = data()
    if not D:
        return []
    home = {"kennung": HOME, "name": "Pokémon HOME", "gen": 0, "home": True, "gebiete": [],
            "pokemon": sum(1 for f in D.forms.values() if f["relevant"])}
    return [home] + [{"kennung": g["kennung"], "name": g["name"], "gen": g["gen"], "pokemon": len(D.in_game.get(g["id"], {})),
                      "gebiete": list(D.areas.get(g["kennung"], {}))} for g in reversed(D.games)]


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
