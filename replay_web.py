"""V12.2 Historical Replay web service: H1 bias + M15 regime + M5 trigger, isolated from live statistics."""
from __future__ import annotations
import json,os,threading
from datetime import timedelta
from pathlib import Path
import pandas as pd
from flask import Response,request
from v11.engine import ENGINE_VERSION

LOCK=threading.RLock();_LOCK=LOCK
RESULT_PATH=Path(os.getenv("V12_BACKTEST_RESULTS","backtest_results.json"));_STATE={"running":False,"status":"idle","result":None,"error":None,"output":[]}
REPLAY_VERSION=ENGINE_VERSION

def _json(v,status=200):return Response(json.dumps(v,ensure_ascii=False,default=str),status=status,mimetype="application/json",headers={"Cache-Control":"no-store"})
def _persist(result):
    tmp=RESULT_PATH.with_suffix(".tmp");tmp.write_text(json.dumps(result,ensure_ascii=False,default=str,allow_nan=False),encoding="utf-8");tmp.replace(RESULT_PATH)
def _fetch_history(symbol,timeframe,start,end,progress=None):
    from lse import LSE
    from v11.replay_m5 import REPLAY_M5_CONTEXT_BARS,REPLAY_M15_CONTEXT_BARS,REPLAY_H1_CONTEXT_BARS
    minutes={"5m":5,"15m":15,"1h":60}[timeframe];warmup_bars={"5m":REPLAY_M5_CONTEXT_BARS,"15m":REPLAY_M15_CONTEXT_BARS,"1h":REPLAY_H1_CONTEXT_BARS}[timeframe];warmup=start-timedelta(minutes=minutes*warmup_bars);market={"BTC":"BTC/USD","GOLD":"XAU/USD"}[symbol];client=LSE(api_key=os.environ["LSE_API_KEY"]);first_day=warmup.date();last_day=(end-pd.Timedelta(nanoseconds=1)).date();frames=[];days=[];day=pd.Timestamp(first_day);last=pd.Timestamp(last_day)
    while day<=last:
        api_start=day.date().isoformat();api_end=(day+pd.Timedelta(days=1)).date().isoformat()
        if progress:progress("data_fetch",symbol=symbol,timeframe=timeframe,day=api_start,completed=len(days),total=int((last-day).days)+1)
        raw=client.candles(market,timeframe,start=api_start,end=api_end,limit=1000,order="asc");rows=raw.get("data") if isinstance(raw,dict) else raw
        if isinstance(rows,dict):rows=rows.get("data") or rows.get("rows")
        if not isinstance(rows,(list,tuple)):raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:{timeframe}:{api_start}")
        frame=pd.DataFrame(rows)
        for candidate in ("timestamp","time","date"):
            if "datetime" not in frame.columns and candidate in frame.columns:frame=frame.rename(columns={candidate:"datetime"})
        required=("datetime","open","high","low","close");missing=[c for c in required if c not in frame.columns]
        if missing:raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:{timeframe}:missing={missing}:day={api_start}")
        frame["datetime"]=pd.to_datetime(frame["datetime"],utc=True,errors="coerce")
        for c in required[1:]:frame[c]=pd.to_numeric(frame[c],errors="coerce")
        frame=frame.dropna(subset=list(required)).sort_values("datetime").drop_duplicates("datetime",keep="last").reset_index(drop=True);frames.append(frame);days.append(api_start);day+=pd.Timedelta(days=1)
    if not frames:raise RuntimeError(f"NO_HISTORICAL_DATA:{symbol}:{timeframe}")
    frame=pd.concat(frames,ignore_index=True).sort_values("datetime").drop_duplicates("datetime",keep="last").reset_index(drop=True)
    target=frame[(frame["datetime"]>=start)&(frame["datetime"]<end)].copy()
    if timeframe=="5m" and target.empty:raise RuntimeError(f"NO_TARGET_HISTORICAL_M5:{symbol}:{start.isoformat()}:{end.isoformat()}")
    return frame,{"timeframe":timeframe,"historical_rows":len(frame),"target_rows":len(target),"warmup_bars":warmup_bars,"api_start":days[0],"api_end":days[-1],"calendar_days_fetched":len(days)}
def _worker(symbols,start,end,start_label,end_label):
    try:
        from v11.replay_m5 import replay_frames
        reports=[];data_quality=[]
        with _LOCK:_STATE["output"]=["Fetching real LSE historical H1/M15/M5 data..."]
        for symbol in symbols:
            m5,q5=_fetch_history(symbol,"5m",start,end,progress=lambda event,**kw:_set_progress(event,**kw));m15,q15=_fetch_history(symbol,"15m",start,end,progress=lambda event,**kw:_set_progress(event,**kw));h1,q1=_fetch_history(symbol,"1h",start,end,progress=lambda event,**kw:_set_progress(event,**kw));report=replay_frames(m5,m15,h1,symbol,start_time=start,end_time=end,progress_callback=lambda event,**kw:_set_progress(event,**kw));report["data_quality"]={"m5":q5,"m15":q15,"h1":q1};reports.append(report);data_quality.append({"symbol":symbol,"m5":q5,"m15":q15,"h1":q1})
        result={"status":"completed","engine_version":ENGINE_VERSION,"engine_name":"REGIME-8-ENGINE-REENTRY","source":"LSE_HISTORICAL_MTF_OHLCV","lookahead_safe":True,"timeframe_mode":"MTF:H1→M15→M5","mtf_policy":"H1_BIAS_M15_REGIME_M5_TRIGGER","symbols":symbols,"start":str(start),"end":str(end),"requested_window":{"start":start_label,"end":end_label},"data_quality":data_quality,"reports":reports};_persist(result)
        with _LOCK:_STATE.update({"running":False,"status":"completed","result":result,"error":None,"output":["Replay completed"]})
    except Exception as exc:
        with _LOCK:_STATE.update({"running":False,"status":"failed","error":f"{type(exc).__name__}: {exc}","output":["Replay failed"]})
