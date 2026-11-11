"""Karten von pokemoncompletion (GPL-3.0, github.com/RainingChain/pokemoncompletion) für Kristall, Smaragd und Platin:
Kartenpunkte aus den Spieldaten im Repository, das Kartenbild als Kacheln von dessen CDN. Ohne Netz; den Abruf macht
abruf.py. Das Ergebnis hat dieselbe Form wie eine Karte von Map Genie (mapgenie.parse), damit es durch dieselbe
Strecke läuft (Zusammenführen, Oberfläche, Kachelvorrat).

Dort ist die Karte ein Bild in Leaflet-CRS.Simple: Kacheln {z}_{x}_{y}.png zu 512 Pixeln, z = 1 volle Auflösung, jede
Stufe darüber halb so groß; ein Punkt [a, b] liegt bei Pixel (b·2^M, −a·2^M) mit M = log2(Seite / 512) − 1. Hier liegt
das Bild in der linken oberen Ecke der Web-Mercator-Welt, auf der Zoomstufe Z1, in der die Welt so breit ist wie das
Bild (256·2^Z1 Pixel). Eine Kachel zu 512 auf Stufe z ist dann genau die Kachel z1 − z + 1 von dort."""
import json
import math

from . import mapgenie

DATA = "https://raw.githubusercontent.com/RainingChain/pokemoncompletion/main/src/pokemonCompletion/data/{}.json"
TILES = "https://pokemonmap.b-cdn.net/"
TILE = 512
# Spiel (Kennung wie in der PokéAPI) → Name dort. Gelb hat dort auch eine Karte, aber die von Map Genie ist schon da
GAMES = {"crystal": "Crystal", "emerald": "Emerald", "platinum": "Platinum"}
TITEL = {"crystal": "Johto und Kanto (Kristall)", "emerald": "Hoenn (Smaragd)", "platinum": "Sinnoh (Platin)"}
# Schwester-Editionen: gleiche Welt, Fundorte und Items weichen ab (steht in den Details)
SHARE = {"gold-silver": "crystal", "ruby-sapphire": "emerald", "diamond-pearl": "platinum"}

# Kategorie dort → (Gruppe, deutscher Titel)
KAT = {"pokemon": ("Pokémon", "Wilde Pokémon"), "pokemonForm": ("Pokémon", "Formen"),
       "inGameGift": ("Pokémon", "Geschenkte Pokémon"), "inGameTrade": ("Pokémon", "Tausch"),
       "item": ("Items", "Items"), "itemInMap": ("Items", "Items auf der Karte"), "itemGift": ("Items", "Geschenkte Items"),
       "undergroundItem": ("Items", "Untergrund"), "battle": ("Kämpfe", "Trainer"),
       "battleFrontier": ("Sammelobjekte", "Kampfzonen-Symbole"), "phone": ("Sammelobjekte", "Telefonnummern"),
       "decoration": ("Sammelobjekte", "Deko"), "pokegear": ("Sammelobjekte", "PokéCom-Teile"),
       "ribbon": ("Sammelobjekte", "Bänder"), "trainerStar": ("Sammelobjekte", "Trainerstern"),
       "pokeblock": ("Sammelobjekte", "Pokériegel"), "easyChatSystemWord": ("Sammelobjekte", "Wörter"),
       "gameStat": ("Sammelobjekte", "Spielwerte"), "poketch": ("Sammelobjekte", "Pokétch-Apps"),
       "backdrop": ("Sammelobjekte", "Kulissen"), "pokeballSeal": ("Sammelobjekte", "Ball-Sticker"),
       "accessory": ("Sammelobjekte", "Accessoires"), "poffin": ("Sammelobjekte", "Knurspe"),
       "pcWallPaper": ("Sammelobjekte", "PC-Hintergründe"), "villaFurniture": ("Sammelobjekte", "Villa-Möbel"),
       "misc": ("Sammelobjekte", "Sonstige Aufgaben")}
FARBE = {"Orte": "#5a9bd5", "Pokémon": "#d95f5f", "Items": "#e0b030", "Kämpfe": "#c27ad6", "Sammelobjekte": "#5fae5f"}
ORT_RAND = 300              # „Gehe zu“: so viele Pixel (volle Auflösung) um einen Ort herum


def geometry(dim):
    """(M, Z1, Stufen) aus der Bildgröße {w, h}: M wie dort, Z1 die eigene Zoomstufe der vollen Auflösung."""
    side = max(int(dim["w"]), int(dim["h"]))
    m = int(round(math.log2(side / TILE))) - 1
    return m, int(round(math.log2(side / 256))), m + 1


def to_ll(pos, m, z1):
    """Punkt dort [a, b] → [Breite, Länge] auf der eigenen Karte."""
    s = 2 ** m
    la, lo = mapgenie.unproject(float(pos[1]) * s, -float(pos[0]) * s, z1)
    return round(la, 6), round(lo, 6)


