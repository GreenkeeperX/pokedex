"""Bilder und Platz: Sprites, Artworks, Item-Bilder, Kacheln der Hisui-Karte, Belegung des Datenordners.

Teil des Pakets app.abruf; alle Namen sind auch dort erreichbar.
"""
import json
import os
import re
import time
from datetime import timedelta

from .. import db, fehler, importer, store

from .grundlage import PLA_MAPS, SPRITES_MAX, SPRITE_MISS_DAYS, SPRITE_RAW, STATE, _Source, _iso, now


# Bilder: kleine Pixel-Sprites (96 × 96) für Listen, offizielle Artworks (475 × 475) für Karten und Detailseite
IMAGES = {"sprites": SPRITE_RAW, "artwork": SPRITE_RAW + "other/official-artwork/"}
# Extras: schillernde und animierte Sprites (Showdown-Stil), Rufe (PokéAPI-Repos); Endung und Kennung der Datei
EXTRAS = {"shiny": (SPRITE_RAW + "shiny/", ".png"), "shinyart": (SPRITE_RAW + "other/official-artwork/shiny/", ".png"),
          "anim": (SPRITE_RAW + "other/showdown/", ".gif"),
          "rufe": ("https://raw.githubusercontent.com/PokeAPI/cries/main/cries/pokemon/latest/", ".ogg"),
          # Item-Bilder: Datei heißt wie die Kennung des Items, gespeichert unter der Nummer
          "itembild": (SPRITE_RAW.replace("/pokemon/", "/items/"), ".png"),
          # größere Item-Bilder von Serebii (Legenden: Arceus 128 px, Karmesin/Purpur und Z-A 160 px) nach dem englischen Namen
          "itemhq": ("https://www.serebii.net/itemdex/sprites/", ".png"),
          # Formen nur zum Ansehen (Burmy, Vivillon, Icognito …): Datei <Art>-<Form>.png, gespeichert unter der Formnummer
          "formen": (SPRITE_RAW, ".png")}
# Spiele, für die Serebii eigene Item-Bilder hat: Unterordner → Spielkennungen
ITEM_HQ = {"legends": ("legends-arceus",), "sv": ("scarlet-violet", "the-teal-mask", "the-indigo-disk", "legends-za", "mega-dimension")}
ITEM_HQ_MAX = 1500          # so viele große Item-Bilder je Lauf (eine Sekunde Pause: knapp eine halbe Stunde beim ersten Mal)
MEDIA_LABEL = {"sprites": "Sprites", "artwork": "Artworks", "shiny": "Schillernde Sprites", "shinyart": "Schillernde Artworks",
               "anim": "Animierte Sprites", "rufe": "Rufe", "itembild": "Item-Bilder", "itemhq": "Große Item-Bilder",
               "formen": "Formen zum Ansehen"}


def miss_name(kind):
    """Datei mit den Bildern, die es nicht gibt. Große Item-Bilder ab 0.20.0 neu: Serebii-Namen mit Bindestrich und Apostroph."""
    return "itemhq3_fehlen.json" if kind == "itemhq" else f"{kind}_fehlen.json"


def serebii_key(name):
    """Dateiname bei Serebii: klein, ohne Leerzeichen; Bindestrich und Apostroph bleiben (King’s Leaf → king'sleaf)."""
    t = (name or "").lower().replace("é", "e").replace("’", "'")
    return re.sub(r"[^a-z0-9'-]", "", t)


