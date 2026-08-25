from __future__ import annotations

"""BTC B1/B2/B3 dispatcher.

The BTC asset family must always produce an explicit evaluation trace for
B1/B2/B3.  Regime is passed into each strategy as context, while the
strategy's own Core Gate, Score and Risk Filter decide qualification.
This prevents an absent/legacy registry path from turning a real evaluation
into UNKNOWN/NOT_APPLICABLE.
"""

from .asset_strategies import _b1, _b2, _b3

BTC_STRATEGIES = ("B1", "B2", "B3")
BTC_FUNCTIONS = {"B1": _b1, "B2": _b2, "B3": _b3}


def evaluate_btc_strategies(m5, regime):
    """Evaluate every BTC strategy/direction and return candidates + trace.

    Each strategy is responsible for its own Core Gate, weighted Score and
    Filters.  We intentionally do not short-circuit on the generic regime
    registry here: the regime is supplied as strategy context so a strategy
    can use it in its asset-specific rules without becoming UNKNOWN.
    """
    candidates = []
    trace = []
    for engine in BTC_STRATEGIES:
        fn = BTC_FUNCTIONS[engine]
        for direction in ("BUY", "SELL"):
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
