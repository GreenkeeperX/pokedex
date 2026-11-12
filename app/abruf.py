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
import base64
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

from . import altissimo, bisafans, companion, db, dittobase, ign, importer, ironmon, mapgenie, pkcompletion, pokearth, pokewiki, raidnester, rankedboost, serebii, shiny, smogon, sources, store

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
         "mapgenie": "Map Genie (Karten)", "pkcompletion": "pokemoncompletion (Karten älterer Spiele)", "ign": "IGN (Karten)", "dittobase": "DittoBase (Karten aus den Spieldaten)", "rankedboost": "RankedBoost (Karten Let's Go, Feuerrot/Blattgrün)", "ironmon": "HGSS IronMON Map (Karte HeartGold/SoulSilver)", "raidnester": "PKHeX Raid Plugin (Raid-Nester Schwert/Schild)", "pokearth": "Serebii PokéEarth (Regionskarten der übrigen Spiele)", "serebii": "Serebii (Abklingzeiten Z-A, Pokopia)", "bisafans": "BisaFans (Aufträge in Legenden: Arceus und Z-A)", "trainer": "PokéWiki (Trainerteams)", "smogon": "Smogon (Nutzungsstatistik)", "bulbapedia": "Bulbapedia (Shiny-Sperren)", "itemhq": "Große Item-Bilder"}
MG_PAUSE = 3.0              # Sekunden zwischen zwei Seiten bei Map Genie
MG_TILE_PAUSE = 0.3         # zwischen zwei Kacheln, die die Oberfläche anfordert
MG_STOCK_PAUSE = 0.6        # zwischen zwei Kacheln, die der Vorrat im Hintergrund holt
MISS_FILE = "mapgenie/kacheln/fehlt.json"     # Kacheln, die es nicht gibt (Rand, Meer), mit Datum: nicht wieder fragen
VORRAT_FILE = "mapgenie/kacheln/vorrat.json"  # Stand des Kachelvorrats, übersteht den Neustart
MISS_DAYS = 30
MG_403_MAX = 8              # so viele 403 nacheinander, dann ruht Map Genie (einzelne 403: Kachel gibt es nicht)
WIKI_PAUSE = 2.0            # Sekunden zwischen zwei Anfragen an das PokéWiki (je Anfrage bis zu 50 Seiten)
WIKI_GAMES = ("legends-arceus",)    # Spiele, deren Attacken und Pokémon im PokéWiki gelesen werden
WIKI_TEXT_TAGE = 30         # deutsche Texte aus dem PokéWiki höchstens so oft neu holen (neue Namen sofort)
WIKI_TEXT_BATCH = 20        # ganze Seiten je Anfrage (Attacken tragen lange Lernlisten)

sleep = time.sleep          # Tests setzen hier eine Attrappe ein
# Pausen je Server gelten für alle Quellen zusammen: laufen Quellen parallel (ab 0.20.0), wartet jeder Abruf an einem
# Server, bis der vorige dort fertig ist und die Pause um ist. Verschiedene Server laufen gleichzeitig.
_HOST_LAST = {}
_HOST_LOCKS = {}
_HOST_GUARD = threading.Lock()


def _host_lock(host):
    with _HOST_GUARD:
        return _HOST_LOCKS.setdefault(host, threading.Lock())


