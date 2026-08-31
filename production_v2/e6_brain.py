from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V36"
VERSION = "36.0"
MIN_BARS = 60
ATR_PERIOD = 14
MIN_SPACE_ATR = 0.75
MAX_EVENT_AGE_BARS = 3

SETUP_FAMILIES = (
    "LIQUIDITY_REVERSAL",
    "AUCTION_ACCEPTANCE_CONTINUATION",
    "BREAKOUT_RETEST",
    "TREND_PULLBACK",
    "BREAKOUT",
    "IMPULSE_CONTINUATION",
)
LIFECYCLE = ("ABSENT", "FORMING", "VALIDATING", "MATURE", "FAILED", "INVALIDATED", "EXPIRED")
UNRESOLVED = {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS", "WAIT", "EMERGING", "PENDING"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _norm(value: Any) -> str:
    x = _text(value)
    if x in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"}:
        return "BUY"
    if x in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"}:
        return "SELL"
    return "NEUTRAL"


def _dedupe(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values if v))


def _payload(upstream: dict[str, EngineResult], engine_id: str) -> dict[str, Any]:
    result = upstream.get(engine_id)
    return dict(result.output or {}) if result else {}


def _atr(bars: list[dict[str, Any]]) -> float:
    if len(bars) < 2:
        return 0.0
    sample = bars[-(ATR_PERIOD + 1):]
    trs: list[float] = []
    for i, candle in enumerate(sample):
        high, low = _num(candle.get("high")), _num(candle.get("low"))
        if i == 0:
            trs.append(max(0.0, high - low))
            continue
        prev = _num(sample[i - 1].get("close"))
        trs.append(max(high - low, abs(high - prev), abs(low - prev)))
    return mean(trs[-ATR_PERIOD:]) if trs else 0.0


def _auction(e4: dict[str, Any]) -> dict[str, Any]:
    event = _text(e4.get("event", e4.get("finding")))
    state = _text(e4.get("auction_state", e4.get("state")))
    age = max(0, int(_num(e4.get("event_age_bars"))))
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED", "RECLAIMED"} or "TERMINAL" in state
    direction = _norm(e4.get("direction"))
    if direction == "NEUTRAL":
        if any(x in event for x in ("HIGH_SWEEP_REJECTION", "HIGH_FAILED_BREAK_RECLAIM", "HIGH_REJECTION")):
            direction = "SELL"
        elif any(x in event for x in ("LOW_SWEEP_REJECTION", "LOW_FAILED_BREAK_RECLAIM", "LOW_REJECTION")):
            direction = "BUY"
        elif any(x in event for x in ("HIGH_ACCEPTANCE", "HIGH_BREAK")):
            direction = "BUY"
        elif any(x in event for x in ("LOW_ACCEPTANCE", "LOW_BREAK")):
            direction = "SELL"
    return {
        "event": event, "state": state, "direction": direction, "terminal": terminal,
        "pending": state == "PENDING" or "PENDING" in event, "age_bars": age,
        "level": _num(e4.get("event_level")),
        "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""),
        "response_actor": _text(e4.get("response_actor")),
    }


def _structure(e3: dict[str, Any]) -> tuple[str, str, str]:
    finding = _text(e3.get("finding", e3.get("structure_state")))
    internal = _norm(e3.get("internal_state", e3.get("internal_count_state")))
    external = _norm(e3.get("external_state", e3.get("external_count_state")))
    return finding, internal, external


def _e2_unresolved(e2: dict[str, Any]) -> bool:
    finding = _text(e2.get("finding", e2.get("state")))
    state = _text(e2.get("opportunity_state", e2.get("opportunity_decision")))
    maturity = _text(e2.get("opportunity_maturity"))
    return finding in UNRESOLVED or state in UNRESOLVED or maturity in {"UNPROVEN", "EMERGING"}


