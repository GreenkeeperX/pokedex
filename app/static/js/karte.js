/* Pokédex-Oberfläche, Teil 6 von 10: Karten, Sammelobjekte, Fortschritt, Shiny-Jagd, Tauschliste, Was fehlt mir noch, Gebiete.
   Die Teile lädt index.html der Reihe nach; sie teilen sich die globalen Namen (docs/oberflaeche.md). */
"use strict";
/* ------------------------------------------------------------------ Karte (Legenden: Arceus)
   Spielkoordinaten 0–1024; Welt in Pixeln = Koordinate × 2 (2048 px bei Zoom 2). Kacheln 256 px von Serebii, auf dem Server
   gespeichert; Zoom 0 hat 2 × 2, Zoom 1 hat 4 × 4, Zoom 2 hat 8 × 8 Kacheln. Ziehen verschiebt, Mausrad zoomt. */
const WORLD = 2048;
const mpct = (x) => String(x).replace(".", ",") + " %";
/* Kartensymbole (Altissimo): Zeichen und Farbe je Art; Ebenen lassen sich einzeln ausblenden */
const MOBJ = {aprikoko: "A", beere: "B", baum: "Z", erz: "E", laub: "L", heu: "H", kiste: "K", truhe: "T",
  irrlicht: "✦", icognito: "?", vers: "V", graben: "G", kristall: "◆", verzerrung: "◎", massen: "M", baumpkmn: "P", alpha: "α", boden: "•", reise: "»", lager: "△"};
/* Ebenen in Gruppen; was keiner Gruppe angehört, steht unter „Weitere“ */
const MGROUPS = [["Pokémon", ["pokemon", "kristall", "verzerrung", "massen", "baumpkmn", "alpha"]], ["Bäume und Rohstoffe", ["baum", "aprikoko", "beere", "erz", "laub", "heu"]],
  ["Items", ["kiste", "truhe", "boden", "graben"]], ["Sammeln", ["irrlicht", "icognito", "vers"]], ["Orte", ["reise", "lager"]]];
let MAPPOS = null;          // Ausschnitt, wenn sich nur ein Filter ändert
const MOBJMON = new Set(["kristall", "verzerrung", "massen", "baumpkmn", "alpha"]);     // Symbole mit Pokémon statt Items
const MAPCACHE = {};        // Kartendaten je Gebiet: die Wahl eines Pokémon lädt nichts neu
const MOBJHINT = {irrlicht: "Geisterlicht zum Einsammeln; 107 gibt es in ganz Hisui.", icognito: "Icognito zum Fangen; 28 Formen gibt es in Hisui.",
  vers: "Gedicht zum Lesen (Sammelobjekt).", graben: "Grabstelle: hier lässt sich mit Ursaluna nach Items graben.",
  kristall: "Kristallbrocken: zerschlagen, dann erscheint das Pokémon.", verzerrung: "Raum-Zeit-Verzerrung: hier erscheinen die Pokémon während einer Verzerrung.",
  massen: "Massenauftreten: hier kann es zu einem Massenauftreten kommen.", baumpkmn: "Baum schütteln oder werfen: das Pokémon fällt heraus.",
  alpha: "Festes Alpha-Pokémon an dieser Stelle.", reise: "Schnellreise: hierher bringt dich Pikas Flug.", lager: "Lager: ausruhen, herstellen, Pokémon tauschen."};
const MAPSPIEL = "legends-arceus";          // bisher die einzige Karte mit Symbolen
const okey = (o) => `${o.art}:${Math.round(o.x)}:${Math.round(o.z)}`;
const mobjTip = (o, arten) => `${arten[o.art]?.[0] || o.art}${o.nr ? " " + o.nr : ""}` + (o.menge ? `\n${o.menge} Stück je Mal` : "")
  + (o.items.length ? "\n" + o.items.map(([n, p]) => p ? `${n}: ${p}` : n).join("\n") : "");
/* Übersicht mit Pokémon-Bildern: die Karte in Felder (64 Spieleinheiten) geteilt; je Feld die häufigsten Pokémon als
   Bild, so groß, wie sie dort wahrscheinlich sind. Gewicht je Spawnpunkt = sein Anteil (höchster Wert, 0–1), je Stelle der
   PokéWiki-Ebenen ihr Anteil oder 1. Das Bild sitzt im Schwerpunkt seiner Punkte im Feld */
const HEAT_G = 64;
function mapHeat(pts, objs, sh = (m) => m.max || 0) {
  const cells = {}, tot = {};
  const add = (x, z, id, name, w) => {
    if (!id) return;
    const k = Math.floor(x / HEAT_G) + "," + Math.floor(z / HEAT_G), c = cells[k] ||= {};
    const s = c[id] ||= {id, name, w: 0, n: 0, sx: 0, sz: 0, sw: 0};
    const ww = Math.max(w, 0.02);
    s.w += w; s.n++; s.sx += x * ww; s.sz += z * ww; s.sw += ww;
    const t = tot[id] ||= {id, name, w: 0, n: 0};
    t.w += w; t.n++;
  };
  pts.forEach((p) => p.mons.forEach((m) => { const v = sh(m); if (v > 0) add(p.x, p.z, m.id, m.name.replace(/ \(.*\)$/, ""), v / 100); }));
  objs.forEach((o) => { if (MOBJMON.has(o.art)) o.items.forEach(([n, t, id]) => {
    const pc = /([\d,]+) %/.exec(t || ""); add(o.x, o.z, id, n.replace(/ \(.*\)$/, ""), pc ? parseFloat(pc[1].replace(",", ".")) / 100 : o.items.length > 1 ? 1 / o.items.length : 1); }); });
  return {cells, tot};
}
const heatTip = (s) => `${s.name}: ${s.n} Stelle${s.n === 1 ? "" : "n"} hier, zusammen ${String(Math.round(s.w * 100) / 100).replace(".", ",")}`;
/* Gebiete eines Spiels (für Spiele ohne Karte): links die Orte, rechts alle Pokémon dort als Bildergitter, nach Methode.
   Gefangene sind blass (Filter „nur fehlende“). Gewählter Ort je Spiel gemerkt; #karte/gebiete/<Ort> öffnet ihn direkt */
/* Karten von Map Genie (für jedes Spiel, für das es dort eine gibt): Kacheln über den eigenen Server (im Datenordner
   zwischengespeichert), Orte als farbige Punkte je Gruppe, Filter je Kategorie, „gefunden“ per Rechtsklick wie bei
   Legenden: Arceus. #karte/mg/<Karte>; ohne Karte für das Spiel geht es zu den Gebieten */
const MGDATA = {};
const MGWORDS = {"How to unlock": "Freischalten", "How to get": "So bekommst du es", "How to catch": "Fangen", "Location": "Ort",
  "Note": "Hinweis", "Hint": "Hinweis", "Steps": "Schritte", "Reward": "Belohnung", "Rewards": "Belohnung", "Requirements": "Voraussetzung",
  "Weather / Time": "Wetter / Tageszeit", "Rarity": "Seltenheit", "Level range": "Level", "Level": "Level", "Cloak": "Umhang",
  "Verse description": "Vers", "Description": "Beschreibung", "Recipe": "Rezept", "Item": "Item", "Items": "Items", "Price": "Preis"};
const MGVALS = {"All": "immer", "Day": "tagsüber", "Night": "nachts", "Common": "häufig", "Rare": "selten", "Very Rare": "sehr selten",
  "Shaking trees": "Bäume schütteln", "Night only": "nur nachts", "Day only": "nur tagsüber", "Shake trees": "Bäume schütteln"};
function mgMd(text, slug) {
  const inline = (s) => esc(s)
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, (_, t, u) => { const m = u.match(/locationIds=(\d+)/);
      return m ? `<a href="#karte/mg/${esc(slug)}/${m[1]}">${t}</a>` : `<a href="${u}" target="_blank" rel="noopener">${t}</a>`; })
    .replace(/\*\*([^*]+)\*\*/g, (_, t) => `<b>${MGWORDS[t.replace(/:$/, "").trim()] ? MGWORDS[t.replace(/:$/, "").trim()] + ":" : t}</b>`)
    .replace(/(^|[\s(\[])[*_]([^*_]+)[*_](?=[\s.,)\]]|$)/g, (_, a, t) => { const k = t.replace(/^\[|\]$/g, ""); return `${a}<i>${MGVALS[k] ? (k === t ? MGVALS[k] : `[${MGVALS[k]}]`) : t}</i>`; });
  const out = [];
  let list = "";
  String(text).split("\n").forEach((raw) => {
    const ln = raw.trimEnd(), m = ln.match(/^(\s*)(?:[-*]|(\d+)\.)\s+(.*)$/);
    if (m) {
      const kind = m[2] ? "ol" : "ul";
      if (list !== kind) { if (list) out.push(`</${list}>`); out.push(`<${kind}>`); list = kind; }
      out.push(`<li${m[1].length ? ' class="sub"' : ""}>${inline(m[3])}</li>`);
      return;
    }
    if (list) { out.push(`</${list}>`); list = ""; }
    if (!ln.trim()) return;
    // „**Feld:** Wert“: Wert übersetzen, wenn es ein bekannter Begriff ist
    const kv = ln.match(/^\*\*([^*]+?):?\*\*:?\s*(.*)$/);
    if (kv) { const v = kv[2].trim(); out.push(`<p><b>${esc(MGWORDS[kv[1].trim()] || kv[1].trim())}:</b> ${MGVALS[v] ? esc(MGVALS[v]) : inline(v)}</p>`); return; }
    out.push(`<p>${inline(ln)}</p>`);
  });
  if (list) out.push(`</${list}>`);
  return out.join("");
}
// Anfangszoom je Spiel (oder Spiel/Karte): Stufen näher als „ganze Karte im Bild“, als Liste mit der Mitte in Anteilen
// 0.49: nach Rückmeldung vom 12.11. abends (eine Mausrad-Raste = eine halbe Stufe)
// 0.56.2: nach Rückmeldung vom 13.11. je Karte nachgestellt; „/karte“ gilt für diese Karte in jedem Spiel
const MGSTART = {"red-blue": 1.75, yellow: 1.75, "legends-arceus": 2, "firered-leafgreen": [1.75, 0.33, 0.44],
  "firered-leafgreen/rb-fire-red-leaf-green": [1, 0.33, 0.3],
  "gold-silver": 1, crystal: 1, "/crystal": [1, 0.46, 0.5], "gold-silver/crystal": [1, 0.43, 0.5], "/db-crystal": 0.75, "/db-gold-silver": 0.75,
  "heartgold-soulsilver": 0, "/se-kanto": 0.25, "omega-ruby-alpha-sapphire": 0.5, "lets-go-pikachu-lets-go-eevee": 0.75,
  "sword-shield": 0.5, "the-isle-of-armor": 0.5, "the-crown-tundra": 0.5,
  "scarlet-violet": 2, "the-teal-mask": 2, "the-indigo-disk": 2.5, "/paldea-region": [2, 0.5, 0.54], "/kitakami-region": 1.5, "/terrarium": 2.5,
  "legends-za": [1.25, 0.45, 0.5], "mega-dimension": [1.25, 0.45, 0.5],
  pokopia: [1.5, 0.59, 0.44],
  "ruby-sapphire": 0.5, emerald: 0.5, "diamond-pearl": [0.5, 0.5, 0.33], platinum: [0.5, 0.5, 0.33],
  "heartgold-soulsilver/im-johto": 1.5, "heartgold-soulsilver/im-kanto": 0.5,   // große Weltkarten (IronMON)
  "sword-shield/rn-wa": 0, "the-isle-of-armor/rn-ioa": 0.5, "the-crown-tundra/rn-ct": 0.5,   // Raid-Nester
  "/se-alola-mele-mele": 0.5, "/se-alola-akala": [0.5, 0.5, 0.53], "/se-alola-ula-ula": [0.5, 0.5, 0.53], "/se-alola-poni": 0.5, "/se-alola-aether": 0.5,
  "/se-kalos": -9};   // X/Y: so weit weg, wie es geht (dazu MGFAR)
const MGFAR = {"se-kalos": 0.5};   // so viele Stufen weiter weg als die weiteste Stufe der Karte
// Karte, mit der ein Spiel beginnt, wenn noch keine gewählt war
const MGFIRST = {"heartgold-soulsilver": "im-johto", "the-teal-mask": "kitakami-region", "the-indigo-disk": "terrarium"};
const mgProj = (lat, lng, z) => {
  const s = 256 * 2 ** z, r = Math.PI / 180, sy = Math.sin(lat * r);
  return [(lng + 180) / 360 * s, (0.5 - Math.log((1 + sy) / (1 - sy)) / (4 * Math.PI)) * s];
};
/* Bildkarte (HGSS IronMON Map) einmal in Kacheln umwandeln: der Server kann das große WebP-Bild ohne Zusatzbibliothek
   nicht zerlegen, der Browser schon. Stufe für Stufe ein halb so großes Bild, daraus die Kacheln, je einige auf einmal
   zum Server. Danach lädt die Karte wie jede andere nur, was sie zeigt */
const blobB64 = (b) => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(",")[1]); r.onerror = no; r.readAsDataURL(b); });
let MGCONV = null, MGCONV_MSG = "";
async function mgConvert(d, slug, rid) {
  const st = await api("/api/kacheln/umwandeln?" + qs({spiel: d.spiel, karte: slug})).catch(teil("Stand der Kacheln dieser Karte", null));
  // die Meldung steht auf der Karte, solange sie offen ist (auch nach einem Wechsel hin und zurück)
  const here = () => $("#mgwarn")?.dataset.slug === slug;
  const say = (t, warn) => { MGCONV_MSG = `<div class="note${warn ? " warn" : ""}">${t}</div>`; if (here()) $("#mgwarn").innerHTML = MGCONV_MSG; };
  if (!st || st.fertig) return;
  if (!st.bild) { say("Das Kartenbild fehlt noch; der nächste Abgleich lädt es (Einstellungen → Abgleich)."); return; }
  if (MGCONV) { if (MGCONV === slug && here()) $("#mgwarn").innerHTML = MGCONV_MSG; return; }
  MGCONV = slug;
  say("Die Karte wird einmalig in Kacheln umgewandelt. Dazu lädt das große Bild einmal (gut 10 MB), danach geht es schnell …");
  try {
    const img = new Image();
    img.src = `/mgbild/${encodeURIComponent(d.spiel)}/${encodeURIComponent(slug)}/0`;
    await img.decode();
    const T = st.kachel, c = document.createElement("canvas"), g = c.getContext("2d");
    c.width = c.height = T;
    let src = img, total = 0, done = 0, batch = [], size = 0;
    for (let z = st.z; z >= st.min; z--) { const k = T * 2 ** (st.z - z); total += Math.ceil(st.w / k) * Math.ceil(st.h / k); }
    const send = async () => { if (batch.length) await api("/api/kacheln/umwandeln", {spiel: d.spiel, karte: slug, kacheln: batch}); batch = []; size = 0; };
    for (let z = st.z; z >= st.min; z--) {
      const k = 2 ** (st.z - z), w = Math.ceil(st.w / k), h = Math.ceil(st.h / k);
      if (z < st.z) {                  // halb so groß aus der Stufe davor (glatter als aus dem Original)
        const s = document.createElement("canvas"), sg = s.getContext("2d");
        s.width = w; s.height = h;
        sg.imageSmoothingQuality = "high";
        sg.drawImage(src, 0, 0, w, h);
        if (src !== img) src.width = src.height = 0;
        src = s;
      }
      for (let y = 0; y * T < h; y++) for (let x = 0; x * T < w; x++) {
        const sw = Math.min(T, w - x * T), sh = Math.min(T, h - y * T);
        g.clearRect(0, 0, T, T);
        g.drawImage(src, x * T, y * T, sw, sh, 0, 0, sw, sh);
        const b64 = await blobB64(await new Promise((ok) => c.toBlob(ok, "image/png")));
        batch.push([z, x, y, b64]);
        size += b64.length;
        done++;
        if (size > 3_000_000 || batch.length >= 60) {
          await send();
          say(`Die Karte wird einmalig in Kacheln umgewandelt: ${Math.round(done / total * 100)} % …`);
        }
      }
    }
    await send();
    if (src !== img) src.width = src.height = 0;
    MGCONV_MSG = "";
    if (here()) route();
  } catch (e) {
    say(`Umwandeln hat nicht geklappt (${esc(e.message || String(e))}). Beim nächsten Öffnen der Karte geht es weiter.`, true);
  } finally {
    MGCONV = null;
  }
}
const MG_EDITION = {redblue: ["red-blue", "red-green-japan", "blue-japan"], yellow: ["yellow"],   // Map-Genie-Karte → Editionen
  // 0.56.2: wie bei Rot/Blau/Gelb: Hauptspiel und Erweiterungen zeigen je ihre Karte, die Spielauswahl wechselt sie
  "paldea-region": ["scarlet-violet"], "kitakami-region": ["the-teal-mask"], terrarium: ["the-indigo-disk"]};
