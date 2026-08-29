from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V16"
VERSION = "16.0"
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
        h = _num(bar.get("high")); l = _num(bar.get("low"))
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
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    pending = state == "PENDING" or "PENDING" in event
    return event, terminal, pending, max(0, int(_num(e4.get("event_age_bars"), 0)))


def _direction_evidence(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any]):
    pressure = _norm(e1.get("directional_pressure", e1.get("pressure")))
    external = _norm(e3.get("external_state", e3.get("external_count_state")))
    auction = _auction_direction(_text(e4.get("event", e4.get("finding"))))
    e2_finding = _text(e2.get("finding", e2.get("state")))
    e2_dirs = [x for x in (_norm(e2.get("direction")), _norm(e2.get("opportunity_direction"))) if x != "NEUTRAL"]
    e2_dir = e2_dirs[0] if e2_dirs and len(set(e2_dirs)) == 1 and not any(x in e2_finding for x in ("UNRESOLVED", "UNPROVEN")) else "NEUTRAL"
    raw = {"E1_PRESSURE": pressure, "E3_EXTERNAL": external, "E4_AUCTION": auction}
    votes = [x for x in raw.values() if x != "NEUTRAL"]
    unique = set(votes)
    supporting = [f"{k}={v}" for k, v in raw.items() if v != "NEUTRAL"]
    counter: list[str] = []
    if len(unique) > 1:
        counter.append("DIRECTIONAL_EVIDENCE_CONFLICT")
        direction, source = "NEUTRAL", "INDEPENDENT_EVIDENCE_CONFLICT"
    elif len(unique) == 1:
        direction = next(iter(unique)); source = "E1_E3_E4_CONVERGENCE" if len(votes) >= 2 else "INDEPENDENT_EVIDENCE"
    elif e2_dir != "NEUTRAL":
        direction, source = e2_dir, "E2_CORROBORATION_ONLY"
    else:
        direction, source = "NEUTRAL", "INSUFFICIENT_CONVERGENCE"
    if e2_dir != "NEUTRAL":
        supporting.append(f"E2_DIRECTION={e2_dir}")
        if direction != "NEUTRAL" and e2_dir != direction:
            counter.append("E2_DIRECTION_DISAGREEMENT")
    if len(e2_dirs) > 1:
        counter.append("E2_INTERNAL_DIRECTION_CONFLICT")
    e3_finding = _text(e3.get("finding", e3.get("structure_state")))
    e3_internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    if "MIXED" in e3_finding or "MIXED" in e3_internal:
        counter.append("STRUCTURE_MIXED")
    if "FAILED_BOS" in e3_finding:
        counter.append("FAILED_STRUCTURE_BREAK")
    if direction != "NEUTRAL" and external != "NEUTRAL" and external != direction:
        counter.append("EXTERNAL_STRUCTURE_COUNTERTREND")
    supporting.append(f"DIRECTION_SOURCE={source}")
    return direction, list(dict.fromkeys(supporting)), list(dict.fromkeys(counter)), source, {"e1_pressure": pressure, "e2_direction": e2_dir, "e3_external": external, "e4_auction": auction}


def _location(e5: dict[str, Any]) -> tuple[float, float, bool, bool]:
    long_space = _num(e5.get("available_space_atr_long")); short_space = _num(e5.get("available_space_atr_short"))
    text = _text(e5)
    return long_space, short_space, any(x in text for x in ("LOCATION_CONSTRAINT", "SPACE_CONSTRAINED")), "EXTENSION_RISK" in text


def _candidate(name: str, direction: str, evidence: list[str], missing: list[str], strength: float, stage: str, invalidation: list[str], components: dict[str, float] | None = None) -> dict[str, Any]:
    return {"name": name, "direction": direction, "formation_stage": stage, "strength": round(max(0.0, min(100.0, strength)), 2), "evidence": list(dict.fromkeys(evidence)), "missing": list(dict.fromkeys(missing)), "invalidation": list(dict.fromkeys(invalidation)), "score_components": components or {}}


