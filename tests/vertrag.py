"""Vertrag zwischen Server und Oberfläche: die Form der Antworten, die die Skripte in app/static/js/ lesen.

`tests/vertrag.json` hält je Aufruf fest, welche Felder die Antwort hat und von welcher Art sie sind (zahl, text, ja/nein,
leer, Liste, Objekt), gemessen an der Mini-Datenbank (tests/minidb.py). Der Test `Vertrag` in tests/mit_daten.py vergleicht
die Antworten des Servers damit und prüft, dass die Oberfläche jedes Feld kennt. Ändert sich eine Antwort mit Absicht:

    python3 -m tests.vertrag        # schreibt tests/vertrag.json neu; die Änderung steht dann im Diff

Die Form kennt nur, was in der Mini-Datenbank vorkommt. Leere Listen (Raids, Aufträge, Karten: Daten aus PKHeX, PokéWiki
und Map Genie) haben keine Form; sie stehen im Vertrag als `[]`.
"""
import json
import os
import re

DATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vertrag.json")
_ZAHL = re.compile(r"-?\d+")


def form(v):
    """Die Form eines Werts: Objekte mit ihren Feldern, Listen mit der gemeinsamen Form ihrer Einträge, sonst die Art.
    Objekte, deren Schlüssel alle Nummern sind (je Typ, je Pokémon), stehen als {"<nr>": Form}."""
    if isinstance(v, dict):
        if v and all(_ZAHL.fullmatch(str(k)) for k in v):
            return {"<nr>": _zusammen([form(x) for x in v.values()])}
        return {k: form(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [_zusammen([form(x) for x in v])] if v else []
    return "leer" if v is None else "ja/nein" if isinstance(v, bool) else "zahl" if isinstance(v, (int, float)) else "text"


def _zusammen(formen):
    out = formen[0]
    for f in formen[1:]:
        if isinstance(out, dict) and isinstance(f, dict):
            out = {k: (_zusammen([out[k], f[k]]) if k in out and k in f else out.get(k, f.get(k))) for k in sorted(set(out) | set(f))}
        elif isinstance(out, list) and isinstance(f, list):
            out = [_zusammen(out + f)] if out or f else []
        elif isinstance(out, str) and isinstance(f, str):
            out = "|".join(sorted(set(out.split("|")) | set(f.split("|"))))
        elif out != f:                  # einmal Objekt oder Liste, einmal leer: die reichere Form gilt, „leer“ steht dabei
            reich, arm = (out, f) if isinstance(out, (dict, list)) else (f, out)
            out = reich if arm == "leer" or isinstance(arm, (dict, list)) else reich
    return out


def felder(f, out=None):
    """Alle Feldnamen einer Form."""
    out = set() if out is None else out
    if isinstance(f, dict):
        for k, v in f.items():
            if k != "<nr>":
                out.add(k)
            felder(v, out)
    elif isinstance(f, list):
        for x in f:
            felder(x, out)
    return out


def unterschiede(soll, ist, pfad=""):
    """Wo zwei Formen auseinandergehen, als lesbare Zeilen."""
    if isinstance(soll, dict) and isinstance(ist, dict):
        out = []
        for k in sorted(set(soll) | set(ist)):
            if k not in ist:
                out.append(f"{pfad}.{k}: fehlt in der Antwort")
            elif k not in soll:
                out.append(f"{pfad}.{k}: neu in der Antwort ({json.dumps(ist[k], ensure_ascii=False)[:60]})")
            else:
                out += unterschiede(soll[k], ist[k], f"{pfad}.{k}")
        return out
    if isinstance(soll, list) and isinstance(ist, list) and soll and ist:
        return unterschiede(soll[0], ist[0], pfad + "[]")
    return [] if soll == ist else [f"{pfad}: {json.dumps(soll, ensure_ascii=False)[:60]} → {json.dumps(ist, ensure_ascii=False)[:60]}"]


# Eigene Daten, damit auch die Listen mit Eigenem eine Form haben: (Weg, Rumpf)
VORHER = (
    ("/api/gefangen", {"spiel": "emerald", "id": [1, 6]}),
    ("/api/gefangen", {"spiel": "scarlet-violet", "id": [1]}),
    ("/api/favoriten", {"spiel": "x-y", "id": 11}),
    ("/api/teams", {"name": "Vertrag", "spiel": "scarlet-violet", "mitglieder": [3, 5, 7], "fest": [3],
                    "details": {"3": {"level": 50, "attacken": [23, 13]}}}),
    ("/api/kampftagebuch", {"spiel": "scarlet-violet", "ergebnis": "sieg", "team": [3, 5], "gegner": [7, 9], "notiz": "Probe"}),
)
_SV = {"spiel": "scarlet-violet"}
# Name: (Weg, Rumpf oder None für GET). Die Namen sind die Abschnitte in vertrag.json.
AUFRUFE = {
    "meta": ("/api/meta", None),
    "stand": ("/api/stand", None),
    "status": ("/api/status", None),
    "statuskarte": ("/api/statuskarte", None),
    "neuigkeiten": ("/api/neuigkeiten", None),
    "fehler": ("/api/fehler", None),
    "liste": ("/api/pokemon?spiel=x-y", None),
    "detail": ("/api/pokemon/3?spiel=x-y", None),
    "detail mit Fundort": ("/api/pokemon/13?spiel=platinum", None),
    "detail Legenden: Arceus": ("/api/pokemon/14?spiel=legends-arceus", None),
    "attacken eines Pokémon": ("/api/pokemon/3/attacken?spiel=scarlet-violet", None),
    "attacken": ("/api/attacken?spiel=emerald", None),
    "items": ("/api/items?spiel=emerald", None),
    "typen": ("/api/typen?spiel=x-y", None),
    "fehlt": ("/api/fehlt?spiel=emerald", None),
    "fortschritt": ("/api/fortschritt?spiel=emerald", None),
    "fehlt in HOME": ("/api/fehlt?spiel=pokemon-home", None),
    "gebiete": ("/api/gebiete?spiel=x-y", None),
    "pruefung": ("/api/pruefung", None),
    "teams": ("/api/teams", None),
    "favoriten": ("/api/favoriten?spiel=x-y", None),
    "gefangen": ("/api/gefangen?spiel=emerald", None),
    "kampftagebuch": ("/api/kampftagebuch?spiel=scarlet-violet", None),
    "team bewerten": ("/api/team/bewerten", {**_SV, "ids": [3, 5, 7], "details": [{"attacken": [23, 13]}, {}, {"tera": 13}]}),
    "team optimieren": ("/api/team/optimieren", {**_SV, "filter": {"ohne_leg": 1}}),
    "team vorschlag": ("/api/team/vorschlag", {**_SV, "ids": [3]}),
    "team gegner": ("/api/team/gegner", {**_SV, "ids": [3, 5], "gegner": [7, 9]}),
    "team doppel": ("/api/team/doppel", {**_SV, "ids": [3, 5, 7, 9]}),
    "team gefangen": ("/api/team/gefangen", {**_SV, "ids": [5, 7]}),
    "team import": ("/api/team/import", {"text": "Dornwald @ Blattamulett\nAbility: Blattwerk\n- Saugwurzel\n\nGibtsnicht\n"}),
    "team export": ("/api/team/export", {"ids": [3], "details": [{"attacken": [23]}]}),
    "schaden": ("/api/schaden", {**_SV, "ids": [10], "details": [{"attacken": [13]}], "slot": 0, "attacke": 13, "verteidiger": [5, 9, 11]}),
    "schaden übersicht": ("/api/schaden/uebersicht", {**_SV, "ids": [3, 10], "details": [{"attacken": [23, 13]}, {"attacken": [13]}], "verteidiger": [5, 7]}),
    "werte": ("/api/werte", {**_SV, "id": 12, "level": 100, "evs": [0, 252, 0, 0, 4, 252]}),
    "effort": ("/api/effort", {"spiel": "legends-arceus", "id": 14, "level": 50}),
    "effort team": ("/api/effort/team", {"spiel": "legends-arceus", "ids": [14, 8]}),
    "wiederherstellung": ("/api/wiederherstellung", {}),
    "leistung": ("/api/leistung", {"spiel": "emerald"}),
}


def messen(test):
    """{Name: {"aufruf", "form"}} gegen den laufenden Server eines Tests (tests.basis.HttpTest mit Mini-Datenbank)."""
    for weg, rumpf in VORHER:
        test.json(weg, rumpf)
    out = {}
    for name, (weg, rumpf) in AUFRUFE.items():
        out[name] = {"aufruf": ("GET " if rumpf is None else "POST ") + weg, "form": form(test.json(weg, rumpf))}
    return out


def lesen():
    with open(DATEI, encoding="utf-8") as f:
        return json.load(f)


def schreiben():
    """tests/vertrag.json neu schreiben: der Server gegen die Mini-Datenbank, wie im Test."""
    from tests import basis

    class Messen(basis.HttpMitDaten):
        def runTest(self):
            self.neu = messen(self)

    t = Messen()
    t.setUp()
    try:
        t.runTest()
    finally:
        t.tearDown()
    with open(DATEI, "w", encoding="utf-8") as f:
        f.write("{\n" + ",\n".join(f" {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False, sort_keys=True)}"
                                   for k, v in t.neu.items()) + "\n}\n")
    return t.neu


if __name__ == "__main__":
    neu = schreiben()
    print(len(neu), "Aufrufe,", len({k for v in neu.values() for k in felder(v["form"])}), "Felder,", os.path.getsize(DATEI), "Byte")
