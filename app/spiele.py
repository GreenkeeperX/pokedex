"""Spielprofile: was in welchem Spiel gilt, an einer Stelle (ohne Datenbank, ohne Netz).

Je Spiel ein Eintrag in `SPIELE`. Dort steht nur, was vom Üblichen abweicht: Das Übliche folgt aus der Generation
(`grund`), bei einer Erweiterung aus ihrem Hauptspiel. `profil(kennung)` gibt das fertige Profil mit allen Feldern aus
`FELDER`; Server und Oberfläche fragen nur noch dieses Profil, nicht mehr die Kennung des Spiels.

Ein neues Spiel: ein Eintrag in `SPIELE` (mindestens die Generation), dazu nur, was es wirklich Neues kann. Führt die
PokéAPI das Spiel nicht, legt `eigen` (Name) es beim nächsten Bau der Datenbank an. Ein Spiel der Datenbank ohne Eintrag
gilt als Hauptspiel seiner Generation und steht im Fehlerregister, bis der Eintrag da ist. Beschreibung der Felder,
wer sie liest und was offen ist: docs/spiele.md.

Was hier nicht steht: Regeln, die nur an der Generation hängen (Formel des Schadens je Generation, Typtabelle,
physisch oder speziell nach Typ), bleiben bei der Rechnung (`schaden.py`, `typen.py`); welche Seite einer Quelle zu
welchem Spiel gehört, bleibt bei der Quelle.
"""
from types import MappingProxyType

HOME = "pokemon-home"       # kein Spiel der PokéAPI: alle Pokémon mit den neuesten Werten, eigene Sammlung

# Feld → erlaubte Werte (Menge), bool oder str (eine Kennung oder leer). Die Reihenfolge ist die der Beschreibung.
FELDER = {
    "gen": int,                 # Generation: Typtabelle, Basiswerte, Formel des Schadens, Fangformel der Hauptreihe
    "hauptspiel": str,          # Erweiterung oder Schwester-Edition: Texte und Trainer kommen vom Hauptspiel; leer sonst
    "lernliste": {"eigene", "hauptspiel"},      # wessen Lernliste gilt
    "schaden": {"hauptreihe", "lgpe", "la"},    # Schadensformel: die der Generation, Let's Go (AV), Legenden: Arceus
    "typfaktoren": {"hauptreihe", "la"},        # Wirkung der Typen: ×2 und ×0,5 oder ×2,5 und ×0,4 (Eigentyp ×1,25)
    "fangformel": {"genau", "gen12", "letsgo", "legenden", "hisui", "keine"},
    "baelle": {"standard", "hisui"},            # Balltabelle
    "werte": {"dv", "ev", "av", "el", "ohne"},  # Statuswerte: DV und Stat Exp, DV und EV, DV und AV, Effort Levels, nicht gerechnet
    "faehigkeiten": bool,
    "zucht": bool,              # Eier und Pension: „Zucht“ als Weg, Ei-Gruppen und Ei-Zyklen
    "tera": bool,               # Tera-Typ je Team-Platz
    "raids": str,               # Spiel, unter dem die Tera-Raids liegen (Reiter Raids); leer ohne
    "auftraege": str,           # Schlüssel, unter dem Aufträge und ihre Haken liegen (Reiter Aufträge); leer ohne
    "blaubeer": bool,           # die Aufträge sind die Blaubeer-Missionen
    "forschung": bool,          # Forschungsaufgaben (Legenden: Arceus)
    "crypto": bool,             # Crypto-Pokémon (Colosseum, XD)
    "kampf": bool,              # Kampfspiel: Kader statt Sammlung, Reiter Kampf statt Karte, Level 50 fest, Doppelkampf
    "spawnkarten": bool,        # Einzelkarten mit Spawnpunkten, Tageszeit und Wetter
    "eigene_dexe": bool,        # eigene Pokédexe aus der Tabelle pokopia
}
# Was die Oberfläche braucht: diese Felder gibt der Server je Spiel in /api/meta mit (basis.js: PROFIL())
OBERFLAECHE = ("fangformel", "baelle", "werte", "faehigkeiten", "tera", "raids", "auftraege", "forschung", "kampf", "spawnkarten")
# Fangformel: bei diesen Werten zeigt die Tabelle nur eine Richtung (das Spiel rechnet anders als die Formel ab Generation 3)
FANG_GROB = ("gen12", "letsgo", "legenden")


