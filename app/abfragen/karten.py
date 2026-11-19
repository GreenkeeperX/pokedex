"""Fundorte und Karten: Bedingungen, Shiny-Sperren, Alphas, Karten von Map Genie und den anderen Quellen, Gebiete.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar.
"""
import json
import os
import re
import threading

from .. import altissimo, db, fehler, importer, mapgenie, spiele

from .basis import LA, _names, _stamp, data, game_of
from .auftraege import _auftragsspiel, _missions, _requests, quest_kind, quest_nr


def _range(xs):
    lo, hi = min(a for a, _ in xs), max(b for _, b in xs)
    return f"{lo}" if lo == hi else f"{lo}–{hi}"


ZEIT_DE = {"Dawn": "Morgen", "Day": "Tag", "Dusk": "Abend", "Night": "Nacht"}
WETTER_DE = {"None": "klar", "Sunny": "sonnig", "Cloudy": "bewölkt", "Rain": "Regen", "Snow": "Schnee", "Drought": "starke Sonne",
             "Fog": "Nebel", "Rainstorm": "Gewitter", "Snowstorm": "Schneesturm"}


def _pct(x):
    return f"{x:.0f} %" if x >= 10 else f"{x:.1f} %".replace(".", ",")


def _cond_text(d, order, names, all_label):
    """Anteile je Tageszeit oder Wetter als kurzer Text: „immer“, „Nacht 88 %“ oder „Regen 45 %, sonst 20 %“."""
    present = [k for k in order if d.get(k)]
    vals = sorted(d[k] for k in present)
    if not vals:
        return ""
    if len(present) == len(order) and vals[0] >= 0.8 * vals[-1]:
        return all_label
    if len(present) < len(order):
        return ", ".join(f"{names[k]} {_pct(d[k])}" for k in present)
    base = vals[len(vals) // 2]
    special = [k for k in present if abs(d[k] - base) > 0.2 * base]
    return ", ".join(f"{names[k]} {_pct(d[k])}" for k in special) + f", sonst {_pct(base)}"


_ALPHA = {}


def shiny_locks(spiel):
    """0.51: Shiny-Sperren des Spiels: {"tausch": [Form-Ids], "nie": [Form-Ids], "gen1": bool}. In Generation I gibt es keine
    schillernden Pokémon: dort gilt alles als „nur per Tausch“ (sichtbar erst in Gold, Silber, Kristall)."""
    out = {"tausch": [], "nie": [], "gen1": False}
    try:
        con = db.game()
    except Exception as err:
        fehler.melden(err)
        return out
    try:
        g = con.execute("SELECT gen FROM spiel WHERE kennung = ?", (str(spiel or ""),)).fetchone()
        out["gen1"] = bool(g and g[0] == 1)
        for form, stufe in con.execute("SELECT form, stufe FROM shinysperre WHERE spiel = ?", (str(spiel or ""),)):
            out.setdefault(stufe, []).append(form)
    except Exception as err:
        fehler.melden(err)
    finally:
        con.close()
    return out


def alpha_possible(spiel):
    """Formen, die es im Spiel als Alpha gibt (Fundorte aus den Spieldaten und Spawn-Tabellen); leer in Spielen ohne Alphas."""
    spiel = str(spiel or "")
    try:
        key = (spiel, os.path.getmtime(db.pokeapi_path()))
    except OSError:
        return []
    if key in _ALPHA:
        return _ALPHA[key]
    ids = set()
    try:
        con = db.game()
    except Exception as err:
        fehler.melden(err)
        return []
    try:
        for sql in ("SELECT DISTINCT form FROM fundort WHERE spiel = ? AND alpha > 0",
                    "SELECT DISTINCT form FROM spawn WHERE spiel = ? AND alpha = 1"):
            try:
                ids |= {r[0] for r in con.execute(sql, (spiel,))}
            except Exception as err:
                fehler.melden(err)
    finally:
        con.close()
    _ALPHA.clear()
    _ALPHA[key] = sorted(i for i in ids if i is not None)
    return _ALPHA[key]


def spawn_summary(con, spiel, pid):
    """Je Gebiet: höchster Anteil an Spawnpunkten je Tageszeit und je Wetter (Alpha nur, wenn es sonst nichts gibt),
    als Text, dazu Höchstwert und Zahl der Punkte."""
    try:
        rows = con.execute("SELECT gebiet, karte, name, alpha, anteile FROM spawn WHERE spiel = ? AND form = ?", (spiel, pid)).fetchall()
    except Exception as err:
        fehler.melden(err)
        return {}
    has_normal = {r["gebiet"] for r in rows if not r["alpha"]}
    out = {}
    for r in rows:
        if r["alpha"] and r["gebiet"] in has_normal:
            continue
        e = out.setdefault(r["gebiet"], {"z": {}, "w": {}, "max": 0, "punkte": set(), "karte": r["karte"]})
        e["punkte"].add(r["name"])
        for cell, pct in json.loads(r["anteile"]).items():
            zt, _, wt = cell.partition("/")
            e["z"][zt] = max(e["z"].get(zt, 0), pct)
            e["w"][wt] = max(e["w"].get(wt, 0), pct)
            e["max"] = max(e["max"], pct)
    return {k: {"zeit": _cond_text(e["z"], importer.ZEITEN, ZEIT_DE, "immer"),
                "wetter": _cond_text(e["w"], importer.WETTER, WETTER_DE, "jedes"),
                "max": e["max"], "punkte": len(e["punkte"]), "karte": e["karte"]} for k, e in out.items()}


def map_data(karte, p):
    """Karte eines Gebiets: Spawnpunkte (x, z in Spielkoordinaten) mit den Pokémon dort, Tageszeit und Anteil, dazu
    Kartensymbole und Sammelobjekte (objekte). Jubeldorf hat nur Objekte und ein eigenes Kartenbild (bild).
    p: spiel (bisher nur legends-arceus)."""
    D = data()
    if not D:
        return None
    spiel = "legends-arceus"
    con = db.game()
    try:
        try:
            pts = con.execute("SELECT nr, name, x, z, alpha, gebiet FROM spawnpunkt WHERE spiel = ? AND karte = ?", (spiel, karte)).fetchall()
            rows = con.execute("SELECT name, form, alpha, anteile FROM spawn WHERE spiel = ? AND karte = ?", (spiel, karte)).fetchall()
            maps = [dict(r) for r in con.execute("SELECT karte, gebiet, COUNT(*) n FROM spawnpunkt WHERE spiel = ? GROUP BY karte "
                                                  "ORDER BY MIN(rowid)", (spiel,))]
        except Exception as err:
            fehler.melden(err)
            return None
        try:
            objs = con.execute("SELECT art, nr, x, z, menge, items, gebiet FROM kartenobjekt WHERE spiel = ? AND karte = ?",
                               (spiel, karte)).fetchall()
            if con.execute("SELECT 1 FROM kartenobjekt WHERE spiel = ? AND karte = ? LIMIT 1", (spiel, altissimo.VILLAGE)).fetchone():
                maps.insert(0, {"karte": altissimo.VILLAGE, "gebiet": altissimo.VILLAGE_NAME, "n": 0})
        except Exception as err:
            fehler.melden(err)
            objs = []
    finally:
        con.close()
    if not pts and not objs:
        return None
    mons = {}
    for r in rows:
        f = D.forms.get(r["form"])
        cells = json.loads(r["anteile"])
        z, w = {}, {}
        for cell, pct in cells.items():
            zt, _, wt = cell.partition("/")
            z[zt] = max(z.get(zt, 0), pct)
            w[wt] = max(w.get(wt, 0), pct)
        mons.setdefault(r["name"], []).append({
            "id": r["form"], "name": f["name"] if f else str(r["form"]), "alpha": bool(r["alpha"]), "max": max(cells.values()),
            "zeit": _cond_text(z, importer.ZEITEN, ZEIT_DE, "immer"), "wetter": _cond_text(w, importer.WETTER, WETTER_DE, "jedes"),
            # Anteil je Tageszeit und Wetter (Tageszeit × 9 + Wetter), für die Filter auf der Karte
            "c": [round(cells.get(f"{zt}/{wt}", 0), 1) for zt in importer.ZEITEN for wt in importer.WETTER]})
    for v in mons.values():
        v.sort(key=lambda m: (m["alpha"], -m["max"]))
    folder = os.path.join(db.data_dir(), "karten", karte)
    files = os.listdir(folder) if os.path.isdir(folder) else []
    return {"karte": karte, "gebiet": (pts or objs)[0]["gebiet"], "karten": maps,
            "kacheln": len([f for f in files if f != "bild.png"]), "bild": "bild.png" in files,
            "punkte": [{"nr": r["nr"], "x": r["x"], "z": r["z"], "alpha": bool(r["alpha"]), "mons": mons.get(r["name"], [])}
                       for r in pts],
            "objekte": [{"art": r["art"], "nr": r["nr"], "x": r["x"], "z": r["z"], "menge": r["menge"], "items": json.loads(r["items"] or "[]")}
                        for r in objs],
            "arten": {k: v for k, v in importer.KARTE_ARTEN.items() if any(r["art"] == k for r in objs)},
            "zeiten": [ZEIT_DE[k] for k in importer.ZEITEN], "wetterarten": [WETTER_DE[k] for k in importer.WETTER]}


_OVERLAY = {}


def mg_overlay(m, stamp=None):
    """Spawnpunkte und Kartensymbole von Legenden: Arceus auf der Karte von Map Genie m (ganz Hisui): je Gebiet an
    Geisterlichtern und Icognito ausgerichtet (mapgenie.align). {gebiete: {Karte: Name}, punkte: [{k, la, lo, alpha, mons}],
    objekte: [{k, la, lo, art, nr, menge, items}], arten}; Gebiete ohne Ausrichtung fehlen."""
    key = (m.get("id"), stamp, _stamp())
    if key in _OVERLAY:
        return _OVERLAY[key]
    mg = [p for ps in mapgenie.anchors(m).values() for p in ps]
    con = db.game()
    try:
        try:
            karten = [r[0] for r in con.execute("SELECT DISTINCT karte FROM kartenobjekt WHERE spiel = ? AND art IN ('irrlicht', 'icognito')",
                                                ("legends-arceus",))]
        except Exception as err:
            fehler.melden(err)
            karten = []
    finally:
        con.close()
    out = {"gebiete": {}, "punkte": [], "objekte": [], "arten": {}}
    for k in karten:
        d = map_data(k, {})
        if not d:
            continue
        game = [(o["x"], o["z"]) for o in d["objekte"] if o["art"] in ("irrlicht", "icognito")]
        f = mapgenie.align(game, mg)
        if not f:
            continue
        ax, bx, az, bz = f
        ll = lambda x, z: [round(v, 6) for v in mapgenie.unproject(ax * x + bx, az * z + bz)]
        out["gebiete"][k] = d["gebiet"]
        out["arten"].update(d["arten"])
        for p in d["punkte"]:
            la, lo = ll(p["x"], p["z"])
            out["punkte"].append({"k": k, "la": la, "lo": lo, "alpha": p["alpha"],
                                  "mons": [{kk: v for kk, v in mon.items() if kk != "c"} for mon in p["mons"]]})
        for o in d["objekte"]:
            la, lo = ll(o["x"], o["z"])
            out["objekte"].append({"k": k, "la": la, "lo": lo, "art": o["art"], "nr": o["nr"], "menge": o["menge"], "items": o["items"],
                                   "x": o["x"], "z": o["z"]})
    _OVERLAY.clear()
    _OVERLAY[key] = out
    return out


_MERGED = {}
MERGED_MAX = 12             # so viele zusammengeführte Karten hält der Server bereit (Wechsel zwischen Karten ohne Wartezeit)


def mg_names():
    """Englische Namen → deutsche, für die Kategorien von Map Genie: Items (Spieldaten) und Pokémon-Arten."""
    key = _stamp()
    if _MERGED.get("names", (None,))[0] == key:
        return _MERGED["names"][1]
    out = {}
    con = db.game()
    try:
        for q in ("SELECT en, name FROM item WHERE en IS NOT NULL AND name IS NOT NULL",
                  "SELECT a.name, b.name FROM pokemon_species_names a JOIN pokemon_species_names b ON b.pokemon_species_id = "
                  "a.pokemon_species_id AND b.local_language_id = 6 WHERE a.local_language_id = 9"):
            try:
                out.update({e: g for e, g in con.execute(q) if e and g})
            except Exception as err:
                fehler.melden(err)
    finally:
        con.close()
    _MERGED["names"] = (key, out)
    return out


def names_rx(names, tail=False):
    """Regulärer Ausdruck für ganze Namen (längste zuerst); tail: dazu, was dahinter steht ((Level, Form), *[Bedingung]*)."""
    if not names:
        return None
    t = r"((?:\s*\([^)]{1,30}\)|\s*[*_]\[?[^\]*_\n]{1,30}\]?[*_])*)" if tail else ""
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![\w-])" + t)


