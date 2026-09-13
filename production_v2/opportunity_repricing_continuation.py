from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def apply_opportunity_repricing(lifecycle: dict[str, Any], *, e4: dict[str, Any] | None = None, e5: dict[str, Any] | None = None, e8: dict[str, Any] | None = None) -> dict[str, Any]:
    state = dict(lifecycle or {})
    e4 = dict(e4 or {})
    e5 = dict(e5 or {})
    e8 = dict(e8 or {})
    if _text(state.get("direction")) not in {"BUY", "SELL"}:
        return state
    if _text(state.get("state")) in {"INVALIDATED", "EXPIRED", "REPLACED", "EXECUTED"} or _text(state.get("lifecycle_stage")) in {"INVALIDATED", "EXPIRED", "REPLACED", "EXECUTED", "TRADE"}:
        return state
    economic_stage = _text(e8.get("economic_stage"))
    reasons = {_text(item) for item in (e8.get("reason_codes") or e8.get("reasons") or [])}
    immature = economic_stage == "EARLY_OPPORTUNITY_SCREEN" and not bool(e8.get("trade_authorized"))
    pending_auction = _text(e4.get("auction_state") or e4.get("auction_phase")) in {"PENDING", "FORMING", "WATCH", "UNRESOLVED"}
    geometry_blockers = {"REAL_RR_BELOW_MINIMUM", "NO_USABLE_STRUCTURAL_TARGET", "EFFECTIVE_SPACE_UNRELIABLE", "TARGET_REALISM_TOO_LOW", "INVALID_TRADE_GEOMETRY", "STOP_QUALITY_TOO_LOW"}
    needs_reprice = immature and (pending_auction or bool(reasons & geometry_blockers))
    if not needs_reprice:
        return state
    direction = _text(state.get("direction"))
    space = e5.get("available_space_atr_long" if direction == "BUY" else "available_space_atr_short")
    updated = dict(state)
    updated.update({
        "lifecycle_stage": "REPRICE_WAIT",
        "state": "REPRICE_WAIT",
        "lifecycle_state": "REPRICE_WAIT",
        "opportunity_phase": "REPRICE_WAIT",
        "wait_for": "NEXT_CLOSED_M5_CANDLE_REPRICE",
        "wait_for_stage": "CONFIRMATION",
        "trade_authorized": False,
        "reprice_required": True,
        "reprice_at_next_candle": True,
        "economic_blockers_deferred": True,
        "reprice_reason": "IMMATURE_OPPORTUNITY_ECONOMICS;RECHECK_AFTER_CLOSED_CANDLE",
        "economic_blockers": sorted(reasons & geometry_blockers),
        "auction_state_at_reprice": _text(e4.get("auction_state") or e4.get("auction_phase") or "UNKNOWN"),
        "available_space_atr_at_reprice": space,
    })
    return updated
