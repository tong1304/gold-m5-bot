from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V33"
VERSION = "33.0"

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

PRIMARY_PRIORITY = (
    "E3_STRUCTURE_INVALIDATED",
    "DIRECTION_UNRESOLVED",
    "AUCTION_CONFIRMATION_PENDING",
    "E2_OPPORTUNITY_UNRESOLVED",
    "DIRECTIONAL_EVIDENCE_CONFLICT",
    "STRUCTURE_CONFLICT",
    "SPACE_CONFLICT",
    "STALE_AUCTION_EVENT",
    "CAUSAL_SETUP_PROOF_INCOMPLETE",
)


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
    ranges: list[float] = []
    for i, candle in enumerate(sample):
        high = _num(candle.get("high"))
        low = _num(candle.get("low"))
        previous_close = _num(sample[i - 1].get("close")) if i else 0.0
        if i == 0:
            ranges.append(max(0.0, high - low))
        else:
            ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return mean(ranges[-ATR_PERIOD:]) if ranges else 0.0


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
        "event": event,
        "state": state,
        "direction": direction,
        "terminal": terminal,
        "pending": state == "PENDING" or "PENDING" in event,
        "age_bars": age,
        "level": _num(e4.get("event_level")),
        "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""),
        "response_actor": _text(e4.get("response_actor")),
    }


def _structure(e3: dict[str, Any]) -> tuple[str, str, str]:
    finding = _text(e3.get("finding", e3.get("structure_state")))
    internal = _norm(e3.get("internal_state", e3.get("internal_count_state")))
    external = _norm(e3.get("external_state", e3.get("external_count_state")))
    return finding, internal, external


def _e3_invalidated(e3: dict[str, Any]) -> bool:
    lifecycle = _text(e3.get("lifecycle"))
    invalidation = _text(e3.get("invalidation"))
    finding = _text(e3.get("finding"))
    if e3.get("structure_invalidated") is True or e3.get("active_invalidation") is True:
        return True
    if lifecycle == "INVALIDATED":
        return True
    return invalidation in {"ACTIVE_INVALIDATION", "STRUCTURE_INVALIDATED", "BULLISH_STRUCTURE_INVALIDATED", "BEARISH_STRUCTURE_INVALIDATED"} or finding.endswith("_INVALIDATED")


def _e2_unresolved(e2: dict[str, Any]) -> bool:
    finding = _text(e2.get("finding", e2.get("state")))
    state = _text(e2.get("opportunity_state", e2.get("opportunity_decision")))
    maturity = _text(e2.get("opportunity_maturity"))
    regime = _text(e2.get("regime"))
    return finding in UNRESOLVED or state in UNRESOLVED or maturity in {"UNPROVEN", "EMERGING"} or regime == "UNRESOLVED"


