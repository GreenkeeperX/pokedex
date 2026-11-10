"""Legenden: Arceus aus den Seiten von Altissimo (altissimo1.github.io, GPL-3.0), ohne Netz gelesen:

- Kartensymbole: Bäume, Erzbrocken, Laub- und Heuhaufen, Kisten (Landmarks/json/<Gebiet>-spawns.json)
- Sammelobjekte: Irrlichter, Icognito, alte Verse, Grabstellen (Collectibles/json/<Gebiet>.json), auch in Jubeldorf
- Rezepte zum Herstellen mit Zutaten (recipes.html)

Altissimo gibt die Lage in Prozent seines Kartenbilds an. FIT rechnet sie in Spielkoordinaten um wie die Spawnpunkte
(JS-Finder): die Geraden sind aus den 1213 Bäumen und Erzbrocken bestimmt, die in beiden Quellen stehen (Abweichung
unter 0,1 %). Jubeldorf hat keine Spawnpunkte; dort gilt das Kartenbild von Altissimo selbst (100 % = 1024).
"""
import html
import json
import re

BASE = "https://raw.githubusercontent.com/Altissimo1/altissimo1.github.io/main/"
PLA = BASE + "Supplementary-Series/Legends/Legends-Arceus/"
VILLAGE = "jubilifevillage"
VILLAGE_NAME = "Jubeldorf"
VILLAGE_IMAGE = BASE + "Resources/images/pla-icons/Jubilife/map.png"
# Karte (wie PLA_MAPS in abruf) → Name der Dateien bei Altissimo
AREAS = {"obsidianfieldlands": "fieldlands", "crimsonmirelands": "mirelands", "cobaltcoastlands": "coastlands",
         "coronethighlands": "highlands", "alabastericelands": "icelands"}
# Prozent = a · Spielkoordinate + b, je Achse (x, z)
FIT = {"obsidianfieldlands": (0.09778, -1.3062, 0.09708, -1.3662),
       "crimsonmirelands": (0.09744, -1.1739, 0.09745, -1.4446),
       "cobaltcoastlands": (0.09775, -1.4611, 0.09752, -1.5754),
       "coronethighlands": (0.09719, -1.3154, 0.09689, -1.2523),
       "alabastericelands": (0.09812, -1.6874, 0.09718, -1.4266)}
GEBIETE = {VILLAGE: VILLAGE_NAME, "obsidianfieldlands": "Obsidian-Grasland", "crimsonmirelands": "Rotes Sumpfland",
           "cobaltcoastlands": "Kobalt-Küstenland", "coronethighlands": "Kraterberg-Hochland",
           "alabastericelands": "Weißes Frostland"}
VILLAGE_FIT = (0.09765625, 0.0, 0.09765625, 0.0)    # 100 % = 1024 Spieleinheiten = ganze Karte

# Art eines Symbols: Schlüssel → (Name, Name in der Mehrzahl)
ARTEN = {"aprikoko": ("Aprikoko-Baum", "Aprikoko-Bäume"), "beere": ("Beerenbaum", "Beerenbäume"),
         "baum": ("Baum", "Bäume mit Zutaten"), "erz": ("Erzbrocken", "Erzbrocken"), "laub": ("Laubhaufen", "Laubhaufen"),
         "heu": ("Heuhaufen", "Heuhaufen"), "kiste": ("Kiste", "Kisten"), "truhe": ("Truhe", "Truhen"),
         "irrlicht": ("Irrlicht", "Irrlichter"), "icognito": ("Icognito", "Icognito"), "vers": ("Alter Vers", "Alte Verse"),
         "graben": ("Grabstelle", "Grabstellen")}
_LANDMARK = {"ore": "erz", "leaf": "laub", "hay": "heu", "box": "kiste", "chest": "truhe"}
_COLLECT = {"wisp": "irrlicht", "unown": "icognito", "verse": "vers", "dig": "graben"}
ORTE = {"Jubilife Village": VILLAGE_NAME, "Obsidian Fieldlands": "Obsidian-Grasland", "Crimson Mirelands": "Rotes Sumpfland",
        "Cobalt Coastlands": "Kobalt-Küstenland", "Coronet Highlands": "Kraterberg-Hochland",
        "Alabaster Icelands": "Weißes Frostland"}


