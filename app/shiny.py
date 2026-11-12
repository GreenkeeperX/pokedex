"""Shiny-Sperren aus Bulbapedia „List of unobtainable Shiny Pokémon“ (ohne Netz).

Die Tabelle hat je Pokémon (oder Form) eine Spalte je Generation (I und II zusammen, dann III bis IX):
{{yes}} schillernd im Spiel zu bekommen, ~ nur per Tausch oder Verteilung, {{no}} gar nicht; dahinter oft die Spiele
(„{{gameabbrev7|USUM}}“). Daraus wird je Spiel eine Stufe: „tausch“ (nur per Tausch, bleibt markierbar) oder „nie“.
"""
import re

GEN_COLS = (2, 3, 4, 5, 6, 7, 8, 9)        # Spalten der Tabelle; die erste gilt für Generation I und II

# Kürzel der Tabelle → Spielkennungen dieses Pokédex
ABBREV = {
    "RGBY": ("red-green-japan", "blue-japan", "red-blue", "yellow"), "GSC": ("gold-silver", "crystal"),
    "G": ("gold-silver",), "S": ("gold-silver",), "C": ("crystal",),
    "RSE": ("ruby-sapphire", "emerald"), "R": ("ruby-sapphire",), "E": ("emerald",), "FRLG": ("firered-leafgreen",),
    "Colo": ("colosseum",), "XD": ("xd",),
    "DPPt": ("diamond-pearl", "platinum"), "DP": ("diamond-pearl",), "D": ("diamond-pearl",), "P": ("diamond-pearl",),
    "Pt": ("platinum",), "HGSS": ("heartgold-soulsilver",), "HG": ("heartgold-soulsilver",), "SS": ("heartgold-soulsilver",),
    "BW": ("black-white",), "B": ("black-white",), "W": ("black-white",),
    "B2W2": ("black-2-white-2",), "B2": ("black-2-white-2",), "W2": ("black-2-white-2",),
    "XY": ("x-y",), "ORAS": ("omega-ruby-alpha-sapphire",), "OR": ("omega-ruby-alpha-sapphire",), "AS": ("omega-ruby-alpha-sapphire",),
    "SMUSUM": ("sun-moon", "ultra-sun-ultra-moon"), "SM": ("sun-moon",), "USUM": ("ultra-sun-ultra-moon",),
    "US": ("ultra-sun-ultra-moon",), "UM": ("ultra-sun-ultra-moon",), "PE": ("lets-go-pikachu-lets-go-eevee",),
    "SwSh": ("sword-shield", "the-isle-of-armor", "the-crown-tundra"), "IoA": ("the-isle-of-armor",), "CT": ("the-crown-tundra",),
    "BDSP": ("brilliant-diamond-shining-pearl",), "BD": ("brilliant-diamond-shining-pearl",), "SP": ("brilliant-diamond-shining-pearl",),
    "LA": ("legends-arceus",), "SV": ("scarlet-violet", "the-teal-mask", "the-indigo-disk"), "TM": ("the-teal-mask",),
    "ID": ("the-indigo-disk",), "ZA": ("legends-za",), "MD": ("mega-dimension",),
}
# Formen in <small> hinter dem Namen → Endung der Kennung in der PokéAPI; None: Zeile gilt für alle Formen der Art
FORM_SUFFIX = {"galarian form": "galar", "alolan form": "alola", "hisuian form": "hisui", "paldean form": "paldea",
               "battle bond": "battle-bond", "roaming form": "roaming", "poké ball pattern": "poke-ball", "fancy pattern": "fancy",
               "eternal flower": "eternal", "chest form": "", "bloodmoon": "bloodmoon", "all patterns": None,
               "(excluding fancy & poké ball)": None}
SPECIAL = {"cosplay pikachu": ("pikachu-cosplay", "pikachu-rock-star", "pikachu-belle", "pikachu-pop-star", "pikachu-phd", "pikachu-libre"),
           "pikachu in a cap": "cap", "partner pikachu": ("pikachu-starter",), "partner eevee": ("eevee-starter",),
           "spiky-eared pichu": ("pichu-spiky-eared",)}

_ROW = re.compile(r"^\|-[^\n]*\n", re.M)


def _plain(s):
    s = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{[ap]\|([^}|]+)\}\}", r"\1", s)
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    return s


def _cells(line_block):
    """Zellen einer Tabellenzeile („| a || b“ über mehrere Zeilen) mit colspan: [(Text, Breite)]."""
    out = []
    for line in line_block.split("\n"):
        if not line.startswith("|") or line.startswith("|-") or line.startswith("|}"):
            continue
        for c in line[1:].split("||"):
            span = 1
            m = re.match(r'\s*colspan\s*=\s*"?(\d+)"?[^|]*\|(?!\|)(.*)$', c, re.S)
            if m:
                span, c = int(m.group(1)), m.group(2)
            elif re.match(r'\s*style="[^"]*"\s*\|(?!\|)', c):
                c = c.split("|", 1)[1]
            out.append((c.strip(), span))
    return out


