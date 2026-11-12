"""Abfragen für die Oberfläche: Pokémon-Liste mit Filtern, Detailseite, Attacken je Spiel, Typtabelle, Teams.

Was oft gebraucht wird (Typen, Formen, Attacken, Spiele), hält Daten im Speicher und lädt neu, sobald der
Abgleich eine neue pokeapi.db gebaut hat. Lernlisten, Fundorte und Entwicklungen kommen je Anfrage aus der Datenbank.
"""
import json
import os
import re
import sqlite3
import threading

from . import altissimo, attacken, db, importer, mapgenie, showdown, store, team, typen

LA = "legends-arceus"          # Legenden: Arceus kennt keine Fähigkeiten und eigene Attackenwerte
NO_ABILITIES = {LA, "lets-go-pikachu-lets-go-eevee"}
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
        self.stats_past = {}           # {Form: {Generation: [sechs Basiswerte]}}, nur wo sie damals anders waren
        try:
            for fid, g, *vals in con.execute("SELECT form, gen, kp, ang, vert, spang, spvert, init FROM werte_alt"):
                self.stats_past.setdefault(fid, {})[g] = vals
        except Exception:
            pass
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
        self.in_game, self.in_dex = {}, {}
        try:
            sf = con.execute("SELECT spiel, form, nr, dex, dexk FROM spiel_form").fetchall()
        except Exception:                      # Datenbank vor 0.43: ohne Dex je Nummer
            sf = [(*r, 0, "") for r in con.execute("SELECT spiel, form, nr FROM spiel_form")]
        for sp, fid, nr, di, dk in sf:
            self.in_game.setdefault(sp, {})[fid] = nr
            if di:
                self.in_dex.setdefault(sp, {})[fid] = (di, dk or "")
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
        # Deutsche Attackentexte je Spiel (PokéAPI, ergänzt aus dem PokéWiki): {Attacke: {Spiel: [(Edition, Text, Quelle)]}}
        self.move_texts = {}
        try:
            for mid, sp, ed, txt, src in con.execute("SELECT id, spiel, edition, text, quelle FROM spieltext WHERE art = 'attacken'"):
                self.move_texts.setdefault(mid, {}).setdefault(sp, []).append((ed, txt, src))
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


def form_stats(D, f, gen):
    """(Basiswerte, Summe) einer Form in einer Generation: früher teils anders (Showdown-Mods), in Generation 1
    Sp.-Angriff = Sp.-Verteidigung = Spezial, dann zählt er in der Summe einmal."""
    vals = (getattr(D, "stats_past", {}).get(f["id"]) or {}).get(gen)
    if not vals:
        return f["werte"], f["summe"]
    return vals, sum(vals) - (vals[4] if gen == 1 else 0)


def no_abilities(g):
    """Spiele ohne Fähigkeiten: Generation 1 und 2, Let's Go und Legenden: Arceus."""
    return bool(g) and (g["kennung"] in NO_ABILITIES or (g.get("gen") or 9) <= 2)


def old_class(v, gen):
    """Bis Generation 3 hängt physisch oder speziell am Typ (Normal bis Stahl physisch, Feuer bis Unlicht speziell)."""
    if gen > 3 or v.get("klasse") == attacken.STATUS:
        return v
    try:
        t = int(v.get("typ"))
    except (TypeError, ValueError):
        return v
    return dict(v, klasse=attacken.PHYS if t <= 9 else attacken.SPEZ) if t <= 18 else v


def ability_of(D, f, g):
    """Fähigkeit für die Typwirkung: die erste normale; in Spielen ohne Fähigkeiten keine."""
    if no_abilities(g):
        return None
    for aid, hidden in f["faehigkeiten"]:
        if not hidden:
            return D.abilities.get(aid, (None,))[0]
    return None


def member(D, f, g, gen, ability=None, attack_types=None):
    w, s = form_stats(D, f, gen)
    return {"id": f["id"], "art": f["art"], "name": f["name"], "typen": form_types(D, f, gen), "werte": w,
            "summe": s, "faehigkeit": ability if ability is not None else ability_of(D, f, g),
            "angriffstypen": attack_types}


def row(D, f, g, gen, nr=None):
    """Kurzform für Listen. nr: Nummer im Regional-Dex des Spiels, sonst die nationale."""
    if nr is None and g:
        nr = D.in_game.get(g["id"], {}).get(f["id"])
    w, s = form_stats(D, f, gen)
    di, dk = D.in_dex.get(g["id"], {}).get(f["id"], (0, "")) if g and nr is not None else (0, "")
    return {"id": f["id"], "art": f["art"], "nr": nr if nr is not None else f["art"], "dex": di, "dexk": dk, "name": f["name"],
            "typen": form_types(D, f, gen), "werte": w, "summe": s, "gen": f["gen"], "werte_alt": w is not f["werte"],
            "legendaer": f["legendaer"] or f["mysterioes"], "endstufe": f["endstufe"], "kampfform": f["kampfform"],
            "standard": f["standard"], "relevant": f["relevant"]}


SORTS = {"nr": lambda r: (r.get("dex", 0), r["nr"] or 99999, r["id"]), "nat": lambda r: (r["art"], r["id"]), "name": lambda r: (r["name"].lower(), r["id"]),
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
    if g and g["kennung"] == LA and p.get("sort") == "forschung":      # 0.49: wo noch viele Forschungspunkte zu holen sind
        con = db.game()
        try:
            op = research_open(con)
        finally:
            con.close()
        for r in rows:
            r["forschung_offen"] = op.get(r["art"])
        rows.sort(key=lambda r: (-(r["forschung_offen"] or 0), r.get("dex", 0), r["nr"] or 99999, r["id"]))
    else:
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

# Spiele ohne eigene Texte: die Erweiterungen nehmen die ihres Hauptspiels
TEXT_BASE = {"the-isle-of-armor": "sword-shield", "the-crown-tundra": "sword-shield", "the-teal-mask": "scarlet-violet",
             "the-indigo-disk": "scarlet-violet", "mega-dimension": "legends-za", "red-green-japan": "red-blue",
             "blue-japan": "red-blue"}


def pick_text(D, per, g):
    """Text für das gewählte Spiel aus {Spiel: [(Edition, Text, Quelle)]}: das Spiel selbst (bei Erweiterungen das
    Hauptspiel), sonst das letzte Spiel davor mit Text, sonst das erste danach. Gibt {"texte": [{edition, text}], "quelle",
    "aus"} zurück; "aus" nennt das Spiel, wenn der Text nicht aus dem gewählten stammt."""
    if not per:
        return {"texte": [], "quelle": "", "aus": ""}
    order = {x["kennung"]: x["reihenfolge"] for x in D.games}
    names = {x["kennung"]: x["name"] for x in D.games}
    want = TEXT_BASE.get(g["kennung"], g["kennung"]) if g else None
    if want in per:
        sp = want
    else:
        known = sorted(per, key=lambda k: order.get(k, 0))
        before = [k for k in known if g and order.get(k, 0) <= g["reihenfolge"]]
        sp = before[-1] if before else known[0] if g else known[-1]       # sonst das nächste danach; ohne Spiel das neueste
    xs = per[sp]
    return {"texte": [{"edition": ed, "text": t} for ed, t, _ in xs], "quelle": xs[0][2],
            "aus": "" if sp == want else names.get(sp, sp)}


def text_rows(con, art, oid):
    """{Spiel: [(Edition, Text, Quelle)]} aus spieltext (leer, solange die Datenbank die Tabelle noch nicht hat)."""
    per = {}
    try:
        for sp, ed, txt, src in con.execute("SELECT spiel, edition, text, quelle FROM spieltext WHERE art = ? AND id = ? "
                                            "ORDER BY rowid", (art, oid)):
            per.setdefault(sp, []).append((ed, txt, src))
    except Exception:
        pass
    return per


def joined(t):
    """Ein Text aus pick_text als Zeile: bei zwei Editionen mit Namen davor."""
    xs = t["texte"]
    if len(xs) == 1:
        return xs[0]["text"]
    return " · ".join((x["edition"] + ": " if x["edition"] else "") + x["text"] for x in xs)


def move_view(D, m, g):
    order = g["reihenfolge"] if g else 10 ** 6
    v = attacken.in_game(m, D.changes.get(m["id"], []), order)
    per = getattr(D, "move_texts", {}).get(m["id"])
    if per:
        t = pick_text(D, per, g)
        v = dict(v, text=joined(t) + (f" (Text aus {t['aus']})" if t["aus"] else ""), text_aus=t["aus"], text_quelle=t["quelle"])
    w = D.game_moves.get((g["kennung"], m["id"])) if g else None
    if w and w.get("abklingzeit") is not None:
        v = dict(v, abkling=w["abklingzeit"])
    if w and (w["kraft"] is not None or w["tempo"] is not None):
        v = dict(v, kraft=w["kraft"], tempo=w["tempo"], quelle="PokéWiki")
    if w:
        for k in ("staerke", "genauigkeit", "ap"):
            if w[k] is not None and w[k] != v.get(k):
                v[k], v["geaendert"] = w[k], True
    return old_class(v, g.get("gen") or 9) if g else v


# Erweiterungen ohne eigene Lernliste: die PokéAPI führt deren Lehrer-Attacken und TMs beim Hauptspiel
LEARN_PARENT = {"the-isle-of-armor": "sword-shield", "the-crown-tundra": "sword-shield",
                "the-teal-mask": "scarlet-violet", "the-indigo-disk": "scarlet-violet"}


def learn_game(D, g):
    """Spiel, dessen Lernliste für g gilt: das Hauptspiel bei Erweiterungen, sonst g selbst."""
    if g and g["kennung"] in LEARN_PARENT:
        return next((x for x in D.games if x["kennung"] == LEARN_PARENT[g["kennung"]]), g)
    return g


def learnset(con, D, f, g):
    """Erlernbare Attacken im Spiel: [(Attacke, Methode, Level, Beherrschung)]; ohne Spiel das neueste mit Liste.
    Erweiterungen nehmen die Liste ihres Hauptspiels (`learn_game`)."""
    g = learn_game(D, g)
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


def owned_tms(spiel):
    """0.53: Maschinen (Item-Ids), die der User im Spiel als vorhanden abgehakt hat (user.db gefunden, Karte „tm“)."""
    try:
        u = db.user()
    except Exception:
        return set()
    try:
        return {int(o) for (o,) in u.execute("SELECT objekt FROM gefunden WHERE spiel = ? AND karte = 'tm'", (str(spiel or ""),))
                if str(o).isdigit()}
    except Exception:
        return set()
    finally:
        u.close()


def _tm_missing(con, vg, owned):
    """{Attacke: TM-Name} der Maschinen des Spiels, die der User nicht hat (nur wenn er überhaupt welche abgehakt hat)."""
    if not owned or vg is None:
        return {}
    out, have = {}, set()
    try:
        for item, mid, name in con.execute("SELECT m.item_id, m.move_id, i.identifier FROM machines m JOIN items i ON i.id = m.item_id "
                                           "WHERE m.version_group_id = ?", (vg,)):
            if item in owned:
                have.add(mid)
            else:
                out.setdefault(mid, machine_label(name, 3 if vg >= 20 else 2) or name)
    except Exception:
        return {}
    return {mid: label for mid, label in out.items() if mid not in have}


TM_RX = re.compile(r"\b(TM|HM|VM|TR|TP)[ -]?0*(\d{1,3})\b")


def tm_key(text):
    """„TM27“, „HM 03“, „TR-12“ → („TM“, 27), („VM“, 3), („TP“, 12); None ohne Maschine."""
    m = TM_RX.search(str(text or ""))
    if not m:
        return None
    return ({"HM": "VM", "TR": "TP"}.get(m.group(1), m.group(1)), int(m.group(2)))


def tm_places(maps, load=None):
    """0.53: Wo es Maschinen gibt, aus den Kartenpunkten aller Karten des Spiels (Name oder Text nennt „TM27“ usw.):
    {"TM27": [{karte, titel, id, name}]}, je Maschine höchstens 6 Stellen. load(m): die fertige Karte (Kartencache)."""
    out = {}
    if not maps:
        return out
    for m in maps["karten"]:
        try:
            r = load(m) if load else mg_map(m, maps["spiel"], maps["am"])
        except Exception:
            continue
        for p in r.get("punkte") or []:
            k = tm_key(p.get("name")) or tm_key(p.get("en")) or tm_key(p.get("text"))
            if not k:
                continue
            xs = out.setdefault(f"{k[0]}{k[1]}", [])
            if len(xs) < 6:
                xs.append({"karte": m.get("slug"), "titel": m.get("titel"), "id": p.get("id"), "name": p.get("name") or ""})
    return out


def ranked_moves(con, D, f, g, gen, level=None):
    """Bewertete Schadens-Attacken einer Form im Spiel, mit Gründen, dazu Moveset und Status-Attacken."""
    ls, used = learnset(con, D, f, g)
    # 0.53: hat der User TMs abgehakt, zählen reine TM-Attacken ohne vorhandene TM nicht als „jetzt verfügbar“
    missing = _tm_missing(con, used["id"], owned_tms(g["kennung"])) if g and used and used["id"] == g["id"] else {}
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
        v = old_class(move_view(D, e["m"], used), gen)
        wege = sorted(e["wege"], key=lambda w: (w[0] != "level-up", w[1] or 0))
        now = level is None or any(w[0] != "level-up" or (w[1] or 0) <= level for w in wege)
        tm_fehlt = missing.get(mid) if mid in missing and all(w[0] == "machine" for w in wege) else ""
        if tm_fehlt:
            now = False
        base = {"id": mid, "name": v["name"], "typ": v["typ"], "klasse": v["klasse"], "staerke": v["staerke"],
                "genauigkeit": v["genauigkeit"], "ap": v["ap"], "prio": v["prio"], "wege": [w[3] for w in wege],
                "jetzt": now, "geaendert": bool(v.get("geaendert")), "text": v.get("text"), "kurz": v.get("kurz") or "",
                "kraft": v.get("kraft"), "tempo": v.get("tempo"), "abkling": v.get("abkling"), "tm_fehlt": tm_fehlt}
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
    if g and used and used["id"] != learn_game(D, g)["id"]:
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
                                        "GROUP BY move_id", (learn_game(D, g)["id"],)).fetchall())
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


