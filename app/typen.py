"""Typwirkung je Generation und Fähigkeiten, die sie ändern. Reine Funktionen ohne Datenbank: die Tabellen
kommen als Zeilen herein (siehe abfragen.py).

Die PokéAPI führt die heutige Tabelle (type_efficacy) und frühere Werte (type_efficacy_past): Ein früherer Wert
gilt bis einschließlich seiner Generation. Typen gibt es ab ihrer Generation (Unlicht und Stahl ab 2, Fee ab 6).
"""

# Typ-IDs der PokéAPI
NORMAL, KAMPF, FLUG, GIFT, BODEN, GESTEIN, KAEFER, GEIST, STAHL, FEUER, WASSER, PFLANZE, ELEKTRO, PSYCHO, EIS, DRACHE, UNLICHT, FEE = range(1, 19)
ALL = tuple(range(1, 19))

# Fähigkeiten, die die erlittene Wirkung eines Typs ändern: {Kennung: {Typ: Faktor}}
ABILITY_DEFENSE = {
    "levitate": {BODEN: 0}, "earth-eater": {BODEN: 0},
    "flash-fire": {FEUER: 0}, "well-baked-body": {FEUER: 0},
    "water-absorb": {WASSER: 0}, "storm-drain": {WASSER: 0}, "dry-skin": {WASSER: 0, FEUER: 1.25},
    "volt-absorb": {ELEKTRO: 0}, "lightning-rod": {ELEKTRO: 0}, "motor-drive": {ELEKTRO: 0},
    "sap-sipper": {PFLANZE: 0},
    "thick-fat": {FEUER: 0.5, EIS: 0.5}, "heatproof": {FEUER: 0.5}, "water-bubble": {FEUER: 0.5},
    "purifying-salt": {GEIST: 0.5}, "fluffy": {FEUER: 2},
}


# Legenden: Arceus rechnet die Wirkung zweier Typen nicht als Produkt: doppelt sehr effektiv ist ×2,5 statt ×4, doppelt
# nicht sehr effektiv ×0,4 statt ×¼ (Quellen in docs/formeln.md). Eigentyp-Bonus dort ×1,25 statt ×1,5.
DOPPELT_LA = (2.5, 0.4)
STAB_LA = 1.25


class Chart(dict):
    """Typtabelle {Angreifer: {Verteidiger: Faktor}} mit den Regeln des Spiels: doppelt = (Faktor für doppelt sehr
    effektiv, Faktor für doppelt nicht sehr effektiv) oder None (Hauptreihe: das Produkt), stab = Eigentyp-Bonus."""
    doppelt = None
    stab = 1.5


def for_la(ch):
    """Dieselbe Tabelle mit den Regeln von Legenden: Arceus."""
    out = Chart(ch)
    out.doppelt, out.stab = DOPPELT_LA, STAB_LA
    return out


def combine(ch, f):
    """Produkt der Einzelfaktoren → Faktor im Spiel. Nur Tabellen mit eigener Regel ändern etwas."""
    dd = getattr(ch, "doppelt", None)
    if dd and f > 2:
        return dd[0]
    if dd and 0 < f < 0.5:
        return dd[1]
    return f


def product(ch, move_type, types):
    """Wirkung eines Angriffstyps gegen ein Pokémon mit diesen Typen. Die einzige Stelle, die Faktoren zusammenrechnet."""
    f = 1.0
    for d in types:
        f *= (ch.get(move_type) or {}).get(d, 1.0)
    return combine(ch, f)


def chart(efficacy, past, type_gen, gen):
    """{Angreifer: {Verteidiger: Faktor}} für eine Generation. efficacy: [(Angreifer, Verteidiger, Prozent)],
    past: [(Angreifer, Verteidiger, Prozent, bis Generation)], type_gen: {Typ: erste Generation}."""
    types = [t for t in ALL if type_gen.get(t, 1) <= gen]
    out = Chart((a, {d: 1.0 for d in types}) for a in types)
    for a, d, f in efficacy:
        if a in out and d in out[a]:
            out[a][d] = f / 100
    best = {}
    for a, d, f, until in past:
        if until >= gen and a in out and d in out[a] and (until < best.get((a, d), (99,))[0]):
            best[(a, d)] = (until, f)
    for (a, d), (_, f) in best.items():
        out[a][d] = f / 100
    return out


def defense(types, ch, ability=None):
    """{Angriffstyp: Faktor} gegen ein Pokémon mit diesen Typen, mit Fähigkeit (Kennung) eingerechnet."""
    mod = ABILITY_DEFENSE.get(ability or "", {})
    out = {}
    for a in ch:
        f = product(ch, a, types)
        if a in mod:
            f = 0.0 if mod[a] == 0 else f * mod[a]
        out[a] = f
    return out


def attack(move_type, target_types, ch):
    return product(ch, move_type, target_types)


def super_effective(move_type, ch):
    """Typen, die ein Angriff dieses Typs sehr effektiv trifft."""
    return {d for d, f in ch.get(move_type, {}).items() if f > 1}


def label(f):
    return {0: "0", 0.25: "¼", 0.4: "0,4", 0.5: "½", 1: "1", 2: "2", 2.5: "2,5", 4: "4"}.get(f, f"{f:g}")
