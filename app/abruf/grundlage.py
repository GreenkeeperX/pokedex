"""Grundlage: Pausen und Ruhezeiten je Server und Quelle, Stand des Laufs (STATE), Einstellungen, Zeitplan, Zugriff auf
eine Quelle (_Source), Liste der CSV-Dateien, Adressen der Quellen.

Teil des Pakets app.abruf; alle Namen sind auch dort erreichbar.
"""
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from .. import db, fehler, importer, sources, store


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
EXTRA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "extra")

SETTINGS = {"auto": True, "tage": 7, "sprites": True, "uhr": "02:30"}    # uhr: feste Uhrzeit des Abgleichs (UTC)
UHR = re.compile(r"([01]\d|2[0-3]):([0-5]\d)")
RESUME_MAX = 2              # so oft wird ein vom Neustart unterbrochener Lauf gleich fortgesetzt, danach wie ein Fehlschlag
REST_FILE = "ruhe.json"     # Ruhezeiten je Quelle {Schlüssel: bis (ISO)}; sofort gespeichert, übersteht den Neustart
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


_rest_lock = threading.Lock()
_REST = {}


def _rests():
    """Ruhezeiten von der Platte, einmal je Start (und je Datenordner) gelesen. Nur unter _rest_lock aufrufen."""
    if _REST.get("dir") != store.DATA_DIR:
        got = store.load_json(REST_FILE, {})
        _REST.clear()
        _REST.update(dir=store.DATA_DIR, bis={k: v for k, v in got.items() if isinstance(v, str)})
    return _REST["bis"]


def rest_set(key, hours=REST_H, at=None):
    """Eine Quelle ruhen lassen und das sofort speichern: Die Ruhe gilt auch nach einem Neustart. Eine längere Ruhe
    bleibt; abgelaufene Einträge fallen weg. Gibt das Ende zurück (ISO)."""
    at = at or now()
    until = _iso(at + timedelta(hours=hours))
    with _rest_lock:
        bis = _rests()
        if bis.get(key, "") < until:
            bis[key] = until
        for k in [k for k, v in bis.items() if v <= _iso(at)]:
            del bis[k]
        try:
            store.save_json(REST_FILE, dict(bis))
        except OSError as e:
            print("Ruhezeiten speichern:", e, file=sys.stderr)
        return bis[key]


def server_rest(url):
    """Schlüssel der Ruhezeit eines Servers ("server:<Name>"). Der Abgleich lässt Quellen ruhen (eine Quelle, ein
    Schlüssel); dazu merkt er sich den Server, der gesperrt hat, damit der Verbindungstest ihn nicht gleich wieder fragt."""
    return "server:" + (urllib.parse.urlsplit(url).hostname or "")


def rest_until(key, at=None):
    """Bis wann die Quelle ruht (ISO) oder ""."""
    with _rest_lock:
        until = _rests().get(key, "")
    return until if until > _iso(at or now()) else ""


def rest_clear(key=None):
    """Ruhezeit einer Quelle (oder alle) aufheben und das speichern. Der Abgleich ruft das nie selbst auf: Eine Ruhe
    endet von allein. Gedacht für Tests und für einen bewussten Eingriff von Hand."""
    with _rest_lock:
        bis = _rests()
        if key is None:
            bis.clear()
        else:
            bis.pop(key, None)
        try:
            store.save_json(REST_FILE, dict(bis))
        except OSError as e:
            print("Ruhezeiten speichern:", e, file=sys.stderr)


def rests(at=None):
    """Alle laufenden Ruhezeiten {Schlüssel: bis}."""
    cur = _iso(at or now())
    with _rest_lock:
        return {k: v for k, v in _rests().items() if v > cur}


def load_settings():
    s = dict(SETTINGS)
    s.update({k: v for k, v in store.load_json("settings.json", {}).items() if k in SETTINGS})
    if not UHR.fullmatch(str(s["uhr"])):
        s["uhr"] = SETTINGS["uhr"]
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
    if "uhr" in body:
        if not UHR.fullmatch(str(body["uhr"])):
            raise ValueError("Uhrzeit: HH:MM von 00:00 bis 23:59")
        s["uhr"] = str(body["uhr"])
    store.save_json("settings.json", s)
    return s


def status():
    """Stand des Abgleichs mit Protokoll (Einstellungen). „unterbrochen“: Der letzte Lauf endete nicht (Neustart)."""
    st = store.load_json("sync.json", {})
    st["running"] = _running.locked()
    if st["running"]:
        st.update(started=STATE["started"], step=STATE["step"], done=STATE["done"], total=STATE["total"], log=list(STATE["log"]))
    st["unterbrochen"] = bool(st.pop("laeuft", False)) and not st["running"]
    st["rest"] = dict(st.get("rest") or {}, **rests())
    st["naechster"] = next_run()
    st["has_data"] = db.has_data()
    return st


def brief():
    """Der Stand in wenigen Feldern, für die regelmäßige Abfrage der Oberfläche (/api/stand): ohne Protokoll, ohne
    Quellen, ohne Versionsgeschichte."""
    st = store.load_json("sync.json", {})
    running = _running.locked()
    out = {k: st.get(k) for k in ("started", "finished", "ok", "built")}
    out.update(running=running, step=STATE["step"] if running else "", done=STATE["done"] if running else 0,
               total=STATE["total"] if running else 0, unterbrochen=bool(st.get("laeuft")) and not running)
    if running:
        out["started"] = STATE["started"]
    return out


