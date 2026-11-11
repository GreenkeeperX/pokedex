"""Schadensrechnung ab Generation 3 (Champions seit 0.22.0, alle Spiele seit 0.23.0), reine Funktionen ohne Datenbank.

Formel wie im Spiel: Grundschaden aus Level, Stärke, Angriff und Verteidigung, dann der Reihe nach Flächenattacke
(× 0,75 im Doppel), Volltreffer (× 1,5), Zufall (85 bis 100 %), Eigentyp (× 1,5, mit passendem Tera-Typ × 2),
Typwirkung. Fähigkeiten, Items, Wetter und Felder rechnen wir nicht ein; die Anzeige sagt das. Bis Generation 5 zählt ein
Volltreffer doppelt (crit_mult 2); Generation 1 und 2 rechnen anders (DV, Stat Exp, Spezial) und bleiben außen vor.
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


def rolls(level, power, atk, dfn, spread=False, crit=False, stab=1.0, eff=1.0, crit_mult=1.5):
    """Die 16 möglichen Schadenswerte (Zufall 85 bis 100 %)."""
    if not power or eff == 0:
        return [0] * 16
    base = (2 * level // 5 + 2) * power * atk // max(1, dfn) // 50 + 2
    if spread:
        base = _round(base * 0.75)
    if crit:
        base = math.floor(base * crit_mult)
    out = []
    for r in range(85, 101):
        x = base * r // 100
        x = _round(x * stab)
        x = math.floor(x * eff)
        out.append(max(1, x))
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
         a_iv=31, a_nat=1.0, d_ev=(0, 0), d_nat=1.0, spread=False, crit=False, crit_mult=1.5, d_level=None):
    """Ein Treffer: {min, max, kp, min_pct, max_pct, sicher, moeglich, eff, stab}. a_base/d_base: sechs Basiswerte;
    cls 2 = physisch (Angriff gegen Verteidigung), 3 = speziell (Spezial-Angriff gegen Spezial-Verteidigung).
    a_ev: Investition in den Angriffswert (None = voll); d_ev: (KP, Verteidigungswert); d_level: Level des Verteidigers
    (Vorgabe: wie der Angreifer)."""
    d_level = d_level or level
    ai, di = (1, 2) if cls == 2 else (3, 4)
    atk = stat(a_base[ai], level, a_iv, EV_MAX if a_ev is None else a_ev, a_nat)
    dfn = stat(d_base[di], d_level, 31, d_ev[1], d_nat)
    hp = stat(d_base[0], d_level, 31, d_ev[0], hp=True)
    st = stab_of(move_type, a_types, a_tera)
    eff = effect(ch, move_type, [d_tera] if d_tera else d_types)
    rs = rolls(level, power, atk, dfn, spread, crit, st, eff, crit_mult)
    lo, hi = rs[0], rs[-1]
    sure, maybe = hits(hp, lo, hi)
    return {"min": lo, "max": hi, "kp": hp, "min_pct": round(lo / hp * 100, 1), "max_pct": round(hi / hp * 100, 1),
            "sicher": sure, "moeglich": maybe, "eff": eff, "stab": st, "angriff": atk, "verteidigung": dfn}
