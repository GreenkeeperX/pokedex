"""Seiten von Serebii, BisaFans und Bulbapedia (Shiny-Sperren, Trainer).

Teil des Pakets app.abruf; alle Namen sind auch dort erreichbar.
"""
import json
import urllib.parse
from datetime import timedelta

from .. import bisafans, fehler, pokewiki, serebii, shiny, store

from .grundlage import REST_H, STATE, _Source, _iso, _resting, now


SEREBII_PAUSE = 2.0         # Sekunden zwischen zwei Seiten bei Serebii


def _serebii(st, log, at):
    """Seiten von Serebii: Abklingzeiten in Legenden: Z-A und die Pokédexe von Pokopia, {"za": {...}, "pokopia": {Dex: [...]}}.
    Fehlt etwas (Sperre, Fehler, Seite ohne Treffer), gilt dafür der letzte Lauf (serebii.json im Datenordner)."""
    old = store.load_json("serebii.json", {})
    if _resting(st, "serebii", at):
        log(f"Serebii ruht bis {st['rest']['serebii'][:16].replace('T', ' ')} UTC")
        return old
    src = _Source("serebii", log, pause=SEREBII_PAUSE)
    STATE["step"] = "Serebii: Attacken in Legenden: Z-A"
    za = serebii.za_cooldowns(src.get(serebii.ZA_ATTACKS) or "")
    pk = {}
    for dex, url in serebii.POKOPIA.items():
        if src.stopped:
            break
        STATE["step"] = f"Serebii: Pokopia, {serebii.POKOPIA_DEX[dex]}"
        rows = serebii.pokopia_dex(src.get(url, absent=(404,)) or "")
        if rows:
            pk[dex] = rows
    out = {"za": za or old.get("za") or {}, "pokopia": {**(old.get("pokopia") or {}), **pk}}
    st["sources"]["serebii"] = src.result(abklingzeiten=len(za), pokopia=sum(len(v) for v in pk.values()))
    if src.blocked:
        st["rest"]["serebii"] = _iso(now() + timedelta(hours=REST_H))
    log(f"Serebii: {len(za)} Abklingzeiten in Z-A, Pokopia " + (", ".join(f"{serebii.POKOPIA_DEX[k]} {len(v)}" for k, v in pk.items()) or "ohne Treffer"))
    if out["za"] or out["pokopia"]:
        if za or pk:
            store.save_json("serebii.json", out)
        return out
    return old


BISA_PAUSE = 3.0            # Sekunden zwischen zwei Seiten bei BisaFans


