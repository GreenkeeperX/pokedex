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
  let r;
  for (let n = 0; ; n++) {          // Netzfehler (Server kurz beschäftigt, Verbindung neu): zweimal nachfassen
    try { r = await fetch(path, opt); break; } catch (e) { if (n >= 2) throw e; await new Promise((ok) => setTimeout(ok, 400 * (n + 1))); }
  }
  const d = await r.json().catch(() => null);
  // status am Fehler: 404 heißt „gibt es hier nicht“; eine Antwort 200, die sich nicht lesen lässt, ist ein Fehler und kein leeres Ergebnis
  if (!r.ok || d === null) throw Object.assign(new Error(d?.error || (r.ok ? "Antwort nicht lesbar" : `HTTP ${r.status}`)), {status: r.status});
  const f = r.headers.get("X-Pokedex-Fehler");
  if (f) {                   // der Server hat geantwortet, konnte aber einen Teil nicht lesen (app/fehler.py): [[Stelle, Art], …]
    let xs = [];
    try { xs = JSON.parse(f); } catch (e) { /* dann ohne Einzelheiten */ }
    (xs.length ? xs : [["Fehler", ""]]).forEach(([wo, art]) => TEILE.add(art ? `${wo}: ${art}` : wo));
    drawNotes();
  }
  return d;
}
/* Hinweise über der Ansicht (seit 0.58.1): Was nicht geladen oder nicht gespeichert werden konnte, steht dort einmal, statt
   still zu fehlen. Gleiche Hinweise zählen hoch, eine neue Ansicht räumt ab. */
const NOTES = new Map(), TEILE = new Set();     // TEILE: was der Server nicht lesen konnte (eine Zeile für alle)
function drawNotes() {
  const el = $("#hinweise");
  if (!el) return;
  const rows = [...NOTES].map(([t, n]) => `<p>${esc(t)}${n > 1 ? ` <span class="hint">(${n}-mal)</span>` : ""}</p>`);
  if (TEILE.size) rows.unshift(`<p>Ein Teil dieser Ansicht fehlt: Der Server konnte ihn nicht lesen (${esc([...TEILE].join("; "))}). Einzelheiten unter <a href="#einstellungen">Einstellungen</a>, Fehler.</p>`);
  el.innerHTML = rows.length ? `<div class="note warn hw"><div>${rows.join("")}</div><button data-act="hwzu" title="Hinweis ausblenden">×</button></div>` : "";
}
const clearNotes = () => { NOTES.clear(); TEILE.clear(); drawNotes(); };
function hinweis(text) { NOTES.set(text, (NOTES.get(text) || 0) + 1); drawNotes(); }
// für .catch beim Laden: den Teil nennen, der fehlt, und mit dem Ersatzwert weiterzeichnen (404: gibt es hier nicht, kein Fehler)
const teil = (was, ersatz) => (e) => { if (e.status !== 404) hinweis(`${was}: nicht geladen (${e.message}).`); return ersatz; };
// für .catch beim Speichern: sagen, dass es nicht gespeichert ist, und die Anzeige zurücknehmen
const ungespeichert = (zurueck) => (e) => { hinweis(`Nicht gespeichert (${e.message}). Die Änderung ist zurückgenommen.`); if (zurueck) zurueck(); };
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== "" && v !== null && v !== undefined && v !== false)).toString();
const weights = () => S.weights || PRESETS[S.preset] || PRESETS.ausgewogen;
const gameName = (k = S.game) => (S.meta?.spiele || []).find((g) => g.kennung === k)?.name || "alle Spiele";

/* ------------------------------------------------------------------ Bausteine */
const tname = (t) => S.types[t] || String(t);
const fl = (f) => ({0: "0", 0.25: "¼", 0.4: "0,4", 0.5: "½", 1: "1", 2: "2", 2.5: "2,5", 4: "4"}[f] ?? String(f));
// doppelte Schwäche oder Resistenz: ×4 und ×¼, in Legenden: Arceus ×2,5 und ×0,4 (darum „über 2“ und „unter ½“)
const fcls = (f) => f === 0 ? "f0" : f > 2 ? "f4" : f > 1 ? "f2" : f < 0.5 ? "f025" : f < 1 ? "f05" : "f1";
/* Wirkung gegen mehrere Typen: das Produkt, außer das Spiel hat eine eigene Regel (S.chartDoppelt vom Server:
   [doppelt sehr effektiv, doppelt nicht sehr effektiv], in Legenden: Arceus [2,5, 0,4]). Die einzige Stelle, die multipliziert */
