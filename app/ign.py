"""Karten von IGN (ign.com/maps) für Schwert/Schild und Let’s Go: Karte, Kacheln und die Punkte, die die Seite mitbringt
(in __NEXT_DATA__). Ohne Netz; den Abruf macht abruf.py. Das Ergebnis hat dieselbe Form wie eine Karte von Map Genie
(mapgenie.parse), damit es durch dieselbe Strecke läuft.

IGN legt die Karte in ein Einheitsquadrat (Breite width, Höhe height ≤ 1; Punkte mit lat ∈ [−height, 0], lng ∈ [0, width])
und kachelt es wie eine Web-Karte: Stufe z hat 256·2^z Pixel je Einheit, Kacheln {z}/{x}-{y}.jpg zu 256 Pixeln. Hier liegt das
Quadrat auf der ganzen Web-Mercator-Welt; damit sind Stufen und Kachelnummern dieselben wie bei IGN."""
import json
import math
import re

from . import mapgenie

BASE = "https://www.ign.com/maps/"
# Spiel (Kennung wie in der PokéAPI) → (Kennung bei IGN, Karten)
GAMES = {"sword-shield": ("pokemon-sword-shield", ("galar",)),
         "lets-go-pikachu-lets-go-eevee": ("pokemon-lets-go-pikachu-eevee", ("kanto",))}
TITEL = {"galar": "Galar (IGN)", "kanto": "Kanto (IGN)"}
KAT_DE = {"Location": "Orte", "Gym": "Arenen", "Pikachu": "Pikachu", "Pokemon": "Pokémon", "Legendary Pokemon": "Legendäre Pokémon",
          "Master Trainer": "Meistertrainer", "TM": "TMs", "Mega Stone": "Mega-Steine", "Item": "Items", "Items": "Items",
          "Trainer": "Trainer", "Den": "Dyna-Nester", "Max Raid Den": "Dyna-Nester", "Berry Tree": "Beerenbäume",
          "Watt Trader": "W-Händler", "Digging Duo": "Grabungsbrüder", "Fossil": "Fossilien"}
GRUPPE = {"Orte": ("Orte", "#5a9bd5"), "Arenen": ("Orte", "#5a9bd5"), "Pokémon": ("Pokémon", "#d95f5f"),
          "Legendäre Pokémon": ("Pokémon", "#d95f5f"), "Pikachu": ("Pokémon", "#d95f5f"), "Dyna-Nester": ("Pokémon", "#d95f5f"),
          "Meistertrainer": ("Kämpfe", "#c27ad6"), "Trainer": ("Kämpfe", "#c27ad6")}


def page_url(slug, karte):
    return f"{BASE}{slug}/{karte}"


def next_data(page):
    """__NEXT_DATA__ einer Seite als Objekt oder None."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', str(page or ""), re.S)
    try:
        return json.loads(m.group(1)) if m else None
    except ValueError:
        return None


def to_ll(lat, lng):
    """Punkt bei IGN → [Breite, Länge] auf der eigenen Karte (Einheitsquadrat = ganze Welt)."""
    la, lo = mapgenie.unproject(float(lng) * 256, -float(lat) * 256, 0)
    return round(la, 6), round(lo, 6)


def parse(page, karte):
    """Kartenseite (HTML) → Karte wie mapgenie.parse, mit quelle "ign", kachel 256, url (Kachelmuster), einheit
    [Breite, Höhe]; None ohne Karte."""
    d = next_data(page) or {}
    m = (((d.get("props") or {}).get("pageProps") or {}).get("page") or {}).get("map") or {}
    ts = m.get("tilesets") or []
    if not (ts and m.get("width") and m.get("height")):
        return None
    url = str(ts[0])
    if not re.fullmatch(r"https://oyster\.ignimgs\.com/ignmedia/wikimaps/[a-z0-9/_-]+/\{z\}/\{x\}-\{y\}\.(jpg|png)", url):
        return None
    w, h = float(m["width"]), float(m["height"])
    cats, gruppen, orte = {}, {}, []
    for t in m.get("types") or []:
        name = str(t.get("typeName") or t.get("typeSlug") or "")
        titel = KAT_DE.get(name, name)
        for mk in t.get("markers") or []:
            try:
                la, lo = to_ll(mk["lat"], mk["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            if titel not in cats:
                g, farbe = GRUPPE.get(titel, ("Sammelobjekte", "#5fae5f"))
                cats[titel] = {"id": len(cats) + 1, "titel": titel, "icon": "", "n": 0}
                gruppen.setdefault((g, farbe), []).append(cats[titel])
            c = cats[titel]
            c["n"] += 1
            text = str(mk.get("description") or "")
            orte.append([20_000_000 + len(orte), c["id"], la, lo, str(mk.get("markerName") or titel)[:120], mapgenie._text(text)])
    n0, w0 = to_ll(0, 0)
    s0, e0 = to_ll(-h, w)
    order = ("Orte", "Pokémon", "Items", "Kämpfe", "Sammelobjekte")
    gl = [{"id": 800 + i, "titel": g, "farbe": f, "kategorien": cs}
          for i, ((g, f), cs) in enumerate(sorted(gruppen.items(), key=lambda kv: order.index(kv[0][0]) if kv[0][0] in order else 99))]
    return {"id": 0, "slug": "ign-" + karte, "titel": TITEL.get(karte, str(m.get("mapName") or karte)), "quelle": "ign",
            "kacheln": "", "endung": url.rsplit(".", 1)[-1], "kachel": 256, "url": url, "einheit": [w, h],
            "min_zoom": int(m.get("minZoom") or 0), "max_zoom": int(m.get("maxZoom") or 0),
            "bounds": [w0, s0, e0, n0], "gruppen": gl, "orte": orte, "gebiete": sorted(
                ([o[4], o[3] - 0.5, o[2] - 0.3, o[3] + 0.5, o[2] + 0.3] for o in orte if o[1] == (cats.get("Orte") or {}).get("id")),
                key=lambda g: g[0].lower())}


def tile(m, z, x, y):
    """(Pfad im Datenordner, Adresse) einer Kachel, oder None außerhalb der Karte."""
    if not (m["min_zoom"] <= z <= m["max_zoom"]):
        return None
    n = 2 ** int(z)
    w, h = m["einheit"]
    if not (0 <= x < math.ceil(w * n) and 0 <= y < math.ceil(h * n)):
        return None
    rel = f"ign/{m['slug'][4:]}/{int(z)}/{int(x)}-{int(y)}.{m['endung']}"
    return rel, m["url"].replace("{z}", str(int(z))).replace("{x}", str(int(x))).replace("{y}", str(int(y)))


def tile_list(m, top=None):
    top = m["max_zoom"] if top is None else min(top, m["max_zoom"])
    w, h = m["einheit"]
    return [(z, x, y) for z in range(m["min_zoom"], top + 1)
            for x in range(math.ceil(w * 2 ** z)) for y in range(math.ceil(h * 2 ** z))]
