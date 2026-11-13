// Vergleichswerte für tests/schaden_referenz.json aus @smogon/calc (MIT). Nur ein Werkzeug für die Entwicklung: Der
// Pokédex braucht weder Node noch dieses Paket, die Tests lesen nur die erzeugte JSON-Datei.
//
//   mkdir /tmp/calc && cd /tmp/calc && npm install --ignore-scripts @smogon/calc@0.12.0
//   NODE_PATH=/tmp/calc/node_modules node tools/schaden_referenz.js > tests/schaden_referenz.json
//
// Die Fälle sind fest (eigener Zufallsgenerator mit festem Startwert), ein neuer Lauf ergibt dieselbe Datei.
const {calculate, Generations, Pokemon, Move, Field} = require("@smogon/calc");
const pkg = require("@smogon/calc/package.json");

const TYPE_ID = {Normal: 1, Fighting: 2, Flying: 3, Poison: 4, Ground: 5, Rock: 6, Bug: 7, Ghost: 8, Steel: 9, Fire: 10, Water: 11,
  Grass: 12, Electric: 13, Psychic: 14, Ice: 15, Dragon: 16, Dark: 17, Fairy: 18};
const MOVES = ["Return", "Earthquake", "Rock Slide", "Surf", "Flamethrower", "Ice Beam", "Thunderbolt", "Psychic", "Shadow Ball",
  "Aerial Ace", "Quick Attack", "Crunch", "Dragon Claw", "Sludge Bomb", "Hydro Pump", "Fire Blast", "Outrage", "Dragon Breath",
  "X-Scissor", "Energy Ball", "Dark Pulse", "Iron Head", "Moonblast", "Water Gun", "Ember", "Body Slam", "Blizzard", "Wing Attack",
  "Ice Punch", "Fire Punch", "Thunder Punch", "Bite", "Twister", "Mega Drain"];
const TYPE_ITEM = {Fire: "Charcoal", Water: "Mystic Water", Grass: "Miracle Seed", Electric: "Magnet", Ice: "Never-Melt Ice",
  Fighting: "Black Belt", Poison: "Poison Barb", Ground: "Soft Sand", Flying: "Sharp Beak", Psychic: "Twisted Spoon",
  Bug: "Silver Powder", Rock: "Hard Stone", Ghost: "Spell Tag", Dragon: "Dragon Fang", Dark: "Black Glasses", Steel: "Metal Coat",
  Normal: "Silk Scarf", Fairy: "Pixie Plate"};
const SKIP = /-|Arceus|Silvally|Shedinja|Ditto|Castform|Cherrim|Kecleon|Terapagos|Ogerpon|Pikachu|Clamperl|Cubone|Marowak|Latios|Latias|Smeargle|Unown|Wobbuffet|Wynaut/;
const id = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
const key = (s) => s.toLowerCase().replace(/ /g, "-").replace(/[^a-z0-9-]/g, "");

let seed = 20261113;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const pick = (a) => a[Math.floor(rnd() * a.length)];
const stats6 = (b) => [b.hp, b.atk, b.def, b.spa, b.spd, b.spe];

