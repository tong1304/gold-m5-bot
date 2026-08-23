"""One-shot historical signal replay for the Statistics page.

This file is intentionally separate from the live trading path. It does not
change scheduler/live-price/scanner behaviour and never sends Telegram alerts.
It replays the existing M5 decision logic over real LSE historical candles,
then resolves each generated setup against subsequent real M5 OHLC candles.

Usage on Render (with LSE_API_KEY already configured):
    python replay_signal_history.py --start 2026-08-01 --end 2026-08-23

The importer writes only REPLAY-* rows into signal_history.db and is safe to
run repeatedly because signal_id is deterministic and INSERT OR IGNORE is used.
"""

import argparse
import json
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

import engine_v5 as engine
import engine_v42 as base
from binance_data import BinanceMarketData
from pattern_engine import detect_all, confluence
from signal_history import history
from live_scanner import _build_trade_levels, _levels_ready, _resolve_m5_direction

BANGKOK = ZoneInfo("Asia/Bangkok")
SYMBOLS = {"BTC": "BTC/USDT", "GOLD": "XAU/USDT"}
START_DEFAULT = "2026-08-01"
END_DEFAULT = "2026-08-23"


def parse_args():
    p = argparse.ArgumentParser(description="Replay real LSE historical candles into signal statistics")
    p.add_argument("--start", default=START_DEFAULT, help="UTC/Bangkok date, inclusive, YYYY-MM-DD")
    p.add_argument("--end", default=END_DEFAULT, help="UTC/Bangkok date, inclusive, YYYY-MM-DD")
    p.add_argument("--symbol", choices=["BTC", "GOLD", "ALL"], default="ALL")
    p.add_argument("--limit", type=int, default=5000)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def dt_utc(value):
    text = str(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def range_bounds(start_text, end_text):
    # User-facing dates are Asia/Bangkok; convert boundaries to UTC so the
    # historical window matches the same timezone used by the live scheduler.
    start_local = datetime.fromisoformat(start_text).replace(tzinfo=BANGKOK)
    end_local = datetime.fromisoformat(end_text).replace(tzinfo=BANGKOK) + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def fetch_history(provider, symbol, start, end, limit):
    """Use the official LSE Python client when available so ranges >5000 rows page automatically."""
    lse_client = None
    try:
        from lse import LSE
        key = os.getenv("LSE_API_KEY", "").strip() or os.getenv("LSE_KEY", "").strip()
        if key:
            lse_client = LSE(api_key=key)
    except Exception:
        lse_client = None

    if lse_client is not None:
        # The official client accepts a start/end window and handles the
        # provider's 5,000-row pagination internally.
        frame = lse_client.candles(
            provider.market_symbol(symbol),
            "5m",
            start=start.isoformat(),
            end=end.isoformat(),
        )
        if not isinstance(frame, pd.DataFrame):
            frame = pd.DataFrame(frame)
        frame = frame.rename(columns={"ts": "datetime"}) if "ts" in frame.columns else frame.copy()
        frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True, errors="coerce")
        return frame.sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)

    # Fallback to the existing LSE REST adapter. This branch is only useful
    # for shorter windows that fit inside its 5,000-candle request.
    frame = provider.fetch_candles(symbol, "5m", min(limit, 5000))
    frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True, errors="coerce")
    return frame[(frame["datetime"] >= pd.Timestamp(start)) & (frame["datetime"] < pd.Timestamp(end))].reset_index(drop=True)


def configure(symbol):
    cfg = {
        "BTC": {"MINIMUM_ATR": 20.0, "MIN_STOP_ATR": 1.0, "MAX_STOP_ATR": 3.0, "SPREAD": 5.0, "SLIPPAGE": 2.0},
        "GOLD": {"MINIMUM_ATR": 1.0, "MIN_STOP_ATR": 1.0, "MAX_STOP_ATR": 3.0, "SPREAD": 0.50, "SLIPPAGE": 0.20},
    }[symbol]
    market_symbol = SYMBOLS[symbol]
    engine.SYMBOL = market_symbol
    base.SYMBOL = market_symbol
    for target in (engine, base):
        for key, value in cfg.items():
            setattr(target, key, value)
        target.MIN_RISK_REWARD = max(float(os.getenv("MIN_RISK_REWARD", "2.0")), 2.0)
        target.RISK_REWARD = max(float(os.getenv("RISK_REWARD", "2.0")), 2.0)
    return market_symbol


