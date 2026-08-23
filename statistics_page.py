import json
from flask import Response, request
from signal_history import history


def _safe(value):
    if isinstance(value, dict): return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_safe(v) for v in value]
    return value


def _patterns(row):
    try: payload = json.loads(row.get("payload_json") or "{}")
    except Exception: payload = {}
    if not isinstance(payload, dict): payload = {}
    v6 = payload.get("v6_setup") or {}
    sweep = v6.get("liquidity_event") or payload.get("liquidity_event") or {}
    mss = v6.get("m5_trigger") or payload.get("m5_trigger") or {}
    location = v6.get("location") or payload.get("location") or {}
    pullback = v6.get("pullback") or payload.get("pullback") or {}
    structure = v6.get("structure_bias") or payload.get("structure_bias") or {}
    mtf = payload.get("mtf") or {}
    h1 = payload.get("h1_bias") or structure.get("bias") or (mtf.get("H1",{}).get("bias") if isinstance(mtf.get("H1"),dict) else None)
    m15 = payload.get("m15_bias") or (mtf.get("M15",{}).get("bias") if isinstance(mtf.get("M15"),dict) else None)
    m5 = payload.get("m5_direction") or payload.get("pattern_signal") or row.get("direction")
    evidence = payload.get("selected_evidence") or payload.get("evidence") or payload.get("confirmed_patterns") or payload.get("patterns") or []
    if isinstance(evidence, dict): evidence=[evidence]
    if not isinstance(evidence,list): evidence=[evidence] if evidence else []
    names=[]; dirs=[]; normalized=[]
    for item in evidence:
        if isinstance(item,dict): name=item.get("name") or item.get("pattern") or item.get("type"); direction=item.get("direction")
        else: name=str(item); direction=None
        if name:
            name=str(name)
            if name not in names: names.append(name); dirs.append(str(direction) if direction else None); normalized.append({"name":name,"direction":str(direction) if direction else None})
    return {
        "pattern_names":names,"pattern_directions":dirs,"pattern_count":len(names),
        "categories":[str(x) for x in (payload.get("m5_categories") or payload.get("categories") or [])] if isinstance(payload.get("m5_categories") or payload.get("categories") or [],list) else [],
        "m5_score":payload.get("m5_score") or payload.get("score"),"h1_bias":h1,"m15_bias":m15,"m5_direction":m5,
        "pattern_signal":payload.get("pattern_signal"),"evidence":normalized,
        "engine_version":payload.get("engine_version") or v6.get("engine_version") or "legacy",
        "structure_bias":structure.get("bias"),"location_zone":location.get("zone"),
        "liquidity_event":sweep.get("type"),"liquidity_level":sweep.get("level"),
        "mss_event":mss.get("type"),"mss_level":mss.get("level"),
        "pullback_valid":pullback.get("valid"),"setup_key":v6.get("setup_key") or payload.get("setup_key"),
        "rejection_reasons":payload.get("rejection_reasons") or v6.get("rejection_reasons") or [],
    }


def _bkk(value):
    if not value: return None
    try:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M:%S")
    except Exception: return str(value)


