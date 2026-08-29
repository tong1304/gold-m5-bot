from __future__ import annotations

from statistics import mean
from typing import Any

from .contracts import EngineResult

NAME = "Setup Brain"
QUESTION = "What setup is forming, in what direction, and at what stage?"
ARCHITECTURE = "E6_PROFESSIONAL_SETUP_FORMATION_BRAIN_V18"
VERSION = "18.0"
MIN_BARS = 60
ATR_PERIOD = 14
MIN_SPACE_ATR = 0.75
SETUP_FAMILIES = ("LIQUIDITY_REVERSAL", "BREAKOUT_RETEST", "TREND_PULLBACK", "BREAKOUT", "IMPULSE_CONTINUATION")


def _payload(upstream: dict[str, EngineResult], name: str) -> dict[str, Any]:
    result = upstream.get(name)
    return result.output if result else {}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _norm(value: Any) -> str:
    text = _text(value)
    if text in {"UP", "BULLISH", "BUY", "BUYERS", "LONG", "TREND_UP"}: return "BUY"
    if text in {"DOWN", "BEARISH", "SELL", "SELLERS", "SHORT", "TREND_DOWN"}: return "SELL"
    return "NEUTRAL"


def _num(value: Any, default: float = 0.0) -> float:
    try: return float(value)
    except (TypeError, ValueError): return default


def _atr(bars: list[dict[str, Any]]) -> float:
    if len(bars) < 2: return 0.0
    sample = bars[-(ATR_PERIOD + 1):]
    trs: list[float] = []
    for i, bar in enumerate(sample):
        h, l = _num(bar.get("high")), _num(bar.get("low"))
        if i == 0: trs.append(max(0.0, h - l))
        else:
            p = _num(sample[i - 1].get("close"))
            trs.append(max(h - l, abs(h - p), abs(l - p)))
    return mean(trs[-ATR_PERIOD:]) if trs else 0.0


def _auction_direction(event: str) -> str:
    if "HIGH_SWEEP_REJECTION" in event or "HIGH_FAILED_BREAK_RECLAIM" in event: return "SELL"
    if "LOW_SWEEP_REJECTION" in event or "LOW_FAILED_BREAK_RECLAIM" in event: return "BUY"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event: return "BUY"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event: return "SELL"
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
    if len(unique) > 1: direction, source = "NEUTRAL", "INDEPENDENT_EVIDENCE_CONFLICT"; counter.append("DIRECTIONAL_EVIDENCE_CONFLICT")
    elif len(unique) == 1: direction, source = next(iter(unique)), "E1_E3_E4_CONVERGENCE" if len(votes) >= 2 else "INDEPENDENT_EVIDENCE"
    elif e2_dir != "NEUTRAL": direction, source = e2_dir, "E2_CORROBORATION_ONLY"
    else: direction, source = "NEUTRAL", "INSUFFICIENT_CONVERGENCE"
    if e2_dir != "NEUTRAL":
        supporting.append(f"E2_DIRECTION={e2_dir}")
        if direction != "NEUTRAL" and e2_dir != direction: counter.append("E2_DIRECTION_DISAGREEMENT")
    if len(e2_dirs) > 1: counter.append("E2_INTERNAL_DIRECTION_CONFLICT")
    e3_finding = _text(e3.get("finding", e3.get("structure_state")))
    e3_internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    if "MIXED" in e3_finding or "MIXED" in e3_internal: counter.append("STRUCTURE_MIXED")
    if "FAILED_BOS" in e3_finding: counter.append("FAILED_STRUCTURE_BREAK")
    if direction != "NEUTRAL" and external != "NEUTRAL" and external != direction: counter.append("EXTERNAL_STRUCTURE_COUNTERTREND")
    supporting.append(f"DIRECTION_SOURCE={source}")
    return direction, list(dict.fromkeys(supporting)), list(dict.fromkeys(counter)), source


