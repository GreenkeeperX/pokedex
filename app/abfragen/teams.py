"""Teams: Plätze, Verbesserungen, Vorschläge, Gefangen, Was fehlt mir noch, Trainer, Gegner; Showdown-Text (Import und
Export).

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar.
"""
import json

from .. import attacken, db, fehler, importer, spiele, team, typen

from .basis import HOME, _names, data, form_stats, form_types, game_of, member, no_abilities, profil, row
from .fortschritt import vertreter
from .liste import _int, _ints, candidates, own_marks
from .karten import FIXED_METHODS, areas
from .lernen import learn_game, learnset, move_view, ranked_moves
from .detailseite import evo_text


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
    ev["tera"] = tera_effect(D, ms, details, ch) if profil(g)["tera"] else []
    return ev


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


NO_EGGS = 15                     # Ei-Gruppe „Unbekannt“: legendäre und manche besondere Pokémon schlüpfen nie
WAYS = ("jetzt", "wild", "fest", "entwicklung", "raid", "zucht", "tausch", "edition", "unklar", "home")


def missing(p):
    """0.54: Was fehlt mir noch im gewählten Spiel: die Arten des Spiel-Dex, von denen keine Form als gefangen markiert
    ist, je mit den Wegen dorthin. p: spiel, edition (Name einer Edition des Spiels: Fundorte nur der anderen Edition
    zählen dann als „andere Edition“). Gibt {spiel, editionen, edition, arten, gefangen, fehlt: [{art, id, name, nr, dex,
    dexk, typen, legendaer, weg, wege: [{art, text, ort?, von?, hast?}]}]} zurück; weg ist der beste Weg:
    jetzt (Vorstufe oder Weiterentwicklung gefangen: entwickeln oder züchten), wild, fest (Geschenk oder einmalige
    Begegnung), entwicklung, raid (Tera-Raid), zucht, tausch (Tausch-Entwicklung), edition (nur in der anderen Edition),
    unklar (kein Weg in den Daten); Reihenfolge wie WAYS. 0.69.0: auch für Pokémon HOME (jede Art mit dem Weg home:
    in einem Spiel fangen und übertragen); jeder Eintrag trägt die Generation der Art (gen)."""
    D = data()
    if not D:
        return None
    if p.get("spiel") == HOME:
        return _missing_home(D)
    g, gen, _ = game_of(D, p.get("spiel"))
    if not g:
        return None
    caught_forms = own_marks("gefangen", g["kennung"])
    caught = {D.forms[i]["art"] for i in caught_forms if i in D.forms}
    rep = vertreter(D, g)           # je Art die Form, die der Dex des Spiels zeigt
    con = db.game()
    try:
        vn = _names(con, "version_names", "version_id")
        eds = [vn.get(v) or ident for v, ident in con.execute("SELECT id, identifier FROM versions WHERE version_group_id = ? ORDER BY id",
                                                              (g["id"],))]
        von = dict(con.execute("SELECT id, evolves_from_species_id FROM pokemon_species WHERE evolves_from_species_id IS NOT NULL"))
        try:
            no_eggs = {r[0] for r in con.execute("SELECT species_id FROM pokemon_egg_groups WHERE egg_group_id = ?", (NO_EGGS,))}
        except Exception as err:
            fehler.melden(err)
            no_eggs = set()
        items = _names(con, "item_names", "item_id")
        trig = _names(con, "evolution_trigger_prose", "evolution_trigger_id")
        locs = _names(con, "location_names", "location_id")
        evo = {}
        for r in con.execute("SELECT * FROM pokemon_evolution"):
            r = dict(r)
            t = evo_text(r, D, items, trig, locs)
            e = evo.setdefault(r["evolved_species_id"], {"texte": [], "tausch": False})
            if t and t not in e["texte"]:
                e["texte"].append(t)
            e["tausch"] = e["tausch"] or r.get("evolution_trigger_id") == 2
        raids = {}
        if profil(g)["raids"]:
            try:
                for fid, st in con.execute("SELECT form, sterne FROM raid WHERE spiel = ?", (profil(g)["raids"],)):
                    if fid in D.forms:
                        raids.setdefault(D.forms[fid]["art"], set()).add(st)
            except Exception as err:
                fehler.melden(err)
    finally:
        con.close()
    edition = p.get("edition") if p.get("edition") in eds else ""
    # Fundorte je Art aus der Gebietsliste (gleiche Quelle wie Karte › Gebiete)
    wild = {}
    for gb in (areas({"spiel": g["kennung"]}) or {}).get("gebiete", []):
        for m in gb["mons"]:
            f = D.forms.get(m["id"])
            if f:
                wild.setdefault(f["art"], []).append({"ort": gb["ort"], "methode": m["methode"], "level": m["level"],
                                                      "editionen": m["editionen"], "bedingungen": m["bedingungen"]})
    kids = {}
    for a, b in von.items():
        kids.setdefault(b, []).append(a)

    def later(a, n=0):
        out = set()
        for k in kids.get(a, []):
            out |= {k} | (later(k, n + 1) if n < 4 else set())
        return out

    breeding = profil(g)["zucht"]              # 0.54: ohne Zucht (kein Ei, keine Pension) fällt „Zucht“ als Weg weg
    out = []
    for art, (_, f, nr, di) in rep.items():
        if art in caught:
            continue
        ways = []
        fx = lambda w: w["methode"] in FIXED_METHODS or w["methode"].startswith("fest")
        here = [w for w in wild.get(art, []) if not fx(w)]
        fixed = [w for w in wild.get(art, []) if fx(w)]
        mine = [w for w in here if not w["editionen"] or not edition or edition in w["editionen"]]
        other = [w for w in here if w not in mine]
        if mine:
            seen, txt = set(), []
            for w in mine:
                if w["ort"] in seen:
                    continue
                seen.add(w["ort"])
                txt.append(w["ort"] + (f" (Lv {w['level']})" if w["level"] else ""))
            only = sorted({e for w in mine for e in w["editionen"]}) if all(w["editionen"] for w in mine) else []
            ways.append({"art": "wild", "text": ", ".join(txt[:2]) + (f" und {len(txt) - 2} weitere" if len(txt) > 2 else ""),
                         "ort": mine[0]["ort"], "methode": mine[0]["methode"], "nur": only})
        if art in raids:
            st = sorted(raids[art])
            ways.append({"art": "raid", "text": "Tera-Raid " + (f"{st[0]}★" if len(st) == 1 else f"{st[0]}–{st[-1]}★")})
        pre = von.get(art)
        if pre and pre in rep:
            e = evo.get(art, {"texte": [], "tausch": False})
            # Vorstufe oder eine Stufe davor gefangen: dann geht es jetzt
            have, x, n = None, pre, 0
            while x and n < 4:
                if x in caught:
                    have = x
                    break
                x, n = von.get(x), n + 1
            pf = rep[pre][1]
            ways.append({"art": "tausch" if e["tausch"] else "entwicklung", "von": pf["id"], "von_name": pf["name"],
                         "text": f"aus {pf['name']}" + (": " + " oder ".join(e["texte"]) if e["texte"] else ""),
                         "hast": have is not None, "hast_name": rep[have][1]["name"] if have in rep else ""})
        # Zucht: eine Weiterentwicklung, die Eier legt (Babys wie Pichu sind selbst „Unbekannt“, Pikachu nicht); ohne
        # gefangene Weiterentwicklung nur, wenn es die Art sonst nicht wild gibt
        parents = {k for k in later(art) if k not in no_eggs} & set(rep)
        if breeding and not pre and parents and not f["legendaer"] and not f["mysterioes"]:
            got = sorted(parents & caught)
            if got or not mine:
                pf = rep[got[0] if got else min(parents)][1]
                ways.append({"art": "zucht", "text": f"Ei von {pf['name']}",
                             "hast": bool(got), "von": pf["id"], "von_name": pf["name"]})
        if other:
            eo = sorted({e for w in other for e in w["editionen"]})
            ways.append({"art": "edition", "text": f"nur in {', '.join(eo)}: tauschen", "ort": other[0]["ort"], "nur": eo})
        if fixed:
            ways.append({"art": "fest", "text": ", ".join(dict.fromkeys(w["ort"] + (f" (Lv {w['level']})" if w["level"] else "")
                                                                         for w in fixed))[:200], "ort": fixed[0]["ort"]})
        if not ways:
            ways.append({"art": "unklar", "text": "nur Verteilung oder Event" if f["mysterioes"] else
                         "kein Fundort in den Daten: Geschenk, Tausch oder aus einem anderen Spiel"})
        best = "jetzt" if any(w.get("hast") for w in ways) else min((w["art"] for w in ways), key=WAYS.index)
        werte, summe = form_stats(D, f, gen)      # 0.56.2: für die Standard-Karte und die Hover-Karte
        out.append({"art": art, "id": f["id"], "name": f["name"], "nr": nr if nr is not None else art, "dex": di[0], "dexk": di[1],
                    "typen": form_types(D, f, gen), "werte": werte, "summe": summe, "gen": f["gen"],
                    "legendaer": bool(f["legendaer"] or f["mysterioes"]), "weg": best, "wege": ways})
    out.sort(key=lambda x: (x["dex"] or 99, x["nr"] or 99999, x["id"]))
    return {"spiel": g["kennung"], "editionen": eds if len(eds) > 1 else [], "edition": edition, "arten": len(rep),
            "gefangen": len(set(rep) & caught), "fehlt": out}