def _termin(s, at):
    """Der letzte Termin des Zeitplans (feste Uhrzeit „uhr“, UTC), der nicht nach at liegt."""
    h, m = (int(x) for x in UHR.fullmatch(s["uhr"]).groups())
    t = at.astimezone(timezone.utc).replace(hour=h, minute=m, second=0, microsecond=0)
    return t if t <= at else t - timedelta(days=1)


def _start_of(last):
    try:
        return datetime.fromisoformat(last.get("started")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def next_run(settings=None, at=None):
    """Nächster Lauf nach Zeitplan (ISO, UTC) oder "", wenn der Zeitplan aus ist."""
    s = settings or load_settings()
    if not s["auto"]:
        return ""
    at = at or now()
    t = _termin(s, at) + timedelta(days=1)
    start = _start_of(store.load_json("sync.json", {}))
    if start is not None:
        first = t.replace(year=start.year, month=start.month, day=start.day) + timedelta(days=s["tage"])
        t = max(t, first)
    return _iso(t)


def due(settings=None, at=None, boot=False):
    """Lauf fällig? Ohne Datenbank immer; nach einem Fehlschlag frühestens nach einer Stunde; ein vom Neustart
    unterbrochener Lauf („laeuft“ steht noch im Stand) wird fortgesetzt, höchstens RESUME_MAX-mal nacheinander.
    Sonst nach Zeitplan: zur festen Uhrzeit, wenn der letzte Lauf mindestens „tage“ Kalendertage zurückliegt. Der
    Termin hängt damit nicht mehr an der Uhrzeit des letzten Laufs (bis 0.57.0: „tage“ × 24 Stunden nach dessen Beginn)."""
    if _running.locked():
        return False
    s = settings or load_settings()
    at = at or now()
    last = store.load_json("sync.json", {})
    since = _ago(last.get("started"), at)
    if last.get("laeuft") and (last.get("versuch") or 1) <= RESUME_MAX:
        return True
    if not db.has_data():
        return since is None or last.get("ok") is not False or since >= timedelta(hours=1)
    if not s["auto"]:
        return False
    if since is None:
        return True
    if last.get("ok") is False:
        return since >= timedelta(hours=1)
    # Nach einem Update mit neuen Tabellen sofort neu bauen, sonst fehlt Neues bis zum nächsten Termin
    if (last.get("stand") or {}).get("importer") not in (None, importer.VERSION) and since >= timedelta(hours=1):
        return True
    t, start = _termin(s, at), _start_of(last)
    return start < t and (t.date() - start.date()).days >= s["tage"]


class _Source:
    """Eine Quelle in einem Lauf: Pausen, Fehlerzähler, zweiter Versuch nach Netzfehler, Ende bei Sperre."""

    def __init__(self, key, log, pause=PAUSE, ruhe=None):
        self.key, self.name, self.log, self.pause = key, NAMES.get(key, key), log, pause
        self.ruhe = ruhe or key          # Schlüssel der Ruhezeit (weicht ab, wenn mehrere Abläufe eine Quelle teilen)
        self.n = self.errors = 0
        self.stopped = ""
        self.blocked = False
        self._last = {}

    def _stop(self, why, url):
        self.stopped, self.blocked = why, True
        fehler.notiere(self.key, urllib.parse.urlsplit(url).hostname or "", why, _short(url))
        rest_set(self.ruhe)              # sofort auf die Platte: gilt auch, wenn der Container gleich neu startet
        rest_set(server_rest(url))       # und je Server, für den Verbindungstest
        self.log(f"{self.name}: {why} bei {_short(url)}, Quelle ruht {REST_H} Stunden")

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
                    self._stop(f"gesperrt (HTTP {e.status})", url)
                else:
                    self.errors += 1
                    art = "HTTP " + str(e.status) if e.status else "keine Verbindung"
                    self.log(f"{self.name}: {art} bei {_short(url)}")
                    fehler.notiere(self.key, host, art, _short(url))
                    if self.errors >= MAX_ERRORS:
                        self.stopped = f"{self.errors} Fehler"
                        self.log(f"{self.name}: zu viele Fehler, für diesen Lauf beendet")
                return None
        why = sources.challenge(body[:4000].decode("utf-8", "replace") if raw else body)
        if why:
            self._stop(why, url)
            return None
        return body

    def result(self, **extra):
        return {"at": _iso(now()), "requests": self.n, "errors": self.errors, "ok": not self.stopped,
                "msg": self.stopped, "blocked": self.blocked, **extra}


def _short(url):
    p = urllib.parse.urlsplit(url)
    return p.hostname + (p.path if len(p.path) < 70 else "…" + p.path[-60:])


def _resting(st, key, at):
    """Ruht die Quelle? Ende der Ruhe (ISO) oder "". Gilt, was im Stand des Laufs oder in ruhe.json steht."""
    until = max(((st.get("rest") or {}).get(key)) or "", rest_until(key, at))
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
        except (ValueError, TypeError, KeyError) as ex:
            fehler.melden(ex, "Liste der CSV-Dateien", "pokeapi")
            names = []
    text = src.get(f"{GH_API}/commits?path=data/v2/csv&per_page=1", absent=(403, 404)) if names else ""
    if text:
        try:
            sha = json.loads(text)[0]["sha"]
        except (ValueError, TypeError, KeyError, IndexError) as ex:
            fehler.melden(ex, "Stand der CSV-Dateien", "pokeapi")
            sha = ""
    if not names:
        log(f"PokéAPI: Dateiliste von GitHub nicht lesbar, hole die {len(importer.NEEDED)} benötigten Dateien")
        names = list(importer.NEEDED)
    else:
        log(f"PokéAPI: {len(names)} Dateien" + (f", Stand {sha[:7]}" if sha else ""))
    return names, sha


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
