"""Statuskarte in den Einstellungen (/api/statuskarte): Gesamtstatus und Einzelheiten in einer kleinen Antwort.

Ohne Netz und ohne den Datenordner zu zählen (das macht /api/speicher erst beim Aufklappen des Speicherplatzes). Der
Gesamtstatus ist die schlechteste Stufe der Gründe: „ok“ (alles in Ordnung), „eingeschraenkt“ (Einschränkungen) oder
„fehler“ (Fehler vorhanden). Welche Lage welche Stufe ergibt, steht in karte() und in docs/abrufe.md („Statuskarte“).
"""
import os
import resource
import shutil
from datetime import datetime, timedelta, timezone

from . import abruf, db, fehler, importer, sources, store

OK, EINGESCHRAENKT, FEHLER = "ok", "eingeschraenkt", "fehler"
_RANG = {OK: 0, EINGESCHRAENKT: 1, FEHLER: 2}
FREI_KNAPP = 2 * 1024 ** 3          # weniger frei auf dem Laufwerk des Datenordners: Einschränkung (Annahme, siehe Doku)
FREI_FEHLER = 500 * 1024 ** 2       # weniger: Fehler (Kacheln und eine neue Datenbank passen dann nicht mehr sicher)
SICHERUNG_ALT = timedelta(days=2)   # die tägliche Sicherung ist älter: Einschränkung
FEHLER_ZEILEN = 10                  # so viele Einträge des Fehlerregisters zeigt die Karte (alle stehen unter Fehler)
WIEDERHERSTELLUNG = "wiederherstellung.json"   # Ergebnis des letzten Wiederherstellungstests (monatlich)


def _iso(t):
    return t.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _datei(pfad):
    """{name, bytes, zeit} einer Datei oder None, wenn es sie nicht gibt."""
    try:
        s = os.stat(pfad)
    except FileNotFoundError:
        return None
    return {"name": os.path.basename(pfad), "bytes": s.st_size, "zeit": _iso(datetime.fromtimestamp(s.st_mtime, timezone.utc))}


def sicherung():
    """Die jüngste tägliche Sicherung von user.db (sicherung/user-JJJJMMTT.db) und wie viele es gibt."""
    ordner = os.path.join(db.data_dir(), "sicherung")
    try:
        namen = sorted(f for f in os.listdir(ordner) if f.startswith("user-") and f.endswith(".db"))
    except FileNotFoundError:
        namen = []
    return {"letzte": _datei(os.path.join(ordner, namen[-1])) if namen else None, "anzahl": len(namen)}


def _ram():
    """Arbeitsspeicher des Dienstes in Bytes: jetzt (VmRSS aus /proc, nur unter Linux) und die Spitze seit dem Start."""
    jetzt = None
    if os.path.exists("/proc/self/status"):
        with open("/proc/self/status", encoding="ascii", errors="replace") as f:
            for zeile in f:
                if zeile.startswith("VmRSS:"):
                    jetzt = int(zeile.split()[1]) * 1024
    spitze = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    return {"jetzt": jetzt, "spitze": max(spitze, jetzt or 0)}


def speicher():
    """Platz auf dem Laufwerk, Größe der beiden Datenbanken, den Datenordner nur, wenn er schon gezählt ist."""
    try:
        platte = shutil.disk_usage(db.data_dir())
        frei, gesamt = platte.free, platte.total
    except OSError as e:
        fehler.melden(e)
        frei = gesamt = None
    gezaehlt = abruf.disk_known()
    return {"frei": frei, "platte": gesamt, "pokeapi_db": (_datei(db.pokeapi_path()) or {}).get("bytes"),
            "user_db": (_datei(db.user_path()) or {}).get("bytes"), "datenordner": gezaehlt["gesamt"] if gezaehlt else None,
            "ram": _ram()}


