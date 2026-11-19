"""Tera-Raids (Karmesin/Purpur) und Crypto-Pokémon.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar.
"""
import json
import sqlite3

from .. import db, typen

from .basis import data, form_types, game_of
from .liste import _int
from .lernen import move_view


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