def _result(*, state: str, setup: str, direction: str, stage: str, maturity: str, thesis: str, quality: float, confidence: float, setup_exists: bool, trade_ready: bool, supporting: list[str], counter: list[str], missing: list[str], next_required: list[str], invalidation: list[str], candidates: list[dict[str, Any]], rejected: list[str], trace: dict[str, Any] | None = None) -> EngineResult:
    quality = max(0.0, min(100.0, quality)); confidence = max(0.0, min(100.0, confidence))
    counter = list(dict.fromkeys(counter)); missing = list(dict.fromkeys(missing)); next_required = list(dict.fromkeys(next_required))
    reasons = list(dict.fromkeys(counter + ([] if stage == "MATURE" else ["SETUP_NOT_MATURE"])))
    output = {"architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION, "role": "SETUP_ANALYST", "reasoning_role": "SETUP_FORMATION_REASONER", "decision_authority": "E9", "trade_decision_authority": False, "state": state, "setup_state": state, "finding": state, "setup": setup, "setup_family": setup, "direction": direction, "stage": stage, "formation_stage": stage, "lifecycle": stage, "maturity": maturity, "thesis": thesis, "setup_exists": setup_exists, "trade_ready": trade_ready, "trade_readiness": "READY" if trade_ready else "NOT_READY", "setup_quality": round(quality, 2), "confidence": round(confidence, 2), "candidate_setups": [x["name"] for x in candidates], "candidate_states": candidates, "rejected_setups": rejected, "supporting_evidence": list(dict.fromkeys(supporting)), "counter_evidence": counter, "missing_evidence": missing, "next_required_evidence": next_required, "invalidation": list(dict.fromkeys(invalidation)), "observations": [f"candidate_setups={','.join(x['name'] for x in candidates) if candidates else 'NONE'}", f"selected_setup={setup}", f"selected_direction={direction}", f"selected_stage={stage}", f"setup_exists={setup_exists}", f"trade_ready={trade_ready}", f"supporting_evidence={','.join(dict.fromkeys(supporting)) if supporting else 'NONE'}", f"counter_evidence={','.join(counter) if counter else 'NONE'}", f"missing_evidence={','.join(missing) if missing else 'NONE'}", f"next_required_evidence={','.join(next_required) if next_required else 'NONE'}", f"lifecycle={stage}", f"maturity={maturity}"]}
    if trace: output["reasoning_trace"] = trace
    return EngineResult("E6", NAME, False, quality, output, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Professional setup-formation reasoner: form hypotheses, challenge them, and never force a trade thesis."""
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _result(state="NO_SETUP", setup="NONE", direction="NEUTRAL", stage="SEARCHING", maturity="UNRESOLVED", thesis="NO_SETUP: insufficient closed-candle history", quality=0.0, confidence=100.0, setup_exists=False, trade_ready=False, supporting=[], counter=[f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"], missing=["sufficient_closed_candle_data"], next_required=[f"wait for at least {MIN_BARS} valid closed candles"], invalidation=["history remains insufficient"], candidates=[], rejected=[])
    try:
        atr = _atr(bars)
        if atr <= 0: raise ValueError("invalid atr")
        for bar in bars[-MIN_BARS:]:
            for key in ("open", "high", "low", "close"):
                value = float(bar[key])
                if value != value: raise ValueError("nan ohlc")
    except (KeyError, TypeError, ValueError):
        return _result(state="NO_SETUP", setup="NONE", direction="NEUTRAL", stage="SEARCHING", maturity="UNRESOLVED", thesis="NO_SETUP: invalid market data", quality=0.0, confidence=100.0, setup_exists=False, trade_ready=False, supporting=[], counter=["INVALID_MARKET_DATA"], missing=["valid_closed_candle_ohlc"], next_required=["provide valid closed-candle OHLC values"], invalidation=["invalid market data"], candidates=[], rejected=[])

    e1, e2, e3, e4, e5 = (_payload(upstream, n) for n in ("E1", "E2", "E3", "E4", "E5"))
    direction, supporting, counter, direction_source, direction_inputs = _direction_evidence(e1, e2, e3, e4)
    event, terminal, pending, event_age = _auction(e4)
    long_space, short_space, location_constrained, extension_risk = _location(e5)
    opportunity = _text(e2.get("finding", e2.get("state", "")))
    e3_finding = _text(e3.get("finding", e3.get("structure_state"))); e3_internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    e3_external = _norm(e3.get("external_state", e3.get("external_count_state"))); e3_lifecycle = _text(e3.get("lifecycle", e3.get("structure_lifecycle", "")))
    e3_bos = _text(e3.get("bos", e3.get("break_of_structure", ""))); e1_trend = _text(e1.get("trend_state", e1.get("finding", "")))
    response = _norm(e4.get("response_actor")); auction_dir = _auction_direction(event); structure_mixed = "MIXED" in e3_finding or "MIXED" in e3_internal

    formation_counter = list(counter)
    if pending and not terminal: formation_counter.append("LIQUIDITY_EVENT_PENDING")
    if any(x in opportunity for x in ("UNRESOLVED", "UNPROVEN")): formation_counter.append("OPPORTUNITY_MATURITY_UNPROVEN")
    if structure_mixed: formation_counter.append("STRUCTURE_MIXED")
    formation_counter = list(dict.fromkeys(formation_counter))
    supporting.extend([f"E4_EVENT={event or 'NONE'}", f"E4_EVENT_AGE_BARS={event_age}", f"E4_AUCTION_STATE={_text(e4.get('auction_state', e4.get('state'))) or 'UNKNOWN'}", f"E3_LIFECYCLE={e3_lifecycle or 'UNKNOWN'}", f"E3_EXTERNAL={e3_external}", f"E5_LOCATION={_text(e5.get('finding', e5.get('state', 'UNKNOWN'))) or 'UNKNOWN'}", f"STRUCTURAL_SPACE_LONG_ATR={long_space:.3f}", f"STRUCTURAL_SPACE_SHORT_ATR={short_space:.3f}"])

    candidates: list[dict[str, Any]] = []; rejected: list[str] = []
    if direction != "NEUTRAL" and not formation_counter:
        if auction_dir == direction and any(x in event for x in ("SWEEP_REJECTION", "FAILED_BREAK_RECLAIM")):
            evidence = ["E4_LIQUIDITY_EVENT"]; missing: list[str] = []
            if response == direction: evidence.append("RESPONSE_ACTOR_ALIGNED")
            else: missing.append(f"closed_candle_{direction.lower()}_response_after_liquidity_event")
            if terminal: evidence.append("TERMINAL_AUCTION_CONFIRMATION")
            else: missing.append("closed_candle_terminal_liquidity_acceptance_or_rejection")
            stage = "MATURE" if response == direction and terminal else "VALIDATING" if response == direction else "FORMING"
            candidates.append(_candidate("LIQUIDITY_REVERSAL", direction, evidence, missing, 92.0 if stage == "MATURE" else 78.0 if stage == "VALIDATING" else 62.0, stage, ["closed_candle_loses_reclaim", "contrary_closed_candle_acceptance", "protected_level_break"], {"causal_event": 30.0, "response": 20.0 if response == direction else 0.0, "terminal": 18.0 if terminal else 0.0}))
        else: rejected.append("LIQUIDITY_REVERSAL: causal sweep/rejection or failed-reclaim sequence absent")

        confirmed_break = "NO_BREAK" not in e3_bos and any(x in e3_bos for x in ("BREAK", "BOS"))
        if confirmed_break and e3_external == direction:
            retest = "RETEST" in e3_lifecycle or "RETEST" in e3_finding; acceptance = any(x in e3_finding for x in ("ACCEPT", "CONTINUATION", "CONFIRMED"))
            evidence = ["E3_CONFIRMED_STRUCTURE_BREAK", "E3_EXTERNAL_DIRECTION_ALIGNED"]; missing = []
            if retest or acceptance: evidence.append("CONTROLLED_RETEST_OR_ACCEPTANCE")
            else: missing.append("controlled_retest_or_closed_candle_acceptance_after_break")
            stage = "MATURE" if (retest or acceptance) else "VALIDATING"; name = "BREAKOUT_RETEST" if retest else "BREAKOUT"
            candidates.append(_candidate(name, direction, evidence, missing, 88.0 if stage == "MATURE" else 74.0, stage, ["failed_retest", "closed_candle_back_inside_broken_structure", "protected_level_failure"], {"break": 32.0, "alignment": 18.0, "retest_or_acceptance": 20.0 if (retest or acceptance) else 0.0}))
        else: rejected.append("BREAKOUT_RETEST: confirmed directional structure break not established")

        trend_aligned = e3_external == direction and any(x in e1_trend for x in ("UP", "DOWN", "TREND")) and not structure_mixed
        pullback = any(x in (e3_finding, e3_lifecycle, opportunity) for x in ("PULLBACK", "RETEST", "REJECTION"))
        if trend_aligned and pullback:
            space = long_space if direction == "BUY" else short_space; evidence = ["E1_TREND_CONTEXT", "E3_STRUCTURE_ALIGNMENT", "PULLBACK_OR_REJECTION_PRESENT"]; missing = ["closed_candle_continuation_after_pullback"]
            if space >= MIN_SPACE_ATR: evidence.append("STRUCTURAL_SPACE_AVAILABLE")
            else: missing.append("sufficient_structural_space_for_direction")
            candidates.append(_candidate("TREND_PULLBACK", direction, evidence, missing, 76.0, "VALIDATING", ["trend_alignment_lost", "protected_structure_failure", "pullback_breaks_directional_structure"], {"trend": 24.0, "pullback": 28.0, "space": 14.0 if space >= MIN_SPACE_ATR else 0.0}))
        else: rejected.append("TREND_PULLBACK: explicit pullback/rejection sequence not established")

        last = bars[-1]; body = abs(_num(last.get("close")) - _num(last.get("open"))); candle_dir = "BUY" if _num(last.get("close")) > _num(last.get("open")) else "SELL" if _num(last.get("close")) < _num(last.get("open")) else "NEUTRAL"
        if body >= 0.8 * atr and candle_dir == direction and e3_external == direction and not structure_mixed:
            candidates.append(_candidate("IMPULSE_CONTINUATION", direction, ["DIRECTIONAL_IMPULSE", "E3_STRUCTURE_ALIGNMENT"], ["closed_candle_follow_through_after_impulse"], 66.0, "FORMING", ["impulse_failure", "countertrend_closed_candle", "protected_structure_failure"], {"impulse": 32.0, "alignment": 20.0}))
        else: rejected.append("IMPULSE_CONTINUATION: current closed candle is not a clean aligned impulse")
    else:
        if direction == "NEUTRAL": rejected.extend(f"{name}:direction_not_established" for name in SETUP_FAMILIES)
        else: rejected.append("ALL_SETUP_FAMILIES: independent formation evidence is conflicting or incomplete")

    stage_rank = {"MATURE": 3, "VALIDATING": 2, "FORMING": 1}; candidates.sort(key=lambda x: (stage_rank.get(x["formation_stage"], 0), x["strength"]), reverse=True)
    if len(candidates) >= 2 and candidates[0]["strength"] - candidates[1]["strength"] < 8.0:
        formation_counter.append("SETUP_HYPOTHESES_TOO_CLOSE"); formation_counter = list(dict.fromkeys(formation_counter)); candidates[0]["missing"].append("clear_hypothesis_separation")

    if not candidates:
        missing = ["specific_setup_causal_sequence"]; next_required = ["a closed-candle sequence that establishes one setup family"]
        if direction == "NEUTRAL": missing.insert(0, "directional_evidence_convergence"); next_required.insert(0, "wait for independent E1/E3/E4 evidence to align")
        guidance = {"DIRECTIONAL_EVIDENCE_CONFLICT": "wait for independent directional evidence to resolve without override", "E2_DIRECTION_DISAGREEMENT": "wait for E2 and independent structure/auction evidence to agree", "E2_INTERNAL_DIRECTION_CONFLICT": "wait for E2 to resolve its own directional contradiction", "STRUCTURE_MIXED": "wait for confirmed pivots to produce a clean structure", "LIQUIDITY_EVENT_PENDING": "wait for the liquidity event to become terminal on a closed candle", "OPPORTUNITY_MATURITY_UNPROVEN": "wait for closed-candle acceptance/follow-through proving the opportunity", "EXTERNAL_STRUCTURE_COUNTERTREND": "wait for external structure and directional thesis to realign", "SETUP_HYPOTHESES_TOO_CLOSE": "wait for one setup hypothesis to gain clear causal dominance"}
        for item in formation_counter: missing.append(item); next_required.append(guidance.get(item, f"resolve {item}"))
        return _result(state="NO_SETUP" if direction == "NEUTRAL" else "FORMING", setup="NONE", direction=direction, stage="SEARCHING" if direction == "NEUTRAL" else "FORMING", maturity="UNRESOLVED", thesis="NO_SETUP: direction is unresolved; no setup family may be promoted" if direction == "NEUTRAL" else f"{direction}: directional thesis exists, but causal setup formation is not established", quality=0.0 if direction == "NEUTRAL" else 10.0, confidence=82.0, setup_exists=False, trade_ready=False, supporting=supporting, counter=formation_counter, missing=missing, next_required=next_required, invalidation=["directional thesis invalidation", "setup-specific formation failure"], candidates=[], rejected=rejected, trace={"direction_source": direction_source, "direction_inputs": direction_inputs, "formation_counter_evidence": formation_counter, "closed_candle_only": True, "lookahead": False, "hypothesis_competition": True})

    selected = candidates[0]; setup = selected["name"]; stage = selected["formation_stage"]
    space = long_space if direction == "BUY" else short_space; blockers: list[str] = []
    if space < MIN_SPACE_ATR: blockers.append(f"INSUFFICIENT_{direction}_STRUCTURAL_SPACE")
    if location_constrained: blockers.append("LOCATION_CONSTRAINT")
    if extension_risk: blockers.append("LOCATION_EXTENSION_RISK")
    blockers.extend(formation_counter); blockers = list(dict.fromkeys(blockers))
    missing = list(selected["missing"]); next_required = list(missing)
    if space < MIN_SPACE_ATR: next_required.append(f"wait for at least {MIN_SPACE_ATR:.2f} ATR {direction.lower()}-side structural space")
    next_required.extend(blockers + ["E7 independent closed-candle entry confirmation", "E8 independent structural/economic survivability"])
    thesis = f"{direction} {setup} | lifecycle={stage} | causal_sequence={' -> '.join(selected['evidence'])}"
    if blockers: thesis += f" | blockers={','.join(blockers)}"
    quality = selected["strength"] - min(30.0, 5.0 * len(blockers)); confidence = selected["strength"] + 4.0 - min(25.0, 5.0 * len(blockers))
    maturity = "MATURE" if stage == "MATURE" else "DEVELOPING"; state = "MATURE" if maturity == "MATURE" and not blockers else "FORMING"
    return _result(state=state, setup=setup, direction=direction, stage=stage, maturity=maturity, thesis=thesis, quality=quality, confidence=max(55.0, min(96.0, confidence)), setup_exists=True, trade_ready=False, supporting=supporting + [f"SETUP_THESIS={thesis}"], counter=formation_counter, missing=missing + blockers, next_required=next_required, invalidation=selected["invalidation"] + ["directional thesis becomes contradictory", "causal setup sequence is invalidated"], candidates=candidates, rejected=rejected, trace={"direction_source": direction_source, "direction_inputs": direction_inputs, "selected_setup": setup, "selected_stage": stage, "selected_strength": selected["strength"], "selected_score_components": selected.get("score_components", {}), "candidate_count": len(candidates), "candidate_margin": round(selected["strength"] - candidates[1]["strength"], 2) if len(candidates) > 1 else None, "formation_counter_evidence": formation_counter, "e3_finding": e3_finding, "e4_event": event, "e4_terminal": terminal, "e4_pending": pending, "e4_event_age_bars": event_age, "e5_location": _text(e5.get("finding", e5.get("state", ""))), "closed_candle_only": True, "lookahead": False, "hypothesis_competition": True, "trade_authority": "E9"})
