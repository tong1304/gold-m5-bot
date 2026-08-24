"""Web-triggered V11 historical replay runner for the free Render web service."""
from __future__ import annotations
import copy, json, subprocess, sys, threading
from datetime import datetime, timezone
from flask import Response, request
_LOCK=threading.RLock(); _STATE={"running":False,"status":"idle","start":None,"end":None,"symbol":"ALL","started_at":None,"finished_at":None,"returncode":None,"output":[],"result":None,"error":None}; _PROC=None

def _json(value): return Response(json.dumps(value,ensure_ascii=False,allow_nan=False),mimetype="application/json")
def _now(): return datetime.now(timezone.utc).isoformat()
def _parse_result(lines):
    for line in reversed(lines):
        try:
            obj=json.loads(line.strip())
            if isinstance(obj,dict) and "status" in obj and "reports" in obj:return obj
        except Exception: pass
    return None

def _trade_history(rows):
    """Keep only actual BUY/SELL entries for the Statistics trade table."""
    trades=[]
    for row in rows or []:
        if row.get("signal") not in ("BUY","SELL") or not row.get("valid"):
            continue
        levels=row.get("trade_levels") or {}
        trades.append({
            "candle_time":row.get("candle_time"),
            "signal":row.get("signal"),
            "strategy":row.get("strategy"),
            "entry":levels.get("entry"),
            "sl":levels.get("sl"),
            "tp":levels.get("tp"),
            "tp1":levels.get("tp1"),
            "tp2":levels.get("tp2"),
            "tp3":levels.get("tp3"),
            "rr":levels.get("rr") if levels.get("rr") is not None else levels.get("risk_reward"),
            "result":row.get("result"),
            "r_multiple":row.get("r_multiple"),
            "resolved_at":row.get("resolved_at"),
        })
    return trades

def _compact_result(result):
    """Keep web state small while preserving actual trade entries for Statistics."""
    if not isinstance(result,dict): return result
    compact=copy.deepcopy(result)
    compact["reports"]=[]
    for report in (result.get("reports") or []):
        item={k:v for k,v in report.items() if k!="rows"}
        item["trade_history"]=_trade_history(report.get("rows") or [])
        compact["reports"].append(item)
    return compact

def _public_state(state):
    public=dict(state)
    public["result"]=_compact_result(state.get("result"))
    return public

def latest_replay_result():
    with _LOCK: return _STATE.get("result")

