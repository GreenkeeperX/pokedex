"""Tauschliste (0.71.0): was du im gewählten Spiel nur über einen Tauschpartner bekommst, und was du ihm bieten kannst.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar. Grundlage ist „Was fehlt mir noch“ (teams.missing):
dieselben Arten, dieselben Wege, dieselbe Edition.

- Nur in der anderen Edition: eine fehlende Art, die die andere Edition wild hat und die du in deiner weder fangen noch
  aus einer Art entwickeln oder züchten kannst, die es bei dir gibt (die Kette wird bis zu vier Stufen verfolgt; sonst
  stünde etwa ein Drache der anderen Edition nicht da, weil „Ei von“ seiner Endstufe als Weg gilt).
- Entwickelt sich durch Tausch: der Weg ist eine Tausch-Entwicklung (auch, wenn du die Vorstufe schon hast).
- Ohne Weg in den Daten: dort ist ein Tausch aus einem anderen Spiel oft der einzige Weg, aber nicht sicher; diese Gruppe
  steht nicht in der Liste zum Kopieren.
- Bieten: was es wild nur in deiner Edition gibt; was du davon schon gefangen hast, ist markiert. Nennen die Fundorte
  eines Spiels keine Editionen, lassen sich Exklusive nicht erkennen; die Antwort sagt das.
"""
from .basis import HOME, data, form_types, game_of
from .fortschritt import vertreter
from .karten import areas
from .teams import missing, own_marks

GRUPPEN = (("edition", "Nur in der anderen Edition"), ("tausch", "Entwickelt sich durch Tausch"),
           ("unklar", "Ohne Weg in den Daten (Tausch aus einem anderen Spiel?)"))
HIER = ("wild", "fest", "raid")          # Wege, die im eigenen Spiel und in der eigenen Edition liegen
AUS = ("entwicklung", "zucht", "tausch")  # Wege aus einer anderen Art (von)


def _eintrag(x, weg):
    return {"id": x["id"], "art": x["art"], "name": x["name"], "nr": x["nr"], "dexk": x["dexk"], "typen": x["typen"],
            "text": weg.get("text", "") if weg else "", "hast": bool(weg and weg.get("hast"))}


def _fundorte(D, g):
    """{Art: [Editionen je Fundort]} aus der Gebietsliste (leere Liste: der Fundort nennt keine Edition)."""
    je_art = {}
    for gb in (areas({"spiel": g["kennung"]}) or {}).get("gebiete", []):
        for m in gb["mons"]:
            f = D.forms.get(m["id"])
            if f:
                je_art.setdefault(f["art"], []).append(list(m["editionen"] or []))
    return je_art


def _erreichbar(D, fehlt, art, tiefe=0):
    """Gibt es die Art im eigenen Spiel und der eigenen Edition, direkt oder über eine Vorstufe oder ein Ei aus einer Art,
    die es dort gibt? Eine Art, die nicht fehlt, ist gefangen und damit da."""
    x = fehlt.get(art)
    if x is None:
        return True
    if tiefe > 4:
        return False
    for w in x["wege"]:
        if w["art"] in HIER or w.get("hast"):
            return True
        if w["art"] in AUS and w.get("von") in D.forms and D.forms[w["von"]]["art"] != art \
                and _erreichbar(D, fehlt, D.forms[w["von"]]["art"], tiefe + 1):
            return True
    return False


