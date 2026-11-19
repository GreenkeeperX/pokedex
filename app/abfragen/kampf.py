"""Doppelkampf (Smogon), Werte, Effort Levels und Schadensrechner.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar.
"""
import sqlite3

from .. import attacken, db, importer, store, typen

from .basis import ability_of, data, form_stats, form_types, game_of, no_abilities, profil
from .liste import _int, _ints
from .lernen import learnset, move_view
from .teams import _paste_names, slot_details


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
    from .. import doppel
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
    from .. import effort
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


def stats_view(body):
    """Werte-Diagramm einer Form (Profilfeld werte: dv, ev oder av): body spiel, id, level, wesen (ID), ivs, evs, ziel (je
    sechs Zahlen; bis Generation 2 DVs und Stat Exp). Dazu die Wesen zur Auswahl (ab Generation 3)."""
    from .. import schaden
    D = data()
    f = D.forms.get(_int(body.get("id"))) if D else None
    if not f:
        raise ValueError("Pokémon nicht gefunden")
    g, gen, _ = game_of(D, body.get("spiel"))
    werte = profil(g)["werte"]
    if werte in ("el", "ohne"):             # eigene Formel (Effort Levels, effort.py) oder nicht gerechnet
        return {"rows": [], "hinweis": "In diesem Spiel rechnen die Werte anders."}
    P = _paste_names(D)
    wesen = _int(body.get("wesen"))
    level = min(100, max(1, _int(body.get("level")) or 50))
    six = lambda v: [_int(x) for x in v][:6] if isinstance(v, list) and len(v) == 6 else None
    out = schaden.stat_view(form_stats(D, f, gen)[0], level, gen, six(body.get("ivs")), six(body.get("evs")),
                            six(body.get("ziel")), P["nat_mod"].get(wesen) if wesen and gen >= 3 else None,
                            lgpe=werte == "av")
    out["wesen_liste"] = sorted(({"id": i, "name": n, "mod": P["nat_mod"].get(i)} for i, n in P["nat_de"].items()),
                                key=lambda x: x["name"]) if gen >= 3 else []
    out["wesen"] = wesen if gen >= 3 else None
    out["minzen"] = gen >= 8
    return out


def effort_team(body):
    """Effort Levels des ganzen Teams (Legenden: Arceus): je Mitglied Stufen (None = nicht eingetragen, gerechnet mit 0),
    Werte jetzt und am Ziel, fehlende Leistungs-Items; dazu die Summe für das Team."""
    from .. import effort
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
    from .. import doppel, schaden
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
    pr = profil(g)
    champ = not g or pr["kampf"]             # Kampfspiel (und ohne Spiel): Level 50 fest
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
    doubles = pr["kampf"]                    # Doppelkampf: Flächenattacken treffen schwächer
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
    from .. import effort
    art = "" if pr["schaden"] == "hauptreihe" else pr["schaden"]       # "la" oder "lgpe": eigene Werte-Formel
    a_base, EV_ALL = form_stats(D, f, gen)[0], schaden.EV_MAX
    six = lambda v, d: [max(0, _int(x) or 0) for x in v][:6] if isinstance(v, list) and len(v) == 6 else [d] * 6
    a_el, a_av = six(d.get("el"), 0), six(d.get("avs"), 0)
    if art:
        a_item = a_abil = ""
    if art == "la":                        # kein Tera, keine Flächenregel der Doppelkämpfe; Wetter rechnen wir dort nicht ein
        tera = d_tera = None
        spread, wetter = False, ""
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
                                  a_item if gen == 2 and a_item in schaden.TYPE_ITEMS_GEN2 else None, wetter, gen)
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
            if art == "la":                    # 0.57.0: eigene Schadensformel, Eigentyp ×1,25, Wirkung 2,5 und 0,4
                r = schaden.calc_la(level, mv["staerke"], mv["klasse"], mv["typ"], a_types, ch, v_types, a_stat, sv,
                                    crit=bool(body.get("krit")))
            else:
                r = schaden.calc(level, mv["staerke"], mv["klasse"], mv["typ"], a_base, a_types, form_stats(D, v, gen)[0], v_types, ch,
                                 a_tera=tera, d_tera=d_tera, a_ev=EV_ALL if art else a_ev, a_iv=a_iv, a_nat=nat, d_ev=inv, spread=spread,
                                 crit=bool(body.get("krit")), crit_mult=2.0 if gen <= 5 else 1.5, d_level=d_level, mods=m, d_mod=dm,
                                 d_stats=sv if art else None, a_stat=a_stat if art else None, d_mult=d_mult, gen=gen, d_ability=d_ab,
                                 tera_min=not mv.get("mehrfach") and (mv.get("prio") or 0) <= 0)
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
            "stab": (schaden.LA_STAB if mv["typ"] in a_types else 1.0) if art == "la" else schaden.stab_of(mv["typ"], a_types, tera, a_abil == "adaptability" and gen >= 4) if gen >= 4 else (1.5 if mv["typ"] in a_types else 1.0), "level": level, "level_vert": d_level, "flaeche": spread, "tera": tera, "wesen": nat, "ev": a_ev, "gen": gen,
            "krit": 1.5 if art == "la" else 2.0 if gen <= 5 else 1.5, "rows": rows, "wetter": wetter, "art": art,
            "el": a_el[ai] if art == "la" else None, "av": a_av[ai] if art == "lgpe" else None,
            "eingerechnet": [f"{label[kind](k)}: {txt}" for kind, k, txt in used]}