def resample_closed(frame, minutes):
    work = frame.copy().set_index("datetime")
    out = work.resample(f"{minutes}min", label="left", closed="left").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
    }).dropna(subset=["open", "high", "low", "close"]).reset_index()
    return out


def pattern_payload(pattern_result, selected, h1, m15, signal, conf):
    return {
        "source": "LSE_HISTORICAL_REPLAY",
        "replay": True,
        "replay_version": "1.0",
        "evidence": selected,
        "m5_categories": conf.get("buy_categories", []) if signal == "BUY" else conf.get("sell_categories", []),
        "m5_score": conf.get("score"),
        "pattern_signal": signal,
        "m5_direction": signal,
        "mtf": {"H1": h1, "M15": m15},
        "pattern_count_total": pattern_result.get("pattern_count"),
        "confirmed_patterns": pattern_result.get("patterns", []),
    }


def resolve_against_future(row, future):
    entry, sl, tp = float(row["entry"]), float(row["sl"]), float(row["tp"])
    direction = row["direction"]
    entry_time = dt_utc(row["candle_time"])
    risk = abs(entry - sl)
    rr = abs(tp - entry) / risk if risk else 0.0
    # Same conservative rule as the existing history evaluator: if both SL
    # and TP occur inside one OHLC bar, mark AMBIGUOUS rather than guessing.
    for _, c in future.iterrows():
        if dt_utc(c["datetime"]) <= entry_time:
            continue
        high, low = float(c["high"]), float(c["low"])
        if direction == "BUY":
            hit_sl, hit_tp = low <= sl, high >= tp
        else:
            hit_sl, hit_tp = high >= sl, low <= tp
        when = str(c["datetime"])
        if hit_sl and hit_tp:
            return "AMBIGUOUS", 0.0, when
        if hit_tp:
            return "WIN", rr, when
        if hit_sl:
            return "LOSS", -1.0, when
    return "OPEN", None, None


