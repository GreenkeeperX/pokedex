"""Interaktive Karten von Map Genie (mapgenie.io), ohne Netz gelesen.

Map Genie baut jede Karte gleich: die Seite `/<Spiel>/maps/<Karte>` trägt in `window.mapData` die Gruppen und Kategorien
der Symbole und die Kachelsätze; `/api/v1/maps/<Nummer>/data` liefert die Orte (Breite, Länge in Grad, Kategorie, Titel,
Beschreibung). Die Kacheln liegen unter `tiles.mapgenie.io/games/<Muster>` im üblichen z/x/y-Schema (Web-Mercator).
Alles bleibt im Datenordner (`mapgenie/`), nichts davon gehört ins Repository.
"""
import html as _html
import json
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
    t = _html.unescape(re.sub(r"<[^>]+>", "", t))
    t = re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()
    return t[:n]


def parse(page, data):
    """Seite (HTML) und Daten (JSON-Text) einer Karte → kompakte Karte oder None:
    {id, slug, titel, kacheln (Muster), min_zoom, max_zoom, bounds [west, süd, ost, nord], gruppen: [{id, titel, farbe,
    kategorien: [{id, titel, icon, n}]}], orte: [[id, Kategorie, Breite, Länge, Titel, Beschreibung]]}."""
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
    bounds = ((d.get("styles") or {}).get("mapStyle") or {}).get("bounds")
    if not (isinstance(bounds, list) and len(bounds) == 4):
        bounds = None
    return {"id": int(m["id"]), "slug": str(m.get("slug") or ""), "titel": str(m.get("title") or ""),
            "kacheln": str(ts.get("pattern") or ""), "endung": str(ts.get("extension") or "png"),
            "min_zoom": int(ts.get("min_zoom") or 0), "max_zoom": int(ts.get("tiles_max_zoom") or ts.get("max_zoom") or 0),
            "bounds": bounds, "gruppen": gruppen, "orte": orte}


def tile_ok(pattern, z, x, y):
    """Kachelpfad nach dem Muster der Karte, nur mit Zahlen; None bei unpassendem Muster."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9/_.-]{0,150}\{z\}/\{x\}/\{y\}\.(png|jpg|webp)", pattern or ""):
        return None
    return pattern.replace("{z}", str(int(z))).replace("{x}", str(int(x))).replace("{y}", str(int(y)))
