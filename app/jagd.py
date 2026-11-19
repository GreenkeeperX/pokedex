"""Shiny-Jagd (0.70.0): Zähler je Jagd mit Methode, Schillerpin und laufender Wahrscheinlichkeit.

Die Quoten stehen als gepflegte Tabelle in extra/shiny_quoten.json; Quelle, Herleitung und Offenes in docs/formeln.md
(„Schillernde Pokémon“). Gerechnet wird mit Würfen: Ein Spiel prüft für eine Begegnung n Werte, jeder ist mit 1/Nenner
schillernd, die Quote ist also 1 − (1 − 1/Nenner)^n. Wie viele Würfe es sind, hängt an Methode, Zählerstand (Ketten),
Optionen (Lockparfüm, Forschung, Schillerkraft) und Schillerpin. Wenige Methoden haben statt Würfen eine feste Quote.

Die Jagden liegen in user.db (Tabelle jagd). Der Zähler zählt Begegnungen; die Quote gilt für die nächste Begegnung beim
aktuellen Zählerstand.
"""
import datetime
import json
import math
import os
import re

from . import db, fehler, spiele

QUOTEN = os.path.join(os.path.dirname(__file__), "..", "extra", "shiny_quoten.json")
METHODE_FELDER = {"name", "text", "wuerfe", "stufen", "je", "optionen", "quote", "quote_pin", "ab"}
SPIEL_FELDER = {"nenner", "pin", "methoden", "text"}
ZAEHLER_MAX = 10_000_000
_cache = {}


def tabelle():
    """Die Quotentabelle (gelesen, solange die Datei sich nicht ändert). {} und ein Eintrag im Fehlerregister, wenn sie
    fehlt oder kaputt ist."""
    try:
        mt = os.path.getmtime(QUOTEN)
        if _cache.get("mt") != mt:
            with open(QUOTEN, encoding="utf-8") as fh:
                _cache.update(mt=mt, d=json.load(fh))
    except (OSError, ValueError) as err:
        fehler.melden(err)
        return {}
    return _cache["d"]


def bruch(text):
    """„41/8192“ → 41/8192 als Zahl."""
    z, n = (float(x) for x in str(text).split("/"))
    return z / n


def eintrag(T, kennung):
    """Eintrag des Spiels (eine Erweiterung nimmt den ihres Hauptspiels) oder None, wenn es dort keine Jagd gibt."""
    return (T.get("spiele") or {}).get(spiele.basis(kennung or ""))


def _wahl(m, optionen):
    """Gewählte Stufe je Option (Index in werte), begrenzt auf die vorhandenen."""
    out = {}
    for o in m.get("optionen", ()):
        try:
            i = int((optionen or {}).get(o["id"], 0))
        except (TypeError, ValueError):
            i = 0
        out[o["id"]] = min(max(i, 0), len(o["werte"]) - 1)
    return out


def wuerfe(m, zaehler, optionen=None, pin=0):
    """Würfe einer Begegnung beim Zählerstand zaehler: Grundwürfe der Methode, Stufe der Kette (die höchste erreichte),
    je Zählerstand (bis zur Grenze), Optionen, Schillerpin (pin: Würfe des Schillerpins im Spiel, 0 ohne)."""
    n = m.get("wuerfe", 1)
    extra = 0
    for ab, mehr in m.get("stufen", ()):
        if zaehler >= ab:
            extra = mehr
    n += extra
    if m.get("je"):
        n += m["je"][0] * min(zaehler, m["je"][1])
    wahl = _wahl(m, optionen)
    for o in m.get("optionen", ()):
        n += o["werte"][wahl[o["id"]]][1]
    return n + pin