def _e3_invalidated(e3: dict[str, Any]) -> bool:
    lifecycle = _text(e3.get("lifecycle"))
    invalidation = _text(e3.get("invalidation"))
    finding = _text(e3.get("finding"))
    return bool(
        e3.get("structure_invalidated") is True
        or e3.get("active_invalidation") is True
        or lifecycle == "INVALIDATED"
        or invalidation in {"ACTIVE_INVALIDATION", "STRUCTURE_INVALIDATED", "BULLISH_STRUCTURE_INVALIDATED", "BEARISH_STRUCTURE_INVALIDATED"}
        or finding.endswith("_INVALIDATED")
    )


def _direction(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any]) -> tuple[str, list[str], list[str], str]:
    auction = _auction(e4)
    pressure = _norm(e1.get("directional_pressure", e1.get("pressure")))
    _, internal, external = _structure(e3)
    support: list[str] = []
    conflicts: list[str] = []
    for label, value in (("E1_PRESSURE", pressure), ("E3_INTERNAL", internal), ("E3_EXTERNAL", external), ("E4_AUCTION", auction["direction"])):
        if value != "NEUTRAL":
            support.append(f"{label}={value}")
    if internal != "NEUTRAL" and external != "NEUTRAL" and internal != external:
        conflicts.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    if pressure != "NEUTRAL" and auction["direction"] != "NEUTRAL" and pressure != auction["direction"] and auction["terminal"]:
        conflicts.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    if pressure != "NEUTRAL" and internal == pressure:
        return pressure, _dedupe(support), _dedupe(conflicts), "E1_E3_DIRECTIONAL_CORE"
    if internal != "NEUTRAL" and internal == external:
        return internal, _dedupe(support), _dedupe(conflicts), "E3_STRUCTURE_CONVERGENCE"
    if pressure != "NEUTRAL":
        return pressure, _dedupe(support), _dedupe(conflicts), "E1_CONTEXT_DIRECTION"
    if internal != "NEUTRAL":
        return internal, _dedupe(support), _dedupe(conflicts), "E3_STRUCTURE_DIRECTION"
    if auction["direction"] != "NEUTRAL":
        return auction["direction"], _dedupe(support), _dedupe(conflicts), "E4_AUCTION_HYPOTHESIS"
    return "NEUTRAL", _dedupe(support), _dedupe(conflicts), "NO_DIRECTIONAL_THESIS"


