/* Pokédex-Oberfläche: reines JavaScript ohne Build. Reiter über die Adresse (#pokemon, #pokemon/6, #team, #attacken,
   #typen, #items, #karte/<Karte>/<Form>, #einstellungen), deshalb öffnet „In neuem Tab öffnen“ jede Karte. Gewähltes Spiel, Filter und das aktuelle
   Team merkt sich der Browser; ein gespeichertes Team ändert sich auf dem Server erst mit „Speichern“. */
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const main = $("#main");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem("px." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("px." + k, JSON.stringify(v)); } catch (e) { /* privates Fenster */ } },
};
const filter0 = (extra = {}) => Object.assign({q: "", typen: {}, modus: "und", art: "typ", klar: false, formen: "relevant", sort: "nr", endstufe: false, ohne_leg: false,
  kampf: false, gen: "", genmodus: "bis", min: "", nur: "", gebiet: ""}, extra);
const S = {
  meta: null, types: {}, chart: null, chartGame: null,
  game: store.get("game", "legends-arceus"),
  team: normTeam(store.get("team", {})), favs: [], favGame: null, caught: new Set(), shiny: new Set(), alpha: new Set(), alphaOk: new Set(), tsort: "",
  weights: store.get("weights", null), preset: store.get("preset", "ausgewogen"),
  filter: filter0(store.get("filter2", {})),
  tfilter: filter0(Object.assign({endstufe: true}, store.get("tfilter", {}))),
  tleg: store.get("tleg", true), dock: store.get("dock", window.innerWidth > 700), foes: store.get("foes", []),
};
const TABS = [["pokemon", "Pokémon"], ["team", "Team"], ["attacken", "Attacken"], ["typen", "Typen"], ["items", "Items"], ["karte", "Karte"], ["einstellungen", "Einstellungen"]];
const STAT = ["KP", "Angriff", "Verteidigung", "Sp.-Angriff", "Sp.-Verteidigung", "Initiative"];
const STAT_K = ["KP", "Ang", "Vert", "SpA", "SpV", "Init"];
const CRIT = {defensive: "Defensive", abdeckung: "Abdeckung", tempo: "Tempo", staerke: "Stärke", balance: "Balance"};
const CRIT_TIP = {defensive: "Wenige offene Schwächen: gegen jeden Angriffstyp sind höchstens so viele Mitglieder schwach wie resistent. 4-fach-Schwächen zählen extra.",
  abdeckung: "Anteil der 18 Typen, die das Team mit seinen Attacken (sonst den Eigentypen) sehr effektiv trifft.",
  tempo: "Mitglieder mit Initiative ab 90, von sechs Plätzen.", staerke: "Summe der Basiswerte, je Mitglied bis 600 gezählt.",
  balance: "Physische und spezielle Angreifer gemischt, keine doppelten Typen."};
const PRESETS = {
  ausgewogen: {defensive: 3, abdeckung: 3, tempo: 1, staerke: 2, balance: 1},
  verteidigung: {defensive: 6, abdeckung: 1, tempo: 1, staerke: 1, balance: 1},
  angriff: {defensive: 1, abdeckung: 6, tempo: 2, staerke: 1, balance: 1},
  staerke: {defensive: 1, abdeckung: 1, tempo: 1, staerke: 6, balance: 0},
  tempo: {defensive: 1, abdeckung: 2, tempo: 6, staerke: 1, balance: 0},
};
const PRESET_DE = {ausgewogen: "Ausgewogen", verteidigung: "Verteidigung", angriff: "Angriff", staerke: "Rohe Stärke", tempo: "Tempo"};
const CLS = {1: "Status", 2: "Physisch", 3: "Speziell"};
const FORMEN_TIP = "Formen mit eigenen Werten: nur Formen, die sich in Typ, Basiswerten oder Fähigkeiten von der Grundform unterscheiden (Hisui-, Alola-, Galar-, Paldea-Formen, Mega, Wulaosu …).\nnur Standardform: eine Karte je Art.\nalle Formen: auch rein optische Formen wie Vivillon-Muster oder Pikachu mit Mütze.";

/* Team: Mitglieder als Liste von Formen (dasselbe Pokémon darf mehrfach hinein), Level und Attacken je Platz in
   details (parallele Liste). Ältere Stände hatten details als {id: ...}. dirty: Änderungen an einem gespeicherten
   Team, die noch nicht gespeichert sind (sie bleiben im Browser, bis du speicherst oder verwirfst). */
function normTeam(t) {
  t = Object.assign({ids: [], fest: [], details: []}, t || {});
  const old = t.details;
  t.details = t.ids.map((id, i) => (Array.isArray(old) ? old[i] : old?.[id]) || {});
  return t;
}
async function api(path, body) {
  const opt = body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  const r = await fetch(path, opt);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== "" && v !== null && v !== undefined && v !== false)).toString();
const weights = () => S.weights || PRESETS[S.preset] || PRESETS.ausgewogen;
const gameName = (k = S.game) => (S.meta?.spiele || []).find((g) => g.kennung === k)?.name || "alle Spiele";

/* ------------------------------------------------------------------ Bausteine */
const tname = (t) => S.types[t] || String(t);
const fl = (f) => ({0: "0", 0.25: "¼", 0.5: "½", 1: "1", 2: "2", 4: "4"}[f] ?? String(f));
const fcls = (f) => f === 0 ? "f0" : f >= 4 ? "f4" : f > 1 ? "f2" : f <= 0.25 ? "f025" : f < 1 ? "f05" : "f1";
const statColor = (v) => `hsl(${Math.min(v, 150) * 0.85} 62% 44%)`;
// Basiswerte-Summe: von Rot (um 200) bis Grün (um 680), wie die Wertungen im VR-Navigator
const sumColor = (v) => `hsl(${Math.max(0, Math.min(1, (v - 200) / 480)) * 125} 70% 38%)`;

/* Marken als SVG (wie „Mein Stand“ im VR-Navigator): gleich kräftig, gleich groß, ändern beim Umschalten nichts am
   Layout. Favorit = Stern, gefangen = Pokéball, im Team = Haken */
const ICON = {fav: '<path d="M8 1.4 9.76 6.17 14.85 6.38 10.85 9.53 12.23 14.42 8 11.6 3.77 14.42 5.15 9.53 1.15 6.38 6.24 6.17Z"/>',
  ball: '<path class="bot" d="M1.9 8a6.1 6.1 0 0 0 12.2 0Z"/><path class="top" d="M1.9 8a6.1 6.1 0 0 1 12.2 0Z"/><circle cx="8" cy="8" r="6.1"/><path d="M1.9 8h12.2"/><circle class="knob" cx="8" cy="8" r="2.1"/>',
  team: '<path d="M3.1 8.5 6.6 11.9 12.9 4.3"/>', plus: '<path d="M8 3v10M3 8h10"/>'};
const icon = (k, on = true) => `<svg class="ic ic-${k}${on ? " on" : ""}" viewBox="0 0 16 16" aria-hidden="true">${ICON[k]}</svg>`;
const SVG = (d) => `<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">${d}</svg>`;
const tchip = (t) => `<span class="t t${t}" data-tip-type="${t}">${esc(tname(t))}</span>`;
const tchips = (ts) => (ts || []).map(tchip).join("");
const img = (id, cls = "", art = false) => `<img class="spr ${cls}" src="${art ? "artwork" : "sprites"}/${id}.png${art ? "?v=2" : ""}" alt="" loading="lazy" draggable="false" onerror="this.onerror=null;this.src='icon.svg';this.classList.add('none')">`;

function defense(types) {
  const ch = S.chart, out = {};
  if (!ch) return out;
  for (const a of Object.keys(ch)) out[a] = types.reduce((f, d) => f * (ch[a][d] ?? 1), 1);
  return out;
}
function pct(i, v) {
  const xs = i === "summe" ? S.meta?.verteilung?.summe : S.meta?.verteilung?.werte?.[i];
  if (!xs || !xs.length) return null;
  let lo = 0, hi = xs.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (xs[m] < v) lo = m + 1; else hi = m; }
  return Math.round((lo / xs.length) * 100);
}
const statTip = (i, v) => { const p = pct(i, v); return `${i === "summe" ? "Summe der Basiswerte" : STAT[i]}: ${v}` + (p === null ? "" : `\nhöher als ${p} % aller Pokémon und Formen`); };

/* Netzdiagramm wie in Legenden: Arceus: KP oben, dann im Uhrzeigersinn Angriff, Verteidigung, Initiative, Sp.-Vert., Sp.-Angriff.
   Maßstab: 100 % (die äußere Ecke) ist je Wert das Maximum aller Pokémon und Formen (ohne Mega und Gigadynamax), etwa
   255 KP bei Heiteira. Ringe bei 25, 50 (betont) und 75 %; an den Ecken der kleinen Ansicht der Wert auf einer
   Skala von 0 bis 10. */
const RADAR_ORDER = [0, 1, 2, 5, 4, 3];
const statMax = (i) => S.meta?.verteilung?.werte?.[i]?.at(-1) || 255;
const scale10 = (i, v) => Math.round(Math.min(1, v / statMax(i)) * 10);
function radar(werte, size = 78, big = false) {
  const pad = big ? 36 : Math.round(size * 0.14), r = size / 2 - pad, c = size / 2;
  const pt = (k, f) => { const a = -Math.PI / 2 + (k * Math.PI) / 3; return [c + Math.cos(a) * r * f, c + Math.sin(a) * r * f]; };
  const xy = (k, f) => pt(k, f).map((x) => x.toFixed(1)).join(",");
  const poly = (f) => RADAR_ORDER.map((_, k) => xy(k, typeof f === "number" ? f : f(k))).join(" ");
  const val = (k) => Math.max(0.04, Math.min(1, werte[RADAR_ORDER[k]] / statMax(RADAR_ORDER[k])));
  let s = `<svg class="radar" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">`;
  s += `<polygon points="${poly(1)}" class="rg"/>`;
  s += [0.25, 0.75].map((f) => `<polygon points="${poly(f)}" class="rg1"/>`).join("") + `<polygon points="${poly(0.5)}" class="rg2"/>`;
  s += RADAR_ORDER.map((_, k) => `<line x1="${c}" y1="${c}" x2="${pt(k, 1)[0].toFixed(1)}" y2="${pt(k, 1)[1].toFixed(1)}" class="rs"/>`).join("");
  s += `<polygon points="${poly(val)}" class="rv"/>`;
  RADAR_ORDER.forEach((i, k) => {
    const [x, y] = pt(k, big ? 1.3 : 1.24);
    s += big ? `<text x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="middle">${STAT_K[i]} <tspan class="v">${werte[i]}</tspan></text>`
      : `<text class="sc" x="${x.toFixed(1)}" y="${(y + 3).toFixed(1)}" text-anchor="middle">${scale10(i, werte[i])}</text>`;
  });
  return s + "</svg>";
}
function radarTipHtml(werte) {
  return `<div class="tt" style="margin-top:0">Netzdiagramm</div><div class="muted">Außen = Höchstwert aller Pokémon, Ringe bei 25, 50 und 75 %</div>
    <table class="rtip"><thead><tr><th></th><th>Wert</th><th></th><th>Skala</th><th>Höchstwert</th></tr></thead><tbody>${[0, 1, 2, 3, 4, 5].map((i) => `<tr><td>${STAT[i]}</td><td class="num"><b>${werte[i]}</b></td>
      <td><span class="sbar"><i style="width:${Math.min(100, werte[i] / statMax(i) * 100)}%;background:${statColor(werte[i])}"></i></span></td>
      <td class="num">${scale10(i, werte[i])}/10</td><td class="num muted">${statMax(i)}</td></tr>`).join("")}</tbody></table>`;
}

const teamFull = () => S.team.ids.length >= 6;
const isFav = (id) => S.favs.some((f) => f.id === id);
/* Champions ist ein reines Kampfspiel: „im Kader“ statt gefangen, kein Schillernd, keine Fangchance, „Kampf“ statt „Karte“ */
const BATTLE = () => S.game === "champions";
const isCaught = (id) => S.caught.has(id);
const isShiny = (id) => S.shiny.has(id);
const isAlpha = (id) => S.alpha.has(id);
/* Alpha: nur in Spielen mit Alphas und nur für Pokémon, die es dort als Alpha gibt (oder schon so markiert sind) */
const alphaBtn = (id) => S.alphaOk.has(id) || isAlpha(id) ? `<span class="a alp${isAlpha(id) ? " on" : ""}" data-act="alpha" data-id="${id}"
  data-tip="${isAlpha(id) ? "Als Alpha gefangen; Klick: kein Alpha" : "Als Alpha gefangen markieren"}">α</span>` : "";
// Pokéball: gefangen, schillernd gefangen (goldener Ball mit Funkeln) oder nichts
const ball = (id, on = isCaught(id)) => icon("ball", on).replace('class="ic ic-ball on"', `class="ic ic-ball on${isShiny(id) ? " shiny" : ""}"`)
;
const ballTip = (id) => BATTLE() ? (isCaught(id) ? "Im Kader; Klick: nicht mehr im Kader" : "In den Kader")
  : isShiny(id) ? `Schillernd in deiner Sammlung (${esc(gameName())}); Klick: doch nicht gefangen`
  : isCaught(id) ? `In deiner Sammlung (${esc(gameName())}); Klick: schillernd` : "Als gefangen markieren";
/* Marken (im Team, gefangen, Favorit) links oben auf der Bildecke, nur die gesetzten: so bleibt dem Namen die ganze
   Zeile. Zum Setzen erscheinen beim Hovern kleine Knöpfe unter dem Bild; nichts verschiebt sich */
function marks(id) {
  const inTeam = S.team.ids.includes(id), fav = isFav(id), got = isCaught(id);
  return `<span class="mk">${inTeam ? `<span class="m m-team" data-tip="Im Team">${icon("team")}</span>` : ""}`
    + `${got ? `<span class="m m-ball" data-tip="${BATTLE() ? "Im Kader" : `${isShiny(id) ? "Schillernd in" : "In"} deiner Sammlung (${esc(gameName())})`}">${ball(id)}</span>` : ""}`
    + `${isAlpha(id) ? `<span class="m m-alpha" data-tip="Als Alpha gefangen">α</span>` : ""}`
    + `${fav ? `<span class="m m-fav" data-tip="Favorit">${icon("fav")}</span>` : ""}</span>`;
}
function acts(id) {
  const inTeam = S.team.ids.includes(id), fav = isFav(id), got = isCaught(id);
  return `<span class="acts">${inTeam ? `<span class="a team on" data-tip="Im Team">${icon("team")}</span>` : `<span class="a team ph"></span>`}`
    + `<span class="a${fav ? " on" : ""}" data-act="fav" data-id="${id}" data-tip="${fav ? "Favorit; Klick: aus den Favoriten" : "Zu den Favoriten (Kader zum schnellen Tauschen)"}">${icon("fav", fav)}</span>`
    + `<span class="a${got ? " on" : ""}" data-act="caught" data-id="${id}" data-tip="${ballTip(id)}">${ball(id, got)}</span>` + alphaBtn(id)
    + `${teamFull() ? `<span class="a ph"></span>` : `<span class="a plus" data-act="teamadd" data-id="${id}" data-tip="${inTeam ? "Noch einmal ins Team" : "Ins Team"}">${icon("plus")}</span>`}</span>`;
}
function monCard(r, xmode = false) {
  const inTeam = S.team.ids.includes(r.id), xs = xmode && XSEL.has(r.id);
  return `<a class="mon${inTeam ? " inteam" : ""}${xs ? " xon" : ""}" href="#pokemon/${r.id}" draggable="true" data-id="${r.id}"><span class="nr">#${r.nr ?? r.art}</span>${xmode
    ? `<span class="xs${xs ? " on" : ""}" data-act="xsel" data-id="${r.id}" data-tip="${xs ? "Ausgewählt zum Übertragen; Klick: abwählen" : "Zum Übertragen auswählen"}">⇄</span>` : ""}<span class="sp">${img(r.id)}${acts(r.id)}</span>
    <span class="mi"><span class="nl"><span class="n">${esc(r.name)}</span></span><span class="ty">${tchips(r.typen)}</span>
    ${r.legendaer ? `<span class="s">legendär</span>` : ""}<span class="s">Basiswerte <b style="color:${sumColor(r.summe)}">${r.summe}</b></span></span>
    ${radar(r.werte, 100)}</a>`;
}
// Marken überall neu zeichnen, ohne die Seite neu aufzubauen
function redrawMarks() {
  $$(".mk").forEach((el) => { const a = el.closest("[data-id]"); if (a) el.outerHTML = marks(+a.dataset.id); });
  $$(".acts").forEach((el) => { const a = el.closest("[data-id]"); if (a) el.outerHTML = acts(+a.dataset.id); });
  $$("[data-markbtn]").forEach((b) => { const id = +b.dataset.id, k = b.dataset.markbtn, on = k === "fav" ? isFav(id) : k === "alpha" ? isAlpha(id) : isCaught(id);
    b.classList.toggle("on", on); b.innerHTML = markLabel(k, on, id); if (k === "gef") b.dataset.tip = ballTip(id); });
  $$(".mon[data-id]").forEach((el) => el.classList.toggle("inteam", S.team.ids.includes(+el.dataset.id)));
}
const markLabel = (k, on, id) => k === "fav" ? `${icon("fav", on)} ${on ? "Favorit" : "Zu den Favoriten"}`
  : k === "alpha" ? `<span class="alpha-i">α</span> ${on ? "Als Alpha gefangen" : "Als Alpha markieren"}`
  : BATTLE() ? `${ball(id, on)} ${on ? "Im Kader" : "In den Kader"}`
  : `${ball(id, on)} ${on ? (isShiny(id) ? "Schillernd in deiner Sammlung" : "In deiner Sammlung") : "Als gefangen markieren"}`;

/* Typ-Duell (wie stark gegen einen Typ): austeilen = bester eigener Typ, einstecken = Attacken des Typs gegen beide
   eigenen Typen. Stufe 2 klar stark (trifft ×2, steckt höchstens ×½ ein), 1 stark (trifft ×2, steckt ×1 ein),
   -1 schwer (steckt ×2 ein, trifft höchstens normal). Dieselbe Rechnung wie duel() in app/abfragen.py */
function duel(own, t) {
  const ch = S.chart || {};
  let dealt = 1, best = null;
  own.forEach((a) => { const f = ch[a]?.[t] ?? 1; if (best === null || f > dealt) { dealt = f; best = a; } });
  const taken = own.reduce((f, d) => f * (ch[t]?.[d] ?? 1), 1);
  const level = dealt > 1 && taken <= 0.5 ? 2 : dealt > 1 && taken <= 1 ? 1 : taken > 1 && dealt <= 1 ? -1 : 0;
  return {dealt, taken, level, best};
}
const DUEL = {2: "klar im Vorteil", 1: "im Vorteil", 0: "ausgeglichen", "-1": "im Nachteil"};
/* Zeilen je Multiplikator: Faktor vorn, dahinter alle Typen (wie in den Typ-Hinweisen) */
const erow = (key, chips) => `<div class="er"><span class="ek">${key}</span><span class="ets">${chips}</span></div>`;
function defRows(d, factors) {
  return factors.map((f) => { const ts = Object.keys(d).filter((t) => d[t] === f);
    return ts.length ? erow(`<span class="f ${fcls(f)}">×${fl(f)}</span>`, ts.map(tchip).join("")) : ""; }).join("");
}
function defHtml(d, short = false) {
  const sec = (title, factors) => { const body = defRows(d, factors); return body ? (short ? `<div class="et">${title}</div>` : `<h3>${title}</h3>`) + body : ""; };
  return sec("Schwach gegen", [4, 2]) + sec("Resistent gegen", [0.5, 0.25]) + sec("Immun gegen (keine Wirkung)", [0])
    || `<p class="hint">Keine Schwäche, keine Resistenz.</p>`;
}
/* Hover-Karte: auf einen Blick, was die eigenen Typen austeilen (bester eigener Typ je Ziel), was sie einstecken
   (beide Typen zusammen) und gegen wen beides passt (trifft ×2 oder mehr und steckt höchstens ×½ ein) */
function glanceHtml(own, d) {
  const ch = S.chart || {}, all = Object.keys(ch);
  const best = (t) => Math.max(...own.map((a) => ch[a]?.[t] ?? 1));
  const acls = (f) => f >= 4 ? "fd4" : f > 1 ? "fd" : f === 0 ? "fa0" : f < 1 ? "fa05" : "f1";
  const rows = (pairs, factors, cls) => factors.map((f) => { const ts = pairs.filter(([, x]) => x === f).map(([t]) => t);
    return ts.length ? erow(`<span class="f ${cls(f)}">×${fl(f)}</span>`, ts.map(tchip).join("")) : ""; }).join("");
  const off = all.map((t) => [t, best(t)]), def = all.map((t) => [t, d[t] ?? 1]);
  const offBody = rows(off, [4, 2, 0.5, 0.25, 0], acls);
  const weak = rows(def, [4, 2], fcls), tough = rows(def, [0.5, 0.25, 0], fcls);
  const ideal = all.filter((t) => best(t) > 1 && (ch[t] ? own.reduce((f, x) => f * (ch[t][x] ?? 1), 1) : 1) <= 0.5);
  const blk = (cls, title, sub, body) => `<div class="hc-blk ${cls}"><h4>${title} <span class="muted">${sub}</span></h4>${body}</div>`;
  return blk("off", "Angriff", "mit Attacken der eigenen Typen", offBody || `<div class="muted">überall normal</div>`)
    + blk("def", "Verteidigung", "wird getroffen", (weak ? `<div class="et">verwundbar</div>${weak}` : "") + (tough ? `<div class="et">hält aus</div>${tough}` : "") || `<div class="muted">überall normal</div>`)
    + (ideal.length ? blk("best", "Gut einzusetzen gegen", "trifft stark, steckt wenig ein", `<div class="ets">${ideal.map(tchip).join("")}</div>`) : "");
}
const DUEL_LEGEND = "↑ teilt aus (bester eigener Typ) · ↓ steckt ein (beide eigenen Typen)";
function duelTip(name, own, t, x) {
  const parts = own.map((d) => `${tname(t)} gegen ${tname(d)} ×${fl(S.chart?.[t]?.[d] ?? 1)}`);
  return `${name} gegen ${tname(t)}: ${DUEL[x.level]}\nAusteilen: ${tname(x.best)} trifft ${tname(t)} ×${fl(x.dealt)}\n`
    + `Einstecken: ${tname(t)}-Attacken treffen ×${fl(x.taken)}${own.length > 1 ? `\n(${parts.join(", ")})` : ""}`;
}
function duelHtml(name, own, short = false) {
  const xs = Object.keys(S.chart || {}).map((t) => [t, duel(own, t)]);
  const dcls = (f) => f >= 4 ? "fd4" : f > 1 ? "fd" : f < 1 ? "f2" : "f1";
  // je Stufe eine Zeile je Paar (austeilen, einstecken), stärkste zuerst
  const rows = (lv) => {
    const groups = {};
    xs.filter(([, x]) => x.level === lv).forEach(([t, x]) => { (groups[`${x.dealt}:${x.taken}`] ||= {x, ts: []}).ts.push([t, x]); });
    return Object.values(groups).sort((a, b) => (b.x.dealt - a.x.dealt) || (a.x.taken - b.x.taken)).map((g) =>
      erow(`<span class="f ${dcls(g.x.dealt)}" data-tip="teilt ×${fl(g.x.dealt)} aus">↑${fl(g.x.dealt)}</span><span class="f ${fcls(g.x.taken)}" data-tip="steckt ×${fl(g.x.taken)} ein">↓${fl(g.x.taken)}</span>`,
        g.ts.map(([t, x]) => `<span class="fx" data-tip="${esc(duelTip(name, own, t, x))}">${tchip(t)}</span>`).join(""))).join("");
  };
  const out = [[2, "Klar im Vorteil gegen", "trifft sehr effektiv und steckt höchstens ½ ein"], [1, "Im Vorteil gegen", "trifft sehr effektiv, steckt normal ein"],
    [-1, "Im Nachteil gegen", "steckt sehr effektiv ein und trifft selbst höchstens normal"]].map(([lv, title, why]) => { const body = rows(lv);
    return body ? (short ? `<div class="et" data-tip="${esc(why)}">${title}</div>` : `<h3 data-tip="${esc(why)}">${title}</h3>`) + body : ""; });
  return out.join("") || (short ? "" : `<p class="hint">Gegen keinen einzelnen Typ klar im Vor- oder Nachteil.</p>`);
}

/* ------------------------------------------------------------------ Hinweise beim Hovern */
const tip = document.createElement("div");
tip.id = "tip";
tip.hidden = true;
document.body.appendChild(tip);
const card = document.createElement("div");
card.id = "hc";
card.hidden = true;
document.body.appendChild(card);
const ROWS = {};          // id → Zeile aus Liste oder Team, für die Hover-Karte
const MOVES = {};         // Attacken-ID → {name, typ, ...}, was die Oberfläche schon kennt

/* Neben das Ziel setzen, nie darüber: Hover-Karten rechts, sonst links, sonst darunter oder darüber; Hinweise (below)
   darunter, sonst darüber, damit sie nichts rechts daneben verdecken */
function place(el, target, below = false) {
  const r = target.getBoundingClientRect(), w = el.offsetWidth, h = el.offsetHeight, m = 8;
  const vw = document.documentElement.clientWidth, vh = window.innerHeight;
  let x, y;
  if (below) {
    x = Math.max(m, Math.min(vw - w - m, r.left + r.width / 2 - w / 2));
    y = r.bottom + 6 + h <= vh ? r.bottom + 6 : r.top - 6 - h;
  } else if (r.right + m + w <= vw) { x = r.right + m; y = r.top; }
  else if (r.left - m - w >= 0) { x = r.left - m - w; y = r.top; }
  else { x = Math.max(m, Math.min(vw - w - m, r.left)); y = r.bottom + m + h <= vh ? r.bottom + m : r.top - m - h; }
  y = Math.max(m, Math.min(vh - h - m, y));
  el.style.left = x + window.scrollX + "px";
  el.style.top = y + window.scrollY + "px";
}
/* Typ-Hinweis mit Bubbles: was der Typ angreifend trifft und was ihn trifft */
function typeTipHtml(t) {
  const ch = S.chart;
  if (!ch || !ch[t]) return esc(tname(t));
  const group = (xs, f) => xs.length ? `<div class="tg"><span class="f ${fcls(f)}">×${fl(f)}</span>${xs.map(tchip).join("")}</div>` : "";
  const out = (f) => Object.keys(ch[t]).filter((d) => ch[t][d] === f);
  const inn = (f) => Object.keys(ch).filter((a) => ch[a][t] === f);
  const sec = (title, parts) => { const body = parts.join(""); return `<div class="tt">${title}</div>` + (body || `<div class="muted">nichts Besonderes</div>`); };
  return `<div class="th">${tchip(t)}</div>`
    + sec(`${esc(tname(t))}-Attacken treffen`, [group(out(2), 2), group(out(0.5), 0.5), group(out(0), 0)])
    + sec(`${esc(tname(t))}-Pokémon werden getroffen von`, [group(inn(2), 2), group(inn(0.5), 0.5), group(inn(0), 0)]);
}
/* Zelle der Typtabelle: Angreifer gegen Verteidiger, dazu Doppeltyp-Beispiele */
function cellTip(a, v) {
  const f = S.chart?.[a]?.[v] ?? 1;
  const word = f === 0 ? "keine Wirkung" : f > 1 ? "sehr effektiv" : f < 1 ? "nicht sehr effektiv" : "normal";
  const back = S.chart?.[v]?.[a] ?? 1;
  return `<div class="tg">${tchip(a)}<span class="arrow">greift an</span>${tchip(v)}</div>
    <div class="tg"><span class="f ${fcls(f)} big">×${fl(f)}</span><b>${word}</b></div>
    <div class="muted">Umgekehrt: ${esc(tname(v))} gegen ${esc(tname(a))} <span class="f ${fcls(back)}">×${fl(back)}</span></div>`;
}
let tipTimer, cardTimer;
document.addEventListener("mouseover", (e) => {
  if (e.pointerType === "touch") return;
  const t = e.target.closest("[data-tip],[data-tip-type],[data-tip-cell],[data-tip-stats]");
  if (t) {
    clearTimeout(tipTimer);
    tipTimer = setTimeout(() => {
      if (t.dataset.tipType) tip.innerHTML = typeTipHtml(t.dataset.tipType);
      else if (t.dataset.tipCell) tip.innerHTML = cellTip(...t.dataset.tipCell.split(":"));
      else if (t.dataset.tipStats) tip.innerHTML = radarTipHtml(t.dataset.tipStats.split(",").map(Number));
      else tip.textContent = t.dataset.tip;
      tip.classList.toggle("rich", !t.dataset.tip);
      tip.hidden = !t.isConnected || !tip.textContent.trim();
      place(tip, t, true);
    }, 220);
  }
  // Hover-Karte: Karten der Liste und alles mit data-hc (Team, Leiste, Verbesserungen, Gegner)
  const c = e.target.closest(".mon,[data-hc]");
  if (c && !t && !document.body.classList.contains("dragging")) {
    clearTimeout(cardTimer);
    cardTimer = setTimeout(() => showCard(c), 280);
  }
});
// Klick vor dem Erscheinen: keine Karte mehr (sonst blieb sie auf der nächsten Seite oben links stehen)
document.addEventListener("pointerdown", () => { clearTimeout(cardTimer); clearTimeout(tipTimer); card.hidden = true; tip.hidden = true; }, true);
document.addEventListener("mouseout", (e) => {
  const t = e.target.closest("[data-tip],[data-tip-type],[data-tip-cell],[data-tip-stats]");
  if (t && !t.contains(e.relatedTarget)) { clearTimeout(tipTimer); tip.hidden = true; }
  const c = e.target.closest(".mon,[data-hc]");
  if (c && !c.contains(e.relatedTarget)) { clearTimeout(cardTimer); card.hidden = true; }
});
document.addEventListener("scroll", () => { tip.hidden = true; card.hidden = true; }, {passive: true});
function showCard(el) {
  if (!el.isConnected || !el.matches(":hover")) return;
  const inTeam = el.closest("#dock,#slots") && el.dataset.slot !== undefined;
  const slot = inTeam ? +el.dataset.slot : null;
  const r = ROWS[el.dataset.hc || el.dataset.id];
  if (!r || !r.werte) return;
  const d = defense(r.typen);
  const det = slot !== null ? S.team.details[slot] || {} : null;
  const mv = det ? (det.attacken || []).map((x) => MOVES[x]).filter(Boolean) : [];
  card.innerHTML = `<div class="hc-head">${img(r.id, "art", true)}<div><b>${esc(r.name)}</b> <span class="muted">#${r.nr ?? r.art}</span><div>${tchips(r.typen)}</div>
      <div class="muted">Basiswerte <b style="color:${sumColor(r.summe)}">${r.summe}</b>${r.legendaer ? " · legendär" : ""}${r.endstufe ? " · Endstufe" : ""}</div>
      ${det ? `<div class="muted">${det.level ? "Level " + det.level : "ohne Level"}</div><div class="hc-mv">${mv.map((m) => `${tchip(m.typ)} ${esc(m.name)}`).join("<br>")}</div>` : ""}</div></div>
    <div class="hc-body">${radar(r.werte, 190, true)}<div class="hc-eff">${glanceHtml(r.typen, d)}</div></div>`;
  card.hidden = false;
  place(card, el);
}

/* ------------------------------------------------------------------ Fadenkreuz in Tabellen
   Zeilen tragen data-r, Zellen data-c; Kopfzellen data-pc (Spalte) oder data-pr (Zeile). Hovern hebt Zeile und Spalte
   hervor, Klick auf einen Kopf hält Zeile oder Spalte fest, Klick auf eine Zelle beides (nochmal: löst). pin = {r, c}
   gehört dem Aufrufer und bleibt über Neuzeichnen erhalten. */
function crossTable(table, pin, onChange) {
  table.classList.add("cross");
  // Sortierbare Spaltenköpfe: der Klick auf den Namen sortiert, das kleine Zeichen daneben hält die Spalte fest
  const hdr = table.tHead?.rows[table.tHead.rows.length - 1];
  if (hdr) [...hdr.cells].forEach((h, i) => {
    if (h.dataset.sort === undefined || h.dataset.pc || !$(`td[data-c="${i}"]`, table)) return;
    h.dataset.c = i;
    h.insertAdjacentHTML("beforeend", `<span class="pinc" data-pc="${i}" data-tip="Spalte markieren">▯</span>`);
  });
  const paint = (hr, hc) => {
    $$(".hl,.fix", table).forEach((x) => x.classList.remove("hl", "fix"));
    const mark = (r, c, cls) => {
      if (r != null) $$(`tr[data-r="${r}"] > *`, table).forEach((x) => x.classList.add(cls));
      if (c != null) $$(`[data-c="${c}"]`, table).forEach((x) => x.classList.add(cls));
    };
    mark(pin.r, pin.c, "fix");
    mark(hr, hc, "hl");
    if (onChange) onChange();
  };
  const cellOf = (e) => e.target.closest("td[data-c],[data-pc],[data-pr]");
  table.addEventListener("mouseover", (e) => {
    const cell = cellOf(e);
    if (!cell) return paint(null, null);
    const row = cell.closest("tr")?.dataset.r ?? null;
    paint(cell.dataset.pc ? null : row, cell.dataset.pr ? null : cell.dataset.c ?? null);
  });
  table.addEventListener("mouseleave", () => paint(null, null));
  table.addEventListener("click", (e) => {
    const cell = cellOf(e);
    if (!cell || e.target.closest("a,button")) return;
    if (cell.classList.contains("pinc")) e.stopPropagation();       // nicht sortieren
    if (cell.dataset.pr) pin.r = pin.r === cell.dataset.pr ? null : cell.dataset.pr;
    else if (cell.dataset.pc) pin.c = pin.c === cell.dataset.pc ? null : cell.dataset.pc;
    else {
      const row = cell.closest("tr").dataset.r, c = cell.dataset.c;
      if (pin.r === row && pin.c === c) { pin.r = null; pin.c = null; } else { pin.r = row; pin.c = c; }
    }
    paint(null, null);
  });
  paint(null, null);
}

/* ------------------------------------------------------------------ Sortierbare Tabellen */
// th[data-sort] sortiert nach den Werten data-s der Zellen (sonst dem Text): erster Klick absteigend, zweiter
// aufsteigend, dritter wieder die ursprüngliche Reihenfolge
document.addEventListener("click", (e) => {
  const th = e.target.closest("table.sort th[data-sort]");
  if (!th) return;
  const table = th.closest("table"), i = [...th.parentNode.children].indexOf(th);
  const tb = table.tBodies[0], rows = [...tb.rows];
  rows.forEach((r, k) => { if (r.dataset.o === undefined) r.dataset.o = k; });
  const key = (tr) => { const c = tr.cells[i]; const v = c?.dataset.s ?? c?.textContent.trim() ?? ""; const n = parseFloat(v); return isNaN(n) || v === "" ? v.toLowerCase() : n; };
  const isNum = rows.some((r) => typeof key(r) === "number");
  const first = isNum ? "desc" : "asc", second = isNum ? "asc" : "desc";
  const dir = !th.dataset.dir ? first : th.dataset.dir === first ? second : "";
  $$("th", table).forEach((x) => delete x.dataset.dir);
  if (dir) th.dataset.dir = dir;
  rows.sort((a, b) => {
    if (!dir) return a.dataset.o - b.dataset.o;
    const x = key(a), y = key(b); const r = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "de");
    return dir === "asc" ? r : -r;
  });
  rows.forEach((r) => tb.appendChild(r));
});
const th = (label, tipText = "", noSort = false, cls = "") => `<th${noSort ? "" : " data-sort"}${cls ? ` class="${cls}"` : ""}${tipText ? ` data-tip="${esc(tipText)}"` : ""}>${label}</th>`;
const thc = (label, tipText = "") => th(label, tipText, false, "c");
// Schadens- und Status-Attacken der Detailseite: dieselben Spalten
const MVCOLS = `<colgroup><col style="width:20%"><col style="width:86px"><col style="width:78px"><col style="width:58px"><col style="width:50px"><col style="width:64px"><col style="width:160px"><col><col style="width:44px"></colgroup>`;
// Statuswörter in Kurztexten farbig (schläfert ein, friert ein, paralysiert …)
const STATUSW = [[/(schläfert ein|schläft|Schlaf\w*)/g, "st-slp"], [/(friert ein|friert|Einfrieren)/g, "st-frz"], [/(paralysiert|Paralyse)/g, "st-par"],
  [/(verbrennt|Verbrennung)/g, "st-brn"], [/(schwer vergiftet|vergiftet|Vergiftung)/g, "st-psn"], [/(verwirrt|Verwirrung)/g, "st-cnf"], [/(zurückschrecken|schreckt zurück)/g, "st-fln"]];