def _bisafans(st, log, at):
    """Seiten von BisaFans: die Aufträge in Legenden: Arceus auf Deutsch, {"la_auftraege": [...]}. Bei Sperre, Fehler oder
    einer Seite ohne Treffer gilt der letzte Lauf (bisafans.json im Datenordner)."""
    old = store.load_json("bisafans.json", {})
    if _resting(st, "bisafans", at):
        log(f"BisaFans ruht bis {st['rest']['bisafans'][:16].replace('T', ' ')} UTC")
        return old
    src = _Source("bisafans", log, pause=BISA_PAUSE)
    STATE["step"] = "BisaFans: Aufträge in Legenden: Arceus"
    rows = bisafans.la_requests(src.get(bisafans.LA_REQUESTS) or "")
    pages = []
    for i, url in enumerate(bisafans.LA_STORY):
        if src.stopped:
            break
        STATE.update(step="BisaFans: Hauptmissionen in Legenden: Arceus", done=i, total=len(bisafans.LA_STORY))
        pages.append(src.get(url, absent=(404,)) or "")
    story = bisafans.la_missions(pages)
    za_pages = []
    for url in bisafans.ZA_REQUESTS:
        if src.stopped:
            break
        STATE.update(step="BisaFans: Nebenmissionen in Legenden: Z-A")
        za_pages.append(src.get(url, absent=(404,)) or "")
    za_rows = bisafans.merged_requests(za_pages)
    # Haupt- und Dimensions-Missionen in Z-A (und Nebenmissionen, die BisaFans noch fehlen) aus dem PokéWiki
    za, bbq = {}, []
    if not _resting(st, "pokewiki", at):
        STATE.update(step="PokéWiki: Missionen in Legenden: Z-A, Blaubeer-Missionen")
        wsrc = _Source("pokewiki", log, pause=BISA_PAUSE)
        t = wsrc.get(pokewiki.batch_url([pokewiki.ZA_MISSIONS, pokewiki.BBQ_PAGE]), absent=(404,))
        try:
            ps = pokewiki.pages(t) if t else {}
            za = pokewiki.za_missions(ps.get(pokewiki.ZA_MISSIONS, ""))
            bbq = pokewiki.bbq_missions(ps.get(pokewiki.BBQ_PAGE, ""))
        except ValueError as ex:
            fehler.melden(ex, "Missionen", "pokewiki")
            za = {}
    have = {r["nr"] for r in za_rows}
    for x in (za or {}).get("neben") or []:
        if x["nr"] not in have:
            za_rows.append({"nr": x["nr"], "name": x["name"], "beschreibung": x["beschreibung"], "aufgabe": "", "ort": "",
                            "loesung": x.get("freischaltung") and "Freigeschaltet: " + x["freischaltung"] or "", "belohnung": x["belohnung"]})
    za_rows.sort(key=lambda r: r["nr"])
    za_story = [dict(x, kapitel=1) for x in (za or {}).get("haupt") or []] + \
        [dict(x, nr=100 + x["nr"], kapitel=2) for x in (za or {}).get("dimension") or []]
    st["sources"]["bisafans"] = src.result(auftraege=len(rows), missionen=len(story), za_nebenmissionen=len(za_rows), za_missionen=len(za_story))
    if src.blocked:
        st["rest"]["bisafans"] = _iso(now() + timedelta(hours=REST_H))
    log(f"BisaFans: {len(rows)} Aufträge und {len(story)} Hauptmissionen in Legenden: Arceus" + ("" if rows else ", es gilt der letzte Lauf")
        + f"; Legenden: Z-A {len(za_rows)} Nebenmissionen, {len(za_story)} Haupt- und Dimensions-Missionen (PokéWiki)"
        + f"; {len(bbq)} Blaubeer-Missionen (PokéWiki)")
    if rows or za_rows or bbq:
        out = {"la_auftraege": rows or old.get("la_auftraege") or [], "la_missionen": story or old.get("la_missionen") or [],
               "za_auftraege": za_rows or old.get("za_auftraege") or [], "za_missionen": za_story or old.get("za_missionen") or [],
               "blaubeer": bbq or old.get("blaubeer") or []}
        store.save_json("bisafans.json", out)
        return out
    return old


SHINY_DAYS = 30            # so oft holt der Abgleich die Liste der Shiny-Sperren neu
SHINY_PAGE = "List_of_unobtainable_Shiny_Pokémon"


def _shiny(st, log, at):
    """0.51: Bulbapedia „List of unobtainable Shiny Pokémon“ als Wikitext: {"am", "text"} in bulbapedia_shiny.json.
    Jünger als SHINY_DAYS: der letzte Lauf gilt."""
    old = store.load_json("bulbapedia_shiny.json", {}) or {}
    if old.get("text") and old.get("am", "") > _iso(now() - timedelta(days=SHINY_DAYS)):
        return old
    if _resting(st, "bulbapedia", at):
        return old
    src = _Source("bulbapedia", log)
    STATE.update(step="Bulbapedia: Shiny-Sperren")
    t = src.get("https://bulbapedia.bulbagarden.net/w/api.php?action=parse&page=" + urllib.parse.quote(SHINY_PAGE)
                + "&prop=wikitext&format=json&redirects=1")
    text = ""
    try:
        w = (json.loads(t) if t else {}).get("parse", {}).get("wikitext")
        text = w.get("*", "") if isinstance(w, dict) else (w or "")
    except ValueError as ex:
        fehler.melden(ex, "Shiny-Sperren", "bulbapedia")
        text = ""
    st["sources"]["bulbapedia"] = src.result(shiny=len(shiny.parse(text)) if text else 0)
    if src.blocked:
        st["rest"]["bulbapedia"] = _iso(now() + timedelta(hours=REST_H))
    if not text:
        return old
    out = {"am": _iso(now()), "text": text}
    store.save_json("bulbapedia_shiny.json", out)
    return out


