"""Abgleich: Daten holen, pokeapi.db neu bauen, Sprites ergänzen. Nach dem Vorbild des VR-Navigators.

Quellen und ihre Rolle:
- PokéAPI (CSV-Dateien im GitHub-Repo): Primärquelle für alle Grunddaten, alle Spiele, deutsche Namen
- Pokémon Showdown (pokedex.ts, moves.ts): Gegenprüfung von Werten, Typen, Attacken; Merkmale wie „Aufladen“
- PokéAPI-Sprites: Bilder, nur fehlende werden geholt
- extra/ im Repo: gepflegte Ergänzungen (JSON), die keine Quelle liefert

Ablauf: Hat sich bei keiner Quelle etwas geändert, wird nichts neu gebaut. Sonst entsteht die neue Datenbank
in einer eigenen Datei und ersetzt die alte erst nach bestandener Selbstprüfung. Scheitert etwas, bleibt die
alte Datenbank. Nach einer Sperre (HTTP 403, 429) oder Prüfseite ruht eine Quelle REST_H Stunden.
"""
import gzip
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from . import altissimo, companion, db, importer, mapgenie, pokewiki, sources, store

PAUSE = 0.5                 # Sekunden zwischen zwei Abrufen am selben Server
REST_H = 24
NET_RETRY = 5.0
MAX_ERRORS = 5
BOOT_WAIT_S = 300           # Ruhe nach dem Start des Containers
LOG_LINES = 300
SPRITES_MAX = 1500          # Bilder je Lauf
SPRITE_MISS_DAYS = 30       # Bild gibt es nicht: so lange nicht neu fragen

GH_API = "https://api.github.com/repos/PokeAPI/pokeapi"
CSV_RAW = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"
SD_RAW = "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/"
SPRITE_RAW = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/"
POKEWIKI_API = "https://www.pokewiki.de/api.php"
EXTRA_DIR = os.path.join(os.path.dirname(__file__), "..", "extra")

SETTINGS = {"auto": True, "tage": 7, "sprites": True}
NAMES = {"pokeapi": "PokéAPI", "showdown": "Showdown", "sprites": "Sprites", "pkhex": "PKHeX", "spawns": "Spawnpunkte",
         "karten": "Kartenbilder", "extras": "Extras (schillernd, animiert, Rufe)", "pokewiki": "PokéWiki",
         "altissimo": "Altissimo (Kartensymbole, Rezepte)", "companion": "PLA Companion (Schnellreise, Lager)",
         "mapgenie": "Map Genie (Karten)"}
MG_PAUSE = 3.0              # Sekunden zwischen zwei Seiten bei Map Genie
MG_TILE_PAUSE = 0.3         # zwischen zwei Kacheln, die die Oberfläche anfordert
WIKI_PAUSE = 2.0            # Sekunden zwischen zwei Anfragen an das PokéWiki (je Anfrage bis zu 50 Seiten)
WIKI_GAMES = ("legends-arceus",)    # Spiele, deren Attacken und Pokémon im PokéWiki gelesen werden

sleep = time.sleep          # Tests setzen hier eine Attrappe ein
_running = threading.Lock()
STATE = {"started": "", "step": "", "done": 0, "total": 0, "log": []}


def now():
    return datetime.now(timezone.utc)


def _iso(at):
    return at.isoformat(timespec="seconds")


def _ago(iso, at):
    try:
        return at - datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None


def load_settings():
    s = dict(SETTINGS)
    s.update({k: v for k, v in store.load_json("settings.json", {}).items() if k in SETTINGS})
    return s


def save_settings(body):
    s = load_settings()
    for k in ("auto", "sprites"):
        if k in body:
            s[k] = bool(body[k])
    if "tage" in body:
        try:
            s["tage"] = min(30, max(1, int(body["tage"])))
        except (TypeError, ValueError):
            raise ValueError("Abstand in Tagen: eine Zahl von 1 bis 30")
    store.save_json("settings.json", s)
    return s


def status():
    st = store.load_json("sync.json", {})
    st["running"] = _running.locked()
    if st["running"]:
        st.update(started=STATE["started"], step=STATE["step"], done=STATE["done"], total=STATE["total"], log=list(STATE["log"]))
    st["has_data"] = db.has_data()
    return st


def due(settings=None, at=None, boot=False):
    """Lauf nach Zeitplan fällig? Ohne Datenbank immer; nach einem Fehlschlag frühestens nach einer Stunde."""
    s = settings or load_settings()
    if not db.has_data():
        last = store.load_json("sync.json", {})
        since = _ago(last.get("started"), at or now())
        return since is None or last.get("ok") is not False or since >= timedelta(hours=1)
    if not s["auto"]:
        return False
    last = store.load_json("sync.json", {})
    at = at or now()
    since = _ago(last.get("started"), at)
    if since is None:
        return True
    if last.get("ok") is False:
        return since >= timedelta(hours=1)
    # Nach einem Update mit neuen Tabellen sofort neu bauen, sonst fehlt Neues bis zum nächsten Termin
    if (last.get("stand") or {}).get("importer") not in (None, importer.VERSION) and since >= timedelta(hours=1):
        return True
    return since >= timedelta(days=s["tage"])


class _Source:
    """Eine Quelle in einem Lauf: Pausen, Fehlerzähler, zweiter Versuch nach Netzfehler, Ende bei Sperre."""

    def __init__(self, key, log, pause=PAUSE):
        self.key, self.name, self.log, self.pause = key, NAMES.get(key, key), log, pause
        self.n = self.errors = 0
        self.stopped = ""
        self.blocked = False
        self._last = {}

    def _stop(self, why, where):
        self.stopped, self.blocked = why, True
        self.log(f"{self.name}: {why} bei {where}, Quelle ruht {REST_H} Stunden")

    def get(self, url, raw=False, absent=()):
        """Text (mit raw Bytes) oder None bei Fehler; "" für Statuscodes aus absent („gibt es nicht“)."""
        if self.stopped:
            return None
        host = urllib.parse.urlsplit(url).hostname or ""
        wait = self._last.get(host, 0) + self.pause - time.monotonic()
        if wait > 0:
            sleep(wait)
        self.n += 1
        for attempt in (1, 2):
            try:
                try:
                    body = sources.fetch(url, timeout=90, raw=raw)
                finally:
                    self._last[host] = time.monotonic()
                break
            except sources.FetchError as e:
                if e.status == 0 and attempt == 1:
                    self.log(f"{self.name}: keine Verbindung bei {_short(url)}, zweiter Versuch")
                    sleep(NET_RETRY)
                    continue
                if e.status in absent:
                    return b"" if raw else ""
                if e.status in sources.BLOCKED:
                    self._stop(f"gesperrt (HTTP {e.status})", _short(url))
                else:
                    self.errors += 1
                    self.log(f"{self.name}: {'HTTP ' + str(e.status) if e.status else 'keine Verbindung'} bei {_short(url)}")
                    if self.errors >= MAX_ERRORS:
                        self.stopped = f"{self.errors} Fehler"
                        self.log(f"{self.name}: zu viele Fehler, für diesen Lauf beendet")
                return None
        why = sources.challenge(body[:4000].decode("utf-8", "replace") if raw else body)
        if why:
            self._stop(why, _short(url))
            return None
        return body

    def result(self, **extra):
        return {"at": _iso(now()), "requests": self.n, "errors": self.errors, "ok": not self.stopped,
                "msg": self.stopped, "blocked": self.blocked, **extra}


def _short(url):
    p = urllib.parse.urlsplit(url)
    return p.hostname + (p.path if len(p.path) < 70 else "…" + p.path[-60:])


def _resting(st, key, at):
    until = ((st.get("rest") or {}).get(key)) or ""
    return until if until > _iso(at) else ""


