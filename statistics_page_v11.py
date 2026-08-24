"""V11 statistics UI backed by the latest historical replay result."""
from __future__ import annotations
import json
from flask import Response
from v11.engine import ENGINE_VERSION


def _replay_state():
    try:
        import replay_web
        with replay_web._LOCK:
            state = dict(replay_web._STATE)
            state["output"] = list(state.get("output") or [])
            state["result"] = replay_web._compact_result(state.get("result"))
            return state
    except Exception:
        return {"running": False, "status": "idle", "output": [], "result": None}


def _latest():
    state = _replay_state()
    return state.get("result"), state


def _json(value):
    return Response(json.dumps(value, ensure_ascii=False, allow_nan=False), mimetype="application/json", headers={"Cache-Control":"no-store"})


def _trade_rows(result):
    rows=[]
    for report in (result.get("reports") or []):
        symbol=report.get("symbol")
        for trade in (report.get("trade_history") or []):
            item=dict(trade); item["symbol"]=symbol; rows.append(item)
    rows.sort(key=lambda x:str(x.get("candle_time") or ""), reverse=True)
    return rows


def _progress(state):
    """Return the newest structured replay progress event without guessing metrics."""
    for line in reversed(state.get("output") or []):
        try:
            obj=json.loads(str(line).strip())
            if isinstance(obj,dict) and obj.get("_replay_progress") in {"engine_progress","engine_started","history_ready","fetching","fetched","symbol_started"}:
                return obj
        except Exception:
            continue
    return None


def _running_payload(state):
    p=_progress(state) or {}
    return {
        "status":"running" if state.get("running") else state.get("status","idle"),
        "engine_version":ENGINE_VERSION,
        "start":state.get("start"), "end":state.get("end"),
        "symbol":state.get("symbol"),
        "symbols":([state.get("symbol")] if state.get("symbol") in ("BTC","GOLD") else ["BTC","GOLD"]),
        "progress":p,
        "running":bool(state.get("running")),
        "message":"Replay กำลังประมวลผล — สถิติสุดท้ายจะแสดงเมื่อ Replay เสร็จ",
        "live_orders_allowed":False,
    }


def register(app):
    @app.route("/statistics", strict_slashes=False)
    def statistics_page(): return Response(PAGE, mimetype="text/html", headers={"Cache-Control":"no-store"})

    @app.route("/api/statistics", strict_slashes=False)
    def statistics_api():
        result, state = _latest()
        if not result:
            if state.get("running"):
                return _json(_running_payload(state))
            return _json({"status":"no_replay","engine_version":ENGINE_VERSION,"message":"ยังไม่มีผล V11 Replay กรุณาเริ่มการทดสอบที่ /replay","live_orders_allowed":False})
        reports=result.get("reports") or []
        combined={"rows":0,"trades":0,"decided":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"net_r":0.0,"gross_profit_r":0.0,"gross_loss_r":0.0}
        strategy_map={}
        for report in reports:
            p=report.get("performance") or {}
            for key in combined: combined[key]+=p.get(key,0) or 0
            for name,stats in (p.get("strategies") or {}).items():
                target=strategy_map.setdefault(name,{"evaluated":0,"trades":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"net_r":0.0})
                for key in target: target[key]+=stats.get(key,0) or 0
        decided=combined["wins"]+combined["losses"]
        combined["win_rate"]=round(100*combined["wins"]/decided,2) if decided else 0.0
        combined["loss_rate"]=round(100*combined["losses"]/decided,2) if decided else 0.0
        combined["expectancy_r"]=round(combined["net_r"]/decided,4) if decided else 0.0
        combined["profit_factor"]=round(combined["gross_profit_r"]/combined["gross_loss_r"],4) if combined["gross_loss_r"] else None
        for stats in strategy_map.values():
            d=stats["wins"]+stats["losses"]
            stats["win_rate"]=round(100*stats["wins"]/d,2) if d else 0.0
            stats["expectancy_r"]=round(stats["net_r"]/d,4) if d else 0.0
        payload={"status":"ok","running":bool(state.get("running")),"engine_version":ENGINE_VERSION,"start":reports[0].get("start") if reports else state.get("start"),"end":reports[0].get("end") if reports else state.get("end"),"symbols":result.get("symbols"),"source":result.get("source"),"performance":combined,"strategies":strategy_map,"trade_history":_trade_rows(result),"reports":reports,"live_orders_allowed":False}
        if state.get("running"): payload["progress"]=_progress(state)
        return _json(payload)

