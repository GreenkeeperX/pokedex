"""Nuzlocke (0.73.0, Soul-Link 0.74.0): Läufe mit erster Begegnung je Gebiet, Team, Box und Friedhof, Regeln je Lauf und Levelgrenze.

Regeln nach Bulbapedia „Nuzlocke Challenge“ (https://bulbapedia.bulbagarden.net/wiki/Nuzlocke) und Smogon „An Introduction
to Pokémon Nuzlockes and Challenges“ (https://smogon.com/articles/introduction-nuzlockes), Stand 19.11.2026:

- Je Gebiet zählt nur die erste wilde Begegnung; ein Gebiet ist, was im Spiel als Fundort erscheint. Die Gebiete kommen aus
  den Fundorten des Pokédex (abfragen.areas).
- Ein besiegtes Pokémon ist tot (Friedhof).
- Wählbar je Lauf: Dupes-Klausel (Art oder ganze Entwicklungsreihe), Shiny-Klausel, Geschenke und feste Begegnungen,
  Levelgrenze (höchstes Level im Team des nächsten Arenaleiters, der Top Vier oder des Champs), Spitznamen, Niederlage
  (Lauf vorbei oder weiter mit der Box).

Soul-Link (0.74.0, Bulbapedia, Smogon und https://emeraldvoid.github.io/pokemon-challenges/soul-link.html): Zwei Spieler,
die ersten Begegnungen eines Gebiets sind gekoppelt. Stirbt eins, stirbt der Partner mit; kommt eins in die Box oder ins
Team, kommt der Partner mit; misslingt ein Fang, kommt der Partner in die Box. Wahlweise teilen die Teams keinen Typ.

Der Pokédex steuert das Spiel nicht: Verstöße sind Hinweise, keine Sperre. Ein Gebiet hat höchstens eine erste Begegnung;
Shiny und Geschenke kommen als Zusatz dazu. Die Läufe liegen in user.db (Tabelle nuzlocke, eine Zeile je Lauf, Begegnungen
und besiegte Trainer als JSON), damit Sicherung und Rückspielen ohne Zuordnung von IDs auskommen.
"""
import datetime
import json

from . import db, fehler

# (Schlüssel, Name, [(Wert, Text)], Standard)
REGELN = (
    ("dupes", "Dupes-Klausel", (("linie", "gefangene Entwicklungsreihen zählen nicht"), ("art", "gefangene Arten zählen nicht"),
                                ("aus", "aus")), "linie"),
    ("shiny", "Shiny-Klausel", (("ja", "schillernde dürfen zusätzlich mit"), ("nein", "aus")), "ja"),
    ("geschenke", "Geschenke und feste Begegnungen", (("extra", "zählen extra"), ("gebiet", "zählen als Begegnung des Gebiets"),
                                                      ("nein", "nicht erlaubt")), "extra"),
    ("levelgrenze", "Levelgrenze", (("ja", "Level des stärksten Pokémon des nächsten Bosses"), ("nein", "aus")), "ja"),
    ("spitznamen", "Spitznamen", (("ja", "Pflicht"), ("nein", "frei")), "ja"),
    ("niederlage", "Niederlage", (("ende", "Lauf vorbei"), ("weiter", "weiter mit der Box")), "ende"),
    ("typen", "Typen (Soul-Link)", (("frei", "frei"), ("getrennt", "kein Typ in beiden Teams")), "frei"),
)
MODUS = ("solo", "soullink")
SPIELER = ("Spieler 1", "Spieler 2")
STATUS = ("team", "box", "tot", "verpasst", "ausgelassen")
STATUS_TEXT = {"team": "im Team", "box": "in der Box", "tot": "tot", "verpasst": "verpasst", "ausgelassen": "ausgelassen"}
LEBT = ("team", "box")
GEFANGEN = ("team", "box", "tot")
EXTRA = ("", "shiny", "geschenk")
LAUF_STATUS = ("laeuft", "geschafft", "gescheitert")
BOSSE = ("Arenaleiter", "Top Vier", "Champ")
TEAM_MAX = 6
BEGEGNUNGEN_MAX = 2000
QUELLEN = (("Bulbapedia: Nuzlocke Challenge", "https://bulbapedia.bulbagarden.net/wiki/Nuzlocke"),
           ("Smogon: An Introduction to Pokémon Nuzlockes and Challenges", "https://smogon.com/articles/introduction-nuzlockes"))


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _text(v, n):
    return " ".join(str(v or "").split())[:n]


