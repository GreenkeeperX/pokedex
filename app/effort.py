"""Effort Levels in Legenden: Arceus (ohne Netz): Werte je Stufe und was es bis zu einer Ziel-Stufe kostet.

Formeln wie in PKHeX (PA8.cs, GetStatHp, GetStat, GetGanbaruStat), das die Rechnung des Spiels nachbildet; dieselben
Formeln nennen Bulbapedia („Effort level“) und Pokébip. Das Spiel rechnet mit einfacher Genauigkeit (32 Bit); f32
bildet das nach, damit kein Wert an einer Rundungskante um 1 abweicht:
KP = ⌊(Level/100 + 1) · Basis + Level⌋ + Bonus,
andere Werte = Wesen(⌊(Level/50 + 1) · Basis / 1,5⌋) + Bonus, Wesen ganzzahlig × 110 / 100 oder × 90 / 100 (abgerundet),
Bonus = (√Basis · Faktor + Level) / 2,5, kaufmännisch gerundet; Faktor je Stufe 0–10 wie in FAKTOR.
Seit 0.57.0 wirkt das Wesen auf den abgerundeten Grundwert (vorher auf den ungerundeten: in manchen Fällen 1 zu viel).
Leistungssand, -kies, -stein und -fels heben die Stufe um eins, jedes nur in seinem Bereich (STEINE).
"""
import math
import struct

FAKTOR = (0, 2, 3, 4, 7, 8, 9, 14, 15, 16, 25)
# Leistungs-Items (Name, englisch, Stufen, auf denen es wirkt; hebt um eins)
STEINE = (("Leistungssand", "Grit Dust", (0, 1, 2)), ("Leistungskies", "Grit Gravel", (3, 4, 5)),
          ("Leistungsstein", "Grit Pebble", (6, 7, 8)), ("Leistungsfels", "Grit Rock", (9,)))
# Anfangsstufe aus den DVs (Fangen): 31 → 3, 26–30 → 2, 20–25 → 1, sonst 0
START = ((31, 3), (26, 2), (20, 1))


def f32(x):
    """Auf einfache Genauigkeit runden, wie das Spiel rechnet."""
    return struct.unpack("f", struct.pack("f", x))[0]


def bonus(base, level, el):
    x = f32(f32(f32(math.sqrt(base) * FAKTOR[el]) + level) / 2.5)
    return int(math.floor(x + 0.5))


def grund(base, level, i):
    """Grundwert ohne Bonus und ohne Wesen: KP ⌊(Level/100 + 1) · Basis + Level⌋, sonst ⌊(Level/50 + 1) · Basis / 1,5⌋."""
    if i == 0:
        return int(f32(f32(f32(f32(level / 100.0) + 1.0) * base) + level))
    return int(f32(f32(f32(f32(level / 50.0) + 1.0) * base) / 1.5))


def _wesen(x, nature):
    return 110 * x // 100 if nature > 1 else 90 * x // 100 if nature < 1 else x


def stat(base, level, el, i, nature=1.0):
    """Wert i (0 = KP) bei Basiswert, Level, Effort Level (0–10) und Wesen-Faktor (0,9 / 1 / 1,1)."""
    el = max(0, min(10, int(el)))
    if i == 0:
        return grund(base, level, 0) + bonus(base, level, el)
    return _wesen(grund(base, level, i), nature) + bonus(base, level, el)


def parts(base, level, el, i, nature=1.0):
    """Woraus ein Wert besteht (Summe = stat): Basiswert (höchstens der Grundwert), was das Level dazugibt (Grundwert
    über dem Basiswert und der Bonus bei Stufe 0), was die Effort Levels dazugeben und was das Wesen ändert (±)."""
    el = max(0, min(10, int(el)))
    g0 = grund(base, level, i)
    wesen = 0 if i == 0 else _wesen(g0, nature) - g0
    b0 = bonus(base, level, 0)
    basis = min(base, g0)
    return {"basis": basis, "level": g0 - basis + b0, "el": bonus(base, level, el) - b0, "wesen": wesen}


def start_level(iv):
    return next((el for lo, el in START if iv >= lo), 0)


def cost(von, bis):
    """Leistungs-Items von Stufe von bis Stufe bis: [Anzahl je Sorte in STEINE]."""
    out = [0] * len(STEINE)
    for s in range(max(0, von), min(10, bis)):
        out[next(k for k, (_, _, lv) in enumerate(STEINE) if s in lv)] += 1
    return out


def view(werte, level, el, ziel=None, nat_mod=None):
    """Tabelle für die Oberfläche: je Wert Basis, Stufe, Wert, Ziel, Wert am Ziel, Leistungs-Items; dazu die Summen.
    werte: sechs Basiswerte; el, ziel: sechs Stufen; nat_mod: (erhöht, gesenkt) als Werte-Index oder None."""
    el = [max(0, min(10, int(x or 0))) for x in (el or [0] * 6)][:6]
    ziel = [max(e, min(10, int(z or 0))) for e, z in zip(el, ziel or el)]
    nat = [1.0] * 6
    if nat_mod:
        nat[nat_mod[0]], nat[nat_mod[1]] = 1.1, 0.9
    rows, total = [], [0] * len(STEINE)
    for i, b in enumerate(werte):
        c = cost(el[i], ziel[i])
        total = [a + x for a, x in zip(total, c)]
        rows.append({"basis": b, "el": el[i], "wert": stat(b, level, el[i], i, nat[i]), "ziel": ziel[i],
                     "wert_ziel": stat(b, level, ziel[i], i, nat[i]), "max": stat(b, level, 10, i, nat[i]),
                     "bonbons": c, "wesen": nat[i], "teile": parts(b, level, el[i], i, nat[i]),
                     "el_ziel_teil": parts(b, level, ziel[i], i, nat[i])["el"], "faktor": FAKTOR[el[i]], "bonus": bonus(b, level, el[i])})
    return {"level": level, "rows": rows, "bonbons": total, "sorten": [s[0] for s in STEINE]}
