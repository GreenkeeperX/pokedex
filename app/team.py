"""Teams bewerten, ergänzen, das beste Team suchen und gegen einen Gegner aufstellen. Reine Funktionen.

Ein Mitglied ist ein dict mit id, art, name, typen, werte (KP, Ang, Vert, SpAng, SpVert, Init), summe und
optional faehigkeit (Kennung) und angriffstypen (Typen seiner Attacken; sonst die Eigentypen).

Sechs Kriterien, jedes zwischen 0 und 1, dann gewichtet (Gewichte frei einstellbar, Presets siehe PRESETS):
- defensive: offene Schwächen (mehr Mitglieder schwach als resistent), 4-fach-Schwächen zählen extra
- abdeckung: Anteil der Typen, die das Team sehr effektiv trifft
- tempo: Mitglieder mit Initiative ab der Schwelle (Standard 90) von sechs Plätzen
- staerke: Basiswerte, je Platz bis 600 gezählt
- balance: physische und spezielle Angreifer gemischt, keine doppelten Typen
"""
from . import typen

CRITERIA = ("defensive", "abdeckung", "tempo", "staerke", "balance")
CRIT_DE = {"defensive": "Defensive", "abdeckung": "Abdeckung", "tempo": "Tempo", "staerke": "Stärke", "balance": "Balance"}
PRESETS = {
    "ausgewogen": {"defensive": 3, "abdeckung": 3, "tempo": 1, "staerke": 2, "balance": 1},
    "verteidigung": {"defensive": 6, "abdeckung": 1, "tempo": 1, "staerke": 1, "balance": 1},
    "angriff": {"defensive": 1, "abdeckung": 6, "tempo": 2, "staerke": 1, "balance": 1},
    "staerke": {"defensive": 1, "abdeckung": 1, "tempo": 1, "staerke": 6, "balance": 0},
    "tempo": {"defensive": 1, "abdeckung": 2, "tempo": 6, "staerke": 1, "balance": 0},
}
SIZE = 6
PENALTY_MAX = 12.0
SPEED = 90


def weights_of(w):
    w = dict(PRESETS["ausgewogen"], **{k: float(v) for k, v in (w or {}).items() if k in CRITERIA})
    return {k: max(0.0, min(10.0, w[k])) for k in CRITERIA}


class Ctx:
    """Vorberechnet je Mitglied: erlittene Faktoren und sehr effektiv getroffene Typen."""

    def __init__(self, ch, speed=SPEED):
        self.ch, self.speed, self._d, self._o = ch, speed, {}, {}

    def dvec(self, m):
        k = m["id"]
        if k not in self._d:
            self._d[k] = typen.defense(m["typen"], self.ch, m.get("faehigkeit"))
        return self._d[k]

    def ovec(self, m):
        k = m["id"]
        if k not in self._o:
            hit = set()
            for t in m.get("angriffstypen") or m["typen"]:
                hit |= typen.super_effective(t, self.ch)
            self._o[k] = hit
        return self._o[k]


def evaluate(members, ctx, weights=None):
    """Wertung (0 bis 100), Kriterien (je 0 bis 1) und Befunde eines Teams."""
    w = weights_of(weights)
    types = list(ctx.ch)
    open_t, four, immune = [], [], []
    penalty = 0.0
    for a in types:
        weak = res = 0
        for m in members:
            f = ctx.dvec(m)[a]
            if f > 1:
                weak += 1
            elif f < 1:
                res += 1
            if f >= 4:
                four.append((a, m["name"]))
            if f == 0:
                immune.append((a, m["name"]))
        if weak > res:
            open_t.append(a)
            penalty += weak - res
    penalty += 0.5 * len(four)
    covered = set()
    for m in members:
        covered |= ctx.ovec(m)
    fast = [m for m in members if (m["werte"][5] or 0) >= ctx.speed]
    phys = sum(1 for m in members if m["werte"][1] >= m["werte"][3])
    spez = len(members) - phys
    seen, dup = set(), 0
    for m in members:
        for t in m["typen"]:
            dup += t in seen
            seen.add(t)
    crit = {
        "defensive": max(0.0, 1 - penalty / PENALTY_MAX) if members else 0.0,
        "abdeckung": len(covered) / len(types),
        "tempo": len(fast) / SIZE,
        "staerke": sum(min(m["summe"], 600) for m in members) / (SIZE * 600),
        "balance": max(0.0, 1 - abs(phys - spez) / SIZE - 0.1 * dup) if members else 0.0,
    }
    total = sum(w[k] * crit[k] for k in CRITERIA) / (sum(w.values()) or 1) * 100
    return {"wertung": round(total, 1), "kriterien": {k: round(v, 3) for k, v in crit.items()},
            "offen": open_t, "vierfach": four, "immun": immune, "abgedeckt": sorted(covered),
            "nicht_abgedeckt": [t for t in types if t not in covered], "schnell": [m["name"] for m in fast],
            "physisch": phys, "speziell": spez}


def reasons(before, after, cand, tname):
    """Was ein Kandidat am Team ändert, in Worten."""
    out = []
    closed = [t for t in before["offen"] if t not in after["offen"]]
    if closed:
        out.append("schließt offene Schwäche gegen " + ", ".join(tname(t) for t in closed))
    opened = [t for t in after["offen"] if t not in before["offen"]]
    if opened:
        out.append("öffnet neu: " + ", ".join(tname(t) for t in opened))
    new = [t for t in after["abgedeckt"] if t not in before["abgedeckt"]]
    if new:
        out.append("trifft zusätzlich " + ", ".join(tname(t) for t in new))
    if len(after["schnell"]) > len(before["schnell"]):
        out.append(f"schnell (Initiative {cand['werte'][5]})")
    if before["speziell"] == 0 and after["speziell"] > 0:
        out.append("erster Spezial-Angreifer")
    elif before["physisch"] == 0 and after["physisch"] > 0:
        out.append("erster physischer Angreifer")
    if not out:
        out.append(f"Basiswerte {cand['summe']}")
    return out