def replay_symbol(provider, symbol, start, end, dry_run=False, limit=5000):
    market_symbol = configure(symbol)
    m5 = fetch_history(provider, market_symbol, start, end, limit)
    if m5.empty:
        raise RuntimeError(f"No LSE M5 history for {symbol} in requested window")
    m5["datetime"] = pd.to_datetime(m5["datetime"], utc=True)
    m5 = m5.sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)

    # Add warm-up data before the requested window so EMA/RSI/ATR/patterns are
    # calculated exactly as they are in the live engine instead of starting cold.
    warm_start = m5["datetime"].min() - timedelta(days=3)
    warm = fetch_history(provider, market_symbol, warm_start, end, limit)
    warm["datetime"] = pd.to_datetime(warm["datetime"], utc=True)
    warm = warm.sort_values("datetime").drop_duplicates("datetime").reset_index(drop=True)
    if len(warm) > len(m5):
        m5 = warm

    h1 = resample_closed(m5, 60)
    m15 = resample_closed(m5, 15)
    m5i = base.calculate_indicators(m5.copy())

    start_ts, end_ts = start, end
    generated = 0
    inserted = 0
    outcomes = {"WIN": 0, "LOSS": 0, "AMBIGUOUS": 0, "OPEN": 0}
    occupied_until = None

    for i in range(100, len(m5i) - 1):
        candle_time = dt_utc(m5i.iloc[i]["datetime"])
        if candle_time < start_ts or candle_time >= end_ts:
            continue

        # Match the live engine's MTF calculation on data available at the
        # signal candle only; no future candles are used for the decision.
        h1_closed = h1[h1["datetime"] <= pd.Timestamp(candle_time)].copy()
        m15_closed = m15[m15["datetime"] <= pd.Timestamp(candle_time)].copy()
        if len(h1_closed) < 50 or len(m15_closed) < 50:
            continue

        def tf_bias(frame):
            ind = base.calculate_indicators(frame.copy())
            j = len(ind) - 1
            close = float(ind.close.iloc[j])
            ema20 = float(ind.close.ewm(span=20, adjust=False).mean().iloc[j])
            ema50 = float(ind.close.ewm(span=50, adjust=False).mean().iloc[j])
            bias = "BUY" if close > ema20 and ema20 > ema50 else "SELL" if close < ema20 and ema20 < ema50 else "NEUTRAL"
            return {"timeframe": "H1" if frame is h1_closed else "M15", "bias": bias, "close": close, "ema20": ema20, "ema50": ema50}

        h1b, m15b = tf_bias(h1_closed), tf_bias(m15_closed)
        pattern_result = detect_all(m5i, i)
        confirmed = [p for p in pattern_result["patterns"] if p.get("confirmed") is True and p.get("direction") in ("BUY", "SELL") and p.get("category") in {"PRICE_ACTION", "CHART_PATTERN", "SMC_ICT", "SUPPLY_DEMAND", "TREND_BREAKOUT", "FIBONACCI_HARMONIC", "INDICATOR_SESSION"}]
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

        levels = _build_trade_levels(m5i, i, signal)
        if not _levels_ready(levels, signal):
            continue
        # Live scanner only creates an alert once per candle. Replay applies
        # the same non-overlap policy to avoid counting the same setup twice.
        if occupied_until is not None and candle_time <= occupied_until and not engine.ALLOW_OVERLAPPING_TRADES:
            continue

        payload = pattern_payload(pattern_result, selected, h1b, m15b, signal, conf)
        signal_id = f"REPLAY-{symbol}-{candle_time.strftime('%Y%m%dT%H%M%SZ')}-{signal}"
        signal_obj = {
            "signal_id": signal_id,
            "symbol": symbol,
            "signal": signal,
            "closed_candle": candle_time.isoformat(),
            "trade_levels": levels,
            "evidence": selected,
            "pattern_signal": signal,
            "m5_direction": signal,
            "m5_score": conf.get("score"),
            "m5_categories": payload["m5_categories"],
            "mtf": {"H1": h1b, "M15": m15b},
            "replay": True,
            "replay_source": "LSE_HISTORICAL_OHLCV",
        }
        generated += 1
        future = m5i.iloc[i + 1: min(len(m5i), i + 1 + int(engine.FORWARD_BARS) + 1)]
        if future.empty:
            result, r, resolved = "OPEN", None, None
        else:
            temp = {"direction": signal, "entry": levels["entry"], "sl": levels["sl"], "tp": levels["tp"], "candle_time": candle_time.isoformat()}
            result, r, resolved = resolve_against_future(temp, future)
        outcomes[result] = outcomes.get(result, 0) + 1

        if not dry_run:
            # record_signal stores the full exact pattern evidence in payload_json.
            if history.record_signal(signal_obj):
                inserted += 1
            row = history.get(signal_id)
            if row and result != "OPEN":
                history.set_result(signal_id, result, r, resolved)
        if result != "OPEN" and resolved:
            occupied_until = dt_utc(resolved)

    return {"symbol": symbol, "generated": generated, "inserted": inserted, "outcomes": outcomes}


def main():
    args = parse_args()
    start, end = range_bounds(args.start, args.end)
    provider = BinanceMarketData()
    symbols = ["BTC", "GOLD"] if args.symbol == "ALL" else [args.symbol]
    results = []
    for symbol in symbols:
        print(f"[REPLAY] {symbol}: {start.isoformat()} -> {end.isoformat()}", flush=True)
        result = replay_symbol(provider, symbol, start, end, args.dry_run, args.limit)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    print(json.dumps({"status": "dry_run" if args.dry_run else "completed", "source": "LSE_HISTORICAL_OHLCV", "results": results}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
