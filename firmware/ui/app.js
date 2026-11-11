// NetScope X1 UI.  No build step, no dependencies: it has to load from the
// device's own flash with no network.  Talks to the engine over /api.
const $ = (s, el = document) => el.querySelector(s);
const view = $('#view');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const api = async (path, body, method) => {
  const r = await fetch('/api/' + path, body === undefined ? { method: method || 'GET' }
    : { method: method || 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
};

const state = { info: {}, tools: [], session: {}, diagnosis: null, overall: null, sessionType: null,
  stack: [], tech: localStorage.getItem('tech') || '' };

const LABEL = { PASS: 'PASS', FAIL: 'FAIL', WARNING: 'WARNING', NOT_TESTED: 'NOT TESTED', RUNNING: 'TESTING' };
const chip = st => `<span class="chip ${st}">${LABEL[st] || st}</span>`;

const GLYPH = {
  cable: '<path d="M8 20h48v18l-8 8H16l-8-8z"/><path d="M20 20v-8m8 8v-8m8 8v-8m8 8v-8M32 46v10"/>',
  poe: '<path d="M36 6 16 36h14l-4 22 22-32H34z"/>',
  fiber: '<path d="M6 32h18M40 32h18"/><circle cx="32" cy="32" r="8"/><path d="M32 10v8M32 46v8M16 16l6 6M42 42l6 6M48 16l-6 6M22 42l-6 6"/>',
  network: '<circle cx="32" cy="12" r="6"/><circle cx="12" cy="52" r="6"/><circle cx="52" cy="52" r="6"/><path d="M32 18v14M12 46V32h40v14"/>',
  wifi: '<path d="M6 24c15-14 37-14 52 0M15 34c10-9 24-9 34 0M24 44c5-4 11-4 16 0"/><circle cx="32" cy="53" r="2"/>',
  discovery: '<circle cx="27" cy="27" r="17"/><path d="m40 40 16 16"/>',
  reports: '<path d="M14 6h26l12 12v40H14zM40 6v12h12M22 30h20M22 40h20M22 50h12"/>',
  settings: '<path d="M8 18h30m10 0h8M8 32h8m10 0h30M8 46h24m10 0h14"/><circle cx="43" cy="18" r="5"/><circle cx="21" cy="32" r="5"/><circle cx="37" cy="46" r="5"/>',
  auto: '<circle cx="32" cy="32" r="24"/><path d="m26 22 16 10-16 10z"/>',
};
const glyph = k => `<svg class="glyph" viewBox="0 0 64 64" aria-hidden="true">${GLYPH[k] || ''}</svg>`;
const row = (id, title, sub, opts = {}) =>
  `<button class="row ${opts.cls || ''}" data-go="${id}">${opts.glyph ? glyph(opts.glyph) : ''}<span class="t">${esc(title)}${sub ? `<span class="s">${esc(sub)}</span>` : ''}</span>${opts.right || ''}</button>`;

// ---------------------------------------------------------------- navigation
const screens = {};
function go(name, arg, replace) {
  if (!replace) state.stack.push([name, arg]);
  else state.stack[state.stack.length - 1] = [name, arg];
  setCtx(null);
  view.scrollTop = 0;
  screens[name](arg);
  focusFirst();
}
function back() {
  if (!$('#osk').hidden) return oskClose(false);
  if (!$('#modal').hidden) return modalClose(false);
  if (state.stack.length > 1) { state.stack.pop(); const [n, a] = state.stack.pop(); go(n, a); }
}
function home() { state.stack = []; go('home'); }
let ctxFn = null;
function setCtx(label, fn) { const b = $('#k-ctx'); b.hidden = !label; b.textContent = label || ''; ctxFn = fn; }
$('#k-back').onclick = back; $('#k-home').onclick = home; $('#k-ctx').onclick = () => ctxFn && ctxFn();

const focusables = () => [...(!$('#modal').hidden ? $('#modal') : view).querySelectorAll('button, input')].filter(e => !e.disabled);
function focusFirst() { const f = focusables()[0]; if (f) f.focus({ preventScroll: true }); }
// Physical keys arrive as keyboard events (the coprocessor feeds uinput):
// D-pad = arrows, OK = Enter, Back = Escape, Home = F1, context = F2.
document.addEventListener('keydown', e => {
  if (!$('#osk').hidden) { if (e.key === 'Escape') oskClose(false); return; }
  const typing = e.target.tagName === 'INPUT';
  if (e.key === 'Escape') { e.preventDefault(); back(); }
  else if (e.key === 'F1') { e.preventDefault(); home(); }
  else if (e.key === 'F2') { e.preventDefault(); ctxFn && ctxFn(); }
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || (!typing && (e.key === 'ArrowRight' || e.key === 'ArrowLeft'))) {
    e.preventDefault();
    const f = focusables(); if (!f.length) return;
    const i = f.indexOf(document.activeElement);
    const d = (e.key === 'ArrowDown' || e.key === 'ArrowRight') ? 1 : -1;
    const n = f[(i + d + f.length) % f.length]; n.focus(); n.scrollIntoView({ block: 'nearest' });
  }
});
view.addEventListener('click', e => {
  const b = e.target.closest('[data-go]');
  if (b) { const [n, a] = b.dataset.go.split(':'); go(n, a); }
});

// ---------------------------------------------------------------- modal + on-screen keyboard
let modalResolve = null;
function confirmBox(title, body, yes) {
  $('#modal').innerHTML = `<div class="card"><h3>${esc(title)}</h3><p>${esc(body)}</p>
    <div class="btns"><button class="btn" id="m-no">Cancel</button><button class="btn go" id="m-yes">${esc(yes)}</button></div></div>`;
  $('#modal').hidden = false;
  $('#m-no').onclick = () => modalClose(false); $('#m-yes').onclick = () => modalClose(true);
  $('#m-no').focus();
  return new Promise(r => { modalResolve = r; });
}
function modalClose(v) { $('#modal').hidden = true; if (modalResolve) modalResolve(v); modalResolve = null; focusFirst(); }

const OSK = [['1234567890', 'qwertyuiop', 'asdfghjkl-', 'zxcvbnm._/'], ['1234567890', 'QWERTYUIOP', 'ASDFGHJKL:', 'ZXCVBNM,@#']];
let oskTarget = null, oskShift = 0, oskVal = '';
function oskOpen(input) {
  oskTarget = input; oskVal = input.value; oskDraw(); $('#osk').hidden = false;
}
function oskDraw() {
  $('#osk').innerHTML = `<div class="echo">${esc(oskVal)}<span class="dim">|</span></div>` +
    OSK[oskShift].map(r => `<div class="r">${[...r].map(c => `<button data-c="${esc(c)}">${esc(c)}</button>`).join('')}</div>`).join('') +
    `<div class="r"><button class="w" data-a="shift">${oskShift ? 'abc' : 'ABC'}</button><button class="w" data-c=" ">space</button><button class="w" data-a="del">Delete</button><button class="w ok" data-a="ok">Done</button></div>`;
}
$('#osk').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.c !== undefined) oskVal += b.dataset.c;
  else if (b.dataset.a === 'del') oskVal = oskVal.slice(0, -1);
  else if (b.dataset.a === 'shift') oskShift ^= 1;
  else if (b.dataset.a === 'ok') return oskClose(true);
  oskDraw();
});
function oskClose(keep) {
  if (keep && oskTarget) { oskTarget.value = oskVal; oskTarget.dispatchEvent(new Event('change')); }
  $('#osk').hidden = true; oskTarget = null;
}
// Touch opens the on-screen keyboard; a real keyboard (desktop simulator) just types.
view.addEventListener('pointerdown', e => { if (e.target.tagName === 'INPUT' && e.pointerType !== 'mouse') { e.preventDefault(); oskOpen(e.target); } });
view.addEventListener('dblclick', e => { if (e.target.tagName === 'INPUT') oskOpen(e.target); });

