"""V11 DATE_RANGE replay adapter.

Uses the corrected LSE date-only fetcher while swapping its decision engine for
V11. Replay is candle-closed: for each M5 candle, M15 context is limited to the
latest M15 candle that was already closed at that M5 candle's close time.
"""
from __future__ import annotations

import os
from datetime import timedelta
import pandas as pd
from replay_signal_history_v10_3 import *
import replay_signal_history_v10_3 as _legacy
from v11 import engine as engine
from v11.strategy_catalog import STRATEGY_CATALOG

engine.ENGINE_VERSION = "11.0-M5-M15-STRATEGY-SPLIT"
engine.MIN_RISK_REWARD = 2.0
engine.RISK_REWARD = 2.0
_legacy.engine = engine


def _closed_m15_context(frame, ts):
    available_through = pd.Timestamp(ts) - timedelta(minutes=15)
    return frame[frame.datetime <= available_through].reset_index(drop=True)


def _empty_stat():
    return {"evaluated": 0, "pass": 0, "fail": 0, "not_applicable": 0,
            "final_selected": 0, "wins": 0, "losses": 0, "open": 0,
            "ambiguous": 0, "no_trade": 0, "net_r": 0.0, "reasons": {}}


def _strategy_stats(candidates, results_by_strategy=None):
    stats = {}
    for candidate in candidates or []:
        name = str(candidate.get("strategy") or "UNKNOWN")
        s = stats.setdefault(name, _empty_stat())
        s["evaluated"] += 1
        status = str(candidate.get("status") or "fail").lower()
        if status not in ("pass", "fail", "not_applicable"):
            status = "fail"
        s[status] += 1
        for reason in candidate.get("reason") or []:
            reason = str(reason)
            s["reasons"][reason] = s["reasons"].get(reason, 0) + 1
    for name, results in (results_by_strategy or {}).items():
        s = stats.setdefault(str(name), _empty_stat())
        for result in results if isinstance(results, list) else [results]:
            s["final_selected"] += 1
            result = str(result).upper()
            if result == "WIN":
                s["wins"] += 1
                s["net_r"] += 2.0
            elif result == "LOSS":
                s["losses"] += 1
                s["net_r"] -= 1.0
            elif result == "OPEN":
                s["open"] += 1
            elif result == "AMBIGUOUS":
                s["ambiguous"] += 1
            else:
                s["no_trade"] += 1
    return stats


# The legacy replay calls this symbol by module-global lookup. Replace it with
# the V11-aware version so PASS counts and FINAL SELECTED counts cannot be mixed.
_legacy._context = _closed_m15_context
_legacy.aggregate_strategy_stats = _strategy_stats


def replay_symbol(symbol, start, end, dry_run=False):
    # Preserve V11's required 1:2 target even though the legacy replay wrapper
    # sets its minimum internally.
    old_rr = os.environ.get("RISK_REWARD")
    os.environ["RISK_REWARD"] = "2.0"
    try:
        result = _legacy.replay_symbol(symbol, start, end, dry_run)
    finally:
        if old_rr is None:
            os.environ.pop("RISK_REWARD", None)
        else:
            os.environ["RISK_REWARD"] = old_rr

    if isinstance(result, dict):
        result["engine_version"] = engine.ENGINE_VERSION
        result["replay_source"] = "LSE_HISTORICAL_OHLCV_V11"
        result["m15_alignment"] = "CLOSED_AT_M5_CLOSE"
        result["minimum_risk_reward"] = 2.0
        result["strategy_catalog"] = STRATEGY_CATALOG.get(symbol, {})
        result["strategy_selection_note"] = (
            "PASS counts include every evaluated strategy. final_selected counts only the strategy "
            "actually selected to create a final outcome; these are intentionally separate."
        )
    return result


def main():
    _legacy.engine = engine
    _legacy._context = _closed_m15_context
    _legacy.aggregate_strategy_stats = _strategy_stats
    return _legacy.main()


if __name__ == "__main__":
    main()
