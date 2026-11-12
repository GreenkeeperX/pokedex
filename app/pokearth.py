"""Regionskarten von Serebii (PokéEarth) lesen, ohne Netz (den Abruf macht abruf._pokearth).

Die Regionsseite (/pokearth/<Region>/) zeigt die Karte der Region als kleines Bild mit Bildkarte (<img usemap> und je Ort
ein <area> mit Titel, Form und Koordinaten in Bildpixeln). Daraus wird eine Karte in derselben Form wie bei Map Genie:
das ganze Bild als eine Bildebene (wie bei RankedBoost, keine Kacheln) und je Ort ein Punkt in der Mitte seiner Fläche.
Die Pokémon je Ort kommen beim Anzeigen aus den Fundorten des Spiels (abfragen._pokearth_mons).
"""
import html
import json
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
# 0.48: Regionen, für die Serebii keine Bildkarte hat → Bildkarte (Vorlage) im PokéWiki, deutsche Ortsnamen. Das Bild
# kommt in groß von Bulbapedia, wenn dort dieselbe Karte liegt (gleiches Seitenverhältnis), sonst klein aus dem PokéWiki.
PW_API = "https://www.pokewiki.de/api.php"
BULBA_API = "https://archives.bulbagarden.net/w/api.php"
PW_MAPS = {"kalos": {"vorlage": "XY-Map Kalos", "bild": "XY-Map Kalos.png", "gross": "Kalos XY.png"},
           # 0.56: Alola hat keine Gesamtkarte, sondern je Insel eine Bildkarte (270 px) in einer Vorlage; eine Karte je Insel
           "alola": {"vorlage": "USUM-Map Alola", "inseln": (("mele-mele", "Mele-Mele", "USUM-Map Mele-Mele.png"),
                                                             ("akala", "Akala", "USUM-Map Akala.png"),
                                                             ("ula-ula", "Ula-Ula", "USUM-Map Ula-Ula.png"),
                                                             ("poni", "Poni", "USUM-Map Poni.png"),
                                                             ("aether", "Æther-Paradies", "USUM-Map Æther-Paradies.png"))}}
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


def pw_template_url(region):
    """Wikitext der PokéWiki-Vorlage mit der Bildkarte einer Region."""
    q = {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "format": "json",
         "formatversion": "2", "titles": "Vorlage:" + PW_MAPS[region]["vorlage"]}
    return PW_API + "?" + urllib.parse.urlencode(q)


def imageinfo_url(api, name):
    """Adresse und Größe einer Bilddatei (MediaWiki, PokéWiki oder Bulbapedia)."""
    q = {"action": "query", "prop": "imageinfo", "iiprop": "url|size", "format": "json", "formatversion": "2", "titles": "File:" + name}
    return api + "?" + urllib.parse.urlencode(q)


def imageinfo(text):
    """Antwort von imageinfo → (url, w, h) oder None."""
    try:
        d = json.loads(text or "")
        ps = (d.get("query") or {}).get("pages") or []
        ps = list(ps.values()) if isinstance(ps, dict) else ps
        ii = (ps[0].get("imageinfo") or [{}])[0]
        u, w, h = ii.get("url"), int(ii.get("width") or 0), int(ii.get("height") or 0)
    except (ValueError, IndexError, AttributeError, TypeError):
        return None
    if not u or w <= 0 or h <= 0 or not wiki_image_ok(u):
        return None
    return u, w, h


def wiki_image_ok(url):
    """Nur Bilder vom PokéWiki oder aus dem Bulbapedia-Archiv; sonst None."""
    p = urllib.parse.urlsplit(str(url or ""))
    ok = p.scheme == "https" and p.netloc in ("www.pokewiki.de", "media.pokewiki.de", "archives.bulbagarden.net") \
        and re.search(r"\.(png|jpe?g|gif)$", p.path, re.I)
    return url if ok else None


_AREA_LINE = re.compile(r"(?m)^\s*(rect|poly|circle)\s+([\d\s.,]+?)\s*\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")


