/* Pokédex-Oberfläche, Teil 7 von 10: Items und Typtabelle.
   Die Teile lädt index.html der Reihe nach; sie teilen sich die globalen Namen (docs/oberflaeche.md). */
"use strict";
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
// 0.57.0: Die Bälle aus Hisui kommen vom Server (/api/meta, hisui_baelle); hier steht keine eigene Tabelle mehr
const ballHisui = (n) => { const b = (S.meta?.hisui_baelle || []).find((x) => x[0] === n); return b ? [b[1], b[4] || ""] : null; };
const ballOf = (x) => { const h = / \(Hisui\)$/.test(x.name) || PROFIL().baelle === "hisui"; const n = x.name.replace(/ \(Hisui\)$/, "");
  return (h ? ballHisui(n) : null) || BALL[n] || null; };
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
  // 0.53: Maschinen abhaken (gefunden, Karte „tm“) und wo es sie gibt (Kartenpunkte); Filter alle / habe ich / fehlen
  const tmGot = await api("/api/gefunden?" + qs({spiel: S.game, karte: "tm"})).catch(teil("Abgehakte Maschinen", {}));
  if (rid !== RID) return;
  const tmHave = new Set((tmGot.tm || []).map(String));
  // 0.56.2: Rezepte abhaken (Legenden: Arceus), abgelegt wie die Maschinen unter der Karte „rezept“
  const rzGot = d.rezepte ? await api("/api/gefunden?" + qs({spiel: S.game, karte: "rezept"})).catch(teil("Abgehakte Rezepte", {})) : {};
  if (rid !== RID) return;
  const rzHave = new Set((rzGot.rezept || []).map(String));
  let tmShow = store.get("tmShow", ""), tmOrte = null;
  const tmKey = (x) => { const m = /\b(TM|VM|TP|HM|TR)\s*0*(\d{1,3})\b/.exec(x.name || ""); return m ? ({HM: "VM", TR: "TP"}[m[1]] || m[1]) + (+m[2]) : ""; };
  if (!(d.taschen || []).includes(pocket) && !(pocket === HERSTELLEN && d.rezepte)) pocket = "";
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Items</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      <input id="itemq" type="search" placeholder="Name oder Beschreibung" style="width:220px">
      <select id="itemart" aria-label="Art"></select>
      ${nOdd ? `<label data-tip="Einträge, deren Text in den Spieldaten noch Platzhalter wie [VAR] enthält"><input type="checkbox" id="itemodd"> unfertige Einträge (${nOdd})</label>` : ""}
