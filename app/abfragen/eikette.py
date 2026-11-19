"""Ei-Attacken-Kette (0.72.0): die kürzeste nachvollziehbare Elternkette, über die ein Pokémon eine Ei-Attacke bekommt.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar. Regeln nach Bulbapedia, „Egg Move“
(https://bulbapedia.bulbagarden.net/wiki/Egg_Move), Stand 19.11.2026; Einzelheiten in docs/formeln.md, „Ei-Attacken“:

- Beim Züchten erbt das Ei eine Ei-Attacke, wenn ein Elternteil sie kann; bis Generation 5 nur vom Vater, ab Generation 6
  von beiden. Die Art des Eis bestimmt die Mutter. Über Artgrenzen hinweg gibt deshalb immer ein männlicher Elternteil
  weiter, der eine Ei-Gruppe mit der Mutter teilt. Ditto gibt nichts weiter; wer nur mit Ditto züchten kann (geschlechtslos
  oder nur männlich), erbt keine Ei-Attacken.
- Karmesin und Purpur (Profil `eiattacken` = spiegelkraut): Im Picknick lernt ein Pokémon mit Spiegelkraut und freiem
  Platz eine Ei-Attacke von einem anderen der Gruppe, ohne Ei-Gruppe. Die Kette ist dann ein Schritt.

Gesucht wird in den Arten des Spiel-Dex (Breitensuche, höchstens fünf Schritte); bei gleicher Länge zuerst über gefangene
Pokémon, dann nach der Nummer im Dex.
"""
from collections import deque

from .. import db, fehler
from .basis import _names, data, game_of, profil
from .fortschritt import vertreter
from .lernen import how, learn_game
from .teams import NO_EGGS, own_marks

DITTO = 13                  # Ei-Gruppe „Ditto“
TIEFE = 5
ALTERNATIVEN = 8


def _arten(con):
    """{Art: (Geschlechterquote, Kette, Vorstufe)} und {Art: {Ei-Gruppen}} aus der Datenbank."""
    sp = {r[0]: (r[1], r[2], r[3]) for r in con.execute(
        "SELECT id, gender_rate, evolution_chain_id, evolves_from_species_id FROM pokemon_species")}
    gruppen = {}
    for art, gid in con.execute("SELECT species_id, egg_group_id FROM pokemon_egg_groups"):
        gruppen.setdefault(art, set()).add(gid)
    return sp, gruppen


