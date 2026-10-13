// Run by tests/test_notebook_blocks.py: the notebook's experiment block
// names the reagent a recorded day used and its lot, "(expired)" when the
// lot had expired by that day, in the experiment page's words; and shows
// the main readout or another measure, the one its setting names.
import assert from 'node:assert/strict';
import { chosenReadout, num, readouts, reagentText, reagentUsed, tc } from '../../frontend/src/blocks/experiment.js';

const rec = (reagent, doneOn = '2026-10-05') => ({ done_on: doneOn, reagent });

assert.equal(reagentText(rec({ id: 3, name: 'Tamoxifen', lot: 'L7', expires: '2027-01-01', inventory: 'Reagents' })),
  'Tamoxifen lot L7');
// Expired before the day it was used; the day it expires still counts as good.
assert.equal(reagentText(rec({ name: 'Tamoxifen', lot: 'L0', expires: '2026-10-01' })), 'Tamoxifen lot L0 (expired)');
assert.equal(reagentText(rec({ name: 'Tamoxifen', lot: 'L0', expires: '2026-10-05' })), 'Tamoxifen lot L0');
// A lot typed by hand has no expiry; an item without a lot is just its name.
assert.equal(reagentText(rec({ name: 'Tamoxifen', lot: 'X-77', expires: '' })), 'Tamoxifen lot X-77');
assert.equal(reagentText(rec({ name: 'PBS', lot: '', expires: '' })), 'PBS');
assert.deepEqual(reagentUsed(rec({ name: 'PBS', lot: '', expires: '2020-01-01' })), { name: 'PBS', lot: '', expired: true });
// A day that kept none (recorded before 1.11.0, or a step with no reagent), or not yet done.
assert.equal(reagentText(rec({})), '');
assert.equal(reagentText(rec(undefined)), '');
assert.equal(reagentText(null), '');
// The words go through the page's translation.
const zh = { 'lot %(lot)s': '批号 %(lot)s', '(expired)': '（已过期）' };
const t = (text, values) => (zh[text] || text).replace(/%\((\w+)\)s/g, (_m, k) => values[k]);
assert.equal(reagentText(rec({ name: 'Tamoxifen', lot: 'L0', expires: '2026-01-01' }), t), 'Tamoxifen 批号 L0 （已过期）');

// A word the page names in context: its "context::English" entry first, else the plain one.
const zhc = { 'experiment::active': '进行中', 'experiment::Day': '日期', Day: '日', Today: '今天' };
const tz = (text) => zhc[text] || text;
assert.equal(tc('experiment', 'active', tz), '进行中');
assert.equal(tc('experiment', 'Day', tz), '日期');
assert.equal(tc('experiment', 'Today', tz), '今天');
assert.equal(tc('experiment', 'paused', tz), 'paused');

// The main readout, then each other measure; the block's setting picks one,
// and one the experiment no longer has (or none) is the main readout.
const table = (values) => ({ dates: ['2026-10-01'], days: [1], rows: [{ key: 'mouse:1', values, pct: [100] }] });
const exp = {
  readout: { key: 'body_weight', label: 'Body weight', unit: 'g', kind: 'value' },
  weights: table([20.5]),
  measures: [{ key: 'measure:1', label: 'IL-6 ELISA', unit: 'pg/mL', kind: 'value', measure: true, table: table([0.45]) }],
};
assert.deepEqual(readouts(exp).map((r) => [r.key, r.readout.label]), [['main', 'Body weight'], ['measure:1', 'IL-6 ELISA']]);
assert.equal(chosenReadout(exp, 'measure:1').table.rows[0].values[0], 0.45);
assert.equal(chosenReadout(exp, undefined).readout.label, 'Body weight');
assert.equal(chosenReadout(exp, 'measure:9').key, 'main');
// A frozen copy from before measures (and one from the first version, with no readout) shows what it showed.
assert.deepEqual(readouts({ weights: table([21]) }).map((r) => [r.key, r.readout.label, r.readout.unit]), [['main', 'Body weight', 'g']]);
assert.equal(chosenReadout({ readout: exp.readout, weights: exp.weights }, 'measure:1').key, 'main');
// Values as the page's sheet writes them: an OD keeps its second decimal.
assert.deepEqual([num(0.45), num(20), num(24.567), num(1.2)], ['0.45', '20', '24.57', '1.2']);
