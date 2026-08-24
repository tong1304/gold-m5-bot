"""Hardened V11 live scanner using LSE closed candles and persistent history."""
from __future__ import annotations
import os, threading
from datetime import datetime, timezone, timedelta
import pandas as pd
from lse import LSE
from signal_history import history
from v11 import engine
from v11.telegram import send_telegram
from v11.data_quality import require_closed, validate_frame

SUPPORTED_SYMBOLS=("BTC","GOLD")
_SCAN_LOCK=threading.Lock()

def _normalize(raw, symbol, timeframe):
    rows = raw.get("data") if isinstance(raw,dict) else raw
    if isinstance(rows,dict): rows = rows.get("data") or rows.get("rows")
    if not isinstance(rows,(list,tuple)): raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:{timeframe}")
    frame=pd.DataFrame(rows)
    for candidate in ("timestamp","time","date"):
        if "datetime" not in frame.columns and candidate in frame.columns: frame=frame.rename(columns={candidate:"datetime"})
    missing=[c for c in ("datetime","open","high","low","close") if c not in frame.columns]
    if missing: raise RuntimeError(f"LSE_INVALID_RESPONSE:{symbol}:{timeframe}:missing={missing}")
    frame["datetime"]=pd.to_datetime(frame["datetime"],utc=True,errors="coerce")
    for c in ("open","high","low","close"): frame[c]=pd.to_numeric(frame[c],errors="coerce")
    frame=frame.dropna(subset=["datetime","open","high","low","close"]).sort_values("datetime").drop_duplicates("datetime",keep="last").reset_index(drop=True)
    frame=require_closed(frame,timeframe_minutes={"5m":5,"15m":15}[timeframe])
    errors=validate_frame(frame,minimum=60,timeframe_minutes={"5m":5,"15m":15}[timeframe],market=symbol)
    if errors: raise RuntimeError(f"LSE_DATA_QUALITY:{symbol}:{timeframe}:{errors}")
    return frame

def _lse_frame(symbol,timeframe,points=200):
    market={"BTC":"BTC/USD","GOLD":"XAU/USD"}[symbol]; minutes={"5m":5,"15m":15}[timeframe]; now=datetime.now(timezone.utc); days=max(2,int(points*minutes/1440)+2)
    client=LSE(api_key=os.environ["LSE_API_KEY"]); raw=client.candles(market,timeframe,start=(now-timedelta(days=days)).date().isoformat(),end=(now+timedelta(days=1)).date().isoformat(),limit=points,order="desc")
    frame=_normalize(raw,symbol,timeframe)
    if frame.empty: raise RuntimeError(f"NO_CLOSED_CANDLES:{symbol}:{timeframe}")
    age=(pd.Timestamp.now(tz="UTC")-frame.iloc[-1].datetime).total_seconds()/60; maximum=20.0 if timeframe=="5m" else 45.0
    if age>maximum: raise RuntimeError(f"STALE_MARKET_DATA:{symbol}:{timeframe}:age={age:.1f}m")
    return frame

def _load_frames(symbol):
    points=max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))); m5=_lse_frame(symbol,"5m",points); m15=_lse_frame(symbol,"15m",points); latest=m5.iloc[-1].datetime
    # LSE timestamps represent candle opens; a 15m candle is usable only 15 minutes after its start.
    m15=m15[m15.datetime <= latest-timedelta(minutes=15)].reset_index(drop=True)
    if len(m15)<60: raise RuntimeError(f"INSUFFICIENT_CLOSED_M15_CONTEXT:{symbol}:{len(m15)}")
    return {"5m":m5,"15m":m15}

def _levels_ready(levels,direction):
    try:
        e,s,t=map(float,(levels["entry"],levels["sl"],levels["tp"])); rr=float(levels["risk_reward"])
        return bool(levels.get("valid")) and rr>=2.0 and ((direction=="BUY" and s<e<t) or (direction=="SELL" and s>e>t)) and min(e,s,t)>0
    except (KeyError,TypeError,ValueError): return False

def _telegram_text(symbol,setup):
    d=setup["signal"]; l=setup["trade_levels"]; m15=setup["m15_trend"]; side="🟢 BUY — ซื้อ" if d=="BUY" else "🔴 SELL — ขาย"
    return (f"🚨 <b>V11 SIGNAL</b>\n\n{side}\n\n📊 <b>สินทรัพย์:</b> {symbol}\n⏱ <b>Entry TF:</b> M5\n🕯 <b>แท่งปิด:</b> {setup.get('candle_time')}\n🧭 <b>M15 Trend:</b> {m15.get('direction')}\n🧠 <b>Strategy:</b> {setup.get('strategy')}\n\n💰 <b>Entry:</b> {l['entry']}\n🛑 <b>SL:</b> {l['sl']}\n🎯 <b>TP:</b> {l['tp']}\n📐 <b>RR:</b> {l['risk_reward']}R\n\n⚠️ ระบบแจ้งเตือนเท่านั้น ไม่เปิดออเดอร์อัตโนมัติ")

def scan_once(symbol="BTC"):
    symbol=(symbol or "BTC").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS: raise ValueError(f"Unsupported symbol: {symbol}")
    with _SCAN_LOCK:
        frames=_load_frames(symbol); m5=frames["5m"]; setup=engine.analyze(m5,frames["15m"],symbol,len(m5)-1); ts=str(m5.iloc[-1].datetime)
        setup.update({"candle_time":ts,"closed_candle":ts,"symbol":symbol,"engine_version":engine.ENGINE_VERSION,"live_orders_allowed":False})
        signal=setup.get("signal"); levels=setup.get("trade_levels") or {}; valid=signal in ("BUY","SELL") and _levels_ready(levels,signal); setup["valid"]=valid; suffix=signal if valid else "NO_TRADE"; signal_id=f"V11-{symbol}-{ts.replace(':','').replace('-','').replace(' ','-')}-{suffix}"; setup["signal_id"]=signal_id
        if not valid:
            recorded=history.record_no_trade({**setup,"signal":"NO_TRADE","result":"NO_TRADE","created_at":datetime.now(timezone.utc).isoformat()}); return {"status":"no_trade","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":"NO_TRADE","recorded":recorded,"rejection_reasons":setup.get("rejection_reasons",[]),**setup}
        if history.get(signal_id): return {"status":"duplicate_suppressed","engine_version":engine.ENGINE_VERSION,"signal":signal,"signal_id":signal_id}
        payload={**setup,"signal_id":signal_id,"replay":False,"created_at":datetime.now(timezone.utc).isoformat()}
        recorded=history.record_signal(payload)
        if not recorded:return {"status":"duplicate_suppressed","engine_version":engine.ENGINE_VERSION,"signal":signal,"signal_id":signal_id}
        telegram=send_telegram(_telegram_text(symbol,setup)); return {"status":"signal_sent" if telegram.get("success") else "signal_recorded_telegram_failed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":signal,"strategy":setup.get("strategy"),"signal_id":signal_id,"recorded":True,"telegram":telegram,"telegram_alert_sent":bool(telegram.get("success")),"setup":setup,"live_orders_allowed":False}