def _candidate(direction: str, auction: dict[str, Any], e1: dict[str, Any], e3: dict[str, Any], e5: dict[str, Any]) -> tuple[str, float, list[str]] | None:
    event = auction["event"]
    event_direction = auction["direction"]
    trend = _norm(e1.get("trend_state"))
    finding = _text(e1.get("finding", e1.get("trend_state")))
    bos = _text(e3.get("bos", e3.get("break_of_structure")))
    repricing = _text(e5.get("repricing_state"))
    value_response = _text(e5.get("value_response"))
    location = _text(e5.get("structural_location"))

    if direction == "NEUTRAL":
        return None
    if auction["terminal"] and event_direction == direction and any(x in event for x in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM")):
        return "LIQUIDITY_REVERSAL", 84.0, ["E4_TERMINAL_LIQUIDITY_RESPONSE"]
    if auction["terminal"] and event_direction == direction and "ACCEPTANCE" in event:
        return "AUCTION_ACCEPTANCE_CONTINUATION", 80.0, ["E4_TERMINAL_AUCTION_ACCEPTANCE"]
    if any(x in event for x in ("BREAKOUT", "BOS")) or bos in {"BREAK", "BOS", "YES"}:
        return "BREAKOUT_RETEST", 70.0, ["E3_BREAK_EVENT"]
    if trend == direction and ("TREND" in finding or "PULLBACK" in finding):
        return "TREND_PULLBACK", 62.0, ["E1_TREND_ALIGNMENT"]
    if repricing or value_response or location:
        return "IMPULSE_CONTINUATION", 58.0, ["E1_DIRECTIONAL_CONTEXT", "E3_STRUCTURE_CONTEXT", "E5_LOCATION_CONTEXT"]
    return None


def _identity(setup: str, direction: str, auction: dict[str, Any], e5: dict[str, Any]) -> tuple[str, str]:
    if auction["event_id"]:
        return f"{setup}:{direction}:{auction['event_id']}", "E4_EVENT_ID"
    if auction["level"]:
        return f"{setup}:{direction}:LEVEL:{auction['level']:.5f}", "E4_EVENT_LEVEL"
    return f"{setup}:{direction}:VALUE:{_num(e5.get('value_distance_atr')):.3f}", "E5_VALUE_CONTEXT"


def _result(**kwargs: Any) -> EngineResult:
    support = _dedupe(kwargs.get("support", []))
    counter = _dedupe(kwargs.get("counter", []))
    missing = _dedupe(kwargs.get("missing", []))
    invalidation = _dedupe(kwargs.get("invalidation", []))
    secondary = _dedupe(kwargs.get("secondary_blockers", []))
    primary = str(kwargs.get("primary_blocker", "NONE"))
    reasons = _dedupe(([primary] if primary != "NONE" else []) + secondary)
    setup = str(kwargs.get("setup", "NONE"))
    thesis = str(kwargs.get("thesis", ""))
    state = str(kwargs.get("state", "NO_SETUP"))
    direction = str(kwargs.get("direction", "NEUTRAL"))
    quality = round(max(0.0, min(100.0, float(kwargs.get("quality", 0.0)))), 2)
    confidence = round(max(0.0, min(100.0, float(kwargs.get("confidence", 0.0)))), 2)
    trace = dict(kwargs.get("trace", {}))
    observations = _dedupe(kwargs.get("observations", []))
    candidates = kwargs.get("candidates", [])
    out = {
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "question": QUESTION,
        "role": "SETUP_FORMATION_REASONER",
        "reasoning_role": "SETUP_FORMATION_REASONER",
        "decision_authority": "E9",
        "trade_decision_authority": False,
        "state": state,
        "setup_state": state,
        "finding": thesis,
        "setup": setup,
        "setup_family": setup,
        "candidate_setup": setup,
        "candidate_setup_thesis": thesis,
        "candidate_setup_identity": trace.get("candidate_identity"),
        "candidate_identity_basis": trace.get("candidate_identity_basis"),
        "direction": direction,
        "direction_thesis": thesis,
        "direction_source": trace.get("direction_source"),
        "stage": state,
        "formation_stage": state,
        "lifecycle": state,
        "lifecycle_states": list(LIFECYCLE),
        "maturity": kwargs.get("maturity", "UNRESOLVED"),
        "thesis": thesis,
        "thesis_owner": "E6",
        "setup_exists": bool(kwargs.get("exists", False)),
        "trade_ready": False,
        "trade_readiness": "NOT_READY",
        "setup_quality": quality,
        "confidence": confidence,
        "observations": observations,
        "candidate_setups": [c.get("name") for c in candidates],
        "candidate_states": candidates,
        "selected_hypothesis": setup if kwargs.get("exists", False) else None,
        "rejected_hypotheses": kwargs.get("rejected", []),
        "rejected_setups": kwargs.get("rejected", []),
        "supporting_evidence": support,
        "counter_evidence": counter,
        "missing_evidence": missing,
        "missing_proof": missing,
        "next_required_evidence": missing,
        "next_required_event": kwargs.get("next_event", "REASSESS_NEXT_CLOSED_CANDLE"),
        "invalidation": invalidation,
        "evidence_ledger": kwargs.get("ledger", []),
        "reasoning_trace": trace,
        "reason_codes": reasons,
        "primary_blocker": primary,
        "secondary_blockers": secondary,
        "conflict_ledger": counter,
        "governance_blockers": reasons,
        "professional_reasoning": {
            "conclusion": thesis,
            "selected_hypothesis": setup if kwargs.get("exists", False) else None,
            "why_it_is_forming": support,
            "what_is_wrong_with_the_thesis": counter,
            "what_is_missing": missing,
            "what_must_happen_next": kwargs.get("next_event", "REASSESS_NEXT_CLOSED_CANDLE"),
            "what_invalidates_it": invalidation,
            "formation_stage": state,
            "maturity": kwargs.get("maturity", "UNRESOLVED"),
            "setup_quality": quality,
            "confidence": confidence,
            "primary_blocker": primary,
            "secondary_blockers": secondary,
            "decision_boundary": "E6 describes and stages the setup; E9 alone decides whether a trade is permitted.",
        },
    }
    return EngineResult("E6", NAME, False, quality, out, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _result(state="ABSENT", setup="NONE", direction="NEUTRAL", maturity="UNRESOLVED", thesis="Insufficient closed-candle evidence.", quality=0, confidence=100, exists=False, observations=[f"valid_candles={len(bars)}"], counter=["INSUFFICIENT_HISTORY"], missing=[f"AT_LEAST_{MIN_BARS}_VALID_CLOSED_CANDLES"], next_event=f"WAIT_FOR_{MIN_BARS}_VALID_CLOSED_CANDLES", invalidation=["insufficient_history"], primary_blocker="CAUSAL_SETUP_PROOF_INCOMPLETE")
    try:
        if _atr(bars) <= 0:
            raise ValueError
        for candle in bars[-MIN_BARS:]:
            for key in ("open", "high", "low", "close"):
                value = float(candle[key])
                if value != value:
                    raise ValueError
    except (KeyError, TypeError, ValueError):
        return _result(state="ABSENT", setup="NONE", direction="NEUTRAL", maturity="UNRESOLVED", thesis="Invalid closed-candle OHLC.", quality=0, confidence=100, exists=False, observations=["ohlc_validation=FAILED"], counter=["INVALID_MARKET_DATA"], missing=["VALID_CLOSED_CANDLE_OHLC"], next_event="WAIT_FOR_VALID_CLOSED_CANDLE_DATA", invalidation=["invalid_market_data"], primary_blocker="CAUSAL_SETUP_PROOF_INCOMPLETE")

    e1, e2, e3, e4, e5 = (_payload(upstream, key) for key in ("E1", "E2", "E3", "E4", "E5"))
    if _e3_invalidated(e3):
        finding = _text(e3.get("finding", "STRUCTURE_INVALIDATED"))
        return _result(state="INVALIDATED", setup="NONE", direction="NEUTRAL", maturity="INVALIDATED", thesis="No setup survives because E3 explicitly invalidated the active market structure.", quality=0, confidence=100, exists=False, observations=["E3_STRUCTURE_INVALIDATED", finding], counter=["E3_STRUCTURE_INVALIDATED"], missing=["NEW_VALID_CLOSED_CANDLE_STRUCTURE_LIFECYCLE"], next_event="E3_NEW_VALID_STRUCTURE_LIFECYCLE", invalidation=[finding], primary_blocker="E3_STRUCTURE_INVALIDATED")

    auction = _auction(e4)
    direction, direction_support, direction_conflicts, direction_source = _direction(e1, e2, e3, e4)
    structure_finding, internal, external = _structure(e3)
    e2_unresolved = _e2_unresolved(e2)
    space_key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    space = _num(e5.get(space_key)) if direction in {"BUY", "SELL"} else 0.0
    blockers = list(direction_conflicts)
    if direction == "NEUTRAL": blockers.append("DIRECTION_UNRESOLVED")
    if e2_unresolved: blockers.append("E2_OPPORTUNITY_UNRESOLVED")
    if auction["pending"] and not auction["terminal"]: blockers.append("AUCTION_CONFIRMATION_PENDING")
    if auction["age_bars"] > MAX_EVENT_AGE_BARS and auction["event"]: blockers.append("STALE_AUCTION_EVENT")
    if internal != "NEUTRAL" and external != "NEUTRAL" and internal != external: blockers.append("STRUCTURE_CONFLICT")
    if "MIXED" in structure_finding or "TRANSITION" in structure_finding: blockers.append("STRUCTURE_CONFLICT")
    if direction in {"BUY", "SELL"} and space < MIN_SPACE_ATR: blockers.append("SPACE_CONFLICT")
    blockers = _dedupe(blockers)

    candidate = _candidate(direction, auction, e1, e3, e5)
    if candidate is None:
        obs = direction_support + [f"auction={auction['event'] or 'NONE'}", f"auction_state={auction['state'] or 'NONE'}", f"space_atr={space:.3f}"]
        return _result(state="ABSENT", setup="NONE", direction=direction, maturity="UNRESOLVED", thesis="No causal setup hypothesis survives current closed-candle evidence.", quality=0, confidence=60, exists=False, observations=obs, support=direction_support, counter=blockers, missing=["causal_setup_chain"], next_event="WAIT_FOR_NEW_CLOSED_CANDLE_SETUP_EVIDENCE", primary_blocker=next((x for x in ("DIRECTION_UNRESOLVED", "E2_OPPORTUNITY_UNRESOLVED", "DIRECTIONAL_EVIDENCE_CONFLICT", "SPACE_CONFLICT") if x in blockers), "CAUSAL_SETUP_PROOF_INCOMPLETE"))

    setup, base_quality, candidate_evidence = candidate
    identity, identity_basis = _identity(setup, direction, auction, e5)
    missing: list[str] = []
    counter = list(blockers)
    support = direction_support + candidate_evidence
    if e2_unresolved: missing.append("E2_CLOSED_CANDLE_OPPORTUNITY_ACCEPTANCE_AND_FOLLOW_THROUGH")
    if auction["pending"] and not auction["terminal"]: missing.append("TERMINAL_AUCTION_CONFIRMATION")
    if direction in {"BUY", "SELL"} and space < MIN_SPACE_ATR: missing.append(f"STRUCTURAL_SPACE_{MIN_SPACE_ATR:.2f}_ATR")
    if internal != external or internal == "NEUTRAL" or external == "NEUTRAL": missing.append("STRUCTURE_DIRECTIONAL_RESOLUTION")
    if not auction["event"]: missing.append("SETUP_SPECIFIC_TRIGGER_EVENT")

    # Space is a trade-economics constraint, not an automatic thesis invalidation.
    # E6 keeps the causal thesis alive and exposes the constraint to E8/E9.
    proof_core = direction in {"BUY", "SELL"} and bool(auction["event"] or direction_support) and not any(x == "DIRECTIONAL_EVIDENCE_CONFLICT" for x in blockers)
    response_observed = bool(auction["response_actor"] and auction["response_actor"] not in {"UNKNOWN", "NONE"})
    if setup == "IMPULSE_CONTINUATION":
        support.append("CONTINUATION_CONTEXT_PRESENT")
        missing.append("CLOSED_CANDLE_FOLLOW_THROUGH_FOR_CONTINUATION")
    if response_observed: support.append(f"E4_RESPONSE_ACTOR={auction['response_actor']}")
    else: missing.append("CLOSED_CANDLE_RESPONSE_CONFIRMATION")
    support = _dedupe(support)
    missing = _dedupe(missing)
    counter = _dedupe(counter)

    if not proof_core:
        stage, maturity, confidence = "FORMING", "FORMING", 55.0
    elif auction["terminal"] and not e2_unresolved and space >= MIN_SPACE_ATR and not blockers:
        stage, maturity, confidence = "MATURE", "MATURE", 90.0
    else:
        stage, maturity, confidence = "VALIDATING", "VALIDATING", 72.0

    quality = max(0.0, min(100.0, base_quality + (6 if response_observed else 0) + (5 if space >= MIN_SPACE_ATR else -8) - (8 if e2_unresolved else 0)))
    primary = "NONE" if stage == "MATURE" else next((x for x in ("E2_OPPORTUNITY_UNRESOLVED", "AUCTION_CONFIRMATION_PENDING", "SPACE_CONFLICT", "STRUCTURE_CONFLICT", "DIRECTIONAL_EVIDENCE_CONFLICT") if x in blockers), "CAUSAL_SETUP_PROOF_INCOMPLETE")
    next_event = {
        "E2_OPPORTUNITY_UNRESOLVED": "E2_CLOSED_CANDLE_OPPORTUNITY_ACCEPTANCE_AND_FOLLOW_THROUGH",
        "AUCTION_CONFIRMATION_PENDING": "E4_TERMINAL_AUCTION_CONFIRMATION",
        "SPACE_CONFLICT": "E5_STRUCTURAL_SPACE_REOPENS_ABOVE_MINIMUM",
        "STRUCTURE_CONFLICT": "E3_STRUCTURE_RESOLUTION_ON_CLOSED_CANDLE",
        "DIRECTIONAL_EVIDENCE_CONFLICT": "NEW_CLOSED_CANDLE_DIRECTIONAL_RESOLUTION",
    }.get(primary, "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION")
    thesis = f"{direction} {setup} is {stage.lower()}: the causal thesis is retained, while remaining proof and economic constraints are explicitly exposed."
    observations = [
        f"direction={direction}",
        f"direction_source={direction_source}",
        f"setup={setup}",
        f"formation_stage={stage}",
        f"auction={auction['event'] or 'NONE'}",
        f"auction_state={auction['state'] or 'NONE'}",
        f"auction_terminal={auction['terminal']}",
        f"space_atr={space:.3f}",
        f"e2_unresolved={e2_unresolved}",
        f"structure_internal={internal}",
        f"structure_external={external}",
    ]
    ledger = [
        {"source": "E1", "kind": "CONTEXT", "statement": _text(e1.get("finding", "NONE"))},
        {"source": "E2", "kind": "OPPORTUNITY", "statement": _text(e2.get("finding", "NONE")), "unresolved": e2_unresolved},
        {"source": "E3", "kind": "STRUCTURE", "statement": structure_finding or "NONE"},
        {"source": "E4", "kind": "AUCTION", "statement": auction["event"] or "NONE", "state": auction["state"]},
        {"source": "E5", "kind": "LOCATION", "space_atr": space},
    ]
    trace = {
        "summary": f"E1->E2->E3->E4->E5->E6:{stage}",
        "decision": "DESCRIBE_SETUP_ONLY",
        "selected_hypothesis": setup,
        "candidate_identity": identity,
        "candidate_identity_basis": identity_basis,
        "direction_source": direction_source,
        "thesis_status": "ALIVE" if stage in {"FORMING", "VALIDATING", "MATURE"} else stage,
        "proof_gates": {
            "direction": proof_core,
            "opportunity": not e2_unresolved,
            "auction_confirmation": auction["terminal"],
            "space": space >= MIN_SPACE_ATR,
            "structure": internal == external and internal != "NEUTRAL",
        },
        "space_is_constraint_not_invalidation": True,
        "e6_owns_thesis": True,
        "e7_owns_confirmation": True,
        "e8_owns_trade_economics": True,
        "e9_owns_trade_decision": True,
    }
    candidate_state = [{"name": setup, "direction": direction, "causal_score": round(quality, 2), "stage": stage, "proof_gates": trace["proof_gates"], "supporting_evidence": support, "counter_evidence": counter, "missing_proof": missing}]
    invalidation = ["closed-candle structure invalidates directional thesis", "opposing confirmed auction response"]
    if auction["level"]: invalidation.append(f"anchor_level={auction['level']:.5f}")
    return _result(state=stage, setup=setup, direction=direction, maturity=maturity, thesis=thesis, quality=quality, confidence=confidence, exists=True, observations=observations, support=support, counter=counter, missing=missing, next_event=next_event, invalidation=invalidation, candidates=candidate_state, rejected=[], trace=trace, ledger=ledger, primary_blocker=primary, secondary_blockers=[x for x in blockers if x != primary])