const effMul = (fs) => { const f = fs.reduce((a, b) => a * b, 1), dd = S.chartDoppelt; return dd && f > 2 ? dd[0] : dd && f > 0 && f < 0.5 ? dd[1] : f; };
const statHue = (v) => Math.min(v, 150) * 0.85;
const statColor = (v) => `hsl(${statHue(v)} 62% 44%)`;
/* Zeile im Werte- und Effort-Diagramm wie bei den Basiswerten: Name, Wert, Balken in der Farbe des Basiswerts (die Teile
   in Stufen derselben Farbe), dahinter der Wert am Ziel. Darunter die Summe */
const elRow = (k, x, segs, tip, extra) => `<div class="elb-n">${k}</div><div class="elb-v"><b>${x.wert}</b></div><div class="elb" style="--h:${statHue(x.basis)}" ${tip}>${segs}</div>`
  + `<div class="elb-z">${extra > 0 ? `<span class="hint">→ ${x.wert_ziel}</span>` : ""}</div>`;
const elSum = (rows) => { const s = rows.reduce((a, x) => a + x.wert, 0), z = rows.reduce((a, x) => a + (x.wert_ziel ?? x.wert), 0);
  return `<div class="elb-n elb-s">Summe</div><div class="elb-v elb-s"><b>${s}</b></div><div></div><div class="elb-z elb-s">${z > s ? `<span class="hint">→ ${z}</span>` : ""}</div>`; };
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
  for (const a of Object.keys(ch)) out[a] = effMul(types.map((d) => ch[a][d] ?? 1));
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
/* Netz der Werte (Effort Levels, IV/EV): wie das große Radar, Basiswert grau, dazu Level hell, jetzt rot, Ziel gestrichelt */
function statNet(rows, top, part) {
  const S0 = 230, c = S0 / 2, R = c - 40;
  const pt = (k, f) => { const a = -Math.PI / 2 + k * Math.PI / 3; return [c + Math.cos(a) * R * f, c + Math.sin(a) * R * f]; };
  const ring = (f, cls) => `<polygon class="${cls}" points="${RADAR_ORDER.map((_, k) => pt(k, f).map((v) => v.toFixed(1)).join(",")).join(" ")}"/>`;
  const poly = (fn, cls) => `<polygon class="${cls}" points="${RADAR_ORDER.map((i, k) => pt(k, Math.max(0.03, Math.min(1, fn(rows[i]) / top))).map((v) => v.toFixed(1)).join(",")).join(" ")}"/>`;
  return `<svg class="radar elnet" width="${S0}" height="${S0}" viewBox="0 0 ${S0} ${S0}" aria-hidden="true">${ring(1, "rg")}${ring(0.25, "rg1")}${ring(0.75, "rg1")}${ring(0.5, "rg2")}
    ${RADAR_ORDER.map((_, k) => `<line x1="${c}" y1="${c}" x2="${pt(k, 1)[0].toFixed(1)}" y2="${pt(k, 1)[1].toFixed(1)}" class="rs"/>`).join("")}
    ${poly((x) => x.wert_ziel, "n-z")}${poly((x) => x.wert, "n-e")}${poly((x) => x.wert - x.teile[part], "n-l")}${poly((x) => x.teile.basis, "n-b")}
    ${RADAR_ORDER.map((i, k) => { const [x, y] = pt(k, 1.3); return `<text x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="middle">${STAT_K[i]} <tspan class="v">${rows[i].wert}</tspan></text>`; }).join("")}</svg>`;
}
/* Rechenweg als Tooltip: der HTML-Text liegt in TIPM, das Element trägt nur die Nummer (data-tip-calc) */
let TIPN = 0;
const TIPM = new Map();
function tipRef(html) {
  TIPM.set(++TIPN, html);
  if (TIPM.size > 5000) TIPM.delete(TIPM.keys().next().value);
  return `data-tip-calc="${TIPN}"`;
}
/* Woraus ein Wert besteht: farbige Teile wie im Balken, Summe, darunter die Formel */
function partsTip(title, parts, total, formulas) {
  return `<div class="tt">${esc(title)}</div><table class="ctip">${parts.filter((p) => p[2]).map(([cls, label, v], k) => `<tr><td><span class="sw ${cls}"></span>${esc(label)}</td><td class="n">${k && v > 0 ? "+" : ""}${v}</td></tr>`).join("")}
    <tr class="sum"><td>Wert</td><td class="n">${total}</td></tr></table>${formulas.filter(Boolean).map((f) => `<div class="muted">${esc(f)}</div>`).join("")}`;
}
const de = (v) => String(v).replace(".", ",");
/* Kleine Tabelle für Rechenwege: [Bezeichnung, Wert, Erklärung]; leere Zeilen fallen weg */
const calcRows = (rows) => `<table class="ctip">${rows.filter(Boolean).map(([l, v, h]) => `<tr><td>${esc(l)}</td><td class="n">${v}</td><td class="muted">${esc(h || "")}</td></tr>`).join("")}</table>`;
/* Fangchance: a = (3 − 2 × KP-Anteil) / 3 × Fangrate × Ball × Status, dann je nach Generation. Gerechnet hat der Server
   (catch_steps): f.b[col] ist der Wert der Rüttelprobe, f.proben die Zahl der Proben; hier steht nur der Rechenweg */
