from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult


NAME = "Confirmation / Trigger Brain"
QUESTION = "Does the setup have a valid closed-candle confirmation, or what is still missing?"
ARCHITECTURE = "E7_PROFESSIONAL_SETUP_AWARE_CONFIRMATION_BRAIN_V1"
VERSION = "1.0"
ATR_PERIOD = 14
MIN_BARS = 5


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _dedupe(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values if v))


def _atr(bars: list[dict[str, Any]], period: int = ATR_PERIOD) -> float:
    if len(bars) < 2:
        return 0.0
    start = max(1, len(bars) - period)
    trs: list[float] = []
    for i in range(start, len(bars)):
        h = _num(bars[i].get("high"))
        l = _num(bars[i].get("low"))
        pc = _num(bars[i - 1].get("close"))
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return mean(trs) if trs else 0.0


def _direction(value: Any) -> str:
    t = _text(value)
    if t in {"BUY", "BULLISH", "UP", "LONG", "BUYERS"}:
        return "BUY"
    if t in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS"}:
        return "SELL"
    return "NEUTRAL"


def _candle(bars: list[dict[str, Any]]) -> dict[str, float | bool]:
    b = bars[-1]
    p = bars[-2]
    o, h, l, c = (_num(b.get(k)) for k in ("open", "high", "low", "close"))
    po, ph, pl, pc = (_num(p.get(k)) for k in ("open", "high", "low", "close"))
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    atr = max(_atr(bars), 1e-9)
    pos = (c - l) / rng
    upper = h - max(o, c)
    lower = min(o, c) - l
    return {
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "prev_open": po,
        "prev_high": ph,
        "prev_low": pl,
        "prev_close": pc,
        "range": rng,
        "body": body,
        "body_atr": body / atr,
        "close_position": pos,
        "upper_wick": upper,
        "lower_wick": lower,
        "bullish": c > o,
        "bearish": c < o,
        "bullish_engulf": o <= pc and c >= po and c > o,
        "bearish_engulf": o >= pc and c <= po and c < o,
        "bullish_displacement": c > o and body / atr >= 0.55 and pos >= 0.65,
        "bearish_displacement": c < o and body / atr >= 0.55 and pos <= 0.35,
        "higher_close": c > pc,
        "lower_close": c < pc,
    }


def _e4_context(e4: dict[str, Any]) -> dict[str, Any]:
    event = _text(e4.get("event", e4.get("finding")))
    state = _text(e4.get("auction_state", e4.get("state")))
    event_level = _num(e4.get("event_level"))
    age = max(0, int(_num(e4.get("event_age_bars"))))
    event_direction = _direction(e4.get("direction"))
    if event_direction == "NEUTRAL":
        if "HIGH_FAILED_BREAK_RECLAIM" in event or "HIGH_SWEEP_REJECTION" in event:
            event_direction = "SELL"
        elif "LOW_FAILED_BREAK_RECLAIM" in event or "LOW_SWEEP_REJECTION" in event:
            event_direction = "BUY"
        elif "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
            event_direction = "BUY"
        elif "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
            event_direction = "SELL"
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    return {
        "event": event,
        "state": state,
        "terminal": terminal,
        "pending": state == "PENDING" or "PENDING" in event,
        "age": age,
        "direction": event_direction,
        "level": event_level,
        "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""),
        "quality": _num(e4.get("auction_quality")),
    }


def _base(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "question": QUESTION,
        "role": "CONFIRMATION_ANALYST",
        "reasoning_role": "CONFIRMATION_ANALYST",
        "decision_authority": "E9",
        "trade_decision_authority": False,
        "closed_candle_only": True,
        "lookahead": False,
        "bar_count": len(snapshot.get("bars") or []),
    }


