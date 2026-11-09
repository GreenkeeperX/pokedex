"""Kleiner Webserver: liefert die Oberfläche, die Sprites und eine JSON-Schnittstelle. Wie im VR-Navigator."""
import datetime
import gzip
import ipaddress
import json
import os
import re
import sys
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import abfragen, abruf, db, sources

STATIC = os.path.join(os.path.dirname(__file__), "static")
LOCAL_SUFFIXES = (".home.arpa", ".local", ".lan", ".internal", ".localhost")
TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml",
         ".png": "image/png", ".html": "text/html; charset=utf-8"}


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

DIAG = {"id": 0, "running": False, "lines": None, "error": ""}
_diag_lock = threading.Lock()


def start_diag():
    with _diag_lock:
        if DIAG["running"]:
            return False
        DIAG.update(id=DIAG["id"] + 1, running=True, lines=None, error="")

    def run():
        try:
            lines, error = abruf.diagnose(), ""
        except Exception as e:
            traceback.print_exc()
            lines, error = None, type(e).__name__
        with _diag_lock:
            DIAG.update(running=False, lines=lines, error=error)
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
    """{id: {"level": 1–100, "attacken": bis zu 4 IDs}} nur für Mitglieder des Teams."""
    out = {}
    for k, d in (v or {}).items():
        try:
            i = int(k)
        except (TypeError, ValueError):
            continue
        if i not in members or not isinstance(d, dict):
            continue
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
        out[str(i)] = {"level": lv, "attacken": moves}
    return out


def save_team(body):
    name = " ".join(str(body.get("name") or "").split())[:80]
    if not name:
        raise ValueError("Bitte einen Namen für das Team angeben")
    members = _ids(body.get("mitglieder"))
    fixed = [i for i in _ids(body.get("fest")) if i in members]
    weights = {k: float(v) for k, v in (body.get("gewichte") or {}).items() if k in abfragen.team.CRITERIA}
    spiel = str(body.get("spiel") or "")[:60]
    details = _details(body.get("details"), set(members))
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


def delete_team(body):
    con = db.user()
    try:
        con.execute("DELETE FROM team WHERE id = ?", (int(body.get("id") or 0),))
        con.commit()
    finally:
        con.close()
    return {"ok": True}


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

class Handler(BaseHTTPRequestHandler):
    server_version = "pokedex"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        packed = len(body) > 20_000 and ctype.startswith(("application/json", "text/")) and "gzip" in (self.headers.get("Accept-Encoding") or "")
        if packed:
            body = gzip.compress(body, compresslevel=5)
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
                self._file(os.path.join(STATIC, "index.html"))
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
            elif path == "/api/typen":
                self._send(200, abfragen.type_chart(q))
            elif path == "/api/teams":
                self._send(200, teams())
            elif path == "/api/status":
                self._send(200, abruf.status())
            elif path == "/api/diag":
                with _diag_lock:
                    self._send(200, dict(DIAG))
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
        "/api/entscheidung": decide,
        "/api/einstellungen": abruf.save_settings,
        "/api/abgleich": lambda b: {"started": abruf.start(force=bool(b.get("neu")))},
        "/api/diag": lambda b: {"started": start_diag()},
    }

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if self._foreign():
            return
        try:
            fn = self.POST.get(path)
            if not fn:
                self._send(404, {"error": "nicht gefunden"})
                return
            self._send(200, fn(self._body()))
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:
            self._fail(path, e)

    def _fail(self, path, e):
        print(f"Fehler bei {path}:", file=sys.stderr)
        traceback.print_exception(e, file=sys.stderr)
        self._send(500, {"error": f"Interner Fehler ({type(e).__name__}), Einzelheiten im Protokoll des Containers"})


def main():
    db.migrate()
    port = int(os.environ.get("PORT", "8789"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    if os.environ.get("AUTO_SYNC", "1") != "0":
        threading.Thread(target=abruf.scheduler, daemon=True, name="zeitplan").start()
    print(f"Pokédex {sources.VERSION} läuft auf Port {port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
