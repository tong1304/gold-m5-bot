"""Standalone v5 validation runner.

Fetches a larger M5 sample from Twelve Data and evaluates the conservative v5
execution layer. This is research/paper-validation only; it never places orders.
"""
import argparse
import json
import os
import sys
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
    df = df.dropna(subset=["datetime", "open", "high", "low", "close"]).sort_values("datetime").reset_index(drop=True)
    return df


def run(symbol: str, bars: int) -> dict:
    df = fetch_candles(symbol, "5min", bars)
    if len(df) < 100:
        raise RuntimeError(f"Only {len(df)} valid candles returned")

    # Use the existing signal engine for setup detection. v5 owns execution and accounting.
    trades = []
    start = max(50, len(df) - bars + 1)
    for i in range(start, len(df) - int(engine.FORWARD_BARS) - 2):
        try:
            signal = base.generate_signal(df.iloc[: i + 1].copy())
        except Exception:
            continue
        if not signal or signal.get("direction") not in ("BUY", "SELL"):
            continue
        direction = signal["direction"]
        levels = signal.get("levels") or {}
        trade = engine.simulate_trade(df, i, direction, levels)
        if trade:
            trade["score"] = signal.get("score")
            trade["pattern"] = signal.get("pattern")
            trade["regime"] = signal.get("regime")
            trades.append(trade)

    stats = engine.calculate_trade_statistics(trades)
    probability = engine.empirical_probability(trades)
    by_side = {}
    for side in ("BUY", "SELL"):
        subset = [t for t in trades if t.get("direction") == side]
        by_side[side] = {
            "statistics": engine.calculate_trade_statistics(subset),
            "probability": engine.empirical_probability(subset, side),
        }

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
