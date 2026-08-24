from __future__ import annotations

from .new_gold_engines import GOLD_NEW_ENGINE_NAMES, GOLD_NEW_ENGINE_MIN_RR, evaluate_new_gold_engines

GOLD_ENGINE_MAP = {"G1": "LIQUIDITY_SWEEP_CHOCH", "G2": "CONTINUATION_FVG_PULLBACK", "G3": "SESSION_BREAKOUT_RETEST"}
GOLD_ENGINE_NAMES = dict(GOLD_NEW_ENGINE_NAMES)
GOLD_ENGINE_PRIORITY = {"G1": 0, "G2": 1, "G3": 2}
GOLD_ENGINE_MIN_RR = dict(GOLD_NEW_ENGINE_MIN_RR)
GOLD_STRATEGIES = tuple(GOLD_NEW_ENGINE_NAMES[g] for g in ("G1", "G2", "G3"))


def evaluate_gold_engines(m5, m15, h1, regime=None, *, m1=None, high_impact_news=False,
                          news_blocked=False, session_trade_taken=None):
    """Approved GOLD routing: H1 context, M15 direction/bias, M5 execution only."""
    regime = dict(regime or {})
    m15_context = dict(regime.get("m15_context") or {})
    m15_direction = str(m15_context.get("direction") or regime.get("m15_direction") or "NEUTRAL").upper()
    regime["h1_bias"] = str(regime.get("h1_bias") or "NEUTRAL").upper()
    regime["m15_context"] = {"direction": m15_direction}
    regime["m1"] = m1
    regime["high_impact_news"] = bool(high_impact_news)
    regime["news_blocked"] = bool(news_blocked)
    regime["session_trade_taken"] = session_trade_taken or {}
    candidates, trace = evaluate_new_gold_engines(m5, m15, h1, regime)
    for item in candidates + trace:
        gid = str(item.get("engine", "")).upper()
        item["engine"] = gid
        item["strategy"] = f"{gid}_{GOLD_ENGINE_NAMES.get(gid, item.get('strategy', ''))}"
        item["minimum_rr"] = GOLD_ENGINE_MIN_RR.get(gid, 2.0)
    candidates.sort(key=lambda x: (GOLD_ENGINE_PRIORITY.get(x.get("engine"), 99), -float(x.get("quality", 0) or 0)))
    return candidates, trace