/* Ebenen, die beim ersten Öffnen aus sind (0.56.2): an bleiben nur Ebenen der Gruppe „Orte“ (oder der ersten Gruppe) und
   Schnellreise/Lager, ohne Kleinkram wie Übergänge, und zusammen höchstens MG_START_MAX Punkte: erst Städte, Orte und
   Routen, dann die kleinsten Ebenen. Eine Ebene bleibt immer an */
/* Übersicht mit Bildern, Auswahl je Feld (0.56.2). lists: je Punkt [[id, name, gewicht], …]; proj: je Punkt [x, y] bei
   Zoom z; Stufen z0 … zq (ganze Zahlen). Je Stufe liegt ein Raster mit Feldern von MGHEAT_G px (bei dieser Stufe) fest auf
   der Karte. Gezeigt werden je Feld die bis zu drei häufigsten (ab 30 % des häufigsten) und dazu alle, die im
   Elternfeld gezeigt wurden, jeweils in dem Teilfeld, in dem sie am häufigsten sind. Gibt die Einträge der Stufe zq zurück:
   {id, name, w, n, sx, sy} (sx/w, sy/w: Schwerpunkt bei Zoom z) */
const MGHEAT_G = 80;
function heatCells(lists, proj, z, z0, zq) {
  let prev = null, cur = {};
  for (let lv = z0; lv <= zq; lv++) {
    const f = 2 ** (lv - z) / MGHEAT_G, cells = {};
    lists.forEach((xs, i) => {
      if (!xs.length || !proj[i]) return;
      const [x, y] = proj[i], c = cells[Math.floor(x * f) + "," + Math.floor(y * f)] ||= {};
      xs.forEach(([id, n, wt]) => { const s = c[id] ||= {id, name: n, w: 0, n: 0, sx: 0, sy: 0}; s.w += wt; s.n++; s.sx += x * wt; s.sy += y * wt; });
    });
    cur = {};
    Object.entries(cells).forEach(([k, c]) => { const xs = Object.values(c).sort((a, b) => b.w - a.w || a.id - b.id), top = xs[0]?.w || 0;
      cur[k] = new Set(xs.filter((s, i) => i < 3 && s.w >= top * 0.3).map((s) => s.id)); });
    if (prev) Object.entries(prev.cur).forEach(([pk, ids]) => {
      const [px, py] = pk.split(",").map(Number);
      const kids = [[0, 0], [1, 0], [0, 1], [1, 1]].map(([dx, dy]) => (px * 2 + dx) + "," + (py * 2 + dy)).filter((k) => cells[k]);
      ids.forEach((id) => { const best = kids.filter((k) => cells[k][id]).sort((a, b) => cells[b][id].w - cells[a][id].w || (a < b ? -1 : 1))[0]; if (best) cur[best].add(id); });
    });
    prev = {cur, cells};
  }
  return prev ? Object.entries(prev.cur).flatMap(([k, ids]) => [...ids].map((id) => prev.cells[k][id]).sort((a, b) => b.w - a.w)) : [];
}
const MG_START_MAX = 150, MG_NOISE = /^(Übergang|Übergänge|Tür|Eingang|Eingänge|Treppe|Leiter|Schild|Sonstiges|Verschiedenes)/i,
  MG_MAIN = /^(Stadt|Städte|Ort|Orte|Route|Routen|Schnellreise|Lager|Arena|Arenen|Pokémon-Center)/i;
