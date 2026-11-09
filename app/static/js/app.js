/* Pokédex-Oberfläche: Vanilla JS ohne Build. Reiter über die Adresse (#pokemon, #pokemon/6, #team, #attacken,
   #typen, #einstellungen); das gewählte Spiel und das aktuelle Team merkt sich der Browser. */
"use strict";
const $ = (s, el = document) => el.querySelector(s);
const main = $("#main");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem("px." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("px." + k, JSON.stringify(v)); } catch (e) { /* privates Fenster */ } },
};
const S = {meta: null, game: store.get("game", "legends-arceus"), types: {}, team: store.get("team", {ids: [], fest: []}),
  weights: store.get("weights", null), preset: store.get("preset", "ausgewogen"), filter: store.get("filter", {formen: "relevant", sort: "nr"}), tleg: store.get("tleg", true)};
const TABS = [["pokemon", "Pokémon"], ["team", "Team"], ["attacken", "Attacken"], ["typen", "Typen"], ["einstellungen", "Einstellungen"]];
const STAT = ["KP", "Angriff", "Verteidigung", "Sp.-Angriff", "Sp.-Vert.", "Initiative"];
const CRIT = {defensive: "Defensive", abdeckung: "Abdeckung", tempo: "Tempo", staerke: "Stärke", balance: "Balance"};
const PRESETS = {
  ausgewogen: {defensive: 3, abdeckung: 3, tempo: 1, staerke: 2, balance: 1},
  verteidigung: {defensive: 6, abdeckung: 1, tempo: 1, staerke: 1, balance: 1},
  angriff: {defensive: 1, abdeckung: 6, tempo: 2, staerke: 1, balance: 1},
  staerke: {defensive: 1, abdeckung: 1, tempo: 1, staerke: 6, balance: 0},
  tempo: {defensive: 1, abdeckung: 2, tempo: 6, staerke: 1, balance: 0},
};
const PRESET_DE = {ausgewogen: "Ausgewogen", verteidigung: "Verteidigung", angriff: "Angriff", staerke: "Rohe Stärke", tempo: "Tempo"};
const CLS = {1: "Status", 2: "Physisch", 3: "Speziell"};

async function api(path, body) {
  const opt = body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  const r = await fetch(path, opt);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== "" && v !== null && v !== undefined && v !== false)).toString();
const weights = () => S.weights || PRESETS[S.preset] || PRESETS.ausgewogen;

/* ------------------------------------------------------------------ Bausteine */
const tchip = (t) => `<span class="t t${t}">${esc(S.types[t] || t)}</span>`;
const tchips = (ts) => (ts || []).map(tchip).join("");
const spr = (id, cls = "") => `<img class="spr ${cls}" src="sprites/${id}.png" alt="" loading="lazy" onerror="this.outerHTML='<span class=&quot;spr none ${cls}&quot;></span>'">`;
const fl = (f) => ({0: "0", 0.25: "¼", 0.5: "½", 1: "1", 2: "2", 4: "4"}[f] ?? String(f));
const fcls = (f) => f === 0 ? "f0" : f >= 4 ? "f4" : f > 1 ? "f2" : f <= 0.25 ? "f025" : f < 1 ? "f05" : "f1";
const statColor = (v) => `hsl(${Math.min(v, 160) * 0.9} 60% 45%)`;
const gameName = () => (S.meta?.spiele || []).find((g) => g.kennung === S.game)?.name || "alle Spiele";

function monCard(r, extra = "") {
  return `<button class="mon" data-go="pokemon/${r.id}">${spr(r.id)}<span class="grow"><span class="n">${esc(r.name)}</span>
    <span class="s"> #${r.nr ?? r.art}</span><br>${tchips(r.typen)}<br><span class="s">Basiswerte ${r.summe}${r.legendaer ? " · legendär" : ""}</span>${extra}</span></button>`;
}

