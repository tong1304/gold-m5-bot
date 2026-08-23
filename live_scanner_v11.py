"""V11 live scanner: one shared V11 engine for M5 setup + M15 trend."""
from datetime import datetime, timezone
import logging
import os
import live_scanner_v9 as _base
from v11 import engine

logger=logging.getLogger("signal_scheduler")
SUPPORTED_SYMBOLS=_base.SUPPORTED_SYMBOLS
_SCAN_LOCK=_base._SCAN_LOCK
_ALERTED_SIGNAL_KEYS=_base._ALERTED_SIGNAL_KEYS


def _load_frames(symbol):
    points=max(100,int(os.getenv("LIVE_SIGNAL_HISTORY","200"))); frames={}
    for tf in ("15m","5m"):
        frame=_base._lse_frame(symbol,tf,points)
        if len(frame)<60:raise RuntimeError(f"Insufficient closed LSE data for {symbol} {tf}: {len(frame)}")
        frames[tf]=frame.reset_index(drop=True)
    latest=frames["5m"].iloc[-1]["datetime"]
    frames["15m"]=frames["15m"][frames["15m"].datetime<=latest].reset_index(drop=True)
    return frames


def _levels_ready(levels,direction):
    try:
        e,s,t=map(float,(levels["entry"],levels["sl"],levels["tp"])); rr=float(levels["risk_reward"])
        return bool(levels.get("valid")) and rr>=2.0 and ((direction=="BUY" and s<e<t) or (direction=="SELL" and s>e>t))
    except (KeyError,TypeError,ValueError):return False


def _telegram(symbol,setup):
    d=setup["signal"]; l=setup["trade_levels"]; m15=setup["m15_trend"]; side="🟢 BUY — ซื้อ" if d=="BUY" else "🔴 SELL — ขาย"
    return (f"🚨 <b>V11 SIGNAL</b>\n\n{side}\n\n📊 <b>สินทรัพย์:</b> {symbol}\n⏱ <b>Entry:</b> M5\n🧭 <b>M15 Trend:</b> {m15.get('direction')}\n🧠 <b>Strategy:</b> {setup.get('strategy')}\n\n💰 <b>Entry:</b> {l['entry']}\n🛑 <b>SL:</b> {l['sl']}\n🎯 <b>TP:</b> {l['tp']}\n📐 <b>RR:</b> {l['risk_reward']}\n\n⚠️ ระบบแจ้งเตือนเท่านั้น ไม่เปิดออเดอร์อัตโนมัติ")


def scan_once(symbol="BTC"):
    symbol=(symbol or "BTC").upper()
    if symbol not in SUPPORTED_SYMBOLS:raise ValueError(f"Unsupported symbol: {symbol}")
    with _SCAN_LOCK:
        frames=_load_frames(symbol); m5=frames["5m"]; setup=engine.analyze(m5,frames["15m"],symbol,len(m5)-1)
        ts=str(m5.iloc[-1].datetime); setup.update({"candle_time":ts,"closed_candle":ts,"symbol":symbol,"engine_version":engine.ENGINE_VERSION})
        signal=setup.get("signal"); levels=setup.get("trade_levels") or {}; valid=signal in ("BUY","SELL") and _levels_ready(levels,signal); setup["valid"]=valid
        signal_id=f"V11-{symbol}-{ts.replace(':','').replace('-','').replace(' ','-')}-{signal if valid else 'NO_TRADE'}"; setup["signal_id"]=signal_id
        if not valid:
            reasons=setup.get("rejection_reasons") or ["NO_TRADE_REASON_UNSPECIFIED"]
            recorded=_base.history.record_no_trade({**setup,"signal":"NO_TRADE","result":"NO_TRADE","created_at":datetime.now(timezone.utc).isoformat(),"no_trade_reasons":reasons})
            return {"status":"no_trade","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":"NO_TRADE","recorded":recorded,"rejection_reasons":reasons,**setup}
        setup_key=f"{symbol}|{ts}|{signal}|{setup.get('strategy')}"
        if setup_key in _ALERTED_SIGNAL_KEYS or _base.history.get(signal_id):return {"status":"duplicate_suppressed","engine_version":engine.ENGINE_VERSION,"signal":signal,"signal_id":signal_id}
        payload={**setup,"signal_id":signal_id,"replay":False,"created_at":datetime.now(timezone.utc).isoformat()}
        recorded=_base.history.record_signal(payload); telegram=engine.send_telegram(_telegram(symbol,setup)); _ALERTED_SIGNAL_KEYS.add(setup_key)
        return {"status":"signal_sent" if telegram.get("success") else "signal_recorded_telegram_failed","engine_version":engine.ENGINE_VERSION,"symbol":symbol,"signal":signal,"strategy":setup.get("strategy"),"recorded":recorded,"telegram":telegram,"telegram_alert_sent":bool(telegram.get("success")),"setup":setup}
