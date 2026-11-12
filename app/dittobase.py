"""Karten von DittoBase (dittobase.com/<Spiel>/map), zuerst Kristall: die Seite bringt die ganze Welt als Spieldaten mit
(Blöcke je Karte, Kachelsätze als Bilder, Lage jeder Karte in der Oberwelt) und alle Punkte (Items, versteckte Items,
Trainer mit Team, feste und geschenkte Pokémon, Türen) und die wilden Pokémon je Karte. Ohne Netz; den Abruf macht
abruf.py. Das Ergebnis hat dieselbe Form wie eine Karte von Map Genie (mapgenie.parse), damit es durch dieselbe Strecke
läuft; die Kacheln zeichnet render_tiles selbst aus den Kachelsätzen (es gibt dort keine fertigen Kacheln).

Die Daten stehen im React-Server-Datenstrom der Seite (self.__next_f.push). Lage: Pixel der Oberwelt, Blöcke zu 32 Pixeln,
Punkte in Schritten zu 16 Pixeln. Die Oberwelt liegt wie bei pokemoncompletion in der linken oberen Ecke der
Web-Mercator-Welt, auf der Stufe Z1, in der die Welt mindestens so breit ist wie das Bild; Z1 + 1 ist doppelt so groß
(Pixelkunst bleibt scharf). Häuser, Höhlen und Etagen liegen nicht in der Oberwelt: ihre Punkte stehen am Eingang
(über die Türen gesucht), mit „In: …“ im Text."""
import base64
import json
import math
import re
from array import array

from . import mapgenie

BASE = "https://www.dittobase.com/"
# Spiel (Kennung wie in der PokéAPI) → Kennung bei DittoBase
GAMES = {"crystal": "crystal"}
TITEL = {"crystal": "Johto und Kanto (DittoBase)"}
BLOCK = 32                   # Pixel je Block
STEP = 16                    # Pixel je Schritt (Lage der Punkte)
TILE = 256
LEVELS = 5                   # so viele Stufen unter der vollen Auflösung
FARBE = {"Orte": "#5a9bd5", "Pokémon": "#d95f5f", "Items": "#e0b030", "Kämpfe": "#c27ad6", "Sammelobjekte": "#5fae5f"}
# Art eines Punkts dort → (Gruppe, Kategorie)
KIND = {"item": ("Items", "Items"), "hidden-item": ("Items", "Versteckte Items"), "trainer": ("Kämpfe", "Trainer"),
        "pokemon": ("Pokémon", "Feste und geschenkte Pokémon")}
METHODE = {"grass": "Gras", "surf": "Surfer", "old-rod": "Angel", "good-rod": "Profiangel", "super-rod": "Superangel",
           "headbutt": "Kopfnuss", "rock-smash": "Zertrümmerer", "walk": "Gras", "cave": "Höhle", "water": "Wasser"}
ZEIT = {"morning": "morgens", "day": "tags", "night": "nachts"}


def page_url(slug):
    return f"{BASE}{slug}/map"


def rsc(page):
    """Der React-Server-Datenstrom einer Next.js-Seite als ein Text (aus den self.__next_f.push-Aufrufen)."""
    out = []
    for m in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", str(page or ""), re.S):
        try:
            a = json.loads(m.group(1))
        except ValueError:
            continue
        if len(a) > 1 and isinstance(a[1], str):
            out.append(a[1])
    return "".join(out)


def _find(x, depth=0):
    if depth > 60:
        return None
    if isinstance(x, dict):
        d = x.get("data")
        if isinstance(d, dict) and "maps" in d and "markers" in d and isinstance(x.get("pixi"), dict):
            return x
        vals = x.values()
    elif isinstance(x, list):
        vals = x
    else:
        return None
    for v in vals:
        r = _find(v, depth + 1)
        if r:
            return r
    return None


def extract(page):
    """Die Kartendaten der Seite: {data: {overworld, maps, markers}, pixi: {tilesets, maps, …}, wild, images} oder None."""
    t = rsc(page)
    dec = json.JSONDecoder()
    for m in re.finditer(r'(?m)^[0-9a-f]{1,6}:(?=\[)', t):
        if '"pixi"' not in t[m.end():m.end() + 3_000_000]:
            continue
        try:
            row, _ = dec.raw_decode(t, m.end())
        except ValueError:
            continue
        hit = _find(row)
        if hit:
            return hit
    return None