// ---------------------------------------------------------------- jobs
async function runJob(tool, params, onUpdate) {
  const { id } = await api('jobs', { tool, params });
  for (;;) {
    const job = await api('jobs/' + id);
    if (onUpdate) onUpdate(job);
    if (job.state === 'done') return job.result;
    if (job.state === 'error') throw new Error(job.error);
    await new Promise(r => setTimeout(r, 250));
  }
}
function remember(result, type) {
  for (const r of result.results) state.session[r.test_id] = r;
  if (result.diagnosis) { state.diagnosis = result.diagnosis; state.overall = result.overall; }
  state.sessionType = type;
}

// ---------------------------------------------------------------- result rendering
const PAIR_COLOR = { 1: 'var(--w-orange)', 2: 'var(--w-orange)', 3: 'var(--w-green)', 6: 'var(--w-green)',
  4: 'var(--w-blue)', 5: 'var(--w-blue)', 7: 'var(--w-brown)', 8: 'var(--w-brown)' };
const STRIPED = { 1: 1, 3: 1, 5: 1, 7: 1 }; // white/colour conductors are drawn dashed

function wiremapSvg(w) {
  const y = p => 48 + (p - 1) * 46, X0 = 86, X1 = 584;
  let s = `<svg class="wiremap" viewBox="0 0 672 430" role="img" aria-label="Wiremap">
    <text x="20" y="22" class="dim">This end</text><text x="652" y="22" class="dim" text-anchor="end">${w.far_end === 'terminator' ? 'RT-1' + (w.terminator_id ? ' #' + w.terminator_id : '') : w.far_end === 'equipment' ? 'Equipment' : 'Far end'}</text>`;
  const shorts = (w.faults || []).filter(f => f.kind === 'short');
  for (let p = 1; p <= 8; p++) {
    const st = w.pin_status[p], to = w.mapping[p], col = PAIR_COLOR[p];
    const dash = STRIPED[p] ? 'stroke-dasharray="16 8"' : '';
    s += `<text x="20" y="${y(p) + 8}">${p}</text><circle cx="64" cy="${y(p)}" r="9" fill="${col}"/>`;
    if (w.far_end === 'equipment') {
      if (st === 'ok') s += `<path d="M${X0} ${y(p)}H${X1}" stroke="${col}" stroke-width="7" ${dash} fill="none"/>`;
      else s += `<path d="M${X0} ${y(p)}h150" stroke="${col}" stroke-width="7" ${dash} fill="none" opacity=".5"/><text x="${X0 + 166}" y="${y(p) + 8}" class="dim">no continuity</text>`;
    } else if (to) {
      const bad = to !== p && st !== 'crossover';
      s += `<path d="M${X0} ${y(p)}C${X0 + 200} ${y(p)} ${X1 - 200} ${y(to)} ${X1} ${y(to)}" stroke="${bad ? 'var(--fail)' : col}" stroke-width="7" ${dash} fill="none"/>`;
    } else if (st === 'short') {
      s += `<path d="M${X0} ${y(p)}h120" stroke="var(--fail)" stroke-width="7" fill="none"/>`;
    } else if (st === 'unverified') {
      s += `<path d="M${X0} ${y(p)}h300" stroke="${col}" stroke-width="7" ${dash} fill="none" opacity=".45"/>`;
    } else {
      s += `<path d="M${X0} ${y(p)}h200" stroke="${col}" stroke-width="7" ${dash} fill="none" opacity=".5"/><path d="m${X0 + 208} ${y(p) - 12} 24 24m0-24-24 24" stroke="var(--fail)" stroke-width="6"/><text x="${X0 + 248}" y="${y(p) + 8}">open</text>`;
    }
    if (w.far_end !== 'equipment') s += `<circle cx="608" cy="${y(p)}" r="9" fill="${PAIR_COLOR[p]}"/><text x="652" y="${y(p) + 8}" text-anchor="end">${p}</text>`;
  }
  for (const f of shorts) {
    const [a, b] = f.pins;
    s += `<path d="M${X0 + 120} ${y(a)}V${y(b)}" stroke="var(--fail)" stroke-width="7"/><text x="${X0 + 136}" y="${(y(a) + y(b)) / 2 + 8}">short ${a}-${b}</text>`;
  }
  if (w.far_end === 'equipment') s += `<rect x="${X1}" y="30" width="72" height="360" rx="6" fill="none" stroke="var(--dim)" stroke-width="3"/>`;
  return s + '</svg>';
}

