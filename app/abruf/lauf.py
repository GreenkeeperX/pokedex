"""Der Lauf: run, die Schritte je Quelle, Bau der Datenbank, Zwischenspeicher der CSV-Texte, Start und Zeitplan im
Hintergrund.

Teil des Pakets app.abruf; alle Namen sind auch dort erreichbar.
"""
import gzip
import json
import os
import sys
import threading
import time
from datetime import timedelta

from .. import db, fehler, importer, smogon, sources, store

from .grundlage import (BOOT_WAIT_S, CSV_RAW, EXTRA_DIR, LOG_LINES, NAMES, REST_H, SD_RAW, STATE, _Source, _hash, _iso,
    _parallel, _resting, _running, csv_list, due, load_settings, now, rests)
from .medien import EXTRAS, _images, _sprites, _tiles
from .quellen import _altissimo, _companion, _pkhex, _spawns
from .wiki import _pokewiki
from .seiten import _bisafans, _serebii, _shiny, _trainer
from .karten import (_dittobase, _ign, _ironmon, _mapgenie, _pkcompletion, _pokearth, _raidnester, _rankedboost,
    start_stock)


def run(by_hand=False, force=False):
    """Ein Abgleich. force: auch ohne Änderung neu bauen."""
    if not _running.acquire(blocking=False):
        return False
    try:
        return _run(by_hand, force)
    finally:
        STATE.update(step="", done=0, total=0)
        _running.release()


_st_lock = threading.RLock()        # schützt den Stand des Laufs (mehrere Fäden schreiben Quellen, Ruhezeiten, Protokoll)
_save_lock = threading.Lock()       # ein Speichern zur Zeit, damit nie ein älterer Stand einen neueren überschreibt


class _Merker(dict):
    """Teil des Laufzustands (Quellen, Ruhezeiten), der bei jeder Änderung sofort auf die Platte geht: Ist eine Quelle
    fertig oder gesperrt, steht das im Stand, auch wenn der Container gleich danach neu startet."""

    def __init__(self, data, save):
        super().__init__(data)
        self._save = save

    def __setitem__(self, key, value):
        with _st_lock:
            super().__setitem__(key, value)
        self._save()


def _run(by_hand, force):
    begun = time.monotonic()
    at = now()
    settings = load_settings()
    prev = store.load_json("sync.json", {})
    offen = bool(prev.get("laeuft"))            # der letzte Lauf endete nicht: Neustart mittendrin
    st = {"started": _iso(at), "by_hand": by_hand, "ok": False, "laeuft": True, "versuch": (prev.get("versuch") or 1) + 1 if offen else 1,
          "log": list(prev.get("log") or [])[-LOG_LINES // 2:] if offen else [], "stand": dict(prev.get("stand") or {}),
          "stats": prev.get("stats") or {}, "built": prev.get("built") or ""}

    def save():
        """Stand auf die Platte. Ein Fehler beim Schreiben (Platte voll) hält den Lauf nicht auf."""
        with _save_lock:
            with _st_lock:
                snap = json.loads(json.dumps(dict(st, log=st["log"][-LOG_LINES:])))
            try:
                store.save_json("sync.json", snap)
            except OSError as e:
                print("Stand des Abgleichs speichern:", e, file=sys.stderr)

    def log(msg):
        line = now().strftime("%H:%M:%S ") + msg
        with _st_lock:
            st["log"].append(line)
            del st["log"][:-LOG_LINES]

    st["sources"] = _Merker(prev.get("sources") or {}, save)
    st["rest"] = _Merker(dict({k: v for k, v in (prev.get("rest") or {}).items() if v > _iso(at)}, **rests(at)), save)
    STATE.update(started=st["started"], log=st["log"])
    try:
        if offen:
            log(f"Der Lauf vom {str(prev.get('started'))[:16].replace('T', ' ')} UTC wurde unterbrochen (Neustart); neuer Anlauf, Versuch {st['versuch']}")
        log(f"Abgleich gestartet ({'von Hand' if by_hand else 'Zeitplan'}), Pokédex {sources.VERSION}")
        save()                                  # der Beginn steht auf der Platte, bevor die erste Quelle gefragt wird
        db.migrate()
        name = db.backup()
        if name:
            log(f"Sicherung deiner Daten: sicherung/{name}")
        ok = _build(st, log, force, at)
        save()                                  # neue Datenbank und ihr Stand
        STATE["step"] = "Bilder, Karten und Map Genie (parallel)"
        res = _parallel({"bilder": lambda: _media(st, log, settings, at), "karten": lambda: _media_tiles(st, log, settings, at),
                         "mapgenie": lambda: _media_mg(st, log, at), "itemhq": lambda: _media_itemhq(st, log, settings, at),
                         "smogon": lambda: _smogon(st, log, at)})
        for k, v in res.items():
            if isinstance(v, Exception):
                log(f"{k}: abgebrochen: {type(v).__name__}: {v}")
                fehler.melden(v, k, "abgleich", immer=True)
        st["ok"] = ok
    except Exception as e:          # ein Fehler im Code soll den Dienst nicht beenden
        log(f"Abgebrochen: {type(e).__name__}: {e}")
        fehler.melden(e, "Lauf", "abgleich", immer=True)
        st["ok"] = False
    finally:
        # auch nach einem Fehler außerhalb der Quellen: Ende, Protokoll und Ruhezeiten stehen im Stand
        s = int(time.monotonic() - begun)
        with _st_lock:
            st["finished"] = _iso(now())
            st.pop("laeuft", None)
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
        from .. import showdown as _sd
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
        fehler.melden(e, "Datenbank bauen", "abgleich", immer=True)
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
        except ValueError as ex:
            fehler.melden(ex, f"Sets Generation {gen}", "showdown")
            data = None
        if isinstance(data, dict) and data:
            out[gen] = data
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
            fehler.melden(e, "Zeitplan", "abgleich", immer=True)
        boot = False
        time.sleep(60)