def _set_progress(event,**kw):
    with _LOCK:_STATE["progress"]={"event":event,**kw}
def _parse_request():
    from v11.replay_m5 import normalize_replay_window
    start=request.args.get("start") or "2026-08-21";end=request.args.get("end") or "2026-08-24";return normalize_replay_window(start,end),start,end
def register(app):
    @app.route("/replay",strict_slashes=False)
    def replay_page():return Response(PAGE,mimetype="text/html",headers={"Cache-Control":"no-store"})
    @app.route("/api/replay/status",strict_slashes=False)
    def replay_status():
        with _LOCK:
            state=dict(_STATE)
            if state.get("result") is None and RESULT_PATH.exists():
                try:state["result"]=json.loads(RESULT_PATH.read_text(encoding="utf-8"));state["status"]="completed"
                except Exception:pass
            return _json(state)
    @app.route("/api/replay/start",methods=["GET","POST"],strict_slashes=False)
    def replay_start():
        with _LOCK:
            if _STATE["running"]:return _json({"status":"busy"},409)
            symbols=[s for s in (request.args.get("symbols") or "BTC,GOLD").upper().split(",") if s in ("BTC","GOLD")] or ["BTC","GOLD"]
            try:(start,end),start_label,end_label=_parse_request()
            except ValueError as exc:return _json({"status":"error","message":str(exc)},400)
            _STATE.update({"running":True,"status":"running","result":None,"error":None,"output":[],"progress":None,"request":{"symbols":symbols,"start":start_label,"end":end_label}})
        threading.Thread(target=_worker,args=(symbols,start,end,start_label,end_label),name="v12-mtf-replay",daemon=True).start();return _json({"status":"started","engine_version":REPLAY_VERSION,"source":"LSE_HISTORICAL_MTF_OHLCV","timeframe_mode":"MTF:H1→M15→M5","start":start_label,"end":end_label},202)
PAGE='''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V12.2 MTF Historical Replay</title><style>body{font-family:system-ui;background:#0b1220;color:#e8eef8;padding:20px}main{max-width:1100px;margin:auto}.box{background:#121c30;border:1px solid #263654;border-radius:14px;padding:18px;margin:12px 0}button,a{padding:10px 14px;border-radius:8px;background:#172238;color:#fff;text-decoration:none;border:1px solid #33425e;cursor:pointer}.muted{color:#93a4bd}</style></head><body><main><div class="box"><h1>⏪ V12.2 Historical Replay — MTF</h1><p class="muted">Engine: '''+REPLAY_VERSION+''' · LSE Historical · H1 Big Trend/Bias → M15 Trend/Regime Filter → M5 Setup/Entry Trigger · Lookahead-safe · Replay แยกจาก Live statistics</p><p><label>เริ่ม <input id="start" value="2026-08-21"></label> <label>ถึง <input id="end" value="2026-08-24"></label></p><button onclick="start()">▶ เริ่ม Replay</button> <a href="/statistics">📊 Statistics</a><span id="s" class="muted"> สถานะ: idle</span></div><div class="box"><div id="out">ยังไม่มีผล</div></div></main><script>const $=x=>document.getElementById(x);async function start(){let q=new URLSearchParams({symbols:'BTC,GOLD',start:$('start').value,end:$('end').value});await fetch('/api/replay/start?'+q.toString());poll()}async function poll(){let d=await(await fetch('/api/replay/status?ts='+Date.now(),{cache:'no-store'})).json();$('s').textContent='สถานะ: '+d.status+' · Engine: '+(d.result?.engine_version||d.engine_version||'V12.2');if(d.progress){let p=d.progress;$('out').textContent=(p.event==='data_fetch'?'กำลังโหลด LSE '+(p.timeframe||'')+': '+p.symbol+' '+p.day+' ('+(p.completed||0)+'/'+(p.total||0)+')':'กำลังประมวลผล '+p.symbol+': '+(p.percent??0)+'% · signals '+(p.trades??0)+' · WIN '+(p.wins??0)+' · LOSS '+(p.losses??0)+' · Net R '+(p.net_r??0))}if(d.result?.reports){$('out').innerHTML='<p><b>Engine:</b> '+d.result.engine_version+' · MTF: H1 → M15 → M5 · ช่วง: '+d.result.requested_window.start+' → '+d.result.requested_window.end+'</p>'+d.result.data_quality.map(q=>'<p><b>'+q.symbol+'</b> H1: '+q.h1.historical_rows+' · M15: '+q.m15.historical_rows+' · M5 Target: '+q.m5.target_rows+'</p>').join('')+d.result.reports.map(r=>{let p=r.performance||{};return '<h2>'+r.symbol+'</h2><p>Candles: '+(r.candles_evaluated??0)+' · Signals: '+(r.signals??0)+' · WIN: '+(p.wins??0)+' · LOSS: '+(p.losses??0)+' · Win Rate: '+(p.win_rate??0)+'% · Net R: '+(r.net_r??0)+'</p>'}).join('')}else if(d.error)$('out').textContent=d.error;if(d.running)setTimeout(poll,1000)}poll()</script></body></html>'''