const kurzHtml = (s) => STATUSW.reduce((h, [re, c]) => h.replace(re, `<span class="${c}">$1</span>`), esc(s || ""));
// Art des Fundorts farbig: frei grün, Verzerrung violett, Massenauftreten blau …
const ARTCLS = {"frei": "fa-frei", "Raum-Zeit-Verzerrung": "fa-rzv", "Baum oder Erzbrocken": "fa-baum", "Massenauftreten": "fa-mass", "Massives Massenauftreten": "fa-mmass"};
const artCell = (m) => `<span class="fa ${ARTCLS[m] || "fa-fest"}">${esc(m)}</span>`;
/* Eigene Rückfrage statt confirm() und prompt(): ein kleiner Dialog im Stil der Seite, Enter bestätigt, Esc bricht ab */
function dialogBox(title, text, okLabel, danger, input) {
  return new Promise((resolve) => {
    const dlg = document.createElement("dialog");
    dlg.className = "ask";
    dlg.innerHTML = `<form method="dialog"><h3>${esc(title)}</h3>${text ? `<p>${esc(text)}</p>` : ""}
      ${input ? `<input name="v" type="text" value="${esc(input.value || "")}" aria-label="${esc(input.label)}" placeholder="${esc(input.label)}">` : ""}
      <div class="bar"><span class="grow"></span><button value="no" type="submit">Abbrechen</button><button value="ok" type="submit" class="${danger ? "danger" : "primary"}">${esc(okLabel)}</button></div></form>`;
    document.body.append(dlg);
    const inp = $("input", dlg);
    dlg.addEventListener("close", () => {
      const ok = dlg.returnValue === "ok";
      resolve(input ? (ok && inp.value.trim() ? inp.value.trim() : null) : ok);
      dlg.remove();
    });
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close("no"); });
    dlg.showModal();
    if (inp) { inp.focus(); inp.select(); } else $("button[value=ok]", dlg).focus();
    if (inp) inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); dlg.close("ok"); } });
  });
}
const ask = (title, text, okLabel = "OK", danger = false) => dialogBox(title, text, okLabel, danger, null);
const askText = (title, label, value, okLabel = "OK") => dialogBox(title, "", okLabel, false, {label, value});

/* ------------------------------------------------------------------ Kopf, Reiter, Adresse */
// „vor 3 Tagen“ zu einer ISO-Zeit
function ago(iso) {
  const d = (Date.now() - new Date(iso)) / 60000;
  if (!(d >= 0)) return "";
  if (d < 2) return "gerade eben";
  if (d < 60) return `vor ${Math.round(d)} Minuten`;
  if (d < 60 * 36) return `vor ${Math.round(d / 60)} Stunden`;
  return `vor ${Math.round(d / 1440)} Tagen`;
}
/* Spielauswahl nach Generation gruppiert (neueste oben); die Gruppen machen die lange Liste überschaubar */
function gameOptions(skip = null, all = true) {
  const gs = (S.meta?.spiele || []).filter((g) => g.kennung !== skip), groups = [], home = gs.filter((g) => g.home);
  gs.filter((g) => !g.home).forEach((g) => { if (!groups.length || groups.at(-1)[0] !== g.gen) groups.push([g.gen, []]); groups.at(-1)[1].push(g); });
  return (all ? `<option value="">Alle Spiele (neueste Werte)</option>` : "")
    + (home.length ? `<optgroup label="Sammlung">${home.map((g) => `<option value="${esc(g.kennung)}">${esc(g.name)}</option>`).join("")}</optgroup>` : "")
    + groups.map(([gen, xs]) => `<optgroup label="Generation ${gen}">`
    + xs.map((g) => `<option value="${esc(g.kennung)}">${esc(g.name)}</option>`).join("") + `</optgroup>`).join("");
}
function header() {
  const gs = S.meta?.spiele || [];
  const opts = gameOptions();
  $$("select.gamesel").forEach((sel) => { sel.innerHTML = opts; sel.value = gs.some((g) => g.kennung === S.game) ? S.game : ""; });
  const a = S.meta?.abgleich || {}, last = a.finished || a.started;
  const stale = last && Date.now() - new Date(last) > 2 * (S.meta?.einstellungen?.tage || 7) * 86400000;
  $("#meta").innerHTML = !S.meta?.has_data ? (a.running ? "Erster Abgleich läuft …" : "Noch keine Daten")
    : `${S.meta.formen} Pokémon und Formen · ${S.meta.attacken} Attacken · ${gs.filter((g) => !g.home).length} Spiele`
      + (a.running ? ` · <span>Abgleich läuft${a.step ? ": " + esc(a.step) : ""}</span>`
        : last ? ` · <span class="${stale ? "stale" : ""}" title="${esc(new Date(last).toLocaleString("de-DE"))}">Stand ${esc(ago(last))}</span>` : "");
  version();
  renderTheme();
}
/* Hell, dunkel oder wie das Gerät: runder Knopf mit Menü, wie im VR-Navigator */
const THEMES = [
  ["system", SVG(`<circle cx="8" cy="8" r="6"/><path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor"/>`), "System", "wie dein Gerät"],
  ["light", SVG(`<circle cx="8" cy="8" r="3"/><path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3 3l1 1M12 12l1 1M3 13l1-1M12 4l1-1"/>`), "Hell", ""],
  ["dark", SVG(`<path d="M13.5 10A6 6 0 0 1 6 2.5a6 6 0 1 0 7.5 7.5z"/>`), "Dunkel", ""]];
