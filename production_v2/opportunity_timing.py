from __future__ import annotations

"""Evidence-speed classification for opportunity lifecycle.

This layer does not authorize trades. It classifies how quickly a live
opportunity should receive the next closed-candle evidence check while E9
remains the sole execution authority.
"""

from typing import Any

DIRECTIONS = {"BUY", "SELL"}
EARLY = "EARLY_OPPORTUNITY"
CONFIRMED = "CONFIRMED_OPPORTUNITY"
LATE = "LATE_OPPORTUNITY"
NEUTRAL = "NO_DIRECTIONAL_OPPORTUNITY"
FAST = "FAST"
STANDARD = "STANDARD"
SLOW = "SLOW"
BLOCK = "BLOCK"
LATE_DISPLACEMENT_ATR = 0.70
FAST_MIN_QUALITY = 65.0
FAST_MIN_SPACE_ATR = 0.75
STRONG_EVENTS = ("FAILED_BREAK_RECLAIM", "SWEEP_RECLAIM", "SWEEP_REJECTION", "HIGH_REJECTION", "LOW_REJECTION", "HIGH_ACCEPTANCE", "LOW_ACCEPTANCE", "BREAK", "RECLAIM", "LIQUIDITY_INTERACTION", "ACCEPTANCE", "REJECTION", "SWEEP")
CONFIRMED_STATES = {"CONFIRMED", "PROVEN", "VALIDATED", "TRADE_READY", "ACCEPTED", "REJECTED", "RECLAIMED", "TERMINALLY_CONFIRMED"}


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{k}={_text(v)}" for k, v in sorted(value.items(), key=lambda x: str(x[0])))
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(v) for v in value)
    return str(value if value is not None else "").upper().strip()


def _num(output: dict[str, Any], *keys: str, default: float | None = None) -> float | None:
    for key in keys:
        try:
            value = float(output.get(key))
        except (TypeError, ValueError):
            continue
        if value == value and abs(value) != float("inf"):
            return value
    return default


def _direction(output: dict[str, Any]) -> str:
    for key in ("direction", "direction_thesis", "thesis_direction", "opportunity_direction"):
        value = _text(output.get(key))
        if value == "BUY" or value.startswith(("BUY ", "BUY_", "BUY:")):
            return "BUY"
        if value == "SELL" or value.startswith(("SELL ", "SELL_", "SELL:")):
            return "SELL"
    finding = _text(output.get("finding"))
    if finding.startswith("BUY "):
        return "BUY"
    if finding.startswith("SELL "):
        return "SELL"
    return "NEUTRAL"


def _age_bars(output: dict[str, Any]) -> int:
    anchor = output.get("causal_event_anchor")
    for value in (output.get("event_age_bars"), output.get("bars_waited"), anchor.get("age_bars") if isinstance(anchor, dict) else None):
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def _event(output: dict[str, Any]) -> str:
    return _text(output.get("event") or output.get("event_type") or output.get("auction_event") or output.get("liquidity_event") or output.get("finding"))


def _confirmed(output: dict[str, Any]) -> bool:
    confirmation = _text(output.get("confirmation_state") or output.get("confirmation") or output.get("trigger_state"))
    auction = _text(output.get("auction_state") or output.get("auction_phase"))
    thesis = bool(output.get("e6_thesis_proven") or output.get("thesis_proven"))
    return confirmation in CONFIRMED_STATES or auction in CONFIRMED_STATES or (thesis and confirmation in {"PROVEN", "CONFIRMED", "VALIDATED", "TRADE_READY"})


def _hard_block(output: dict[str, Any]) -> bool:
    text = " ".join(_text(output.get(k)) for k in ("reason_codes", "reasons", "blockers", "conflicts", "invalidations"))
    state = _text(output.get("state") or output.get("execution_state"))
    return any(token in text or token in state for token in ("INVALIDATED", "HARD_VETO", "RISK_BLOCKED", "NO_USABLE_STRUCTURAL_TARGET", "STOP_TOO_WIDE"))


def _directional_space(output: dict[str, Any], direction: str) -> float:
    if direction == "BUY":
        return _num(output, "available_space_atr_long", "long_space_atr", "available_space_atr", "effective_space_atr", "space_atr", default=0.0) or 0.0
    if direction == "SELL":
        return _num(output, "available_space_atr_short", "short_space_atr", "available_space_atr", "effective_space_atr", "space_atr", default=0.0) or 0.0
    return 0.0


