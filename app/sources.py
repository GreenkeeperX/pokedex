"""Netzabrufe: eine Stelle für alle Quellen (PokéAPI, Pokémon Showdown, Sprites, PokéWiki).

Übernommen aus dem VR-Navigator: ehrliche Kennung, nur öffentliche Ziele, Grenzen für Antwortgröße
und Zeit. Alle Abrufe laufen über `fetch(url)`, damit Tests eine Attrappe einsetzen können.
"""
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
import zlib

VERSION = "0.1.0"

# Das Tool gibt sich immer als es selbst zu erkennen. Antwortet eine Quelle mit einer Sperre
# (403, 429) oder einer Prüfseite, hört es auf, statt sich zu tarnen.
USER_AGENT = f"pokedex/{VERSION} (privates Nachschlage-Tool)"
BLOCKED = (403, 429)
MAX_BODY = 40 << 20      # größte Antwort: pokemon_moves.csv hat gut 10 MB


def blocked_target(url):
    """Grund, warum das Tool eine Adresse nicht abruft, sonst "". Abgerufen wird nur das
    öffentliche Internet, damit nie Geräte im Heimnetz angesprochen werden."""
    p = urllib.parse.urlsplit(str(url or ""))
    if p.scheme not in ("http", "https"):
        return "nur http und https"
    if p.username or p.password:
        return "Adresse mit Zugangsdaten"
    try:
        port = p.port or (443 if p.scheme == "https" else 80)
        infos = socket.getaddrinfo(p.hostname or "", port, proto=socket.IPPROTO_TCP)
    except (OSError, ValueError, UnicodeError):
        return ""
    for info in infos:
        try:
            ip = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        except ValueError:
            continue
        if not ip.is_global:
            return "Adresse nicht öffentlich"
    return ""


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nur ins öffentliche Internet."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        why = blocked_target(newurl)
        if why:
            raise urllib.error.URLError(f"Weiterleitung abgelehnt: {why}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirect)


class FetchError(Exception):
    def __init__(self, url, status, detail=""):
        super().__init__(f"{status} bei {url} {detail}".strip())
        self.url, self.status = url, status


def _inflate(raw, wbits):
    d = zlib.decompressobj(wbits)
    out = d.decompress(raw, MAX_BODY + 1)
    if len(out) > MAX_BODY:
        raise ValueError("Antwort zu groß")
    return out


def _decode(raw, enc):
    if enc == "gzip":
        return _inflate(raw, 16 + zlib.MAX_WBITS)
    if enc == "deflate":
        try:
            return _inflate(raw, zlib.MAX_WBITS)
        except zlib.error:
            return _inflate(raw, -zlib.MAX_WBITS)
    return raw


def request(url, timeout=40, encoding="gzip, deflate", headers=None, raw=False):
    """HTTP GET ohne Ausnahme: liefert Status, Text (mit raw die Bytes unter „body“) und Kopfdaten
    für den Verbindungstest."""
    head = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
        "Accept-Encoding": encoding,
        **(headers or {}),
    }
    out = {"url": url, "status": 0, "text": "", "enc": "", "server": "", "error": blocked_target(url)}
    if out["error"]:
        return out
    try:
        try:
            resp = _opener.open(urllib.request.Request(url, headers=head), timeout=timeout)
        except urllib.error.HTTPError as e:
            resp = e                      # Fehlerseiten haben auch einen Inhalt
        with resp:
            body = resp.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise ValueError("Antwort zu groß")
            out["status"] = getattr(resp, "status", None) or resp.getcode()
            out["enc"] = (resp.headers.get("Content-Encoding") or "").lower()
            out["server"] = resp.headers.get("Server") or ""
            if out["enc"] not in ("", "identity", "gzip", "deflate") and encoding != "identity":
                return request(url, timeout, "identity", headers, raw)
            data = _decode(body, out["enc"])
            if raw:
                out["body"] = data
            else:
                out["text"] = data.decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
    except Exception as e:                # Zeitüberschreitung, DNS, TLS
        out["error"] = str(e)[:160]
    return out


def fetch(url, timeout=40, headers=None, raw=False):
    """HTTP GET, gibt Text zurück, mit raw die Bytes. Wirft FetchError mit Statuscode."""
    r = request(url, timeout, headers=headers, raw=raw)
    if r["error"]:
        raise FetchError(url, 0, r["error"])
    if r["status"] >= 400:
        raise FetchError(url, r["status"])
    return r.get("body", b"") if raw else r["text"]


def challenge(text):
    """Prüfseite statt Inhalt (Cloudflare „Just a moment…“), sonst ""."""
    t = str(text or "")[:200_000]
    if "cf_chl_opt" in t or "<title>Just a moment" in t:
        return "Prüfseite von Cloudflare"
    return ""