function catchTip(m, f, hpLabel, share, st, stLabel, v, col) {
  const gen = m.fang_gen || 9, rate = Math.max(1, m.fangrate + (f.plus || 0)), a = (3 - 2 * share) / 3 * rate * f.faktor * st;
  const n = f.proben, b = f.b ? f.b[col] : null;
  const bf = gen <= 4 ? "⌊1048560 / ⌊√⌊√⌊16711680 / ⌊a⌋⌋⌋⌋⌋" : `⌊65536 × (a / 255)<sup>${gen === 5 ? "0,25" : "0,1875"}</sup>⌋`;
  return `<div class="tt">${esc(f.ball)}, ${esc(hpLabel)}${stLabel ? ", " + esc(stLabel) : ""}</div>
    ${calcRows([["Fangrate", rate, f.plus ? `der Art ${m.fangrate}, Schwerball ${f.plus > 0 ? "+" : ""}${f.plus}` : "der Art, 3 bis 255"], ["KP", `×${share ? "⅓" : "1"}`, share ? "volle KP: (3 − 2) / 3" : "fast keine KP: (3 − 0) / 3"],
      ["Ball", `×${de(f.faktor)}`, ""], st !== 1 ? ["Status", `×${de(st)}`, stLabel] : null])}
    <div class="tt">Fangwert a</div><div>(3 × KP<sub>max</sub> − 2 × KP) / (3 × KP<sub>max</sub>) × Fangrate × Ball × Status</div>
    <div class="muted">= ${share ? "⅓" : "1"} × ${rate} × ${de(f.faktor)}${st !== 1 ? " × " + de(st) : ""} = <b style="color:#fff">${de(Math.round(a * 10) / 10)}</b></div>
    <div class="tt">Chance je Wurf</div>
    ${a >= 255 ? `<div>a ab 255: der Ball fängt immer</div>`
      : b == null ? `<div>a / 255 = ${de(Math.round(a * 10) / 10)} / 255</div>`
      : `<div>${n} Rüttelproben, jede mit b / 65536</div><div class="muted">b = ${bf} = ${b}; (${b} / 65536)<sup>${n}</sup></div>`}
    <div class="tt">Ergebnis</div><div><b>${de(v)} %</b>${m.fang_grob ? " (Richtwert: dieses Spiel rechnet anders)" : ""}</div>`;
}
/* Initiative-Wert: Werte, Formel mit Zahlen, Faktoren (Item, Rückenwind, Wahlschal), Ergebnis */
function speedTip(title, o) {
  const {base, lv, gen, iv, ev, nat = 1, el, mults = []} = o;
  let rows, form, nums, val;
  if (LA()) {
    const fk = EL_FAKTOR[el];
    val = laStat(base, lv, el, nat);
    rows = [["Basis", base], ["Level", lv], ["Effort Level", el, `Faktor ${fk}`], nat !== 1 ? ["Wesen", `×${de(nat)}`] : null];
    form = "⌊⌊(Level / 50 + 1) × Basis / 1,5⌋ × Wesen⌋ + ⌊(√Basis × Faktor + Level) / 2,5 + 0,5⌋";
    nums = `⌊⌊(${lv} / 50 + 1) × ${base} / 1,5⌋${nat !== 1 ? " × " + de(nat) : ""}⌋ + ⌊(√${base} × ${fk} + ${lv}) / 2,5 + 0,5⌋`;
  } else if (gen <= 2) {
    val = speedStat(base, lv, iv, ev, 1, gen);
    const r = Math.min(255, Math.ceil(Math.sqrt(ev)));
    rows = [["Basis", base], ["Level", lv], ["DV", iv, "0 bis 15"], ["Stat Exp", ev, `Wurzel ${r}, höchstens 255`]];
    form = "⌊((Basis + DV) × 2 + ⌊√StatExp / 4⌋) × Level / 100⌋ + 5";
    nums = `⌊((${base} + ${iv}) × 2 + ⌊${r} / 4⌋) × ${lv} / 100⌋ + 5`;
  } else {
    val = speedStat(base, lv, iv, ev, nat, gen);
    rows = [["Basis", base], ["Level", lv], ["IV", iv, "0 bis 31"], ["EV", ev, "0 bis 252"], nat !== 1 ? ["Wesen", `×${de(nat)}`, nat > 1 ? "steigert Initiative" : "senkt Initiative"] : null];
    form = "⌊(⌊(2 × Basis + IV + ⌊EV / 4⌋) × Level / 100⌋ + 5) × Wesen⌋";
    nums = `⌊(⌊(2 × ${base} + ${iv} + ⌊${ev} / 4⌋) × ${lv} / 100⌋ + 5)${nat !== 1 ? " × " + de(nat) : ""}⌋`;
  }
  let end = val;
  mults.forEach(([, f]) => { end *= f; });
  end = Math.floor(end);
  return `<div class="tt">${esc(title)}</div>${calcRows(rows)}
    <div class="tt">Initiative-Wert</div><div>${form}</div><div class="muted">${nums} = <b style="color:#fff">${val}</b></div>
    ${mults.length ? `<div class="tt">Dann</div><div class="tg">${mults.map(([l, f]) => `<span class="fx">${esc(l)} <b>×${de(f)}</b></span>`).join("")}</div>
      <div class="tt">Ergebnis</div><div><b>${end}</b></div>` : ""}`;
}
/* Schadensrechner: Rechenweg einer Zeile (Werte, Grundschaden, Faktoren der Reihe nach, Ergebnis) */
function dmgTip(r, x) {
  const fx = (x.faktoren || []).map(([l, v]) => `<span class="fx">${esc(l)}${v == null ? "" : ` <b>×${typeof v === "number" ? de(v) : esc(v)}</b>`}</span>`).join("");
  const lv = r.gen === 1 && x.faktoren?.some((f) => String(f[0]).startsWith("Volltreffer")) ? r.level * 2 : r.level;
  const k = Math.floor(2 * lv / 5) + 2, old = r.gen <= 2;
  return `<div class="tt">${esc(r.angreifer)}: ${esc(r.attacke)} gegen ${esc(x.name)}</div>
    <table class="ctip"><tr><td>Angriff</td><td class="n">${x.angriff}</td><td class="muted">${esc(x.a_info || "")}</td></tr>
      <tr><td>Verteidigung</td><td class="n">${x.verteidigung}</td><td class="muted">${esc(x.d_info || "")}</td></tr>
      <tr><td>KP</td><td class="n">${x.kp}</td><td></td></tr></table>
    <div class="tt">Grundschaden</div>
    ${x.formel ? `<div>${esc(x.formel[0])}</div><div class="muted">${esc(x.formel[1])} = <b style="color:#fff">${x.grund}</b></div>`
      : `<div>${old ? "min(" : ""}⌊⌊(2 × Level / 5 + 2) × Stärke × Angriff / Verteidigung⌋ / 50⌋${old ? ", 997)" : ""} + 2</div>
    <div class="muted">${old ? "min(" : ""}⌊⌊${k} × ${x.staerke} × ${x.angriff} / ${x.verteidigung}⌋ / 50⌋${old ? ", 997)" : ""} + 2 = <b style="color:#fff">${x.grund}</b>${old && (x.angriff > 255 || x.verteidigung > 255) ? " (Werte über 255: beide geviertelt)" : ""}</div>`}
    <div class="tt">Dann der Reihe nach</div><div class="tg">${fx}</div>
    <div class="tt">Ergebnis</div><div><b>${x.min}–${x.max}</b> von ${x.kp} KP = ${String(x.min_pct).replace(".", ",")}–${String(x.max_pct).replace(".", ",")} %</div>`;
}
function radarTipHtml(werte) {
  return `<div class="tt" style="margin-top:0">Netzdiagramm</div><div class="muted">Außen = Höchstwert aller Pokémon, Ringe bei 25, 50 und 75 %</div>
    <table class="rtip"><thead><tr><th></th><th>Wert</th><th></th><th>Skala</th><th>Höchstwert</th></tr></thead><tbody>${[0, 1, 2, 3, 4, 5].map((i) => `<tr><td>${STAT[i]}</td><td class="num"><b>${werte[i]}</b></td>
      <td><span class="sbar"><i style="width:${Math.min(100, werte[i] / statMax(i) * 100)}%;background:${statColor(werte[i])}"></i></span></td>
      <td class="num">${scale10(i, werte[i])}/10</td><td class="num muted">${statMax(i)}</td></tr>`).join("")}</tbody></table>`;
}

