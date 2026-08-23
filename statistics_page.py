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
    evidence = payload.get("selected_evidence") or payload.get("evidence") or payload.get("confirmed_patterns") or payload.get("patterns") or []
    if isinstance(evidence, dict): evidence = [evidence]
    if not isinstance(evidence, list): evidence = [evidence] if evidence else []
    names=[]; dirs=[]; normalized=[]
    for item in evidence:
        if isinstance(item, dict): name=item.get("name") or item.get("pattern") or item.get("type"); direction=item.get("direction")
        else: name=str(item); direction=None
        if not name: continue
        name=str(name)
        if name not in names:
            names.append(name); dirs.append(str(direction) if direction else None); normalized.append({"name":name,"direction":str(direction) if direction else None})
    compact=payload.get("pattern_names") or payload.get("patterns_used") or []
    if not names:
        if isinstance(compact,str): compact=[compact]
        for item in compact if isinstance(compact,list) else []:
            name=item.get("name") if isinstance(item,dict) else str(item)
            if name and str(name) not in names: names.append(str(name)); dirs.append(None); normalized.append({"name":str(name),"direction":None})
    cats=payload.get("m5_categories") or payload.get("categories") or []
    if isinstance(cats,str): cats=[cats]
    if not isinstance(cats,list): cats=[]
    mtf=payload.get("mtf") or {}
    h1=payload.get("h1_bias") or (mtf.get("H1",{}).get("bias") if isinstance(mtf,dict) and isinstance(mtf.get("H1"),dict) else None)
    m15=payload.get("m15_bias") or (mtf.get("M15",{}).get("bias") if isinstance(mtf,dict) and isinstance(mtf.get("M15"),dict) else None)
    m5=payload.get("m5_direction") or payload.get("pattern_signal") or row.get("direction")
    return {"pattern_names":names,"pattern_directions":dirs,"pattern_count":len(names),"categories":[str(x) for x in cats],"m5_score":payload.get("m5_score") or payload.get("score") or payload.get("confluence_score"),"h1_bias":h1,"m15_bias":m15,"m5_direction":m5,"pattern_signal":payload.get("pattern_signal"),"evidence":normalized}


def _bkk(value):
    if not value: return None
    try:
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M:%S")
    except Exception: return str(value)

