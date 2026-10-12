'use strict';
/* BioManager · AI assistants: a 60-second film on a 120 bpm grid (a beat is
   0.5 s, a bar 2 s). Every scene is a pure function of time, so any frame can
   be drawn on its own; scripts/promo-film.py renders it and builds the music
   and the sound effects from FILM.cues. */

const Q = new URLSearchParams(location.search);
const W = +(Q.get('w') || 1920), H = +(Q.get('h') || 1080), LANG = Q.get('lang') || 'en';
const V = H > W, ZH = LANG === 'zh', CX = W / 2, CY = H / 2, DUR = 60;
document.body.classList.toggle('zh', ZH);

// ------------------------------------------------------------------ words
const T = {
  en: {
    hook: 'What if your notes *filed themselves?*',
    hand: 'litter in 102 · 7 pups',
    byo: 'Your assistant • *Any app that speaks MCP*',
    byo2: 'No AI inside. *Bring your own.*',
    yourAssistant: 'YOUR ASSISTANT', yourLab: 'YOUR LAB',
    apps: ['Claude', 'ChatGPT', 'Codex', 'Cursor', 'Cherry Studio', 'Qwen Code', 'Trae', 'Claude'],
    type: 'Type it.', snap: 'Snap it.', say: 'Say it.', drop: '*Drop the file.*',
    typed: 'weaned 110 · weighed #6 #7 · TMX day 3',
    said: 'moved the two females from 112 to 106',
    finds: 'It finds *every record.*',
    chips: ['litter · cage 110', '#6 24.1 g · #7 23.8 g', 'TMX cohort · day 3', 'tamoxifen −0.5 mL', "today's log", 'next dose · Thu'],
    dbs: ['Mouse colony', 'Cages', 'Experiments', 'Inventory', 'Plasmids', 'Notebook', 'Calendar'],
    found: [['Mouse #6, #7', 'cage 103'], ['Cage 110', 'litter 19 d old'], ['TMX cohort', 'day 3 of 5'], ['Tamoxifen', '4.5 mL left'], null, ['Daily log', 'Mon 5 Oct'], ['Dose 4', 'Thu 9:00']],
    propHd: 'From AI assistant, just now · 6 changes · #1',
    propSum: 'Today: weaned the litter in 110, weighed 6 and 7, gave day 3 of tamoxifen, and logged it.',
    rows: ['Cage 110 weaned', 'Mouse #6 weighed 24.1 g', 'Mouse #7 weighed 23.8 g', 'TMX cohort · day 3 done', 'Tamoxifen −0.5 mL', "Line added to today's log"],
    ev: ['photo · line 2', 'photo · line 3', 'photo · line 4', 'you said', 'photo · line 4', 'today'],
    approve: 'Approve', discard: 'Discard', propNote: 'Approving makes every change above at once; Batch history can undo them as one.',
    banner: 'Approved. It is in Batch history, where it can be undone as one.',
    one: 'One proposal. *You approve.*', nothing: 'Nothing changes *until you do.*',
    captures: 'Captures', newCapture: 'New capture', takePhoto: 'Take photo', chooseFile: 'Choose file', scanCard: 'Scan a card', save: 'Save',
    capText: 'Weighed cohort 3 after TMX, all fine', capList: ['Weighed cohort 3 after TMX', 'Litter in 88 · 6 pups', 'plate-reader.csv', 'clone3.ab1'],
    capSub: ['Photo · Cage 104', 'Just now', 'File · 96 wells', 'File · sequencing read'], waiting: 'Waiting', used: 'Used', cage104: 'Cage 104',
    bench: 'Capture at the bench.', later: '*File it later.*', process: 'process my captures',
    prop2: 'Proposal #2 · 5 changes', prop2s: 'Waiting for you on Proposed changes', review: 'Review →',
    q1: "Where's the last tube of pAAV-hSyn-GCaMP8m?", q2: 'Where did mouse #42 come from?', q3: "Who changed cage 88's purpose?",
    box: '−80 °C · Rack B · Box 3', a1: ['pAAV-hSyn-GCaMP8m', '1 tube left · A7'], a2: 'Litter L-17 · born 12 Aug · cage 88',
    hist: [['12 Sep', 'Created'], ['20 Sep', 'Moved to rack B'], ['28 Sep', 'Note added'], ['3 Oct', 'Purpose changed']],
    a3: ['Sam · 3 Oct, 14:20', 'Purpose', 'Breeding', 'Experiment'],
    ask: 'Ask anything.', links: 'Answers come *with links.*', reads: 'It reads only what you can read.',
    words: ['Design', 'Compute', 'Verify', 'Write up'],
    vehicle: 'Vehicle', tmx: 'Tamoxifen', power: 'n = 8 per group · power 0.80',
    ctl: 'Control ΔCt', trt: 'Treated ΔCt', fold: 'fold change', maths: 'BioManager does the maths. *Your assistant does the talking.*',
    mut: 'c.412A>G · p.Lys138Glu', verify: 'Verify sequencing',
    methods: 'Methods', arrive: 'ARRIVE 2.0 · Essential 10',
    arriveItems: ['Study design', 'Sample size', 'Inclusion & exclusion', 'Randomisation', 'Blinding', 'Outcome measures', 'Statistical methods', 'Experimental animals', 'Experimental procedures', 'Results'],
    methodLines: ['Male C57BL/6J mice (8–10 weeks, n = 16)', 'were randomised to vehicle or tamoxifen', '(n = 8 per group; power 0.80, α = 0.05).', 'Tamoxifen (75 mg/kg, i.p.) was given daily', 'for 5 days. Body weight was recorded', 'before each dose. Expression was measured', 'by qPCR and analysed by the ΔΔCt method', 'relative to Gapdh.'],
    tag: ['Say what you did.', 'Approve.', '*Done.*'],
    foot: 'Works with Claude, ChatGPT, Codex, Cursor and more  ·  Free and open source  ·  biomanager.org',
  },
  zh: {
    hook: '如果实验笔记，|*能自己归档？*',
    hand: 'litter in 102 · 7 pups',
    byo: '你的 AI 助手 •|*任何支持 MCP 的应用*',
    byo2: 'BioManager 不内置 AI，|*用你自己的。*',
    yourAssistant: '你的助手', yourLab: '你的实验室',
    apps: ['Claude', 'ChatGPT', 'Cherry Studio', '千问', 'Trae', '豆包', 'Kimi', 'Claude'],
    type: '打一句。', snap: '拍一张。', say: '说一声。', drop: '*拖个文件。*',
    typed: '110 断奶 · #6 #7 称重 · TMX 第 3 天',
    said: '把 112 的两只母鼠移到 106',
    finds: '它会找到*每一条记录。*',
    chips: ['窝 · 笼 110', '#6 24.1 g · #7 23.8 g', 'TMX 组 · 第 3 天', '他莫昔芬 −0.5 mL', '今日日志', '下次给药 · 周四'],
    dbs: ['鼠群', '笼', '实验', '库存', '质粒', '实验记录本', '日历'],
    found: [['小鼠 #6、#7', '笼 103'], ['笼 110', '窝龄 19 天'], ['TMX 组', '第 3 / 5 天'], ['他莫昔芬', '剩 4.5 mL'], null, ['每日日志', '10月5日 周一'], ['第 4 次给药', '周四 9:00']],
    propHd: '来自 AI 助手 · 刚刚 · 6 处修改 · #1',
    propSum: '今天：110 笼断奶，6 号和 7 号称重，他莫昔芬第 3 天给药，并记入日志。',
    rows: ['笼 110 已断奶', '小鼠 #6 体重 24.1 g', '小鼠 #7 体重 23.8 g', 'TMX 组 · 第 3 天完成', '他莫昔芬 −0.5 mL', '今日日志新增一行'],
    ev: ['照片 · 第 2 行', '照片 · 第 3 行', '照片 · 第 4 行', '你说的', '照片 · 第 4 行', '今天'],
    approve: '批准', discard: '丢弃', propNote: '批准后上面的修改一次全部生效；批量操作记录可以一次全部撤销。',
    banner: '已批准。可在批量操作记录中一次撤销。',
    one: '一份提议，*由你批准。*', nothing: '你不点批准，*什么都不会变。*',
    captures: '速记', newCapture: '新速记', takePhoto: '拍照', chooseFile: '选择文件', scanCard: '扫描卡片', save: '保存',
    capText: 'TMX 后给第 3 组称重，一切正常', capList: ['TMX 后第 3 组称重', '88 笼产仔 · 6 只', 'plate-reader.csv', 'clone3.ab1'],
    capSub: ['照片 · 笼 104', '刚刚', '文件 · 96 孔', '文件 · 测序结果'], waiting: '待处理', used: '已用', cage104: '笼 104',
    bench: '在实验台边随手速记，', later: '*回到桌前再归档。*', process: '处理我的速记',
    prop2: '提议 #2 · 5 处修改', prop2s: '在修改提议里等你确认', review: '查看 →',
    q1: 'pAAV-hSyn-GCaMP8m 最后一管在哪？', q2: '小鼠 #42 是从哪来的？', q3: '谁改了 88 笼的用途？',
    box: '−80 °C · B 架 · 3 号盒', a1: ['pAAV-hSyn-GCaMP8m', '剩 1 管 · A7'], a2: '窝 L-17 · 8月12日出生 · 笼 88',
    hist: [['9月12日', '创建'], ['9月20日', '移到 B 架'], ['9月28日', '添加备注'], ['10月3日', '修改用途']],
    a3: ['Sam · 10月3日 14:20', '用途', '繁殖', '实验'],
    ask: '想问什么就问。', links: '答案都*附带记录链接。*', reads: '它只能看到你能看到的。',
    words: ['设计', '计算', '核对', '撰写'],
    vehicle: '溶剂对照', tmx: '他莫昔芬', power: '每组 n = 8 · 检验效能 0.80',
    ctl: '对照 ΔCt', trt: '处理 ΔCt', fold: '倍数变化', maths: '算数交给 BioManager，|*说话交给助手。*',
    mut: 'c.412A>G · p.Lys138Glu', verify: '核对测序结果',
    methods: '方法', arrive: 'ARRIVE 2.0 · 核心 10 项',
    arriveItems: ['研究设计', '样本量', '纳入与排除', '随机分组', '盲法', '结局指标', '统计方法', '实验动物', '实验操作', '结果'],
    methodLines: ['雄性 C57BL/6J 小鼠（8–10 周龄，n = 16）', '随机分为溶剂对照组和他莫昔芬组', '（每组 n = 8；检验效能 0.80，α = 0.05）。', '他莫昔芬（75 mg/kg，腹腔注射）每日给药，', '连续 5 天，每次给药前记录体重。', '基因表达以 qPCR 测定，', '采用 ΔΔCt 法分析，', '以 Gapdh 为内参。'],
    tag: ['说一句，', '点批准，', '*搞定。*'],
    foot: '支持 Claude、ChatGPT、Cherry Studio、豆包等  ·  免费开源 | biomanager.org',
  },
}[LANG];

// ------------------------------------------------------------------ maths
const clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x);
const pr = (t, a, b) => clamp((t - a) / (b - a));
const lerp = (a, b, x) => a + (b - a) * x;
const E = {
  o2: x => 1 - (1 - x) ** 2, o3: x => 1 - (1 - x) ** 3, o4: x => 1 - (1 - x) ** 4, o5: x => 1 - (1 - x) ** 5,
  i2: x => x * x, i3: x => x * x * x, i4: x => x ** 4,
  io2: x => (x < 0.5 ? 2 * x * x : 1 - (-2 * x + 2) ** 2 / 2),
  io3: x => (x < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2),
  io4: x => (x < 0.5 ? 8 * x ** 4 : 1 - (-2 * x + 2) ** 4 / 2),
  oX: x => (x >= 1 ? 1 : 1 - 2 ** (-10 * x)), iX: x => (x <= 0 ? 0 : 2 ** (10 * x - 10)),
  ioX: x => (x <= 0 ? 0 : x >= 1 ? 1 : x < 0.5 ? 2 ** (20 * x - 10) / 2 : (2 - 2 ** (-20 * x + 10)) / 2),
  oB: (x, s = 1.70158) => 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2,
  iB: (x, s = 1.70158) => (s + 1) * x ** 3 - s * x * x,
};
const ease = (t, a, b, f = E.o3) => f(pr(t, a, b));
// A damped spring from 0 to 1, dt seconds after it is let go.
function spring(dt, f = 3, z = 0.42) {
  if (dt <= 0) return 0;
  const w = 2 * Math.PI * f, wd = w * Math.sqrt(1 - z * z);
  return 1 - Math.exp(-z * w * dt) * (Math.cos(wd * dt) + (z * w / wd) * Math.sin(wd * dt));
}
// A decaying wobble (0 at rest), for squash and jiggle.
const wob = (dt, f = 4, d = 6) => (dt < 0 ? 0 : Math.exp(-d * dt) * Math.sin(2 * Math.PI * f * dt));
function rng(seed) { return () => { seed |= 0; seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const bez = (p0, p1, p2, p3, s) => { const u = 1 - s; return [u * u * u * p0[0] + 3 * u * u * s * p1[0] + 3 * u * s * s * p2[0] + s * s * s * p3[0], u * u * u * p0[1] + 3 * u * u * s * p1[1] + 3 * u * s * s * p2[1] + s * s * s * p3[1]]; };
const mix = (a, b, x) => [lerp(a[0], b[0], x), lerp(a[1], b[1], x)];
const hexmix = (a, b, x) => { const p = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)); const A = p(a), B = p(b); return `rgb(${A.map((v, i) => Math.round(lerp(v, B[i], x))).join(',')})`; };

// ------------------------------------------------------------------ DOM
const $ = id => document.getElementById(id);
const stage = $('stage'), world = $('world'), fx = $('fx'), capsLayer = $('caps');
stage.style.width = W + 'px'; stage.style.height = H + 'px';
fx.setAttribute('width', W); fx.setAttribute('height', H); fx.setAttribute('viewBox', `0 0 ${W} ${H}`);
function el(parent, cls = '', html = '', tag = 'div') { const e = document.createElement(tag); if (cls) e.className = cls; if (html) e.innerHTML = html; parent.appendChild(e); return e; }
const icon = (id, cls = 'ic') => `<svg class="${cls}"><use href="#${id}"/></svg>`;
// Place an element by its centre. o: x y s sx sy r rx ry o blur st=[angle, stretch]
function S(e, o) {
  const op = o.o ?? 1;
  if (op <= 0.002) { if (e._vis !== false) { e.style.visibility = 'hidden'; e.style.opacity = '0'; e._vis = false; } return; }
  if (e._vis !== true) { e.style.visibility = 'visible'; e._vis = true; }
  let tr = `translate(${(o.x ?? 0).toFixed(2)}px,${(o.y ?? 0).toFixed(2)}px) translate(-50%,-50%)`;
  if (o.rx || o.ry) tr += ` perspective(1400px) rotateX(${o.rx || 0}deg) rotateY(${o.ry || 0}deg)`;
  if (o.r) tr += ` rotate(${o.r.toFixed(3)}deg)`;
  if (o.st && o.st[1]) tr += ` rotate(${o.st[0]}rad) scale(${1 + o.st[1]},${1 - o.st[1] * 0.5}) rotate(${-o.st[0]}rad)`;
  const s = o.s ?? 1;
  tr += ` scale(${((o.sx ?? 1) * s).toFixed(4)},${((o.sy ?? 1) * s).toFixed(4)})`;
  e.style.transform = tr;
  e.style.opacity = op.toFixed(3);
  const f = o.blur > 0.05 ? `blur(${o.blur.toFixed(2)}px)` : '';
  if (e._f !== f) { e.style.filter = f; e._f = f; }
}
const hide = e => S(e, { o: 0 });
function box(e, w, h, r) { e.style.width = w + 'px'; e.style.height = h + 'px'; if (r !== undefined) e.style.borderRadius = r + 'px'; }

// ------------------------------------------------------------------ cues (sound)
const CUES = [];
const cue = (t, n, g = 1, p = 0, f = 0) => CUES.push({ t: +t.toFixed(4), n, g, p, f });