def _parallel(jobs):
    """Aufgaben ohne gegenseitige Abhängigkeit gleichzeitig: {Name: Funktion} → {Name: Ergebnis}. Ein Fehler in einer
    Aufgabe kommt als Ausnahme zurück, die anderen laufen zu Ende."""
    out, threads = {}, []

    def one(k, fn):
        try:
            out[k] = fn()
        except Exception as e:          # noqa: BLE001 – der Aufrufer protokolliert
            out[k] = e
    for k, fn in jobs.items():
        t = threading.Thread(target=one, args=(k, fn), name=f"abgleich-{k}", daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    return out
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

    def get(self, url, raw=False, absent=(), data=None):
        """Text (mit raw Bytes) oder None bei Fehler; "" für Statuscodes aus absent („gibt es nicht“).
        data: als JSON per POST (GraphQL-Abfrage, die nur liest)."""
        if self.stopped:
            return None
        host = urllib.parse.urlsplit(url).hostname or ""
        with _host_lock(host):
            return self._get(url, host, raw, absent, data)

    def _get(self, url, host, raw, absent, data=None):
        wait = _HOST_LAST.get(host, 0) + self.pause - time.monotonic()
        if wait > 0:
            sleep(wait)
        self.n += 1
        for attempt in (1, 2):
            try:
                try:
                    body = (sources.fetch(url, timeout=90, raw=raw) if data is None
                            else sources.fetch(url, timeout=90, raw=raw, data=data))
                finally:
                    _HOST_LAST[host] = time.monotonic()
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
_disk = {"at": 0.0, "data": None}


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


def disk_usage(force=False):
    """Speicherplatz des Datenordners: {gesamt, frei, teile: [{name, titel, bytes, dateien, teile?}]}, groß zuerst;
    Karten aufgeschlüsselt nach Quelle der Kacheln und je Karte. Gezählt höchstens alle DISK_CACHE_S Sekunden."""
    if not force and _disk["data"] and time.monotonic() - _disk["at"] < DISK_CACHE_S:
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
    _disk.update(at=time.monotonic(), data=data)
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
        STATE["step"] = "Bilder, Karten und Map Genie (parallel)"
        res = _parallel({"bilder": lambda: _media(st, log, settings, at), "karten": lambda: _media_tiles(st, log, settings, at),
                         "mapgenie": lambda: _media_mg(st, log, at), "itemhq": lambda: _media_itemhq(st, log, settings, at),
                         "smogon": lambda: _smogon(st, log, at)})
        for k, v in res.items():
            if isinstance(v, Exception):
                log(f"{k}: abgebrochen: {type(v).__name__}: {v}")
        st["ok"] = ok
    except Exception as e:          # ein Fehler im Code soll den Dienst nicht beenden
        log(f"Abgebrochen: {type(e).__name__}: {e}")
        st["ok"] = False
    s = int(time.monotonic() - begun)
    st["finished"] = _iso(now())
    log(f"fertig nach {s // 60}:{s % 60:02d} min" + ("" if st["ok"] else ", mit Fehlern"))
    save()
    start_stock()
    return True


def _media(st, log, settings, at):
    """Sprites, Artworks und Extras (ohne große Item-Bilder): alles bei GitHub, nacheinander."""
    if True:
        if db.has_data() and settings["sprites"] and not _resting(st, "sprites", at):
            res = _sprites(log)
            if not res["blocked"]:
                art = _images("artwork", log)
                res = dict(art, requests=res["requests"] + art["requests"], errors=res["errors"] + art["errors"],
                           neu=res["neu"] + art["neu"], fehlen=res["fehlen"] + art["fehlen"], offen=res["offen"] + art["offen"])
            st["sources"]["sprites"] = res
            if res["blocked"]:
                st["rest"]["sprites"] = _iso(now() + timedelta(hours=REST_H))
        if db.has_data() and settings["sprites"] and not _resting(st, "extras", at):
            total = None
            for kind in EXTRAS:
                if kind == "itemhq":
                    continue                # eigener Faden (Serebii)
                res = _images(kind, log)
                total = res if total is None else dict(res, **{k: total[k] + res[k] for k in ("requests", "errors", "neu", "fehlen", "offen")})
                if res["blocked"]:
                    break
            st["sources"]["extras"] = total
            if total["blocked"]:
                st["rest"]["extras"] = _iso(now() + timedelta(hours=REST_H))


def _smogon(st, log, at):
    """Nutzungsstatistik für die Kampfansicht (Champions): neuester Monat, passendes Doppel-Format, gekürzt in
    smogon.json. Ohne Änderung am Stand nur zwei kleine Abrufe (Übersicht und Ordner)."""
    if _resting(st, "smogon", at):
        return
    src = _Source("smogon", log, pause=2.0)
    old = store.load_json("smogon.json", {})
    try:
        ms = smogon.months(src.get(smogon.INDEX))
        got = None
        for month in ms[:2]:            # ein neuer Monat ist manchmal noch leer
            files = smogon.chaos_files(src.get(f"{smogon.INDEX}{month}/chaos/"))
            got = smogon.pick(files)
            if got:
                break
        if not got:
            log("Smogon: kein passendes Format gefunden")
        elif old.get("monat") == month and old.get("format") == got[0] and old.get("grenze") == got[1]:
            log(f"Smogon: {got[0]} ({month}) unverändert")
        else:
            body = src.get(f"{smogon.INDEX}{month}/chaos/{got[0]}-{got[1]}.json")
            if body:
                d = smogon.digest(json.loads(body), got[0], got[1], month)
                store.save_json("smogon.json", d)
                log(f"Smogon: {got[0]} ({month}, ab {got[1]}): {len(d['pokemon'])} Pokémon aus {d['kaempfe']} Kämpfen")
    except ValueError as e:
        log(f"Smogon: Datei nicht lesbar ({e})")
    st["sources"]["smogon"] = src.result()
    if src.blocked:
        st["rest"]["smogon"] = _iso(now() + timedelta(hours=REST_H))


def _media_tiles(st, log, settings, at):
    if db.has_data() and settings["sprites"] and not _resting(st, "karten", at):
        res = _tiles(log)
        st["sources"]["karten"] = res
        if res["blocked"]:
            st["rest"]["karten"] = _iso(now() + timedelta(hours=REST_H))


def _media_mg(st, log, at):
    for key, run in (("mapgenie", _mapgenie), ("pkcompletion", _pkcompletion), ("ign", _ign), ("dittobase", _dittobase), ("rankedboost", _rankedboost), ("ironmon", _ironmon), ("raidnester", _raidnester), ("pokearth", _pokearth)):
        if db.has_data() and not _resting(st, key, at):
            res = run(log)
            st["sources"][key] = res
            if res["blocked"]:
                st["rest"][key] = _iso(now() + timedelta(hours=REST_H))


def _media_itemhq(st, log, settings, at):
    """Große Item-Bilder von Serebii: eine Sekunde Pause je Abruf, deshalb neben den anderen Bildern."""
    if db.has_data() and settings["sprites"] and not _resting(st, "itemhq", at) and not _resting(st, "extras", at):
        res = _images("itemhq", log)
        st["sources"]["itemhq"] = res
        if res["blocked"]:
            st["rest"]["itemhq"] = _iso(now() + timedelta(hours=REST_H))


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

    def showdown_all():
        nonlocal sets
        if _resting(st, "showdown", at):
            return
        for k in ("pokedex", "moves"):
            t = sd.get(f"{SD_RAW}{k}.ts")
            if t:
                sd_texts[k] = t
        # Basiswerte früherer Generationen (Spezial in Gen. 1, spätere Änderungen) aus den Generations-Mods
        from . import showdown as _sd
        for n in _sd.MOD_GENS:
            t = sd.get(f"{SD_RAW}mods/gen{n}/pokedex.ts", absent=(404,))
            if t:
                sd_texts[f"gen{n}"] = t
        sets = _sets(sd)
        st["sources"]["showdown"] = sd.result(dateien=len(sd_texts) + len(sets))
        if sd.blocked:
            st["rest"]["showdown"] = _iso(now() + timedelta(hours=REST_H))
    # Quellen ohne gegenseitige Abhängigkeit gleichzeitig; die Pause je Server gilt weiter für alle zusammen
    STATE["step"] = "Showdown, PKHeX, Spawnpunkte, PokéWiki, Serebii, Altissimo, PLA Companion (parallel)"
    got = _parallel({"showdown": showdown_all, "pkhex": lambda: _pkhex(st, log, at), "spawns": lambda: _spawns(st, log, at),
                     "pokewiki": lambda: _pokewiki(st, log, at), "serebii": lambda: _serebii(st, log, at),
                     "bisafans": lambda: _bisafans(st, log, at), "trainer": lambda: _trainer(st, log, at),
                     "altissimo": lambda: _altissimo(st, log, at), "companion": lambda: _companion(st, log, at),
                     "shiny": lambda: _shiny(st, log, at)})
    for k, v in got.items():
        if isinstance(v, Exception):
            log(f"{NAMES.get(k, k)}: abgebrochen: {type(v).__name__}: {v}")
            got[k] = None
    pkhex, spawns, wiki = got["pkhex"] or {}, got["spawns"] or {}, got["pokewiki"] or {}
    if got["serebii"]:
        wiki = dict(wiki, serebii=got["serebii"])           # Serebii läuft beim Bauen mit dem PokéWiki zusammen
    if got.get("bisafans"):
        wiki = dict(wiki, bisafans=got["bisafans"])         # ebenso BisaFans
    if got.get("trainer"):
        wiki = dict(wiki, trainer=(got["trainer"] or {}).get("teams") or [])
    if (got.get("shiny") or {}).get("text"):
        wiki = dict(wiki, shiny=got["shiny"]["text"])         # 0.51: Shiny-Sperren (importer._derive_shiny)
    alt, comp = got["altissimo"] or {}, got["companion"]
    if comp:
        alt.setdefault("legends-arceus", {})["companion"] = comp
    extra = importer.load_extra(EXTRA_DIR)
    stand = {"csv": sha, "showdown": _hash(*(sd_texts.get(k, "") for k in sorted(sd_texts))) if "pokedex" in sd_texts and "moves" in sd_texts else "",
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
        + (f"; {stats['werte_alt']} frühere Basiswerte (Showdown-Mods)" if stats.get('werte_alt') else "")
        + (f"; PokéWiki: {stats['wiki_attacken']} Attackenwerte, {stats['wiki_items']} getragene Items, "
           f"{stats.get('wiki_karte', 0)} Stellen auf der Karte" if wiki else "")
        + (f"; Serebii: {stats.get('abklingzeiten', 0)} Abklingzeiten (Z-A), {stats.get('pokopia', 0)} Pokémon in Pokopia"
           if (wiki or {}).get("serebii") else "")
        + (f"; Altissimo: {stats['kartenobjekte']} Kartensymbole, {stats['rezepte']} Rezepte" if alt else "")
        + (f"; PLA Companion: {stats.get('orte', 0)} Orte (Schnellreise, Lager)" if comp else "")
        + (f"; {stats['items']} Items" if stats.get("items") else "")
        + ("; deutsche Texte je Spiel: " + ", ".join(f"{n} {TEXT_LABEL.get(k, k)}" for k, n in sorted((stats.get("texte") or {}).items()))
           if stats.get("texte") else "")
        + (f", {stats['forschung']} Forschungsaufgaben (Legenden: Arceus)" if stats.get("forschung") else "")
        + (f"; BisaFans: {stats['auftraege']} Aufträge (Legenden: Arceus)" if stats.get("auftraege") else ""))
    for k, keys in (stats.get("kuerzel_unbekannt") or {}).items():
        log(f"PokéWiki: unbekannte Spielkürzel bei {TEXT_LABEL.get(k, k)}: {', '.join(keys[:20])}")
    return not papi.stopped and not sd.stopped


TEXT_LABEL = {"pokemon": "Pokémon", "attacken": "Attacken", "faehigkeiten": "Fähigkeiten"}
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
    # Tera-Raids in Karmesin/Purpur (importer.PKHEX_RAIDS)
    STATE["step"] = "PKHeX: Tera-Raids"
    raids = {k: src.get(PKHEX_RAW + f"legality/wild/Gen9/encounter_{k}.pkl", raw=True) for k in importer.PKHEX_RAIDS}
    if any(raids.values()):
        out["_raids"] = {k: v for k, v in raids.items() if v}
    # Crypto-Pokémon in Colosseum und XD (importer.PKHEX_SHADOW)
    STATE["step"] = "PKHeX: Crypto-Pokémon"
    shadow = {k: src.get(PKHEX_SRC + f) for k, f in importer.PKHEX_SHADOW.items()}
    if any(shadow.values()):
        out["_crypto"] = {k: v for k, v in shadow.items() if v}
    # Lernlisten für Spiele ohne Lernliste in der PokéAPI (importer.PKHEX_LEARN)
    for key in importer.PKHEX_LEARN:
        STATE["step"] = f"PKHeX: Lernlisten {key}"
        lvl = src.get(PKHEX_RAW + f"byte/levelup/lvlmove_{key}.pkl", raw=True)
        per = src.get(PKHEX_RAW + f"byte/personal/personal_{key}", raw=True) if lvl else None
        if lvl and per:
            out[f"_lernen_{key}"] = {"lvl": lvl, "personal": per}
    # 0.50: Werte je Form in Legenden: Arceus, für die eigenen Fangraten des Spiels (importer._derive_fangrate)
    STATE["step"] = "PKHeX: Fangraten Legenden: Arceus"
    per = src.get(PKHEX_RAW + "byte/personal/personal_la", raw=True)
    if per:
        out["_fang_la"] = {"personal": per}
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
    for spiel in mapgenie.GAMES:
        page = slug = None
        for slug in mapgenie.slugs(spiel):           # Schreibweise unsicher: die erste, die antwortet
            STATE["step"] = f"Map Genie: {slug}"
            page = src.get(mapgenie.game_url(slug), absent=(404,))
            if page or src.stopped:
                break
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


def _pkcompletion(log):
    """Karten von pokemoncompletion für die Spiele in pkcompletion.GAMES: Punkte aus den Spieldaten im Repository, in
    derselben Form wie Map Genie nach data/mapgenie/<Spiel>.json. Kacheln holt der Vorrat (mg_stock) vom CDN."""
    src = _Source("pkcompletion", log)
    found = 0
    for spiel, name in pkcompletion.GAMES.items():
        STATE["step"] = f"pokemoncompletion: {name}"
        text = src.get(pkcompletion.DATA.format(name), absent=(404,))
        if src.stopped:
            break
        m = pkcompletion.parse(text, spiel) if text else None
        if m:
            _save_maps(spiel, "pc", [m])
            log(f"pokemoncompletion: {name} mit {len(m['orte'])} Punkten")
            found += 1
    return src.result(dateien=found)


def _save_maps(spiel, quelle, karten):
    """Karten einer Quelle nach data/mapgenie/<Spiel>.<Quelle>.json (Map Genie selbst: <Spiel>.json)."""
    os.makedirs(mg_dir(), exist_ok=True)
    store.save_json(os.path.join("mapgenie", f"{spiel}.{quelle}.json"), {"spiel": spiel, "am": _iso(now()), "karten": karten})
    old = mg_dir(spiel + ".json")          # bis 0.28.3 lag pokemoncompletion unter <Spiel>.json
    if quelle == "pc" and (store.load_json(os.path.join("mapgenie", spiel + ".json"), {}) or {}).get("quelle") == "pokemoncompletion":
        os.remove(old)


def _ign(log):
    """Karten von IGN für die Spiele in ign.GAMES: Kartenseite, daraus Kachelmuster und die mitgelieferten Punkte; alle
    Punkte über die GraphQL-Abfrage, die auch die Seite stellt (ohne Antwort bleibt es bei denen der Seite)."""
    src = _Source("ign", log, pause=MG_PAUSE)
    found = 0
    for spiel, (slug, karten) in ign.GAMES.items():
        maps = []
        for k in karten:
            STATE["step"] = f"IGN: {slug}/{k}"
            page = src.get(ign.page_url(slug, k), absent=(404,))
            if src.stopped:
                break
            m = ign.parse(page, k) if page else None
            q = ign.query(m)
            if q:
                STATE["step"] = f"IGN: Punkte {slug}/{k}"
                more = ign.markers(src.get(ign.GRAPH, data=q) or "")
                if more:
                    m = ign.parse(page, k, more)
                else:
                    log(f"IGN: Abfrage der Punkte für {slug}/{k} ohne Antwort, nur die Punkte der Seite")
            if m:
                maps.append(m)
        if maps:
            _save_maps(spiel, "ign", maps)
            log(f"IGN: {slug} mit {len(maps)} Karten, {sum(len(m['orte']) for m in maps)} Punkten")
            found += 1
        if src.stopped:
            break
    return src.result(dateien=found)


def _dittobase(log):
    """Karten von DittoBase für die Spiele in dittobase.GAMES: Kartenseite (Spieldaten und Punkte), die Kachelsätze als
    Bilder, daraus zeichnet der Abgleich alle Kacheln selbst (kacheln/db/<Spiel>/). Gezeichnet wird nur, was fehlt oder
    sich geändert hat."""
    from . import png
    src = _Source("dittobase", log, pause=MG_PAUSE)
    found = 0
    for spiel, slug in dittobase.GAMES.items():
        STATE["step"] = f"DittoBase: {slug}"
        page = src.get(dittobase.page_url(slug), absent=(404,))
        if src.stopped:
            break
        m, draw = dittobase.parse(dittobase.extract(page), spiel) if page else (None, None)
        if not m:
            if page:
                log(f"DittoBase: {slug} ohne Kartendaten (Seite geändert?)")
            continue
        sets, sdir = {}, mg_dir("kacheln", "db", "_saetze")
        os.makedirs(sdir, exist_ok=True)
        for n, (name, v) in enumerate(sorted(draw["saetze"].items())):
            f = os.path.join(sdir, name + ".png")
            if not os.path.isfile(f) and dittobase.tileset_ok(v["bild"]):
                STATE.update(step=f"DittoBase: Kachelsätze {slug}", done=n, total=len(draw["saetze"]))
                body = src.get(v["bild"], raw=True, absent=(404,))
                if body and body[:8] == png.SIG:
                    with open(f + ".neu", "wb") as fh:
                        fh.write(body)
                    os.replace(f + ".neu", f)
                elif src.stopped:
                    break
            if os.path.isfile(f):
                try:
                    with open(f, "rb") as fh:
                        sets[name] = png.decode(fh.read())
                except (OSError, ValueError, png.zlib.error) as e:
                    log(f"DittoBase: Kachelsatz {name} nicht lesbar ({e})")
        if src.stopped:
            break
        tdir = mg_dir("kacheln", "db", slug)
        stamp = _hash(json.dumps(draw, sort_keys=True), *sorted(sets))
        old = store.load_json(os.path.join("mapgenie", "kacheln", "db", slug, "stand.json"), {}) or {}
        same = old.get("stand") == stamp

        def have(z, x, y):
            return same and os.path.isfile(os.path.join(tdir, str(z), f"{x}-{y}.png"))

        def save(z, x, y, rgba):
            d = os.path.join(tdir, str(z))
            os.makedirs(d, exist_ok=True)
            f = os.path.join(d, f"{x}-{y}.png")
            with open(f + ".neu", "wb") as fh:
                fh.write(png.encode(dittobase.TILE, dittobase.TILE, rgba))
            os.replace(f + ".neu", f)

        def step(z, done, alle):
            STATE.update(step=f"DittoBase: Kacheln {slug} Stufe {z}", done=done, total=alle)
        n = dittobase.render_tiles(draw, sets, save, have, step)
        os.makedirs(tdir, exist_ok=True)
        store.save_json(os.path.join("mapgenie", "kacheln", "db", slug, "stand.json"), {"stand": stamp, "am": _iso(now())})
        _save_maps(spiel, "db", [m])
        log(f"DittoBase: {slug} mit {len(m['orte'])} Punkten, {len(sets)} von {len(draw['saetze'])} Kachelsätzen"
            + (f", {n} Kacheln gezeichnet" if n else ""))
        found += 1
    return src.result(dateien=found)


def _rankedboost(log):
    """Megakarten von RankedBoost für die Spiele in rankedboost.GAMES: Spielseite → Adresse der JSON-Datei → Orte mit
    Pokémon und die Ortsbilder (webp), die als Bildebene statt Kacheln auf der Karte liegen (kacheln/rb/<Karte>/<Nr>.webp).
    Was schon da ist, wird nicht wieder geholt."""
    src = _Source("rankedboost", log, pause=MG_PAUSE)
    found = 0
    for spiel, slug in rankedboost.GAMES.items():
        STATE["step"] = f"RankedBoost: {slug}"
        url = None
        for p in rankedboost.page_urls(spiel):
            url = rankedboost.json_url(src.get(p, absent=(404,)))
            if url or src.stopped:
                break
        if src.stopped:
            break
        if not url:
            log(f"RankedBoost: {slug} ohne Adresse der Kartendaten auf der Seite, es gilt die zuletzt bekannte")
            url = rankedboost.KNOWN.get(spiel)
        m, bilder = rankedboost.parse(rankedboost.extract(src.get(url, absent=(404,)) or "" if url else ""), spiel)
        if not m:
            if not src.stopped:
                log(f"RankedBoost: {slug} ohne lesbare Kartendaten")
            continue
        d = mg_dir("kacheln", "rb", m["slug"])
        os.makedirs(d, exist_ok=True)
        stand = store.load_json(os.path.join("mapgenie", "kacheln", "rb", m["slug"], "stand.json"), {}) or {}
        neu, have = 0, []
        for n, (nr, u, x, y, w, h) in enumerate(bilder):
            f = os.path.join(d, f"{nr}.webp")
            if not (os.path.isfile(f) and stand.get(str(nr)) == u) and not src.stopped:
                STATE.update(step=f"RankedBoost: Ortsbilder {slug}", done=n, total=len(bilder))
                body = src.get(u, raw=True, absent=(404,))
                if body and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
                    with open(f + ".neu", "wb") as fh:
                        fh.write(body)
                    os.replace(f + ".neu", f)
                    stand[str(nr)] = u
                    neu += 1
            if os.path.isfile(f):
                have.append([nr, x, y, w, h])
        store.save_json(os.path.join("mapgenie", "kacheln", "rb", m["slug"], "stand.json"), stand)
        m["bilder"] = have
        _save_maps(spiel, "rb", [m])
        log(f"RankedBoost: {slug} mit {len(m['orte'])} Orten, {len(have)} von {len(bilder)} Ortsbildern" + (f" ({neu} neu)" if neu else ""))
        found += 1
        if src.stopped:
            break
    return src.result(dateien=found)


def _ironmon(log):
    """HeartGold/SoulSilver aus der HGSS IronMON Map (GitHub): je Region Trainer und Items (TypeScript) und einmal das
    große Bild (kacheln/im/<Region>.webp, Kacheln daraus macht der Browser, tile_upload); mapgenie/<Spiel>.im.json."""
    src = _Source("ironmon", log, pause=PAUSE)
    found = 0
    for spiel, regs in ironmon.GAMES.items():
        maps = []
        for reg in regs:
            STATE["step"] = f"HGSS IronMON Map: {ironmon.REGION.get(reg, reg)}"
            bild, tr, it = ironmon.urls(reg)
            f = mg_dir("kacheln", "im", reg + ".webp")
            if not os.path.isfile(f):
                body = src.get(bild, raw=True, absent=(404,))
                if body and ironmon.webp_size(body[:64]):
                    os.makedirs(os.path.dirname(f), exist_ok=True)
                    with open(f + ".neu", "wb") as fh:
                        fh.write(body)
                    os.replace(f + ".neu", f)
            ts = [src.get(u, absent=(404,)) or "" for u in (tr, it)]
            if src.stopped:
                break
            if not os.path.isfile(f):
                log(f"HGSS IronMON Map: {reg} ohne Kartenbild")
                continue
            with open(f, "rb") as fh:
                size = ironmon.webp_size(fh.read(64))
            m = ironmon.parse(reg, *(size or (0, 0)), ironmon.objects(ts[0]), ironmon.objects(ts[1]))
            if m:
                maps.append(m)
        if maps:
            _save_maps(spiel, "im", maps)
            found += 1
            log("HGSS IronMON Map: " + ", ".join(f"{m['titel']} mit {len(m['orte'])} Punkten" for m in maps))
        if src.stopped:
            break
    return src.result(dateien=found)


def _raidnester(log):
    """Raid-Nester in Schwert/Schild aus dem PKHeX Raid Plugin (GitHub): Lage je Nest, Gebietsnamen und einmal die
    Bilder der drei Teile (kacheln/rn/<Teil>.png); je Spiel mapgenie/<Spiel>.rn.json."""
    src = _Source("raidnester", log, pause=PAUSE)
    ns = raidnester.nests(src.get(raidnester.NESTS, absent=(404,)) or "",
                          raidnester.location_names(src.get(raidnester.NAMES, absent=(404,)) or ""))
    if not ns:
        if not src.stopped:
            log("PKHeX Raid Plugin: keine Raid-Nester gelesen")
        return src.result(dateien=0)
    tabs = raidnester.tables(src.get(raidnester.TABLES, absent=(404,)) or "") if not src.stopped else {}
    names = {}
    try:
        con = db.game()
        try:
            names = {i: n for i, n in con.execute("SELECT pokemon_species_id, name FROM pokemon_species_names WHERE local_language_id = 6") if n}
        finally:
            con.close()
    except Exception:
        pass
    found = 0
    for area, (spiel, bild, _, _) in raidnester.AREAS.items():
        STATE["step"] = f"PKHeX Raid Plugin: {area}"
        f = mg_dir("kacheln", "rn", area + ".png")
        if not os.path.isfile(f) and not src.stopped:
            body = src.get(raidnester.BASE + bild, raw=True, absent=(404,))
            if body and raidnester.png_size(body):
                os.makedirs(os.path.dirname(f), exist_ok=True)
                with open(f + ".neu", "wb") as fh:
                    fh.write(body)
                os.replace(f + ".neu", f)
        if not os.path.isfile(f):
            continue
        with open(f, "rb") as fh:
            m = raidnester.parse(ns, area, *(raidnester.png_size(fh.read(32)) or (0, 0)), tabs=tabs, names=names)
        if m:
            _save_maps(spiel, "rn", [m])
            found += 1
    n_tab = sum(len(v) for v in tabs.values())
    log(f"PKHeX Raid Plugin: {len(ns)} Raid-Nester auf {found} Karten" + (f", Inhalt aus {n_tab} Tabellen" if n_tab else ", ohne Inhalt der Nester"))
    return src.result(dateien=found)


def tile_convert_state(spiel, karte):
    """Umwandlung einer Bildkarte in Kacheln (HGSS IronMON Map): {fertig, bild, w, h, z, min, kachel, fehlen} oder None."""
    m = _mg_map(spiel, karte)
    if not m or m.get("quelle") != "ironmon":
        return None
    d = mg_dir("kacheln", "im", m["region"])
    fehlen = 0
    for z in range(m["min_zoom"], m["max_zoom"] + 1):
        nx, ny = ironmon.tile_range(m, z)
        fehlen += sum(1 for x in range(nx) for y in range(ny) if not os.path.isfile(os.path.join(d, str(z), f"{x}-{y}.png")))
    return {"fertig": not fehlen, "fehlen": fehlen, "bild": mg_image(spiel, karte, 0) is not None, "w": m["dim"]["w"],
            "h": m["dim"]["h"], "z": m["bild_z"], "min": m["min_zoom"], "kachel": m["kachel"]}


TILE_UPLOAD_MAX = 400_000      # Bytes je Kachel (PNG); eine Kachel der Karte hat meist unter 100 KB


def tile_upload(b):
    """Kacheln, die der Browser aus dem Bild einer Karte geschnitten hat: {spiel, karte, kacheln: [[z, x, y, PNG als
    Base64]]}. Nur Karten, deren Bild der Server selbst geholt hat, nur Kacheln innerhalb der Karte, nur PNG."""
    import base64
    m = _mg_map(str(b.get("spiel") or ""), str(b.get("karte") or ""))
    if not m or m.get("quelle") != "ironmon":
        raise ValueError("keine Karte zum Umwandeln")
    n = 0
    for k in (b.get("kacheln") or [])[:64]:
        if not (isinstance(k, list) and len(k) == 4 and all(isinstance(v, int) for v in k[:3]) and isinstance(k[3], str)):
            raise ValueError("Kachel ungültig")
        rel = ironmon.tile(m, *k[:3])
        body = base64.b64decode(k[3], validate=True) if rel and len(k[3]) < TILE_UPLOAD_MAX * 4 // 3 + 4 else b""
        if not rel or body[:8] != b"\x89PNG\r\n\x1a\n" or len(body) > TILE_UPLOAD_MAX:
            raise ValueError("Kachel ungültig")
        f = mg_dir("kacheln", *rel[0].split("/"))
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f + ".neu", "wb") as fh:
            fh.write(body)
        os.replace(f + ".neu", f)
        n += 1
    return {"gespeichert": n}


