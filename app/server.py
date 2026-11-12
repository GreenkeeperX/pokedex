"""Kleiner Webserver: liefert die Oberfläche, die Sprites und eine JSON-Schnittstelle. Wie im VR-Navigator."""
import datetime
import gzip
import io
import ipaddress
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import abfragen, abruf, altissimo, aufgaben, db, mapgenie, sources, store

STATIC = os.path.join(os.path.dirname(__file__), "static")
LOCAL_SUFFIXES = (".home.arpa", ".local", ".lan", ".internal", ".localhost")
TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml",
         ".png": "image/png", ".html": "text/html; charset=utf-8", ".gif": "image/gif", ".mp3": "audio/mpeg", ".ogg": "audio/ogg",
         ".jpg": "image/jpeg", ".webp": "image/webp"}


def host_allowed(host, extra=None):
    """Schutz gegen DNS-Rebinding: angenommen werden nur IP-Adressen, localhost, Namen ohne Punkt, Namen im
    eigenen Netz (LOCAL_SUFFIXES) und, was in ALLOWED_HOSTS steht (mit Komma; „.beispiel.de“ gilt für alle darunter)."""
    if not host:
        return True
    name = host.strip().lower()
    if name.startswith("["):
        name = name[1:].split("]")[0]
    elif name.count(":") == 1:
        name = name.split(":")[0]
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    name = name.rstrip(".")
    if "." not in name or name.endswith(LOCAL_SUFFIXES):
        return True
    extra = os.environ.get("ALLOWED_HOSTS", "") if extra is None else extra
    for e in (x.strip().lower().rstrip(".") for x in extra.split(",")):
        if e and (name == e or (e.startswith(".") and name.endswith(e))):
            return True
    return False


# ------------------------------------------------------------------ Verbindungstest im Hintergrund

# Ergebnis und Probe-Seiten liegen nur im Speicher; ein neuer Test ersetzt sie (nichts sammelt sich auf der Platte)
DIAG = {"id": 0, "running": False, "lines": None, "error": "", "proben": {}, "stand": {}, "start": "", "dauer": None}
_diag_lock = threading.Lock()


def start_diag():
    with _diag_lock:
        if DIAG["running"]:
            return False
        DIAG.update(id=DIAG["id"] + 1, running=True, lines=None, error="", proben={}, stand={}, start=_now(), dauer=None)

    def run():
        proben, t0 = {}, time.monotonic()
        try:
            lines, error = abruf.diagnose(proben, DIAG["stand"]), ""
        except Exception as e:
            traceback.print_exc()
            lines, error = None, type(e).__name__
        with _diag_lock:
            DIAG.update(running=False, lines=lines, error=error, proben=proben, dauer=round(time.monotonic() - t0))
    threading.Thread(target=run, daemon=True).start()
    return True


# ------------------------------------------------------------------ Teams und Entscheidungen (user.db)

def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _ids(v, limit=6):
    out = []
    for x in v or []:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            raise ValueError("Mitglieder: Zahlen erwartet")
    return out[:limit]


def teams():
    con = db.user()
    try:
        rows = con.execute("SELECT * FROM team ORDER BY geaendert DESC").fetchall()
    finally:
        con.close()
    return [{"id": r["id"], "name": r["name"], "spiel": r["spiel"] or "", "mitglieder": json.loads(r["mitglieder"]),
             "fest": json.loads(r["fest"] or "[]"), "gewichte": json.loads(r["gewichte"] or "{}"),
             "details": json.loads(r["details"] or "{}"), "geaendert": r["geaendert"]}
            for r in rows]


def _details(v, members):
    """Je Platz {"level": 1–100, "attacken": bis zu 4 IDs, dazu wahlweise item, faehigkeit, wesen, tera, evs, ivs,
    geschlecht, schillernd, spitzname}, als Liste parallel zu den Mitgliedern. Ältere Oberflächen
    schicken {id: {...}}; das wird hier zur Liste."""
    out = []
    for d in abfragen.slot_details(v, members):
        lv = d.get("level")
        try:
            lv = min(100, max(1, int(lv))) if lv not in (None, "") else None
        except (TypeError, ValueError):
            raise ValueError("Level: eine Zahl von 1 bis 100")
        moves = []
        for x in (d.get("attacken") or [])[:4]:
            try:
                moves.append(int(x))
            except (TypeError, ValueError):
                raise ValueError("Attacken: Zahlen erwartet")
        e = {"level": lv, "attacken": moves}
        for k in ("item", "faehigkeit", "wesen", "tera"):        # seit 0.18.0 (Showdown-Import): IDs
            if isinstance(d.get(k), int) and 0 < d[k] < 100000:
                e[k] = d[k]
        for k in ("evs", "ivs"):
            v6 = d.get(k)
            if isinstance(v6, list) and len(v6) == 6 and all(isinstance(x, int) and 0 <= x <= 255 for x in v6):
                e[k] = v6
        for k in ("el", "el_ziel"):                               # Effort Levels (Legenden: Arceus), seit 0.25.0
            v6 = d.get(k)
            if isinstance(v6, list) and len(v6) == 6 and all(isinstance(x, int) and 0 <= x <= 10 for x in v6):
                e[k] = v6
        if d.get("geschlecht") in ("M", "F"):
            e["geschlecht"] = d["geschlecht"]
        if d.get("schillernd") is True:
            e["schillernd"] = True
        if d.get("spitzname"):
            e["spitzname"] = " ".join(str(d["spitzname"]).split())[:30]
        out.append(e)
    return out


