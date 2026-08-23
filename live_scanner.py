# M5_DIRECTION_POLICY: majority confirmed patterns; discard opposing side
import math
import os
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import engine_v5 as engine
import engine_v42 as base
from binance_data import BinanceMarketData
from pattern_engine import detect_all, confluence

_SCAN_LOCK = threading.RLock()
_ALERTED_SIGNAL_KEYS = set()
BINANCE = BinanceMarketData()
BANGKOK = ZoneInfo("Asia/Bangkok")


def _format_candle_time_bangkok(value):
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BANGKOK).strftime("%d/%m/%Y %H:%M:%S") + " (กรุงเทพฯ)"
    except (TypeError, ValueError, OverflowError):
        return str(value)
SUPPORTED_SYMBOLS = {"BTC", "ETH", "SOL", "GOLD"}
SYMBOL_MAP = {"BTC": "BTC/USDT", "ETH": "ETH/USDT", "SOL": "SOL/USDT", "GOLD": "XAU/USDT"}


def _market_symbol(symbol):
    return SYMBOL_MAP.get((symbol or "").strip().upper(), symbol)


def _config(symbol, timeframe):
    return {
        "symbol": _market_symbol(symbol),
        "timeframe": timeframe,
        "history": int(os.getenv("LIVE_SIGNAL_HISTORY", str(engine.SIGNAL_HISTORY_POINTS))),
    }


def _tf_bias(df, timeframe):
    df = base.calculate_indicators(df.copy())
    i = len(df) - 1
    close = float(df.close.iloc[i])
    ema20 = float(df.close.ewm(span=20, adjust=False).mean().iloc[i])
    ema50 = float(df.close.ewm(span=50, adjust=False).mean().iloc[i])
    bias = "BUY" if close > ema20 and ema20 > ema50 else "SELL" if close < ema20 and ema20 < ema50 else "NEUTRAL"
    patterns = detect_all(df, i)
    conf = confluence(patterns["patterns"], minimum=2)
    return {"timeframe": timeframe, "bias": bias, "close": close, "ema20": ema20, "ema50": ema50, "pattern_count": patterns["pattern_count"], "patterns": patterns["patterns"], "confluence": conf}


def _format_price(value):
    try: return f"{float(value):,.8f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError): return str(value)


def _levels_ready(levels, direction=None):
    if not isinstance(levels, dict): return False
    try:
        entry = float(levels.get("entry"))
        sl = float(levels.get("sl"))
        tp = float(levels.get("tp"))
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if not all(math.isfinite(v) for v in (entry, sl, tp, risk, reward)): return False
        if not (entry > 0 and sl > 0 and tp > 0 and risk > 0 and reward > 0): return False
        if direction == "BUY" and not (sl < entry < tp): return False
        if direction == "SELL" and not (sl > entry > tp): return False
        raw_rr = reward / risk if risk else 0.0
        configured_rr = float(levels.get("risk_reward", levels.get("effective_rr", raw_rr)) or 0)
        effective_rr = float(levels.get("effective_rr", raw_rr) or raw_rr)
        return all(math.isfinite(v) for v in (raw_rr, configured_rr, effective_rr)) and raw_rr >= 2.0 and configured_rr >= 2.0 and effective_rr >= 2.0
    except (TypeError, ValueError):
        return False


