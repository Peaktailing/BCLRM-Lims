// Reaction block: an equation and what came of it. Each side's substances
// are picked from the lab's Chemicals database the way a Formulation picks
// its components — with the CAS number, the formula and the molecular
// weight coming along — or typed in with a CAS number, which the server
// completes from the chemical references (/notebook/api/reaction).
//
// What was weighed at the bench goes in the Weighed column; the block works
// out each reactant's equivalents against the first one, which reactant
// runs out first (the limiting reagent), and what the equation says the
// chosen product should come to. The mass that actually came out of the
// flask is recorded against it — the percent yield, with chemlib's
// warning when the number cannot be true — and each recording is kept in
// the page as a line of the record, which is the ELN write-back.
//
// The arithmetic mirrors app/chemlib.py (equivalents, limiting_reagent,
// theoretical_yield, percent_yield) so the block and the chemical
// experiment plans read the same numbers; the CAS numbers and the
// molecular weights only the lab's records know are fetched from the
// server, which also checks the equation balances.
//
// data = {
//   name, notes,
//   sides: [{ side: 'reactant'|'product', cas, name, coef, mw, formula,
//             role: 'reactant'|'catalyst'|'solvent'|'workup',   (reactants)
//             weighed, unit: 'g' }],                            (reactants)
//   product: <index of the product the yield counts>,
//   actual: '<grams obtained>',
//   log: [{ at: ISO, grams, percent }],   one line per recording
// }

import { api, debounce, escapeHtml, fmt, toNumber } from '../util.js';
import { MASS_UNITS, showMass, unitOptions } from './units.js';
import { showMol } from './formulation.js';

const WEIGH_UNITS = { kg: MASS_UNITS.kg, g: MASS_UNITS.g, mg: MASS_UNITS.mg, 'µg': MASS_UNITS['µg'] };

// The roles a substance plays. A reactant and a catalyst go into the yield
// arithmetic; a solvent and a workup reagent are there in bulk and are
// never the limiting one (app/chemical_experiments.py REAGENT_ROLES).
export const ROLES = ['reactant', 'catalyst', 'solvent', 'workup'];
const COUNTED_ROLES = ['reactant', 'catalyst'];

export function emptyRow(side) {
  const base = { side: side === 'product' ? 'product' : 'reactant', cas: '', name: '', coef: '1', mw: '', formula: '' };
  return side === 'product' ? base : { ...base, role: 'reactant', weighed: '', unit: 'g' };
}

export function defaultReaction() {
  return { name: '', notes: '', sides: [emptyRow('reactant'), emptyRow('reactant'), emptyRow('product')],
           product: 2, actual: '', log: [] };
}

export function normalize(data) {
  const d = { ...defaultReaction(), ...(data || {}) };
  d.sides = Array.isArray(d.sides)
    ? d.sides.map((r) => ({ ...emptyRow(r && r.side), ...(r || {}) })).filter((r) => r && typeof r === 'object')
    : [];
  d.log = Array.isArray(d.log) ? d.log.filter((e) => e && Number.isFinite(Number(e.grams))) : [];
  const firstProduct = d.sides.findIndex((r) => r.side === 'product');
  d.product = Number.isInteger(d.product) && d.sides[d.product] && d.sides[d.product].side === 'product'
    ? d.product : Math.max(firstProduct, -1);
  return d;
}

// ---------------------------------------------------------------- the arithmetic

// chemlib rounds the theoretical yield to 4 decimals and the percent to 1.
const round4 = (n) => Math.round(n * 1e4) / 1e4;
const round1 = (n) => Math.round(n * 10) / 10;

function gramsOf(row) {
  const g = toNumber(row.weighed);
  return Number.isFinite(g) ? g * (WEIGH_UNITS[row.unit] ?? 1) : NaN;
}

function mwOf(row) {
  const m = toNumber(row.mw);
  return Number.isFinite(m) && m > 0 ? m : NaN;
}

function coefOf(row) {
  const c = toNumber(row.coef);
  return Number.isFinite(c) && c > 0 ? c : NaN;
}

