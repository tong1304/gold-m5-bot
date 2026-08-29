from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V27"
VERSION = "27.0"
MIN_BARS = 60
ATR_PERIOD = 14
MIN_SPACE_ATR = 0.75
MAX_EVENT_AGE_BARS = 3
SETUP_FAMILIES = ("LIQUIDITY_REVERSAL", "AUCTION_ACCEPTANCE_CONTINUATION", "BREAKOUT_RETEST", "TREND_PULLBACK", "BREAKOUT", "IMPULSE_CONTINUATION")
LIFECYCLE = ("ABSENT", "FORMING", "VALIDATING", "MATURE", "FAILED", "INVALIDATED", "EXPIRED")


def _payload(upstream: dict[str, EngineResult], name: str) -> dict[str, Any]:
    result = upstream.get(name)
    return result.output if result else {}


def _text(v: Any) -> str:
    return str(v or "").upper().strip()


def _norm(v: Any) -> str:
    t = _text(v)
    if t in {"UP", "BULLISH", "BUY", "BUYERS", "LONG", "TREND_UP"}: return "BUY"
    if t in {"DOWN", "BEARISH", "SELL", "SELLERS", "SHORT", "TREND_DOWN"}: return "SELL"
    return "NEUTRAL"


def _num(v: Any, default: float = 0.0) -> float:
    try: return float(v)
    except (TypeError, ValueError): return default


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(v) for v in values if v))


def _atr(bars: list[dict[str, Any]]) -> float:
    sample = bars[-(ATR_PERIOD + 1):]
    if len(sample) < 2: return 0.0
    trs: list[float] = []
    for i, c in enumerate(sample):
        h, l = _num(c.get("high")), _num(c.get("low"))
        if i == 0: trs.append(max(0.0, h - l))
        else:
            p = _num(sample[i - 1].get("close"))
            trs.append(max(h - l, abs(h - p), abs(l - p)))
    return mean(trs[-ATR_PERIOD:]) if trs else 0.0


def _auction(e4: dict[str, Any]) -> dict[str, Any]:
    event = _text(e4.get("event", e4.get("finding")))
    state = _text(e4.get("auction_state", e4.get("state")))
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    direction = "NEUTRAL"
    if any(x in event for x in ("HIGH_SWEEP_REJECTION", "HIGH_FAILED_BREAK_RECLAIM")): direction = "SELL"
    elif any(x in event for x in ("LOW_SWEEP_REJECTION", "LOW_FAILED_BREAK_RECLAIM")): direction = "BUY"
    elif any(x in event for x in ("HIGH_ACCEPTANCE", "HIGH_BREAK")): direction = "BUY"
    elif any(x in event for x in ("LOW_ACCEPTANCE", "LOW_BREAK")): direction = "SELL"
    return {"event": event, "state": state, "terminal": terminal, "pending": state == "PENDING" or "PENDING" in event,
            "age_bars": max(0, int(_num(e4.get("event_age_bars"), 0))), "direction": direction,
            "level": _num(e4.get("event_level")), "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or "")}


def _direction_thesis(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any]):
    a = _auction(e4)
    pressure, internal, external = _norm(e1.get("directional_pressure", e1.get("pressure"))), _norm(e3.get("internal_state", e3.get("internal_count_state"))), _norm(e3.get("external_state", e3.get("external_count_state")))
    support, counter = [], []
    if pressure != "NEUTRAL": support.append(f"E1_PRESSURE={pressure}")
    if internal != "NEUTRAL": support.append(f"E3_INTERNAL={internal}")
    if a["direction"] != "NEUTRAL": support.append(f"E4_AUCTION={a['direction']}")
    e3f = _text(e3.get("finding", e3.get("structure_state")))
    if "MIXED" in e3f or "TRANSITION" in e3f: counter.append("STRUCTURE_NOT_RESOLVED")
    if external != "NEUTRAL" and internal != "NEUTRAL" and external != internal: counter.append("EXTERNAL_INTERNAL_STRUCTURE_CONFLICT")
    votes = [x for x in (pressure, internal, a["direction"]) if x != "NEUTRAL"]
    unique = set(votes)
    if len(unique) == 1 and votes: direction, source = next(iter(unique)), "E1_E3_E4_CONVERGENCE" if len(votes) == 3 else "DIRECTIONAL_CONVERGENCE"
    elif pressure != "NEUTRAL" and internal == pressure: direction, source = pressure, "E1_E3_DIRECTIONAL_CORE"
    elif internal != "NEUTRAL" and a["direction"] == internal: direction, source = internal, "E3_E4_DIRECTIONAL_CORE"
    elif pressure != "NEUTRAL" and a["direction"] == pressure: direction, source = pressure, "E1_E4_DIRECTIONAL_CORE"
    else:
        direction, source = "NEUTRAL", "NO_DIRECTIONAL_CONVERGENCE"
        counter.append("DIRECTIONAL_EVIDENCE_CONFLICT" if len(unique) > 1 else "INSUFFICIENT_DIRECTIONAL_EVIDENCE")
    e2f, e2d = _text(e2.get("finding", e2.get("state"))), _norm(e2.get("direction", e2.get("opportunity_direction")))
    if e2d != "NEUTRAL" and not any(x in e2f for x in ("UNRESOLVED", "UNPROVEN", "AMBIGUOUS")):
        if direction == "NEUTRAL": direction, source = e2d, "E2_CORROBORATION"
        elif direction == e2d: support.append(f"E2_DIRECTION={e2d}")
        else: counter.append("E2_DIRECTION_DISAGREEMENT")
    return direction, _dedupe(support), _dedupe(counter), source


