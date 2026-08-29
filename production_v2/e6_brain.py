from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V22"
VERSION = "22.0"
MIN_BARS = 60
ATR_PERIOD = 14
MIN_SPACE_ATR = 0.75

SETUP_FAMILIES = (
    "LIQUIDITY_REVERSAL",
    "AUCTION_ACCEPTANCE_CONTINUATION",
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


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values if v))


def _atr(bars: list[dict[str, Any]]) -> float:
    sample = bars[-(ATR_PERIOD + 1) :]
    if len(sample) < 2:
        return 0.0
    trs: list[float] = []
    for i, candle in enumerate(sample):
        high = _num(candle.get("high"))
        low = _num(candle.get("low"))
        if i == 0:
            trs.append(max(0.0, high - low))
        else:
            prev = _num(sample[i - 1].get("close"))
            trs.append(max(high - low, abs(high - prev), abs(low - prev)))
    return mean(trs[-ATR_PERIOD:]) if trs else 0.0


def _auction(e4: dict[str, Any]) -> dict[str, Any]:
    event = _text(e4.get("event", e4.get("finding")))
    state = _text(e4.get("auction_state", e4.get("state")))
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    pending = state == "PENDING" or "PENDING" in event
    direction = "NEUTRAL"
    if "HIGH_SWEEP_REJECTION" in event or "HIGH_FAILED_BREAK_RECLAIM" in event:
        direction = "SELL"
    elif "LOW_SWEEP_REJECTION" in event or "LOW_FAILED_BREAK_RECLAIM" in event:
        direction = "BUY"
    elif "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
        direction = "BUY"
    elif "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
        direction = "SELL"
    return {
        "event": event,
        "state": state,
        "terminal": terminal,
        "pending": pending,
        "age_bars": max(0, int(_num(e4.get("event_age_bars"), 0))),
        "direction": direction,
        "level": _num(e4.get("event_level")),
    }


def _direction_thesis(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any]) -> tuple[str, list[str], list[str], str]:
    auction = _auction(e4)
    sources = {
        "E1_PRESSURE": _norm(e1.get("directional_pressure", e1.get("pressure"))),
        "E3_EXTERNAL": _norm(e3.get("external_state", e3.get("external_count_state"))),
        "E4_AUCTION": auction["direction"],
    }
    votes = [v for v in sources.values() if v != "NEUTRAL"]
    unique = set(votes)
    support = [f"{k}={v}" for k, v in sources.items() if v != "NEUTRAL"]
    counter: list[str] = []
    if len(unique) > 1:
        direction, source = "NEUTRAL", "DIRECTIONAL_CONFLICT"
        counter.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    elif len(unique) == 1:
        direction = next(iter(unique))
        source = "E1_E3_E4_CONVERGENCE" if len(votes) >= 2 else "LIMITED_DIRECTIONAL_EVIDENCE"
    else:
        direction, source = "NEUTRAL", "NO_DIRECTIONAL_CONVERGENCE"
        counter.append("INSUFFICIENT_DIRECTIONAL_EVIDENCE")

    e2_finding = _text(e2.get("finding", e2.get("state")))
    e2_direction = _norm(e2.get("direction", e2.get("opportunity_direction")))
    if e2_direction != "NEUTRAL" and not any(x in e2_finding for x in ("UNRESOLVED", "UNPROVEN")):
        if direction == "NEUTRAL":
            direction, source = e2_direction, "E2_CORROBORATION"
        elif direction == e2_direction:
            support.append(f"E2_DIRECTION={e2_direction}")
        else:
            counter.append("E2_DIRECTION_DISAGREEMENT")

    if "MIXED" in _text(e3.get("finding", e3.get("structure_state"))) or "MIXED" in _text(e3.get("internal_state", e3.get("internal_count_state"))):
        counter.append("STRUCTURE_MIXED")
    return direction, _dedupe(support), _dedupe(counter), source


def _evidence(source: str, statement: str, kind: str = "SUPPORT", strength: str = "MEDIUM") -> dict[str, str]:
    return {"source": source, "kind": kind, "strength": strength, "statement": statement}