/* ------------------------------------------------------------------ Kopf, Reiter, Adresse */
function header() {
  const sel = $("#game");
  const gs = S.meta?.spiele || [];
  sel.innerHTML = `<option value="">Alle Spiele (neueste Werte)</option>` +
    gs.map((g) => `<option value="${esc(g.kennung)}"${g.kennung === S.game ? " selected" : ""}>${esc(g.name)} · Gen ${g.gen}</option>`).join("");
  if (S.game && !gs.some((g) => g.kennung === S.game)) sel.value = "";
  const a = S.meta?.abgleich || {};
  $("#meta").textContent = !S.meta?.has_data ? (a.running ? "Erster Abgleich läuft …" : "Noch keine Daten")
    : `${S.meta.formen} Pokémon und Formen · ${S.meta.attacken} Attacken` + (a.running ? " · Abgleich läuft" : "");
  const th = document.documentElement.dataset.theme;
  $("#thm").textContent = th === "dark" ? "Dunkel" : th === "light" ? "Hell" : "Ansicht: Gerät";
}
function nav(tab) {
  $("#nav").innerHTML = TABS.map(([k, n]) => `<button data-go="${k}" class="${k === tab ? "on" : ""}">${n}</button>`).join("");
}
let RID = 0;                // jede neue Adresse zählt hoch; ältere Antworten schreiben dann nichts mehr
async function route() {
  RID++;
  const [tab, arg] = (location.hash.slice(1) || "pokemon").split("/");
  nav(tab);
  try {
    if (!S.meta?.has_data && tab !== "einstellungen") return noData();
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
}
function noData() {
  const a = S.meta?.abgleich || {};
  main.innerHTML = `<div class="box"><h2>Noch keine Spieldaten</h2>
    <p>${a.running ? "Der erste Abgleich läuft gerade (PokéAPI und Showdown, einige Minuten). Die Seite lädt neu, sobald er fertig ist."
      : "Der Abgleich holt die Daten von der PokéAPI und von Pokémon Showdown."}</p>
    <button class="primary" data-act="sync"${a.running ? " disabled" : ""}>Abgleich starten</button>
    <button data-go="einstellungen">Protokoll ansehen</button></div>`;
  if (a.running) setTimeout(refreshMeta, 5000);
}
async function refreshMeta() {
  S.meta = await api("/api/meta");
  S.types = Object.fromEntries((S.meta.typen || []).map((t) => [t.id, t.name]));
  header();
  if (S.meta.has_data || !S.meta.abgleich?.running) route(); else setTimeout(refreshMeta, 5000);
}

/* ------------------------------------------------------------------ Pokémon-Liste */
let listState = {offset: 0, rows: [], n: 0};
function typeOptions(v, empty) {
  return `<option value="">${empty}</option>` + Object.entries(S.types).map(([id, n]) => `<option value="${id}"${+v === +id ? " selected" : ""}>${esc(n)}</option>`).join("");
}
async function listView() {
  const f = S.filter;
  main.innerHTML = `<div class="bar">
      <input class="grow" id="q" type="search" placeholder="Name oder Nummer" value="${esc(f.q || "")}">
      <select id="typ">${typeOptions(f.typ, "Typ")}</select><select id="typ2">${typeOptions(f.typ2, "2. Typ")}</select>
      <select id="formen"><option value="relevant">Formen mit eigenen Werten</option><option value="standard">nur Standardform</option><option value="alle">alle Formen</option></select>
      <select id="sort"><option value="nr">Nummer</option><option value="name">Name</option><option value="summe">Basiswerte</option>
        <option value="ang">Angriff</option><option value="spang">Sp.-Angriff</option><option value="init">Initiative</option><option value="kp">KP</option><option value="vert">Verteidigung</option></select>
    </div><div class="bar">
      <label><input type="checkbox" id="endstufe"${f.endstufe ? " checked" : ""}> nur Endstufen</label>
      <label><input type="checkbox" id="ohne_leg"${f.ohne_leg ? " checked" : ""}> ohne Legendäre</label>
      <label><input type="checkbox" id="kampf"${f.kampf ? " checked" : ""}> mit Mega und Gigadynamax</label>
      <label>bis Gen <select id="gen"><option value="">alle</option>${[1, 2, 3, 4, 5, 6, 7, 8, 9].map((g) => `<option${+f.gen === g ? " selected" : ""}>${g}</option>`).join("")}</select></label>
      <label>Basiswerte ab <input id="min" type="number" min="0" max="800" step="10" style="width:80px" value="${esc(f.min || "")}"></label>
      <span class="hint grow" id="cnt"></span>
    </div><div class="list" id="list"></div><div class="more" id="more"></div>`;
  $("#formen").value = f.formen || "relevant";
  $("#sort").value = f.sort || "nr";
  let timer;
  main.querySelectorAll("input,select").forEach((el) => el.addEventListener(el.type === "search" || el.type === "number" ? "input" : "change", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      S.filter = {q: $("#q").value, typ: $("#typ").value, typ2: $("#typ2").value, formen: $("#formen").value, sort: $("#sort").value,
        endstufe: $("#endstufe").checked, ohne_leg: $("#ohne_leg").checked, kampf: $("#kampf").checked, gen: $("#gen").value, min: $("#min").value};
      store.set("filter", S.filter);
      loadList(true);
    }, 200);
  }));
  await loadList(true);
}
async function loadList(reset) {
  if (reset) listState = {offset: 0, rows: [], n: 0};
  const rid = RID;
  const d = await api("/api/pokemon?" + qs({...S.filter, spiel: S.game, limit: 90, offset: listState.offset}));
  if (rid !== RID || !$("#list")) return;
  listState.rows.push(...d.rows);
  listState.n = d.n;
  listState.offset += d.rows.length;
  $("#list").innerHTML = listState.rows.map((r) => monCard(r)).join("") || `<p class="hint">Nichts gefunden.</p>`;
  $("#cnt").textContent = `${d.n} Treffer in ${gameName()}`;
  $("#more").innerHTML = listState.offset < d.n ? `<button data-act="more">Weitere ${Math.min(90, d.n - listState.offset)} zeigen</button>` : "";
}

