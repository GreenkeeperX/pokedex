"""Die beiden Datenbanken im Datenordner.

- pokeapi.db: Spieldaten, baut der Abgleich jedes Mal neu (importer.py); wird nur gelesen
- user.db: deine Teams und Entscheidungen; der Abgleich berührt sie nie. Tabellen legt migrate() an,
  alte Dateien laden auch nach einem Update weiter (nur neue Tabellen und Spalten, nie löschen).
"""
import datetime
import os
import sqlite3
import threading

from . import store

BACKUP_KEEP = 14
_lock = threading.Lock()

USER_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS team (id INTEGER PRIMARY KEY, name TEXT NOT NULL, spiel TEXT, mitglieder TEXT NOT NULL,
       fest TEXT, gewichte TEXT, geaendert TEXT)""",
    # Entscheidungen zu „Zu erledigen“: welcher Wert gilt (art: pruefung; schluessel: form:25:Typen …)
    """CREATE TABLE IF NOT EXISTS entscheidung (art TEXT, schluessel TEXT, wert TEXT, at TEXT, PRIMARY KEY (art, schluessel))""",
)
# Spalten, die später dazukamen: (Tabelle, Spalte, Typ). Alte Dateien bekommen sie beim Start
USER_COLUMNS = (
    ("team", "details", "TEXT"),        # 0.2.0: Level und Attacken je Mitglied
)


def data_dir():
    return store.DATA_DIR


def pokeapi_path():
    return os.path.join(data_dir(), "pokeapi.db")


def user_path():
    return os.path.join(data_dir(), "user.db")


def has_data():
    return os.path.isfile(pokeapi_path())


def migrate():
    os.makedirs(data_dir(), exist_ok=True)
    with _lock:
        con = sqlite3.connect(user_path())
        try:
            for sql in USER_SCHEMA:
                con.execute(sql)
            for table, col, typ in USER_COLUMNS:
                if col not in [r[1] for r in con.execute(f"PRAGMA table_info({table})")]:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            con.commit()
        finally:
            con.close()


def user():
    """Verbindung zu user.db (schreibbar)."""
    con = sqlite3.connect(user_path(), timeout=10)
    con.row_factory = sqlite3.Row
    return con


def game():
    """Verbindung zu pokeapi.db, nur lesend. Ohne Daten: None."""
    if not has_data():
        return None
    con = sqlite3.connect(f"file:{pokeapi_path()}?mode=ro", uri=True, timeout=10, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def backup(today=None):
    """Tägliche Kopie von user.db in sicherung/, die letzten BACKUP_KEEP bleiben. Gibt den Dateinamen oder "" zurück."""
    if not os.path.isfile(user_path()):
        return ""
    day = (today or datetime.date.today()).strftime("%Y%m%d")
    folder = os.path.join(data_dir(), "sicherung")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"user-{day}.db")
    if not os.path.exists(target):
        src, dst = sqlite3.connect(user_path()), sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
    old = sorted(f for f in os.listdir(folder) if f.startswith("user-") and f.endswith(".db"))
    for f in old[:-BACKUP_KEEP]:
        os.remove(os.path.join(folder, f))
    return os.path.basename(target)
