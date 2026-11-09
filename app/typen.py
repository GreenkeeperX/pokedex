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


def chart(efficacy, past, type_gen, gen):
    """{Angreifer: {Verteidiger: Faktor}} für eine Generation. efficacy: [(Angreifer, Verteidiger, Prozent)],
    past: [(Angreifer, Verteidiger, Prozent, bis Generation)], type_gen: {Typ: erste Generation}."""
    types = [t for t in ALL if type_gen.get(t, 1) <= gen]
    out = {a: {d: 1.0 for d in types} for a in types}
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
        f = 1.0
        for d in types:
            f *= ch[a].get(d, 1.0)
        if a in mod:
            f = 0.0 if mod[a] == 0 else f * mod[a]
        out[a] = f
    return out


def attack(move_type, target_types, ch):
    f = 1.0
    for d in target_types:
        f *= ch.get(move_type, {}).get(d, 1.0)
    return f


def super_effective(move_type, ch):
    """Typen, die ein Angriff dieses Typs sehr effektiv trifft."""
    return {d for d, f in ch.get(move_type, {}).items() if f > 1}


def label(f):
    return {0: "0", 0.25: "¼", 0.5: "½", 1: "1", 2: "2", 4: "4"}.get(f, f"{f:g}")
