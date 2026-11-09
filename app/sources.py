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

VERSION = "0.5.1"

# Was sich je Version ändert, für den Hinweis in der Oberfläche. Neueste zuerst; der erste Eintrag
# muss VERSION sein (Test). Ausführlich steht es in ROADMAP.md.
NEUIGKEITEN = [
    ("0.5.1", "09.11.2026", [
        "Verbindungstest prüft weitere Quellen: feste Begegnungen (Geschenke, Legendäre) und Raids aus PKHeX, "
        "Werte je Form in Legenden: Arceus, schillernde und animierte Sprites, Rufe, Showdown-Stufen und Random-Battle-Sets",
        "Verbindungstest zeigt, was die Datenbank schon hat, aber noch nicht nutzt (TM, Wesen, Ei-Gruppen, Fangraten, Beeren)",
        "Abgleich holt TM-Listen, Wesen, Ei-Gruppen und Beeren auch ohne Dateiliste von GitHub",
    ]),
    ("0.5.0", "09.11.2026", [
        "Fundorte in Legenden: Arceus aus den Spieldaten (PKHeX): je Gebiet die Stellen mit Level, Alpha-Level und Art "
        "(frei, Raum-Zeit-Verzerrung, Baum oder Erzbrocken, Massenauftreten)",
        "Filter „Gebiet“ in der Liste und bei der Teamsuche: nur Pokémon, die dort frei vorkommen",
        "PKHeX als neue Quelle im Abgleich und unter „Quellen und Lizenzen“",
    ]),
    ("0.4.2", "09.11.2026", [
        "Verbindungstest prüft auch mögliche neue Quellen: Items (PokéAPI, Showdown, PKHeX), Fundorte aus den Spieldaten "
        "(PKHeX für Legenden: Arceus, Karmesin/Purpur, Legenden: Z-A), Wikis (PokéWiki, Bulbapedia, Serebii, Pokémon Database), "
        "Karten (Map Genie) und Kampfdaten (Smogon)",
        "Probe-Seiten der Quellen zum Herunterladen, damit sich Leser für sie bauen lassen",
    ]),
    ("0.4.1", "09.11.2026", [
        "Hover-Karte mit eigenem, getöntem Hintergrund und kräftigerem Rahmen, damit sie sich von den Karten abhebt",
    ]),
    ("0.4.0", "09.11.2026", [
        "Kopfzeile und Team-Leiste gleiten beim Scrollen sanft weg und kommen beim Hochscrollen zurück",
        "Gefangen (Pokéball) je Spiel: Empfehlungen daraus im Team, Filter „nur Gefangene“ oder „nur Favoriten“, Teamsuche nur aus Gefangenen",
        "„Im Duell gegen Typen“ auf Hover-Karte und Detailseite: klar stark, stark, schwer, mit der Rechnung beim Hovern",
        "Marken (im Team, gefangen, Favorit) direkt hinter dem Namen; Knöpfe zum Setzen beim Hovern auf dem Bild",
        "Filter: „bis“ oder „nur“ Generation, „stark gegen“ wahlweise nur klar",
        "Deine Attacken als feste Liste mit vier Zeilen, Auswahl in der Tabelle hinterlegt, Status-Attacken offen mit Wirkung",
        "Team: Sortierung bleibt sichtbar, Abweichungen in Verbesserungen und Teamsuche hinterlegt, volles Team fragt nach dem Platz",
        "Ziehen aus der Suche ins Team und auf Favoriten oder Gefangene; Gegner mit rotem Rahmen und Namen; Vorteil, Nachteil, ausgeglichen",
        "Attacken mit Farben für die Werte, Hinweise zu Vorrang und Kontakt; PokéWiki-Links an Attacken, Fähigkeiten und Orten",
        "Ansicht per rundem Knopf (System, Hell, Dunkel), Version rechts daneben, Stand des letzten Abgleichs in der Kopfzeile",
        "Spielauswahl nach Generationen gruppiert; Versionen schließen per Klick daneben",
        "Einstellungen: Sicherung herunterladen und wieder einlesen, Kopieren erst, wenn es etwas gibt",
    ]),
    ("0.3.0", "09.11.2026", [
        "Nintendo-Rot, dezentere Linien; Klick auf den Titel lädt alles neu",
        "Netzdiagramm mit Speichen und Ringen; außen = Höchstwert aller Pokémon, an den Ecken eine Skala von 0 bis 10",
        "Team: dasselbe Pokémon darf mehrfach hinein, Plätze per Drag & Drop umsortieren, Sortieren nach Werten",
        "Gespeicherte Teams ändern sich erst mit „Speichern“; bis dahin „Verwerfen“ möglich",
        "Favoriten je Spiel (☆): Klick auf einen leeren Platz oder ⇄ tauscht schnell ein",
        "Hinweis, wenn Team-Mitglieder nicht zum gewählten Spiel passen",
        "Hover-Karten auch im Team, in der Team-Leiste, bei Verbesserungen und Gegnern",
        "Filter „stark gegen Typ“; ausgeschlossene Typen rot umrandet und durchgestrichen; Festgesetzte grün",
        "Attacken: Reihenfolge per Ziehen, Standard-Attacken wie im Spiel, beigebrachte Attacken (TM, Lehrer) hinzufügen",
        "„Zurück“ führt dorthin, woher du kamst; Tabellen: dritter Klick stellt die ursprüngliche Reihenfolge her",
        "Typtabelle: Zeile und Spalte per Klick festhalten, Hinweise mit Typ-Bubbles",
        "Protokoll und Verbindungstest kopieren oder herunterladen; eigene Daten als JSON herunterladen",
    ]),
    ("0.2.1", "09.11.2026", [
        "Version in der Kopfzeile; nach einem Update erscheint einmal ein Hinweis, was neu ist",
    ]),
    ("0.2.0", "09.11.2026", [
        "Liste: Hover-Karte mit Artwork, Netzdiagramm und Schwächen, Typ-Filter als Bubbles (und/oder, ausschließen), "
        "Zurücksetzen, Nachladen beim Scrollen, Links lassen sich in neuem Tab öffnen",
        "Team-Leiste unten in jedem Reiter mit Drag & Drop und „+“ auf jeder Karte",
        "Teams je Spiel speichern sich selbst, mit Level und vier Attacken je Mitglied und Verbesserungsvorschlägen",
        "Detailseite: Spielwahl, Level ohne Neuladen, eigene Attacken-Auswahl, mehr Hover-Infos",
        "Team-Ansicht: alle Filter, Gegner-Team mit bis zu sechs Pokémon",
        "Attacken: alle Attacken je Spiel inklusive Status, mehr Filter, sortierbare Spalten",
        "Typtabelle: lesbare Kopfzeile, Linien, Legende, Hervorhebung von Zeile und Spalte",
        "Offizielle Artworks in 475 × 475 zusätzlich zu den Sprites",
    ]),
    ("0.1.0", "09.11.2026", [
        "Erste Version als Dienst: Abgleich mit PokéAPI und Showdown, Liste, Detailseite, Team-Planer, Typtabelle",
    ]),
]

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
