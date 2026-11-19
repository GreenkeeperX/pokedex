/* Pokédex-Oberfläche, Teil 8 von 10: Vergleich, Initiative-Liste, Kampf (Champions), Schadensrechner.
   Die Teile lädt index.html der Reihe nach; sie teilen sich die globalen Namen (docs/oberflaeche.md). */
"use strict";
/* ------------------------------------------------------------------ Vergleich */
/* Zwei Pokémon nebeneinander (#vergleich/<A>/<B>): Werte mit Unterschied, Typwirkung, Fähigkeiten, Attacken. Das jeweils
   bessere ist grün; ein Feld ohne Pokémon bietet die Suche an */
/* ------------------------------------------------------------------ Initiative-Liste */
// Initiative-Wert ab Generation 3: ((2·Basis + DV + EV/4) · Level/100 + 5) · Wesen; bis Generation 2 mit DV (0–15) und Stat Exp
function speedStat(base, lv, iv, ev, nat, gen) {
  if (gen <= 2) return Math.floor(((base + iv) * 2 + Math.floor(Math.min(255, Math.ceil(Math.sqrt(ev))) / 4)) * lv / 100) + 5;
  return natAmp(Math.floor((2 * base + iv + Math.floor(ev / 4)) * lv / 100) + 5, nat);
}
// Wesen wie im Spiel und in app/schaden.py (nature_amp): ganzzahlig × 110 / 100 oder × 90 / 100, abgerundet
const natAmp = (x, nat) => nat > 1 ? Math.floor(110 * x / 100) : nat < 1 ? Math.floor(90 * x / 100) : x;
/* Legenden: Arceus: andere Formel, Effort Level 0–10 statt EVs und DVs (wie app/effort.py) */
const EL_FAKTOR = [0, 2, 3, 4, 7, 8, 9, 14, 15, 16, 25];
// 0.57.0: wie app/effort.py: das Spiel rechnet mit einfacher Genauigkeit (Math.fround), das Wesen wirkt auf den abgerundeten Grundwert
const laStat = (base, lv, el, nat = 1) => { const f = Math.fround;
  return natAmp(Math.trunc(f(f(f(f(lv / 50) + 1) * base) / 1.5)), nat) + Math.floor(f(f(f(Math.sqrt(base) * EL_FAKTOR[el]) + lv) / 2.5) + 0.5); };
