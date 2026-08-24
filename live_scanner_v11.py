"""V12 live scanner: approved regime/8-engine pipeline with controlled re-entry."""
from __future__ import annotations
import os,threading,json
from datetime import datetime,timezone,timedelta
import pandas as pd
from lse import LSE
from signal_history import history
from v11 import engine
from v11.setup_state import state_from_history
from v11.telegram import send_telegram
from v11.data_quality import require_closed,validate_frame
SUPPORTED_SYMBOLS=("BTC","GOLD");_SCAN_LOCK=threading.Lock()

def _normalize(raw,symbol,timeframe):
    rows=raw.get("data") if isinstance(raw,dict) else raw
    if isinstance(rows,dict):rows=rows.get("data") or rows.get("rows")
    if not isinstance(rows,(list,tuple)):raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:{timeframe}")
    frame=pd.DataFrame(rows)
    for candidate in ("timestamp","time","date"):
        if "datetime" not in frame.columns and candidate in frame.columns:frame=frame.rename(columns={candidate:"datetime"})
    missing=[c for c in ("datetime","open","high","low","close") if c not in frame.columns]
    if missing:raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:{timeframe}:missing={missing}")
    frame["datetime"]=pd.to_datetime(frame["datetime"],utc=True,errors="coerce")
    for c in ("open","high","low","close"):frame[c]=pd.to_numeric(frame[c],errors="coerce")
    frame=frame.dropna(subset=["datetime","open","high","low","close"]).sort_values("datetime").drop_duplicates("datetime",keep="last").reset_index(drop=True)
    frame=require_closed(frame,timeframe_minutes={"5m":5,"15m":15}[timeframe]);errors=validate_frame(frame,minimum=60,timeframe_minutes={"5m":5,"15m":15}[timeframe],market=symbol)
    if errors:raise RuntimeError(f"LSE_DATA_QUALITY:{symbol}:{timeframe}:{errors}")
    return frame

def _lse_frame(symbol,timeframe,points=200):
    market={"BTC":"BTC/USD","GOLD":"XAU/USD"}[symbol];minutes={"5m":5,"15m":15}[timeframe];now=datetime.now(timezone.utc);days=max(2,int(points*minutes/1440)+2);client=LSE(api_key=os.environ["LSE_API_KEY"]);raw=client.candles(market,timeframe,start=(now-timedelta(days=days)).date().isoformat(),end=(now+timedelta(days=1)).date().isoformat(),limit=points,order="desc");frame=_normalize(raw,symbol,timeframe)
    if frame.empty:raise RuntimeError(f"NO_CLOSED_CANDLES:{symbol}:{timeframe}")
    age=(pd.Timestamp.now(tz="UTC")-frame.iloc[-1].datetime).total_seconds()/60;maximum=20.0 if timeframe=="5m" else 45.0
    if age>maximum:raise RuntimeError(f"STALE_MARKET_DATA:{symbol}:{timeframe}:age={age:.1f}m")
    return frame

def _load_frames(symbol):
    points=max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200")));m5=_lse_frame(symbol,"5m",points);m15=_lse_frame(symbol,"15m",points);latest=m5.iloc[-1].datetime;m15=m15[m15.datetime<=latest-timedelta(minutes=15)].reset_index(drop=True)
    if len(m15)<60:raise RuntimeError(f"INSUFFICIENT_CLOSED_M15_CONTEXT:{symbol}:{len(m15)}")
    return {"5m":m5,"15m":m15}

def _levels_ready(levels,direction):
    try:
        e,s,t=map(float,(levels["entry"],levels["sl"],levels["tp"]));rr=float(levels["risk_reward"]);return bool(levels.get("valid")) and rr>=2.0 and ((direction=="BUY" and s<e<t) or (direction=="SELL" and s>e>t)) and min(e,s,t)>0
    except (KeyError,TypeError,ValueError):return False

def _fmt(v):
    try:return f"{float(v):,.2f}"
    except (TypeError,ValueError):return "N/A"

def _live_price(symbol):
    try:
        import live_price;tick=live_price.get(symbol);return _fmt(tick.get("price")) if tick else "N/A"
    except Exception:return "N/A"

def _telegram_text(symbol,setup):
    d=setup["signal"];l=setup["trade_levels"];side="🟢 BUY — ซื้อ" if d=="BUY" else "🔴 SELL — ขาย";engine_id=setup.get("engine","NONE");entry_type=setup.get("entry_type","INITIAL")
    return (f"🚨 <b>พบสัญญาณเข้าออเดอร์ V12</b>\n\n{side}\n\n📊 <b>สินทรัพย์:</b> {symbol}\n💵 <b>ราคาปัจจุบัน:</b> {_live_price(symbol)}\n⏱ <b>กรอบเวลาเข้า:</b> M5\n🧠 <b>Regime:</b> {setup.get('regime',{}).get('regime')}\n🎯 <b>Engine:</b> {engine_id} — {setup.get('strategy')}\n🔁 <b>Entry Type:</b> {entry_type}\n🆔 <b>Setup ID:</b> {setup.get('setup_id')}\n\n💰 <b>จุดเข้า:</b> {_fmt(l['entry'])}\n🛑 <b>SL:</b> {_fmt(l['sl'])}\n🎯 <b>TP:</b> {_fmt(l['tp'])}\n📐 <b>Risk/Reward:</b> {l['risk_reward']}R\n📊 <b>Setup Score:</b> {setup.get('setup_score',{}).get('score','N/A')}/100\n\n⚠️ ระบบแจ้งเตือนเท่านั้น ไม่มีการเปิดออเดอร์อัตโนมัติ")

