/* Pokédex-Oberfläche, Teil 4 von 10: Detailseite, Raids, Aufträge, Forschung.
   Die Teile lädt index.html der Reihe nach; sie teilen sich die globalen Namen (docs/oberflaeche.md). */
"use strict";
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
  // 0.56.2: auch aus „Was fehlt mir noch?“, Karte, Items und den übrigen Ansichten führt „Zurück“ dorthin, woher man kam
  const names = {team: "Team", attacken: "Attacken", typen: "Typen", pokemon: "Liste", fehlt: "Was fehlt mir noch?", karte: "Karte", items: "Items",
    sammeln: "Sammelobjekte", raids: "Raids", auftraege: "Aufträge", initiative: "Initiative", kampf: "Kampf"};
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
  // Generation 1: ein Spezial-Wert statt Sp.-Angriff und Sp.-Verteidigung
  const stats = d.werte.map((v, i) => GEN() === 1 && i === 4 ? "" : `<span>${GEN() === 1 && i === 3 ? "Spezial" : STAT[i]}</span><span class="num">${v}</span><span class="sbar" data-tip="${esc(statTip(i, v))}"><i style="width:${Math.min(100, v / statMax(i) * 100)}%;background:${statColor(v)}"></i></span>`).join("");
  const evo = evoHtml(d.entwicklung, d.id);
  main.innerHTML = `
    <div class="bar">${backLink()}
      <label class="game2">Spiel <select class="gamesel"></select></label>
      ${inTeam ? `<button data-act="teamdel" data-slot="${DSLOT}">Aus dem Team nehmen</button>` : ""}
      ${teamFull() ? (inTeam ? "" : `<span class="hint">Team voll</span>`) : `<button class="${inTeam ? "" : "primary"}" data-act="teamadd" data-id="${d.id}">${inTeam ? "Noch einmal ins Team" : "Ins Team"}</button>`}
      <button data-act="fav" data-id="${d.id}" data-markbtn="fav" class="mark${isFav(d.id) ? " on" : ""}">${markLabel("fav", isFav(d.id))}</button>
      <button data-act="caught" data-id="${d.id}" data-markbtn="gef" class="mark${isCaught(d.id) ? " on" : ""}" data-tip="${ballTip(d.id)}">${markLabel("gef", isCaught(d.id), d.id)}</button>
      ${S.alphaOk.has(d.id) || isAlpha(d.id) ? `<button data-act="alpha" data-id="${d.id}" data-markbtn="alpha" class="mark${isAlpha(d.id) ? " on" : ""}">${markLabel("alpha", isAlpha(d.id), d.id)}</button>` : ""}
      <a class="btn" href="${esc(d.wiki)}" target="_blank" rel="noopener noreferrer" data-tip="Seite im PokéWiki in einem neuen Tab">PokéWiki ↗</a>
      <span class="seg"><a class="btn mark" href="#vergleich/${d.id}/-" data-tip="Neben ein anderes Pokémon stellen: Werte, Typwirkung, Fähigkeiten, Attacken">⚖ Vergleichen</a>
      <button data-act="cmpmark" data-id="${d.id}" data-markbtn="cmp" class="mark${cmpMarked(d.id) ? " on" : ""}" data-tip="Merkt das Pokémon für den Vergleich (bis zu 8). Im Vergleich stehen gemerkte und Favoriten zur schnellen Wahl bereit">${markLabel("cmp", cmpMarked(d.id))}</button></span>
      ${d.formen.length ? `<span class="hint">Formen:</span>` + d.formen.map((f) => `<a class="btn small" href="#pokemon/${f.id}">${esc(f.name)}</a>`).join("") : ""}
      ${inTeam && d.formen.length ? `<label data-tip="Tauscht die Form auf diesem Team-Platz (etwa Mega-Entwicklung für den Kampf); Level, Attacken und Tera bleiben">Platz ${DSLOT + 1} als
        <select id="formsel"><option value="${d.id}" selected>${esc(d.name)}</option>${d.formen.map((f) => `<option value="${f.id}">${esc(f.name)}${f.kampf ? " (Kampfform)" : ""}</option>`).join("")}</select></label>` : ""}</div>
    ${!d.im_spiel && S.game ? `<div class="note warn">In ${esc(gameName())} nicht enthalten.</div>` : ""}
    ${inTeam && S.team.ids.filter((x) => x === id).length > 1 ? `<div class="note info">${esc(d.name)} ist mehrmals im Team; hier geht es um Platz ${DSLOT + 1}.</div>` : ""}
    <div class="dgrid">
      <div class="box"><div class="head"><div class="pic">${img(d.id, "big", true)}${extrasHtml(d)}</div><div><h2>${esc(d.name)}</h2><div class="muted">#${d.nr ?? d.art} · ${esc(d.kategorie)}</div>
        <div style="margin-top:4px">${tchips(d.typen)}</div><span data-tip-stats="${d.werte.join(",")}">${radar(d.werte, 220, true)}</span></div></div>
        ${dexTextHtml(d)}<div class="stats">${stats}<span><b>Summe</b></span><span class="num" data-tip="${esc(statTip("summe", d.summe))}"><b style="color:${sumColor(d.summe)}">${d.summe}</b></span><span></span></div>
        ${d.werte_alt ? `<p class="hint">Basiswerte wie in Generation ${GEN()}; später wurden sie geändert (Quelle: Pokémon Showdown).</p>` : ""}
        ${moreHtml(d)}
        ${LA() ? `<div id="elbox"></div>` : STATS_OK() ? `<div id="stbox"></div>` : ""}
        ${d.faehigkeiten.length ? `<h3>Fähigkeiten</h3>` + d.faehigkeiten.map((a) => `<div><b>${wikiLink(a.name)}</b>${a.versteckt ? " <span class='cls'>versteckt</span>" : ""}${a.wirkt ? " <span class='cls'>ändert Typwirkung</span>" : ""}<div class="why">${esc(a.text)}${fromHtml(a)}</div></div>`).join("")
          : noAbil() ? `<p class="hint">In ${esc(gameName())} gibt es keine Fähigkeiten${GEN() <= 2 ? " (erst ab Generation 3)" : ""}.</p>` : ""}
        ${GEN() <= 3 ? `<p class="hint">Bis Generation 3 hängt physisch oder speziell am Typ der Attacke: Normal, Kampf, Flug, Gift, Boden, Gestein, Käfer, Geist und Stahl sind physisch, die übrigen speziell.${GEN() === 1 ? " In Generation 1 gab es statt Sp.-Angriff und Sp.-Verteidigung einen gemeinsamen Spezial-Wert." : ""}</p>` : ""}
      </div>
      <div class="stack">
        <div class="box"><h2 data-fold="def" data-tip="Verteidigung: so stark treffen Attacken eines Typs ${esc(d.name)}">Verteidigung: Typwirkung gegen ${esc(d.name)}</h2>
          ${d.faehigkeit_wirkt ? `<p class="hint">Mit Fähigkeit eingerechnet.</p>` : ""}
          ${defHtml(Object.fromEntries(Object.entries(d.wirkung).map(([t, f]) => [t, f])))}
          ${inTeam && TERA() ? (() => { const tt = S.team.details[DSLOT]?.tera; return `<div class="bar slim" style="margin-top:8px"><label data-tip="Tera-Typ dieses Team-Platzes: nach der Terakristallisierung zählt nur noch er für die Verteidigung; Attacken vom Tera-Typ bekommen den Eigentyp-Bonus">Tera-Typ
              <select id="terasel"><option value="">–</option>${Object.entries(S.types).map(([k, n]) => `<option value="${k}"${String(tt) === k ? " selected" : ""}>${esc(n)}</option>`).join("")}</select></label></div>
            ${tt ? `<h3>Terakristallisiert: ${tchip(String(tt))}</h3>${defHtml(defense([String(tt)]))}` : ""}`; })() : ""}</div>
        <div class="box"><h2 data-fold="duel" data-tip="Typ-Duell: wie gut ${esc(d.name)} gegen Pokémon eines Typs steht. Austeilen = bester eigener Typ, einstecken = beide eigenen Typen zusammengerechnet. Hovern zeigt die Rechnung.">Im Duell gegen Typen</h2>
          <p class="hint">${DUEL_LEGEND}</p>
          ${duelHtml(d.name, d.typen)}</div>
        <div class="box"><h2 data-fold="evo">Entwicklung</h2>${evo ? `<div class="evo">${evo}</div>` : `<p class="hint">${esc(d.name)} entwickelt sich nicht.</p>`}</div>
        ${catchHtml(d)}${researchHtml(d)}${requestsHtml(d)}${partnerHtml(d)}
        ${raidHtml(d)}
        ${cryptoHtml(d)}
        ${heldHtml(d)}${pokopiaHtml(d)}
        ${optikHtml(d)}
      </div>
    </div>
    <div class="box" style="margin-top:12px"><h2 data-fold="enc">Fundorte in ${esc(gameName())}</h2>${encHtml(d)}</div>
    <div class="box" id="mbox"></div>`;
  header();
  renderMoves(d.attacken, level);
  if (LA()) elBox(d, inTeam ? DSLOT : null);
  else if (STATS_OK()) statBox(d, inTeam ? DSLOT : null);
  wireExtras(d);
  $('details[data-store="raidOpen"]')?.addEventListener("toggle", (e) => store.set("raidOpen", e.target.open));
  $("#formsel")?.addEventListener("change", (e) => {
    S.team.ids[DSLOT] = +e.target.value; saveTeam(); dock(); location.hash = `#pokemon/${e.target.value}/${DSLOT}`;
  });
  $("#terasel")?.addEventListener("change", (e) => {
    S.team.details[DSLOT] = Object.assign({}, S.team.details[DSLOT], {tera: e.target.value ? +e.target.value : null}); saveTeam(); dock();
    const y = window.scrollY; detailView(id, DSLOT).then(() => window.scrollTo(0, y));
  });
  window.scrollTo(0, 0);
}
/* Effort Levels (Legenden: Arceus): je Wert die Stufe 0–10 und ein Ziel; der Server rechnet die Werte und wie viele
   Leistungs-Items (Sand, Kies, Stein, Fels) bis zum Ziel fehlen. Im Team je Platz gespeichert, sonst nur zum Ausprobieren. */
