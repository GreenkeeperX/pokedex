"""Forschung, Aufträge und Missionen.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar.
"""
import json
import re

from .. import db, fehler

from .basis import LA, data, profil_von


def research_done(spiel=LA):
    """0.49: erreichte Stufen der Forschungsaufgaben aus user.db (Tabelle gefunden, Karte „forschung“, Objekt
    „Art|Nr|Stufe“): {(Art, Nr): höchste erreichte Stufe}."""
    con = db.user()
    try:
        rows = con.execute("SELECT objekt FROM gefunden WHERE spiel = ? AND karte = 'forschung'", (spiel,)).fetchall()
    except Exception as err:
        fehler.melden(err)
        rows = []
    finally:
        con.close()
    out = {}
    for (o,) in rows:
        try:
            art, nr, k = (int(x) for x in str(o).split("|"))
        except ValueError:
            continue
        out[(art, nr)] = max(out.get((art, nr), 0), k)
    return out


def _research(con, art, done=None):
    """Forschungsaufgaben in Legenden: Arceus (PokéWiki): [{nr, aufgabe, stufen, doppelt, erreicht}]."""
    try:
        rows = con.execute("SELECT nr, aufgabe, stufen, doppelt FROM forschung WHERE art = ? ORDER BY nr", (art,)).fetchall()
    except Exception as err:
        fehler.melden(err)
        return []
    done = research_done() if done is None else done
    out = []
    for nr, a, st, d in rows:
        stufen = [x for x in json.loads(st or "[]") if x not in ("0", "")]
        out.append({"nr": nr, "aufgabe": a, "stufen": stufen, "doppelt": bool(d), "erreicht": min(done.get((art, nr), 0), len(stufen))})
    return out


def research_open(con):
    """Offene Forschungspunkte je Art bis zum Forschungslevel 10 (100 Punkte): {Art: Punkte}. Jede Stufe 10 Punkte,
    doppelt zählende 20; was über 100 hinausgeht, zählt nicht."""
    done = research_done()
    got, open_ = {}, {}
    try:
        rows = con.execute("SELECT art, nr, stufen, doppelt FROM forschung").fetchall()
    except Exception as err:
        fehler.melden(err)
        return {}
    for art, nr, st, d in rows:
        n = len([x for x in json.loads(st or "[]") if x not in ("0", "")])
        k = min(done.get((art, nr), 0), n)
        w = 20 if d else 10
        got[art] = got.get(art, 0) + k * w
        open_[art] = open_.get(art, 0) + (n - k) * w
    return {a: max(0, min(o, 100 - got.get(a, 0))) for a, o in open_.items()}


def _requests(con, D, art=None, spiel=LA):
    """Aufträge (Nebenmissionen) eines Spiels (BisaFans), mit art nur die, in denen die Art vorkommt."""
    try:
        rows = con.execute("SELECT nr, name, beschreibung, aufgabe, ort, loesung, belohnung, arten FROM auftrag "
                           "WHERE spiel = ? ORDER BY nr", (spiel,)).fetchall()
    except Exception as err:
        fehler.melden(err)
        return []
    std = {}
    for f in D.forms.values():
        if f["standard"]:
            std.setdefault(f["art"], f)
    out = []
    for nr, name, besch, aufg, ort, loes, bel, arten in rows:
        arts = json.loads(arten or "[]")
        if art is not None and art not in arts:
            continue
        out.append({"nr": nr, "name": name, "beschreibung": besch, "aufgabe": aufg, "ort": ort, "loesung": loes,
                    "belohnung": bel, "pokemon": [{"id": std[a]["id"], "name": std[a]["name"]} for a in arts if a in std]})
    return out


def _missions(con, spiel=LA):
    try:
        return [{"nr": nr, "name": n, "kapitel": k, "text": t, "label": f"D{nr - 100}" if spiel == ZA and k == 2 else str(nr)}
                for nr, n, k, t in con.execute("SELECT nr, name, kapitel, text FROM mission WHERE spiel = ? ORDER BY nr", (spiel,))]
    except Exception as err:
        fehler.melden(err)
        return []


ZA = "legends-za"


def _auftragsspiel(pr):
    """Spiel, unter dem Aufträge und Missionen in der Datenbank liegen (Profilfeld auftraege); leer ohne Aufträge und bei
    den Blaubeer-Missionen (eigene Tabelle)."""
    return "" if pr["blaubeer"] else pr["auftraege"]


