"""Schadensrechnung je Generation, reine Funktionen ohne Datenbank. Quellen und Herleitung: docs/formeln.md.

Jede Generation rechnet in ihrer eigenen Reihenfolge und rundet an ihren eigenen Stellen (seit 0.57.0; vorher galt die
Reihenfolge ab Generation 5 für alle Spiele ab Generation 3):

- Generation 1 und 2 (rolls_old, calc_old): DV statt IV, Stat Exp statt EV, in Generation 1 ein Spezial-Wert, Zufall
  217 bis 255 von 255.
- Generation 3 (rolls_gen3): Typ-Item und Wahlband ändern den Angriffswert; Wetter, + 2, Volltreffer × 2, Eigentyp, Typ 1,
  Typ 2, zuletzt der Zufall.
- Generation 4 (rolls_gen4): Typ-Item und Techniker ändern die Stärke; durch 50 vor der Verteidigung; Wetter, + 2,
  Volltreffer × 2, Leben-Orb × 1,3, dann Zufall, Eigentyp, Typ 1, Typ 2, Expertengurt × 1,2. Alles abgerundet.
- Ab Generation 5 (rolls): Faktoren in 4096steln, gerundet „ab mehr als ,5 auf“; Volltreffer × 2 (Generation 5) oder
  × 1,5.
- Legenden: Arceus (rolls_la, calc_la): eigene Formel, Eigentyp × 1,25, Wirkung 2,5 / 2 / 0,5 / 0,4.

Die Reihenfolgen folgen smogon/damage-calc (MIT-Lizenz), nachgeschrieben, nicht übernommen; die Vergleichswerte in
tests/schaden_referenz.json stammen aus @smogon/calc 0.12.0.
"""
import math

EV_MAX = 252


def nature_amp(x, nat):
    """Wesen wie im Spiel, ganzzahlig: × 110 / 100 oder × 90 / 100, abgerundet (nat: 1,1 / 0,9 / 1)."""
    return 110 * x // 100 if nat > 1 else 90 * x // 100 if nat < 1 else x


