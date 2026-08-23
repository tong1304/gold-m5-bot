"""V10.3 statistics page with detailed entry-order reporting."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import Response, request
from signal_history import DEFAULT_DB
from strategy_engine import BTC_STRATEGIES, GOLD_STRATEGIES

BANGKOK = ZoneInfo("Asia/Bangkok")

def _rows(days=30, symbol=None):
    days=max(1,min(int(days),3650)); where=["datetime(created_at)>=datetime('now', ?)"]; params=[f"-{days} days"]
    if symbol in ("BTC","GOLD"): where.append("symbol=?"); params.append(symbol)
    q=f"SELECT * FROM signals WHERE {' AND '.join(where)} ORDER BY datetime(created_at) DESC LIMIT 10000"
    conn=sqlite3.connect(DEFAULT_DB); conn.row_factory=sqlite3.Row
    try:return [dict(r) for r in conn.execute(q,params).fetchall()]
    finally:conn.close()

def _payload(row):
    try:
        p=json.loads(row.get("payload_json") or "{}")
        return p if isinstance(p,dict) else {}
    except Exception:return {}

def _num(value):
    try:
        value=float(value); return value if value==value and abs(value)!=float("inf") else None
    except (TypeError,ValueError):return None

def _bangkok_time(value):
    if not value:return None
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BANGKOK).strftime("%d/%m/%Y %H:%M:%S")
    except (TypeError,ValueError):return str(value)

def _entry_detail(row):
    """Normalize a real BUY/SELL history row for the Statistics UI."""
    p=_payload(row); levels=p.get("trade_levels") or {}; levels=levels if isinstance(levels,dict) else {}
    result=str(row.get("result") or p.get("result") or "OPEN").upper()
    direction=str(row.get("direction") or p.get("signal") or "").upper()
    if direction not in ("BUY","SELL") or result=="NO_TRADE":return None
    entry=_num(row.get("entry")) or _num(levels.get("entry")); sl=_num(row.get("sl")) or _num(levels.get("sl")); tp=_num(row.get("tp")) or _num(levels.get("tp")); rr=_num(row.get("risk_reward")) or _num(levels.get("risk_reward",levels.get("effective_rr")))
    reasons=p.get("reasons") or p.get("reason") or p.get("validation_reasons") or []
    if not isinstance(reasons,list):reasons=[reasons]
    return {"signal_id":row.get("signal_id"),"symbol":row.get("symbol"),"direction":direction,"result":result,"strategy":p.get("strategy") or p.get("selected_strategy") or "—","regime":p.get("regime") or "—","timeframe":p.get("timeframe") or "M5","context_timeframe":p.get("context_timeframe") or "M15","candle_time":row.get("candle_time"),"entry_time_thailand":_bangkok_time(row.get("created_at") or row.get("candle_time")),"exit_time_thailand":_bangkok_time(row.get("resolved_at")),"entry":entry,"sl":sl,"tp":tp,"risk_reward":rr,"r_multiple":_num(row.get("r_multiple")),"reasons":[str(x) for x in reasons if str(x).strip()],"telegram_sent":bool(row.get("telegram_sent"))}

def _build(days=30,symbol=None):
    rows=_rows(days,symbol); names=(BTC_STRATEGIES if symbol=="BTC" else GOLD_STRATEGIES if symbol=="GOLD" else tuple(dict.fromkeys(BTC_STRATEGIES+GOLD_STRATEGIES)))
    stats={n:{"evaluated":0,"pass":0,"fail":0,"not_applicable":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"reasons":{}} for n in names}; overall={"rows":len(rows),"trades":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"net_r":0.0}; entries=[]
    for row in rows:
        p=_payload(row)
        if str(p.get("engine_version","")).startswith(("10.3","10.0")):
            for c in p.get("strategy_candidates") or []:
                n=c.get("strategy")
                if n not in stats:stats[n]={"evaluated":0,"pass":0,"fail":0,"not_applicable":0,"wins":0,"losses":0,"open":0,"ambiguous":0,"no_trade":0,"reasons":{}}
                s=stats[n]; s["evaluated"]+=1; st=str(c.get("status","FAIL")).lower()
                if st in ("pass","fail","not_applicable"):s[st]+=1
                for reason in c.get("reason") or []:s["reasons"][reason]=s["reasons"].get(reason,0)+1
        result=str(row.get("result") or "").upper()
        if result=="NO_TRADE":overall["no_trade"]+=1
        elif result in ("WIN","LOSS","OPEN","AMBIGUOUS"):
            overall["trades"]+=1; overall["wins"]+=result=="WIN"; overall["losses"]+=result=="LOSS"; overall["open"]+=result=="OPEN"; overall["ambiguous"]+=result=="AMBIGUOUS"
            if result in ("WIN","LOSS"):overall["net_r"]+=float(row.get("r_multiple") or 0)
            n=p.get("strategy")
            if n in stats:stats[n][{"WIN":"wins","LOSS":"losses","OPEN":"open","AMBIGUOUS":"ambiguous"}[result]]+=1
            d=_entry_detail(row)
            if d:entries.append(d)
    for s in stats.values():
        decided=s["wins"]+s["losses"]; s["win_rate"]=round(100*s["wins"]/decided,2) if decided else 0; s["top_rejections"]=sorted(s.pop("reasons").items(),key=lambda x:x[1],reverse=True)[:10]
    decided=overall["wins"]+overall["losses"]; overall["net_r"]=round(overall["net_r"],4); overall["win_rate"]=round(100*overall["wins"]/decided,2) if decided else 0
    return {"status":"ok","engine_version":"10.3-MULTI-M15-M5","period_days":days,"symbol":symbol or "ALL","overall":overall,"entries":entries,"strategies":stats}

def register(app):
    @app.route("/statistics",strict_slashes=False)
    def page():return Response(PAGE,mimetype="text/html")
    @app.route("/api/statistics",strict_slashes=False)
    def api():
        try:return Response(json.dumps(_build(int(request.args.get("days",30)),request.args.get("symbol")),ensure_ascii=False),mimetype="application/json")
        except Exception as e:return Response(json.dumps({"status":"error","message":f"{type(e).__name__}: {e}"},ensure_ascii=False),status=500,mimetype="application/json")

PAGE=r'''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V10.3 Statistics</title><style>body{font-family:system-ui,sans-serif;background:#0b1220;color:#e8eef8;margin:0;padding:20px}main{max-width:1400px;margin:auto}.box{background:#121c30;border:1px solid #263654;border-radius:14px;padding:16px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.card{background:#172238;padding:12px;border-radius:10px}.muted{color:#93a4bd}.controls{display:flex;gap:8px;flex-wrap:wrap}select,input,button{background:#172238;color:#fff;border:1px solid #33425e;border-radius:8px;padding:9px}button{cursor:pointer}.table{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:8px;border-bottom:1px solid #263654;text-align:left;vertical-align:top;white-space:nowrap}th{color:#9db2d0}.buy{color:#55d68b}.sell{color:#ff6b6b}.win{color:#55d68b;font-weight:700}.loss{color:#ff6b6b;font-weight:700}.open{color:#ffd166;font-weight:700}.amb{color:#b69cff;font-weight:700}.entry-card{background:#172238;border:1px solid #2d3e5f;border-radius:12px;padding:14px;margin:10px 0}.entry-head{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}.levels{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:12px}.level{background:#101a2c;padding:9px;border-radius:8px}.reason{font-size:12px;color:#b9c8df;margin-top:3px}.badge{display:inline-block;padding:4px 8px;border-radius:99px;background:#263654}.empty{padding:24px;text-align:center;color:#93a4bd}@media(max-width:900px){.grid{grid-template-columns:repeat(3,1fr)}.levels{grid-template-columns:repeat(2,1fr)}}@media(max-width:500px){.grid{grid-template-columns:1fr 1fr}.levels{grid-template-columns:1fr}}</style></head><body><main><div class="box"><h1>📊 V10.3 Statistics</h1><div class="muted">M15 Context + M5 Setup/Trigger · แสดงออเดอร์ที่ระบบ V10.3 ผ่านเงื่อนไขจริงเท่านั้น</div><div class="controls" style="margin-top:12px"><input id="days" type="number" min="1" max="3650" value="30"><select id="symbol"><option value="">BTC + GOLD</option><option>BTC</option><option>GOLD</option></select><button onclick="load()">Refresh</button><a href="/replay" style="color:#70a7ff;padding:9px">⏪ Replay</a></div></div><div class="box"><div id="overall" class="grid"></div></div><div class="box"><h2>🎯 รายละเอียดการเข้าออเดอร์</h2><div class="muted">เรียงจากสัญญาณล่าสุด · เวลาแสดงเป็นประเทศไทย (UTC+7)</div><div id="entries"></div></div><div class="box"><h2>📋 Strategy Evaluation Log</h2><div class="table"><table><thead><tr><th>Strategy</th><th>Evaluated</th><th>PASS</th><th>FAIL</th><th>N/A</th><th>WIN</th><th>LOSS</th><th>WR</th><th>เงื่อนไขที่แพ้บ่อย</th></tr></thead><tbody id="body"></tbody></table></div></div></main><script>const $=id=>document.getElementById(id);function esc(x){return String(x??'').replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]))}function n(x){return x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:8})}function cls(x){return ({WIN:'win',LOSS:'loss',OPEN:'open',AMBIGUOUS:'amb'})[x]||''}function renderEntries(rows){if(!rows.length){$('entries').innerHTML='<div class="empty">ยังไม่มีออเดอร์ BUY/SELL ในช่วงเวลาที่เลือก</div>';return}$('entries').innerHTML=rows.map(e=>`<div class="entry-card"><div class="entry-head"><div><span class="badge ${e.direction==='BUY'?'buy':'sell'}">${e.direction==='BUY'?'🟢 BUY':'🔴 SELL'}</span> <b>${esc(e.symbol)}</b> · ${esc(e.strategy)} · ${esc(e.regime)}</div><div class="${cls(e.result)}">${esc(e.result)}</div></div><div class="muted" style="margin-top:8px">🕐 เข้า: ${esc(e.entry_time_thailand)} · ${esc(e.timeframe)} Trigger · ${esc(e.context_timeframe)} Context · ID: ${esc(e.signal_id)}</div><div class="levels"><div class="level"><div class="muted">Entry</div><b>${n(e.entry)}</b></div><div class="level"><div class="muted">Stop Loss</div><b>${n(e.sl)}</b></div><div class="level"><div class="muted">Take Profit</div><b>${n(e.tp)}</b></div><div class="level"><div class="muted">Risk / Reward</div><b>${n(e.risk_reward)}</b></div><div class="level"><div class="muted">R ผลลัพธ์</div><b>${n(e.r_multiple)}</b></div></div>${e.exit_time_thailand?`<div class="muted" style="margin-top:9px">⏱ ปิด: ${esc(e.exit_time_thailand)}</div>`:''}${e.reasons.length?`<div style="margin-top:9px"><b>เงื่อนไข/เหตุผล:</b>${e.reasons.map(r=>`<div class="reason">✓ ${esc(r)}</div>`).join('')}</div>`:''}</div>`).join('')}async function load(){try{const q=new URLSearchParams({days:$('days').value});if($('symbol').value)q.set('symbol',$('symbol').value);const d=await(await fetch('/api/statistics?'+q)).json();if(d.status!=='ok'){alert(d.message||'statistics error');return}const o=d.overall;$('overall').innerHTML=[['Rows',o.rows],['Trades',o.trades],['WIN / LOSS',o.wins+' / '+o.losses],['Win Rate',o.win_rate+'%'],['NO_TRADE',o.no_trade],['Net R',o.net_r]].map(x=>`<div class="card"><div class="muted">${x[0]}</div><b>${x[1]}</b></div>`).join('');renderEntries(d.entries||[]);$('body').innerHTML=Object.entries(d.strategies).map(([name,s])=>`<tr><td><b>${esc(name)}</b></td><td>${s.evaluated}</td><td class="buy">${s.pass}</td><td class="sell">${s.fail}</td><td class="muted">${s.not_applicable}</td><td>${s.wins}</td><td>${s.losses}</td><td>${s.win_rate}%</td><td>${(s.top_rejections||[]).map(x=>`<div class="reason">${esc(x[0])} × ${x[1]}</div>`).join('')}</td></tr>`).join('')}catch(e){console.error(e)}}load();setInterval(load,10000)</script></body></html>'''