/* ------------------------------------------------------------------ Detailseite */
async function detailView(id, level) {
  main.innerHTML = `<p class="hint">Lädt …</p>`;
  const rid = RID;
  const d = await api(`/api/pokemon/${id}?` + qs({spiel: S.game, level}));
  if (rid !== RID) return;
  const inTeam = S.team.ids.includes(d.id);
  const stats = d.werte.map((v, i) => `<span>${STAT[i]}</span><span class="num">${v}</span><span class="sbar"><i style="width:${Math.min(100, v / 2.2)}%;background:${statColor(v)}"></i></span>`).join("");
  const eff = Object.entries(d.wirkung).sort((a, b) => b[1] - a[1] || a[0] - b[0]);
  const effHtml = (pred, title) => {
    const xs = eff.filter(([, f]) => pred(f));
    return xs.length ? `<h3>${title}</h3><div class="eff">${xs.map(([t, f]) => `<div>${tchip(t)}<span class="f ${fcls(f)}">×${fl(f)}</span></div>`).join("")}</div>` : "";
  };
  const evo = d.entwicklung.length > 1 ? d.entwicklung.map((e, i) => (i && e.von ? `<span class="ar">→ ${esc(e.bedingungen.join(" oder ") || "")}</span>` : "") +
    `<button class="st link" data-go="pokemon/${e.id}" style="text-decoration:none">${spr(e.id)}${esc(e.name)}</button>`).join("") : "";
  const A = d.attacken;
  const mrow = (m) => `<tr class="${m.jetzt ? "" : "off"}"><td>${esc(m.name)}${m.geaendert ? ' <span class="cls" title="Werte in diesem Spiel anders als heute">Spielwert</span>' : ""}</td>
    <td>${tchip(m.typ)}</td><td><span class="cls">${CLS[m.klasse] || ""}</span></td><td class="num">${m.staerke ?? "–"}</td><td class="num">${m.genauigkeit ?? "–"}</td>
    <td class="num"><b>${m.wertung}</b></td><td>${esc(m.wege.join(", "))}</td><td class="why">${esc(m.gruende.join(" · "))}</td></tr>`;
  main.innerHTML = `
    <div class="bar"><button data-go="pokemon">← Liste</button>
      <button class="${inTeam ? "" : "primary"}" data-act="${inTeam ? "teamdel" : "teamadd"}" data-id="${d.id}">${inTeam ? "Aus dem Team nehmen" : "Ins Team"}</button>
      <a href="${esc(d.wiki)}" target="_blank" rel="noopener noreferrer">Im PokéWiki öffnen</a>
      ${d.formen.length ? `<span class="hint">Formen:</span>` + d.formen.map((f) => `<button class="small" data-go="pokemon/${f.id}">${esc(f.name)}</button>`).join("") : ""}</div>
    ${!d.im_spiel && S.game ? `<div class="note warn">In ${esc(gameName())} nicht enthalten.</div>` : ""}
    <div class="cols">
      <div class="box"><div class="head">${spr(d.id, "big")}<div><h2>${esc(d.name)}</h2><div class="muted">#${d.nr ?? d.art} · ${esc(d.kategorie)}</div>
        <div style="margin-top:4px">${tchips(d.typen)}</div></div></div>
        <p>${esc(d.text)}</p><div class="stats">${stats}<span><b>Summe</b></span><span class="num"><b>${d.summe}</b></span><span></span></div>
        ${d.faehigkeiten.length ? `<h3>Fähigkeiten</h3>` + d.faehigkeiten.map((a) => `<div><b>${esc(a.name)}</b>${a.versteckt ? " <span class='cls'>versteckt</span>" : ""}${a.wirkt ? " <span class='cls'>ändert Typwirkung</span>" : ""}<div class="why">${esc(a.text)}</div></div>`).join("")
          : S.game === "legends-arceus" ? `<p class="hint">In Legenden: Arceus gibt es keine Fähigkeiten.</p>` : ""}
      </div>
      <div class="box"><h2>Typwirkung gegen ${esc(d.name)}</h2>
        ${d.faehigkeit_wirkt ? `<p class="hint">Mit Fähigkeit eingerechnet.</p>` : ""}
        ${effHtml((f) => f > 1, "Schwach gegen")}${effHtml((f) => f > 0 && f < 1, "Resistent gegen")}${effHtml((f) => f === 0, "Immun gegen")}
        ${evo ? `<h3>Entwicklung</h3><div class="evo">${evo}</div>` : ""}
      </div>
    </div>
    <div class="box" style="margin-top:12px"><h2>Fundorte in ${esc(gameName())}</h2>
      ${d.fundorte.length ? `<div class="scroll"><table><tr><th>Ort</th><th>Methode</th><th>Level</th><th>Bedingungen</th><th>Edition</th></tr>
        ${d.fundorte.map((e) => `<tr><td>${esc(e.ort)}</td><td>${esc(e.methode)}</td><td>${esc(e.level)}</td><td>${esc(e.bedingungen.join(", "))}</td><td>${esc(e.editionen.join(", "))}</td></tr>`).join("")}</table></div>`
        : `<p class="hint">${S.game ? "Die PokéAPI kennt hier keine Fundorte" + (["legends-arceus", "scarlet-violet", "legends-za"].includes(S.game) ? " (für dieses Spiel liefert sie keine; kommt mit dem PokéWiki-Abruf)" : "") + "." : "Wähle oben ein Spiel."}</p>`}
    </div>
    <div class="box"><h2>Attacken${A.spiel_name ? " in " + esc(A.spiel_name) : ""}</h2>
      ${A.hinweis ? `<div class="note info">${esc(A.hinweis)}</div>` : ""}
      <div class="bar"><label>Bis Level <input id="lvl" type="number" min="1" max="100" style="width:70px" value="${esc(level || "")}"></label>
        <span class="hint">Leer: alle erlernbaren. Mit Level zählen nur Attacken, die bis dahin gehen.</span></div>
      ${A.moveset.length ? `<h3>Vorschlag: vier Attacken</h3><div class="chips">${A.moveset.map((m) => `<span class="chip">${tchip(m.typ)} <span class="pick">${esc(m.name)}</span> <span class="why">${esc(m.grund)}</span></span>`).join("")}</div>` : ""}
      <h3>Schadens-Attacken nach Wertung</h3>
      <p class="hint">Wertung = Stärke × Genauigkeit × Eigentyp-Bonus × passender Angriffswert, mit Zu- und Abschlägen (Aussetzen, Anlauf, Rückstoß, Werte senken, Vorrang).</p>
      <div class="scroll"><table><tr><th>Attacke</th><th>Typ</th><th>Klasse</th><th>Stärke</th><th>Gen.</th><th>Wertung</th><th>Weg</th><th>Gründe</th></tr>
        ${A.attacken.map(mrow).join("") || `<tr><td colspan="8" class="hint">Keine Lernliste.</td></tr>`}</table></div>
      ${A.status.length ? `<details><summary>Status-Attacken (${A.status.length})</summary><div class="chips" style="margin-top:6px">${A.status.map((m) => `<span class="chip" title="${esc(m.text || "")}">${tchip(m.typ)} ${esc(m.name)} <span class="why">${esc(m.wege.join(", "))}</span></span>`).join("")}</div></details>` : ""}
    </div>`;
  $("#lvl").addEventListener("change", (e) => detailView(id, e.target.value));
  window.scrollTo(0, 0);
}

