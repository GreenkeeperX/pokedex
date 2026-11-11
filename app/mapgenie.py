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
# Spiel (Kennung wie in der PokéAPI) → Kennung bei Map Genie. Was es dort nicht gibt, meldet 404 und fällt weg.
GAMES = {"legends-arceus": "pokemon-legends-arceus", "scarlet-violet": "pokemon-scarlet-violet",
         "legends-za": "pokemon-legends-z-a", "sword-shield": "pokemon-sword-shield",
         "brilliant-diamond-shining-pearl": "pokemon-brilliant-diamond-shining-pearl",
         "lets-go-pikachu-lets-go-eevee": "pokemon-lets-go"}
# Erweiterungen zeigen die Karten ihres Hauptspiels
SHARE = {"the-teal-mask": "scarlet-violet", "the-indigo-disk": "scarlet-violet", "mega-dimension": "legends-za",
         "the-isle-of-armor": "sword-shield", "the-crown-tundra": "sword-shield"}


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


def _text(s, n=600):
    """Beschreibung ohne HTML, gekürzt."""
    t = re.sub(r"<br\s*/?>|</p>", "\n", str(s or ""), flags=re.I)
    t = _html.unescape(re.sub(r"<[^>]+>|\*\*|__", "", t))      # HTML und Fettdruck (Markdown) weg
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


def tile_ok(pattern, z, x, y):
    """Kachelpfad nach dem Muster der Karte, nur mit Zahlen; None bei unpassendem Muster."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9/_.-]{0,150}\{z\}/\{x\}/\{y\}\.(png|jpg|webp)", pattern or ""):
        return None
    return pattern.replace("{z}", str(int(z))).replace("{x}", str(int(x))).replace("{y}", str(int(y)))


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