def pw_areas(wt):
    """Wikitext einer Vorlage mit Bildkarte → Orte [{name, x, y, w, h, seite}] in Pixeln des Originalbilds; nur die erste
    Bildkarte. Der Name ist das Linkziel ohne Region in Klammern („Route 1 (Kalos)“ → „Route 1“), wie die Ortsnamen der
    Fundorte; das PokéWiki nennt die Orte deutsch."""
    wt = str(wt or "")
    m = re.search(r"(#tag:imagemap|<imagemap>)", wt, re.I)
    if not m:
        return []
    return _areas_of(wt[m.end():])


_MAP_START = re.compile(r"(#tag:imagemap\||<imagemap>)", re.I)


def pw_imagemaps(wt):
    """0.56: alle Bildkarten einer Vorlage → {Bilddatei: Orte}. Die Datei steht in der ersten Zeile („Datei:X.png“, bei
    {{Fileexist|…}} die letzte, das ist das Bild ohne hervorgehobenen Ort)."""
    wt = str(wt or "")
    starts = [m.end() for m in _MAP_START.finditer(wt)] + [len(wt)]
    out = {}
    for a, b in zip(starts, starts[1:]):
        body = wt[a:b]
        files = re.findall(r"(?:Datei|File|Bild):([^|{}\[\]\n]+?\.(?:png|jpe?g|gif))", body.split("\n", 1)[0], re.I)
        if files:
            out.setdefault(" ".join(files[-1].split()), _areas_of(body))
    return out


def _centre(cs, kind):
    """Punkt für einen Ort: Schwerpunkt der Fläche; liegt er außerhalb (Route mit Knick), die nächste Ecke."""
    if kind == "circle" or len(cs) < 6:
        return None
    xs, ys = cs[0::2], cs[1::2]
    n = min(len(xs), len(ys))
    a = cx = cy = 0.0
    for i in range(n):
        j = (i + 1) % n
        f = xs[i] * ys[j] - xs[j] * ys[i]
        a, cx, cy = a + f, cx + (xs[i] + xs[j]) * f, cy + (ys[i] + ys[j]) * f
    if abs(a) < 1e-9:
        return None
    cx, cy = cx / (3 * a), cy / (3 * a)
    inside = False
    for i in range(n):
        j = i - 1
        if (ys[i] > cy) != (ys[j] > cy) and cx < (xs[j] - xs[i]) * (cy - ys[i]) / ((ys[j] - ys[i]) or 1e-9) + xs[i]:
            inside = not inside
    if inside:
        return cx, cy
    k = min(range(n), key=lambda i: (xs[i] - cx) ** 2 + (ys[i] - cy) ** 2)
    return xs[k], ys[k]


def _areas_of(body):
    end = re.search(r"(?m)^\s*desc\b|</imagemap>", body)
    body = body[:end.start()] if end else body
    orte, seen = [], set()
    for kind, coords, target, label in _AREA_LINE.findall(body):
        try:
            cs = [float(c) for c in re.split(r"[\s,]+", coords.strip()) if c]
        except ValueError:
            continue
        if kind == "circle" and len(cs) >= 3:
            x0, y0, x1, y1 = cs[0] - cs[2], cs[1] - cs[2], cs[0] + cs[2], cs[1] + cs[2]
        elif len(cs) >= 4:
            xs, ys = cs[0::2], cs[1::2]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        else:
            continue
        name = re.sub(r"\s+\((Kalos|Alola|Hoenn|Einall|Sinnoh)\)$", "", " ".join(target.split()))
        if not name or name in seen:
            continue
        seen.add(name)
        o = {"name": name[:120], "x": x0, "y": y0, "w": max(1.0, x1 - x0), "h": max(1.0, y1 - y0),
             "seite": "https://www.pokewiki.de/" + urllib.parse.quote(target.strip().replace(" ", "_"))}
        c = _centre(cs, kind)
        if c:
            o["cx"], o["cy"] = c
        orte.append(o)
    return orte