def regeln(werte=None):
    """Die Regeln eines Laufs: Standard, darüber die gültigen Werte aus werte (Unbekanntes fällt weg)."""
    werte = werte if isinstance(werte, dict) else {}
    return {k: werte[k] if werte.get(k) in {w for w, _ in ws} else std for k, _, ws, std in REGELN}


def begegnung(x, n):
    """Eine Begegnung geprüft und gekürzt: {n, spieler, ort, form, spitzname, status, extra, level, zeit}. ValueError bei Unsinn."""
    if not isinstance(x, dict):
        raise ValueError("Begegnung: ein Objekt erwartet")
    try:
        form = int(x["form"])
        level = None if x.get("level") in (None, "") else int(x["level"])
        spieler = int(x.get("spieler") or 1)
    except (TypeError, ValueError, KeyError):
        raise ValueError("Begegnung: form (Zahl), level (Zahl oder leer) und spieler (1 oder 2) erwartet")
    if spieler not in (1, 2):
        raise ValueError("spieler: 1 oder 2")
    if level is not None and not 1 <= level <= 100:
        raise ValueError("Level: eine Zahl von 1 bis 100")
    status, extra = x.get("status") or "team", x.get("extra") or ""
    if status not in STATUS:
        raise ValueError(f"Status: {', '.join(STATUS)}")
    if extra not in EXTRA:
        raise ValueError("Zusatz: leer, shiny oder geschenk")
    ort = _text(x.get("ort"), 80)
    if not ort and not extra:
        raise ValueError("Gebiet fehlt (nur Shiny und Geschenke dürfen ohne Gebiet)")
    return {"n": int(n), "spieler": spieler, "ort": ort, "form": form, "spitzname": _text(x.get("spitzname"), 30), "status": status, "extra": extra,
            "level": level, "zeit": _text(x.get("zeit"), 40) or _jetzt()}


def zeile(r):
    """Ein Lauf aus user.db (oder aus einer Sicherung) als Objekt mit geprüften Feldern."""
    r = dict(r)
    lade = lambda v, leer: (json.loads(v) if isinstance(v, str) and v else v) or leer
    bs = []
    for i, x in enumerate(lade(r.get("begegnungen"), [])[:BEGEGNUNGEN_MAX]):
        try:
            bs.append(begegnung(x, x.get("n", i + 1) if isinstance(x, dict) else i + 1))
        except (ValueError, TypeError) as err:
            fehler.melden(err)          # eine kaputte Begegnung fällt weg, der Lauf bleibt lesbar
    return {"id": r.get("id"), "spiel": _text(r.get("spiel"), 60), "name": _text(r.get("name"), 60) or "Nuzlocke",
            "modus": r.get("modus") if r.get("modus") in MODUS else "solo",
            "spieler": [_text(n, 30) or SPIELER[i] for i, n in enumerate((list(lade(r.get("spieler"), [])) + ["", ""])[:2])],
            "regeln": regeln(lade(r.get("regeln"), {})), "begegnungen": bs,
            "besiegt": sorted({int(t) for t in lade(r.get("besiegt"), []) if str(t).isdigit()}),
            "status": r.get("status") if r.get("status") in LAUF_STATUS else "laeuft",
            "start": _text(r.get("start"), 40) or _jetzt(), "geaendert": _text(r.get("geaendert"), 40) or _jetzt(),
            "notiz": _text(r.get("notiz"), 500)}


def _laden(con, lid):
    r = con.execute("SELECT * FROM nuzlocke WHERE id = ?", (lid,)).fetchone()
    if not r:
        raise ValueError("Lauf nicht gefunden")
    return zeile(r)


