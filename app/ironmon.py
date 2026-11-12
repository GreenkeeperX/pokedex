"""Karten von HeartGold/SoulSilver aus der HGSS IronMON Map (GitHub, MIT) lesen, ohne Netz (den Abruf macht
abruf._ironmon).

Das Projekt hat je Region ein großes Bild der ganzen Welt mit allen Häusern und Höhlen (WebP, Johto 13712×5893) und
Punkte in TypeScript-Dateien: Trainer (Name mit Klasse, Zahl und Level der Pokémon) und Items (sichtbar, versteckt,
TM), je mit x/y in Bildpixeln. Ein Kommentar vor den Punkten nennt den Ort („// Rt 30“), darunter das Stockwerk
(„// 2F“). Daraus wird eine Karte wie bei Serebii PokéEarth: das Bild als eine Bildebene und Punkte; je Ort zusätzlich
ein Punkt in der Mitte seiner Trainer und Items (darüber kommen die Pokémon des Orts, abfragen._pokearth_mons).

Das Bild ist zu groß, um es bei jedem Öffnen zu laden, und ohne Zusatzbibliothek lässt sich WebP nicht zerlegen. Deshalb
wandelt der Browser es beim ersten Öffnen einmal in Kacheln um und legt sie auf dem Server ab (abruf.tile_upload);
danach lädt die Karte wie jede andere nur die Kacheln, die sie zeigt.
"""
import math
import re

from . import mapgenie

BASE = "https://raw.githubusercontent.com/kelseyyoung/HGSSIronmonMap/main/src/"
TILE = 256
GAMES = {"heartgold-soulsilver": ("johto", "kanto")}
REGION = {"johto": "Johto", "kanto": "Kanto"}
FILES = {"johto": ("assets/FullJohto.webp", "data/trainers.ts", "data/items.ts"),
         "kanto": ("assets/FullKanto.webp", "data/kantoTrainers.ts", "data/kantoItems.ts")}
# Kommentare, die kein Ort sind, sondern ein Teil davon (Stockwerk, Abschnitt)
_SUB = re.compile(r"^(B?\d+F|\d+F|Statue \d+|North|South|East|West|Inside|Outside|After .*|Before .*|Floor .*|Room .*|"
                  r"Basement.*|Roof|Top|Bottom|Upper|Lower)$", re.I)
# Trainerklassen (englisch, wie dort geschrieben) → deutsch; unbekannte bleiben, wie sie sind
KLASSEN = {"Team Rocket Grunt": "Rocket-Rüpel", "Team Rocket": "Team Rocket", "Rocket Grunt": "Rocket-Rüpel",
           "Swimmer": "Schwimmer", "Swmimmer": "Schwimmer", "Ace Trainer": "Ass-Trainer", "Bird Keeper": "Vogelfänger",
           "Fisherman": "Angler", "Hiker": "Wanderer", "Camper": "Camper", "Biker": "Rowdy", "School Kid": "Schüler",
           "Picnicker": "Picknickerin", "Picknicker": "Picknickerin", "Bug Catcher": "Käfersammler", "Pokéfan": "Pokéfan",
           "Youngster": "Knirps", "Lass": "Göre", "Super Nerd": "Supernerd", "Sailor": "Matrose", "Psychic": "Psycho",
           "Scientist": "Forscher", "Firebreather": "Feuerspucker", "Black Belt": "Schwarzgurt", "Twins": "Zwillinge",
           "Poké Maniac": "Pokémaniac", "PokéManiac": "Pokémaniac", "Beauty": "Schönheit", "Sage": "Weiser",
           "Medium": "Medium", "Executive": "Rocket-Vorstand", "Boarder": "Snowboarder", "Young Couple": "Junges Paar",
           "Gentleman": "Gentleman", "Teacher": "Lehrerin", "Skier": "Skifahrerin", "Juggler": "Jongleur",
           "Double Team": "Doppelteam", "Policeman": "Polizist", "Burglar": "Einbrecher", "Guitarist": "Gitarrist",
           "Elder": "Ältester", "Kimono Girl": "Kimono-Girl", "Rival": "Rivale", "Gym Leader": "Arenaleiter",
           "Elite Four": "Top Vier", "Champion": "Champ", "Leader": "Arenaleiter"}
ITEM_ART = {"Normal": (3, "Item"), "Hidden": (4, "Verstecktes Item"), "TM": (5, "TM")}


def urls(region):
    """Adressen (Bild, Trainer, Items) einer Region."""
    return tuple(BASE + f for f in FILES[region])


def webp_size(b):
    """Breite und Höhe eines WebP-Bilds aus seinem Kopf (VP8, VP8L, VP8X) oder None."""
    if len(b or b"") < 30 or b[:4] != b"RIFF" or b[8:12] != b"WEBP":
        return None
    c = b[12:16]
    if c == b"VP8X":
        return int.from_bytes(b[24:27], "little") + 1, int.from_bytes(b[27:30], "little") + 1
    if c == b"VP8L" and b[20] == 0x2F:
        v = int.from_bytes(b[21:25], "little")
        return (v & 0x3FFF) + 1, ((v >> 14) & 0x3FFF) + 1
    if c == b"VP8 " and b[23:26] == b"\x9d\x01\x2a":
        return int.from_bytes(b[26:28], "little") & 0x3FFF, int.from_bytes(b[28:30], "little") & 0x3FFF
    return None


