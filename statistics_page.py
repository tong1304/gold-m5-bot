"""V12 statistics: live V12 signals and historical V12 replay are separate sources."""
from __future__ import annotations
import json
from flask import Response
from v11.engine import ENGINE_VERSION


def _json(value, status=200):
    return Response(json.dumps(value, ensure_ascii=False, allow_nan=False, default=str), status=status,
                    mimetype="application/json", headers={"Cache-Control": "no-store"})


def _live_signals(days=3650, limit=1000):
    try:
        from signal_history import history
        rows = history.list_signals(days=days, limit=limit)
        out = []
        for row in rows:
            item = dict(row)
            try:
                payload = json.loads(item.get("payload_json") or "{}")
            except Exception:
                payload = {}
            levels = payload.get("trade_levels") or {}
            item.update({
                "engine_version": payload.get("engine_version") or ENGINE_VERSION,
                "strategy": payload.get("strategy") or "NONE",
                "engine": payload.get("engine") or "NONE",
                "regime": (payload.get("regime") or {}).get("regime") if isinstance(payload.get("regime"), dict) else payload.get("regime"),
                "setup_id": payload.get("setup_id") or item.get("setup_key"),
                "trigger_id": payload.get("trigger_id"),
                "entry_type": payload.get("entry_type"),
                "setup_score": (payload.get("setup_score") or {}).get("score") if isinstance(payload.get("setup_score"), dict) else payload.get("setup_score"),
                "entry": levels.get("entry", item.get("entry")),
                "sl": levels.get("sl", item.get("sl")),
                "tp": levels.get("tp", item.get("tp")),
                "rr": levels.get("risk_reward", levels.get("effective_rr", item.get("risk_reward"))),
                "candle_time": payload.get("candle_time") or payload.get("closed_candle") or item.get("candle_time"),
                "telegram_alert_sent": bool(item.get("telegram_sent")),
                "replay": bool(payload.get("replay", False)),
            })
            out.append(item)
        return out
    except Exception:
        return []


def _replay_state():
    try:
        import replay_web
        with replay_web._LOCK:
            return dict(replay_web._STATE)
    except Exception:
        return {"running": False, "status": "idle", "result": None, "output": []}


def _replay_trades(result):
    trades = []
    for report in (result or {}).get("reports") or []:
        symbol = report.get("symbol")
        for trade in report.get("trade_history") or []:
            item = dict(trade)
            item["symbol"] = symbol
            trades.append(item)
    trades.sort(key=lambda x: str(x.get("candle_time") or ""), reverse=True)
    return trades


def _performance(trades):
    outcomes = [str(t.get("result") or "OPEN").upper() for t in trades]
    wins = sum(x == "WIN" for x in outcomes)
    losses = sum(x == "LOSS" for x in outcomes)
    opens = sum(x == "OPEN" for x in outcomes)
    ambiguous = sum(x == "AMBIGUOUS" for x in outcomes)
    decided = wins + losses
    r_values = [float(t.get("r_multiple") or 0) for t in trades if str(t.get("result") or "").upper() in ("WIN", "LOSS")]
    net = round(sum(r_values), 4)
    gross_profit = round(sum(x for x in r_values if x > 0), 4)
    gross_loss = round(abs(sum(x for x in r_values if x < 0)), 4)
    return {
        "trades": len(trades), "decided": decided, "wins": wins, "losses": losses,
        "open": opens, "ambiguous": ambiguous, "no_trade": 0,
        "net_r": net, "gross_profit_r": gross_profit, "gross_loss_r": gross_loss,
        "win_rate": round(100 * wins / decided, 2) if decided else 0.0,
        "loss_rate": round(100 * losses / decided, 2) if decided else 0.0,
        "expectancy_r": round(net / decided, 4) if decided else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
    }


def _strategy_stats(trades):
    result = {}
    for trade in trades:
        name = trade.get("strategy") or "NONE"
        s = result.setdefault(name, {"trades": 0, "wins": 0, "losses": 0, "open": 0, "ambiguous": 0, "net_r": 0.0})
        s["trades"] += 1
        outcome = str(trade.get("result") or "OPEN").upper()
        if outcome == "WIN": s["wins"] += 1
        elif outcome == "LOSS": s["losses"] += 1
        elif outcome == "OPEN": s["open"] += 1
        elif outcome == "AMBIGUOUS": s["ambiguous"] += 1
        s["net_r"] += float(trade.get("r_multiple") or 0)
    for s in result.values():
        decided = s["wins"] + s["losses"]
        s["net_r"] = round(s["net_r"], 4)
        s["win_rate"] = round(100 * s["wins"] / decided, 2) if decided else 0.0
        s["expectancy_r"] = round(s["net_r"] / decided, 4) if decided else 0.0
    return result


def _progress(state):
    for line in reversed(state.get("output") or []):
        try:
            obj = json.loads(str(line).strip())
            if isinstance(obj, dict) and obj.get("_replay_progress"):
                return obj
        except Exception:
            pass
    return None


