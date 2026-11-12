"""PokéWiki lesen (ohne Netz): Antworten der MediaWiki-API in Seiten zerlegen und aus dem Wikitext die Werte holen,
die PokéAPI und PKHeX nicht haben.

- Attacken in Legenden: Arceus (Infobox Attacke: PLStärke, PLStärkeKraft, PLStärkeTempo, PLGenauigkeit, PLAP)
- getragene Items wilder Pokémon je Spiel (Vorlage „Getragene Items“, mit Anteil und „Nur Elite-Pokémon“)
- deutsche Texte je Spiel: Pokédex-Einträge (Vorlage „Pokédex-Einträge“), Attackenbeschreibungen („Atk-Beschreibung“),
  Fähigkeitstexte („Fähigkeit/Infobox“, Gen3 … Gen9), dazu die Forschungsaufgaben in Legenden: Arceus („Pokédex-Aufgaben“).
  Die Kürzel der Vorlagen bleiben in den Rohdaten; welche Spiele sie meinen, steht in DEX_KEYS und ATK_KEYS.

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
    out = {}
    for p in _parts(wt, name):
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _parts(wt, name):
    """Alle Teile der ersten Vorlage name (zwischen den „|“ der obersten Ebene), benannte und unbenannte."""
    m = re.search(r"\{\{\s*" + re.escape(name) + r"\s*\|", wt or "")
    if not m:
        return []
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
    return parts


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
    v = re.sub(r"\{\{\s*item\s*\|([^|}]+)[^}]*\}\}", r"\1", v, flags=re.I)     # {{Item|Sinelbeere|sp=PLA}}
    v = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", v)
    v = re.sub(r"<[^>]+>|'''|''", "", v)
    return " ".join(v.replace("&nbsp;", " ").split())


plain = _plain             # für den Import: ältere Abrufe tragen noch Vorlagen im Namen


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


# Karte der Gebiete in Legenden: Arceus (Erweiterung PwMapHisui): je Gebiet drei JSON-Dateien. Die Lage steht in
# Spielkoordinaten wie bei den Spawnpunkten (JS-Finder). ha_area01 … 05 sind die fünf Gebiete; welche Datei zu welcher
# Karte gehört, klärt importer._derive_wiki_karte über die gemeinsamen Spawnpunkte.
MAP_DATA = "https://www.pokewiki.de/extensions/PwMapHisui/data/"
MAP_AREAS = ("ha_area01", "ha_area02", "ha_area03", "ha_area04", "ha_area05")
MAP_KINDS = ("pokemon", "items")
# Art eines Pokémon-Punkts → Art des Kartensymbols (Spawnpunkte „default“ kommen schon von JS-Finder)
MAP_TYPES = {"crystal": "kristall", "wormhole": "verzerrung", "mass": "massen", "berry": "baumpkmn", "apricorn": "baumpkmn",
             "alpha": "alpha"}


def map_url(kind, area):
    return f"{MAP_DATA}{kind}/{area}.json"


def _xz(pos):
    x, _, z = str(pos).partition(",")
    return round(float(x), 2), round(float(z), 2)


def map_pokemon(text):
    """Pokémon-Datei eines Gebiets: {Name: {"x,z": {"t": Art, "LvlMin", "LvlMax", "ALvlMin", "ALvlMax", "0"…"3":
    [{"d": Anteil %, "a": Alpha-Anteil %}] je Tageszeit und Wetter}}}. Gibt [{name, x, z, typ, lv, alv, max}] zurück;
    lv und alv als (von, bis) oder None, max: höchster Anteil in % (None bei festen Alphas)."""
    out = []
    for name, pts in (json.loads(text or "{}") or {}).items():
        if not isinstance(pts, dict):
            continue
        for pos, v in pts.items():
            try:
                x, z = _xz(pos)
            except ValueError:
                continue
            lv = (int(v["LvlMin"]), int(v["LvlMax"])) if v.get("LvlMin") not in (None, "") else None
            alv = (int(v["ALvlMin"]), int(v["ALvlMax"])) if v.get("ALvlMin") not in (None, "") else None
            ds = [c.get("d") for k in ("0", "1", "2", "3") for c in (v.get(k) or []) if isinstance(c, dict) and c.get("d") is not None]
            out.append({"name": name, "x": x, "z": z, "typ": v.get("t") or "default", "lv": lv, "alv": alv,
                        "max": max(ds) if ds else None})
    return out


def map_items(text):
    """Item-Datei eines Gebiets: {Name mit Trennstrichen: [{"p": "x,z", "c": Anteil %, "u": 1}]}. Die Trennstriche
    („Apri-ko-ko“) sind Silbentrennung und fallen weg. Gibt [{name, x, z, anteil}] zurück."""
    out = []
    for name, xs in (json.loads(text or "{}") or {}).items():
        for e in xs if isinstance(xs, list) else []:
            try:
                x, z = _xz(e.get("p"))
            except (ValueError, AttributeError):
                continue
            out.append({"name": name, "x": x, "z": z, "anteil": str(e.get("c") or "")})
    return out


def item_key(name):
    """Vergleichsschlüssel für Itemnamen ohne Silbentrennung: klein, ohne Striche und Leerzeichen."""
    return re.sub(r"[\s\-­]", "", str(name or "")).lower()


# ------------------------------------------------------------------ deutsche Texte je Spiel
# Kürzel der Vorlage „Pokédex-Einträge“ → (Spiele, Edition). Groß- und Kleinschreibung zählt: „sw“ ist Schwarz/Weiß,
# „SW“ Schwert. Ein Kürzel für mehrere Spiele gilt nur, wo es kein genaueres gibt.
DEX_KEYS = {
    "rotblau": (("red-blue",), ""), "gelb": (("yellow",), ""),
    "gold": (("gold-silver",), "Gold"), "silber": (("gold-silver",), "Silber"), "crystal": (("crystal",), ""),
    "rubin": (("ruby-sapphire",), "Rubin"), "saphir": (("ruby-sapphire",), "Saphir"), "rubinsaphir": (("ruby-sapphire",), ""),
    "feuerrot": (("firered-leafgreen",), "Feuerrot"), "blattgrün": (("firered-leafgreen",), "Blattgrün"),
    "feuerrotblattgrün": (("firered-leafgreen",), ""), "smaragd": (("emerald",), ""),
    "diamond": (("diamond-pearl",), "Diamant"), "pearl": (("diamond-pearl",), "Perl"), "diamondpearl": (("diamond-pearl",), ""),
    "platinum": (("platinum",), ""), "diamondpearlplatinum": (("diamond-pearl", "platinum"), ""),
    "hg": (("heartgold-soulsilver",), "HeartGold"), "ss": (("heartgold-soulsilver",), "SoulSilver"),
    "hgss": (("heartgold-soulsilver",), ""),
    "s": (("black-white",), "Schwarz"), "w": (("black-white",), "Weiß"), "sw": (("black-white",), ""),
    "sw2": (("black-2-white-2",), ""), "s2w2": (("black-2-white-2",), ""),
    "x": (("x-y",), "X"), "y": (("x-y",), "Y"), "xy": (("x-y",), ""),
    "or": (("omega-ruby-alpha-sapphire",), "Omega Rubin"), "as": (("omega-ruby-alpha-sapphire",), "Alpha Saphir"),
    "oras": (("omega-ruby-alpha-sapphire",), ""),
    "so": (("sun-moon",), "Sonne"), "mo": (("sun-moon",), "Mond"), "somo": (("sun-moon",), ""),
    "us": (("ultra-sun-ultra-moon",), "Ultrasonne"), "um": (("ultra-sun-ultra-moon",), "Ultramond"),
    "usum": (("ultra-sun-ultra-moon",), ""), "lgpe": (("lets-go-pikachu-lets-go-eevee",), ""),
    "SW": (("sword-shield",), "Schwert"), "SH": (("sword-shield",), "Schild"), "SWSH": (("sword-shield",), ""),
    "sd": (("brilliant-diamond-shining-pearl",), "Strahlender Diamant"),
    "lp": (("brilliant-diamond-shining-pearl",), "Leuchtende Perle"), "sdlp": (("brilliant-diamond-shining-pearl",), ""),
    "pla": (("legends-arceus",), ""),
    "KA": (("scarlet-violet",), "Karmesin"), "PU": (("scarlet-violet",), "Purpur"), "KAPU": (("scarlet-violet",), ""),
    "PLZA": (("legends-za",), ""),
}
_G2, _G3 = ("gold-silver", "crystal"), ("ruby-sapphire", "emerald", "firered-leafgreen", "colosseum", "xd")
_G4, _G5 = ("diamond-pearl", "platinum", "heartgold-soulsilver"), ("black-white", "black-2-white-2")
_G6, _G7 = ("x-y", "omega-ruby-alpha-sapphire"), ("sun-moon", "ultra-sun-ultra-moon", "lets-go-pikachu-lets-go-eevee")
_G8, _G9 = ("sword-shield", "brilliant-diamond-shining-pearl", "legends-arceus"), ("scarlet-violet", "legends-za")
# Kürzel der Vorlage „Atk-Beschreibung“ (Attacken und Fähigkeiten) → Spiele; „sm“ ist hier Smaragd
ATK_KEYS = {
    "gosi": ("gold-silver",), "kr": ("crystal",), "gen2": _G2,
    "rusa": ("ruby-sapphire",), "rusasm": ("ruby-sapphire", "emerald"), "sm": ("emerald",), "frbg": ("firered-leafgreen",),
    "smfrbg": ("emerald", "firered-leafgreen"), "col": ("colosseum",), "xd": ("xd",), "gen3": _G3,
    "dp": ("diamond-pearl",), "dppt": ("diamond-pearl", "platinum"), "pt": ("platinum",), "hgss": ("heartgold-soulsilver",),
    "pthgss": ("platinum", "heartgold-soulsilver"), "gen4": _G4,
    "sw": ("black-white",), "s2w2": ("black-2-white-2",), "gen5": _G5,
    "xy": ("x-y",), "oras": ("omega-ruby-alpha-sapphire",), "gen6": _G6,
    "somo": ("sun-moon",), "usum": ("ultra-sun-ultra-moon",), "somousum": ("sun-moon", "ultra-sun-ultra-moon"),
    "usumlgpe": ("ultra-sun-ultra-moon", "lets-go-pikachu-lets-go-eevee"), "lgpe": ("lets-go-pikachu-lets-go-eevee",), "gen7": _G7,
    "swsh": ("sword-shield",), "sdlp": ("brilliant-diamond-shining-pearl",),
    "swshsdlp": ("sword-shield", "brilliant-diamond-shining-pearl"), "pla": ("legends-arceus",), "gen8": _G8,
    "kapu": ("scarlet-violet",), "plza": ("legends-za",), "gen9": _G9,
}
# Kürzel aus Spin-offs (Mystery Dungeon, Stadium, UNITE …): gehören zu keinem Hauptspiel und fallen still weg
ATK_SPINOFF = {"stadium", "stadium2", "pmd", "pmd2", "pmd3", "pmd4", "zd", "himmel", "rumble", "conquest", "spru", "psmd",
               "rblw", "quest", "masters", "pmddx", "unite", "poko", "cmp", "typ"}


def clean(v):
    """Wikitext eines Spieltexts als schlichter Text: ohne Fußnoten, Vorlagen, Links und Formatierung."""
    v = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", v or "", flags=re.S)
    v = re.sub(r"<!--.*?-->", "", v, flags=re.S)
    v = re.sub(r"<br\s*/?>", " ", v)
    v = re.sub(r"\{\{\s*Anmerkung\s*\|[^{}]*\}\}", "", v)
    for _ in range(3):          # verschachtelte Vorlagen von innen nach außen: {{tt|Text|Hinweis}} → Text
        v = re.sub(r"\{\{\s*(?:tt|item|p|a|atk|fäh|sk)\s*\|([^|{}]*)[^{}]*\}\}", r"\1", v, flags=re.I)
        v = re.sub(r"\{\{[^{}]*\}\}", "", v)
    v = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", v)
    v = re.sub(r"<[^>]+>|'''|''", "", v)
    return " ".join(v.replace("&nbsp;", " ").split())


def _texts(wt, name, skip=()):
    out = {}
    for k, v in template(wt, name).items():
        if k.lower() in skip or k.lower().startswith("typ"):
            continue
        t = clean(v)
        if t and t not in ("-", "—", "?"):
            out[k] = t
    return out


def dex_texts(wt):
    """Pokédex-Einträge der Hauptspiele: {Kürzel: Text} (die Spin-offs stehen in einer eigenen Vorlage)."""
    return _texts(wt, "Pokédex-Einträge")


def move_texts(wt):
    """Beschreibungen einer Attacke: {Kürzel: Text}."""
    return _texts(wt, "Atk-Beschreibung")


def ability_texts(wt):
    """Texte einer Fähigkeit: die Infobox trägt sie je Generation (Gen3 … Gen9 → gen3 …), die Vorlage
    „Atk-Beschreibung“ im Abschnitt Beschreibungen kann genauere Kürzel ergänzen."""
    out = {k.lower(): clean(v) for k, v in template(wt, "Fähigkeit/Infobox").items() if re.fullmatch(r"Gen\d", k)}
    out = {k: v for k, v in out.items() if v}
    out.update(move_texts(wt))
    return out


def research_tasks(wt):
    """Forschungsaufgaben in Legenden: Arceus: [{aufgabe, stufen, doppelt}]. Jede Aufgabe ist ein unbenannter Teil
    „Aufgabe/Stufe1/…/Stufe5“, doubleN=1 heißt: zählt doppelt."""
    parts = _parts(wt, "Pokédex-Aufgaben")
    named = {k.strip(): v.strip() for k, v in (p.split("=", 1) for p in parts if "=" in p)}
    out = []
    for p in parts:
        if "=" in p:
            continue
        bits = [clean(x) for x in p.split("/")]
        if not bits or not bits[0]:
            continue
        out.append({"aufgabe": bits[0], "stufen": [b for b in bits[1:] if b],
                    "doppelt": named.get(f"double{len(out) + 1}") == "1"})
    return out


def games_for(kind, key):
    """Spiele und Edition zu einem Kürzel: ((Spiele…), Edition) oder None, wenn es zu keinem Hauptspiel gehört."""
    if kind == "pokemon":
        return DEX_KEYS.get(key)
    g = ATK_KEYS.get(key) or ATK_KEYS.get(key.lower())
    return (g, "") if g else None


def unknown_keys(kind, texts):
    """Kürzel, die weder ein Hauptspiel noch ein bekanntes Spin-off sind (für das Protokoll)."""
    return sorted(k for k in texts if games_for(kind, k) is None and (kind == "pokemon" or k.lower() not in ATK_SPINOFF))


def per_game(kind, texts):
    """{Spiel: [(Edition, Text)]} aus {Kürzel: Text}. Gilt ein Kürzel für mehrere Spiele, zählt es nur dort, wo kein
    genaueres (für weniger Spiele) da ist; gleicher Text verschiedener Editionen wird zusammengefasst."""
    best = {}
    for k, t in texts.items():
        g = games_for(kind, k)
        if not g:
            continue
        games, ed = g
        for sp in games:
            cur = best.get(sp)
            if cur is None or len(games) < cur[0]:
                best[sp] = (len(games), [(ed, t)])
            elif len(games) == cur[0]:
                cur[1].append((ed, t))
    out = {}
    for sp, (_, xs) in best.items():
        merged = []
        for ed, t in xs:
            same = next((m for m in merged if m[1] == t), None)
            if same:
                same[0] = " / ".join(x for x in (same[0], ed) if x) if same[0] and ed else ""
            else:
                merged.append([ed, t])
        out[sp] = [tuple(m) for m in merged]
    return out


ZA_MISSIONS = "Missionen in Pokémon-Legenden: Z-A"


def _cell(c):
    """Zelle einer Wikitabelle: „attr | Inhalt“ → Inhalt (nur wenn links Attribute oder nichts stehen)."""
    m = re.match(r"^([^|\[{]*?)\s*\|(?!\|)\s*(.*)$", c, re.S)
    if m and (not m.group(1).strip() or "=" in m.group(1)):
        c = m.group(2)
    return "\n".join(x for x in (clean(ln) for ln in re.sub(r"<br\s*/?>", "\n", c).split("\n")) if x)


def wikitables(wt):
    """Alle Tabellen eines Wikitexts je Abschnitt: {Überschrift (Ebene 2): [[Zellen je Zeile], …]} (ohne Kopfzeilen)."""
    out, head = {}, ""
    for part in re.split(r"(?m)^(==[^=].*?==)\s*$", wt or ""):
        h = re.fullmatch(r"==\s*(.*?)\s*==", part.strip())
        if h:
            head = h.group(1)
            continue
        for tab in re.findall(r"(?ms)^\{\|.*?^\|\}", part):
            rows = []
            for row in re.split(r"(?m)^\|-.*$", tab)[1:]:
                cells, cur = [], None
                for ln in row.split("\n"):
                    if ln.startswith("|}") or ln.startswith("!") or ln.startswith("|+"):
                        cur = None
                        continue
                    if ln.startswith("|"):
                        for c in ln[1:].split("||") if "||" in ln[1:] and not ln.startswith("| |") else [ln[1:]]:
                            cells.append(c)
                        cur = len(cells) - 1
                    elif cur is not None:
                        cells[cur] += "\n" + ln
                if cells:
                    rows.append([_cell(c) for c in cells])
            out.setdefault(head, []).extend(rows)
    return out


def za_missions(wt):
    """Missionen in Legenden: Z-A aus dem PokéWiki: {"haupt": [{nr, name, text}], "dimension": [...], "neben": [{nr, name,
    beschreibung, belohnung, freischaltung}]}."""
    out = {"haupt": [], "dimension": [], "neben": []}
    for head, rows in wikitables(wt).items():
        h = head.lower()
        k = "neben" if "neben" in h else "dimension" if "dimension" in h else "haupt" if "haupt" in h else None
        if not k:
            continue
        for r in rows:
            nr = _num(r[0]) if r else None
            if nr is None or len(r) < 3:
                continue
            x = {"nr": nr, "name": r[1].replace("\n", " "), "text": r[2]}
            if k == "neben":
                x = {"nr": nr, "name": x["name"], "beschreibung": r[2].replace("\n", " "), "belohnung": (r[3] if len(r) > 3 else "").replace("\n", ", "),
                     "freischaltung": (r[4] if len(r) > 4 else "").replace("\n", " ")}
            out[k].append(x)
    return out


# ---- Trainer mit Team (Arenaleiter, Top Vier, Champs, Rivalen): Vorlagen Team/Kopf und Team/Zeile

TRAINER_CATS = {"Arenaleiter": "Arenaleiter", "Top Vier": "Top Vier", "Champ": "Champ", "Rivale": "Rivale",
                "Ort aus einem Hauptspiel": "Trainer"}
# Rolle der Ortsseiten (Routen, Höhlen, Städte): dort heißt der Trainer „Name“, „Trainername“ ist das Bild der Klasse
ORT_ROLLE = "Trainer"
# Kürzel im Parameter Edition (klein, ohne Zeichen dazwischen) → Spiele
ED_GAMES = {"rb": ["red-blue"], "gelb": ["yellow"], "g": ["yellow"], "rbg": ["red-blue", "yellow"], "gs": ["gold-silver"],
            "kristall": ["crystal"], "k": ["crystal"], "gsk": ["gold-silver", "crystal"], "rs": ["ruby-sapphire"],
            "sm": ["emerald"], "smaragd": ["emerald"], "rss": ["ruby-sapphire", "emerald"], "frbg": ["firered-leafgreen"],
            "dp": ["diamond-pearl"], "pt": ["platinum"], "platin": ["platinum"], "dppt": ["diamond-pearl", "platinum"],
            "hgss": ["heartgold-soulsilver"], "sw": ["black-white"], "s2w2": ["black-2-white-2"], "xy": ["x-y"],
            "oras": ["omega-ruby-alpha-sapphire"], "somo": ["sun-moon"], "usum": ["ultra-sun-ultra-moon"],
            "lgpe": ["lets-go-pikachu-lets-go-eevee"], "swsh": ["sword-shield"], "sdlp": ["brilliant-diamond-shining-pearl"],
            "pla": ["legends-arceus"], "kapu": ["scarlet-violet"], "plza": ["legends-za"], "col": ["colosseum"],
            "colosseum": ["colosseum"], "xd": ["xd"]}


def ed_games(code):
    """Edition einer Team-Zeile → Spiele ([] für Stadium, Anime und Unbekanntes)."""
    return list(ED_GAMES.get(re.sub(r"[^a-z0-9]", "", (code or "").lower()), []))


def category_url(cat, cont=None):
    q = {"action": "query", "list": "categorymembers", "cmtitle": "Kategorie:" + cat, "cmlimit": "500", "cmnamespace": "0",
         "format": "json", "formatversion": "2"}
    if cont:
        q["cmcontinue"] = cont
    return API + "?" + urllib.parse.urlencode(q)


def category_members(text):
    """Antwort von list=categorymembers → (Titel, Fortsetzung oder None)."""
    d = json.loads(text or "{}")
    titles = [x["title"] for x in (d.get("query") or {}).get("categorymembers") or [] if x.get("title")]
    return titles, ((d.get("continue") or {}).get("cmcontinue"))


def templates_all(wt, name):
    """Alle Vorlagen name im Wikitext in Reihenfolge: [(Position, {Parameter: Wert})]."""
    out, pos = [], 0
    pat = re.compile(r"\{\{\s*" + re.escape(name) + r"\s*\|")
    while True:
        m = pat.search(wt or "", pos)
        if not m:
            return out
        parts = _parts(wt[m.start():], name)
        p = {}
        for x in parts:
            if "=" in x:
                k, v = x.split("=", 1)
                p[k.strip()] = v.strip()
        out.append((m.start(), p))
        pos = m.end()


def _role(klasse, rolle):
    k = (klasse or "").lower()
    if "top" in k and "vier" in k:
        return "Top Vier"
    if "champ" in k:
        return "Champ"
    if "leiter" in k or "arena" in k:
        return "Arenaleiter"
    if "rival" in k:
        return "Rivale"
    return rolle


def dedupe_teams(teams):
    """Dieselben Kämpfe von Trainer- und Ortsseite nur einmal (die Trainerseite zuerst): gleiche Spiele, gleiches Team."""
    seen, out = set(), []
    for t in sorted(teams, key=lambda t: t.get("seite_rolle") == ORT_ROLLE):
        k = (tuple(sorted(t["spiele"])), tuple((m["nr"], m.get("lvl")) for m in t["team"]))
        if k not in seen:
            seen.add(k)
            t.pop("seite_rolle", None)
            out.append(t)
    return out


def trainer_teams(wt, title, rolle):
    """Teams eines Trainers aus seiner Seite: [{spiele, name, rolle, titel, hinweis, rueckkampf, team: [{nr, lvl, item,
    faehigkeit, attacken}]}]; nur Teams aus den Hauptspielen (Kürzel in ED_GAMES)."""
    heads = [(pos, clean(re.sub(r"\{\{\s*sk\s*\|[^{}]*\}\}", "", p.get("Überschrift", ""))))
             for pos, p in templates_all(wt, "Team/Kopf")]
    out = []
    for pos, p in templates_all(wt, "Team/Zeile"):
        games = ed_games(p.get("Edition"))
        if not games:
            continue
        team = []
        for n in range(1, 7):
            nr = _num(p.get(f"id{n}"))
            if not nr:
                continue
            team.append({"nr": nr, "lvl": _num(p.get(f"lvl{n}")), "item": clean(p.get(f"item{n}", "")),
                         "faehigkeit": clean(p.get(f"fähigkeit{n}", "")),
                         "attacken": [a for a in (clean(p.get(f"atk{n}_{k}", "")) for k in range(1, 5)) if a]})
        if not team:
            continue
        head = next((h for hp, h in reversed(heads) if hp < pos), "")
        if rolle == ORT_ROLLE:
            klasse, name = clean(p.get("Trainerklasse", "")), clean(p.get("Name", ""))
            name = f"{klasse} {name}".strip() if name and klasse and klasse.lower() not in name.lower() else (name or klasse)
            head = title + (f" · {head}" if head and head.lower() != "trainer" else "")
        else:
            name = clean(p.get("Trainername") or p.get("Name") or title)
        out.append({"spiele": games, "name": name or title, "seite": title, "rolle": _role(p.get("Trainerklasse"), rolle),
                    "titel": head[:160], "hinweis": clean(p.get("Hinweis", ""))[:300],
                    "rueckkampf": bool(clean(p.get("Rückkampf", ""))), "team": team, "seite_rolle": rolle})
    return out


# ---- Blaubeer-Missionen (Karmesin/Purpur: Die Indigoblaue Scheibe), Seite Blaubeer-Punkte

BBQ_PAGE = "Blaubeer-Punkte"


def _span(c):
    m = re.search(r"rowspan\s*=\s*\"?(\d+)", c.split("|")[0] if "|" in c else "")
    return int(m.group(1)) if m else 1


def bbq_missions(wt):
    """Blaubeer-Missionen aus der Tabelle der Seite Blaubeer-Punkte: [{bereich, art, text, bp}]. Die Tabelle fasst Art,
    Name und Belohnung über mehrere Zeilen zusammen (rowspan); Abschnittszeilen (Solo-, Bonus-, Gruppen-Missionen)
    stehen als eine Kopfzelle über alle Spalten."""
    m = re.search(r"==\s*Blaubeer-Missionen\s*==(.*?)(?:\n==[^=]|\Z)", wt or "", re.S)
    body = m.group(1) if m else ""
    out, bereich, carry = [], "", {}
    for tab in re.findall(r"(?ms)^\{\|.*?^\|\}", body):
        for row in re.split(r"(?m)^\|-.*$", tab)[1:]:
            cells = [ln[1:] for ln in row.split("\n") if ln[:1] in ("|", "!") and not ln.startswith("|}")]
            if len(cells) == 1 and "colspan" in cells[0]:
                bereich = _cell(cells[0])
                carry = {}
                continue
            cols, it = [], iter(cells)
            for col in range(4):
                if carry.get(col, (0,))[0] > 0:
                    n, v = carry[col]
                    carry[col] = (n - 1, v)
                    cols.append(v)
                    continue
                c = next(it, None)
                if c is None:
                    break
                v = _cell(c)
                s = _span(c)
                if s > 1:
                    carry[col] = (s - 1, v)
                cols.append(v)
            if len(cols) == 4 and cols[2]:
                bp = _num(re.sub(r"[.\s]", "", cols[3]) if cols[3] else "")
                out.append({"bereich": bereich.replace("\n", " "), "art": cols[1].replace("\n", " "), "text": cols[2].replace("\n", " "), "bp": bp})
    return out
