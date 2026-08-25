from __future__ import annotations

"""BTC B1/B2/B3 dispatcher.

BTC strategies are selected by the active M5 regime first, then each
strategy evaluates its own Core Gate, Score and Risk Filter. H1 direction
is a hard directional gate and is recorded explicitly in the trace.
"""

from .asset_strategies import _b1, _b2, _b3
from .regime import strategy_allowed_by_regime
from .h1_gate import allows_trend_direction, gate_reason

BTC_STRATEGIES = ("B1", "B2", "B3")
BTC_FUNCTIONS = {"B1": _b1, "B2": _b2, "B3": _b3}


def _h1_gate_result(engine, direction, regime):
    h1_bias = str(regime.get("h1_bias") or "NEUTRAL").upper()
    if allows_trend_direction(h1_bias, direction):
        return None
    reason = gate_reason(h1_bias, direction)
    return {
        "status": "FAIL",
        "engine": engine,
        "strategy": f"BTC_{engine}",
        "direction": direction,
        "quality": 0.0,
        "score_detail": {
            "score": 0.0,
            "minimum_score": None,
            "qualified": False,
            "failed_gate": ["h1_direction"],
            "filter_rejections": [],
            "h1_bias": h1_bias,
            "h1_gate_reason": reason,
        },
        "rejection_reasons": [reason],
        "evidence": {"h1_bias": h1_bias, "h1_gate": reason},
    }


def evaluate_btc_strategies(m5, regime):
    """Evaluate only BTC strategies compatible with the current M5 regime."""
    candidates = []
    trace = []
    current_regime = str(regime.get("m5_regime") or regime.get("regime") or "TRANSITION").upper()

    for engine in BTC_STRATEGIES:
        if not strategy_allowed_by_regime("BTC", engine, current_regime):
            trace.append({
                "status": "NOT_APPLICABLE",
                "engine": engine,
                "strategy": f"BTC_{engine}",
                "regime": current_regime,
                "reason": "REGIME_NOT_COMPATIBLE",
            })
            continue

        fn = BTC_FUNCTIONS[engine]
        for direction in ("BUY", "SELL"):
            h1_failure = _h1_gate_result(engine, direction, regime)
            if h1_failure is not None:
                trace.append(h1_failure)
                continue
            try:
                result = fn(m5.tail(140).reset_index(drop=True).copy(), direction, regime)
            except Exception as exc:
                result = {
                    "status": "FAIL",
                    "engine": engine,
                    "strategy": f"BTC_{engine}",
                    "direction": direction,
                    "quality": 0.0,
                    "score_detail": {
                        "score": 0.0,
                        "qualified": False,
                        "failed_gate": [f"ENGINE_ERROR:{type(exc).__name__}"],
                        "filter_rejections": [],
                    },
                    "rejection_reasons": [f"ENGINE_ERROR:{type(exc).__name__}:{exc}"],
                    "evidence": {},
                }
            trace.append(result)
            if result.get("status") == "PASS" and result.get("score_detail", {}).get("qualified"):
                candidates.append(result)

    candidates.sort(key=lambda item: item.get("quality", 0.0), reverse=True)
    return candidates, trace
