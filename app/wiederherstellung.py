"""Monatlicher Wiederherstellungstest: Lässt sich die jüngste tägliche Sicherung von user.db wirklich zurückholen?

Die Sicherung wird nur lesend geöffnet und in ein temporäres Verzeichnis wiederhergestellt (SQLite-Backup, wie beim
Anlegen). Geprüft wird an der Kopie:

1. Integrität (`PRAGMA integrity_check`),
2. Laden wie nach einem Update (`db.migrate` an der Kopie: fehlende Tabellen und Spalten der jetzigen Version),
3. Lesen wie die Anwendung: jede Tabelle von user.db zählen, die JSON-Spalten (Teams, Kampftagebuch) zerlegen.

user.db, die Sicherungen und alles andere im Datenordner bleiben unberührt; geschrieben wird nur das Ergebnis
(`wiederherstellung.json`: zeit, ok, text, datei, dauer_ms). Die Statuskarte zeigt es (app/statuskarte.py).
"""
import json
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone

from . import db, fehler, store

DATEI = "wiederherstellung.json"
ABSTAND = timedelta(days=30)        # „monatlich“: so lange nach dem letzten Test ist der nächste fällig
ABSTAND_FEHLER = timedelta(days=1)  # nach einem gescheiterten Test schon am nächsten Tag (mit der nächsten Sicherung)
# Spalten mit JSON-Text, die die Anwendung beim Lesen zerlegt (server.teams, server.export)
JSON_SPALTEN = {"team": ("mitglieder", "fest", "gewichte", "details"), "kampf": ("team", "gegner")}
NAMEN = {"team": ("Team", "Teams"), "favorit": ("Favorit", "Favoriten"), "gefangen": ("Gefangenes", "Gefangene"),
         "schillernd": ("Schillerndes", "Schillernde"), "alpha": ("Alpha", "Alphas"),
         "gefunden": ("Kartensymbol", "Kartensymbole"), "entscheidung": ("Entscheidung", "Entscheidungen"),
         "kampf": ("Kampf", "Kämpfe")}


def _iso(t):
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def juengste():
    """Pfad der jüngsten täglichen Sicherung (sicherung/user-JJJJMMTT.db) oder None."""
    ordner = os.path.join(db.data_dir(), "sicherung")
    try:
        namen = sorted(f for f in os.listdir(ordner) if f.startswith("user-") and f.endswith(".db"))
    except FileNotFoundError:
        return None
    return os.path.join(ordner, namen[-1]) if namen else None


def letzter():
    """Das gespeicherte Ergebnis des letzten Tests oder None."""
    return store.load_json(DATEI, {}) or None


def faellig(at=None):
    """Ein Test ist fällig, wenn es eine Sicherung gibt und der letzte Test fehlt oder älter als ABSTAND ist (nach einem
    gescheiterten: ABSTAND_FEHLER)."""
    if not juengste():
        return False
    test = letzter() or {}
    try:
        zuletzt = datetime.fromisoformat(test.get("zeit"))
    except (TypeError, ValueError):
        return True
    return zuletzt <= (at or datetime.now(timezone.utc)) - (ABSTAND if test.get("ok") else ABSTAND_FEHLER)


def _pruefe_kopie(pfad):
    """Prüft eine wiederhergestellte Kopie; gibt {Tabelle: Zeilen} zurück oder wirft ValueError mit dem Grund."""
    con = sqlite3.connect(pfad)
    try:
        ergebnis = [r[0] for r in con.execute("PRAGMA integrity_check")]
        if ergebnis != ["ok"]:
            raise ValueError("Integrität verletzt: " + "; ".join(ergebnis[:3]))
    finally:
        con.close()
    db.migrate(pfad)
    con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    try:
        zeilen = {}
        for tabelle in NAMEN:
            zeilen[tabelle] = con.execute(f"SELECT count(*) FROM {tabelle}").fetchone()[0]
            spalten = JSON_SPALTEN.get(tabelle)
            if spalten:
                for zeile in con.execute(f"SELECT rowid, {', '.join(spalten)} FROM {tabelle}"):
                    for name, wert in zip(spalten, zeile[1:]):
                        try:
                            json.loads(wert or "null")
                        except ValueError:
                            raise ValueError(f"{tabelle} Zeile {zeile[0]}: {name} ist kein gültiger Text")
        return zeilen
    finally:
        con.close()


def pruefen(at=None, speichern=True):
    """Den Test jetzt ausführen. Ohne Sicherung: {ok: None, text}, nichts gespeichert. Sonst das Ergebnis, gespeichert."""
    at = at or datetime.now(timezone.utc)
    quelle = juengste()
    if not quelle:
        return {"zeit": _iso(at), "ok": None, "text": "Es gibt noch keine Sicherung zum Prüfen.", "datei": "", "dauer_ms": 0}
    start = time.monotonic()
    out = {"zeit": _iso(at), "datei": os.path.basename(quelle)}
    try:
        with tempfile.TemporaryDirectory(prefix="pokedex-wiederherstellung-") as tmp:
            kopie = os.path.join(tmp, "user.db")
            with db.sicherung_lock:                  # keine Sicherung, die gerade erst geschrieben wird
                src = sqlite3.connect(f"file:{quelle}?mode=ro", uri=True)
                dst = sqlite3.connect(kopie)
                try:
                    src.backup(dst)
                finally:
                    src.close()
                    dst.close()
            zeilen = _pruefe_kopie(kopie)
        teile = [f"{n} {NAMEN[t][0] if n == 1 else NAMEN[t][1]}" for t, n in zeilen.items() if n]
        out.update(ok=True, text="Wiederhergestellt und lesbar: " + (", ".join(teile) if teile else "noch keine eigenen Daten") + ".")
    except (sqlite3.DatabaseError, ValueError) as e:     # das erwartete Scheitern: die Sicherung taugt nicht
        out.update(ok=False, text=f"Nicht wiederherstellbar: {e}")
    except Exception as e:                               # etwas anderes (Platz, Rechte): ins Fehlerregister
        fehler.melden(e, "wiederherstellung", "abgleich", immer=True)
        out.update(ok=False, text=f"Test nicht möglich: {type(e).__name__}: {e}")
    out["dauer_ms"] = round((time.monotonic() - start) * 1000)
    if speichern:
        store.save_json(DATEI, out)
    return out
