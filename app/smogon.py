"""Nutzungsstatistik von Smogon (ab 0.21.0), ohne Netz und ohne Datenbank.

Smogon veröffentlicht jeden Monat unter https://www.smogon.com/stats/<Monat>/ Statistiken je Format, ausführlich als
`chaos/<Format>-<Grenze>.json` (Grenze = Mindestwertung der gezählten Kämpfe). Daraus nehmen wir das passende
Doppel-Format für Champions (zuerst eines mit „champions“ im Namen, sonst die neueste VGC-Regel der Generation 9) und
kürzen es auf die häufigsten Pokémon mit ihren Attacken, Items, Fähigkeiten, Tera-Typen und Partnern.
"""
import re

INDEX = "https://www.smogon.com/stats/"
TOP = 60            # so viele Pokémon behalten
KEEP = 6            # so viele Attacken, Items … je Pokémon


def months(html):
    """Monatsordner aus der Übersicht, neuester zuerst (2026-10, 2026-10-DLC1 …)."""
    out = set(re.findall(r'href="(\d{4}-\d{2}(?:-[A-Za-z0-9]+)?)/"', html or ""))
    return sorted(out, key=lambda m: (m[:7], len(m)), reverse=True)


def chaos_files(html):
    """{Format: [Grenzen]} aus der Liste eines chaos-Ordners."""
    out = {}
    for fmt, cut in re.findall(r'href="([a-z0-9]+)-(\d+)\.json"', html or ""):
        out.setdefault(fmt, []).append(int(cut))
    return {k: sorted(v) for k, v in out.items()}


def pick(files):
    """(Format, Grenze) für die Kampfansicht oder None. Champions-Doppel vor VGC, mittlere Grenze vor der höchsten
    (mehr Kämpfe, trotzdem gute Spieler)."""
    names = sorted(files)
    champ = [n for n in names if "champions" in n and ("vgc" in n or "doubles" in n)] or [n for n in names if "champions" in n]
    vgc = [n for n in names if n.startswith("gen9vgc") and "bo3" not in n]
    fmt = (champ or vgc or [None])[-1]
    if not fmt:
        return None
    cuts = files[fmt]
    for want in (1630, 1500, 1760):
        if want in cuts:
            return fmt, want
    return fmt, max(cuts)


def _top(d, n=KEEP):
    """Die n häufigsten Einträge als [[Name, Anteil in Prozent]]; Anteile aus Gewichten."""
    if not isinstance(d, dict):
        return []
    total = sum(v for v in d.values() if isinstance(v, (int, float)) and v > 0) or 1
    xs = sorted(((k, v) for k, v in d.items() if isinstance(v, (int, float)) and v > 0 and k not in ("", "nothing", "Nothing")),
                key=lambda x: -x[1])
    return [[k, round(v / total * 100, 1)] for k, v in xs[:n]]


def digest(chaos, fmt="", cutoff=0, month=""):
    """Kurzfassung einer chaos-Datei: {format, grenze, monat, kaempfe, pokemon: [{name, anteil, attacken, items,
    faehigkeiten, tera, partner}]}. Attacken zählen je Pokémon vier Plätze; ihr Anteil ist auf das Pokémon bezogen."""
    info = (chaos or {}).get("info") or {}
    data = (chaos or {}).get("data") or {}
    rows = []
    for name, d in data.items():
        if not isinstance(d, dict):
            continue
        use = d.get("usage")
        if not isinstance(use, (int, float)) or use <= 0:
            continue
        moves = _top(d.get("Moves"), KEEP)
        for m in moves:            # vier Attacken je Pokémon: Anteil an allen Plätzen × 4
            m[1] = round(min(100.0, m[1] * 4), 1)
        rows.append({"name": name, "anteil": round(use * 100, 1), "attacken": moves, "items": _top(d.get("Items"), 3),
                     "faehigkeiten": _top(d.get("Abilities"), 2), "tera": _top(d.get("Tera Types"), 3),
                     "partner": [k for k, _ in _top(d.get("Teammates"), KEEP)]})
    rows.sort(key=lambda r: -r["anteil"])
    return {"format": fmt or info.get("metagame", ""), "grenze": cutoff or info.get("cutoff", 0), "monat": month,
            "kaempfe": info.get("number of battles", 0), "pokemon": rows[:TOP]}