function mgStartHide(groups, keep) {
  const all = groups.flatMap((g) => g.kategorien);
  const cand = all.filter((c) => (keep.some((g) => g.kategorien.includes(c)) || /^(Schnellreise|Lager)$/.test(c.titel || "")) && !MG_NOISE.test(c.titel || ""));
  const order = [...cand].sort((a, b) => (MG_MAIN.test(b.titel || "") - MG_MAIN.test(a.titel || "")) || (a.n || 0) - (b.n || 0));
  const on = new Set();
  let sum = 0;
  order.forEach((c) => { if (!on.size || sum + (c.n || 0) <= MG_START_MAX) { on.add(c.id); sum += c.n || 0; } });
  if (!on.size && all.length) on.add([...all].sort((a, b) => (a.n || 0) - (b.n || 0))[0].id);
  return all.map((c) => c.id).filter((id) => !on.has(id));
}
async function mgView(slug, want) {
  const rid = RID;
  const lst = await api("/api/mapgenie?" + qs({spiel: S.game})).catch(teil("Karten des Spiels", {karten: []}));
  if (rid !== RID) return;
  if (!lst.karten.length) return PROFIL().spawnkarten ? mapView() : areasView();
  // 0.48.6: Karten einer Schwester-Edition nicht anbieten (Rot/Blau zeigt nicht Gelb und umgekehrt), sonst blieb beim
  // Spielwechsel die Karte der anderen Edition stehen
  lst.karten = lst.karten.filter((k) => (want && k.slug === slug) || !MG_EDITION[k.slug] || MG_EDITION[k.slug].includes(S.game));   // ein Link auf eine Ebene (want) darf auch die Karte der Erweiterung öffnen
  const kk = "mgKarte:" + S.game;
  // Schwester-Editionen teilen sich ein Spiel bei Map Genie: anfangs die Karte, deren Kennung zur Edition passt (Gelb: yellow)
  const mine = lst.karten.find((k) => k.slug === MGFIRST[S.game])
    || lst.karten.find((k) => !/^(rb|se)-/.test(k.slug) && S.game.split("-").some((w) => w.length > 3 && k.slug.includes(w))) || lst.karten[0];
  if (!slug || !lst.karten.some((k) => k.slug === slug)) slug = store.get(kk, mine.slug);
  if (!lst.karten.some((k) => k.slug === slug)) slug = lst.karten[0].slug;
  store.set(kk, slug);
  const ck = S.game + "/" + slug;
  const d = MGDATA[ck] || (MGDATA[ck] = await api("/api/mapgenie?" + qs({spiel: S.game, karte: slug})));
  const gk = "mg-" + slug;
  const gotRes = await api("/api/gefunden?" + qs({spiel: d.spiel})).catch(teil("Abgehakte Punkte", {}));
  if (rid !== RID) return;
  window.scrollTo(0, 0);
  const got = new Set((gotRes[gk] || []).map((o) => gk + "|" + o));
  Object.entries(gotRes).forEach(([k, os]) => { if (k !== gk) os.forEach((o) => got.add(k + "|" + o)); });
  /* eine Datenbank: der Server hat Map Genie und die Spieldaten schon zusammengeführt (gleiche Stellen sind ein Punkt);
     t "mg" Ort von Map Genie (vielleicht mit Angaben aus den Spieldaten), "ob" nur aus den Spieldaten, "sp" Spawnpunkt */
  const cats = {}, groups = d.gruppen.map((g) => ({...g, kategorien: g.kategorien.map((c) => ({...c}))}));
  groups.forEach((g) => g.kategorien.forEach((c) => { cats[c.id] = Object.assign(c, {g}); }));
  const own = {gebiete: d.gebiete_eigen || {}};
  const pts = d.punkte.filter((p) => cats[p.c]).map((p) => ({...p, t: p.sp ? "sp" : p.id ? "mg" : "ob", k: p.sp?.k || p.o?.k,
    alpha: p.sp?.alpha, mons: p.sp?.mons,
    items: [...(p.o?.items || []), ...(p.drin || []).flatMap((x) => x.items)].map((e) => e[0]).join(", ")}));
  const okeyOf = (p) => p.o ? p.o.k + "|" + okey(p.o) : "";
  // Aufträge und Hauptmissionen: der Haken liegt wie im Reiter Aufträge unter auftrag|Nr bzw. mission|Nr
  const gkey = (p) => p.aq || (p.t === "mg" ? gk + "|mg:" + p.id : p.t === "ob" ? okeyOf(p) : "");
  const isGot = (p) => got.has(gkey(p)) || (p.t === "mg" && p.o && got.has(okeyOf(p)));
  const hk = "mgEbenen3:" + d.spiel + "/" + slug;   // 0.56.2: neuer Anfang (höchstens rund 150 Punkte), je Karte gemerkt
  /* anfangs nur zur Orientierung: die Gruppe „Orte“ (Städte, Routen, Schnellreise, Lager); alles andere schaltet man dazu.
     Hat eine Karte keine solche Gruppe, bleibt ihre erste an */
  const keep0 = groups.filter((g) => /^Orte/.test(g.titel));
  const hide0 = mgStartHide(groups, keep0.length ? keep0 : groups.slice(0, 1));
  const hide = new Set(store.get(hk, hide0).map((k) => (isNaN(+k) ? k : +k)));
  let gotHide = store.get("mapGotHide", false), q = "", sel = -1;
  const open = new Set(store.get("mgOpen", groups.filter((g) => g.kategorien.length <= 12).map((g) => String(g.id))).map(String));
  const cnt = (c) => { const f = pts.filter((p) => p.c === c.id && isGot(p)).length; return f ? `${f}/${c.n} ✓` : c.n; };
  const dot = (c) => c.id === "sp" ? `<span class="mpin-l"></span>` : c.art ? `<span class="mobj o-${c.art}">${MOBJ[c.art] || "•"}</span>` : `<span class="mgdot" style="--c:${esc(c.g.farbe)}">${esc(c.titel[0] || "•")}</span>`;
  const catBtn = (c) => `<button class="mlay${hide.has(c.id) ? "" : " on"}" data-cat="${esc(c.id)}">${dot(c)}${esc(c.titel)} <span class="hint" data-cnt="${esc(c.id)}">${cnt(c)}</span></button>`;
  const regions = d.gebiete || [];
  // Pokémon je Punkt mit Gewicht (Spawnpunkt: sein Anteil; Liste eines Orts: zu gleichen Teilen) für die Übersicht
  const HEATP = pts.map((p) => p.t === "sp" ? (p.mons || []).filter((m) => m.max > 0).map((m) => [m.id, m.name.replace(/ \(.*\)$/, ""), m.max / 100])
    : (p.pk || []).map(([id, n], _, a) => [id, n, 1 / a.length]));
  let heatOn = store.get("mgHeat", false);
  main.innerHTML = `<div class="box mapbox">
    <div class="bar"><h2 style="margin:0">Karte</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      ${lst.karten.length > 1 ? `<span class="seg">${lst.karten.map((k) => `<a class="btn${k.slug === slug ? " on" : ""}" href="#karte/mg/${esc(k.slug)}">${esc(k.titel)}</a>`).join("")}</span>` : ""}
      ${regions.length ? `<select id="mggo" aria-label="Gehe zu"><option value="">Gehe zu …</option>${regions.map((r, i) => `<option value="${i}">${esc(r[0])}</option>`).join("")}</select>` : ""}
      ${PROFIL().spawnkarten ? `<a class="btn" href="#karte/obsidianfieldlands" data-tip="Einzelkarten je Gebiet mit Tageszeit- und Wetterfilter">Einzelkarten</a>` : ""}
      <a class="btn" href="#karte/gebiete" data-tip="Alle Orte mit ihren Pokémon als Liste">Gebiete</a>
      <a class="btn" href="#sammeln" data-tip="Sammelobjekte aller Karten des Spiels mit deinem Fortschritt (Haken per Rechtsklick)">Sammelobjekte</a>
      <input id="mgq" type="search" placeholder="Ort, Symbol oder Pokémon suchen" style="width:240px">
      <label class="mgot" data-tip="Was du als erledigt markiert hast (Rechtsklick oder ✓ in den Details), ausblenden"><input type="checkbox" id="gothide"${gotHide ? " checked" : ""}> erledigte ausblenden</label>
      ${HEATP.some((x) => x.length) ? `<button class="mlay heatbtn${heatOn ? " on" : ""}" id="mgheat" data-tip="Wo es welche Pokémon gibt: Bilder je Kartenfeld, je größer, desto häufiger; rechts die häufigsten. Mit Suche nur das gesuchte Pokémon">▦ Übersicht mit Bildern</button>` : ""}
      <span class="hint grow" id="mgn"></span></div>
    <div id="mgwarn"></div>
    <div class="mapwrap"><div class="mapcol"><div id="mgmap" class="map mgmap"><div class="mgold"></div><div class="mgtiles"></div><div class="mgpins"></div><div class="mgload" hidden></div></div>
      <div class="mapzoom"><button data-mz="1" data-tip="näher">+</button><input type="range" id="mgz" aria-label="Zoom" data-tip="Zoom stufenlos; das Mausrad zoomt in halben Stufen"><button data-mz="-1" data-tip="weiter weg">−</button><button data-mz="0" data-tip="ganze Karte">⤢</button></div></div>
      <div class="mgside"><aside id="mapside" class="mapside"><p class="hint">Fahre über einen Punkt für den Namen, klicke für Einzelheiten. Rechtsklick markiert ihn als erledigt. Die Suche listet die Treffer hier; ein Klick springt hin.</p></aside>
      <div class="mgcats"><div class="bar"><b>Ebenen</b><span class="mlay-all"><button class="link" data-all="1">alle</button> · <button class="link" data-all="0">keine</button>
        <span class="hint">|</span> <button class="link" data-gfold="1" data-tip="alle Gruppen aufklappen">auf</button> · <button class="link" data-gfold="0" data-tip="alle Gruppen zuklappen">zu</button></span></div>
        ${groups.map((g, gi) => `<details class="mgg"${open.has(String(g.id)) ? " open" : ""} data-gid="${esc(g.id)}"><summary${g.tipp ? ` data-tip="${esc(g.tipp)}"` : ""}><span class="mgdot" style="--c:${esc(g.farbe)}"></span>${esc(g.titel)} <span class="hint">${g.kategorien.reduce((a, c) => a + c.n, 0)}</span>
          <button class="link" data-grp="${gi}" data-tip="ganze Gruppe ein- oder ausblenden">ein/aus</button></summary><div class="mlays">${g.kategorien.map(catBtn).join("")}</div></details>`).join("")}</div></div></div>
    <p class="hint">Alles liegt auf dem Server: Karte und Orte von ${({pokemoncompletion: "pokemoncompletion", ign: "IGN", dittobase: "DittoBase (aus den Spieldaten gezeichnet; Häuser und Höhlen stehen an ihrem Eingang)", pokearth: "Serebii PokéEarth (Karte der Region; je Ort die Pokémon aus den Fundorten des Spiels)", raidnester: "dem PKHeX Raid Plugin (Lage der Raid-Nester aus den Spieldaten)", ironmon: "der HGSS IronMON Map (ganze Welt mit Häusern und Höhlen, Trainer mit Level, Items; je Ort die Pokémon aus den Fundorten des Spiels)", rankedboost: "RankedBoost (je Ort ein Bild an seiner Stelle, ein Punkt je Ort mit seinen Pokémon)"})[d.quelle] || "Map Genie"}${["pokemoncompletion", "dittobase"].includes(d.quelle) && d.spiel !== S.game ? ` (Welt von ${esc(gameName(d.spiel))}; Fundorte und Items deiner Edition können abweichen)` : ""} (Stand ${esc(String(d.am || "").slice(0, 10).split("-").reverse().join("."))}, Texte englisch, Begriffe übersetzt)${d.spiel === "legends-arceus" ? ", zusammengeführt mit den Spieldaten (Spawnpunkte, Items, Pokémon in Bäumen und Erzbrocken): was an derselben Stelle dasselbe ist, ist ein Punkt" : ""}. Kacheln: <span id="mgstock"></span>.</p></div>`;
  header();
  const box = $("#mgmap"), tl = $(".mgtiles", box), pl = $(".mgpins", box), old = $(".mgold", box), ld = $(".mgload", box);
  const tileUrl = (k) => `/mgkachel/${encodeURIComponent(d.spiel)}/${encodeURIComponent(slug)}/${k}`;
  let oldZ = null, pending = 0, warm = new Set();
  const TS = d.kachel || 256;        // Kachelgröße: Map Genie 256, pokemoncompletion 512
  const IMGS = d.bilder || null;     // RankedBoost, Serebii: keine Kacheln, je Ort bzw. Region ein Bild
  const zmin = d.min_zoom, zmax = d.max_zoom;
  /* stufenloser Zoom: z darf zwischen den Stufen liegen; die Kacheln kommen von der nächsten Stufe (tz) und der Browser
     skaliert sie. Unter der weitesten Stufe zeigt die Karte deren Kacheln verkleinert (zwei Stufen weiter weg) */
  const zlo = (IMGS ? zmin : zmin - 2) - (MGFAR[slug] || 0), zhi = zmax + (IMGS ? 0 : 1);
  let floorZ = zmin;      // erste Stufe, für die es Kacheln gibt (manche Karten beginnen später; merkt sich die Seite)
  const tz = () => Math.max(floorZ, Math.min(zmax, Math.ceil(z - 0.25)));
  const bb = d.bounds || (() => { const la = pts.map((p) => p.la), lo = pts.map((p) => p.lo); return [Math.min(...lo), Math.min(...la), Math.max(...lo), Math.max(...la)]; })();
  let z = zmin, cx = 0, cy = 0;
  const fitBox = (b, closer = 0, fx = 0.5, fy = 0.5) => {   // [west, süd, ost, nord] ins Bild, größte passende Stufe (closer: so viele näher)
    const w = box.clientWidth, h = box.clientHeight;
    z = zlo;
    for (let t = zhi; t >= zlo; t--) {
      const [x1, y1] = mgProj(b[3], b[0], t), [x2, y2] = mgProj(b[1], b[2], t);
      if (x2 - x1 <= w * 0.92 && y2 - y1 <= h * 0.92) { z = t; break; }
    }
    z = Math.max(zlo, Math.min(zhi, z + closer));
    const [x1, y1] = mgProj(b[3], b[0], z), [x2, y2] = mgProj(b[1], b[2], z);
    cx = x1 + (x2 - x1) * fx; cy = y1 + (y2 - y1) * fy;
  };
  const zr = $("#mgz");
  Object.assign(zr, {min: zlo, max: zhi, step: 0.25});
  const zshow = () => { zr.value = z; };
  const ql = () => q.toLowerCase();
  const match = (p) => { if (!q) return true; const c = cats[p.c], l = ql();
    return [p.name, p.en, c.titel, c.en, p.items].some((x) => (x || "").toLowerCase().includes(l)); };
  const vis = (p) => !hide.has(p.c) && !(gotHide && isGot(p)) && match(p);
  const pinHtml = (p, i) => {
    const [x, y] = mgProj(p.la, p.lo, z), pos = `left:${x.toFixed(1)}px;top:${y.toFixed(1)}px`, g = isGot(p) ? " got" : "", s = i === sel ? " sel" : "";
    if (p.t === "sp") return `<button class="mpin${p.alpha ? " alpha" : ""}${s}" data-i="${i}" style="${pos}" data-tip="${esc((p.alpha ? "Alpha-Spawnpunkt\n" : "") + p.mons.map((m) => `${m.alpha ? "Alpha-" : ""}${m.name}: bis ${mpct(m.max)}`).join("\n"))}"></button>`;
    const c = cats[p.c], tipText = (p.name || c.titel) + (p.name && p.name !== c.titel ? "\n" + c.titel : "") + (p.items ? "\n" + p.items : "");
    if (c.art) return `<button class="mobj o-${c.art}${g}${s}" data-i="${i}" style="${pos}" data-tip="${esc(tipText)}">${MOBJ[c.art] || "•"}</button>`;
    return `<button class="mgp${g}${s}" data-i="${i}" style="${pos};--c:${esc(c.g.farbe)}" data-tip="${esc(tipText)}">${esc(c.titel[0] || "•")}</button>`;
  };
  const pins = () => {
    let n = 0;
    pl.innerHTML = pts.map((p, i) => { if (!vis(p)) return ""; n++; return pinHtml(p, i); }).join("");
    $("#mgn").textContent = `${n} von ${pts.length} Punkten`;
    heat();
  };
  /* Übersicht mit Bildern: die Karte in Felder geteilt; je Feld bis zu drei Pokémon, so groß, wie sie dort häufig sind
     (Summe der Gewichte), im Schwerpunkt ihrer Stellen. Mit Suche nur passende Pokémon.
     0.56.2: Die Felder liegen fest auf der Karte (je ganze Zoomstufe, 80 bis 160 px im Bild) statt am Bildschirm, und
     jede Stufe teilt ein Feld in vier. Wer in einem Feld zu sehen war, bleibt beim Hineinzoomen in dem Teilfeld zu sehen,
     in dem er am häufigsten ist: Hineinzoomen zeigt mehr und lässt niemanden verschwinden (vorher fiel etwa Chaneira weg) */
  const hl = document.createElement("div");
  hl.className = "heat mgheat";
  const heatTot = () => {
    const tot = {};
    HEATP.forEach((xs) => xs.forEach(([id, n, w]) => { const t = tot[id] ||= {id, name: n, w: 0, n: 0}; t.w += w; t.n++; }));
    return Object.values(tot).sort((a, b) => b.w - a.w);
  };
  const heat = () => {
    hl.hidden = !heatOn;
    if (!heatOn) { hl.innerHTML = ""; return; }
    hl.style.transform = pl.style.transform;
    const l = ql(), zq = Math.floor(z + 1e-6), z0 = Math.min(zq, Math.floor(zlo));
    const proj = HEATP.map((xs, i) => xs.length ? mgProj(pts[i].la, pts[i].lo, z) : null);
    const show = heatCells(HEATP.map((xs) => l ? xs.filter((e) => e[1].toLowerCase().includes(l)) : xs), proj, z, z0, zq);
    const wmax = Math.max(0.01, ...show.map((s) => s.w));
    hl.innerHTML = show.map((s) => { const px = Math.round(30 + 46 * Math.sqrt(s.w / wmax));
      return `<a class="hspr" draggable="false" href="#pokemon/${s.id}" style="left:${(s.sx / s.w).toFixed(1)}px;top:${(s.sy / s.w).toFixed(1)}px;width:${px}px;height:${px}px;margin:-${px / 2}px 0 0 -${px / 2}px" data-tip="${esc(heatTip(s))}">${img(s.id)}</a>`; }).join("");
  };
  const heatSide = () => {
    const xs = heatTot().slice(0, 40), m = xs[0]?.w || 1;
    $("#mapside").innerHTML = `<h3>Häufig auf dieser Karte</h3><table class="rows heatl">${xs.map((s) => `<tr><td>${img(s.id, "sm")}</td><td><button class="link" data-heatq="${esc(s.name)}">${esc(s.name)}</button>
      <span class="hbar"><i style="width:${Math.max(3, s.w / m * 100)}%"></i></span></td><td class="num hint" data-tip="Stellen auf der Karte">${s.n}</td></tr>`).join("")}</table>
      <p class="hint">Balken: Summe der Anteile über alle Spawnpunkte und Orte; ein Maß dafür, wie viele man antrifft. Klick sucht das Pokémon auf der Karte.</p>`;
    $$("[data-heatq]").forEach((b) => b.addEventListener("click", () => { const f = $("#mgq"); f.value = b.dataset.heatq; f.dispatchEvent(new Event("input")); }));
  };
  // Kacheln im Bild bei Zoomstufe zz (mit Rand von pad Kacheln); nur innerhalb der Karte, außerhalb gibt es keine
  const view = (zz, pad = 0) => {
    const f = 2 ** (zz - z), w = box.clientWidth, h = box.clientHeight, ox = (cx - w / 2) * f, oy = (cy - h / 2) * f;
    const [gx0, gy0] = mgProj(bb[3], bb[0], zz), [gx1, gy1] = mgProj(bb[1], bb[2], zz), out = [];
    for (let tx = Math.max(Math.floor(gx0 / TS), Math.floor(ox / TS) - pad); tx <= Math.min(Math.floor((gx1 - 1e-6) / TS), Math.floor((ox + w * f) / TS) + pad); tx++)
      for (let ty = Math.max(Math.floor(gy0 / TS), Math.floor(oy / TS) - pad); ty <= Math.min(Math.floor((gy1 - 1e-6) / TS), Math.floor((oy + h * f) / TS) + pad); ty++) out.push(`${zz}/${tx}/${ty}`);
    return out;
  };
  // RankedBoost, Serebii: je Ort ein Bild in Weltpixeln der Stufe bild_z (der Browser skaliert); nur die Bilder im Blick
  const shown = new Map();
  const images = () => {
    if (old.firstChild) { old.innerHTML = ""; oldZ = null; }   // die Bilder skaliert der Browser, das alte Bild braucht es nicht
    const w = box.clientWidth, h = box.clientHeight, vx = cx - w / 2, vy = cy - h / 2;
    tl.style.transform = pl.style.transform = hl.style.transform = `translate(${-vx}px,${-vy}px)`;
    const f = 2 ** (z - d.bild_z), [ox, oy] = mgProj(bb[3], bb[0], z), keep = new Set();
    IMGS.forEach(([n, x, y, iw, ih]) => {
      const l = ox + x * f, t = oy + y * f, ww = iw * f, hh = ih * f;
      if (l > vx + w * 1.5 || t > vy + h * 1.5 || l + ww < vx - w / 2 || t + hh < vy - h / 2) return;
      keep.add(n);
      let im = shown.get(n);
      if (!im) {
        im = new Image(); im.className = "mgimg"; im.alt = ""; im.draggable = false; im.decoding = "async";
        im.onerror = () => { im.style.visibility = "hidden"; };
        im.src = `/mgbild/${encodeURIComponent(d.spiel)}/${encodeURIComponent(slug)}/${n}`;
        shown.set(n, im); tl.appendChild(im);
      }
      Object.assign(im.style, {left: l.toFixed(1) + "px", top: t.toFixed(1) + "px", width: ww.toFixed(1) + "px", height: hh.toFixed(1) + "px"});
    });
    shown.forEach((im, n) => { if (!keep.has(n)) { im.remove(); shown.delete(n); } });
  };
  const progress = () => {
    if (IMGS) { ld.hidden = true; old.innerHTML = ""; oldZ = null; return; }
    ld.hidden = !pending; ld.textContent = pending ? `Kacheln laden … noch ${pending}` : "";
    if (pending) return;
    old.innerHTML = ""; oldZ = null;           // alles da: das vergrößerte alte Bild weg
    // auf dieser Stufe gab es keine einzige Kachel (die Karte beginnt erst weiter innen): ab jetzt die nächste nehmen
    const T = tz(), lv = lvl[T];
    if (lv && !lv.ok && lv.bad > 0 && T < zmax) { floorZ = T + 1; redraw(T); return; }
    // danach still vorladen: Nachbarschaft und die nächste Stufe hinein und hinaus (der Browser hebt sie auf)
    [...view(T, 1), ...(T < zmax ? view(T + 1) : []), ...(T > floorZ ? view(T - 1) : [])].slice(0, 120)
      .forEach((k) => { if (!warm.has(k)) { warm.add(k); new Image().src = tileUrl(k); } });
  };
  const lvl = {};
  const tiles = () => {
    if (IMGS) return images();
    const w = box.clientWidth, h = box.clientHeight, ox = cx - w / 2, oy = cy - h / 2, T = tz();
    tl.style.transform = `translate(${-ox}px,${-oy}px) scale(${2 ** (z - T)})`;
    pl.style.transform = hl.style.transform = `translate(${-ox}px,${-oy}px)`;
    if (oldZ !== null) old.style.transform = `translate(${-ox}px,${-oy}px) scale(${2 ** (z - oldZ)})`;
    const wantT = new Set(view(T)), lv = lvl[T] ||= {ok: 0, bad: 0};
    $$("img", tl).forEach((im) => { if (!wantT.has(im.dataset.k)) { if (im.onload) pending--; im.onload = im.onerror = null; im.src = ""; im.remove(); } else wantT.delete(im.dataset.k); });
    wantT.forEach((k) => {
      const [, tx, ty] = k.split("/").map(Number), im = new Image();
      im.dataset.k = k; im.alt = ""; im.draggable = false;
      im.style.left = tx * TS + "px"; im.style.top = ty * TS + "px";
      if (TS !== 256) im.style.width = im.style.height = TS + "px";
      pending++;
      im.onload = () => { im.onload = im.onerror = null; pending--; lv.ok++; progress(); };
      im.onerror = () => { im.onload = im.onerror = null; pending--; lv.bad++; im.style.visibility = "hidden"; tileTrouble(); progress(); };
      im.src = tileUrl(k); warm.add(k);
      tl.appendChild(im);
    });
    progress();
  };
  // Vorrat des Servers: wie viel der Karte schon im Datenordner liegt
  api("/api/mapgenie?" + qs({spiel: S.game})).then((r) => {
    const v = r.kacheln?.vorrat?.[`${d.spiel}/${slug}`], el = $("#mgstock");
    if (!el || rid !== RID) return;
    el.textContent = IMGS ? `keine; ${IMGS.length} Ortsbilder liegen auf dem Server, die Karte braucht kein Netz` : !v ? (r.kacheln?.laedt ? "läuft gerade" : "startet nach dem nächsten Abgleich")
      : v.fertig && v.ganz ? `alle ${v.da} Kacheln liegen auf dem Server, die Karte braucht kein Netz mehr`
      : `${v.da} von ${v.alle} Kacheln bis Stufe ${v.bis} liegen auf dem Server; der Rest kommt im Hintergrund`;
  }).catch(teil("Vorrat an Kacheln"));
  $("#mgwarn").dataset.slug = slug;
  if (d.quelle === "ironmon") mgConvert(d, slug, rid);
  // fehlen Kacheln, sagt die Karte warum (Map Genie ruht nach 403/429 einen Tag; ein Neustart des Dienstes hebt das auf)
  let troubleT = 0;
  const tileTrouble = () => {
    if (troubleT || d.quelle === "ironmon") return;      // dort fehlen Kacheln nur bis zur Umwandlung (mgConvert)
    troubleT = setTimeout(async () => {
      const st = (await api("/api/mapgenie?" + qs({spiel: S.game})).catch(teil("Stand der Kacheln", {}))).kacheln || {};
      if (rid !== RID || !$("#mgwarn")) return;
      $("#mgwarn").innerHTML = st.ruht && !d.quelle ? `<div class="note warn">Map Genie liefert gerade keine Kacheln (${esc(st.fehler)}); der Abruf ruht bis ${esc(st.ruht.slice(11, 16))} Uhr (UTC) am ${esc(st.ruht.slice(0, 10).split("-").reverse().join("."))}. Ein Neustart des Dienstes setzt das zurück.</div>`
        : st.fehler ? `<div class="note warn">Einige Kacheln fehlen (zuletzt ${esc(st.fehler)}).</div>` : "";
    }, 1500);
  };
  /* neue Zoomstufe: das bisherige Bild bleibt vergrößert stehen, bis die neuen Kacheln da sind (kein schwarzes Bild) */
  let curT = null;
  const redraw = (prevT) => {
    const T = tz();
    zshow();
    if (IMGS) { tiles(); pins(); return; }
    if (prevT !== undefined && prevT === T && curT === T) { tiles(); pins(); return; }   // gleiche Stufe: nur skalieren
    if (prevT !== undefined && prevT !== T) {
      if (!pending || oldZ === null) { old.innerHTML = ""; $$("img", tl).forEach((im) => { if (im.complete && im.style.visibility !== "hidden") old.appendChild(im); }); oldZ = prevT; }
    } else { old.innerHTML = ""; oldZ = null; }
    $$("img", tl).forEach((im) => { im.onload = im.onerror = null; im.src = ""; }); tl.innerHTML = ""; pending = 0; curT = T; tiles(); pins();
  };
  const zoomTo = (nz, px, py) => {
    nz = Math.max(zlo, Math.min(zhi, Math.round(nz * 4) / 4));
    if (Math.abs(nz - z) < 1e-6) return;
    const pT = tz();
    const w = box.clientWidth, h = box.clientHeight;
    px ??= w / 2; py ??= h / 2;
    const f = 2 ** (nz - z), wx = cx - w / 2 + px, wy = cy - h / 2 + py;
    cx = wx * f - px + w / 2; cy = wy * f - py + h / 2; z = nz;
    redraw(pT);
  };
  /* zu einem Punkt springen: hinzoomen, mittig, ausgewählt, Einzelheiten rechts */
  const jump = (i) => {
    const p = pts[i];
    if (hide.has(p.c)) { hide.delete(p.c); saveHide(); }
    z = Math.max(z, Math.min(zmax, zmax - 2));
    [cx, cy] = mgProj(p.la, p.lo, z);
    sel = i; redraw(); side(i);
  };
  /* Anfang: ganze Karte im Bild plus eine Stufe näher; je Spiel angepasst (Zahl: Stufen näher; dazu die Mitte als Anteil) */
  const st0 = MGSTART[d.spiel + "/" + slug] ?? MGSTART["/" + slug] ?? MGSTART[S.game] ?? MGSTART[d.spiel] ?? 1;
  const [sc, sfx, sfy] = Array.isArray(st0) ? st0 : [st0, 0.5, 0.5];
  fitBox(bb, sc, sfx, sfy); redraw();
  let drag = null, moved = false;
  box.addEventListener("pointerdown", (e) => { if (e.button !== 0) return; drag = {x: e.clientX, y: e.clientY, cx, cy}; moved = false; });
  box.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!moved && Math.abs(dx) + Math.abs(dy) < 4) return;
    if (!moved) { moved = true; box.setPointerCapture(e.pointerId); box.classList.add("grab"); }
    cx = drag.cx - dx; cy = drag.cy - dy; tiles();
  });
  const stop = () => { drag = null; box.classList.remove("grab"); };
  box.addEventListener("pointerup", stop);
  box.addEventListener("pointercancel", stop);
  // Mausrad: eine Raste eine halbe Stufe, Touchpad fein; mehrere Ereignisse je Bild zusammengefasst
  let wz = 0, wxy = null, wraf = 0;
  box.addEventListener("wheel", (e) => {
    e.preventDefault();
    const dy = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY, r = box.getBoundingClientRect();
    wz += Math.max(-0.5, Math.min(0.5, -dy / 200)); wxy = [e.clientX - r.left, e.clientY - r.top];
    if (!wraf) wraf = requestAnimationFrame(() => { wraf = 0; const dz = wz; wz = 0; zoomTo(z + dz, ...wxy); });
  }, {passive: false});
  box.addEventListener("dblclick", (e) => { const r = box.getBoundingClientRect(); zoomTo(z + 1, e.clientX - r.left, e.clientY - r.top); });
  $$("[data-mz]").forEach((b) => b.addEventListener("click", () => { if (b.dataset.mz === "0") { const pT = tz(); fitBox(bb); redraw(pT); } else zoomTo(z + +b.dataset.mz * 0.5); }));
  zr.addEventListener("input", () => zoomTo(+zr.value));
  $("#mggo")?.addEventListener("change", (e) => { const r = regions[+e.target.value]; if (r) { const pT = tz(); fitBox(r.slice(1)); redraw(pT); } e.target.value = ""; });
  const side = (i) => {
    const p = pts[i], c = cats[p.c], on = isGot(p);
    const gotBtn = p.t === "sp" ? "" : `<p><button class="btn gotbtn${on ? " on" : ""}" id="gotbtn">${on ? "✓ erledigt" : "als erledigt markieren"}</button></p>`;
    const itemRows = (its) => `<table class="rows">${its.map(([n, t, id]) => `<tr><td>${id ? img(id, "sm") : ""}</td><td>${id ? `<a href="#pokemon/${id}">${esc(n)}</a>` : wikiLink(n)}</td><td>${esc(t || "")}</td></tr>`).join("")}</table>`;
    let body = "";
    if (p.t === "sp") body = `<table class="rows"><tr><th></th><th>Pokémon</th><th>Anteil</th><th>Tageszeit</th><th>Wetter</th></tr>${p.mons.map((m) => `<tr><td>${img(m.id, "sm")}</td>
      <td><a href="#pokemon/${m.id}">${m.alpha ? `<span class="alpha">Alpha</span> ` : ""}${esc(m.name)}</a></td><td>bis ${mpct(m.max)}</td><td>${esc(m.zeit)}</td><td>${esc(m.wetter)}</td></tr>`).join("")}</table>`;
    if (p.pk) {
      const by = {};
      p.pk.forEach(([id, n, lab, x]) => (by[lab || "Pokémon"] ||= []).push([id, n, x]));
      body += Object.entries(by).map(([lab, xs]) => `<h4>${esc(MGVALS[lab] || lab)}</h4><div class="ggrid mgk">${xs.map(([id, n, x]) =>
        `<a class="gmon${isCaught(id) ? " got" : ""}" href="#pokemon/${id}">${img(id)}${isCaught(id) ? `<span class="gball">${ball(id)}</span>` : ""}<b>${esc(n)}</b>${x ? `<span class="hint">${esc(x)}</span>` : ""}</a>`).join("")}</div>`).join("");
    }
    if (p.it?.length) body += `<div class="mgits">${p.it.map(([id, n]) => `<span class="mgit"><img src="itembild/${id}" alt="" loading="lazy" onerror="this.remove()">${esc(n)}</span>`).join("")}</div>`;
    if (p.text) body += `<div class="mgdesc">${mgMd(p.text, slug)}</div>`;
    if (p.o) body += (p.o.items.length ? (p.text ? `<h4>Items an dieser Stelle</h4>` : "") + itemRows(p.o.items) : "")
      + (p.o.menge ? `<p class="hint">${esc(p.o.menge)} Stück je Mal.</p>` : "") + (!p.text && !p.o.items.length && MOBJHINT[p.o.art] ? `<p class="hint">${esc(MOBJHINT[p.o.art])}</p>` : "");
    (p.drin || []).forEach((x) => { body += `<h4 data-tip="${esc(MOBJHINT[x.art] || "")}">${x.art === "kristall" ? "Pokémon im Kristallbrocken" : "Pokémon im Baum"}</h4>${itemRows(x.items)}`; });
    const quelle = p.t === "sp" ? "Spieldaten" : (p.q || []).join(" und ");
    $("#mapside").innerHTML = `<h3>${dot(c)} ${esc(p.t === "sp" ? (p.alpha ? "Alpha-Spawnpunkt" : "Spawnpunkt") : p.name || c.titel)}</h3>
      <p class="hint">${esc(c.g.titel)} · ${esc(c.titel)}${p.k && own.gebiete[p.k] ? " · " + esc(own.gebiete[p.k]) : ""}</p>${gotBtn}${body}
      ${quelle ? `<p class="hint" data-tip="${esc(p.q?.length > 1 ? "Map Genie und die Spieldaten haben hier dasselbe; beides ist zu einem Punkt zusammengeführt." : "")}">Quelle: ${esc(quelle)}${p.text ? ` (Text von ${esc(p.q?.[0] || "Map Genie")}, Begriffe übersetzt)` : ""}</p>` : ""}`;
    $("#gotbtn")?.addEventListener("click", () => toggle(i));
  };
  const listHits = () => {
    if (!q) return;
    const hits = pts.map((p, i) => [p, i]).filter(([p]) => match(p));          // auch ausgeblendete Ebenen; der Sprung blendet ein
    $("#mapside").innerHTML = `<h3>${hits.length} Treffer</h3>` + (hits.length > 60 ? `<p class="hint">Zu viele für eine Liste; genauer suchen.</p>` :
      `<div class="mghits">${hits.map(([p, i]) => `<button data-jump="${i}">${dot(cats[p.c])}<span>${esc(p.t === "sp" ? "Spawnpunkt: " + p.name : p.name || cats[p.c].titel)}</span></button>`).join("")}</div>`);
    $$("[data-jump]").forEach((b) => b.addEventListener("click", () => jump(+b.dataset.jump)));
  };
  const toggle = (i) => {
    const p = pts[i], k = gkey(p);
    if (!k) return;
    const on = !isGot(p);
    if (on) got.add(k); else got.delete(k);
    // früher getrennt als eigenes Symbol markiert: das fällt mit weg
    if (!on && p.t === "mg" && p.o && got.has(okeyOf(p))) { const ok = okeyOf(p); got.delete(ok); const [ka, ob] = ok.split("|"); api("/api/gefunden", {spiel: d.spiel, karte: ka, objekt: ob, an: false}).catch(ungespeichert(() => { got.add(ok); pins(); })); }
    const c = $(`[data-cnt="${CSS.escape(String(p.c))}"]`);
    if (c) c.innerHTML = cnt(cats[p.c]);
    pins();
    if (sel === i) side(i);
    const [karte, objekt] = k.split("|");
    if (p.aq) REQ_OK = false;          // der Reiter Aufträge liest die Haken neu
    api("/api/gefunden", {spiel: d.spiel, karte, objekt, an: on}).catch(ungespeichert(() => { if (on) got.delete(k); else got.add(k); pins(); }));
  };
  pl.addEventListener("click", (e) => {
    if (moved) return;
    const b = e.target.closest("[data-i]");
    if (!b) return;
    $$(".sel", pl).forEach((x) => x.classList.remove("sel"));
    b.classList.add("sel");
    sel = +b.dataset.i; side(sel);
  });
  pl.addEventListener("contextmenu", (e) => { const b = e.target.closest("[data-i]"); if (!b) return; e.preventDefault(); toggle(+b.dataset.i); });
  const catKey = (v) => (isNaN(+v) ? v : +v);
  const saveHide = () => { store.set(hk, [...hide]); $$("[data-cat]").forEach((b) => b.classList.toggle("on", !hide.has(catKey(b.dataset.cat)))); pins(); };
  $$("[data-cat]").forEach((b) => b.addEventListener("click", () => { const k = catKey(b.dataset.cat); if (hide.has(k)) hide.delete(k); else hide.add(k); saveHide(); }));
  $$("summary [data-grp]").forEach((b) => b.addEventListener("click", (e) => {
    e.preventDefault();
    const ks = groups[+b.dataset.grp].kategorien.map((c) => c.id), anyOn = ks.some((k) => !hide.has(k));
    ks.forEach((k) => { if (anyOn) hide.add(k); else hide.delete(k); });
    saveHide();
  }));
  $$("[data-all]").forEach((b) => b.addEventListener("click", () => { Object.values(cats).forEach((c) => { if (b.dataset.all === "1") hide.delete(c.id); else hide.add(c.id); }); saveHide(); }));
  $$("details.mgg").forEach((x) => x.addEventListener("toggle", () => { if (x.open) open.add(x.dataset.gid); else open.delete(x.dataset.gid); store.set("mgOpen", [...open]); }));
  $$("[data-gfold]").forEach((b) => b.addEventListener("click", () => $$("details.mgg").forEach((x) => { x.open = b.dataset.gfold === "1"; })));
  $("#gothide").addEventListener("change", (e) => { gotHide = e.target.checked; store.set("mapGotHide", gotHide); pins(); });
  pl.before(hl);
  hl.addEventListener("click", (e) => { if (moved) e.preventDefault(); });
  $("#mgheat")?.addEventListener("click", (e) => { heatOn = !heatOn; store.set("mgHeat", heatOn); e.currentTarget.classList.toggle("on", heatOn); heat(); if (heatOn && sel < 0 && !q) heatSide(); });
  if (heatOn && !want) heatSide();
  let qt;
  $("#mgq").addEventListener("input", (e) => { clearTimeout(qt); qt = setTimeout(() => { q = e.target.value.trim(); pins(); listHits(); }, 150); });
  // #karte/mg/<Karte>/k:<Kategorie>: nur diese Ebene zeigen (aus „Sammelobjekte“)
  if (want && want.startsWith("k:")) {
    const k = catKey(decodeURIComponent(want.slice(2)));
    if (cats[k]) { Object.values(cats).forEach((c) => { if (c.id === k) hide.delete(c.id); else hide.add(c.id); }); saveHide(); }
    return;
  }
  // #karte/mg/<Karte>/<Ort>: direkt dorthin
  if (want) { const i = pts.findIndex((p) => p.t === "mg" && String(p.id) === String(want)); if (i >= 0) jump(i); }
}
/* 0.55: Sammelobjekte (Geisterlichter, Icognito, Pflöcke, Schrauben …) aus allen Karten des Spiels mit Fortschritt; die
   Haken sind dieselben wie auf der Karte (Rechtsklick oder „als gefunden markieren“) */
