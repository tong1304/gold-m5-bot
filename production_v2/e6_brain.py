from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V26"
VERSION = "26.0"
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
    sample = bars[-(ATR_PERIOD + 1):]
    if len(sample) < 2:
        return 0.0
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
    terminal = state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED"} or "TERMINAL" in state
    pending = state == "PENDING" or "PENDING" in event
    direction = "NEUTRAL"
    if any(x in event for x in ("HIGH_SWEEP_REJECTION", "HIGH_FAILED_BREAK_RECLAIM")):
        direction = "SELL"
    elif any(x in event for x in ("LOW_SWEEP_REJECTION", "LOW_FAILED_BREAK_RECLAIM")):
        direction = "BUY"
    elif any(x in event for x in ("HIGH_ACCEPTANCE", "HIGH_BREAK")):
        direction = "BUY"
    elif any(x in event for x in ("LOW_ACCEPTANCE", "LOW_BREAK")):
        direction = "SELL"
    return {"event": event, "state": state, "terminal": terminal, "pending": pending,
            "age_bars": max(0, int(_num(e4.get("event_age_bars"), 0))),
            "direction": direction, "level": _num(e4.get("event_level")),
            "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or "")}


def _direction_thesis(e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e4: dict[str, Any]):
    auction = _auction(e4)
    pressure = _norm(e1.get("directional_pressure", e1.get("pressure")))
    external = _norm(e3.get("external_state", e3.get("external_count_state")))
    internal = _norm(e3.get("internal_state", e3.get("internal_count_state")))
    support: list[str] = []
    counter: list[str] = []
    votes = [x for x in (pressure, internal, auction["direction"]) if x != "NEUTRAL"]
    if pressure != "NEUTRAL": support.append(f"E1_PRESSURE={pressure}")
    if internal != "NEUTRAL": support.append(f"E3_INTERNAL={internal}")
    if auction["direction"] != "NEUTRAL": support.append(f"E4_AUCTION={auction['direction']}")
    if external != "NEUTRAL" and internal != "NEUTRAL" and external != internal:
        counter.append("EXTERNAL_INTERNAL_STRUCTURE_CONFLICT")
    if "MIXED" in _text(e3.get("finding", e3.get("structure_state"))):
        counter.append("STRUCTURE_MIXED")
    unique = set(votes)
    if len(unique) == 1 and votes:
        direction = next(iter(unique)); source = "E1_E3_E4_CONVERGENCE" if len(votes) == 3 else "DIRECTIONAL_CONVERGENCE"
    elif pressure != "NEUTRAL" and internal == pressure:
        direction, source = pressure, "E1_E3_DIRECTIONAL_CORE"
    elif internal != "NEUTRAL" and auction["direction"] == internal:
        direction, source = internal, "E3_E4_DIRECTIONAL_CORE"
    elif pressure != "NEUTRAL" and auction["direction"] == pressure:
        direction, source = pressure, "E1_E4_DIRECTIONAL_CORE"
    else:
        direction, source = "NEUTRAL", "NO_DIRECTIONAL_CONVERGENCE"
        counter.append("DIRECTIONAL_EVIDENCE_CONFLICT" if len(unique) > 1 else "INSUFFICIENT_DIRECTIONAL_EVIDENCE")
    e2_finding = _text(e2.get("finding", e2.get("state")))
    e2_direction = _norm(e2.get("direction", e2.get("opportunity_direction")))
    if e2_direction != "NEUTRAL" and not any(x in e2_finding for x in ("UNRESOLVED", "UNPROVEN")):
        if direction == "NEUTRAL": direction, source = e2_direction, "E2_CORROBORATION"
        elif direction == e2_direction: support.append(f"E2_DIRECTION={e2_direction}")
        else: counter.append("E2_DIRECTION_DISAGREEMENT")
    return direction, _dedupe(support), _dedupe(counter), source


def _candidate_identity(setup: str, direction: str, e3: dict[str, Any], auction: dict[str, Any], e5: dict[str, Any]):
    event_id = auction.get("event_id") or ""
    level = auction.get("level") or 0.0
    if event_id:
        anchor, basis = event_id, "E4_EVENT_ID"
    elif level:
        anchor, basis = f"LEVEL:{level:.5f}", "E4_EVENT_LEVEL"
    elif setup == "BREAKOUT_RETEST":
        anchor, basis = f"PROTECTED:{_num(e3.get('protected_high')):.5f}:{_num(e3.get('protected_low')):.5f}", "E3_PROTECTED_LEVELS"
    elif _text(e3.get("sequence")):
        anchor, basis = f"SEQUENCE:{_text(e3.get('sequence'))[-80:]}", "E3_STRUCTURE_SEQUENCE"
    else:
        anchor, basis = f"VALUE:{_num(e5.get('value_distance_atr')):.3f}", "E5_VALUE_CONTEXT"
    return f"{setup}:{direction}:{anchor}", basis


def _candidate_states(direction: str, auction: dict[str, Any], e1: dict[str, Any], e2: dict[str, Any], e3: dict[str, Any], e5: dict[str, Any]):
    event = auction["event"]
    opportunity = _text(e2.get("finding", e2.get("state")))
    structure = _text(e3.get("finding", e3.get("structure_state")))
    trend = _norm(e1.get("trend_state", e1.get("finding")))
    space = _num(e5.get("available_space_atr_long") if direction == "BUY" else e5.get("available_space_atr_short"))
    candidates: list[dict[str, Any]] = []
    def add(name: str, d: str, base: float, evidence: list[str], event_required: bool = False):
        if d not in {"BUY", "SELL"}: return
        candidates.append({"name": name, "direction": d, "base_quality": base, "evidence": evidence,
                           "event_required": event_required, "opportunity_state": opportunity or "UNRESOLVED",
                           "structure_state": structure or "UNKNOWN", "space_atr": round(space, 4)})
    if "FAILED_BREAK_RECLAIM" in event or "SWEEP_REJECTION" in event:
        add("LIQUIDITY_REVERSAL", auction["direction"], 82.0, ["E4_LIQUIDITY_EVENT", "E4_DIRECTIONAL_RESPONSE"], True)
    if "ACCEPTANCE" in event:
        add("AUCTION_ACCEPTANCE_CONTINUATION", auction["direction"], 76.0, ["E4_ACCEPTANCE_EVENT", "E4_AUCTION_RESPONSE"], True)
    if "BREAK" in event or "BOS" in _text(e3.get("bos")):
        add("BREAKOUT_RETEST", direction, 72.0, ["E3_BREAK_EVENT", "E4_AUCTION_CONTEXT"], True)
        add("BREAKOUT", direction, 68.0, ["E3_BOS", "E4_AUCTION_CONTEXT"], True)
    if trend == direction:
        add("TREND_PULLBACK", direction, 66.0, ["E1_TREND_ALIGNMENT", "E3_STRUCTURE"], False)
    if direction in {"BUY", "SELL"} and ("REPRICING_STARTING" in _text(e5.get("repricing_state")) or "ACCEPTED_ABOVE_VALUE" in _text(e5.get("value_response"))):
        add("IMPULSE_CONTINUATION", direction, 60.0, ["E5_REPRICING_CONTEXT", "E1_DIRECTIONAL_CONTEXT"], False)
    return candidates


def _score_candidate(c: dict[str, Any], direction: str, opportunity: str, structure: str, auction: dict[str, Any], space: float, direction_support: list[str], direction_counter: list[str]):
    score = float(c["base_quality"])
    support = list(c["evidence"])
    counter: list[str] = []
    missing: list[str] = []
    if c["direction"] != direction:
        score -= 30; counter.append("DIRECTION_MISMATCH")
    elif direction in {"BUY", "SELL"}:
        score += 5
    if direction_support: score += min(8.0, 2.0 * len(direction_support))
    if direction_counter: score -= min(12.0, 4.0 * len(direction_counter)); counter.extend(direction_counter)
    if auction["terminal"]: score += 8
    else: score -= 6; missing.append("terminal_auction_confirmation")
    if auction["age_bars"] > MAX_EVENT_AGE_BARS:
        score -= 18; counter.append("STALE_SETUP_EVENT")
    elif auction["age_bars"] > 0:
        score -= min(8, auction["age_bars"] * 2); support.append(f"EVENT_FRESHNESS={auction['age_bars']}B")
    if opportunity in {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS"}:
        score -= 12; counter.append("OPPORTUNITY_MATURITY_UNPROVEN"); missing.append("opportunity_follow_through")
    else:
        score += 5; support.append("E2_OPPORTUNITY_RESOLVED")
    if "MIXED" in structure:
        score -= 12; counter.append("STRUCTURE_MIXED"); missing.append("structure_resolution")
    else:
        score += 5; support.append("E3_STRUCTURE_NOT_MIXED")
    if space < MIN_SPACE_ATR:
        score -= 18; counter.append("STRUCTURAL_SPACE_CONSTRAINED"); missing.append("sufficient_structural_space")
    else:
        score += 6; support.append(f"SPACE_OK={space:.3f}ATR")
    if c["event_required"] and not auction["event"]:
        score -= 25; counter.append("REQUIRED_EVENT_MISSING"); missing.append("setup_event")
    score = max(0.0, min(100.0, score))
    return score, _dedupe(support), _dedupe(counter), _dedupe(missing)


def _build_result(state: str, setup: str, direction: str, stage: str, maturity: str, thesis: str, quality: float, confidence: float, exists: bool, ready: bool, supporting: list[str], counter: list[str], missing: list[str], next_required: list[str], invalidation: list[str], candidates: list[dict[str, Any]], rejected: list[str], trace: dict[str, Any], ledger: list[dict[str, str]]) -> EngineResult:
    supporting, counter = _dedupe(supporting), _dedupe(counter)
    missing, next_required, invalidation = _dedupe(missing), _dedupe(next_required), _dedupe(invalidation)
    quality, confidence = max(0.0, min(100.0, float(quality))), max(0.0, min(100.0, float(confidence)))
    observations = [f"candidate_setup={setup}", f"candidate_identity={trace.get('candidate_identity') or 'NONE'}", f"candidate_identity_basis={trace.get('candidate_identity_basis') or 'NONE'}", f"direction={direction}", f"direction_thesis={thesis}", f"formation_stage={stage}", f"maturity={maturity}", f"setup_exists={exists}", f"trade_ready={ready}", f"supporting_evidence={' | '.join(supporting) or 'NONE'}", f"counter_evidence={' | '.join(counter) or 'NONE'}", f"missing_evidence={' | '.join(missing) or 'NONE'}", f"next_required_evidence={' | '.join(next_required) or 'NONE'}", f"invalidation={' | '.join(invalidation) or 'NONE'}", f"reasoning_trace={trace.get('summary','NONE')}"]
    professional = {"conclusion": thesis, "what_is_forming": setup, "candidate_identity": trace.get("candidate_identity"), "candidate_identity_basis": trace.get("candidate_identity_basis"), "directional_thesis": thesis, "direction_source": trace.get("direction_source"), "why_it_is_forming": supporting, "what_is_wrong_with_the_thesis": counter, "what_is_missing": missing, "what_must_happen_next": next_required, "what_invalidates_it": invalidation, "formation_stage": stage, "maturity": maturity, "setup_quality": round(quality,2), "confidence": round(confidence,2), "decision_boundary": "E6 describes and stages the setup; E9 alone decides whether a trade is permitted."}
    reasons = _dedupe(counter + ([] if ready else ["SETUP_NOT_TRADE_READY"]))
    output = {"architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION, "role":"SETUP_FORMATION_REASONER", "reasoning_role":"SETUP_FORMATION_REASONER", "decision_authority":"E9", "trade_decision_authority":False, "state":state, "setup_state":state, "finding":state, "setup":setup, "setup_family":setup, "candidate_setup":setup, "candidate_setup_identity":trace.get("candidate_identity"), "candidate_identity_basis":trace.get("candidate_identity_basis"), "candidate_setup_thesis":thesis, "direction":direction, "direction_thesis":thesis, "direction_source":trace.get("direction_source"), "stage":stage, "formation_stage":stage, "lifecycle":stage, "lifecycle_states":list(LIFECYCLE), "maturity":maturity, "thesis":thesis, "setup_exists":exists, "trade_ready":ready, "trade_readiness":"READY" if ready else "NOT_READY", "setup_quality":round(quality,2), "confidence":round(confidence,2), "candidate_setups":[c.get("name") for c in candidates], "candidate_states":candidates, "rejected_setups":_dedupe(rejected), "supporting_evidence":supporting, "counter_evidence":counter, "missing_evidence":missing, "next_required_evidence":next_required, "invalidation":invalidation, "invalidation_status":"TRIGGERED" if "THESIS_INVALIDATED" in counter else "NOT_TRIGGERED", "evidence_ledger":ledger, "observations":observations, "reasoning_trace":trace, "professional_reasoning":professional, "specialists":{"setup_formation":{"role":"SETUP_FORMATION_REASONER","question":QUESTION,"conclusion":thesis,"observations":observations+[f"candidate_count={len(candidates)}",f"rejected_setups={','.join(_dedupe(rejected)) or 'NONE'}"],"reason_codes":reasons,"candidate_setup":setup,"candidate_setup_identity":trace.get("candidate_identity"),"candidate_identity_basis":trace.get("candidate_identity_basis"),"direction":direction,"direction_thesis":thesis,"supporting_evidence":supporting,"counter_evidence":counter,"missing_evidence":missing,"next_required_evidence":next_required,"invalidation":invalidation,"formation_stage":stage,"maturity":maturity}}, "reason_codes":reasons}
    return EngineResult("E6", NAME, False, quality, output, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """E6 V26: reason about setup hypotheses, causal proof, lifecycle and failure without deciding trades."""
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _build_result("NO_SETUP","NONE","NEUTRAL","ABSENT","UNRESOLVED","No setup can be established before sufficient closed-candle evidence exists.",0,100,False,False,[],[f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"],["sufficient_closed_candle_data"],[f"wait for at least {MIN_BARS} valid closed candles"],["insufficient_history"],[],list(SETUP_FAMILIES),{"summary":"insufficient closed-candle history","decision":"DEFER"},[_evidence("DATA",f"closed_candles={len(bars)}","CONSTRAINT","HIGH")])
    try:
        atr = _atr(bars)
        if atr <= 0: raise ValueError("invalid ATR")
        for candle in bars[-MIN_BARS:]:
            for key in ("open","high","low","close"):
                value=float(candle[key])
                if value != value: raise ValueError("NaN OHLC")
    except (KeyError, TypeError, ValueError):
        return _build_result("NO_SETUP","NONE","NEUTRAL","ABSENT","UNRESOLVED","Setup reasoning is deferred because closed-candle OHLC data is invalid.",0,100,False,False,[],["INVALID_MARKET_DATA"],["valid_closed_candle_ohlc"],["provide valid closed-candle OHLC values"],["invalid_market_data"],[],list(SETUP_FAMILIES),{"summary":"invalid closed-candle data","decision":"DEFER"},[_evidence("DATA","closed-candle OHLC validation failed","CONSTRAINT","HIGH")])

    e1,e2,e3,e4,e5 = (_payload(upstream,n) for n in ("E1","E2","E3","E4","E5"))
    auction = _auction(e4)
    direction, direction_support, direction_counter, direction_source = _direction_thesis(e1,e2,e3,e4)
    opportunity = _text(e2.get("finding",e2.get("state")))
    structure = _text(e3.get("finding",e3.get("structure_state")))
    internal, external = _norm(e3.get("internal_state",e3.get("internal_count_state"))), _norm(e3.get("external_state",e3.get("external_count_state")))
    mixed = "MIXED" in structure or (internal != "NEUTRAL" and external != "NEUTRAL" and internal != external)
    bos = _text(e3.get("bos",e3.get("break_of_structure")))
    value_response = _text(e5.get("value_response",e5.get("repricing_state")))
    space = _num(e5.get("available_space_atr_long") if direction == "BUY" else e5.get("available_space_atr_short"))
    candidates = _candidate_states(direction,auction,e1,e2,e3,e5)
    rejected: list[str] = []
    supporting, counter, missing, next_required, invalidation = list(direction_support), list(direction_counter), [], [], []

    if not e2: counter.append("E2_CONTEXT_MISSING")
    if not e3: counter.append("E3_STRUCTURE_CONTEXT_MISSING")
    if not e4: counter.append("E4_AUCTION_CONTEXT_MISSING")
    if not e5: counter.append("E5_LOCATION_CONTEXT_MISSING")
    if mixed: counter.append("STRUCTURE_MIXED")
    if opportunity in {"UNRESOLVED","UNPROVEN","AMBIGUOUS",""}: counter.append("OPPORTUNITY_MATURITY_UNPROVEN"); missing.append("opportunity_acceptance_follow_through")
    if auction["pending"] and not auction["terminal"]: counter.append("AUCTION_PENDING"); missing.append("terminal_auction_confirmation")
    if auction["age_bars"] > MAX_EVENT_AGE_BARS: counter.append("STALE_SETUP_EVENT"); missing.append("fresh_current_event")
    if direction in {"BUY","SELL"} and space < MIN_SPACE_ATR: counter.append("STRUCTURAL_SPACE_CONSTRAINED"); missing.append("sufficient_structural_space")
    if direction not in {"BUY","SELL"}: missing.append("directional_convergence")

    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        score, c_support, c_counter, c_missing = _score_candidate(candidate,direction,opportunity,structure,auction,space,direction_support,direction_counter)
        item = dict(candidate); item.update({"causal_score":round(score,2),"supporting_evidence":c_support,"counter_evidence":c_counter,"missing_proof":c_missing,"proof_gates":{"direction":candidate["direction"]==direction and direction in {"BUY","SELL"},"event":bool(auction["event"]),"response":auction["terminal"],"structure":not mixed,"location":bool(e5),"space":space>=MIN_SPACE_ATR,"freshness":auction["age_bars"]<=MAX_EVENT_AGE_BARS}})
        scored.append(item)
    scored.sort(key=lambda c:(c["causal_score"], c["base_quality"]), reverse=True)

    if not scored:
        setup="NONE"; exists=False; stage="ABSENT"; maturity="UNRESOLVED"; ready=False; quality=15.0; confidence=70.0
        thesis="No setup hypothesis has sufficient causal evidence to become a valid formation."
        missing.append("causal_setup_evidence"); next_required.append("a specific closed-candle setup event with directional response")
    else:
        primary=scored[0]; setup=str(primary["name"]); exists=True
        for alt in scored[1:]:
            rejected.append(f"{alt['name']}:OUTRANKED_BY_{setup}")
        identity, identity_basis = _candidate_identity(setup,direction,e3,auction,e5)
        all_gates=all(primary["proof_gates"].values())
        causal_core=primary["proof_gates"]["direction"] and primary["proof_gates"]["event"] and primary["proof_gates"]["structure"]
        hard_conflict=any(x in counter for x in ("E2_DIRECTION_DISAGREEMENT","EXTERNAL_INTERNAL_STRUCTURE_CONFLICT","DIRECTIONAL_EVIDENCE_CONFLICT"))
        if hard_conflict:
            stage="FAILED"; maturity="FAILED"; ready=False; quality=min(primary["causal_score"],45.0); confidence=35.0; counter.append("THESIS_INVALIDATED"); missing=[]; next_required=["new independent setup event after failure"]
            thesis=f"{direction if direction!='NEUTRAL' else 'NEUTRAL'} {setup} failed because competing directional evidence defeats the causal thesis."
        elif all_gates and not hard_conflict:
            stage="MATURE"; maturity="MATURE"; ready=True; quality=max(82.0,primary["causal_score"]); confidence=min(96.0,82.0+primary["causal_score"]*0.12)
            thesis=f"{direction} {setup} is mature: direction, event, response, structure, location, space and freshness are simultaneously proven."
        elif causal_core and not hard_conflict:
            stage="VALIDATING"; maturity="VALIDATING"; ready=False; quality=primary["causal_score"]; confidence=72.0
            thesis=f"{direction} {setup} is validating: the causal core exists, but one or more proof gates remain incomplete."
        else:
            stage="FORMING"; maturity="FORMING"; ready=False; quality=primary["causal_score"]; confidence=62.0
            thesis=f"{direction if direction!='NEUTRAL' else 'NEUTRAL'} {setup} is forming: the hypothesis is identifiable but its causal chain is incomplete."
        supporting.extend(primary["supporting_evidence"]); counter.extend(primary["counter_evidence"]); missing.extend(primary["missing_proof"]); missing.extend(direction_counter)
        next_required.extend(primary["missing_proof"])
        if not auction["terminal"]: next_required.append("closed-candle acceptance/rejection follow-through")
        if mixed: next_required.append("resolve internal/external structure conflict")
        if direction not in {"BUY","SELL"}: next_required.append("directional evidence convergence")
        if auction["age_bars"] > MAX_EVENT_AGE_BARS: next_required.append("fresh setup event")
        if space < MIN_SPACE_ATR and direction in {"BUY","SELL"}: next_required.append("structural space >= MIN_SPACE_ATR")
        if setup == "LIQUIDITY_REVERSAL": invalidation += ["closed-candle acceptance back through liquidity anchor","opposing confirmed auction response","protected structure breaks against reversal"]
        elif setup in {"BREAKOUT","BREAKOUT_RETEST","AUCTION_ACCEPTANCE_CONTINUATION"}: invalidation += ["closed-candle rejection back through acceptance/breakout anchor","failed follow-through","structure invalidates continuation"]
        elif setup == "TREND_PULLBACK": invalidation += ["trend no longer agrees with setup direction","protected structure breaks","pullback fails to continue"]
        else: invalidation += ["closed-candle structure invalidates directional thesis","opposing confirmed auction response"]
        if auction["level"]: invalidation.append(f"anchor_level={auction['level']:.5f}")
        if auction["age_bars"] > MAX_EVENT_AGE_BARS: stage="EXPIRED"; maturity="EXPIRED"; ready=False; quality=min(quality,35.0); thesis=f"{setup} is expired because its initiating event is stale; a new causal event is required."; next_required=["new independent setup event after expiry"]
        identity = locals().get("identity", "NONE"); identity_basis = locals().get("identity_basis", "NONE")

    invalidated = "THESIS_INVALIDATED" in counter
    if invalidated and stage not in {"FAILED","EXPIRED"}:
        stage="INVALIDATED"; maturity="INVALIDATED"; ready=False; confidence=min(confidence,35.0); thesis=f"{setup} thesis is invalidated by contradictory causal evidence."; missing=[]; next_required=["new independent setup event after invalidation"]

    ledger=[_evidence("E1",f"trend={_text(e1.get('trend_state',e1.get('finding'))) or 'MISSING'}","CONTEXT","MEDIUM"),_evidence("E1",f"directional_pressure={_norm(e1.get('directional_pressure',e1.get('pressure')))}","SUPPORT","MEDIUM"),_evidence("E2",f"opportunity={opportunity or 'MISSING'}","CONTEXT","HIGH"),_evidence("E3",f"structure={structure or 'MISSING'}","STRUCTURE","HIGH"),_evidence("E3",f"bos={bos or 'NONE'}","EVENT","HIGH"),_evidence("E4",f"auction_event={auction['event'] or 'NONE'}","EVENT","HIGH"),_evidence("E4",f"auction_state={auction['state'] or 'NONE'}","STATE","HIGH"),_evidence("E4",f"event_age_bars={auction['age_bars']}","FRESHNESS","HIGH"),_evidence("E5",f"value_response={value_response or 'NONE'}","LOCATION","MEDIUM"),_evidence("E5",f"space_atr={space:.4f}","CONSTRAINT","HIGH")]
    identity = locals().get("identity", "NONE"); identity_basis = locals().get("identity_basis", "NONE")
    trace={"summary":f"E1 context -> E2 opportunity -> E3 structure -> E4 auction -> E5 location -> hypothesis competition -> primary={setup} -> direction={direction} -> lifecycle={stage}","decision":"DESCRIBE_SETUP_ONLY","candidate_identity":identity,"candidate_identity_basis":identity_basis,"direction_source":direction_source,"causal_chain":["E1_MARKET_CONTEXT","E2_OPPORTUNITY_STATE","E3_STRUCTURE","E4_AUCTION_EVENT","E5_LOCATION_VALUE","E6_HYPOTHESIS_COMPETITION","E6_LIFECYCLE"],"candidate_selection_rule":"CAUSAL_SCORE_THEN_PROOF_COMPLETENESS_THEN_BASE_QUALITY","hypothesis_competition":{"primary":setup,"ranked":[{"name":c.get('name'),"direction":c.get('direction'),"causal_score":c.get('causal_score'),"rejected":c.get('name')!=setup} for c in scored]},"lifecycle_rule":"ABSENT -> FORMING -> VALIDATING -> MATURE; contradiction -> FAILED/INVALIDATED; stale event -> EXPIRED","maturity_gate":scored[0]["proof_gates"] if scored else {"direction":False,"event":False,"response":False,"structure":False,"location":False,"space":False,"freshness":False},"counter_evidence_active":_dedupe(counter),"missing_proof":_dedupe(missing),"next_proof":_dedupe(next_required),"invalidation_conditions":_dedupe(invalidation)}
    return _build_result(stage if stage not in {"ABSENT"} else "NO_SETUP",setup,direction,stage,maturity,thesis,quality,confidence,exists,ready,supporting,counter,missing,next_required,invalidation,scored,rejected,trace,ledger)


def _evidence(source: str, statement: str, kind: str = "SUPPORT", strength: str = "MEDIUM") -> dict[str, str]:
    return {"source": source, "kind": kind, "strength": strength, "statement": statement}
