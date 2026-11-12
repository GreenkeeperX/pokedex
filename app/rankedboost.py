"""Megakarten von RankedBoost lesen, ohne Netz (den Abruf macht abruf._rankedboost).

Die Fundortseite (/pokemon/location/<Spiel>/) nennt eine JSON-Datei im Cache des CDN (megamap-<Spiel>-<Prüfsumme>.json). Darin
steht unter "megaMap" als Text die ganze Welt: bounds {x, y, w, h} und je Ort ein Bild (webp) mit Lage und Größe in
denselben Pixeln, dazu Name, Art, Level und je Fangart (methods: l = Bezeichnung, s = Sprites) die Pokémon. Kacheln
gibt es nicht: die Karte zeigt die Ortsbilder an ihrer Stelle (der Server legt sie ab, der Browser zeichnet sie).
"""
import json
import math
import re
import urllib.parse

from . import mapgenie

BASE = "https://rankedboost.com/"
CDN = "https://img.rankedboost.com"
# Karmesin/Purpur und Z-A nicht (0.43.0): dort liegen die Ortsbilder in mehreren Regionen übereinander und Map Genie
# hat die bessere Karte
GAMES = {"lets-go-pikachu-lets-go-eevee": "lets-go-pikachu-eevee", "firered-leafgreen": "fire-red-leaf-green"}   # Spiel → Kennung
TITEL = {"lets-go-pikachu-lets-go-eevee": "Kanto (RankedBoost)", "firered-leafgreen": "Kanto und Sevii-Inseln (RankedBoost)",
         "scarlet-violet": "Paldea (RankedBoost)", "legends-za": "Illumina City (RankedBoost)"}
TILE = 256
LEVELS = 4                  # so viele Stufen weiter weg als die volle Auflösung
_JSON = re.compile(r"https?://img\.rankedboost\.com/wp-content/plugins/k-Pokemon/assets/cache/megamap-[a-z0-9-]+\.json")
METHODE = {"grass": "Gras", "walk": "Gras", "walking": "Gras", "surf": "Surfer", "surfing": "Surfer", "old rod": "Angel",
           "good rod": "Profiangel", "super rod": "Superangel", "fishing": "Angeln", "rock smash": "Zertrümmerer",
           "gift": "Geschenk", "static": "fest", "trade": "Tausch", "cave": "Höhle", "special": "besonders"}


PAGES = {"lets-go-pikachu-lets-go-eevee": ("pokemon/location/letsgo-pikachu-eevee/", "pokemon-lets-go-pikachu-eevee/map/"),
         "firered-leafgreen": ("pokemon/location/firered-leafgreen/", "pokemon/location/fire-red-leaf-green/", "pokemon-fire-red-leaf-green/map/"),
         "scarlet-violet": ("pokemon/location/scarlet-violet/", "pokemon-scarlet-violet/map/"),
         "legends-za": ("pokemon/location/legends-z-a/", "pokemon-legends-z-a/map/")}
# zuletzt gesehene Adressen der Kartendaten (die Prüfsumme wechselt mit jedem Stand; erst die Seite, dann diese)
KNOWN = {"lets-go-pikachu-lets-go-eevee": CDN + "/wp-content/plugins/k-Pokemon/assets/cache/megamap-lets-go-pikachu-eevee-791ae0729e4a.json",
         "firered-leafgreen": CDN + "/wp-content/plugins/k-Pokemon/assets/cache/megamap-fire-red-leaf-green-84d92005e6ed.json",
         "scarlet-violet": CDN + "/wp-content/plugins/k-Pokemon/assets/cache/megamap-scarlet-violet-ca85664731f4.json"}


def page_urls(spiel):
    """Seiten, die die Adresse der Kartendaten nennen können, in dieser Reihenfolge."""
    return [BASE + p for p in PAGES.get(spiel, ())]


def json_url(page):
    """Adresse der Kartendaten aus der Spielseite, None ohne."""
    m = _JSON.search(page or "")
    return m.group(0) if m else None


def extract(text):
    """Antwort der JSON-Datei → Kartendaten (dict) oder None."""
    try:
        d = json.loads(text or "")
    except ValueError:
        return None
    mm = d.get("megaMap") if isinstance(d, dict) else None
    if isinstance(mm, str):
        try:
            mm = json.loads(mm)
        except ValueError:
            return None
    return mm if isinstance(mm, dict) and isinstance(mm.get("maps"), list) else None


def image_ok(url):
    """Nur Ortsbilder vom CDN (oder relativ dazu) als Adresse; sonst None."""
    u = urllib.parse.urljoin(CDN + "/", str(url or ""))
    p = urllib.parse.urlsplit(u)
    if p.scheme == "https" and p.netloc == "img.rankedboost.com" and re.fullmatch(r"/wp-content/plugins/k-Pokemon/assets/[\w/.-]+\.(webp|png|jpg)", p.path):
        return u
    return None


