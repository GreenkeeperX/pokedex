/* Pokédex-Oberfläche, Teil 5 von 10: Team, Gegner, Attacken.
   Die Teile lädt index.html der Reihe nach; sie teilen sich die globalen Namen (docs/oberflaeche.md). */
"use strict";
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
const TSORT = {nr: ["Nummer", (r) => (r.dex || 0) * 10000 + (r.nr ?? r.art)], level: ["Level", (r, d) => -(d.level || 0)], summe: ["Basiswerte", (r) => -r.summe],
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
      <button data-act="tsaveas">Speichern unter …</button><button data-act="trename">Umbenennen</button><button class="dangerline" data-act="tdel" data-tip="Gespeichertes Team löschen (mit Rückfrage)">Löschen</button>`
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
  el.innerHTML = S.favs.length ? `<div class="list favlist">${S.favs.map((r) => monCard(r)).join("")}</div>`
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
  const where = (x) => x.slot === null || x.slot === undefined ? "auf einen freien Platz" : `statt ${esc(x.statt)} <span class="nw">(Platz ${x.slot + 1})</span>`;
  const line = (x, extra = "") => `<div class="imp diff" data-id="${x.id}" data-hc="${x.id}" draggable="true"><a href="#pokemon/${x.id}">${img(x.id)}</a><div class="grow"><b>${esc(x.name)}</b> ${favStar(x.id)}<button class="favstar teamck" data-act="${x.slot === null || x.slot === undefined ? "teamadd" : "altpick"}" data-id="${x.id}" data-slot="${x.slot ?? ""}"
      data-tip="${x.slot === null || x.slot === undefined ? "Ins Team (auf einen freien Platz)" : `Ins Team: fragt, wen es ersetzt (empfohlen: ${esc(x.statt)})`}">${icon("team")}</button><div class="tl">${tchips(x.typen)}</div>
    <div class="why">${extra}<b class="plus">+${x.plus}</b> Teamwertung ${where(x)}</div></div></div>`;   // 0.49: Häkchen hinter dem Stern statt „Tauschen“
  el.innerHTML = `<p class="hint">${S.caught.size} gefangen in ${esc(gameName())}.</p>
    <div class="fsec"><h3 data-fold="talt" data-tip="Ein Tausch mit einem Mitglied (oder ein freier Platz) hebt die Teamwertung jetzt">Bessere Alternative</h3>
    ${r.alternativen.map((x) => line(x)).join("") || `<p class="hint">Nichts aus deiner Sammlung hebt das Team im Moment.</p>`}</div>
    <div class="fsec"><h3 data-fold="tpot" data-tip="Noch nicht voll entwickelt (gefangen oder schon im Team): die Endstufe würde das Team deutlich mehr heben als das Pokémon heute. Je Endstufe zählt die weiteste Stufe, die du hast">Langfristig mehr Potential</h3>
    ${r.potential.map((x) => `<div class="imp diff" data-id="${x.id}" data-hc="${x.id}" draggable="true"><a href="#pokemon/${x.id}">${img(x.id)}</a><span class="arrow">→</span><a href="#pokemon/${x.wird.id}" data-hc="${x.wird.id}">${img(x.wird.id)}</a>
      <div class="grow"><b>${esc(x.name)}</b> → <b>${esc(x.wird.name)}</b> ${favStar(x.wird.id)}<div class="tl">${tchips(x.wird.typen)}</div><div class="why">als ${esc(x.wird.name)}: <b class="plus">+${x.plus}</b> Teamwertung
        ${x.im_team ? `auf seinem Platz (${x.slot + 1}), ${esc(x.name)} steht schon im Team` : where(x)}</div></div></div>`).join("")
      || `<p class="hint">Nichts aus deiner Sammlung, das entwickelt deutlich mehr bringt.</p>`}</div>
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
      <div class="tslots" id="slots"><p class="hint">Lädt …</p></div>
      <details class="sdbox" id="sdbox"><summary>Team als Text <span class="hint" data-tip="Das übliche Format, um Teams weiterzugeben: Pokémon Showdown (Kampf-Simulator im Browser), PokePaste-Links, Smogon und Foren lesen es">zum Weitergeben oder Einlesen, im Format von Pokémon Showdown</span>
          <button class="small" data-act="sdcopy2" data-tip="Das aktuelle Team als Text in die Zwischenablage, etwa für Showdown, PokePaste oder eine Nachricht">Team kopieren</button></summary>
        <p class="hint">Pokémon Showdown ist der bekannte Kampf-Simulator im Browser. Sein Textformat ist der übliche Weg, Teams weiterzugeben:
          Smogon-Analysen, PokePaste-Links und Foren nutzen es, und Showdown liest es über „Import/Export“ ein. Hier holst du ein Team aus so einem Text
          (Pokémon, Item, Fähigkeit, Wesen, EVs/IVs, Attacken; englisch oder deutsch) oder gibst deins als Text weiter.</p>
        <textarea id="sdtext" rows="12" spellcheck="false" placeholder="Garchomp @ Choice Scarf&#10;Ability: Rough Skin&#10;EVs: 252 Atk / 4 SpD / 252 Spe&#10;Jolly Nature&#10;- Earthquake"></textarea>
        <div class="bar"><button data-act="sdexp" data-tip="Das aktuelle Team als Text">Aus dem Team</button>
          <button class="primary" data-act="sdimp" data-tip="Ersetzt das aktuelle Team">Als Team übernehmen</button>
          <button data-act="sdcopy">Kopieren</button><span id="sdnote" class="hint"></span></div></details>
      <details class="favd dropmark" data-drop="fav" open><summary>${icon("fav")} Favoriten in ${esc(gameName())} <span id="favn"></span> <span class="hint">zum schnellen Tauschen auf einen Platz ziehen; hierher ziehen macht zum Favoriten</span></summary><div id="favs"></div></details></div>
    ${LA() && S.team.ids.length ? `<details class="box" id="elteam"${store.get("elTeamOpen", S.team.details.some((d) => d?.el)) ? " open" : ""}><summary><h2 style="display:inline">Effort Levels</h2>
        <span class="hint">Stand und Ziel je Mitglied, was dem Team fehlt</span></summary><div id="eltbody"><p class="hint">Lädt …</p></div></details>` : ""}
    <details class="box" id="findbox"${store.get("findOpen", true) ? " open" : ""}><summary><h2 style="display:inline">Passende Pokémon finden</h2>
      <span class="hint">bestes Team suchen, Vorschläge für den nächsten Platz</span></summary>
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
    </details>
    <div class="cols tcols">
      <div class="box"><h2 data-fold="tev">Bewertung</h2><div id="ev"><p class="hint">Lädt …</p></div></div>
      <div class="box"><h2 data-fold="timp">Verbesserungen</h2><div id="imp"></div></div>
      <div class="box dropmark" data-drop="gef"><h2 data-fold="tgef">${icon("ball")} Aus deiner Sammlung</h2><div id="gef"><p class="hint">Lädt …</p></div></div>
    </div>
    <div class="box"><h2 data-fold="tmu">Gegen Gegner</h2>
      <div class="bar"><div class="ac grow"><input id="foe" type="search" placeholder="Gegner hinzufügen (bis zu 6, etwa die Pokémon eines Arenaleiters)" style="width:100%"></div>
        <button data-act="foeclear" id="foeclr"${S.foes.length ? "" : " hidden"}>Gegner leeren</button></div>
      <div id="trpick"></div>
      <div id="mu"><p class="hint">Wähle Gegner: das Tool zeigt, wer aus deinem Team gegen wen im Vorteil ist.</p></div>
      ${!BATTLE() && GEN() >= 3 ? `<details class="sub" id="calcbox"${store.get("calcOpen", false) ? " open" : ""}><summary><h3 style="margin:0">Schadensrechner</h3>
        <span class="hint">wie viel eine Attacke deines Teams den Gegnern abzieht</span></summary><div id="calc"><p class="hint">Lädt …</p></div></details>` : ""}</div>`;
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
  trainerPick();
  const cb = $("#calcbox");
  if (cb) { cb.addEventListener("toggle", () => { store.set("calcOpen", cb.open); if (cb.open) calcBox(); }); if (cb.open) calcBox(); }
  $("#findbox")?.addEventListener("toggle", (e) => store.set("findOpen", e.target.open));
  if ($("#elteam")) { $("#elteam").addEventListener("toggle", (e) => store.set("elTeamOpen", e.target.open)); elTeam(); }
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
      ${favStar(id)}
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
    ${(ev.tera || []).length ? `<div class="note tera" data-tip="Nur Verteidigung: der Tera-Typ ersetzt beim Terakristallisieren die eigenen Typen. Wählen auf der Detailseite.">${ev.tera.map((x) => `<div><b>${esc(x.name)}</b> mit Tera ${tchip(x.tera)}${x.eigentyp ? ` <span class="muted">(Eigentyp, stärkere Attacken)</span>` : ""}: ${x.weg.length ? `nimmt Schwächen gegen ${tchips(x.weg)}` : "nimmt keine Schwäche"}${x.neu.length ? `, neu schwach gegen ${tchips(x.neu)}` : ""}</div>`).join("")}</div>` : ""}
    <p class="hint">${ev.physisch} physisch, ${ev.speziell} speziell · schnell: ${esc(ev.schnell.join(", ") || "keiner")}</p>
    <details><summary>Typwirkung je Mitglied</summary><div class="scroll"><table class="matrix" id="matrix"><tr><th></th>${ms.map((m, i) => `<th data-hc="${m.id}" data-c="${i + 1}" data-pc="${i + 1}">${img(m.id)}</th>`).join("")}</tr>
      ${Object.keys(S.types).filter((a) => ev.matrix[ms[0].id]?.[a] !== undefined).map((a) => `<tr data-r="${a}"><th class="r" data-pr="${a}">${tchip(a)}</th>${ms.map((m, i) => { const f = ev.matrix[m.id][a]; return `<td data-c="${i + 1}" data-tip="${esc(`${tname(a)} gegen ${m.name}: ×${fl(f)}`)}"><span class="f ${fcls(f)}">${f === 1 ? "" : fl(f)}</span></td>`; }).join("")}</tr>`).join("")}</table></div>
      <p class="hint">Zeile: angreifender Typ, Spalte: Mitglied. Klick hält Zeile oder Spalte fest.</p></details>`;
  crossTable($("#matrix"), MPIN, null, false);      // 0.49: ohne Markier-Zeichen, Klick auf Kopf oder Zelle genügt
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
/* Trainer als Gegner: Arenaleiter, Top Vier, Champs und Rivalen des Spiels (PokéWiki). Damit die vielen Teams nicht
   erschlagen: eine Rolle zur Zeit, nach Level sortiert (etwa die Reihenfolge im Spiel), Rückkämpfe erst auf Wunsch;
   die Suche findet Trainer, Orte und Pokémon über alle Rollen. Gewählt: sein Team wird zu den Gegnern (mit Level und
   Attacken für die Rechnung) */
const TRAINERS = {};
const foeTrainer = () => { const t = store.get("foeTrainer:" + S.game, null); return t && S.foes.length && S.foes.every((id) => t.team.some((m) => m.id === id)) ? t : null; };
const foeMember = (id) => foeTrainer()?.team.find((m) => m.id === id) || null;
const trTip = (t) => [t.name + (t.titel ? " · " + t.titel : ""), t.hinweis, ...t.team.map((m) => `${m.name}${m.lvl ? " Lv " + m.lvl : ""}${m.item ? " · " + m.item : ""}${m.attacken.length ? "\n   " + m.attacken.join(", ") : ""}`)].filter(Boolean).join("\n");
async function trainerPick(keepOpen) {
  const el = $("#trpick"), g = S.game;
  if (!el) return;
  const d = TRAINERS[g] || (TRAINERS[g] = await api("/api/trainer?" + qs({spiel: g})).catch(teil("Trainer", {trainer: [], rollen: []})));
  if (!$("#trpick") || S.game !== g) return;
  if (!d.trainer.length) { el.innerHTML = ""; return; }
  const o = Object.assign({rolle: d.rollen[0], rk: false}, store.get("trOpt", {}));
  if (!d.rollen.includes(o.rolle)) o.rolle = d.rollen[0];
  const cur = foeTrainer(), wasOpen = keepOpen ?? el.querySelector("details")?.open ?? false;
  const q = (el.querySelector("#trq")?.value || "").trim().toLowerCase();
  const n = (r) => d.trainer.filter((t) => t.rolle === r && (o.rk || !t.rueckkampf)).length;
  el.innerHTML = `<details class="trp"${wasOpen ? " open" : ""}><summary>Trainer als Gegner: <b>${cur ? esc(cur.name) + (cur.titel ? ` <span class="hint">${esc(cur.titel)}</span>` : "") : "wählen"}</b>
      ${cur ? `<button class="small" data-trx="1" data-tip="Trainer und seine Pokémon als Gegner entfernen">✕ entfernen</button>
      <span class="hint">anderen Trainer: aufklappen und anklicken</span>` : ""}
      <span class="hint">${d.trainer.length} Teams aus Arenen, Top Vier, Champs, Rivalen und von Routen</span></summary>
    <div class="bar"><span class="seg">${d.rollen.map((r) => `<button class="${r === o.rolle && !q ? "on" : ""}" data-trrolle="${esc(r)}">${esc(r)} <span class="hint">${n(r)}</span></button>`).join("")}</span>
      <input id="trq" type="search" placeholder="Trainer, Ort oder Pokémon" value="${esc(q)}" style="width:200px">
      <label data-tip="Rückkämpfe und weitere Kämpfe derselben Trainer zeigen"><input type="checkbox" id="trrk"${o.rk ? " checked" : ""}> Rückkämpfe</label></div>
    <div class="trgrid" id="trgrid"></div></details>`;
  const grid = () => {
    const ql = ($("#trq")?.value || "").trim().toLowerCase();
    const xs = d.trainer.filter((t) => ql ? [t.name, t.titel, t.hinweis, ...t.team.map((m) => m.name)].join(" ").toLowerCase().includes(ql) && (o.rk || !t.rueckkampf)
      : t.rolle === o.rolle && (o.rk || !t.rueckkampf));
    $("#trgrid").innerHTML = xs.slice(0, 120).map((t) => `<button class="trc${cur && cur.id === t.id ? " on" : ""}" data-act="trpick" data-id="${t.id}" data-tip="${esc(trTip(t))}">
        <span class="trn"><b>${esc(t.name)}</b>${t.level ? `<span class="hint">Lv ${t.level}</span>` : ""}</span>
        <span class="hint trt">${esc(t.titel || t.rolle)}</span><span class="trm">${t.team.map((m) => img(m.id)).join("")}</span></button>`).join("")
      + (xs.length > 120 ? `<p class="hint">… und ${xs.length - 120} weitere: die Suche findet sie (Ort, Trainer oder Pokémon).</p>` : "")
      || `<p class="hint">Nichts gefunden.</p>`;
    $$("#trpick [data-trrolle]").forEach((b) => b.classList.toggle("on", !ql && b.dataset.trrolle === o.rolle));
  };
  grid();
  el.querySelector("[data-trx]")?.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation();
    S.foes = []; store.set("foes", S.foes); store.set("foeTrainer:" + S.game, null); VPIN.c = null; trainerPick(); matchup();
  });
  $("#trq").addEventListener("input", grid);
  $$("#trpick [data-trrolle]").forEach((b) => b.addEventListener("click", () => { o.rolle = b.dataset.trrolle; store.set("trOpt", o); $("#trq").value = ""; grid(); }));
  $("#trrk").addEventListener("change", (e) => { o.rk = e.target.checked; store.set("trOpt", o); trainerPick(true); });
}
function pickTrainer(id) {
  const t = (TRAINERS[S.game]?.trainer || []).find((x) => x.id === id);
  if (!t) return;
  S.foes = [...new Set(t.team.map((m) => m.id))].slice(0, 6);
  store.set("foes", S.foes);
  store.set("foeTrainer:" + S.game, {id: t.id, name: t.name, titel: t.titel, team: t.team});
  VPIN.c = null;
  trainerPick(false);
  matchup();
}