def _schreiben(con, L):
    args = (L["spiel"], L["name"], L["modus"], json.dumps(L["spieler"], ensure_ascii=False), json.dumps(L["regeln"]),
            json.dumps(L["begegnungen"], ensure_ascii=False), json.dumps(L["besiegt"]), L["status"], L["start"], _jetzt(), L["notiz"])
    if L.get("id"):
        con.execute("UPDATE nuzlocke SET spiel=?, name=?, modus=?, spieler=?, regeln=?, begegnungen=?, besiegt=?, status=?, start=?, "
                    "geaendert=?, notiz=? WHERE id=?", args + (L["id"],))
        return L["id"]
    return con.execute("INSERT INTO nuzlocke (spiel, name, modus, spieler, regeln, begegnungen, besiegt, status, start, geaendert, notiz) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", args).lastrowid


def _ketten():
    """{Art: Entwicklungsreihe} aus den Spieldaten."""
    con = db.game()
    try:
        return {r[0]: r[1] for r in con.execute("SELECT id, evolution_chain_id FROM pokemon_species")}
    finally:
        con.close()


def _bosse(spiel, besiegt):
    """Arenaleiter, Top Vier und Champ des Spiels in der Reihenfolge ihres Levels: [{id, name, rolle, titel, level, besiegt}]."""
    from . import abfragen
    out = []
    for t in abfragen.trainer_list({"spiel": spiel}).get("trainer", []):
        if t["rolle"] in BOSSE and not t["rueckkampf"]:
            out.append({"id": t["id"], "name": t["name"], "rolle": t["rolle"], "titel": t["titel"],
                        "level": max([m["lvl"] or 0 for m in t["team"]] or [0]), "besiegt": t["id"] in besiegt})
    return sorted(out, key=lambda b: (b["level"], b["id"]))


def ansicht(p):
    """{spiel, regeln_liste: [{id, name, werte, standard, wert}], quellen, laeufe: [{id, name, status, start, geaendert}], lauf}
    für p["spiel"]; lauf ist der Lauf p["lauf"] (sonst der zuletzt geänderte laufende) mit gebiete, team, box, friedhof,
    verpasst, extras, bosse, grenze, hinweise, oder None. Die Regeln des Laufs stehen als wert in regeln_liste."""
    spiel = _text(p.get("spiel"), 60)
    con = db.user()
    try:
        rows = con.execute("SELECT * FROM nuzlocke WHERE spiel = ? ORDER BY status = 'laeuft' DESC, geaendert DESC, id DESC",
                           (spiel,)).fetchall()
    finally:
        con.close()
    laeufe = [zeile(r) for r in rows]
    try:
        wahl = int(p.get("lauf") or 0)
    except (TypeError, ValueError):
        raise ValueError("lauf: eine Zahl")
    L = next((x for x in laeufe if x["id"] == wahl), laeufe[0] if laeufe else None)
    return {"spiel": spiel, "quellen": [list(q) for q in QUELLEN],
            "regeln_liste": [{"id": k, "name": n, "werte": [list(w) for w in ws], "standard": std, "wert": L["regeln"][k] if L else std}
                             for k, n, ws, std in REGELN],
            "laeufe": [{k: x[k] for k in ("id", "name", "status", "start", "geaendert")} for x in laeufe],
            "lauf": _auswerten(L) if L else None}