def _pic_names():
    """{deutscher Name: Art-Nr.} und {deutscher Itemname: Item-Nr.} für Bilder in den Kartendetails."""
    key = _stamp()
    if _MERGED.get("pics", (None,))[0] == key:
        return _MERGED["pics"][1]
    mons, items = {}, {}
    con = db.game()
    try:
        try:
            mons = {n: i for i, n in con.execute("SELECT pokemon_species_id, name FROM pokemon_species_names WHERE local_language_id = 6") if n}
        except Exception as err:
            fehler.melden(err)
        try:
            items = {n: i for i, n in con.execute("SELECT id, name FROM item WHERE name IS NOT NULL") if n and len(n) >= 4}
        except Exception as err:
            fehler.melden(err)
    finally:
        con.close()
    out = (mons, names_rx(mons, True), items, names_rx(items))
    _MERGED["pics"] = (key, out)
    return out


PIC_VALS = {"Night only": "nur nachts", "Day only": "nur tagsüber", "Shake trees": "Bäume schütteln", "Plant Cloak": "Pflanzenumhang",
            "Sandy Cloak": "Sandumhang", "Trash Cloak": "Lumpenumhang", "Rare": "selten", "Common": "häufig", "Very Rare": "sehr selten",
            "Uncommon": "gelegentlich", "Walking": "zu Fuß", "Surfing": "Surfen", "Fishing": "Angeln", "Day": "tagsüber", "Night": "nachts"}


