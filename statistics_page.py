"""V12.1 Statistics UI: M5-only."""
from __future__ import annotations
import json
from flask import Response
from v11.engine import ENGINE_VERSION

def _json(v,status=200):return Response(json.dumps(v,ensure_ascii=False,allow_nan=False,default=str),status=status,mimetype="application/json",headers={"Cache-Control":"no-store"})
def _live():
    try:
        from signal_history import history
        out=[]
        for row in history.list_signals(days=3650,limit=1000):
            x=dict(row)
            try:p=json.loads(x.get("payload_json") or "{}")
            except Exception:p={}
            l=p.get("trade_levels") or {};r=p.get("regime") or {};x.update({"engine_version":p.get("engine_version") or ENGINE_VERSION,"strategy":p.get("strategy") or "NONE","engine":p.get("engine") or "NONE","regime":r.get("regime") if isinstance(r,dict) else r,"setup_id":p.get("setup_id") or x.get("setup_key"),"entry_type":p.get("entry_type"),"setup_score":(p.get("setup_score") or {}).get("score") if isinstance(p.get("setup_score"),dict) else p.get("setup_score"),"entry":l.get("entry",x.get("entry")),"sl":l.get("sl",x.get("sl")),"tp":l.get("tp",x.get("tp")),"rr":l.get("risk_reward",l.get("effective_rr",x.get("risk_reward"))),"candle_time":p.get("candle_time") or p.get("closed_candle") or x.get("candle_time"),"timeframe_mode":"M5-only"});out.append(x)
        return out
    except Exception:return []
def _replay():
    try:
        import replay_web
        with replay_web._LOCK:return dict(replay_web._STATE)
    except Exception:return {"running":False,"result":None}
def _payload():
    live=_live();state=_replay();result=state.get("result");base={"engine_version":ENGINE_VERSION,"engine_name":"REGIME-8-ENGINE-REENTRY","source_contract":"V12.1","timeframe_mode":"M5-only","timeframes":["M5"],"live_signals":live,"live_signal_count":len(live),"live_orders_allowed":False}
    if state.get("running"):return {**base,"status":"running","running":True,"source":"LSE_HISTORICAL_M5_OHLCV","message":"V12 M5-only Historical Replay กำลังประมวลผล","backtest_window":state.get("request")}
    if not result:return {**base,"status":"no_replay","running":False,"source":"LSE_HISTORICAL_M5_OHLCV","message":"ยังไม่มีผล V12 M5-only Historical Replay","replay_trades":[],"performance":None,"strategies":{},"backtest_window":None}
    trades=[]
    for report in result.get("reports") or []:
        for t in report.get("trade_history") or []:trades.append({**t,"symbol":report.get("symbol")})
    w=sum(t.get("result")=="WIN" for t in trades);l=sum(t.get("result")=="LOSS" for t in trades);d=w+l;rs=[float(t.get("r_multiple") or 0) for t in trades if t.get("result") in ("WIN","LOSS")];net=round(sum(rs),4)
    strategies={}
    for t in trades:
        name=str(t.get("strategy") or "NONE");s=strategies.setdefault(name,{"trades":0,"wins":0,"losses":0,"net_r":0.0});res=t.get("result")
        if res in ("WIN","LOSS"):s["trades"]+=1;s["wins"]+=res=="WIN";s["losses"]+=res=="LOSS";s["net_r"]+=float(t.get("r_multiple") or 0)
    for s in strategies.values():
        decided=s["wins"]+s["losses"];s["net_r"]=round(s["net_r"],4);s["win_rate"]=round(100*s["wins"]/decided,2) if decided else 0.0;s["expectancy_r"]=round(s["net_r"]/decided,4) if decided else 0.0
    reports=[{"symbol":r.get("symbol"),"candles_evaluated":r.get("candles_evaluated"),"signals":r.get("signals"),"wins":r.get("wins"),"losses":r.get("losses"),"net_r":r.get("net_r"),"performance":r.get("performance")} for r in result.get("reports") or []]
    return {**base,"status":"ok","running":False,"source":"LSE_HISTORICAL_M5_OHLCV","backtest_window":{"start":result.get("start"),"end":result.get("end"),"symbols":result.get("symbols")},"performance":{"trades":len(trades),"decided":d,"wins":w,"losses":l,"win_rate":round(100*w/d,2) if d else 0.0,"net_r":net,"expectancy_r":round(net/d,4) if d else 0.0},"symbol_reports":reports,"strategies":strategies,"replay_trades":sorted(trades,key=lambda x:str(x.get("candle_time") or ""),reverse=True)}
def register(app):
    @app.route("/statistics",strict_slashes=False)
    def statistics_page():return Response(PAGE,mimetype="text/html",headers={"Cache-Control":"no-store"})
    @app.route("/api/statistics",strict_slashes=False)
    def statistics_api():return _json(_payload())
    try:
        import replay_web
        replay_web.register(app)
    except Exception:pass