def _pokearth(log):
    """Regionskarten von Serebii (PokéEarth) für die Spiele in pokearth.GAMES: je Region die Seite und einmal das Bild
    (kacheln/se/<Region>.<Endung>), dann je Spiel die Karten seiner Regionen (mapgenie/<Spiel>.se.json)."""
    src = _Source("pokearth", log, pause=SEREBII_PAUSE)
    have = {}
    for i, reg in enumerate(pokearth.regions()):
        STATE.update(step=f"Serebii PokéEarth: {pokearth.REGION.get(reg, reg)}", done=i, total=len(pokearth.regions()))
        d = pokearth.extract(src.get(pokearth.page_url(reg), absent=(404,)) or "")
        if src.stopped:
            break
        if not d and pokearth.PW_MAPS.get(reg, {}).get("inseln"):     # 0.56: Alola, eine Karte je Insel
            ms = [m for m in (_pw_island(src, reg, t) for t in _pw_islands(src, reg)) if m]
            if ms:
                have[reg] = ms
            else:
                log(f"Serebii PokéEarth: {reg} ohne Bildkarte")
            continue
        if not d and reg in pokearth.PW_MAPS:      # 0.48: Bildkarte aus dem PokéWiki, großes Bild von Bulbapedia
            d = _pw_region(src, reg)
        m = pokearth.parse(d, reg)
        if not m:
            log(f"Serebii PokéEarth: {reg} ohne Bildkarte")
            continue
        _region_image(src, m, d)
        have[reg] = [m]
    found = 0
    for spiel, regs in pokearth.GAMES.items():
        ks = [m for r in regs if r in have for m in have[r]]
        if ks:
            _save_maps(spiel, "se", ks)
            found += 1
    if have:
        log(f"Serebii PokéEarth: {len(have)} Regionen mit {sum(len(m['orte']) for ms in have.values() for m in ms)} Orten für {found} Spiele")
    return src.result(dateien=found)


def _region_image(src, m, d):
    """Bild einer Regions- oder Inselkarte einmal holen (kacheln/se/…); ohne Bild bleibt die Karte ohne Bildebene."""
    rel = m["bilder"][0][5]
    f = mg_dir("kacheln", *rel.split("/"))
    if not os.path.isfile(f):
        body = src.get(d["bild"], raw=True, absent=(404,))
        if body and (body[:8] == b"\x89PNG\r\n\x1a\n" or body[:3] == b"\xff\xd8\xff" or body[:4] == b"GIF8"):
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f + ".neu", "wb") as fh:
                fh.write(body)
            os.replace(f + ".neu", f)
    if not os.path.isfile(f):
        m["bilder"] = []


def _pw_islands(src, reg):
    """0.56: Orte je Insel aus der PokéWiki-Vorlage (pokearth.pw_islands)."""
    try:
        wt = next(iter(pokewiki.pages(src.get(pokearth.pw_template_url(reg)) or "{}").values()), "")
    except ValueError:
        wt = ""
    return pokearth.pw_islands(wt, reg)


def _pw_island(src, reg, t):
    """Karte einer Insel: Orte aus der Bildkarte, Bild in Originalgröße aus dem PokéWiki."""
    key, title, f, orte = t
    small = pokearth.imageinfo(src.get(pokearth.imageinfo_url(pokearth.PW_API, f)))
    m = pokearth.parse(pokearth.pw_map(orte, small), reg, (key, title))
    if m:
        _region_image(src, m, {"bild": small[0]})
    src.log(f"PokéWiki-Bildkarte {pokearth.REGION.get(reg, reg)}, {title}: {len(orte)} Orte, Bild "
            + (f"{small[1]}×{small[2]}" if small else "fehlt"))
    return m


def _pw_region(src, reg):
    """Regionskarte aus einer PokéWiki-Vorlage (Orte) mit dem kleinen Bild von dort oder dem großen von Bulbapedia."""
    cfg = pokearth.PW_MAPS[reg]
    try:
        wt = next(iter(pokewiki.pages(src.get(pokearth.pw_template_url(reg)) or "{}").values()), "")
    except ValueError:
        wt = ""
    orte = pokearth.pw_areas(wt)
    small = pokearth.imageinfo(src.get(pokearth.imageinfo_url(pokearth.PW_API, cfg["bild"])))
    big = pokearth.imageinfo(src.get(pokearth.imageinfo_url(pokearth.BULBA_API, cfg["gross"]))) if cfg.get("gross") else None
    d = pokearth.pw_map(orte, small, big)
    src.log(f"PokéWiki-Bildkarte {pokearth.REGION.get(reg, reg)}: {len(orte)} Orte, Bild "
            + (f"{d['w']}×{d['h']} von {'Bulbapedia' if 'bulbagarden' in d['bild'] else 'PokéWiki'}" if d else "fehlt"))
    return d


def mg_image(spiel, karte, nr):
    """Pfad eines Bilds einer Bildkarte (RankedBoost: Ortsbilder, Serebii: Regionsbild) im Datenordner oder None. Ohne
    Netz: die Bilder holt der Abgleich."""
    m = _mg_map(spiel, karte)
    b = next((b for b in ((m or {}).get("bilder") or []) + ([m["quellbild"]] if (m or {}).get("quellbild") else []) if b[0] == nr), None)
    if not b:
        return None
    rel = b[5] if len(b) > 5 and re.fullmatch(r"[a-z]{2}/[\w.-]+", str(b[5])) and ".." not in b[5] else f"rb/{m['slug']}/{nr}.webp"
    f = mg_dir("kacheln", *rel.split("/"))
    return f if os.path.isfile(f) else None


MAP_GAMES = tuple(dict.fromkeys((*mapgenie.GAMES, *pkcompletion.GAMES, *ign.GAMES, *dittobase.GAMES, *rankedboost.GAMES, *ironmon.GAMES, *raidnester.GAMES, *pokearth.GAMES)))   # Spiele mit eigener Karte
MAP_FILES = ("", ".pc", ".ign", ".rn", ".db", ".rb", ".im", ".se")   # je Spiel eine Datei je Quelle; die Karten erscheinen in dieser Reihenfolge


def mg_maps(spiel):
    """Gespeicherte Karten eines Spiels aus allen Quellen (Erweiterungen und Schwester-Editionen: die des Hauptspiels)
    als {spiel, am, karten} oder None. Hat die Schwester-Edition eigene Karten (Gold/Silber bei DittoBase), stehen sie
    vorn; vom Hauptspiel kommen dann nur Karten anderer Quellen dazu."""
    share = mapgenie.SHARE.get(spiel) or pkcompletion.SHARE.get(spiel)
    fs = []
    for g in dict.fromkeys((spiel, share)):
        for suf in MAP_FILES if g in MAP_GAMES else ():
            if suf == ".rb" and g not in rankedboost.GAMES:
                continue                 # frühere Karte einer Quelle, die für dieses Spiel nicht mehr gilt
            try:
                fs.append((g, suf, os.path.getmtime(mg_dir(g + suf + ".json"))))
            except OSError:
                pass
    if not fs:
        return None
    key = spiel if fs[0][0] == spiel else fs[0][0]
    hit = _mg_cache.get(key)
    if not hit or hit[0] != fs:
        out = {"spiel": key, "am": "", "karten": []}
        own = set()
        for g, suf, _ in fs:
            d = store.load_json(os.path.join("mapgenie", g + suf + ".json"), {}) or {}
            ks = d.get("karten") or []
            if g == key:
                own |= {k.get("quelle") or "mapgenie" for k in ks}
            else:
                ks = [k for k in ks if (k.get("quelle") or "mapgenie") not in own]
            out["karten"] += ks
            out["am"] = max(out["am"], str(d.get("am") or ""))
        hit = _mg_cache[key] = (fs, out if out["karten"] else None)
    return hit[1]


_mg_cache = {}


_mg_lock = threading.Lock()
_mg = {"last": 0.0, "rest": "", "miss": set(), "fehler": "", "n403": 0, "vorrat": {}, "laeuft": False, "ok": "", "rest_pokemoncompletion": "", "rest_ign": "", "rest_dittobase": "", "rest_rankedboost": "", "rest_ironmon": "", "rest_raidnester": "", "rest_pokearth": ""}


def _miss_load():
    """Fehlende Kacheln vom letzten Lauf (höchstens MISS_DAYS alt) und den Stand des Vorrats einmal je Start lesen."""
    if _mg.get("miss_da"):
        return
    _mg["miss_da"] = True
    old = _iso(now() - timedelta(days=MISS_DAYS))[:10]
    got = store.load_json(MISS_FILE, {}) or {}
    _mg["miss_am"] = {k: v for k, v in got.items() if isinstance(v, str) and v >= old}
    _mg["miss"] |= set(_mg["miss_am"])
    for k, v in (store.load_json(VORRAT_FILE, {}) or {}).items():
        _mg["vorrat"].setdefault(k, v)


def _miss_add(rel, kept=True):
    _mg["miss"].add(rel)
    if kept:
        _mg.setdefault("miss_am", {})[rel] = _iso(now())[:10]
        if time.monotonic() - _mg.get("miss_t", 0) > 60:
            _miss_save()


def _miss_save():
    _mg["miss_t"] = time.monotonic()
    try:
        store.save_json(MISS_FILE, dict(_mg.get("miss_am") or {}))
        store.save_json(VORRAT_FILE, dict(_mg["vorrat"]))
    except OSError as e:
        print("Kachelvorrat speichern:", e, file=sys.stderr)


def mg_status():
    """Zustand der Kacheln für die Oberfläche: ruht bis (ISO oder leer), letzter Fehler, Vorrat je Karte
    {"<Spiel>/<Karte>": {"da": n, "alle": m, "bis": Zoom}} und ob der Vorrat gerade lädt."""
    _miss_load()
    return {"ruht": _mg["rest"] if _mg["rest"] > _iso(now()) else "", "fehler": _mg["fehler"],
            "vorrat": dict(_mg["vorrat"]), "laedt": _mg["laeuft"]}


def _mg_map(spiel, karte):
    d = mg_maps(spiel)
    return next((m for m in (d or {}).get("karten", []) if m["slug"] == karte), None)


def mg_stock():
    """Kachelvorrat im Hintergrund: holt für jede Karte von Map Genie alle Kacheln aller Zoomstufen, mit Pause; was da
    ist, bleibt. Erst alle Karten bis eine Stufe unter der größten (weite Stufen zuerst), dann die größte Stufe. Danach
    braucht die Karte kein Netz mehr. Ein Lauf zur Zeit."""
    if _mg["laeuft"]:
        return
    _mg["laeuft"] = True
    _miss_load()
    try:
        jobs = [(spiel, m, top) for top in (1, 0) for spiel in MAP_GAMES for m in (mg_maps(spiel) or {}).get("karten", [])]
        for spiel, m, top in jobs:
            q = m.get("quelle")
            ts = TILE_SRC.get(q, mapgenie).tile_list(m, m["max_zoom"] - top)
            key = f"{spiel}/{m['slug']}"
            have = 0
            for i, (z, x, y) in enumerate(ts):
                if _mg["rest_" + q if q in TILE_SRC else "rest"] > _iso(now()):
                    break
                rel = _tile_of(m, z, x, y)[0]
                if not rel or rel in _mg["miss"]:
                    pass
                elif os.path.isfile(mg_dir("kacheln", *rel.split("/"))):
                    have += 1
                else:
                    # die Pause des Vorrats außerhalb der Sperre: Kacheln, die die Karte gerade braucht, warten nicht
                    if m.get("quelle") not in TILE_SRC or _tile_of(m, z, x, y)[1]:
                        sleep(MG_STOCK_PAUSE)
                    if mg_tile(spiel, m["slug"], z, x, y, pause=MG_TILE_PAUSE, stock=True):
                        have += 1
                if i % 50 == 0 or i == len(ts) - 1:
                    _mg["vorrat"][key] = {"da": have, "alle": len(ts), "bis": m["max_zoom"] - top, "fertig": i == len(ts) - 1,
                                          "ganz": not top}
            _miss_save()
    except Exception as e:          # der Vorrat darf den Dienst nicht stören
        print("Kachelvorrat:", e, file=sys.stderr)
    finally:
        _mg["laeuft"] = False


def start_stock():
    if not _mg["laeuft"]:
        threading.Thread(target=mg_stock, daemon=True, name="kachelvorrat").start()


def _mg_probe():
    """Nach vielen 403 nacheinander: kommt eine Kachel, die es sicher gibt, noch? Dann sperrt Map Genie nicht, sondern
    die Kacheln fehlen nur (Ränder, Meer). Ohne bekannte Kachel False."""
    if not _mg.get("ok"):
        return False
    try:
        sources.fetch(mapgenie.TILES + _mg["ok"], timeout=30, raw=True)
        return True
    except sources.FetchError:
        return False
    finally:
        _mg["last"] = time.monotonic()


def _tile_of(m, z, x, y):
    """(Pfad unter kacheln/, Adresse) einer Kachel, (None, None) außerhalb der Karte."""
    if m.get("quelle") in TILE_SRC:
        return TILE_SRC[m["quelle"]].tile(m, z, x, y) or (None, None)
    rel = mapgenie.tile_ok(m["kacheln"], z, x, y, m.get("endung", "png"))
    if not rel or not (m["min_zoom"] <= z <= m["max_zoom"]):
        return None, None
    r = mapgenie.tile_range(mapgenie.bounds_of(m), z)
    if r and not (r[0] <= x <= r[1] and r[2] <= y <= r[3]):
        return None, None                # außerhalb der Karte gibt es keine Kachel; nicht nachfragen
    return rel, mapgenie.TILES + rel


