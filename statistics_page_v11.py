"""V11 statistics UI backed by the latest historical replay result."""
from __future__ import annotations
import json
from flask import Response
from v11.engine import ENGINE_VERSION

def _latest():
    try:
        import replay_web
        return replay_web.latest_replay_result()
    except Exception:
        return None

def _json(value):
    return Response(json.dumps(value, ensure_ascii=False, allow_nan=False), mimetype="application/json")

def register(app):
    @app.route("/statistics", strict_slashes=False)
    def statistics_page(): return Response(PAGE, mimetype="text/html")
    @app.route("/api/statistics", strict_slashes=False)
    def statistics_api():
        result = _latest()
        if not result:
            return _json({"status":"no_replay","engine_version":ENGINE_VERSION,"message":"ยังไม่มีผล V11 Replay กรุณาเริ่มการทดสอบที่ /replay","live_orders_allowed":False})
        reports = result.get("reports") or []
        combined = {"rows":0,"trades":0,"decided":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"net_r":0.0,"gross_profit_r":0.0,"gross_loss_r":0.0}
        strategy_map = {}
        for report in reports:
            p = report.get("performance") or {}
            for key in combined: combined[key] += p.get(key, 0) or 0
            for name, stats in (p.get("strategies") or {}).items():
                target = strategy_map.setdefault(name,{"evaluated":0,"trades":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"net_r":0.0})
                for key in target: target[key] += stats.get(key,0) or 0
        decided=combined["wins"]+combined["losses"]
        combined["win_rate"]=round(100*combined["wins"]/decided,2) if decided else 0.0
        combined["loss_rate"]=round(100*combined["losses"]/decided,2) if decided else 0.0
        combined["expectancy_r"]=round(combined["net_r"]/decided,4) if decided else 0.0
        combined["profit_factor"]=round(combined["gross_profit_r"]/combined["gross_loss_r"],4) if combined["gross_loss_r"] else None
        for stats in strategy_map.values():
            d=stats["wins"]+stats["losses"]; stats["win_rate"]=round(100*stats["wins"]/d,2) if d else 0.0; stats["expectancy_r"]=round(stats["net_r"]/d,4) if d else 0.0
        return _json({"status":"ok","engine_version":ENGINE_VERSION,"start":reports[0].get("start") if reports else None,"end":reports[0].get("end") if reports else None,"symbols":result.get("symbols"),"source":result.get("source"),"performance":combined,"strategies":strategy_map,"reports":reports,"live_orders_allowed":False})

PAGE=r'''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V11 Backtest Statistics</title><style>body{font-family:system-ui,sans-serif;background:#0b1220;color:#e8eef8;margin:0;padding:20px}main{max-width:1300px;margin:auto}.box{background:#121c30;border:1px solid #263654;border-radius:14px;padding:16px;margin:12px 0}.muted{color:#93a4bd}.cards{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.card{background:#172238;padding:12px;border-radius:10px}.card b{display:block;font-size:20px;margin-top:4px}.table{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:9px;border-bottom:1px solid #263654;text-align:left;white-space:nowrap}.win{color:#55d68b}.loss{color:#ff6b6b}.link{color:#70a7ff}.empty{text-align:center;padding:30px;color:#93a4bd}@media(max-width:900px){.cards{grid-template-columns:repeat(3,1fr)}}@media(max-width:500px){.cards{grid-template-columns:repeat(2,1fr)}}</style></head><body><main><div class="box"><h1>📊 V11 Backtest Statistics</h1><div class="muted">สถิติจาก Historical Replay เท่านั้น · ใช้ V11 engine เดียวกับ Live · M5 trigger + M15 context · ไม่มี Telegram และไม่มีการเปิดออเดอร์จริง</div><p><a class="link" href="/replay">⏪ ไปหน้า V11 Replay</a></p><div id="period" class="muted">กำลังโหลด...</div></div><div id="main"></div><div class="box"><h2>🧠 สถิติแยก Strategy</h2><div class="table"><table><thead><tr><th>Strategy</th><th>Evaluated</th><th>Trades</th><th>WIN</th><th>LOSS</th><th>WR</th><th>Net R</th><th>Expectancy</th></tr></thead><tbody id="strategies"></tbody></table></div></div><div class="box"><h2>📌 ความหมาย</h2><div class="muted">WIN/LOSS ใช้คำนวณ Win Rate, Profit Factor และ Expectancy; OPEN/AMBIGUOUS ถูกแยกไว้ ไม่ถูกนับเป็น WIN/LOSS; NO_TRADE ไม่ใช่ออเดอร์</div></div></main><script>const $=x=>document.getElementById(x);function esc(x){return String(x??'').replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[m])||m)}function n(x){return x==null?'—':Number(x).toFixed(4)}async function load(){const d=await(await fetch('/api/statistics')).json();if(d.status!=='ok'){$('main').innerHTML='<div class="box empty">'+esc(d.message||'ยังไม่มีข้อมูล')+'<br><br><a class="link" href="/replay">เริ่ม V11 Replay</a></div>';return}const p=d.performance;$('period').textContent='ช่วงทดสอบ: '+d.start+' ถึง '+d.end+' · '+(d.symbols||[]).join(' + ');const cards=[['Candles',p.rows],['Trades',p.trades],['WIN / LOSS',p.wins+' / '+p.losses],['Win Rate',p.win_rate+'%'],['Net R',n(p.net_r)],['Profit Factor',p.profit_factor??'—'],['Expectancy',n(p.expectancy_r)+' R'],['Max DD',n((d.reports||[]).reduce((m,r)=>Math.max(m,Number((r.performance||{}).max_drawdown_r||0)),0))+' R'],['OPEN',p.open],['AMBIGUOUS',p.ambiguous],['NO_TRADE',p.no_trade],['Signals',(d.reports||[]).reduce((s,r)=>s+Number(r.signals||0),0)]];$('main').innerHTML='<div class="box"><div class="cards">'+cards.map(c=>'<div class="card"><span class="muted">'+c[0]+'</span><b>'+esc(c[1])+'</b></div>').join('')+'</div></div>';$('strategies').innerHTML=Object.entries(d.strategies||{}).map(([name,s])=>'<tr><td><b>'+esc(name)+'</b></td><td>'+s.evaluated+'</td><td>'+s.trades+'</td><td class="win">'+s.wins+'</td><td class="loss">'+s.losses+'</td><td>'+s.win_rate+'%</td><td>'+n(s.net_r)+'</td><td>'+n(s.expectancy_r)+' R</td></tr>').join('')||'<tr><td colspan="8">ไม่มีข้อมูล</td></tr>'}load();setInterval(load,10000)</script></body></html>'''
