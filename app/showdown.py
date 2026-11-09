"""Pokémon Showdown als zweite Quelle, ohne Netz: liest pokedex.ts und moves.ts aus dem Repository
smogon/pokemon-showdown (MIT-Lizenz).

Die Dateien sind TypeScript, aber regelmäßig aufgebaut: je Eintrag eine Zeile `\\tname: {`, darin je Feld
eine Zeile mit zwei Tabs. Gelesen werden nur einzeilige Felder; Funktionen und verschachtelte Blöcke
bleiben liegen, bis auf die Wertänderungen am Anwender (`self: { boosts: … }`).
"""
import json
import re

_ENTRY = re.compile(r"^\t([a-z0-9]+): \{\n(.*?)^\t\},?$", re.M | re.S)
_FIELD = re.compile(r"^\t\t([A-Za-z]+): (.+?),?$", re.M)
_SELF_BOOSTS = re.compile(r"^\t\tself: \{\n\t\t\tboosts: \{(.*?)\}", re.M | re.S)


def js_value(text):
    """Einfacher JavaScript-Wert (Zahl, Text, Liste, Objekt ohne Funktionen) als Python-Wert, sonst None."""
    t = text.strip()
    t = re.sub(r"'([^'\\]*)'", lambda m: json.dumps(m.group(1)), t)          # 'par' → "par"
    t = re.sub(r"([{,]\s*)([A-Za-z0-9_]+)\s*:", r'\1"\2":', t)              # { hp: 1 } → { "hp": 1 }
    t = re.sub(r",\s*([}\]])", r"\1", t)                                    # Komma vor Klammer zu
    try:
        return json.loads(t)
    except ValueError:
        return None


def entries(text):
    """{Kennung: {Feld: Wert}} aus einer Showdown-Datendatei."""
    out = {}
    for m in _ENTRY.finditer(text or ""):
        key, body = m.group(1), m.group(2)
        rec = {}
        for f in _FIELD.finditer(body):
            v = js_value(f.group(2))
            if v is not None:
                rec[f.group(1)] = v
        sb = _SELF_BOOSTS.search(body)
        if sb:
            rec["selfBoosts"] = js_value("{" + sb.group(1) + "}") or {}
        out[key] = rec
    return out


def pokedex(text):
    """Pokémon: Kennung → num, name, types, baseStats, abilities, forme, baseSpecies."""
    return {k: v for k, v in entries(text).items() if "num" in v and "baseStats" in v}


def moves(text):
    """Attacken: Kennung → num, name, type, basePower, accuracy (true = trifft immer), pp, priority, category, flags."""
    return {k: v for k, v in entries(text).items() if "num" in v and "category" in v}


def sd_id(identifier):
    """PokéAPI-Kennung in Showdown-Schreibweise: „raichu-alola“ → „raichualola“."""
    return re.sub(r"[^a-z0-9]", "", str(identifier or "").lower())
