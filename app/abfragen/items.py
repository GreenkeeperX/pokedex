"""Typtabelle und Items.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar.
"""
import json
import os

from .. import db, fehler, importer

from .basis import data, game_of, profil


# ------------------------------------------------------------------ Typen und Teams

def type_chart(p):
    D = data()
    if not D:
        return {}
    g, gen, ch = game_of(D, p.get("spiel"))
    return {"gen": gen, "typen": [{"id": t, "name": D.tname(t)} for t in ch], "doppelt": list(ch.doppelt) if ch.doppelt else None,
            "tabelle": {str(a): {str(d): f for d, f in ch[a].items()} for a in ch}}


ITEMS_GENAU = 50            # ab so vielen Items mit Beschreibung im Spiel gilt dessen Liste als vollständig (item_list)


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
        except Exception as err:
            fehler.melden(err)
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
            except Exception as err:
                fehler.melden(err)
                recs, mats = {}, {}
        tms = {}
        # 0.60.0: Eine Erweiterung führt bei der PokéAPI nur ihre neuen Maschinen; die übrigen stehen beim Hauptspiel
        haupt = D.game_by.get(profil(g)["hauptspiel"]) if g else None
        if vg:
            try:
                for v in ([haupt["id"]] if haupt else []) + [vg]:          # die eigenen zuletzt: sie gelten, wo beide eine haben
                    for r in con.execute("SELECT m.item_id, a.name, a.typ, a.klasse, a.staerke, a.genauigkeit, a.ap, a.kurz FROM machines m "
                                         "JOIN attacke a ON a.id = m.move_id WHERE m.version_group_id = ?", (v,)):
                        tms[r[0]] = {"name": r[1], "typ": r[2], "klasse": r[3], "staerke": r[4], "genauigkeit": r[5], "ap": r[6], "kurz": r[7] or ""}
            except Exception as err:
                fehler.melden(err)
                tms = {}
    finally:
        con.close()
    have = set()
    for kind in ("itembild", "itemhq"):
        folder = os.path.join(db.data_dir(), kind)
        have |= {os.path.splitext(x)[0] for x in os.listdir(folder)} if os.path.isdir(folder) else set()
    exact = bool(vg) and sum(1 for r in rows if vg in json.loads(r["spiele"] or "[]")) >= ITEMS_GENAU
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
