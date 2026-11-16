"""Gerüst der Mini-Datenbank für die Tests: tests/minidb_geruest.json.

Die Mini-Datenbank (tests/minidb.py) besteht aus einer erfundenen Welt (Arten, Attacken, Items, Orte) und einem Gerüst
aus Bezeichnern, an denen die Regeln des Programms hängen: Generationen, Spiele und Editionen, Regional-Dexe, Typen mit
Typtabelle, Statuswerte, Lernwege, Ei-Gruppen, Wesen, Taschen der Items. Dieses Werkzeug schneidet das Gerüst aus den
CSV-Dateien der PokéAPI (https://github.com/PokeAPI/pokeapi, data/v2/csv, BSD-3-Clause, siehe tests/minidb_LIZENZ.txt):
nur die Tabellen unten, nur Deutsch und Englisch, ohne Beschreibungstexte.

Aufruf (selten nötig, etwa wenn ein neues Spiel dazukommt):

    python3 tools/minidb_geruest.py /pfad/zu/den/csv

Das Werkzeug ist keine Abhängigkeit: Tests und Dienst lesen nur die erzeugte Datei bzw. gar nichts davon.
"""
import csv
import json
import os
import sys

SPRACHEN = ("6", "9")           # Deutsch, Englisch
# Tabelle: (Spalten, die bleiben; None = alle, Filter je Zeile)
GANZ = ("generations", "regions", "version_groups", "versions", "version_group_regions", "pokedexes",
        "pokedex_version_groups", "types", "type_efficacy", "type_efficacy_past", "stats", "pokemon_move_methods",
        "item_categories", "natures")
BIS = {"encounter_methods": ("id", 6), "encounter_method_prose": ("encounter_method_id", 6),
       "encounter_condition_value_prose": ("encounter_condition_value_id", 5)}
NAMEN = ("version_names", "pokedex_prose", "type_names", "stat_names", "pokemon_move_method_prose", "encounter_method_prose",
         "encounter_condition_value_prose", "egg_group_prose", "move_damage_class_prose", "evolution_trigger_prose",
         "nature_names")
LEER = ("description", "formula")       # Beschreibungen und Formeltexte braucht kein Test


def lesen(folder, name):
    with open(os.path.join(folder, name + ".csv"), encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], [r for r in rows[1:] if r]


def main(folder, out):
    data = {}
    for name in sorted(set(GANZ) | set(BIS) | set(NAMEN) | {"growth_rates"}):
        head, rows = lesen(folder, name)
        if "local_language_id" in head:
            i = head.index("local_language_id")
            rows = [r for r in rows if r[i] in SPRACHEN]
        if name in BIS:
            col, top = BIS[name]
            i = head.index(col)
            rows = [r for r in rows if int(r[i]) <= top]
        for col in LEER:
            if col in head:
                i = head.index(col)
                rows = [r[:i] + [""] + r[i + 1:] for r in rows]
        data[name] = [head] + rows
    with open(out, "w", encoding="utf-8") as f:
        f.write("{\n" + ",\n".join(f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False, separators=(',', ':'))}"
                                   for k, v in data.items()) + "\n}\n")
    print(len(data), "Tabellen,", sum(len(v) - 1 for v in data.values()), "Zeilen,", os.path.getsize(out), "Byte")


if __name__ == "__main__":
    main(sys.argv[1], os.path.join(os.path.dirname(__file__), "..", "tests", "minidb_geruest.json"))
