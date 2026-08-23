"""Replay the live M5 signal logic using real LSE historical OHLCV.

Usage:
    python replay_signal_history.py --start 2026-08-01 --end 2026-08-23
    python replay_signal_history.py --start 2026-08-01 --end 2026-08-23 --symbol BTC

Statistics-only: no Telegram alert and no live order is sent.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

import engine_v5 as engine
import engine_v42 as base
from pattern_engine import detect_all, confluence
from signal_history import history
from live_scanner import _build_trade_levels, _levels_ready, _resolve_m5_direction

BANGKOK = ZoneInfo("Asia/Bangkok")
SYMBOLS = {"BTC": "BTC/USD", "GOLD": "XAU/USD"}
CATEGORIES = {"PRICE_ACTION", "CHART_PATTERN", "SMC_ICT", "SUPPLY_DEMAND", "TREND_BREAKOUT", "FIBONACCI_HARMONIC", "INDICATOR_SESSION"}


def _bounds(start_text, end_text):
    start = datetime.fromisoformat(start_text).replace(tzinfo=BANGKOK)
    end = datetime.fromisoformat(end_text).replace(tzinfo=BANGKOK) + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _normalize(result):
    if isinstance(result, pd.DataFrame):
        df = result.copy()
    elif isinstance(result, dict):
        df = pd.DataFrame(result.get("data") or result.get("rows") or [])
    else:
        df = pd.DataFrame(result or [])
    if df.empty:
        return df
    time_col = next((c for c in ("datetime", "timestamp", "ts") if c in df.columns), None)
    if not time_col:
        raise RuntimeError("LSE response has no timestamp field")
    df["datetime"] = pd.to_datetime(df[time_col], utc=True, errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return (df.dropna(subset=["datetime", "open", "high", "low", "close"])
              [["datetime", "open", "high", "low", "close", "volume"]]
              .sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True))


def _fetch_lse(symbol, start, end, timeframe="5m", chunk_days=6):
    """Fetch real LSE history with the lse-data 0.14 API.

    IMPORTANT: lse-data 0.14 requires candle start/end in YYYY-MM-DD form.
    Passing ISO timestamps causes HTTP 400 "invalid date" errors.  We also
    avoid the unsupported as_dataframe argument and normalize the returned
    object locally.
    """
    key = os.getenv("LSE_API_KEY", "").strip() or os.getenv("LSE_KEY", "").strip()
    if not key:
        raise RuntimeError("LSE_API_KEY/LSE_KEY is not configured")

    from lse import LSE
    client = LSE(api_key=key)
    parts = []
    cursor = start

    while cursor < end:
        chunk_end = min(cursor + timedelta(days=chunk_days), end)
        start_date = cursor.date().isoformat()
        end_date = chunk_end.date().isoformat()
        print(f"[{symbol}] LSE candles request: {start_date} -> {end_date} ({timeframe})", flush=True)

        # The provider API accepts calendar dates, not timestamps.
        result = client.candles(
            symbol,
            timeframe,
            start=start_date,
            end=end_date,
        )
        frame = _normalize(result)
        if not frame.empty:
            parts.append(frame)

        # Advance by the exact chunk boundary. Duplicate boundary candles are
        # removed after concatenation.
        cursor = chunk_end

    if not parts:
        raise RuntimeError(f"LSE returned no {timeframe} candles for {symbol}")

    return (pd.concat(parts, ignore_index=True)
              .sort_values("datetime")
              .drop_duplicates("datetime")
              .reset_index(drop=True))


def _configure(symbol):
    cfg = {
        "BTC": {"MINIMUM_ATR": 20.0, "MIN_STOP_ATR": 1.0, "MAX_STOP_ATR": 3.0, "SPREAD": 5.0, "SLIPPAGE": 2.0},
        "GOLD": {"MINIMUM_ATR": 1.0, "MIN_STOP_ATR": 1.0, "MAX_STOP_ATR": 3.0, "SPREAD": 0.50, "SLIPPAGE": 0.20},
    }[symbol]
    market = SYMBOLS[symbol]
    engine.SYMBOL = market
    base.SYMBOL = market
    for target in (engine, base):
        for key, value in cfg.items():
            setattr(target, key, value)
        target.MIN_RISK_REWARD = max(float(os.getenv("MIN_RISK_REWARD", "2.0")), 2.0)
        target.RISK_REWARD = max(float(os.getenv("RISK_REWARD", "2.0")), 2.0)
    return market


def _bias(frame, timeframe):
    c = pd.to_numeric(frame["close"], errors="coerce")
    e20 = c.ewm(span=20, adjust=False).mean()
    e50 = c.ewm(span=50, adjust=False).mean()
    i = len(frame) - 1
    close = float(c.iloc[i])
    a, b = float(e20.iloc[i]), float(e50.iloc[i])
    return {"timeframe": timeframe, "bias": "BUY" if close > a and a > b else "SELL" if close < a and a < b else "NEUTRAL", "close": close, "ema20": a, "ema50": b}


def _context_at(frame, ts, timeframe):
    pos = frame["datetime"].searchsorted(pd.Timestamp(ts), side="right") - 1
    if pos < 0:
        return {"timeframe": timeframe, "bias": "NEUTRAL", "close": None}
    return _bias(frame.iloc[:int(pos) + 1].copy(), timeframe)


def _resolve(row, future):
    entry, sl, tp = float(row["entry"]), float(row["sl"]), float(row["tp"])
    direction = row["direction"]
    entry_time = pd.Timestamp(row["candle_time"])
    risk = abs(entry - sl)
    rr = abs(tp - entry) / risk if risk else 0.0
    for _, candle in future.iterrows():
        if pd.Timestamp(candle["datetime"]) <= entry_time:
            continue
        high, low = float(candle["high"]), float(candle["low"])
        if direction == "BUY":
            hit_sl, hit_tp = low <= sl, high >= tp
        else:
            hit_sl, hit_tp = high >= sl, low <= tp
        when = str(candle["datetime"])
        if hit_sl and hit_tp:
            return "AMBIGUOUS", 0.0, when
        if hit_tp:
            return "WIN", rr, when
        if hit_sl:
            return "LOSS", -1.0, when
    return "OPEN", None, None


def replay_symbol(symbol, start, end, dry_run=False):
    market = _configure(symbol)
    warm_start = start - timedelta(days=7)
    print(f"[{symbol}] LSE history: {start.isoformat()} -> {end.isoformat()}", flush=True)

    m5 = _fetch_lse(market, warm_start, end, "5m", 6)
    if len(m5) < 200:
        raise RuntimeError(f"Not enough LSE M5 history for {symbol}: {len(m5)}")
    m5 = base.calculate_indicators(m5)
    m15 = (m5[["datetime", "open", "high", "low", "close", "volume"]].set_index("datetime")
           .resample("15min", label="left", closed="left").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
           .dropna(subset=["open","high","low","close"]).reset_index())
    h1 = (m5[["datetime", "open", "high", "low", "close", "volume"]].set_index("datetime")
          .resample("60min", label="left", closed="left").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"})
          .dropna(subset=["open","high","low","close"]).reset_index())

    generated = inserted = 0
    outcomes = {"WIN": 0, "LOSS": 0, "AMBIGUOUS": 0, "OPEN": 0}
    for i in range(100, len(m5) - 1):
        ts = pd.Timestamp(m5.iloc[i]["datetime"])
        if ts < pd.Timestamp(start) or ts >= pd.Timestamp(end):
            continue
        h1b = _context_at(h1, ts, "H1")
        m15b = _context_at(m15, ts, "M15")
        pattern_result = detect_all(m5, i)
        confirmed = [p for p in pattern_result["patterns"] if p.get("confirmed") is True and p.get("direction") in ("BUY", "SELL") and p.get("category") in CATEGORIES]
        buys = [p for p in confirmed if p.get("direction") == "BUY"]
        sells = [p for p in confirmed if p.get("direction") == "SELL"]
        conf = confluence(pattern_result["patterns"], minimum=1)
        signal = _resolve_m5_direction(conf, buys, sells)
        if signal not in ("BUY", "SELL"):
            continue
        selected = buys if signal == "BUY" else sells
        opposite = "SELL" if signal == "BUY" else "BUY"
        if h1b["bias"] == opposite or m15b["bias"] == opposite:
            continue
        levels = _build_trade_levels(m5, i, signal)
        if not _levels_ready(levels, signal):
            continue
        signal_id = f"REPLAY-{symbol}-{ts.strftime('%Y%m%dT%H%MZ')}-{signal}"
        payload = {
            "signal_id": signal_id,
            "symbol": symbol,
            "signal": signal,
            "closed_candle": ts.isoformat(),
            "created_at": ts.isoformat(),
            "replay": True,
            "replay_source": "LSE_HISTORICAL_OHLCV",
            "pattern_signal": signal,
            "m5_direction": signal,
            "m5_score": conf.get("score"),
            "m5_categories": conf.get("buy_categories", []) if signal == "BUY" else conf.get("sell_categories", []),
            "evidence": selected,
            "selected_evidence": selected,
            "confirmed_patterns": confirmed,
            "patterns": pattern_result["patterns"],
            "mtf": {"H1": h1b, "M15": m15b, "M5": signal},
            "h1_bias": h1b["bias"],
            "m15_bias": m15b["bias"],
            "previous_close": float(m5.iloc[i]["close"]),
            "trade_levels": levels,
        }
        generated += 1
        future = m5.iloc[i + 1:i + 1 + int(engine.FORWARD_BARS) + 1]
        result, r_multiple, resolved = _resolve({"direction": signal, "entry": levels["entry"], "sl": levels["sl"], "tp": levels["tp"], "candle_time": ts}, future)
        outcomes[result] += 1
        if not dry_run:
            if history.record_signal(payload):
                inserted += 1
            if result != "OPEN":
                history.set_result(signal_id, result, r_multiple, resolved)

    return {"symbol": symbol, "generated": generated, "inserted": inserted, "outcomes": outcomes}


def main():
    parser = argparse.ArgumentParser(description="Replay real LSE historical M5 signals")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--symbol", choices=["BTC", "GOLD", "ALL"], default="ALL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    start, end = _bounds(args.start, args.end)
    symbols = ["BTC", "GOLD"] if args.symbol == "ALL" else [args.symbol]
    results = [replay_symbol(symbol, start, end, args.dry_run) for symbol in symbols]
    print(json.dumps({"status": "dry-run" if args.dry_run else "completed", "provider": "LSE", "start": args.start, "end": args.end, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
