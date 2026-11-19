"""Karten: Map Genie und die anderen Kartenquellen, Kacheln, Vorrat, hochgeladene Kacheln, Regionskarten.

Teil des Pakets app.abruf; alle Namen sind auch dort erreichbar.
"""
import json
import os
import re
import sys
import threading
import time
from datetime import timedelta

from .. import (db, dittobase, fehler, ign, ironmon, mapgenie, pkcompletion, pokearth, pokewiki, raidnester,
    rankedboost, sources, store)

from .grundlage import (MG_403_MAX, MG_PAUSE, MG_STOCK_PAUSE, MG_TILE_PAUSE, MISS_DAYS, MISS_FILE, PAUSE, STATE,
    VORRAT_FILE, _Source, _hash, _iso, now, rest_set, rest_until, server_rest, sleep)
from .seiten import SEREBII_PAUSE


def mg_dir(*parts):
    return os.path.join(db.data_dir(), "mapgenie", *parts)


def _mapgenie(log):
    """Karten von Map Genie für alle Spiele in mapgenie.GAMES: je Spiel die Kartenseiten und die Orte, kompakt nach
    data/mapgenie/<Spiel>.json. Kacheln holt erst die Oberfläche (mg_tile). Spiele ohne Karte dort melden 404."""
    src = _Source("mapgenie", log, pause=MG_PAUSE)
    found = 0
    for spiel in mapgenie.GAMES:
        page = slug = None
        for slug in mapgenie.slugs(spiel):           # Schreibweise unsicher: die erste, die antwortet
            STATE["step"] = f"Map Genie: {slug}"
            page = src.get(mapgenie.game_url(slug), absent=(404,))
            if page or src.stopped:
                break
        if src.stopped:
            break
        if not page:
            continue
        maps = []
        for k in mapgenie.map_slugs(page, slug)[:12]:
            p = src.get(mapgenie.map_url(slug, k), absent=(404,))
            md = (mapgenie._var(p, "mapData") or {}).get("map") or {} if p else {}
            d = src.get(mapgenie.data_url(md["id"]), absent=(404,)) if md.get("id") else None
            m = mapgenie.parse(p, d) if p and d else None
            if m:
                m["slug"] = m["slug"] or k
                maps.append(m)
            if src.stopped:
                break
        if maps:
            os.makedirs(mg_dir(), exist_ok=True)
            store.save_json(os.path.join("mapgenie", spiel + ".json"), {"spiel": spiel, "slug": slug, "am": _iso(now()), "karten": maps})
            log(f"Map Genie: {slug} mit {len(maps)} Karten, {sum(len(m['orte']) for m in maps)} Orten")
            found += 1
    return src.result(dateien=found)


def _pkcompletion(log):
    """Karten von pokemoncompletion für die Spiele in pkcompletion.GAMES: Punkte aus den Spieldaten im Repository, in
    derselben Form wie Map Genie nach data/mapgenie/<Spiel>.json. Kacheln holt der Vorrat (mg_stock) vom CDN."""
    src = _Source("pkcompletion", log)
    found = 0
    for spiel, name in pkcompletion.GAMES.items():
        STATE["step"] = f"pokemoncompletion: {name}"
        text = src.get(pkcompletion.DATA.format(name), absent=(404,))
        if src.stopped:
            break
        m = pkcompletion.parse(text, spiel) if text else None
        if m:
            _save_maps(spiel, "pc", [m])
            log(f"pokemoncompletion: {name} mit {len(m['orte'])} Punkten")
            found += 1
    return src.result(dateien=found)


def _save_maps(spiel, quelle, karten):
    """Karten einer Quelle nach data/mapgenie/<Spiel>.<Quelle>.json (Map Genie selbst: <Spiel>.json)."""
    os.makedirs(mg_dir(), exist_ok=True)
    store.save_json(os.path.join("mapgenie", f"{spiel}.{quelle}.json"), {"spiel": spiel, "am": _iso(now()), "karten": karten})
    old = mg_dir(spiel + ".json")          # bis 0.28.3 lag pokemoncompletion unter <Spiel>.json
    if quelle == "pc" and (store.load_json(os.path.join("mapgenie", spiel + ".json"), {}) or {}).get("quelle") == "pokemoncompletion":
        os.remove(old)


