from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V13"
VERSION = "13.0"
MIN_BARS = 60
ATR_PERIOD = 14
MIN_SPACE_ATR = 0.75

SETUP_FAMILIES = (
    "LIQUIDITY_REVERSAL",
    "BREAKOUT_RETEST",
    "TREND_PULLBACK",
    "BREAKOUT",
    "IMPULSE_CONTINUATION",
)


def _payload(upstream: dict[str, EngineResult], name: str) -> dict[str, Any]:
    result = upstream.get(name)
    return result.output if result else {}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _norm(value: Any) -> str:
    text = _text(value)
    if text in {"UP", "BULLISH", "BUY", "BUYERS", "LONG", "TREND_UP"}:
        return "BUY"
    if text in {"DOWN", "BEARISH", "SELL", "SELLERS", "SHORT", "TREND_DOWN"}:
        return "SELL"
    return "NEUTRAL"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _atr(bars: list[dict[str, Any]]) -> float:
    if len(bars) < 2:
        return 0.0
    sample = bars[-(ATR_PERIOD + 1):]
    trs: list[float] = []
    for i, bar in enumerate(sample):
        h, l = _num(bar.get("high")), _num(bar.get("low"))
        if i == 0:
            trs.append(max(0.0, h - l))
        else:
            p = _num(sample[i - 1].get("close"))
            trs.append(max(h - l, abs(h - p), abs(l - p)))
    return mean(trs[-ATR_PERIOD:]) if trs else 0.0


def _auction_direction(event: str) -> str:
    if "HIGH_SWEEP_REJECTION" in event or "HIGH_FAILED_BREAK_RECLAIM" in event:
        return "SELL"
    if "LOW_SWEEP_REJECTION" in event or "LOW_FAILED_BREAK_RECLAIM" in event:
        return "BUY"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
        return "BUY"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
        return "SELL"
    return "NEUTRAL"


def _evidence_direction(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any]):
    pressure = _norm(e1.get("directional_pressure", e1.get("pressure")))
    external = _norm(e3.get("external_state", e3.get("external_count_state")))
    auction = _auction_direction(_text(e4.get("event", e4.get("finding"))))
    e2_finding = _text(e2.get("finding", e2.get("state")))
    e2_dirs = [x for x in (_norm(e2.get("direction")), _norm(e2.get("opportunity_direction"))) if x != "NEUTRAL"]
    e2_resolved = bool(e2_dirs) and "UNRESOLVED" not in e2_finding and "UNPROVEN" not in e2_finding

    supporting: list[str] = []
    counter: list[str] = []
    votes = [x for x in (pressure, external, auction) if x != "NEUTRAL"]

    if e2_resolved and len(set(e2_dirs)) == 1:
        direction, source = e2_dirs[0], "E2_RESOLVED"
    elif len(votes) >= 2 and len(set(votes)) == 1:
        direction, source = votes[0], "E1_E3_E4_CONVERGENCE"
    elif external != "NEUTRAL" and auction == external:
        direction, source = external, "E3_E4_ALIGNMENT"
    else:
        direction, source = "NEUTRAL", "INSUFFICIENT_CONVERGENCE"

    for label, value in (("E1_PRESSURE", pressure), ("E3_EXTERNAL", external), ("E4_AUCTION", auction)):
        if value != "NEUTRAL":
            supporting.append(f"{label}={value}")
    if e2_resolved:
        supporting.append(f"E2_DIRECTION={e2_dirs[0]}")
    if direction != "NEUTRAL":
        supporting.append(f"DIRECTION_SOURCE={source}")

    if len(set(votes)) > 1:
        counter.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    e3_finding = _text(e3.get("finding", e3.get("structure_state")))
    internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    if "MIXED" in e3_finding or "MIXED" in internal:
        counter.append("STRUCTURE_MIXED")
    if "FAILED_BOS" in e3_finding:
        counter.append("FAILED_STRUCTURE_BREAK")
    if direction != "NEUTRAL" and external != "NEUTRAL" and external != direction:
        counter.append("EXTERNAL_STRUCTURE_COUNTERTREND")

    return direction, supporting, list(dict.fromkeys(counter)), source


def _location(e5: dict[str, Any]):
    long_space = _num(e5.get("available_space_atr_long"))
    short_space = _num(e5.get("available_space_atr_short"))
    text = _text(e5)
    constrained = any(x in text for x in ("LOCATION_CONSTRAINT", "SPACE_CONSTRAINED"))
    extension = "EXTENSION_RISK" in text
    return long_space, short_space, constrained, extension


def _auction(e4: dict[str, Any]):
    state = _text(e4.get("auction_state", e4.get("state")))
    event = _text(e4.get("event", e4.get("finding")))
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    pending = state == "PENDING" or "PENDING" in event
    age = max(0, int(_num(e4.get("event_age_bars"), 0)))
    return event, terminal, pending, age