def _hash(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8") if isinstance(p, str) else p)
    return h.hexdigest()[:16]


def csv_list(src, log):
    """Namen der CSV-Dateien und Stand (Commit) der Pokémon-API. Ohne GitHub-API: NEEDED und kein Stand."""
    names, sha = [], ""
    text = src.get(f"{GH_API}/contents/data/v2/csv?ref=master", absent=(403, 404))
    if text:
        try:
            names = sorted(x["name"][:-4] for x in json.loads(text) if str(x.get("name", "")).endswith(".csv"))
        except (ValueError, TypeError, KeyError):
            names = []
    text = src.get(f"{GH_API}/commits?path=data/v2/csv&per_page=1", absent=(403, 404)) if names else ""
    if text:
        try:
            sha = json.loads(text)[0]["sha"]
        except (ValueError, TypeError, KeyError, IndexError):
            sha = ""
    if not names:
        log(f"PokéAPI: Dateiliste von GitHub nicht lesbar, hole die {len(importer.NEEDED)} benötigten Dateien")
        names = list(importer.NEEDED)
    else:
        log(f"PokéAPI: {len(names)} Dateien" + (f", Stand {sha[:7]}" if sha else ""))
    return names, sha


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
    """Datei mit den Bildern, die es nicht gibt. Große Item-Bilder ab 0.13.0 neu: es gibt jetzt mehrere Orte je Bild."""
    return "itemhq2_fehlen.json" if kind == "itemhq" else f"{kind}_fehlen.json"


def media_ids(kind):
    """Was es für eine Bildart geben sollte: {Nummer: Name der Datei bei der Quelle}. Items ohne Maschinen (die haben kein
    eigenes Bild) und ohne unfertige Einträge."""
    con = db.game()
    try:
        if kind == "itembild":
            try:
                return {r[0]: r[1] for r in con.execute("SELECT id, kennung FROM item WHERE tasche != 'Maschinen' AND unfertig = 0 "
                                                        "AND kennung NOT LIKE 'pkhex-%' ORDER BY id")}
            except Exception:           # Datenbank noch ohne die Spalten von 0.8.0
                return {}
        if kind == "formen":
            try:
                return {r[0]: f"{r[1]}-{r[2]}" for r in con.execute(
                    "SELECT f.id, p.species_id, f.form_identifier FROM pokemon_forms f JOIN pokemon p ON p.id = f.pokemon_id "
                    "WHERE f.is_default = 0 AND f.form_identifier != '' AND f.pokemon_id IN "
                    "(SELECT pokemon_id FROM pokemon_forms GROUP BY pokemon_id HAVING COUNT(*) > 1) ORDER BY f.id")}
            except Exception:
                return {}
        if kind == "itemhq":            # Ordner bei Serebii nach dem neuesten Spiel mit dem Item
            try:
                vgs = {k: i for i, k in con.execute("SELECT id, kennung FROM spiel")}
                rows = con.execute("SELECT id, en, spiele, kennung FROM item WHERE tasche != 'Maschinen' AND unfertig = 0 AND en != '' "
                                   "ORDER BY id").fetchall()
            except Exception:           # Datenbank vor 0.12.0 (ohne englische Namen)
                return {}
            out = {}
            big = {vgs.get(k) for ks in ITEM_HQ.values() for k in ks}
            for iid, en, spiele, kennung in rows:
                if not big & set(json.loads(spiele or "[]")) and not str(kennung).startswith("pkhex-"):
                    continue            # ältere Items: das Bild der PokéAPI reicht
                # Ordner der Spiele mit dem Item zuerst, dann der andere, zuletzt das kleine Bild (40 px) für ältere Items
                games, key = set(json.loads(spiele or "[]")), importer.en_key(en)
                subs = sorted(ITEM_HQ, key=lambda sub: (not games & {vgs.get(k) for k in ITEM_HQ[sub]}, sub != "sv"))
                out[iid] = tuple(f"{sub}/{key}" for sub in subs) + (key,)
            return out
        return {r[0]: str(r[0]) for r in con.execute("SELECT id FROM form ORDER BY id")}
    finally:
        con.close()


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
    src = _Source("extras" if kind in EXTRAS else "sprites", log, pause=1.0 if kind == "itemhq" else 0.2)
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


def run(by_hand=False, force=False):
    """Ein Abgleich. force: auch ohne Änderung neu bauen."""
    if not _running.acquire(blocking=False):
        return False
    try:
        return _run(by_hand, force)
    finally:
        STATE.update(step="", done=0, total=0)
        _running.release()


def _run(by_hand, force):
    begun = time.monotonic()
    at = now()
    settings = load_settings()
    prev = store.load_json("sync.json", {})
    st = {"started": _iso(at), "by_hand": by_hand, "ok": False, "log": [], "sources": dict(prev.get("sources") or {}),
          "rest": {k: v for k, v in (prev.get("rest") or {}).items() if v > _iso(at)}, "stand": dict(prev.get("stand") or {}),
          "stats": prev.get("stats") or {}, "built": prev.get("built") or ""}
    STATE.update(started=st["started"], log=st["log"])

    def log(msg):
        line = now().strftime("%H:%M:%S ") + msg
        st["log"].append(line)
        del st["log"][:-LOG_LINES]

    def save():
        store.save_json("sync.json", dict(st, log=st["log"][-LOG_LINES:]))

    log(f"Abgleich gestartet ({'von Hand' if by_hand else 'Zeitplan'}), Pokédex {sources.VERSION}")
    db.migrate()
    name = db.backup()
    if name:
        log(f"Sicherung deiner Daten: sicherung/{name}")
    try:
        ok = _build(st, log, force, at)
        if db.has_data() and settings["sprites"] and not _resting(st, "sprites", at):
            STATE["step"] = "Sprites"
            res = _sprites(log)
            if not res["blocked"]:
                STATE["step"] = "Artworks"
                art = _images("artwork", log)
                res = dict(art, requests=res["requests"] + art["requests"], errors=res["errors"] + art["errors"],
                           neu=res["neu"] + art["neu"], fehlen=res["fehlen"] + art["fehlen"], offen=res["offen"] + art["offen"])
            st["sources"]["sprites"] = res
            if res["blocked"]:
                st["rest"]["sprites"] = _iso(now() + timedelta(hours=REST_H))
        if db.has_data() and settings["sprites"] and not _resting(st, "karten", at):
            STATE["step"] = "Kartenkacheln"
            res = _tiles(log)
            st["sources"]["karten"] = res
            if res["blocked"]:
                st["rest"]["karten"] = _iso(now() + timedelta(hours=REST_H))
        if db.has_data() and not _resting(st, "mapgenie", at):
            STATE["step"] = "Map Genie"
            res = _mapgenie(log)
            st["sources"]["mapgenie"] = res
            if res["blocked"]:
                st["rest"]["mapgenie"] = _iso(now() + timedelta(hours=REST_H))
        if db.has_data() and settings["sprites"] and not _resting(st, "extras", at):
            total = None
            for kind in EXTRAS:
                STATE["step"] = MEDIA_LABEL[kind]
                res = _images(kind, log)
                total = res if total is None else dict(res, **{k: total[k] + res[k] for k in ("requests", "errors", "neu", "fehlen", "offen")})
                if res["blocked"]:
                    break
            st["sources"]["extras"] = total
            if total["blocked"]:
                st["rest"]["extras"] = _iso(now() + timedelta(hours=REST_H))
        st["ok"] = ok
    except Exception as e:          # ein Fehler im Code soll den Dienst nicht beenden
        log(f"Abgebrochen: {type(e).__name__}: {e}")
        st["ok"] = False
    s = int(time.monotonic() - begun)
    st["finished"] = _iso(now())
    log(f"fertig nach {s // 60}:{s % 60:02d} min" + ("" if st["ok"] else ", mit Fehlern"))
    save()
    return True


def _build(st, log, force, at):
    """PokéAPI und Showdown holen und bauen, wenn sich etwas geändert hat. True, wenn alles glatt lief."""
    if _resting(st, "pokeapi", at):
        log(f"PokéAPI ruht bis {st['rest']['pokeapi'][:16].replace('T', ' ')} UTC")
        return db.has_data()
    papi = _Source("pokeapi", log)
    STATE["step"] = "PokéAPI: Dateiliste"
    names, sha = csv_list(papi, log)
    sd = _Source("showdown", log)
    sd_texts, sets = {}, {}
    if not _resting(st, "showdown", at):
        for k in ("pokedex", "moves"):
            STATE["step"] = f"Showdown: {k}.ts"
            t = sd.get(f"{SD_RAW}{k}.ts")
            if t:
                sd_texts[k] = t
        sets = _sets(sd)
        st["sources"]["showdown"] = sd.result(dateien=len(sd_texts) + len(sets))
        if sd.blocked:
            st["rest"]["showdown"] = _iso(now() + timedelta(hours=REST_H))
    pkhex = _pkhex(st, log, at)
    spawns = _spawns(st, log, at)
    wiki = _pokewiki(st, log, at)
    alt = _altissimo(st, log, at)
    comp = _companion(st, log, at)
    if comp:
        alt.setdefault("legends-arceus", {})["companion"] = comp
    extra = importer.load_extra(EXTRA_DIR)
    stand = {"csv": sha, "showdown": _hash(*(sd_texts.get(k, "") for k in ("pokedex", "moves"))) if len(sd_texts) == 2 else "",
             "pkhex": _hash(*(v for src in pkhex.values() for v in src.values())) if pkhex else "",
             "spawns": _hash(json.dumps(spawns, sort_keys=True)) if spawns else "",
             "sets": _hash(json.dumps(sets, sort_keys=True)) if sets else "",
             "wiki": _hash(json.dumps(wiki, sort_keys=True)) if wiki else "",
             "alt": _hash(json.dumps(alt, sort_keys=True)) if alt else "",
             "extra": _hash(json.dumps(extra, sort_keys=True)), "importer": importer.VERSION}
    old = st.get("stand") or {}
    if (db.has_data() and not force and sha and stand["csv"] == old.get("csv") and stand["extra"] == old.get("extra")
            and stand["importer"] == old.get("importer") and (not stand["showdown"] or stand["showdown"] == old.get("showdown"))
            and (not stand["pkhex"] or stand["pkhex"] == old.get("pkhex"))
            and (not stand["spawns"] or stand["spawns"] == old.get("spawns"))
            and (not stand["sets"] or stand["sets"] == old.get("sets"))
            and (not stand["wiki"] or stand["wiki"] == old.get("wiki"))
            and (not stand["alt"] or stand["alt"] == old.get("alt"))):
        log("Keine Änderung bei PokéAPI, Showdown, PKHeX, Spawnpunkten, PokéWiki und Ergänzungen, Datenbank bleibt")
        st["sources"]["pokeapi"] = papi.result(geaendert=False)
        return True
    csvs = cached_csvs(sha) if sha else {}
    if csvs:
        log(f"PokéAPI: Stand {sha[:7]} unverändert, {len(csvs)} Dateien aus dem Zwischenspeicher")
    for i, n in enumerate(names):
        if n in csvs:
            continue
        STATE.update(step=f"PokéAPI: {n}.csv", done=i, total=len(names))
        t = papi.get(f"{CSV_RAW}{n}.csv", absent=(404,))
        if t:
            csvs[n] = t
        if papi.stopped:
            break
    st["sources"]["pokeapi"] = papi.result(dateien=len(csvs), geaendert=True)
    if papi.blocked:
        st["rest"]["pokeapi"] = _iso(now() + timedelta(hours=REST_H))
    missing = [n for n in importer.REQUIRED if n not in csvs]
    if sha and not missing and not papi.stopped:
        save_csv_cache(sha, csvs)
    if missing:
        log("PokéAPI: es fehlen " + ", ".join(missing) + "; die bisherige Datenbank bleibt")
        return False
    STATE.update(step="Datenbank bauen", done=0, total=0)
    tmp = db.pokeapi_path() + ".neu"
    try:
        stats = importer.build(tmp, csvs, sd_texts, extra, pkhex=pkhex, spawns=spawns, sets=sets, wiki=wiki, alt=alt)
    except Exception as e:
        log(f"Neue Datenbank verworfen: {e}; die bisherige bleibt")
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
    os.replace(tmp, db.pokeapi_path())
    if len(sd_texts) < 2:
        stand["showdown"] = old.get("showdown", "")
    if not pkhex:
        stand["pkhex"] = old.get("pkhex", "")
    if not spawns:
        stand["spawns"] = old.get("spawns", "")
    if not sets:
        stand["sets"] = old.get("sets", "")
    if not wiki:
        stand["wiki"] = old.get("wiki", "")
    if not alt:
        stand["alt"] = old.get("alt", "")
    st["stand"], st["stats"], st["built"] = stand, stats, _iso(now())
    log(f"Datenbank neu: {stats['species']} Arten, {stats['forms']} Formen, {stats['moves']} Attacken, {stats['games']} Spiele, "
        f"{stats['tables']} Tabellen" + (f"; Showdown {stats['sd_pokemon']} Pokémon, {stats['sd_moves']} Attacken, "
                                         f"{stats['diff']} Abweichungen zu prüfen" if sd_texts else "; ohne Showdown-Abgleich")
        + (f"; {stats['fundorte']} Fundorte aus PKHeX" if pkhex else "; ohne Fundorte aus PKHeX")
        + (f"; Lernlisten Legenden: Z-A aus PKHeX: {stats['lernen']} Einträge" if stats.get("lernen") else "")
        + (f"; {stats['spawns']} Spawn-Einträge mit Tageszeit und Wetter" if spawns else "")
        + (f"; {stats['sets']} bewährte Sets" if sets else "")
        + (f"; PokéWiki: {stats['wiki_attacken']} Attackenwerte, {stats['wiki_items']} getragene Items, "
           f"{stats.get('wiki_karte', 0)} Stellen auf der Karte" if wiki else "")
        + (f"; Altissimo: {stats['kartenobjekte']} Kartensymbole, {stats['rezepte']} Rezepte" if alt else "")
        + (f"; PLA Companion: {stats.get('orte', 0)} Orte (Schnellreise, Lager)" if comp else "")
        + (f"; {stats['items']} Items" if stats.get("items") else ""))
    return not papi.stopped and not sd.stopped


CSV_CACHE = "pokeapi-csv.json.gz"      # die CSV-Texte des letzten Stands: ein Nachlauf (neue Quelle, Lücken) lädt sie nicht neu


def cached_csvs(sha):
    """{Name: Text} aus dem Zwischenspeicher, wenn er zum Stand sha gehört, sonst {}."""
    path = os.path.join(store.DATA_DIR, CSV_CACHE)
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, EOFError):
        return {}
    return data.get("csv") or {} if data.get("stand") == sha else {}


