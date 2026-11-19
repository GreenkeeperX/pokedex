"""Fangchance: Bälle, Formeln der Hauptreihe und von Legenden: Arceus, Balltabelle.

Teil des Pakets app.abfragen; alle Namen sind auch dort erreichbar.
"""


BALLS = (("Pokéball", 1), ("Superball", 1.5), ("Hyperball", 2))
# Bälle in Legenden: Arceus. Seit 0.57.0 die einzige Tabelle: Fangchance, Item-Liste und Oberfläche lesen sie von hier
# (über /api/meta als "hisui_baelle"); vorher standen drei Tabellen mit verschiedenen Werten nebeneinander.
# [Name, Faktor, Faktor verstärkt, wann verstärkt, Text für die Item-Liste]; Faktor 0 = fängt immer.
# Quelle: Bulbapedia „Catch rate“ (Abschnitt Legends: Arceus). Schwer-Bälle verstärkt, wenn das Pokémon dich nicht bemerkt
# hat oder im Kampf; Feder-Bälle bei fliegenden Pokémon. Federball: Die Tabelle dort nennt 0,5, der Artikel „Feather Ball“
# ×1 und ×1,25 nur bei bestimmten fliegenden Begegnungen; hier gilt der Artikel zum Ball (siehe docs/formeln.md).
HISUI_BALLS = [["Pokéball", 0.75, 0.75, "", ""], ["Superball", 1.5, 1.5, "", ""], ["Hyperball", 2.25, 2.25, "", ""],
               ["Schwerball", 1, 1.25, "unbemerkt", "×1,25, wenn das Pokémon dich nicht bemerkt hat; fliegt kurz"],
               ["Zentnerball", 1.75, 2, "unbemerkt", "×2, wenn das Pokémon dich nicht bemerkt hat"],
               ["Tonnenball", 2.5, 2.75, "unbemerkt", "×2,75, wenn das Pokémon dich nicht bemerkt hat"],
               ["Federball", 1, 1.25, "fliegt", "×1,25 bei bestimmten fliegenden Pokémon; fliegt weit"],
               ["Flügelball", 1.25, 2, "fliegt", "×2 bei fliegenden Pokémon; fliegt weiter"],
               ["Düsenball", 2, 2.75, "fliegt", "×2,75 bei fliegenden Pokémon; fliegt am weitesten"],
               ["Urball", 0, 0, "", "fängt immer"], ["Rätselball", 1, 1, "", ""]]
HISUI_NO_TABLE = ("Urball", "Rätselball")        # stehen in der Item-Liste, nicht in der Fangtabelle


def catch_chance_la(rate, ball=0.75, hp_share=1.0, status=1.0, behavior=2.0, back=1.0, berry=1.0, rank=0, outbreak=False):
    """0.50: Fangchance in % in Legenden: Arceus (Bulbapedia, Catch rate):
    a = 0,75 × Fangrate (+10 im Massenausbruch) + 30 × (Rang + KP-Faktor × Status × Ball × Verhalten × Rücken × Beere),
    Rang zwischen −5 und 0; a bis 255, b = 65535 × (1 − √(1 − a/255)), zwei Proben, eine muss gelingen."""
    hp = (3 - 2 * hp_share) / 3
    a = 0.75 * rate + (10 if outbreak else 0) + 30 * (max(-5, min(0, rank)) + hp * status * ball * behavior * back * berry)
    if a < 0:
        return 0.0
    a = min(255, a)
    b = 65535 * (1 - (1 - a / 255) ** 0.5)
    return round(100 * (1 - (1 - b / 65536) ** 2), 1)


def rank_la(level, alpha=False, player=10):
    """Rang-Term in Legenden: Arceus: Rang des Spielers − Rang des Pokémon + 1, zwischen −5 und 0. Rang des Pokémon
    ⌊(Level − 1)/10 + 1⌋, Alpha +4, höchstens 10."""
    poke = min(10, int((level - 1) / 10 + 1) + (4 if alpha else 0))
    return max(-5, min(0, player - poke + 1))
