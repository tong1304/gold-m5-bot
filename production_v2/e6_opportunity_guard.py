from __future__ import annotations
from typing import Any
from .contracts import EngineResult


def _text(v: Any) -> str:
    return str(v or "").upper().strip()


def _direction(*values: Any) -> str:
    for value in values:
        t = _text(value)
        if t in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "BUYER", "BUY_CONTROLLED", "TREND_UP"}: return "BUY"
        if t in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "SELLER", "SELL_CONTROLLED", "TREND_DOWN"}: return "SELL"
    return "NEUTRAL"


def _out(r: Any) -> dict[str, Any]: return dict(getattr(r, "output", {}) or {})
def _payload(upstream: dict[str, EngineResult], key: str) -> dict[str, Any]:
    r = upstream.get(key); return _out(r) if r else {}


def _event_direction(e4: dict[str, Any]) -> str:
    d = _direction(e4.get("direction"))
    if d != "NEUTRAL": return d
    actor = _direction(e4.get("response_actor")); event = _text(e4.get("event", e4.get("finding")))
    if actor != "NEUTRAL" and "FAILED_BREAK_RECLAIM" in event: return actor
    if "HIGH_SWEEP_REJECTION" in event or "HIGH_REJECTION" in event: return "SELL"
    if "LOW_SWEEP_REJECTION" in event or "LOW_REJECTION" in event: return "BUY"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event: return "BUY"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event: return "SELL"
    if "HIGH_LIQUIDITY_INTERACTION" in event or "LOW_LIQUIDITY_INTERACTION" in event: return _direction(e4.get("liquidity_taker"))
    return "NEUTRAL"


def _e2_unresolved(e2: dict[str, Any]) -> bool:
    text = _text(e2.get("finding", e2.get("state"))); state = _text(e2.get("opportunity_state", e2.get("opportunity_decision"))); maturity = _text(e2.get("opportunity_maturity"))
    return ("OPPORTUNITY IS EMERGING" in text or "OPPORTUNITY IS DEVELOPING" in text or "UNPROVEN" in text or "NOT PROVEN" in text or text in {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS", "WAIT", "EMERGING", "PENDING", "DEVELOPING"} or state in {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS", "WAIT", "EMERGING", "PENDING", "DEVELOPING"} or maturity in {"UNPROVEN", "EMERGING", "DEVELOPING"})


def _e2_direction(e2: dict[str, Any]) -> str:
    for value in (e2.get("direction"), e2.get("opportunity_direction"), e2.get("auction_direction")):
        d = _direction(value)
        if d != "NEUTRAL": return d
    finding = _text(e2.get("finding", e2.get("state")))
    if "DOWN OPPORTUNITY" in finding or "SELL OPPORTUNITY" in finding: return "SELL"
    if "UP OPPORTUNITY" in finding or "BUY OPPORTUNITY" in finding: return "BUY"
    return "NEUTRAL"