def _team(tr):
    xs = []
    for p in (tr or {}).get("team") or []:
        moves = ", ".join(str(mv.get("name") or "") for mv in p.get("moves") or [] if mv.get("name"))
        t = f"«{p.get('name') or p.get('slug') or '?'}» Lv. {p.get('level', '?')}" + (f" ({moves})" if moves else "")
        if xs and xs[-1][1] == t:
            xs[-1][0] += 1
        else:
            xs.append([1, t])
    return [(f"{n}× " if n > 1 else "") + t for n, t in xs]


def _wild_text(rows):
    out = []
    for w in rows:
        meth = METHODE.get(w.get("method"), w.get("method") or "")
        when = "/".join(ZEIT.get(t, t) for t in w.get("times") or [])
        lv = f"{w.get('minLevel')}" + (f"–{w['maxLevel']}" if w.get("maxLevel") not in (None, w.get("minLevel")) else "")
        out.append(f"«{w.get('name') or w.get('slug')}» Lv. {lv}, {meth}" + (f" ({when})" if when else "")
                   + (f", {w['chance']} %" if w.get("chance") is not None else ""))
    return out


def geometry(w, h):
    """(Z1, Stufen) für eine Oberwelt von w × h Pixeln."""
    z1 = max(0, math.ceil(math.log2(max(w, h) / TILE)))
    return z1, LEVELS


def _ll(x, y, z1):
    la, lo = mapgenie.unproject(x, y, z1)
    return round(la, 6), round(lo, 6)


def anchors(data):
    """{Karte: (x, y, Weg)}: Lage jeder Karte in Pixeln der Oberwelt. Karten der Oberwelt: ihre Ecke; Häuser und Höhlen:
    die Tür, durch die man sie von der Oberwelt aus erreicht (Breitensuche über die Türen), Weg = Namen dorthin."""
    maps, markers = data.get("maps") or {}, data.get("markers") or {}
    out, todo = {}, []
    for k, v in maps.items():
        ow = v.get("overworld")
        if ow and ow.get("x") is not None:
            out[k] = (float(ow["x"]), float(ow["y"]), ())
            todo.append(k)
    while todo:
        nxt = []
        for k in todo:
            x0, y0, path = out[k]
            ow = (maps.get(k) or {}).get("overworld")
            for mk in markers.get(k) or []:
                to = (mk.get("door") or {}).get("to") if mk.get("kind") == "door" else None
                if not to or to in out or to not in maps:
                    continue
                if ow:
                    px, py = x0 + float(mk["x"]) * STEP + STEP / 2, y0 + float(mk["y"]) * STEP + STEP / 2
                else:
                    px, py = x0, y0
                out[to] = (px, py, path + (str(maps[to].get("name") or to),))
                nxt.append(to)
        todo = nxt
    return out