function chanSvg(channels) {
  const bands = [['2.4', '2.4 GHz'], ['5', '5 GHz']];
  let s = '<svg class="chan" viewBox="0 0 672 500" role="img" aria-label="Channel comparison">';
  bands.forEach(([b, name], bi) => {
    const list = channels.filter(c => c.band === b), top = 34 + bi * 250, H = 150;
    s += `<text x="0" y="${top - 8}" class="dim">${name}</text><path d="M0 ${top + H}H672" stroke="var(--rule)" stroke-width="2"/>`;
    const w = Math.min(160, 656 / Math.max(list.length, 1));
    list.forEach((c, i) => {
      const h = Math.max(8, (Math.min(Math.max(c.strongest_rssi, -90), -30) + 90) / 60 * H), x = 8 + i * w;
      const col = c.util_pct >= 50 ? 'var(--warn)' : 'var(--w-blue)';
      s += `<rect x="${x}" y="${top + H - h}" width="${w - 12}" height="${h}" rx="4" fill="${col}"/>
        <text x="${x + (w - 12) / 2}" y="${top + H - h - 8}" text-anchor="middle">${c.strongest_rssi}</text>
        <text x="${x + (w - 12) / 2}" y="${top + H + 28}" text-anchor="middle">ch ${c.channel}</text>
        <text x="${x + (w - 12) / 2}" y="${top + H + 54}" text-anchor="middle" class="dim">${c.aps} AP${c.aps > 1 ? 's' : ''}${c.util_pct != null ? ' ' + c.util_pct + '%' : ''}</text>`;
    });
    if (!list.length) s += `<text x="8" y="${top + 60}" class="dim">No networks seen</text>`;
  });
  return s + '</svg>';
}

