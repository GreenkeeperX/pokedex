"""Grundlage: Daten im Speicher (Data, data), Spiel und Formen, Profil, Spiele und Metadaten für die Oberfläche.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar.
"""
import json
import os
import re
import threading

from .. import attacken, db, fehler, spiele, typen

from .fangen import HISUI_BALLS


LA = "legends-arceus"          # Schlüssel der Tabellen von Legenden: Arceus (Forschung, Fangrate, Aufträge, eigene Attackenwerte)
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
    except Exception as err:
        fehler.melden(err)
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
        except Exception as err:
            fehler.melden(err)
            self.past = []
        self.games = [dict(r) for r in con.execute("SELECT id, kennung, name, gen, reihenfolge FROM spiel ORDER BY reihenfolge")]
        self.game_by = {g["kennung"]: g for g in self.games}
        for g in self.games:                    # 0.60.0: ein Spiel ohne Profil gilt als Hauptspiel seiner Generation, das soll man sehen
            if not spiele.bekannt(g["kennung"]):
                fehler.notiere("abfrage", "spiele.profil", "Spiel ohne Profil",
                               f"{g['kennung']} gilt als Hauptspiel der Generation {g['gen']}; Eintrag in app/spiele.py fehlt")
            elif spiele.profil(g["kennung"])["gen"] != g["gen"]:
                fehler.notiere("abfrage", "spiele.profil", "Generation weicht ab",
                               f"{g['kennung']}: Datenbank {g['gen']}, Profil {spiele.profil(g['kennung'])['gen']}; es gilt die der Datenbank")
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
        except Exception as err:
            fehler.melden(err)
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
        except Exception as err:
            fehler.melden(err)
        self.in_game, self.in_dex = {}, {}
        try:
            sf = con.execute("SELECT spiel, form, nr, dex, dexk FROM spiel_form").fetchall()
        except Exception as err:                      # Datenbank vor 0.43: ohne Dex je Nummer
            fehler.melden(err)
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
        except Exception as err:
            fehler.melden(err)
        self.methods = _names(con, "pokemon_move_method_prose", "pokemon_move_method_id")
        self.method_key = dict(con.execute("SELECT id, identifier FROM pokemon_move_methods"))
        # TM-Nummern je Spiel und Attacke: tm012 → TM012, hm03 → VM03, tr05 → TP05
        self.machines = {}
        try:
            rows = con.execute("SELECT m.version_group_id, m.move_id, i.identifier FROM machines m JOIN items i ON i.id = m.item_id").fetchall()
            wide = {vg for vg, _, ident in rows if re.fullmatch(r"tm\d{3,}", ident or "")}
            for vg, mid, ident in rows:
                self.machines[(vg, mid)] = machine_label(ident, 3 if vg in wide else 2)
        except Exception as err:
            fehler.melden(err)
        # Attackenwerte je Spiel aus dem PokéWiki (Legenden: Arceus mit Kraft- und Tempostil)
        self.game_moves = {}
        try:
            for r in con.execute("SELECT * FROM attacke_spiel"):
                self.game_moves[(r["spiel"], r["attacke"])] = dict(r)
        except Exception as err:
            fehler.melden(err)
        # Deutsche Attackentexte je Spiel (PokéAPI, ergänzt aus dem PokéWiki): {Attacke: {Spiel: [(Edition, Text, Quelle)]}}
        self.move_texts = {}
        try:
            for mid, sp, ed, txt, src in con.execute("SELECT id, spiel, edition, text, quelle FROM spieltext WHERE art = 'attacken'"):
                self.move_texts.setdefault(mid, {}).setdefault(sp, []).append((ed, txt, src))
        except Exception as err:
            fehler.melden(err)
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
    return g, gen, chart_of(D, g, gen)


def profil(g):
    """Profil eines Spiels aus D.games (app/spiele.py); ohne Spiel das Übliche der neuesten Generation."""
    return spiele.profil(g["kennung"], g.get("gen")) if g else spiele.profil("")


def profil_von(D, kennung):
    """Profil zu einer Kennung, auch wenn die Datenbank das Spiel (noch) nicht führt."""
    g = D.game_by.get(kennung or "") if D else None
    return profil(g) if g else spiele.profil(kennung or "")


def chart_of(D, g, gen):
    """Typtabelle des Spiels: die der Generation, in Legenden: Arceus mit eigener Regel (×2,5 und ×0,4, Eigentyp ×1,25)."""
    if profil(g)["typfaktoren"] == "la":
        if ("la", gen) not in D.charts:
            D.charts[("la", gen)] = typen.for_la(D.chart(gen))
        return D.charts[("la", gen)]
    return D.chart(gen)


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
    return not profil(g)["faehigkeiten"]


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


def machine_label(ident, width=2):
    """tm12 → TM12, hm03 → VM03, tr05 → TP05; width: Stellen (Karmesin/Purpur zählt dreistellig)."""
    m = re.match(r"(tm|hm|tr)(\d+)$", ident or "")
    return {"tm": "TM", "hm": "VM", "tr": "TP"}[m.group(1)] + m.group(2).zfill(width) if m else ""


HOME = spiele.HOME          # kein Spiel der PokéAPI: alle Pokémon mit den neuesten Werten, eigene Sammlung


def games():
    D = data()
    if not D:
        return []
    home = {"kennung": HOME, "name": "Pokémon HOME", "gen": 0, "home": True, "gebiete": [],
            "pokemon": sum(1 for f in D.forms.values() if f["relevant"]), "profil": spiele.fuer_oberflaeche(spiele.profil(HOME, D.max_gen))}
    return [home] + [{"kennung": g["kennung"], "name": g["name"], "gen": g["gen"], "pokemon": len(D.in_game.get(g["id"], {})),
                      "gebiete": list(D.areas.get(g["kennung"], {})), "profil": spiele.fuer_oberflaeche(profil(g))} for g in reversed(D.games)]


def meta():
    D = data()
    if not D:
        return {}
    rel = [f for f in D.forms.values() if f["relevant"] and not f["kampfform"]]
    return {"typen": [{"id": t, "name": n, "kennung": D.type_key.get(t)} for t, n in D.types.items()],
            "hisui_baelle": HISUI_BALLS,
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
