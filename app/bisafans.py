"""Seiten von BisaFans lesen, ohne Netz (den Abruf macht abruf._bisafans):

- Legenden: Arceus, Nebenmissionen (spiele/editionen/legenden-arceus/nebenmissionen.php): alle Aufträge auf einer Seite,
  je Auftrag Nummer, Name, Beschreibung, Aufgabe, Ort („Wo“), Lösung und Belohnung, auf Deutsch.

Der Leser hängt nicht an der HTML-Form: er macht aus der Seite Textzeilen und sucht darin die Überschriften
„Nebenmission N: Name“ und die Beschriftungen der Abschnitte (mit oder ohne Doppelpunkt, in Listen oder Tabellen).
"""
import html
import re

BASE = "https://www.bisafans.de/"
LA_REQUESTS = BASE + "spiele/editionen/legenden-arceus/nebenmissionen.php"
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
            cur = {"nr": int(m.group(1)), "name": m.group(2).strip(), "beschreibung": "", "aufgabe": "", "ort": "",
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
