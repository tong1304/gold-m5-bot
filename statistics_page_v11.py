"""V11.2 statistics: historical replay and real live Telegram signals are separate sources."""
from __future__ import annotations
import json
from flask import Response
from v11.engine import ENGINE_VERSION

def _replay_state():
    try:
        import replay_web
        with replay_web._LOCK:
            state=dict(replay_web._STATE);state["output"]=list(state.get("output") or []);state["result"]=replay_web._compact_result(state.get("result"));return state
    except Exception:return {"running":False,"status":"idle","output":[],"result":None}

def _live_signals(days=3650,limit=500):
    try:
        from signal_history import history
        rows=history.list_signals(days=days,limit=limit)
        for row in rows:
            try:
                payload=json.loads(row.get("payload_json") or "{}")
            except Exception:payload={}
            levels=payload.get("trade_levels") or {}
            row["strategy"]=payload.get("strategy") or payload.get("selected_strategy",{}).get("name") or "NONE"
            row["setup_key"]=row.get("setup_key") or payload.get("setup_key")
            row["tp1"]=levels.get("tp1",row.get("tp"));row["tp2"]=levels.get("tp2");row["tp3"]=levels.get("tp3");row["rr"]=row.get("risk_reward")
            row["m5_candle"]=payload.get("candle_time") or payload.get("closed_candle");row["m15_trend"]=(payload.get("m15_trend") or {}).get("direction") if isinstance(payload.get("m15_trend"),dict) else payload.get("m15_trend");row["telegram_alert_sent"]=bool(row.get("telegram_sent"));row["replay"]=bool(payload.get("replay",False))
        return rows
    except Exception:return []

def _json(value):return Response(json.dumps(value,ensure_ascii=False,allow_nan=False,default=str),mimetype="application/json",headers={"Cache-Control":"no-store"})

def _trade_rows(result):
    rows=[]
    for report in (result.get("reports") or []):
        symbol=report.get("symbol")
        for trade in (report.get("trade_history") or []):
            item=dict(trade);item["symbol"]=symbol;rows.append(item)
    rows.sort(key=lambda x:str(x.get("candle_time") or ""),reverse=True);return rows

def _progress(state):
    for line in reversed(state.get("output") or []):
        try:
            obj=json.loads(str(line).strip())
            if isinstance(obj,dict) and obj.get("_replay_progress") in {"engine_progress","engine_started","history_ready","fetching","fetched","symbol_started"}:return obj
        except Exception:continue
    return None

def _running_payload(state):
    p=_progress(state) or {};return {"status":"running" if state.get("running") else state.get("status","idle"),"engine_version":ENGINE_VERSION,"start":state.get("start"),"end":state.get("end"),"symbol":state.get("symbol"),"symbols":([state.get("symbol")] if state.get("symbol") in ("BTC","GOLD") else ["BTC","GOLD"]),"progress":p,"running":bool(state.get("running")),"message":"Replay กำลังประมวลผล — Historical statistics จะแสดงเมื่อเสร็จ","source":"LSE_HISTORICAL_OHLCV","live_orders_allowed":False}

def _replay_payload(result,state):
    reports=result.get("reports") or [];combined={"rows":0,"trades":0,"decided":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"net_r":0.0,"gross_profit_r":0.0,"gross_loss_r":0.0};strategy_map={}
    for report in reports:
        p=report.get("performance") or {}
        for key in combined:combined[key]+=p.get(key,0) or 0
        for name,stats in (p.get("strategies") or {}).items():
            target=strategy_map.setdefault(name,{"evaluated":0,"trades":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"net_r":0.0})
            for key in target:target[key]+=stats.get(key,0) or 0
    decided=combined["wins"]+combined["losses"];combined["win_rate"]=round(100*combined["wins"]/decided,2) if decided else 0.0;combined["loss_rate"]=round(100*combined["losses"]/decided,2) if decided else 0.0;combined["expectancy_r"]=round(combined["net_r"]/decided,4) if decided else 0.0;combined["profit_factor"]=round(combined["gross_profit_r"]/combined["gross_loss_r"],4) if combined["gross_loss_r"] else None
    for stats in strategy_map.values():
        d=stats["wins"]+stats["losses"];stats["win_rate"]=round(100*stats["wins"]/d,2) if d else 0.0;stats["expectancy_r"]=round(stats["net_r"]/d,4) if d else 0.0
    return {"status":"ok","running":bool(state.get("running")),"engine_version":ENGINE_VERSION,"start":reports[0].get("start") if reports else state.get("start"),"end":reports[0].get("end") if reports else state.get("end"),"symbols":result.get("symbols"),"source":"LSE_HISTORICAL_OHLCV","performance":combined,"strategies":strategy_map,"trade_history":_trade_rows(result),"reports":reports,"live_orders_allowed":False}

