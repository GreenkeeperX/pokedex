"""Kleine JSON-Dateien im Datenordner: settings.json (Einstellungen) und sync.json (Stand des Abgleichs).

Wie im VR-Navigator: jede Datei wird erst vollständig geschrieben und dann umbenannt, und eine
kaputte Datei bleibt daneben liegen, statt still überschrieben zu werden. Die Spieldaten und deine
Teams liegen in SQLite (siehe db.py).
"""
import json
import os
import sys
import threading
from datetime import datetime

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))

lock = threading.RLock()


def _path(name):
    return os.path.join(DATA_DIR, name)


def _load(name, default):
    try:
        with open(_path(name), encoding="utf-8") as f:
            got = json.load(f)
        if type(got) is type(default):
            return got
        why = "falsche Form"
    except FileNotFoundError:
        return json.loads(json.dumps(default))
    except ValueError as e:
        why = str(e)[:80]
    # Kaputte Datei: nicht still durch die Vorgabe ersetzen, sonst überschriebe das nächste
    # Speichern sie endgültig. Sie bleibt daneben liegen, das Protokoll des Containers nennt sie
    keep = f"{_path(name)}.kaputt-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    try:
        os.replace(_path(name), keep)
        print(f"{name} nicht lesbar ({why}), aufgehoben als {os.path.basename(keep)}", file=sys.stderr)
    except OSError:
        pass
    return json.loads(json.dumps(default))


def _save(name, obj):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = _path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())      # erst auf der Platte, dann umbenennen: kein leeres File nach Stromausfall
    os.replace(tmp, _path(name))


def load_json(name, default):
    """Dateien im Datenordner: settings.json, sync.json."""
    with lock:
        return _load(name, default)


def save_json(name, obj):
    with lock:
        _save(name, obj)