def quote(T, kennung, mid, zaehler=0, optionen=None, pin=False):
    """Quote der nächsten Begegnung: {p, eins_zu, wuerfe, hinweise}. wuerfe ist None bei einer festen Quote der Quelle;
    hinweise sagen, was die Quelle nicht belegt (dann zeigt die Quote eine Untergrenze oder lässt den Schillerpin weg)."""
    e = eintrag(T, kennung)
    m = (T.get("methoden") or {}).get(mid)
    if not e or not m or mid not in e["methoden"]:
        raise ValueError("Methode gibt es in diesem Spiel nicht")
    pin_w = e["pin"] if pin and e["pin"] else 0
    hinweise = []
    if m.get("quote") and zaehler >= m.get("ab", 0):
        if pin_w and m.get("quote_pin"):
            p = bruch(m["quote_pin"])
        else:
            p = bruch(m["quote"])
            if pin_w:
                hinweise.append("Der Schillerpin ist nicht eingerechnet: Die Quelle nennt für diese Methode keinen Wert mit ihm.")
        n = None
    else:
        if m.get("quote"):
            hinweise.append(f"Unter {m['ab']} nennt die Quelle keine Quote; gezeigt ist die Grundquote als Untergrenze.")
        n = wuerfe(m, zaehler, optionen, pin_w)
        p = 1 - (1 - 1 / e["nenner"]) ** n
    return {"p": p, "eins_zu": round(1 / p, 2), "wuerfe": n, "hinweise": hinweise}


def _grenzen(m, zaehler):
    """Zählerstände, an denen sich die Quote ändern kann, von 0 bis zaehler."""
    out = {0, zaehler}
    out |= {ab for ab, _ in m.get("stufen", ()) if ab < zaehler}
    if m.get("ab") and m["ab"] < zaehler:
        out.add(m["ab"])
    if m.get("je"):
        out |= set(range(0, min(m["je"][1], zaehler) + 1))
    return sorted(out)


def schon(T, kennung, mid, zaehler, optionen=None, pin=False):
    """Wahrscheinlichkeit, in zaehler Begegnungen (Zählerstand 0 bis zaehler − 1) mindestens ein schillerndes Pokémon
    gesehen zu haben: 1 − Π (1 − p). Zwischen zwei Grenzen ist p gleich, das Produkt also eine Potenz."""
    m = T["methoden"][mid]
    log_keins = 0.0
    xs = _grenzen(m, zaehler)
    for a, b in zip(xs, xs[1:]):
        log_keins += (b - a) * math.log1p(-quote(T, kennung, mid, a, optionen, pin)["p"])
    return 1 - math.exp(log_keins)


def methoden(T, kennung):
    """Was die Oberfläche zum Spiel braucht: {nenner, pin (bool), text, methoden: [{id, name, text, optionen}]}; None ohne
    Jagd im Spiel."""
    e = eintrag(T, kennung)
    if not e:
        return None
    ms = T["methoden"]
    return {"nenner": e["nenner"], "pin": bool(e["pin"]), "text": e.get("text", ""),
            "methoden": [{"id": k, "name": ms[k]["name"], "text": ms[k].get("text", ""),
                          "optionen": [{"id": o["id"], "name": o["name"], "werte": [w[0] for w in o["werte"]]}
                                       for o in ms[k].get("optionen", ())]} for k in e["methoden"]]}


def pruefe(T=None):
    """Fehler der Quotentabelle als Liste von Texten (leer: in Ordnung)."""
    T = tabelle() if T is None else T
    out = []
    ms = T.get("methoden") or {}
    if not T.get("quellen"):
        out.append("ohne Quellen")
    for k, m in ms.items():
        for f in set(m) - METHODE_FELDER:
            out.append(f"Methode {k}: unbekanntes Feld {f}")
        if not m.get("name"):
            out.append(f"Methode {k}: ohne Namen")
        if not isinstance(m.get("wuerfe", 1), int) or m.get("wuerfe", 1) < 1:
            out.append(f"Methode {k}: wuerfe keine Zahl ab 1")
        st = m.get("stufen", [])
        if [ab for ab, _ in st] != sorted({ab for ab, _ in st}) or any(not isinstance(x, int) or x < 0 for s in st for x in s):
            out.append(f"Methode {k}: stufen nicht aufsteigend oder keine Zahlen")
        for f in ("quote", "quote_pin"):
            if f in m and not re.fullmatch(r"\d+(\.\d+)?/\d+", str(m[f])):
                out.append(f"Methode {k}: {f} ist kein Bruch wie 1/99")
        for o in m.get("optionen", ()):
            if not o.get("id") or not o.get("name") or not o.get("werte") or o["werte"][0][1] != 0:
                out.append(f"Methode {k}: Option ohne id, Namen oder Werte (der erste Wert muss 0 sein)")
    for kennung, e in (T.get("spiele") or {}).items():
        if kennung not in spiele.SPIELE:
            out.append(f"{kennung}: kein Spiel in app/spiele.py")
        elif spiele.basis(kennung) != kennung:
            out.append(f"{kennung}: Erweiterung, gilt schon über ihr Hauptspiel")
        for f in set(e) - SPIEL_FELDER:
            out.append(f"{kennung}: unbekanntes Feld {f}")
        if e.get("nenner") not in (4096, 8192):
            out.append(f"{kennung}: nenner nicht 4096 oder 8192")
        if not isinstance(e.get("pin"), int) or e["pin"] < 0:
            out.append(f"{kennung}: pin keine Zahl ab 0")
        for mid in e.get("methoden") or ["(keine)"]:
            if mid not in ms:
                out.append(f"{kennung}: Methode {mid} fehlt unter methoden")
    return out