def grund(gen):
    """Das Übliche einer Generation: ein Hauptspiel ohne Besonderheiten."""
    return {"gen": gen, "hauptspiel": "", "lernliste": "eigene", "schaden": "hauptreihe", "typfaktoren": "hauptreihe",
            "fangformel": "gen12" if gen <= 2 else "genau", "baelle": "standard", "werte": "dv" if gen <= 2 else "ev",
            "faehigkeiten": gen >= 3, "zucht": gen >= 2, "tera": False, "raids": "", "auftraege": "", "blaubeer": False,
            "forschung": False, "crypto": False, "kampf": False, "spawnkarten": False, "eigene_dexe": False}


_ORRE = {"zucht": False, "crypto": True}
_ERWEITERUNG_SWSH = {"hauptspiel": "sword-shield", "lernliste": "hauptspiel"}
_ERWEITERUNG_KAPU = {"hauptspiel": "scarlet-violet", "lernliste": "hauptspiel"}

# Je Spiel: die Generation und was abweicht. Eine Erweiterung (hauptspiel) übernimmt zuerst, was bei ihrem Hauptspiel steht.
# „eigen“: Name eines Spiels, das die PokéAPI nicht führt (der Importer legt es an).
SPIELE = {
    "red-green-japan": {"gen": 1, "hauptspiel": "red-blue"},
    "blue-japan": {"gen": 1, "hauptspiel": "red-blue"},
    "red-blue": {"gen": 1},
    "yellow": {"gen": 1},
    "gold-silver": {"gen": 2},
    "crystal": {"gen": 2},
    "ruby-sapphire": {"gen": 3},
    "emerald": {"gen": 3},
    "colosseum": {"gen": 3, **_ORRE},
    "xd": {"gen": 3, **_ORRE},
    "firered-leafgreen": {"gen": 3},
    "diamond-pearl": {"gen": 4},
    "platinum": {"gen": 4},
    "heartgold-soulsilver": {"gen": 4},
    "black-white": {"gen": 5},
    "black-2-white-2": {"gen": 5},
    "x-y": {"gen": 6},
    "omega-ruby-alpha-sapphire": {"gen": 6},
    "sun-moon": {"gen": 7},
    "ultra-sun-ultra-moon": {"gen": 7},
    "lets-go-pikachu-lets-go-eevee": {"gen": 7, "schaden": "lgpe", "fangformel": "letsgo", "werte": "av",
                                      "faehigkeiten": False, "zucht": False},
    "sword-shield": {"gen": 8},
    "the-isle-of-armor": {"gen": 8, **_ERWEITERUNG_SWSH},
    "the-crown-tundra": {"gen": 8, **_ERWEITERUNG_SWSH},
    "brilliant-diamond-shining-pearl": {"gen": 8},
    "legends-arceus": {"gen": 8, "schaden": "la", "typfaktoren": "la", "fangformel": "hisui", "baelle": "hisui", "werte": "el",
                       "faehigkeiten": False, "zucht": False, "auftraege": "legends-arceus", "forschung": True,
                       "spawnkarten": True},
    "scarlet-violet": {"gen": 9, "tera": True, "raids": "scarlet-violet", "auftraege": "the-indigo-disk", "blaubeer": True},
    "the-teal-mask": {"gen": 9, **_ERWEITERUNG_KAPU},
    "the-indigo-disk": {"gen": 9, **_ERWEITERUNG_KAPU},
    "legends-za": {"gen": 9, "fangformel": "legenden", "zucht": False, "auftraege": "legends-za"},
    "mega-dimension": {"gen": 9, "hauptspiel": "legends-za"},
    "champions": {"gen": 9, "fangformel": "keine", "werte": "ohne", "zucht": False, "kampf": True},
    "pokopia": {"gen": 9, "eigen": "Pokopia", "werte": "ohne", "eigene_dexe": True},
}
NEUESTE = max(e["gen"] for e in SPIELE.values())
# Spiele, die die PokéAPI (noch) nicht führt: (Kennung, Name, Generation); der Importer legt sie an
EIGENE = tuple((k, e["eigen"], e["gen"]) for k, e in SPIELE.items() if e.get("eigen"))
_fertig = {}


