"""Regionskarten von Serebii (PokéEarth) lesen, ohne Netz (den Abruf macht abruf._pokearth).

Die Regionsseite (/pokearth/<Region>/) zeigt die Karte der Region als kleines Bild mit Bildkarte (<img usemap> und je Ort
ein <area> mit Titel, Form und Koordinaten in Bildpixeln). Daraus wird eine Karte in derselben Form wie bei Map Genie:
das ganze Bild als eine Bildebene (wie bei RankedBoost, keine Kacheln) und je Ort ein Punkt in der Mitte seiner Fläche.
Die Pokémon je Ort kommen beim Anzeigen aus den Fundorten des Spiels (abfragen._pokearth_mons).
"""
import html
import math
import re
import urllib.parse

from . import mapgenie

BASE = "https://www.serebii.net/"
TILE = 256
ZOOM_IN = 3                 # so viele Stufen näher als das Bild (die Karten sind klein, der Browser vergrößert sie pixelig)
# Spiele ohne eigene Karte einer anderen Quelle → Regionen bei Serebii (die erste ist die Hauptregion)
GAMES = {"heartgold-soulsilver": ("johto", "kanto"), "black-white": ("unova",), "black-2-white-2": ("unova",),
         "x-y": ("kalos",), "omega-ruby-alpha-sapphire": ("hoenn",), "sun-moon": ("alola",),
         "ultra-sun-ultra-moon": ("alola",), "brilliant-diamond-shining-pearl": ("sinnoh",), "colosseum": ("orre",),
         "xd": ("orre",)}
REGION = {"kanto": "Kanto", "johto": "Johto", "hoenn": "Hoenn", "sinnoh": "Sinnoh", "unova": "Einall", "kalos": "Kalos",
          "alola": "Alola", "orre": "Orre"}
_IMG = re.compile(r"<img\b[^>]*\busemap\s*=\s*[\"']#?([^\"']+)[\"'][^>]*>", re.I)
_AREA = re.compile(r"<area\b[^>]*>", re.I)


def regions():
    return sorted({r for rs in GAMES.values() for r in rs})


def page_url(region):
    return f"{BASE}pokearth/{region}/"


def _attr(tag, name):
    m = re.search(r"\b" + name + r"\s*=\s*([\"'])(.*?)\1", tag, re.I | re.S)
    return html.unescape(m.group(2)) if m else None


def image_ok(url):
    """Nur Bilder von Serebii unter /pokearth/; sonst None."""
    u = urllib.parse.urljoin(BASE, str(url or ""))
    p = urllib.parse.urlsplit(u)
    if p.scheme == "https" and p.netloc in ("www.serebii.net", "serebii.net") and re.fullmatch(r"/pokearth/[\w/.-]+\.(png|jpg|gif)", p.path):
        return u
    return None


def extract(page):
    """Regionsseite → {bild, w, h, orte: [{name, x, y, w, h, seite}]} oder None (ohne Bildkarte)."""
    page = page or ""
    for img in _IMG.finditer(page):
        tag, name = img.group(0), img.group(1)
        url = image_ok(_attr(tag, "src"))
        try:
            w, h = int(_attr(tag, "width") or 0), int(_attr(tag, "height") or 0)
        except ValueError:
            continue
        if not url or w <= 0 or h <= 0:
            continue
        m = re.search(r"<map\b[^>]*\bname\s*=\s*[\"']" + re.escape(name) + r"[\"'][^>]*>(.*?)</map>", page, re.I | re.S)
        body = m.group(1) if m else page[img.end():]
        orte = []
        for a in _AREA.finditer(body):
            t = a.group(0)
            title = " ".join((_attr(t, "title") or _attr(t, "alt") or "").split())
            try:
                cs = [float(c) for c in re.split(r"[\s,]+", (_attr(t, "coords") or "").strip()) if c]
            except ValueError:
                continue
            shape = (_attr(t, "shape") or "rect").lower()
            if not title or len(cs) < 3:
                continue
            if shape.startswith("circ"):
                x0, y0, x1, y1 = cs[0] - cs[2], cs[1] - cs[2], cs[0] + cs[2], cs[1] + cs[2]
            else:
                xs, ys = cs[0::2], cs[1::2]
                x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            orte.append({"name": title[:120], "x": x0, "y": y0, "w": max(1.0, x1 - x0), "h": max(1.0, y1 - y0),
                         "seite": urllib.parse.urljoin(BASE, _attr(t, "href") or "")})
        if orte:
            return {"bild": url, "w": w, "h": h, "orte": orte}
    return None


def parse(d, region):
    """Daten einer Regionsseite → Karte wie mapgenie.parse mit einem Bild (bilder [[0, 0, 0, w, h, Datei]]) oder None."""
    if not d:
        return None
    W, H = d["w"], d["h"]
    z1 = max(0, math.ceil(math.log2(max(W, H) / TILE)))
    ll = lambda x, y: tuple(round(v, 6) for v in mapgenie.unproject(x, y, z1))
    ext = d["bild"].rsplit(".", 1)[-1]
    orte, gebiete, seen = [], [], set()
    for o in d["orte"]:
        if o["name"] in seen:
            continue
        seen.add(o["name"])
        la, lo = ll(o["x"] + o["w"] / 2, o["y"] + o["h"] / 2)
        n, w = ll(o["x"], o["y"])
        s, e = ll(o["x"] + o["w"], o["y"] + o["h"])
        cat = 2 if re.search(r"\b(Route|Road|Path|Sea|Water)\b", o["name"]) else 1
        orte.append([45_000_000 + len(orte), cat, la, lo, o["name"], ""])
        gebiete.append([o["name"], w, s, e, n])
    n0, w0 = ll(0, 0)
    s0, e0 = ll(W, H)
    cats = [{"id": 1, "titel": "Städte und Orte", "icon": "", "n": sum(1 for o in orte if o[1] == 1)},
            {"id": 2, "titel": "Routen", "icon": "", "n": sum(1 for o in orte if o[1] == 2)}]
    gebiete.sort(key=lambda g: g[0].lower())
    return {"id": 0, "slug": "se-" + region, "titel": f"{REGION.get(region, region.title())} (Serebii)", "quelle": "pokearth",
            "kacheln": "", "endung": ext, "kachel": TILE, "dim": {"w": W, "h": H}, "min_zoom": z1, "max_zoom": z1 + ZOOM_IN,
            "bild_z": z1, "bounds": [w0, s0, e0, n0], "region": region,
            "gruppen": [{"id": 910, "titel": "Orte der Region", "farbe": "#e0a040", "kategorien": cats}],
            "orte": orte, "gebiete": gebiete, "bilder": [[0, 0, 0, W, H, f"se/{region}.{ext}"]]}


def tile(m, z, x, y):
    """Keine Kacheln: die Karte ist ein Bild (siehe abruf.mg_image)."""
    return None


def tile_list(m, top=None):
    return []