# ------------------------------------------------------------------ Jagden in user.db

def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _zeile(T, r, sperren, namen):
    """Eine Jagd für die Oberfläche, mit Quote und laufender Wahrscheinlichkeit."""
    x = dict(r)
    x["optionen"] = json.loads(x["optionen"] or "{}")
    x["pin"], x["angeheftet"] = bool(x["pin"]), bool(x["angeheftet"])
    x["name"] = namen.get(x["form"]) or f"#{x['form']}"
    x["sperre"] = sperren.get(x["form"], "")
    m = (T.get("methoden") or {}).get(x["methode"])
    x["methode_name"] = m["name"] if m else x["methode"]
    try:
        q = quote(T, x["spiel"], x["methode"], x["zaehler"], x["optionen"], x["pin"])
        x.update(eins_zu=q["eins_zu"], wuerfe=q["wuerfe"], hinweise=q["hinweise"],
                 schon=round(schon(T, x["spiel"], x["methode"], x["zaehler"], x["optionen"], x["pin"]), 4))
        if m.get("ab") and x["zaehler"] > m["ab"]:
            x["hinweise"].append(f"„Bis jetzt“ rechnet die ersten {m['ab']} mit der Grundquote (Untergrenze).")
    except ValueError:      # Methode nicht (mehr) in der Tabelle: Zähler bleibt, Quote fehlt sichtbar
        x.update(eins_zu=None, wuerfe=None, schon=None, hinweise=["Diese Methode steht nicht mehr in der Quotentabelle."])
    return x


def _namen_und_sperren(spiel):
    from . import abfragen
    D = abfragen.data()
    namen = {i: f["name"] for i, f in D.forms.items()} if D else {}
    s = abfragen.shiny_locks(spiel)
    sperren = {**{i: "tausch" for i in s.get("tausch", ())}, **{i: "nie" for i in s.get("nie", ())}}
    return namen, sperren


def ansicht(p):
    """{spiel, nenner, pin, text, methoden, quellen, jagden: [laufende, angeheftete zuerst, dann zuletzt geändert],
    gefunden: [abgeschlossene, neueste zuerst]} für p["spiel"]; methoden ist None, wo es keine Jagd gibt."""
    T = tabelle()
    spiel = str(p.get("spiel") or "")
    namen, sperren = _namen_und_sperren(spiel)
    con = db.user()
    try:
        rows = con.execute("SELECT * FROM jagd WHERE spiel = ? ORDER BY angeheftet DESC, geaendert DESC, id DESC", (spiel,)).fetchall()
    finally:
        con.close()
    xs = [_zeile(T, r, sperren, namen) for r in rows]
    info = methoden(T, spiel) or {"nenner": None, "pin": False, "methoden": None,
                                  "text": "In Generation 1 gibt es keine schillernden Pokémon." if spiele.profil(spiel)["gen"] == 1 and spiel
                                  else "Für dieses Spiel nennt die Quotentabelle keine Shiny-Jagd (nicht möglich oder ohne Quelle)."}
    return {"spiel": spiel, **info, "quellen": T.get("quellen", []),
            "jagden": [x for x in xs if not x["gefunden"]],
            "gefunden": sorted((x for x in xs if x["gefunden"]), key=lambda x: x["gefunden"], reverse=True)}