def _ign(log):
    """Karten von IGN für die Spiele in ign.GAMES: Kartenseite, daraus Kachelmuster und die mitgelieferten Punkte; alle
    Punkte über die GraphQL-Abfrage, die auch die Seite stellt (ohne Antwort bleibt es bei denen der Seite)."""
    src = _Source("ign", log, pause=MG_PAUSE)
    found = 0
    for spiel, (slug, karten) in ign.GAMES.items():
        maps = []
        for k in karten:
            STATE["step"] = f"IGN: {slug}/{k}"
            page = src.get(ign.page_url(slug, k), absent=(404,))
            if src.stopped:
                break
            m = ign.parse(page, k) if page else None
            q = ign.query(m)
            if q:
                STATE["step"] = f"IGN: Punkte {slug}/{k}"
                more = ign.markers(src.get(ign.GRAPH, data=q) or "")
                if more:
                    m = ign.parse(page, k, more)
                else:
                    log(f"IGN: Abfrage der Punkte für {slug}/{k} ohne Antwort, nur die Punkte der Seite")
            if m:
                maps.append(m)
        if maps:
            _save_maps(spiel, "ign", maps)
            log(f"IGN: {slug} mit {len(maps)} Karten, {sum(len(m['orte']) for m in maps)} Punkten")
            found += 1
        if src.stopped:
            break
    return src.result(dateien=found)


def _dittobase(log):
    """Karten von DittoBase für die Spiele in dittobase.GAMES: Kartenseite (Spieldaten und Punkte), die Kachelsätze als
    Bilder, daraus zeichnet der Abgleich alle Kacheln selbst (kacheln/db/<Spiel>/). Gezeichnet wird nur, was fehlt oder
    sich geändert hat."""
    from .. import png
    src = _Source("dittobase", log, pause=MG_PAUSE)
    found = 0
    for spiel, slug in dittobase.GAMES.items():
        STATE["step"] = f"DittoBase: {slug}"
        page = src.get(dittobase.page_url(slug), absent=(404,))
        if src.stopped:
            break
        m, draw = dittobase.parse(dittobase.extract(page), spiel) if page else (None, None)
        if not m:
            if page:
                log(f"DittoBase: {slug} ohne Kartendaten (Seite geändert?)")
            continue
        sets, sdir = {}, mg_dir("kacheln", "db", "_saetze")
        os.makedirs(sdir, exist_ok=True)
        for n, (name, v) in enumerate(sorted(draw["saetze"].items())):
            f = os.path.join(sdir, name + ".png")
            if not os.path.isfile(f) and dittobase.tileset_ok(v["bild"]):
                STATE.update(step=f"DittoBase: Kachelsätze {slug}", done=n, total=len(draw["saetze"]))
                body = src.get(v["bild"], raw=True, absent=(404,))
                if body and body[:8] == png.SIG:
                    with open(f + ".neu", "wb") as fh:
                        fh.write(body)
                    os.replace(f + ".neu", f)
                elif src.stopped:
                    break
            if os.path.isfile(f):
                try:
                    with open(f, "rb") as fh:
                        sets[name] = png.decode(fh.read())
                except (OSError, ValueError, png.zlib.error) as e:
                    log(f"DittoBase: Kachelsatz {name} nicht lesbar ({e})")
        if src.stopped:
            break
        tdir = mg_dir("kacheln", "db", slug)
        stamp = _hash(json.dumps(draw, sort_keys=True), *sorted(sets))
        old = store.load_json(os.path.join("mapgenie", "kacheln", "db", slug, "stand.json"), {}) or {}
        same = old.get("stand") == stamp

        def have(z, x, y):
            return same and os.path.isfile(os.path.join(tdir, str(z), f"{x}-{y}.png"))

        def save(z, x, y, rgba):
            d = os.path.join(tdir, str(z))
            os.makedirs(d, exist_ok=True)
            f = os.path.join(d, f"{x}-{y}.png")
            with open(f + ".neu", "wb") as fh:
                fh.write(png.encode(dittobase.TILE, dittobase.TILE, rgba))
            os.replace(f + ".neu", f)

        def step(z, done, alle):
            STATE.update(step=f"DittoBase: Kacheln {slug} Stufe {z}", done=done, total=alle)
        n = dittobase.render_tiles(draw, sets, save, have, step)
        os.makedirs(tdir, exist_ok=True)
        store.save_json(os.path.join("mapgenie", "kacheln", "db", slug, "stand.json"), {"stand": stamp, "am": _iso(now())})
        _save_maps(spiel, "db", [m])
        log(f"DittoBase: {slug} mit {len(m['orte'])} Punkten, {len(sets)} von {len(draw['saetze'])} Kachelsätzen"
            + (f", {n} Kacheln gezeichnet" if n else ""))
        found += 1
    return src.result(dateien=found)


