"""Leistungstest auf Klick (Statuskarte, POST /api/leistung): Wie schnell antwortet dieser Server, wie viel Speicher und
Rechenzeit braucht er?

Gemessen wird am laufenden Dienst, über die eigene Schnittstelle auf 127.0.0.1 (der Weg der Oberfläche, mit JSON und
Packen), ohne Netz nach außen:

- je Weg die erste Antwort im Test und der Median von WIEDERHOLUNGEN weiteren, Größe roh und gepackt,
- Arbeitsspeicher vorher und nachher, Spitze seit dem Start, Rechenzeit des Prozesses während des Tests (alle Fäden,
  also auch die, die die Anfragen beantworten), Anzahl der Kerne und Last,
- wie lange das letzte Laden der Spieldaten in den Speicher dauerte (beim Start oder nach einem Abgleich),
- ein Schreibtest: SCHREIBEN erfundene Teams, jedes für sich gespeichert, in einer temporären Datenbank in einem
  temporären Ordner im Datenordner (dasselbe Laufwerk wie user.db); danach ist der Ordner wieder weg.

Nicht während eines Abgleichs, nie zwei zugleich. user.db wird nicht geschrieben (die Wege lesen; „Was fehlt mir noch“
liest dabei die eigenen Markierungen). Das Ergebnis steht mit Version und Zeit in `leistung.json` (die letzten
BEHALTEN). Ein Weg, der scheitert (Fehler oder Zeitlimit), steht mit Status 0 und Meldung darin; der Test läuft weiter.
"""
import gzip
import http.client
import json
import os
import sqlite3
import statistics
import tempfile
import threading
import time
from datetime import datetime, timezone

from . import abfragen, abruf, db, importer, sources, statuskarte, store

DATEI = statuskarte.LEISTUNG
BEHALTEN = 10
WIEDERHOLUNGEN = 3
SCHREIBEN = 100
ZEITLIMIT_S = 120            # je Anfrage; ein Weg, der länger braucht, zählt als gescheitert
_lock = threading.Lock()


def _iso(t):
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def wege(spiel, pokemon):
    """Die gemessenen Wege: (Name, Adresse). Die Liste und die Attacken zuerst, sie sind die größten Antworten."""
    return [("Pokémon-Liste", f"/api/pokemon?spiel={spiel}"),
            ("Attacken", f"/api/attacken?spiel={spiel}"),
            ("Detailseite", f"/api/pokemon/{pokemon}?spiel={spiel}"),
            ("Attacken eines Pokémon", f"/api/pokemon/{pokemon}/attacken?spiel={spiel}"),
            ("Items", f"/api/items?spiel={spiel}"),
            ("Typen", f"/api/typen?spiel={spiel}"),
            ("Was fehlt mir noch", f"/api/fehlt?spiel={spiel}"),
            ("Metadaten", "/api/meta"),
            ("Statuskarte", "/api/statuskarte")]


def letzte():
    """Die gespeicherten Ergebnisse, das jüngste zuerst."""
    return [r for r in store.load_json(DATEI, []) if isinstance(r, dict)]


def _abruf(port, weg):
    """(Millisekunden, Status, Bytes roh, Bytes übertragen) einer Anfrage an den eigenen Server."""
    con = http.client.HTTPConnection("127.0.0.1", port, timeout=ZEITLIMIT_S)
    try:
        start = time.perf_counter()
        con.request("GET", weg, headers={"Host": f"127.0.0.1:{port}", "Accept-Encoding": "gzip"})
        r = con.getresponse()
        body = r.read()
        ms = (time.perf_counter() - start) * 1000
        roh = len(gzip.decompress(body)) if r.getheader("Content-Encoding") == "gzip" else len(body)
        return ms, r.status, roh, len(body)
    finally:
        con.close()