const teamFull = () => S.team.ids.length >= 6;
const isFav = (id) => S.favs.some((f) => f.id === id);
/* 0.60.0: Was im gewählten Spiel gilt, sagt das Spielprofil des Servers (app/spiele.py, in /api/meta je Spiel als profil);
   die Oberfläche fragt Eigenschaften, nicht die Kennung des Spiels. Felder und Werte: docs/spiele.md */
const PROFIL = () => S.meta?.spiele?.find((g) => g.kennung === S.game)?.profil || {};
/* Kampfspiel (Champions): „im Kader“ statt gefangen, kein Schillernd, keine Fangchance, „Kampf“ statt „Karte“ */
const BATTLE = () => !!PROFIL().kampf;
const TERA = () => !!PROFIL().tera;          // Tera-Typ je Team-Platz
const RAIDS = () => !!PROFIL().raids;        // Reiter Raids (Tera-Raids)
const GEN = () => S.meta?.spiele?.find((g) => g.kennung === S.game)?.gen || 9;
const noAbil = () => PROFIL().faehigkeiten === false;
const isCaught = (id) => S.caught.has(id);
const isShiny = (id) => S.shiny.has(id);
const isAlpha = (id) => S.alpha.has(id);
/* Alpha: nur in Spielen mit Alphas und nur für Pokémon, die es dort als Alpha gibt (oder schon so markiert sind) */
const alphaBtn = (id) => S.alphaOk.has(id) || isAlpha(id) ? `<span class="a alp${isAlpha(id) ? " on" : ""}" data-act="alpha" data-id="${id}"
  data-tip="${isAlpha(id) ? "Als Alpha gefangen; Klick: kein Alpha" : "Als Alpha gefangen markieren"}">α</span>`
  : S.alphaOk.size ? `<span class="a alp ph"></span>` : "";   // 0.47.11: leerer Platz, damit die übrigen Knöpfe an ihrer Stelle bleiben
