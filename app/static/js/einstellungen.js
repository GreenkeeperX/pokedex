/* Pokédex-Oberfläche, Teil 9 von 10: Einstellungen.
   Die Teile lädt index.html der Reihe nach; sie teilen sich die globalen Namen (docs/oberflaeche.md). */
"use strict";
/* ------------------------------------------------------------------ Einstellungen */
/* Zeiten deutsch und in der Zeit des Browsers: „10.11.2026, 15:40 Uhr“ (der Server schreibt UTC) */
const deTime = (iso) => { if (!iso) return ""; const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + "Z");
  return isNaN(d) ? String(iso) : d.toLocaleString("de-DE", {day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit"}) + " Uhr"; };
// Protokollzeilen beginnen mit der Uhrzeit in UTC; gezeigt in der Zeit des Browsers
const logLocal = (line) => { const m = /^(\d\d):(\d\d):(\d\d)( [\s\S]*)$/.exec(line); if (!m) return line;
  const d = new Date(); d.setUTCHours(+m[1], +m[2], +m[3], 0); return d.toLocaleTimeString("de-DE") + m[4]; };
/* Einstellungen wie im VR-Navigator: oben eine Leiste mit den Abschnitten, jeder Kasten klappt auf und zu (gemerkt) */
function foldBoxes(root) {
  const shut = new Set(store.get("setShut", ["quellen", "lesezeichen", "spieldaten"]));
  const boxes = $$(":scope > .box, :scope > .cols > .box, :scope > .cols > .stack > .box, :scope > details.box", root);
  const slug = (t) => t.toLowerCase().replace(/[^a-zäöüß]+/g, "-").replace(/^-|-$/g, "").replace(/^seite-untersuchen.*/, "lesezeichen").replace(/^quellen.*/, "quellen");
  const jumps = [];
  boxes.forEach((b) => {
    const h = $("h2", b); if (!h) return;
    const id = slug(h.textContent); jumps.push([id, h.textContent.replace(/\s*\(.*\)$/, "")]);
    let d = b;
    if (b.tagName !== "DETAILS") {
      d = document.createElement("details"); d.className = b.className;
      const sm = document.createElement("summary"); const bar = h.closest(".bar") && h.closest(".bar") !== b ? h.closest(".bar") : null;
      if (bar) { sm.append(...bar.childNodes); bar.remove(); } else { sm.append(h); }
      d.append(sm, ...b.childNodes); b.replaceWith(d);
    }
    d.id = "s-" + id; d.classList.add("fold");
    d.open = id === "status" ? store.get("statusOpen", false) : !shut.has(id);     // die Statuskarte ist anfangs zu
    $("summary", d).addEventListener("click", (e) => { if (e.target.closest("button")) e.preventDefault(); });   // Knöpfe im Kopf klappen nicht
    d.addEventListener("toggle", () => {
      if (id === "status") { store.set("statusOpen", d.open); return; }
      if (d.open) shut.delete(id); else shut.add(id); store.set("setShut", [...shut]);
    });
  });
  root.insertAdjacentHTML("afterbegin", `<div class="jump">${jumps.map(([id, l]) => `<a href="#einstellungen" data-jump="s-${id}">${esc(l)}</a>`).join("")}
    <span class="foldall"><button class="link" data-fold="1">alle auf</button> · <button class="link" data-fold="0">alle zu</button></span></div>`);
  $$("[data-jump]", root).forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); const d = $("#" + a.dataset.jump); d.open = true; const box = d.parentElement?.closest("details.fold"); if (box) box.open = true; d.scrollIntoView({behavior: "smooth", block: "start"}); }));
  $$("[data-fold]", root).forEach((b) => b.addEventListener("click", () => $$("details.fold", root).forEach((d) => { d.open = b.dataset.fold === "1"; })));
}
/* Speicherplatz des Datenordners (/api/speicher): Teile nach Größe, Karten aufklappbar nach Quelle und Karte */
const fmtBytes = (b) => b == null ? "?" : b >= 1e9 ? `${(b / 1e9).toFixed(2).replace(".", ",")} GB` : b >= 1e6 ? `${Math.round(b / 1e6)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`;
async function diskBox(neu) {
  const el = $("#disk");
  if (!el) return;
  const d = await api("/api/speicher" + (neu ? "?neu=1" : "")).catch((e) => ({error: e.message}));
  if (!$("#disk")) return;
  if (d.error) { el.innerHTML = `<p class="hint">Nicht lesbar (${esc(d.error)}).</p>`; return; }
  const row = (t, lv) => {
    const pct = d.gesamt ? t.bytes / d.gesamt * 100 : 0, kids = (t.teile || []).filter((x) => x.bytes > 0);
    const head = `<span class="dk-n">${esc(t.titel)}</span><span class="dk-b"><i style="width:${Math.max(0.5, pct).toFixed(1)}%"></i></span><span class="dk-v">${fmtBytes(t.bytes)}</span><span class="hint dk-c">${t.dateien ? t.dateien.toLocaleString("de-DE") + (t.dateien === 1 ? " Datei" : " Dateien") : ""}</span>`;
    return kids.length ? `<details class="dk dk${lv}"><summary>${head}</summary>${kids.map((x) => row(x, lv + 1)).join("")}</details>` : `<div class="dk dk${lv}">${head}</div>`;
  };
  el.innerHTML = `<p>Zusammen <b>${fmtBytes(d.gesamt)}</b>${d.frei != null ? `, auf dem Laufwerk frei: <b>${fmtBytes(d.frei)}</b> von ${fmtBytes(d.platte)}` : ""}.
      <button class="link" id="diskneu" data-tip="Neu zählen (sonst gilt die Zählung fünf Minuten)">neu zählen</button></p>
    ${d.teile.filter((t) => t.bytes > 0).map((t) => row(t, 0)).join("")}`;
  $("#diskneu").addEventListener("click", () => { el.innerHTML = `<p class="hint">Zählt …</p>`; diskBox(true); });
}
/* Statuskarte (/api/statuskarte): eingeklappt nur der Gesamtstatus, aufgeklappt die Einzelheiten. Die Gründe für den
   Gesamtstatus rechnet der Server (app/statuskarte.py); die Oberfläche zeigt sie nur. */
