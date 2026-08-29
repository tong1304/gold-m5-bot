from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V14"
VERSION = "14.0"
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


# E6 is a formation reasoner. It may describe a mature setup, but it never grants
# execution authority. E7/E8/E9 remain responsible for confirmation, economics and decision.

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
        h = _num(bar.get("high"))
        l = _num(bar.get("low"))
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


def _auction(e4: dict[str, Any]) -> tuple[str, bool, bool, int]:
    state = _text(e4.get("auction_state", e4.get("state")))
    event = _text(e4.get("event", e4.get("finding")))
    terminal = (
        state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"}
        or "TERMINAL" in state
    )
    pending = state == "PENDING" or "PENDING" in event
    age = max(0, int(_num(e4.get("event_age_bars"), 0)))
    return event, terminal, pending, age


def _direction_evidence(
    e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any]
) -> tuple[str, list[str], list[str], str, dict[str, str]]:
    """Resolve direction from independent evidence, never from setup-family preference."""
    pressure = _norm(e1.get("directional_pressure", e1.get("pressure")))
    external = _norm(e3.get("external_state", e3.get("external_count_state")))
    auction = _auction_direction(_text(e4.get("event", e4.get("finding"))))

    e2_finding = _text(e2.get("finding", e2.get("state")))
    e2_dirs = [
        value
        for value in (_norm(e2.get("direction")), _norm(e2.get("opportunity_direction")))
        if value != "NEUTRAL"
    ]
    e2_resolved = bool(e2_dirs) and not any(x in e2_finding for x in ("UNRESOLVED", "UNPROVEN"))

    votes = [x for x in (pressure, external, auction) if x != "NEUTRAL"]
    supporting: list[str] = []
    counter: list[str] = []

    if e2_resolved and len(set(e2_dirs)) == 1:
        direction = e2_dirs[0]
        source = "E2_RESOLVED"
    elif len(votes) >= 2 and len(set(votes)) == 1:
        direction = votes[0]
        source = "E1_E3_E4_CONVERGENCE"
    elif external != "NEUTRAL" and auction == external:
        direction = external
        source = "E3_E4_ALIGNMENT"
    else:
        direction = "NEUTRAL"
        source = "INSUFFICIENT_CONVERGENCE"

    for label, value in (
        ("E1_PRESSURE", pressure),
        ("E3_EXTERNAL", external),
        ("E4_AUCTION", auction),
    ):
        if value != "NEUTRAL":
            supporting.append(f"{label}={value}")
    if e2_resolved:
        supporting.append(f"E2_DIRECTION={e2_dirs[0]}")
    supporting.append(f"DIRECTION_SOURCE={source}")

    if len(set(votes)) > 1:
        counter.append("DIRECTIONAL_EVIDENCE_CONFLICT")

    e3_finding = _text(e3.get("finding", e3.get("structure_state")))
    e3_internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    if "MIXED" in e3_finding or "MIXED" in e3_internal:
        counter.append("STRUCTURE_MIXED")
    if "FAILED_BOS" in e3_finding:
        counter.append("FAILED_STRUCTURE_BREAK")
    if direction != "NEUTRAL" and external != "NEUTRAL" and external != direction:
        counter.append("EXTERNAL_STRUCTURE_COUNTERTREND")

    raw = {
        "e1_pressure": pressure,
        "e2_direction": e2_dirs[0] if e2_resolved else "NEUTRAL",
        "e3_external": external,
        "e4_auction": auction,
    }
    return direction, list(dict.fromkeys(supporting)), list(dict.fromkeys(counter)), source, raw


def _location(e5: dict[str, Any]) -> tuple[float, float, bool, bool]:
    long_space = _num(e5.get("available_space_atr_long"))
    short_space = _num(e5.get("available_space_atr_short"))
    text = _text(e5)
    constrained = any(x in text for x in ("LOCATION_CONSTRAINT", "SPACE_CONSTRAINED"))
    extension = "EXTENSION_RISK" in text
    return long_space, short_space, constrained, extension


def _candidate(
    name: str,
    direction: str,
    evidence: list[str],
    missing: list[str],
    strength: float,
    stage: str,
    invalidation: list[str],
) -> dict[str, Any]:
    return {
        "name": name,
        "direction": direction,
        "formation_stage": stage,
        "strength": round(max(0.0, min(100.0, strength)), 2),
        "evidence": list(dict.fromkeys(evidence)),
        "missing": list(dict.fromkeys(missing)),
        "invalidation": list(dict.fromkeys(invalidation)),
    }


