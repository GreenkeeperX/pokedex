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
import hashlib
import json
import os
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from . import db, importer, sources, store

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
NAMES = {"pokeapi": "PokéAPI", "showdown": "Showdown", "sprites": "Sprites"}

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


def _sprites(log, limit=SPRITES_MAX):
    """Fehlende Bilder nach data/sprites/<id>.png. Gibt das Ergebnis der Quelle zurück."""
    src = _Source("sprites", log, pause=0.2)
    folder = os.path.join(db.data_dir(), "sprites")
    os.makedirs(folder, exist_ok=True)
    con = db.game()
    try:
        ids = [r[0] for r in con.execute("SELECT id FROM form ORDER BY id")]
    finally:
        con.close()
    miss = store.load_json("sprites_fehlen.json", {})
    cutoff = _iso(now() - timedelta(days=SPRITE_MISS_DAYS))
    have = set(os.listdir(folder))
    todo = [i for i in ids if f"{i}.png" not in have and (miss.get(str(i)) or "") < cutoff]
    got = absent = 0
    for n, i in enumerate(todo[:limit]):
        STATE.update(step="Sprites", done=n, total=min(len(todo), limit))
        body = src.get(f"{SPRITE_RAW}{i}.png", raw=True, absent=(404,))
        if body is None:
            if src.stopped:
                break
            continue
        if not body:
            miss[str(i)] = _iso(now())
            absent += 1
            continue
        if body[:8] != b"\x89PNG\r\n\x1a\n":
            continue
        tmp = os.path.join(folder, f".{i}.tmp")
        with open(tmp, "wb") as f:
            f.write(body)
        os.replace(tmp, os.path.join(folder, f"{i}.png"))
        got += 1
    store.save_json("sprites_fehlen.json", miss)
    left = max(0, len(todo) - limit)
    if todo:
        log(f"Sprites: {got} neu" + (f", {absent} gibt es nicht" if absent else "") + (f", {left} im nächsten Lauf" if left else ""))
    return src.result(neu=got, fehlen=absent, offen=left)


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
            st["sources"]["sprites"] = res
            if res["blocked"]:
                st["rest"]["sprites"] = _iso(now() + timedelta(hours=REST_H))
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
    sd_texts = {}
    if not _resting(st, "showdown", at):
        for k in ("pokedex", "moves"):
            STATE["step"] = f"Showdown: {k}.ts"
            t = sd.get(f"{SD_RAW}{k}.ts")
            if t:
                sd_texts[k] = t
        st["sources"]["showdown"] = sd.result(dateien=len(sd_texts))
        if sd.blocked:
            st["rest"]["showdown"] = _iso(now() + timedelta(hours=REST_H))
    extra = importer.load_extra(EXTRA_DIR)
    stand = {"csv": sha, "showdown": _hash(*(sd_texts.get(k, "") for k in ("pokedex", "moves"))) if len(sd_texts) == 2 else "",
             "extra": _hash(json.dumps(extra, sort_keys=True)), "importer": importer.VERSION}
    old = st.get("stand") or {}
    if (db.has_data() and not force and sha and stand["csv"] == old.get("csv") and stand["extra"] == old.get("extra")
            and stand["importer"] == old.get("importer") and (not stand["showdown"] or stand["showdown"] == old.get("showdown"))):
        log("Keine Änderung bei PokéAPI, Showdown und Ergänzungen, Datenbank bleibt")
        st["sources"]["pokeapi"] = papi.result(geaendert=False)
        return True
    csvs = {}
    for i, n in enumerate(names):
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
    if missing:
        log("PokéAPI: es fehlen " + ", ".join(missing) + "; die bisherige Datenbank bleibt")
        return False
    STATE.update(step="Datenbank bauen", done=0, total=0)
    tmp = db.pokeapi_path() + ".neu"
    try:
        stats = importer.build(tmp, csvs, sd_texts, extra)
    except Exception as e:
        log(f"Neue Datenbank verworfen: {e}; die bisherige bleibt")
        if os.path.exists(tmp):
            os.remove(tmp)
        return False
    os.replace(tmp, db.pokeapi_path())
    if len(sd_texts) < 2:
        stand["showdown"] = old.get("showdown", "")
    st["stand"], st["stats"], st["built"] = stand, stats, _iso(now())
    log(f"Datenbank neu: {stats['species']} Arten, {stats['forms']} Formen, {stats['moves']} Attacken, {stats['games']} Spiele, "
        f"{stats['tables']} Tabellen" + (f"; Showdown {stats['sd_pokemon']} Pokémon, {stats['sd_moves']} Attacken, "
                                         f"{stats['diff']} Abweichungen zu prüfen" if sd_texts else "; ohne Showdown-Abgleich"))
    return not papi.stopped and not sd.stopped


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


def diagnose():
    """Verbindung testen: jede Quelle einmal abfragen und beschreiben, was zurückkommt. Speichert nichts."""
    lines = [f"Pokédex {sources.VERSION}, Test vom {now().strftime('%d.%m.%Y %H:%M')} UTC"]

    def probe(name, url, info, raw=False):
        r = sources.request(url, raw=raw)
        if r["error"]:
            lines.append(f"{name}: keine Verbindung ({r['error']})")
            return None
        size = len(r.get("body", b"")) if raw else len(r["text"])
        head = f"{name}: HTTP {r['status']}, Server {r['server'] or '?'}, {size} {'Bytes' if raw else 'Zeichen'}"
        if r["status"] >= 400 or (not raw and sources.challenge(r["text"])):
            lines.append(head + (", gesperrt" if r["status"] in sources.BLOCKED else "") +
                         ("" if raw else f". Anfang: {' '.join(r['text'][:160].split())}"))
            return None
        try:
            lines.append(f"{head}, {info(r.get('body') if raw else r['text'])}")
        except Exception as e:
            lines.append(f"{head}, nicht auswertbar ({type(e).__name__}: {e})")
        sleep(PAUSE)
        return r

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

    def wiki_info(text):
        g = json.loads(text)["query"]["general"]
        return f"{g.get('sitename')} auf MediaWiki {g.get('generator', '?').split()[-1]}"
    probe("PokéWiki, API", POKEWIKI_API + "?action=query&meta=siteinfo&format=json", wiki_info)

    def wiki_page(text):
        p = json.loads(text)["parse"]
        wt = p["wikitext"]["*"] if isinstance(p["wikitext"], dict) else p["wikitext"]
        return f"Seite „{p['title']}“, {len(wt)} Zeichen Wikitext, {wt.count('{{')} Vorlagen"
    probe("PokéWiki, Seite Legenden: Arceus", POKEWIKI_API + "?action=parse&page=" + urllib.parse.quote("Pokémon-Legenden: Arceus")
          + "&prop=wikitext&format=json&redirects=1", wiki_page)
    return lines