def save_csv_cache(sha, csvs):
    path = os.path.join(store.DATA_DIR, CSV_CACHE)
    try:
        with gzip.open(path + ".neu", "wt", encoding="utf-8", compresslevel=6) as f:
            json.dump({"stand": sha, "csv": csvs}, f)
        os.replace(path + ".neu", path)
    except OSError:
        pass


def sets_url(gen):
    """Random-Battle-Sets von Showdown je Generation (Generation 1 hat nur data.json mit einem Set je Pokémon)."""
    return f"{SD_RAW}random-battles/gen{gen}/{'data' if gen == 1 else 'sets'}.json"


def _sets(sd):
    """{Generation: Sets} von Showdown; was fehlt oder sich nicht lesen lässt, bleibt weg."""
    out = {}
    for gen in range(1, 10):
        if sd.stopped:
            break
        STATE["step"] = f"Showdown: Sets Generation {gen}"
        t = sd.get(sets_url(gen))
        try:
            data = json.loads(t) if t else None
        except ValueError:
            data = None
        if isinstance(data, dict) and data:
            out[gen] = data
    return out


def _pkhex(st, log, at):
    """Begegnungsdateien aus PKHeX (Spieldaten, GPL-3.0): {Spielkennung: {"begegnungen": Bytes, "orte": Text,
    "orte3": Text (Orte ab 30000: Geschenke), "fest": Quelltext}}."""
    if _resting(st, "pkhex", at):
        log(f"PKHeX ruht bis {st['rest']['pkhex'][:16].replace('T', ' ')} UTC")
        return {}
    src = _Source("pkhex", log)
    out = {}
    texts = {}
    for spiel, (enc, names, fixed) in PKHEX_GAMES.items():
        STATE["step"] = f"PKHeX: {spiel}"
        enc, _, enc2 = enc.partition("|")          # zweite Datei: die andere Edition
        b = src.get(PKHEX_RAW + enc, raw=True)
        for f in (names, names.replace("_00000_", "_30000_")) if b else ():
            if f not in texts:
                texts[f] = src.get(PKHEX_RAW + f) or ""
        t = texts.get(names)
        if b and t:
            out[spiel] = {"begegnungen": b, "orte": t, "orte3": texts.get(names.replace("_00000_", "_30000_"), ""),
                          "fest": (src.get(PKHEX_SRC + fixed) or "") if fixed else ""}
            if enc2:
                out[spiel]["begegnungen2"] = src.get(PKHEX_RAW + enc2, raw=True) or b""
    # Lernlisten für Spiele ohne Lernliste in der PokéAPI (importer.PKHEX_LEARN)
    for key in importer.PKHEX_LEARN:
        STATE["step"] = f"PKHeX: Lernlisten {key}"
        lvl = src.get(PKHEX_RAW + f"byte/levelup/lvlmove_{key}.pkl", raw=True)
        per = src.get(PKHEX_RAW + f"byte/personal/personal_{key}", raw=True) if lvl else None
        if lvl and per:
            out[f"_lernen_{key}"] = {"lvl": lvl, "personal": per}
    # Itemlisten je Spiel und die Itemnamen (deutsch, englisch) für Spiele ohne Liste in der PokéAPI
    STATE["step"] = "PKHeX: Items"
    items = {lang: src.get(PKHEX_RAW + f"text/items/text_Items_{lang}.txt") for lang in ("de", "en")}
    if items["de"] and items["en"]:
        for key in importer.ITEM_LISTS:
            t = src.get(PKHEX_ITEMS + f"ItemStorage{key}.cs")
            if t:
                items[key] = t
        out["_items"] = items
    st["sources"]["pkhex"] = src.result(dateien=sum(len(v) for v in out.values()))
    if src.blocked:
        st["rest"]["pkhex"] = _iso(now() + timedelta(hours=REST_H))
    return out