def objects(ts):
    """Punkte einer TypeScript-Datei → [{ort, teil, felder…}]. Auskommentierte Punkte und solche ohne Lage fallen weg."""
    out, ort, teil, obj, depth = [], "", "", None, 0
    for raw in (ts or "").splitlines():
        ln = raw.strip()
        if ln.startswith("//"):
            c = ln[2:].strip()
            if obj is not None or not c or re.search(r"[:{}\[\]]|TODO", c):
                continue                         # Kommentar im Punkt, auskommentierter Code, Notiz
            if _SUB.match(c):
                teil = c
            else:
                ort, teil = c, ""
            continue
        if obj is None:
            if ln.startswith("{"):
                obj, depth = {}, 0
            else:
                continue
        depth += ln.count("{") - ln.count("}")
        for k, v in re.findall(r"(\w+)\s*:\s*(\"[^\"]*\"|\[[^\]]*\]|[\w.-]+)", ln):
            if v.startswith('"'):
                obj[k] = v[1:-1]
            elif v.startswith("["):
                obj[k] = [int(x) for x in re.findall(r"-?\d+", v)]
            elif re.fullmatch(r"-?\d+(\.\d+)?", v):
                obj[k] = float(v) if "." in v else int(v)
            else:
                obj[k] = v.rsplit(".", 1)[-1]
        if depth <= 0:
            if isinstance(obj.get("x"), (int, float)) and isinstance(obj.get("y"), (int, float)) and (obj["x"] or obj["y"]):
                obj.update(ort=ort, teil=teil)
                out.append(obj)
            obj = None
    return out


def ort_name(s):
    """„Rt 30“ → „Route 30“; sonst wie dort."""
    return re.sub(r"^Rt\.?\s*(\d+)", r"Route \1", (s or "").strip())


def trainer_name(s):
    """„Bug Catcher Wade“ → „Käfersammler Wade“ (längste bekannte Klasse vorn)."""
    s = (s or "").strip()
    for k in sorted(KLASSEN, key=len, reverse=True):
        if s == k or s.startswith(k + " "):
            return KLASSEN[k] + s[len(k):]
    return s


def parse(region, w, h, trainers, items, ext="webp"):
    """Bildgröße und Punkte einer Region → Karte wie mapgenie.parse mit einem Bild (bilder [[0, 0, 0, w, h, Datei]])."""
    if not (w and h) or not (trainers or items):
        return None
    z1 = max(0, math.ceil(math.log2(max(w, h) / TILE)))
    ll = lambda x, y: tuple(round(v, 6) for v in mapgenie.unproject(x, y, z1))
    orte, sammel, base = [], {}, 46_000_000 + (0 if region == "johto" else 500_000)
    for t in trainers:
        lv = t.get("pokemonLevels") or []
        lines = [f"**Ort:** {ort_name(t['ort'])}" + (f" ({t['teil']})" if t["teil"] else "")] if t["ort"] else []
        if lv:
            lines.append(f"**Pokémon:** {len(lv)}, Level {', '.join(str(x) for x in lv)}")
        la, lo = ll(t["x"], t["y"])
        orte.append([base + len(orte), 2, la, lo, trainer_name(t.get("name")) or "Trainer", "\n".join(lines)])
        sammel.setdefault(ort_name(t["ort"]), []).append((t["x"], t["y"]))
    for it in items:
        cat, titel = ITEM_ART.get(it.get("type"), (3, "Item"))
        la, lo = ll(it["x"], it["y"])
        ort = ort_name(it["ort"])
        orte.append([base + len(orte), cat, la, lo, titel, f"**Ort:** {ort}" + (f" ({it['teil']})" if it["teil"] else "") if ort else ""])
        sammel.setdefault(ort, []).append((it["x"], it["y"]))
    for name, ps in sammel.items():
        if not name:
            continue
        x, y = sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps)
        la, lo = ll(x, y)
        orte.append([base + len(orte), 1, la, lo, name, ""])
    n0, w0 = ll(0, 0)
    s0, e0 = ll(w, h)
    count = lambda c: sum(1 for o in orte if o[1] == c)
    return {"id": 0, "slug": "im-" + region, "titel": f"{REGION.get(region, region.title())} (ganze Welt)", "quelle": "ironmon",
            "kacheln": "", "endung": "png", "kachel": TILE, "dim": {"w": w, "h": h}, "min_zoom": max(0, z1 - 4), "max_zoom": z1,
            "bild_z": z1, "bounds": [w0, s0, e0, n0], "region": region,
            "gruppen": [{"id": 920, "titel": "Orte", "farbe": "#e0a040",
                         "kategorien": [{"id": 1, "titel": "Orte", "icon": "", "n": count(1)}]},
                        {"id": 921, "titel": "Trainer und Items", "farbe": "#5b8fc7",
                         "kategorien": [{"id": c, "titel": t, "icon": "", "n": count(c)}
                                        for c, t in ((2, "Trainer"), (3, "Items"), (4, "Versteckte Items"), (5, "TM"))]}],
            "orte": orte, "gebiete": [], "quellbild": [0, 0, 0, w, h, f"im/{region}.{ext}"]}


def tile_range(m, z):
    """Zahl der Kacheln (Spalten, Zeilen) auf Stufe z oder None außerhalb der Stufen."""
    if not (m["min_zoom"] <= z <= m["max_zoom"]):
        return None
    span = TILE * 2 ** (m["bild_z"] - z)
    return math.ceil(m["dim"]["w"] / span), math.ceil(m["dim"]["h"] / span)


def tile(m, z, x, y):
    """(Pfad im Datenordner, None) einer Kachel: es gibt keine Adresse, der Browser hat sie umgewandelt. None außerhalb."""
    r = tile_range(m, z)
    if not r or not (0 <= x < r[0] and 0 <= y < r[1]):
        return None
    return f"im/{m['region']}/{int(z)}/{int(x)}-{int(y)}.png", None


def tile_list(m, top=None):
    return []
