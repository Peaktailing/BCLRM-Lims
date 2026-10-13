// Run by tests/test_notebook_blocks.py: every word the notebook's
// experiment block shows has its Chinese in the catalogue the notebook
// page loads (app/translations/zh/js*.json, which base.html gives t() via
// app/i18n.py js_catalog), and no English is left outside tr().
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const ZH = join(ROOT, 'app', 'translations', 'zh');
const catalogue = {};
readdirSync(ZH).filter((f) => f.startsWith('js') && f.endsWith('.json')).sort().forEach((f) => {
  Object.entries(JSON.parse(readFileSync(join(ZH, f), 'utf8'))).forEach(([k, v]) => { if (v) catalogue[k] = v; });
});

const file = join(ROOT, 'frontend', 'src', 'blocks', 'experiment.js');
const source = readFileSync(file, 'utf8')
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n').map((line) => line.replace(/^\s*\/\/.*$/, '').replace(/\s\/\/ .*$/, '')).join('\n');

const lit = "'((?:[^'\\\\]|\\\\.)*)'";
const plain = new RegExp(`\\b(?:tr|t)\\(\\s*${lit}`, 'g');
const context = new RegExp(`\\btc\\(\\s*${lit}\\s*,\\s*${lit}`, 'g');
const wanted = [];
for (const m of source.matchAll(plain)) wanted.push(m[1]);
for (const m of source.matchAll(context)) wanted.push(`${m[1]}::${m[2]}` in catalogue ? `${m[1]}::${m[2]}` : m[2]);
assert.ok(wanted.length > 30, `only ${wanted.length} words found: has the block stopped using tr()?`);
const missing = [...new Set(wanted)].filter((w) => !(w in catalogue));
assert.deepEqual(missing, [], `no Chinese in app/translations/zh/js-*.json for:\n${missing.join('\n')}`);

// A tr() of a template string can't be looked up; a word outside tr() isn't translated.
assert.doesNotMatch(source, /\b(?:tr|t|tc)\(\s*`/, 'tr() of a template string: give it one literal and %(name)s values');
const rest = source.replace(plain, '').replace(context, '');
const bare = [
  ...rest.matchAll(/\b(?:text|title|'aria-label'):\s*'[A-Za-z][^']*'/g),
  ...rest.matchAll(/>[A-Z][a-z]+[^<$]*</g),
].map((m) => m[0]);
assert.deepEqual(bare, [], `English shown without tr():\n${bare.join('\n')}`);
