"""Quellen der Spieldaten außer PokéAPI und Showdown: PKHeX, Spawnpunkte, Altissimo, Begleiter.

Teil des Pakets app.abruf; alle Namen sind auch dort erreichbar.
"""
import os
from datetime import timedelta

from .. import altissimo, companion, db, fehler, importer

from .grundlage import (PKHEX_GAMES, PKHEX_ITEMS, PKHEX_RAW, PKHEX_SRC, PLA_MAPS, REST_H, SPAWN_POINTS, SPAWN_SLOTS,
    STATE, _Source, _iso, _resting, now)


def _pkhex(st, log, at):
    """Begegnungsdateien aus PKHeX (Spieldaten, GPL-3.0): {Spielkennung: {"begegnungen": Bytes, "orte": Text,
    "orte3": Text (Orte ab 30000: Geschenke), "fest": Quelltext}}."""
    if _resting(st, "pkhex", at):
        log(f"PKHeX ruht bis {st['rest']['pkhex'][:16].replace('T', ' ')} UTC")
        return {}
    src = _Source("pkhex", log)
    out = {}
    texts = {}
    for spiel, (enc, names, fixed) in PKHEX_GAMES.items():
        STATE["step"] = f"PKHeX: {spiel}"
        enc, _, enc2 = enc.partition("|")          # zweite Datei: die andere Edition
        b = src.get(PKHEX_RAW + enc, raw=True)
        for f in (names, names.replace("_00000_", "_30000_")) if b else ():
            if f not in texts:
                texts[f] = src.get(PKHEX_RAW + f) or ""
        t = texts.get(names)
        if b and t:
            out[spiel] = {"begegnungen": b, "orte": t, "orte3": texts.get(names.replace("_00000_", "_30000_"), ""),
                          "fest": (src.get(PKHEX_SRC + fixed) or "") if fixed else ""}
            if enc2:
                out[spiel]["begegnungen2"] = src.get(PKHEX_RAW + enc2, raw=True) or b""
    # Tera-Raids in Karmesin/Purpur (importer.PKHEX_RAIDS)
    STATE["step"] = "PKHeX: Tera-Raids"
    raids = {k: src.get(PKHEX_RAW + f"legality/wild/Gen9/encounter_{k}.pkl", raw=True) for k in importer.PKHEX_RAIDS}
    if any(raids.values()):
        out["_raids"] = {k: v for k, v in raids.items() if v}
    # Crypto-Pokémon in Colosseum und XD (importer.PKHEX_SHADOW)
    STATE["step"] = "PKHeX: Crypto-Pokémon"
    shadow = {k: src.get(PKHEX_SRC + f) for k, f in importer.PKHEX_SHADOW.items()}
    if any(shadow.values()):
        out["_crypto"] = {k: v for k, v in shadow.items() if v}
    # Lernlisten für Spiele ohne Lernliste in der PokéAPI (importer.PKHEX_LEARN)
    for key in importer.PKHEX_LEARN:
        STATE["step"] = f"PKHeX: Lernlisten {key}"
        lvl = src.get(PKHEX_RAW + f"byte/levelup/lvlmove_{key}.pkl", raw=True)
        per = src.get(PKHEX_RAW + f"byte/personal/personal_{key}", raw=True) if lvl else None
        if lvl and per:
            out[f"_lernen_{key}"] = {"lvl": lvl, "personal": per}
    # 0.50: Werte je Form in Legenden: Arceus, für die eigenen Fangraten des Spiels (importer._derive_fangrate)
    STATE["step"] = "PKHeX: Fangraten Legenden: Arceus"
    per = src.get(PKHEX_RAW + "byte/personal/personal_la", raw=True)
    if per:
        out["_fang_la"] = {"personal": per}
    # Itemlisten je Spiel und die Itemnamen (deutsch, englisch) für Spiele ohne Liste in der PokéAPI
    STATE["step"] = "PKHeX: Items"
    items = {lang: src.get(PKHEX_RAW + f"text/items/text_Items_{lang}.txt") for lang in ("de", "en")}
    if items["de"] and items["en"]:
        for key in importer.ITEM_LISTS:
            t = src.get(PKHEX_ITEMS + f"ItemStorage{key}.cs")
            if t:
                items[key] = t
        out["_items"] = items
    st["sources"]["pkhex"] = src.result(dateien=sum(len(v) for v in out.values()))
    if src.blocked:
        st["rest"]["pkhex"] = _iso(now() + timedelta(hours=REST_H))
    return out


