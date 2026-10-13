// A mouse colony experiment in a notebook page: its manipulations day by
// day (what, dose, route, which group, the reagent and lot used, when it
// was done and by whom, the amount each mouse got) and its body weights,
// as a table and a chart with the manipulation days marked.
//
// The block holds only which experiment and what to show, and reads the
// rest live from /colony/experiments/<id>/notebook.json
// (app/experiment_steps.py). "Freeze a copy" stores what it shows at that
// moment in the block itself, so the page keeps a record that later edits
// to the experiment don't change; "Show live" goes back.
//
//   ```experiment
//   {"id": 12, "show": ["plan", "weights"], "percent": false, "measure": "measure:2"}
//   ```
//
// "weights" is the readout: the experiment's main one, or with "measure"
// another measure of the same animals (an ELISA a plate filled; readings
// keyed "measure:<id>", app/experiments.py measures_of). No "measure" is
// the main readout.
//
// Every word goes through tr(), the page's t() (app/translations/zh/js-*.json);
// the readout's built-in names, the kinds and the statuses arrive in English,
// as the experiment page gets them, and are translated where they show.
// tests/js/experiment.check.mjs checks each literal has its Chinese.

import { api, clock, el, escapeHtml as esc, isoDate, tr } from '../util.js';

export function defaultExperiment() {
  return { id: null, show: ['plan', 'weights'], percent: false };
}

// The reagent a recorded day used, as its record keeps it (app/experiment_steps.py
// reagent_used): its name, its lot, and whether that lot had expired by the
// day it was used. Null for a day that kept none.
export function reagentUsed(rec) {
  const r = rec && rec.reagent;
  if (!r || !r.name) return null;
  return { name: r.name, lot: r.lot || '', expired: Boolean(r.expires && rec.done_on && r.expires < rec.done_on) };
}

// …in the experiment page's words (static/experiment-page.js usedText):
// "Tamoxifen lot L7 (expired)".
export function reagentText(rec, t = tr) {
  const used = reagentUsed(rec);
  if (!used) return '';
  return `${used.name}${used.lot ? ` ${t('lot %(lot)s', { lot: used.lot })}` : ''}${used.expired ? ` ${t('(expired)')}` : ''}`;
}

function reagentHtml(rec) {
  const used = reagentUsed(rec);
  if (!used) return '';
  return `<div class="nb-exp-lot">${esc(used.name)}${used.lot ? ` ${esc(tr('lot %(lot)s', { lot: used.lot }))}` : ''}${
    used.expired ? ` <span class="nb-exp-expired">${esc(tr('(expired)'))}</span>` : ''}</div>`;
}


// A label that arrives as a value (a status, a column the page names in
// context): the "context::English" entry first, as the experiment page's tc().
export function tc(ctx, text, t = tr) {
  const key = `${ctx}::${text}`;
  const out = t(key);
  return out === key ? t(text) : out;
}

// The readouts the block can show: the main one first, then each other
// measure, each with its table (the same shape as the main readout's).
// A frozen copy from before 1.13 has no measures, and one from the first
// version no readout: body weight.
const BODY_WEIGHT = { key: 'body_weight', label: 'Body weight', unit: 'g', kind: 'value' };
export function readouts(exp) {
  const main = { key: 'main', readout: exp.readout || BODY_WEIGHT, table: exp.weights };
  return [main, ...(exp.measures || []).filter((m) => m && m.table).map((m) => ({ key: m.key, readout: m, table: m.table }))];
}

// The one shown: the block's measure while the experiment still has it, else the main readout.
export function chosenReadout(exp, key) {
  const all = readouts(exp);
  return all.find((r) => key && r.key === key) || all[0];
}

function openInAppTab(url) {
  if (window.BiomanagerTabs && window.BiomanagerTabs.open) window.BiomanagerTabs.open(url);
  else window.location.href = url;
}

// Dates as the experiment page writes them (10月3日 in Chinese, 3 Oct in English).
function niceDate(iso) {
  if (!iso) return '';
  const locale = typeof window !== 'undefined' && window.BM_LANG === 'zh' ? 'zh-CN' : undefined;
  return new Date(`${iso}T12:00:00`).toLocaleDateString(locale, { day: 'numeric', month: 'short' });
}

const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
// A value as the experiment page's sheet writes it: up to `digits` decimals, no trailing zeros.
export const num = (v, digits = 2) => Number(v).toFixed(digits).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');

