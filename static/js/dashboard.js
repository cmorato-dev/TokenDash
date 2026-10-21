const $ = (selector, root = document) => root.querySelector(selector);
const fmt = new Intl.DateTimeFormat('es-ES', { dateStyle: 'short', timeStyle: 'short', timeZone: document.body.dataset.timezone });
const percent = value => value === null ? '—' : `${Number(value).toLocaleString('es-ES', { maximumFractionDigits: 1 })}%`;
const renewDay = new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'numeric', timeZone: document.body.dataset.timezone });
const renewHour = new Intl.DateTimeFormat('es-ES', { hour: 'numeric', minute: '2-digit', hourCycle: 'h23', timeZone: document.body.dataset.timezone });
// «Llevas un 26% del límite esta semana. Se renueva el 27/10 a las 7:41.»
const quotaPeriods = { session: 'en esta sesión de 5 horas', weekly: 'esta semana', weekly_all: 'esta semana', weekly_sonnet: 'esta semana con Sonnet', monthly: 'este mes' };
function quotaSentence(quota) {
  const period = quotaPeriods[quota.key] || `en «${quota.label}»`;
  // The window restarted after this reading: the value is the last known one, not the current one.
  if (quota.window_reset) return `Llevabas un ${percent(quota.used_percent)} del límite ${period}. Ya se ha renovado.`;
  const when = new Date(quota.resets_at);
  const renews = quota.resets_at && !Number.isNaN(when.getTime()) ? ` Se renueva el ${renewDay.format(when)} a las ${renewHour.format(when)}.` : '';
  return `Llevas un ${percent(quota.used_percent)} del límite ${period}.${renews}`;
}
// More than half of a limit used turns it yellow; more than 80 %, red. A window that has
// already restarted keeps its old value, so it is not coloured.
const levelOf = (used, reset) => used === null || used === undefined || reset ? 'ok' : used > 80 ? 'critical' : used > 50 ? 'warning' : 'ok';
const levelNotes = { warning: 'Has pasado de la mitad del límite.', critical: 'Te queda poco: has pasado del 80 % del límite.' };
let pending = false;
// Home Assistant modules carry their read-only key in the URL fragment (#clave=…),
// which the browser never sends to the server; the API receives it as a header.
const embedded = 'embed' in document.body.dataset;
const embedKey = new URLSearchParams(window.location.hash.slice(1)).get('clave');
const showError = message => { const feedback = $('#feedback'); if (feedback) feedback.textContent = message; };
async function getJSON(url, options = {}) {
  if (embedded && !embedKey) throw new Error('Falta la clave: añade #clave=… al final de la dirección del módulo.');
  const auth = embedKey ? { Authorization: `Bearer ${embedKey}` } : {};
  const response = await fetch(url, { ...options, headers: { Accept: 'application/json', ...auth, ...options.headers } });
  if (response.redirected) { window.location.href = response.url; throw new Error('Inicia sesión de nuevo.'); }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'No se pudo completar la solicitud.');
  return data;
}
async function refreshStatus() {
  const data = await getJSON('/api/status/');
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
    $('.quota-label', card).textContent = provider.quota_label || 'Sin lectura confirmada';
    $('.state', card).textContent = provider.refreshing ? 'Actualizando…' : provider.state_label;
    $('.state', card).classList.toggle('success', provider.state === 'ok');
    $('.updated', card).textContent = provider.last_success_at ? fmt.format(new Date(provider.last_success_at)) : 'Nunca';
    $('.attempt', card).textContent = provider.last_attempt_at ? `Último intento: ${fmt.format(new Date(provider.last_attempt_at))}` : '';
    $('.error', card).textContent = provider.last_error;
    $('.hint', card).textContent = provider.hint || '';
    const resetText = quota => quota.window_reset ? 'La ventana se ha reiniciado desde esta lectura' : (quota.reset_text || '');
    $('.reset', card).textContent = provider.quotas[0] ? resetText(provider.quotas[0]) : '';
    const level = levelOf(provider.used_percent, provider.quotas[0]?.window_reset);
    card.dataset.level = level;
    const note = $('.level-note', card);
    note.dataset.level = level;
    note.textContent = levelNotes[level] || '';
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
}
const palette = ['#34d399', '#fb923c', '#60a5fa', '#c084fc', '#facc15', '#f472b6'];
// Fixed colour per provider and window, so a series keeps its colour when another one has no data.
const seriesColors = { 'chatgpt:session': '#34d399', 'chatgpt:weekly': '#60a5fa', 'claude:session': '#fb923c', 'claude:weekly_all': '#c084fc' };
const quotaNames = { session: 'sesión / 5 h', weekly: 'semana', weekly_all: 'semana', weekly_sonnet: 'semana · Sonnet', monthly: 'mes' };
// Five-hour windows are drawn solid; weekly and monthly ones dashed, with hollow points.
const dashFor = quota => quota === 'session' ? null : '9 6';
// How each period is grouped and how its axis is labelled.
const granularityNames = { day: 'Media diaria', week: 'Media por semana', month: 'Media por mes', year: 'Media por año' };
function axisLabel(label, granularity) {
  if (granularity === 'year') return label.slice(0, 4);
  if (granularity === 'month') return label.slice(0, 7);
  if (granularity === 'week') return `sem. ${label.slice(8)}/${label.slice(5, 7)}`;
  return label.slice(5);
}
function bucketName(label, granularity) {
  if (granularity === 'day') return `día ${label.slice(8)}/${label.slice(5, 7)}/${label.slice(0, 4)}`;
  if (granularity === 'week') return `semana del ${label.slice(8)}/${label.slice(5, 7)}/${label.slice(0, 4)}`;
  if (granularity === 'month') return `mes de ${label.slice(0, 4)}-${label.slice(5, 7)}`;
  return `año ${label.slice(0, 4)}`;
}
function svgNode(tag, attrs, text) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  if (text !== undefined) node.textContent = text;
  return node;
}
async function loadHistory() {
  showError('');
  const data = await getJSON(`/api/history/?days=${$('#history-days').value}`);
  const root = $('#history'), legend = $('#history-legend');
  root.replaceChildren(); legend.replaceChildren();
  const granularity = data.granularity || 'day';
  const note = $('#history-note');
  if (note) note.textContent = `${granularityNames[granularity] || 'Media diaria'} del porcentaje observado por cuota.`;
  if (!data.series.length) {
    const empty = document.createElement('p');
    empty.className = 'empty'; empty.textContent = 'El histórico aparecerá tras la primera lectura confirmada.';
    root.append(empty); return;
  }
  // Use the real width so labels keep their size on phones.
  const W = Math.max(300, root.clientWidth || 1000);
  const svg = svgNode('svg', { viewBox: `0 0 ${W} 260`, role: 'img', 'aria-label': 'Media del consumo, de 0 a 100 por ciento' });
  [0, 25, 50, 75, 100].forEach(value => {
    const y = 220 - value * 2;
    svg.append(svgNode('line', { x1: 48, x2: W - 25, y1: y, y2: y, stroke: '#263449', 'stroke-dasharray': '4 6' }));
    svg.append(svgNode('text', { x: 0, y: y + 4, fill: '#8190a6', 'font-size': 12 }, `${value}%`));
  });
  const xAt = i => 48 + i * (W - 73) / Math.max(1, data.labels.length - 1);
  const every = Math.ceil(data.labels.length / Math.max(2, Math.floor((W - 73) / 70)));
  data.series.forEach((series, idx) => {
    const color = seriesColors[`${series.provider}:${series.quota}`] || palette[idx % palette.length];
    const dash = dashFor(series.quota);
    let path = '', connected = false;
    const points = [];
    series.values.forEach((value, index) => {
      if (value === null) { connected = false; return; }
      const x = xAt(index), y = 220 - value * 2;
      path += `${connected ? 'L' : 'M'}${x},${y} `; connected = true;
      const point = svgNode('circle', dash ? { cx: x, cy: y, r: 4, fill: '#111b2c', stroke: color, 'stroke-width': 2 } : { cx: x, cy: y, r: 4, fill: color });
      point.append(svgNode('title', {}, `${series.provider === 'chatgpt' ? 'ChatGPT' : 'Claude'} · ${quotaNames[series.quota] || series.quota} · ${bucketName(data.labels[index], granularity)}: ${percent(value)}`));
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
  data.labels.forEach((label, index) => {
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
  // A module can open on another period: /ha/grafica/?dias=30#clave=…
  const days = new URLSearchParams(window.location.search).get('dias');
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