def _build_trade_levels(df, index, direction):
    row = df.iloc[index]
    close = float(row["close"])
    try:
        entry = engine.calculate_execution_price(close, direction)
        levels = engine.calculate_trade_levels(df, index, direction, entry)
        if _levels_ready(levels, direction):
            levels["entry"] = levels.get("entry", levels.get("entry_reference", entry))
            levels["source"] = "engine_v5"
            levels["validated"] = True
            return levels
    except Exception as exc:
        print(f"[{direction}] Engine trade-level calculation failed: {type(exc).__name__}: {exc}", flush=True)

    # Robust ATR fallback. Never allow NaN/inf ATR to poison Entry/SL/TP.
    atr_candidates = []
    if "atr" in df.columns:
        try:
            atr_candidates.append(float(df["atr"].iloc[index]))
        except (TypeError, ValueError, IndexError):
            pass
    try:
        atr_candidates.extend(float(v) for v in df["high"].sub(df["low"]).tail(14).tolist())
    except Exception:
        pass
    finite_atrs = [v for v in atr_candidates if math.isfinite(v) and v > 0]
    observed_atr = sum(finite_atrs[-14:]) / len(finite_atrs[-14:]) if finite_atrs else 0.0
    minimum_atr = float(engine.MINIMUM_ATR)
    atr = max(observed_atr, minimum_atr, 1e-12)

    stop_atr = min(max(float(engine.MIN_STOP_ATR), 1.0), float(engine.MAX_STOP_ATR))
    risk = atr * stop_atr
    rr_target = max(float(engine.RISK_REWARD), 2.0)
    entry = engine.calculate_execution_price(close, direction)
    if direction == "BUY":
        sl, tp = entry - risk, entry + risk * rr_target
    else:
        sl, tp = entry + risk, entry - risk * rr_target
    levels = {
        "entry": round(entry, 8),
        "sl": round(sl, 8),
        "tp": round(tp, 8),
        "risk": round(abs(entry-sl), 8),
        "reward": round(abs(tp-entry), 8),
        "risk_reward": round(rr_target, 3),
        "effective_rr": round(rr_target, 3),
        "source": "atr_fallback",
        "validated": False,
    }
    levels["validated"] = _levels_ready(levels, direction)
    return levels


def _resolve_m5_direction(conf, buy_confirmed, sell_confirmed):
    buy_count, sell_count = len(buy_confirmed), len(sell_confirmed)
    if buy_count > sell_count and buy_count >= 1: return "BUY"
    if sell_count > buy_count and sell_count >= 1: return "SELL"
    return "NO_TRADE"


def _format_signal(symbol, signal, levels, confluence_result, mtf, previous_close, candle_time, signal_id, evidence):
    direction = "🟢 BUY — ซื้อ" if signal == "BUY" else "🔴 SELL — ขาย"
    evidence_lines = "\n".join(f"• {p['name']}" for p in evidence[:8]) or "• สัญญาณผ่านเกณฑ์ระบบ"
    categories = confluence_result["buy_categories"] if signal == "BUY" else confluence_result["sell_categories"]
    return ("🚨 <b>พบสัญญาณเข้าออเดอร์</b>\n\n" f"{direction}\n\n" f"📊 <b>สินทรัพย์:</b> {symbol}\n" "⏱ <b>กรอบเวลาเข้า:</b> M5\n\n" f"🕯 <b>แท่งที่ใช้วิเคราะห์:</b> {_format_candle_time_bangkok(candle_time)}\n" f"📌 <b>ราคาปิดแท่งก่อนหน้า:</b> {_format_price(previous_close)}\n" f"🔐 <b>Signal ID:</b> {signal_id}\n\n" "🧭 <b>ยืนยันหลายไทม์เฟรม</b>\n" f"H1: {mtf['H1']['bias']} | M15: {mtf['M15']['bias']} | M5: {signal}\n\n" f"💰 <b>จุดเข้า:</b> {_format_price(levels.get('entry'))}\n" f"🛑 <b>Stop Loss:</b> {_format_price(levels.get('sl'))}\n" f"🎯 <b>Take Profit:</b> {_format_price(levels.get('tp'))}\n\n" f"📐 <b>Risk/Reward:</b> {levels.get('risk_reward')}\n" f"⭐ <b>คะแนนความสอดคล้อง M5:</b> {confluence_result['score']}/100\n" f"🔎 <b>หลักฐาน M5:</b> {len(evidence)}\n" f"🧩 <b>หมวดที่สนับสนุน:</b> {', '.join(categories) if categories else 'ไม่มี'}\n\n" "📌 <b>รูปแบบ M5:</b>\n" f"{evidence_lines}\n\n" "⚠️ <b>การเปิดออเดอร์: คุณเป็นผู้กดเอง</b>\n" "👉 กรุณาตรวจสอบราคาตลาดก่อนกดออเดอร์\n" "🤖 <b>ระบบไม่เปิดออเดอร์อัตโนมัติ</b>")