def pw_map(orte, small, big=None):
    """Orte der kleinen PokéWiki-Karte und die Bilder (url, w, h) → Daten wie extract. Das große Bild nur, wenn es
    dasselbe Seitenverhältnis hat (höchstens 2 % Abweichung); die Orte werden dann hochgerechnet."""
    if not orte or not small:
        return None
    url, w, h = small
    if big and big[1] > w and abs(big[1] / big[2] - w / h) <= 0.02 * (w / h):
        fx, fy = big[1] / w, big[2] / h
        orte = [dict(o, x=o["x"] * fx, y=o["y"] * fy, w=o["w"] * fx, h=o["h"] * fy,
                     **({"cx": o["cx"] * fx, "cy": o["cy"] * fy} if "cx" in o else {})) for o in orte]
        url, w, h = big
    return {"bild": url, "w": w, "h": h, "orte": orte, "quelle": "PokéWiki"}


def parse(d, region, teil=None):
    """Daten einer Regionsseite → Karte wie mapgenie.parse mit einem Bild (bilder [[0, 0, 0, w, h, Datei]]) oder None.
    teil: (Kennung, Titel) eines Teils der Region (Insel in Alola), sonst die ganze Region."""
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
        la, lo = ll(o["cx"], o["cy"]) if "cx" in o else ll(o["x"] + o["w"] / 2, o["y"] + o["h"] / 2)
        n, w = ll(o["x"], o["y"])
        s, e = ll(o["x"] + o["w"], o["y"] + o["h"])
        cat = 2 if re.search(r"\b(Route|Road|Path|Sea|Water|Weg|Pfad|Straße)\b", o["name"]) else 1
        orte.append([45_000_000 + len(orte), cat, la, lo, o["name"], ""])
        gebiete.append([o["name"], w, s, e, n])
    n0, w0 = ll(0, 0)
    s0, e0 = ll(W, H)
    cats = [{"id": 1, "titel": "Städte und Orte", "icon": "", "n": sum(1 for o in orte if o[1] == 1)},
            {"id": 2, "titel": "Routen", "icon": "", "n": sum(1 for o in orte if o[1] == 2)}]
    gebiete.sort(key=lambda g: g[0].lower())
    key = region + ("-" + teil[0] if teil else "")
    name = REGION.get(region, region.title()) + (": " + teil[1] if teil else "")
    return {"id": 0, "slug": "se-" + key, "titel": f"{name} ({d.get('quelle') or 'Serebii'})", "quelle": "pokearth",
            "kacheln": "", "endung": ext, "kachel": TILE, "dim": {"w": W, "h": H}, "min_zoom": z1, "max_zoom": z1 + ZOOM_IN,
            "bild_z": z1, "bounds": [w0, s0, e0, n0], "region": region,
            "gruppen": [{"id": 910, "titel": "Orte der Region", "farbe": "#e0a040", "kategorien": cats}],
            "orte": orte, "gebiete": gebiete, "bilder": [[0, 0, 0, W, H, f"se/{key}.{ext}"]]}


def pw_islands(wt, region):
    """0.56: Orte je Insel aus einer Vorlage mit mehreren Bildkarten → [(Kennung, Titel, Bilddatei, Orte)]. Flächen, die
    auf eine andere Insel verweisen (Pfeile zur Nachbarinsel), fallen weg."""
    cfg = PW_MAPS.get(region) or {}
    maps = pw_imagemaps(wt)
    names = {t for _, t, _ in cfg.get("inseln", ())}
    out = []
    for key, title, f in cfg.get("inseln", ()):
        orte = [o for o in maps.get(f, []) if o["name"] not in names and not o["name"].startswith(("Kategorie:", "{{"))]
        if orte:
            out.append((key, title, f, orte))
    return out


def tile(m, z, x, y):
    """Keine Kacheln: die Karte ist ein Bild (siehe abruf.mg_image)."""
    return None


def tile_list(m, top=None):
    return []
