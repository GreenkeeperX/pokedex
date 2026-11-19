/* Pokédex-Oberfläche, Teil 10 von 10: Klicks und Start (läuft zuletzt: erst hier lädt die Seite Daten).
   Die Teile lädt index.html der Reihe nach; sie teilen sich die globalen Namen (docs/oberflaeche.md). */
"use strict";
/* ------------------------------------------------------------------ Klicks */
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]");
  if (!b) return;
  const act = b.dataset.act, id = +b.dataset.id;
  if (b.closest("a") || b.closest("summary")) e.preventDefault();       // „+“ auf einer Karte öffnet nicht die Detailseite; Knöpfe im Kopf klappen nicht
  try {
    if (act === "thm") themeMenu($("#thmMenu").hidden);
    else if (act === "thmset") setTheme(b.dataset.v);
    else if (act === "neu") versionsDialog();
    else if (act === "hwzu") clearNotes();
    else if (act === "neuok") { try { localStorage.setItem("px.version", S.meta.version); } catch (x) { /* egal */ } version(); }
    else if (act === "dock" && MAPFOLD && S.dock) { MAPFOLD = false; $("#dock")?.classList.remove("fold"); }   // auf der Karte: nur für diesen Besuch aufklappen
    else if (act === "dock") { MAPFOLD = false; S.dock = !S.dock; store.set("dock", S.dock); $("#dock")?.classList.remove("fold"); dock(); }
    else if (act === "teamadd") {
      const slot = addToTeam(id);
      if (slot !== null && location.hash.startsWith("#pokemon/")) location.hash = `#pokemon/${id}/${slot}`;
    } else if (act === "teamdel") {
      // Haken an einer Karte: den Platz dieses Pokémon nehmen, nie einen veralteten (0.47.4)
      const slot = b.dataset.id && S.team.ids[+b.dataset.slot] !== id ? S.team.ids.lastIndexOf(id) : +b.dataset.slot;
      if (slot >= 0) removeSlot(slot); if (location.hash.startsWith("#pokemon/")) location.hash = `#pokemon/${DETAIL?.id || ""}`; }
    else if (act === "fav") await toggleFav(id);
    else if (act === "reqdone") await toggleReq(b.dataset.id);
    else if (act === "rsdone") await toggleResearch(b);
    else if (act === "cmpclear") { store.set("cmpMerk", []); redrawMarks(); compareView(...location.hash.split("/").slice(1, 3)); }
    else if (act === "cmpmark") { cmpToggle(id); redrawMarks(); if (location.hash.startsWith("#vergleich")) compareView(...location.hash.split("/").slice(1, 3)); }
    else if (act === "favadd") { $("#pick").hidden = true; await toggleFav(id, true); }
    else if (act === "caught") await toggleCaught(id);
    else if (act === "alpha") await toggleAlpha(id);
    else if (act === "xsel") xsel(id);
    else if (act === "xall") $$("#list .mon[data-id]").forEach((el) => xsel(+el.dataset.id, true));
    else if (act === "xnone") [...XSEL].forEach((x) => xsel(x, false));
    else if (act === "xgo") await xferGo();
    else if (act === "pick") picker(b, +b.dataset.slot);
    else if (act === "favswap") { if (!teamFull()) addToTeam(id); else swapPicker(b, id); }
    else if (act === "pickfav") { $("#pick").hidden = true; addToTeam(id, +b.dataset.slot); }
    else if (act === "altpick") fullChoice(id, b.closest(".imp") || b, +b.dataset.slot);   // 0.56.2: das Häkchen tauschte ungefragt
    else if (act === "tgame") setGame(S.team.spiel);
    else if (act === "unpin") { PIN.r = null; PIN.c = null; chartView(); }
    else if (act === "copy") await copyText($(b.dataset.src)?.textContent || "", b);
    else if (act === "dl") download(`${b.dataset.name}-${new Date().toISOString().slice(0, 10)}.txt`, $(b.dataset.src)?.textContent || "");
    else if (act === "pin") {
      S.team.fest = S.team.fest.includes(id) ? S.team.fest.filter((x) => x !== id) : [...S.team.fest, id];
      saveTeam(); dock(); teamRefresh();
    } else if (act === "freset") {
      const which = b.dataset.fid === "lf" ? "filter" : "tfilter";
      S[which] = filter0(which === "tfilter" ? {endstufe: true} : {});
      store.set(which === "filter" ? "filter2" : "tfilter", S[which]);
      route();
    } else if (act === "opt") await optimize();
    else if (act === "sdexp") await sdExport();
    else if (act === "sdimp") await sdImport();
    else if (act === "sdcopy") await copyText($("#sdtext").value, b);
    else if (act === "sdcopy2") await copyText((await api("/api/team/export", {spiel: S.game, ids: S.team.ids, details: S.team.details})).text, b);
    else if (act === "take") {
      const ids = S.lastOpt[+b.dataset.i].ids, old = S.team;
      // Level und Attacken bleiben bei Pokémon, die schon im Team waren
      S.team.details = ids.map((x) => { const i = old.ids.indexOf(x); return i >= 0 ? old.details[i] : {}; });
      S.team.ids = ids;
      teamChanged();
      ids.forEach((x, i) => fillStandard(i));
    } else if (act === "tclear") { Object.assign(S.team, {ids: [], fest: [], details: []}); teamChanged(); teamView(); }
    else if (act === "tnew") {
      if (S.team.dirty && !await ask(S.team.name ? `„${S.team.name}“ hat ungespeicherte Änderungen.` : "Das Team hat ungespeicherte Änderungen.", "Trotzdem ein neues Team beginnen? Die Änderungen gehen verloren.", "Neues Team")) return;
      S.team = normTeam({spiel: S.game});
      store.set("team", S.team); dock(); location.hash.startsWith("#team") ? teamView() : (location.hash = "#team");
    } else if (act === "tsave" && S.team.tid) { await saveToServer(); dock(); if (location.hash.startsWith("#team")) teamView(); }
    else if (act === "tsave" || act === "tsaveas" || act === "trename") {
      const name = await askText(act === "trename" ? "Team umbenennen" : "Team speichern", "Name des Teams", act === "tsaveas" && S.team.tid ? S.team.name + " (Kopie)" : S.team.name || "Team " + gameName(), act === "trename" ? "Umbenennen" : "Speichern");
      if (!name) return;
      if (act === "trename") { S.team.name = name; await saveToServer(name); }
      else await saveToServer(name, act === "tsaveas");
      dock(); if (location.hash.startsWith("#team")) teamView();
    } else if (act === "tundo") {
      const tt = (await api("/api/teams")).find((x) => x.id === S.team.tid);
      if (tt) loadTeam(tt); else { S.team.dirty = false; store.set("team", S.team); }
      dock(); if (!location.hash.startsWith("#team")) route();
    } else if (act === "tdel") {
      if (!await ask(`Team „${S.team.name}“ löschen?`, "Das gespeicherte Team geht verloren; die Plätze bleiben als ungespeichertes Team stehen.", "Löschen", true)) return;
      await api("/api/teams/loeschen", {id: S.team.tid});
      S.team = normTeam({ids: S.team.ids, fest: S.team.fest, details: S.team.details});
      store.set("team", S.team); dock(); teamView();
    } else if (act === "foedel") { S.foes = S.foes.filter((x) => x !== id); store.set("foes", S.foes); matchup(); }
    else if (act === "foeclear") { S.foes = []; store.set("foes", S.foes); store.set("foeTrainer:" + S.game, null); teamView(); }
    else if (act === "trpick") pickTrainer(+b.dataset.id);
    else if (act === "logpick") { const id = +b.dataset.id, i = LOGPICK.indexOf(id); if (i >= 0) LOGPICK.splice(i, 1); else if (LOGPICK.length < 6) LOGPICK.push(id); logBox(); }
    else if (act === "logadd") { await api("/api/kampftagebuch", {spiel: S.game, ergebnis: b.dataset.res, team: S.team.ids, gegner: LOGPICK, notiz: $("#lognote")?.value || ""}); LOGPICK = []; logBox(); }
    else if (act === "logdel") { await api("/api/kampftagebuch/loeschen", {id: +b.dataset.id}); logBox(); }
    else if (act === "usagefoes") { S.foes = [...(S.usageTop || [])]; store.set("foes", S.foes); location.hash = "team"; }
    else if (act === "mvadd" || act === "mvdel" || act === "mvtake") {
      const pid = DETAIL.id, cur = ownSet(pid), mid = +b.dataset.mid;
      setOwnSet(pid, act === "mvadd" ? [...cur, mid] : act === "mvdel" ? cur.filter((x) => x !== mid) : DETAIL.attacken.moveset.map((m) => m.id));
      renderMoves(DETAIL.attacken, $("#lvl")?.value);
    } else if (act === "mvstd") {
      setOwnSet(DETAIL.id, DETAIL.attacken.standard || []);
      renderMoves(DETAIL.attacken, $("#lvl")?.value);
    } else if (act === "mreset") { store.set("mfilter2", {}); movesView(); }
    else if (act === "fehlerleeren") { await api("/api/fehler/leeren", {}); route(); }
    else if (act === "leistung") { b.disabled = true; b.textContent = "misst …"; await api("/api/leistung", {spiel: S.game}).catch((x) => hinweis(x.message)); route(); }
    else if (act === "wtest") { b.disabled = true; const r = await api("/api/wiederherstellung", {}); if (r.ok === null) hinweis(r.text); route(); }
    else if (act === "sync" || act === "rebuild") {
      await api("/api/abgleich", {neu: act === "rebuild"});
      setTimeout(refreshMeta, 800);
    } else if (act === "diag") await diag();
    else if (act === "calcfoe") { const k = "calcFoes:" + S.game; store.set(k, store.get(k, []).filter((x) => x !== id)); calcBox(); }
    else if (act === "calcgegen") { const k = BATTLE() ? "calc" : "calcT"; store.set(k, Object.assign(store.get(k, {}), {gegen: b.dataset.v})); calcBox(); }
    else if (act === "nobm") { b.dataset.tip = "Nicht hier klicken: in die Lesezeichenleiste ziehen und auf der fremden Seite anklicken"; }
    else if (act === "bmcopy") await copyText(probeBm(), b);
    else if (act === "todotask") {
      const t = await api("/api/aufgabe");
      if (t.text) await copyText(t.text, b);
    } else if (act === "todoans") { $("#todoans").hidden = !$("#todoans").hidden; if (!$("#todoans").hidden) $("#todotext").focus(); }
    else if (act === "todocsv") {
      const cell = (v) => { v = String(v ?? ""); return /[";\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v; };
      const rows = (await api("/api/pruefung")).filter((x) => !x.entscheidung).map((x) => [x.name, x.feld, x.pokeapi, x.showdown, x.key]);
      download(`pokedex-zu-erledigen-${new Date().toISOString().slice(0, 10)}.csv`, "\ufeff" + [["Was", "Feld", "PokéAPI", "Showdown", "Kennung"], ...rows].map((x) => x.map(cell).join(";")).join("\r\n"), "text/csv");
    } else if (act === "todoprev" || act === "todotake") {
      const out = $("#todoprev");
      try {
        const res = await api("/api/antwort", {text: $("#todotext").value, dry: act === "todoprev"});
        if (act === "todotake") { settingsView(); return; }
        const W = {pokeapi: "PokéAPI", showdown: "Showdown", egal: "egal"};
        out.innerHTML = (res.uebernehmen.length ? `<table class="rows"><tr><th>Was</th><th>Feld</th><th>Antwort</th><th>Grund</th></tr>${res.uebernehmen.map((x) => `<tr><td>${esc(x.name)}</td><td>${esc(x.feld)}</td><td><b>${W[x.wert]}</b></td>
            <td class="why">${esc(x.grund)}${/^https:\/\/\S+$/.test(x.quelle) ? ` <a href="${esc(x.quelle)}" target="_blank" rel="noopener noreferrer">Quelle</a>` : ""}</td></tr>`).join("")}</table>` : "")
          + (res.liegen.length ? `<p class="hint">Bleibt liegen: ${res.liegen.map((x) => `${esc(x.key)} (${esc(x.warum)})`).join(", ")}</p>` : "")
          + (res.uebernehmen.length ? `<div class="bar slim"><button class="primary" data-act="todotake">${res.uebernehmen.length} übernehmen</button></div>` : `<div class="note warn">Nichts zu übernehmen.</div>`);
      } catch (x) { out.innerHTML = `<div class="note stop">${esc(x.message)}</div>`; }
    }
    else if (act === "mvclear") { const id = DETAIL?.id; if (id != null) { setOwnSet(id, []); renderMoves(DETAIL.attacken, $("#lvl")?.value); } }
    else if (act === "dec") {
      await api("/api/entscheidung", {art: "pruefung", schluessel: b.dataset.k, wert: b.dataset.v});
      settingsView();
    }
  } catch (err) { alert(err.message); }
});
document.addEventListener("change", (e) => { if (e.target.matches("select.gamesel")) setGame(e.target.value); });
// Titel: zur Liste und alles neu laden (Spieldaten, Favoriten, Typtabelle)
$("#home").addEventListener("click", (e) => {
  e.preventDefault();
  if (location.hash !== "#pokemon") history.pushState(null, "", "#pokemon");
  S.chart = null; LS.key = ""; CHECK.key = "";
  window.scrollTo(0, 0);
  refreshMeta();
});
window.addEventListener("hashchange", route);
// Netz zum Auffangen: Was nirgends abgefangen wird, steht als Hinweis über der Ansicht statt nur in der Konsole
window.addEventListener("unhandledrejection", (e) => { hinweis(`Fehler: ${e.reason?.message || e.reason || "unbekannt"}`); });
refreshMeta().catch((e) => { main.innerHTML = `<div class="note stop">Server nicht erreichbar: ${esc(e.message)}</div>`; });