def stat(base, level=50, iv=31, ev=0, nat=1.0, hp=False):
    """Statuswert ab Generation 3. nat: 1,1 (erhöht), 0,9 (gesenkt) oder 1."""
    core = (2 * base + iv + ev // 4) * level // 100
    if hp:
        return 1 if base == 1 else core + level + 10       # Ninjask-Hülle Ninjatom hat immer 1 KP
    return nature_amp(core + 5, nat)


def _round(x):
    """Rundung des Spiels: ab mehr als ,5 auf, sonst ab."""
    return math.ceil(x) if x - math.floor(x) > 0.5 else math.floor(x)


def _mul(x, mod):
    """x × mod / 4096, gerundet wie im Spiel (genau ,5 rundet ab). Ganzzahlig, ohne Kommazahlen."""
    q, r = divmod(x * mod, 4096)
    return q + (1 if r > 2048 else 0)


def chain(mods):
    """Mehrere Faktoren in 4096steln zu einem verketten, wie das Spiel ab Generation 5."""
    m = 4096
    for x in mods:
        if x != 4096:
            m = (m * x + 2048) >> 12
    return m


def _base(level, power, atk, dfn):
    return (2 * level // 5 + 2) * power * atk // max(1, dfn) // 50


def rolls(level, power, atk, dfn, spread=False, crit=False, stab=1.0, eff=1.0, crit_mult=1.5, weather=1.0, final=1.0):
    """Ab Generation 5: die 16 möglichen Schadenswerte (Zufall 85 bis 100 %). stab, weather und final als Faktor
    (1,5 / 2 / 2,25; 1,5 / 0,5; Produkt der Items am Schluss); gerechnet wird in 4096steln."""
    if not power or eff == 0:
        return [0] * 16
    base = _base(level, power, atk, dfn) + 2
    if spread:
        base = _mul(base, 3072)
    if weather != 1.0:
        base = _mul(base, round(weather * 4096))
    if crit:
        base = math.floor(base * crit_mult)
    st, fin = round(stab * 4096), final if isinstance(final, int) else round(final * 4096)
    out = []
    for r in range(85, 101):
        x = base * r // 100
        if st != 4096:
            x = _mul(x, st)
        x = math.floor(x * eff)
        x = _mul(x, fin) if x * fin >= 4096 else 1         # mindestens 1, dann gerundet
        out.append(max(1, x))
    return out


# Reihenfolge der Typen in Generation 3: Das Spiel prüft die Typtabelle in dieser Folge, bei zwei Typen des Ziels zählt
# also der hier frühere zuerst (das ändert das Abrunden). Typ-IDs der PokéAPI.
GEN3_ORDER = (1, 10, 11, 13, 12, 15, 2, 4, 5, 3, 14, 7, 6, 8, 16, 17, 9)


def rolls_gen3(level, power, atk, dfn, effs=(1.0,), phys=True, spread=False, crit=False, stab=False, weather=1.0):
    """Generation 3: Wetter und Fläche vor dem „+ 2“, Volltreffer × 2, Eigentyp, dann je Typ des Ziels; der Zufall
    kommt zuletzt. atk mit Item und Fähigkeit (attack_gen3), effs in der Folge von GEN3_ORDER."""
    if not power or any(e == 0 for e in effs):
        return [0] * 16
    base = _base(level, power, atk, dfn)
    if spread:
        base //= 2
    if weather != 1.0:
        base = math.floor(base * weather)
    base = (max(1, base) if phys else base) + 2
    if crit:
        base *= 2
    if stab:
        base = math.floor(base * 1.5)
    for e in effs:
        base = math.floor(base * e)
    return [max(1, base * r // 100) for r in range(85, 101)]


def rolls_gen4(level, power, atk, dfn, effs=(1.0,), spread=False, crit=False, stab=1.0, weather=1.0, orb=False, belt=False):
    """Generation 4: erst durch 50, dann durch die Verteidigung; Fläche × ¾, Wetter, + 2, Volltreffer × 2, Leben-Orb
    × 1,3; dann je Zufallswert Eigentyp (1,5 oder mit Anpassung 2), Typ 1, Typ 2, Expertengurt × 1,2. power mit Typ-Item
    und Techniker (power_gen4)."""
    if not power or any(e == 0 for e in effs):
        return [0] * 16
    base = (2 * level // 5 + 2) * power * atk // 50 // max(1, dfn)
    if spread:
        base = base * 3 // 4
    if weather != 1.0:
        base = math.floor(base * weather)
    base += 2
    if crit:
        base *= 2
    if orb:
        base = base * 13 // 10
    eff = 1.0
    for e in effs:
        eff *= e
    out = []
    for r in range(85, 101):
        x = base * r // 100
        x = math.floor(x * stab)
        for e in effs:
            x = math.floor(x * e)
        if belt and eff > 1:
            x = x * 12 // 10
        out.append(max(1, x))
    return out


def rolls_la(level, power, atk, dfn, crit=False, stab=False, eff=1.0):
    """Legenden: Arceus: ⌊⌊⌊(100 + Angriff + 15 × Level) × Stärke⌋ / (Verteidigung + 50)⌋ / 5⌋, Volltreffer × 1,5,
    Zufall 85 bis 100 %, Eigentyp × 5120/4096 (genau ,5 rundet ab), Wirkung 2,5 / 2 / 0,5 / 0,4 abgerundet.
    Nach der Zerlegung des Spiels (Version 1.1.1), siehe docs/formeln.md; „mindestens 1“ ist dort nicht belegt und
    hier wie in der Hauptreihe angenommen."""
    if not power or eff == 0:
        return [0] * 16
    base = (100 + atk + 15 * level) * power // (dfn + 50) // 5
    if crit:
        base = _mul(base, 6144)
    num, den = LA_EFF.get(eff, (None, None))
    out = []
    for r in range(85, 101):
        x = base * r // 100
        if stab:
            x = _mul(x, 5120)
        x = x * num // den if num else math.floor(x * eff)
        out.append(max(1, x))
    return out


LA_EFF = {0.4: (2, 5), 0.5: (1, 2), 1.0: (1, 1), 2.0: (2, 1), 2.5: (5, 2)}       # Wirkung als Bruch, ohne Kommazahlen
LA_STAB = 1.25


# Fähigkeiten und Items, die ohne Bedingung wirken: Kennung → (wo, Faktor, Klasse, Text, ab Generation). wo: "wert"
# (Angriffswert), "stab" (Eigentyp-Bonus), "ende" (am Schluss). Klasse 2 physisch, 3 speziell, 0 beide.
MODS = {"huge-power": ("wert", 2.0, 2, "Angriff ×2", 3), "pure-power": ("wert", 2.0, 2, "Angriff ×2", 3),
        "hustle": ("wert", 1.5, 2, "Angriff ×1,5", 3), "gorilla-tactics": ("wert", 1.5, 2, "Angriff ×1,5", 8),
        "choice-band": ("wert", 1.5, 2, "Angriff ×1,5", 3), "choice-specs": ("wert", 1.5, 3, "Sp.-Angriff ×1,5", 4),
        "adaptability": ("stab", 2.0, 0, "Eigentyp ×2", 4),
        "life-orb": ("ende", 5324 / 4096, 0, "Schaden ×1,3", 4), "expert-belt": ("ende", 4915 / 4096, 0, "sehr effektiv ×1,2", 4)}
# Leben-Orb und Expertengurt: ab Generation 5 in 4096steln (5324 und 4915, seit 0.56.1), in Generation 4 × 1,3 und × 1,2
# abgerundet und an anderer Stelle (rolls_gen4).
ORB, BELT, TYP_ITEM = 5324, 4915, 4915
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
# Generation 2: Der Drachenzahn wirkt im Spiel nicht, die Drachenhaut verstärkt stattdessen Drache (ein Fehler des
# Spiels: die Wirkungen sind vertauscht). Rosa und gepunktete Schleife verstärken Normal.
TYPE_ITEMS_GEN2 = dict({k: v for k, v in TYPE_ITEMS.items() if k != "dragon-fang"},
                       **{"dragon-scale": "dragon", "pink-bow": "normal", "polkadot-bow": "normal"})
# Items des Verteidigers: Kennung → (Klasse 2/3/0, Faktor auf die Verteidigung, Text); Evolith nur vor der Endstufe
DEF_ITEMS = {"assault-vest": (3, 1.5, "Sp.-Verteidigung ×1,5"), "eviolite": (0, 1.5, "Verteidigung ×1,5 (noch nicht voll entwickelt)")}
WEATHER = {"sonne": {"fire": 1.5, "water": 0.5}, "regen": {"water": 1.5, "fire": 0.5}}
# Fähigkeiten des Verteidigers, die einen Typ abschwächen oder verstärken (typen.ABILITY_DEFENSE): wo das Spiel den
# Faktor einrechnet. "at" = Angriffswert, "bp" = Stärke, "ende" = am Schluss. Hitzeschutz: Stärke bis Generation 8, dann Angriff.
DEF_ABILITY_WHERE = {"thick-fat": "at", "water-bubble": "at", "purifying-salt": "at", "heatproof": "bp", "dry-skin": "bp", "fluffy": "ende"}


def type_item(item, move_type, gen):
    """Faktor eines Typ-Items für diese Attacke oder 1: ×1,1 bis Generation 3 (Seerauch ×1,05), danach ×1,2."""
    table = TYPE_ITEMS_GEN2 if gen == 2 else TYPE_ITEMS
    if not item or table.get(item) != move_type:
        return 1.0
    if gen <= 3:
        return 1.05 if item == "sea-incense" else 1.1
    return 1.2


def modifiers(cls, power, move_type, eff, ability=None, item=None, weather="", gen=9):
    """Faktoren aus Fähigkeit, Item und Wetter: {"wert", "staerke", "stab", "ende", "wetter", "texte"} für die Anzeige,
    dazu was die Rechnung braucht: "faehigkeit", "item" (nur wenn sie wirken), "typ_item" (Faktor), "techniker".
    move_type als Kennung (fire …); Fähigkeiten ab Generation 3, Items ab 2, Wetter ab 2; jedes erst ab seiner Generation."""
    out = {"wert": 1.0, "staerke": 1.0, "stab": None, "ende": 1.0, "wetter": 1.0, "texte": [],
           "faehigkeit": "", "item": "", "typ_item": 1.0, "techniker": False}
    for kind, k in (("faehigkeit", ability if gen >= 3 else None), ("item", item)):
        m = MODS.get(k or "")
        if m and gen >= m[4] and m[2] in (0, cls) and not (m[0] == "ende" and k == "expert-belt" and eff <= 1):
            if m[0] == "stab":
                out["stab"] = m[1]
            else:
                out[m[0]] *= m[1]
            out[kind] = k
            out["texte"].append((kind, k, m[3]))
    if ability == TECHNICIAN and gen >= 4 and power and power <= 60:
        out["staerke"] *= 1.5
        out["techniker"] = True
        out["texte"].append(("faehigkeit", ability, "Stärke ×1,5"))
    f = type_item(item, move_type, gen)
    if f != 1.0:
        out["typ_item"] = f
        out["wert" if gen == 3 else "staerke"] *= f
        was = "Angriff" if gen == 3 else "Stärke" if gen >= 4 else "Schaden"
        out["texte"].append(("item", item, f"{was} ×{str(f).replace('.', ',')}"))
    w = (WEATHER.get(weather) or {}).get(move_type)
    if w:
        out["wetter"] = w
        out["texte"].append(("wetter", weather, f"×{str(w).replace('.', ',')}"))
    return out


def stab_of(move_type, types, tera=None, adapt=False):
    """Eigentyp-Bonus ab Generation 4 (in Generation 3 ohne Anpassung): 1,5 für einen eigenen Typ oder den Tera-Typ, 2
    wenn der Tera-Typ auch ein eigener Typ ist. Mit Anpassung (adapt): 2, und 2,25, wenn Tera-Typ, eigener Typ und Typ
    der Attacke zusammenfallen. Die Anpassung zählt nur für die Typen, die das Pokémon gerade hat (terakristallisiert:
    nur den Tera-Typ)."""
    mod = 4096
    if move_type in types:
        mod += 2048
    if tera and move_type == tera:
        mod += 2048
    if adapt and (move_type == tera if tera else move_type in types):
        mod += 1024 if tera and tera in types else 2048
    return mod / 4096


def effect(ch, move_type, types):
    from . import typen
    return typen.product(ch, move_type, types)


def hits(hp, lo, hi):
    """(sicher, möglich): so viele Treffer reichen sicher, mit Glück schon so viele (ohne Heilung)."""
    if hi <= 0:
        return None, None
    return math.ceil(hp / max(1, lo)), math.ceil(hp / hi)


def _result(rs, hp, eff, st, atk, dfn, grund, power, formel):
    lo, hi = rs[0], rs[-1]
    sure, maybe = hits(hp, lo, hi)
    return {"min": lo, "max": hi, "kp": hp, "min_pct": round(lo / hp * 100, 1), "max_pct": round(hi / hp * 100, 1),
            "sicher": sure, "moeglich": maybe, "eff": eff, "stab": st, "angriff": atk, "verteidigung": dfn, "grund": grund,
            "staerke": power, "werte": rs, "formel": formel}


def calc(level, power, cls, move_type, a_base, a_types, d_base, d_types, ch, a_tera=None, d_tera=None, a_ev=None,
         a_iv=31, a_nat=1.0, d_ev=(0, 0), d_nat=1.0, spread=False, crit=False, crit_mult=1.5, d_level=None, mods=None, d_mod=1.0,
         d_stats=None, a_stat=None, d_mult=1.0, gen=9, d_ability=None, tera_min=True):
    """Ein Treffer ab Generation 3: {min, max, kp, min_pct, max_pct, sicher, moeglich, eff, stab, werte, formel}.
    a_base/d_base: sechs Basiswerte; cls 2 = physisch (Angriff gegen Verteidigung), 3 = speziell.
    a_ev: Investition in den Angriffswert (None = voll); d_ev: (KP, Verteidigungswert); d_level: Level des Verteidigers
    (Vorgabe: wie der Angreifer); mods: modifiers(); d_mod: Faktor aus der Fähigkeit des Verteidigers (Schwebe 0 …),
    d_ability: ihre Kennung (bestimmt, wo der Faktor wirkt; ohne Kennung zählt er zur Typwirkung);
    d_stats: (Verteidigung, KP) des Verteidigers, a_stat: Angriffswert, fertig gerechnet (Spiele mit eigener Werte-Formel);
    gen: Generation des Spiels (3, 4 oder ab 5: je eigene Reihenfolge); tera_min: Attacken des Tera-Typs unter Stärke 60
    zählen mit 60 (Generation 9; der Aufrufer schaltet es für Mehrfach-Treffer und Attacken mit Erstschlag ab)."""
    from . import typen
    d_level = d_level or level
    mods = mods or {}
    ai, di = (1, 2) if cls == 2 else (3, 4)
    raw = a_stat if a_stat else stat(a_base[ai], level, a_iv, EV_MAX if a_ev is None else a_ev, a_nat)
    dfn = stat(d_base[di], d_level, 31, d_ev[1], d_nat)
    hp = stat(d_base[0], d_level, 31, d_ev[0], hp=True)
    if d_stats:
        dfn, hp = d_stats
    if d_mult != 1.0:
        dfn = math.floor(dfn * d_mult)            # Item des Verteidigers (Offensivweste, Evolith)
    ab, item = mods.get("faehigkeit", ""), mods.get("item", "")
    adapt = bool(mods.get("stab")) or ab == "adaptability"
    types = [d_tera] if d_tera else list(d_types)
    effs = [(ch.get(move_type) or {}).get(t, 1.0) for t in types] or [1.0]
    eff = typen.combine(ch, math.prod(effs))
    where = DEF_ABILITY_WHERE.get(d_ability or "") if d_mod not in (0, 1.0) else None
    if d_mod == 0:
        effs, eff = [0.0], 0.0
    elif d_mod != 1.0 and not where:
        effs, eff = effs + [d_mod], eff * d_mod              # unbekannte Fähigkeit: wie ein weiterer Typ
    huge = ab in ("huge-power", "pure-power")
    choice = item in ("choice-band", "choice-specs")
    ti = mods.get("typ_item", 1.0)
    belt = item == "expert-belt"
    weather = mods.get("wetter", 1.0)
    k = 2 * level // 5 + 2
    if gen <= 3:
        atk = raw * 2 if huge else raw
        if ti != 1.0:
            atk = math.floor(atk * ti)
        elif choice:
            atk = atk * 3 // 2
        if where:
            atk = math.floor(atk * d_mod)                     # Speckschicht halbiert in Generation 3 den Angriffswert
        if ab == "hustle":
            atk = atk * 3 // 2
        st = 1.5 if move_type in a_types else 1.0
        order = {t: i for i, t in enumerate(GEN3_ORDER)}
        if len(types) == len(effs):
            effs = [e for _, e in sorted(zip(types, effs), key=lambda te: order.get(te[0], 99))]
        rs = rolls_gen3(level, power, atk, dfn, effs, cls == 2, spread, crit, st > 1, weather)
        grund = _base(level, power, atk, dfn) if power else 0             # das „+ 2“ kommt erst nach dem Wetter
        formel = ["⌊⌊(2 × Level / 5 + 2) × Stärke × Angriff / Verteidigung⌋ / 50⌋",
                  f"⌊⌊{k} × {power} × {atk} / {dfn}⌋ / 50⌋"]
    elif gen == 4:
        bp = power
        if mods.get("techniker"):
            bp = bp * 3 // 2
        if ti != 1.0:
            bp = math.floor(bp * ti)
        if where:
            bp = math.floor(bp * d_mod)                       # Speckschicht, Hitzeschutz, Trockenheit: an der Stärke
        atk = raw * 2 if huge else raw * 3 // 2 if ab == "hustle" else raw
        if choice:
            atk = atk * 3 // 2
        st = (2.0 if adapt else 1.5) if move_type in a_types else 1.0
        rs = rolls_gen4(level, bp, atk, dfn, effs, spread, crit, st, weather, item == "life-orb", belt)
        power = bp
        grund = k * bp * atk // 50 // max(1, dfn) if bp else 0
        formel = ["⌊⌊(2 × Level / 5 + 2) × Stärke × Angriff / 50⌋ / Verteidigung⌋",
                  f"⌊⌊{k} × {bp} × {atk} / 50⌋ / {dfn}⌋"]
    else:
        bpm = [6144 if mods.get("techniker") else 4096, TYP_ITEM if ti != 1.0 else 4096]
        atm = [8192 if huge else 4096, 6144 if choice or ab == "gorilla-tactics" else 4096]
        fin = [ORB if item == "life-orb" else 4096, BELT if belt and eff > 1 else 4096]
        if where:
            w = "at" if d_ability == "heatproof" and gen >= 9 else where
            (atm if w == "at" else bpm if w == "bp" else fin).append(round(d_mod * 4096))
        bp = max(1, _mul(power, chain(bpm))) if power else power
        if gen >= 9 and tera_min and a_tera and move_type == a_tera and 0 < bp < 60:
            bp = 60                                           # Tera-Typ: mindestens Stärke 60, nach Techniker und Typ-Item
        atk = raw * 3 // 2 if ab == "hustle" else raw
        atk = max(1, _mul(atk, chain(atm)))
        st = stab_of(move_type, a_types, a_tera, adapt)
        rs = rolls(level, bp, atk, dfn, spread, crit, st, eff, crit_mult, weather, chain(fin))
        power = bp
        grund = _base(level, bp, atk, dfn) + 2 if bp else 0
        formel = ["⌊⌊(2 × Level / 5 + 2) × Stärke × Angriff / Verteidigung⌋ / 50⌋ + 2",
                  f"⌊⌊{k} × {bp} × {atk} / {dfn}⌋ / 50⌋ + 2"]
    # Anzeige: "eff" ist die Wirkung samt Fähigkeit des Verteidigers (wie bisher), "eff_typ" die der Typen allein;
    # "d_wo" sagt, wo die Fähigkeit eingerechnet ist ("at" Angriffswert, "bp" Stärke, "ende" am Schluss)
    out = _result(rs, hp, eff * d_mod if where else eff, st, atk, dfn, grund, power, formel)
    if where:
        w = "at" if gen <= 3 or (d_ability == "heatproof" and gen >= 9) else "bp" if gen == 4 else where
        out.update(eff_typ=eff, d_wo=w, d_faktor=d_mod)
    return out


def calc_la(level, power, cls, move_type, a_types, ch, d_types, a_stat, d_stats, crit=False):
    """Ein Treffer in Legenden: Arceus, Rückgabe wie calc. a_stat: Angriffswert, d_stats: (Verteidigung, KP), beide mit
    Effort Levels gerechnet (effort.stat); ch: Typtabelle des Spiels (typen.for_la). Fähigkeiten und Items gibt es
    nicht; Wetter, Statusprobleme, Stile und „Wilde Macht“ der Alpha-Pokémon sind nicht eingerechnet."""
    from . import typen
    dfn, hp = d_stats
    eff = typen.product(ch, move_type, d_types)
    stab = move_type in a_types
    rs = rolls_la(level, power, a_stat, dfn, crit, stab, eff)
    grund = (100 + a_stat + 15 * level) * power // (dfn + 50) // 5 if power else 0
    formel = ["⌊⌊(100 + Angriff + 15 × Level) × Stärke / (Verteidigung + 50)⌋ / 5⌋",
              f"⌊⌊({100 + a_stat + 15 * level}) × {power} / {dfn + 50}⌋ / 5⌋"]
    return _result(rs, hp, eff, LA_STAB if stab else 1.0, a_stat, dfn, grund, power, formel)


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
    in Generation 2 der Schaden, und zwar vor dem Typ-Item (seit 0.57.0; vorher danach). Über 255 werden Angriff und
    Verteidigung geviertelt. effs: Wirkung je Typ des Ziels; Generation 1 rundet nach jedem Typ ab, Generation 2 nimmt
    das Produkt beider Typen in einem Schritt."""
    if not power or any(e == 0 for e in effs):
        return [0] * 39
    if atk > 255 or dfn > 255:
        atk, dfn = max(1, atk // 4), max(1, dfn // 4)
    lv = level * 2 if crit and gen == 1 else level
    base = (2 * lv // 5 + 2) * power * max(1, atk) // max(1, dfn) // 50
    if crit and gen == 2:
        base *= 2
    if item != 1.0:
        base = math.floor(base * item)
    base = min(base, 997) + 2
    if weather != 1.0:
        base = math.floor(base * weather)
    if stab > 1:
        base += base // 2
    if gen == 1:
        for e in effs:
            base = math.floor(base * e)
    else:
        base = math.floor(base * math.prod(effs))
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
    a4, d4 = (max(1, atk // 4), max(1, dfn // 4)) if atk > 255 or dfn > 255 else (atk, dfn)
    lv = level * 2 if crit and gen == 1 else level
    grund = min((2 * lv // 5 + 2) * power * a4 // d4 // 50, 997) + 2 if power else 0
    eff = 1.0
    for e in effs:
        eff *= e
    k = 2 * lv // 5 + 2
    formel = ["min(⌊⌊(2 × Level / 5 + 2) × Stärke × Angriff / Verteidigung⌋ / 50⌋, 997) + 2",
              f"min(⌊⌊{k} × {power} × {a4} / {d4}⌋ / 50⌋, 997) + 2" + (" (Werte über 255: beide geviertelt)" if (a4, d4) != (atk, dfn) else "")]
    return _result(rs, hp, eff, st, atk, dfn, grund, power, formel)


# ------------------------------------------------------------------ Werte-Diagramm (alle Spiele außer Sonderformeln)

EV_TOTAL = 510


def _core(base, level, iv, ev, gen):
    """Wert vor dem Wesen ohne „+ 5“ bzw. „+ Level + 10“: ab Gen. 3 (2·Basis + IV + EV/4)·Level/100, bis Gen. 2 mit DV
    und Stat Exp wie stat_old."""
    if gen <= 2:
        return ((base + iv) * 2 + min(255, math.ceil(math.sqrt(max(0, ev)))) // 4) * level // 100
    return (2 * base + iv + ev // 4) * level // 100


def stat_parts(base, level, iv, ev, nat, i, gen):
    """Woraus ein Wert besteht (Summe = Wert): Basiswert (höchstens so viel, wie ohne IV und EV herauskommt), was das Level
    dazugibt, was IV (DV) und EV (Stat Exp) dazugeben und was das Wesen ändert (±)."""
    add = level + 10 if i == 0 else 5
    c0, ci, ce = _core(base, level, 0, 0, gen), _core(base, level, iv, 0, gen), _core(base, level, iv, ev, gen)
    grund = c0 + add
    wert = ce + add if i == 0 or gen <= 2 else nature_amp(ce + 5, nat)
    if i == 0 and base == 1:
        return {"basis": 1, "level": 0, "iv": 0, "ev": 0, "wesen": 0}, 1
    basis = min(base, grund)
    return {"basis": basis, "level": grund - basis, "iv": ci - c0, "ev": ce - ci, "wesen": wert - (ce + add)}, wert


AV_MAX = 200


def stat_lgpe(base, level, iv=31, av=0, nat=1.0, hp=False):
    """Let's Go: wie ab Gen. 3 ohne EVs, danach + AV (Punkte aus Bonbons, 0–200 je Wert). Den Freundschafts-Bonus
    (bis × 1,1) rechnen wir nicht ein."""
    core = (2 * base + iv) * level // 100
    return core + level + 10 + av if hp else nature_amp(core + 5, nat) + av


def stat_view(werte, level, gen, ivs=None, evs=None, ziel=None, nat_mod=None, lgpe=False):
    """Tabelle für das Werte-Diagramm: je Wert Basis, IV/DV, EV/Stat Exp, Wert, Ziel-EVs, Wert am Ziel, höchstens.
    Bis Generation 2 sind ivs DVs (0–15) und evs Stat Exp (0–65535), sonst IVs (0–31) und EVs (0–252, zusammen 510);
    in Let's Go (lgpe) sind evs AVs (0–200 je Wert, ohne Summengrenze)."""
    old = gen <= 2
    iv_max, ev_max = (DV_MAX, EXP_MAX) if old else (31, AV_MAX) if lgpe else (31, EV_MAX)
    clamp = lambda v, hi, d: [max(0, min(hi, int(x))) if isinstance(x, (int, float)) else d for x in (v or [d] * 6)][:6]
    ivs, evs = clamp(ivs, iv_max, iv_max), clamp(evs, ev_max, 0)
    ziel = [max(e, z) for e, z in zip(evs, clamp(ziel, ev_max, 0))] if ziel else list(evs)
    nat = [1.0] * 6
    if nat_mod and not old:
        nat[nat_mod[0]], nat[nat_mod[1]] = 1.1, 0.9
    rows = []
    parts = stat_parts
    if lgpe:
        def parts(b, lv, iv, av, n, i, g):
            t, w = stat_parts(b, lv, iv, 0, n, i, g)
            return dict(t, ev=av), w + av
    for i, b in enumerate(werte[:6]):
        t, w = parts(b, level, ivs[i], evs[i], nat[i], i, gen)
        tz, wz = parts(b, level, ivs[i], ziel[i], nat[i], i, gen)
        _, top = parts(b, level, iv_max, ev_max, max(nat[i], 1.0) if not old else 1.0, i, gen)
        rows.append({"basis": b, "iv": ivs[i], "ev": evs[i], "wert": w, "ziel": ziel[i], "wert_ziel": wz, "max": top,
                     "wesen": nat[i], "teile": t, "ev_ziel_teil": tz["ev"]})
    return {"level": level, "gen": gen, "rows": rows, "iv_max": iv_max, "ev_max": ev_max,
            "ev_summe": sum(evs), "ev_ziel_summe": sum(ziel), "ev_gesamt": None if old or lgpe else EV_TOTAL,
            "art": "lgpe" if lgpe else "alt" if old else ""}
