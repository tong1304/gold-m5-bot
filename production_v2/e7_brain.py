from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult


NAME = "Confirmation / Trigger Brain"
QUESTION = "Does the setup have a valid closed-candle confirmation, or what is still missing?"
ARCHITECTURE = "E7_PROFESSIONAL_SETUP_AWARE_CONFIRMATION_BRAIN_V2"
VERSION = "2.0"
ATR_PERIOD = 14
MIN_BARS = 5
FOLLOW_THROUGH_MAX_AGE = 3


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _dedupe(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values if v))


def _direction(value: Any) -> str:
    t = _text(value)
    if t in {"BUY", "BULLISH", "UP", "LONG", "BUYERS"}:
        return "BUY"
    if t in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS"}:
        return "SELL"
    return "NEUTRAL"


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


def _candle(bar: dict[str, Any], previous: dict[str, Any], atr: float) -> dict[str, float | bool]:
    o, h, l, c = (_num(bar.get(k)) for k in ("open", "high", "low", "close"))
    po, ph, pl, pc = (_num(previous.get(k)) for k in ("open", "high", "low", "close"))
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    pos = (c - l) / rng
    return {
        "open": o, "high": h, "low": l, "close": c,
        "prev_open": po, "prev_high": ph, "prev_low": pl, "prev_close": pc,
        "range": rng, "body": body, "body_atr": body / max(atr, 1e-9),
        "close_position": pos,
        "upper_wick": h - max(o, c), "lower_wick": min(o, c) - l,
        "bullish": c > o, "bearish": c < o,
        "bullish_engulf": o <= pc and c >= po and c > o,
        "bearish_engulf": o >= pc and c <= po and c < o,
        "bullish_displacement": c > o and body / max(atr, 1e-9) >= 0.55 and pos >= 0.65,
        "bearish_displacement": c < o and body / max(atr, 1e-9) >= 0.55 and pos <= 0.35,
        "higher_close": c > pc, "lower_close": c < pc,
    }


def _e4_context(e4: dict[str, Any]) -> dict[str, Any]:
    event = _text(e4.get("event", e4.get("finding")))
    state = _text(e4.get("auction_state", e4.get("state")))
    level = _num(e4.get("event_level"))
    age = max(0, int(_num(e4.get("event_age_bars"))))
    direction = _direction(e4.get("direction"))
    if direction == "NEUTRAL":
        if any(x in event for x in ("HIGH_FAILED_BREAK_RECLAIM", "HIGH_SWEEP_REJECTION")):
            direction = "SELL"
        elif any(x in event for x in ("LOW_FAILED_BREAK_RECLAIM", "LOW_SWEEP_REJECTION")):
            direction = "BUY"
        elif any(x in event for x in ("HIGH_ACCEPTANCE", "HIGH_BREAK")):
            direction = "BUY"
        elif any(x in event for x in ("LOW_ACCEPTANCE", "LOW_BREAK")):
            direction = "SELL"
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    return {
        "event": event, "state": state, "terminal": terminal,
        "pending": state == "PENDING" or "PENDING" in event,
        "age": age, "direction": direction, "level": level,
        "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""),
        "quality": _num(e4.get("auction_quality")),
    }


def _base(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "role": "CONFIRMATION_ANALYST", "reasoning_role": "CONFIRMATION_ANALYST",
        "decision_authority": "E9", "trade_decision_authority": False,
        "closed_candle_only": True, "lookahead": False,
        "bar_count": len(snapshot.get("bars") or []),
    }


