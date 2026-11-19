"""Verbindungstest: jede Quelle einmal fragen, Proben für neue Leser.

Teil des Pakets app.abruf; alle Namen sind auch dort erreichbar.
"""
import base64
import json
import re
import threading
import time
import urllib.parse

from .. import (altissimo, bisafans, companion, db, dittobase, ign, importer, mapgenie, pokearth, pokewiki, raidnester,
    serebii, smogon, sources)

from .grundlage import (CSV_RAW, GH_API, MG_PAUSE, PAUSE, PKHEX_ITEMS, PKHEX_RAW, PKHEX_SRC, POKEAPI_RAW, POKEWIKI_API,
    PROBE_MAX, SD_RAW, SPAWN_POINTS, SPAWN_SLOTS, SPRITE_RAW, WIKI_PAUSE, _HOST_LAST, _host_lock, now, pkhex_areas,
    rest_until, server_rest, sleep)
from .medien import GAMERGUIDES, MAP_TILES, POKEBIP, SEREBII
from .wiki import _wiki_page
from .seiten import SEREBII_PAUSE
from .karten import MAP_GAMES, _tile_of, mg_maps, mg_status


# Pausen im Verbindungstest je Server (sonst PAUSE): wer beim Abgleich langsamer abgefragt wird, auch hier
DIAG_TIMEOUT = 20           # Sekunden ohne Antwort, dann gibt eine Abfrage im Verbindungstest auf
DIAG_LIMIT = 60             # Sekunden insgesamt je Abfrage (große Seiten, die langsam tröpfeln)
DIAG_HANG = 120             # Sekunden ohne jeden Fortschritt, dann beendet sich der Test trotz offener Abfragen
DIAG_PARALLEL = 6           # so viele Abfragen gleichzeitig (mehr überlastete die Namensauflösung: „Errno -3 Try again“)
DIAG_PAUSE = {"www.serebii.net": SEREBII_PAUSE, "www.pokewiki.de": WIKI_PAUSE, "mapgenie.io": MG_PAUSE}


def tile_patterns(t, limit=50):
    """Kachelmuster wie „…/{z}/{x}/{y}.png“ in einer Seite. Sucht nur rund um jedes „{z}“: ein Muster mit führendem
    [\\w…]* über die ganze Seite braucht bei langen Wortketten (Base64 in großen Seiten) quadratisch lange und hielt
    mit dem GIL den ganzen Dienst fest."""
    out, i = set(), t.find("{z}")
    while i >= 0 and len(out) < limit:
        win = t[max(0, i - 200):i + 200]
        m = re.search(r"[\w/.:-]{0,200}\{z\}[\w/.{}-]{0,200}", win)
        if m:
            out.add(m.group(0))
        i = t.find("{z}", i + 3)
    return sorted(out)