def _payload():
    state = _replay_state()
    live = _live_signals()
    result = state.get("result")
    base = {
        "engine_version": ENGINE_VERSION,
        "engine_name": "REGIME-8-ENGINE-REENTRY",
        "source_contract": "V12",
        "timeframes": ["M5", "M15"],
        "live_signal_count": len(live),
        "live_signals": live,
        "live_orders_allowed": False,
    }
    if state.get("running"):
        return {**base, "status": "running", "running": True, "source": "LSE_HISTORICAL_OHLCV", "progress": _progress(state),
                "message": "V12 Historical Replay กำลังประมวลผล"}
    if not result:
        return {**base, "status": "no_replay", "running": False, "source": "LSE_HISTORICAL_OHLCV",
                "message": "ยังไม่มีผล V12 Historical Replay", "replay_trades": [], "performance": None, "strategies": {}}
    trades = _replay_trades(result)
    perf = _performance(trades)
    reports = result.get("reports") or []
    return {**base, "status": "ok", "running": False, "source": "LSE_HISTORICAL_OHLCV",
            "start": state.get("start"), "end": state.get("end"), "symbols": result.get("symbols"),
            "performance": perf, "strategies": _strategy_stats(trades), "replay_trades": trades,
            "reports": reports, "progress": None}


def register(app):
    @app.route("/statistics", strict_slashes=False)
    def statistics_page():
        return Response(PAGE, mimetype="text/html", headers={"Cache-Control": "no-store"})

    @app.route("/api/statistics", strict_slashes=False)
    def statistics_api():
        return _json(_payload())

    # Keep the existing replay implementation, but make its public page clearly V12.
    if not any(rule.rule == "/replay" for rule in app.url_map.iter_rules()):
        try:
            import replay_web
            replay_web.register(app)
        except Exception:
            pass