def save_team(body):
    name = " ".join(str(body.get("name") or "").split())[:80]
    if not name:
        raise ValueError("Bitte einen Namen für das Team angeben")
    members = _ids(body.get("mitglieder"))
    fixed = [i for i in _ids(body.get("fest")) if i in members]
    weights = {k: float(v) for k, v in (body.get("gewichte") or {}).items() if k in abfragen.team.CRITERIA}
    spiel = str(body.get("spiel") or "")[:60]
    details = _details(body.get("details"), members)
    con = db.user()
    try:
        tid = body.get("id")
        args = (name, spiel, json.dumps(members), json.dumps(fixed), json.dumps(weights), json.dumps(details), _now())
        if tid:
            cur = con.execute("UPDATE team SET name=?, spiel=?, mitglieder=?, fest=?, gewichte=?, details=?, geaendert=? WHERE id=?",
                              args + (int(tid),))
            if not cur.rowcount:
                raise ValueError("Team nicht gefunden")
        else:
            tid = con.execute("INSERT INTO team (name, spiel, mitglieder, fest, gewichte, details, geaendert) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              args).lastrowid
        con.commit()
    finally:
        con.close()
    return {"id": int(tid)}


MARKS = ("favorit", "gefangen", "schillernd", "alpha")      # Tabellen gleicher Form: (spiel, form, seit)
CAUGHT_EXTRA = ("schillernd", "alpha")                       # gelten zusätzlich zu gefangen


def marked(table, spiel):
    """IDs mit Marke (Favorit oder gefangen) im Spiel, in der Reihenfolge des Markierens."""
    assert table in MARKS
    con = db.user()
    try:
        return [r[0] for r in con.execute(f"SELECT form FROM {table} WHERE spiel = ? ORDER BY seit, form", (str(spiel or ""),))]
    finally:
        con.close()


def favorites(spiel):
    return abfragen.rows_of(marked("favorit", spiel), spiel)


def set_mark(table, body):
    """Marke an- oder abwählen: {spiel, id, an}; id darf auch eine Liste sein (mehrere auf einmal).
    Schillernd und Alpha setzen auch gefangen; nicht mehr gefangen nimmt beides weg."""
    assert table in MARKS
    spiel = str(body.get("spiel") or "")[:60]
    raw = body.get("id")
    try:
        ids = [int(x) for x in (raw if isinstance(raw, list) else [raw])][:2000]
    except (TypeError, ValueError):
        raise ValueError("id: eine Zahl")
    con = db.user()
    try:
        for fid in ids:
            if body.get("an", True):
                for t in (table, "gefangen") if table in CAUGHT_EXTRA else (table,):
                    con.execute(f"INSERT OR IGNORE INTO {t} (spiel, form, seit) VALUES (?, ?, ?)", (spiel, fid, _now()))
            else:
                for t in (table, *CAUGHT_EXTRA) if table == "gefangen" else (table,):
                    con.execute(f"DELETE FROM {t} WHERE spiel = ? AND form = ?", (spiel, fid))
        con.commit()
    finally:
        con.close()
    return {"ok": True}


def found(spiel, karte=None):
    """Gefundene Kartensymbole: {Karte: [Objekt]} im Spiel, mit karte nur diese."""
    con = db.user()
    try:
        sql, args = "SELECT karte, objekt FROM gefunden WHERE spiel = ?", [str(spiel or "")]
        if karte:
            sql, args = sql + " AND karte = ?", args + [str(karte)]
        out = {}
        for k, o in con.execute(sql + " ORDER BY seit", args):
            out.setdefault(k, []).append(o)
        return out
    finally:
        con.close()


def set_found(body):
    """Kartensymbol als gefunden markieren oder nicht: {spiel, karte, objekt (Text oder Liste), an}."""
    spiel, karte = str(body.get("spiel") or "")[:60], str(body.get("karte") or "")[:60]
    raw = body.get("objekt")
    objs = [str(x)[:80] for x in (raw if isinstance(raw, list) else [raw]) if x not in (None, "")][:5000]
    if not karte or not objs:
        raise ValueError("karte und objekt erwartet")
    con = db.user()
    try:
        for o in objs:
            if body.get("an", True):
                con.execute("INSERT OR IGNORE INTO gefunden (spiel, karte, objekt, seit) VALUES (?, ?, ?, ?)", (spiel, karte, o, _now()))
            else:
                con.execute("DELETE FROM gefunden WHERE spiel = ? AND karte = ? AND objekt = ?", (spiel, karte, o))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "n": len(objs)}


FREE = "freilassen"         # Ziel „Freilassen“: nur aus der Sammlung nehmen