PAGE=r'''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Signal Statistics</title><style>
body{font-family:system-ui,-apple-system,sans-serif;background:#0b1220;color:#e8eef8;margin:0;padding:18px}main{max-width:1500px;margin:auto}.top{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}.muted{color:#93a4bd}.filters{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}select,button{background:#172238;color:#fff;border:1px solid #33425e;border-radius:8px;padding:9px 12px}button{cursor:pointer}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}.card{background:#121c30;border:1px solid #243451;border-radius:12px;padding:14px}.value{font-size:25px;font-weight:700;margin-top:5px}.green{color:#55d68b}.red{color:#ff6b78}.blue{color:#70a7ff}.yellow{color:#f4c95d}.wrap{overflow:auto;margin-top:18px;background:#121c30;border:1px solid #243451;border-radius:12px}table{width:100%;border-collapse:collapse;min-width:1550px}th,td{padding:9px;border-bottom:1px solid #243451;text-align:left;font-size:13px;vertical-align:top}th{color:#93a4bd}.badge{padding:4px 7px;border-radius:7px;background:#243451}.win{background:#123d2a}.loss{background:#4a1d25}.open{background:#3d3214}.amb{background:#30244a}.pattern{line-height:1.5}.detail{color:#93a4bd;font-size:12px;margin-top:3px}a{color:#70a7ff}@media(max-width:600px){body{padding:10px}}
</style></head><body><main><div class="top"><div><h1>📊 Signal Statistics</h1><div class="muted">BTC + GOLD | Asia/Bangkok | Pattern ที่ใช้เข้าเทรดจริงจาก Telegram / Historical Replay</div></div><div><a href="/replay">⏪ Historical Replay</a> &nbsp; <button onclick="loadData()">↻ รีเฟรช</button></div></div><div class="filters"><select id="days"><option value="1">วันนี้</option><option value="7" selected>7 วัน</option><option value="30">30 วัน</option><option value="90">90 วัน</option><option value="365">ทั้งหมด</option></select><select id="symbol"><option value="">ทั้งหมด</option><option value="BTC">BTC</option><option value="GOLD">GOLD</option></select></div><div class="cards"><div class="card">ทั้งหมด<div id="total" class="value">-</div></div><div class="card">ชนะ<div id="wins" class="value green">-</div></div><div class="card">แพ้<div id="losses" class="value red">-</div></div><div class="card">ยังไม่จบ<div id="open" class="value yellow">-</div></div><div class="card">Win Rate<div id="rate" class="value blue">-</div></div><div class="card">Net R<div id="netr" class="value">-</div></div></div><div class="wrap"><table><thead><tr><th>เวลา</th><th>สินทรัพย์</th><th>Signal</th><th>รูปแบบ M5 ที่ใช้เข้า</th><th>MTF</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>ผล</th><th>R</th><th>เวลาจบ</th></tr></thead><tbody id="rows"><tr><td colspan="12">กำลังโหลด...</td></tr></tbody></table></div></main><script>
const $=id=>document.getElementById(id);function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function fmt(v){return v==null||v===''?'-':Number(v).toLocaleString(undefined,{maximumFractionDigits:8})}function badge(v){let c=v==='WIN'?'win':v==='LOSS'?'loss':v==='OPEN'?'open':'amb';return `<span class="badge ${c}">${esc(v)}</span>`}function pats(x){let n=x.pattern_names||[],d=x.pattern_directions||[],c=x.categories||[];let list=n.length?n.map((v,i)=>`• ${esc(v)}${d[i]?` [${esc(d[i])}]`:''}`).join('<br>'):'• ไม่พบข้อมูลแพทเทิร์นในสัญญาณเดิม';let m=[];if(x.m5_direction)m.push('M5: '+esc(x.m5_direction));if(x.m5_score!=null)m.push('Score: '+esc(x.m5_score));if(c.length)m.push('หมวด: '+esc(c.join(', ')));return `<div class="pattern">${list}<div class="detail">${m.join(' | ')}</div></div>`}async function loadData(){let q=new URLSearchParams({days:$('days').value,symbol:$('symbol').value});let r=await fetch('/api/statistics?'+q),d=await r.json();if(!r.ok){alert(d.message||'โหลดข้อมูลไม่สำเร็จ');return}$('total').textContent=d.total;$('wins').textContent=d.wins;$('losses').textContent=d.losses;$('open').textContent=d.open;$('rate').textContent=d.win_rate+'%';$('netr').textContent=fmt(d.net_r);$('rows').innerHTML=d.rows.length?d.rows.map(x=>`<tr><td>${esc(x.created_at_bangkok||x.created_at)}</td><td>${esc(x.symbol)}</td><td><b>${esc(x.direction)}</b></td><td>${pats(x)}</td><td>H1: ${esc(x.h1_bias||'-')}<br>M15: ${esc(x.m15_bias||'-')}<br>M5: ${esc(x.m5_direction||x.direction)}</td><td>${fmt(x.entry)}</td><td>${fmt(x.sl)}</td><td>${fmt(x.tp)}</td><td>${fmt(x.risk_reward)}</td><td>${badge(x.result)}</td><td>${fmt(x.r_multiple)}</td><td>${esc(x.resolved_at_bangkok||'-')}</td></tr>`).join(''):'<tr><td colspan="12">ยังไม่มีสัญญาณที่บันทึก</td></tr>'}$('days').onchange=loadData;$('symbol').onchange=loadData;loadData();</script></body></html>'''


def register(app):
    @app.route('/statistics')
    def statistics_page(): return Response(PAGE,mimetype='text/html')
    @app.route('/api/statistics')
    def statistics_api():
        try: days=max(1,min(int(request.args.get('days','7')),3650))
        except ValueError: days=7
        data=history.statistics(days=days,symbol=request.args.get('symbol') or None)
        for row in data['rows']:
            row.update(_patterns(row));row['created_at_bangkok']=_bkk(row.get('created_at'));row['resolved_at_bangkok']=_bkk(row.get('resolved_at'))
        return Response(json.dumps(_safe(data),ensure_ascii=False),mimetype='application/json')
    @app.route('/api/signals')
    def signals_api():
        try: days=max(1,min(int(request.args.get('days','30')),3650))
        except ValueError: days=30
        rows=history.list_signals(days=days,symbol=request.args.get('symbol'),result=request.args.get('result'),limit=1000)
        for row in rows:
            row.update(_patterns(row));row['created_at_bangkok']=_bkk(row.get('created_at'));row['resolved_at_bangkok']=_bkk(row.get('resolved_at'))
        return Response(json.dumps(_safe(rows),ensure_ascii=False),mimetype='application/json')
    try:
        import replay_web
        replay_web.register(app)
    except Exception:
        import logging; logging.getLogger(__name__).exception('Failed to register Historical Replay routes')
'''