async function matchup() {
  const box = $("#mu");
  if (!box) return;
  $("#foeclr")?.toggleAttribute("hidden", !S.foes.length);    // auch nach der Wahl eines Trainers (ohne neuen Aufbau)
  if (!S.foes.length) { box.innerHTML = `<p class="hint">Wähle Gegner: das Tool zeigt, wer aus deinem Team gegen wen im Vorteil ist.</p>`; return; }
  const foeCard = (id, r) => { const fm = foeMember(id);
    return `<div class="foe" draggable="true" data-foe="${id}" data-hc="${id}">${img(id, "", true)}<b>${esc(r?.name || "#" + id)}</b>${fm?.lvl ? ` <span class="hint">Lv ${fm.lvl}</span>` : ""}<div>${tchips(r?.typen || [])}</div>
    ${fm?.attacken?.length ? `<div class="hint foeatk">${esc(fm.attacken.join(", "))}</div>` : ""}
    <button class="small x" data-act="foedel" data-id="${id}" data-tip="Gegner entfernen">✕</button></div>`; };
  if (!S.team.ids.length) { box.innerHTML = `<div class="foes">${S.foes.map((id) => foeCard(id, ROWS[id])).join("")}</div><p class="hint">Erst ein Team zusammenstellen.</p>`; return; }
  const miss = S.foes.filter((id) => !ROWS[id]?.werte);
  const [r, extra] = await Promise.all([api("/api/team/gegner", {spiel: S.game, ids: S.team.ids, gegner: S.foes, details: S.team.details,
      gegner_attacken: Object.fromEntries((foeTrainer()?.team || []).map((m) => [m.id, m.attacken]))}),
    miss.length ? api("/api/team/bewerten", {spiel: S.game, ids: miss, kurz: 1}) : null]);
  (extra?.mitglieder || []).forEach((m) => { ROWS[m.id] = Object.assign(ROWS[m.id] || {}, m); });
  if (!$("#mu")) return;
  r.einzeln.forEach((x) => { if (x.gegner.id) ROWS[x.gegner.id] = Object.assign(ROWS[x.gegner.id] || {}, {id: x.gegner.id, name: x.gegner.name, typen: x.gegner.typen}); });
  const verdict = Object.fromEntries(r.einzeln.flatMap((x) => x.rows.map((row) => [`${row.id}:${x.gegner.id}`, row])));
  const seen = new Set();
  box.innerHTML = `<div class="foes">${r.einzeln.map((x) => foeCard(x.gegner.id, ROWS[x.gegner.id])).join("")}</div>
    ${r.ohne_antwort.length ? `<div class="note warn">Niemand im Team ist klar im Vorteil gegen: ${esc(r.ohne_antwort.join(", "))}</div>` : `<div class="note go">Gegen jeden Gegner hast du mindestens einen guten Kandidaten.</div>`}
    <div class="scroll"><table class="vs" id="vs" data-rowpin="0"><thead><tr><th class="corner vsteam" data-c="0" data-pc="0" data-tip="Spalte deines Teams markieren">Dein Team</th>${r.einzeln.map((x, i) => `<th class="foeh" data-c="${i + 1}" data-pc="${i + 1}" data-hc="${x.gegner.id}">${img(x.gegner.id)}<div>${esc(x.gegner.name)}</div></th>`).join("")}</tr></thead><tbody>
      ${r.uebersicht.filter((m) => !seen.has(m.id) && seen.add(m.id)).map((m, k) => `<tr data-r="${k}"><th class="r" data-pr="${k}" data-c="0" data-hc="${m.id}">${img(m.id)} ${esc(m.name)}</th>${r.einzeln.map((x, i) => { const v = verdict[`${m.id}:${x.gegner.id}`], u = VERDICT[v.urteil];
        return `<td data-c="${i + 1}" class="v-${v.urteil}" data-tip="${esc(`${m.name} gegen ${x.gegner.name}: ${u[1]}\n${v.gruende.map((g) => "· " + g).join("\n")}`)}">${u[0]}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div>
    <p class="hint">Vorteil: teilt mehr aus, als es einsteckt (Typen und Initiative). Nachteil: steckt mehr ein, als es austeilt. Die Attacken des Gegners zählen über seine Typen (beim Team eines Trainers über seine echten Attacken), deine über die gewählten Attacken; eine Attacke ohne Eigentyp-Bonus (×1,5) zählt dabei ein Drittel weniger. Zelle hovern für die Rechnung; Klick hält Zeile oder Spalte fest. Gegner lassen sich oben per Ziehen umsortieren.</p>`;
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
    $("#mv").innerHTML = `<div class="box scroll sticky"><table class="sort fixed lines" style="min-width:1100px"><colgroup><col style="width:21%"><col style="width:84px"><col style="width:88px"><col style="width:84px"><col style="width:68px"><col style="width:58px"><col style="width:90px"><col style="width:90px"><col style="width:82px"><col style="width:60px"><col></colgroup><thead><tr>${th("Attacke")}${thc("Typ")}${thc("Klasse")}${thc("Stärke")}${thc("Gen.", "Genauigkeit in Prozent; – trifft immer")}${thc("AP", "Angriffspunkte: so oft lässt sich die Attacke einsetzen")}
      ${thc("Vorrang", "Vorrang (Priorität): positive Werte kommen vor normalen Attacken dran, negative danach")}${thc("Wertung", "Stärke × Genauigkeit mit Zu- und Abschlägen, ohne Eigentyp-Bonus")}${thc("Lernen", "So viele Pokémon (und Formen) lernen sie im Spiel")}${thc("Gen", "Generation, seit der es die Attacke gibt")}${th("Wirkung", "Kurz-Info aus den Spieldaten; die ganze Beschreibung beim Hovern über die Zeile", true)}</tr></thead><tbody>
      ${xs.map((m) => `<tr data-r="${m.id}"><td data-s="${esc(m.name)}"><b${m.text ? ` data-tip="${esc(m.text)}"` : ""}>${wikiLink(m.name)}</b>${m.geaendert ? ' <span class="cls" data-tip="Werte in diesem Spiel anders als heute">Spielwert</span>' : ""}${m.merkmale.includes("contact") ? ' <span class="cls" data-tip="Kontakt: berührt das Ziel (löst etwa Rauhaut oder Statik aus)">Kontakt</span>' : ""}${teamMoves[m.id] ? ` <span class="cls tm" data-tip="${esc("Im Team: " + teamMoves[m.id].join(", "))}">Team${teamMoves[m.id].length > 1 ? " ×" + teamMoves[m.id].length : ""}</span>` : ""}</td><td class="c" data-s="${tname(m.typ)}">${tchip(m.typ)}</td>
        <td class="c"><span class="cls">${CLS[m.klasse]}</span></td><td class="c num" data-s="${m.staerke || 0}">${powStil(m)}</td><td class="c num" data-s="${m.genauigkeit ?? 101}">${accCell(m.genauigkeit)}</td>
        <td class="c num">${m.ap ?? ""}</td><td class="c num">${m.prio ? `<span data-tip="${m.prio > 0 ? `Vorrang +${m.prio}: kommt vor normalen Attacken` : `Vorrang ${m.prio}: kommt nach normalen Attacken`}">${m.prio > 0 ? "+" : ""}${m.prio}</span>` : ""}</td>
        <td class="c num" data-s="${m.wertung}"${m.gruende.length ? ` data-tip="${esc(m.gruende.join("\n"))}"` : ""}>${m.wertung ? `<b style="color:${scoreColor(m.wertung)}">${m.wertung}</b>` : ""}</td>
        <td class="c num">${m.lernen || ""}</td><td class="c num">${m.gen || ""}</td><td class="kurz">${kurzHtml(m.kurz || (m.klasse === 1 ? m.text || "" : ""))}</td></tr>`).join("")}</tbody></table></div>`;
    const tb = $("#mv table");
    // Name: Zeilenkopf (markiert nur die Zeile), die übrigen Zellen markieren Zeile und Spalte
    // Wirkung: Hovern und Klick markieren nur die Zeile; das Zeichen im Kopf hält die Spalte trotzdem fest
    $$("tbody tr", tb).forEach((tr) => [...tr.cells].forEach((td, i) => { td.dataset.c = i; if (td.classList.contains("kurz")) td.classList.add("nohc"); if (!i) td.dataset.pr = tr.dataset.r; }));
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
const PIN = {r: null, c: null}, MPIN = {r: null, c: null}, VPIN = {r: null, c: null}, APIN = {r: null, c: null}, IPIN = {r: null, c: null}, XPIN = {r: null, c: null};
let MSORT = {k: "", dir: ""};