def mg_tile(spiel, karte, z, x, y, pause=MG_TILE_PAUSE, stock=False):
    """Pfad einer Kachel im Datenordner; fehlt sie, einmal bei der Quelle holen (eine Anfrage zur Zeit, kurze Pause).
    Ein einzelnes 403 heißt bei Map Genie „Kachel gibt es nicht“; erst viele nacheinander oder 429 lassen die Quelle
    24 Stunden ruhen. pokemoncompletion ruht schon nach einem 403 oder 429. None, wenn es sie nicht gibt.
    Hat der Vorrat die Karte ganz durchgesehen, fragt die Oberfläche nicht mehr nach: was fehlt, gibt es nicht."""
    m = _mg_map(spiel, karte)
    rel, url = _tile_of(m, z, x, y) if m else (None, None)
    if not rel:
        return None
    f = mg_dir("kacheln", *rel.split("/"))
    if os.path.isfile(f):
        return f
    _miss_load()
    sp = (mg_maps(spiel) or {}).get("spiel", spiel)
    v = _mg["vorrat"].get(f"{sp}/{karte}") or {}
    if not stock and v.get("fertig") and v.get("ganz"):
        return None
    if m.get("quelle") in TILE_SRC:
        return _cdn_tile(rel, url, f, pause, m["quelle"]) if url else None      # ohne Adresse: selbst gezeichnet
    with _mg_lock:
        if os.path.isfile(f):
            return f
        if rel in _mg["miss"] or _mg["rest"] > _iso(now()):
            return None
        wait = _mg["last"] + pause - time.monotonic()
        if wait > 0:
            sleep(wait)
        try:
            body = sources.fetch(mapgenie.TILES + rel, timeout=30, raw=True)
        except sources.FetchError as e:
            _mg["fehler"] = f"HTTP {e.status or '?'} bei {rel} ({_iso(now())[:16].replace('T', ' ')})"
            _mg["n403"] = _mg["n403"] + 1 if e.status == 403 else 0
            if e.status == 403 and _mg["n403"] >= MG_403_MAX and _mg_probe():
                _mg["n403"] = 0          # bekannte Kachel kommt noch: am Rand gibt es eben viele leere Kacheln
                _mg["r403"] = []
            if e.status == 429 or _mg["n403"] >= MG_403_MAX:
                _mg["rest"] = _iso(now() + timedelta(hours=REST_H))
                for r in _mg.get("r403") or []:            # das war eine Sperre, keine fehlenden Kacheln
                    _mg["miss"].discard(r)
                    (_mg.get("miss_am") or {}).pop(r, None)
                _mg["r403"] = []
            elif e.status:
                _mg.setdefault("r403", []).append(rel)
                _miss_add(rel, e.status in (403, 404))
            return None
        finally:
            _mg["last"] = time.monotonic()
        _mg["n403"] = 0
        _mg["r403"] = []
        _mg["ok"] = rel
        if not (body[:8] == b"\x89PNG\r\n\x1a\n" or body[:3] == b"\xff\xd8\xff" or body[8:12] == b"WEBP"):
            _miss_add(rel)
            return None
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f + ".neu", "wb") as fh:
            fh.write(body)
        os.replace(f + ".neu", f)
        return f


TILE_SRC = {"pokemoncompletion": pkcompletion, "ign": ign, "dittobase": dittobase, "rankedboost": rankedboost, "ironmon": ironmon, "raidnester": raidnester, "pokearth": pokearth}     # Kartenquellen mit eigenem Kachelschema


def _cdn_tile(rel, url, f, pause, quelle):
    """Kachel einer anderen Quelle als Map Genie holen; nach 403 oder 429 ruht nur diese Quelle."""
    with _mg_lock:
        if os.path.isfile(f):
            return f
        if rel in _mg["miss"] or _mg["rest_" + quelle] > _iso(now()):
            return None
        wait = _mg["last"] + pause - time.monotonic()
        if wait > 0:
            sleep(wait)
        try:
            body = sources.fetch(url, timeout=30, raw=True)
        except sources.FetchError as e:
            _mg["fehler"] = f"{quelle}: HTTP {e.status or '?'} bei {rel} ({_iso(now())[:16].replace('T', ' ')})"
            if e.status in (403, 429):
                _mg["rest_" + quelle] = _iso(now() + timedelta(hours=REST_H))
            elif e.status:
                _miss_add(rel, e.status == 404)
            return None
        finally:
            _mg["last"] = time.monotonic()
        if not (body[:8] == b"\x89PNG\r\n\x1a\n" or body[:3] == b"\xff\xd8\xff"):
            _miss_add(rel)
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
    old_texts = store.load_json("pokewiki_texte.json", {})
    if old_texts:
        old["texte"] = old_texts            # liegen in einer eigenen Datei, siehe _wiki_texts
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
    texte = _wiki_texts(src, log, at)
    if texte:
        out["texte"] = texte
    st["sources"]["pokewiki"] = src.result(seiten=sum(len(v) for k in ("attacken", "items") for v in out[k].values()),
                                           karten=len(karte), texte=sum(len(texte.get(k) or {}) for k in WIKI_TEXT_KINDS))
    if src.blocked:
        st["rest"]["pokewiki"] = _iso(now() + timedelta(hours=REST_H))
    if src.stopped or not any(out["attacken"].values()):
        return dict(old, texte=texte) if texte else old
    store.save_json("pokewiki.json", {k: v for k, v in out.items() if k != "texte"})
    return out


WIKI_TEXT_KINDS = ("pokemon", "attacken", "faehigkeiten")
_WIKI_SUFFIX = {"attacken": " (Attacke)", "faehigkeiten": " (Fähigkeit)"}


def wiki_text_titles(con):
    """Deutsche Namen aller Arten, Attacken und Fähigkeiten: {Art der Seite: [Titel]}."""
    def names(sql):
        return sorted({r[0] for r in con.execute(sql) if r[0]})
    return {"pokemon": names("SELECT name FROM pokemon_species_names WHERE local_language_id = 6"),
            "attacken": names("SELECT name FROM attacke"),
            "faehigkeiten": names("SELECT name FROM ability_names WHERE local_language_id = 6 AND ability_id < 10000")}


def _wiki_page(kind, wt):
    """Was aus einer Seite übernommen wird, oder None, wenn sie nichts davon trägt (etwa eine Begriffsklärung)."""
    if kind == "pokemon":
        v = {"texte": pokewiki.dex_texts(wt), "aufgaben": pokewiki.research_tasks(wt)}
        return v if v["texte"] or v["aufgaben"] else None
    v = pokewiki.move_texts(wt) if kind == "attacken" else pokewiki.ability_texts(wt)
    return {"texte": v} if v else None


def _wiki_texts(src, log, at):
    """Deutsche Texte je Spiel aus dem PokéWiki (pokewiki_texte.json): {"stand", Art: {Name: {"texte": {Kürzel: Text},
    "aufgaben": […]}}}. Alle WIKI_TEXT_TAGE Tage alles neu, sonst nur Namen, die noch fehlen. Seiten, die die API in
    einer Antwort nicht mehr unterbringt, kommen in einer zweiten Runde; tragen Attacken oder Fähigkeiten nichts, wird
    „Name (Attacke)“ bzw. „Name (Fähigkeit)“ versucht."""
    old = store.load_json("pokewiki_texte.json", {})
    con = db.game()
    if con is None or src.stopped:
        return old
    try:
        titles = wiki_text_titles(con)
    except Exception as e:
        log(f"PokéWiki: Namen für Texte nicht lesbar ({e})")
        return old
    finally:
        con.close()
    age = _ago(old.get("stand"), at)
    full = age is None or age >= timedelta(days=WIKI_TEXT_TAGE)
    out = {"stand": old.get("stand"), "gefragt": dict(old.get("gefragt") or {})}
    asked = 0
    labels = {"pokemon": "Pokédex-Einträge", "attacken": "Attackentexte", "faehigkeiten": "Fähigkeitstexte"}

    def ask(kind, names, have):
        """Seiten holen; gibt (fehlt in der Antwort, ohne Texte) zurück. names: {Seitentitel: Name}."""
        nonlocal asked
        absent, empty, todo = [], [], list(names)
        for i in range(0, len(todo), WIKI_TEXT_BATCH):
            part = todo[i:i + WIKI_TEXT_BATCH]
            STATE.update(step=f"PokéWiki: {labels[kind]}", done=i, total=len(todo))
            t = src.get(pokewiki.batch_url(part))
            asked += 1
            if src.stopped:
                break
            try:
                got = pokewiki.pages(t or "{}")
            except ValueError as e:
                log(f"PokéWiki: Antwort nicht lesbar ({e})")
                got = {}
            for title in part:
                v = _wiki_page(kind, got[title]) if title in got else None
                if v:
                    have[names[title]] = v
                else:
                    (absent if title not in got else empty).append(names[title])
        return absent, empty

    for kind in WIKI_TEXT_KINDS:
        have = dict(old.get(kind) or {})
        done = set() if full else set(out["gefragt"].get(kind) or ())
        todo = [t for t in titles[kind] if full or (t not in have and t not in done)]
        absent, empty = ask(kind, {t: t for t in todo}, have) if todo else ([], [])
        if absent and not src.stopped:              # fehlt in der Antwort: Antwort war voll, oder es gibt die Seite nicht
            a2, e2 = ask(kind, {t: t for t in absent}, have)
            empty += a2 + e2
        if empty and kind in _WIKI_SUFFIX and not src.stopped:
            ask(kind, {t + _WIKI_SUFFIX[kind]: t for t in empty}, have)
        out[kind] = have
        if todo and not src.stopped:
            out["gefragt"][kind] = sorted(set(titles[kind]) - set(have))      # ohne Texte: erst beim nächsten vollen Lauf
    if full and not src.stopped:
        out["stand"] = _iso(at)
    if asked:
        n = {k: len(out.get(k) or {}) for k in WIKI_TEXT_KINDS}
        log(f"PokéWiki: Texte für {n['pokemon']} Pokémon, {n['attacken']} Attacken und {n['faehigkeiten']} Fähigkeiten"
            + (" (unvollständig, Rest beim nächsten Abgleich)" if src.stopped else ""))
        store.save_json("pokewiki_texte.json", out)
    return out


SEREBII_PAUSE = 2.0         # Sekunden zwischen zwei Seiten bei Serebii


def _serebii(st, log, at):
    """Seiten von Serebii: Abklingzeiten in Legenden: Z-A und die Pokédexe von Pokopia, {"za": {...}, "pokopia": {Dex: [...]}}.
    Fehlt etwas (Sperre, Fehler, Seite ohne Treffer), gilt dafür der letzte Lauf (serebii.json im Datenordner)."""
    old = store.load_json("serebii.json", {})
    if _resting(st, "serebii", at):
        log(f"Serebii ruht bis {st['rest']['serebii'][:16].replace('T', ' ')} UTC")
        return old
    src = _Source("serebii", log, pause=SEREBII_PAUSE)
    STATE["step"] = "Serebii: Attacken in Legenden: Z-A"
    za = serebii.za_cooldowns(src.get(serebii.ZA_ATTACKS) or "")
    pk = {}
    for dex, url in serebii.POKOPIA.items():
        if src.stopped:
            break
        STATE["step"] = f"Serebii: Pokopia, {serebii.POKOPIA_DEX[dex]}"
        rows = serebii.pokopia_dex(src.get(url, absent=(404,)) or "")
        if rows:
            pk[dex] = rows
    out = {"za": za or old.get("za") or {}, "pokopia": {**(old.get("pokopia") or {}), **pk}}
    st["sources"]["serebii"] = src.result(abklingzeiten=len(za), pokopia=sum(len(v) for v in pk.values()))
    if src.blocked:
        st["rest"]["serebii"] = _iso(now() + timedelta(hours=REST_H))
    log(f"Serebii: {len(za)} Abklingzeiten in Z-A, Pokopia " + (", ".join(f"{serebii.POKOPIA_DEX[k]} {len(v)}" for k, v in pk.items()) or "ohne Treffer"))
    if out["za"] or out["pokopia"]:
        if za or pk:
            store.save_json("serebii.json", out)
        return out
    return old


BISA_PAUSE = 3.0            # Sekunden zwischen zwei Seiten bei BisaFans


def _bisafans(st, log, at):
    """Seiten von BisaFans: die Aufträge in Legenden: Arceus auf Deutsch, {"la_auftraege": [...]}. Bei Sperre, Fehler oder
    einer Seite ohne Treffer gilt der letzte Lauf (bisafans.json im Datenordner)."""
    old = store.load_json("bisafans.json", {})
    if _resting(st, "bisafans", at):
        log(f"BisaFans ruht bis {st['rest']['bisafans'][:16].replace('T', ' ')} UTC")
        return old
    src = _Source("bisafans", log, pause=BISA_PAUSE)
    STATE["step"] = "BisaFans: Aufträge in Legenden: Arceus"
    rows = bisafans.la_requests(src.get(bisafans.LA_REQUESTS) or "")
    pages = []
    for i, url in enumerate(bisafans.LA_STORY):
        if src.stopped:
            break
        STATE.update(step="BisaFans: Hauptmissionen in Legenden: Arceus", done=i, total=len(bisafans.LA_STORY))
        pages.append(src.get(url, absent=(404,)) or "")
    story = bisafans.la_missions(pages)
    za_pages = []
    for url in bisafans.ZA_REQUESTS:
        if src.stopped:
            break
        STATE.update(step="BisaFans: Nebenmissionen in Legenden: Z-A")
        za_pages.append(src.get(url, absent=(404,)) or "")
    za_rows = bisafans.merged_requests(za_pages)
    # Haupt- und Dimensions-Missionen in Z-A (und Nebenmissionen, die BisaFans noch fehlen) aus dem PokéWiki
    za, bbq = {}, []
    if not _resting(st, "pokewiki", at):
        STATE.update(step="PokéWiki: Missionen in Legenden: Z-A, Blaubeer-Missionen")
        wsrc = _Source("pokewiki", log, pause=BISA_PAUSE)
        t = wsrc.get(pokewiki.batch_url([pokewiki.ZA_MISSIONS, pokewiki.BBQ_PAGE]), absent=(404,))
        try:
            ps = pokewiki.pages(t) if t else {}
            za = pokewiki.za_missions(ps.get(pokewiki.ZA_MISSIONS, ""))
            bbq = pokewiki.bbq_missions(ps.get(pokewiki.BBQ_PAGE, ""))
        except ValueError:
            za = {}
    have = {r["nr"] for r in za_rows}
    for x in (za or {}).get("neben") or []:
        if x["nr"] not in have:
            za_rows.append({"nr": x["nr"], "name": x["name"], "beschreibung": x["beschreibung"], "aufgabe": "", "ort": "",
                            "loesung": x.get("freischaltung") and "Freigeschaltet: " + x["freischaltung"] or "", "belohnung": x["belohnung"]})
    za_rows.sort(key=lambda r: r["nr"])
    za_story = [dict(x, kapitel=1) for x in (za or {}).get("haupt") or []] + \
        [dict(x, nr=100 + x["nr"], kapitel=2) for x in (za or {}).get("dimension") or []]
    st["sources"]["bisafans"] = src.result(auftraege=len(rows), missionen=len(story), za_nebenmissionen=len(za_rows), za_missionen=len(za_story))
    if src.blocked:
        st["rest"]["bisafans"] = _iso(now() + timedelta(hours=REST_H))
    log(f"BisaFans: {len(rows)} Aufträge und {len(story)} Hauptmissionen in Legenden: Arceus" + ("" if rows else ", es gilt der letzte Lauf")
        + f"; Legenden: Z-A {len(za_rows)} Nebenmissionen, {len(za_story)} Haupt- und Dimensions-Missionen (PokéWiki)"
        + f"; {len(bbq)} Blaubeer-Missionen (PokéWiki)")
    if rows or za_rows or bbq:
        out = {"la_auftraege": rows or old.get("la_auftraege") or [], "la_missionen": story or old.get("la_missionen") or [],
               "za_auftraege": za_rows or old.get("za_auftraege") or [], "za_missionen": za_story or old.get("za_missionen") or [],
               "blaubeer": bbq or old.get("blaubeer") or []}
        store.save_json("bisafans.json", out)
        return out
    return old