</div>
    <div class="bar"><span class="seg" id="itemseg"><button data-t="">alle</button>${(d.taschen || []).map((t) => `<button data-t="${esc(t)}">${esc(t)}</button>`).join("")}${d.rezepte
      ? `<button data-t="${HERSTELLEN}" data-tip="Items mit Rezept: was es zum Herstellen braucht">Herstellen</button>` : ""}</span>
      <span class="seg" id="tmseg" hidden><button data-tms="">alle</button><button data-tms="habe">habe ich</button><button data-tms="fehlt">fehlen</button><span class="hint" id="tmcnt" style="margin-left:8px"></span></span>
      <span class="hint grow" id="itemn"></span></div>
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
              ...FXCOLS.map(([k, n, tip]) => [thc(["kp", "ap", "ep"].includes(k) ? n : `<span class="st-${k}">${n}</span>`, tip), "64px", fxCell(k)]),
              [th("Beschreibung", "", true), "", text]],
    Bälle: [[th("Name"), "22%", name], [thc("Preis"), "7%", price], [thc("Fang", "Fangfaktor des Balls; „immer“ fängt sicher. In Legenden: Arceus Richtwerte"), "70px", ballCell],
            [th("Bedingung", "Wann der Ball besser fängt"), "26%", (x) => `<td>${esc(ballOf(x)?.[1] || "")}</td>`], [th("Beschreibung", "", true), "", text]],
    Maschinen: [[thc("✓", "Habe ich: abgehakte Maschinen nutzt der Moveset-Vorschlag, fehlende nicht"), "44px", (x) => `<td class="c" data-s="${tmHave.has(String(x.id)) ? 1 : 0}"><span class="tmck${tmHave.has(String(x.id)) ? " on" : ""}" data-tm="${x.id}" data-tip="${tmHave.has(String(x.id)) ? "Habe ich; Klick: doch nicht" : "Als vorhanden abhaken"}">✓</span></td>`],
                [th("Name"), "13%", name], [thc("Preis"), "7%", price], [th("Attacke"), "15%", (x) => `<td><b>${esc(x.attacke?.name || "")}</b></td>`],
                [thc("Typ"), "9%", (x) => `<td class="c" data-s="${x.attacke ? esc(tname(x.attacke.typ)) : ""}">${x.attacke ? tchip(x.attacke.typ) : ""}</td>`],
                [thc("Klasse"), "8%", (x) => `<td class="c">${esc(MKLASSE[x.attacke?.klasse] || "")}</td>`],
                [thc("Stärke"), "6%", (x) => num(x.attacke?.staerke)], [thc("Gen."), "6%", (x) => num(x.attacke?.genauigkeit)], [thc("AP"), "5%", (x) => num(x.attacke?.ap)],
                [th("Wo", "Kartenpunkte, die diese Maschine nennen (Klick: auf der Karte zeigen)"), "12%", (x) => { const ws = (tmOrte || {})[tmKey(x)] || [];
                  return `<td class="why">${tmOrte === null ? `<span class="hint">…</span>` : ws.length ? ws.map((w) => w.id ? `<a href="#karte/mg/${esc(w.karte)}/${esc(w.id)}">${esc(w.name || w.titel)}</a>` : esc(w.name)).join(", ") : `<span class="hint">–</span>`}</td>`; }],
                [th("Wirkung", "", true), "", (x) => `<td class="why">${x.attacke?.kurz ? kurzHtml(x.attacke.kurz) : esc(x.text)}</td>`]],
    [HERSTELLEN]: [[th("Name"), "22%", name], [th("Zutaten"), "30%", recipe], [th("Wo", "Wo das Rezept zu haben ist"), "16%", where],
                   [thc("✓", "Rezept habe ich"), "44px", (x) => `<td class="c" data-s="${rzHave.has(String(x.id)) ? 1 : 0}"><span class="tmck${rzHave.has(String(x.id)) ? " on" : ""}" data-tm="${x.id}" data-ka="rezept" data-tip="${rzHave.has(String(x.id)) ? "Rezept habe ich; Klick: doch nicht" : "Rezept als vorhanden abhaken"}">✓</span></td>`],
                   [th("Rezept bekommen", "", true), "", (x) => `<td class="why" lang="en">${esc(x.rezept?.hinweis && x.rezept.hinweis !== "N/A" ? x.rezept.hinweis : "–")}</td>`]],
  };
  const draw = () => {
    const ql = q.toLowerCase();
    const inPocket = items.filter((x) => (!pocket || x.tasche === pocket || (pocket === HERSTELLEN && x.rezept)) && (odd || !x.unfertig));
    const arts = [...new Set(inPocket.map((x) => x.art).filter(Boolean))].sort((a, b) => a.localeCompare(b, "de"));
    if (art && !arts.includes(art)) art = "";
    $("#itemart").innerHTML = `<option value="">jede Art</option>` + arts.map((a) => `<option${a === art ? " selected" : ""}>${esc(a)}</option>`).join("");
    const isTm = pocket === "Maschinen";
    const xs = inPocket.filter((x) => (!art || x.art === art) && (!ql || x.name.toLowerCase().includes(ql) || x.text.toLowerCase().includes(ql)
      || (x.attacke?.name || "").toLowerCase().includes(ql))
      && (!isTm || !tmShow || (tmShow === "habe") === tmHave.has(String(x.id))));
    $("#tmseg").hidden = !isTm;
    if (isTm) { const all = inPocket.length, got = inPocket.filter((x) => tmHave.has(String(x.id))).length;
      $("#tmcnt").textContent = `${got} von ${all} abgehakt`; $$("#tmseg button").forEach((b) => b.classList.toggle("on", b.dataset.tms === tmShow));
      if (tmOrte === null && !draw.loading) { draw.loading = true;
        api("/api/tmorte?" + qs({spiel: S.game})).then((o) => { tmOrte = o || {}; if (rid === RID) draw(); }).catch((e) => { tmOrte = {}; teil("Fundorte der Maschinen")(e); }); } }
    const kind = pocket === HERSTELLEN ? HERSTELLEN : pocket === "Maschinen" ? "Maschinen" : pocket === "Bälle" ? "Bälle"
      : pocket === "Medizin" || pocket === "Beeren" ? "wirkung" : "";
    const cols = COLS[kind].filter((c, i) => !(pocket && !kind && i === 2));      // in einer Tasche braucht es die Spalte Tasche nicht
    $("#itemn").textContent = `${xs.length} Items`;
    $("#itembox").innerHTML = `<table class="rows sort fixed items lines"><colgroup>${cols.map((c) => `<col${c[1] ? ` style="width:${c[1]}"` : ""}>`).join("")}</colgroup>
      <thead><tr>${cols.map((c) => c[0]).join("")}</tr></thead><tbody>${xs.map((x) => `<tr data-r="${x.id}"${x.unfertig ? ` class="odd"` : ""}>${cols.map((c) => c[2](x)).join("")}</tr>`).join("")
      + (xs.length ? "" : `<tr><td colspan="${cols.length}" class="hint">Nichts gefunden.</td></tr>`)}</tbody></table>`;
    $$("#itemseg button").forEach((x) => x.classList.toggle("on", x.dataset.t === pocket));
    const tb = $("#itembox table");
    $$("tbody tr[data-r]", tb).forEach((tr) => [...tr.cells].forEach((td, i) => { td.dataset.c = i; if (td.classList.contains("why")) td.classList.add("nohc"); if (!i) td.dataset.pr = tr.dataset.r; }));
    crossTable(tb, IPIN);
  };
  $$("#tmseg button").forEach((b) => b.addEventListener("click", () => { tmShow = b.dataset.tms; store.set("tmShow", tmShow); draw(); }));
  $("#itembox").addEventListener("click", async (e) => {
    const t = e.target.closest("[data-tm]");
    if (!t) return;
    const ka = t.dataset.ka || "tm", have = ka === "rezept" ? rzHave : tmHave;
    const id = t.dataset.tm, on = !have.has(id);
    await api("/api/gefunden", {spiel: S.game, karte: ka, objekt: [id], an: on});
    if (on) have.add(id); else have.delete(id);
    draw();
  });
  $("#itemq").addEventListener("input", (e) => { q = e.target.value.trim(); draw(); });
  $("#itemart").addEventListener("change", (e) => { art = e.target.value; draw(); });
  $("#itemodd")?.addEventListener("change", (e) => { odd = e.target.checked; draw(); });
  $$("#itemseg button").forEach((b) => b.addEventListener("click", () => { pocket = b.dataset.t; store.set("itemPocket", pocket); art = ""; draw(); }));
  draw();
}
const CPIN = {r: null, c: null}, TPIN = {d: {r: null, c: null}, a: {r: null, c: null}};
/* Typfilter je Tabelle: eine Knopfreihe mit allen Typen, gemerkt unter key */
const typePick = (key, ts) => new Set(store.get(key, []).filter((t) => ts.includes(t)));
const typeFilter = (key, ts, pick, tip) => `<div class="bar tpick" data-tip="${esc(tip)}"><span class="hint">Filter</span>${ts.map((t) =>
  `<button class="tpk${pick.has(t) ? " on" : ""}" data-tf="${key}" data-tpk="${t}">${tchip(t)}</button>`).join("")}${pick.size ? `<button class="small" data-tf="${key}" data-tpkx>alle</button>` : ""}</div>`;