def _spawns(st, log, at):
    """Spawnpunkte (JS-Finder) und ihre Tabellen nach Tageszeit und Wetter (PLA-Live-Map), beide GPL-3.0:
    {Spielkennung: {Karte: {"gebiet": Name, "punkte": Text, "plaetze": Text}}}."""
    if _resting(st, "spawns", at):
        log(f"Spawnpunkte ruhen bis {st['rest']['spawns'][:16].replace('T', ' ')} UTC")
        return {}
    src = _Source("spawns", log)
    maps = {}
    for karte, gebiet in PLA_MAPS.items():
        STATE["step"] = f"Spawnpunkte: {gebiet}"
        p = src.get(SPAWN_POINTS + karte + ".json")
        t = src.get(SPAWN_SLOTS + karte + ".json") if p else None
        if p and t:
            maps[karte] = {"gebiet": gebiet, "punkte": p, "plaetze": t}
    st["sources"]["spawns"] = src.result(dateien=2 * len(maps))
    if src.blocked:
        st["rest"]["spawns"] = _iso(now() + timedelta(hours=REST_H))
    return {"legends-arceus": maps} if maps else {}


def _altissimo(st, log, at):
    """Kartensymbole, Sammelobjekte und Rezepte für Legenden: Arceus von Altissimo (GPL-3.0):
    {"legends-arceus": {"symbole": {Karte: Text}, "sammeln": {Karte: Text}, "rezepte": HTML}}. Dazu einmal das Kartenbild
    von Jubeldorf in den Datenordner (karten/jubilifevillage/bild.png)."""
    if _resting(st, "altissimo", at):
        log(f"Altissimo ruht bis {st['rest']['altissimo'][:16].replace('T', ' ')} UTC")
        return {}
    src = _Source("altissimo", log)
    sym, col = {}, {}
    for karte, area in altissimo.AREAS.items():
        STATE["step"] = f"Altissimo: {altissimo.GEBIETE[karte]}"
        t = src.get(altissimo.landmarks_url(area))
        if t:
            sym[karte] = t
        t = src.get(altissimo.collectibles_url(area))
        if t:
            col[karte] = t
    t = src.get(altissimo.collectibles_url("jubilife"))
    if t:
        col[altissimo.VILLAGE] = t
    STATE["step"] = "Altissimo: Rezepte"
    rec = src.get(altissimo.RECIPES_URL) or ""
    image = os.path.join(db.data_dir(), "karten", altissimo.VILLAGE, "bild.png")
    if not os.path.isfile(image) and not src.stopped:
        STATE["step"] = "Altissimo: Karte von Jubeldorf"
        b = src.get(altissimo.VILLAGE_IMAGE, raw=True)
        if b and b[:8] == b"\x89PNG\r\n\x1a\n":
            os.makedirs(os.path.dirname(image), exist_ok=True)
            with open(image + ".neu", "wb") as f:
                f.write(b)
            os.replace(image + ".neu", image)
    st["sources"]["altissimo"] = src.result(dateien=len(sym) + len(col) + bool(rec))
    if src.blocked:
        st["rest"]["altissimo"] = _iso(now() + timedelta(hours=REST_H))
    if not sym and not col and not rec:
        return {}
    return {"legends-arceus": {"symbole": sym, "sammeln": col, "rezepte": rec}}


def _companion(st, log, at):
    """Schnellreise und Lager aus dem PLA Companion (software-notion.de): {Karte: Text der Kartendaten}. Zwei Sekunden
    Pause je Anfrage; bei Sperre ruht die Quelle wie die anderen."""
    if _resting(st, "companion", at):
        log(f"PLA Companion ruht bis {st['rest']['companion'][:16].replace('T', ' ')} UTC")
        return {}
    src = _Source("companion", log, pause=2.0)
    out = {}
    for karte in companion.MAPS:
        STATE["step"] = f"PLA Companion: {altissimo.GEBIETE.get(karte, karte)}"
        t = src.get(companion.url(karte))
        if src.stopped:
            break
        if t:
            out[karte] = t
    kinds = {}
    for t in out.values():
        try:
            for e in companion.entries(t):
                kinds[e["t"]] = kinds.get(e["t"], 0) + 1
        except ValueError:
            pass
    if kinds:          # welche Arten es gibt, damit sich weitere Ebenen planen lassen
        log("PLA Companion: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
    st["sources"]["companion"] = src.result(dateien=len(out))
    if src.blocked:
        st["rest"]["companion"] = _iso(now() + timedelta(hours=REST_H))
    return out


def mg_dir(*parts):
    return os.path.join(db.data_dir(), "mapgenie", *parts)


def _mapgenie(log):
    """Karten von Map Genie für alle Spiele in mapgenie.GAMES: je Spiel die Kartenseiten und die Orte, kompakt nach
    data/mapgenie/<Spiel>.json. Kacheln holt erst die Oberfläche (mg_tile). Spiele ohne Karte dort melden 404."""
    src = _Source("mapgenie", log, pause=MG_PAUSE)
    found = 0
    for spiel, slug in mapgenie.GAMES.items():
        STATE["step"] = f"Map Genie: {slug}"
        page = src.get(mapgenie.game_url(slug), absent=(404,))
        if src.stopped:
            break
        if not page:
            continue
        maps = []
        for k in mapgenie.map_slugs(page, slug)[:12]:
            p = src.get(mapgenie.map_url(slug, k), absent=(404,))
            md = (mapgenie._var(p, "mapData") or {}).get("map") or {} if p else {}
            d = src.get(mapgenie.data_url(md["id"]), absent=(404,)) if md.get("id") else None
            m = mapgenie.parse(p, d) if p and d else None
            if m:
                m["slug"] = m["slug"] or k
                maps.append(m)
            if src.stopped:
                break
        if maps:
            os.makedirs(mg_dir(), exist_ok=True)
            store.save_json(os.path.join("mapgenie", spiel + ".json"), {"spiel": spiel, "slug": slug, "am": _iso(now()), "karten": maps})
            log(f"Map Genie: {slug} mit {len(maps)} Karten, {sum(len(m['orte']) for m in maps)} Orten")
            found += 1
    return src.result(dateien=found)


def mg_maps(spiel):
    """Gespeicherte Map-Genie-Karten eines Spiels (Erweiterungen: die des Hauptspiels) oder None."""
    spiel = mapgenie.SHARE.get(spiel, spiel)
    if spiel not in mapgenie.GAMES:
        return None
    f = mg_dir(spiel + ".json")
    try:
        mt = os.path.getmtime(f)
    except OSError:
        return None
    hit = _mg_cache.get(spiel)
    if not hit or hit[0] != mt:
        hit = _mg_cache[spiel] = (mt, store.load_json(os.path.join("mapgenie", spiel + ".json"), {}) or None)
    return hit[1]


_mg_cache = {}


_mg_lock = threading.Lock()
_mg = {"last": 0.0, "rest": "", "miss": set()}


def mg_tile(spiel, karte, z, x, y):
    """Pfad einer Kachel im Datenordner; fehlt sie, einmal bei Map Genie holen (eine Anfrage zur Zeit, kurze Pause,
    bei 403/429 ruht die Quelle 24 Stunden). None, wenn es sie nicht gibt."""
    d = mg_maps(spiel)
    m = next((m for m in (d or {}).get("karten", []) if m["slug"] == karte), None)
    rel = mapgenie.tile_ok(m["kacheln"], z, x, y) if m else None
    if not rel or not (m["min_zoom"] - 2 <= z <= m["max_zoom"]):
        return None
    f = mg_dir("kacheln", *rel.split("/"))
    if os.path.isfile(f):
        return f
    with _mg_lock:
        if os.path.isfile(f):
            return f
        if rel in _mg["miss"] or _mg["rest"] > _iso(now()):
            return None
        wait = _mg["last"] + MG_TILE_PAUSE - time.monotonic()
        if wait > 0:
            sleep(wait)
        try:
            body = sources.fetch(mapgenie.TILES + rel, timeout=30, raw=True)
        except sources.FetchError as e:
            if e.status in sources.BLOCKED:
                _mg["rest"] = _iso(now() + timedelta(hours=REST_H))
            elif e.status:
                _mg["miss"].add(rel)
            return None
        finally:
            _mg["last"] = time.monotonic()
        if not (body[:8] == b"\x89PNG\r\n\x1a\n" or body[:3] == b"\xff\xd8\xff" or body[8:12] == b"WEBP"):
            _mg["miss"].add(rel)
            return None
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f + ".neu", "wb") as fh:
            fh.write(body)
        os.replace(f + ".neu", f)
        return f