def register(app):
    @app.route("/statistics",strict_slashes=False)
    def statistics_page():return Response(PAGE,mimetype="text/html",headers={"Cache-Control":"no-store"})
    @app.route("/api/statistics",strict_slashes=False)
    def statistics_api():
        result,state=_replay_state()
        live=_live_signals()
        if not result:
            if state.get("running"):payload=_running_payload(state);payload["live_signal_count"]=len(live);payload["live_signals"]=live;return _json(payload)
            return _json({"status":"no_replay","engine_version":ENGINE_VERSION,"source":"LSE_HISTORICAL_OHLCV","message":"ยังไม่มีผล V11 Replay","live_signal_count":len(live),"live_signals":live,"live_orders_allowed":False})
        payload=_replay_payload(result,state);payload["live_signal_count"]=len(live);payload["live_signals"]=live;payload["progress"]=_progress(state) if state.get("running") else None;return _json(payload)

PAGE=r'''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V11.2 Statistics</title><style>body{font-family:system-ui,sans-serif;background:#0b1220;color:#e8eef8;margin:0;padding:20px}main{max-width:1550px;margin:auto}.box{background:#121c30;border:1px solid #263654;border-radius:14px;padding:16px;margin:12px 0}.muted{color:#93a4bd}.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.card{background:#172238;padding:12px;border-radius:10px}.card b{display:block;font-size:20px;margin-top:4px}.table{overflow:auto;max-height:620px}table{width:100%;border-collapse:collapse}th,td{padding:9px;border-bottom:1px solid #263654;text-align:left;white-space:nowrap}th{position:sticky;top:0;background:#172238}.win{color:#55d68b}.loss{color:#ff6b6b}.open{color:#ffd166}.link{color:#70a7ff}.empty{text-align:center;padding:25px}.progress{height:15px;background:#09101d;border-radius:8px;overflow:hidden}.bar{height:100%;background:#3b82f6;width:0%;transition:width .3s}.filters{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.filters select{background:#172238;color:#fff;border:1px solid #33425e;border-radius:8px;padding:8px}@media(max-width:900px){.cards{grid-template-columns:repeat(3,1fr)}}@media(max-width:600px){.cards{grid-template-columns:repeat(2,1fr)}} </style></head><body><main><div class="box"><h1>📊 V11.2 Statistics</h1><div class="muted">Historical Replay และ Live Telegram Signals แยกจากกันอย่างชัดเจน</div><p><a class="link" href="/replay">⏪ V11 Replay</a></p><div id="period" class="muted">กำลังโหลด...</div></div><div id="historical"></div><div id="running" class="box" style="display:none"><h2>⏳ Historical Replay กำลังทำงาน</h2><div id="prog"></div><div class="progress"><div id="bar" class="bar"></div></div></div><div class="box"><h2>📡 LIVE SIGNALS — ออเดอร์ที่ระบบแจ้ง Telegram จริง</h2><div class="muted">แหล่งข้อมูล: signal_history.db · ไม่ใช่ผลจาก Replay</div><div class="filters"><select id="ls"><option>ALL</option><option>BTC</option><option>GOLD</option></select><select id="ld"><option>ALL</option><option>BUY</option><option>SELL</option></select><select id="lr"><option>ALL</option><option>WIN</option><option>LOSS</option><option>OPEN</option><option>AMBIGUOUS</option></select></div><div class="table"><table><thead><tr><th>เวลา</th><th>Asset</th><th>Side</th><th>Strategy</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>Result</th><th>R</th><th>Resolved</th><th>Signal ID</th><th>Setup Key</th><th>Telegram</th></tr></thead><tbody id="live"></tbody></table></div></div><div class="box"><h2>📜 HISTORICAL REPLAY — Trades</h2><div class="muted">ใช้ LSE Historical OHLCV จริง และ V11.2 engine เดียวกับ Live</div><div class="table"><table><thead><tr><th>เวลา</th><th>Asset</th><th>Side</th><th>Strategy</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>Result</th><th>R</th><th>Setup Key</th></tr></thead><tbody id="replayTrades"></tbody></table></div></div><div class="box"><h2>🧠 Historical Strategy Statistics</h2><div class="table"><table><thead><tr><th>Strategy</th><th>Evaluated</th><th>Trades</th><th>WIN</th><th>LOSS</th><th>WR</th><th>Net R</th><th>Expectancy</th></tr></thead><tbody id="strategies"></tbody></table></div></div></main><script>const $=id=>document.getElementById(id);let LIVE=[],REPLAY=[];const esc=x=>String(x??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));const num=x=>x==null?'—':Number(x).toFixed(4);function liveRender(){let s=$('ls').value,d=$('ld').value,r=$('lr').value;let rows=LIVE.filter(x=>(s==='ALL'||x.symbol===s)&&(d==='ALL'||x.direction===d)&&(r==='ALL'||x.result===r));$('live').innerHTML=rows.map(x=>'<tr><td>'+esc(x.candle_time||x.created_at)+'</td><td>'+esc(x.symbol)+'</td><td><b>'+esc(x.direction)+'</b></td><td>'+esc(x.strategy)+'</td><td>'+num(x.entry)+'</td><td>'+num(x.sl)+'</td><td>'+num(x.tp)+'</td><td>'+num(x.rr)+'</td><td class="'+(x.result==='WIN'?'win':x.result==='LOSS'?'loss':x.result==='OPEN'?'open':'')+'"><b>'+esc(x.result)+'</b></td><td>'+num(x.r_multiple)+'</td><td>'+esc(x.resolved_at||'—')+'</td><td>'+esc(x.signal_id)+'</td><td>'+esc(x.setup_key||'—')+'</td><td>'+(x.telegram_alert_sent?'✅':'❌')+'</td></tr>').join('')||'<tr><td colspan="14" class="empty">ยังไม่มี Live Signal</td></tr>'}function replayRender(){ $('replayTrades').innerHTML=REPLAY.map(x=>'<tr><td>'+esc(x.candle_time)+'</td><td>'+esc(x.symbol)+'</td><td>'+esc(x.signal)+'</td><td>'+esc(x.strategy)+'</td><td>'+num(x.entry)+'</td><td>'+num(x.sl)+'</td><td>'+num(x.tp)+'</td><td>'+num(x.rr)+'</td><td>'+esc(x.result)+'</td><td>'+num(x.r_multiple)+'</td><td>'+esc(x.setup_key||'—')+'</td></tr>').join('')||'<tr><td colspan="11" class="empty">ยังไม่มี Historical Trade</td></tr>'}async function load(){try{let d=await (await fetch('/api/statistics?ts='+Date.now(),{cache:'no-store'})).json();LIVE=d.live_signals||[];liveRender();if(d.status==='running'){ $('running').style.display='block';let p=d.progress||{};$('bar').style.width=(p.percent||0)+'%';$('prog').textContent=(p.symbol||'ALL')+' · '+(p.completed??0)+'/'+(p.total??'?')+' · Trades '+(p.trades??0)+' · WIN '+(p.wins??0)+' · LOSS '+(p.losses??0);$('historical').innerHTML='';return}$('running').style.display='none';if(d.status!=='ok'){ $('period').textContent=d.message||'ยังไม่มี Historical Replay';$('historical').innerHTML='';REPLAY=[];replayRender();return}let p=d.performance||{};$('period').textContent='Historical: '+d.start+' → '+d.end+' · '+(d.symbols||[]).join(' + ')+' · Source: '+d.source;let cards=[['Candles',p.evaluated_rows??p.rows],['Trades',p.trades],['WIN',p.wins],['LOSS',p.losses],['Win Rate',p.win_rate+'%'],['Net R',num(p.net_r)],['Profit Factor',p.profit_factor??'—'],['Expectancy',num(p.expectancy_r)+'R'],['OPEN',p.open],['AMBIGUOUS',p.ambiguous],['LOCKED',p.locked_rows??0],['Live Signals',LIVE.length]];$('historical').innerHTML='<div class="box"><div class="cards">'+cards.map(c=>'<div class="card"><span class="muted">'+c[0]+'</span><b>'+esc(c[1])+'</b></div>').join('')+'</div></div>';REPLAY=d.trade_history||[];replayRender();$('strategies').innerHTML=Object.entries(d.strategies||{}).map(([n,s])=>'<tr><td><b>'+esc(n)+'</b></td><td>'+s.evaluated+'</td><td>'+s.trades+'</td><td class="win">'+s.wins+'</td><td class="loss">'+s.losses+'</td><td>'+s.win_rate+'%</td><td>'+num(s.net_r)+'</td><td>'+num(s.expectancy_r)+'R</td></tr>').join('')||'<tr><td colspan="8" class="empty">ไม่มีข้อมูล</td></tr>'}catch(e){$('period').textContent='Statistics API error: '+e}}['ls','ld','lr'].forEach(id=>$(id).addEventListener('change',liveRender));load();setInterval(load,2000)</script></body></html>'''
