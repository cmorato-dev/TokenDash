const $ = (selector, root = document) => root.querySelector(selector);
// Texts come from Django's catalog (/<language>/jsi18n/); without it the page stays in English.
const _ = window.gettext || (text => text);
const format = (text, values) => text.replace(/%\((\w+)\)s/g, (match, key) => values[key]);
const lang = document.documentElement.lang || 'en';
const timeZone = document.body.dataset.timezone;
const fmt = new Intl.DateTimeFormat(lang, { dateStyle: 'short', timeStyle: 'short', timeZone });
const percent = value => value === null ? '—' : `${Number(value).toLocaleString(lang, { maximumFractionDigits: 1 })}%`;
// The same day format as the server's reset sentences: «Oct 27» in English, «27/10» in Spanish.
const renewDay = new Intl.DateTimeFormat(lang, { day: 'numeric', month: lang === 'es' ? 'numeric' : 'short', timeZone });
const renewHour = new Intl.DateTimeFormat(lang, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone });
// «You have used 26% of the limit this week. It renews on Oct 27 at 07:41.»
const quotaPeriods = { session: _('in this 5-hour session'), weekly: _('this week'), weekly_all: _('this week'), weekly_sonnet: _('this week with Sonnet'), monthly: _('this month') };
function quotaSentence(quota) {
  const period = quotaPeriods[quota.key] || format(_('in “%(label)s”'), { label: quota.label });
  const used = percent(quota.used_percent);
  // The window restarted after this reading: the value is the last known one, not the current one.
  if (quota.window_reset) return format(_('You had used %(percent)s of the limit %(period)s. It has already renewed.'), { percent: used, period });
  const when = new Date(quota.resets_at);
  const renews = quota.resets_at && !Number.isNaN(when.getTime())
    ? ` ${format(_('It renews on %(day)s at %(time)s.'), { day: renewDay.format(when), time: renewHour.format(when) })}` : '';
  return `${format(_('You have used %(percent)s of the limit %(period)s.'), { percent: used, period })}${renews}`;
}
// More than half of a limit used turns it yellow; more than 80 %, red. A window that has
// already restarted keeps its old value, so it is not coloured.
const levelOf = (used, reset) => used === null || used === undefined || reset ? 'ok' : used > 80 ? 'critical' : used > 50 ? 'warning' : 'ok';
const levelNotes = { warning: _('You are past half of the limit.'), critical: _('Little left: you are past 80% of the limit.') };
// The whole limit used: say so plainly instead of "little left".
const levelNote = (level, used) => level === 'critical' && used >= 100 ? _('Out of tokens: you have used 100% of the limit. Wait until it renews.') : levelNotes[level] || '';
let pending = false;
let historyVersion = null;
// Home Assistant modules carry their read-only key in the URL fragment (#key=…),
// which the browser never sends to the server; the API receives it as a header.
// #clave=… is the name used by the first, Spanish-only addresses.
const embedded = 'embed' in document.body.dataset;
const fragment = new URLSearchParams(window.location.hash.slice(1));
const embedKey = fragment.get('key') || fragment.get('clave');
const showError = message => { const feedback = $('#feedback'); if (feedback) feedback.textContent = message; };
async function getJSON(url, options = {}) {
  if (embedded && !embedKey) throw new Error(_('The key is missing: add #key=… at the end of the module address.'));
  // The API has a single address for every language: ask for the page's one.
  const auth = embedKey ? { Authorization: `Bearer ${embedKey}` } : {};
  let response;
  try {
    response = await fetch(url, { ...options, headers: { Accept: 'application/json', 'Accept-Language': lang, ...auth, ...options.headers } });
  } catch {
    throw new Error(_('No connection with the TokenDash server. It will be retried in a few seconds.'));
  }
  if (response.redirected) { window.location.href = response.url; throw new Error(_('Sign in again.')); }
  // While the server restarts or stops, the reply is an HTML error page instead of JSON.
  if (!(response.headers.get('content-type') || '').includes('application/json')) {
    throw new Error(format(_('The TokenDash server did not answer properly (error %(status)s). It may be restarting; it will be retried in a few seconds.'), { status: response.status }));
  }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || _('The request could not be completed.'));
  return data;
}
async function refreshStatus() {
  const data = await getJSON('/api/status/');
  const version = JSON.stringify(data.providers.map(p => [p.provider, p.last_success_at]));
  const historyChanged = historyVersion !== null && version !== historyVersion;
  historyVersion = version;
  pending = false;
  data.providers.forEach(provider => {
    const card = $(`[data-provider="${provider.provider}"]`);
    if (!card) return;
    $('.available', card).textContent = percent(provider.available_percent);
    $('.used', card).textContent = percent(provider.used_percent);
    const gauge = $('.gauge', card);
    gauge.style.setProperty('--available', `${provider.available_percent ?? 0}%`);
    if (provider.available_percent !== null) gauge.setAttribute('aria-valuenow', provider.available_percent);
    else gauge.removeAttribute('aria-valuenow');
    $('.quota-label', card).textContent = provider.quota_label || _('No confirmed reading');
    $('.state', card).textContent = provider.refreshing ? _('Refreshing…') : provider.state_label;
    $('.state', card).classList.toggle('success', provider.state === 'ok');
    $('.updated', card).textContent = provider.last_success_at ? fmt.format(new Date(provider.last_success_at)) : _('Never');
    $('.attempt', card).textContent = provider.last_attempt_at ? format(_('Last attempt: %(when)s'), { when: fmt.format(new Date(provider.last_attempt_at)) }) : '';
    $('.error', card).textContent = provider.last_error;
    $('.hint', card).textContent = provider.hint || '';
    const resetText = quota => quota.window_reset ? _('The window has restarted since this reading') : (quota.reset_text || '');
    $('.reset', card).textContent = provider.quotas[0] ? resetText(provider.quotas[0]) : '';
    const level = levelOf(provider.used_percent, provider.quotas[0]?.window_reset);
    card.dataset.level = level;
    const note = $('.level-note', card);
    note.dataset.level = level;
    note.textContent = levelNote(level, provider.used_percent);
    const extra = $('.extra-quotas', card);
    extra.replaceChildren();
    provider.quotas.slice(1).forEach(quota => {
      const line = document.createElement('p');
      line.textContent = quotaSentence(quota);
      // A thin bar with the share used, coloured like the gauge.
      const bar = document.createElement('div');
      bar.className = 'quota-bar';
      bar.dataset.level = levelOf(quota.used_percent, quota.window_reset);
      bar.classList.toggle('stale', Boolean(quota.window_reset));
      bar.setAttribute('aria-hidden', 'true');
      const fill = document.createElement('span');
      fill.style.width = `${Math.min(100, Math.max(0, Number(quota.used_percent) || 0))}%`;
      bar.append(fill);
      const row = document.createElement('div');
      row.append(line, bar);
      extra.append(row);
    });
    const button = $('.refresh', card);
    if (button) { button.hidden = !provider.can_refresh; button.disabled = provider.refreshing; }
    pending ||= provider.refreshing;
  });
  if (historyChanged) await reloadHistory();
}
const palette = ['#34d399', '#fb923c', '#60a5fa', '#c084fc', '#facc15', '#f472b6'];
// Fixed colour per provider and window, so a series keeps its colour when another one has no data.
const seriesColors = { 'chatgpt:session': '#34d399', 'chatgpt:weekly': '#60a5fa', 'claude:session': '#fb923c', 'claude:weekly_all': '#c084fc' };
const quotaNames = { session: _('session / 5 h'), weekly: _('week'), weekly_all: _('week'), weekly_sonnet: _('week · Sonnet'), monthly: _('month') };
// Five-hour windows are drawn solid; weekly and monthly ones dashed, with hollow points.
const dashFor = quota => quota === 'session' ? null : '9 6';
// How each period is grouped and how its axis is labelled.
const granularityNames = { day: _('Daily average'), week: _('Weekly average'), month: _('Monthly average'), year: _('Yearly average') };
function axisLabel(label, granularity) {
  if (granularity === 'year') return label.slice(0, 4);
  if (granularity === 'month') return label.slice(0, 7);
  if (granularity === 'week') return format(_('wk %(date)s'), { date: shortDay(label) });
  return shortDay(label);
}
// «Oct 27» or «27/10» from an ISO date (the axis has no room for the year), and the long form.
const atNoon = label => new Date(`${label}T12:00:00Z`);
const shortDay = label => new Intl.DateTimeFormat(lang, { day: 'numeric', month: lang === 'es' ? 'numeric' : 'short', timeZone: 'UTC' }).format(atNoon(label));
const longDay = label => new Intl.DateTimeFormat(lang, { dateStyle: 'medium', timeZone: 'UTC' }).format(atNoon(label));
function bucketName(label, granularity) {
  if (granularity === 'day') return longDay(label);
  if (granularity === 'week') return format(_('week of %(date)s'), { date: longDay(label) });
  if (granularity === 'month') return new Intl.DateTimeFormat(lang, { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(atNoon(label));
  return label.slice(0, 4);
}
function svgNode(tag, attrs, text) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  if (text !== undefined) node.textContent = text;
  return node;
}
async function loadHistory() {
  showError('');
  const days = $('#history-days').value;
  const data = await getJSON(`/api/history/?days=${days}`);
  if ($('#history-days').value !== days) return;
  const root = $('#history'), legend = $('#history-legend');
  root.replaceChildren(); legend.replaceChildren();
  const granularity = data.granularity || 'day';
  const detailed = granularity === 'observation';
  const note = $('#history-note');
  if (note) note.textContent = detailed
    ? _('Each point is a recorded reading, with its time. No daily averages or estimated resets. Gaps longer than 24 hours are left blank.')
    : format(_('%(average)s of the percentage observed per quota.'), { average: granularityNames[granularity] || granularityNames.day });
  if (!data.series.length) {
    const empty = document.createElement('p');
    empty.className = 'empty'; empty.textContent = _('The history will appear after the first confirmed reading.');
    root.append(empty); return;
  }
  // Use the real width so labels keep their size on phones.
  const W = Math.max(300, root.clientWidth || 1000);
  const svg = svgNode('svg', { viewBox: `0 0 ${W} 280`, role: 'img', 'aria-label': _('Usage, from 0 to 100 percent') });
  [0, 25, 50, 75, 100].forEach(value => {
    const y = 220 - value * 2;
    svg.append(svgNode('line', { x1: 48, x2: W - 25, y1: y, y2: y, stroke: '#263449', 'stroke-dasharray': '4 6' }));
    svg.append(svgNode('text', { x: 0, y: y + 4, fill: '#8190a6', 'font-size': 12 }, `${value}%`));
  });
  const start = Date.parse(data.start_at), end = Date.parse(data.end_at);
  const xTime = at => 48 + (Date.parse(at) - start) * (W - 73) / Math.max(1, end - start);
  const xAt = i => 48 + i * (W - 73) / Math.max(1, (data.labels?.length || 0) - 1);
  if (detailed) {
    const hour = 3600000, step = Number(days) === 1 ? 3 : Number(days) === 7 ? 6 : 24;
    const labelEvery = Math.max(1, Math.ceil(data.day_boundaries.length / Math.max(2, Math.floor((W - 73) / 80))));
    let lastHourLabel = -Infinity;
    data.day_boundaries.forEach((boundary, index) => {
      const midnight = Date.parse(boundary), x = xTime(boundary);
      if (midnight >= start && midnight <= end) {
        svg.append(svgNode('line', { class: 'day-boundary', x1: x, x2: x, y1: 20, y2: 225, stroke: '#42526a' }));
        if (index % labelEvery === 0) svg.append(svgNode('text', { x, y: 266, fill: '#a8b8cf', 'text-anchor': 'middle', 'font-size': 12 }, renewDay.format(new Date(boundary))));
      }
      // Absolute hours preserve the two occurrences of an hour when DST ends.
      for (let at = midnight; at < midnight + 25 * hour && at <= end; at += step * hour) {
        if (at < start || (index + 1 < data.day_boundaries.length && at >= Date.parse(data.day_boundaries[index + 1]))) continue;
        const tickX = xTime(new Date(at).toISOString());
        svg.append(svgNode('line', { class: 'hour-tick', x1: tickX, x2: tickX, y1: 220, y2: 226, stroke: '#8190a6' }));
        if (step < 24) {
          svg.append(svgNode('line', { x1: tickX, x2: tickX, y1: 20, y2: 220, stroke: '#263449', 'stroke-dasharray': '2 7' }));
          if (tickX - lastHourLabel >= 62 && tickX < W - 40) {
            svg.append(svgNode('text', { x: tickX, y: 244, fill: '#8190a6', 'text-anchor': 'middle', 'font-size': 11 }, renewHour.format(new Date(at))));
            lastHourLabel = tickX;
          }
        }
      }
    });
  }
  data.series.forEach((series, idx) => {
    const color = seriesColors[`${series.provider}:${series.quota}`] || palette[idx % palette.length];
    const dash = dashFor(series.quota);
    let path = '', connected = false, previousAt = null;
    const points = [];
    const readings = detailed ? series.points : series.values.map((used, index) => ({ used, at: data.labels[index] }));
    readings.forEach(({ used: value, at }, index) => {
      if (value === null) { connected = false; return; }
      const x = detailed ? xTime(at) : xAt(index), y = 220 - value * 2;
      if (detailed && previousAt !== null && Date.parse(at) - previousAt > 86400000) connected = false;
      path += `${connected ? 'L' : 'M'}${x},${y} `; connected = true;
      previousAt = Date.parse(at);
      const r = detailed ? 2 : 4;
      const point = svgNode('circle', dash ? { cx: x, cy: y, r, fill: '#111b2c', stroke: color, 'stroke-width': 1.5 } : { cx: x, cy: y, r, fill: color });
      point.append(svgNode('title', {}, `${series.provider === 'chatgpt' ? 'ChatGPT' : 'Claude'} · ${quotaNames[series.quota] || series.quota} · ${detailed ? fmt.format(new Date(at)) : bucketName(at, granularity)}: ${percent(value)}`));
      points.push(point);
    });
    svg.append(svgNode('path', { d: path, stroke: color, 'stroke-width': 2.5, fill: 'none', ...(dash && { 'stroke-dasharray': dash }) }));
    points.forEach(point => svg.append(point));
    const item = document.createElement('span'); item.style.color = color;
    item.className = 'flex items-center gap-2';
    const swatch = svgNode('svg', { width: 26, height: 10, 'aria-hidden': 'true' });
    swatch.append(svgNode('line', { x1: 1, x2: 25, y1: 5, y2: 5, stroke: color, 'stroke-width': 2.5, ...(dash && { 'stroke-dasharray': '6 4' }) }));
    item.append(swatch, `${series.provider === 'chatgpt' ? 'ChatGPT' : 'Claude'} · ${quotaNames[series.quota] || series.quota}`); legend.append(item);
  });
  const every = Math.ceil((data.labels?.length || 0) / Math.max(2, Math.floor((W - 73) / 70)));
  (data.labels || []).forEach((label, index) => {
    if (index % every !== 0 && index !== data.labels.length - 1) return;
    svg.append(svgNode('text', { x: xAt(index), y: 250, fill: '#8190a6', 'text-anchor': 'middle', 'font-size': 12 }, axisLabel(label, granularity)));
  });
  root.append(svg);
}
document.querySelectorAll('.refresh').forEach(button => button.addEventListener('click', async () => {
  button.disabled = true;
  try {
    const card = button.closest('[data-provider]');
    const data = await getJSON(card.dataset.refreshUrl, { method: 'POST', headers: { 'X-CSRFToken': $('[name=csrfmiddlewaretoken]').value } });
    showError(data.message);
    await refreshStatus();
  } catch (error) { showError(error.message); button.disabled = false; }
}));
// Each page may hold the cards, the chart or both (a Home Assistant module holds one).
const hasCards = Boolean($('[data-provider]')), periodSelect = $('#history-days');
const reloadHistory = () => periodSelect ? loadHistory().catch(e => showError(e.message)) : Promise.resolve();
if (periodSelect) {
  // A module can open on another period: /en/ha/chart/?days=30#key=… (?dias= in the first addresses).
  const query = new URLSearchParams(window.location.search);
  const days = query.get('days') || query.get('dias');
  if ([...periodSelect.options].some(option => option.value === days)) periodSelect.value = days;
  periodSelect.addEventListener('change', reloadHistory);
  // Pages left open on a wall screen also pick up the new readings.
  setInterval(reloadHistory, 10 * 60 * 1000);
}
async function poll() {
  try { const wasPending = pending; await refreshStatus(); showError(''); if (wasPending && !pending) await reloadHistory(); }
  catch (error) { showError(error.message); }
  setTimeout(poll, pending ? 4000 : 30000);
}
reloadHistory();
if (hasCards) poll();
