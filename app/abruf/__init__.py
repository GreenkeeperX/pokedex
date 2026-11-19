"""Abgleich: Daten holen, pokeapi.db neu bauen, Sprites ergänzen. Nach dem Vorbild des VR-Navigators.

Quellen und ihre Rolle:
- PokéAPI (CSV-Dateien im GitHub-Repo): Primärquelle für alle Grunddaten, alle Spiele, deutsche Namen
- Pokémon Showdown (pokedex.ts, moves.ts): Gegenprüfung von Werten, Typen, Attacken; Merkmale wie „Aufladen“
- PokéAPI-Sprites: Bilder, nur fehlende werden geholt
- extra/ im Repo: gepflegte Ergänzungen (JSON), die keine Quelle liefert

Ablauf: Hat sich bei keiner Quelle etwas geändert, wird nichts neu gebaut. Sonst entsteht die neue Datenbank
in einer eigenen Datei und ersetzt die alte erst nach bestandener Selbstprüfung. Scheitert etwas, bleibt die
alte Datenbank. Nach einer Sperre (HTTP 403, 429) oder Prüfseite ruht eine Quelle REST_H Stunden.

Neustart mitten im Lauf (seit 0.58.0): Der Stand (sync.json) geht nach jeder abgeschlossenen Quelle auf die Platte, die
Ruhezeiten (ruhe.json) im Augenblick der Sperre. Ein unterbrochener Lauf trägt „laeuft“ und wird nach dem Start
fortgesetzt, mit seinem Protokoll. Der Zeitplan hat eine feste Uhrzeit (Einstellung „uhr“, UTC).

Seit 0.63.0 ein Paket mit Modulen nach Thema (in der Reihenfolge der Abhängigkeiten von unten nach oben):

- grundlage: Grundlage: Pausen und Ruhezeiten je Server und Quelle, Stand des Laufs (STATE), Einstellungen,
  Zeitplan, Zugriff auf eine Quelle (_Source), Liste der CSV-Dateien, Adressen der Quellen
- medien: Bilder und Platz: Sprites, Artworks, Item-Bilder, Kacheln der Hisui-Karte, Belegung des Datenordners
- quellen: Quellen der Spieldaten außer PokéAPI und Showdown: PKHeX, Spawnpunkte, Altissimo, Begleiter
- wiki: PokéWiki: Attacken und Pokémon in Legenden: Arceus, deutsche Texte
- seiten: Seiten von Serebii, BisaFans und Bulbapedia (Shiny-Sperren, Trainer)
- karten: Karten: Map Genie und die anderen Kartenquellen, Kacheln, Vorrat, hochgeladene Kacheln, Regionskarten
- lauf: Der Lauf: run, die Schritte je Quelle, Bau der Datenbank, Zwischenspeicher der CSV-Texte, Start und Zeitplan
  im Hintergrund
- verbindungstest: Verbindungstest: jede Quelle einmal fragen, Proben für neue Leser

Alle Namen von früher sind weiter unter app.abruf erreichbar (Funktionen, Tabellen, Zwischenspeicher).
Wer für einen Test einen Wert ersetzt, ersetzt ihn mit tests.basis.im_paket hier und in jedem Modul, das ihn
liest; ein Ersatz nur hier wirkte nicht auf die Funktionen des Pakets.
"""
# Die Module, die abruf.py bisher einband, bleiben erreichbar (wie bisher abruf.sources, abruf.db, abruf.store)
from .. import (altissimo, bisafans, companion, db, dittobase, fehler, ign, importer, ironmon, mapgenie, pkcompletion,
    pokearth, pokewiki, raidnester, rankedboost, serebii, shiny, smogon, sources, store)

from .grundlage import (PAUSE, REST_H, NET_RETRY, MAX_ERRORS, BOOT_WAIT_S, LOG_LINES, SPRITES_MAX, SPRITE_MISS_DAYS,
    GH_API, CSV_RAW, SD_RAW, SPRITE_RAW, POKEWIKI_API, EXTRA_DIR, SETTINGS, UHR, RESUME_MAX, REST_FILE, NAMES,
    MG_PAUSE, MG_TILE_PAUSE, MG_STOCK_PAUSE, MISS_FILE, VORRAT_FILE, MISS_DAYS, MG_403_MAX, WIKI_PAUSE, WIKI_GAMES,
    WIKI_TEXT_TAGE, WIKI_TEXT_BATCH, sleep, _HOST_LAST, _HOST_LOCKS, _HOST_GUARD, _host_lock, _parallel, _running,
    STATE, now, _iso, _ago, _rest_lock, _REST, _rests, rest_set, server_rest, rest_until, rest_clear, rests,
    load_settings, save_settings, status, brief, _termin, _start_of, next_run, due, _Source, _short, _resting, _hash,
    csv_list, PKHEX_RAW, PKHEX_ITEMS, PKHEX_SRC, POKEAPI_RAW, PROBE_MAX, pkhex_areas, PLA_MAPS, SPAWN_POINTS,
    SPAWN_SLOTS, PKHEX_GAMES)
from .medien import (IMAGES, EXTRAS, ITEM_HQ, ITEM_HQ_MAX, MEDIA_LABEL, miss_name, serebii_key, media_ids, DISK_LABEL,
    DISK_TILES, DISK_CACHE_S, _disk, _du, disk_usage, media_inventory, file_kind, _images, SEREBII, GAMERGUIDES,
    POKEBIP, MAP_TILES, MAP_ZOOM, map_tiles, _tiles, _sprites)
from .quellen import _pkhex, _spawns, _altissimo, _companion
from .wiki import wiki_titles, _pokewiki, WIKI_TEXT_KINDS, _WIKI_SUFFIX, wiki_text_titles, _wiki_page, _wiki_texts
from .seiten import (SEREBII_PAUSE, _serebii, BISA_PAUSE, _bisafans, SHINY_DAYS, SHINY_PAGE, _shiny, TRAINER_DAYS,
    _trainer)
from .karten import (mg_dir, _mapgenie, _pkcompletion, _save_maps, _ign, _dittobase, _rankedboost, _ironmon,
    _raidnester, tile_convert_state, TILE_UPLOAD_MAX, tile_upload, _pokearth, _region_image, _pw_islands, _pw_island,
    _pw_region, mg_image, MAP_GAMES, MAP_FILES, mg_maps, _mg_cache, _mg_lock, _mg, _tile_rest, _miss_load, _miss_add,
    _miss_save, mg_status, _mg_map, mg_stock, start_stock, _mg_probe, _tile_of, mg_tile, TILE_SRC, _cdn_tile)
from .lauf import (run, _st_lock, _save_lock, _Merker, _run, _media, _smogon, _media_tiles, _media_mg, _media_itemhq,
    _build, TEXT_LABEL, CSV_CACHE, cached_csvs, save_csv_cache, sets_url, _sets, start, scheduler)
from .verbindungstest import DIAG_TIMEOUT, DIAG_LIMIT, DIAG_HANG, DIAG_PARALLEL, DIAG_PAUSE, tile_patterns, diagnose