SHINY_DAYS = 30            # so oft holt der Abgleich die Liste der Shiny-Sperren neu
SHINY_PAGE = "List_of_unobtainable_Shiny_Pokémon"


def _shiny(st, log, at):
    """0.51: Bulbapedia „List of unobtainable Shiny Pokémon“ als Wikitext: {"am", "text"} in bulbapedia_shiny.json.
    Jünger als SHINY_DAYS: der letzte Lauf gilt."""
    old = store.load_json("bulbapedia_shiny.json", {}) or {}
    if old.get("text") and old.get("am", "") > _iso(now() - timedelta(days=SHINY_DAYS)):
        return old
    if _resting(st, "bulbapedia", at):
        return old
    src = _Source("bulbapedia", log)
    STATE.update(step="Bulbapedia: Shiny-Sperren")
    t = src.get("https://bulbapedia.bulbagarden.net/w/api.php?action=parse&page=" + urllib.parse.quote(SHINY_PAGE)
                + "&prop=wikitext&format=json&redirects=1")
    text = ""
    try:
        w = (json.loads(t) if t else {}).get("parse", {}).get("wikitext")
        text = w.get("*", "") if isinstance(w, dict) else (w or "")
    except ValueError:
        text = ""
    st["sources"]["bulbapedia"] = src.result(shiny=len(shiny.parse(text)) if text else 0)
    if src.blocked:
        st["rest"]["bulbapedia"] = _iso(now() + timedelta(hours=REST_H))
    if not text:
        return old
    out = {"am": _iso(now()), "text": text}
    store.save_json("bulbapedia_shiny.json", out)
    return out


TRAINER_DAYS = 7           # so oft holt der Abgleich die Trainerseiten neu (sie ändern sich selten)


def _trainer(st, log, at):
    """Teams der Arenaleiter, Top Vier, Champs und Rivalen aller Hauptspiele aus dem PokéWiki, dazu die Trainer auf den
    Ortsseiten (Routen, Höhlen, Städte); Kategorien, dann die Seiten zu je 50: {"am", "teams": [...]} in pokewiki_trainer.json. Jünger als TRAINER_DAYS: der letzte Lauf gilt."""
    old = store.load_json("pokewiki_trainer.json", {}) or {}
    cats = sorted(pokewiki.TRAINER_CATS)          # neue Kategorien (0.48.6: Hisui) holen sofort neu, nicht erst nach TRAINER_DAYS
    if old.get("teams") and old.get("am", "") > _iso(now() - timedelta(days=TRAINER_DAYS)) and old.get("kategorien", cats) == cats:
        return old
    if _resting(st, "pokewiki", at):
        return old
    src = _Source("pokewiki", log, pause=BISA_PAUSE)
    roles = {}
    for cat, rolle in pokewiki.TRAINER_CATS.items():
        cont, n = None, 0
        while n < 10 and not src.stopped:
            STATE.update(step=f"PokéWiki: Trainer ({cat})")
            t = src.get(pokewiki.category_url(cat, cont), absent=(404,))
            try:
                titles, cont = pokewiki.category_members(t) if t else ([], None)
            except ValueError:
                titles, cont = [], None
            for x in titles:
                roles.setdefault(x, rolle)
            n += 1
            if not cont:
                break
    names, teams = sorted(roles), []
    for i in range(0, len(names), pokewiki.BATCH):
        if src.stopped:
            break
        STATE.update(step="PokéWiki: Teams der Trainer", done=i, total=len(names))
        t = src.get(pokewiki.batch_url(names[i:i + pokewiki.BATCH]))
        try:
            got = pokewiki.pages(t) if t else {}
        except ValueError:
            got = {}
        for title, wt in got.items():
            teams += pokewiki.trainer_teams(wt, title, roles.get(title, ""))
    teams = pokewiki.dedupe_teams(teams)
    st["sources"]["trainer"] = src.result(trainer=len(names), teams=len(teams))
    if src.blocked:
        st["rest"]["pokewiki"] = _iso(now() + timedelta(hours=REST_H))
    log(f"PokéWiki: {len(teams)} Teams von {len(names)} Trainern" + ("" if teams else ", es gilt der letzte Lauf"))
    if teams and not src.stopped:
        out = {"am": _iso(now()), "teams": teams, "kategorien": cats}
        store.save_json("pokewiki_trainer.json", out)
        return out
    return old


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


# Pausen im Verbindungstest je Server (sonst PAUSE): wer beim Abgleich langsamer abgefragt wird, auch hier
DIAG_TIMEOUT = 20           # Sekunden ohne Antwort, dann gibt eine Abfrage im Verbindungstest auf
DIAG_LIMIT = 60             # Sekunden insgesamt je Abfrage (große Seiten, die langsam tröpfeln)
DIAG_HANG = 120             # Sekunden ohne jeden Fortschritt, dann beendet sich der Test trotz offener Abfragen
DIAG_PARALLEL = 6           # so viele Abfragen gleichzeitig (mehr überlastete die Namensauflösung: „Errno -3 Try again“)
DIAG_PAUSE = {"www.serebii.net": SEREBII_PAUSE, "www.pokewiki.de": WIKI_PAUSE, "mapgenie.io": MG_PAUSE}


def tile_patterns(t, limit=50):
    """Kachelmuster wie „…/{z}/{x}/{y}.png“ in einer Seite. Sucht nur rund um jedes „{z}“: ein Muster mit führendem
    [\\w…]* über die ganze Seite braucht bei langen Wortketten (Base64 in großen Seiten) quadratisch lange und hielt
    mit dem GIL den ganzen Dienst fest."""
    out, i = set(), t.find("{z}")
    while i >= 0 and len(out) < limit:
        win = t[max(0, i - 200):i + 200]
        m = re.search(r"[\w/.:-]{0,200}\{z\}[\w/.{}-]{0,200}", win)
        if m:
            out.add(m.group(0))
        i = t.find("{z}", i + 3)
    return sorted(out)


