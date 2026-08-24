"""V12.1 Historical Replay web service: M5-only."""
from __future__ import annotations
import json,threading
from flask import Response,request
_LOCK=threading.RLock();_STATE={"running":False,"status":"idle","result":None,"error":None,"output":[]}
def _json(v,status=200):return Response(json.dumps(v,ensure_ascii=False,default=str),status=status,mimetype="application/json",headers={"Cache-Control":"no-store"})
def _worker(symbols,bars):
    try:
        import live_scanner_v11
        from v11.replay_m5 import replay_frames
        reports=[]
        for symbol in symbols:
            m5=live_scanner_v11._lse_frame(symbol,"5m",bars);reports.append(replay_frames(m5,None,symbol,limit=bars))
        with _LOCK:_STATE.update({"running":False,"status":"completed","result":{"engine_version":reports[0].get("engine_version") if reports else None,"symbols":symbols,"reports":reports}})
    except Exception as exc:
        with _LOCK:_STATE.update({"running":False,"status":"failed","error":f"{type(exc).__name__}: {exc}"})
def register(app):
    @app.route("/replay",strict_slashes=False)
    def replay_page():return Response(PAGE,mimetype="text/html",headers={"Cache-Control":"no-store"})
    @app.route("/api/replay/status",strict_slashes=False)
    def replay_status():
        with _LOCK:return _json(_STATE)
    @app.route("/api/replay/start",methods=["GET","POST"],strict_slashes=False)
    def replay_start():
        with _LOCK:
            if _STATE["running"]:return _json({"status":"busy"},409)
            symbols=[s for s in (request.args.get("symbols") or "BTC,GOLD").upper().split(",") if s in ("BTC","GOLD")] or ["BTC","GOLD"]
            try:bars=max(100,min(int(request.args.get("bars","500")),2000))
            except ValueError:bars=500
            _STATE.update({"running":True,"status":"running","result":None,"error":None,"output":[]})
        threading.Thread(target=_worker,args=(symbols,bars),name="v12-m5-replay",daemon=True).start();return _json({"status":"started","engine_version":"12.1-M5-ONLY-REGIME-8-ENGINE-REENTRY"},202)
PAGE='''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V12.1 M5-only Historical Replay</title><style>body{font-family:system-ui;background:#0b1220;color:#e8eef8;padding:20px}main{max-width:1100px;margin:auto}.box{background:#121c30;border:1px solid #263654;border-radius:14px;padding:18px;margin:12px 0}button,a{padding:10px 14px;border-radius:8px;background:#172238;color:#fff;text-decoration:none;border:1px solid #33425e;cursor:pointer}table{width:100%;border-collapse:collapse;margin-top:15px}td,th{padding:8px;border-bottom:1px solid #263654;text-align:left}.muted{color:#93a4bd}</style></head><body><main><div class="box"><h1>⏪ V12.1 Historical Replay — M5-only</h1><p class="muted">LSE Historical M5 · Trend/Regime/Context และ Entry ใช้ M5 ทั้งหมด · ไม่มี M15</p><button onclick="start()">▶ เริ่ม Replay</button> <a href="/statistics">📊 Statistics</a><span id="s" class="muted"> สถานะ: idle</span></div><div class="box"><div id="out">ยังไม่มีผล</div></div></main><script>const $=x=>document.getElementById(x);async function start(){await fetch('/api/replay/start?bars=500&symbols=BTC,GOLD');poll()}async function poll(){let d=await(await fetch('/api/replay/status?ts='+Date.now(),{cache:'no-store'})).json();$('s').textContent='สถานะ: '+d.status;if(d.result?.reports){$('out').innerHTML=d.result.reports.map(r=>{let p=r.performance||{};return '<h2>'+r.symbol+'</h2><p>Signals: '+(r.signals??0)+' · WIN: '+(p.wins??r.wins??0)+' · LOSS: '+(p.losses??r.losses??0)+' · Win Rate: '+(p.win_rate??0)+'% · Net R: '+(r.net_r??0)+'</p>'}).join('')}else if(d.error)$('out').textContent=d.error;if(d.running)setTimeout(poll,1500)}poll()</script></body></html>'''