def bekannt(kennung):
    return kennung in SPIELE or kennung == HOME


def profil(kennung, gen=None):
    """Das Profil eines Spiels mit allen Feldern aus FELDER (nur lesen). gen: die Generation aus der Datenbank; ohne
    Angabe die des Eintrags. Ein Spiel ohne Eintrag ist ein Hauptspiel seiner Generation (ohne Angabe: der neuesten)."""
    key = (kennung, gen)
    if key not in _fertig:
        eintrag = SPIELE.get(kennung or "", {})
        p = grund(gen or eintrag.get("gen") or NEUESTE)
        haupt = SPIELE.get(eintrag.get("hauptspiel", ""), {})
        for quelle in (haupt, eintrag):
            p.update({k: v for k, v in quelle.items() if k not in ("gen", "eigen", "hauptspiel", "lernliste")})
        p.update({k: eintrag[k] for k in ("hauptspiel", "lernliste") if k in eintrag})
        _fertig[key] = MappingProxyType(p)
    return _fertig[key]


def fuer_oberflaeche(p):
    """Der Teil eines Profils, den die Oberfläche liest."""
    return {k: p[k] for k in OBERFLAECHE}


def basis(kennung):
    """Das Spiel, dessen Texte und Trainer gelten: das Hauptspiel einer Erweiterung, sonst das Spiel selbst."""
    return SPIELE.get(kennung or "", {}).get("hauptspiel") or kennung


def pruefe():
    """Fehler in SPIELE als Liste von Texten (leer: in Ordnung): unbekannte Felder und Werte, Hauptspiel ohne Eintrag,
    Erweiterung einer Erweiterung, andere Generation als das Hauptspiel."""
    out = []
    for kennung, eintrag in SPIELE.items():
        for k, v in eintrag.items():
            art = str if k == "eigen" else FELDER.get(k)
            if art is None:
                out.append(f"{kennung}: unbekanntes Feld {k}")
            elif isinstance(art, set):
                if v not in art:
                    out.append(f"{kennung}: {k} = {v!r} ist keiner von {sorted(art)}")
            elif type(v) is not art:
                out.append(f"{kennung}: {k} = {v!r} ist kein {art.__name__}")
        if not isinstance(eintrag.get("gen"), int) or eintrag["gen"] < 1:
            out.append(f"{kennung}: ohne Generation")
        haupt = eintrag.get("hauptspiel")
        if haupt is not None:
            if haupt not in SPIELE or haupt == kennung:
                out.append(f"{kennung}: Hauptspiel {haupt!r} hat keinen Eintrag")
            elif SPIELE[haupt].get("hauptspiel"):
                out.append(f"{kennung}: Hauptspiel {haupt} ist selbst eine Erweiterung")
            elif SPIELE[haupt].get("gen") != eintrag.get("gen"):
                out.append(f"{kennung}: andere Generation als das Hauptspiel {haupt}")
        elif eintrag.get("lernliste") == "hauptspiel":
            out.append(f"{kennung}: Lernliste vom Hauptspiel, aber kein Hauptspiel")
        p = profil(kennung)
        if set(p) != set(FELDER):
            out.append(f"{kennung}: Profil mit anderen Feldern als FELDER")
        if p["blaubeer"] and not p["auftraege"]:
            out.append(f"{kennung}: Blaubeer-Missionen ohne Schlüssel in auftraege")
    return out
