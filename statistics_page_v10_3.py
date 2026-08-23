"""V10.3 statistics page: strategy-level results and rejection diagnostics."""
from __future__ import annotations
import json, sqlite3
from flask import Response, request
from signal_history import DEFAULT_DB
from strategy_engine import BTC_STRATEGIES, GOLD_STRATEGIES

def _rows(days=30,symbol=None):
    days=max(1,min(int(days),3650)); where=["datetime(created_at)>=datetime('now', ?)"]; params=[f"-{days} days"]
    if symbol in ("BTC","GOLD"):where.append("symbol=?");params.append(symbol)
    q=f"SELECT * FROM signals WHERE {' AND '.join(where)} ORDER BY datetime(created_at) DESC LIMIT 10000"; conn=sqlite3.connect(DEFAULT_DB);conn.row_factory=sqlite3.Row
    try:return [dict(r) for r in conn.execute(q,params).fetchall()]
    finally:conn.close()

def _build(days=30,symbol=None):
    rows=_rows(days,symbol); names=(BTC_STRATEGIES if symbol=="BTC" else GOLD_STRATEGIES if symbol=="GOLD" else tuple(dict.fromkeys(BTC_STRATEGIES+GOLD_STRATEGIES)))
    stats={n:{"evaluated":0,"pass":0,"fail":0,"not_applicable":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"reasons":{}} for n in names}
    overall={"rows":len(rows),"trades":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"net_r":0.0}
    for row in rows:
        try:p=json.loads(row.get("payload_json") or "{}")
        except Exception:p={}
        if str(p.get("engine_version","")).startswith("10.3") or str(p.get("engine_version","")).startswith("10.0"):
            for c in p.get("strategy_candidates") or []:
                n=c.get("strategy");
                if n not in stats:stats[n]={"evaluated":0,"pass":0,"fail":0,"not_applicable":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"reasons":{}}
                s=stats[n];s["evaluated"]+=1; st=c.get("status","FAIL").lower();
                if st in ("pass","fail","not_applicable"):s[st]+=1
                for reason in c.get("reason") or []:s["reasons"][reason]=s["reasons"].get(reason,0)+1
        result=row.get("result");
        if result=="NO_TRADE":overall["no_trade"]+=1
        elif result in ("WIN","LOSS","OPEN","AMBIGUOUS"):
            overall["trades"]+=1; overall["wins"]+=result=="WIN"; overall["losses"]+=result=="LOSS"; overall["open"]+=result=="OPEN"; overall["ambiguous"]+=result=="AMBIGUOUS"
            overall["net_r"]+=float(row.get("r_multiple") or 0) if result in ("WIN","LOSS") else 0
            try:n=p.get("strategy");
            except Exception:n=None
            if n in stats:stats[n][{"WIN":"wins","LOSS":"losses","OPEN":"open","AMBIGUOUS":"ambiguous"}[result]]+=1
    for s in stats.values():s["win_rate"]=round(100*s["wins"]/(s["wins"]+s["losses"]),2) if s["wins"]+s["losses"] else 0;s["top_rejections"]=sorted(s.pop("reasons").items(),key=lambda x:x[1],reverse=True)[:10]
    overall["net_r"]=round(overall["net_r"],4);overall["win_rate"]=round(100*overall["wins"]/(overall["wins"]+overall["losses"]),2) if overall["wins"]+overall["losses"] else 0
    return {"status":"ok","engine_version":"10.3-MULTI-M15-M5","period_days":days,"symbol":symbol or "ALL","overall":overall,"strategies":stats}

def register(app):
    @app.route("/statistics",strict_slashes=False)
    def page():return Response(PAGE,mimetype="text/html")
    @app.route("/api/statistics",strict_slashes=False)
    def api():
        try:return Response(json.dumps(_build(int(request.args.get("days",30)),request.args.get("symbol")),ensure_ascii=False),mimetype="application/json")
        except Exception as e:return Response(json.dumps({"status":"error","message":f"{type(e).__name__}: {e}"},ensure_ascii=False),status=500,mimetype="application/json")

PAGE=r'''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V10.3 Strategy Statistics</title><style>body{font-family:system-ui,sans-serif;background:#0b1220;color:#e8eef8;margin:0;padding:20px}main{max-width:1200px;margin:auto}.box{background:#121c30;border:1px solid #263654;border-radius:14px;padding:16px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.card{background:#172238;padding:12px;border-radius:10px}.muted{color:#93a4bd}select,input,button{background:#172238;color:#fff;border:1px solid #33425e;border-radius:8px;padding:9px}button{cursor:pointer}.table{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #263654;text-align:left;vertical-align:top}th{color:#9db2d0}.pass{color:#55d68b}.fail{color:#ffb454}.na{color:#93a4bd}.reason{font-size:12px;color:#ffb454}.controls{display:flex;gap:8px;flex-wrap:wrap}@media(max-width:800px){.grid{grid-template-columns:1fr 1fr}}@media(max-width:500px){.grid{grid-template-columns:1fr}}</style></head><body><main><div class="box"><h1>📊 V10.3 Strategy Evaluation</h1><div class="muted">M15 Context + M5 Setup/Trigger · BTC 5 strategies · GOLD 6 strategies · ไม่มี H1 · ไม่มี weighted confluence</div><div class="controls" style="margin-top:12px"><input id="days" type="number" min="1" max="3650" value="30"><select id="symbol"><option value="">BTC + GOLD</option><option>BTC</option><option>GOLD</option></select><button onclick="load()">Refresh</button><a href="/replay" style="color:#70a7ff;padding:9px">⏪ Replay</a></div></div><div class="box"><div id="overall" class="grid"></div></div><div class="box"><h2>Strategy Evaluation Log</h2><div class="table"><table><thead><tr><th>Strategy</th><th>Evaluated</th><th>PASS</th><th>FAIL</th><th>N/A</th><th>WIN</th><th>LOSS</th><th>WR</th><th>เงื่อนไขที่แพ้บ่อย</th></tr></thead><tbody id="body"></tbody></table></div></div></main><script>const $=id=>document.getElementById(id);function esc(x){return String(x).replace(/[&<>\"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]))}async function load(){const q=new URLSearchParams({days:$('days').value});if($('symbol').value)q.set('symbol',$('symbol').value);const d=await (await fetch('/api/statistics?'+q)).json();if(d.status!=='ok'){alert(d.message||'statistics error');return}const o=d.overall;$('overall').innerHTML=[['Rows',o.rows],['Trades',o.trades],['WIN / LOSS',o.wins+' / '+o.losses],['Win Rate',o.win_rate+'%'],['NO_TRADE',o.no_trade],['Net R',o.net_r]].map(x=>`<div class="card"><div class="muted">${x[0]}</div><b>${x[1]}</b></div>`).join('');$('body').innerHTML=Object.entries(d.strategies).map(([n,s])=>`<tr><td><b>${esc(n)}</b></td><td>${s.evaluated}</td><td class="pass">${s.pass}</td><td class="fail">${s.fail}</td><td class="na">${s.not_applicable}</td><td>${s.wins}</td><td>${s.losses}</td><td>${s.win_rate}%</td><td>${(s.top_rejections||[]).map(x=>`<div class="reason">${esc(x[0])} × ${x[1]}</div>`).join('')}</td></tr>`).join('')}load();setInterval(load,10000)</script></body></html>'''