def media_ids(kind):
    """Was es für eine Bildart geben sollte: {Nummer: Name der Datei bei der Quelle}. Items ohne Maschinen (die haben kein
    eigenes Bild) und ohne unfertige Einträge."""
    con = db.game()
    try:
        if kind == "itembild":
            try:
                return {r[0]: r[1] for r in con.execute("SELECT id, kennung FROM item WHERE tasche != 'Maschinen' AND unfertig = 0 "
                                                        "AND kennung NOT LIKE 'pkhex-%' ORDER BY id")}
            except Exception as e:      # Datenbank noch ohne die Spalten von 0.8.0
                fehler.melden(e)
                return {}
        if kind == "formen":
            try:
                return {r[0]: f"{r[1]}-{r[2]}" for r in con.execute(
                    "SELECT f.id, p.species_id, f.form_identifier FROM pokemon_forms f JOIN pokemon p ON p.id = f.pokemon_id "
                    "WHERE f.is_default = 0 AND f.form_identifier != '' AND f.pokemon_id IN "
                    "(SELECT pokemon_id FROM pokemon_forms GROUP BY pokemon_id HAVING COUNT(*) > 1) ORDER BY f.id")}
            except Exception as e:
                fehler.melden(e)
                return {}
        if kind == "itemhq":            # Ordner bei Serebii nach dem neuesten Spiel mit dem Item
            try:
                vgs = {k: i for i, k in con.execute("SELECT id, kennung FROM spiel")}
                rows = con.execute("SELECT id, en, spiele, kennung FROM item WHERE tasche != 'Maschinen' AND unfertig = 0 AND en != '' "
                                   "ORDER BY id").fetchall()
            except Exception as e:      # Datenbank vor 0.12.0 (ohne englische Namen)
                fehler.melden(e)
                return {}
            out = {}
            big = {vgs.get(k) for ks in ITEM_HQ.values() for k in ks}
            for iid, en, spiele, kennung in rows:
                if not big & set(json.loads(spiele or "[]")) and not str(kennung).startswith("pkhex-"):
                    continue            # ältere Items: das Bild der PokéAPI reicht
                # Ordner der Spiele mit dem Item zuerst, dann der andere, zuletzt das kleine Bild (40 px) für ältere Items
                games, key = set(json.loads(spiele or "[]")), importer.en_key(en)
                subs = sorted(ITEM_HQ, key=lambda sub: (not games & {vgs.get(k) for k in ITEM_HQ[sub]}, sub != "sv"))
                keys = list(dict.fromkeys([key, serebii_key(en)]))       # Serebii behält Bindestrich und Apostroph
                out[iid] = tuple(f"{sub}/{k}" for k in keys for sub in subs) + tuple(keys)
            return out
        return {r[0]: str(r[0]) for r in con.execute("SELECT id FROM form ORDER BY id")}
    finally:
        con.close()


# Speicherplatz im Datenordner: Namen für die Ordner und Dateien (sonst steht der Name selbst da)
DISK_LABEL = {"pokeapi.db": "Spieldatenbank", "user.db": "Deine Daten (Teams, Sammlung, Entscheidungen)",
              "sicherung": "Tägliche Sicherungen deiner Daten", "karten": "Karten Legenden: Arceus (Spieldaten)",
              "mapgenie": "Karten (Daten und Kacheln)", "formen": "Bilder der Formen", "bisafans.json": "Aufträge (BisaFans)",
              "pokewiki_trainer.json": "Trainerteams (PokéWiki)"}
DISK_TILES = {"im": "HeartGold/SoulSilver: Weltkarten (im Browser umgewandelt)", "rn": "Schwert/Schild: Raid-Nester",
              "se": "Serebii PokéEarth", "rb": "RankedBoost", "pc": "pokemoncompletion", "db": "DittoBase", "ign": "IGN"}
DISK_CACHE_S = 300          # so lange gilt eine Zählung (viele Kacheln: das Durchzählen dauert)
_disk = {"at": 0.0, "data": None, "dir": None}


def _du(path):
    """(Bytes, Dateien) unter einem Pfad, ohne Verknüpfungen zu folgen."""
    if os.path.isfile(path):
        return os.path.getsize(path), 1
    total = n = 0
    stack = [path]
    while stack:
        try:
            it = os.scandir(stack.pop())
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        total += e.stat(follow_symlinks=False).st_size
                        n += 1
                except OSError:
                    pass
    return total, n


def disk_known():
    """Die letzte Zählung des Datenordners, solange sie gilt (DISK_CACHE_S, derselbe Ordner), sonst None. Zählt nicht selbst."""
    if _disk["data"] and _disk["dir"] == db.data_dir() and time.monotonic() - _disk["at"] < DISK_CACHE_S:
        return _disk["data"]
    return None


