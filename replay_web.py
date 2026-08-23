"""Web-triggered V10.3 historical replay runner for the free Render web service.

Runs replay_signal_history.py in an isolated subprocess so replay cannot mutate
live scanner/scheduler globals. No Telegram alert and no live order is sent.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Response, request

_LOCK = threading.RLock()
_STATE = {"running": False, "status": "idle", "start": None, "end": None, "symbol": "ALL", "started_at": None, "finished_at": None, "returncode": None, "output": [], "result": None, "error": None}
_PROC = None
BANGKOK = ZoneInfo("Asia/Bangkok")


def _json(value):
    return Response(json.dumps(value, ensure_ascii=False, allow_nan=False), mimetype="application/json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _parse_result(output_lines):
    for line in reversed(output_lines):
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "status" in obj and "results" in obj:
                return obj
        except Exception:
            pass
    return None


def _worker(start, end, symbol):
    global _PROC
    cmd = [sys.executable, "-u", "replay_signal_history.py", "--start", start, "--end", end, "--symbol", symbol]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        with _LOCK:
            _PROC = proc
        for line in proc.stdout:
            with _LOCK:
                _STATE["output"].append(line.rstrip())
                _STATE["output"] = _STATE["output"][-200:]
        code = proc.wait()
        with _LOCK:
            parsed = _parse_result(_STATE["output"])
            failed = [x.get("error") for x in (parsed or {}).get("results", []) if x.get("status") == "failed" and x.get("error")]
            if code != 0:
                error = f"Replay process exited with code {code}. Check output for the Python/LSE error."
                status = "failed"
            elif parsed and parsed.get("status") in ("completed", "dry-run", "partial"):
                error = "; ".join(failed) if failed else None
                status = parsed.get("status")
            elif parsed and parsed.get("status") == "failed":
                error = "; ".join(failed) if failed else "Replay reported failed status."
                status = "failed"
            else:
                error = "Replay finished without a valid JSON result."
                status = "failed"
            _STATE.update({"returncode": code, "result": parsed, "status": status, "running": False, "finished_at": _now(), "error": error})
            _PROC = None
    except Exception as exc:
        with _LOCK:
            _STATE.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}", "running": False, "finished_at": _now()})
            _PROC = None


def register(app):
    @app.route("/replay", strict_slashes=False)
    def replay_page():
        return Response(PAGE, mimetype="text/html")

    @app.route("/api/replay/status", strict_slashes=False)
    def replay_status():
        with _LOCK:
            return _json(dict(_STATE))

    @app.route("/api/replay/start", methods=["POST"], strict_slashes=False)
    def replay_start():
        data = request.get_json(silent=True) or request.form
        start = str(data.get("start") or "").strip()
        end = str(data.get("end") or "").strip()
        symbol = str(data.get("symbol") or "ALL").strip().upper()
        try:
            datetime.fromisoformat(start)
            datetime.fromisoformat(end)
        except ValueError:
            return _json({"status": "error", "message": "วันที่ต้องเป็น YYYY-MM-DD"}), 400
        if symbol not in ("BTC", "GOLD", "ALL"):
            return _json({"status": "error", "message": "symbol ต้องเป็น BTC, GOLD หรือ ALL"}), 400
        if end < start:
            return _json({"status": "error", "message": "วันสิ้นสุดต้องไม่น้อยกว่าวันเริ่มต้น"}), 400
        with _LOCK:
            if _STATE["running"]:
                return _json({"status": "busy", "message": "Replay กำลังทำงานอยู่", "state": dict(_STATE)}), 409
            _STATE.update({"running": True, "status": "running", "start": start, "end": end, "symbol": symbol, "started_at": _now(), "finished_at": None, "returncode": None, "output": [], "result": None, "error": None})
        threading.Thread(target=_worker, args=(start, end, symbol), name="historical-replay", daemon=True).start()
        return _json({"status": "started", "message": "เริ่ม Replay ราคาย้อนหลังจริงจาก LSE แล้ว"}), 202


PAGE = r'''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V10.3 Historical Replay</title><style>body{font-family:system-ui,-apple-system,sans-serif;background:#0b1220;color:#e8eef8;margin:0;padding:20px}main{max-width:1000px;margin:auto}.box{background:#121c30;border:1px solid #243451;border-radius:14px;padding:18px;margin:12px 0}h1{margin:0 0 6px}.muted{color:#93a4bd}label{display:block;margin:12px 0 6px}input,select,button{width:100%;box-sizing:border-box;background:#172238;color:#fff;border:1px solid #33425e;border-radius:8px;padding:10px}button{cursor:pointer;margin-top:15px;background:#2459a8}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}pre{white-space:pre-wrap;max-height:420px;overflow:auto;background:#09101d;padding:12px;border-radius:8px}.ok{color:#55d68b}.bad{color:#ff6b78}.warn{color:#ffb454}@media(max-width:650px){.grid{grid-template-columns:1fr}}a{color:#70a7ff}</style></head><body><main><div class="box"><h1>⏪ V10.3 Historical Replay</h1><div class="muted">จำลองด้วยเส้นทาง Multi-Strategy เดียวกับ Live V10.3 จาก LSE · M15 Context + M5 Setup/Trigger · ไม่ส่ง Telegram · ไม่เปิดออเดอร์</div></div><div class="box"><div class="grid"><div><label>เริ่มวันที่</label><input id="start" type="date" value="2026-08-01"></div><div><label>ถึงวันที่</label><input id="end" type="date"></div></div><label>สินทรัพย์</label><select id="symbol"><option value="ALL">BTC + GOLD</option><option value="BTC">BTC</option><option value="GOLD">GOLD</option></select><button onclick="startReplay()">▶ เริ่ม Replay V10.3</button></div><div class="box"><b id="status">สถานะ: กำลังตรวจสอบ...</b><div id="summary" class="muted" style="margin-top:10px"></div><pre id="log">-</pre><p><a href="/statistics">📊 เปิด V10.3 Statistics</a></p></div></main><script>const $=x=>document.getElementById(x);$('end').value=new Date().toISOString().slice(0,10);async function startReplay(){const body={start:$('start').value,end:$('end').value,symbol:$('symbol').value};const r=await fetch('/api/replay/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok){alert(d.message||'เริ่ม Replay ไม่สำเร็จ');return}poll()}function render(d){$('status').textContent='สถานะ: '+d.status;$('status').className=d.status==='completed'||d.status==='dry-run'?'ok':d.status==='partial'?'warn':d.status==='failed'?'bad':'';const rs=d.result&&d.result.results?d.result.results:[];$('summary').textContent=rs.map(x=>`${x.symbol}: status=${x.status||'-'}, generated=${x.generated??'-'}, inserted=${x.inserted??'-'}, WIN=${x.outcomes?.WIN??'-'}, LOSS=${x.outcomes?.LOSS??'-'}, OPEN=${x.outcomes?.OPEN??'-'}, AMBIGUOUS=${x.outcomes?.AMBIGUOUS??'-'}, NO_TRADE=${x.outcomes?.NO_TRADE??'-'}`).join(' | ')||d.error||'';$('log').textContent=(d.output||[]).join('\n')||d.error||'-'}async function poll(){try{const r=await fetch('/api/replay/status');const d=await r.json();render(d);if(d.running)setTimeout(poll,2000)}catch(e){setTimeout(poll,3000)}}poll();</script></body></html>'''
