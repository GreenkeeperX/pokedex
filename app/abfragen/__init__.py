"""Abfragen für die Oberfläche: Pokémon-Liste mit Filtern, Detailseite, Attacken je Spiel, Typtabelle, Teams.

Was oft gebraucht wird (Typen, Formen, Attacken, Spiele), hält Daten im Speicher und lädt neu, sobald der
Abgleich eine neue pokeapi.db gebaut hat. Lernlisten, Fundorte und Entwicklungen kommen je Anfrage aus der Datenbank.

Seit 0.62.0 ein Paket mit Modulen nach Thema (in der Reihenfolge der Abhängigkeiten von unten nach oben):

- fangen: Fangchance: Bälle, Formeln der Hauptreihe und von Legenden: Arceus, Balltabelle
- basis: Grundlage: Daten im Speicher (Data, data), Spiel und Formen, Profil, Spiele und Metadaten für die
  Oberfläche
- auftraege: Forschung, Aufträge und Missionen
- items: Typtabelle und Items
- liste: Pokémon-Liste: Typwirkung im Vergleich, Kandidaten, Suche mit Filtern
- karten: Fundorte und Karten: Bedingungen, Shiny-Sperren, Alphas, Karten von Map Genie und den anderen Quellen,
  Gebiete
- lernen: Attacken: Texte, Lernlisten, Maschinen, bewährte Sets, Wertung, Reiter Attacken; TMs und Sammelobjekte auf
  den Karten
- raids: Tera-Raids (Karmesin/Purpur) und Crypto-Pokémon
- detailseite: Detailseite: Entwicklungen, mehr Details (Fang, Zucht, EV), Spielwissen, Optik, getragene Items,
  Pokopia
- fortschritt: Fortschritt je Spiel und in HOME, nach Generation und Typ (0.69.0)
- teams: Teams: Plätze, Verbesserungen, Vorschläge, Gefangen, Was fehlt mir noch, Trainer, Gegner; Showdown-Text
  (Import und Export)
- tausch: Tauschliste aus „Was fehlt mir noch“: Suche und Biete, als Text zum Kopieren (0.71.0)
- kampf: Doppelkampf (Smogon), Werte, Effort Levels und Schadensrechner

Alle Namen von früher sind weiter unter app.abfragen erreichbar (Funktionen, Tabellen, Zwischenspeicher).
Wer für einen Test einen Wert ersetzt, ersetzt ihn mit tests.basis.im_paket hier und in jedem Modul, das ihn
liest; ein Ersatz nur hier wirkte nicht auf die Funktionen des Pakets.
"""
# Die Module, die abfragen.py bisher einband, bleiben erreichbar (server.py liest abfragen.team.CRITERIA)
from .. import altissimo, attacken, db, fehler, importer, mapgenie, showdown, spiele, store, team, typen

from .fangen import (BALLS, HISUI_BALLS, HISUI_NO_TABLE, catch_chance_la, rank_la, GROWTH_DE, STAT_KEYS, catch_chance,
    catch_steps, catch_b_gen34, catch_table, MOON_SPECIES, ULTRA_BEASTS, ball_rows, sleep_factor)
from .basis import (LA, WIKI, _lock, _cache, _stamp, _names, Data, data, ladezeit, game_of, profil, profil_von, chart_of,
    form_types, form_stats, no_abilities, old_class, ability_of, member, row, machine_label, HOME, games, meta,
    pruefung)
from .auftraege import (research_done, _research, research_open, _requests, _missions, ZA, _auftragsspiel, _blaubeer,
    QUEST_INFO, quest_kind, QUEST_CATS, _QNR, quest_nr, quest_points, request_list, _wiki_title)
from .items import type_chart, ITEMS_GENAU, item_list
from .liste import SORTS, duel, strong_against, own_marks, candidates, rows_of, search, _int, _ints
from .karten import (_range, ZEIT_DE, WETTER_DE, _pct, _cond_text, _ALPHA, shiny_locks, alpha_possible, spawn_summary,
    map_data, _OVERLAY, mg_overlay, _MERGED, MERGED_MAX, mg_names, names_rx, _pic_names, PIC_VALS, point_pics,
    _point_pics, _quests_de, _pokearth_mons, mg_map, _MERGE_LOCK, _mg_map, _enc_pkhex, _enc, _AREAS, AREAS_MAX,
    METHOD_DE, FIXED_METHODS, _methods, _place, areas, _areas_pkhex, _areas_pokeapi)
from .lernen import (pick_text, text_rows, joined, move_view, learn_game, learnset, how, ROLLEN, _sd_move_map,
    proven_sets, owned_tms, _tm_missing, TM_RX, tm_key, COLLECT_RX, _js_round, point_key, collectibles, tm_places,
    ranked_moves, move_list, moves_of)
from .raids import _raids, raid_list, _crypto
from .fortschritt import vertreter, _gefangen_alle, fortschritt
from .detailseite import (_evolutions, evo_text, _more, _extras, detail, WISSEN, _WISSEN, knowledge, _optik, _held,
    _pokopia)
from .teams import (slot_details, _members, improvements, foreign_moves, team_view, tera_effect, _pool, team_suggest,
    team_optimize, team_caught, NO_EGGS, WAYS, missing, _missing_home, _evolves_from, _between, _stage, _furthest, TRAINER_ROLLEN,
    trainer_list, _move_types, team_matchup, _paste_names, slot_info, paste_import, paste_export)
from .tausch import GRUPPEN, HIER, AUS, _eintrag, _fundorte, _erreichbar, tauschliste, _nr, _text
from .kampf import (smogon_view, team_doubles, effort_view, stats_view, effort_team, damage_matrix, damage_view,
    _calc_steps, _calc_names)