def _candidate_identity(setup: str, direction: str, e3: dict[str, Any], a: dict[str, Any], e5: dict[str, Any]):
    anchor = a.get("event_id") or (f"LEVEL:{a['level']:.5f}" if a.get("level") else "")
    basis = "E4_EVENT_ID" if a.get("event_id") else "E4_EVENT_LEVEL"
    if not anchor and setup == "BREAKOUT_RETEST": anchor, basis = f"PROTECTED:{_num(e3.get('protected_high')):.5f}:{_num(e3.get('protected_low')):.5f}", "E3_PROTECTED_LEVELS"
    if not anchor: anchor, basis = f"VALUE:{_num(e5.get('value_distance_atr')):.3f}", "E5_VALUE_CONTEXT"
    return f"{setup}:{direction}:{anchor}", basis


def _candidate_states(direction: str, a: dict[str, Any], e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e5: dict[str, Any]):
    event, trend = a["event"], _norm(e1.get("trend_state", e1.get("finding")))
    out: list[dict[str, Any]] = []
    def add(name: str, d: str, base: float, evidence: list[str], required: bool = False):
        if d in {"BUY", "SELL"}: out.append({"name": name, "direction": d, "base_quality": base, "evidence": evidence, "event_required": required})
    if "FAILED_BREAK_RECLAIM" in event or "SWEEP_REJECTION" in event: add("LIQUIDITY_REVERSAL", a["direction"], 82, ["E4_LIQUIDITY_EVENT", "E4_DIRECTIONAL_RESPONSE"], True)
    if "ACCEPTANCE" in event: add("AUCTION_ACCEPTANCE_CONTINUATION", a["direction"], 76, ["E4_ACCEPTANCE_EVENT", "E4_AUCTION_RESPONSE"], True)
    if "BREAK" in event or _text(e3.get("bos", e3.get("break_of_structure"))) in {"BREAK", "BOS", "YES"}:
        add("BREAKOUT_RETEST", direction, 72, ["E3_BREAK_EVENT", "E4_AUCTION_CONTEXT"], True)
        add("BREAKOUT", direction, 68, ["E3_BOS", "E4_AUCTION_CONTEXT"], True)
    if trend == direction: add("TREND_PULLBACK", direction, 66, ["E1_TREND_ALIGNMENT", "E3_STRUCTURE"])
    rp, vr = _text(e5.get("repricing_state")), _text(e5.get("value_response"))
    if direction in {"BUY", "SELL"} and ("REPRICING_STARTING" in rp or "ACCEPTED_ABOVE_VALUE" in vr or "ACCEPTED_BELOW_VALUE" in vr):
        add("IMPULSE_CONTINUATION", direction, 60, ["E5_REPRICING_CONTEXT", "E1_DIRECTIONAL_CONTEXT"])
    return out