def _result(state: str, setup: str, direction: str, stage: str, maturity: str, thesis: str, quality: float, confidence: float, exists: bool, ready: bool, supporting: list[str], counter: list[str], missing: list[str], next_required: list[str], invalidation: list[str], candidates: list[dict[str, Any]], rejected: list[str], trace: dict[str, Any]) -> EngineResult:
    quality = max(0.0, min(100.0, quality)); confidence = max(0.0, min(100.0, confidence))
    reasons = list(dict.fromkeys(counter + ([] if stage == "MATURE" else ["SETUP_NOT_MATURE"])))
    observations = [f"candidate_setups={','.join(x['name'] for x in candidates) if candidates else 'NONE'}", f"selected_setup={setup}", f"selected_direction={direction}", f"selected_stage={stage}", f"setup_exists={exists}", f"trade_ready={ready}", f"supporting_evidence={','.join(dict.fromkeys(supporting)) if supporting else 'NONE'}", f"counter_evidence={','.join(counter) if counter else 'NONE'}", f"missing_evidence={','.join(missing) if missing else 'NONE'}", f"next_required_evidence={','.join(next_required) if next_required else 'NONE'}", f"lifecycle={stage}", f"maturity={maturity}"]
    return EngineResult("E6", NAME, False, quality, {"architecture": ARCHITECTURE, "version": VERSION, "question": QUESTION, "role": "SETUP_ANALYST", "reasoning_role": "SETUP_FORMATION_REASONER", "decision_authority": "E9", "trade_decision_authority": False, "state": state, "setup_state": state, "finding": state, "setup": setup, "setup_family": setup, "direction": direction, "stage": stage, "formation_stage": stage, "lifecycle": stage, "maturity": maturity, "thesis": thesis, "setup_exists": exists, "trade_ready": ready, "trade_readiness": "READY" if ready else "NOT_READY", "setup_quality": round(quality, 2), "confidence": round(confidence, 2), "candidate_setups": [x["name"] for x in candidates], "candidate_states": candidates, "rejected_setups": rejected, "supporting_evidence": list(dict.fromkeys(supporting)), "counter_evidence": counter, "missing_evidence": missing, "next_required_evidence": next_required, "invalidation": list(dict.fromkeys(invalidation)), "observations": observations, "reasoning_trace": trace}, tuple(reasons))