def _decision_summary(setup):
    trace=setup.get("decision_trace") or []
    if not trace:return "trace=NONE"
    parts=[]
    for r in trace:
        status="PASS" if r.get("status")=="PASS" else "FAIL"
        reason=",".join(r.get("rejection_reasons") or [])
        score=(r.get("score_detail") or {}).get("score")
        suffix=f" score={score}" if score is not None else f" reason={reason or '-'}"
        parts.append(f"{r.get('engine')}:{r.get('direction')}:{status}{suffix}")
    return " | ".join(parts)

def scan_once(symbol="BTC"):
    symbol=(symbol or "BTC").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS:raise ValueError(f"Unsupported symbol: {symbol}")
    with _SCAN_LOCK:
        frames=_load_frames(symbol);m5=frames["5m"];ts=str(m5.iloc[-1].datetime)
        resolved=history.resolve_open_for_symbol(symbol,m5.to_dict("records"))
        history_rows=history.list_signals(days=3650,symbol=symbol,limit=1000);state=state_from_history(history_rows)
        setup=engine.analyze(m5,frames["15m"],symbol,len(m5)-1,setup_state=state);setup.update({"candle_time":ts,"closed_candle":ts,"symbol":symbol,"engine_version":engine.ENGINE_VERSION,"live_orders_allowed":False})
        print(f"[V12 TRACE] {symbol} regime={setup.get('regime',{}).get('regime')} allowed={','.join(setup.get('allowed_engines') or [])} final={setup.get('signal')} reason={','.join(setup.get('rejection_reasons') or [])}")
        print(f"[V12 TRACE] {symbol} {_decision_summary(setup)}",flush=True)
        active=history.active_for_symbol(symbol);signal=setup.get("signal");levels=setup.get("trade_levels") or {};valid=signal in ("BUY","SELL") and _levels_ready(levels,signal)
        setup["valid"]=valid;signal_id=f"V12-{symbol}-{ts.replace(':','').replace('-','').replace(' ','-')}-{signal if valid else 'NO_TRADE'}-{setup.get('trigger_id','NONE')}";setup["signal_id"]=signal_id
        if not valid:
            recorded=history.record_no_trade({**setup,"signal":"NO_TRADE","result":"NO_TRADE","created_at":datetime.now(timezone.utc).isoformat()});return {"status":"no_trade","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":"NO_TRADE","recorded":recorded,"resolved_this_scan":resolved,**setup}
        same_setup_active=any((json_load(r.get("payload_json"),"setup_id") or r.get("setup_key"))==setup.get("setup_id") for r in active)
        if active and not same_setup_active:
            return {"status":"active_signal_locked","reason":"DIFFERENT_SETUP_ALREADY_ACTIVE","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"active_signals":[{"signal_id":r["signal_id"],"direction":r["direction"],"strategy":json_load(r.get("payload_json"),"strategy"),"setup_id":json_load(r.get("payload_json"),"setup_id"),"entry":r["entry"],"sl":r["sl"],"tp":r["tp"]} for r in active],"resolved_this_scan":resolved,"setup":setup,"live_orders_allowed":False}
        payload={**setup,"signal_id":signal_id,"setup_key":setup.get("setup_id"),"replay":False,"created_at":datetime.now(timezone.utc).isoformat()};recorded=history.record_signal(payload)
        if not recorded:return {"status":"duplicate_suppressed","reason":"HISTORY_INSERT_REJECTED","engine_version":engine.ENGINE_VERSION,"signal":signal,"signal_id":signal_id}
        telegram=send_telegram(_telegram_text(symbol,setup));return {"status":"signal_sent" if telegram.get("success") else "signal_recorded_telegram_failed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":signal,"strategy":setup.get("strategy"),"engine":setup.get("engine"),"entry_type":setup.get("entry_type"),"setup_id":setup.get("setup_id"),"trigger_id":setup.get("trigger_id"),"signal_id":signal_id,"recorded":True,"telegram":telegram,"telegram_alert_sent":bool(telegram.get("success")),"setup":setup,"live_orders_allowed":False}

def json_load(payload,key):
    try:return json.loads(payload or "{}").get(key)
    except Exception:return None