// Every row with its moles, equivalents and share of the yield; the
// limiting reagent; what the chosen product comes to; the percent yield
// of what was obtained. NaN where the arithmetic has nothing to stand on
// (no mass weighed, no molecular weight, no product chosen).
export function compute(data) {
  const d = normalize(data);
  const rows = d.sides.map((row, i) => ({ i, row, side: row.side }));
  for (const x of rows) {
    x.grams = x.side === 'reactant' ? gramsOf(x.row) : NaN;
    x.moles = Number.isFinite(x.grams) && Number.isFinite(mwOf(x.row)) ? x.grams / mwOf(x.row) : NaN;
    x.counted = x.side === 'reactant' && COUNTED_ROLES.includes(x.row.role || 'reactant');
  }
  // The basis is the first reactant in the equation, as chemlib's
  // equivalents() takes it: 1.00, the others count against it.
  const basis = rows.find((x) => x.side === 'reactant');
  const basisMol = basis ? basis.moles : NaN;
  const basisCoef = basis ? coefOf(basis.row) : NaN;
  for (const x of rows) {
    x.isBasis = Boolean(basis) && x.i === basis.i;
    const c = coefOf(x.row);
    // Equivalents are a reactant's word; a solvent or a workup reagent is
    // in the flask but has none.
    x.eq = x.counted && Number.isFinite(x.moles) && Number.isFinite(c) && basisMol > 0
      && Number.isFinite(basisCoef) ? (x.moles / c) / (basisMol / basisCoef) : NaN;
  }
  let limiting = null;
  for (const x of rows) {
    if (!x.counted || !Number.isFinite(x.moles) || !Number.isFinite(coefOf(x.row))) continue;
    x.ratio = x.moles / coefOf(x.row);
    if (!limiting || x.ratio < limiting.ratio) limiting = x;
  }
  if (limiting) limiting.isLimiting = true;
  const product = d.sides[d.product];
  let productMoles = NaN;
  let productGrams = NaN;
  if (limiting && product && product.side === 'product' && Number.isFinite(mwOf(product)) && Number.isFinite(coefOf(product))) {
    const scale = limiting.moles / coefOf(limiting.row);
    productMoles = scale * coefOf(product);
    productGrams = round4(scale * coefOf(product) * mwOf(product));
  }
  const actual = toNumber(d.actual);
  let percent = NaN;
  let warning = '';
  if (Number.isFinite(actual) && Number.isFinite(productGrams) && productGrams > 0) {
    percent = round1((actual / productGrams) * 100);
    warning = percent > 100
      ? 'over the theoretical value — check the product is dry, side products, and the weighing'
      : percent < 5 ? 'very low — check the limiting reagent was really the one weighed, and losses in workup' : '';
  }
  return {
    rows, basis, limiting, limiting_moles: limiting ? limiting.moles : NaN,
    product_index: d.product, product_moles: productMoles, product_grams: productGrams,
    percent, warning,
    notWeighed: rows.filter((x) => x.counted && !Number.isFinite(x.grams)).map((x) => x.row.name || x.row.cas || 'a reactant'),
  };
}

// A number for an input box: no thousands separators or decimal commas,
// which the box would read back wrongly.
function plain(n, sig = 4) {
  return Number.isFinite(n) ? String(Number(n.toPrecision(sig))) : '';
}

// The equation as one line, for the block's head: "2 A + B → C". Empty
// placeholder rows (no name, no CAS number) stay out of it, so a fresh
// block reads "… → …" rather than "… + … → …".
export function equationText(data) {
  const d = normalize(data);
  const side = (which) => d.sides.filter((r) => r.side === which && (r.name || r.cas))
    .map((r) => `${coefOf(r) === 1 ? '' : `${plain(coefOf(r), 6)} `}${r.name || r.cas}`).join(' + ');
  return `${side('reactant') || '…'} → ${side('product') || '…'}`;
}

// ---------------------------------------------------------------- the block

let uid = 0;