PAGE='''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V12.1 M5-only Statistics</title><style>body{font-family:system-ui;background:#0b1220;color:#e8eef8;margin:0;padding:20px}main{max-width:1600px;margin:auto}.box{background:#121c30;border:1px solid #263654;border-radius:14px;padding:16px;margin:12px 0}.muted{color:#93a4bd}.table{overflow:auto;max-height:650px}table{width:100%;border-collapse:collapse}th,td{padding:7px;border-bottom:1px solid #263654;white-space:nowrap;text-align:left}th{position:sticky;top:0;background:#172238}.link{color:#70a7ff}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.card{background:#172238;padding:12px;border-radius:10px}</style></head><body><main><div class="box"><h1>📊 V12.1 Statistics — M5-only</h1><div class="muted">REGIME-8 ENGINE + CONTROLLED RE-ENTRY · M5 Context + M5 Entry · ไม่มี M15</div><p><a class="link" href="/replay">⏪ V12 M5-only Historical Replay</a></p><div id="msg"></div></div><div id="summary" class="box"></div><div class="box"><h2>📈 Backtest by Asset</h2><div class="table"><table><thead><tr><th>Asset</th><th>Candles</th><th>Signals</th><th>WIN</th><th>LOSS</th><th>Win Rate</th><th>Net R</th></tr></thead><tbody id="assets"></tbody></table></div></div><div class="box"><h2>🧠 Strategy Results</h2><div class="table"><table><thead><tr><th>Strategy</th><th>Trades</th><th>WIN</th><th>LOSS</th><th>Win Rate</th><th>Net R</th><th>Expectancy R</th></tr></thead><tbody id="strategies"></tbody></table></div></div><div class="box"><h2>📡 V12 M5-only Live Signals</h2><div class="table"><table><thead><tr><th>เวลา</th><th>Asset</th><th>Side</th><th>Regime</th><th>Engine</th><th>Strategy</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>Score</th><th>Signal ID</th></tr></thead><tbody id="live"></tbody></table></div></div><div class="box"><h2>📜 V12 M5-only Historical Replay</h2><div class="table"><table><thead><tr><th>เวลา</th><th>Asset</th><th>Side</th><th>Strategy</th><th>Entry</th><th>SL</th><th>TP</th><th>Result</th><th>R</th></tr></thead><tbody id="replay"></tbody></table></div></div></main><script>const $=x=>document.getElementById(x),e=x=>String(x??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));const n=x=>x==null?'—':Number(x).toFixed(4);async function load(){let d=await(await fetch('/api/statistics?ts='+Date.now(),{cache:'no-store'})).json();$('msg').innerHTML=(d.message||'V12 M5-only')+(d.backtest_window?'<br><b>Backtest:</b> '+e(d.backtest_window.start)+' → '+e(d.backtest_window.end)+' · '+e((d.backtest_window.symbols||[]).join(', ')):'' );let p=d.performance||{};$('summary').innerHTML='<div class="grid"><div class="card"><b>Trades</b><br>'+e(p.trades??0)+'</div><div class="card"><b>WIN / LOSS</b><br>'+e(p.wins??0)+' / '+e(p.losses??0)+'</div><div class="card"><b>Win Rate</b><br>'+e(p.win_rate??0)+'%</div><div class="card"><b>Net R</b><br>'+e(p.net_r??0)+'</div><div class="card"><b>Expectancy</b><br>'+e(p.expectancy_r??0)+'R</div></div>';$('assets').innerHTML=(d.symbol_reports||[]).map(x=>'<tr><td>'+e(x.symbol)+'</td><td>'+e(x.candles_evaluated??0)+'</td><td>'+e(x.signals??0)+'</td><td>'+e(x.wins??0)+'</td><td>'+e(x.losses??0)+'</td><td>'+e(x.performance?.win_rate??0)+'%</td><td>'+e(x.net_r??0)+'</td></tr>').join('');$('strategies').innerHTML=Object.entries(d.strategies||{}).map(([k,x])=>'<tr><td>'+e(k)+'</td><td>'+e(x.trades)+'</td><td>'+e(x.wins)+'</td><td>'+e(x.losses)+'</td><td>'+e(x.win_rate)+'%</td><td>'+e(x.net_r)+'</td><td>'+e(x.expectancy_r)+'</td></tr>').join('');$('live').innerHTML=(d.live_signals||[]).map(x=>'<tr><td>'+e(x.candle_time||x.created_at)+'</td><td>'+e(x.symbol)+'</td><td>'+e(x.direction||x.signal)+'</td><td>'+e(x.regime||'—')+'</td><td>'+e(x.engine||'—')+'</td><td>'+e(x.strategy||'NONE')+'</td><td>'+n(x.entry)+'</td><td>'+n(x.sl)+'</td><td>'+n(x.tp)+'</td><td>'+n(x.rr)+'</td><td>'+e(x.setup_score??'—')+'</td><td>'+e(x.signal_id||'—')+'</td></tr>').join('');$('replay').innerHTML=(d.replay_trades||[]).map(x=>'<tr><td>'+e(x.candle_time)+'</td><td>'+e(x.symbol)+'</td><td>'+e(x.signal)+'</td><td>'+e(x.strategy)+'</td><td>'+n(x.trade_levels?.entry)+'</td><td>'+n(x.trade_levels?.sl)+'</td><td>'+n(x.trade_levels?.tp)+'</td><td>'+e(x.result)+'</td><td>'+n(x.r_multiple)+'</td></tr>').join('')}load();setInterval(load,15000)</script></body></html>'''
