"""Raid-Nester in Schwert/Schild (Naturzone, Insel der Rüstung, Schneelande der Krone) aus dem PKHeX Raid Plugin
(GitHub) lesen, ohne Netz (den Abruf macht abruf._raidnester).

Nests/NestLocations.cs nennt je Nest das Gebiet (Nummer in LocationNames aus Raid/RaidParameters.cs) und x/y in den
Pixeln der Karte seines Teils: Gebiete 0–16 Naturzone (map.png), 17–31 Insel der Rüstung (map_ioa.png), ab 32
Schneelande (map_02.png). Daraus wird je Teil eine Bildkarte wie bei Serebii PokéEarth: das Bild als eine Bildebene,
je Nest ein Punkt, je Gebiet ein Punkt in der Mitte seiner Nester. Für die Insel der Rüstung und die Schneelande ist
das die erste eigene Karte (sonst zeigen sie Galar).
Nests/RaidTables.cs nennt je Tabelle (Schlüssel wie in NestLocations.cs: normaler und seltener Strahl) die Pokémon
für Schwert und für Schild mit Sternen, Form und Gigadynamax; das steht in jedem Nest (seit 0.47).
(pkTeraRaid hat dieselben Nester, aber in den Schneelanden auf falsche Pixel umgerechnet.)
"""
import math
import re

from . import mapgenie

BASE = "https://raw.githubusercontent.com/Leanny/PKHeX_Raid_Plugin/master/PKHeX_Raid_Plugin/"
NESTS = BASE + "Nests/NestLocations.cs"
NAMES = BASE + "Raid/RaidParameters.cs"
TABLES = BASE + "Nests/RaidTables.cs"
# Formen, die im Nest vorkommen: (Art, Form) → Zusatz; sonst „Form n“
FORMS = {**{(a, 1): "Galar-Form" for a in (77, 78, 79, 80, 83, 110, 122, 144, 145, 146, 199, 222, 263, 264, 554, 562, 618)},
         (52, 2): "Galar-Form", (555, 2): "Galar-Form", (52, 1): "Alola-Form", (422, 1): "Ostmeer", (423, 1): "Ostmeer",
         (849, 1): "Tief-Form", (869, 0): ""}
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
    """NestLocations.cs → [(Teil, x, y, Gebietsname, Schlüssel normal, Schlüssel selten)]; auskommentierte Zeilen zählen nicht."""
    out = []
    for ln in (cs or "").splitlines():
        m = re.match(r"\s*new\s+NestHashDetail\(\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*,\s*(\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\)", ln)
        if m:
            loc, x, y = (int(v) for v in m.groups()[2:])
            out.append((area_of(loc), x, y, names[loc] if loc < len(names) else "", int(m.group(1), 16), int(m.group(2), 16)))
    return out


_TPL = re.compile(r"new\s+RaidTemplate\(\s*(\d+)\s*,\s*new\s*\[\]\s*\{([^}]*)\}\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,"
                  r"\s*(?:(-?\d+)\s*,\s*)?(true|false)")


def tables(cs):
    """RaidTables.cs → {"sw": {Schlüssel: [(Art, Form, Sterne von, bis, Gigadynamax)]}, "sh": {…}} (ohne Event-Tabellen)."""
    out = {}
    for key, name in (("sw", "SwordNests"), ("sh", "ShieldNests")):
        m = re.search(name + r"\s*=\s*\{(.*?)\n\s*\};", cs or "", re.S)
        tabs = out[key] = {}
        for t in re.split(r"new\s+RaidTemplateTable\(", m.group(1) if m else "")[1:]:
            h = re.match(r"\s*(0x[0-9a-fA-F]+)", t)
            if not h:
                continue
            rows = []
            for x in _TPL.finditer(t):
                probs = [int(v.strip().rstrip("uU") or 0) for v in x.group(2).split(",")]
                stars = [i + 1 for i, v in enumerate(probs) if v]
                if stars:
                    rows.append((int(x.group(1)), int(x.group(4)), stars[0], stars[-1], x.group(8) == "true"))
            tabs[int(h.group(1), 16)] = rows
    return out


def den_text(tabs, common, rare, names):
    """Text eines Nests: je Strahl und Spiel die Pokémon mit Sternen (Name (Form, 1–3★, Gigadynamax)); gleich in beiden
    Spielen: einmal für „Schwert und Schild“. names: {Art: Name}."""
    def line(key, h):
        seen, parts = set(), []
        for art, form, a, b, giga in (tabs or {}).get(key, {}).get(h) or []:
            if not names.get(art) or (art, form, giga) in seen:
                continue
            seen.add((art, form, giga))
            extra = [x for x in (FORMS.get((art, form), f"Form {form}" if form else ""), f"{a}–{b}★" if a != b else f"{a}★",
                                 "Gigadynamax" if giga else "") if x]
            parts.append(f"{names[art]} ({', '.join(extra)})")
        return ", ".join(parts)
    out = []
    for h, beam in ((common, ""), (rare, ", seltener Strahl")):
        sw, sh = line("sw", h), line("sh", h)
        for game, txt in ([("Schwert und Schild", sw)] if sw == sh else [("Schwert", sw), ("Schild", sh)]):
            if txt:
                out += [f"**{game}{beam}:**", txt]
    return "\n".join(out)


def parse(ns, area, w, h, tabs=None, names=None):
    """Nester eines Teils und die Größe seines Bilds → Karte wie mapgenie.parse mit einem Bild oder None;
    mit tabs (tables) und names ({Art: deutscher Name}) steht im Nest, welche Pokémon dort erscheinen."""
    ns = [n for n in ns or [] if n[0] == area]
    if not ns or not (w and h):
        return None
    z1 = max(0, math.ceil(math.log2(max(w, h) / TILE)))
    ll = lambda x, y: tuple(round(v, 6) for v in mapgenie.unproject(x, y, z1))
    base = 47_000_000 + 1000 * list(AREAS).index(area)
    orte, mitte = [], {}
    for i, (_, x, y, ort, *hs) in enumerate(ns):
        la, lo = ll(x, y)
        den = den_text(tabs, *hs, names or {}) if tabs and len(hs) == 2 else ""
        orte.append([base + i, 1, la, lo, f"Raid-Nest {i + 1}", "\n".join(t for t in (f"**Ort:** {ort}" if ort else "", den) if t)])
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