// ------------------------------------------------------------------ fx layer: strands, particles, rings
const NS = 'http://www.w3.org/2000/svg';
fx.innerHTML = `<defs>
  <filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  <linearGradient id="sg" x1="0" x2="1"><stop offset="0" stop-color="#3FD6BC" stop-opacity="0"/><stop offset="0.35" stop-color="#3FD6BC"/><stop offset="1" stop-color="#d8fff7"/></linearGradient>
</defs><g id="fxg" filter="url(#glow)"></g><g id="fxp"></g>`;
const fxg = $('fxg'), fxp = $('fxp');
const pool = { path: [], circ: [], ring: [] }, used = { path: 0, circ: 0, ring: 0 };
function take(kind) {
  const list = pool[kind];
  if (used[kind] >= list.length) {
    const tag = kind === 'path' ? 'path' : 'circle';
    const e = document.createElementNS(NS, tag);
    (kind === 'path' ? fxg : fxp).appendChild(e);
    list.push(e);
  }
  const e = list[used[kind]++]; e.style.display = ''; return e;
}
function fxReset() { for (const k in used) used[k] = 0; }
function fxFinish() { for (const k in pool) for (let i = used[k]; i < pool[k].length; i++) pool[k][i].style.display = 'none'; }
// The thread: a double helix ribbon along a curve C(s), drawn from s0 to s1.
function strand(C, s0, s1, { amp = 14, period = 120, phase = 0, w = 4, alpha = 1, n = 70, color = '#3FD6BC', rungs = true } = {}) {
  s0 = clamp(s0); s1 = clamp(s1); if (s1 - s0 < 0.004 || alpha <= 0.01) return;
  const pts = [];
  let len = 0, prev = null;
  for (let i = 0; i <= n; i++) { const s = lerp(s0, s1, i / n); const p = C(s); if (prev) len += Math.hypot(p[0] - prev[0], p[1] - prev[1]); pts.push({ p, d: len }); prev = p; }
  const a = [], b = [], r = [];
  for (let i = 0; i <= n; i++) {
    const q = pts[Math.min(n, i + 1)].p, o = pts[Math.max(0, i - 1)].p;
    let nx = -(q[1] - o[1]), ny = q[0] - o[0]; const L = Math.hypot(nx, ny) || 1; nx /= L; ny /= L;
    const taper = Math.sin(Math.PI * Math.min(1, i / n)) ** 0.6;
    const th = pts[i].d / period * 2 * Math.PI + phase, k = amp * taper;
    const [x, y] = pts[i].p;
    a.push([x + nx * Math.sin(th) * k, y + ny * Math.sin(th) * k]);
    b.push([x - nx * Math.sin(th) * k, y - ny * Math.sin(th) * k]);
    if (rungs && i % 4 === 2) r.push(`M${a[i][0].toFixed(1)} ${a[i][1].toFixed(1)}L${b[i][0].toFixed(1)} ${b[i][1].toFixed(1)}`);
  }
  const d = pts2 => 'M' + pts2.map(p => p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('L');
  const p1 = take('path'); p1.setAttribute('d', d(a)); p1.setAttribute('stroke', color); p1.setAttribute('stroke-width', w); p1.setAttribute('fill', 'none'); p1.setAttribute('stroke-linecap', 'round'); p1.setAttribute('opacity', alpha);
  const p2 = take('path'); p2.setAttribute('d', d(b)); p2.setAttribute('stroke', '#c9fff4'); p2.setAttribute('stroke-width', w * 0.7); p2.setAttribute('fill', 'none'); p2.setAttribute('stroke-linecap', 'round'); p2.setAttribute('opacity', alpha * 0.8);
  if (rungs && r.length) { const p3 = take('path'); p3.setAttribute('d', r.join('')); p3.setAttribute('stroke', color); p3.setAttribute('stroke-width', 1.5); p3.setAttribute('fill', 'none'); p3.setAttribute('opacity', alpha * 0.45); }
}
function dotAt(x, y, r, color, alpha = 1) { const c = take('circ'); c.setAttribute('cx', x); c.setAttribute('cy', y); c.setAttribute('r', Math.max(0, r)); c.setAttribute('fill', color); c.setAttribute('stroke', 'none'); c.setAttribute('opacity', alpha); }
function ring(x, y, r, w, color, alpha) { if (alpha <= 0.01) return; const c = take('ring'); if (c.parentNode !== fxp) fxp.appendChild(c); c.setAttribute('cx', x); c.setAttribute('cy', y); c.setAttribute('r', Math.max(0, r)); c.setAttribute('fill', 'none'); c.setAttribute('stroke', color); c.setAttribute('stroke-width', w); c.setAttribute('opacity', alpha); }
// A burst of particles that fly out, fall a little and fade.
function burst(t, t0, x, y, { n = 30, speed = 900, life = 0.9, seed = 1, colors = ['#3FD6BC', '#ffffff', '#9ff5e4'], size = 6, grav = 900 } = {}) {
  const dt = t - t0; if (dt < 0 || dt > life) return;
  const R = rng(seed);
  for (let i = 0; i < n; i++) {
    const a = R() * Math.PI * 2, v = speed * (0.35 + 0.65 * R()), sz = size * (0.5 + R()), c = colors[Math.floor(R() * colors.length)];
    const drag = (1 - Math.exp(-3.2 * dt)) / 3.2;
    const px = x + Math.cos(a) * v * drag, py = y + Math.sin(a) * v * drag + 0.5 * grav * dt * dt * 0.6;
    dotAt(px, py, sz * (1 - dt / life), c, 1 - E.i2(dt / life));
  }
}

// camera inside the world layer (world coords = screen coords at rest)
const cam = { x: 0, y: 0, s: 1, r: 0 };
function applyCam(t) {
  // a small punch on every kick, and a shake on the four big hits
  let punch = 0;
  const kick = (a, b, step) => { if (t >= a && t < b) { const k = Math.floor((t - a) / step) * step + a; punch += 0.007 * Math.exp(-(t - k) * 11); } };
  kick(4, 19.5, 0.5); kick(20, 36, 0.5); kick(36, 42, 2); kick(44, 52, 0.5);
  let sx = 0, sy = 0;
  for (const [ht, a] of [[20, 16], [26, 10], [44, 14], [54, 18]]) {
    const dt = t - ht; if (dt >= 0 && dt < 0.6) { const k = a * Math.exp(-dt * 9); sx += k * Math.sin(dt * 71); sy += k * Math.cos(dt * 53); }
  }
  const s = cam.s * (1 + punch);
  world.style.transform = `translate(${(cam.x + sx).toFixed(2)}px,${(cam.y + sy).toFixed(2)}px) rotate(${cam.r.toFixed(3)}deg) scale(${s.toFixed(4)})`;
  fx.style.transform = world.style.transform; fx.style.transformOrigin = '50% 50%';
  capsLayer.style.transform = `translate(${(sx * 0.5).toFixed(2)}px,${(sy * 0.5).toFixed(2)}px)`;
}

// ------------------------------------------------------------------ captions
// Markup: *words* are mint. Words rise out of a mask with a little overshoot.
class Caption {
  constructor(text, o) {
    this.o = Object.assign({ x: CX, y: CY, size: 64, align: 'center', t0: 0, t1: 9e9, step: 0.07, color: '#EEF7F4', maxW: W * 0.86, weight: null, times: null, slam: false, dimAt: null, dim: 0.32 }, o);
    const e = this.e = el(CUR_CAPS || capsLayer, 'cap');
    e.style.fontSize = this.o.size + 'px'; e.style.color = this.o.color; e.style.maxWidth = this.o.maxW + 'px'; e.style.textAlign = this.o.align;
    if (this.o.weight) e.style.fontWeight = this.o.weight;
    if (this.o.align === 'center') e.style.width = this.o.maxW + 'px';
    this.words = [];
    const parts = text.split(/(\*[^*]+\*)/).filter(Boolean);
    for (const part of parts) {
      const acc = part.startsWith('*'); const s = acc ? part.slice(1, -1) : part;
      const toks = ZH ? s.match(/[A-Za-z0-9#.\-−]+[，。？、！：；）]*|\s+|\|[，。？、！：；）]*|.[，。？、！：；）]*/g) : s.split(/(\s+)/);
      for (const tk of toks) {
        if (!tk) continue;
        if (/^\s+$/.test(tk)) { e.appendChild(document.createTextNode(' ')); continue; }
        if (tk === '|') { if (V) el(e, '', '', 'br'); continue; }
        const w = el(e, 'w', '', 'span'); const wi = el(w, 'wi' + (acc ? ' acc' : ''), '', 'span'); wi.textContent = tk;
        this.words.push(wi);
      }
    }
    if (ZH) { // keep CJK punctuation glued to what came before
      e.querySelectorAll('.w').forEach(w => { w.style.marginRight = '0'; });
    }
  }
  render(t) {
    const o = this.o;
    if (t < o.t0 - 0.05 || t > o.t1 + 0.6) { hide(this.e); return; }
    const anchor = o.align === 'center' ? -50 : 0;
    let s = 1, blur = 0;
    if (o.slam) { const d = t - o.t0; s = 1 + 0.35 * (1 - spring(d, 2.6, 0.5)); blur = 10 * (1 - E.o3(pr(t, o.t0, o.t0 + 0.25))); }
    const dim = o.dimAt !== null ? lerp(1, o.dim, ease(t, o.dimAt, o.dimAt + 0.3)) : 1;
    this.e.style.visibility = 'visible'; this.e._vis = true;
    this.e.style.transform = `translate(${o.x}px,${o.y}px) translate(${anchor}%,-50%) scale(${s.toFixed(4)})`;
    this.e.style.transformOrigin = o.align === 'center' ? '50% 50%' : '0 50%';
    this.e.style.opacity = dim;
    this.e.style.filter = blur > 0.1 ? `blur(${blur.toFixed(2)}px)` : '';
    const n = this.words.length;
    this.words.forEach((w, i) => {
      const ti = o.times ? o.times[Math.min(i, o.times.length - 1)] : o.t0 + i * o.step;
      const din = t - ti;
      const p = clamp(din / 0.5);
      const y = din < 0 ? 110 : 110 * (1 - E.oB(p, 1.6));
      const te = o.t1 + (n - 1 - i) * 0.025, dout = pr(t, te, te + 0.32);
      const yo = -115 * E.iX(dout);
      const op = din < 0 ? 0 : Math.min(1, din / 0.12) * (1 - E.i2(dout));
      const bl = 8 * (1 - E.o3(clamp(din / 0.3))) + 10 * dout;
      w.style.transform = `translateY(${(y + yo).toFixed(2)}%) rotate(${(din < 0 ? 8 : 8 * (1 - E.o4(p))).toFixed(2)}deg)`;
      w.style.opacity = op.toFixed(3);
      w.style.filter = bl > 0.1 ? `blur(${bl.toFixed(2)}px)` : '';
    });
  }
}
const CAPS = [];
const caption = (text, o) => { const c = new Caption(text, o); CAPS.push(c); return c; };

// ------------------------------------------------------------------ background
const b1 = $('b1'), b2 = $('b2'), b3 = $('b3'), grid = $('grid'), flashEl = $('flash');
const BW = Math.max(W, H) * 0.9;
[b1, b2, b3].forEach(b => box(b, BW, BW));
function renderBg(t) {
  // colour moods per section: [t, blob1, blob2, blob3, intensity]
  const moods = [[0, '#2fb8a2', '#3a5bd0', '#0d2a26', 0.35], [4, '#2fb8a2', '#3a5bd0', '#0d2a26', 0.55], [20, '#3FD6BC', '#2e6ae0', '#1b6b5e', 0.8],
    [28, '#2fb8a2', '#5a4fd0', '#0f3b35', 0.6], [36, '#2a7fb8', '#6b4fd0', '#0d2a3a', 0.5], [44, '#3FD6BC', '#ff7a66', '#2e6ae0', 0.75], [52, '#0d3a33', '#0d1f3a', '#04100e', 0.3], [54, '#3FD6BC', '#2e6ae0', '#0B8C7E', 0.7]];
  let i = 0; while (i < moods.length - 1 && t >= moods[i + 1][0]) i++;
  const m0 = moods[i], m1 = moods[Math.min(moods.length - 1, i + 1)];
  const k = m1 === m0 ? 0 : E.io2(pr(t, m1[0] - 0.8, m1[0]));
  const c1 = hexmix(m0[1], m1[1], k), c2 = hexmix(m0[2], m1[2], k), c3 = hexmix(m0[3], m1[3], k), inten = lerp(m0[4], m1[4], k);
  b1.style.background = `radial-gradient(circle, ${c1} 0%, transparent 62%)`;
  b2.style.background = `radial-gradient(circle, ${c2} 0%, transparent 62%)`;
  b3.style.background = `radial-gradient(circle, ${c3} 0%, transparent 62%)`;
  const dr = (a, f, ph) => a * Math.sin(t * f + ph);
  S(b1, { x: W * 0.18 + dr(120, 0.21, 0), y: H * 0.15 + dr(90, 0.17, 1), o: inten });
  S(b2, { x: W * 0.85 + dr(140, 0.19, 2), y: H * 0.88 + dr(100, 0.23, 3), o: inten * 0.8 });
  S(b3, { x: W * 0.5 + dr(200, 0.13, 4), y: H * 0.5 + dr(150, 0.11, 5), s: 0.8, o: inten * 0.6 });
  grid.style.transform = `translate(${(-t * 6 % 38).toFixed(2)}px, ${(-t * 3 % 38).toFixed(2)}px)`;
  grid.style.opacity = lerp(0.6, 1, inten);
}
function flash(t, at, peak = 0.85, decay = 0.35) { const d = t - at; return d < -0.06 || d > decay ? 0 : d < 0 ? peak * (1 + d / 0.06) : peak * (1 - E.o2(d / decay)); }

// ------------------------------------------------------------------ scenes
const SCENES = [];
let CUR_CAPS = null;
function scene(t0, t1, build) { const root = el(world, 'layer'); const caps = el(capsLayer, 'layer'); CUR_CAPS = caps; const s = { t0, t1, root, caps }; s.render = build(root, s); CUR_CAPS = null; SCENES.push(s); return s; }
const at = (h, v) => (V ? v : h);

// ================================================================ 1 · hook (0–4.5)
const A2 = at([CX - 520, CY - 40], [CX, CY - 560]);   // where the thread goes: the assistant node
scene(0, 4.7, root => {
  const pw = at(820, 860), ph = at(330, 350), px = CX, py = CY + at(-30, 60);
  const paper = el(root, 'a paper'); box(paper, pw, ph);
  const rules = [0, 1, 2, 3].map(i => { const r = el(paper, 'rule'); r.style.top = (70 + i * 72) + 'px'; return r; });
  const margin = el(paper, 'margin'); margin.style.left = '64px';
  const hw = el(paper, 'a hand'); hw.style.fontSize = at(72, 78) + 'px';
  const letters = [...T.hand].map(ch => { const s = el(hw, '', '', 'span'); s.textContent = ch; s.style.display = 'inline-block'; s.style.whiteSpace = 'pre'; return s; });
  const caret = el(paper, 'a'); box(caret, 4, 74); caret.style.background = '#1c2a6e'; caret.style.borderRadius = '2px';
  const nib = el(root, 'a dot'); box(nib, 14, 14); nib.style.background = 'radial-gradient(circle,#2a3c9a,#1c2a6e)'; nib.style.boxShadow = '0 0 14px rgba(80,120,255,.8)';
  const cap = caption(T.hook, { x: CX, y: at(CY + 310, CY - 440), size: at(68, 72), t0: 2.0, t1: 3.85, maxW: at(1500, 940), step: ZH ? 0.06 : 0.16 });
  // handwriting, word by word on the beats
  const hx = 100, hy = ph / 2 - 6;
  let lw = []; const words = []; // reveal schedule: [index, t]
  const sched = [];
  let tt = 0.62; letters.forEach((l, i) => { if (T.hand[i] === ' ') tt += 0.06; sched.push(tt); tt += T.hand[i] === ' ' ? 0 : 0.072; });
  letters.forEach((l, i) => { if (i === 0 || T.hand[i - 1] === ' ') cue(sched[i], 'scribble', 0.55, -0.2 + i / letters.length * 0.4); });
  let meas = null;
  return (t) => {
    if (!meas) { meas = letters.map(l => ({ x: l.offsetLeft + l.offsetWidth / 2, w: l.offsetWidth })); }
    cam.s = 1 + 0.07 * E.io2(pr(t, 0, 3.9));
    cam.x = 0; cam.y = 0; cam.r = 0;
    // paper in, then away at the drop
    const pin = spring(t - 0.05, 1.6, 0.6), away = E.iB(pr(t, 3.95, 4.55), 2.2);
    const squash = E.io2(pr(t, 3.3, 3.95));
    S(paper, { x: px, y: py + 40 * (1 - pin) + 520 * away, s: lerp(0.9, 1, pin) * (1 - 0.03 * squash), sy: 1 - 0.02 * squash, r: -2 + 9 * away, o: clamp(t / 0.3) * (1 - E.i2(pr(t, 4.2, 4.6))), blur: 14 * (1 - E.o3(pr(t, 0, 0.5))) + 12 * away });
    rules.forEach((r, i) => { r.style.transform = `scaleX(${E.o4(pr(t, 0.15 + i * 0.07, 0.7 + i * 0.07)).toFixed(4)})`; });
    margin.style.transform = `scaleY(${E.o4(pr(t, 0.1, 0.6)).toFixed(4)})`;
    hw.style.left = hx + 'px'; hw.style.top = (hy - 46) + 'px';
    // caret blinks before the pen starts
    caret.style.left = hx + 'px'; caret.style.top = (hy - 40) + 'px';
    caret.style.opacity = t < 0.62 ? (Math.floor(t / 0.25) % 2 ? 0.15 : 1) : 0;
    // letters: written on, glow mint, then lift off into the thread
    const glow = E.io2(pr(t, 3.2, 3.95));
    let nibX = null;
    letters.forEach((l, i) => {
      const ti = sched[i], d = t - ti;
      const wr = clamp(d / 0.09);
      const lt = 3.98 + i * 0.012, ld = pr(t, lt, lt + 0.5);
      if (t < lt) {
        l.style.transform = `translateY(${(1 - E.o3(wr)) * 6}px) scale(${lerp(0.7, 1, E.oB(wr))})`;
        l.style.opacity = wr; l.style.color = hexmix('#1c2a6e', '#0B8C7E', glow);
        l.style.textShadow = glow > 0.01 ? `0 0 ${18 * glow}px rgba(63,214,188,${0.8 * glow})` : '';
        l.style.filter = '';
        if (wr > 0 && wr < 1) nibX = meas[i].x + meas[i].w / 2;
      } else {
        // fly to the assistant node along an arc
        const k = E.io3(ld);
        const sx0 = px - pw / 2 + hx + meas[i].x, sy0 = py - ph / 2 + hy;
        const p = bez([sx0, sy0], [sx0, sy0 - 240], [A2[0] - 200, A2[1] - 150], A2, k);
        l.style.transform = `translate(${p[0] - sx0}px, ${p[1] - sy0}px) scale(${lerp(1, 0.25, k)}) rotate(${lerp(0, -40 + i * 7, k)}deg)`;
        l.style.opacity = 1 - E.i3(ld); l.style.color = '#3FD6BC'; l.style.filter = `blur(${4 * Math.sin(Math.PI * ld)}px)`;
      }
    });
    if (nibX !== null && t < 3) S(nib, { x: px - pw / 2 + hx + nibX, y: py - ph / 2 + hy + 6 + 4 * Math.sin(t * 40), s: 1, o: 0.9 }); else hide(nib);
    // the thread leaves the page
    if (t > 3.98) {
      const sx0 = px - pw / 2 + hx + 220, sy0 = py - ph / 2 + hy;
      const C = s => bez([sx0, sy0], [sx0, sy0 - 260], [A2[0] - 220, A2[1] - 160], A2, s);
      strand(C, E.io3(pr(t, 4.1, 4.6)), E.oX(pr(t, 3.98, 4.38)), { amp: 12, period: 90, phase: t * 9, alpha: 1 - pr(t, 4.5, 4.7) });
    }
    cap.render(t);
  };
});
cue(0.0, 'tickclock', 0.4);

// ================================================================ 2 · bring your own assistant (4–8.2)
const M2 = at([CX, CY - 40], [CX, CY - 190]), B2 = at([CX + 520, CY - 40], [CX, CY + 165]);
const BOX = at([CX + 230, CY], [CX, CY + 130]);       // the morphing input box of scene 3
scene(3.9, 8.3, root => {
  const an = el(root, 'a glass'); box(an, at(400, 460), at(132, 144), 32);
  an.style.display = 'flex'; an.style.alignItems = 'center'; an.style.gap = '20px'; an.style.padding = '0 24px';
  const av = el(an, ''); box(av, 80, 80, 22); av.style.flex = 'none'; av.style.display = 'grid'; av.style.placeItems = 'center';
  av.style.background = 'linear-gradient(135deg,#7aa7ff,#b79cff)'; av.style.boxShadow = '0 8px 24px rgba(122,167,255,.45)'; av.innerHTML = icon('sparkle'); av.firstChild.style.cssText = 'width:38px;height:38px;color:#fff';
  const col = el(an, ''); col.style.minWidth = '0';
  const lab = el(col, 'mono', T.yourAssistant); lab.style.cssText = 'font-size:15px;letter-spacing:.14em;color:var(--muted);margin-bottom:6px';
  const slot = el(col, ''); slot.style.cssText = 'position:relative;height:54px;overflow:hidden;width:260px';
  const names = T.apps.map(n => { const s = el(slot, 'a', n); s.style.cssText += ';font-size:42px;font-weight:720;letter-spacing:-.02em;white-space:nowrap;left:0;top:0'; return s; });
  const sock = el(root, 'a glass'); box(sock, 230, 112, 56); sock.style.display = 'grid'; sock.style.placeItems = 'center';
  sock.innerHTML = '<span class="mono" style="font-size:40px;font-weight:800;letter-spacing:.12em;color:#e9fffa">MCP</span>';
  const ports = [0, 1].map(() => { const d = el(root, 'a dot'); box(d, 18, 18); d.style.background = '#3FD6BC'; d.style.boxShadow = '0 0 18px #3FD6BC'; return d; });
  const bm = el(root, 'a'); bm.style.textAlign = 'center';
  bm.innerHTML = `<img src="/app/static/icon.svg" style="width:190px;height:190px;display:block;margin:0 auto -6px;filter:drop-shadow(0 18px 40px rgba(63,214,188,.45))">
    <div class="mono" style="font-size:15px;letter-spacing:.14em;color:var(--muted)">${T.yourLab}</div><div style="font-size:32px;font-weight:760;letter-spacing:-.02em">BioManager</div>`;
  const c1 = caption(T.byo, { x: CX, y: at(CY + 300, CY + 465), size: at(60, 58), t0: 5.0, t1: 7.6, maxW: at(1600, 960), step: ZH ? 0.035 : 0.09 });
  const c2 = caption(T.byo2, { x: CX, y: at(CY + 385, CY + 595), size: at(36, 38), t0: 6.3, t1: 7.6, maxW: at(1400, 960), step: ZH ? 0.03 : 0.08, weight: 620 });
  for (let k = 0; k < 7; k++) cue(4.5 + k * 0.5, 'flip', 0.5, at(-0.5, 0));
  cue(4.3, 'pop', 0.8, at(-0.5, 0), 1); cue(4.72, 'pop', 0.7, 0, 1.25); cue(5.12, 'pop', 0.8, at(0.5, 0), 1.5);
  return (t) => {
    cam.s = 1 + 0.03 * E.io2(pr(t, 4, 7.6)); cam.x = 0; cam.y = 0; cam.r = 0;
    const squeeze = E.iB(pr(t, 7.55, 8.0), 2.4);
    const pa = mix(A2, M2, squeeze), pb = mix(B2, M2, squeeze);
    const sA = spring(t - 4.32, 2.6, 0.45), sM = spring(t - 4.72, 2.6, 0.45), sB = spring(t - 5.12, 2.4, 0.42);
    S(an, { x: pa[0], y: pa[1], s: sA * (1 - 0.6 * squeeze), o: clamp((t - 4.32) / 0.08) * (1 - squeeze) });
    S(sock, { x: M2[0], y: M2[1], s: sM * (1 + 0.06 * wob(t - 8 + 0.4, 3, 5)), o: clamp((t - 4.72) / 0.08) * (t < 8 ? 1 : 0) });
    S(bm, { x: pb[0], y: pb[1] + at(18, 30), s: sB * (1 - 0.6 * squeeze), o: clamp((t - 5.12) / 0.08) * (1 - squeeze) });
    // app names roll on the beat
    const idx = clamp(Math.floor((t - 4.5) / 0.5) + 1, 0, names.length - 1);
    names.forEach((n, i) => {
      const since = t - (4.5 + (i - 1) * 0.5);  // when this one arrives
      if (i === idx) { const k = i === 0 ? 1 : E.oB(clamp(since / 0.22), 1.8); n.style.transform = `translateY(${(1 - k) * 56}px)`; n.style.opacity = 1; n.style.filter = k < 1 ? `blur(${(1 - k) * 6}px)` : ''; }
      else if (i === idx - 1) { const k = E.i3(clamp((t - (4.5 + (idx - 1) * 0.5)) / 0.16)); n.style.transform = `translateY(${-k * 56}px)`; n.style.opacity = 1 - k; n.style.filter = `blur(${k * 6}px)`; }
      else { n.style.opacity = 0; }
    });
    // thread: assistant → MCP → BioManager, then pulses on every beat
    const half = at(115, 0);
    const pts1 = at([[pa[0] + 200, pa[1]], [pa[0] + 330, pa[1] - 60], [M2[0] - 250, M2[1] + 60], [M2[0] - half, M2[1]]], [[pa[0], pa[1] + 72], [pa[0] + 60, pa[1] + 150], [M2[0] - 60, M2[1] - 140], [M2[0], M2[1] - 56]]);
    const pts2 = at([[M2[0] + half, M2[1]], [M2[0] + 250, M2[1] - 60], [pb[0] - 330, pb[1] + 60], [pb[0] - 105, pb[1]]], [[M2[0], M2[1] + 56], [M2[0] - 60, M2[1] + 140], [pb[0] + 60, pb[1] - 170], [pb[0], pb[1] - 95]]);
    const C1 = s => bez(...pts1, s), C2 = s => bez(...pts2, s);
    const al = 1 - squeeze;
    if (t > 4.3) strand(C1, 0, E.o3(pr(t, 4.3, 4.72)), { amp: 9, period: 70, phase: -t * 8, alpha: al });
    if (t > 4.72) strand(C2, 0, E.o3(pr(t, 4.72, 5.12)), { amp: 9, period: 70, phase: -t * 8, alpha: al });
    S(ports[0], { x: at(M2[0] - half, M2[0]), y: at(M2[1], M2[1] - 56), s: sM, o: (t > 4.72 ? 1 : 0) * al });
    S(ports[1], { x: at(M2[0] + half, M2[0]), y: at(M2[1], M2[1] + 56), s: sM, o: (t > 4.72 ? 1 : 0) * al });
    for (let b = 5.5; b < 7.6; b += 0.5) {
      const k = pr(t, b, b + 0.5); if (k <= 0 || k >= 1) continue;
      const p = k < 0.5 ? C1(E.io2(k * 2)) : C2(E.io2(k * 2 - 1));
      dotAt(p[0], p[1], 9, '#eafffb', al * Math.sin(Math.PI * k)); dotAt(p[0], p[1], 22, '#3FD6BC', 0.35 * al * Math.sin(Math.PI * k));
    }
    c1.render(t); c2.render(t);
  };
});

// ================================================================ 3 · four ways in (7.95–14.2)
scene(7.95, 14.3, root => {
  const states = at(
    [[940, 112, 56], [660, 490, 30], [580, 150, 75], [840, 430, 34]],
    [[960, 124, 62], [820, 620, 30], [760, 170, 85], [940, 560, 34]]);
  const sw = [7.95, 9.5, 11.0, 12.5];
  const bx = el(root, 'a glass'); bx.style.overflow = 'hidden';
  // A · typing
  const typ = el(bx, 'a mono'); typ.style.cssText += ';left:44px;top:50%;transform:translateY(-50%);font-size:' + at(30, 32) + 'px;white-space:nowrap;color:#e9fffa';
  const send = el(root, 'a'); box(send, 74, 74, 37); send.style.cssText += ';display:grid;place-items:center;background:linear-gradient(180deg,#56e3ca,#0B8C7E);box-shadow:0 8px 24px rgba(63,214,188,.5)';
  send.innerHTML = icon('arrow-up'); send.firstChild.style.cssText = 'width:30px;height:30px;color:#fff';
  // B · photo of the notebook
  const ph = el(bx, 'a paper'); const PL = ['Mon 5 Oct', 'weaned the litter in [110]', 'weighed [#6 24.1 g]', '[#7 23.8 g] (TMX)', 'moved 2 females [112] to [106]'];
  const marks = [];
  const phLines = PL.map((line, i) => {
    const r = el(ph, 'rule'); r.style.top = (54 + i * at(80, 104) + at(48, 64)) + 'px';
    const l = el(ph, 'a hand'); l.style.fontSize = at(36, 46) + 'px'; l.style.left = (i === 3 ? at(130, 160) : 60) + 'px'; l.style.top = (54 + i * at(80, 104)) + 'px';
    l.innerHTML = line.replace(/\[([^\]]+)\]/g, '<span class="mk" style="position:relative;display:inline-block">$1</span>');
    l.querySelectorAll('.mk').forEach(m => { const b = el(m, 'a'); b.style.cssText = 'left:-8px;top:-2px;right:-8px;bottom:-4px;width:auto;height:auto;border:3px solid #0B8C7E;border-radius:10px;transform-origin:50% 50%;box-shadow:0 0 16px rgba(63,214,188,.6)'; marks.push({ b, line: i }); });
    return l;
  });
  const scan = el(bx, 'a'); scan.style.cssText += ';left:0;right:0;width:100%;height:6px;background:linear-gradient(90deg,transparent,#3FD6BC,#eafffb,#3FD6BC,transparent);box-shadow:0 0 30px 8px rgba(63,214,188,.55)';
  const corners = [0, 1, 2, 3].map(i => { const c = el(root, 'a'); box(c, 46, 46); c.style.border = '5px solid #3FD6BC'; c.style.borderRadius = '8px'; c.style.borderWidth = ['5px 0 0 5px', '5px 5px 0 0', '0 5px 5px 0', '0 0 5px 5px'][i]; return c; });
  // C · voice
  const mic = el(bx, 'a'); box(mic, 92, 92, 46); mic.style.cssText += ';display:grid;place-items:center;background:linear-gradient(180deg,#ff9a85,#ff6a55);box-shadow:0 8px 24px rgba(255,122,102,.45)';
  mic.innerHTML = '<svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round"><rect x="9" y="3" width="6" height="11" rx="3" fill="#fff"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>';
  const bars = Array.from({ length: 30 }, () => { const b = el(bx, 'a'); b.style.cssText += ';width:8px;border-radius:4px;background:linear-gradient(180deg,#eafffb,#3FD6BC)'; return b; });
  const said = el(root, 'a mono'); said.style.cssText += ';font-size:' + at(28, 32) + 'px;white-space:nowrap;color:#e9fffa';
  const saidWords = T.said.split(ZH ? '' : ' ').map((w, i) => { const s = el(said, '', '', 'span'); s.textContent = w + (ZH ? '' : ' '); s.style.whiteSpace = 'pre'; return s; });
  // D · files
  const mkFile = (name, kind) => {
    const f = el(root, 'a card'); box(f, at(330, 380), at(250, 290), 20); f.style.padding = '20px 22px'; f.style.overflow = 'hidden';
    f.innerHTML = `<div style="display:flex;align-items:center;gap:10px;font:600 20px var(--mono)">${icon('file')}<span>${name}</span></div>`;
    f.firstChild.firstChild.style.cssText = 'width:22px;height:22px;color:#0B8C7E';
    const body = el(f, ''); body.style.marginTop = '14px';
    if (kind === 'csv') {
      const R = rng(7); let h = '<table style="font:500 15px var(--mono);border-collapse:collapse;color:#3a3a3c">';
      for (let r = 0; r < 6; r++) { h += '<tr>'; for (let c = 0; c < 5; c++) h += `<td style="padding:3px 7px;border:1px solid #ececef;${r === 0 ? 'color:#0B8C7E;font-weight:700' : ''}">${r === 0 ? 'ABCDE'[c] + (c + 1) : (R() * 2).toFixed(3)}</td>`; h += '</tr>'; }
      body.innerHTML = h + '</table>';
    } else {
      const cols = ['#2fbf71', '#3d7bff', '#f5b13d', '#ff5a5f'], R = rng(11);
      let svg = `<svg width="${at(286, 336)}" height="${at(150, 180)}" viewBox="0 0 300 150">`;
      cols.forEach((c, k) => { let d = 'M0 140'; for (let x = 0; x <= 300; x += 3) { let y = 0; for (let p = 0; p < 12; p++) { if ((p + k) % 4 === 0) { const px = 12 + p * 25 + R() * 4; y += 110 * Math.exp(-((x - px) ** 2) / 40) * (0.6 + 0.4 * R()); } } d += `L${x} ${140 - y}`; } svg += `<path class="tr" d="${d}" fill="none" stroke="${c}" stroke-width="2.4" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>`; });
      body.innerHTML = svg + '</svg>';
    }
    return f;
  };
  const f1 = mkFile('plate-reader.csv', 'csv'), f2 = mkFile('clone3.ab1', 'ab1');
  const traces = [...f2.querySelectorAll('.tr')];
  // captions: stacked, each slams in and the last one dims
  const capX = at(CX - 870, CX), al = at('left', 'center');
  const cy0 = at(CY - 165, CY - 780), gap = at(110, 92), sz = at(78, 74);
  const caps = [T.type, T.snap, T.say, T.drop].map((s, i) => caption(s, { x: capX, y: cy0 + i * gap, size: sz, align: al, t0: sw[i] + 0.05, t1: 13.75, slam: true, step: 0.05, maxW: at(620, 960), dimAt: i < 3 ? sw[i + 1] : null }));
  // sounds
  [...T.typed].forEach((ch, i) => { if (ch !== ' ') cue(8.2 + i * (0.95 / T.typed.length), 'key', 0.35 + 0.2 * ((i * 7) % 3) / 2, 0.2); });
  cue(9.27, 'click', 0.9); cue(9.5, 'swoosh', 0.7); cue(9.62, 'scan', 0.7); cue(11.0, 'swoosh', 0.7); cue(12.5, 'swoosh', 0.7);
  cue(12.78, 'drop', 0.9, -0.3); cue(13.03, 'drop', 0.9, 0.3);
  return (t) => {
    cam.s = 1 + 0.02 * Math.sin((t - 8) * 0.8); cam.x = 0; cam.y = 0; cam.r = 0;
    // box geometry springs from one state to the next (it starts as the MCP socket)
    let k = 0; while (k < 3 && t >= sw[k + 1]) k++;
    const from = k === 0 ? [230, 112, 56] : states[k - 1], to = states[k];
    const sp = spring(t - sw[k], k === 0 ? 2.2 : 2.6, 0.55);
    const fromPos = k === 0 ? M2 : BOX;
    const pos = mix(fromPos, BOX, k === 0 ? E.io3(pr(t, 7.95, 8.4)) : 1);
    const end = E.iB(pr(t, 13.6, 14.05), 2.2);
    const bw = lerp(from[0], to[0], sp), bh = lerp(from[1], to[1], sp), br = lerp(from[2], to[2], clamp(sp));
    box(bx, Math.max(20, bw), Math.max(20, bh), br);
    S(bx, { x: pos[0], y: pos[1], s: 1 - 0.85 * end, o: 1 - pr(t, 13.9, 14.1) });
    const L = pos[0] - bw / 2, Tp = pos[1] - bh / 2;
    // A
    const ta = pr(t, 8.2, 9.15), n = Math.floor(ta * [...T.typed].length);
    typ.innerHTML = [...T.typed].slice(0, n).join('') + '<span class="caret" style="background:#3FD6BC"></span>';
    typ.style.opacity = t < 9.5 ? 1 - pr(t, 9.3, 9.5) : 0;
    typ.firstChild && (typ.lastChild.style.opacity = Math.floor(t / 0.2) % 2 ? 0.2 : 1);
    const press = t > 9.2 ? 1 - 0.18 * Math.exp(-(t - 9.2) * 9) * (t < 9.27 ? (t - 9.2) / 0.07 : 1) + 0.12 * wob(t - 9.27, 4, 7) : 1;
    S(send, { x: pos[0] + bw / 2 - 56, y: pos[1], s: spring(t - 8.1, 3, 0.5) * press, o: t < 9.5 ? 1 - pr(t, 9.35, 9.5) : 0 });
    // B
    const pB = t >= 9.5 && t < 11.1;
    if (pB) {
      ph.style.left = '16px'; ph.style.top = '16px'; box(ph, bw - 32, bh - 32);
      ph.style.opacity = E.o3(pr(t, 9.55, 9.75)) * (1 - pr(t, 10.85, 11.05)); ph.style.transform = `rotate(-1.5deg) scale(${lerp(1.08, 1, E.o3(pr(t, 9.5, 9.9)))})`;
      const sy = lerp(-10, bh, E.io2(pr(t, 9.65, 10.5)));
      scan.style.top = sy + 'px'; scan.style.opacity = t < 10.55 ? clamp((t - 9.65) / 0.05) : 0;
      marks.forEach((m, i) => { const lineY = 54 + m.line * at(80, 104) + 30; const tm = 9.65 + (lineY / bh) * 0.85 + (i % 2) * 0.05; if (!m.cued) { cue(tm, 'pop', 0.6, 0, 1 + i * 0.12); m.cued = 1; } const s = spring(t - tm, 3.2, 0.42); m.b.style.transform = `scale(${lerp(1.6, 1, clamp(s))})`; m.b.style.opacity = clamp((t - tm) / 0.06); });
      corners.forEach((c, i) => { const s = E.oB(pr(t, 9.5, 9.8)); const sx = i === 0 || i === 3 ? -1 : 1, syy = i < 2 ? -1 : 1; S(c, { x: pos[0] + sx * (bw / 2 + 14) * lerp(1.25, 1, s), y: pos[1] + syy * (bh / 2 + 14) * lerp(1.25, 1, s), o: s * (1 - pr(t, 10.8, 11.0)) }); });
    } else { ph.style.opacity = 0; scan.style.opacity = 0; corners.forEach(hide); }
    // C
    const pC = t >= 11 && t < 12.6;
    if (pC) {
      const ap = E.o3(pr(t, 11.05, 11.3)) * (1 - pr(t, 12.4, 12.55));
      mic.style.left = '30px'; mic.style.top = (bh / 2 - 46) + 'px'; mic.style.opacity = ap; mic.style.transform = `scale(${1 + 0.06 * Math.sin(t * 20)})`;
      bars.forEach((b, i) => {
        const env = 0.25 + 0.75 * Math.abs(Math.sin(t * 7.3 + i * 0.55) * Math.sin(t * 3.1 + i * 0.27)) * (0.6 + 0.4 * Math.sin(t * 13 + i));
        const hh = Math.max(8, (bh - 50) * env * E.o3(pr(t, 11.1 + i * 0.01, 11.4 + i * 0.01)));
        b.style.left = (150 + i * ((bw - 190) / 30)) + 'px'; b.style.top = (bh / 2 - hh / 2) + 'px'; b.style.height = hh + 'px'; b.style.opacity = ap;
      });
      saidWords.forEach((w, i) => { const tw = 11.2 + i * (ZH ? 0.07 : 0.16); w.style.opacity = clamp((t - tw) / 0.1); w.style.color = t - tw < 0.25 ? '#3FD6BC' : '#e9fffa'; });
      S(said, { x: pos[0], y: pos[1] + bh / 2 + at(60, 70), o: ap });
    } else { mic.style.opacity = 0; bars.forEach(b => (b.style.opacity = 0)); hide(said); }
    // D
    if (t >= 12.5) {
      const land = [12.78, 13.03];
      [f1, f2].forEach((f, i) => {
        const tl = land[i], fall = pr(t, tl - 0.28, tl);
        const tx = pos[0] + (i ? 1 : -1) * at(190, 215), ty = pos[1];
        const yy = lerp(ty - 520, ty, E.i2(fall));
        const sq = t > tl ? wob(t - tl, 3.4, 6) : 0;
        S(f, { x: tx, y: yy + (t > tl ? 0 : 0), r: (i ? 4 : -4) * (1 - fall) + (i ? 2 : -2), sx: 1 + 0.12 * sq, sy: 1 - 0.14 * sq, s: 1 - 0.85 * end, o: clamp(fall * 4) * (1 - pr(t, 13.9, 14.1)) });
      });
      traces.forEach((tr, i) => tr.setAttribute('stroke-dashoffset', 1 - E.o2(pr(t, 13.05 + i * 0.06, 13.6 + i * 0.06))));
      bx.style.outline = `3px dashed rgba(63,214,188,${0.5 * pr(t, 12.5, 12.7) * (1 - end)})`; bx.style.outlineOffset = '-14px';
    } else { hide(f1); hide(f2); bx.style.outline = 'none'; }
    caps.forEach(c => c.render(t));
  };
});

// ================================================================ 4 · it finds every record (13.95–20.1)
const TILE = at(168, 190);
const tilePos = V
  ? [[CX - 375, CY - 190], [CX - 125, CY - 190], [CX + 125, CY - 190], [CX + 375, CY - 190], [CX - 250, CY + 180], [CX, CY + 180], [CX + 250, CY + 180]]
  : Array.from({ length: 7 }, (_, i) => [CX + (i - 3) * 236, CY + 100]);
scene(13.95, 20.15, root => {
  const icons = ['mouse', 'cage', 'flask', 'vials', 'plasmid', 'notebook', 'calendar'];
  const tiles = icons.map((ic, i) => { const e = el(root, 'a glass tile', icon(ic)); box(e, TILE, TILE, TILE * 0.24); return e; });
  const labels = T.dbs.map(n => el(root, 'a tlabel', n));
  const founds = T.found.map(f => f ? el(root, 'a tfound', `<b>${f[0]}</b>${f[1]}`) : null);
  const target = [1, 0, 2, 3, 5, 6];
  const chips = T.chips.map(c => el(root, 'a chip', c));
  if (V) chips.forEach(c => (c.style.fontSize = '25px'));
  let rowPos = null;
  const cap = caption(T.finds, { x: CX, y: at(CY + 400, CY + 470), size: at(66, 72), t0: 15.0, t1: 19.35, maxW: at(1500, 960), step: ZH ? 0.05 : 0.09 });
  const launch = i => 15.5 + i * 0.5, FLY = 0.42;
  chips.forEach((_, i) => { cue(launch(i), 'zip', 0.55, (tilePos[target[i]][0] - CX) / W); cue(launch(i) + FLY, 'hit', 0.8, (tilePos[target[i]][0] - CX) / W, 1 + i * 0.1); });
  tiles.forEach((_, i) => cue(14.3 + i * 0.07, 'pop', 0.35, (tilePos[i][0] - CX) / W, 0.8 + i * 0.08));
  cue(18.0, 'riser', 0.7);
  return (t) => {
    if (!rowPos) {
      const ws = chips.map(c => c.offsetWidth), g = 16;
      if (V) { const rows = [[0, 1, 2], [3, 4, 5]]; rowPos = []; rows.forEach((r, ri) => { const tw = r.reduce((a, i) => a + ws[i], 0) + g * (r.length - 1); let x = CX - tw / 2; r.forEach(i => { rowPos[i] = [x + ws[i] / 2, CY - 600 + ri * 84]; x += ws[i] + g; }); }); }
      else { const tw = ws.reduce((a, b) => a + b, 0) + g * 5; let x = CX - tw / 2; rowPos = ws.map(w => { const p = [x + w / 2, CY - 270]; x += w + g; return p; }); }
    }
    cam.s = 1 + 0.05 * E.io2(pr(t, 14, 18.5)); cam.x = 0; cam.y = 0; cam.r = 0;
    // the build-up: pull out a little, then everything collapses into the middle
    const out = E.io2(pr(t, 18.5, 19.55)), col = E.iX(pr(t, 19.55, 20.0));
    const ctr = [CX, at(CY - 40, CY + 40)];
    const place = p => { const q = [ctr[0] + (p[0] - ctr[0]) * (1 + 0.08 * out), ctr[1] + (p[1] - ctr[1]) * (1 + 0.08 * out)]; return mix(q, ctr, col); };
    tiles.forEach((e, i) => {
      const hits = target.map((tg, k) => (tg === i ? launch(k) + FLY : null)).filter(x => x !== null);
      let sq = 0, glow = 0; hits.forEach(h => { sq += wob(t - h, 3.6, 7); glow = Math.max(glow, t > h ? Math.exp(-(t - h) * 2.2) : 0); });
      const s = spring(t - (14.3 + i * 0.07), 2.8, 0.45);
      const p = place(tilePos[i]);
      S(e, { x: p[0], y: p[1], s: s * (1 - 0.8 * col), sx: 1 + 0.14 * sq, sy: 1 - 0.14 * sq, o: clamp((t - 14.3 - i * 0.07) / 0.08) * (1 - col), blur: 8 * col });
      const lit = hits.length && t > hits[0];
      e.style.boxShadow = lit ? `inset 0 1px 0 rgba(255,255,255,.25), 0 0 ${30 + 50 * glow}px rgba(63,214,188,${0.25 + 0.5 * glow}), 0 30px 80px rgba(0,0,0,.45)` : '';
      e.style.borderColor = lit ? 'rgba(63,214,188,.55)' : '';
      const lp = place([tilePos[i][0], tilePos[i][1] + TILE / 2 + 34]);
      const fk = lit ? E.o3(pr(t, hits[0], hits[0] + 0.25)) : 0;
      S(labels[i], { x: lp[0], y: lp[1], o: clamp((t - 14.45 - i * 0.07) / 0.2) * (1 - fk) * (1 - col), s: 1 - 0.8 * col });
      if (founds[i]) S(founds[i], { x: lp[0], y: lp[1] + 12 - 12 * fk, o: fk * (1 - col), s: (0.9 + 0.1 * E.oB(fk)) * (1 - 0.8 * col) });
    });
    chips.forEach((c, i) => {
      const appear = 13.98 + i * 0.07;
      const pIn = E.oX(pr(t, appear, appear + 0.45));
      const l0 = launch(i), tg = place(tilePos[target[i]]);
      const start = mix(BOX, rowPos[i], pIn);
      if (t < l0) {
        const hop = l0 - t < 0.1 ? -8 * E.o2(1 - (l0 - t) / 0.1) : 0;
        S(c, { x: start[0], y: start[1] + hop + 3 * Math.sin(t * 3 + i), s: lerp(0.3, 1, pIn), o: clamp((t - appear) / 0.06), blur: 6 * (1 - pIn) });
      } else {
        const k = E.io3(pr(t, l0, l0 + FLY));
        const p0 = rowPos[i], p3 = tg;
        const p1 = [p0[0], p0[1] - 120], p2 = [p3[0], p3[1] - 260];
        const p = bez(p0, p1, p2, p3, k), q = bez(p0, p1, p2, p3, Math.min(1, k + 0.02));
        const ang = Math.atan2(q[1] - p[1], q[0] - p[0]), spd = Math.sin(Math.PI * k);
        S(c, { x: p[0], y: p[1], s: lerp(1, 0.35, E.i2(k)), st: [ang, 0.35 * spd], o: 1 - pr(t, l0 + FLY - 0.06, l0 + FLY), blur: 3 * spd });
        strand(s => bez(p0, p1, p2, p3, s), Math.max(0, k - 0.45), k, { amp: 8, period: 60, phase: -t * 12, w: 3, alpha: 1 - pr(t, l0 + FLY, l0 + FLY + 0.3) });
        if (t > l0 + FLY) burst(t, l0 + FLY, tg[0], tg[1], { n: 14, speed: 520, life: 0.55, seed: 40 + i, size: 5, grav: 300 });
      }
    });
    cap.render(t);
  };
});

// ================================================================ 5 · one proposal, you approve (19.95–28.3)
const CARD = at([CX, CY - 60], [CX, CY + 90]), CS = at(1.18, 1);
const PHONE = at([CX + 400, CY + 10], [CX, CY + 250]), PS = at(1.1, 1.25);
scene(19.95, 28.35, root => {
  const card = el(root, 'a card prop'); card.style.width = at(1060, 980) + 'px';
  const banner = el(card, 'banner', `${icon('check')}<span>${T.banner}</span>`); banner.firstChild.style.cssText = 'width:20px;height:20px';
  const hd = el(card, 'hd', T.propHd), sum = el(card, 'sum', T.propSum);
  const tints = [['mouse', '#e3f6f2', '#0B8C7E'], ['cage', '#e3f6f2', '#0B8C7E'], ['mouse', '#e3f6f2', '#0B8C7E'], ['flask', '#e9edff', '#3d63d8'], ['vials', '#fff1dc', '#b8760a'], ['notebook', '#f1ebff', '#7a52d6']];
  const rowIcons = [0, 1, 1, 2, 3, 4].map(i => [['cage', '#e3f6f2', '#0B8C7E'], ['mouse', '#e3f6f2', '#0B8C7E'], ['flask', '#e9edff', '#3d63d8'], ['vials', '#fff1dc', '#b8760a'], ['notebook', '#f1ebff', '#7a52d6']][i]);
  const rows = T.rows.map((r, i) => {
    const e = el(card, 'row');
    const ic = el(e, 'rico', icon(rowIcons[i][0])); ic.style.background = rowIcons[i][1]; ic.style.color = rowIcons[i][2];
    const ok = el(ic, 'ok', icon('check')); ok.firstChild.style.cssText = 'width:22px;height:22px';
    const tx = el(e, '', r, 'span'); const ev = el(e, 'ev', T.ev[i], 'span');
    return { e, ic, ok, tx, ev };
  });
  const btns = el(card, 'btns');
  const ok = el(btns, 'btn ok', `${icon('check')}<span>${T.approve}</span>`); ok.firstChild.style.cssText = 'width:20px;height:20px';
  const no = el(btns, 'btn no', `${icon('close')}<span>${T.discard}</span>`); no.firstChild.style.cssText = 'width:18px;height:18px';
  const note = el(btns, 'note', T.propNote); if (V) note.style.display = 'none';
  const cursor = el(root, 'a'); cursor.innerHTML = '<svg width="44" height="44" viewBox="0 0 24 24"><path d="M5 2.5l13.5 12.2-6.1.6 3.6 6.7-2.6 1.3-3.5-6.8-4.9 4.2z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  cursor.style.filter = 'drop-shadow(0 6px 10px rgba(0,0,0,.45))';
  const c1 = caption(T.one, { x: CX, y: at(CY + 400, CY - 720), size: at(64, 72), t0: 22.0, t1: 26.15, maxW: at(1500, 960), times: ZH ? null : [22.0, 22.5, 23.0, 23.35], step: 0.06 });
  const c2 = caption(T.nothing, { x: CX, y: at(CY + 400, CY - 720), size: at(64, 72), t0: 26.5, t1: 27.6, maxW: at(1500, 960), step: ZH ? 0.04 : 0.08 });
  let m = null;
  cue(20.0, 'impact', 1); rows.forEach((_, i) => { cue(20.5 + i * 0.25, 'note', 0.6, 0, i); cue(22.0 + i * 0.125, 'tick', 0.45, 0.3, 1 + i * 0.1); });
  cue(25.5, 'press', 0.8); cue(26.0, 'approve', 1); rows.forEach((_, i) => cue(26.1 + i * 0.07, 'tick', 0.5, 0, 1.5 + i * 0.12));
  cue(27.65, 'swoosh', 0.8);
  return (t) => {
    if (!m) {
      card.style.transform = 'none'; card.style.left = (CARD[0] - card.offsetWidth / 2) + 'px'; card.style.top = (CARD[1] - card.offsetHeight / 2) + 'px';
      const cr = card.getBoundingClientRect(), br = ok.getBoundingClientRect();
      m = { w: card.offsetWidth, h: card.offsetHeight, btn: [(br.left + br.width / 2 - cr.left - cr.width / 2) * CS + CARD[0], (br.top + br.height / 2 - cr.top - cr.height / 2) * CS + CARD[1]] };
      card.style.left = '0px'; card.style.top = '0px';
    }
    cam.x = 0; cam.y = 0; cam.r = 0;
    const zoomIn = E.io3(pr(t, 23.5, 25.2)), zoomOut = E.io3(pr(t, 26.1, 27.0));
    const fx0 = m.btn[0] - CX, fy0 = m.btn[1] - CY;
    const z = at(0.12, 0.05) * zoomIn * (1 - zoomOut);
    cam.s = 1 + z; cam.x = -fx0 * z; cam.y = -fy0 * z;
    // the card slams together on the drop
    const sp = spring(t - 20.0, 2.4, 0.38), leave = E.iB(pr(t, 27.6, 28.15), 1.8);
    const pos = mix(CARD, PHONE, leave);
    S(card, { x: pos[0], y: pos[1], s: lerp(0.55, 1, sp) * lerp(1, 0.28, leave) * CS, r: -3 * (1 - clamp(sp)) + 6 * leave, o: clamp((t - 20) / 0.06) * (1 - pr(t, 28.0, 28.2)), blur: 14 * (1 - E.o3(pr(t, 20, 20.3))) + 6 * leave });
    hd.style.opacity = E.o3(pr(t, 20.15, 20.4)); hd.style.transform = `translateX(${(1 - E.o3(pr(t, 20.15, 20.5))) * -30}px)`;
    sum.style.opacity = E.o3(pr(t, 20.3, 20.6)); sum.style.transform = `translateY(${(1 - E.o3(pr(t, 20.3, 20.6))) * 14}px)`;
    rows.forEach((r, i) => {
      const ti = 20.5 + i * 0.25, k = E.oX(pr(t, ti, ti + 0.4));
      r.e.style.opacity = clamp((t - ti) / 0.08); r.e.style.transform = `translateX(${(1 - k) * 90}px)`;
      const si = spring(t - ti, 3, 0.4);
      r.ic.style.transform = `scale(${si}) rotate(${(1 - clamp(si)) * -30}deg)`;
      const te = 22.0 + i * 0.125, se = spring(t - te, 3.2, 0.45);
      r.ev.style.opacity = clamp((t - te) / 0.05); r.ev.style.transform = `scale(${lerp(0.4, 1, se)})`;
      const ta = 26.1 + i * 0.07, sa = spring(t - ta, 3.4, 0.4);
      r.ok.style.opacity = clamp((t - ta) / 0.04); r.ok.style.transform = `scale(${sa})`;
      r.tx.style.color = t > ta ? hexmix('#1d1d1f', '#11714f', E.o3(pr(t, ta, ta + 0.2))) : '';
    });
    const sb = spring(t - 22.75, 3, 0.45);
    btns.style.opacity = clamp((t - 22.75) / 0.06); btns.style.transform = `translateY(${(1 - clamp(sb)) * 20}px)`;
    // hover, press, release
    const hover = E.o3(pr(t, 24.9, 25.2)), down = E.io2(pr(t, 25.5, 25.62)) * (1 - pr(t, 25.98, 26.0));
    const rel = t >= 26 ? wob(t - 26, 3.2, 5) : 0;
    ok.style.transform = `translateY(${-3 * hover * (1 - down)}px) scale(${1 + 0.04 * hover - 0.1 * down + 0.16 * rel})`;
    ok.style.boxShadow = `0 ${6 + 10 * hover}px ${18 + 20 * hover}px rgba(31,158,139,${0.35 + 0.3 * hover})`;
    const bh = E.oB(pr(t, 26.1, 26.45));
    banner.style.height = (bh * 50) + 'px'; banner.style.marginBottom = (bh * 16) + 'px'; banner.style.opacity = clamp((t - 26.1) / 0.1);
    // cursor glides in on a curve
    if (t > 23.4 && t < 27.6) {
      const k = E.io3(pr(t, 23.5, 25.0));
      const p = bez([W + 60, H + 80], [W * 0.8, H * 0.95], [m.btn[0] + 160, m.btn[1] + 170], [m.btn[0] + 10, m.btn[1] + 14], k);
      S(cursor, { x: p[0] + 10, y: p[1] + 14, s: 1 - 0.14 * down + 0.1 * rel, o: 1 - pr(t, 26.8, 27.3) });
    } else hide(cursor);
    if (t > 26) {
      for (let j = 0; j < 3; j++) { const d = pr(t, 26 + j * 0.08, 26.7 + j * 0.08); ring(m.btn[0], m.btn[1], 30 + 520 * E.o4(d), 6 * (1 - d) + 1, j ? '#ffffff' : '#3FD6BC', (1 - d) * 0.9); }
      burst(t, 26.0, m.btn[0], m.btn[1], { n: 44, speed: 1300, life: 1.0, seed: 9, size: 7, grav: 1100 });
    }
    c1.render(t); c2.render(t);
  };
});

// ================================================================ 6 · captures at the bench (27.9–36.2)
scene(27.9, 36.2, (root, me) => {
  const ph = el(root, 'a phone'); const scr = el(ph, 'screen'); el(scr, 'island');
  const status = el(scr, 'a', '<b>9:41</b>'); status.style.cssText += ';left:40px;top:22px;font-size:17px';
  // list pane
  const list = el(scr, 'pane');
  el(list, 'ptitle', T.captures);
  const nb = el(list, 'pbtn', `${icon('plus')}<span>${T.newCapture}</span>`); nb.style.cssText += ';position:absolute;right:22px;top:66px;height:46px;padding:0 16px;font-size:17px'; nb.firstChild.style.cssText = 'width:16px;height:16px';
  const cards = T.capList.map((c, i) => { const e = el(list, 'cap-card', `<div class="t">${c}</div><div class="s">${T.capSub[i]}</div><span class="badge wait">${T.waiting}</span><span class="badge used">${T.used}</span>`); e.style.top = (140 + i * 118) + 'px'; return e; });
  // form pane
  const form = el(scr, 'pane');
  el(form, 'ptitle', T.newCapture).style.fontSize = '32px';
  const ta = el(form, ''); ta.style.cssText = 'margin-top:18px;height:150px;border-radius:16px;background:#fff;border:1.5px solid #d2d2d7;padding:14px 16px;font-size:20px;line-height:1.35';
  const brow = el(form, ''); brow.style.cssText = 'display:flex;gap:8px;margin-top:14px';
  const camSvg = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>';
  const fb = [[camSvg, T.takePhoto], [icon('file'), T.chooseFile], [icon('qrcode'), T.scanCard]].map(([ic, l]) => { const b = el(brow, '', `${ic}<div>${l}</div>`); b.style.cssText = 'flex:1;height:84px;border-radius:14px;background:#fff;border:1.5px solid #d2d2d7;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;font-size:14px;font-weight:600;color:#1d1d1f;text-align:center'; const s = b.querySelector('svg'); s.style.width = '22px'; s.style.height = '22px'; s.style.color = '#0B8C7E'; return b; });
  const att = el(form, ''); att.style.cssText = 'display:flex;gap:10px;margin-top:16px;align-items:center;height:76px';
  const thumb = el(att, 'paper'); thumb.style.cssText += ';width:96px;height:72px;transform-origin:50% 50%;position:relative';
  [0, 1, 2].forEach(i => { const r = el(thumb, 'rule'); r.style.top = (18 + i * 18) + 'px'; });
  const tchip = el(att, '', `${icon('cage')}<span>${T.cage104}</span>`); tchip.style.cssText = 'display:flex;gap:8px;align-items:center;padding:10px 14px;border-radius:99px;background:#e3f6f2;color:#0B8C7E;font-weight:650;font-size:17px';
  tchip.firstChild.style.cssText = 'width:18px;height:18px';
  const save = el(form, 'pbtn', T.save); save.style.cssText += ';position:absolute;left:22px;right:22px;bottom:40px;height:60px;font-size:20px';
  const flashS = el(scr, 'a'); flashS.style.cssText += ';inset:0;width:100%;height:100%;background:#fff;z-index:5';
  const scanner = el(scr, 'a'); scanner.style.cssText += ';inset:0;width:100%;height:100%;background:rgba(10,14,15,.86);z-index:4';
  const qr = el(scanner, 'a'); qr.style.cssText += ';left:50%;top:46%;width:200px;height:200px;margin:-100px 0 0 -100px;background:#fff;border-radius:10px;padding:14px';
  { const R = rng(5); let h = '<svg viewBox="0 0 21 21" width="172" height="172" shape-rendering="crispEdges">'; for (let y = 0; y < 21; y++) for (let x = 0; x < 21; x++) { const fin = (x < 7 && y < 7) || (x > 13 && y < 7) || (x < 7 && y > 13); const on = fin ? (x % 20 === 0 || y % 20 === 0 || x === 6 || y === 6 || x === 14 || y === 14 || ((x > 1 && x < 5 && y > 1 && y < 5) || (x > 15 && x < 19 && y > 1 && y < 5) || (x > 1 && x < 5 && y > 15 && y < 19))) : R() > 0.52; if (on && !(fin && ((x === 1 || x === 5 || x === 15 || x === 19) && (y < 6 || y > 14)) )) h += `<rect x="${x}" y="${y}" width="1" height="1"/>`; } qr.innerHTML = h + '</svg>'; }
  const qc = [0, 1, 2, 3].map(i => { const c = el(scanner, 'a'); box(c, 44, 44); c.style.border = '5px solid #3FD6BC'; c.style.borderRadius = '8px'; c.style.borderWidth = ['5px 0 0 5px', '5px 5px 0 0', '0 5px 5px 0', '0 0 5px 5px'][i]; return c; });
  const tap = el(root, 'a dot'); box(tap, 70, 70); tap.style.background = 'rgba(255,255,255,.35)'; tap.style.border = '2px solid rgba(255,255,255,.8)';
  // beside the phone: the request and the proposal it makes
  const BUB = at([CX - 450, CY + 40], [CX, CY - 550]), MP = at([CX - 450, CY + 200], [CX, CY - 420]);
  const bub = el(root, 'a bubble'); const bubT = el(bub, '', '', 'span'); const bubC = el(bub, 'caret', '', 'span');
  const mp = el(root, 'a card'); mp.style.cssText += ';display:flex;align-items:center;gap:16px;padding:18px 22px;width:' + at(470, 600) + 'px';
  mp.innerHTML = `<img src="/app/static/icon.svg" style="width:52px;height:52px;margin:-4px"><div style="flex:1"><div style="font-size:21px;font-weight:700">${T.prop2}</div><div style="font-size:15px;color:#6e6e73;margin-top:3px">${T.prop2s}</div></div><div style="color:#0B8C7E;font-weight:700;font-size:18px;white-space:nowrap">${T.review}</div>`;
  const ghosts = [0, 1, 2, 3].map(i => { const g = el(root, 'a cap-card', `<div class="t">${T.capList[i]}</div><div class="s">${T.capSub[i]}</div>`); g.style.left = '0'; g.style.right = 'auto'; g.style.width = '350px'; return g; });
  const capX = at(CX - 870, CX), al = at('left', 'center');
  const c1 = caption(T.bench, { x: capX, y: at(CY - 260, CY - 760), size: at(74, 70), align: al, t0: 28.5, t1: 35.6, maxW: at(800, 960), step: ZH ? 0.04 : 0.1 });
  const c2 = caption(T.later, { x: capX, y: at(CY - 165, CY - 670), size: at(74, 70), align: al, t0: 32.0, t1: 35.6, maxW: at(800, 960), step: ZH ? 0.04 : 0.1 });
  // phone-local → screen coordinates (the phone is 420×860 and sits at PHONE)
  const scrPt = (x, y) => [PHONE[0] + (13 + x - 210) * PS, PHONE[1] + (13 + y - 430) * PS];
  const taps = [[28.9, 330, 89], [30.0, 72, 300], [30.6, 322, 300], [31.5, 197, 783]];
  taps.forEach(([tt]) => cue(tt, 'tap', 0.7, at(0.4, 0)));
  cue(28.0, 'whoosh', 0.9); cue(29.0, 'swoosh', 0.4); cue(30.02, 'shutter', 0.9); cue(30.62, 'scan', 0.5); cue(31.15, 'blip', 0.8); cue(31.8, 'swoosh', 0.4);
  [32.0, 32.5, 33.0, 33.5].forEach((tt, i) => cue(tt, 'drop', 0.6, at(0.4, 0), 1 + i * 0.1));
  [...T.process].forEach((ch, i) => cue(33.85 + i * (0.5 / T.process.length), 'key', 0.35, at(-0.4, 0)));
  [0, 1, 2, 3].forEach(i => cue(34.5 + i * 0.12, 'zip', 0.4, at(-0.3, 0)));
  cue(35.0, 'pop', 0.9, at(-0.4, 0), 1.6); [0, 1, 2, 3].forEach(i => cue(35.1 + i * 0.1, 'tick', 0.45, 0, 1.4 + i * 0.1));
  cue(35.7, 'whoosh', 0.8);
  return (t) => {
    const dive = E.iX(pr(t, 35.65, 36.15));
    cam.s = 1; cam.x = 0; cam.y = 0; cam.r = 0;
    const tf = `translate(${MP[0]}px,${MP[1]}px) scale(${1 + 1.6 * dive}) translate(${-MP[0]}px,${-MP[1]}px)`;
    root.style.transformOrigin = me.caps.style.transformOrigin = '0 0';
    root.style.transform = me.caps.style.transform = tf;
    root.style.opacity = me.caps.style.opacity = 1 - pr(t, 35.85, 36.15);
    const sin = spring(t - 28.0, 1.6, 0.55);
    S(ph, { x: PHONE[0], y: PHONE[1] + 900 * (1 - sin) + 8 * Math.sin(t * 1.3), s: PS, rx: 24 * (1 - clamp(sin)), r: lerp(-10, at(-2, 0), clamp(sin)) + Math.sin(t * 0.9) * 0.6, o: clamp((t - 28) / 0.1), blur: 10 * dive });
    // panes: list ⇄ form
    const toForm = E.oX(pr(t, 29.0, 29.35)), back = E.oX(pr(t, 31.8, 32.15));
    const fpos = t < 31.8 ? 1 - toForm : back;
    list.style.transform = `translateX(${-fpos * 0 + (t < 31.8 ? -toForm * 100 : (back - 1) * 100)}%)`;
    form.style.transform = `translateX(${t < 31.8 ? (1 - toForm) * 100 : back * -100}%)`;
    // list: buttons and capture cards
    nb.style.transform = `scale(${t > 28.85 && t < 29.05 ? 0.92 : 1})`;
    cards.forEach((c, i) => {
      const first = t < 31.8;
      const ti = 32.0 + i * 0.5;
      const k = first ? (i === 1 ? 1 : 0) : spring(t - ti, 2.6, 0.45);
      const shown = first ? (i === 1 ? 1 : 0) : clamp((t - ti) / 0.06);
      c.style.opacity = first ? (i === 1 ? 1 : 0) : shown;
      c.style.transform = `translateY(${(1 - k) * -70}px) scale(${lerp(0.9, 1, clamp(k))})`;
      c.style.top = (first ? 140 : 140 + i * 118) + 'px';
      const tu = 35.1 + i * 0.1, u = E.oB(pr(t, tu, tu + 0.18));
      const [bw, bu] = c.querySelectorAll('.badge'); bw.style.opacity = 1 - u; bu.style.opacity = u; bu.style.transform = `scale(${lerp(0.5, 1, u)})`;
      const lift = Math.sin(Math.PI * pr(t, 34.5 + i * 0.12, 35.0 + i * 0.12));
      c.style.boxShadow = lift > 0 ? `0 0 0 3px rgba(63,214,188,${lift}), 0 10px 30px rgba(63,214,188,${0.5 * lift})` : '';
    });
    if (t < 31.8) cards[1].querySelector('.t').textContent = T.capList[1];
    // form
    const typed = pr(t, 29.15, 29.9), n = Math.floor(typed * [...T.capText].length);
    ta.innerHTML = [...T.capText].slice(0, n).join('') + (t < 30 ? '<span class="caret" style="background:#0B8C7E"></span>' : '');
    [28.9, 30.0, 30.6].forEach(() => {});
    fb.forEach((b, i) => { const tt = [30.0, 0, 30.6][i]; b.style.transform = `scale(${tt && t > tt - 0.05 && t < tt + 0.1 ? 0.93 : 1})`; b.style.borderColor = tt && t > tt ? '#0B8C7E' : '#d2d2d7'; });
    const st = spring(t - 30.1, 3, 0.42); thumb.style.transform = `scale(${st}) rotate(${(1 - clamp(st)) * 20 - 3}deg)`; thumb.style.opacity = clamp((t - 30.1) / 0.05);
    const sc = spring(t - 31.25, 3, 0.42); tchip.style.transform = `scale(${sc})`; tchip.style.opacity = clamp((t - 31.25) / 0.05);
    save.style.transform = `scale(${t > 31.45 && t < 31.6 ? 0.95 : 1})`; save.style.filter = t > 31.5 && t < 31.75 ? 'brightness(1.25)' : '';
    flashS.style.opacity = t > 30.02 ? 0.95 * (1 - E.o2(pr(t, 30.02, 30.3))) : 0;
    const sv = pr(t, 30.62, 30.7) * (1 - pr(t, 31.15, 31.3));
    scanner.style.opacity = sv;
    qc.forEach((c, i) => { const k = E.oB(pr(t, 30.65, 31.05)); const sx = i === 0 || i === 3 ? -1 : 1, sy = i < 2 ? -1 : 1; c.style.left = (197 + sx * lerp(160, 118, k) - 22) + 'px'; c.style.top = (385 + sy * lerp(160, 118, k) - 22) + 'px'; c.style.borderColor = t > 31.1 ? '#7ff0dc' : '#3FD6BC'; });
    // finger taps
    let shown = false;
    for (const [tt, x, y] of taps) { const d = t - tt + 0.08; if (d > 0 && d < 0.45) { const p = scrPt(x, y); S(tap, { x: p[0], y: p[1] + 900 * (1 - sin), s: lerp(0.5, 1.3, E.o3(d / 0.45)), o: 1 - d / 0.45 }); shown = true; } }
    if (!shown) hide(tap);
    // the request beside the phone
    const sb = spring(t - 33.7, 2.8, 0.45);
    bubT.textContent = [...T.process].slice(0, Math.floor(pr(t, 33.85, 34.35) * [...T.process].length)).join('');
    bubC.style.opacity = t < 34.5 && Math.floor(t / 0.2) % 2 ? 0.2 : t < 34.5 ? 1 : 0;
    S(bub, { x: BUB[0], y: BUB[1], s: sb, o: clamp((t - 33.7) / 0.06) * (1 - dive) });
    ghosts.forEach((g, i) => {
      const t0 = 34.5 + i * 0.12, k = E.io3(pr(t, t0, t0 + 0.5));
      if (t < t0 || k >= 1) { hide(g); return; }
      const p0 = scrPt(197, 140 + i * 118 + 52), p3 = MP;
      const p = bez(p0, [p0[0] - at(150, 0), p0[1] - at(100, 160)], [p3[0] + at(150, 0), p3[1] - at(140, -120)], p3, k);
      S(g, { x: p[0], y: p[1], s: lerp(1, 0.4, k), o: 1 - pr(k, 0.8, 1), blur: 3 * Math.sin(Math.PI * k), r: (i - 1.5) * 6 * Math.sin(Math.PI * k) });
      strand(s => bez(p0, [p0[0] - at(150, 0), p0[1] - at(100, 160)], [p3[0] + at(150, 0), p3[1] - at(140, -120)], p3, s), Math.max(0, k - 0.4), k, { amp: 7, period: 50, phase: -t * 12, w: 3, alpha: 0.9 });
    });
    const sm = spring(t - 35.0, 2.6, 0.42);
    S(mp, { x: MP[0], y: MP[1], s: sm, o: clamp((t - 35) / 0.05) });
    if (t > 35) burst(t, 35.0, MP[0], MP[1], { n: 20, speed: 700, life: 0.7, seed: 21, size: 6, grav: 400 });
    c1.render(t); c2.render(t);
  };
});

// ================================================================ 7 · ask anything (35.9–44.1)
scene(35.9, 44.15, (root, me) => {
  const QP = at([CX, CY - 330], [CX, CY - 500]), AP = at([CX, CY + 70], [CX, CY + 40]);
  const qs = [T.q1, T.q2, T.q3];
  const qWin = [[36.05, 38.55], [38.65, 41.15], [41.25, 43.6]];
  const bubs = qs.map(q => { const b = el(root, 'a bubble'); b.style.fontSize = at(32, 38) + 'px'; if (V) { b.style.whiteSpace = 'normal'; b.style.width = '900px'; b.style.textAlign = 'center'; } b.innerHTML = `<span></span><span class="caret"></span>`; return b; });
  // a · the freezer box
  const fz = el(root, 'a glass'); box(fz, 560, 600, 30);
  const fzH = el(fz, 'mono', `${icon('snowflake')} ${T.box}`); fzH.style.cssText = 'position:absolute;left:28px;top:22px;font-size:19px;color:#cfeee8;display:flex;gap:10px;align-items:center';
  const R = rng(3), cellCols = ['#5e7bb8', '#8a6cc2', '#c26c8a', '#c29a5e', '#5ea8a0', '#7d8691'];
  const cells = []; for (let r = 0; r < 9; r++) for (let c = 0; c < 9; c++) { const e = el(fz, 'a dot'); box(e, 44, 44); const empty = R() < 0.18 && !(r === 0 && c === 6); e.style.background = empty ? 'transparent' : `radial-gradient(circle at 35% 30%, #fff8, ${cellCols[Math.floor(R() * cellCols.length)]} 55%)`; if (empty) e.style.border = '2px dashed rgba(255,255,255,.22)'; cells.push({ e, r, c, empty }); }
  const tgt = cells.find(c => c.r === 0 && c.c === 6);
  const a1 = el(root, 'a glass'); a1.style.cssText += ';padding:20px 26px;border-color:rgba(63,214,188,.5)';
  a1.innerHTML = `<div style="font:700 30px var(--mono);color:#fff;white-space:nowrap">${T.a1[0]}</div><div style="font:500 24px var(--mono);color:var(--mint);margin-top:6px;white-space:nowrap">${T.a1[1]} ${icon('external')}</div>`;
  // b · the family tree
  const tree = el(root, 'a'); box(tree, 900, 500);
  const nodes = [[-330, -190, 'f', '#3'], [-130, -190, 'm', '#1'], [130, -190, 'f', '#8'], [330, -190, 'm', '#5'], [-230, -10, 'f', '#12'], [230, -10, 'm', '#9'], [-200, 170, 'f', '#41'], [0, 170, 'm', '#42'], [200, 170, 'f', '#43']];
  const lvl = [0, 0, 0, 0, 1, 1, 2, 2, 2];
  const svgT = el(tree, 'a'); svgT.style.cssText += ';left:0;top:0;transform:none';
  const lines = [[0, 4], [1, 4], [2, 5], [3, 5], [4, 7], [5, 7], [4, 6], [5, 6], [4, 8], [5, 8]];
  svgT.innerHTML = `<svg width="900" height="500" viewBox="-450 -250 900 500" style="overflow:visible">${lines.map(([a, b]) => { const A = nodes[a], B = nodes[b]; const my = (A[1] + B[1]) / 2; return `<path d="M${A[0]} ${A[1] + 28}V${my}H${B[0]}V${B[1] - 28}" fill="none" stroke="${b === 7 ? '#3FD6BC' : 'rgba(255,255,255,.35)'}" stroke-width="${b === 7 ? 4 : 2.5}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>`; }).join('')}</svg>`;
  const tl = [...svgT.querySelectorAll('path')];
  const tnodes = nodes.map(([x, y, s, id], i) => { const e = el(tree, 'a glass node', `${icon(s === 'f' ? 'female' : 'male')}<span>${id}</span>`); e.firstChild.style.cssText = `width:22px;height:22px;color:${s === 'f' ? '#ff9ab5' : '#8fb4ff'}`; if (i === 7) { e.style.borderColor = 'rgba(63,214,188,.8)'; e.style.boxShadow = '0 0 40px rgba(63,214,188,.45)'; } return e; });
  const a2 = el(root, 'a glass'); a2.style.cssText += ';padding:18px 26px;font:600 26px var(--mono);color:var(--mint);white-space:nowrap;border-color:rgba(63,214,188,.5)'; a2.innerHTML = `${T.a2} ${icon('external')}`;
  // c · history
  const hist = el(root, 'a'); box(hist, at(1000, 940), 420);
  const hline = el(hist, 'a'); hline.style.cssText += `;left:${at(40, 90)}px;top:90px;height:3px;width:${at(920, 760)}px;background:rgba(255,255,255,.25);transform-origin:0 50%;border-radius:2px`;
  const hev = T.hist.map(([d, l], i) => { const e = el(hist, 'a'); e.style.cssText += `;left:${at(40, 90) + i * at(300, 253)}px;top:90px;transform:none;width:0`; e.innerHTML = `<div class="dot" style="position:absolute;left:-11px;top:-11px;width:22px;height:22px;background:${i === 3 ? '#3FD6BC' : '#9aa8a6'};box-shadow:${i === 3 ? '0 0 20px #3FD6BC' : 'none'}"></div><div class="mono" style="position:absolute;left:-60px;width:120px;text-align:center;top:-58px;font-size:21px;color:var(--muted)">${d}</div><div style="position:absolute;left:-90px;width:180px;text-align:center;top:26px;font-size:23px;font-weight:600;color:#dfeeea">${l}</div>`; return e; });
  const hc = el(root, 'a card'); hc.style.cssText += ';padding:22px 26px;display:flex;gap:18px;align-items:center;width:' + at(640, 760) + 'px';
  hc.innerHTML = `<div class="dot" style="width:56px;height:56px;flex:none;background:linear-gradient(135deg,#ffb36b,#ff7a66);display:grid;place-items:center;color:#fff;font-weight:800;font-size:24px">S</div><div style="flex:1"><div style="font-size:18px;color:#6e6e73">${T.a3[0]}</div><div style="font-size:24px;margin-top:4px"><span style="color:#6e6e73">${T.a3[1]}</span>&nbsp; <b>${T.a3[2]}</b> <span style="color:#0B8C7E">→</span> <b>${T.a3[3]}</b></div></div><div style="color:#0B8C7E">${icon('external')}</div>`;
  const cA = caption(T.ask, { x: at(CX, CX), y: at(CY + 400, CY - 760), size: at(56, 70), t0: 36.2, t1: 43.45, maxW: at(1500, 960), step: 0.08 });
  const cB = caption(T.links, { x: at(CX, CX), y: at(CY + 400, CY - 680), size: at(56, 70), t0: 39.2, t1: 43.45, maxW: at(1500, 960), step: ZH ? 0.04 : 0.08 });
  const cC = caption(T.reads, { x: CX, y: at(CY + 470, CY - 600), size: at(30, 36), t0: 41.9, t1: 43.45, maxW: at(1400, 960), step: ZH ? 0.03 : 0.06, weight: 560, color: 'rgba(238,247,244,.7)' });
  // place caption A/B side by side in 16:9: A left of B
  if (!V) { cA.o.x = CX - 360; cB.o.x = CX + 250; cA.o.maxW = 700; cB.o.maxW = 900; cA.e.style.width = '700px'; cB.e.style.width = '900px'; }
  qWin.forEach(([a], i) => { cue(a, 'pop', 0.6, 0, 1.2); [...qs[i]].forEach((ch, j) => { if (j % 2 === 0) cue(a + 0.08 + j * (0.75 / qs[i].length), 'key', 0.25, 0.1); }); });
  cue(37.6, 'chime', 0.8); cue(39.4, 'swoosh', 0.4); cue(40.8, 'chime', 0.7); cue(42.0, 'swoosh', 0.4); cue(43.2, 'chime', 0.7); cue(42.0, 'riser2', 0.65);
  return (t) => {
    const suck = E.iX(pr(t, 43.55, 44.05));
    cam.s = 1 + 0.04 * Math.sin((t - 36) * 0.4); cam.x = 0; cam.y = 0; cam.r = 0;
    root.style.transform = me.caps.style.transform = `rotate(${-20 * suck}deg) scale(${1 - 0.3 * suck})`;
    root.style.opacity = me.caps.style.opacity = 1 - pr(t, 43.9, 44.12);
    const fin = E.o3(pr(t, 35.9, 36.25));
    root.style.filter = fin < 1 ? `blur(${(1 - fin) * 8}px)` : '';
    // questions
    bubs.forEach((b, i) => {
      const [a, z] = qWin[i];
      const sIn = spring(t - a, 2.6, 0.5), out = E.i3(pr(t, z - 0.2, z + 0.1));
      const n = Math.floor(pr(t, a + 0.08, a + 0.85) * [...qs[i]].length);
      b.firstChild.textContent = [...qs[i]].slice(0, n).join('');
      b.lastChild.style.opacity = t < a + 0.9 && Math.floor(t / 0.2) % 2 ? 0.2 : t < a + 0.9 ? 1 : 0;
      S(b, { x: QP[0], y: QP[1] - 60 * out + 30 * (1 - clamp(sIn)), s: lerp(0.85, 1, clamp(sIn)), o: clamp((t - a) / 0.1) * (1 - out) * (1 - suck), blur: 8 * out });
    });
    // a · freezer box: cells pop in a wave from the middle
    const aIn = 36.9, aOut = E.i3(pr(t, 38.35, 38.7));
    if (t < 38.8) {
      S(fz, { x: AP[0] - at(170, 0), y: AP[1] + at(-30, -10), s: spring(t - aIn + 0.1, 2.2, 0.55) * (1 - 0.3 * aOut) * at(0.94, 1.35), o: clamp((t - aIn + 0.1) / 0.1) * (1 - aOut), blur: 10 * aOut });
      const hl = t > 37.6;
      cells.forEach(c => {
        const d = Math.hypot(c.r - 4, c.c - 4), tc = aIn + d * 0.04, s = spring(t - tc, 3.2, 0.45);
        const dim = hl && c !== tgt ? 0.32 : 1;
        c.e.style.left = (40 + c.c * 54) + 'px'; c.e.style.top = (80 + c.r * 54) + 'px';
        c.e.style.transform = `scale(${s * (c === tgt && hl ? 1 + 0.25 * spring(t - 37.6, 3, 0.35) : 1)})`;
        c.e.style.opacity = clamp((t - tc) / 0.05) * dim;
        if (c === tgt && hl) { c.e.style.background = 'radial-gradient(circle at 35% 30%, #fff, #3FD6BC 60%)'; c.e.style.boxShadow = '0 0 30px #3FD6BC'; }
        else if (c === tgt) { c.e.style.boxShadow = ''; }
      });
      if (hl) { const k0 = at(0.94, 1.35), cx0 = AP[0] - at(170, 0) + (-280 + 40 + 6 * 54 + 22) * k0, cy0 = AP[1] + at(-30, -10) + (-300 + 80 + 22) * k0; for (let j = 0; j < 2; j++) { const d = pr(t, 37.6 + j * 0.25, 38.4 + j * 0.25); ring(cx0, cy0, 22 + 90 * E.o3(d), 3, '#3FD6BC', (1 - d) * (1 - aOut)); } }
      const sa = spring(t - 37.8, 2.8, 0.45);
      S(a1, { x: at(AP[0] + 330, AP[0]), y: at(AP[1], AP[1] + 480), s: sa * (1 - 0.3 * aOut) * at(1, 1.2), o: clamp((t - 37.8) / 0.06) * (1 - aOut) });
    } else { hide(fz); hide(a1); }
    // b · tree grows top-down
    const bOut = E.i3(pr(t, 40.95, 41.3));
    if (t > 39.3 && t < 41.4) {
      S(tree, { x: AP[0], y: AP[1] - at(55, 20), s: at(1, 1.2) * (1 - 0.3 * bOut), o: (1 - bOut), blur: 10 * bOut });
      tnodes.forEach((e, i) => { const tn = 39.4 + lvl[i] * 0.42 + (i % 4) * 0.04; const s = spring(t - tn, 3, 0.45); S(e, { x: 450 + nodes[i][0], y: 250 + nodes[i][1], s, o: clamp((t - tn) / 0.05) }); });
      tl.forEach((p, i) => { const tn = 39.55 + (i < 4 ? 0 : 0.42); p.setAttribute('stroke-dashoffset', 1 - E.io2(pr(t, tn, tn + 0.35))); });
      const sa = spring(t - 40.8, 2.8, 0.45);
      S(a2, { x: AP[0], y: AP[1] + at(232, 360), s: sa * (1 - 0.3 * bOut) * at(1, 1.15), o: clamp((t - 40.8) / 0.06) * (1 - bOut) });
    } else { hide(tree); hide(a2); }
    // c · history
    if (t > 41.9) {
      S(hist, { x: AP[0], y: AP[1] - 60, s: (1 - 0.7 * suck), o: 1 - suck });
      hline.style.transform = `scaleX(${E.oX(pr(t, 41.95, 42.5))})`;
      hev.forEach((e, i) => { const tn = 42.0 + i * 0.25, s = spring(t - tn, 3, 0.45); e.style.opacity = clamp((t - tn) / 0.06); e.firstChild.style.transform = `scale(${s})`; e.children[1].style.transform = e.children[2].style.transform = `translateY(${(1 - clamp(s)) * 14}px)`; });
      const sc = spring(t - 43.2, 2.6, 0.45);
      S(hc, { x: AP[0] + at(150, 0), y: AP[1] + at(150, 200), s: sc * (1 - 0.7 * suck) * at(1, 1.15), o: clamp((t - 43.2) / 0.06) * (1 - suck) });
    } else { hide(hist); hide(hc); }
    cA.render(t); cB.render(t); cC.render(t);
  };
});

// ================================================================ 8 · design · compute · verify · write up (43.95–52.15)
scene(43.95, 52.2, root => {
  const VC = at([CX, CY - 60], [CX, CY + 40]);
  const g8 = el(root, 'layer'); g8.style.transformOrigin = `${VC[0]}px ${VC[1]}px`; g8.style.transform = `scale(${at(1, 1.3)})`;
  // the word bar
  const bar = el(CUR_CAPS, 'a'); bar.style.cssText += ';display:flex;gap:' + at(46, 26) + 'px;align-items:center;white-space:nowrap';
  const bw = T.words.map((w, i) => { const s = el(bar, '', '', 'span'); s.textContent = w; s.style.cssText = `font-size:${at(54, 52)}px;font-weight:800;letter-spacing:-.02em;display:inline-block;transform-origin:50% 60%`; if (i < 3) { const d = el(bar, '', '•', 'span'); d.style.cssText = 'font-size:40px;color:rgba(255,255,255,.3)'; } return s; });
  // a · design: randomise 16 animals into two groups
  const R = rng(17); const perm = [...Array(16).keys()].sort(() => R() - 0.5);
  const toks = Array.from({ length: 16 }, () => { const e = el(g8, 'a glass', icon('mouse')); box(e, 76, 76, 38); e.style.display = 'grid'; e.style.placeItems = 'center'; e.firstChild.style.cssText = 'width:38px;height:38px;color:#e9fffa'; return e; });
  const gl = [T.vehicle, T.tmx].map((g, i) => { const e = el(g8, 'a', g); e.style.cssText += `;font-size:30px;font-weight:750;color:${i ? '#3FD6BC' : '#9cbcff'}`; return e; });
  const pw = el(g8, 'a glass'); pw.style.cssText += ';padding:16px 28px;font:700 30px var(--mono);white-space:nowrap;color:#fff;border-color:rgba(63,214,188,.6)';
  // b · compute
  const ctl = el(g8, 'a glass'), trt = el(g8, 'a glass');
  [[ctl, T.ctl, '6.29'], [trt, T.trt, '4.05']].forEach(([e, l, v]) => { e.style.cssText += ';padding:22px 30px;text-align:center'; e.innerHTML = `<div class="mono" style="font-size:20px;color:var(--muted)">${l}</div><div class="mono" style="font-size:56px;font-weight:800;margin-top:4px">${v}</div>`; });
  const dd = el(g8, 'a mono'); dd.style.cssText += ';font-size:64px;font-weight:800;white-space:nowrap';
  const big = el(g8, 'a'); big.style.cssText += ';text-align:center';
  big.innerHTML = `<div class="mono" style="font-size:24px;color:var(--muted);letter-spacing:.1em;text-transform:uppercase">${T.fold}</div><div class="num" style="font-size:${at(190, 200)}px;font-weight:850;letter-spacing:-.05em;line-height:1;background:linear-gradient(180deg,#fff,#3FD6BC);-webkit-background-clip:text;color:transparent"></div>`;
  const num = big.querySelector('.num');
  const barsC = [0, 1].map(i => { const e = el(g8, 'a'); e.style.cssText += `;width:90px;border-radius:14px 14px 4px 4px;background:${i ? 'linear-gradient(180deg,#7ff0dc,#0B8C7E)' : 'linear-gradient(180deg,#9cbcff,#3d63d8)'};transform-origin:50% 100%`; return e; });
  const cMaths = caption(T.maths, { x: CX, y: at(CY + 300, CY + 520), size: at(34, 38), t0: 46.3, t1: 47.75, maxW: at(1500, 960), step: ZH ? 0.025 : 0.05, weight: 620, color: 'rgba(238,247,244,.82)' });
  // c · verify: a chromatogram scrolling to the one base that differs
  const chW = at(1180, 1000), chH = at(400, 560);
  const ch = el(root, 'a glass'); box(ch, chW, chH, 28); ch.style.overflow = 'hidden';
  const seq = 'ATGGCTAAGCTGGAGAAACTGACCGGCAAGGAATTCGTGCAGCTGAAAGGCTTAGCCGTTGAAGCAACGCTGATCGAAAAGCTG'.split('');
  const MUT = 40; const read = seq.slice(); read[MUT] = 'G'; seq[MUT] = 'A';
  const colr = { A: '#2fbf71', C: '#3d7bff', G: '#f5b13d', T: '#ff5a5f' };
  const STEP = 46;
  let chSvg = `<svg width="${seq.length * STEP + 400}" height="${chH}" class="chs" style="position:absolute;left:0;top:0">`;
  ['A', 'C', 'G', 'T'].forEach(b => { let d = `M0 ${chH - 130}`; for (let x = 0; x < seq.length * STEP; x += 3) { let y = 0; for (let i = Math.max(0, Math.floor(x / STEP) - 2); i < Math.min(seq.length, Math.floor(x / STEP) + 3); i++) { if (read[i] === b) { const px = i * STEP + STEP / 2; y += (150 + ((i * 37) % 60)) * Math.exp(-((x - px) ** 2) / 90); } else if (((i * 13 + b.charCodeAt(0)) % 7) === 0) { const px = i * STEP + STEP / 2; y += 18 * Math.exp(-((x - px) ** 2) / 90); } } d += `L${x} ${(chH - 130 - y).toFixed(1)}`; } chSvg += `<path d="${d}" fill="none" stroke="${colr[b]}" stroke-width="3"/>`; });
  read.forEach((b, i) => { chSvg += `<text x="${i * STEP + STEP / 2}" y="44" text-anchor="middle" font-family="JBM" font-weight="700" font-size="24" fill="${colr[b]}">${b}</text><text x="${i * STEP + STEP / 2}" y="${chH - 70}" text-anchor="middle" font-family="JBM" font-weight="600" font-size="22" fill="rgba(255,255,255,${i === MUT ? 1 : 0.55})">${seq[i]}</text><text x="${i * STEP + STEP / 2}" y="${chH - 104}" text-anchor="middle" font-family="JBM" font-size="18" fill="rgba(255,255,255,.35)">${i === MUT ? '' : '|'}</text>`; });
  chSvg += `<text x="10" y="${chH - 70}" font-family="JBM" font-size="16" fill="rgba(255,255,255,.4)">ref</text></svg>`;
  ch.innerHTML = chSvg; const chs = ch.firstChild;
  const mBox = el(ch, 'a'); mBox.style.cssText += `;width:${STEP + 8}px;height:${chH - 30}px;border-radius:12px;border:3px solid #ff7a66;background:rgba(255,122,102,.14);box-shadow:0 0 40px rgba(255,122,102,.5)`;
  const mut = el(root, 'a glass'); mut.style.cssText += ';padding:18px 28px;white-space:nowrap;border-color:rgba(255,122,102,.7)';
  mut.innerHTML = `<div class="mono" style="font-size:18px;color:var(--muted)">${T.verify} · clone3.ab1</div><div class="mono" style="font-size:34px;font-weight:800;color:#ffb0a3;margin-top:4px">${T.mut}</div>`;
  // d · write up
  const doc = el(root, 'a card'); box(doc, at(620, 900), at(560, 430), 22); doc.style.padding = '36px 40px';
  el(doc, '', T.methods).style.cssText = 'font-size:34px;font-weight:780;letter-spacing:-.02em;margin-bottom:16px';
  const mlines = T.methodLines.map(l => { const r = el(doc, ''); r.style.cssText = 'position:relative;height:' + at(46, 38) + 'px'; const sh = el(r, 'a'); sh.style.cssText += ';left:0;top:12px;height:18px;border-radius:9px;background:linear-gradient(90deg,#e8e8ec,#f6f6f8,#e8e8ec);transform:none;transform-origin:0 50%;width:' + (60 + (l.length * 7) % 35) + '%'; const tx = el(r, 'a', l); tx.style.cssText += ';left:0;top:6px;transform:none;font-size:' + at(21, 20) + 'px;white-space:nowrap;color:#2c2c2e'; return { sh, tx }; });
  const ck = el(root, 'a glass'); box(ck, at(560, 900), at(600, 340), 26); ck.style.padding = '28px 30px';
  el(ck, 'mono', T.arrive).style.cssText = 'font-size:19px;color:var(--mint);letter-spacing:.06em;margin-bottom:14px';
  const items = T.arriveItems.map((it, i) => { const r = el(ck, ''); r.style.cssText = `display:flex;align-items:center;gap:14px;height:${at(48, 46)}px;font-size:${at(22, 21)}px;font-weight:560${V ? `;position:absolute;left:${30 + (i % 2) * 430}px;top:${66 + Math.floor(i / 2) * 52}px` : ''}`; const b = el(r, ''); b.style.cssText = 'width:30px;height:30px;border-radius:9px;border:2px solid rgba(255,255,255,.3);display:grid;place-items:center;flex:none;position:relative'; const c = el(b, '', icon('check')); c.style.cssText = 'position:absolute;inset:-2px;border-radius:9px;background:#3FD6BC;display:grid;place-items:center;color:#04100e'; c.firstChild.style.cssText = 'width:18px;height:18px'; const tx = el(r, '', `${i + 1}  ${it}`, 'span'); return { c, tx }; });
  // sounds
  [44.0, 46.0, 48.0, 50.0].forEach((tt, i) => cue(tt, 'crash', i ? 0.55 : 0.9));
  cue(44.0, 'impact', 0.9); toks.forEach((_, i) => i % 2 || cue(44.0 + i * 0.028, 'pop', 0.25, (i % 4 - 1.5) / 4, 1 + i * 0.03));
  cue(44.5, 'shuffle', 0.8); cue(45.0, 'pop', 0.6, -0.3, 1.1); cue(45.06, 'pop', 0.6, 0.3, 1.3); cue(45.5, 'hit', 0.9, 0, 1.2);
  cue(46.0, 'drop', 0.7, -0.3); cue(46.25, 'drop', 0.7, 0.3); cue(46.5, 'swoosh', 0.6); cue(47.0, 'count', 0.7); cue(47.5, 'hit', 1, 0, 1.5);
  cue(48.0, 'swoosh', 0.5); cue(49.0, 'alert', 0.8); cue(49.5, 'hit', 0.9, 0, 1.1);
  mlines.forEach((_, i) => cue(50.05 + i * 0.08, 'key', 0.3, -0.2));
  items.forEach((_, i) => cue(50.75 + i * 0.115, 'note', 0.5, 0.2, i));
  cue(51.75, 'whoosh', 0.9);
  const grpPos = i => { const g = i < 8 ? 0 : 1, j = i % 8; return [VC[0] + (g ? 1 : -1) * at(270, 230) + (j % 2 ? 48 : -48), VC[1] - 135 + Math.floor(j / 2) * 92]; };
  return (t) => {
    cam.s = 1 + 0.03 * E.io2(pr(t % 2, 0, 2)); cam.x = 0; cam.y = 0; cam.r = 0;
    const sec = clamp(Math.floor((t - 44) / 2), 0, 3);
    // word bar
    const barIn = spring(t - 44.0, 2.4, 0.5), barOut = E.i3(pr(t, 51.75, 52.1));
    S(bar, { x: CX, y: at(CY + 420, CY - 720), s: (V ? 0.92 : 1) * lerp(0.8, 1, clamp(barIn)), o: clamp((t - 44) / 0.1) * (1 - barOut), blur: 8 * barOut });
    bw.forEach((w, i) => { const on = i === sec, k = on ? spring(t - (44 + i * 2), 3, 0.42) : 0; w.style.color = on ? '#3FD6BC' : 'rgba(255,255,255,.35)'; w.style.transform = `scale(${on ? lerp(1.25, 1.12, clamp(k)) + 0.06 * wob(t - (44 + i * 2), 3, 5) : 1})`; w.style.textShadow = on ? '0 0 30px rgba(63,214,188,.6)' : ''; });
    const secOut = (a) => E.i3(pr(t, a + 1.8, a + 2.05));
    // a
    if (t < 46.1) {
      const o = secOut(44);
      toks.forEach((e, i) => {
        const g0 = [VC[0] + ((i % 4) - 1.5) * 100, VC[1] + (Math.floor(i / 4) - 1.5) * 100];
        const dst = grpPos(perm.indexOf(i));
        const ts = 44.5 + i * 0.018, k = E.io3(pr(t, ts, ts + 0.42));
        const arc = Math.sin(Math.PI * k) * (i % 2 ? -120 : 120);
        const p = [lerp(g0[0], dst[0], k), lerp(g0[1], dst[1], k) + arc * 0.5];
        const s = spring(t - (44.0 + i * 0.028), 3.2, 0.45);
        S(e, { x: p[0], y: p[1], s: s * (1 - 0.6 * o), o: clamp((t - 44 - i * 0.028) / 0.05) * (1 - o), blur: 4 * Math.sin(Math.PI * k) + 8 * o });
        const grp = perm.indexOf(i) < 8 ? 0 : 1, tint = E.o3(pr(t, 44.95, 45.15));
        e.style.borderColor = tint ? (grp ? `rgba(63,214,188,${0.8 * tint})` : `rgba(156,188,255,${0.8 * tint})`) : '';
        e.style.background = tint ? (grp ? `rgba(63,214,188,${0.18 * tint})` : `rgba(156,188,255,${0.16 * tint})`) : '';
      });
      gl.forEach((g, i) => { const s = spring(t - (45.0 + i * 0.06), 3, 0.45); S(g, { x: VC[0] + (i ? 1 : -1) * at(270, 230), y: VC[1] - 205, s, o: clamp((t - 45 - i * 0.06) / 0.05) * (1 - o) }); });
      const sp = spring(t - 45.5, 2.6, 0.38);
      const nn = Math.round(8 * E.o3(pr(t, 45.5, 45.8)));
      pw.textContent = T.power.replace('8', String(nn));
      S(pw, { x: VC[0], y: VC[1] + 270, s: lerp(1.6, 1, clamp(sp)) * (1 - 0.5 * o), o: clamp((t - 45.5) / 0.04) * (1 - o) });
    } else { toks.forEach(hide); gl.forEach(hide); hide(pw); }
    // b
    if (t > 45.95 && t < 48.1) {
      const o = secOut(46);
      const join = E.io3(pr(t, 46.5, 46.85)), toBig = E.iB(pr(t, 46.85, 47.05));
      [ctl, trt].forEach((e, i) => { const s = spring(t - (46.0 + i * 0.25), 3, 0.42); const x0 = VC[0] + (i ? 1 : -1) * at(260, 230); S(e, { x: lerp(x0, VC[0], join), y: VC[1] - 40, s: s * (1 - 0.7 * join), o: clamp((t - 46 - i * 0.25) / 0.05) * (1 - join) }); });
      dd.innerHTML = `ΔΔCt = <span style="color:#3FD6BC">−2.24</span>`;
      S(dd, { x: VC[0], y: VC[1] - 40, s: lerp(0.5, 1, E.oB(pr(t, 46.6, 46.9))) * (1 - toBig), o: pr(t, 46.6, 46.7) * (1 - toBig) });
      const cnt = E.o3(pr(t, 47.0, 47.45));
      num.textContent = (4.72 * cnt).toFixed(2) + '×';
      const slam = t > 47.5 ? 1 + 0.12 * wob(t - 47.5, 3, 5) : 1;
      S(big, { x: VC[0] - at(140, 0), y: VC[1] - at(40, 230), s: lerp(0.6, 1, E.oB(pr(t, 47.0, 47.3))) * slam * (1 - 0.6 * o), o: pr(t, 47.0, 47.06) * (1 - o), blur: 8 * o });
      barsC.forEach((b, i) => { const hgt = (i ? 300 : 300 / 4.72) * spring(t - (47.5 + i * 0.06), 2.6, 0.45); b.style.height = Math.max(0, hgt) + 'px'; S(b, { x: at(VC[0] + 230 + i * 120, VC[0] - 70 + i * 140), y: at(VC[1] + 100, VC[1] + 290) - hgt / 2, o: clamp((t - 47.5) / 0.05) * (1 - o) }); });
    } else { hide(ctl); hide(trt); hide(dd); hide(big); barsC.forEach(hide); }
    // c
    if (t > 47.95 && t < 50.1) {
      const o = secOut(48);
      const stop = MUT * STEP + STEP / 2 - chW / 2;
      const k = E.o4(pr(t, 48.0, 49.0));
      const off = lerp(stop - 1400, stop, k);
      chs.style.transform = `translateX(${-off}px)`;
      S(ch, { x: VC[0], y: VC[1] - at(20, 40), s: lerp(0.92, 1, E.o3(pr(t, 48, 48.3))) * (1 - 0.4 * o), o: pr(t, 47.95, 48.1) * (1 - o), blur: 8 * o });
      const mk = spring(t - 49.0, 3.2, 0.4);
      mBox.style.left = (chW / 2 - STEP / 2 - 4) + 'px'; mBox.style.top = '14px'; mBox.style.transform = `scaleY(${clamp(mk, 0, 1.2)}) scaleX(${lerp(1.6, 1, clamp(mk))})`; mBox.style.opacity = clamp((t - 49) / 0.05);
      const sm = spring(t - 49.5, 2.6, 0.4);
      S(mut, { x: VC[0], y: VC[1] + chH / 2 + at(30, 80), s: lerp(1.5, 1, clamp(sm)) * (1 - 0.4 * o), o: clamp((t - 49.5) / 0.04) * (1 - o) });
    } else { hide(ch); hide(mut); }
    // d
    if (t > 49.95) {
      const o = E.iX(pr(t, 51.75, 52.1));
      const dp = at([VC[0] - 310, VC[1]], [VC[0], VC[1] - 190]), cp = at([VC[0] + 330, VC[1]], [VC[0], VC[1] + 230]);
      S(doc, { x: dp[0], y: dp[1] + 40 * (1 - E.o3(pr(t, 50, 50.35))), r: -1.5, s: 1 - 0.8 * o, o: pr(t, 49.95, 50.1) * (1 - o), blur: 10 * o });
      mlines.forEach((l, i) => { const tl = 50.05 + i * 0.08; l.sh.style.transform = `scaleX(${E.o3(pr(t, tl, tl + 0.2))})`; l.sh.style.opacity = 1 - pr(t, tl + 0.25, tl + 0.4); l.tx.style.opacity = pr(t, tl + 0.25, tl + 0.4); });
      S(ck, { x: cp[0], y: cp[1], s: spring(t - 50.2, 2.6, 0.5) * (1 - 0.8 * o), o: clamp((t - 50.2) / 0.08) * (1 - o), blur: 10 * o });
      items.forEach((it, i) => { const ti = 50.75 + i * 0.115, s = spring(t - ti, 3.4, 0.4); it.c.style.transform = `scale(${s})`; it.c.style.opacity = clamp((t - ti) / 0.03); it.tx.style.color = t > ti ? '#fff' : 'rgba(255,255,255,.45)'; });
    } else { hide(doc); hide(ck); }
    cMaths.render(t);
  };
});

// ================================================================ 9 · it all comes together (51.7–60)
scene(51.7, 60.01, root => {
  const IC = 300;
  const lock = el(root, 'a'); // the icon
  lock.innerHTML = `<div style="position:relative;width:${IC}px;height:${IC}px"><img src="/app/static/icon.svg" style="width:100%;height:100%;display:block;filter:drop-shadow(0 30px 60px rgba(63,214,188,.45))"><div class="gloss" style="position:absolute;left:9.8%;top:9.8%;width:80.4%;height:80.4%;border-radius:22.5%;overflow:hidden"><div style="position:absolute;top:-50%;left:0;width:40%;height:200%;background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);transform:rotate(20deg)"></div></div></div>`;
  const tile = el(root, 'a'); box(tile, IC * 0.805, IC * 0.805, IC * 0.181); tile.style.background = 'linear-gradient(180deg,#3FD6BC,#0B8C7E)';
  const gl = lock.querySelector('.gloss > div');
  const word = el(root, 'a'); word.style.cssText += `;font-size:${at(150, 140)}px;font-weight:820;letter-spacing:-.045em;white-space:nowrap;line-height:1`;
  const letters = [...'BioManager'].map(ch => { const s = el(word, '', ch, 'span'); s.style.display = 'inline-block'; return s; });
  const shine = el(word, 'a'); shine.style.cssText += ';left:0;top:0;width:100%;height:100%;transform:none;background:linear-gradient(100deg,transparent 40%,rgba(255,255,255,.9) 50%,transparent 60%);-webkit-background-clip:text;mix-blend-mode:overlay';
  const tagY = at(CY + 120, CY + 130);
  const tag = caption(T.tag.join(' '), { x: CX, y: tagY, size: at(58, 60), t0: 55.5, t1: 99, maxW: at(1600, 980), times: null, step: 0.5 });
  const foot = caption(T.foot, { x: CX, y: at(CY + 290, CY + 330), size: at(30, 32), t0: 57.0, t1: 99, maxW: at(1500, 900), step: ZH ? 0.012 : 0.03, weight: 540, color: 'rgba(238,247,244,.62)' });
  // tagline words land on the three beats
  const tw = tag.words.length, tt = [];
  { let k = 0; T.tag.forEach((ph, j) => { const nw = ZH ? [...ph.replace(/\*/g, '')].length : ph.split(' ').length; for (let i = 0; i < nw; i++) tt.push(55.5 + j * 0.5 + i * (ZH ? 0.03 : 0.06)); }); }
  tag.o.times = tt;
  const N = 12, R = rng(31), sp = Array.from({ length: N }, (_, i) => ({ a: (i / N) * Math.PI * 2 + R() * 0.3, d: R() * 0.25, w: 3 + R() * 2 }));
  let wordW = null;
  cue(52.0, 'reverse', 0.75); cue(54.0, 'final', 1); cue(55.5, 'bell', 0.7, -0.2, 0); cue(56.0, 'bell', 0.7, 0, 1); cue(56.5, 'bell', 0.8, 0.2, 2); cue(54.55, 'swoosh', 0.6);
  return (t) => {
    if (wordW === null) wordW = word.offsetWidth;
    cam.s = 1 + 0.025 * E.io2(pr(t, 54, 60)); cam.x = 0; cam.y = 0; cam.r = 0;
    const ctr = [CX, CY - at(40, 120)];
    // strands spiral in from everywhere
    const Rr = Math.hypot(W, H) * 0.42;
    sp.forEach((s, i) => {
      const C = u => { const r = Rr * (1 - u) + 4, a = s.a + 2.2 * u; return [ctr[0] + Math.cos(a) * r, ctr[1] + Math.sin(a) * r * (V ? 1.2 : 0.8)]; };
      const k = E.io2(pr(t, 51.8 + s.d * 0.6, 53.6 + s.d * 0.5));
      if (k > 0 && k < 1) strand(C, Math.max(0, k - 0.35), k, { amp: 10, period: 80, phase: -t * 10, w: s.w, alpha: 1 - pr(t, 53.5, 54.0) });
    });
    // the helix spins up in the middle, then becomes the icon
    if (t > 53.2 && t < 54.15) {
      const k = pr(t, 53.2, 54.0), hh = lerp(80, IC * 0.49, E.o3(k)), amp = lerp(10, IC * 0.115, E.o3(k));
      const spin = (1 - E.o3(k)) * 18;
      const helixPath = (ph) => { let d = ''; let front = ''; for (let i = 0; i <= 60; i++) { const u = i / 60, y = ctr[1] - hh / 2 + u * hh, th = u * Math.PI * 3 + ph; const x = ctr[0] + Math.sin(th) * amp; const z = Math.cos(th); (z > 0 ? (front += (front && !front.endsWith('M') ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1)) : (d += (d && !d.endsWith('M') ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1))); if (z > 0 && d && !d.endsWith('M')) d += 'M'; if (z <= 0 && front && !front.endsWith('M')) front += 'M'; } return [d.replace(/M$/, ''), front.replace(/M$/, '')]; };
      const al = 1 - pr(t, 54.0, 54.15);
      [0, Math.PI].forEach(off => {
        const [back, front] = helixPath(spin + off + Math.PI / 2);
        if (back) { const p = take('path'); p.setAttribute('d', back); p.setAttribute('stroke', '#3FD6BC'); p.setAttribute('stroke-width', 10); p.setAttribute('opacity', 0.4 * al); p.setAttribute('fill', 'none'); p.setAttribute('stroke-linecap', 'round'); }
        if (front) { const p = take('path'); p.setAttribute('d', front); p.setAttribute('stroke', '#ffffff'); p.setAttribute('stroke-width', 16); p.setAttribute('opacity', al); p.setAttribute('fill', 'none'); p.setAttribute('stroke-linecap', 'round'); }
      });
    }
    // the icon lands, then slides aside for the name
    const si = spring(t - 54.0, 2.0, 0.42);
    const lockW = IC * 0.9 * 0.82 + 40 + (wordW || 0);
    const slide = E.io4(pr(t, 54.6, 55.25));
    const iconTo = at([CX - lockW / 2 + IC * 0.9 * 0.41, ctr[1]], [CX, CY - 330]);
    const ip = mix(ctr, iconTo, slide), isc = lerp(1, at(0.9, 0.95), slide);
    S(lock, { x: ip[0], y: ip[1], s: lerp(0.4, 1, si) * isc, o: clamp((t - 54.0) / 0.03), r: (1 - clamp(si)) * -12 });
    S(tile, { x: ctr[0], y: ctr[1], s: E.oB(pr(t, 53.85, 54.05), 3) * (1 - pr(t, 54.0, 54.05)), o: pr(t, 53.85, 53.95) * (1 - pr(t, 54.0, 54.05)) });
    gl.style.transform = `translateX(${lerp(-150, 350, E.io2(pr(t, 54.25, 54.85)))}%) rotate(20deg)`;
    if (t > 54) {
      for (let j = 0; j < 2; j++) { const d = pr(t, 54 + j * 0.1, 54.9 + j * 0.1); ring(ctr[0], ctr[1], 80 + Math.max(W, H) * 0.6 * E.o3(d), 10 * (1 - d) + 1, j ? '#ffffff' : '#3FD6BC', (1 - d) * 0.8); }
      burst(t, 54.0, ctr[0], ctr[1], { n: 60, speed: 1500, life: 1.3, seed: 77, size: 7, grav: 500 });
    }
    // the name
    const wx = at(iconTo[0] + IC * 0.9 * 0.41 + 40 + (wordW || 0) / 2, CX), wy = at(ctr[1] + 8, CY - 70);
    S(word, { x: wx, y: wy, o: t > 54.6 ? 1 : 0 });
    letters.forEach((l, i) => { const tl = 54.7 + i * 0.035, s = spring(t - tl, 2.8, 0.5); l.style.transform = `translate(${(1 - clamp(s)) * -50}px, ${(1 - s) * 30}px)`; l.style.opacity = clamp((t - tl) / 0.12); l.style.filter = t - tl < 0.25 ? `blur(${8 * (1 - clamp((t - tl) / 0.25))}px)` : ''; });
    const sh = pr(t, 57.6, 58.6);
    shine.style.backgroundPosition = `${lerp(-200, 200, sh)}% 0`; shine.style.backgroundSize = '300% 100%'; shine.style.opacity = sh > 0 && sh < 1 ? 1 : 0;
    shine.textContent = 'BioManager'; shine.style.color = 'transparent';
    tag.render(t); foot.render(t);
  };
});

// ------------------------------------------------------------------ render
function render(t) {
  fxReset();
  renderBg(t);
  // the camera blends from one scene's to the next over the time they overlap
  let acc = null, prev = null;
  for (const s of SCENES) {
    const on = t >= s.t0 && t < s.t1;
    if (on !== s._on) { s.root.style.display = s.caps.style.display = on ? '' : 'none'; s._on = on; }
    if (!on) continue;
    cam.x = 0; cam.y = 0; cam.s = 1; cam.r = 0;
    s.render(t);
    const c = { x: cam.x, y: cam.y, s: cam.s, r: cam.r };
    if (!acc) acc = c;
    else { const w = E.io2(pr(t, s.t0, Math.max(s.t0 + 0.05, prev.t1))); for (const k in acc) acc[k] = lerp(acc[k], c[k], w); }
    prev = s;
  }
  if (acc) Object.assign(cam, acc);
  // captions belong to scenes; hide those whose scene is not playing
  for (const c of CAPS) if (t < c.o.t0 - 0.05 || t > c.o.t1 + 0.6) hide(c.e);
  const fl = Math.max(flash(t, 20.0, 0.9), flash(t, 26.02, 0.35, 0.3), flash(t, 44.0, 0.8), flash(t, 54.0, 0.6, 0.45), flash(t, 4.0, 0.25, 0.25));
  flashEl.style.opacity = fl.toFixed(3);
  applyCam(t);
  fxFinish();
}

window.FILM = { ready: false, duration: DUR, cues: CUES, render, W, H, LANG };
(async () => {
  const sprite = await fetch('/app/static/icons.svg').then(r => r.text());
  $('sprite').innerHTML = sprite.replace(/<\?xml[^>]*>/, '').replace(/<!--[\s\S]*?-->/g, '');
  await document.fonts.load('700 40px Inter'); await document.fonts.load('700 40px JBM'); await document.fonts.load('700 40px "Bradley Hand"').catch(() => {});
  await document.fonts.ready;
  await Promise.all([...document.images].map(i => i.complete ? 0 : new Promise(r => { i.onload = i.onerror = r; })));
  render(0);
  CUES.sort((a, b) => a.t - b.t);
  window.FILM.ready = true;
  const t0 = Q.get('t'); if (t0) render(+t0);
  if (Q.get('play')) { const st = performance.now() - (+(t0 || 0)) * 1000; const loop = () => { const t = ((performance.now() - st) / 1000) % DUR; render(t); requestAnimationFrame(loop); }; loop(); }
})();
