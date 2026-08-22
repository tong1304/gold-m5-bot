"""V5 paper validation: M5 pattern trigger + M15/H1 trend confirmation.

No orders are placed. The validator mirrors the live multi-timeframe decision:
M5 must produce a confirmed directional setup, while M15 and H1 must agree.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone

import pandas as pd

import engine_v5 as engine
import engine_v42 as base
from binance_data import BinanceMarketData
from pattern_engine import detect_all, confluence

BINANCE = BinanceMarketData()
TF_MINUTES = {"1h": 60, "15m": 15, "5m": 5}


def fetch_candles(symbol: str, interval: str, outputsize: int) -> pd.DataFrame:
    return BINANCE.fetch_candles(symbol, interval, outputsize)


def closed(df, minutes):
    return BINANCE.remove_incomplete_last_candle(df, timeframe_minutes=minutes)


def _trend_context(df, timeframe):
    df = base.calculate_indicators(df.copy())
    if len(df) < 55:
        return {"timeframe": timeframe, "bias": "NEUTRAL", "structure": "INSUFFICIENT_DATA"}
    c = df.close
    e20 = c.ewm(span=20, adjust=False).mean()
    e50 = c.ewm(span=50, adjust=False).mean()
    i = len(df) - 1
    recent = df.iloc[max(0, i - 20):i]
    close = float(c.iloc[i])
    if close > float(e20.iloc[i]) > float(e50.iloc[i]):
        bias = "BUY"
    elif close < float(e20.iloc[i]) < float(e50.iloc[i]):
        bias = "SELL"
    else:
        bias = "NEUTRAL"
    if len(recent) >= 6:
        first_high = float(recent.high.iloc[:len(recent)//2].max())
        last_high = float(recent.high.iloc[len(recent)//2:].max())
        first_low = float(recent.low.iloc[:len(recent)//2].min())
        last_low = float(recent.low.iloc[len(recent)//2:].min())
        structure = "HH_HL" if last_high > first_high and last_low > first_low else "LH_LL" if last_high < first_high and last_low < first_low else "MIXED"
    else:
        structure = "MIXED"
    return {"timeframe": timeframe, "bias": bias, "structure": structure, "close": close}


def _simulate_direction(df, i, direction, levels):
    trade = engine.simulate_trade(df, i, direction, levels)
    return trade


def run(symbol: str, bars: int) -> dict:
    # Fetch enough history so each M5 candidate has contemporaneous M15/H1 context.
    m5 = closed(fetch_candles(symbol, "5m", bars), 5)
    m15 = closed(fetch_candles(symbol, "15m", max(200, bars // 3 + 100)), 15)
    h1 = closed(fetch_candles(symbol, "1h", max(200, bars // 12 + 100)), 60)
    if min(len(m5), len(m15), len(h1)) < 100:
        raise RuntimeError(f"Insufficient closed candles: M5={len(m5)}, M15={len(m15)}, H1={len(h1)}")
    m5 = base.calculate_indicators(m5)
    diagnostics = Counter()
    pattern_counts = Counter()
    rejection_reasons = Counter()
    score_buckets = Counter()
    trades = []
    start = max(80, len(m5) - bars + 1)
    end = len(m5) - int(engine.FORWARD_BARS) - 2
    for i in range(start, end):
        diagnostics["candidate_candles"] += 1
        # Only use information available at/ before the M5 candle close.
        ts = pd.Timestamp(m5.iloc[i]["datetime"])
        m15_slice = m15[m15["datetime"] <= ts]
        h1_slice = h1[h1["datetime"] <= ts]
        if len(m15_slice) < 55 or len(h1_slice) < 55:
            rejection_reasons["insufficient_mtf_history"] += 1
            continue
        m15_ctx = _trend_context(m15_slice, "M15")
        h1_ctx = _trend_context(h1_slice, "H1")
        patterns = detect_all(m5, i)
        conf = confluence(patterns["patterns"], minimum=3)
        direction = conf["signal"]
        confirmed_patterns = [p for p in patterns["patterns"] if p.get("confirmed") is True or p.get("category") != "CHART_PATTERN"]
        if direction not in ("BUY", "SELL"):
            diagnostics["m5_no_trade"] += 1
            rejection_reasons["m5_pattern_no_direction"] += 1
            continue
        if not confirmed_patterns:
            diagnostics["m5_unconfirmed_pattern"] += 1
            rejection_reasons["m5_unconfirmed_pattern"] += 1
            continue
        diagnostics["m5_directional_setups"] += 1
        pattern_counts[direction] += 1
        for p in confirmed_patterns:
            pattern_counts[p.get("name", "UNKNOWN")] += 1
        if m15_ctx["bias"] != direction:
            diagnostics["rejected_m15"] += 1
            rejection_reasons[f"M15_{m15_ctx['bias']}"] += 1
            continue
        if h1_ctx["bias"] != direction:
            diagnostics["rejected_h1"] += 1
            rejection_reasons[f"H1_{h1_ctx['bias']}"] += 1
            continue
        diagnostics["mtf_aligned"] += 1
        try:
            raw = base.analyze_candle(m5, i)
            if not isinstance(raw, dict) or raw.get("valid") is False:
                diagnostics["engine_gate_rejected"] += 1
                rejection_reasons["engine_gate_rejected"] += 1
                continue
            levels = raw.get("trade_levels") or {}
            trade = _simulate_direction(m5, i, direction, levels)
            if not trade:
                diagnostics["execution_rejected"] += 1
                rejection_reasons["execution_rejected"] += 1
                continue
            trade["score"] = conf["score"]
            trade["engine_score"] = raw.get("score")
            trade["pattern"] = [p.get("name") for p in confirmed_patterns]
            trade["m15_bias"] = m15_ctx["bias"]
            trade["h1_bias"] = h1_ctx["bias"]
            trade["closed_candle"] = str(ts)
            trade["previous_close"] = float(m5.iloc[i]["close"])
            trades.append(trade)
            diagnostics["trades_accepted"] += 1
        except Exception as exc:
            diagnostics["engine_exceptions"] += 1
            rejection_reasons[f"exception:{type(exc).__name__}"] += 1
    stats = engine.calculate_trade_statistics(trades)
    probability = engine.empirical_probability(trades)
    by_side = {}
    for side in ("BUY", "SELL"):
        subset = [t for t in trades if t.get("direction") == side]
        by_side[side] = {"statistics": engine.calculate_trade_statistics(subset), "probability": engine.empirical_probability(subset, side)}
    windows = engine.build_walk_forward_windows(len(m5), 400, 200, 200)
    return {
        "status": "PAPER_VALIDATION_ONLY",
        "engine_version": engine.ENGINE_VERSION,
        "strategy": "M5 confirmed pattern + M15 trend + H1 trend alignment",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol, "timeframe": "M5 trigger / M15+H1 confirmation", "exchange": "Binance", "market_type": "spot",
        "candles": {"M5": len(m5), "M15": len(m15), "H1": len(h1)},
        "data_start": m5.iloc[0]["datetime"].isoformat(), "data_end": m5.iloc[-1]["datetime"].isoformat(),
        "walk_forward_windows_available": len(windows),
        "assumptions": {"intrabar_policy": engine.INTRABAR_AMBIGUITY_POLICY, "orders_placed": False, "slippage": engine.SLIPPAGE, "spread": engine.SPREAD, "timeout_in_expectancy": True},
        "diagnostics": {**dict(diagnostics), "rejection_reasons": dict(rejection_reasons.most_common()), "pattern_counts": dict(pattern_counts.most_common()), "score_buckets": dict(score_buckets)},
        "statistics": stats, "resolved_probability": probability, "by_side": by_side, "trades": trades,
        "live_orders_allowed": False,
        "warning": "Paper validation only. Multi-timeframe alignment does not guarantee profitability; validate on broker/exchange-specific data and execution conditions."
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--bars", type=int, default=1000)
    args = parser.parse_args()
    print(json.dumps(run(args.symbol, args.bars), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