// Pokéball: gefangen, schillernd gefangen (goldener Ball mit Funkeln) oder nichts
const ball = (id, on = isCaught(id)) => icon("ball", on).replace('class="ic ic-ball on"', `class="ic ic-ball on${isShiny(id) ? " shiny" : ""}"`)
;
const ballTip = (id) => BATTLE() ? (isCaught(id) ? "Im Kader; Klick: nicht mehr im Kader" : "In den Kader")
  : isShiny(id) ? `Schillernd in deiner Sammlung (${esc(gameName())}); Klick: doch nicht gefangen`
  : isCaught(id) ? (shinyLock(id) === "nie" ? `In deiner Sammlung (${esc(gameName())}). Schillernd gibt es hier nicht (Shiny-Sperre); Klick: doch nicht gefangen`
    : `In deiner Sammlung (${esc(gameName())}); Klick: schillernd${shinyLock(id) === "tausch" ? (S.shinyGen1 ? " (in Generation I unsichtbar, erst nach dem Tausch nach Gold, Silber oder Kristall)" : " (hier nur per Tausch oder Verteilung)") : ""}`)
  : "Als gefangen markieren";
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
  // Haken: im Team (Klick nimmt es heraus); sonst blass, Klick füllt einen freien Platz
  return `<span class="acts">${inTeam ? `<span class="a team on" data-act="teamdel" data-id="${id}" data-slot="${S.team.ids.lastIndexOf(id)}" data-tip="Im Team; Klick: aus dem Team">${icon("team")}</span>`
    : teamFull() ? `<span class="a team" data-act="favswap" data-id="${id}" data-tip="Team voll; Klick: wählen, wen es ersetzt">${icon("team")}</span>`   // 0.47.6: wie ⇄ im Team-Reiter
    : `<span class="a team" data-act="teamadd" data-id="${id}" data-tip="Ins Team (auf den nächsten freien Platz)">${icon("team")}</span>`}`
    + `<span class="a${fav ? " on" : ""}" data-act="fav" data-id="${id}" data-tip="${fav ? "Favorit; Klick: aus den Favoriten" : "Zu den Favoriten (Kader zum schnellen Tauschen)"}">${icon("fav", fav)}</span>`
    + `<span class="a${got ? " on" : ""}" data-act="caught" data-id="${id}" data-tip="${ballTip(id)}">${ball(id, got)}</span>` + alphaBtn(id) + `</span>`;   // 0.47.5: ohne „+“, das Häkchen nimmt ins Team
}
// mode: true = Sammlung (⇄ wählt zum Übertragen aus); Favoriten im Team ohne ⇄ (0.47.7: das Häkchen nimmt ins Team oder tauscht)
function monCard(r, mode = false, extra = "") {   // extra: eigene Zeile unter den Basiswerten (0.56.2, „Was fehlt mir noch?“)
  const xmode = mode === true, inTeam = S.team.ids.includes(r.id), xs = xmode && XSEL.has(r.id);
  return `<a class="mon${inTeam ? " inteam" : ""}${xs ? " xon" : ""}" href="#pokemon/${r.id}" draggable="true" data-id="${r.id}"><span class="nr"${r.dexk ? ` data-tip="Nummer im ${r.dex + 1}. Pokédex des Spiels"` : ""}>#${r.dexk || ""}${r.nr ?? r.art}</span>${xmode
    ? `<span class="xs${xs ? " on" : ""}" data-act="xsel" data-id="${r.id}" data-tip="${xs ? "Ausgewählt zum Übertragen; Klick: abwählen" : "Zum Übertragen auswählen"}">⇄</span>`
    : ""}<span class="sp">${img(r.id)}${acts(r.id)}</span>
    <span class="mi"><span class="nl"><span class="n">${esc(r.name)}</span></span><span class="ty">${tchips(r.typen)}</span>
    ${r.legendaer ? `<span class="s">legendär</span>` : ""}<span class="s">Basiswerte <b style="color:${sumColor(r.summe)}">${r.summe}</b></span>${r.forschung_offen != null ? `<span class="s">Forschung offen <b>${r.forschung_offen}</b></span>` : ""}${extra}</span>
    ${radar(r.werte, 100)}</a>`;
}
// Marken überall neu zeichnen, ohne die Seite neu aufzubauen
const favStar = (id) => `<button class="favstar${isFav(id) ? " on" : ""}" data-act="fav" data-id="${id}" data-favstar data-tip="${isFav(id) ? "Favorit; Klick: aus den Favoriten" : "Zu den Favoriten"}">${icon("fav", isFav(id))}</button>`;
function redrawMarks() {
  $$("[data-favstar]").forEach((b) => { b.outerHTML = favStar(+b.dataset.id); });
  $$(".mk").forEach((el) => { const a = el.closest("[data-id]"); if (a) el.outerHTML = marks(+a.dataset.id); });
  $$(".acts").forEach((el) => { const a = el.closest("[data-id]"); if (a) el.outerHTML = acts(+a.dataset.id); });
  $$("[data-markbtn]").forEach((b) => { const id = +b.dataset.id, k = b.dataset.markbtn, on = k === "cmp" ? cmpMarked(id) : k === "fav" ? isFav(id) : k === "alpha" ? isAlpha(id) : isCaught(id);
    b.classList.toggle("on", on); b.innerHTML = markLabel(k, on, id); if (k === "gef") b.dataset.tip = ballTip(id); });
  $$(".mon[data-id]").forEach((el) => el.classList.toggle("inteam", S.team.ids.includes(+el.dataset.id)));
}
const cmpList = () => store.get("cmpMerk", []);
const cmpMarked = (id) => cmpList().includes(id);
function cmpToggle(id) {
  const xs = cmpList().filter((x) => x !== id);
  if (xs.length === cmpList().length) xs.unshift(id);
  store.set("cmpMerk", xs.slice(0, 8));
}
const markLabel = (k, on, id) => k === "cmp" ? `${on ? "✓ gemerkt" : "＋ merken"}`
  : k === "fav" ? `${icon("fav", on)} ${on ? "Favorit" : "Zu den Favoriten"}`
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
  const taken = effMul(own.map((d) => ch[t]?.[d] ?? 1));
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
  return sec("Schwach gegen", [4, 2.5, 2]) + sec("Resistent gegen", [0.5, 0.4, 0.25]) + sec("Immun gegen (keine Wirkung)", [0])
    || `<p class="hint">Keine Schwäche, keine Resistenz.</p>`;
}
/* Hover-Karte: auf einen Blick, was die eigenen Typen austeilen (bester eigener Typ je Ziel), was sie einstecken
   (beide Typen zusammen) und gegen wen beides passt (trifft ×2 oder mehr und steckt höchstens ×½ ein) */