GROWTH_DE = {"slow": "langsam", "medium": "mittel", "fast": "schnell", "medium-slow": "mittel-langsam",
             "slow-then-very-fast": "erratisch", "fast-then-very-slow": "fluktuierend"}
STAT_KEYS = ("kp", "ang", "vert", "spang", "spvert", "init")


def catch_chance(rate, ball=1.0, hp_share=1.0, status=1.0, gen=9):
    """Fangchance in % (ohne kritischen Fang und Level-Boni): a = (3 − 2·KP-Anteil)/3 · Fangrate · Ball · Status; ab
    a = 255 fängt der Ball immer. Danach je Generation (Bulbapedia, „Catch rate“):
    Generation 3 und 4: b = ⌊1048560 / ⌊√⌊√⌊16711680 / a⌋⌋⌋⌋ mit ganzzahligem a (mindestens 1), vier Proben mit b/65536.
    Generation 5: b = ⌊65536 · (a/255)^0,25⌋, drei Proben. Ab Generation 6: b = ⌊65536 · (a/255)^0,1875⌋, vier Proben.
    Generation 5 und spätere kommen so beide auf (a/255)^0,75. Bis 0.56.2 rechnete Generation 5 mit dem Exponenten der
    Generation 6 und nur drei Proben (zu hoch), Generation 3 und 4 mit a/255 ohne die Rundungen des Spiels.
    Generation 1 und 2 rechnen anders; hier bleibt a/255 als Richtwert (fang_grob)."""
    return catch_steps(rate, ball, hp_share, status, gen)[0]


def catch_steps(rate, ball=1.0, hp_share=1.0, status=1.0, gen=9):
    """(Chance in %, a, b, Zahl der Proben) für den Rechenweg im Tooltip; b und Proben None, wo es keine Probe gibt
    (sicherer Fang, kein Fang, Richtwert a/255 bis Generation 2)."""
    a = (3 - 2 * hp_share) / 3 * rate * ball * status
    if a >= 255:
        return 100.0, a, None, None
    if a <= 0:
        return 0.0, a, None, None
    if gen <= 2:
        return round(100 * a / 255, 1), a, None, None
    if gen <= 4:
        b, n = catch_b_gen34(a), 4
    else:
        b, n = int(65536 * (a / 255) ** (0.25 if gen == 5 else 0.1875)), 3 if gen == 5 else 4
    return round(100 * (b / 65536) ** n, 1), a, b, n