def point_pics(text, names, mons, mrx, items, irx):
    """Pokémon und Items in einem Text eines Kartenpunkts: ([[Nr, Name, Fangart, Zusatz]], [[Item-Nr, Name]], Rest des
    Texts). Fangart ist die Überschrift bzw. Bezeichnung vor dem Doppelpunkt (auch Tageszeit), Zusatz was in Klammern
    folgt (Level, Anteil). Zeilen, die nur Pokémon aufzählen, fallen aus dem Rest (sie stehen dann als Bilder da)."""
    pk, it, rest, head = [], [], [], ""
    seen = set()
    for raw in (text or "").split("\n"):
        ln = raw.strip()
        h = re.fullmatch(r"\*\*(.+?):?\*\*:?", ln)
        if h:
            head = h.group(1).strip()
            rest.append(raw)
            continue
        body, lab = re.sub(r"^[-*]\s+", "", ln), head
        m = re.match(r"^\*\*([^*]{1,40}?):?\*\*:?\s*(.*)$", body) or re.match(r"^([^:*«»\[\]]{2,30}):\s+(.*)$", body)
        if m:
            lab, body = m.group(1).strip(), m.group(2)
        found, left = [], body
        if mrx and body:
            # Name, dahinter vielleicht (Level, Form) und *[Bedingung]*; nur Zeilen, die allein Pokémon aufzählen, zählen
            left = mrx.sub(lambda x: found.append((x.group(1), x.group(2))) or "", body)
        if found and not re.sub(r"[\s,;/()\d–\-%.·Lvl]+", "", left):
            for n, tail in found:
                extra = " · ".join(PIC_VALS.get(v.strip(), v.strip()) for v in re.findall(r"\(([^)]+)\)|[*_]\[?([^\]*_]+)\]?[*_]", tail) for v in v if v)
                k = (mons[n], lab, extra)
                if k not in seen:
                    seen.add(k)
                    pk.append([mons[n], n, PIC_VALS.get(lab, lab), extra])
            continue                              # nur Pokémon (mit Level): die Bilder zeigen es
        for x in (irx.finditer(body) if irx and body else ()):
            if x.group(1) not in mons and items[x.group(1)] not in {i[0] for i in it}:
                it.append([items[x.group(1)], x.group(1)])
        rest.append(raw)
    while rest and re.fullmatch(r"\*\*.+\*\*:?|\s*", rest[-1].strip()):
        rest.pop()                                 # Überschriften ohne Inhalt am Ende
    out, hd = [], re.compile(r"\*\*[^*]+\*\*:?")
    for i, ln in enumerate(rest):                  # Überschrift ohne eigenen Inhalt (danach nur eine weitere) auch weg
        if hd.fullmatch(ln.strip()):
            nxt = next((x.strip() for x in rest[i + 1:] if x.strip()), "")
            if not nxt or hd.fullmatch(nxt) or re.match(r"\*\*[^*]+\*\*:?\s*\S", nxt):
                continue
        out.append(ln)
    return pk, it, "\n".join(out).strip()