def tauschliste(p):
    """{spiel, name, editionen, edition, gruppen: [{id, titel, rows: [{id, art, name, nr, dexk, typen, text, hast}]}],
    biete: [rows], text, hinweis}. p: spiel, edition (wie in „Was fehlt mir noch“). text: die Liste zum Kopieren, ohne die
    Gruppe „unklar“. hinweis: warum eine Gruppe leer bleiben muss (keine Edition gewählt, Fundorte ohne Editionen)."""
    D = data()
    if not D:
        return None
    if p.get("spiel") == HOME:
        return {"spiel": HOME, "name": "Pokémon HOME", "editionen": [], "edition": "", "gruppen": [], "biete": [], "text": "",
                "hinweis": "In Pokémon HOME wird nicht getauscht: wähle das Spiel, in dem du tauschen willst."}
    d = missing(p)
    if d is None:
        return None
    g, gen, _ = game_of(D, d["spiel"])
    fehlt = {x["art"]: x for x in d["fehlt"]}
    gruppen = {gid: [] for gid, _ in GRUPPEN}
    for x in d["fehlt"]:
        weg = {w["art"]: w for w in reversed(x["wege"])}
        if "edition" in weg and not _erreichbar(D, fehlt, x["art"]):
            gruppen["edition"].append(_eintrag(x, weg["edition"]))
        if "tausch" in weg and x["weg"] in ("tausch", "jetzt"):
            gruppen["tausch"].append(_eintrag(x, weg["tausch"]))
        if x["weg"] == "unklar":
            gruppen["unklar"].append(_eintrag(x, weg["unklar"]))
    orte = _fundorte(D, g)
    mit_edition = any(e for eds in orte.values() for e in eds)
    biete = []
    if d["edition"] and mit_edition:
        gefangen = {D.forms[i]["art"] for i in own_marks("gefangen", g["kennung"]) if i in D.forms}
        rep = vertreter(D, g)
        nur = {a for a, eds in orte.items() if all(e and set(e) == {d["edition"]} for e in eds)}
        for art in sorted(nur & set(rep), key=lambda a: (rep[a][3][0] or 99, rep[a][2] or 99999, a)):
            _, f, nr, di = rep[art]
            biete.append({"id": f["id"], "art": art, "name": f["name"], "nr": nr if nr is not None else art, "dexk": di[1],
                          "typen": form_types(D, f, gen), "text": f"nur in {d['edition']}", "hast": art in gefangen})
    if not d["editionen"]:
        hinweis = ""
    elif not d["edition"]:
        hinweis = "Wähle deine Edition: dann stehen hier auch, was nur die andere Edition hat, und was du bieten kannst."
    elif not mit_edition:
        hinweis = ("Die Fundorte dieses Spiels nennen keine Editionen; was nur eine Edition hat, lässt sich hier nicht "
                   "erkennen. Es steht dann meist unter „Ohne Weg in den Daten“.")
    else:
        hinweis = ""
    andere = [e for e in d["editionen"] if e != d["edition"]]
    out = [{"id": gid, "titel": titel, "rows": gruppen[gid]} for gid, titel in GRUPPEN]
    return {"spiel": d["spiel"], "name": g["name"], "editionen": d["editionen"], "edition": d["edition"], "gruppen": out,
            "biete": biete, "text": _text(g["name"], d["edition"], andere, out, biete), "hinweis": hinweis}


def _nr(x):
    return f"#{x['dexk'] or ''}{x['nr']} {x['name']}"


def _text(name, edition, andere, gruppen, biete):
    """Die Liste als einfacher Text zum Kopieren (für einen Tauschpartner); ohne die Gruppe „unklar“."""
    zeilen = [f"Tauschliste {name}" + (f" ({edition})" if edition else "")]
    kopf = {"edition": f"Suche, nur in {' oder '.join(andere)}:", "tausch": "Suche, entwickelt sich durch Tausch:"}
    for gr in gruppen:
        if gr["rows"] and gr["id"] in kopf:
            zeilen += ["", kopf[gr["id"]]] + [f"- {_nr(x)}" for x in gr["rows"]]
    if biete:
        zeilen += ["", f"Biete, nur in {edition}:"] + [f"- {_nr(x)}" + ("" if x["hast"] else " (noch nicht gefangen)") for x in biete]
    if len(zeilen) == 1:
        zeilen += ["", "Nichts zu tauschen."]
    return "\n".join(zeilen)
