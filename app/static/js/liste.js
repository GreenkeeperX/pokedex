/* Pokédex-Oberfläche, Teil 3 von 10: Pokémon-Liste und Team-Leiste.
   Die Teile lädt index.html der Reihe nach; sie teilen sich die globalen Namen (docs/oberflaeche.md). */
"use strict";
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
  redrawMarks();      // 0.47.4: auch im Team-Reiter, sonst behalten die Favoriten-Karten alte Haken
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
  } catch (e) { teil("Standard-Attacken")(e); }
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
function fullChoice(id, anchor = document.activeElement?.closest?.(".ac,.bar,.box") || $("#dock"), best = -1) {   // best: empfohlener Platz (0.56.2)
  let el = $("#pick");
  if (!el) { el = document.createElement("div"); el.id = "pick"; document.body.appendChild(el); }
  const r = ROWS[id];
  el.innerHTML = `<div class="hint">${teamFull() ? "Team voll. " : ""}${esc(r?.name || "")} ersetzt …</div>`
    + S.team.ids.map((x, i) => `<button${i === best ? ' class="best"' : ""} data-act="pickfav" data-id="${id}" data-slot="${i}" data-hc="${x}">${img(x)}<span>Platz ${i + 1}: ${esc(ROWS[x]?.name || "#" + x)}</span>${i === best ? "<small>empfohlen</small>" : ""}</button>`).join("")
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
  }).catch((e) => { teamCheck.busy = false; teil("Prüfung des Teams")(e); });
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
/* Favorit ins volle Team tauschen: Auswahl, wen er ersetzt */
function swapPicker(anchor, id) {
  let el = $("#pick");
  if (!el) { el = document.createElement("div"); el.id = "pick"; document.body.appendChild(el); }
  el.innerHTML = `<div class="hint">${esc(ROWS[id]?.name || "")} ersetzt …</div>`
    + S.team.ids.map((x, i) => `<button data-act="pickfav" data-id="${id}" data-slot="${i}" data-hc="${x}">${img(x)}<span>${esc(ROWS[x]?.name || "")}</span>${tchips(ROWS[x]?.typen)}</button>`).join("");
  el.hidden = false;
  place(el, anchor);
}
document.addEventListener("click", (e) => { const p = $("#pick"); if (p && !p.hidden && !p.contains(e.target) && !e.target.closest('[data-act="pick"],[data-act="favswap"],.ac .menu')) p.hidden = true; });
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