def transfer(body):
    """Sammlung übertragen (etwa nach Pokémon HOME): {von, nach, ids, behalten}. Die Pokémon gelten danach im Zielspiel
    als gefangen; ohne behalten verschwinden sie aus der Sammlung im bisherigen Spiel (wie beim Übertragen im Spiel)."""
    von, nach = str(body.get("von") or "")[:60], str(body.get("nach") or "")[:60]
    free = nach == FREE
    if not nach or nach == von or not (free or nach in {abfragen.HOME} | {g["kennung"] for g in abfragen.games()}):
        raise ValueError("nach: ein anderes Spiel")
    try:
        ids = [int(x) for x in body.get("ids") or []][:2000]
    except (TypeError, ValueError):
        raise ValueError("ids: Zahlen")
    con = db.user()
    try:
        for fid in ids:
            extra = [t for t in CAUGHT_EXTRA if con.execute(f"SELECT 1 FROM {t} WHERE spiel = ? AND form = ?", (von, fid)).fetchone()]
            for t in ("gefangen", *extra):
                if not free:
                    con.execute(f"INSERT OR IGNORE INTO {t} (spiel, form, seit) VALUES (?, ?, ?)", (nach, fid, _now()))
                if free or not body.get("behalten"):
                    con.execute(f"DELETE FROM {t} WHERE spiel = ? AND form = ?", (von, fid))
        con.commit()
    finally:
        con.close()
    return {"ok": True, "n": len(ids)}


def set_favorite(body):
    return set_mark("favorit", body)


def export():
    """Alles Eigene als JSON (die Sicherung): Teams, Favoriten, Gefangene, Entscheidungen."""
    con = db.user()
    try:
        out = {t: [dict(r) for r in con.execute(f"SELECT spiel, form, seit FROM {t} ORDER BY spiel, seit, form")] for t in MARKS}
        dec = [dict(r) for r in con.execute("SELECT art, schluessel, wert, at FROM entscheidung ORDER BY art, schluessel")]
        got = [dict(r) for r in con.execute("SELECT spiel, karte, objekt, seit FROM gefunden ORDER BY spiel, karte, seit")]
        log = [dict(r, team=json.loads(r["team"] or "[]"), gegner=json.loads(r["gegner"] or "[]"))
               for r in con.execute("SELECT spiel, at, ergebnis, team, gegner, notiz FROM kampf ORDER BY at, id")]
    finally:
        con.close()
    return {"app": "pokedex", "version": sources.VERSION, "exportiert": _now(), "teams": teams(), "favoriten": out["favorit"],
            "gefangen": out["gefangen"], "schillernd": out["schillernd"], "alpha": out["alpha"], "gefunden": got, "entscheidungen": dec,
            "kampftagebuch": log}


def restore(body):
    """Sicherung einlesen: ersetzt Teams, Favoriten, Gefangene und Entscheidungen durch den Inhalt der Datei.
    Vorher legt db.backup() eine Kopie von user.db an."""
    if body.get("app") != "pokedex" or not isinstance(body.get("teams"), list):
        raise ValueError("Keine Sicherung des Pokédex (es fehlen app und teams)")
    rows = {"team": [], "favorit": [], "gefangen": [], "schillernd": [], "alpha": [], "gefunden": [], "entscheidung": [], "kampf": []}
    for t in body["teams"][:500]:
        name = " ".join(str(t.get("name") or "").split())[:80] or "Team"
        members = _ids(t.get("mitglieder"))
        fixed = [i for i in _ids(t.get("fest")) if i in members]
        weights = {k: float(v) for k, v in (t.get("gewichte") or {}).items() if k in abfragen.team.CRITERIA}
        rows["team"].append((name, str(t.get("spiel") or "")[:60], json.dumps(members), json.dumps(fixed), json.dumps(weights),
                             json.dumps(_details(t.get("details"), members)), str(t.get("geaendert") or _now())[:40]))
    for table, key in (("favorit", "favoriten"), ("gefangen", "gefangen"), ("schillernd", "schillernd"), ("alpha", "alpha")):
        for r in (body.get(key) or [])[:20000]:
            try:
                rows[table].append((str(r.get("spiel") or "")[:60], int(r["form"]), str(r.get("seit") or _now())[:40]))
            except (TypeError, ValueError, KeyError, AttributeError):
                raise ValueError(f"{key}: Einträge mit spiel und form erwartet")
    for r in (body.get("gefunden") or [])[:50000]:
        if isinstance(r, dict) and r.get("karte") and r.get("objekt"):
            rows["gefunden"].append((str(r.get("spiel") or "")[:60], str(r["karte"])[:60], str(r["objekt"])[:80], str(r.get("seit") or _now())[:40]))
    for r in (body.get("entscheidungen") or [])[:20000]:
        if isinstance(r, dict) and r.get("art") == "pruefung" and r.get("wert") in ("pokeapi", "showdown", "egal"):
            rows["entscheidung"].append(("pruefung", str(r.get("schluessel") or "")[:200], r["wert"], str(r.get("at") or _now())[:40]))
    for r in (body.get("kampftagebuch") or [])[:50000]:
        if isinstance(r, dict) and r.get("ergebnis") in ("sieg", "niederlage"):
            rows["kampf"].append((str(r.get("spiel") or "")[:60], str(r.get("at") or _now())[:40], r["ergebnis"],
                                  json.dumps(_ids(r.get("team"))[:6]), json.dumps(_ids(r.get("gegner"))[:6]), str(r.get("notiz") or "")[:500]))
    db.backup(force=True)
    con = db.user()
    try:
        for table in rows:
            if table not in ("gefunden", "kampf") or ("kampftagebuch" if table == "kampf" else table) in body:   # ältere Sicherungen lassen sie stehen
                con.execute(f"DELETE FROM {table}")
        con.executemany("INSERT INTO team (name, spiel, mitglieder, fest, gewichte, details, geaendert) VALUES (?, ?, ?, ?, ?, ?, ?)", rows["team"])
        for table in MARKS:
            con.executemany(f"INSERT OR IGNORE INTO {table} (spiel, form, seit) VALUES (?, ?, ?)", rows[table])
        con.executemany("INSERT OR REPLACE INTO entscheidung VALUES (?, ?, ?, ?)", rows["entscheidung"])
        con.executemany("INSERT OR IGNORE INTO gefunden (spiel, karte, objekt, seit) VALUES (?, ?, ?, ?)", rows["gefunden"])
        con.executemany("INSERT INTO kampf (spiel, at, ergebnis, team, gegner, notiz) VALUES (?, ?, ?, ?, ?, ?)", rows["kampf"])
        con.commit()
    finally:
        con.close()
    return {"teams": len(rows["team"]), "favoriten": len(rows["favorit"]), "gefangen": len(rows["gefangen"]),
            "gefunden": len(rows["gefunden"]), "entscheidungen": len(rows["entscheidung"]), "kampftagebuch": len(rows["kampf"])}


