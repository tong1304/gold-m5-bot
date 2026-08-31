from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_OPPORTUNITY_THESIS_ENGINE_V41"
VERSION = "41.0"
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
UNRESOLVED = {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS", "WAIT", "EMERGING", "PENDING", "DEVELOPING"}
TERMINAL_AUCTION_STATES = {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED", "RECLAIMED"}


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
        else:
            prev = _num(sample[i - 1].get("close"))
            trs.append(max(high - low, abs(high - prev), abs(low - prev)))
    return mean(trs[-ATR_PERIOD:]) if trs else 0.0


def _auction(e4: dict[str, Any]) -> dict[str, Any]:
    event = _text(e4.get("event", e4.get("finding")))
    state = _text(e4.get("auction_state", e4.get("state")))
    age = max(0, int(_num(e4.get("event_age_bars"))))
    terminal = state in TERMINAL_AUCTION_STATES or "TERMINAL" in state
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
    return {"event": event, "state": state, "direction": direction, "terminal": terminal,
            "pending": state == "PENDING" or "PENDING" in event, "age_bars": age,
            "level": _num(e4.get("event_level")),
            "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""),
            "response_actor": _text(e4.get("response_actor"))}


def _structure(e3: dict[str, Any]) -> tuple[str, str, str]:
    return (_text(e3.get("finding", e3.get("structure_state"))),
            _norm(e3.get("internal_state", e3.get("internal_count_state"))),
            _norm(e3.get("external_state", e3.get("external_count_state"))))


def _e2_direction(e2: dict[str, Any]) -> str:
    for key in ("direction", "opportunity_direction", "auction_direction"):
        d = _norm(e2.get(key))
        if d != "NEUTRAL":
            return d
    finding = _text(e2.get("finding", e2.get("state")))
    if finding.startswith(("BUY ", "LONG ", "UP ")):
        return "BUY"
    if finding.startswith(("SELL ", "SHORT ", "DOWN ")):
        return "SELL"
    return "NEUTRAL"


def _e2_unresolved(e2: dict[str, Any]) -> bool:
    finding = _text(e2.get("finding", e2.get("state")))
    state = _text(e2.get("opportunity_state", e2.get("opportunity_decision")))
    maturity = _text(e2.get("opportunity_maturity"))
    return (finding in UNRESOLVED or state in UNRESOLVED or
            maturity in {"UNPROVEN", "EMERGING", "DEVELOPING"} or
            "OPPORTUNITY IS DEVELOPING" in finding)


def _e2_confirmed(e2: dict[str, Any]) -> bool:
    if _e2_unresolved(e2):
        return False
    finding = _text(e2.get("finding", e2.get("state")))
    state = _text(e2.get("opportunity_state", e2.get("opportunity_decision")))
    maturity = _text(e2.get("opportunity_maturity"))
    return ("OPPORTUNITY IS CONFIRMED" in finding or
            state in {"CONFIRMED", "VALID", "ELIGIBLE", "ACTIONABLE"} or
            maturity in {"CONFIRMED", "VALIDATED", "MATURE"})


def _e3_invalidated(e3: dict[str, Any]) -> bool:
    lifecycle = _text(e3.get("lifecycle"))
    invalidation = _text(e3.get("invalidation"))
    finding = _text(e3.get("finding"))
    return bool(e3.get("structure_invalidated") is True or e3.get("active_invalidation") is True or
                lifecycle == "INVALIDATED" or invalidation in {
                    "ACTIVE_INVALIDATION", "STRUCTURE_INVALIDATED",
                    "BULLISH_STRUCTURE_INVALIDATED", "BEARISH_STRUCTURE_INVALIDATED"} or
                finding.endswith("_INVALIDATED"))


def _direction(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any]):
    auction = _auction(e4)
    pressure = _norm(e1.get("directional_pressure", e1.get("pressure")))
    finding, internal, external = _structure(e3)
    e2_direction = _e2_direction(e2)
    support = [f"{k}={v}" for k, v in (("E1_PRESSURE", pressure), ("E2_DIRECTION", e2_direction),
                                        ("E3_INTERNAL", internal), ("E3_EXTERNAL", external),
                                        ("E4_AUCTION", auction["direction"])) if v != "NEUTRAL"]
    conflicts: list[str] = []
    directions = [x for x in (pressure, e2_direction, internal, external) if x != "NEUTRAL"]
    if len(set(directions)) > 1:
        conflicts.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    if pressure != "NEUTRAL" and e2_direction != "NEUTRAL" and pressure != e2_direction:
        conflicts.append("E1_E2_DIRECTION_CONFLICT")
    if internal != "NEUTRAL" and external != "NEUTRAL" and internal != external:
        conflicts.append("STRUCTURE_DIRECTION_CONFLICT")
    if pressure != "NEUTRAL" and internal == pressure and external in {pressure, "NEUTRAL"}:
        return pressure, _dedupe(support), _dedupe(conflicts), "E1_E3_DIRECTIONAL_CORE"
    if e2_direction != "NEUTRAL" and internal == e2_direction:
        return e2_direction, _dedupe(support), _dedupe(conflicts), "E2_E3_OPPORTUNITY_STRUCTURE"
    if internal != "NEUTRAL" and external == internal:
        return internal, _dedupe(support), _dedupe(conflicts), "E3_STRUCTURE_CONVERGENCE"
    if pressure != "NEUTRAL":
        return pressure, _dedupe(support), _dedupe(conflicts), "E1_CONTEXT_DIRECTION"
    if internal != "NEUTRAL":
        return internal, _dedupe(support), _dedupe(conflicts), "E3_STRUCTURE_DIRECTION"
    if auction["direction"] != "NEUTRAL":
        return auction["direction"], _dedupe(support), _dedupe(conflicts), "E4_AUCTION_HYPOTHESIS"
    return "NEUTRAL", _dedupe(support), _dedupe(conflicts), "NO_DIRECTIONAL_THESIS"


def _space(direction: str, e5: dict[str, Any]) -> dict[str, Any]:
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short" if direction == "SELL" else ""
    available = _num(e5.get(key)) if key else 0.0
    return {"direction": direction, "available_space_atr": round(available, 4),
            "minimum_required_space_atr": MIN_SPACE_ATR, "space_sufficient": available >= MIN_SPACE_ATR,
            "structural_location": _text(e5.get("structural_location")) or "UNKNOWN",
            "next_resistance": _num(e5.get("next_resistance")), "next_support": _num(e5.get("next_support")),
            "constraint": "NONE" if available >= MIN_SPACE_ATR else "STRUCTURAL_SPACE_INSUFFICIENT",
            "interpretation": "SPACE_IS_TRADE_GEOMETRY_CONSTRAINT_NOT_SETUP_INVALIDATION" if available < MIN_SPACE_ATR else "SPACE_SUPPORTS_SETUP_FORMATION"}


def _candidate(direction: str, auction: dict[str, Any], e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e5: dict[str, Any]):
    if direction == "NEUTRAL":
        return None
    e2_confirmed, e2_unresolved = _e2_confirmed(e2), _e2_unresolved(e2)
    event, event_direction = auction["event"], auction["direction"]
    terminal = auction["terminal"]
    e1_finding, e3_finding = _text(e1.get("finding", e1.get("trend_state"))), _text(e3.get("finding", e3.get("structure_state")))
    trend, internal, external = _norm(e1.get("trend_state")), _norm(e3.get("internal_state")), _norm(e3.get("external_state"))
    bos = _text(e3.get("bos", e3.get("break_of_structure")))
    market_state = _text(e1.get("market_state"))
    repricing = _text(e5.get("repricing_state"))
    value_response = _text(e5.get("value_response"))

    # Opportunity formation is deliberately allowed before E2 is fully confirmed.
    # E6 records a hypothesis; E7/E8 remain mandatory proof/economic gates.
    if direction == "BUY" and ("BOS_UP" in e3_finding or bos in {"BOS_UP", "UP", "BREAK", "BOS", "YES"}) and ("HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event):
        return "BREAKOUT_RETEST", 72.0, ["E3_BOS_UP", "E4_HIGH_ACCEPTANCE_OR_BREAK", "E6_THESIS_FORMED_BEFORE_E2_PROOF"]
    if direction == "SELL" and ("BOS_DOWN" in e3_finding or bos in {"BOS_DOWN", "DOWN", "BREAK", "BOS", "YES"}) and ("LOW_ACCEPTANCE" in event or "LOW_BREAK" in event):
        return "BREAKOUT_RETEST", 72.0, ["E3_BOS_DOWN", "E4_LOW_ACCEPTANCE_OR_BREAK", "E6_THESIS_FORMED_BEFORE_E2_PROOF"]

    if event_direction == direction and any(x in event for x in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM", "HIGH_REJECTION", "LOW_REJECTION")):
        if terminal and e2_confirmed:
            return "LIQUIDITY_REVERSAL", 86.0, ["E4_TERMINAL_LIQUIDITY_RESPONSE", "E2_OPPORTUNITY_CONFIRMED"]
        if e2_unresolved and (internal == direction or external == direction or direction in e3_finding):
            return "LIQUIDITY_REVERSAL", 62.0, ["E4_LIQUIDITY_RESPONSE", "E3_STRUCTURE_RESPONSE", "E6_THESIS_FORMED_BEFORE_E2_PROOF"]

    if event_direction == direction and "ACCEPTANCE" in event:
        if terminal and e2_confirmed:
            return "AUCTION_ACCEPTANCE_CONTINUATION", 82.0, ["E4_TERMINAL_AUCTION_ACCEPTANCE", "E2_OPPORTUNITY_CONFIRMED"]
        if e2_unresolved and (internal == direction or external == direction):
            return "AUCTION_ACCEPTANCE_CONTINUATION", 60.0, ["E4_AUCTION_ACCEPTANCE_CANDIDATE", "E3_STRUCTURE_RESPONSE", "E6_THESIS_FORMED_BEFORE_E2_PROOF"]

    break_event = any(x in event for x in ("BREAKOUT", "BOS", "FAILED_BREAK_RECLAIM")) or bos in {"BREAK", "BOS", "YES"}
    if break_event and ("RETEST" in e3_finding or "RECLAIM" in e3_finding or terminal):
        if e2_confirmed or (e2_unresolved and internal == direction):
            return "BREAKOUT_RETEST", 68.0 if e2_confirmed else 58.0, ["E3_CONFIRMED_BREAK_STRUCTURE", "E6_THESIS_FORMED_BEFORE_E2_PROOF"]

    aligned = trend == direction == internal == external
    transition = any("TRANSITION" in x for x in (market_state, e1_finding, e3_finding))
    pullback = any(x in e1_finding or x in e3_finding for x in ("PULLBACK", "RETRACE"))
    if e2_confirmed and aligned and not transition and pullback:
        return "TREND_PULLBACK", 72.0, ["E1_TREND_ALIGNMENT", "E2_OPPORTUNITY_CONFIRMED", "E3_STRUCTURE_ALIGNMENT", "PULLBACK_CONTEXT"]

    expansion = any(x in e1_finding for x in ("EXPANSION", "IMPULSE", "DIRECTIONAL_EXPANSION"))
    pressure = _norm(e1.get("pressure", e1.get("directional_pressure")))
    accepted = any(x in repricing for x in ("ACCEPTANCE", "REPRICING", "CONTINUATION")) or "ACCEPTED" in value_response
    if e2_confirmed and expansion and pressure == direction and internal == external == direction and accepted:
        return "IMPULSE_CONTINUATION", 68.0, ["E1_DIRECTIONAL_EXPANSION", "E2_OPPORTUNITY_CONFIRMED", "E3_STRUCTURE_ALIGNMENT", "E5_REPRICING_ACCEPTANCE"]
    return None


def _result(**kw: Any) -> EngineResult:
    state, setup, direction = kw.get("state", "ABSENT"), kw.get("setup", "NONE"), kw.get("direction", "NEUTRAL")
    quality = round(max(0.0, min(100.0, _num(kw.get("quality")))), 2)
    confidence = round(max(0.0, min(100.0, _num(kw.get("confidence")))), 2)
    support, counter, missing = _dedupe(kw.get("support", [])), _dedupe(kw.get("counter", [])), _dedupe(kw.get("missing", []))
    primary = str(kw.get("primary_blocker", "NONE"))
    secondary = _dedupe(kw.get("secondary_blockers", []))
    reasons = _dedupe(([primary] if primary != "NONE" else []) + secondary)
    thesis, exists = str(kw.get("thesis", "")), bool(kw.get("exists", False))
    trace = dict(kw.get("trace", {}))
    out = {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "role": "SETUP_FORMATION_REASONER", "reasoning_role": "SETUP_FORMATION_REASONER",
        "decision_authority": "E9", "trade_decision_authority": False,
        "state": state, "setup_state": state, "finding": thesis,
        "setup": setup, "setup_family": setup, "candidate_setup": setup,
        "candidate_setup_thesis": thesis, "candidate_setup_identity": trace.get("candidate_identity"),
        "candidate_identity_basis": trace.get("candidate_identity_basis"), "direction": direction,
        "direction_thesis": thesis, "direction_source": trace.get("direction_source"),
        "stage": state, "formation_stage": state, "lifecycle": state, "lifecycle_states": list(LIFECYCLE),
        "maturity": kw.get("maturity", "UNRESOLVED"), "thesis": thesis, "thesis_owner": "E6",
        "setup_exists": exists, "trade_ready": False, "trade_readiness": "NOT_READY",
        "setup_quality": quality, "confidence": confidence, "observations": _dedupe(kw.get("observations", [])),
        "candidate_setups": [setup] if exists else [], "candidate_states": kw.get("candidates", []),
        "selected_hypothesis": setup if exists else None, "rejected_hypotheses": [], "rejected_setups": [],
        "supporting_evidence": support, "counter_evidence": counter, "missing_evidence": missing,
        "missing_proof": missing, "next_required_evidence": missing,
        "next_required_event": kw.get("next_event", "REASSESS_NEXT_CLOSED_CANDLE"),
        "invalidation": kw.get("invalidation", []), "evidence_ledger": kw.get("ledger", []),
        "reasoning_trace": trace, "reason_codes": reasons, "primary_blocker": primary,
        "secondary_blockers": secondary, "conflict_ledger": counter, "governance_blockers": reasons,
        "professional_reasoning": {
            "conclusion": thesis, "selected_hypothesis": setup if exists else None,
            "why_it_is_forming": support, "what_is_wrong_with_the_thesis": counter,
            "what_is_missing": missing, "what_must_happen_next": kw.get("next_event", "REASSESS_NEXT_CLOSED_CANDLE"),
            "what_invalidates_it": kw.get("invalidation", []), "formation_stage": state,
            "maturity": kw.get("maturity", "UNRESOLVED"), "setup_quality": quality, "confidence": confidence,
            "primary_blocker": primary, "secondary_blockers": secondary,
            "decision_boundary": "E6 forms and stages the opportunity thesis; E7 proves confirmation; E8 proves economics; E9 decides trade permission.",
        },
    }
    return EngineResult("E6", NAME, False, quality, out, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _result(state="ABSENT", thesis="Insufficient closed-candle evidence.", quality=0, confidence=100, exists=False,
                       observations=[f"valid_candles={len(bars)}"], counter=["INSUFFICIENT_HISTORY"],
                       missing=[f"AT_LEAST_{MIN_BARS}_VALID_CLOSED_CANDLES"], next_event=f"WAIT_FOR_{MIN_BARS}_VALID_CLOSED_CANDLES",
                       primary_blocker="CAUSAL_SETUP_PROOF_INCOMPLETE")
    try:
        if _atr(bars) <= 0:
            raise ValueError
        for candle in bars[-MIN_BARS:]:
            for key in ("open", "high", "low", "close"):
                value = float(candle[key])
                if value != value:
                    raise ValueError
    except (KeyError, TypeError, ValueError):
        return _result(state="ABSENT", thesis="Invalid closed-candle OHLC.", quality=0, confidence=100, exists=False,
                       observations=["ohlc_validation=FAILED"], counter=["INVALID_MARKET_DATA"],
                       missing=["VALID_CLOSED_CANDLE_OHLC"], next_event="WAIT_FOR_VALID_CLOSED_CANDLE_DATA",
                       primary_blocker="CAUSAL_SETUP_PROOF_INCOMPLETE")

    e1, e2, e3, e4, e5 = (_payload(upstream, key) for key in ("E1", "E2", "E3", "E4", "E5"))
    if _e3_invalidated(e3):
        finding = _text(e3.get("finding", "STRUCTURE_INVALIDATED"))
        return _result(state="INVALIDATED", setup="NONE", direction="NEUTRAL", maturity="INVALIDATED",
                       thesis="No setup survives because E3 explicitly invalidated the active market structure.", quality=0, confidence=100, exists=False,
                       observations=["E3_STRUCTURE_INVALIDATED", finding], counter=["E3_STRUCTURE_INVALIDATED"],
                       missing=["NEW_VALID_CLOSED_CANDLE_STRUCTURE_LIFECYCLE"], next_event="E3_NEW_VALID_STRUCTURE_LIFECYCLE",
                       invalidation=[finding], primary_blocker="E3_STRUCTURE_INVALIDATED")

    auction = _auction(e4)
    direction, direction_support, conflicts, direction_source = _direction(e1, e2, e3, e4)
    structure_finding, internal, external = _structure(e3)
    e2_unresolved, e2_confirmed = _e2_unresolved(e2), _e2_confirmed(e2)
    space = _space(direction, e5)
    blockers = list(conflicts)
    if direction == "NEUTRAL":
        blockers.append("DIRECTION_UNRESOLVED")
    if auction["pending"] and not auction["terminal"]:
        blockers.append("AUCTION_CONFIRMATION_PENDING")
    if auction["age_bars"] > MAX_EVENT_AGE_BARS and auction["event"]:
        blockers.append("STALE_AUCTION_EVENT")
    if internal != "NEUTRAL" and external != "NEUTRAL" and internal != external:
        blockers.append("STRUCTURE_CONFLICT")
    if "MIXED" in structure_finding or "TRANSITION" in structure_finding:
        blockers.append("STRUCTURE_TRANSITION")
    if direction in {"BUY", "SELL"} and not space["space_sufficient"]:
        blockers.append("STRUCTURAL_SPACE_INSUFFICIENT")
    blockers = _dedupe(blockers)

    candidate = _candidate(direction, auction, e1, e2, e3, e5)
    if candidate is None:
        missing = ["CAUSAL_SETUP_CHAIN"]
        if e2_unresolved:
            missing.append("E2_CLOSED_CANDLE_OPPORTUNITY_CONFIRMATION")
        if auction["pending"] and not auction["terminal"]:
            missing.append("TERMINAL_AUCTION_CONFIRMATION")
        if direction in {"BUY", "SELL"} and not space["space_sufficient"]:
            missing.append(f"STRUCTURAL_SPACE_{MIN_SPACE_ATR:.2f}_ATR")
        primary = next((x for x in ("DIRECTIONAL_EVIDENCE_CONFLICT", "E1_E2_DIRECTION_CONFLICT", "STRUCTURE_CONFLICT", "DIRECTION_UNRESOLVED") if x in blockers), "CAUSAL_SETUP_PROOF_INCOMPLETE")
        thesis = "No causal setup hypothesis survives current closed-candle evidence."
        return _result(state="ABSENT", setup="NONE", direction=direction, maturity="UNRESOLVED", thesis=thesis,
                       quality=0, confidence=65, exists=False, observations=direction_support,
                       support=direction_support, counter=blockers, missing=missing,
                       next_event="WAIT_FOR_NEW_CLOSED_CANDLE_CAUSAL_SETUP_EVIDENCE", primary_blocker=primary,
                       secondary_blockers=[x for x in blockers if x != primary],
                       trace={"direction_source": direction_source, "space_diagnostic": space, "context_is_not_setup": True})

    setup, quality, evidence = candidate
    identity = f"{setup}:{direction}:{auction['event_id']}" if auction["event_id"] else f"{setup}:{direction}:{auction['level']:.5f}"
    identity_basis = "E4_EVENT_ID" if auction["event_id"] else "E4_EVENT_LEVEL"
    # Formation is independent of proof completion. Space/auction/E2 uncertainty becomes a proof/economic blocker, not thesis deletion.
    stage = "MATURE" if e2_confirmed and auction["terminal"] and space["space_sufficient"] else "VALIDATING" if e2_confirmed else "FORMING"
    maturity = "MATURE" if stage == "MATURE" else "VALIDATING" if stage == "VALIDATING" else "HYPOTHESIS"
    missing: list[str] = []
    if e2_unresolved:
        missing.append("E2_CLOSED_CANDLE_OPPORTUNITY_CONFIRMATION")
    if auction["pending"] and not auction["terminal"]:
        missing.append("CLOSED_CANDLE_AUCTION_FOLLOW_THROUGH")
    if not space["space_sufficient"]:
        missing.append(f"STRUCTURAL_SPACE_{MIN_SPACE_ATR:.2f}_ATR_OR_VALID_TRADE_GEOMETRY")
    if stage != "MATURE":
        missing.append("E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION")
    counter = _dedupe(blockers)
    primary = "NONE" if stage == "MATURE" else ("AUCTION_CONFIRMATION_PENDING" if auction["pending"] and not auction["terminal"] else "E2_OPPORTUNITY_UNRESOLVED" if e2_unresolved else "STRUCTURAL_SPACE_INSUFFICIENT" if not space["space_sufficient"] else "E7_CONFIRMATION_REQUIRED")
    thesis = f"{direction} {setup} is {stage.lower()}: E6 has identified a causal opportunity thesis; E7/E8 proof and economic gates remain independent."
    observations = direction_support + evidence + [f"setup={setup}", f"formation_stage={stage}", f"e2_opportunity_confirmed={e2_confirmed}",
                  f"e2_opportunity_unresolved={e2_unresolved}", f"auction={auction['event'] or 'NONE'}",
                  f"auction_state={auction['state'] or 'NONE'}", f"space_atr={space['available_space_atr']:.3f}",
                  f"space_required_atr={MIN_SPACE_ATR:.3f}"]
    ledger = [
        {"source": "E1", "kind": "CONTEXT", "statement": _text(e1.get("finding", "NONE"))},
        {"source": "E2", "kind": "OPPORTUNITY", "statement": _text(e2.get("finding", "NONE")), "unresolved": e2_unresolved, "confirmed": e2_confirmed},
        {"source": "E3", "kind": "STRUCTURE", "statement": structure_finding or "NONE"},
        {"source": "E4", "kind": "AUCTION", "statement": auction["event"] or "NONE", "state": auction["state"]},
        {"source": "E5", "kind": "LOCATION", "space_atr": space["available_space_atr"], "space_sufficient": space["space_sufficient"]},
    ]
    trace = {"summary": f"E1->E2->E3->E4->E5->E6:{stage}", "decision": "FORM_OPPORTUNITY_THESIS_NOT_TRADE", "selected_hypothesis": setup,
             "candidate_identity": identity, "candidate_identity_basis": identity_basis, "direction_source": direction_source,
             "thesis_status": "ALIVE", "e2_proof_pending": e2_unresolved, "auction_proof_pending": not auction["terminal"],
             "space_is_constraint_not_invalidation": True, "context_is_not_setup": False,
             "e6_owns_thesis": True, "e7_owns_confirmation": True, "e8_owns_trade_economics": True, "e9_owns_trade_decision": True}
    candidate_state = [{"name": setup, "direction": direction, "causal_score": quality, "stage": stage,
                        "supporting_evidence": evidence, "counter_evidence": counter, "missing_proof": missing}]
    invalidation = ["closed-candle structure invalidates directional thesis", "opposing confirmed auction response"]
    if auction["level"]:
        invalidation.append(f"anchor_level={auction['level']:.5f}")
    return _result(state=stage, setup=setup, direction=direction, maturity=maturity, thesis=thesis,
                   quality=quality, confidence=78 if stage == "FORMING" else 86, exists=True,
                   observations=observations, support=_dedupe(direction_support + evidence), counter=counter, missing=missing,
                   next_event="WAIT_FOR_E7_SETUP_SPECIFIC_PROOF_AND_E8_TRADE_ECONOMICS",
                   invalidation=invalidation, candidates=candidate_state, ledger=ledger, trace=trace,
                   primary_blocker=primary, secondary_blockers=[x for x in counter if x != primary])
