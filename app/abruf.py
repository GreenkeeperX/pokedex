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
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from . import db, importer, pokewiki, sources, store

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
         "karten": "Kartenbilder", "extras": "Extras (schillernd, animiert, Rufe)", "pokewiki": "PokéWiki"}
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
          "itembild": (SPRITE_RAW.replace("/pokemon/", "/items/"), ".png")}
MEDIA_LABEL = {"sprites": "Sprites", "artwork": "Artworks", "shiny": "Schillernde Sprites", "shinyart": "Schillernde Artworks",
               "anim": "Animierte Sprites", "rufe": "Rufe", "itembild": "Item-Bilder"}


def media_ids(kind):
    """Was es für eine Bildart geben sollte: {Nummer: Name der Datei bei der Quelle}. Items ohne Maschinen (die haben kein
    eigenes Bild) und ohne unfertige Einträge."""
    con = db.game()
    try:
        if kind == "itembild":
            try:
                return {r[0]: r[1] for r in con.execute("SELECT id, kennung FROM item WHERE tasche != 'Maschinen' AND unfertig = 0 ORDER BY id")}
            except Exception:           # Datenbank noch ohne die Spalten von 0.8.0
                return {}
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
        gone = store.load_json(f"{kind}_fehlen.json", {})
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
    src = _Source("extras" if kind in EXTRAS else "sprites", log, pause=0.2)
    prefix, ext = EXTRAS.get(kind, (IMAGES.get(kind), ".png"))
    folder = os.path.join(db.data_dir(), kind)
    os.makedirs(folder, exist_ok=True)
    names = media_ids(kind)
    ids = list(names)
    miss_file = f"{kind}_fehlen.json"
    miss = store.load_json(miss_file, {})
    cutoff = _iso(now() - timedelta(days=SPRITE_MISS_DAYS))
    have = {os.path.splitext(x)[0] for x in os.listdir(folder)}
    todo = [i for i in ids if str(i) not in have and (miss.get(str(i)) or "") < cutoff]
    got = absent = 0
    label = MEDIA_LABEL[kind]
    for n, i in enumerate(todo[:limit]):
        STATE.update(step=label, done=n, total=min(len(todo), limit))
        body = src.get(f"{prefix}{names[i]}{ext}", raw=True, absent=(404,))
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


MAP_TILES = "https://www.serebii.net/pokearth/hisui/"
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
    extra = importer.load_extra(EXTRA_DIR)
    stand = {"csv": sha, "showdown": _hash(*(sd_texts.get(k, "") for k in ("pokedex", "moves"))) if len(sd_texts) == 2 else "",
             "pkhex": _hash(*(v for src in pkhex.values() for v in src.values())) if pkhex else "",
             "spawns": _hash(json.dumps(spawns, sort_keys=True)) if spawns else "",
             "sets": _hash(json.dumps(sets, sort_keys=True)) if sets else "",
             "wiki": _hash(json.dumps(wiki, sort_keys=True)) if wiki else "",
             "extra": _hash(json.dumps(extra, sort_keys=True)), "importer": importer.VERSION}
    old = st.get("stand") or {}
    if (db.has_data() and not force and sha and stand["csv"] == old.get("csv") and stand["extra"] == old.get("extra")
            and stand["importer"] == old.get("importer") and (not stand["showdown"] or stand["showdown"] == old.get("showdown"))
            and (not stand["pkhex"] or stand["pkhex"] == old.get("pkhex"))
            and (not stand["spawns"] or stand["spawns"] == old.get("spawns"))
            and (not stand["sets"] or stand["sets"] == old.get("sets"))
            and (not stand["wiki"] or stand["wiki"] == old.get("wiki"))):
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
        stats = importer.build(tmp, csvs, sd_texts, extra, pkhex=pkhex, spawns=spawns, sets=sets, wiki=wiki)
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
    st["stand"], st["stats"], st["built"] = stand, stats, _iso(now())
    log(f"Datenbank neu: {stats['species']} Arten, {stats['forms']} Formen, {stats['moves']} Attacken, {stats['games']} Spiele, "
        f"{stats['tables']} Tabellen" + (f"; Showdown {stats['sd_pokemon']} Pokémon, {stats['sd_moves']} Attacken, "
                                         f"{stats['diff']} Abweichungen zu prüfen" if sd_texts else "; ohne Showdown-Abgleich")
        + (f"; {stats['fundorte']} Fundorte aus PKHeX" if pkhex else "; ohne Fundorte aus PKHeX")
        + (f"; {stats['spawns']} Spawn-Einträge mit Tageszeit und Wetter" if spawns else "")
        + (f"; {stats['sets']} bewährte Sets" if sets else "")
        + (f"; PokéWiki: {stats['wiki_attacken']} Attackenwerte, {stats['wiki_items']} getragene Items" if wiki else ""))
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
    """Begegnungsdateien aus PKHeX (Spieldaten, GPL-3.0): {Spielkennung: {"begegnungen": Bytes, "orte": Text}}."""
    if _resting(st, "pkhex", at):
        log(f"PKHeX ruht bis {st['rest']['pkhex'][:16].replace('T', ' ')} UTC")
        return {}
    src = _Source("pkhex", log)
    out = {}
    for spiel, (enc, names, fixed) in PKHEX_GAMES.items():
        STATE["step"] = f"PKHeX: {spiel}"
        b = src.get(PKHEX_RAW + enc, raw=True)
        t = src.get(PKHEX_RAW + names) if b else None
        if b and t:
            out[spiel] = {"begegnungen": b, "orte": t, "fest": src.get(PKHEX_SRC + fixed) or ""}
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
    st["sources"]["pokewiki"] = src.result(seiten=sum(len(v) for k in out.values() for v in k.values()))
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
PKHEX_GAMES = {"legends-arceus": ("legality/wild/Gen8/encounter_la.pkl", "text/locations/gen8a/text_la_00000_de.txt",
                                   "Gen8/Encounters8a.cs")}


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
            proben[name] = r["text"][:PROBE_MAX]
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
    probe("PKHeX, Begegnungen Karmesin/Purpur", PKHEX_RAW + "legality/wild/Gen9/encounter_wild_paldea.pkl", pkl, raw=True)
    probe("PKHeX, Orte Karmesin/Purpur deutsch", PKHEX_RAW + "text/locations/gen9/text_sv_00000_de.txt", names)
    probe("PKHeX, Begegnungen Legenden: Z-A", PKHEX_RAW + "legality/wild/Gen9/encounter_za.pkl", pkl, raw=True)
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
    page_info = lambda t: f"Titel „{(t.split('<title>')[1].split('</title>')[0].strip() if '<title>' in t else '?')[:80]}“"
    probe("Serebii, Legenden: Arceus Bidiza", "https://www.serebii.net/pokedex-swsh/bidoof/", page_info, keep=True, headers=html)
    probe("Serebii, Legenden: Arceus Übersicht", "https://www.serebii.net/legendsarceus/", page_info, keep=True, headers=html)
    probe("Pokémon Database, Legenden: Arceus", "https://pokemondb.net/pokedex/game/legends-arceus", page_info, keep=True, headers=html)
    probe("Map Genie, Karte Legenden: Arceus", "https://mapgenie.io/pokemon-legends-arceus/maps/hisui", page_info, headers=html)

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