def _calc_steps(gen, art, mv, m, r, level, d_level, a_base, ai, a_iv, a_ev, a_el, a_av, nat, v, vb, inv, spread, crit, wetter, d_item):
    """Rechenweg einer Zeile für den Tooltip: woraus Angriff und Verteidigung bestehen, die Faktoren der Reihe nach."""
    from .. import schaden
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
    elif art == "la":                      # Legenden: Arceus: eigene Reihenfolge, keine Items, kein Wetter
        if crit:
            fx.append(["Volltreffer", 1.5])
        fx.append(["Zufall", "0,85–1"])
        if r["stab"] > 1:
            fx.append(["Eigentyp", r["stab"]])
        fx.append(["Wirkung", r["eff"]])
    else:
        wname = {"sonne": "Sonne", "regen": "Regen"}.get(wetter, wetter)
        eff_typ, d_wo = r.get("eff_typ", r["eff"]), r.get("d_wo")       # Fähigkeit des Ziels: an ihrer Stelle, nicht in der Wirkung
        if d_wo in ("at", "bp"):
            fx.append(["Fähigkeit des Ziels, " + ("am Angriffswert" if d_wo == "at" else "an der Stärke"), r["d_faktor"]])
        if mv["staerke"] != r["staerke"]:
            fx.append([f"Stärke {mv['staerke']} → {r['staerke']}", None])
        if spread:
            fx.append(["Fläche", 0.5 if gen == 3 else 0.75])
        if m.get("wetter", 1.0) != 1.0:
            fx.append([wname, m["wetter"]])
        if gen <= 4:                       # bis Generation 4 kommt das „+ 2“ erst hier, nach Fläche und Wetter
            fx.append(["+ 2", None])
        if crit:
            fx.append(["Volltreffer", 2.0 if gen <= 5 else 1.5])
        if gen == 3:                       # Generation 3: Eigentyp und Wirkung vor dem Zufall
            if r["stab"] > 1:
                fx.append(["Eigentyp", r["stab"]])
            fx.append(["Wirkung", eff_typ])
            fx.append(["Zufall", "0,85–1"])
        else:
            if gen == 4 and m.get("item") == "life-orb":
                fx.append(["Leben-Orb", 1.3])
            fx.append(["Zufall", "0,85–1"])
            if r["stab"] > 1:
                fx.append(["Eigentyp", r["stab"]])
            fx.append(["Wirkung", eff_typ])
            if gen == 4 and m.get("item") == "expert-belt":
                fx.append(["Expertengurt", 1.2])
            elif gen >= 5 and m.get("ende", 1.0) != 1.0:
                fx.append(["Item", round(m["ende"], 2)])
            if d_wo == "ende":
                fx.append(["Fähigkeit des Ziels", r["d_faktor"]])
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
