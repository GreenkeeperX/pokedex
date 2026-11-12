"""Interaktive Karten von Map Genie (mapgenie.io), ohne Netz gelesen.

Map Genie baut jede Karte gleich: die Seite `/<Spiel>/maps/<Karte>` trägt in `window.mapData` die Gruppen und Kategorien
der Symbole und die Kachelsätze; `/api/v1/maps/<Nummer>/data` liefert die Orte (Breite, Länge in Grad, Kategorie, Titel,
Beschreibung). Die Kacheln liegen unter `tiles.mapgenie.io/games/<Muster>` im üblichen z/x/y-Schema (Web-Mercator).
Alles bleibt im Datenordner (`mapgenie/`), nichts davon gehört ins Repository.
"""
import html as _html
import json
import math
import re

BASE = "https://mapgenie.io/"
TILES = "https://tiles.mapgenie.io/games/"
# Spiel (Kennung wie in der PokéAPI) → Kennung bei Map Genie (auch mehrere zum Probieren: die erste, die antwortet, gilt).
# Stand 11.11.2026 gibt es dort genau diese Pokémon-Spiele (Rot/Blau/Gelb in einem, mit den Karten redblue und yellow);
# Schwert/Schild, BDSP, Let’s Go und die übrigen alten Spiele fehlen. Pokopia steht dort ohne „pokemon-“ (importer.EIGENE_SPIELE)
GAMES = {"legends-arceus": "pokemon-legends-arceus", "scarlet-violet": "pokemon-scarlet-violet",
         "legends-za": "pokemon-legends-z-a", "firered-leafgreen": "pokemon-firered-leafgreen",
         "red-blue": "pokemon-red-blue-yellow", "pokopia": "pokopia"}
# Erweiterungen und Schwester-Editionen zeigen die Karten ihres Hauptspiels
SHARE = {"the-isle-of-armor": "sword-shield", "the-crown-tundra": "sword-shield", "the-teal-mask": "scarlet-violet", "the-indigo-disk": "scarlet-violet", "mega-dimension": "legends-za",
         "yellow": "red-blue", "red-green-japan": "red-blue", "blue-japan": "red-blue"}


def slugs(spiel):
    """Kennungen bei Map Genie zum Probieren, in Reihenfolge."""
    s = GAMES.get(spiel) or ()
    return (s,) if isinstance(s, str) else tuple(s)


def game_url(slug):
    return f"{BASE}{slug}"


def map_url(slug, karte):
    return f"{BASE}{slug}/maps/{karte}"


def data_url(map_id):
    return f"{BASE}api/v1/maps/{int(map_id)}/data"


def map_slugs(page, slug):
    """Kennungen der Karten eines Spiels aus einer seiner Seiten (Links /<Spiel>/maps/<Karte>), in Reihenfolge."""
    out = []
    for m in re.finditer(r"/" + re.escape(slug) + r"/maps/([a-z0-9][a-z0-9-]{0,60})", str(page or "").replace("\\/", "/")):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def _var(page, name):
    i = str(page or "").find(f"window.{name} = ")
    if i < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(page, i + len(f"window.{name} = "))[0]
    except ValueError:
        return None


def _text(s, n=1500):
    """Beschreibung ohne HTML, gekürzt; Markdown (Fett, Kursiv, Links, Listen) bleibt für die Oberfläche."""
    t = re.sub(r"<br\s*/?>|</p>", "\n", str(s or ""), flags=re.I)
    t = _html.unescape(re.sub(r"<[^>]+>", "", t))
    t = re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()
    return t[:n]


