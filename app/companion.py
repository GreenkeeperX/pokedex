"""Legenden: Arceus aus dem PLA Companion (software-notion.de), ohne Netz gelesen: Schnellreise-Punkte, Lager und
weitere Orte je Karte (`/apps/pla-companion/map/<Karte>/data?lang=de`).

Der Companion rechnet in eigenen Kartenkoordinaten. Die Umrechnung in Spielkoordinaten ergibt sich je Karte aus den
Geisterlichtern und Icognito, die auch Altissimo führt: aus je zwei Paaren eine Gerade je Achse, und es gilt die, unter
der die meisten Punkte beider Quellen aufeinander fallen (`fit`). Ohne genug gemeinsame Punkte bleibt die Karte leer.
"""
import json

BASE = "https://software-notion.de/apps/pla-companion/map/"
# Karte (wie PLA_MAPS in abruf und altissimo) → Schlüssel im Companion
MAPS = {"jubilifevillage": "jubilife-village", "obsidianfieldlands": "obsidian-fieldlands", "crimsonmirelands": "crimson-mirelands",
        "cobaltcoastlands": "cobalt-coastlands", "coronethighlands": "coronet-highlands", "alabastericelands": "alabaster-icelands"}
# Art im Companion → Art der Kartensymbole; alles mit „camp“ im Namen zählt als Lager
ARTEN = {"fast-travel": "reise", "camp": "lager", "base-camp": "lager", "basecamp": "lager"}
NAMEN = {"reise": ("Schnellreise", "Schnellreise"), "lager": ("Lager", "Lager")}
# Gemeinsame Punkte mit Altissimo zum Ausrichten
ANKER = {"wisp": "irrlicht", "unown": "icognito"}
TOL = 15.0                  # so nah (Spieleinheiten) müssen sich zwei Punkte nach der Umrechnung kommen (Kartenbilder weichen leicht ab)
MIN_HITS = 4


def url(karte):
    return f"{BASE}{MAPS[karte]}/data?lang=de"


def entries(text):
    """Einträge einer Karte: [{t, n, x, y}] mit Lage (Einträge ohne Lage, etwa Aufträge, fallen weg)."""
    d = json.loads(text or "{}") or {}
    out = []
    for e in d.get("entries") or []:
        if not isinstance(e, dict):
            continue
        try:
            x, y = float(e.get("x") or 0), float(e.get("y") or 0)
        except (TypeError, ValueError):
            continue
        if x or y:
            out.append({"t": str(e.get("t") or ""), "n": str(e.get("n") or ""), "x": x, "y": y})
    return out


def art(t):
    return ARTEN.get(t) or ("lager" if "camp" in t else None)


def fit(src, game):
    """src: [(x, y)] im Companion, game: [(x, z)] in Spielkoordinaten (dieselbe Art Punkte). Gibt (ax, bx, az, bz) mit
    x = ax·cx + bx und z = az·cy + bz zurück, oder None. Probiert die am weitesten auseinander liegenden Paare im
    Companion gegen alle Paare im Spiel und zählt, wie viele Punkte danach zusammenfallen."""
    if len(src) < 2 or len(game) < 2:
        return None
    pairs = sorted(((i, j) for i in range(len(src)) for j in range(i + 1, len(src))),
                   key=lambda p: -min(abs(src[p[0]][0] - src[p[1]][0]), abs(src[p[0]][1] - src[p[1]][1])))[:6]
    best, hits = None, 0
    for i, j in pairs:
        (x1, y1), (x2, y2) = src[i], src[j]
        if x1 == x2 or y1 == y2:
            continue
        for k, g1 in enumerate(game):
            for m, g2 in enumerate(game):
                if k == m:
                    continue
                ax, az = (g2[0] - g1[0]) / (x2 - x1), (g2[1] - g1[1]) / (y2 - y1)
                if not ax or not az or not 0.2 < abs(ax / az) < 5:
                    continue
                bx, bz = g1[0] - ax * x1, g1[1] - az * y1
                n = sum(1 for x, y in src if any(abs(ax * x + bx - gx) <= TOL and abs(az * y + bz - gz) <= TOL for gx, gz in game))
                if n > hits:
                    best, hits = (ax, bx, az, bz), n
    return best if hits >= max(MIN_HITS, min(len(src), len(game)) // 2) else None


def places(text, anchors):
    """Schnellreise und Lager einer Karte in Spielkoordinaten: [{art, name, x, z}]. anchors: {Art bei Altissimo: [(x, z)]}."""
    es = entries(text)
    src, game = [], []
    for t, a in ANKER.items():
        s = [(e["x"], e["y"]) for e in es if e["t"] == t]
        if s and anchors.get(a):
            src.append(s)
            game.append(anchors[a])
    f = None
    for s, g in zip(src, game):
        f = fit(s, g)
        if f:
            break
    if not f:
        return []
    ax, bx, az, bz = f
    return [{"art": art(e["t"]), "name": e["n"], "x": round(ax * e["x"] + bx, 1), "z": round(az * e["y"] + bz, 1)}
            for e in es if art(e["t"])]