const table = (head, rows) => `<table><tr>${head.map(h => `<th>${esc(h)}</th>`).join('')}</tr>${rows.map(r => `<tr>${r.map(c => `<td>${esc(c ?? '-')}</td>`).join('')}</tr>`).join('')}</table>`;

function measurements(r) {
  const m = r.measurements || {}; let h = '';
  if (m.wiremap) h += wiremapSvg(m.wiremap);
  if (m.length_m != null) h += `<p>Length about <b>${m.length_m} m</b> (${(m.length_m * 3.281).toFixed(0)} ft)</p>`;
  if (m.tdr) h += table(['Pair', 'TDR result', 'Distance'], m.tdr.map(t => [t.pins, t.meaning || (t.code === 'ok' ? 'terminated' : t.code.replace('_', ' ')), t.length_m != null ? t.length_m + ' m' : '']));
  if (m.aps) h += chanSvg(m.channels) + table(['Network', 'Ch', 'dBm', 'Security'], m.aps.map(a => [a.ssid || '(hidden)', a.channel, a.rssi, a.security]));
  if (m.hops) h += table(['Hop', 'Address', 'ms'], m.hops.map(x => [x.hop, x.address || '* no reply', x.rtt_ms]));
  if (m.entries) h += table(['Address', 'MAC', 'Vendor'], m.entries.map(x => [x.address, x.mac, x.vendor]));
  if (m.neighbors && m.neighbors.length) { const n = m.neighbors[0]; h += kv({ Switch: n.system_name, Port: n.port_id, 'Port description': n.port_description, VLAN: n.vlan, Management: n.mgmt_address, 'PoE capable': n.poe_mdi == null ? null : (n.poe_mdi ? 'yes' : 'no') }); }
  if (m.load_test) h += kv({ 'Load requested': m.load_test.requested_w + ' W', 'Voltage under load': m.load_test.voltage_v + ' V', Current: Math.round(m.load_test.current_a * 1000) + ' mA', Delivered: m.load_test.power_w + ' W' });
  const skip = new Set(['wiremap', 'tdr', 'aps', 'channels', 'hops', 'entries', 'neighbors', 'load_test', 'crosstalk_db', 'port_voltage', 'roam_events', 'partner_modes', 'ping', 'http', 'length_m', 'present', 'ddm', 'los']);
  const flat = {};
  for (const [k, v] of Object.entries(m)) if (!skip.has(k) && v !== null && typeof v !== 'object') flat[k.replace(/_/g, ' ')] = v;
  for (const [k, v] of Object.entries(m)) if (!skip.has(k) && Array.isArray(v) && v.every(x => typeof x !== 'object')) flat[k.replace(/_/g, ' ')] = v.join(', ');
  return h + (Object.keys(flat).length ? kv(flat) : '');
}
const kv = o => `<table class="kv">${Object.entries(o).filter(([, v]) => v != null && v !== '').map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>`;