const out = {quelle: `@smogon/calc ${pkg.version} (MIT)`, erzeugt_mit: "tools/schaden_referenz.js", typen: TYPE_ID, tabellen: {}, faelle: []};
const WANT = {1: 30, 2: 60, 3: 80, 4: 100, 5: 60, 6: 40, 7: 40, 8: 40, 9: 100};
for (const g of [1, 2, 3, 4, 5, 6, 7, 8, 9]) {
  const gen = Generations.get(g);
  const chart = {};
  for (const t of gen.types) {
    if (!TYPE_ID[t.name]) continue;
    chart[TYPE_ID[t.name]] = {};
    for (const [d, f] of Object.entries(t.effectiveness)) if (TYPE_ID[d]) chart[TYPE_ID[t.name]][TYPE_ID[d]] = f;
  }
  out.tabellen[g] = chart;
  const species = [...gen.species].filter((s) => !SKIP.test(s.name) && s.baseStats.hp > 1).map((s) => s.name).sort();
  const moves = MOVES.filter((m) => { const x = gen.moves.get(id(m)); return x && x.basePower > 1; });
  let n = 0, tries = 0;
  while (n < WANT[g] && tries++ < 5000) {
    const an = pick(species), dn = pick(species), mn = pick(moves);
    const md = gen.moves.get(id(mn));
    const mtype = md.type;
    const special = g <= 3 ? !["Normal", "Fighting", "Flying", "Poison", "Ground", "Rock", "Bug", "Ghost", "Steel"].includes(mtype) : md.category === "Special";
    const natUp = special ? "Modest" : "Adamant", natDown = special ? "Adamant" : "Modest";
    const nature = g >= 3 ? pick([natUp, "Hardy", "Hardy", natDown]) : "Hardy";
    const level = pick([50, 50, 100, 100, 5 + Math.floor(rnd() * 96)]);
    const dLevel = pick([level, level, 5 + Math.floor(rnd() * 96)]);
    const aEv = g >= 3 ? pick([252, 252, 0, 4 * Math.floor(rnd() * 64)]) : 252;
    const inv = pick([[0, 0], [252, 0], [252, 252]]);
    // Fähigkeit und Item: nur was der Pokédex einrechnet, sonst etwas ohne Wirkung
    let ability = "Inner Focus", item = "", dAbility = "Inner Focus", weather = "", tera = "", dTera = "";
    const r = rnd();
    if (g >= 3 && r < 0.35) ability = pick(["Huge Power", "Hustle"].concat(g >= 4 ? ["Technician", "Adaptability", "Adaptability"] : []).concat(g >= 8 ? ["Gorilla Tactics"] : []));
    const r2 = rnd();
    if (g >= 2 && r2 < 0.55) {
      const cand = [TYPE_ITEM[mtype], TYPE_ITEM[mtype]];
      if (g === 2 && mtype === "Dragon") cand.push("Dragon Scale", "Dragon Scale");
      if (g === 3 && mtype === "Water") cand.push("Sea Incense");
      if (g >= 3) cand.push("Choice Band");
      if (g >= 4) cand.push("Choice Specs", "Life Orb", "Life Orb", "Expert Belt", "Expert Belt");
      item = pick(cand);
      if (!gen.items.get(id(item))) item = "";
    }
    if (g >= 3 && rnd() < 0.3) {
      const cand = ["Thick Fat", "Levitate"].concat(g >= 4 ? ["Heatproof", "Dry Skin"] : []).concat(g >= 9 ? ["Purifying Salt", "Water Bubble"] : []);
      dAbility = pick(cand);
      if (!gen.abilities.get(id(dAbility))) dAbility = "Inner Focus";
    }
    if (g >= 2 && rnd() < 0.3) weather = pick(["Sun", "Rain"]);
    if (g === 9 && rnd() < 0.5) tera = pick([mtype, mtype, pick(Object.keys(TYPE_ID))]);
    if (g === 9 && rnd() < 0.25) dTera = pick(Object.keys(TYPE_ID));
    const crit = rnd() < 0.2, doubles = g >= 3 && rnd() < 0.25;
    const aOpt = {level, nature, ability, item: item || undefined, evs: g >= 3 ? {[special ? "spa" : "atk"]: aEv} : undefined, teraType: tera || undefined};
    const dOpt = {level: dLevel, nature: "Hardy", ability: dAbility,
      evs: g >= 3 ? {hp: inv[0], [special ? "spd" : "def"]: inv[1]} : {hp: inv[0], def: inv[1], spa: inv[1], spd: inv[1], atk: 252, spe: 252}, teraType: dTera || undefined};
    if (g <= 2) { aOpt.evs = undefined; }
    let A, D, M, res;
    try {
      A = new Pokemon(gen, an, aOpt); D = new Pokemon(gen, dn, dOpt);
      M = new Move(gen, mn, {isCrit: crit});
      res = calculate(gen, A, D, M, new Field({weather: weather || undefined, gameType: doubles ? "Doubles" : "Singles"}));
    } catch (e) { continue; }
    let dmg = res.damage;
    if (!Array.isArray(dmg) || Array.isArray(dmg[0])) continue;
    if (g <= 2 && inv[0] !== inv[1] && inv[1]) continue;      // bis Generation 2 kennt der Pokédex nur „ohne“ oder „voll“
    const target = md.target || "normal";
    const spread = doubles && (g === 3 ? target === "allAdjacentFoes" : ["allAdjacent", "allAdjacentFoes"].includes(target));
    const sa = gen.species.get(id(an)), sd = gen.species.get(id(dn));
    out.faelle.push({gen: g, attacke: mn, level, level_vert: dLevel, staerke: md.basePower, klasse: special ? 3 : 2,
      typ: TYPE_ID[mtype], a_basis: stats6(sa.baseStats), a_typen: sa.types.map((t) => TYPE_ID[t]), d_basis: stats6(sd.baseStats),
      d_typen: sd.types.map((t) => TYPE_ID[t]), wesen: nature === "Hardy" ? 1.0 : nature === natUp ? 1.1 : 0.9, a_ev: aEv, d_ev: inv,
      krit: crit, flaeche: spread, wetter: weather === "Sun" ? "sonne" : weather === "Rain" ? "regen" : "",
      faehigkeit: ability === "Inner Focus" ? "" : key(ability), item: item ? key(item) : "", faehigkeit_vert: dAbility === "Inner Focus" ? "" : key(dAbility),
      tera: tera ? TYPE_ID[tera] : null, tera_vert: dTera ? TYPE_ID[dTera] : null, kp: D.maxHP(), werte: dmg});
    n++;
  }
}
process.stdout.write(JSON.stringify(out).replace(/\{"gen"/g, "\n{\"gen\"") + "\n");
