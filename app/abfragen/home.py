"""HOME-Boxen (0.75.0): die Sammlung in Pokémon HOME als Living Dex in Boxen zu 30, mit Lücken und freien Plätzen.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar. Grundlage sind die Marken in HOME (gefangen, schillernd),
wie in „Fortschritt“ und „Was fehlt mir noch“. Es gibt keine eigenen Boxen in user.db: Die Einteilung folgt der Nummer im
Nationaldex, so wie man eine Living Dex in HOME einsortiert; wo ein Pokémon hingehört, sagt sein Platz (Box, Reihe, Spalte).

- Arten: ein Platz je Art (die Standardform). Belegt ist er, sobald eine Form der Art in HOME gefangen ist.
- Formen: ein Platz je Form, die HOME lagert (keine Kampfform, nichts aus spiele.HOME_NICHT_LAGERBAR); die Formen einer Art
  folgen ihrer Standardform. Formen aus spiele.HOME_FRAGLICH stehen getrennt und zählen nicht.
- Shiny: belegt ist ein Platz erst mit der Marke „schillernd“ in HOME.

Für jeden leeren Platz nennt die Antwort die Spiele, in denen die Art (bei Formen: die Form) als gefangen markiert ist (mit
Shiny: als schillernd); von dort lässt sie sich übertragen. Größe der Boxen und Plätze im Plan: spiele.HOME_BOX, spiele.HOME_PLAETZE (Quellen in docs/formeln.md).
"""
import re

from .. import db, fehler, spiele

from .basis import HOME, data, form_types
from .fortschritt import vertreter

MODI = (("arten", "Arten"), ("formen", "mit Formen"))
_FRAGLICH = re.compile(spiele.HOME_FRAGLICH)


def lagerbar(f):
    """Lagert HOME diese Form als eigenen Platz? True, False oder None (nicht belegt: spiele.HOME_FRAGLICH)."""
    if not f["relevant"] or f["kampfform"] or f["mega"] or f["kennung"] in spiele.HOME_NICHT_LAGERBAR:
        return False
    if _FRAGLICH.search(f["kennung"] or ""):
        return None
    return True


def _marken(tabelle):
    """{Spiel: {Form}} einer Marke (gefangen oder schillernd) aus user.db, in einer Abfrage."""
    out = {}
    con = db.user()
    try:
        for spiel, form in con.execute(f"SELECT spiel, form FROM {tabelle}"):
            out.setdefault(spiel, set()).add(form)
    except Exception as err:
        fehler.melden(err)
    finally:
        con.close()
    return out


def einteilen(plaetze, groesse):
    """Plätze der Reihe nach in Boxen: [{nr, plaetze}] (die letzte Box kann kürzer sein)."""
    return [{"nr": i // groesse + 1, "plaetze": plaetze[i:i + groesse]} for i in range(0, len(plaetze), groesse)]


def home_boxen(p):
    """{spiel, modus, modi: [{id, name}], shiny, box, spalten, plaene: {basis, premium}, eintraege, belegt, fehlt, frei,
    boxen_noetig, boxen: [{nr, von, bis, belegt, fehlt, plaetze: [{id, art, name, typen, platz, reihe, spalte, hat, in}]}],
    fraglich: [{id, art, name, hat}], ausgenommen}. p: modus (arten, formen), shiny (1). frei: Plätze des Premium-Plans, die
    nach der vollen Living Dex bleiben. in: Namen der Spiele, in denen ein leerer Platz gefangen ist (mit shiny: schillernd)."""
    D = data()
    if not D:
        return None
    modus = p.get("modus") if p.get("modus") in dict(MODI) else "arten"
    shiny = str(p.get("shiny") or "") in ("1", "ja", "true")
    alle = _marken("schillernd" if shiny else "gefangen")
    marken = alle.get(HOME, set())
    arten_mit = {D.forms[i]["art"] for i in marken if i in D.forms}
    namen = {g["kennung"]: g["name"] for g in D.games}
    # je Art und je Form: in welchen Spielen gefangen (ohne HOME)
    je_art, je_form = {}, {}
    for kennung, ids in alle.items():
        if kennung == HOME or kennung not in namen:
            continue
        for i in ids:
            if i in D.forms:
                je_form.setdefault(i, []).append(kennung)
                je_art.setdefault(D.forms[i]["art"], []).append(kennung)
    reihe = {g["kennung"]: n for n, g in enumerate(reversed(D.games))}       # das neueste Spiel zuerst

    def spiele_von(ks):
        return [namen[k] for k in sorted(set(ks), key=lambda k: reihe.get(k, 999))]

    ausgenommen, fraglich, liste = 0, [], []
    if modus == "arten":
        rep = vertreter(D, None)
        for art in sorted(rep):
            f = rep[art][1]
            liste.append((f, art in arten_mit, je_art.get(art, [])))
    else:
        for f in sorted(D.forms.values(), key=lambda f: (f["art"], not f["standard"], f["id"])):
            ok = lagerbar(f)
            if ok is False:
                ausgenommen += bool(f["relevant"])
            elif ok is None:
                fraglich.append({"id": f["id"], "art": f["art"], "name": f["name"], "hat": f["id"] in marken})
            else:
                liste.append((f, f["id"] in marken, je_form.get(f["id"], [])))
    gen = D.max_gen
    plaetze = []
    for n, (f, hat, wo) in enumerate(liste):
        r = n % spiele.HOME_BOX
        plaetze.append({"id": f["id"], "art": f["art"], "name": f["name"], "typen": form_types(D, f, gen),
                        "platz": n + 1, "reihe": r // 6 + 1, "spalte": r % 6 + 1, "hat": hat,
                        "in": [] if hat else spiele_von(wo)})
    boxen = []
    for b in einteilen(plaetze, spiele.HOME_BOX):
        belegt = sum(x["hat"] for x in b["plaetze"])
        boxen.append({**b, "von": b["plaetze"][0]["art"], "bis": b["plaetze"][-1]["art"], "belegt": belegt,
                      "fehlt": len(b["plaetze"]) - belegt})
    belegt = sum(x["hat"] for x in plaetze)
    premium = spiele.HOME_PLAETZE["premium"]
    return {"spiel": HOME, "modus": modus, "modi": [{"id": k, "name": v} for k, v in MODI], "shiny": shiny,
            "box": spiele.HOME_BOX, "spalten": 6, "plaene": dict(spiele.HOME_PLAETZE), "eintraege": len(plaetze),
            "belegt": belegt, "fehlt": len(plaetze) - belegt, "frei": max(0, premium - len(plaetze)),
            "boxen_noetig": len(boxen), "boxen": boxen, "fraglich": fraglich, "ausgenommen": ausgenommen}