async function collectView() {
  const rid = RID;
  const d = await api("/api/sammeln?" + qs({spiel: S.game})).catch(teil("Sammelobjekte", {sachen: []}));
  if (rid !== RID) return;
  const xs = d.sachen || [];
  const bar = (f, n) => `<span class="cbar" data-tip="${f} von ${n}"><span style="width:${n ? Math.round(100 * f / n) : 0}%"></span></span>`;
  const all = xs.reduce((a, x) => [a[0] + x.gefunden, a[1] + x.n], [0, 0]);
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Sammelobjekte</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      <span class="hint grow">${xs.length ? `${all[0]} von ${all[1]} gefunden` : ""}</span><a class="btn small" href="#karte">Zur Karte</a><a class="btn small" href="#fehlt">Was fehlt mir noch?</a></div>
    ${xs.length ? `<table class="ctab"><thead><tr><th>Was</th><th class="c">Fortschritt</th><th></th><th>Auf der Karte</th></tr></thead><tbody>${xs.map((x) =>
      `<tr class="${x.gefunden >= x.n ? "done" : ""}"><td><b>${esc(x.titel)}</b></td><td class="c num">${x.gefunden} / ${x.n}</td><td>${bar(x.gefunden, x.n)}</td>
        <td>${x.karten.map((k) => `<a href="#karte/mg/${esc(k.slug)}/k:${encodeURIComponent(k.kat)}" data-tip="Karte mit nur dieser Ebene öffnen">${esc(k.karte)}</a>${x.karten.length > 1 ? ` <span class="hint">${k.gefunden}/${k.n}</span>` : ""}`).join(" · ")}</td></tr>`).join("")}</tbody></table>`
      : `<p class="hint">Für ${esc(gameName())} gibt es auf den Karten keine Sammelobjekte (oder noch keine Karte).</p>`}
    <p class="hint">Gezählt aus den Karten: was in der Gruppe „Sammelobjekte“ steht, dazu Icognito und ähnliche. Abhaken auf der Karte per Rechtsklick
      auf ein Symbol oder mit „als gefunden markieren“ in den Details.</p></div>`;
  header();
}
/* 0.54: Was fehlt mir noch: Arten des Spiel-Dex ohne gefangene Form, gruppiert nach dem besten Weg dorthin */
const WEG = {jetzt: ["Geht jetzt", "Du hast eine Vorstufe (entwickeln) oder eine Weiterentwicklung (Ei)"],
  wild: ["Wild fangen", "Kommt in deiner Edition wild vor"], fest: ["Geschenk oder einmalig", "Geschenk, Tausch im Spiel oder eine feste Begegnung"],
  entwicklung: ["Entwickeln", "Entsteht aus einer Vorstufe, die du noch fangen musst"], raid: ["Tera-Raid", "Gibt es in Tera-Raids"],
  zucht: ["Züchten", "Schlüpft aus dem Ei einer Weiterentwicklung"], tausch: ["Tausch-Entwicklung", "Entwickelt sich nur beim Tausch"],
  edition: ["Andere Edition", "Nur in der anderen Edition: tauschen"], unklar: ["Sonst", "Kein Weg in den Daten: Geschenk, Event, Tausch oder ein anderes Spiel"],
  home: ["Übertragen", "In einem Spiel fangen und nach HOME übertragen"]};
/* 0.69.0: Fortschritt auf einen Blick (/api/fortschritt): alle Spiele und HOME mit gefangenen Arten, für das gewählte
   Spiel nach Generation und Typ; jede Zeile springt zu den fehlenden Pokémon (#fehlt/gen/3, #fehlt/typ/10) */
const pbar = (n, a) => `<span class="pbar" data-tip="${n} von ${a}"><i style="width:${a ? Math.round(100 * n / a) : 0}%"></i></span>`;
const anteil = (n, a) => a ? `${Math.floor(100 * n / a)} %` : "–";
async function progressView() {
  const rid = RID;
  const d = await api("/api/fortschritt?" + qs({spiel: S.game}));
  if (rid !== RID) return;
  const zeile = (x, href, attr = "") => `<tr${href ? ` class="click" data-href="${href}"` : attr}><td>${x.label}</td><td class="num">${x.gefangen}</td><td class="num">${x.arten}</td><td>${pbar(x.gefangen, x.arten)}</td><td class="num">${anteil(x.gefangen, x.arten)}</td>
    <td>${href && x.gefangen < x.arten ? `<a href="${href}" data-tip="Die fehlenden Pokémon dieser Zeile in „Was fehlt mir noch“">${x.arten - x.gefangen} fehlen</a>` : x.arten && x.gefangen === x.arten ? "✓" : ""}</td></tr>`;
  const kopf = (was) => `<tr><th>${was}</th><th>gefangen</th><th>Arten</th><th></th><th></th><th></th></tr>`;
  const fett = (x) => x.kennung === S.game ? `<b>${esc(x.name)}</b>` : esc(x.name);
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Fortschritt</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      <span class="hint grow">${d.gefangen} von ${d.arten} Arten in ${esc(d.name)} gefangen (${anteil(d.gefangen, d.arten)})</span>
      <a class="btn small" href="#fehlt">Was fehlt mir noch?</a><a class="btn small" href="#tausch">Tauschliste</a><a class="btn small" href="#pokemon">Zur Liste</a></div>
    <div class="cols"><div><h3>Nach Generation</h3><table class="rows prog">${kopf("Generation")}${d.generationen.map((x) => zeile({...x, label: `Generation ${x.gen}`}, `#fehlt/gen/${x.gen}`)).join("")}</table></div>
      <div><h3>Nach Typ</h3><table class="rows prog">${kopf("Typ")}${d.typen.map((x) => zeile({...x, label: esc(x.name)}, `#fehlt/typ/${x.id}`)).join("")}</table></div></div>
    <h3>Alle Spiele</h3><div class="scroll"><table class="rows prog">${kopf("Spiel")}${d.spiele.map((x) => zeile({...x, label: fett(x)}, null,
      ` class="click" data-spiel="${esc(x.kennung)}" data-tip="${esc(x.name)} wählen"`)).join("")}</table></div>
    <p class="hint">Gezählt wird je Art wie in „Was fehlt mir noch“: eine gefangene Form (Pokéball) reicht. Die Arten eines Spiels sind die seines Spiel-Dex,
      in HOME alle Arten. Eine Art mit zwei Typen zählt bei beiden.</p></div>`;
  header();
  $$("tr[data-href]", main).forEach((tr) => tr.addEventListener("click", (e) => { if (!e.target.closest("a")) location.hash = tr.dataset.href; }));
  $$("tr[data-spiel]", main).forEach((tr) => tr.addEventListener("click", () => setGame(tr.dataset.spiel)));
}
/* 0.70.0: Shiny-Jagd (/api/jagd): Zähler je Jagd mit Methode, Optionen und Schillerpin. Quote und Wahrscheinlichkeit
   „bis jetzt“ rechnet der Server (app/jagd.py, Tabelle extra/shiny_quoten.json); hier wird nur gezeigt und gezählt.
   Leertaste oder + zählt die oberste Jagd, − nimmt eine zurück. #jagd/neu/<Form> legt eine Jagd an (Detailseite). */
let JAGD = null;
const prozent = (x) => x === null || x === undefined ? "–" : `${(100 * x).toLocaleString("de-DE", {maximumFractionDigits: x < 0.1 ? 1 : 0})} %`;
const einsZu = (x) => x ? `1 zu ${x.toLocaleString("de-DE", {maximumFractionDigits: x < 1000 ? 2 : 0})}` : "–";
const SPERRE = {tausch: "Shiny-Sperre: in diesem Spiel nur per Tausch schillernd zu bekommen.", nie: "Shiny-Sperre: in diesem Spiel nie schillernd."};
function huntCard(j) {
  const M = JAGD.methoden || [], m = M.find((x) => x.id === j.methode);
  const opts = (m?.optionen || []).map((o) => `<label class="hint">${esc(o.name)} <select data-jopt="${esc(o.id)}">${o.werte.map((w, i) =>
    `<option value="${i}"${(j.optionen[o.id] || 0) === i ? " selected" : ""}>${esc(w)}</option>`).join("")}</select></label>`).join("");
  return `<div class="box jagd${j.angeheftet ? " pin" : ""}" data-jid="${j.id}">
    <div class="bar">${img(j.form)}<h3 style="margin:0"><a href="#pokemon/${j.form}">${esc(j.name)}</a></h3>
      ${M.length ? `<select data-jm data-tip="Methode">${M.map((x) => `<option value="${esc(x.id)}"${x.id === j.methode ? " selected" : ""}>${esc(x.name)}</option>`).join("")}</select>` : `<span class="hint">${esc(j.methode_name)}</span>`}
      ${opts}${JAGD.pin ? `<label class="hint" data-tip="Der Schillerpin bringt in diesem Spiel zusätzliche Würfe"><input type="checkbox" data-jpin${j.pin ? " checked" : ""}> Schillerpin</label>` : ""}
      <span class="grow"></span>
      <button class="small${j.angeheftet ? " on" : ""}" data-jact="anheften" data-tip="${j.angeheftet ? "Nicht mehr anheften" : "Anheften: steht oben, die oberste Jagd zählt mit der Tastatur"}">📌</button>
      <button class="small x" data-jact="loeschen" data-tip="Jagd löschen">✕</button></div>
    ${j.sperre ? `<div class="note warn">${SPERRE[j.sperre] || esc(j.sperre)}</div>` : ""}
    <div class="jzahl">
      <button class="jminus" data-jact="minus" data-tip="Eine Begegnung zurück (Taste −)">−</button>
      <button class="jplus primary" data-jact="plus" data-tip="Eine Begegnung mehr (Leertaste oder +)"><b>${j.zaehler.toLocaleString("de-DE")}</b><span>Begegnungen</span></button>
      <div class="jinfo">
        <div>Quote jetzt: <b>${einsZu(j.eins_zu)}</b>${j.wuerfe ? ` <span class="hint">(${j.wuerfe} ${j.wuerfe === 1 ? "Wurf" : "Würfe"})</span>` : ""}</div>
        <div>Bis jetzt hätten <b>${prozent(j.schon)}</b> schon eins gefunden.</div>
        ${j.hinweise.map((h) => `<div class="hint">${esc(h)}</div>`).join("")}
        <div class="bar slim"><input type="number" min="0" value="${j.zaehler}" data-jwert style="width:100px" data-tip="Zählerstand setzen (Enter)">
          <input type="text" value="${esc(j.notiz || "")}" data-jnotiz placeholder="Notiz" maxlength="300" class="grow">
          <button class="small" data-jact="gefunden" data-tip="Jagd abschließen; das Pokémon gilt dann in diesem Spiel als schillernd gefangen">Gefunden ✨</button></div>
      </div></div>
    ${m?.text ? `<p class="hint">${esc(m.text)}</p>` : ""}</div>`;
}
async function huntView(neu, form) {
  const rid = RID;
  const d = await api("/api/jagd?" + qs({spiel: S.game}));
  if (rid !== RID) return;
  if (neu === "neu" && +form && d.methoden) {
    await api("/api/jagd", {spiel: S.game, form: +form, methode: d.methoden[0].id}).catch(ungespeichert());
    location.replace("#jagd");
    return;
  }
  JAGD = d;
  const dt = (s) => esc(String(s || "").slice(0, 10).split("-").reverse().join("."));
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Shiny-Jagd</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      <span class="hint grow">${d.methoden ? `Grundquote 1 zu ${d.nenner.toLocaleString("de-DE")}` : ""}</span>
      <a class="btn small" href="#fortschritt">Fortschritt</a><a class="btn small" href="#pokemon">Zur Liste</a></div>
    ${d.methoden ? `<div class="bar"><div class="ac"><input id="jagdq" type="search" placeholder="Neue Jagd: Pokémon suchen" style="width:220px"></div></div>` : ""}
    ${d.text ? `<div class="note ${d.methoden ? "info" : "warn"}">${esc(d.text)}</div>` : ""}
    <p class="hint">Der Zähler zählt Begegnungen (bei Ketten die Länge der Kette); die Quote gilt für die nächste. „Bis jetzt“: Anteil der Jäger,
      die mit so vielen Begegnungen schon eins gefunden hätten. Leertaste oder + zählt die oberste Jagd, − nimmt eine zurück.
      Quellen: ${d.quellen.map(([n, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(n)} ↗</a>`).join(", ")}.</p></div>
    <div id="jagden">${d.jagden.map(huntCard).join("") || (d.methoden ? `<p class="hint">Noch keine laufende Jagd in ${esc(gameName())}.</p>` : "")}</div>
    ${d.gefunden.length ? `<div class="box"><h3>Gefunden</h3><table class="rows jfund"><tbody>${d.gefunden.map((j) => `<tr data-jid="${j.id}">
      <td>${img(j.form, "sm")} <a href="#pokemon/${j.form}">${esc(j.name)}</a></td><td class="hint">${esc(j.methode_name)}</td>
      <td class="num">${j.zaehler.toLocaleString("de-DE")} Begegnungen</td><td class="hint nw">${dt(j.start)} bis ${dt(j.gefunden)}</td><td class="hint">${esc(j.notiz || "")}</td>
      <td class="nw"><button class="small" data-jact="weiter" data-tip="Jagd wieder aufnehmen (die Marke schillernd bleibt)">Weiter</button>
        <button class="small x" data-jact="loeschen" data-tip="Eintrag löschen">✕</button></td></tr>`).join("")}</tbody></table></div>` : ""}`;
  header();
  if (d.methoden) autocomplete($("#jagdq"), (r) => api("/api/jagd", {spiel: S.game, form: r.id, methode: d.methoden[0].id}).then(() => huntView()).catch(ungespeichert()));
}
// Eine Jagd neu zeichnen (Antwort des Servers); ohne Antwort die Ansicht neu laden
function huntPut(j) {
  const el = $(`#jagden [data-jid="${j.id}"]`);
  if (el) el.outerHTML = huntCard(j); else huntView();
}
function huntCount(el, plus, wert) {
  const id = +el.dataset.jid, b = $(".jplus b", el), alt = b.textContent;
  const n = Math.max(0, wert ?? ((JAGD.jagden.find((j) => j.id === id)?.zaehler || 0) + plus));
  const j = JAGD.jagden.find((x) => x.id === id);
  if (j) j.zaehler = n;
  b.textContent = n.toLocaleString("de-DE");
  api("/api/jagd/zaehlen", wert === undefined ? {id, plus} : {id, wert}).then((x) => { if (j) Object.assign(j, x); huntPut(x); })
    .catch(ungespeichert(() => { b.textContent = alt; if (j) j.zaehler = +alt.replace(/\D/g, ""); }));
}
function huntSave(id, body, ganz) {
  return api("/api/jagd", Object.assign({id}, body)).then((x) => { if (ganz) huntView(); else huntPut(x); }).catch(ungespeichert(() => huntView()));
}
main.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-jact]"), el = b?.closest("[data-jid]");
  if (!b || !el || !JAGD) return;
  const id = +el.dataset.jid, j = [...JAGD.jagden, ...JAGD.gefunden].find((x) => x.id === id), act = b.dataset.jact;
  if (act === "plus" || act === "minus") huntCount(el, act === "plus" ? 1 : -1);
  else if (act === "anheften") huntSave(id, {angeheftet: !j?.angeheftet}, true);
  else if (act === "gefunden") huntSave(id, {gefunden: true}, true).then(() => loadCaught(true)).catch(teil("Sammlung", null));
  else if (act === "weiter") huntSave(id, {gefunden: false}, true);
  else if (act === "loeschen" && await ask(`Jagd auf ${j?.name || "dieses Pokémon"} löschen?`, `Der Zähler (${j?.zaehler ?? 0}) geht verloren.`, "Löschen", true))
    api("/api/jagd/loeschen", {id}).then(() => huntView()).catch(ungespeichert());
});
main.addEventListener("change", (e) => {
  const el = e.target.closest("#jagden [data-jid]");
  if (!el) return;
  const id = +el.dataset.jid, t = e.target;
  if (t.matches("[data-jm]")) huntSave(id, {methode: t.value, optionen: {}});
  else if (t.matches("[data-jopt]")) huntSave(id, {optionen: Object.fromEntries($$("[data-jopt]", el).map((s) => [s.dataset.jopt, +s.value]))});
  else if (t.matches("[data-jpin]")) huntSave(id, {pin: t.checked});
  else if (t.matches("[data-jwert]")) huntCount(el, 0, Math.max(0, Math.floor(+t.value || 0)));
  else if (t.matches("[data-jnotiz]")) huntSave(id, {notiz: t.value});
});
document.addEventListener("keydown", (e) => {
  if (!location.hash.startsWith("#jagd") || !JAGD || e.ctrlKey || e.metaKey || e.altKey || e.target.closest("input, select, textarea, dialog")) return;
  const top = $("#jagden [data-jid]");
  if (!top) return;
  if (e.key === " " || e.key === "+") { e.preventDefault(); huntCount(top, 1); }
  else if (e.key === "-") { e.preventDefault(); huntCount(top, -1); }
});
/* 0.71.0: Tauschliste (/api/tausch): was nur ein Tauschpartner geben kann (andere Edition, Tausch-Entwicklung, ohne Weg in
   den Daten) und was du bieten kannst; die Liste zum Kopieren baut der Server (text). Edition wie in „Was fehlt mir noch“ */