def _positions(p):
    if not p:
        return []
    return [p] if isinstance(p[0], (int, float)) else [q for q in p if isinstance(q, list) and len(q) == 2]


def parse(text, spiel):
    """Spieldaten (JSON-Text) → Karte wie mapgenie.parse, mit quelle, kachel (512) und dim; None ohne Karte."""
    try:
        d = json.loads(text) if isinstance(text, str) else (text or {})
    except ValueError:
        return None
    im = d.get("interactiveMap") or {}
    dim = im.get("dim") or {}
    if not (dim.get("w") and dim.get("h")) or int(im.get("cropSize") or 0) != TILE:
        return None
    m, z1, _ = geometry(dim)
    s = 2 ** m
    orte, cats, gruppen, gebiete = [], {}, {}, []

    def cat(gruppe, titel):
        key = (gruppe, titel)
        if key not in cats:
            cats[key] = {"id": len(cats) + 1, "titel": titel, "icon": "", "n": 0}
            gruppen.setdefault(gruppe, []).append(cats[key])
        return cats[key]

    for i, loc in enumerate(d.get("locations") or []):
        if not (loc.get("pos") and loc.get("name")):
            continue
        c = cat("Orte", "Orte")
        la, lo = to_ll(loc["pos"], m, z1)
        orte.append([10_000_000 + i, c["id"], la, lo, str(loc["name"])[:120], ""])
        x, y = float(loc["pos"][1]) * s, -float(loc["pos"][0]) * s
        n, w = mapgenie.unproject(x - ORT_RAND, y - ORT_RAND, z1)
        su, e = mapgenie.unproject(x + ORT_RAND, y + ORT_RAND, z1)
        gebiete.append([str(loc["name"])[:80], round(w, 6), round(su, 6), round(e, 6), round(n, 6)])
    for k in d.get("categories") or []:
        gruppe, titel = KAT.get(k.get("id"), ("Sammelobjekte", str(k.get("name") or k.get("id") or "")))
        for x in k.get("list") or []:
            ps = _positions(x.get("pos"))
            if not ps or x.get("uid") is None:
                continue
            c = cat(gruppe, titel)
            text = str(x.get("location") or "")
            if x.get("reqs"):
                text += ("\n" if text else "") + "Bedingung: " + ", ".join(map(str, x["reqs"]))
            for j, p in enumerate(ps[:999]):
                la, lo = to_ll(p, m, z1)
                orte.append([int(x["uid"]) * 1000 + j, c["id"], la, lo, str(x.get("name") or titel)[:120], text[:1500]])
    for c in cats.values():
        c["n"] = sum(1 for o in orte if o[1] == c["id"])
    order = ("Orte", "Pokémon", "Items", "Kämpfe", "Sammelobjekte")
    gl = [{"id": 900 + order.index(g) if g in order else 999, "titel": g, "farbe": FARBE.get(g, "#888888"), "kategorien": cs}
          for g, cs in sorted(gruppen.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)]
    n0, w0 = mapgenie.unproject(0, 0, z1)
    s0, e0 = mapgenie.unproject(int(dim["w"]), int(dim["h"]), z1)
    gebiete.sort(key=lambda g: g[0].lower())
    return {"id": 0, "slug": GAMES.get(spiel, spiel).lower(), "titel": TITEL.get(spiel, spiel), "quelle": "pokemoncompletion",
            "kacheln": "", "endung": "png", "kachel": TILE, "dim": {"w": int(dim["w"]), "h": int(dim["h"])},
            "min_zoom": z1 - m, "max_zoom": z1, "bounds": [round(w0, 6), round(s0, 6), round(e0, 6), round(n0, 6)],
            "gruppen": gl, "orte": orte, "gebiete": gebiete}


def tile(m, z, x, y):
    """(Pfad im Datenordner, Adresse) einer Kachel der eigenen Stufe z, oder None außerhalb des Bilds."""
    _, z1, _ = geometry(m["dim"])
    k = z1 - int(z) + 1
    if not (m["min_zoom"] <= z <= m["max_zoom"]) or k < 1:
        return None
    f = TILE * 2 ** (k - 1)
    if not (0 <= x < math.ceil(m["dim"]["w"] / f) and 0 <= y < math.ceil(m["dim"]["h"] / f)):
        return None
    slug = m["slug"]
    return f"pc/{slug}/{k}_{int(x)}_{int(y)}.png", f"{TILES}{slug}/{k}_{int(x)}_{int(y)}.png?v=1"


def tile_list(m, top=None):
    """Alle Kacheln als (z, x, y), von der weitesten Stufe bis top (Vorgabe: volle Auflösung)."""
    top = m["max_zoom"] if top is None else min(top, m["max_zoom"])
    out = []
    for z in range(m["min_zoom"], top + 1):
        f = TILE * 2 ** (m["max_zoom"] - z)
        out += [(z, x, y) for x in range(math.ceil(m["dim"]["w"] / f)) for y in range(math.ceil(m["dim"]["h"] / f))]
    return out