function glanceHtml(own, d) {
  const ch = S.chart || {}, all = Object.keys(ch);
  const best = (t) => Math.max(...own.map((a) => ch[a]?.[t] ?? 1));
  const acls = (f) => f > 2 ? "fd4" : f > 1 ? "fd" : f === 0 ? "fa0" : f < 1 ? "fa05" : "f1";
  const rows = (pairs, factors, cls) => factors.map((f) => { const ts = pairs.filter(([, x]) => x === f).map(([t]) => t);
    return ts.length ? erow(`<span class="f ${cls(f)}">×${fl(f)}</span>`, ts.map(tchip).join("")) : ""; }).join("");
  const off = all.map((t) => [t, best(t)]), def = all.map((t) => [t, d[t] ?? 1]);
  const offBody = rows(off, [4, 2.5, 2, 0.5, 0.4, 0.25, 0], acls);
  const weak = rows(def, [4, 2.5, 2], fcls), tough = rows(def, [0.5, 0.4, 0.25, 0], fcls);
  const ideal = all.filter((t) => best(t) > 1 && (ch[t] ? effMul(own.map((x) => ch[t][x] ?? 1)) : 1) <= 0.5);
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
  const dcls = (f) => f > 2 ? "fd4" : f > 1 ? "fd" : f < 1 ? "f2" : "f1";
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
  const t = e.target.closest("[data-tip],[data-tip-type],[data-tip-cell],[data-tip-stats],[data-tip-calc],[data-tip-speed]");
  if (t) {
    clearTimeout(tipTimer);
    tipTimer = setTimeout(() => {
      if (t.dataset.tipType) tip.innerHTML = typeTipHtml(t.dataset.tipType);
      else if (t.dataset.tipCell) tip.innerHTML = cellTip(...t.dataset.tipCell.split(":"));
      else if (t.dataset.tipStats) tip.innerHTML = radarTipHtml(t.dataset.tipStats.split(",").map(Number));
      else if (t.dataset.tipCalc) tip.innerHTML = TIPM.get(+t.dataset.tipCalc) || "";
      else if (t.dataset.tipSpeed) tip.innerHTML = speedListTip(...t.dataset.tipSpeed.split(":").map(Number));
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
  const t = e.target.closest("[data-tip],[data-tip-type],[data-tip-cell],[data-tip-stats],[data-tip-calc],[data-tip-speed]");
  if (t && !t.contains(e.relatedTarget)) { clearTimeout(tipTimer); tip.hidden = true; }
  const c = e.target.closest(".mon,[data-hc]");
  if (c && !c.contains(e.relatedTarget)) { clearTimeout(cardTimer); card.hidden = true; }
});
document.addEventListener("scroll", () => { tip.hidden = true; card.hidden = true; }, {passive: true});
const HCLOAD = new Set();
function showCard(el) {
  if (!el.isConnected || !el.matches(":hover")) return;
  const inTeam = el.closest("#dock,#slots") && el.dataset.slot !== undefined;
  const slot = inTeam ? +el.dataset.slot : null;
  const hid = el.dataset.hc || el.dataset.id, r = ROWS[hid];
  if (!r || !r.werte) {               // noch nicht geladen (etwa gemerkt, aus dem Kampftagebuch): einmal nachladen
    if (hid && !isNaN(+hid) && !HCLOAD.has(hid)) {
      HCLOAD.add(hid);
      api(`/api/pokemon/${hid}?` + qs({spiel: S.game})).then((x) => { ROWS[hid] = Object.assign(ROWS[hid] || {}, x); showCard(el); }).catch(teil("Einzelheiten zur Vorschau"));
    }
    return;
  }
  const d = defense(r.typen);
  const det = slot !== null ? S.team.details[slot] || {} : null;
  const mv = det ? (det.attacken || []).map((x) => MOVES[x]).filter(Boolean) : [];
  card.innerHTML = `<div class="hc-head">${img(r.id, "art", true)}<div><b>${esc(r.name)}</b> <span class="muted">#${r.dexk || ""}${r.nr ?? r.art}</span><div>${tchips(r.typen)}</div>
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
const PIN_COL = `<svg viewBox="0 0 12 12" aria-hidden="true"><rect x="0.5" y="0.5" width="11" height="11" rx="2" fill="none" stroke="currentColor"/><rect x="4.5" y="0.5" width="3" height="11" fill="currentColor"/></svg>`;
const PIN_ROW = `<svg viewBox="0 0 12 12" aria-hidden="true"><rect x="0.5" y="0.5" width="11" height="11" rx="2" fill="none" stroke="currentColor"/><rect x="0.5" y="4.5" width="11" height="3" fill="currentColor"/></svg>`;
function crossTable(table, pin, onChange, marks = true) {
  table.classList.add("cross");
  if (!marks) table.dataset.rowpin = "0";       // ohne Markierungszeichen (Typtabellen): Klick auf Kopf oder Zelle genügt
  // Sortierbare Spaltenköpfe: der Klick auf den Namen sortiert, das kleine Zeichen daneben hält die Spalte fest
  const hdr = table.tHead?.rows[table.tHead.rows.length - 1];
  if (hdr && marks) [...hdr.cells].forEach((h, i) => {
    if (h.dataset.pc || !$(`td[data-c="${i}"]`, table)) return;   // auch nicht sortierbare Spalten (z. B. Beschreibung)
    h.dataset.c = i;
    h.insertAdjacentHTML("afterbegin", `<span class="pinc" data-pc="${i}" data-tip="Spalte markieren${h.dataset.sort === undefined ? "" : " (Klick auf den Titel sortiert)"}">${PIN_COL}</span>`);
  });
  if (marks) $$("th[data-pc]", table).forEach((h) => { if (!$(":scope > .pinc", h)) h.insertAdjacentHTML("afterbegin", `<span class="pinc" data-pc="${h.dataset.pc}" data-tip="Spalte markieren">${PIN_COL}</span>`); });
  // Zeilenköpfe markieren schon per Klick; das Zeichen nur, wo die Tabelle es will (data-rowpin="0": ohne)
  if (table.dataset.rowpin !== "0") $$("th[data-pr]", table).forEach((h) => { if (!$(":scope > .pinc", h)) h.insertAdjacentHTML("afterbegin", `<span class="pinc" data-pr="${h.dataset.pr}" data-tip="Zeile markieren">${PIN_ROW}</span>`); });
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
  const cellOf = (e) => e.target.closest("td[data-c],[data-pc],[data-pr],tr[data-r]>td");
  table.addEventListener("mouseover", (e) => {
    const cell = cellOf(e);
    if (!cell) return paint(null, null);
    const row = cell.closest("tr")?.dataset.r ?? null;
    paint(cell.dataset.pc ? null : row, cell.dataset.pr || cell.classList.contains("nohc") ? null : cell.dataset.c ?? null);
  });
  table.addEventListener("mouseleave", () => paint(null, null));
  table.addEventListener("click", (e) => {
    const cell = cellOf(e);
    if (!cell || e.target.closest("a,button")) return;
    if (cell.classList.contains("pinc")) e.stopPropagation();       // nicht sortieren
    if (cell.dataset.pr) pin.r = pin.r === cell.dataset.pr ? null : cell.dataset.pr;
    else if (cell.dataset.pc) pin.c = pin.c === cell.dataset.pc ? null : cell.dataset.pc;
    else {
      const row = cell.closest("tr").dataset.r, c = cell.classList.contains("nohc") ? null : cell.dataset.c ?? null;
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
const MVCOLS = `<colgroup><col style="width:20%"><col style="width:86px"><col style="width:92px"><col style="width:76px"><col style="width:66px"><col style="width:82px"><col style="width:160px"><col><col style="width:44px"></colgroup>`;
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