const QUELLEN_DE = {pokeapi: "PokéAPI", showdown: "Showdown", pkhex: "PKHeX", spawns: "Spawnpunkte", karten: "Kartenbilder",
  sprites: "Bilder", extras: "Extras", itemhq: "Große Item-Bilder", mapgenie: "Map Genie", smogon: "Smogon", pokewiki: "PokéWiki",
  altissimo: "Altissimo", companion: "PLA Companion", serebii: "Serebii"};
const STATUS_DE = {ok: ["ok", "Alles in Ordnung"], eingeschraenkt: ["warn", "Einschränkungen"], fehler: ["bad", "Fehler vorhanden"]};
function statusBox(k) {
  if (!k) return `<div class="box"><div class="bar"><h2>Status</h2> <span class="badge warn">nicht lesbar</span></div><p class="hint">Der Server hat den Status nicht geliefert.</p></div>`;
  const [cls, label] = STATUS_DE[k.gesamt] || STATUS_DE.fehler, sp = k.speicher, ab = k.abgleich, v = k.version, w = k.wiederherstellung;
  const note = (g) => `<div class="note ${g.stufe === "fehler" ? "stop" : "warn"}">${esc(g.text)}</div>`;
  const qn = (s) => QUELLEN_DE[s] || s;
  const tr = (th, td) => `<tr><th>${th}</th><td>${td}</td></tr>`;
  const letzte = k.sicherung.letzte, lt = k.leistung;
  const ms = (x) => x == null ? "–" : `${x.toLocaleString("de-DE", {maximumFractionDigits: 0})} ms`;
  return `<div class="box"><div class="bar"><h2>Status</h2> <span class="badge ${cls}" data-tip="${esc(k.gruende.map((g) => g.text).join(" ") || "Abgleich, Quellen, Fehlerregister, Platz und Sicherung sind in Ordnung.")}">${label}</span></div>
    ${k.gruende.map(note).join("") || `<div class="note go">Abgleich, Quellen, Fehlerregister, Platz und Sicherung sind in Ordnung.</div>`}
    <table class="rows kv">
      ${tr("Abgleich", ab.laeuft ? "läuft" : ab.start ? `${esc(deTime(ab.start))}${ab.unterbrochen ? ", unterbrochen" : ab.ok === false ? ", mit Fehlern" : ab.ende ? ", fertig " + esc(deTime(ab.ende)) : ""}` : "noch keiner")}
      ${ab.naechster && !ab.laeuft ? tr("Nächster Lauf", esc(deTime(ab.naechster))) : ""}
      ${tr("Version", `Pokédex ${esc(v.anwendung)}, Datenstand ${esc(v.daten)}${ab.gebaut ? `, Datenbank gebaut ${esc(deTime(ab.gebaut))}` : ""}${v.gebaut_mit && v.gebaut_mit !== v.daten ? ` mit Stand ${esc(v.gebaut_mit)}` : ""}`)}
      ${tr("Sicherung", letzte ? `${esc(deTime(letzte.zeit))} (${esc(letzte.name)}, ${fmtBytes(letzte.bytes)}), ${k.sicherung.anzahl} vorhanden` : "noch keine")}
      ${tr("Wiederherstellungstest", `${w ? `${esc(deTime(w.zeit))}${w.datei ? ` (${esc(w.datei)}, ${w.dauer_ms} ms)` : ""}: ${w.ok ? "bestanden" : "<b class=\"errc\">gescheitert</b>"}${w.text ? " – " + esc(w.text) : ""}` : "noch keiner"} · <button class="link" data-act="wtest" data-tip="Stellt die jüngste Sicherung in einem temporären Ordner wieder her und prüft, ob sie heil ist und sich laden lässt. Deine Daten bleiben unberührt. Läuft sonst von selbst einmal im Monat.">jetzt prüfen</button>`)}
      ${tr("Leistungstest", `${lt ? `${esc(deTime(lt.zeit))}, Pokédex ${esc(lt.version)}: ${lt.ok ? "" : "<b class=\"errc\">nicht alle Wege beantwortet</b>, "}${(lt.dauer_ms / 1000).toLocaleString("de-DE")} s, Arbeitsspeicher danach ${lt.ram.nachher != null ? fmtBytes(lt.ram.nachher) : "?"}` : "noch keiner"} · <button class="link" data-act="leistung"${ab.laeuft ? " disabled" : ""} data-tip="Misst die Antwortzeiten der wichtigsten Wege (je einmal und dreimal wiederholt), Größe der Antworten, Speicher, Rechenzeit und das Speichern in einer temporären Datenbank mit erfundenen Teams. Ohne Netz, nicht während eines Abgleichs; deine Daten bleiben unberührt. Dauert einige Sekunden.">messen</button>`)}
      ${tr("Platz", sp.frei != null ? `frei ${fmtBytes(sp.frei)} von ${fmtBytes(sp.platte)}` : "nicht lesbar")}
      ${tr("Daten", `pokeapi.db ${sp.pokeapi_db != null ? fmtBytes(sp.pokeapi_db) : "fehlt"}, user.db ${sp.user_db != null ? fmtBytes(sp.user_db) : "fehlt"}, Datenordner ${sp.datenordner != null ? fmtBytes(sp.datenordner) : `<button class="link" data-jump="diskd" data-tip="Zählt den Datenordner (Speicherplatz im Kasten Sicherung)">zählen</button>`}`)}
      ${tr("Arbeitsspeicher", `${sp.ram.jetzt != null ? `jetzt ${fmtBytes(sp.ram.jetzt)}, ` : ""}höchstens ${fmtBytes(sp.ram.spitze)} seit dem Start`)}
    </table>
    ${k.quellen.length ? `<h3>Letzter Abgleich je Quelle</h3><div class="scroll"><table class="rows"><tr><th>Quelle</th><th>Stand</th><th>Fehler</th><th>Zeit</th></tr>
      ${k.quellen.map((q) => `<tr><td>${esc(qn(q.quelle))}</td><td>${q.ok ? "✓" : "✗"} ${esc(q.meldung)}</td><td class="num">${q.fehler}</td><td class="nw">${esc(deTime(q.zeit))}</td></tr>`).join("")}</table></div>` : ""}
    ${lt ? `<details class="sub" id="leistungd"><summary><b>Leistungstest</b> <span class="hint">${esc(deTime(lt.zeit))}, ${esc(gameName(lt.spiel))}, Detailseite von Form ${lt.pokemon}</span></summary>
      <div class="scroll"><table class="rows"><tr><th>Weg</th><th>erste</th><th>wiederholt</th><th>Größe</th><th>gepackt</th></tr>
      ${lt.abrufe.map((a) => `<tr><td data-tip="${esc(a.weg)}">${esc(a.name)}${a.status === 200 ? "" : ` <b class="errc">${a.status || esc(a.meldung || "")}</b>`}</td><td class="num">${ms(a.erste_ms)}</td><td class="num">${ms(a.wieder_ms)}</td><td class="num">${fmtBytes(a.bytes)}</td><td class="num">${fmtBytes(a.gepackt)}</td></tr>`).join("")}</table></div>
      <p class="hint">Rechenzeit ${lt.cpu_s.toLocaleString("de-DE")} s in ${(lt.dauer_ms / 1000).toLocaleString("de-DE")} s (${lt.kerne || "?"} Kerne${lt.last != null ? `, Last ${lt.last.toLocaleString("de-DE")}` : ""}).
        Arbeitsspeicher vorher ${lt.ram.vorher != null ? fmtBytes(lt.ram.vorher) : "?"}, nachher ${lt.ram.nachher != null ? fmtBytes(lt.ram.nachher) : "?"}, höchstens ${fmtBytes(lt.ram.spitze)}.
        ${lt.laden ? `Spieldaten laden zuletzt ${ms(lt.laden.ms)} (${esc(deTime(lt.laden.am))}).` : ""}
        Speichern: ${lt.schreiben.anzahl} erfundene Teams in einer temporären Datenbank, ${ms(lt.schreiben.ms)}, je Team ${lt.schreiben.ms_je.toLocaleString("de-DE")} ms. Datenstand ${esc(lt.daten)}.</p></details>` : ""}
    ${k.ruhe.length ? `<h3>Ruhezeiten</h3><table class="rows"><tr><th>Quelle oder Server</th><th>Ruht bis</th></tr>
      ${k.ruhe.map((r) => `<tr><td>${esc(qn(r.schluessel))}</td><td class="nw">${esc(deTime(r.bis))}</td></tr>`).join("")}</table>` : ""}
    ${k.fehler.anzahl ? `<h3>Fehler (${k.fehler.anzahl})</h3><div class="scroll"><table class="rows"><tr><th>Zuletzt</th><th>Quelle</th><th>Art</th><th>Anzahl</th></tr>
      ${k.fehler.eintraege.map((f) => `<tr><td class="nw">${esc(deTime(f.zuletzt))}</td><td>${esc(f.quelle)}</td><td>${esc(f.art)}</td><td class="num">${f.anzahl}</td></tr>`).join("")}</table></div>
      ${k.fehler.anzahl > k.fehler.eintraege.length ? `<p class="hint">Alle ${k.fehler.anzahl} mit Text stehen im Kasten Abgleich unter Fehler.</p>` : ""}` : ""}
  </div>`;
}
/* Uhrzeit des Abgleichs: Der Server führt sie als Weltzeit (UTC, „HH:MM“), das Feld zeigt die Ortszeit des Browsers */
const uhrShift = (hm, sign) => { const m = /^(\d\d):(\d\d)$/.exec(hm || ""); if (!m) return "";
  const t = ((+m[1] * 60 + +m[2] + sign * new Date().getTimezoneOffset()) % 1440 + 1440) % 1440;
  return String(Math.floor(t / 60)).padStart(2, "0") + ":" + String(t % 60).padStart(2, "0"); };