def _marks(cell):
    """Zelle einer Generation → [(Stufe, Kürzel oder None)]; Stufe ja / tausch / nie, None ohne Kürzel = ganze Generation."""
    out, cur = [], None
    for tok in re.finditer(r"\{\{(yes|no)\}\}|~|✔|✘|\{\{[Gg]ameabbrev[0-9a-z]*\|([^}|]+)[^}]*\}\}", cell):
        if tok.group(2):
            if cur:
                out.append((cur, tok.group(2).strip()))
            continue
        t = tok.group(1) or tok.group(0)
        cur = {"yes": "ja", "✔": "ja", "no": "nie", "✘": "nie", "~": "tausch"}[t]
        out.append((cur, None))
    # eine Stufe mit Kürzeln dahinter gilt nur für diese Spiele
    keep = []
    for i, (st, ab) in enumerate(out):
        if ab is None and i + 1 < len(out) and out[i + 1][0] == st and out[i + 1][1]:
            continue
        keep.append((st, ab))
    return keep


def parse(wikitext):
    """→ [{"name", "form", "link", "gens": {Generation: [(Stufe, Kürzel|None)]}}] aus der ersten großen Tabelle."""
    sec = wikitext.split("===Intentionally unobtainable Shiny Pokémon===", 1)[-1].split("\n|}", 1)[0]
    rows = []
    for block in _ROW.split(sec)[1:]:
        cells = _cells(block)
        if len(cells) < 3:
            continue
        name_cell = cells[1][0]
        m = re.search(r"\{\{p\|([^}|]+)", name_cell)
        link = re.search(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]", _strip_small(name_cell))
        name = m.group(1) if m else (link.group(1) if link else "")
        label = " ".join(re.sub(r"<[^>]+>", " ", _plain(name_cell)).split()).lower()
        small = re.search(r"<small>(.*?)</small>", name_cell, re.S)
        form = " ".join(_plain(small.group(1)).split()).lower() if small else ""
        gens, i = {}, 0
        for text, span in cells[2:]:
            if i >= len(GEN_COLS):
                break
            if "#999" not in text and text.strip():
                for g in GEN_COLS[i:i + span]:
                    gens[g] = _marks(text)
            i += span
        rows.append({"name": name.strip(), "form": form, "label": label, "gens": gens})
    return rows


def _strip_small(s):
    return re.sub(r"<small>.*?</small>|<ref[^>]*>.*?</ref>|<ref[^>]*/>", "", s, flags=re.S)


def _slug(name):
    s = name.lower().replace("♀", "-f").replace("♂", "-m").replace("é", "e").replace(".", "").replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9-]+", "-", s.replace(": ", "-")).strip("-")


def targets(row, forms):
    """Form-Ids einer Zeile. forms: {Kennung: (id, species_identifier, is_default)}."""
    lab = row["label"]
    for key, spec in SPECIAL.items():
        if lab.startswith(key):
            if spec == "cap":
                return [i for k, (i, _, _) in forms.items() if k.startswith("pikachu-") and k.endswith("-cap") and k != "pikachu-partner-cap"]
            return [forms[k][0] for k in spec if k in forms]
    sp = _slug(row["name"])
    if row["form"]:
        if row["form"] == "partner cap":
            return [forms["pikachu-partner-cap"][0]] if "pikachu-partner-cap" in forms else []
        if row["form"] not in FORM_SUFFIX:
            return []                                   # unbekannte Form: lieber nichts sperren
        suf = FORM_SUFFIX[row["form"]]
        if suf is None:
            return [i for k, (i, s, _) in forms.items() if s == sp]
        k = f"{sp}-{suf}" if suf else sp
        if k in forms:
            return [forms[k][0]]
        return [i for kk, (i, s, d) in forms.items() if s == sp and d] if suf == "" else []
    return [i for k, (i, s, d) in forms.items() if s == sp and d]


def locks(rows, forms, games):
    """→ {(Spiel, Form-Id): "tausch" | "nie"}. games: {Kennung: Generation}. Spiele einer Generation, die eine Zelle mit
    Kürzeln nicht nennt, gelten als „tausch“ (dort nicht direkt, vielleicht per Tausch); „ja“ sperrt nichts.
    Generation I kennt keine schillernden Pokémon: dort zählt die Spalte I/II, „ja“ wird zu „tausch“ (erst in Gen. II sichtbar)."""
    out = {}
    for row in sorted(rows, key=lambda r: FORM_SUFFIX.get(r["form"], "") is not None):   # „alle Formen“ zuerst
        ids = targets(row, forms)
        if not ids:
            continue
        for gen, marks in row["gens"].items():
            gens = (1, 2) if gen == 2 else (gen,)
            per = {}
            whole = [st for st, ab in marks if ab is None]
            named = [(st, ab) for st, ab in marks if ab]
            for g, n in games.items():
                if n not in gens:
                    continue
                st = None
                for s, ab in named:
                    if g in ABBREV.get(ab, ()):
                        st = s if st is None or s == "ja" else st
                if st is None:
                    st = whole[0] if whole else ("tausch" if named else None)
                if st is None:
                    continue
                if n == 1 and st == "ja":
                    st = "tausch"
                per[g] = st
            for g, st in per.items():
                for i in ids:
                    if st == "ja":
                        out.pop((g, i), None)
                    else:
                        out[(g, i)] = st
    return out