async function elBox(d, slot) {
  const el = $("#elbox");
  if (!el) return;
  const det = slot !== null ? S.team.details[slot] || {} : (elBox.tmp ||= {});
  if (slot === null && elBox.tmpId !== d.id) { elBox.tmpId = d.id; Object.keys(det).forEach((k) => delete det[k]); }
  const lv = det.level || 50;
  const r = await api("/api/effort", {spiel: S.game, id: d.id, level: lv, wesen: det.wesen || null, el: det.el || [0, 0, 0, 0, 0, 0], ziel: det.el_ziel || det.el || [0, 0, 0, 0, 0, 0]}).catch(teil("Effort Levels", null));
  if (!r || !$("#elbox")) return;
  const opt = (v, from = 0) => Array.from({length: 11 - from}, (_, k) => k + from).map((k) => `<option value="${k}"${k === v ? " selected" : ""}>${k}</option>`).join("");
  const nat = (x) => x.wesen > 1 ? ` <span class="f fd" data-tip="Wesen +10 %">+</span>` : x.wesen < 1 ? ` <span class="f fa05" data-tip="Wesen −10 %">−</span>` : "";
  const need = r.bonbons.some((n) => n);
  const open = store.get("elOpen", true);
  el.innerHTML = `<details class="sub" id="eldet"${open ? " open" : ""}><summary><h3 style="display:inline">Effort Levels</h3> <span class="hint">${slot !== null ? `Platz ${slot + 1}, Level ${lv}` : `zum Ausprobieren, Level ${lv}`}</span></summary>
    <p class="hint">In Legenden: Arceus ersetzen Effort Levels (0 bis 10 je Wert) die EVs. Jede Stufe gibt Bonuspunkte, die großen Sprünge kommen bei 4, 7 und 10.
      Ein frisch gefangenes Pokémon startet nach seinen DVs (31: Stufe 3, ab 26: 2, ab 20: 1).${slot === null ? " Im Team merkt sich jeder Platz seine Stufen." : ""}</p>
    <div class="bar slim"><label data-tip="Mit einer Minze: das Wesen wählen, dessen Werte die Minze gibt. Sie ändert, welchen Wert das Wesen hebt und senkt; das Wesen selbst bleibt">Wesen (oder Minze) <select id="elnat"><option value="">neutral</option>${r.wesen_liste.filter((w) => w.mod).map((w) => `<option value="${w.id}"${w.id === r.wesen ? " selected" : ""}>${esc(w.name)} (+${STAT[w.mod[0]]} −${STAT[w.mod[1]]})</option>`).join("")}</select></label>
      ${slot !== null ? `<span class="hint">Level wie unten bei den Attacken</span>` : `<label>Level <input type="number" id="ellv" min="1" max="100" value="${lv}" style="width:64px"></label>`}</div>
    ${elChart(r.rows, lv)}
    <table class="rows eltab"><tr><th>Wert</th><th class="c" data-tip="Basiswert der Art: fest, hängt nicht vom Level ab. Aus ihm, dem Level, dem Effort Level und dem Wesen rechnet das Spiel den Wert">Basis</th>
      <th class="c" data-tip="Effort Level 0 bis 10, wie im Spiel in der Übersicht des Pokémon">Stufe</th><th class="c" data-tip="Wert im Spiel mit dieser Stufe, diesem Level und Wesen">jetzt</th>
      <th class="c" data-tip="Stufe, auf die du hinarbeitest; folgt der Stufe, bis du es eigens höher setzt">Ziel</th><th class="c" data-tip="Wert, wenn das Ziel erreicht ist">am Ziel</th><th class="c" data-tip="Wert mit Stufe 10 bei diesem Level und Wesen">höchstens</th></tr>
    ${r.rows.map((x, i) => `<tr><td>${STAT[i]}${nat(x)}</td><td class="c">${x.basis}</td><td class="c"><select data-el="${i}">${opt(x.el)}</select></td><td class="c" ${tipRef(elTipHtml(x, i, lv))}><b>${x.wert}</b></td>
      <td class="c"><select data-elz="${i}">${opt(x.ziel, x.el)}</select></td><td class="c">${x.ziel > x.el ? `<b style="color:var(--go)">${x.wert_ziel}</b> <span class="hint">+${x.wert_ziel - x.wert}</span>` : `<span class="hint">${x.wert_ziel}</span>`}</td><td class="c hint">${x.max}</td></tr>`).join("")}</table>
    <p class="hint">${need ? `Bis zum Ziel fehlen: ${r.bonbons.map((n, k) => n ? `<b>${n}× ${esc(r.sorten[k])}</b>` : "").filter(Boolean).join(", ")}.` : "Ziel wählen: dann steht hier, wie viele Leistungs-Items fehlen."}
      Leistungssand hebt Stufe 0–2, Leistungskies 3–5, Leistungsstein 6–8, Leistungsfels 9 auf 10, je um eins. Es gibt sie für freigelassene Pokémon, von Alphas und bei Zisu im Trainingsplatz zum Tauschen.
      <button class="link" id="elmax" data-tip="Ziel überall auf 10">alles auf 10</button> · <button class="link" id="elreach" data-tip="Ziel erreicht: Stufen auf das Ziel setzen">Ziel erreicht</button></p></details>`;
  const save = () => { if (slot !== null) { S.team.details[slot] = Object.assign({}, S.team.details[slot], {el: det.el, el_ziel: det.el_ziel, wesen: det.wesen}); saveTeam(); dock(); } elBox(d, slot); };
  const cur = () => r.rows.map((x) => x.el), goal = () => r.rows.map((x) => x.ziel);
  $("#eldet").addEventListener("toggle", (e) => store.set("elOpen", e.target.open));
  $$("[data-el]", el).forEach((s) => s.addEventListener("change", () => { const a = cur(), z = goal(); const i = +s.dataset.el, v = +s.value, prev = a[i]; a[i] = v; if (z[i] === prev || z[i] < v) z[i] = v; det.el = a; det.el_ziel = z; save(); }));
  $$("[data-elz]", el).forEach((s) => s.addEventListener("change", () => { const z = goal(); z[+s.dataset.elz] = +s.value; det.el = cur(); det.el_ziel = z; save(); }));
  $("#elnat").addEventListener("change", (e) => { det.wesen = e.target.value ? +e.target.value : null; det.el = cur(); det.el_ziel = goal(); save(); });
  $("#ellv")?.addEventListener("change", (e) => { det.level = Math.max(1, Math.min(100, +e.target.value || 50)); det.el = cur(); det.el_ziel = goal(); save(); });
  $("#elmax").addEventListener("click", () => { det.el = cur(); det.el_ziel = [10, 10, 10, 10, 10, 10]; save(); });
  $("#elreach").addEventListener("click", () => { det.el = goal(); det.el_ziel = goal(); save(); });
}
/* Werte-Diagramm (alle Spiele außer Legenden: Arceus, Champions, Pokopia): IVs und EVs (bis Generation 2
   DVs und Stat Exp, in Let's Go AVs), Wesen und Ziel-EVs; der Server rechnet die Werte. Im Team je Platz gespeichert, sonst zum Ausprobieren. */