const COLORS = ['var(--viz-1)', 'var(--viz-2)', 'var(--viz-3)', 'var(--viz-4)', 'var(--viz-5)', 'var(--viz-7)'];

export function mountExperiment(host, ctx) {
  let data = { ...defaultExperiment(), ...(ctx.data || {}) };
  let editable = ctx.editable;
  let live = null;          // the experiment as read from the app
  let error = '';
  let looking = null;       // a reader's own choice of measure, not saved (they can't change the page)
  const root = el('div', { class: 'nb-exp' });
  host.appendChild(root);

  const commit = (next) => { data = next; ctx.commit(JSON.parse(JSON.stringify(next))); render(); };
  const STATE = { today: tr('Today'), overdue: tr('Overdue'), upcoming: tr('To come'), planned: tr('Planned') };
  const nounsOf = (exp) => tr(exp.nouns || 'mice');
  const nounOf = (exp) => tr(exp.noun || 'mouse');
  // A day's title in the page's language: what was given, or its kind, or the readout's name.
  const titleOf = (exp, r) => {
    const step = (exp.steps || []).find((x) => x.id === r.step_id);
    if (!step) return r.title;
    if (step.reading) return tr((exp.readout || BODY_WEIGHT).label);
    return [step.agent || tr(step.kind_label), step.dose, step.route].filter(Boolean).join(' ');
  };

  async function load() {
    if (!data.id || data.frozen) { render(); return; }
    error = '';
    try {
      live = (await api(`/colony/experiments/${data.id}/notebook.json`)).experiment;
    } catch (e) {
      live = null;
      error = e.status === 404 ? tr('That experiment is no longer there.') : tr('It could not be read (%(error)s).', { error: e.message });
    }
    render();
  }

  async function renderPicker() {
    root.innerHTML = `<p class="nb-muted">${esc(tr('Loading the experiments…'))}</p>`;
    let items = [];
    try {
      items = (await api('/colony/experiments/notebook-list.json')).experiments;
    } catch (e) {
      root.innerHTML = `<p class="nb-warn">${esc(tr('The experiments could not be listed (%(error)s).', { error: e.message }))}</p>`;
      return;
    }
    if (!items.length) {
      root.innerHTML = `<p class="nb-muted">${tr('No experiments yet: make one on a database’s <b>Experiments</b> tab.')}</p>`;
      return;
    }
    root.innerHTML = '';
    root.appendChild(el('p', { class: 'nb-exp-lede', text: tr('Which experiment? Its manipulations and readout show here, kept up to date.') }));
    const list = el('div', { class: 'nb-exp-pick' });
    items.forEach((e) => {
      const b = el('button', { type: 'button', class: 'nb-exp-pick-item' });
      const meta = [tr(e.db_label || 'Mouse colony'), tc('experiment', e.status), tr('%(count)s %(nouns)s', { count: e.mice, nouns: tr(e.nouns || 'mice') })]
        .concat(e.start_date ? [tr('from %(date)s', { date: niceDate(e.start_date) })] : [], e.mine ? [] : [e.owner]);
      b.innerHTML = `<b>${esc(e.name)}</b><span class="nb-muted">${esc(meta.join(' · '))}</span>`;
      b.addEventListener('click', () => { commit({ ...data, id: e.id }); load(); });
      list.appendChild(b);
    });
    root.appendChild(list);
  }

  function toolbar(exp) {
    const bar = el('div', { class: 'nb-exp-bar' });
    const title = el('a', { href: exp.url, class: 'nb-exp-title', text: exp.name });
    title.addEventListener('click', (ev) => { ev.preventDefault(); openInAppTab(exp.url); });
    bar.appendChild(title);
    const meta = [tr(exp.db_label || 'Mouse colony'), tc('experiment', exp.status),
      tr('%(count)s %(nouns)s', { count: exp.members.length, nouns: nounsOf(exp) }),
      exp.start_date ? tr('day 1 = %(date)s', { date: niceDate(exp.start_date) }) : tr('no start date')]
      .concat(data.frozen ? [tr('frozen %(at)s', { at: data.frozen.at })] : [tr('as of %(time)s', { time: exp.as_of.slice(11) })]);
    bar.appendChild(el('span', { class: 'nb-muted', text: meta.join(' · ') }));
    bar.appendChild(el('span', { class: 'nb-spacer' }));
    if (editable) {
      const shown = chosenReadout(exp, data.measure).readout;
      [['plan', tr('Manipulations')], ['weights', tr(shown.label)]].forEach(([key, label]) => {
        const on = data.show.includes(key);
        const b = el('button', { type: 'button', class: `nb-mini${on ? ' is-on' : ''}`, text: label, 'aria-pressed': String(on) });
        b.addEventListener('click', () => {
          const show = on ? data.show.filter((k) => k !== key) : [...data.show, key];
          commit({ ...data, show });
        });
        bar.appendChild(b);
      });
      if (data.frozen) {
        const b = el('button', { type: 'button', class: 'nb-mini', text: tr('Show live'), title: tr('Read the experiment as it is now') });
        b.addEventListener('click', () => { const { frozen, ...rest } = data; commit(rest); load(); });
        bar.appendChild(b);
      } else {
        const r = el('button', { type: 'button', class: 'nb-mini', text: tr('Refresh') });
        r.addEventListener('click', load);
        bar.appendChild(r);
        const f = el('button', { type: 'button', class: 'nb-mini', text: tr('Freeze a copy'),
          title: tr('Keep what this shows now in the page, so later changes to the experiment don’t alter it') });
        f.addEventListener('click', () => {
          if (live) commit({ ...data, frozen: { at: `${isoDate()} ${clock()}`, experiment: live } });
        });
        bar.appendChild(f);
      }
    }
    return bar;
  }

  function planTable(exp) {
    const wrap = el('div', { class: 'nb-exp-section' });
    wrap.appendChild(el('h4', { text: tr('Manipulations') }));
    if (!exp.schedule.length) {
      wrap.appendChild(el('p', { class: 'nb-muted', text: tr('No manipulations planned yet. Add them on the experiment page.') }));
      return wrap;
    }
    const nouns = nounsOf(exp);
    const rows = exp.schedule.map((r) => {
      const rec = r.record;
      const given = rec ? esc(tr('%(count)s of %(total)s %(nouns)s', { count: rec.count, total: r.group_size, nouns })) : '';
      const amounts = rec && rec.mice.some((m) => m.amount || m.volume || m.grams)
        ? `<details><summary>${given}</summary><ul class="nb-exp-amounts">${rec.mice.map((m) =>
          `<li>#${esc(m.mouse_id)}${m.grams != null ? ` · ${Number(m.grams).toFixed(1)} g` : ''}${m.amount ? ` · ${esc(m.amount)}` : ''}${m.volume ? ` · ${esc(m.volume)}` : ''}</li>`).join('')}</ul></details>`
        : given;
      const done = rec ? `<span class="nb-exp-done">✓ ${esc(niceDate(rec.done_on))} · ${esc(rec.done_by)}</span>`
        : `<span class="nb-exp-state" data-state="${esc(r.state)}">${esc(STATE[r.state] || '')}</span>`;
      return `<tr><td class="nb-exp-day">${esc(tr('Day %(n)s', { n: r.day }))}${r.date ? `<div class="nb-muted">${esc(niceDate(r.date))}</div>` : ''}</td>
        <td><b>${esc(titleOf(exp, r))}</b>${r.group ? ` <span class="nb-muted">· ${esc(r.group)}</span>` : ''}${reagentHtml(rec)}${rec && rec.note ? `<div class="nb-muted">${esc(rec.note)}</div>` : ''}</td>
        <td>${done}</td><td>${amounts}</td></tr>`;
    }).join('');
    const table = el('div', { class: 'nb-exp-scroll' });
    table.innerHTML = `<table class="nb-exp-table"><thead><tr><th>${esc(tc('experiment', 'Day'))}</th><th>${esc(tr('What'))}</th><th>${esc(tr('Done'))}</th><th>${esc(cap(nouns))}</th></tr></thead><tbody>${rows}</tbody></table>`;
    wrap.appendChild(table);
    return wrap;
  }

  function weightChart(exp, shown) {
    const w = shown.table;
    const readout = shown.readout;
    const pct = data.percent;
    const unit = readout.unit ? tr(readout.unit) : '';
    const xs = w.days.every((d) => d !== null) ? w.days : w.dates.map((_d, i) => i + 1);
    const groups = new Map();
    // An animal left out of the analysis stays in the table, not the chart.
    w.rows.filter((r) => !r.left_out).forEach((r) => {
      const key = r.group || tr('All %(nouns)s', { nouns: nounsOf(exp) });
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(pct ? r.pct : r.values);
    });
    const series = [...groups.entries()].map(([name, list], gi) => ({
      name, color: COLORS[gi % COLORS.length],
      points: xs.map((x, i) => {
        const vals = list.map((v) => v[i]).filter((v) => v !== null && v !== undefined);
        if (!vals.length) return null;
        const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
        const sd = vals.length > 1 ? Math.sqrt(vals.reduce((a, b) => a + (b - mean) ** 2, 0) / (vals.length - 1)) : 0;
        return { x, y: mean, sem: vals.length > 1 ? sd / Math.sqrt(vals.length) : 0, n: vals.length };
      }).filter(Boolean),
    }));
    const all = series.flatMap((s) => s.points.flatMap((p) => [p.y - p.sem, p.y + p.sem]));
    if (!all.length) return null;
    const marks = exp.schedule.filter((r) => !r.reading && r.kind !== 'weigh').map((r) => r.day);
    const xMin = Math.min(...xs, ...(marks.length ? marks : xs));
    const xMax = Math.max(...xs, ...(marks.length ? marks : xs));
    let yMin = Math.min(...all);
    let yMax = Math.max(...all);
    const pad = (yMax - yMin || 1) * 0.12;
    yMin -= pad; yMax += pad;
    const W = 640; const H = 220; const L = 44; const R = 12; const T = 12; const B = 30;
    const sx = (x) => L + ((x - xMin) / ((xMax - xMin) || 1)) * (W - L - R);
    const sy = (y) => T + (1 - (y - yMin) / ((yMax - yMin) || 1)) * (H - T - B);
    const ticks = 4;
    const places = pct ? 0 : (yMax - yMin < 2 ? 2 : 1);     // an OD of 0.45 needs its second decimal
    const label = tr('%(readout)s by group over the days', { readout: tr(readout.label) });
    let svg = `<svg viewBox="0 0 ${W} ${H}" class="nb-exp-chart" role="img" aria-label="${esc(label)}">`;
    for (let i = 0; i <= ticks; i += 1) {
      const y = yMin + ((yMax - yMin) * i) / ticks;
      svg += `<line x1="${L}" x2="${W - R}" y1="${sy(y)}" y2="${sy(y)}" stroke="var(--viz-grid)"/>`;
      svg += `<text x="${L - 6}" y="${sy(y) + 4}" text-anchor="end" class="nb-exp-axis">${y.toFixed(places)}</text>`;
    }
    [...new Set(marks)].forEach((d) => {
      svg += `<line x1="${sx(d)}" x2="${sx(d)}" y1="${T}" y2="${H - B}" stroke="var(--viz-muted)" stroke-dasharray="2 3" opacity="0.6"/>`;
    });
    [...new Set(xs.concat(marks))].sort((a, b) => a - b).forEach((d) => {
      svg += `<text x="${sx(d)}" y="${H - B + 16}" text-anchor="middle" class="nb-exp-axis">${d}</text>`;
    });
    series.forEach((s) => {
      const path = s.points.map((p, i) => `${i ? 'L' : 'M'}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(' ');
      svg += `<path d="${path}" fill="none" stroke="${s.color}" stroke-width="2"/>`;
      s.points.forEach((p) => {
        if (p.sem) svg += `<line x1="${sx(p.x)}" x2="${sx(p.x)}" y1="${sy(p.y - p.sem)}" y2="${sy(p.y + p.sem)}" stroke="${s.color}" stroke-width="1.5"/>`;
        const value = `${num(p.y, places + 1)}${pct ? '%' : (unit ? ` ${unit}` : '')}`;
        svg += `<circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="3.5" fill="${s.color}"><title>${esc(tr('%(group)s, day %(day)s: %(value)s (n=%(n)s)', { group: s.name, day: p.x, value, n: p.n }))}</title></circle>`;
      });
    });
    svg += '</svg>';
    const scale = pct ? (readout.kind === 'fraction' ? tr('% of those at the start') : tr('% of the first')) : unit;
    const notes = [tr('mean ± SEM'), scale, tr('x: day'), marks.length ? tr('dashed: manipulation days') : ''].filter(Boolean);
    const box = el('div', { class: 'nb-exp-chart-box' });
    box.innerHTML = svg + `<div class="nb-exp-legend">${series.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join('')}
      <span class="nb-muted">${esc(notes.join(' · '))}</span></div>`;
    return box;
  }

  // Which readout: the main one or another measure. Whoever can edit the
  // page saves the choice with the block; a reader looks without saving.
  function readoutSwitch(exp, shown) {
    const all = readouts(exp);
    if (all.length < 2) return null;
    const box = el('div', { class: 'nb-exp-switch', role: 'group', 'aria-label': tr('Readout') });
    all.forEach((r) => {
      const on = r.key === shown.key;
      const b = el('button', { type: 'button', class: `nb-mini${on ? ' is-on' : ''}`, text: tr(r.readout.label), 'aria-pressed': String(on),
        title: r.key === 'main' ? tr('The main readout') : tr('Another measure, beside the main readout') });
      b.addEventListener('click', () => {
        if (on) return;
        if (editable) {
          looking = null;
          const { measure, ...rest } = data;
          commit(r.key === 'main' ? rest : { ...rest, measure: r.key });
        } else {
          looking = r.key;
          render();
        }
      });
      box.appendChild(b);
    });
    return box;
  }

  function weightTable(exp) {
    const wrap = el('div', { class: 'nb-exp-section' });
    const head = el('div', { class: 'nb-exp-subhead' });
    const shown = chosenReadout(exp, (!editable && looking) || data.measure);
    const readout = shown.readout;
    const name = tr(readout.label);
    const fraction = readout.kind === 'fraction';
    const toggle = readoutSwitch(exp, shown);
    // With other measures the switch names the one shown; without, the heading does.
    head.appendChild(el('h4', { text: toggle ? tr('Readout') : name }));
    if (toggle) head.appendChild(toggle);
    if (editable || data.percent) {
      const b = el('button', { type: 'button', class: `nb-mini${data.percent ? ' is-on' : ''}`, text: fraction ? tr('% of start') : tr('% of first'), 'aria-pressed': String(Boolean(data.percent)) });
      b.disabled = !editable;
      b.addEventListener('click', () => commit({ ...data, percent: !data.percent }));
      head.appendChild(b);
    }
    wrap.appendChild(head);
    const w = shown.table;
    if (!w || !w.dates.length) {
      wrap.appendChild(el('p', { class: 'nb-muted', text: tr('No %(readout)s yet: record it on the experiment page.', { readout: name.toLowerCase() }) }));
      return wrap;
    }
    const chart = weightChart(exp, shown);
    if (chart) wrap.appendChild(chart);
    const cols = w.dates.map((d, i) => `<th>${w.days[i] !== null ? `${esc(tr('Day %(n)s', { n: w.days[i] }))}<br>` : ''}<span class="nb-muted">${esc(niceDate(d))}</span></th>`).join('');
    const rows = w.rows.map((r) => `<tr><td>${esc(r.label || `#${r.mouse_id}`)} <span class="nb-muted">${esc(r.sex)}</span></td><td>${esc(r.group)}</td>${
      (data.percent ? r.pct : r.values).map((v) => `<td class="nb-exp-num">${v === null ? '' : (data.percent ? `${v.toFixed(0)}%` : (fraction && r.start != null ? `${v.toFixed(0)}/${r.start}` : esc(num(v))))}</td>`).join('')}</tr>`).join('');
    const table = el('div', { class: 'nb-exp-scroll' });
    table.innerHTML = `<table class="nb-exp-table"><thead><tr><th>${esc(cap(nounOf(exp)))}</th><th>${esc(tr('Group'))}</th>${cols}</tr></thead><tbody>${rows}</tbody></table>`;
    wrap.appendChild(table);
    return wrap;
  }

  function render() {
    root.innerHTML = '';
    if (!data.id) {
      if (editable) renderPicker();
      else root.appendChild(el('p', { class: 'nb-muted', text: tr('No experiment chosen.') }));
      return;
    }
    const exp = data.frozen ? data.frozen.experiment : live;
    if (!exp) {
      root.appendChild(el('p', { class: error ? 'nb-warn' : 'nb-muted', text: error || tr('Reading the experiment…') }));
      if (error && editable) {
        const b = el('button', { type: 'button', class: 'nb-mini', text: tr('Choose another') });
        b.addEventListener('click', () => commit({ ...data, id: null }));
        root.appendChild(b);
      }
      return;
    }
    root.appendChild(toolbar(exp));
    if (data.show.includes('plan')) root.appendChild(planTable(exp));
    if (data.show.includes('weights')) root.appendChild(weightTable(exp));
  }

  load();
  return {
    update(value) { const was = data.id; data = { ...defaultExperiment(), ...(value || {}) }; if (data.id !== was && !data.frozen) load(); else render(); },
    setEditable(v) { editable = v; render(); },
    destroy() {},
  };
}
