import json
from flask import Response, request

from signal_history import history


def _safe(value):
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return value


PAGE = r'''<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Signal Statistics</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;background:#0b1220;color:#e8eef8;margin:0;padding:18px}main{max-width:1100px;margin:auto}.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}h1{margin:0 0 6px}.muted{color:#93a4bd}.filters{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}select,button{background:#172238;color:#fff;border:1px solid #33425e;border-radius:8px;padding:9px 12px}button{cursor:pointer}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}.card{background:#121c30;border:1px solid #243451;border-radius:12px;padding:14px}.value{font-size:25px;font-weight:700;margin-top:5px}.green{color:#55d68b}.red{color:#ff6b78}.blue{color:#70a7ff}.yellow{color:#f4c95d}.table-wrap{overflow:auto;margin-top:18px;background:#121c30;border:1px solid #243451;border-radius:12px}table{width:100%;border-collapse:collapse;min-width:900px}th,td{padding:10px;border-bottom:1px solid #243451;text-align:left;font-size:13px}th{color:#93a4bd}.badge{padding:4px 7px;border-radius:7px;background:#243451}.win{background:#123d2a}.loss{background:#4a1d25}.open{background:#3d3214}.amb{background:#30244a}.refresh{margin-left:auto}@media(max-width:600px){body{padding:10px}}
</style></head>
<body><main>
<div class="top"><div><h1>📊 Signal Statistics</h1><div class="muted">สถิติสัญญาณ BTC + GOLD | เวลา Asia/Bangkok</div></div><button class="refresh" onclick="loadData()">↻ รีเฟรช</button></div>
<div class="filters"><select id="days"><option value="1">วันนี้</option><option value="7" selected>7 วัน</option><option value="30">30 วัน</option><option value="90">90 วัน</option><option value="365">ทั้งหมด</option></select><select id="symbol"><option value="">ทั้งหมด</option><option value="BTC">BTC</option><option value="GOLD">GOLD</option></select></div>
<div class="cards"><div class="card">สัญญาณทั้งหมด<div id="total" class="value">-</div></div><div class="card">ชนะ<div id="wins" class="value green">-</div></div><div class="card">แพ้<div id="losses" class="value red">-</div></div><div class="card">ยังไม่จบ<div id="open" class="value yellow">-</div></div><div class="card">Win Rate<div id="rate" class="value blue">-</div></div><div class="card">Net R<div id="netr" class="value">-</div></div></div>
<div class="table-wrap"><table><thead><tr><th>เวลา</th><th>สินทรัพย์</th><th>Signal</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>ผล</th><th>R</th><th>Resolved</th></tr></thead><tbody id="rows"><tr><td colspan="10">กำลังโหลด...</td></tr></tbody></table></div>
</main><script>
const $=id=>document.getElementById(id);
function fmt(v){return v==null?'-':Number(v).toLocaleString(undefined,{maximumFractionDigits:8})}
function badge(v){let c=v==='WIN'?'win':v==='LOSS'?'loss':v==='OPEN'?'open':'amb';return `<span class="badge ${c}">${v}</span>`}
async function loadData(){const q=new URLSearchParams({days:$('days').value,symbol:$('symbol').value});const r=await fetch('/api/statistics?'+q);const d=await r.json();if(!r.ok){alert(d.message||'โหลดข้อมูลไม่สำเร็จ');return}$('total').textContent=d.total;$('wins').textContent=d.wins;$('losses').textContent=d.losses;$('open').textContent=d.open;$('rate').textContent=d.win_rate+'%';$('netr').textContent=fmt(d.net_r);$('rows').innerHTML=d.rows.length?d.rows.map(x=>`<tr><td>${x.created_at_bangkok||x.created_at}</td><td>${x.symbol}</td><td>${x.direction}</td><td>${fmt(x.entry)}</td><td>${fmt(x.sl)}</td><td>${fmt(x.tp)}</td><td>${fmt(x.risk_reward)}</td><td>${badge(x.result)}</td><td>${fmt(x.r_multiple)}</td><td>${x.resolved_at_bangkok||'-'}</td></tr>`).join(''):'<tr><td colspan="10">ยังไม่มีสัญญาณที่บันทึก</td></tr>'}
$('days').onchange=loadData;$('symbol').onchange=loadData;loadData();
</script></body></html>'''


def register(app):
    @app.route("/statistics")
    def statistics_page():
        return Response(PAGE, mimetype="text/html")

    @app.route("/api/statistics")
    def statistics_api():
        try:
            days = max(1, min(int(request.args.get("days", "7")), 3650))
        except ValueError:
            days = 7
        symbol = request.args.get("symbol") or None
        data = history.statistics(days=days, symbol=symbol)
        for row in data["rows"]:
            row["created_at_bangkok"] = _bkk(row.get("created_at"))
            row["resolved_at_bangkok"] = _bkk(row.get("resolved_at"))
        return Response(json.dumps(_safe(data), ensure_ascii=False), mimetype="application/json")

    @app.route("/api/signals")
    def signals_api():
        try:
            days = max(1, min(int(request.args.get("days", "30")), 3650))
        except ValueError:
            days = 30
        rows = history.list_signals(days=days, symbol=request.args.get("symbol"), result=request.args.get("result"), limit=1000)
        for row in rows:
            row["created_at_bangkok"] = _bkk(row.get("created_at"))
            row["resolved_at_bangkok"] = _bkk(row.get("resolved_at"))
        return Response(json.dumps(_safe(rows), ensure_ascii=False), mimetype="application/json")


def _bkk(value):
    if not value:
        return None
    try:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return str(value)