def battle_log(spiel=None):
    """Kampftagebuch eines Spiels, neueste zuerst, mit Bilanz und den häufigsten Gegnern (mit Siegen gegen sie)."""
    con = db.user()
    try:
        rows = [dict(r) for r in con.execute("SELECT id, spiel, at, ergebnis, team, gegner, notiz FROM kampf WHERE spiel = ? "
                                              "ORDER BY at DESC, id DESC", (str(spiel or ""),))]
    finally:
        con.close()
    foes = {}
    for r in rows:
        r["team"], r["gegner"] = json.loads(r["team"] or "[]"), json.loads(r["gegner"] or "[]")
        for f in set(r["gegner"]):
            n, w = foes.get(f, (0, 0))
            foes[f] = (n + 1, w + (r["ergebnis"] == "sieg"))
    top = sorted(foes.items(), key=lambda x: (-x[1][0], x[1][1]))[:12]
    wins = sum(r["ergebnis"] == "sieg" for r in rows)
    return {"rows": rows, "kaempfe": len(rows), "siege": wins, "gegner": [{"id": f, "kaempfe": n, "siege": w} for f, (n, w) in top]}


def add_battle(body):
    """Eintrag ins Kampftagebuch: spiel, ergebnis (sieg|niederlage), team und gegner (Form-IDs), notiz."""
    if body.get("ergebnis") not in ("sieg", "niederlage"):
        raise ValueError("ergebnis: sieg oder niederlage")
    con = db.user()
    try:
        cur = con.execute("INSERT INTO kampf (spiel, at, ergebnis, team, gegner, notiz) VALUES (?, ?, ?, ?, ?, ?)",
                          (str(body.get("spiel") or "")[:60], _now(), body["ergebnis"], json.dumps(_ids(body.get("team"))[:6]),
                           json.dumps(_ids(body.get("gegner"))[:6]), " ".join(str(body.get("notiz") or "").split())[:500]))
        con.commit()
        return {"id": cur.lastrowid}
    finally:
        con.close()


def delete_battle(body):
    con = db.user()
    try:
        con.execute("DELETE FROM kampf WHERE id = ?", (int(body.get("id") or 0),))
        con.commit()
    finally:
        con.close()
    return {"ok": True}


def delete_team(body):
    con = db.user()
    try:
        con.execute("DELETE FROM team WHERE id = ?", (int(body.get("id") or 0),))
        con.commit()
    finally:
        con.close()
    return {"ok": True}


def spieldaten():
    """Alle Spieldaten als ZIP: die gebaute Datenbank, Stand und Protokoll des Abgleichs, Einstellungen und eine Liste,
    welche Bilder, Rufe und Kartenkacheln da sind und welche fehlen. Ohne die Medien selbst und ohne eigene Daten."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        if db.has_data():
            z.write(os.path.join(db.data_dir(), "pokeapi.db"), "pokeapi.db")
        z.writestr("abgleich.json", json.dumps(store.load_json("sync.json", {}), ensure_ascii=False, indent=1))
        z.writestr("einstellungen.json", json.dumps(abruf.load_settings(), ensure_ascii=False, indent=1))
        z.writestr("medien.json", json.dumps(abruf.media_inventory(), ensure_ascii=False, indent=1))
        z.writestr("zu-erledigen.json", json.dumps(abfragen.pruefung(), ensure_ascii=False, indent=1))
        z.writestr("LIESMICH.txt", SPIELDATEN_TEXT.format(version=sources.VERSION, tag=_now()[:10]))
    return buf.getvalue()


SPIELDATEN_TEXT = """Pokédex {version}, Spieldaten vom {tag}

pokeapi.db          SQLite-Datenbank mit allen Spieldaten (PokéAPI, Showdown, PKHeX, Spawnpunkte, gepflegte Ergänzungen)
abgleich.json       Stand und Protokoll des letzten Abgleichs
einstellungen.json  Zeitplan und Bilder-Schalter
medien.json         je Bildart: erwartet, vorhanden, fehlende Nummern, bei der Quelle nicht vorhanden
zu-erledigen.json   Abweichungen zwischen PokéAPI und Showdown mit der Entscheidung dazu