def mon_name(sprite):
    """Sprite → englischer Name der Art (aus dem Dateinamen: …/bulbasaur.png → Bulbasaur)."""
    if isinstance(sprite, dict):
        sprite = sprite.get("n") or sprite.get("name") or sprite.get("s") or ""
    base = re.sub(r"\.[a-z]+$", "", str(sprite).rsplit("/", 1)[-1])
    base = re.sub(r"[-_](icon|sprite|small|mini|\d+x\d+)$", "", base, flags=re.I)
    words = [w for w in re.split(r"[-_ ]+", base) if w]
    return " ".join(w[:1].upper() + w[1:] for w in words)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse(d, spiel):
    """Kartendaten → (Karte wie mapgenie.parse, Bilder [[Nr, Adresse, x, y, w, h]]) oder (None, None). Je Ort ein Punkt
    in der Mitte seines Bilds mit den Pokémon je Fangart; die Ortsbilder liegen in Pixeln der Welt bei Stufe z1."""
    if not d:
        return None, None
    b = d.get("bounds") or {}
    bx, by, W, H = (_num(b.get(k)) for k in ("x", "y", "w", "h"))
    if not (W and H) or bx is None or by is None:
        return None, None
    z1 = max(0, math.ceil(math.log2(max(W, H) / TILE)))
    ll = lambda x, y: tuple(round(v, 6) for v in mapgenie.unproject(x, y, z1))
    cats, orte, bilder, gebiete = {}, [], [], []

    def cat(titel):
        if titel not in cats:
            cats[titel] = {"id": len(cats) + 1, "titel": titel, "icon": "", "n": 0}
        return cats[titel]["id"]
    for o in d.get("maps") or []:
        if not isinstance(o, dict):
            continue
        x, y, w, h = (_num(o.get(k)) for k in ("x", "y", "w", "h"))
        if None in (x, y, w, h) or w <= 0 or h <= 0:
            continue
        x, y = x - bx, y - by
        url = image_ok(o.get("url"))
        if url:
            bilder.append([len(bilder), url, round(x, 1), round(y, 1), round(w, 1), round(h, 1)])
        name = str(o.get("name") or o.get("slug") or "")[:120]
        if not name:
            continue
        n, wl = ll(x, y)
        s, e = ll(x + w, y + h)
        gebiete.append([name, wl, s, e, n])
        lines = []
        lv = "–".join(str(v) for v in dict.fromkeys(v for v in (o.get("minLv"), o.get("maxLv")) if v not in (None, "", 0)))
        for mt in o.get("methods") or []:
            if not isinstance(mt, dict):
                continue
            mons = [mon_name(s) for s in mt.get("s") or []]
            mons = [m for m in dict.fromkeys(mons) if m]
            if mons:
                label = str(mt.get("l") or "").strip()
                lines.append(f"{METHODE.get(label.lower(), label) or 'Pokémon'}: " + ", ".join(f"«{m}»" for m in mons))
        if not lines and not o.get("pk"):
            continue
        if lv:
            lines.append(f"Level {lv}")
        art = str(o.get("type") or "").strip().lower()
        la, lo = ll(x + w / 2, y + h / 2)
        orte.append([40_000_000 + len(orte), cat("Höhlen und Gebäude" if art in ("cave", "building", "dungeon", "interior") else "Orte und Routen"),
                     la, lo, name, "\n".join(lines)[:1500]])
    if not bilder and not orte:
        return None, None
    for c in cats.values():
        c["n"] = sum(1 for o in orte if o[1] == c["id"])
    n0, w0 = ll(0, 0)
    s0, e0 = ll(W, H)
    gebiete.sort(key=lambda g: g[0].lower())
    m = {"id": 0, "slug": "rb-" + GAMES.get(spiel, spiel), "titel": TITEL.get(spiel, spiel), "quelle": "rankedboost", "kacheln": "",
         "endung": "webp", "kachel": TILE, "dim": {"w": W, "h": H}, "min_zoom": z1 - LEVELS, "max_zoom": z1 + 1, "bild_z": z1,
         "bounds": [w0, s0, e0, n0], "gruppen": [{"id": 900, "titel": "Orte mit Pokémon", "farbe": "#4fbf8f", "kategorien": list(cats.values())}],
         "orte": orte, "gebiete": gebiete}
    return m, bilder


def tile(m, z, x, y):
    """Keine Kacheln: die Karte zeigt Ortsbilder (siehe abruf.mg_image)."""
    return None


def tile_list(m, top=None):
    return []
