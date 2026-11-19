/* Pokédex-Oberfläche, Teil 2 von 10: Kopf, Reiter, Adresse, Spielwahl, Favoriten, Filter.
   Die Teile lädt index.html der Reihe nach; sie teilen sich die globalen Namen (docs/oberflaeche.md). */
"use strict";
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
  // 0.56: läuft ein Abgleich, fragt die Seite alle 5 Sekunden nach, in jedem Reiter; sonst blieb „Abgleich läuft“ bis zum Neuladen stehen
  if (a.running && !syncT) syncT = setTimeout(syncPoll, 5000);
}
let syncT = 0;
/* 0.58.0: fragt den schlanken Stand ab (/api/stand, wenige hundert Byte) statt der ganzen Grunddaten. Solange der Lauf
   läuft, nur die Kopfzeile; meldet der Server das Ende, gilt das sofort (die Meldung „Abgleich läuft“ verschwindet auch
   dann, wenn das Nachladen der Grunddaten scheitert), danach einmal /api/meta für Zahlen, Spiele und neue Daten */
async function syncPoll() {
  syncT = 0;
  let s;
  try { s = await api("/api/stand"); } catch (x) { s = null; }
  if (!s) { if (!syncT) syncT = setTimeout(syncPoll, 15000); return; }
  if (LOADED_VER && s.version && s.version !== LOADED_VER) { location.reload(); return; }
  if (!S.meta) return;
  const fresh = !S.meta.has_data && s.has_data;
  S.meta.abgleich = s.abgleich;
  if (s.abgleich.running && !fresh) { header(); return; }
  S.meta.has_data = s.has_data;
  header();
  try {
    const m = await api("/api/meta");
    S.meta = m;
    S.types = Object.fromEntries((m.typen || []).map((t) => [t.id, t.name]));
    header();
  } catch (x) { hinweis(`Grunddaten nach dem Abgleich nicht geladen (${x.message}). Die Seite neu laden holt sie.`); }
  if (fresh || !S.meta.has_data) route();
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
    $("#dock")?.classList.toggle("fold", hid || MAPFOLD);
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
  // 0.58.0: die Punkte dieser Version kommen bei Bedarf (/api/neuigkeiten?version=…), nicht mehr mit jeder Abfrage der Grunddaten
  const cur = S.neuCur && S.neuCur[0] === v ? S.neuCur : null;
  box.innerHTML = `<div class="note neu"><b>Neu in Version ${esc(v)}</b>${cur ? `<ul>${cur[2].map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    ${S.neuErr ? `<div class="hint">Die Punkte dieser Version ließen sich nicht laden (${esc(S.neuErr)}).</div>` : ""}
    <button data-act="neu">Alle Versionen</button> <button class="primary" data-act="neuok">Verstanden</button></div>`;
  if (!cur && !S.neuErr && !S.neuLoad) {
    S.neuLoad = true;
    api("/api/neuigkeiten?version=" + encodeURIComponent(v)).then((d) => { S.neuCur = d[0] || [v, "", []]; }, (x) => { S.neuErr = x.message; })
      .finally(() => { S.neuLoad = false; version(); });
  }
}
async function versionsDialog() {
  let all, err = "";
  try { all = S.neuAll || (S.neuAll = await api("/api/neuigkeiten")); } catch (x) { all = []; err = x.message; }
  let d = $("#vdlg");
  if (!d) {
    d = document.createElement("dialog"); d.id = "vdlg"; document.body.append(d);
    // Klick neben den Dialog (auf den abgedunkelten Rand) schließt ihn
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
  }
  d.innerHTML = `<div class="dh"><h2>Was ist neu?</h2><form method="dialog"><button class="x" aria-label="Schließen" title="Schließen">✕</button></form></div><div class="db">`
    + (err ? `<div class="note stop">Die Versionsgeschichte ließ sich nicht laden: ${esc(err)}</div>` : "")
    + all.map(([v, datum, punkte]) =>
      `<h3>Version ${esc(v)} <span class="hint">${esc(datum)}</span></h3><ul>${punkte.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`).join("") + `</div>`;
  d.showModal();
}
function nav(tab) {
  $("#nav").innerHTML = TABS.map(([k, n]) => k === "karte" && BATTLE() ? ["kampf", "Kampf"] : [k, n])
    .flatMap((x) => x[0] === "karte" && RAIDS() ? [x, ["raids", "Raids"]] : x[0] === "karte" && REQ_GAME() ? [x, ["auftraege", "Aufträge"]] : [x])
    .map(([k, n]) => `<a href="#${k}" class="${k === tab ? "on" : ""}">${n}</a>`).join("");
}
// Zweiter Klick auf den offenen Reiter: nach oben
document.addEventListener("click", (e) => {
  const a = e.target.closest("#nav a");
  if (a && a.getAttribute("href") === (location.hash || "#pokemon")) { e.preventDefault(); window.scrollTo({top: 0, behavior: "smooth"}); }
});
/* Einklappbare Boxen: <h2 data-fold="schlüssel"> klappt die Box zu, <div class="fsec"><h3 data-fold> nur den Abschnitt.
   Der Zustand steht im Browser; neue Überschriften bekommen ihn, sobald sie im Bild sind */
const foldBox = (h) => h.closest(".fsec, .box") || h.parentElement;
function applyFolds(root = main) {
  $$("[data-fold]:not([data-fi])", root).forEach((h) => {
    h.dataset.fi = "1";
    if (!h.dataset.tip) h.title = "Klick: ein- oder ausklappen";
    foldBox(h).classList.toggle("zu", !!store.get("zu:" + h.dataset.fold, false));
  });
}
new MutationObserver(() => applyFolds()).observe(main, {childList: true, subtree: true});
document.addEventListener("click", (e) => {
  const h = e.target.closest("[data-fold]");
  if (!h || e.target.closest("a, button, input, select, label")) return;
  const zu = !foldBox(h).classList.contains("zu");
  foldBox(h).classList.toggle("zu", zu);
  store.set("zu:" + h.dataset.fold, zu);
});
let RID = 0;                // jede neue Adresse zählt hoch; ältere Antworten schreiben dann nichts mehr
let HERE = "", FROM = "";   // aktuelle und vorige Adresse, für „Zurück“ auf der Detailseite
let VIEW = "";              // welche Ansicht gerade steht (Reiter, Detailseite, Kartenart)
let busyT = 0;
let ONMAP = false, MAPFOLD = false;   // Karte offen; Team-Leiste dort eingeklappt (bis man sie aufklappt)
async function route() {
  RID++;
  clearNotes();
  clearTimeout(cardTimer); clearTimeout(tipTimer);
  tip.hidden = card.hidden = true;
  if (location.hash !== HERE) { FROM = HERE; HERE = location.hash; }
  const [tab, arg, arg2] = (location.hash.slice(1) || "pokemon").split("/");
  nav(tab);
  // 0.56.2: auf der Karte klappt die Team-Leiste auf ihre Kopfzeile zu; woanders gilt wieder, was vorher galt
  if ((tab === "karte") !== ONMAP) { ONMAP = tab === "karte"; MAPFOLD = ONMAP; $("#dock")?.classList.toggle("fold", MAPFOLD || $("#stick").classList.contains("hid")); }
  const rid = RID;
  if (tab === "karte" && BATTLE()) { location.replace("#kampf"); return; }
  if (tab === "kampf" && !BATTLE()) { location.replace("#karte"); return; }   // Spielwechsel: Kampf gibt es nur im Kampfspiel (Champions)
  if (tab === "raids" && !RAIDS()) { location.replace("#karte"); return; }   // Raids nur mit Tera-Raids (Karmesin/Purpur)
  if (tab === "auftraege" && !REQ_GAME()) { location.replace("#karte"); return; }   // Aufträge nur, wo das Profil welche nennt
  // neue Ansicht: der alte Reiter verschwindet sofort; dieselbe Ansicht mit anderem Inhalt bleibt stehen, oben läuft ein Balken
  const view = tab + (tab === "pokemon" && arg ? "/d" : tab === "karte" ? "/" + (arg === "gebiete" ? "g" : !arg || arg === "mg" ? "mg" : "pla") : "");
  if (view !== VIEW && VIEW) main.innerHTML = `<p class="hint loading">Lädt …</p>`;
  VIEW = view;
  clearTimeout(busyT); busyT = setTimeout(() => { if (rid === RID) document.body.classList.add("busy"); }, 120);
  try {
    if (!S.meta?.has_data && tab !== "einstellungen") return noData();
    await Promise.all([loadChart(), loadFavs(), loadCaught(), REQ_GAME() ? loadReqDone() : null]);
    if (tab === "pokemon" && arg) await detailView(+arg, arg2 === undefined ? null : +arg2);
    else if (tab === "pokemon") await listView();
    else if (tab === "team") await teamView();
    else if (tab === "attacken") await movesView();
    else if (tab === "typen") await chartView();
    else if (tab === "vergleich") await compareView(arg, arg2);
    else if (tab === "initiative") await speedView();
    else if (tab === "kampf") await battleView();
    else if (tab === "raids") await raidsView(arg);
    else if (tab === "auftraege") await requestsView();
    else if (tab === "items") await itemsView();
    else if (tab === "fehlt") await missingView(arg, arg2);
    else if (tab === "fortschritt") await progressView();
    else if (tab === "home") await homeView();
    else if (tab === "jagd") await huntView(arg, arg2);
    else if (tab === "tausch") await tradeView();
    else if (tab === "kette") await chainView(arg, arg2);
    else if (tab === "nuzlocke") await nuzView(arg);
    else if (tab === "sammeln") await collectView();
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
  if (rid === RID) { clearTimeout(busyT); document.body.classList.remove("busy"); }
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
  if (!on) undoToast(`${ROWS[id]?.name || "Pokémon"} ist kein Favorit mehr.`, () => toggleFav(id, true));
}
/* kurze Nachricht unten mit „Rückgängig“ (8 Sekunden); eine neue ersetzt die alte */
let toastT = 0;
function undoToast(text, undo) {
  let el = $("#toast");
  if (!el) { el = document.createElement("div"); el.id = "toast"; el.setAttribute("role", "status"); document.body.appendChild(el); }
  el.innerHTML = `<span>${esc(text)}</span><button class="small" type="button">Rückgängig</button>`;
  el.hidden = false;
  clearTimeout(toastT);
  toastT = setTimeout(() => { el.hidden = true; }, 8000);
  $("button", el).addEventListener("click", () => { el.hidden = true; clearTimeout(toastT); undo(); });
}
async function loadCaught(force = false) {
  if (!force && S.caughtGame === S.game) return;
  const [c, sh, al, lk] = await Promise.all([api("/api/gefangen?" + qs({spiel: S.game})), api("/api/schillernd?" + qs({spiel: S.game})),
    api("/api/alpha?" + qs({spiel: S.game})).catch(teil("Alpha-Pokémon", {ids: [], moeglich: []})),
    api("/api/shinysperre?" + qs({spiel: S.game})).catch(teil("Shiny-Sperren", {tausch: [], nie: [], gen1: false}))]);
  S.caught = new Set(c); S.shiny = new Set(sh); S.alpha = new Set(al.ids); S.alphaOk = new Set(al.moeglich);
  S.shinyLock = new Map([...(lk.tausch || []).map((i) => [i, "tausch"]), ...(lk.nie || []).map((i) => [i, "nie"])]); S.shinyGen1 = !!lk.gen1;
  S.caughtGame = S.game;
}
// 0.51: Shiny-Sperre im Spiel: "nie" (gibt es dort nicht schillernd), "tausch" (nur per Tausch oder Verteilung) oder ""
const shinyLock = (id) => S.shinyLock?.get(id) || (S.shinyGen1 ? "tausch" : "");
// Klick am Pokéball: nicht gefangen → gefangen → schillernd → nicht gefangen; „nie“ überspringt schillernd
async function toggleCaught(id, plain = false) {
  if (isCaught(id) && !isShiny(id) && !plain && !BATTLE() && shinyLock(id) !== "nie") {
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
  S.chartDoppelt = d.doppelt || null;
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
  // 0.58.0: kein eigener Zeitgeber mehr; die Kopfzeile fragt den schlanken Stand ab (syncPoll) und lädt neu, sobald Daten da sind
}
let LOADED_VER = null;     // Version, mit der diese Seite geladen wurde
async function refreshMeta() {
  S.favGame = null; S.caughtGame = null;
  S.meta = await api("/api/meta");
  // 0.48.6: Server inzwischen auf neuer Version (Update im Hintergrund): Seite neu laden, sonst bleiben altes CSS und JS
  if (LOADED_VER && S.meta.version && S.meta.version !== LOADED_VER) { location.reload(); return; }
  LOADED_VER = LOADED_VER || S.meta.version;
  S.types = Object.fromEntries((S.meta.typen || []).map((t) => [t.id, t.name]));
  header();
  route();
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
        ? ". Tageszeit und Wetter: aus den Spawn-Tabellen (PLA-Live-Map), nur für frei auftauchende Pokémon" : ""}.${RAIDS()
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
      ${opts.sort === false ? "" : `<select data-f="sort"><option value="nr" data-tip="Nummer im Pokédex des Spiels; Spiele mit mehreren Dexen der Reihe nach">Nummer</option><option value="nat">Nationale Nummer</option><option value="name">Name</option><option value="summe">Basiswerte</option>
        <option value="ang">Angriff</option><option value="spang">Sp.-Angriff</option><option value="init">Initiative</option><option value="kp">KP</option><option value="vert">Verteidigung</option>${PROFIL().forschung ? `<option value="forschung" data-tip="Wo bis zum Forschungslevel 10 noch die meisten Punkte offen sind (abgehakte Stufen zählen nicht)">Offene Forschung</option>` : ""}</select>`}
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
      <span class="hint grow" data-cnt="${id}"></span>${id === "lf" ? `<a class="btn small" href="#jagd" data-tip="Zähler für Shiny-Jagden mit Quote je Methode">Shiny-Jagd</a><a class="btn small" href="#nuzlocke" data-tip="Nuzlocke-Lauf: erste Begegnung je Gebiet, Team, Box, Friedhof und Levelgrenze">Nuzlocke</a><a class="btn small" href="#fortschritt" data-tip="Wie viel du je Spiel, Generation und Typ schon hast">Fortschritt</a><a class="btn small" href="#fehlt" data-tip="Welche Pokémon des Spiel-Dex dir noch fehlen und wie du sie bekommst">Was fehlt mir noch?</a>` : ""}</div></div>`;
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

