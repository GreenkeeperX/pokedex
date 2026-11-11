"""Schadensrechnung ab Generation 3 (Champions seit 0.22.0, alle Spiele seit 0.23.0), reine Funktionen ohne Datenbank.

Formel wie im Spiel: Grundschaden aus Level, Stärke, Angriff und Verteidigung, dann der Reihe nach Flächenattacke
(× 0,75 im Doppel), Volltreffer (× 1,5), Zufall (85 bis 100 %), Eigentyp (× 1,5, mit passendem Tera-Typ × 2),
Typwirkung. Seit 0.30.0 dazu häufige Fähigkeiten und Items, die immer wirken (MODS), und Sonne oder Regen; Felder und
Fähigkeiten mit Bedingung (wenig KP, Kontakt, Zusatzeffekt) nicht. Bis Generation 5 zählt ein Volltreffer doppelt
(crit_mult 2). Generation 1 und 2 rechnen anders (calc_old): DV statt IV, Stat Exp statt EV, in Generation 1 ein
Spezial-Wert, Zufall 217 bis 255 von 255.
"""
import math

EV_MAX = 252


def stat(base, level=50, iv=31, ev=0, nat=1.0, hp=False):
    """Statuswert ab Generation 3. nat: 1,1 (erhöht), 0,9 (gesenkt) oder 1."""
    core = (2 * base + iv + ev // 4) * level // 100
    if hp:
        return 1 if base == 1 else core + level + 10       # Ninjask-Hülle Ninjatom hat immer 1 KP
    return math.floor((core + 5) * nat)


def _round(x):
    """Rundung des Spiels: ab mehr als ,5 auf, sonst ab."""
    return math.ceil(x) if x - math.floor(x) > 0.5 else math.floor(x)


def rolls(level, power, atk, dfn, spread=False, crit=False, stab=1.0, eff=1.0, crit_mult=1.5, weather=1.0, final=1.0):
    """Die 16 möglichen Schadenswerte (Zufall 85 bis 100 %). weather: Sonne oder Regen; final: Items wie Leben-Orb."""
    if not power or eff == 0:
        return [0] * 16
    base = (2 * level // 5 + 2) * power * atk // max(1, dfn) // 50 + 2
    if spread:
        base = _round(base * 0.75)
    if weather != 1.0:
        base = _round(base * weather)
    if crit:
        base = math.floor(base * crit_mult)
    out = []
    for r in range(85, 101):
        x = base * r // 100
        x = _round(x * stab)
        x = math.floor(x * eff)
        if final != 1.0:
            x = _round(x * final)
        out.append(max(1, x))
    return out


# Fähigkeiten und Items, die ohne Bedingung wirken: Kennung → (wo, Faktor, Klasse, Text). wo: "wert" (Angriffswert),
# "staerke" (Stärke der Attacke), "stab" (Eigentyp-Bonus), "ende" (am Schluss). Klasse 2 physisch, 3 speziell, 0 beide.
MODS = {"huge-power": ("wert", 2.0, 2, "Angriff ×2"), "pure-power": ("wert", 2.0, 2, "Angriff ×2"),
        "hustle": ("wert", 1.5, 2, "Angriff ×1,5"), "gorilla-tactics": ("wert", 1.5, 2, "Angriff ×1,5"),
        "choice-band": ("wert", 1.5, 2, "Angriff ×1,5"), "choice-specs": ("wert", 1.5, 3, "Sp.-Angriff ×1,5"),
        "adaptability": ("stab", 2.0, 0, "Eigentyp ×2"),
        "life-orb": ("ende", 1.3, 0, "Schaden ×1,3"), "expert-belt": ("ende", 1.2, 0, "sehr effektiv ×1,2")}
TECHNICIAN = "technician"            # Techniker: Stärke bis 60 ×1,5
# Items, die einen Typ verstärken (×1,2, bis Generation 3 ×1,1): Kennung → Typ-Kennung
TYPE_ITEMS = {"charcoal": "fire", "flame-plate": "fire", "mystic-water": "water", "splash-plate": "water",
              "miracle-seed": "grass", "meadow-plate": "grass", "magnet": "electric", "zap-plate": "electric",
              "never-melt-ice": "ice", "icicle-plate": "ice", "black-belt": "fighting", "fist-plate": "fighting",
              "poison-barb": "poison", "toxic-plate": "poison", "soft-sand": "ground", "earth-plate": "ground",
              "sharp-beak": "flying", "sky-plate": "flying", "twisted-spoon": "psychic", "mind-plate": "psychic",
              "odd-incense": "psychic", "silver-powder": "bug", "insect-plate": "bug", "hard-stone": "rock",
              "stone-plate": "rock", "rock-incense": "rock", "spell-tag": "ghost", "spooky-plate": "ghost",
              "dragon-fang": "dragon", "draco-plate": "dragon", "black-glasses": "dark", "dread-plate": "dark",
              "metal-coat": "steel", "iron-plate": "steel", "silk-scarf": "normal", "pixie-plate": "fairy",
              "fairy-feather": "fairy", "sea-incense": "water", "wave-incense": "water", "rose-incense": "grass"}
WEATHER = {"sonne": {"fire": 1.5, "water": 0.5}, "regen": {"water": 1.5, "fire": 0.5}}


def modifiers(cls, power, move_type, eff, ability=None, item=None, weather="", gen=9):
    """Faktoren aus Fähigkeit, Item und Wetter: {"wert", "staerke", "stab", "ende", "wetter", "texte"}. move_type als
    Kennung (fire …); Fähigkeiten erst ab Generation 3, Items ab 2, Wetter ab 2."""
    out = {"wert": 1.0, "staerke": 1.0, "stab": None, "ende": 1.0, "wetter": 1.0, "texte": []}
    for kind, k in (("faehigkeit", ability if gen >= 3 else None), ("item", item)):
        m = MODS.get(k or "")
        if m and m[2] in (0, cls) and not (m[0] == "ende" and k == "expert-belt" and eff <= 1):
            if m[0] == "stab":
                out["stab"] = m[1]
            else:
                out[m[0]] *= m[1]
            out["texte"].append((kind, k, m[3]))
    if ability == TECHNICIAN and gen >= 4 and power and power <= 60:
        out["staerke"] *= 1.5
        out["texte"].append(("faehigkeit", ability, "Stärke ×1,5"))
    if item and TYPE_ITEMS.get(item) == move_type:
        f = 1.1 if gen <= 3 else 1.2
        out["staerke"] *= f
        out["texte"].append(("item", item, f"{'Stärke' if gen >= 4 else 'Schaden'} ×{str(f).replace('.', ',')}"))
    w = (WEATHER.get(weather) or {}).get(move_type)
    if w:
        out["wetter"] = w
        out["texte"].append(("wetter", weather, f"×{str(w).replace('.', ',')}"))
    return out


def stab_of(move_type, types, tera=None):
    """Eigentyp-Bonus: 1,5 für einen eigenen Typ oder den Tera-Typ, 2 wenn der Tera-Typ auch ein eigener Typ ist."""
    if tera and move_type == tera:
        return 2.0 if tera in types else 1.5
    return 1.5 if move_type in types else 1.0


def effect(ch, move_type, types):
    f = 1.0
    for t in types:
        f *= (ch.get(move_type) or {}).get(t, 1.0)
    return f


def hits(hp, lo, hi):
    """(sicher, möglich): so viele Treffer reichen sicher, mit Glück schon so viele (ohne Heilung)."""
    if hi <= 0:
        return None, None
    return math.ceil(hp / max(1, lo)), math.ceil(hp / hi)


def calc(level, power, cls, move_type, a_base, a_types, d_base, d_types, ch, a_tera=None, d_tera=None, a_ev=None,
         a_iv=31, a_nat=1.0, d_ev=(0, 0), d_nat=1.0, spread=False, crit=False, crit_mult=1.5, d_level=None, mods=None, d_mod=1.0):
    """Ein Treffer: {min, max, kp, min_pct, max_pct, sicher, moeglich, eff, stab}. a_base/d_base: sechs Basiswerte;
    cls 2 = physisch (Angriff gegen Verteidigung), 3 = speziell (Spezial-Angriff gegen Spezial-Verteidigung).
    a_ev: Investition in den Angriffswert (None = voll); d_ev: (KP, Verteidigungswert); d_level: Level des Verteidigers
    (Vorgabe: wie der Angreifer); mods: modifiers(); d_mod: Faktor aus der Fähigkeit des Verteidigers (Schwebe 0 …)."""
    d_level = d_level or level
    mods = mods or {}
    ai, di = (1, 2) if cls == 2 else (3, 4)
    atk = math.floor(stat(a_base[ai], level, a_iv, EV_MAX if a_ev is None else a_ev, a_nat) * mods.get("wert", 1.0))
    dfn = stat(d_base[di], d_level, 31, d_ev[1], d_nat)
    hp = stat(d_base[0], d_level, 31, d_ev[0], hp=True)
    st = stab_of(move_type, a_types, a_tera)
    if st > 1 and mods.get("stab"):
        st = max(st, mods["stab"])
    eff = effect(ch, move_type, [d_tera] if d_tera else d_types) * d_mod
    power = _round(power * mods.get("staerke", 1.0)) if power else power
    rs = rolls(level, power, atk, dfn, spread, crit, st, eff, crit_mult, mods.get("wetter", 1.0), mods.get("ende", 1.0))
    lo, hi = rs[0], rs[-1]
    sure, maybe = hits(hp, lo, hi)
    return {"min": lo, "max": hi, "kp": hp, "min_pct": round(lo / hp * 100, 1), "max_pct": round(hi / hp * 100, 1),
            "sicher": sure, "moeglich": maybe, "eff": eff, "stab": st, "angriff": atk, "verteidigung": dfn}


# ------------------------------------------------------------------ Generation 1 und 2

DV_MAX = 15
EXP_MAX = 65535


def stat_old(base, level=50, dv=DV_MAX, exp=EXP_MAX, hp=False):
    """Statuswert in Generation 1 und 2: ((Basis + DV) · 2 + ⌈√Stat Exp⌉ / 4) · Level / 100 + 5, KP + Level + 10.
    Die Wurzel kappt das Spiel bei 255, volle Stat Exp gibt also 63."""
    core = ((base + dv) * 2 + min(255, math.ceil(math.sqrt(max(0, exp)))) // 4) * level // 100
    return core + level + 10 if hp else core + 5


def rolls_old(gen, level, power, atk, dfn, crit=False, stab=1.0, effs=(1.0,), item=1.0, weather=1.0):
    """Die 39 möglichen Schadenswerte (Zufall 217 bis 255 von 255). Volltreffer: in Generation 1 zählt das Level doppelt,
    in Generation 2 der Schaden. Über 255 werden Angriff und Verteidigung geviertelt. effs: Wirkung je Typ des Ziels."""
    if not power or any(e == 0 for e in effs):
        return [0] * 39
    if atk > 255 or dfn > 255:
        atk, dfn = max(1, atk // 4), max(1, dfn // 4)
    lv = level * 2 if crit and gen == 1 else level
    base = (2 * lv // 5 + 2) * power * atk // max(1, dfn) // 50
    if item != 1.0:
        base = math.floor(base * item)
    if crit and gen == 2:
        base *= 2
    base = min(base, 997) + 2
    if weather != 1.0:
        base = math.floor(base * weather)
    if stab > 1:
        base += base // 2
    for e in effs:
        base = math.floor(base * e)
    if base == 1:
        return [1] * 39
    return [max(1, base * r // 255) for r in range(217, 256)]


def calc_old(gen, level, power, cls, move_type, a_base, a_types, d_base, d_types, ch, crit=False, d_inv=(0, 0),
             d_level=None, a_exp=EXP_MAX, a_dv=DV_MAX, item=1.0, weather=1.0):
    """Ein Treffer in Generation 1 oder 2, Rückgabe wie calc. Basiswerte wie in der Generation (in Generation 1 Spezial an
    Stelle 3 und 4). d_inv: Stat Exp der Verteidiger in (KP, Verteidigung), 0 oder voll; DVs immer 15."""
    d_level = d_level or level
    ai, di = (1, 2) if cls == 2 else (3, 4)
    if gen == 1 and cls != 2:
        ai = di = 3
    atk = stat_old(a_base[ai], level, a_dv, a_exp)
    dfn = stat_old(d_base[di], d_level, DV_MAX, EXP_MAX if d_inv[1] else 0)
    hp = stat_old(d_base[0], d_level, DV_MAX, EXP_MAX if d_inv[0] else 0, hp=True)
    st = 1.5 if move_type in a_types else 1.0
    effs = [(ch.get(move_type) or {}).get(t, 1.0) for t in d_types]
    rs = rolls_old(gen, level, power, atk, dfn, crit, st, effs or [1.0], item, weather)
    lo, hi = rs[0], rs[-1]
    sure, maybe = hits(hp, lo, hi)
    eff = 1.0
    for e in effs:
        eff *= e
    return {"min": lo, "max": hi, "kp": hp, "min_pct": round(lo / hp * 100, 1), "max_pct": round(hi / hp * 100, 1),
            "sicher": sure, "moeglich": maybe, "eff": eff, "stab": st, "angriff": atk, "verteidigung": dfn}