function themeNow() { const t = document.documentElement.dataset.theme; return t === "light" || t === "dark" ? t : "system"; }
function renderTheme() {
  const cur = THEMES.find((x) => x[0] === themeNow()), b = $("#thmBtn");
  b.innerHTML = cur[1];
  b.title = `Ansicht: ${cur[2]}${cur[3] ? ` (${cur[3]})` : ""}. Klick zum Ändern`;
  b.setAttribute("aria-label", b.title);
  $("#thmMenu").innerHTML = THEMES.map(([k, ic, l, h]) => `<button role="menuitemradio" aria-checked="${k === cur[0]}" class="${k === cur[0] ? "on" : ""}" data-act="thmset" data-v="${k}"><span class="ic">${ic}</span>${l}${h ? ` <span class="hint">${h}</span>` : ""}</button>`).join("");
}
function themeMenu(open) { $("#thmMenu").hidden = !open; $("#thmBtn").setAttribute("aria-expanded", open); }
function setTheme(k) {
  if (k === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = k;
  try { if (k === "system") localStorage.removeItem("px.theme"); else localStorage.setItem("px.theme", k); } catch (x) { /* privates Fenster */ }
  renderTheme(); themeMenu(false);
}
document.addEventListener("click", (e) => { if (!e.target.closest(".thm")) themeMenu(false); });
/* Kopfzeile und Team-Leiste: nach gut 300 px abwärts gleiten beide sanft weg (die Leiste klappt nur auf ihre Kopfzeile
   zu), ein kurzes Stück aufwärts holt sie zurück; wie im VR-Navigator */
(function () {
  let lastY = scrollY, turn = scrollY, dir = 0, hidden = false;
  const set = (hid) => {
    hidden = hid;
    const el = $("#stick");
    el.classList.toggle("hid", hid);
    document.documentElement.style.setProperty("--stick", hid ? "0px" : el.offsetHeight + "px");
    $("#dock")?.classList.toggle("fold", hid);
  };
  addEventListener("scroll", () => {
    const y = scrollY;
    if (Math.abs(y - lastY) < 8 && y > 60) return;
    const d = Math.sign(y - lastY);
    if (d !== dir) { dir = d; turn = lastY; }
    if (dir > 0 && !hidden && y > 300 && y - turn > 300 && $("#thmMenu").hidden && !document.body.classList.contains("dragging")) requestAnimationFrame(() => set(true));
    else if (dir < 0 && hidden && (turn - y > 40 || y < 60)) requestAnimationFrame(() => set(false));
    lastY = y;
  }, {passive: true});
  addEventListener("resize", () => set(hidden));
  set(false);
  window.unfold = () => hidden && set(false);
})();
/* Version in der Kopfzeile; nach einem Update einmal ein Hinweis, was neu ist. Wer das Tool zum
   ersten Mal öffnet, bekommt keinen Hinweis, nur die Version. */
function version() {
  const v = S.meta?.version;
  if (!v) return;
  let seen = null;
  try { seen = localStorage.getItem("px.version"); if (seen === null) localStorage.setItem("px.version", seen = v); } catch (x) { seen = v; }
  const neu = seen !== v;
  const b = $("#ver");
  b.hidden = false; b.textContent = "v" + v; b.classList.toggle("frisch", neu);
  const box = $("#neu");
  if (!neu) { box.innerHTML = ""; return; }
  const cur = (S.meta.neu || []).find((n) => n[0] === v);
  box.innerHTML = `<div class="note neu"><b>Neu in Version ${esc(v)}</b>${cur ? `<ul>${cur[2].map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    <button data-act="neu">Alle Versionen</button> <button class="primary" data-act="neuok">Verstanden</button></div>`;
}
function versionsDialog() {
  let d = $("#vdlg");
  if (!d) {
    d = document.createElement("dialog"); d.id = "vdlg"; document.body.append(d);
    // Klick neben den Dialog (auf den abgedunkelten Rand) schließt ihn
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
  }
  d.innerHTML = `<div class="dh"><h2>Was ist neu?</h2><form method="dialog"><button class="x" aria-label="Schließen" title="Schließen">✕</button></form></div><div class="db">`
    + (S.meta?.neu || []).map(([v, datum, punkte]) =>
      `<h3>Version ${esc(v)} <span class="hint">${esc(datum)}</span></h3><ul>${punkte.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`).join("") + `</div>`;
  d.showModal();
}
function nav(tab) {
  $("#nav").innerHTML = TABS.map(([k, n]) => k === "karte" && BATTLE() ? ["kampf", "Kampf"] : [k, n])
    .map(([k, n]) => `<a href="#${k}" class="${k === tab ? "on" : ""}">${n}</a>`).join("");
}
// Zweiter Klick auf den offenen Reiter: nach oben
document.addEventListener("click", (e) => {
  const a = e.target.closest("#nav a");
  if (a && a.getAttribute("href") === (location.hash || "#pokemon")) { e.preventDefault(); window.scrollTo({top: 0, behavior: "smooth"}); }
});
let RID = 0;                // jede neue Adresse zählt hoch; ältere Antworten schreiben dann nichts mehr
let HERE = "", FROM = "";   // aktuelle und vorige Adresse, für „Zurück“ auf der Detailseite
async function route() {
  RID++;
  clearTimeout(cardTimer); clearTimeout(tipTimer);
  tip.hidden = card.hidden = true;
  if (location.hash !== HERE) { FROM = HERE; HERE = location.hash; }
  const [tab, arg, arg2] = (location.hash.slice(1) || "pokemon").split("/");
  nav(tab);
  const rid = RID;
  if (tab === "karte" && BATTLE()) { location.replace("#kampf"); return; }
  try {
    if (!S.meta?.has_data && tab !== "einstellungen") return noData();
    await Promise.all([loadChart(), loadFavs(), loadCaught()]);
    if (tab === "pokemon" && arg) await detailView(+arg, arg2 === undefined ? null : +arg2);
    else if (tab === "pokemon") await listView();
    else if (tab === "team") await teamView();
    else if (tab === "attacken") await movesView();
    else if (tab === "typen") await chartView();
    else if (tab === "vergleich") await compareView(arg, arg2);
    else if (tab === "initiative") await speedView();
    else if (tab === "kampf") await battleView();
    else if (tab === "items") await itemsView();
    else if (tab === "karte" && arg === "gebiete") await areasView(arg2);
    else if (tab === "karte" && (arg === "mg" || !arg)) await mgView(arg2 && decodeURIComponent(arg2), location.hash.split("/")[3]);
    else if (tab === "karte") await mapView(arg, arg2 === undefined ? null : +arg2);
    else if (tab === "einstellungen") await settingsView();
    else location.hash = "pokemon";
  } catch (e) {
    // eine inzwischen überholte Ansicht schreibt keinen Fehler über die neue
    if (rid === RID) main.innerHTML = `<div class="note stop">Fehler: ${esc(e.message)}</div>`;
    else console.warn(e);
  }
  dock();
}
async function loadFavs(force = false) {
  if (!force && S.favGame === S.game) return;
  S.favs = await api("/api/favoriten?" + qs({spiel: S.game}));
  S.favs.forEach((r) => { ROWS[r.id] = Object.assign(ROWS[r.id] || {}, r); });
  S.favGame = S.game;
}
async function toggleFav(id, on = !isFav(id)) {
  await api("/api/favoriten", {spiel: S.game, id, an: on});
  await loadFavs(true);
  redrawMarks();
  if (location.hash.startsWith("#team")) favBox();
}
async function loadCaught(force = false) {
  if (!force && S.caughtGame === S.game) return;
  const [c, sh, al] = await Promise.all([api("/api/gefangen?" + qs({spiel: S.game})), api("/api/schillernd?" + qs({spiel: S.game})),
    api("/api/alpha?" + qs({spiel: S.game})).catch(() => ({ids: [], moeglich: []}))]);
  S.caught = new Set(c); S.shiny = new Set(sh); S.alpha = new Set(al.ids); S.alphaOk = new Set(al.moeglich);
  S.caughtGame = S.game;
}
// Klick am Pokéball: nicht gefangen → gefangen → schillernd → nicht gefangen
async function toggleCaught(id, plain = false) {
  if (isCaught(id) && !isShiny(id) && !plain && !BATTLE()) {
    await api("/api/schillernd", {spiel: S.game, id, an: true});
    S.shiny.add(id);
  } else {
    const on = !isCaught(id);
    await api("/api/gefangen", {spiel: S.game, id, an: on});
    if (on) S.caught.add(id); else { S.caught.delete(id); S.shiny.delete(id); S.alpha.delete(id); }
  }
  redrawMarks();
  if (location.hash.startsWith("#team")) caughtBox();
}
// α: als Alpha gefangen an und aus (setzt auch gefangen)
async function toggleAlpha(id) {
  const on = !isAlpha(id);
  await api("/api/alpha", {spiel: S.game, id, an: on});
  if (on) { S.alpha.add(id); S.caught.add(id); } else S.alpha.delete(id);
  redrawMarks();
  if (location.hash.startsWith("#team")) caughtBox();
}
async function loadChart() {
  if (S.chart && S.chartGame === S.game) return;
  const d = await api("/api/typen?" + qs({spiel: S.game}));
  S.chart = d.tabelle;
  S.chartGen = d.gen;
  S.chartGame = S.game;
}
function setGame(k) {
  S.game = k;
  store.set("game", k);
  header();
  route();
}
function noData() {
  const a = S.meta?.abgleich || {};
  main.innerHTML = `<div class="box"><h2>Noch keine Spieldaten</h2>
    <p>${a.running ? "Der erste Abgleich läuft gerade (PokéAPI und Showdown, einige Minuten). Die Seite lädt neu, sobald er fertig ist."
      : "Der Abgleich holt die Daten von der PokéAPI und von Pokémon Showdown."}</p>
    <button class="primary" data-act="sync"${a.running ? " disabled" : ""}>Abgleich starten</button>
    <a class="btn" href="#einstellungen">Protokoll ansehen</a></div>`;
  if (a.running) setTimeout(refreshMeta, 5000);
}
async function refreshMeta() {
  S.favGame = null; S.caughtGame = null;
  S.meta = await api("/api/meta");
  S.types = Object.fromEntries((S.meta.typen || []).map((t) => [t.id, t.name]));
  header();
  if (S.meta.has_data || !S.meta.abgleich?.running) route(); else setTimeout(refreshMeta, 5000);
}

/* Farben der Gebiete in Legenden: Arceus (wie auf den Karten), damit gleiche Gebiete in langen Listen auffallen */
const AREA_COLOR = {"Obsidian-Grasland": "#6cc463", "Rotes Sumpfland": "#e07a5f", "Kobalt-Küstenland": "#5aa2f0",
  "Kraterberg-Hochland": "#c99a5b", "Weißes Frostland": "#9fd3ee", "Jubeldorf": "#e8c35a"};
const areaName = (ort) => AREA_COLOR[ort] ? `<span class="area" style="--ac:${AREA_COLOR[ort]}">${wikiLink(ort)}</span>` : wikiLink(ort);
/* Fundorte: aus den Spieldaten (PKHeX) mit Stellen und Alpha, sonst aus der PokéAPI */
function encHtml(d) {
  const f = d.fundorte;
  if (d.fundquelle === "PKHeX") {
    if (!f.length) return `<p class="hint">Kommt in diesem Spiel nicht frei vor (etwa Geschenk, Entwicklung, Tausch oder fester Ort). <a class="wl" href="${esc(d.wiki)}" target="_blank" rel="noopener noreferrer">PokéWiki</a></p>`;
    const one = (p) => (p.name || "im ganzen Gebiet") + (p.level ? ` (${p.level})` : p.alpha ? ` (Alpha ${p.alpha})` : "");
    const places = (xs) => xs.length <= 6 ? esc(xs.map(one).join(", "))
      : `${esc(xs.slice(0, 4).map(one).join(", "))} <span class="weitere" data-tip="${esc(xs.map(one).join(", "))}">und ${xs.length - 4} weitere</span>`;
    // Spalten nur, wo es Daten gibt: Stellen und Alpha nur in den Legenden-Spielen, Tageszeit und Wetter nur mit Spawn-Tabellen
    const has = (k) => f.some((e) => Array.isArray(e[k]) ? e[k].some((x) => x.name) : e[k]);
    const cols = [[th("Gebiet"), (e) => `<td>${areaName(e.ort)}${e.karte ? ` <a class="maplink" href="#karte/${e.karte}/${d.id}" data-tip="Spawnpunkte auf der Karte">Karte</a>` : ""}</td>`],
      has("stellen") && [th("Stellen"), (e) => `<td>${places(e.stellen)}</td>`],
      [th("Art"), (e) => `<td>${artCell(e.methode)}</td>`],
      has("zeit") && [th("Tageszeit"), (e) => `<td>${e.zeit ? `<span data-tip="${esc(`An ${e.punkte} Spawnpunkt${e.punkte === 1 ? "" : "en"}, Anteil bis ${String(e.chance).replace(".", ",")} %`)}">${esc(e.zeit).replace(/, /g, ",<br>")}</span>` : ""}</td>`],
      has("wetter") && [th("Wetter"), (e) => `<td>${esc(e.wetter)}</td>`],
      [th("Level"), (e) => `<td class="nw" data-s="${parseInt(e.level || e.alpha) || 0}">${esc(e.level || "–")}</td>`],
      has("alpha") && [th("Alpha"), (e) => `<td class="nw" data-s="${parseInt(e.alpha) || 0}">${e.alpha ? `<span class="alpha">${esc(e.alpha)}</span>${e.nur_alpha ? " (immer Alpha)" : ""}` : ""}</td>`]].filter(Boolean);
    return `<div class="scroll"><table class="sort"><thead><tr>${cols.map((c) => c[0]).join("")}</tr></thead><tbody>
      ${f.map((e) => `<tr>${cols.map((c) => c[1](e)).join("")}</tr>`).join("")}</tbody></table></div>
      <p class="hint">Aus den Spieldaten (PKHeX)${has("stellen") ? ". Stellen: wo das Pokémon im Gebiet erscheinen kann, mit Level" : ""}${has("alpha") ? "; Alpha-Pokémon sind höher" : ""}${has("zeit")
        ? ". Tageszeit und Wetter: aus den Spawn-Tabellen (PLA-Live-Map), nur für frei auftauchende Pokémon" : ""}.${S.game === "scarlet-violet" || S.game === "the-teal-mask" || S.game === "the-indigo-disk"
        ? " Level: von–bis über alle Stellen des Gebiets; Tera-Raids, Massenauftreten und feste Pokémon auf der Karte fehlen noch." : ""}</p>`;
  }
  if (f.length) return `<div class="scroll"><table class="sort"><thead><tr>${th("Ort")}${th("Methode")}${th("Level")}${th("Bedingungen")}${th("Edition")}</tr></thead><tbody>
    ${f.map((e) => `<tr><td>${wikiLink(e.ort)}</td><td>${esc(e.methode)}</td><td data-s="${parseInt(e.level) || 0}">${esc(e.level)}</td><td>${esc(e.bedingungen.join(", "))}</td><td>${esc(e.editionen.join(", "))}</td></tr>`).join("")}</tbody></table></div>`;
  return `<p class="hint">${S.game ? "Die PokéAPI kennt hier keine Fundorte" + `. Bis dahin: <a class="wl" href="${esc(d.wiki)}" target="_blank" rel="noopener noreferrer">Fundorte im PokéWiki</a>` : "Wähle oben ein Spiel."}</p>`;
}

const gameAreas = () => (S.meta?.spiele || []).find((g) => g.kennung === S.game)?.gebiete || [];
function areaSelect(f) {
  const gb = gameAreas();
  if (!gb.length) return "";
  return `<label data-tip="Nur Pokémon, die in diesem Gebiet frei vorkommen (aus den Spieldaten, ohne Massenauftreten)">Gebiet <select data-f="gebiet"><option value="">alle</option>${gb.map((g) => `<option${f.gebiet === g ? " selected" : ""}>${esc(g)}</option>`).join("")}</select></label>`;
}
/* ------------------------------------------------------------------ Filter (Liste und Team) */
function filterBar(f, id, opts = {}) {
  const bub = Object.entries(S.types).map(([t, n]) => {
    const st = f.typen[t] || 0;
    return `<button class="tb t t${t}${st === 1 ? " in" : st === -1 ? " out" : ""}" data-fb="${id}" data-t="${t}" aria-pressed="${st === 1}">${esc(n)}</button>`;
  }).join("") + `<span class="hint bhint">Klick: gewählt · nochmal: ausgeschlossen (rot) · nochmal: egal</span>`;
  return `<div class="filters" id="${id}">
    <div class="bar">${opts.search === false ? "" : `<input class="grow" data-f="q" type="search" placeholder="Name oder Nummer" value="${esc(f.q)}">`}
      <span class="seg" data-tip="${esc("Gewählte Typen: „Typ ist“ = das Pokémon hat den Typ.\n„stark gegen“ = ein eigener Typ trifft ihn sehr effektiv, und seine Attacken treffen das Pokémon höchstens normal (beide eigenen Typen zusammengerechnet). Mit „klar“ nur, wenn sie höchstens ½ treffen.")}">
        <button data-fa="typ" class="${f.art !== "gegen" ? "on" : ""}">Typ ist</button><button data-fa="gegen" class="${f.art === "gegen" ? "on" : ""}">stark gegen</button></span>
      <label class="klar" data-tip="Nur klar stark: trifft sehr effektiv und steckt höchstens ½ ein"${f.art === "gegen" ? "" : " hidden"}><input type="checkbox" data-f="klar"${f.klar ? " checked" : ""}> klar</label>
      <span class="seg" data-tip="Mehrere gewählte Typen: „und“ = alle zugleich, „oder“ = einer davon reicht">
        <button data-fm="und" class="${f.modus === "und" ? "on" : ""}">und</button><button data-fm="oder" class="${f.modus === "oder" ? "on" : ""}">oder</button></span>
      <select data-f="formen" data-tip="${esc(FORMEN_TIP)}"><option value="relevant">Formen mit eigenen Werten</option><option value="standard">nur Standardform</option><option value="alle">alle Formen</option></select>
      ${opts.sort === false ? "" : `<select data-f="sort"><option value="nr">Nummer</option><option value="name">Name</option><option value="summe">Basiswerte</option>
        <option value="ang">Angriff</option><option value="spang">Sp.-Angriff</option><option value="init">Initiative</option><option value="kp">KP</option><option value="vert">Verteidigung</option></select>`}
      <button data-act="freset" data-fid="${id}">Zurücksetzen</button></div>
    <div class="bubbles">${bub}</div>
    <div class="bar">
      <label><input type="checkbox" data-f="endstufe"${f.endstufe ? " checked" : ""}> nur Endstufen</label>
      <label><input type="checkbox" data-f="ohne_leg"${f.ohne_leg ? " checked" : ""}> ohne Legendäre</label>
      <label data-tip="Mega-Entwicklungen und Gigadynamax-Formen gibt es nur im Kampf"><input type="checkbox" data-f="kampf"${f.kampf ? " checked" : ""}> mit Mega und Gigadynamax</label>
      <label data-tip="„bis“: Pokémon bis zu dieser Generation; „nur“: nur Pokémon, die in dieser Generation neu kamen"><select data-f="genmodus"><option value="bis">bis</option><option value="nur"${f.genmodus === "nur" ? " selected" : ""}>nur</option></select>
        Gen <select data-f="gen"><option value="">alle</option>${[1, 2, 3, 4, 5, 6, 7, 8, 9].map((g) => `<option${+f.gen === g ? " selected" : ""}>${g}</option>`).join("")}</select></label>
      <label data-tip="Nur deine Favoriten (Stern) oder deine Sammlung (als gefangen markiert, Pokéball) im gewählten Spiel"><select data-f="nur"><option value="">alle Pokémon</option><option value="fav"${f.nur === "fav" ? " selected" : ""}>nur Favoriten</option><option value="gef"${f.nur === "gef" ? " selected" : ""}>nur aus deiner Sammlung</option></select></label>
      ${areaSelect(f)}
      <label>Basiswerte ab <input data-f="min" type="number" min="0" max="800" step="10" style="width:80px" value="${esc(f.min)}"></label>
      <span class="hint grow" data-cnt="${id}"></span></div></div>`;
}
function bindFilter(f, id, onChange, save) {
  const box = $("#" + id);
  $('[data-f="formen"]', box).value = f.formen;
  if ($('[data-f="sort"]', box)) $('[data-f="sort"]', box).value = f.sort;
  let timer;
  const changed = () => { save(); clearTimeout(timer); timer = setTimeout(onChange, 180); };
  $$("[data-f]", box).forEach((el) => el.addEventListener(el.type === "search" || el.type === "number" ? "input" : "change", () => {
    f[el.dataset.f] = el.type === "checkbox" ? el.checked : el.value;
    changed();
  }));
  $$("[data-fa]", box).forEach((b) => b.addEventListener("click", () => {
    f.art = b.dataset.fa;
    $$("[data-fa]", box).forEach((x) => x.classList.toggle("on", x === b));
    $(".klar", box).hidden = f.art !== "gegen";
    changed();
  }));
  $$("[data-fm]", box).forEach((b) => b.addEventListener("click", () => {
    f.modus = b.dataset.fm;
    $$("[data-fm]", box).forEach((x) => x.classList.toggle("on", x === b));
    changed();
  }));
  $$("[data-fb]", box).forEach((b) => b.addEventListener("click", () => {
    const t = b.dataset.t, st = f.typen[t] || 0, next = st === 0 ? 1 : st === 1 ? -1 : 0;
    if (next) f.typen[t] = next; else delete f.typen[t];
    b.classList.toggle("in", next === 1);
    b.classList.toggle("out", next === -1);
    changed();
  }));
}
const filterQuery = (f) => ({q: f.q, formen: f.formen, sort: f.sort, endstufe: f.endstufe ? 1 : "", ohne_leg: f.ohne_leg ? 1 : "", kampf: f.kampf ? 1 : "",
  gen: f.gen, genmodus: f.gen && f.genmodus === "nur" ? "nur" : "", min: f.min, modus: f.modus, nur: f.nur || "", gebiet: f.gebiet && gameAreas().includes(f.gebiet) ? f.gebiet : "", klar: f.art === "gegen" && f.klar ? 1 : "",
  [f.art === "gegen" ? "gegen" : "typen"]: Object.keys(f.typen).filter((t) => f.typen[t] === 1).join(","),
  ohne: Object.keys(f.typen).filter((t) => f.typen[t] === -1).join(",")});

/* ------------------------------------------------------------------ Pokémon-Liste */
let LS = {offset: 0, n: 0, busy: false, key: "", y: 0};
function pageSize() {
  const grid = $("#list");
  const w = grid ? grid.clientWidth : main.clientWidth;
  const cols = Math.max(1, Math.floor((w + 8) / (270 + 8)));
  return cols * Math.ceil(100 / cols);      // füllt die letzte Reihe
}
/* Sammlung übertragen: bei „nur aus deiner Sammlung“ lassen sich Karten mit ⇄ wählen und in ein anderes Spiel
   oder nach Pokémon HOME übertragen (danach dort gefangen; im bisherigen Spiel nur auf Wunsch behalten) */
const XSEL = new Set();
const xmode = () => S.filter.nur === "gef";
function xferBar() {
  const box = $("#xfer");
  if (!box) return;
  $("#list")?.classList.toggle("xmode", xmode());
  if (!xmode()) { box.innerHTML = ""; XSEL.clear(); return; }
  const to = store.get("xferTo", "pokemon-home");
  box.innerHTML = `<div class="xfer"><b>Sammlung übertragen</b><span class="hint">mit ⇄ an den Karten</span>
    <button class="small" data-act="xall">Alle angezeigten</button><button class="small" data-act="xnone"${XSEL.size ? "" : " disabled"}>Keine</button>
    <label>nach <select id="xto">${gameOptions(S.game, false)}<optgroup label="Aufräumen"><option value="freilassen">Freilassen (aus der Sammlung nehmen)</option></optgroup></select></label>
    <label data-tip="Sonst verschwinden sie hier aus der Sammlung, wie beim Übertragen im Spiel"><input type="checkbox" id="xkeep"${store.get("xferKeep", false) ? " checked" : ""}> hier behalten</label>
    <button class="primary" data-act="xgo"${XSEL.size ? "" : " disabled"}>${XSEL.size} übertragen</button></div>`;
  $("#xto").value = [...$("#xto").options].some((o) => o.value === to) ? to : $("#xto").options[0]?.value || "";
  $("#xto").addEventListener("change", (e) => { store.set("xferTo", e.target.value); $("#xkeep").closest("label").hidden = e.target.value === "freilassen"; });
  $("#xkeep").closest("label").hidden = $("#xto").value === "freilassen";
  $("#xkeep").addEventListener("change", (e) => store.set("xferKeep", e.target.checked));
}
function xsel(id, on = !XSEL.has(id)) {
  if (on) XSEL.add(id); else XSEL.delete(id);
  $$(`.mon[data-id="${id}"]`).forEach((el) => { el.classList.toggle("xon", on); $(".xs", el)?.classList.toggle("on", on); });
  xferBar();
}
async function xferGo() {
  const to = $("#xto").value, keep = $("#xkeep").checked, n = XSEL.size;
  if (!n || !to) return;
  if (to === "freilassen") {
    if (!await ask(`${n} Pokémon freilassen?`, `Sie verschwinden aus deiner Sammlung in ${gameName()}.`, "Freilassen", true)) return;
  } else if (!await ask(`${n} Pokémon nach ${gameName(to)} übertragen?`, keep ? `Sie bleiben auch in ${gameName()} in deiner Sammlung.`
    : `Sie gelten danach in ${gameName(to)} als gefangen und verschwinden aus deiner Sammlung in ${gameName()}.`, "Übertragen")) return;
  await api("/api/uebertragen", {von: S.game, nach: to, ids: [...XSEL], behalten: keep});
  XSEL.clear();
  S.caughtGame = null;
  await loadCaught();
  xferBar();
  await loadList(true);
}
async function listView() {
  main.innerHTML = filterBar(S.filter, "lf") + `<div id="xfer"></div><div class="list${xmode() ? " xmode" : ""}" id="list"></div><div class="more" id="more"></div>`;
  bindFilter(S.filter, "lf", () => { xferBar(); loadList(true); }, () => store.set("filter2", S.filter));
  xferBar();
  const key = JSON.stringify([S.filter, S.game]);
  const back = LS.key === key && LS.offset;
  await loadList(true, back ? LS.offset : 0);
  if (back) window.scrollTo(0, LS.y);
  const io = new IntersectionObserver((es) => { if (es[0].isIntersecting) loadList(false); }, {rootMargin: "600px"});
  io.observe($("#more"));
}
window.addEventListener("scroll", () => { if (location.hash.split("/")[0] === "#pokemon" && !location.hash.includes("/")) LS.y = window.scrollY; }, {passive: true});
async function loadList(reset, want = 0) {
  if (!$("#list") || (LS.busy && !reset)) return;
  if (!reset && LS.offset >= LS.n) return;
  const rid = RID;
  LS.busy = true;
  if (reset) LS = {offset: 0, n: 0, busy: true, key: JSON.stringify([S.filter, S.game]), y: LS.y};
  const limit = Math.max(want, pageSize());
  try {
    const d = await api("/api/pokemon?" + qs({...filterQuery(S.filter), spiel: S.game, limit, offset: LS.offset}));
    if (rid !== RID || !$("#list")) return;
    d.rows.forEach((r) => { ROWS[r.id] = r; });
    const html = d.rows.map((r) => monCard(r, xmode())).join("");
    if (reset) $("#list").innerHTML = html || `<p class="hint">Nichts gefunden.</p>`;
    else $("#list").insertAdjacentHTML("beforeend", html);
    LS.n = d.n;
    LS.offset += d.rows.length;
    $('[data-cnt="lf"]').textContent = `${d.n} Treffer in ${gameName()}`;
    $("#more").innerHTML = LS.offset < d.n ? `<span class="hint">Lädt weitere …</span>` : d.n ? `<span class="hint">Alle ${d.n} angezeigt.</span>` : "";
  } finally { LS.busy = false; }
}

/* ------------------------------------------------------------------ Team-Leiste unten (in jedem Reiter) */
/* Das aktuelle Team liegt immer im Browser. Ein gespeichertes Team ändert sich auf dem Server erst mit „Speichern“;
   bis dahin zeigt die Oberfläche „nicht gespeichert“ und bietet „Verwerfen“ an. */
function saveTeam() {
  if (S.team.tid) S.team.dirty = true;
  store.set("team", S.team);
}
async function saveToServer(name = S.team.name, asNew = false) {
  const t = S.team;
  const r = await api("/api/teams", {id: asNew ? null : t.tid, name, spiel: t.spiel || S.game, mitglieder: t.ids, fest: t.fest,
    gewichte: weights(), details: t.details});
  Object.assign(t, {tid: r.id, name, spiel: t.spiel || S.game, dirty: false});
  store.set("team", t);
}
/* Showdown-Text: Export des aktuellen Teams, Import ersetzt das Team (Level, Attacken, Item, Fähigkeit, Wesen, EVs) */
async function sdExport() {
  const r = await api("/api/team/export", {spiel: S.game, ids: S.team.ids, details: S.team.details});
  if (!$("#sdtext")) return;
  $("#sdtext").value = r.text;
  $("#sdnote").textContent = S.team.ids.length ? "Englische Namen, wie in Showdown." : "Das Team ist leer: Text einfügen und übernehmen.";
}
async function sdImport() {
  const text = $("#sdtext").value;
  if (!text.trim()) return;
  const r = await api("/api/team/import", {spiel: S.game, text});
  if (!r.ids.length) { $("#sdnote").textContent = r.hinweise.join(" · ") || "Kein Pokémon erkannt."; return; }
  if (S.team.ids.length && !await ask("Team ersetzen?", `${r.ids.length} Pokémon aus dem Text ersetzen das aktuelle Team.`, "Ersetzen")) return;
  S.team.ids = r.ids;
  S.team.details = r.details;
  S.team.fest = [];
  teamChanged();
  $("#sdnote").textContent = r.hinweise.length ? "Übernommen; nicht erkannt: " + r.hinweise.join(" · ") : `${r.ids.length} Pokémon übernommen.`;
}
const STATK = ["KP", "Ang", "Vert", "SpAng", "SpVert", "Init"];
function slotExtra(x) {
  if (!x || !Object.keys(x).length) return "";
  const mod = x.wesen_mod ? ` (+${STATK[x.wesen_mod[0]]} −${STATK[x.wesen_mod[1]]})` : "";
  const parts = [x.item && `@ ${esc(x.item)}`, x.faehigkeit && esc(x.faehigkeit), x.wesen && esc(x.wesen + mod)].filter(Boolean);
  return `<div class="hint slotx">${parts.join(" · ")}${x.tera ? ` · Tera ${tchip(x.tera)}` : ""}</div>`;
}
function teamChanged() {
  saveTeam();
  dock();
  const h = location.hash;
  if (h.startsWith("#team")) teamRefresh();
  else redrawMarks();
}
/* Neue Mitglieder bekommen die Attacken, die sie im Spiel bis zu ihrem Level kennen (ohne Level: die ersten vier).
   Auch Mitglieder ohne Attacken (ältere Teams) bekommen sie, einmal je Platz, Pokémon und Spiel */
const STD_TRIED = new Set();
async function fillStandard(slot) {
  const t = S.team, id = t.ids[slot];
  if (!id || (t.details[slot]?.attacken || []).length) return;
  const key = `${S.game}|${slot}|${id}|${t.details[slot]?.level || ""}`;
  if (STD_TRIED.has(key)) return;
  STD_TRIED.add(key);
  try {
    const A = await api(`/api/pokemon/${id}/attacken?` + qs({spiel: S.game, level: t.details[slot]?.level || ""}));
    [...A.attacken, ...A.status].forEach((m) => { MOVES[m.id] = m; });
    if (t.ids[slot] !== id || (t.details[slot]?.attacken || []).length || !A.standard?.length) return;
    t.details[slot] = Object.assign({}, t.details[slot], {attacken: A.standard});
    teamChanged();
  } catch (e) { console.warn(e); }
}
// at: Platz, auf den das Pokémon soll; ein belegter Platz wird ersetzt, sonst kommt es ans Ende
function addToTeam(id, at = null) {
  id = +id;
  const t = S.team;
  let slot;
  if (at !== null && at < t.ids.length) {
    const old = t.ids[at];
    t.ids[at] = id; t.details[at] = {}; slot = at;
    if (!t.ids.includes(old)) t.fest = t.fest.filter((x) => x !== old);
  } else {
    if (t.ids.length >= 6) { fullChoice(id); return null; }
    t.ids.push(id); t.details.push({}); slot = t.ids.length - 1;
  }
  teamChanged();
  fillStandard(slot);
  return slot;
}
/* Team voll: statt einer Fehlermeldung die Wahl, welchen Platz das Pokémon ersetzt, oder ab in die Favoriten */
function fullChoice(id, anchor = document.activeElement?.closest?.(".ac,.bar,.box") || $("#dock")) {
  let el = $("#pick");
  if (!el) { el = document.createElement("div"); el.id = "pick"; document.body.appendChild(el); }
  const r = ROWS[id];
  el.innerHTML = `<div class="hint">Team voll. ${esc(r?.name || "")} ersetzt …</div>`
    + S.team.ids.map((x, i) => `<button data-act="pickfav" data-id="${id}" data-slot="${i}" data-hc="${x}">${img(x)}<span>Platz ${i + 1}: ${esc(ROWS[x]?.name || "#" + x)}</span></button>`).join("")
    + (isFav(id) ? "" : `<button data-act="favadd" data-id="${id}">${icon("fav", false)}<span>Lieber zu den Favoriten</span></button>`);
  el.hidden = false;
  place(el, anchor && anchor.isConnected ? anchor : $("#dock"), true);
}
function removeSlot(slot) {
  const t = S.team, id = t.ids[slot];
  t.ids.splice(slot, 1);
  t.details.splice(slot, 1);
  if (!t.ids.includes(id)) t.fest = t.fest.filter((x) => x !== id);
  teamChanged();
}
function moveSlot(a, b) {
  const t = S.team;
  b = Math.max(0, Math.min(b, t.ids.length - 1));
  if (a === b) return;
  const [id] = t.ids.splice(a, 1), [d] = t.details.splice(a, 1);
  t.ids.splice(b, 0, id); t.details.splice(b, 0, d);
  S.tsort = "";
  if ($("#tsort")) $("#tsort").value = "";
  teamChanged();
}
const slotOf = (id) => S.team.ids.indexOf(id);
// Passt das Team zum gewählten Spiel? Fragt den Server knapp (ohne Verbesserungen) und merkt sich die Antwort
let CHECK = {key: "", nicht: [], fremd: {}};
function teamCheck() {
  const key = S.game + "|" + S.team.ids.join(",") + "|" + JSON.stringify(S.team.details.map((d) => d.attacken || []));
  if (CHECK.key === key || teamCheck.busy) return;
  teamCheck.busy = true;
  api("/api/team/bewerten", {spiel: S.game, ids: S.team.ids, details: S.team.details, kurz: 1}).then((ev) => {
    (ev.mitglieder || []).forEach((m) => { ROWS[m.id] = Object.assign(ROWS[m.id] || {}, m); });
    Object.entries(ev.attacken || {}).forEach(([k, m]) => { MOVES[k] = Object.assign(MOVES[k] || {}, m, {id: +k}); });
    CHECK = {key, nicht: ev.nicht_im_spiel || [], fremd: ev.fremde_attacken || {}};
    teamCheck.busy = false;
    dock();
    if (location.hash.startsWith("#team") && $("#tnote")) teamNote();
  }).catch(() => { teamCheck.busy = false; });
}
function mismatch() {
  const t = S.team, out = [];
  if (t.spiel && t.spiel !== S.game) out.push(`Dieses Team gehört zu ${gameName(t.spiel)}, oben ist ${gameName()} gewählt.`);
  const n = CHECK.nicht.filter((i) => i < t.ids.length);
  if (n.length && S.game) out.push(`Nicht in ${gameName()}: ${n.map((i) => ROWS[t.ids[i]]?.name || "#" + t.ids[i]).join(", ")}.`);
  const fm = Object.entries(CHECK.fremd || {}).filter(([i]) => +i < t.ids.length);
  if (fm.length && S.game) out.push(`Attacken, die es so in ${gameName()} nicht gibt: ${fm.map(([i, xs]) => `${xs.map((x) => MOVES[x]?.name || "#" + x).join(", ")} (${ROWS[t.ids[+i]]?.name || "#" + t.ids[+i]})`).join("; ")}.`);
  return out;
  return out;
}
function dock() {
  let el = $("#dock");
  if (!el) { el = document.createElement("div"); el.id = "dock"; document.body.appendChild(el); }
  const t = S.team;
  teamCheck();
  const bad = new Set(CHECK.nicht);
  const slots = [0, 1, 2, 3, 4, 5].map((i) => {
    const id = t.ids[i];
    if (!id) return `<div class="dslot empty" data-slot="${i}" data-act="pick" data-tip="Hierher ziehen, oder klicken für deine Favoriten">${i === t.ids.length ? `hierher ziehen · ${icon("fav", false)}` : icon("fav", false)}</div>`;
    const r = ROWS[id];
    const lv = t.details[i]?.level;
    return `<div class="dslot${bad.has(i) ? " warn" : ""}" data-slot="${i}" draggable="true" data-id="${id}" data-hc="${id}"><a href="#pokemon/${id}/${i}" draggable="false">${img(id)}</a>
      <span class="dn">${esc(r?.name || "#" + id)}${lv ? ` <span class="muted">Lv ${lv}</span>` : ""}${bad.has(i) ? ` <span class="wbadge" data-tip="Nicht in ${esc(gameName())}">!</span>` : ""}</span>
      <button class="x" data-act="teamdel" data-slot="${i}" data-tip="Aus dem Team">✕</button></div>`;
  }).join("");
  const warn = mismatch();
  // Plätze sind immer da und klappen nur weg (sanft, auch beim Scrollen); zugeklappt zeigt die Kopfzeile kleine Bilder
  el.classList.toggle("open", S.dock);
  el.innerHTML = `<div class="dhead"><button data-act="dock" class="link"><span class="chev">▾</span> Team${t.name ? ": " + esc(t.name) : ""}</button>
    <span class="hint">${t.ids.length}/6 · ${esc(gameName(t.spiel || S.game))}</span>
    ${t.tid && t.dirty ? `<span class="dirty" data-tip="Die Änderungen liegen im Browser. Erst „Speichern“ ändert das gespeicherte Team.">nicht gespeichert</span>
      <button class="small primary" data-act="tsave">Speichern</button><button class="small" data-act="tundo">Verwerfen</button>` : ""}
    ${warn.length ? `<span class="wtext" data-tip="${esc(warn.join("\n"))}">⚠ passt nicht ganz zum Spiel</span>` : ""}
    <span class="dmini">${t.ids.map((id) => img(id)).join("")}</span>
    <a class="btn small" href="#team">Team ansehen</a></div><div class="dslots"><div class="dgrid">${slots}</div></div>`;
  document.body.classList.toggle("dock-open", S.dock);
}
// Auswahl aus den Favoriten für einen Platz (leer: hinzufügen, belegt: tauschen)
function picker(anchor, slot) {
  let el = $("#pick");
  if (!el) { el = document.createElement("div"); el.id = "pick"; document.body.appendChild(el); }
  el.innerHTML = `<div class="hint">Favoriten in ${esc(gameName())}${slot < S.team.ids.length ? ` · ersetzt ${esc(ROWS[S.team.ids[slot]]?.name || "")}` : ""}</div>`
    + (S.favs.length ? S.favs.map((r) => `<button data-act="pickfav" data-id="${r.id}" data-slot="${slot}" data-hc="${r.id}">${img(r.id)}<span>${esc(r.name)}</span>${tchips(r.typen)}</button>`).join("")
      : `<p class="hint">Noch keine Favoriten. Markiere Pokémon mit ☆ auf ihrer Karte oder der Detailseite.</p>`);
  el.hidden = false;
  place(el, anchor);
}
document.addEventListener("click", (e) => { const p = $("#pick"); if (p && !p.hidden && !p.contains(e.target) && !e.target.closest('[data-act="pick"],.ac .menu')) p.hidden = true; });
/* Ziehen und Ablegen: Karten (auch aus der Suche) in die Leiste oder auf einen Platz (ersetzt ihn), Plätze
   untereinander verschieben, Pokémon auf die Favoriten oder Gefangenen ziehen (markiert sie) */
document.addEventListener("dragstart", (e) => {
  const c = e.target.closest(".mon,.dslot[data-id],.tslot[data-id],.sugg,.mvchip,.ac .menu button[data-id],.imp[data-id]");
  if (!c) return;
  if (c.classList.contains("mvchip")) { e.dataTransfer.setData("text/x-move", c.dataset.i); e.dataTransfer.effectAllowed = "move"; return; }
  e.dataTransfer.setData("text/x-pokemon", c.dataset.id);
  if (c.dataset.slot !== undefined) e.dataTransfer.setData("text/x-slot", c.dataset.slot);
  e.dataTransfer.effectAllowed = "move";
  card.hidden = true;
  if (!S.dock && !c.classList.contains("tslot")) { S.dock = true; dock(); }
  $("#dock")?.classList.remove("fold");
  document.body.classList.add("dragging");
});
document.addEventListener("dragend", () => { document.body.classList.remove("dragging"); $$(".over").forEach((x) => x.classList.remove("over")); });
const DROP = ".dslot,#dock,.tslot,.mvchip,.dropmark";
document.addEventListener("dragover", (e) => {
  const s = e.target.closest(DROP);
  if (!s) return;
  e.preventDefault();
  $$(".over").forEach((x) => x !== s && x.classList.remove("over"));
  s.classList.add("over");
});
document.addEventListener("drop", (e) => {
  const s = e.target.closest(DROP);
  if (!s) return;
  e.preventDefault();
  s.classList.remove("over");
  document.body.classList.remove("dragging");
  if (s.classList.contains("mvchip")) {
    const from = e.dataTransfer.getData("text/x-move");
    if (from !== "") moveMove(+from, +s.dataset.i);
    return;
  }
  const id = +e.dataTransfer.getData("text/x-pokemon");
  if (!id) return;
  if (s.dataset.drop === "fav") { if (!isFav(id)) toggleFav(id, true).catch((x) => alert(x.message)); return; }
  if (s.dataset.drop === "gef") { if (!isCaught(id)) toggleCaught(id).catch((x) => alert(x.message)); return; }
  const fromSlot = e.dataTransfer.getData("text/x-slot");
  const to = s.dataset.slot !== undefined ? +s.dataset.slot : null;
  if (fromSlot !== "") { if (to !== null) moveSlot(+fromSlot, to); }
  else addToTeam(id, to);
});

/* ------------------------------------------------------------------ Detailseite */
// Eigene Attacken: im Team je Platz (#pokemon/<id>/<platz>), sonst je Spiel und Pokémon im Browser
const moveSetKey = (id) => `set.${S.game || "-"}.${id}`;
let DETAIL = null, DSLOT = null;
function ownSet(id) {
  if (DSLOT !== null && S.team.ids[DSLOT] === id) return S.team.details[DSLOT]?.attacken || [];
  return store.get(moveSetKey(id), []);
}
function setOwnSet(id, moves) {
  moves = [...new Set(moves)].slice(0, 4);
  if (DSLOT !== null && S.team.ids[DSLOT] === id) { S.team.details[DSLOT] = Object.assign({}, S.team.details[DSLOT], {attacken: moves}); saveTeam(); dock(); }
  else store.set(moveSetKey(id), moves);
}
function moveMove(a, b) {
  const id = DETAIL?.id, cur = ownSet(id);
  if (!id || a === b || a >= cur.length) return;
  const [m] = cur.splice(a, 1);
  cur.splice(Math.min(b, cur.length), 0, m);
  setOwnSet(id, cur);
  renderMoves(DETAIL.attacken, $("#lvl")?.value);
}
// PokéWiki: Suche mit „Seite“, springt bei genauem Treffer direkt auf die Seite (Attacke, Fähigkeit, Ort, Typ)
const wikiUrl = (q) => `https://www.pokewiki.de/index.php?title=Spezial:Suche&go=Seite&search=${encodeURIComponent(q)}`;
const wikiLink = (q, label = esc(q)) => `<a class="wl" href="${esc(wikiUrl(q))}" target="_blank" rel="noopener noreferrer">${label}</a>`;
function backLink() {
  const tab = (FROM.slice(1) || "").split("/")[0];
  const names = {team: "Team", attacken: "Attacken", typen: "Typen", pokemon: "Liste"};
  if (FROM && names[tab] && FROM !== HERE) return `<a class="btn" href="${esc(FROM)}">← ${FROM.includes("/") ? "Zurück" : names[tab]}</a>`;
  return `<a class="btn" href="#pokemon">← Liste</a>`;
}
async function detailView(id, slot = null) {
  main.innerHTML = `<p class="hint">Lädt …</p>`;
  const rid = RID;
  DSLOT = slot !== null && S.team.ids[slot] === id ? slot : slotOf(id) >= 0 ? slotOf(id) : null;
  const inTeam = DSLOT !== null;
  const level = inTeam ? S.team.details[DSLOT]?.level || "" : "";
  const d = await api(`/api/pokemon/${id}?` + qs({spiel: S.game, level}));
  if (rid !== RID) return;
  DETAIL = d;
  ROWS[d.id] = Object.assign(ROWS[d.id] || {}, d);
  [...d.attacken.attacken, ...d.attacken.status].forEach((m) => { MOVES[m.id] = m; });
  const stats = d.werte.map((v, i) => `<span>${STAT[i]}</span><span class="num">${v}</span><span class="sbar" data-tip="${esc(statTip(i, v))}"><i style="width:${Math.min(100, v / statMax(i) * 100)}%;background:${statColor(v)}"></i></span>`).join("");
  const evo = d.entwicklung.length > 1 ? d.entwicklung.map((e, i) => (i && e.von ? `<span class="ar">→ ${esc(e.bedingungen.join(" oder ") || "")}</span>` : "") +
    `<a class="st" href="#pokemon/${e.id}">${img(e.id)}${esc(e.name)}</a>`).join("") : "";
  main.innerHTML = `
    <div class="bar">${backLink()}
      <label class="game2">Spiel <select class="gamesel"></select></label>
      ${inTeam ? `<button data-act="teamdel" data-slot="${DSLOT}">Aus dem Team nehmen</button>` : ""}
      ${teamFull() ? (inTeam ? "" : `<span class="hint">Team voll</span>`) : `<button class="${inTeam ? "" : "primary"}" data-act="teamadd" data-id="${d.id}">${inTeam ? "Noch einmal ins Team" : "Ins Team"}</button>`}
      <button data-act="fav" data-id="${d.id}" data-markbtn="fav" class="mark${isFav(d.id) ? " on" : ""}">${markLabel("fav", isFav(d.id))}</button>
      <button data-act="caught" data-id="${d.id}" data-markbtn="gef" class="mark${isCaught(d.id) ? " on" : ""}" data-tip="${ballTip(d.id)}">${markLabel("gef", isCaught(d.id), d.id)}</button>
      ${S.alphaOk.has(d.id) || isAlpha(d.id) ? `<button data-act="alpha" data-id="${d.id}" data-markbtn="alpha" class="mark${isAlpha(d.id) ? " on" : ""}">${markLabel("alpha", isAlpha(d.id), d.id)}</button>` : ""}
      <a class="btn" href="#vergleich/${d.id}/-" data-tip="Neben ein anderes Pokémon stellen: Werte, Typwirkung, Fähigkeiten, Attacken">Vergleichen</a>
      <a class="btn" href="${esc(d.wiki)}" target="_blank" rel="noopener noreferrer">Im PokéWiki öffnen</a>
      ${d.formen.length ? `<span class="hint">Formen:</span>` + d.formen.map((f) => `<a class="btn small" href="#pokemon/${f.id}">${esc(f.name)}</a>`).join("") : ""}</div>
    ${!d.im_spiel && S.game ? `<div class="note warn">In ${esc(gameName())} nicht enthalten.</div>` : ""}
    ${inTeam && S.team.ids.filter((x) => x === id).length > 1 ? `<div class="note info">${esc(d.name)} ist mehrmals im Team; hier geht es um Platz ${DSLOT + 1}.</div>` : ""}
    <div class="cols">
      <div class="box"><div class="head"><div class="pic">${img(d.id, "big", true)}${extrasHtml(d)}</div><div><h2>${esc(d.name)}</h2><div class="muted">#${d.nr ?? d.art} · ${esc(d.kategorie)}</div>
        <div style="margin-top:4px">${tchips(d.typen)}</div><span data-tip-stats="${d.werte.join(",")}">${radar(d.werte, 220, true)}</span></div></div>
        <p>${esc(d.text)}</p><div class="stats">${stats}<span><b>Summe</b></span><span class="num" data-tip="${esc(statTip("summe", d.summe))}"><b style="color:${sumColor(d.summe)}">${d.summe}</b></span><span></span></div>
        ${moreHtml(d)}
        ${d.faehigkeiten.length ? `<h3>Fähigkeiten</h3>` + d.faehigkeiten.map((a) => `<div><b>${wikiLink(a.name)}</b>${a.versteckt ? " <span class='cls'>versteckt</span>" : ""}${a.wirkt ? " <span class='cls'>ändert Typwirkung</span>" : ""}<div class="why">${esc(a.text)}</div></div>`).join("")
          : S.game === "legends-arceus" ? `<p class="hint">In Legenden: Arceus gibt es keine Fähigkeiten.</p>` : ""}
      </div>
      <div class="stack">
        <div class="box"><h2 data-tip="Verteidigung: so stark treffen Attacken eines Typs ${esc(d.name)}">Verteidigung: Typwirkung gegen ${esc(d.name)}</h2>
          ${d.faehigkeit_wirkt ? `<p class="hint">Mit Fähigkeit eingerechnet.</p>` : ""}
          ${defHtml(Object.fromEntries(Object.entries(d.wirkung).map(([t, f]) => [t, f])))}</div>
        <div class="box"><h2 data-tip="Typ-Duell: wie gut ${esc(d.name)} gegen Pokémon eines Typs steht. Austeilen = bester eigener Typ, einstecken = beide eigenen Typen zusammengerechnet. Hovern zeigt die Rechnung.">Im Duell gegen Typen</h2>
          <p class="hint">${DUEL_LEGEND}</p>
          ${duelHtml(d.name, d.typen)}</div>
        ${evo ? `<div class="box"><h2>Entwicklung</h2><div class="evo">${evo}</div></div>` : ""}
        ${catchHtml(d)}
        ${heldHtml(d)}
        ${optikHtml(d)}
      </div>
    </div>
    <div class="box" style="margin-top:12px"><h2>Fundorte in ${esc(gameName())}</h2>${encHtml(d)}</div>
    <div class="box" id="mbox"></div>`;
  header();
  renderMoves(d.attacken, level);
  wireExtras(d);
  window.scrollTo(0, 0);
}
// Sprite-Umschalter (Artwork, schillernd, animiert) und Ruf, nur für schon geladene Extras
function extrasHtml(d) {
  const x = d.extras || {}, b = [];
  if (x.shiny || x.shinyart || x.anim) {
    b.push(`<button class="small on" data-pic="art">Artwork</button>`);
    if (x.shiny || x.shinyart) b.push(`<button class="small" data-pic="${x.shinyart ? "shinyart" : "shiny"}" data-tip="Schillernde Form${x.shinyart ? "" : " (Sprite; das Artwork lädt der nächste Abgleich)"}">Schillernd</button>`);
    if (x.anim) b.push(`<button class="small" data-pic="anim" data-tip="Animiertes Sprite">Animiert</button>`);
  }
  if (x.rufe) b.push(`<button class="small" data-ruf="${d.id}" data-tip="Ruf abspielen">▶ Ruf</button>`);
  return b.length ? `<div class="picbar">${b.join("")}</div>` : "";
}
function wireExtras(d) {
  const pic = $(".head .pic img");
  $$("[data-pic]").forEach((b) => b.addEventListener("click", () => {
    $$("[data-pic]").forEach((x) => x.classList.toggle("on", x === b));
    pic.src = b.dataset.pic === "art" ? `artwork/${d.id}.png?v=2` : `${b.dataset.pic}/${d.id}`;
    pic.classList.toggle("px", b.dataset.pic === "shiny" || b.dataset.pic === "anim");
  }));
  const rb = $("[data-ruf]");
  if (rb) rb.addEventListener("click", () => { new Audio(`rufe/${d.id}`).play().catch(() => { rb.textContent = "Ruf fehlt"; }); });
}
/* Formen nur zum Ansehen (Burmy, Vivillon, Icognito …): gleiche Werte, eigenes Aussehen; Bilder lädt der Abgleich */
function optikHtml(d) {
  const xs = d.optik || [];
  if (!xs.length) return "";
  return `<details class="box"><summary><h2>Formen zum Ansehen</h2><span class="hint">${xs.length} · gleiche Werte, anderes Aussehen</span></summary>
    <div class="optik">${xs.map((x) => `<figure>${x.id == null ? img(d.id) : x.bild ? `<img class="spr" src="formen/${x.id}" alt="" loading="lazy">` : `<img class="spr none" src="icon.svg" alt="">`}
      <figcaption>${esc(x.name)}</figcaption></figure>`).join("")}</div>
    ${xs.some((x) => !x.bild) ? `<p class="hint">Fehlende Bilder lädt der nächste Abgleich.</p>` : ""}</details>`;
}
/* Getragene Items wilder Pokémon (PokéWiki), mit Bild und Anteil; „Elite“ nur bei Alpha-Pokémon */
function heldHtml(d) {
  const xs = d.getragen || [];
  if (!xs.length) return "";
  return `<div class="box"><h2>Getragene Items</h2><table class="rows held"><tbody>${xs.map((x) => `<tr>
    <td>${x.id ? `<img class="ibild sm" src="itembild/${x.id}" alt="" loading="lazy" onerror="this.remove()">` : ""}</td><td><b>${wikiLink(x.item)}</b>${x.elite ? ` <span class="alpha" data-tip="Nur Elite-Pokémon (Alpha)">Elite</span>` : ""}</td>
    <td class="c num">${esc(x.prozent)}</td></tr>`).join("")}</tbody></table><p class="hint">Beim Fangen oder Besiegen, aus dem PokéWiki.</p></div>`;
}
/* Fangchance als eigene Karte unter der Entwicklung: offen, solange das Pokémon nicht als gefangen markiert ist */
function catchHtml(d) {
  const m = d.mehr || {};
  if (!m.fangen || BATTLE()) return "";
  const pc = (v) => `<span style="color:${ramp(v / 100)}">${String(v).replace(".", ",")} %</span>`;
  const la = (S.game || "").startsWith("legends-"), grob = m.fang_grob && !la;
  return `<details class="box"${isCaught(d.id) ? "" : " open"}><summary><h2>Fangchance</h2><span class="hint">Fangrate ${m.fangrate}${isCaught(d.id) ? " · schon gefangen" : ""}</span></summary>
    <table class="rows sort"><thead><tr>${th("Ball")}${thc("volle KP")}${thc("1 KP", "Ein einziger KP übrig: der beste Fall, etwa dreimal so gut wie volle KP. Die Chance steigt gleichmäßig, je weniger KP übrig sind, ohne Schwellen")}${thc("1 KP, gelähmt", "Paralyse, Vergiftung und Verbrennung: Fangrate ×1,5")}${thc("1 KP, schlafend", `Schlaf und Einfrieren: Fangrate ×${m.schlaf_faktor || 2.5}`)}</tr></thead>
    <tbody>${m.fangen.map((f) => `<tr><td>${esc(f.ball)}</td><td class="c" data-s="${f.voll}">${pc(f.voll)}</td><td class="c" data-s="${f.rot}">${pc(f.rot)}</td><td class="c" data-s="${f.status ?? ""}">${f.status != null ? pc(f.status) : "–"}</td><td class="c" data-s="${f.schlaf}">${pc(f.schlaf)}</td></tr>`).join("")}</tbody></table>
    <p class="hint">Je Wurf, ohne kritischen Fang und ohne Boni durch Level oder Runde. Statusprobleme helfen: Schlaf und Einfrieren am meisten, Paralyse, Gift und Verbrennung etwas${la ? ". Die Legenden-Spiele rechnen anders (Wurf in den Rücken, Level, Alpha); die Werte geben nur eine Richtung."
      : grob ? ". Generation 1 und 2 rechnen anders; die Werte geben nur eine Richtung." : "."}</p></details>`;
}
// Mehr Details, eingeklappt: Geschlecht, Wachstum, Ei-Gruppen, EV-Ausbeute
const EVK = ["kp", "ang", "vert", "spang", "spvert", "init"];
function moreHtml(d) {
  const m = d.mehr || {};
  if (!Object.keys(m).length) return "";
  const rows = [];
  if (m.geschlecht) rows.push(["Geschlecht", esc(m.geschlecht)]);
  if (m.wachstum) rows.push(["Wachstum", esc(m.wachstum)]);
  if (m.eigruppen) rows.push(["Ei-Gruppen", esc(m.eigruppen.join(", ")) + (m.eizyklen != null ? ` · ${m.eizyklen} Ei-Zyklen` : "")]);
  if (m.ev && m.ev.length) rows.push(["EV-Ausbeute", m.ev.map((e) => `${e.punkte} ${STAT[EVK.indexOf(e.wert)]}`).join(", ")]);
  return rows.length ? `<details class="mehr"><summary>Mehr Details</summary>
    <div class="kv">${rows.map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join("")}</div></details>` : "";
}
// Farben für Werte: Stärke (bis 150), Genauigkeit (ab 70), Wertung (bis 160), von Rot nach Grün
const ramp = (x) => `hsl(${Math.max(0, Math.min(1, x)) * 125} 62% 40%)`;
const powCell = (v) => v ? `<span style="color:${ramp((v - 30) / 100)}">${v}</span>` : "–";
// Stärke, in Legenden: Arceus darunter Kraftstil / Tempostil (aus dem PokéWiki)
const powStil = (m) => powCell(m.staerke) + (m.kraft != null || m.tempo != null
  ? `<span class="stil" data-tip="${esc(`Kraftstil: Stärke ${m.kraft ?? "–"} (langsamer, oft mit Zusatzwirkung)\nTempostil: Stärke ${m.tempo ?? "–"} (schneller, oft öfter am Zug)`)}">${m.kraft ?? "–"} / ${m.tempo ?? "–"}</span>` : "");
const accCell = (v) => v ? `<span style="color:${ramp((v - 60) / 40)}">${v}</span>` : `<span data-tip="Trifft immer">–</span>`;
const scoreColor = (v) => ramp((v - 20) / 120);
// Alle Attacken des Spiels, für „andere Attacke hinzufügen“ (TM, Lehrer, Trainingsgelände)
const ALLMOVES = {};
async function allMoves() {
  const k = S.game || "-";
  if (!ALLMOVES[k]) ALLMOVES[k] = (await api("/api/attacken?" + qs({spiel: S.game, lernbar: 0}))).rows;
  ALLMOVES[k].forEach((m) => { MOVES[m.id] = Object.assign(MOVES[m.id] || {}, m); });
  return ALLMOVES[k];
}
// Marke: beim Attacken-Lehrer lernbar (die Beherrschung steht schon in der Spalte „Weg“)
function moveMarks(m) {
  const w = m.wege || [], out = [];
  if (w.includes("Lehrer")) out.push(`<span class="cls mk-lehrer" data-tip="${esc(w.length > 1 ? "Auch beim Attacken-Lehrer" : "Nur beim Attacken-Lehrer")}">Lehrer</span>`);
  return out.length ? " " + out.join(" ") : "";
}
// Bewährte Sets (Showdown, Random Battle): Rolle, Attacken, Übernehmen
function setsHtml(A, mine) {
  if (!A.sets || !A.sets.length) return "";
  return `<h3 style="margin-top:12px" data-tip="Aus den Random-Battle-Sets von Pokémon Showdown: erprobte Kombinationen für Kämpfe der Generation ${A.sets_gen}. Grau: nicht in der Lernliste dieses Spiels.">Bewährte Sets <span class="hint">(Showdown, Generation ${A.sets_gen})</span></h3>
    ${A.sets.map((x, i) => `<div class="pset"><b>${esc(x.rolle || "Set")}</b>${x.faehigkeiten.length ? ` <span class="hint">· ${esc(x.faehigkeiten.join(", "))}</span>` : ""}
      <div>${x.attacken.map((m) => `<span class="pmv${m.lernbar ? "" : " off"}${mine.includes(m.id) ? " same" : ""}"${m.lernbar ? "" : ` data-tip="Nicht in der Lernliste dieses Spiels"`}>${tchip(m.typ)} ${esc(m.name)}</span>`).join("")}</div>
      ${x.vorschlag.length ? `<button class="small" data-act="settake" data-i="${i}" data-tip="${esc("Übernimmt die vier stärksten lernbaren: " + x.vorschlag.map((id) => x.attacken.find((m) => m.id === id).name).join(", "))}">Übernehmen</button>` : ""}</div>`).join("")}`;
}
function renderMoves(A, level) {
  const d = DETAIL, id = d.id, inTeam = DSLOT !== null;
  const all = Object.fromEntries([...A.attacken, ...A.status].map((m) => [m.id, m]));
  const mine = ownSet(id).filter((x) => all[x] || MOVES[x]);
  const mv = (x) => all[x] || MOVES[x];
  const covered = new Set();
  mine.map(mv).filter((m) => m.klasse !== 1 && m.staerke).forEach((m) => Object.entries(S.chart?.[m.typ] || {}).forEach(([t, f]) => f > 1 && covered.add(t)));
  const mrow = (m, status = false) => `<tr class="${m.jetzt === false ? "off" : ""}${mine.includes(m.id) ? " sel" : ""}"><td data-s="${esc(m.name)}"><span${m.text ? ` data-tip="${esc(m.text)}"` : ""}>${wikiLink(m.name)}</span>${m.geaendert ? ' <span class="cls" data-tip="Werte in diesem Spiel anders als heute">Spielwert</span>' : ""}${moveMarks(m)}</td>
    <td class="c" data-s="${tname(m.typ)}">${tchip(m.typ)}</td><td class="c"><span class="cls">${CLS[m.klasse] || ""}</span></td><td class="c num" data-s="${m.staerke ?? 0}">${powStil(m)}</td><td class="c num" data-s="${m.genauigkeit ?? 101}">${accCell(m.genauigkeit)}</td>
    <td class="c num" data-s="${status ? 0 : m.wertung}">${status ? "–" : `<b style="color:${scoreColor(m.wertung)}">${m.wertung}</b>`}</td><td class="c weg" data-s="${esc(m.wege[0] || "")}">${m.wege.map((w) => esc(w).replace(", Beherrschung", "<br>Beherrschung")).join("<br>")}</td><td class="why">${status ? (m.kurz ? `<b>${kurzHtml(m.kurz)}</b>` : esc(m.text || "")) : (m.kurz ? kurzHtml(m.kurz) + (m.gruende.length ? " · " : "") : "") + esc(m.gruende.join(" · "))}</td>
    <td class="c">${mine.includes(m.id) ? `<button class="small on" data-act="mvdel" data-mid="${m.id}" data-tip="Aus deiner Auswahl">✓</button>` : mine.length < 4 ? `<button class="small" data-act="mvadd" data-mid="${m.id}" data-tip="In deine Auswahl (4 Plätze)">+</button>` : ""}</td></tr>`;
  const std = (A.standard || []).map((x) => all[x]?.name).filter(Boolean);
  // Deine Auswahl als feste Tabelle mit vier Zeilen: springt nicht, wenn Attacken dazukommen oder gehen
  const mineRow = (i) => {
    const m = mv(mine[i]);
    if (!m) return `<tr class="mvchip empty" data-i="${i}"><td class="grip"></td><td colspan="7" class="hint">Platz ${i + 1}: mit + in der Tabelle wählen</td></tr>`;
    const r = all[m.id];
    return `<tr class="mvchip" draggable="true" data-i="${i}"><td class="grip" data-tip="Ziehen zum Umsortieren">⋮⋮</td><td class="c">${tchip(m.typ)}</td>
      <td${m.text ? ` data-tip="${esc(m.text)}"` : ""}><b>${esc(m.name)}</b>${r ? "" : ` <span class="cls" data-tip="Nicht in der Lernliste dieses Spiels (TM, Lehrer, Trainingsgelände)">beigebracht</span>`}</td>
      <td class="c"><span class="cls">${CLS[m.klasse] || ""}</span></td><td class="c num">${powStil(r || m)}</td><td class="c num">${accCell((r || m).genauigkeit)}</td>
      <td class="c num">${r?.wertung ? `<b style="color:${scoreColor(r.wertung)}">${r.wertung}</b>` : ""}</td>
      <td><button class="link" data-act="mvdel" data-mid="${m.id}" data-tip="Aus deiner Auswahl">✕</button></td></tr>`;
  };
  $("#mbox").innerHTML = `<h2>Attacken${A.spiel_name ? " in " + esc(A.spiel_name) : ""}</h2>
    ${A.hinweis ? `<div class="note info">${esc(A.hinweis)}</div>` : ""}
    <div class="bar"><label>${inTeam ? "Level im Team" : "Bis Level"} <input id="lvl" type="number" min="1" max="100" style="width:70px" value="${esc(level || "")}"></label>
      <span class="hint">${inTeam ? "Gilt für diesen Platz im Team und filtert die Attacken." : "Leer: alle erlernbaren. Mit Level zählen nur Attacken, die bis dahin gehen."}</span></div>
    <div class="cols">
      <div><h3>Deine Auswahl${inTeam ? ` (Team, Platz ${DSLOT + 1})` : ""}</h3>
        <table class="mine"><thead><tr><th></th>${[["typ", "Typ"], ["name", "Attacke"], ["klasse", "Klasse"], ["staerke", "Stärke"], ["genauigkeit", "Gen."], ["wertung", "Wertung"]]
          .map(([k, n]) => `<th data-ms="${k}"${k === "name" ? "" : ` class="c"`}${MSORT.k === k ? ` data-dir="${MSORT.dir}"` : ""} data-tip="Auswahl danach sortieren (ändert die Reihenfolge)">${n}</th>`).join("")}<th></th></tr></thead>
          <tbody>${[0, 1, 2, 3].map(mineRow).join("")}</tbody></table>
        ${mine.length ? `<p class="hint">Trifft sehr effektiv: ${covered.size ? [...covered].map(tchip).join(" ") : "nichts"} (${covered.size} von ${Object.keys(S.chart || {}).length} Typen)</p>`
          : `<p class="hint">Mit + in der Tabelle wählen. ${inTeam ? "Die Auswahl zählt in der Team-Bewertung." : "Gespeichert in diesem Browser; im Team zählt sie für die Bewertung."}</p>`}
        <div class="bar">${mine.length ? `<button class="small" data-act="mvclear" data-tip="Alle vier Plätze leeren">Alle entfernen</button>` : ""}${std.length ? `<button class="small" data-act="mvstd" data-tip="${esc("Wie im Spiel: die letzten vier Level-Attacken bis zum Level (ohne Level die ersten vier): " + std.join(", "))}">Standard-Attacken</button>` : ""}
          <div class="ac"><input id="mvextra" type="search" placeholder="Andere Attacke (TM, Lehrer …)" style="width:240px"></div></div></div>
      <div><h3>Vorschlag: vier Attacken</h3><table class="mine sug"><thead><tr><th class="c">Typ</th><th>Attacke</th><th>Warum</th></tr></thead><tbody>${[0, 1, 2, 3].map((i) => { const m = A.moveset[i];
          return m ? `<tr class="sgrow${mine.includes(m.id) ? " same" : ""}"><td class="c">${tchip(m.typ)}</td><td><b>${esc(m.name)}</b></td><td class="why">${esc(m.grund)}</td></tr>`
            : `<tr class="sgrow empty"><td colspan="3" class="hint">${i ? "" : "Keine Schadens-Attacke."}</td></tr>`; }).join("")}</tbody></table>
        ${A.moveset.length ? `<button class="small" data-act="mvtake" style="margin-top:6px">Als eigene Auswahl übernehmen</button>` : ""}
        ${setsHtml(A, mine)}</div>
    </div>
    <h3>Schadens-Attacken nach Wertung</h3>
    <p class="hint">Wertung = Stärke × Genauigkeit × Eigentyp-Bonus × passender Angriffswert, mit Zu- und Abschlägen (Aussetzen, Anlauf, Rückstoß, Werte senken, Vorrang). Spalten zum Sortieren anklicken; deine Auswahl ist hinterlegt.</p>
    <div class="scroll"><table class="sort fixed mvt">${MVCOLS}<thead><tr>${th("Attacke")}${thc("Typ")}${thc("Klasse")}${thc("Stärke")}${thc("Gen.", "Genauigkeit in Prozent; – trifft immer")}${thc("Wertung")}${thc("Weg", "Wie das Pokémon die Attacke lernt")}${th("Gründe", "", true)}<th></th></tr></thead>
      <tbody>${A.attacken.map((m) => mrow(m)).join("") || `<tr><td colspan="9" class="hint">Keine Lernliste.</td></tr>`}</tbody></table></div>
    ${A.status.length ? `<details open><summary>Status-Attacken (${A.status.length})</summary><div class="scroll"><table class="sort fixed mvt">${MVCOLS}<thead><tr>${th("Attacke")}${thc("Typ")}${thc("Klasse")}${thc("Stärke")}${thc("Gen.")}${thc("Wertung", "Status-Attacken haben keine Wertung")}${thc("Weg")}${th("Wirkung", "", true)}<th></th></tr></thead>
      <tbody>${A.status.map((m) => mrow(m, true)).join("")}</tbody></table></div></details>` : ""}`;
  $("#lvl").addEventListener("change", async (e) => {
    const v = e.target.value;
    if (inTeam) { S.team.details[DSLOT] = Object.assign({}, S.team.details[DSLOT], {level: v ? Math.max(1, Math.min(100, +v)) : null}); saveTeam(); dock(); }
    const A2 = await api(`/api/pokemon/${id}/attacken?` + qs({spiel: S.game, level: v}));
    d.attacken = A2;
    renderMoves(A2, v);
  });
  $$("table.mine th[data-ms]").forEach((h) => h.addEventListener("click", () => {
    const k = h.dataset.ms, num = !["typ", "name", "klasse"].includes(k);
    const first = num ? "desc" : "asc", second = num ? "asc" : "desc";
    const dir = MSORT.k !== k ? first : MSORT.dir === first ? second : "";
    if (!dir) { if (MSORT.orig) setOwnSet(id, MSORT.orig.filter((x) => mine.includes(x)).concat(mine.filter((x) => !MSORT.orig.includes(x))));
      MSORT = {k: "", dir: ""}; renderMoves(DETAIL.attacken, $("#lvl")?.value); return; }
    const val = (x) => { const m = mv(x); return k === "wertung" ? all[x]?.wertung ?? 0 : k === "typ" ? tname(m.typ) : k === "genauigkeit" ? m.genauigkeit ?? 101 : m[k] ?? 0; };
    const sorted = [...mine].sort((a, b) => { const x = val(a), y = val(b); const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "de");
      return dir === "asc" ? c : -c; });
    MSORT = {k, dir, orig: MSORT.orig && MSORT.k ? MSORT.orig : [...mine]};
    setOwnSet(id, sorted);
    renderMoves(DETAIL.attacken, $("#lvl")?.value);
  }));
  $$("[data-act=settake]").forEach((b) => b.addEventListener("click", () => {
    const x = A.sets[+b.dataset.i];
    x.attacken.forEach((m) => { if (!MOVES[m.id]) MOVES[m.id] = all[m.id] || m; });
    setOwnSet(id, x.vorschlag.slice(0, 4));
    renderMoves(DETAIL.attacken, $("#lvl")?.value);
  }));
  moveSearch($("#mvextra"), (m) => {
    const cur = ownSet(id);
    if (cur.length >= 4) return alert("Alle vier Plätze sind belegt. Nimm erst eine Attacke heraus.");
    setOwnSet(id, [...cur, m.id]);
    renderMoves(DETAIL.attacken, $("#lvl")?.value);
  });
}
function moveSearch(el, onPick) {
  const box = el.closest(".ac");
  const menu = document.createElement("div");
  menu.className = "menu";
  menu.hidden = true;
  box.appendChild(menu);
  let rows = [];
  el.addEventListener("input", async () => {
    const q = el.value.trim().toLowerCase();
    if (!q) { menu.hidden = true; return; }
    rows = (await allMoves()).filter((m) => m.name.toLowerCase().includes(q)).slice(0, 12);
    menu.innerHTML = rows.map((m, i) => `<button data-i="${i}">${tchip(m.typ)} ${esc(m.name)} <span class="muted">${CLS[m.klasse]}${m.staerke ? " · " + m.staerke : ""}</span></button>`).join("") || `<div class="hint" style="padding:6px">Nichts gefunden</div>`;
    menu.hidden = false;
  });
  menu.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-i]");
    if (!b) return;
    menu.hidden = true;
    el.value = "";
    onPick(rows[+b.dataset.i]);
  });
  el.addEventListener("keydown", (e) => { if (e.key === "Enter" && rows[0] && !menu.hidden) { menu.hidden = true; el.value = ""; onPick(rows[0]); } });
}