def _point_pics(r):
    """Kartenpunkte: Pokémon und Items aus dem Text als Bilder (pk, it); was der Text sonst sagt, bleibt."""
    mons, mrx, items, irx = _pic_names()
    if not (mrx or irx):
        return
    for p in r["punkte"]:
        if p.get("sp"):
            continue
        names = " ".join([p.get("name") or ""] + [i[0] for i in (p.get("o") or {}).get("items") or []])
        pk, it, rest = point_pics(p.get("text") or "", names, mons, mrx, items, irx)
        if irx:                                    # der Punkt selbst ist ein Item (Name) oder hat Items aus den Spieldaten
            for x in irx.finditer(names):
                if x.group(1) not in mons and items[x.group(1)] not in {i[0] for i in it}:
                    it.append([items[x.group(1)], x.group(1)])
        if pk:
            p["pk"] = pk
            p["text"] = rest
        if it:
            p["it"] = it[:24]


def _quests_de(r, spiel=LA):
    """Aufträge und Hauptmissionen auf der Karte: deutscher Name und Text von BisaFans vor dem englischen von Map Genie;
    „aq“ nennt den Schlüssel, unter dem der Haken liegt (wie im Reiter Aufträge)."""
    spiel = _auftragsspiel(spiele.profil(spiel)) or spiel
    cats = {c["id"]: quest_kind(c["en"]) for g in r["gruppen"] for c in g["kategorien"]}
    con = db.game()
    try:
        D = data()
        de = {"auftrag": {x["nr"]: x for x in (_requests(con, D, spiel=spiel) if D else [])},
              "mission": {x["nr"]: x for x in _missions(con, spiel)}}
    finally:
        con.close()
    for p in r["punkte"]:
        k = cats.get(p["c"])
        nr = quest_nr(p.get("en") or p["name"]) if k else None
        if nr is None:
            continue
        p["aq"] = f"{k}|{nr}"
        g = de[k].get(nr)
        if not g:
            continue
        p.setdefault("en", p["name"])
        p["name"] = f"#{nr}: {g['name']}"
        parts = ([g.get("beschreibung"), "**Aufgabe:** " + g["aufgabe"] if g.get("aufgabe") else "", "**Lösung:** " + g["loesung"] if g.get("loesung") else "",
                  "**Belohnung:** " + g["belohnung"] if g.get("belohnung") else ""] if k == "auftrag" else [g.get("text")])
        de_text = "\n\n".join(x for x in parts if x)
        if de_text:
            p["text"] = de_text + ("\n\n---\n\n**Map Genie (englisch):**\n\n" + p["text"] if p.get("text") else "")
            p["q"] = p.get("q", []) + ["BisaFans"]