def _rankedboost(log):
    """Megakarten von RankedBoost für die Spiele in rankedboost.GAMES: Spielseite → Adresse der JSON-Datei → Orte mit
    Pokémon und die Ortsbilder (webp), die als Bildebene statt Kacheln auf der Karte liegen (kacheln/rb/<Karte>/<Nr>.webp).
    Was schon da ist, wird nicht wieder geholt."""
    src = _Source("rankedboost", log, pause=MG_PAUSE)
    found = 0
    for spiel, slug in rankedboost.GAMES.items():
        STATE["step"] = f"RankedBoost: {slug}"
        url = None
        for p in rankedboost.page_urls(spiel):
            url = rankedboost.json_url(src.get(p, absent=(404,)))
            if url or src.stopped:
                break
        if src.stopped:
            break
        if not url:
            log(f"RankedBoost: {slug} ohne Adresse der Kartendaten auf der Seite, es gilt die zuletzt bekannte")
            url = rankedboost.KNOWN.get(spiel)
        m, bilder = rankedboost.parse(rankedboost.extract(src.get(url, absent=(404,)) or "" if url else ""), spiel)
        if not m:
            if not src.stopped:
                log(f"RankedBoost: {slug} ohne lesbare Kartendaten")
            continue
        d = mg_dir("kacheln", "rb", m["slug"])
        os.makedirs(d, exist_ok=True)
        stand = store.load_json(os.path.join("mapgenie", "kacheln", "rb", m["slug"], "stand.json"), {}) or {}
        neu, have = 0, []
        for n, (nr, u, x, y, w, h) in enumerate(bilder):
            f = os.path.join(d, f"{nr}.webp")
            if not (os.path.isfile(f) and stand.get(str(nr)) == u) and not src.stopped:
                STATE.update(step=f"RankedBoost: Ortsbilder {slug}", done=n, total=len(bilder))
                body = src.get(u, raw=True, absent=(404,))
                if body and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
                    with open(f + ".neu", "wb") as fh:
                        fh.write(body)
                    os.replace(f + ".neu", f)
                    stand[str(nr)] = u
                    neu += 1
            if os.path.isfile(f):
                have.append([nr, x, y, w, h])
        store.save_json(os.path.join("mapgenie", "kacheln", "rb", m["slug"], "stand.json"), stand)
        m["bilder"] = have
        _save_maps(spiel, "rb", [m])
        log(f"RankedBoost: {slug} mit {len(m['orte'])} Orten, {len(have)} von {len(bilder)} Ortsbildern" + (f" ({neu} neu)" if neu else ""))
        found += 1
        if src.stopped:
            break
    return src.result(dateien=found)


def _ironmon(log):
    """HeartGold/SoulSilver aus der HGSS IronMON Map (GitHub): je Region Trainer und Items (TypeScript) und einmal das
    große Bild (kacheln/im/<Region>.webp, Kacheln daraus macht der Browser, tile_upload); mapgenie/<Spiel>.im.json."""
    src = _Source("ironmon", log, pause=PAUSE)
    found = 0
    for spiel, regs in ironmon.GAMES.items():
        maps = []
        for reg in regs:
            STATE["step"] = f"HGSS IronMON Map: {ironmon.REGION.get(reg, reg)}"
            bild, tr, it = ironmon.urls(reg)
            f = mg_dir("kacheln", "im", reg + ".webp")
            if not os.path.isfile(f):
                body = src.get(bild, raw=True, absent=(404,))
                if body and ironmon.webp_size(body[:64]):
                    os.makedirs(os.path.dirname(f), exist_ok=True)
                    with open(f + ".neu", "wb") as fh:
                        fh.write(body)
                    os.replace(f + ".neu", f)
            ts = [src.get(u, absent=(404,)) or "" for u in (tr, it)]
            if src.stopped:
                break
            if not os.path.isfile(f):
                log(f"HGSS IronMON Map: {reg} ohne Kartenbild")
                continue
            with open(f, "rb") as fh:
                size = ironmon.webp_size(fh.read(64))
            m = ironmon.parse(reg, *(size or (0, 0)), ironmon.objects(ts[0]), ironmon.objects(ts[1]))
            if m:
                maps.append(m)
        if maps:
            _save_maps(spiel, "im", maps)
            found += 1
            log("HGSS IronMON Map: " + ", ".join(f"{m['titel']} mit {len(m['orte'])} Punkten" for m in maps))
        if src.stopped:
            break
    return src.result(dateien=found)


