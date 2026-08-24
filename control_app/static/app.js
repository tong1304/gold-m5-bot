const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function api(url, options = {}) {
  const response = await fetch(url, {headers: {'Content-Type': 'application/json'}, ...options});
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
  setTelegram(data.telegram_enabled);
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

function renderMetrics(stats) {
  const cards = [
    ['Total Trades', stats.total_trades], ['Wins', stats.wins], ['Losses', stats.losses],
    ['BE', stats.be], ['Win Rate', `${stats.win_rate}%`], ['Net Result', `${stats.net_r} R`],
    ['Average R', stats.average_r], ['Profit Factor', stats.profit_factor ?? '—'], ['Max Drawdown', `${stats.max_drawdown_r} R`]
  ];
  $('metrics').innerHTML = cards.map(([name, value]) => `<div class="metric"><span>${esc(name)}</span><strong>${esc(value)}</strong></div>`).join('');
}

function renderBreakdown(target, data) {
  const entries = Object.entries(data || {});
  target.innerHTML = entries.length ? `<table class="compact"><thead><tr><th>Name</th><th>Trades</th><th>Win%</th><th>Net R</th></tr></thead><tbody>${entries.map(([name, v]) => `<tr><td>${esc(name)}</td><td>${v.trades}</td><td>${v.win_rate}%</td><td>${v.net_r}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">ยังไม่มี trade</p>';
}

function renderTrades(trades) {
  $('trades').innerHTML = (trades || []).map(t => `<tr><td>${esc(t.candle_time)}</td><td>${esc(t.side)}</td><td>${esc(t.strategy)}</td><td>${esc(t.entry)}</td><td>${esc(t.sl)}</td><td>${esc(t.tp)}</td><td><span class="result ${String(t.result || '').toLowerCase()}">${esc(t.result)}</span></td><td>${esc(t.r_multiple)}</td></tr>`).join('');
}

function renderResult(run) {
  const result = run.result || {};
  const stats = result.statistics || {};
  $('statistics').classList.remove('hidden');
  $('runMeta').textContent = `${run.symbol} · ${run.start_time} → ${run.end_time} · ${run.engine_version}`;
  renderMetrics(stats);
  renderBreakdown($('strategies'), stats.strategy_breakdown);
  renderBreakdown($('sides'), stats.side_breakdown);
  renderTrades(result.trades);
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
    const data = await api('/api/backtest', {method: 'POST', body: JSON.stringify({symbol: $('symbol').value, start: $('start').value, end: $('end').value})});
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