const uhrLocal = (utc) => uhrShift(utc || "02:30", -1), uhrUtc = (local) => uhrShift(local, 1);
async function settingsView() {
  const rid = RID;
  const [st, pr, fe, sk] = await Promise.all([api("/api/status"), S.meta?.has_data ? api("/api/pruefung") : [],
    api("/api/fehler").catch(teil("Fehlerliste", {fehler: [], max: 0})), api("/api/statuskarte").catch(teil("Statuskarte", null))]);
  if (rid !== RID) return;
  const fehler = fe.fehler || [];
  const s = S.meta?.einstellungen || {};
  const src = st.sources || {};
  const open = pr.filter((r) => !r.entscheidung);
  const srcRow = (k, n) => { const r = src[k]; return r ? `<tr><td>${n}</td><td>${r.ok ? "✓" : "✗"} ${esc(r.msg || "")}</td><td class="num">${r.requests}</td><td class="num">${r.errors}</td><td class="nw">${esc(deTime(r.at))}</td></tr>` : ""; };
  const srcKeys = ["pokeapi", "showdown", "pkhex", "spawns", "karten", "sprites", "extras", "itemhq", "mapgenie", "smogon", "pokewiki", "altissimo", "companion"].filter((k) => src[k]);
  const okN = srcKeys.filter((k) => src[k].ok).length, bad = srcKeys.filter((k) => !src[k].ok);
  main.innerHTML = `${statusBox(sk)}<div class="cols">
    <div class="box"><h2>Abgleich</h2>
      ${st.running ? `<div class="note info">Läuft: ${esc(st.step || "")}${st.total ? ` (${st.done}/${st.total})` : ""}</div>` : ""}
      ${st.unterbrochen ? `<div class="note info">Der letzte Lauf wurde von einem Neustart unterbrochen. Er wird in wenigen Minuten fortgesetzt; was schon geholt war, bleibt.</div>` : ""}
      <p>Letzter Lauf: ${st.started ? esc(deTime(st.started)) + (st.unterbrochen ? " <b>unterbrochen</b>" : st.ok === false ? " <b>mit Fehlern</b>" : "") : "noch keiner"}
      ${st.naechster && !st.running ? `<br>Nächster Lauf nach Zeitplan: ${esc(deTime(st.naechster))}` : ""}
      ${st.built ? `<br>Datenbank gebaut: ${esc(deTime(st.built))}` : ""}
      ${bad.length ? `<br><b class="errc">${bad.length} ${bad.length === 1 ? "Quelle" : "Quellen"} mit Problem</b> (${esc(bad.join(", "))})` : ""}</p>
      ${st.stats?.species ? `<p class="hint">${st.stats.species} Arten, ${st.stats.forms} Formen, ${st.stats.moves} Attacken, ${st.stats.games} Spiele, ${st.stats.tables} Tabellen</p>` : ""}
      <div class="plan"><h3>Zeitplan</h3>
      <div class="bar"><label><input type="checkbox" id="auto"${s.auto ? " checked" : ""}> automatisch alle</label>
        <input type="number" id="tage" min="1" max="30" value="${s.tage || 7}" style="width:64px"> Tage
        <label data-tip="Feste Uhrzeit in deiner Ortszeit. Der Server merkt sie sich als Weltzeit (UTC); mit der Zeitumstellung verschiebt sie sich um eine Stunde.">um <input type="time" id="uhr" value="${esc(uhrLocal(s.uhr))}" style="width:96px"> Uhr</label></div>
      <div class="bar"><label><input type="checkbox" id="sprites"${s.sprites ? " checked" : ""}> Bilder laden (Sprites 96 × 96 und offizielle Artworks 475 × 475, zusammen gut 180 MB; dazu schillernde und animierte Sprites, Rufe und Item-Bilder, gut 45 MB)</label></div>
      <p class="hint">Ändert sich bei keiner Quelle etwas, bleibt die Datenbank. Eine neue gilt erst nach bestandener Selbstprüfung; deine Teams liegen getrennt (user.db) und werden täglich gesichert.</p></div>
      ${srcKeys.length ? `<details class="sub"${bad.length ? " open" : ""}><summary><b>Quellen</b> ${okN ? `<span class="badge ok">${okN} ok</span>` : ""}${bad.length ? `<span class="badge bad">${bad.length} mit Problem</span>` : ""}</summary>
      <table class="rows"><tr><th>Quelle</th><th>Stand</th><th>Abrufe</th><th>Fehler</th><th>Zeit</th></tr>${srcRow("pokeapi", "PokéAPI")}${srcRow("showdown", "Showdown")}${srcRow("pkhex", "PKHeX")}${srcRow("spawns", "Spawnpunkte")}${srcRow("karten", "Kartenbilder")}${srcRow("sprites", "Bilder")}${srcRow("extras", "Extras")}${srcRow("itemhq", "Große Item-Bilder")}${srcRow("mapgenie", "Map Genie")}${srcRow("smogon", "Smogon")}${srcRow("pokewiki", "PokéWiki")}${srcRow("altissimo", "Altissimo")}${srcRow("companion", "PLA Companion")}</table></details>` : ""}
      <div class="bar acts"><button class="primary" data-act="sync"${st.running ? " disabled" : ""}>Jetzt abgleichen</button>
        <button data-act="rebuild"${st.running ? " disabled" : ""} data-tip="Auch ohne Änderung neu bauen">Neu bauen</button>
        <button data-act="diag" data-tip="Fragt jede Quelle einmal an, auch mögliche neue (Items, Fundorte, Wikis, Kampfdaten, Karten), und beschreibt die Antwort. Verschiedene Server gleichzeitig, jeden für sich mit Pause. Speichert nichts und läuft weiter, wenn du den Reiter wechselst">Verbindung testen</button></div>
      <details class="sub nosep" id="diagsub"><summary><b>Verbindungstest</b> <span class="hint">noch nicht gestartet</span><span id="dlinks" class="slinks"></span></summary>
        <div id="diag"><p class="hint">„Verbindung testen“ fragt jede Quelle einmal an; Probe-Seiten lassen sich danach herunterladen.</p></div></details>
      <details class="sub"${st.ok === false || st.running ? " open" : ""}><summary><b>Protokoll</b> <span class="hint">${st.started ? esc(deTime(st.started)) + (st.ok === false ? ", mit Fehlern" : "") : "noch keins"}</span>
        ${(st.log || []).length ? `<span class="slinks"><button class="link" data-act="copy" data-src="#plog">kopieren</button> · <button class="link" data-act="dl" data-src="#plog" data-name="pokedex-protokoll">herunterladen</button></span>` : ""}</summary>
        <div class="log" id="plog">${esc((st.log || []).map(logLocal).join("\n") || "Noch kein Lauf.")}</div></details>
      <details class="sub" id="fehlersub"><summary><b>Fehler</b> ${fehler.length ? `<span class="badge bad">${fehler.length}</span> <span class="hint">zuletzt ${esc(deTime(fehler[0].zuletzt))}</span>` : `<span class="hint">keine</span>`}
        ${fehler.length ? `<span class="slinks"><button class="link" data-act="fehlerleeren" data-tip="Liste leeren. Was wieder auftritt, steht danach wieder hier.">leeren</button></span>` : ""}</summary>
        ${fehler.length ? `<p class="hint">Was beim Abgleich oder beim Anzeigen gescheitert ist, je Fehler eine Zeile mit Anzahl (höchstens ${fe.max}, die ältesten fallen weg). Die technischen Einzelheiten stehen im Protokoll des Containers.</p>
        <div class="scroll"><table class="rows"><tr><th>Zuletzt</th><th>Quelle</th><th>Stelle</th><th>Art</th><th>Anzahl</th><th>Seit</th></tr>
        ${fehler.map((f) => `<tr><td class="nw">${esc(deTime(f.zuletzt))}</td><td>${esc(f.quelle)}</td><td>${esc(f.wo)}</td><td data-tip="${esc(f.text || "")}">${esc(f.art)}</td><td class="num">${f.anzahl}</td><td class="nw">${esc(deTime(f.erst))}</td></tr>
          ${f.text ? `<tr class="ftext"><td></td><td colspan="5" class="hint">${esc(f.text)}</td></tr>` : ""}`).join("")}</table></div>`
        : `<p class="hint">Seit dem letzten Leeren ist nichts gescheitert. Fehlt nur eine Tabelle, weil die Datenbank älter ist als die Version, zählt das nicht als Fehler; der nächste Abgleich baut sie.</p>`}</details>
      <details class="sub"><summary><b>Quellen und Lizenzen</b> <span class="hint">Pokédex ${esc(S.meta?.version || "")}</span></summary>
      <p><a href="https://pokeapi.co" target="_blank" rel="noopener noreferrer">PokéAPI</a> (Grunddaten, alle Spiele, BSD-Lizenz) ·
        <a href="https://github.com/smogon/pokemon-showdown" target="_blank" rel="noopener noreferrer">Pokémon Showdown</a> (Gegenprüfung, MIT) ·
        <a href="https://github.com/kwsch/PKHeX" target="_blank" rel="noopener noreferrer">PKHeX</a> (Fundorte aus den Spieldaten, Item-Listen, GPL-3.0) ·
        <a href="https://github.com/Lincoln-LM/PLA-Live-Map" target="_blank" rel="noopener noreferrer">PLA-Live-Map</a> und
        <a href="https://github.com/Lincoln-LM/JS-Finder" target="_blank" rel="noopener noreferrer">JS-Finder</a> (Spawnpunkte, GPL-3.0) ·
        <a href="https://github.com/Altissimo1/altissimo1.github.io" target="_blank" rel="noopener noreferrer">Altissimo</a> (Kartensymbole, Jubeldorf, Rezepte, GPL-3.0) ·
        <a href="https://www.serebii.net" target="_blank" rel="noopener noreferrer">Serebii</a> (Kartenbilder, große Item-Bilder) ·
        <a href="https://www.pokewiki.de" target="_blank" rel="noopener noreferrer">PokéWiki</a> (Links, Attackenwerte, getragene Items und Kartenebenen in Legenden: Arceus, CC BY-SA 3.0 DE).
        Pokémon und alle Namen sind Marken von Nintendo, Creatures und GAME FREAK; dies ist ein privates Nachschlage-Tool.</p></details>
    </div>
    <div class="stack"><div class="box"><h2>Zu erledigen</h2>
      ${open.length ? `<p class="hint">PokéAPI und Showdown sind sich hier nicht einig. Das gilt für kein einzelnes Spiel: verglichen wird der neueste Stand der Hauptspiele
          (Generation 9), so steht es auch im Auftrag. Ältere Spiele haben teils andere Werte, die zeigt die Attackenliste je Spiel. Wähle, welcher Wert stimmt; im Zweifel im PokéWiki nachsehen. Oder gib die Liste als Auftrag an eine KI und lies ihre Antwort ein.</p>
        <div class="bar slim"><button data-act="todotask" data-tip="Auftrag für einen KI-Chat: die offenen Punkte mit der Bitte, sie zu prüfen. Die Antwort fügst du unter „Antwort einlesen“ ein und siehst erst eine Vorschau.">Auftrag kopieren${open.length > 60 ? ` (60 von ${open.length})` : ""}</button>
          <button data-act="todoans">Antwort einlesen</button>
          <button data-act="todocsv" data-tip="Die offenen Punkte als CSV-Datei, etwa für LibreOffice">herunterladen</button></div>
        <div id="todoans" hidden><textarea id="todotext" rows="5" placeholder="Antwort der KI hier einfügen (JSON)" style="width:100%"></textarea>
          <div class="bar slim"><button class="primary" data-act="todoprev">Vorschau</button><span class="hint">Übernommen wird erst nach der Vorschau.</span></div><div id="todoprev"></div></div>
        <div class="scroll"><table class="rows"><tr><th>Was</th><th>Feld</th><th>PokéAPI</th><th>Showdown</th><th></th></tr>
        ${open.slice(0, 80).map((r) => `<tr><td data-tip="${esc(`${r.key.startsWith("attacke") ? "Attacke" : "Pokémon"}: neuester Stand der Hauptspiele (Generation 9), kein einzelnes Spiel`)}">${esc(r.name)}</td><td>${esc(r.feld)}</td><td>${esc(r.pokeapi)}</td><td>${esc(r.showdown)}</td>
          <td><button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="pokeapi">PokéAPI</button> <button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="showdown">Showdown</button>
          <button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="egal">egal</button></td></tr>`).join("")}</table></div>`
        : `<div class="note go">Nichts offen${pr.length ? ` (${pr.length} Abweichungen entschieden)` : ""}.</div>`}
      ${pr.length - open.length ? `<details><summary>Entschieden (${pr.length - open.length})</summary><table class="rows">${pr.filter((r) => r.entscheidung).map((r) => `<tr><td>${esc(r.name)}</td><td>${esc(r.feld)}</td><td>${esc(r.entscheidung)}</td><td><button class="small" data-act="dec" data-k="${esc(r.key)}" data-v="">zurück</button></td></tr>`).join("")}</table></details>` : ""}
    </div>
    <div class="box"><h2>Sicherung</h2>
      <div class="bar"><a class="btn" href="/api/export" download data-tip="Alles Eigene als JSON-Datei">Sicherung herunterladen</a>
        <label class="btn filebtn" data-tip="Ersetzt alle eigenen Daten durch die Datei; vorher legt der Server eine Kopie an">Sicherung einlesen <input type="file" id="restore" accept="application/json,.json" hidden></label>
        <a class="btn" href="/api/spieldaten" download data-tip="ZIP-Datei, etwa 20 MB, ohne Bilder und ohne eigene Daten">Spieldaten herunterladen</a></div>
      <div id="restmsg"></div>
      <details class="sub" id="sichinfo"${store.get("sichInfo", false) ? " open" : ""}><summary><span class="hint">Der Server sichert deine Daten außerdem täglich (14 Tage)</span></summary>
        <p class="hint">Die Sicherung enthält alles Eigene: Teams, Favoriten, deine Sammlung (als gefangen markiert), Kampftagebuch und Entscheidungen.
        Einlesen ersetzt alle eigenen Daten durch die Datei; vorher legt der Server eine Kopie an. Der Server sichert user.db außerdem täglich selbst (die letzten 14 Tage).
        Die Spieldaten sind alles, was der Abgleich gesammelt hat (Datenbank, Stand, Protokoll, „Zu erledigen“ und welche Bilder und Kacheln fehlen), zum Nachprüfen; zum Einlesen braucht es sie nicht.</p></details>
      <details class="sub" id="diskd"${store.get("diskOpen", false) ? " open" : ""}><summary><b>Speicherplatz</b> <span class="hint">Datenbanken, Bilder und Kartenkacheln auf dem Server</span></summary>
        <div id="disk"><p class="hint">Lädt …</p></div></details></div></div></div>
    <h2 class="sect">Deine Daten</h2>
    <div class="box"><h2>Seite untersuchen (Lesezeichen)</h2><p class="hint">Manche Seiten laden ihre Karten erst im Browser (etwa das PokéWiki),
      der Abgleich sieht dann nur eine leere Hülle. Dieses Lesezeichen liest die fertig geladene Seite in deinem Browser: welche Daten-Dateien sie nachlädt
      (mit Inhalt), Daten in Variablen, Kartenmarker und das HTML. Ergebnis ist eine Datei für den Testdaten-Ordner, aus der sich ein Leser bauen lässt.
      Es geht nichts an einen Server; Benutzername und Schlüssel der Seite werden entfernt.</p>
      <span class="bm-w"><a class="bm" href="${esc(probeBm())}" data-act="nobm" data-tip="In die Lesezeichenleiste ziehen">⠿ <b>Seite untersuchen</b></a>
        <button data-act="bmcopy" data-tip="Für ein von Hand angelegtes Lesezeichen">Code kopieren</button></span>
      <ul class="hint"><li>Lesezeichenleiste einblenden (Strg+Umschalt+B) und den Knopf hineinziehen, oder „Code kopieren“ und als Adresse eines neuen Lesezeichens einfügen.</li>
        <li>Dann die Seite öffnen (etwa eine Karte im PokéWiki, bei Serebii, GamerGuides oder Pokébip), warten, bis die Karte steht, und das Lesezeichen anklicken.</li></ul></div>`;
  $$("h2.sect", main).forEach((h) => h.remove());       // die Leiste oben ersetzt die Zwischenüberschriften
  foldBoxes(main);
  diag(false);                                          // laufenden Test oder letztes Ergebnis zeigen
  const saveSet = async () => {
    const uhr = uhrUtc($("#uhr").value);
    S.meta.einstellungen = await api("/api/einstellungen", {auto: $("#auto").checked, tage: +$("#tage").value, sprites: $("#sprites").checked, ...(uhr ? {uhr} : {})});
  };
  ["auto", "tage", "sprites", "uhr"].forEach((k) => $("#" + k).addEventListener("change", saveSet));
  { const dk = $("#diskd"); if (dk.open) diskBox(); dk.addEventListener("toggle", () => { store.set("diskOpen", dk.open); if (dk.open) diskBox(); }); }   // zählt nur aufgeklappt
  $("#sichinfo").addEventListener("toggle", (e) => store.set("sichInfo", e.target.open));
  $("#restore").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    let body;
    try { body = JSON.parse(await file.text()); } catch (x) { $("#restmsg").innerHTML = `<div class="note stop">Keine lesbare JSON-Datei.</div>`; return; }
    const n = (k) => (body[k] || []).length;
    if (!await ask(`Sicherung vom ${String(body.exportiert || "?").slice(0, 10)} einlesen?`, `${n("teams")} Teams, ${n("favoriten")} Favoriten, ${n("gefangen")} in der Sammlung, ${n("entscheidungen")} Entscheidungen, ${n("jagden")} Shiny-Jagden, ${n("nuzlocke")} Nuzlocke-Läufe. Das ersetzt alle eigenen Daten.`, "Einlesen", true)) return;
    try {
      const r = await api("/api/restore", body);
      $("#restmsg").innerHTML = `<div class="note go">Eingelesen: ${r.teams} Teams, ${r.favoriten} Favoriten, ${r.gefangen} in der Sammlung, ${r.entscheidungen} Entscheidungen, ${r.jagden} Shiny-Jagden, ${r.nuzlocke} Nuzlocke-Läufe.</div>`;
      S.favGame = null; S.caughtGame = null;
      if (S.team.tid) { S.team.tid = null; S.team.dirty = false; store.set("team", S.team); }
      await Promise.all([loadFavs(true), loadCaught(true)]);
      dock();
    } catch (x) { $("#restmsg").innerHTML = `<div class="note stop">${esc(x.message)}</div>`; }
  });
  if (st.running) setTimeout(() => location.hash.startsWith("#einstellungen") && refreshMeta(), 4000);
}
/* Lesezeichen „Seite untersuchen“ (wie im VR-Navigator): läuft im Browser auf einer fremden Seite (PokéWiki, Serebii,
   GamerGuides, Pokébip …), wo die Karte erst per Skript lädt. Sammelt, was der Server beim Abruf nicht sieht: geladene
   Daten-Dateien samt Inhalt, Daten in globalen Variablen, Kartenmarker, Skripte und das fertige HTML. Ergebnis als Datei;
   nichts geht an einen Server. Muss für sich allein laufen (kein Zugriff auf diese Datei). */