_ALPHA = {}


def shiny_locks(spiel):
    """0.51: Shiny-Sperren des Spiels: {"tausch": [Form-Ids], "nie": [Form-Ids], "gen1": bool}. In Generation I gibt es keine
    schillernden Pokémon: dort gilt alles als „nur per Tausch“ (sichtbar erst in Gold, Silber, Kristall)."""
    out = {"tausch": [], "nie": [], "gen1": False}
    try:
        con = db.game()
    except Exception:
        return out
    try:
        g = con.execute("SELECT gen FROM spiel WHERE kennung = ?", (str(spiel or ""),)).fetchone()
        out["gen1"] = bool(g and g[0] == 1)
        for form, stufe in con.execute("SELECT form, stufe FROM shinysperre WHERE spiel = ?", (str(spiel or ""),)):
            out.setdefault(stufe, []).append(form)
    except Exception:
        pass
    finally:
        con.close()
    return out


def alpha_possible(spiel):
    """Formen, die es im Spiel als Alpha gibt (Fundorte aus den Spieldaten und Spawn-Tabellen); leer in Spielen ohne Alphas."""
    spiel = str(spiel or "")
    try:
        key = (spiel, os.path.getmtime(db.pokeapi_path()))
    except OSError:
        return []
    if key in _ALPHA:
        return _ALPHA[key]
    ids = set()
    try:
        con = db.game()
    except Exception:
        return []
    try:
        for sql in ("SELECT DISTINCT form FROM fundort WHERE spiel = ? AND alpha > 0",
                    "SELECT DISTINCT form FROM spawn WHERE spiel = ? AND alpha = 1"):
            try:
                ids |= {r[0] for r in con.execute(sql, (spiel,))}
            except Exception:
                pass
    finally:
        con.close()
    _ALPHA.clear()
    _ALPHA[key] = sorted(i for i in ids if i is not None)
    return _ALPHA[key]


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
    """Karte eines Gebiets: Spawnpunkte (x, z in Spielkoordinaten) mit den Pokémon dort, Tageszeit und Anteil, dazu
    Kartensymbole und Sammelobjekte (objekte). Jubeldorf hat nur Objekte und ein eigenes Kartenbild (bild).
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
        try:
            objs = con.execute("SELECT art, nr, x, z, menge, items, gebiet FROM kartenobjekt WHERE spiel = ? AND karte = ?",
                               (spiel, karte)).fetchall()
            if con.execute("SELECT 1 FROM kartenobjekt WHERE spiel = ? AND karte = ? LIMIT 1", (spiel, altissimo.VILLAGE)).fetchone():
                maps.insert(0, {"karte": altissimo.VILLAGE, "gebiet": altissimo.VILLAGE_NAME, "n": 0})
        except Exception:
            objs = []
    finally:
        con.close()
    if not pts and not objs:
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
            "zeit": _cond_text(z, importer.ZEITEN, ZEIT_DE, "immer"), "wetter": _cond_text(w, importer.WETTER, WETTER_DE, "jedes"),
            # Anteil je Tageszeit und Wetter (Tageszeit × 9 + Wetter), für die Filter auf der Karte
            "c": [round(cells.get(f"{zt}/{wt}", 0), 1) for zt in importer.ZEITEN for wt in importer.WETTER]})
    for v in mons.values():
        v.sort(key=lambda m: (m["alpha"], -m["max"]))
    folder = os.path.join(db.data_dir(), "karten", karte)
    files = os.listdir(folder) if os.path.isdir(folder) else []
    return {"karte": karte, "gebiet": (pts or objs)[0]["gebiet"], "karten": maps,
            "kacheln": len([f for f in files if f != "bild.png"]), "bild": "bild.png" in files,
            "punkte": [{"nr": r["nr"], "x": r["x"], "z": r["z"], "alpha": bool(r["alpha"]), "mons": mons.get(r["name"], [])}
                       for r in pts],
            "objekte": [{"art": r["art"], "nr": r["nr"], "x": r["x"], "z": r["z"], "menge": r["menge"], "items": json.loads(r["items"] or "[]")}
                        for r in objs],
            "arten": {k: v for k, v in importer.KARTE_ARTEN.items() if any(r["art"] == k for r in objs)},
            "zeiten": [ZEIT_DE[k] for k in importer.ZEITEN], "wetterarten": [WETTER_DE[k] for k in importer.WETTER]}


_OVERLAY = {}


def mg_overlay(m, stamp=None):
    """Spawnpunkte und Kartensymbole von Legenden: Arceus auf der Karte von Map Genie m (ganz Hisui): je Gebiet an
    Geisterlichtern und Icognito ausgerichtet (mapgenie.align). {gebiete: {Karte: Name}, punkte: [{k, la, lo, alpha, mons}],
    objekte: [{k, la, lo, art, nr, menge, items}], arten}; Gebiete ohne Ausrichtung fehlen."""
    key = (m.get("id"), stamp, _stamp())
    if key in _OVERLAY:
        return _OVERLAY[key]
    mg = [p for ps in mapgenie.anchors(m).values() for p in ps]
    con = db.game()
    try:
        try:
            karten = [r[0] for r in con.execute("SELECT DISTINCT karte FROM kartenobjekt WHERE spiel = ? AND art IN ('irrlicht', 'icognito')",
                                                ("legends-arceus",))]
        except Exception:
            karten = []
    finally:
        con.close()
    out = {"gebiete": {}, "punkte": [], "objekte": [], "arten": {}}
    for k in karten:
        d = map_data(k, {})
        if not d:
            continue
        game = [(o["x"], o["z"]) for o in d["objekte"] if o["art"] in ("irrlicht", "icognito")]
        f = mapgenie.align(game, mg)
        if not f:
            continue
        ax, bx, az, bz = f
        ll = lambda x, z: [round(v, 6) for v in mapgenie.unproject(ax * x + bx, az * z + bz)]
        out["gebiete"][k] = d["gebiet"]
        out["arten"].update(d["arten"])
        for p in d["punkte"]:
            la, lo = ll(p["x"], p["z"])
            out["punkte"].append({"k": k, "la": la, "lo": lo, "alpha": p["alpha"],
                                  "mons": [{kk: v for kk, v in mon.items() if kk != "c"} for mon in p["mons"]]})
        for o in d["objekte"]:
            la, lo = ll(o["x"], o["z"])
            out["objekte"].append({"k": k, "la": la, "lo": lo, "art": o["art"], "nr": o["nr"], "menge": o["menge"], "items": o["items"],
                                   "x": o["x"], "z": o["z"]})
    _OVERLAY.clear()
    _OVERLAY[key] = out
    return out


_MERGED = {}
MERGED_MAX = 12             # so viele zusammengeführte Karten hält der Server bereit (Wechsel zwischen Karten ohne Wartezeit)


def mg_names():
    """Englische Namen → deutsche, für die Kategorien von Map Genie: Items (Spieldaten) und Pokémon-Arten."""
    key = _stamp()
    if _MERGED.get("names", (None,))[0] == key:
        return _MERGED["names"][1]
    out = {}
    con = db.game()
    try:
        for q in ("SELECT en, name FROM item WHERE en IS NOT NULL AND name IS NOT NULL",
                  "SELECT a.name, b.name FROM pokemon_species_names a JOIN pokemon_species_names b ON b.pokemon_species_id = "
                  "a.pokemon_species_id AND b.local_language_id = 6 WHERE a.local_language_id = 9"):
            try:
                out.update({e: g for e, g in con.execute(q) if e and g})
            except Exception:
                pass
    finally:
        con.close()
    _MERGED["names"] = (key, out)
    return out


def names_rx(names, tail=False):
    """Regulärer Ausdruck für ganze Namen (längste zuerst); tail: dazu, was dahinter steht ((Level, Form), *[Bedingung]*)."""
    if not names:
        return None
    t = r"((?:\s*\([^)]{1,30}\)|\s*[*_]\[?[^\]*_\n]{1,30}\]?[*_])*)" if tail else ""
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![\w-])" + t)


def _pic_names():
    """{deutscher Name: Art-Nr.} und {deutscher Itemname: Item-Nr.} für Bilder in den Kartendetails."""
    key = _stamp()
    if _MERGED.get("pics", (None,))[0] == key:
        return _MERGED["pics"][1]
    mons, items = {}, {}
    con = db.game()
    try:
        try:
            mons = {n: i for i, n in con.execute("SELECT pokemon_species_id, name FROM pokemon_species_names WHERE local_language_id = 6") if n}
        except Exception:
            pass
        try:
            items = {n: i for i, n in con.execute("SELECT id, name FROM item WHERE name IS NOT NULL") if n and len(n) >= 4}
        except Exception:
            pass
    finally:
        con.close()
    out = (mons, names_rx(mons, True), items, names_rx(items))
    _MERGED["pics"] = (key, out)
    return out


PIC_VALS = {"Night only": "nur nachts", "Day only": "nur tagsüber", "Shake trees": "Bäume schütteln", "Plant Cloak": "Pflanzenumhang",
            "Sandy Cloak": "Sandumhang", "Trash Cloak": "Lumpenumhang", "Rare": "selten", "Common": "häufig", "Very Rare": "sehr selten",
            "Uncommon": "gelegentlich", "Walking": "zu Fuß", "Surfing": "Surfen", "Fishing": "Angeln", "Day": "tagsüber", "Night": "nachts"}


def point_pics(text, names, mons, mrx, items, irx):
    """Pokémon und Items in einem Text eines Kartenpunkts: ([[Nr, Name, Fangart, Zusatz]], [[Item-Nr, Name]], Rest des
    Texts). Fangart ist die Überschrift bzw. Bezeichnung vor dem Doppelpunkt (auch Tageszeit), Zusatz was in Klammern
    folgt (Level, Anteil). Zeilen, die nur Pokémon aufzählen, fallen aus dem Rest (sie stehen dann als Bilder da)."""
    pk, it, rest, head = [], [], [], ""
    seen = set()
    for raw in (text or "").split("\n"):
        ln = raw.strip()
        h = re.fullmatch(r"\*\*(.+?):?\*\*:?", ln)
        if h:
            head = h.group(1).strip()
            rest.append(raw)
            continue
        body, lab = re.sub(r"^[-*]\s+", "", ln), head
        m = re.match(r"^\*\*([^*]{1,40}?):?\*\*:?\s*(.*)$", body) or re.match(r"^([^:*«»\[\]]{2,30}):\s+(.*)$", body)
        if m:
            lab, body = m.group(1).strip(), m.group(2)
        found, left = [], body
        if mrx and body:
            # Name, dahinter vielleicht (Level, Form) und *[Bedingung]*; nur Zeilen, die allein Pokémon aufzählen, zählen
            left = mrx.sub(lambda x: found.append((x.group(1), x.group(2))) or "", body)
        if found and not re.sub(r"[\s,;/()\d–\-%.·Lvl]+", "", left):
            for n, tail in found:
                extra = " · ".join(PIC_VALS.get(v.strip(), v.strip()) for v in re.findall(r"\(([^)]+)\)|[*_]\[?([^\]*_]+)\]?[*_]", tail) for v in v if v)
                k = (mons[n], lab, extra)
                if k not in seen:
                    seen.add(k)
                    pk.append([mons[n], n, PIC_VALS.get(lab, lab), extra])
            continue                              # nur Pokémon (mit Level): die Bilder zeigen es
        for x in (irx.finditer(body) if irx and body else ()):
            if x.group(1) not in mons and items[x.group(1)] not in {i[0] for i in it}:
                it.append([items[x.group(1)], x.group(1)])
        rest.append(raw)
    while rest and re.fullmatch(r"\*\*.+\*\*:?|\s*", rest[-1].strip()):
        rest.pop()                                 # Überschriften ohne Inhalt am Ende
    out, hd = [], re.compile(r"\*\*[^*]+\*\*:?")
    for i, ln in enumerate(rest):                  # Überschrift ohne eigenen Inhalt (danach nur eine weitere) auch weg
        if hd.fullmatch(ln.strip()):
            nxt = next((x.strip() for x in rest[i + 1:] if x.strip()), "")
            if not nxt or hd.fullmatch(nxt) or re.match(r"\*\*[^*]+\*\*:?\s*\S", nxt):
                continue
        out.append(ln)
    return pk, it, "\n".join(out).strip()


def _point_pics(r):
    """Kartenpunkte: Pokémon und Items aus dem Text als Bilder (pk, it); was der Text sonst sagt, bleibt."""
    mons, mrx, items, irx = _pic_names()
    if not (mrx or irx):
        return
    for p in r["punkte"]:
        if p.get("sp"):
            continue
        names = " ".join([p.get("name") or ""] + [i[0] for i in (p.get("o") or {}).get("items") or []])
        pk, it, rest = point_pics(p.get("text") or "", names, mons, mrx, items, irx)
        if irx:                                    # der Punkt selbst ist ein Item (Name) oder hat Items aus den Spieldaten
            for x in irx.finditer(names):
                if x.group(1) not in mons and items[x.group(1)] not in {i[0] for i in it}:
                    it.append([items[x.group(1)], x.group(1)])
        if pk:
            p["pk"] = pk
            p["text"] = rest
        if it:
            p["it"] = it[:24]


def _quests_de(r, spiel=LA):
    """Aufträge und Hauptmissionen auf der Karte: deutscher Name und Text von BisaFans vor dem englischen von Map Genie;
    „aq“ nennt den Schlüssel, unter dem der Haken liegt (wie im Reiter Aufträge)."""
    spiel = QUEST_GAMES.get(spiel, spiel)
    cats = {c["id"]: quest_kind(c["en"]) for g in r["gruppen"] for c in g["kategorien"]}
    con = db.game()
    try:
        D = data()
        de = {"auftrag": {x["nr"]: x for x in (_requests(con, D, spiel=spiel) if D else [])},
              "mission": {x["nr"]: x for x in _missions(con, spiel)}}
    finally:
        con.close()
    for p in r["punkte"]:
        k = cats.get(p["c"])
        nr = quest_nr(p.get("en") or p["name"]) if k else None
        if nr is None:
            continue
        p["aq"] = f"{k}|{nr}"
        g = de[k].get(nr)
        if not g:
            continue
        p.setdefault("en", p["name"])
        p["name"] = f"#{nr}: {g['name']}"
        parts = ([g.get("beschreibung"), "**Aufgabe:** " + g["aufgabe"] if g.get("aufgabe") else "", "**Lösung:** " + g["loesung"] if g.get("loesung") else "",
                  "**Belohnung:** " + g["belohnung"] if g.get("belohnung") else ""] if k == "auftrag" else [g.get("text")])
        de_text = "\n\n".join(x for x in parts if x)
        if de_text:
            p["text"] = de_text + ("\n\n---\n\n**Map Genie (englisch):**\n\n" + p["text"] if p.get("text") else "")
            p["q"] = p.get("q", []) + ["BisaFans"]


def _pokearth_mons(r, spiel):
    """Regionskarten von Serebii: je Ort die Pokémon aus den Fundorten des Spiels (Spieldaten oder PokéAPI), deutscher
    Ortsname. Serebii nennt die Orte englisch; die PokéAPI kennt beide Namen."""
    a = areas({"spiel": spiel}) or {}
    if not a.get("gebiete"):
        return
    con = db.game()
    try:
        en, de = {}, {}
        for k, lang, n in con.execute("SELECT location_id, local_language_id, name FROM location_names WHERE local_language_id IN (6, 9)"):
            (de if lang == 6 else en).setdefault(k, n)
    except Exception:
        return
    finally:
        con.close()
    en2de = {}
    for k, n in en.items():
        if n:
            en2de.setdefault(n.lower(), de.get(k) or n)
    for n in de.values():                  # 0.48: Karten aus dem PokéWiki nennen die Orte schon deutsch
        if n:                              # 0.49: Arten ohne deutschen Namen (None) warfen AttributeError
            en2de.setdefault(n.lower(), n)
    for p in r["punkte"]:
        if p.get("text"):              # „Ort: Cherrygrove“ (Trainer, Items) → deutscher Ortsname
            p["text"] = re.sub(r"(\*\*Ort:\*\* )([^\n(]+?)(?=\s*\(|\n|$)", lambda x: x.group(1) + (
                en2de.get(x.group(2).lower()) or en2de.get(re.sub(r"\s+(City|Town)$", "", x.group(2)).lower()) or x.group(2)), p["text"])
        name = p.get("en") or p["name"]
        d = en2de.get(name.lower()) or en2de.get(re.sub(r"\s+(City|Town)$", "", name).lower())
        if not d:
            continue
        if d != p["name"]:
            p.setdefault("en", p["name"])
            p["name"] = d
        dl = d.lower()
        gs = [g for g in a["gebiete"] if g["ort"].lower() == dl or g["ort"].lower().startswith(dl + " (")]
        if not gs:
            continue
        lines = []
        for g in gs:
            by = {}
            for x in g["mons"]:
                by.setdefault(x["methode"] or "Pokémon", []).append(f"{x['name']} ({x['level']})" if x.get("level") else x["name"])
            head = f"**{g['ort']}**" if len(gs) > 1 else ""
            lines += ([head] if head else []) + [f"- **{k}:** " + ", ".join(dict.fromkeys(v)) for k, v in by.items()]
        p["text"] = "\n".join(lines)
        p["q"] = list(dict.fromkeys(p.get("q", []) + [a.get("quelle") or "PokéAPI"]))


def mg_map(m, spiel, stamp=None):
    """Eine Karte von Map Genie als eine Datenbank mit den eigenen Daten (mapgenie.merge): deutsche Ebenen, gleiche
    Stellen verschmolzen. Für Legenden: Arceus kommen Spawnpunkte und Symbole aus den Spieldaten dazu."""
    key = (spiel, m.get("id"), m.get("slug"), stamp, _stamp())
    hit = _MERGED.setdefault("maps", {})
    if key in hit:
        return hit[key]
    with _MERGE_LOCK:              # 0.52: Vorbereiten im Hintergrund und erste Anfrage rechnen nicht doppelt
        if key in hit:
            return hit[key]
        return _mg_map(m, spiel, stamp, key, hit)


_MERGE_LOCK = threading.Lock()


def _mg_map(m, spiel, stamp, key, hit):
    own = mg_overlay(m, stamp) if spiel == "legends-arceus" else None
    r = mapgenie.merge(m, own, mg_names())
    if spiel in QUEST_GAMES:
        _quests_de(r, spiel)
    if m.get("quelle") in ("pokearth", "ironmon", "raidnester"):       # Orte mit englischem Namen: Pokémon aus den Fundorten
        _pokearth_mons(r, spiel)
    _point_pics(r)
    out = {k: v for k, v in m.items() if k not in ("orte", "gruppen")}
    out.update(r, spiel=spiel, am=stamp, bounds=mapgenie.bounds_of(m))
    while len(hit) >= MERGED_MAX:            # die ältesten zuerst weg
        hit.pop(next(iter(hit)))
    hit[key] = out
    return out


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
        out.append({"ort": _place(place, area),
                    "methode": meths.get(r["meth"], ""), "level": f"{r['lo']}" if r["lo"] == r["hi"] else f"{r['lo']}–{r['hi']}",
                    "bedingungen": [conds[int(c)] for c in str(r["cond"] or "").split(",") if c and int(c) in conds],
                    "editionen": [vn.get(v, "") for v in vs] if len(vs) < nv else []})
    return out


_AREAS = {}


def _place(place, area):
    """Ort mit Teilgebiet: „Eispfad (1.UG)“; enthält das Teilgebiet schon den Ort („Dunkelhöhle (Viola City Eingang)“),
    nur das Teilgebiet."""
    if not area or area.lower() in place.lower():
        return place
    return area if place.lower() in area.lower() else f"{place} ({area})"


def areas(p):
    """Gebiete eines Spiels mit allen Pokémon dort (für Spiele ohne Karte): {spiel, quelle, gebiete: [{ort, mons:
    [{id, name, methode, level, anteil, editionen, bedingungen}]}]}. Aus den Spieldaten (PKHeX), sonst aus der PokéAPI."""
    D = data()
    if not D:
        return None
    g, _, _ = game_of(D, p.get("spiel"))
    if not g:
        return None
    try:
        key = (g["kennung"], os.path.getmtime(db.pokeapi_path()))
    except OSError:
        return None
    if key in _AREAS:
        return _AREAS[key]
    con = db.game()
    try:
        out = _areas_pkhex(con, D, g)
        quelle = "PKHeX"
        if out is None:
            out, quelle = _areas_pokeapi(con, D, g), "PokéAPI"
    finally:
        con.close()
    res = {"spiel": g["kennung"], "quelle": quelle,
           "gebiete": [{"ort": k, "mons": sorted(v, key=lambda m: (m["methode"], -(m["anteil"] or 0), m["name"]))} for k, v in out.items()]}
    _AREAS.clear()
    _AREAS[key] = res
    return res


def _areas_pkhex(con, D, g):
    try:
        rows = con.execute("SELECT form, gebiet, gebiet_nr, art, MIN(min) lo, MAX(max) hi, MAX(alpha) al FROM fundort WHERE spiel = ? "
                           "GROUP BY gebiet, form, art ORDER BY MIN(gebiet_nr), gebiet", (g["kennung"],)).fetchall()
    except Exception:
        return None
    if not rows:
        return None
    out = {}
    for r in rows:
        f = D.forms.get(r["form"])
        if not f:
            continue
        lv = f"{r['lo']}" if r["lo"] == r["hi"] else f"{r['lo']}–{r['hi']}"
        out.setdefault(r["gebiet"], []).append({"id": f["id"], "name": f["name"], "methode": importer.PKHEX_ART.get(r["art"], str(r["art"])),
                                                "level": lv if r["lo"] else "", "anteil": None, "editionen": [], "bedingungen": [],
                                                "alpha": r["al"] == 2})
    return out


def _areas_pokeapi(con, D, g):
    try:
        rows = con.execute(
            """SELECT e.pokemon_id pid, l.id loc, e.location_area_id la, es.encounter_method_id meth, MIN(e.min_level) lo,
                      MAX(e.max_level) hi, GROUP_CONCAT(DISTINCT v.id) vers, GROUP_CONCAT(DISTINCT m.encounter_condition_value_id) cond,
                      SUM(es.rarity) rar
               FROM encounters e JOIN versions v ON v.id = e.version_id JOIN location_areas la ON la.id = e.location_area_id
               JOIN locations l ON l.id = la.location_id JOIN encounter_slots es ON es.id = e.encounter_slot_id
               LEFT JOIN encounter_condition_value_map m ON m.encounter_id = e.id
               WHERE v.version_group_id = ?
               GROUP BY e.pokemon_id, e.location_area_id, es.encounter_method_id ORDER BY l.id, la.id""", (g["id"],)).fetchall()
    except Exception:
        return {}
    locs = _names(con, "location_names", "location_id")
    area_n = _names(con, "location_area_prose", "location_area_id")
    meths = _names(con, "encounter_method_prose", "encounter_method_id")
    conds = _names(con, "encounter_condition_value_prose", "encounter_condition_value_id")
    vn = _names(con, "version_names", "version_id")
    nv = con.execute("SELECT COUNT(*) FROM versions WHERE version_group_id = ?", (g["id"],)).fetchone()[0]
    out = {}
    for r in rows:
        f = D.forms.get(r["pid"])
        if not f:
            continue
        place, area = locs.get(r["loc"]) or f"Ort {r['loc']}", area_n.get(r["la"]) or ""
        ort = _place(place, area)
        vs = [int(v) for v in str(r["vers"] or "").split(",") if v]
        out.setdefault(ort, []).append({
            "id": f["id"], "name": f["name"], "methode": meths.get(r["meth"], ""),
            "level": f"{r['lo']}" if r["lo"] == r["hi"] else f"{r['lo']}–{r['hi']}",
            "anteil": min(100, r["rar"]) if r["rar"] else None,
            "editionen": [vn.get(v, "") for v in vs] if len(vs) < nv else [],
            "bedingungen": [conds[int(c)] for c in str(r["cond"] or "").split(",") if c and int(c) in conds]})
    return out


BALLS = (("Pokéball", 1), ("Superball", 1.5), ("Hyperball", 2))
# 0.50: Bälle in Legenden: Arceus nach Bulbapedia (Catch rate): [Name, Faktor, Faktor verstärkt, wann verstärkt].
# Schwer-Bälle verstärkt, wenn das Pokémon dich nicht bemerkt hat oder im Kampf; Feder-Bälle bei fliegenden Pokémon
HISUI_BALLS = [["Pokéball", 0.75, 0.75, ""], ["Superball", 1.5, 1.5, ""], ["Hyperball", 2.25, 2.25, ""],
               ["Schwerball", 1, 1.25, "unbemerkt"], ["Zentnerball", 1.75, 2, "unbemerkt"], ["Tonnenball", 2.5, 2.75, "unbemerkt"],
               ["Federball", 1, 1.25, "fliegt"], ["Flügelball", 1.25, 2, "fliegt"], ["Düsenball", 2, 2.75, "fliegt"]]


def catch_chance_la(rate, ball=0.75, hp_share=1.0, status=1.0, behavior=2.0, back=1.0, berry=1.0, rank=0, outbreak=False):
    """0.50: Fangchance in % in Legenden: Arceus (Bulbapedia, Catch rate):
    a = 0,75 × Fangrate (+10 im Massenausbruch) + 30 × (Rang + KP-Faktor × Status × Ball × Verhalten × Rücken × Beere),
    Rang zwischen −5 und 0; a bis 255, b = 65535 × (1 − √(1 − a/255)), zwei Proben, eine muss gelingen."""
    hp = (3 - 2 * hp_share) / 3
    a = 0.75 * rate + (10 if outbreak else 0) + 30 * (max(-5, min(0, rank)) + hp * status * ball * behavior * back * berry)
    if a < 0:
        return 0.0
    a = min(255, a)
    b = 65535 * (1 - (1 - a / 255) ** 0.5)
    return round(100 * (1 - (1 - b / 65536) ** 2), 1)


def rank_la(level, alpha=False, player=10):
    """Rang-Term in Legenden: Arceus: Rang des Spielers − Rang des Pokémon + 1, zwischen −5 und 0. Rang des Pokémon
    ⌊(Level − 1)/10 + 1⌋, Alpha +4, höchstens 10."""
    poke = min(10, int((level - 1) / 10 + 1) + (4 if alpha else 0))
    return max(-5, min(0, player - poke + 1))
# 0.48.7: Bälle in Legenden: Arceus (Faktoren wie in der Item-Liste, BALL_HISUI in app.js); die Schwer-Bälle zusätzlich mit dem
# Faktor, wenn das Pokémon dich nicht bemerkt hat, der Düsenball bei fliegenden Pokémon. Urball (fängt immer) fehlt
BALLS_HISUI = (("Pokéball", 1), ("Superball", 1.5), ("Hyperball", 2.25), ("Federball", 1), ("Flügelball", 1.5), ("Düsenball", 2),
               ("Düsenball, Pokémon fliegt", 2.75), ("Schwerball", 1), ("Schwerball, unbemerkt", 1.25), ("Zentnerball", 1.25),
               ("Zentnerball, unbemerkt", 2), ("Tonnenball", 2.5), ("Tonnenball, unbemerkt", 2.75))
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


def catch_table(rate, gen, balls=BALLS, extra=()):
    """Fangchance je Ball bei vollen KP, bei 1 KP, bei 1 KP mit Paralyse, Gift oder Verbrennung (×1,5) und bei 1 KP mit
    Schlaf oder Einfrieren (ab Generation 5 ×2,5, sonst ×2)."""
    sleep = sleep_factor(gen)
    return [{"ball": n, "faktor": f, "voll": catch_chance(rate, f, gen=gen), "rot": catch_chance(rate, f, 0, gen=gen),
             "status": catch_chance(rate, f, 0, 1.5, gen=gen), "schlaf": catch_chance(rate, f, 0, sleep, gen=gen)} for n, f in balls] + [
        {"ball": n, "faktor": f, "plus": plus or None, "voll": catch_chance(max(1, rate + plus), f, gen=gen),
         "rot": catch_chance(max(1, rate + plus), f, 0, gen=gen), "status": catch_chance(max(1, rate + plus), f, 0, 1.5, gen=gen),
         "schlaf": catch_chance(max(1, rate + plus), f, 0, sleep, gen=gen)} for n, f, plus in extra]


MOON_SPECIES = {30, 33, 35, 39, 300, 517}          # entwickeln sich mit dem Mondstein (Nidorina, Nidorino, Piepi, Pummeluff, Eneco, Somniam)
ULTRA_BEASTS = {793, 794, 795, 796, 797, 798, 799, 803, 804, 805, 806}


def ball_rows(gen, have, f, weight_kg=None):
    """0.48.9: weitere Bälle der Hauptspiele für die Fangtabelle, nur die es im Spiel gibt (have: Namen aus der Item-Liste).
    → [(Name mit Bedingung, Faktor, Zuschlag auf die Fangrate)]. Bälle, die nur vom Pokémon abhängen (Netz-, Turbo-, Mond-,
    Schwer-, Ultraball), stehen nur da, wenn sie hier wirken; Bälle, die von der Lage abhängen, mit der Lage im Namen.
    Faktoren je Generation: Netz- und Wiederball ×3 bis Gen. 6, dann ×3,5; Finsterball ×3,5 bis Gen. 6, dann ×3;
    Flottball ×4 in Gen. 4, dann ×5; Köderball ×3 bis Gen. 6, ×5 in Gen. 7, dann ×4."""
    typen = set(f.get("typen") or [])
    out = []
    def add(name, label, fac, plus=0):
        if name in have:
            out.append((label, fac, plus))
    if typen & {7, 11}:                                     # Käfer, Wasser
        add("Netzball", "Netzball (Wasser oder Käfer)", 3 if gen <= 6 else 3.5)
    if (f.get("werte") or [0] * 6)[5] >= 100:
        add("Turboball", "Turboball (Initiative ab 100)", 4)
    if f.get("art") in MOON_SPECIES:
        add("Mondball", "Mondball (entwickelt sich mit Mondstein)", 4)
    if "Ultraball" in have:
        add("Ultraball", "Ultraball" + (" (Ultrabestie)" if f.get("art") in ULTRA_BEASTS else " (keine Ultrabestie)"),
            5 if f.get("art") in ULTRA_BEASTS else 0.1)
    if weight_kg is not None and "Schwerball" in have:
        if gen >= 7:
            plus = -20 if weight_kg < 100 else 0 if weight_kg < 200 else 20 if weight_kg < 300 else 30
        else:
            plus = -20 if weight_kg < 102.4 else 0 if weight_kg < 204.8 else 20 if weight_kg < 307.2 else 30 if weight_kg < 409.6 else 40
        add("Schwerball", f"Schwerball ({weight_kg:g} kg: Fangrate {plus:+d})".replace(".", ","), 1, plus)
    add("Tauchball", "Tauchball (Surfen, Angeln, unter Wasser)", 3.5)
    add("Finsterball", "Finsterball (nachts oder in Höhlen)", 3.5 if gen <= 6 else 3)
    add("Flottball", "Flottball (erste Runde)", 4 if gen == 4 else 5)
    add("Timerball", "Timerball (ab Runde 11)", 4)
    add("Nestball", "Nestball (wildes Pokémon Level 10)", max(1, (41 - 10) / 10 if gen >= 5 else (40 - 10) / 10))
    add("Wiederball", "Wiederball (Art schon gefangen)", 3 if gen <= 6 else 3.5)
    add("Köderball", "Köderball (geangelt)", 3 if gen <= 6 else 5 if gen == 7 else 4)
    if gen >= 8:
        add("Traumball", "Traumball (schlafend)", 4)
    add("Levelball", "Levelball (dein Pokémon mind. 4× so hohes Level)", 8)
    add("Sympaball", "Sympaball (gleiche Art, anderes Geschlecht)", 8)
    return out


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
        if kennung == "legends-arceus":       # 0.50: eigene Fangrate und eigene Formel (Rechnung in app.js, catchHtmlLA)
            try:
                r = con.execute("SELECT rate FROM fangrate WHERE spiel = ? AND art = ?", (kennung, f["art"])).fetchone()
            except Exception:
                r = None
            out["fangrate_la"] = r[0] if r else None
            out["fang_hisui"] = HISUI_BALLS
        extra = ()
        if g and kennung != "legends-arceus":
            try:
                have = {r["name"] for r in con.execute("SELECT name, spiele FROM item WHERE tasche = 'Bälle'")
                        if g["id"] in json.loads(r["spiele"] or "[]")}
                w = con.execute("SELECT weight FROM pokemon WHERE id = ?", (f["id"],)).fetchone()
                extra = ball_rows(gen, have, f, w[0] / 10 if w and w[0] is not None else None)
            except Exception:
                extra = ()
        out["fangen"] = catch_table(sp["capture_rate"], gen, BALLS_HISUI if kennung == "legends-arceus" else BALLS, extra)
        out["schlaf_faktor"] = str(sleep_factor(gen)).replace(".", ",")
        out["fang_gen"] = gen
        out["fang_grob"] = gen <= 2 or kennung.startswith("legends-") or kennung.startswith("lets-go")
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
        dex = pick_text(D, text_rows(con, "pokemon", f["art"]), g)
        genus = con.execute("SELECT genus FROM pokemon_species_names WHERE pokemon_species_id = ? AND local_language_id = 6", (f["art"],)).fetchone()
        abil = []
        if not no_abilities(g):
            for aid, hidden in f["faehigkeiten"]:
                k, n = D.abilities.get(aid, ("", str(aid)))
                txt = con.execute("SELECT flavor_text FROM ability_flavor_text WHERE ability_id = ? AND language_id = 6 "
                                  "ORDER BY version_group_id DESC LIMIT 1", (aid,)).fetchone()
                at = pick_text(D, text_rows(con, "faehigkeiten", aid), g)
                abil.append({"name": n, "versteckt": bool(hidden),
                             "text": joined(at) if at["texte"] else (" ".join(str(txt[0]).split()) if txt else ""),
                             "text_aus": at["aus"], "text_quelle": at["quelle"], "wirkt": k in typen.ABILITY_DEFENSE})
        siblings = [{"id": x["id"], "name": x["name"], "kampf": bool(x["kampfform"])} for x in D.forms.values()
                    if x["art"] == f["art"] and x["id"] != f["id"] and (x["relevant"] or x["standard"])]
        moves = ranked_moves(con, D, f, g, gen, _int(p.get("level")))
        nr = D.in_game.get(g["id"], {}).get(fid) if g else None
        return dict(row(D, f, g, gen, nr), formname=f["formname"], kategorie=genus[0] if genus else "",
                    text=joined(dex) if dex["texte"] else (" ".join(str(flavor[0]).split()) if flavor else ""),
                    texte=dex["texte"], text_aus=dex["aus"], text_quelle=dex["quelle"] or ("PokéAPI" if flavor else ""),
                    forschung=_research(con, f["art"]) if g and g["kennung"] == LA else [], faehigkeiten=abil,
                    auftraege=_requests(con, D, f["art"], QUEST_GAMES[g["kennung"]]) if g and g["kennung"] in QUEST_GAMES else [],
                    wirkung={str(a): v for a, v in dvec.items()}, faehigkeit_wirkt=ab if ab in typen.ABILITY_DEFENSE else "",
                    entwicklung=_evolutions(con, D, f), fundorte=_enc(con, g, fid), fundquelle="PKHeX" if g and g["kennung"] in D.areas else "PokéAPI", formen=siblings, attacken=moves,
                    im_spiel=(fid in D.in_game.get(g["id"], {})) if g else True, mehr=_more(con, f, g, gen), extras=_extras(fid),
                    wiki=WIKI + _wiki_title(D, f), getragen=_held(con, g, f), optik=_optik(con, f), pokopia=_pokopia(con, g, f),
                    raids=_raids(con, D, g, form=fid) if g and g["kennung"] in TERA_GAMES else [],
                    crypto=_crypto(con, D, g, fid) if g and g["kennung"] in ("colosseum", "xd") else [],
                    spielwissen=knowledge(con, g["kennung"] if g else "", fid))
    finally:
        con.close()


WISSEN = os.path.join(os.path.dirname(__file__), "..", "extra", "spielwissen.json")
_WISSEN = {}


def knowledge(con, spiel, fid=None):
    """Gepflegtes Spielwissen (extra/spielwissen.json) für die Detailseite: Fangen und Fang-Kombo; beim Partner-Pokémon
    dazu seine Partner-Techniken (aus der Datenbank: Name, Typ, Stärke) und die Geheimen Techniken. None ohne Eintrag."""
    try:
        mt = os.path.getmtime(WISSEN)
        if _WISSEN.get("mt") != mt:
            with open(WISSEN, encoding="utf-8") as fh:
                _WISSEN.update(mt=mt, d=json.load(fh))
    except (OSError, ValueError):
        return None
    w = (_WISSEN.get("d") or {}).get(spiel)
    if not w:
        return None
    out = {k: w[k] for k in ("fangen", "kombo", "quellen") if k in w}
    ids = ((w.get("partner") or {}).get(str(fid)) or []) if fid else []
    if ids:
        rows = []
        for k in ids:
            r = con.execute("SELECT id, name, typ, staerke, genauigkeit, klasse, kurz FROM attacke WHERE kennung = ?", (k,)).fetchone()
            if r:
                rows.append(dict(r))
        out["partner"] = {"text": w["partner"].get("text", ""), "attacken": rows}
        if w.get("techniken"):
            out["techniken"] = w["techniken"]
    return out


def _optik(con, f):
    """Formen nur zum Ansehen (gleiche Werte, eigenes Aussehen: Burmy, Vivillon, Icognito …) einer Form:
    [{id, name, bild}], die Standardform zuerst (id None: ihr Bild ist das der Form). Leer, wenn es nur eine gibt."""
    try:
        rows = con.execute("SELECT f.id, f.is_default, f.form_identifier, n.form_name FROM pokemon_forms f "
                           "LEFT JOIN pokemon_form_names n ON n.pokemon_form_id = f.id AND n.local_language_id = 6 "
                           "WHERE f.pokemon_id = ? ORDER BY f.form_order, f.id", (f["id"],)).fetchall()
    except Exception:
        return []
    if len(rows) < 2:
        return []
    folder = os.path.join(db.data_dir(), "formen")
    # 0.48.2: Formen, für die es bei der Quelle kein Bild gibt (Moterpel: sieht in jeder Form gleich aus), weglassen
    gone = store.load_json("formen_fehlen.json", {}) or {}
    out = [{"id": None if d else i, "name": n or (k or "").replace("-", " ").title() or "Standard",
            "bild": bool(d) or os.path.isfile(os.path.join(folder, f"{i}.png"))} for i, d, k, n in rows
           if d or str(i) not in gone or os.path.isfile(os.path.join(folder, f"{i}.png"))]
    return out if len(out) > 1 else []


def _held(con, g, f):
    """Getragene Items wilder Pokémon im Spiel: aus dem PokéWiki (Legenden: Arceus), sonst aus der PokéAPI
    (pokemon_items, Generation 3 bis 7, je Edition): [{item, id, prozent, elite, quelle, editionen}]."""
    if not g:
        return []
    try:
        rows = con.execute("SELECT item, item_id, prozent, elite FROM getragen WHERE spiel = ? AND art = ?", (g["kennung"], f["art"])).fetchall()
    except Exception:
        rows = []
    if rows:
        return [{"item": r[0], "id": r[1], "prozent": r[2], "elite": bool(r[3]), "quelle": "PokéWiki"} for r in rows]
    try:
        q = ("SELECT pi.item_id, COALESCE(n.name, i.identifier), pi.rarity, COALESCE(vn.name, v.identifier) FROM pokemon_items pi "
             "JOIN versions v ON v.id = pi.version_id JOIN items i ON i.id = pi.item_id "
             "LEFT JOIN item_names n ON n.item_id = pi.item_id AND n.local_language_id = 6 "
             "LEFT JOIN version_names vn ON vn.version_id = v.id AND vn.local_language_id = 6 "
             "WHERE pi.pokemon_id = ? AND v.version_group_id = ? ORDER BY pi.rarity DESC, v.id")
        rows = con.execute(q, (f["id"], g["id"])).fetchall()
    except sqlite3.OperationalError:
        return []
    out = {}
    for iid, name, rarity, ver in rows:
        x = out.setdefault((iid, rarity), {"item": name, "id": iid, "prozent": f"{rarity} %", "elite": False, "quelle": "PokéAPI", "editionen": []})
        x["editionen"].append(ver)
    n_ver = con.execute("SELECT COUNT(*) FROM versions WHERE version_group_id = ?", (g["id"],)).fetchone()[0]
    for x in out.values():
        if len(x["editionen"]) >= n_ver:
            x["editionen"] = []                 # in allen Editionen gleich: nicht eigens nennen
    return list(out.values())


def _pokopia(con, g, f):
    """Einträge der Art in den Pokédexen von Pokopia (Serebii): [{dex, nr, name, spezial: [deutsch]}]."""
    if not g or g["kennung"] != "pokopia":
        return []
    from . import serebii
    try:
        rows = con.execute("SELECT dex, nr, name, spezial FROM pokopia WHERE art = ? ORDER BY dex = 'haupt' DESC, nr", (f["art"],)).fetchall()
    except Exception:
        return []
    return [{"dex": serebii.POKOPIA_DEX.get(r[0], r[0]), "nr": r[1], "name": r[2],
             "spezial": [serebii.spezial_de(k) for k in json.loads(r[3] or "[]")]} for r in rows]


def research_done(spiel=LA):
    """0.49: erreichte Stufen der Forschungsaufgaben aus user.db (Tabelle gefunden, Karte „forschung“, Objekt
    „Art|Nr|Stufe“): {(Art, Nr): höchste erreichte Stufe}."""
    con = db.user()
    try:
        rows = con.execute("SELECT objekt FROM gefunden WHERE spiel = ? AND karte = 'forschung'", (spiel,)).fetchall()
    except Exception:
        rows = []
    finally:
        con.close()
    out = {}
    for (o,) in rows:
        try:
            art, nr, k = (int(x) for x in str(o).split("|"))
        except ValueError:
            continue
        out[(art, nr)] = max(out.get((art, nr), 0), k)
    return out


def _research(con, art, done=None):
    """Forschungsaufgaben in Legenden: Arceus (PokéWiki): [{nr, aufgabe, stufen, doppelt, erreicht}]."""
    try:
        rows = con.execute("SELECT nr, aufgabe, stufen, doppelt FROM forschung WHERE art = ? ORDER BY nr", (art,)).fetchall()
    except Exception:
        return []
    done = research_done() if done is None else done
    out = []
    for nr, a, st, d in rows:
        stufen = [x for x in json.loads(st or "[]") if x not in ("0", "")]
        out.append({"nr": nr, "aufgabe": a, "stufen": stufen, "doppelt": bool(d), "erreicht": min(done.get((art, nr), 0), len(stufen))})
    return out


def research_open(con):
    """Offene Forschungspunkte je Art bis zum Forschungslevel 10 (100 Punkte): {Art: Punkte}. Jede Stufe 10 Punkte,
    doppelt zählende 20; was über 100 hinausgeht, zählt nicht."""
    done = research_done()
    got, open_ = {}, {}
    try:
        rows = con.execute("SELECT art, nr, stufen, doppelt FROM forschung").fetchall()
    except Exception:
        return {}
    for art, nr, st, d in rows:
        n = len([x for x in json.loads(st or "[]") if x not in ("0", "")])
        k = min(done.get((art, nr), 0), n)
        w = 20 if d else 10
        got[art] = got.get(art, 0) + k * w
        open_[art] = open_.get(art, 0) + (n - k) * w
    return {a: max(0, min(o, 100 - got.get(a, 0))) for a, o in open_.items()}


def _requests(con, D, art=None, spiel=LA):
    """Aufträge (Nebenmissionen) eines Spiels (BisaFans), mit art nur die, in denen die Art vorkommt."""
    try:
        rows = con.execute("SELECT nr, name, beschreibung, aufgabe, ort, loesung, belohnung, arten FROM auftrag "
                           "WHERE spiel = ? ORDER BY nr", (spiel,)).fetchall()
    except Exception:
        return []
    std = {}
    for f in D.forms.values():
        if f["standard"]:
            std.setdefault(f["art"], f)
    out = []
    for nr, name, besch, aufg, ort, loes, bel, arten in rows:
        arts = json.loads(arten or "[]")
        if art is not None and art not in arts:
            continue
        out.append({"nr": nr, "name": name, "beschreibung": besch, "aufgabe": aufg, "ort": ort, "loesung": loes,
                    "belohnung": bel, "pokemon": [{"id": std[a]["id"], "name": std[a]["name"]} for a in arts if a in std]})
    return out


def _missions(con, spiel=LA):
    try:
        return [{"nr": nr, "name": n, "kapitel": k, "text": t, "label": f"D{nr - 100}" if spiel == ZA and k == 2 else str(nr)}
                for nr, n, k, t in con.execute("SELECT nr, name, kapitel, text FROM mission WHERE spiel = ? ORDER BY nr", (spiel,))]
    except Exception:
        return []


ZA = "legends-za"
QUEST_GAMES = {LA: LA, ZA: ZA, "mega-dimension": ZA}       # Spiel → Spiel, unter dem Aufträge und Haken liegen
BBQ_GAMES = ("scarlet-violet", "the-teal-mask", "the-indigo-disk")   # Blaubeer-Missionen (Indigoblaue Scheibe)


def _blaubeer(con):
    try:
        return [dict(r) for r in con.execute("SELECT nr, bereich, art, text, bp FROM blaubeer ORDER BY nr")]
    except Exception:
        return []
QUEST_INFO = {
    LA: {"kapitel": ["Erste Schritte in einer fremden Welt", "Wächter und Könige in Hisui", "Abenteuer im Sumpfland",
                     "Gemeinsamkeit und Stärke", "Der Berg ruft!", "Eisige Abenteuer im Frostland", "Unerwartete Unterstützung",
                     "Legenden im Sinnoh-Tempel", "Die Suche nach Arceus"],
         "quelle": "Nebenmissionen von BisaFans, Hauptmissionen aus der Komplettlösung von BisaFans", "karte_bis": 94,
         "spaet": "Aus dem Update „Ein neuer Tag in Hisui“; die Karte von Map Genie kennt ihn nicht"},
    ZA: {"kapitel": ["Hauptmission", "Dimensions-Mission (Mega-Dimension)"],
         "quelle": "Nebenmissionen von BisaFans (auch Mega-Dimension), Haupt- und Dimensions-Missionen aus dem PokéWiki",
         "karte_bis": 0, "spaet": ""},
}


def quest_kind(title):
    """Kategorie von Map Genie → Schlüssel in gefunden: Aufträge (Request, Side Mission) und Hauptmissionen."""
    t = (title or "").lower()
    if "request" in t or "side mission" in t or "side quest" in t:
        return "auftrag"
    if "story mission" in t or "main mission" in t or "main quest" in t:
        return "mission"
    return None


QUEST_CATS = {"Request": "auftrag", "Story Mission": "mission"}     # Legenden: Arceus; andere über quest_kind
_QNR = re.compile(r"^\s*(?:#|(?:(?:side|main|story)\s+)?(?:mission|quest|request)\s*#?)?\s*(\d{1,3})\s*[:.\-–]", re.I)


def quest_nr(name):
    x = _QNR.match(name or "")
    return int(x.group(1)) if x else None


def quest_points(m):
    """Aufträge und Hauptmissionen auf der Karte von Map Genie: {"auftrag": {Nr: Ort-id}, "mission": {...}}. Die Namen
    beginnen mit der Nummer („#Nr: “, „Side Mission Nr: “); Map Genie zählt wie BisaFans."""
    out = {"auftrag": {}, "mission": {}}
    cats = {c["id"]: c["titel"] for g in (m or {}).get("gruppen") or [] for c in g["kategorien"]}
    for o in (m or {}).get("orte") or []:
        k = quest_kind(cats.get(o[1]))
        nr = quest_nr(o[4])
        if k and nr is not None:
            out[k].setdefault(nr, o[0])
    return out


def request_list(p):
    """Aufträge und Missionen eines Spiels mit Aufträgen (QUEST_GAMES): {"spiel", "rows": [...], "missionen": [...],
    "kapitel", "quelle", "karte": {auftrag: {Nr: [Karte, Ort-id]}, mission: {...}}} (leer in anderen Spielen)."""
    D = data()
    if D and p.get("spiel") in BBQ_GAMES:
        con = db.game()
        try:
            return {"spiel": "the-indigo-disk", "rows": [], "missionen": [], "blaubeer": _blaubeer(con),
                    "quelle": "Blaubeer-Missionen aus dem PokéWiki"}
        finally:
            con.close()
    spiel = QUEST_GAMES.get(p.get("spiel") or LA)
    if not D or not spiel:
        return {"rows": [], "missionen": []}
    from . import abruf
    con = db.game()
    try:
        out = {"spiel": spiel, "rows": _requests(con, D, spiel=spiel), "missionen": _missions(con, spiel)}
    finally:
        con.close()
    out.update(QUEST_INFO.get(spiel, {}))
    karte = {"auftrag": {}, "mission": {}}
    for m in (abruf.mg_maps(spiel) or {}).get("karten", []):
        if m.get("quelle"):
            continue
        for k, v in quest_points(m).items():
            for nr, oid in v.items():
                karte[k].setdefault(nr, [m["slug"], oid])
    out["karte"] = karte
    return out


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
        recs, mats = {}, {}
        if g:
            try:
                for r in con.execute("SELECT item_id, item, zutaten, ort, hinweis FROM rezept WHERE spiel = ?", (g["kennung"],)):
                    if r["item_id"]:
                        recs.setdefault(r["item_id"], {"zutaten": [{"n": n, "name": z, "id": i} for n, z, i in json.loads(r["zutaten"])],
                                                       "ort": r["ort"], "hinweis": r["hinweis"]})
                for r in con.execute("SELECT item_id, fundorte FROM zutat WHERE spiel = ?", (g["kennung"],)):
                    if r["item_id"]:
                        mats[r["item_id"]] = json.loads(r["fundorte"] or "[]")
            except Exception:
                recs, mats = {}, {}
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
    have = set()
    for kind in ("itembild", "itemhq"):
        folder = os.path.join(db.data_dir(), kind)
        have |= {os.path.splitext(x)[0] for x in os.listdir(folder)} if os.path.isdir(folder) else set()
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
        if r["id"] in recs:
            e["rezept"] = recs[r["id"]]
        if r["id"] in mats:
            e["fundorte"] = mats[r["id"]]
        out.append(e)
    order = list(importer.TASCHEN.values())
    out.sort(key=lambda x: (order.index(x["tasche"]) if x["tasche"] in order else 99, x["name"].lower()))
    note = "" if exact or not g else (f"Die PokéAPI hat für dieses Spiel keine eigene Item-Liste; gezeigt sind alle Items "
                                      f"der Generation {gen}, darunter auch welche, die es hier nicht gibt.")
    return {"gen": gen, "items": out, "taschen": [t for t in order if any(x["tasche"] == t for x in out)], "hinweis": note,
            "rezepte": sum(1 for x in out if "rezept" in x)}


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
            if not used or used["id"] != learn_game(D, g)["id"]:
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
    ev["plaetze"] = slot_info(D, details)
    ev["fremde_attacken"] = foreign_moves(D, ms, details, g)
    ev["matrix"] = {str(m["id"]): {str(a): f for a, f in ctx.dvec(m).items()} for m in ms}
    ev["mitglieder"] = [row(D, D.forms[m["id"]], g, gen) for m in ms]
    ev["tera"] = tera_effect(D, ms, details, ch) if g and g["kennung"] in TERA_GAMES else []
    return ev


TERA_GAMES = {"scarlet-violet", "the-teal-mask", "the-indigo-disk"}


def tera_effect(D, ms, details, ch):
    """Je Platz mit Tera-Typ: welche Schwächen die Terakristallisierung nimmt und welche sie bringt (nur Verteidigung)."""
    out = []
    for m in ms:
        t = _int((details[m["slot"]] if m["slot"] < len(details) else {}).get("tera"))
        if t not in D.types:
            continue
        before = typen.defense(m["typen"], ch, m.get("faehigkeit"))
        after = typen.defense([t], ch, m.get("faehigkeit"))
        out.append({"slot": m["slot"], "name": m["name"], "tera": t,
                    "weg": [a for a, f in before.items() if f > 1 and after.get(a, 1) <= 1],
                    "neu": [a for a, f in after.items() if f > 1 and before.get(a, 1) <= 1],
                    "eigentyp": t in m["typen"]})
    return out


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
    von = _evolves_from()
    owned = {D.forms[i]["art"] for i in ids | {f["id"] for f in caught} if i in D.forms}
    # weiteste Stufe je Entwicklungskette im Team: ein gefangenes Abra bringt kein Potential, wenn Kadabra schon mitspielt
    st = _stage(D, {D.forms[i]["art"] for i in ids | {f["id"] for f in caught} if i in D.forms})
    in_team = {}
    for m in ms:
        f = D.forms.get(m["id"])
        if f and f.get("kette"):
            in_team[f["kette"]] = max(in_team.get(f["kette"], -1), st.get(f["art"], 0))
    for f in caught:
        if f["id"] in ids:
            continue
        gain, k = best_place(f)
        if gain >= 1:
            alt.append(dict(row(D, f, g, gen), plus=round(gain, 1), slot=ms[k]["slot"] if k is not None else None,
                            statt=ms[k]["name"] if k is not None else ""))
        if f["endstufe"] or not f.get("kette") or in_team.get(f["kette"], -1) >= st.get(f["art"], 0):
            continue
        # Endstufen, zu denen keine schon gefangene oder mitspielende weitere Stufe führt (gefangenes Kadabra: Abra fällt weg)
        finals = [x for x in D.forms.values() if x.get("kette") == f["kette"] and x["endstufe"] and x["relevant"] and not x["kampfform"]
                  and x["id"] not in ids and (in_game is None or x["id"] in in_game)
                  and not (_between(von, f["art"], x["art"]) & owned)]
        best = None
        for x in finals:
            gain2, k2 = best_place(x)
            # Potential misst die Endstufe am Team, nicht am Abstand zur heutigen Stufe: sonst fiele Kadabra heraus,
            # während Abra (weiter weg, heute schwächer) drin wäre. Nur: die Endstufe muss besser sein als heute
            if gain2 >= 1 and gain2 > gain and (not best or gain2 > best[0]):
                best = (gain2, k2, x)
        if best:
            gain2, k2, x = best
            pot.append(dict(row(D, f, g, gen), plus=round(gain2, 1), wird=row(D, x, g, gen),
                            slot=ms[k2]["slot"] if k2 is not None else None, statt=ms[k2]["name"] if k2 is not None else ""))
    # Mitglieder, die sich noch entwickeln: Endstufe auf ihrem eigenen Platz. Steht etwa Kadabra im Team, zeigt das
    # Potential Kadabra → Simsala statt des gefangenen Abra (die weitere Stufe gewinnt in _furthest)
    for k, m in enumerate(ms):
        f = D.forms.get(m["id"])
        if not f or f["endstufe"] or not f.get("kette"):
            continue
        for x in D.forms.values():
            if x.get("kette") != f["kette"] or not x["endstufe"] or not x["relevant"] or x["kampfform"] or x["id"] in ids \
                    or (in_game is not None and x["id"] not in in_game):
                continue
            gain2 = team.evaluate(ms[:k] + [member(D, x, g, gen)] + ms[k + 1:], ctx, w)["wertung"] - base
            if gain2 >= 0.5:          # schon im Team: jede spürbare Verbesserung durch die Endstufe
                pot.append(dict(row(D, f, g, gen), plus=round(gain2, 1), wird=row(D, x, g, gen), slot=m["slot"], statt=m["name"], im_team=True))
    alt.sort(key=lambda r: -r["plus"])
    pot = _furthest(pot, D, {f["id"] for f in caught} | {r["id"] for r in alt[:8]})
    pot.sort(key=lambda r: -r["plus"])
    return {"alternativen": alt[:8], "potential": pot[:8], "gefangen": len(caught), "wertung": base}


def _evolves_from():
    """{Art: Vorstufe} aus pokemon_species."""
    try:
        con = db.game()
    except Exception:
        return {}
    try:
        return dict(con.execute("SELECT id, evolves_from_species_id FROM pokemon_species WHERE evolves_from_species_id IS NOT NULL"))
    except Exception:
        return {}
    finally:
        con.close()


def _between(von, lo, hi):
    """Arten zwischen lo und hi auf dem Entwicklungsweg (ohne beide); leer, wenn hi nicht von lo abstammt."""
    out, x, n = set(), von.get(hi), 0
    while x and x != lo and n < 6:
        out.add(x)
        x, n = von.get(x), n + 1
    return out if x == lo else set()


def _stage(D, arten):
    """Entwicklungsstufe je Art (0 = Basis), aus pokemon_species.evolves_from_species_id."""
    try:
        con = db.game()
    except Exception:
        return {}
    try:
        von = dict(con.execute("SELECT id, evolves_from_species_id FROM pokemon_species"))
    except Exception:
        return {}
    finally:
        con.close()
    out = {}
    for a in arten:
        n, x = 0, a
        while von.get(x) and n < 5:
            x, n = von[x], n + 1
        out[a] = n
    return out


def _furthest(pot, D, skip):
    """Langfristiges Potential nur einmal je Endstufe, von der weitesten gefangenen Stufe; fällt weg, wenn die Endstufe
    schon gefangen ist oder bei den besseren Alternativen steht."""
    st = _stage(D, {D.forms[r["id"]]["art"] for r in pot if r["id"] in D.forms})
    best = {}
    for r in pot:
        w = r["wird"]["id"]
        if w in skip:
            continue
        key = (st.get(D.forms[r["id"]]["art"], 0) if r["id"] in D.forms else 0, bool(r.get("im_team")), r["plus"])
        if w not in best or key > best[w][0]:
            best[w] = (key, r)
    return [r for _, r in best.values()]


# Erweiterungen und Schwester-Editionen zeigen die Trainer ihres Hauptspiels
TRAINER_SHARE = {"the-teal-mask": "scarlet-violet", "the-indigo-disk": "scarlet-violet", "the-isle-of-armor": "sword-shield",
                 "the-crown-tundra": "sword-shield", "mega-dimension": "legends-za", "red-green-japan": "red-blue", "blue-japan": "red-blue"}
TRAINER_ROLLEN = ("Arenaleiter", "Top Vier", "Champ", "Rivale", "Trainer")


def trainer_list(p):
    """Wichtige Trainer eines Spiels mit Team (PokéWiki): {"spiel", "rollen", "trainer": [{id, name, rolle, titel, hinweis,
    rueckkampf, level, team: [{id, name, lvl, item, faehigkeit, attacken}]}]}, nach Level (etwa die Reihenfolge im Spiel)."""
    D = data()
    if not D:
        return {"trainer": []}
    g, _, _ = game_of(D, p.get("spiel"))
    spiel = TRAINER_SHARE.get(g["kennung"], g["kennung"]) if g else ""
    std = {}
    for f in D.forms.values():
        if f["standard"]:
            std.setdefault(f["art"], f)
    con = db.game()
    try:
        rows = con.execute("SELECT id, name, seite, rolle, titel, hinweis, rueckkampf, level, team FROM trainer WHERE spiel = ? "
                           "ORDER BY level, id", (spiel,)).fetchall()
    except Exception:
        rows = []
    finally:
        con.close()
    out = []
    for r in rows:
        team = []
        for m in json.loads(r["team"] or "[]"):
            f = std.get(m.get("nr"))
            if f:
                team.append({"id": f["id"], "name": f["name"], "lvl": m.get("lvl"), "item": m.get("item") or "",
                             "faehigkeit": m.get("faehigkeit") or "", "attacken": m.get("attacken") or []})
        if team:
            out.append({"id": r["id"], "name": r["name"], "seite": r["seite"], "rolle": r["rolle"] or "Sonstige", "titel": r["titel"],
                        "hinweis": r["hinweis"], "rueckkampf": bool(r["rueckkampf"]), "level": r["level"], "team": team})
    rollen = [x for x in TRAINER_ROLLEN if any(t["rolle"] == x for t in out)] + sorted({t["rolle"] for t in out} - set(TRAINER_ROLLEN))
    return {"spiel": spiel, "rollen": rollen, "trainer": out}


def _move_types(D, names):
    """Typen der Schadensattacken unter den deutschen Namen (Status-Attacken zählen nicht)."""
    by = getattr(D, "_move_by_name", None)
    if by is None:
        by = D._move_by_name = {m["name"].lower(): m for m in D.moves.values() if m.get("name")}
    out = []
    for n in names or []:
        m = by.get(str(n).lower())
        if m and m.get("klasse") != 1 and m.get("staerke") and m["typ"] not in out:
            out.append(m["typ"])
    return out


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
    atk = body.get("gegner_attacken") or {}           # bekannte Attacken der Gegner (Trainerteams): {ID: [Namen]}
    for i in _ints(raw if isinstance(raw, list) else [raw] if raw is not None else []):
        if i in D.forms:
            ef = D.forms[i]
            e = {"id": i, "typen": form_types(D, ef, gen), "init": ef["init"], "name": ef["name"]}
            at = _move_types(D, atk.get(str(i)) if isinstance(atk, dict) else None)
            if at:
                e["angriffstypen"] = at
            foes.append(e)
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


# ------------------------------------------------------------------ Showdown-Text (Import und Export)

def _paste_names(D):
    """Zuordnung Showdown-Namen ↔ IDs (Arten und Formen, Attacken, Items, Fähigkeiten, Wesen), einmal je Datenstand.
    Schlüssel sind Kleinbuchstaben ohne Zeichen (wie bei Showdown); deutsche Namen gelten beim Import auch."""
    if getattr(D, "paste", None) is not None:
        return D.paste
    key = importer._sd_key
    P = {"form": {}, "form_en": {}, "move": {}, "move_en": {}, "item": {}, "item_en": {}, "abil": {}, "abil_en": {},
         "nat": {}, "nat_en": {}, "nat_mod": {}, "typ": {}, "item_de": {}, "abil_de": {}, "nat_de": {}}
    by_kennung = {key(f["kennung"]): i for i, f in D.forms.items()}
    std = {}
    for i, f in sorted(D.forms.items()):
        if f["standard"] and f["art"] not in std:
            std[f["art"]] = i
    for i, f in D.forms.items():
        P["form"].setdefault(key(f["name"]), i)
    con = db.game()
    try:
        for art, lang, n in con.execute("SELECT pokemon_species_id, local_language_id, name FROM pokemon_species_names "
                                        "WHERE local_language_id IN (6, 9)"):
            if art in std:
                P["form"].setdefault(key(n), std[art])
                if lang == 9:
                    P["form_en"].setdefault(std[art], n)
        try:
            sd = list(con.execute("SELECT id, num, name FROM sd_pokemon"))
        except Exception:
            sd = []
        for sid, num, name in sd:
            fid = by_kennung.get(sid)
            if fid is None and "-" not in str(name):
                fid = std.get(num)
            if fid is not None:
                P["form"][sid] = fid
                if fid not in P["form_en"] or "-" in name:
                    P["form_en"][fid] = name
        for k, fid in by_kennung.items():
            P["form"].setdefault(k, fid)
        try:
            sd_moves = {r[0]: r[1] for r in con.execute("SELECT id, name FROM sd_attacke")}
        except Exception:
            sd_moves = {}
        for mid, m in D.moves.items():
            k = key(m["kennung"])
            P["move"][k] = mid
            P["move"].setdefault(key(m["name"]), mid)
            P["move_en"][mid] = sd_moves.get(k) or m["kennung"].replace("-", " ").title()
        for table, idcol, p in (("item_names", "item_id", "item"), ("ability_names", "ability_id", "abil"), ("nature_names", "nature_id", "nat")):
            try:
                for i, lang, n in con.execute(f"SELECT {idcol}, local_language_id, name FROM {table} WHERE local_language_id IN (6, 9)"):
                    P[p].setdefault(key(n), i)
                    if lang == 9:
                        P[p + "_en"][i] = n
                    else:
                        P[p + "_de"][i] = n
            except Exception:
                pass
        for i, ident in con.execute("SELECT id, identifier FROM items"):
            P["item"].setdefault(key(ident), i)
        for i, dec, inc in con.execute("SELECT id, decreased_stat_id, increased_stat_id FROM natures"):
            P["nat_mod"][i] = (inc - 1, dec - 1) if inc != dec else None     # Werte-Index (0 = KP): erhöht, gesenkt
    finally:
        con.close()
    for t, k in D.type_key.items():
        P["typ"][key(k)] = t
        P["typ"][key(D.types.get(t, ""))] = t
    D.paste = P
    return P


def slot_info(D, details):
    """Item, Fähigkeit, Wesen (mit Wirkung) und Tera-Typ je Platz, deutsch, für die Anzeige im Team."""
    if not any(any(d.get(k) for k in ("item", "faehigkeit", "wesen", "tera")) for d in details):
        return [{} for _ in details]
    P = _paste_names(D)
    out = []
    for d in details:
        x = {}
        for k, p in (("item", "item"), ("faehigkeit", "abil"), ("wesen", "nat")):
            i = _int(d.get(k))
            if i:
                x[k] = P[p + "_de"].get(i) or P[p + "_en"].get(i) or str(i)
        if _int(d.get("wesen")):
            x["wesen_mod"] = P["nat_mod"].get(_int(d["wesen"]))
        if _int(d.get("tera")) in D.types:
            x["tera"] = _int(d["tera"])
        out.append(x)
    return out


def paste_import(body):
    """Showdown-Text → {ids, details, hinweise}. details je Platz: level, attacken, item, faehigkeit, wesen, evs, ivs, tera,
    spitzname, schillernd (nur, was im Text steht)."""
    from . import paste
    D = data()
    if not D:
        return {"ids": [], "details": [], "hinweise": ["Noch keine Spieldaten."]}
    P = _paste_names(D)
    key = importer._sd_key
    ids, details, notes = [], [], []
    for s in paste.parse(body.get("text")):
        fid = P["form"].get(key(s["name"]))
        if fid is None:
            notes.append(f"„{s['name']}“ nicht gefunden")
            continue
        d = {}
        if s["level"]:
            d["level"] = s["level"]
        moves = []
        for mv in s["attacken"]:
            k = key(mv)
            mid = P["move"].get(k) or (P["move"].get("hiddenpower") if k.startswith("hiddenpower") else None)
            if mid:
                moves.append(mid)
            else:
                notes.append(f"{s['name']}: Attacke „{mv}“ nicht gefunden")
        if moves:
            d["attacken"] = moves
        for field, p in (("item", "item"), ("faehigkeit", "abil"), ("wesen", "nat")):
            if s[field]:
                i = P[p].get(key(s[field]))
                if i:
                    d[field] = i
                else:
                    notes.append(f"{s['name']}: „{s[field]}“ nicht gefunden")
        if s["tera"] and P["typ"].get(key(s["tera"])):
            d["tera"] = P["typ"][key(s["tera"])]
        for field in ("evs", "ivs"):
            if s[field]:
                d[field] = s[field]
        if s["spitzname"]:
            d["spitzname"] = s["spitzname"]
        if s["schillernd"]:
            d["schillernd"] = True
        if s["geschlecht"]:
            d["geschlecht"] = s["geschlecht"]
        ids.append(fid)
        details.append(d)
    if len(ids) > 6:
        notes.append(f"{len(ids)} Pokémon im Text, übernommen werden die ersten sechs")
        ids, details = ids[:6], details[:6]
    return {"ids": ids, "details": details, "hinweise": notes}


def paste_export(body):
    """Team (ids, details) → {text} im Showdown-Format mit englischen Namen."""
    from . import paste
    D = data()
    if not D:
        return {"text": ""}
    P = _paste_names(D)
    ids = _ints(body.get("ids"))
    per = slot_details(body.get("details"), ids)
    g = D.game_by.get(body.get("spiel") or "")
    sets = []
    for i, d in zip(ids, per):
        f = D.forms.get(i)
        if not f:
            continue
        abil = _int(d.get("faehigkeit"))
        if not abil and not no_abilities(g):
            abil = next((a for a, hidden in f["faehigkeiten"] if not hidden), None)
        tera = _int(d.get("tera"))
        sets.append({"name": P["form_en"].get(i) or f["kennung"].title(), "spitzname": str(d.get("spitzname") or "")[:30], "geschlecht": d.get("geschlecht"),
                     "item": P["item_en"].get(_int(d.get("item")), ""), "faehigkeit": P["abil_en"].get(abil, "") if abil else "",
                     "level": _int(d.get("level")), "schillernd": bool(d.get("schillernd")),
                     "tera": D.type_key.get(tera, "").title() if tera else "",
                     "evs": _ints(d.get("evs"))[:6] or None, "ivs": _ints(d.get("ivs"))[:6] or None,
                     "wesen": P["nat_en"].get(_int(d.get("wesen")), ""),
                     "attacken": [P["move_en"][m] for m in _ints(d.get("attacken")) if m in P["move_en"]]})
    return {"text": paste.dump(sets)}


# ------------------------------------------------------------------ Doppelkampf

def smogon_view(spiel=None):
    """Häufige Gegner aus der Nutzungsstatistik (smogon.json), mit IDs und deutschen Namen, soweit zuzuordnen."""
    d = store.load_json("smogon.json", {})
    D = data()
    if not d.get("pokemon") or not D:
        return {"format": d.get("format", ""), "monat": d.get("monat", ""), "rows": []}
    P = _paste_names(D)
    key = importer._sd_key
    g, gen, _ = game_of(D, spiel)

    def de(kind, pairs):
        out = []
        for n, pct in pairs:
            i = P[kind].get(key(n))
            if kind == "move":
                name = D.moves[i]["name"] if i in D.moves else n
            elif kind == "typ":
                name = D.types.get(i, n)
            else:
                name = P[kind + "_de"].get(i) or n if i else n
            out.append([name, pct])
        return out
    rows = []
    for r in d["pokemon"]:
        fid = P["form"].get(key(r["name"]))
        f = D.forms.get(fid)
        rows.append({"id": fid, "name": f["name"] if f else r["name"], "en": r["name"], "anteil": r["anteil"],
                     "typen": form_types(D, f, gen) if f else [], "werte": f["werte"] if f else None,
                     "attacken": de("move", r.get("attacken", [])), "items": de("item", r.get("items", [])),
                     "faehigkeiten": de("abil", r.get("faehigkeiten", [])), "tera": de("typ", r.get("tera", [])),
                     "partner": [P["form"].get(key(x)) for x in r.get("partner", []) if P["form"].get(key(x))]})
    return {"format": d.get("format", ""), "monat": d.get("monat", ""), "grenze": d.get("grenze", 0),
            "kaempfe": d.get("kaempfe", 0), "rows": rows}


def team_doubles(body):
    """Doppelkampf-Bewertung des Teams (ids, details, spiel) mit Rollen, Flächenattacken und Tempo."""
    from . import doppel
    D = data()
    if not D:
        return {}
    g, gen, ch = game_of(D, body.get("spiel"))
    ids = _ints(body.get("ids"))[:6]
    per = slot_details(body.get("details"), ids)
    if getattr(D, "move_target", None) is None:
        con = db.game()
        try:
            D.move_target = dict(con.execute("SELECT id, target_id FROM moves"))
        finally:
            con.close()
    role_moves = {k for _, _, _, ks in doppel.ROLES for k in ks}
    con = db.game()
    try:
        ms = []
        for i, d in zip(ids, per):
            f = D.forms.get(i)
            if not f:
                continue
            aid = _int(d.get("faehigkeit"))
            if no_abilities(g):
                abil = None
            elif aid in D.abilities:
                abil = D.abilities[aid][0]
            else:
                abil = ability_of(D, f, g)
            abil_name = next((n for k, n in D.abilities.values() if k == abil), abil) if abil else None
            moves = []
            for mid in _ints(d.get("attacken")):
                m = D.moves.get(mid)
                if m:
                    v = move_view(D, m, g)
                    moves.append({"kennung": m["kennung"], "name": v["name"], "typ": v["typ"], "ziel": D.move_target.get(mid),
                                  "schaden": m["klasse"] != attacken.STATUS and bool(v["staerke"])})
            learn = {}
            for mid, _meth, _lv, _mas in learnset(con, D, f, g)[0]:
                m = D.moves.get(mid)
                if m and m["kennung"] in role_moves:
                    learn[m["kennung"]] = m["name"]
            ms.append({"name": f["name"], "typen": form_types(D, f, gen), "init": f["init"], "faehigkeit": abil,
                       "faehigkeit_name": abil_name, "attacken": moves, "lernbar": learn})
    finally:
        con.close()
    return doppel.evaluate(ms, ch, D.type_key)


# ------------------------------------------------------------------ Schadensrechner

def effort_view(body):
    """Effort Levels (Legenden: Arceus) einer Form: Werte je Stufe, Ziel und nötige Leistungs-Items (app/effort.py).
    body: spiel, id, level, wesen (ID), el, ziel (je sechs Stufen 0–10). Dazu die Wesen zur Auswahl."""
    from . import effort
    D = data()
    f = D.forms.get(_int(body.get("id"))) if D else None
    if not f:
        raise ValueError("Pokémon nicht gefunden")
    _, gen, _ = game_of(D, body.get("spiel"))
    P = _paste_names(D)
    wesen = _int(body.get("wesen"))
    level = min(100, max(1, _int(body.get("level")) or 50))
    six = lambda v: [_int(x) or 0 for x in v][:6] if isinstance(v, list) and len(v) == 6 else None
    out = effort.view(form_stats(D, f, gen)[0], level, six(body.get("el")), six(body.get("ziel")), P["nat_mod"].get(wesen) if wesen else None)
    out["wesen_liste"] = sorted(({"id": i, "name": n, "mod": P["nat_mod"].get(i)} for i, n in P["nat_de"].items()), key=lambda x: x["name"])
    out["wesen"] = wesen
    return out


STATS_OTHER = ("legends-arceus", "champions", "pokopia")   # eigene Formeln (Effort Levels) oder keine Werte
LGPE = "lets-go-pikachu-lets-go-eevee"                     # Let's Go: IVs und AVs statt EVs


def stats_view(body):
    """Werte-Diagramm einer Form (alle Spiele außer STATS_OTHER): body spiel, id, level, wesen (ID), ivs, evs, ziel (je
    sechs Zahlen; bis Generation 2 DVs und Stat Exp). Dazu die Wesen zur Auswahl (ab Generation 3)."""
    from . import schaden
    D = data()
    f = D.forms.get(_int(body.get("id"))) if D else None
    if not f:
        raise ValueError("Pokémon nicht gefunden")
    g, gen, _ = game_of(D, body.get("spiel"))
    if g and g["kennung"] in STATS_OTHER:
        return {"rows": [], "hinweis": "In diesem Spiel rechnen die Werte anders."}
    P = _paste_names(D)
    wesen = _int(body.get("wesen"))
    level = min(100, max(1, _int(body.get("level")) or 50))
    six = lambda v: [_int(x) for x in v][:6] if isinstance(v, list) and len(v) == 6 else None
    out = schaden.stat_view(form_stats(D, f, gen)[0], level, gen, six(body.get("ivs")), six(body.get("evs")),
                            six(body.get("ziel")), P["nat_mod"].get(wesen) if wesen and gen >= 3 else None,
                            lgpe=bool(g) and g["kennung"] == LGPE)
    out["wesen_liste"] = sorted(({"id": i, "name": n, "mod": P["nat_mod"].get(i)} for i, n in P["nat_de"].items()),
                                key=lambda x: x["name"]) if gen >= 3 else []
    out["wesen"] = wesen if gen >= 3 else None
    out["minzen"] = gen >= 8
    return out


def effort_team(body):
    """Effort Levels des ganzen Teams (Legenden: Arceus): je Mitglied Stufen (None = nicht eingetragen, gerechnet mit 0),
    Werte jetzt und am Ziel, fehlende Leistungs-Items; dazu die Summe für das Team."""
    from . import effort
    D = data()
    if not D:
        return {"mitglieder": [], "bonbons": [0] * len(effort.STEINE), "sorten": [s[0] for s in effort.STEINE]}
    _, gen, _ = game_of(D, body.get("spiel"))
    P = _paste_names(D)
    details = slot_details(body.get("details"), _ints(body.get("ids")))
    out, total = [], [0] * len(effort.STEINE)
    for i, fid in enumerate(_ints(body.get("ids"))[:6]):
        f = D.forms.get(fid)
        if not f:
            continue
        d = details[i] if i < len(details) else {}
        six = lambda v: v if isinstance(v, list) and len(v) == 6 else None
        el = six(d.get("el"))
        v = effort.view(form_stats(D, f, gen)[0], min(100, max(1, _int(d.get("level")) or 50)), el, six(d.get("el_ziel")) or el,
                        P["nat_mod"].get(_int(d.get("wesen"))) if _int(d.get("wesen")) else None)
        total = [a + b for a, b in zip(total, v["bonbons"])]
        out.append({"id": fid, "slot": i, "name": f["name"], "eingetragen": el is not None, "level": v["level"],
                    "el": [r["el"] for r in v["rows"]], "ziel": [r["ziel"] for r in v["rows"]],
                    "werte": [r["wert"] for r in v["rows"]], "werte_ziel": [r["wert_ziel"] for r in v["rows"]], "bonbons": v["bonbons"]})
    return {"mitglieder": out, "bonbons": total, "sorten": [s[0] for s in effort.STEINE]}


def damage_matrix(body):
    """Übersicht für den Schadensrechner: je Team-Platz und Gegner die stärkste der gewählten Schadens-Attacken
    {rows: [{slot, id, name, zellen: [{gegner, attacke, min_pct, max_pct, sicher, moeglich, eff} | None]}], gegner: [{id, name}]}."""
    D = data()
    if not D:
        return {}
    ids = _ints(body.get("ids"))[:6]
    per = slot_details(body.get("details"), ids)
    vd = body.get("verteidiger_details") if isinstance(body.get("verteidiger_details"), list) else []
    pairs = [(v, vd[k] if k < len(vd) else {}) for k, v in enumerate(_ints(body.get("verteidiger"))[:30]) if v in D.forms]
    foes, body = [v for v, _ in pairs], dict(body, verteidiger_details=[x for _, x in pairs])
    out = []
    for i, fid in enumerate(ids):
        best = [None] * len(foes)
        for mid in (per[i].get("attacken") or [])[:4]:
            r = damage_view(dict(body, slot=i, attacke=mid, verteidiger=foes))
            if r.get("hinweis"):
                return {"rows": [], "gegner": [], "hinweis": r["hinweis"]}
            by = {x["id"]: x for x in r.get("rows", [])}
            for k, vid in enumerate(foes):
                x = by.get(vid)
                if x and (best[k] is None or x["max_pct"] > best[k]["max_pct"]):
                    best[k] = dict(x, attacke=r["attacke"], typ=r["typ"], level=r["level"])
        if fid in D.forms:
            out.append({"slot": i, "id": fid, "name": D.forms[fid]["name"], "zellen": best})
    return {"rows": out, "gegner": [{"id": v, "name": D.forms[v]["name"]} for v in foes]}


def damage_view(body):
    """Schaden einer Attacke eines Team-Platzes (ids, details, slot, attacke) gegen Verteidiger (verteidiger: [Form-IDs]).
    Optionen: krit, flaeche (None = nach dem Ziel der Attacke, nur im Doppel), vert ("0", "kp", "kp_vert": Investition
    der Verteidiger), tera_vert (Tera-Typ der Verteidiger), level (eigenes Level, sonst aus dem Platz oder 50),
    level_vert (Level der Verteidiger, sonst wie der Angreifer), wetter ("sonne", "regen"). In Champions immer Level 50.
    Fähigkeit und Item des Platzes zählen, wenn sie ohne Bedingung wirken (schaden.MODS); bei den Verteidigern die erste
    Fähigkeit, wenn sie die Typwirkung ändert. Generation 1 und 2: eigene Formel (schaden.calc_old)."""
    from . import doppel, schaden
    D = data()
    if not D:
        return {}
    g, gen, ch = game_of(D, body.get("spiel"))
    ids = _ints(body.get("ids"))[:6]
    per = slot_details(body.get("details"), ids)
    slot = _int(body.get("slot")) or 0
    if slot >= len(ids) or ids[slot] not in D.forms or _int(body.get("attacke")) not in D.moves:
        return {"rows": []}
    f, d = D.forms[ids[slot]], per[slot]
    mv = move_view(D, D.moves[_int(body.get("attacke"))], g)
    champ = not g or g["kennung"] == "champions"
    level = 50 if champ else min(100, max(1, _int(body.get("level")) or _int(d.get("level")) or 50))
    d_level = level if champ else min(100, max(1, _int(body.get("level_vert")) or level))
    P = _paste_names(D) if _int(d.get("wesen")) else None
    mod = P["nat_mod"].get(_int(d["wesen"])) if P else None
    ai = 1 if mv["klasse"] == 2 else 3
    nat = 1.1 if mod and mod[0] == ai else 0.9 if mod and mod[1] == ai else 1.0
    evs, ivs = d.get("evs"), d.get("ivs")
    a_ev = _int(evs[ai]) if isinstance(evs, list) and len(evs) == 6 else None
    a_iv = _int(ivs[ai]) if isinstance(ivs, list) and len(ivs) == 6 and ivs[ai] is not None else 31
    tera = _int(d.get("tera")) if _int(d.get("tera")) in D.types else None
    a_types = form_types(D, f, gen)
    if getattr(D, "move_target", None) is None:
        con = db.game()
        try:
            D.move_target = dict(con.execute("SELECT id, target_id FROM moves"))
        finally:
            con.close()
    doubles = bool(g) and g["kennung"] == "champions"
    spread = body.get("flaeche")
    spread = (doubles and D.move_target.get(mv["id"]) in (doppel.ALL_OTHERS, doppel.ALL_FOES)) if spread is None else bool(spread)
    inv = {"0": (0, 0), "kp": (schaden.EV_MAX, 0), "kp_vert": (schaden.EV_MAX, schaden.EV_MAX)}.get(str(body.get("vert") or "0"), (0, 0))
    d_tera = _int(body.get("tera_vert")) if _int(body.get("tera_vert")) in D.types else None
    wetter = str(body.get("wetter") or "") if gen >= 2 and str(body.get("wetter") or "") in schaden.WEATHER else ""
    names = _calc_names(D)
    item_id = _int(d.get("item"))
    a_item = names["items"].get(item_id, ("", ""))[0] if item_id else ""
    abil_id = _int(d.get("faehigkeit"))
    a_abil = (D.abilities.get(abil_id, ("",))[0] if abil_id else "") or (ability_of(D, f, g) or "")
    if no_abilities(g):
        a_abil = ""
    tkey = D.type_key.get(mv["typ"], "")
    from . import effort
    art = "la" if g and g["kennung"] == LA else "lgpe" if g and g["kennung"] == LGPE else ""
    a_base, EV_ALL = form_stats(D, f, gen)[0], schaden.EV_MAX
    six = lambda v, d: [max(0, _int(x) or 0) for x in v][:6] if isinstance(v, list) and len(v) == 6 else [d] * 6
    a_el, a_av = six(d.get("el"), 0), six(d.get("avs"), 0)
    if art:
        a_item = a_abil = ""
    rows, used = [], []
    vdet = body.get("verteidiger_details") if isinstance(body.get("verteidiger_details"), list) else []
    d_level0 = d_level
    for k, vid in enumerate(_ints(body.get("verteidiger"))[:60]):
        v = D.forms.get(vid)
        vd = vdet[k] if k < len(vdet) and isinstance(vdet[k], dict) else {}
        # Level je Gegner (Trainerteams), sonst das gemeinsame
        d_level = min(100, max(1, _int(vd.get("level")))) if _int(vd.get("level")) and not champ else d_level0
        v_item = names["items"].get(_int(vd.get("item")), ("", ""))[0] if _int(vd.get("item")) and not art and gen >= 2 else ""
        if not v or mv["klasse"] not in (2, 3) or not mv["staerke"]:
            continue
        v_types = form_types(D, v, gen)
        if gen <= 2:
            exp = schaden.EXP_MAX                                    # bis Generation 2: volle DVs und Stat Exp
            m = schaden.modifiers(mv["klasse"], mv["staerke"], tkey, 1.0, None,
                                  a_item if gen == 2 and a_item in schaden.TYPE_ITEMS else None, wetter, gen)
            r = schaden.calc_old(gen, level, mv["staerke"], mv["klasse"], mv["typ"], form_stats(D, f, gen)[0], a_types,
                                 form_stats(D, v, gen)[0], v_types, ch, crit=bool(body.get("krit")),
                                 d_inv=(inv[0] > 0, inv[1] > 0), d_level=d_level, a_exp=exp, item=m["staerke"], weather=m["wetter"])
        else:
            eff = schaden.effect(ch, mv["typ"], [d_tera] if d_tera else v_types)
            m = schaden.modifiers(mv["klasse"], mv["staerke"], tkey, eff, a_abil, a_item, wetter, gen)
            if art:                            # eigene Werte-Formel: Werte vorab, Fähigkeiten und Items gibt es nicht
                di = 2 if mv["klasse"] == 2 else 4
                vb = form_stats(D, v, gen)[0]
                if art == "la":
                    a_stat = effort.stat(a_base[ai], level, a_el[ai], ai, nat)
                    sv = (effort.stat(vb[di], d_level, 10 if inv[1] else 0, di), effort.stat(vb[0], d_level, 10 if inv[0] else 0, 0))
                else:
                    a_stat = schaden.stat_lgpe(a_base[ai], level, 31, a_av[ai], nat)
                    sv = (schaden.stat_lgpe(vb[di], d_level, 31, 200 if inv[1] else 0), schaden.stat_lgpe(vb[0], d_level, 31, 200 if inv[0] else 0, hp=True))
            d_ab = ability_of(D, v, g)
            dm = typen.ABILITY_DEFENSE.get(d_ab or "", {}).get(mv["typ"], 1.0)
            di_ = schaden.DEF_ITEMS.get(v_item)
            d_mult = di_[1] if di_ and di_[0] in (0, mv["klasse"]) and gen >= 4 and (v_item != "eviolite" or not v["endstufe"]) else 1.0
            r = schaden.calc(level, mv["staerke"], mv["klasse"], mv["typ"], a_base, a_types, form_stats(D, v, gen)[0], v_types, ch,
                             a_tera=tera, d_tera=d_tera, a_ev=EV_ALL if art else a_ev, a_iv=a_iv, a_nat=nat, d_ev=inv, spread=spread,
                             crit=bool(body.get("krit")), crit_mult=2.0 if gen <= 5 else 1.5, d_level=d_level, mods=m, d_mod=dm,
                             d_stats=sv if art else None, a_stat=a_stat if art else None, d_mult=d_mult)
            if d_mult != 1.0:
                r["item_vert"] = f"{names['item_de'].get(v_item, v_item)}: {di_[2]}"
            if dm != 1.0:
                r["faehigkeit_vert"] = D.abilities.get(next((a for a, h in v["faehigkeiten"] if not h), 0), ("", d_ab))[1]
        r.update(_calc_steps(gen, art, mv, m, r, level, d_level, a_base, ai, a_iv, a_ev, a_el, a_av, nat, v, form_stats(D, v, gen)[0],
                             inv, spread, bool(body.get("krit")), wetter, r.get("item_vert")))
        if v_item == "focus-sash" and gen >= 4 and r.get("sicher") == 1:
            r["item_vert"], r["sicher"] = names["item_de"].get(v_item, v_item) + ": übersteht den ersten Treffer aus vollen KP mit 1 KP", 2
            r["moeglich"] = 2
        for t in m["texte"]:
            if t not in used:
                used.append(t)
        rows.append(dict(r, id=vid, name=v["name"]))
    label = {"faehigkeit": lambda k: names["abil"].get(k, k), "item": lambda k: names["item_de"].get(k, k),
             "wetter": lambda k: {"sonne": "Sonne", "regen": "Regen"}.get(k, k)}
    return {"angreifer": f["name"], "attacke": mv["name"], "typ": mv["typ"], "klasse": mv["klasse"], "staerke": mv["staerke"],
            "stab": schaden.stab_of(mv["typ"], a_types, tera), "level": level, "level_vert": d_level, "flaeche": spread, "tera": tera, "wesen": nat, "ev": a_ev, "gen": gen,
            "krit": 2.0 if gen <= 5 else 1.5, "rows": rows, "wetter": wetter, "art": art,
            "el": a_el[ai] if art == "la" else None, "av": a_av[ai] if art == "lgpe" else None,
            "eingerechnet": [f"{label[kind](k)}: {txt}" for kind, k, txt in used]}


def _calc_steps(gen, art, mv, m, r, level, d_level, a_base, ai, a_iv, a_ev, a_el, a_av, nat, v, vb, inv, spread, crit, wetter, d_item):
    """Rechenweg einer Zeile für den Tooltip: woraus Angriff und Verteidigung bestehen, die Faktoren der Reihe nach."""
    from . import schaden
    di = (2 if mv["klasse"] == 2 else 4) if not (gen == 1 and mv["klasse"] != 2) else 3
    fl = lambda x: f"{x:g}".replace(".", ",")
    if gen <= 2:
        a_info, d_extra = f"Basis {a_base[ai]}, Level {level}, DV 15, volle Stat Exp", "DV 15, " + ("volle Stat Exp" if inv[1] else "ohne Stat Exp")
    elif art == "la":
        a_info, d_extra = f"Basis {a_base[ai]}, Level {level}, Effort Level {a_el[ai]}", f"Effort Level {10 if inv[1] else 0}"
    elif art == "lgpe":
        a_info, d_extra = f"Basis {a_base[ai]}, Level {level}, IV 31, {a_av[ai]} AV", f"IV 31, {200 if inv[1] else 0} AV"
    else:
        a_info = f"Basis {a_base[ai]}, Level {level}, IV {a_iv}, {schaden.EV_MAX if a_ev is None else a_ev} EV"
        d_extra = f"IV 31, {inv[1]} EV"
    if nat != 1.0 and gen >= 3:
        a_info += f", Wesen ×{fl(nat)}"
    if m.get("wert", 1.0) != 1.0:
        a_info += f", ×{fl(m['wert'])} durch Item oder Fähigkeit"
    d_info = f"Basis {vb[di]}, Level {d_level}, {d_extra}" + (f"; {d_item}" if d_item else "")
    fx = []
    if gen <= 2:
        if m.get("staerke", 1.0) != 1.0:
            fx.append(["Typ-Item", m["staerke"]])
        if crit:
            fx.append(["Volltreffer (Level doppelt)" if gen == 1 else "Volltreffer", 2 if gen == 2 else None])
        if m.get("wetter", 1.0) != 1.0:
            fx.append([{"sonne": "Sonne", "regen": "Regen"}.get(wetter, wetter), m["wetter"]])
        if r["stab"] > 1:
            fx.append(["Eigentyp", r["stab"]])
        fx.append(["Wirkung", r["eff"]])
        fx.append(["Zufall", "217–255 / 255"])
    else:
        if m.get("staerke", 1.0) != 1.0:
            fx.append([f"Stärke {mv['staerke']} → {r['staerke']}", None])
        if spread:
            fx.append(["Fläche", 0.75])
        if m.get("wetter", 1.0) != 1.0:
            fx.append([{"sonne": "Sonne", "regen": "Regen"}.get(wetter, wetter), m["wetter"]])
        if crit:
            fx.append(["Volltreffer", 2.0 if gen <= 5 else 1.5])
        fx.append(["Zufall", "0,85–1"])
        if r["stab"] > 1:
            fx.append(["Eigentyp", r["stab"]])
        fx.append(["Wirkung", r["eff"]])
        if m.get("ende", 1.0) != 1.0:
            fx.append(["Item", m["ende"]])
    return {"a_info": a_info, "d_info": d_info, "faktoren": fx}


def _calc_names(D):
    """Für den Schadensrechner: {"items": {ID: (Kennung, Name)}, "item_de": {Kennung: Name}, "abil": {Kennung: Name}}."""
    if getattr(D, "calc_names", None) is None:
        con = db.game()
        try:
            de = dict(con.execute("SELECT item_id, name FROM item_names WHERE local_language_id = 6"))
            items = {i: (k, de.get(i) or k) for i, k in con.execute("SELECT id, identifier FROM items")}
        except sqlite3.OperationalError:
            items = {}
        finally:
            con.close()
        D.calc_names = {"items": items, "item_de": {k: n for k, n in items.values()},
                        "abil": {k: n for k, n in D.abilities.values()}}
    return D.calc_names


# ------------------------------------------------------------------ Tera-Raids (Karmesin/Purpur)

def _raids(con, D, g, form=None, stars=None):
    """Tera-Raids aus PKHeX (Tabelle raid): je Begegnung Gebiet, Sterne, Level, Tera-Typ (None = zufällig), Attacken
    und die Typen, die den Tera-Typ sehr effektiv treffen (der Raid-Gegner verteidigt mit ihm)."""
    sql, args = "SELECT gebiet, sterne, form, level, tera, attacken FROM raid WHERE 1", []
    if form is not None:
        sql, args = sql + " AND form = ?", args + [form]
    if stars:
        sql, args = sql + " AND sterne = ?", args + [stars]
    try:
        rows = con.execute(sql + " ORDER BY sterne DESC, level DESC, form", args).fetchall()
    except sqlite3.OperationalError:          # Datenbank vor 0.22.0
        return []
    _, gen, ch = game_of(D, g["kennung"] if g else None)
    out = []
    for gebiet, sterne, fid, level, tera, moves in rows:
        f = D.forms.get(fid)
        if not f:
            continue
        ms = []
        for mid in json.loads(moves or "[]"):
            if mid in D.moves:
                v = move_view(D, D.moves[mid], g)
                ms.append({"id": mid, "name": v["name"], "typ": v["typ"], "klasse": v["klasse"]})
        weak = [a for a, x in typen.defense([tera], ch).items() if x > 1] if tera in D.types else []
        out.append({"gebiet": gebiet, "sterne": sterne, "id": fid, "name": f["name"], "typen": form_types(D, f, gen),
                    "level": level, "tera": tera if tera in D.types else None, "attacken": ms, "schwach": weak})
    return out


def raid_list(p):
    """Alle Tera-Raids (optional nur sterne=N) für die Liste."""
    D = data()
    if not D:
        return {"rows": []}
    g, _, _ = game_of(D, p.get("spiel") or "scarlet-violet")
    con = db.game()
    try:
        return {"rows": _raids(con, D, g, stars=_int(p.get("sterne")) or None)}
    finally:
        con.close()


def _crypto(con, D, g, fid):
    """Crypto-Pokémon (Colosseum, XD) aus PKHeX: Level, Attacken, Läuterungswert (Heart Gauge), Trainer und Orte (englisch)."""
    try:
        rows = con.execute("SELECT nr, level, attacken, messer, trainer, orte FROM crypto WHERE spiel = ? AND form = ? ORDER BY nr",
                           (g["kennung"], fid)).fetchall()
    except sqlite3.OperationalError:          # Datenbank vor 0.22.0
        return []
    return [{"nr": nr, "level": lv, "messer": gauge, "trainer": who, "orte": json.loads(orte or "[]"),
             "attacken": [D.moves[m]["name"] for m in json.loads(moves or "[]") if m in D.moves]}
            for nr, lv, moves, gauge, who, orte in rows]