export function mountReaction(host, ctx) {
  let data = normalize(ctx.data);
  const editable = ctx.editable;
  const group = `nb-rxn-product-${++uid}`;
  const commit = debounce(() => ctx.commit(JSON.parse(JSON.stringify(data))), 350);
  const root = document.createElement('div');
  root.className = 'nb-recipe nb-reaction';
  host.appendChild(root);

  // What the server made of the equation: substances it completed by CAS
  // number, and whether it balances. Kept so the status line survives a
  // re-render.
  let check = null;   // { state: 'idle'|'working'|'ok'|'bad'|'unknown', problems: [] }

  function about(row) {
    const bits = [row.cas && `CAS ${row.cas}`, row.formula && escapeHtml(row.formula),
      Number.isFinite(mwOf(row)) && `${fmt(mwOf(row))} g/mol`].filter(Boolean);
    return bits.length ? `<small class="nb-muted">${bits.join(' · ')}</small>` : '';
  }

  function renderResults() {
    const got = compute(data);
    root.querySelectorAll('tr[data-i]').forEach((tr) => {
      const x = got.rows[Number(tr.dataset.i)];
      if (!x) return;
      const mol = tr.querySelector('.nb-rxn-mol');
      if (mol) {
        const needsMw = !Number.isFinite(mwOf(x.row)) && Number.isFinite(x.grams);
        mol.innerHTML = needsMw ? '<span class="nb-warn">needs a molecular weight</span>'
          : Number.isFinite(x.moles) ? `<b>${showMol(x.moles)}</b>` : '';
      }
      const eq = tr.querySelector('.nb-rxn-eq');
      if (eq) {
        eq.innerHTML = x.isBasis ? '<span class="nb-form-one">1 <small>basis</small></span>'
          : Number.isFinite(x.eq) ? plain(x.eq, 3) : '';
      }
      tr.classList.toggle('is-limiting', Boolean(x.isLimiting));
      tr.classList.toggle('is-product', x.side === 'product');
    });
    const foot = root.querySelector('.nb-rxn-total');
    if (foot) {
      const parts = [];
      if (got.limiting) {
        parts.push(`Limiting <b>${escapeHtml(got.limiting.row.name || got.limiting.row.cas || '?')}</b>`
          + ` <span class="nb-muted">${showMol(got.limiting_moles)}</span>`);
      } else if (got.notWeighed.length) {
        parts.push(`<span class="nb-warn">Weigh ${escapeHtml(got.notWeighed.join(', '))} to work out the limiting reagent.</span>`);
      }
      if (Number.isFinite(got.product_grams)) {
        parts.push(`Theoretical <b>${showMass(got.product_grams)}</b>`
          + ` <span class="nb-muted">${showMol(got.product_moles)}</span>`);
      }
      foot.innerHTML = parts.join(' · ');
    }
    const yieldLine = root.querySelector('.nb-rxn-yield-line');
    if (yieldLine) {
      yieldLine.innerHTML = Number.isFinite(got.percent)
        ? `Yield <b>${plain(got.percent, 3)} %</b>${got.warning ? ` <span class="nb-warn">${escapeHtml(got.warning)}</span>` : ''}`
        : (Number.isFinite(got.product_grams) ? '' : '<span class="nb-muted">Weigh the reactants and pick a product for the yield.</span>');
    }
    const recordBtn = root.querySelector('[data-act="record"]');
    if (recordBtn) recordBtn.disabled = !editable || !Number.isFinite(toNumber(data.actual));
  }

  function renderCheck() {
    const line = root.querySelector('.nb-rxn-check');
    if (!line) return;
    if (!check) { line.innerHTML = ''; return; }
    if (check.state === 'working') line.innerHTML = '<span class="nb-muted">Checking with the lab’s records…</span>';
    else if (check.state === 'ok') line.innerHTML = '<span class="nb-rxn-ok">✓ the equation balances</span>';
    else if (check.state === 'bad') {
      line.innerHTML = `<span class="nb-warn">✗ the equation does not balance — ${check.problems.map(escapeHtml).join('; ')}</span>`;
    } else if (check.state === 'unknown') {
      line.innerHTML = `<span class="nb-warn">Cannot check: no formula known for ${check.problems.map(escapeHtml).join(', ')}</span>`;
    }
  }

  function render() {
    const dis = editable ? '' : ' disabled';
    const arrow = '<tr class="nb-rxn-arrow"><td colspan="7"><span>→</span></td></tr>';
    const rowHtml = (i) => {
      const r = data.sides[i];
      if (r.side === 'product') {
        return `<tr data-i="${i}">
            <td class="nb-rxn-tick"><label class="nb-form-basis" title="The product the yield counts"><input type="radio" name="${group}" data-product="${i}"${i === data.product ? ' checked' : ''}${dis}></label></td>
            <td class="nb-form-name"><input data-c="name" value="${escapeHtml(r.name || '')}" placeholder="${editable ? 'Product, or its CAS number' : ''}" autocomplete="off"${dis}>${about(r)}</td>
            <td><input data-c="coef" inputmode="decimal" value="${escapeHtml(r.coef ?? '1')}"${dis}></td>
            <td><input data-c="mw" inputmode="decimal" value="${escapeHtml(r.mw ?? '')}" placeholder="needed"${dis}></td>
            <td class="nb-recipe-amount nb-rxn-mol"></td>
            <td class="nb-rxn-eq"></td>
            ${editable ? `<td><button type="button" class="nb-icon-btn" data-remove="${i}" title="Remove" aria-label="Remove">×</button></td>` : ''}
          </tr>`;
      }
      return `<tr data-i="${i}">
          <td class="nb-rxn-tick">${COUNTED_ROLES.includes(r.role || 'reactant') ? '' : '<span class="nb-muted" title="Not counted in the yield">·</span>'}</td>
          <td class="nb-form-name"><input data-c="name" value="${escapeHtml(r.name || '')}" placeholder="${editable ? 'Reactant, or its CAS number' : ''}" autocomplete="off"${dis}>${about(r)}</td>
          <td><input data-c="coef" inputmode="decimal" value="${escapeHtml(r.coef ?? '1')}"${dis}></td>
          <td><input data-c="mw" inputmode="decimal" value="${escapeHtml(r.mw ?? '')}" placeholder="needed"${dis}></td>
          <td class="nb-recipe-conc"><input data-c="weighed" inputmode="decimal" value="${escapeHtml(r.weighed ?? '')}" placeholder="weighed"${dis}><select data-c="unit"${dis}>${unitOptions(WEIGH_UNITS, r.unit || 'g')}</select></td>
          <td class="nb-recipe-amount nb-rxn-mol"></td>
          <td class="nb-rxn-eq"></td>
          ${editable ? `<td><button type="button" class="nb-icon-btn" data-remove="${i}" title="Remove" aria-label="Remove">×</button></td>` : ''}
        </tr>`;
    };
    const sides = normalize(data).sides;
    const firstProduct = sides.findIndex((r) => r.side === 'product');
    const head = `<thead><tr><th class="nb-recipe-tick" title="The product the yield counts">◎</th><th>Substance</th><th title="Coefficient in the equation">Coef.</th><th>MW (g/mol)</th><th>Weighed</th><th>Amount</th><th title="Moles against the first reactant, which is 1">Equiv.</th>${editable ? '<th></th>' : ''}</tr></thead>`;
    const body = sides.map((r, i) => (i === firstProduct ? arrow : '') + rowHtml(i)).join('');
    root.innerHTML = `
      <div class="nb-recipe-head">
        <input class="nb-recipe-name" data-f="name" placeholder="Reaction name, e.g. Aspirin synthesis" value="${escapeHtml(data.name)}"${dis}>
      </div>
      <div class="nb-sheet-scroll"><table class="nb-recipe-table nb-form-table nb-rxn-table">
        <colgroup><col class="c-tick"><col class="c-name"><col class="c-coef"><col class="c-mw"><col class="c-mass"><col class="c-mol"><col class="c-eq">${editable ? '<col class="c-x">' : ''}</colgroup>
        ${head}
        <tbody>${body || '<tr><td colspan="7" class="nb-muted">No substances yet.</td></tr>'}</tbody>
      </table></div>
      <div class="nb-rxn-total nb-recipe-water"></div>
      <div class="nb-rxn-yield">
        <label class="nb-rxn-yield-label">Obtained
          <input data-f="actual" inputmode="decimal" value="${escapeHtml(data.actual ?? '')}" placeholder="grams"${dis}>
          <span class="nb-rxn-unit">g</span>
        </label>
        <span class="nb-rxn-yield-line"></span>
        ${editable ? '<button type="button" class="nb-mini" data-act="record">Record the yield</button>' : ''}
      </div>
      <div class="nb-rxn-check"></div>
      <div class="nb-recipe-actions">
        ${editable ? '<button type="button" class="nb-mini" data-act="add-reactant">+ Reactant</button><button type="button" class="nb-mini" data-act="add-product">+ Product</button>' : ''}
        <button type="button" class="nb-mini" data-act="check"${dis}>Check the equation</button>
      </div>
      ${data.log.length ? `<div class="nb-rxn-log"><table class="nb-stats-table"><thead><tr><th>Date</th><th>Obtained (g)</th><th>Yield</th></tr></thead><tbody>${
        data.log.map((e) => `<tr><td>${escapeHtml(String(e.at || '').slice(0, 10))}</td><td class="is-num">${escapeHtml(plain(Number(e.grams), 6))}</td><td class="is-num">${
          Number.isFinite(Number(e.percent)) ? `${plain(Number(e.percent), 3)} %` : '—'}</td></tr>`).join('')}</tbody></table></div>` : ''}
      <textarea class="nb-recipe-notes" data-f="notes" rows="2" placeholder="Notes: conditions, workup, what the flask looked like"${dis}>${escapeHtml(data.notes || '')}</textarea>`;
    renderResults();
    renderCheck();
  }

  // ---- the server: complete a CAS number, and check the equation
  // What the server knows about a row: by its CAS number, or — a row that
  // carries only a name — by that name.
  function knownFor(res, row) {
    return (res.substances || []).find((s) =>
      (row.cas && s.cas === row.cas) || (!row.cas && s.name && s.name === row.name));
  }

  async function resolve(casList, full) {
    const wanted = [...new Set(casList.map((c) => String(c || '').trim()).filter(Boolean))];
    if (!wanted.length && !full) return null;
    const payload = {
      reactants: data.sides.filter((r) => r.side === 'reactant').map((r) => ({ cas: r.cas, coef: r.coef, name: r.name, formula: r.formula })),
      products: data.sides.filter((r) => r.side === 'product').map((r) => ({ cas: r.cas, coef: r.coef, name: r.name, formula: r.formula })),
      cas_list: wanted, check: Boolean(full),
    };
    try {
      const res = await api('/notebook/api/reaction', { method: 'POST', body: payload });
      if (full && res.balance) {
        check = res.balance.checked
          ? (res.balance.problems.length ? { state: 'bad', problems: res.balance.problems } : { state: 'ok', problems: [] })
          : { state: 'unknown', problems: res.balance.missing || [] };
        renderCheck();
      }
      return res;
    } catch (e) {
      if (full) {
        check = { state: 'unknown', problems: [e.message || 'the server could not be reached'] };
        renderCheck();
      }
      return null;
    }
  }

  // A CAS number typed where a name goes: the server knows the substance.
  const resolveTyped = debounce(async (row, cas) => {
    const res = await resolve([cas], false);
    const found = res && res.substances && res.substances.find((s) => s.cas === cas);
    if (!found) return;
    const i = data.sides.indexOf(row);
    if (i < 0) return;
    let changed = false;
    if (found.mw && !mwOf(row)) { row.mw = String(found.mw); changed = true; }
    if (found.formula && !row.formula) { row.formula = found.formula; changed = true; }
    if (found.name && !row.name) { row.name = found.name; changed = true; }
    if (found.cas_valid === false) row.cas_bad = true;
    if (changed) {
      const tr = root.querySelector(`tr[data-i="${i}"]`);
      if (tr) {
        tr.querySelector('input[data-c="mw"]').value = row.mw;
        const small = tr.querySelector('.nb-form-name small');
        if (small) small.remove();
        tr.querySelector('.nb-form-name').insertAdjacentHTML('beforeend', about(row));
      }
      commit(); renderResults();
    }
  }, 250);

  // ---- picking a substance from the lab's Chemicals database
  let menu = null;
  let found = [];
  let active = -1;
  let forRow = -1;

  function onScroll(event) {
    if (!(menu && event.target instanceof Node && menu.contains(event.target))) closeMenu();
  }

  function closeMenu() {
    window.removeEventListener('scroll', onScroll, { capture: true });
    menu?.remove();
    menu = null;
    found = [];
    active = -1;
  }

  function showMenu(input, res) {
    closeMenu();
    found = res.items || [];
    forRow = Number(input.closest('tr').dataset.i);
    if (!found.length && res.has_database) return;
    menu = document.createElement('div');
    menu.className = 'nb-chem-menu';
    menu.setAttribute('role', 'listbox');
    menu.innerHTML = found.map((c, k) => `<button type="button" role="option" data-pick="${k}">
        <b>${escapeHtml(c.name)}</b>${c.abbr ? ` <span>${escapeHtml(c.abbr)}</span>` : ''}
        <small>${[c.mw ? `${fmt(c.mw)} g/mol` : 'no MW', c.cas && `CAS ${escapeHtml(c.cas)}`, c.formula && escapeHtml(c.formula),
          c.builtin ? 'built in' : `${escapeHtml(c.database)} ${escapeHtml(c.ref.replace(/^@\w+\s+/, '#'))}`,
          c.available ? '' : escapeHtml(c.status)].filter(Boolean).join(' · ')}</small></button>`).join('')
      + (res.has_database ? '' : '<p class="nb-muted">Keep your chemicals in a <a href="/inventory/new?preset=chemicals" target="_blank" rel="noopener">Chemicals database</a> to pick them here with their molecular weight, CAS number and lot.</p>');
    const box = input.getBoundingClientRect();
    Object.assign(menu.style, { left: `${box.left}px`, top: `${box.bottom + 2}px`, width: `${Math.max(box.width, 320)}px` });
    root.appendChild(menu);
    window.addEventListener('scroll', onScroll, { capture: true });
  }

  function highlight(k) {
    active = k;
    menu?.querySelectorAll('[data-pick]').forEach((b) => b.classList.toggle('is-active', Number(b.dataset.pick) === k));
  }

  function pick(k) {
    const chem = found[k];
    const row = data.sides[forRow];
    closeMenu();
    if (!chem || !row) return;
    Object.assign(row, {
      name: chem.name, cas: chem.cas || '', mw: chem.mw ? String(chem.mw) : row.mw,
      formula: chem.formula || row.formula,
    });
    delete row.cas_bad;
    commit(); render();
    root.querySelector(`tr[data-i="${forRow}"] input[data-c="${row.side === 'product' ? 'coef' : 'weighed'}"]`)?.focus();
  }

  const CAS_SHAPE = /^\d{2,7}-\d{2}-\d$/;

  const search = debounce(async (input) => {
    const q = input.value.trim();
    const row = data.sides[Number(input.closest('tr').dataset.i)];
    if (CAS_SHAPE.test(q)) {
      // A CAS number typed outright: the server completes the substance.
      closeMenu();
      if (row && row.cas !== q) { row.cas = q; commit(); }
      if (row) resolveTyped(row, q);
      return;
    }
    if (!q) { closeMenu(); return; }
    try {
      const res = await api(`/notebook/api/chemicals?q=${encodeURIComponent(q)}`);
      if (document.activeElement === input && input.value.trim() === q) showMenu(input, res);
    } catch (_e) { closeMenu(); }
  }, 200);

  root.addEventListener('input', (event) => {
    const t = event.target;
    if (t.dataset.f) {
      data[t.dataset.f] = t.value;
    } else if (t.dataset.c && t.type !== 'checkbox' && t.type !== 'radio') {
      const i = Number(t.closest('tr').dataset.i);
      const row = data.sides[i];
      if (!row) return;
      row[t.dataset.c] = t.value;
      if (t.dataset.c === 'name') {
        delete row.cas_bad;
        search(t);
      }
    } else return;
    commit();
    renderResults();
  });
  root.addEventListener('change', (event) => {
    const t = event.target;
    if (t.dataset.c === 'unit') {
      const row = data.sides[Number(t.closest('tr').dataset.i)];
      if (!row) return;
      const before = toNumber(row.weighed);
      const from = WEIGH_UNITS[row.unit] ?? 1;
      row.unit = t.value;
      if (Number.isFinite(before)) row.weighed = plain(before * from / WEIGH_UNITS[row.unit], 6);
      commit(); render();
    }
  });
  root.addEventListener('keydown', (event) => {
    if (!menu || event.target.dataset.c !== 'name') return;
    const count = found.length;
    if (event.key === 'ArrowDown' && count) { event.preventDefault(); highlight((active + 1) % count); }
    else if (event.key === 'ArrowUp' && count) { event.preventDefault(); highlight((active - 1 + count) % count); }
    else if (event.key === 'Enter' && active >= 0) { event.preventDefault(); pick(active); }
    else if (event.key === 'Escape') { event.preventDefault(); closeMenu(); }
  });
  root.addEventListener('focusout', (event) => {
    if (menu && !(event.relatedTarget && menu.contains(event.relatedTarget))) setTimeout(closeMenu, 150);
  });
  root.addEventListener('mousedown', (event) => {
    if (event.target.closest('[data-pick]')) event.preventDefault();
  });
  root.addEventListener('click', (event) => {
    const t = event.target.closest('button');
    if (!t) return;
    if (t.dataset.pick !== undefined) {
      pick(Number(t.dataset.pick));
    } else if (t.dataset.remove !== undefined) {
      const i = Number(t.dataset.remove);
      data.sides.splice(i, 1);
      if (data.product === i) data.product = -1;
      else if (data.product > i) data.product -= 1;
      data = normalize(data);
      commit(); render();
    } else if (t.dataset.act === 'add-reactant' || t.dataset.act === 'add-product') {
      const side = t.dataset.act === 'add-product' ? 'product' : 'reactant';
      const at = side === 'product' ? data.sides.length : data.sides.findIndex((r) => r.side === 'product');
      data.sides.splice(at < 0 ? data.sides.length : at, 0, emptyRow(side));
      data = normalize(data);
      commit(); render();
      root.querySelector(`tr[data-i="${at < 0 ? data.sides.length - 1 : at}"] input[data-c="name"]`)?.focus();
    } else if (t.dataset.act === 'check') {
      check = { state: 'working', problems: [] };
      renderCheck();
      resolve([], true).then((res) => {
        if (!res) return;
        // What the server knew fills what the rows lack.
        let changed = false;
        for (const row of data.sides) {
          const s = knownFor(res, row);
          if (!s) continue;
          if (s.cas && !row.cas) { row.cas = s.cas; changed = true; }
          if (s.mw && !mwOf(row)) { row.mw = String(s.mw); changed = true; }
          if (s.formula && !row.formula) { row.formula = s.formula; changed = true; }
          if (s.name && !row.name) { row.name = s.name; changed = true; }
        }
        if (changed) { commit(); render(); }
      });
    } else if (t.dataset.act === 'record') {
      const got = compute(data);
      const grams = toNumber(data.actual);
      if (!Number.isFinite(grams)) return;
      data.log = [...data.log, { at: new Date().toISOString(), grams: round1(grams),
                                 percent: Number.isFinite(got.percent) ? got.percent : null }];
      commit(); render();
    }
  });

  render();
  return {
    update(next) { closeMenu(); data = normalize(next); render(); },
    destroy() { closeMenu(); commit.flush(); },
  };
}
