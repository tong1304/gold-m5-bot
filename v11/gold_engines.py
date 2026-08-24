from __future__ import annotations

from .new_gold_engines import (
    GOLD_NEW_ENGINE_NAMES,
    GOLD_NEW_ENGINE_MIN_RR,
    evaluate_new_gold_engines,
)

# Approved GOLD architecture: only G1-G3 are active.
GOLD_ENGINE_MAP = {
    "G1": "LIQUIDITY_SWEEP_CHOCH",
    "G2": "CONTINUATION_FVG_PULLBACK",
    "G3": "SESSION_BREAKOUT_RETEST",
}
GOLD_ENGINE_NAMES = dict(GOLD_NEW_ENGINE_NAMES)
GOLD_ENGINE_PRIORITY = {"G1": 0, "G2": 1, "G3": 2}
GOLD_ENGINE_MIN_RR = dict(GOLD_NEW_ENGINE_MIN_RR)
GOLD_STRATEGIES = tuple(GOLD_NEW_ENGINE_NAMES[g] for g in ("G1", "G2", "G3"))


def evaluate_gold_engines(m5, m15, h1, regime=None, *, m1=None, high_impact_news=False,
                          news_blocked=False, session_trade_taken=None):
    """Run only the approved G1/G2/G3 engines.

    H1 supplies context/POI; M15 supplies direction/bias only. No M15 regime
    filter is applied here. M5 remains the execution timeframe.
    """
    regime = regime or {}
    h1_bias = str(regime.get("h1_bias") or "NEUTRAL").upper()
    m15_context = regime.get("m15_context") or {}
    m15_direction = str(m15_context.get("direction") or regime.get("m15_direction") or "NEUTRAL").upper()
    ctx = {
        "h1_bias": h1_bias,
        "h1_poi": regime.get("h1_poi"),
        "poi": regime.get("poi"),
        "m15": {"direction": m15_direction},
        "m1": m1,
        "high_impact_news": bool(high_impact_news),
        "news_blocked": bool(news_blocked),
        "session_trade_taken": session_trade_taken or {},
    }
    candidates, trace = evaluate_new_gold_engines(m5, m15, h1, ctx)
    for item in candidates:
        item["engine"] = str(item.get("engine", "")).upper()
        item["strategy"] = f"{item['engine']}_{GOLD_ENGINE_NAMES.get(item['engine'], item.get('strategy',''))}"
        item["minimum_rr"] = GOLD_ENGINE_MIN_RR.get(item["engine"], 2.0)
    for item in trace:
        item["engine"] = str(item.get("engine", "")).upper()
    candidates.sort(key=lambda x: (GOLD_ENGINE_PRIORITY.get(x.get("engine"), 99), -float(x.get("quality", 0) or 0)))
    return candidates, trace