def suggest(team, pool, ctx, weights=None, n=10, tname=str):
    """Beste nächste Ergänzung: jeder Kandidat probeweise im Team, gerankt nach dem Zuwachs der Wertung."""
    base = evaluate(team, ctx, weights)
    species = {m["art"] for m in team}
    out = []
    for c in pool:
        if c["art"] in species:
            continue
        ev = evaluate(team + [c], ctx, weights)
        out.append((ev["wertung"] - base["wertung"], c, ev))
    out.sort(key=lambda x: (-x[0], -x[1]["summe"], x[1]["id"]))
    return [{"id": c["id"], "plus": round(d, 1), "wertung": ev["wertung"], "gruende": reasons(base, ev, c, tname)}
            for d, c, ev in out[:n]]


def prefilter(pool, ctx, keep=120, per_typing=3):
    """Pool vorab eingrenzen: je Typkombination die stärksten, davon die besten nach Basiswerten."""
    by = {}
    for c in sorted(pool, key=lambda c: (-c["summe"], c["id"])):
        k = tuple(sorted(c["typen"]))
        if len(by.setdefault(k, [])) < per_typing:
            by[k].append(c)
    flat = [c for cs in by.values() for c in cs]
    flat.sort(key=lambda c: (-c["summe"], c["id"]))
    return flat[:keep]


def optimize(pool, ctx, weights=None, fixed=(), size=SIZE, beam=20, keep=120):
    """Bestes Team: Strahlsuche Platz für Platz, danach ein Tauschdurchgang. fixed bleiben gesetzt.
    Gibt bis zu drei Teams [(Wertung, [Mitglieder])] zurück, das beste zuerst."""
    fixed = list(fixed)[:size]
    fixed_ids = {m["id"] for m in fixed}
    cands = [c for c in prefilter(pool, ctx, keep) if c["id"] not in fixed_ids]
    states = [(evaluate(fixed, ctx, weights)["wertung"], fixed)]
    for _ in range(size - len(fixed)):
        nxt, seen = [], set()
        for _, team in states:
            species = {m["art"] for m in team}
            for c in cands:
                if c["art"] in species:
                    continue
                key = frozenset([m["id"] for m in team] + [c["id"]])
                if key in seen:
                    continue
                seen.add(key)
                t2 = team + [c]
                nxt.append((evaluate(t2, ctx, weights)["wertung"], t2))
        if not nxt:
            break
        nxt.sort(key=lambda x: (-x[0], [m["id"] for m in x[1]]))
        states = nxt[:beam]
    best = []
    for sc, team in states[:3]:
        improved = True
        rounds = 0
        while improved and rounds < 3:
            improved, rounds = False, rounds + 1
            for i in range(len(fixed), len(team)):
                species = {m["art"] for j, m in enumerate(team) if j != i}
                for c in cands:
                    if c["art"] in species or any(c["id"] == m["id"] for m in team):
                        continue
                    t2 = team[:i] + [c] + team[i + 1:]
                    s2 = evaluate(t2, ctx, weights)["wertung"]
                    if s2 > sc + 1e-9:
                        sc, team, improved = s2, t2, True
                        species = {m["art"] for j, m in enumerate(team) if j != i}
        if not any({m["id"] for m in team} == {m["id"] for m in t} for _, t in best):
            best.append((sc, team))
    best.sort(key=lambda x: -x[0])
    return best[:3]


def matchup(team, enemy, ctx, tname=str):
    """Wer im Team gegen einen Gegner passt. enemy: dict mit typen, optional angriffstypen und init.
    Je Mitglied: erlittener Faktor (schlimmster Angriffstyp des Gegners), ausgeteilter Faktor (bester eigener
    Angriffstyp), Tempo-Vergleich. Sortiert: wer am meisten austeilt und am wenigsten einsteckt."""
    atk_types = enemy.get("angriffstypen") or enemy["typen"]
    out = []
    for m in team:
        d = ctx.dvec(m)
        taken = max(d[t] for t in atk_types) if atk_types else 1.0
        own = m.get("angriffstypen") or m["typen"]
        dealt, best_t = max(((typen.attack(t, enemy["typen"], ctx.ch), t) for t in own), default=(1.0, None))
        faster = None if enemy.get("init") is None else (m["werte"][5] > enemy["init"])
        sc = dealt / max(taken, 0.125) * (1.15 if faster else 1.0)
        why = []
        if dealt > 1:
            why.append(f"trifft sehr effektiv mit {tname(best_t)} (× {typen.label(dealt)})")
        elif dealt < 1:
            why.append(f"trifft nur schwach (× {typen.label(dealt)})")
        if taken == 0:
            why.append("immun gegen die Angriffe des Gegners")
        elif taken < 1:
            why.append(f"steckt wenig ein (× {typen.label(taken)})")
        elif taken > 1:
            why.append(f"steckt viel ein (× {typen.label(taken)})")
        if faster is True:
            why.append("schneller als der Gegner")
        elif faster is False:
            why.append("langsamer als der Gegner")
        verdict = "schicken" if sc >= 2 else "schonen" if sc < 0.75 else "geht"
        out.append({"id": m["id"], "wertung": round(sc, 2), "urteil": verdict, "gruende": why,
                    "austeilen": dealt, "einstecken": taken})
    out.sort(key=lambda x: -x["wertung"])
    return out