def disk_usage(force=False):
    """Speicherplatz des Datenordners: {gesamt, frei, teile: [{name, titel, bytes, dateien, teile?}]}, groß zuerst;
    Karten aufgeschlüsselt nach Quelle der Kacheln und je Karte. Gezählt höchstens alle DISK_CACHE_S Sekunden."""
    if not force and disk_known():
        return _disk["data"]
    import shutil
    root = db.data_dir()
    label = {**DISK_LABEL, **{k: MEDIA_LABEL.get(k, k) for k in list(IMAGES) + list(EXTRAS)}}

    def entry(path, name, titel, deeper=None):
        b, n = _du(path)
        out = {"name": name, "titel": titel, "bytes": b, "dateien": n}
        if deeper:
            subs = deeper(path)
            if subs:
                out["teile"] = sorted(subs, key=lambda x: -x["bytes"])
                out["bytes"] = max(b, sum(x["bytes"] for x in subs))   # Teile können verknüpft sein
                out["dateien"] = max(n, sum(x["dateien"] for x in subs))
        return out

    def maps(path):
        k = os.path.join(path, "kacheln")
        subs = [entry(os.path.join(k, x), x, DISK_TILES.get(x, f"Map Genie: {x}"),
                      lambda p: [entry(os.path.join(p, y), y, y) for y in os.listdir(p) if os.path.isdir(os.path.join(p, y))])
                for x in (os.listdir(k) if os.path.isdir(k) else []) if os.path.isdir(os.path.join(k, x))]
        rest = sum(_du(os.path.join(path, x))[0] for x in os.listdir(path) if x != "kacheln")
        return subs + [{"name": "daten", "titel": "Kartendaten (Punkte, Orte)", "bytes": rest, "dateien": 0}]

    teile = []
    for x in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        p = os.path.join(root, x)
        teile.append(entry(p, x, label.get(x, x), maps if x == "mapgenie" else None))
    big = [t for t in teile if t["bytes"] >= 1_000_000 or t["name"] in label]
    small = [t for t in teile if t not in big]
    if small:
        big.append({"name": "sonst", "titel": "Sonstiges (Stand, Protokolle, Einstellungen)", "bytes": sum(t["bytes"] for t in small),
                    "dateien": sum(t["dateien"] for t in small)})
    try:
        du = shutil.disk_usage(root)
        frei, platte = du.free, du.total
    except OSError:
        frei = platte = None
    data = {"gesamt": sum(t["bytes"] for t in teile), "frei": frei, "platte": platte, "am": _iso(now()),
            "teile": sorted(big, key=lambda t: -t["bytes"])}
    _disk.update(at=time.monotonic(), data=data, dir=root)
    return data


def media_inventory():
    """Je Bildart: wie viele Dateien da sind und welche Nummern fehlen (für den Download der Spieldaten)."""
    out = {}
    for kind in list(IMAGES) + list(EXTRAS):
        folder = os.path.join(db.data_dir(), kind)
        have = {os.path.splitext(x)[0] for x in os.listdir(folder)} if os.path.isdir(folder) else set()
        want = media_ids(kind)
        gone = store.load_json(miss_name(kind), {})
        missing = [i for i in want if str(i) not in have]
        out[kind] = {"name": MEDIA_LABEL[kind], "erwartet": len(want), "vorhanden": len(want) - len(missing),
                     "fehlen": [i for i in missing if str(i) not in gone],
                     "gibt_es_nicht": [i for i in missing if str(i) in gone]}
    tiles = map_tiles()
    folder = os.path.join(db.data_dir(), "karten")
    lost = [f"{k}/{z}-{x}-{y}" for k, z, x, y in tiles if not os.path.isfile(os.path.join(folder, k, f"{z}-{x}-{y}.png"))]
    out["karten"] = {"name": "Kartenkacheln", "erwartet": len(tiles), "vorhanden": len(tiles) - len(lost), "fehlen": lost, "gibt_es_nicht": []}
    return out