def _eine(con, jid):
    r = con.execute("SELECT * FROM jagd WHERE id = ?", (jid,)).fetchone()
    if not r:
        raise ValueError("Jagd nicht gefunden")
    return r


def _antwort(jid):
    con = db.user()
    try:
        r = _eine(con, jid)
    finally:
        con.close()
    namen, sperren = _namen_und_sperren(r["spiel"])
    return _zeile(tabelle(), r, sperren, namen)


def speichern(body):
    """Neue Jagd ({spiel, form, methode, optionen, pin}) oder Änderung einer ({id, …}: methode, optionen, pin, angeheftet,
    notiz, gefunden). gefunden: true schließt die Jagd ab und setzt das Pokémon im Spiel auf schillernd gefangen;
    false nimmt nur den Abschluss zurück. Antwort: die Jagd wie in ansicht."""
    T = tabelle()
    con = db.user()
    try:
        jid = body.get("id")
        if jid:
            alt = dict(_eine(con, int(jid)))
        else:
            try:
                form = int(body.get("form"))
            except (TypeError, ValueError):
                raise ValueError("form: eine Zahl")
            alt = {"spiel": str(body.get("spiel") or "")[:60], "form": form, "methode": "", "optionen": "{}", "pin": 0,
                   "zaehler": 0, "angeheftet": 0, "gefunden": None, "notiz": ""}
        neu = dict(alt)
        if "methode" in body:
            neu["methode"] = str(body["methode"])[:40]
        if "optionen" in body or "methode" in body:
            m = (T.get("methoden") or {}).get(neu["methode"]) or {}
            neu["optionen"] = json.dumps(_wahl(m, body.get("optionen") if "optionen" in body else json.loads(alt["optionen"] or "{}")))
        for k in ("pin", "angeheftet"):
            if k in body:
                neu[k] = 1 if body[k] else 0
        if "notiz" in body:
            neu["notiz"] = " ".join(str(body["notiz"] or "").split())[:300]
        quote(T, neu["spiel"], neu["methode"], neu["zaehler"], json.loads(neu["optionen"]), neu["pin"])   # prüft Spiel und Methode
        if "gefunden" in body:
            neu["gefunden"] = (alt["gefunden"] or _jetzt()) if body["gefunden"] else None
        args = (neu["methode"], neu["optionen"], neu["pin"], neu["angeheftet"], neu["gefunden"], neu["notiz"], _jetzt())
        if jid:
            con.execute("UPDATE jagd SET methode=?, optionen=?, pin=?, angeheftet=?, gefunden=?, notiz=?, geaendert=? WHERE id=?",
                        args + (int(jid),))
        else:
            jid = con.execute("INSERT INTO jagd (methode, optionen, pin, angeheftet, gefunden, notiz, geaendert, spiel, form, zaehler, start) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)", args + (neu["spiel"], neu["form"], _jetzt())).lastrowid
        if neu["gefunden"] and not alt["gefunden"]:
            for t in ("schillernd", "gefangen"):
                con.execute(f"INSERT OR IGNORE INTO {t} (spiel, form, seit) VALUES (?, ?, ?)", (neu["spiel"], neu["form"], _jetzt()))
        con.commit()
    finally:
        con.close()
    return _antwort(int(jid))


def zaehlen(body):
    """Zähler ändern: {id, plus} (auch negativ) oder {id, wert}; nie unter 0. Antwort: die Jagd wie in ansicht."""
    try:
        jid = int(body.get("id"))
        wert, plus = body.get("wert"), int(body.get("plus") or 0)
        wert = None if wert is None else int(wert)
    except (TypeError, ValueError):
        raise ValueError("id, plus und wert: Zahlen")
    con = db.user()
    try:
        r = _eine(con, jid)
        z = min(max((r["zaehler"] + plus) if wert is None else wert, 0), ZAEHLER_MAX)
        con.execute("UPDATE jagd SET zaehler = ?, geaendert = ? WHERE id = ?", (z, _jetzt(), jid))
        con.commit()
    finally:
        con.close()
    return _antwort(jid)


def loeschen(body):
    con = db.user()
    try:
        con.execute("DELETE FROM jagd WHERE id = ?", (int(body.get("id") or 0),))
        con.commit()
    finally:
        con.close()
    return {"ok": True}
