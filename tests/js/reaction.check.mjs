// Run by tests/test_notebook_blocks.py: a Reaction's equivalents, limiting
// reagent, theoretical yield and recorded yield, in Node — the same aspirin
// synthesis the chemical experiment plans do (tests/test_chemical_experiments.py:
// the acid at 2, the anhydride at 1, 1.381 g of acid limiting, 0.9008 g of
// aspirin), so the block and the plans read one set of numbers.
import assert from 'node:assert/strict';
import { compute, equationText, normalize } from '../../frontend/src/blocks/reaction.js';

// The tolerance the chemical experiment tests use (assertAlmostEqual with
// places=3): 1.381 g is 9.9985 mmol, not the round 10 mmol of the comment,
// and 0.90066 g of aspirin, not 0.9008 — the block and the plans read the
// same numbers to the same precision.
const close = (a, b, tol = 5e-4) => assert.ok(Math.abs(a - b) <= tol * Math.max(1, Math.abs(b)), `${a} ≠ ${b}`);

const SALICYLIC = '69-72-7';    // C7H6O3, 138.121
const ANHYDRIDE = '108-24-7';   // C4H6O3, 102.089
const ASPIRIN = '50-78-6';      // C9H8O4, 180.159
const ACETIC = '64-19-7';       // C2H4O2, 60.052

const data = {
  name: 'Aspirin synthesis',
  sides: [
    { side: 'reactant', cas: SALICYLIC, name: 'Salicylic acid', coef: '2', mw: '138.121', role: 'reactant', weighed: '1.381', unit: 'g' },
    { side: 'reactant', cas: ANHYDRIDE, name: 'Acetic anhydride', coef: '1', mw: '102.089', role: 'reactant', weighed: '1.021', unit: 'g' },
    { side: 'product', cas: ASPIRIN, name: 'Aspirin', coef: '1', mw: '180.159' },
    { side: 'product', cas: ACETIC, name: 'Acetic acid', coef: '1', mw: '60.052' },
  ],
  product: 2, actual: '', log: [],
};

let got = compute(data);
assert.equal(got.limiting.row.cas, SALICYLIC, 'the acid runs out first');
close(got.limiting_moles, 0.01);                       // 1.381 g is 10 mmol
close(got.rows[0].eq, 1);                              // the basis
close(got.rows[1].eq, 2.0);                            // the anhydride at two equivalents
close(got.product_moles, 0.005);                       // the acid's extent, one aspirin each
close(got.product_grams, 0.9008);
assert.ok(Number.isNaN(got.percent));                  // nothing obtained yet
assert.equal(got.rows[0].isBasis, true);
assert.equal(got.rows[1].isLimiting, undefined);

// The yield recorded against it: 0.72 g is 79.9 %, as the plan records it.
data.actual = '0.72';
got = compute(data);
assert.equal(got.percent, 79.9);
assert.equal(got.warning, '');
data.actual = '1.4';
assert.ok(compute(data).warning.startsWith('over the theoretical'));
data.actual = '0.01';
assert.ok(compute(data).warning.startsWith('very low'));
data.actual = '';

// The equation as one line.
assert.equal(equationText(data), '2 Salicylic acid + Acetic anhydride → Aspirin + Acetic acid');
assert.equal(equationText(normalize({})), '… → …');

// A solvent and a workup reagent are in the flask but never the limiting
// one, and have no equivalents.
data.sides.push({ side: 'reactant', cas: '67-64-1', name: 'Acetone', coef: '1', mw: '58.08', role: 'solvent', weighed: '5', unit: 'g' });
data.sides.push({ side: 'reactant', cas: '7732-18-5', name: 'Water', coef: '1', mw: '18.015', role: 'workup', weighed: '10', unit: 'g' });
got = compute(data);
assert.equal(got.limiting.row.cas, SALICYLIC);
close(got.rows[0].eq, 1);                              // the solvent does not move the basis
close(got.rows[4].moles, 5 / 58.08);                   // but its amount is still worked out
assert.ok(Number.isNaN(got.rows[4].eq), 'a solvent has no equivalents');

// Masses in other units, and a mass with no molecular weight.
data.sides[1].weighed = '1020.9';
data.sides[1].unit = 'mg';
close(compute(data).rows[1].moles, 0.01);
data.sides[3].mw = '';
assert.ok(Number.isNaN(compute(data).rows[3].moles), 'no molecular weight, no moles');
data.sides[3].mw = '60.052';
data.sides[1].weighed = '1.021';
data.sides[1].unit = 'g';

// Without a mass weighed there is no limiting reagent, and the block says
// which reactants to weigh.
const unweighed = { ...data, sides: data.sides.map((r) => ({ ...r, weighed: '' })) };
got = compute(unweighed);
assert.equal(got.limiting, null);
assert.deepEqual(got.notWeighed, ['Salicylic acid', 'Acetic anhydride']);
assert.ok(Number.isNaN(got.product_grams));

// A product picked other than the first: the yield counts against it.
const byproduct = { ...data, product: 3 };
close(compute(byproduct).product_grams, 0.005 * 60.052);

// normalize() repairs a product index that no longer points at a product.
assert.equal(normalize({ ...data, product: 0 }).product, 2);
assert.equal(normalize({ ...data, product: 99 }).product, 2);
assert.equal(normalize({ sides: [] }).product, -1);

console.log('ok');
