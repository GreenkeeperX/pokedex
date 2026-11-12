"""Seiten von BisaFans lesen, ohne Netz (den Abruf macht abruf._bisafans):

- Legenden: Arceus, Nebenmissionen (spiele/editionen/legenden-arceus/nebenmissionen.php): alle Aufträge auf einer Seite,
  je Auftrag Nummer, Name, Beschreibung, Aufgabe, Ort („Wo“), Lösung und Belohnung, auf Deutsch.
- Legenden: Arceus, Hauptmissionen aus der Komplettlösung (komplettloesung-1.php bis -9.php): Überschriften
  „Mission N: Name“, darunter der Weg durch die Mission.
- Legenden: Z-A, Nebenmissionen (spiele/editionen/z-a/nebenmissionen.php und die der Mega-Dimension) im selben Aufbau
  wie die von Legenden: Arceus.

Der Leser hängt nicht an der HTML-Form: er macht aus der Seite Textzeilen und sucht darin die Überschriften
„Nebenmission N: Name“ und die Beschriftungen der Abschnitte (mit oder ohne Doppelpunkt, in Listen oder Tabellen).
"""
import html
import re

BASE = "https://www.bisafans.de/"
LA_REQUESTS = BASE + "spiele/editionen/legenden-arceus/nebenmissionen.php"
ZA_REQUESTS = [BASE + "spiele/editionen/z-a/nebenmissionen.php", BASE + "spiele/editionen/z-a/mega-dimension/nebenmissionen-dlc.php"]
LA_STORY = [BASE + f"spiele/editionen/legenden-arceus/komplettloesung-{i}.php" for i in range(1, 10)]
KAPITEL = ("Erste Schritte in einer fremden Welt", "Wächter und Könige in Hisui", "Abenteuer im Sumpfland", "Gemeinsamkeit und Stärke",
           "Der Berg ruft!", "Eisige Abenteuer im Frostland", "Unerwartete Unterstützung", "Legenden im Sinnoh-Tempel",
           "Die Suche nach Arceus")
_MISSION = re.compile(r"^Mission\s+(\d{1,2})\s*[:\-–—.]\s*(.+)$", re.I)
STORY_LINES = 8             # so viele Zeilen der Komplettlösung je Mission (der Anfang des Wegs)
FIELDS = {"beschreibung": "beschreibung", "aufgabe": "aufgabe", "wo": "ort", "ort": "ort", "lösung": "loesung",
          "belohnung": "belohnung", "belohnungen": "belohnung"}
_HEAD = re.compile(r"^(?:Nebenmission|Auftrag|Mission)\s*(?:Nr\.\s*)?(\d{1,3})\s*[:\-–—.]\s*(.+)$", re.I)
_LABEL = re.compile(r"^(" + "|".join(sorted(FIELDS, key=len, reverse=True)) + r")\s*:?\s*(.*)$", re.I)


def lines(page):
    """Sichtbarer Text einer Seite als Zeilen: Block-Elemente, Zellen und <br> trennen; Skripte und Stile fallen weg."""
    s = re.sub(r"<(script|style|noscript)\b.*?</\1>", " ", page or "", flags=re.S | re.I)
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    s = re.sub(r"<\s*(br|/p|p|/div|div|/li|li|/h\d|h\d|/tr|tr|/td|td|/th|th|/dt|dt|/dd|dd|hr)\b[^>]*>", "\n", s, flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return [" ".join(x.split()) for x in s.split("\n") if x.strip()]


def la_requests(page):
    """Aufträge in Legenden: Arceus: [{nr, name, beschreibung, aufgabe, ort, loesung, belohnung}], nach Nummer.
    Eine Nummer zählt einmal (das Inhaltsverzeichnis der Seite nennt dieselben Überschriften ohne Abschnitte)."""
    out, cur, field = {}, None, None
    for ln in lines(page):
        m = _HEAD.match(ln)
        if m:
            name = re.sub(r"(?:\s+(?:PLZA|PLA|MD))+\s*$", "", m.group(2).strip())       # Spielkürzel hinter der Überschrift
            cur = {"nr": int(m.group(1)), "name": name, "beschreibung": "", "aufgabe": "", "ort": "",
                   "loesung": "", "belohnung": ""}
            field = None
            prev = out.get(cur["nr"])
            if prev is None or not any(prev[k] for k in ("aufgabe", "belohnung")):
                out[cur["nr"]] = cur
            else:
                cur = None                  # zweite Nennung derselben Nummer (etwa ein Rücksprung), die erste bleibt
            continue
        if cur is None:
            continue
        m = _LABEL.match(ln)
        if m and (ln.rstrip().endswith(":") or ":" in ln[:len(m.group(1)) + 2] or not m.group(2)):
            field = FIELDS[m.group(1).lower()]
            if m.group(2):
                cur[field] = (cur[field] + " " + m.group(2)).strip()
            continue
        if field == "belohnung" and cur[field] and not re.match(r"^\d+\s*[x×]\s", ln):
            field = None                    # nach der Belohnung beginnt Fremdes (Fußzeile, Werbung, Kommentare)
        if field:
            cur[field] = (cur[field] + " " + ln).strip()
    return [x for _, x in sorted(out.items()) if x["aufgabe"] or x["belohnung"] or x["beschreibung"]]


def la_missions(pages):
    """Hauptmissionen in Legenden: Arceus aus den Seiten der Komplettlösung (in der Reihenfolge der Kapitel):
    [{nr, name, kapitel, text}], nach Nummer. Eine Nummer ohne Text (Inhaltsverzeichnis) weicht der mit Text."""
    out = {}
    for k, page in enumerate(pages, 1):
        cur = None
        for ln in lines(page):
            m = _MISSION.match(ln)
            if m:
                cur = {"nr": int(m.group(1)), "name": m.group(2).strip(), "kapitel": k, "text": []}
                prev = out.get(cur["nr"])
                if prev is None or not prev["text"]:
                    out[cur["nr"]] = cur
                else:
                    cur = None
                continue
            if cur is not None and len(cur["text"]) < STORY_LINES and len(ln) > 2:
                if re.match(r"^(Kapitel|Inhalt|Teil)\b", ln) or ln in KAPITEL:
                    cur = None
                    continue
                cur["text"].append(ln)
    return [dict(x, text="\n".join(x["text"])) for _, x in sorted(out.items())]


requests = la_requests      # derselbe Leser für Legenden: Z-A


def merged_requests(pages):
    """Nebenmissionen aus mehreren Seiten (Hauptspiel, Erweiterung): je Nummer der vollständigste Eintrag."""
    out = {}
    for page in pages:
        for r in la_requests(page):
            prev = out.get(r["nr"])
            if prev is None or sum(bool(r[k]) for k in r) > sum(bool(prev[k]) for k in prev):
                out[r["nr"]] = r
    return [x for _, x in sorted(out.items())]