/* ------------------------------------------------------------------ Team */
function saveTeam() { store.set("team", S.team); }
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
      menu.innerHTML = rows.map((r, i) => `<button data-i="${i}">${spr(r.id)}${esc(r.name)} ${tchips(r.typen)}</button>`).join("") || `<div class="hint" style="padding:6px">Nichts gefunden</div>`;
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
async function teamView() {
  const rid = RID;
  const saved = await api("/api/teams");
  if (rid !== RID) return;
  const w = weights();
  main.innerHTML = `
    <div class="bar"><div class="ac grow"><input id="add" type="search" placeholder="Pokémon hinzufügen: Name oder Nummer" style="width:100%"></div>
      <select id="saved"><option value="">Gespeicherte Teams (${saved.length})</option>${saved.map((t) => `<option value="${t.id}"${t.id === S.team.tid ? " selected" : ""}>${esc(t.name)}</option>`).join("")}</select>
      <button data-act="tsave">Speichern</button>${S.team.tid ? `<button data-act="tdel">Löschen</button>` : ""}<button data-act="tclear">Leeren</button></div>
    <div class="slots" id="slots"></div>
    <div class="cols" style="margin-top:12px">
      <div class="box"><h2>Bewertung</h2><div id="ev"><p class="hint">Füge Pokémon hinzu.</p></div></div>
      <div class="box"><h2>Ziel</h2>
        <div class="bar"><select id="preset">${Object.entries(PRESET_DE).map(([k, n]) => `<option value="${k}"${k === S.preset && !S.weights ? " selected" : ""}>${n}</option>`).join("")}
          <option value=""${S.weights ? " selected" : ""}>Eigene Gewichte</option></select></div>
        <div class="weights">${Object.entries(CRIT).map(([k, n]) => `<span>${n}</span><input type="range" min="0" max="10" step="1" data-w="${k}" value="${w[k]}"><span class="num">${w[k]}</span>`).join("")}</div>
        <p class="hint">Defensive: wenige offene Schwächen. Abdeckung: viele Typen sehr effektiv getroffen. Tempo: Initiative ab 90. Stärke: Basiswerte. Balance: physisch und speziell gemischt, keine doppelten Typen.</p>
        <div class="bar"><label><input type="checkbox" id="tleg"${S.tleg ? " checked" : ""}> ohne Legendäre und Mysteriöse</label></div>
        <div class="bar"><button class="primary" data-act="opt">Bestes Team suchen</button><span class="hint">Festgesetzte (📌) bleiben, der Rest wird gefüllt.</span></div>
        <div id="opt"></div>
      </div>
    </div>
    <div class="cols" style="margin-top:12px">
      <div class="box"><h2>Vorschläge für den nächsten Platz</h2><div id="sug"><p class="hint">Mit mindestens einem Mitglied.</p></div></div>
      <div class="box"><h2>Gegen einen Gegner</h2><div class="bar"><div class="ac grow"><input id="foe" type="search" placeholder="Gegner: Name" style="width:100%"></div></div>
        <div id="mu"><p class="hint">Wähle einen Gegner: das Tool sagt, wen du schickst und wen du schonst.</p></div></div>
    </div>`;
  autocomplete($("#add"), (r) => {
    if (S.team.ids.length >= 6) return alert("Das Team ist voll (6).");
    if (!S.team.ids.includes(r.id)) S.team.ids.push(r.id);
    saveTeam(); teamRefresh();
  });
  autocomplete($("#foe"), (r) => matchup(r));
  $("#tleg").addEventListener("change", (e) => { S.tleg = e.target.checked; store.set("tleg", S.tleg); teamRefresh(); });
  $("#saved").addEventListener("change", (e) => {
    const t = saved.find((x) => x.id === +e.target.value);
    if (!t) return;
    S.team = {ids: t.mitglieder, fest: t.fest, tid: t.id, name: t.name};
    if (Object.keys(t.gewichte || {}).length) { S.weights = t.gewichte; store.set("weights", S.weights); }
    saveTeam(); teamView();
  });
  $("#preset").addEventListener("change", (e) => {
    if (e.target.value) { S.preset = e.target.value; S.weights = null; store.set("preset", S.preset); store.set("weights", null); }
    else S.weights = {...weights()};
    teamView();
  });
  main.querySelectorAll("[data-w]").forEach((el) => el.addEventListener("change", () => {
    S.weights = {...weights(), [el.dataset.w]: +el.value};
    store.set("weights", S.weights);
    el.nextElementSibling.textContent = el.value;
    $("#preset").value = "";
    teamRefresh();
  }));
  await teamRefresh();
}
async function teamRefresh() {
  const t = S.team;
  const ev = await api("/api/team/bewerten", {spiel: S.game, ids: t.ids, gewichte: weights()});
  if (!$("#slots")) return;
  const byId = Object.fromEntries((ev.mitglieder || []).map((m) => [m.id, m]));
  $("#slots").innerHTML = [0, 1, 2, 3, 4, 5].map((i) => {
    const id = t.ids[i], m = byId[id];
    if (!m) return `<div class="slot empty">Platz ${i + 1}</div>`;
    const fixed = t.fest.includes(id);
    return `<div class="slot${fixed ? " fixed" : ""}"><button class="small pin${fixed ? " on" : ""}" data-act="pin" data-id="${id}" title="Für die Teamsuche festsetzen">📌</button>
      <button class="small x" data-act="teamdel" data-id="${id}" title="Entfernen">✕</button>
      <button class="link" data-go="pokemon/${id}" style="text-decoration:none">${spr(id)}<br><b>${esc(m.name)}</b></button><br>${tchips(m.typen)}<div class="hint">Basiswerte ${m.summe}</div></div>`;
  }).join("");
  if (!t.ids.length) { $("#ev").innerHTML = `<p class="hint">Füge Pokémon hinzu.</p>`; $("#sug").innerHTML = ""; return; }
  const ms = ev.mitglieder;
  $("#ev").innerHTML = `<div class="score">${ev.wertung}<span class="hint"> / 100</span></div>
    <div class="crit">${Object.entries(CRIT).map(([k, n]) => `<span>${n}</span><span class="sbar"><i style="width:${ev.kriterien[k] * 100}%"></i></span><span class="num">${Math.round(ev.kriterien[k] * 100)}</span>`).join("")}</div>
    ${ev.offen.length ? `<div class="note stop">Offene Schwächen (mehr Mitglieder schwach als resistent): ${tchips(ev.offen)}</div>` : `<div class="note go">Keine offene Schwäche.</div>`}
    ${ev.vierfach.length ? `<div class="note warn">4-fach-Schwächen: ${ev.vierfach.map(([a, n]) => `${esc(n)} gegen ${tchip(a)}`).join(", ")}</div>` : ""}
    ${ev.nicht_abgedeckt.length ? `<p class="hint">Nicht sehr effektiv getroffen (mit Eigentypen): ${tchips(ev.nicht_abgedeckt)}</p>` : ""}
    <p class="hint">${ev.physisch} physisch, ${ev.speziell} speziell · schnell: ${esc(ev.schnell.join(", ") || "keiner")}</p>
    <details><summary>Typwirkung je Mitglied</summary><div class="scroll"><table class="matrix"><tr><th></th>${ms.map((m) => `<th>${spr(m.id)}</th>`).join("")}</tr>
      ${Object.keys(S.types).filter((a) => ev.matrix[ms[0].id]?.[a] !== undefined).map((a) => `<tr><th class="r">${tchip(a)}</th>${ms.map((m) => { const f = ev.matrix[m.id][a]; return `<td><span class="f ${fcls(f)}">${f === 1 ? "" : fl(f)}</span></td>`; }).join("")}</tr>`).join("")}</table></div></details>`;
  if (t.ids.length < 6) {
    $("#sug").innerHTML = `<p class="hint">Rechnet …</p>`;
    const s = await api("/api/team/vorschlag", {spiel: S.game, ids: t.ids, gewichte: weights(), filter: {ohne_leg: S.tleg ? 1 : ""}});
    if (!$("#sug")) return;
    $("#sug").innerHTML = s.rows.map((r) => `<div class="bar" style="margin:0 0 6px"><span class="grow">${monCard(r, `<div class="why">+${r.plus} · ${esc(r.gruende.join(" · "))}</div>`)}</span>
      <button class="small" data-act="teamadd" data-id="${r.id}">+ Ins Team</button></div>`).join("") || `<p class="hint">Keine Vorschläge.</p>`;
  } else $("#sug").innerHTML = `<p class="hint">Das Team ist voll.</p>`;
}
async function optimize() {
  $("#opt").innerHTML = `<p class="hint">Sucht … (einige Sekunden)</p>`;
  const r = await api("/api/team/optimieren", {spiel: S.game, fest: S.team.fest, gewichte: weights(), filter: {ohne_leg: S.tleg ? 1 : "", endstufe: 1}});
  $("#opt").innerHTML = `<p class="hint">Aus ${r.pool} Endstufen${S.tleg ? " ohne Legendäre" : ""} in ${esc(gameName())}.</p>` + r.teams.map((t, i) => `<div class="box">
    <div class="bar"><b>${t.wertung}</b><span class="grow">${t.mitglieder.map((m) => `<button class="link" data-go="pokemon/${m.id}" title="${esc(m.name)}">${spr(m.id)}</button>`).join("")}</span>
    <button class="small" data-act="take" data-i="${i}">Übernehmen</button></div>
    <div class="why">${t.mitglieder.map((m) => esc(m.name)).join(", ")}${t.offen.length ? " · offen: " + t.offen.map((x) => S.types[x]).join(", ") : ""}</div></div>`).join("");
  S.lastOpt = r.teams;
}
async function matchup(foe) {
  if (!S.team.ids.length) return ($("#mu").innerHTML = `<p class="hint">Erst ein Team zusammenstellen.</p>`);
  const r = await api("/api/team/gegner", {spiel: S.game, ids: S.team.ids, gegner: foe.id});
  $("#mu").innerHTML = `<div class="bar">${spr(foe.id)}<b>${esc(foe.name)}</b> ${tchips(r.gegner.typen)}</div><table>
    ${r.rows.map((x) => `<tr><td>${spr(x.id)}</td><td><b>${esc(x.name)}</b><div class="why">${esc(x.gruende.join(" · "))}</div></td><td class="v-${x.urteil}">${x.urteil}</td></tr>`).join("")}</table>
    <p class="hint">Nach Typen und Initiative; Attacken des Gegners zählen über seine Typen.</p>`;
}

