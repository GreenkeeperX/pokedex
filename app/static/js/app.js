/* Pokédex-Oberfläche: reines JavaScript ohne Build. Reiter über die Adresse (#pokemon, #pokemon/6, #team, #attacken,
   #typen, #einstellungen), deshalb öffnet „In neuem Tab öffnen“ jede Karte. Gewähltes Spiel, Filter und das aktuelle
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
  kampf: false, gen: "", genmodus: "bis", min: "", nur: ""}, extra);
const S = {
  meta: null, types: {}, chart: null, chartGame: null,
  game: store.get("game", "legends-arceus"),
  team: normTeam(store.get("team", {})), favs: [], favGame: null, caught: new Set(), tsort: "",
  weights: store.get("weights", null), preset: store.get("preset", "ausgewogen"),
  filter: filter0(store.get("filter2", {})),
  tfilter: filter0(Object.assign({endstufe: true}, store.get("tfilter", {}))),
  tleg: store.get("tleg", true), dock: store.get("dock", window.innerWidth > 700), foes: store.get("foes", []),
};
const TABS = [["pokemon", "Pokémon"], ["team", "Team"], ["attacken", "Attacken"], ["typen", "Typen"], ["einstellungen", "Einstellungen"]];
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
  ball: '<path class="top" d="M1.9 8a6.1 6.1 0 0 1 12.2 0h-3.9a2.2 2.2 0 0 0-4.4 0Z"/><circle cx="8" cy="8" r="6.1"/><path d="M1.9 8h3.9M10.2 8h3.9"/><circle cx="8" cy="8" r="2.2"/>',
  team: '<path d="M3.1 8.5 6.6 11.9 12.9 4.3"/>', plus: '<path d="M8 3v10M3 8h10"/>'};
const icon = (k, on = true) => `<svg class="ic ic-${k}${on ? " on" : ""}" viewBox="0 0 16 16" aria-hidden="true">${ICON[k]}</svg>`;
const SVG = (d) => `<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">${d}</svg>`;
const tchip = (t) => `<span class="t t${t}" data-tip-type="${t}">${esc(tname(t))}</span>`;
const tchips = (ts) => (ts || []).map(tchip).join("");
const img = (id, cls = "", art = false) => `<img class="spr ${cls}" src="${art ? "artwork" : "sprites"}/${id}.png" alt="" loading="lazy" draggable="false" onerror="this.onerror=null;this.src='icon.svg';this.classList.add('none')">`;

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
  const pad = big ? 36 : 10, r = size / 2 - pad, c = size / 2;
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
const radarTip = (werte) => "Netzdiagramm: außen = Höchstwert aller Pokémon, Ringe bei 25, 50 und 75 %. Zahlen: Skala 0 bis 10.\n"
  + RADAR_ORDER.map((i) => `${STAT[i]} ${werte[i]} (${scale10(i, werte[i])}/10, Höchstwert ${statMax(i)})`).join("\n");

const teamFull = () => S.team.ids.length >= 6;
const isFav = (id) => S.favs.some((f) => f.id === id);
const isCaught = (id) => S.caught.has(id);
/* Marken direkt hinter dem Namen, nur die gesetzten (im Team, gefangen, Favorit). Zum Setzen erscheinen beim Hovern
   kleine Knöpfe unten auf dem Bild; so verdeckt nichts das Netzdiagramm und nichts verschiebt sich */
