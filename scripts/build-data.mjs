// Lädt die PokéAPI-Rohdaten (CSV) einmalig und schreibt sie als kompakte JSON-Dateien.
// Aufruf: node scripts/build-data.mjs <ausgabeordner>   (Standard: ./data)
// Optional: CSV_DIR=/pfad/zu/csv liest die CSVs lokal statt von GitHub.
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { join } from 'node:path';

const OUT = process.argv[2] || 'data';
const SRC = process.env.CSV_SRC || 'https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/';
const DE = '6', EN = '9';

function csv(t) {
  const o = []; let r = [], f = '', q = false;
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (q) { if (c === '"') { if (t[i + 1] === '"') { f += '"'; i++ } else q = false } else f += c }
    else if (c === '"') q = true;
    else if (c === ',') { r.push(f); f = '' }
    else if (c === '\n') { r.push(f); o.push(r); r = []; f = '' }
    else if (c !== '\r') f += c;
  }
  if (f || r.length) { r.push(f); o.push(r) }
  const h = o.shift();
  return o.filter(x => x.length > 1).map(x => Object.fromEntries(h.map((k, i) => [k, x[i]])));
}

async function load(name) {
  if (process.env.CSV_DIR) return csv(await readFile(join(process.env.CSV_DIR, name + '.csv'), 'utf8'));
  for (let attempt = 1; ; attempt++) {
    try {
      const r = await fetch(SRC + name + '.csv');
      if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
      return csv(await r.text());
    } catch (e) {
      if (attempt >= 4) throw e;
      await new Promise(res => setTimeout(res, 2000 * attempt));
    }
  }
}

const names = ['pokemon', 'pokemon_species', 'pokemon_species_names', 'pokemon_types', 'pokemon_stats',
  'type_names', 'type_efficacy', 'moves', 'move_names', 'version_groups', 'versions', 'version_names',
  'pokemon_moves', 'pokemon_move_methods'];
const D = Object.fromEntries(await Promise.all(names.map(async n => [n, await load(n)])));

// Typen (nur die 18 regulären) und Effektivität
const types = {};
D.type_names.filter(r => r.local_language_id === DE && +r.type_id <= 18).forEach(r => types[r.type_id] = r.name);
const eff = Array.from({ length: 18 }, () => Array(18).fill(100));
D.type_efficacy.filter(r => +r.damage_type_id <= 18 && +r.target_type_id <= 18)
  .forEach(r => eff[r.damage_type_id - 1][r.target_type_id - 1] = +r.damage_factor);

// Arten, Namen, Typen, Werte
const S = {}, parents = new Set(), N = {}, T = {}, ST = {};
D.pokemon_species.forEach(r => {
  S[r.id] = { i: r.identifier, g: +r.generation_id, l: r.is_legendary === '1' || r.is_mythical === '1' };
  if (r.evolves_from_species_id) parents.add(r.evolves_from_species_id);
});
D.pokemon_species_names.forEach(r => {
  if (r.local_language_id === DE || (r.local_language_id === EN && !N[r.pokemon_species_id])) N[r.pokemon_species_id] = r.name;
});
D.pokemon_types.forEach(r => (T[r.pokemon_id] = T[r.pokemon_id] || [])[r.slot - 1] = +r.type_id);
D.pokemon_stats.forEach(r => (ST[r.pokemon_id] = ST[r.pokemon_id] || [])[r.stat_id - 1] = +r.base_stat);

// Pokémon: [id, Art-ID, Formkürzel, Kennung, Name, Typen, Basiswerte, Generation, legendär, Endstufe]
const pokemon = D.pokemon.filter(r => T[r.id] && ST[r.id] && S[r.species_id]).map(r => {
  const s = S[r.species_id];
  return [+r.id, +r.species_id, r.identifier.slice(s.i.length + 1), r.identifier, N[r.species_id] || s.i,
    T[r.id].filter(Boolean), ST[r.id], s.g, s.l ? 1 : 0, parents.has(r.species_id) ? 0 : 1];
});
const ids = new Set(pokemon.map(p => p[0]));

// Attacken: {id: [Name, Typ, Stärke, Genauigkeit, AP, Klasse(1 Status, 2 physisch, 3 speziell)]}
const MN = {};
D.move_names.forEach(r => { if (r.local_language_id === DE) MN[r.move_id] = r.name });
const moves = {};
D.moves.forEach(r => moves[r.id] = [MN[r.id] || r.identifier, +r.type_id, +r.power || 0, +r.accuracy || 0, +r.pp || 0, +r.damage_class_id]);

// Editionen mit deutschen Namen
const VN = {};
D.version_names.filter(r => r.local_language_id === DE).forEach(r => VN[r.version_id] = r.name);
const VV = {};
D.versions.forEach(v => (VV[v.version_group_id] = VV[v.version_group_id] || []).push(VN[v.id] || v.identifier));
const versionGroups = D.version_groups.sort((a, b) => b.order - a.order)
  .map(v => [v.identifier, (VV[v.id] || [v.identifier]).join(' / '), +v.generation_id]);

// Erlernbare Attacken je Pokémon und Edition: {Edition: [[Attacke, Methode, Level], …]}
const VG = Object.fromEntries(D.version_groups.map(v => [v.id, v.identifier]));
const MM = Object.fromEntries(D.pokemon_move_methods.map(m => [m.id, m.identifier]));
const learn = {};
D.pokemon_moves.forEach(r => {
  if (!ids.has(+r.pokemon_id)) return;
  const p = learn[r.pokemon_id] = learn[r.pokemon_id] || {}, v = VG[r.version_group_id];
  const l = p[v] = p[v] || [];
  if (!l.some(x => x[0] === +r.move_id && x[1] === MM[r.pokemon_move_method_id])) l.push([+r.move_id, MM[r.pokemon_move_method_id], +r.level || 0]);
});

// Formen ohne eigene Liste (z. B. Mega-Entwicklungen) erben die Liste der Standardform
pokemon.forEach(p => { if (!learn[p[0]] && learn[p[1]]) learn[p[0]] = learn[p[1]] });

await mkdir(join(OUT, 'learn'), { recursive: true });
const core = { generated: new Date().toISOString(), types, eff, pokemon, moves, versionGroups };
await writeFile(join(OUT, 'core.json'), JSON.stringify(core));
await Promise.all(Object.entries(learn).map(([id, v]) => writeFile(join(OUT, 'learn', id + '.json'), JSON.stringify(v))));
console.log(`${pokemon.length} Pokémon, ${Object.keys(moves).length} Attacken, ${Object.keys(learn).length} Lernlisten → ${OUT}`);