/* ------------------------------------------------------------------ Team */
function autocomplete(el, onPick) {
  const box = el.closest(".ac");
  const menu = document.createElement("div");
  menu.className = "menu";
  menu.hidden = true;
  box.appendChild(menu);
  let timer, rows = [];
  el.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = el.value.trim();
      if (!q) { menu.hidden = true; return; }
      rows = (await api("/api/pokemon?" + qs({q, spiel: S.game, formen: "relevant", kampf: 1, limit: 12}))).rows;
      rows.forEach((r) => { ROWS[r.id] = r; });
      menu.innerHTML = rows.map((r, i) => `<button data-i="${i}" data-id="${r.id}" draggable="true" title="Klicken oder ziehen">${img(r.id)}${esc(r.name)} ${tchips(r.typen)}</button>`).join("") || `<div class="hint" style="padding:6px">Nichts gefunden</div>`;
      menu.hidden = false;
    }, 150);
  });
  menu.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-i]");
    if (!b) return;
    e.stopPropagation();
    menu.hidden = true;
    el.value = "";
    onPick(rows[+b.dataset.i]);
  });
  el.addEventListener("keydown", (e) => { if (e.key === "Enter" && rows[0] && !menu.hidden) { menu.hidden = true; el.value = ""; onPick(rows[0]); } });
  document.addEventListener("click", (e) => { if (!box.contains(e.target)) menu.hidden = true; });
}
let TEAMS = [];
const TSORT = {nr: ["Nummer", (r) => r.nr ?? r.art], level: ["Level", (r, d) => -(d.level || 0)], summe: ["Basiswerte", (r) => -r.summe],
  kp: ["KP", (r) => -r.werte[0]], ang: ["Angriff", (r) => -r.werte[1]], vert: ["Verteidigung", (r) => -r.werte[2]],
  spa: ["Sp.-Angriff", (r) => -r.werte[3]], spv: ["Sp.-Verteidigung", (r) => -r.werte[4]], init: ["Initiative", (r) => -r.werte[5]]};