def classify_opportunity_timing(output: dict[str, Any]) -> dict[str, Any]:
    out = dict(output or {})
    direction = _direction(out)
    age = _age_bars(out)
    event = _event(out)
    confidence = _num(out, "opportunity_strength", "opportunity_score", "confidence", "evidence_strength", "auction_quality", "liquidity_quality", "quality", default=0.0) or 0.0
    if confidence <= 1.0:
        confidence *= 100.0
    confidence = max(0.0, min(100.0, confidence))
    space = _directional_space(out, direction)
    confirmed = _confirmed(out)
    hard_block = _hard_block(out)
    strong_event = any(token in event for token in STRONG_EVENTS)
    event_level = _num(out, "event_level")
    price = _num(out, "price", "current_price", "last_price")
    event_atr = _num(out, "event_atr_frozen", "event_atr", "atr")
    displacement_atr = abs(price - event_level) / event_atr if event_level is not None and price is not None and event_atr and event_atr > 0 else None
    late_by_age = age >= 2
    late_by_displacement = displacement_atr is not None and displacement_atr >= LATE_DISPLACEMENT_ATR
    late = late_by_age or late_by_displacement
    if direction not in DIRECTIONS:
        phase, speed, reasons = NEUTRAL, STANDARD, ["NO_DIRECTIONAL_EVIDENCE"]
    elif hard_block:
        phase, speed, reasons = (LATE if late else EARLY), (BLOCK if late else SLOW), ["HARD_BLOCK_PRESENT"]
    elif confirmed and not late:
        phase, speed, reasons = CONFIRMED, STANDARD, ["CLOSED_CANDLE_CONFIRMATION_PRESENT"]
    elif late:
        phase, speed = LATE, SLOW
        reasons = []
        if late_by_age:
            reasons.append("EVENT_AGE_REACHED_LATE_WINDOW")
        if late_by_displacement:
            reasons.append("PRICE_DISPLACEMENT_REACHED_LATE_WINDOW")
        if confirmed:
            reasons.append("CONFIRMED_BUT_ENTRY_WINDOW_IS_LATE")
    elif strong_event and confidence >= FAST_MIN_QUALITY and space >= FAST_MIN_SPACE_ATR:
        phase, speed, reasons = EARLY, FAST, ["HIGH_QUALITY_FRESH_EVENT", "FAST_EVIDENCE_CYCLE_ALLOWED"]
    elif confidence >= 50.0:
        phase, speed, reasons = EARLY, STANDARD, ["DEVELOPING_EVIDENCE_REQUIRES_STANDARD_CONFIRMATION"]
    else:
        phase, speed, reasons = EARLY, SLOW, ["LOW_EVIDENCE_REQUIRES_ADDITIONAL_CONFIRMATION"]
    if space < FAST_MIN_SPACE_ATR and direction in DIRECTIONS:
        reasons.append("SPACE_BELOW_MINIMUM_FOR_FAST_PATH")
        if speed == FAST:
            speed = STANDARD
    return {
        "phase": phase,
        "decision_speed": speed,
        "direction": direction,
        "event_age_bars": age,
        "event": event,
        "evidence_quality": round(confidence, 2),
        "available_space_atr": round(space, 4),
        "displacement_atr": round(displacement_atr, 4) if displacement_atr is not None else None,
        "confirmed": confirmed,
        "late_by_age": late_by_age,
        "late_by_displacement": late_by_displacement,
        "fast_path_eligible": speed == FAST,
        "chase_prohibited": phase == LATE,
        "execution_authority": "E9_ONLY",
        "reasons": list(dict.fromkeys(reasons)),
    }


def enrich_timing(output: dict[str, Any]) -> dict[str, Any]:
    out = dict(output or {})
    timing = classify_opportunity_timing(out)
    out["opportunity_timing"] = timing
    out["opportunity_phase_speed"] = timing["phase"]
    out["opportunity_decision_speed"] = timing["decision_speed"]
    out["opportunity_fast_path"] = timing["fast_path_eligible"]
    out["opportunity_chase_prohibited"] = timing["chase_prohibited"]
    return out