def _direction(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any]) -> tuple[str, list[str], list[str], str]:
    auction = _auction(e4)
    pressure = _norm(e1.get("directional_pressure", e1.get("pressure")))
    _, internal, external = _structure(e3)
    support: list[str] = []
    conflicts: list[str] = []
    if pressure != "NEUTRAL":
        support.append(f"E1_PRESSURE={pressure}")
    if internal != "NEUTRAL":
        support.append(f"E3_INTERNAL={internal}")
    if external != "NEUTRAL":
        support.append(f"E3_EXTERNAL={external}")
    if auction["direction"] != "NEUTRAL":
        support.append(f"E4_AUCTION={auction['direction']}")
    if internal != "NEUTRAL" and external != "NEUTRAL" and internal != external:
        conflicts.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    if pressure != "NEUTRAL" and auction["direction"] != "NEUTRAL" and pressure != auction["direction"]:
        conflicts.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    if pressure != "NEUTRAL" and internal == pressure:
        direction, source = pressure, "E1_E3_DIRECTIONAL_CORE"
    elif internal != "NEUTRAL" and internal == external:
        direction, source = internal, "E3_STRUCTURE_CONVERGENCE"
    elif pressure != "NEUTRAL" and pressure == auction["direction"]:
        direction, source = pressure, "E1_E4_DIRECTIONAL_CORE"
    elif auction["terminal"] and auction["direction"] != "NEUTRAL":
        direction, source = auction["direction"], "E4_TERMINAL_AUCTION"
    elif pressure != "NEUTRAL":
        direction, source = pressure, "E1_CONTEXT_ONLY"
    elif internal != "NEUTRAL":
        direction, source = internal, "E3_STRUCTURE_ONLY"
    elif auction["direction"] != "NEUTRAL":
        direction, source = auction["direction"], "E4_PENDING_HYPOTHESIS"
    else:
        direction, source = "NEUTRAL", "NO_DIRECTIONAL_THESIS"
    e2_direction = _norm(e2.get("direction", e2.get("opportunity_direction")))
    if e2_direction != "NEUTRAL" and not _e2_unresolved(e2):
        if direction == e2_direction:
            support.append(f"E2_DIRECTION={e2_direction}")
        elif direction != "NEUTRAL":
            conflicts.append("E2_DIRECTION_DISAGREEMENT")
    return direction, _dedupe(support), _dedupe(conflicts), source


def _candidates(direction: str, auction: dict[str, Any], e1: dict[str, Any], e3: dict[str, Any], e5: dict[str, Any]) -> list[dict[str, Any]]:
    event = auction["event"]
    event_direction = auction["direction"]
    candidates: list[dict[str, Any]] = []

    def add(name: str, side: str, quality: float, evidence: list[str]) -> None:
        if side in {"BUY", "SELL"}:
            candidates.append({"name": name, "direction": side, "base_quality": quality, "evidence": evidence})

    if event_direction in {"NEUTRAL", direction}:
        if "FAILED_BREAK_RECLAIM" in event or "SWEEP_REJECTION" in event:
            add("LIQUIDITY_REVERSAL", event_direction, 82.0, ["E4_LIQUIDITY_EVENT", "E4_DIRECTIONAL_RESPONSE"])
        if "ACCEPTANCE" in event:
            add("AUCTION_ACCEPTANCE_CONTINUATION", event_direction, 76.0, ["E4_ACCEPTANCE_EVENT", "E4_AUCTION_RESPONSE"])
    bos = _text(e3.get("bos", e3.get("break_of_structure")))
    if any(x in event for x in ("BREAKOUT", "BOS")) or bos in {"BREAK", "BOS", "YES"}:
        add("BREAKOUT_RETEST", direction, 72.0, ["E3_BREAK_EVENT", "E4_AUCTION_CONTEXT"])
        add("BREAKOUT", direction, 68.0, ["E3_BOS", "E4_AUCTION_CONTEXT"])
    trend = _norm(e1.get("trend_state"))
    if trend == direction and "PULLBACK" in _text(e1.get("finding", e1.get("trend_state"))):
        add("TREND_PULLBACK", direction, 66.0, ["E1_TREND_ALIGNMENT", "E3_STRUCTURE"])
    repricing = _text(e5.get("repricing_state"))
    value_response = _text(e5.get("value_response"))
    if direction in {"BUY", "SELL"} and (repricing == "REPRICING_STARTING" or "ACCEPTED_ABOVE_VALUE" in value_response or "ACCEPTED_BELOW_VALUE" in value_response):
        add("IMPULSE_CONTINUATION", direction, 60.0, ["E5_REPRICING_CONTEXT", "E1_DIRECTIONAL_CONTEXT"])
    return candidates


def _identity(setup: str, direction: str, auction: dict[str, Any], e5: dict[str, Any]) -> tuple[str, str]:
    anchor = auction["event_id"] or (f"LEVEL:{auction['level']:.5f}" if auction["level"] else "")
    basis = "E4_EVENT_ID" if auction["event_id"] else "E4_EVENT_LEVEL"
    if not anchor:
        anchor = f"VALUE:{_num(e5.get('value_distance_atr')):.3f}"
        basis = "E5_VALUE_CONTEXT"
    return f"{setup}:{direction}:{anchor}", basis