def _candidate(name: str, direction: str, evidence: list[str], missing: list[str], strength: float, stage: str, invalidation: list[str]):
    return {
        "name": name,
        "direction": direction,
        "formation_stage": stage,
        "strength": round(strength, 2),
        "evidence": list(dict.fromkeys(evidence)),
        "missing": list(dict.fromkeys(missing)),
        "invalidation": list(dict.fromkeys(invalidation)),
    }


def _result(*, state: str, setup: str, direction: str, stage: str, maturity: str, thesis: str,
            quality: float, confidence: float, setup_exists: bool, trade_ready: bool,
            supporting: list[str], counter: list[str], missing: list[str], next_required: list[str],
            invalidation: list[str], candidates: list[dict[str, Any]], rejected: list[str],
            trace: dict[str, Any] | None = None) -> EngineResult:
    quality = max(0.0, min(100.0, quality))
    confidence = max(0.0, min(100.0, confidence))
    reasons = list(dict.fromkeys(counter + ([] if stage == "MATURE" else ["SETUP_NOT_MATURE"])))
    output = {
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "question": QUESTION,
        "role": "SETUP_ANALYST",
        "reasoning_role": "SETUP_FORMATION_REASONER",
        "decision_authority": "E9",
        "trade_decision_authority": False,
        "state": state,
        "setup_state": state,
        "finding": state,
        "setup": setup,
        "setup_family": setup,
        "direction": direction,
        "stage": stage,
        "formation_stage": stage,
        "lifecycle": stage,
        "maturity": maturity,
        "thesis": thesis,
        "setup_exists": setup_exists,
        "trade_ready": trade_ready,
        "trade_readiness": "READY" if trade_ready else "NOT_READY",
        "setup_quality": round(quality, 2),
        "confidence": round(confidence, 2),
        "candidate_setups": [x["name"] for x in candidates],
        "candidate_states": candidates,
        "rejected_setups": rejected,
        "supporting_evidence": list(dict.fromkeys(supporting)),
        "counter_evidence": list(dict.fromkeys(counter)),
        "missing_evidence": list(dict.fromkeys(missing)),
        "next_required_evidence": list(dict.fromkeys(next_required)),
        "invalidation": list(dict.fromkeys(invalidation)),
        "observations": [
            f"candidate_setups={','.join(x['name'] for x in candidates) if candidates else 'NONE'}",
            f"selected_setup={setup}",
            f"selected_direction={direction}",
            f"selected_stage={stage}",
            f"setup_exists={setup_exists}",
            f"trade_ready={trade_ready}",
            f"supporting_evidence={','.join(dict.fromkeys(supporting)) if supporting else 'NONE'}",
            f"counter_evidence={','.join(dict.fromkeys(counter)) if counter else 'NONE'}",
            f"missing_evidence={','.join(dict.fromkeys(missing)) if missing else 'NONE'}",
            f"next_required_evidence={','.join(dict.fromkeys(next_required)) if next_required else 'NONE'}",
            f"lifecycle={stage}",
            f"maturity={maturity}",
        ],
    }
    if trace:
        output["reasoning_trace"] = trace
    return EngineResult("E6", NAME, False, quality, output, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Synthesize E3/E4/E5 into a causal setup thesis without granting execution authority."""
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _result(
            state="NO_SETUP", setup="NONE", direction="NEUTRAL", stage="SEARCHING", maturity="UNRESOLVED",
            thesis="NO_SETUP: insufficient closed-candle history", quality=0.0, confidence=100.0,
            setup_exists=False, trade_ready=False, supporting=[], counter=[f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"],
            missing=["sufficient_closed_candle_data"], next_required=["more closed candles"],
            invalidation=["history remains insufficient"], candidates=[], rejected=[])

    try:
        atr = _atr(bars)
        if atr <= 0:
            raise ValueError("invalid atr")
        for bar in bars[-MIN_BARS:]:
            for key in ("open", "high", "low", "close"):
                float(bar[key])
    except (KeyError, TypeError, ValueError):
        return _result(
            state="NO_SETUP", setup="NONE", direction="NEUTRAL", stage="SEARCHING", maturity="UNRESOLVED",
            thesis="NO_SETUP: invalid market data", quality=0.0, confidence=100.0,
            setup_exists=False, trade_ready=False, supporting=[], counter=["INVALID_MARKET_DATA"],
            missing=["valid_ohlc_data"], next_required=["valid closed candle"],
            invalidation=["invalid market data"], candidates=[], rejected=[])

    e1, e2, e3, e4, e5 = (_payload(upstream, name) for name in ("E1", "E2", "E3", "E4", "E5"))
    direction, supporting, counter, direction_source = _evidence_direction(e1, e2, e3, e4)
    event, terminal, pending, event_age = _auction(e4)
    long_space, short_space, location_constrained, extension_risk = _location(e5)
    opportunity = _text(e2.get("finding", e2.get("state", "")))
    e3_finding = _text(e3.get("finding", e3.get("structure_state")))
    e3_internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    e3_external = _norm(e3.get("external_state", e3.get("external_count_state")))

    if event:
        supporting += [f"E4_EVENT={event}", f"E4_EVENT_AGE_BARS={event_age}"]
    if pending and not terminal:
        counter.append("LIQUIDITY_EVENT_PENDING")
    if "UNRESOLVED" in opportunity or "UNPROVEN" in opportunity:
        counter.append("OPPORTUNITY_MATURITY_UNPROVEN")
    if long_space or short_space:
        supporting += [f"STRUCTURAL_SPACE_LONG_ATR={long_space:.3f}", f"STRUCTURAL_SPACE_SHORT_ATR={short_space:.3f}"]
    if location_constrained:
        counter.append("LOCATION_CONSTRAINT")
    if extension_risk:
        counter.append("LOCATION_EXTENSION_RISK")
    if "MIXED" in e3_finding or "MIXED" in e3_internal:
        counter.append("STRUCTURE_MIXED")
    counter = list(dict.fromkeys(counter))

    # Setup existence is deliberately independent from trade economics. E5 can make a setup
    # unattractive without deleting the causal setup thesis.
    candidates: list[dict[str, Any]] = []
    rejected: list[str] = []
    auction_dir = _auction_direction(event)
    response = _norm(e4.get("response_actor"))
    bos = _text(e3.get("bos", e3.get("break_of_structure", "")))
    trend = _text(e1.get("trend_state", e1.get("finding", "")))
    structure_mixed = "MIXED" in e3_finding or "MIXED" in e3_internal

    if direction != "NEUTRAL":
        if auction_dir == direction and any(x in event for x in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM")):
            ev = ["E4_LIQUIDITY_EVENT"]
            missing = []
            if response == direction:
                ev.append("RESPONSE_ACTOR_ALIGNED")
            else:
                missing.append("aligned_auction_response")
            if terminal:
                ev.append("TERMINAL_AUCTION_CONFIRMATION")
            else:
                missing.append("terminal_liquidity_auction_confirmation")
            stage = "MATURE" if terminal and response == direction and not structure_mixed else "VALIDATING" if response == direction else "FORMING"
            candidates.append(_candidate("LIQUIDITY_REVERSAL", direction, ev, missing, 90.0 if stage == "MATURE" else 78.0 if stage == "VALIDATING" else 62.0, stage, ["loss_of_reclaim", "contrary_closed_candle_acceptance", "protected_level_break"]))
        if "BREAK" in bos and "NO_BREAK" not in bos and "FAILED_BOS" not in bos and e3_external == direction:
            ev = ["E3_CONFIRMED_STRUCTURE_BREAK"]
            missing = []
            if "RETEST" in _text(e3.get("lifecycle", e3.get("finding", ""))):
                ev.append("E3_RETEST_LIFECYCLE")
            else:
                missing.append("controlled_retest_or_acceptance")
            stage = "VALIDATING" if missing else "MATURE"
            candidates.append(_candidate("BREAKOUT_RETEST" if "RETEST" in ev else "BREAKOUT", direction, ev, missing, 76.0 if stage == "VALIDATING" else 88.0, stage, ["failed_retest", "close_back_inside_structure"]))
        if e3_external == direction and "NONE" not in trend and any(x in trend for x in ("UP", "DOWN", "TREND")) and not structure_mixed:
            candidates.append(_candidate("TREND_PULLBACK", direction, ["E1_TREND_CONTEXT", "E3_STRUCTURE_ALIGNMENT"], ["closed_candle_continuation_trigger"], 70.0, "VALIDATING", ["trend_alignment_lost", "protected_structure_failure"]))
        last = bars[-1]
        body = abs(_num(last.get("close")) - _num(last.get("open")))
        candle_dir = _norm("UP" if _num(last.get("close")) > _num(last.get("open")) else "DOWN")
        if body >= 0.8 * atr and candle_dir == direction and e3_external == direction:
            candidates.append(_candidate("IMPULSE_CONTINUATION", direction, ["DIRECTIONAL_IMPULSE", "E3_STRUCTURE_ALIGNMENT"], ["closed_candle_follow_through"], 66.0, "FORMING", ["impulse_failure", "countertrend_close"]))
    else:
        rejected.extend(f"{name}:direction_not_established" for name in SETUP_FAMILIES)

    candidates.sort(key=lambda x: (x["strength"], x["formation_stage"] == "MATURE"), reverse=True)
    if not candidates:
        missing = ["setup_specific_causal_sequence"]
        next_required = ["a closed-candle sequence that establishes a specific setup family"]
        if direction == "NEUTRAL":
            missing.append("directional_evidence_convergence")
            next_required.insert(0, "directional evidence convergence")
        if pending and not terminal:
            missing.append("terminal_liquidity_auction_confirmation")
            next_required.append("terminal liquidity acceptance/rejection")
        if "OPPORTUNITY_MATURITY_UNPROVEN" in counter:
            missing.append("opportunity_acceptance")
            next_required.append("closed-candle opportunity acceptance/follow-through")
        thesis = "NO_SETUP: no causal setup family is established" if direction == "NEUTRAL" else f"{direction}: directional thesis exists, but no setup family has a causal sequence yet"
        return _result(
            state="NO_SETUP" if direction == "NEUTRAL" else "FORMING",
            setup="NONE", direction=direction, stage="SEARCHING" if direction == "NEUTRAL" else "FORMING", maturity="UNRESOLVED",
            thesis=thesis, quality=12.0 if direction != "NEUTRAL" else 0.0, confidence=82.0,
            setup_exists=False, trade_ready=False, supporting=supporting, counter=counter,
            missing=missing, next_required=next_required,
            invalidation=["directional thesis invalidation", "setup-specific formation failure"],
            candidates=[], rejected=rejected,
            trace={"direction_source": direction_source, "e3_finding": e3_finding, "e4_event": event, "e5_location": _text(e5.get("finding", e5.get("state", ""))), "closed_candle_only": True, "lookahead": False})

    selected = candidates[0]
    setup = selected["name"]
    stage = selected["formation_stage"]
    setup_exists = True
    maturity = "MATURE" if stage == "MATURE" and not counter else "DEVELOPING"
    if maturity != "MATURE" and stage == "MATURE":
        stage = "VALIDATING"
        selected["formation_stage"] = stage

    missing = list(selected["missing"])
    next_required = list(missing)
    readiness_blockers: list[str] = []
    if direction == "BUY" and long_space < MIN_SPACE_ATR:
        readiness_blockers.append("INSUFFICIENT_LONG_STRUCTURAL_SPACE")
    if direction == "SELL" and short_space < MIN_SPACE_ATR:
        readiness_blockers.append("INSUFFICIENT_SHORT_STRUCTURAL_SPACE")
    if location_constrained or extension_risk:
        readiness_blockers.append("LOCATION_RISK")
    if "OPPORTUNITY_MATURITY_UNPROVEN" in counter:
        readiness_blockers.append("OPPORTUNITY_NOT_MATURE")
    if "DIRECTIONAL_EVIDENCE_CONFLICT" in counter:
        readiness_blockers.append("DIRECTIONAL_CONFLICT")
    if "STRUCTURE_MIXED" in counter:
        readiness_blockers.append("STRUCTURE_MIXED")
    if "LIQUIDITY_EVENT_PENDING" in counter:
        readiness_blockers.append("LIQUIDITY_PENDING")
    missing.extend(readiness_blockers)
    next_required.extend(readiness_blockers)
    next_required.append("E7 independent closed-candle entry confirmation")

    thesis_parts = [f"{direction} {setup}", f"stage={stage}", f"causal_evidence={','.join(selected['evidence'])}"]
    if counter:
        thesis_parts.append(f"counter_evidence={','.join(counter)}")
    thesis = " | ".join(thesis_parts)
    quality = selected["strength"] - min(25.0, 5.0 * len(counter))
    confidence = max(55.0, min(96.0, selected["strength"] + 5.0 - 5.0 * len(counter)))

    return _result(
        state="MATURE" if maturity == "MATURE" else "FORMING",
        setup=setup, direction=direction, stage=stage, maturity=maturity, thesis=thesis,
        quality=quality, confidence=confidence, setup_exists=True, trade_ready=False,
        supporting=supporting + [f"SETUP_THESIS={thesis}"], counter=counter,
        missing=list(dict.fromkeys(missing)), next_required=list(dict.fromkeys(next_required)),
        invalidation=selected["invalidation"] + ["directional thesis becomes contradictory", "causal sequence invalidated"],
        candidates=candidates, rejected=rejected,
        trace={
            "direction_source": direction_source,
            "e1_trend_state": trend,
            "e2_opportunity": opportunity,
            "e3_finding": e3_finding,
            "e3_external": e3_external,
            "e4_event": event,
            "e4_terminal": terminal,
            "e4_pending": pending,
            "e4_event_age_bars": event_age,
            "e5_location": _text(e5.get("finding", e5.get("state", ""))),
            "setup_exists": True,
            "trade_ready": False,
            "readiness_blockers": readiness_blockers,
            "closed_candle_only": True,
            "lookahead": False,
        })