def catch_b_gen34(a):
    """Wert b der Rüttelprobe in Generation 3 und 4: alle Divisionen und Wurzeln runden ab."""
    import math
    a = max(1, int(a))
    return min(65536, 1048560 // max(1, math.isqrt(math.isqrt(16711680 // a))))


def catch_table(rate, gen, balls=BALLS, extra=()):
    """Fangchance je Ball bei vollen KP, bei 1 KP, bei 1 KP mit Paralyse, Gift oder Verbrennung (×1,5) und bei 1 KP mit
    Schlaf oder Einfrieren (ab Generation 5 ×2,5, sonst ×2). "b" je Spalte: Wert der Rüttelprobe für den Rechenweg
    (None ohne Probe), "proben": wie viele Proben gelingen müssen."""
    sleep = sleep_factor(gen)
    out = []
    for n, f, plus, is_extra in [(n, f, 0, False) for n, f in balls] + [(n, f, plus, True) for n, f, plus in extra]:
        r = max(1, rate + plus) if is_extra else rate
        cols = {"voll": catch_steps(r, f, 1.0, 1.0, gen), "rot": catch_steps(r, f, 0, 1.0, gen),
                "status": catch_steps(r, f, 0, 1.5, gen), "schlaf": catch_steps(r, f, 0, sleep, gen)}
        row = {"ball": n, "faktor": f, **{k: v[0] for k, v in cols.items()}, "b": {k: v[2] for k, v in cols.items()},
               "proben": next((v[3] for v in cols.values() if v[3]), None)}
        if is_extra:
            row["plus"] = plus or None
        out.append(row)
    return out


MOON_SPECIES = {30, 33, 35, 39, 300, 517}          # entwickeln sich mit dem Mondstein (Nidorina, Nidorino, Piepi, Pummeluff, Eneco, Somniam)
ULTRA_BEASTS = {793, 794, 795, 796, 797, 798, 799, 803, 804, 805, 806}


def ball_rows(gen, have, f, weight_kg=None):
    """0.48.9: weitere Bälle der Hauptspiele für die Fangtabelle, nur die es im Spiel gibt (have: Namen aus der Item-Liste).
    → [(Name mit Bedingung, Faktor, Zuschlag auf die Fangrate)]. Bälle, die nur vom Pokémon abhängen (Netz-, Turbo-, Mond-,
    Schwer-, Ultraball), stehen nur da, wenn sie hier wirken; Bälle, die von der Lage abhängen, mit der Lage im Namen.
    Faktoren je Generation: Netz- und Wiederball ×3 bis Gen. 6, dann ×3,5; Finsterball ×3,5 bis Gen. 6, dann ×3;
    Flottball ×4 in Gen. 4, dann ×5; Köderball ×3 bis Gen. 6, ×5 in Gen. 7, dann ×4."""
    typen = set(f.get("typen") or [])
    out = []
    def add(name, label, fac, plus=0):
        if name in have:
            out.append((label, fac, plus))
    if typen & {7, 11}:                                     # Käfer, Wasser
        add("Netzball", "Netzball (Wasser oder Käfer)", 3 if gen <= 6 else 3.5)
    if (f.get("werte") or [0] * 6)[5] >= 100:
        add("Turboball", "Turboball (Initiative ab 100)", 4)
    if f.get("art") in MOON_SPECIES:
        add("Mondball", "Mondball (entwickelt sich mit Mondstein)", 4)
    if "Ultraball" in have:
        add("Ultraball", "Ultraball" + (" (Ultrabestie)" if f.get("art") in ULTRA_BEASTS else " (keine Ultrabestie)"),
            5 if f.get("art") in ULTRA_BEASTS else 0.1)
    if weight_kg is not None and "Schwerball" in have:
        if gen >= 7:
            plus = -20 if weight_kg < 100 else 0 if weight_kg < 200 else 20 if weight_kg < 300 else 30
        else:
            plus = -20 if weight_kg < 102.4 else 0 if weight_kg < 204.8 else 20 if weight_kg < 307.2 else 30 if weight_kg < 409.6 else 40
        add("Schwerball", f"Schwerball ({weight_kg:g} kg: Fangrate {plus:+d})".replace(".", ","), 1, plus)
    add("Tauchball", "Tauchball (Surfen, Angeln, unter Wasser)", 3.5)
    add("Finsterball", "Finsterball (nachts oder in Höhlen)", 3.5 if gen <= 6 else 3)
    add("Flottball", "Flottball (erste Runde)", 4 if gen == 4 else 5)
    add("Timerball", "Timerball (ab Runde 11)", 4)
    add("Nestball", "Nestball (wildes Pokémon Level 10)", max(1, (41 - 10) / 10 if gen >= 5 else (40 - 10) / 10))
    add("Wiederball", "Wiederball (Art schon gefangen)", 3 if gen <= 6 else 3.5)
    add("Köderball", "Köderball (geangelt)", 3 if gen <= 6 else 5 if gen == 7 else 4)
    if gen >= 8:
        add("Traumball", "Traumball (schlafend)", 4)
    add("Levelball", "Levelball (dein Pokémon mind. 4× so hohes Level)", 8)
    add("Sympaball", "Sympaball (gleiche Art, anderes Geschlecht)", 8)
    return out


def sleep_factor(gen):
    return 2.5 if gen >= 5 else 2
