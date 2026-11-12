"""Raid-Nester in Schwert/Schild (Naturzone, Insel der Rüstung, Schneelande der Krone) aus dem PKHeX Raid Plugin
(GitHub) lesen, ohne Netz (den Abruf macht abruf._raidnester).

Nests/NestLocations.cs nennt je Nest das Gebiet (Nummer in LocationNames aus Raid/RaidParameters.cs) und x/y in den
Pixeln der Karte seines Teils: Gebiete 0–16 Naturzone (map.png), 17–31 Insel der Rüstung (map_ioa.png), ab 32
Schneelande (map_02.png). Daraus wird je Teil eine Bildkarte wie bei Serebii PokéEarth: das Bild als eine Bildebene,
je Nest ein Punkt, je Gebiet ein Punkt in der Mitte seiner Nester. Für die Insel der Rüstung und die Schneelande ist
das die erste eigene Karte (sonst zeigen sie Galar).
(pkTeraRaid hat dieselben Nester, aber in den Schneelanden auf falsche Pixel umgerechnet.)
"""
import math
import re

from . import mapgenie

BASE = "https://raw.githubusercontent.com/Leanny/PKHeX_Raid_Plugin/master/PKHeX_Raid_Plugin/"
NESTS = BASE + "Nests/NestLocations.cs"
NAMES = BASE + "Raid/RaidParameters.cs"
TILE = 256
# Teil → (Spiel, Bild, Titel, erstes Gebiet)
AREAS = {"wa": ("sword-shield", "Resources/map.png", "Naturzone (Raid-Nester)", 0),
         "ioa": ("the-isle-of-armor", "Resources/map_ioa.png", "Insel der Rüstung (Raid-Nester)", 17),
         "ct": ("the-crown-tundra", "Resources/map_02.png", "Schneelande der Krone (Raid-Nester)", 32)}
GAMES = tuple(dict.fromkeys(a[0] for a in AREAS.values()))


def png_size(b):
    """Breite und Höhe eines PNG-Bilds aus seinem Kopf oder None."""
    if len(b or b"") < 24 or b[:8] != b"\x89PNG\r\n\x1a\n" or b[12:16] != b"IHDR":
        return None
    return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")


def area_of(loc):
    """Teil eines Gebiets (Nummer) → Kürzel."""
    return max((a for a, v in AREAS.items() if loc >= v[3]), key=lambda a: AREAS[a][3])


def location_names(cs):
    """RaidParameters.cs → [Gebietsname] (englisch, in der Reihenfolge der Nummern)."""
    m = re.search(r"LocationNames\s*=\s*[\[{](.*?)[\]}]\s*;", cs or "", re.S)
    return re.findall(r"\"([^\"]*)\"", m.group(1)) if m else []


def nests(cs, names=()):
    """NestLocations.cs → [(Teil, x, y, Gebietsname)]; auskommentierte Zeilen zählen nicht."""
    out = []
    for ln in (cs or "").splitlines():
        m = re.match(r"\s*new\s+NestHashDetail\(\s*0x[0-9a-fA-F]+\s*,\s*0x[0-9a-fA-F]+\s*,\s*(\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\)", ln)
        if m:
            loc, x, y = (int(v) for v in m.groups())
            out.append((area_of(loc), x, y, names[loc] if loc < len(names) else ""))
    return out


def parse(ns, area, w, h):
    """Nester eines Teils und die Größe seines Bilds → Karte wie mapgenie.parse mit einem Bild oder None."""
    ns = [n for n in ns or [] if n[0] == area]
    if not ns or not (w and h):
        return None
    z1 = max(0, math.ceil(math.log2(max(w, h) / TILE)))
    ll = lambda x, y: tuple(round(v, 6) for v in mapgenie.unproject(x, y, z1))
    base = 47_000_000 + 1000 * list(AREAS).index(area)
    orte, mitte = [], {}
    for i, (_, x, y, ort) in enumerate(ns):
        la, lo = ll(x, y)
        orte.append([base + i, 1, la, lo, f"Raid-Nest {i + 1}", f"**Ort:** {ort}" if ort else ""])
        mitte.setdefault(ort, []).append((x, y))
    for ort, ps in mitte.items():
        if ort:
            la, lo = ll(sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps))
            orte.append([base + 500 + len(orte), 2, la, lo, ort, ""])
    n0, w0 = ll(0, 0)
    s0, e0 = ll(w, h)
    return {"id": 0, "slug": "rn-" + area, "titel": AREAS[area][2], "quelle": "raidnester", "kacheln": "", "endung": "png",
            "kachel": TILE, "dim": {"w": w, "h": h}, "min_zoom": max(0, z1 - 2), "max_zoom": z1 + 1, "bild_z": z1,
            "bounds": [w0, s0, e0, n0], "region": area,
            "gruppen": [{"id": 930, "titel": "Orte und Raid-Nester", "farbe": "#c0508a",      # „Orte …“: gleich sichtbar
                         "kategorien": [{"id": 1, "titel": "Raid-Nester", "icon": "", "n": len(ns)},
                                        {"id": 2, "titel": "Gebiete", "icon": "", "n": len(orte) - len(ns)}]}],
            "orte": orte, "gebiete": [], "bilder": [[0, 0, 0, w, h, f"rn/{area}.png"]]}


def tile(m, z, x, y):
    """Keine Kacheln: die Karte ist ein Bild (siehe abruf.mg_image)."""
    return None


def tile_list(m, top=None):
    return []
