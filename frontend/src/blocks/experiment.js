// A mouse colony experiment in a notebook page: its manipulations day by
// day (what, dose, route, which group, when it was done and by whom, the
// amount each mouse got) and its body weights, as a table and a chart
// with the manipulation days marked.
//
// The block holds only which experiment and what to show, and reads the
// rest live from /colony/experiments/<id>/notebook.json
// (app/experiment_steps.py). "Freeze a copy" stores what it shows at that
// moment in the block itself, so the page keeps a record that later edits
// to the experiment don't change; "Show live" goes back.
//
//   ```experiment
//   {"id": 12, "show": ["plan", "weights"], "percent": false}
//   ```

import { api, clock, el, escapeHtml as esc, isoDate } from '../util.js';

export function defaultExperiment() {
  return { id: null, show: ['plan', 'weights'], percent: false };
}

function openInAppTab(url) {
  if (window.BiomanagerTabs && window.BiomanagerTabs.open) window.BiomanagerTabs.open(url);
  else window.location.href = url;
}

function niceDate(iso) {
  if (!iso) return '';
  return new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

const COLORS = ['var(--viz-1)', 'var(--viz-2)', 'var(--viz-3)', 'var(--viz-4)', 'var(--viz-5)', 'var(--viz-7)'];

export function mountExperiment(host, ctx) {
  let data = { ...defaultExperiment(), ...(ctx.data || {}) };
  let editable = ctx.editable;
  let live = null;          // the experiment as read from the app
  let error = '';
  const root = el('div', { class: 'nb-exp' });
  host.appendChild(root);

  const commit = (next) => { data = next; ctx.commit(JSON.parse(JSON.stringify(next))); render(); };

  async function load() {
    if (!data.id || data.frozen) { render(); return; }
    error = '';
    try {
      live = (await api(`/colony/experiments/${data.id}/notebook.json`)).experiment;
    } catch (e) {
      live = null;
      error = e.status === 404 ? 'That experiment is no longer in the colony.' : `It could not be read (${e.message}).`;
    }
    render();
  }

  async function renderPicker() {
    root.innerHTML = '<p class="nb-muted">Loading the colony’s experiments…</p>';
    let items = [];
    try {
      items = (await api('/colony/experiments/notebook-list.json')).experiments;
    } catch (e) {
      root.innerHTML = `<p class="nb-warn">The experiments could not be listed (${esc(e.message)}).</p>`;
      return;
    }
    if (!items.length) {
      root.innerHTML = '<p class="nb-muted">No mouse experiments yet: make one under <b>Mouse colony → Experiments</b>.</p>';
      return;
    }
    root.innerHTML = '';
    root.appendChild(el('p', { class: 'nb-exp-lede', text: 'Which experiment? Its manipulations and body weights show here, kept up to date.' }));
    const list = el('div', { class: 'nb-exp-pick' });
    items.forEach((e) => {
      const b = el('button', { type: 'button', class: 'nb-exp-pick-item' });
      b.innerHTML = `<b>${esc(e.name)}</b><span class="nb-muted">${esc(e.db_label || 'Mouse colony')} · ${esc(e.status)} · ${e.mice} ${esc(e.nouns || 'mice')}${e.start_date ? ` · from ${esc(niceDate(e.start_date))}` : ''}${e.mine ? '' : ` · ${esc(e.owner)}`}</span>`;
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
    const meta = [exp.db_label, exp.status, `${exp.members.length} ${exp.nouns || 'mice'}`, exp.start_date ? `day 1 = ${niceDate(exp.start_date)}` : 'no start date']
      .concat(data.frozen ? [`frozen ${data.frozen.at}`] : [`as of ${exp.as_of.slice(11)}`]);
    bar.appendChild(el('span', { class: 'nb-muted', text: meta.join(' · ') }));
    bar.appendChild(el('span', { class: 'nb-spacer' }));
    if (editable) {
      [['plan', 'Manipulations'], ['weights', (exp.readout && exp.readout.label) || 'Body weight']].forEach(([key, label]) => {
        const on = data.show.includes(key);
        const b = el('button', { type: 'button', class: `nb-mini${on ? ' is-on' : ''}`, text: label, 'aria-pressed': String(on) });
        b.addEventListener('click', () => {
          const show = on ? data.show.filter((k) => k !== key) : [...data.show, key];
          commit({ ...data, show });
        });
        bar.appendChild(b);
      });
      if (data.frozen) {
        const b = el('button', { type: 'button', class: 'nb-mini', text: 'Show live', title: 'Read the experiment as it is now' });
        b.addEventListener('click', () => { const { frozen, ...rest } = data; commit(rest); load(); });
        bar.appendChild(b);
      } else {
        const r = el('button', { type: 'button', class: 'nb-mini', text: 'Refresh' });
        r.addEventListener('click', load);
        bar.appendChild(r);
        const f = el('button', { type: 'button', class: 'nb-mini', text: 'Freeze a copy',
          title: 'Keep what this shows now in the page, so later changes to the experiment don’t alter it' });
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
    wrap.appendChild(el('h4', { text: 'Manipulations' }));
    if (!exp.schedule.length) {
      wrap.appendChild(el('p', { class: 'nb-muted', text: 'No manipulations planned yet. Add them on the experiment page.' }));
      return wrap;
    }
    const rows = exp.schedule.map((r) => {
      const rec = r.record;
      const amounts = rec && rec.mice.some((m) => m.amount || m.volume || m.grams)
        ? `<details><summary>${rec.count} of ${r.group_size} mice</summary><ul class="nb-exp-amounts">${rec.mice.map((m) =>
          `<li>#${esc(m.mouse_id)}${m.grams != null ? ` · ${Number(m.grams).toFixed(1)} g` : ''}${m.amount ? ` · ${esc(m.amount)}` : ''}${m.volume ? ` · ${esc(m.volume)}` : ''}</li>`).join('')}</ul></details>`
        : (rec ? `${rec.count} of ${r.group_size} mice` : '');
      const done = rec ? `<span class="nb-exp-done">✓ ${esc(niceDate(rec.done_on))} · ${esc(rec.done_by)}</span>`
        : `<span class="nb-exp-state" data-state="${esc(r.state)}">${esc({ today: 'today', overdue: 'overdue', upcoming: 'to come', planned: 'planned' }[r.state] || '')}</span>`;
      return `<tr><td class="nb-exp-day">Day ${r.day}${r.date ? `<div class="nb-muted">${esc(niceDate(r.date))}</div>` : ''}</td>
        <td><b>${esc(r.title)}</b>${r.group ? ` <span class="nb-muted">· ${esc(r.group)}</span>` : ''}${rec && rec.note ? `<div class="nb-muted">${esc(rec.note)}</div>` : ''}</td>
        <td>${done}</td><td>${amounts}</td></tr>`;
    }).join('');
    const table = el('div', { class: 'nb-exp-scroll' });
    table.innerHTML = `<table class="nb-exp-table"><thead><tr><th>Day</th><th>What</th><th>Done</th><th>Mice</th></tr></thead><tbody>${rows}</tbody></table>`;
    wrap.appendChild(table);
    return wrap;
  }

  function weightChart(exp) {
    const w = exp.weights;
    const pct = data.percent;
    const xs = w.days.every((d) => d !== null) ? w.days : w.dates.map((_d, i) => i + 1);
    const groups = new Map();
    // An animal left out of the analysis stays in the table, not the chart.
    w.rows.filter((r) => !r.left_out).forEach((r) => {
      const key = r.group || 'All mice';
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
    let svg = `<svg viewBox="0 0 ${W} ${H}" class="nb-exp-chart" role="img" aria-label="The readout by group over the days of the experiment">`;
    for (let i = 0; i <= ticks; i += 1) {
      const y = yMin + ((yMax - yMin) * i) / ticks;
      svg += `<line x1="${L}" x2="${W - R}" y1="${sy(y)}" y2="${sy(y)}" stroke="var(--viz-grid)"/>`;
      svg += `<text x="${L - 6}" y="${sy(y) + 4}" text-anchor="end" class="nb-exp-axis">${y.toFixed(pct ? 0 : 1)}</text>`;
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
        svg += `<circle cx="${sx(p.x)}" cy="${sy(p.y)}" r="3.5" fill="${s.color}"><title>${esc(s.name)}, day ${p.x}: ${p.y.toFixed(1)}${pct ? '%' : ' g'} (n=${p.n})</title></circle>`;
      });
    });
    svg += '</svg>';
    const box = el('div', { class: 'nb-exp-chart-box' });
    box.innerHTML = svg + `<div class="nb-exp-legend">${series.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join('')}
      <span class="nb-muted">mean ± SEM · ${pct ? (exp.readout && exp.readout.kind === 'fraction' ? '% of those at the start' : '% of the first') : ((exp.readout && exp.readout.unit) || 'grams')} · x: day${marks.length ? ' · dashed: manipulation days' : ''}</span></div>`;
    return box;
  }

  function weightTable(exp) {
    const wrap = el('div', { class: 'nb-exp-section' });
    const head = el('div', { class: 'nb-exp-subhead' });
    const readout = exp.readout || { label: 'Body weight', unit: 'g', kind: 'value' };
    const fraction = readout.kind === 'fraction';
    head.appendChild(el('h4', { text: readout.label }));
    if (editable || data.percent) {
      const b = el('button', { type: 'button', class: `nb-mini${data.percent ? ' is-on' : ''}`, text: fraction ? '% of start' : '% of first', 'aria-pressed': String(Boolean(data.percent)) });
      b.disabled = !editable;
      b.addEventListener('click', () => commit({ ...data, percent: !data.percent }));
      head.appendChild(b);
    }
    wrap.appendChild(head);
    const w = exp.weights;
    if (!w.dates.length) {
      wrap.appendChild(el('p', { class: 'nb-muted', text: `No ${readout.label.toLowerCase()} yet: record it on the experiment page.` }));
      return wrap;
    }
    const chart = weightChart(exp);
    if (chart) wrap.appendChild(chart);
    const cols = w.dates.map((d, i) => `<th>${w.days[i] !== null ? `Day ${w.days[i]}<br>` : ''}<span class="nb-muted">${esc(niceDate(d))}</span></th>`).join('');
    const rows = w.rows.map((r) => `<tr><td>${esc(r.label || `#${r.mouse_id}`)} <span class="nb-muted">${esc(r.sex)}</span></td><td>${esc(r.group)}</td>${
      (data.percent ? r.pct : r.values).map((v) => `<td class="nb-exp-num">${v === null ? '' : (data.percent ? `${v.toFixed(0)}%` : (fraction && r.start != null ? `${v.toFixed(0)}/${r.start}` : v.toFixed(1)))}</td>`).join('')}</tr>`).join('');
    const table = el('div', { class: 'nb-exp-scroll' });
    table.innerHTML = `<table class="nb-exp-table"><thead><tr><th>Mouse</th><th>Group</th>${cols}</tr></thead><tbody>${rows}</tbody></table>`;
    wrap.appendChild(table);
    return wrap;
  }

  function render() {
    root.innerHTML = '';
    if (!data.id) {
      if (editable) renderPicker();
      else root.appendChild(el('p', { class: 'nb-muted', text: 'No experiment chosen.' }));
      return;
    }
    const exp = data.frozen ? data.frozen.experiment : live;
    if (!exp) {
      root.appendChild(el('p', { class: error ? 'nb-warn' : 'nb-muted', text: error || 'Reading the experiment…' }));
      if (error && editable) {
        const b = el('button', { type: 'button', class: 'nb-mini', text: 'Choose another' });
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
