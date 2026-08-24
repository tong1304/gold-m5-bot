"""V12.1 Historical Replay web service: M5-only, persistent and isolated from live statistics."""
from __future__ import annotations
import json,os,threading
from datetime import timedelta
from pathlib import Path
import pandas as pd
from flask import Response,request
_LOCK=threading.RLock();RESULT_PATH=Path(os.getenv("V12_BACKTEST_RESULTS","backtest_results.json"));_STATE={"running":False,"status":"idle","result":None,"error":None,"output":[]}

def _json(v,status=200):return Response(json.dumps(v,ensure_ascii=False,default=str),status=status,mimetype="application/json",headers={"Cache-Control":"no-store"})

def _persist(result):
    tmp=RESULT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,default=str,allow_nan=False),encoding="utf-8")
    tmp.replace(RESULT_PATH)

def _historical_m5(symbol,start,end):
    from lse import LSE
    from v11.replay_m5 import REPLAY_M5_CONTEXT_BARS
    market={"BTC":"BTC/USD","GOLD":"XAU/USD"}[symbol]
    warmup=start-timedelta(minutes=5*REPLAY_M5_CONTEXT_BARS)
    client=LSE(api_key=os.environ["LSE_API_KEY"])
    raw=client.candles(market,"5m",start=warmup.isoformat(),end=end.isoformat(),limit=5000,order="asc")
    rows=raw.get("data") if isinstance(raw,dict) else raw
    if isinstance(rows,dict):rows=rows.get("data") or rows.get("rows")
    if not isinstance(rows,(list,tuple)):raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:5m")
    frame=pd.DataFrame(rows)
    for candidate in ("timestamp","time","date"):
        if "datetime" not in frame.columns and candidate in frame.columns:frame=frame.rename(columns={candidate:"datetime"})
    required=("datetime","open","high","low","close")
    missing=[c for c in required if c not in frame.columns]
    if missing:raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:missing={missing}")
    frame["datetime"]=pd.to_datetime(frame["datetime"],utc=True,errors="coerce")
    for c in required[1:]:frame[c]=pd.to_numeric(frame[c],errors="coerce")
    frame=frame.dropna(subset=list(required)).sort_values("datetime").drop_duplicates("datetime",keep="last").reset_index(drop=True)
    if len(frame)<REPLAY_M5_CONTEXT_BARS+1:raise RuntimeError(f"INSUFFICIENT_HISTORICAL_M5:{symbol}:rows={len(frame)}")
    target=frame[(frame["datetime"]>=start)&(frame["datetime"]<end)].copy()
    if target.empty:raise RuntimeError(f"NO_TARGET_HISTORICAL_M5:{symbol}:{start.isoformat()}:{end.isoformat()}")
    gaps=target["datetime"].diff().dropna()/pd.Timedelta(minutes=5)
    gap_count=int((gaps>1).sum())
    return frame,{"source":"LSE_HISTORICAL_M5_OHLCV","historical_rows":len(frame),"target_m5_rows":len(target),"first_target_candle":str(target.iloc[0].datetime),"last_target_candle":str(target.iloc[-1].datetime),"five_minute_gap_count":gap_count,"warmup_bars":REPLAY_M5_CONTEXT_BARS}

def _worker(symbols,start,end,start_label,end_label):
    try:
        from v11.replay_m5 import replay_frames
        reports=[];data_quality=[]
        for symbol in symbols:
            m5,quality=_historical_m5(symbol,start,end);report=replay_frames(m5,None,symbol,start_time=start,end_time=end);report["data_quality"]=quality;reports.append(report);data_quality.append({"symbol":symbol,**quality})
        result={"engine_version":reports[0].get("engine_version") if reports else None,"engine_name":"REGIME-8-ENGINE-REENTRY","source":"LSE_HISTORICAL_M5_OHLCV","lookahead_safe":True,"timeframe_mode":"M5-only","symbols":symbols,"start":str(start),"end":str(end),"requested_window":{"start":start_label,"end":end_label},"data_quality":data_quality,"reports":reports}
        _persist(result)
        with _LOCK:_STATE.update({"running":False,"status":"completed","result":result,"error":None})
    except Exception as exc:
        with _LOCK:_STATE.update({"running":False,"status":"failed","error":f"{type(exc).__name__}: {exc}"})

def _parse_request():
    from v11.replay_m5 import normalize_replay_window
    start=request.args.get("start") or "2026-08-21"
    end=request.args.get("end") or "2026-08-24"
    return normalize_replay_window(start,end),start,end

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
            _STATE.update({"running":True,"status":"running","result":None,"error":None,"output":[],"request":{"symbols":symbols,"start":start_label,"end":end_label}})
        threading.Thread(target=_worker,args=(symbols,start,end,start_label,end_label),name="v12-m5-replay",daemon=True).start();return _json({"status":"started","engine_version":"12.1-M5-ONLY-REGIME-8-ENGINE-REENTRY","source":"LSE_HISTORICAL_M5_OHLCV","timeframe_mode":"M5-only","start":start_label,"end":end_label},202)

PAGE='''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V12.1 M5-only Historical Replay</title><style>body{font-family:system-ui;background:#0b1220;color:#e8eef8;padding:20px}main{max-width:1100px;margin:auto}.box{background:#121c30;border:1px solid #263654;border-radius:14px;padding:18px;margin:12px 0}button,a{padding:10px 14px;border-radius:8px;background:#172238;color:#fff;text-decoration:none;border:1px solid #33425e;cursor:pointer}.muted{color:#93a4bd}</style></head><body><main><div class="box"><h1>⏪ V12.1 Historical Replay — M5-only</h1><p class="muted">LSE Historical M5 · Trend/Regime/Context และ Entry ใช้ M5 ทั้งหมด · ไม่มี M15 · ผลบันทึกแยกจาก Live statistics</p><p><label>เริ่ม <input id="start" value="2026-08-21"></label> <label>ถึง <input id="end" value="2026-08-24"></label></p><button onclick="start()">▶ เริ่ม Replay</button> <a href="/statistics">📊 Statistics</a><span id="s" class="muted"> สถานะ: idle</span></div><div class="box"><div id="out">ยังไม่มีผล</div></div></main><script>const $=x=>document.getElementById(x);async function start(){let q=new URLSearchParams({symbols:'BTC,GOLD',start:$('start').value,end:$('end').value});await fetch('/api/replay/start?'+q.toString());poll()}async function poll(){let d=await(await fetch('/api/replay/status?ts='+Date.now(),{cache:'no-store'})).json();$('s').textContent='สถานะ: '+d.status;if(d.result?.reports){$('out').innerHTML='<p>ช่วง: '+d.result.requested_window.start+' → '+d.result.requested_window.end+'</p>'+d.result.data_quality.map(q=>'<p><b>'+q.symbol+'</b> Target M5: '+q.target_m5_rows+' · Warm-up: '+q.warmup_bars+' · 5M gaps: '+q.five_minute_gap_count+'</p>').join('')+d.result.reports.map(r=>{let p=r.performance||{};return '<h2>'+r.symbol+'</h2><p>Candles: '+(r.candles_evaluated??0)+' · Signals: '+(r.signals??0)+' · WIN: '+(p.wins??0)+' · LOSS: '+(p.losses??0)+' · Win Rate: '+(p.win_rate??0)+'% · Net R: '+(r.net_r??0)+'</p>'}).join('')}else if(d.error)$('out').textContent=d.error;if(d.running)setTimeout(poll,1500)}poll()</script></body></html>'''
'''
