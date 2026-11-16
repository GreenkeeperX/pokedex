"""Fehlerregister (seit 0.58.1): Fehler, die eine Ansicht oder einen Lauf nicht abbrechen sollen, werden gezählt statt
verschluckt. Leitsatz „Lieber melden als raten“: Ein Fehler darf nicht aussehen wie „keine Daten“.

Je Fehler (Quelle, Stelle, Art) ein Eintrag mit Text, erstem und letztem Zeitpunkt und Anzahl; höchstens MAX Einträge,
die am längsten nicht aufgetretenen fallen weg. Das Register steht in fehler.json im Datenordner und übersteht den
Neustart. Die technischen Einzelheiten (Traceback) gehen einmal je Eintrag und Start ins Protokoll des Containers.

Zwei Wege hinein:
- melden(e): eine Ausnahme aus einer Abfrage. Fehlt nur eine Tabelle oder Spalte (ältere Datenbank, der nächste Abgleich
  baut sie) oder gibt es noch gar keine Datenbank, ist das kein Fehler und wird nicht gezählt (fehlt).
- notiere(quelle, wo, art, text): ein Ereignis ohne Ausnahme, etwa „HTTP 404“ bei einer Quelle des Abgleichs.

Für die Oberfläche sammelt der Server je Anfrage, was dabei gemeldet wurde (beginne, ende), und gibt es in der Kopfzeile
X-Pokedex-Fehler mit: Die betroffene Ansicht zeigt dann einen Hinweis, statt still weniger anzuzeigen.
"""
import os
import sqlite3
import sys
import threading
import traceback
from datetime import datetime, timezone

from . import store

FILE = "fehler.json"
MAX = 100               # so viele verschiedene Fehler bleiben
TEXT = 300              # Zeichen je Fehlertext
SAVE_S = 20             # so lange sammelt das Register, bevor es schreibt (viele Fehler nacheinander: ein Schreiben)
STUMM = False           # True: nichts ins Protokoll des Containers (Tests)

_lock = threading.RLock()
_reg = {"dir": None, "liste": {}, "timer": None, "gedruckt": set()}
_local = threading.local()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fehlt(e):
    """Kein Fehler, sondern ein älterer Stand: Die Tabelle oder Spalte gibt es in dieser Datenbank (noch) nicht, oder es
    gibt noch gar keine Datenbank (db.game() gibt dann None, die Abfrage scheitert an der fehlenden Verbindung)."""
    if isinstance(e, sqlite3.OperationalError):
        return str(e).startswith(("no such table", "no such column"))
    return isinstance(e, AttributeError) and "'NoneType'" in str(e) and not os.path.isfile(os.path.join(store.DATA_DIR, "pokeapi.db"))


def _liste():
    """Das Register, einmal je Start (und je Datenordner) von der Platte gelesen. Nur unter _lock aufrufen."""
    if _reg["dir"] != store.DATA_DIR:
        got = store.load_json(FILE, {})
        _reg.update(dir=store.DATA_DIR, liste={k: v for k, v in got.items() if isinstance(v, dict)}, gedruckt=set())
    return _reg["liste"]


def notiere(quelle, wo, art, text="", tb=None):
    """Ein Ereignis eintragen oder hochzählen. quelle: woher (Quelle des Abgleichs oder „abfrage“, „server“, „karte“),
    wo: Stelle (Funktion, Server), art: kurze Art („HTTP 404“, „KeyError“), text: Einzelheit für die Anzeige."""
    quelle, wo, art, text = str(quelle)[:40], str(wo)[:80], str(art)[:60], " ".join(str(text).split())[:TEXT]
    key = f"{quelle}|{wo}|{art}"
    at = _now()
    with _lock:
        liste = _liste()
        e = liste.pop(key, None) or {"quelle": quelle, "wo": wo, "art": art, "erst": at, "anzahl": 0}
        e.update(text=text, zuletzt=at, anzahl=e["anzahl"] + 1)
        liste[key] = e                                  # zuletzt aufgetreten: ans Ende
        while len(liste) > MAX:
            liste.pop(next(iter(liste)))
        if key not in _reg["gedruckt"]:
            _reg["gedruckt"].add(key)
            if not STUMM:
                print(f"Fehler ({quelle}, {wo}): {art}: {text}" + (f"\n{tb}" if tb else ""), file=sys.stderr, flush=True)
        if _reg["timer"] is None:
            t = threading.Timer(SAVE_S, sichern)
            t.daemon = True
            _reg["timer"] = t
            t.start()
    got = getattr(_local, "liste", None)
    if got is not None and len(got) < 5:
        got.append({"quelle": quelle, "wo": wo, "art": art, "text": text})
    return True


def melden(e, wo=None, quelle="abfrage", immer=False):
    """Eine Ausnahme eintragen, die der Aufrufer abfängt, um mit einem Ersatzwert weiterzumachen. False, wenn nur eine
    Tabelle oder Spalte fehlt (ältere Datenbank). wo: Stelle; ohne Angabe der Name der aufrufenden Funktion (ohne
    Zeilennummer, damit derselbe Fehler nach einem Update derselbe Eintrag bleibt; die Zeile steht im Traceback). immer: auch eine
    fehlende Tabelle zählt (die Ausnahme hat eine Anfrage oder einen Lauf abgebrochen, es gab keinen Ersatzwert)."""
    if not immer and fehlt(e):
        return False
    if wo is None:
        code = sys._getframe(1).f_code
        wo = getattr(code, "co_qualname", code.co_name)
    tb = "".join(traceback.format_exception(type(e), e, e.__traceback__)).rstrip()
    return notiere(quelle, wo, type(e).__name__, str(e), tb)


def sichern():
    """Register auf die Platte. Scheitert das Schreiben, bleibt es im Speicher."""
    with _lock:
        _reg["timer"] = None
        if _reg["dir"] != store.DATA_DIR or not os.path.isdir(store.DATA_DIR):
            return
        try:
            store.save_json(FILE, dict(_reg["liste"]))
        except OSError as e:
            print("Fehlerregister speichern:", e, file=sys.stderr)


def liste():
    """Alle Einträge, die jüngsten zuerst: [{quelle, wo, art, text, erst, zuletzt, anzahl}]."""
    with _lock:
        return [dict(v) for v in reversed(list(_liste().values()))]     # das Register steht in der Reihenfolge des Auftretens


def leeren():
    with _lock:
        _liste().clear()
        _reg["gedruckt"].clear()
    sichern()
    return {"ok": True}


def beginne():
    """Ab jetzt sammeln, was in diesem Faden gemeldet wird (eine Anfrage an den Server)."""
    _local.liste = []


def ende():
    """Was seit beginne() in diesem Faden gemeldet wurde; beendet das Sammeln."""
    got = getattr(_local, "liste", None) or []
    _local.liste = None
    return got
