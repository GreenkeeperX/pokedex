"""Teams im Textformat von Pokémon Showdown (auch PokePaste), ohne Datenbank.

Ein Set sieht so aus (Leerzeile zwischen den Sets):

    Spitzname (Knakrack) (M) @ Wahlschal        ← in Showdown mit englischen Namen
    Ability: Rough Skin
    Level: 50
    Shiny: Yes
    Tera Type: Fire
    EVs: 252 Atk / 4 SpD / 252 Spe
    Jolly Nature
    IVs: 0 SpA
    - Earthquake
    - Outrage

`parse` liefert die Namen so, wie sie dastehen; das Zuordnen zu Kennungen macht `abfragen.paste_import`.
"""
import re

STATS = ("hp", "atk", "def", "spa", "spd", "spe")
_STAT_IN = {"hp": "hp", "atk": "atk", "def": "def", "spa": "spa", "spd": "spd", "spe": "spe",
            "kp": "hp", "ang": "atk", "vert": "def", "spang": "spa", "spvert": "spd", "init": "spe"}
_STAT_OUT = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}
MAX_SETS = 24


def _spread(text, default):
    """„252 Atk / 4 SpD“ → Liste in der Reihenfolge von STATS, fehlende mit default."""
    out = [default] * 6
    for part in text.split("/"):
        m = re.fullmatch(r"\s*(\d{1,3})\s+([A-Za-z]+)\s*", part)
        if m and m.group(2).lower() in _STAT_IN:
            out[STATS.index(_STAT_IN[m.group(2).lower()])] = min(int(m.group(1)), 255)
    return out


def _head(line):
    """Erste Zeile → (Spitzname, Art, Geschlecht, Item)."""
    item = ""
    if " @ " in line:
        line, item = line.rsplit(" @ ", 1)
    line = line.strip()
    gender = ""
    m = re.search(r"\s\((M|F)\)$", line)
    if m:
        gender, line = m.group(1), line[:m.start()].rstrip()
    nick = ""
    m = re.fullmatch(r"(.+?)\s\(([^()]+)\)", line)
    if m:
        nick, line = m.group(1).strip(), m.group(2).strip()
    return nick, line.strip(), gender, item.strip()


def parse(text):
    """Text → [{name, spitzname, geschlecht, item, faehigkeit, level, schillernd, tera, evs, ivs, wesen, attacken}]."""
    sets = []
    for block in re.split(r"\n\s*\n", str(text or "").replace("\r", "")):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip() and not ln.strip().startswith("===")]
        if not lines:
            continue
        nick, name, gender, item = _head(lines[0])
        if not name:
            continue
        s = {"name": name[:60], "spitzname": nick[:30], "geschlecht": gender, "item": item[:60], "faehigkeit": "", "level": None,
             "schillernd": False, "tera": "", "evs": None, "ivs": None, "wesen": "", "attacken": []}
        for ln in lines[1:]:
            key, _, val = ln.partition(":")
            k, val = key.strip().lower(), val.strip()
            if ln.startswith("-"):
                mv = ln.lstrip("-–").strip()
                if mv and len(s["attacken"]) < 4:
                    s["attacken"].append(mv[:60])
            elif k == "ability":
                s["faehigkeit"] = val[:60]
            elif k == "level" and val.isdigit():
                s["level"] = max(1, min(int(val), 100))
            elif k == "shiny":
                s["schillernd"] = val.lower() == "yes"
            elif k == "tera type":
                s["tera"] = val[:20]
            elif k == "evs":
                s["evs"] = _spread(val, 0)
            elif k == "ivs":
                s["ivs"] = _spread(val, 31)
            elif re.fullmatch(r"[A-Za-z]+ Nature", ln):
                s["wesen"] = ln.split()[0]
        sets.append(s)
        if len(sets) >= MAX_SETS:
            break
    return sets


def dump(sets):
    """[{name, spitzname?, geschlecht?, item?, faehigkeit?, level?, schillernd?, tera?, evs?, ivs?, wesen?, attacken}] → Text."""
    out = []
    for s in sets:
        head = s["name"]
        if s.get("spitzname") and s["spitzname"] != s["name"]:
            head = f'{s["spitzname"]} ({head})'
        if s.get("geschlecht") in ("M", "F"):
            head += f' ({s["geschlecht"]})'
        if s.get("item"):
            head += f' @ {s["item"]}'
        lines = [head]
        if s.get("faehigkeit"):
            lines.append(f'Ability: {s["faehigkeit"]}')
        if s.get("level") and s["level"] != 100:
            lines.append(f'Level: {s["level"]}')
        if s.get("schillernd"):
            lines.append("Shiny: Yes")
        if s.get("tera"):
            lines.append(f'Tera Type: {s["tera"]}')
        evs = [f"{v} {_STAT_OUT[k]}" for k, v in zip(STATS, s.get("evs") or []) if v]
        if evs:
            lines.append("EVs: " + " / ".join(evs))
        if s.get("wesen"):
            lines.append(f'{s["wesen"]} Nature')
        ivs = [f"{v} {_STAT_OUT[k]}" for k, v in zip(STATS, s.get("ivs") or []) if v != 31]
        if ivs:
            lines.append("IVs: " + " / ".join(ivs))
        lines += [f"- {m}" for m in s.get("attacken") or []]
        out.append("\n".join(lines))
    return "\n\n".join(out) + ("\n" if out else "")