def _raidnester(log):
    """Raid-Nester in Schwert/Schild aus dem PKHeX Raid Plugin (GitHub): Lage je Nest, Gebietsnamen und einmal die
    Bilder der drei Teile (kacheln/rn/<Teil>.png); je Spiel mapgenie/<Spiel>.rn.json."""
    src = _Source("raidnester", log, pause=PAUSE)
    ns = raidnester.nests(src.get(raidnester.NESTS, absent=(404,)) or "",
                          raidnester.location_names(src.get(raidnester.NAMES, absent=(404,)) or ""))
    if not ns:
        if not src.stopped:
            log("PKHeX Raid Plugin: keine Raid-Nester gelesen")
        return src.result(dateien=0)
    tabs = raidnester.tables(src.get(raidnester.TABLES, absent=(404,)) or "") if not src.stopped else {}
    names = {}
    try:
        con = db.game()
        try:
            names = {i: n for i, n in con.execute("SELECT pokemon_species_id, name FROM pokemon_species_names WHERE local_language_id = 6") if n}
        finally:
            con.close()
    except Exception as e:
        fehler.melden(e, "Namen für Raid-Nester", "raidnester")
    found = 0
    for area, (spiel, bild, _, _) in raidnester.AREAS.items():
        STATE["step"] = f"PKHeX Raid Plugin: {area}"
        f = mg_dir("kacheln", "rn", area + ".png")
        if not os.path.isfile(f) and not src.stopped:
            body = src.get(raidnester.BASE + bild, raw=True, absent=(404,))
            if body and raidnester.png_size(body):
                os.makedirs(os.path.dirname(f), exist_ok=True)
                with open(f + ".neu", "wb") as fh:
                    fh.write(body)
                os.replace(f + ".neu", f)
        if not os.path.isfile(f):
            continue
        with open(f, "rb") as fh:
            m = raidnester.parse(ns, area, *(raidnester.png_size(fh.read(32)) or (0, 0)), tabs=tabs, names=names)
        if m:
            _save_maps(spiel, "rn", [m])
            found += 1
    n_tab = sum(len(v) for v in tabs.values())
    log(f"PKHeX Raid Plugin: {len(ns)} Raid-Nester auf {found} Karten" + (f", Inhalt aus {n_tab} Tabellen" if n_tab else ", ohne Inhalt der Nester"))
    return src.result(dateien=found)


def tile_convert_state(spiel, karte):
    """Umwandlung einer Bildkarte in Kacheln (HGSS IronMON Map): {fertig, bild, w, h, z, min, kachel, fehlen} oder None."""
    m = _mg_map(spiel, karte)
    if not m or m.get("quelle") != "ironmon":
        return None
    d = mg_dir("kacheln", "im", m["region"])
    fehlen = 0
    for z in range(m["min_zoom"], m["max_zoom"] + 1):
        nx, ny = ironmon.tile_range(m, z)
        fehlen += sum(1 for x in range(nx) for y in range(ny) if not os.path.isfile(os.path.join(d, str(z), f"{x}-{y}.png")))
    return {"fertig": not fehlen, "fehlen": fehlen, "bild": mg_image(spiel, karte, 0) is not None, "w": m["dim"]["w"],
            "h": m["dim"]["h"], "z": m["bild_z"], "min": m["min_zoom"], "kachel": m["kachel"]}


TILE_UPLOAD_MAX = 400_000      # Bytes je Kachel (PNG); eine Kachel der Karte hat meist unter 100 KB


def tile_upload(b):
    """Kacheln, die der Browser aus dem Bild einer Karte geschnitten hat: {spiel, karte, kacheln: [[z, x, y, PNG als
    Base64]]}. Nur Karten, deren Bild der Server selbst geholt hat, nur Kacheln innerhalb der Karte, nur PNG."""
    import base64
    m = _mg_map(str(b.get("spiel") or ""), str(b.get("karte") or ""))
    if not m or m.get("quelle") != "ironmon":
        raise ValueError("keine Karte zum Umwandeln")
    n = 0
    for k in (b.get("kacheln") or [])[:64]:
        if not (isinstance(k, list) and len(k) == 4 and all(isinstance(v, int) for v in k[:3]) and isinstance(k[3], str)):
            raise ValueError("Kachel ungültig")
        rel = ironmon.tile(m, *k[:3])
        body = base64.b64decode(k[3], validate=True) if rel and len(k[3]) < TILE_UPLOAD_MAX * 4 // 3 + 4 else b""
        if not rel or body[:8] != b"\x89PNG\r\n\x1a\n" or len(body) > TILE_UPLOAD_MAX:
            raise ValueError("Kachel ungültig")
        f = mg_dir("kacheln", *rel[0].split("/"))
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f + ".neu", "wb") as fh:
            fh.write(body)
        os.replace(f + ".neu", f)
        n += 1
    return {"gespeichert": n}