def _auswerten(L):
    """Ein Lauf für die Oberfläche: Gebiete mit erster Begegnung und gesperrten Arten je Spieler, Team, Box, Friedhof, Bosse,
    Levelgrenze und Hinweise auf Verstöße. Im Soul-Link je Begegnung der Partner (partner: n oder None)."""
    from . import abfragen
    D = abfragen.data()
    R, soul = L["regeln"], L["modus"] == "soullink"
    wer = (1, 2) if soul else (1,)
    ketten = _ketten() if D else {}
    form = lambda i: D.forms.get(i) if D else None
    art = lambda i: (form(i) or {}).get("art", i)
    schluessel = lambda i: (("k", ketten.get(art(i), art(i))) if R["dupes"] == "linie" else ("a", art(i)))
    gen = abfragen.game_of(D, L["spiel"])[1] if D else None
    partner = _partner(L)

    def karte(b):
        f = form(b["form"]) or {}
        return dict(b, name=f.get("name") or f"#{b['form']}", typen=abfragen.form_types(D, f, gen) if f else [],
                    partner=partner.get(b["n"]))

    bs = [karte(b) for b in L["begegnungen"] if b["spieler"] in wer]
    nach_n = {b["n"]: b for b in bs}
    gefangen = {s: {} for s in wer}
    for b in bs:
        if b["status"] in GEFANGEN:
            gefangen[b["spieler"]].setdefault(schluessel(b["form"]), b["name"])
    erste = {}
    for b in bs:
        if not b["extra"] and b["ort"]:
            erste.setdefault(b["ort"], {})[b["spieler"]] = b
    gebiete = []
    daten = abfragen.areas({"spiel": L["spiel"]}) if D else None

    def sperre(m_id, s, eigene):
        k = schluessel(m_id)
        if R["dupes"] == "aus" or k not in gefangen[s] or (eigene and eigene["form"] == m_id):
            return ""
        return f"schon gefangen: {gefangen[s][k]}"

    for gb in (daten or {}).get("gebiete", []):
        hier, mons, gesehen = erste.pop(gb["ort"], {}), [], set()
        for m in gb["mons"]:
            if m["id"] not in gesehen:
                gesehen.add(m["id"])
                mons.append({"id": m["id"], "name": m["name"], "methode": m["methode"], "level": m["level"],
                             "gesperrt": [sperre(m["id"], s, hier.get(s)) for s in wer]})
        gebiete.append({"ort": gb["ort"], "mons": mons, "erste": [hier.get(s) for s in wer]})
    # Begegnungen in Gebieten, die die Fundorte nicht kennen (von Hand eingetragen), kommen hinten dazu
    gebiete += [{"ort": o, "mons": [], "erste": [hier.get(s) for s in wer]} for o, hier in erste.items()]
    bosse = _bosse(L["spiel"], set(L["besiegt"])) if D else []
    team = [b for b in bs if b["status"] == "team"]
    grenze = None
    if R["levelgrenze"] == "ja":
        boss = next((b for b in bosse if not b["besiegt"]), None)
        if boss:
            grenze = {"boss": boss, "level": boss["level"],
                      "ueber": [b["n"] for b in team if b["level"] and b["level"] > boss["level"]]}
    name = lambda b: b["spitzname"] or b["name"]
    vor = lambda s: f"{L['spieler'][s - 1]}: " if soul else ""
    hinweise = []
    if not daten or not daten.get("gebiete"):
        hinweise.append("Für dieses Spiel kennt der Pokédex keine Fundorte; trag Gebiete von Hand ein.")
    if R["levelgrenze"] == "ja" and not bosse:
        hinweise.append("Für dieses Spiel kennt der Pokédex keine Arenaleiter, Top Vier oder Champs: keine Levelgrenze.")
    for s in wer:
        eig = [b for b in team if b["spieler"] == s]
        if len(eig) > TEAM_MAX:
            hinweise.append(f"{vor(s)}Mehr als {TEAM_MAX} Pokémon im Team ({len(eig)}).")
        if grenze and any(b["n"] in grenze["ueber"] for b in eig):
            hinweise.append(f"{vor(s)}Über der Levelgrenze {grenze['level']} ({grenze['boss']['name']}): "
                            f"{', '.join(name(b) for b in eig if b['n'] in grenze['ueber'])}.")
    if R["spitznamen"] == "ja":
        ohne = [b["name"] for b in bs if b["status"] in LEBT and not b["spitzname"]]
        if ohne:
            hinweise.append(f"Ohne Spitznamen: {', '.join(ohne)}.")
    if R["geschenke"] == "nein" and any(b["extra"] == "geschenk" for b in bs):
        hinweise.append("Geschenke und feste Begegnungen sind in diesem Lauf nicht erlaubt.")
    if R["shiny"] == "nein" and any(b["extra"] == "shiny" for b in bs):
        hinweise.append("Ohne Shiny-Klausel zählt ein schillerndes Pokémon als erste Begegnung seines Gebiets.")
    if soul:
        allein = [b for b in team if not b["extra"] and (nach_n.get(b["partner"]) or {}).get("status") != "team"]
        if allein:
            hinweise.append("Im Team ohne Partner im Team: " + ", ".join(
                f"{name(b)} ({L['spieler'][b['spieler'] - 1]}, {b['ort']}: "
                f"{'Partner fehlt noch' if not b['partner'] else STATUS_TEXT[nach_n[b['partner']]['status']]})" for b in allein) + ".")
        if R["typen"] == "getrennt":
            t1, t2 = ({t for b in team if b["spieler"] == s for t in b["typen"]} for s in (1, 2))
            if t1 & t2:
                hinweise.append(f"Typen in beiden Teams: {', '.join(D.tname(t) for t in sorted(t1 & t2))}.")
    for s in wer:
        eig = [b for b in bs if b["spieler"] == s]
        if L["status"] == "laeuft" and any(b["status"] == "tot" for b in eig) and not any(b["status"] in LEBT for b in eig):
            hinweise.append(f"{vor(s)}Kein Pokémon lebt mehr" + (": der Lauf ist vorbei." if R["niederlage"] == "ende" else "."))
    return dict({k: v for k, v in L.items() if k != "regeln"}, gebiete=gebiete, team=team, box=[b for b in bs if b["status"] == "box"],
                friedhof=[b for b in bs if b["status"] == "tot"], verpasst=[b for b in bs if b["status"] in ("verpasst", "ausgelassen")],
                extras=[b for b in bs if b["extra"]], bosse=bosse, grenze=grenze, hinweise=hinweise)