def _build_result(
    state: str, setup: str, direction: str, stage: str, maturity: str,
    thesis: str, quality: float, confidence: float, exists: bool, ready: bool,
    supporting: list[str], counter: list[str], missing: list[str],
    next_required: list[str], invalidation: list[str], candidates: list[dict[str, Any]],
    rejected: list[str], trace: dict[str, Any], ledger: list[dict[str, str]],
) -> EngineResult:
    supporting, counter = _dedupe(supporting), _dedupe(counter)
    missing, next_required = _dedupe(missing), _dedupe(next_required)
    invalidation = _dedupe(invalidation)
    quality = max(0.0, min(100.0, float(quality)))
    confidence = max(0.0, min(100.0, float(confidence)))

    observations = [
        f"candidate_setups={','.join(c.get('name', 'UNKNOWN') for c in candidates) or 'NONE'}",
        f"selected_setup={setup}",
        f"selected_direction={direction}",
        f"direction_thesis={thesis}",
        f"stage={stage}",
        f"maturity={maturity}",
        f"setup_exists={exists}",
        f"trade_ready={ready}",
        f"supporting_evidence={' | '.join(supporting) or 'NONE'}",
        f"counter_evidence={' | '.join(counter) or 'NONE'}",
        f"missing_evidence={' | '.join(missing) or 'NONE'}",
        f"next_required_evidence={' | '.join(next_required) or 'NONE'}",
        f"invalidation={' | '.join(invalidation) or 'NONE'}",
        f"reasoning_trace={trace.get('summary', 'NONE')}",
    ]
    output = {
        "architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION,
        "role": "SETUP_FORMATION_REASONER", "reasoning_role": "SETUP_FORMATION_REASONER",
        "decision_authority": "E9", "trade_decision_authority": False,
        "state": state, "setup_state": state, "finding": state,
        "setup": setup, "setup_family": setup, "candidate_setup": setup,
        "direction": direction, "direction_thesis": thesis,
        "stage": stage, "formation_stage": stage, "lifecycle": stage,
        "maturity": maturity, "thesis": thesis,
        "setup_exists": exists, "trade_ready": ready,
        "trade_readiness": "READY" if ready else "NOT_READY",
        "setup_quality": round(quality, 2), "confidence": round(confidence, 2),
        "candidate_setups": [c.get("name") for c in candidates],
        "candidate_states": candidates, "rejected_setups": _dedupe(rejected),
        "supporting_evidence": supporting, "counter_evidence": counter,
        "missing_evidence": missing, "next_required_evidence": next_required,
        "invalidation": invalidation, "evidence_ledger": ledger,
        "observations": observations, "reasoning_trace": trace,
        "professional_reasoning": {
            "what_is_forming": setup, "why_it_is_forming": supporting,
            "what_is_wrong_with_the_thesis": counter, "what_is_missing": missing,
            "what_must_happen_next": next_required, "what_invalidates_it": invalidation,
            "decision_boundary": "E6 describes and stages the setup; E9 alone decides whether a trade is permitted.",
        },
        "reason_codes": counter + ([] if ready else ["SETUP_NOT_TRADE_READY"]),
    }
    return EngineResult("E6", NAME, False, quality, output, tuple(_dedupe(output["reason_codes"])))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Professional setup formation reasoning; E6 never manufactures an execution decision."""
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _build_result(
            "NO_SETUP", "NONE", "NEUTRAL", "SEARCHING", "UNRESOLVED",
            "Setup reasoning is deferred until sufficient closed-candle evidence exists.",
            0, 100, False, False, [], [f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"],
            ["sufficient_closed_candle_data"], [f"wait for at least {MIN_BARS} valid closed candles"],
            ["insufficient_history"], [], list(SETUP_FAMILIES),
            {"summary": "insufficient closed-candle history", "decision": "DEFER"},
            [_evidence("DATA", f"closed_candles={len(bars)}", "CONSTRAINT", "HIGH")],
        )

    try:
        atr = _atr(bars)
        if atr <= 0:
            raise ValueError("invalid ATR")
        for candle in bars[-MIN_BARS:]:
            for key in ("open", "high", "low", "close"):
                value = float(candle[key])
                if value != value:
                    raise ValueError("NaN OHLC")
    except (KeyError, TypeError, ValueError):
        return _build_result(
            "NO_SETUP", "NONE", "NEUTRAL", "SEARCHING", "UNRESOLVED",
            "Setup reasoning is deferred because closed-candle OHLC data is invalid.",
            0, 100, False, False, [], ["INVALID_MARKET_DATA"], ["valid_closed_candle_ohlc"],
            ["provide valid closed-candle OHLC values"], ["invalid_market_data"], [],
            list(SETUP_FAMILIES), {"summary": "invalid closed-candle data", "decision": "DEFER"},
            [_evidence("DATA", "closed-candle OHLC validation failed", "CONSTRAINT", "HIGH")],
        )

    e1, e2, e3 = _payload(upstream, "E1"), _payload(upstream, "E2"), _payload(upstream, "E3")
    e4, e5 = _payload(upstream, "E4"), _payload(upstream, "E5")
    auction = _auction(e4)
    direction, direction_support, direction_counter, direction_source = _direction_thesis(e1, e2, e3, e4)
    opportunity = _text(e2.get("finding", e2.get("state")))
    structure = _text(e3.get("finding", e3.get("structure_state")))
    internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    mixed = "MIXED" in structure or "MIXED" in internal
    trend = _norm(e1.get("trend_state", e1.get("finding")))
    bos = _text(e3.get("bos", e3.get("break_of_structure")))
    sequence = _text(e3.get("sequence"))
    value_response = _text(e5.get("value_response", e5.get("repricing_state")))
    space = _num(e5.get("available_space_atr_long")) if direction == "BUY" else _num(e5.get("available_space_atr_short"))

    counter = list(direction_counter)
    ledger: list[dict[str, str]] = []
    candidates: list[dict[str, Any]] = []
    rejected: list[str] = []
    opportunity_unresolved = any(x in opportunity for x in ("UNRESOLVED", "UNPROVEN"))

    if direction != "NEUTRAL":
        ledger.extend([
            _evidence("E1", f"pressure={_norm(e1.get('pressure'))}; trend={trend}"),
            _evidence("E3", f"structure={structure or 'UNKNOWN'}; internal={internal or 'UNKNOWN'}"),
            _evidence("E4", f"event={auction['event'] or 'NONE'}; direction={auction['direction']}; state={auction['state'] or 'UNKNOWN'}"),
            _evidence("E5", f"value_response={value_response or 'UNKNOWN'}; space={space:.3f} ATR"),
        ])
    else:
        ledger.append(_evidence("DIRECTION", "independent evidence does not converge", "CONSTRAINT", "HIGH"))
    if opportunity_unresolved:
        counter.append("OPPORTUNITY_MATURITY_UNPROVEN")
        ledger.append(_evidence("E2", "opportunity thesis remains unresolved/unproven", "COUNTER", "HIGH"))
    if mixed:
        counter.append("STRUCTURE_MIXED")
        ledger.append(_evidence("E3", "external/internal structure remains mixed", "COUNTER", "HIGH"))
    if auction["pending"]:
        counter.append("LIQUIDITY_EVENT_PENDING")
        ledger.append(_evidence("E4", "auction evidence is pending and not terminal confirmation", "COUNTER", "HIGH"))
    if direction != "NEUTRAL" and space < MIN_SPACE_ATR:
        counter.append("STRUCTURAL_SPACE_CONSTRAINED")
        ledger.append(_evidence("E5", f"available space {space:.3f} ATR is below {MIN_SPACE_ATR:.2f} ATR", "COUNTER", "HIGH"))
    counter = _dedupe(counter)
    hard_veto = direction == "NEUTRAL" or "DIRECTIONAL_EVIDENCE_CONFLICT" in counter

    def add(name: str, stage: str, strength: float, support: list[str], missing: list[str], next_required: list[str], invalidation: list[str]) -> None:
        candidates.append({
            "name": name, "identity": f"{name}:{direction}", "direction": direction,
            "formation_stage": stage, "strength": max(0, min(100, strength)),
            "supporting_evidence": _dedupe(support), "counter_evidence": list(counter),
            "missing_evidence": _dedupe(missing), "next_required_evidence": _dedupe(next_required),
            "invalidation": _dedupe(invalidation),
        })

    if not hard_veto and auction["direction"] == direction and "ACCEPTANCE" in auction["event"]:
        missing = []
        if auction["pending"]: missing += ["terminal_auction_confirmation", "closed_candle_follow_through"]
        if mixed: missing.append("structural_direction_confirmation")
        if space < MIN_SPACE_ATR: missing.append("adequate_structural_space")
        if opportunity_unresolved: missing.append("opportunity_acceptance_follow_through")
        add(
            "AUCTION_ACCEPTANCE_CONTINUATION", "VALIDATING",
            64 + (8 if value_response else 0) + (8 if auction["terminal"] else 0) - (6 if mixed else 0) - (6 if auction["pending"] else 0),
            ["directional_auction_event", "value_response_context" if value_response else "auction_location_context"],
            missing,
            [f"closed-candle {direction} follow-through after auction acceptance",
             "auction transitions from PENDING to terminal confirmation" if auction["pending"] else "continued acceptance without failure",
             "structure resolves into directional confirmation" if mixed else "maintain structural integrity"],
            ["acceptance_failure", "reclaim_through_accepted_auction_level"],
        )

    if not hard_veto and auction["direction"] == direction and any(x in auction["event"] for x in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM")):
        add("LIQUIDITY_REVERSAL", "VALIDATING", 66 + (8 if auction["terminal"] else 0) - (8 if mixed else 0),
            ["liquidity_event_with_directional_response"],
            (["terminal_auction_confirmation"] if not auction["terminal"] else []) + (["structural_direction_confirmation"] if mixed else []),
            ["closed-candle rejection holds", "follow-through in reversal direction"],
            ["auction_response_failure", "loss_of_protected_structure"])

    if not hard_veto and direction == trend and not mixed:
        if "BREAK" in bos and "NO_BREAK" not in bos:
            name = "BREAKOUT_RETEST" if "RETEST" in _text(e3) else "BREAKOUT"
            add(name, "VALIDATING", 58 if auction["terminal"] else 50,
                ["trend_direction_aligned", f"structure_event={bos}"],
                ["closed_candle_follow_through", "acceptance_after_break"],
                ["closed-candle acceptance beyond broken level", "follow-through without immediate reclaim"],
                ["breakout_failure", "reclaim_inside_prior_structure"])
        elif "HL" in sequence or "LH" in sequence:
            add("TREND_PULLBACK", "FORMING", 42,
                ["directional_structure_present_but_trigger_not_proven"],
                ["impulse_then_pullback_sequence", "continuation_trigger"],
                ["confirmed pullback into meaningful structure", "closed-candle continuation trigger"],
                ["loss_of_protected_structure"])

    for c in candidates:
        c["counter_evidence"] = _dedupe(c["counter_evidence"])

    # Professional selection: identify a hypothesis, but never manufacture maturity.
    if not candidates:
        setup, exists, stage = "NONE", False, "FORMING"
        missing = ["directional_convergence", "causal_setup_sequence"]
        next_required = ["closed-candle evidence resolving direction and establishing a causal setup sequence"]
        thesis = "No defensible setup hypothesis exists yet; professional action is to wait rather than manufacture a setup."
        quality, confidence = 20, 84
        rejected = list(SETUP_FAMILIES)
    else:
        candidates.sort(key=lambda c: c["strength"], reverse=True)
        best = candidates[0]
        setup, exists = best["name"], True
        missing, next_required = list(best["missing_evidence"]), list(best["next_required_evidence"])
        if opportunity_unresolved:
            missing.append("opportunity_acceptance_follow_through")
            next_required.append("E2 opportunity thesis becoming resolved through closed-candle follow-through")
        missing, next_required = _dedupe(missing), _dedupe(next_required)

        if len(candidates) > 1 and best["strength"] - candidates[1]["strength"] < 8:
            setup, stage = "AMBIGUOUS", "FORMING"
            thesis = "Competing setup hypotheses are too close to justify false precision; wait for discriminating evidence."
            missing.append("discriminating_evidence_between_candidate_setups")
            next_required.append("closed-candle evidence distinguishing the leading hypotheses")
            quality, confidence = max(20, best["strength"] - 10), 70
            rejected = [c["name"] for c in candidates]
        else:
            # MATURE requires every critical proof, not merely a high score.
            critical_missing = {
                "terminal_auction_confirmation", "closed_candle_follow_through",
                "structural_direction_confirmation", "opportunity_acceptance_follow_through",
                "adequate_structural_space", "acceptance_after_break",
            }
            blockers = critical_missing.intersection(missing)
            mature = (
                best["formation_stage"] == "VALIDATING" and not blockers and not mixed
                and not hard_veto and direction != "NEUTRAL" and space >= MIN_SPACE_ATR
                and not opportunity_unresolved
            )
            stage = "MATURE" if mature else best["formation_stage"]
            thesis = f"{direction} {setup} is {stage.lower()}: evidence supports a conditional formation thesis; remaining proof requirements stay explicit."
            quality = best["strength"]
            confidence = max(45, min(95, 56 + 7 * len(best["supporting_evidence"]) - 5 * len(missing)))

    if direction != "NEUTRAL" and space < MIN_SPACE_ATR:
        counter = _dedupe(counter + ["STRUCTURAL_SPACE_CONSTRAINED"])

    maturity = "MATURE" if stage == "MATURE" else "VALIDATING" if stage == "VALIDATING" else "FORMING"
    # E6 readiness is descriptive only; E9 remains the trade authority.
    ready = (
        exists and setup not in {"NONE", "AMBIGUOUS"} and stage == "MATURE"
        and direction != "NEUTRAL" and space >= MIN_SPACE_ATR
        and not auction["pending"] and not opportunity_unresolved and not mixed
    )

    invalidation: list[str] = []
    for c in candidates:
        invalidation.extend(c.get("invalidation", []))
    protected_high = _num(e3.get("protected_high"))
    protected_low = _num(e3.get("protected_low"))
    if auction["level"] > 0:
        invalidation.append(f"event_level_invalidation_reference={auction['level']:.5f}")
    if direction == "BUY" and protected_low > 0:
        invalidation.append(f"protected_low_failure={protected_low:.5f}")
    if direction == "SELL" and protected_high > 0:
        invalidation.append(f"protected_high_failure={protected_high:.5f}")
    invalidation = _dedupe(invalidation)[:12]

    selected = next((c for c in candidates if c["name"] == setup), None)
    if selected:
        selected["selected"] = True

    trace = {
        "summary": f"direction={direction}; candidate={setup}; lifecycle={stage}; blockers={','.join(missing) or 'NONE'}",
        "direction_source": direction_source,
        "directional_veto": hard_veto,
        "candidate_identity": selected.get("identity") if selected else None,
        "selection_confidence": round(confidence, 2),
        "auction": auction,
        "structure": {"finding": structure or "UNKNOWN", "internal": internal or "UNKNOWN", "bos": bos or "UNKNOWN", "sequence": sequence or "UNKNOWN", "mixed": mixed},
        "location": {"space_atr": round(space, 4), "minimum_space_atr": MIN_SPACE_ATR, "value_response": value_response or "UNKNOWN"},
        "opportunity": {"finding": opportunity or "UNKNOWN", "resolved": not opportunity_unresolved},
        "hypothesis_count": len(candidates),
        "selection_rule": "causal evidence -> direction -> candidate identity -> support/counter -> missing proof -> lifecycle -> invalidation",
        "professional_rule": "Preserve conditional hypotheses, expose uncertainty, reject false precision, require closed-candle proof, and never usurp E9 trade authority.",
    }

    return _build_result(
        stage, setup, direction, stage, maturity, thesis, quality, confidence, exists, ready,
        direction_support + (selected.get("supporting_evidence", []) if selected else []),
        counter, missing, next_required, invalidation, candidates, rejected, trace, ledger,
    )