TRAINER_DAYS = 7           # so oft holt der Abgleich die Trainerseiten neu (sie ändern sich selten)


def _trainer(st, log, at):
    """Teams der Arenaleiter, Top Vier, Champs und Rivalen aller Hauptspiele aus dem PokéWiki, dazu die Trainer auf den
    Ortsseiten (Routen, Höhlen, Städte); Kategorien, dann die Seiten zu je 50: {"am", "teams": [...]} in pokewiki_trainer.json. Jünger als TRAINER_DAYS: der letzte Lauf gilt."""
    old = store.load_json("pokewiki_trainer.json", {}) or {}
    cats = sorted(pokewiki.TRAINER_CATS)          # neue Kategorien (0.48.6: Hisui) holen sofort neu, nicht erst nach TRAINER_DAYS
    # 0.56.2: eine Datei von vor 0.48.6 nennt ihre Kategorien nicht; sie galt als aktuell, und die Trainer aus Hisui kamen
    # erst nach TRAINER_DAYS. Fehlt die Angabe, holt der Abgleich jetzt neu
    if old.get("teams") and old.get("am", "") > _iso(now() - timedelta(days=TRAINER_DAYS)) and old.get("kategorien") == cats:
        return old
    if _resting(st, "pokewiki", at):
        return old
    src = _Source("pokewiki", log, pause=BISA_PAUSE)
    roles = {}
    for cat, rolle in pokewiki.TRAINER_CATS.items():
        cont, n = None, 0
        while n < 10 and not src.stopped:
            STATE.update(step=f"PokéWiki: Trainer ({cat})")
            t = src.get(pokewiki.category_url(cat, cont), absent=(404,))
            try:
                titles, cont = pokewiki.category_members(t) if t else ([], None)
            except ValueError as ex:
                fehler.melden(ex, f"Trainer ({cat})", "pokewiki")
                titles, cont = [], None
            for x in titles:
                roles.setdefault(x, rolle)
            n += 1
            if not cont:
                break
    names, teams = sorted(roles), []
    for i in range(0, len(names), pokewiki.BATCH):
        if src.stopped:
            break
        STATE.update(step="PokéWiki: Teams der Trainer", done=i, total=len(names))
        t = src.get(pokewiki.batch_url(names[i:i + pokewiki.BATCH]))
        try:
            got = pokewiki.pages(t) if t else {}
        except ValueError as ex:
            fehler.melden(ex, "Teams der Trainer", "pokewiki")
            got = {}
        for title, wt in got.items():
            teams += pokewiki.trainer_teams(wt, title, roles.get(title, ""))
    teams = pokewiki.dedupe_teams(teams)
    st["sources"]["trainer"] = src.result(trainer=len(names), teams=len(teams))
    if src.blocked:
        st["rest"]["pokewiki"] = _iso(now() + timedelta(hours=REST_H))
    log(f"PokéWiki: {len(teams)} Teams von {len(names)} Trainern" + ("" if teams else ", es gilt der letzte Lauf"))
    if teams and not src.stopped:
        out = {"am": _iso(now()), "teams": teams, "kategorien": cats}
        store.save_json("pokewiki_trainer.json", out)
        return out
    return old