def wiki_titles(con, spiel):
    """Deutsche Namen der Attacken, die im Spiel jemand lernt, und der Arten im Spiel (Seitentitel im PokéWiki)."""
    g = con.execute("SELECT id FROM spiel WHERE kennung = ?", (spiel,)).fetchone()
    if not g:
        return [], []
    moves = [r[0] for r in con.execute("SELECT DISTINCT a.name FROM pokemon_moves pm JOIN attacke a ON a.id = pm.move_id "
                                       "WHERE pm.version_group_id = ? ORDER BY a.name", (g[0],)) if r[0]]
    species = [r[0] for r in con.execute(
        "SELECT DISTINCT n.name FROM spiel_form sf JOIN form f ON f.id = sf.form JOIN pokemon_species_names n "
        "ON n.pokemon_species_id = f.art AND n.local_language_id = 6 WHERE sf.spiel = ? ORDER BY n.name", (g[0],)) if r[0]]
    return moves, species


def _pokewiki(st, log, at):
    """Werte aus dem PokéWiki, die sonst fehlen: {"attacken": {Spiel: {Name: Werte}}, "items": {Spiel: {Art: [Items]}}}.
    Die Namen kommen aus der bisherigen Datenbank (ohne sie gibt es noch nichts zu fragen). Bei Sperre oder Fehlern gilt
    das Ergebnis des letzten Laufs (pokewiki.json im Datenordner)."""
    old = store.load_json("pokewiki.json", {})
    if _resting(st, "pokewiki", at):
        log(f"PokéWiki ruht bis {st['rest']['pokewiki'][:16].replace('T', ' ')} UTC")
        return old
    con = db.game()
    if con is None:
        return old
    try:
        titles = {sp: wiki_titles(con, sp) for sp in WIKI_GAMES}
    except Exception as e:
        log(f"PokéWiki: Namen nicht lesbar ({e})")
        return old
    finally:
        con.close()
    src = _Source("pokewiki", log, pause=WIKI_PAUSE)
    out = {"attacken": {}, "items": {}}
    for sp, (moves, species) in titles.items():
        for kind, names, section0 in (("attacken", moves, True), ("items", species, False)):
            got = {}
            for i in range(0, len(names), pokewiki.BATCH):
                STATE.update(step=f"PokéWiki: {'Attacken' if kind == 'attacken' else 'Pokémon'}", done=i, total=len(names))
                t = src.get(pokewiki.batch_url(names[i:i + pokewiki.BATCH], section0))
                if src.stopped:
                    break
                try:
                    for name, wt in pokewiki.pages(t or "{}").items():
                        v = pokewiki.la_move(wt) if kind == "attacken" else [x for x in pokewiki.held_items(wt) if x["spiel"] == sp]
                        if v:
                            got[name] = v
                except ValueError as e:
                    log(f"PokéWiki: Antwort nicht lesbar ({e})")
            out[kind][sp] = got
        if src.stopped:
            break
    # Karte von Legenden: Arceus (Kristalle, Verzerrungen, Massenauftreten, Bäume, Alphas, Items am Boden)
    karte = {}
    for i, area in enumerate(pokewiki.MAP_AREAS if not src.stopped else ()):
        STATE.update(step="PokéWiki: Karte", done=i, total=len(pokewiki.MAP_AREAS))
        got = {kind: src.get(pokewiki.map_url(kind, area)) for kind in pokewiki.MAP_KINDS}
        if src.stopped:
            break
        if got.get("pokemon"):
            karte[area] = {k: v for k, v in got.items() if v}
    out["karte"] = {"legends-arceus": karte} if karte else old.get("karte", {})
    st["sources"]["pokewiki"] = src.result(seiten=sum(len(v) for k in ("attacken", "items") for v in out[k].values()),
                                           karten=len(karte))
    if src.blocked:
        st["rest"]["pokewiki"] = _iso(now() + timedelta(hours=REST_H))
    if src.stopped or not any(out["attacken"].values()):
        return old
    store.save_json("pokewiki.json", out)
    return out


def start(force=False):
    """Lauf im Hintergrund. False, wenn schon einer läuft."""
    if _running.locked():
        return False
    threading.Thread(target=run, kwargs={"by_hand": True, "force": bool(force)}, daemon=True, name="abgleich").start()
    return True


def scheduler():
    """Prüft jede Minute, ob ein Lauf fällig ist; ohne Datenbank gleich, sonst erst nach BOOT_WAIT_S."""
    if db.has_data():
        time.sleep(BOOT_WAIT_S)
    boot = True
    while True:
        try:
            if due(boot=boot) and not _running.locked():
                run()
            db.backup()
        except Exception as e:
            print("Zeitplan:", e, file=sys.stderr)
        boot = False
        time.sleep(60)


PKHEX_RAW = "https://raw.githubusercontent.com/kwsch/PKHeX/master/PKHeX.Core/Resources/"
PKHEX_ITEMS = "https://raw.githubusercontent.com/kwsch/PKHeX/master/PKHeX.Core/Items/"
PKHEX_SRC = "https://raw.githubusercontent.com/kwsch/PKHeX/master/PKHeX.Core/Legality/Encounters/Data/"
POKEAPI_RAW = "https://raw.githubusercontent.com/PokeAPI/"
PROBE_MAX = 60_000          # so viele Zeichen je Probe-Seite behält der Verbindungstest