def _missing_home(D):
    """Was fehlt in Pokémon HOME: jede Art ohne gefangene Form in HOME. Einziger Weg: in einem Spiel fangen und übertragen
    (welches Spiel, steht je Spiel unter „Was fehlt mir noch“)."""
    rep = vertreter(D, None)
    caught = {D.forms[i]["art"] for i in own_marks("gefangen", HOME) if i in D.forms}
    out = []
    for art, (_, f, nr, di) in sorted(rep.items()):
        if art in caught:
            continue
        werte, summe = form_stats(D, f, D.max_gen)
        out.append({"art": art, "id": f["id"], "name": f["name"], "nr": art, "dex": 0, "dexk": "",
                    "typen": form_types(D, f, D.max_gen), "werte": werte, "summe": summe, "gen": f["gen"],
                    "legendaer": bool(f["legendaer"] or f["mysterioes"]), "weg": "home",
                    "wege": [{"art": "home", "text": "in einem Spiel fangen und nach HOME übertragen"}]})
    return {"spiel": HOME, "editionen": [], "edition": "", "arten": len(rep), "gefangen": len(set(rep) & caught), "fehlt": out}


def _evolves_from():
    """{Art: Vorstufe} aus pokemon_species."""
    try:
        con = db.game()
    except Exception as err:
        fehler.melden(err)
        return {}
    try:
        return dict(con.execute("SELECT id, evolves_from_species_id FROM pokemon_species WHERE evolves_from_species_id IS NOT NULL"))
    except Exception as err:
        fehler.melden(err)
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
    except Exception as err:
        fehler.melden(err)
        return {}
    try:
        von = dict(con.execute("SELECT id, evolves_from_species_id FROM pokemon_species"))
    except Exception as err:
        fehler.melden(err)
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


