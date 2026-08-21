"""Standalone v5 validation runner.

Fetches M5 candles from Twelve Data and evaluates the conservative v5
execution layer. Research/paper-validation only; never places orders.
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

import pandas as pd
import requests

import engine_v5 as engine
import engine_v42 as base


def fetch_candles(symbol: str, interval: str, outputsize: int) -> pd.DataFrame:
    api_key = os.getenv("TWELVE_DATA_API_KEY") or getattr(base, "TWELVE_DATA_API_KEY", "")
    if not api_key:
        raise RuntimeError("TWELVE_DATA_API_KEY is not configured")
    response = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": symbol,
            "interval": interval,
            "outputsize": min(int(outputsize), 5000),
            "apikey": api_key,
            "format": "JSON",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") == "error" or "values" not in payload:
        raise RuntimeError(payload.get("message", "Twelve Data returned no values"))
    df = pd.DataFrame(payload["values"])
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    for column in ("open", "high", "low", "close"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return (
        df.dropna(subset=["datetime", "open", "high", "low", "close"])
        .sort_values("datetime")
        .reset_index(drop=True)
    )


def _normalize_signal(signal):
    if not isinstance(signal, dict):
        return None
    direction = str(signal.get("signal") or signal.get("direction") or "").upper().strip()
    if direction not in ("BUY", "SELL") or signal.get("valid") is False:
        return None
    levels = signal.get("trade_levels") or signal.get("levels") or {}
    return {
        "direction": direction,
        "levels": levels if isinstance(levels, dict) else {},
        "score": signal.get("score"),
        "pattern": signal.get("patterns") or signal.get("pattern"),
        "regime": signal.get("market_regime") or signal.get("regime"),
    }


def _record_rejection(raw_signal, counters, score_buckets, pattern_direction_counts):
    """Best-effort diagnostics only; never allow diagnostics to break validation."""
    try:
        if not isinstance(raw_signal, dict):
            counters["invalid_result"] += 1
            return

        status = str(raw_signal.get("status") or "").strip().upper()
        signal_name = str(raw_signal.get("signal") or "").strip().upper()
        hard_filter = raw_signal.get("hard_filter")
        if not isinstance(hard_filter, dict):
            hard_filter = {}
        failed = hard_filter.get("failed") or []
        if not isinstance(failed, (list, tuple, set)):
            failed = [failed]

        if status:
            counters[f"status:{status}"] += 1
        elif signal_name == "NO_TRADE":
            counters["status:NO_TRADE"] += 1
        else:
            counters["status:UNKNOWN"] += 1

        if failed:
            for reason in failed:
                counters[str(reason)] += 1
        else:
            counters["no_failed_gate_reported"] += 1

        score = raw_signal.get("score")
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = None
        if score is not None:
            if score < 50:
                bucket = "<50"
            elif score < 60:
                bucket = "50-59"
            elif score < 70:
                bucket = "60-69"
            elif score < 75:
                bucket = "70-74"
            elif score < 80:
                bucket = "75-79"
            elif score < 90:
                bucket = "80-89"
            else:
                bucket = "90+"
            score_buckets[bucket] += 1

        # Do not call a non-production helper here. Production analyze_candle
        # already exposes the pattern information; keep diagnostics side-effect free.
        patterns = raw_signal.get("patterns") or raw_signal.get("pattern")
        if isinstance(patterns, str):
            patterns = [patterns]
        if patterns:
            for pattern in patterns if isinstance(patterns, (list, tuple, set)) else [patterns]:
                pattern_direction_counts[str(pattern)] += 1
    except Exception:
        counters["diagnostics_internal_error"] += 1


def run(symbol: str, bars: int) -> dict:
    df = fetch_candles(symbol, "5min", bars)
    if len(df) < 100:
        raise RuntimeError(f"Only {len(df)} valid candles returned")

    diagnostics = {
        "candidate_candles": 0,
        "engine_calls": 0,
        "engine_exceptions": 0,
        "engine_exception_samples": [],
        "signals_seen": 0,
        "invalid_signals": 0,
        "buy_signals": 0,
        "sell_signals": 0,
        "trades_accepted": 0,
        "trades_rejected_by_execution": 0,
        "no_trade_reasons": {},
        "score_buckets": {},
        "pattern_direction_counts": {},
    }
    rejection_reasons = Counter()
    score_buckets = Counter()
    pattern_direction_counts = Counter()

    df = base.remove_incomplete_last_candle(df)
    if len(df) < 100:
        raise RuntimeError(f"Only {len(df)} closed candles returned")
    df = base.calculate_indicators(df)

    start = max(55, len(df) - int(bars) + 1)
    end = len(df) - int(engine.FORWARD_BARS) - 2
    if end <= start:
        raise RuntimeError(f"Not enough closed candles for validation window: start={start}, end={end}")

    trades = []
    for i in range(start, end):
        diagnostics["candidate_candles"] += 1
        diagnostics["engine_calls"] += 1
        try:
            raw_signal = base.analyze_candle(df, i)
            signal = _normalize_signal(raw_signal)
            if signal is None:
                if isinstance(raw_signal, dict) and raw_signal.get("valid") is False:
                    diagnostics["invalid_signals"] += 1
                _record_rejection(raw_signal, rejection_reasons, score_buckets, pattern_direction_counts)
                continue

            diagnostics["signals_seen"] += 1
            direction = signal["direction"]
            diagnostics["buy_signals" if direction == "BUY" else "sell_signals"] += 1
            pattern_direction_counts[direction] += 1

            trade = engine.simulate_trade(df, i, direction, signal["levels"])
            if not trade:
                diagnostics["trades_rejected_by_execution"] += 1
                continue

            trade["score"] = signal["score"]
            trade["pattern"] = signal["pattern"]
            trade["regime"] = signal["regime"]
            trades.append(trade)
            diagnostics["trades_accepted"] += 1
        except Exception as exc:
            diagnostics["engine_exceptions"] += 1
            if len(diagnostics["engine_exception_samples"]) < 5:
                diagnostics["engine_exception_samples"].append(
                    f"index={i} {type(exc).__name__}: {str(exc)[:240]}"
                )

    stats = engine.calculate_trade_statistics(trades)
    probability = engine.empirical_probability(trades)
    by_side = {}
    for side in ("BUY", "SELL"):
        subset = [t for t in trades if t.get("direction") == side]
        by_side[side] = {
            "statistics": engine.calculate_trade_statistics(subset),
            "probability": engine.empirical_probability(subset, side),
        }

    diagnostics["no_trade_reasons"] = dict(rejection_reasons.most_common())
    diagnostics["score_buckets"] = dict(score_buckets)
    diagnostics["pattern_direction_counts"] = dict(pattern_direction_counts)

    windows = engine.build_walk_forward_windows(len(df), 400, 200, 200)
    return {
        "status": "PAPER_VALIDATION_ONLY",
        "engine_version": engine.ENGINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "timeframe": "M5",
        "candles": len(df),
        "data_start": df.iloc[0]["datetime"].isoformat(),
        "data_end": df.iloc[-1]["datetime"].isoformat(),
        "diagnostics": diagnostics,
        "statistics": stats,
        "resolved_probability": probability,
        "by_side": by_side,
        "walk_forward_windows_available": len(windows),
        "assumptions": {
            "intrabar_policy": engine.INTRABAR_AMBIGUITY_POLICY,
            "spread": engine.SPREAD,
            "slippage": engine.SLIPPAGE,
            "timeout_in_expectancy": True,
            "orders_placed": False,
        },
        "warning": "This report is not proof of live profitability. Validate against the exact broker feed, spread, slippage and execution behavior before risking capital.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="XAU/USD")
    parser.add_argument("--bars", type=int, default=1000)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.symbol, args.bars), indent=2, ensure_ascii=False, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