def diagnose(proben=None, stand=None):
    """Verbindung testen: jede Quelle einmal abfragen und beschreiben, was zurückkommt. Speichert nichts.
    proben: dict, in das Probe-Seiten (gekürzt) kommen, damit sich Leser für neue Quellen bauen lassen.
    stand: dict für den Fortschritt (gesamt, fertig, laeuft: Namen der Abfragen, die gerade laufen).
    Verschiedene Server fragt der Test gleichzeitig an, jeden Server für sich nacheinander und mit Pause;
    die Zeilen bleiben in der Reihenfolge der Abfragen."""
    import concurrent.futures as cf
    lines = [f"Pokédex {sources.VERSION}, Test vom {now().strftime('%d.%m.%Y %H:%M')} UTC"]
    proben = {} if proben is None else proben
    stand = {} if stand is None else stand
    stand.update(gesamt=0, fertig=0, laeuft=[])
    html = {"Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}
    lock, pools, futs = threading.Lock(), {}, []

    gate = threading.Semaphore(DIAG_PARALLEL)

    def one(slot, name, url, info, raw, keep, headers, pause, data=None):
        r = None
        gate.acquire()
        with lock:
            stand["laeuft"].append(name)
        try:
            post = {"data": data} if data is not None else {}
            r = sources.request(url, timeout=DIAG_TIMEOUT, raw=raw, headers=headers, limit=DIAG_LIMIT, **post)
            if r["error"] and "Errno -3" in r["error"]:      # Namensauflösung kurz überlastet: einmal nachfassen
                sleep(2)
                r = sources.request(url, timeout=DIAG_TIMEOUT, raw=raw, headers=headers, limit=DIAG_LIMIT, **post)
            if r["error"]:
                lines[slot] = f"{name}: keine Verbindung ({r['error']})"
                return None
            size = len(r.get("body", b"")) if raw else len(r["text"])
            head = (f"{name}: HTTP {r['status']}, Server {r['server'] or '?'}, {size} {'Bytes' if raw else 'Zeichen'}"
                    + (f" (nach {DIAG_LIMIT} s abgebrochen, nur der Anfang)" if r.get("teil") else ""))
            if r["status"] >= 400 or (not raw and sources.challenge(r["text"])):
                lines[slot] = (head + (", gesperrt" if r["status"] in sources.BLOCKED else "") +
                               (", Prüfseite (Cloudflare)" if not raw and sources.challenge(r["text"]) else "") +
                               ("" if raw else f". Anfang: {' '.join(r['text'][:160].split())}"))
                return None
            try:
                lines[slot] = f"{head}, {info(r.get('body') if raw else r['text'])}"
            except Exception as e:
                lines[slot] = f"{head}, nicht auswertbar ({type(e).__name__}: {e})"
            if keep and not raw:
                proben[name] = r["text"][:keep if keep is not True else PROBE_MAX]
            elif keep and raw:                 # 0.52: Bilder für die Auswertung als base64 mitnehmen
                proben[name] = "base64:" + base64.b64encode(r.get("body", b"")[:keep if keep is not True else PROBE_MAX]).decode("ascii")
            return r
        except Exception as e:
            lines[slot] = f"{name}: Fehler im Test ({type(e).__name__}: {e})"
            return None
        finally:
            with lock:
                stand["laeuft"].remove(name)
                stand["fertig"] += 1
            gate.release()
            if r is not None and not r.get("error"):
                sleep(pause)

    def probe(name, url, info, raw=False, keep=False, headers=None, data=None):
        """Reiht die Abfrage beim Server ein; gibt ein Future zurück (.result(): Antwort oder None)."""
        host = urllib.parse.urlsplit(url).hostname or ""
        if host not in pools:
            pools[host] = cf.ThreadPoolExecutor(1, thread_name_prefix="test-" + host)
        lines.append(f"{name}: keine Antwort")
        with lock:
            stand["gesamt"] += 1
        f = pools[host].submit(one, len(lines) - 1, name, url, info, raw, keep, headers, DIAG_PAUSE.get(host, PAUSE), data)
        futs.append(f)
        return f

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
        j = json.loads(text)
        if "parse" not in j:
            return f"Seite gibt es nicht ({(j.get('error') or {}).get('code', '?')})"
        p = j["parse"]
        wt = p["wikitext"]["*"] if isinstance(p["wikitext"], dict) else p["wikitext"]
        return f"Seite „{p['title']}“, {len(wt)} Zeichen Wikitext, {wt.count('{{')} Vorlagen"
    probe("PokéWiki, API", POKEWIKI_API + "?action=query&meta=siteinfo&format=json", wiki_info)
    for page in ("Pokémon-Legenden: Arceus", "Bidiza", "Obsidian-Grasland", "Tackle", "Kraftstil", "Alpha-Pokémon",
                 "Forschungsaufgabe", "Edelhorde", "Raum-Zeit-Verzerrung"):
        probe(f"PokéWiki, Seite {page}", POKEWIKI_API + "?action=parse&page=" + urllib.parse.quote(page)
              + "&prop=wikitext&format=json&redirects=1", wiki_page, keep=True)
    # 0.42: Trainerteams und Blaubeer-Missionen (der Leser zählt, was er findet)
    def wiki_trainer(text):
        got = pokewiki.pages(text)
        ts = [t for k, v in got.items() for t in pokewiki.trainer_teams(v, k, "")]
        bbq = pokewiki.bbq_missions(got.get(pokewiki.BBQ_PAGE, ""))
        return (f"{len(ts)} Teams ({', '.join(sorted({g for t in ts for g in t['spiele']}))}); "
                f"{len(bbq)} Blaubeer-Missionen ({', '.join(sorted({x['bereich'] for x in bbq}))})")
    probe("PokéWiki, Trainerteams und Blaubeer-Missionen", pokewiki.batch_url(["Rocko", "Nemila", pokewiki.BBQ_PAGE]), wiki_trainer)
    probe("PokéWiki, Kategorie Arenaleiter", pokewiki.category_url("Arenaleiter"),
          lambda t: f"{len(pokewiki.category_members(t)[0])} Seiten")
    # 0.48.6: Trainer in Legenden: Arceus (Charaktere aus Hisui; Kamado und Wächterin Irida als Stichprobe)
    probe("PokéWiki, Kategorie Charakter aus Hisui", pokewiki.category_url("Charakter aus Hisui"),
          lambda t: (lambda n: f"{len(n)} Seiten: " + ", ".join(n[:15]))(pokewiki.category_members(t)[0]), keep=True)
    probe("PokéWiki, Trainerteams Hisui (Kamado, Irida, Adamas)", pokewiki.batch_url(["Kamado", "Irida", "Adamas"]), wiki_trainer)
    def wiki_batch(text):
        got = pokewiki.pages(text)
        vals = {k: pokewiki.la_move(v) for k, v in got.items()}
        return f"{len(got)} Seiten gebündelt; " + "; ".join(f"{k}: {v}" for k, v in vals.items())
    probe("PokéWiki, Bündel Attacken (Legenden: Arceus)", pokewiki.batch_url(["Tackle", "Donnerblitz", "Kraftschub"], True), wiki_batch)

    # 0.36.0: deutsche Texte je Spiel; meldet, welche Spiele die Kürzel abdecken und welche Kürzel unbekannt sind
    def wiki_texts(text):
        got = pokewiki.pages(text)
        out = []
        for name, kind in (("Pikachu", "pokemon"), ("Donnerblitz", "attacken"), ("Statik", "faehigkeiten")):
            v = _wiki_page(kind, got.get(name, "")) if name in got else None
            if not v:
                out.append(f"{name}: keine Texte")
                continue
            tx = v["texte"]
            unk = pokewiki.unknown_keys(kind, tx)
            out.append(f"{name}: {len(pokewiki.per_game(kind, tx))} Spiele" + (f", unbekannt: {', '.join(unk)}" if unk else "")
                       + (f", {len(v.get('aufgaben') or [])} Forschungsaufgaben" if kind == "pokemon" else ""))
        return "; ".join(out)
    probe("BisaFans, Aufträge in Legenden: Arceus", bisafans.LA_REQUESTS,
          lambda t: (lambda r: f"{len(r)} Aufträge" + (f", zuletzt Nr. {r[-1]['nr']} „{r[-1]['name']}“, Belohnung {r[-1]['belohnung'] or '?'}"
                                                        if r else ""))(bisafans.la_requests(t)), keep=True)
    probe("PokéWiki, Texte je Spiel (Pikachu, Donnerblitz, Statik)", pokewiki.batch_url(["Pikachu", "Donnerblitz", "Statik"]),
          wiki_texts, keep=True)
    probe("Bulbapedia, API", "https://bulbapedia.bulbagarden.net/w/api.php?action=query&meta=siteinfo&format=json", wiki_info)
    probe("Bulbapedia, Seite Bidoof", "https://bulbapedia.bulbagarden.net/w/api.php?action=parse&page=Bidoof_(Pok%C3%A9mon)"
          "&prop=wikitext&format=json&redirects=1", wiki_page, keep=True)
    # 0.13.0: Fangfaktoren der Hisui-Bälle zum Gegenprüfen (Bulbapedia und PokéWiki), Kartendaten des PLA Companion
    # 0.48.8: die echte Fangformel in Legenden: Arceus (Seite „Catch rate“ und alle Hisui-Bälle, PokéWiki „Fangchance“)
    for page in ("Heavy_Ball_(Hisui)", "Feather_Ball", "Ultra_Ball_(Hisui)", "Catch_rate", "Poké_Ball_(Hisui)",
                 "Great_Ball_(Hisui)", "Wing_Ball", "Jet_Ball", "Leaden_Ball", "Gigaton_Ball", "Origin_Ball", "Strange_Ball"):
        probe(f"Bulbapedia, Seite {page}", "https://bulbapedia.bulbagarden.net/w/api.php?action=parse&page=" + urllib.parse.quote(page)
              + "&prop=wikitext&format=json&redirects=1", wiki_page, keep=400_000)
    for page in ("Schwerball", "Federball", "Hyperball", "Fangchance", "Fangrate"):
        probe(f"PokéWiki, Seite {page}", POKEWIKI_API + "?" + urllib.parse.urlencode(
            {"action": "parse", "page": page, "prop": "wikitext", "format": "json", "redirects": 1}), wiki_page, keep=400_000)
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
    for spiel in mapgenie.GAMES:
        for slug in mapgenie.slugs(spiel):
            probe(f"Map Genie, {slug}", mapgenie.game_url(slug),
                  lambda t, s=slug: page_info(t) + ", Karten: " + (", ".join(mapgenie.map_slugs(t, s)) or "keine"), headers=html)
    # eine Kachel innerhalb der Karte (zeigt, ob der Kachelspeicher antwortet; außerhalb meldet er 403)
    probe("Map Genie, Kachel Hisui 9/254/254", mapgenie.TILES + "pokemon-legends-arceus/hisui-region/default-v3/9/254/254.png",
          lambda b: f"{len(b)} Bytes, " + ("PNG" if b[:4] == b"\x89PNG" else "kein Bild"), raw=True)
    # je gespeicherter Karte: Kachelmuster, Zoom und Grenzen (zeigt, warum eine Karte keine Kacheln bekommt)
    for spiel in MAP_GAMES:
        for m in (mg_maps(spiel) or {}).get("karten", []):
            rel = (_tile_of(m, m["min_zoom"], 0, 0)[0] if m.get("quelle")
                   else mapgenie.tile_ok(m["kacheln"], m["min_zoom"], 0, 0, m.get("endung", "png")))
            v = mg_status()["vorrat"].get(f"{spiel}/{m['slug']}") or {}
            lines.append(f"{m.get('quelle') or 'Map Genie'}, Karte {spiel}/{m['slug']}: Muster {m['kacheln'] or '–'} ({m.get('endung', '?')}), "
                         f"Zoom {m['min_zoom']}–{m['max_zoom']}, Grenzen {'ja' if m.get('bounds') else 'aus den Orten' if mapgenie.bounds_of(m) else 'keine'}, "
                         f"Kachelpfad {'ok' if rel else 'unbrauchbar'}" + (f", Vorrat {v.get('da', 0)}/{v.get('alle', 0)}" if v else ""))
    st = mg_status()
    lines.append(f"Map Genie, Kacheln im Dienst: {'ruht bis ' + st['ruht'] if st['ruht'] else 'bereit'}"
                 + (f", zuletzt {st['fehler']}" if st["fehler"] else ""))
    # ältere Spiele: interaktive Karten mit Symbolen (Items, Trainer, Pokémon) zum Abhaken
    for g in ("Yellow", "Crystal", "Emerald", "Platinum", "Red", "Gold", "FireRed", "HeartGold", "Black", "X", "Sun"):
        probe(f"pokemoncompletion, {g}", f"https://pokemoncompletion.com/completion/{g}", page_info, keep=200_000, headers=html)

    section("Gesuchte Quellen (Spezial in Gen. 1, Abklingzeiten in Z-A, Karten älterer Spiele)")
    # Spezial-Wert und frühere Basiswerte: die Generations-Mods von Showdown (seit 0.23.0 im Abgleich)
    from . import showdown as _sd
    for n in (1, 2, 5, 6):
        probe(f"Showdown, Basiswerte Generation {n}", f"{SD_RAW}mods/gen{n}/pokedex.ts",
              lambda t: f"{len(_sd.mod_stats(t))} Pokémon mit eigenen Basiswerten")
    img_info = lambda t: page_info(t) + f", {t.count('<img')} Bilder, {t.count('.png')} PNG-Verweise"

    def wiki_hits(text):
        hits = (json.loads(text).get("query") or {}).get("search") or []
        return f"{len(hits)} Treffer: " + ", ".join(h.get("title", "") for h in hits[:10])
    # Abklingzeiten der Attacken in Legenden: Z-A (Echtzeitkampf)
    probe("PokéWiki, Suche Abklingzeit Z-A", POKEWIKI_API + "?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Abklingzeit Legenden Z-A", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)
    probe("Bulbapedia, Suche cooldown Z-A", "https://bulbapedia.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "cooldown Legends Z-A move", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)
    probe("Serebii, Legenden: Z-A Übersicht", "https://www.serebii.net/legendsz-a/", img_info, keep=True, headers=html)
    probe("Serebii, Attackdex Z-A", "https://www.serebii.net/attackdex-za/", img_info, keep=True, headers=html)
    # Leser seit 0.30.0: die ganzen Seiten, damit sich der Leser an der echten Seite prüfen lässt
    probe("Serebii, Z-A Attacken (Leser)", serebii.ZA_ATTACKS,
          lambda t: f"{len(serebii.za_cooldowns(t))} Abklingzeiten gelesen, z. B. " + ", ".join(
              f"{v['name']} {v['abkling']} s" for v in list(serebii.za_cooldowns(t).values())[:5]), keep=600_000, headers=html)
    for dex, url in serebii.POKOPIA.items():
        probe(f"Serebii, Pokopia {serebii.POKOPIA_DEX[dex]} (Leser)", url,
              lambda t: f"{len(serebii.pokopia_dex(t))} Pokémon gelesen, z. B. " + ", ".join(
                  f"#{r['nr']} {r['name']} ({', '.join(r['spezial'])})" for r in serebii.pokopia_dex(t)[:5]), keep=600_000, headers=html)
    probe("GitHub, Projekte zu Legenden: Z-A", "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
        {"q": "legends z-a pokemon data", "sort": "updated", "per_page": "15"}),
        lambda t: f"{json.loads(t).get('total_count', 0)} Projekte: " + ", ".join(r.get("full_name", "") for r in json.loads(t).get("items", [])[:15]), keep=True)
    # Karten älterer Spiele: Ortsbilder bei Serebii (PokéEarth), Disassemblies (pret) und das Bildarchiv von Bulbapedia
    for reg in ("kanto", "johto", "hoenn", "sinnoh"):
        probe(f"Serebii, PokéEarth {reg.title()}", f"https://www.serebii.net/pokearth/{reg}/", img_info, keep=True, headers=html)
    def earth_info(t):
        d = pokearth.extract(t)
        return f"Bildkarte {d['bild'].rsplit('/', 1)[-1]} ({d['w']}×{d['h']}) mit {len(d['orte'])} Orten" if d else "keine Bildkarte"
    for reg in ("unova", "kalos", "alola", "orre"):          # 0.41: Regionskarten der übrigen Spiele
        probe(f"Serebii, PokéEarth {reg.title()} (Bildkarte)", pokearth.page_url(reg), earth_info, keep=True, headers=html)
    probe("Serebii, PokéEarth Route 1 (Kanto)", "https://www.serebii.net/pokearth/kanto/route1.shtml", img_info, keep=True, headers=html)
    probe("Bulbapedia-Archiv, Kartenbilder Kanto", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Kanto Route 1 RBY", "srnamespace": "6", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)

    def blk(text):
        ps = [x.get("path", "") for x in json.loads(text).get("tree", [])]
        return f"{len(ps)} Dateien, {sum(p.endswith('.blk') for p in ps)} Kartenblöcke (.blk), {sum(p.endswith('.png') for p in ps)} Bilder"
    probe("GitHub: pret/pokered (Rot/Blau, Karten als Blöcke)", "https://api.github.com/repos/pret/pokered/git/trees/master?recursive=1", blk)
    probe("GitHub: pret/pokecrystal (Kristall)", "https://api.github.com/repos/pret/pokecrystal/git/trees/master?recursive=1", blk)
    probe("Altissimo, Orte Gold/Silber/Kristall", "https://altissimo1.github.io/Main-Series/GSC/locations.html", img_info, keep=True, headers=html)
    # nächste Schritte aus dem letzten Test (11.11.): Seite „Cooldown“ bei Bulbapedia, Z-A-Projekte auf GitHub, Kartenbilder älterer Spiele
    probe("Bulbapedia, Seite Cooldown (Z-A)", "https://bulbapedia.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "parse", "page": "Cooldown", "prop": "wikitext", "format": "json"}),
        lambda t: (lambda w: f"{len(w)} Zeichen Wikitext, {w.count('{{')} Vorlagen, {w.lower().count('cooldown')}× cooldown")(
            ((json.loads(t).get("parse") or {}).get("wikitext") or {}).get("*", "")), keep=True)

    # 0.48.4: Shiny-Sperren je Spiel (Bulbapedia-Liste mit Zeichen je Spiel: fangbar, nur Übertragung, gar nicht; PokéWiki zum Gegenprüfen)
    def shiny_info(t):
        w = ((json.loads(t).get("parse") or {}).get("wikitext") or {}).get("*", "")
        return (f"{len(w)} Zeichen Wikitext, {w.count('{{')} Vorlagen, {w.count('|-')} Tabellenzeilen, "
                f"{w.lower().count('shiny lock') + w.lower().count('shiny-lock')}× shiny lock, {w.lower().count('transfer')}× transfer")
    for page in ("List_of_unobtainable_Shiny_Pok%C3%A9mon", "Shiny-locked", "Shiny_Pok%C3%A9mon"):
        probe(f"Bulbapedia, Seite {urllib.parse.unquote(page)}", "https://bulbapedia.bulbagarden.net/w/api.php?action=parse&page=" + page
              + "&prop=wikitext&format=json&redirects=1", shiny_info, keep=400_000)
    for page in ("Schillernde Pokémon", "Shiny-Lock"):
        probe(f"PokéWiki, Seite {page}", POKEWIKI_API + "?" + urllib.parse.urlencode(
            {"action": "parse", "page": page, "prop": "wikitext", "format": "json", "redirects": 1}), shiny_info, keep=400_000)

    def tree_hits(*words):
        def f(text):
            ps = [x.get("path", "") for x in json.loads(text).get("tree", [])]
            hit = [p for p in ps if any(w in p.lower() for w in words)]
            return f"{len(ps)} Dateien, {len(hit)} passend ({', '.join(words)}): " + ", ".join(hit[:12])
        return f
    for repo in ("Setmaster/ZA-Decoder", "Scotts-Thoughts/pokemon-data", "solomonjasperkim/pokehex", "NyanWinPhyo/dex-atlas"):
        probe(f"GitHub: {repo} (Z-A)", f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1", tree_hits("cool", "move", "waza", "za"), keep=True)
    probe("Bulbapedia-Archiv, Kartenbilder Johto", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Johto Route 29 GSC", "srnamespace": "6", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)
    probe("Bulbapedia-Archiv, Kartenbilder Hoenn", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Hoenn Route 101 RSE", "srnamespace": "6", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)
    probe("Serebii, PokéEarth Route 29 (Johto)", "https://www.serebii.net/pokearth/johto/route29.shtml", img_info, keep=True, headers=html)
    probe("Altissimo, Orte Rot/Blau/Gelb", "https://altissimo1.github.io/Main-Series/RBY/locations.html", img_info, keep=True, headers=html)

    section("Karten für Schwert/Schild, Strahlender Diamant/Leuchtende Perle und Let’s Go")
    # Map Genie hat sie nicht; IGN (Galar, Let’s Go) steht unter „Weitere Kartenquellen“, IGN-Pfade für DLCs und BDSP gibt es
    # nicht (404). Serebii zeigt in 3D-Spielen Bilder je Ort statt einer Karte; Bulbapedia hat Kartenbilder
    for reg in ("galar", "sinnoh"):
        probe(f"Serebii, PokéEarth {reg.title()}", f"https://www.serebii.net/pokearth/{reg}/", img_info, keep=True, headers=html)
    for name, page in (("Naturzone", "galar/wildarea"), ("Insel der Rüstung", "galar/isleofarmor"),
                       ("Kronen-Schneelande", "galar/thecrowntundra"), ("Untergrund (BDSP)", "sinnoh/grandunderground")):
        probe(f"Serebii, {name}", f"https://www.serebii.net/pokearth/{page}.shtml", img_info, keep=True, headers=html)
    probe("Bulbapedia-Archiv, Kategorie Spielkarten", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "categorymembers", "cmtitle": "Category:Game maps", "cmlimit": "100", "format": "json"}),
        lambda t: (lambda ms: f"{len(ms)} Einträge: " + ", ".join(m["title"] for m in ms[:15]))(
            (json.loads(t).get("query") or {}).get("categorymembers") or []), keep=True)
    probe("Bulbapedia-Archiv, Kartenbilder Galar", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Galar map", "srnamespace": "6", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)
    probe("Bulbapedia-Archiv, Kartenbilder Sinnoh BDSP", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Sinnoh BDSP map", "srnamespace": "6", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)
    probe("pokemoncompletion, Let’s Go", "https://pokemoncompletion.com/completion/LetsGo", page_info, keep=200_000, headers=html)

    section("Weitere Kartenquellen (Funde vom 11.11.)")
    # interaktive Karten: ob die Punkte als JSON nachgeladen werden (Hinweise in der Seite), sonst Bilder je Gebiet
    looks = lambda t: (page_info(t) + f", {t.count('.json')} × .json, {t.count('marker')} × marker, {t.count('tile')} × tile, "
                       f"{t.count('drive.google')} × Google Drive, {t.count('<img')} Bilder, eingebettete Daten: "
                       + (", ".join(k for k in ("__NEXT_DATA__", "__NUXT__", "window.__", "application/json", "mapData", "markers\"", "\"lat\"")
                                    if k in t) or "keine"))
    for name, url in (("IGN, Let’s Go Kanto", "https://www.ign.com/maps/pokemon-lets-go-pikachu-eevee/kanto"),
                      ("IGN, Schwert/Schild Galar", "https://www.ign.com/maps/pokemon-sword-shield/galar"),
                      ("IGN, Feuerrot/Blattgrün", "https://www.ign.com/maps/pokemon-firered-leafgreen-version"),
                      ("MewMaps, Let’s Go", "https://www.mewmaps.org/lets-go-pikachu-eevee"),
                      ("RankedBoost, Let’s Go", "https://rankedboost.com/pokemon/location/letsgo-pikachu-eevee/"),
                      ("RankedBoost, HG/SS Route 45", "https://rankedboost.com/pokemon/location/heartgold-soulsilver/route-45/"),
                      ("RankedBoost, Rubin/Saphir", "https://rankedboost.com/pokemon/location/ruby-sapphire/"),
                      ("Poké Atlas, Naturzone", "https://pokeatlas.com/maps/wild-area/"),
                      ("FrontierNav, Sonne/Mond", "https://frontiernav.net/wiki/pokemon-sun-moon/visualisations/maps"),
                      ("SimplyBLG, Johto", "https://simplyblgdev.github.io/Pokemon/Johto"),
                      ("HGSS Ironmon Map", "https://kelseyyoung.github.io/HGSSIronmonMap/"),
                      ("PokéMaps, Hoenn RSE", "https://pokemaps.net/maps/rse/hoenn"),
                      ("PokéTools, Smaragd", "https://www.poketools.com/emerald/map"),
                      ("PKMNMap, Smaragd", "https://pkmnmap.com/Maps/Emerald/"),
                      ("DittoBase, Kristall", "https://www.dittobase.com/crystal/map"),
                      ("PokémonRNG, Sinnoh", "https://www.pokemonrng.com/sinnoh-map/")):
        probe(name, url, looks, keep=200_000, headers=html)
    probe("Bulbapedia-Archiv, Kategorie Let’s-Go-Karten", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "categorymembers", "cmtitle": "Category:Let's Go, Pikachu! and Let's Go, Eevee! maps",
         "cmlimit": "50", "format": "json"}),
        lambda t: (lambda ms: f"{len(ms)} Bilder: " + ", ".join(m["title"] for m in ms[:10]))(
            (json.loads(t).get("query") or {}).get("categorymembers") or []), keep=True)
    # GitHub-Projekte mit Kartendaten (Trainer, Items, Begegnungen)
    for repo, words in (("kelseyyoung/HGSSIronmonMap", ("json", "map", "trainer")),
                        ("kelseyyoung/EmeraldIronmonMap", ("json", "map", "trainer")),
                        ("kelseyyoung/FRLGIronmonMap", ("json", "map", "trainer")),
                        ("simplyblgdev/simplyblgdev.github.io", ("johto", "json", "map")),
                        ("tristan-paul/Emerald_Encounters", ("db", "sql", "csv", "json"))):
        probe(f"GitHub: {repo}", f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1", tree_hits(*words), keep=True)
    # pokemoncompletion (GPL-3.0): Spieldaten mit Kartenpunkten liegen als JSON im Repository, die Karten als ganzes Bild
    # und als Kacheln ({z}_{x}_{y}.png) auf einem CDN; Gelb, Kristall, Smaragd und Platin haben eine Karte
    def pc_info(text):
        d = json.loads(text)
        im = d.get("interactiveMap") or {}
        n = sum(1 for c in d.get("categories") or [] for x in c.get("list") or [] if x.get("pos"))
        return (f"Karte {im.get('dim')}, Bild {im.get('fullImgUrl', '–')} ({im.get('fullImgSize', '?')}), "
                f"{len(d.get('locations') or [])} Orte, {n} Punkte in {len(d.get('categories') or [])} Kategorien")
    for g in ("Yellow", "Crystal", "Emerald", "Platinum"):
        probe(f"GitHub: pokemoncompletion, Daten {g}", f"https://raw.githubusercontent.com/RainingChain/pokemoncompletion/main/src/pokemonCompletion/data/{g}.json",
              pc_info)
        probe(f"pokemoncompletion, Kachel {g}", f"https://pokemonmap.b-cdn.net/{g.lower()}/1_0_0.png?v=1",
              lambda b: f"{len(b)} Bytes, " + ("PNG" if b[:4] == b"\x89PNG" else "kein Bild"), raw=True)
    probe("GitHub: Insektaure/pkTeraRaid (Raid-Nester SwSh mit Lage)", "https://api.github.com/repos/Insektaure/pkTeraRaid/git/trees/HEAD?recursive=1",
          tree_hits("den", "map", "swsh", "location"), keep=True)

    section("Kartenquellen im Detail: IGN, RankedBoost, DittoBase, PokéTools")
    # IGN (Next.js): Karte, Kacheln und ein Teil der Punkte stehen in __NEXT_DATA__, der Rest kommt per GraphQL
    # (mollusk.apis.ign.com). Die Abfrage steht im Code der Seite; deshalb die Skripte nach Abfragen mit „marker“ durchsuchen
    def ign_info(t):
        mk = re.findall(r'"__typename":"MapMarker"', t)
        ty = sorted(set(re.findall(r'"typeSlug":"([^"]+)","typeName"', t)))
        ts = re.findall(r'wikimaps/[^"]+\{z\}[^"]*', t)
        zz = re.findall(r'"(minZoom|maxZoom|width|height)":([\d.]+),', t)[:4]
        return f"{len(mk)} Punkte in der Seite, Arten: {', '.join(ty)}; Kacheln {ts[:1]}, {zz}"
    ign_js = set()
    for name, url in (("IGN, Galar (ganz)", "https://www.ign.com/maps/pokemon-sword-shield/galar"),
                      ("IGN, Let’s Go Kanto (ganz)", "https://www.ign.com/maps/pokemon-lets-go-pikachu-eevee/kanto")):
        try:
            r = probe(name, url, ign_info, keep=600_000, headers=html).result(timeout=DIAG_HANG)
        except cf.TimeoutError:
            r = None
        if r:
            ign_js.update(u for u in re.findall(r'<script src="(https://kraken\.ignimgs\.com/_next/static/chunks/[^"]+\.js)"', r["text"])
                          if "polyfills" not in u and "framework" not in u)

    def gql_info(t):
        ops = sorted(set(re.findall(r"(?:query|fragment)\s+(\w+)", t)))
        hits = [t[max(0, m.start() - 80):m.start() + 700] for m in re.finditer(r"(?:query|fragment)\s+\w*[Mm]arker\w*", t)][:4]
        return f"{len(ops)} Abfragen: {', '.join(ops[:30])}" + (" | " + " || ".join(" ".join(h.split()) for h in hits) if hits else "")
    for u in sorted(ign_js)[:25]:
        probe(f"IGN, Skript {u.rsplit('/', 1)[-1]}", u, gql_info)
    for slug in ("pokemon-lets-go-pikachu-eevee/kanto-hi-res", "pokemon-sword-shield/locations"):
        probe(f"IGN, Kachel {slug} 2/0-0", f"https://oyster.ignimgs.com/ignmedia/wikimaps/{slug}/2/0-0.jpg",
              lambda b: f"{len(b)} Bytes, " + ("JPEG" if b[:3] == b"\xff\xd8\xff" else "kein Bild"), raw=True)
    # die übrigen Kartenseiten ganz (die erste Probe war bei 200 000 Zeichen abgeschnitten)
    for name, url in (("RankedBoost, Let’s Go (ganz)", "https://rankedboost.com/pokemon/location/letsgo-pikachu-eevee/"),
                      ("RankedBoost, HG/SS (ganz)", "https://rankedboost.com/pokemon/location/heartgold-soulsilver/"),
                      ("DittoBase, Kristall (ganz)", "https://www.dittobase.com/crystal/map"),
                      ("PokéTools, Smaragd (ganz)", "https://www.poketools.com/emerald/map")):
        probe(name, url, lambda t: looks(t) + "; Muster: " + ", ".join(tile_patterns(t)[:5])
              + "; JSON-Adressen: " + ", ".join(sorted(set(re.findall(r'https?://[^"\' ]+\.json', t)))[:8]),
              keep=1_600_000, headers=html)

    section("Kartendaten im Detail (0.38): IGN-Abfrage, DittoBase, RankedBoost, PokéTools")
    # IGN: dieselbe GraphQL-Abfrage wie der Abgleich (alle Punkte einer Karte)
    for spiel, (slug, karten) in ign.GAMES.items():
        q = {"operationName": "MapMarkersMultiple", "query": ign.QUERY, "variables": {"objectSlug": slug, "mapSlug": karten[0],
             "typeSlugs": ["location", "pokemon", "item", "technical-machine", "trainer", "master-trainer", "gym", "pikachu",
                           "legendary-pokemon", "mega-stone", "den", "max-raid-den", "berry-tree", "fossil"]}}

        def gq(t):
            xs = ign.markers(t)
            from collections import Counter
            c = Counter(x.get("typeSlug") for x in xs)
            err = (json.loads(t).get("errors") or [{}])[0].get("message", "") if not xs else ""
            return f"{len(xs)} Punkte: " + ", ".join(f"{k} {n}" for k, n in c.most_common()) + (f"; Fehler: {err[:200]}" if err else "")
        probe(f"IGN, Abfrage aller Punkte {slug}/{karten[0]}", ign.GRAPH, gq, data=q)

    # DittoBase: welche Spiele haben eine Karte mit Spieldaten (wie Kristall), und wie sehen die Kachelsätze aus
    def db_info(t):
        d = dittobase.extract(t)
        if not d:
            return looks(t) + "; keine Kartendaten"
        m, draw = dittobase.parse(d, "x")
        ks = sorted({x.get("kind") for v in (d.get("data") or {}).get("markers", {}).values() for x in v})
        return (f"Oberwelt {d['data'].get('overworld')}, {len(d['data'].get('maps') or {})} Karten, {len((m or {}).get('orte') or [])} Punkte, "
                f"Arten {', '.join(map(str, ks))}, {len((draw or {}).get('saetze') or {})} Kachelsätze, Schlüssel {sorted(d)}")
    for g in ("red-blue", "yellow", "gold-silver", "ruby-sapphire", "emerald", "firered-and-leafgreen", "diamond-pearl",
              "platinum", "heartgold-soulsilver"):
        probe(f"DittoBase, Karte {g}", dittobase.page_url(g), db_info, headers=html)

    def png_info(b):
        import struct
        w, h, depth, ct, _, _, il = struct.unpack(">IIBBBBB", b[16:29])
        return f"PNG {w}×{h}, Farbtyp {ct}, {depth} Bit, Zeilensprung {il}"
    probe("DittoBase, Kachelsatz Johto (New Bark)", "https://assets.dittobase.com/game-maps/crystal-maps/pixi/tilesets/johto_89abcdef_g8_new_bark.png",
          png_info, raw=True)
    probe("DittoBase, Kachelsatz Höhle", "https://assets.dittobase.com/game-maps/crystal-maps/pixi/tilesets/cave_89abcdef.png", png_info, raw=True)

    # RankedBoost: die Daten der großen Karte (data-mega-src) und der Code, der sie liest
    def rb_json(t):
        d = json.loads(t)
        top = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in (d.items() if isinstance(d, dict) else [])}
        return f"Schlüssel {json.dumps(top)[:600]}"
    probe("RankedBoost, Daten der Let’s-Go-Karte",
          "https://img.rankedboost.com/wp-content/plugins/k-Pokemon/assets/cache/megamap-lets-go-pikachu-eevee-791ae0729e4a.json",
          rb_json, keep=1_500_000)
    probe("RankedBoost, Kartencode (mega-map-loader)", "https://img.rankedboost.com/wp-content/plugins/template-framework/assets/js/rb-mega-map-loader.js",
          lambda t: "Muster: " + ", ".join(tile_patterns(t)[:5]) + f"; {t.count('tile')}× tile", keep=400_000)
    for g in ("heartgold-soulsilver", "firered-leafgreen", "sword-shield", "brilliant-diamond-shining-pearl", "scarlet-violet"):
        probe(f"RankedBoost, Karte {g}", f"https://rankedboost.com/pokemon/location/{g}/",
              lambda t: "große Karte: " + (", ".join(sorted(set(re.findall(r'data-mega-src="([^"]+)"', t)))[:3]) or "keine"), headers=html)

    # PokéTools: die Kacheln stehen im Code der Kartenseite (Next.js-Skripte); in den Skripten die Stellen mit „tile“ zeigen
    chunk_re = re.compile(r'/_next/static/chunks/[^"\\]+[.]js')

    def tile_spots(t):
        spots = [" ".join(t[max(0, m.start() - 120):m.start() + 160].split()) for m in re.finditer(r"tiles?[/`'\"]", t)][:3]
        return f"Muster: {', '.join(tile_patterns(t)[:5]) or '–'}" + ("; Stellen: " + " || ".join(spots) if spots else "")
    try:
        r = probe("PokéTools, Kartenseite Smaragd (Skripte)", "https://www.poketools.com/emerald/map",
                  lambda t: f"{len(set(chunk_re.findall(t)))} Skripte", headers=html).result(timeout=DIAG_HANG)
    except cf.TimeoutError:
        r = None
    for u in sorted(set(chunk_re.findall(r["text"])))[:30] if r else ():
        probe(f"PokéTools, Skript {u.rsplit('/', 1)[-1]}", "https://www.poketools.com" + u, tile_spots)
    for g in ("firered", "ruby", "crystal", "platinum", "heartgold"):
        probe(f"PokéTools, Karte {g}", f"https://www.poketools.com/{g}/map",
              lambda t: f"{t.count('kind')}× kind, Titel {(re.findall(r'<title>(.*?)</title>', t) or ['–'])[0][:80]}", headers=html)

    section("Kartenquellen aus der Recherche vom 12.11. (Gamer Guides, Pokédens)")

    def geojson(text):
        d = json.loads(text)
        fs = d.get("features") or []
        kinds = sorted({str((f.get("properties") or {}).get("category") or (f.get("properties") or {}).get("type") or "?") for f in fs})[:12]
        geo = sorted({(f.get("geometry") or {}).get("type", "?") for f in fs})
        return f"{len(fs)} Punkte ({', '.join(geo)}), Arten: {', '.join(kinds)}; Schlüssel: {', '.join(list((fs[0].get('properties') or {}))[:12]) if fs else '–'}"
    # Gamer Guides: Kartendaten als GeoJSON; die Kartenseiten nennen Bild bzw. Kacheln (Muster und Größe stehen im HTML)
    for n, name in ((49, "BDSP Untergrund"), (238, "Indigoblaue Scheibe")):
        probe(f"Gamer Guides, Punkte {name}", f"https://www.gamerguides.com/map/{n}/geojson", geojson, keep=True)
    for path, name in (("pokemon-brilliant-diamond-and-shining-pearl/maps/grand-underground", "BDSP Untergrund"),
                       ("pokemon-scarlet-and-violet/maps/the-indigo-disk", "Indigoblaue Scheibe")):
        probe(f"Gamer Guides, Kartenseite {name}", f"https://www.gamerguides.com/{path}",
              lambda t: f"Muster: {', '.join(tile_patterns(t)[:5]) or '–'}; {t.count('max_zoom')}× max_zoom", keep=True, headers=html)
    # Spiele ohne Karte (X/Y, Sonne/Mond, USUM): Regionskarten mit Bildkarte im PokéWiki (deutsche Ortsnamen),
    # Kartenbilder bei Bulbapedia und Pokémon Database; die Antworten bleiben für die Auswertung (keep)
    area_rx = re.compile(r"(?m)^\s*(?:rect|poly|circle)\s")
    file_rx = re.compile(r"[\w .-]+-Map [\w .äöüÆæ-]+[.](?:png|gif)")

    def imagemap(text):
        out = []
        for k, v in pokewiki.pages(text).items():
            files = ", ".join(sorted(set(file_rx.findall(v)))[:6]) or "–"
            out.append(f"{k}: {len(area_rx.findall(v))} Flächen, Bilder {files}")
        return "; ".join(out) or "keine Seiten"
    probe("PokéWiki, Bildkarten Kalos und Alola (Vorlagen)", pokewiki.batch_url(
        ["Vorlage:XY-Map Kalos", "Vorlage:SM-Map Alola", "Vorlage:USUM-Map Alola", "Vorlage:ORAS-Map Hoenn",
         "Vorlage:SW-Map Einall", "Vorlage:S2W2-Map Einall", "Vorlage:SDLP-Map Sinnoh"]), imagemap, keep=True)
    probe("Bulbapedia-Archiv, Kategorie Spielkarten", "https://archives.bulbagarden.net/w/api.php?action=query&list=categorymembers"
          "&cmtitle=Category:Game_maps&cmlimit=500&cmtype=file&format=json",
          lambda t: f"{len(json.loads(t)['query']['categorymembers'])} Dateien", keep=True)
    map_rx = re.compile(r'href="(/map/[^"]+)"')
    probe("Pokémon Database, Regionskarten", "https://pokemondb.net/map",
          lambda t: f"{t.count('<area')} Flächen, {len(set(map_rx.findall(t)))} Kartenseiten", keep=True, headers=html)
    probe("Pokédens, Raid-Nester Schwert/Schild (Inhalt je Nest)", "https://pokedens.github.io/data.json",
          lambda t: (lambda d: f"{type(d).__name__} mit {len(d)} Einträgen; Schlüssel: {', '.join(list(d)[:8]) if isinstance(d, dict) else ', '.join(list(d[0])[:8]) if d and isinstance(d[0], dict) else '–'}")(json.loads(t)), keep=True)

    section("Kartenbilder im Detail (seit 0.47): Größe der Bilder für X/Y, Sonne/Mond, USUM, ORAS, BDSP")

    def sizes(text):
        d = json.loads(text).get("query") or {}
        xs = [(i.get("name") or "", i.get("width"), i.get("height")) for i in d.get("allimages") or []]
        xs += [(p.get("title") or "", (p.get("imageinfo") or [{}])[0].get("width"), (p.get("imageinfo") or [{}])[0].get("height"))
               for p in (d.get("pages") or {}).values()] if isinstance(d.get("pages"), dict) else \
              [(p.get("title") or "", (p.get("imageinfo") or [{}])[0].get("width"), (p.get("imageinfo") or [{}])[0].get("height"))
               for p in d.get("pages") or []]
        return "; ".join(f"{n} {w}×{h}" if w else f"{n} fehlt" for n, w, h in xs[:40]) or "keine Bilder"
    # PokéWiki: alle Bilder mit diesen Anfängen (die Vorlagen nennen sie), mit Größe; Bulbapedia: einzelne Regionskarten
    for pre in ("XY-Map", "SM-Global-Map", "SM-Map", "USUM-Global-Map", "USUM-Map", "Map Hoenn", "ORAS-Map", "SDLP-Map", "Karte Kalos", "Karte Alola"):
        probe(f"PokéWiki, Bilder „{pre}…“ mit Größe", "https://www.pokewiki.de/api.php?action=query&list=allimages&aiprop=size|url"
              f"&ailimit=100&format=json&formatversion=2&aiprefix={urllib.parse.quote(pre)}", sizes, keep=True)
    for t in ("XY-Map Kalos", "USUM-Map Alola", "ORAS-Map Hoenn"):
        probe(f"PokéWiki, Vorlage {t} (ganz)", pokewiki.batch_url(["Vorlage:" + t]), imagemap, keep=300_000)
    bulba = ["Kalos XY.png", "Melemele Island Map.png", "Melemele Island Map 2.png", "Ula'ula Island Map.png", "Ula'ula Island Map 2.png",
             "Poni Island Map.png", "Poni Island Map 2.png", "Sinnoh BDSP.png", "UGMAP.png", "Galar Sh.png", "Galar Sh DLC.png",
             "Hoenn Soaring ORAS Map.png", "Sinnoh DP.png", "Sinnoh.png", "Hisui.png", "Paldea.png", "Kitakami.png", "Blueberry Academy.png"]
    # Recherche 12.11. (Kalos und Alola): große Fan-Karten als PNG, MewMaps (Insel- und Gebietskarten), japanische Übersicht
    def png_info(text):
        b = text.encode("latin-1", "replace") if isinstance(text, str) else text
        wh = raidnester.png_size(b)
        return f"PNG {wh[0]} × {wh[1]} px, {len(b)} Bytes" if wh else f"kein PNG ({len(b)} Bytes, Anfang {b[:12]!r})"
    for u, name in (("http://www.40k.zombiecrisis.org/map.png", "Kalos"), ("http://40k.zombiecrisis.org/map-alola.png", "Alola")):
        probe(f"Fan-Karte {name} (PNG)", u, png_info, raw=True)
    img_rx = re.compile(r'(?:src|href)="([^"]+?\.(?:jpe?g|png|webp))"', re.I)
    for path, name in (("sun-moon", "Sonne/Mond"), ("ultra-sun-ultra-moon", "Ultrasonne/Ultramond")):
        probe(f"MewMaps, {name}", f"https://www.mewmaps.org/{path}",
              lambda t: f"{len(set(img_rx.findall(t)))} Bilder: {', '.join(sorted(set(img_rx.findall(t)))[:12])}", keep=True, headers=html)
    # 0.48.1: MewMaps verlinkt die Karten nur (Google Drive): Größe der Inselkarten; FrontierNav lädt alles per Skript:
    # die Skripte nach Adressen von Daten durchsuchen (Marker mit Koordinaten?)
    def img_info(text):
        b = text.encode("latin-1", "replace") if isinstance(text, str) else text
        wh = raidnester.png_size(b)
        if wh:
            return f"PNG {wh[0]} × {wh[1]} px, {len(b)} Bytes"
        i = 2
        while b[:2] == b"\xff\xd8" and i + 9 < len(b) and b[i] == 0xFF:
            if b[i + 1] in (0xC0, 0xC1, 0xC2):
                return f"JPEG {int.from_bytes(b[i + 7:i + 9], 'big')} × {int.from_bytes(b[i + 5:i + 7], 'big')} px, {len(b)} Bytes"
            i += 2 + int.from_bytes(b[i + 2:i + 4], "big")
        return f"kein Bild ({len(b)} Bytes, Anfang {b[:40]!r})"
    for fid, name in (("1SBdYdLXsasmpgfDZAqOVVw2ap3L6TbDi", "SM Akala"), ("1nViijDWmSY6xQCsqlxaLeOrUjY6xi5TK", "SM Ula'ula"),
                      ("1b4-8C-A123vAd-2iq0JiRcDGk-lb3D09", "SM Poni"), ("1GALSC0RLFUE5na21LVNWHqOMwASflw_m", "USUM Mele-Mele"),
                      ("1oAFE9RUbkkZzHlO4UQ6fLjpQbvzlmxC2", "USUM Akala/Übersicht"), ("1lQxMilRC8NfT7m6twLWebCQs_PvFvEeH", "USUM Ula'ula"),
                      ("1DsTHOuQyBA9X3QquPsoTvhgnTKPf61tr", "USUM Poni")):
        probe(f"MewMaps, Inselkarte {name} (Google Drive)", f"https://drive.google.com/uc?export=download&id={fid}", img_info, raw=True)
    api_rx = re.compile(r"""["'`]((?:https?:)?/[\w./-]*(?:api|graphql|tiles?|entit|marker|\.json)[\w./{}?=&-]*)["'`]""", re.I)
    probe("FrontierNav, Alola-Karte (Seite)", "https://frontiernav.net/wiki/pokemon-sun-moon/visualisations/maps?m=alola-map",
          lambda t: "Skripte: " + ", ".join(re.findall(r'src="(/static/[^"]+)"', t)), keep=True, headers=html)
    for js in ("8a5a94fd-a.js", "27648ee4-a.js", "46bc1287-a.js"):
        probe(f"FrontierNav, Skript {js}", f"https://frontiernav.net/static/{js}",
              lambda t: f"{len(t)} Zeichen; Adressen: " + ", ".join(sorted(set(api_rx.findall(t)))[:30]), keep=200_000)
    probe("Japanische X/Y-Kartenübersicht", "https://xn--rckteqa2e6038anjua.com/xy/pokemon_xy_map.html",
          lambda t: f"{t.count('<area')} Flächen, {len(set(img_rx.findall(t)))} Bilder: {', '.join(sorted(set(img_rx.findall(t)))[:8])}", keep=True, headers=html)
    probe("Bulbapedia-Archiv, Regionskarten mit Größe", "https://archives.bulbagarden.net/w/api.php?action=query&prop=imageinfo"
          "&iiprop=size|url&format=json&titles=" + urllib.parse.quote("|".join("File:" + b for b in bulba)), sizes, keep=True)

    section("Alola und die Quellen der Liste vom 12.11. (anderssprachige Wikis, pokemon.com)")
    # 0.52: PokéWiki hat je Ort ein Inselbild mit hervorgehobenem Ort (94 Bilder, 270 px): Vergleich mit dem leeren
    # Inselbild ergibt die Lage. Dazu die größeren Inselkarten von Bulbapedia, um zu sehen, ob beide zusammenpassen
    pw_img = "https://www.pokewiki.de/images/"
    for path, name in (("f/fe/USUM-Map_Mele-Mele.png", "Mele-Mele leer"), ("3/39/USUM-Map_Mele-Mele_Lili%E2%80%99i.png", "Mele-Mele Lili’i"),
                       ("1/19/USUM-Map_Mele-Mele_Route_1_%28Alola%29.png", "Mele-Mele Route 1"), ("0/0a/USUM-Map_Ula-Ula.png", "Ula-Ula leer"),
                       ("6/66/USUM-Map_Ula-Ula_Route_10_%28Alola%29.png", "Ula-Ula Route 10"), ("9/98/USUM-Map_Akala.png", "Akala leer"),
                       ("e/e1/USUM-Map_Poni.png", "Poni leer"), ("1/14/USUM-Global-Map_Mele-Mele.png", "Übersicht Mele-Mele")):
        probe(f"PokéWiki, Inselbild {name}", pw_img + path, img_info, raw=True, keep=True)
    for f in ("Melemele Island Map 2.png", "Ula'ula Island Map 2.png", "Poni Island Map 2.png"):
        probe(f"Bulbapedia-Archiv, Bild {f}", "https://archives.bulbagarden.net/wiki/Special:FilePath/" + urllib.parse.quote(f),
              img_info, raw=True, keep=True)
    probe("Bulbapedia-Archiv, Suche Akala Island Map", "https://archives.bulbagarden.net/w/api.php?action=query&list=allimages"
          "&aiprefix=Akala&aiprop=size|url&ailimit=50&format=json&formatversion=2", sizes, keep=True)
    # die anderssprachigen Wikis (alle MediaWiki): Seite der Region und einer Insel als Wikitext, Bildkarten (imagemap)?
    def wiki_maps(text):
        j = json.loads(text)
        if "parse" not in j:
            return f"Seite gibt es nicht ({(j.get('error') or {}).get('code', '?')})"
        p = j["parse"]
        wt = p["wikitext"]["*"] if isinstance(p["wikitext"], dict) else p["wikitext"]
        files = sorted(set(re.findall(r"(?:File|Datei|Fichier|Archivo|Immagine|文件|ファイル|Image):([^|\]\n]+\.(?:png|jpe?g|gif))", wt, re.I)))
        return (f"Seite „{p['title']}“, {len(wt)} Zeichen, {wt.count('<imagemap')} Bildkarten, {wt.count('rect ') + wt.count('poly ')} Flächen; "
                f"Bilder: {', '.join(files[:12])}")
    wikis = (("Poképédia (FR)", "https://www.pokepedia.fr/api.php", ("Alola", "Île de Mele-Mele")),
             ("WikiDex (ES)", "https://www.wikidex.net/api.php", ("Alola", "Isla Melemele")),
             ("Pokémon Central (IT)", "https://wiki.pokemoncentral.it/api.php", ("Alola", "Mele Mele")),
             ("52poke (CN)", "https://wiki.52poke.com/api.php", ("阿罗拉地区", "美乐美乐岛")),
             ("ポケモンWiki (JA)", "https://wiki.xn--rckteqa2e.com/w/api.php", ("アローラ地方", "メレメレ島")))
    for wname, api, pages in wikis:
        probe(f"{wname}, API", api + "?action=query&meta=siteinfo&format=json", wiki_info)
        for page in pages:
            probe(f"{wname}, Seite {page}", api + "?action=parse&page=" + urllib.parse.quote(page) + "&prop=wikitext&format=json&redirects=1",
                  wiki_maps, keep=300_000)
    probe("pokemon.com, Pokédex-Daten", "https://www.pokemon.com/us/api/pokedex/kalos",
          lambda t: f"{len(json.loads(t))} Einträge, Felder: {', '.join(sorted(json.loads(t)[0])) if json.loads(t) else '-'}", keep=60_000)
    probe("pokemon.com, Pokédex-Seite Bisasam (DE)", "https://www.pokemon.com/de/pokedex/bisasam",
          lambda t: f"{len(t)} Zeichen, Titel: {(re.search(r'<title>([^<]*)', t) or [None, '?'])[1].strip()}", keep=150_000, headers=html)

    section("Kampfdaten (Movesets, Nutzung)")
    probe("pkmn, Smogon-Sets Gen 9", "https://data.pkmn.cc/sets/gen9.json",
          lambda t: f"{len(json.loads(t))} Pokémon mit Sets")
    probe("Smogon, Nutzungsstatistik", "https://www.smogon.com/stats/", lambda t: f"{t.count('href=')} Einträge, neuester Monat {(smogon.months(t) or ['–'])[0]}")
    probe("Showdown, learnsets.ts", SD_RAW + "learnsets.ts", lambda t: f"{t.count('learnset:')} Lernlisten (TM, Lehrer, Ei je Generation)")
    probe("Showdown, formats-data.ts", SD_RAW + "formats-data.ts", lambda t: f"{t.count('tier:')} Pokémon mit Stufe (OU, UU …)")
    probe("Showdown, Random-Battle-Sets Gen 9", SD_RAW + "random-battles/gen9/sets.json",
          lambda t: f"{len(json.loads(t))} Pokémon mit Rollen und Attacken")
    probe("Showdown, abilities.ts", SD_RAW + "abilities.ts", lambda t: f"{t.count('num:')} Fähigkeiten mit Wirkung im Code")
    # Wächter: rührt sich DIAG_HANG Sekunden lang nichts, gelten die offenen Abfragen als hängend; der Test endet trotzdem
    seen, last = -1, time.monotonic()
    while True:
        done, todo = cf.wait(futs, timeout=min(5, DIAG_HANG))
        if not todo:
            break
        if stand["fertig"] != seen:
            seen, last = stand["fertig"], time.monotonic()
        elif time.monotonic() - last > DIAG_HANG:
            with lock:
                hung = list(stand["laeuft"])
            for k, x in enumerate(lines):
                if x and x.endswith(": keine Antwort") and x[:-len(": keine Antwort")] in hung:
                    lines[k] = x + f" (hängt nach {DIAG_HANG} s ohne Fortschritt, abgebrochen)"
            lines.append("")
            lines.append(f"Abgebrochen: {len(todo)} Abfragen kamen nicht mehr dran oder hingen ({', '.join(hung)}).")
            break
    for p in pools.values():
        p.shutdown(wait=False, cancel_futures=True)
    if proben:
        lines.append("")
        lines.append(f"{len(proben)} Probe-Seiten zum Herunterladen (Knopf „Proben herunterladen“).")
    return lines