def _worker(start,end,symbol):
    global _PROC
    try:
        proc=subprocess.Popen([sys.executable,"-u","replay_signal_history.py","--start",start,"--end",end,"--symbol",symbol],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        with _LOCK:_PROC=proc
        for line in proc.stdout:
            with _LOCK:_STATE["output"]=( _STATE["output"]+[line.rstrip()] )[-200:]
        code=proc.wait()
        with _LOCK:
            parsed=_parse_result(_STATE["output"]); failed=[x.get("error") for x in (parsed or {}).get("reports",[]) if x.get("status")=="failed" and x.get("error")]
            status="failed" if code!=0 else (parsed.get("status") if parsed else "failed"); error=("Replay process exited with code %s"%code) if code!=0 else ("; ".join(failed) if failed else None)
            _STATE.update({"returncode":code,"result":_compact_result(parsed),"status":status,"running":False,"finished_at":_now(),"error":error}); _PROC=None
    except Exception as exc:
        with _LOCK:_STATE.update({"status":"failed","error":f"{type(exc).__name__}: {exc}","running":False,"finished_at":_now()}); _PROC=None

def register(app):
    @app.route("/replay",strict_slashes=False)
    def replay_page(): return Response(PAGE,mimetype="text/html")
    @app.route("/api/replay/status",strict_slashes=False)
    def replay_status():
        with _LOCK:return _json(_public_state(_STATE))
    @app.route("/api/replay/start",methods=["POST"],strict_slashes=False)
    def replay_start():
        data=request.get_json(silent=True) or request.form; start=str(data.get("start") or "").strip(); end=str(data.get("end") or "").strip(); symbol=str(data.get("symbol") or "ALL").strip().upper()
        try: datetime.fromisoformat(start); datetime.fromisoformat(end)
        except ValueError:return _json({"status":"error","message":"วันที่ต้องเป็น YYYY-MM-DD"}),400
        if symbol not in ("BTC","GOLD","ALL"):return _json({"status":"error","message":"symbol ต้องเป็น BTC, GOLD หรือ ALL"}),400
        if end<start:return _json({"status":"error","message":"วันสิ้นสุดต้องไม่น้อยกว่าวันเริ่มต้น"}),400
        with _LOCK:
            if _STATE["running"]:return _json({"status":"busy","message":"Replay กำลังทำงานอยู่","state":_public_state(_STATE)}),409
            _STATE.update({"running":True,"status":"running","start":start,"end":end,"symbol":symbol,"started_at":_now(),"finished_at":None,"returncode":None,"output":[],"result":None,"error":None})
        threading.Thread(target=_worker,args=(start,end,symbol),name="historical-replay",daemon=True).start(); return _json({"status":"started","message":"เริ่ม V11 Replay ราคาย้อนหลังจริงจาก LSE แล้ว"}),202

PAGE=r'''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V11 Historical Replay</title><style>body{font-family:system-ui;background:#0b1220;color:#e8eef8;margin:0;padding:20px}main{max-width:1000px;margin:auto}.box{background:#121c30;border:1px solid #243451;border-radius:14px;padding:18px;margin:12px 0}.muted{color:#93a4bd}label{display:block;margin:12px 0 6px}input,select,button{width:100%;box-sizing:border-box;background:#172238;color:#fff;border:1px solid #33425e;border-radius:8px;padding:10px}button{cursor:pointer;margin-top:15px;background:#2459a8}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}pre{white-space:pre-wrap;max-height:420px;overflow:auto;background:#09101d;padding:12px;border-radius:8px}.ok{color:#55d68b}.bad{color:#ff6b78}.metric{display:inline-block;background:#172238;border-radius:8px;padding:9px;margin:5px 5px 0 0}.metric b{display:block;font-size:18px}@media(max-width:650px){.grid{grid-template-columns:1fr}}a{color:#70a7ff}</style></head><body><main><div class="box"><h1>⏪ V11 Historical Replay</h1><div class="muted">LSE OHLCV จริง · M5 setup + M15 trend · RR 1:2 · ใช้ engine V11 เดียวกับ Live · ไม่ส่ง Telegram · historical warm-up และป้องกัน lookahead</div></div><div class="box"><div class="grid"><div><label>เริ่มวันที่</label><input id="start" type="date" value="2026-08-01"></div><div><label>ถึงวันที่</label><input id="end" type="date"></div></div><label>สินทรัพย์</label><select id="symbol"><option value="ALL">BTC + GOLD</option><option value="BTC">BTC</option><option value="GOLD">GOLD</option></select><button onclick="startReplay()">▶ เริ่ม Replay V11</button></div><div class="box"><b id="status">สถานะ: กำลังตรวจสอบ...</b><div id="summary" style="margin-top:10px"></div><pre id="log">-</pre><p><a href="/statistics">📊 เปิด V11 Statistics</a></p></div></main><script>const $=x=>document.getElementById(x);$('end').value=new Date().toISOString().slice(0,10);async function startReplay(){try{const body={start:$('start').value,end:$('end').value,symbol:$('symbol').value};const r=await fetch('/api/replay/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok){$('status').textContent='สถานะ: เริ่มไม่สำเร็จ';$('status').className='bad';$('log').textContent=d.message||'เริ่ม Replay ไม่สำเร็จ';return}poll()}catch(e){$('status').textContent='สถานะ: เชื่อมต่อ API ไม่สำเร็จ';$('status').className='bad';$('log').textContent=String(e)}}function render(d){$('status').textContent='สถานะ: '+d.status;$('status').className=d.status==='completed'||d.status==='dry-run'?'ok':d.status==='failed'?'bad':'';const rs=d.result&&d.result.reports?d.result.reports:[];$('summary').innerHTML=rs.map(x=>{const p=x.performance||{};return `<div class="metric"><span>${x.symbol}</span><b>${p.win_rate??0}% Win</b>WIN ${p.wins??0} · LOSS ${p.losses??0} · Net ${p.net_r??0}R · PF ${p.profit_factor??'—'} · DD ${p.max_drawdown_r??0}R</div>`}).join('')||d.error||'';$('log').textContent=(d.output||[]).join('\n')||d.error||'-'}async function poll(){try{const r=await fetch('/api/replay/status');if(!r.ok)throw new Error('HTTP '+r.status);const d=await r.json();render(d);if(d.running)setTimeout(poll,2000)}catch(e){$('status').textContent='สถานะ: กำลังเชื่อมต่อ...';$('status').className='bad';$('log').textContent=String(e);setTimeout(poll,3000)}}poll();</script></body></html>'''
