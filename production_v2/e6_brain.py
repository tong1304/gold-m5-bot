from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V20"
VERSION = "20.0"
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


def _atr(bars: list[dict[str, Any]]) -> float:
    if len(bars) < 2:
        return 0.0
    sample = bars[-(ATR_PERIOD + 1) :]
    true_ranges: list[float] = []
    for i, candle in enumerate(sample):
        high = _num(candle.get("high"))
        low = _num(candle.get("low"))
        previous_close = _num(sample[i - 1].get("close")) if i else 0.0
        if i == 0:
            true_ranges.append(max(0.0, high - low))
        else:
            true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return mean(true_ranges[-ATR_PERIOD:]) if true_ranges else 0.0


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


def _auction(e4: dict[str, Any]) -> tuple[str, bool, bool, int]:
    state = _text(e4.get("auction_state", e4.get("state")))
    event = _text(e4.get("event", e4.get("finding")))
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    pending = state == "PENDING" or "PENDING" in event
    age = max(0, int(_num(e4.get("event_age_bars"), 0)))
    return event, terminal, pending, age


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(x for x in values if x))


def _dirs(
    e1: dict[str, Any],
    e2: dict[str, Any],
    e3: dict[str, Any],
    e4: dict[str, Any],
) -> tuple[str, list[str], list[str], str]:
    sources = {
        "E1_PRESSURE": _norm(e1.get("directional_pressure", e1.get("pressure"))),
        "E3_EXTERNAL": _norm(e3.get("external_state", e3.get("external_count_state"))),
        "E4_AUCTION": _auction_direction(_text(e4.get("event", e4.get("finding")))),
    }
    votes = [value for value in sources.values() if value != "NEUTRAL"]
    unique = set(votes)
    supporting = [f"{key}={value}" for key, value in sources.items() if value != "NEUTRAL"]
    counter: list[str] = []

    if len(unique) > 1:
        direction = "NEUTRAL"
        source = "INDEPENDENT_EVIDENCE_CONFLICT"
        counter.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    elif len(unique) == 1:
        direction = next(iter(unique))
        source = "E1_E3_E4_CONVERGENCE" if len(votes) >= 2 else "INDEPENDENT_EVIDENCE"
    else:
        direction = "NEUTRAL"
        source = "INSUFFICIENT_CONVERGENCE"

    e2_directions = [
        value
        for value in (_norm(e2.get("direction")), _norm(e2.get("opportunity_direction")))
        if value != "NEUTRAL"
    ]
    e2_finding = _text(e2.get("finding", e2.get("state")))
    if e2_directions and len(set(e2_directions)) == 1 and not any(
        marker in e2_finding for marker in ("UNRESOLVED", "UNPROVEN")
    ):
        if direction == "NEUTRAL":
            direction = e2_directions[0]
            source = "E2_CORROBORATION_ONLY"
        supporting.append(f"E2_DIRECTION={e2_directions[0]}")
        if direction != e2_directions[0]:
            counter.append("E2_DIRECTION_DISAGREEMENT")
    if len(e2_directions) > 1:
        counter.append("E2_INTERNAL_DIRECTION_CONFLICT")

    e3_finding = _text(e3.get("finding", e3.get("structure_state")))
    e3_internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    if "MIXED" in e3_finding or "MIXED" in e3_internal:
        counter.append("STRUCTURE_MIXED")

    return direction, _dedupe(supporting + [f"DIRECTION_SOURCE={source}"]), _dedupe(counter), source


def _evidence_item(source: str, statement: str, kind: str = "SUPPORT") -> dict[str, str]:
    return {"source": source, "kind": kind, "statement": statement}