const STATS_OK = () => ["dv", "ev", "av"].includes(PROFIL().werte);     // Werte-Rechner der Hauptreihe; Effort Levels: elBox
async function statBox(d, slot) {
  const el = $("#stbox");
  if (!el) return;
  const det = slot !== null ? S.team.details[slot] || {} : (statBox.tmp ||= {});
  if (slot === null && statBox.tmpId !== d.id) { statBox.tmpId = d.id; Object.keys(det).forEach((k) => delete det[k]); }
  const lv = det.level || 50, K = GEN() <= 2 ? {iv: "dvs", ev: "exp", z: "exp_ziel"} : PROFIL().werte === "av" ? {iv: "ivs", ev: "avs", z: "av_ziel"} : {iv: "ivs", ev: "evs", z: "ev_ziel"};   // bis Gen. 2 eigene Felder (Showdown schreibt dort EVs)
  const r = await api("/api/werte", {spiel: S.game, id: d.id, level: lv, wesen: det.wesen || null, ivs: det[K.iv] || null, evs: det[K.ev] || null, ziel: det[K.z] || null}).catch(teil("Werte", null));
  if (!r || !$("#stbox") || !r.rows.length) return;
  const old = r.gen <= 2, lg = r.art === "lgpe", IV = old ? "DV" : "IV", EV = old ? "Stat Exp" : lg ? "AV" : "EV";
  const nat = (x) => x.wesen > 1 ? ` <span class="f fd" data-tip="Wesen +10 %">+</span>` : x.wesen < 1 ? ` <span class="f fa05" data-tip="Wesen −10 %">−</span>` : "";
  const open = store.get("stOpen", true), left = r.ev_gesamt ? r.ev_gesamt - r.ev_ziel_summe : null;
  const tip = (x, i) => `${STAT[i]} ${x.wert}: Basiswert ${x.teile.basis}, durch Level ${lv} +${x.teile.level}, ${IV} ${x.iv}: +${x.teile.iv}, ${EV} ${x.ev}: +${x.teile.ev}${x.teile.wesen ? `, Wesen ${x.teile.wesen > 0 ? "+" : ""}${x.teile.wesen}` : ""}`
    + (old ? `\nFormel: ((Basis + DV) × 2 + √Stat Exp / 4) × Level / 100 + ${i === 0 ? "Level + 10" : "5"}` : lg ? `\nFormel: (2 × Basis + IV) × Level / 100 + ${i === 0 ? "Level + 10" : "5, dann × Wesen"}, dann + AV`
      : `\nFormel: (2 × Basis + IV + EV / 4) × Level / 100 + ${i === 0 ? "Level + 10" : "5, dann × Wesen"}`);
  const tipH = (x, i) => partsTip(`${STAT[i]} bei Level ${lv}`, [["e-b", "Basiswert", x.teile.basis], ["e-l", "durch das Level", x.teile.level], ["e-i", `${IV} ${x.iv}`, x.teile.iv], ["e-e", `${EV} ${x.ev}`, x.teile.ev], ["e-w", "Wesen", x.teile.wesen]], x.wert,
    [tip(x, i).split("\n")[1], x.ziel > x.ev ? `Mit ${x.ziel} ${EV}: ${x.wert_ziel}` : ""]);
  const top = Math.max(...r.rows.map((x) => x.max), 1), pc = (v) => (Math.max(0, v) / top * 100).toFixed(2);
  const seg = (cls, v) => v > 0 ? `<i class="${cls}" style="width:${pc(v)}%"></i>` : "";            // Rechenweg am ganzen Balken
  const bars = r.rows.map((x, i) => { const t = x.teile, extra = x.ev_ziel_teil - t.ev;
    return elRow(STAT_K[i], x, `${seg("e-b", t.basis, `Basiswert ${t.basis}`)}${seg("e-l", t.level, `durch Level ${lv}: +${t.level}`)}${seg("e-i", t.iv, `${IV} ${x.iv}: +${t.iv}`)}${seg("e-e", t.ev, `${EV} ${x.ev}: +${t.ev}`)}${seg("e-w", t.wesen, `Wesen: +${t.wesen}`)}${t.wesen < 0 ? `<i class="e-m" style="width:${pc(-t.wesen)}%;margin-left:-${pc(-t.wesen)}%"></i>` : ""}${seg("e-z", extra, `bis zum Ziel (${x.ziel} ${EV}): +${extra}`)}`, tipRef(tipH(x, i)), extra); }).join("") + elSum(r.rows);
  const net = statNet(r.rows, top, "ev");
  el.innerHTML = `<details class="sub" id="stdet"${open ? " open" : ""}><summary><h3 style="display:inline">Werte</h3> <span class="hint">${slot !== null ? `Platz ${slot + 1}, Level ${lv}` : `zum Ausprobieren, Level ${lv}`}</span></summary>
    <p class="hint">${old ? "Bis Generation 2: DVs 0 bis 15 und Stat Exp bis 65535 je Wert (aus besiegten Pokémon und Vitaminen); es gibt kein Wesen." : lg ? "Let's Go: statt EVs gibt es AVs (Punkte aus Bonbons), 0 bis 200 je Wert und ohne Grenze für die Summe; jeder AV ist ein Punkt. Den Freundschafts-Bonus (bis +10 %) rechnet das Diagramm nicht ein." : `IVs 0 bis 31 (angeboren), EVs bis 252 je Wert und ${r.ev_gesamt} zusammen, aus besiegten Pokémon, Vitaminen (+10) und Federn (+1).${r.minzen ? " Minzen ändern, welchen Wert das Wesen hebt und senkt." : ""}`}${slot === null ? " Im Team merkt sich jeder Platz seine Werte." : ""}</p>
    <div class="bar slim">${old ? "" : `<label${r.minzen ? ` data-tip="Mit einer Minze: das Wesen wählen, dessen Werte die Minze gibt. Sie ändert, welchen Wert das Wesen hebt und senkt; das Wesen selbst bleibt"` : ""}>Wesen${r.minzen ? " (oder Minze)" : ""} <select id="stnat"><option value="">neutral</option>${r.wesen_liste.filter((w) => w.mod).map((w) => `<option value="${w.id}"${w.id === r.wesen ? " selected" : ""}>${esc(w.name)} (+${STAT[w.mod[0]]} −${STAT[w.mod[1]]})</option>`).join("")}</select></label>`}
      ${slot !== null ? `<span class="hint">Level wie unten bei den Attacken</span>` : `<label>Level <input type="number" id="stlv" min="1" max="100" value="${lv}" style="width:64px"></label>`}</div>
    <div class="elchart"><div class="elbars">${bars}</div><div>${net}</div></div>
    <p class="hint ellg"><span class="e-b"></span>Basiswert <span class="e-l"></span>durch das Level <span class="e-i"></span>${IV} <span class="e-e"></span>${EV} <span class="e-w"></span>Wesen + <span class="e-m"></span>Wesen − <span class="e-z"></span>bis zum Ziel</p>
    <table class="rows eltab stab"><tr><th>Wert</th><th class="c">Basis</th><th class="c" data-tip="0 bis ${r.iv_max}">${IV}</th><th class="c" data-tip="0 bis ${r.ev_max}">${EV}</th><th class="c">jetzt</th>
      <th class="c" data-tip="${EV}, auf die du hinarbeitest">Ziel</th><th class="c">am Ziel</th><th class="c" data-tip="mit vollen ${IV}s und ${EV}${old ? "" : " und passendem Wesen"}">höchstens</th></tr>
    ${r.rows.map((x, i) => `<tr><td>${STAT[i]}${nat(x)}</td><td class="c">${x.basis}</td><td class="c"><input type="number" min="0" max="${r.iv_max}" value="${x.iv}" data-stiv="${i}"></td>
      <td class="c"><input type="number" min="0" max="${r.ev_max}" step="${old || lg ? 1 : 4}" value="${x.ev}" data-stev="${i}"></td><td class="c" ${tipRef(tipH(x, i))}><b>${x.wert}</b></td>
      <td class="c"><input type="number" min="0" max="${r.ev_max}" step="${old || lg ? 1 : 4}" value="${x.ziel}" data-stz="${i}"></td>
      <td class="c">${x.ziel > x.ev ? `<b style="color:var(--go)">${x.wert_ziel}</b> <span class="hint">+${x.wert_ziel - x.wert}</span>` : `<span class="hint">${x.wert_ziel}</span>`}</td><td class="c hint">${x.max}</td></tr>`).join("")}</table>
    <p class="hint">${left === null ? "" : left >= 0 ? `Ziel-EVs zusammen ${r.ev_ziel_summe} von ${r.ev_gesamt}, noch ${left} frei. ` : `<span style="color:var(--stop)">Ziel-EVs zusammen ${r.ev_ziel_summe}: ${-left} mehr als erlaubt (${r.ev_gesamt}).</span> `}
      <button class="link" id="streach" data-tip="Ziel erreicht: ${EV} auf das Ziel setzen">Ziel erreicht</button></p></details>`;
  const cur = (k) => r.rows.map((x) => x[k]);
  const save = () => { if (slot !== null) { S.team.details[slot] = Object.assign({}, S.team.details[slot], {[K.iv]: det[K.iv], [K.ev]: det[K.ev], [K.z]: det[K.z], wesen: det.wesen}); saveTeam(); dock(); } statBox(d, slot); };
  const fix = () => { det[K.iv] = det[K.iv] || cur("iv"); det[K.ev] = det[K.ev] || cur("ev"); det[K.z] = det[K.z] || cur("ziel"); };
  $("#stdet").addEventListener("toggle", (e) => store.set("stOpen", e.target.open));
  $$("[data-stiv]", el).forEach((s) => s.addEventListener("change", () => { fix(); det[K.iv] = cur("iv"); det[K.iv][+s.dataset.stiv] = Math.max(0, Math.min(r.iv_max, +s.value || 0)); save(); }));
  $$("[data-stev]", el).forEach((s) => s.addEventListener("change", () => { fix(); const i = +s.dataset.stev, v = Math.max(0, Math.min(r.ev_max, +s.value || 0)), z = cur("ziel");
    if (z[i] === r.rows[i].ev || z[i] < v) z[i] = v; det[K.ev] = cur("ev"); det[K.ev][i] = v; det[K.z] = z; save(); }));
  $$("[data-stz]", el).forEach((s) => s.addEventListener("change", () => { fix(); det[K.z] = cur("ziel"); det[K.z][+s.dataset.stz] = Math.max(0, Math.min(r.ev_max, +s.value || 0)); save(); }));
  $("#stnat")?.addEventListener("change", (e) => { det.wesen = e.target.value ? +e.target.value : null; save(); });
  $("#stlv")?.addEventListener("change", (e) => { det.level = Math.max(1, Math.min(100, +e.target.value || 50)); save(); });
  $("#streach").addEventListener("click", () => { fix(); det[K.ev] = cur("ziel"); det[K.z] = cur("ziel"); save(); });
}
/* Woraus ein Wert in Legenden: Arceus besteht, als Text für den Tooltip */
function elTipHtml(x, i, lv) {
  const t = x.teile;
  return partsTip(`${STAT[i]} bei Level ${lv}, Effort Level ${x.el}`, [["e-b", "Basiswert", t.basis], ["e-l", "durch das Level", t.level], ["e-e", "durch Effort Levels", t.el], ["e-w", "Wesen", t.wesen]], x.wert,
    [i === 0 ? `Grundwert: (Level/100 + 1) × Basis + Level = (${lv}/100 + 1) × ${x.basis} + ${lv}` : `Grundwert: (Level/50 + 1) × Basis / 1,5${x.wesen !== 1 ? " × Wesen" : ""} = (${lv}/50 + 1) × ${x.basis} / 1,5${x.wesen !== 1 ? ` × ${de(x.wesen)}` : ""}`,
      `Bonus: (√Basis × Faktor + Level) / 2,5, gerundet; Faktor bei Stufe ${x.el}: ${x.faktor}, Bonus ${x.bonus}`]);
}
function elTip(x, i, lv) {
  const t = x.teile, n = x.wesen > 1 ? "× 1,1 (Wesen)" : x.wesen < 1 ? "× 0,9 (Wesen)" : "";
  return `${STAT[i]} ${x.wert} = Grundwert ${t.basis + t.level - (x.bonus - t.el) + t.wesen} + Bonus ${x.bonus}\n`
    + (i === 0 ? `Grundwert: (Level/100 + 1) × Basis + Level = (${lv}/100 + 1) × ${x.basis} + ${lv}` : `Grundwert: (Level/50 + 1) × Basis / 1,5 ${n} = (${lv}/50 + 1) × ${x.basis} / 1,5 ${n}`)
    + `\nBonus: (√Basis × Faktor + Level) / 2,5, gerundet; Faktor bei Stufe ${x.el}: ${x.faktor}`
    + `\nDavon: Basiswert ${t.basis}, durch das Level +${t.level}, durch Effort Levels +${t.el}${t.wesen ? `, Wesen ${t.wesen > 0 ? "+" : ""}${t.wesen}` : ""}`;
}
/* Live-Diagramm zu den Effort Levels: je Wert ein gestapelter Balken (Basiswert, Level, Effort Levels, Wesen, bis
   zum Ziel gestrichelt) und ein Netz mit denselben Schichten. Maßstab: der höchste Wert mit Stufe 10 */