def analyze_e6(snapshot: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    """Professional formation diagnosis: distinguish setup existence from maturity and trade readiness."""
    bars = list(snapshot.get("bars") or [])
    if len(bars) < MIN_BARS:
        return _result("NO_SETUP", "NONE", "NEUTRAL", "SEARCHING", "UNRESOLVED", "Insufficient closed-candle history", 0, 100, False, False, [], [f"CLOSED_CANDLES_BELOW_MINIMUM={MIN_BARS}"], ["sufficient_closed_candle_data"], [f"wait for at least {MIN_BARS} valid closed candles"], ["history remains insufficient"], [], [], {"decision":"NO_SETUP","cause":"INSUFFICIENT_HISTORY"})
    try:
        atr = _atr(bars)
        if atr <= 0: raise ValueError
        for b in bars[-MIN_BARS:]:
            for k in ("open", "high", "low", "close"):
                v = float(b[k])
                if v != v: raise ValueError
    except (KeyError, TypeError, ValueError):
        return _result("NO_SETUP", "NONE", "NEUTRAL", "SEARCHING", "UNRESOLVED", "Invalid closed-candle market data", 0, 100, False, False, [], ["INVALID_MARKET_DATA"], ["valid_closed_candle_ohlc"], ["provide valid closed-candle OHLC values"], ["invalid market data"], [], [], {"decision":"NO_SETUP","cause":"INVALID_DATA"})

    e1,e2,e3,e4,e5 = (_payload(upstream,n) for n in ("E1","E2","E3","E4","E5"))
    direction, supporting, counter, direction_source = _direction_evidence(e1,e2,e3,e4)
    event, terminal, pending, age = _auction(e4)
    auction_dir = _auction_direction(event)
    long_space = _num(e5.get("available_space_atr_long")); short_space = _num(e5.get("available_space_atr_short"))
    opportunity = _text(e2.get("finding", e2.get("state","")))
    e3_finding = _text(e3.get("finding", e3.get("structure_state")))
    e3_internal = _text(e3.get("internal_state", e3.get("internal_count_state")))
    e3_lifecycle = _text(e3.get("lifecycle", e3.get("structure_lifecycle","")))
    structure_mixed = "MIXED" in e3_finding or "MIXED" in e3_internal
    response = _norm(e4.get("response_actor"))
    hard_veto = direction == "NEUTRAL" or "DIRECTIONAL_EVIDENCE_CONFLICT" in counter
    candidates: list[dict[str,Any]] = []; rejected: list[str] = []

    if not hard_veto:
        # Liquidity reversal requires an actual directional sweep/rejection/reclaim event.
        if auction_dir == direction and any(x in event for x in ("SWEEP_REJECTION","FAILED_BREAK_RECLAIM")):
            strength = 58 + (12 if response == direction else 0) + (10 if terminal else 0) - (8 if structure_mixed else 0)
            missing = [] if terminal else ["terminal_auction_confirmation"]
            candidates.append({"name":"LIQUIDITY_REVERSAL","direction":direction,"formation_stage":"MATURE" if terminal else "VALIDATING","strength":max(0,min(100,strength)),"evidence":[f"E4_EVENT={event}",f"E4_RESPONSE={response}",f"EVENT_AGE_BARS={age}"],"missing":missing,"invalidation":["auction_response_failure","loss_of_structural_invalidation_level"]})
        # Breakout/retest and continuation are hypotheses, never declared solely from labels.
        if direction == _norm(e1.get("trend_state",e1.get("finding"))) and not structure_mixed:
            if "BREAK" in _text(e3.get("bos",e3.get("break_of_structure",""))) or "BREAK" in event:
                stage = "MATURE" if terminal else "VALIDATING"
                candidates.append({"name":"BREAKOUT_RETEST" if "RETEST" in _text(e3) else "BREAKOUT","direction":direction,"formation_stage":stage,"strength":62 if terminal else 48,"evidence":["DIRECTIONAL_TREND_ALIGNMENT",f"STRUCTURE_EVENT={_text(e3.get('bos',e3.get('break_of_structure','')))}",f"AUCTION_EVENT={event or 'NONE'}"],"missing":[] if terminal else ["closed_candle_follow_through","acceptance_after_break"],"invalidation":["breakout_failure","reclaim_inside_prior_structure"]})
            elif "PULLBACK" in _text(e3) or "HL" in _text(e3.get("sequence","")) or "LH" in _text(e3.get("sequence","")):
                candidates.append({"name":"TREND_PULLBACK","direction":direction,"formation_stage":"FORMING","strength":42,"evidence":["TREND_DIRECTION_ALIGNED",f"STRUCTURE_LIFECYCLE={e3_lifecycle or 'UNKNOWN'}"],"missing":["impulse_then_pullback_sequence","continuation_trigger"],"invalidation":["loss_of_protected_structure"]})

    # Location is a maturity/risk constraint, not an excuse to erase a legitimate formation diagnosis.
    space = long_space if direction == "BUY" else short_space
    if direction != "NEUTRAL":
        supporting.append(f"STRUCTURAL_SPACE_{direction}={space:.3f}ATR")
        if space < MIN_SPACE_ATR:
            counter.append("STRUCTURAL_SPACE_CONSTRAINED")
    if pending and not terminal: counter.append("LIQUIDITY_EVENT_PENDING")
    if any(x in opportunity for x in ("UNRESOLVED","UNPROVEN")): counter.append("OPPORTUNITY_MATURITY_UNPROVEN")
    if structure_mixed: counter.append("STRUCTURE_MIXED")
    counter = list(dict.fromkeys(counter)); supporting = list(dict.fromkeys(supporting))

    if not candidates:
        state, setup, stage, exists = "FORMING", "NONE", "FORMING", False
        thesis = "No defensible setup hypothesis: evidence is insufficient or direction is conflicted."
        missing = ["directional_convergence","causal_setup_sequence"]
        next_required = ["closed-candle evidence that resolves direction and establishes a causal setup sequence"]
        quality = 20; confidence = 82
    else:
        candidates.sort(key=lambda x:(x["strength"], -len(x["missing"])), reverse=True)
        best = candidates[0]
        # Do not call a setup mature merely because an upstream opportunity is mature.
        setup = best["name"]; stage = best["formation_stage"]; exists = True
        maturity = "MATURE" if stage == "MATURE" else ("VALIDATING" if stage == "VALIDATING" else "FORMING")
        state = stage
        missing = list(best["missing"])
        if space < MIN_SPACE_ATR: missing.append("adequate_structural_space")
        if not terminal and event: missing.append("terminal_auction_confirmation")
        if any(x in opportunity for x in ("UNRESOLVED","UNPROVEN")): missing.append("opportunity_acceptance_follow_through")
        missing = list(dict.fromkeys(missing))
        next_required = [f"evidence required to advance {setup}: {x}" for x in missing]
        thesis = f"{direction} {setup} is {stage.lower()}: causal evidence is present, but maturity is gated by the missing evidence rather than hidden behind a binary no-setup decision."
        quality = best["strength"]; confidence = min(95, 58 + len(best["evidence"])*7 - len(missing)*5)
        if len(candidates) > 1 and candidates[0]["strength"] - candidates[1]["strength"] < 8:
            counter.append("HYPOTHESES_TOO_CLOSE_TO_FORCE_SELECTION"); rejected.append("SELECTION_DEFERRED_DUE_TO_HYPOTHESIS_AMBIGUITY")
            state, setup, stage, exists = "FORMING", "AMBIGUOUS", "FORMING", True
            thesis = "Multiple setup hypotheses remain too close to justify false precision; wait for discriminating evidence."
    maturity = "MATURE" if stage == "MATURE" else ("VALIDATING" if stage == "VALIDATING" else "FORMING")
    ready = exists and stage == "MATURE" and direction != "NEUTRAL" and space >= MIN_SPACE_ATR and not pending and not any(x in opportunity for x in ("UNRESOLVED","UNPROVEN"))
    invalidation = [x for c in candidates for x in c.get("invalidation",[])][:6]
    trace = {"direction_source":direction_source,"auction":{"event":event,"terminal":terminal,"pending":pending,"age_bars":age,"direction":auction_dir},"location":{"long_space_atr":long_space,"short_space_atr":short_space,"selected_space_atr":space},"hypothesis_count":len(candidates),"selection_rule":"causal_evidence_then_strength_then_missing_evidence; defer if top hypotheses are too close","hard_direction_veto":hard_veto,"professional_rule":"maturity blockers do not erase a diagnosable formation; trade authority remains E9"}
    return _result(state, setup, direction, stage, maturity, thesis, quality, confidence, exists, ready, supporting, counter, missing, next_required, invalidation, candidates, rejected, trace)