def scan_once(symbol="BTC"):
    symbol = (symbol or "BTC").strip().upper()
    if symbol not in SUPPORTED_SYMBOLS: raise ValueError(f"ไม่รองรับสินทรัพย์: {symbol}; รองรับ: {', '.join(sorted(SUPPORTED_SYMBOLS))}")
    market_symbol = _market_symbol(symbol)
    with _SCAN_LOCK:
        engine.SYMBOL = market_symbol; base.SYMBOL = market_symbol
        # Scheduler calls scan_once directly, so enforce the same per-symbol
        # execution/RR configuration here instead of relying on the Flask route.
        cfg = {"BTC": {"MINIMUM_ATR": 20.0, "MIN_STOP_ATR": 1.0, "MAX_STOP_ATR": 3.0, "SPREAD": 5.0, "SLIPPAGE": 2.0}, "ETH": {"MINIMUM_ATR": 1.0, "MIN_STOP_ATR": 1.0, "MAX_STOP_ATR": 3.0, "SPREAD": 0.50, "SLIPPAGE": 0.20}, "SOL": {"MINIMUM_ATR": 0.20, "MIN_STOP_ATR": 1.0, "MAX_STOP_ATR": 3.0, "SPREAD": 0.10, "SLIPPAGE": 0.05}, "GOLD": {"MINIMUM_ATR": 1.0, "MIN_STOP_ATR": 1.0, "MAX_STOP_ATR": 3.0, "SPREAD": 0.50, "SLIPPAGE": 0.20}}[symbol]
        for target in (engine, base):
            for key, value in cfg.items(): setattr(target, key, value)
            target.MIN_RISK_REWARD = max(float(os.getenv("MIN_RISK_REWARD", "2.0")), 2.0)
            target.RISK_REWARD = max(float(os.getenv("RISK_REWARD", "2.0")), 2.0)
        frames = {}; tf_minutes = {"1h": 60, "15m": 15, "5m": 5}
        for tf in ("1h", "15m", "5m"):
            cfg = _config(symbol, tf)
            df = BINANCE.fetch_candles(market_symbol, tf, cfg["history"])
            df = BINANCE.remove_incomplete_last_candle(df, timeframe_minutes=tf_minutes[tf])
            if len(df) < 100: raise RuntimeError(f"ข้อมูล {tf} ของ {symbol} ที่ปิดแล้วไม่เพียงพอ: {len(df)} แท่ง")
            frames[tf] = df
        h1, m15 = _tf_bias(frames["1h"], "H1"), _tf_bias(frames["15m"], "M15")
        m5_df = base.calculate_indicators(frames["5m"]); index = len(m5_df) - 1; candle = m5_df.iloc[index]
        candle_time = str(candle.get("datetime", candle.name)); previous_close = float(candle["close"])
        pattern_result = detect_all(m5_df, index); conf = confluence(pattern_result["patterns"], minimum=1); result = base.analyze_candle(m5_df, index)
        if not isinstance(result, dict): raise RuntimeError("ผลการวิเคราะห์ไม่ถูกต้อง")
        confirmed_m5 = [p for p in pattern_result["patterns"] if p.get("confirmed") is True and p.get("direction") in ("BUY", "SELL") and p.get("category") in {"PRICE_ACTION", "CHART_PATTERN", "SMC_ICT", "SUPPLY_DEMAND", "TREND_BREAKOUT", "FIBONACCI_HARMONIC", "INDICATOR_SESSION"}]
        buy_confirmed = [p for p in confirmed_m5 if p.get("direction") == "BUY"]; sell_confirmed = [p for p in confirmed_m5 if p.get("direction") == "SELL"]
        m5_signal = _resolve_m5_direction(conf, buy_confirmed, sell_confirmed)
        if m5_signal == "BUY": selected_evidence, discarded_opposite = buy_confirmed, sell_confirmed
        elif m5_signal == "SELL": selected_evidence, discarded_opposite = sell_confirmed, buy_confirmed
        else: selected_evidence, discarded_opposite = [], []
        pattern_signal = m5_signal if selected_evidence else None

        opposite = "SELL" if pattern_signal == "BUY" else "BUY"
        aligned = pattern_signal in ("BUY", "SELL") and h1["bias"] != opposite and m15["bias"] != opposite
        signal = pattern_signal if aligned else "NO_TRADE"
        levels = _build_trade_levels(m5_df, index, signal) if signal in ("BUY", "SELL") else {}
        levels_ready = _levels_ready(levels, signal if signal in ("BUY", "SELL") else None); valid = aligned and levels_ready
        key = f"{symbol}|{candle_time}"; signal_id = f"{symbol}-{candle_time.replace(':', '').replace('-', '').replace(' ', '-')}-{signal}"
        telegram_result = None; alerted = False
        reasons = []
        if not confirmed_m5: reasons.append("NO_CONFIRMED_M5_PATTERN")
        if m5_signal == "NO_TRADE": reasons.append(f"M5_PATTERN_TIE:BUY={len(buy_confirmed)},SELL={len(sell_confirmed)}" if (buy_confirmed or sell_confirmed) else "NO_DIRECTIONAL_M5_PATTERN")
        elif conf.get("signal") == "NO_TRADE": reasons.append("M5_MAJORITY_RULE_USED")
        if len(selected_evidence) < 1: reasons.append(f"M5_DIRECTIONAL_EVIDENCE_LOW:{len(selected_evidence)}")
        if pattern_signal and h1["bias"] == opposite: reasons.append(f"H1_MISMATCH:{h1['bias']}")
        if pattern_signal and m15["bias"] == opposite: reasons.append(f"M15_MISMATCH:{m15['bias']}")
        if signal in ("BUY", "SELL") and not levels_ready: reasons.append("RR_BELOW_2_OR_TRADE_LEVELS_NOT_READY")
        if valid: reasons = []
        print(f"[{symbol}] Decision: pattern_signal={pattern_signal} raw_m5_confluence={conf.get('signal')} m5_direction={m5_signal} H1={h1['bias']} M15={m15['bias']} confirmed_patterns={len(confirmed_m5)} BUY={len(buy_confirmed)} SELL={len(sell_confirmed)} selected={len(selected_evidence)} discarded_opposite={len(discarded_opposite)} levels_ready={levels_ready} aligned={aligned} valid={valid} level_source={levels.get('source', 'none')} rr={levels.get('risk_reward', 'none')} reasons={','.join(reasons) if reasons else 'PASS'}", flush=True)
        with _SCAN_LOCK:
            already_alerted = key in _ALERTED_SIGNAL_KEYS
            if valid and not already_alerted:
                message = _format_signal(symbol, signal, levels, conf, {"H1": h1, "M15": m15}, previous_close, candle_time, signal_id, selected_evidence)
                telegram_result = engine.send_telegram(message)
                if isinstance(telegram_result, dict) and telegram_result.get("success"):
                    _ALERTED_SIGNAL_KEYS.add(key); alerted = True
        return {"status":"ok", "engine_version":engine.ENGINE_VERSION, "exchange":"Binance", "market_type":"spot", "symbol":symbol, "market_symbol":market_symbol, "timeframe":"M5", "closed_candle":candle_time, "previous_close":previous_close, "signal_id":signal_id, "signal":signal, "valid":valid, "score":conf["score"], "engine_score":result.get("score"), "trade_levels":levels, "levels_ready":levels_ready, "pattern_count":pattern_result["pattern_count"], "patterns":pattern_result["patterns"], "confirmed_m5_patterns":confirmed_m5, "confirmed_m5_buy":buy_confirmed, "confirmed_m5_sell":sell_confirmed, "selected_m5_evidence":selected_evidence, "discarded_opposite_m5":discarded_opposite, "pattern_signal":pattern_signal, "decision_reasons":reasons, "confluence":conf, "multi_timeframe":{"H1":h1,"M15":m15,"M5":{"signal":m5_signal,"raw_confluence":conf.get("signal"),"valid":valid}}, "alignment":aligned, "duplicate_alert_suppressed":already_alerted, "telegram_alert_sent":alerted, "telegram_result":telegram_result, "live_orders_allowed":False, "generated_at":datetime.now(timezone.utc).isoformat()}