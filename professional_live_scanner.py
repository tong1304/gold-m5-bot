from __future__ import annotations
import os, threading
from datetime import datetime, timezone, timedelta
import pandas as pd
from lse import LSE
import professional_engine_core as _core
from professional_engine_core import analyze, ENGINE_VERSION
from professional_e3_brain import e3_structure as _professional_e3_structure
from signal_history import history
from production_v2_telegram import send_telegram

# E3 is intentionally implemented as one professional brain for now.
# Its future 3A-3F decomposition is parked and not part of runtime execution.
_core.e3_structure = _professional_e3_structure

SUPPORTED_SYMBOLS=("BTC","GOLD"); _LOCK=threading.Lock()

def _normalize(raw,symbol,timeframe):
    rows=raw.get("data") if isinstance(raw,dict) else raw
    if isinstance(rows,dict): rows=rows.get("data") or rows.get("rows")
    if not isinstance(rows,(list,tuple)): raise RuntimeError("LSE_INVALID_RESPONSE")
    frame=pd.DataFrame([r for r in rows if isinstance(r,dict) and {"open","high","low","close"}.issubset(r)])
    if "datetime" not in frame.columns:
        for k in ("timestamp","time","date"):
            if k in frame.columns: frame=frame.rename(columns={k:"datetime"}); break
    need=["datetime","open","high","low","close"]
    if any(k not in frame.columns for k in need): raise RuntimeError("LSE_MISSING_OHLC")
    frame["datetime"]=pd.to_datetime(frame.datetime,utc=True,errors="coerce")
    for k in need[1:]: frame[k]=pd.to_numeric(frame[k],errors="coerce")
    frame=frame.dropna(subset=need).sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)
    mins={"5m":5,"15m":15,"1h":60}[timeframe]; cutoff=pd.Timestamp.now(tz="UTC").floor(f"{mins}min")
    frame=frame.loc[frame.datetime<cutoff].reset_index(drop=True)
    if len(frame)<80: raise RuntimeError(f"INSUFFICIENT_CONTEXT:{symbol}:{timeframe}")
    age=(pd.Timestamp.now(tz="UTC")-frame.iloc[-1].datetime).total_seconds()/60
    if age>{"5m":20,"15m":45,"1h":180}[timeframe]: raise RuntimeError(f"STALE_MARKET_DATA:{symbol}:{timeframe}:age={age:.1f}m")
    return frame

def _lse_frame(symbol,timeframe="5m",points=200):
    market={"BTC":"BTC/USD","GOLD":"XAU/USD"}[symbol]; mins={"5m":5,"15m":15,"1h":60}[timeframe]
    now=datetime.now(timezone.utc); days=max(3,int(points*mins/1440)+3)
    client=LSE(api_key=os.environ["LSE_API_KEY"])
    try: raw=client.candles(market,timeframe,start=(now-timedelta(days=days)).date().isoformat(),end=(now+timedelta(days=1)).date().isoformat(),limit=points,order="desc")
    finally:
        try: client.disconnect()
        except Exception: pass
    return _normalize(raw,symbol,timeframe)

def _load_frames(symbol):
    p=max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))); return {"1h":_lse_frame(symbol,"1h",p),"15m":_lse_frame(symbol,"15m",p),"5m":_lse_frame(symbol,"5m",p)}

def _telegram_text(symbol,d):
    pd=d.get("professional_decision",{}); e8=pd.get("e8",{}); e9=pd.get("e9",{}); side="🟢 BUY — ซื้อ" if d.get("signal")=="BUY" else "🔴 SELL — ขาย"
    return (f"🚨 <b>PROFESSIONAL DECISION ENGINE</b>\n\n{side}\n\n📊 <b>สินทรัพย์:</b> {symbol}\n🧠 <b>Architecture:</b> E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9\n\n" f"E1: {pd.get('e1',{}).get('state')}\nE2: {pd.get('e2',{}).get('playbook')}\nE3: {pd.get('e3',{}).get('structure')}\nE4: {pd.get('e4',{}).get('liquidity_state')}\nE5: {pd.get('e5',{}).get('location')}\nE6: {pd.get('e6',{}).get('setup')}\nE7: {pd.get('e7',{}).get('confirmation')}\nE8: RR {e8.get('rr')} / min {e8.get('minimum_rr')}\n\n🎯 <b>Final Decision E9:</b> {e9.get('decision')}\n🧾 <b>Reason:</b> {e9.get('decision_reason')}\n\n⚠️ ระบบแจ้งเตือนเท่านั้น ไม่มีการเปิดออเดอร์อัตโนมัติ")

def scan_once(symbol="BTC"):
    symbol=symbol.upper();
    if symbol not in SUPPORTED_SYMBOLS: raise ValueError(f"Unsupported symbol: {symbol}")
    with _LOCK:
        frames=_load_frames(symbol); m5,m15,h1=frames["5m"],frames["15m"],frames["1h"]; ts=str(m5.iloc[-1].datetime)
        decision=analyze(m5,m15,h1,symbol=symbol)
        decision.update({"candle_time":ts,"closed_candle":ts,"symbol":symbol,"engine_version":ENGINE_VERSION,"live_orders_allowed":False})
        if decision["signal"] not in ("BUY","SELL"):
            recorded=history.record_no_trade({**decision,"signal":"NO_TRADE","result":"NO_TRADE","created_at":datetime.now(timezone.utc).isoformat()})
            return {"status":"no_trade","recorded":recorded,**decision}
        payload={**decision,"signal_id":f"PE9-{symbol}-{ts.replace(':','').replace('-','').replace(' ','-')}-{decision['signal']}","setup_key":decision.get("professional_decision",{}).get("e6",{}).get("setup"),"created_at":datetime.now(timezone.utc).isoformat()}
        recorded=history.record_signal(payload)
        if not recorded:return {"status":"duplicate_suppressed",**decision}
        tg=send_telegram(_telegram_text(symbol,decision))
        return {"status":"signal_sent" if tg.get("success") else "signal_recorded_telegram_failed","telegram":tg,"telegram_alert_sent":bool(tg.get("success")),**decision}
