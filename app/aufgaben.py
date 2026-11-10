"""Auftrag zu „Zu erledigen“ (ab 0.8.0), ohne Netz und ohne Datenbank.

Die offenen Abweichungen zwischen PokéAPI und Showdown als Text zum Einfügen in einen KI-Chat (`task`). Die Antwort ist
JSON mit derselben Kennung je Eintrag (`parse`): erst Vorschau, dann übernommen. Was nicht mehr offen ist oder keine
erlaubte Antwort trägt, bleibt liegen und steht in der Vorschau."""
import json
import re

MARK = "pokedex-aufgaben"
BATCH = 60          # so viele Einträge je Auftrag
WERTE = ("pokeapi", "showdown", "egal")

INTRO = ("Hilf mir, Abweichungen in meinen Pokémon-Spieldaten zu klären. Zwei Quellen (PokéAPI und Pokémon Showdown) nennen für "
         "dieselbe Angabe verschiedene Werte. Prüfe jeden Eintrag einzeln, etwa bei Bulbapedia, im PokéWiki oder bei Serebii, "
         "und sag, welche Quelle für den neuesten Stand der Hauptspiele recht hat. Nichts erfinden: was sich nicht belegen "
         "lässt, bekommt die Antwort „unklar“.")
FORM = ("Antworte nur mit JSON in genau diesem Aufbau, ohne Text davor oder danach:\n"
        '{"' + MARK + '": 1, "antworten": [{"key": "<Kennung>", "wert": "pokeapi", "grund": "<ein Satz>", '
        '"quelle": "<Adresse der Seite>"}]}\n'
        "Erlaubte Werte: „pokeapi“ (PokéAPI stimmt), „showdown“ (Showdown stimmt), „egal“ (beide vertretbar oder nicht "
        "spielrelevant) oder „unklar“.")


def task(rows, batch=BATCH):
    """Auftragstext für die offenen Abweichungen: {"text", "offen", "im_auftrag"}."""
    todo = [r for r in rows if not r.get("entscheidung")]
    part = todo[:batch]
    lines = [f"- Kennung {r['key']} | {r.get('name', '')} | {r.get('feld', '')} | PokéAPI: {r.get('pokeapi', '')} | "
             f"Showdown: {r.get('showdown', '')}" for r in part]
    text = "\n\n".join([INTRO, "Einträge:\n" + "\n".join(lines), FORM]) if part else ""
    return {"text": text, "offen": len(todo), "im_auftrag": len(part)}


def parse(text, rows):
    """Antwort lesen: {"uebernehmen": [{key, name, feld, wert, grund, quelle}], "liegen": [{key, warum}]}.
    Wirft ValueError, wenn der Text keine Antwort auf einen Auftrag ist."""
    m = re.search(r"\{.*\}", text or "", re.S)          # auch, wenn die Antwort in einem Code-Block steht
    try:
        obj = json.loads(m.group(0)) if m else None
    except ValueError:
        obj = None
    if not isinstance(obj, dict) or MARK not in obj or not isinstance(obj.get("antworten"), list):
        raise ValueError("Das ist keine Antwort auf einen Auftrag aus „Zu erledigen“")
    by_key = {r["key"]: r for r in rows}
    take, left, seen = [], [], set()
    for a in obj["antworten"]:
        if not isinstance(a, dict):
            continue
        key, wert = str(a.get("key") or "")[:200], str(a.get("wert") or "").strip().lower()
        r = by_key.get(key)
        if not r:
            left.append({"key": key, "warum": "unbekannte Kennung"})
        elif key in seen:
            left.append({"key": key, "warum": "doppelt"})
        elif r.get("entscheidung"):
            left.append({"key": key, "warum": "schon entschieden"})
        elif wert not in WERTE:
            left.append({"key": key, "warum": "unklar" if wert == "unklar" else f"unbekannte Antwort „{wert[:20]}“"})
        else:
            take.append({"key": key, "name": r.get("name", ""), "feld": r.get("feld", ""), "wert": wert,
                         "grund": str(a.get("grund") or "")[:300], "quelle": str(a.get("quelle") or "")[:300]})
        seen.add(key)
    return {"uebernehmen": take, "liegen": left}
