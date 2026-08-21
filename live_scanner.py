import os
import threading
from datetime import datetime, timezone

import engine_v5 as engine
import engine_v42 as base
from binance_data import BinanceMarketData

_SCAN_LOCK = threading.RLock()
_LAST_ALERT_KEY = None
BINANCE = BinanceMarketData()


def _config(symbol):
    return {"symbol": symbol, "timeframe": "5m", "history": int(os.getenv("LIVE_SIGNAL_HISTORY", str(engine.SIGNAL_HISTORY_POINTS)))}


def _risk_block_reason(result):
    if not isinstance(result, dict):
        return None
    for key in ("risk_block_reason", "risk_reason", "guard_reason"):
        value = result.get(key)
        if value:
            return str(value)
    if result.get("risk_blocked") is True:
        return "ระบบควบคุมความเสี่ยงไม่อนุญาตให้แจ้งสัญญาณ"
    return None


def _thai_reason(signal, result):
    patterns = result.get("patterns") or []
    parts = []
    if signal == "BUY":
        parts.append("แนวโน้ม/แรงซื้อผ่านเงื่อนไข")
    elif signal == "SELL":
        parts.append("แนวโน้ม/แรงขายผ่านเงื่อนไข")
    if patterns:
        parts.append("รูปแบบ: " + ", ".join(str(x) for x in patterns))
    return parts or ["สัญญาณผ่านเกณฑ์ของระบบ"]


def _format_signal(symbol, signal, result, levels):
    direction = "🟢 BUY — ซื้อ" if signal == "BUY" else "🔴 SELL — ขาย"
    reasons = _thai_reason(signal, result)
    reason_text = "\n".join(f"• {x}" for x in reasons)
    return (
        "🚨 <b>พบสัญญาณเข้าออเดอร์</b>\n\n"
        f"{direction}\n\n"
        f"📊 <b>สินทรัพย์:</b> {symbol}\n"
        "⏱ <b>กรอบเวลา:</b> M5\n\n"
        f"💰 <b>จุดเข้า:</b> {levels.get('entry', 'แท่งถัดไปเปิดราคา')}\n"
        f"🛑 <b>Stop Loss:</b> {levels.get('sl')}\n"
        f"🎯 <b>Take Profit:</b> {levels.get('tp')}\n\n"
        f"📐 <b>Risk/Reward:</b> {levels.get('risk_reward')}\n"
        f"⭐ <b>คะแนนสัญญาณ:</b> {result.get('score')}/100\n\n"
        "📌 <b>เหตุผล:</b>\n"
        f"{reason_text}\n\n"
        "⚠️ <b>การเปิดออเดอร์: MANUAL</b>\n"
        "👉 กรุณาตรวจสอบราคาตลาดก่อนกดออเดอร์\n"
        "🤖 <b>ระบบไม่เปิดออเดอร์อัตโนมัติ</b>"
    )


def _format_risk_block(symbol, signal, result, reason):
    direction = signal if signal in ("BUY", "SELL") else "สัญญาณ"
    return (
        "🛡️ <b>สัญญาณถูกระงับโดยระบบควบคุมความเสี่ยง</b>\n\n"
        f"📊 <b>สินทรัพย์:</b> {symbol}\n"
        f"📌 <b>ทิศทาง:</b> {direction}\n"
        f"⭐ <b>คะแนน:</b> {result.get('score')}\n\n"
        f"❌ <b>เหตุผล:</b> {reason}\n\n"
        "⛔ ระบบจะไม่ส่งสัญญาณเข้าออเดอร์\n"
        "🤖 <b>ไม่มีการเปิดออเดอร์อัตโนมัติ</b>"
    )


def scan_once(symbol="BTC/USDT"):
    global _LAST_ALERT_KEY
    symbol = (symbol or "BTC/USDT").strip().upper()
    if symbol != "BTC/USDT":
        raise ValueError(f"ไม่รองรับสินทรัพย์ Binance: {symbol}")
    with _SCAN_LOCK:
        engine.SYMBOL = symbol
        base.SYMBOL = symbol
        cfg = _config(symbol)
        df = BINANCE.fetch_candles(symbol, cfg["timeframe"], cfg["history"])
        df = BINANCE.remove_incomplete_last_candle(df, timeframe_minutes=5)
        if len(df) < 100:
            raise RuntimeError(f"มีแท่ง M5 ที่ปิดแล้วเพียง {len(df)} แท่ง ซึ่งไม่เพียงพอ")
        df = base.calculate_indicators(df)
        index = len(df) - 1
        candle = df.iloc[index]
        candle_time = str(candle.get("datetime", candle.name))
        result = base.analyze_candle(df, index)
        if not isinstance(result, dict):
            raise RuntimeError("ผลการวิเคราะห์ไม่ถูกต้อง")
        signal = result.get("signal")
        valid = bool(result.get("valid"))
        key = f"{symbol}|{candle_time}|{signal}"
        alerted = False
        telegram_result = None
        levels = result.get("trade_levels") or {}
        risk_reason = _risk_block_reason(result)

        if risk_reason and signal in ("BUY", "SELL") and key != _LAST_ALERT_KEY:
            telegram_result = engine.send_telegram(_format_risk_block(symbol, signal, result, risk_reason))
            if isinstance(telegram_result, dict) and telegram_result.get("success"):
                _LAST_ALERT_KEY = key
                alerted = True
        elif valid and signal in ("BUY", "SELL") and key != _LAST_ALERT_KEY:
            telegram_result = engine.send_telegram(_format_signal(symbol, signal, result, levels))
            if isinstance(telegram_result, dict) and telegram_result.get("success"):
                _LAST_ALERT_KEY = key
                alerted = True

        return {
            "status": "ok", "engine_version": engine.ENGINE_VERSION, "exchange": "Binance",
            "market_type": "spot", "symbol": symbol, "timeframe": "M5",
            "closed_candle": candle_time, "signal": signal, "valid": valid,
            "score": result.get("score"), "trade_levels": result.get("trade_levels"),
            "patterns": result.get("patterns") or [], "telegram_alert_sent": alerted,
            "telegram_result": telegram_result, "risk_blocked": bool(risk_reason),
            "risk_block_reason": risk_reason, "live_orders_allowed": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