TRAINER_ROLLEN = ("Arenaleiter", "Top Vier", "Champ", "Rivale", "Trainer")


def trainer_list(p):
    """Wichtige Trainer eines Spiels mit Team (PokéWiki): {"spiel", "rollen", "trainer": [{id, name, rolle, titel, hinweis,
    rueckkampf, level, team: [{id, name, lvl, item, faehigkeit, attacken}]}]}, nach Level (etwa die Reihenfolge im Spiel)."""
    D = data()
    if not D:
        return {"trainer": []}
    g, _, _ = game_of(D, p.get("spiel"))
    spiel = spiele.basis(g["kennung"]) if g else ""        # Erweiterungen und Schwester-Editionen zeigen die Trainer ihres Hauptspiels
    std = {}
    for f in D.forms.values():
        if f["standard"]:
            std.setdefault(f["art"], f)
    con = db.game()
    try:
        rows = con.execute("SELECT id, name, seite, rolle, titel, hinweis, rueckkampf, level, team FROM trainer WHERE spiel = ? "
                           "ORDER BY level, id", (spiel,)).fetchall()
    except Exception as err:
        fehler.melden(err)
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
        except Exception as err:
            fehler.melden(err)
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
        except Exception as err:
            fehler.melden(err)
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
            except Exception as err:
                fehler.melden(err)
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
    from .. import paste
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
    from .. import paste
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