def file_kind(body):
    """Endung nach Inhalt: .png, .gif, .mp3, .ogg oder None."""
    if body[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if body[:4] == b"GIF8":
        return ".gif"
    if body[:4] == b"OggS":
        return ".ogg"
    if body[:3] == b"ID3" or body[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3"
    return None


def _images(kind, log, limit=SPRITES_MAX):
    """Fehlende Bilder nach data/<kind>/<id>.png (Extras auch .gif, .mp3, .ogg). Gibt das Ergebnis der Quelle zurück."""
    src = _Source("extras" if kind in EXTRAS else "sprites", log, pause=1.0 if kind == "itemhq" else 0.2,
                  ruhe="itemhq" if kind == "itemhq" else None)
    if kind == "itemhq":
        limit = min(limit, ITEM_HQ_MAX)
    prefix, ext = EXTRAS.get(kind, (IMAGES.get(kind), ".png"))
    folder = os.path.join(db.data_dir(), kind)
    os.makedirs(folder, exist_ok=True)
    names = media_ids(kind)
    ids = list(names)
    miss_file = miss_name(kind)
    miss = store.load_json(miss_file, {})
    cutoff = _iso(now() - timedelta(days=SPRITE_MISS_DAYS))
    have = {os.path.splitext(x)[0] for x in os.listdir(folder)}
    todo = [i for i in ids if str(i) not in have and (miss.get(str(i)) or "") < cutoff]
    got = absent = 0
    label = MEDIA_LABEL[kind]
    for n, i in enumerate(todo[:limit]):
        STATE.update(step=label, done=n, total=min(len(todo), limit))
        for name in names[i] if isinstance(names[i], tuple) else (names[i],):     # mehrere Orte: der erste, den es gibt
            body = src.get(f"{prefix}{name}{ext}", raw=True, absent=(404,))
            if body != b"" and body != "":
                break
        if body is None:
            if src.stopped:
                break
            continue
        if not body:
            miss[str(i)] = _iso(now())
            absent += 1
            continue
        real = file_kind(body)
        if not real:
            continue
        tmp = os.path.join(folder, f".{i}.tmp")
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, os.path.join(folder, f"{i}{real}"))
        got += 1
    store.save_json(miss_file, miss)
    left = max(0, len(todo) - limit)
    if todo:
        log(f"{label}: {got} neu" + (f", {absent} gibt es nicht" if absent else "") + (f", {left} im nächsten Lauf" if left else ""))
    return src.result(neu=got, fehlen=absent, offen=left)


SEREBII = "https://www.serebii.net/"
GAMERGUIDES = "https://www.gamerguides.com/"
POKEBIP = "https://www.pokebip.com/"
MAP_TILES = SEREBII + "pokearth/hisui/"
MAP_ZOOM = 2                # Kacheln 256 px, Zoom z hat 2^(z+1) × 2^(z+1) Kacheln je Karte


def map_tiles():
    """Alle Kacheln der Karten als (Karte, z, x, y)."""
    return [(k, z, x, y) for k in PLA_MAPS for z in range(MAP_ZOOM + 1)
            for x in range(2 ** (z + 1)) for y in range(2 ** (z + 1))]


def _tiles(log):
    """Fehlende Kartenkacheln (Serebii) nach data/karten/<Karte>/<z>-<x>-<y>.png, alle fehlenden je Lauf."""
    src = _Source("karten", log, pause=1.0)
    root = os.path.join(db.data_dir(), "karten")
    miss = store.load_json("karten_fehlen.json", {})
    cutoff = _iso(now() - timedelta(days=SPRITE_MISS_DAYS))
    todo = [t for t in map_tiles() if not os.path.isfile(os.path.join(root, t[0], "%d-%d-%d.png" % t[1:]))
            and (miss.get("%s/%d-%d-%d" % t) or "") < cutoff]
    got = absent = 0
    for n, (k, z, x, y) in enumerate(todo):
        STATE.update(step="Kartenkacheln", done=n, total=len(todo))
        body = src.get(f"{MAP_TILES}{k}/tile_{z}-{x}-{y}.png", raw=True, absent=(404,))
        if body is None:
            if src.stopped:
                break
            continue
        if not body or body[:8] != b"\x89PNG\r\n\x1a\n":
            miss["%s/%d-%d-%d" % (k, z, x, y)] = _iso(now())
            absent += 1
            continue
        folder = os.path.join(root, k)
        os.makedirs(folder, exist_ok=True)
        tmp = os.path.join(folder, f".{z}-{x}-{y}.tmp")
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, os.path.join(folder, f"{z}-{x}-{y}.png"))
        got += 1
    store.save_json("karten_fehlen.json", miss)
    if todo:
        log(f"Kartenkacheln: {got} neu" + (f", {absent} gibt es nicht" if absent else ""))
    return src.result(neu=got, fehlen=absent)


def _sprites(log, limit=SPRITES_MAX):
    return _images("sprites", log, limit)
