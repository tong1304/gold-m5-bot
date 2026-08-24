"""V12.2 Statistics UI: MTF H1/M15/M5."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from flask import Response
from v11.engine import ENGINE_VERSION
BANGKOK=ZoneInfo("Asia/Bangkok")
UI_VERSION="V12.2"
SOURCE_CONTRACT="V12.2"
def _json(v,status=200):return Response(json.dumps(v,ensure_ascii=False,allow_nan=False,default=str),status=status,mimetype="application/json",headers={"Cache-Control":"no-store"})
def _bangkok_display_time(value):
    if not value:return "—"
    try:
        dt=datetime.fromisoformat(str(value).strip().replace("Z","+00:00"))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BANGKOK).strftime("%d/%m/%Y %H:%M:%S")
    except (TypeError,ValueError):return str(value).replace("+00:00","").replace("+00","")
def _no_trade_reason(payload):
    if not isinstance(payload,dict):return "—"
    reasons=payload.get("no_trade_reasons") or payload.get("rejection_reasons") or []
    if isinstance(reasons,str):reasons=[reasons]
    return " · ".join(str(x) for x in reasons if str(x).strip()) or "—"
def _live():
    try:
        from signal_history import history
        out=[]
        for row in history.list_signals(days=3650,limit=1000):
            x=dict(row)
            try:p=json.loads(x.get("payload_json") or "{}")
            except Exception:p={}
            l=p.get("trade_levels") or {};r=p.get("regime") or {};raw_time=p.get("candle_time") or p.get("closed_candle") or x.get("candle_time") or x.get("created_at")
            x.update({"engine_version":p.get("engine_version") or ENGINE_VERSION,"strategy":p.get("strategy") or "NONE","engine":p.get("engine") or "NONE","regime":r.get("regime") if isinstance(r,dict) else r,"h1_bias":p.get("h1_bias") or (r.get("h1_bias") if isinstance(r,dict) else None),"m15_regime":p.get("m15_regime") or (r.get("m15_regime") if isinstance(r,dict) else None),"setup_id":p.get("setup_id") or x.get("setup_key"),"entry_type":p.get("entry_type"),"setup_score":(p.get("setup_score") or {}).get("score") if isinstance(p.get("setup_score"),dict) else p.get("setup_score"),"entry":l.get("entry",x.get("entry")),"sl":l.get("sl",x.get("sl")),"tp":l.get("tp",x.get("tp")),"rr":l.get("risk_reward",l.get("effective_rr",x.get("risk_reward"))),"candle_time":raw_time,"display_time":_bangkok_display_time(raw_time),"no_trade_reason":_no_trade_reason(p),"timeframe_mode":"MTF:H1→M15→M5"});out.append(x)
        return out
    except Exception:return []
def _replay():
    try:
        import replay_web
        with replay_web._LOCK:
            if replay_web._STATE.get("result") is not None:return dict(replay_web._STATE)
    except Exception:pass
    path=Path("backtest_results.json")
    if path.exists():
        try:return {"running":False,"status":"completed","result":json.loads(path.read_text(encoding="utf-8")),"error":None}
        except Exception:pass
    return {"running":False,"result":None}
def _payload():
    live=_live();state=_replay();result=state.get("result");base={"engine_version":ENGINE_VERSION,"ui_version":UI_VERSION,"engine_name":"REGIME-8-ENGINE-REENTRY","source_contract":SOURCE_CONTRACT,"timeframe_mode":"MTF:H1→M15→M5","timeframes":["H1","M15","M5"],"mtf_policy":"H1_BIAS_M15_REGIME_M5_TRIGGER","live_signals":live,"live_signal_count":len(live),"live_orders_allowed":False}
    if state.get("running"):return {**base,"status":"running","running":True,"source":"LSE_HISTORICAL_MTF_OHLCV","message":"V12.2 MTF Historical Replay กำลังประมวลผล","backtest_window":state.get("request")}
    if not result:return {**base,"status":"no_replay","running":False,"source":"LSE_HISTORICAL_MTF_OHLCV","message":"ยังไม่มีผล V12.2 MTF Historical Replay","replay_trades":[],"performance":None,"strategies":{},"backtest_window":None}
    trades=[]
    for report in result.get("reports") or []:
        for t in report.get("trade_history") or []:
            item={**t,"symbol":report.get("symbol"),"display_time":_bangkok_display_time(t.get("candle_time") or t.get("created_at"))};trades.append(item)
    w=sum(t.get("result")=="WIN" for t in trades);l=sum(t.get("result")=="LOSS" for t in trades);d=w+l;rs=[float(t.get("r_multiple") or 0) for t in trades if t.get("result") in ("WIN","LOSS")];net=round(sum(rs),4);strategies={}
    for t in trades:
        name=str(t.get("strategy") or "NONE");s=strategies.setdefault(name,{"trades":0,"wins":0,"losses":0,"net_r":0.0});res=t.get("result")
        if res in ("WIN","LOSS"):s["trades"]+=1;s["wins"]+=res=="WIN";s["losses"]+=res=="LOSS";s["net_r"]+=float(t.get("r_multiple") or 0)
    for s in strategies.values():
        decided=s["wins"]+s["losses"];s["net_r"]=round(s["net_r"],4);s["win_rate"]=round(100*s["wins"]/decided,2) if decided else 0.0;s["expectancy_r"]=round(s["net_r"]/decided,4) if decided else 0.0
    reports=[{"symbol":r.get("symbol"),"candles_evaluated":r.get("candles_evaluated"),"signals":r.get("signals"),"wins":r.get("wins"),"losses":r.get("losses"),"net_r":r.get("net_r"),"performance":r.get("performance")} for r in result.get("reports") or []]
    return {**base,"status":"ok","running":False,"source":result.get("source","LSE_HISTORICAL_MTF_OHLCV"),"lookahead_safe":result.get("lookahead_safe",True),"backtest_window":{"start":result.get("start"),"end":result.get("end"),"symbols":result.get("symbols")},"performance":{"trades":len(trades),"decided":d,"wins":w,"losses":l,"win_rate":round(100*w/d,2) if d else 0.0,"net_r":net,"expectancy_r":round(net/d,4) if d else 0.0},"symbol_reports":reports,"strategies":strategies,"replay_trades":sorted(trades,key=lambda x:str(x.get("candle_time") or ""),reverse=True)}
def register(app):
    @app.route("/statistics",strict_slashes=False)
    def statistics_page():return Response(PAGE,mimetype="text/html",headers={"Cache-Control":"no-store"})
    @app.route("/api/statistics",strict_slashes=False)
    def statistics_api():return _json(_payload())
    try:
        import replay_web;replay_web.register(app)
    except Exception:pass
PAGE='''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V12.2 MTF Statistics</title><style>body{font-family:system-ui;background:#0b1220;color:#e8eef8;margin:0;padding:20px}main{max-width:1700px;margin:auto}.box{background:#121c30;border:1px solid #263654;border-radius:14px;padding:16px;margin:12px 0}.muted{color:#93a4bd}.table{overflow:auto;max-height:650px}table{width:100%;border-collapse:collapse}th,td{padding:7px;border-bottom:1px solid #263654;white-space:nowrap;text-align:left}th{position:sticky;top:0;background:#172238}.link{color:#70a7ff}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.card{background:#172238;padding:12px;border-radius:10px}.reason{white-space:normal;min-width:280px;max-width:520px;color:#ffcf7a}</style></head><body><main><div class="box"><h1>📊 V12.2 Statistics — MTF</h1><div class="muted">H1 Big Trend/Bias → M15 Trend/Regime Filter → M5 Setup/Entry Trigger · 8 Engines · RR Engine</div><p><a class="link" href="/replay">⏪ V12.2 MTF Historical Replay</a></p><div id="msg"></div></div><div id="summary" class="box"></div><div class="box"><h2>📈 Backtest by Asset</h2><div class="table"><table><thead><tr><th>Asset</th><th>Candles</th><th>Signals</th><th>WIN</th><th>LOSS</th><th>Win Rate</th><th>Net R</th></tr></thead><tbody id="assets"></tbody></table></div></div><div class="box"><h2>🧠 Strategy Results</h2><div class="table"><table><thead><tr><th>Strategy</th><th>Trades</th><th>WIN</th><th>LOSS</th><th>Win Rate</th><th>Net R</th><th>Expectancy R</th></tr></thead><tbody id="strategies"></tbody></table></div></div><div class="box"><h2>📡 V12.2 MTF Live Signals</h2><div class="muted">เวลาแสดงเป็นเขตกรุงเทพ ประเทศไทย (Asia/Bangkok, UTC+7)</div><div class="table"><table><thead><tr><th>เวลา (Bangkok)</th><th>Asset</th><th>Side</th><th>H1 Bias</th><th>M15 Regime</th><th>Engine</th><th>Strategy</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>Score</th><th>เหตุผล No Trade</th></tr></thead><tbody id="live"></tbody></table></div></div><div class="box"><h2>📜 V12.2 MTF Historical Replay</h2><div class="muted">เวลาแสดงเป็นเขตกรุงเทพ ประเทศไทย (UTC+7) · ผล Replay แยกจาก Live</div><div class="table"><table><thead><tr><th>เวลา (Bangkok)</th><th>Asset</th><th>Side</th><th>Strategy</th><th>Entry</th><th>SL</th><th>TP</th><th>Result</th><th>R</th></tr></thead><tbody id="replay"></tbody></table></div></div></main><script>const $=x=>document.getElementById(x),e=x=>String(x??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));const n=x=>x==null?'—':Number(x).toFixed(4);async function load(){let d=await(await fetch('/api/statistics?ts='+Date.now(),{cache:'no-store'})).json();$('msg').innerHTML=(d.message||'V12.2 MTF')+(d.backtest_window?'<br><b>Backtest:</b> '+e(d.backtest_window.start)+' → '+e(d.backtest_window.end)+' · '+e((d.backtest_window.symbols||[]).join(', ')):'' );let p=d.performance||{};$('summary').innerHTML='<div class="grid"><div class="card"><b>Engine</b><br>'+e(d.engine_version||'V12.2')+'</div><div class="card"><b>Trades</b><br>'+e(p.trades??0)+'</div><div class="card"><b>WIN / LOSS</b><br>'+e(p.wins??0)+' / '+e(p.losses??0)+'</div><div class="card"><b>Win Rate</b><br>'+e(p.win_rate??0)+'%</div><div class="card"><b>Net R</b><br>'+e(p.net_r??0)+'</div><div class="card"><b>Expectancy</b><br>'+e(p.expectancy_r??0)+'R</div></div>';$('assets').innerHTML=(d.symbol_reports||[]).map(x=>'<tr><td>'+e(x.symbol)+'</td><td>'+e(x.candles_evaluated??0)+'</td><td>'+e(x.signals??0)+'</td><td>'+e(x.wins??0)+'</td><td>'+e(x.losses??0)+'</td><td>'+e(x.performance?.win_rate??0)+'%</td><td>'+e(x.net_r??0)+'</td></tr>').join('');$('strategies').innerHTML=Object.entries(d.strategies||{}).map(([k,x])=>'<tr><td>'+e(k)+'</td><td>'+e(x.trades)+'</td><td>'+e(x.wins)+'</td><td>'+e(x.losses)+'</td><td>'+e(x.win_rate)+'%</td><td>'+e(x.net_r)+'</td><td>'+e(x.expectancy_r)+'</td></tr>').join('');$('live').innerHTML=(d.live_signals||[]).map(x=>'<tr><td>'+e(x.display_time||x.candle_time||x.created_at)+'</td><td>'+e(x.symbol)+'</td><td>'+e(x.direction||x.signal)+'</td><td>'+e(x.h1_bias||'—')+'</td><td>'+e(x.m15_regime||'—')+'</td><td>'+e(x.engine||'—')+'</td><td>'+e(x.strategy||'NONE')+'</td><td>'+n(x.entry)+'</td><td>'+n(x.sl)+'</td><td>'+n(x.tp)+'</td><td>'+n(x.rr)+'</td><td>'+e(x.setup_score??'—')+'</td><td class="reason">'+e(x.no_trade_reason||'—')+'</td></tr>').join('');$('replay').innerHTML=(d.replay_trades||[]).map(x=>'<tr><td>'+e(x.display_time||x.candle_time)+'</td><td>'+e(x.symbol)+'</td><td>'+e(x.signal)+'</td><td>'+e(x.strategy)+'</td><td>'+n(x.trade_levels?.entry)+'</td><td>'+n(x.trade_levels?.sl)+'</td><td>'+n(x.trade_levels?.tp)+'</td><td>'+e(x.result)+'</td><td>'+n(x.r_multiple)+'</td></tr>').join('')}load();setInterval(load,15000)</script></body></html>'''