def _empty_result(snapshot: dict[str, Any], reason: str) -> EngineResult:
    output = {
        **_base(snapshot), "state": "WAIT", "confirmation": "UNRESOLVED",
        "trigger_status": "NOT_EVALUATED", "direction": "NEUTRAL", "setup": "NONE",
        "trigger_observed": False, "confirmation_strength": "NONE", "confirmation_score": 0.0,
        "supporting_evidence": [], "counter_evidence": [reason],
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
    atr = max(_atr(bars), 1e-9)
    c = _candle(bars[-1], bars[-2], atr)
    prev = _candle(bars[-2], bars[-3], atr) if len(bars) >= 3 else c
    auction = _e4_context(e4o)

    supporting: list[str] = []
    counter: list[str] = []
    missing: list[str] = []
    invalidation: list[str] = []

    if direction not in {"BUY", "SELL"}:
        output = {
            **_base(snapshot), "state": "UNRESOLVED", "confirmation": "UNRESOLVED",
            "trigger_status": "NOT_EVALUATED", "direction": "NEUTRAL", "setup": setup,
            "candidate_setup_thesis": thesis, "trigger_observed": False,
            "confirmation_strength": "NONE", "confirmation_score": 20.0,
            "supporting_evidence": [], "counter_evidence": ["SETUP_DIRECTION_UNRESOLVED"],
            "missing_evidence": ["directional setup thesis"],
            "next_required_evidence": ["E6 must expose a resolved BUY/SELL thesis"],
            "invalidation": ["new closed candle changes the setup thesis"],
            "proof_gates": {"direction_resolved": False},
            "reasoning_trace": {"conclusion": "No directional thesis can be confirmed."},
        }
        return EngineResult("E7", NAME, False, 20.0, output, ("SETUP_DIRECTION_UNRESOLVED",))

    bullish = direction == "BUY"
    directional_close = bool(c["bullish"] if bullish else c["bearish"])
    close_location = bool(c["close_position"] >= 0.65 if bullish else c["close_position"] <= 0.35)
    displacement = bool(c["bullish_displacement"] if bullish else c["bearish_displacement"])
    engulf = bool(c["bullish_engulf"] if bullish else c["bearish_engulf"])
    trigger_observed = directional_close and close_location and (displacement or engulf)

    if directional_close: supporting.append("DIRECTIONAL_CLOSED_CANDLE")
    else: counter.append("CANDLE_DIRECTION_CONTRADICTS_THESIS")
    if close_location: supporting.append("CLOSE_LOCATION_SUPPORTS_DIRECTION")
    else: counter.append("CLOSE_LOCATION_WEAK")
    if displacement: supporting.append(f"DIRECTIONAL_DISPLACEMENT={c['body_atr']:.3f}ATR")
    else: missing.append("meaningful_directional_displacement")
    if engulf: supporting.append("ENGULFING_RESPONSE")

    internal = _direction(e3o.get("internal_state", e3o.get("internal_count_state")))
    external = _direction(e3o.get("external_state", e3o.get("external_count_state")))
    structure_finding = _text(e3o.get("finding", e3o.get("structure_state")))
    if internal == direction: supporting.append("INTERNAL_STRUCTURE_CORROBORATES")
    elif internal != "NEUTRAL": counter.append("INTERNAL_STRUCTURE_CONFLICT")
    if external == direction: supporting.append("EXTERNAL_STRUCTURE_CORROBORATES")
    elif external != "NEUTRAL": counter.append("EXTERNAL_STRUCTURE_CONFLICT")
    if "MIXED" in structure_finding or "TRANSITION" in structure_finding:
        counter.append("STRUCTURE_NOT_RESOLVED")

    space = _num(e5o.get("available_space_atr_long" if bullish else "available_space_atr_short"))
    if space > 0 and space >= 0.75:
        supporting.append(f"STRUCTURAL_SPACE={space:.3f}ATR")
    elif space > 0:
        counter.append("STRUCTURAL_SPACE_CONSTRAINED")
        missing.append("sufficient_structural_space")

    family = setup.replace(" ", "_")
    setup_proof: dict[str, str] = {}

    def gate(name: str, value: bool, fail: str) -> None:
        setup_proof[name] = "PASS" if value else "FAIL"
        if value: supporting.append(name.upper())
        else: missing.append(fail)

    if "LIQUIDITY_REVERSAL" in family:
        event_ok = bool(auction["event"] and any(x in auction["event"] for x in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM")))
        gate("liquidity_event", event_ok, "liquidity_sweep_or_failed_break_reclaim")
        response_ok = auction["direction"] == direction
        if response_ok: supporting.append("LIQUIDITY_RESPONSE_ALIGNS")
        elif auction["direction"] in {"BUY", "SELL"}: counter.append("LIQUIDITY_RESPONSE_CONFLICT")
        setup_proof["liquidity_response"] = "PASS" if response_ok else ("FAIL" if auction["direction"] in {"BUY", "SELL"} else "PENDING")
        if auction["pending"] and not auction["terminal"]:
            counter.append("AUCTION_CONFIRMATION_PENDING")
            missing.append("terminal_auction_confirmation")
            setup_proof["auction_terminality"] = "PENDING"
        else:
            setup_proof["auction_terminality"] = "PASS" if auction["terminal"] else "FAIL"
        if auction["level"]:
            reclaimed = c["close"] < auction["level"] if not bullish else c["close"] > auction["level"]
            setup_proof["level_reclaim"] = "PASS" if reclaimed else "FAIL"
            if reclaimed: supporting.append("LIQUIDITY_LEVEL_RECLAIMED_BY_CLOSE")
            else: missing.append("closed_candle_reclaim_of_liquidity_level")
        else:
            setup_proof["level_reclaim"] = "UNAVAILABLE"

    elif "BREAKOUT_RETEST" in family or "BREAKOUT" in family:
        bos = _text(e3o.get("bos", e3o.get("break_of_structure"))) in {"BREAK", "BOS", "YES"}
        gate("structure_break", bos, "confirmed_structure_break")
        gate("break_acceptance_close", close_location, "closed_candle_acceptance_beyond_level")
        gate("breakout_displacement", displacement, "breakout_displacement")
        if "BREAKOUT_RETEST" in family:
            setup_proof["retest_continuation"] = "PASS" if displacement else "PENDING"
            if not displacement: missing.append("continuation_after_retest")

    elif "TREND_PULLBACK" in family:
        trend = _direction(e3o.get("trend_state", e3o.get("direction")))
        gate("trend_alignment", trend == direction, "trend_direction_alignment")
        gate("pullback_response", directional_close, "pullback_rejection_and_continuation")
        gate("continuation_displacement", displacement, "continuation_displacement")

    elif "AUCTION_ACCEPTANCE_CONTINUATION" in family:
        gate("terminal_auction_acceptance", auction["terminal"], "terminal_auction_acceptance")
        gate("directional_acceptance_close", close_location, "directional_acceptance_close")
        gate("continuation_displacement", displacement, "continuation_displacement")
    else:
        missing.append("setup_specific_confirmation_definition")
        counter.append("UNKNOWN_SETUP_CONFIRMATION_RULE")
        setup_proof["setup_definition"] = "FAIL"

    # Confirmation lifecycle: the latest candle can be the trigger, but it cannot also be
    # treated as its own future follow-through. Follow-through requires a subsequent close.
    previous_trigger = bool(
        prev["bullish"] if bullish else prev["bearish"
    ]) and bool(prev["close_position"] >= 0.65 if bullish else prev["close_position"] <= 0.35) and bool(
        prev["bullish_displacement"] if bullish else prev["bearish_displacement"]
    )
    if previous_trigger and directional_close:
        follow_state = "PASS"
        supporting.append("FOLLOW_THROUGH_CONFIRMED")
    elif trigger_observed:
        follow_state = "PENDING"
        missing.append("follow_through")
    elif previous_trigger and not directional_close:
        follow_state = "FAIL"
        counter.append("FOLLOW_THROUGH_FAILED")
    else:
        follow_state = "NOT_ESTABLISHED"
        missing.append("follow_through")

    if auction["event"]:
        if auction["age"] <= FOLLOW_THROUGH_MAX_AGE:
            supporting.append(f"EVENT_FRESHNESS={auction['age']}BARS")
        else:
            counter.append("LIQUIDITY_EVENT_STALE")
            missing.append("fresh_confirmation_to_event")

    if bullish and c["bearish"] and c["close_position"] <= 0.35:
        invalidation.append("bearish_closed_candle_rejects_long_thesis")
    if not bullish and c["bullish"] and c["close_position"] >= 0.65:
        invalidation.append("bullish_closed_candle_rejects_short_thesis")
    if auction["direction"] in {"BUY", "SELL"} and auction["direction"] != direction:
        invalidation.append("auction_response_reverses_setup_direction")

    hard_conflict = any(x in counter for x in (
        "CANDLE_DIRECTION_CONTRADICTS_THESIS", "LIQUIDITY_RESPONSE_CONFLICT",
        "INTERNAL_STRUCTURE_CONFLICT", "EXTERNAL_STRUCTURE_CONFLICT",
    ))
    invalidated = bool(invalidation) or hard_conflict

    # Hard proof is intentionally stricter than trigger detection. A trigger is not a confirmation.
    setup_specific = all(v == "PASS" for v in setup_proof.values()) if setup_proof else False
    confirmed = bool(trigger_observed and setup_specific and follow_state == "PASS" and not invalidated)

    support_count = len(_dedupe(supporting))
    counter_count = len(_dedupe(counter))
    missing_count = len(_dedupe(missing))
    score = 30.0 + min(45.0, support_count * 5.0) - min(30.0, counter_count * 6.0) - min(20.0, missing_count * 2.5)
    if trigger_observed: score += 10.0
    if follow_state == "PASS": score += 10.0
    score = max(0.0, min(100.0, score))

    if invalidated:
        state, trigger_status, strength = "INVALIDATED", "CONFLICTED", "NONE"
    elif confirmed:
        state, trigger_status = "CONFIRMED", "CONFIRMED"
        strength = "STRONG" if score >= 80 else "MODERATE"
    elif trigger_observed or previous_trigger or support_count >= 3:
        state, trigger_status = "DEVELOPING", "TRIGGER_OBSERVED_NOT_PROVEN"
        strength = "MODERATE" if score >= 60 else "WEAK"
    else:
        state, trigger_status, strength = "UNRESOLVED", "NOT_CONFIRMED", "NONE"

    required_missing = _dedupe(missing)
    next_required = required_missing[:]
    if not confirmed and not next_required:
        next_required = ["closed-candle evidence completing the setup-specific proof gates"]

    reasons: list[str] = []
    if confirmed: reasons.append("SETUP_SPECIFIC_CONFIRMATION_PROVEN")
    else:
        if trigger_observed: reasons.append("TRIGGER_OBSERVED_NOT_CONFIRMATION")
        if required_missing: reasons.append("PROOF_GATES_INCOMPLETE")
        if invalidated: reasons.append("CONFIRMATION_INVALIDATED")
        if not reasons: reasons.append("CONFIRMATION_NOT_PROVEN")

    gate_states = {
        "direction_resolved": "PASS",
        "directional_closed_candle": "PASS" if directional_close else "FAIL",
        "close_location": "PASS" if close_location else "FAIL",
        "displacement_or_engulfing": "PASS" if (displacement or engulf) else "FAIL",
        "setup_specific_proof": "PASS" if setup_specific else "FAIL",
        "follow_through": follow_state,
        "counter_evidence_clear": "PASS" if not invalidated else "FAIL",
    }
    trace = {
        "thesis": thesis, "setup_family": family, "direction": direction,
        "lifecycle": "TRIGGER" if trigger_observed and follow_state == "PENDING" else ("FOLLOW_THROUGH" if follow_state == "PASS" else state),
        "trigger_observed": trigger_observed,
        "trigger_definition": "directional closed candle + close location + displacement/engulfing",
        "follow_through_state": follow_state,
        "setup_proof": setup_proof,
        "counter_evidence_applied": _dedupe(counter),
        "missing_proof": required_missing,
        "next_required_evidence": next_required,
        "confirmation_boundary": "E7 proves evidence for the E6 thesis; E9 alone decides whether a trade is permitted.",
    }
    output = {
        **_base(snapshot), "state": state, "confirmation": state,
        "trigger_status": trigger_status, "direction": direction, "setup": setup,
        "setup_family": family, "candidate_setup_thesis": thesis,
        "trigger_observed": trigger_observed,
        "trigger_type": (
            "BULLISH_DISPLACEMENT" if bullish and displacement else
            "BEARISH_DISPLACEMENT" if not bullish and displacement else
            "BULLISH_ENGULFING" if bullish and engulf else
            "BEARISH_ENGULFING" if not bullish and engulf else "NONE"
        ),
        "confirmation_strength": strength, "confirmation_score": round(score, 2),
        "candle_body": round(float(c["body"]), 8), "candle_range": round(float(c["range"]), 8),
        "body_atr": round(float(c["body_atr"]), 4), "close_position": round(float(c["close_position"]), 4),
        "follow_through": follow_state == "PASS", "follow_through_state": follow_state,
        "displacement": displacement, "auction_context": auction,
        "supporting_evidence": _dedupe(supporting), "counter_evidence": _dedupe(counter),
        "missing_evidence": required_missing, "next_required_evidence": next_required,
        "invalidation": _dedupe(invalidation + ["new closed candle materially invalidates the confirmation"]),
        "proof_gates": gate_states, "setup_proof": setup_proof, "reasoning_trace": trace,
        "professional_reasoning": {
            "conclusion": state,
            "why_trigger_is_or_is_not_present": trigger_observed,
            "why_confirmation_is_or_is_not_proven": confirmed,
            "what_is_missing": required_missing,
            "what_can_invalidate": _dedupe(invalidation),
            "decision_boundary": "E7 is evidence/confirmation only; E9 retains trade decision authority.",
        },
    }
    return EngineResult("E7", NAME, confirmed, round(score, 2), output, tuple(_dedupe(reasons + counter + required_missing)))
