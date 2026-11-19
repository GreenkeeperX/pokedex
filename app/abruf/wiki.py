"""PokéWiki: Attacken und Pokémon in Legenden: Arceus, deutsche Texte.

Teil des Pakets app.abruf; alle Namen sind auch dort erreichbar.
"""
from datetime import timedelta

from .. import db, fehler, pokewiki, store

from .grundlage import (REST_H, STATE, WIKI_GAMES, WIKI_PAUSE, WIKI_TEXT_BATCH, WIKI_TEXT_TAGE, _Source, _ago, _iso,
    _resting, now)


def wiki_titles(con, spiel):
    """Deutsche Namen der Attacken, die im Spiel jemand lernt, und der Arten im Spiel (Seitentitel im PokéWiki)."""
    g = con.execute("SELECT id FROM spiel WHERE kennung = ?", (spiel,)).fetchone()
    if not g:
        return [], []
    moves = [r[0] for r in con.execute("SELECT DISTINCT a.name FROM pokemon_moves pm JOIN attacke a ON a.id = pm.move_id "
                                       "WHERE pm.version_group_id = ? ORDER BY a.name", (g[0],)) if r[0]]
    species = [r[0] for r in con.execute(
        "SELECT DISTINCT n.name FROM spiel_form sf JOIN form f ON f.id = sf.form JOIN pokemon_species_names n "
        "ON n.pokemon_species_id = f.art AND n.local_language_id = 6 WHERE sf.spiel = ? ORDER BY n.name", (g[0],)) if r[0]]
    return moves, species


def _pokewiki(st, log, at):
    """Werte aus dem PokéWiki, die sonst fehlen: {"attacken": {Spiel: {Name: Werte}}, "items": {Spiel: {Art: [Items]}}}.
    Die Namen kommen aus der bisherigen Datenbank (ohne sie gibt es noch nichts zu fragen). Bei Sperre oder Fehlern gilt
    das Ergebnis des letzten Laufs (pokewiki.json im Datenordner)."""
    old = store.load_json("pokewiki.json", {})
    old_texts = store.load_json("pokewiki_texte.json", {})
    if old_texts:
        old["texte"] = old_texts            # liegen in einer eigenen Datei, siehe _wiki_texts
    if _resting(st, "pokewiki", at):
        log(f"PokéWiki ruht bis {st['rest']['pokewiki'][:16].replace('T', ' ')} UTC")
        return old
    con = db.game()
    if con is None:
        return old
    try:
        titles = {sp: wiki_titles(con, sp) for sp in WIKI_GAMES}
    except Exception as e:
        log(f"PokéWiki: Namen nicht lesbar ({e})")
        fehler.melden(e, "Namen", "pokewiki")
        return old
    finally:
        con.close()
    src = _Source("pokewiki", log, pause=WIKI_PAUSE)
    out = {"attacken": {}, "items": {}}
    for sp, (moves, species) in titles.items():
        for kind, names, section0 in (("attacken", moves, True), ("items", species, False)):
            got = {}
            for i in range(0, len(names), pokewiki.BATCH):
                STATE.update(step=f"PokéWiki: {'Attacken' if kind == 'attacken' else 'Pokémon'}", done=i, total=len(names))
                t = src.get(pokewiki.batch_url(names[i:i + pokewiki.BATCH], section0))
                if src.stopped:
                    break
                try:
                    for name, wt in pokewiki.pages(t or "{}").items():
                        v = pokewiki.la_move(wt) if kind == "attacken" else [x for x in pokewiki.held_items(wt) if x["spiel"] == sp]
                        if v:
                            got[name] = v
                except ValueError as e:
                    log(f"PokéWiki: Antwort nicht lesbar ({e})")
            out[kind][sp] = got
        if src.stopped:
            break
    # Karte von Legenden: Arceus (Kristalle, Verzerrungen, Massenauftreten, Bäume, Alphas, Items am Boden)
    karte = {}
    for i, area in enumerate(pokewiki.MAP_AREAS if not src.stopped else ()):
        STATE.update(step="PokéWiki: Karte", done=i, total=len(pokewiki.MAP_AREAS))
        got = {kind: src.get(pokewiki.map_url(kind, area)) for kind in pokewiki.MAP_KINDS}
        if src.stopped:
            break
        if got.get("pokemon"):
            karte[area] = {k: v for k, v in got.items() if v}
    out["karte"] = {"legends-arceus": karte} if karte else old.get("karte", {})
    texte = _wiki_texts(src, log, at)
    if texte:
        out["texte"] = texte
    st["sources"]["pokewiki"] = src.result(seiten=sum(len(v) for k in ("attacken", "items") for v in out[k].values()),
                                           karten=len(karte), texte=sum(len(texte.get(k) or {}) for k in WIKI_TEXT_KINDS))
    if src.blocked:
        st["rest"]["pokewiki"] = _iso(now() + timedelta(hours=REST_H))
    if src.stopped or not any(out["attacken"].values()):
        return dict(old, texte=texte) if texte else old
    store.save_json("pokewiki.json", {k: v for k, v in out.items() if k != "texte"})
    return out