pkhex_areas = importer.pkhex_areas
# Spiele mit Begegnungsdatei und deutschen Ortsnamen (weitere folgen, sobald ihr Format gelesen wird)
# Karten in Legenden: Arceus: Name bei PLA-Live-Map, JS-Finder und Serebii → Gebiet (wie in PKHeX)
PLA_MAPS = {"obsidianfieldlands": "Obsidian-Grasland", "crimsonmirelands": "Rotes Sumpfland",
            "cobaltcoastlands": "Kobalt-Küstenland", "coronethighlands": "Kraterberg-Hochland",
            "alabastericelands": "Weißes Frostland"}
SPAWN_POINTS = "https://raw.githubusercontent.com/Lincoln-LM/JS-Finder/main/Resources/pla_spawners/jsons/"
SPAWN_SLOTS = "https://raw.githubusercontent.com/Lincoln-LM/PLA-Live-Map/main/static/resources/"
# Erweiterungen bekommen die Fundorte ihres Hauptspiels dazu (importer.PKHEX_SHARE); Mega-Dimension hat eigene
PKHEX_GAMES = {"brilliant-diamond-shining-pearl": ("legality/wild/Gen8/encounter_bd.pkl|legality/wild/Gen8/encounter_sp.pkl",
                                                   "text/locations/gen8b/text_bdsp_00000_de.txt", "Gen8/Encounters8b.cs"),
               "legends-arceus": ("legality/wild/Gen8/encounter_la.pkl", "text/locations/gen8a/text_la_00000_de.txt",
                                   "Gen8/Encounters8a.cs"),
               "scarlet-violet": ("legality/wild/Gen9/encounter_wild_paldea.pkl", "text/locations/gen9/text_sv_00000_de.txt",
                                  "Gen9/Encounters9.cs"),
               "legends-za": ("legality/wild/Gen9/encounter_za.pkl", "text/locations/gen9a/text_za_00000_de.txt",
                              "Gen9/Encounters9a.cs"),
               "mega-dimension": ("legality/wild/Gen9/encounter_hyperspace_za.pkl", "text/locations/gen9a/text_za_00000_de.txt", "")}