function sortTeam(k) {
  const t = S.team, f = TSORT[k]?.[1];
  if (!f) return;
  const order = t.ids.map((id, i) => i).sort((a, b) => {
    const ra = ROWS[t.ids[a]], rb = ROWS[t.ids[b]];
    return ra && rb ? f(ra, t.details[a] || {}) - f(rb, t.details[b] || {}) || a - b : a - b;
  });
  t.ids = order.map((i) => t.ids[i]);
  t.details = order.map((i) => t.details[i]);
  S.tsort = k;
  teamChanged();
}
function teamNote() {
  const el = $("#tnote");
  if (!el) return;
  const w = mismatch(), t = S.team;
  el.innerHTML = w.map((x) => `<div class="note warn">${esc(x)}${t.spiel && t.spiel !== S.game && x.startsWith("Dieses Team") ? ` <button class="small" data-act="tgame">Zu ${esc(gameName(t.spiel))} wechseln</button>` : ""}</div>`).join("");
}
function teamBar() {
  const el = $("#tbar"), t = S.team;
  if (!el) return;
  el.innerHTML = `<button data-act="tnew">Neues Team</button>
    ${t.tid ? `<button class="${t.dirty ? "primary" : ""}" data-act="tsave"${t.dirty ? "" : " disabled"}>Speichern</button>${t.dirty ? `<button data-act="tundo">Verwerfen</button>` : ""}
      <button data-act="tsaveas">Speichern unter …</button><button data-act="trename">Umbenennen</button><button data-act="tdel">Löschen</button>`
      : `<button class="primary" data-act="tsaveas">Speichern</button>`}
    <button data-act="tclear">Leeren</button>
    <span class="hint">${t.tid ? (t.dirty ? "Geändert, noch nicht gespeichert: die Änderungen bleiben im Browser, bis du speicherst oder verwirfst." : "Gespeichert.") : "Ein gespeichertes Team behält Level und Attacken je Platz."}</span>`;
  const o = $("#saved option");
  if (o && t.tid) o.textContent = `${t.name}${t.dirty ? " (geändert)" : ""}`;
}
function favBox() {
  const el = $("#favs");
  if (!el) return;
  $("#favn").textContent = S.favs.length ? `(${S.favs.length})` : "";
  el.innerHTML = S.favs.length ? `<div class="list favlist">${S.favs.map(monCard).join("")}</div>`
    : `<p class="hint">Markiere Pokémon mit dem Stern (in der Liste oder auf der Detailseite) oder ziehe sie hierher. Sie stehen dann hier und beim Klick auf einen leeren Platz bereit.</p>`;
}
/* Gefangene: Empfehlungen daraus (bessere Alternative jetzt, langfristig mehr Potential nach der Entwicklung) */
async function caughtBox() {
  const el = $("#gef");
  if (!el) return;
  const rid = RID, t = S.team;
  if (!S.caught.size) {
    el.innerHTML = `<p class="hint">Markiere gefangene Pokémon mit dem Pokéball (in der Liste, auf der Detailseite oder hierher ziehen). Dann zeigt sich hier, wer dein Team jetzt verbessern würde und wer nach der Entwicklung.</p>`;
    return;
  }
  const r = await api("/api/team/gefangen", {spiel: S.game, ids: t.ids, details: t.details, gewichte: weights()});
  if (rid !== RID || !$("#gef")) return;
  [...r.alternativen, ...r.potential].forEach((x) => { ROWS[x.id] = Object.assign(ROWS[x.id] || {}, x); if (x.wird) ROWS[x.wird.id] = Object.assign(ROWS[x.wird.id] || {}, x.wird); });
  const where = (x) => x.slot === null || x.slot === undefined ? "auf einen freien Platz" : `statt ${esc(x.statt)} (Platz ${x.slot + 1})`;
  const line = (x, extra = "") => `<div class="imp diff" data-id="${x.id}" data-hc="${x.id}" draggable="true"><a href="#pokemon/${x.id}">${img(x.id)}</a><div class="grow"><b>${esc(x.name)}</b> ${tchips(x.typen)}
    <div class="why">${extra}<b class="plus">+${x.plus}</b> Teamwertung ${where(x)}</div></div>
    <button class="small" data-act="${x.slot === null || x.slot === undefined ? "teamadd" : "pickfav"}" data-id="${x.id}" data-slot="${x.slot ?? ""}">${x.slot === null || x.slot === undefined ? "Ins Team" : "Tauschen"}</button></div>`;
  el.innerHTML = `<p class="hint">${S.caught.size} gefangen in ${esc(gameName())}.</p>
    <h3 data-tip="Ein Tausch mit einem Mitglied (oder ein freier Platz) hebt die Teamwertung jetzt">Bessere Alternative</h3>
    ${r.alternativen.map((x) => line(x)).join("") || `<p class="hint">Nichts aus deiner Sammlung hebt das Team im Moment.</p>`}
    <h3 data-tip="Noch nicht voll entwickelt: die Endstufe würde das Team deutlich mehr heben als das Pokémon heute">Langfristig mehr Potential</h3>
    ${r.potential.map((x) => `<div class="imp diff" data-id="${x.id}" data-hc="${x.id}" draggable="true"><a href="#pokemon/${x.id}">${img(x.id)}</a><span class="arrow">→</span><a href="#pokemon/${x.wird.id}" data-hc="${x.wird.id}">${img(x.wird.id)}</a>
      <div class="grow"><b>${esc(x.name)}</b> → <b>${esc(x.wird.name)}</b> ${tchips(x.wird.typen)}<div class="why">als ${esc(x.wird.name)}: <b class="plus">+${x.plus}</b> Teamwertung ${where(x)}</div></div></div>`).join("")
      || `<p class="hint">Nichts aus deiner Sammlung, das entwickelt deutlich mehr bringt.</p>`}
    <p class="hint">„Bestes Team suchen“ mit „nur aus deiner Sammlung“ im Filter baut ein Team nur aus Pokémon, die du als gefangen markiert hast.</p>`;
}
async function teamView() {
  const rid = RID;
  const t = S.team, w = weights();
  main.innerHTML = `
    <div class="box"><div class="bar"><b>Teams in</b> <select class="gamesel"></select>
      <select id="saved"><option value="">${t.tid ? "– anderes Team laden –" : "Aktuelles Team (nicht gespeichert)"}</option></select>
      <span id="tbar" class="bar" style="margin:0"></span>
      <label class="hint">Sortieren <select id="tsort"><option value="">eigene Reihenfolge</option>${Object.entries(TSORT).map(([k, [n]]) => `<option value="${k}"${S.tsort === k ? " selected" : ""}>${n}</option>`).join("")}</select></label></div>
      <div id="tnote"></div>
      <div class="bar"><div class="ac grow"><input id="add" type="search" placeholder="Pokémon hinzufügen: Name oder Nummer" style="width:100%"></div>
        <a class="btn" href="#initiative" data-tip="Wer ist schneller: alle Pokémon des Spiels nach Initiative, mit deinem Team">Initiative-Liste</a></div>
      <details class="sdbox" id="sdbox"><summary>Showdown-Text <span class="hint">Team als Text übernehmen oder weitergeben (Pokémon Showdown, PokePaste)</span></summary>
        <textarea id="sdtext" rows="12" spellcheck="false" placeholder="Garchomp @ Choice Scarf&#10;Ability: Rough Skin&#10;EVs: 252 Atk / 4 SpD / 252 Spe&#10;Jolly Nature&#10;- Earthquake"></textarea>
        <div class="bar"><button data-act="sdexp" data-tip="Das aktuelle Team als Text">Aus dem Team</button>
          <button class="primary" data-act="sdimp" data-tip="Ersetzt das aktuelle Team">Als Team übernehmen</button>
          <button data-act="sdcopy">Kopieren</button><span id="sdnote" class="hint"></span></div></details>
      <div class="tslots" id="slots"><p class="hint">Lädt …</p></div>
      <details class="favd dropmark" data-drop="fav" open><summary>${icon("fav")} Favoriten in ${esc(gameName())} <span id="favn"></span> <span class="hint">zum schnellen Tauschen auf einen Platz ziehen; hierher ziehen macht zum Favoriten</span></summary><div id="favs"></div></details></div>
    <div class="cols">
      <div class="box"><h2>Bewertung</h2><div id="ev"><p class="hint">Lädt …</p></div></div>
      <div class="box"><h2>Verbesserungen</h2><div id="imp"></div></div>
      <div class="box dropmark" data-drop="gef"><h2>${icon("ball")} Aus deiner Sammlung</h2><div id="gef"><p class="hint">Lädt …</p></div></div>
    </div>
    <div class="box" style="margin-top:12px"><h2>Passende Pokémon finden</h2>
      <div class="cols"><div><h3>Ziel</h3>
        <div class="bar"><select id="preset">${Object.entries(PRESET_DE).map(([k, n]) => `<option value="${k}"${k === S.preset && !S.weights ? " selected" : ""}>${n}</option>`).join("")}
          <option value=""${S.weights ? " selected" : ""}>Eigene Gewichte</option></select>
          <label><input type="checkbox" id="tleg"${S.tleg ? " checked" : ""}> ohne Legendäre und Mysteriöse</label></div>
        <div class="weights">${Object.entries(CRIT).map(([k, n]) => `<span data-tip="${esc(CRIT_TIP[k])}">${n}</span><input type="range" min="0" max="10" step="1" data-w="${k}" value="${w[k]}"><span class="num">${w[k]}</span>`).join("")}</div>
        <div class="bar" style="margin-top:8px"><button class="primary" data-act="opt">Bestes Team suchen</button>
          <label data-tip="Wie „nur aus deiner Sammlung“ im Filter rechts"><input type="checkbox" id="tgef"${S.tfilter.nur === "gef" ? " checked" : ""}> nur aus deiner Sammlung</label>
          <span class="hint">Festgesetzte (📌) bleiben, der Rest wird aus den gefilterten Pokémon gefüllt.</span></div>
        <div id="opt"></div></div>
        <div><h3>Filter für Vorschläge und Suche</h3>${filterBar(S.tfilter, "tf", {sort: false})}</div></div>
      <h3>Vorschläge für den nächsten Platz</h3><div id="sug" class="sugs"><p class="hint">Mit mindestens einem Mitglied.</p></div>
    </div>
    <div class="box"><h2>Gegen Gegner</h2>
      <div class="bar"><div class="ac grow"><input id="foe" type="search" placeholder="Gegner hinzufügen (bis zu 6, etwa die Pokémon eines Arenaleiters)" style="width:100%"></div>
        ${S.foes.length ? `<button data-act="foeclear">Gegner leeren</button>` : ""}</div>
      <div id="mu"><p class="hint">Wähle Gegner: das Tool zeigt, wer aus deinem Team gegen wen im Vorteil ist.</p></div></div>`;
  header();
  teamBar();
  favBox();
  teamNote();
  autocomplete($("#add"), (r) => addToTeam(r.id));
  $("#sdbox").open = store.get("sdOpen", false);
  $("#sdbox").addEventListener("toggle", (e) => { store.set("sdOpen", e.target.open); if (e.target.open && !$("#sdtext").value.trim()) sdExport(); });
  if ($("#sdbox").open) sdExport();
  autocomplete($("#foe"), (r) => { if (S.foes.length < 6 && !S.foes.includes(r.id)) { S.foes.push(r.id); store.set("foes", S.foes); } matchup(); });
  bindFilter(S.tfilter, "tf", () => teamRefresh(), () => store.set("tfilter", S.tfilter));
  $("#tleg").addEventListener("change", (e) => { S.tleg = e.target.checked; store.set("tleg", S.tleg); teamRefresh(); });
  $("#tsort").addEventListener("change", (e) => { if (e.target.value) sortTeam(e.target.value); else S.tsort = ""; });
  $("#tgef").addEventListener("change", (e) => { S.tfilter.nur = e.target.checked ? "gef" : ""; store.set("tfilter", S.tfilter); teamView(); });
  $("#saved").addEventListener("change", async (e) => {
    const tt = TEAMS.find((x) => x.id === +e.target.value);
    if (!tt) return;
    if (S.team.dirty && !await ask(S.team.name ? `„${S.team.name}“ hat ungespeicherte Änderungen.` : "Das Team hat ungespeicherte Änderungen.", `Verwerfen und „${tt.name}“ laden?`, "Verwerfen und laden")) { e.target.value = ""; return; }
    loadTeam(tt);
  });
  $("#preset").addEventListener("change", (e) => {
    if (e.target.value) { S.preset = e.target.value; S.weights = null; store.set("preset", S.preset); store.set("weights", null); }
    else S.weights = {...weights()};
    saveTeam();
    teamView();
  });
  $$("[data-w]").forEach((el) => el.addEventListener("change", () => {
    S.weights = {...weights(), [el.dataset.w]: +el.value};
    store.set("weights", S.weights);
    el.nextElementSibling.textContent = el.value;
    $("#preset").value = "";
    saveTeam();
    teamRefresh();
  }));
  // Gespeicherte Teams und Bewertung zugleich laden
  const teamsP = api("/api/teams").then((xs) => {
    TEAMS = xs;
    if (rid !== RID || !$("#saved")) return;
    const here = xs.filter((x) => x.spiel === S.game && x.id !== S.team.tid), other = xs.filter((x) => x.spiel !== S.game && x.id !== S.team.tid);
    $("#saved").insertAdjacentHTML("beforeend", here.map((x) => `<option value="${x.id}">${esc(x.name)} (${x.mitglieder.length})</option>`).join("")
      + (other.length ? `<optgroup label="Andere Spiele">${other.map((x) => `<option value="${x.id}">${esc(x.name)} · ${esc(gameName(x.spiel))}</option>`).join("")}</optgroup>` : ""));
    if (S.team.tid) $("#saved option").textContent = `${S.team.name}${S.team.dirty ? " (geändert)" : ""}`;
  });
  await Promise.all([teamsP, teamRefresh()]);
  if (S.foes.length) matchup();
}
function loadTeam(tt) {
  S.team = normTeam({ids: tt.mitglieder, fest: tt.fest, tid: tt.id, name: tt.name, spiel: tt.spiel, details: tt.details});
  if (Object.keys(tt.gewichte || {}).length) { S.weights = tt.gewichte; store.set("weights", S.weights); }
  store.set("team", S.team);
  if (tt.spiel && tt.spiel !== S.game) setGame(tt.spiel); else teamView();
}
async function teamRefresh() {
  const t = S.team, rid = RID;
  const ev = await api("/api/team/bewerten", {spiel: S.game, ids: t.ids, gewichte: weights(), details: t.details});
  if (rid !== RID || !$("#slots")) return;
  (ev.mitglieder || []).forEach((m) => { ROWS[m.id] = Object.assign(ROWS[m.id] || {}, m); });
  Object.entries(ev.attacken || {}).forEach(([k, m]) => { MOVES[k] = Object.assign(MOVES[k] || {}, m, {id: +k}); });
  CHECK = {key: "", nicht: ev.nicht_im_spiel || [], fremd: ev.fremde_attacken || {}};
  teamNote();
  teamBar();
  const bad = new Set(CHECK.nicht);
  $("#slots").innerHTML = [0, 1, 2, 3, 4, 5].map((i) => {
    const id = t.ids[i], m = ROWS[id];
    if (!id || !m) return `<div class="tslot empty" data-slot="${i}" data-act="pick" data-tip="Klicken: aus den Favoriten wählen">Platz ${i + 1}<br><span class="hint">hierher ziehen, oben suchen<br>oder klicken für die Favoriten</span></div>`;
    const fixed = t.fest.includes(id), det = t.details[i] || {};
    return `<div class="tslot${fixed ? " fixed" : ""}${bad.has(i) ? " warn" : ""}" data-slot="${i}" draggable="true" data-id="${id}" data-hc="${id}">
      <span class="grip" data-tip="Ziehen zum Umsortieren">⋮⋮</span>
      <button class="small fixbtn${fixed ? " on" : ""}" data-act="pin" data-id="${id}" data-tip="Für die Teamsuche festsetzen">📌</button>
      <button class="small swap" data-act="pick" data-slot="${i}" data-tip="Gegen einen Favoriten tauschen">⇄</button>
      <button class="small x" data-act="teamdel" data-slot="${i}" data-tip="Entfernen">✕</button>
      <a href="#pokemon/${id}/${i}" draggable="false">${img(id, "mid", true)}<br><b>${esc(m.name)}</b></a>
      ${bad.has(i) ? `<div class="note warn small">Nicht in ${esc(gameName())}</div>` : ""}
      <div>${tchips(m.typen)}</div><div class="hint">${det.level ? "Level " + det.level + " · " : ""}Basiswerte <b style="color:${sumColor(m.summe)}">${m.summe}</b></div>
      ${slotExtra(ev.plaetze?.[i])}
      <div class="mvs">${(det.attacken || []).map((x) => MOVES[x] ? (CHECK.fremd?.[i] || []).includes(x)
        ? `<span class="mv off" data-tip="${esc(`Nicht in der Lernliste von ${gameName()}`)}">${tchip(MOVES[x].typ)} ${esc(MOVES[x].name)} <b class="wbadge">!</b></span>`
        : `<span class="mv">${tchip(MOVES[x].typ)} ${esc(MOVES[x].name)}</span>` : "").join("") || `<a class="hint" href="#pokemon/${id}/${i}">Attacken wählen</a>`}</div></div>`;
  }).join("");
  dock();
  t.ids.forEach((x, i) => fillStandard(i));
  caughtBox();
  if (!t.ids.length) { $("#ev").innerHTML = `<p class="hint">Füge Pokémon hinzu.</p>`; $("#sug").innerHTML = ""; $("#imp").innerHTML = ""; return; }
  const ms = ev.mitglieder;
  $("#ev").innerHTML = `<div class="score" data-tip="Gewichteter Schnitt der Kriterien (Gewichte unter „Ziel“)">${ev.wertung}<span class="hint"> / 100</span></div>
    <div class="crit">${Object.entries(CRIT).map(([k, n]) => `<span data-tip="${esc(CRIT_TIP[k])}">${n}</span><span class="sbar"><i style="width:${ev.kriterien[k] * 100}%"></i></span><span class="num">${Math.round(ev.kriterien[k] * 100)}</span>`).join("")}</div>
    ${ev.offen.length ? `<div class="note stop">Offene Schwächen (mehr Mitglieder schwach als resistent): ${tchips(ev.offen)}</div>` : `<div class="note go">Keine offene Schwäche.</div>`}
    ${ev.vierfach.length ? `<div class="note warn">4-fach-Schwächen: ${ev.vierfach.map(([a, n]) => `${esc(n)} gegen ${tchip(a)}`).join(", ")}</div>` : ""}
    ${ev.nicht_abgedeckt.length ? `<p class="hint">Nicht sehr effektiv getroffen (mit den gewählten Attacken, sonst Eigentypen): ${tchips(ev.nicht_abgedeckt)}</p>` : ""}
    <p class="hint">${ev.physisch} physisch, ${ev.speziell} speziell · schnell: ${esc(ev.schnell.join(", ") || "keiner")}</p>
    <details><summary>Typwirkung je Mitglied</summary><div class="scroll"><table class="matrix" id="matrix"><tr><th></th>${ms.map((m, i) => `<th data-hc="${m.id}" data-c="${i}" data-pc="${i}">${img(m.id)}</th>`).join("")}</tr>
      ${Object.keys(S.types).filter((a) => ev.matrix[ms[0].id]?.[a] !== undefined).map((a) => `<tr data-r="${a}"><th class="r" data-pr="${a}">${tchip(a)}</th>${ms.map((m, i) => { const f = ev.matrix[m.id][a]; return `<td data-c="${i}" data-tip="${esc(`${tname(a)} gegen ${m.name}: ×${fl(f)}`)}"><span class="f ${fcls(f)}">${f === 1 ? "" : fl(f)}</span></td>`; }).join("")}</tr>`).join("")}</table></div>
      <p class="hint">Zeile: angreifender Typ, Spalte: Mitglied. Klick hält Zeile oder Spalte fest.</p></details>`;
  crossTable($("#matrix"), MPIN);
  $("#ev details").open = store.get("matrixOpen", false);
  $("#ev details").addEventListener("toggle", (e) => store.set("matrixOpen", e.target.open));
  // Wo ein Vorschlag vom Team abweicht, ist die Zeile dezent hinterlegt; „passt so“ bleibt blass
  $("#imp").innerHTML = (ev.verbesserungen || []).length ? ev.verbesserungen.map((v) => { const diff = v.hinweise.length || v.besser.length;
    const cur = (t.details[v.slot]?.attacken || []).map((x) => MOVES[x]).filter(Boolean);
    return `<div class="imp${diff ? " diff" : " same"}" data-hc="${v.id}" data-slot="${v.slot}"><a href="#pokemon/${v.id}/${v.slot}">${img(v.id)}</a><div><b>${esc(v.name)}</b> <span class="muted">Platz ${v.slot + 1}</span>
      ${v.hinweise.map((h) => `<div class="why">${esc(h)}</div>`).join("")}
      ${v.besser.length ? `<div class="why">Statt <b class="old">${esc(v.schwaechste)}</b> besser:</div><div class="alts">${v.besser.map((b) => `<span class="new">${tchip(b.typ)} <b>${esc(b.name)}</b> <span class="muted">Wertung ${b.wertung}</span></span>`).join("")}</div>
        <div class="why">Jetzt: ${cur.map((m) => `${esc(m.name)}`).join(", ")}</div>` : ""}
      ${!diff ? `<div class="why">Passt so.</div>` : ""}</div></div>`; }).join("")
    : `<p class="hint">Lege Level und Attacken in der Detailansicht eines Mitglieds fest (Klick auf das Bild), dann zeigt sich hier, was besser ginge.</p>`;
  if (t.ids.length < 6) {
    $("#sug").innerHTML = `<p class="hint">Rechnet …</p>`;
    const sg = await api("/api/team/vorschlag", {spiel: S.game, ids: t.ids, gewichte: weights(), details: t.details, filter: {...filterQuery(S.tfilter), ohne_leg: S.tleg || S.tfilter.ohne_leg ? 1 : ""}});
    if (rid !== RID || !$("#sug")) return;
    sg.rows.forEach((r) => { ROWS[r.id] = Object.assign(ROWS[r.id] || {}, r); });
    const already = sg.schon_im_team ? `<p class="hint">${sg.schon_im_team} passende ${sg.schon_im_team === 1 ? "Form gehört" : "Formen gehören"} zu Arten, die schon im Team sind, und fehlen deshalb hier. Doppelt aufnehmen geht trotzdem: über „+“ in der Liste oder die Suche oben.</p>` : "";
    $("#sug").innerHTML = (sg.rows.map((r) => `<div class="sugg" draggable="true" data-id="${r.id}">${monCard(r)}<div class="why"><b>+${r.plus}</b> · ${esc(r.gruende.join(" · "))}</div></div>`).join("") || `<p class="hint">Keine Vorschläge mit diesen Filtern.</p>`) + already;
  } else $("#sug").innerHTML = `<p class="hint">Das Team ist voll. Entferne ein Mitglied, um Vorschläge zu sehen, oder nutze „Bestes Team suchen“.</p>`;
}
async function optimize() {
  $("#opt").innerHTML = `<p class="hint">Sucht … (einige Sekunden)</p>`;
  const r = await api("/api/team/optimieren", {spiel: S.game, fest: S.team.fest, gewichte: weights(), filter: {...filterQuery(S.tfilter), ohne_leg: S.tleg || S.tfilter.ohne_leg ? 1 : ""}});
  r.teams.forEach((t) => t.mitglieder.forEach((m) => { ROWS[m.id] = Object.assign(ROWS[m.id] || {}, m); }));
  // Mitglieder, die nicht im aktuellen Team sind, dezent markiert
  const now = new Set(S.team.ids);
  $("#opt").innerHTML = `<p class="hint">Aus ${r.pool} Pokémon (Filter rechts${S.tfilter.nur === "gef" ? ", nur aus deiner Sammlung" : ""}) in ${esc(gameName())}. Hinterlegt: nicht in deinem Team.</p>` + r.teams.map((t, i) => `<div class="optt">
    <div class="bar"><b class="score-s">${t.wertung}</b><span class="grow">${t.mitglieder.map((m) => `<a href="#pokemon/${m.id}" data-hc="${m.id}" class="${now.has(m.id) ? "" : "new"}">${img(m.id)}</a>`).join("")}</span>
    <button class="small" data-act="take" data-i="${i}">Übernehmen</button></div>
    <div class="why">${t.mitglieder.map((m) => now.has(m.id) ? esc(m.name) : `<b>${esc(m.name)}</b>`).join(", ")}${t.offen.length ? " · offen: " + t.offen.map(tname).join(", ") : ""}</div></div>`).join("");
  S.lastOpt = r.teams;
}
async function matchup() {
  const box = $("#mu");
  if (!box) return;
  if (!S.foes.length) { box.innerHTML = `<p class="hint">Wähle Gegner: das Tool zeigt, wer aus deinem Team gegen wen im Vorteil ist.</p>`; return; }
  const foeCard = (id, r) => `<div class="foe" draggable="true" data-foe="${id}" data-hc="${id}">${img(id, "", true)}<b>${esc(r?.name || "#" + id)}</b><div>${tchips(r?.typen || [])}</div>
    <button class="small x" data-act="foedel" data-id="${id}" data-tip="Gegner entfernen">✕</button></div>`;
  if (!S.team.ids.length) { box.innerHTML = `<div class="foes">${S.foes.map((id) => foeCard(id, ROWS[id])).join("")}</div><p class="hint">Erst ein Team zusammenstellen.</p>`; return; }
  const miss = S.foes.filter((id) => !ROWS[id]?.werte);
  const [r, extra] = await Promise.all([api("/api/team/gegner", {spiel: S.game, ids: S.team.ids, gegner: S.foes, details: S.team.details}),
    miss.length ? api("/api/team/bewerten", {spiel: S.game, ids: miss, kurz: 1}) : null]);
  (extra?.mitglieder || []).forEach((m) => { ROWS[m.id] = Object.assign(ROWS[m.id] || {}, m); });
  if (!$("#mu")) return;
  r.einzeln.forEach((x) => { if (x.gegner.id) ROWS[x.gegner.id] = Object.assign(ROWS[x.gegner.id] || {}, {id: x.gegner.id, name: x.gegner.name, typen: x.gegner.typen}); });
  const verdict = Object.fromEntries(r.einzeln.flatMap((x) => x.rows.map((row) => [`${row.id}:${x.gegner.id}`, row])));
  const seen = new Set();
  box.innerHTML = `<div class="foes">${r.einzeln.map((x) => foeCard(x.gegner.id, ROWS[x.gegner.id])).join("")}</div>
    ${r.ohne_antwort.length ? `<div class="note warn">Niemand im Team ist klar im Vorteil gegen: ${esc(r.ohne_antwort.join(", "))}</div>` : `<div class="note go">Gegen jeden Gegner hast du mindestens einen guten Kandidaten.</div>`}
    <div class="scroll"><table class="vs" id="vs"><thead><tr><th></th>${r.einzeln.map((x, i) => `<th class="foeh" data-c="${i}" data-pc="${i}" data-hc="${x.gegner.id}">${img(x.gegner.id)}<div>${esc(x.gegner.name)}</div></th>`).join("")}</tr></thead><tbody>
      ${r.uebersicht.filter((m) => !seen.has(m.id) && seen.add(m.id)).map((m, k) => `<tr data-r="${k}"><th class="r" data-pr="${k}" data-hc="${m.id}">${img(m.id)} ${esc(m.name)}</th>${r.einzeln.map((x, i) => { const v = verdict[`${m.id}:${x.gegner.id}`], u = VERDICT[v.urteil];
        return `<td data-c="${i}" class="v-${v.urteil}" data-tip="${esc(`${m.name} gegen ${x.gegner.name}: ${u[1]}\n${v.gruende.map((g) => "· " + g).join("\n")}`)}">${u[0]}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div>
    <p class="hint">Vorteil: teilt mehr aus, als es einsteckt (Typen und Initiative). Nachteil: steckt mehr ein, als es austeilt. Die Attacken des Gegners zählen über seine Typen, deine über die gewählten Attacken. Zelle hovern für die Rechnung; Klick hält Zeile oder Spalte fest. Gegner lassen sich oben per Ziehen umsortieren.</p>`;
  crossTable($("#vs"), VPIN);
  foeDrag(box);
}
// Gegner per Ziehen umsortieren (einmal je Kasten anmelden; der Inhalt wird neu gezeichnet)
function foeDrag(box) {
  if (box.dataset.dnd) return;
  box.dataset.dnd = "1";
  box.addEventListener("dragstart", (e) => { const f = e.target.closest(".foe"); if (!f) return; e.dataTransfer.setData("text/x-foe", f.dataset.foe); e.dataTransfer.effectAllowed = "move"; card.hidden = true; });
  box.addEventListener("dragover", (e) => {
    const f = e.target.closest(".foe");
    if (!f || !e.dataTransfer.types.includes("text/x-foe")) return;
    e.preventDefault();
    $$(".foe.over", box).forEach((x) => x !== f && x.classList.remove("over"));
    f.classList.add("over");
  });
  box.addEventListener("dragleave", (e) => { const f = e.target.closest(".foe"); if (f && !f.contains(e.relatedTarget)) f.classList.remove("over"); });
  box.addEventListener("drop", (e) => {
    const f = e.target.closest(".foe"), from = +e.dataTransfer.getData("text/x-foe");
    if (!f || !from) return;
    e.preventDefault();
    const to = +f.dataset.foe, a = S.foes.indexOf(from), b = S.foes.indexOf(to);
    if (a < 0 || b < 0 || a === b) return;
    S.foes.splice(a, 1); S.foes.splice(b, 0, from);
    store.set("foes", S.foes); VPIN.c = null;
    matchup();
  });
}

const VERDICT = {schicken: ["Vorteil", "im Vorteil, gut einzusetzen"], geht: ["ausgeglichen", "ausgeglichen, weder klar besser noch schlechter"],
  schonen: ["Nachteil", "im Nachteil, besser nicht gegen diesen Gegner"]};

/* ------------------------------------------------------------------ Attacken */
async function movesView() {
  const f = Object.assign({q: "", typen: [], klasse: "", lernbar: true, min: "", prio: false, kontakt: "", gen: "", genmodus: "bis", team: false}, store.get("mfilter2", {}));
  // Attacken des aktuellen Teams: Attacke → Mitglieder, die sie haben
  const teamMoves = {};
  S.team.ids.forEach((id, i) => (S.team.details[i]?.attacken || []).forEach((m) => { (teamMoves[m] = teamMoves[m] || []).push(ROWS[id]?.name || `#${id}`); }));
  const rid = RID;
  main.innerHTML = `<div class="bar"><span class="hint">Spiel</span><select class="gamesel"></select>
    <input id="mq" class="grow" type="search" placeholder="Attacke suchen" value="${esc(f.q)}"></div>
    <div class="bubbles">${Object.entries(S.types).map(([t, n]) => `<button class="tb t t${t}${f.typen.includes(t) ? " in" : ""}" data-mt="${t}">${esc(n)}</button>`).join("")}</div>
    <div class="bar"><span class="seg">${[["", "Alle"], ["2", "Physisch"], ["3", "Speziell"], ["1", "Status"]].map(([k, n]) => `<button data-mk="${k}" class="${f.klasse === k ? "on" : ""}">${n}</button>`).join("")}</span>
      <label data-tip="Nur Attacken, die im gewählten Spiel mindestens ein Pokémon lernen kann"><input type="checkbox" id="mlern"${f.lernbar ? " checked" : ""}> im Spiel erlernbar</label>
      <label data-tip="Nur die Attacken, die die Mitglieder des aktuellen Teams haben"><input type="checkbox" id="mteam"${f.team ? " checked" : ""}> Team-Attacken</label>
      <label data-tip="Vorrang (Priorität): die Attacke kommt vor normalen Attacken dran, egal wie schnell der Gegner ist (etwa Ruckzuckhieb). Höhere Zahl = noch früher"><input type="checkbox" id="mprio"${f.prio ? " checked" : ""}> nur mit Vorrang</label>
      <label data-tip="Kontakt: der Angreifer berührt das Ziel. Das löst Fähigkeiten wie Rauhaut, Statik oder Flammkörper aus; Attacken ohne Kontakt umgehen sie">Kontakt <select id="mkon"><option value="">egal</option><option value="1"${f.kontakt === "1" ? " selected" : ""}>mit</option><option value="0"${f.kontakt === "0" ? " selected" : ""}>ohne</option></select></label>
      <label data-tip="„bis“: Attacken bis zu dieser Generation; „nur“: Attacken, die in dieser Generation neu kamen"><select id="mgm"><option value="bis">bis</option><option value="nur"${f.genmodus === "nur" ? " selected" : ""}>nur</option></select>
        Gen <select id="mgen"><option value="">alle</option>${[1, 2, 3, 4, 5, 6, 7, 8, 9].map((g) => `<option${+f.gen === g ? " selected" : ""}>${g}</option>`).join("")}</select></label>
      <label>Stärke ab <input id="mmin" type="number" min="0" max="250" step="10" style="width:70px" value="${esc(f.min)}"></label>
      <button data-act="mreset">Zurücksetzen</button><span class="hint grow" id="mcnt"></span></div>
    <div id="mv"><p class="hint">Lädt …</p></div>`;
  header();
  let rows = [];
  const draw = () => {
    store.set("mfilter2", f);
    const q = f.q.trim().toLowerCase();
    const xs = rows.filter((m) => (!f.typen.length || f.typen.includes(String(m.typ))) && (!f.klasse || String(m.klasse) === f.klasse) &&
      (!q || m.name.toLowerCase().includes(q)) && (!f.min || (m.staerke || 0) >= +f.min) && (!f.prio || m.prio > 0) &&
      (f.kontakt === "" || m.merkmale.includes("contact") === (f.kontakt === "1")) &&
      (!f.gen || (f.genmodus === "nur" ? m.gen === +f.gen : m.gen <= +f.gen)) && (!f.team || teamMoves[m.id]));
    $("#mcnt").textContent = f.team && !Object.keys(teamMoves).length ? "Im Team sind noch keine Attacken gewählt"
      : `${xs.length} von ${rows.length} Attacken in ${gameName()}`;
    $("#mv").innerHTML = `<div class="box scroll sticky"><table class="sort fixed lines" style="min-width:980px"><colgroup><col style="width:23%"><col style="width:86px"><col style="width:74px"><col style="width:70px"><col style="width:54px"><col style="width:46px"><col style="width:70px"><col style="width:70px"><col style="width:66px"><col style="width:46px"><col></colgroup><thead><tr>${th("Attacke")}${thc("Typ")}${thc("Klasse")}${thc("Stärke")}${thc("Gen.", "Genauigkeit in Prozent; – trifft immer")}${thc("AP", "Angriffspunkte: so oft lässt sich die Attacke einsetzen")}
      ${thc("Vorrang", "Vorrang (Priorität): positive Werte kommen vor normalen Attacken dran, negative danach")}${thc("Wertung", "Stärke × Genauigkeit mit Zu- und Abschlägen, ohne Eigentyp-Bonus")}${thc("Lernen", "So viele Pokémon (und Formen) lernen sie im Spiel")}${thc("Gen", "Generation, seit der es die Attacke gibt")}${th("Wirkung", "Kurz-Info aus den Spieldaten; die ganze Beschreibung beim Hovern über die Zeile", true)}</tr></thead><tbody>
      ${xs.map((m) => `<tr data-r="${m.id}"><td data-s="${esc(m.name)}"><b${m.text ? ` data-tip="${esc(m.text)}"` : ""}>${wikiLink(m.name)}</b>${m.geaendert ? ' <span class="cls" data-tip="Werte in diesem Spiel anders als heute">Spielwert</span>' : ""}${m.merkmale.includes("contact") ? ' <span class="cls" data-tip="Kontakt: berührt das Ziel (löst etwa Rauhaut oder Statik aus)">Kontakt</span>' : ""}${teamMoves[m.id] ? ` <span class="cls tm" data-tip="${esc("Im Team: " + teamMoves[m.id].join(", "))}">Team${teamMoves[m.id].length > 1 ? " ×" + teamMoves[m.id].length : ""}</span>` : ""}</td><td class="c" data-s="${tname(m.typ)}">${tchip(m.typ)}</td>
        <td class="c"><span class="cls">${CLS[m.klasse]}</span></td><td class="c num" data-s="${m.staerke || 0}">${powStil(m)}</td><td class="c num" data-s="${m.genauigkeit ?? 101}">${accCell(m.genauigkeit)}</td>
        <td class="c num">${m.ap ?? ""}</td><td class="c num">${m.prio ? `<span data-tip="${m.prio > 0 ? `Vorrang +${m.prio}: kommt vor normalen Attacken` : `Vorrang ${m.prio}: kommt nach normalen Attacken`}">${m.prio > 0 ? "+" : ""}${m.prio}</span>` : ""}</td>
        <td class="c num" data-s="${m.wertung}"${m.gruende.length ? ` data-tip="${esc(m.gruende.join("\n"))}"` : ""}>${m.wertung ? `<b style="color:${scoreColor(m.wertung)}">${m.wertung}</b>` : ""}</td>
        <td class="c num">${m.lernen || ""}</td><td class="c num">${m.gen || ""}</td><td class="kurz">${kurzHtml(m.kurz || (m.klasse === 1 ? m.text || "" : ""))}</td></tr>`).join("")}</tbody></table></div>`;
    const tb = $("#mv table");
    // Name: Zeilenkopf (markiert nur die Zeile), die übrigen Zellen markieren Zeile und Spalte
    $$("tbody tr", tb).forEach((tr) => [...tr.cells].forEach((td, i) => { if (i) td.dataset.c = i; else td.dataset.pr = tr.dataset.r; }));
    crossTable(tb, APIN);
  };
  const load = async () => {
    const d = await api("/api/attacken?" + qs({spiel: S.game, lernbar: f.lernbar ? 1 : 0}));
    if (rid !== RID) return;
    rows = d.rows;
    draw();
  };
  $("#mq").addEventListener("input", (e) => { f.q = e.target.value; draw(); });
  $$("[data-mt]").forEach((b) => b.addEventListener("click", () => {
    const t = b.dataset.mt;
    f.typen = f.typen.includes(t) ? f.typen.filter((x) => x !== t) : [...f.typen, t];
    b.classList.toggle("in");
    draw();
  }));
  $$("[data-mk]").forEach((b) => b.addEventListener("click", () => { f.klasse = b.dataset.mk; $$("[data-mk]").forEach((x) => x.classList.toggle("on", x === b)); draw(); }));
  $("#mlern").addEventListener("change", (e) => { f.lernbar = e.target.checked; load(); });
  $("#mprio").addEventListener("change", (e) => { f.prio = e.target.checked; draw(); });
  $("#mteam").addEventListener("change", (e) => { f.team = e.target.checked; draw(); });
  $("#mkon").addEventListener("change", (e) => { f.kontakt = e.target.value; draw(); });
  $("#mmin").addEventListener("input", (e) => { f.min = e.target.value; draw(); });
  $("#mgen").addEventListener("change", (e) => { f.gen = e.target.value; draw(); });
  $("#mgm").addEventListener("change", (e) => { f.genmodus = e.target.value; draw(); });
  await load();
}

/* ------------------------------------------------------------------ Typtabelle */
const PIN = {r: null, c: null}, MPIN = {r: null, c: null}, VPIN = {r: null, c: null}, APIN = {r: null, c: null}, IPIN = {r: null, c: null};
let MSORT = {k: "", dir: ""};
/* ------------------------------------------------------------------ Karte (Legenden: Arceus)
   Spielkoordinaten 0–1024; Welt in Pixeln = Koordinate × 2 (2048 px bei Zoom 2). Kacheln 256 px von Serebii, auf dem Server
   gespeichert; Zoom 0 hat 2 × 2, Zoom 1 hat 4 × 4, Zoom 2 hat 8 × 8 Kacheln. Ziehen verschiebt, Mausrad zoomt. */
const WORLD = 2048;
const mpct = (x) => String(x).replace(".", ",") + " %";
/* Kartensymbole (Altissimo): Zeichen und Farbe je Art; Ebenen lassen sich einzeln ausblenden */
const MOBJ = {aprikoko: "A", beere: "B", baum: "Z", erz: "E", laub: "L", heu: "H", kiste: "K", truhe: "T",
  irrlicht: "✦", icognito: "?", vers: "V", graben: "G", kristall: "◆", verzerrung: "◎", massen: "M", baumpkmn: "P", alpha: "α", boden: "•", reise: "»", lager: "△"};
/* Ebenen in Gruppen; was keiner Gruppe angehört, steht unter „Weitere“ */
const MGROUPS = [["Pokémon", ["pokemon", "kristall", "verzerrung", "massen", "baumpkmn", "alpha"]], ["Bäume und Rohstoffe", ["baum", "aprikoko", "beere", "erz", "laub", "heu"]],
  ["Items", ["kiste", "truhe", "boden", "graben"]], ["Sammeln", ["irrlicht", "icognito", "vers"]], ["Orte", ["reise", "lager"]]];
let MAPPOS = null;          // Ausschnitt, wenn sich nur ein Filter ändert
const MOBJMON = new Set(["kristall", "verzerrung", "massen", "baumpkmn", "alpha"]);     // Symbole mit Pokémon statt Items
const MAPCACHE = {};        // Kartendaten je Gebiet: die Wahl eines Pokémon lädt nichts neu
const MOBJHINT = {irrlicht: "Geisterlicht zum Einsammeln; 107 gibt es in ganz Hisui.", icognito: "Icognito zum Fangen; 28 Formen gibt es in Hisui.",
  vers: "Gedicht zum Lesen (Sammelobjekt).", graben: "Grabstelle: hier lässt sich mit Ursaluna nach Items graben.",
  kristall: "Kristallbrocken: zerschlagen, dann erscheint das Pokémon.", verzerrung: "Raum-Zeit-Verzerrung: hier erscheinen die Pokémon während einer Verzerrung.",
  massen: "Massenauftreten: hier kann es zu einem Massenauftreten kommen.", baumpkmn: "Baum schütteln oder werfen: das Pokémon fällt heraus.",
  alpha: "Festes Alpha-Pokémon an dieser Stelle.", reise: "Schnellreise: hierher bringt dich Pikas Flug.", lager: "Lager: ausruhen, herstellen, Pokémon tauschen."};
const MAPSPIEL = "legends-arceus";          // bisher die einzige Karte mit Symbolen
const okey = (o) => `${o.art}:${Math.round(o.x)}:${Math.round(o.z)}`;
const mobjTip = (o, arten) => `${arten[o.art]?.[0] || o.art}${o.nr ? " " + o.nr : ""}` + (o.menge ? `\n${o.menge} Stück je Mal` : "")
  + (o.items.length ? "\n" + o.items.map(([n, p]) => p ? `${n}: ${p}` : n).join("\n") : "");
/* Übersicht mit Pokémon-Bildern: die Karte in Felder (64 Spieleinheiten) geteilt; je Feld die häufigsten Pokémon als
   Bild, so groß, wie sie dort wahrscheinlich sind. Gewicht je Spawnpunkt = sein Anteil (höchster Wert, 0–1), je Stelle der
   PokéWiki-Ebenen ihr Anteil oder 1. Das Bild sitzt im Schwerpunkt seiner Punkte im Feld */
const HEAT_G = 64;
function mapHeat(pts, objs, sh = (m) => m.max || 0) {
  const cells = {}, tot = {};
  const add = (x, z, id, name, w) => {
    if (!id) return;
    const k = Math.floor(x / HEAT_G) + "," + Math.floor(z / HEAT_G), c = cells[k] ||= {};
    const s = c[id] ||= {id, name, w: 0, n: 0, sx: 0, sz: 0, sw: 0};
    const ww = Math.max(w, 0.02);
    s.w += w; s.n++; s.sx += x * ww; s.sz += z * ww; s.sw += ww;
    const t = tot[id] ||= {id, name, w: 0, n: 0};
    t.w += w; t.n++;
  };
  pts.forEach((p) => p.mons.forEach((m) => { const v = sh(m); if (v > 0) add(p.x, p.z, m.id, m.name.replace(/ \(.*\)$/, ""), v / 100); }));
  objs.forEach((o) => { if (MOBJMON.has(o.art)) o.items.forEach(([n, t, id]) => {
    const pc = /([\d,]+) %/.exec(t || ""); add(o.x, o.z, id, n.replace(/ \(.*\)$/, ""), pc ? parseFloat(pc[1].replace(",", ".")) / 100 : o.items.length > 1 ? 1 / o.items.length : 1); }); });
  return {cells, tot};
}
const heatTip = (s) => `${s.name}: ${s.n} Stelle${s.n === 1 ? "" : "n"} hier, zusammen ${String(Math.round(s.w * 100) / 100).replace(".", ",")}`;
/* Gebiete eines Spiels (für Spiele ohne Karte): links die Orte, rechts alle Pokémon dort als Bildergitter, nach Methode.
   Gefangene sind blass (Filter „nur fehlende“). Gewählter Ort je Spiel gemerkt; #karte/gebiete/<Ort> öffnet ihn direkt */
/* Karten von Map Genie (für jedes Spiel, für das es dort eine gibt): Kacheln über den eigenen Server (im Datenordner
   zwischengespeichert), Orte als farbige Punkte je Gruppe, Filter je Kategorie, „gefunden“ per Rechtsklick wie bei
   Legenden: Arceus. #karte/mg/<Karte>; ohne Karte für das Spiel geht es zu den Gebieten */
const MGDATA = {};
const mgProj = (lat, lng, z) => {
  const s = 256 * 2 ** z, r = Math.PI / 180, sy = Math.sin(lat * r);
  return [(lng + 180) / 360 * s, (0.5 - Math.log((1 + sy) / (1 - sy)) / (4 * Math.PI)) * s];
};
async function mgView(slug, want) {
  const rid = RID;
  const lst = await api("/api/mapgenie?" + qs({spiel: S.game})).catch(() => ({karten: []}));
  if (rid !== RID) return;
  if (!lst.karten.length) return S.game === "legends-arceus" ? mapView() : areasView();
  const kk = "mgKarte:" + S.game;
  if (!slug || !lst.karten.some((k) => k.slug === slug)) slug = store.get(kk, lst.karten[0].slug);
  if (!lst.karten.some((k) => k.slug === slug)) slug = lst.karten[0].slug;
  store.set(kk, slug);
  const ck = S.game + "/" + slug;
  const d = MGDATA[ck] || (MGDATA[ck] = await api("/api/mapgenie?" + qs({spiel: S.game, karte: slug})));
  const gk = "mg-" + slug;
  // Legenden: Arceus: eigene Spawnpunkte und Symbole, an Geisterlichtern und Icognito ausgerichtet
  const own = d.spiel === "legends-arceus" ? (MGDATA[ck + "/eigene"] ||= await api("/api/mapgenie/eigene?" + qs({spiel: S.game, karte: slug})).catch(() => null)) : null;
  const gotRes = await api("/api/gefunden?" + qs({spiel: d.spiel})).catch(() => ({}));
  if (rid !== RID) return;
  window.scrollTo(0, 0);
  const got = new Set((gotRes[gk] || []).map((o) => gk + "|" + o));
  Object.entries(gotRes).forEach(([k, os]) => { if (k !== gk) os.forEach((o) => got.add(k + "|" + o)); });
  const cats = {}, groups = d.gruppen.map((g) => ({...g, kategorien: g.kategorien.map((c) => ({...c}))}));
  groups.forEach((g) => g.kategorien.forEach((c) => { cats[c.id] = Object.assign(c, {g}); }));
  /* alle Punkte in einer Liste: Orte von Map Genie (t "mg"), eigene Spawnpunkte ("sp") und eigene Symbole ("ob") */
  const pts = d.orte.filter((o) => cats[o[1]]).map((o) => ({t: "mg", id: o[0], c: o[1], la: o[2], lo: o[3], name: o[4], text: o[5]}));
  if (own && (own.punkte.length || own.objekte.length)) {
    const arten = own.arten || {}, og = {id: "own", titel: "Aus den Spieldaten", farbe: "#3a7bd5", kategorien: []};
    if (own.punkte.length) og.kategorien.push({id: "sp", titel: "Spawnpunkte", n: own.punkte.length, own: 1});
    Object.keys(arten).forEach((a) => { const n = own.objekte.filter((o) => o.art === a).length; if (n) og.kategorien.push({id: "o:" + a, titel: arten[a][1], n, own: 1, art: a}); });
    og.kategorien.forEach((c) => { cats[c.id] = Object.assign(c, {g: og}); });
    groups.unshift(og);
    own.punkte.forEach((p) => pts.push({t: "sp", c: "sp", la: p.la, lo: p.lo, alpha: p.alpha, mons: p.mons, k: p.k,
      name: p.mons.map((m) => m.name).join(", ")}));
    own.objekte.forEach((o) => pts.push({t: "ob", c: "o:" + o.art, la: o.la, lo: o.lo, o, k: o.k,
      name: (arten[o.art]?.[0] || o.art) + (o.nr ? " " + o.nr : ""), items: o.items.map((e) => e[0]).join(", ")}));
  }
  const gkey = (p) => p.t === "mg" ? gk + "|mg:" + p.id : p.t === "ob" ? p.k + "|" + okey(p.o) : "";
  const hk = "mgHide:" + d.spiel;
  // eigene Symbole außer den Spawnpunkten anfangs aus: Map Genie hat vieles davon selbst
  const hide = new Set(store.get(hk, Object.keys(cats).filter((k) => k.startsWith("o:"))).map((k) => (isNaN(+k) ? k : +k)));
  let gotHide = store.get("mapGotHide", false), q = "", sel = -1;
  const open = new Set(store.get("mgOpen", groups.filter((g) => g.kategorien.length <= 12).map((g) => String(g.id))).map(String));
  const cnt = (c) => { const f = pts.filter((p) => p.c === c.id && got.has(gkey(p))).length; return f ? `${f}/${c.n} ✓` : c.n; };
  const dot = (c) => c.id === "sp" ? `<span class="mpin-l"></span>` : c.art ? `<span class="mobj o-${c.art}">${MOBJ[c.art] || "•"}</span>` : `<span class="mgdot" style="--c:${esc(c.g.farbe)}">${esc(c.titel[0] || "•")}</span>`;
  const catBtn = (c) => `<button class="mlay${hide.has(c.id) ? "" : " on"}" data-cat="${esc(c.id)}">${dot(c)}${esc(c.titel)} <span class="hint" data-cnt="${esc(c.id)}">${cnt(c)}</span></button>`;
  const regions = d.gebiete || [];
  main.innerHTML = `<div class="box mapbox">
    <div class="bar"><h2 style="margin:0">Karte</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      ${lst.karten.length > 1 ? `<span class="seg">${lst.karten.map((k) => `<a class="btn${k.slug === slug ? " on" : ""}" href="#karte/mg/${esc(k.slug)}">${esc(k.titel)}</a>`).join("")}</span>` : ""}
      ${regions.length ? `<select id="mggo" aria-label="Gehe zu"><option value="">Gehe zu …</option>${regions.map((r, i) => `<option value="${i}">${esc(r[0])}</option>`).join("")}</select>` : ""}
      ${S.game === "legends-arceus" ? `<a class="btn" href="#karte/obsidianfieldlands" data-tip="Einzelkarten je Gebiet mit Tageszeit- und Wetterfilter">Einzelkarten</a>` : ""}
      <a class="btn" href="#karte/gebiete" data-tip="Alle Orte mit ihren Pokémon als Liste">Gebiete</a>
      <input id="mgq" type="search" placeholder="Ort, Symbol oder Pokémon suchen" style="width:240px">
      <label class="mgot" data-tip="Orte, die du als gefunden markiert hast (Rechtsklick oder ✓ in den Details), ausblenden"><input type="checkbox" id="gothide"${gotHide ? " checked" : ""}> gefundene ausblenden</label>
      <span class="hint grow" id="mgn"></span></div>
    <div class="mapwrap"><div class="mapcol"><div id="mgmap" class="map mgmap"><div class="mgtiles"></div><div class="mgpins"></div></div>
      <div class="mapzoom"><button data-mz="1" data-tip="näher">+</button><button data-mz="-1" data-tip="weiter weg">−</button><button data-mz="0" data-tip="ganze Karte">⤢</button></div></div>
      <div class="mgside"><aside id="mapside" class="mapside"><p class="hint">Fahre über einen Punkt für den Namen, klicke für Einzelheiten. Rechtsklick markiert ihn als gefunden. Die Suche listet die Treffer hier; ein Klick springt hin.</p></aside>
      <div class="mgcats"><div class="bar"><b>Ebenen</b><span class="mlay-all"><button class="link" data-all="1">alle</button> · <button class="link" data-all="0">keine</button></span></div>
        ${groups.map((g, gi) => `<details class="mgg"${open.has(String(g.id)) ? " open" : ""} data-gid="${esc(g.id)}"><summary>${g.id === "own" ? `<span class="mpin-l"></span>` : `<span class="mgdot" style="--c:${esc(g.farbe)}"></span>`}${esc(g.titel)} <span class="hint">${g.kategorien.reduce((a, c) => a + c.n, 0)}</span>
          <button class="link" data-grp="${gi}" data-tip="ganze Gruppe ein- oder ausblenden">ein/aus</button></summary><div class="mlays">${g.kategorien.map(catBtn).join("")}</div></details>`).join("")}</div></div></div>
    <p class="hint">Karte und Orte: Map Genie (mapgenie.io), Stand ${esc(String(d.am || "").slice(0, 10).split("-").reverse().join("."))}; Namen und Texte englisch wie dort.${own ? " „Aus den Spieldaten“: Spawnpunkte und Symbole wie auf den Einzelkarten, je Gebiet an Geisterlichtern und Icognito ausgerichtet (auf wenige Meter genau)." : ""} Kacheln lädt der Server beim ersten Ansehen und hebt sie auf.</p></div>`;
  header();
  const box = $("#mgmap"), tl = $(".mgtiles", box), pl = $(".mgpins", box);
  const zmin = d.min_zoom, zmax = d.max_zoom;
  const bb = d.bounds || (() => { const la = pts.map((p) => p.la), lo = pts.map((p) => p.lo); return [Math.min(...lo), Math.min(...la), Math.max(...lo), Math.max(...la)]; })();
  let z = zmin, cx = 0, cy = 0;
  const fitBox = (b) => {          // [west, süd, ost, nord] ins Bild, größte passende Zoomstufe
    const w = box.clientWidth, h = box.clientHeight;
    z = zmin;
    for (let t = zmax; t >= zmin; t--) {
      const [x1, y1] = mgProj(b[3], b[0], t), [x2, y2] = mgProj(b[1], b[2], t);
      if (x2 - x1 <= w * 0.92 && y2 - y1 <= h * 0.92) { z = t; break; }
    }
    const [x1, y1] = mgProj(b[3], b[0], z), [x2, y2] = mgProj(b[1], b[2], z);
    cx = (x1 + x2) / 2; cy = (y1 + y2) / 2;
  };
  const ql = () => q.toLowerCase();
  const match = (p) => !q || (p.name || "").toLowerCase().includes(ql()) || cats[p.c].titel.toLowerCase().includes(ql()) || (p.items || "").toLowerCase().includes(ql());
  const vis = (p) => !hide.has(p.c) && !(gotHide && got.has(gkey(p))) && match(p);
  const pinHtml = (p, i) => {
    const [x, y] = mgProj(p.la, p.lo, z), pos = `left:${x.toFixed(1)}px;top:${y.toFixed(1)}px`, g = got.has(gkey(p)) ? " got" : "", s = i === sel ? " sel" : "";
    if (p.t === "sp") return `<button class="mpin${p.alpha ? " alpha" : ""}${s}" data-i="${i}" style="${pos}" data-tip="${esc((p.alpha ? "Alpha-Spawnpunkt\n" : "") + p.mons.map((m) => `${m.alpha ? "Alpha-" : ""}${m.name}: bis ${mpct(m.max)}`).join("\n"))}"></button>`;
    if (p.t === "ob") return `<button class="mobj o-${p.o.art}${g}${s}" data-i="${i}" style="${pos}" data-tip="${esc(p.name + (p.items ? "\n" + p.items : ""))}">${MOBJ[p.o.art] || "•"}</button>`;
    const c = cats[p.c];
    return `<button class="mgp${g}${s}" data-i="${i}" style="${pos};--c:${esc(c.g.farbe)}" data-tip="${esc(p.name || c.titel)}${p.name && p.name !== c.titel ? "\n" + esc(c.titel) : ""}">${esc(c.titel[0] || "•")}</button>`;
  };
  const pins = () => {
    let n = 0;
    pl.innerHTML = pts.map((p, i) => { if (!vis(p)) return ""; n++; return pinHtml(p, i); }).join("");
    $("#mgn").textContent = `${n} von ${pts.length} Punkten`;
  };
  const tiles = () => {
    const w = box.clientWidth, h = box.clientHeight, ox = cx - w / 2, oy = cy - h / 2, nmax = 2 ** z;
    tl.style.transform = pl.style.transform = `translate(${-ox}px,${-oy}px)`;
    const wantT = new Set();
    for (let tx = Math.max(0, Math.floor(ox / 256)); tx <= Math.min(nmax - 1, Math.floor((ox + w) / 256)); tx++)
      for (let ty = Math.max(0, Math.floor(oy / 256)); ty <= Math.min(nmax - 1, Math.floor((oy + h) / 256)); ty++) wantT.add(`${z}/${tx}/${ty}`);
    $$("img", tl).forEach((im) => { if (!wantT.has(im.dataset.k)) im.remove(); else wantT.delete(im.dataset.k); });
    wantT.forEach((k) => {
      const [, tx, ty] = k.split("/").map(Number), im = new Image();
      im.dataset.k = k; im.alt = ""; im.draggable = false;
      im.style.left = tx * 256 + "px"; im.style.top = ty * 256 + "px";
      im.onerror = () => { im.style.visibility = "hidden"; };
      im.src = `/mgkachel/${encodeURIComponent(d.spiel)}/${encodeURIComponent(slug)}/${k}`;
      tl.appendChild(im);
    });
  };
  const redraw = () => { tl.innerHTML = ""; tiles(); pins(); };
  const zoomTo = (nz, px, py) => {
    nz = Math.max(zmin, Math.min(zmax, nz));
    if (nz === z) return;
    const w = box.clientWidth, h = box.clientHeight;
    px ??= w / 2; py ??= h / 2;
    const f = 2 ** (nz - z), wx = cx - w / 2 + px, wy = cy - h / 2 + py;
    cx = wx * f - px + w / 2; cy = wy * f - py + h / 2; z = nz;
    redraw();
  };
  /* zu einem Punkt springen: hinzoomen, mittig, ausgewählt, Einzelheiten rechts */
  const jump = (i) => {
    const p = pts[i];
    if (hide.has(p.c)) { hide.delete(p.c); saveHide(); }
    z = Math.max(z, Math.min(zmax, zmax - 2));
    [cx, cy] = mgProj(p.la, p.lo, z);
    sel = i; redraw(); side(i);
  };
  fitBox(bb); tiles(); pins();
  let drag = null, moved = false;
  box.addEventListener("pointerdown", (e) => { if (e.button !== 0) return; drag = {x: e.clientX, y: e.clientY, cx, cy}; moved = false; });
  box.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!moved && Math.abs(dx) + Math.abs(dy) < 4) return;
    if (!moved) { moved = true; box.setPointerCapture(e.pointerId); box.classList.add("grab"); }
    cx = drag.cx - dx; cy = drag.cy - dy; tiles();
  });
  const stop = () => { drag = null; box.classList.remove("grab"); };
  box.addEventListener("pointerup", stop);
  box.addEventListener("pointercancel", stop);
  box.addEventListener("wheel", (e) => { e.preventDefault(); const r = box.getBoundingClientRect(); zoomTo(z + (e.deltaY < 0 ? 1 : -1), e.clientX - r.left, e.clientY - r.top); }, {passive: false});
  box.addEventListener("dblclick", (e) => { const r = box.getBoundingClientRect(); zoomTo(z + 1, e.clientX - r.left, e.clientY - r.top); });
  $$("[data-mz]").forEach((b) => b.addEventListener("click", () => { if (b.dataset.mz === "0") { fitBox(bb); redraw(); } else zoomTo(z + +b.dataset.mz); }));
  $("#mggo")?.addEventListener("change", (e) => { const r = regions[+e.target.value]; if (r) { fitBox(r.slice(1)); redraw(); } e.target.value = ""; });
  const side = (i) => {
    const p = pts[i], c = cats[p.c], on = got.has(gkey(p));
    const gotBtn = p.t === "sp" ? "" : `<p><button class="btn gotbtn${on ? " on" : ""}" id="gotbtn">${on ? "✓ gefunden" : "als gefunden markieren"}</button></p>`;
    let body = "";
    if (p.t === "sp") body = `<table class="rows"><tr><th></th><th>Pokémon</th><th>Anteil</th><th>Tageszeit</th><th>Wetter</th></tr>${p.mons.map((m) => `<tr><td>${img(m.id, "sm")}</td>
      <td><a href="#pokemon/${m.id}">${m.alpha ? `<span class="alpha">Alpha</span> ` : ""}${esc(m.name)}</a></td><td>bis ${mpct(m.max)}</td><td>${esc(m.zeit)}</td><td>${esc(m.wetter)}</td></tr>`).join("")}</table>`;
    else if (p.t === "ob") body = p.o.items.length ? `<table class="rows">${p.o.items.map(([n, t, id]) => `<tr><td>${id ? img(id, "sm") : ""}</td><td>${id ? `<a href="#pokemon/${id}">${esc(n)}</a>` : wikiLink(n)}</td><td>${esc(t)}</td></tr>`).join("")}</table>`
      + (p.o.menge ? `<p class="hint">${esc(p.o.menge)} Stück je Mal.</p>` : "") : `<p class="hint">${esc(MOBJHINT[p.o.art] || "")}</p>`;
    else body = p.text ? `<p class="mgdesc">${esc(p.text)}</p>` : "";
    $("#mapside").innerHTML = `<h3>${dot(c)} ${esc(p.t === "sp" ? (p.alpha ? "Alpha-Spawnpunkt" : "Spawnpunkt") : p.name || c.titel)}</h3>
      <p class="hint">${esc(c.g.titel)} · ${esc(c.titel)}${p.k && own ? " · " + esc(own.gebiete[p.k] || "") : ""}</p>${gotBtn}${body}`;
    $("#gotbtn")?.addEventListener("click", () => toggle(i));
  };
  const listHits = () => {
    if (!q) return;
    const hits = pts.map((p, i) => [p, i]).filter(([p]) => !hide.has(p.c) && match(p));
    $("#mapside").innerHTML = `<h3>${hits.length} Treffer</h3>` + (hits.length > 60 ? `<p class="hint">Zu viele für eine Liste; genauer suchen.</p>` :
      `<div class="mghits">${hits.map(([p, i]) => `<button data-jump="${i}">${dot(cats[p.c])}<span>${esc(p.t === "sp" ? "Spawnpunkt: " + p.name : p.name || cats[p.c].titel)}</span></button>`).join("")}</div>`);
    $$("[data-jump]").forEach((b) => b.addEventListener("click", () => jump(+b.dataset.jump)));
  };
  const toggle = (i) => {
    const p = pts[i], k = gkey(p);
    if (!k) return;
    const on = !got.has(k);
    if (on) got.add(k); else got.delete(k);
    const c = $(`[data-cnt="${CSS.escape(String(p.c))}"]`);
    if (c) c.innerHTML = cnt(cats[p.c]);
    pins();
    if (sel === i) side(i);
    const [karte, objekt] = k.split("|");
    api("/api/gefunden", {spiel: d.spiel, karte, objekt, an: on}).catch(() => { if (on) got.delete(k); else got.add(k); pins(); });
  };
  pl.addEventListener("click", (e) => {
    if (moved) return;
    const b = e.target.closest("[data-i]");
    if (!b) return;
    $$(".sel", pl).forEach((x) => x.classList.remove("sel"));
    b.classList.add("sel");
    sel = +b.dataset.i; side(sel);
  });
  pl.addEventListener("contextmenu", (e) => { const b = e.target.closest("[data-i]"); if (!b) return; e.preventDefault(); toggle(+b.dataset.i); });
  const catKey = (v) => (isNaN(+v) ? v : +v);
  const saveHide = () => { store.set(hk, [...hide]); $$("[data-cat]").forEach((b) => b.classList.toggle("on", !hide.has(catKey(b.dataset.cat)))); pins(); };
  $$("[data-cat]").forEach((b) => b.addEventListener("click", () => { const k = catKey(b.dataset.cat); if (hide.has(k)) hide.delete(k); else hide.add(k); saveHide(); }));
  $$("summary [data-grp]").forEach((b) => b.addEventListener("click", (e) => {
    e.preventDefault();
    const ks = groups[+b.dataset.grp].kategorien.map((c) => c.id), anyOn = ks.some((k) => !hide.has(k));
    ks.forEach((k) => { if (anyOn) hide.add(k); else hide.delete(k); });
    saveHide();
  }));
  $$("[data-all]").forEach((b) => b.addEventListener("click", () => { Object.values(cats).forEach((c) => { if (b.dataset.all === "1") hide.delete(c.id); else hide.add(c.id); }); saveHide(); }));
  $$("details.mgg").forEach((x) => x.addEventListener("toggle", () => { if (x.open) open.add(x.dataset.gid); else open.delete(x.dataset.gid); store.set("mgOpen", [...open]); }));
  $("#gothide").addEventListener("change", (e) => { gotHide = e.target.checked; store.set("mapGotHide", gotHide); pins(); });
  let qt;
  $("#mgq").addEventListener("input", (e) => { clearTimeout(qt); qt = setTimeout(() => { q = e.target.value.trim(); pins(); listHits(); }, 150); });
  // #karte/mg/<Karte>/<Ort>: direkt dorthin
  if (want) { const i = pts.findIndex((p) => p.t === "mg" && String(p.id) === String(want)); if (i >= 0) jump(i); }
}
async function areasView(want) {
  const rid = RID;
  const d = await api("/api/gebiete?" + qs({spiel: S.game})).catch(() => null);
  if (rid !== RID) return;
  if (!d || !d.gebiete.length) {
    main.innerHTML = `<div class="box"><h2>Gebiete</h2><p class="hint">Für ${esc(gameName())} gibt es keine Fundorte in den Daten.</p>
      <p><a href="#karte/obsidianfieldlands">Karte von Legenden: Arceus öffnen</a></p></div>`;
    return;
  }
  const key = "gebiet:" + S.game;
  let sel = want ? decodeURIComponent(want) : store.get(key, d.gebiete[0].ort), q = "", miss = store.get("gebietFehlend", false);
  if (!d.gebiete.some((g) => g.ort === sel)) sel = d.gebiete[0].ort;
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Gebiete</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      <input id="gq" type="search" placeholder="Ort oder Pokémon" style="width:220px">
      <label data-tip="Pokémon, die du in diesem Spiel schon gefangen hast, ausblenden"><input type="checkbox" id="gmiss"${miss ? " checked" : ""}> nur noch nicht gefangene</label>
      ${S.game === "legends-arceus" ? `<a class="btn" href="#karte/obsidianfieldlands">Zur Karte</a>` : ""}<span class="hint grow">${d.gebiete.length} Orte</span></div>
    <div class="gwrap"><nav class="glist" id="glist"></nav><div class="gmain" id="gmain"></div></div>
    <p class="hint">Quelle: ${d.quelle === "PKHeX" ? "Spieldaten (PKHeX)" : "PokéAPI"}. Anteil: so oft erscheint es mit dieser Methode (Summe der Plätze).</p></div>`;
  header();
  const own = (m) => isCaught(m.id);
  const list = () => {
    const ql = q.toLowerCase();
    $("#glist").innerHTML = d.gebiete.filter((g) => !ql || g.ort.toLowerCase().includes(ql) || g.mons.some((m) => m.name.toLowerCase().includes(ql)))
      .map((g) => { const ids = new Set(g.mons.map((m) => m.id)), left = [...ids].filter((i) => !isCaught(i)).length;
        return `<button class="${g.ort === sel ? "on" : ""}" data-g="${esc(g.ort)}"><span>${esc(g.ort)}</span><span class="hint" data-tip="noch nicht gefangen / Pokémon">${left ? left + "/" : "✓ "}${ids.size}</span></button>`; }).join("")
      || `<p class="hint">Nichts gefunden.</p>`;
    $$("#glist [data-g]").forEach((b) => b.addEventListener("click", () => { sel = b.dataset.g; store.set(key, sel); list(); show(); }));
  };
  const show = () => {
    const g = d.gebiete.find((x) => x.ort === sel);
    const ms = g.mons.filter((m) => !miss || !own(m));
    const by = {};
    ms.forEach((m) => (by[m.methode || "–"] ||= []).push(m));
    $("#gmain").innerHTML = `<h3>${areaName(g.ort)}</h3>` + (Object.entries(by).map(([meth, xs]) => `<h4>${esc(meth)}</h4><div class="ggrid">${xs.map((m) =>
      `<a class="gmon${own(m) ? " got" : ""}" href="#pokemon/${m.id}" data-id="${m.id}">${img(m.id)}${own(m) ? `<span class="gball">${ball(m.id)}</span>` : ""}<b>${esc(m.name)}</b>
        <span class="hint">${m.level ? "Lv " + esc(m.level) : ""}${m.anteil ? ` · ${m.anteil} %` : ""}${m.alpha ? ` · <span class="alpha">Alpha</span>` : ""}</span>
        ${m.editionen.length ? `<span class="ged">nur ${esc(m.editionen.join(", "))}</span>` : ""}${m.bedingungen.length ? `<span class="hint">${esc(m.bedingungen.join(", "))}</span>` : ""}</a>`).join("")}</div>`).join("")
      || `<p class="hint">${miss ? "Hier hast du schon alles gefangen." : "Keine Pokémon."}</p>`);
  };
  $("#gq").addEventListener("input", (e) => { q = e.target.value.trim(); list(); });
  $("#gmiss").addEventListener("change", (e) => { miss = e.target.checked; store.set("gebietFehlend", miss); list(); show(); });
  list(); show();
  const on = $("#glist .on"), gl = $("#glist");
  if (on) gl.scrollTop = on.offsetTop - gl.offsetTop - gl.clientHeight / 2;     // nur die Liste scrollen, nicht die Seite
}
async function mapView(karte, fid) {
  const rid = RID;
  const key = karte || "obsidianfieldlands";
  const d = MAPCACHE[key] || (MAPCACHE[key] = await api("/api/karte/" + encodeURIComponent(key)));
  /* gefundene Symbole (Geisterlichter, Icognito, Kisten …): je Karte; Schlüssel Art:x:z, damit er einen Neubau übersteht */
  const gotRes = await api("/api/gefunden?" + qs({spiel: MAPSPIEL, karte: key})).catch(() => ({}));
  if (rid !== RID) return;
  if (!$("#map")) window.scrollTo(0, 0);
  const got = new Set(gotRes[key] || []);
  let gotHide = store.get("mapGotHide", false);
  /* Tageszeit und Wetter: -1 = alle; der Anteil eines Pokémon ist dann der höchste unter den gewählten Bedingungen */
  const fz = store.get("mapZeit", -1), fw = store.get("mapWetter", -1), cond = fz >= 0 || fw >= 0;
  const sh = (m) => !cond || !m.c ? m.max || 0 : Math.max(0, ...m.c.filter((v, i) => (fz < 0 || Math.floor(i / 9) === fz) && (fw < 0 || i % 9 === fw)));
  const pts = d.punkte.map((p) => Object.assign(p, {hit: fid != null && p.mons.some((m) => m.id === fid && sh(m) > 0), off: cond && !p.mons.some((m) => sh(m) > 0)}));
  const species = {};
  pts.forEach((p) => p.mons.forEach((m) => { (species[m.id] ||= {id: m.id, name: m.name, n: 0}).n++; }));
  const hits = pts.filter((p) => p.hit).length;
  const objs = (d.objekte || []).map((o) => Object.assign(o, {hit: fid != null && MOBJMON.has(o.art) && o.items.some((e) => e[2] === fid)}));
  objs.forEach((o) => { if (MOBJMON.has(o.art)) o.items.forEach(([n, , id]) => { if (id) (species[id] ||= {id, name: n.replace(/ \(.*\)$/, ""), n: 0}).n++; }); });
  const list = Object.values(species).sort((a, b) => a.name.localeCompare(b.name, "de"));
  const arten = d.arten || {};
  const ohits = objs.filter((o) => o.hit).length;
  const hide = new Set(store.get("mapHide", ["boden"]));      // Items am Boden sind viele: anfangs aus
  let heatOn = store.get("mapHeat", false);
  const H = mapHeat(pts, objs, sh);
  const layerBtn = (k, label, n) => `<button class="mlay${hide.has(k) ? "" : " on"}" data-lay="${k}" data-tip="${hide.has(k) ? "einblenden" : "ausblenden"}">${k === "pokemon"
    ? `<span class="mpin-l"></span>` : `<span class="mobj o-${k}">${MOBJ[k] || "•"}</span>`}${esc(label)} <span class="hint" data-cnt="${k}">${cnt(k, n)}</span></button>`;
  const cnt = (k, n) => { const f = k === "pokemon" ? 0 : objs.filter((o) => o.art === k && got.has(okey(o))).length; return f ? `${f}/${n} ✓` : n; };
  const lays = [...(pts.length ? [["pokemon", "Spawnpunkte", pts.length]] : []), ...Object.entries(arten).map(([k, v]) => [k, v[1], objs.filter((o) => o.art === k).length])];
  const known = new Set(MGROUPS.flatMap((g) => g[1]));
  const groups = [...MGROUPS.map(([n, ks]) => [n, ks.map((k) => lays.find((l) => l[0] === k)).filter(Boolean)]), ["Weitere", lays.filter((l) => !known.has(l[0]))]].filter((g) => g[1].length);
  const layerBar = groups.map(([n, ls], gi) => `<span class="mgrp"><button class="mgrp-b" data-grp="${gi}" data-tip="ganze Gruppe ein- oder ausblenden">${esc(n)}</button>${ls.map((l) => layerBtn(...l)).join("")}</span>`).join("");
  const hasCond = pts.some((p) => p.mons.some((m) => m.c));
  const condSel = (key, label, names, v) => `<label class="mcond">${label} <select data-cond="${key}"><option value="-1">alle</option>${names.map((x, i) => `<option value="${i}"${i === v ? " selected" : ""}>${esc(x)}</option>`).join("")}</select></label>`;
  main.innerHTML = `<div class="box mapbox">
    <div class="bar"><h2 style="margin:0">Karte</h2>
      <span class="seg">${d.karten.map((k) => `<a class="btn${k.karte === d.karte ? " on" : ""}" href="#karte/${k.karte}${fid != null ? "/" + fid : ""}">${esc(k.gebiet)}</a>`).join("")}</span>
      <a class="btn" href="#karte/gebiete" data-tip="Alle Orte mit ihren Pokémon als Liste">Gebiete</a>
      <a class="btn" href="#karte/mg" data-tip="Karte von Map Genie mit Orten, Sammelobjekten und Materialien (wenn geladen)">Map Genie</a>
      ${pts.length ? `<div class="pick" id="mapmon"><button class="pickbtn" aria-haspopup="true" aria-expanded="false">${fid != null && species[fid] ? img(fid) + `<b>${esc(species[fid].name)}</b>` : "Pokémon wählen"} <span class="hint">▾</span></button>
        <div class="pickm" hidden><input type="search" placeholder="Pokémon suchen" aria-label="Pokémon suchen">
          <div class="pickl"><a href="#karte/${d.karte}" class="${fid == null ? "on" : ""}"><span class="spr none"></span><span>alle Spawnpunkte</span><span class="hint">${pts.length}</span></a>${list.map((s) => `<a href="#karte/${d.karte}/${s.id}" class="${s.id === fid ? "on" : ""}" data-n="${esc(s.name.toLowerCase())}">${img(s.id)}<span>${esc(s.name)}</span><span class="hint" data-tip="Stellen in diesem Gebiet">${s.n}</span></a>`).join("")}</div></div></div>
      <span class="hint grow">${fid != null ? (hits || ohits ? [hits && `${hits} Spawnpunkte`, ohits && `${ohits} weitere Stellen`].filter(Boolean).join(" und ") + " hervorgehoben" : "hier an keinem Spawnpunkt") : `${pts.length} Spawnpunkte, davon ${pts.filter((p) => p.alpha).length} Alpha`}</span>` : ""}
</div>
    ${objs.length || pts.length ? `<div class="bar mlays">${pts.length ? `<button class="mlay heatbtn${heatOn ? " on" : ""}" id="heatbtn" data-tip="Wo es welche Pokémon gibt: Bilder je Kartenfeld, je größer, desto wahrscheinlicher">▦ Übersicht mit Bildern</button>` : ""}${hasCond ? condSel("mapZeit", "Tageszeit", d.zeiten || [], fz) + condSel("mapWetter", "Wetter", d.wetterarten || [], fw) : ""}
      ${objs.length ? `<label class="mgot" data-tip="Symbole, die du als gefunden markiert hast (Rechtsklick auf ein Symbol oder ✓ in den Details), ausblenden"><input type="checkbox" id="gothide"${gotHide ? " checked" : ""}> gefundene ausblenden</label>` : ""}
      <span class="mlay-all"><button class="link" data-layall="1" data-tip="alle Ebenen einblenden">alle</button> · <button class="link" data-layall="0" data-tip="alle Ebenen ausblenden">keine</button></span></div>
    <div class="bar mlays mgrps">${layerBar}</div>` : ""}
    ${S.game && S.game !== "legends-arceus" ? `<div class="note info">Für ${esc(gameName())} gibt es noch keine Karte; gezeigt ist Legenden: Arceus. <a href="#karte/gebiete">Gebiete von ${esc(gameName())}</a></div>` : ""}
    ${d.kacheln || d.bild ? "" : `<div class="note">Das Kartenbild fehlt noch; der nächste Abgleich lädt es (Einstellungen → Abgleich). Die Spawnpunkte stimmen trotzdem.</div>`}
    <div class="mapwrap"><div class="mapcol"><div id="map" class="map"><div class="mapin"><div class="tiles"></div><div class="pins"></div></div></div>
      <div class="mapzoom"><button data-mz="1" data-tip="näher">+</button><button data-mz="-1" data-tip="weiter weg">−</button><button data-mz="0" data-tip="ganze Karte">⤢</button></div></div>
      <aside id="mapside" class="mapside"><p class="hint">${pts.length ? "Fahre über einen Punkt für die Pokémon dort, klicke für Details. Rot: Alpha." : "Fahre über ein Symbol für Einzelheiten, klicke für die Liste."}${objs.length ? " Rechtsklick auf ein Symbol markiert es als gefunden." : ""}</p></aside></div>
    <p class="hint">Kartenbild: ${d.bild ? "Altissimo" : "Serebii"}${pts.length ? "; Spawnpunkte und Tabellen: PLA-Live-Map und JS-Finder (GPL-3.0), aus den Spieldaten" : ""}${objs.length ? "; Symbole und Sammelobjekte: Altissimo (GPL-3.0)" : ""}${objs.some((o) => MOBJMON.has(o.art) || o.art === "boden") ? "; Kristalle, Verzerrungen, Massenauftreten, Bäume, Alphas und Items am Boden: PokéWiki (CC BY-SA 3.0)" : ""}${objs.some((o) => o.art === "reise" || o.art === "lager") ? "; Schnellreise und Lager: PLA Companion (software-notion.de)" : ""}.</p></div>`;
  const pick = $("#mapmon") || document.createElement("div"), pickM = $(".pickm", pick) || document.createElement("div");
  const pickOpen = (on) => { pickM.hidden = !on; $(".pickbtn", pick).setAttribute("aria-expanded", on); if (on) { const f = $("input", pickM); f.value = ""; pickFilter(""); f.focus(); $("a.on", pickM)?.scrollIntoView({block: "center"}); } };
  const pickFilter = (v) => $$(".pickl a[data-n]", pick).forEach((a) => { a.hidden = !!v && !a.dataset.n.includes(v); });
  $(".pickbtn", pick)?.addEventListener("click", () => pickOpen(pickM.hidden));
  $("input", pickM)?.addEventListener("input", (e) => pickFilter(e.target.value.trim().toLowerCase()));
  pick.addEventListener("keydown", (e) => {
    if (e.key === "Escape") pickOpen(false);
    else if (e.key === "Enter" && e.target.tagName === "INPUT") { const a = $$(".pickl a[data-n]", pick).find((x) => !x.hidden); if (a) location.hash = a.getAttribute("href"); }
  });
  document.addEventListener("click", function away(e) { if (!document.body.contains(pick)) document.removeEventListener("click", away); else if (!pick.contains(e.target)) pickOpen(false); });
  const box = $("#map"), inner = $(".mapin", box), tiles = $(".tiles", box), pins = $(".pins", box);
  // Übersicht: Bilder je Feld (eigene Ebene unter den Punkten); mit gewähltem Pokémon nur dieses
  const heatEl = document.createElement("div"); heatEl.className = "heat"; pins.before(heatEl);
  const wmax = Math.max(0.01, ...Object.values(H.cells).flatMap((c) => Object.values(c).map((s) => s.w)));
  heatEl.innerHTML = Object.values(H.cells).map((c) => {
    const xs = Object.values(c).filter((s) => fid == null || s.id === fid).sort((a, b) => b.w - a.w);
    const top = xs[0]?.w || 0;
    return xs.filter((s, i) => i < 3 && s.w >= top * 0.3).map((s) => { const px = Math.round(44 + 90 * Math.sqrt(s.w / wmax));
      return `<a class="hspr" draggable="false" href="#karte/${d.karte}/${s.id}" style="left:${s.sx / s.sw * 2}px;top:${s.sz / s.sw * 2}px;width:${px}px;height:${px}px;margin:-${px / 2}px 0 0 -${px / 2}px" data-tip="${esc(heatTip(s))}">${img(s.id)}</a>`; }).join("");
  }).join("");
  const heatSide = async () => {
    const side = $("#mapside");
    if (fid == null) {
      const xs = Object.values(H.tot).sort((a, b) => b.w - a.w).slice(0, 30), m = xs[0]?.w || 1;
      side.innerHTML = `<h3>Häufig in ${esc(d.gebiet || "")}</h3><table class="rows heatl">${xs.map((s) => `<tr><td>${img(s.id, "sm")}</td><td><a href="#karte/${d.karte}/${s.id}">${esc(s.name)}</a>
        <span class="hbar"><i style="width:${Math.max(3, s.w / m * 100)}%"></i></span></td><td class="num hint" data-tip="Stellen in diesem Gebiet">${s.n}</td></tr>`).join("")}</table>
        <p class="hint">Balken: Summe der Anteile über alle Spawnpunkte und Stellen; ein Maß dafür, wie viele man hier antrifft. Klick wählt das Pokémon.</p>`;
      return;
    }
    side.innerHTML = `<h3>${img(fid, "sm")} ${esc(species[fid]?.name || "")} in allen Gebieten</h3><p class="hint">Lädt …</p>`;
    const all = await Promise.all(d.karten.map(async (k) => MAPCACHE[k.karte] || (MAPCACHE[k.karte] = await api("/api/karte/" + encodeURIComponent(k.karte)))));
    if (rid !== RID || !document.body.contains(side)) return;
    const rows = all.map((m) => { const t = mapHeat(m.punkte || [], m.objekte || [], sh).tot[fid]; return {k: m.karte, g: m.gebiet, w: t?.w || 0, n: t?.n || 0}; }).sort((a, b) => b.w - a.w);
    const m = rows[0]?.w || 1;
    side.innerHTML = `<h3>${img(fid, "sm")} ${esc(species[fid]?.name || "")} in allen Gebieten</h3><table class="rows heatl">${rows.map((r) => `<tr${r.k === d.karte ? ` class="on"` : ""}><td>${r.n
      ? `<a href="#karte/${r.k}/${fid}">${esc(r.g)}</a>` : `<span class="hint">${esc(r.g)}</span>`}<span class="hbar"><i style="width:${r.w ? Math.max(3, r.w / m * 100) : 0}%"></i></span></td><td class="num hint">${r.n || "–"}</td></tr>`).join("")}</table>
      <p class="hint">Je länger der Balken, desto mehr trifft man es dort an (Summe der Anteile); die Zahl: Stellen. <a href="#karte/${d.karte}">Alle Pokémon zeigen</a></p>`;
  };
  const showHeat = () => { heatEl.hidden = !heatOn; $("#heatbtn")?.classList.toggle("on", heatOn); if (heatOn) heatSide(); };
  $("#heatbtn")?.addEventListener("click", () => { heatOn = !heatOn; store.set("mapHeat", heatOn); showHeat(); });
  showHeat();
  const tipOf = (p) => (p.alpha ? "Alpha-Spawnpunkt\n" : "") + (p.mons.length ? p.mons.filter((m) => sh(m) > 0).map((m) => `${m.alpha ? "Alpha-" : ""}${m.name}: bis ${mpct(sh(m))}`
    + (!cond && m.zeit !== "immer" ? ` (${m.zeit})` : "")).join("\n") || "zu dieser Zeit und bei diesem Wetter nichts" : "keine Angaben");
  pins.innerHTML = pts.map((p, i) => `<button class="mpin${p.alpha ? " alpha" : ""}${p.hit ? " hit" : ""}${(fid != null && !p.hit) || p.off ? " dim" : ""}" data-i="${i}"
    style="left:${p.x * 2}px;top:${p.z * 2}px" data-tip="${esc(tipOf(p))}" aria-label="Spawnpunkt"></button>`).join("")
    + objs.map((o, i) => `<button class="mobj o-${o.art}${o.hit ? " hit" : ""}${got.has(okey(o)) ? " got" : ""}" data-o="${i}" style="left:${o.x * 2}px;top:${o.z * 2}px" data-tip="${esc(mobjTip(o, arten))}"
      aria-label="${esc(arten[o.art]?.[0] || o.art)}">${MOBJ[o.art] || "•"}</button>`).join("");
  const showLayers = () => {
    $$(".mpin", pins).forEach((b) => { b.hidden = hide.has("pokemon"); });
    $$(".mobj[data-o]", pins).forEach((b) => { const o = objs[+b.dataset.o]; b.hidden = hide.has(o.art) || (gotHide && got.has(okey(o))); });
  };
  showLayers();
  const toggleGot = (i) => {
    const o = objs[i], k = okey(o), on = !got.has(k);
    if (on) got.add(k); else got.delete(k);
    $(`.mobj[data-o="${i}"]`, pins)?.classList.toggle("got", on);
    const c = $(`[data-cnt="${o.art}"]`);
    if (c) c.innerHTML = cnt(o.art, objs.filter((x) => x.art === o.art).length);
    const gb = $("#gotbtn");
    if (gb && +gb.dataset.o === i) { gb.classList.toggle("on", on); gb.textContent = on ? "✓ gefunden" : "als gefunden markieren"; }
    showLayers();
    api("/api/gefunden", {spiel: MAPSPIEL, karte: key, objekt: k, an: on}).catch(() => {
      if (on) got.delete(k); else got.add(k);        // nicht gespeichert: zurück
      $(`.mobj[data-o="${i}"]`, pins)?.classList.toggle("got", !on);
      showLayers();
    });
  };
  $("#gothide")?.addEventListener("change", (e) => { gotHide = e.target.checked; store.set("mapGotHide", gotHide); showLayers(); });
  pins.addEventListener("contextmenu", (e) => {
    const ob = e.target.closest(".mobj[data-o]");
    if (!ob) return;
    e.preventDefault();
    toggleGot(+ob.dataset.o);
  });
  const layBtns = () => $$(".mlay[data-lay]").forEach((b) => { b.classList.toggle("on", !hide.has(b.dataset.lay)); b.dataset.tip = hide.has(b.dataset.lay) ? "einblenden" : "ausblenden"; });
  $$(".mlay[data-lay]").forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.lay;
    if (hide.has(k)) hide.delete(k); else hide.add(k);
    store.set("mapHide", [...hide]);
    layBtns(); showLayers();
  }));
  $$("[data-layall]").forEach((b) => b.addEventListener("click", () => {
    $$(".mlay[data-lay]").forEach((x) => { if (b.dataset.layall === "1") hide.delete(x.dataset.lay); else hide.add(x.dataset.lay); });
    store.set("mapHide", [...hide]);
    layBtns(); showLayers();
  }));
  $$("[data-grp]").forEach((b) => b.addEventListener("click", () => {
    const ks = groups[+b.dataset.grp][1].map((l) => l[0]), anyOn = ks.some((k) => !hide.has(k));
    ks.forEach((k) => { if (anyOn) hide.add(k); else hide.delete(k); });
    store.set("mapHide", [...hide]);
    layBtns(); showLayers();
  }));
  $$("[data-cond]").forEach((s) => s.addEventListener("change", () => {
    store.set(s.dataset.cond, +s.value);
    MAPPOS = {key, fid, scale, ox, oy};
    mapView(karte, fid);
  }));
  let scale = 1, ox = 0, oy = 0, level = -1;
  const fit = () => {
    const r = box.getBoundingClientRect(), on = [...pts.filter((p) => p.hit), ...objs.filter((o) => o.hit)];
    if (on.length) {
      const xs = on.map((p) => p.x * 2), ys = on.map((p) => p.z * 2), pad = 140;
      const w = Math.max(...xs) - Math.min(...xs) + pad * 2, h = Math.max(...ys) - Math.min(...ys) + pad * 2;
      scale = Math.min(1.5, r.width / w, r.height / h);
      ox = r.width / 2 - (Math.min(...xs) + Math.max(...xs)) / 2 * scale;
      oy = r.height / 2 - (Math.min(...ys) + Math.max(...ys)) / 2 * scale;
    } else {
      scale = Math.min(r.width, r.height) / WORLD;
      ox = (r.width - WORLD * scale) / 2; oy = (r.height - WORLD * scale) / 2;
    }
  };
  /* Kacheln: je Zoomstufe eine Ebene, gröbere bleiben darunter liegen (nichts wird leer, während feinere laden);
     geladen wird nur, was im Ausschnitt liegt */
  const layers = [0, 1, 2].map((z) => { const el = document.createElement("div"); el.dataset.z = z; tiles.appendChild(el); return {el, have: new Set()}; });
  if (d.bild) {          // Jubeldorf: ein Bild für die ganze Karte statt Kacheln
    const im = new Image();
    im.alt = ""; im.draggable = false; im.decoding = "async";
    im.style.cssText = `left:0;top:0;width:${WORLD}px;height:${WORLD}px`;
    im.src = `karten/${d.karte}/bild.png`;
    tiles.appendChild(im);
  }
  const draw = () => {
    const z = scale < 0.3 ? 0 : scale < 0.6 ? 1 : 2;
    level = z;
    const r = box.getBoundingClientRect();
    for (let k = 0; k <= z; k++) {
      if (d.bild || (k !== 0 && k !== z)) continue;          // die gröbste als Unterlage, dazu die passende
      const n = 2 ** (k + 1), size = WORLD / n, L = layers[k];
      const x0 = Math.max(0, Math.floor(-ox / scale / size)), x1 = Math.min(n - 1, Math.floor((r.width - ox) / scale / size));
      const y0 = Math.max(0, Math.floor(-oy / scale / size)), y1 = Math.min(n - 1, Math.floor((r.height - oy) / scale / size));
      for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) {
        const key = `${x}-${y}`;
        if (L.have.has(key)) continue;
        L.have.add(key);
        const im = new Image();
        im.alt = ""; im.draggable = false; im.decoding = "async";
        im.style.cssText = `left:${x * size}px;top:${y * size}px;width:${size}px;height:${size}px`;
        im.onerror = () => { im.style.visibility = "hidden"; };
        im.src = `karten/${d.karte}/${k}-${x}-${y}.png`;
        L.el.appendChild(im);
      }
    }
    layers.forEach((L, k) => { L.el.hidden = k > z; });
    inner.style.transform = `translate(${ox}px,${oy}px) scale(${scale})`;
    inner.style.setProperty("--inv", 1 / scale);
  };
  const zoomAt = (f, cx, cy) => {
    const ns = Math.max(0.15, Math.min(4, scale * f));
    ox = cx - (cx - ox) * ns / scale; oy = cy - (cy - oy) * ns / scale; scale = ns; draw();
  };
  if (MAPPOS && MAPPOS.key === key && MAPPOS.fid === fid) ({scale, ox, oy} = MAPPOS); else fit();
  MAPPOS = null;
  draw();
  box.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = box.getBoundingClientRect();
    zoomAt(e.deltaY < 0 ? 1.25 : 0.8, e.clientX - r.left, e.clientY - r.top);
  }, {passive: false});
  $$("[data-mz]").forEach((b) => b.addEventListener("click", () => {
    const r = box.getBoundingClientRect();
    if (b.dataset.mz === "0") { fit(); draw(); return; }
    zoomAt(b.dataset.mz === "1" ? 1.4 : 1 / 1.4, r.width / 2, r.height / 2);
  }));
  let drag = null, moved = false;
  box.addEventListener("dragstart", (e) => e.preventDefault());
  box.addEventListener("pointerdown", (e) => {
    if (e.button || e.target.closest(".mapzoom")) return;
    drag = {x: e.clientX, y: e.clientY, ox, oy, id: e.pointerId};
    moved = false;
  });
  box.addEventListener("pointermove", (e) => {
    if (!drag) return;
    if (!moved && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) > 4) {
      moved = true;
      box.setPointerCapture(drag.id);
      box.classList.add("grab");
    }
    if (moved) { ox = drag.ox + e.clientX - drag.x; oy = drag.oy + e.clientY - drag.y; draw(); }
  });
  box.addEventListener("click", (e) => { if (moved) { e.preventDefault(); e.stopPropagation(); moved = false; } }, true);
  const stop = () => { drag = null; box.classList.remove("grab"); };
  box.addEventListener("pointerup", stop);
  box.addEventListener("pointercancel", stop);
  pins.addEventListener("click", (e) => {
    const ob = e.target.closest(".mobj[data-o]");
    if (ob) {
      $$(".sel", pins).forEach((x) => x.classList.remove("sel"));
      ob.classList.add("sel");
      const o = objs[+ob.dataset.o];
      const mon = MOBJMON.has(o.art);
      const isGot = got.has(okey(o));
      $("#mapside").innerHTML = `<h3><span class="mobj o-${o.art}">${MOBJ[o.art] || "•"}</span> ${esc(arten[o.art]?.[0] || o.art)}${o.nr ? " " + o.nr : ""}</h3>`
        + `<p><button class="btn gotbtn${isGot ? " on" : ""}" id="gotbtn" data-o="${ob.dataset.o}" data-tip="Merken, dass du das schon hast (auch per Rechtsklick auf das Symbol)">${isGot ? "✓ gefunden" : "als gefunden markieren"}</button></p>`
        + (mon ? `<table class="rows"><tr><th></th><th>Pokémon</th><th>${o.art === "alpha" ? "Level" : "Level, Anteil"}</th></tr>${o.items.map(([n, t, id]) => `<tr${id === fid ? ` class="on"` : ""}><td>${id ? img(id, "sm") : ""}</td>
            <td>${id ? `<a href="#pokemon/${id}">${esc(n)}</a>` : esc(n)}</td><td>${esc(t)}</td></tr>`).join("")}</table><p class="hint">${esc(MOBJHINT[o.art] || "")}</p>`
        : o.items.length ? `<table class="rows"><tr><th>Item</th><th class="c">Anteil</th></tr>${o.items.map(([n, p]) => `<tr><td>${wikiLink(n)}</td><td class="c num">${esc(p)}</td></tr>`).join("")}</table>`
          + (o.menge ? `<p class="hint">${esc(o.menge)} Stück je Mal; Anteil: so oft ist es dieses Item.</p>` : "") : `<p class="hint">${esc(MOBJHINT[o.art] || "")}</p>`);
      $("#gotbtn").addEventListener("click", () => toggleGot(+ob.dataset.o));
      return;
    }
    const b = e.target.closest(".mpin");
    if (!b) return;
    $$(".sel", pins).forEach((x) => x.classList.remove("sel"));
    b.classList.add("sel");
    const p = pts[+b.dataset.i];
    $("#mapside").innerHTML = `<h3>${p.alpha ? "Alpha-Spawnpunkt" : "Spawnpunkt"}</h3>` + (p.mons.length ? `<table class="rows"><tr><th></th><th>Pokémon</th><th>Anteil</th><th>Tageszeit</th><th>Wetter</th></tr>
      ${p.mons.map((m) => `<tr${cond && !(sh(m) > 0) ? ` class="dim"` : ""}><td>${img(m.id, "sm")}</td><td><a href="#pokemon/${m.id}">${m.alpha ? `<span class="alpha">Alpha</span> ` : ""}${esc(m.name)}</a></td>
        <td>${cond ? (sh(m) > 0 ? "bis " + mpct(sh(m)) : "–") : "bis " + mpct(m.max)}</td><td>${esc(m.zeit)}</td><td>${esc(m.wetter)}</td></tr>`).join("")}</table>` : `<p class="hint">keine Angaben</p>`)
      + `<p class="hint">Anteil: so oft erscheint es an diesem Punkt unter den passenden Bedingungen (höchster Wert${cond ? ", nur zur gewählten Tageszeit und beim gewählten Wetter" : ""}).</p>`;
  });
}

// Items des Spiels: Suche, Tasche und Art. Je Tasche passende Spalten (Wirkung bei Medizin und Bällen, die Attacke bei
// Maschinen); unfertige Einträge (Platzhalter im Text) nur auf Wunsch.
const MKLASSE = {1: "Status", 2: "physisch", 3: "speziell"};
const HERSTELLEN = "herstellen";      // Ansicht der Items mit Rezept (Legenden: Arceus)
const itemImg = (x) => x.bild ? `<img class="ibild" src="itembild/${x.id}" alt="" loading="lazy">`
  : `<span class="ibild none">${x.attacke ? "TM" : ""}</span>`;
/* Bälle: Fangfaktor und Bedingung. Hauptreihe nach den bekannten Werten; Legenden: Arceus rechnet anders (Richtwerte,
   die Quellen sind sich nicht überall einig). [Faktor, Bedingung]; Faktor 0 = fängt immer */
const BALL = {"Pokéball": [1, ""], "Superball": [1.5, ""], "Hyperball": [2, ""], "Meisterball": [0, "fängt immer"], "Safariball": [1.5, "nur in der Safari-Zone"],
  "Netzball": [3.5, "×3,5 gegen Wasser und Käfer, sonst ×1"], "Tauchball": [3.5, "×3,5 beim Surfen, Angeln oder unter Wasser"], "Nestball": [4, "bis ×4 bei niedrigem Level"],
  "Wiederball": [3.5, "×3,5, wenn die Art schon gefangen ist"], "Timerball": [4, "steigt je Runde, bis ×4 ab Runde 11"], "Luxusball": [1, "Freundschaft wächst schneller"],
  "Premierball": [1, ""], "Finsterball": [3, "×3 nachts und in Höhlen"], "Heilball": [1, "heilt das gefangene Pokémon"], "Flottball": [5, "×5 in der ersten Runde"],
  "Jubelball": [1, ""], "Turboball": [4, "×4 bei Initiative ab 100"], "Levelball": [8, "bis ×8, wenn das eigene Pokémon viel höher ist"], "Köderball": [4, "×4 bei geangelten Pokémon"],
  "Schwerball": [1, "besser bei schweren Pokémon"], "Sympaball": [8, "×8 bei gleicher Art und anderem Geschlecht"], "Freundesball": [1, "startet mit hoher Freundschaft"],
  "Mondball": [4, "×4 bei Pokémon, die sich mit Mondstein entwickeln"], "Turnierball": [1.5, "nur beim Käferturnier"], "Parkball": [0, "fängt immer (Park)"],
  "Traumball": [4, "×4 bei schlafenden Pokémon"], "Ultraball": [5, "×5 bei Ultrabestien, sonst ×0,1"], "Kirschball": [1, ""], "Kirschenball": [1, ""]};
const BALL_HISUI = {"Pokéball": [1, ""], "Superball": [1.5, ""], "Hyperball": [2.25, ""], "Federball": [1, "besser bei fliegenden Pokémon; fliegt weit"],
  "Flügelball": [1.5, "besser bei fliegenden Pokémon; fliegt weiter"], "Düsenball": [2, "×2,75 bei fliegenden Pokémon; fliegt am weitesten"],
  "Schwerball": [1, "×1,25, wenn das Pokémon dich nicht bemerkt hat; fliegt kurz"], "Zentnerball": [1.25, "×2, wenn das Pokémon dich nicht bemerkt hat"],
  "Tonnenball": [2.5, "×2,75, wenn das Pokémon dich nicht bemerkt hat"], "Urball": [0, "fängt immer"], "Rätselball": [1, ""]};
const ballOf = (x) => { const h = / \(Hisui\)$/.test(x.name) || S.game === "legends-arceus"; const n = x.name.replace(/ \(Hisui\)$/, "");
  return (h ? BALL_HISUI[n] : null) || BALL[n] || null; };
/* Wirkung von Medizin und Beeren in schmalen Spalten: KP, AP, EP und die Statusprobleme. Aus Kurztext und Beschreibung
   des Spiels gelesen (die Beschreibung gilt, wenn sie eine Zahl nennt: Werte ändern sich zwischen den Spielen) */
const FXCOLS = [["kp", "KP", "Füllt KP auf"], ["ap", "AP", "Füllt AP auf"], ["ep", "EP", "Erfahrung oder Level"], ["slp", "zZz", "Weckt aus dem Schlaf"],
  ["frz", "Eis", "Taut auf"], ["par", "Par", "Heilt Paralyse"], ["psn", "Gift", "Heilt Vergiftung"], ["brn", "Brand", "Heilt Verbrennung"], ["cnf", "Verw", "Heilt Verwirrung"]];
function itemFx(x) {
  const t = x.text || "", w = x.wirkung || "", o = {};
  const kp = t.match(/KP[^.]*?um (\d+) Punkte/) || t.match(/(\d+) KP/);
  if (/belebt|wiederbelebt/i.test(w + t)) o.kp = /vollständig|vollen KP/.test(w + t) ? "voll" : /Hälfte|halben/.test(w + t) ? "½" : "✓";
  else if (kp) o.kp = "+" + kp[1];
  else if (/KP voll|KP[^.]*vollständig|alle KP/.test(w + " " + t)) o.kp = "voll";
  else if (/KP[^.]*ein wenig/.test(t)) o.kp = "etwas";
  else if (/im Notfall die KP/.test(t)) o.kp = "⅓";
  else if (/KP \+(\d+)/.test(w)) o.kp = "+" + w.match(/KP \+(\d+)/)[1];
  if (/belebt/i.test(w + t)) o.belebt = true;
  const ap = t.match(/AP[^.]*?um (\d+)/);
  if (ap) o.ap = "+" + ap[1];
  else if (/AP[^.]*vollständig|AP voll/.test(t + " " + w)) o.ap = /aller Attacken|alle Attacken/.test(t + w) ? "alle" : "voll";
  if (/Sonderbonbon/.test(x.name) || /Level[^.]*um 1/.test(t)) o.ep = "Lv +1";
  else if (/Erfahrungspunkte/.test(t)) o.ep = /sehr große/.test(t) ? "XL" : /große/.test(t) ? "L" : /gewisse/.test(t) ? "M" : /geringe/.test(t) ? "S" : "✓";
  const all = /alle (seine |ihre )?Statusprobleme|alle Statusprobleme/.test(t + " " + w);
  const chk = (k, re) => { if (all && k !== "cnf" || re.test(t + " " + w)) o[k] = "✓"; };
  chk("slp", /Schlaf|erwacht|aufweck/i); chk("frz", /taut|Einfrier|eingefroren|aufgetaut/i); chk("par", /Paralyse|paralys/i);
  chk("psn", /Vergiftung|vergiftet/i); chk("brn", /Verbrennung/i);
  if (/heilt[^.]*Verwirrung|Verwirrung[^.]*(behebt|heilt)|und Verwirrung/.test(t + " " + w)) o.cnf = "✓";
  return o;
}
const priceColor = (v) => v ? `hsl(45 ${40 + Math.min(1, Math.log10(v) / 4.5) * 50}% ${48 + Math.min(1, Math.log10(v) / 4.5) * 17}%)` : "";
async function itemsView() {
  const rid = RID;
  const d = await api("/api/items?" + qs({spiel: S.game}));
  if (rid !== RID) return;
  const items = d.items || [];
  const nOdd = items.filter((x) => x.unfertig).length;
  let pocket = store.get("itemPocket", ""), q = "", art = "", odd = false;
  if (!(d.taschen || []).includes(pocket) && !(pocket === HERSTELLEN && d.rezepte)) pocket = "";
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Items</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      <input id="itemq" type="search" placeholder="Name oder Beschreibung" style="width:220px">
      <select id="itemart" aria-label="Art"></select>
      ${nOdd ? `<label data-tip="Einträge, deren Text in den Spieldaten noch Platzhalter wie [VAR] enthält"><input type="checkbox" id="itemodd"> unfertige Einträge (${nOdd})</label>` : ""}
</div>
    <div class="bar"><span class="seg" id="itemseg"><button data-t="">alle</button>${(d.taschen || []).map((t) => `<button data-t="${esc(t)}">${esc(t)}</button>`).join("")}${d.rezepte
      ? `<button data-t="${HERSTELLEN}" data-tip="Items mit Rezept: was es zum Herstellen braucht">Herstellen</button>` : ""}</span><span class="hint grow" id="itemn"></span></div>
    ${d.hinweis ? `<div class="note info">${esc(d.hinweis)}</div>` : ""}
    <div class="scroll sticky" id="itembox"></div>
    <p class="hint">Quelle: PokéAPI; Items ohne Eintrag dort und deutsche Namen: PKHeX${d.rezepte ? "; Rezepte und Fundorte der Zutaten: Altissimo (englisch)" : ""}. Englisch, wo es keinen deutschen Text gibt. Bilder lädt der Abgleich.</p></div>`;
  header();
  const num = (v) => `<td class="c num" data-s="${v ?? -1}">${v || "–"}</td>`;
  const price = (x) => `<td class="c num" data-s="${x.preis ?? -1}">${x.preis ? `<span style="color:${priceColor(x.preis)}">${x.preis.toLocaleString("de-DE")}</span>` : "–"}</td>`;
  const fxCell = (k) => (x) => { const v = itemFx(x)[k]; const n = v === "voll" || v === "alle" ? 999 : v === "✓" ? 1 : parseFloat(String(v || "").replace("+", "")) || (v ? 1 : 0);
    return `<td class="c ifx${v ? " on" : ""}" data-s="${n}">${v ? esc(v) : ""}</td>`; };
  const ballCell = (x) => { const b = ballOf(x); return `<td class="c num" data-s="${b ? (b[0] || 999) : -1}">${b ? (b[0] ? `<b style="color:${ramp((b[0] - 0.8) / 3)}">×${String(b[0]).replace(".", ",")}</b>` : `<b style="color:${ramp(1)}">immer</b>`) : "–"}</td>`; };
  const name = (x) => `<td><span class="iname">${itemImg(x)}<b>${esc(x.name)}</b></span></td>`;
  const text = (x) => x.text ? `<td class="why"${x.englisch ? ` lang="en"` : ""}>${esc(x.text)}</td>`
    : x.fundorte ? `<td class="why" lang="en"><span class="hint">Zu finden:</span> ${esc(x.fundorte.join("; "))}</td>`
    : x.rezept ? `<td class="why" lang="en">${esc(x.rezept.hinweis)}</td>` : `<td class="why hint">–</td>`;
  // Zutaten untereinander, mit Bild (fehlt es, bleibt nur der Name)
  const recipe = (x) => x.rezept ? `<td>${x.rezept.zutaten.map((z) => `<span class="zut2">${z.id ? `<img class="ibild zi" src="itembild/${z.id}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">` : `<span class="ibild zi none"></span>`}<b>${z.n}×</b> ${esc(z.name)}</span>`).join("")}</td>` : "<td></td>";
  const where = (x) => { const o = x.rezept?.ort || "", k = Object.keys(AREA_COLOR).find((a) => o.startsWith(a));
    return `<td data-s="${esc(o)}">${k ? `<span class="area" style="--ac:${AREA_COLOR[k]}">${esc(o)}</span>` : esc(o)}</td>`; };
  // Spalten je Tasche: [Kopf, Breite, Zelle]
  const COLS = {
    "": [[th("Name"), "24%", name], [thc("Preis"), "8%", price], [th("Tasche"), "11%", (x) => `<td>${esc(x.tasche)}</td>`], [th("Art"), "15%", (x) => `<td>${esc(x.art)}</td>`],
         [th("Beschreibung", "", true), "", text]],
    wirkung: [[th("Name"), "20%", name], [thc("Preis"), "7%", price], [th("Art"), "11%", (x) => `<td>${esc(x.art)}</td>`],
              ...FXCOLS.map(([k, n, tip]) => [thc(n, tip), "52px", fxCell(k)]),
              [th("Beschreibung", "", true), "", text]],
    Bälle: [[th("Name"), "22%", name], [thc("Preis"), "7%", price], [thc("Fang", "Fangfaktor des Balls; „immer“ fängt sicher. In Legenden: Arceus Richtwerte"), "70px", ballCell],
            [th("Bedingung", "Wann der Ball besser fängt"), "26%", (x) => `<td>${esc(ballOf(x)?.[1] || "")}</td>`], [th("Beschreibung", "", true), "", text]],
    Maschinen: [[th("Name"), "16%", name], [thc("Preis"), "7%", price], [th("Attacke"), "15%", (x) => `<td><b>${esc(x.attacke?.name || "")}</b></td>`],
                [thc("Typ"), "9%", (x) => `<td class="c" data-s="${x.attacke ? esc(tname(x.attacke.typ)) : ""}">${x.attacke ? tchip(x.attacke.typ) : ""}</td>`],
                [thc("Klasse"), "8%", (x) => `<td class="c">${esc(MKLASSE[x.attacke?.klasse] || "")}</td>`],
                [thc("Stärke"), "6%", (x) => num(x.attacke?.staerke)], [thc("Gen."), "6%", (x) => num(x.attacke?.genauigkeit)], [thc("AP"), "5%", (x) => num(x.attacke?.ap)],
                [th("Wirkung", "", true), "", (x) => `<td class="why">${x.attacke?.kurz ? kurzHtml(x.attacke.kurz) : esc(x.text)}</td>`]],
    [HERSTELLEN]: [[th("Name"), "22%", name], [th("Zutaten"), "30%", recipe], [th("Wo", "Wo das Rezept zu haben ist"), "16%", where],
                   [th("Rezept bekommen", "", true), "", (x) => `<td class="why" lang="en">${esc(x.rezept?.hinweis && x.rezept.hinweis !== "N/A" ? x.rezept.hinweis : "–")}</td>`]],
  };
  const draw = () => {
    const ql = q.toLowerCase();
    const inPocket = items.filter((x) => (!pocket || x.tasche === pocket || (pocket === HERSTELLEN && x.rezept)) && (odd || !x.unfertig));
    const arts = [...new Set(inPocket.map((x) => x.art).filter(Boolean))].sort((a, b) => a.localeCompare(b, "de"));
    if (art && !arts.includes(art)) art = "";
    $("#itemart").innerHTML = `<option value="">jede Art</option>` + arts.map((a) => `<option${a === art ? " selected" : ""}>${esc(a)}</option>`).join("");
    const xs = inPocket.filter((x) => (!art || x.art === art) && (!ql || x.name.toLowerCase().includes(ql) || x.text.toLowerCase().includes(ql)
      || (x.attacke?.name || "").toLowerCase().includes(ql)));
    const kind = pocket === HERSTELLEN ? HERSTELLEN : pocket === "Maschinen" ? "Maschinen" : pocket === "Bälle" ? "Bälle"
      : pocket === "Medizin" || pocket === "Beeren" ? "wirkung" : "";
    const cols = COLS[kind].filter((c, i) => !(pocket && !kind && i === 2));      // in einer Tasche braucht es die Spalte Tasche nicht
    $("#itemn").textContent = `${xs.length} Items`;
    $("#itembox").innerHTML = `<table class="rows sort fixed items lines"><colgroup>${cols.map((c) => `<col${c[1] ? ` style="width:${c[1]}"` : ""}>`).join("")}</colgroup>
      <thead><tr>${cols.map((c) => c[0]).join("")}</tr></thead><tbody>${xs.map((x) => `<tr data-r="${x.id}"${x.unfertig ? ` class="odd"` : ""}>${cols.map((c) => c[2](x)).join("")}</tr>`).join("")
      + (xs.length ? "" : `<tr><td colspan="${cols.length}" class="hint">Nichts gefunden.</td></tr>`)}</tbody></table>`;
    $$("#itemseg button").forEach((x) => x.classList.toggle("on", x.dataset.t === pocket));
    const tb = $("#itembox table");
    $$("tbody tr[data-r]", tb).forEach((tr) => [...tr.cells].forEach((td, i) => { if (i) td.dataset.c = i; else td.dataset.pr = tr.dataset.r; }));
    crossTable(tb, IPIN);
  };
  $("#itemq").addEventListener("input", (e) => { q = e.target.value.trim(); draw(); });
  $("#itemart").addEventListener("change", (e) => { art = e.target.value; draw(); });
  $("#itemodd")?.addEventListener("change", (e) => { odd = e.target.checked; draw(); });
  $$("#itemseg button").forEach((b) => b.addEventListener("click", () => { pocket = b.dataset.t; store.set("itemPocket", pocket); art = ""; draw(); }));
  draw();
}
const TPIN = {d: {r: null, c: null}, a: {r: null, c: null}};
/* Typen des Teams: je Mitglied mit seinen (Doppel-)Typen, wie viel es einsteckt (Verteidigung) und wie stark seine
   Eigentypen treffen (Angriff, der bessere der beiden). Zeilen sind die Mitglieder, Spalten die 18 Typen */
