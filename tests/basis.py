"""Gemeinsame Grundlage der Tests: eigener Datenordner je Test, der Server über HTTP, die Mini-Datenbank.

- `TempData`: ein leerer Datenordner je Test (store.DATA_DIR), danach wieder weg,
- `HttpTest`: dazu der Server auf einem freien Port (nur 127.0.0.1), mit `get`, `post` und `json`,
- `MitMiniDatenbank`: ein Datenordner mit der Mini-Datenbank aus tests/minidb.py als pokeapi.db (Verweis auf die einmal
  gebaute Datei, nur lesend) und einer frischen user.db,
- `HttpMitDaten`: beides zusammen, der Weg der Oberfläche,
- `oberflaeche_js()`: der Text aller Skripte der Oberfläche in der Reihenfolge von index.html (seit 0.61.0 mehrere Dateien),
- `app_quellen()`: alle Python-Dateien unter app/, auch in Paketen (seit 0.62.0 `app/abfragen/`), als {Pfad: Text},
- `im_paket(paket, name, neu)`: einen Namen eines Pakets für einen Test ersetzen, im Paket und in jedem seiner Module
  (seit 0.63.0; ein Ersatz nur im Paket erreichte die Funktionen der Module nicht).
"""
import contextlib
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock
from http.server import ThreadingHTTPServer

from app import db, fehler, server, store
from tests import minidb

fehler.STUMM = True          # das Fehlerregister schreibt in den Tests nichts ins Protokoll


def oberflaeche_js():
    """Alle Skripte der Oberfläche hintereinander, wie der Browser sie lädt (index.html, server.skripte)."""
    with open(os.path.join(server.STATIC, "index.html"), encoding="utf-8") as f:
        teile = server.skripte(f.read())
    texte = []
    for rel in teile:
        with open(os.path.join(server.STATIC, rel), encoding="utf-8") as f:
            texte.append(f.read())
    return "\n".join(texte)


def app_quellen(paket=""):
    """Alle Python-Dateien unter app/ (oder nur unter app/<paket>/), auch in Unterordnern: {Pfad ab app/: Text}, sortiert."""
    wurzel = os.path.dirname(os.path.abspath(server.__file__))
    out = {}
    for ordner, unter, dateien in os.walk(os.path.join(wurzel, paket)):
        unter[:] = sorted(u for u in unter if u != "__pycache__")
        for name in sorted(dateien):
            if name.endswith(".py"):
                pfad = os.path.join(ordner, name)
                with open(pfad, encoding="utf-8") as f:
                    out[os.path.relpath(pfad, wurzel).replace(os.sep, "/")] = f.read()
    return out


@contextlib.contextmanager
def im_paket(paket, name, neu=mock.DEFAULT, **art):
    """Wie mock.patch.object(paket, name, neu), aber für ein Paket wie app.abruf: ersetzt den Namen im Paket und in jedem
    Modul darunter, das dasselbe Objekt unter diesem Namen führt (es definiert oder importiert hat). So sieht jede Funktion
    des Pakets den Ersatz, wie früher in der einen Datei. Ohne neu entsteht ein MagicMock(**art), derselbe für alle."""
    alt = getattr(paket, name)
    if neu is mock.DEFAULT:
        neu = mock.MagicMock(**art)
    module = [paket] + [m for n, m in sorted(sys.modules.items()) if n.startswith(paket.__name__ + ".") and m is not None]
    with contextlib.ExitStack() as stapel:
        for m in module:
            if name in vars(m) and vars(m)[name] is alt:
                stapel.enter_context(mock.patch.object(m, name, neu))
        yield neu


class TempData(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._old = store.DATA_DIR
        store.DATA_DIR = self.dir

    def tearDown(self):
        store.DATA_DIR = self._old
        shutil.rmtree(self.dir, ignore_errors=True)


class HttpTest(TempData):
    """Der Server über HTTP auf einem freien Port, ohne Netz nach außen."""
    HANDLER = server.Handler

    def setUp(self):
        super().setUp()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), self.HANDLER)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def _request(self, method, path, body, headers):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            c.request(method, path, body=body, headers=headers)
            r = c.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            c.close()

    def get(self, path, **headers):
        """(Status, Kopfzeilen, Rumpf als Bytes)"""
        return self._request("GET", path, None, headers)

    def post(self, path, data, **headers):
        """POST als JSON, wie die Oberfläche: (Status, Kopfzeilen, Rumpf als Bytes)"""
        return self._request("POST", path, json.dumps(data).encode("utf-8"), {"Content-Type": "application/json", **headers})

    def json(self, path, data=None, status=200):
        """Antwort als Objekt; der Status muss stimmen. Mit data als POST."""
        code, _, body = self.get(path) if data is None else self.post(path, data)
        self.assertEqual(code, status, f"{path}: {body[:300]!r}")
        return json.loads(body)


class MitMiniDatenbank(TempData):
    """Die Mini-Datenbank als pokeapi.db des Tests. Das Fehlerregister ist vor jedem Test leer; `ohne_fehler` prüft,
    dass keine Abfrage still auf einen Ersatzwert ausgewichen ist."""

    def setUp(self):
        super().setUp()
        os.symlink(minidb.pfad(), db.pokeapi_path())
        db.migrate()
        fehler.leeren()

    def ohne_fehler(self):
        self.assertEqual([(e["wo"], e["art"], e["text"]) for e in fehler.liste()], [])


class HttpMitDaten(MitMiniDatenbank, HttpTest):
    """Der Server über HTTP mit der Mini-Datenbank: derselbe Weg wie die Oberfläche."""