/* ------------------------------------------------------------------ Attacken je Typ */
async function movesView() {
  const f = store.get("mfilter", {typ: "", klasse: ""});
  main.innerHTML = `<div class="bar"><select id="mtyp">${typeOptions(f.typ, "Alle Typen")}</select>
    <select id="mkl"><option value="">Physisch und speziell</option><option value="2"${f.klasse === "2" ? " selected" : ""}>Physisch</option><option value="3"${f.klasse === "3" ? " selected" : ""}>Speziell</option></select>
    <span class="hint grow">Beste Attacken in ${esc(gameName())}: Stärke × Genauigkeit mit Zu- und Abschlägen, ohne Eigentyp-Bonus.</span></div><div id="mv"></div>`;
  const load = async () => {
    const nf = {typ: $("#mtyp").value, klasse: $("#mkl").value};
    store.set("mfilter", nf);
    const d = await api("/api/attacken?" + qs({...nf, spiel: S.game, limit: 60}));
    if (!$("#mv")) return;
    $("#mv").innerHTML = `<div class="box scroll"><table><tr><th>Attacke</th><th>Typ</th><th>Klasse</th><th>Stärke</th><th>Gen.</th><th>AP</th><th>Wertung</th><th>Gründe</th><th>Beschreibung</th></tr>
      ${d.rows.map((m) => `<tr><td><b>${esc(m.name)}</b>${m.geaendert ? ' <span class="cls">Spielwert</span>' : ""}</td><td>${tchip(m.typ)}</td><td><span class="cls">${CLS[m.klasse]}</span></td>
        <td class="num">${m.staerke}</td><td class="num">${m.genauigkeit ?? "–"}</td><td class="num">${m.ap ?? ""}</td><td class="num"><b>${m.wertung}</b></td>
        <td class="why">${esc(m.gruende.join(" · "))}</td><td class="why">${esc(m.text || "")}</td></tr>`).join("")}</table></div>`;
  };
  $("#mtyp").addEventListener("change", load);
  $("#mkl").addEventListener("change", load);
  await load();
}