def _schreibtest():
    """SCHREIBEN erfundene Teams einzeln in eine temporäre Datenbank speichern und wieder lesen: {anzahl, ms, ms_je}."""
    with tempfile.TemporaryDirectory(dir=db.data_dir(), prefix=".leistung-") as tmp:
        pfad = os.path.join(tmp, "probe.db")
        db.migrate(pfad)
        con = sqlite3.connect(pfad)
        try:
            start = time.perf_counter()
            for i in range(SCHREIBEN):
                con.execute("INSERT INTO team (name, spiel, mitglieder, fest, gewichte, details, geaendert) VALUES (?,?,?,?,?,?,?)",
                            (f"Probe {i}", "probe", json.dumps([1, 4, 7, 25, 133, 150]), "[]", "{}", "{}", "2000-01-01T00:00:00+00:00"))
                con.commit()                     # wie die Oberfläche: jedes Speichern für sich
            gelesen = con.execute("SELECT count(*) FROM team").fetchone()[0]
            ms = (time.perf_counter() - start) * 1000
        finally:
            con.close()
    if gelesen != SCHREIBEN:
        raise ValueError(f"Schreibtest: {gelesen} statt {SCHREIBEN} Zeilen gelesen")
    return {"anzahl": SCHREIBEN, "ms": round(ms), "ms_je": round(ms / SCHREIBEN, 2)}


def _beispiel(D, spiel):
    """Spiel und ein Pokémon darin für die Detailseite: das gewünschte Spiel, sonst das neueste; das erste Pokémon der
    Liste dieses Spiels."""
    if spiel not in D.game_by:
        spiel = D.games[-1]["kennung"]
    rows = abfragen.search({"spiel": spiel}).get("rows") or []
    return spiel, (rows[0]["id"] if rows else 1)


def messen(port, body=None, at=None):
    """Den Test jetzt ausführen und das Ergebnis speichern. port: der Port dieses Servers (aus der Anfrage)."""
    body = body or {}
    if abruf.brief()["running"]:
        raise ValueError("Während eines Abgleichs misst der Leistungstest nicht; bitte danach noch einmal.")
    D = abfragen.data()
    if not D:
        raise ValueError("Noch keine Spieldaten; der Leistungstest misst erst nach dem ersten Abgleich.")
    if not _lock.acquire(blocking=False):
        raise ValueError("Der Leistungstest läuft schon.")
    try:
        at = at or datetime.now(timezone.utc)
        spiel, pokemon = _beispiel(D, str(body.get("spiel") or ""))
        ram_vorher = statuskarte.ram()["jetzt"]
        cpu = os.times()
        start = time.perf_counter()
        abrufe = []
        for name, weg in wege(spiel, pokemon):
            try:
                ms, status, roh, gesendet = _abruf(port, weg)
                wieder = [_abruf(port, weg)[0] for _ in range(WIEDERHOLUNGEN)]
                abrufe.append({"name": name, "weg": weg, "status": status, "erste_ms": round(ms, 1),
                               "wieder_ms": round(statistics.median(wieder), 1), "bytes": roh, "gepackt": gesendet})
            except (OSError, http.client.HTTPException) as e:      # Zeitlimit, Verbindung: festhalten, weiter messen
                abrufe.append({"name": name, "weg": weg, "status": 0, "erste_ms": None, "wieder_ms": None, "bytes": 0,
                               "gepackt": 0, "meldung": f"{type(e).__name__}: {e}"[:200]})
        schreiben = _schreibtest()
        dauer = (time.perf_counter() - start) * 1000
        cpu2 = os.times()
        ram = statuskarte.ram()
        try:
            last = round(os.getloadavg()[0], 2)
        except (AttributeError, OSError):         # nicht auf jedem System
            last = None
        out = {"zeit": _iso(at), "version": sources.VERSION, "daten": importer.VERSION, "spiel": spiel, "pokemon": pokemon,
               "dauer_ms": round(dauer), "cpu_s": round((cpu2.user - cpu.user) + (cpu2.system - cpu.system), 2),
               "kerne": os.cpu_count(), "last": last,
               "ram": {"vorher": ram_vorher, "nachher": ram["jetzt"], "spitze": ram["spitze"]},
               "laden": abfragen.ladezeit(), "abrufe": abrufe, "schreiben": schreiben,
               "ok": all(a["status"] == 200 for a in abrufe)}
        store.save_json(DATEI, [out] + letzte()[:BEHALTEN - 1])
        return out
    finally:
        _lock.release()