PAGE = r'''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V12 Statistics</title>
<style>body{font-family:system-ui,sans-serif;background:#0b1220;color:#e8eef8;margin:0;padding:20px}main{max-width:1600px;margin:auto}.box{background:#121c30;border:1px solid #263654;border-radius:14px;padding:16px;margin:12px 0}.muted{color:#93a4bd}.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.card{background:#172238;padding:12px;border-radius:10px}.card b{display:block;font-size:20px;margin-top:4px}.win{color:#55d68b}.loss{color:#ff6b6b}.open{color:#ffd166}.link{color:#70a7ff}.table{overflow:auto;max-height:600px}table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #263654;text-align:left;white-space:nowrap}th{position:sticky;top:0;background:#172238}.filters{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.filters select{background:#172238;color:#fff;border:1px solid #33425e;border-radius:8px;padding:8px}.badge{display:inline-block;padding:4px 8px;border-radius:8px;background:#172238;margin:2px}.empty{text-align:center;padding:25px}.progress{height:14px;background:#09101d;border-radius:8px;overflow:hidden}.bar{height:100%;background:#3b82f6;width:0%}@media(max-width:900px){.cards{grid-template-columns:repeat(3,1fr)}}@media(max-width:600px){.cards{grid-template-columns:repeat(2,1fr)}} </style></head><body><main>
<div class="box"><h1>📊 V12 Statistics</h1><div class="muted">REGIME-8 ENGINE + CONTROLLED RE-ENTRY · M5 Trigger + M15 Context · BTC + GOLD</div><p><a class="link" href="/replay">⏪ V12 Historical Replay</a></p><div id="period" class="muted">กำลังโหลด...</div></div>
<div id="summary"></div><div id="running" class="box" style="display:none"><h2>⏳ V12 Historical Replay</h2><div id="prog"></div><div class="progress"><div id="bar" class="bar"></div></div></div>
<div class="box"><h2>📡 LIVE SIGNALS — V12</h2><div class="muted">ข้อมูลจาก signal_history.db · NO_TRADE ไม่ถูกนับเป็น WIN/LOSS</div><div class="filters"><select id="asset"><option>ALL</option><option>BTC</option><option>GOLD</option></select><select id="side"><option>ALL</option><option>BUY</option><option>SELL</option><option>NO_TRADE</option></select><select id="result"><option>ALL</option><option>WIN</option><option>LOSS</option><option>OPEN</option><option>NO_TRADE</option><option>AMBIGUOUS</option></select></div><div class="table"><table><thead><tr><th>เวลา</th><th>Asset</th><th>Side</th><th>Regime</th><th>Engine</th><th>Strategy</th><th>Entry Type</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>Score</th><th>Result</th><th>Signal ID</th><th>Setup ID</th><th>Telegram</th></tr></thead><tbody id="live"></tbody></table></div></div>
<div class="box"><h2>📜 V12 HISTORICAL REPLAY</h2><div class="table"><table><thead><tr><th>เวลา</th><th>Asset</th><th>Side</th><th>Strategy</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>Result</th><th>R</th><th>Setup</th></tr></thead><tbody id="replay"></tbody></table></div></div>
<div class="box"><h2>🧠 V12 Strategy Performance</h2><div class="table"><table><thead><tr><th>Strategy</th><th>Trades</th><th>WIN</th><th>LOSS</th><th>WR</th><th>Net R</th><th>Expectancy</th></tr></thead><tbody id="strategies"></tbody></table></div></div>
</main><script>const $=id=>document.getElementById(id),esc=x=>String(x??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])),num=x=>x==null?'—':Number(x).toFixed(4);let LIVE=[];function renderLive(){let a=$('asset').value,s=$('side').value,r=$('result').value;let rows=LIVE.filter(x=>(a==='ALL'||x.symbol===a)&&(s==='ALL'||(x.direction||x.signal)===s)&&(r==='ALL'||String(x.result||'').toUpperCase()===r));$('live').innerHTML=rows.map(x=>'<tr><td>'+esc(x.candle_time||x.created_at)+'</td><td>'+esc(x.symbol)+'</td><td>'+esc(x.direction||x.signal)+'</td><td>'+esc(x.regime||'—')+'</td><td>'+esc(x.engine||'—')+'</td><td>'+esc(x.strategy||'NONE')+'</td><td>'+esc(x.entry_type||'—')+'</td><td>'+num(x.entry)+'</td><td>'+num(x.sl)+'</td><td>'+num(x.tp)+'</td><td>'+num(x.rr)+'</td><td>'+esc(x.setup_score??'—')+'</td><td>'+esc(x.result||'—')+'</td><td>'+esc(x.signal_id||'—')+'</td><td>'+esc(x.setup_id||x.setup_key||'—')+'</td><td>'+(x.telegram_alert_sent?'✅':'—')+'</td></tr>').join('')||'<tr><td colspan="16" class="empty">ยังไม่มี V12 Live Signal</td></tr>'}function renderReplay(rows){$('replay').innerHTML=(rows||[]).map(x=>'<tr><td>'+esc(x.candle_time)+'</td><td>'+esc(x.symbol)+'</td><td>'+esc(x.signal)+'</td><td>'+esc(x.strategy)+'</td><td>'+num(x.entry)+'</td><td>'+num(x.sl)+'</td><td>'+num(x.tp)+'</td><td>'+num(x.rr)+'</td><td>'+esc(x.result)+'</td><td>'+num(x.r_multiple)+'</td><td>'+esc(x.setup_key||'—')+'</td></tr>').join('')||'<tr><td colspan="11" class="empty">ยังไม่มี V12 Historical Trade</td></tr>'}async function load(){try{let d=await(await fetch('/api/statistics?ts='+Date.now(),{cache:'no-store'})).json();LIVE=d.live_signals||[];renderLive();if(d.status==='running'){$('running').style.display='block';let p=d.progress||{};$('bar').style.width=(p.percent||0)+'%';$('prog').textContent=(p.symbol||'ALL')+' · '+(p.completed??0)+'/'+(p.total??'?');$('summary').innerHTML='';return}$('running').style.display='none';if(d.status!=='ok'){$('period').textContent=d.message||'ยังไม่มี V12 Historical Replay';$('summary').innerHTML='';renderReplay([]);$('strategies').innerHTML='';return}let p=d.performance||{};$('period').textContent='Historical '+(d.start||'—')+' → '+(d.end||'—')+' · '+(d.symbols||[]).join(' + ')+' · '+d.source;let cards=[['Trades',p.trades],['WIN',p.wins],['LOSS',p.losses],['Win Rate',p.win_rate+'%'],['Net R',p.net_r],['Profit Factor',p.profit_factor??'—'],['Expectancy',p.expectancy_r+'R'],['OPEN',p.open],['AMBIGUOUS',p.ambiguous],['Live Signals',LIVE.length]];$('summary').innerHTML='<div class="box"><div class="cards">'+cards.map(c=>'<div class="card"><span class="muted">'+c[0]+'</span><b>'+esc(c[1])+'</b></div>').join('')+'</div></div>';renderReplay(d.replay_trades);$('strategies').innerHTML=Object.entries(d.strategies||{}).map(([n,s])=>'<tr><td><b>'+esc(n)+'</b></td><td>'+s.trades+'</td><td class="win">'+s.wins+'</td><td class="loss">'+s.losses+'</td><td>'+s.win_rate+'%</td><td>'+num(s.net_r)+'</td><td>'+num(s.expectancy_r)+'R</td></tr>').join('')||'<tr><td colspan="7" class="empty">ไม่มีข้อมูล</td></tr>'}catch(e){$('period').textContent='Statistics API error: '+e}}['asset','side','result'].forEach(id=>$(id).addEventListener('change',renderLive));load();setInterval(load,3000)</script></body></html>'''

__all__ = ["register"]
