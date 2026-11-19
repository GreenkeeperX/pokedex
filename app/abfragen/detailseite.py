"""Detailseite: Entwicklungen, mehr Details (Fang, Zucht, EV), Spielwissen, Optik, getragene Items, Pokopia.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar.
"""
import json
import os
import sqlite3

from .. import db, fehler, spiele, store, typen

from .fangen import (BALLS, GROWTH_DE, HISUI_BALLS, HISUI_NO_TABLE, STAT_KEYS, ball_rows, catch_chance_la, catch_table,
    sleep_factor)
from .basis import WIKI, _names, ability_of, data, form_types, game_of, no_abilities, profil, row
from .auftraege import _auftragsspiel, _requests, _research, _wiki_title
from .liste import _int
from .karten import _enc
from .lernen import joined, pick_text, ranked_moves, text_rows
from .raids import _crypto, _raids


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


def _more(con, f, g, gen):
    """Mehr Details: Fangrate mit Fangchance, Geschlecht, Wachstum, Ei-Gruppen, Ei-Zyklen, EV-Ausbeute. Was es im Spiel
    nicht gibt, bleibt weg; das sagt das Spielprofil (fangformel, baelle, zucht, werte)."""
    out = {}
    try:
        sp = con.execute("SELECT capture_rate, gender_rate, hatch_counter, base_happiness, growth_rate_id FROM pokemon_species "
                         "WHERE id = ?", (f["art"],)).fetchone()
    except Exception as err:
        fehler.melden(err)
        return out
    if not sp:
        return out
    pr = profil(g)
    hisui = pr["fangformel"] == "hisui"
    if sp["capture_rate"] is not None:
        out["fangrate"] = sp["capture_rate"]
    if sp["capture_rate"] is not None and pr["fangformel"] != "keine":
        if hisui:                             # 0.50: eigene Fangrate und eigene Formel (Rechnung in detail.js, catchHtmlLA)
            try:
                r = con.execute("SELECT rate FROM fangrate WHERE spiel = ? AND art = ?", (g["kennung"], f["art"])).fetchone()
            except Exception as err:
                fehler.melden(err)
                r = None
            out["fangrate_la"] = r[0] if r else None
            out["fang_hisui"] = [b[:4] for b in HISUI_BALLS if b[0] not in HISUI_NO_TABLE]
        extra = ()
        if g and pr["baelle"] == "standard":
            try:
                have = {r["name"] for r in con.execute("SELECT name, spiele FROM item WHERE tasche = 'Bälle'")
                        if g["id"] in json.loads(r["spiele"] or "[]")}
                w = con.execute("SELECT weight FROM pokemon WHERE id = ?", (f["id"],)).fetchone()
                extra = ball_rows(gen, have, f, w[0] / 10 if w and w[0] is not None else None)
            except Exception as err:
                fehler.melden(err)
                extra = ()
        if hisui:                             # dieselbe Tabelle und Formel wie die Oberfläche (Sternrang 10, Level bis 10)
            rate_la = out.get("fangrate_la") or sp["capture_rate"]
            out["fangen"] = [{"ball": b[0], "faktor": b[1], "voll": catch_chance_la(rate_la, b[1]), "rot": catch_chance_la(rate_la, b[1], 0),
                              "status": catch_chance_la(rate_la, b[1], 0, 2.0), "schlaf": catch_chance_la(rate_la, b[1], 0, 2.0)}
                             for b in HISUI_BALLS if b[0] not in HISUI_NO_TABLE]
        else:
            out["fangen"] = catch_table(sp["capture_rate"], gen, BALLS, extra)
        out["schlaf_faktor"] = str(sleep_factor(gen)).replace(".", ",")
        out["fang_gen"] = gen
        out["fang_grob"] = pr["fangformel"] in spiele.FANG_GROB
    if sp["gender_rate"] is not None and gen >= 2:
        gr = sp["gender_rate"]
        out["geschlecht"] = "geschlechtslos" if gr < 0 else f"{100 - gr * 12.5:g} % männlich, {gr * 12.5:g} % weiblich"
    try:
        gk = con.execute("SELECT identifier FROM growth_rates WHERE id = ?", (sp["growth_rate_id"],)).fetchone()
        if gk:
            out["wachstum"] = GROWTH_DE.get(gk[0], gk[0])
    except Exception as err:
        fehler.melden(err)
    if pr["zucht"]:                           # 0.60.0: Ei-Gruppen nur, wo es Zucht gibt (vorher überall außer in Legenden: Arceus)
        try:
            eg = [r[0] for r in con.execute(
                "SELECT COALESCE(p.name, pe.egg_group_id) FROM pokemon_egg_groups pe LEFT JOIN egg_group_prose p "
                "ON p.egg_group_id = pe.egg_group_id AND p.local_language_id = 6 WHERE pe.species_id = ?", (f["art"],))]
        except Exception as err:
            fehler.melden(err)
            eg = []
        if eg:
            out["eigruppen"] = eg
            if sp["hatch_counter"] is not None:
                out["eizyklen"] = sp["hatch_counter"]
    if pr["werte"] == "ev":                   # 0.60.0: EV-Ausbeute nur, wo es EVs gibt (vorher ab Generation 3 überall außer in Legenden: Arceus)
        try:
            ev = [(r[0], r[1]) for r in con.execute("SELECT stat_id, effort FROM pokemon_stats WHERE pokemon_id = ? AND effort > 0",
                                                     (f["id"],))]
            out["ev"] = [{"wert": STAT_KEYS[s - 1], "punkte": e} for s, e in ev if 1 <= s <= 6]
        except Exception as err:
            fehler.melden(err)
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
    pr = profil(g)
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
                    forschung=_research(con, f["art"]) if pr["forschung"] else [], faehigkeiten=abil,
                    auftraege=_requests(con, D, f["art"], _auftragsspiel(pr)) if _auftragsspiel(pr) else [],
                    wirkung={str(a): v for a, v in dvec.items()}, faehigkeit_wirkt=ab if ab in typen.ABILITY_DEFENSE else "",
                    entwicklung=_evolutions(con, D, f), fundorte=_enc(con, g, fid), fundquelle="PKHeX" if g and g["kennung"] in D.areas else "PokéAPI", formen=siblings, attacken=moves,
                    im_spiel=(fid in D.in_game.get(g["id"], {})) if g else True, mehr=_more(con, f, g, gen), extras=_extras(fid),
                    wiki=WIKI + _wiki_title(D, f), getragen=_held(con, g, f), optik=_optik(con, f), pokopia=_pokopia(con, g, f),
                    raids=_raids(con, D, g, form=fid) if pr["raids"] else [],
                    crypto=_crypto(con, D, g, fid) if pr["crypto"] else [],
                    spielwissen=knowledge(con, g["kennung"] if g else "", fid))
    finally:
        con.close()


WISSEN = os.path.join(os.path.dirname(__file__), "..", "..", "extra", "spielwissen.json")
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
    except Exception as err:
        fehler.melden(err)
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
    except Exception as err:
        fehler.melden(err)
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
    if not profil(g)["eigene_dexe"]:
        return []
    from .. import serebii
    try:
        rows = con.execute("SELECT dex, nr, name, spezial FROM pokopia WHERE art = ? ORDER BY dex = 'haupt' DESC, nr", (f["art"],)).fetchall()
    except Exception as err:
        fehler.melden(err)
        return []
    return [{"dex": serebii.POKOPIA_DEX.get(r[0], r[0]), "nr": r[1], "name": r[2],
             "spezial": [serebii.spezial_de(k) for k in json.loads(r[3] or "[]")]} for r in rows]