def parse(d, spiel):
    """Kartendaten (extract) → (Karte wie mapgenie.parse, Zeichendaten für render_tiles) oder (None, None)."""
    if not d:
        return None, None
    data, pixi = d.get("data") or {}, d.get("pixi") or {}
    ow = data.get("overworld") or {}
    W, H = int(ow.get("width") or 0), int(ow.get("height") or 0)
    if not (W and H and data.get("maps")):
        return None, None
    z1, levels = geometry(W, H)
    maps, wild = data["maps"], d.get("wild") or {}
    pos = anchors(data)
    orte, cats, gruppen, gebiete = [], {}, {}, []

    def cat(gruppe, titel):
        if (gruppe, titel) not in cats:
            cats[(gruppe, titel)] = {"id": len(cats) + 1, "titel": titel, "icon": "", "n": 0}
            gruppen.setdefault(gruppe, []).append(cats[(gruppe, titel)])
        return cats[(gruppe, titel)]["id"]

    inside = {}                     # Punkte an derselben Tür etwas auseinanderziehen
    for k in sorted(maps):
        if k not in pos:
            continue
        x0, y0, path = pos[k]
        is_ow = not path
        where = "In: " + " → ".join(path) if path else ""
        mname = str(maps[k].get("name") or k)
        if is_ow:
            mw, mh = int(maps[k].get("width") or 0) * BLOCK, int(maps[k].get("height") or 0) * BLOCK
            n, w = _ll(x0 - 64, y0 - 64, z1)
            s, e = _ll(x0 + mw + 64, y0 + mh + 64, z1)
            gebiete.append([mname[:80], w, s, e, n])
        rows = []
        for mk in data["markers"].get(k) or []:
            kind = mk.get("kind")
            name = str(mk.get("name") or "")
            if kind == "npc" and name == "Fruit Tree":
                g, t, name = "Items", "Beerenbäume", "Beerenbaum"
            elif kind in KIND:
                g, t = KIND[kind]
            else:
                continue
            lines = [where] if where else []
            if kind == "trainer":
                lines += _team(mk.get("trainer"))
                if (mk.get("trainer") or {}).get("prize"):
                    lines.append(f"Preisgeld {mk['trainer']['prize']} ¥")
            elif kind == "pokemon":
                p = mk.get("pokemon") or {}
                if p.get("level"):
                    lines.append(f"Lv. {p['level']}")
            rows.append((g, t, mk, name or t, lines))
        if wild.get(k):
            rows.append(("Pokémon", "Wilde Pokémon", None, mname, ([where] if where else []) + _wild_text(wild[k])))
        for i, (g, t, mk, name, lines) in enumerate(rows):
            if is_ow and mk is not None:
                x, y = x0 + float(mk["x"]) * STEP + STEP / 2, y0 + float(mk["y"]) * STEP + STEP / 2
            elif is_ow:              # wilde Pokémon: Mitte der Karte
                x = x0 + int(maps[k].get("width") or 0) * BLOCK / 2
                y = y0 + int(maps[k].get("height") or 0) * BLOCK / 2
            else:
                j = inside.get((x0, y0), 0)
                inside[(x0, y0)] = j + 1
                r = 10 + 4 * (j // 8)
                x, y = x0 + r * math.cos(j * 0.785), y0 + r * math.sin(j * 0.785)
            la, lo = _ll(x, y, z1)
            orte.append([30_000_000 + len(orte), cat(g, t), la, lo, name[:120], "\n".join(lines)[:1500]])
    for c in cats.values():
        c["n"] = sum(1 for o in orte if o[1] == c["id"])
    order = ("Orte", "Pokémon", "Items", "Kämpfe", "Sammelobjekte")
    gl = [{"id": 700 + order.index(g) if g in order else 799, "titel": g, "farbe": FARBE.get(g, "#888888"), "kategorien": cs}
          for g, cs in sorted(gruppen.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)]
    n0, w0 = _ll(0, 0, z1)
    s0, e0 = _ll(W, H, z1)
    gebiete.sort(key=lambda g: g[0].lower())
    slug = "db-" + GAMES.get(spiel, spiel)
    m = {"id": 0, "slug": slug, "titel": TITEL.get(spiel, spiel), "quelle": "dittobase", "kacheln": "", "endung": "png",
         "kachel": TILE, "dim": {"w": W, "h": H}, "min_zoom": z1 - levels, "max_zoom": z1 + 1,
         "bounds": [w0, s0, e0, n0], "gruppen": gl, "orte": orte, "gebiete": gebiete}
    # zum Zeichnen: nur die Karten der Oberwelt und ihre Kachelsätze
    draw = {"w": W, "h": H, "z1": z1, "karten": [], "saetze": {}}
    for k, v in maps.items():
        o = v.get("overworld")
        pm = (pixi.get("maps") or {}).get(k) or {}
        ts = (pixi.get("tilesets") or {}).get(pm.get("tileset")) or {}
        if not (o and pm.get("blocks") and ts.get("image")):
            continue
        draw["karten"].append([k, int(o["x"]), int(o["y"]), int(v.get("width") or 0), int(v.get("height") or 0),
                               pm["tileset"], pm["blocks"]])
        draw["saetze"][pm["tileset"]] = {"bild": str(ts["image"]), "spalten": int(ts.get("columns") or 16)}
    if not draw["karten"]:
        return None, None
    return m, draw


def tileset_ok(url):
    return bool(re.fullmatch(r"https://assets\.dittobase\.com/game-maps/[a-z0-9_-]+/pixi/tilesets/[a-z0-9_]+\.png", str(url)))


# ---------------------------------------------------------------------------------------------------- Kacheln zeichnen
def _blocks(rgba, w, h, cols, k):
    """Kachelsatz (RGBA, w × h) → je Blocknummer die Zeilen (Bytes) bei Stufe k unter der vollen Auflösung
    (k < 0: vergrößert). Nächster Nachbar; die Pixelkunst bleibt scharf."""
    out = []
    n = (w // BLOCK) * (h // BLOCK)
    for b in range(n):
        bx, by = (b % cols) * BLOCK, (b // cols) * BLOCK
        rows = []
        for r in range(BLOCK):
            a = array("I")
            a.frombytes(rgba[((by + r) * w + bx) * 4:((by + r) * w + bx + BLOCK) * 4])
            rows.append(a)
        if k > 0:
            f = 2 ** k
            rows = [a[::f] for a in rows[::f]]
        elif k < 0:
            f = 2 ** -k
            big = []
            for a in rows:
                d = array("I", bytes(len(a) * f * 4))
                for i in range(f):
                    d[i::f] = a
                big += [d] * f
            rows = big
        out.append([a.tobytes() for a in rows])
    return out


def render_tiles(draw, sets, save, have=lambda z, x, y: False, step=None):
    """Alle Kacheln der Oberwelt zeichnen. sets: {Kachelsatz: (w, h, RGBA)}; save(z, x, y, RGBA-Bytes 256 × 256);
    have(z, x, y): schon da (wird übersprungen). step(z, fertig, alle) für den Fortschritt. Gibt die Zahl der Kacheln."""
    W, H, z1 = draw["w"], draw["h"], draw["z1"]
    n = 0
    for z in range(z1 - LEVELS, z1 + 2):
        k = z1 - z                                     # > 0 verkleinert, −1 doppelt so groß
        bs = BLOCK // 2 ** k if k >= 0 else BLOCK * 2
        if bs < 1:
            continue
        cache = {}
        span = TILE * 2 ** k if k >= 0 else TILE // 2   # Pixel der Oberwelt je Kachel
        nx, ny = math.ceil(W / span), math.ceil(H / span)
        grid = {}
        for kname, mx, my, mw, mh, ts, blocks in draw["karten"]:
            for tx in range(int(mx // span), int((mx + mw * BLOCK - 1) // span) + 1):
                for ty in range(int(my // span), int((my + mh * BLOCK - 1) // span) + 1):
                    grid.setdefault((tx, ty), []).append((mx, my, mw, mh, ts, blocks))
        done = 0
        for tx in range(nx):
            for ty in range(ny):
                done += 1
                if have(z, tx, ty):
                    continue
                canvas = bytearray(TILE * TILE * 4)
                for mx, my, mw, mh, ts, blocks in grid.get((tx, ty), ()):
                    if ts not in sets:
                        continue
                    if ts not in cache:
                        w, h, rgba = sets[ts]
                        cache[ts] = _blocks(rgba, w, h, draw["saetze"][ts]["spalten"], k)
                    bl = cache[ts]
                    raw = base64.b64decode(blocks)
                    # Lage der Karte in Pixeln dieser Stufe, relativ zur Kachel
                    ox = (mx * bs) // BLOCK - tx * TILE
                    oy = (my * bs) // BLOCK - ty * TILE
                    for i, b in enumerate(raw[:mw * mh]):
                        if b >= len(bl):
                            continue
                        px, py = ox + (i % mw) * bs, oy + (i // mw) * bs
                        if px >= TILE or py >= TILE or px + bs <= 0 or py + bs <= 0:
                            continue
                        x0, x1 = max(0, -px), min(bs, TILE - px)
                        rows = bl[b]
                        for r in range(max(0, -py), min(bs, TILE - py)):
                            o = ((py + r) * TILE + px + x0) * 4
                            canvas[o:o + (x1 - x0) * 4] = rows[r][x0 * 4:x1 * 4]
                save(z, tx, ty, bytes(canvas))
                n += 1
                if step and done % 25 == 0:
                    step(z, done, nx * ny)
    return n


def tile(m, z, x, y):
    """(Pfad im Datenordner, None) einer Kachel: es gibt keine Adresse, render_tiles hat sie gezeichnet. None außerhalb."""
    if not (m["min_zoom"] <= z <= m["max_zoom"]):
        return None
    span = TILE * 2 ** (m["max_zoom"] - 1 - z) if z <= m["max_zoom"] - 1 else TILE // 2
    if not (0 <= x < math.ceil(m["dim"]["w"] / span) and 0 <= y < math.ceil(m["dim"]["h"] / span)):
        return None
    return f"db/{m['slug'][3:]}/{int(z)}/{int(x)}-{int(y)}.png", None


def tile_list(m, top=None):
    top = m["max_zoom"] if top is None else min(top, m["max_zoom"])
    out = []
    for z in range(m["min_zoom"], top + 1):
        span = TILE * 2 ** (m["max_zoom"] - 1 - z) if z <= m["max_zoom"] - 1 else TILE // 2
        out += [(z, x, y) for x in range(math.ceil(m["dim"]["w"] / span)) for y in range(math.ceil(m["dim"]["h"] / span))]
    return out
