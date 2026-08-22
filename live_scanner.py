import os
import threading
from datetime import datetime, timezone

import engine_v5 as engine
import engine_v42 as base
from binance_data import BinanceMarketData
from pattern_engine import detect_all, confluence

_SCAN_LOCK = threading.RLock()
_ALERTED_SIGNAL_KEYS = set()
BINANCE = BinanceMarketData()
SUPPORTED_SYMBOLS = {"BTC", "ETH", "SOL", "GOLD"}
SYMBOL_MAP = {"BTC": "BTC/USDT", "ETH": "ETH/USDT", "SOL": "SOL/USDT", "GOLD": "XAU/USDT"}


def _market_symbol(symbol):
    return SYMBOL_MAP.get((symbol or "").strip().upper(), symbol)


def _config(symbol, timeframe):
    return {"symbol": _market_symbol(symbol), "timeframe": timeframe, "history": int(os.getenv("LIVE_SIGNAL_HISTORY", str(engine.SIGNAL_HISTORY_POINTS)))}


def _risk_block_reason(result):
    if not isinstance(result, dict): return None
    for key in ("risk_block_reason", "risk_reason", "guard_reason"):
        value = result.get(key)
        if value: return str(value)
    if result.get("risk_blocked") is True: return "ระบบควบคุมความเสี่ยงไม่อนุญาตให้แจ้งสัญญาณ"
    return None


def _tf_bias(df, timeframe):
    df = base.calculate_indicators(df.copy()); i = len(df) - 1
    close = float(df.close.iloc[i]); ema20 = float(df.close.ewm(span=20, adjust=False).mean().iloc[i]); ema50 = float(df.close.ewm(span=50, adjust=False).mean().iloc[i])
    bias = "BUY" if close > ema20 and ema20 > ema50 else "SELL" if close < ema20 and ema20 < ema50 else "NEUTRAL"
    patterns = detect_all(df, i); conf = confluence(patterns["patterns"], minimum=2)
    return {"timeframe": timeframe, "bias": bias, "close": close, "ema20": ema20, "ema50": ema50, "pattern_count": patterns["pattern_count"], "patterns": patterns["patterns"], "confluence": conf}


def _format_signal(symbol, signal, result, levels, pattern_result, confluence_result, mtf):
    direction = "🟢 BUY — ซื้อ" if signal == "BUY" else "🔴 SELL — ขาย"
    evidence = confluence_result["buy_evidence"] if signal == "BUY" else confluence_result["sell_evidence"]
    evidence_lines = "\n".join(f"• {p['name']}" for p in evidence[:8]) or "• สัญญาณผ่านเกณฑ์ระบบ"
    categories = confluence_result["buy_categories"] if signal == "BUY" else confluence_result["sell_categories"]
    return ("🚨 <b>พบสัญญาณเข้าออเดอร์</b>\n\n" f"{direction}\n\n📊 <b>สินทรัพย์:</b> {symbol}\n⏱ <b>กรอบเวลาเข้า:</b> M5\n\n" "🧭 <b>ยืนยันหลายไทม์เฟรม</b>\n" f"H1: {mtf['H1']['bias']} | M15: {mtf['M15']['bias']} | M5: {signal}\n\n" f"💰 <b>จุดเข้า:</b> {levels.get('entry', 'แท่งถัดไปเปิดราคา')}\n🛑 <b>Stop Loss:</b> {levels.get('sl')}\n🎯 <b>Take Profit:</b> {levels.get('tp')}\n\n" f"📐 <b>Risk/Reward:</b> {levels.get('risk_reward')}\n⭐ <b>คะแนนความสอดคล้อง M5:</b> {confluence_result['score']}/100\n🔎 <b>หลักฐาน M5:</b> {len(evidence)}\n🧩 <b>หมวดที่สนับสนุน:</b> {', '.join(categories) if categories else 'ไม่มี'}\n\n" "📌 <b>รูปแบบ M5:</b>\n" f"{evidence_lines}\n\n⚠️ <b>การเปิดออเดอร์: MANUAL</b>\n👉 กรุณาตรวจสอบราคาตลาดก่อนกดออเดอร์\n🤖 <b>ระบบไม่เปิดออเดอร์อัตโนมัติ</b>")


