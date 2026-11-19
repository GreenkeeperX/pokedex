"""Fortschritt auf einen Blick: wie viele Arten je Spiel und in Pokémon HOME gefangen sind, für das gewählte Spiel nach
Generation und Typ (0.69.0).

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar. Gezählt wird je Art wie in „Was fehlt mir noch“
(teams.missing): eine gefangene Form reicht. Die Arten eines Spiels sind die seines Spiel-Dex (`in_game`), in HOME alle
Arten mit einer relevanten Form.
"""
from .. import db, fehler

from .basis import HOME, data, form_types, game_of


def vertreter(D, g):
    """Je Art des Spiels die Form, die der Dex des Spiels zeigt (niedrigste Nummer, sonst die Standardform):
    {Art: (Sortierschlüssel, Form, Nummer, (Dex, Dex-Kürzel))}. In HOME (g None) die Standardform jeder Art mit einer
    relevanten Form."""
    rep = {}
    if g is None:
        for f in D.forms.values():
            if f["relevant"] and not f["kampfform"]:
                k = (not f["standard"], f["id"])
                if f["art"] not in rep or k < rep[f["art"]][0]:
                    rep[f["art"]] = (k, f, f["art"], (0, ""))
        return rep
    for fid, nr in D.in_game.get(g["id"], {}).items():
        f = D.forms.get(fid)
        if not f:
            continue
        di = D.in_dex.get(g["id"], {}).get(fid, (0, ""))
        k = (di[0] or 99, nr or 99999, not f["standard"], fid)
        if f["art"] not in rep or k < rep[f["art"]][0]:
            rep[f["art"]] = (k, f, nr, di)
    return rep


def _gefangen_alle():
    """{Spiel: {Form}} aller als gefangen markierten Formen aus user.db, in einer Abfrage."""
    out = {}
    con = db.user()
    try:
        for spiel, form in con.execute("SELECT spiel, form FROM gefangen"):
            out.setdefault(spiel, set()).add(form)
    except Exception as err:
        fehler.melden(err)
    finally:
        con.close()
    return out


def fortschritt(p):
    """{spiele: [{kennung, name, gen, arten, gefangen}] (HOME zuerst, dann die Spiele wie in der Auswahl im Kopf, das
    neueste zuerst, ohne Spiele ohne Dex), spiel, name, arten, gefangen, generationen: [{gen, arten, gefangen}], typen: [{id, name, arten,
    gefangen}]}. Die Aufteilung gilt für p["spiel"] (HOME oder ein Spiel; sonst das neueste Spiel). Eine Art mit zwei
    Typen zählt bei beiden; Typen nach dem Stand der Generation des Spiels."""
    D = data()
    if not D:
        return None
    marken = _gefangen_alle()

    def zaehlen(g, kennung):
        rep = vertreter(D, g)
        arten = {D.forms[i]["art"] for i in marken.get(kennung, ()) if i in D.forms}
        return rep, set(rep) & arten

    spiele = []
    for g, kennung, name, gen in [(None, HOME, "Pokémon HOME", 0)] + [(g, g["kennung"], g["name"], g["gen"]) for g in reversed(D.games)]:
        rep, hat = zaehlen(g, kennung)
        if rep:
            spiele.append({"kennung": kennung, "name": name, "gen": gen, "arten": len(rep), "gefangen": len(hat)})
    wahl = p.get("spiel") or ""
    if wahl == HOME:
        g, gen, name = None, D.max_gen, "Pokémon HOME"
    else:
        g, gen, _ = game_of(D, wahl)
        g = g or (D.games[-1] if D.games else None)
        if g is None:
            return {"spiele": spiele, "spiel": "", "name": "", "arten": 0, "gefangen": 0, "generationen": [], "typen": []}
        wahl, gen, name = g["kennung"], g["gen"], g["name"]
    rep, hat = zaehlen(g, wahl)
    je_gen, je_typ = {}, {}
    for art, (_, f, _, _) in rep.items():
        drin = art in hat
        z = je_gen.setdefault(f["gen"], [0, 0])
        z[0] += 1
        z[1] += drin
        for t in form_types(D, f, gen):
            z = je_typ.setdefault(t, [0, 0])
            z[0] += 1
            z[1] += drin
    return {"spiele": spiele, "spiel": wahl, "name": name, "arten": len(rep), "gefangen": len(hat),
            "generationen": [{"gen": k, "arten": a, "gefangen": n} for k, (a, n) in sorted(je_gen.items())],
            "typen": [{"id": t, "name": D.types.get(t, str(t)), "arten": a, "gefangen": n} for t, (a, n) in sorted(je_typ.items())]}
