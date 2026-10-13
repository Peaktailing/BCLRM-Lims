// Run by tests/test_notebook_blocks.py: the notebook's experiment block
// names the reagent a recorded day used and its lot, "(expired)" when the
// lot had expired by that day, in the experiment page's words.
import assert from 'node:assert/strict';
import { reagentText, reagentUsed } from '../../frontend/src/blocks/experiment.js';

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