/* ------------------------------------------------------------------ Typtabelle */
async function chartView() {
  const rid = RID;
  const d = await api("/api/typen?" + qs({spiel: S.game}));
  if (rid !== RID) return;
  const ts = d.typen;
  main.innerHTML = `<div class="box"><h2>Typtabelle Generation ${d.gen}</h2><p class="hint">Zeile greift an, Spalte verteidigt. Leer heißt ×1.</p>
    <div class="scroll"><table class="chart"><tr><th></th>${ts.map((t) => `<th class="v">${tchip(t.id)}</th>`).join("")}</tr>
    ${ts.map((a) => `<tr><th>${tchip(a.id)}</th>${ts.map((v) => { const f = d.tabelle[a.id][v.id]; return `<td>${f === 1 ? "" : `<span class="f ${fcls(f)}">${fl(f)}</span>`}</td>`; }).join("")}</tr>`).join("")}
    </table></div></div>`;
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
        <button data-act="rebuild"${st.running ? " disabled" : ""} title="Auch ohne Änderung neu bauen">Neu bauen</button></div>
      <table><tr><th>Quelle</th><th>Stand</th><th>Abrufe</th><th>Fehler</th><th>Zeit</th></tr>${srcRow("pokeapi", "PokéAPI")}${srcRow("showdown", "Showdown")}${srcRow("sprites", "Sprites")}</table>
      <h3>Zeitplan</h3>
      <div class="bar"><label><input type="checkbox" id="auto"${s.auto ? " checked" : ""}> automatisch alle</label>
        <input type="number" id="tage" min="1" max="30" value="${s.tage || 7}" style="width:64px"> Tage</div>
      <div class="bar"><label><input type="checkbox" id="sprites"${s.sprites ? " checked" : ""}> Bilder (Sprites) laden</label></div>
      <p class="hint">Ändert sich bei keiner Quelle etwas, bleibt die Datenbank. Eine neue gilt erst nach bestandener Selbstprüfung; deine Teams liegen getrennt (user.db) und werden täglich gesichert.</p>
    </div>
    <div class="box"><h2>Zu erledigen</h2>
      ${open.length ? `<p class="hint">PokéAPI und Showdown sind sich hier nicht einig. Wähle, welcher Wert stimmt; im Zweifel im PokéWiki nachsehen.</p>
        <div class="scroll"><table><tr><th>Was</th><th>Feld</th><th>PokéAPI</th><th>Showdown</th><th></th></tr>
        ${open.slice(0, 80).map((r) => `<tr><td>${esc(r.name)}</td><td>${esc(r.feld)}</td><td>${esc(r.pokeapi)}</td><td>${esc(r.showdown)}</td>
          <td><button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="pokeapi">PokéAPI</button> <button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="showdown">Showdown</button>
          <button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="egal">egal</button></td></tr>`).join("")}</table></div>`
        : `<div class="note go">Nichts offen${pr.length ? ` (${pr.length} Abweichungen entschieden)` : ""}.</div>`}
      ${pr.length - open.length ? `<details><summary>Entschieden (${pr.length - open.length})</summary><table>${pr.filter((r) => r.entscheidung).map((r) => `<tr><td>${esc(r.name)}</td><td>${esc(r.feld)}</td><td>${esc(r.entscheidung)}</td><td><button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="">zurück</button></td></tr>`).join("")}</table></details>` : ""}
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
  const go = e.target.closest("[data-go]");
  if (go) { location.hash = go.dataset.go; return; }
  const b = e.target.closest("[data-act]");
  if (!b) return;
  const act = b.dataset.act, id = +b.dataset.id;
  try {
    if (act === "thm") {
      const cur = document.documentElement.dataset.theme;
      const next = cur === "dark" ? "light" : cur === "light" ? "" : "dark";
      if (next) document.documentElement.dataset.theme = next; else delete document.documentElement.dataset.theme;
      try { if (next) localStorage.setItem("px.theme", next); else localStorage.removeItem("px.theme"); } catch (x) { /* egal */ }
      header();
    } else if (act === "more") await loadList(false);
    else if (act === "teamadd") {
      if (S.team.ids.length >= 6) return alert("Das Team ist voll (6).");
      if (!S.team.ids.includes(id)) S.team.ids.push(id);
      saveTeam();
      location.hash.startsWith("#team") ? teamRefresh() : route();
    } else if (act === "teamdel") {
      S.team.ids = S.team.ids.filter((x) => x !== id);
      S.team.fest = S.team.fest.filter((x) => x !== id);
      saveTeam();
      location.hash.startsWith("#team") ? teamRefresh() : route();
    } else if (act === "pin") {
      S.team.fest = S.team.fest.includes(id) ? S.team.fest.filter((x) => x !== id) : [...S.team.fest, id];
      saveTeam(); teamRefresh();
    } else if (act === "opt") await optimize();
    else if (act === "take") {
      S.team.ids = S.lastOpt[+b.dataset.i].ids;
      saveTeam(); teamRefresh();
    } else if (act === "tclear") { S.team = {ids: [], fest: []}; saveTeam(); teamView(); }
    else if (act === "tsave") {
      const name = prompt("Name des Teams", S.team.name || "Team " + gameName());
      if (!name) return;
      const r = await api("/api/teams", {id: S.team.tid, name, spiel: S.game, mitglieder: S.team.ids, fest: S.team.fest, gewichte: weights()});
      S.team.tid = r.id; S.team.name = name; saveTeam(); teamView();
    } else if (act === "tdel") {
      if (!confirm("Team löschen?")) return;
      await api("/api/teams/loeschen", {id: S.team.tid});
      S.team = {ids: S.team.ids, fest: S.team.fest}; saveTeam(); teamView();
    } else if (act === "sync" || act === "rebuild") {
      await api("/api/abgleich", {neu: act === "rebuild"});
      setTimeout(refreshMeta, 800);
    } else if (act === "diag") await diag();
    else if (act === "dec") {
      await api("/api/entscheidung", {art: "pruefung", schluessel: b.dataset.k, wert: b.dataset.v});
      settingsView();
    }
  } catch (err) { alert(err.message); }
});
$("#game").addEventListener("change", (e) => { S.game = e.target.value; store.set("game", S.game); route(); });
window.addEventListener("hashchange", route);
refreshMeta().catch((e) => { main.innerHTML = `<div class="note stop">Server nicht erreichbar: ${esc(e.message)}</div>`; });