def _out(
    state: str,
    setup: str,
    direction: str,
    stage: str,
    maturity: str,
    thesis: str,
    quality: float,
    confidence: float,
    exists: bool,
    ready: bool,
    supporting: list[str],
    counter: list[str],
    missing: list[str],
    next_required: list[str],
    invalidation: list[str],
    candidates: list[dict[str, Any]],
    rejected: list[str],
    trace: dict[str, Any],
    evidence_ledger: list[dict[str, str]] | None = None,
) -> EngineResult:
    supporting = _dedupe(supporting)
    counter = _dedupe(counter)
    missing = _dedupe(missing)
    next_required = _dedupe(next_required)
    invalidation = _dedupe(invalidation)
    quality = max(0.0, min(100.0, quality))
    confidence = max(0.0, min(100.0, confidence))
    reasons = _dedupe(counter + ([] if ready else ["SETUP_NOT_TRADE_READY"]))

    observations = [
        f"candidate_setups={','.join(x['name'] for x in candidates) if candidates else 'NONE'}",
        f"selected_setup={setup}",
        f"selected_direction={direction}",
        f"selected_stage={stage}",
        f"setup_exists={exists}",
        f"trade_ready={ready}",
        f"supporting_evidence={','.join(supporting) if supporting else 'NONE'}",
        f"counter_evidence={','.join(counter) if counter else 'NONE'}",
        f"missing_evidence={','.join(missing) if missing else 'NONE'}",
        f"next_required_evidence={','.join(next_required) if next_required else 'NONE'}",
        f"invalidation={','.join(invalidation) if invalidation else 'NONE'}",
        f"lifecycle={stage}",
        f"maturity={maturity}",
    ]

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
        "direction_thesis": direction,
        "stage": stage,
        "formation_stage": stage,
        "lifecycle": stage,
        "maturity": maturity,
        "thesis": thesis,
        "setup_exists": exists,
        "trade_ready": ready,
        "trade_readiness": "READY" if ready else "NOT_READY",
        "setup_quality": round(quality, 2),
        "confidence": round(confidence, 2),
        "candidate_setups": [candidate["name"] for candidate in candidates],
        "candidate_states": candidates,
        "rejected_setups": _dedupe(rejected),
        "supporting_evidence": supporting,
        "counter_evidence": counter,
        "missing_evidence": missing,
        "next_required_evidence": next_required,
        "invalidation": invalidation,
        "evidence_ledger": evidence_ledger or [],
        "observations": observations,
        "reasoning_trace": trace,
    }
    return EngineResult("E6", NAME, False, quality, output, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _out(
            "NO_SETUP",
            "NONE",
            "NEUTRAL",
            "SEARCHING",
            "UNRESOLVED",
            "Setup reasoning is deferred because the closed-candle sample is insufficient.",
            0,
            100,
            False,
            False,
            [],
            [f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"],
            ["sufficient_closed_candle_data"],
            [f"wait for at least {MIN_BARS} valid closed candles"],
            ["history remains insufficient"],
            [],
            [],
            {"decision": "NO_SETUP", "cause": "INSUFFICIENT_HISTORY"},
            [_evidence_item("DATA", f"closed_candles={len(bars)}", "CONSTRAINT")],
        )

    try:
        atr = _atr(bars)
        if atr <= 0:
            raise ValueError
        for candle in bars[-MIN_BARS:]:
            for key in ("open", "high", "low", "close"):
                value = float(candle[key])
                if value != value:
                    raise ValueError
    except (KeyError, TypeError, ValueError):
        return _out(
            "NO_SETUP",
            "NONE",
            "NEUTRAL",
            "SEARCHING",
            "UNRESOLVED",
            "Setup reasoning is deferred because closed-candle OHLC data is invalid.",
            0,
            100,
            False,
            False,
            [],
            ["INVALID_MARKET_DATA"],
            ["valid_closed_candle_ohlc"],
            ["provide valid closed-candle OHLC values"],
            ["invalid market data"],
            [],
            [],
            {"decision": "NO_SETUP", "cause": "INVALID_DATA"},
            [_evidence_item("DATA", "closed-candle OHLC validation failed", "CONSTRAINT")],
        )

    e1, e2, e3, e4, e5 = (_payload(upstream, name) for name in ("E1", "E2", "E3", "E4", "E5"))
    direction, supporting, counter, direction_source = _dirs(e1, e2, e3, e4)
    event, terminal, pending, age = _auction(e4)
    auction_direction = _auction_direction(event)
    opportunity_finding = _text(e2.get("finding", e2.get("state", "")))
    structure_finding = _text(e3.get("finding", e3.get("structure_state", "")))
    internal_structure = _text(e3.get("internal_state", e3.get("internal_count_state", "")))
    structure_mixed = "MIXED" in structure_finding or "MIXED" in internal_structure
    trend_direction = _norm(e1.get("trend_state", e1.get("finding")))
    bos = _text(e3.get("bos", e3.get("break_of_structure", "")))
    sequence = _text(e3.get("sequence", ""))
    value_response = _text(e5.get("value_response", e5.get("repricing_state", "")))
    space = (
        _num(e5.get("available_space_atr_long"))
        if direction == "BUY"
        else _num(e5.get("available_space_atr_short"))
    )

    candidates: list[dict[str, Any]] = []
    rejected: list[str] = []
    evidence_ledger: list[dict[str, str]] = []

    # E6 is a formation reasoner. It can preserve a conditional hypothesis while
    # explicitly refusing to promote it to a trade. A directional conflict is the
    # only hard veto at this stage because a setup without a coherent direction is
    # not a defensible setup thesis.
    hard_direction_veto = direction == "NEUTRAL" or "DIRECTIONAL_EVIDENCE_CONFLICT" in counter

    if direction != "NEUTRAL":
        evidence_ledger.append(_evidence_item("E1", f"pressure={_norm(e1.get('pressure'))}; trend={trend_direction}"))
        evidence_ledger.append(_evidence_item("E3", f"external={structure_finding}; internal={internal_structure}"))
        evidence_ledger.append(_evidence_item("E4", f"event={event or 'NONE'}; auction_direction={auction_direction}; state={'TERMINAL' if terminal else 'PENDING' if pending else 'UNKNOWN'}"))
        evidence_ledger.append(_evidence_item("E5", f"value_response={value_response or 'UNKNOWN'}; space_atr={space:.3f}"))
    else:
        evidence_ledger.append(_evidence_item("DIRECTION", "directional evidence does not converge", "CONSTRAINT"))

    if not hard_direction_veto:
        # 1) Auction acceptance continuation.
        if auction_direction == direction and "ACCEPTANCE" in event:
            acceptance_context = any(
                token in value_response
                for token in (
                    "ACCEPTED_ABOVE_VALUE",
                    "ACCEPTANCE_ABOVE_VALUE",
                    "ACCEPTED_BELOW_VALUE",
                    "ACCEPTANCE_BELOW_VALUE",
                    "EQUILIBRIUM",
                )
            )
            strength = 56 + (10 if acceptance_context else 0) + (8 if not pending else 0)
            if structure_mixed:
                strength -= 6
            candidate = {
                "name": "AUCTION_ACCEPTANCE_CONTINUATION",
                "direction": direction,
                "formation_stage": "VALIDATING",
                "strength": max(0, min(100, strength)),
                "evidence": [
                    f"E4_EVENT={event}",
                    f"E4_AUCTION_STATE={'TERMINAL' if terminal else 'PENDING' if pending else 'UNKNOWN'}",
                    f"E5_VALUE_RESPONSE={value_response or 'UNKNOWN'}",
                    f"E1_PRESSURE={_norm(e1.get('pressure'))}",
                ],
                "supporting_evidence": [
                    "buyers_or_sellers_have_defined_auction_direction",
                    "value_response_supports_repricing_context" if acceptance_context else "auction_event_provides_location_context",
                ],
                "counter_evidence": [],
                "missing_evidence": [],
                "next_required_evidence": [],
                "invalidation": [
                    "acceptance_failure",
                    "reclaim_through_accepted_auction_level",
                ],
            }
            # Terminal auction is not sufficient by itself. Professional maturity
            # requires follow-through and an intact structural thesis.
            if pending:
                candidate["missing_evidence"] += [
                    "terminal_auction_confirmation",
                    "closed_candle_follow_through",
                ]
            if structure_mixed:
                candidate["missing_evidence"].append("structural_direction_confirmation")
            if space < MIN_SPACE_ATR:
                candidate["missing_evidence"].append("adequate_structural_space")
            candidate["missing_evidence"] = _dedupe(candidate["missing_evidence"])
            candidate["next_required_evidence"] = [
                f"closed-candle evidence proving {direction} follow-through at the accepted auction",
                "auction state transitions from PENDING to terminal confirmation" if pending else "continued acceptance without failure",
            ]
            if structure_mixed:
                candidate["next_required_evidence"].append("price structure resolves from MIXED into directional confirmation")
            candidates.append(candidate)

        # 2) Liquidity reversal.
        if auction_direction == direction and any(token in event for token in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM")):
            candidate = {
                "name": "LIQUIDITY_REVERSAL",
                "direction": direction,
                "formation_stage": "VALIDATING",
                "strength": min(100, 58 + (12 if _norm(e4.get("response_actor")) == direction else 0) + (8 if terminal else 0) - (6 if structure_mixed else 0)),
                "evidence": [
                    f"E4_EVENT={event}",
                    f"E4_RESPONSE={_norm(e4.get('response_actor'))}",
                    f"EVENT_AGE_BARS={age}",
                ],
                "supporting_evidence": ["liquidity_event_has_directional_response"],
                "counter_evidence": [],
                "missing_evidence": [],
                "next_required_evidence": [],
                "invalidation": [
                    "auction_response_failure",
                    "loss_of_structural_invalidation_level",
                ],
            }
            if not terminal:
                candidate["missing_evidence"].append("terminal_auction_confirmation")
            if structure_mixed:
                candidate["missing_evidence"].append("structural_direction_confirmation")
            candidate["missing_evidence"] = _dedupe(candidate["missing_evidence"])
            candidate["next_required_evidence"] = [
                "closed-candle confirmation that the liquidity rejection is holding",
                "follow-through in the reversal direction",
            ]
            candidates.append(candidate)

        # 3) Trend / breakout families are deliberately weaker than a causal auction
        # event. E6 should not manufacture a breakout from an EMA state alone.
        if direction == trend_direction and not structure_mixed:
            if "BREAK" in bos and "NO_BREAK" not in bos:
                name = "BREAKOUT_RETEST" if "RETEST" in _text(e3) else "BREAKOUT"
                candidate = {
                    "name": name,
                    "direction": direction,
                    "formation_stage": "VALIDATING",
                    "strength": 58 if terminal else 50,
                    "evidence": ["DIRECTIONAL_TREND_ALIGNMENT", f"STRUCTURE_EVENT={bos}"],
                    "supporting_evidence": ["trend_direction_and_structure_event_align"],
                    "counter_evidence": [],
                    "missing_evidence": ["closed_candle_follow_through", "acceptance_after_break"],
                    "next_required_evidence": [
                        "closed-candle acceptance beyond the broken structural level",
                        "follow-through without immediate reclaim",
                    ],
                    "invalidation": ["breakout_failure", "reclaim_inside_prior_structure"],
                }
                candidates.append(candidate)
            elif "HL" in sequence or "LH" in sequence:
                candidates.append({
                    "name": "TREND_PULLBACK",
                    "direction": direction,
                    "formation_stage": "FORMING",
                    "strength": 42,
                    "evidence": ["TREND_DIRECTION_ALIGNED", f"STRUCTURE_SEQUENCE={sequence}"],
                    "supporting_evidence": ["directional_structure_is_present_but_trigger_is_not_proven"],
                    "counter_evidence": [],
                    "missing_evidence": ["impulse_then_pullback_sequence", "continuation_trigger"],
                    "next_required_evidence": [
                        "confirmed pullback into a structurally meaningful area",
                        "closed-candle continuation trigger in the trend direction",
                    ],
                    "invalidation": ["loss_of_protected_structure"],
                })

    # Global evidence ledger: E6 records why an apparently attractive setup is still
    # conditional. These are not hidden vetoes; they are explicit evidence weights.
    if pending and not terminal:
        counter.append("LIQUIDITY_EVENT_PENDING")
    if any(marker in opportunity_finding for marker in ("UNRESOLVED", "UNPROVEN")):
        counter.append("OPPORTUNITY_MATURITY_UNPROVEN")
    if structure_mixed:
        counter.append("STRUCTURE_MIXED")
    if direction != "NEUTRAL" and space < MIN_SPACE_ATR:
        counter.append("STRUCTURAL_SPACE_CONSTRAINED")
    counter = _dedupe(counter)

    if any(marker in opportunity_finding for marker in ("UNRESOLVED", "UNPROVEN")):
        evidence_ledger.append(_evidence_item("E2", "opportunity remains unresolved/unproven", "COUNTER"))
    if structure_mixed:
        evidence_ledger.append(_evidence_item("E3", "structure is mixed; directional structure is not fully confirmed", "COUNTER"))
    if pending:
        evidence_ledger.append(_evidence_item("E4", "auction event is pending and therefore not terminal confirmation", "COUNTER"))
    if direction != "NEUTRAL" and space < MIN_SPACE_ATR:
        evidence_ledger.append(_evidence_item("E5", f"available structural space {space:.3f} ATR is below minimum {MIN_SPACE_ATR:.2f} ATR", "COUNTER"))

    # Enrich every candidate with the shared counter-evidence ledger.
    for candidate in candidates:
        candidate["counter_evidence"] = _dedupe(candidate.get("counter_evidence", []) + counter)
        candidate["missing_evidence"] = _dedupe(candidate.get("missing_evidence", []))
        candidate["next_required_evidence"] = _dedupe(candidate.get("next_required_evidence", []))
        candidate["supporting_evidence"] = _dedupe(candidate.get("supporting_evidence", []))
        candidate["invalidation"] = _dedupe(candidate.get("invalidation", []))

    if not candidates:
        setup = "NONE"
        stage = "FORMING"
        exists = False
        thesis = (
            "No defensible setup hypothesis exists yet: the evidence either lacks directional convergence "
            "or lacks a causal formation sequence."
        )
        missing = ["directional_convergence", "causal_setup_sequence"]
        next_required = [
            "closed-candle evidence that resolves direction and establishes a causal setup sequence"
        ]
        quality = 20
        confidence = 84
        rejected = list(SETUP_FAMILIES)
    else:
        candidates.sort(key=lambda candidate: candidate["strength"], reverse=True)
        best = candidates[0]
        if len(candidates) > 1 and candidates[0]["strength"] - candidates[1]["strength"] < 8:
            setup = "AMBIGUOUS"
            stage = "FORMING"
            exists = True
            rejected = [candidate["name"] for candidate in candidates]
            counter.append("HYPOTHESES_TOO_CLOSE_TO_FORCE_SELECTION")
            thesis = (
                "Multiple setup hypotheses remain too close to justify false precision; the correct professional action "
                "is to preserve the competing hypotheses and wait for discriminating evidence."
            )
            missing = _dedupe(
                [item for candidate in candidates for item in candidate.get("missing_evidence", [])]
                + ["discriminating_evidence_between_candidate_setups"]
            )
            next_required = [
                "closed-candle evidence that clearly distinguishes the leading setup hypotheses"
            ]
            quality = max(20, best["strength"] - 10)
            confidence = 70
            exists = True
        else:
            setup = best["name"]
            exists = True
            missing = list(best.get("missing_evidence", []))
            if any(marker in opportunity_finding for marker in ("UNRESOLVED", "UNPROVEN")):
                missing.append("opportunity_acceptance_follow_through")
            missing = _dedupe(missing)
            next_required = list(best.get("next_required_evidence", []))
            if any(marker in opportunity_finding for marker in ("UNRESOLVED", "UNPROVEN")):
                next_required.append("E2 opportunity thesis becoming resolved through closed-candle follow-through")
            next_required = _dedupe(next_required)
            # A setup is MATURE only when its own causal event is terminal AND the
            # remaining evidence does not contain a material formation blocker.
            terminal_for_family = terminal and "ACCEPTANCE" in event
            material_blockers = set(missing) & {
                "terminal_auction_confirmation",
                "closed_candle_follow_through",
                "structural_direction_confirmation",
                "opportunity_acceptance_follow_through",
                "adequate_structural_space",
                "acceptance_after_break",
            }
            mature = terminal_for_family and not material_blockers and not structure_mixed
            stage = "MATURE" if mature else best.get("formation_stage", "VALIDATING")
            if stage == "FORMING" and best["strength"] >= 50:
                stage = "VALIDATING"
            thesis = (
                f"{direction} {setup} is {stage.lower()}: the formation has a causal explanation, "
                "but maturity is conditional on the explicitly listed missing evidence."
            )
            quality = best["strength"]
            confidence = min(
                95,
                max(45, 56 + 7 * len(best.get("evidence", [])) - 5 * len(missing)),
            )

    maturity = "MATURE" if stage == "MATURE" else "VALIDATING" if stage == "VALIDATING" else "FORMING"
    ready = (
        exists
        and setup not in {"NONE", "AMBIGUOUS"}
        and stage == "MATURE"
        and direction != "NEUTRAL"
        and space >= MIN_SPACE_ATR
        and not pending
        and not any(marker in opportunity_finding for marker in ("UNRESOLVED", "UNPROVEN"))
        and not structure_mixed
    )

    invalidation: list[str] = []
    for candidate in candidates:
        invalidation.extend(candidate.get("invalidation", []))
    event_level = _num(e4.get("event_level"))
    protected_high = _num(e3.get("protected_high"))
    protected_low = _num(e3.get("protected_low"))
    if event_level > 0:
        invalidation.append(f"event_level_invalidation_reference={event_level:.5f}")
    if direction == "BUY" and protected_low > 0:
        invalidation.append(f"protected_low_failure={protected_low:.5f}")
    if direction == "SELL" and protected_high > 0:
        invalidation.append(f"protected_high_failure={protected_high:.5f}")
    invalidation = _dedupe(invalidation)[:10]

    selected_candidate = next(
        (candidate for candidate in candidates if candidate["name"] == setup),
        candidates[0] if candidates else None,
    )
    if selected_candidate:
        selected_candidate["selected"] = True

    trace = {
        "direction_source": direction_source,
        "directional_veto": hard_direction_veto,
        "auction": {
            "event": event,
            "direction": auction_direction,
            "terminal": terminal,
            "pending": pending,
            "age_bars": age,
            "event_level": event_level or None,
        },
        "structure": {
            "finding": structure_finding or "UNKNOWN",
            "internal": internal_structure or "UNKNOWN",
            "bos": bos or "UNKNOWN",
            "sequence": sequence or "UNKNOWN",
            "mixed": structure_mixed,
        },
        "location": {
            "selected_space_atr": round(space, 4),
            "minimum_space_atr": MIN_SPACE_ATR,
            "value_response": value_response or "UNKNOWN",
        },
        "opportunity": {
            "finding": opportunity_finding or "UNKNOWN",
            "resolved": not any(marker in opportunity_finding for marker in ("UNRESOLVED", "UNPROVEN")),
        },
        "hypothesis_count": len(candidates),
        "selection": "causal evidence -> supporting/counter evidence -> missing evidence -> lifecycle -> invalidation",
        "professional_rule": (
            "diagnose formation before declaring absence; preserve conditional hypotheses; "
            "do not convert pending auction evidence into trade confirmation; do not manufacture certainty; E9 retains trade authority"
        ),
    }

    return _out(
        stage,
        setup,
        direction,
        stage,
        maturity,
        thesis,
        quality,
        confidence,
        exists,
        ready,
        supporting,
        counter,
        missing,
        next_required,
        invalidation,
        candidates,
        rejected,
        trace,
        evidence_ledger,
    )
