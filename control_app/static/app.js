const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function api(url, options = {}) {
  const response = await fetch(url, {headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-cache'}, cache: 'no-store', ...options});
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
  return data;
}

function setTelegram(enabled) {
  $('telegramToggle').checked = enabled;
  $('telegramLabel').textContent = enabled ? 'เปิด' : 'ปิด';
  $('telegramLabel').className = enabled ? 'on' : 'off';
}

async function loadHealth() {
  const data = await api('/api/health');
  $('health').textContent = data.live_services_started ? 'LIVE SERVICES ACTIVE' : 'CONTROL APP READY';
  setTelegram(Boolean(data.telegram_enabled));
}

$('telegramToggle').addEventListener('change', async (event) => {
  const enabled = event.target.checked;
  try {
    const data = await api('/api/telegram/toggle', {method: 'POST', body: JSON.stringify({enabled})});
    setTelegram(data.enabled);
  } catch (error) {
    event.target.checked = !enabled;
    alert(error.message);
  }
});

function num(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeStats(raw) {
  const stats = raw && typeof raw === 'object' ? raw : {};
  return {
    total_trades: num(stats.total_trades),
    wins: num(stats.wins),
    losses: num(stats.losses),
    be: num(stats.be),
    win_rate: num(stats.win_rate),
    net_r: num(stats.net_r),
    average_r: num(stats.average_r),
    profit_factor: stats.profit_factor == null ? null : num(stats.profit_factor),
    max_drawdown_r: num(stats.max_drawdown_r),
    strategy_breakdown: stats.strategy_breakdown || {},
    side_breakdown: stats.side_breakdown || {},
  };
}

function renderMetrics(rawStats) {
  const stats = normalizeStats(rawStats);
  const cards = [
    ['Total Trades', stats.total_trades],
    ['Wins', stats.wins],
    ['Losses', stats.losses],
    ['BE', stats.be],
    ['Win Rate', `${stats.win_rate}%`],
    ['Net Result', `${stats.net_r} R`],
    ['Average R', stats.average_r],
    ['Profit Factor', stats.profit_factor == null ? '—' : stats.profit_factor],
    ['Max Drawdown', `${stats.max_drawdown_r} R`]
  ];
  $('metrics').innerHTML = cards.map(([name, value]) => `<div class="metric"><span>${esc(name)}</span><strong>${esc(value)}</strong></div>`).join('');
}

function renderBreakdown(target, data) {
  const entries = Object.entries(data || {});
  target.innerHTML = entries.length ? `<table class="compact"><thead><tr><th>Name</th><th>Trades</th><th>Win%</th><th>Net R</th></tr></thead><tbody>${entries.map(([name, v]) => `<tr><td>${esc(name)}</td><td>${num(v.trades)}</td><td>${num(v.win_rate)}%</td><td>${num(v.net_r)}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">ยังไม่มี trade</p>';
}

function renderTrades(trades) {
  $('trades').innerHTML = (trades || []).map(t => `<tr><td>${esc(t.candle_time)}</td><td>${esc(t.side)}</td><td>${esc(t.strategy)}</td><td>${esc(t.entry)}</td><td>${esc(t.sl)}</td><td>${esc(t.tp)}</td><td><span class="result ${String(t.result || '').toLowerCase()}">${esc(t.result)}</span></td><td>${esc(t.r_multiple)}</td></tr>`).join('');
}

function renderResult(run) {
  const result = run.result && typeof run.result === 'object' ? run.result : {};
  const stats = normalizeStats(result.statistics || result.performance || run.statistics || run.summary);
  const engineVersion = result.engine_version || run.engine_version || 'V12.9';
  $('statistics').classList.remove('hidden');
  $('runMeta').textContent = `${run.symbol || result.symbol || ''} · ${run.start_time || result.start_time || ''} → ${run.end_time || result.end_time || ''} · ${engineVersion}`;
  renderMetrics(stats);
  renderBreakdown($('strategies'), stats.strategy_breakdown);
  renderBreakdown($('sides'), stats.side_breakdown);
  renderTrades(result.trades || run.trades || []);
}

async function pollRun(runId) {
  for (;;) {
    const run = await api(`/api/backtest/${encodeURIComponent(runId)}`);
    if (run.status === 'completed') { renderResult(run); $('backtestMessage').textContent = 'Backtest เสร็จแล้ว'; await loadRuns(); return; }
    if (run.status === 'failed') throw new Error(run.error || 'Backtest failed');
    $('backtestMessage').textContent = 'กำลังประมวลผล…';
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
}

$('backtestForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('runButton').disabled = true;
  $('backtestMessage').textContent = 'กำลังเริ่ม Backtest…';
  try {
    const start = $('start').value;
    const end = $('end').value;
    if (!start || !end) throw new Error('กรุณาเลือกวันที่เริ่มต้นและสิ้นสุด');
    if (end < start) throw new Error('วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่มต้น');
    const data = await api('/api/backtest', {method: 'POST', body: JSON.stringify({symbol: $('symbol').value, start, end})});
    await pollRun(data.run_id);
  } catch (error) {
    $('backtestMessage').textContent = `เกิดข้อผิดพลาด: ${error.message}`;
  } finally { $('runButton').disabled = false; }
});

async function loadRuns() {
  const data = await api('/api/backtests?limit=20');
  $('runs').innerHTML = (data.runs || []).map(run => `<button class="run-row" data-id="${esc(run.run_id)}"><strong>${esc(run.symbol)}</strong><span>${esc(run.start_time)} → ${esc(run.end_time)}</span><span>${esc(run.status)}</span></button>`).join('') || '<p class="muted">ยังไม่มีผลการทดสอบ</p>';
  document.querySelectorAll('.run-row').forEach(button => button.addEventListener('click', async () => {
    try { renderResult(await api(`/api/backtest/${encodeURIComponent(button.dataset.id)}`)); } catch (error) { alert(error.message); }
  }));
}

$('refreshRuns').addEventListener('click', loadRuns);

(async function init() {
  const now = new Date();
  const end = now.toISOString().slice(0, 10);
  const startDate = new Date(now.getTime() - 7 * 86400000).toISOString().slice(0, 10);
  $('start').value = startDate; $('end').value = end;
  try { await loadHealth(); await loadRuns(); } catch (error) { $('health').textContent = 'ERROR'; $('backtestMessage').textContent = error.message; }
})();