from __future__ import annotations

"""Retrospective opportunity-quality measurement.

This module is deliberately non-authoritative: it never creates a trade signal,
changes E9 governance, or loosens an execution gate. It classifies what happened
*after* an opportunity lifecycle has enough closed-candle evidence to evaluate.
"""

from typing import Any, Iterable

VALID_DIRECTIONS = {"BUY", "SELL"}
CLASSIFICATIONS = {
    "GOOD_WAIT",
    "MISSED_GOOD_TRADE",
    "LATE_ENTRY",
    "FALSE_OPPORTUNITY",
    "UNRESOLVED",
}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _num(value: Any) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def _price(candle: dict[str, Any], key: str) -> float | None:
    return _num(candle.get(key))


def _favorable_excursion(direction: str, entry: float, candles: Iterable[dict[str, Any]]) -> float:
    best = 0.0
    for candle in candles:
        high, low = _price(candle, "high"), _price(candle, "low")
        if high is None or low is None:
            continue
        move = high - entry if direction == "BUY" else entry - low
        best = max(best, move)
    return best


def _adverse_excursion(direction: str, entry: float, candles: Iterable[dict[str, Any]]) -> float:
    worst = 0.0
    for candle in candles:
        high, low = _price(candle, "high"), _price(candle, "low")
        if high is None or low is None:
            continue
        move = entry - low if direction == "BUY" else high - entry
        worst = max(worst, move)
    return worst


def classify_opportunity(
    opportunity: dict[str, Any],
    followup_candles: Iterable[dict[str, Any]],
    *,
    favorable_r: float = 0.50,
    late_extension_r: float = 1.00,
) -> dict[str, Any]:
    """Classify a completed/aged opportunity from subsequent closed candles.

    Expected opportunity fields are intentionally permissive so this can consume
    persisted lifecycle records without coupling the detector to E6/E8 schemas.
    """
    op = dict(opportunity or {})
    candles = [dict(c) for c in (followup_candles or ()) if isinstance(c, dict)]
    direction = _text(op.get("direction"))
    if direction not in VALID_DIRECTIONS:
        return {"classification": "UNRESOLVED", "reason": "INVALID_DIRECTION", "measured": False}

    entry = _num(op.get("entry") or op.get("entry_price"))
    stop = _num(op.get("stop") or op.get("stop_loss"))
    risk = abs(entry - stop) if entry is not None and stop is not None else None
    if entry is None or risk is None or risk <= 0:
        # A watch can be useful even before E8 supplies executable geometry.
        if not op.get("thesis_proven") and _text(op.get("state")) in {"WATCHING", "DEVELOPING", "FORMING"}:
            return {"classification": "GOOD_WAIT", "reason": "THESIS_OR_ECONOMIC_GEOMETRY_NOT_PROVEN", "measured": True}
        return {"classification": "UNRESOLVED", "reason": "MISSING_EXECUTABLE_GEOMETRY", "measured": False}

    favorable = _favorable_excursion(direction, entry, candles) / risk
    adverse = _adverse_excursion(direction, entry, candles) / risk
    thesis_proven = bool(op.get("thesis_proven") or op.get("e6_thesis_proven") or op.get("setup_exists"))
    executed = bool(op.get("executed") or _text(op.get("execution_state")) in {"POSITION_OPEN", "EXECUTED"})
    authorized = bool(op.get("trade_authorized") or op.get("execution_authorized"))
    invalidated = _text(op.get("state")) in {"INVALIDATED", "EXPIRED", "REPLACED"} or bool(op.get("invalidated"))

    if executed or authorized:
        return {
            "classification": "GOOD_WAIT" if favorable < favorable_r else "MISSED_GOOD_TRADE" if not executed else "GOOD_WAIT",
            "reason": "EXECUTED_OR_AUTHORIZED",
            "measured": True,
            "favorable_r": round(favorable, 4),
            "adverse_r": round(adverse, 4),
        }

    if thesis_proven and favorable >= favorable_r:
        classification = "LATE_ENTRY" if favorable >= late_extension_r else "MISSED_GOOD_TRADE"
        return {
            "classification": classification,
            "reason": "PROVEN_OPPORTUNITY_MOVED_WITHOUT_EXECUTION",
            "measured": True,
            "favorable_r": round(favorable, 4),
            "adverse_r": round(adverse, 4),
        }

    if invalidated and adverse >= favorable_r:
        return {
            "classification": "FALSE_OPPORTUNITY",
            "reason": "OPPORTUNITY_INVALIDATED_BEFORE_FAVORABLE_MOVE",
            "measured": True,
            "favorable_r": round(favorable, 4),
            "adverse_r": round(adverse, 4),
        }

    if not thesis_proven:
        return {
            "classification": "GOOD_WAIT",
            "reason": "CONDITIONAL_OPPORTUNITY_NEVER_PROVED",
            "measured": True,
            "favorable_r": round(favorable, 4),
            "adverse_r": round(adverse, 4),
        }

    return {
        "classification": "UNRESOLVED",
        "reason": "INSUFFICIENT_FOLLOW_THROUGH_EVIDENCE",
        "measured": False,
        "favorable_r": round(favorable, 4),
        "adverse_r": round(adverse, 4),
    }