def _pokearth(log):
    """Regionskarten von Serebii (PokéEarth) für die Spiele in pokearth.GAMES: je Region die Seite und einmal das Bild
    (kacheln/se/<Region>.<Endung>), dann je Spiel die Karten seiner Regionen (mapgenie/<Spiel>.se.json)."""
    src = _Source("pokearth", log, pause=SEREBII_PAUSE)
    have = {}
    for i, reg in enumerate(pokearth.regions()):
        STATE.update(step=f"Serebii PokéEarth: {pokearth.REGION.get(reg, reg)}", done=i, total=len(pokearth.regions()))
        d = pokearth.extract(src.get(pokearth.page_url(reg), absent=(404,)) or "")
        if src.stopped:
            break
        if not d and pokearth.PW_MAPS.get(reg, {}).get("inseln"):     # 0.56: Alola, eine Karte je Insel
            ms = [m for m in (_pw_island(src, reg, t) for t in _pw_islands(src, reg)) if m]
            if ms:
                have[reg] = ms
            else:
                log(f"Serebii PokéEarth: {reg} ohne Bildkarte")
            continue
        if not d and reg in pokearth.PW_MAPS:      # 0.48: Bildkarte aus dem PokéWiki, großes Bild von Bulbapedia
            d = _pw_region(src, reg)
        m = pokearth.parse(d, reg)
        if not m:
            log(f"Serebii PokéEarth: {reg} ohne Bildkarte")
            continue
        _region_image(src, m, d)
        have[reg] = [m]
    found = 0
    for spiel, regs in pokearth.GAMES.items():
        ks = [m for r in regs if r in have for m in have[r]]
        if ks:
            _save_maps(spiel, "se", ks)
            found += 1
    if have:
        log(f"Serebii PokéEarth: {len(have)} Regionen mit {sum(len(m['orte']) for ms in have.values() for m in ms)} Orten für {found} Spiele")
    return src.result(dateien=found)


def _region_image(src, m, d):
    """Bild einer Regions- oder Inselkarte einmal holen (kacheln/se/…); ohne Bild bleibt die Karte ohne Bildebene."""
    rel = m["bilder"][0][5]
    f = mg_dir("kacheln", *rel.split("/"))
    if not os.path.isfile(f):
        body = src.get(d["bild"], raw=True, absent=(404,))
        if body and (body[:8] == b"\x89PNG\r\n\x1a\n" or body[:3] == b"\xff\xd8\xff" or body[:4] == b"GIF8"):
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f + ".neu", "wb") as fh:
                fh.write(body)
            os.replace(f + ".neu", f)
    if not os.path.isfile(f):
        m["bilder"] = []


def _pw_islands(src, reg):
    """0.56: Orte je Insel aus der PokéWiki-Vorlage (pokearth.pw_islands)."""
    try:
        wt = next(iter(pokewiki.pages(src.get(pokearth.pw_template_url(reg)) or "{}").values()), "")
    except ValueError as ex:
        fehler.melden(ex, f"Orte je Insel: {reg}", "pokewiki")
        wt = ""
    return pokearth.pw_islands(wt, reg)


def _pw_island(src, reg, t):
    """Karte einer Insel: Orte aus der Bildkarte, Bild in Originalgröße aus dem PokéWiki."""
    key, title, f, orte = t
    small = pokearth.imageinfo(src.get(pokearth.imageinfo_url(pokearth.PW_API, f)))
    m = pokearth.parse(pokearth.pw_map(orte, small), reg, (key, title))
    if m:
        _region_image(src, m, {"bild": small[0]})
    src.log(f"PokéWiki-Bildkarte {pokearth.REGION.get(reg, reg)}, {title}: {len(orte)} Orte, Bild "
            + (f"{small[1]}×{small[2]}" if small else "fehlt"))
    return m


def _pw_region(src, reg):
    """Regionskarte aus einer PokéWiki-Vorlage (Orte) mit dem kleinen Bild von dort oder dem großen von Bulbapedia."""
    cfg = pokearth.PW_MAPS[reg]
    try:
        wt = next(iter(pokewiki.pages(src.get(pokearth.pw_template_url(reg)) or "{}").values()), "")
    except ValueError as ex:
        fehler.melden(ex, f"Regionskarte: {reg}", "pokewiki")
        wt = ""
    orte = pokearth.pw_areas(wt)
    small = pokearth.imageinfo(src.get(pokearth.imageinfo_url(pokearth.PW_API, cfg["bild"])))
    big = pokearth.imageinfo(src.get(pokearth.imageinfo_url(pokearth.BULBA_API, cfg["gross"]))) if cfg.get("gross") else None
    d = pokearth.pw_map(orte, small, big)
    src.log(f"PokéWiki-Bildkarte {pokearth.REGION.get(reg, reg)}: {len(orte)} Orte, Bild "
            + (f"{d['w']}×{d['h']} von {'Bulbapedia' if 'bulbagarden' in d['bild'] else 'PokéWiki'}" if d else "fehlt"))
    return d