def _empty_result(snapshot: dict[str, Any], reason: str) -> EngineResult:
    output = {
        **_base(snapshot),
        "state": "WAIT",
        "confirmation": "UNRESOLVED",
        "trigger_status": "NOT_EVALUATED",
        "direction": "NEUTRAL",
        "setup": "NONE",
        "trigger_observed": False,
        "confirmation_strength": "NONE",
        "confirmation_score": 0.0,
        "supporting_evidence": [],
        "counter_evidence": [reason],
        "missing_evidence": ["valid setup thesis", "valid closed-candle confirmation"],
        "next_required_evidence": ["a valid closed candle proving the setup thesis"],
        "invalidation": ["new closed candle invalidates or replaces the current thesis"],
        "proof_gates": {},
        "reasoning_trace": {"conclusion": "Confirmation cannot be evaluated from current context."},
    }
    return EngineResult("E7", NAME, False, 0.0, output, ("INSUFFICIENT_CONTEXT",))


def analyze_e7(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars = list(snapshot.get("bars") or [])
    e6 = upstream.get("E6")
    e4 = upstream.get("E4")
    e3 = upstream.get("E3")
    e5 = upstream.get("E5")

    if len(bars) < MIN_BARS or not e6:
        return _empty_result(snapshot, "MISSING_SETUP_CONTEXT")

    e6o = dict(e6.output or {})
    e4o = dict(e4.output or {}) if e4 else {}
    e3o = dict(e3.output or {}) if e3 else {}
    e5o = dict(e5.output or {}) if e5 else {}

    direction = _direction(e6o.get("direction", e6o.get("direction_thesis")))
    setup = _text(e6o.get("setup", e6o.get("setup_family"))) or "NONE"
    thesis = str(e6o.get("candidate_setup_thesis") or e6o.get("thesis") or "")
    c = _candle(bars)
    auction = _e4_context(e4o)

    supporting: list[str] = []
    counter: list[str] = []
    missing: list[str] = []
    next_required: list[str] = []
    invalidation: list[str] = []

    if direction not in {"BUY", "SELL"}:
        return EngineResult(
            "E7", NAME, False, 20.0,
            {
                **_base(snapshot),
                "state": "UNRESOLVED",
                "confirmation": "UNRESOLVED",
                "trigger_status": "NOT_EVALUATED",
                "direction": "NEUTRAL",
                "setup": setup,
                "candidate_setup_thesis": thesis,
                "trigger_observed": False,
                "confirmation_strength": "NONE",
                "confirmation_score": 20.0,
                "supporting_evidence": [],
                "counter_evidence": ["SETUP_DIRECTION_UNRESOLVED"],
                "missing_evidence": ["directional setup thesis"],
                "next_required_evidence": ["E6 must expose a resolved BUY/SELL thesis"],
                "invalidation": ["new closed candle changes the setup thesis"],
                "proof_gates": {"direction": False},
                "reasoning_trace": {"conclusion": "No directional thesis can be confirmed."},
            },
            ("SETUP_DIRECTION_UNRESOLVED",),
        )

    # Generic candle evidence is deliberately subordinate to the setup thesis.
    directional_close = bool(c["bullish"] if direction == "BUY" else c["bearish"])
    directional_close_location = bool(c["close_position"] >= 0.65 if direction == "BUY" else c["close_position"] <= 0.35)
    displacement = bool(c["bullish_displacement"] if direction == "BUY" else c["bearish_displacement"])
    engulf = bool(c["bullish_engulf"] if direction == "BUY" else c["bearish_engulf"])
    trigger_observed = directional_close and directional_close_location and (displacement or engulf)

    if directional_close:
        supporting.append("DIRECTIONAL_CLOSED_CANDLE")
    else:
        counter.append("CANDLE_DIRECTION_CONTRADICTS_THESIS")
    if directional_close_location:
        supporting.append("CLOSE_LOCATION_SUPPORTS_DIRECTION")
    else:
        counter.append("CLOSE_LOCATION_WEAK")
    if displacement:
        supporting.append(f"DIRECTIONAL_DISPLACEMENT={c['body_atr']:.3f}ATR")
    else:
        missing.append("meaningful_directional_displacement")
    if engulf:
        supporting.append("ENGULFING_RESPONSE")

    # Structural context is corroboration, not an independent decision authority.
    structure_finding = _text(e3o.get("finding", e3o.get("structure_state")))
    structure_internal = _direction(e3o.get("internal_state", e3o.get("internal_count_state")))
    structure_external = _direction(e3o.get("external_state", e3o.get("external_count_state")))
    if structure_internal == direction or structure_external == direction:
        supporting.append("STRUCTURE_CORROBORATES_DIRECTION")
    elif structure_internal != "NEUTRAL" or structure_external != "NEUTRAL":
        counter.append("STRUCTURE_DIRECTION_CONFLICT")
    if "MIXED" in structure_finding or "TRANSITION" in structure_finding:
        counter.append("STRUCTURE_NOT_RESOLVED")

    # Location is used as a quality/counter-evidence check, never as a trade decision.
    available_space = _num(e5o.get("available_space_atr_long" if direction == "BUY" else "available_space_atr_short"))
    if available_space > 0:
        if available_space >= 0.75:
            supporting.append(f"STRUCTURAL_SPACE={available_space:.3f}ATR")
        else:
            counter.append("STRUCTURAL_SPACE_CONSTRAINED")
            missing.append("sufficient_structural_space")

    # Setup-specific proof requirements.
    setup_upper = setup.replace(" ", "_")
    setup_family = setup_upper
    if "LIQUIDITY_REVERSAL" in setup_family:
        proof_event = auction["event"] and any(x in auction["event"] for x in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM"))
        if proof_event:
            supporting.append("LIQUIDITY_EVENT_PRESENT")
        else:
            missing.append("liquidity_sweep_or_failed_break_reclaim")
        if auction["direction"] == direction:
            supporting.append("LIQUIDITY_RESPONSE_ALIGNS")
        elif auction["direction"] in {"BUY", "SELL"}:
            counter.append("LIQUIDITY_RESPONSE_CONFLICT")
        if auction["pending"] and not auction["terminal"]:
            counter.append("AUCTION_CONFIRMATION_PENDING")
            missing.append("terminal_auction_confirmation")
        if auction["level"]:
            level = auction["level"]
            if direction == "SELL":
                reclaimed = c["close"] < level
            else:
                reclaimed = c["close"] > level
            if reclaimed:
                supporting.append("LIQUIDITY_LEVEL_RECLAIMED_BY_CLOSE")
            else:
                missing.append("closed_candle_reclaim_of_liquidity_level")

    elif "BREAKOUT_RETEST" in setup_family:
        bos = _text(e3o.get("bos", e3o.get("break_of_structure")))
        if bos in {"BREAK", "BOS", "YES"}:
            supporting.append("STRUCTURE_BREAK_PRESENT")
        else:
            missing.append("confirmed_structure_break")
        if directional_close_location:
            supporting.append("BREAK_LEVEL_CLOSED_IN_DIRECTION")
        else:
            missing.append("closed_candle_acceptance_beyond_break_level")
        if displacement:
            supporting.append("RETEST_CONTINUATION_DISPLACEMENT")
        else:
            missing.append("continuation_after_retest")

    elif "BREAKOUT" in setup_family:
        bos = _text(e3o.get("bos", e3o.get("break_of_structure")))
        if bos in {"BREAK", "BOS", "YES"}:
            supporting.append("STRUCTURE_BREAK_PRESENT")
        else:
            missing.append("confirmed_structure_break")
        if directional_close_location:
            supporting.append("BREAK_ACCEPTANCE_CLOSE")
        else:
            missing.append("closed_candle_acceptance_beyond_level")
        if not displacement:
            missing.append("breakout_displacement")

    elif "TREND_PULLBACK" in setup_family:
        trend_state = _direction(e3o.get("trend_state", e3o.get("direction")))
        if trend_state == direction:
            supporting.append("TREND_DIRECTION_CORROBORATES")
        elif trend_state != "NEUTRAL":
            counter.append("TREND_DIRECTION_CONFLICT")
        if directional_close:
            supporting.append("PULLBACK_DIRECTIONAL_RESPONSE")
        else:
            missing.append("pullback_rejection_and_continuation")
        if not displacement:
            missing.append("continuation_displacement")

    elif "AUCTION_ACCEPTANCE_CONTINUATION" in setup_family:
        if auction["terminal"]:
            supporting.append("AUCTION_ACCEPTANCE_TERMINALLY_CONFIRMED")
        else:
            missing.append("terminal_auction_acceptance")
        if directional_close_location:
            supporting.append("ACCEPTANCE_CLOSE_SUPPORTS_DIRECTION")
        else:
            missing.append("directional_acceptance_close")
        if not displacement:
            missing.append("continuation_displacement")

    else:
        # Unknown setup: never silently promote a generic candle to confirmation.
        missing.append("setup_specific_confirmation_definition")
        counter.append("UNKNOWN_SETUP_CONFIRMATION_RULE")

    # Follow-through is evidence from the current closed candle relative to the prior close.
    follow_through = bool(c["higher_close"] if direction == "BUY" else c["lower_close"])
    if follow_through and directional_close:
        supporting.append("CLOSED_CANDLE_FOLLOW_THROUGH")
    elif not follow_through:
        missing.append("follow_through")

    # Freshness: an old event should not be promoted merely because a later candle looks good.
    if auction["event"] and auction["age"] <= 3:
        supporting.append(f"EVENT_FRESHNESS={auction['age']}BARS")
    elif auction["event"]:
        counter.append("LIQUIDITY_EVENT_STALE")
        missing.append("fresh_confirmation_to_event")

    # Explicit invalidation checks.
    if direction == "BUY" and c["bearish"] and c["close_position"] <= 0.35:
        invalidation.append("bearish_closed_candle_rejects_long_thesis")
    if direction == "SELL" and c["bullish"] and c["close_position"] >= 0.65:
        invalidation.append("bullish_closed_candle_rejects_short_thesis")
    if auction["direction"] in {"BUY", "SELL"} and auction["direction"] != direction:
        invalidation.append("auction_response_reverses_setup_direction")

    # Hard confirmation gates. A trigger is only confirmed when the thesis-specific proof is present.
    hard_conflict = bool(counter and any(x in counter for x in (
        "CANDLE_DIRECTION_CONTRADICTS_THESIS",
        "LIQUIDITY_RESPONSE_CONFLICT",
        "STRUCTURE_DIRECTION_CONFLICT",
        "TREND_DIRECTION_CONFLICT",
    )))
    invalidated = bool(invalidation) or hard_conflict

    required_missing = _dedupe(missing)
    support_count = len(_dedupe(supporting))
    counter_count = len(_dedupe(counter))
    score = 35.0 + min(40.0, support_count * 5.0) - min(30.0, counter_count * 6.0) - min(20.0, len(required_missing) * 3.0)
    if trigger_observed:
        score += 10.0
    if follow_through:
        score += 5.0
    score = max(0.0, min(100.0, score))

    # Confirmation is intentionally stricter than trigger detection.
    setup_specific_proof = False
    if "LIQUIDITY_REVERSAL" in setup_family:
        setup_specific_proof = (
            bool(auction["event"])
            and auction["direction"] == direction
            and not auction["pending"]
            and direction in {"BUY", "SELL"}
            and directional_close_location
            and (displacement or engulf)
        )
    elif "BREAKOUT_RETEST" in setup_family:
        setup_specific_proof = directional_close_location and displacement and _text(e3o.get("bos")) in {"BREAK", "BOS", "YES"}
    elif "BREAKOUT" in setup_family:
        setup_specific_proof = directional_close_location and displacement and _text(e3o.get("bos")) in {"BREAK", "BOS", "YES"}
    elif "TREND_PULLBACK" in setup_family:
        setup_specific_proof = directional_close and directional_close_location and displacement
    elif "AUCTION_ACCEPTANCE_CONTINUATION" in setup_family:
        setup_specific_proof = auction["terminal"] and directional_close_location and displacement

    confirmed = (
        direction in {"BUY", "SELL"}
        and trigger_observed
        and follow_through
        and setup_specific_proof
        and not invalidated
        and not required_missing
    )

    if invalidated:
        state = "INVALIDATED"
        trigger_status = "CONFLICTED"
        strength = "NONE"
    elif confirmed:
        state = "CONFIRMED"
        trigger_status = "CONFIRMED"
        strength = "STRONG" if score >= 80 else "MODERATE"
    elif trigger_observed or support_count >= 3:
        state = "DEVELOPING"
        trigger_status = "TRIGGER_OBSERVED_NOT_PROVEN"
        strength = "WEAK" if score < 60 else "MODERATE"
    else:
        state = "UNRESOLVED"
        trigger_status = "NOT_CONFIRMED"
        strength = "NONE"

    if not confirmed and direction in {"BUY", "SELL"}:
        next_required.extend(required_missing)
    if not next_required and state == "DEVELOPING":
        next_required.append("closed-candle evidence completing the setup-specific proof gates")

    gate = confirmed
    reason_codes: list[str] = []
    if gate:
        reason_codes.append("SETUP_SPECIFIC_CONFIRMATION_PROVEN")
    else:
        if trigger_observed:
            reason_codes.append("TRIGGER_OBSERVED_NOT_CONFIRMATION")
        if required_missing:
            reason_codes.append("PROOF_GATES_INCOMPLETE")
        if invalidated:
            reason_codes.append("CONFIRMATION_INVALIDATED")
        if not reason_codes:
            reason_codes.append("CONFIRMATION_NOT_PROVEN")

    trace = {
        "thesis": thesis,
        "setup_family": setup_family,
        "direction": direction,
        "trigger_observed": trigger_observed,
        "trigger_definition": "directional close + close location + displacement/engulfing",
        "follow_through": follow_through,
        "setup_specific_proof": setup_specific_proof,
        "counter_evidence_applied": _dedupe(counter),
        "missing_proof": required_missing,
        "confirmation_boundary": "E7 confirms proof of the setup thesis; E9 alone decides whether a trade is permitted.",
    }

    output = {
        **_base(snapshot),
        "state": state,
        "confirmation": state,
        "trigger_status": trigger_status,
        "direction": direction,
        "setup": setup,
        "setup_family": setup_family,
        "candidate_setup_thesis": thesis,
        "trigger_observed": trigger_observed,
        "trigger_type": (
            "BULLISH_DISPLACEMENT" if direction == "BUY" and displacement else
            "BEARISH_DISPLACEMENT" if direction == "SELL" and displacement else
            "BULLISH_ENGULFING" if direction == "BUY" and engulf else
            "BEARISH_ENGULFING" if direction == "SELL" and engulf else
            "NONE"
        ),
        "confirmation_strength": strength,
        "confirmation_score": round(score, 2),
        "candle_body": round(float(c["body"]), 8),
        "candle_range": round(float(c["range"]), 8),
        "body_atr": round(float(c["body_atr"]), 4),
        "close_position": round(float(c["close_position"]), 4),
        "follow_through": follow_through,
        "displacement": displacement,
        "auction_context": auction,
        "supporting_evidence": _dedupe(supporting),
        "counter_evidence": _dedupe(counter),
        "missing_evidence": required_missing,
        "next_required_evidence": _dedupe(next_required),
        "invalidation": _dedupe(invalidation + ["new closed candle materially invalidates the confirmation"]),
        "proof_gates": {
            "direction_resolved": direction in {"BUY", "SELL"},
            "directional_closed_candle": directional_close,
            "close_location": directional_close_location,
            "displacement_or_engulfing": displacement or engulf,
            "follow_through": follow_through,
            "setup_specific_proof": setup_specific_proof,
            "counter_evidence_clear": not invalidated,
        },
        "reasoning_trace": trace,
        "professional_reasoning": {
            "conclusion": state,
            "why_trigger_is_or_is_not_present": trigger_observed,
            "why_confirmation_is_or_is_not_proven": setup_specific_proof and not invalidated and not required_missing,
            "what_is_missing": required_missing,
            "what_can_invalidate": _dedupe(invalidation),
            "decision_boundary": "E7 is evidence/confirmation only; E9 retains trade decision authority.",
        },
    }

    return EngineResult("E7", NAME, gate, round(score, 2), output, tuple(_dedupe(reason_codes + counter + required_missing)))
