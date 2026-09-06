from __future__ import annotations

from typing import Any

EVENT_TTL_BARS = {
    "LIQUIDITY_SWEEP": 3,
    "SWEEP": 3,
    "FAILED_BREAK": 3,
    "BREAKOUT": 5,
    "BREAKOUT_RETEST": 5,
    "TREND_PULLBACK": 8,
    "PULLBACK": 8,
    "TREND": 10,
    "REGIME_CHANGE": 10,
}
DEFAULT_TTL_BARS = 5
MIN_RR = 1.50
LATE_RR = 1.25
MIN_ATR_SPACE = 0.50


def _f(value: Any) -> float | None:
    try:
        x = float(value)
        return x if x == x and abs(x) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _ttl(event_type: Any) -> int:
    key = str(event_type or "").upper().strip().replace("-", "_")
    for name, bars in EVENT_TTL_BARS.items():
        if name in key:
            return bars
    return DEFAULT_TTL_BARS


def evaluate_execution_geometry(*, direction: str, entry: Any, stop: Any, target: Any,
                                current_price: Any, atr: Any = None,
                                bars_since_event: int = 0, event_type: Any = None) -> dict[str, Any]:
    d = str(direction or "").upper().strip()
    e, s, t, p, a = map(_f, (entry, stop, target, current_price, atr))
    ttl = _ttl(event_type)
    bars = max(0, int(bars_since_event or 0))
    if d not in {"BUY", "SELL"} or None in (e, s, t, p) or (d == "BUY" and not s < e < t) or (d == "SELL" and not t < e < s):
        return {"state": "INVALID_GEOMETRY", "thesis_status": "INVALID", "rr": None, "ttl_bars": ttl, "bars_since_event": bars}
    risk = abs(e - s)
    reward = abs(t - e)
    rr = reward / risk if risk > 0 else 0.0
    favorable_distance = (p - e) if d == "BUY" else (e - p)
    remaining_reward = (t - p) if d == "BUY" else (p - t)
    current_rr = remaining_reward / risk if risk > 0 else 0.0
    space_atr = (abs(t - p) / a) if a and a > 0 else None
    if bars > ttl:
        state, thesis = "EXPIRED", "EXPIRED"
    elif current_rr < LATE_RR or (space_atr is not None and space_atr < MIN_ATR_SPACE):
        state, thesis = "TOO_LATE", "VALID_BUT_MISSED"
    elif rr < MIN_RR:
        state, thesis = "UNFAVORABLE_RR", "VALID_BUT_ECONOMICS_WEAK"
    elif favorable_distance < 0:
        state, thesis = "WAIT_ENTRY", "VALID"
    else:
        state, thesis = "ACTIONABLE", "VALID"
    return {
        "state": state,
        "thesis_status": thesis,
        "rr": round(rr, 4),
        "current_rr": round(current_rr, 4),
        "ttl_bars": ttl,
        "bars_since_event": bars,
        "space_atr": round(space_atr, 4) if space_atr is not None else None,
        "entry_reference": e,
        "stop_reference": s,
        "target_reference": t,
        "current_price": p,
        "event_type": str(event_type or "").upper().strip(),
    }