def _partner(L):
    """{n: n des Partners} im Soul-Link: die ersten Begegnungen desselben Gebiets der beiden Spieler (Shiny und Geschenke
    haben keinen Partner)."""
    if L["modus"] != "soullink":
        return {}
    je = {}
    for b in L["begegnungen"]:
        if not b["extra"] and b["ort"]:
            je.setdefault(b["ort"], {})[b["spieler"]] = b["n"]
    out = {}
    for x in je.values():
        if 1 in x and 2 in x:
            out[x[1]], out[x[2]] = x[2], x[1]
    return out


def _antwort(lid):
    con = db.user()
    try:
        L = _laden(con, lid)
    finally:
        con.close()
    return ansicht({"spiel": L["spiel"], "lauf": lid})


def speichern(body):
    """Neuer Lauf ({spiel, name, modus, regeln}) oder Änderung ({id, …}: name, spieler [zwei Namen], regeln, status, notiz,
    besiegt: {trainer, ja}). Der Modus (solo, soullink) steht mit dem Anlegen fest. Antwort: die Ansicht mit diesem Lauf."""
    con = db.user()
    try:
        if body.get("id"):
            L = _laden(con, int(body["id"]))
        else:
            spiel = _text(body.get("spiel"), 60)
            if not spiel:
                raise ValueError("spiel fehlt")
            if body.get("modus", "solo") not in MODUS:
                raise ValueError(f"modus: {', '.join(MODUS)}")
            L = zeile({"spiel": spiel, "name": body.get("name"), "modus": body.get("modus", "solo")})
        if "name" in body:
            L["name"] = _text(body["name"], 60) or L["name"]
        if "regeln" in body:
            L["regeln"] = regeln({**L["regeln"], **(body["regeln"] if isinstance(body["regeln"], dict) else {})})
        if "status" in body:
            if body["status"] not in LAUF_STATUS:
                raise ValueError(f"status: {', '.join(LAUF_STATUS)}")
            L["status"] = body["status"]
        if "notiz" in body:
            L["notiz"] = _text(body["notiz"], 500)
        if isinstance(body.get("spieler"), list):
            L["spieler"] = [_text(n, 30) or L["spieler"][i] for i, n in enumerate((body["spieler"] + ["", ""])[:2])]
        if isinstance(body.get("besiegt"), dict):
            try:
                tid = int(body["besiegt"].get("trainer"))
            except (TypeError, ValueError):
                raise ValueError("besiegt: trainer (Zahl) erwartet")
            s = set(L["besiegt"])
            (s.add if body["besiegt"].get("ja") else s.discard)(tid)
            L["besiegt"] = sorted(s)
        lid = _schreiben(con, L)
        con.commit()
    finally:
        con.close()
    return _antwort(lid)


