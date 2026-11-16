"""Teams für Doppelkämpfe bewerten (Champions und die offiziellen Turniere). Reine Funktionen ohne Datenbank.

Ein Mitglied ist ein dict mit name, typen, init (Basiswert), faehigkeit (Kennung oder None), attacken (gewählte
Attacken als dicts mit kennung, name, typ, ziel, schaden) und lernbar ({Kennung: Name} der Rollen-Attacken, die es lernen kann).

Bewertet werden Rollen, die im Doppel zählen (je eine Attacke oder Fähigkeit reicht), Flächenattacken und ob sie den
Partner treffen, und die Tempo-Strategie (Rückenwind für schnelle, Bizarroraum für langsame Teams).
"""
from . import typen
ROLES = (
    ("schutz", "Schutz", "Schützt sich eine Runde, während der Partner angreift",
     ("protect", "detect", "spiky-shield", "kings-shield", "baneful-bunker", "silk-trap", "burning-bulwark", "obstruct", "max-guard")),
    ("tempo", "Tempo-Kontrolle", "Ändert, wer zuerst zieht",
     ("tailwind", "trick-room", "icy-wind", "electroweb", "thunder-wave", "bulldoze", "scary-face", "glare", "string-shot", "rock-tomb")),
    ("stoerer", "Störer", "Bringt den Gegner aus dem Takt",
     ("fake-out", "taunt", "encore", "spore", "sleep-powder", "will-o-wisp", "snarl", "parting-shot", "disable", "imprison")),
    ("umlenken", "Umlenken", "Zieht Angriffe auf sich oder tauscht die Plätze",
     ("follow-me", "rage-powder", "ally-switch")),
    ("hilfe", "Unterstützung", "Stärkt oder schützt den Partner",
     ("helping-hand", "wide-guard", "quick-guard", "light-screen", "reflect", "aurora-veil", "coaching", "life-dew", "pollen-puff",
      "heal-pulse", "decorate")),
)
# Fähigkeiten, die eine Rolle übernehmen
ROLE_ABIL = {"intimidate": "stoerer", "prankster": "stoerer", "drizzle": "hilfe", "drought": "hilfe",
             "sand-stream": "hilfe", "snow-warning": "hilfe", "electric-surge": "hilfe", "psychic-surge": "hilfe",
             "grassy-surge": "hilfe", "misty-surge": "hilfe", "friend-guard": "hilfe"}
# Fähigkeiten, die einen Angriffstyp abfangen (für Flächenattacken des Partners)
IMMUN = {"levitate": "ground", "earth-eater": "ground", "water-absorb": "water", "storm-drain": "water", "dry-skin": "water",
         "volt-absorb": "electric", "lightning-rod": "electric", "motor-drive": "electric", "flash-fire": "fire",
         "well-baked-body": "fire", "sap-sipper": "grass", "telepathy": "*"}
ALL_OTHERS, ALL_FOES = 9, 11      # PokéAPI-Ziele: alle anderen Pokémon (trifft den Partner), alle Gegner
SLOW, FAST = 60, 95               # Basis-Initiative: bis SLOW profitiert vom Bizarroraum, ab FAST vom Rückenwind


def _factor(ch, atk, types):
    return typen.product(ch, atk, types)


def evaluate(ms, ch, type_key):
    """ms: Mitglieder (siehe oben), ch: Typtabelle {Angriff: {Verteidiger: Faktor}}, type_key: {Typ-ID: Kennung}.
    → {wertung, rollen: [{key, name, tipp, wer: [[Mitglied, Attacke]], kann: [[Mitglied, Attacke]]}], flaeche, partner,
    tempo: {schnell, langsam, rat}}."""
    roles = []
    for key, name, tip, moves in ROLES:
        have, can = [], []
        for m in ms:
            hit = [a["name"] for a in m["attacken"] if a["kennung"] in moves]
            if m.get("faehigkeit") and ROLE_ABIL.get(m["faehigkeit"]) == key:
                hit.append(m.get("faehigkeit_name") or m["faehigkeit"])
            if hit:
                have.append([m["name"], ", ".join(hit)])
            else:
                opt = [n for k, n in (m.get("lernbar") or {}).items() if k in moves]
                if opt:
                    can.append([m["name"], ", ".join(sorted(opt)[:3])])
        roles.append({"key": key, "name": name, "tipp": tip, "wer": have, "kann": can})
    spread, partner = [], []
    for i, m in enumerate(ms):
        for a in m["attacken"]:
            if not a.get("schaden") or a.get("ziel") not in (ALL_OTHERS, ALL_FOES):
                continue
            spread.append([m["name"], a["name"], a["ziel"] == ALL_OTHERS])
            if a["ziel"] != ALL_OTHERS:
                continue
            hurt, safe = [], []
            for j, p in enumerate(ms):
                if j == i:
                    continue
                immun = IMMUN.get(p.get("faehigkeit") or "")
                f = 0.0 if immun in ("*", type_key.get(a["typ"])) else _factor(ch, a["typ"], p["typen"])
                (safe if f == 0 else hurt).append([p["name"], f])
            partner.append({"wer": m["name"], "attacke": a["name"], "typ": a["typ"], "trifft": hurt, "immun": safe})
    fast = [m["name"] for m in ms if m["init"] >= FAST]
    slow = [m["name"] for m in ms if m["init"] <= SLOW]
    moves = {a["kennung"] for m in ms for a in m["attacken"]}
    if len(slow) >= 3 and "trick-room" not in moves:
        rat = "Viele langsame Mitglieder: Bizarroraum würde passen."
    elif len(fast) >= 3 and "tailwind" not in moves:
        rat = "Viele schnelle Mitglieder: Rückenwind würde sie noch weiter nach vorn bringen."
    elif "trick-room" in moves and len(fast) >= 3:
        rat = "Bizarroraum und viele schnelle Mitglieder passen schlecht zusammen."
    else:
        rat = ""
    n = len(ms) or 1
    covered = sum(1 for r in roles if r["wer"])
    score = covered / len(ROLES) * 70
    score += min(len(spread), 3) / 3 * 20
    risky = sum(1 for p in partner if any(f > 1 for _, f in p["trifft"]))
    score += 10 - min(risky, 2) * 5
    return {"wertung": round(score * min(1.0, n / 4)), "rollen": roles, "flaeche": spread, "partner": partner,
            "tempo": {"schnell": fast, "langsam": slow, "rat": rat}}