Nicht enthalten: die Bilder, Rufe und Kartenkacheln selbst und eigene Daten (Teams, Favoriten, Gefangene);
die stehen in der Sicherung.
"""


def answer(body):
    """Antwort auf den Auftrag aus „Zu erledigen“: mit dry nur Vorschau, sonst Entscheidungen übernehmen."""
    res = aufgaben.parse(str(body.get("text") or ""), abfragen.pruefung())
    if not body.get("dry"):
        con = db.user()
        try:
            for r in res["uebernehmen"]:
                con.execute("INSERT OR REPLACE INTO entscheidung VALUES (?, ?, ?, ?)", ("pruefung", r["key"], r["wert"], _now()))
            con.commit()
        finally:
            con.close()
        res["gespeichert"] = len(res["uebernehmen"])
    return res


def decide(body):
    art = str(body.get("art") or "")
    key = str(body.get("schluessel") or "")[:200]
    wert = str(body.get("wert") or "")[:40]
    if art not in ("pruefung",) or not key:
        raise ValueError("Unbekannte Entscheidung")
    if wert not in ("", "pokeapi", "showdown", "egal"):
        raise ValueError("Wert: pokeapi, showdown oder egal")
    con = db.user()
    try:
        if wert:
            con.execute("INSERT OR REPLACE INTO entscheidung VALUES (?, ?, ?, ?)", (art, key, wert, _now()))
        else:
            con.execute("DELETE FROM entscheidung WHERE art = ? AND schluessel = ?", (art, key))
        con.commit()
    finally:
        con.close()
    return {"ok": True}


def meta():
    st = abruf.status()
    return {"app": "pokedex", "version": sources.VERSION, "neu": sources.NEUIGKEITEN, "has_data": db.has_data(), **abfragen.meta(),
            "spiele": abfragen.games(), "einstellungen": abruf.load_settings(),
            "abgleich": {k: st.get(k) for k in ("running", "started", "finished", "ok", "built", "step")}}


# ------------------------------------------------------------------ HTTP

_PACKED = {}
_GZ = {}


def _packed(obj):
    """Große, unveränderte Antworten (zusammengeführte Karten) nur einmal in JSON wandeln; das Objekt selbst ist der
    Schlüssel (abfragen hält es, solange es gilt)."""
    hit = _PACKED.get(id(obj))
    if hit and hit[0] is obj:
        return hit[1]
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    if len(_PACKED) >= 16:
        _PACKED.clear()
    _PACKED[id(obj)] = (obj, body)
    return body


_WARM = set()


def _prewarm(d):
    """Die Karten eines Spiels im Hintergrund zusammenführen und packen, sobald die Oberfläche die Liste holt: der
    Wechsel zwischen ihnen wartet dann nicht mehr auf den Server."""
    key = (d["spiel"], d.get("am"), len(d["karten"]))
    if key in _WARM:
        return
    _WARM.add(key)

    def run():
        for m in d["karten"][:abfragen.MERGED_MAX - 2]:
            try:
                t0 = time.time()
                body = _map_body(m, d["spiel"], d["am"])
                print(f"Karte bereit: {d['spiel']}/{m.get('slug')} in {time.time() - t0:.1f} s, "
                      f"{len(body) // 1024} KB", file=sys.stderr, flush=True)
            except Exception as e:
                print("Karte vorbereiten:", e, file=sys.stderr)
    threading.Thread(target=run, daemon=True, name="karten-vorbereiten").start()


_MAPBODY = {}
_MAPBODY_LOCK = threading.Lock()


def _map_body(m, spiel, am):
    """0.53: eine zusammengeführte Karte als JSON (und gepackt), gespeichert im Datenordner (kartencache/): die Punkte
    ändern sich nur mit einem Abgleich oder einer neuen Version, also rechnet der Server sie nur dann neu, nicht nach
    jedem Neustart. Schlüssel: Spiel, Karte, Stand der Karte, Stand von pokeapi.db, Version."""
    key = json.dumps([spiel, m.get("slug"), m.get("id"), am, abfragen._stamp(), sources.VERSION])
    hit = _MAPBODY.get(key)
    if hit:
        return hit
    with _MAPBODY_LOCK:
        hit = _MAPBODY.get(key)
        if hit:
            return hit
        folder = os.path.join(db.data_dir(), "kartencache")
        name = re.sub(r"[^a-z0-9-]+", "_", f"{spiel}__{m.get('slug') or m.get('id')}".lower())
        path = os.path.join(folder, name + ".json.gz")
        body = None
        try:
            with open(path + ".key", encoding="utf-8") as f:
                if f.read() == key:
                    with open(path, "rb") as g:
                        gz = g.read()
                    body = gzip.decompress(gz)
        except (OSError, EOFError, ValueError):
            body = None
        if body is None:
            body = json.dumps(abfragen.mg_map(m, spiel, am), ensure_ascii=False).encode("utf-8")
            gz = gzip.compress(body, compresslevel=6)
            try:
                os.makedirs(folder, exist_ok=True)
                with open(path + ".tmp", "wb") as g:
                    g.write(gz)
                os.replace(path + ".tmp", path)
                with open(path + ".key", "w", encoding="utf-8") as f:
                    f.write(key)
            except OSError as e:
                print("Kartencache:", e, file=sys.stderr)
        while len(_MAPBODY) >= 12:
            _MAPBODY.pop(next(iter(_MAPBODY)))
        _MAPBODY[key] = body
        if len(_GZ) >= 16:
            _GZ.clear()
        _GZ[id(body)] = (body, gz)
        return body


WARM_GAMES = ("legends-arceus",)    # 0.52: diese Karten führt der Server schon beim Start zusammen (Arceus ist das Startspiel)


def _warm_loop():
    """0.52: nach dem Start und nach jedem Abgleich (neuer Stand der Karten) die Karten von WARM_GAMES vorbereiten,
    damit das erste Öffnen nicht auf das Zusammenführen wartet. Prüft alle 5 Minuten; ist alles bereit, kostet das nichts."""
    try:
        abfragen.data()
    except Exception:
        pass
    while True:
        for spiel in WARM_GAMES:
            try:
                d = abruf.mg_maps(spiel)
                if d:
                    _prewarm(d)
            except Exception as e:
                print("Karten vorbereiten:", e, file=sys.stderr)
        time.sleep(300)


class Handler(BaseHTTPRequestHandler):
    server_version = "pokedex"
    protocol_version = "HTTP/1.1"    # Verbindungen bleiben offen: die vielen Kacheln der Karte kommen ohne neuen Aufbau
    timeout = 60                     # ungenutzte Verbindungen schließen

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        packed = len(body) > 20_000 and ctype.startswith(("application/json", "text/")) and "gzip" in (self.headers.get("Accept-Encoding") or "")
        if packed:
            hit = _GZ.get(id(body))
            if hit and hit[0] is body:
                body = hit[1]
            else:
                gz = gzip.compress(body, compresslevel=5)
                if any(body is b for _, b in _PACKED.values()):   # gleiche große Antwort: nur einmal packen
                    if len(_GZ) >= 16:
                        _GZ.clear()
                    _GZ[id(body)] = (body, gz)
                body = gz
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if packed:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", (extra or {}).pop("Cache-Control", "no-store"))
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if self.close_connection:
            self.send_header("Connection", "close")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _body(self, limit=200_000):
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise ValueError("nur application/json")
        n = int(self.headers.get("Content-Length") or 0)
        if n < 0 or n > limit:
            raise ValueError("zu groß")
        body = json.loads(self.rfile.read(n) or b"{}")
        if not isinstance(body, dict):
            raise ValueError("JSON-Objekt erwartet")
        return body

    def _foreign(self):
        if host_allowed(self.headers.get("Host")):
            return False
        self.close_connection = True
        self._send(421, {"error": "Unbekannte Adresse. Erlaubte Namen stehen in ALLOWED_HOSTS (siehe README)."})
        return True

    def _file(self, path, cache="no-cache"):
        with open(path, "rb") as f:
            self._send(200, f.read(), TYPES.get(os.path.splitext(path)[1], "application/octet-stream"), {"Cache-Control": cache})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        split = urllib.parse.urlsplit(self.path)
        path = split.path
        q = {k: v[0] for k, v in urllib.parse.parse_qs(split.query).items()}
        if self._foreign():
            return
        try:
            if path in ("/", "/index.html"):
                # 0.48.6: CSS und JS mit der Version in der Adresse, damit der Browser nach einem Update nie alte Dateien nimmt
                with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as f:
                    page = f.read().replace('href="style.css"', f'href="style.css?v={sources.VERSION}"').replace(
                        'src="js/app.js"', f'src="js/app.js?v={sources.VERSION}"')
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8", {"Cache-Control": "no-cache"})
            elif re.fullmatch(r"/(style\.css|icon\.svg|js/[a-z-]+\.js)", path) and os.path.isfile(os.path.join(STATIC, path[1:])):
                self._file(os.path.join(STATIC, path[1:]))
            elif m := re.fullmatch(r"/(sprites|artwork)/(\d{1,6})\.png", path):
                # Artwork fehlt (noch nicht geladen): das kleine Sprite statt dessen
                for kind in ((m.group(1), "sprites") if m.group(1) == "artwork" else ("sprites",)):
                    f = os.path.join(db.data_dir(), kind, f"{int(m.group(2))}.png")
                    if os.path.isfile(f):
                        self._file(f, "max-age=604800")
                        break
                else:
                    self._send(404, {"error": "kein Bild"})
            elif m := re.fullmatch(r"/(shiny|shinyart|anim|rufe|itembild|formen)/(\d{1,6})", path):
                # Item-Bilder: das große von Serebii, wenn es da ist
                kinds = ("itemhq", "itembild") if m.group(1) == "itembild" else (m.group(1),)
                f = next((os.path.join(db.data_dir(), k, m.group(2) + e) for k in kinds for e in (".png", ".gif", ".mp3", ".ogg")
                          if os.path.isfile(os.path.join(db.data_dir(), k, m.group(2) + e))), None)
                if f:
                    self._file(f, "max-age=604800")
                else:
                    self._send(404, {"error": "nicht geladen"})
            elif m := re.fullmatch(r"/karten/([a-z]{4,30})/(\d)-(\d{1,2})-(\d{1,2})\.png", path):
                f = os.path.join(db.data_dir(), "karten", m.group(1), f"{m.group(2)}-{m.group(3)}-{m.group(4)}.png")
                if m.group(1) in abruf.PLA_MAPS and os.path.isfile(f):
                    self._file(f, "max-age=604800")
                else:
                    self._send(404, {"error": "keine Kachel"})
            elif path == f"/karten/{altissimo.VILLAGE}/bild.png":
                f = os.path.join(db.data_dir(), "karten", altissimo.VILLAGE, "bild.png")
                if os.path.isfile(f):
                    self._file(f, "max-age=604800")
                else:
                    self._send(404, {"error": "kein Kartenbild"})
            elif m := re.fullmatch(r"/mgkachel/([a-z0-9-]{2,60})/([a-z0-9-]{1,60})/(\d{1,2})/(\d{1,6})/(\d{1,6})", path):
                f = abruf.mg_tile(m.group(1), m.group(2), *(int(m.group(i)) for i in (3, 4, 5)))
                if f:
                    self._file(f, "max-age=2592000")
                else:                # fehlende Kacheln (Rand, Meer) fragt der Browser eine Stunde nicht wieder
                    self._send(404, {"error": "keine Kachel"}, extra={"Cache-Control": "max-age=3600"})
            elif m := re.fullmatch(r"/mgbild/([a-z0-9-]{2,60})/([a-z0-9-]{1,60})/(\d{1,5})", path):
                f = abruf.mg_image(m.group(1), m.group(2), int(m.group(3)))
                if f:
                    self._file(f, "max-age=2592000")
                else:
                    self._send(404, {"error": "kein Ortsbild"}, extra={"Cache-Control": "max-age=3600"})
            elif path == "/api/speicher":
                self._send(200, abruf.disk_usage(force=q.get("neu") == "1"))
            elif path == "/api/kacheln/umwandeln":
                d = abruf.tile_convert_state(q.get("spiel", ""), q.get("karte", ""))
                self._send(200 if d else 404, d or {"error": "keine Karte zum Umwandeln"})
            elif path == "/api/smogon":
                self._send(200, abfragen.smogon_view(q.get("spiel")))
            elif path == "/api/mapgenie/eigene":
                # eigene Punkte (Legenden: Arceus) auf der Karte von Map Genie
                d = abruf.mg_maps(q.get("spiel"))
                m = next((m for m in (d or {}).get("karten", []) if m["slug"] == q.get("karte")), None)
                ok = m and d["spiel"] == "legends-arceus"
                self._send(200 if ok else 404, abfragen.mg_overlay(m, d.get("am")) if ok else {"error": "keine eigenen Punkte"})
            elif path == "/api/mapgenie":
                d = abruf.mg_maps(q.get("spiel"))
                if d and q.get("karte"):
                    m = next((m for m in d["karten"] if m["slug"] == q["karte"]), None)
                    if m:
                        self._send(200, _map_body(m, d["spiel"], d["am"]))
                    else:
                        self._send(404, {"error": "keine Karte"})
                else:
                    self._send(200, {"karten": [{"slug": m["slug"], "titel": m["titel"], "orte": len(m["orte"])} for m in (d or {}).get("karten", [])],
                                     "kacheln": abruf.mg_status()})
                    if d:
                        _prewarm(d)
            elif path == "/api/fehlt":
                d = abfragen.missing(q)
                self._send(200 if d else 404, d or {"error": "kein Spiel"})
            elif path == "/api/gebiete":
                d = abfragen.areas(q)
                self._send(200 if d else 404, d or {"error": "keine Gebiete"})
            elif m := re.fullmatch(r"/api/karte/([a-z]{4,30})", path):
                d = abfragen.map_data(m.group(1), q)
                self._send(200 if d else 404, d or {"error": "keine Karte"})
            elif path == "/healthz":
                self._send(200, {"ok": True, "version": sources.VERSION})
            elif path == "/api/meta":
                self._send(200, meta())
            elif path == "/api/pokemon":
                self._send(200, abfragen.search(q))
            elif m := re.fullmatch(r"/api/pokemon/(\d{1,6})/attacken", path):
                d = abfragen.moves_of(int(m.group(1)), q)
                self._send(200 if d else 404, d or {"error": "Pokémon nicht gefunden"})
            elif m := re.fullmatch(r"/api/pokemon/(\d{1,6})", path):
                d = abfragen.detail(int(m.group(1)), q)
                self._send(200 if d else 404, d or {"error": "Pokémon nicht gefunden"})
            elif path == "/api/attacken":
                self._send(200, abfragen.move_list(q))
            elif path == "/api/items":
                self._send(200, abfragen.item_list(q))
            elif path == "/api/typen":
                self._send(200, abfragen.type_chart(q))
            elif path == "/api/teams":
                self._send(200, teams())
            elif path == "/api/favoriten":
                self._send(200, favorites(q.get("spiel")))
            elif path == "/api/gefangen":
                self._send(200, marked("gefangen", q.get("spiel")))
            elif path == "/api/schillernd":
                self._send(200, marked("schillernd", q.get("spiel")))
            elif path == "/api/sammeln":
                d = abruf.mg_maps(q.get("spiel"))
                self._send(200, abfragen.collectibles(d, lambda m: json.loads(_map_body(m, d["spiel"], d["am"])),
                                                      found(d["spiel"]) if d else {}))
            elif path == "/api/tmorte":
                d = abruf.mg_maps(q.get("spiel"))
                self._send(200, abfragen.tm_places(d, lambda m: json.loads(_map_body(m, d["spiel"], d["am"]))))
            elif path == "/api/shinysperre":
                self._send(200, abfragen.shiny_locks(q.get("spiel")))
            elif path == "/api/alpha":
                self._send(200, {"ids": marked("alpha", q.get("spiel")), "moeglich": abfragen.alpha_possible(q.get("spiel"))})
            elif path == "/api/gefunden":
                self._send(200, found(q.get("spiel"), q.get("karte")))
            elif path == "/api/raids":
                self._send(200, abfragen.raid_list(q))
            elif path == "/api/trainer":
                self._send(200, abfragen.trainer_list(q))
            elif path == "/api/auftraege":
                self._send(200, abfragen.request_list(q))
            elif path == "/api/kampftagebuch":
                self._send(200, battle_log(q.get("spiel")))
            elif path == "/api/export":
                day = _now()[:10]
                self._send(200, export(), extra={"Content-Disposition": f'attachment; filename="pokedex-daten-{day}.json"'})
            elif path == "/api/spieldaten":
                self._send(200, spieldaten(), "application/zip",
                           {"Content-Disposition": f'attachment; filename="pokedex-spieldaten-{_now()[:10]}.zip"'})
            elif path == "/api/aufgabe":
                self._send(200, aufgaben.task(abfragen.pruefung()))
            elif path == "/api/status":
                self._send(200, abruf.status())
            elif path == "/api/diag":
                with _diag_lock:
                    st = DIAG["stand"]
                    self._send(200, {k: v for k, v in DIAG.items() if k not in ("proben", "stand")} | {"proben": len(DIAG["proben"]),
                               "gesamt": st.get("gesamt", 0), "fertig": st.get("fertig", 0), "laeuft": list(st.get("laeuft", []))[:4]})
            elif path == "/api/diag/proben":
                with _diag_lock:
                    body = {"app": "pokedex", "version": sources.VERSION, "proben": dict(DIAG["proben"])}
                self._send(200, body, extra={"Content-Disposition": f'attachment; filename="pokedex-proben-{_now()[:10]}.json"'})
            elif path == "/api/pruefung":
                self._send(200, abfragen.pruefung())
            else:
                self._send(404, {"error": "nicht gefunden"})
        except Exception as e:
            self._fail(path, e)

    POST = {
        "/api/team/bewerten": abfragen.team_view,
        "/api/team/vorschlag": abfragen.team_suggest,
        "/api/team/optimieren": abfragen.team_optimize,
        "/api/team/gegner": abfragen.team_matchup,
        "/api/teams": save_team,
        "/api/teams/loeschen": delete_team,
        "/api/favoriten": set_favorite,
        "/api/gefangen": lambda b: set_mark("gefangen", b),
        "/api/schillernd": lambda b: set_mark("schillernd", b),
        "/api/alpha": lambda b: set_mark("alpha", b),
        "/api/gefunden": set_found,
        "/api/team/gefangen": abfragen.team_caught,
        "/api/team/import": abfragen.paste_import,
        "/api/team/doppel": abfragen.team_doubles,
        "/api/schaden": abfragen.damage_view,
        "/api/schaden/uebersicht": abfragen.damage_matrix,
        "/api/effort": abfragen.effort_view,
        "/api/werte": abfragen.stats_view,
        "/api/effort/team": abfragen.effort_team,
        "/api/kampftagebuch": add_battle,
        "/api/kampftagebuch/loeschen": delete_battle,
        "/api/team/export": abfragen.paste_export,
        "/api/uebertragen": transfer,
        "/api/restore": restore,
        "/api/entscheidung": decide,
        "/api/antwort": answer,
        "/api/einstellungen": abruf.save_settings,
        "/api/abgleich": lambda b: {"started": abruf.start(force=bool(b.get("neu")))},
        "/api/diag": lambda b: {"started": start_diag()},
        "/api/kacheln/umwandeln": abruf.tile_upload,
    }
    # größere Rümpfe: Datensicherung, Kacheln aus dem Browser (je Anfrage einige, als Base64)
    BODY_MAX = {"/api/restore": 8_000_000, "/api/kacheln/umwandeln": 6_000_000}

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if self._foreign():
            return
        try:
            fn = self.POST.get(path)
            if not fn:
                self.close_connection = True      # Rumpf ungelesen: die Verbindung nicht weiter nutzen
                self._send(404, {"error": "nicht gefunden"})
                return
            self._send(200, fn(self._body(self.BODY_MAX.get(path, 200_000))))
        except ValueError as e:
            self.close_connection = True
            self._send(400, {"error": str(e)})
        except Exception as e:
            self._fail(path, e)

    def _fail(self, path, e):
        print(f"Fehler bei {path}:", file=sys.stderr)
        traceback.print_exception(e, file=sys.stderr)
        if self.command == "POST":
            self.close_connection = True
        self._send(500, {"error": f"Interner Fehler ({type(e).__name__}), Einzelheiten im Protokoll des Containers"})


def main():
    db.migrate()
    port = int(os.environ.get("PORT", "8789"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    # Spieldaten gleich in den Speicher laden, damit die erste Anfrage nach einem Update nicht wartet
    threading.Thread(target=abfragen.data, daemon=True, name="vorladen").start()
    threading.Thread(target=_warm_loop, daemon=True, name="karten-warm").start()
    if os.environ.get("AUTO_SYNC", "1") != "0":
        threading.Thread(target=abruf.scheduler, daemon=True, name="zeitplan").start()
        abruf.start_stock()           # Kartenkacheln im Hintergrund vervollständigen
    print(f"Pokédex {sources.VERSION} läuft auf Port {port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