def eikette(p):
    """{spiel, id, name, attacke: {id, name, typ}, modus, art, text, kette: [{id, art, name, wie, gruppe, gefangen}],
    alternativen: [{id, name, wie, gefangen}], quelle}. p: spiel, id (Form), attacke (ID).

    art: selbst (lernt die Attacke ohne Ei), kette (gefunden), keine_ei (keine Ei-Attacke der Art), besonders (ein besonderes
    Ei wie Volttackle-Pichu, Text aus der PokéAPI), ohne_zucht (im Spiel
    gibt es keine Zucht), nicht_vererbbar (nur Ditto als Partner: geschlechtslos oder nur männlich), keine_kette (in fünf
    Schritten keine Kette aus Arten des Spiels). kette beginnt beim Pokémon, das die Attacke selbst lernt, und endet beim
    gewählten; alternativen sind andere Anfänge derselben Länge."""
    D = data()
    if not D:
        return None
    try:
        fid, mid = int(p.get("id")), int(p.get("attacke"))
    except (TypeError, ValueError):
        raise ValueError("id und attacke: Zahlen")
    f = D.forms.get(fid)
    g, gen, _ = game_of(D, p.get("spiel"))
    if not f or not g:
        return None
    pr = profil(g)
    lg = learn_game(D, g)
    vg = lg["id"]
    rep = vertreter(D, g)
    gefangen = {D.forms[i]["art"] for i in own_marks("gefangen", g["kennung"]) if i in D.forms}
    con = db.game()
    try:
        m = con.execute("SELECT id, name, typ FROM attacke WHERE id = ?", (mid,)).fetchone()
        if not m:
            return None
        sp, gruppen = _arten(con)
        try:
            gname = _names(con, "egg_group_prose", "egg_group_id")
        except Exception as err:
            fehler.melden(err)
            gname = {}
        rows = con.execute("SELECT pokemon_id, pokemon_move_method_id, level, mastery FROM pokemon_moves "
                           "WHERE move_id = ? AND version_group_id = ?", (mid, vg)).fetchall()
        beschreibung = {k: " ".join(str(t or "").split()) for k, t in con.execute(
            "SELECT pokemon_move_method_id, description FROM pokemon_move_method_prose WHERE local_language_id = 6")}
    finally:
        con.close()
    selbst, ei, sonder = {}, set(), {}   # Art → Weg ohne Ei; Arten mit der Ei-Attacke; Art → Methode eines besonderen Eis
    for pid, meth, lv, mastery in rows:
        x = D.forms.get(pid)
        if not x:
            continue
        if D.method_key.get(meth, "") == "egg":
            ei.add(x["art"])
        elif D.method_key.get(meth, "").endswith("-egg"):      # Volttackle-Pichu: Ei mit Kugelblitz (PokéAPI)
            sonder[x["art"]] = meth
        else:
            selbst.setdefault(x["art"], how(D, meth, lv, mastery, mid, vg))
    kette_von = lambda a: sp.get(a, (0, a, None))[1]
    ei_ketten = {kette_von(a) for a in ei}
    art = f["art"]
    out = {"spiel": g["kennung"], "id": fid, "name": f["name"], "attacke": {"id": m["id"], "name": m["name"], "typ": m["typ"]},
           "modus": pr["eiattacken"], "kette": [], "alternativen": [],
           "quelle": ["Bulbapedia: Egg Move", "https://bulbapedia.bulbagarden.net/wiki/Egg_Move"]}

    def glied(a, wie, gruppe=""):
        x = rep[a][1] if a in rep else next((y for y in D.forms.values() if y["art"] == a and y["standard"]), f)
        return {"id": x["id"], "art": a, "name": x["name"], "wie": wie, "gruppe": gruppe, "gefangen": a in gefangen}

    def fertig(art_, text, **mehr):
        out.update(art=art_, text=text, **mehr)
        return out

    if art in selbst:
        return fertig("selbst", f"{f['name']} lernt {m['name']} selbst ({selbst[art]}); keine Zucht nötig.")
    if art in sonder and kette_von(art) not in ei_ketten:
        return fertig("besonders", f"{D.methods.get(sonder[art], '')}: {beschreibung.get(sonder[art]) or 'besonderes Ei'}".strip(": "))
    if kette_von(art) not in ei_ketten:
        return fertig("keine_ei", f"{m['name']} ist in {g['name']} keine Ei-Attacke von {f['name']}.")
    if not pr["zucht"]:
        return fertig("ohne_zucht", f"In {g['name']} gibt es keine Zucht.")
    im_spiel = set(rep)
    sortiert = lambda arten: sorted(arten, key=lambda a: (a not in gefangen, rep[a][3][0] or 99, rep[a][2] or 99999, a))
    if pr["eiattacken"] == "spiegelkraut":
        lehrer = sortiert(set(selbst) & im_spiel)
        if not lehrer:
            return fertig("keine_kette", f"Kein Pokémon im Dex von {g['name']} lernt {m['name']} selbst.")
        a = lehrer[0]
        return fertig("kette", f"Im Picknick: {f['name']} hält Spiegelkraut und hat einen freien Platz, {rep[a][1]['name']} "
                               f"kann {m['name']} ({selbst[a]}). Eine Ei-Gruppe brauchen sie nicht.",
                      kette=[glied(a, selbst[a]), glied(art, "Spiegelkraut")],
                      alternativen=[glied(b, selbst[b]) for b in lehrer[1:1 + ALTERNATIVEN]])
    familie = lambda k: [a for a, v in sp.items() if v[1] == k]

    def muetter(k):
        """Ei-Gruppen der Arten einer Familie, die Mutter sein können (es gibt Weibchen, sie züchten nicht nur mit Ditto)."""
        out_ = set()
        for a in familie(k):
            gs = gruppen.get(a, set())
            if 0 <= sp[a][0] <= 8 and sp[a][0] != 0 and gs and NO_EGGS not in gs and DITTO not in gs:
                out_ |= gs
        return out_

    vaeter = [a for a in im_spiel if 0 <= sp.get(a, (-1,))[0] <= 7 and gruppen.get(a) and NO_EGGS not in gruppen[a]
              and DITTO not in gruppen[a]]
    start = muetter(kette_von(art))
    if not start:
        return fertig("nicht_vererbbar", f"{f['name']} kann nur mit Ditto Eier legen (geschlechtslos oder nur männlich) und "
                                         f"erbt deshalb keine Ei-Attacken.")
    # Breitensuche von der Mutter rückwärts: Knoten = Familie, die die Attacke als Ei bekommt
    vorher = {kette_von(art): None}
    ebene = [(kette_von(art), start)]
    for _ in range(TIEFE):
        treffer, weiter = [], []
        for k, gs in ebene:
            for a in sortiert(vaeter):
                # eine Familie nur einmal, außer ein Vater der eigenen Familie lernt die Attacke selbst (Rankel für Keimling)
                if not gruppen[a] & gs or (kette_von(a) in vorher and not (a in selbst and kette_von(a) == k)):
                    continue
                gemeinsam = sorted(gruppen[a] & gs)[0]
                if a in selbst:
                    treffer.append((a, k, gemeinsam))
                elif kette_von(a) in ei_ketten and muetter(kette_von(a)):
                    weiter.append((a, k, gemeinsam))
        if treffer:
            a, k, gruppe = treffer[0]
            kette = [glied(a, selbst[a])]
            while True:         # vorher[k]: (Art der Familie k, die als Vater weitergibt, Familie ihres Eis, Ei-Gruppe)
                if vorher[k] is None:
                    kette.append(glied(art, "Ei", gname.get(gruppe, str(gruppe))))
                    break
                b, k_naechste, g_naechste = vorher[k]
                kette.append(glied(b, "Ei", gname.get(gruppe, str(gruppe))))
                k, gruppe = k_naechste, g_naechste
            return fertig("kette", _saetze(kette, m["name"]), kette=kette,
                          alternativen=[glied(b, selbst[b], gname.get(gg, str(gg))) for b, kk, gg in treffer[1:]
                                        if kk == treffer[0][1]][:ALTERNATIVEN])
        ebene = []
        for a, k, gemeinsam in weiter:
            ka = kette_von(a)
            if ka not in vorher:
                vorher[ka] = (a, k, gemeinsam)
                ebene.append((ka, muetter(ka)))
        if not ebene:
            break
    return fertig("keine_kette", f"In {TIEFE} Schritten keine Kette aus Pokémon im Dex von {g['name']}.")


def _saetze(kette, attacke):
    """Die Kette in Sätzen: wer die Attacke lernt, dann je Schritt Vater, Mutter und Ei-Gruppe."""
    s = [f"{kette[0]['name']} lernt {attacke} selbst ({kette[0]['wie']})."]
    for a, b in zip(kette, kette[1:]):
        s.append(f"{a['name']} (♂) mit {b['name']} (♀) züchten, Ei-Gruppe {b['gruppe']}: das Ei erbt {attacke}.")
    return " ".join(s)