function elChart(rows, lv) {
  const top = Math.max(...rows.map((x) => x.max), 1), pc = (v) => (Math.max(0, v) / top * 100).toFixed(2);
  const seg = (cls, v, tip) => v > 0 ? `<i class="${cls}" style="width:${pc(v)}%" data-tip="${esc(tip)}"></i>` : "";
  const bars = rows.map((x, i) => { const t = x.teile, extra = x.el_ziel_teil - t.el;
    return elRow(STAT_K[i], x, `${seg("e-b", t.basis, `Basiswert ${t.basis}`)}${seg("e-l", t.level, `durch Level ${lv}: +${t.level}`)}${seg("e-e", t.el, `durch Effort Level ${x.el}: +${t.el}`)}${seg("e-w", t.wesen, `Wesen: +${t.wesen}`)}${t.wesen < 0 ? `<i class="e-m" style="width:${pc(-t.wesen)}%;margin-left:-${pc(-t.wesen)}%"></i>` : ""}${seg("e-z", extra, `bis zum Ziel (Stufe ${x.ziel}): +${extra}`)}`, tipRef(elTipHtml(x, i, lv)), extra); }).join("") + elSum(rows);
  // Netz: Schichten von außen nach innen (Ziel, jetzt, ohne Effort Levels, Basiswert)
  const net = statNet(rows, top, "el");
  return `<div class="elchart"><div class="elbars">${bars}</div><div>${net}</div></div>
    <p class="hint ellg"><span class="e-b"></span>Basiswert <span class="e-l"></span>durch das Level <span class="e-e"></span>durch Effort Levels <span class="e-w"></span>Wesen + <span class="e-m"></span>Wesen − <span class="e-z"></span>bis zum Ziel</p>`;
}
/* Effort Levels des Teams (Legenden: Arceus): Übersicht; ändern auf der Detailseite. Nicht eingetragen = Stufe 0 */
async function elTeam() {
  const rid = RID, r = await api("/api/effort/team", {spiel: S.game, ids: S.team.ids, details: S.team.details}).catch(teil("Effort Levels des Teams", null));
  const el = $("#eltbody");
  if (!r || !el || rid !== RID) return;
  const miss = r.mitglieder.filter((m) => !m.eingetragen).length, need = r.bonbons.some((n) => n);
  const items = (b) => b.map((n, k) => n ? `${n}× ${esc(r.sorten[k])}` : "").filter(Boolean).join(", ");
  el.innerHTML = `${miss ? `<p class="hint">${miss === r.mitglieder.length ? "Noch für kein Mitglied eingetragen" : `Für ${miss} Mitglied${miss > 1 ? "er" : ""} nicht eingetragen`}: dann rechnet das Tool mit Stufe 0, also vorsichtig.
      Im Spiel zeigt die Übersicht des Pokémon bei den Werten seine Effort Levels; auf der Detailseite eintragen, dann zählen sie hier und in der Initiative-Liste.</p>` : ""}
    <table class="rows eltab"><tr><th>Mitglied</th>${STAT.map((s) => `<th class="c">${esc(s.replace("Verteidigung", "Vert.").replace("Sp.-Angriff", "Sp.-Ang."))}</th>`).join("")}<th>fehlt bis zum Ziel</th></tr>
    ${r.mitglieder.map((m) => `<tr data-hc="${m.id}"><td class="nw">${img(m.id, "sm")} <a href="#pokemon/${m.id}/${m.slot}">${esc(m.name)}</a>${m.eingetragen ? "" : ` <span class="cls" data-tip="Stufen nicht eingetragen; gerechnet mit 0">offen</span>`}</td>
      ${m.el.map((e, i) => `<td class="c" data-tip="${esc(`${STAT[i]}: Stufe ${e}, Wert ${m.werte[i]}${m.ziel[i] > e ? `\nZiel ${m.ziel[i]}: Wert ${m.werte_ziel[i]}` : ""}`)}">${m.eingetragen ? `<b>${e}</b>` : `<span class="hint">0</span>`}${m.ziel[i] > e ? `<span class="hint">→${m.ziel[i]}</span>` : ""}</td>`).join("")}
      <td class="hint">${items(m.bonbons) || (m.eingetragen ? "Ziel erreicht" : "")}</td></tr>`).join("")}</table>
    <p class="hint">${need ? `Dem ganzen Team fehlen: <b>${items(r.bonbons)}</b>.` : "Ziele setzt du auf der Detailseite jedes Mitglieds; dann steht hier, was dem Team fehlt."} Werte mit Level und Wesen des Platzes (sonst Level 50).</p>`;
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
/* Tera-Raids in Karmesin/Purpur (PKHeX): Sterne, Level, Tera-Typ und Attacken des Raid-Gegners */
const stars = (n) => `<span class="stars" data-tip="${n} ${n === 1 ? "Stern" : "Sterne"}">${"★".repeat(Math.min(n, 7))}</span>`;
const raidMoves = (r) => r.attacken.map((m) => `<span class="rm">${tchip(m.typ)} ${esc(m.name)}</span>`).join(" ");
function raidHtml(d) {
  const xs = d.raids || [];
  if (!xs.length) return "";
  return `<details class="box"${store.get("raidOpen", false) ? " open" : ""} data-store="raidOpen"><summary><h2>Tera-Raids</h2><span class="hint">${xs.length} · ${[...new Set(xs.map((r) => r.sterne))].sort().map((n) => n + "★").join(" ")}</span></summary>
    <div class="raidl">${xs.map((r) => `<div>${stars(r.sterne)} <b>Lv ${r.level}</b> <span class="hint">${esc(r.gebiet)}</span>
      · ${r.tera ? `Tera ${tchip(r.tera)} <span class="hint">schwach gegen</span> ${tchips(r.schwach)}` : `<span class="hint">Tera zufällig</span>`}
      <div class="hint">${r.attacken.map((m) => esc(m.name)).join(", ")}</div></div>`).join("")}</div>
    <p class="hint">Aus den Spieldaten von PKHeX; Events (Distribution) und 7-Sterne-Raids sind frühere oder wiederkehrende Aktionen. <a href="#raids">Alle Raids</a></p></details>`;
}
/* Crypto-Pokémon in Colosseum und XD (PKHeX): wer es einsetzt, wo, mit welchen Attacken */
function cryptoHtml(d) {
  const xs = d.crypto || [];
  if (!xs.length) return "";
  return `<div class="box"><h2 data-tip="Crypto-Pokémon (englisch Shadow Pokémon) setzen Gegner ein; du fängst sie im Kampf (Snag Machine) und läuterst sie danach">Crypto-Pokémon</h2>
    <div class="raidl">${xs.map((x) => `<div><b>Lv ${x.level}</b> <span class="hint">Nr. ${x.nr} · <span data-tip="Heart Gauge: so viel Läuterung braucht es, bis es wieder normal ist">Läuterung ${x.messer.toLocaleString("de-DE")}</span></span>
      <div>${esc(x.trainer)}${x.orte.length ? ` <span class="hint">@ ${esc(x.orte.join(", "))}</span>` : ""}</div>
      <div class="hint">${esc(x.attacken.join(", "))}</div></div>`).join("")}</div>
    <p class="hint">Aus den Spieldaten von PKHeX; Trainer und Orte englisch.</p></div>`;
}
/* Liste aller Tera-Raids mit Konter aus dem eigenen Team (wer den Tera-Typ mit einem Eigentyp sehr effektiv trifft) */
async function raidsView(arg) {
  const rid = RID, n = +arg || store.get("raidStars", 7);
  main.innerHTML = `<div class="box"><div class="bar"><b>Tera-Raids in</b> <select class="gamesel"></select>
      <span class="seg">${[7, 6, 5, 4, 3, 2, 1].map((k) => `<a class="btn${k === n ? " on" : ""}" href="#raids/${k}">${k}★</a>`).join("")}</span></div>
    <p class="hint">Raid-Gegner aus den Spieldaten (PKHeX): Level, Tera-Typ und Attacken. Der Gegner verteidigt mit seinem Tera-Typ; „Konter“ sind Mitglieder deines Teams,
      die ihn mit einem Eigentyp sehr effektiv treffen. „Gefahr“: Mitglieder, die eine seiner Attacken sehr effektiv trifft.</p>
    <div id="rlist"><p class="hint">Lädt …</p></div></div>`;
  header();
  store.set("raidStars", n);
  const r = await api("/api/raids?" + qs({spiel: S.game, sterne: n}));
  if (rid !== RID) return;
  const ev = S.team.ids.length ? await api("/api/team/bewerten", {spiel: S.game, ids: S.team.ids, details: S.team.details, kurz: 1}) : {mitglieder: []};
  if (rid !== RID) return;
  const team = ev.mitglieder || [];
  const hitF = (atk, defT) => effMul(defT.map((d) => S.chart?.[atk]?.[d] ?? 1));
  const names = (xs) => xs.map((m) => esc(m.name)).join(", ");
  $("#rlist").innerHTML = r.rows.length ? `<div class="scroll sticky"><table class="rows sort raids"><thead><tr>${th("Pokémon")}${thc("Level")}${th("Tera")}${th("Attacken", "", true)}${team.length ? th("Konter", "", true) + th("Gefahr", "", true) : ""}${th("Gebiet")}</tr></thead>
    <tbody>${r.rows.map((x) => { const def = x.tera ? [String(x.tera)] : x.typen.map(String);
      const counter = team.filter((m) => m.typen.some((t) => hitF(String(t), def) > 1));
      const danger = team.filter((m) => x.attacken.some((a) => a.klasse !== 1 && hitF(String(a.typ), m.typen.map(String)) > 1));
      return `<tr data-hc="${x.id}"><td class="nw" data-s="${esc(x.name)}">${img(x.id, "sm")} <a href="#pokemon/${x.id}">${esc(x.name)}</a> ${tchips(x.typen)}</td>
        <td class="c num">${x.level}</td><td data-s="${x.tera || 0}">${x.tera ? tchip(x.tera) : `<span class="hint">zufällig</span>`}${x.schwach.length ? `<div class="hint">schwach: ${tchips(x.schwach)}</div>` : ""}</td>
        <td>${raidMoves(x)}</td>${team.length ? `<td class="${counter.length ? "go" : "stop"}">${names(counter) || "keiner"}</td><td class="${danger.length >= 3 ? "stop" : ""}">${names(danger) || "–"}</td>` : ""}
        <td class="hint">${esc(x.gebiet)}</td></tr>`; }).join("")}</tbody></table></div>`
    : `<p class="hint">Keine Raids gefunden. Der nächste Abgleich holt sie aus PKHeX.</p>`;
}
/* Aufträge in Legenden: Arceus (BisaFans): Liste mit Suche und Haken für erledigte; erledigt liegt beim Server
   in „gefunden“ unter der Karte „auftrag“ */
let REQ_DONE = new Set();
let REQ_REDRAW = null, REQ_OK = false;
// Spiele mit Aufträgen und Missionen; Mega-Dimension teilt sie mit Legenden: Z-A
/* Schlüssel, unter dem Aufträge und ihre Haken liegen (Profil: auftraege); eine Erweiterung teilt ihn mit dem Hauptspiel */
const REQ_GAME = () => PROFIL().auftraege || "";
async function loadReqDone(force = false) {      // einmal je Seitenaufruf und Spiel; die Haken ändert die Oberfläche selbst
  if (REQ_OK === REQ_GAME() && !force) return;
  const g = REQ_GAME();
  const r = g ? await api("/api/gefunden?" + qs({spiel: g})).catch(teil("Erledigte Aufträge", null)) : null;
  if (!r) return;
  // Nebenaufträge unter ihrer Nummer, Hauptmissionen als „m“ + Nummer (gespeichert unter auftrag und mission)
  REQ_DONE = new Set([...(r.auftrag || []).map(String), ...(r.mission || []).map((x) => "m" + x)]);
  REQ_OK = g;
}
const reqCheck = (nr) => `<span class="a req${REQ_DONE.has(String(nr)) ? " on" : ""}" data-act="reqdone" data-id="${nr}" data-tip="${REQ_DONE.has(String(nr)) ? "Erledigt; Klick: wieder offen" : "Als erledigt markieren"}">${REQ_DONE.has(String(nr)) ? "✓" : "○"}</span>`;
const reqMons = (x) => x.pokemon.map((m) => `<a href="#pokemon/${m.id}" data-hc="${m.id}">${esc(m.name)}</a>`).join(", ");
const reqTip = (x) => [x.beschreibung, x.loesung ? "Lösung: " + x.loesung : ""].filter(Boolean).join("\n\n");

async function requestsView() {
  const rid = RID, q = store.get("reqQ", ""), mode = store.get("reqMode", "offen"), art = store.get("reqArt", "neben");
  main.innerHTML = `<div class="box"><div class="bar"><b>Aufträge in</b> <select class="gamesel"></select>
      <span class="seg">${[["neben", "Nebenaufträge"], ["haupt", "Hauptmissionen"]].map(([k, n]) => `<button class="${k === art ? "on" : ""}" data-reqart="${k}">${n}</button>`).join("")}</span>
      <input id="reqq" type="search" placeholder="Suchen: Name, Pokémon, Ort, Belohnung" value="${esc(q)}">
      <span class="seg">${[["offen", "Offen"], ["alle", "Alle"], ["erledigt", "Erledigt"]].map(([k, n]) => `<button class="${k === mode ? "on" : ""}" data-reqmode="${k}">${n}</button>`).join("")}</span>
      <span id="reqn" class="hint"></span></div>
    <details class="sub reqinfo" id="reqinfo"${store.get("reqInfo", false) ? " open" : ""}><summary><span class="hint">Lösung beim Überfahren · ○ erledigt · 📍 auf der Karte</span></summary>
      <p class="hint"><span id="reqsrc"></span> Fährst du über einen Eintrag, siehst du Beschreibung und Lösung. ○ markiert ihn als erledigt,
      auch auf der Karte (und umgekehrt); 📍 ganz rechts springt zur Stelle auf der Karte.</p></details>
    <div id="reqlist"><p class="hint">Lädt …</p></div></div>`;
  header();
  const [r] = await Promise.all([api("/api/auftraege?" + qs({spiel: S.game})), loadReqDone(true)]);
  if (rid !== RID) return;
  $("#reqinfo").addEventListener("toggle", (e) => store.set("reqInfo", e.target.open));
  if (r.blaubeer) return blaubeerView(r);
  const K = r.karte || {}, KAP = r.kapitel || [];
  $("#reqsrc").textContent = `${gameName(r.spiel || REQ_GAME())} auf Deutsch (Quelle: ${r.quelle || "BisaFans"}).`;
  // Sprung zur Karte: eigene Spalte ganz rechts, hinter „erledigt“
  const pin = (k, nr) => `<td class="c">${K[k]?.[nr] ? `<a class="reqpin" href="#karte/mg/${esc(K[k][nr][0])}/${K[k][nr][1]}" data-tip="Auf der Karte zeigen">📍</a>` : ""}</td>`;
  const pinTh = Object.keys(K).length ? th("", "Auf der Karte zeigen", true) : "";
  const pinTd = (k, nr) => pinTh ? pin(k, nr) : "";
  const late = (x) => r.karte_bis && x.nr > r.karte_bis ? `<span class="hint" data-tip="${esc(r.spaet || "")}">nach dem Spiel</span>` : "";
  const draw = () => {
    const ql = ($("#reqq")?.value || "").trim().toLowerCase(), m = store.get("reqMode", "offen");
    if (store.get("reqArt", "neben") === "haupt") {
      const ms = r.missionen || [], done = (x) => REQ_DONE.has("m" + x.nr);
      const xs = ms.filter((x) => (m === "alle" || (m === "erledigt") === done(x)) && (!ql || [x.name, x.text].join(" ").toLowerCase().includes(ql)));
      $("#reqn").textContent = `${ms.filter(done).length} von ${ms.length} erledigt`;
      $("#reqlist").innerHTML = !ms.length ? `<p class="hint">Noch keine Hauptmissionen. Der nächste Abgleich holt sie.</p>`
        : `<div class="scroll sticky"><table class="rows sort vlines"><thead><tr>${thc("Nr.")}${th("Mission")}${th("Kapitel")}${th("Weg", "", true)}${th("", "", true)}${pinTh}</tr></thead>
          <tbody>${xs.map((x) => `<tr class="${done(x) ? "off" : ""}"><td class="c num" data-s="${x.nr}">${esc(x.label || String(x.nr))}</td>
            <td data-s="${esc(x.name)}"><b data-tip="${esc(x.text)}">${esc(x.name)}</b></td><td class="hint" data-s="${x.kapitel}">${x.kapitel ? esc(KAP.length > 2 ? `${x.kapitel}. ${KAP[x.kapitel - 1] || ""}` : KAP[x.kapitel - 1] || "") : ""}</td>
            <td class="why">${esc(x.text.split("\n").slice(0, 2).join(" "))}</td><td class="c">${reqCheck("m" + x.nr)}</td>${pinTd("mission", x.nr)}</tr>`).join("")
            || `<tr><td colspan="6" class="hint">Nichts gefunden.</td></tr>`}</tbody></table></div>`;
      return;
    }
    const xs = r.rows.filter((x) => (m === "alle" || (m === "erledigt") === REQ_DONE.has(String(x.nr)))
      && (!ql || [x.name, x.aufgabe, x.ort, x.belohnung, x.beschreibung, ...x.pokemon.map((p) => p.name)].join(" ").toLowerCase().includes(ql)));
    $("#reqn").textContent = `${r.rows.filter((x) => REQ_DONE.has(String(x.nr))).length} von ${r.rows.length} erledigt`;
    $("#reqlist").innerHTML = !r.rows.length ? `<p class="hint">Noch keine Aufträge. Der nächste Abgleich holt sie.</p>`
      : `<div class="scroll sticky"><table class="rows sort vlines"><thead><tr>${thc("Nr.")}${th("Auftrag")}${th("Aufgabe", "", true)}${th("Ort")}${th("Belohnung")}${th("Pokémon")}${th("", "", true)}${pinTh}</tr></thead>
        <tbody>${xs.map((x) => `<tr class="${REQ_DONE.has(String(x.nr)) ? "off" : ""}"><td class="c num" data-s="${x.nr}">${x.nr}</td>
          <td data-s="${esc(x.name)}"><b data-tip="${esc(reqTip(x))}">${esc(x.name)}</b></td><td class="why">${esc(x.aufgabe)}</td>
          <td data-s="${esc(x.ort)}">${esc(x.ort) || (K.auftrag?.[x.nr] ? `<span class="hint">siehe Karte</span>` : late(x))}</td><td data-s="${esc(x.belohnung)}">${esc(x.belohnung)}</td><td data-s="${esc(x.pokemon.map((p) => p.name).join(", "))}">${reqMons(x)}</td><td class="c">${reqCheck(x.nr)}</td>${pinTd("auftrag", x.nr)}</tr>`).join("")
          || `<tr><td colspan="8" class="hint">Nichts gefunden.</td></tr>`}</tbody></table></div>`;
  };
  draw();
  $("#reqq").addEventListener("input", () => { store.set("reqQ", $("#reqq").value); draw(); });
  main.querySelectorAll("[data-reqart]").forEach((b) => b.addEventListener("click", () => {
    store.set("reqArt", b.dataset.reqart); main.querySelectorAll("[data-reqart]").forEach((x) => x.classList.toggle("on", x === b)); draw(); }));
  main.querySelectorAll("[data-reqmode]").forEach((b) => b.addEventListener("click", () => {
    store.set("reqMode", b.dataset.reqmode); main.querySelectorAll("[data-reqmode]").forEach((x) => x.classList.toggle("on", x === b)); draw(); }));
  REQ_REDRAW = draw;
}
/* Karmesin/Purpur: Blaubeer-Missionen der Indigoblauen Scheibe (wiederholbar, daher ohne Haken), nach Bereich und Art */
function blaubeerView(r) {
  $("#reqsrc").textContent = `Blaubeer-Missionen der Indigoblauen Scheibe (Quelle: ${r.quelle}). Sie wechseln und lassen sich wiederholen, deshalb ohne Haken.`;
  $$("[data-reqart], [data-reqmode]").forEach((b) => { b.closest(".seg").hidden = true; });
  const bs = [...new Set(r.blaubeer.map((x) => x.bereich))];
  const draw = () => {
    const ql = ($("#reqq")?.value || "").trim().toLowerCase(), b = store.get("bbqBereich", "");
    const xs = r.blaubeer.filter((x) => (!b || x.bereich === b) && (!ql || [x.art, x.text, x.bereich].join(" ").toLowerCase().includes(ql)));
    $("#reqn").textContent = `${xs.length} von ${r.blaubeer.length}`;
    $("#reqlist").innerHTML = !r.blaubeer.length ? `<p class="hint">Noch keine Blaubeer-Missionen. Der nächste Abgleich holt sie.</p>`
      : `<div class="bar"><span class="seg">${[["", "Alle"], ...bs.map((x) => [x, x])].map(([k, n]) => `<button class="${k === b ? "on" : ""}" data-bbq="${esc(k)}">${esc(n)}</button>`).join("")}</span></div>
      <div class="scroll sticky"><table class="rows sort vlines"><thead><tr>${th("Bereich")}${th("Art")}${th("Aufgabe", "", true)}${thc("BP")}</tr></thead>
        <tbody>${xs.map((x) => `<tr><td class="hint">${esc(x.bereich)}</td><td data-s="${esc(x.art)}">${esc(x.art)}</td><td class="why">${esc(x.text)}</td>
          <td class="c num" data-s="${x.bp || 0}">${x.bp ?? ""}</td></tr>`).join("") || `<tr><td colspan="4" class="hint">Nichts gefunden.</td></tr>`}</tbody></table></div>`;
    $$("[data-bbq]").forEach((e) => e.addEventListener("click", () => { store.set("bbqBereich", e.dataset.bbq); draw(); }));
  };
  draw();
  $("#reqq").placeholder = "Suchen: Aufgabe, Art";
  $("#reqq").addEventListener("input", draw);
  REQ_REDRAW = draw;
}
/* 0.49: Forschungsstufe abhaken: Klick auf Stufe k setzt „bis k erreicht“, Klick auf die höchste erreichte nimmt sie zurück */
async function toggleResearch(b) {
  const art = +b.dataset.art, nr = +b.dataset.nr, k = +b.dataset.k, cell = b.closest("td"), spans = $$("[data-act=rsdone]", cell);
  const have = spans.filter((x) => x.classList.contains("on")).length, to = k === have ? k - 1 : k;
  const paint = (n) => spans.forEach((x, i) => { x.classList.toggle("on", i < n); x.dataset.tip = i < n ? (i + 1 === n ? "Erreicht; Klick: doch nicht" : "Erreicht") : "Klick: bis hier erreicht"; });
  paint(to);
  const obj = (n) => `${art}|${nr}|${n}`, all = spans.map((_, i) => i + 1);
  try {
    if (all.some((n) => n > to)) await api("/api/gefunden", {spiel: "legends-arceus", karte: "forschung", objekt: all.filter((n) => n > to).map(obj), an: false});
    if (to) await api("/api/gefunden", {spiel: "legends-arceus", karte: "forschung", objekt: all.filter((n) => n <= to).map(obj), an: true});
    if (DETAIL && DETAIL.forschung) {
      const a = DETAIL.forschung.find((x) => x.nr === nr), box = cell.closest(".box");
      if (a) { a.erreicht = to; if (box) { box.outerHTML = researchHtml(DETAIL); applyFolds(); } }
    }
  } catch (e) { ungespeichert(() => paint(have))(e); }
}
async function toggleReq(nr) {
  const k = String(nr), on = !REQ_DONE.has(k), mis = k.startsWith("m");
  const paint = () => $$(`[data-act="reqdone"][data-id="${nr}"]`).forEach((el) => { el.outerHTML = reqCheck(nr); });
  if (on) REQ_DONE.add(k); else REQ_DONE.delete(k);
  paint();
  if (location.hash.startsWith("#auftraege") && REQ_REDRAW) REQ_REDRAW();
  await api("/api/gefunden", {spiel: REQ_GAME(), karte: mis ? "mission" : "auftrag", objekt: mis ? k.slice(1) : k, an: on}).catch(ungespeichert(() => {
    if (on) REQ_DONE.delete(k); else REQ_DONE.add(k);
    paint();
  }));
}
/* Detailseite: Aufträge, in denen das Pokémon vorkommt */
function requestsHtml(d) {
  const xs = d.auftraege || [];
  if (!xs.length) return "";
  return `<div class="box"><h2 data-fold="reqmon">Aufträge mit ${esc(d.name)}</h2><table class="rows"><tbody>${xs.map((x) => `<tr class="${REQ_DONE.has(String(x.nr)) ? "off" : ""}">
      <td class="c num hint">${x.nr}</td><td><b data-tip="${esc(reqTip(x))}">${esc(x.name)}</b><div class="why">${esc(x.aufgabe)}</div></td>
      <td class="hint">${esc(x.ort)}</td><td>${esc(x.belohnung)}</td><td class="c">${reqCheck(x.nr)}</td></tr>`).join("")}</tbody></table>
    <p class="hint">Quelle: BisaFans. Alle Aufträge stehen unter <a href="#auftraege">Aufträge</a>.</p></div>`;
}

/* Pokopia (Serebii): Nummer im Pokédex und Spezialitäten */
function pokopiaHtml(d) {
  const xs = d.pokopia || [];
  if (!xs.length) return "";
  return `<div class="box"><h2>In Pokopia</h2><table class="rows"><tbody>${xs.map((x) => `<tr><td class="hint nw">${esc(x.dex)} #${String(x.nr).padStart(3, "0")}</td>
    <td><b>${esc(x.name)}</b></td><td>${x.spezial.map((s) => `<span class="cls">${esc(s)}</span>`).join(" ") || `<span class="hint">keine Spezialität</span>`}</td></tr>`).join("")}</tbody></table>
    <p class="hint">Spezialitäten: was das Pokémon in Pokopia für dich erledigt. Aus Serebii, Namen eigene Übersetzung.</p></div>`;
}
/* Getragene Items wilder Pokémon (PokéWiki), mit Bild und Anteil; „Elite“ nur bei Alpha-Pokémon */
function heldHtml(d) {
  const xs = d.getragen || [];
  if (!xs.length) return "";
  return `<div class="box"><h2 data-fold="held">Getragene Items</h2><table class="rows held"><tbody>${xs.map((x) => `<tr>
    <td>${x.id ? `<img class="ibild sm" src="itembild/${x.id}" alt="" loading="lazy" onerror="this.remove()">` : ""}</td><td><b>${wikiLink(x.item)}</b>${x.elite ? ` <span class="alpha" data-tip="Nur Elite-Pokémon (Alpha)">Elite</span>` : ""}</td>
    <td class="c num">${esc(x.prozent)}</td><td class="hint">${x.editionen?.length ? "nur " + esc(x.editionen.join(", ")) : ""}</td></tr>`).join("")}</tbody></table>
    <p class="hint">Trägt ein wildes Pokémon mit dieser Wahrscheinlichkeit; du bekommst das Item, wenn du es fängst (oder mit Raub, Trick). Aus ${esc(xs[0].quelle || "PokéWiki")}.</p></div>`;
}
/* Entwicklungskette als Baum: jeder Ast eine Zeile; ein zweiter Ast beginnt unter seiner Stufe (Waumpel → Schaloko
   → Papinella, darunter → Panekon → Pudox) */
function evoHtml(list, cur) {
  if (list.length < 2) return "";
  const kids = {}, cells = [];
  list.forEach((e) => { (kids[e.von] ||= []).push(e); });
  let row = 1;
  const walk = (e, dep) => {
    if (dep) cells.push(`<span class="ar" style="grid-area:${row}/${2 * dep}">→ ${esc(e.bedingungen.join(" oder ") || "")}</span>`);
    cells.push(`<a class="st${e.id === cur ? " cur" : ""}" style="grid-area:${row}/${2 * dep + 1}" href="#pokemon/${e.id}"${e.id ? ` data-hc="${e.id}"` : ""}>${img(e.id)}${esc(e.name)}</a>`);
    (kids[e.art] || []).forEach((c, i) => { if (i) row++; walk(c, dep + 1); });
  };
  list.filter((e) => !e.von || !list.some((x) => x.art === e.von)).forEach((r, i) => { if (i) row++; walk(r, 0); });
  return cells.join("");
}
/* Fangchance als eigene Karte unter der Entwicklung: offen, solange das Pokémon nicht als gefangen markiert ist */
// Pokédex-Eintrag des gewählten Spiels; bei zwei Editionen beide, mit Namen. Fehlt er im Spiel, steht dabei, woher er ist.
function dexTextHtml(d) {
  const xs = d.texte?.length ? d.texte : d.text ? [{edition: "", text: d.text}] : [];
  if (!xs.length) return "";
  return `<div class="dex">${xs.map((x, i) => `<p>${x.edition && xs.length > 1 ? `<span class="cls">${esc(x.edition)}</span> ` : ""}${esc(x.text)}${i === xs.length - 1 ? fromHtml(d) : ""}</p>`).join("")}</div>`;
}

function fromHtml(x) {
  const src = x.text_quelle ? `Quelle: ${x.text_quelle}` : "";
  if (x.text_aus) return ` <span class="cls" data-tip="${esc(`Im gewählten Spiel gibt es keinen deutschen Text; gezeigt ist der aus ${x.text_aus}. ${src}`)}">aus ${esc(x.text_aus)}</span>`;
  return src && x.text_quelle !== "PokéAPI" ? ` <span class="cls" data-tip="${esc(src)}">${esc(x.text_quelle)}</span>` : "";
}

// Forschungsaufgaben in Legenden: Arceus (PokéWiki): je Aufgabe die Stufen; jede erreichte Stufe bringt 10 Punkte,
// doppelt zählende 20, ab 100 Punkten ist der Forschungslevel 10 erreicht
function researchHtml(d) {
  const xs = d.forschung || [];
  if (!xs.length) return "";
  const pts = (a) => a.stufen.length * (a.doppelt ? 20 : 10);
  const all = xs.reduce((n, a) => n + pts(a), 0), have = xs.reduce((n, a) => n + (a.erreicht || 0) * (a.doppelt ? 20 : 10), 0);
  const calc = calcRows(xs.map((a) => [a.aufgabe, `${a.stufen.length} × ${a.doppelt ? 20 : 10} = ${pts(a)}`]).concat([["Alle Stufen", `${all} Punkte`]]));
  return `<div class="box"><h2 data-fold="research" data-tip="Aufgaben im Pokédex von Hisui. Jede erreichte Stufe bringt 10 Punkte, doppelt zählende 20. Ab 100 Punkten ist der Forschungslevel 10 erreicht.">Forschungsaufgaben</h2>
    <table class="rows"><tbody>${xs.map((a) => `<tr><td>${esc(a.aufgabe)}${a.doppelt ? ' <span class="cls tm" data-tip="Zählt doppelt: 20 statt 10 Punkte je Stufe">×2</span>' : ""}</td><td class="rst">${a.stufen.map((x, k) => `<span class="rs${k < (a.erreicht || 0) ? " on" : ""}" data-act="rsdone" data-art="${d.art}" data-nr="${a.nr}" data-k="${k + 1}"
      data-tip="${k < (a.erreicht || 0) ? (k + 1 === a.erreicht ? "Erreicht; Klick: doch nicht" : "Erreicht") : "Klick: bis hier erreicht"}">${esc(x)}</span>`).join("")}</td></tr>`).join("")}</tbody></table>
    <p class="hint"><span ${tipRef(`<b>Punkte, wenn alle Stufen erreicht sind</b>${calc}`)}>Alle Stufen: ${all} Punkte</span>, Forschungslevel 10 ab 100.${have ? ` Erreicht: <b>${have}</b> Punkte${have >= 100 ? " (Level 10)" : `, noch ${Math.min(100, all) - have > 0 ? Math.min(100, all) - have : 0} bis Level 10`}.` : " Klick auf eine Zahl hakt die Stufe ab."} Quelle: PokéWiki.</p></div>`;
}

/* 0.50: Fangchance in Legenden: Arceus mit der Formel des Spiels (Bulbapedia, Catch rate), Lage über Schalter.
   a = 0,75 × Fangrate (+10 Massenausbruch) + 30 × (Rang + KP × Status × Ball × Verhalten × Rücken × Beere) */
const FLA_BEHAV = [["Standard", 2], ["frisst (auch Beere)", 2.5], ["ruht", 2.5], ["betäubt", 3], ["schläft", 4], ["frisst Kuchen", 4],
  ["scheu oder angriffslustig", 1], ["flieht", 1]];
const FLA = Object.assign({lv: 0, alpha: false, rang: 10, beh: 0, rueck: false, unb: false, fliegt: false, beere: false, aus: false}, store.get("fangla", {}));
function fangLA(rate, ball, hp, st, o) {
  const poke = Math.min(10, Math.floor((o.lv - 1) / 10 + 1) + (o.alpha ? 4 : 0)), rank = Math.max(-5, Math.min(0, o.rang - poke + 1));
  const mult = (3 - 2 * hp) / 3 * st * ball * FLA_BEHAV[o.beh][1] * (o.rueck ? 1.75 : 1) * (o.beere ? 1.3 : 1);
  const a0 = 0.75 * rate + (o.aus ? 10 : 0) + 30 * (rank + mult), a = Math.min(255, a0);
  const b = a < 0 ? 0 : 65535 * (1 - Math.sqrt(1 - a / 255)), p = a < 0 ? 0 : Math.round(1000 * (1 - (1 - b / 65536) ** 2)) / 10;
  return {p, a: a0, b, rank, poke, mult};
}
function catchHtmlLA(d) {
  const m = d.mehr || {}, rate = m.fangrate_la ?? m.fangrate, o = FLA;
  if (!o.lv) { const lv = [...JSON.stringify(d.fundorte || "").matchAll(/"level": ?"?(\d+)/g)].map((x) => +x[1]); o.lvAuto = lv.length ? Math.min(...lv) : 20; }
  const opt = Object.assign({}, o, {lv: o.lv || o.lvAuto});
  const pc = (v) => `<span style="color:${ramp(v / 100)}">${de(v)} %</span>`;
  const cell = (b, f, hp, st, lbl) => { const r = fangLA(rate, f, hp, st, opt);
    return `<td class="c" data-s="${r.p}" ${tipRef(`<div class="tt">${esc(b[0])}, ${esc(lbl)}</div>${calcRows([
      ["Fangrate", `${rate} × 0,75`, m.fangrate_la != null ? "eigene Fangrate in Legenden: Arceus" : "Fangrate der Hauptspiele (eigene fehlt noch)"],
      o.aus ? ["Massenausbruch", "+10", ""] : null,
      ["Rang", r.rank, `dein Sternrang ${opt.rang} − Rang des Pokémon ${r.poke} + 1, zwischen −5 und 0`],
      ["KP", `×${hp ? "⅓" : "1"}`, hp ? "volle KP" : "fast keine KP"], st !== 1 ? ["Status", "×2", "Statusproblem"] : null,
      ["Ball", `×${de(f)}`, f !== b[1] ? (b[3] === "fliegt" ? "verstärkt: Pokémon fliegt" : "verstärkt: unbemerkt oder im Kampf") : ""],
      ["Verhalten", `×${de(FLA_BEHAV[o.beh][1])}`, FLA_BEHAV[o.beh][0]], o.rueck ? ["Rücken", "×1,75", "Wurf in den Rücken"] : null,
      o.beere ? ["Beere", "×1,3", "frisst eine Himmihbeere (Razz Berry)"] : null])}
      <div class="tt">Fangwert a</div><div>0,75 × ${rate}${o.aus ? " + 10" : ""} + 30 × (${r.rank} + ${de(Math.round(r.mult * 100) / 100)}) = <b style="color:#fff">${de(Math.round(r.a * 10) / 10)}</b>${r.a > 255 ? " (bis 255)" : ""}</div>
      <div class="tt">Chance je Wurf</div>${r.a < 0 ? "<div>a unter 0: kein Fang möglich</div>" : `<div>b = 65535 × (1 − √(1 − a/255)) = ${Math.round(r.b)}; zwei Proben, eine muss gelingen</div>`}
      <div class="tt">Ergebnis</div><div><b>${de(r.p)} %</b></div>`)}>${pc(r.p)}</td>`; };
  const rows = (m.fang_hisui || []).map((b) => { const boost = (b[3] === "unbemerkt" && o.unb) || (b[3] === "fliegt" && o.fliegt), f = boost ? b[2] : b[1];
    return `<tr><td>${esc(b[0])}${boost && b[2] !== b[1] ? ` <span class="hint">verstärkt</span>` : ""}</td>${cell(b, f, 1, 1, "volle KP")}${cell(b, f, 0, 1, "1 KP")}${cell(b, f, 0, 2, "1 KP, Statusproblem")}</tr>`; }).join("");
  const ck = (k, t, tip) => `<label data-tip="${esc(tip)}"><input type="checkbox" data-fla="${k}"${o[k] ? " checked" : ""}> ${t}</label>`;
  return `<details class="box" id="fangla"${isCaught(d.id) ? "" : " open"}><summary><h2>Fangchance</h2><span class="hint">Fangrate ${rate}${m.fangrate_la != null && m.fangrate_la !== m.fangrate ? ` (Hauptspiele ${m.fangrate})` : ""}${isCaught(d.id) ? " · schon gefangen" : ""}</span></summary>
    <div class="bar fla"><label data-tip="Level des wilden Pokémon. Sein Rang: ⌊(Level − 1)/10 + 1⌋">Level <input type="number" min="1" max="100" data-fla="lv" value="${opt.lv}" style="width:4.2em"></label>
      ${ck("alpha", "Alpha", "Alpha-Pokémon: Rang +4 (höchstens 10)")}
      <label data-tip="Dein Sternrang im Galaktik-Team. Liegt er unter dem Rang des Pokémon, sinkt die Chance">Sternrang <select data-fla="rang">${[...Array(11).keys()].map((i) => `<option${i === o.rang ? " selected" : ""}>${i}</option>`).join("")}</select></label>
      <label>Verhalten <select data-fla="beh">${FLA_BEHAV.map(([t, v], i) => `<option value="${i}"${i === o.beh ? " selected" : ""}>${t} (×${de(v)})</option>`).join("")}</select></label></div>
    <div class="bar fla">${ck("rueck", "in den Rücken", "Wurf in den Rücken: ×1,75, gilt auch im Kampf danach")}${ck("unb", "unbemerkt", "Pokémon hat dich nicht bemerkt (oder Kampf): Schwer-, Zentner- und Tonnenball verstärkt")}
      ${ck("fliegt", "fliegt", "Pokémon fliegt: Feder-, Flügel- und Düsenball verstärkt (Federball laut Bulbapedia nur bei bestimmten fliegenden Begegnungen)")}${ck("beere", "Himmihbeere", "Pokémon frisst eine Himmihbeere (Razz Berry): ×1,3")}${ck("aus", "Massenausbruch", "Massenausbruch: +10 auf den Fangwert")}</div>
    <table class="rows sort catch"><thead><tr>${th("Ball")}${thc("volle KP")}${thc("1 KP", "Ein einziger KP übrig: dreimal so gut wie volle KP")}${thc("1 KP, Status", "Jedes Statusproblem: ×2")}</tr></thead><tbody>${rows}</tbody></table>
    <p class="hint">Je Wurf, mit der Formel von Legenden: Arceus (Quelle: Bulbapedia). Der Urball fängt immer.</p></details>`;
}
document.addEventListener("change", (e) => {
  const k = e.target.dataset?.fla;
  if (!k || !DETAIL) return;
  FLA[k] = e.target.type === "checkbox" ? e.target.checked : +e.target.value;
  const {lvAuto, ...keep} = FLA; store.set("fangla", keep);
  const box = $("#fangla");
  if (box) { const open = box.open; box.outerHTML = catchHtmlLA(DETAIL); $("#fangla").open = open; }
});
function catchHtml(d) {
  const m = d.mehr || {};
  if (!m.fangen) return "";                                  // ohne Fangen (Profil: fangformel keine) schickt der Server nichts
  if (m.fang_hisui) return catchHtmlLA(d);                   // eigene Formel (Profil: fangformel hisui)
  const pc = (v) => `<span style="color:${ramp(v / 100)}">${String(v).replace(".", ",")} %</span>`;
  const art = PROFIL().fangformel;                           // legenden, letsgo, gen12: die Tabelle gibt nur eine Richtung
  return `<details class="box"${isCaught(d.id) ? "" : " open"}><summary><h2>Fangchance</h2><span class="hint">Fangrate ${m.fangrate}${isCaught(d.id) ? " · schon gefangen" : ""}</span></summary>
    <table class="rows sort catch"><thead><tr>${th("Ball")}${thc("volle KP")}${thc("1 KP", "Ein einziger KP übrig: der beste Fall, etwa dreimal so gut wie volle KP. Die Chance steigt gleichmäßig, je weniger KP übrig sind, ohne Schwellen")}${thc("1 KP, gelähmt", "Paralyse, Vergiftung und Verbrennung: Fangrate ×1,5")}${thc("1 KP, schlafend", `Schlaf und Einfrieren: Fangrate ×${m.schlaf_faktor || 2.5}`)}</tr></thead>
    <tbody>${m.fangen.map((f) => { const ct = (lbl, sh, st, stl, v, col) => f.faktor != null ? tipRef(catchTip(m, f, lbl, sh, st, stl, v, col)) : "";
      return `<tr><td>${esc(f.ball)}</td><td class="c" data-s="${f.voll}" ${ct("volle KP", 1, 1, "", f.voll, "voll")}>${pc(f.voll)}</td><td class="c" data-s="${f.rot}" ${ct("1 KP", 0, 1, "", f.rot, "rot")}>${pc(f.rot)}</td>
        <td class="c" data-s="${f.status ?? ""}" ${f.status != null ? ct("1 KP", 0, 1.5, "gelähmt, vergiftet oder verbrannt", f.status, "status") : ""}>${f.status != null ? pc(f.status) : "–"}</td>
        <td class="c" data-s="${f.schlaf}" ${ct("1 KP", 0, +String(m.schlaf_faktor || 2.5).replace(",", "."), "schlafend oder eingefroren", f.schlaf, "schlaf")}>${pc(f.schlaf)}</td></tr>`; }).join("")}</tbody></table>
    <p class="hint">Je Wurf, ohne kritischen Fang und ohne Boni durch Level oder Runde. Statusprobleme helfen: Schlaf und Einfrieren am meisten, Paralyse, Gift und Verbrennung etwas${art === "legenden" ? ". Die Legenden-Spiele rechnen anders (Wurf in den Rücken, Level, Alpha); die Werte geben nur eine Richtung."
      : art === "letsgo" ? ". Let’s Go rechnet anders (siehe unten); die Werte geben nur eine Richtung."
      : art === "gen12" ? ". Generation 1 und 2 rechnen anders; die Werte geben nur eine Richtung." : "."}</p>${wissenHtml(d.spielwissen)}</details>`;
}
/* Gepflegtes Spielwissen (extra/spielwissen.json), bisher Let’s Go: Fangen ohne Kampf und Fang-Kombo */
const miniTable = (head, rows) => `<table class="rows">${head ? `<tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr>` : ""}${rows.map((r) => `<tr>${r.map((c, i) => `<td${i && String(c).length < 14 ? ' class="c"' : ""}>${esc(c)}</td>`).join("")}</tr>`).join("")}</table>`;
const quellenHtml = (q) => q?.length ? `<p class="hint">Quellen: ${q.map(([n, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)}</a>`).join(" · ")}</p>` : "";
function wissenHtml(w) {
  if (!w || (!w.fangen && !w.kombo)) return "";
  const f = w.fangen, k = w.kombo;
  return `${f ? `<h3>Fangen in diesem Spiel</h3><p class="hint">${esc(f.text)}</p><div class="cols2">
      <div>${miniTable(["Wirkt", "Faktor"], f.faktoren)}</div>
      <div>${miniTable(["Wurfkreis", "Fangen"], f.ringe)}<p class="hint">${esc(f.ring_text)}</p></div></div>` : ""}
    ${k ? `<details class="sub"><summary>Fang-Kombo: schillernde, seltene und perfekte Pokémon</summary><p class="hint">${esc(k.text)}</p>
      ${miniTable(k.schillernd_kopf, k.schillernd)}
      <div class="cols2"><div>${miniTable(["Kombo", k.dvs_text], k.dvs)}</div><div>${miniTable(["Kombo", k.selten_text], k.selten)}</div></div>
      <p class="hint">${esc(k.ep_text)}</p></details>` : ""}${quellenHtml(w.quellen)}`;
}
/* Partner-Pikachu und Partner-Evoli (Let’s Go): eigene Techniken und die Geheimen Techniken */
function partnerHtml(d) {
  const w = d.spielwissen, p = w?.partner;
  if (!p) return "";
  const t = w.techniken;
  return `<div class="box"><h2>Partner-Techniken</h2><p class="hint">${esc(p.text)}</p>
    <table class="rows"><tr><th>Attacke</th><th>Typ</th><th class="c">Stärke</th><th>Wirkung</th></tr>${p.attacken.map((m) => `<tr><td><b>${esc(m.name)}</b></td><td>${tchip(m.typ)}</td>
      <td class="c">${m.staerke ? powCell(m.staerke) : `<span data-tip="hängt von der Freundschaft ab, bis 102">Freundschaft</span>`}</td><td class="hint">${esc(m.kurz || "")}</td></tr>`).join("")}</table>
    ${t ? `<h3>Geheime Techniken</h3><p class="hint">${esc(t.text)}</p>${miniTable(["Technik", "Wirkung", "So bekommst du sie"], t.liste)}` : ""}${quellenHtml(w.quellen)}</div>`;
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
  return rows.length ? `<details class="mehr"><summary><h3 style="display:inline">Mehr Details</h3></summary>
    <div class="kv">${rows.map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join("")}</div></details>` : "";
}
// Farben für Werte: Stärke (bis 150), Genauigkeit (ab 70), Wertung (bis 160), von Rot nach Grün
const ramp = (x) => `hsl(${Math.max(0, Math.min(1, x)) * 125} 62% 40%)`;
const powCell = (v) => v ? `<span style="color:${ramp((v - 30) / 100)}">${v}</span>` : "–";
// Stärke, in Legenden: Arceus darunter Kraftstil / Tempostil (aus dem PokéWiki)
const powStil = (m) => powCell(m.staerke) + (m.abkling != null ? ` <span class="stil" data-tip="${esc(`Abklingzeit in Legenden: Z-A: ${m.abkling} Sekunden, bis die Attacke wieder einsetzbar ist (Serebii).\nHohe Initiative verkürzt sie, etwa 3 Sekunden je 100 Punkte über 25, nie unter 3; Müdigkeit verdoppelt sie.`)}">${m.abkling} s</span>` : "") + (m.kraft != null || m.tempo != null
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
  const mrow = (m, status = false) => `<tr class="${m.jetzt === false ? "off" : ""}${mine.includes(m.id) ? " sel" : ""}"><td data-s="${esc(m.name)}"><span${m.text ? ` data-tip="${esc(m.text)}"` : ""}>${wikiLink(m.name)}</span>${m.geaendert ? ' <span class="cls" data-tip="Werte in diesem Spiel anders als heute">Spielwert</span>' : ""}${m.tm_fehlt ? ` <span class="cls tmfehlt" data-tip="${esc(`Nur per ${m.tm_fehlt}, und die hast du in diesem Spiel nicht abgehakt (Items › Maschinen); der Vorschlag lässt sie weg`)}">${esc(m.tm_fehlt)} fehlt</span>` : ""}${moveMarks(m)}</td>
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
  $("#mbox").innerHTML = `<h2 data-fold="moves">Attacken${A.spiel_name ? " in " + esc(A.spiel_name) : ""}</h2>
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
    <div class="fsec"><h3 data-fold="rank">Schadens-Attacken nach Wertung</h3>
    <p class="hint">Wertung = Stärke × Genauigkeit × Eigentyp-Bonus × passender Angriffswert, mit Zu- und Abschlägen (Aussetzen, Anlauf, Rückstoß, Werte senken, Vorrang). Spalten zum Sortieren anklicken; deine Auswahl ist hinterlegt.</p>
    <div class="scroll"><table class="sort fixed mvt">${MVCOLS}<thead><tr>${th("Attacke")}${thc("Typ")}${thc("Klasse")}${thc("Stärke")}${thc("Gen.", "Genauigkeit in Prozent; – trifft immer")}${thc("Wertung")}${thc("Weg", "Wie das Pokémon die Attacke lernt")}${th("Gründe", "", true)}<th></th></tr></thead>
      <tbody>${A.attacken.map((m) => mrow(m)).join("") || `<tr><td colspan="9" class="hint">Keine Lernliste.</td></tr>`}</tbody></table></div></div>
    ${A.status.length ? `<details id="stmv"${store.get("stMvOpen", true) ? " open" : ""}><summary>Status-Attacken (${A.status.length})</summary><div class="scroll"><table class="sort fixed mvt">${MVCOLS}<thead><tr>${th("Attacke")}${thc("Typ")}${thc("Klasse")}${thc("Stärke")}${thc("Gen.")}${thc("Wertung", "Status-Attacken haben keine Wertung")}${thc("Weg")}${th("Wirkung", "", true)}<th></th></tr></thead>
      <tbody>${A.status.map((m) => mrow(m, true)).join("")}</tbody></table></div></details>` : ""}`;
  $("#stmv")?.addEventListener("toggle", (e) => store.set("stMvOpen", e.target.open));   // 0.56.2: merkt sich wie die anderen Karten
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