def landmarks_url(area):
    return PLA + f"Landmarks/json/{area}-spawns.json"


def collectibles_url(area):
    return PLA + f"Collectibles/json/{area}.json"


RECIPES_URL = PLA + "recipes.html"


def _pct(v):
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*%?", str(v or ""))
    return float(m.group(1)) if m else None


def _pos(item, fit):
    px, pz = _pct(item.get("iconLeft")), _pct(item.get("iconTop"))
    if px is None or pz is None:
        return None
    ax, bx, az, bz = fit
    return round((px - bx) / ax, 1), round((pz - bz) / az, 1)


def _tree_kind(names):
    low = [n.lower() for n in names]
    if any("apricorn" in n for n in low):
        return "aprikoko"
    if low and all(n.endswith(" berry") for n in low):
        return "beere"
    return "baum"


def landmarks(text, fit):
    """Symbole aus <Gebiet>-spawns.json: [{art, x, z, menge, items: [[Name englisch, Anteil]]}]."""
    out = []
    for x in json.loads(text or "[]"):
        for g in x.get("groups") or []:
            conds = g.get("conditions") or []
            kind = conds[-1] if conds else ""
            pos = _pos(g, fit)
            if not pos:
                continue
            full = (x.get("full") or [{}])[0]
            items = [[n, p] for n, p in zip(full.get("itemName") or [], full.get("spawn") or [])]
            art = _tree_kind([n for n, _ in items]) if kind == "tree" else _LANDMARK.get(kind)
            if not art:
                continue
            menge = next((d.split(":", 1)[1].strip() for d in g.get("display") or [] if d.startswith("Items:")), "")
            out.append({"art": art, "x": pos[0], "z": pos[1], "menge": menge, "items": items})
    return out


def collectibles(text, fit):
    """Sammelobjekte aus <Gebiet>.json: [{art, x, z, nr}] (nr: laufende Nummer je Art, wie bei Altissimo)."""
    out, count = [], {}
    for x in json.loads(text or "[]"):
        art = _COLLECT.get(x.get("type"))
        pos = _pos(x, fit)
        if not art or not pos:
            continue
        count[art] = count.get(art, 0) + 1
        out.append({"art": art, "x": pos[0], "z": pos[1], "nr": count[art], "menge": "", "items": []})
    return out


def _cells(row):
    return [c for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]


def _text(cell):
    t = re.sub(r"<br\s*/?>", "\n", cell)
    t = re.sub(r"<[^>]+>", "", t)
    return [" ".join(html.unescape(x).split()) for x in t.split("\n") if x.strip()]


def recipes(page):
    """Rezepte aus recipes.html: ([{item, zutaten: [[Anzahl, Name]], ort, hinweis}], {Zutat: [Fundorte]}), englisch."""
    tables = re.findall(r"<table[^>]*>(.*?)</table>", page or "", re.S)
    recs, mats = [], {}
    for t in tables:
        head = [" ".join(_text(h)) for h in re.findall(r"<th[^>]*>(.*?)</th>", t, re.S)]
        rows = [_cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)]
        if head[:2] == ["Item", "Materials"]:
            for c in rows:
                if len(c) < 4:
                    continue
                parts = []
                for z in _text(c[1]):
                    m = re.match(r"(\d+)\s*x\s*(.+)", z)
                    if m:
                        parts.append([int(m.group(1)), m.group(2).strip()])
                name = " ".join(_text(c[0]))
                if name and parts:
                    recs.append({"item": name, "zutaten": parts, "ort": " ".join(_text(c[2])), "hinweis": " ".join(_text(c[3]))})
        elif head[:1] == ["Material"]:
            for c in rows:
                if len(c) >= 3 and _text(c[0]):
                    mats[" ".join(_text(c[0]))] = _text(c[2])
    return recs, mats


def place(name):
    """Ort auf Deutsch, sonst wie bei Altissimo."""
    return ORTE.get(name, name)