const LA = () => PROFIL().werte === "el";      // Effort Levels statt EVs und DVs (Legenden: Arceus)
/* Rechenweg einer Zelle der Initiative-Liste (Spalte k: minimal, neutral, maximal, maximal +), Einstellungen aus SPO */
let SPO = {};
const SPEED_COLS = ["minimal", "neutral", "maximal", "maximal +"];
function speedListTip(base, k) {
  const {lv, gen, wind, schal} = SPO, mults = [wind ? ["Rückenwind", 2] : null, schal ? ["Wahlschal", 1.5] : null].filter(Boolean);
  const o = LA() ? {el: k >= 2 ? 10 : 0, nat: [0.9, 1, 1, 1.1][k]}
    : gen <= 2 ? {iv: k >= 2 ? 15 : 0, ev: k >= 2 ? 65535 : 0}
    : {iv: k ? 31 : 0, ev: k >= 2 ? 252 : 0, nat: [0.9, 1, 1, 1.1][k]};
  return speedTip(gen <= 2 && !LA() ? (k >= 2 ? "voll" : "ohne") : SPEED_COLS[k], Object.assign({base, lv, gen, mults}, o));
}
function speedCols(base, lv, gen) {
  if (LA()) return [laStat(base, lv, 0, 0.9), laStat(base, lv, 0), laStat(base, lv, 10), laStat(base, lv, 10, 1.1)];
  if (gen <= 2) return [speedStat(base, lv, 0, 0, 1, gen), null, speedStat(base, lv, 15, 65535, 1, gen), null];
  return [speedStat(base, lv, 0, 0, 0.9, gen), speedStat(base, lv, 31, 0, 1, gen), speedStat(base, lv, 31, 252, 1, gen), speedStat(base, lv, 31, 252, 1.1, gen)];
}
/* ------------------------------------------------------------------ Kampf: Doppelkampf-Bewertung (nur Champions) */
async function battleView() {
  const rid = RID, t = S.team;
  main.innerHTML = `<div class="box"><div class="bar"><b>Kampf in</b> <select class="gamesel"></select>
      <a class="btn" href="#team">Team bearbeiten</a><a class="btn" href="#initiative">Initiative-Liste</a></div>
      <p class="hint">Doppelkampf-Bewertung des aktuellen Teams (${t.ids.length} Pokémon) mit den gewählten Attacken: Rollen, Flächenattacken und
        Tempo. Attacken wählst du je Platz auf der Detailseite oder übernimmst sie als Team-Text im Reiter Team.</p>
      <details class="dblhelp"${store.get("dblHelp", true) ? " open" : ""}><summary>Kurz erklärt: Kämpfen in Champions</summary>
        <ul><li><b>Doppelkampf:</b> In offiziellen Turnieren (VGC) stehen je zwei Pokémon gleichzeitig im Feld. Du meldest sechs an und wählst vor jedem Kampf vier aus; alle kämpfen auf Level 50.</li>
          <li><b>Rollen:</b> Ein gutes Doppel-Team hat Werkzeuge für bestimmte Aufgaben: sich schützen (Schutzschild), das Tempo bestimmen (Rückenwind, Bizarroraum),
            den Gegner stören (Mogelhieb, die Fähigkeit Bedroher), Angriffe auf sich ziehen (Spotlight, Wutpulver) oder den Partner stärken (Rechte Hand). Hovern über eine Rolle erklärt sie.</li>
          <li><b>Flächenattacken</b> treffen beide Gegner (mit 75 % Stärke). Manche wie Erdbeben treffen auch den eigenen Partner; dann passt ein Partner, der dagegen immun ist (etwa ein Flug-Pokémon).</li>
          <li><b>Tempo:</b> Wer zuerst angreift, gewinnt oft. Die Initiative-Liste zeigt, wer auf Level 50 schneller ist.</li>
          <li><b>Was fehlt</b> steht rot; darunter, wer im Team die passende Attacke lernen könnte.</li></ul></details>
      <div id="dbl"><p class="hint">Lädt …</p></div></div>
    <div class="box" id="calc"><h2>Schadensrechner</h2><p class="hint">Lädt …</p></div>
    <div class="box" id="log"><h2>Kampftagebuch</h2><p class="hint">Lädt …</p></div>
    <div class="box" id="usage"><h2>Häufige Gegner</h2><p class="hint">Lädt …</p></div>`;
  header();
  usageBox().then(() => { calcBox(); logBox(); });
  $("details.dblhelp").addEventListener("toggle", (e) => store.set("dblHelp", e.target.open));
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
/* Häufige Gegner aus der Nutzungsstatistik von Smogon (smogon.json, beim Abgleich geholt) */
async function usageBox() {
  const rid = RID, el = () => $("#usage");
  const u = await api("/api/smogon?" + qs({spiel: S.game})).catch(teil("Nutzungsstatistik", {rows: []}));
  if (rid !== RID || !el()) return;
  if (!u.rows.length) {
    el().innerHTML = `<h2>Häufige Gegner</h2><p class="hint">Noch keine Nutzungsstatistik. Der nächste Abgleich holt sie von Smogon (monatlich, Doppel-Format für Champions oder die aktuelle VGC-Regel).</p>`;
    return;
  }
  u.rows.forEach((r) => { if (r.id) ROWS[r.id] = Object.assign(ROWS[r.id] || {}, {id: r.id, name: r.name, typen: r.typen, werte: r.werte}); });
  const team = S.team.ids.map((id) => ROWS[id]).filter((m) => m?.typen);
  const hitF = (atk, defT) => effMul(defT.map((d) => S.chart?.[atk]?.[d] ?? 1));
  // Gefahr: welche Mitglieder ein Eigentyp des Gegners sehr effektiv trifft; Antwort: wer ihn selbst mit einem Eigentyp sehr effektiv trifft
  const threat = (r) => team.filter((m) => r.typen.some((t) => hitF(String(t), m.typen.map(String)) > 1));
  const answer = (r) => team.filter((m) => m.typen.some((t) => hitF(String(t), r.typen.map(String)) > 1));
  const names = (xs) => xs.map((m) => esc(m.name)).join(", ");
  const top = (xs, n) => xs.slice(0, n).map(([k, p]) => `${esc(k)} <span class="hint">${String(p).replace(".", ",")} %</span>`).join(", ");
  const n = store.get("usageN", 20);
  el().innerHTML = `<div class="bar"><h2 style="margin:0">Häufige Gegner</h2>
      <span class="hint grow" data-tip="Nutzungsstatistik von Smogon (Pokémon Showdown) für ${esc(u.format)}, Kämpfe ab Wertung ${u.grenze}">${esc(u.format)} · ${esc(u.monat)} · ${Number(u.kaempfe || 0).toLocaleString("de-DE")} Kämpfe</span>
      <button data-act="usagefoes" data-tip="Die sechs häufigsten als Gegner in „Gegen Gegner“ im Reiter Team">Top 6 als Gegner</button>
      <label class="hint">zeigen <select id="usagen">${[10, 20, 40, 60].map((v) => `<option${v === n ? " selected" : ""}>${v}</option>`).join("")}</select></label></div>
    <p class="hint">So spielen andere das Format: Anteil der Teams mit dem Pokémon, dazu die häufigsten Attacken, Items, Fähigkeiten und Tera-Typen.
      „Gefahr für“: Mitglieder, die ein Eigentyp des Gegners sehr effektiv trifft. „Antwort“: Mitglieder, die ihn selbst sehr effektiv treffen.</p>
    <div class="scroll sticky"><table class="rows sort usage"><thead><tr>${thc("#")}${th("Pokémon")}${thc("Anteil", "Anteil der Teams mit diesem Pokémon")}${th("Attacken", "", true)}${th("Item", "", true)}${th("Fähigkeit", "", true)}${team.length ? th("Gefahr für", "", true) + th("Antwort", "", true) : ""}</tr></thead>
    <tbody>${u.rows.slice(0, n).map((r, i) => { const th_ = r.typen.length ? threat(r) : [], an = r.typen.length ? answer(r) : [];
      return `<tr${r.id ? ` data-hc="${r.id}"` : ""}><td class="c num" data-s="${i + 1}">${i + 1}</td>
        <td data-s="${esc(r.name)}" class="nw">${r.id ? `${img(r.id, "sm")} <a href="#pokemon/${r.id}">${esc(r.name)}</a> ${tchips(r.typen)}` : esc(r.name)}</td>
        <td class="c num ushare" data-s="${r.anteil}" style="--w:${Math.min(100, r.anteil / (u.rows[0].anteil || 1) * 100).toFixed(0)}%" data-tip="In ${String(r.anteil).replace(".", ",")} % der Teams; der Balken misst am häufigsten (${String(u.rows[0].anteil).replace(".", ",")} %)">${String(r.anteil).replace(".", ",")} %</td>
        <td>${top(r.attacken, 4)}</td><td>${top(r.items, 2)}</td><td>${top(r.faehigkeiten, 1)}${r.tera.length ? `<div class="hint">Tera: ${r.tera.slice(0, 2).map(([k]) => esc(k)).join(", ")}</div>` : ""}</td>
        ${team.length ? `<td class="${th_.length >= 3 ? "stop" : th_.length === 2 ? "warn" : ""}" data-tip="${th_.length} Mitglieder trifft ein Eigentyp des Gegners sehr effektiv">${names(th_) || "–"}</td><td class="${an.length ? "go" : "stop"}">${names(an) || "keiner"}</td>` : ""}</tr>`; }).join("")}</tbody></table></div>`;
  $("#usagen").addEventListener("change", (e) => { store.set("usageN", +e.target.value); usageBox(); });
  S.usageTop = u.rows.filter((r) => r.id).slice(0, 6).map((r) => r.id);
  S.usageIds = u.rows.filter((r) => r.id).map((r) => r.id);
}
/* Kampftagebuch: Ergebnis, Gegner und Notiz je Kampf, mit Bilanz und den häufigsten Gegnern */
let LOGPICK = [];
async function logBox() {
  const rid = RID, el = () => $("#log");
  const L = await api("/api/kampftagebuch?" + qs({spiel: S.game}));
  if (rid !== RID || !el()) return;
  const need = [...new Set([...L.rows.flatMap((r) => [...r.gegner, ...r.team]), ...LOGPICK])].filter((id) => !ROWS[id]?.name);
  if (need.length) (await Promise.all(need.slice(0, 40).map((id) => api(`/api/pokemon/${id}?` + qs({spiel: S.game})).catch(teil("Namen im Kampftagebuch", null)))))
    .forEach((d) => { if (d) ROWS[d.id] = Object.assign(ROWS[d.id] || {}, {id: d.id, name: d.name, typen: d.typen}); });
  if (rid !== RID || !el()) return;
  const nm = (id) => esc(ROWS[id]?.name || "#" + id);
  const quick = (S.usageIds || []).slice(0, 24);
  const pct = L.kaempfe ? Math.round(L.siege / L.kaempfe * 100) : 0;
  el().innerHTML = `<div class="bar"><h2 style="margin:0">Kampftagebuch</h2>
      ${L.kaempfe ? `<span class="hint grow">${L.kaempfe} ${L.kaempfe === 1 ? "Kampf" : "Kämpfe"} · ${L.siege} ${L.siege === 1 ? "Sieg" : "Siege"}, ${L.kaempfe - L.siege} ${L.kaempfe - L.siege === 1 ? "Niederlage" : "Niederlagen"} (${pct} % gewonnen)</span>` : `<span class="hint grow">Noch kein Kampf eingetragen.</span>`}</div>
    <p class="hint">Nach jedem Kampf: Gegner antippen (bis sechs), Ergebnis wählen. Das aktuelle Team wird mit gespeichert. So zeigt sich mit der Zeit, gegen wen es schwer wird.</p>
    <div class="logpick">${LOGPICK.length ? LOGPICK.map((id) => `<span class="chip on" data-act="logpick" data-id="${id}" data-hc="${id}" aria-label="Entfernen">${img(id, "sm")}${nm(id)} ✕</span>`).join("") : `<span class="hint">Gegner: noch keiner gewählt</span>`}</div>
    ${quick.length ? `<div class="logquick">${quick.filter((id) => !LOGPICK.includes(id)).map((id) => `<span class="chip" data-act="logpick" data-id="${id}" data-hc="${id}" aria-label="${nm(id)}">${img(id, "sm")}</span>`).join("")}</div>` : ""}
    <div class="bar"><div class="ac"><input id="logq" type="search" placeholder="Anderen Gegner suchen" style="width:200px"></div>
      <input id="lognote" type="text" placeholder="Notiz (optional)" class="grow" maxlength="500">
      <button class="primary" data-act="logadd" data-res="sieg"${LOGPICK.length ? "" : " disabled"}>Sieg</button>
      <button data-act="logadd" data-res="niederlage"${LOGPICK.length ? "" : " disabled"}>Niederlage</button></div>
    ${L.gegner.length ? `<h3>Häufigste Gegner</h3><div class="logfoes">${L.gegner.map((g) => `<span class="lf ${g.siege * 2 < g.kaempfe ? "stop" : "go"}" data-hc="${g.id}">${img(g.id, "sm")}<span>${nm(g.id)}<br><span class="hint">${g.kaempfe} ${g.kaempfe === 1 ? "Kampf" : "Kämpfe"}, ${g.siege} ${g.siege === 1 ? "Sieg" : "Siege"}</span></span></span>`).join("")}</div>` : ""}
    ${L.rows.length ? `<details${store.get("logOpen", false) ? " open" : ""} id="logall"><summary>Alle Kämpfe</summary><table class="rows logrows"><tbody>${L.rows.map((r) => `<tr>
      <td class="nw hint">${esc(r.at.slice(0, 10).split("-").reverse().join("."))}</td><td class="${r.ergebnis === "sieg" ? "go" : "stop"}">${r.ergebnis === "sieg" ? "Sieg" : "Niederlage"}</td>
      <td>${r.gegner.map((id) => `<span data-hc="${id}">${img(id, "sm")}</span>`).join("")}</td><td class="hint">${esc(r.notiz || "")}</td>
      <td><button class="small x" data-act="logdel" data-id="${r.id}" data-tip="Eintrag löschen">✕</button></td></tr>`).join("")}</tbody></table></details>` : ""}`;
  autocomplete($("#logq"), (r) => { if (LOGPICK.length < 6 && !LOGPICK.includes(r.id)) LOGPICK.push(r.id); logBox(); });
  $("#logall")?.addEventListener("toggle", (e) => store.set("logOpen", e.target.open));
}
/* Schadensrechner: eine gewählte Attacke eines Team-Platzes gegen Gegner. Champions (Reiter Kampf, Level 50): die
   häufigsten aus der Nutzungsstatistik; sonst (Reiter Team, alle Generationen): die Gegner aus „Gegen Gegner“ mit Level.
   Dazu immer das eigene Team oder eine eigene Auswahl */
async function calcBox() {
  const CH = () => BATTLE() ? "<h2>Schadensrechner</h2>" : "";
  const rid = RID, el = () => $("#calc"), t = S.team;
  if (!el()) return;
  if (!t.ids.length) { el().innerHTML = `${CH()}<p class="hint">Das Team ist leer.</p>`; return; }
  const ev = await api("/api/team/bewerten", {spiel: S.game, ids: t.ids, details: t.details, kurz: 1});
  if (rid !== RID || !el()) return;
  (ev.mitglieder || []).forEach((m) => { ROWS[m.id] = Object.assign(ROWS[m.id] || {}, m); });
  const A = ev.attacken || {};
  const dmg = (i) => (t.details[i]?.attacken || []).filter((x) => A[x] && A[x].klasse !== 1 && A[x].staerke);
  const champ = BATTLE(), ck = champ ? "calc" : "calcT";
  const o = Object.assign({slot: 0, move: null, gegen: champ ? "smogon" : "foes", vert: "0", krit: false, flaeche: "auto", tera: "", level: "", lvv: ""}, store.get(ck, {}));
  if (!champ && o.gegen === "smogon") o.gegen = "foes";
  if (!dmg(o.slot)?.length) o.slot = t.ids.findIndex((_, i) => dmg(i).length);
  if (o.slot < 0) {
    el().innerHTML = `${CH()}<p class="hint">Wähle auf der Detailseite eines Mitglieds Schadens-Attacken, dann rechnet das hier den Schaden gegen deine Gegner aus.</p>`;
    return;
  }
  if (!dmg(o.slot).includes(o.move)) o.move = dmg(o.slot)[0];
  // Gegner: die 30 häufigsten aus der Nutzungsstatistik, das eigene Team oder eine eigene Auswahl (gemerkt je Spiel)
  const ownKey = "calcFoes:" + S.game, own = store.get(ownKey, []);
  if (o.gegen === "smogon" && !(S.usageIds || []).length) o.gegen = "team";
  if (o.gegen === "foes" && !S.foes.length) o.gegen = "team";
  const favIds = S.favs.map((f) => f.id);
  if (o.gegen === "favs" && !favIds.length) o.gegen = "team";
  const foes = o.gegen === "eigene" ? own : o.gegen === "team" ? t.ids : o.gegen === "favs" ? favIds : o.gegen === "foes" ? S.foes : S.usageIds.slice(0, 30);
  if (!foes.length) {
    // zurück zur vorigen Wahl (Gegner von oben, Favoriten …), sonst zu häufigen Gegnern oder dem Team
    const ok = {smogon: champ && (S.usageIds || []).length, foes: !champ && S.foes.length, favs: favIds.length, team: true};
    const back = ok[o.vorher] ? o.vorher : champ && (S.usageIds || []).length ? "smogon" : "team";
    const NAMEN = {smogon: "häufigen Gegnern", foes: "den Gegnern von oben", favs: "den Favoriten", team: "meinem Team"};
    el().innerHTML = `${CH()}<p class="hint">Noch keine eigenen Gegner gewählt.</p><div class="bar"><div class="ac"><input id="cfoeq" type="search" placeholder="Gegner hinzufügen" style="width:220px"></div>
      <button data-act="calcgegen" data-v="${back}">zurück zu ${NAMEN[back]}</button></div>`;
    autocomplete($("#cfoeq"), (x) => { store.set(ownKey, [x.id]); calcBox(); });
    return;
  }
  const r = await api("/api/schaden", {spiel: S.game, ids: t.ids, details: t.details, slot: o.slot, attacke: o.move, verteidiger: foes, verteidiger_details: o.gegen === "team" ? t.details : o.gegen === "foes" && foeTrainer() ? foes.map((id) => ({level: foeMember(id)?.lvl || ""})) : null,
    vert: o.vert, krit: o.krit ? 1 : "", flaeche: champ ? (o.flaeche === "auto" ? null : o.flaeche === "ja") : false, tera_vert: o.tera && (champ || TERA()) ? +o.tera : null,
    level: champ ? "" : o.level, level_vert: champ ? "" : o.lvv, wetter: o.wetter || ""});
  if (rid !== RID || !el()) return;
  if (r.hinweis) { el().innerHTML = `${CH()}<p class="hint">${esc(r.hinweis)}</p>`; return; }
  // Übersicht: je Mitglied gegen jeden Gegner die stärkste seiner gewählten Attacken
  const all = o.ansicht === "alle" ? await api("/api/schaden/uebersicht", {spiel: S.game, ids: t.ids, details: t.details, verteidiger: foes, verteidiger_details: o.gegen === "team" ? t.details : o.gegen === "foes" && foeTrainer() ? foes.map((id) => ({level: foeMember(id)?.lvl || ""})) : null, vert: o.vert, krit: o.krit ? 1 : "",
    flaeche: champ ? (o.flaeche === "auto" ? null : o.flaeche === "ja") : false, tera_vert: o.tera && (champ || TERA()) ? +o.tera : null, level: champ ? "" : o.level, level_vert: champ ? "" : o.lvv, wetter: o.wetter || ""}) : null;
  if (rid !== RID || !el()) return;
  const pct = (x) => String(x).replace(".", ",");
  const toneOf = (x) => x.min_pct >= 100 ? "go" : x.max_pct >= 100 ? "warn" : x.max_pct >= 50 ? "mid" : "low";
  const ko = (x) => !x.sicher ? "keine Wirkung" : x.sicher === 1 ? "sicher K.O." : x.moeglich === 1 ? `K.O. mit Glück, sonst ${x.sicher} Treffer` : x.sicher === x.moeglich ? `${x.sicher} Treffer` : `${x.moeglich}–${x.sicher} Treffer`;
  const cls = (x) => x.sicher === 1 ? "go" : x.moeglich === 1 ? "warn" : x.sicher === 0 || !x.sicher ? "stop" : "";
  const old = r.gen <= 2, inc = (r.eingerechnet || []).length ? `Eingerechnet: ${esc(r.eingerechnet.join(", "))}. ` : "";
  const rest = old ? `${inc}Bis Generation 2: volle DVs und Stat Exp, Zufall 217 bis 255 von 255${r.gen === 1 ? ", ein Spezial-Wert für Angriff und Verteidigung" : ""}.`
    : r.art === "la" ? `Werte nach Effort Levels (deine von der Detailseite); ohne Kraft- und Tempostil; Zufall 85 bis 100 %.`
    : r.art === "lgpe" ? `Werte mit IV 31 und AVs (deine von der Detailseite), ohne Freundschafts-Bonus; Zufall 85 bis 100 %.`
    : `${inc}Ohne Felder und Fähigkeiten mit Bedingung (wenig KP, Kontakt …); Zufall 85 bis 100 %.`;
  el().innerHTML = `${CH()}
    <div class="bar"><span class="seg"><button class="${o.ansicht === "alle" ? "" : "on"}" data-cv="eins" data-tip="Eine Attacke eines Mitglieds gegen alle Gegner, mit Balken und Treffern bis K.O.">eine Attacke</button><button class="${o.ansicht === "alle" ? "on" : ""}" data-cv="alle" data-tip="Jedes Mitglied gegen jeden Gegner mit seiner stärksten gewählten Attacke">Übersicht</button></span>
      ${o.ansicht === "alle" ? "" : `<span class="hint">Angreifer</span><span class="seg cslots">${t.ids.map((id, i) => dmg(i).length ? `<button class="${i === o.slot ? "on" : ""}" data-cslot="${i}" data-hc="${id}" data-slot="${i}" aria-label="${esc(ROWS[id]?.name || id)}">${img(id, "sm")}<span>${esc(ROWS[id]?.name || id)}</span></button>` : "").join("")}</span>
      <label>Attacke <select id="cmove">${dmg(o.slot).map((x) => `<option value="${x}"${x === o.move ? " selected" : ""}>${esc(A[x].name)} (${A[x].staerke})</option>`).join("")}</select></label>`}
      </div><div class="bar">
      <label data-tip="${champ ? "Häufige Gegner: die 30 meistgenutzten Pokémon der Nutzungsstatistik von Smogon (unten unter „Häufige Gegner“)." : "Gegner von oben: die aus „Gegen Gegner“."} Mein Team: deine eigenen sechs. Favoriten: deine Favoriten in diesem Spiel. Eigene Auswahl: wen du selbst hinzufügst">gegen <select id="cgegen">${champ && (S.usageIds || []).length ? `<option value="smogon"${o.gegen === "smogon" ? " selected" : ""}>häufige Gegner (Top 30)</option>` : ""}
        ${!champ && S.foes.length ? `<option value="foes"${o.gegen === "foes" ? " selected" : ""}>Gegner von oben (${S.foes.length})</option>` : ""}
        <option value="team"${o.gegen === "team" ? " selected" : ""}>mein Team</option>${favIds.length ? `<option value="favs"${o.gegen === "favs" ? " selected" : ""}>Favoriten (${favIds.length})</option>` : ""}<option value="eigene"${o.gegen === "eigene" ? " selected" : ""}>eigene Auswahl (${own.length})</option></select></label>
      <label data-tip="${old ? "Ob die Verteidiger volle Stat Exp in KP und der passenden Verteidigung haben (DVs immer 15)" : "Wie viel die Verteidiger in KP und die passende Verteidigung stecken (252 EVs)"}">Gegner <select id="cvert">${[["0", "nicht investiert"], ["kp", "volle KP"], ["kp_vert", "volle KP und Verteidigung"]].map(([k, n]) => [k, r.art === "la" && k !== "0" ? n + " (Effort Level 10)" : r.art === "lgpe" && k !== "0" ? n + " (200 AVs)" : n]).map(([k, n]) => `<option value="${k}"${o.vert === k ? " selected" : ""}>${n}</option>`).join("")}</select></label>
      ${champ ? "" : `<label data-tip="Level deines Pokémon; leer: wie auf seiner Detailseite eingetragen, sonst 50">Level <input type="number" id="clv" min="1" max="100" value="${esc(o.level)}" placeholder="${r.level}" style="width:64px"></label>
        <label data-tip="Level der Gegner; leer: wie dein Pokémon">Level Gegner <input type="number" id="clvv" min="1" max="100" value="${esc(o.lvv)}" placeholder="${r.level_vert}" style="width:64px"></label>`}
      ${champ || TERA() ? `<label data-tip="Tera-Typ aller Verteidiger (ersetzt ihre Typen)">Tera Gegner <select id="ctera"><option value="">–</option>${Object.entries(S.types).map(([k, n]) => `<option value="${k}"${o.tera === k ? " selected" : ""}>${esc(n)}</option>`).join("")}</select></label>` : ""}
      ${champ ? `<label data-tip="Flächenattacken treffen im Doppel beide Gegner mit 75 % Stärke">Fläche <select id="cfl">${[["auto", "nach Attacke"], ["ja", "ja"], ["nein", "nein"]].map(([k, n]) => `<option value="${k}"${o.flaeche === k ? " selected" : ""}>${n}</option>`).join("")}</select></label>` : ""}
      ${r.gen >= 2 ? `<label data-tip="Sonne: Feuer ×1,5, Wasser ×0,5; Regen umgekehrt">Wetter <select id="cwet">${[["", "keins"], ["sonne", "Sonne"], ["regen", "Regen"]].map(([k, n]) => `<option value="${k}"${(o.wetter || "") === k ? " selected" : ""}>${n}</option>`).join("")}</select></label>` : ""}
      <label data-tip="Volltreffer: ${r.gen === 1 ? "das Level zählt doppelt" : r.krit === 2 ? "× 2 (bis Generation 5)" : "× 1,5"}"><input type="checkbox" id="ckrit"${o.krit ? " checked" : ""}> Volltreffer</label></div>
    ${all ? `<p class="hint">Je Zelle die stärkste gewählte Attacke des Mitglieds gegen den Gegner, Schaden in Prozent seiner KP (größter Wurf, Einzelheiten beim Darüberfahren); grün: sicher K.O., gelb: K.O. mit Glück. Level ${r.level}${r.level_vert !== r.level ? `, Gegner Level ${r.level_vert}` : ""}. ${rest}</p>` : `<p class="hint">${esc(r.angreifer)}: ${esc(r.attacke)} ${tchip(r.typ)} ${r.klasse === 2 ? "physisch" : "speziell"}, Stärke ${r.staerke}${r.stab > 1 ? `, <span data-tip="Eigentyp-Bonus: Attacke vom eigenen Typ ×1,5${r.stab === 2 ? "; Tera-Typ gleich eigenem Typ: ×2" : ""}">Eigentyp ×${fl(r.stab)}</span>` : `, <span data-tip="Kein eigener Typ: ohne Eigentyp-Bonus (sonst ×1,5)">ohne Eigentyp-Bonus</span>`}, Level ${r.level},
      ${old ? "volle DVs und Stat Exp" : r.art === "la" ? `Effort Level ${r.el}` : r.art === "lgpe" ? `${r.av} AVs` : r.ev == null ? "Angriff voll investiert (252 EVs)" : `${r.ev} EVs`}${r.wesen > 1 ? ", Wesen +10 %" : r.wesen < 1 ? ", Wesen −10 %" : ""}${r.tera ? `, Tera ${tname(r.tera)}` : ""}${r.flaeche ? ", als Flächenattacke (× 0,75)" : ""}${r.level_vert !== r.level ? `; Gegner Level ${r.level_vert}` : ""}.
      ${rest}</p>`}
    ${o.gegen === "eigene" ? `<div class="bar logpick">${own.map((id) => `<span class="chip on" data-act="calcfoe" data-id="${id}" data-tip="Entfernen">${img(id, "sm")}${esc(ROWS[id]?.name || "#" + id)} ✕</span>`).join("")}
      <div class="ac"><input id="cfoeq" type="search" placeholder="Gegner hinzufügen" style="width:200px"></div></div>` : ""}
    ${all ? `<div class="scroll"><table class="rows dmgx" id="dmgx" data-rowpin="0"><thead><tr><th></th>${all.gegner.map((g, k) => `<th class="c" data-c="${k + 1}" data-pc="${k + 1}" data-hc="${g.id}">${img(g.id, "sm")}<div>${esc(g.name)}</div></th>`).join("")}</tr></thead>
      <tbody>${all.rows.map((m, i) => `<tr data-r="${i}"><th class="nw r" data-pr="${i}" data-c="0" data-hc="${m.id}">${img(m.id, "sm")} ${esc(m.name)}</th>${m.zellen.map((x, k) => !x ? `<td class="c hint" data-c="${k + 1}">–</td>`
        : `<td class="c ${toneOf(x)}" data-c="${k + 1}" ${tipRef(dmgTip({angreifer: m.name, attacke: x.attacke, level: x.level ?? r.level, gen: r.gen}, Object.assign({}, x, {name: all.gegner[k].name})) + `<div class="muted">${esc(ko(x))}</div>`)}><b style="color:${ramp(x.max_pct / 100)}">${pct(x.max_pct)} %</b><div class="hint">${esc(x.attacke)}</div></td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<div class="scroll sticky"><table class="rows sort dmg fixed"><colgroup><col style="width:26%"><col style="width:84px"><col style="width:180px"><col style="width:110px"><col style="width:120px"><col></colgroup>
      <thead><tr>${th("Verteidiger")}${thc("Wirkung")}${thc("Schaden", "Balken: kräftig der kleinste Wurf, blass bis zum größten; ein voller Balken ist 100 % der KP")}${thc("in %", "Prozent der KP, kleinster bis größter Wurf")}${thc("KP")}${th("Treffer bis K.O.", "", true)}</tr></thead>
      <tbody>${r.rows.map((x) => { const tone = x.min_pct >= 100 ? "go" : x.max_pct >= 100 ? "warn" : x.max_pct >= 50 ? "mid" : "low";
        return `<tr data-hc="${x.id}"><td class="nw" data-s="${esc(x.name)}">${img(x.id, "sm")} <a href="#pokemon/${x.id}">${esc(x.name)}</a>${x.faehigkeit_vert ? ` <span class="cls" data-tip="Fähigkeit des Verteidigers ändert die Wirkung dieser Attacke (gerechnet mit seiner ersten Fähigkeit)">${esc(x.faehigkeit_vert)}</span>` : ""}${x.item_vert ? ` <span class="cls" data-tip="${esc("Item des Verteidigers: " + x.item_vert)}">Item</span>` : ""}</td>
        <td class="c" data-s="${x.eff}">${x.eff === 1 ? `<span class="hint">×1</span>` : `<span class="f ${fcls(x.eff)}">×${fl(x.eff)}</span>`}</td>
        <td data-s="${x.max_pct}" ${tipRef(dmgTip(r, x))}><span class="dbar ${tone}"><i class="mx" style="width:${Math.min(100, x.max_pct)}%"></i><i class="mn" style="width:${Math.min(100, x.min_pct)}%"></i></span></td>
        <td class="c num ${tone}" data-s="${x.max_pct}" ${tipRef(dmgTip(r, x))}>${pct(x.min_pct)}–${pct(x.max_pct)} %</td>
        <td class="c num hint" data-s="${x.kp}" ${tipRef(dmgTip(r, x))}>${x.min}–${x.max} / ${x.kp}</td><td class="${cls(x)}">${ko(x)}</td></tr>`; }).join("")}</tbody></table></div>`}`;
  if ($("#dmgx")) crossTable($("#dmgx"), XPIN);     // 0.48.6: Übersicht wie „Gegen Gegner“ markierbar
  $$("[data-cv]", el()).forEach((b) => b.addEventListener("click", () => set("ansicht", b.dataset.cv)));
  if ($("#cfoeq")) autocomplete($("#cfoeq"), (x) => { if (!own.includes(x.id)) store.set(ownKey, [...own, x.id].slice(0, 30)); calcBox(); });
  const set = (k, v) => { o[k] = v; store.set(ck, o); calcBox(); };
  $$("[data-cslot]", el()).forEach((b) => b.addEventListener("click", () => set("slot", +b.dataset.cslot)));
  $("#cmove")?.addEventListener("change", (e) => set("move", +e.target.value));
  $("#cgegen").addEventListener("change", (e) => { if (o.gegen !== "eigene") o.vorher = o.gegen; set("gegen", e.target.value); });
  $("#cvert").addEventListener("change", (e) => set("vert", e.target.value));
  $("#ctera")?.addEventListener("change", (e) => set("tera", e.target.value));
  $("#cfl")?.addEventListener("change", (e) => set("flaeche", e.target.value));
  $("#clv")?.addEventListener("change", (e) => set("level", e.target.value));
  $("#clvv")?.addEventListener("change", (e) => set("lvv", e.target.value));
  $("#ckrit").addEventListener("change", (e) => set("krit", e.target.checked));
  $("#cwet")?.addEventListener("change", (e) => set("wetter", e.target.value));
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
      <p class="hint">${LA() ? "Legenden: Arceus rechnet mit Effort Levels statt EVs und DVs. Spalten: Effort Level 0 mit senkendem Wesen, 0 neutral, 10 neutral, 10 mit Wesen (+10 %). Dein Team mit seinen eingetragenen Stufen (Detailseite), sonst Stufe 0." : gen <= 2 ? "Bis Generation 2: ohne und mit vollen DVs und Stat Exp." : "Spalten: minimal (0 IV, 0 EV, senkendes Wesen), neutral (31 IV, 0 EV), maximal (31 IV, 252 EV), maximal mit Wesen (+10 %)."}
        Dein Team ist hervorgehoben, mit dem Wert aus Level, EVs, IVs und Wesen, soweit eingetragen (sonst neutral). Unter Bizarroraum gilt die Liste umgekehrt.</p>
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
    SPO = {lv, gen, wind: o.wind, schal: o.schal};
    const mine = S.team.ids.map((id, i) => {
      const r = ROWS[id], det = S.team.details[i] || {}, x = ev.plaetze?.[i] || {};
      if (!r) return null;
      const iv = det.ivs ? det.ivs[5] : (gen <= 2 ? 15 : 31), evv = det.evs ? det.evs[5] : 0;
      const nat = x.wesen_mod ? (x.wesen_mod[0] === 5 ? 1.1 : x.wesen_mod[1] === 5 ? 0.9 : 1) : 1;
      const own = (LA() ? laStat(r.werte[5], det.level || lv, det.el?.[5] || 0, nat) : speedStat(r.werte[5], det.level || lv, iv, evv, nat, gen)) * (x.item === "Wahlschal" && !o.schal ? 1.5 : 1);
      const mults = [x.item === "Wahlschal" && !o.schal ? ["Wahlschal (Item)", 1.5] : null, o.wind ? ["Rückenwind", 2] : null, o.schal ? ["Wahlschal", 1.5] : null].filter(Boolean);
      const tipH = speedTip(`${r.name}, dein Team`, {base: r.werte[5], lv: det.level || lv, gen, iv, ev: evv, nat, el: det.el?.[5] || 0, mults});
      return {r, own: Math.floor(own * (o.wind ? 2 : 1) * (o.schal ? 1.5 : 1)), det, x, slot: i, tipH};
    }).filter(Boolean);
    let rows = d.rows.map((r) => ({r, cols: speedCols(r.werte[5], lv, gen).map((v) => v == null ? null : Math.floor(v * mult))}));
    if (q) rows = rows.filter(({r}) => r.name.toLowerCase().includes(q));
    if (o.team) rows = [];
    const mrow = (m) => `<tr class="mine" data-hc="${m.r.id}"><td>${img(m.r.id)} <a href="#pokemon/${m.r.id}/${m.slot}">${esc(m.r.name)}</a> <span class="hint">dein Team${m.det.level ? ", Level " + m.det.level : ""}${LA() ? (m.det.el ? ", Effort Level " + m.det.el[5] : ", Effort Level nicht eingetragen (0)") : ""}${m.x.wesen ? ", " + esc(m.x.wesen) : ""}${m.x.item ? ", " + esc(m.x.item) : ""}</span></td>
      <td class="num">${m.r.werte[5]}</td><td class="num" colspan="4" ${tipRef(m.tipH)}><b>${m.own}</b></td></tr>`;
    // Team-Zeilen stehen dort, wo ihr eigener Wert in die Liste fällt
    const out = [], todo = [...mine].sort((a, b) => b.own - a.own);
    rows.forEach(({r, cols}) => {
      const top = cols[3] ?? cols[2];
      while (todo.length && todo[0].own >= top) out.push(mrow(todo.shift()));
      out.push(`<tr data-hc="${r.id}"><td>${img(r.id)} <a href="#pokemon/${r.id}">${esc(r.name)}</a></td><td class="num">${r.werte[5]}</td>${cols.map((v, k) => v == null ? `<td class="num"></td>` : `<td class="num" data-tip-speed="${r.werte[5]}:${k}">${v}</td>`).join("")}</tr>`);
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
const CMPC = new Map();
async function compareView(a, b) {
  const rid = RID;
  const ids = [a, b].map((x) => (x && !isNaN(+x) ? +x : null));
  // Merken und Schnellwahl zeichnen sofort neu: schon geladene Pokémon kommen aus dem Zwischenspeicher
  const ck = (id) => id + "|" + S.game;
  const ds = await Promise.all(ids.map((id) => id == null ? null : CMPC.get(ck(id)) || api(`/api/pokemon/${id}?` + qs({spiel: S.game})).then((d) => { CMPC.set(ck(id), d); return d; }).catch(teil("Pokémon im Vergleich", null))));
  if (rid !== RID) return;
  ds.forEach((d) => { if (d) { ROWS[d.id] = Object.assign(ROWS[d.id] || {}, d); } });
  const [A, B] = ds;
  const go = (x, y) => { location.hash = `vergleich/${x ?? "-"}/${y ?? "-"}`; };
  // Schnellwahl unter dem Vergleich: zuerst die gemerkten (mit „alle entfernen“), darunter die Favoriten, ohne die schon gewählten
  const marked = cmpList(), favs = S.favs.map((f) => f.id).filter((id) => !marked.includes(id));
  const qbtn = (k, id, tip) => `<button class="cq" data-cq="${k}" data-id="${id}" data-hc="${id}" aria-label="${tip}: hierher stellen">${img(id)}</button>`;
  const qrow = (k) => {
    const m = marked.filter((id) => id !== ids[k]), f = favs.filter((id) => id !== ids[k]).slice(0, 12);
    return `<div class="cmppick">${m.length ? `<div class="cqh"><b>Zum Vergleich gemerkt</b>${k === 0 ? `<button class="small" data-act="cmpclear" data-tip="Alle gemerkten Pokémon aus der Merkliste nehmen">alle entfernen</button>` : ""}</div>
        <div class="cmpquick">${m.map((id) => qbtn(k, id, "Gemerkt")).join("")}</div>` : ""}
      ${f.length ? `<div class="cqh"><b>Favoriten</b></div><div class="cmpquick fav">${f.map((id) => qbtn(k, id, "Favorit")).join("")}</div>` : ""}
      ${!m.length && !f.length ? `<p class="hint small">Tipp: Auf der Detailseite „Zum Vergleich merken“ oder Favoriten setzen, dann stehen sie hier zur Wahl.</p>` : ""}</div>`;
  };
  const pick = (d, k) => `<div class="box cmphead cmpsel"><div class="ac"><input type="search" id="cmpq${k}" placeholder="${d ? `statt ${esc(d.name)} ein anderes Pokémon` : "Pokémon suchen"}" aria-label="Pokémon suchen"></div>${qrow(k)}</div>`;
  const head = (d, k) => `<div class="box cmphead">
    ${d ? `<a class="cmpmon" href="#pokemon/${d.id}" data-tip="Zur Detailseite">${img(d.id, "big", true)}<b>${esc(d.name)}</b></a><div>${tchips(d.typen)}</div>
      ${d.im_spiel === false ? `<div class="note warn small">In ${esc(gameName())} nicht enthalten</div>` : ""}
      <span class="cmpradar" data-tip-stats="${d.werte.join(",")}">${radar(d.werte, 200, true)}</span>
      <button class="mark small${cmpMarked(d.id) ? " on" : ""}" data-act="cmpmark" data-id="${d.id}" data-markbtn="cmp">${markLabel("cmp", cmpMarked(d.id))}</button>`
      : `<p class="hint">Noch kein Pokémon gewählt. Suche oder wähle unten eines aus.</p><div class="ac"><input type="search" id="cmpe${k}" placeholder="Pokémon suchen"></div>`}</div>`;
  const better = (x, y) => x > y ? " win" : "";
  const statRows = A && B ? [...STAT.map((n, i) => [n, A.werte[i], B.werte[i], i]), ["Summe", A.summe, B.summe, "summe"]].map(([n, x, y, i]) => {
    const w = (v) => Math.min(100, v / (i === "summe" ? 780 : statMax(i)) * 100);
    const diff = x - y;
    return `<tr><td class="num${better(x, y)}">${x}</td><td><span class="sbar rev"><i style="width:${w(x)}%;background:${i === "summe" ? sumColor(x) : statColor(x)}"></i></span></td>
      <th data-tip="${esc(i === "summe" ? "Summe aller Basiswerte" : STAT[i] + ": Basiswert. Grün ist der höhere; darunter der Unterschied aus Sicht von " + A.name)}">${n}<div class="hint">${diff ? (diff > 0 ? "+" : "") + diff : "gleich"}</div></th>
      <td><span class="sbar"><i style="width:${w(y)}%;background:${i === "summe" ? sumColor(y) : statColor(y)}"></i></span></td><td class="num${better(y, x)}">${y}</td></tr>`;
  }).join("") : "";
  const ts = Object.keys(S.chart || {});
  // Verteidigung: je Angriffstyp der Faktor beider; wer weniger einsteckt, bekommt die Zelle grün hinterlegt und ein ✓
  const fword = (f) => f === 0 ? "keine Wirkung" : f > 2 ? "doppelt schwach" : f > 1 ? "schwach" : f < 0.5 ? "doppelt resistent" : f < 1 ? "resistent" : "neutral";
  const dcell = (d, f, other, t) => `<td class="c${f < other ? " better" : f > other ? " worse" : ""}" data-tip="${esc(`${tname(t)}-Attacken gegen ${d.name}: ×${fl(f)} (${fword(f)})${f < other ? `; steckt weniger ein als ${(d === A ? B : A).name}` : f > other ? `; steckt mehr ein als ${(d === A ? B : A).name}` : ""}`)}">${f === 1 ? `<span class="hint">1</span>` : `<span class="f ${fcls(f)}">${fl(f)}</span>`}${f < other ? ` <span class="ok">✓</span>` : ""}</td>`;
  const defRow = A && B ? ts.map((t) => { const x = A.wirkung[t] ?? 1, y = B.wirkung[t] ?? 1;
    return `<tr data-r="${t}">${dcell(A, x, y, t)}<th class="c" data-tip="${esc(`${tname(t)}-Attacken: links gegen ${A.name}, rechts gegen ${B.name}. Grün = steckt weniger ein, rot = mehr`)}">${tchip(t)}</th>${dcell(B, y, x, t)}</tr>`; }).join("") : "";
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
  // Kurz gesagt: wer schneller ist (Level 50, volle Initiative), wer wen mit Eigentyp-Attacken härter trifft
  let fazit = "";
  if (A && B) {
    const gen = S.meta?.spiele?.find((g) => g.kennung === S.game)?.gen || 9;
    const sp = (d) => speedCols(d.werte[5], 50, gen)[2];
    const fac = (t, y) => effMul(y.typen.map((d) => S.chart?.[t]?.[d] ?? 1));
    const best = (x, y) => x.typen.reduce((b, t) => fac(t, y) > fac(b, y) ? t : b, x.typen[0]);
    const ta = best(A, B), tb = best(B, A), ha = fac(ta, B), hb = fac(tb, A), sa = sp(A), sb = sp(B);
    const win = (v, o, low) => (low ? v < o : v > o) ? `<b class="fz-g">${v}</b>` : (low ? v > o : v < o) ? `<b class="fz-r">${v}</b>` : `<b>${v}</b>`;
    const line = (txt, tip) => `<li data-tip="${esc(tip)}">${txt}</li>`;
    fazit = `<div class="box"><h2>Kurz gesagt</h2><ul class="fazit">
      ${line(sa === sb ? `Gleich schnell (${sa} auf Level 50)` : `<b>${esc(sa > sb ? A.name : B.name)}</b> ist schneller: <b class="fz-g">${Math.max(sa, sb)}</b> gegen <b class="fz-r">${Math.min(sa, sb)}</b> auf Level 50`,
        "Initiative auf Level 50 mit 31 IV und 252 EV, neutrales Wesen. Mehr dazu in der Initiative-Liste")}
      ${line(`${esc(A.name)} trifft ${esc(B.name)} mit ${tchip(ta)} <span class="f ${fcls(1 / (ha || 0.001))}">×${fl(ha)}</span>, umgekehrt ${esc(B.name)} mit ${tchip(tb)} <span class="f ${fcls(1 / (hb || 0.001))}">×${fl(hb)}</span>`,
        "Bester Faktor einer Attacke von einem eigenen Typ (genannt ist der Typ); mit Eigentyp-Bonus kommt noch ×1,5 dazu")}
      ${line(`Physisch oder speziell: ${esc(A.name)} ${A.werte[1] >= A.werte[3] ? "eher physisch" : "eher speziell"}, ${esc(B.name)} ${B.werte[1] >= B.werte[3] ? "eher physisch" : "eher speziell"}`,
        "Aus dem höheren der Werte Angriff und Spezial-Angriff")}
      ${line(`Schwächen: ${esc(A.name)} ${win(sum(A).s, sum(B).s, true)}, ${esc(B.name)} ${win(sum(B).s, sum(A).s, true)}; Resistenzen und Immunitäten: ${win(sum(A).r + sum(A).i, sum(B).r + sum(B).i)} gegen ${win(sum(B).r + sum(B).i, sum(A).r + sum(A).i)}`, "Aus der Typwirkung unten; grün ist besser (weniger Schwächen, mehr Resistenzen)")}
    </ul></div>`;
  }
  const abil = (d) => d.faehigkeiten.length ? d.faehigkeiten.map((x) => `<div><b>${wikiLink(x.name)}</b>${x.versteckt ? " <span class='cls'>versteckt</span>" : ""}<div class="why">${esc(x.text)}</div></div>`).join("") : `<p class="hint">keine</p>`;
  main.innerHTML = `<div class="bar">${backLink()}<h2 style="margin:0">Vergleich</h2><label class="game2">Spiel <select class="gamesel"></select></label>
      ${A || B ? `<button id="cmpswap" data-tip="Seiten tauschen">⇄ tauschen</button>` : ""}</div>
    <div class="cmpgrid">${head(A, 0)}<div class="box cmpmid">${A && B ? `<table class="cmpst">${statRows}</table>` : `<p class="hint">Wähle zwei Pokémon, dann stehen hier die Werte nebeneinander.</p>`}</div>${head(B, 1)}</div>
    <div class="cmpgrid sel">${pick(A, 0)}<div></div>${pick(B, 1)}</div>
    ${fazit}
    ${A && B ? `<div class="cols"><div class="box"><h2 data-tip="So stark treffen Attacken eines Typs; grün = steckt weniger ein">Verteidigung</h2>
        <p class="hint">${esc(A.name)}: ${sum(A).s} Schwächen, ${sum(A).r} Resistenzen, ${sum(A).i} Immunitäten · ${esc(B.name)}: ${sum(B).s}, ${sum(B).r}, ${sum(B).i}</p>
        <table class="cmpdef"><thead><tr><th class="c">${esc(A.name)}</th><th class="c">Angriffstyp</th><th class="c">${esc(B.name)}</th></tr></thead><tbody>${defRow}</tbody></table></div>
      <div class="stack"><div class="box"><h2>Fähigkeiten</h2><div class="cols2"><div><h3>${esc(A.name)}</h3>${abil(A)}</div><div><h3>${esc(B.name)}</h3>${abil(B)}</div></div></div>${moves}</div></div>` : ""}`;
  header();
  autocomplete($("#cmpq0"), (r) => go(r.id, B?.id));
  autocomplete($("#cmpq1"), (r) => go(A?.id, r.id));
  if ($("#cmpe0")) autocomplete($("#cmpe0"), (r) => go(r.id, B?.id));
  if ($("#cmpe1")) autocomplete($("#cmpe1"), (r) => go(A?.id, r.id));
  $("#cmpswap")?.addEventListener("click", () => go(B?.id, A?.id));
  $$("[data-cq]").forEach((b) => b.addEventListener("click", () => { const id = +b.dataset.id; b.dataset.cq === "0" ? go(id, B?.id) : go(A?.id, id); }));
  if (!A) $("#cmpe0")?.focus(); else if (!B) $("#cmpe1")?.focus();
}

/* Alle Typkombinationen (Verteidigung): je Kombination die Wirkung jedes Angriffstyps, dazu Schwächen, 4-fach,
   Resistenzen und Immunitäten zum Sortieren; Filter auf einen enthaltenen Typ */
function combosHtml(ch) {
  const ts = Object.keys(ch), att = store.get("combosSicht", "def") === "att", pick = typePick("combosPick", ts);
  const combos = [];
  ts.forEach((x, i) => { combos.push([x]); ts.slice(i + 1).forEach((y) => combos.push([x, y])); });
  const shown = combos.filter((c) => [...pick].every((t) => c.includes(t)));
  const rows = shown.map((c) => {
    // Verteidiger: Spalte greift an, Faktoren multiplizieren sich. Angreifer: Spalte verteidigt, es zählt der bessere Eigentyp
    const fs = ts.map((t) => att ? Math.max(...c.map((a) => ch[a]?.[t] ?? 1)) : effMul(c.map((d) => ch[t]?.[d] ?? 1)));
    const cnt = att ? attCnt(fs) : defCnt(fs);
    // als Verteidiger ist ½ gut (grün), als Angreifer ist 2 gut: dann Farben umdrehen
    return `<tr data-r="${c.join(",")}"><th class="r" data-pr="${c.join(",")}" data-s="${esc(c.map(tname).join(" "))}">${tchips(c)}</th>
      ${fs.map((f, j) => `<td class="c" data-c="${j + 1}" data-s="${f}">${f === 1 ? "" : `<span class="f ${att && f ? fcls(1 / f) : fcls(f)}">${fl(f)}</span>`}</td>`).join("")}
      ${cntCells(att ? ATTC : DEFC, cnt, ts.length + 1)}</tr>`;
  }).join("");
  const heads = (att ? ATTC : DEFC).map(([n, tip]) => thc(n, tip)).join("");
  return `<details class="box combos"${store.get("combosOpen", false) ? " open" : ""}><summary><h2 style="display:inline">Alle Typkombinationen</h2> <span class="hint">${shown.length} von ${combos.length} Kombinationen</span></summary>
    <div class="bar"><label data-tip="Verteidiger: so viel steckt ein Pokémon mit diesen Typen ein. Angreifer: so gut treffen Attacken seiner beiden Eigentypen zusammen">Sicht
        <select id="cbsicht"><option value="def"${att ? "" : " selected"}>als Verteidiger</option><option value="att"${att ? " selected" : ""}>als Angreifer</option></select></label>
      <span class="hint">${att ? "Spalte: verteidigender Typ, es zählt der bessere der beiden Eigentypen (wie die Typtabelle oben, nur je Kombination)." : "Spalte: angreifender Typ, so stark trifft er ein Pokémon mit diesen Typen."}
        Klick auf eine Überschrift sortiert, das Zeichen davor markiert die Spalte; Klick auf die Typen markiert die Zeile. Zählung rechts: grün hilft, rot schadet.</span></div>
    ${typeFilter("combosPick", ts, pick, "Typen wählen: nur Kombinationen, die alle gewählten Typen enthalten")}
    <div class="scroll sticky"><table class="chart sort cbt"><thead><tr>${th("Typen")}
      ${ts.map((t) => `<th class="v c" data-sort><span>${tchip(t)}</span></th>`).join("")}${heads}</tr></thead><tbody>${rows}</tbody></table></div></details>`;
}

