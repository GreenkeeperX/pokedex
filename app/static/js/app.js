/* Pokédex-Oberfläche: reines JavaScript ohne Build. Reiter über die Adresse (#pokemon, #pokemon/6, #team, #attacken,
   #typen, #einstellungen), deshalb öffnet „In neuem Tab öffnen“ jede Karte. Gewähltes Spiel, Filter und das aktuelle
   Team merkt sich der Browser; ein gespeichertes Team speichert sich bei jeder Änderung selbst auf dem Server. */
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const main = $("#main");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem("px." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("px." + k, JSON.stringify(v)); } catch (e) { /* privates Fenster */ } },
};
const filter0 = (extra = {}) => Object.assign({q: "", typen: {}, modus: "und", formen: "relevant", sort: "nr", endstufe: false, ohne_leg: false, kampf: false, gen: "", min: ""}, extra);
const S = {
  meta: null, types: {}, chart: null, chartGame: null,
  game: store.get("game", "legends-arceus"),
  team: Object.assign({ids: [], fest: [], details: {}}, store.get("team", {})),
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

function typeTip(t) {
  const ch = S.chart;
  if (!ch || !ch[t]) return tname(t);
  const strong = Object.entries(ch[t]).filter(([, f]) => f > 1).map(([d]) => tname(d));
  const weak = Object.entries(ch[t]).filter(([, f]) => f > 0 && f < 1).map(([d]) => tname(d));
  const none = Object.entries(ch[t]).filter(([, f]) => f === 0).map(([d]) => tname(d));
  const hurt = Object.keys(ch).filter((a) => ch[a][t] > 1).map(tname);
  const res = Object.keys(ch).filter((a) => ch[a][t] > 0 && ch[a][t] < 1).map(tname);
  const imm = Object.keys(ch).filter((a) => ch[a][t] === 0).map(tname);
  return [`${tname(t)}-Attacken`, strong.length && `sehr effektiv gegen ${strong.join(", ")}`, weak.length && `nicht sehr effektiv gegen ${weak.join(", ")}`,
    none.length && `keine Wirkung gegen ${none.join(", ")}`, `${tname(t)}-Pokémon`, hurt.length && `schwach gegen ${hurt.join(", ")}`,
    res.length && `resistent gegen ${res.join(", ")}`, imm.length && `immun gegen ${imm.join(", ")}`].filter(Boolean).join("\n");
}
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

/* Netzdiagramm wie in Legenden: Arceus: KP oben, dann im Uhrzeigersinn Angriff, Verteidigung, Initiative, Sp.-Vert., Sp.-Angriff */
const RADAR_ORDER = [0, 1, 2, 5, 4, 3];
function radar(werte, size = 44, labels = false) {
  const pad = labels ? 34 : 2, r = size / 2 - pad, c = size / 2;
  const pt = (k, f) => { const a = -Math.PI / 2 + (k * Math.PI) / 3; return [c + Math.cos(a) * r * f, c + Math.sin(a) * r * f]; };
  const poly = (f) => RADAR_ORDER.map((_, k) => pt(k, typeof f === "number" ? f : f(k)).map((x) => x.toFixed(1)).join(",")).join(" ");
  const val = (k) => Math.max(0.06, Math.min(1, werte[RADAR_ORDER[k]] / 160));
  let s = `<svg class="radar" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">`;
  s += `<polygon points="${poly(1)}" class="rg"/>` + (labels ? `<polygon points="${poly(0.5)}" class="rg2"/>` : "");
  s += `<polygon points="${poly(val)}" class="rv"/>`;
  if (labels) RADAR_ORDER.forEach((i, k) => {
    const [x, y] = pt(k, 1.28);
    s += `<text x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="middle">${STAT_K[i]} ${werte[i]}</text>`;
  });
  return s + "</svg>";
}

const teamFull = () => S.team.ids.length >= 6;
function monCard(r) {
  const inTeam = S.team.ids.includes(r.id);
  return `<a class="mon" href="#pokemon/${r.id}" draggable="true" data-id="${r.id}">${img(r.id)}
    <span class="mi"><span class="n">${esc(r.name)}</span> <span class="s">#${r.nr ?? r.art}</span><span class="ty">${tchips(r.typen)}</span>
    <span class="s">Basiswerte <b style="color:${sumColor(r.summe)}">${r.summe}</b>${r.legendaer ? " · legendär" : ""}</span></span>
    ${radar(r.werte, 46)}
    ${inTeam ? `<span class="badge" data-tip="Im Team">✓</span>` : teamFull() ? "" : `<span class="plus" data-act="teamadd" data-id="${r.id}" data-tip="Ins Team">+</span>`}</a>`;
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
const ROWS = {};          // id → Zeile aus der Liste, für die Hover-Karte

// Neben das Ziel setzen, nie darüber: rechts, sonst links, sonst darunter oder darüber
function place(el, target) {
  const r = target.getBoundingClientRect(), w = el.offsetWidth, h = el.offsetHeight, m = 8;
  const vw = document.documentElement.clientWidth, vh = window.innerHeight;
  let x, y;
  if (r.right + m + w <= vw) { x = r.right + m; y = r.top; }
  else if (r.left - m - w >= 0) { x = r.left - m - w; y = r.top; }
  else { x = Math.max(m, Math.min(vw - w - m, r.left)); y = r.bottom + m + h <= vh ? r.bottom + m : r.top - m - h; }
  y = Math.max(m, Math.min(vh - h - m, y));
  el.style.left = x + window.scrollX + "px";
  el.style.top = y + window.scrollY + "px";
}
let tipTimer, cardTimer;
document.addEventListener("mouseover", (e) => {
  if (e.pointerType === "touch") return;
  const t = e.target.closest("[data-tip],[data-tip-type]");
  if (t) {
    clearTimeout(tipTimer);
    tipTimer = setTimeout(() => {
      tip.textContent = t.dataset.tipType ? typeTip(t.dataset.tipType) : t.dataset.tip;
      tip.hidden = false;
      place(tip, t);
    }, 220);
  }
  const c = e.target.closest(".mon");
  if (c && !t) {
    clearTimeout(cardTimer);
    cardTimer = setTimeout(() => showCard(c), 280);
  }
});
document.addEventListener("mouseout", (e) => {
  const t = e.target.closest("[data-tip],[data-tip-type]");
  if (t && !t.contains(e.relatedTarget)) { clearTimeout(tipTimer); tip.hidden = true; }
  const c = e.target.closest(".mon");
  if (c && !c.contains(e.relatedTarget)) { clearTimeout(cardTimer); card.hidden = true; }
});
document.addEventListener("scroll", () => { tip.hidden = true; card.hidden = true; }, {passive: true});
function showCard(el) {
  const r = ROWS[el.dataset.id];
  if (!r) return;
  const d = defense(r.typen);
  const by = (pred) => Object.entries(d).filter(([, f]) => pred(f)).sort((a, b) => b[1] - a[1]);
  const fx = (xs) => xs.map(([t, f]) => `<span class="fx">${tchip(t)}<span class="f ${fcls(f)}">×${fl(f)}</span></span>`).join("") || `<span class="muted">keine</span>`;
  card.innerHTML = `<div class="hc-head">${img(r.id, "art", true)}<div><b>${esc(r.name)}</b> <span class="muted">#${r.nr ?? r.art}</span><div>${tchips(r.typen)}</div>
      <div class="muted">Basiswerte <b style="color:${sumColor(r.summe)}">${r.summe}</b>${r.legendaer ? " · legendär" : ""}${r.endstufe ? " · Endstufe" : ""}</div></div></div>
    <div class="hc-body">${radar(r.werte, 190, true)}<div class="hc-eff"><div class="muted">Schwach gegen</div>${fx(by((f) => f > 1))}
      <div class="muted">Resistent / immun</div>${fx(by((f) => f < 1))}</div></div>`;
  card.hidden = false;
  place(card, el);
}

/* ------------------------------------------------------------------ Sortierbare Tabellen */
// th[data-sort] sortiert nach den Werten data-s der Zellen (sonst dem Text); zweiter Klick dreht die Richtung
document.addEventListener("click", (e) => {
  const th = e.target.closest("table.sort th[data-sort]");
  if (!th) return;
  const table = th.closest("table"), i = [...th.parentNode.children].indexOf(th);
  const tb = table.tBodies[0], rows = [...tb.rows];
  const dir = th.dataset.dir === "desc" ? "asc" : "desc";
  $$("th", table).forEach((x) => delete x.dataset.dir);
  th.dataset.dir = dir;
  const key = (tr) => { const c = tr.cells[i]; const v = c?.dataset.s ?? c?.textContent.trim() ?? ""; const n = parseFloat(v); return isNaN(n) || v === "" ? v.toLowerCase() : n; };
  rows.sort((a, b) => { const x = key(a), y = key(b); const r = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "de"); return dir === "asc" ? r : -r; });
  rows.forEach((r) => tb.appendChild(r));
});
const th = (label, tipText = "", noSort = false) => `<th${noSort ? "" : " data-sort"}${tipText ? ` data-tip="${esc(tipText)}"` : ""}>${label}</th>`;

/* ------------------------------------------------------------------ Kopf, Reiter, Adresse */
function header() {
  const gs = S.meta?.spiele || [];
  const opts = `<option value="">Alle Spiele (neueste Werte)</option>` + gs.map((g) => `<option value="${esc(g.kennung)}">${esc(g.name)} · Gen ${g.gen}</option>`).join("");
  $$("select.gamesel").forEach((sel) => { sel.innerHTML = opts; sel.value = gs.some((g) => g.kennung === S.game) ? S.game : ""; });
  const a = S.meta?.abgleich || {};
  $("#meta").textContent = !S.meta?.has_data ? (a.running ? "Erster Abgleich läuft …" : "Noch keine Daten")
    : `${S.meta.formen} Pokémon und Formen · ${S.meta.attacken} Attacken · ${gs.length} Spiele` + (a.running ? " · Abgleich läuft" : "");
  const t = document.documentElement.dataset.theme;
  $("#thm").textContent = t === "dark" ? "Dunkel" : t === "light" ? "Hell" : "Ansicht: Gerät";
}
function nav(tab) {
  $("#nav").innerHTML = TABS.map(([k, n]) => `<a href="#${k}" class="${k === tab ? "on" : ""}">${n}</a>`).join("");
}
let RID = 0;                // jede neue Adresse zählt hoch; ältere Antworten schreiben dann nichts mehr
async function route() {
  RID++;
  tip.hidden = card.hidden = true;
  const [tab, arg] = (location.hash.slice(1) || "pokemon").split("/");
  nav(tab);
  try {
    if (!S.meta?.has_data && tab !== "einstellungen") return noData();
    await loadChart();
    if (tab === "pokemon" && arg) await detailView(+arg);
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
  S.meta = await api("/api/meta");
  S.types = Object.fromEntries((S.meta.typen || []).map((t) => [t.id, t.name]));
  header();
  if (S.meta.has_data || !S.meta.abgleich?.running) route(); else setTimeout(refreshMeta, 5000);
}

/* ------------------------------------------------------------------ Filter (Liste und Team) */
function filterBar(f, id, opts = {}) {
  const bub = Object.entries(S.types).map(([t, n]) => {
    const st = f.typen[t] || 0;
    return `<button class="tb t t${t}${st === 1 ? " in" : st === -1 ? " out" : ""}" data-fb="${id}" data-t="${t}" data-tip="${esc(n)}: klicken = muss dabei sein, nochmal = ausschließen, nochmal = egal">${esc(n)}</button>`;
  }).join("");
  return `<div class="filters" id="${id}">
    <div class="bar">${opts.search === false ? "" : `<input class="grow" data-f="q" type="search" placeholder="Name oder Nummer" value="${esc(f.q)}">`}
      <span class="seg" data-tip="Mehrere gewählte Typen: „und“ = alle zugleich (Doppeltyp), „oder“ = einer davon reicht">
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
      <label>bis Gen <select data-f="gen"><option value="">alle</option>${[1, 2, 3, 4, 5, 6, 7, 8, 9].map((g) => `<option${+f.gen === g ? " selected" : ""}>${g}</option>`).join("")}</select></label>
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
  gen: f.gen, min: f.min, modus: f.modus, typen: Object.keys(f.typen).filter((t) => f.typen[t] === 1).join(","),
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
let saveTimer;
function saveTeam() {
  store.set("team", S.team);
  if (S.team.tid) {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => api("/api/teams", {id: S.team.tid, name: S.team.name, spiel: S.team.spiel ?? S.game, mitglieder: S.team.ids,
      fest: S.team.fest, gewichte: weights(), details: S.team.details}).catch((e) => console.warn(e)), 600);
  }
}
function teamChanged() {
  saveTeam();
  dock();
  const h = location.hash;
  if (h.startsWith("#team")) teamRefresh();
  else if (h === "" || h === "#pokemon") $$(".mon").forEach((el) => { const r = ROWS[el.dataset.id]; if (r) el.outerHTML = monCard(r); });
}
function addToTeam(id, at = null) {
  id = +id;
  const t = S.team;
  const from = t.ids.indexOf(id);
  if (from >= 0 && at === null) return;
  if (from >= 0) t.ids.splice(from, 1);
  if (at === null) { if (t.ids.length >= 6) return alert("Das Team ist voll (6)."); t.ids.push(id); }
  else if (t.ids.length >= 6 && from < 0) { const old = t.ids[at]; t.ids[at] = id; t.fest = t.fest.filter((x) => x !== old); delete t.details[old]; }
  else t.ids.splice(Math.min(at, t.ids.length), 0, id);
  teamChanged();
}
function removeFromTeam(id) {
  const t = S.team;
  t.ids = t.ids.filter((x) => x !== id);
  t.fest = t.fest.filter((x) => x !== id);
  delete t.details[id];
  teamChanged();
}
function dock() {
  let el = $("#dock");
  if (!el) { el = document.createElement("div"); el.id = "dock"; document.body.appendChild(el); }
  const t = S.team;
  const slots = [0, 1, 2, 3, 4, 5].map((i) => {
    const id = t.ids[i];
    if (!id) return `<div class="dslot empty" data-slot="${i}">${i === t.ids.length ? "hierher ziehen" : ""}</div>`;
    const r = ROWS[id];
    const lv = t.details[id]?.level;
    return `<div class="dslot" data-slot="${i}" draggable="true" data-id="${id}"><a href="#pokemon/${id}" draggable="false">${img(id)}</a>
      <span class="dn">${esc(r?.name || "#" + id)}${lv ? ` <span class="muted">Lv ${lv}</span>` : ""}</span>
      <button class="x" data-act="teamdel" data-id="${id}" data-tip="Aus dem Team">✕</button></div>`;
  }).join("");
  el.className = S.dock ? "open" : "";
  el.innerHTML = `<div class="dhead"><button data-act="dock" class="link">${S.dock ? "▾" : "▴"} Team${t.name ? ": " + esc(t.name) : ""}</button>
    <span class="hint">${t.ids.length}/6 · ${esc(gameName(t.spiel ?? S.game))}${t.tid ? " · speichert sich selbst" : ""}</span>
    ${S.dock ? "" : `<span class="dmini">${t.ids.map((id) => img(id)).join("")}</span>`}
    <a class="btn small" href="#team">Team ansehen</a></div>${S.dock ? `<div class="dslots">${slots}</div>` : ""}`;
  document.body.classList.toggle("dock-open", S.dock);
  // Namen nachladen, die die Liste nicht kennt
  const unknown = t.ids.filter((id) => !ROWS[id]);
  if (unknown.length && !dock.loading) {
    dock.loading = true;
    api("/api/team/bewerten", {spiel: S.game, ids: unknown}).then((ev) => { (ev.mitglieder || []).forEach((m) => { ROWS[m.id] = m; }); dock.loading = false; dock(); })
      .catch(() => { dock.loading = false; });
  }
}
// Ziehen und Ablegen: Karten aus der Liste in die Leiste, Plätze in der Leiste tauschen
document.addEventListener("dragstart", (e) => {
  const c = e.target.closest(".mon,.dslot[data-id],.sugg");
  if (!c) return;
  e.dataTransfer.setData("text/x-pokemon", c.dataset.id);
  if (c.classList.contains("dslot")) e.dataTransfer.setData("text/x-slot", c.dataset.slot);
  e.dataTransfer.effectAllowed = "move";
  card.hidden = true;
  if (!S.dock) { S.dock = true; dock(); }
  document.body.classList.add("dragging");
});
document.addEventListener("dragend", () => { document.body.classList.remove("dragging"); $$(".dslot.over").forEach((x) => x.classList.remove("over")); });
document.addEventListener("dragover", (e) => {
  const s = e.target.closest(".dslot,#dock,.tslot");
  if (!s) return;
  e.preventDefault();
  $$(".dslot.over,.tslot.over").forEach((x) => x !== s && x.classList.remove("over"));
  s.classList.add("over");
});
document.addEventListener("drop", (e) => {
  const s = e.target.closest(".dslot,#dock,.tslot");
  if (!s) return;
  e.preventDefault();
  s.classList.remove("over");
  document.body.classList.remove("dragging");
  const id = +e.dataTransfer.getData("text/x-pokemon");
  if (!id) return;
  const fromSlot = e.dataTransfer.getData("text/x-slot");
  const to = s.dataset.slot !== undefined ? +s.dataset.slot : null;
  if (fromSlot !== "" && to !== null) {
    const ids = S.team.ids, a = +fromSlot, b = Math.min(to, ids.length - 1);
    [ids[a], ids[b]] = [ids[b], ids[a]];
    teamChanged();
  } else addToTeam(id, to);
});

/* ------------------------------------------------------------------ Detailseite */
const moveSetKey = (id) => `set.${S.game || "-"}.${id}`;
function ownSet(id) {
  if (S.team.ids.includes(id)) return S.team.details[id]?.attacken || [];
  return store.get(moveSetKey(id), []);
}
function setOwnSet(id, moves) {
  moves = moves.slice(0, 4);
  if (S.team.ids.includes(id)) { S.team.details[id] = Object.assign({}, S.team.details[id], {attacken: moves}); saveTeam(); }
  else store.set(moveSetKey(id), moves);
}
let DETAIL = null;
async function detailView(id) {
  main.innerHTML = `<p class="hint">Lädt …</p>`;
  const rid = RID;
  const inTeam = S.team.ids.includes(id);
  const level = inTeam ? S.team.details[id]?.level || "" : "";
  const d = await api(`/api/pokemon/${id}?` + qs({spiel: S.game, level}));
  if (rid !== RID) return;
  DETAIL = d;
  ROWS[d.id] = d;
  const stats = d.werte.map((v, i) => `<span>${STAT[i]}</span><span class="num">${v}</span><span class="sbar" data-tip="${esc(statTip(i, v))}"><i style="width:${Math.min(100, v / 2)}%;background:${statColor(v)}"></i></span>`).join("");
  const eff = Object.entries(d.wirkung).sort((a, b) => b[1] - a[1] || a[0] - b[0]);
  const effHtml = (pred, title) => {
    const xs = eff.filter(([, f]) => pred(f));
    return xs.length ? `<h3>${title}</h3><div class="eff">${xs.map(([t, f]) => `<div data-tip="${esc(`${tname(t)}-Attacken treffen ${d.name} mit ×${fl(f)}`)}">${tchip(t)}<span class="f ${fcls(f)}">×${fl(f)}</span></div>`).join("")}</div>` : "";
  };
  const evo = d.entwicklung.length > 1 ? d.entwicklung.map((e, i) => (i && e.von ? `<span class="ar">→ ${esc(e.bedingungen.join(" oder ") || "")}</span>` : "") +
    `<a class="st" href="#pokemon/${e.id}">${img(e.id)}${esc(e.name)}</a>`).join("") : "";
  main.innerHTML = `
    <div class="bar"><a class="btn" href="#pokemon">← Liste</a>
      <label class="game2">Spiel <select class="gamesel"></select></label>
      ${inTeam ? `<button data-act="teamdel" data-id="${d.id}">Aus dem Team nehmen</button>` : teamFull() ? `<span class="hint">Team voll</span>` : `<button class="primary" data-act="teamadd" data-id="${d.id}">Ins Team</button>`}
      <a href="${esc(d.wiki)}" target="_blank" rel="noopener noreferrer">Im PokéWiki öffnen ↗</a>
      ${d.formen.length ? `<span class="hint">Formen:</span>` + d.formen.map((f) => `<a class="btn small" href="#pokemon/${f.id}">${esc(f.name)}</a>`).join("") : ""}</div>
    ${!d.im_spiel && S.game ? `<div class="note warn">In ${esc(gameName())} nicht enthalten.</div>` : ""}
    <div class="cols">
      <div class="box"><div class="head">${img(d.id, "big", true)}<div><h2>${esc(d.name)}</h2><div class="muted">#${d.nr ?? d.art} · ${esc(d.kategorie)}</div>
        <div style="margin-top:4px">${tchips(d.typen)}</div>${radar(d.werte, 210, true)}</div></div>
        <p>${esc(d.text)}</p><div class="stats">${stats}<span><b>Summe</b></span><span class="num" data-tip="${esc(statTip("summe", d.summe))}"><b style="color:${sumColor(d.summe)}">${d.summe}</b></span><span></span></div>
        ${d.faehigkeiten.length ? `<h3>Fähigkeiten</h3>` + d.faehigkeiten.map((a) => `<div data-tip="${esc(a.text)}"><b>${esc(a.name)}</b>${a.versteckt ? " <span class='cls'>versteckt</span>" : ""}${a.wirkt ? " <span class='cls'>ändert Typwirkung</span>" : ""}<div class="why">${esc(a.text)}</div></div>`).join("")
          : S.game === "legends-arceus" ? `<p class="hint">In Legenden: Arceus gibt es keine Fähigkeiten.</p>` : ""}
      </div>
      <div class="box"><h2>Typwirkung gegen ${esc(d.name)}</h2>
        ${d.faehigkeit_wirkt ? `<p class="hint">Mit Fähigkeit eingerechnet.</p>` : ""}
        ${effHtml((f) => f > 1, "Schwach gegen")}${effHtml((f) => f > 0 && f < 1, "Resistent gegen")}${effHtml((f) => f === 0, "Immun gegen (keine Wirkung)")}
        ${evo ? `<h3>Entwicklung</h3><div class="evo">${evo}</div>` : ""}
      </div>
    </div>
    <div class="box" style="margin-top:12px"><h2>Fundorte in ${esc(gameName())}</h2>
      ${d.fundorte.length ? `<div class="scroll"><table class="sort"><thead><tr>${th("Ort")}${th("Methode")}${th("Level")}${th("Bedingungen")}${th("Edition")}</tr></thead><tbody>
        ${d.fundorte.map((e) => `<tr><td>${esc(e.ort)}</td><td>${esc(e.methode)}</td><td data-s="${parseInt(e.level) || 0}">${esc(e.level)}</td><td>${esc(e.bedingungen.join(", "))}</td><td>${esc(e.editionen.join(", "))}</td></tr>`).join("")}</tbody></table></div>`
        : `<p class="hint">${S.game ? "Die PokéAPI kennt hier keine Fundorte" + (["legends-arceus", "scarlet-violet", "legends-za"].includes(S.game) ? " (für dieses Spiel liefert sie keine; kommt mit dem PokéWiki-Abruf)" : "") + "." : "Wähle oben ein Spiel."}</p>`}
    </div>
    <div class="box" id="mbox"></div>`;
  header();
  renderMoves(d.attacken, level);
  window.scrollTo(0, 0);
}
function renderMoves(A, level) {
  const d = DETAIL, id = d.id, inTeam = S.team.ids.includes(id);
  const all = Object.fromEntries([...A.attacken, ...A.status].map((m) => [m.id, m]));
  const mine = ownSet(id).filter((x) => all[x]);
  const covered = new Set();
  mine.map((x) => all[x]).filter((m) => m.klasse !== 1 && m.staerke).forEach((m) => Object.entries(S.chart?.[m.typ] || {}).forEach(([t, f]) => f > 1 && covered.add(t)));
  const mrow = (m, status = false) => `<tr class="${m.jetzt === false ? "off" : ""}"><td data-s="${esc(m.name)}" data-tip="${esc(m.text || "")}">${esc(m.name)}${m.geaendert ? ' <span class="cls" data-tip="Werte in diesem Spiel anders als heute">Spielwert</span>' : ""}</td>
    <td data-s="${tname(m.typ)}">${tchip(m.typ)}</td><td><span class="cls">${CLS[m.klasse] || ""}</span></td><td class="num" data-s="${m.staerke ?? 0}">${m.staerke ?? "–"}</td><td class="num" data-s="${m.genauigkeit ?? 101}">${m.genauigkeit ?? "–"}</td>
    ${status ? "" : `<td class="num" data-s="${m.wertung}"><b>${m.wertung}</b></td>`}<td data-s="${esc(m.wege[0] || "")}">${esc(m.wege.join(", "))}</td>${status ? "" : `<td class="why">${esc(m.gruende.join(" · "))}</td>`}
    <td>${mine.includes(m.id) ? `<button class="small on" data-act="mvdel" data-mid="${m.id}" data-tip="Aus deiner Auswahl">✓</button>` : mine.length < 4 ? `<button class="small" data-act="mvadd" data-mid="${m.id}" data-tip="In deine Auswahl (4 Plätze)">+</button>` : ""}</td></tr>`;
  $("#mbox").innerHTML = `<h2>Attacken${A.spiel_name ? " in " + esc(A.spiel_name) : ""}</h2>
    ${A.hinweis ? `<div class="note info">${esc(A.hinweis)}</div>` : ""}
    <div class="bar"><label>${inTeam ? "Level im Team" : "Bis Level"} <input id="lvl" type="number" min="1" max="100" style="width:70px" value="${esc(level || "")}"></label>
      <span class="hint">${inTeam ? "Gilt für dieses Team und filtert die Attacken." : "Leer: alle erlernbaren. Mit Level zählen nur Attacken, die bis dahin gehen."}</span></div>
    <div class="cols">
      <div><h3>Vorschlag: vier Attacken</h3><div class="chips">${A.moveset.map((m) => `<span class="chip">${tchip(m.typ)} <span class="pick">${esc(m.name)}</span> <span class="why">${esc(m.grund)}</span></span>`).join("") || `<span class="hint">Keine Schadens-Attacke.</span>`}</div>
        ${A.moveset.length ? `<button class="small" data-act="mvtake" style="margin-top:6px">Als eigene Auswahl übernehmen</button>` : ""}</div>
      <div><h3>Deine Auswahl${inTeam ? " (im Team)" : ""}</h3><div class="chips mine">${[0, 1, 2, 3].map((i) => { const m = all[mine[i]];
        return m ? `<span class="chip">${tchip(m.typ)} <span class="pick">${esc(m.name)}</span>${m.wertung ? ` <span class="why">${m.wertung}</span>` : ""} <button class="link" data-act="mvdel" data-mid="${m.id}">✕</button></span>` : `<span class="chip empty">Platz ${i + 1}</span>`; }).join("")}</div>
        ${mine.length ? `<p class="hint">Trifft sehr effektiv: ${covered.size ? [...covered].map(tchip).join(" ") : "nichts"} (${covered.size} von ${Object.keys(S.chart || {}).length} Typen)</p>` : `<p class="hint">Mit + in der Tabelle wählen. ${inTeam ? "Die Auswahl zählt in der Team-Bewertung." : "Gespeichert in diesem Browser; im Team zählt sie für die Bewertung."}</p>`}</div>
    </div>
    <h3>Schadens-Attacken nach Wertung</h3>
    <p class="hint">Wertung = Stärke × Genauigkeit × Eigentyp-Bonus × passender Angriffswert, mit Zu- und Abschlägen (Aussetzen, Anlauf, Rückstoß, Werte senken, Vorrang). Spalten zum Sortieren anklicken.</p>
    <div class="scroll"><table class="sort"><thead><tr>${th("Attacke")}${th("Typ")}${th("Klasse")}${th("Stärke")}${th("Gen.", "Genauigkeit in Prozent; – trifft immer")}${th("Wertung")}${th("Weg", "Wie das Pokémon die Attacke lernt")}${th("Gründe", "", true)}<th></th></tr></thead>
      <tbody>${A.attacken.map((m) => mrow(m)).join("") || `<tr><td colspan="9" class="hint">Keine Lernliste.</td></tr>`}</tbody></table></div>
    ${A.status.length ? `<details><summary>Status-Attacken (${A.status.length})</summary><div class="scroll"><table class="sort"><thead><tr>${th("Attacke")}${th("Typ")}${th("Klasse")}${th("Stärke")}${th("Gen.")}${th("Weg")}<th></th></tr></thead>
      <tbody>${A.status.map((m) => mrow(m, true)).join("")}</tbody></table></div></details>` : ""}`;
  $("#lvl").addEventListener("change", async (e) => {
    const v = e.target.value;
    if (inTeam) { S.team.details[id] = Object.assign({}, S.team.details[id], {level: v ? Math.max(1, Math.min(100, +v)) : null}); saveTeam(); dock(); }
    const A2 = await api(`/api/pokemon/${id}/attacken?` + qs({spiel: S.game, level: v}));
    d.attacken = A2;
    renderMoves(A2, v);
  });
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
      menu.innerHTML = rows.map((r, i) => `<button data-i="${i}">${img(r.id)}${esc(r.name)} ${tchips(r.typen)}</button>`).join("") || `<div class="hint" style="padding:6px">Nichts gefunden</div>`;
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
async function teamView() {
  const rid = RID;
  TEAMS = await api("/api/teams");
  if (rid !== RID) return;
  const w = weights();
  const here = TEAMS.filter((t) => t.spiel === S.game), other = TEAMS.filter((t) => t.spiel !== S.game);
  main.innerHTML = `
    <div class="box"><div class="bar"><b>Teams in</b> <select class="gamesel"></select>
      <select id="saved"><option value="">${S.team.tid ? "" : "Aktuelles Team (nicht gespeichert)"}</option>
        ${here.map((t) => `<option value="${t.id}"${t.id === S.team.tid ? " selected" : ""}>${esc(t.name)} (${t.mitglieder.length})</option>`).join("")}
        ${other.length ? `<optgroup label="Andere Spiele">${other.map((t) => `<option value="${t.id}"${t.id === S.team.tid ? " selected" : ""}>${esc(t.name)} · ${esc(gameName(t.spiel))}</option>`).join("")}</optgroup>` : ""}</select>
      <button data-act="tnew">Neues Team</button>${S.team.tid ? `<button data-act="trename">Umbenennen</button><button data-act="tdel">Löschen</button>` : `<button class="primary" data-act="tsave">Speichern</button>`}
      <button data-act="tclear">Leeren</button>
      <span class="hint grow">${S.team.tid ? "Änderungen speichern sich selbst." : "Ein gespeichertes Team behält Level und Attacken je Mitglied."}</span></div>
      <div class="bar"><div class="ac grow"><input id="add" type="search" placeholder="Pokémon hinzufügen: Name oder Nummer" style="width:100%"></div></div>
      <div class="tslots" id="slots"></div></div>
    <div class="cols">
      <div class="box"><h2>Bewertung</h2><div id="ev"><p class="hint">Füge Pokémon hinzu.</p></div></div>
      <div class="box"><h2>Verbesserungen</h2><div id="imp"><p class="hint">Lege Level und Attacken in der Detailansicht eines Mitglieds fest (Klick auf das Bild), dann zeigt sich hier, was besser ginge.</p></div></div>
    </div>
    <div class="box" style="margin-top:12px"><h2>Passende Pokémon finden</h2>
      <div class="cols"><div><h3>Ziel</h3>
        <div class="bar"><select id="preset">${Object.entries(PRESET_DE).map(([k, n]) => `<option value="${k}"${k === S.preset && !S.weights ? " selected" : ""}>${n}</option>`).join("")}
          <option value=""${S.weights ? " selected" : ""}>Eigene Gewichte</option></select>
          <label><input type="checkbox" id="tleg"${S.tleg ? " checked" : ""}> ohne Legendäre und Mysteriöse</label></div>
        <div class="weights">${Object.entries(CRIT).map(([k, n]) => `<span data-tip="${esc(CRIT_TIP[k])}">${n}</span><input type="range" min="0" max="10" step="1" data-w="${k}" value="${w[k]}"><span class="num">${w[k]}</span>`).join("")}</div>
        <div class="bar" style="margin-top:8px"><button class="primary" data-act="opt">Bestes Team suchen</button><span class="hint">Festgesetzte (📌) bleiben, der Rest wird aus den gefilterten Pokémon gefüllt.</span></div>
        <div id="opt"></div></div>
        <div><h3>Filter für Vorschläge und Suche</h3>${filterBar(S.tfilter, "tf", {sort: false})}</div></div>
      <h3>Vorschläge für den nächsten Platz</h3><div id="sug" class="sugs"><p class="hint">Mit mindestens einem Mitglied.</p></div>
    </div>
    <div class="box"><h2>Gegen Gegner</h2>
      <div class="bar"><div class="ac grow"><input id="foe" type="search" placeholder="Gegner hinzufügen (bis zu 6, etwa die Pokémon eines Arenaleiters)" style="width:100%"></div>
        ${S.foes.length ? `<button data-act="foeclear">Gegner leeren</button>` : ""}</div>
      <div id="mu"><p class="hint">Wähle Gegner: das Tool sagt, wen du schickst und wen du schonst.</p></div></div>`;
  header();
  autocomplete($("#add"), (r) => addToTeam(r.id));
  autocomplete($("#foe"), (r) => { if (S.foes.length < 6 && !S.foes.includes(r.id)) { S.foes.push(r.id); store.set("foes", S.foes); } matchup(); });
  bindFilter(S.tfilter, "tf", () => teamRefresh(), () => store.set("tfilter", S.tfilter));
  $("#tleg").addEventListener("change", (e) => { S.tleg = e.target.checked; store.set("tleg", S.tleg); teamRefresh(); });
  $("#saved").addEventListener("change", (e) => {
    const t = TEAMS.find((x) => x.id === +e.target.value);
    if (!t) return;
    S.team = {ids: t.mitglieder, fest: t.fest, tid: t.id, name: t.name, spiel: t.spiel, details: t.details || {}};
    if (Object.keys(t.gewichte || {}).length) { S.weights = t.gewichte; store.set("weights", S.weights); }
    store.set("team", S.team);
    if (t.spiel !== S.game) setGame(t.spiel); else teamView();
  });
  $("#preset").addEventListener("change", (e) => {
    if (e.target.value) { S.preset = e.target.value; S.weights = null; store.set("preset", S.preset); store.set("weights", null); }
    else S.weights = {...weights()};
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
  await teamRefresh();
  if (S.foes.length) matchup();
}
async function teamRefresh() {
  const t = S.team;
  const ev = await api("/api/team/bewerten", {spiel: S.game, ids: t.ids, gewichte: weights(), details: t.details});
  if (!$("#slots")) return;
  (ev.mitglieder || []).forEach((m) => { ROWS[m.id] = Object.assign(ROWS[m.id] || {}, m); });
  const byId = Object.fromEntries((ev.mitglieder || []).map((m) => [m.id, m]));
  const names = ev.attacken || {};
  $("#slots").innerHTML = [0, 1, 2, 3, 4, 5].map((i) => {
    const id = t.ids[i], m = byId[id];
    if (!m) return `<div class="tslot empty" data-slot="${i}">Platz ${i + 1}<br><span class="hint">hierher ziehen oder oben suchen</span></div>`;
    const fixed = t.fest.includes(id), det = t.details[id] || {};
    return `<div class="tslot${fixed ? " fixed" : ""}" data-slot="${i}" draggable="true" data-id="${id}">
      <button class="small pin${fixed ? " on" : ""}" data-act="pin" data-id="${id}" data-tip="Für die Teamsuche festsetzen">📌</button>
      <button class="small x" data-act="teamdel" data-id="${id}" data-tip="Entfernen">✕</button>
      <a href="#pokemon/${id}" draggable="false" data-tip="Detailansicht: Level und Attacken festlegen">${img(id, "mid", true)}<br><b>${esc(m.name)}</b></a>
      <div>${tchips(m.typen)}</div><div class="hint">${det.level ? "Level " + det.level + " · " : ""}Basiswerte <b style="color:${sumColor(m.summe)}">${m.summe}</b></div>
      <div class="mvs">${(det.attacken || []).map((x) => names[x] ? `<span class="mv">${tchip(names[x].typ)} ${esc(names[x].name)}</span>` : "").join("") || `<a class="hint" href="#pokemon/${id}">Attacken wählen</a>`}</div></div>`;
  }).join("");
  dock();
  if (!t.ids.length) { $("#ev").innerHTML = `<p class="hint">Füge Pokémon hinzu.</p>`; $("#sug").innerHTML = ""; $("#imp").innerHTML = ""; return; }
  const ms = ev.mitglieder;
  $("#ev").innerHTML = `<div class="score" data-tip="Gewichteter Schnitt der Kriterien (Gewichte unter „Ziel“)">${ev.wertung}<span class="hint"> / 100</span></div>
    <div class="crit">${Object.entries(CRIT).map(([k, n]) => `<span data-tip="${esc(CRIT_TIP[k])}">${n}</span><span class="sbar"><i style="width:${ev.kriterien[k] * 100}%"></i></span><span class="num">${Math.round(ev.kriterien[k] * 100)}</span>`).join("")}</div>
    ${ev.offen.length ? `<div class="note stop">Offene Schwächen (mehr Mitglieder schwach als resistent): ${tchips(ev.offen)}</div>` : `<div class="note go">Keine offene Schwäche.</div>`}
    ${ev.vierfach.length ? `<div class="note warn">4-fach-Schwächen: ${ev.vierfach.map(([a, n]) => `${esc(n)} gegen ${tchip(a)}`).join(", ")}</div>` : ""}
    ${ev.nicht_abgedeckt.length ? `<p class="hint">Nicht sehr effektiv getroffen${Object.keys(t.details).length ? " (mit den gewählten Attacken, sonst Eigentypen)" : " (mit Eigentypen)"}: ${tchips(ev.nicht_abgedeckt)}</p>` : ""}
    <p class="hint">${ev.physisch} physisch, ${ev.speziell} speziell · schnell: ${esc(ev.schnell.join(", ") || "keiner")}</p>
    <details><summary>Typwirkung je Mitglied</summary><div class="scroll"><table class="matrix"><tr><th></th>${ms.map((m) => `<th data-tip="${esc(m.name)}">${img(m.id)}</th>`).join("")}</tr>
      ${Object.keys(S.types).filter((a) => ev.matrix[ms[0].id]?.[a] !== undefined).map((a) => `<tr><th class="r">${tchip(a)}</th>${ms.map((m) => { const f = ev.matrix[m.id][a]; return `<td data-tip="${esc(`${tname(a)} gegen ${m.name}: ×${fl(f)}`)}"><span class="f ${fcls(f)}">${f === 1 ? "" : fl(f)}</span></td>`; }).join("")}</tr>`).join("")}</table></div></details>`;
  $("#imp").innerHTML = (ev.verbesserungen || []).length ? ev.verbesserungen.map((v) => `<div class="imp"><a href="#pokemon/${v.id}">${img(v.id)}</a><div><b>${esc(v.name)}</b>
      ${v.hinweise.map((h) => `<div class="why">${esc(h)}</div>`).join("")}
      ${v.besser.length ? `<div class="why">Stärker als ${esc(v.schwaechste)}: ${v.besser.map((b) => `${tchip(b.typ)} <b>${esc(b.name)}</b> (${b.wertung})`).join(", ")}</div>` : ""}
      ${!v.hinweise.length && !v.besser.length ? `<div class="why">Passt so.</div>` : ""}</div></div>`).join("")
    : `<p class="hint">Lege Level und Attacken in der Detailansicht eines Mitglieds fest (Klick auf das Bild), dann zeigt sich hier, was besser ginge.</p>`;
  if (t.ids.length < 6) {
    $("#sug").innerHTML = `<p class="hint">Rechnet …</p>`;
    const s = await api("/api/team/vorschlag", {spiel: S.game, ids: t.ids, gewichte: weights(), details: t.details, filter: {...filterQuery(S.tfilter), ohne_leg: S.tleg || S.tfilter.ohne_leg ? 1 : ""}});
    if (!$("#sug")) return;
    s.rows.forEach((r) => { ROWS[r.id] = Object.assign(ROWS[r.id] || {}, r); });
    $("#sug").innerHTML = s.rows.map((r) => `<div class="sugg" draggable="true" data-id="${r.id}">${monCard(r)}<div class="why"><b>+${r.plus}</b> · ${esc(r.gruende.join(" · "))}</div></div>`).join("") || `<p class="hint">Keine Vorschläge mit diesen Filtern.</p>`;
  } else $("#sug").innerHTML = `<p class="hint">Das Team ist voll. Entferne ein Mitglied, um Vorschläge zu sehen, oder nutze „Bestes Team suchen“.</p>`;
}
async function optimize() {
  $("#opt").innerHTML = `<p class="hint">Sucht … (einige Sekunden)</p>`;
  const r = await api("/api/team/optimieren", {spiel: S.game, fest: S.team.fest, gewichte: weights(), details: S.team.details, filter: {...filterQuery(S.tfilter), ohne_leg: S.tleg || S.tfilter.ohne_leg ? 1 : ""}});
  r.teams.forEach((t) => t.mitglieder.forEach((m) => { ROWS[m.id] = Object.assign(ROWS[m.id] || {}, m); }));
  $("#opt").innerHTML = `<p class="hint">Aus ${r.pool} Pokémon (Filter rechts) in ${esc(gameName())}.</p>` + r.teams.map((t, i) => `<div class="optt">
    <div class="bar"><b class="score-s">${t.wertung}</b><span class="grow">${t.mitglieder.map((m) => `<a href="#pokemon/${m.id}" data-tip="${esc(m.name)}">${img(m.id)}</a>`).join("")}</span>
    <button class="small" data-act="take" data-i="${i}">Übernehmen</button></div>
    <div class="why">${t.mitglieder.map((m) => esc(m.name)).join(", ")}${t.offen.length ? " · offen: " + t.offen.map(tname).join(", ") : ""}</div></div>`).join("");
  S.lastOpt = r.teams;
}
async function matchup() {
  const box = $("#mu");
  if (!box) return;
  if (!S.foes.length) { box.innerHTML = `<p class="hint">Wähle Gegner: das Tool sagt, wen du schickst und wen du schonst.</p>`; return; }
  const foeStrip = `<div class="foes">${S.foes.map((id) => { const r = ROWS[id]; return `<div class="foe">${img(id, "", true)}<b>${esc(r?.name || "#" + id)}</b><div>${tchips(r?.typen || [])}</div>
    <button class="small x" data-act="foedel" data-id="${id}" data-tip="Gegner entfernen">✕</button></div>`; }).join("")}</div>`;
  if (!S.team.ids.length) { box.innerHTML = foeStrip + `<p class="hint">Erst ein Team zusammenstellen.</p>`; return; }
  const r = await api("/api/team/gegner", {spiel: S.game, ids: S.team.ids, gegner: S.foes, details: S.team.details});
  r.einzeln.forEach((x) => { if (x.gegner.id) ROWS[x.gegner.id] = Object.assign(ROWS[x.gegner.id] || {}, x.gegner); });
  const verdict = Object.fromEntries(r.einzeln.flatMap((x) => x.rows.map((row) => [`${row.id}:${x.gegner.id}`, row])));
  box.innerHTML = `<div class="foes">${r.einzeln.map((x) => `<div class="foe">${img(x.gegner.id, "", true)}<b>${esc(x.gegner.name)}</b><div>${tchips(x.gegner.typen)}</div>
      <button class="small x" data-act="foedel" data-id="${x.gegner.id}" data-tip="Gegner entfernen">✕</button></div>`).join("")}</div>
    ${r.ohne_antwort.length ? `<div class="note warn">Niemand im Team ist klar im Vorteil gegen: ${esc(r.ohne_antwort.join(", "))}</div>` : `<div class="note go">Gegen jeden Gegner hast du mindestens einen guten Kandidaten.</div>`}
    <div class="scroll"><table class="vs"><thead><tr><th></th>${r.einzeln.map((x) => `<th data-tip="${esc(x.gegner.name)}">${img(x.gegner.id)}</th>`).join("")}</tr></thead><tbody>
      ${r.uebersicht.map((m) => `<tr><th class="r">${img(m.id)} ${esc(m.name)}</th>${r.einzeln.map((x) => { const v = verdict[`${m.id}:${x.gegner.id}`];
        return `<td class="v-${v.urteil}" data-tip="${esc(`${m.name} gegen ${x.gegner.name}: ${v.urteil}\n${v.gruende.join("\n")}`)}">${v.urteil}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div>
    <p class="hint">Nach Typen und Initiative; die Attacken des Gegners zählen über seine Typen, deine über die gewählten Attacken. Zelle hovern für die Gründe.</p>`;
}

/* ------------------------------------------------------------------ Attacken */
async function movesView() {
  const f = Object.assign({q: "", typen: [], klasse: "", lernbar: true, min: "", prio: false, kontakt: ""}, store.get("mfilter2", {}));
  const rid = RID;
  main.innerHTML = `<div class="bar"><span class="hint">Spiel</span><select class="gamesel"></select>
    <input id="mq" class="grow" type="search" placeholder="Attacke suchen" value="${esc(f.q)}"></div>
    <div class="bubbles">${Object.entries(S.types).map(([t, n]) => `<button class="tb t t${t}${f.typen.includes(t) ? " in" : ""}" data-mt="${t}">${esc(n)}</button>`).join("")}</div>
    <div class="bar"><span class="seg">${[["", "Alle"], ["2", "Physisch"], ["3", "Speziell"], ["1", "Status"]].map(([k, n]) => `<button data-mk="${k}" class="${f.klasse === k ? "on" : ""}">${n}</button>`).join("")}</span>
      <label data-tip="Nur Attacken, die im gewählten Spiel mindestens ein Pokémon lernen kann"><input type="checkbox" id="mlern"${f.lernbar ? " checked" : ""}> im Spiel erlernbar</label>
      <label><input type="checkbox" id="mprio"${f.prio ? " checked" : ""}> nur mit Vorrang</label>
      <label>Kontakt <select id="mkon"><option value="">egal</option><option value="1"${f.kontakt === "1" ? " selected" : ""}>mit</option><option value="0"${f.kontakt === "0" ? " selected" : ""}>ohne</option></select></label>
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
    $("#mv").innerHTML = `<div class="box scroll"><table class="sort"><thead><tr>${th("Attacke")}${th("Typ")}${th("Klasse")}${th("Stärke")}${th("Gen.", "Genauigkeit in Prozent; – trifft immer")}${th("AP")}
      ${th("Vorrang")}${th("Wertung", "Stärke × Genauigkeit mit Zu- und Abschlägen, ohne Eigentyp-Bonus")}${th("Lernen", "So viele Pokémon (und Formen) lernen sie im Spiel")}${th("Gen", "Generation, seit der es die Attacke gibt")}${th("Beschreibung", "", true)}</tr></thead><tbody>
      ${xs.map((m) => `<tr><td data-s="${esc(m.name)}"><b>${esc(m.name)}</b>${m.geaendert ? ' <span class="cls" data-tip="Werte in diesem Spiel anders als heute">Spielwert</span>' : ""}</td><td data-s="${tname(m.typ)}">${tchip(m.typ)}</td>
        <td><span class="cls">${CLS[m.klasse]}</span></td><td class="num" data-s="${m.staerke || 0}">${m.staerke || "–"}</td><td class="num" data-s="${m.genauigkeit ?? 101}">${m.genauigkeit ?? "–"}</td>
        <td class="num">${m.ap ?? ""}</td><td class="num">${m.prio || ""}</td><td class="num" data-s="${m.wertung}" data-tip="${esc(m.gruende.join("\n"))}"><b>${m.wertung || ""}</b></td>
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
async function chartView() {
  const ch = S.chart, ts = Object.keys(ch);
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Typtabelle Generation ${S.chartGen}</h2><span class="hint">Spiel</span><select class="gamesel"></select></div>
    <p class="hint">Zeile greift an, Spalte verteidigt. <span class="f f2">2</span> sehr effektiv · <span class="f f05">½</span> nicht sehr effektiv ·
      <span class="f f0">0</span> keine Wirkung (immun) · leer = normal (×1). Typ hovern für alle Stärken und Schwächen.</p>
    <div class="scroll"><table class="chart"><thead><tr><th class="corner"><span>Angriff ↓ · Verteidigung →</span></th>${ts.map((t) => `<th class="v" data-c="${t}"><span>${tchip(t)}</span></th>`).join("")}</tr></thead>
    <tbody>${ts.map((a) => `<tr><th class="r">${tchip(a)}</th>${ts.map((v) => { const f = ch[a][v];
      return `<td data-c="${v}" data-tip="${esc(`${tname(a)} gegen ${tname(v)}: ×${fl(f)}${f === 0 ? " (keine Wirkung)" : f > 1 ? " (sehr effektiv)" : f < 1 ? " (nicht sehr effektiv)" : ""}`)}">${f === 1 ? "" : `<span class="f ${fcls(f)}">${fl(f)}</span>`}</td>`; }).join("")}</tr>`).join("")}</tbody>
    </table></div></div>`;
  header();
  const table = $(".chart");
  table.addEventListener("mouseover", (e) => {
    const td = e.target.closest("td[data-c]");
    $$(".hl", table).forEach((x) => x.classList.remove("hl"));
    if (td) $$(`[data-c="${td.dataset.c}"]`, table).forEach((x) => x.classList.add("hl"));
  });
  table.addEventListener("mouseleave", () => $$(".hl", table).forEach((x) => x.classList.remove("hl")));
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
    <div class="box" style="margin-top:12px"><h2>Protokoll</h2><div class="log">${esc((st.log || []).join("\n") || "Noch kein Lauf.")}</div></div>
    <div class="box"><h2>Verbindungstest</h2><p class="hint">Fragt jede Quelle einmal an und beschreibt die Antwort. Speichert nichts.</p>
      <button data-act="diag">Test starten</button><div id="diag"></div></div>
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
  if (st.running) setTimeout(() => location.hash.startsWith("#einstellungen") && refreshMeta(), 4000);
}
async function diag() {
  await api("/api/diag", {});
  const poll = async () => {
    const d = await api("/api/diag");
    const el = $("#diag");
    if (!el) return;
    if (d.running) { el.innerHTML = `<p class="hint">Läuft …</p>`; setTimeout(poll, 1500); return; }
    el.innerHTML = `<div class="log">${esc((d.lines || []).join("\n") || d.error)}</div>`;
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
    if (act === "thm") {
      const cur = document.documentElement.dataset.theme;
      const next = cur === "dark" ? "light" : cur === "light" ? "" : "dark";
      if (next) document.documentElement.dataset.theme = next; else delete document.documentElement.dataset.theme;
      try { if (next) localStorage.setItem("px.theme", next); else localStorage.removeItem("px.theme"); } catch (x) { /* egal */ }
      header();
    } else if (act === "dock") { S.dock = !S.dock; store.set("dock", S.dock); dock(); }
    else if (act === "teamadd") { addToTeam(id); if (location.hash.startsWith("#pokemon/")) route(); }
    else if (act === "teamdel") { removeFromTeam(id); if (location.hash.startsWith("#pokemon/")) route(); }
    else if (act === "pin") {
      S.team.fest = S.team.fest.includes(id) ? S.team.fest.filter((x) => x !== id) : [...S.team.fest, id];
      saveTeam(); teamRefresh();
    } else if (act === "freset") {
      const which = b.dataset.fid === "lf" ? "filter" : "tfilter";
      S[which] = filter0(which === "tfilter" ? {endstufe: true} : {});
      store.set(which === "filter" ? "filter2" : "tfilter", S[which]);
      route();
    } else if (act === "opt") await optimize();
    else if (act === "take") {
      const ids = S.lastOpt[+b.dataset.i].ids;
      Object.keys(S.team.details).forEach((k) => { if (!ids.includes(+k)) delete S.team.details[k]; });
      S.team.ids = ids;
      teamChanged();
    } else if (act === "tclear") { S.team = Object.assign(S.team, {ids: [], fest: [], details: {}}); saveTeam(); teamView(); }
    else if (act === "tnew") {
      const name = prompt("Name des neuen Teams", "Team " + gameName());
      if (!name) return;
      const r = await api("/api/teams", {name, spiel: S.game, mitglieder: [], fest: [], gewichte: weights(), details: {}});
      S.team = {ids: [], fest: [], details: {}, tid: r.id, name, spiel: S.game};
      store.set("team", S.team); teamView();
    } else if (act === "tsave" || act === "trename") {
      const name = prompt("Name des Teams", S.team.name || "Team " + gameName());
      if (!name) return;
      const r = await api("/api/teams", {id: S.team.tid, name, spiel: S.team.spiel ?? S.game, mitglieder: S.team.ids, fest: S.team.fest, gewichte: weights(), details: S.team.details});
      S.team.tid = r.id; S.team.name = name; S.team.spiel = S.team.spiel ?? S.game; store.set("team", S.team); teamView();
    } else if (act === "tdel") {
      if (!confirm(`Team „${S.team.name}“ löschen?`)) return;
      await api("/api/teams/loeschen", {id: S.team.tid});
      S.team = {ids: S.team.ids, fest: S.team.fest, details: S.team.details};
      store.set("team", S.team); teamView();
    } else if (act === "foedel") { S.foes = S.foes.filter((x) => x !== id); store.set("foes", S.foes); matchup(); }
    else if (act === "foeclear") { S.foes = []; store.set("foes", S.foes); teamView(); }
    else if (act === "mvadd" || act === "mvdel" || act === "mvtake") {
      const pid = DETAIL.id, cur = ownSet(pid), mid = +b.dataset.mid;
      setOwnSet(pid, act === "mvadd" ? [...cur, mid] : act === "mvdel" ? cur.filter((x) => x !== mid) : DETAIL.attacken.moveset.map((m) => m.id));
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
window.addEventListener("hashchange", route);
refreshMeta().catch((e) => { main.innerHTML = `<div class="note stop">Server nicht erreichbar: ${esc(e.message)}</div>`; });
