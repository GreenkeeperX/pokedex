"""Attacken: Texte, Lernlisten, Maschinen, bewährte Sets, Wertung, Reiter Attacken; TMs und Sammelobjekte auf den
Karten.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar.
"""
import json
import math
import re

from .. import attacken, db, fehler, importer, showdown, spiele

from .basis import LA, ability_of, chart_of, data, form_types, game_of, machine_label, old_class, profil
from .liste import _int, _ints
from .karten import mg_map


# ------------------------------------------------------------------ Attacken

def pick_text(D, per, g):
    """Text für das gewählte Spiel aus {Spiel: [(Edition, Text, Quelle)]}: das Spiel selbst (bei Erweiterungen das
    Hauptspiel), sonst das letzte Spiel davor mit Text, sonst das erste danach. Gibt {"texte": [{edition, text}], "quelle",
    "aus"} zurück; "aus" nennt das Spiel, wenn der Text nicht aus dem gewählten stammt."""
    if not per:
        return {"texte": [], "quelle": "", "aus": ""}
    order = {x["kennung"]: x["reihenfolge"] for x in D.games}
    names = {x["kennung"]: x["name"] for x in D.games}
    want = spiele.basis(g["kennung"]) if g else None         # Erweiterungen ohne eigene Texte nehmen die ihres Hauptspiels
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
    except Exception as err:
        fehler.melden(err)
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


def learn_game(D, g):
    """Spiel, dessen Lernliste für g gilt: das Hauptspiel bei Erweiterungen ohne eigene Lernliste (die PokéAPI führt deren
    Lehrer-Attacken und TMs beim Hauptspiel), sonst g selbst."""
    pr = profil(g)
    if pr["lernliste"] == "hauptspiel":
        return next((x for x in D.games if x["kennung"] == pr["hauptspiel"]), g)
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
    except Exception as err:
        fehler.melden(err)
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
    except Exception as err:
        fehler.melden(err)
        return set()
    try:
        return {int(o) for (o,) in u.execute("SELECT objekt FROM gefunden WHERE spiel = ? AND karte = 'tm'", (str(spiel or ""),))
                if str(o).isdigit()}
    except Exception as err:
        fehler.melden(err)
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
    except Exception as err:
        fehler.melden(err)
        return {}
    return {mid: label for mid, label in out.items() if mid not in have}


TM_RX = re.compile(r"\b(TM|HM|VM|TR|TP)[ -]?0*(\d{1,3})\b")


def tm_key(text):
    """„TM27“, „HM 03“, „TR-12“ → („TM“, 27), („VM“, 3), („TP“, 12); None ohne Maschine."""
    m = TM_RX.search(str(text or ""))
    if not m:
        return None
    return ({"HM": "VM", "TR": "TP"}.get(m.group(1), m.group(1)), int(m.group(2)))


# 0.55: Sammelobjekte auf den Karten: alles in der Gruppe „Sammelobjekte“ und Kategorien mit diesen Namen (englisch oder deutsch)
COLLECT_RX = re.compile(r"(?i)\b(wisps?|geisterlicht|unown|icognito|old verse|gedicht|stakes?|pflock|pflöcke|colou?rful screws?|"
                        r"schraube|diglett|digda|lost satchel|verlorene tasche|shrines?|schrein|mega stones?|megastein|flags?|fahne)")


def _js_round(v):
    """Math.round wie im Browser (x.5 rundet auf), für Schlüssel, die die Oberfläche bildet."""
    return math.floor(v + 0.5)


def point_key(p, slug):
    """Schlüssel eines Kartenpunkts in user.db gefunden, wie mgView ihn bildet: (Karte, Objekt) oder None."""
    if p.get("aq"):
        k, _, o = p["aq"].partition("|")
        return k, o
    if p.get("id") and not p.get("sp"):
        return "mg-" + slug, f"mg:{p['id']}"
    o = p.get("o")
    if o:
        return o.get("k"), f"{o.get('art')}:{_js_round(o.get('x') or 0)}:{_js_round(o.get('z') or 0)}"
    return None


def collectibles(maps, load, got):
    """Sammelobjekte je Karte mit Fortschritt. maps: abruf.mg_maps, load(m): zusammengeführte Karte, got: {Karte: [Objekt]}
    (server.found). Gibt {spiel, sachen: [{titel, n, gefunden, karten: [{slug, karte, kat, n, gefunden}]}]}, je Titel über
    alle Karten des Spiels zusammengezählt."""
    have = {(k, str(o)) for k, os in (got or {}).items() for o in os}
    by = {}
    for m in (maps or {}).get("karten", []):
        try:
            d = load(m)
        except Exception as err:
            fehler.melden(err, f"Karte {m.get('slug')}", "karte")
            continue
        cats = {}
        for G in d.get("gruppen", []):
            for C in G.get("kategorien", []):
                if G.get("titel") == "Sammelobjekte" or COLLECT_RX.search(C.get("en") or "") or COLLECT_RX.search(C.get("titel") or ""):
                    cats[C["id"]] = C
        if not cats:
            continue
        cnt = {}
        for p in d.get("punkte", []):
            if p.get("c") not in cats:
                continue
            k = point_key(p, m["slug"])
            ok = k in have if k else False
            if not ok and p.get("o") and p.get("id"):       # früher als Symbol der Spieldaten markiert
                ok = point_key({"o": p["o"]}, m["slug"]) in have
            n = cnt.setdefault(p["c"], [0, 0])
            n[0] += 1
            n[1] += ok
        for cid, (n, f) in cnt.items():
            t = cats[cid]["titel"]
            e = by.setdefault(t, {"titel": t, "n": 0, "gefunden": 0, "karten": []})
            e["n"] += n
            e["gefunden"] += f
            e["karten"].append({"slug": m["slug"], "karte": m.get("titel") or m["slug"], "kat": cid, "n": n, "gefunden": f})
    out = sorted(by.values(), key=lambda e: (e["gefunden"] >= e["n"], -e["n"], e["titel"]))
    return {"spiel": (maps or {}).get("spiel"), "sachen": out}


def tm_places(maps, load=None):
    """0.53: Wo es Maschinen gibt, aus den Kartenpunkten aller Karten des Spiels (Name oder Text nennt „TM27“ usw.):
    {"TM27": [{karte, titel, id, name}]}, je Maschine höchstens 6 Stellen. load(m): die fertige Karte (Kartencache)."""
    out = {}
    if not maps:
        return out
    for m in maps["karten"]:
        try:
            r = load(m) if load else mg_map(m, maps["spiel"], maps["am"])
        except Exception as err:
            fehler.melden(err, f"Karte {m.get('slug')}", "karte")
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
    ch = chart_of(D, g, gen)
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