def _fallback_opportunity(upstream: dict[str, EngineResult]) -> dict[str, Any] | None:
    e1, e2, e3, e4, e5 = (_payload(upstream, k) for k in ("E1", "E2", "E3", "E4", "E5"))
    pressure = _direction(e1.get("directional_pressure", e1.get("pressure")))
    external = _direction(e3.get("external_state", e3.get("direction"))); internal = _direction(e3.get("internal_state"))
    auction = _text(e4.get("auction_state", e4.get("state"))); event = _text(e4.get("event", e4.get("finding")))
    event_direction = _event_direction(e4)
    finding = _text(e5.get("finding")); value = _text(e5.get("value_state")); location = _text(e5.get("structural_location"))
    favorable = "FAVORABLE_LOCATION" in finding or location in {"AT_SUPPORT", "AT_RESISTANCE"} or value in {"DISCOUNT", "PREMIUM", "EQUILIBRIUM"}
    causal_event = any(x in event for x in ("ACCEPTANCE", "REJECTION", "SWEEP", "FAILED_BREAK", "BREAK", "RECLAIM", "LIQUIDITY_INTERACTION"))
    if not favorable or not causal_event or event_direction == "NEUTRAL": return None

    # A confirmed opposite E2 direction is a hard conflict. Pending/E2-neutral
    # can remain a watch, but confirmed disagreement must not be rescued.
    e2_direction = _e2_direction(e2)
    e2_confirmed = not _e2_unresolved(e2) and e2_direction in {"BUY", "SELL"}
    if e2_confirmed and e2_direction != event_direction: return None

    pending = auction in {"PENDING", "DEVELOPING", "FORMING"}; unresolved = _e2_unresolved(e2)
    counterflow = external != "NEUTRAL" and external != event_direction; pressure_counterflow = pressure != "NEUTRAL" and pressure != event_direction
    if counterflow and not unresolved and not pending: return None
    if pressure_counterflow and not unresolved and not pending: return None
    if internal in {"BUY", "SELL"} and internal != event_direction and not (unresolved or pending): return None
    if _text(e3.get("lifecycle")) == "INVALIDATED" or e3.get("structure_invalidated") is True or e3.get("active_invalidation") is True: return None

    space_key = "available_space_atr_long" if event_direction == "BUY" else "available_space_atr_short"
    try: space = float(e5.get(space_key) or 0.0)
    except (TypeError, ValueError): space = 0.0
    family = "AUCTION_ACCEPTANCE_CONTINUATION" if "ACCEPTANCE" in event else "LIQUIDITY_RESPONSE"
    missing = ["E7_CONFIRMATION"]
    if unresolved: missing.insert(0, "E2_OPPORTUNITY_CONFIRMATION")
    if pending or "CANDIDATE" in event: missing.insert(1 if missing and missing[0] == "E2_OPPORTUNITY_CONFIRMATION" else 0, "E4_AUCTION_FOLLOW_THROUGH")
    if counterflow: missing.append("E3_EXTERNAL_STRUCTURE_ALIGNMENT")
    if internal == "NEUTRAL" or internal != event_direction: missing.append("E3_INTERNAL_STRUCTURE_ALIGNMENT")
    if space < 0.75: missing.append("STRUCTURAL_SPACE_INSUFFICIENT")
    counter = []
    if counterflow: counter.append("E3_EXTERNAL_COUNTERFLOW")
    if pressure_counterflow: counter.append("E1_COUNTER_EVIDENCE")
    return {"direction": event_direction, "family": family, "space": round(space, 4), "missing": list(dict.fromkeys(missing)), "support": ["E4_DIRECTIONAL_AUCTION_EVIDENCE", "E5_LOCATION_VALUE_SUPPORT"], "counter": list(dict.fromkeys(counter)), "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""), "contested": bool(counterflow or pressure_counterflow)}


def _watch(original: EngineResult, candidate: dict[str, Any]) -> EngineResult:
    out = dict(original.output or {}); direction = candidate["direction"]; missing = candidate["missing"]; contested = bool(candidate.get("contested")); stage = "CONTESTED" if contested else "FORMING"
    out.update({"state":"CONTESTED_WATCH" if contested else "FORMING","setup_state":"CONTESTED_WATCH" if contested else "FORMING","opportunity_stage":stage,"setup":"OPPORTUNITY_WATCH","setup_family":candidate["family"],"candidate_type":"OPPORTUNITY_CANDIDATE","direction":direction,"direction_thesis":direction,"thesis_direction":direction,"thesis_status":stage,"trade_ready":False,"trade_permission":False,"gate_passed":False,"watch_only":True,"finding":f"{direction} opportunity is {stage.lower()}; causal event exists but trade setup is not yet proven.","thesis":f"{direction} causal opportunity is watchable; unresolved evidence and E4/E7 proof remain pending.","supporting_evidence":candidate["support"],"counter_evidence":candidate["counter"],"hard_conflicts":[],"missing_proof":missing,"next_required_event":"NEXT_CLOSED_M5_CANDLE","wait_for":",".join(missing),"candidate_identity":f"OPPORTUNITY_WATCH:{direction}:{candidate['family']}","opportunity_id":f"{direction}|OPPORTUNITY_WATCH","event_id":candidate["event_id"],"available_space_atr":candidate["space"],"reason_codes":missing,"reasons":missing,"execution_authority":"E9"})
    return EngineResult(original.engine_id, original.name, False, original.score, out, tuple(missing))


def _normalize_existing_watch(result: EngineResult) -> EngineResult:
    out = _out(result); setup = _text(out.get("setup") or out.get("setup_type") or out.get("setup_family")); direction = _direction(out.get("direction"), out.get("thesis_direction"), out.get("direction_thesis"))
    if setup not in {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"} or direction not in {"BUY","SELL"} or out.get("watch_only") is not True or out.get("trade_ready") is True: return result
    finding = _text(out.get("finding"))
    if "NO CAUSAL SETUP HYPOTHESIS" not in finding and "NO SURVIVING CAUSAL OPPORTUNITY THESIS" not in finding: return result
    out.update({"setup":"OPPORTUNITY_WATCH","candidate_type":"OPPORTUNITY_CANDIDATE","direction":direction,"direction_thesis":direction,"thesis_direction":direction,"watch_only":True,"trade_ready":False,"gate_passed":False,"finding":f"{direction} opportunity is forming; causal event exists but trade setup is not yet proven.","thesis":out.get("thesis") or f"{direction} causal opportunity is watchable; required proof remains pending."})
    return EngineResult(result.engine_id,result.name,False,result.score,out,result.reason_codes)


def _should_rescue_watch(result: EngineResult) -> bool:
    out = _out(result); setup = _text(out.get("setup"))
    if out.get("trade_ready") is True or out.get("gate_passed") is True: return False
    if setup in {"OPPORTUNITY_WATCH","OPPORTUNITY_CANDIDATE","OPPORTUNITY_THESIS"}:
        finding = _text(out.get("finding")); reasons = {_text(x) for x in (out.get("reason_codes") or out.get("reasons") or [])}
        return "NO CAUSAL SETUP HYPOTHESIS" in finding and reasons.issubset({"E2_OPPORTUNITY_CONFIRMATION","E4_AUCTION_FOLLOW_THROUGH","E7_CONFIRMATION","STRUCTURAL_SPACE_INSUFFICIENT","E3_EXTERNAL_STRUCTURE_ALIGNMENT","E3_INTERNAL_STRUCTURE_ALIGNMENT","E3_INTERNAL_EVIDENCE_UNRESOLVED"})
    finding = _text(out.get("finding")); reasons = {_text(x) for x in (out.get("reason_codes") or out.get("reasons") or [])}
    if "NO CAUSAL SETUP HYPOTHESIS" in finding or "NO SURVIVING CAUSAL OPPORTUNITY THESIS" in finding: return True
    if "NO_CAUSAL_OPPORTUNITY" in reasons and setup in {"","NO_SETUP","UNKNOWN"}: return True
    stage = _text(out.get("opportunity_stage")); state = _text(out.get("state"))
    return setup in {"","NO_SETUP","UNKNOWN"} or stage in {"","ABSENT","UNKNOWN"} or state in {"","NO_SETUP","UNKNOWN"}


def install(e6_module) -> None:
    if getattr(e6_module, "_E6_OPPORTUNITY_GUARD_INSTALLED", False): return
    original = e6_module.analyze_e6
    def guarded(market_data, upstream):
        result = original(market_data, upstream)
        if not isinstance(result, EngineResult): return result
        normalized = _normalize_existing_watch(result)
        if normalized is not result: return normalized
        if not _should_rescue_watch(result): return result
        candidate = _fallback_opportunity(upstream)
        if candidate is None: return result
        return _watch(result, candidate)
    e6_module.analyze_e6 = guarded
    e6_module._E6_OPPORTUNITY_GUARD_INSTALLED = True