def _result(
    *, state: str, setup: str, direction: str, stage: str, maturity: str, thesis: str,
    quality: float, confidence: float, exists: bool, support: list[str], counter: list[str],
    missing: list[str], next_event: str, invalidation: list[str], candidates: list[dict[str, Any]],
    rejected: list[str], trace: dict[str, Any], ledger: list[dict[str, Any]],
    primary_blocker: str = "NONE", secondary_blockers: list[str] | None = None,
) -> EngineResult:
    support = _dedupe(support)
    counter = _dedupe(counter)
    missing = _dedupe(missing)
    invalidation = _dedupe(invalidation)
    secondary = _dedupe(secondary_blockers or [])
    reasons = _dedupe(([primary_blocker] if primary_blocker != "NONE" else []) + secondary)
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
        "stage": stage,
        "formation_stage": stage,
        "lifecycle": stage,
        "lifecycle_states": list(LIFECYCLE),
        "maturity": maturity,
        "thesis": thesis,
        "setup_exists": exists,
        "trade_ready": False,
        "trade_readiness": "NOT_READY",
        "setup_quality": round(max(0.0, min(100.0, quality)), 2),
        "confidence": round(max(0.0, min(100.0, confidence)), 2),
        "candidate_setups": [c["name"] for c in candidates],
        "candidate_states": candidates,
        "selected_hypothesis": setup if exists else None,
        "rejected_hypotheses": rejected,
        "rejected_setups": rejected,
        "supporting_evidence": support,
        "counter_evidence": counter,
        "missing_evidence": missing,
        "missing_proof": missing,
        "next_required_evidence": missing,
        "next_required_event": next_event,
        "invalidation": invalidation,
        "evidence_ledger": ledger,
        "reasoning_trace": trace,
        "reason_codes": reasons,
        "primary_blocker": primary_blocker,
        "secondary_blockers": secondary,
        "conflict_ledger": counter,
        "governance_blockers": reasons,
        "professional_reasoning": {
            "conclusion": thesis,
            "selected_hypothesis": setup if exists else None,
            "why_it_is_forming": support,
            "what_is_wrong_with_the_thesis": counter,
            "what_is_missing": missing,
            "what_must_happen_next": next_event,
            "what_invalidates_it": invalidation,
            "formation_stage": stage,
            "maturity": maturity,
            "setup_quality": round(max(0.0, min(100.0, quality)), 2),
            "confidence": round(max(0.0, min(100.0, confidence)), 2),
            "primary_blocker": primary_blocker,
            "secondary_blockers": secondary,
            "decision_boundary": "E6 describes and stages the setup; E9 alone decides whether a trade is permitted.",
        },
    }
    return EngineResult("E6", NAME, False, out["setup_quality"], out, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _result(
            state="NO_SETUP", setup="NONE", direction="NEUTRAL", stage="ABSENT", maturity="UNRESOLVED",
            thesis="Insufficient closed-candle evidence.", quality=0.0, confidence=100.0, exists=False,
            support=[], counter=["INSUFFICIENT_HISTORY"], missing=["sufficient_closed_candle_data"],
            next_event=f"WAIT_FOR_AT_LEAST_{MIN_BARS}_VALID_CLOSED_CANDLES", invalidation=["insufficient_history"],
            candidates=[], rejected=[], trace={"selected_hypothesis": None}, ledger=[], primary_blocker="CAUSAL_SETUP_PROOF_INCOMPLETE",
        )

    try:
        if _atr(bars) <= 0:
            raise ValueError("zero ATR")
        for candle in bars[-MIN_BARS:]:
            for key in ("open", "high", "low", "close"):
                value = float(candle[key])
                if value != value:
                    raise ValueError("NaN OHLC")
    except (KeyError, TypeError, ValueError):
        return _result(
            state="NO_SETUP", setup="NONE", direction="NEUTRAL", stage="ABSENT", maturity="UNRESOLVED",
            thesis="Invalid closed-candle OHLC.", quality=0.0, confidence=100.0, exists=False,
            support=[], counter=["INVALID_MARKET_DATA"], missing=["valid_closed_candle_ohlc"],
            next_event="WAIT_FOR_VALID_CLOSED_CANDLE_DATA", invalidation=["invalid_market_data"],
            candidates=[], rejected=[], trace={"selected_hypothesis": None}, ledger=[], primary_blocker="CAUSAL_SETUP_PROOF_INCOMPLETE",
        )

    e1, e2, e3, e4, e5 = (_payload(upstream, key) for key in ("E1", "E2", "E3", "E4", "E5"))
    if _e3_invalidated(e3):
        finding = _text(e3.get("finding", e3.get("structure_state"))) or "STRUCTURE_INVALIDATED"
        return _result(
            state="INVALIDATED", setup="NONE", direction="NEUTRAL", stage="INVALIDATED", maturity="INVALIDATED",
            thesis="No setup survives because E3 explicitly invalidated the active market structure.", quality=0.0,
            confidence=100.0, exists=False, support=[], counter=["E3_STRUCTURE_INVALIDATED", finding],
            missing=["a new closed-candle structure lifecycle after invalidation"],
            next_event="E3_NEW_VALID_STRUCTURE_LIFECYCLE", invalidation=[finding], candidates=[], rejected=[],
            trace={"selected_hypothesis": None, "direction_source": "E3_STRUCTURE_INVALIDATION", "lifecycle_owner": "E3"},
            ledger=[{"source": "E3", "kind": "INVALIDATION", "strength": "HIGH", "statement": finding}],
            primary_blocker="E3_STRUCTURE_INVALIDATED",
        )

    auction = _auction(e4)
    direction, direction_support, direction_conflicts, direction_source = _direction(e1, e2, e3, e4)
    structure_finding, internal, external = _structure(e3)
    e2_unresolved = _e2_unresolved(e2)
    location_present = bool(e5)
    space_key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    space = _num(e5.get(space_key)) if direction in {"BUY", "SELL"} else 0.0

    blockers = list(direction_conflicts)
    if direction not in {"BUY", "SELL"}:
        blockers.append("DIRECTION_UNRESOLVED")
    if e2_unresolved:
        blockers.append("E2_OPPORTUNITY_UNRESOLVED")
    if auction["pending"] and not auction["terminal"]:
        blockers.append("AUCTION_CONFIRMATION_PENDING")
    if auction["age_bars"] > MAX_EVENT_AGE_BARS and auction["event"]:
        blockers.append("STALE_AUCTION_EVENT")
    if internal != "NEUTRAL" and external != "NEUTRAL" and internal != external:
        blockers.append("STRUCTURE_CONFLICT")
    if "MIXED" in structure_finding or "TRANSITION" in structure_finding:
        blockers.append("STRUCTURE_CONFLICT")
    if not location_present:
        blockers.append("LOCATION_EVIDENCE_MISSING")
    if direction in {"BUY", "SELL"} and space < MIN_SPACE_ATR:
        blockers.append("SPACE_CONFLICT")
    blockers = _dedupe(blockers)

    candidates = _candidates(direction, auction, e1, e3, e5)
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        quality = candidate["base_quality"]
        support = list(candidate["evidence"])
        counter: list[str] = []
        missing: list[str] = []
        if candidate["direction"] != direction:
            quality -= 25.0
            counter.append("DIRECTION_MISMATCH")
        if auction["terminal"]:
            quality += 8.0
        else:
            quality -= 12.0
            counter.append("AUCTION_CONFIRMATION_PENDING")
            missing.append("terminal_auction_confirmation")
        if e2_unresolved:
            quality -= 18.0
            counter.append("E2_OPPORTUNITY_UNRESOLVED")
            missing.append("E2_opportunity_acceptance_follow_through")
        else:
            quality += 4.0
            support.append("E2_OPPORTUNITY_RESOLVED")
        structure_resolved = internal != "NEUTRAL" and external != "NEUTRAL" and internal == external and "MIXED" not in structure_finding and "TRANSITION" not in structure_finding
        if structure_resolved:
            quality += 6.0
            support.append("E3_STRUCTURE_RESOLVED")
        else:
            quality -= 7.0
            missing.append("structure_resolution")
        if space >= MIN_SPACE_ATR:
            quality += 6.0
            support.append(f"SPACE_OK={space:.3f}ATR")
        else:
            quality -= 15.0
            counter.append("SPACE_CONFLICT")
            missing.append("sufficient_structural_space")
        if candidate["name"] in {"LIQUIDITY_REVERSAL", "AUCTION_ACCEPTANCE_CONTINUATION"} and not auction["terminal"]:
            quality -= 12.0
            missing.append("terminal_auction_confirmation")
        for blocker in blockers:
            if blocker not in counter and blocker not in {"DIRECTION_UNRESOLVED", "LOCATION_EVIDENCE_MISSING"}:
                counter.append(blocker)
        proof = {
            "direction": candidate["direction"] == direction and direction in {"BUY", "SELL"},
            "event": bool(auction["event"]),
            "response": auction["terminal"] or auction["response_actor"] not in {"", "UNKNOWN", "NONE"},
            "structure": structure_resolved,
            "opportunity": not e2_unresolved,
            "auction_finality": auction["terminal"] if candidate["name"] in {"LIQUIDITY_REVERSAL", "AUCTION_ACCEPTANCE_CONTINUATION"} else True,
            "space": space >= MIN_SPACE_ATR,
            "freshness": auction["age_bars"] <= MAX_EVENT_AGE_BARS,
        }
        scored.append({
            **candidate,
            "causal_score": round(max(0.0, min(100.0, quality)), 2),
            "supporting_evidence": _dedupe(support),
            "counter_evidence": _dedupe(counter),
            "missing_proof": _dedupe(missing),
            "proof_gates": proof,
        })

    scored.sort(key=lambda item: (item["causal_score"], sum(bool(x) for x in item["proof_gates"].values())), reverse=True)
    selected = scored[0] if scored else None
    if selected is None:
        return _result(
            state="NO_SETUP", setup="NONE", direction=direction, stage="ABSENT", maturity="UNRESOLVED",
            thesis="No plausible setup survives causal screening.", quality=0.0, confidence=60.0, exists=False,
            support=direction_support, counter=blockers, missing=["causal_setup_evidence"],
            next_event="E1_E2_E3_E4_MUST_FORM_A_CAUSAL_SETUP_CHAIN", invalidation=[], candidates=[], rejected=[],
            trace={"selected_hypothesis": None, "direction_source": direction_source}, ledger=[],
            primary_blocker=next((x for x in PRIMARY_PRIORITY if x in blockers), "CAUSAL_SETUP_PROOF_INCOMPLETE"),
            secondary_blockers=[x for x in blockers if x != next((y for y in PRIMARY_PRIORITY if y in blockers), "")],
        )

    setup = selected["name"]
    identity, identity_basis = _identity(setup, direction, auction, e5)
    proof = selected["proof_gates"]
    explicit_opposition = auction["terminal"] and auction["direction"] in {"BUY", "SELL"} and selected["direction"] != auction["direction"]
    stale = auction["age_bars"] > MAX_EVENT_AGE_BARS
    hard_pending = e2_unresolved or (setup in {"LIQUIDITY_REVERSAL", "AUCTION_ACCEPTANCE_CONTINUATION"} and not auction["terminal"])

    if stale:
        stage = maturity = "EXPIRED"
        thesis = f"{direction} {setup} expired because its initiating event is stale."
        quality = min(selected["causal_score"], 40.0)
        confidence = 30.0
        primary = "STALE_AUCTION_EVENT"
    elif explicit_opposition:
        stage = maturity = "INVALIDATED"
        thesis = f"{direction} {setup} is invalidated by explicit opposing auction evidence."
        quality = min(selected["causal_score"], 35.0)
        confidence = 25.0
        primary = "DIRECTIONAL_EVIDENCE_CONFLICT"
    elif all(proof.values()) and not blockers and not hard_pending:
        stage = maturity = "MATURE"
        thesis = f"{direction} {setup} is mature: the causal chain is complete and no governance blocker remains."
        quality = max(82.0, selected["causal_score"])
        confidence = min(96.0, 80.0 + selected["causal_score"] * 0.14)
        primary = "NONE"
    elif proof["direction"] and proof["event"] and proof["response"] and not hard_pending:
        stage = maturity = "VALIDATING"
        thesis = f"{direction} {setup} is validating: the thesis is alive, but one or more proof gates remain incomplete."
        quality = selected["causal_score"]
        confidence = 72.0
        primary = next((x for x in PRIMARY_PRIORITY if x in blockers), "CAUSAL_SETUP_PROOF_INCOMPLETE")
    else:
        stage = maturity = "FORMING"
        thesis = f"{direction} {setup} is a candidate hypothesis only; required upstream proof is incomplete."
        quality = selected["causal_score"]
        confidence = 58.0
        primary = next((x for x in PRIMARY_PRIORITY if x in blockers), "CAUSAL_SETUP_PROOF_INCOMPLETE")

    missing = list(selected["missing_proof"])
    if e2_unresolved and "E2_OPPORTUNITY_ACCEPTANCE_FOLLOW_THROUGH" not in missing:
        missing.append("E2_OPPORTUNITY_ACCEPTANCE_FOLLOW_THROUGH")
    if not auction["terminal"] and setup in {"LIQUIDITY_REVERSAL", "AUCTION_ACCEPTANCE_CONTINUATION"}:
        missing.append("TERMINAL_AUCTION_CONFIRMATION")
    if direction in {"BUY", "SELL"} and space < MIN_SPACE_ATR:
        missing.append(f"STRUCTURAL_SPACE_{MIN_SPACE_ATR:.2f}_ATR")

    if primary == "AUCTION_CONFIRMATION_PENDING":
        next_event = "TERMINAL_AUCTION_CONFIRMATION"
    elif primary == "E2_OPPORTUNITY_UNRESOLVED":
        next_event = "E2_CLOSED_CANDLE_OPPORTUNITY_ACCEPTANCE_AND_FOLLOW_THROUGH"
    elif primary == "SPACE_CONFLICT":
        next_event = "E5_STRUCTURAL_SPACE_REOPENS_ABOVE_MINIMUM"
    elif primary == "DIRECTIONAL_EVIDENCE_CONFLICT":
        next_event = "NEW_CLOSED_CANDLE_DIRECTIONAL_RESOLUTION"
    elif primary == "STRUCTURE_CONFLICT":
        next_event = "E3_STRUCTURE_RESOLUTION_ON_CLOSED_CANDLE"
    elif primary == "STALE_AUCTION_EVENT":
        next_event = "NEW_CAUSAL_AUCTION_EVENT"
    elif stage == "MATURE":
        next_event = "E7_SETUP_SPECIFIC_CLOSED_CANDLE_CONFIRMATION"
    else:
        next_event = "CLOSE_NEXT_BAR_AND_REASSESS_MISSING_PROOF"

    if setup == "LIQUIDITY_REVERSAL":
        invalidation = ["closed-candle acceptance through the liquidity anchor", "opposing confirmed auction response", "protected structure breaks against reversal"]
    elif setup in {"BREAKOUT", "BREAKOUT_RETEST", "AUCTION_ACCEPTANCE_CONTINUATION"}:
        invalidation = ["closed-candle rejection through the acceptance/breakout anchor", "failed follow-through", "structure invalidates continuation"]
    elif setup == "TREND_PULLBACK":
        invalidation = ["trend no longer agrees with setup direction", "protected structure breaks", "pullback fails to continue"]
    else:
        invalidation = ["closed-candle structure invalidates directional thesis", "opposing confirmed auction response"]
    if auction["level"]:
        invalidation.append(f"anchor_level={auction['level']:.5f}")

    ledger = [
        {"source": "E1", "kind": "CONTEXT", "strength": "HIGH", "statement": _text(e1.get("finding", "NONE"))},
        {"source": "E2", "kind": "OPPORTUNITY", "strength": "HIGH", "statement": f"unresolved={e2_unresolved}"},
        {"source": "E3", "kind": "STRUCTURE", "strength": "HIGH", "statement": structure_finding or "NONE"},
        {"source": "E4", "kind": "AUCTION", "strength": "HIGH", "statement": f"event={auction['event'] or 'NONE'}; state={auction['state'] or 'NONE'}; terminal={auction['terminal']}"},
        {"source": "E5", "kind": "LOCATION", "strength": "HIGH", "statement": f"space_atr={space:.4f}"},
    ]
    trace = {
        "summary": f"E1->E2->E3->E4->E5->conflict_engine->hypothesis_competition->lifecycle={stage}",
        "decision": "DESCRIBE_SETUP_ONLY",
        "selected_hypothesis": setup,
        "candidate_identity": identity,
        "candidate_identity_basis": identity_basis,
        "direction_source": direction_source,
        "causal_chain": {
            "context": bool(e1),
            "opportunity": not e2_unresolved,
            "event": bool(auction["event"]),
            "response": proof["response"],
            "structure": proof["structure"],
        },
        "authority_gates": {
            "e2_opportunity_required": True,
            "e4_terminal_auction_required_for_reversal_and_acceptance": True,
            "e5_space_is_non_overrideable": True,
            "e7_confirmation_required_after_maturity": True,
        },
        "hypothesis_competition": {
            "primary": setup,
            "ranked": [
                {"name": x["name"], "direction": x["direction"], "causal_score": x["causal_score"], "proof_gates": x["proof_gates"]}
                for x in scored
            ],
        },
        "thesis_status": "INVALIDATED" if explicit_opposition else "EXPIRED" if stale else "CANDIDATE_ONLY" if hard_pending else "ALIVE",
        "lifecycle_rule": "unresolved upstream proof keeps the thesis candidate-only; explicit invalidation kills it; stale causal events expire it; only complete proof permits MATURE",
        "evidence_integrity": {"status": "PASS" if all((e1, e2, e3, e4, e5)) else "PARTIAL", "upstream_is_source_of_truth": True},
        "selected_setup_is_not_trade_permission": True,
        "candidate_identity": identity,
        "candidate_identity_basis": identity_basis,
        "primary_blocker": primary,
        "next_required_event": next_event,
    }
    rejected = [f"{x['name']}:OUTRANKED_BY_{setup}:SCORE_{x['causal_score']:.2f}" for x in scored[1:]]
    secondary = [x for x in blockers if x != primary]
    return _result(
        state=stage, setup=setup, direction=direction, stage=stage, maturity=maturity, thesis=thesis,
        quality=quality, confidence=confidence, exists=True, support=direction_support + selected["supporting_evidence"],
        counter=blockers + selected["counter_evidence"], missing=missing, next_event=next_event,
        invalidation=invalidation, candidates=scored, rejected=rejected, trace=trace, ledger=ledger,
        primary_blocker=primary, secondary_blockers=secondary,
    )
