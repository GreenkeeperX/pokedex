"""Gemeinsame Grundlage der Tests: eigener Datenordner je Test, der Server über HTTP, die Mini-Datenbank.

- `TempData`: ein leerer Datenordner je Test (store.DATA_DIR), danach wieder weg,
- `HttpTest`: dazu der Server auf einem freien Port (nur 127.0.0.1), mit `get`, `post` und `json`,
- `MitMiniDatenbank`: ein Datenordner mit der Mini-Datenbank aus tests/minidb.py als pokeapi.db (Verweis auf die einmal
  gebaute Datei, nur lesend) und einer frischen user.db,
- `HttpMitDaten`: beides zusammen, der Weg der Oberfläche.
"""
import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from app import db, fehler, server, store
from tests import minidb

fehler.STUMM = True          # das Fehlerregister schreibt in den Tests nichts ins Protokoll


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