def _pokearth_mons(r, spiel):
    """Regionskarten von Serebii: je Ort die Pokémon aus den Fundorten des Spiels (Spieldaten oder PokéAPI), deutscher
    Ortsname. Serebii nennt die Orte englisch; die PokéAPI kennt beide Namen."""
    a = areas({"spiel": spiel}) or {}
    if not a.get("gebiete"):
        return
    con = db.game()
    try:
        en, de = {}, {}
        for k, lang, n in con.execute("SELECT location_id, local_language_id, name FROM location_names WHERE local_language_id IN (6, 9)"):
            (de if lang == 6 else en).setdefault(k, n)
    except Exception as err:
        fehler.melden(err)
        return
    finally:
        con.close()
    low = lambda t: t.lower().replace("’", "'")      # 0.56: PokéWiki schreibt „Lili’i“, die PokéAPI „Lili'i“
    en2de = {}
    for k, n in en.items():
        if n:
            en2de.setdefault(low(n), de.get(k) or n)
    for n in de.values():                  # 0.48: Karten aus dem PokéWiki nennen die Orte schon deutsch
        if n:                              # 0.49: Arten ohne deutschen Namen (None) warfen AttributeError
            en2de.setdefault(low(n), n)
    for p in r["punkte"]:
        if p.get("text"):              # „Ort: Cherrygrove“ (Trainer, Items) → deutscher Ortsname
            p["text"] = re.sub(r"(\*\*Ort:\*\* )([^\n(]+?)(?=\s*\(|\n|$)", lambda x: x.group(1) + (
                en2de.get(x.group(2).lower()) or en2de.get(re.sub(r"\s+(City|Town)$", "", x.group(2)).lower()) or x.group(2)), p["text"])
        name = p.get("en") or p["name"]
        d = en2de.get(low(name)) or en2de.get(low(re.sub(r"\s+(City|Town)$", "", name)))
        if not d:
            continue
        if d != p["name"]:
            p.setdefault("en", p["name"])
            p["name"] = d
        dl = low(d)
        gs = [g for g in a["gebiete"] if low(g["ort"]) == dl or low(g["ort"]).startswith(dl + " (")]
        if not gs:
            continue
        lines = []
        for g in gs:
            by = {}
            for x in g["mons"]:
                by.setdefault(x["methode"] or "Pokémon", []).append(f"{x['name']} ({x['level']})" if x.get("level") else x["name"])
            head = f"**{g['ort']}**" if len(gs) > 1 else ""
            lines += ([head] if head else []) + [f"- **{k}:** " + ", ".join(dict.fromkeys(v)) for k, v in by.items()]
        p["text"] = "\n".join(lines)
        p["q"] = list(dict.fromkeys(p.get("q", []) + [a.get("quelle") or "PokéAPI"]))


def mg_map(m, spiel, stamp=None):
    """Eine Karte von Map Genie als eine Datenbank mit den eigenen Daten (mapgenie.merge): deutsche Ebenen, gleiche
    Stellen verschmolzen. Für Legenden: Arceus kommen Spawnpunkte und Symbole aus den Spieldaten dazu."""
    key = (spiel, m.get("id"), m.get("slug"), stamp, _stamp())
    hit = _MERGED.setdefault("maps", {})
    if key in hit:
        return hit[key]
    with _MERGE_LOCK:              # 0.52: Vorbereiten im Hintergrund und erste Anfrage rechnen nicht doppelt
        if key in hit:
            return hit[key]
        return _mg_map(m, spiel, stamp, key, hit)


_MERGE_LOCK = threading.Lock()


def _mg_map(m, spiel, stamp, key, hit):
    own = mg_overlay(m, stamp) if spiele.profil(spiel)["spawnkarten"] else None      # eigene Spawnpunkte (Legenden: Arceus)
    r = mapgenie.merge(m, own, mg_names())
    if _auftragsspiel(spiele.profil(spiel)):
        _quests_de(r, spiel)
    if m.get("quelle") in ("pokearth", "ironmon", "raidnester"):       # Orte mit englischem Namen: Pokémon aus den Fundorten
        _pokearth_mons(r, spiel)
    _point_pics(r)
    out = {k: v for k, v in m.items() if k not in ("orte", "gruppen")}
    out.update(r, spiel=spiel, am=stamp, bounds=mapgenie.bounds_of(m))
    while len(hit) >= MERGED_MAX:            # die ältesten zuerst weg
        hit.pop(next(iter(hit)))
    hit[key] = out
    return out


