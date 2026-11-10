"""PokéWiki lesen (ohne Netz): Antworten der MediaWiki-API in Seiten zerlegen und aus dem Wikitext die Werte holen,
die PokéAPI und PKHeX nicht haben.

- Attacken in Legenden: Arceus (Infobox Attacke: PLStärke, PLStärkeKraft, PLStärkeTempo, PLGenauigkeit, PLAP)
- getragene Items wilder Pokémon je Spiel (Vorlage „Getragene Items“, mit Anteil und „Nur Elite-Pokémon“)

Abgerufen wird gebündelt: bis zu 50 Seiten je Anfrage (action=query, prop=revisions), siehe abruf._pokewiki.
"""
import json
import re
import urllib.parse

API = "https://www.pokewiki.de/api.php"
BATCH = 50
# Spielkürzel der Vorlage {{sk|…}} → Spielkennung; weitere Spiele, sobald ihre Kürzel geprüft sind
SK_GAMES = {"PLA": "legends-arceus"}


def batch_url(titles, section0=False):
    """Adresse für bis zu 50 Seiten auf einmal; section0: nur der Abschnitt vor der ersten Überschrift (Infobox)."""
    q = {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "format": "json",
         "formatversion": "2", "redirects": "1", "titles": "|".join(titles)}
    if section0:
        q["rvsection"] = "0"
    return API + "?" + urllib.parse.urlencode(q)


def pages(text):
    """{angefragter Titel: Wikitext} aus einer Antwort von action=query (formatversion 1 oder 2). Umleitungen und
    normalisierte Titel werden auf den angefragten Titel zurückgeführt; fehlende Seiten bleiben weg."""
    data = json.loads(text)
    if isinstance(data.get("error"), dict):
        raise ValueError(data["error"].get("info") or data["error"].get("code") or "Fehler")
    q = data.get("query") or {}
    back = {}
    for step in ("normalized", "redirects"):
        for x in q.get(step) or []:
            back[x["to"]] = back.get(x["from"], x["from"])
    ps = q.get("pages") or []
    if isinstance(ps, dict):
        ps = list(ps.values())
    out = {}
    for p in ps:
        if p.get("missing") is not None and p.get("missing") is not False:
            continue
        revs = p.get("revisions") or []
        if not revs:
            continue
        r = revs[0]
        slot = (r.get("slots") or {}).get("main") or r
        wt = slot.get("content", slot.get("*"))
        if isinstance(wt, str):
            out[back.get(p["title"], p["title"])] = wt
    return out


def template(wt, name):
    """Parameter der ersten Vorlage name im Wikitext als {Name: Wert}; verschachtelte Vorlagen bleiben im Wert."""
    m = re.search(r"\{\{\s*" + re.escape(name) + r"\s*\|", wt)
    if not m:
        return {}
    i, depth, start, parts = m.end(), 1, m.end(), []
    while i < len(wt) and depth:
        two = wt[i:i + 2]
        if two in ("{{", "[["):
            depth += 1
            i += 2
            continue
        if two in ("}}", "]]"):
            depth -= 1
            if depth == 0:
                parts.append(wt[start:i])
                break
            i += 2
            continue
        if wt[i] == "|" and depth == 1:
            parts.append(wt[start:i])
            start = i + 1
        i += 1
    out = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _num(v):
    m = re.match(r"\s*(\d+)", v or "")
    return int(m.group(1)) if m else None


def la_move(wt):
    """Werte einer Attacke in Legenden: Arceus oder None: {staerke, kraft, tempo, genauigkeit, ap}."""
    p = template(wt, "Infobox Attacke")
    keys = {"staerke": "PLStärke", "kraft": "PLStärkeKraft", "tempo": "PLStärkeTempo", "genauigkeit": "PLGenauigkeit", "ap": "PLAP"}
    if not any(k in p for k in keys.values()):
        return None
    return {k: _num(p.get(v)) for k, v in keys.items()}


def _plain(v):
    """Wikitext einer Zelle ohne Anmerkungen, Links und Formatierung."""
    v = re.sub(r"\{\{\s*Anmerkung\s*\|[^{}]*\}\}", "", v)
    v = re.sub(r"\{\{\s*item\s*\|([^|}]+)[^}]*\}\}", r"\1", v)
    v = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", v)
    v = re.sub(r"<[^>]+>|'''|''", "", v)
    return " ".join(v.replace("&nbsp;", " ").split())


def held_items(wt):
    """Getragene Items: [{spiel, item, prozent, elite}] für die Spiele aus SK_GAMES."""
    p = template(wt, "Getragene Items")
    out = []
    for k, v in p.items():
        m = re.fullmatch(r"Spiele(\d+)", k)
        if not m:
            continue
        n = m.group(1)
        games = [SK_GAMES[c] for c in re.findall(r"[A-Za-z0-9]+", re.sub(r"\{\{\s*sk\s*\||\}\}", " ", v)) if c in SK_GAMES]
        if not games:
            continue
        split = lambda s: re.split(r"<br\s*/?>", s or "")
        items, pct = split(p.get("Item" + n)), split(p.get("Prozent" + n))
        for i, raw in enumerate(items):
            name = _plain(raw)
            if not name:
                continue
            share = _plain(pct[i]) if i < len(pct) else ""
            elite = "Elite" in raw or (i < len(pct) and "Elite" in pct[i])
            for g in games:
                out.append({"spiel": g, "item": name, "prozent": share, "elite": elite})
    return out