def eintragen(body):
    """Begegnung anlegen ({lauf, spieler, ort, form, spitzname, status, extra, level}), ändern ({lauf, n, …}) oder löschen
    ({lauf, n, loeschen: true}). Ein Gebiet hat je Spieler höchstens eine erste Begegnung. Im Soul-Link geht der Partner
    mit: tot, Team und Box übernimmt er, bei verpasst kommt er in die Box (KOPPLUNG). Antwort: die Ansicht mit diesem Lauf."""
    try:
        lid = int(body.get("lauf"))
    except (TypeError, ValueError):
        raise ValueError("lauf: eine Zahl")
    con = db.user()
    try:
        L = _laden(con, lid)
        bs = L["begegnungen"]
        if body.get("n") is not None:
            alt = next((b for b in bs if b["n"] == int(body["n"])), None)
            if not alt:
                raise ValueError("Begegnung nicht gefunden")
            if body.get("loeschen"):
                bs.remove(alt)
                neu = None
            else:
                neu = begegnung({**alt, **{k: body[k] for k in ("ort", "form", "spitzname", "status", "extra", "level") if k in body}},
                                alt["n"])
                if L["modus"] == "soullink" and neu["status"] != alt["status"]:
                    _koppeln(L, neu)
                bs[bs.index(alt)] = neu
        else:
            if len(bs) >= BEGEGNUNGEN_MAX:
                raise ValueError(f"Höchstens {BEGEGNUNGEN_MAX} Begegnungen je Lauf")
            neu = begegnung(body if L["modus"] == "soullink" else dict(body, spieler=1), max([b["n"] for b in bs] or [0]) + 1)
            bs.append(neu)
        if neu and not neu["extra"] and any(b is not neu and b["ort"] == neu["ort"] and b["spieler"] == neu["spieler"] and not b["extra"]
                                            for b in bs):
            raise ValueError(f"In {neu['ort']} gibt es schon eine erste Begegnung; ändere sie statt einer zweiten")
        _schreiben(con, L)
        con.commit()
    finally:
        con.close()
    return _antwort(lid)


# Soul-Link: neuer Status → Status des Partners (fehlt: bleibt). Quelle: Soul-Link-Regeln (siehe oben)
KOPPLUNG = {"tot": "tot", "team": "team", "box": "box", "verpasst": "box"}


def _koppeln(L, b):
    """Den Partner von b mitziehen; ein toter Partner bleibt tot, ein verpasster bleibt verpasst."""
    p = next((x for x in L["begegnungen"] if x["n"] == _partner(L).get(b["n"])), None)
    ziel = KOPPLUNG.get(b["status"])
    if p and ziel and p["status"] not in ("tot", "verpasst", "ausgelassen"):
        p["status"] = ziel


def loeschen(body):
    con = db.user()
    try:
        con.execute("DELETE FROM nuzlocke WHERE id = ?", (int(body.get("id") or 0),))
        con.commit()
    finally:
        con.close()
    return {"ok": True}


def sicherung(con):
    """Alle Läufe für die Sicherung (ohne id)."""
    return [{k: v for k, v in zeile(r).items() if k != "id"} for r in con.execute("SELECT * FROM nuzlocke ORDER BY start, id")]


def aus_sicherung(xs):
    """Läufe aus einer Sicherung als Zeilen für INSERT (Reihenfolge wie in _schreiben). ValueError bei Unsinn."""
    out = []
    for x in (xs or [])[:2000]:
        if not isinstance(x, dict) or not x.get("spiel"):
            raise ValueError("nuzlocke: Einträge mit spiel erwartet")
        for i, b in enumerate(x.get("begegnungen") or []):
            begegnung(b, b.get("n", i + 1) if isinstance(b, dict) else i + 1)     # prüft; Unsinn bricht das Rückspielen ab
        L = zeile(dict(x, id=None, regeln=x.get("regeln") or {}, begegnungen=x.get("begegnungen") or [],
                       besiegt=x.get("besiegt") or []))
        out.append((L["spiel"], L["name"], L["modus"], json.dumps(L["spieler"], ensure_ascii=False), json.dumps(L["regeln"]),
                    json.dumps(L["begegnungen"], ensure_ascii=False), json.dumps(L["besiegt"]), L["status"], L["start"], L["geaendert"],
                    L["notiz"]))
    return out