WIKI_TEXT_KINDS = ("pokemon", "attacken", "faehigkeiten")
_WIKI_SUFFIX = {"attacken": " (Attacke)", "faehigkeiten": " (Fähigkeit)"}


def wiki_text_titles(con):
    """Deutsche Namen aller Arten, Attacken und Fähigkeiten: {Art der Seite: [Titel]}."""
    def names(sql):
        return sorted({r[0] for r in con.execute(sql) if r[0]})
    return {"pokemon": names("SELECT name FROM pokemon_species_names WHERE local_language_id = 6"),
            "attacken": names("SELECT name FROM attacke"),
            "faehigkeiten": names("SELECT name FROM ability_names WHERE local_language_id = 6 AND ability_id < 10000")}


def _wiki_page(kind, wt):
    """Was aus einer Seite übernommen wird, oder None, wenn sie nichts davon trägt (etwa eine Begriffsklärung)."""
    if kind == "pokemon":
        v = {"texte": pokewiki.dex_texts(wt), "aufgaben": pokewiki.research_tasks(wt)}
        return v if v["texte"] or v["aufgaben"] else None
    v = pokewiki.move_texts(wt) if kind == "attacken" else pokewiki.ability_texts(wt)
    return {"texte": v} if v else None


def _wiki_texts(src, log, at):
    """Deutsche Texte je Spiel aus dem PokéWiki (pokewiki_texte.json): {"stand", Art: {Name: {"texte": {Kürzel: Text},
    "aufgaben": […]}}}. Alle WIKI_TEXT_TAGE Tage alles neu, sonst nur Namen, die noch fehlen. Seiten, die die API in
    einer Antwort nicht mehr unterbringt, kommen in einer zweiten Runde; tragen Attacken oder Fähigkeiten nichts, wird
    „Name (Attacke)“ bzw. „Name (Fähigkeit)“ versucht."""
    old = store.load_json("pokewiki_texte.json", {})
    con = db.game()
    if con is None or src.stopped:
        return old
    try:
        titles = wiki_text_titles(con)
    except Exception as e:
        log(f"PokéWiki: Namen für Texte nicht lesbar ({e})")
        fehler.melden(e, "Namen für Texte", "pokewiki")
        return old
    finally:
        con.close()
    age = _ago(old.get("stand"), at)
    full = age is None or age >= timedelta(days=WIKI_TEXT_TAGE)
    out = {"stand": old.get("stand"), "gefragt": dict(old.get("gefragt") or {})}
    asked = 0
    labels = {"pokemon": "Pokédex-Einträge", "attacken": "Attackentexte", "faehigkeiten": "Fähigkeitstexte"}

    def ask(kind, names, have):
        """Seiten holen; gibt (fehlt in der Antwort, ohne Texte) zurück. names: {Seitentitel: Name}."""
        nonlocal asked
        absent, empty, todo = [], [], list(names)
        for i in range(0, len(todo), WIKI_TEXT_BATCH):
            part = todo[i:i + WIKI_TEXT_BATCH]
            STATE.update(step=f"PokéWiki: {labels[kind]}", done=i, total=len(todo))
            t = src.get(pokewiki.batch_url(part))
            asked += 1
            if src.stopped:
                break
            try:
                got = pokewiki.pages(t or "{}")
            except ValueError as e:
                log(f"PokéWiki: Antwort nicht lesbar ({e})")
                got = {}
            for title in part:
                v = _wiki_page(kind, got[title]) if title in got else None
                if v:
                    have[names[title]] = v
                else:
                    (absent if title not in got else empty).append(names[title])
        return absent, empty

    for kind in WIKI_TEXT_KINDS:
        have = dict(old.get(kind) or {})
        done = set() if full else set(out["gefragt"].get(kind) or ())
        todo = [t for t in titles[kind] if full or (t not in have and t not in done)]
        absent, empty = ask(kind, {t: t for t in todo}, have) if todo else ([], [])
        if absent and not src.stopped:              # fehlt in der Antwort: Antwort war voll, oder es gibt die Seite nicht
            a2, e2 = ask(kind, {t: t for t in absent}, have)
            empty += a2 + e2
        if empty and kind in _WIKI_SUFFIX and not src.stopped:
            ask(kind, {t + _WIKI_SUFFIX[kind]: t for t in empty}, have)
        out[kind] = have
        if todo and not src.stopped:
            out["gefragt"][kind] = sorted(set(titles[kind]) - set(have))      # ohne Texte: erst beim nächsten vollen Lauf
    if full and not src.stopped:
        out["stand"] = _iso(at)
    if asked:
        n = {k: len(out.get(k) or {}) for k in WIKI_TEXT_KINDS}
        log(f"PokéWiki: Texte für {n['pokemon']} Pokémon, {n['attacken']} Attacken und {n['faehigkeiten']} Fähigkeiten"
            + (" (unvollständig, Rest beim nächsten Abgleich)" if src.stopped else ""))
        store.save_json("pokewiki_texte.json", out)
    return out