def mg_image(spiel, karte, nr):
    """Pfad eines Bilds einer Bildkarte (RankedBoost: Ortsbilder, Serebii: Regionsbild) im Datenordner oder None. Ohne
    Netz: die Bilder holt der Abgleich."""
    m = _mg_map(spiel, karte)
    b = next((b for b in ((m or {}).get("bilder") or []) + ([m["quellbild"]] if (m or {}).get("quellbild") else []) if b[0] == nr), None)
    if not b:
        return None
    rel = b[5] if len(b) > 5 and re.fullmatch(r"[a-z]{2}/[\w.-]+", str(b[5])) and ".." not in b[5] else f"rb/{m['slug']}/{nr}.webp"
    f = mg_dir("kacheln", *rel.split("/"))
    return f if os.path.isfile(f) else None


MAP_GAMES = tuple(dict.fromkeys((*mapgenie.GAMES, *pkcompletion.GAMES, *ign.GAMES, *dittobase.GAMES, *rankedboost.GAMES, *ironmon.GAMES, *raidnester.GAMES, *pokearth.GAMES)))   # Spiele mit eigener Karte
MAP_FILES = ("", ".pc", ".ign", ".rn", ".db", ".rb", ".im", ".se")   # je Spiel eine Datei je Quelle; die Karten erscheinen in dieser Reihenfolge


def mg_maps(spiel):
    """Gespeicherte Karten eines Spiels aus allen Quellen (Erweiterungen und Schwester-Editionen: die des Hauptspiels)
    als {spiel, am, karten} oder None. Hat die Schwester-Edition eigene Karten (Gold/Silber bei DittoBase), stehen sie
    vorn; vom Hauptspiel kommen dann nur Karten anderer Quellen dazu."""
    share = mapgenie.SHARE.get(spiel) or pkcompletion.SHARE.get(spiel)
    fs = []
    for g in dict.fromkeys((spiel, share)):
        for suf in MAP_FILES if g in MAP_GAMES else ():
            if suf == ".rb" and g not in rankedboost.GAMES:
                continue                 # frühere Karte einer Quelle, die für dieses Spiel nicht mehr gilt
            try:
                fs.append((g, suf, os.path.getmtime(mg_dir(g + suf + ".json"))))
            except OSError:
                pass
    if not fs:
        return None
    key = spiel if fs[0][0] == spiel else fs[0][0]
    hit = _mg_cache.get(key)
    if not hit or hit[0] != fs:
        out = {"spiel": key, "am": "", "karten": []}
        own = set()
        for g, suf, _ in fs:
            d = store.load_json(os.path.join("mapgenie", g + suf + ".json"), {}) or {}
            ks = d.get("karten") or []
            if g == key:
                own |= {k.get("quelle") or "mapgenie" for k in ks}
            else:
                ks = [k for k in ks if (k.get("quelle") or "mapgenie") not in own]
            out["karten"] += ks
            out["am"] = max(out["am"], str(d.get("am") or ""))
        hit = _mg_cache[key] = (fs, out if out["karten"] else None)
    return hit[1]


_mg_cache = {}


_mg_lock = threading.Lock()
_mg = {"last": 0.0, "miss": set(), "fehler": "", "n403": 0, "vorrat": {}, "laeuft": False, "ok": ""}


def _tile_rest(quelle=None):
    """Schlüssel der Ruhezeit für Kacheln: Map Genie "kacheln", andere Quellen "kacheln:<Quelle>". Seit 0.58.0 in
    ruhe.json (rest_set, rest_until); vorher nur im Speicher, ein Neustart fragte eine gesperrte Quelle sofort wieder."""
    return "kacheln:" + quelle if quelle in TILE_SRC else "kacheln"


def _miss_load():
    """Fehlende Kacheln vom letzten Lauf (höchstens MISS_DAYS alt) und den Stand des Vorrats einmal je Start lesen."""
    if _mg.get("miss_da"):
        return
    _mg["miss_da"] = True
    old = _iso(now() - timedelta(days=MISS_DAYS))[:10]
    got = store.load_json(MISS_FILE, {}) or {}
    _mg["miss_am"] = {k: v for k, v in got.items() if isinstance(v, str) and v >= old}
    _mg["miss"] |= set(_mg["miss_am"])
    for k, v in (store.load_json(VORRAT_FILE, {}) or {}).items():
        _mg["vorrat"].setdefault(k, v)


def _miss_add(rel, kept=True):
    _mg["miss"].add(rel)
    if kept:
        _mg.setdefault("miss_am", {})[rel] = _iso(now())[:10]
        if time.monotonic() - _mg.get("miss_t", 0) > 60:
            _miss_save()