def parse(page, data):
    """Seite (HTML) und Daten (JSON-Text) einer Karte → kompakte Karte oder None:
    {id, slug, titel, kacheln (Muster), min_zoom, max_zoom, bounds [west, süd, ost, nord], gruppen: [{id, titel, farbe,
    kategorien: [{id, titel, icon, n}]}], orte: [[id, Kategorie, Breite, Länge, Titel, Beschreibung]],
    gebiete: [[Name, west, süd, ost, nord]]}."""
    md = _var(page, "mapData") or {}
    try:
        d = json.loads(data) if isinstance(data, str) else (data or {})
    except ValueError:
        return None
    m = md.get("map") or d.get("map") or {}
    sets = sorted((md.get("mapConfig") or {}).get("tile_sets") or [], key=lambda s: s.get("order") or 0)
    if not m.get("id") or not sets:
        return None
    ts = sets[0]
    orte = []
    for loc in d.get("locations") or []:
        try:
            orte.append([int(loc["id"]), int(loc["category_id"]), round(float(loc["latitude"]), 6), round(float(loc["longitude"]), 6),
                         str(loc.get("title") or "")[:120], _text(loc.get("description"))])
        except (KeyError, TypeError, ValueError):
            continue
    n = {}
    for o in orte:
        n[o[1]] = n.get(o[1], 0) + 1
    gruppen = []
    for g in sorted(md.get("groups") or [], key=lambda g: g.get("order") or 0):
        cats = [{"id": int(c["id"]), "titel": str(c.get("title") or ""), "icon": str(c.get("icon") or ""), "n": n.get(int(c["id"]), 0)}
                for c in sorted(g.get("categories") or [], key=lambda c: c.get("order") or 0) if c.get("id") is not None]
        cats = [c for c in cats if c["n"]]
        if cats:
            gruppen.append({"id": int(g.get("id") or 0), "titel": str(g.get("title") or ""), "farbe": "#" + str(g.get("color") or "888888")[:6],
                            "kategorien": cats})
    gebiete = []                # Gebiete mit Umriss: [Name, west, süd, ost, nord] für „Gehe zu“
    for r in sorted(d.get("regions") or [], key=lambda r: (r.get("order") or 0, str(r.get("title") or ""))):
        xs, ys = [], []
        for f in r.get("features") or []:
            stack = [((f or {}).get("geometry") or {}).get("coordinates")]
            while stack:
                c = stack.pop()
                if isinstance(c, list) and len(c) == 2 and all(isinstance(v, (int, float)) for v in c):
                    xs.append(c[0]); ys.append(c[1])
                elif isinstance(c, list):
                    stack.extend(c)
        if xs and r.get("title"):
            gebiete.append([str(r["title"])[:80], round(min(xs), 6), round(min(ys), 6), round(max(xs), 6), round(max(ys), 6)])
    gebiete.sort(key=lambda g: g[0].lower())
    bounds = ((d.get("styles") or {}).get("mapStyle") or {}).get("bounds")
    if not (isinstance(bounds, list) and len(bounds) == 4):
        bounds = None
    return {"id": int(m["id"]), "slug": str(m.get("slug") or ""), "titel": str(m.get("title") or ""),
            "kacheln": str(ts.get("pattern") or ""), "endung": str(ts.get("extension") or "png"),
            "min_zoom": int(ts.get("min_zoom") or 0), "max_zoom": int(ts.get("tiles_max_zoom") or ts.get("max_zoom") or 0),
            "bounds": bounds, "gruppen": gruppen, "orte": orte, "gebiete": gebiete}