def _enc_pkhex(con, g, pid):
    """Fundorte aus den Spieldaten (PKHeX): je Gebiet und Art die Stellen, Level und Alpha-Level. None ohne Daten."""
    try:
        rows = con.execute("SELECT gebiet, gebiet_nr, stellen, art, min, max, alpha FROM fundort WHERE spiel = ? AND form = ?",
                           (g["kennung"], pid)).fetchall()
        if not rows and not con.execute("SELECT 1 FROM fundort WHERE spiel = ? LIMIT 1", (g["kennung"],)).fetchone():
            return None
    except Exception as err:
        fehler.melden(err)
        return None
    groups = {}
    for r in rows:
        e = groups.setdefault((r["gebiet_nr"], r["art"]), {"gebiet": r["gebiet"], "stellen": {}, "lv": [], "alpha": [], "immer": False})
        lv = (r["min"], r["max"])
        (e["alpha"] if r["alpha"] else e["lv"]).append(lv)
        e["immer"] = e["immer"] or r["alpha"] == 2
        for x in (json.loads(r["stellen"] or "[]") or [""]) if r["art"] != importer.FEST else []:
            st = e["stellen"].setdefault(x, {"lv": [], "alpha": []})
            (st["alpha"] if r["alpha"] else st["lv"]).append(lv)
    spawn = spawn_summary(con, g["kennung"], pid)
    out = []
    for (nr, art), e in sorted(groups.items()):
        sp = spawn.get(e["gebiet"]) if art == 0 else None
        places = [{"name": k, "level": _range(v["lv"]) if v["lv"] else "", "alpha": _range(v["alpha"]) if v["alpha"] else ""}
                  for k, v in e["stellen"].items()]
        places.sort(key=lambda x: (int((x["level"] or x["alpha"]).split("–")[0] or 0), x["name"]))
        out.append({"ort": e["gebiet"], "stellen": places, "methode": importer.PKHEX_ART.get(art, str(art)),
                    "level": _range(e["lv"]) if e["lv"] else "", "alpha": _range(e["alpha"]) if e["alpha"] else "",
                    "nur_alpha": not e["lv"] and bool(e["alpha"]), "bedingungen": [], "editionen": [],
                    "zeit": sp["zeit"] if sp else "", "wetter": sp["wetter"] if sp else "",
                    "chance": sp["max"] if sp else 0, "punkte": sp["punkte"] if sp else 0, "karte": sp["karte"] if sp else ""})
    return out


def _enc(con, g, pid):
    """Fundorte im Spiel: Ort, Methode, Level, Bedingungen. Aus den Spieldaten (PKHeX), wo es sie gibt."""
    if not g:
        return []
    own = _enc_pkhex(con, g, pid)
    if own is not None:
        return own
    try:
        rows = con.execute(
            """SELECT e.location_area_id la, l.id loc, es.encounter_method_id meth, MIN(e.min_level) lo, MAX(e.max_level) hi,
                      GROUP_CONCAT(DISTINCT v.id) vers, GROUP_CONCAT(DISTINCT m.encounter_condition_value_id) cond
               FROM encounters e JOIN versions v ON v.id = e.version_id JOIN location_areas la ON la.id = e.location_area_id
               JOIN locations l ON l.id = la.location_id JOIN encounter_slots es ON es.id = e.encounter_slot_id
               LEFT JOIN encounter_condition_value_map m ON m.encounter_id = e.id
               WHERE e.pokemon_id = ? AND v.version_group_id = ?
               GROUP BY e.location_area_id, es.encounter_method_id ORDER BY l.id""", (pid, g["id"])).fetchall()
    except Exception as err:
        fehler.melden(err)
        return []
    if not rows:
        return []
    locs = _names(con, "location_names", "location_id")
    areas = _names(con, "location_area_prose", "location_area_id")
    meths = _methods(con)
    conds = _names(con, "encounter_condition_value_prose", "encounter_condition_value_id")
    vn = _names(con, "version_names", "version_id")
    nv = con.execute("SELECT COUNT(*) FROM versions WHERE version_group_id = ?", (g["id"],)).fetchone()[0]
    out = []
    for r in rows:
        area = areas.get(r["la"]) or ""
        place = locs.get(r["loc"]) or ""
        vs = [int(v) for v in str(r["vers"] or "").split(",") if v]
        out.append({"ort": _place(place, area),
                    "methode": meths.get(r["meth"], ""), "level": f"{r['lo']}" if r["lo"] == r["hi"] else f"{r['lo']}–{r['hi']}",
                    "bedingungen": [conds[int(c)] for c in str(r["cond"] or "").split(",") if c and int(c) in conds],
                    "editionen": [vn.get(v, "") for v in vs] if len(vs) < nv else []})
    return out


