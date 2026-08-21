import os
import threading
from datetime import datetime, timezone

import engine_v5 as engine
import engine_v42 as base
from binance_data import BinanceMarketData
from pattern_engine import detect_all, confluence

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


def _format_signal(symbol, signal, result, levels, pattern_result, confluence_result):
    direction = "🟢 BUY — ซื้อ" if signal == "BUY" else "🔴 SELL — ขาย"
    evidence = confluence_result["buy_evidence"] if signal == "BUY" else confluence_result["sell_evidence"]
    evidence_lines = "\n".join(f"• {p['name']}" for p in evidence[:8]) or "• สัญญาณผ่านเกณฑ์ระบบ"
    categories = confluence_result["buy_categories"] if signal == "BUY" else confluence_result["sell_categories"]
    return (
        "🚨 <b>พบสัญญาณเข้าออเดอร์</b>\n\n"
        f"{direction}\n\n📊 <b>สินทรัพย์:</b> {symbol}\n⏱ <b>กรอบเวลาเข้า:</b> M5\n\n"
        f"💰 <b>จุดเข้า:</b> {levels.get('entry', 'แท่งถัดไปเปิดราคา')}\n"
        f"🛑 <b>Stop Loss:</b> {levels.get('sl')}\n🎯 <b>Take Profit:</b> {levels.get('tp')}\n\n"
        f"📐 <b>Risk/Reward:</b> {levels.get('risk_reward')}\n"
        f"⭐ <b>คะแนนความสอดคล้อง:</b> {confluence_result['score']}/100\n"
        f"🔎 <b>จำนวนหลักฐาน:</b> {len(evidence)}\n"
        f"🧩 <b>หมวดที่สนับสนุน:</b> {', '.join(categories) if categories else 'ไม่มี'}\n\n"
        "📌 <b>รูปแบบที่ตรวจพบ:</b>\n" f"{evidence_lines}\n\n"
        "⚠️ <b>การเปิดออเดอร์: MANUAL</b>\n"
        "👉 กรุณาตรวจสอบราคาตลาดก่อนกดออเดอร์\n🤖 <b>ระบบไม่เปิดออเดอร์อัตโนมัติ</b>"
    )


def _format_risk_block(symbol, signal, result, reason):
    return (
        "🛡️ <b>สัญญาณถูกระงับโดยระบบควบคุมความเสี่ยง</b>\n\n"
        f"📊 <b>สินทรัพย์:</b> {symbol}\n📌 <b>ทิศทาง:</b> {signal}\n"
        f"⭐ <b>คะแนน:</b> {result.get('score')}\n\n❌ <b>เหตุผล:</b> {reason}\n\n"
        "⛔ ระบบจะไม่ส่งสัญญาณเข้าออเดอร์\n🤖 <b>ไม่มีการเปิดออเดอร์อัตโนมัติ</b>"
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
        pattern_result = detect_all(df, index)
        conf = confluence(pattern_result["patterns"], minimum=3)
        result = base.analyze_candle(df, index)
        if not isinstance(result, dict):
            raise RuntimeError("ผลการวิเคราะห์ไม่ถูกต้อง")
        signal = conf["signal"] if conf["signal"] != "NO_TRADE" else result.get("signal")
        # New pattern layer is authoritative only when it has sufficient cross-category evidence.
        if conf["signal"] == "NO_TRADE":
            signal = "NO_TRADE"
        valid = signal in ("BUY", "SELL") and bool(result.get("valid"))
        key = f"{symbol}|{candle_time}|{signal}"
        alerted = False
        telegram_result = None
        levels = result.get("trade_levels") or {}
        risk_reason = _risk_block_reason(result)
        if risk_reason and signal in ("BUY", "SELL") and key != _LAST_ALERT_KEY:
            telegram_result = engine.send_telegram(_format_risk_block(symbol, signal, result, risk_reason))
        elif valid and key != _LAST_ALERT_KEY:
            telegram_result = engine.send_telegram(_format_signal(symbol, signal, result, levels, pattern_result, conf))
        if isinstance(telegram_result, dict) and telegram_result.get("success"):
            _LAST_ALERT_KEY = key
            alerted = True
        return {
            "status":"ok", "engine_version":engine.ENGINE_VERSION, "exchange":"Binance", "market_type":"spot",
            "symbol":symbol, "timeframe":"M5", "closed_candle":candle_time, "signal":signal, "valid":valid,
            "score":conf["score"], "engine_score":result.get("score"), "trade_levels":result.get("trade_levels"),
            "pattern_count":pattern_result["pattern_count"], "patterns":pattern_result["patterns"],
            "confluence":conf, "telegram_alert_sent":alerted, "telegram_result":telegram_result,
            "risk_blocked":bool(risk_reason), "risk_block_reason":risk_reason, "live_orders_allowed":False,
            "generated_at":datetime.now(timezone.utc).isoformat(),
        }