def tile_range(bounds, z):
    """Kacheln (x0, x1, y0, y1) einer Zoomstufe, die die Karte [west, süd, ost, nord] bedecken; None ohne Grenzen.
    Außerhalb gibt es bei Map Genie keine Kacheln (der Speicher antwortet dann mit 403 statt 404)."""
    if not (isinstance(bounds, list) and len(bounds) == 4):
        return None
    w, s, e, n = bounds
    x0, y0 = project(n, w, z)
    x1, y1 = project(s, e, z)
    return int(x0 // 256), int((x1 - 1e-6) // 256), int(y0 // 256), int((y1 - 1e-6) // 256)


def tile_ok(pattern, z, x, y, endung="png"):
    """Kachelpfad nach dem Muster der Karte, nur mit Zahlen; None bei unpassendem Muster. Manche Karten nennen die
    Endung nicht im Muster, sondern getrennt (endung); dann wird sie angehängt."""
    pattern = pattern or ""
    xy = r"\{z\}/(\{x\}/\{y\}|\{y\}/\{x\})"          # Z-A nennt erst y, dann x
    if re.fullmatch(r"[a-z0-9][a-z0-9/_.-]{0,150}" + xy, pattern) and endung in ("png", "jpg", "jpeg", "webp"):
        pattern += "." + endung
    if not re.fullmatch(r"[a-z0-9][a-z0-9/_.-]{0,150}" + xy + r"(@2x)?\.(png|jpg|jpeg|webp)", pattern):
        return None
    return pattern.replace("{z}", str(int(z))).replace("{x}", str(int(x))).replace("{y}", str(int(y)))


def bounds_of(m):
    """Grenzen einer Karte [west, süd, ost, nord]; fehlen sie bei Map Genie, aus den Orten mit etwas Rand."""
    b = m.get("bounds")
    if isinstance(b, list) and len(b) == 4:
        return b
    la = [o[2] for o in m.get("orte") or []]
    lo = [o[3] for o in m.get("orte") or []]
    if not la:
        return None
    pa, po = (max(la) - min(la)) * 0.08 or 0.05, (max(lo) - min(lo)) * 0.08 or 0.05
    return [round(min(lo) - po, 6), round(min(la) - pa, 6), round(max(lo) + po, 6), round(max(la) + pa, 6)]


def tile_list(m, top=None):
    """Alle Kacheln einer Karte als (z, x, y), von min_zoom bis top (Vorgabe: die größte); ohne Grenzen leer."""
    b = bounds_of(m)
    if not b:
        return []
    top = m["max_zoom"] if top is None else min(top, m["max_zoom"])
    out = []
    for z in range(max(0, m["min_zoom"]), top + 1):       # unter min_zoom gibt es keine Kacheln (nur 403)
        x0, x1, y0, y1 = tile_range(b, z)
        out += [(z, x, y) for x in range(max(0, x0), x1 + 1) for y in range(max(0, y0), y1 + 1)]
    return out


# ------------------------------------------------------------------ eigene Punkte auf der Karte von Map Genie
# Gemeinsame Sammelobjekte, an denen sich die Spielkoordinaten (x, z je Gebiet) an Map Genie ausrichten
ANKER = (("wisp", "irrlicht"), ("unown", "icognito"))
ALIGN_ZOOM = 14             # Weltpixel dieser Zoomstufe als Rechenebene
ALIGN_TOL = 30.0            # so nah (Pixel) gilt ein Anker als getroffen
ALIGN_MIN = 6


def project(lat, lng, z=ALIGN_ZOOM):
    """Breite, Länge → Weltpixel (Web-Mercator)."""
    s = 256 * 2 ** z
    sy = math.sin(math.radians(lat))
    return (lng + 180) / 360 * s, (0.5 - math.log((1 + sy) / (1 - sy)) / (4 * math.pi)) * s


def unproject(x, y, z=ALIGN_ZOOM):
    s = 256 * 2 ** z
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / s)))), x / s * 360 - 180


def anchors(m):
    """Anker einer Karte von Map Genie: {Art im Pokédex: [(x, y) in Weltpixeln]}."""
    cats = {}
    for g in m.get("gruppen") or []:
        for c in g["kategorien"]:
            for key, art in ANKER:
                if key in c["titel"].lower():
                    cats[c["id"]] = art
    out = {}
    for o in m.get("orte") or []:
        if o[1] in cats:
            out.setdefault(cats[o[1]], []).append(project(o[2], o[3]))
    return out


