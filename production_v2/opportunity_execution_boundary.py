from __future__ import annotations

"""Bridge opportunity intelligence into an explicit preparation state.

This boundary deliberately does not authorize a trade. It makes a live,
non-invalidated opportunity visible as PREPARE/WATCH while E7/E8/E9 continue
to own confirmation, economics and capital authorization.
"""

from typing import Any

from .contracts import DecisionResult

_ACTIONABLE_STAGES = {"HIGH_OPPORTUNITY", "ACTIONABLE"}
_WATCH_STAGES = {"WATCH", "DEVELOPING"}
_HARD_INVALIDATIONS = {
    "THESIS_INVALIDATED",
    "E6_THESIS_INVALIDATED",
    "E7_CONFIRMATION_INVALIDATED",
    "E8_RISK_INVALIDATED",
    "STRUCTURE_INVALIDATED",
    "E3_STRUCTURE_INVALIDATED",
    "STRUCTURE_INTEGRITY_INVALID",
    "EXECUTION_IMPOSSIBLE",
    "DATA_INTEGRITY_INVALID",
}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _codes(value: Any) -> set[str]:
    if not isinstance(value, dict):
        return set()
    found: set[str] = set()
    for key in (
        "reason_codes",
        "reasons",
        "blockers",
        "conflicts",
        "invalidations",
        "active_invalidations",
        "hard_vetoes",
    ):
        raw = value.get(key)
        if isinstance(raw, str):
            found.add(_text(raw))
        elif isinstance(raw, (list, tuple, set)):
            found.update(_text(item) for item in raw if _text(item))
    return found


def _confirmed(result: DecisionResult) -> bool:
    for engine in result.engines:
        if engine.engine_id != "E7":
            continue
        output = engine.output or {}
        confirmation = _text(
            output.get("confirmation_state")
            or output.get("confirmation")
            or output.get("proof_state")
        )
        trigger = any(
            output.get(key) is True
            for key in ("trigger_observed", "valid_trigger", "closed_candle_trigger")
        )
        if confirmation in {"PROVEN", "CONFIRMED", "VALIDATED", "TRADE_READY"} and trigger:
            return True
    return False


def apply_opportunity_execution_boundary(result: DecisionResult) -> DecisionResult:
    """Expose actionable opportunity state without bypassing E8/E9."""
    risk = dict(result.risk or {})
    intelligence = risk.get("opportunity_intelligence")
    if not isinstance(intelligence, dict):
        return result

    leader = intelligence.get("leader") if isinstance(intelligence.get("leader"), dict) else {}
    stage = _text(intelligence.get("leader_stage") or leader.get("stage"))
    direction = _text(intelligence.get("leader_direction") or leader.get("direction"))
    opportunity_id = str(intelligence.get("opportunity_id") or "").strip()
    score = intelligence.get("leader_score", leader.get("score", 0.0))
    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 0.0

    invalidations = _codes(risk)
    for engine in result.engines:
        invalidations.update(_codes(engine.output))
    invalidated = bool(invalidations & _HARD_INVALIDATIONS)

    confirmed = _confirmed(result)
    if confirmed or invalidated:
        risk["opportunity_action"] = "HOLD" if confirmed else "INVALIDATE"
        risk["opportunity_state"] = "CONFIRMED" if confirmed else "INVALIDATED"
        risk["opportunity_direction"] = direction if direction in {"BUY", "SELL"} else "NEUTRAL"
        risk["opportunity_score"] = score
        risk["trade_authorized"] = result.decision in {"BUY", "SELL"} and result.gate_passed
        return result.__class__(
            result.symbol,
            result.timeframe,
            result.decision,
            result.gate_passed,
            result.score,
            result.engines,
            risk,
            result.reason_codes,
            result.state,
            result.blocked_by,
            result.wait_bars,
            result.execution_state,
        )

    if stage in _ACTIONABLE_STAGES and direction in {"BUY", "SELL"}:
        risk.update(
            {
                "opportunity_action": "PREPARE",
                "opportunity_state": "ACTIONABLE_OPPORTUNITY",
                "opportunity_direction": direction,
                "opportunity_score": score,
                "opportunity_id": opportunity_id,
                "trade_authorized": False,
                "user_action": "PREPARE_ENTRY_AND_WAIT_FOR_E7_CONFIRMATION",
                "next_required_event": "NEXT_CLOSED_M5_CANDLE",
                "authority_note": "PREPARE_ONLY_E7_E8_E9_RETAIN_TRADE_AUTHORITY",
            }
        )
        state = "OPPORTUNITY_ACTIONABLE"
    elif stage in _WATCH_STAGES and direction in {"BUY", "SELL"}:
        risk.update(
            {
                "opportunity_action": "WATCH",
                "opportunity_state": "OPPORTUNITY_WATCH",
                "opportunity_direction": direction,
                "opportunity_score": score,
                "opportunity_id": opportunity_id,
                "trade_authorized": False,
                "user_action": "WAIT_FOR_REQUIRED_EVENT",
            }
        )
        state = result.state
    else:
        risk.setdefault("opportunity_action", "IGNORE")
        risk.setdefault("opportunity_state", "NO_OPPORTUNITY")
        risk["trade_authorized"] = result.decision in {"BUY", "SELL"} and result.gate_passed
        state = result.state

    return result.__class__(
        result.symbol,
        result.timeframe,
        result.decision,
        result.gate_passed,
        result.score,
        result.engines,
        risk,
        result.reason_codes,
        state,
        result.blocked_by,
        result.wait_bars,
        result.execution_state,
    )