def _score(c: dict[str, Any], direction: str, opportunity: str, structure: str, a: dict[str, Any], space: float, ds: list[str], dc: list[str], location_ok: bool):
    score = float(c["base_quality"]); support = list(c["evidence"]); counter: list[str] = []; missing: list[str] = []
    gates = {"direction": False, "event": bool(a["event"]) if c["event_required"] else True, "response": a["terminal"], "structure": False, "location": location_ok, "space": space >= MIN_SPACE_ATR, "freshness": a["age_bars"] <= MAX_EVENT_AGE_BARS}
    if c["direction"] == direction and direction in {"BUY", "SELL"}: score += 5; gates["direction"] = True
    else: score -= 30; counter.append("DIRECTION_MISMATCH")
    if ds: score += min(8, 2 * len(ds))
    if dc: score -= min(12, 4 * len(dc)); counter.extend(dc)
    if a["terminal"]: score += 8
    else: score -= 6; missing.append("terminal_auction_confirmation")
    if c["event_required"] and not a["event"]: score -= 25; counter.append("REQUIRED_EVENT_MISSING"); missing.append("setup_event")
    if a["age_bars"] > MAX_EVENT_AGE_BARS: score -= 18; counter.append("STALE_SETUP_EVENT"); missing.append("fresh_current_event")
    elif a["age_bars"] > 0: score -= min(8, a["age_bars"] * 2); support.append(f"EVENT_FRESHNESS={a['age_bars']}B")
    if opportunity in {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS", ""}: score -= 12; counter.append("OPPORTUNITY_MATURITY_UNPROVEN"); missing.append("opportunity_acceptance_follow_through")
    else: score += 5; support.append("E2_OPPORTUNITY_RESOLVED")
    if "MIXED" in structure or "TRANSITION" in structure: score -= 12; counter.append("STRUCTURE_NOT_RESOLVED"); missing.append("structure_resolution")
    else: score += 5; support.append("E3_STRUCTURE_RESOLVED"); gates["structure"] = True
    if space < MIN_SPACE_ATR: score -= 18; counter.append("STRUCTURAL_SPACE_CONSTRAINED"); missing.append("sufficient_structural_space")
    else: score += 6; support.append(f"SPACE_OK={space:.3f}ATR")
    if not location_ok: score -= 20; counter.append("LOCATION_CONTEXT_MISSING"); missing.append("location_value_context")
    return max(0, min(100, score)), _dedupe(support), _dedupe(counter), _dedupe(missing), gates


def _evidence(source: str, statement: str, kind: str = "SUPPORT", strength: str = "MEDIUM") -> dict[str, str]:
    return {"source": source, "kind": kind, "strength": strength, "statement": statement}


def _build_result(state: str, setup: str, direction: str, stage: str, maturity: str, thesis: str, quality: float, confidence: float, exists: bool, ready: bool, supporting: list[str], counter: list[str], missing: list[str], next_required: list[str], invalidation: list[str], candidates: list[dict[str, Any]], rejected: list[str], trace: dict[str, Any], ledger: list[dict[str, str]]) -> EngineResult:
    supporting, counter, missing = _dedupe(supporting), _dedupe(counter), _dedupe(missing)
    next_required, invalidation = _dedupe(next_required), _dedupe(invalidation)
    reasons = _dedupe(counter + ([] if ready else ["SETUP_NOT_TRADE_READY"]))
    observations = [f"candidate_setup={setup}", f"candidate_identity={trace.get('candidate_identity','NONE')}", f"candidate_identity_basis={trace.get('candidate_identity_basis','NONE')}", f"direction={direction}", f"direction_thesis={thesis}", f"formation_stage={stage}", f"maturity={maturity}", f"setup_exists={exists}", f"trade_ready={ready}", f"supporting_evidence={' | '.join(supporting) or 'NONE'}", f"counter_evidence={' | '.join(counter) or 'NONE'}", f"missing_evidence={' | '.join(missing) or 'NONE'}", f"next_required_evidence={' | '.join(next_required) or 'NONE'}", f"invalidation={' | '.join(invalidation) or 'NONE'}"]
    professional = {"conclusion": thesis, "what_is_forming": setup, "candidate_identity": trace.get("candidate_identity"), "directional_thesis": thesis, "direction_source": trace.get("direction_source"), "why_it_is_forming": supporting, "what_is_wrong_with_the_thesis": counter, "what_is_missing": missing, "what_must_happen_next": next_required, "what_invalidates_it": invalidation, "formation_stage": stage, "maturity": maturity, "setup_quality": round(max(0, min(100, quality)), 2), "confidence": round(max(0, min(100, confidence)), 2), "decision_boundary": "E6 describes and stages the setup; E9 alone decides whether a trade is permitted."}
    output = {"architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION, "role": "SETUP_FORMATION_REASONER", "reasoning_role": "SETUP_FORMATION_REASONER", "decision_authority": "E9", "trade_decision_authority": False, "state": state, "setup_state": state, "finding": state, "setup": setup, "setup_family": setup, "candidate_setup": setup, "candidate_setup_identity": trace.get("candidate_identity"), "candidate_identity_basis": trace.get("candidate_identity_basis"), "candidate_setup_thesis": thesis, "direction": direction, "direction_thesis": thesis, "direction_source": trace.get("direction_source"), "stage": stage, "formation_stage": stage, "lifecycle": stage, "lifecycle_states": list(LIFECYCLE), "maturity": maturity, "thesis": thesis, "setup_exists": exists, "trade_ready": ready, "trade_readiness": "READY" if ready else "NOT_READY", "setup_quality": round(max(0, min(100, quality)), 2), "confidence": round(max(0, min(100, confidence)), 2), "candidate_setups": [c.get("name") for c in candidates], "candidate_states": candidates, "rejected_setups": _dedupe(rejected), "supporting_evidence": supporting, "counter_evidence": counter, "missing_evidence": missing, "next_required_evidence": next_required, "invalidation": invalidation, "evidence_ledger": ledger, "observations": observations, "reasoning_trace": trace, "professional_reasoning": professional, "reason_codes": reasons}
    return EngineResult("E6", NAME, False, max(0, min(100, quality)), output, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E6 V27: evidence-integrity-first setup reasoning. E6 never decides a trade."""
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _build_result("NO_SETUP", "NONE", "NEUTRAL", "ABSENT", "UNRESOLVED", "No setup can be established before sufficient closed-candle evidence exists.", 0, 100, False, False, [], [f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"], ["sufficient_closed_candle_data"], [f"wait for at least {MIN_BARS} valid closed candles"], ["insufficient_history"], [], list(SETUP_FAMILIES), [], {"summary": "insufficient closed-candle history", "decision": "DEFER"}, [_evidence("DATA", f"closed_candles={len(bars)}", "CONSTRAINT", "HIGH")])
    try:
        if _atr(bars) <= 0: raise ValueError
        for candle in bars[-MIN_BARS:]:
            for key in ("open", "high", "low", "close"):
                value = float(candle[key])
                if value != value: raise ValueError
    except (KeyError, TypeError, ValueError):
        return _build_result("NO_SETUP", "NONE", "NEUTRAL", "ABSENT", "UNRESOLVED", "Setup reasoning is deferred because closed-candle OHLC data is invalid.", 0, 100, False, False, [], ["INVALID_MARKET_DATA"], ["valid_closed_candle_ohlc"], ["provide valid closed-candle OHLC values"], ["invalid_market_data"], [], list(SETUP_FAMILIES), [], {"summary": "invalid closed-candle data", "decision": "DEFER"}, [_evidence("DATA", "closed-candle OHLC validation failed", "CONSTRAINT", "HIGH")])

    e1, e2, e3, e4, e5 = (_payload(upstream, n) for n in ("E1", "E2", "E3", "E4", "E5"))
    a = _auction(e4)
    direction, ds, dc, direction_source = _direction_thesis(e1, e2, e3, e4)
    opportunity = _text(e2.get("finding", e2.get("state"))) or "UNRESOLVED"
    structure = _text(e3.get("finding", e3.get("structure_state"))) or "UNKNOWN"
    internal, external = _norm(e3.get("internal_state", e3.get("internal_count_state"))), _norm(e3.get("external_state", e3.get("external_count_state")))
    mixed = "MIXED" in structure or "TRANSITION" in structure or (internal != "NEUTRAL" and external != "NEUTRAL" and internal != external)
    space = _num(e5.get("available_space_atr_long") if direction == "BUY" else e5.get("available_space_atr_short"))
    integrity: list[str] = []
    if not e2: integrity.append("E2_CONTEXT_MISSING")
    if not e3: integrity.append("E3_STRUCTURE_CONTEXT_MISSING")
    if not e4: integrity.append("E4_AUCTION_CONTEXT_MISSING")
    if not e5: integrity.append("E5_LOCATION_CONTEXT_MISSING")
    if opportunity in {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS"}: integrity.append("E2_OPPORTUNITY_UNRESOLVED")
    if mixed: integrity.append("E3_STRUCTURE_UNRESOLVED")
    if internal != "NEUTRAL" and external != "NEUTRAL" and internal != external: integrity.append("E3_INTERNAL_EXTERNAL_CONFLICT")
    if a["pending"] and not a["terminal"]: integrity.append("E4_AUCTION_PENDING")

    candidates = _candidate_states(direction, a, e1, e2, e3, e5)
    scored: list[dict[str, Any]] = []
    for c in candidates:
        score, sup, con, miss, gates = _score(c, direction, opportunity, structure, a, space, ds, dc, bool(e5))
        if opportunity in {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS"}: sup = [x for x in sup if x != "E2_OPPORTUNITY_RESOLVED"]
        if mixed: sup = [x for x in sup if x != "E3_STRUCTURE_RESOLVED"]
        scored.append({**c, "causal_score": round(score, 2), "supporting_evidence": _dedupe(sup), "counter_evidence": _dedupe(con), "missing_proof": _dedupe(miss), "proof_gates": gates, "evidence_integrity": _dedupe(integrity)})
    scored.sort(key=lambda x: (x["causal_score"], sum(bool(v) for v in x["proof_gates"].values()), x["base_quality"]), reverse=True)

    supporting, counter, missing, next_required, invalidation = list(ds), list(dc) + list(integrity), [], [], []
    if not scored:
        setup, exists, stage, maturity, ready = "NONE", False, "ABSENT", "UNRESOLVED", False
        quality, confidence = 15, 70
        thesis = "No setup hypothesis has sufficient causal evidence to become a valid formation."
        missing.append("causal_setup_evidence"); next_required.append("a specific closed-candle setup event with directional response")
        identity, identity_basis = "NONE", "NONE"
    else:
        primary = scored[0]; setup, exists = primary["name"], True
        identity, identity_basis = _candidate_identity(setup, direction, e3, a, e5)
        rejected = [f"{x['name']}:OUTRANKED_BY_{setup}:SCORE_{x['causal_score']:.2f}" for x in scored[1:]]
        all_gates = all(bool(v) for v in primary["proof_gates"].values())
        hard_conflict = any(x in counter for x in ("E2_DIRECTION_DISAGREEMENT", "EXTERNAL_INTERNAL_STRUCTURE_CONFLICT", "DIRECTIONAL_EVIDENCE_CONFLICT"))
        if hard_conflict:
            stage, maturity, ready, quality, confidence = "FAILED", "FAILED", False, min(primary["causal_score"], 45), 35
            counter.append("THESIS_INVALIDATED"); thesis = f"{direction if direction != 'NEUTRAL' else 'NEUTRAL'} {setup} failed because contradictory directional evidence defeats the causal thesis."; next_required.append("new independent setup event after failure")
        elif a["age_bars"] > MAX_EVENT_AGE_BARS:
            stage, maturity, ready, quality, confidence = "EXPIRED", "EXPIRED", False, min(primary["causal_score"], 35), 30
            counter.append("STALE_SETUP_EVENT"); missing.append("fresh_current_event"); thesis = f"{setup} is expired because its initiating event is stale; a new causal event is required."; next_required.append("new independent setup event after expiry")
        elif all_gates and not integrity:
            stage, maturity, ready, quality, confidence = "MATURE", "MATURE", False, max(82, primary["causal_score"]), min(96, 82 + primary["causal_score"] * 0.12)
            thesis = f"{direction} {setup} is mature: all seven causal proof gates are satisfied; execution confirmation remains downstream."
        elif primary["proof_gates"]["direction"] and primary["proof_gates"]["event"] and primary["proof_gates"]["structure"]:
            stage, maturity, ready, quality, confidence = "VALIDATING", "VALIDATING", False, primary["causal_score"], 72
            thesis = f"{direction} {setup} is validating: the causal core exists, but one or more proof gates remain incomplete."
        else:
            stage, maturity, ready, quality, confidence = "FORMING", "FORMING", False, primary["causal_score"], 62
            thesis = f"{direction if direction != 'NEUTRAL' else 'NEUTRAL'} {setup} is forming: the hypothesis is identifiable but its causal chain is incomplete."
        supporting.extend(primary["supporting_evidence"]); counter.extend(primary["counter_evidence"]); missing.extend(primary["missing_proof"]); next_required.extend(primary["missing_proof"])
        if not a["terminal"]: next_required.append("closed-candle acceptance/rejection follow-through")
        if opportunity in {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS"}: next_required.append("E2 opportunity acceptance/follow-through")
        if mixed: next_required.append("resolve internal/external structure conflict")
        if space < MIN_SPACE_ATR and direction in {"BUY", "SELL"}: next_required.append(f"structural space >= {MIN_SPACE_ATR:.2f} ATR")
        if setup == "LIQUIDITY_REVERSAL": invalidation = ["closed-candle acceptance back through liquidity anchor", "opposing confirmed auction response", "protected structure breaks against reversal"]
        elif setup in {"BREAKOUT", "BREAKOUT_RETEST", "AUCTION_ACCEPTANCE_CONTINUATION"}: invalidation = ["closed-candle rejection back through acceptance/breakout anchor", "failed follow-through", "structure invalidates continuation"]
        elif setup == "TREND_PULLBACK": invalidation = ["trend no longer agrees with setup direction", "protected structure breaks", "pullback fails to continue"]
        else: invalidation = ["closed-candle structure invalidates directional thesis", "opposing confirmed auction response"]
        if a["level"]: invalidation.append(f"anchor_level={a['level']:.5f}")

    ledger = [_evidence("E1", f"directional_pressure={_norm(e1.get('directional_pressure', e1.get('pressure')))}", "CONTEXT", "MEDIUM"), _evidence("E2", f"opportunity={opportunity}", "CONTEXT", "HIGH"), _evidence("E3", f"structure={structure}", "STRUCTURE", "HIGH"), _evidence("E4", f"auction_event={a['event'] or 'NONE'}", "EVENT", "HIGH"), _evidence("E4", f"auction_state={a['state'] or 'NONE'}", "STATE", "HIGH"), _evidence("E4", f"event_age_bars={a['age_bars']}", "FRESHNESS", "HIGH"), _evidence("E5", f"space_atr={space:.4f}", "CONSTRAINT", "HIGH"), _evidence("E6", f"evidence_integrity={'PASS' if not integrity else 'FAIL'}", "INTEGRITY", "HIGH")]
    trace = {"summary": f"E1 context -> E2 opportunity -> E3 structure -> E4 auction -> E5 location -> evidence integrity -> hypothesis competition -> primary={setup} -> lifecycle={stage}", "decision": "DESCRIBE_SETUP_ONLY", "candidate_identity": identity, "candidate_identity_basis": identity_basis, "direction_source": direction_source, "causal_chain": ["E1_MARKET_CONTEXT", "E2_OPPORTUNITY_STATE", "E3_STRUCTURE", "E4_AUCTION_EVENT", "E5_LOCATION_VALUE", "E6_EVIDENCE_INTEGRITY", "E6_HYPOTHESIS_COMPETITION", "E6_LIFECYCLE"], "candidate_selection_rule": "CAUSAL_SCORE_THEN_PROOF_COMPLETENESS_THEN_BASE_QUALITY", "hypothesis_competition": {"primary": setup, "ranked": [{"name": c["name"], "direction": c["direction"], "causal_score": c["causal_score"], "proof_gates": c["proof_gates"], "rejected": c["name"] != setup} for c in scored]}, "lifecycle_rule": "ABSENT -> FORMING -> VALIDATING -> MATURE; contradiction -> FAILED/INVALIDATED; stale event -> EXPIRED", "maturity_gate": scored[0]["proof_gates"] if scored else {k: False for k in ("direction", "event", "response", "structure", "location", "space", "freshness")}, "evidence_integrity": {"status": "PASS" if not integrity else "FAIL", "violations": _dedupe(integrity), "upstream_is_source_of_truth": True}, "counter_evidence_active": _dedupe(counter), "missing_proof": _dedupe(missing), "next_proof": _dedupe(next_required), "invalidation_conditions": _dedupe(invalidation)}
    return _build_result(stage if stage != "ABSENT" else "NO_SETUP", setup, direction, stage, maturity, thesis, quality, confidence, exists, ready, supporting, counter, missing, next_required, invalidation, scored, rejected if scored else [], trace, ledger)