/* Zählspalte farbig: gut grün, schlecht rot, kräftiger je mehr (bezogen auf max); 0 bleibt blass */
const cntTd = (v, good, max, c, tip = "") => `<td class="c num cnt${v ? (good ? " cg" : " cb") : " zero"}" data-c="${c}" data-s="${v}"${tip ? ` data-tip="${esc(`${tip}: ${v}`)}"` : ""}>${v}</td>`;
// Zählung je Zeile aus den Faktoren: Verteidigung [Schw., ×4, Res., Imm.], Angriff [stark, schwach, ohne Wirkung]
const defCnt = (fs) => [fs.filter((f) => f > 1).length, fs.filter((f) => f > 2).length, fs.filter((f) => f < 1 && f > 0).length, fs.filter((f) => f === 0).length];
const attCnt = (fs) => [fs.filter((f) => f > 1).length, fs.filter((f) => f < 1 && f > 0).length, fs.filter((f) => f === 0).length];
const DEFC = [["Schw.", "Schwächen: Angriffstypen mit ×2 oder mehr", false, 8], ["×4", "Doppelte Schwächen: ×4, in Legenden: Arceus ×2,5", false, 2], ["Res.", "Resistenzen: ×½ oder weniger", true, 8], ["Imm.", "Immun: keine Wirkung", true, 2]];
const ATTC = [["Stark", "Verteidigende Typen, die sehr effektiv getroffen werden", true, 8], ["Schwach", "Typen, gegen die es nur ×½ schafft", false, 8], ["Imm.", "Typen, gegen die nichts wirkt", false, 2]];
const cntHeads = (cs) => cs.map(([n, tip]) => `<th class="c cnth" data-tip="${esc(tip)}">${n}</th>`).join("");
const cntCells = (cs, vs, base) => vs.map((v, i) => cntTd(v, cs[i][2], cs[i][3], typeof base === "number" ? base + i : base + i, cs[i][1])).join("");
/* Typen des Teams: je Mitglied mit seinen (Doppel-)Typen, wie viel es einsteckt (Verteidigung) und wie stark seine
   Eigentypen treffen (Angriff, der bessere der beiden). Zeilen sind die Mitglieder, Spalten die 18 Typen */
