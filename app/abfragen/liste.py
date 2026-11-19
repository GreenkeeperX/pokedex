"""Pokémon-Liste: Typwirkung im Vergleich, Kandidaten, Suche mit Filtern.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar.
"""
from .. import db, fehler, typen

from .basis import data, form_types, game_of, profil, row
from .auftraege import research_open


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
    taken = typen.product(ch, target, own)
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
    except Exception as err:
        fehler.melden(err)
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
    if profil(g)["forschung"] and p.get("sort") == "forschung":      # 0.49: wo noch viele Forschungspunkte zu holen sind
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