def _format_risk_block(symbol, signal, result, reason):
    return ("🛡️ <b>สัญญาณถูกระงับโดยระบบควบคุมความเสี่ยง</b>\n\n" f"📊 <b>สินทรัพย์:</b> {symbol}\n📌 <b>ทิศทาง:</b> {signal}\n⭐ <b>คะแนน:</b> {result.get('score')}\n\n❌ <b>เหตุผล:</b> {reason}\n\n⛔ ระบบจะไม่ส่งสัญญาณเข้าออเดอร์\n🤖 <b>ไม่มีการเปิดออเดอร์อัตโนมัติ</b>")


def scan_once(symbol="BTC"):
    symbol = (symbol or "BTC").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS: raise ValueError(f"ไม่รองรับสินทรัพย์: {symbol}; รองรับ: {', '.join(sorted(SUPPORTED_SYMBOLS))}")
    market_symbol = _market_symbol(symbol)
    with _SCAN_LOCK:
        engine.SYMBOL = market_symbol; base.SYMBOL = market_symbol
        frames = {}; tf_minutes = {"1h":60,"15m":15,"5m":5}
        for tf in ("1h","15m","5m"):
            cfg = _config(symbol, tf); df = BINANCE.fetch_candles(market_symbol, tf, cfg["history"]); df = BINANCE.remove_incomplete_last_candle(df, timeframe_minutes=tf_minutes[tf])
            if len(df) < 100: raise RuntimeError(f"ข้อมูล {tf} ของ {symbol} ที่ปิดแล้วไม่เพียงพอ: {len(df)} แท่ง")
            frames[tf] = df
        h1 = _tf_bias(frames["1h"], "H1"); m15 = _tf_bias(frames["15m"], "M15")
        m5_df = base.calculate_indicators(frames["5m"]); index = len(m5_df)-1; candle = m5_df.iloc[index]; candle_time = str(candle.get("datetime", candle.name))
        pattern_result = detect_all(m5_df,index); conf = confluence(pattern_result["patterns"], minimum=3); result = base.analyze_candle(m5_df,index)
        if not isinstance(result,dict): raise RuntimeError("ผลการวิเคราะห์ไม่ถูกต้อง")
        m5_signal = conf["signal"]; aligned = m5_signal in ("BUY","SELL") and h1["bias"] == m5_signal and m15["bias"] == m5_signal
        signal = m5_signal if aligned else "NO_TRADE"; valid = aligned and bool(result.get("valid")); key = f"{symbol}|{candle_time}|{signal}"
        alerted=False; telegram_result=None; levels=result.get("trade_levels") or {}; risk_reason=_risk_block_reason(result)
        with _SCAN_LOCK:
            already_alerted = key in _ALERTED_SIGNAL_KEYS
            if not already_alerted:
                if risk_reason and signal in ("BUY","SELL"):
                    telegram_result=engine.send_telegram(_format_risk_block(symbol,signal,result,risk_reason))
                elif valid:
                    telegram_result=engine.send_telegram(_format_signal(symbol,signal,result,levels,pattern_result,conf,{"H1":h1,"M15":m15}))
                if isinstance(telegram_result,dict) and telegram_result.get("success"):
                    _ALERTED_SIGNAL_KEYS.add(key); alerted=True
        return {"status":"ok","engine_version":engine.ENGINE_VERSION,"exchange":"Binance","market_type":"spot","symbol":symbol,"market_symbol":market_symbol,"timeframe":"M5","closed_candle":candle_time,"signal":signal,"valid":valid,"score":conf["score"],"engine_score":result.get("score"),"trade_levels":result.get("trade_levels"),"pattern_count":pattern_result["pattern_count"],"patterns":pattern_result["patterns"],"confluence":conf,"multi_timeframe":{"H1":h1,"M15":m15,"M5":{"signal":m5_signal,"valid":bool(result.get("valid"))}},"alignment":aligned,"duplicate_alert_suppressed":already_alerted,"telegram_alert_sent":alerted,"telegram_result":telegram_result,"risk_blocked":bool(risk_reason),"risk_block_reason":risk_reason,"live_orders_allowed":False,"generated_at":datetime.now(timezone.utc).isoformat()}