def _blaubeer(con):
    try:
        return [dict(r) for r in con.execute("SELECT nr, bereich, art, text, bp FROM blaubeer ORDER BY nr")]
    except Exception as err:
        fehler.melden(err)
        return []
QUEST_INFO = {
    LA: {"kapitel": ["Erste Schritte in einer fremden Welt", "Wächter und Könige in Hisui", "Abenteuer im Sumpfland",
                     "Gemeinsamkeit und Stärke", "Der Berg ruft!", "Eisige Abenteuer im Frostland", "Unerwartete Unterstützung",
                     "Legenden im Sinnoh-Tempel", "Die Suche nach Arceus"],
         "quelle": "Nebenmissionen von BisaFans, Hauptmissionen aus der Komplettlösung von BisaFans", "karte_bis": 94,
         "spaet": "Aus dem Update „Ein neuer Tag in Hisui“; die Karte von Map Genie kennt ihn nicht"},
    ZA: {"kapitel": ["Hauptmission", "Dimensions-Mission (Mega-Dimension)"],
         "quelle": "Nebenmissionen von BisaFans (auch Mega-Dimension), Haupt- und Dimensions-Missionen aus dem PokéWiki",
         "karte_bis": 0, "spaet": ""},
}


def quest_kind(title):
    """Kategorie von Map Genie → Schlüssel in gefunden: Aufträge (Request, Side Mission) und Hauptmissionen."""
    t = (title or "").lower()
    if "request" in t or "side mission" in t or "side quest" in t:
        return "auftrag"
    if "story mission" in t or "main mission" in t or "main quest" in t:
        return "mission"
    return None


QUEST_CATS = {"Request": "auftrag", "Story Mission": "mission"}     # Legenden: Arceus; andere über quest_kind
_QNR = re.compile(r"^\s*(?:#|(?:(?:side|main|story)\s+)?(?:mission|quest|request)\s*#?)?\s*(\d{1,3})\s*[:.\-–]", re.I)


def quest_nr(name):
    x = _QNR.match(name or "")
    return int(x.group(1)) if x else None


def quest_points(m):
    """Aufträge und Hauptmissionen auf der Karte von Map Genie: {"auftrag": {Nr: Ort-id}, "mission": {...}}. Die Namen
    beginnen mit der Nummer („#Nr: “, „Side Mission Nr: “); Map Genie zählt wie BisaFans."""
    out = {"auftrag": {}, "mission": {}}
    cats = {c["id"]: c["titel"] for g in (m or {}).get("gruppen") or [] for c in g["kategorien"]}
    for o in (m or {}).get("orte") or []:
        k = quest_kind(cats.get(o[1]))
        nr = quest_nr(o[4])
        if k and nr is not None:
            out[k].setdefault(nr, o[0])
    return out


def request_list(p):
    """Aufträge und Missionen eines Spiels mit Aufträgen (Profilfeld auftraege): {"spiel", "rows": [...], "missionen": [...],
    "kapitel", "quelle", "karte": {auftrag: {Nr: [Karte, Ort-id]}, mission: {...}}} (leer in anderen Spielen)."""
    D = data()
    pr = profil_von(D, p.get("spiel") or LA)
    if D and pr["blaubeer"]:
        con = db.game()
        try:
            return {"spiel": pr["auftraege"], "rows": [], "missionen": [], "blaubeer": _blaubeer(con),
                    "quelle": "Blaubeer-Missionen aus dem PokéWiki"}
        finally:
            con.close()
    spiel = _auftragsspiel(pr)
    if not D or not spiel:
        return {"rows": [], "missionen": []}
    from .. import abruf
    con = db.game()
    try:
        out = {"spiel": spiel, "rows": _requests(con, D, spiel=spiel), "missionen": _missions(con, spiel)}
    finally:
        con.close()
    out.update(QUEST_INFO.get(spiel, {}))
    karte = {"auftrag": {}, "mission": {}}
    for m in (abruf.mg_maps(spiel) or {}).get("karten", []):
        if m.get("quelle"):
            continue
        for k, v in quest_points(m).items():
            for nr, oid in v.items():
                karte[k].setdefault(nr, [m["slug"], oid])
    out["karte"] = karte
    return out


def _wiki_title(D, f):
    base = next((x for x in D.forms.values() if x["art"] == f["art"] and x["standard"]), f)
    return base["name"].replace(" ", "_")