def _spawns(st, log, at):
    """Spawnpunkte (JS-Finder) und ihre Tabellen nach Tageszeit und Wetter (PLA-Live-Map), beide GPL-3.0:
    {Spielkennung: {Karte: {"gebiet": Name, "punkte": Text, "plaetze": Text}}}."""
    if _resting(st, "spawns", at):
        log(f"Spawnpunkte ruhen bis {st['rest']['spawns'][:16].replace('T', ' ')} UTC")
        return {}
    src = _Source("spawns", log)
    maps = {}
    for karte, gebiet in PLA_MAPS.items():
        STATE["step"] = f"Spawnpunkte: {gebiet}"
        p = src.get(SPAWN_POINTS + karte + ".json")
        t = src.get(SPAWN_SLOTS + karte + ".json") if p else None
        if p and t:
            maps[karte] = {"gebiet": gebiet, "punkte": p, "plaetze": t}
    st["sources"]["spawns"] = src.result(dateien=2 * len(maps))
    if src.blocked:
        st["rest"]["spawns"] = _iso(now() + timedelta(hours=REST_H))
    return {"legends-arceus": maps} if maps else {}


def _altissimo(st, log, at):
    """Kartensymbole, Sammelobjekte und Rezepte für Legenden: Arceus von Altissimo (GPL-3.0):
    {"legends-arceus": {"symbole": {Karte: Text}, "sammeln": {Karte: Text}, "rezepte": HTML}}. Dazu einmal das Kartenbild
    von Jubeldorf in den Datenordner (karten/jubilifevillage/bild.png)."""
    if _resting(st, "altissimo", at):
        log(f"Altissimo ruht bis {st['rest']['altissimo'][:16].replace('T', ' ')} UTC")
        return {}
    src = _Source("altissimo", log)
    sym, col = {}, {}
    for karte, area in altissimo.AREAS.items():
        STATE["step"] = f"Altissimo: {altissimo.GEBIETE[karte]}"
        t = src.get(altissimo.landmarks_url(area))
        if t:
            sym[karte] = t
        t = src.get(altissimo.collectibles_url(area))
        if t:
            col[karte] = t
    t = src.get(altissimo.collectibles_url("jubilife"))
    if t:
        col[altissimo.VILLAGE] = t
    STATE["step"] = "Altissimo: Rezepte"
    rec = src.get(altissimo.RECIPES_URL) or ""
    image = os.path.join(db.data_dir(), "karten", altissimo.VILLAGE, "bild.png")
    if not os.path.isfile(image) and not src.stopped:
        STATE["step"] = "Altissimo: Karte von Jubeldorf"
        b = src.get(altissimo.VILLAGE_IMAGE, raw=True)
        if b and b[:8] == b"\x89PNG\r\n\x1a\n":
            os.makedirs(os.path.dirname(image), exist_ok=True)
            with open(image + ".neu", "wb") as f:
                f.write(b)
            os.replace(image + ".neu", image)
    st["sources"]["altissimo"] = src.result(dateien=len(sym) + len(col) + bool(rec))
    if src.blocked:
        st["rest"]["altissimo"] = _iso(now() + timedelta(hours=REST_H))
    if not sym and not col and not rec:
        return {}
    return {"legends-arceus": {"symbole": sym, "sammeln": col, "rezepte": rec}}


def _companion(st, log, at):
    """Schnellreise und Lager aus dem PLA Companion (software-notion.de): {Karte: Text der Kartendaten}. Zwei Sekunden
    Pause je Anfrage; bei Sperre ruht die Quelle wie die anderen."""
    if _resting(st, "companion", at):
        log(f"PLA Companion ruht bis {st['rest']['companion'][:16].replace('T', ' ')} UTC")
        return {}
    src = _Source("companion", log, pause=2.0)
    out = {}
    for karte in companion.MAPS:
        STATE["step"] = f"PLA Companion: {altissimo.GEBIETE.get(karte, karte)}"
        t = src.get(companion.url(karte))
        if src.stopped:
            break
        if t:
            out[karte] = t
    kinds = {}
    for t in out.values():
        try:
            for e in companion.entries(t):
                kinds[e["t"]] = kinds.get(e["t"], 0) + 1
        except ValueError as ex:
            fehler.melden(ex, "Einträge zählen", "companion")
    if kinds:          # welche Arten es gibt, damit sich weitere Ebenen planen lassen
        log("PLA Companion: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
    st["sources"]["companion"] = src.result(dateien=len(out))
    if src.blocked:
        st["rest"]["companion"] = _iso(now() + timedelta(hours=REST_H))
    return out