async function probeHelper() {
  const box = document.createElement("div");
  box.style.cssText = "position:fixed;z-index:2147483647;top:12px;right:12px;width:min(420px,90vw);background:#253033;color:#e8eeee;"
    + "border:1px solid #5b7a80;border-radius:8px;padding:12px;font:14px system-ui,sans-serif;box-shadow:0 4px 18px rgba(0,0,0,.5)";
  box.textContent = "Pokédex: warte, bis die Seite fertig geladen hat …";
  document.body.appendChild(box);
  const wait = (t) => new Promise((r) => setTimeout(r, t));
  // Anmeldedaten der Seite (etwa der Benutzername im Wiki) gehören nicht in die Probe; auch in Text mit \"…\"
  const KEYS = "wgUserName|wgUserId|wgUserEmail|wgUserGroups|wgUserRights|wgUserEditCount|wgUserRegistration|csrfToken|editToken|token|userId|username|email";
  const scrub = (t) => String(t).replace(new RegExp(`(\\\\?["']?)\\b(${KEYS})\\1\\s*[:=]\\s*(?:(\\\\?["'])(?:(?!\\3).)*?\\3|-?\\d+|null|\\[[^\\]]*\\])`, "gi"),
    (m, q, k, v) => `${q}${k}${q}:${v || q || '"'}–${v || q || '"'}`);
  await wait(1500);
  const skip = /\.(png|jpe?g|gif|webp|avif|svg|ico|css|woff2?|ttf|mp3|ogg|mp4|webm)(\?|#|$)/i;
  const res = performance.getEntriesByType("resource").map((e) => ({url: e.name, typ: e.initiatorType, bytes: e.transferSize || e.encodedBodySize || 0}));
  const wanted = res.filter((r) => !skip.test(r.url) && (r.typ === "fetch" || r.typ === "xmlhttprequest" || /\.(json|geojson|csv|txt)(\?|$)|api\.php|\/api\//i.test(r.url)));
  const bodies = {};
  let total = 0, i = 0;
  for (const r of wanted.slice(0, 40)) {
    if (total > 6e6) break;
    box.textContent = `Pokédex: lese Daten-Datei ${++i} von ${Math.min(40, wanted.length)} …`;
    try { const t = await (await fetch(r.url, {credentials: "same-origin"})).text(); bodies[r.url] = scrub(t.slice(0, 2e6)); total += bodies[r.url].length; }
    catch (e) { bodies[r.url] = "nicht lesbar: " + e.message; }
  }
  box.textContent = "Pokédex: sammle Variablen und Marker …";
  const fr = document.createElement("iframe");
  fr.style.display = "none"; document.body.appendChild(fr);
  const base = new Set(Object.getOwnPropertyNames(fr.contentWindow)); fr.remove();
  const globals = {};
  for (const k of Object.getOwnPropertyNames(window)) {
    if (base.has(k) || /^(on|webkit)/.test(k)) continue;
    let v; try { v = window[k]; } catch (e) { continue; }
    if (!v || typeof v !== "object" || v instanceof Node) continue;
    try { const j = JSON.stringify(v); if (j && j.length > 100) globals[k] = scrub(j.slice(0, 5e5)); }
    catch (e) { try { globals[k] = "Objekt mit " + Object.keys(v).slice(0, 40).join(", "); } catch (x) { /* fremd */ } }
  }
  const cls = (e) => String(typeof e.className === "string" ? e.className : e.className?.baseVal || "").slice(0, 120);
  const marks = [...document.querySelectorAll(".leaflet-marker-icon,[class*=marker],[class*=Marker],[class*=pin],[data-lat],[data-x],[data-id] > img")].slice(0, 8000)
    .map((e) => ({cls: cls(e), title: e.getAttribute("title") || e.getAttribute("alt") || e.getAttribute("aria-label") || "", style: (e.getAttribute("style") || "").slice(0, 200),
      data: Object.assign({}, e.dataset), src: (e.getAttribute("src") || "").slice(0, 200), text: (e.innerText || "").trim().slice(0, 80)}));
  const scripts = [...document.scripts].map((x) => scrub(x.src || `inline, ${x.textContent.length} Zeichen: ${x.textContent.slice(0, 400)}`));
  box.remove();
  const html = scrub(document.documentElement.outerHTML.slice(0, 3e6));
  document.body.appendChild(box);
  const txt = JSON.stringify({art: "pokedex-probe", fassung: 1, am: new Date().toISOString(), url: location.href, titel: document.title,
    ressourcen: res, inhalte: bodies, variablen: globals, marker: marks, skripte: scripts, html});
  const host = location.hostname.replace(/^www\./, "").replace(/[^a-z0-9.-]/gi, "");
  const name = `pokedex-probe-${host}-${(location.pathname.split("/").filter(Boolean).pop() || "start").replace(/[^\w.-]/g, "_").slice(0, 60)}.json`;
  box.textContent = "";
  const p = document.createElement("p");
  p.style.margin = "0 0 8px";
  p.textContent = `Gelesen: ${wanted.length} Daten-Dateien, ${Object.keys(globals).length} Variablen, ${marks.length} Marker, ${Math.round(txt.length / 1024)} KB. `
    + "Datei sichern und in den Testdaten-Ordner legen; sie enthält nur, was diese Seite zeigt.";
  const btn = (t, main) => { const b = document.createElement("button"); b.textContent = t;
    b.style.cssText = "margin:0 8px 0 0;padding:6px 12px;border-radius:6px;font:600 13px system-ui,sans-serif;cursor:pointer;border:1px solid #5b7a80;"
      + (main ? "background:#3f8f86;color:#fff" : "background:#1c2426;color:#e8eeee"); return b; };
  const f = btn("Als Datei sichern", true);
  f.onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([txt], {type: "application/json"})); a.download = name;
    document.body.appendChild(a); a.click(); a.remove(); };
  const c = btn("Schließen");
  c.onclick = () => box.remove();
  box.append(p, f, c);
}
const probeBm = () => "javascript:" + encodeURIComponent(`(${probeHelper})()`);
async function copyText(txt, btn) {
  try { await navigator.clipboard.writeText(txt); }
  catch (e) {     // ohne HTTPS gibt es die Zwischenablage-Schnittstelle nicht; dann der alte Weg
    const ta = document.createElement("textarea");
    ta.value = txt; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove();
  }
  const old = btn.textContent;
  btn.textContent = "Kopiert ✓";
  setTimeout(() => { btn.textContent = old; }, 1500);
}
function download(name, txt, type = "text/plain") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([txt], {type: type + ";charset=utf-8"}));
  a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