def _miss_save():
    _mg["miss_t"] = time.monotonic()
    try:
        store.save_json(MISS_FILE, dict(_mg.get("miss_am") or {}))
        store.save_json(VORRAT_FILE, dict(_mg["vorrat"]))
    except OSError as e:
        print("Kachelvorrat speichern:", e, file=sys.stderr)


def mg_status():
    """Zustand der Kacheln für die Oberfläche: ruht bis (ISO oder leer), letzter Fehler, Vorrat je Karte
    {"<Spiel>/<Karte>": {"da": n, "alle": m, "bis": Zoom}} und ob der Vorrat gerade lädt."""
    _miss_load()
    return {"ruht": rest_until(_tile_rest()), "fehler": _mg["fehler"],
            "vorrat": dict(_mg["vorrat"]), "laedt": _mg["laeuft"]}


def _mg_map(spiel, karte):
    d = mg_maps(spiel)
    return next((m for m in (d or {}).get("karten", []) if m["slug"] == karte), None)


def mg_stock():
    """Kachelvorrat im Hintergrund: holt für jede Karte von Map Genie alle Kacheln aller Zoomstufen, mit Pause; was da
    ist, bleibt. Erst alle Karten bis eine Stufe unter der größten (weite Stufen zuerst), dann die größte Stufe. Danach
    braucht die Karte kein Netz mehr. Ein Lauf zur Zeit."""
    if _mg["laeuft"]:
        return
    _mg["laeuft"] = True
    _miss_load()
    try:
        jobs = [(spiel, m, top) for top in (1, 0) for spiel in MAP_GAMES for m in (mg_maps(spiel) or {}).get("karten", [])]
        for spiel, m, top in jobs:
            q = m.get("quelle")
            ts = TILE_SRC.get(q, mapgenie).tile_list(m, m["max_zoom"] - top)
            key = f"{spiel}/{m['slug']}"
            have = 0
            for i, (z, x, y) in enumerate(ts):
                if rest_until(_tile_rest(q)):
                    break
                rel = _tile_of(m, z, x, y)[0]
                if not rel or rel in _mg["miss"]:
                    pass
                elif os.path.isfile(mg_dir("kacheln", *rel.split("/"))):
                    have += 1
                else:
                    # die Pause des Vorrats außerhalb der Sperre: Kacheln, die die Karte gerade braucht, warten nicht
                    if m.get("quelle") not in TILE_SRC or _tile_of(m, z, x, y)[1]:
                        sleep(MG_STOCK_PAUSE)
                    if mg_tile(spiel, m["slug"], z, x, y, pause=MG_TILE_PAUSE, stock=True):
                        have += 1
                if i % 50 == 0 or i == len(ts) - 1:
                    _mg["vorrat"][key] = {"da": have, "alle": len(ts), "bis": m["max_zoom"] - top, "fertig": i == len(ts) - 1,
                                          "ganz": not top}
            _miss_save()
    except Exception as e:          # der Vorrat darf den Dienst nicht stören
        fehler.melden(e, "Kachelvorrat", "kacheln", immer=True)
    finally:
        _mg["laeuft"] = False


def start_stock():
    if not _mg["laeuft"]:
        threading.Thread(target=mg_stock, daemon=True, name="kachelvorrat").start()


def _mg_probe():
    """Nach vielen 403 nacheinander: kommt eine Kachel, die es sicher gibt, noch? Dann sperrt Map Genie nicht, sondern
    die Kacheln fehlen nur (Ränder, Meer). Ohne bekannte Kachel False."""
    if not _mg.get("ok"):
        return False
    try:
        sources.fetch(mapgenie.TILES + _mg["ok"], timeout=30, raw=True)
        return True
    except sources.FetchError:
        return False
    finally:
        _mg["last"] = time.monotonic()


def _tile_of(m, z, x, y):
    """(Pfad unter kacheln/, Adresse) einer Kachel, (None, None) außerhalb der Karte."""
    if m.get("quelle") in TILE_SRC:
        return TILE_SRC[m["quelle"]].tile(m, z, x, y) or (None, None)
    rel = mapgenie.tile_ok(m["kacheln"], z, x, y, m.get("endung", "png"))
    if not rel or not (m["min_zoom"] <= z <= m["max_zoom"]):
        return None, None
    r = mapgenie.tile_range(mapgenie.bounds_of(m), z)
    if r and not (r[0] <= x <= r[1] and r[2] <= y <= r[3]):
        return None, None                # außerhalb der Karte gibt es keine Kachel; nicht nachfragen
    return rel, mapgenie.TILES + rel


