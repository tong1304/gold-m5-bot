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


def fetch_candles(symbol: str, interval: str, outputsize: int) -> pd.DataFrame:
    return BINANCE.fetch_candles(symbol, interval, outputsize)


def closed(df, minutes):
    return BinanceMarketData.remove_incomplete_last_candle(df, timeframe_minutes=minutes)


def _trend_context(df, timeframe):
    df = base.calculate_indicators(df.copy())
    if len(df) < 55:
        return {"timeframe": timeframe, "bias": "NEUTRAL", "structure": "INSUFFICIENT_DATA", "close": None}
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
        half = len(recent) // 2
        first_high = float(recent.high.iloc[:half].max())
        last_high = float(recent.high.iloc[half:].max())
        first_low = float(recent.low.iloc[:half].min())
        last_low = float(recent.low.iloc[half:].min())
        structure = "HH_HL" if last_high > first_high and last_low > first_low else "LH_LL" if last_high < first_high and last_low < first_low else "MIXED"
    else:
        structure = "MIXED"
    return {"timeframe": timeframe, "bias": bias, "structure": structure, "close": close}


def _context_for_timestamp(context_df, ts, timeframe):
    available = context_df[context_df["datetime"] <= ts]
    return _trend_context(available, timeframe)


def run(symbol: str, bars: int) -> dict:
    """Run a bounded paper backtest using only closed candles and no live orders."""
    stage = "start"
    try:
        stage = "fetch_m5"
        m5 = closed(fetch_candles(symbol, "5m", bars), 5)
        stage = "fetch_m15"
        m15 = closed(fetch_candles(symbol, "15m", max(200, min(1000, bars // 3 + 100))), 15)
        stage = "fetch_h1"
        h1 = closed(fetch_candles(symbol, "1h", max(200, min(1000, bars // 12 + 100))), 60)
        if min(len(m5), len(m15), len(h1)) < 100:
            raise RuntimeError(f"ข้อมูลแท่งที่ปิดแล้วไม่เพียงพอ: M5={len(m5)}, M15={len(m15)}, H1={len(h1)}")

        stage = "prepare_indicators"
        m5 = base.calculate_indicators(m5)
        m15_prepared = base.calculate_indicators(m15)
        h1_prepared = base.calculate_indicators(h1)

        diagnostics = Counter()
        pattern_counts = Counter()
        rejection_reasons = Counter()
        trades = []
        start = max(80, len(m5) - bars + 1)
        end = len(m5) - int(engine.FORWARD_BARS) - 2
        if end <= start:
            raise RuntimeError(f"ช่วง Backtest ไม่เพียงพอ: start={start}, end={end}, M5={len(m5)}")

        for i in range(start, end):
            diagnostics["candidate_candles"] += 1
            ts = pd.Timestamp(m5.iloc[i]["datetime"])
            try:
                m15_ctx = _context_for_timestamp(m15_prepared, ts, "M15")
                h1_ctx = _context_for_timestamp(h1_prepared, ts, "H1")
                if m15_ctx["bias"] == "NEUTRAL" or h1_ctx["bias"] == "NEUTRAL":
                    rejection_reasons["mtf_neutral"] += 1
                    continue

                patterns = detect_all(m5, i)
                conf = confluence(patterns["patterns"], minimum=3)
                direction = conf["signal"]
                confirmed_patterns = [
                    p for p in patterns["patterns"]
                    if p.get("confirmed") is True or p.get("category") != "CHART_PATTERN"
                ]
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
                # Reuse the V5 execution simulator. This is paper-only and never places an order.
                raw = base.analyze_candle(m5, i)
                if not isinstance(raw, dict):
                    diagnostics["engine_gate_rejected"] += 1
                    rejection_reasons["engine_result_invalid"] += 1
                    continue
                levels = raw.get("trade_levels") or {}
                trade = engine.simulate_trade(m5, i, direction, levels)
                if not trade:
                    diagnostics["execution_rejected"] += 1
                    rejection_reasons["invalid_trade_levels_or_rr"] += 1
                    continue
                trade["score"] = conf["score"]
                trade["engine_score"] = raw.get("score")
                trade["pattern"] = [p.get("name") for p in confirmed_patterns]
                trade["m15_bias"] = m15_ctx["bias"]
                trade["m15_structure"] = m15_ctx["structure"]
                trade["h1_bias"] = h1_ctx["bias"]
                trade["h1_structure"] = h1_ctx["structure"]
                trade["closed_candle"] = str(ts)
                trade["previous_close"] = float(m5.iloc[i]["close"])
                trades.append(trade)
                diagnostics["trades_accepted"] += 1
            except Exception as exc:
                diagnostics["candidate_exceptions"] += 1
                rejection_reasons[f"exception:{type(exc).__name__}"] += 1

        stats = engine.calculate_trade_statistics(trades)
        probability = engine.empirical_probability(trades)
        by_side = {}
        for side in ("BUY", "SELL"):
            subset = [t for t in trades if t.get("direction") == side]
            by_side[side] = {
                "statistics": engine.calculate_trade_statistics(subset),
                "probability": engine.empirical_probability(subset, side),
            }
        windows = engine.build_walk_forward_windows(len(m5), 400, 200, 200)
        return {
            "status": "PAPER_VALIDATION_ONLY",
            "engine_version": engine.ENGINE_VERSION,
            "strategy": "M5 confirmed pattern + M15 trend + H1 trend alignment",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "timeframe": "M5 trigger / M15+H1 confirmation",
            "exchange": "Binance with configured public-data fallback",
            "market_type": "spot",
            "data_provider": getattr(BINANCE, "last_provider", "unknown"),
            "candles": {"M5": len(m5), "M15": len(m15), "H1": len(h1)},
            "data_start": str(m5.iloc[0]["datetime"]),
            "data_end": str(m5.iloc[-1]["datetime"]),
            "walk_forward_windows_available": len(windows),
            "assumptions": {
                "intrabar_policy": engine.INTRABAR_AMBIGUITY_POLICY,
                "orders_placed": False,
                "slippage": engine.SLIPPAGE,
                "spread": engine.SPREAD,
                "timeout_in_expectancy": True,
            },
            "diagnostics": {
                **dict(diagnostics),
                "rejection_reasons": dict(rejection_reasons.most_common()),
                "pattern_counts": dict(pattern_counts.most_common()),
            },
            "statistics": stats,
            "resolved_probability": probability,
            "by_side": by_side,
            "trades": trades,
            "live_orders_allowed": False,
            "warning": "Paper validation only. Multi-timeframe alignment does not guarantee profitability; validate on broker/exchange-specific data and execution conditions.",
        }
    except Exception as exc:
        # The API layer already serializes this response. Keeping the stage here makes
        # Render failures actionable instead of returning a generic 500.
        return {
            "status": "VALIDATION_FAILED",
            "engine_version": getattr(engine, "ENGINE_VERSION", "5.0"),
            "symbol": symbol,
            "bars": bars,
            "stage": stage,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "data_provider": getattr(BINANCE, "last_provider", "unknown"),
            "live_orders_allowed": False,
            "trades": [],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--bars", type=int, default=1000)
    args = parser.parse_args()
    print(json.dumps(run(args.symbol, args.bars), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