def _result(
    *,
    state: str,
    setup: str,
    direction: str,
    stage: str,
    maturity: str,
    thesis: str,
    quality: float,
    confidence: float,
    setup_exists: bool,
    trade_ready: bool,
    supporting: list[str],
    counter: list[str],
    missing: list[str],
    next_required: list[str],
    invalidation: list[str],
    candidates: list[dict[str, Any]],
    rejected: list[str],
    trace: dict[str, Any] | None = None,
) -> EngineResult:
    quality = max(0.0, min(100.0, quality))
    confidence = max(0.0, min(100.0, confidence))
    counter = list(dict.fromkeys(counter))
    missing = list(dict.fromkeys(missing))
    next_required = list(dict.fromkeys(next_required))

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
        "counter_evidence": counter,
        "missing_evidence": missing,
        "next_required_evidence": next_required,
        "invalidation": list(dict.fromkeys(invalidation)),
        "observations": [
            f"candidate_setups={','.join(x['name'] for x in candidates) if candidates else 'NONE'}",
            f"selected_setup={setup}",
            f"selected_direction={direction}",
            f"selected_stage={stage}",
            f"setup_exists={setup_exists}",
            f"trade_ready={trade_ready}",
            f"supporting_evidence={','.join(dict.fromkeys(supporting)) if supporting else 'NONE'}",
            f"counter_evidence={','.join(counter) if counter else 'NONE'}",
            f"missing_evidence={','.join(missing) if missing else 'NONE'}",
            f"next_required_evidence={','.join(next_required) if next_required else 'NONE'}",
            f"lifecycle={stage}",
            f"maturity={maturity}",
        ],
    }
    if trace:
        output["reasoning_trace"] = trace
    return EngineResult("E6", NAME, False, quality, output, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Build a causal setup thesis from E3/E4/E5 using closed-candle evidence only."""
    bars = list(snapshot.get("bars") or [])

    if len(bars) < MIN_BARS:
        return _result(
            state="NO_SETUP",
            setup="NONE",
            direction="NEUTRAL",
            stage="SEARCHING",
            maturity="UNRESOLVED",
            thesis="NO_SETUP: insufficient closed-candle history",
            quality=0.0,
            confidence=100.0,
            setup_exists=False,
            trade_ready=False,
            supporting=[],
            counter=[f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"],
            missing=["sufficient_closed_candle_data"],
            next_required=[f"wait for at least {MIN_BARS} valid closed candles"],
            invalidation=["history remains insufficient"],
            candidates=[],
            rejected=[],
        )

    try:
        atr = _atr(bars)
        if atr <= 0:
            raise ValueError("invalid atr")
        for bar in bars[-MIN_BARS:]:
            for key in ("open", "high", "low", "close"):
                value = float(bar[key])
                if value != value:  # NaN
                    raise ValueError("nan ohlc")
    except (KeyError, TypeError, ValueError):
        return _result(
            state="NO_SETUP",
            setup="NONE",
            direction="NEUTRAL",
            stage="SEARCHING",
            maturity="UNRESOLVED",
            thesis="NO_SETUP: invalid market data",
            quality=0.0,
            confidence=100.0,
            setup_exists=False,
            trade_ready=False,
            supporting=[],
            counter=["INVALID_MARKET_DATA"],
            missing=["valid_closed_candle_ohlc"],
            next_required=["provide a valid closed candle with finite OHLC values"],
            invalidation=["invalid market data"],
            candidates=[],
            rejected=[],
        )

    e1, e2, e3, e4, e5 = (
        _payload(upstream, name) for name in ("E1", "E2", "E3", "E4", "E5")
    )

    direction, supporting, counter, direction_source, direction_inputs = _direction_evidence(e1, e2, e3, e4)
    event, terminal, pending, event_age = _auction(e4)
    long_space, short_space, location_constrained, extension_risk = _location(e5)

    opportunity = _text(e2.get("finding", e2.get("state", "")))
    e3_finding = _text(e3.get("finding", e3.get("structure_state")))
    e3_internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    e3_external = _norm(e3.get("external_state", e3.get("external_count_state")))
    e3_lifecycle = _text(e3.get("lifecycle", e3.get("structure_lifecycle", "")))
    e3_bos = _text(e3.get("bos", e3.get("break_of_structure", "")))
    e1_trend = _text(e1.get("trend_state", e1.get("finding", "")))
    response = _norm(e4.get("response_actor"))
    auction_dir = _auction_direction(event)
    structure_mixed = "MIXED" in e3_finding or "MIXED" in e3_internal

    # These are formation counter-evidence. Location/space is deliberately not in this list:
    # poor location can make a setup uneconomic without erasing the setup's existence.
    formation_counter: list[str] = list(counter)
    if pending and not terminal:
        formation_counter.append("LIQUIDITY_EVENT_PENDING")
    if any(x in opportunity for x in ("UNRESOLVED", "UNPROVEN")):
        formation_counter.append("OPPORTUNITY_MATURITY_UNPROVEN")
    if structure_mixed:
        formation_counter.append("STRUCTURE_MIXED")
    formation_counter = list(dict.fromkeys(formation_counter))

    supporting.extend(
        [
            f"E4_EVENT={event or 'NONE'}",
            f"E4_EVENT_AGE_BARS={event_age}",
            f"E4_AUCTION_STATE={_text(e4.get('auction_state', e4.get('state'))) or 'UNKNOWN'}",
            f"E3_LIFECYCLE={e3_lifecycle or 'UNKNOWN'}",
            f"E3_EXTERNAL={e3_external}",
            f"E5_LOCATION={_text(e5.get('finding', e5.get('state', 'UNKNOWN'))) or 'UNKNOWN'}",
            f"STRUCTURAL_SPACE_LONG_ATR={long_space:.3f}",
            f"STRUCTURAL_SPACE_SHORT_ATR={short_space:.3f}",
        ]
    )

    candidates: list[dict[str, Any]] = []
    rejected: list[str] = []

    if direction != "NEUTRAL":
        # 1) Liquidity reversal: event -> response -> terminal auction.
        if auction_dir == direction and any(x in event for x in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM")):
            evidence = ["E4_LIQUIDITY_EVENT"]
            missing: list[str] = []
            if response == direction:
                evidence.append("RESPONSE_ACTOR_ALIGNED")
            else:
                missing.append(f"closed_candle_{direction.lower()}_response_after_liquidity_event")
            if terminal:
                evidence.append("TERMINAL_AUCTION_CONFIRMATION")
            else:
                missing.append("closed_candle_terminal_liquidity_acceptance_or_rejection")

            if response == direction and terminal and not structure_mixed and not pending:
                stage = "MATURE"
            elif response == direction:
                stage = "VALIDATING"
            else:
                stage = "FORMING"
            strength = 91.0 if stage == "MATURE" else 79.0 if stage == "VALIDATING" else 63.0
            candidates.append(
                _candidate(
                    "LIQUIDITY_REVERSAL",
                    direction,
                    evidence,
                    missing,
                    strength,
                    stage,
                    ["closed_candle_loses_reclaim", "contrary_closed_candle_acceptance", "protected_level_break"],
                )
            )
        else:
            rejected.append("LIQUIDITY_REVERSAL: no directional liquidity rejection/reclaim sequence")

        # 2) Breakout/retest: structure break must agree with the direction and be accepted.
        confirmed_break = "NO_BREAK" not in e3_bos and any(x in e3_bos for x in ("BREAK", "BOS"))
        if confirmed_break and e3_external == direction:
            evidence = ["E3_CONFIRMED_STRUCTURE_BREAK", "E3_EXTERNAL_DIRECTION_ALIGNED"]
            missing = []
            retest = "RETEST" in e3_lifecycle or "RETEST" in e3_finding
            acceptance = any(x in e3_finding for x in ("ACCEPT", "CONTINUATION", "CONFIRMED"))
            if retest or acceptance:
                evidence.append("CONTROLLED_RETEST_OR_ACCEPTANCE")
            else:
                missing.append("controlled_retest_or_closed_candle_acceptance_after_break")

            stage = "MATURE" if (retest or acceptance) and not structure_mixed else "VALIDATING"
            candidates.append(
                _candidate(
                    "BREAKOUT_RETEST" if retest else "BREAKOUT",
                    direction,
                    evidence,
                    missing,
                    88.0 if stage == "MATURE" else 75.0,
                    stage,
                    ["failed_retest", "closed_candle_back_inside_broken_structure", "protected_level_failure"],
                )
            )
        else:
            rejected.append("BREAKOUT_RETEST: confirmed directional structure break not established")

        # 3) Trend pullback: context + external structure alignment is a formation thesis,
        # but it remains validating until continuation evidence exists.
        trend_aligned = (
            e3_external == direction
            and "NONE" not in e1_trend
            and any(x in e1_trend for x in ("UP", "DOWN", "TREND"))
            and not structure_mixed
        )
        if trend_aligned:
            evidence = ["E1_TREND_CONTEXT", "E3_STRUCTURE_ALIGNMENT"]
            missing = ["closed_candle_pullback_rejection_and_continuation"]
            if long_space >= MIN_SPACE_ATR if direction == "BUY" else short_space >= MIN_SPACE_ATR:
                evidence.append("STRUCTURAL_SPACE_AVAILABLE")
            else:
                missing.append("sufficient_structural_space_for_direction")
            candidates.append(
                _candidate(
                    "TREND_PULLBACK",
                    direction,
                    evidence,
                    missing,
                    72.0,
                    "VALIDATING",
                    ["trend_alignment_lost", "protected_structure_failure", "pullback_breaks_directional_structure"],
                )
            )
        else:
            rejected.append("TREND_PULLBACK: trend/structure alignment insufficient")

        # 4) Impulse continuation: the latest closed candle itself can begin a setup, never
        # mature it without follow-through.
        last = bars[-1]
        body = abs(_num(last.get("close")) - _num(last.get("open")))
        candle_dir = _norm("UP" if _num(last.get("close")) > _num(last.get("open")) else "DOWN")
        if body >= 0.8 * atr and candle_dir == direction and e3_external == direction and not structure_mixed:
            candidates.append(
                _candidate(
                    "IMPULSE_CONTINUATION",
                    direction,
                    ["DIRECTIONAL_IMPULSE", "E3_STRUCTURE_ALIGNMENT"],
                    ["closed_candle_follow_through_after_impulse"],
                    66.0,
                    "FORMING",
                    ["impulse_failure", "countertrend_closed_candle", "protected_structure_failure"],
                )
            )
        else:
            rejected.append("IMPULSE_CONTINUATION: current closed candle is not a clean aligned impulse")
    else:
        rejected.extend(f"{name}:direction_not_established" for name in SETUP_FAMILIES)

    # A professional reasoner prefers causal completeness over a merely high score.
    stage_rank = {"MATURE": 3, "VALIDATING": 2, "FORMING": 1}
    candidates.sort(key=lambda x: (stage_rank.get(x["formation_stage"], 0), x["strength"]), reverse=True)

    # No directional thesis means no setup exists. Do not invent a family to fill the field.
    if not candidates:
        missing = ["specific_setup_causal_sequence"]
        next_required = ["a closed-candle sequence that establishes one setup family"]
        if direction == "NEUTRAL":
            missing.insert(0, "directional_evidence_convergence")
            next_required.insert(0, "resolve E1/E3/E4 directional conflict on a subsequent closed candle")
        if "LIQUIDITY_EVENT_PENDING" in formation_counter:
            missing.append("terminal_liquidity_auction_confirmation")
            next_required.append("wait for the liquidity auction to become terminal on a closed candle")
        if "OPPORTUNITY_MATURITY_UNPROVEN" in formation_counter:
            missing.append("opportunity_acceptance")
            next_required.append("wait for closed-candle acceptance/follow-through proving the opportunity")
        if structure_mixed:
            missing.append("clean_structure_alignment")
            next_required.append("wait for confirmed pivots to produce a non-mixed directional structure")

        state = "NO_SETUP" if direction == "NEUTRAL" else "FORMING"
        stage = "SEARCHING" if direction == "NEUTRAL" else "FORMING"
        thesis = (
            "NO_SETUP: direction is unresolved; no setup family may be promoted"
            if direction == "NEUTRAL"
            else f"{direction}: directional thesis exists, but no setup family has a causal sequence yet"
        )
        return _result(
            state=state,
            setup="NONE",
            direction=direction,
            stage=stage,
            maturity="UNRESOLVED",
            thesis=thesis,
            quality=10.0 if direction != "NEUTRAL" else 0.0,
            confidence=82.0,
            setup_exists=False,
            trade_ready=False,
            supporting=supporting,
            counter=formation_counter,
            missing=missing,
            next_required=next_required,
            invalidation=["directional thesis invalidation", "setup-specific formation failure"],
            candidates=[],
            rejected=rejected,
            trace={
                "direction_source": direction_source,
                "direction_inputs": direction_inputs,
                "formation_counter_evidence": formation_counter,
                "e3_finding": e3_finding,
                "e4_event": event,
                "e4_terminal": terminal,
                "e4_pending": pending,
                "e4_event_age_bars": event_age,
                "e5_location": _text(e5.get("finding", e5.get("state", ""))),
                "setup_exists": False,
                "trade_ready": False,
                "closed_candle_only": True,
                "lookahead": False,
            },
        )

    selected = candidates[0]
    setup = selected["name"]
    stage = selected["formation_stage"]

    # Formation lifecycle is monotonic for the current observation, but MATURE is a hard
    # epistemic state: any formation counter-evidence prevents promotion.
    if formation_counter and stage == "MATURE":
        stage = "VALIDATING"
        selected["formation_stage"] = stage
        selected["missing"].append("resolution_of_formation_counter_evidence")
        selected["missing"] = list(dict.fromkeys(selected["missing"]))

    maturity = "MATURE" if stage == "MATURE" and not formation_counter else "DEVELOPING"
    setup_exists = True

    missing = list(selected["missing"])
    next_required = list(missing)

    # These are trade-readiness/economic blockers, intentionally separate from setup existence.
    readiness_blockers: list[str] = []
    if direction == "BUY" and long_space < MIN_SPACE_ATR:
        readiness_blockers.append("INSUFFICIENT_LONG_STRUCTURAL_SPACE")
        next_required.append("wait for price to create at least 0.75 ATR long-side structural space")
    if direction == "SELL" and short_space < MIN_SPACE_ATR:
        readiness_blockers.append("INSUFFICIENT_SHORT_STRUCTURAL_SPACE")
        next_required.append("wait for price to create at least 0.75 ATR short-side structural space")
    if location_constrained:
        readiness_blockers.append("LOCATION_CONSTRAINT")
        next_required.append("wait for a location with sufficient structural room")
    if extension_risk:
        readiness_blockers.append("LOCATION_EXTENSION_RISK")
        next_required.append("wait for extension risk to normalize before considering economics")
    if "OPPORTUNITY_MATURITY_UNPROVEN" in formation_counter:
        readiness_blockers.append("OPPORTUNITY_NOT_MATURE")
    if "DIRECTIONAL_EVIDENCE_CONFLICT" in formation_counter:
        readiness_blockers.append("DIRECTIONAL_CONFLICT")
    if "STRUCTURE_MIXED" in formation_counter:
        readiness_blockers.append("STRUCTURE_MIXED")
    if "LIQUIDITY_EVENT_PENDING" in formation_counter:
        readiness_blockers.append("LIQUIDITY_PENDING")

    # E6 never sets trade_ready=True. It explicitly hands the remaining execution question to E7/E8.
    readiness_blockers = list(dict.fromkeys(readiness_blockers))
    next_required.extend(readiness_blockers)
    next_required.append("E7 independent closed-candle entry confirmation")
    next_required.append("E8 independent structural/economic survivability")

    thesis_parts = [
        f"{direction} {setup}",
        f"lifecycle={stage}",
        f"causal_sequence={' -> '.join(selected['evidence'])}",
    ]
    if formation_counter:
        thesis_parts.append(f"formation_counter_evidence={','.join(formation_counter)}")
    if readiness_blockers:
        thesis_parts.append(f"trade_readiness_blockers={','.join(readiness_blockers)}")
    thesis = " | ".join(thesis_parts)

    quality = selected["strength"]
    quality -= min(25.0, 5.0 * len(formation_counter))
    confidence = selected["strength"] + 5.0 - min(30.0, 5.0 * len(formation_counter))

    # A mature setup may still be economically unusable. This is why state/maturity and
    # trade_ready are deliberately different fields.
    state = "MATURE" if maturity == "MATURE" else "FORMING"

    return _result(
        state=state,
        setup=setup,
        direction=direction,
        stage=stage,
        maturity=maturity,
        thesis=thesis,
        quality=quality,
        confidence=max(55.0, min(96.0, confidence)),
        setup_exists=setup_exists,
        trade_ready=False,
        supporting=supporting + [f"SETUP_THESIS={thesis}"],
        counter=formation_counter,
        missing=missing + readiness_blockers,
        next_required=next_required,
        invalidation=selected["invalidation"] + [
            "directional thesis becomes contradictory",
            "causal setup sequence is invalidated",
        ],
        candidates=candidates,
        rejected=rejected,
        trace={
            "direction_source": direction_source,
            "direction_inputs": direction_inputs,
            "e1_trend_state": e1_trend,
            "e2_opportunity": opportunity,
            "e3_finding": e3_finding,
            "e3_external": e3_external,
            "e3_lifecycle": e3_lifecycle,
            "e4_event": event,
            "e4_terminal": terminal,
            "e4_pending": pending,
            "e4_event_age_bars": event_age,
            "e5_location": _text(e5.get("finding", e5.get("state", ""))),
            "setup_exists": True,
            "trade_ready": False,
            "formation_counter_evidence": formation_counter,
            "trade_readiness_blockers": readiness_blockers,
            "closed_candle_only": True,
            "lookahead": False,
        },
    )