_AREAS = {}                 # {(Spiel, Stand der Datenbank): Gebiete}, je Spiel getrennt (seit 0.58.0; vorher nur das letzte Spiel)
AREAS_MAX = 6               # so viele Spiele bleiben bereit; das am längsten nicht gefragte fällt zuerst weg


# 0.54: Begegnungsarten der PokéAPI, die es nur englisch gibt (ab Nr. 18), auf Deutsch
METHOD_DE = {18: "Geschenk", 19: "Ei als Geschenk", 20: "feste Begegnung", 21: "Pokéflöte spielen",
             22: "Kopfnuss (Baum, selten)", 23: "Kopfnuss (Baum)", 24: "Kopfnuss (Baum, häufig)", 25: "Schiggykanne an Mogelbaum",
             26: "Wailmerkanne an Mogelbaum", 27: "Tauchen im Seetang", 28: "frei im Gras", 29: "frei auf dem Wasser",
             30: "Devon-Scope", 31: "Angeln an Barschwa-Stellen", 32: "Inselscan", 33: "Notruf (SOS)", 34: "Angeln an sprudelnden Stellen",
             35: "Beerenbaum", 36: "Tausch mit einer Person im Spiel", 37: "Notruf an sprudelnden Stellen", 38: "frei laufend",
             39: "frei beim Surfen", 40: "fliegend am Himmel", 41: "selten im Gras (Lockparfüm oder Fangserie)",
             42: "selten am Himmel (Lockparfüm oder Fangserie)", 43: "selten im Wasser (Lockparfüm oder Fangserie)",
             44: "Fünfer-Begegnung", 45: "Bonus-Disc (USA, Jirachi)", 46: "Bonus-Disc (Japan)", 47: "Pokémon Channel (Jirachi)",
             48: "Pokémon Ranger (Manaphy)", 49: "Pokémon Battle Revolution", 50: "Ei aus dem Pokémon Center New York",
             51: "Erlösen (Colosseum/XD)", 52: "Erlösen, zweiter Versuch (Colosseum/XD)", 53: "Poképlatz (XD)",
             54: "Versteckte Grotte", 55: "Honigbaum", 56: "frei aus Boden oder Sumpf", 57: "feste Stelle (Oberwelt)",
             58: "feste Stelle im Wasser", 59: "verfolgt beim Schwimmen", 60: "Dynamax-Abenteuer", 61: "Dyna-Raid",
             62: "aus der Mülltonne", 63: "aus dem raschelnden Busch", 64: "von der Höhlendecke", 65: "aus dem Boden", 66: "vom Himmel"}
# Begegnungsarten, die einmalig sind oder ein Geschenk: in „Was fehlt mir noch“ unter „fest“
FIXED_METHODS = {METHOD_DE[i] for i in (18, 19, 20, 36, 45, 46, 47, 48, 49, 50, 51, 52, 57, 58)}


def _methods(con):
    """Begegnungsarten der PokéAPI mit deutschem Namen (eigene Übersetzung, wo die PokéAPI nur englisch hat)."""
    out = _names(con, "encounter_method_prose", "encounter_method_id")
    out.update(METHOD_DE)
    return out


def _place(place, area):
    """Ort mit Teilgebiet: „Eispfad (1.UG)“; enthält das Teilgebiet schon den Ort („Dunkelhöhle (Viola City Eingang)“),
    nur das Teilgebiet."""
    if not area or area.lower() in place.lower():
        return place
    return area if place.lower() in area.lower() else f"{place} ({area})"


def areas(p):
    """Gebiete eines Spiels mit allen Pokémon dort (für Spiele ohne Karte): {spiel, quelle, gebiete: [{ort, mons:
    [{id, name, methode, level, anteil, editionen, bedingungen}]}]}. Aus den Spieldaten (PKHeX), sonst aus der PokéAPI."""
    D = data()
    if not D:
        return None
    g, _, _ = game_of(D, p.get("spiel"))
    if not g:
        return None
    try:
        key = (g["kennung"], os.path.getmtime(db.pokeapi_path()))
    except OSError:
        return None
    hit = _AREAS.pop(key, None)
    if hit is not None:
        _AREAS[key] = hit                       # zuletzt gefragt: ans Ende
        return hit
    con = db.game()
    try:
        out = _areas_pkhex(con, D, g)
        quelle = "PKHeX"
        if out is None:
            out, quelle = _areas_pokeapi(con, D, g), "PokéAPI"
    finally:
        con.close()
    res = {"spiel": g["kennung"], "quelle": quelle,
           "gebiete": [{"ort": k, "mons": sorted(v, key=lambda m: (m["methode"], -(m["anteil"] or 0), m["name"]))} for k, v in out.items()]}
    for k in [k for k in _AREAS if k[1] != key[1]]:      # neue Datenbank: alles Alte weg
        _AREAS.pop(k, None)
    while len(_AREAS) >= AREAS_MAX:
        _AREAS.pop(next(iter(_AREAS)), None)
    _AREAS[key] = res
    return res