function resultCard(r, detail = true) {
  return `<div class="card edge-${r.status}"><h3>${esc(r.title)} ${chip(r.status)}</h3><p>${esc(r.summary)}</p>
    ${detail ? measurements(r) : ''}
    ${r.findings.length ? `<ul>${r.findings.map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : ''}
    ${r.recommendations.length ? `<h2>What to do</h2><ul class="fix">${r.recommendations.map(f => `<li>${esc(f)}</li>`).join('')}</ul>` : ''}</div>`;
}
function diagnosisCard(d) {
  const list = (t, a) => a && a.length ? `<h2>${t}</h2><ul>${a.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '';
  return `<div class="card"><h3>${esc(d.headline)}</h3><p>${esc(d.explanation)}</p>
    ${list('Likely causes', d.likely_causes)}${d.next_steps && d.next_steps.length ? `<h2>What to do</h2><ul class="fix">${d.next_steps.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}${list('Also noted', d.notes)}</div>`;
}
const busy = t => `<div class="card"><h3>${esc(t)} <span class="spin"></span></h3><p class="dim">Testing. Keep the cable connected.</p></div>`;
const failBox = e => `<div class="card edge-FAIL"><h3>Test did not run</h3><p>${esc(e.message)}</p><p class="dim">Check the connection and run it again.</p></div>`;

// ---------------------------------------------------------------- screens
screens.home = () => {
  view.innerHTML = `<h1>NetScope X1</h1>
    ${row('auto', 'Auto Diagnose', 'Connect a cable to the test port, then start', { cls: 'primary', glyph: 'auto' })}
    ${row('tool:cable', 'Cable Test', 'Wiremap, length, distance to fault', { glyph: 'cable' })}
    ${row('poe', 'PoE Analyzer', 'Standard, class, voltage, load test', { glyph: 'poe' })}
    ${row('network', 'Network Diagnostics', 'Link, DHCP, ping, DNS, traceroute', { glyph: 'network' })}
    ${row('tool:fiber', 'Fiber Test', 'SFP+ module, light level, link', { glyph: 'fiber' })}
    ${row('wifi', 'Wi-Fi Analyzer', 'Networks, channels, signal', { glyph: 'wifi' })}
    ${row('discovery', 'Device Discovery', 'Switch port, VLAN, neighbours', { glyph: 'discovery' })}
    ${row('reports', 'Test Reports', Object.keys(state.session).length ? Object.keys(state.session).length + ' unsaved result(s)' : 'Saved reports and export', { glyph: 'reports' })}
    ${row('settings', 'Settings', '', { glyph: 'settings' })}`;
};

screens.auto = async () => {
  state.session = {}; state.diagnosis = null;
  const draw = job => {
    const done = Object.fromEntries(job.steps.map(s => [s.test_id, s]));
    view.innerHTML = `<h1>Auto Diagnose</h1><div class="card">${job.plan.map(p => {
      const r = done[p.id], st = r ? r.status : job.current === p.id ? 'RUNNING' : null;
      return `<div class="step"><span class="n">${esc(p.title)}<span class="d">${esc(r ? r.summary : '')}</span></span>${st ? chip(st) : ''}</div>`;
    }).join('')}</div>`;
  };
  view.innerHTML = busy('Auto Diagnose');
  try {
    const res = await runJob('autodiag', {}, draw);
    remember(res, 'Auto Diagnose');
    view.innerHTML = `<h1>Auto Diagnose ${chip(res.overall)}</h1>${diagnosisCard(res.diagnosis)}
      <h2>Steps</h2>${res.results.map((r, i) => `<button class="row compact" data-go="detail:${r.test_id}"><span class="t">${esc(r.title)}<span class="s">${esc(r.summary)}</span></span>${chip(r.status)}</button>`).join('')}
      <div class="btns"><button class="btn" id="again">Run again</button>${state.info.ai_configured ? '<button class="btn" id="ai">Ask AI</button>' : ''}</div><div id="aiout"></div>`;
    $('#again').onclick = () => go('auto', null, true);
    if ($('#ai')) $('#ai').onclick = askAi;
    setCtx('Save report', () => go('save'));
    focusFirst();
  } catch (e) { view.innerHTML = `<h1>Auto Diagnose</h1>${failBox(e)}`; }
};
async function askAi() {
  if (!await confirmBox('Send results to cloud AI?', 'Test results leave this device. Addresses and device names are masked unless redaction is turned off.', 'Send')) return;
  $('#aiout').innerHTML = busy('Cloud analysis');
  try {
    const a = await api('assistant', { results: Object.values(state.session), diagnosis: state.diagnosis, cloud: true });
    $('#aiout').innerHTML = `<div class="card"><h3>Cloud AI analysis</h3><p style="white-space:pre-wrap">${esc(a.cloud || a.cloud_error)}</p><p class="dim small">AI output can be wrong. The diagnosis above comes from on-device rules.</p></div>`;
  } catch (e) { $('#aiout').innerHTML = failBox(e); }
}
screens.detail = id => { view.innerHTML = `<h1>${esc(state.session[id].title)}</h1>${resultCard(state.session[id])}`; };

async function runTool(id, params, type) {
  const t = state.tools.find(x => x.id === id);
  if (t.disruptive || params.authorized) {
    const ok = await confirmBox('Run this test?', id === 'poe' ? 'The load test draws real power from the switch and counts against its PoE budget.' : 'This test puts heavy traffic on the network or records other devices\' traffic. Only run it with the network owner\'s permission.', 'Run test');
    if (!ok) return;
    params.authorized = true;
  }
  const out = $('#out'); out.innerHTML = busy(t.title);
  try { const res = await runJob(id, params); remember(res, type || t.title); out.innerHTML = res.results.map(r => resultCard(r)).join(''); setCtx('Save report', () => go('save')); }
  catch (e) { out.innerHTML = failBox(e); }
}
function form(t) {
  return t.params.map(p => `<label for="p-${p.name}">${esc(p.name.replace(/_/g, ' '))}</label><input id="p-${p.name}" data-p="${p.name}" value="${esc(p.default)}" ${p.type === 'number' ? 'inputmode="decimal"' : ''} autocomplete="off">`).join('');
}
const readForm = () => Object.fromEntries([...view.querySelectorAll('[data-p]')].map(i => [i.dataset.p, i.value]));

screens.tool = id => {
  const t = state.tools.find(x => x.id === id);
  view.innerHTML = `<h1>${esc(t.title)}</h1>${form(t)}<div class="btns"><button class="btn go" id="run">Start test</button></div><div id="out"></div>`;
  $('#run').onclick = () => runTool(id, readForm());
  if (!t.params.length && !t.disruptive) runTool(id, {});
};
screens.poe = () => {
  view.innerHTML = `<h1>PoE Analyzer</h1><div class="btns"><button class="btn go" id="run">Identify PoE</button><button class="btn" id="load">Load test</button></div>
    <label for="p-load">Load test power (W), capped at the allocated class</label><input id="p-load" value="13" inputmode="decimal"><div id="out"></div>`;
  $('#run').onclick = () => runTool('poe', {});
  $('#load').onclick = () => runTool('poe', { load_w: $('#p-load').value, authorized: true });
  runTool('poe', {});
};
screens.network = () => {
  const ids = ['link', 'dhcp', 'ping', 'dns', 'traceroute', 'http', 'static', 'throughput', 'capture'];
  view.innerHTML = `<h1>Network Diagnostics</h1>${row('auto', 'Auto Diagnose', 'Cable to internet in one pass', { cls: 'primary compact' })}` +
    ids.map(i => { const t = state.tools.find(x => x.id === i); return row('tool:' + i, t.title, t.disruptive ? 'Asks before running' : '', { cls: 'compact' }); }).join('');
};
screens.wifi = () => {
  view.innerHTML = `<h1>Wi-Fi Analyzer</h1><div class="btns"><button class="btn go" id="scan">Scan networks</button><button class="btn" id="conn">Connection</button></div><div id="out"></div>`;
  $('#scan').onclick = () => runTool('wifi_scan', {}, 'Wi-Fi'); $('#conn').onclick = () => runTool('wifi_status', {}, 'Wi-Fi');
  runTool('wifi_scan', {}, 'Wi-Fi');
};
screens.discovery = async () => {
  view.innerHTML = `<h1>Device Discovery</h1><div id="out"></div><div id="out2"></div>`;
  await runTool('neighbors', {}, 'Device Discovery');
  const keep = $('#out').innerHTML; await runTool('arp', {}, 'Device Discovery');
  $('#out').innerHTML = keep + $('#out').innerHTML;
};

screens.reports = async () => {
  const n = Object.keys(state.session).length;
  view.innerHTML = `<h1>Test Reports</h1>${n ? row('save', 'Save current results', n + ' result(s) from ' + (state.sessionType || 'this session'), { cls: 'primary compact' }) : '<p class="dim">Run a test, then save it here with a work-order number.</p>'}<div id="list"></div>`;
  try {
    const list = await api('reports');
    $('#list').innerHTML = list.length ? '<h2>Saved</h2>' + list.map(r => `<button class="row compact" data-go="report:${r.id}"><span class="t">${esc(r.job || 'No job number')}<span class="s">${esc(r.test_type)}, ${esc((r.created_iso || '').slice(0, 16).replace('T', ' '))}${r.provenance.includes('simulated') ? ', simulated' : ''}</span></span>${chip(r.overall)}</button>`).join('') : '';
  } catch (e) { $('#list').innerHTML = failBox(e); }
  focusFirst();
};
screens.save = () => {
  view.innerHTML = `<h1>Save report</h1><label for="job">Job or work-order number</label><input id="job" autocomplete="off">
    <label for="tech">Technician</label><input id="tech" value="${esc(state.tech)}" autocomplete="off">
    <label for="notes">Notes</label><input id="notes" autocomplete="off">
    <div class="btns"><button class="btn go" id="do">Save report</button></div><div id="out"></div>`;
  $('#do').onclick = async () => {
    state.tech = $('#tech').value; try { localStorage.setItem('tech', state.tech); } catch (e) { /* storage unavailable */ }
    try {
      const rep = await api('reports', { job: $('#job').value, technician: state.tech, notes: $('#notes').value,
        test_type: state.sessionType || 'Test', results: Object.values(state.session), diagnosis: state.diagnosis, overall: state.diagnosis ? state.overall : undefined });
      state.session = {}; state.diagnosis = null; go('report', rep.id, true);
    } catch (e) { $('#out').innerHTML = failBox(e); }
  };
};
screens.report = async id => {
  view.innerHTML = busy('Report');
  try {
    const r = await api('reports/' + id);
    view.innerHTML = `<h1>${esc(r.job || 'Report')} ${chip(r.overall)}</h1>
      ${kv({ Report: r.id, Date: r.created_iso.slice(0, 16).replace('T', ' '), Technician: r.technician, 'Test type': r.test_type, Device: r.device.serial, 'Data source': r.provenance.join(', '), Notes: r.notes })}
      <h2>Export</h2><div class="btns">${['pdf', 'csv', 'json'].map(f => `<button class="btn" data-x="${f}">${f.toUpperCase()}</button>`).join('')}</div>
      <p class="dim small">On the device, exports are written to USB storage. In the simulator they download.</p>
      ${r.diagnosis && r.diagnosis.headline ? diagnosisCard(r.diagnosis) : ''}${r.results.map(x => resultCard(x, false)).join('')}
      <div class="btns"><button class="btn danger" id="del">Delete report</button></div>`;
    view.querySelectorAll('[data-x]').forEach(b => b.onclick = () => { location.href = `/api/reports/${id}/export.${b.dataset.x}`; });
    $('#del').onclick = async () => { if (await confirmBox('Delete this report?', 'It is removed from the device. Exported copies are not affected.', 'Delete report')) { await api('reports/' + id, undefined, 'DELETE'); back(); } };
  } catch (e) { view.innerHTML = failBox(e); }
  focusFirst();
};
screens.settings = async () => {
  const i = state.info, b = i.battery, sc = await api('sim/scenarios').catch(() => ({ scenarios: [] }));
  view.innerHTML = `<h1>Settings</h1><div class="card"><h3>Device</h3>${kv({ Model: i.device.model, Serial: i.device.serial, Hardware: i.device.hw_rev, Firmware: i.version, 'Measurement source': i.provenance, 'Cloud AI': i.ai_configured ? 'configured (asks before sending)' : 'off - local rules only' })}</div>
    ${b ? `<div class="card"><h3>Battery</h3>${kv({ Charge: b.percent + '%', Health: b.health_pct + '%', Cycles: b.cycles, Temperature: b.temp_c + ' C', Voltage: b.voltage_v + ' V', 'Time remaining': b.time_to_empty_min != null ? Math.floor(b.time_to_empty_min / 60) + ' h ' + b.time_to_empty_min % 60 + ' min' : null })}</div>` : ''}
    ${sc.scenarios.length ? `<h2>Simulator scenario</h2>${sc.scenarios.map(s => `<button class="row compact" data-sc="${s.id}"><span class="t">${esc(s.title)}</span>${s.id === sc.current ? chip('PASS').replace('PASS<', 'ACTIVE<') : ''}</button>`).join('')}` : ''}`;
  view.querySelectorAll('[data-sc]').forEach(el => el.onclick = async () => { await api('sim/scenario', { id: el.dataset.sc }); state.session = {}; await refreshInfo(); go('settings', null, true); });
  focusFirst();
};

// ---------------------------------------------------------------- boot
async function refreshInfo() {
  try {
    state.info = await api('info');
    $('#sim').hidden = state.info.provenance !== 'simulated';
    const b = state.info.battery;
    $('#batt').textContent = b ? `${b.charging ? 'Charging ' : ''}${b.percent}%` : '';
  } catch (e) { $('#batt').textContent = 'Engine offline'; }
  $('#clock').textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
function fit() {
  const s = Math.min(innerWidth / 720, innerHeight / 1280, 1);
  $('#frame').style.transform = `translate(-50%, -50%) scale(${s})`;
}
addEventListener('resize', fit); fit();
(async () => {
  await refreshInfo();
  try { state.tools = await api('tools'); home(); }
  catch (e) { view.innerHTML = failBox(new Error('The diagnostic engine is not responding.')); }
  setInterval(refreshInfo, 15000);
})();