def diagnose(proben=None):
    """Verbindung testen: jede Quelle einmal abfragen und beschreiben, was zurückkommt. Speichert nichts.
    proben: dict, in das Probe-Seiten (gekürzt) kommen, damit sich Leser für neue Quellen bauen lassen."""
    lines = [f"Pokédex {sources.VERSION}, Test vom {now().strftime('%d.%m.%Y %H:%M')} UTC"]
    proben = {} if proben is None else proben
    html = {"Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}

    def probe(name, url, info, raw=False, keep=False, headers=None):
        r = sources.request(url, raw=raw, headers=headers)
        if r["error"]:
            lines.append(f"{name}: keine Verbindung ({r['error']})")
            return None
        size = len(r.get("body", b"")) if raw else len(r["text"])
        head = f"{name}: HTTP {r['status']}, Server {r['server'] or '?'}, {size} {'Bytes' if raw else 'Zeichen'}"
        if r["status"] >= 400 or (not raw and sources.challenge(r["text"])):
            lines.append(head + (", gesperrt" if r["status"] in sources.BLOCKED else "") +
                         (", Prüfseite (Cloudflare)" if not raw and sources.challenge(r["text"]) else "") +
                         ("" if raw else f". Anfang: {' '.join(r['text'][:160].split())}"))
            return None
        try:
            lines.append(f"{head}, {info(r.get('body') if raw else r['text'])}")
        except Exception as e:
            lines.append(f"{head}, nicht auswertbar ({type(e).__name__}: {e})")
        if keep and not raw:
            proben[name] = r["text"][:keep if keep is not True else PROBE_MAX]
        sleep(PAUSE)
        return r

    def section(title):
        lines.append("")
        lines.append(f"== {title}")

    section("Heutige Quellen")

    def gh_list(text):
        n = [x for x in json.loads(text) if str(x.get("name", "")).endswith(".csv")]
        return f"{len(n)} CSV-Dateien gelistet"
    probe("GitHub-API, Dateiliste PokéAPI", f"{GH_API}/contents/data/v2/csv?ref=master", gh_list)

    def csv_info(text):
        rows = text.strip().splitlines()
        return f"{len(rows) - 1} Zeilen, Spalten: {rows[0][:80]}"
    probe("PokéAPI, types.csv", CSV_RAW + "types.csv", csv_info)

    def sd_info(text):
        from . import showdown
        return f"{len(showdown.pokedex(text))} Einträge erkannt"
    probe("Showdown, pokedex.ts", SD_RAW + "pokedex.ts", sd_info)
    probe("Sprites, Bild 25", SPRITE_RAW + "25.png", lambda b: "PNG" if b[:4] == b"\x89PNG" else "kein PNG", raw=True)

    section("Items (Namen, Beschreibungen, je Spiel)")
    probe("PokéAPI, items.csv", CSV_RAW + "items.csv", csv_info)
    probe("PokéAPI, item_flavor_text.csv", CSV_RAW + "item_flavor_text.csv", csv_info)
    probe("Showdown, items.ts", SD_RAW + "items.ts", lambda t: f"{t.count('num:')} Items mit Nummer")
    probe("PKHeX, Itemnamen deutsch", PKHEX_RAW + "text/items/text_Items_de.txt",
          lambda t: f"{sum(1 for x in t.splitlines() if x.strip())} Namen (alle Spiele bis Legenden: Z-A)")
    probe("PKHeX, Itemliste Legenden: Arceus", PKHEX_ITEMS + "ItemStorage8LA.cs",
          lambda t: ", ".join(f"{k} {len(v)}" for k, v in importer.pkhex_spans(t).items()) or "keine Listen erkannt")
    probe("Altissimo, Rezepte Legenden: Arceus", altissimo.RECIPES_URL,
          lambda t: "{} Rezepte, {} Zutaten mit Fundorten".format(*map(len, altissimo.recipes(t))))

    section("Kartensymbole und Sammelobjekte (Altissimo, GPL-3.0)")
    probe("Altissimo, Symbole Obsidian-Grasland", altissimo.landmarks_url("fieldlands"),
          lambda t: f"{len(altissimo.landmarks(t, altissimo.FIT['obsidianfieldlands']))} Bäume, Erzbrocken und Haufen")
    probe("Altissimo, Sammelobjekte Jubeldorf", altissimo.collectibles_url("jubilife"),
          lambda t: f"{len(altissimo.collectibles(t, altissimo.VILLAGE_FIT))} Geisterlichter und Icognito")
    probe("Altissimo, Karte Jubeldorf", altissimo.VILLAGE_IMAGE, lambda b: "PNG" if b[:4] == b"\x89PNG" else "kein PNG", raw=True)

    section("Fundorte aus den Spieldaten (PKHeX, GPL-3.0)")

    def la_info(b):
        areas = pkhex_areas(b)
        slots = sum(len(x[2]) for x in areas)
        alpha = sum(1 for x in areas for s in x[2] if s[4])
        return f"{len(areas)} Gebiete, {slots} Begegnungen, davon {alpha} Alpha (mit Level von–bis)"
    probe("PKHeX, Begegnungen Legenden: Arceus", PKHEX_RAW + "legality/wild/Gen8/encounter_la.pkl", la_info, raw=True)
    names = lambda t: f"{sum(1 for x in t.splitlines() if x.strip() and not x.startswith('－'))} Ortsnamen"
    probe("PKHeX, Orte Legenden: Arceus deutsch", PKHEX_RAW + "text/locations/gen8a/text_la_00000_de.txt", names)
    pkl = lambda b: (f"Datei {b[:2].decode('ascii')!r}, {int.from_bytes(b[2:4], 'little')} Einträge"
                     if b[:2].isalpha() else f"Binärdaten, {len(b)} Bytes (Format noch zu lesen)")
    probe("PKHeX, Begegnungen Karmesin/Purpur", PKHEX_RAW + "legality/wild/Gen9/encounter_wild_paldea.pkl", la_info, raw=True)
    probe("PKHeX, Orte Karmesin/Purpur deutsch", PKHEX_RAW + "text/locations/gen9/text_sv_00000_de.txt", names)
    probe("PKHeX, Begegnungen Legenden: Z-A", PKHEX_RAW + "legality/wild/Gen9/encounter_za.pkl", la_info, raw=True)
    probe("PKHeX, Lernlisten Legenden: Z-A", PKHEX_RAW + "byte/levelup/lvlmove_za.pkl", lambda b: f"{len(b)} Bytes, {int.from_bytes(b[2:4], 'little') if b[:2] == b'za' else 0} Lernlisten" if b else "leer", raw=True)
    probe("PKHeX, Begegnungen Mega-Dimension", PKHEX_RAW + "legality/wild/Gen9/encounter_hyperspace_za.pkl", la_info, raw=True)
    probe("PKHeX, Orte Legenden: Z-A deutsch", PKHEX_RAW + "text/locations/gen9a/text_za_00000_de.txt", names)
    probe("PKHeX, Beherrschung Legenden: Arceus", PKHEX_RAW + "legality/misc/mastery_la.pkl", pkl, raw=True)
    probe("PKHeX, Level-Attacken Legenden: Arceus", PKHEX_RAW + "byte/levelup/lvlmove_la.pkl", pkl, raw=True)

    section("Weitere Spieldaten (PKHeX): feste Begegnungen, Raids, Werte")

    def static_info(t):
        st = importer.pkhex_static(t)
        return f"{len(st)} feste Begegnungen (Geschenke, Legendäre, feste Pokémon) mit Art, Level und Ort"
    probe("PKHeX, feste Begegnungen Legenden: Arceus", PKHEX_SRC + "Gen8/Encounters8a.cs", static_info)
    probe("PKHeX, feste Begegnungen Karmesin/Purpur", PKHEX_SRC + "Gen9/Encounters9.cs", static_info)
    probe("PKHeX, feste Begegnungen Legenden: Z-A", PKHEX_SRC + "Gen9/Encounters9a.cs", static_info)
    probe("PKHeX, Tera-Raids Karmesin/Purpur", PKHEX_RAW + "legality/wild/Gen9/encounter_gem_paldea.pkl", pkl, raw=True)
    probe("PKHeX, Event-Raids Karmesin/Purpur", PKHEX_RAW + "legality/wild/Gen9/encounter_dist_paldea.pkl", pkl, raw=True)
    probe("PKHeX, 7-Sterne-Raids Karmesin/Purpur", PKHEX_RAW + "legality/wild/Gen9/encounter_might_paldea.pkl", pkl, raw=True)
    probe("PKHeX, feste Symbole Karmesin/Purpur", PKHEX_RAW + "legality/wild/Gen9/encounter_fixed_paldea.pkl", pkl, raw=True)
    probe("PKHeX, Werte je Form Legenden: Arceus", PKHEX_RAW + "byte/personal/personal_la",
          lambda b: f"{len(b)} Bytes (Basiswerte, Fangrate, Formen wie im Spiel)", raw=True)

    section("Karte (Legenden: Arceus)")
    probe("JS-Finder, Spawnpunkte Obsidian-Grasland", SPAWN_POINTS + "obsidianfieldlands.json",
          lambda t: f"{len(json.loads(t))} Spawnpunkte mit Koordinaten")
    probe("PLA-Live-Map, Tabellen Obsidian-Grasland", SPAWN_SLOTS + "obsidianfieldlands.json",
          lambda t: f"{len(json.loads(t))} Tabellen nach Tageszeit und Wetter")
    probe("Serebii, Kartenkachel", MAP_TILES + "obsidianfieldlands/tile_0-0-0.png",
          lambda b: "PNG" if b[:4] == b"\x89PNG" else "kein PNG", raw=True, headers={"Accept": "image/png,image/*;q=0.8"})

    section("Mögliche Quellen zum Testen: Item-Bilder, Lager und Schnellreise")

    def png(b):
        if b[:8] != b"\x89PNG\r\n\x1a\n":
            return "kein PNG"
        return f"PNG {int.from_bytes(b[16:20], 'big')} × {int.from_bytes(b[20:24], 'big')} px"
    img = {"Accept": "image/png,image/*;q=0.8"}
    for path in ("itemdex/sprites/apricorn.png", "itemdex/sprites/legends/apricorn.png", "itemdex/sprites/potion.png",
                 "itemdex/sprites/sv/potion.png"):
        probe(f"Serebii, Item-Bild {path.split('sprites/')[1]}", SEREBII + path, png, raw=True, headers=img)

    def markers(t):
        low = t.lower()
        keys = ("camp", "fast travel", "distortion", "outbreak", "marker", ".json", "oldverse", "crystal")
        return ", ".join(f"{k} {low.count(k)}×" for k in keys)
    probe("Serebii, Karte Obsidian-Grasland (Seite)", SEREBII + "pokearth/hisui/obsidianfieldlands.shtml", markers, keep=400_000, headers=html)

    # Weitere Karten zum Vergleich: GamerGuides (Lager, Schnellreise, Sammelobjekte) und Pokébip (französisch)
    def scan(t):
        low = t.lower()
        keys = ("camp", "fast travel", "marker", "markers", "lat", "leaflet", "mapbox", "__next_data__", "api/", ".json",
                "wisp", "unown", "distortion", "outbreak", "marqueur", "campement", "voyage rapide")
        hits = ", ".join(f"{k} {low.count(k)}×" for k in keys if low.count(k))
        js = sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', t)))[:6]
        return (hits or "keine Stichwörter") + (f"; Skripte: {', '.join(js)}" if js else "")
    probe("GamerGuides, Karte Obsidian-Grasland", GAMERGUIDES + "pokemon-legends-arceus/maps/obsidian-fieldlands", scan,
          keep=400_000, headers=html)
    probe("GamerGuides, Karte Jubeldorf", GAMERGUIDES + "pokemon-legends-arceus/maps/jubilife-village", scan, keep=400_000, headers=html)
    probe("Pokébip, Karte Obsidian-Grasland", POKEBIP + "page/jeuxvideo/legendes-pokemon-arceus/cartes-interactives/plaines-obsidiennes",
          scan, keep=400_000, headers=html)
    probe("Pokébip, Massenauftreten", POKEBIP + "page/jeuxvideo/legendes-pokemon-arceus/megapparitions", scan, keep=200_000, headers=html)

    def wiki_list(t):
        q = json.loads(t).get("query") or {}
        xs = q.get("allimages") or q.get("search") or []
        return "; ".join(f"{x.get('name') or x.get('title')}" + (f" ({x['width']}×{x['height']})" if x.get("width") else "") for x in xs[:12]) or "nichts"
    probe("PokéWiki, Bilder „Aprikoko…“", POKEWIKI_API + "?" + urllib.parse.urlencode(
        {"action": "query", "list": "allimages", "aiprefix": "Aprikoko", "aiprop": "url|size", "ailimit": "20", "format": "json"}),
        wiki_list, keep=True)
    probe("PokéWiki, Suche Schnellreise", POKEWIKI_API + "?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Schnellreise Basislager Hisui", "srlimit": "15", "format": "json"}),
        wiki_list, keep=True)
    probe("PokéWiki, Seite Basislager", POKEWIKI_API + "?" + urllib.parse.urlencode(
        {"action": "parse", "page": "Basislager", "prop": "wikitext", "format": "json"}),
        lambda t: f"{len(t)} Zeichen Wikitext", keep=True)

    section("Bilder und Rufe (PokéAPI-Repos)")
    img = lambda kind: (lambda b: kind if b[:4] in (b"\x89PNG", b"GIF8") else "unbekanntes Format")
    probe("Sprites, schillernd 25", POKEAPI_RAW + "sprites/master/sprites/pokemon/shiny/25.png", img("PNG"), raw=True)
    probe("Sprites, animiert 25", POKEAPI_RAW + "sprites/master/sprites/pokemon/other/showdown/25.gif", img("GIF"), raw=True)
    probe("Rufe, Pokémon 25", POKEAPI_RAW + "cries/main/cries/pokemon/latest/25.ogg",
          lambda b: "Ogg-Audio" if b[:4] == b"OggS" else "MP3-Audio" if b[:3] == b"ID3" or b[:2] == b"\xff\xfb"
          else "unbekanntes Format", raw=True)

    section("Schon geladen, noch ungenutzt (PokéAPI in pokeapi.db)")
    if db.has_data():
        con = db.game()
        try:
            for label, sql in (("TM und VM je Spiel", "SELECT COUNT(*) FROM machines"),
                               ("Wesen", "SELECT COUNT(*) FROM natures"),
                               ("Ei-Gruppen je Pokémon", "SELECT COUNT(*) FROM pokemon_egg_groups"),
                               ("Fangraten", "SELECT COUNT(capture_rate) FROM pokemon_species"),
                               ("Beeren", "SELECT COUNT(*) FROM berries"),
                               ("EV-Ausbeute", "SELECT COUNT(*) FROM pokemon_stats WHERE effort > 0")):
                try:
                    lines.append(f"{label}: {con.execute(sql).fetchone()[0]} Einträge")
                except Exception as e:
                    lines.append(f"{label}: nicht in der Datenbank ({e})")
        finally:
            con.close()
    else:
        lines.append("Noch keine Datenbank: erst einen Abgleich starten.")

    section("Wikis und Datenbanken (Fundorte mit Tageszeit, Attackenwerte, Karten)")

    def wiki_info(text):
        g = json.loads(text)["query"]["general"]
        return f"{g.get('sitename')} auf MediaWiki {g.get('generator', '?').split()[-1]}"

    def wiki_page(text):
        p = json.loads(text)["parse"]
        wt = p["wikitext"]["*"] if isinstance(p["wikitext"], dict) else p["wikitext"]
        return f"Seite „{p['title']}“, {len(wt)} Zeichen Wikitext, {wt.count('{{')} Vorlagen"
    probe("PokéWiki, API", POKEWIKI_API + "?action=query&meta=siteinfo&format=json", wiki_info)
    for page in ("Pokémon-Legenden: Arceus", "Bidiza", "Obsidian-Grasland", "Tackle", "Kraftstil", "Alpha-Pokémon",
                 "Forschungsaufgabe", "Edelhorde", "Raum-Zeit-Verzerrung"):
        probe(f"PokéWiki, Seite {page}", POKEWIKI_API + "?action=parse&page=" + urllib.parse.quote(page)
              + "&prop=wikitext&format=json&redirects=1", wiki_page, keep=True)
    def wiki_batch(text):
        got = pokewiki.pages(text)
        vals = {k: pokewiki.la_move(v) for k, v in got.items()}
        return f"{len(got)} Seiten gebündelt; " + "; ".join(f"{k}: {v}" for k, v in vals.items())
    probe("PokéWiki, Bündel Attacken (Legenden: Arceus)", pokewiki.batch_url(["Tackle", "Donnerblitz", "Kraftschub"], True), wiki_batch)
    probe("Bulbapedia, API", "https://bulbapedia.bulbagarden.net/w/api.php?action=query&meta=siteinfo&format=json", wiki_info)
    probe("Bulbapedia, Seite Bidoof", "https://bulbapedia.bulbagarden.net/w/api.php?action=parse&page=Bidoof_(Pok%C3%A9mon)"
          "&prop=wikitext&format=json&redirects=1", wiki_page, keep=True)
    # 0.13.0: Fangfaktoren der Hisui-Bälle zum Gegenprüfen (Bulbapedia und PokéWiki), Kartendaten des PLA Companion
    for page in ("Heavy_Ball_(Hisui)", "Feather_Ball", "Ultra_Ball_(Hisui)"):
        probe(f"Bulbapedia, Seite {page}", "https://bulbapedia.bulbagarden.net/w/api.php?action=parse&page=" + page
              + "&prop=wikitext&format=json&redirects=1", wiki_page, keep=True)
    for page in ("Schwerball", "Federball", "Hyperball"):
        probe(f"PokéWiki, Seite {page}", POKEWIKI_API + "?" + urllib.parse.urlencode(
            {"action": "parse", "page": page, "prop": "wikitext", "format": "json", "redirects": 1}), wiki_page, keep=True)
    def kinds(t):
        n = {}
        for e in companion.entries(t):
            n[e["t"]] = n.get(e["t"], 0) + 1
        return "Einträge mit Lage: " + ", ".join(f"{k} {v}" for k, v in sorted(n.items()))
    probe("PLA Companion, Karte Obsidian-Grasland", companion.url("obsidianfieldlands"), kinds, keep=True)
    # Karten weiterer Spiele: welche Dateien die offenen Projekte haben (Kartenbilder, Koordinaten), als Probe zum Herunterladen
    def tree(t):
        ps = [x.get("path", "") for x in json.loads(t).get("tree", [])]
        hits = [x for x in ps if re.search(r"(?i)(paldea|kitakami|terarium|lumiose|z-?a|scarlet|violet|sv)[^/]*$|map", x)
                and re.search(r"(?i)\.(json|png|jpe?g|webp|js|html)$", x)]
        return f"{len(ps)} Dateien, davon {len(hits)} zu Karten und neueren Spielen: " + ", ".join(hits[:12])
    probe("GitHub: Dateien von sv-live-map (Karmesin/Purpur)", "https://api.github.com/repos/Lincoln-LM/sv-live-map/git/trees/master?recursive=1",
          tree, keep=True)
    probe("GitHub: Dateien von Altissimo", "https://api.github.com/repos/Altissimo1/altissimo1.github.io/git/trees/main?recursive=1",
          tree, keep=True)
    probe("sv-live-map: Tera-Raid-Höhlen (Spielkoordinaten)",
          "https://raw.githubusercontent.com/Lincoln-LM/sv-live-map/master/resources/den_locations.json",
          lambda t: f"{len(json.loads(t))} Höhlen")
    page_info = lambda t: f"Titel „{(t.split('<title>')[1].split('</title>')[0].strip() if '<title>' in t else '?')[:80]}“"
    probe("Serebii, Legenden: Arceus Bidiza", "https://www.serebii.net/pokedex-swsh/bidoof/", page_info, keep=True, headers=html)
    probe("Serebii, Legenden: Arceus Übersicht", "https://www.serebii.net/legendsarceus/", page_info, keep=True, headers=html)
    probe("Pokémon Database, Legenden: Arceus", "https://pokemondb.net/pokedex/game/legends-arceus", page_info, keep=True, headers=html)
    for spiel, slug in mapgenie.GAMES.items():
        probe(f"Map Genie, {slug}", mapgenie.game_url(slug),
              lambda t, s=slug: page_info(t) + ", Karten: " + (", ".join(mapgenie.map_slugs(t, s)) or "keine"), headers=html)
    # ältere Spiele: interaktive Karten mit Symbolen (Items, Trainer, Pokémon) zum Abhaken
    for g in ("Yellow", "Crystal", "Emerald", "Platinum", "Red", "Gold", "FireRed", "HeartGold", "Black", "X", "Sun"):
        probe(f"pokemoncompletion, {g}", f"https://pokemoncompletion.com/completion/{g}", page_info, keep=200_000, headers=html)

    section("Kampfdaten (Movesets, Nutzung)")
    probe("pkmn, Smogon-Sets Gen 9", "https://data.pkmn.cc/sets/gen9.json",
          lambda t: f"{len(json.loads(t))} Pokémon mit Sets")
    probe("Smogon, Nutzungsstatistik", "https://www.smogon.com/stats/", lambda t: f"{t.count('href=')} Einträge")
    probe("Showdown, learnsets.ts", SD_RAW + "learnsets.ts", lambda t: f"{t.count('learnset:')} Lernlisten (TM, Lehrer, Ei je Generation)")
    probe("Showdown, formats-data.ts", SD_RAW + "formats-data.ts", lambda t: f"{t.count('tier:')} Pokémon mit Stufe (OU, UU …)")
    probe("Showdown, Random-Battle-Sets Gen 9", SD_RAW + "random-battles/gen9/sets.json",
          lambda t: f"{len(json.loads(t))} Pokémon mit Rollen und Attacken")
    probe("Showdown, abilities.ts", SD_RAW + "abilities.ts", lambda t: f"{t.count('num:')} Fähigkeiten mit Wirkung im Code")
    if proben:
        lines.append("")
        lines.append(f"{len(proben)} Probe-Seiten zum Herunterladen (Knopf „Proben herunterladen“).")
    return lines
