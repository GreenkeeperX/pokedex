"""Seiten von Serebii lesen, ohne Netz (den Abruf macht abruf._serebii):

- Legenden: Z-A, „Usable Attacks“ (legendsz-a/attacks.shtml): die Abklingzeit jeder Attacke in Sekunden
- Pokopia, Pokédex (pokemonpokopia/availablepokemon.shtml, basinpokedex.shtml, eventpokedex.shtml): Nummer, Art
  (aus dem Bild, nationale Nummer), Name und Spezialitäten

Die Leser hängen nicht an der Tabellenform: sie schneiden die Seite an den Links und Bildern, die jede Zeile hat.
"""
import html
import re

BASE = "https://www.serebii.net/"
ZA_ATTACKS = BASE + "legendsz-a/attacks.shtml"
POKOPIA = {"haupt": BASE + "pokemonpokopia/availablepokemon.shtml", "becken": BASE + "pokemonpokopia/basinpokedex.shtml",
           "event": BASE + "pokemonpokopia/eventpokedex.shtml"}
POKOPIA_DEX = {"haupt": "Pokédex", "becken": "Pokédex (Sprudelbecken)", "event": "Pokédex (Event)"}
# Spezialitäten in Pokopia (Serebii-Kennung → deutsch); Unbekanntes bleibt englisch
SPEZIAL = {"appraise": "Begutachten", "build": "Bauen", "bulldoze": "Planieren", "burn": "Anzünden", "chop": "Hacken",
           "collect": "Sammeln", "crush": "Zerkleinern", "dj": "DJ", "dreamisland": "Trauminsel", "eat": "Essen",
           "engineer": "Technik", "explode": "Sprengen", "fly": "Fliegen", "gather": "Einsammeln", "gatherhoney": "Honig sammeln",
           "generate": "Strom erzeugen", "grow": "Wachsen lassen", "hype": "Anfeuern", "illuminate": "Leuchten",
           "litter": "Fallenlassen", "paint": "Malen", "party": "Feiern", "rarify": "Veredeln", "recycle": "Wiederverwerten", "scrub": "Schrubben",
           "search": "Suchen", "storage": "Lagern", "teleport": "Teleport", "trade": "Tauschen", "transform": "Verwandeln",
           "water": "Bewässern", "yawn": "Gähnen"}       # eigene Übersetzung, die deutschen Spielnamen fehlen noch


def _text(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def key(name):
    """Vergleichsschlüssel für englische Namen: klein, nur Buchstaben und Ziffern (Aqua Jet, aqua-jet → aquajet)."""
    return re.sub(r"[^a-z0-9]", "", html.unescape(str(name or "")).lower())


_MOVE = re.compile(r'<a href="(?:https?://www\.serebii\.net)?/attackdex-[a-z0-9]+/([a-z0-9-]+)\.shtml"[^>]*>(.*?)</a>', re.S)


def za_cooldowns(page):
    """Attackenliste von Legenden: Z-A → {Schlüssel: {"name", "abkling", "staerke", "typ", "klasse"}}. Die Abklingzeit ist
    die erste ganze Zahl nach dem Namen, die Stärke die Angabe danach („--“ ohne Stärke)."""
    page = str(page or "")
    hits = [m for m in _MOVE.finditer(page) if _text(m.group(2))]
    out = {}
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else min(len(page), m.end() + 4000)
        chunk = page[m.end():end]
        cut = re.search(r"</table>", chunk)
        if cut:
            chunk = chunk[:cut.start()]
        toks = re.findall(r"--|\d+", _text(chunk))
        if not toks or toks[0] == "--":
            continue
        typ = re.search(r'/type/([a-z]+)\.gif', chunk)
        cls = re.search(r'/type/(physical|special|other)\.png', chunk)
        name = _text(m.group(2))
        out[key(m.group(1))] = {"name": name, "abkling": int(toks[0]),
                                "staerke": int(toks[1]) if len(toks) > 1 and toks[1] != "--" else None,
                                "typ": typ.group(1) if typ else "", "klasse": cls.group(1) if cls else ""}
    return out


_NR = re.compile(r">\s*#\s*(\d{3,4})\s*<")
_IMG = re.compile(r'/pokemonpokopia/pokemon/(?:small/)?(\d{3,4})(?:-([a-z0-9-]+))?\.png')
_NAME = re.compile(r'<a href="(?:https?://(?:www\.)?serebii\.net)?/pokemonpokopia/pokedex/([a-z0-9_-]+)\.shtml"[^>]*>(.*?)</a>', re.S)
_SPEZ = re.compile(r'/pokemonpokopia/pokedex/specialty/([a-z0-9_-]+)\.(?:shtml|png)')


def pokopia_dex(page):
    """Pokédex-Seite von Pokopia → [{"nr", "national", "form", "name", "seite", "spezial": [Kennungen]}] in Seitenfolge.
    Eine Zeile beginnt mit „#001“; dazu gehören Bild, Name und Spezialitäten bis zur nächsten Nummer."""
    page = str(page or "")
    starts = list(_NR.finditer(page))
    out = []
    for i, m in enumerate(starts):
        chunk = page[m.end():starts[i + 1].start() if i + 1 < len(starts) else min(len(page), m.end() + 6000)]
        img = _IMG.search(chunk)
        names = [(s, _text(n)) for s, n in _NAME.findall(chunk) if _text(n)]
        if not img or not names:
            continue
        spez = list(dict.fromkeys(_SPEZ.findall(chunk)))
        out.append({"nr": int(m.group(1)), "national": int(img.group(1)), "form": img.group(2) or "",
                    "name": names[0][1], "seite": names[0][0], "spezial": spez})
    return out


def spezial_de(k):
    return SPEZIAL.get(k, k.replace("-", " ").title())