async function tradeView() {
  const rid = RID, ek = "edition:" + S.game;
  let ed = store.get(ek, "");
  const d = await api("/api/tausch?" + qs({spiel: S.game, edition: ed}));
  if (rid !== RID) return;
  const kachel = (x) => `<a class="tk${x.hast ? " hast" : ""}" href="#pokemon/${x.id}" data-hc="${x.id}" data-tip="${esc(x.text)}">${img(x.id, "sm")}<span><span class="hint">#${esc(x.dexk || "")}${x.nr}</span> ${esc(x.name)}${x.hast ? ` <b class="fok">${x.text.startsWith("nur in") ? "gefangen" : "Vorstufe da"}</b>` : ""}</span></a>`;
  const block = (titel, rows, tip, zu) => rows.length ? `<details class="sub"${zu ? "" : " open"}><summary>${esc(titel)} <span class="hint">${rows.length}</span></summary>
      ${tip ? `<p class="hint">${esc(tip)}</p>` : ""}<div class="tks">${rows.map(kachel).join("")}</div></details>` : "";
  const TIP = {edition: "Fehlt dir und gibt es wild nur in der anderen Edition; auch nicht über eine Vorstufe oder ein Ei aus deiner Edition.",
    tausch: "Entwickelt sich nur durch Tausch: Vorstufe hinschicken und zurücktauschen lassen.",
    unklar: "Kein Fundort und keine Entwicklung in den Daten. Oft hilft ein Tausch aus einem anderen Spiel, sicher ist es nicht; steht deshalb nicht in der Liste zum Kopieren."};
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Tauschliste</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      ${d.editionen.length ? `<select id="ted" data-tip="Deine Edition"><option value="">Edition wählen</option>${d.editionen.map((e) => `<option${e === d.edition ? " selected" : ""}>${esc(e)}</option>`).join("")}</select>` : ""}
      <span class="grow"></span><a class="btn small" href="#fehlt">Was fehlt mir noch?</a><a class="btn small" href="#fortschritt">Fortschritt</a></div>
    ${d.hinweis ? `<div class="note info">${esc(d.hinweis)}</div>` : ""}
    <p class="hint">Aus „Was fehlt mir noch“: dieselben Arten und Wege, gefangen zählt je Art.</p></div>
    ${d.gruppen.length ? `<div class="cols"><div class="box"><h3>Suche</h3>${d.gruppen.map((g) => block(g.titel, g.rows, TIP[g.id], g.id === "unklar")).join("") || `<p class="hint">Nichts.</p>`}</div>
      <div class="box"><h3>Biete${d.edition ? ` (nur in ${esc(d.edition)})` : ""}</h3>${d.biete.length ? `<div class="tks">${d.biete.map(kachel).join("")}</div>` : `<p class="hint">Nichts erkannt.</p>`}
        <h3>Zum Kopieren</h3><textarea id="ttext" rows="12" readonly style="width:100%">${esc(d.text)}</textarea>
        <div class="bar"><button id="tcopy" class="primary" data-tip="Die Liste in die Zwischenablage, etwa für einen Tauschpartner">Kopieren</button></div></div></div>` : ""}`;
  header();
  $("#ted")?.addEventListener("change", (e) => { store.set(ek, e.target.value); tradeView(); });
  $("#tcopy")?.addEventListener("click", (e) => copyText(d.text, e.target));
}
async function missingView(nach, wert) {
  const rid = RID, ek = "edition:" + S.game;
  // 0.69.0: aus dem Fortschritt nur eine Generation oder einen Typ (#fehlt/gen/3, #fehlt/typ/10)
  const nur = nach === "gen" ? {gen: +wert, text: `Generation ${+wert}`} : nach === "typ" ? {typ: +wert, text: S.types[+wert] || "Typ"} : null;
  let ed = store.get(ek, ""), q = "", weg = store.get("fehltWeg", "");
  const load = () => api("/api/fehlt?" + qs({spiel: S.game, edition: ed}));
  let d = await load();
  if (rid !== RID) return;
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Was fehlt mir noch?</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      <span id="fed"></span><input id="fq" type="search" placeholder="Pokémon oder Ort" style="width:200px"><span class="hint grow" id="fcnt"></span>
      ${nur ? `<a class="btn small on" href="#fehlt" data-tip="Wieder alle fehlenden zeigen">nur ${esc(nur.text)} ×</a>` : ""}
      <a class="btn small" href="#tausch" data-tip="Was du nur über einen Tauschpartner bekommst, und was du bieten kannst, als Liste zum Kopieren">Tauschliste</a><a class="btn small" href="#fortschritt" data-tip="Wie viel du je Spiel, Generation und Typ schon hast">Fortschritt</a><a class="btn small" href="#sammeln">Sammelobjekte</a><a class="btn small" href="#pokemon">Zur Liste</a></div>
    <div class="bar"><span class="seg" id="fseg"></span></div><div id="fbody"></div>
    <p class="hint">Gezählt wird je Art: eine gefangene Form (Pokéball) reicht. Wege aus den Fundorten des Spiels (Spieldaten oder PokéAPI), den Entwicklungen und,
      wo es Zucht gibt, den Eiern einer Weiterentwicklung. Den Pokéball auf einer Karte kannst du gleich hier setzen.</p></div>`;
  header();
  const draw = () => {
    $("#fed").innerHTML = d.editionen.length ? `<select id="fedsel" data-tip="Deine Edition: was nur die andere hat, steht unter „Andere Edition“"><option value="">beide Editionen</option>${d.editionen.map((e) =>
      `<option${e === ed ? " selected" : ""}>${esc(e)}</option>`).join("")}</select>` : "";
    $("#fedsel")?.addEventListener("change", async (e) => { ed = e.target.value; store.set(ek, ed); d = await load(); if (rid === RID) draw(); });
    const ql = q.toLowerCase();
    const xs = d.fehlt.filter((x) => (!nur || (nur.gen ? x.gen === nur.gen : x.typen.includes(nur.typ)))
      && (!ql || x.name.toLowerCase().includes(ql) || x.wege.some((w) => (w.text || "").toLowerCase().includes(ql))));
    const by = {};
    xs.forEach((x) => (by[x.weg] ||= []).push(x));
    const ks = Object.keys(WEG).filter((k) => by[k]);
    if (weg && !by[weg]) weg = "";
    $("#fcnt").textContent = `${d.gefangen} von ${d.arten} Arten gefangen, ${d.fehlt.length} fehlen`;
    $("#fseg").innerHTML = `<button data-w=""${weg ? "" : ' class="on"'}>alle ${xs.length}</button>` + ks.map((k) =>
      `<button data-w="${k}"${weg === k ? ' class="on"' : ""} data-tip="${esc(WEG[k][1])}">${esc(WEG[k][0])} ${by[k].length}</button>`).join("");
    $$("#fseg button").forEach((b) => b.addEventListener("click", () => { weg = b.dataset.w; store.set("fehltWeg", weg); draw(); }));
    const card = (x) => {
      const main1 = x.wege.find((w) => w.art === x.weg) || x.wege.find((w) => w.hast) || x.wege[0];
      const more = x.wege.filter((w) => w !== main1);
      const line = (w) => `<span class="fw fw-${w.art}">${esc(WEG[w.art]?.[0] || w.art)}</span> ${esc(w.text || "")}${w.hast ? ` <b class="fok">${w.hast_name && w.hast_name !== w.von_name ? `hast ${esc(w.hast_name)}` : "hast du"}</b>` : ""}`;
      // 0.56.2: die Standard-Karte der Liste (mit Hover-Karte und Knöpfen), dazu nur der Weg; alle Wege im Hinweis und auf der Detailseite
      const badge = (w, cls = "") => `<span class="fw fw-${w.art}${cls}">${esc(WEG[w.art]?.[0] || w.art)}</span>`;
      const hast = main1.hast ? ` <b class="fok">${main1.hast_name && main1.hast_name !== main1.von_name ? `hast ${esc(main1.hast_name)}` : "hast du"}</b>` : "";
      return monCard(x, false, `<span class="s fway" data-tip="${esc(x.wege.map((w) => (WEG[w.art]?.[0] || w.art) + ": " + w.text).join("\n"))}">${badge(main1)}${hast}${
        [...new Set(more.map((w) => w.art))].filter((a) => a !== main1.art).slice(0, 2).map((a) => " " + badge({art: a}, " alt")).join("")}</span>`);
    };
    d.fehlt.forEach((x) => { ROWS[x.id] = Object.assign(ROWS[x.id] || {}, x); });
    $("#fbody").innerHTML = (weg ? [weg] : ks).map((k) => `<div class="fsec"><h3 data-fold="fehlt-${k}">${esc(WEG[k][0])} <span class="hint">${by[k].length} · ${esc(WEG[k][1])}</span></h3>
      <div class="list">${by[k].map(card).join("")}</div></div>`).join("")
      || `<p class="hint">${d.fehlt.length ? "Nichts gefunden." : `Du hast alle ${d.arten} Arten in ${esc(gameName())}. Glückwunsch!`}</p>`;
  };
  draw();
  $("#fq").addEventListener("input", (e) => { q = e.target.value.trim(); draw(); });
  // Pokéball gesetzt: die Karte wird blass; erst beim nächsten Öffnen fällt sie aus der Liste
  $("#fbody").addEventListener("click", (e) => {
    const b = e.target.closest('[data-act="caught"]');
    if (b) { const id = +b.dataset.id; setTimeout(() => $$(`#fbody .mon[data-id="${id}"]`).forEach((c) => c.classList.toggle("got", isCaught(id))), 400); }
  });
}
async function areasView(want) {
  const rid = RID;
  const d = await api("/api/gebiete?" + qs({spiel: S.game})).catch(teil("Gebiete", null));
  if (rid !== RID) return;
  if (!d || !d.gebiete.length) {
    main.innerHTML = `<div class="box"><h2>Gebiete</h2><p class="hint">Für ${esc(gameName())} gibt es keine Fundorte in den Daten.</p>
      <p><a href="#karte/obsidianfieldlands">Karte von Legenden: Arceus öffnen</a></p></div>`;
    return;
  }
  const key = "gebiet:" + S.game;
  let sel = want ? decodeURIComponent(want) : store.get(key, d.gebiete[0].ort), q = "", miss = store.get("gebietFehlend", false);
  if (!d.gebiete.some((g) => g.ort === sel)) sel = d.gebiete[0].ort;
  main.innerHTML = `<div class="box"><div class="bar"><h2 style="margin:0">Gebiete</h2><span class="hint">Spiel</span><select class="gamesel"></select>
      <input id="gq" type="search" placeholder="Ort oder Pokémon" style="width:220px">
      <label data-tip="Pokémon, die du in diesem Spiel schon gefangen hast, ausblenden"><input type="checkbox" id="gmiss"${miss ? " checked" : ""}> nur noch nicht gefangene</label>
      ${PROFIL().spawnkarten ? `<a class="btn" href="#karte/obsidianfieldlands">Zur Karte</a>` : ""}<span class="hint grow">${d.gebiete.length} Orte</span></div>
    <div class="gwrap"><nav class="glist" id="glist"></nav><div class="gmain" id="gmain"></div></div>
    <p class="hint">Quelle: ${d.quelle === "PKHeX" ? "Spieldaten (PKHeX)" : "PokéAPI"}. Anteil: so oft erscheint es mit dieser Methode (Summe der Plätze).</p></div>`;
  header();
  const own = (m) => isCaught(m.id);
  const list = () => {
    const ql = q.toLowerCase();
    $("#glist").innerHTML = d.gebiete.filter((g) => !ql || g.ort.toLowerCase().includes(ql) || g.mons.some((m) => m.name.toLowerCase().includes(ql)))
      .map((g) => { const ids = new Set(g.mons.map((m) => m.id)), left = [...ids].filter((i) => !isCaught(i)).length;
        return `<button class="${g.ort === sel ? "on" : ""}" data-g="${esc(g.ort)}"><span>${esc(g.ort)}</span><span class="hint" data-tip="noch nicht gefangen / Pokémon">${left ? left + "/" : "✓ "}${ids.size}</span></button>`; }).join("")
      || `<p class="hint">Nichts gefunden.</p>`;
    $$("#glist [data-g]").forEach((b) => b.addEventListener("click", () => { sel = b.dataset.g; store.set(key, sel); list(); show(); }));
  };
  const show = () => {
    const g = d.gebiete.find((x) => x.ort === sel);
    const ms = g.mons.filter((m) => !miss || !own(m));
    const by = {};
    ms.forEach((m) => (by[m.methode || "–"] ||= []).push(m));
    $("#gmain").innerHTML = `<h3>${areaName(g.ort)}</h3>` + (Object.entries(by).map(([meth, xs]) => `<h4>${esc(meth)}</h4><div class="ggrid">${xs.map((m) =>
      `<a class="gmon${own(m) ? " got" : ""}" href="#pokemon/${m.id}" data-id="${m.id}">${img(m.id)}${own(m) ? `<span class="gball">${ball(m.id)}</span>` : ""}<b>${esc(m.name)}</b>
        <span class="hint">${m.level ? "Lv " + esc(m.level) : ""}${m.anteil ? ` · ${m.anteil} %` : ""}${m.alpha ? ` · <span class="alpha">Alpha</span>` : ""}</span>
        ${m.editionen.length ? `<span class="ged">nur ${esc(m.editionen.join(", "))}</span>` : ""}${m.bedingungen.length ? `<span class="hint">${esc(m.bedingungen.join(", "))}</span>` : ""}</a>`).join("")}</div>`).join("")
      || `<p class="hint">${miss ? "Hier hast du schon alles gefangen." : "Keine Pokémon."}</p>`);
  };
  $("#gq").addEventListener("input", (e) => { q = e.target.value.trim(); list(); });
  $("#gmiss").addEventListener("change", (e) => { miss = e.target.checked; store.set("gebietFehlend", miss); list(); show(); });
  list(); show();
  const on = $("#glist .on"), gl = $("#glist");
  if (on) gl.scrollTop = on.offsetTop - gl.offsetTop - gl.clientHeight / 2;     // nur die Liste scrollen, nicht die Seite
}
async function mapView(karte, fid) {
  const rid = RID;
  const key = karte || "obsidianfieldlands";
  let d = MAPCACHE[key];
  if (!d) {
    try { d = MAPCACHE[key] = await api("/api/karte/" + encodeURIComponent(key)); } catch (e) {
      if (e.status !== 404) throw e;
      // 0.59.0: Die Spawnpunkte fehlen (Quelle beim Abgleich nicht erreicht): sagen, woran es liegt, statt „Fehler: keine Karte“
      main.innerHTML = `<div class="box"><h2>Karte</h2><p>Für diese Karte sind noch keine Kartendaten da. Der Abgleich holt sie; ob eine Quelle gefehlt hat, steht im Protokoll.</p>
        <a class="btn" href="#einstellungen">Einstellungen, Abgleich</a> <a class="btn" href="#karte/gebiete">Gebiete</a></div>`;
      return;
    }
  }
  /* gefundene Symbole (Geisterlichter, Icognito, Kisten …): je Karte; Schlüssel Art:x:z, damit er einen Neubau übersteht */
  const gotRes = await api("/api/gefunden?" + qs({spiel: MAPSPIEL, karte: key})).catch(teil("Abgehakte Symbole", {}));
  if (rid !== RID) return;
  if (!$("#map")) window.scrollTo(0, 0);
  const got = new Set(gotRes[key] || []);
  let gotHide = store.get("mapGotHide", false);
  /* Tageszeit und Wetter: -1 = alle; der Anteil eines Pokémon ist dann der höchste unter den gewählten Bedingungen */
  const fz = store.get("mapZeit", -1), fw = store.get("mapWetter", -1), cond = fz >= 0 || fw >= 0;
  const sh = (m) => !cond || !m.c ? m.max || 0 : Math.max(0, ...m.c.filter((v, i) => (fz < 0 || Math.floor(i / 9) === fz) && (fw < 0 || i % 9 === fw)));
  const pts = d.punkte.map((p) => Object.assign(p, {hit: fid != null && p.mons.some((m) => m.id === fid && sh(m) > 0), off: cond && !p.mons.some((m) => sh(m) > 0)}));
  const species = {};
  pts.forEach((p) => p.mons.forEach((m) => { (species[m.id] ||= {id: m.id, name: m.name, n: 0}).n++; }));
  const hits = pts.filter((p) => p.hit).length;
  const objs = (d.objekte || []).map((o) => Object.assign(o, {hit: fid != null && MOBJMON.has(o.art) && o.items.some((e) => e[2] === fid)}));
  objs.forEach((o) => { if (MOBJMON.has(o.art)) o.items.forEach(([n, , id]) => { if (id) (species[id] ||= {id, name: n.replace(/ \(.*\)$/, ""), n: 0}).n++; }); });
  const list = Object.values(species).sort((a, b) => a.name.localeCompare(b.name, "de"));
  const arten = d.arten || {};
  const ohits = objs.filter((o) => o.hit).length;
  const hide = new Set(store.get("mapHide", ["boden"]));      // Items am Boden sind viele: anfangs aus
  let heatOn = store.get("mapHeat", false);
  const H = mapHeat(pts, objs, sh);
  const layerBtn = (k, label, n) => `<button class="mlay${hide.has(k) ? "" : " on"}" data-lay="${k}" data-tip="${hide.has(k) ? "einblenden" : "ausblenden"}">${k === "pokemon"
    ? `<span class="mpin-l"></span>` : `<span class="mobj o-${k}">${MOBJ[k] || "•"}</span>`}${esc(label)} <span class="hint" data-cnt="${k}">${cnt(k, n)}</span></button>`;
  const cnt = (k, n) => { const f = k === "pokemon" ? 0 : objs.filter((o) => o.art === k && got.has(okey(o))).length; return f ? `${f}/${n} ✓` : n; };
  const lays = [...(pts.length ? [["pokemon", "Spawnpunkte", pts.length]] : []), ...Object.entries(arten).map(([k, v]) => [k, v[1], objs.filter((o) => o.art === k).length])];
  const known = new Set(MGROUPS.flatMap((g) => g[1]));
  const groups = [...MGROUPS.map(([n, ks]) => [n, ks.map((k) => lays.find((l) => l[0] === k)).filter(Boolean)]), ["Weitere", lays.filter((l) => !known.has(l[0]))]].filter((g) => g[1].length);
  const mopen = new Set(store.get("mapOpen", groups.map((g) => g[0])));
  const layerBar = groups.map(([n, ls], gi) => `<details class="mgg"${mopen.has(n) ? " open" : ""} data-gid="${esc(n)}"><summary>${esc(n)} <span class="hint">${ls.reduce((a, l) => a + l[2], 0)}</span>
    <button class="link" data-grp="${gi}" data-tip="ganze Gruppe ein- oder ausblenden">ein/aus</button></summary><div class="mlays">${ls.map((l) => layerBtn(...l)).join("")}</div></details>`).join("");
  const hasCond = pts.some((p) => p.mons.some((m) => m.c));
  const condSel = (key, label, names, v) => `<label class="mcond">${label} <select data-cond="${key}"><option value="-1">alle</option>${names.map((x, i) => `<option value="${i}"${i === v ? " selected" : ""}>${esc(x)}</option>`).join("")}</select></label>`;
  main.innerHTML = `<div class="box mapbox">
    <div class="bar"><h2 style="margin:0">Karte</h2>
      <span class="seg">${d.karten.map((k) => `<a class="btn${k.karte === d.karte ? " on" : ""}" href="#karte/${k.karte}${fid != null ? "/" + fid : ""}">${esc(k.gebiet)}</a>`).join("")}</span>
      <a class="btn" href="#karte/gebiete" data-tip="Alle Orte mit ihren Pokémon als Liste">Gebiete</a>
      <a class="btn" href="#karte/mg" data-tip="Karte von Map Genie mit Orten, Sammelobjekten und Materialien (wenn geladen)">Map Genie</a>
      ${pts.length ? `<div class="pick" id="mapmon"><button class="pickbtn" aria-haspopup="true" aria-expanded="false">${fid != null && species[fid] ? img(fid) + `<b>${esc(species[fid].name)}</b>` : "Pokémon wählen"} <span class="hint">▾</span></button>
        <div class="pickm" hidden><input type="search" placeholder="Pokémon suchen" aria-label="Pokémon suchen">
          <div class="pickl"><a href="#karte/${d.karte}" class="${fid == null ? "on" : ""}"><span class="spr none"></span><span>alle Spawnpunkte</span><span class="hint">${pts.length}</span></a>${list.map((s) => `<a href="#karte/${d.karte}/${s.id}" class="${s.id === fid ? "on" : ""}" data-n="${esc(s.name.toLowerCase())}">${img(s.id)}<span>${esc(s.name)}</span><span class="hint" data-tip="Stellen in diesem Gebiet">${s.n}</span></a>`).join("")}</div></div></div>
      <span class="hint grow">${fid != null ? (hits || ohits ? [hits && `${hits} Spawnpunkte`, ohits && `${ohits} weitere Stellen`].filter(Boolean).join(" und ") + " hervorgehoben" : "hier an keinem Spawnpunkt") : `${pts.length} Spawnpunkte, davon ${pts.filter((p) => p.alpha).length} Alpha`}</span>` : ""}
</div>
    ${objs.length || pts.length ? `<div class="bar mlays">${pts.length ? `<button class="mlay heatbtn${heatOn ? " on" : ""}" id="heatbtn" data-tip="Wo es welche Pokémon gibt: Bilder je Kartenfeld, je größer, desto wahrscheinlicher">▦ Übersicht mit Bildern</button>` : ""}${hasCond ? condSel("mapZeit", "Tageszeit", d.zeiten || [], fz) + condSel("mapWetter", "Wetter", d.wetterarten || [], fw) : ""}
      ${objs.length ? `<label class="mgot" data-tip="Symbole, die du als erledigt markiert hast (Rechtsklick auf ein Symbol oder ✓ in den Details), ausblenden"><input type="checkbox" id="gothide"${gotHide ? " checked" : ""}> gefundene ausblenden</label>` : ""}
</div>` : ""}
    ${S.game && !PROFIL().spawnkarten ? `<div class="note info">Für ${esc(gameName())} gibt es noch keine Karte; gezeigt ist Legenden: Arceus. <a href="#karte/gebiete">Gebiete von ${esc(gameName())}</a></div>` : ""}
    ${d.kacheln || d.bild ? "" : `<div class="note">Das Kartenbild fehlt noch; der nächste Abgleich lädt es (Einstellungen → Abgleich). Die Spawnpunkte stimmen trotzdem.</div>`}
    <div class="mapwrap"><div class="mapcol"><div id="map" class="map"><div class="mapin"><div class="tiles"></div><div class="pins"></div></div></div>
      <div class="mapzoom"><button data-mz="1" data-tip="näher">+</button><input type="range" id="mapz" aria-label="Zoom" data-tip="Zoom stufenlos"><button data-mz="-1" data-tip="weiter weg">−</button><button data-mz="0" data-tip="ganze Karte">⤢</button></div></div>
      <div class="mgside"><aside id="mapside" class="mapside"><p class="hint">${pts.length ? "Fahre über einen Punkt für die Pokémon dort, klicke für Details. Rot: Alpha." : "Fahre über ein Symbol für Einzelheiten, klicke für die Liste."}${objs.length ? " Rechtsklick auf ein Symbol markiert es als gefunden." : ""}</p></aside>
      ${lays.length ? `<div class="mgcats"><div class="bar"><b>Ebenen</b><span class="mlay-all"><button class="link" data-layall="1" data-tip="alle Ebenen einblenden">alle</button> · <button class="link" data-layall="0" data-tip="alle Ebenen ausblenden">keine</button>
        <span class="hint">|</span> <button class="link" data-gfold="1" data-tip="alle Gruppen aufklappen">auf</button> · <button class="link" data-gfold="0" data-tip="alle Gruppen zuklappen">zu</button></span></div>${layerBar}</div>` : ""}</div></div>
    <p class="hint">Kartenbild: ${d.bild ? "Altissimo" : "Serebii"}${pts.length ? "; Spawnpunkte und Tabellen: PLA-Live-Map und JS-Finder (GPL-3.0), aus den Spieldaten" : ""}${objs.length ? "; Symbole und Sammelobjekte: Altissimo (GPL-3.0)" : ""}${objs.some((o) => MOBJMON.has(o.art) || o.art === "boden") ? "; Kristalle, Verzerrungen, Massenauftreten, Bäume, Alphas und Items am Boden: PokéWiki (CC BY-SA 3.0)" : ""}${objs.some((o) => o.art === "reise" || o.art === "lager") ? "; Schnellreise und Lager: PLA Companion (software-notion.de)" : ""}.</p></div>`;
  const pick = $("#mapmon") || document.createElement("div"), pickM = $(".pickm", pick) || document.createElement("div");
  const pickOpen = (on) => { pickM.hidden = !on; $(".pickbtn", pick).setAttribute("aria-expanded", on); if (on) { const f = $("input", pickM); f.value = ""; pickFilter(""); f.focus(); $("a.on", pickM)?.scrollIntoView({block: "center"}); } };
  const pickFilter = (v) => $$(".pickl a[data-n]", pick).forEach((a) => { a.hidden = !!v && !a.dataset.n.includes(v); });
  $(".pickbtn", pick)?.addEventListener("click", () => pickOpen(pickM.hidden));
  $("input", pickM)?.addEventListener("input", (e) => pickFilter(e.target.value.trim().toLowerCase()));
  pick.addEventListener("keydown", (e) => {
    if (e.key === "Escape") pickOpen(false);
    else if (e.key === "Enter" && e.target.tagName === "INPUT") { const a = $$(".pickl a[data-n]", pick).find((x) => !x.hidden); if (a) location.hash = a.getAttribute("href"); }
  });
  document.addEventListener("click", function away(e) { if (!document.body.contains(pick)) document.removeEventListener("click", away); else if (!pick.contains(e.target)) pickOpen(false); });
  const box = $("#map"), inner = $(".mapin", box), tiles = $(".tiles", box), pins = $(".pins", box);
  // Übersicht: Bilder je Feld (eigene Ebene unter den Punkten); mit gewähltem Pokémon nur dieses
  const heatEl = document.createElement("div"); heatEl.className = "heat"; pins.before(heatEl);
  const wmax = Math.max(0.01, ...Object.values(H.cells).flatMap((c) => Object.values(c).map((s) => s.w)));
  heatEl.innerHTML = Object.values(H.cells).map((c) => {
    const xs = Object.values(c).filter((s) => fid == null || s.id === fid).sort((a, b) => b.w - a.w);
    const top = xs[0]?.w || 0;
    return xs.filter((s, i) => i < 3 && s.w >= top * 0.3).map((s) => { const px = Math.round(44 + 90 * Math.sqrt(s.w / wmax));
      return `<a class="hspr" draggable="false" href="#karte/${d.karte}/${s.id}" style="left:${s.sx / s.sw * 2}px;top:${s.sz / s.sw * 2}px;width:${px}px;height:${px}px;margin:-${px / 2}px 0 0 -${px / 2}px" data-tip="${esc(heatTip(s))}">${img(s.id)}</a>`; }).join("");
  }).join("");
  const heatSide = async () => {
    const side = $("#mapside");
    if (fid == null) {
      const xs = Object.values(H.tot).sort((a, b) => b.w - a.w).slice(0, 30), m = xs[0]?.w || 1;
      side.innerHTML = `<h3>Häufig in ${esc(d.gebiet || "")}</h3><table class="rows heatl">${xs.map((s) => `<tr><td>${img(s.id, "sm")}</td><td><a href="#karte/${d.karte}/${s.id}">${esc(s.name)}</a>
        <span class="hbar"><i style="width:${Math.max(3, s.w / m * 100)}%"></i></span></td><td class="num hint" data-tip="Stellen in diesem Gebiet">${s.n}</td></tr>`).join("")}</table>
        <p class="hint">Balken: Summe der Anteile über alle Spawnpunkte und Stellen; ein Maß dafür, wie viele man hier antrifft. Klick wählt das Pokémon.</p>`;
      return;
    }
    side.innerHTML = `<h3>${img(fid, "sm")} ${esc(species[fid]?.name || "")} in allen Gebieten</h3><p class="hint">Lädt …</p>`;
    const all = await Promise.all(d.karten.map(async (k) => MAPCACHE[k.karte] || (MAPCACHE[k.karte] = await api("/api/karte/" + encodeURIComponent(k.karte)))));
    if (rid !== RID || !document.body.contains(side)) return;
    const rows = all.map((m) => { const t = mapHeat(m.punkte || [], m.objekte || [], sh).tot[fid]; return {k: m.karte, g: m.gebiet, w: t?.w || 0, n: t?.n || 0}; }).sort((a, b) => b.w - a.w);
    const m = rows[0]?.w || 1;
    side.innerHTML = `<h3>${img(fid, "sm")} ${esc(species[fid]?.name || "")} in allen Gebieten</h3><table class="rows heatl">${rows.map((r) => `<tr${r.k === d.karte ? ` class="on"` : ""}><td>${r.n
      ? `<a href="#karte/${r.k}/${fid}">${esc(r.g)}</a>` : `<span class="hint">${esc(r.g)}</span>`}<span class="hbar"><i style="width:${r.w ? Math.max(3, r.w / m * 100) : 0}%"></i></span></td><td class="num hint">${r.n || "–"}</td></tr>`).join("")}</table>
      <p class="hint">Je länger der Balken, desto mehr trifft man es dort an (Summe der Anteile); die Zahl: Stellen. <a href="#karte/${d.karte}">Alle Pokémon zeigen</a></p>`;
  };
  const showHeat = () => { heatEl.hidden = !heatOn; $("#heatbtn")?.classList.toggle("on", heatOn); if (heatOn) heatSide(); };
  $("#heatbtn")?.addEventListener("click", () => { heatOn = !heatOn; store.set("mapHeat", heatOn); showHeat(); });
  showHeat();
  const tipOf = (p) => (p.alpha ? "Alpha-Spawnpunkt\n" : "") + (p.mons.length ? p.mons.filter((m) => sh(m) > 0).map((m) => `${m.alpha ? "Alpha-" : ""}${m.name}: bis ${mpct(sh(m))}`
    + (!cond && m.zeit !== "immer" ? ` (${m.zeit})` : "")).join("\n") || "zu dieser Zeit und bei diesem Wetter nichts" : "keine Angaben");
  pins.innerHTML = pts.map((p, i) => `<button class="mpin${p.alpha ? " alpha" : ""}${p.hit ? " hit" : ""}${(fid != null && !p.hit) || p.off ? " dim" : ""}" data-i="${i}"
    style="left:${p.x * 2}px;top:${p.z * 2}px" data-tip="${esc(tipOf(p))}" aria-label="Spawnpunkt"></button>`).join("")
    + objs.map((o, i) => `<button class="mobj o-${o.art}${o.hit ? " hit" : ""}${got.has(okey(o)) ? " got" : ""}" data-o="${i}" style="left:${o.x * 2}px;top:${o.z * 2}px" data-tip="${esc(mobjTip(o, arten))}"
      aria-label="${esc(arten[o.art]?.[0] || o.art)}">${MOBJ[o.art] || "•"}</button>`).join("");
  const showLayers = () => {
    $$(".mpin", pins).forEach((b) => { b.hidden = hide.has("pokemon"); });
    $$(".mobj[data-o]", pins).forEach((b) => { const o = objs[+b.dataset.o]; b.hidden = hide.has(o.art) || (gotHide && got.has(okey(o))); });
  };
  showLayers();
  const toggleGot = (i) => {
    const o = objs[i], k = okey(o), on = !got.has(k);
    if (on) got.add(k); else got.delete(k);
    $(`.mobj[data-o="${i}"]`, pins)?.classList.toggle("got", on);
    const c = $(`[data-cnt="${o.art}"]`);
    if (c) c.innerHTML = cnt(o.art, objs.filter((x) => x.art === o.art).length);
    const gb = $("#gotbtn");
    if (gb && +gb.dataset.o === i) { gb.classList.toggle("on", on); gb.textContent = on ? "✓ erledigt" : "als erledigt markieren"; }
    showLayers();
    api("/api/gefunden", {spiel: MAPSPIEL, karte: key, objekt: k, an: on}).catch(ungespeichert(() => {
      if (on) got.delete(k); else got.add(k);        // nicht gespeichert: zurück
      $(`.mobj[data-o="${i}"]`, pins)?.classList.toggle("got", !on);
      showLayers();
    }));
  };
  $("#gothide")?.addEventListener("change", (e) => { gotHide = e.target.checked; store.set("mapGotHide", gotHide); showLayers(); });
  pins.addEventListener("contextmenu", (e) => {
    const ob = e.target.closest(".mobj[data-o]");
    if (!ob) return;
    e.preventDefault();
    toggleGot(+ob.dataset.o);
  });
  const layBtns = () => $$(".mlay[data-lay]").forEach((b) => { b.classList.toggle("on", !hide.has(b.dataset.lay)); b.dataset.tip = hide.has(b.dataset.lay) ? "einblenden" : "ausblenden"; });
  $$(".mlay[data-lay]").forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.lay;
    if (hide.has(k)) hide.delete(k); else hide.add(k);
    store.set("mapHide", [...hide]);
    layBtns(); showLayers();
  }));
  $$("[data-layall]").forEach((b) => b.addEventListener("click", () => {
    $$(".mlay[data-lay]").forEach((x) => { if (b.dataset.layall === "1") hide.delete(x.dataset.lay); else hide.add(x.dataset.lay); });
    store.set("mapHide", [...hide]);
    layBtns(); showLayers();
  }));
  $$("details.mgg").forEach((x) => x.addEventListener("toggle", () => { if (x.open) mopen.add(x.dataset.gid); else mopen.delete(x.dataset.gid); store.set("mapOpen", [...mopen]); }));
  $$("[data-gfold]").forEach((b) => b.addEventListener("click", () => $$("details.mgg").forEach((x) => { x.open = b.dataset.gfold === "1"; })));
  $$("[data-grp]").forEach((b) => b.addEventListener("click", (e) => {
    e.preventDefault();
    const ks = groups[+b.dataset.grp][1].map((l) => l[0]), anyOn = ks.some((k) => !hide.has(k));
    ks.forEach((k) => { if (anyOn) hide.add(k); else hide.delete(k); });
    store.set("mapHide", [...hide]);
    layBtns(); showLayers();
  }));
  $$("[data-cond]").forEach((s) => s.addEventListener("change", () => {
    store.set(s.dataset.cond, +s.value);
    MAPPOS = {key, fid, scale, ox, oy};
    mapView(karte, fid);
  }));
  let scale = 1, ox = 0, oy = 0, level = -1;
  const fit = () => {
    const r = box.getBoundingClientRect(), on = [...pts.filter((p) => p.hit), ...objs.filter((o) => o.hit)];
    if (on.length) {
      const xs = on.map((p) => p.x * 2), ys = on.map((p) => p.z * 2), pad = 140;
      const w = Math.max(...xs) - Math.min(...xs) + pad * 2, h = Math.max(...ys) - Math.min(...ys) + pad * 2;
      scale = Math.min(1.5, r.width / w, r.height / h);
      ox = r.width / 2 - (Math.min(...xs) + Math.max(...xs)) / 2 * scale;
      oy = r.height / 2 - (Math.min(...ys) + Math.max(...ys)) / 2 * scale;
    } else {
      scale = Math.min(r.width, r.height) / WORLD * 1.6;           // etwas näher als die ganze Karte
      ox = (r.width - WORLD * scale) / 2; oy = (r.height - WORLD * scale) / 2;
    }
  };
  /* Kacheln: je Zoomstufe eine Ebene, gröbere bleiben darunter liegen (nichts wird leer, während feinere laden);
     geladen wird nur, was im Ausschnitt liegt */
  const layers = [0, 1, 2].map((z) => { const el = document.createElement("div"); el.dataset.z = z; tiles.appendChild(el); return {el, have: new Set()}; });
  if (d.bild) {          // Jubeldorf: ein Bild für die ganze Karte statt Kacheln
    const im = new Image();
    im.alt = ""; im.draggable = false; im.decoding = "async";
    im.style.cssText = `left:0;top:0;width:${WORLD}px;height:${WORLD}px`;
    im.src = `karten/${d.karte}/bild.png`;
    tiles.appendChild(im);
  }
  const draw = () => {
    const z = scale < 0.3 ? 0 : scale < 0.6 ? 1 : 2;
    level = z;
    const r = box.getBoundingClientRect();
    for (let k = 0; k <= z; k++) {
      if (d.bild || (k !== 0 && k !== z)) continue;          // die gröbste als Unterlage, dazu die passende
      const n = 2 ** (k + 1), size = WORLD / n, L = layers[k];
      const x0 = Math.max(0, Math.floor(-ox / scale / size)), x1 = Math.min(n - 1, Math.floor((r.width - ox) / scale / size));
      const y0 = Math.max(0, Math.floor(-oy / scale / size)), y1 = Math.min(n - 1, Math.floor((r.height - oy) / scale / size));
      for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) {
        const key = `${x}-${y}`;
        if (L.have.has(key)) continue;
        L.have.add(key);
        const im = new Image();
        im.alt = ""; im.draggable = false; im.decoding = "async";
        im.style.cssText = `left:${x * size}px;top:${y * size}px;width:${size}px;height:${size}px`;
        im.onerror = () => { im.style.visibility = "hidden"; };
        im.src = `karten/${d.karte}/${k}-${x}-${y}.png`;
        L.el.appendChild(im);
      }
    }
    layers.forEach((L, k) => { L.el.hidden = k > z; });
    inner.style.transform = `translate(${ox}px,${oy}px) scale(${scale})`;
    inner.style.setProperty("--inv", 1 / scale);
  };
  const zoomAt = (f, cx, cy) => {
    const ns = Math.max(0.15, Math.min(4, scale * f));
    ox = cx - (cx - ox) * ns / scale; oy = cy - (cy - oy) * ns / scale; scale = ns; draw(); zsync();
  };
  if (MAPPOS && MAPPOS.key === key && MAPPOS.fid === fid) ({scale, ox, oy} = MAPPOS); else fit();
  MAPPOS = null;
  draw();
  // Zoomregler wie auf der großen Karte (log. Maßstab); das Rad zoomt fein
  const zr = $("#mapz"), zsync = () => { if (zr) zr.value = Math.log2(scale); };
  if (zr) { Object.assign(zr, {min: Math.log2(0.15), max: 2, step: 0.05}); zsync();
    zr.addEventListener("input", () => { const r = box.getBoundingClientRect(); zoomAt(2 ** +zr.value / scale, r.width / 2, r.height / 2); }); }
  box.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = box.getBoundingClientRect(), dy = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY;
    zoomAt(2 ** Math.max(-0.5, Math.min(0.5, -dy / 200)), e.clientX - r.left, e.clientY - r.top);
  }, {passive: false});
  $$("[data-mz]").forEach((b) => b.addEventListener("click", () => {
    const r = box.getBoundingClientRect();
    if (b.dataset.mz === "0") { fit(); draw(); return; }
    zoomAt(b.dataset.mz === "1" ? 1.4 : 1 / 1.4, r.width / 2, r.height / 2);
  }));
  let drag = null, moved = false;
  box.addEventListener("dragstart", (e) => e.preventDefault());
  box.addEventListener("pointerdown", (e) => {
    if (e.button || e.target.closest(".mapzoom")) return;
    drag = {x: e.clientX, y: e.clientY, ox, oy, id: e.pointerId};
    moved = false;
  });
  box.addEventListener("pointermove", (e) => {
    if (!drag) return;
    if (!moved && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) > 4) {
      moved = true;
      box.setPointerCapture(drag.id);
      box.classList.add("grab");
    }
    if (moved) { ox = drag.ox + e.clientX - drag.x; oy = drag.oy + e.clientY - drag.y; draw(); }
  });
  box.addEventListener("click", (e) => { if (moved) { e.preventDefault(); e.stopPropagation(); moved = false; } }, true);
  const stop = () => { drag = null; box.classList.remove("grab"); };
  box.addEventListener("pointerup", stop);
  box.addEventListener("pointercancel", stop);
  pins.addEventListener("click", (e) => {
    const ob = e.target.closest(".mobj[data-o]");
    if (ob) {
      $$(".sel", pins).forEach((x) => x.classList.remove("sel"));
      ob.classList.add("sel");
      const o = objs[+ob.dataset.o];
      const mon = MOBJMON.has(o.art);
      const isGot = got.has(okey(o));
      $("#mapside").innerHTML = `<h3><span class="mobj o-${o.art}">${MOBJ[o.art] || "•"}</span> ${esc(arten[o.art]?.[0] || o.art)}${o.nr ? " " + o.nr : ""}</h3>`
        + `<p><button class="btn gotbtn${isGot ? " on" : ""}" id="gotbtn" data-o="${ob.dataset.o}" data-tip="Merken, dass du das schon hast (auch per Rechtsklick auf das Symbol)">${isGot ? "✓ gefunden" : "als gefunden markieren"}</button></p>`
        + (mon ? `<table class="rows"><tr><th></th><th>Pokémon</th><th>${o.art === "alpha" ? "Level" : "Level, Anteil"}</th></tr>${o.items.map(([n, t, id]) => `<tr${id === fid ? ` class="on"` : ""}><td>${id ? img(id, "sm") : ""}</td>
            <td>${id ? `<a href="#pokemon/${id}">${esc(n)}</a>` : esc(n)}</td><td>${esc(t)}</td></tr>`).join("")}</table><p class="hint">${esc(MOBJHINT[o.art] || "")}</p>`
        : o.items.length ? `<table class="rows"><tr><th>Item</th><th class="c">Anteil</th></tr>${o.items.map(([n, p]) => `<tr><td>${wikiLink(n)}</td><td class="c num">${esc(p)}</td></tr>`).join("")}</table>`
          + (o.menge ? `<p class="hint">${esc(o.menge)} Stück je Mal; Anteil: so oft ist es dieses Item.</p>` : "") : `<p class="hint">${esc(MOBJHINT[o.art] || "")}</p>`);
      $("#gotbtn").addEventListener("click", () => toggleGot(+ob.dataset.o));
      return;
    }
    const b = e.target.closest(".mpin");
    if (!b) return;
    $$(".sel", pins).forEach((x) => x.classList.remove("sel"));
    b.classList.add("sel");
    const p = pts[+b.dataset.i];
    $("#mapside").innerHTML = `<h3>${p.alpha ? "Alpha-Spawnpunkt" : "Spawnpunkt"}</h3>` + (p.mons.length ? `<table class="rows"><tr><th></th><th>Pokémon</th><th>Anteil</th><th>Tageszeit</th><th>Wetter</th></tr>
      ${p.mons.map((m) => `<tr${cond && !(sh(m) > 0) ? ` class="dim"` : ""}><td>${img(m.id, "sm")}</td><td><a href="#pokemon/${m.id}">${m.alpha ? `<span class="alpha">Alpha</span> ` : ""}${esc(m.name)}</a></td>
        <td>${cond ? (sh(m) > 0 ? "bis " + mpct(sh(m)) : "–") : "bis " + mpct(m.max)}</td><td>${esc(m.zeit)}</td><td>${esc(m.wetter)}</td></tr>`).join("")}</table>` : `<p class="hint">keine Angaben</p>`)
      + `<p class="hint">Anteil: so oft erscheint es an diesem Punkt unter den passenden Bedingungen (höchster Wert${cond ? ", nur zur gewählten Tageszeit und beim gewählten Wetter" : ""}).</p>`;
  });
}

// Items des Spiels: Suche, Tasche und Art. Je Tasche passende Spalten (Wirkung bei Medizin und Bällen, die Attacke bei
// Maschinen); unfertige Einträge (Platzhalter im Text) nur auf Wunsch.
const MKLASSE = {1: "Status", 2: "physisch", 3: "speziell"};
const HERSTELLEN = "herstellen";      // Ansicht der Items mit Rezept (Legenden: Arceus)
const itemImg = (x) => x.bild ? `<img class="ibild" src="itembild/${x.id}" alt="" loading="lazy">`
  : `<span class="ibild none">${x.attacke ? "TM" : ""}</span>`;