def align(game, mg):
    """game: [(x, z)] Anker eines Gebiets in Spielkoordinaten, mg: [(x, y)] dieselbe Art Anker auf der ganzen Karte.
    Gibt (ax, bx, az, bz) mit X = ax·x + bx, Y = az·z + bz (Weltpixel) oder None. Erst eine Abstimmung über Maßstab und
    Verschiebung (jedes Paar stimmt für eine Verschiebung), dann Ausgleich über die getroffenen Paare je Achse."""
    if len(game) < ALIGN_MIN or len(mg) < ALIGN_MIN:
        return None
    best, hits = None, 0
    for k in range(-40, 41):
        s = 2.0 * 1.012 ** k                    # Maßstab um 2 Pixel je Spieleinheit, ±60 %
        votes = {}
        for x, z in game:
            for X, Y in mg:
                key = (round((X - s * x) / ALIGN_TOL), round((Y - s * z) / ALIGN_TOL))
                votes[key] = votes.get(key, 0) + 1
        # Nachbarfelder zählen mit: Map Genie setzt die Symbole von Hand, ein Anker liegt schon mal ein Feld daneben
        key, n = max(((kk, sum(votes.get((kk[0] + i, kk[1] + j), 0) for i in (-1, 0, 1) for j in (-1, 0, 1))) for kk in votes),
                     key=lambda kv: kv[1])
        if n > hits:
            best, hits = (s, key[0] * ALIGN_TOL, key[1] * ALIGN_TOL), n
    if hits < max(ALIGN_MIN, len(game) // 2):
        return None
    s, tx, tz = best
    pairs = []
    for x, z in game:
        X, Y = min(mg, key=lambda p: (p[0] - s * x - tx) ** 2 + (p[1] - s * z - tz) ** 2)
        if math.hypot(X - s * x - tx, Y - s * z - tz) <= 2 * ALIGN_TOL:
            pairs.append((x, z, X, Y))
    if len(pairs) < ALIGN_MIN:
        return None

    def line(us, vs):
        n, mu, mv = len(us), sum(us) / len(us), sum(vs) / len(vs)
        var = sum((u - mu) ** 2 for u in us)
        a = sum((u - mu) * (v - mv) for u, v in zip(us, vs)) / var if var else s
        return a, mv - a * mu
    ax, bx = line([p[0] for p in pairs], [p[2] for p in pairs])
    az, bz = line([p[1] for p in pairs], [p[3] for p in pairs])
    return ax, bx, az, bz


# ------------------------------------------------------------------ eine Datenbank: Map Genie und Spieldaten in einem
# Gruppen und Kategorien auf Deutsch; Items und Pokémon übersetzt die Datenbank (englischer Name → deutscher)
GRUPPEN_DE = {"Locations": "Orte", "Services": "Dienste", "Collectibles": "Sammelobjekte", "Quests": "Aufträge",
              "Other": "Sonstiges", "Special Pokémon": "Besondere Pokémon", "Pokemon": "Pokémon", "Pokémon": "Pokémon",
              "Materials": "Materialien und Fundstellen", "Items": "Items", "Collectables": "Sammelobjekte"}
KAT_DE = {"Area": "Gebiet", "Arena": "Arena", "Camp": "Lager", "Cave": "Höhle", "Fast Travel Point": "Schnellreise",
          "Game": "Spiel", "Point of Interest": "Sehenswürdigkeit", "Transition": "Übergang", "Clothier": "Schneiderei",
          "Craftworks": "Werkstatt", "General Store": "Laden", "Hairdresser": "Friseur", "Photo Studio": "Fotostudio",
          "Quarters": "Unterkunft", "Trading Post": "Tauschbörse", "Training Grounds": "Trainingsplatz", "Vendor": "Händler",
          "Old Verse": "Gedichte", "Wisp": "Geisterlichter", "Request": "Nebenaufträge", "Story Mission": "Hauptmissionen",
          "Character": "Personen", "Miscellaneous": "Verschiedenes", "Alpha Pokemon": "Alpha-Pokémon",
          "Event Pokemon": "Ereignis-Pokémon", "Noble Pokemon": "Königs-Pokémon", "Pokemon Area": "Pokémon-Gebiete",
          "Rare Pokemon": "Seltene Pokémon", "Unown Pokemon": "Icognito", "Plant": "Pflanzen", "Apricorn": "Aprikoko-Bäume",
          "Treasure": "Schätze", "Item": "Items", "Items": "Items", "TM": "TMs", "Shop": "Laden", "Pokemon Center": "Pokémon-Center"}
# Eigene Arten, die bei Map Genie eine Kategorie gleicher Bedeutung haben (Titel klein geschrieben)
GLEICH = {"irrlicht": ("wisp",), "icognito": ("unown pokemon",), "vers": ("old verse",), "alpha": ("alpha pokemon",),
          "aprikoko": ("apricorn",), "reise": ("fast travel point",), "lager": ("camp",)}
NACH_ITEM = ("beere", "erz", "boden")        # Kategorie = Item der Stelle (Sinelbeere ↔ Oran Berry)
DRIN = {"kristall": ("erz",), "baumpkmn": ("aprikoko", "beere", "baum")}   # Pokémon, die in etwas stecken
# Gruppe (Titel bei Map Genie) für eigene Ebenen ohne Gegenstück
GRUPPE = {"sp": "Pokemon", "massen": "Special Pokémon", "verzerrung": "Special Pokémon", "alpha": "Special Pokémon",
          "kristall": "Special Pokémon", "baumpkmn": "Special Pokémon", "irrlicht": "Collectibles", "icognito": "Special Pokémon",
          "vers": "Collectibles", "reise": "Locations", "lager": "Locations"}
GRUPPE_NEU = {"Pokemon": "#d95f5f", "Special Pokémon": "#c27ad6", "Collectibles": "#e0b030", "Locations": "#5a9bd5",
              "Materials": "#5fae5f"}
# Namen einzelner Orte: Muster (englisch) → deutsch; {de} steht für die Übersetzung des ersten Teils
NAMEN_DE = ((r"^(.+ Berry) Tree$", "Beerenbaum ({de})"), (r"^Apricorn Tree$", "Aprikoko-Baum"), (r"^Wisp\b", "Geisterlicht"),
            (r"^Old Verse\b", "Altes Gedicht"), (r"^Unown\b", "Icognito"), (r"^King's Leaf$", "Königsblatt"), (r"^Exit$", "Ausgang"),
            (r"^Alpha (.+)$", "Alpha-{de}"))


def name_de(t, de):
    """Name eines Orts von Map Genie auf Deutsch, soweit bekannt (sonst wie dort)."""
    if t in KAT_DE or t in de:
        return KAT_DE.get(t) or de[t]
    for pat, rep in NAMEN_DE:
        m = re.match(pat, t)
        if m:
            first = m.group(1) if m.groups() else ""
            return t[:m.start()] + rep.format(de=de.get(first, first)) + t[m.end():]
    return t


QUELLE = {"pokemoncompletion": "pokemoncompletion", "ign": "IGN", "dittobase": "DittoBase", "rankedboost": "RankedBoost", "pokearth": "Serebii"}   # Name der Quelle einer Karte
MERGE_TOL = 30.0            # so nah (Weltpixel bei Zoomstufe 14, wenige Meter) gelten zwei Punkte als dasselbe
MERGE_WIDE = 3              # Einzelstücke (Geisterlichter, Icognito, Gedichte, Alphas …) dürfen dreimal so weit weg sein


DUP_PX = 3.0               # so nah (Weltpixel bei Zoomstufe 14) und gleich: ein Punkt


def _dedupe(pts):
    """Doppelte Punkte zusammenlegen: dieselbe Ebene an (fast) derselben Stelle. Gleiche Namen werden einer (Map Genie
    führt manche Pflanzen dreifach), eigene Symbole gleicher Art legen ihre Items zusammen (ein Massenauftreten mit
    mehreren Pokémon). Spawnpunkte und verschiedene Namen (zwei Alphas an einer Stelle) bleiben."""
    out, seen = [], {}
    for p in pts:
        if p.get("sp"):
            out.append(p)
            continue
        X, Y = p.get("_xy") or project(p["la"], p["lo"])
        key = (p["c"], round(X / DUP_PX), round(Y / DUP_PX))
        q = seen.get(key)
        if q is None:
            seen[key] = p
            out.append(p)
            continue
        own_p, own_q = p.get("o") and "id" not in p, q.get("o") and "id" not in q
        if own_p and own_q and p["o"].get("art") == q["o"].get("art"):
            q["o"]["items"] = q["o"]["items"] + [i for i in p["o"]["items"] if i not in q["o"]["items"]]
        elif p["name"] == q["name"]:
            if p.get("o") and not q.get("o"):
                q["o"] = p["o"]
            q["q"] = list(dict.fromkeys(q.get("q", []) + p.get("q", [])))
            q["mal"] = q.get("mal", 1) + 1
        else:
            out.append(p)
    return out


def merge(m, own=None, de=None):
    """Eine Karte als eine Datenbank: Orte von Map Genie und eigene Daten (Spawnpunkte, Symbole aus den Spieldaten),
    nach Bedeutung gruppiert. Was an derselben Stelle dasselbe ist, wird ein Punkt mit allen Angaben (Text von Map Genie,
    Items, Pokémon darin); der Rest kommt in die passende Ebene. own: Ergebnis von abfragen.mg_overlay oder None,
    de: {englischer Name: deutscher} für Items und Pokémon.
    {gruppen: [{id, titel, farbe, kategorien: [{id, titel, en, n, art?}]}], punkte: [{c, la, lo, name, en?, id?, text?,
    o?, sp?, drin?, q}], gebiete_eigen: {Karte: Gebiet}}"""
    de = de or {}
    tr = lambda t: KAT_DE.get(t) or de.get(t) or t
    groups, by_en, cat = [], {}, {}
    for g in m.get("gruppen") or []:
        G = {"id": g["id"], "titel": GRUPPEN_DE.get(g["titel"], g["titel"]), "farbe": g["farbe"], "kategorien": []}
        for c in g["kategorien"]:
            C = {"id": c["id"], "titel": tr(c["titel"]), "en": c["titel"], "n": 0}
            G["kategorien"].append(C)
            cat[c["id"]] = C
        groups.append(G)
        by_en[g["titel"]] = G
    pts = []
    qname = QUELLE.get(m.get("quelle"), "Map Genie")
    for o in m.get("orte") or []:
        if o[1] in cat:
            text = re.sub(r"«([^»]+)»", lambda x: de.get(x.group(1), x.group(1)), o[5]) if "«" in o[5] else o[5]
            p = {"id": o[0], "c": o[1], "la": o[2], "lo": o[3], "name": name_de(o[4], de), "text": text, "q": [qname]}
            if p["name"] != o[4]:
                p["en"] = o[4]
            pts.append(p)
    gebiete = {}
    if own:
        gebiete = dict(own.get("gebiete") or {})
        arten = own.get("arten") or {}

        def group_of(key):
            t = GRUPPE.get(key, "Materials")
            if t not in by_en:
                G = {"id": "g:" + t, "titel": GRUPPEN_DE.get(t, t), "farbe": GRUPPE_NEU.get(t, "#888888"), "kategorien": []}
                groups.append(G)
                by_en[t] = G
            return by_en[t]

        def own_cat(art, titel=None):
            k = "o:" + art
            if k not in cat:
                C = {"id": k, "titel": titel or (arten.get(art) or [art, art])[1], "en": "", "n": 0, "art": art}
                group_of(art)["kategorien"].append(C)
                cat[k] = C
            return k
        by_title = {C["titel"]: C["id"] for C in cat.values()}
        by_low = {}
        for C in cat.values():
            by_low.setdefault(C["en"].lower(), C["id"])

        def compatible(o, p):
            C = cat[p["c"]]
            if o["art"] in GLEICH:
                return C["en"].lower() in GLEICH[o["art"]]
            if o["art"] in NACH_ITEM:
                return C["titel"] in {i[0] for i in o["items"]}
            return False

        grid = {}
        for j, p in enumerate(pts):
            X, Y = project(p["la"], p["lo"])
            p["_xy"] = (X, Y)
            grid.setdefault((int(X // MERGE_TOL), int(Y // MERGE_TOL)), []).append(j)

        def near(x, y, r=1):
            gx, gy = int(x // MERGE_TOL), int(y // MERGE_TOL)
            for i in range(-r, r + 1):
                for k in range(-r, r + 1):
                    yield from grid.get((gx + i, gy + k), ())
        objs = [o for o in own.get("objekte") or [] if o["art"] not in DRIN]
        pairs = []
        for i, o in enumerate(objs):
            x, y = project(o["la"], o["lo"])
            o["_xy"] = (x, y)
            wide = MERGE_WIDE if o["art"] in GLEICH else 1
            for j in near(x, y, wide):
                d = math.hypot(pts[j]["_xy"][0] - x, pts[j]["_xy"][1] - y)
                if d <= MERGE_TOL * wide and compatible(o, pts[j]):
                    pairs.append((d, i, j))
        pairs.sort()
        used_o, used_p = set(), set()
        slim = lambda o: {k: o[k] for k in ("art", "nr", "menge", "items", "k", "x", "z") if k in o}
        for d, i, j in pairs:
            if i in used_o or j in used_p:
                continue
            used_o.add(i)
            used_p.add(j)
            pts[j]["o"] = slim(objs[i])
            pts[j]["q"].append("Spieldaten")
            if objs[i]["art"] in GLEICH:
                cat[pts[j]["c"]].setdefault("art", objs[i]["art"])      # Symbol wie auf den Einzelkarten
        for i, o in enumerate(objs):
            if i in used_o:
                continue
            c = next((by_low[t] for t in GLEICH.get(o["art"], ()) if t in by_low), None)
            if not c and o["art"] in NACH_ITEM and o["items"]:
                c = by_title.get(o["items"][0][0])
            if not c:
                c = own_cat(o["art"])
            name = (arten.get(o["art"]) or [o["art"]])[0] + (f" {o['nr']}" if o.get("nr") else "")
            p = {"c": c, "la": o["la"], "lo": o["lo"], "name": name, "o": slim(o), "q": ["Spieldaten"], "_xy": o["_xy"]}
            pts.append(p)
            grid.setdefault((int(o["_xy"][0] // MERGE_TOL), int(o["_xy"][1] // MERGE_TOL)), []).append(len(pts) - 1)
        # Pokémon in Erzbrocken und Bäumen: an die Stelle, in der sie stecken
        for o in own.get("objekte") or []:
            if o["art"] not in DRIN:
                continue
            x, y = project(o["la"], o["lo"])
            best = None
            for j in near(x, y):
                h = pts[j].get("o")
                if h and h["art"] in DRIN[o["art"]]:
                    d = math.hypot(pts[j]["_xy"][0] - x, pts[j]["_xy"][1] - y)
                    if d <= MERGE_TOL and (not best or d < best[0]):
                        best = (d, j)
            if best:
                p = pts[best[1]]
                p.setdefault("drin", []).append({"art": o["art"], "items": o["items"]})
            else:
                pts.append({"c": own_cat(o["art"]), "la": o["la"], "lo": o["lo"], "name": (arten.get(o["art"]) or [o["art"]])[0],
                            "o": slim(o), "q": ["Spieldaten"]})
        if own.get("punkte"):
            k = "sp"
            G = group_of("sp")
            C = {"id": k, "titel": "Spawnpunkte", "en": "", "n": 0, "art": "sp"}
            G["kategorien"].insert(0, C)
            cat[k] = C
            for s in own["punkte"]:
                pts.append({"c": k, "la": s["la"], "lo": s["lo"], "name": ", ".join(x["name"] for x in s["mons"]),
                            "sp": {"alpha": s["alpha"], "mons": s["mons"], "k": s["k"]}, "q": ["Spieldaten"]})
    pts = _dedupe(pts)
    for p in pts:
        p.pop("_xy", None)
        cat[p["c"]]["n"] += 1
    for G in groups:
        G["kategorien"] = [C for C in G["kategorien"] if C["n"]]
    return {"gruppen": [G for G in groups if G["kategorien"]], "punkte": pts, "gebiete_eigen": gebiete}