PAGE=r'''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V11 Backtest Statistics</title><style>body{font-family:system-ui,sans-serif;background:#0b1220;color:#e8eef8;margin:0;padding:20px}main{max-width:1450px;margin:auto}.box{background:#121c30;border:1px solid #263654;border-radius:14px;padding:16px;margin:12px 0}.muted{color:#93a4bd}.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.card{background:#172238;padding:12px;border-radius:10px}.card b{display:block;font-size:20px;margin-top:4px}.table{overflow:auto;max-height:620px}table{width:100%;border-collapse:collapse}th,td{padding:9px;border-bottom:1px solid #263654;text-align:left;white-space:nowrap}th{position:sticky;top:0;background:#172238;z-index:1}.win{color:#55d68b}.loss{color:#ff6b6b}.open{color:#ffd166}.link{color:#70a7ff}.empty{text-align:center;padding:30px;color:#93a4bd}.filters{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:10px 0}.filters select{width:100%;box-sizing:border-box;background:#172238;color:#fff;border:1px solid #33425e;border-radius:8px;padding:9px}.progress{height:16px;background:#09101d;border-radius:8px;overflow:hidden}.bar{height:100%;background:#3b82f6;width:0%;transition:width .3s}.progressText{margin-top:8px}@media(max-width:900px){.cards{grid-template-columns:repeat(3,1fr)}}@media(max-width:600px){.cards{grid-template-columns:repeat(2,1fr)}.filters{grid-template-columns:1fr}}</style></head><body><main><div class="box"><h1>📊 V11 Backtest Statistics</h1><div class="muted">สถิติจาก Historical Replay · V11 engine เดียวกับ Live · M5 trigger + M15 context</div><p><a class="link" href="/replay">⏪ ไปหน้า V11 Replay</a></p><div id="period" class="muted">กำลังโหลด...</div></div><div id="main"></div><div id="running" class="box" style="display:none"><h2>⏳ Replay กำลังทำงาน</h2><div id="progressLabel" class="muted">กำลังเริ่ม...</div><div class="progress"><div id="bar" class="bar"></div></div><div id="progressText" class="progressText"></div></div><div class="box"><h2>📋 รายการออเดอร์ที่เข้าเทรด</h2><div class="muted">แสดงเฉพาะ BUY/SELL ที่เกิดเป็นออเดอร์จริง · ไม่รวม NO_TRADE</div><div class="filters"><select id="symbolFilter"><option value="ALL">ทุกสินทรัพย์</option><option value="BTC">BTC</option><option value="GOLD">GOLD</option></select><select id="sideFilter"><option value="ALL">BUY + SELL</option><option value="BUY">BUY</option><option value="SELL">SELL</option></select><select id="resultFilter"><option value="ALL">ทุกผลลัพธ์</option><option value="WIN">WIN</option><option value="LOSS">LOSS</option><option value="OPEN">OPEN</option><option value="AMBIGUOUS">AMBIGUOUS</option></select></div><div class="table"><table><thead><tr><th>เวลาเข้า (UTC)</th><th>สินทรัพย์</th><th>Side</th><th>Strategy</th><th>Entry</th><th>S/L</th><th>TP1</th><th>TP2</th><th>TP3</th><th>RR</th><th>ผล</th><th>R</th><th>เวลาปิด</th></tr></thead><tbody id="trades"></tbody></table></div></div><div class="box"><h2>🧠 สถิติแยก Strategy</h2><div class="table"><table><thead><tr><th>Strategy</th><th>Evaluated</th><th>Trades</th><th>WIN</th><th>LOSS</th><th>WR</th><th>Net R</th><th>Expectancy</th></tr></thead><tbody id="strategies"></tbody></table></div></div></main><script>const $=x=>document.getElementById(x);let DATA=[];function esc(x){return String(x??'').replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[m])||m)}function n(x){return x==null?'—':Number(x).toFixed(4)}function renderTrades(){const sf=$('symbolFilter').value,side=$('sideFilter').value,rf=$('resultFilter').value;const rows=DATA.filter(t=>(sf==='ALL'||t.symbol===sf)&&(side==='ALL'||t.signal===side)&&(rf==='ALL'||t.result===rf));$('trades').innerHTML=rows.map(t=>{const cls=t.result==='WIN'?'win':t.result==='LOSS'?'loss':t.result==='OPEN'?'open':'';return '<tr><td>'+esc(t.candle_time)+'</td><td>'+esc(t.symbol)+'</td><td><b>'+esc(t.signal)+'</b></td><td>'+esc(t.strategy)+'</td><td>'+n(t.entry)+'</td><td>'+n(t.sl)+'</td><td>'+n(t.tp1??t.tp)+'</td><td>'+n(t.tp2)+'</td><td>'+n(t.tp3)+'</td><td>'+n(t.rr)+'</td><td class="'+cls+'"><b>'+esc(t.result)+'</b></td><td>'+n(t.r_multiple)+'</td><td>'+esc(t.resolved_at||'—')+'</td></tr>'}).join('')||'<tr><td colspan="13" class="empty">'+(DATA.length?'ไม่พบรายการตามตัวกรอง':'ยังไม่มีออเดอร์ที่ปิด/ยืนยันระหว่าง Replay')+'</td></tr>'}async function load(){try{const r=await fetch('/api/statistics?ts='+Date.now(),{cache:'no-store'});const d=await r.json();if(d.status==='running'){ $('running').style.display='block';const p=d.progress||{};const pct=Math.max(0,Math.min(100,Number(p.percent||0)));$('bar').style.width=pct+'%';$('progressLabel').textContent='สินทรัพย์: '+(p.symbol||d.symbol||'—')+' · '+(p._replay_progress||'running');$('progressText').textContent=(p.completed!=null?p.completed+' / '+(p.total||'?')+' candles · '+pct.toFixed(1)+'%':'กำลังเตรียมข้อมูล...')+' · Trades '+(p.trades??0)+' · WIN '+(p.wins??0)+' · LOSS '+(p.losses??0)+' · OPEN '+(p.open??0)+' · Net '+(p.net_r??0)+'R';$('period').textContent='ช่วงทดสอบ: '+d.start+' ถึง '+d.end+' · Replay RUNNING';$('main').innerHTML='';return} $('running').style.display='none';if(d.status!=='ok'){$('main').innerHTML='<div class="box empty">'+esc(d.message||'ยังไม่มีข้อมูล')+'<br><br><a class="link" href="/replay">เริ่ม V11 Replay</a></div>';DATA=[];renderTrades();return}const p=d.performance;$('period').textContent='ช่วงทดสอบ: '+d.start+' ถึง '+d.end+' · '+(d.symbols||[]).join(' + ');const cards=[['Candles',p.rows],['Trades',p.trades],['WIN / LOSS',p.wins+' / '+p.losses],['Win Rate',p.win_rate+'%'],['Net R',n(p.net_r)],['Profit Factor',p.profit_factor??'—'],['Expectancy',n(p.expectancy_r)+' R'],['Max DD',n((d.reports||[]).reduce((m,r)=>Math.max(m,Number((r.performance||{}).max_drawdown_r||0)),0))+' R'],['OPEN',p.open],['AMBIGUOUS',p.ambiguous],['NO_TRADE',p.no_trade],['Signals',(d.reports||[]).reduce((s,r)=>s+Number(r.signals||0),0)]];$('main').innerHTML='<div class="box"><div class="cards">'+cards.map(c=>'<div class="card"><span class="muted">'+c[0]+'</span><b>'+esc(c[1])+'</b></div>').join('')+'</div></div>';DATA=d.trade_history||[];renderTrades();$('strategies').innerHTML=Object.entries(d.strategies||{}).map(([name,s])=>'<tr><td><b>'+esc(name)+'</b></td><td>'+s.evaluated+'</td><td>'+s.trades+'</td><td class="win">'+s.wins+'</td><td class="loss">'+s.losses+'</td><td>'+s.win_rate+'%</td><td>'+n(s.net_r)+'</td><td>'+n(s.expectancy_r)+' R</td></tr>').join('')||'<tr><td colspan="8">ไม่มีข้อมูล</td></tr>'}catch(e){$('period').textContent='เชื่อมต่อ Statistics API ไม่สำเร็จ: '+e}finally{}}['symbolFilter','sideFilter','resultFilter'].forEach(id=>$(id).addEventListener('change',renderTrades));load();setInterval(load,2000)</script></body></html>'''