function teamTypeHtml(ms, ts) {
  const ch = S.chart;
  const def = (m, a) => m.typen.reduce((f, t) => f * (ch[a]?.[t] ?? 1), 1);
  const att = (m, v) => Math.max(...m.typen.map((t) => ch[t]?.[v] ?? 1));
  const one = (k, title, hint, fn, good) => {
    const sum = ts.map((t) => { const fs = ms.map((m) => fn(m, t)); return [fs.filter((f) => good(f)).length, fs.filter((f) => good(1 / (f || 0.001)) && f !== 1).length]; });
    return `<details class="box tteam" data-tt="${k}"${store.get("ttOpen", {})[k] === false ? "" : " open"}><summary><h2>${title}</h2><span class="hint">${hint}</span></summary>
      <div class="scroll"><table class="chart" id="tt-${k}"><thead><tr><th class="corner"></th>${ts.map((t) => `<th class="v" data-c="${t}" data-pc="${t}"><span>${tchip(t)}</span></th>`).join("")}</tr></thead>
      <tbody>${ms.map((m, i) => `<tr data-r="${i}"><th class="r tm" data-pr="${i}" data-hc="${m.id}"><span class="tmh">${img(m.id, "sm")}<span>${esc(m.name)}</span>${tchips(m.typen)}</span></th>${ts.map((t) => { const f = fn(m, t);
        return `<td data-c="${t}" data-tip="${esc(k === "d" ? `${tname(t)} gegen ${m.name}: ×${fl(f)}` : `${m.name} (Eigentyp) gegen ${tname(t)}: ×${fl(f)}`)}">${f === 1 ? "" : `<span class="f ${k === "a" && f ? fcls(1 / f) : fcls(f)}">${fl(f)}</span>`}</td>`; }).join("")}</tr>`).join("")}</tbody>
      <tfoot><tr><th class="r">${k === "d" ? "resistent · schwach" : "stark · schwach"}</th>${sum.map(([g, b], j) => `<td data-c="${ts[j]}"><span class="go">${g || ""}</span>${g && b ? "·" : ""}<span class="stop">${b || ""}</span></td>`).join("")}</tr></tfoot></table></div></details>`;
  };
  // Farben aus Sicht des Mitglieds: grün hilft ihm, rot schadet ihm. Verteidigung: ½ grün, 2 rot; Angriff umgekehrt
  return one("d", "Verteidigung je Mitglied", "Spalte: angreifender Typ. So viel steckt das Mitglied mit seinen Typen ein; grün: steckt wenig ein, rot: viel.", def, (f) => f < 1)
    + one("a", "Angriff je Mitglied", "Spalte: verteidigender Typ. So gut trifft der bessere Eigentyp des Mitglieds; grün: trifft stark, rot: schwach.", att, (f) => f > 1);
}
async function chartView() {
  const ch = S.chart, ts = Object.keys(ch);
  const rid = RID, mine = store.get("chartTeam", false) && S.team.ids.length;
  let ms = [];
  if (mine) {
    const miss = S.team.ids.filter((id) => !ROWS[id]?.typen);
    if (miss.length) (await api("/api/team/bewerten", {spiel: S.game, ids: miss, kurz: 1})).mitglieder.forEach((m) => { ROWS[m.id] = Object.assign(ROWS[m.id] || {}, m); });
    if (rid !== RID) return;
    ms = S.team.ids.map((id) => ROWS[id]).filter((r) => r?.typen).map((r) => ({...r, typen: r.typen.map(String)}));
  }
  const own = new Set(ms.flatMap((m) => m.typen));
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Typtabelle Generation ${S.chartGen}</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      <label data-tip="${S.team.ids.length ? "Nur die Typen deines Teams als Zeilen, dazu Verteidigung und Angriff je Mitglied" : "Erst ein Team zusammenstellen"}"><input type="checkbox" id="ctm"${mine ? " checked" : ""}${S.team.ids.length ? "" : " disabled"}> Mein Team</label>
      <button class="small" data-act="unpin" id="unpin" hidden>Markierung aufheben</button></div>
    <p class="hint">Zeile greift an, Spalte verteidigt. <span class="f f2">2</span> sehr effektiv · <span class="f f05">½</span> nicht sehr effektiv ·
      <span class="f f0">0</span> keine Wirkung (immun) · leer = normal (×1). Klick auf einen Typ hält Zeile oder Spalte fest, Klick auf eine Zelle beides.</p>
    <div class="scroll"><table class="chart"><thead><tr><th class="corner"><span>Angriff ↓ · Verteidigung →</span></th>${ts.map((t) => `<th class="v" data-c="${t}" data-pc="${t}"><span>${tchip(t)}</span></th>`).join("")}</tr></thead>
    <tbody>${ts.filter((a) => !mine || own.has(a)).map((a) => `<tr data-r="${a}"><th class="r" data-pr="${a}">${tchip(a)}</th>${ts.map((v) => { const f = ch[a][v];
      return `<td data-c="${v}" data-tip-cell="${a}:${v}">${f === 1 ? "" : `<span class="f ${fcls(f)}">${fl(f)}</span>`}</td>`; }).join("")}</tr>`).join("")}</tbody>
    </table></div>${mine ? `<p class="hint">Nur die Typen deines Teams als Angreifer: ${ms.map((m) => esc(m.name)).join(", ")}.</p>` : ""}</div>
    ${mine ? teamTypeHtml(ms, ts) : ""}${combosHtml(ch)}`;
  header();
  $("details.combos").addEventListener("toggle", (e) => store.set("combosOpen", e.target.open));
  $("#cbt").addEventListener("change", (e) => { const t = e.target.value; $$("table.cbt tbody tr").forEach((r) => { r.hidden = !!t && !r.dataset.ts.split(",").includes(t); }); });
  crossTable($(".chart"), PIN, () => { $("#unpin").hidden = PIN.r === null && PIN.c === null; });
  $("#ctm").addEventListener("change", (e) => { store.set("chartTeam", e.target.checked); chartView(); });
  $$("details.tteam").forEach((d) => {
    crossTable($("table", d), TPIN[d.dataset.tt]);
    d.addEventListener("toggle", () => store.set("ttOpen", {...store.get("ttOpen", {}), [d.dataset.tt]: d.open}));
  });
}

/* ------------------------------------------------------------------ Vergleich */
/* Zwei Pokémon nebeneinander (#vergleich/<A>/<B>): Werte mit Unterschied, Typwirkung, Fähigkeiten, Attacken. Das jeweils
   bessere ist grün; ein Feld ohne Pokémon bietet die Suche an */
/* ------------------------------------------------------------------ Initiative-Liste */
// Initiative-Wert ab Generation 3: ((2·Basis + DV + EV/4) · Level/100 + 5) · Wesen; bis Generation 2 mit DV (0–15) und Stat Exp
function speedStat(base, lv, iv, ev, nat, gen) {
  if (gen <= 2) return Math.floor(((base + iv) * 2 + Math.floor(Math.ceil(Math.sqrt(ev)) / 4)) * lv / 100) + 5;
  return Math.floor((Math.floor((2 * base + iv + Math.floor(ev / 4)) * lv / 100) + 5) * nat);
}
function speedCols(base, lv, gen) {
  if (gen <= 2) return [speedStat(base, lv, 0, 0, 1, gen), null, speedStat(base, lv, 15, 65535, 1, gen), null];
  return [speedStat(base, lv, 0, 0, 0.9, gen), speedStat(base, lv, 31, 0, 1, gen), speedStat(base, lv, 31, 252, 1, gen), speedStat(base, lv, 31, 252, 1.1, gen)];
}
/* ------------------------------------------------------------------ Kampf: Doppelkampf-Bewertung (Champions, für alle Spiele erreichbar) */
async function battleView() {
  const rid = RID, t = S.team;
  main.innerHTML = `<div class="box"><div class="bar"><b>Kampf in</b> <select class="gamesel"></select>
      <a class="btn" href="#team">Team bearbeiten</a><a class="btn" href="#initiative">Initiative-Liste</a></div>
      <p class="hint">Doppelkampf-Bewertung des aktuellen Teams (${t.ids.length} Pokémon) mit den gewählten Attacken: Rollen, Flächenattacken und
        Tempo. Attacken wählst du je Platz auf der Detailseite oder übernimmst sie als Showdown-Text im Reiter Team.</p>
      <div id="dbl"><p class="hint">Lädt …</p></div></div>`;
  header();
  if (!t.ids.length) { $("#dbl").innerHTML = `<p class="hint">Das Team ist leer.</p>`; return; }
  const r = await api("/api/team/doppel", {spiel: S.game, ids: t.ids, details: t.details});
  if (rid !== RID) return;
  const who = (xs) => xs.map(([n, a]) => `<b>${esc(n)}</b> <span class="hint">(${esc(a)})</span>`).join(", ");
  const roles = r.rollen.map((x) => `<tr><th data-tip="${esc(x.tipp)}">${esc(x.name)}</th>
      <td>${x.wer.length ? `<span style="color:var(--go)">✓</span> ${who(x.wer)}` : `<span style="color:var(--stop)">fehlt</span>`}
      ${x.kann.length ? `<div class="hint">Könnten lernen: ${x.kann.map(([n, a]) => `${esc(n)} (${esc(a)})`).join(", ")}</div>` : ""}</td></tr>`).join("");
  const spread = r.flaeche.length ? r.flaeche.map(([n, a, ally]) => `<b>${esc(n)}</b>: ${esc(a)}${ally ? ` <span class="hint">(trifft auch den Partner)</span>` : ""}`).join("<br>")
    : `<span class="hint">Keine Flächenattacke gewählt. Im Doppel treffen sie beide Gegner (mit 75 % Stärke).</span>`;
  const partner = r.partner.map((p) => `<div class="note ${p.trifft.some(([, f]) => f > 1) ? "warn" : "info"}">${tchip(p.typ)} <b>${esc(p.attacke)}</b> von ${esc(p.wer)}:
      ${p.immun.length ? `sicher neben ${p.immun.map(([n]) => esc(n)).join(", ")}` : "kein Partner ist immun"}${p.trifft.length ? `; trifft ${p.trifft.map(([n, f]) => `${esc(n)} ×${fl(f)}`).join(", ")}` : ""}</div>`).join("");
  $("#dbl").innerHTML = `<div class="cols"><div><div class="score" data-tip="Rollen (70), Flächenattacken (20), keine Gefahr für den Partner (10)">${r.wertung}<span class="hint"> / 100</span></div>
      <table class="rows dblroles"><tbody>${roles}</tbody></table></div>
    <div><h3>Flächenattacken</h3><p>${spread}</p>${partner}
      <h3>Tempo</h3><p class="hint">Schnell (Basis ab 95): ${esc(r.tempo.schnell.join(", ") || "keiner")} · langsam (bis 60): ${esc(r.tempo.langsam.join(", ") || "keiner")}</p>
      ${r.tempo.rat ? `<div class="note info">${esc(r.tempo.rat)}</div>` : ""}</div></div>`;
}
async function speedView() {
  const rid = RID, gen = S.meta?.spiele?.find((g) => g.kennung === S.game)?.gen || 9;
  const o = Object.assign({level: 50, wind: false, schal: false, q: "", team: false}, store.get("speed", {}));
  main.innerHTML = `<div class="box"><div class="bar"><b>Initiative in</b> <select class="gamesel"></select>
      <label>Level <select id="splv">${[50, 100].map((v) => `<option${v === o.level ? " selected" : ""}>${v}</option>`).join("")}</select></label>
      <label data-tip="Verdoppelt die Initiative (vier Runden)"><input type="checkbox" id="spwind"${o.wind ? " checked" : ""}> Rückenwind</label>
      <label data-tip="Wahlschal: Initiative ×1,5"><input type="checkbox" id="spschal"${o.schal ? " checked" : ""}> Wahlschal</label>
      <label><input type="checkbox" id="spteam"${o.team ? " checked" : ""}> nur mein Team</label>
      <input id="spq" type="search" placeholder="Pokémon suchen" value="${esc(o.q)}" class="grow"></div>
      <p class="hint">${gen <= 2 ? "Bis Generation 2: ohne und mit vollen DVs und Stat Exp." : "Spalten: minimal (0 IV, 0 EV, senkendes Wesen), neutral (31 IV, 0 EV), maximal (31 IV, 252 EV), maximal mit Wesen (+10 %)."}
        Dein Team ist hervorgehoben, mit dem Wert aus Level, EVs, IVs und Wesen, soweit eingetragen (sonst neutral). Unter Bitterraum gilt die Liste umgekehrt.</p>
      <div id="splist"><p class="hint">Lädt …</p></div></div>`;
  header();
  const d = await api("/api/pokemon?" + qs({spiel: S.game, formen: "relevant", kampf: 1, sort: "init", limit: 2000}));
  if (rid !== RID) return;
  d.rows.forEach((r) => { ROWS[r.id] = Object.assign(ROWS[r.id] || {}, r); });
  const ev = S.team.ids.length ? await api("/api/team/bewerten", {spiel: S.game, ids: S.team.ids, details: S.team.details, kurz: 1}) : {mitglieder: [], plaetze: []};
  if (rid !== RID) return;
  (ev.mitglieder || []).forEach((m) => { ROWS[m.id] = Object.assign(ROWS[m.id] || {}, m); });
  const draw = () => {
    const mult = (o.wind ? 2 : 1) * (o.schal ? 1.5 : 1), lv = o.level, q = o.q.trim().toLowerCase();
    const mine = S.team.ids.map((id, i) => {
      const r = ROWS[id], det = S.team.details[i] || {}, x = ev.plaetze?.[i] || {};
      if (!r) return null;
      const iv = det.ivs ? det.ivs[5] : (gen <= 2 ? 15 : 31), evv = det.evs ? det.evs[5] : 0;
      const nat = x.wesen_mod ? (x.wesen_mod[0] === 5 ? 1.1 : x.wesen_mod[1] === 5 ? 0.9 : 1) : 1;
      const own = speedStat(r.werte[5], det.level || lv, iv, evv, nat, gen) * (x.item === "Wahlschal" && !o.schal ? 1.5 : 1);
      return {r, own: Math.floor(own * (o.wind ? 2 : 1) * (o.schal ? 1.5 : 1)), det, x, slot: i};
    }).filter(Boolean);
    let rows = d.rows.map((r) => ({r, cols: speedCols(r.werte[5], lv, gen).map((v) => v == null ? null : Math.floor(v * mult))}));
    if (q) rows = rows.filter(({r}) => r.name.toLowerCase().includes(q));
    if (o.team) rows = [];
    const mrow = (m) => `<tr class="mine" data-hc="${m.r.id}"><td>${img(m.r.id)} <a href="#pokemon/${m.r.id}/${m.slot}">${esc(m.r.name)}</a> <span class="hint">dein Team${m.det.level ? ", Level " + m.det.level : ""}${m.x.wesen ? ", " + esc(m.x.wesen) : ""}${m.x.item ? ", " + esc(m.x.item) : ""}</span></td>
      <td class="num">${m.r.werte[5]}</td><td class="num" colspan="4"><b>${m.own}</b></td></tr>`;
    // Team-Zeilen stehen dort, wo ihr eigener Wert in die Liste fällt
    const out = [], todo = [...mine].sort((a, b) => b.own - a.own);
    rows.forEach(({r, cols}) => {
      const top = cols[3] ?? cols[2];
      while (todo.length && todo[0].own >= top) out.push(mrow(todo.shift()));
      out.push(`<tr data-hc="${r.id}"><td>${img(r.id)} <a href="#pokemon/${r.id}">${esc(r.name)}</a></td><td class="num">${r.werte[5]}</td>${cols.map((v) => `<td class="num">${v ?? ""}</td>`).join("")}</tr>`);
    });
    todo.forEach((m) => out.push(mrow(m)));
    $("#splist").innerHTML = `<div class="scroll"><table class="speed"><thead><tr><th>Pokémon</th><th class="num">Basis</th>${gen <= 2 ? "<th class=\"num\">ohne</th><th></th><th class=\"num\">voll</th><th></th>" : "<th class=\"num\">minimal</th><th class=\"num\">neutral</th><th class=\"num\">maximal</th><th class=\"num\">maximal +</th>"}</tr></thead>
      <tbody>${out.join("") || `<tr><td colspan="6" class="hint">Nichts gefunden.</td></tr>`}</tbody></table></div>`;
  };
  const set = (k, v) => { o[k] = v; store.set("speed", o); draw(); };
  $("#splv").addEventListener("change", (e) => set("level", +e.target.value));
  $("#spwind").addEventListener("change", (e) => set("wind", e.target.checked));
  $("#spschal").addEventListener("change", (e) => set("schal", e.target.checked));
  $("#spteam").addEventListener("change", (e) => set("team", e.target.checked));
  $("#spq").addEventListener("input", (e) => set("q", e.target.value));
  draw();
}
async function compareView(a, b) {
  const rid = RID;
  const ids = [a, b].map((x) => (x && !isNaN(+x) ? +x : null));
  const ds = await Promise.all(ids.map((id) => id == null ? null : api(`/api/pokemon/${id}?` + qs({spiel: S.game})).catch(() => null)));
  if (rid !== RID) return;
  ds.forEach((d) => { if (d) { ROWS[d.id] = Object.assign(ROWS[d.id] || {}, d); } });
  const [A, B] = ds;
  const go = (x, y) => { location.hash = `vergleich/${x ?? "-"}/${y ?? "-"}`; };
  const head = (d, k) => `<div class="box cmphead"><div class="ac"><input type="search" id="cmpq${k}" placeholder="${d ? "anderes Pokémon suchen" : "Pokémon suchen"}" aria-label="Pokémon suchen"></div>
    ${d ? `<a class="cmpmon" href="#pokemon/${d.id}">${img(d.id, "big")}<b>${esc(d.name)}</b></a><div>${tchips(d.typen)}</div>
      <span data-tip-stats="${d.werte.join(",")}">${radar(d.werte, 150, true)}</span>` : `<p class="hint">Noch kein Pokémon gewählt.</p>`}</div>`;
  const better = (x, y) => x > y ? " win" : "";
  const statRows = A && B ? [...STAT.map((n, i) => [n, A.werte[i], B.werte[i], i]), ["Summe", A.summe, B.summe, "summe"]].map(([n, x, y, i]) => {
    const w = (v) => Math.min(100, v / (i === "summe" ? 780 : statMax(i)) * 100);
    const diff = x - y;
    return `<tr><td class="num${better(x, y)}">${x}</td><td><span class="sbar rev"><i style="width:${w(x)}%;background:${i === "summe" ? sumColor(x) : statColor(x)}"></i></span></td>
      <th>${n}<div class="hint">${diff ? (diff > 0 ? "+" : "") + diff : "gleich"}</div></th>
      <td><span class="sbar"><i style="width:${w(y)}%;background:${i === "summe" ? sumColor(y) : statColor(y)}"></i></span></td><td class="num${better(y, x)}">${y}</td></tr>`;
  }).join("") : "";
  const ts = Object.keys(S.chart || {});
  const defRow = A && B ? ts.map((t) => { const x = A.wirkung[t] ?? 1, y = B.wirkung[t] ?? 1;
    return `<tr><td class="c">${x === 1 ? "" : `<span class="f ${fcls(x)}${x < y ? " win" : ""}">${fl(x)}</span>`}</td><th class="c">${tchip(t)}</th><td class="c">${y === 1 ? "" : `<span class="f ${fcls(y)}${y < x ? " win" : ""}">${fl(y)}</span>`}</td></tr>`; }).join("") : "";
  const sum = (d) => { const v = Object.values(d.wirkung); return {s: v.filter((f) => f > 1).length, r: v.filter((f) => f < 1 && f > 0).length, i: v.filter((f) => f === 0).length}; };
  const mv = (d) => new Map([...d.attacken.attacken, ...d.attacken.status].map((m) => [m.id, m]));
  let moves = "";
  if (A && B) {
    const ma = mv(A), mb = mv(B);
    const only = (x, y) => [...x.values()].filter((m) => !y.has(m.id)).sort((p, q) => p.name.localeCompare(q.name, "de"));
    const both = [...ma.values()].filter((m) => mb.has(m.id)).sort((p, q) => p.name.localeCompare(q.name, "de"));
    const list = (xs) => xs.length ? `<div class="cmpmoves">${xs.map((m) => `<span>${tchip(m.typ)} ${esc(m.name)}</span>`).join("")}</div>` : `<p class="hint">keine</p>`;
    moves = `<div class="box"><h2>Attacken im Spiel</h2>
      <details><summary>Nur ${esc(A.name)} <span class="hint">${only(ma, mb).length}</span></summary>${list(only(ma, mb))}</details>
      <details><summary>Beide <span class="hint">${both.length}</span></summary>${list(both)}</details>
      <details><summary>Nur ${esc(B.name)} <span class="hint">${only(mb, ma).length}</span></summary>${list(only(mb, ma))}</details></div>`;
  }
  const abil = (d) => d.faehigkeiten.length ? d.faehigkeiten.map((x) => `<div><b>${wikiLink(x.name)}</b>${x.versteckt ? " <span class='cls'>versteckt</span>" : ""}<div class="why">${esc(x.text)}</div></div>`).join("") : `<p class="hint">keine</p>`;
  main.innerHTML = `<div class="bar">${backLink()}<h2 style="margin:0">Vergleich</h2><label class="game2">Spiel <select class="gamesel"></select></label>
      ${A || B ? `<button id="cmpswap" data-tip="Seiten tauschen">⇄ tauschen</button>` : ""}</div>
    <div class="cmpgrid">${head(A, 0)}<div class="box cmpmid">${A && B ? `<table class="cmpst">${statRows}</table>` : `<p class="hint">Wähle zwei Pokémon, dann stehen hier die Werte nebeneinander.</p>`}</div>${head(B, 1)}</div>
    ${A && B ? `<div class="cols"><div class="box"><h2 data-tip="So stark treffen Attacken eines Typs; grün = steckt weniger ein">Verteidigung</h2>
        <p class="hint">${esc(A.name)}: ${sum(A).s} Schwächen, ${sum(A).r} Resistenzen, ${sum(A).i} Immunitäten · ${esc(B.name)}: ${sum(B).s}, ${sum(B).r}, ${sum(B).i}</p>
        <table class="cmpdef"><thead><tr><th class="c">${esc(A.name)}</th><th class="c">Angriffstyp</th><th class="c">${esc(B.name)}</th></tr></thead><tbody>${defRow}</tbody></table></div>
      <div class="stack"><div class="box"><h2>Fähigkeiten</h2><div class="cols2"><div><h3>${esc(A.name)}</h3>${abil(A)}</div><div><h3>${esc(B.name)}</h3>${abil(B)}</div></div></div>${moves}</div></div>` : ""}`;
  header();
  autocomplete($("#cmpq0"), (r) => go(r.id, B?.id));
  autocomplete($("#cmpq1"), (r) => go(A?.id, r.id));
  $("#cmpswap")?.addEventListener("click", () => go(B?.id, A?.id));
  if (!A) $("#cmpq0").focus(); else if (!B) $("#cmpq1").focus();
}

/* Alle Typkombinationen (Verteidigung): je Kombination die Wirkung jedes Angriffstyps, dazu Schwächen, 4-fach,
   Resistenzen und Immunitäten zum Sortieren; Filter auf einen enthaltenen Typ */
function combosHtml(ch) {
  const ts = Object.keys(ch);
  const combos = [];
  ts.forEach((x, i) => { combos.push([x]); ts.slice(i + 1).forEach((y) => combos.push([x, y])); });
  const rows = combos.map((c) => {
    const fs = ts.map((a) => c.reduce((f, d) => f * (ch[a]?.[d] ?? 1), 1));
    const n = (p) => fs.filter(p).length;
    return `<tr data-ts="${c.join(",")}"><th class="r" data-s="${esc(c.map(tname).join(" "))}">${tchips(c)}</th>
      <td class="c num" data-s="${n((f) => f > 1)}">${n((f) => f > 1)}</td><td class="c num" data-s="${n((f) => f >= 4)}">${n((f) => f >= 4) || ""}</td>
      <td class="c num" data-s="${n((f) => f < 1 && f > 0)}">${n((f) => f < 1 && f > 0)}</td><td class="c num" data-s="${n((f) => f === 0)}">${n((f) => f === 0) || ""}</td>
      ${fs.map((f) => `<td class="c" data-s="${f}">${f === 1 ? "" : `<span class="f ${fcls(f)}">${fl(f)}</span>`}</td>`).join("")}</tr>`;
  }).join("");
  return `<details class="box combos"${store.get("combosOpen", false) ? " open" : ""}><summary><h2 style="display:inline">Alle Typkombinationen</h2> <span class="hint">${combos.length} Kombinationen, als Verteidiger</span></summary>
    <div class="bar"><label>mit Typ <select id="cbt"><option value="">alle</option>${ts.map((t) => `<option value="${t}">${esc(tname(t))}</option>`).join("")}</select></label>
      <span class="hint">Spalten: so stark treffen Attacken dieses Typs. Klick auf eine Überschrift sortiert.</span></div>
    <div class="scroll sticky"><table class="chart sort cbt"><thead><tr>${th("Typen")}${thc("Schw.", "Schwächen: Angriffstypen mit ×2 oder mehr")}${thc("×4", "4-fache Schwächen")}${thc("Res.", "Resistenzen: ×½ oder weniger")}${thc("Imm.", "Immun: keine Wirkung")}
      ${ts.map((t) => `<th class="v c" data-sort><span>${tchip(t)}</span></th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div></details>`;
}

/* ------------------------------------------------------------------ Einstellungen */
/* Zeiten deutsch und in der Zeit des Browsers: „10.11.2026, 15:40 Uhr“ (der Server schreibt UTC) */
const deTime = (iso) => { if (!iso) return ""; const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");
  return isNaN(d) ? String(iso) : d.toLocaleString("de-DE", {day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit"}) + " Uhr"; };
// Protokollzeilen beginnen mit der Uhrzeit in UTC; gezeigt in der Zeit des Browsers
const logLocal = (line) => { const m = /^(\d\d):(\d\d):(\d\d)( [\s\S]*)$/.exec(line); if (!m) return line;
  const d = new Date(); d.setUTCHours(+m[1], +m[2], +m[3], 0); return d.toLocaleTimeString("de-DE") + m[4]; };
/* Einstellungen wie im VR-Navigator: oben eine Leiste mit den Abschnitten, jeder Kasten klappt auf und zu (gemerkt) */
function foldBoxes(root) {
  const shut = new Set(store.get("setShut", ["quellen", "lesezeichen", "spieldaten"]));
  const boxes = $$(":scope > .box, :scope > .cols > .box, :scope > details.box", root);
  const slug = (t) => t.toLowerCase().replace(/[^a-zäöüß]+/g, "-").replace(/^-|-$/g, "").replace(/^seite-untersuchen.*/, "lesezeichen").replace(/^quellen.*/, "quellen");
  const jumps = [];
  boxes.forEach((b) => {
    const h = $("h2", b); if (!h) return;
    const id = slug(h.textContent); jumps.push([id, h.textContent.replace(/\s*\(.*\)$/, "")]);
    let d = b;
    if (b.tagName !== "DETAILS") {
      d = document.createElement("details"); d.className = b.className;
      const sm = document.createElement("summary"); const bar = h.closest(".bar") && h.closest(".bar") !== b ? h.closest(".bar") : null;
      if (bar) { sm.append(...bar.childNodes); bar.remove(); } else { sm.append(h); }
      d.append(sm, ...b.childNodes); b.replaceWith(d);
    }
    d.id = "s-" + id; d.classList.add("fold"); d.open = !shut.has(id);
    $("summary", d).addEventListener("click", (e) => { if (e.target.closest("button")) e.preventDefault(); });   // Knöpfe im Kopf klappen nicht
    d.addEventListener("toggle", () => { if (d.open) shut.delete(id); else shut.add(id); store.set("setShut", [...shut]); });
  });
  root.insertAdjacentHTML("afterbegin", `<div class="jump">${jumps.map(([id, l]) => `<a href="#einstellungen" data-jump="s-${id}">${esc(l)}</a>`).join("")}
    <span class="foldall"><button class="link" data-fold="1">alle auf</button> · <button class="link" data-fold="0">alle zu</button></span></div>`);
  $$("[data-jump]", root).forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); const d = $("#" + a.dataset.jump); d.open = true; d.scrollIntoView({behavior: "smooth", block: "start"}); }));
  $$("[data-fold]", root).forEach((b) => b.addEventListener("click", () => $$("details.fold", root).forEach((d) => { d.open = b.dataset.fold === "1"; })));
}
async function settingsView() {
  const rid = RID;
  const [st, pr] = await Promise.all([api("/api/status"), S.meta?.has_data ? api("/api/pruefung") : []]);
  if (rid !== RID) return;
  const s = S.meta?.einstellungen || {};
  const src = st.sources || {};
  const open = pr.filter((r) => !r.entscheidung);
  const srcRow = (k, n) => { const r = src[k]; return r ? `<tr><td>${n}</td><td>${r.ok ? "✓" : "✗"} ${esc(r.msg || "")}</td><td class="num">${r.requests}</td><td class="num">${r.errors}</td><td class="nw">${esc(deTime(r.at))}</td></tr>` : ""; };
  const srcKeys = ["pokeapi", "showdown", "pkhex", "spawns", "karten", "sprites", "extras", "pokewiki", "altissimo", "companion"].filter((k) => src[k]);
  const okN = srcKeys.filter((k) => src[k].ok).length, bad = srcKeys.filter((k) => !src[k].ok);
  main.innerHTML = `<div class="cols">
    <div class="box"><h2>Abgleich</h2>
      ${st.running ? `<div class="note info">Läuft: ${esc(st.step || "")}${st.total ? ` (${st.done}/${st.total})` : ""}</div>` : ""}
      <p>Letzter Lauf: ${st.started ? esc(deTime(st.started)) + (st.ok === false ? " <b>mit Fehlern</b>" : "") : "noch keiner"}
      ${st.built ? `<br>Datenbank gebaut: ${esc(deTime(st.built))}` : ""}
      ${srcKeys.length ? `<br>Quellen: ${[okN && `<b class="okc">${okN} ok</b>`, bad.length && `<b class="errc">${bad.length} mit Problem</b> (${esc(bad.join(", "))})`].filter(Boolean).join(", ")}` : ""}</p>
      ${st.stats?.species ? `<p class="hint">${st.stats.species} Arten, ${st.stats.forms} Formen, ${st.stats.moves} Attacken, ${st.stats.games} Spiele, ${st.stats.tables} Tabellen</p>` : ""}
      <div class="bar"><button class="primary" data-act="sync"${st.running ? " disabled" : ""}>Jetzt abgleichen</button>
        <button data-act="rebuild"${st.running ? " disabled" : ""} data-tip="Auch ohne Änderung neu bauen">Neu bauen</button></div>
      <table class="rows"><tr><th>Quelle</th><th>Stand</th><th>Abrufe</th><th>Fehler</th><th>Zeit</th></tr>${srcRow("pokeapi", "PokéAPI")}${srcRow("showdown", "Showdown")}${srcRow("pkhex", "PKHeX")}${srcRow("spawns", "Spawnpunkte")}${srcRow("karten", "Kartenbilder")}${srcRow("sprites", "Bilder")}${srcRow("extras", "Extras")}${srcRow("pokewiki", "PokéWiki")}${srcRow("altissimo", "Altissimo")}${srcRow("companion", "PLA Companion")}</table>
      <h3>Zeitplan</h3>
      <div class="bar"><label><input type="checkbox" id="auto"${s.auto ? " checked" : ""}> automatisch alle</label>
        <input type="number" id="tage" min="1" max="30" value="${s.tage || 7}" style="width:64px"> Tage</div>
      <div class="bar"><label><input type="checkbox" id="sprites"${s.sprites ? " checked" : ""}> Bilder laden (Sprites 96 × 96 und offizielle Artworks 475 × 475, zusammen gut 180 MB; dazu schillernde und animierte Sprites, Rufe und Item-Bilder, gut 45 MB)</label></div>
      <p class="hint">Ändert sich bei keiner Quelle etwas, bleibt die Datenbank. Eine neue gilt erst nach bestandener Selbstprüfung; deine Teams liegen getrennt (user.db) und werden täglich gesichert.</p>
    </div>
    <div class="box"><h2>Zu erledigen</h2>
      ${open.length ? `<p class="hint">PokéAPI und Showdown sind sich hier nicht einig. Wähle, welcher Wert stimmt; im Zweifel im PokéWiki nachsehen. Oder gib die Liste als Auftrag an eine KI und lies ihre Antwort ein.</p>
        <div class="bar slim"><button data-act="todotask" data-tip="Auftrag für einen KI-Chat: die offenen Punkte mit der Bitte, sie zu prüfen. Die Antwort fügst du unter „Antwort einlesen“ ein und siehst erst eine Vorschau.">Auftrag kopieren${open.length > 60 ? ` (60 von ${open.length})` : ""}</button>
          <button data-act="todoans">Antwort einlesen</button>
          <button data-act="todocsv" data-tip="Die offenen Punkte als CSV-Datei, etwa für LibreOffice">herunterladen</button></div>
        <div id="todoans" hidden><textarea id="todotext" rows="5" placeholder="Antwort der KI hier einfügen (JSON)" style="width:100%"></textarea>
          <div class="bar slim"><button class="primary" data-act="todoprev">Vorschau</button><span class="hint">Übernommen wird erst nach der Vorschau.</span></div><div id="todoprev"></div></div>
        <div class="scroll"><table class="rows"><tr><th>Was</th><th>Feld</th><th>PokéAPI</th><th>Showdown</th><th></th></tr>
        ${open.slice(0, 80).map((r) => `<tr><td>${esc(r.name)}</td><td>${esc(r.feld)}</td><td>${esc(r.pokeapi)}</td><td>${esc(r.showdown)}</td>
          <td><button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="pokeapi">PokéAPI</button> <button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="showdown">Showdown</button>
          <button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="egal">egal</button></td></tr>`).join("")}</table></div>`
        : `<div class="note go">Nichts offen${pr.length ? ` (${pr.length} Abweichungen entschieden)` : ""}.</div>`}
      ${pr.length - open.length ? `<details><summary>Entschieden (${pr.length - open.length})</summary><table class="rows">${pr.filter((r) => r.entscheidung).map((r) => `<tr><td>${esc(r.name)}</td><td>${esc(r.feld)}</td><td>${esc(r.entscheidung)}</td><td><button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="">zurück</button></td></tr>`).join("")}</table></details>` : ""}
    </div></div>
    <h2 class="sect">Spieldaten aus den Quellen</h2>
    <div class="box"><h2>Spieldaten</h2>
      <p class="hint">Alles, was der Abgleich gesammelt hat, als ZIP-Datei: die gebaute Datenbank (SQLite), Stand und Protokoll, Einstellungen, die Liste „Zu erledigen“
        und eine Übersicht, welche Bilder, Rufe und Kartenkacheln da sind und welche fehlen. Ohne die Bilder selbst und ohne eigene Daten. Etwa 20 MB.</p>
      <div class="bar"><a class="btn" href="/api/spieldaten" download>Spieldaten herunterladen</a></div></div>
    <div class="box"><div class="bar"><h2 style="margin:0">Protokoll</h2><span class="grow"></span>
        ${(st.log || []).length ? `<button class="link" data-act="copy" data-src="#plog">kopieren</button> <button class="link" data-act="dl" data-src="#plog" data-name="pokedex-protokoll">herunterladen</button>` : ""}</div>
      <div class="log" id="plog">${esc((st.log || []).map(logLocal).join("\n") || "Noch kein Lauf.")}</div></div>
    <div class="box"><h2>Verbindungstest</h2><p class="hint">Fragt jede Quelle einmal an, auch mögliche neue (Items, Fundorte aus den Spieldaten, Wikis, Kampfdaten), und beschreibt die Antwort. Speichert nichts; Probe-Seiten lassen sich herunterladen. Dauert etwa eine Minute.</p>
      <div class="bar"><button data-act="diag">Test starten</button><span class="grow"></span><span id="dlinks"></span></div>
      <div id="diag"></div></div>
    <div class="box"><h2>Seite untersuchen (Lesezeichen)</h2><p class="hint">Manche Seiten laden ihre Karten erst im Browser (etwa das PokéWiki),
      der Abgleich sieht dann nur eine leere Hülle. Dieses Lesezeichen liest die fertig geladene Seite in deinem Browser: welche Daten-Dateien sie nachlädt
      (mit Inhalt), Daten in Variablen, Kartenmarker und das HTML. Ergebnis ist eine Datei für den Testdaten-Ordner, aus der sich ein Leser bauen lässt.
      Es geht nichts an einen Server; Benutzername und Schlüssel der Seite werden entfernt.</p>
      <span class="bm-w"><a class="bm" href="${esc(probeBm())}" data-act="nobm" data-tip="In die Lesezeichenleiste ziehen">⠿ <b>Seite untersuchen</b></a>
        <button data-act="bmcopy" data-tip="Für ein von Hand angelegtes Lesezeichen">Code kopieren</button></span>
      <ul class="hint"><li>Lesezeichenleiste einblenden (Strg+Umschalt+B) und den Knopf hineinziehen, oder „Code kopieren“ und als Adresse eines neuen Lesezeichens einfügen.</li>
        <li>Dann die Seite öffnen (etwa eine Karte im PokéWiki, bei Serebii, GamerGuides oder Pokébip), warten, bis die Karte steht, und das Lesezeichen anklicken.</li></ul></div>
    <h2 class="sect">Deine Daten</h2>
    <div class="box"><h2>Sicherung</h2>
      <p class="hint">Alles Eigene in einer Datei: Teams, Favoriten, deine Sammlung (als gefangen markiert) und Entscheidungen. Die Spieldaten gehören nicht dazu; die holt der Abgleich jederzeit neu.
        Der Server sichert user.db außerdem täglich selbst (die letzten 14 Tage).</p>
      <div class="bar"><a class="btn" href="/api/export" download>Sicherung herunterladen</a>
        <label class="btn filebtn">Sicherung einlesen <input type="file" id="restore" accept="application/json,.json" hidden></label>
        <span class="hint">Einlesen ersetzt alle eigenen Daten durch die Datei (vorher legt der Server eine Kopie an).</span></div>
      <div id="restmsg"></div></div>
    <details class="box"><summary><h2>Quellen und Lizenzen</h2><span class="hint">7 Quellen · Pokédex ${esc(S.meta?.version || "")}</span></summary>
      <p><a href="https://pokeapi.co" target="_blank" rel="noopener noreferrer">PokéAPI</a> (Grunddaten, alle Spiele, BSD-Lizenz) ·
        <a href="https://github.com/smogon/pokemon-showdown" target="_blank" rel="noopener noreferrer">Pokémon Showdown</a> (Gegenprüfung, MIT) ·
        <a href="https://github.com/kwsch/PKHeX" target="_blank" rel="noopener noreferrer">PKHeX</a> (Fundorte aus den Spieldaten, Item-Listen, GPL-3.0) ·
        <a href="https://github.com/Lincoln-LM/PLA-Live-Map" target="_blank" rel="noopener noreferrer">PLA-Live-Map</a> und
        <a href="https://github.com/Lincoln-LM/JS-Finder" target="_blank" rel="noopener noreferrer">JS-Finder</a> (Spawnpunkte, GPL-3.0) ·
        <a href="https://github.com/Altissimo1/altissimo1.github.io" target="_blank" rel="noopener noreferrer">Altissimo</a> (Kartensymbole, Jubeldorf, Rezepte, GPL-3.0) ·
        <a href="https://www.serebii.net" target="_blank" rel="noopener noreferrer">Serebii</a> (Kartenbilder, große Item-Bilder) ·
        <a href="https://www.pokewiki.de" target="_blank" rel="noopener noreferrer">PokéWiki</a> (Links, Attackenwerte, getragene Items und Kartenebenen in Legenden: Arceus, CC BY-SA 3.0 DE).
        Pokémon und alle Namen sind Marken von Nintendo, Creatures und GAME FREAK; dies ist ein privates Nachschlage-Tool.</p></details>`;
  $$("h2.sect", main).forEach((h) => h.remove());       // die Leiste oben ersetzt die Zwischenüberschriften
  foldBoxes(main);
  const saveSet = async () => {
    S.meta.einstellungen = await api("/api/einstellungen", {auto: $("#auto").checked, tage: +$("#tage").value, sprites: $("#sprites").checked});
  };
  ["auto", "tage", "sprites"].forEach((k) => $("#" + k).addEventListener("change", saveSet));
  $("#restore").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    let body;
    try { body = JSON.parse(await file.text()); } catch (x) { $("#restmsg").innerHTML = `<div class="note stop">Keine lesbare JSON-Datei.</div>`; return; }
    const n = (k) => (body[k] || []).length;
    if (!await ask(`Sicherung vom ${String(body.exportiert || "?").slice(0, 10)} einlesen?`, `${n("teams")} Teams, ${n("favoriten")} Favoriten, ${n("gefangen")} in der Sammlung, ${n("entscheidungen")} Entscheidungen. Das ersetzt alle eigenen Daten.`, "Einlesen", true)) return;
    try {
      const r = await api("/api/restore", body);
      $("#restmsg").innerHTML = `<div class="note go">Eingelesen: ${r.teams} Teams, ${r.favoriten} Favoriten, ${r.gefangen} in der Sammlung, ${r.entscheidungen} Entscheidungen.</div>`;
      S.favGame = null; S.caughtGame = null;
      if (S.team.tid) { S.team.tid = null; S.team.dirty = false; store.set("team", S.team); }
      await Promise.all([loadFavs(true), loadCaught(true)]);
      dock();
    } catch (x) { $("#restmsg").innerHTML = `<div class="note stop">${esc(x.message)}</div>`; }
  });
  if (st.running) setTimeout(() => location.hash.startsWith("#einstellungen") && refreshMeta(), 4000);
}
/* Lesezeichen „Seite untersuchen“ (wie im VR-Navigator): läuft im Browser auf einer fremden Seite (PokéWiki, Serebii,
   GamerGuides, Pokébip …), wo die Karte erst per Skript lädt. Sammelt, was der Server beim Abruf nicht sieht: geladene
   Daten-Dateien samt Inhalt, Daten in globalen Variablen, Kartenmarker, Skripte und das fertige HTML. Ergebnis als Datei;
   nichts geht an einen Server. Muss für sich allein laufen (kein Zugriff auf diese Datei). */