PAGE=r'''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Signal Statistics V6</title><style>
body{font-family:system-ui,-apple-system,sans-serif;background:#0b1220;color:#e8eef8;margin:0;padding:18px}main{max-width:1700px;margin:auto}.top{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}.muted{color:#93a4bd}.filters{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}select,button{background:#172238;color:#fff;border:1px solid #33425e;border-radius:8px;padding:9px 12px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}.card{background:#121c30;border:1px solid #243451;border-radius:12px;padding:14px}.value{font-size:25px;font-weight:700;margin-top:5px}.green{color:#55d68b}.red{color:#ff6b78}.blue{color:#70a7ff}.yellow{color:#f4c95d}.wrap{overflow:auto;margin-top:18px;background:#121c30;border:1px solid #243451;border-radius:12px}table{width:100%;border-collapse:collapse;min-width:1900px}th,td{padding:9px;border-bottom:1px solid #243451;text-align:left;font-size:13px;vertical-align:top}th{color:#93a4bd}.badge{padding:4px 7px;border-radius:7px;background:#243451}.win{background:#123d2a}.loss{background:#4a1d25}.open{background:#3d3214}.pattern{line-height:1.5}.detail{color:#93a4bd;font-size:12px;margin-top:3px}.v6{color:#d7e4ff}a{color:#70a7ff}
</style></head><body><main><div class="top"><div><h1>📊 Signal Statistics V6</h1><div class="muted">Structure → Location → Liquidity → MSS/BOS → Pullback | BTC + GOLD | Asia/Bangkok</div></div><div><a href="/replay">⏪ Historical Replay</a> &nbsp; <button onclick="loadData()">↻ รีเฟรช</button></div></div><div class="filters"><select id="days"><option value="1">วันนี้</option><option value="7" selected>7 วัน</option><option value="30">30 วัน</option><option value="90">90 วัน</option><option value="365">ทั้งหมด</option></select><select id="symbol"><option value="">ทั้งหมด</option><option value="BTC">BTC</option><option value="GOLD">GOLD</option></select></div><div class="cards"><div class="card">ทั้งหมด<div id="total" class="value">-</div></div><div class="card">ชนะ<div id="wins" class="value green">-</div></div><div class="card">แพ้<div id="losses" class="value red">-</div></div><div class="card">ยังไม่จบ<div id="open" class="value yellow">-</div></div><div class="card">Win Rate<div id="rate" class="value blue">-</div></div><div class="card">Net R<div id="netr" class="value">-</div></div></div><div class="wrap"><table><thead><tr><th>เวลา</th><th>สินทรัพย์</th><th>Signal</th><th>V6 Setup</th><th>MTF</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>ผล</th><th>R</th><th>เวลาจบ</th></tr></thead><tbody id="rows"><tr><td colspan="12">กำลังโหลด...</td></tr></tbody></table></div></main><script>
const $=id=>document.getElementById(id);function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function fmt(v){return v==null||v===''?'-':Number(v).toLocaleString(undefined,{maximumFractionDigits:8})}function badge(v){let c=v==='WIN'?'win':v==='LOSS'?'loss':v==='OPEN'?'open':'';return `<span class="badge ${c}">${esc(v)}</span>`}function v6(x){let s=[];if(x.engine_version&&x.engine_version!=='legacy')s.push(`<b>Engine ${esc(x.engine_version)}</b>`);if(x.structure_bias)s.push(`Structure: ${esc(x.structure_bias)}`);if(x.location_zone)s.push(`Location: ${esc(x.location_zone)}`);if(x.liquidity_event)s.push(`Liquidity: ${esc(x.liquidity_event)}`);if(x.mss_event)s.push(`MSS/BOS: ${esc(x.mss_event)}`);if(x.pullback_valid!=null)s.push(`Pullback: ${x.pullback_valid?'CONFIRMED':'NO'}`);if(x.setup_key)s.push(`Setup: ${esc(x.setup_key)}`);if(x.rejection_reasons?.length)s.push(`Reject: ${esc(x.rejection_reasons.join(', '))}`);if(!s.length)s.push('Legacy signal / no V6 metadata');return `<div class="v6">${s.join('<br>')}</div>`}async function loadData(){let q=new URLSearchParams({days:$('days').value,symbol:$('symbol').value});let r=await fetch('/api/statistics?'+q),d=await r.json();if(!r.ok){alert(d.message||'โหลดข้อมูลไม่สำเร็จ');return}$('total').textContent=d.total;$('wins').textContent=d.wins;$('losses').textContent=d.losses;$('open').textContent=d.open;$('rate').textContent=d.win_rate+'%';$('netr').textContent=fmt(d.net_r);$('rows').innerHTML=d.rows.length?d.rows.map(x=>`<tr><td>${esc(x.created_at_bangkok||x.created_at)}</td><td>${esc(x.symbol)}</td><td><b>${esc(x.direction)}</b></td><td>${v6(x)}</td><td>H1: ${esc(x.h1_bias||'-')}<br>M15: ${esc(x.m15_bias||'-')}<br>M5: ${esc(x.m5_direction||x.direction)}</td><td>${fmt(x.entry)}</td><td>${fmt(x.sl)}</td><td>${fmt(x.tp)}</td><td>${fmt(x.risk_reward)}</td><td>${badge(x.result)}</td><td>${fmt(x.r_multiple)}</td><td>${esc(x.resolved_at_bangkok||'-')}</td></tr>`).join(''):'<tr><td colspan="12">ยังไม่มีสัญญาณที่บันทึก</td></tr>'}$('days').onchange=loadData;$('symbol').onchange=loadData;loadData();</script></body></html>'''


def register(app):
    @app.route('/statistics', strict_slashes=False)
    def statistics_page(): return Response(PAGE,mimetype='text/html')
    @app.route('/api/statistics', strict_slashes=False)
    def statistics_api():
        try: days=max(1,min(int(request.args.get('days','7')),3650))
        except ValueError: days=7
        data=history.statistics(days=days,symbol=request.args.get('symbol') or None)
        for row in data['rows']:
            row.update(_patterns(row));row['created_at_bangkok']=_bkk(row.get('created_at'));row['resolved_at_bangkok']=_bkk(row.get('resolved_at'))
        return Response(json.dumps(_safe(data),ensure_ascii=False),mimetype='application/json')
    @app.route('/api/signals', strict_slashes=False)
    def signals_api():
        try: days=max(1,min(int(request.args.get('days','30')),3650))
        except ValueError: days=30
        rows=history.list_signals(days=days,symbol=request.args.get('symbol'),result=request.args.get('result'),limit=1000)
        for row in rows:
            row.update(_patterns(row));row['created_at_bangkok']=_bkk(row.get('created_at'));row['resolved_at_bangkok']=_bkk(row.get('resolved_at'))
        return Response(json.dumps(_safe(rows),ensure_ascii=False),mimetype='application/json')
    try:
        import replay_web; replay_web.register(app)
    except Exception:
        import logging; logging.getLogger(__name__).exception('Failed to register Historical Replay routes')
