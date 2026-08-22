"""V5 paper validation: M5 pattern trigger + M15/H1 trend confirmation.

Optimized for Render: M15/H1 trend context is precomputed once, rather than
recalculating indicators for every M5 candle. No live orders are placed.
"""
import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone

import pandas as pd

import engine_v5 as engine
import engine_v42 as base
from binance_data import BinanceMarketData
from pattern_engine import detect_all, confluence

BINANCE = BinanceMarketData()
MIN_CONTEXT_BARS = 60


def fetch_candles(symbol: str, interval: str, outputsize: int) -> pd.DataFrame:
    return BINANCE.fetch_candles(symbol, interval, outputsize)


def closed(df, minutes):
    return BinanceMarketData.remove_incomplete_last_candle(df, timeframe_minutes=minutes)


def _prepare_trend_table(df, timeframe):
    """Precompute the MTF bias/structure once for every closed candle."""
    out = df.copy()
    c = pd.to_numeric(out["close"], errors="coerce")
    out["ema20_v5"] = c.ewm(span=20, adjust=False).mean()
    out["ema50_v5"] = c.ewm(span=50, adjust=False).mean()
    out["bias_v5"] = "NEUTRAL"
    out.loc[(c > out["ema20_v5"]) & (out["ema20_v5"] > out["ema50_v5"]), "bias_v5"] = "BUY"
    out.loc[(c < out["ema20_v5"]) & (out["ema20_v5"] < out["ema50_v5"]), "bias_v5"] = "SELL"
    highs = out["high"].rolling(10, min_periods=10)
    lows = out["low"].rolling(10, min_periods=10)
    prev_high = out["high"].shift(10).rolling(10, min_periods=10).max()
    prev_low = out["low"].shift(10).rolling(10, min_periods=10).min()
    hhhl = (highs.max() > prev_high) & (lows.min() > prev_low)
    llll = (highs.max() < prev_high) & (lows.min() < prev_low)
    out["structure_v5"] = "MIXED"
    out.loc[hhhl, "structure_v5"] = "HH_HL"
    out.loc[llll, "structure_v5"] = "LH_LL"
    out.attrs["timeframe"] = timeframe
    return out


def _context_for_timestamp(context_df, ts, timeframe):
    if context_df.empty:
        return {"timeframe": timeframe, "bias": "NEUTRAL", "structure": "INSUFFICIENT_DATA", "close": None}
    pos = context_df["datetime"].searchsorted(ts, side="right") - 1
    if pos < 0:
        return {"timeframe": timeframe, "bias": "NEUTRAL", "structure": "INSUFFICIENT_DATA", "close": None}
    row = context_df.iloc[int(pos)]
    return {"timeframe": timeframe, "bias": str(row["bias_v5"]), "structure": str(row["structure_v5"]), "close": float(row["close"])}


def run(symbol: str, bars: int) -> dict:
    started = time.monotonic()
    stage = "start"
    try:
        bars = max(10, int(bars))
        stage = "fetch_m5"
        m5 = closed(fetch_candles(symbol, "5m", bars), 5)
        stage = "fetch_m15"
        # Need enough history for EMA50, but do not force 200 bars for short smoke tests.
        m15_requested = max(MIN_CONTEXT_BARS + 10, min(1000, bars // 3 + 60))
        m15 = closed(fetch_candles(symbol, "15m", m15_requested), 15)
        stage = "fetch_h1"
        h1_requested = max(MIN_CONTEXT_BARS + 10, min(1000, bars // 12 + 60))
        h1 = closed(fetch_candles(symbol, "1h", h1_requested), 60)
        if len(m5) < 10 or len(m15) < MIN_CONTEXT_BARS or len(h1) < MIN_CONTEXT_BARS:
            raise RuntimeError(f"ข้อมูลแท่งที่ปิดแล้วไม่เพียงพอ: M5={len(m5)}, M15={len(m15)}, H1={len(h1)}; ต้องการอย่างน้อย M5=10, M15/H1={MIN_CONTEXT_BARS}")

        stage = "prepare_indicators"
        m5 = base.calculate_indicators(m5)
        m15_ctx_table = _prepare_trend_table(m15, "M15")
        h1_ctx_table = _prepare_trend_table(h1, "H1")

        diagnostics = Counter()
        pattern_counts = Counter()
        rejection_reasons = Counter()
        trades = []
        start = max(80, len(m5) - bars + 1)
        end = len(m5) - int(engine.FORWARD_BARS) - 2
        if end <= start:
            raise RuntimeError(f"ช่วง Backtest ไม่เพียงพอ: start={start}, end={end}, M5={len(m5)}; เพิ่ม bars อย่างน้อย 300-500 สำหรับผลที่มีนัยสำคัญ")

        stage = "backtest_loop"
        for i in range(start, end):
            diagnostics["candidate_candles"] += 1
            ts = pd.Timestamp(m5.iloc[i]["datetime"])
            try:
                m15_ctx = _context_for_timestamp(m15_ctx_table, ts, "M15")
                h1_ctx = _context_for_timestamp(h1_ctx_table, ts, "H1")
                if m15_ctx["bias"] == "NEUTRAL" or h1_ctx["bias"] == "NEUTRAL":
                    rejection_reasons["mtf_neutral"] += 1
                    continue

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
            by_side[side] = {"statistics": engine.calculate_trade_statistics(subset), "probability": engine.empirical_probability(subset, side)}
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
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "assumptions": {"intrabar_policy": engine.INTRABAR_AMBIGUITY_POLICY, "orders_placed": False, "slippage": engine.SLIPPAGE, "spread": engine.SPREAD, "timeout_in_expectancy": True},
            "diagnostics": {**dict(diagnostics), "rejection_reasons": dict(rejection_reasons.most_common()), "pattern_counts": dict(pattern_counts.most_common())},
            "statistics": stats,
            "resolved_probability": probability,
            "by_side": by_side,
            "trades": trades,
            "live_orders_allowed": False,
            "warning": "Paper validation only. Multi-timeframe alignment does not guarantee profitability; validate on broker/exchange-specific data and execution conditions.",
        }
    except Exception as exc:
        return {
            "status": "VALIDATION_FAILED",
            "engine_version": getattr(engine, "ENGINE_VERSION", "5.0"),
            "symbol": symbol,
            "bars": bars,
            "stage": stage,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "data_provider": getattr(BINANCE, "last_provider", "unknown"),
            "elapsed_seconds": round(time.monotonic() - started, 3),
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