def karte(at=None):
    """Alles für die Statuskarte. Einzelne Teile, die sich nicht lesen lassen, stehen im Fehlerregister und damit im
    Gesamtstatus; die Karte kommt trotzdem."""
    at = at or datetime.now(timezone.utc)
    st = store.load_json("sync.json", {})
    lauf = abruf.brief()
    hat_daten = db.has_data()
    ruhe = abruf.rests(at)
    quellen = [{"quelle": k, "zeit": r.get("at"), "ok": bool(r.get("ok")), "meldung": r.get("msg") or "",
                "fehler": r.get("errors") or 0} for k, r in sorted((st.get("sources") or {}).items()) if isinstance(r, dict)]
    sich = sicherung()
    platz = speicher()
    liste = fehler.liste()      # zuletzt: was eben beim Lesen scheiterte, steht schon darin
    test = store.load_json(WIEDERHERSTELLUNG, {}) or None     # {}: mit None legte store die Datei als kaputt beiseite
    gebaut_mit = (st.get("stand") or {}).get("importer")

    gruende = []

    def grund(stufe, text):
        gruende.append({"stufe": stufe, "text": text})

    if not hat_daten:
        grund(EINGESCHRAENKT, "Noch keine Spieldaten" + (": der Abgleich läuft." if lauf["running"] else "; der erste Abgleich holt sie."))
    elif gebaut_mit not in (None, importer.VERSION):
        grund(EINGESCHRAENKT, "Die Datenbank stammt aus einer älteren Version; der nächste Abgleich baut sie neu.")
    if lauf["unterbrochen"]:
        grund(EINGESCHRAENKT, "Der letzte Abgleich wurde von einem Neustart unterbrochen und wird fortgesetzt.")
    elif lauf["ok"] is False and not lauf["running"]:
        grund(FEHLER, "Der letzte Abgleich endete mit Fehlern (Protokoll im Kasten Abgleich).")
    schlecht = [q["quelle"] for q in quellen if not q["ok"]]
    if schlecht:
        grund(EINGESCHRAENKT, f"{len(schlecht)} {'Quelle' if len(schlecht) == 1 else 'Quellen'} mit Problem beim letzten Abgleich: "
              + ", ".join(schlecht) + ".")
    if ruhe:
        grund(EINGESCHRAENKT, f"{len(ruhe)} {'Quelle ruht' if len(ruhe) == 1 else 'Quellen ruhen'} nach einer Sperre (403 oder 429).")
    if liste:
        grund(FEHLER, f"{len(liste)} {'Eintrag' if len(liste) == 1 else 'Einträge'} im Fehlerregister.")
    if platz["frei"] is not None and platz["frei"] < FREI_FEHLER:
        grund(FEHLER, "Auf dem Laufwerk des Datenordners ist fast kein Platz mehr frei.")
    elif platz["frei"] is not None and platz["frei"] < FREI_KNAPP:
        grund(EINGESCHRAENKT, "Auf dem Laufwerk des Datenordners wird der Platz knapp.")
    if os.path.isfile(db.user_path()):
        letzte = sich["letzte"]
        if not letzte:
            grund(EINGESCHRAENKT, "Es gibt noch keine Sicherung deiner Daten.")
        elif datetime.fromisoformat(letzte["zeit"]) < at - SICHERUNG_ALT:
            grund(EINGESCHRAENKT, "Die letzte Sicherung deiner Daten ist älter als zwei Tage.")
    if test and test.get("ok") is False:
        grund(FEHLER, "Der letzte Wiederherstellungstest ist gescheitert.")

    gesamt = max((g["stufe"] for g in gruende), key=_RANG.get, default=OK)
    gruende.sort(key=lambda g: -_RANG[g["stufe"]])
    return {
        "gesamt": gesamt,
        "gruende": gruende,
        "abgleich": {"laeuft": lauf["running"], "unterbrochen": lauf["unterbrochen"], "ok": lauf["ok"],
                     "start": lauf["started"], "ende": lauf["finished"], "gebaut": lauf["built"],
                     "naechster": abruf.next_run()},
        "quellen": quellen,
        "ruhe": [{"schluessel": k, "bis": v} for k, v in sorted(ruhe.items(), key=lambda x: x[1])],
        "fehler": {"anzahl": len(liste), "eintraege": [{k: f.get(k) for k in ("zuletzt", "quelle", "art", "anzahl")}
                                                       for f in liste[:FEHLER_ZEILEN]]},
        "speicher": platz,
        "version": {"anwendung": sources.VERSION, "daten": importer.VERSION, "gebaut_mit": gebaut_mit},
        "sicherung": sich,
        "wiederherstellung": test,
    }