/* Verbindungstest: läuft auf dem Server weiter, auch wenn du den Reiter wechselst; die Einstellungen zeigen beim
   Öffnen den Stand (Fortschritt oder letztes Ergebnis) */
let diagPoll = 0;
async function diag(start = true) {
  if (start) await api("/api/diag", {});
  const sub = $("#diagsub"), my = ++diagPoll;
  if (sub && start) sub.open = true;
  const poll = async () => {
    if (my !== diagPoll) return;
    const d = await api("/api/diag").catch(() => null);
    const el = $("#diag"), sub = $("#diagsub");
    if (!el) return;                           // andere Seite: beim nächsten Öffnen der Einstellungen weiter
    if (!d) { setTimeout(poll, 3000); return; } // Dienst gerade beschäftigt oder Netz weg: nicht aufgeben
    const hint = $("summary .hint", sub), btn = $('[data-act="diag"]');
    if (btn) { btn.disabled = !!d.running; btn.textContent = d.running ? "Test läuft …" : "Verbindung testen"; }   // 0.49: nicht doppelt starten
    if (d.running) {
      const pc = d.gesamt ? Math.round(d.fertig / d.gesamt * 100) : 0;
      hint.textContent = d.gesamt ? `läuft … ${d.fertig} von ${d.gesamt}` : "läuft …";
      el.innerHTML = `<div class="dprog"><i style="width:${pc}%"></i></div><p class="hint">${d.gesamt ? `${d.fertig} von ${d.gesamt} Abfragen fertig. ` : ""}${d.laeuft?.length ? "Gerade: " + esc(d.laeuft.join(" · ")) : d.gesamt ? "Wartet auf die Pause zwischen zwei Abfragen am selben Server." : ""}</p>`;
      $("#dlinks").innerHTML = "";
      setTimeout(poll, 1000); return;
    }
    if (!d.lines && !d.error) return;          // noch kein Test seit dem Start des Dienstes
    el.innerHTML = `<div class="log" id="dlog">${esc((d.lines || []).join("\n") || d.error)}</div>`;
    const bad = (d.lines || []).filter((x) => /keine Verbindung|gesperrt|Prüfseite|HTTP [45]\d\d|Fehler im Test/.test(x)).length;
    hint.textContent = (d.lines || []).length ? `${d.dauer != null ? `${Math.floor(d.dauer / 60)}:${String(d.dauer % 60).padStart(2, "0")} min, ` : ""}${bad ? `${bad} von ${d.gesamt} ohne Erfolg` : `${d.gesamt} ok`}` : "ohne Ergebnis";
    hint.dataset.tip = d.start ? `Gestartet ${deTime(d.start)}; ${d.gesamt} Abfragen` : "";
    // Kopieren und Herunterladen erst, wenn es ein Ergebnis gibt
    $("#dlinks").innerHTML = (d.lines || []).length ? `<button class="link" data-act="copy" data-src="#dlog">kopieren</button> · <button class="link" data-act="dl" data-src="#dlog" data-name="pokedex-verbindungstest">herunterladen</button>`
      + (d.proben ? ` · <a href="/api/diag/proben" download data-tip="Gekürzte Rohseiten der Quellen (${d.proben}), aus denen sich Leser für sie bauen lassen. Liegen nur im Speicher des Dienstes; der nächste Test ersetzt sie">Proben</a>` : "") : "";
  };
  poll();
}

