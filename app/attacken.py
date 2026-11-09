"""Attacken bewerten: Werte im gewählten Spiel, Wertung mit Gründen, Moveset aus vier Attacken.
Reine Funktionen ohne Datenbank.

Wertung = Stärke × Genauigkeit × Eigentyp-Bonus × Klassenfaktor × Zu- und Abschläge. Der Klassenfaktor ist der
genutzte Angriffswert geteilt durch den höheren der beiden; so verliert eine Spezial-Attacke bei einem
Pokémon mit Angriff 55 und Sp.-Angriff 50 kaum etwas (früher pauschal × 0,55).
"""
from . import typen

PHYS, SPEZ, STATUS = 2, 3, 1
MULTI_AVG = {(2, 5): 3.1}         # ab Generation 5: 2 und 3 Treffer je 35 %, 4 und 5 je 15 %

# Zu- und Abschläge: Faktor und Grund
RECHARGE = (0.6, "muss danach eine Runde aussetzen")
CHARGE = (0.6, "braucht eine Runde Anlauf")
SELF_DROP = (0.85, "senkt eigene Werte")
PRIO_UP = (1.1, "greift zuerst an")
PRIO_DOWN = (0.9, "greift zuletzt an")
DRAIN = (1.05, "heilt den Anwender")
SELF_KO = (0.3, "Anwender wird danach kampfunfähig")
SELF_KO_MOVES = {"explosion", "self-destruct", "misty-explosion", "memento", "final-gambit"}


def in_game(move, changes, game_order):
    """Werte einer Attacke in einem Spiel. move: dict mit typ, staerke, genauigkeit, ap, prio; changes:
    [(Reihenfolge des Spiels mit der Änderung, typ, staerke, ap, genauigkeit, prio)] aus move_changelog. Ein
    Eintrag nennt die Werte VOR der Änderung; es gilt der früheste Eintrag nach dem Spiel."""
    out = dict(move)
    for order, typ, power, pp, acc, prio in sorted(changes, reverse=True):
        if order > game_order:
            for k, v in (("typ", typ), ("staerke", power), ("ap", pp), ("genauigkeit", acc), ("prio", prio)):
                if v is not None:
                    out[k] = v
            out["geaendert"] = True
    return out


def score(move, mon, ch=None):
    """(Wertung, [Gründe]) einer Schadens-Attacke für ein Pokémon. mon: dict mit typen, ang, spang, faehigkeit.
    Ohne feste Stärke (Status, variable Stärke) → (0, [Grund])."""
    power, cls = move.get("staerke"), move.get("klasse")
    if cls == STATUS or not power or power <= 1:
        return 0.0, ["keine feste Stärke"]
    why = []
    acc = move.get("genauigkeit")
    s = power * (acc if acc else 100) / 100
    if not acc:
        why.append("trifft immer")
    hits = move.get("mehrfach")
    if hits:
        lo, hi = hits if isinstance(hits, list) else (hits, hits)
        avg = MULTI_AVG.get((lo, hi), (lo + hi) / 2)
        s *= avg
        why.append(f"trifft {lo}- bis {hi}-mal" if lo != hi else f"trifft {lo}-mal")
    if move.get("typ") in (mon.get("typen") or []):
        bonus = 2.0 if mon.get("faehigkeit") == "adaptability" else 1.5
        s *= bonus
        why.append("Eigentyp-Bonus" + (" (Anpassungsfähigkeit)" if bonus == 2 else ""))
    atk, spa = mon.get("ang") or 1, mon.get("spang") or 1
    used = atk if cls == PHYS else spa
    f = used / max(atk, spa)
    s *= f
    if f >= 0.999:
        why.append("passt zum stärkeren Angriffswert")
    else:
        why.append(f"nutzt den schwächeren Angriffswert (× {f:.2f})")
    flags = set(move.get("merkmale") or [])
    for cond, (fac, text) in (("recharge" in flags, RECHARGE), ("charge" in flags, CHARGE),
                              (any(v < 0 for k, v in (move.get("selbst") or {}).items() if k in ("atk", "spa", "def", "spd", "spe")), SELF_DROP),
                              ((move.get("prio") or 0) > 0, PRIO_UP), ((move.get("prio") or 0) < 0, PRIO_DOWN),
                              ((move.get("entzug") or 0) > 0, DRAIN), (move.get("kennung") in SELF_KO_MOVES, SELF_KO)):
        if cond:
            s *= fac
            why.append(text)
    drain = move.get("entzug") or 0
    if drain < 0:
        fac = 1 + drain / 200
        s *= fac
        why.append(f"Rückstoß ({-drain} % des Schadens)")
    return round(s, 1), why


def coverage_note(move_type, mon_types, ch):
    """Typen, die diese Attacke zusätzlich zu den Eigentypen sehr effektiv trifft."""
    own = set()
    for t in mon_types:
        own |= typen.super_effective(t, ch)
    return sorted(typen.super_effective(move_type, ch) - own)


def moveset(ranked, mon, ch, n=4):
    """Vier Attacken mit Abdeckung statt viermal derselbe Typ. ranked: [(Wertung, Attacke)] absteigend.
    Die erste ist die stärkste; jede weitere zählt nach Wertung und neu abgedeckten Typen. Gibt
    [(Attacke, Grund)] zurück."""
    pool = [(s, m) for s, m in ranked if s > 0]
    out, covered, used_types = [], set(), set()
    while pool and len(out) < n:
        best = None
        for s, m in pool:
            new = typen.super_effective(m["typ"], ch) - covered
            value = s * (0.5 + 0.5 * min(len(new), 4) / 4) * (0.35 if m["typ"] in used_types else 1)
            if best is None or value > best[0]:
                best = (value, s, m, new)
        _, s, m, new = best
        pool = [(x, y) for x, y in pool if y is not m]
        if not out:
            why = f"stark, trifft {len(new)} Typen sehr effektiv" if new else "stärkste Attacke"
        else:
            why = f"trifft neu: {len(new)} Typen" if new else "keine neue Abdeckung, aber stark"
        out.append((m, why))
        covered |= typen.super_effective(m["typ"], ch)
        used_types.add(m["typ"])
    return out