def diagnose(proben=None, stand=None):
    """Verbindung testen: jede Quelle einmal abfragen und beschreiben, was zurückkommt. Speichert nichts.
    proben: dict, in das Probe-Seiten (gekürzt) kommen, damit sich Leser für neue Quellen bauen lassen.
    stand: dict für den Fortschritt (gesamt, fertig, laeuft: Namen der Abfragen, die gerade laufen).
    Verschiedene Server fragt der Test gleichzeitig an, jeden Server für sich nacheinander und mit Pause;
    die Zeilen bleiben in der Reihenfolge der Abfragen."""
    import concurrent.futures as cf
    lines = [f"Pokédex {sources.VERSION}, Test vom {now().strftime('%d.%m.%Y %H:%M')} UTC"]
    proben = {} if proben is None else proben
    stand = {} if stand is None else stand
    stand.update(gesamt=0, fertig=0, laeuft=[])
    html = {"Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}
    lock, pools, futs = threading.Lock(), {}, []

    gate = threading.Semaphore(DIAG_PARALLEL)

    def one(slot, name, url, info, raw, keep, headers, pause, data=None):
        r = None
        gate.acquire()
        with lock:
            stand["laeuft"].append(name)
        try:
            post = {"data": data} if data is not None else {}
            host = urllib.parse.urlsplit(url).hostname or ""
            # 0.58.0: dieselbe Sperre und dieselbe Pause je Server wie der Abgleich: läuft er gerade, fragt der Test
            # denselben Server nie gleichzeitig und nie schneller als erlaubt
            with _host_lock(host):
                wait = _HOST_LAST.get(host, 0) + pause - time.monotonic()
                if wait > 0:
                    sleep(wait)
                try:
                    r = sources.request(url, timeout=DIAG_TIMEOUT, raw=raw, headers=headers, limit=DIAG_LIMIT, **post)
                    if r["error"] and "Errno -3" in r["error"]:      # Namensauflösung kurz überlastet: einmal nachfassen
                        sleep(2)
                        r = sources.request(url, timeout=DIAG_TIMEOUT, raw=raw, headers=headers, limit=DIAG_LIMIT, **post)
                finally:
                    _HOST_LAST[host] = time.monotonic()
            if r["error"]:
                lines[slot] = f"{name}: keine Verbindung ({r['error']})"
                return None
            size = len(r.get("body", b"")) if raw else len(r["text"])
            head = (f"{name}: HTTP {r['status']}, Server {r['server'] or '?'}, {size} {'Bytes' if raw else 'Zeichen'}"
                    + (f" (nach {DIAG_LIMIT} s abgebrochen, nur der Anfang)" if r.get("teil") else ""))
            if r["status"] >= 400 or (not raw and sources.challenge(r["text"])):
                lines[slot] = (head + (", gesperrt" if r["status"] in sources.BLOCKED else "") +
                               (", Prüfseite (Cloudflare)" if not raw and sources.challenge(r["text"]) else "") +
                               ("" if raw else f". Anfang: {' '.join(r['text'][:160].split())}"))
                return None
            try:
                lines[slot] = f"{head}, {info(r.get('body') if raw else r['text'])}"
            except Exception as e:
                lines[slot] = f"{head}, nicht auswertbar ({type(e).__name__}: {e})"
            if keep and not raw:
                proben[name] = r["text"][:keep if keep is not True else PROBE_MAX]
            elif keep and raw:                 # 0.52: Bilder für die Auswertung als base64 mitnehmen
                proben[name] = "base64:" + base64.b64encode(r.get("body", b"")[:keep if keep is not True else PROBE_MAX]).decode("ascii")
            return r
        except Exception as e:
            lines[slot] = f"{name}: Fehler im Test ({type(e).__name__}: {e})"
            return None
        finally:
            with lock:
                stand["laeuft"].remove(name)
                stand["fertig"] += 1
            gate.release()

    def probe(name, url, info, raw=False, keep=False, headers=None, data=None):
        """Reiht die Abfrage beim Server ein; gibt ein Future zurück (.result(): Antwort oder None)."""
        host = urllib.parse.urlsplit(url).hostname or ""
        until = rest_until(server_rest(url))
        if until:
            # 0.58.0: Ein Server, der den Abgleich gesperrt hat (403, 429, Prüfseite), wird in seiner Ruhezeit auch vom
            # Test nicht gefragt
            lines.append(f"{name}: nicht gefragt, {host} ruht nach einer Sperre bis {until[:16].replace('T', ' ')} UTC")
            f = cf.Future()
            f.set_result(None)
            return f
        if host not in pools:
            pools[host] = cf.ThreadPoolExecutor(1, thread_name_prefix="test-" + host)
        lines.append(f"{name}: keine Antwort")
        with lock:
            stand["gesamt"] += 1
        f = pools[host].submit(one, len(lines) - 1, name, url, info, raw, keep, headers, DIAG_PAUSE.get(host, PAUSE), data)
        futs.append(f)
        return f

    def section(title):
        lines.append("")
        lines.append(f"== {title}")

    section("Heutige Quellen")

    def gh_list(text):
        n = [x for x in json.loads(text) if str(x.get("name", "")).endswith(".csv")]
        return f"{len(n)} CSV-Dateien gelistet"
    probe("GitHub-API, Dateiliste PokéAPI", f"{GH_API}/contents/data/v2/csv?ref=master", gh_list)

    def csv_info(text):
        rows = text.strip().splitlines()
        return f"{len(rows) - 1} Zeilen, Spalten: {rows[0][:80]}"
    probe("PokéAPI, types.csv", CSV_RAW + "types.csv", csv_info)

    def sd_info(text):
        from .. import showdown
        return f"{len(showdown.pokedex(text))} Einträge erkannt"
    probe("Showdown, pokedex.ts", SD_RAW + "pokedex.ts", sd_info)
    probe("Sprites, Bild 25", SPRITE_RAW + "25.png", lambda b: "PNG" if b[:4] == b"\x89PNG" else "kein PNG", raw=True)

    section("Items (Namen, Beschreibungen, je Spiel)")
    probe("PokéAPI, items.csv", CSV_RAW + "items.csv", csv_info)
    probe("PokéAPI, item_flavor_text.csv", CSV_RAW + "item_flavor_text.csv", csv_info)
    probe("Showdown, items.ts", SD_RAW + "items.ts", lambda t: f"{t.count('num:')} Items mit Nummer")
    probe("PKHeX, Itemnamen deutsch", PKHEX_RAW + "text/items/text_Items_de.txt",
          lambda t: f"{sum(1 for x in t.splitlines() if x.strip())} Namen (alle Spiele bis Legenden: Z-A)")
    probe("PKHeX, Itemliste Legenden: Arceus", PKHEX_ITEMS + "ItemStorage8LA.cs",
          lambda t: ", ".join(f"{k} {len(v)}" for k, v in importer.pkhex_spans(t).items()) or "keine Listen erkannt")
    probe("Altissimo, Rezepte Legenden: Arceus", altissimo.RECIPES_URL,
          lambda t: "{} Rezepte, {} Zutaten mit Fundorten".format(*map(len, altissimo.recipes(t))))

    section("Kartensymbole und Sammelobjekte (Altissimo, GPL-3.0)")
    probe("Altissimo, Symbole Obsidian-Grasland", altissimo.landmarks_url("fieldlands"),
          lambda t: f"{len(altissimo.landmarks(t, altissimo.FIT['obsidianfieldlands']))} Bäume, Erzbrocken und Haufen")
    probe("Altissimo, Sammelobjekte Jubeldorf", altissimo.collectibles_url("jubilife"),
          lambda t: f"{len(altissimo.collectibles(t, altissimo.VILLAGE_FIT))} Geisterlichter und Icognito")
    probe("Altissimo, Karte Jubeldorf", altissimo.VILLAGE_IMAGE, lambda b: "PNG" if b[:4] == b"\x89PNG" else "kein PNG", raw=True)

    section("Fundorte aus den Spieldaten (PKHeX, GPL-3.0)")

    def la_info(b):
        areas = pkhex_areas(b)
        slots = sum(len(x[2]) for x in areas)
        alpha = sum(1 for x in areas for s in x[2] if s[4])
        return f"{len(areas)} Gebiete, {slots} Begegnungen, davon {alpha} Alpha (mit Level von–bis)"
    probe("PKHeX, Begegnungen Legenden: Arceus", PKHEX_RAW + "legality/wild/Gen8/encounter_la.pkl", la_info, raw=True)
    names = lambda t: f"{sum(1 for x in t.splitlines() if x.strip() and not x.startswith('－'))} Ortsnamen"
    probe("PKHeX, Orte Legenden: Arceus deutsch", PKHEX_RAW + "text/locations/gen8a/text_la_00000_de.txt", names)
    pkl = lambda b: (f"Datei {b[:2].decode('ascii')!r}, {int.from_bytes(b[2:4], 'little')} Einträge"
                     if b[:2].isalpha() else f"Binärdaten, {len(b)} Bytes (Format noch zu lesen)")
    probe("PKHeX, Begegnungen Karmesin/Purpur", PKHEX_RAW + "legality/wild/Gen9/encounter_wild_paldea.pkl", la_info, raw=True)
    probe("PKHeX, Orte Karmesin/Purpur deutsch", PKHEX_RAW + "text/locations/gen9/text_sv_00000_de.txt", names)
    probe("PKHeX, Begegnungen Legenden: Z-A", PKHEX_RAW + "legality/wild/Gen9/encounter_za.pkl", la_info, raw=True)
    probe("PKHeX, Lernlisten Legenden: Z-A", PKHEX_RAW + "byte/levelup/lvlmove_za.pkl", lambda b: f"{len(b)} Bytes, {int.from_bytes(b[2:4], 'little') if b[:2] == b'za' else 0} Lernlisten" if b else "leer", raw=True)
    probe("PKHeX, Begegnungen Mega-Dimension", PKHEX_RAW + "legality/wild/Gen9/encounter_hyperspace_za.pkl", la_info, raw=True)
    probe("PKHeX, Orte Legenden: Z-A deutsch", PKHEX_RAW + "text/locations/gen9a/text_za_00000_de.txt", names)
    probe("PKHeX, Beherrschung Legenden: Arceus", PKHEX_RAW + "legality/misc/mastery_la.pkl", pkl, raw=True)
    probe("PKHeX, Level-Attacken Legenden: Arceus", PKHEX_RAW + "byte/levelup/lvlmove_la.pkl", pkl, raw=True)

    section("Weitere Spieldaten (PKHeX): feste Begegnungen, Raids, Werte")

    def static_info(t):
        st = importer.pkhex_static(t)
        return f"{len(st)} feste Begegnungen (Geschenke, Legendäre, feste Pokémon) mit Art, Level und Ort"
    probe("PKHeX, feste Begegnungen Legenden: Arceus", PKHEX_SRC + "Gen8/Encounters8a.cs", static_info)
    probe("PKHeX, feste Begegnungen Karmesin/Purpur", PKHEX_SRC + "Gen9/Encounters9.cs", static_info)
    probe("PKHeX, feste Begegnungen Legenden: Z-A", PKHEX_SRC + "Gen9/Encounters9a.cs", static_info)
    probe("PKHeX, Tera-Raids Karmesin/Purpur", PKHEX_RAW + "legality/wild/Gen9/encounter_gem_paldea.pkl", pkl, raw=True)
    probe("PKHeX, Event-Raids Karmesin/Purpur", PKHEX_RAW + "legality/wild/Gen9/encounter_dist_paldea.pkl", pkl, raw=True)
    probe("PKHeX, 7-Sterne-Raids Karmesin/Purpur", PKHEX_RAW + "legality/wild/Gen9/encounter_might_paldea.pkl", pkl, raw=True)
    probe("PKHeX, feste Symbole Karmesin/Purpur", PKHEX_RAW + "legality/wild/Gen9/encounter_fixed_paldea.pkl", pkl, raw=True)
    probe("PKHeX, Werte je Form Legenden: Arceus", PKHEX_RAW + "byte/personal/personal_la",
          lambda b: f"{len(b)} Bytes (Basiswerte, Fangrate, Formen wie im Spiel)", raw=True)

    section("Karte (Legenden: Arceus)")
    probe("JS-Finder, Spawnpunkte Obsidian-Grasland", SPAWN_POINTS + "obsidianfieldlands.json",
          lambda t: f"{len(json.loads(t))} Spawnpunkte mit Koordinaten")
    probe("PLA-Live-Map, Tabellen Obsidian-Grasland", SPAWN_SLOTS + "obsidianfieldlands.json",
          lambda t: f"{len(json.loads(t))} Tabellen nach Tageszeit und Wetter")
    probe("Serebii, Kartenkachel", MAP_TILES + "obsidianfieldlands/tile_0-0-0.png",
          lambda b: "PNG" if b[:4] == b"\x89PNG" else "kein PNG", raw=True, headers={"Accept": "image/png,image/*;q=0.8"})

    section("Mögliche Quellen zum Testen: Item-Bilder, Lager und Schnellreise")

    def png(b):
        if b[:8] != b"\x89PNG\r\n\x1a\n":
            return "kein PNG"
        return f"PNG {int.from_bytes(b[16:20], 'big')} × {int.from_bytes(b[20:24], 'big')} px"
    img = {"Accept": "image/png,image/*;q=0.8"}
    for path in ("itemdex/sprites/apricorn.png", "itemdex/sprites/legends/apricorn.png", "itemdex/sprites/potion.png",
                 "itemdex/sprites/sv/potion.png"):
        probe(f"Serebii, Item-Bild {path.split('sprites/')[1]}", SEREBII + path, png, raw=True, headers=img)

    def markers(t):
        low = t.lower()
        keys = ("camp", "fast travel", "distortion", "outbreak", "marker", ".json", "oldverse", "crystal")
        return ", ".join(f"{k} {low.count(k)}×" for k in keys)
    probe("Serebii, Karte Obsidian-Grasland (Seite)", SEREBII + "pokearth/hisui/obsidianfieldlands.shtml", markers, keep=400_000, headers=html)

    # Weitere Karten zum Vergleich: GamerGuides (Lager, Schnellreise, Sammelobjekte) und Pokébip (französisch)
    def scan(t):
        low = t.lower()
        keys = ("camp", "fast travel", "marker", "markers", "lat", "leaflet", "mapbox", "__next_data__", "api/", ".json",
                "wisp", "unown", "distortion", "outbreak", "marqueur", "campement", "voyage rapide")
        hits = ", ".join(f"{k} {low.count(k)}×" for k in keys if low.count(k))
        js = sorted(set(re.findall(r'src="([^"]+\.js[^"]*)"', t)))[:6]
        return (hits or "keine Stichwörter") + (f"; Skripte: {', '.join(js)}" if js else "")
    probe("GamerGuides, Karte Obsidian-Grasland", GAMERGUIDES + "pokemon-legends-arceus/maps/obsidian-fieldlands", scan,
          keep=400_000, headers=html)
    probe("GamerGuides, Karte Jubeldorf", GAMERGUIDES + "pokemon-legends-arceus/maps/jubilife-village", scan, keep=400_000, headers=html)
    probe("Pokébip, Karte Obsidian-Grasland", POKEBIP + "page/jeuxvideo/legendes-pokemon-arceus/cartes-interactives/plaines-obsidiennes",
          scan, keep=400_000, headers=html)
    probe("Pokébip, Massenauftreten", POKEBIP + "page/jeuxvideo/legendes-pokemon-arceus/megapparitions", scan, keep=200_000, headers=html)

    def wiki_list(t):
        q = json.loads(t).get("query") or {}
        xs = q.get("allimages") or q.get("search") or []
        return "; ".join(f"{x.get('name') or x.get('title')}" + (f" ({x['width']}×{x['height']})" if x.get("width") else "") for x in xs[:12]) or "nichts"
    probe("PokéWiki, Bilder „Aprikoko…“", POKEWIKI_API + "?" + urllib.parse.urlencode(
        {"action": "query", "list": "allimages", "aiprefix": "Aprikoko", "aiprop": "url|size", "ailimit": "20", "format": "json"}),
        wiki_list, keep=True)
    probe("PokéWiki, Suche Schnellreise", POKEWIKI_API + "?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Schnellreise Basislager Hisui", "srlimit": "15", "format": "json"}),
        wiki_list, keep=True)
    probe("PokéWiki, Seite Basislager", POKEWIKI_API + "?" + urllib.parse.urlencode(
        {"action": "parse", "page": "Basislager", "prop": "wikitext", "format": "json"}),
        lambda t: f"{len(t)} Zeichen Wikitext", keep=True)

    section("Bilder und Rufe (PokéAPI-Repos)")
    img = lambda kind: (lambda b: kind if b[:4] in (b"\x89PNG", b"GIF8") else "unbekanntes Format")
    probe("Sprites, schillernd 25", POKEAPI_RAW + "sprites/master/sprites/pokemon/shiny/25.png", img("PNG"), raw=True)
    probe("Sprites, animiert 25", POKEAPI_RAW + "sprites/master/sprites/pokemon/other/showdown/25.gif", img("GIF"), raw=True)
    probe("Rufe, Pokémon 25", POKEAPI_RAW + "cries/main/cries/pokemon/latest/25.ogg",
          lambda b: "Ogg-Audio" if b[:4] == b"OggS" else "MP3-Audio" if b[:3] == b"ID3" or b[:2] == b"\xff\xfb"
          else "unbekanntes Format", raw=True)

    section("Schon geladen, noch ungenutzt (PokéAPI in pokeapi.db)")
    if db.has_data():
        con = db.game()
        try:
            for label, sql in (("TM und VM je Spiel", "SELECT COUNT(*) FROM machines"),
                               ("Wesen", "SELECT COUNT(*) FROM natures"),
                               ("Ei-Gruppen je Pokémon", "SELECT COUNT(*) FROM pokemon_egg_groups"),
                               ("Fangraten", "SELECT COUNT(capture_rate) FROM pokemon_species"),
                               ("Beeren", "SELECT COUNT(*) FROM berries"),
                               ("EV-Ausbeute", "SELECT COUNT(*) FROM pokemon_stats WHERE effort > 0")):
                try:
                    lines.append(f"{label}: {con.execute(sql).fetchone()[0]} Einträge")
                except Exception as e:
                    lines.append(f"{label}: nicht in der Datenbank ({e})")
        finally:
            con.close()
    else:
        lines.append("Noch keine Datenbank: erst einen Abgleich starten.")

    section("Wikis und Datenbanken (Fundorte mit Tageszeit, Attackenwerte, Karten)")

    def wiki_info(text):
        g = json.loads(text)["query"]["general"]
        return f"{g.get('sitename')} auf MediaWiki {g.get('generator', '?').split()[-1]}"

    def wiki_page(text):
        j = json.loads(text)
        if "parse" not in j:
            return f"Seite gibt es nicht ({(j.get('error') or {}).get('code', '?')})"
        p = j["parse"]
        wt = p["wikitext"]["*"] if isinstance(p["wikitext"], dict) else p["wikitext"]
        return f"Seite „{p['title']}“, {len(wt)} Zeichen Wikitext, {wt.count('{{')} Vorlagen"
    probe("PokéWiki, API", POKEWIKI_API + "?action=query&meta=siteinfo&format=json", wiki_info)
    for page in ("Pokémon-Legenden: Arceus", "Bidiza", "Obsidian-Grasland", "Tackle", "Kraftstil", "Alpha-Pokémon",
                 "Forschungsaufgabe", "Edelhorde", "Raum-Zeit-Verzerrung"):
        probe(f"PokéWiki, Seite {page}", POKEWIKI_API + "?action=parse&page=" + urllib.parse.quote(page)
              + "&prop=wikitext&format=json&redirects=1", wiki_page, keep=True)
    # 0.42: Trainerteams und Blaubeer-Missionen (der Leser zählt, was er findet)
    def wiki_trainer(text):
        got = pokewiki.pages(text)
        ts = [t for k, v in got.items() for t in pokewiki.trainer_teams(v, k, "")]
        bbq = pokewiki.bbq_missions(got.get(pokewiki.BBQ_PAGE, ""))
        return (f"{len(ts)} Teams ({', '.join(sorted({g for t in ts for g in t['spiele']}))}); "
                f"{len(bbq)} Blaubeer-Missionen ({', '.join(sorted({x['bereich'] for x in bbq}))})")
    probe("PokéWiki, Trainerteams und Blaubeer-Missionen", pokewiki.batch_url(["Rocko", "Nemila", pokewiki.BBQ_PAGE]), wiki_trainer)
    probe("PokéWiki, Kategorie Arenaleiter", pokewiki.category_url("Arenaleiter"),
          lambda t: f"{len(pokewiki.category_members(t)[0])} Seiten")
    # 0.48.6: Trainer in Legenden: Arceus (Charaktere aus Hisui; Kamado und Wächterin Irida als Stichprobe)
    probe("PokéWiki, Kategorie Charakter aus Hisui", pokewiki.category_url("Charakter aus Hisui"),
          lambda t: (lambda n: f"{len(n)} Seiten: " + ", ".join(n[:15]))(pokewiki.category_members(t)[0]), keep=True)
    probe("PokéWiki, Trainerteams Hisui (Kamado, Irida, Adamas)", pokewiki.batch_url(["Kamado", "Irida", "Adamas"]), wiki_trainer)
    def wiki_batch(text):
        got = pokewiki.pages(text)
        vals = {k: pokewiki.la_move(v) for k, v in got.items()}
        return f"{len(got)} Seiten gebündelt; " + "; ".join(f"{k}: {v}" for k, v in vals.items())
    probe("PokéWiki, Bündel Attacken (Legenden: Arceus)", pokewiki.batch_url(["Tackle", "Donnerblitz", "Kraftschub"], True), wiki_batch)

    # 0.36.0: deutsche Texte je Spiel; meldet, welche Spiele die Kürzel abdecken und welche Kürzel unbekannt sind
    def wiki_texts(text):
        got = pokewiki.pages(text)
        out = []
        for name, kind in (("Pikachu", "pokemon"), ("Donnerblitz", "attacken"), ("Statik", "faehigkeiten")):
            v = _wiki_page(kind, got.get(name, "")) if name in got else None
            if not v:
                out.append(f"{name}: keine Texte")
                continue
            tx = v["texte"]
            unk = pokewiki.unknown_keys(kind, tx)
            out.append(f"{name}: {len(pokewiki.per_game(kind, tx))} Spiele" + (f", unbekannt: {', '.join(unk)}" if unk else "")
                       + (f", {len(v.get('aufgaben') or [])} Forschungsaufgaben" if kind == "pokemon" else ""))
        return "; ".join(out)
    probe("BisaFans, Aufträge in Legenden: Arceus", bisafans.LA_REQUESTS,
          lambda t: (lambda r: f"{len(r)} Aufträge" + (f", zuletzt Nr. {r[-1]['nr']} „{r[-1]['name']}“, Belohnung {r[-1]['belohnung'] or '?'}"
                                                        if r else ""))(bisafans.la_requests(t)), keep=True)
    probe("PokéWiki, Texte je Spiel (Pikachu, Donnerblitz, Statik)", pokewiki.batch_url(["Pikachu", "Donnerblitz", "Statik"]),
          wiki_texts, keep=True)
    probe("Bulbapedia, API", "https://bulbapedia.bulbagarden.net/w/api.php?action=query&meta=siteinfo&format=json", wiki_info)
    probe("Bulbapedia, Seite Bidoof", "https://bulbapedia.bulbagarden.net/w/api.php?action=parse&page=Bidoof_(Pok%C3%A9mon)"
          "&prop=wikitext&format=json&redirects=1", wiki_page, keep=True)
    # 0.13.0: Fangfaktoren der Hisui-Bälle zum Gegenprüfen (Bulbapedia und PokéWiki), Kartendaten des PLA Companion
    # 0.48.8: die echte Fangformel in Legenden: Arceus (Seite „Catch rate“ und alle Hisui-Bälle, PokéWiki „Fangchance“)
    for page in ("Heavy_Ball_(Hisui)", "Feather_Ball", "Ultra_Ball_(Hisui)", "Catch_rate", "Poké_Ball_(Hisui)",
                 "Great_Ball_(Hisui)", "Wing_Ball", "Jet_Ball", "Leaden_Ball", "Gigaton_Ball", "Origin_Ball", "Strange_Ball"):
        probe(f"Bulbapedia, Seite {page}", "https://bulbapedia.bulbagarden.net/w/api.php?action=parse&page=" + urllib.parse.quote(page)
              + "&prop=wikitext&format=json&redirects=1", wiki_page, keep=400_000)
    for page in ("Schwerball", "Federball", "Hyperball", "Fangchance", "Fangrate"):
        probe(f"PokéWiki, Seite {page}", POKEWIKI_API + "?" + urllib.parse.urlencode(
            {"action": "parse", "page": page, "prop": "wikitext", "format": "json", "redirects": 1}), wiki_page, keep=400_000)
    def kinds(t):
        n = {}
        for e in companion.entries(t):
            n[e["t"]] = n.get(e["t"], 0) + 1
        return "Einträge mit Lage: " + ", ".join(f"{k} {v}" for k, v in sorted(n.items()))
    probe("PLA Companion, Karte Obsidian-Grasland", companion.url("obsidianfieldlands"), kinds, keep=True)
    # Karten weiterer Spiele: welche Dateien die offenen Projekte haben (Kartenbilder, Koordinaten), als Probe zum Herunterladen
    def tree(t):
        ps = [x.get("path", "") for x in json.loads(t).get("tree", [])]
        hits = [x for x in ps if re.search(r"(?i)(paldea|kitakami|terarium|lumiose|z-?a|scarlet|violet|sv)[^/]*$|map", x)
                and re.search(r"(?i)\.(json|png|jpe?g|webp|js|html)$", x)]
        return f"{len(ps)} Dateien, davon {len(hits)} zu Karten und neueren Spielen: " + ", ".join(hits[:12])
    probe("GitHub: Dateien von sv-live-map (Karmesin/Purpur)", "https://api.github.com/repos/Lincoln-LM/sv-live-map/git/trees/master?recursive=1",
          tree, keep=True)
    probe("GitHub: Dateien von Altissimo", "https://api.github.com/repos/Altissimo1/altissimo1.github.io/git/trees/main?recursive=1",
          tree, keep=True)
    probe("sv-live-map: Tera-Raid-Höhlen (Spielkoordinaten)",
          "https://raw.githubusercontent.com/Lincoln-LM/sv-live-map/master/resources/den_locations.json",
          lambda t: f"{len(json.loads(t))} Höhlen")
    page_info = lambda t: f"Titel „{(t.split('<title>')[1].split('</title>')[0].strip() if '<title>' in t else '?')[:80]}“"
    probe("Serebii, Legenden: Arceus Bidiza", "https://www.serebii.net/pokedex-swsh/bidoof/", page_info, keep=True, headers=html)
    probe("Serebii, Legenden: Arceus Übersicht", "https://www.serebii.net/legendsarceus/", page_info, keep=True, headers=html)
    probe("Pokémon Database, Legenden: Arceus", "https://pokemondb.net/pokedex/game/legends-arceus", page_info, keep=True, headers=html)
    for spiel in mapgenie.GAMES:
        for slug in mapgenie.slugs(spiel):
            probe(f"Map Genie, {slug}", mapgenie.game_url(slug),
                  lambda t, s=slug: page_info(t) + ", Karten: " + (", ".join(mapgenie.map_slugs(t, s)) or "keine"), headers=html)
    # eine Kachel innerhalb der Karte (zeigt, ob der Kachelspeicher antwortet; außerhalb meldet er 403)
    probe("Map Genie, Kachel Hisui 9/254/254", mapgenie.TILES + "pokemon-legends-arceus/hisui-region/default-v3/9/254/254.png",
          lambda b: f"{len(b)} Bytes, " + ("PNG" if b[:4] == b"\x89PNG" else "kein Bild"), raw=True)
    # je gespeicherter Karte: Kachelmuster, Zoom und Grenzen (zeigt, warum eine Karte keine Kacheln bekommt)
    for spiel in MAP_GAMES:
        for m in (mg_maps(spiel) or {}).get("karten", []):
            rel = (_tile_of(m, m["min_zoom"], 0, 0)[0] if m.get("quelle")
                   else mapgenie.tile_ok(m["kacheln"], m["min_zoom"], 0, 0, m.get("endung", "png")))
            v = mg_status()["vorrat"].get(f"{spiel}/{m['slug']}") or {}
            lines.append(f"{m.get('quelle') or 'Map Genie'}, Karte {spiel}/{m['slug']}: Muster {m['kacheln'] or '–'} ({m.get('endung', '?')}), "
                         f"Zoom {m['min_zoom']}–{m['max_zoom']}, Grenzen {'ja' if m.get('bounds') else 'aus den Orten' if mapgenie.bounds_of(m) else 'keine'}, "
                         f"Kachelpfad {'ok' if rel else 'unbrauchbar'}" + (f", Vorrat {v.get('da', 0)}/{v.get('alle', 0)}" if v else ""))
    st = mg_status()
    lines.append(f"Map Genie, Kacheln im Dienst: {'ruht bis ' + st['ruht'] if st['ruht'] else 'bereit'}"
                 + (f", zuletzt {st['fehler']}" if st["fehler"] else ""))
    # ältere Spiele: interaktive Karten mit Symbolen (Items, Trainer, Pokémon) zum Abhaken
    for g in ("Yellow", "Crystal", "Emerald", "Platinum", "Red", "Gold", "FireRed", "HeartGold", "Black", "X", "Sun"):
        probe(f"pokemoncompletion, {g}", f"https://pokemoncompletion.com/completion/{g}", page_info, keep=200_000, headers=html)

    section("Gesuchte Quellen (Spezial in Gen. 1, Abklingzeiten in Z-A, Karten älterer Spiele)")
    # Spezial-Wert und frühere Basiswerte: die Generations-Mods von Showdown (seit 0.23.0 im Abgleich)
    from .. import showdown as _sd
    for n in (1, 2, 5, 6):
        probe(f"Showdown, Basiswerte Generation {n}", f"{SD_RAW}mods/gen{n}/pokedex.ts",
              lambda t: f"{len(_sd.mod_stats(t))} Pokémon mit eigenen Basiswerten")
    img_info = lambda t: page_info(t) + f", {t.count('<img')} Bilder, {t.count('.png')} PNG-Verweise"

    def wiki_hits(text):
        hits = (json.loads(text).get("query") or {}).get("search") or []
        return f"{len(hits)} Treffer: " + ", ".join(h.get("title", "") for h in hits[:10])
    # Abklingzeiten der Attacken in Legenden: Z-A (Echtzeitkampf)
    probe("PokéWiki, Suche Abklingzeit Z-A", POKEWIKI_API + "?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Abklingzeit Legenden Z-A", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)
    probe("Bulbapedia, Suche cooldown Z-A", "https://bulbapedia.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "cooldown Legends Z-A move", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)
    probe("Serebii, Legenden: Z-A Übersicht", "https://www.serebii.net/legendsz-a/", img_info, keep=True, headers=html)
    probe("Serebii, Attackdex Z-A", "https://www.serebii.net/attackdex-za/", img_info, keep=True, headers=html)
    # Leser seit 0.30.0: die ganzen Seiten, damit sich der Leser an der echten Seite prüfen lässt
    probe("Serebii, Z-A Attacken (Leser)", serebii.ZA_ATTACKS,
          lambda t: f"{len(serebii.za_cooldowns(t))} Abklingzeiten gelesen, z. B. " + ", ".join(
              f"{v['name']} {v['abkling']} s" for v in list(serebii.za_cooldowns(t).values())[:5]), keep=600_000, headers=html)
    for dex, url in serebii.POKOPIA.items():
        probe(f"Serebii, Pokopia {serebii.POKOPIA_DEX[dex]} (Leser)", url,
              lambda t: f"{len(serebii.pokopia_dex(t))} Pokémon gelesen, z. B. " + ", ".join(
                  f"#{r['nr']} {r['name']} ({', '.join(r['spezial'])})" for r in serebii.pokopia_dex(t)[:5]), keep=600_000, headers=html)
    probe("GitHub, Projekte zu Legenden: Z-A", "https://api.github.com/search/repositories?" + urllib.parse.urlencode(
        {"q": "legends z-a pokemon data", "sort": "updated", "per_page": "15"}),
        lambda t: f"{json.loads(t).get('total_count', 0)} Projekte: " + ", ".join(r.get("full_name", "") for r in json.loads(t).get("items", [])[:15]), keep=True)
    # Karten älterer Spiele: Ortsbilder bei Serebii (PokéEarth), Disassemblies (pret) und das Bildarchiv von Bulbapedia
    for reg in ("kanto", "johto", "hoenn", "sinnoh"):
        probe(f"Serebii, PokéEarth {reg.title()}", f"https://www.serebii.net/pokearth/{reg}/", img_info, keep=True, headers=html)
    def earth_info(t):
        d = pokearth.extract(t)
        return f"Bildkarte {d['bild'].rsplit('/', 1)[-1]} ({d['w']}×{d['h']}) mit {len(d['orte'])} Orten" if d else "keine Bildkarte"
    for reg in ("unova", "kalos", "alola", "orre"):          # 0.41: Regionskarten der übrigen Spiele
        probe(f"Serebii, PokéEarth {reg.title()} (Bildkarte)", pokearth.page_url(reg), earth_info, keep=True, headers=html)
    probe("Serebii, PokéEarth Route 1 (Kanto)", "https://www.serebii.net/pokearth/kanto/route1.shtml", img_info, keep=True, headers=html)
    probe("Bulbapedia-Archiv, Kartenbilder Kanto", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Kanto Route 1 RBY", "srnamespace": "6", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)

    def blk(text):
        ps = [x.get("path", "") for x in json.loads(text).get("tree", [])]
        return f"{len(ps)} Dateien, {sum(p.endswith('.blk') for p in ps)} Kartenblöcke (.blk), {sum(p.endswith('.png') for p in ps)} Bilder"
    probe("GitHub: pret/pokered (Rot/Blau, Karten als Blöcke)", "https://api.github.com/repos/pret/pokered/git/trees/master?recursive=1", blk)
    probe("GitHub: pret/pokecrystal (Kristall)", "https://api.github.com/repos/pret/pokecrystal/git/trees/master?recursive=1", blk)
    probe("Altissimo, Orte Gold/Silber/Kristall", "https://altissimo1.github.io/Main-Series/GSC/locations.html", img_info, keep=True, headers=html)
    # nächste Schritte aus dem letzten Test (11.11.): Seite „Cooldown“ bei Bulbapedia, Z-A-Projekte auf GitHub, Kartenbilder älterer Spiele
    probe("Bulbapedia, Seite Cooldown (Z-A)", "https://bulbapedia.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "parse", "page": "Cooldown", "prop": "wikitext", "format": "json"}),
        lambda t: (lambda w: f"{len(w)} Zeichen Wikitext, {w.count('{{')} Vorlagen, {w.lower().count('cooldown')}× cooldown")(
            ((json.loads(t).get("parse") or {}).get("wikitext") or {}).get("*", "")), keep=True)

    # 0.48.4: Shiny-Sperren je Spiel (Bulbapedia-Liste mit Zeichen je Spiel: fangbar, nur Übertragung, gar nicht; PokéWiki zum Gegenprüfen)
    def shiny_info(t):
        w = ((json.loads(t).get("parse") or {}).get("wikitext") or {}).get("*", "")
        return (f"{len(w)} Zeichen Wikitext, {w.count('{{')} Vorlagen, {w.count('|-')} Tabellenzeilen, "
                f"{w.lower().count('shiny lock') + w.lower().count('shiny-lock')}× shiny lock, {w.lower().count('transfer')}× transfer")
    for page in ("List_of_unobtainable_Shiny_Pok%C3%A9mon", "Shiny-locked", "Shiny_Pok%C3%A9mon"):
        probe(f"Bulbapedia, Seite {urllib.parse.unquote(page)}", "https://bulbapedia.bulbagarden.net/w/api.php?action=parse&page=" + page
              + "&prop=wikitext&format=json&redirects=1", shiny_info, keep=400_000)
    for page in ("Schillernde Pokémon", "Shiny-Lock"):
        probe(f"PokéWiki, Seite {page}", POKEWIKI_API + "?" + urllib.parse.urlencode(
            {"action": "parse", "page": page, "prop": "wikitext", "format": "json", "redirects": 1}), shiny_info, keep=400_000)

    def tree_hits(*words):
        def f(text):
            ps = [x.get("path", "") for x in json.loads(text).get("tree", [])]
            hit = [p for p in ps if any(w in p.lower() for w in words)]
            return f"{len(ps)} Dateien, {len(hit)} passend ({', '.join(words)}): " + ", ".join(hit[:12])
        return f
    for repo in ("Setmaster/ZA-Decoder", "Scotts-Thoughts/pokemon-data", "solomonjasperkim/pokehex", "NyanWinPhyo/dex-atlas"):
        probe(f"GitHub: {repo} (Z-A)", f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1", tree_hits("cool", "move", "waza", "za"), keep=True)
    probe("Bulbapedia-Archiv, Kartenbilder Johto", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Johto Route 29 GSC", "srnamespace": "6", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)
    probe("Bulbapedia-Archiv, Kartenbilder Hoenn", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Hoenn Route 101 RSE", "srnamespace": "6", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)
    probe("Serebii, PokéEarth Route 29 (Johto)", "https://www.serebii.net/pokearth/johto/route29.shtml", img_info, keep=True, headers=html)
    probe("Altissimo, Orte Rot/Blau/Gelb", "https://altissimo1.github.io/Main-Series/RBY/locations.html", img_info, keep=True, headers=html)

    section("Karten für Schwert/Schild, Strahlender Diamant/Leuchtende Perle und Let’s Go")
    # Map Genie hat sie nicht; IGN (Galar, Let’s Go) steht unter „Weitere Kartenquellen“, IGN-Pfade für DLCs und BDSP gibt es
    # nicht (404). Serebii zeigt in 3D-Spielen Bilder je Ort statt einer Karte; Bulbapedia hat Kartenbilder
    for reg in ("galar", "sinnoh"):
        probe(f"Serebii, PokéEarth {reg.title()}", f"https://www.serebii.net/pokearth/{reg}/", img_info, keep=True, headers=html)
    for name, page in (("Naturzone", "galar/wildarea"), ("Insel der Rüstung", "galar/isleofarmor"),
                       ("Kronen-Schneelande", "galar/thecrowntundra"), ("Untergrund (BDSP)", "sinnoh/grandunderground")):
        probe(f"Serebii, {name}", f"https://www.serebii.net/pokearth/{page}.shtml", img_info, keep=True, headers=html)
    probe("Bulbapedia-Archiv, Kategorie Spielkarten", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "categorymembers", "cmtitle": "Category:Game maps", "cmlimit": "100", "format": "json"}),
        lambda t: (lambda ms: f"{len(ms)} Einträge: " + ", ".join(m["title"] for m in ms[:15]))(
            (json.loads(t).get("query") or {}).get("categorymembers") or []), keep=True)
    probe("Bulbapedia-Archiv, Kartenbilder Galar", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Galar map", "srnamespace": "6", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)
    probe("Bulbapedia-Archiv, Kartenbilder Sinnoh BDSP", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": "Sinnoh BDSP map", "srnamespace": "6", "srlimit": "15", "format": "json"}), wiki_hits, keep=True)
    probe("pokemoncompletion, Let’s Go", "https://pokemoncompletion.com/completion/LetsGo", page_info, keep=200_000, headers=html)

    section("Weitere Kartenquellen (Funde vom 11.11.)")
    # interaktive Karten: ob die Punkte als JSON nachgeladen werden (Hinweise in der Seite), sonst Bilder je Gebiet
    looks = lambda t: (page_info(t) + f", {t.count('.json')} × .json, {t.count('marker')} × marker, {t.count('tile')} × tile, "
                       f"{t.count('drive.google')} × Google Drive, {t.count('<img')} Bilder, eingebettete Daten: "
                       + (", ".join(k for k in ("__NEXT_DATA__", "__NUXT__", "window.__", "application/json", "mapData", "markers\"", "\"lat\"")
                                    if k in t) or "keine"))
    for name, url in (("IGN, Let’s Go Kanto", "https://www.ign.com/maps/pokemon-lets-go-pikachu-eevee/kanto"),
                      ("IGN, Schwert/Schild Galar", "https://www.ign.com/maps/pokemon-sword-shield/galar"),
                      ("IGN, Feuerrot/Blattgrün", "https://www.ign.com/maps/pokemon-firered-leafgreen-version"),
                      ("MewMaps, Let’s Go", "https://www.mewmaps.org/lets-go-pikachu-eevee"),
                      ("RankedBoost, Let’s Go", "https://rankedboost.com/pokemon/location/letsgo-pikachu-eevee/"),
                      ("RankedBoost, HG/SS Route 45", "https://rankedboost.com/pokemon/location/heartgold-soulsilver/route-45/"),
                      ("RankedBoost, Rubin/Saphir", "https://rankedboost.com/pokemon/location/ruby-sapphire/"),
                      ("Poké Atlas, Naturzone", "https://pokeatlas.com/maps/wild-area/"),
                      ("FrontierNav, Sonne/Mond", "https://frontiernav.net/wiki/pokemon-sun-moon/visualisations/maps"),
                      ("SimplyBLG, Johto", "https://simplyblgdev.github.io/Pokemon/Johto"),
                      ("HGSS Ironmon Map", "https://kelseyyoung.github.io/HGSSIronmonMap/"),
                      ("PokéMaps, Hoenn RSE", "https://pokemaps.net/maps/rse/hoenn"),
                      ("PokéTools, Smaragd", "https://www.poketools.com/emerald/map"),
                      ("PKMNMap, Smaragd", "https://pkmnmap.com/Maps/Emerald/"),
                      ("DittoBase, Kristall", "https://www.dittobase.com/crystal/map"),
                      ("PokémonRNG, Sinnoh", "https://www.pokemonrng.com/sinnoh-map/")):
        probe(name, url, looks, keep=200_000, headers=html)
    probe("Bulbapedia-Archiv, Kategorie Let’s-Go-Karten", "https://archives.bulbagarden.net/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "categorymembers", "cmtitle": "Category:Let's Go, Pikachu! and Let's Go, Eevee! maps",
         "cmlimit": "50", "format": "json"}),
        lambda t: (lambda ms: f"{len(ms)} Bilder: " + ", ".join(m["title"] for m in ms[:10]))(
            (json.loads(t).get("query") or {}).get("categorymembers") or []), keep=True)
    # GitHub-Projekte mit Kartendaten (Trainer, Items, Begegnungen)
    for repo, words in (("kelseyyoung/HGSSIronmonMap", ("json", "map", "trainer")),
                        ("kelseyyoung/EmeraldIronmonMap", ("json", "map", "trainer")),
                        ("kelseyyoung/FRLGIronmonMap", ("json", "map", "trainer")),
                        ("simplyblgdev/simplyblgdev.github.io", ("johto", "json", "map")),
                        ("tristan-paul/Emerald_Encounters", ("db", "sql", "csv", "json"))):
        probe(f"GitHub: {repo}", f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1", tree_hits(*words), keep=True)
    # pokemoncompletion (GPL-3.0): Spieldaten mit Kartenpunkten liegen als JSON im Repository, die Karten als ganzes Bild
    # und als Kacheln ({z}_{x}_{y}.png) auf einem CDN; Gelb, Kristall, Smaragd und Platin haben eine Karte
    def pc_info(text):
        d = json.loads(text)
        im = d.get("interactiveMap") or {}
        n = sum(1 for c in d.get("categories") or [] for x in c.get("list") or [] if x.get("pos"))
        return (f"Karte {im.get('dim')}, Bild {im.get('fullImgUrl', '–')} ({im.get('fullImgSize', '?')}), "
                f"{len(d.get('locations') or [])} Orte, {n} Punkte in {len(d.get('categories') or [])} Kategorien")
    for g in ("Yellow", "Crystal", "Emerald", "Platinum"):
        probe(f"GitHub: pokemoncompletion, Daten {g}", f"https://raw.githubusercontent.com/RainingChain/pokemoncompletion/main/src/pokemonCompletion/data/{g}.json",
              pc_info)
        probe(f"pokemoncompletion, Kachel {g}", f"https://pokemonmap.b-cdn.net/{g.lower()}/1_0_0.png?v=1",
              lambda b: f"{len(b)} Bytes, " + ("PNG" if b[:4] == b"\x89PNG" else "kein Bild"), raw=True)
    probe("GitHub: Insektaure/pkTeraRaid (Raid-Nester SwSh mit Lage)", "https://api.github.com/repos/Insektaure/pkTeraRaid/git/trees/HEAD?recursive=1",
          tree_hits("den", "map", "swsh", "location"), keep=True)

    section("Kartenquellen im Detail: IGN, RankedBoost, DittoBase, PokéTools")
    # IGN (Next.js): Karte, Kacheln und ein Teil der Punkte stehen in __NEXT_DATA__, der Rest kommt per GraphQL
    # (mollusk.apis.ign.com). Die Abfrage steht im Code der Seite; deshalb die Skripte nach Abfragen mit „marker“ durchsuchen
    def ign_info(t):
        mk = re.findall(r'"__typename":"MapMarker"', t)
        ty = sorted(set(re.findall(r'"typeSlug":"([^"]+)","typeName"', t)))
        ts = re.findall(r'wikimaps/[^"]+\{z\}[^"]*', t)
        zz = re.findall(r'"(minZoom|maxZoom|width|height)":([\d.]+),', t)[:4]
        return f"{len(mk)} Punkte in der Seite, Arten: {', '.join(ty)}; Kacheln {ts[:1]}, {zz}"
    ign_js = set()
    for name, url in (("IGN, Galar (ganz)", "https://www.ign.com/maps/pokemon-sword-shield/galar"),
                      ("IGN, Let’s Go Kanto (ganz)", "https://www.ign.com/maps/pokemon-lets-go-pikachu-eevee/kanto")):
        try:
            r = probe(name, url, ign_info, keep=600_000, headers=html).result(timeout=DIAG_HANG)
        except cf.TimeoutError:
            r = None
        if r:
            ign_js.update(u for u in re.findall(r'<script src="(https://kraken\.ignimgs\.com/_next/static/chunks/[^"]+\.js)"', r["text"])
                          if "polyfills" not in u and "framework" not in u)

    def gql_info(t):
        ops = sorted(set(re.findall(r"(?:query|fragment)\s+(\w+)", t)))
        hits = [t[max(0, m.start() - 80):m.start() + 700] for m in re.finditer(r"(?:query|fragment)\s+\w*[Mm]arker\w*", t)][:4]
        return f"{len(ops)} Abfragen: {', '.join(ops[:30])}" + (" | " + " || ".join(" ".join(h.split()) for h in hits) if hits else "")
    for u in sorted(ign_js)[:25]:
        probe(f"IGN, Skript {u.rsplit('/', 1)[-1]}", u, gql_info)
    for slug in ("pokemon-lets-go-pikachu-eevee/kanto-hi-res", "pokemon-sword-shield/locations"):
        probe(f"IGN, Kachel {slug} 2/0-0", f"https://oyster.ignimgs.com/ignmedia/wikimaps/{slug}/2/0-0.jpg",
              lambda b: f"{len(b)} Bytes, " + ("JPEG" if b[:3] == b"\xff\xd8\xff" else "kein Bild"), raw=True)
    # die übrigen Kartenseiten ganz (die erste Probe war bei 200 000 Zeichen abgeschnitten)
    for name, url in (("RankedBoost, Let’s Go (ganz)", "https://rankedboost.com/pokemon/location/letsgo-pikachu-eevee/"),
                      ("RankedBoost, HG/SS (ganz)", "https://rankedboost.com/pokemon/location/heartgold-soulsilver/"),
                      ("DittoBase, Kristall (ganz)", "https://www.dittobase.com/crystal/map"),
                      ("PokéTools, Smaragd (ganz)", "https://www.poketools.com/emerald/map")):
        probe(name, url, lambda t: looks(t) + "; Muster: " + ", ".join(tile_patterns(t)[:5])
              + "; JSON-Adressen: " + ", ".join(sorted(set(re.findall(r'https?://[^"\' ]+\.json', t)))[:8]),
              keep=1_600_000, headers=html)

    section("Kartendaten im Detail (0.38): IGN-Abfrage, DittoBase, RankedBoost, PokéTools")
    # IGN: dieselbe GraphQL-Abfrage wie der Abgleich (alle Punkte einer Karte)
    for spiel, (slug, karten) in ign.GAMES.items():
        q = {"operationName": "MapMarkersMultiple", "query": ign.QUERY, "variables": {"objectSlug": slug, "mapSlug": karten[0],
             "typeSlugs": ["location", "pokemon", "item", "technical-machine", "trainer", "master-trainer", "gym", "pikachu",
                           "legendary-pokemon", "mega-stone", "den", "max-raid-den", "berry-tree", "fossil"]}}

        def gq(t):
            xs = ign.markers(t)
            from collections import Counter
            c = Counter(x.get("typeSlug") for x in xs)
            err = (json.loads(t).get("errors") or [{}])[0].get("message", "") if not xs else ""
            return f"{len(xs)} Punkte: " + ", ".join(f"{k} {n}" for k, n in c.most_common()) + (f"; Fehler: {err[:200]}" if err else "")
        probe(f"IGN, Abfrage aller Punkte {slug}/{karten[0]}", ign.GRAPH, gq, data=q)

    # DittoBase: welche Spiele haben eine Karte mit Spieldaten (wie Kristall), und wie sehen die Kachelsätze aus
    def db_info(t):
        d = dittobase.extract(t)
        if not d:
            return looks(t) + "; keine Kartendaten"
        m, draw = dittobase.parse(d, "x")
        ks = sorted({x.get("kind") for v in (d.get("data") or {}).get("markers", {}).values() for x in v})
        return (f"Oberwelt {d['data'].get('overworld')}, {len(d['data'].get('maps') or {})} Karten, {len((m or {}).get('orte') or [])} Punkte, "
                f"Arten {', '.join(map(str, ks))}, {len((draw or {}).get('saetze') or {})} Kachelsätze, Schlüssel {sorted(d)}")
    for g in ("red-blue", "yellow", "gold-silver", "ruby-sapphire", "emerald", "firered-and-leafgreen", "diamond-pearl",
              "platinum", "heartgold-soulsilver"):
        probe(f"DittoBase, Karte {g}", dittobase.page_url(g), db_info, headers=html)

    def png_info(b):
        import struct
        w, h, depth, ct, _, _, il = struct.unpack(">IIBBBBB", b[16:29])
        return f"PNG {w}×{h}, Farbtyp {ct}, {depth} Bit, Zeilensprung {il}"
    probe("DittoBase, Kachelsatz Johto (New Bark)", "https://assets.dittobase.com/game-maps/crystal-maps/pixi/tilesets/johto_89abcdef_g8_new_bark.png",
          png_info, raw=True)
    probe("DittoBase, Kachelsatz Höhle", "https://assets.dittobase.com/game-maps/crystal-maps/pixi/tilesets/cave_89abcdef.png", png_info, raw=True)

    # RankedBoost: die Daten der großen Karte (data-mega-src) und der Code, der sie liest
    def rb_json(t):
        d = json.loads(t)
        top = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in (d.items() if isinstance(d, dict) else [])}
        return f"Schlüssel {json.dumps(top)[:600]}"
    probe("RankedBoost, Daten der Let’s-Go-Karte",
          "https://img.rankedboost.com/wp-content/plugins/k-Pokemon/assets/cache/megamap-lets-go-pikachu-eevee-791ae0729e4a.json",
          rb_json, keep=1_500_000)
    probe("RankedBoost, Kartencode (mega-map-loader)", "https://img.rankedboost.com/wp-content/plugins/template-framework/assets/js/rb-mega-map-loader.js",
          lambda t: "Muster: " + ", ".join(tile_patterns(t)[:5]) + f"; {t.count('tile')}× tile", keep=400_000)
    for g in ("heartgold-soulsilver", "firered-leafgreen", "sword-shield", "brilliant-diamond-shining-pearl", "scarlet-violet"):
        probe(f"RankedBoost, Karte {g}", f"https://rankedboost.com/pokemon/location/{g}/",
              lambda t: "große Karte: " + (", ".join(sorted(set(re.findall(r'data-mega-src="([^"]+)"', t)))[:3]) or "keine"), headers=html)

    # PokéTools: die Kacheln stehen im Code der Kartenseite (Next.js-Skripte); in den Skripten die Stellen mit „tile“ zeigen
    chunk_re = re.compile(r'/_next/static/chunks/[^"\\]+[.]js')

    def tile_spots(t):
        spots = [" ".join(t[max(0, m.start() - 120):m.start() + 160].split()) for m in re.finditer(r"tiles?[/`'\"]", t)][:3]
        return f"Muster: {', '.join(tile_patterns(t)[:5]) or '–'}" + ("; Stellen: " + " || ".join(spots) if spots else "")
    try:
        r = probe("PokéTools, Kartenseite Smaragd (Skripte)", "https://www.poketools.com/emerald/map",
                  lambda t: f"{len(set(chunk_re.findall(t)))} Skripte", headers=html).result(timeout=DIAG_HANG)
    except cf.TimeoutError:
        r = None
    for u in sorted(set(chunk_re.findall(r["text"])))[:30] if r else ():
        probe(f"PokéTools, Skript {u.rsplit('/', 1)[-1]}", "https://www.poketools.com" + u, tile_spots)
    for g in ("firered", "ruby", "crystal", "platinum", "heartgold"):
        probe(f"PokéTools, Karte {g}", f"https://www.poketools.com/{g}/map",
              lambda t: f"{t.count('kind')}× kind, Titel {(re.findall(r'<title>(.*?)</title>', t) or ['–'])[0][:80]}", headers=html)

    section("Kartenquellen aus der Recherche vom 12.11. (Gamer Guides, Pokédens)")

    def geojson(text):
        d = json.loads(text)
        fs = d.get("features") or []
        kinds = sorted({str((f.get("properties") or {}).get("category") or (f.get("properties") or {}).get("type") or "?") for f in fs})[:12]
        geo = sorted({(f.get("geometry") or {}).get("type", "?") for f in fs})
        return f"{len(fs)} Punkte ({', '.join(geo)}), Arten: {', '.join(kinds)}; Schlüssel: {', '.join(list((fs[0].get('properties') or {}))[:12]) if fs else '–'}"
    # Gamer Guides: Kartendaten als GeoJSON; die Kartenseiten nennen Bild bzw. Kacheln (Muster und Größe stehen im HTML)
    for n, name in ((49, "BDSP Untergrund"), (238, "Indigoblaue Scheibe")):
        probe(f"Gamer Guides, Punkte {name}", f"https://www.gamerguides.com/map/{n}/geojson", geojson, keep=True)
    for path, name in (("pokemon-brilliant-diamond-and-shining-pearl/maps/grand-underground", "BDSP Untergrund"),
                       ("pokemon-scarlet-and-violet/maps/the-indigo-disk", "Indigoblaue Scheibe")):
        probe(f"Gamer Guides, Kartenseite {name}", f"https://www.gamerguides.com/{path}",
              lambda t: f"Muster: {', '.join(tile_patterns(t)[:5]) or '–'}; {t.count('max_zoom')}× max_zoom", keep=True, headers=html)
    # Spiele ohne Karte (X/Y, Sonne/Mond, USUM): Regionskarten mit Bildkarte im PokéWiki (deutsche Ortsnamen),
    # Kartenbilder bei Bulbapedia und Pokémon Database; die Antworten bleiben für die Auswertung (keep)
    area_rx = re.compile(r"(?m)^\s*(?:rect|poly|circle)\s")
    file_rx = re.compile(r"[\w .-]+-Map [\w .äöüÆæ-]+[.](?:png|gif)")

    def imagemap(text):
        out = []
        for k, v in pokewiki.pages(text).items():
            files = ", ".join(sorted(set(file_rx.findall(v)))[:6]) or "–"
            out.append(f"{k}: {len(area_rx.findall(v))} Flächen, Bilder {files}")
        return "; ".join(out) or "keine Seiten"
    probe("PokéWiki, Bildkarten Kalos und Alola (Vorlagen)", pokewiki.batch_url(
        ["Vorlage:XY-Map Kalos", "Vorlage:SM-Map Alola", "Vorlage:USUM-Map Alola", "Vorlage:ORAS-Map Hoenn",
         "Vorlage:SW-Map Einall", "Vorlage:S2W2-Map Einall", "Vorlage:SDLP-Map Sinnoh"]), imagemap, keep=True)
    probe("Bulbapedia-Archiv, Kategorie Spielkarten", "https://archives.bulbagarden.net/w/api.php?action=query&list=categorymembers"
          "&cmtitle=Category:Game_maps&cmlimit=500&cmtype=file&format=json",
          lambda t: f"{len(json.loads(t)['query']['categorymembers'])} Dateien", keep=True)
    map_rx = re.compile(r'href="(/map/[^"]+)"')
    probe("Pokémon Database, Regionskarten", "https://pokemondb.net/map",
          lambda t: f"{t.count('<area')} Flächen, {len(set(map_rx.findall(t)))} Kartenseiten", keep=True, headers=html)
    probe("Pokédens, Raid-Nester Schwert/Schild (Inhalt je Nest)", "https://pokedens.github.io/data.json",
          lambda t: (lambda d: f"{type(d).__name__} mit {len(d)} Einträgen; Schlüssel: {', '.join(list(d)[:8]) if isinstance(d, dict) else ', '.join(list(d[0])[:8]) if d and isinstance(d[0], dict) else '–'}")(json.loads(t)), keep=True)

    section("Kartenbilder im Detail (seit 0.47): Größe der Bilder für X/Y, Sonne/Mond, USUM, ORAS, BDSP")

    def sizes(text):
        d = json.loads(text).get("query") or {}
        xs = [(i.get("name") or "", i.get("width"), i.get("height")) for i in d.get("allimages") or []]
        xs += [(p.get("title") or "", (p.get("imageinfo") or [{}])[0].get("width"), (p.get("imageinfo") or [{}])[0].get("height"))
               for p in (d.get("pages") or {}).values()] if isinstance(d.get("pages"), dict) else \
              [(p.get("title") or "", (p.get("imageinfo") or [{}])[0].get("width"), (p.get("imageinfo") or [{}])[0].get("height"))
               for p in d.get("pages") or []]
        return "; ".join(f"{n} {w}×{h}" if w else f"{n} fehlt" for n, w, h in xs[:40]) or "keine Bilder"
    # PokéWiki: alle Bilder mit diesen Anfängen (die Vorlagen nennen sie), mit Größe; Bulbapedia: einzelne Regionskarten
    for pre in ("XY-Map", "SM-Global-Map", "SM-Map", "USUM-Global-Map", "USUM-Map", "Map Hoenn", "ORAS-Map", "SDLP-Map", "Karte Kalos", "Karte Alola"):
        probe(f"PokéWiki, Bilder „{pre}…“ mit Größe", "https://www.pokewiki.de/api.php?action=query&list=allimages&aiprop=size|url"
              f"&ailimit=100&format=json&formatversion=2&aiprefix={urllib.parse.quote(pre)}", sizes, keep=True)
    for t in ("XY-Map Kalos", "USUM-Map Alola", "ORAS-Map Hoenn"):
        probe(f"PokéWiki, Vorlage {t} (ganz)", pokewiki.batch_url(["Vorlage:" + t]), imagemap, keep=300_000)
    bulba = ["Kalos XY.png", "Melemele Island Map.png", "Melemele Island Map 2.png", "Ula'ula Island Map.png", "Ula'ula Island Map 2.png",
             "Poni Island Map.png", "Poni Island Map 2.png", "Sinnoh BDSP.png", "UGMAP.png", "Galar Sh.png", "Galar Sh DLC.png",
             "Hoenn Soaring ORAS Map.png", "Sinnoh DP.png", "Sinnoh.png", "Hisui.png", "Paldea.png", "Kitakami.png", "Blueberry Academy.png"]
    # Recherche 12.11. (Kalos und Alola): große Fan-Karten als PNG, MewMaps (Insel- und Gebietskarten), japanische Übersicht
    def png_info(text):
        b = text.encode("latin-1", "replace") if isinstance(text, str) else text
        wh = raidnester.png_size(b)
        return f"PNG {wh[0]} × {wh[1]} px, {len(b)} Bytes" if wh else f"kein PNG ({len(b)} Bytes, Anfang {b[:12]!r})"
    for u, name in (("http://www.40k.zombiecrisis.org/map.png", "Kalos"), ("http://40k.zombiecrisis.org/map-alola.png", "Alola")):
        probe(f"Fan-Karte {name} (PNG)", u, png_info, raw=True)
    img_rx = re.compile(r'(?:src|href)="([^"]+?\.(?:jpe?g|png|webp))"', re.I)
    for path, name in (("sun-moon", "Sonne/Mond"), ("ultra-sun-ultra-moon", "Ultrasonne/Ultramond")):
        probe(f"MewMaps, {name}", f"https://www.mewmaps.org/{path}",
              lambda t: f"{len(set(img_rx.findall(t)))} Bilder: {', '.join(sorted(set(img_rx.findall(t)))[:12])}", keep=True, headers=html)
    # 0.48.1: MewMaps verlinkt die Karten nur (Google Drive): Größe der Inselkarten; FrontierNav lädt alles per Skript:
    # die Skripte nach Adressen von Daten durchsuchen (Marker mit Koordinaten?)
    def img_info(text):
        b = text.encode("latin-1", "replace") if isinstance(text, str) else text
        wh = raidnester.png_size(b)
        if wh:
            return f"PNG {wh[0]} × {wh[1]} px, {len(b)} Bytes"
        i = 2
        while b[:2] == b"\xff\xd8" and i + 9 < len(b) and b[i] == 0xFF:
            if b[i + 1] in (0xC0, 0xC1, 0xC2):
                return f"JPEG {int.from_bytes(b[i + 7:i + 9], 'big')} × {int.from_bytes(b[i + 5:i + 7], 'big')} px, {len(b)} Bytes"
            i += 2 + int.from_bytes(b[i + 2:i + 4], "big")
        return f"kein Bild ({len(b)} Bytes, Anfang {b[:40]!r})"
    for fid, name in (("1SBdYdLXsasmpgfDZAqOVVw2ap3L6TbDi", "SM Akala"), ("1nViijDWmSY6xQCsqlxaLeOrUjY6xi5TK", "SM Ula'ula"),
                      ("1b4-8C-A123vAd-2iq0JiRcDGk-lb3D09", "SM Poni"), ("1GALSC0RLFUE5na21LVNWHqOMwASflw_m", "USUM Mele-Mele"),
                      ("1oAFE9RUbkkZzHlO4UQ6fLjpQbvzlmxC2", "USUM Akala/Übersicht"), ("1lQxMilRC8NfT7m6twLWebCQs_PvFvEeH", "USUM Ula'ula"),
                      ("1DsTHOuQyBA9X3QquPsoTvhgnTKPf61tr", "USUM Poni")):
        probe(f"MewMaps, Inselkarte {name} (Google Drive)", f"https://drive.google.com/uc?export=download&id={fid}", img_info, raw=True)
    api_rx = re.compile(r"""["'`]((?:https?:)?/[\w./-]*(?:api|graphql|tiles?|entit|marker|\.json)[\w./{}?=&-]*)["'`]""", re.I)
    probe("FrontierNav, Alola-Karte (Seite)", "https://frontiernav.net/wiki/pokemon-sun-moon/visualisations/maps?m=alola-map",
          lambda t: "Skripte: " + ", ".join(re.findall(r'src="(/static/[^"]+)"', t)), keep=True, headers=html)
    for js in ("8a5a94fd-a.js", "27648ee4-a.js", "46bc1287-a.js"):
        probe(f"FrontierNav, Skript {js}", f"https://frontiernav.net/static/{js}",
              lambda t: f"{len(t)} Zeichen; Adressen: " + ", ".join(sorted(set(api_rx.findall(t)))[:30]), keep=200_000)
    probe("Japanische X/Y-Kartenübersicht", "https://xn--rckteqa2e6038anjua.com/xy/pokemon_xy_map.html",
          lambda t: f"{t.count('<area')} Flächen, {len(set(img_rx.findall(t)))} Bilder: {', '.join(sorted(set(img_rx.findall(t)))[:8])}", keep=True, headers=html)
    probe("Bulbapedia-Archiv, Regionskarten mit Größe", "https://archives.bulbagarden.net/w/api.php?action=query&prop=imageinfo"
          "&iiprop=size|url&format=json&titles=" + urllib.parse.quote("|".join("File:" + b for b in bulba)), sizes, keep=True)

    section("Alola und die Quellen der Liste vom 12.11. (anderssprachige Wikis, pokemon.com)")
    # 0.52: PokéWiki hat je Ort ein Inselbild mit hervorgehobenem Ort (94 Bilder, 270 px): Vergleich mit dem leeren
    # Inselbild ergibt die Lage. Dazu die größeren Inselkarten von Bulbapedia, um zu sehen, ob beide zusammenpassen
    pw_img = "https://www.pokewiki.de/images/"
    for path, name in (("f/fe/USUM-Map_Mele-Mele.png", "Mele-Mele leer"), ("3/39/USUM-Map_Mele-Mele_Lili%E2%80%99i.png", "Mele-Mele Lili’i"),
                       ("1/19/USUM-Map_Mele-Mele_Route_1_%28Alola%29.png", "Mele-Mele Route 1"), ("0/0a/USUM-Map_Ula-Ula.png", "Ula-Ula leer"),
                       ("6/66/USUM-Map_Ula-Ula_Route_10_%28Alola%29.png", "Ula-Ula Route 10"), ("9/98/USUM-Map_Akala.png", "Akala leer"),
                       ("e/e1/USUM-Map_Poni.png", "Poni leer"), ("1/14/USUM-Global-Map_Mele-Mele.png", "Übersicht Mele-Mele")):
        probe(f"PokéWiki, Inselbild {name}", pw_img + path, img_info, raw=True, keep=True)
    for f in ("Melemele Island Map 2.png", "Ula'ula Island Map 2.png", "Poni Island Map 2.png"):
        probe(f"Bulbapedia-Archiv, Bild {f}", "https://archives.bulbagarden.net/wiki/Special:FilePath/" + urllib.parse.quote(f),
              img_info, raw=True, keep=True)
    probe("Bulbapedia-Archiv, Suche Akala Island Map", "https://archives.bulbagarden.net/w/api.php?action=query&list=allimages"
          "&aiprefix=Akala&aiprop=size|url&ailimit=50&format=json&formatversion=2", sizes, keep=True)
    # die anderssprachigen Wikis (alle MediaWiki): Seite der Region und einer Insel als Wikitext, Bildkarten (imagemap)?
    def wiki_maps(text):
        j = json.loads(text)
        if "parse" not in j:
            return f"Seite gibt es nicht ({(j.get('error') or {}).get('code', '?')})"
        p = j["parse"]
        wt = p["wikitext"]["*"] if isinstance(p["wikitext"], dict) else p["wikitext"]
        files = sorted(set(re.findall(r"(?:File|Datei|Fichier|Archivo|Immagine|文件|ファイル|Image):([^|\]\n]+\.(?:png|jpe?g|gif))", wt, re.I)))
        return (f"Seite „{p['title']}“, {len(wt)} Zeichen, {wt.count('<imagemap')} Bildkarten, {wt.count('rect ') + wt.count('poly ')} Flächen; "
                f"Bilder: {', '.join(files[:12])}")
    wikis = (("Poképédia (FR)", "https://www.pokepedia.fr/api.php", ("Alola", "Île de Mele-Mele")),
             ("WikiDex (ES)", "https://www.wikidex.net/api.php", ("Alola", "Isla Melemele")),
             ("Pokémon Central (IT)", "https://wiki.pokemoncentral.it/api.php", ("Alola", "Mele Mele")),
             ("52poke (CN)", "https://wiki.52poke.com/api.php", ("阿罗拉地区", "美乐美乐岛")),
             ("ポケモンWiki (JA)", "https://wiki.xn--rckteqa2e.com/w/api.php", ("アローラ地方", "メレメレ島")))
    for wname, api, pages in wikis:
        probe(f"{wname}, API", api + "?action=query&meta=siteinfo&format=json", wiki_info)
        for page in pages:
            probe(f"{wname}, Seite {page}", api + "?action=parse&page=" + urllib.parse.quote(page) + "&prop=wikitext&format=json&redirects=1",
                  wiki_maps, keep=300_000)
    probe("pokemon.com, Pokédex-Daten", "https://www.pokemon.com/us/api/pokedex/kalos",
          lambda t: f"{len(json.loads(t))} Einträge, Felder: {', '.join(sorted(json.loads(t)[0])) if json.loads(t) else '-'}", keep=60_000)
    probe("pokemon.com, Pokédex-Seite Bisasam (DE)", "https://www.pokemon.com/de/pokedex/bisasam",
          lambda t: f"{len(t)} Zeichen, Titel: {(re.search(r'<title>([^<]*)', t) or [None, '?'])[1].strip()}", keep=150_000, headers=html)

    section("Kampfdaten (Movesets, Nutzung)")
    probe("pkmn, Smogon-Sets Gen 9", "https://data.pkmn.cc/sets/gen9.json",
          lambda t: f"{len(json.loads(t))} Pokémon mit Sets")
    probe("Smogon, Nutzungsstatistik", "https://www.smogon.com/stats/", lambda t: f"{t.count('href=')} Einträge, neuester Monat {(smogon.months(t) or ['–'])[0]}")
    probe("Showdown, learnsets.ts", SD_RAW + "learnsets.ts", lambda t: f"{t.count('learnset:')} Lernlisten (TM, Lehrer, Ei je Generation)")
    probe("Showdown, formats-data.ts", SD_RAW + "formats-data.ts", lambda t: f"{t.count('tier:')} Pokémon mit Stufe (OU, UU …)")
    probe("Showdown, Random-Battle-Sets Gen 9", SD_RAW + "random-battles/gen9/sets.json",
          lambda t: f"{len(json.loads(t))} Pokémon mit Rollen und Attacken")
    probe("Showdown, abilities.ts", SD_RAW + "abilities.ts", lambda t: f"{t.count('num:')} Fähigkeiten mit Wirkung im Code")
    # Wächter: rührt sich DIAG_HANG Sekunden lang nichts, gelten die offenen Abfragen als hängend; der Test endet trotzdem
    seen, last = -1, time.monotonic()
    while True:
        done, todo = cf.wait(futs, timeout=min(5, DIAG_HANG))
        if not todo:
            break
        if stand["fertig"] != seen:
            seen, last = stand["fertig"], time.monotonic()
        elif time.monotonic() - last > DIAG_HANG:
            with lock:
                hung = list(stand["laeuft"])
            for k, x in enumerate(lines):
                if x and x.endswith(": keine Antwort") and x[:-len(": keine Antwort")] in hung:
                    lines[k] = x + f" (hängt nach {DIAG_HANG} s ohne Fortschritt, abgebrochen)"
            lines.append("")
            lines.append(f"Abgebrochen: {len(todo)} Abfragen kamen nicht mehr dran oder hingen ({', '.join(hung)}).")
            break
    for p in pools.values():
        p.shutdown(wait=False, cancel_futures=True)
    if proben:
        lines.append("")
        lines.append(f"{len(proben)} Probe-Seiten zum Herunterladen (Knopf „Proben herunterladen“).")
    return lines