function teamTypeHtml(ms, all) {
  const ch = S.chart;
  const def = (m, a) => effMul(m.typen.map((t) => ch[a]?.[t] ?? 1));
  const att = (m, v) => Math.max(...m.typen.map((t) => ch[t]?.[v] ?? 1));
  const one = (k, title, hint, fn, good) => {
    const tp = typePick(`ttPick${k}`, all), ts = tp.size ? all.filter((t) => tp.has(t)) : all;
    const sum = ts.map((t) => { const fs = ms.map((m) => fn(m, t)); return [fs.filter((f) => good(f)).length, fs.filter((f) => good(1 / (f || 0.001)) && f !== 1).length]; });
    return `<details class="box tteam" data-tt="${k}"${store.get("ttOpen", {})[k] === false ? "" : " open"}><summary><h2>${title}</h2><span class="hint">${hint}</span></summary>
      ${typeFilter(`ttPick${k}`, all, tp, "Typen wählen: die Tabelle zeigt nur diese Spalten; die Zählung rechts gilt weiter für alle Typen")}
      <div class="scroll"><table class="chart" id="tt-${k}"><thead><tr><th class="corner"></th>${ts.map((t) => `<th class="v" data-c="${t}" data-pc="${t}"><span>${tchip(t)}</span></th>`).join("")}${cntHeads(k === "d" ? DEFC : ATTC)}</tr></thead>
      <tbody>${ms.map((m, i) => `<tr data-r="${i}"><th class="r tm" data-pr="${i}" data-hc="${m.id}"><span class="tmh">${img(m.id, "sm")}<span>${esc(m.name)}</span>${tchips(m.typen)}</span></th>${ts.map((t) => { const f = fn(m, t);
        return `<td data-c="${t}" data-tip="${esc(k === "d" ? `${tname(t)} gegen ${m.name}: ×${fl(f)}` : `${m.name} (Eigentyp) gegen ${tname(t)}: ×${fl(f)}`)}">${f === 1 ? "" : `<span class="f ${k === "a" && f ? fcls(1 / f) : fcls(f)}">${fl(f)}</span>`}</td>`; }).join("")}${(() => {
          const fs = all.map((t) => fn(m, t)); return k === "d" ? cntCells(DEFC, defCnt(fs), "n") : cntCells(ATTC, attCnt(fs), "n"); })()}</tr>`).join("")}</tbody>
      <tfoot><tr><th class="r">${k === "d" ? "resistent · schwach" : "stark · schwach"}</th>${sum.map(([g, b], j) => `<td data-c="${ts[j]}"><span class="go">${g || ""}</span>${g && b ? "·" : ""}<span class="stop">${b || ""}</span></td>`).join("")}${"<td></td>".repeat(k === "d" ? 4 : 3)}</tr></tfoot></table></div></details>`;
  };
  // Farben aus Sicht des Mitglieds: grün hilft ihm, rot schadet ihm. Verteidigung: ½ grün, 2 rot; Angriff umgekehrt
  return one("d", "Verteidigung je Mitglied", "Spalte: angreifender Typ. So viel steckt das Mitglied mit seinen Typen ein; grün: steckt wenig ein, rot: viel.", def, (f) => f < 1)
    + one("a", "Angriff je Mitglied", "Spalte: verteidigender Typ. So gut trifft der bessere Eigentyp des Mitglieds; grün: trifft stark, rot: schwach.", att, (f) => f > 1);
}
async function chartView() {
  const ch = S.chart, ts = Object.keys(ch);
  const rid = RID, mine = store.get("chartTeam", false) && S.team.ids.length;
  let ms = [], fremd = [];
  if (mine) {
    const ev = await api("/api/team/bewerten", {spiel: S.game, ids: S.team.ids, kurz: 1});
    if (rid !== RID) return;
    ev.mitglieder.forEach((m) => { ROWS[m.id] = Object.assign(ROWS[m.id] || {}, m); });
    ms = S.team.ids.map((id) => ROWS[id]).filter((r) => r?.typen).map((r) => ({...r, typen: r.typen.map(String)}));
    fremd = (ev.nicht_im_spiel || []).map((i) => ROWS[S.team.ids[i]]?.name).filter(Boolean);
  }
  const own = new Set(ms.flatMap((m) => m.typen));
  const pick = typePick("chartPick", ts);
  const rowOk = (a) => (!mine || own.has(a)) && (!pick.size || pick.has(a));
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Typtabelle Generation ${S.chartGen}</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      <label data-tip="${S.team.ids.length ? "Nur die Typen deines Teams als Zeilen, dazu Verteidigung und Angriff je Mitglied" : "Erst ein Team zusammenstellen"}"><input type="checkbox" id="ctm"${mine ? " checked" : ""}${S.team.ids.length ? "" : " disabled"}> Mein Team</label>
      <button class="small" data-act="unpin" id="unpin" hidden>Markierung aufheben</button></div>
    ${typeFilter("chartPick", ts, pick, "Typen wählen: die Tabelle zeigt nur diese Angreifer")}
    ${fremd.length ? `<div class="note warn">Nicht in ${esc(gameName())}: ${fremd.map(esc).join(", ")}. Die Typen gelten trotzdem, das Pokémon kannst du dort aber nicht einsetzen.</div>` : ""}
    <p class="hint">Zeile greift an, Spalte verteidigt. <span class="f f2">2</span> sehr effektiv · <span class="f f05">½</span> nicht sehr effektiv ·
      <span class="f f0">0</span> keine Wirkung (immun) · leer = normal (×1). Klick auf einen Typ hält Zeile oder Spalte fest, Klick auf eine Zelle beides.</p>
    <div class="scroll"><table class="chart" id="tchart"><thead><tr><th class="corner"><span>Angriff ↓ · Verteidigung →</span></th>${ts.map((t) => `<th class="v" data-c="${t}" data-pc="${t}"><span>${tchip(t)}</span></th>`).join("")}${cntHeads(ATTC)}</tr></thead>
    <tbody>${ts.filter(rowOk).map((a) => `<tr data-r="${a}"><th class="r" data-pr="${a}">${tchip(a)}</th>${ts.map((v) => { const f = ch[a][v];
      return `<td data-c="${v}" data-tip-cell="${a}:${v}">${f === 1 ? "" : `<span class="f ${fcls(f)}">${fl(f)}</span>`}</td>`; }).join("")}${cntCells(ATTC, attCnt(ts.map((v) => ch[a][v])), "n")}</tr>`).join("")}</tbody>
    </table></div>${mine ? `<p class="hint">Nur die Typen deines Teams als Angreifer: ${ms.map((m) => esc(m.name)).join(", ")}.</p>` : ""}</div>
    ${mine ? teamTypeHtml(ms, ts) : combosHtml(ch)}`;
  header();
  // jeder Filter merkt sich seine Auswahl selbst (data-tf); „alle“ leert ihn
  $$("[data-tf]").forEach((b) => b.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation();
    const k = b.dataset.tf, p = typePick(k, ts);
    if (b.dataset.tpkx !== undefined) p.clear(); else p.has(b.dataset.tpk) ? p.delete(b.dataset.tpk) : p.add(b.dataset.tpk);
    store.set(k, [...p]); chartView();
  }));
  if (!mine) {
    $("details.combos").addEventListener("toggle", (e) => store.set("combosOpen", e.target.open));
    $("#cbsicht").addEventListener("change", (e) => { store.set("combosSicht", e.target.value); chartView(); });
    crossTable($("table.cbt"), CPIN, null, false);
  }
  crossTable($("#tchart"), PIN, () => { $("#unpin").hidden = PIN.r === null && PIN.c === null; }, false);
  $("#ctm").addEventListener("change", (e) => { store.set("chartTeam", e.target.checked); chartView(); });
  $$("details.tteam").forEach((d) => {
    crossTable($("table", d), TPIN[d.dataset.tt], null, false);
    d.addEventListener("toggle", () => store.set("ttOpen", {...store.get("ttOpen", {}), [d.dataset.tt]: d.open}));
  });
}