def mg_tile(spiel, karte, z, x, y, pause=MG_TILE_PAUSE, stock=False):
    """Pfad einer Kachel im Datenordner; fehlt sie, einmal bei der Quelle holen (eine Anfrage zur Zeit, kurze Pause).
    Ein einzelnes 403 heißt bei Map Genie „Kachel gibt es nicht“; erst viele nacheinander oder 429 lassen die Quelle
    24 Stunden ruhen. pokemoncompletion ruht schon nach einem 403 oder 429. None, wenn es sie nicht gibt.
    Hat der Vorrat die Karte ganz durchgesehen, fragt die Oberfläche nicht mehr nach: was fehlt, gibt es nicht."""
    m = _mg_map(spiel, karte)
    rel, url = _tile_of(m, z, x, y) if m else (None, None)
    if not rel:
        return None
    f = mg_dir("kacheln", *rel.split("/"))
    if os.path.isfile(f):
        return f
    _miss_load()
    sp = (mg_maps(spiel) or {}).get("spiel", spiel)
    v = _mg["vorrat"].get(f"{sp}/{karte}") or {}
    if not stock and v.get("fertig") and v.get("ganz"):
        return None
    if m.get("quelle") in TILE_SRC:
        return _cdn_tile(rel, url, f, pause, m["quelle"]) if url else None      # ohne Adresse: selbst gezeichnet
    with _mg_lock:
        if os.path.isfile(f):
            return f
        if rel in _mg["miss"] or rest_until(_tile_rest()):
            return None
        wait = _mg["last"] + pause - time.monotonic()
        if wait > 0:
            sleep(wait)
        try:
            body = sources.fetch(mapgenie.TILES + rel, timeout=30, raw=True)
        except sources.FetchError as e:
            _mg["fehler"] = f"HTTP {e.status or '?'} bei {rel} ({_iso(now())[:16].replace('T', ' ')})"
            _mg["n403"] = _mg["n403"] + 1 if e.status == 403 else 0
            if e.status == 403 and _mg["n403"] >= MG_403_MAX and _mg_probe():
                _mg["n403"] = 0          # bekannte Kachel kommt noch: am Rand gibt es eben viele leere Kacheln
                _mg["r403"] = []
            if e.status == 429 or _mg["n403"] >= MG_403_MAX:
                rest_set(_tile_rest())
                rest_set(server_rest(mapgenie.TILES))
                for r in _mg.get("r403") or []:            # das war eine Sperre, keine fehlenden Kacheln
                    _mg["miss"].discard(r)
                    (_mg.get("miss_am") or {}).pop(r, None)
                _mg["r403"] = []
            elif e.status:
                _mg.setdefault("r403", []).append(rel)
                _miss_add(rel, e.status in (403, 404))
            return None
        finally:
            _mg["last"] = time.monotonic()
        _mg["n403"] = 0
        _mg["r403"] = []
        _mg["ok"] = rel
        if not (body[:8] == b"\x89PNG\r\n\x1a\n" or body[:3] == b"\xff\xd8\xff" or body[8:12] == b"WEBP"):
            _miss_add(rel)
            return None
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f + ".neu", "wb") as fh:
            fh.write(body)
        os.replace(f + ".neu", f)
        return f


TILE_SRC = {"pokemoncompletion": pkcompletion, "ign": ign, "dittobase": dittobase, "rankedboost": rankedboost, "ironmon": ironmon, "raidnester": raidnester, "pokearth": pokearth}     # Kartenquellen mit eigenem Kachelschema


def _cdn_tile(rel, url, f, pause, quelle):
    """Kachel einer anderen Quelle als Map Genie holen; nach 403 oder 429 ruht nur diese Quelle."""
    with _mg_lock:
        if os.path.isfile(f):
            return f
        if rel in _mg["miss"] or rest_until(_tile_rest(quelle)):
            return None
        wait = _mg["last"] + pause - time.monotonic()
        if wait > 0:
            sleep(wait)
        try:
            body = sources.fetch(url, timeout=30, raw=True)
        except sources.FetchError as e:
            _mg["fehler"] = f"{quelle}: HTTP {e.status or '?'} bei {rel} ({_iso(now())[:16].replace('T', ' ')})"
            if e.status in (403, 429):
                rest_set(_tile_rest(quelle))
                rest_set(server_rest(url))
            elif e.status:
                _miss_add(rel, e.status == 404)
            return None
        finally:
            _mg["last"] = time.monotonic()
        if not (body[:8] == b"\x89PNG\r\n\x1a\n" or body[:3] == b"\xff\xd8\xff"):
            _miss_add(rel)
            return None
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f + ".neu", "wb") as fh:
            fh.write(body)
        os.replace(f + ".neu", f)
        return f