async function probeHelper() {
  const box = document.createElement("div");
  box.style.cssText = "position:fixed;z-index:2147483647;top:12px;right:12px;width:min(420px,90vw);background:#253033;color:#e8eeee;"
    + "border:1px solid #5b7a80;border-radius:8px;padding:12px;font:14px system-ui,sans-serif;box-shadow:0 4px 18px rgba(0,0,0,.5)";
  box.textContent = "Pokédex: warte, bis die Seite fertig geladen hat …";
  document.body.appendChild(box);
  const wait = (t) => new Promise((r) => setTimeout(r, t));
  // Anmeldedaten der Seite (etwa der Benutzername im Wiki) gehören nicht in die Probe; auch in Text mit \"…\"
  const KEYS = "wgUserName|wgUserId|wgUserEmail|wgUserGroups|wgUserRights|wgUserEditCount|wgUserRegistration|csrfToken|editToken|token|userId|username|email";
  const scrub = (t) => String(t).replace(new RegExp(`(\\\\?["']?)\\b(${KEYS})\\1\\s*[:=]\\s*(?:(\\\\?["'])(?:(?!\\3).)*?\\3|-?\\d+|null|\\[[^\\]]*\\])`, "gi"),
    (m, q, k, v) => `${q}${k}${q}:${v || q || '"'}–${v || q || '"'}`);
  await wait(1500);
  const skip = /\.(png|jpe?g|gif|webp|avif|svg|ico|css|woff2?|ttf|mp3|ogg|mp4|webm)(\?|#|$)/i;
  const res = performance.getEntriesByType("resource").map((e) => ({url: e.name, typ: e.initiatorType, bytes: e.transferSize || e.encodedBodySize || 0}));
  const wanted = res.filter((r) => !skip.test(r.url) && (r.typ === "fetch" || r.typ === "xmlhttprequest" || /\.(json|geojson|csv|txt)(\?|$)|api\.php|\/api\//i.test(r.url)));
  const bodies = {};
  let total = 0, i = 0;
  for (const r of wanted.slice(0, 40)) {
    if (total > 6e6) break;
    box.textContent = `Pokédex: lese Daten-Datei ${++i} von ${Math.min(40, wanted.length)} …`;
    try { const t = await (await fetch(r.url, {credentials: "same-origin"})).text(); bodies[r.url] = scrub(t.slice(0, 2e6)); total += bodies[r.url].length; }
    catch (e) { bodies[r.url] = "nicht lesbar: " + e.message; }
  }
  box.textContent = "Pokédex: sammle Variablen und Marker …";
  const fr = document.createElement("iframe");
  fr.style.display = "none"; document.body.appendChild(fr);
  const base = new Set(Object.getOwnPropertyNames(fr.contentWindow)); fr.remove();
  const globals = {};
  for (const k of Object.getOwnPropertyNames(window)) {
    if (base.has(k) || /^(on|webkit)/.test(k)) continue;
    let v; try { v = window[k]; } catch (e) { continue; }
    if (!v || typeof v !== "object" || v instanceof Node) continue;
    try { const j = JSON.stringify(v); if (j && j.length > 100) globals[k] = scrub(j.slice(0, 5e5)); }
    catch (e) { try { globals[k] = "Objekt mit " + Object.keys(v).slice(0, 40).join(", "); } catch (x) { /* fremd */ } }
  }
  const cls = (e) => String(typeof e.className === "string" ? e.className : e.className?.baseVal || "").slice(0, 120);
  const marks = [...document.querySelectorAll(".leaflet-marker-icon,[class*=marker],[class*=Marker],[class*=pin],[data-lat],[data-x],[data-id] > img")].slice(0, 8000)
    .map((e) => ({cls: cls(e), title: e.getAttribute("title") || e.getAttribute("alt") || e.getAttribute("aria-label") || "", style: (e.getAttribute("style") || "").slice(0, 200),
      data: Object.assign({}, e.dataset), src: (e.getAttribute("src") || "").slice(0, 200), text: (e.innerText || "").trim().slice(0, 80)}));
  const scripts = [...document.scripts].map((x) => scrub(x.src || `inline, ${x.textContent.length} Zeichen: ${x.textContent.slice(0, 400)}`));
  box.remove();
  const html = scrub(document.documentElement.outerHTML.slice(0, 3e6));
  document.body.appendChild(box);
  const txt = JSON.stringify({art: "pokedex-probe", fassung: 1, am: new Date().toISOString(), url: location.href, titel: document.title,
    ressourcen: res, inhalte: bodies, variablen: globals, marker: marks, skripte: scripts, html});
  const host = location.hostname.replace(/^www\./, "").replace(/[^a-z0-9.-]/gi, "");
  const name = `pokedex-probe-${host}-${(location.pathname.split("/").filter(Boolean).pop() || "start").replace(/[^\w.-]/g, "_").slice(0, 60)}.json`;
  box.textContent = "";
  const p = document.createElement("p");
  p.style.margin = "0 0 8px";
  p.textContent = `Gelesen: ${wanted.length} Daten-Dateien, ${Object.keys(globals).length} Variablen, ${marks.length} Marker, ${Math.round(txt.length / 1024)} KB. `
    + "Datei sichern und in den Testdaten-Ordner legen; sie enthält nur, was diese Seite zeigt.";
  const btn = (t, main) => { const b = document.createElement("button"); b.textContent = t;
    b.style.cssText = "margin:0 8px 0 0;padding:6px 12px;border-radius:6px;font:600 13px system-ui,sans-serif;cursor:pointer;border:1px solid #5b7a80;"
      + (main ? "background:#3f8f86;color:#fff" : "background:#1c2426;color:#e8eeee"); return b; };
  const f = btn("Als Datei sichern", true);
  f.onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([txt], {type: "application/json"})); a.download = name;
    document.body.appendChild(a); a.click(); a.remove(); };
  const c = btn("Schließen");
  c.onclick = () => box.remove();
  box.append(p, f, c);
}
const probeBm = () => "javascript:" + encodeURIComponent(`(${probeHelper})()`);
async function copyText(txt, btn) {
  try { await navigator.clipboard.writeText(txt); }
  catch (e) {     // ohne HTTPS gibt es die Zwischenablage-Schnittstelle nicht; dann der alte Weg
    const ta = document.createElement("textarea");
    ta.value = txt; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove();
  }
  const old = btn.textContent;
  btn.textContent = "Kopiert ✓";
  setTimeout(() => { btn.textContent = old; }, 1500);
}
function download(name, txt, type = "text/plain") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([txt], {type: type + ";charset=utf-8"}));
  a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