function marks(id) {
  const inTeam = S.team.ids.includes(id), fav = isFav(id), got = isCaught(id);
  return `<span class="mk">${inTeam ? `<span class="m m-team" data-tip="Im Team">${icon("team")}</span>` : ""}`
    + `${got ? `<span class="m m-ball" data-tip="Gefangen in ${esc(gameName())}">${icon("ball")}</span>` : ""}`
    + `${fav ? `<span class="m m-fav" data-tip="Favorit">${icon("fav")}</span>` : ""}</span>`;
}
function acts(id) {
  const inTeam = S.team.ids.includes(id), fav = isFav(id), got = isCaught(id);
  return `<span class="acts"><span class="a${got ? " on" : ""}" data-act="caught" data-id="${id}" data-tip="${got ? "Gefangen; Klick: doch nicht" : "Als gefangen markieren"}">${icon("ball", got)}</span>`
    + `<span class="a${fav ? " on" : ""}" data-act="fav" data-id="${id}" data-tip="${fav ? "Favorit; Klick: aus den Favoriten" : "Zu den Favoriten (Kader zum schnellen Tauschen)"}">${icon("fav", fav)}</span>`
    + `${teamFull() ? "" : `<span class="a plus" data-act="teamadd" data-id="${id}" data-tip="${inTeam ? "Noch einmal ins Team" : "Ins Team"}">${icon("plus")}</span>`}</span>`;
}
function monCard(r) {
  const inTeam = S.team.ids.includes(r.id);
  return `<a class="mon${inTeam ? " inteam" : ""}" href="#pokemon/${r.id}" draggable="true" data-id="${r.id}"><span class="sp">${img(r.id)}${acts(r.id)}</span>
    <span class="mi"><span class="nl"><span class="n">${esc(r.name)}</span>${marks(r.id)}</span><span class="ty">${tchips(r.typen)}</span>
    <span class="s">#${r.nr ?? r.art} · Basiswerte <b style="color:${sumColor(r.summe)}">${r.summe}</b>${r.legendaer ? " · legendär" : ""}</span></span>
    ${radar(r.werte)}</a>`;
}
// Marken überall neu zeichnen, ohne die Seite neu aufzubauen
function redrawMarks() {
  $$(".mk").forEach((el) => { const a = el.closest("[data-id]"); if (a) el.outerHTML = marks(+a.dataset.id); });
  $$(".acts").forEach((el) => { const a = el.closest("[data-id]"); if (a) el.outerHTML = acts(+a.dataset.id); });
  $$("[data-markbtn]").forEach((b) => { const id = +b.dataset.id, k = b.dataset.markbtn, on = k === "fav" ? isFav(id) : isCaught(id);
    b.classList.toggle("on", on); b.innerHTML = markLabel(k, on); });
  $$(".mon[data-id]").forEach((el) => el.classList.toggle("inteam", S.team.ids.includes(+el.dataset.id)));
}
const markLabel = (k, on) => k === "fav" ? `${icon("fav", on)} ${on ? "Favorit" : "Zu den Favoriten"}` : `${icon("ball", on)} ${on ? "Gefangen" : "Als gefangen markieren"}`;

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
const DUEL = {2: "klar stark", 1: "stark", 0: "ausgeglichen", "-1": "schwer"};
function duelTip(name, own, t, x) {
  const parts = own.map((d) => `${tname(t)} gegen ${tname(d)} ×${fl(S.chart?.[t]?.[d] ?? 1)}`);
  return `${name} gegen ${tname(t)}: ${DUEL[x.level]}\nAusteilen: ${tname(x.best)} trifft ${tname(t)} ×${fl(x.dealt)}\n`
    + `Einstecken: ${tname(t)}-Attacken treffen ×${fl(x.taken)}${own.length > 1 ? `\n(${parts.join(", ")})` : ""}`;
}
function duelHtml(name, own, short = false) {
  const xs = Object.keys(S.chart || {}).map((t) => [t, duel(own, t)]);
  const pick = (lv) => xs.filter(([, x]) => x.level === lv);
  const row = (lv) => pick(lv).map(([t, x]) => `<span class="fx" data-tip="${esc(duelTip(name, own, t, x))}">${tchip(t)}</span>`).join("");
  const out = [[2, "Klar stark gegen", "trifft sehr effektiv und steckt höchstens ½ ein"], [1, "Stark gegen", "trifft sehr effektiv, steckt normal ein"],
    [-1, "Schwer gegen", "steckt sehr effektiv ein und trifft selbst höchstens normal"]].filter(([lv]) => pick(lv).length)
    .map(([lv, title, why]) => short ? `<div class="muted" data-tip="${esc(why)}">${title}</div>${row(lv)}` : `<h3 data-tip="${esc(why)}">${title}</h3><div class="eff">${row(lv)}</div>`);
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
  const t = e.target.closest("[data-tip],[data-tip-type],[data-tip-cell]");
  if (t) {
    clearTimeout(tipTimer);
    tipTimer = setTimeout(() => {
      if (t.dataset.tipType) tip.innerHTML = typeTipHtml(t.dataset.tipType);
      else if (t.dataset.tipCell) tip.innerHTML = cellTip(...t.dataset.tipCell.split(":"));
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
  const t = e.target.closest("[data-tip],[data-tip-type],[data-tip-cell]");
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
  const by = (pred) => Object.entries(d).filter(([, f]) => pred(f)).sort((a, b) => b[1] - a[1]);
  const fx = (xs) => xs.map(([t, f]) => `<span class="fx">${tchip(t)}<span class="f ${fcls(f)}">×${fl(f)}</span></span>`).join("") || `<span class="muted">keine</span>`;
  const det = slot !== null ? S.team.details[slot] || {} : null;
  const mv = det ? (det.attacken || []).map((x) => MOVES[x]).filter(Boolean) : [];
  card.innerHTML = `<div class="hc-head">${img(r.id, "art", true)}<div><b>${esc(r.name)}</b> <span class="muted">#${r.nr ?? r.art}</span><div>${tchips(r.typen)}</div>
      <div class="muted">Basiswerte <b style="color:${sumColor(r.summe)}">${r.summe}</b>${r.legendaer ? " · legendär" : ""}${r.endstufe ? " · Endstufe" : ""}</div>
      ${det ? `<div class="muted">${det.level ? "Level " + det.level : "ohne Level"}</div><div class="hc-mv">${mv.map((m) => `${tchip(m.typ)} ${esc(m.name)}`).join("<br>")}</div>` : ""}</div></div>
    <div class="hc-body">${radar(r.werte, 190, true)}<div class="hc-eff"><div class="muted">Schwach gegen</div>${fx(by((f) => f > 1))}
      <div class="muted">Resistent / immun</div>${fx(by((f) => f < 1))}
      ${duelHtml(r.name, r.typen, true)}</div></div>`;
  card.hidden = false;
  place(card, el);
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
  const dir = !th.dataset.dir ? "desc" : th.dataset.dir === "desc" ? "asc" : "";
  $$("th", table).forEach((x) => delete x.dataset.dir);
  if (dir) th.dataset.dir = dir;
  const key = (tr) => { const c = tr.cells[i]; const v = c?.dataset.s ?? c?.textContent.trim() ?? ""; const n = parseFloat(v); return isNaN(n) || v === "" ? v.toLowerCase() : n; };
  rows.sort((a, b) => {
    if (!dir) return a.dataset.o - b.dataset.o;
    const x = key(a), y = key(b); const r = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "de");
    return dir === "asc" ? r : -r;
  });
  rows.forEach((r) => tb.appendChild(r));
});
const th = (label, tipText = "", noSort = false) => `<th${noSort ? "" : " data-sort"}${tipText ? ` data-tip="${esc(tipText)}"` : ""}>${label}</th>`;

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
function gameOptions() {
  const gs = S.meta?.spiele || [], groups = [];
  gs.forEach((g) => { if (!groups.length || groups.at(-1)[0] !== g.gen) groups.push([g.gen, []]); groups.at(-1)[1].push(g); });
  return `<option value="">Alle Spiele (neueste Werte)</option>` + groups.map(([gen, xs]) => `<optgroup label="Generation ${gen}">`
    + xs.map((g) => `<option value="${esc(g.kennung)}">${esc(g.name)}</option>`).join("") + `</optgroup>`).join("");
}
function header() {
  const gs = S.meta?.spiele || [];
  const opts = gameOptions();
  $$("select.gamesel").forEach((sel) => { sel.innerHTML = opts; sel.value = gs.some((g) => g.kennung === S.game) ? S.game : ""; });
  const a = S.meta?.abgleich || {}, last = a.finished || a.started;
  const stale = last && Date.now() - new Date(last) > 2 * (S.meta?.einstellungen?.tage || 7) * 86400000;
  $("#meta").innerHTML = !S.meta?.has_data ? (a.running ? "Erster Abgleich läuft …" : "Noch keine Daten")
    : `${S.meta.formen} Pokémon und Formen · ${S.meta.attacken} Attacken · ${gs.length} Spiele`
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
  $("#nav").innerHTML = TABS.map(([k, n]) => `<a href="#${k}" class="${k === tab ? "on" : ""}">${n}</a>`).join("");
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
  try {
    if (!S.meta?.has_data && tab !== "einstellungen") return noData();
    await Promise.all([loadChart(), loadFavs(), loadCaught()]);
    if (tab === "pokemon" && arg) await detailView(+arg, arg2 === undefined ? null : +arg2);
    else if (tab === "pokemon") await listView();
    else if (tab === "team") await teamView();
    else if (tab === "attacken") await movesView();
    else if (tab === "typen") await chartView();
    else if (tab === "einstellungen") await settingsView();
    else location.hash = "pokemon";
  } catch (e) {
    main.innerHTML = `<div class="note stop">Fehler: ${esc(e.message)}</div>`;
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
  S.caught = new Set(await api("/api/gefangen?" + qs({spiel: S.game})));
  S.caughtGame = S.game;
}
async function toggleCaught(id) {
  const on = !isCaught(id);
  await api("/api/gefangen", {spiel: S.game, id, an: on});
  if (on) S.caught.add(id); else S.caught.delete(id);
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
      <label data-tip="Nur deine Favoriten (Stern) oder Gefangenen (Pokéball) im gewählten Spiel"><select data-f="nur"><option value="">alle Pokémon</option><option value="fav"${f.nur === "fav" ? " selected" : ""}>nur Favoriten</option><option value="gef"${f.nur === "gef" ? " selected" : ""}>nur Gefangene</option></select></label>
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
  gen: f.gen, genmodus: f.gen && f.genmodus === "nur" ? "nur" : "", min: f.min, modus: f.modus, nur: f.nur || "", klar: f.art === "gegen" && f.klar ? 1 : "",
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
async function listView() {
  main.innerHTML = filterBar(S.filter, "lf") + `<div class="list" id="list"></div><div class="more" id="more"></div>`;
  bindFilter(S.filter, "lf", () => loadList(true), () => store.set("filter2", S.filter));
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
    const html = d.rows.map(monCard).join("");
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
let CHECK = {key: "", nicht: []};
function teamCheck() {
  const key = S.game + "|" + S.team.ids.join(",") + "|" + JSON.stringify(S.team.details.map((d) => d.attacken || []));
  if (CHECK.key === key || teamCheck.busy) return;
  teamCheck.busy = true;
  api("/api/team/bewerten", {spiel: S.game, ids: S.team.ids, details: S.team.details, kurz: 1}).then((ev) => {
    (ev.mitglieder || []).forEach((m) => { ROWS[m.id] = Object.assign(ROWS[m.id] || {}, m); });
    Object.entries(ev.attacken || {}).forEach(([k, m]) => { MOVES[k] = Object.assign(MOVES[k] || {}, m, {id: +k}); });
    CHECK = {key, nicht: ev.nicht_im_spiel || []};
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
const wikiLink = (q, label = "↗") => `<a class="wl" href="${esc(wikiUrl(q))}" target="_blank" rel="noopener noreferrer" data-tip="${esc(q)} im PokéWiki">${label}</a>`;
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
  const eff = Object.entries(d.wirkung).sort((a, b) => b[1] - a[1] || a[0] - b[0]);
  const effHtml = (pred, title) => {
    const xs = eff.filter(([, f]) => pred(f));
    return xs.length ? `<h3>${title}</h3><div class="eff">${xs.map(([t, f]) => `<div data-tip="${esc(`${tname(t)}-Attacken treffen ${d.name} mit ×${fl(f)}`)}">${tchip(t)}<span class="f ${fcls(f)}">×${fl(f)}</span></div>`).join("")}</div>` : "";
  };
  const evo = d.entwicklung.length > 1 ? d.entwicklung.map((e, i) => (i && e.von ? `<span class="ar">→ ${esc(e.bedingungen.join(" oder ") || "")}</span>` : "") +
    `<a class="st" href="#pokemon/${e.id}">${img(e.id)}${esc(e.name)}</a>`).join("") : "";
  main.innerHTML = `
    <div class="bar">${backLink()}
      <label class="game2">Spiel <select class="gamesel"></select></label>
      ${inTeam ? `<button data-act="teamdel" data-slot="${DSLOT}">Aus dem Team nehmen</button>` : ""}
      ${teamFull() ? (inTeam ? "" : `<span class="hint">Team voll</span>`) : `<button class="${inTeam ? "" : "primary"}" data-act="teamadd" data-id="${d.id}">${inTeam ? "Noch einmal ins Team" : "Ins Team"}</button>`}
      <button data-act="fav" data-id="${d.id}" data-markbtn="fav" class="mark${isFav(d.id) ? " on" : ""}">${markLabel("fav", isFav(d.id))}</button>
      <button data-act="caught" data-id="${d.id}" data-markbtn="gef" class="mark${isCaught(d.id) ? " on" : ""}">${markLabel("gef", isCaught(d.id))}</button>
      <a href="${esc(d.wiki)}" target="_blank" rel="noopener noreferrer">Im PokéWiki öffnen ↗</a>
      ${d.formen.length ? `<span class="hint">Formen:</span>` + d.formen.map((f) => `<a class="btn small" href="#pokemon/${f.id}">${esc(f.name)}</a>`).join("") : ""}</div>
    ${!d.im_spiel && S.game ? `<div class="note warn">In ${esc(gameName())} nicht enthalten.</div>` : ""}
    ${inTeam && S.team.ids.filter((x) => x === id).length > 1 ? `<div class="note info">${esc(d.name)} ist mehrmals im Team; hier geht es um Platz ${DSLOT + 1}.</div>` : ""}
    <div class="cols">
      <div class="box"><div class="head">${img(d.id, "big", true)}<div><h2>${esc(d.name)}</h2><div class="muted">#${d.nr ?? d.art} · ${esc(d.kategorie)}</div>
        <div style="margin-top:4px">${tchips(d.typen)}</div><span data-tip="${esc(radarTip(d.werte))}">${radar(d.werte, 220, true)}</span></div></div>
        <p>${esc(d.text)}</p><div class="stats">${stats}<span><b>Summe</b></span><span class="num" data-tip="${esc(statTip("summe", d.summe))}"><b style="color:${sumColor(d.summe)}">${d.summe}</b></span><span></span></div>
        ${d.faehigkeiten.length ? `<h3>Fähigkeiten</h3>` + d.faehigkeiten.map((a) => `<div><b>${esc(a.name)}</b> ${wikiLink(a.name)}${a.versteckt ? " <span class='cls'>versteckt</span>" : ""}${a.wirkt ? " <span class='cls'>ändert Typwirkung</span>" : ""}<div class="why">${esc(a.text)}</div></div>`).join("")
          : S.game === "legends-arceus" ? `<p class="hint">In Legenden: Arceus gibt es keine Fähigkeiten.</p>` : ""}
      </div>
      <div class="box"><h2>Typwirkung gegen ${esc(d.name)}</h2>
        ${d.faehigkeit_wirkt ? `<p class="hint">Mit Fähigkeit eingerechnet.</p>` : ""}
        ${effHtml((f) => f > 1, "Schwach gegen")}${effHtml((f) => f > 0 && f < 1, "Resistent gegen")}${effHtml((f) => f === 0, "Immun gegen (keine Wirkung)")}
        <h2 style="margin-top:14px" data-tip="Typ-Duell: wie gut ${esc(d.name)} gegen Pokémon eines Typs steht. Austeilen = bester eigener Typ, einstecken = beide eigenen Typen zusammengerechnet. Hovern zeigt die Rechnung.">Im Duell gegen Typen</h2>
        ${duelHtml(d.name, d.typen)}
        ${evo ? `<h3>Entwicklung</h3><div class="evo">${evo}</div>` : ""}
      </div>
    </div>
    <div class="box" style="margin-top:12px"><h2>Fundorte in ${esc(gameName())}</h2>
      ${d.fundorte.length ? `<div class="scroll"><table class="sort"><thead><tr>${th("Ort")}${th("Methode")}${th("Level")}${th("Bedingungen")}${th("Edition")}</tr></thead><tbody>
        ${d.fundorte.map((e) => `<tr><td>${esc(e.ort)} ${wikiLink(e.ort)}</td><td>${esc(e.methode)}</td><td data-s="${parseInt(e.level) || 0}">${esc(e.level)}</td><td>${esc(e.bedingungen.join(", "))}</td><td>${esc(e.editionen.join(", "))}</td></tr>`).join("")}</tbody></table></div>`
        : `<p class="hint">${S.game ? "Die PokéAPI kennt hier keine Fundorte" + (["legends-arceus", "scarlet-violet", "legends-za"].includes(S.game) ? " (für dieses Spiel liefert sie keine; kommt mit dem PokéWiki-Abruf)" : "") + `. Bis dahin: <a href="${esc(d.wiki)}" target="_blank" rel="noopener noreferrer">Fundorte im PokéWiki ↗</a>` : "Wähle oben ein Spiel."}</p>`}
    </div>
    <div class="box" id="mbox"></div>`;
  header();
  renderMoves(d.attacken, level);
  window.scrollTo(0, 0);
}
// Farben für Werte: Stärke (bis 150), Genauigkeit (ab 70), Wertung (bis 160), von Rot nach Grün
const ramp = (x) => `hsl(${Math.max(0, Math.min(1, x)) * 125} 62% 40%)`;
const powCell = (v) => v ? `<span style="color:${ramp((v - 30) / 100)}">${v}</span>` : "–";
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
function renderMoves(A, level) {
  const d = DETAIL, id = d.id, inTeam = DSLOT !== null;
  const all = Object.fromEntries([...A.attacken, ...A.status].map((m) => [m.id, m]));
  const mine = ownSet(id).filter((x) => all[x] || MOVES[x]);
  const mv = (x) => all[x] || MOVES[x];
  const covered = new Set();
  mine.map(mv).filter((m) => m.klasse !== 1 && m.staerke).forEach((m) => Object.entries(S.chart?.[m.typ] || {}).forEach(([t, f]) => f > 1 && covered.add(t)));
  const mrow = (m, status = false) => `<tr class="${m.jetzt === false ? "off" : ""}${mine.includes(m.id) ? " sel" : ""}"><td data-s="${esc(m.name)}"${m.text ? ` data-tip="${esc(m.text)}"` : ""}>${esc(m.name)} ${wikiLink(m.name)}${m.geaendert ? ' <span class="cls" data-tip="Werte in diesem Spiel anders als heute">Spielwert</span>' : ""}</td>
    <td data-s="${tname(m.typ)}">${tchip(m.typ)}</td><td><span class="cls">${CLS[m.klasse] || ""}</span></td><td class="num" data-s="${m.staerke ?? 0}">${powCell(m.staerke)}</td><td class="num" data-s="${m.genauigkeit ?? 101}">${accCell(m.genauigkeit)}</td>
    ${status ? "" : `<td class="num" data-s="${m.wertung}"><b style="color:${scoreColor(m.wertung)}">${m.wertung}</b></td>`}<td data-s="${esc(m.wege[0] || "")}">${esc(m.wege.join(", "))}</td><td class="why">${esc(status ? m.text || "" : m.gruende.join(" · "))}</td>
    <td>${mine.includes(m.id) ? `<button class="small on" data-act="mvdel" data-mid="${m.id}" data-tip="Aus deiner Auswahl">✓</button>` : mine.length < 4 ? `<button class="small" data-act="mvadd" data-mid="${m.id}" data-tip="In deine Auswahl (4 Plätze)">+</button>` : ""}</td></tr>`;
  const std = (A.standard || []).map((x) => all[x]?.name).filter(Boolean);
  // Deine Auswahl als feste Tabelle mit vier Zeilen: springt nicht, wenn Attacken dazukommen oder gehen
  const mineRow = (i) => {
    const m = mv(mine[i]);
    if (!m) return `<tr class="mvchip empty" data-i="${i}"><td class="grip"></td><td colspan="7" class="hint">Platz ${i + 1}: mit + in der Tabelle wählen</td></tr>`;
    const r = all[m.id];
    return `<tr class="mvchip" draggable="true" data-i="${i}"><td class="grip" data-tip="Ziehen zum Umsortieren">⋮⋮</td><td>${tchip(m.typ)}</td>
      <td${m.text ? ` data-tip="${esc(m.text)}"` : ""}><b>${esc(m.name)}</b>${r ? "" : ` <span class="cls" data-tip="Nicht in der Lernliste dieses Spiels (TM, Lehrer, Trainingsgelände)">beigebracht</span>`}</td>
      <td><span class="cls">${CLS[m.klasse] || ""}</span></td><td class="num">${powCell(m.staerke)}</td><td class="num">${accCell(m.genauigkeit)}</td>
      <td class="num">${r?.wertung ? `<b style="color:${scoreColor(r.wertung)}">${r.wertung}</b>` : ""}</td>
      <td><button class="link" data-act="mvdel" data-mid="${m.id}" data-tip="Aus deiner Auswahl">✕</button></td></tr>`;
  };
  $("#mbox").innerHTML = `<h2>Attacken${A.spiel_name ? " in " + esc(A.spiel_name) : ""}</h2>
    ${A.hinweis ? `<div class="note info">${esc(A.hinweis)}</div>` : ""}
    <div class="bar"><label>${inTeam ? "Level im Team" : "Bis Level"} <input id="lvl" type="number" min="1" max="100" style="width:70px" value="${esc(level || "")}"></label>
      <span class="hint">${inTeam ? "Gilt für diesen Platz im Team und filtert die Attacken." : "Leer: alle erlernbaren. Mit Level zählen nur Attacken, die bis dahin gehen."}</span></div>
    <div class="cols">
      <div><h3>Deine Auswahl${inTeam ? ` (Team, Platz ${DSLOT + 1})` : ""}</h3>
        <table class="mine"><tbody>${[0, 1, 2, 3].map(mineRow).join("")}</tbody></table>
        ${mine.length ? `<p class="hint">Trifft sehr effektiv: ${covered.size ? [...covered].map(tchip).join(" ") : "nichts"} (${covered.size} von ${Object.keys(S.chart || {}).length} Typen)</p>`
          : `<p class="hint">Mit + in der Tabelle wählen. ${inTeam ? "Die Auswahl zählt in der Team-Bewertung." : "Gespeichert in diesem Browser; im Team zählt sie für die Bewertung."}</p>`}
        <div class="bar">${std.length ? `<button class="small" data-act="mvstd" data-tip="${esc("Wie im Spiel: die letzten vier Level-Attacken bis zum Level (ohne Level die ersten vier): " + std.join(", "))}">Standard-Attacken</button>` : ""}
          <div class="ac"><input id="mvextra" type="search" placeholder="Andere Attacke (TM, Lehrer …)" style="width:240px"></div></div></div>
      <div><h3>Vorschlag: vier Attacken</h3><div class="sugl">${A.moveset.map((m) => `<div class="${mine.includes(m.id) ? "same" : ""}">${tchip(m.typ)} <b>${esc(m.name)}</b> <span class="why">${esc(m.grund)}</span></div>`).join("") || `<span class="hint">Keine Schadens-Attacke.</span>`}</div>
        ${A.moveset.length ? `<button class="small" data-act="mvtake" style="margin-top:6px">Als eigene Auswahl übernehmen</button>` : ""}</div>
    </div>
    <h3>Schadens-Attacken nach Wertung</h3>
    <p class="hint">Wertung = Stärke × Genauigkeit × Eigentyp-Bonus × passender Angriffswert, mit Zu- und Abschlägen (Aussetzen, Anlauf, Rückstoß, Werte senken, Vorrang). Spalten zum Sortieren anklicken; deine Auswahl ist hinterlegt.</p>
    <div class="scroll"><table class="sort"><thead><tr>${th("Attacke")}${th("Typ")}${th("Klasse")}${th("Stärke")}${th("Gen.", "Genauigkeit in Prozent; – trifft immer")}${th("Wertung")}${th("Weg", "Wie das Pokémon die Attacke lernt")}${th("Gründe", "", true)}<th></th></tr></thead>
      <tbody>${A.attacken.map((m) => mrow(m)).join("") || `<tr><td colspan="9" class="hint">Keine Lernliste.</td></tr>`}</tbody></table></div>
    ${A.status.length ? `<details open><summary>Status-Attacken (${A.status.length})</summary><div class="scroll"><table class="sort"><thead><tr>${th("Attacke")}${th("Typ")}${th("Klasse")}${th("Stärke")}${th("Gen.")}${th("Weg")}${th("Wirkung", "", true)}<th></th></tr></thead>
      <tbody>${A.status.map((m) => mrow(m, true)).join("")}</tbody></table></div></details>` : ""}`;
  $("#lvl").addEventListener("change", async (e) => {
    const v = e.target.value;
    if (inTeam) { S.team.details[DSLOT] = Object.assign({}, S.team.details[DSLOT], {level: v ? Math.max(1, Math.min(100, +v)) : null}); saveTeam(); dock(); }
    const A2 = await api(`/api/pokemon/${id}/attacken?` + qs({spiel: S.game, level: v}));
    d.attacken = A2;
    renderMoves(A2, v);
  });
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
    ${r.alternativen.map((x) => line(x)).join("") || `<p class="hint">Keiner deiner Gefangenen hebt das Team im Moment.</p>`}
    <h3 data-tip="Noch nicht voll entwickelt: die Endstufe würde das Team deutlich mehr heben als das Pokémon heute">Langfristig mehr Potential</h3>
    ${r.potential.map((x) => `<div class="imp diff" data-id="${x.id}" data-hc="${x.id}" draggable="true"><a href="#pokemon/${x.id}">${img(x.id)}</a><span class="arrow">→</span><a href="#pokemon/${x.wird.id}" data-hc="${x.wird.id}">${img(x.wird.id)}</a>
      <div class="grow"><b>${esc(x.name)}</b> → <b>${esc(x.wird.name)}</b> ${tchips(x.wird.typen)}<div class="why">als ${esc(x.wird.name)}: <b class="plus">+${x.plus}</b> Teamwertung ${where(x)}</div></div></div>`).join("")
      || `<p class="hint">Keine Gefangenen, die entwickelt deutlich mehr bringen.</p>`}
    <p class="hint">„Bestes Team suchen“ mit „nur Gefangene“ im Filter baut ein Team nur aus deinen Gefangenen.</p>`;
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
      <div class="bar"><div class="ac grow"><input id="add" type="search" placeholder="Pokémon hinzufügen: Name oder Nummer" style="width:100%"></div></div>
      <div class="tslots" id="slots"><p class="hint">Lädt …</p></div>
      <details class="favd dropmark" data-drop="fav" open><summary>${icon("fav")} Favoriten in ${esc(gameName())} <span id="favn"></span> <span class="hint">zum schnellen Tauschen auf einen Platz ziehen; hierher ziehen macht zum Favoriten</span></summary><div id="favs"></div></details></div>
    <div class="cols">
      <div class="box"><h2>Bewertung</h2><div id="ev"><p class="hint">Lädt …</p></div></div>
      <div class="box"><h2>Verbesserungen</h2><div id="imp"></div></div>
      <div class="box dropmark" data-drop="gef"><h2>${icon("ball")} Aus deinen Gefangenen</h2><div id="gef"><p class="hint">Lädt …</p></div></div>
    </div>
    <div class="box" style="margin-top:12px"><h2>Passende Pokémon finden</h2>
      <div class="cols"><div><h3>Ziel</h3>
        <div class="bar"><select id="preset">${Object.entries(PRESET_DE).map(([k, n]) => `<option value="${k}"${k === S.preset && !S.weights ? " selected" : ""}>${n}</option>`).join("")}
          <option value=""${S.weights ? " selected" : ""}>Eigene Gewichte</option></select>
          <label><input type="checkbox" id="tleg"${S.tleg ? " checked" : ""}> ohne Legendäre und Mysteriöse</label></div>
        <div class="weights">${Object.entries(CRIT).map(([k, n]) => `<span data-tip="${esc(CRIT_TIP[k])}">${n}</span><input type="range" min="0" max="10" step="1" data-w="${k}" value="${w[k]}"><span class="num">${w[k]}</span>`).join("")}</div>
        <div class="bar" style="margin-top:8px"><button class="primary" data-act="opt">Bestes Team suchen</button>
          <label data-tip="Wie „nur Gefangene“ im Filter rechts"><input type="checkbox" id="tgef"${S.tfilter.nur === "gef" ? " checked" : ""}> nur aus Gefangenen</label>
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
  autocomplete($("#foe"), (r) => { if (S.foes.length < 6 && !S.foes.includes(r.id)) { S.foes.push(r.id); store.set("foes", S.foes); } matchup(); });
  bindFilter(S.tfilter, "tf", () => teamRefresh(), () => store.set("tfilter", S.tfilter));
  $("#tleg").addEventListener("change", (e) => { S.tleg = e.target.checked; store.set("tleg", S.tleg); teamRefresh(); });
  $("#tsort").addEventListener("change", (e) => { if (e.target.value) sortTeam(e.target.value); else S.tsort = ""; });
  $("#tgef").addEventListener("change", (e) => { S.tfilter.nur = e.target.checked ? "gef" : ""; store.set("tfilter", S.tfilter); teamView(); });
  $("#saved").addEventListener("change", (e) => {
    const tt = TEAMS.find((x) => x.id === +e.target.value);
    if (!tt) return;
    if (S.team.dirty && !confirm(`„${S.team.name}“ hat ungespeicherte Änderungen. Verwerfen und „${tt.name}“ laden?`)) { e.target.value = ""; return; }
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
  CHECK = {key: "", nicht: ev.nicht_im_spiel || []};
  teamNote();
  teamBar();
  const bad = new Set(CHECK.nicht);
  $("#slots").innerHTML = [0, 1, 2, 3, 4, 5].map((i) => {
    const id = t.ids[i], m = ROWS[id];
    if (!id || !m) return `<div class="tslot empty" data-slot="${i}" data-act="pick" data-tip="Klicken: aus den Favoriten wählen">Platz ${i + 1}<br><span class="hint">hierher ziehen, oben suchen<br>oder klicken für die Favoriten</span></div>`;
    const fixed = t.fest.includes(id), det = t.details[i] || {};
    return `<div class="tslot${fixed ? " fixed" : ""}${bad.has(i) ? " warn" : ""}" data-slot="${i}" draggable="true" data-id="${id}" data-hc="${id}">
      <span class="grip" data-tip="Ziehen zum Umsortieren">⋮⋮</span>
      <button class="small pin${fixed ? " on" : ""}" data-act="pin" data-id="${id}" data-tip="Für die Teamsuche festsetzen">📌</button>
      <button class="small swap" data-act="pick" data-slot="${i}" data-tip="Gegen einen Favoriten tauschen">⇄</button>
      <button class="small x" data-act="teamdel" data-slot="${i}" data-tip="Entfernen">✕</button>
      <a href="#pokemon/${id}/${i}" draggable="false">${img(id, "mid", true)}<br><b>${esc(m.name)}</b></a>
      ${bad.has(i) ? `<div class="note warn small">Nicht in ${esc(gameName())}</div>` : ""}
      <div>${tchips(m.typen)}</div><div class="hint">${det.level ? "Level " + det.level + " · " : ""}Basiswerte <b style="color:${sumColor(m.summe)}">${m.summe}</b></div>
      <div class="mvs">${(det.attacken || []).map((x) => MOVES[x] ? `<span class="mv">${tchip(MOVES[x].typ)} ${esc(MOVES[x].name)}</span>` : "").join("") || `<a class="hint" href="#pokemon/${id}/${i}">Attacken wählen</a>`}</div></div>`;
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
    <details><summary>Typwirkung je Mitglied</summary><div class="scroll"><table class="matrix"><tr><th></th>${ms.map((m) => `<th data-hc="${m.id}">${img(m.id)}</th>`).join("")}</tr>
      ${Object.keys(S.types).filter((a) => ev.matrix[ms[0].id]?.[a] !== undefined).map((a) => `<tr><th class="r">${tchip(a)}</th>${ms.map((m) => { const f = ev.matrix[m.id][a]; return `<td data-tip="${esc(`${tname(a)} gegen ${m.name}: ×${fl(f)}`)}"><span class="f ${fcls(f)}">${f === 1 ? "" : fl(f)}</span></td>`; }).join("")}</tr>`).join("")}</table></div></details>`;
  // Wo ein Vorschlag vom Team abweicht, ist die Zeile dezent hinterlegt; „passt so“ bleibt blass
  $("#imp").innerHTML = (ev.verbesserungen || []).length ? ev.verbesserungen.map((v) => { const diff = v.hinweise.length || v.besser.length;
    const cur = (t.details[v.slot]?.attacken || []).map((x) => MOVES[x]).filter(Boolean);
    return `<div class="imp${diff ? " diff" : " same"}" data-hc="${v.id}" data-slot="${v.slot}"><a href="#pokemon/${v.id}/${v.slot}">${img(v.id)}</a><div><b>${esc(v.name)}</b> <span class="muted">Platz ${v.slot + 1}</span>
      ${v.hinweise.map((h) => `<div class="why">${esc(h)}</div>`).join("")}
      ${v.besser.length ? `<div class="why">Statt ${esc(v.schwaechste)}: ${v.besser.map((b) => `<span class="new">${tchip(b.typ)} <b>${esc(b.name)}</b> (${b.wertung})</span>`).join(" ")}</div>
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
  $("#opt").innerHTML = `<p class="hint">Aus ${r.pool} Pokémon (Filter rechts${S.tfilter.nur === "gef" ? ", nur Gefangene" : ""}) in ${esc(gameName())}. Hinterlegt: nicht in deinem Team.</p>` + r.teams.map((t, i) => `<div class="optt">
    <div class="bar"><b class="score-s">${t.wertung}</b><span class="grow">${t.mitglieder.map((m) => `<a href="#pokemon/${m.id}" data-hc="${m.id}" class="${now.has(m.id) ? "" : "new"}">${img(m.id)}</a>`).join("")}</span>
    <button class="small" data-act="take" data-i="${i}">Übernehmen</button></div>
    <div class="why">${t.mitglieder.map((m) => now.has(m.id) ? esc(m.name) : `<b>${esc(m.name)}</b>`).join(", ")}${t.offen.length ? " · offen: " + t.offen.map(tname).join(", ") : ""}</div></div>`).join("");
  S.lastOpt = r.teams;
}
async function matchup() {
  const box = $("#mu");
  if (!box) return;
  if (!S.foes.length) { box.innerHTML = `<p class="hint">Wähle Gegner: das Tool zeigt, wer aus deinem Team gegen wen im Vorteil ist.</p>`; return; }
  const foeCard = (id, r) => `<div class="foe" data-hc="${id}">${img(id, "", true)}<b>${esc(r?.name || "#" + id)}</b><div>${tchips(r?.typen || [])}</div>
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
    <div class="scroll"><table class="vs"><thead><tr><th></th>${r.einzeln.map((x) => `<th class="foeh" data-hc="${x.gegner.id}">${img(x.gegner.id)}<div>${esc(x.gegner.name)}</div></th>`).join("")}</tr></thead><tbody>
      ${r.uebersicht.filter((m) => !seen.has(m.id) && seen.add(m.id)).map((m) => `<tr><th class="r" data-hc="${m.id}">${img(m.id)} ${esc(m.name)}</th>${r.einzeln.map((x) => { const v = verdict[`${m.id}:${x.gegner.id}`], u = VERDICT[v.urteil];
        return `<td class="v-${v.urteil}" data-tip="${esc(`${m.name} gegen ${x.gegner.name}: ${u[1]}\n${v.gruende.map((g) => "· " + g).join("\n")}`)}">${u[0]}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div>
    <p class="hint">Vorteil: teilt mehr aus, als es einsteckt (Typen und Initiative). Nachteil: steckt mehr ein, als es austeilt. Die Attacken des Gegners zählen über seine Typen, deine über die gewählten Attacken. Zelle hovern für die Rechnung.</p>`;
}

const VERDICT = {schicken: ["Vorteil", "im Vorteil, gut einzusetzen"], geht: ["ausgeglichen", "ausgeglichen, weder klar besser noch schlechter"],
  schonen: ["Nachteil", "im Nachteil, besser nicht gegen diesen Gegner"]};

/* ------------------------------------------------------------------ Attacken */
async function movesView() {
  const f = Object.assign({q: "", typen: [], klasse: "", lernbar: true, min: "", prio: false, kontakt: ""}, store.get("mfilter2", {}));
  const rid = RID;
  main.innerHTML = `<div class="bar"><span class="hint">Spiel</span><select class="gamesel"></select>
    <input id="mq" class="grow" type="search" placeholder="Attacke suchen" value="${esc(f.q)}"></div>
    <div class="bubbles">${Object.entries(S.types).map(([t, n]) => `<button class="tb t t${t}${f.typen.includes(t) ? " in" : ""}" data-mt="${t}">${esc(n)}</button>`).join("")}</div>
    <div class="bar"><span class="seg">${[["", "Alle"], ["2", "Physisch"], ["3", "Speziell"], ["1", "Status"]].map(([k, n]) => `<button data-mk="${k}" class="${f.klasse === k ? "on" : ""}">${n}</button>`).join("")}</span>
      <label data-tip="Nur Attacken, die im gewählten Spiel mindestens ein Pokémon lernen kann"><input type="checkbox" id="mlern"${f.lernbar ? " checked" : ""}> im Spiel erlernbar</label>
      <label data-tip="Vorrang (Priorität): die Attacke kommt vor normalen Attacken dran, egal wie schnell der Gegner ist (etwa Ruckzuckhieb). Höhere Zahl = noch früher"><input type="checkbox" id="mprio"${f.prio ? " checked" : ""}> nur mit Vorrang</label>
      <label data-tip="Kontakt: der Angreifer berührt das Ziel. Das löst Fähigkeiten wie Rauhaut, Statik oder Flammkörper aus; Attacken ohne Kontakt umgehen sie">Kontakt <select id="mkon"><option value="">egal</option><option value="1"${f.kontakt === "1" ? " selected" : ""}>mit</option><option value="0"${f.kontakt === "0" ? " selected" : ""}>ohne</option></select></label>
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
      (f.kontakt === "" || m.merkmale.includes("contact") === (f.kontakt === "1")));
    $("#mcnt").textContent = `${xs.length} von ${rows.length} Attacken in ${gameName()}`;
    $("#mv").innerHTML = `<div class="box scroll"><table class="sort"><thead><tr>${th("Attacke")}${th("Typ")}${th("Klasse")}${th("Stärke")}${th("Gen.", "Genauigkeit in Prozent; – trifft immer")}${th("AP", "Angriffspunkte: so oft lässt sich die Attacke einsetzen")}
      ${th("Vorrang", "Vorrang (Priorität): positive Werte kommen vor normalen Attacken dran, negative danach")}${th("Wertung", "Stärke × Genauigkeit mit Zu- und Abschlägen, ohne Eigentyp-Bonus")}${th("Lernen", "So viele Pokémon (und Formen) lernen sie im Spiel")}${th("Gen", "Generation, seit der es die Attacke gibt")}${th("Beschreibung", "", true)}</tr></thead><tbody>
      ${xs.map((m) => `<tr><td data-s="${esc(m.name)}"><b>${esc(m.name)}</b> ${wikiLink(m.name)}${m.geaendert ? ' <span class="cls" data-tip="Werte in diesem Spiel anders als heute">Spielwert</span>' : ""}${m.merkmale.includes("contact") ? ' <span class="cls" data-tip="Kontakt: berührt das Ziel (löst etwa Rauhaut oder Statik aus)">Kontakt</span>' : ""}</td><td data-s="${tname(m.typ)}">${tchip(m.typ)}</td>
        <td><span class="cls">${CLS[m.klasse]}</span></td><td class="num" data-s="${m.staerke || 0}">${powCell(m.staerke)}</td><td class="num" data-s="${m.genauigkeit ?? 101}">${accCell(m.genauigkeit)}</td>
        <td class="num">${m.ap ?? ""}</td><td class="num">${m.prio ? `<span data-tip="${m.prio > 0 ? `Vorrang +${m.prio}: kommt vor normalen Attacken` : `Vorrang ${m.prio}: kommt nach normalen Attacken`}">${m.prio > 0 ? "+" : ""}${m.prio}</span>` : ""}</td>
        <td class="num" data-s="${m.wertung}"${m.gruende.length ? ` data-tip="${esc(m.gruende.join("\n"))}"` : ""}>${m.wertung ? `<b style="color:${scoreColor(m.wertung)}">${m.wertung}</b>` : ""}</td>
        <td class="num">${m.lernen || ""}</td><td class="num">${m.gen || ""}</td><td class="why">${esc(m.text || "")}</td></tr>`).join("")}</tbody></table></div>`;
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
  $("#mkon").addEventListener("change", (e) => { f.kontakt = e.target.value; draw(); });
  $("#mmin").addEventListener("input", (e) => { f.min = e.target.value; draw(); });
  await load();
}

/* ------------------------------------------------------------------ Typtabelle */
let PIN = {r: null, c: null};
async function chartView() {
  const ch = S.chart, ts = Object.keys(ch);
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Typtabelle Generation ${S.chartGen}</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      <button class="small" data-act="unpin" id="unpin" hidden>Markierung aufheben</button></div>
    <p class="hint">Zeile greift an, Spalte verteidigt. <span class="f f2">2</span> sehr effektiv · <span class="f f05">½</span> nicht sehr effektiv ·
      <span class="f f0">0</span> keine Wirkung (immun) · leer = normal (×1). Klick auf einen Typ hält Zeile oder Spalte fest, Klick auf eine Zelle beides.</p>
    <div class="scroll"><table class="chart"><thead><tr><th class="corner"><span>Angriff ↓ · Verteidigung →</span></th>${ts.map((t) => `<th class="v" data-c="${t}" data-pc="${t}"><span>${tchip(t)}</span></th>`).join("")}</tr></thead>
    <tbody>${ts.map((a) => `<tr data-r="${a}"><th class="r" data-pr="${a}">${tchip(a)}</th>${ts.map((v) => { const f = ch[a][v];
      return `<td data-c="${v}" data-tip-cell="${a}:${v}">${f === 1 ? "" : `<span class="f ${fcls(f)}">${fl(f)}</span>`}</td>`; }).join("")}</tr>`).join("")}</tbody>
    </table></div></div>`;
  header();
  const table = $(".chart");
  const paint = (hr, hc) => {
    $$(".hl,.pin", table).forEach((x) => x.classList.remove("hl", "pin"));
    const mark = (r, c, cls) => {
      if (r !== null) $$(`tr[data-r="${r}"] > *`, table).forEach((x) => x.classList.add(cls));
      if (c !== null) $$(`[data-c="${c}"]`, table).forEach((x) => x.classList.add(cls));
    };
    mark(PIN.r, PIN.c, "pin");
    mark(hr, hc, "hl");
    $("#unpin").hidden = PIN.r === null && PIN.c === null;
  };
  table.addEventListener("mouseover", (e) => {
    const cell = e.target.closest("td[data-c],th[data-pc],th[data-pr]");
    if (!cell) return paint(null, null);
    const r = cell.closest("tr")?.dataset.r ?? null;
    paint(cell.dataset.pc ? null : r, cell.dataset.pr ? null : cell.dataset.c ?? null);
  });
  table.addEventListener("mouseleave", () => paint(null, null));
  table.addEventListener("click", (e) => {
    const cell = e.target.closest("td[data-c],th[data-pc],th[data-pr]");
    if (!cell) return;
    if (cell.dataset.pr) PIN = {r: PIN.r === cell.dataset.pr ? null : cell.dataset.pr, c: PIN.c};
    else if (cell.dataset.pc) PIN = {r: PIN.r, c: PIN.c === cell.dataset.pc ? null : cell.dataset.pc};
    else {
      const r = cell.closest("tr").dataset.r, c = cell.dataset.c;
      PIN = PIN.r === r && PIN.c === c ? {r: null, c: null} : {r, c};
    }
    paint(null, null);
  });
  paint(null, null);
}

/* ------------------------------------------------------------------ Einstellungen */
async function settingsView() {
  const rid = RID;
  const [st, pr] = await Promise.all([api("/api/status"), S.meta?.has_data ? api("/api/pruefung") : []]);
  if (rid !== RID) return;
  const s = S.meta?.einstellungen || {};
  const src = st.sources || {};
  const open = pr.filter((r) => !r.entscheidung);
  const srcRow = (k, n) => { const r = src[k]; return r ? `<tr><td>${n}</td><td>${r.ok ? "✓" : "✗"} ${esc(r.msg || "")}</td><td class="num">${r.requests}</td><td class="num">${r.errors}</td><td>${esc((r.at || "").slice(0, 16).replace("T", " "))}</td></tr>` : ""; };
  main.innerHTML = `<div class="cols">
    <div class="box"><h2>Abgleich</h2>
      ${st.running ? `<div class="note info">Läuft: ${esc(st.step || "")}${st.total ? ` (${st.done}/${st.total})` : ""}</div>` : ""}
      <p>Letzter Lauf: ${st.started ? esc(st.started.slice(0, 16).replace("T", " ")) + " UTC" + (st.ok === false ? " <b>mit Fehlern</b>" : "") : "noch keiner"}
      ${st.built ? `<br>Datenbank gebaut: ${esc(st.built.slice(0, 16).replace("T", " "))} UTC` : ""}</p>
      ${st.stats?.species ? `<p class="hint">${st.stats.species} Arten, ${st.stats.forms} Formen, ${st.stats.moves} Attacken, ${st.stats.games} Spiele, ${st.stats.tables} Tabellen</p>` : ""}
      <div class="bar"><button class="primary" data-act="sync"${st.running ? " disabled" : ""}>Jetzt abgleichen</button>
        <button data-act="rebuild"${st.running ? " disabled" : ""} data-tip="Auch ohne Änderung neu bauen">Neu bauen</button></div>
      <table class="rows"><tr><th>Quelle</th><th>Stand</th><th>Abrufe</th><th>Fehler</th><th>Zeit</th></tr>${srcRow("pokeapi", "PokéAPI")}${srcRow("showdown", "Showdown")}${srcRow("sprites", "Bilder")}</table>
      <h3>Zeitplan</h3>
      <div class="bar"><label><input type="checkbox" id="auto"${s.auto ? " checked" : ""}> automatisch alle</label>
        <input type="number" id="tage" min="1" max="30" value="${s.tage || 7}" style="width:64px"> Tage</div>
      <div class="bar"><label><input type="checkbox" id="sprites"${s.sprites ? " checked" : ""}> Bilder laden (Sprites 96 × 96 und offizielle Artworks 475 × 475, zusammen gut 180 MB)</label></div>
      <p class="hint">Ändert sich bei keiner Quelle etwas, bleibt die Datenbank. Eine neue gilt erst nach bestandener Selbstprüfung; deine Teams liegen getrennt (user.db) und werden täglich gesichert.</p>
    </div>
    <div class="box"><h2>Zu erledigen</h2>
      ${open.length ? `<p class="hint">PokéAPI und Showdown sind sich hier nicht einig. Wähle, welcher Wert stimmt; im Zweifel im PokéWiki nachsehen.</p>
        <div class="scroll"><table class="rows"><tr><th>Was</th><th>Feld</th><th>PokéAPI</th><th>Showdown</th><th></th></tr>
        ${open.slice(0, 80).map((r) => `<tr><td>${esc(r.name)}</td><td>${esc(r.feld)}</td><td>${esc(r.pokeapi)}</td><td>${esc(r.showdown)}</td>
          <td><button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="pokeapi">PokéAPI</button> <button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="showdown">Showdown</button>
          <button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="egal">egal</button></td></tr>`).join("")}</table></div>`
        : `<div class="note go">Nichts offen${pr.length ? ` (${pr.length} Abweichungen entschieden)` : ""}.</div>`}
      ${pr.length - open.length ? `<details><summary>Entschieden (${pr.length - open.length})</summary><table class="rows">${pr.filter((r) => r.entscheidung).map((r) => `<tr><td>${esc(r.name)}</td><td>${esc(r.feld)}</td><td>${esc(r.entscheidung)}</td><td><button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="">zurück</button></td></tr>`).join("")}</table></details>` : ""}
    </div></div>
    <h2 class="sect">Spieldaten aus den Quellen</h2>
    <div class="box"><div class="bar"><h2 style="margin:0">Protokoll</h2><span class="grow"></span>
        ${(st.log || []).length ? `<button class="link" data-act="copy" data-src="#plog">kopieren</button> <button class="link" data-act="dl" data-src="#plog" data-name="pokedex-protokoll">herunterladen</button>` : ""}</div>
      <div class="log" id="plog">${esc((st.log || []).join("\n") || "Noch kein Lauf.")}</div></div>
    <div class="box"><h2>Verbindungstest</h2><p class="hint">Fragt jede Quelle einmal an, auch mögliche neue (Items, Fundorte aus den Spieldaten, Wikis, Kampfdaten), und beschreibt die Antwort. Speichert nichts; Probe-Seiten lassen sich herunterladen. Dauert etwa eine Minute.</p>
      <div class="bar"><button data-act="diag">Test starten</button><span class="grow"></span><span id="dlinks"></span></div>
      <div id="diag"></div></div>
    <h2 class="sect">Deine Daten</h2>
    <div class="box"><h2>Sicherung</h2>
      <p class="hint">Alles Eigene in einer Datei: Teams, Favoriten, Gefangene und Entscheidungen. Die Spieldaten gehören nicht dazu; die holt der Abgleich jederzeit neu.
        Der Server sichert user.db außerdem täglich selbst (die letzten 14 Tage).</p>
      <div class="bar"><a class="btn" href="/api/export" download>Sicherung herunterladen</a>
        <label class="btn filebtn">Sicherung einlesen <input type="file" id="restore" accept="application/json,.json" hidden></label>
        <span class="hint">Einlesen ersetzt alle eigenen Daten durch die Datei (vorher legt der Server eine Kopie an).</span></div>
      <div id="restmsg"></div></div>
    <div class="box"><h2>Quellen und Lizenzen</h2>
      <p><a href="https://pokeapi.co" target="_blank" rel="noopener noreferrer">PokéAPI</a> (Grunddaten, alle Spiele, BSD-Lizenz) ·
        <a href="https://github.com/smogon/pokemon-showdown" target="_blank" rel="noopener noreferrer">Pokémon Showdown</a> (Gegenprüfung, MIT) ·
        <a href="https://www.pokewiki.de" target="_blank" rel="noopener noreferrer">PokéWiki</a> (Links; Abruf für Legenden: Arceus folgt, CC BY-SA 3.0 DE).
        Pokémon und alle Namen sind Marken von Nintendo, Creatures und GAME FREAK; dies ist ein privates Nachschlage-Tool.</p>
      <p class="hint">Pokédex ${esc(S.meta?.version || "")}</p></div>`;
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
    if (!confirm(`Sicherung vom ${String(body.exportiert || "?").slice(0, 10)} einlesen?\n${n("teams")} Teams, ${n("favoriten")} Favoriten, ${n("gefangen")} Gefangene, ${n("entscheidungen")} Entscheidungen.\n\nDas ersetzt alle eigenen Daten.`)) return;
    try {
      const r = await api("/api/restore", body);
      $("#restmsg").innerHTML = `<div class="note go">Eingelesen: ${r.teams} Teams, ${r.favoriten} Favoriten, ${r.gefangen} Gefangene, ${r.entscheidungen} Entscheidungen.</div>`;
      S.favGame = null; S.caughtGame = null;
      if (S.team.tid) { S.team.tid = null; S.team.dirty = false; store.set("team", S.team); }
      await Promise.all([loadFavs(true), loadCaught(true)]);
      dock();
    } catch (x) { $("#restmsg").innerHTML = `<div class="note stop">${esc(x.message)}</div>`; }
  });
  if (st.running) setTimeout(() => location.hash.startsWith("#einstellungen") && refreshMeta(), 4000);
}
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
    else if (act === "pick") picker(b, +b.dataset.slot);
    else if (act === "pickfav") { $("#pick").hidden = true; addToTeam(id, +b.dataset.slot); }
    else if (act === "tgame") setGame(S.team.spiel);
    else if (act === "unpin") { PIN = {r: null, c: null}; chartView(); }
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
    else if (act === "take") {
      const ids = S.lastOpt[+b.dataset.i].ids, old = S.team;
      // Level und Attacken bleiben bei Pokémon, die schon im Team waren
      S.team.details = ids.map((x) => { const i = old.ids.indexOf(x); return i >= 0 ? old.details[i] : {}; });
      S.team.ids = ids;
      teamChanged();
      ids.forEach((x, i) => fillStandard(i));
    } else if (act === "tclear") { Object.assign(S.team, {ids: [], fest: [], details: []}); teamChanged(); teamView(); }
    else if (act === "tnew") {
      if (S.team.dirty && !confirm(`„${S.team.name}“ hat ungespeicherte Änderungen. Trotzdem ein neues Team beginnen?`)) return;
      S.team = normTeam({spiel: S.game});
      store.set("team", S.team); dock(); location.hash.startsWith("#team") ? teamView() : (location.hash = "#team");
    } else if (act === "tsave" && S.team.tid) { await saveToServer(); dock(); if (location.hash.startsWith("#team")) teamView(); }
    else if (act === "tsave" || act === "tsaveas" || act === "trename") {
      const name = prompt(act === "trename" ? "Neuer Name" : "Name des Teams", act === "tsaveas" && S.team.tid ? S.team.name + " (Kopie)" : S.team.name || "Team " + gameName());
      if (!name) return;
      if (act === "trename") { S.team.name = name; await saveToServer(name); }
      else await saveToServer(name, act === "tsaveas");
      dock(); if (location.hash.startsWith("#team")) teamView();
    } else if (act === "tundo") {
      const tt = (await api("/api/teams")).find((x) => x.id === S.team.tid);
      if (tt) loadTeam(tt); else { S.team.dirty = false; store.set("team", S.team); }
      dock(); if (!location.hash.startsWith("#team")) route();
    } else if (act === "tdel") {
      if (!confirm(`Team „${S.team.name}“ löschen?`)) return;
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