def _areas_pkhex(con, D, g):
    try:
        rows = con.execute("SELECT form, gebiet, gebiet_nr, art, MIN(min) lo, MAX(max) hi, MAX(alpha) al FROM fundort WHERE spiel = ? "
                           "GROUP BY gebiet, form, art ORDER BY MIN(gebiet_nr), gebiet", (g["kennung"],)).fetchall()
    except Exception as err:
        fehler.melden(err)
        return None
    if not rows:
        return None
    out = {}
    for r in rows:
        f = D.forms.get(r["form"])
        if not f:
            continue
        lv = f"{r['lo']}" if r["lo"] == r["hi"] else f"{r['lo']}–{r['hi']}"
        out.setdefault(r["gebiet"], []).append({"id": f["id"], "name": f["name"], "methode": importer.PKHEX_ART.get(r["art"], str(r["art"])),
                                                "level": lv if r["lo"] else "", "anteil": None, "editionen": [], "bedingungen": [],
                                                "alpha": r["al"] == 2})
    return out


def _areas_pokeapi(con, D, g):
    """Gebiete aus den Begegnungen der PokéAPI. Die Häufigkeit (anteil) ist die Summe der Plätze (encounter_slots), die das
    Pokémon in einer Edition belegt: jeder Platz einmal, auch wenn er je Edition und je Bedingung (Tageszeit, Schwarm …)
    eine eigene Zeile hat; bei zwei Editionen der größere Wert. Bis 0.58.1 zählte jede Zeile, also doppelt in Spielen mit
    zwei Editionen und mehrfach bei Bedingungen. Mit Bedingungen ist der Wert der höchste, den das Pokémon erreicht."""
    try:
        rows = con.execute(
            """SELECT e.id eid, e.pokemon_id pid, l.id loc, e.location_area_id la, es.encounter_method_id meth, e.min_level lo,
                      e.max_level hi, v.id ver, es.id slot, es.rarity rar
               FROM encounters e JOIN versions v ON v.id = e.version_id JOIN location_areas la ON la.id = e.location_area_id
               JOIN locations l ON l.id = la.location_id JOIN encounter_slots es ON es.id = e.encounter_slot_id
               WHERE v.version_group_id = ? ORDER BY l.id, la.id, e.id""", (g["id"],)).fetchall()
        bed = {}
        for eid, c in con.execute(
                """SELECT m.encounter_id, m.encounter_condition_value_id FROM encounter_condition_value_map m
                   JOIN encounters e ON e.id = m.encounter_id JOIN versions v ON v.id = e.version_id
                   WHERE v.version_group_id = ? ORDER BY m.encounter_id, m.encounter_condition_value_id""", (g["id"],)):
            bed.setdefault(eid, []).append(c)
    except Exception as err:
        fehler.melden(err)
        return {}
    locs = _names(con, "location_names", "location_id")
    area_n = _names(con, "location_area_prose", "location_area_id")
    meths = _methods(con)
    conds = _names(con, "encounter_condition_value_prose", "encounter_condition_value_id")
    vn = _names(con, "version_names", "version_id")
    nv = con.execute("SELECT COUNT(*) FROM versions WHERE version_group_id = ?", (g["id"],)).fetchone()[0]
    groups = {}
    for r in rows:
        x = groups.setdefault((r["pid"], r["la"], r["meth"]), {"loc": r["loc"], "lo": r["lo"], "hi": r["hi"], "slots": {}, "cond": []})
        x["lo"], x["hi"] = min(x["lo"], r["lo"]), max(x["hi"], r["hi"])
        x["slots"].setdefault(r["ver"], {})[r["slot"]] = r["rar"] or 0
        x["cond"] += [c for c in bed.get(r["eid"], ()) if c not in x["cond"]]
    out = {}
    for (pid, la, meth), x in groups.items():
        f = D.forms.get(pid)
        if not f:
            continue
        place, area = locs.get(x["loc"]) or f"Ort {x['loc']}", area_n.get(la) or ""
        ort = _place(place, area)
        vs = sorted(x["slots"])
        rar = max(sum(s.values()) for s in x["slots"].values())
        out.setdefault(ort, []).append({
            "id": f["id"], "name": f["name"], "methode": meths.get(meth, ""),
            "level": f"{x['lo']}" if x["lo"] == x["hi"] else f"{x['lo']}–{x['hi']}",
            "anteil": min(100, rar) if rar else None,
            "editionen": [vn.get(v, "") for v in vs] if len(vs) < nv else [],
            "bedingungen": [conds[c] for c in sorted(x["cond"]) if c in conds]})
    return out