async function diag() {
  await api("/api/diag", {});
  const poll = async () => {
    const d = await api("/api/diag");
    const el = $("#diag");
    if (!el) return;
    if (d.running) { el.innerHTML = `<p class="hint">Läuft …</p>`; setTimeout(poll, 1500); return; }
    el.innerHTML = `<div class="log" id="dlog">${esc((d.lines || []).join("\n") || d.error)}</div>`;
    // Kopieren und Herunterladen erst, wenn es ein Ergebnis gibt
    $("#dlinks").innerHTML = (d.lines || []).length ? `<button class="link" data-act="copy" data-src="#dlog">Ergebnis kopieren</button> <button class="link" data-act="dl" data-src="#dlog" data-name="pokedex-verbindungstest">herunterladen</button>`
      + (d.proben ? ` <a href="/api/diag/proben" download data-tip="Gekürzte Rohseiten der Quellen (${d.proben}), aus denen sich Leser für sie bauen lassen">Proben herunterladen</a>` : "") : "";
  };
  poll();
}

/* ------------------------------------------------------------------ Klicks */
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]");
  if (!b) return;
  const act = b.dataset.act, id = +b.dataset.id;
  if (b.closest("a")) e.preventDefault();       // „+“ auf einer Karte öffnet nicht die Detailseite
  try {
    if (act === "thm") themeMenu($("#thmMenu").hidden);
    else if (act === "thmset") setTheme(b.dataset.v);
    else if (act === "neu") versionsDialog();
    else if (act === "neuok") { try { localStorage.setItem("px.version", S.meta.version); } catch (x) { /* egal */ } version(); }
    else if (act === "dock") { S.dock = !S.dock; store.set("dock", S.dock); $("#dock")?.classList.remove("fold"); dock(); }
    else if (act === "teamadd") {
      const slot = addToTeam(id);
      if (slot !== null && location.hash.startsWith("#pokemon/")) location.hash = `#pokemon/${id}/${slot}`;
    } else if (act === "teamdel") { removeSlot(+b.dataset.slot); if (location.hash.startsWith("#pokemon/")) location.hash = `#pokemon/${DETAIL?.id || ""}`; }
    else if (act === "fav") await toggleFav(id);
    else if (act === "favadd") { $("#pick").hidden = true; await toggleFav(id, true); }
    else if (act === "caught") await toggleCaught(id);
    else if (act === "alpha") await toggleAlpha(id);
    else if (act === "xsel") xsel(id);
    else if (act === "xall") $$("#list .mon[data-id]").forEach((el) => xsel(+el.dataset.id, true));
    else if (act === "xnone") [...XSEL].forEach((x) => xsel(x, false));
    else if (act === "xgo") await xferGo();
    else if (act === "pick") picker(b, +b.dataset.slot);
    else if (act === "pickfav") { $("#pick").hidden = true; addToTeam(id, +b.dataset.slot); }
    else if (act === "tgame") setGame(S.team.spiel);
    else if (act === "unpin") { PIN.r = null; PIN.c = null; chartView(); }
    else if (act === "copy") await copyText($(b.dataset.src)?.textContent || "", b);
    else if (act === "dl") download(`${b.dataset.name}-${new Date().toISOString().slice(0, 10)}.txt`, $(b.dataset.src)?.textContent || "");
    else if (act === "pin") {
      S.team.fest = S.team.fest.includes(id) ? S.team.fest.filter((x) => x !== id) : [...S.team.fest, id];
      saveTeam(); dock(); teamRefresh();
    } else if (act === "freset") {
      const which = b.dataset.fid === "lf" ? "filter" : "tfilter";
      S[which] = filter0(which === "tfilter" ? {endstufe: true} : {});
      store.set(which === "filter" ? "filter2" : "tfilter", S[which]);
      route();
    } else if (act === "opt") await optimize();
    else if (act === "sdexp") await sdExport();
    else if (act === "sdimp") await sdImport();
    else if (act === "sdcopy") await copyText($("#sdtext").value, b);
    else if (act === "take") {
      const ids = S.lastOpt[+b.dataset.i].ids, old = S.team;
      // Level und Attacken bleiben bei Pokémon, die schon im Team waren
      S.team.details = ids.map((x) => { const i = old.ids.indexOf(x); return i >= 0 ? old.details[i] : {}; });
      S.team.ids = ids;
      teamChanged();
      ids.forEach((x, i) => fillStandard(i));
    } else if (act === "tclear") { Object.assign(S.team, {ids: [], fest: [], details: []}); teamChanged(); teamView(); }
    else if (act === "tnew") {
      if (S.team.dirty && !await ask(S.team.name ? `„${S.team.name}“ hat ungespeicherte Änderungen.` : "Das Team hat ungespeicherte Änderungen.", "Trotzdem ein neues Team beginnen? Die Änderungen gehen verloren.", "Neues Team")) return;
      S.team = normTeam({spiel: S.game});
      store.set("team", S.team); dock(); location.hash.startsWith("#team") ? teamView() : (location.hash = "#team");
    } else if (act === "tsave" && S.team.tid) { await saveToServer(); dock(); if (location.hash.startsWith("#team")) teamView(); }
    else if (act === "tsave" || act === "tsaveas" || act === "trename") {
      const name = await askText(act === "trename" ? "Team umbenennen" : "Team speichern", "Name des Teams", act === "tsaveas" && S.team.tid ? S.team.name + " (Kopie)" : S.team.name || "Team " + gameName(), act === "trename" ? "Umbenennen" : "Speichern");
      if (!name) return;
      if (act === "trename") { S.team.name = name; await saveToServer(name); }
      else await saveToServer(name, act === "tsaveas");
      dock(); if (location.hash.startsWith("#team")) teamView();
    } else if (act === "tundo") {
      const tt = (await api("/api/teams")).find((x) => x.id === S.team.tid);
      if (tt) loadTeam(tt); else { S.team.dirty = false; store.set("team", S.team); }
      dock(); if (!location.hash.startsWith("#team")) route();
    } else if (act === "tdel") {
      if (!await ask(`Team „${S.team.name}“ löschen?`, "Das gespeicherte Team geht verloren; die Plätze bleiben als ungespeichertes Team stehen.", "Löschen", true)) return;
      await api("/api/teams/loeschen", {id: S.team.tid});
      S.team = normTeam({ids: S.team.ids, fest: S.team.fest, details: S.team.details});
      store.set("team", S.team); dock(); teamView();
    } else if (act === "foedel") { S.foes = S.foes.filter((x) => x !== id); store.set("foes", S.foes); matchup(); }
    else if (act === "foeclear") { S.foes = []; store.set("foes", S.foes); teamView(); }
    else if (act === "mvadd" || act === "mvdel" || act === "mvtake") {
      const pid = DETAIL.id, cur = ownSet(pid), mid = +b.dataset.mid;
      setOwnSet(pid, act === "mvadd" ? [...cur, mid] : act === "mvdel" ? cur.filter((x) => x !== mid) : DETAIL.attacken.moveset.map((m) => m.id));
      renderMoves(DETAIL.attacken, $("#lvl")?.value);
    } else if (act === "mvstd") {
      setOwnSet(DETAIL.id, DETAIL.attacken.standard || []);
      renderMoves(DETAIL.attacken, $("#lvl")?.value);
    } else if (act === "mreset") { store.set("mfilter2", {}); movesView(); }
    else if (act === "sync" || act === "rebuild") {
      await api("/api/abgleich", {neu: act === "rebuild"});
      setTimeout(refreshMeta, 800);
    } else if (act === "diag") await diag();
    else if (act === "nobm") { b.dataset.tip = "Nicht hier klicken: in die Lesezeichenleiste ziehen und auf der fremden Seite anklicken"; }
    else if (act === "bmcopy") await copyText(probeBm(), b);
    else if (act === "todotask") {
      const t = await api("/api/aufgabe");
      if (t.text) await copyText(t.text, b);
    } else if (act === "todoans") { $("#todoans").hidden = !$("#todoans").hidden; if (!$("#todoans").hidden) $("#todotext").focus(); }
    else if (act === "todocsv") {
      const cell = (v) => { v = String(v ?? ""); return /[";\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v; };
      const rows = (await api("/api/pruefung")).filter((x) => !x.entscheidung).map((x) => [x.name, x.feld, x.pokeapi, x.showdown, x.key]);
      download(`pokedex-zu-erledigen-${new Date().toISOString().slice(0, 10)}.csv`, "\ufeff" + [["Was", "Feld", "PokéAPI", "Showdown", "Kennung"], ...rows].map((x) => x.map(cell).join(";")).join("\r\n"), "text/csv");
    } else if (act === "todoprev" || act === "todotake") {
      const out = $("#todoprev");
      try {
        const res = await api("/api/antwort", {text: $("#todotext").value, dry: act === "todoprev"});
        if (act === "todotake") { settingsView(); return; }
        const W = {pokeapi: "PokéAPI", showdown: "Showdown", egal: "egal"};
        out.innerHTML = (res.uebernehmen.length ? `<table class="rows"><tr><th>Was</th><th>Feld</th><th>Antwort</th><th>Grund</th></tr>${res.uebernehmen.map((x) => `<tr><td>${esc(x.name)}</td><td>${esc(x.feld)}</td><td><b>${W[x.wert]}</b></td>
            <td class="why">${esc(x.grund)}${/^https:\/\/\S+$/.test(x.quelle) ? ` <a href="${esc(x.quelle)}" target="_blank" rel="noopener noreferrer">Quelle</a>` : ""}</td></tr>`).join("")}</table>` : "")
          + (res.liegen.length ? `<p class="hint">Bleibt liegen: ${res.liegen.map((x) => `${esc(x.key)} (${esc(x.warum)})`).join(", ")}</p>` : "")
          + (res.uebernehmen.length ? `<div class="bar slim"><button class="primary" data-act="todotake">${res.uebernehmen.length} übernehmen</button></div>` : `<div class="note warn">Nichts zu übernehmen.</div>`);
      } catch (x) { out.innerHTML = `<div class="note stop">${esc(x.message)}</div>`; }
    }
    else if (act === "mvclear") { const id = DETAIL?.id; if (id != null) { setOwnSet(id, []); renderMoves(DETAIL.attacken, $("#lvl")?.value); } }
    else if (act === "dec") {
      await api("/api/entscheidung", {art: "pruefung", schluessel: b.dataset.k, wert: b.dataset.v});
      settingsView();
    }
  } catch (err) { alert(err.message); }
});
document.addEventListener("change", (e) => { if (e.target.matches("select.gamesel")) setGame(e.target.value); });
// Titel: zur Liste und alles neu laden (Spieldaten, Favoriten, Typtabelle)
$("#home").addEventListener("click", (e) => {
  e.preventDefault();
  if (location.hash !== "#pokemon") history.pushState(null, "", "#pokemon");
  S.chart = null; LS.key = ""; CHECK.key = "";
  window.scrollTo(0, 0);
  refreshMeta();
});
window.addEventListener("hashchange", route);
refreshMeta().catch((e) => { main.innerHTML = `<div class="note stop">Server nicht erreichbar: ${esc(e.message)}</div>`; });
