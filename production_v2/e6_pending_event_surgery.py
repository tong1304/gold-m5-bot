from __future__ import annotations

from typing import Any

from .contracts import EngineResult

VERSION = "E6_PENDING_EVENT_SURGERY_V3"
PENDING_AUCTION_STATES = {"PENDING", "DEVELOPING", "FORMING", "AWAITING_CONFIRMATION", "CONFIRMATION_PENDING"}
WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
DIRECTIONS = {"BUY", "SELL"}
MEANINGFUL_EVENTS = ("FAILED_BREAK_RECLAIM", "HIGH_SWEEP_REJECTION", "LOW_SWEEP_REJECTION", "HIGH_REJECTION", "LOW_REJECTION", "HIGH_ACCEPTANCE", "LOW_ACCEPTANCE", "BREAK", "RECLAIM", "LIQUIDITY_INTERACTION", "ACCEPTANCE", "REJECTION", "SWEEP")


def _text(value: Any) -> str: return str(value or "").upper().strip()

def _direction(value: Any) -> str:
    text = _text(value)
    if text in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "BUYER", "TREND_UP", "BUY_CONTROLLED"} or text.startswith(("BUY ", "BUY_", "BUY:")): return "BUY"
    if text in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "SELLER", "TREND_DOWN", "SELL_CONTROLLED"} or text.startswith(("SELL ", "SELL_", "SELL:")): return "SELL"
    return "NEUTRAL"

def _out(result: Any) -> dict[str, Any]:
    value = getattr(result, "output", {})
    return dict(value) if isinstance(value, dict) else {}

def _payload(upstream: dict[str, EngineResult], key: str) -> dict[str, Any]:
    result = upstream.get(key)
    return _out(result) if result else {}

def _is_invalidated(e3: dict[str, Any]) -> bool:
    return bool(e3.get("structure_invalidated") is True or e3.get("active_invalidation") is True or _text(e3.get("lifecycle")) == "INVALIDATED" or "STRUCTURE_INVALIDATED" in _text(e3.get("finding")) or "STRUCTURE_INVALIDATED" in _text(e3.get("invalidation")))

def _is_existing_watch(e6: dict[str, Any]) -> bool:
    setup = _text(e6.get("setup") or e6.get("setup_family")); candidate = _text(e6.get("candidate_type"))
    return (setup in WATCH_SETUPS or candidate == "OPPORTUNITY_CANDIDATE" or e6.get("watch_only") is True) and e6.get("trade_ready") is not True

def _is_no_setup(e6: dict[str, Any]) -> bool:
    setup = _text(e6.get("setup") or e6.get("setup_family")); finding = _text(e6.get("finding")); reasons = {_text(x) for x in (e6.get("reason_codes") or e6.get("reasons") or [])}
    return setup in {"", "NO_SETUP", "UNKNOWN", "NONE"} and ("NO_CAUSAL_OPPORTUNITY" in reasons or "NO SURVIVING CAUSAL OPPORTUNITY THESIS" in finding or "NO CAUSAL SETUP HYPOTHESIS" in finding)

def _pending_event(e4: dict[str, Any]) -> bool:
    event = _text(e4.get("event") or e4.get("finding")); state = _text(e4.get("auction_state") or e4.get("auction_phase") or e4.get("state"))
    return state in PENDING_AUCTION_STATES and any(token in event for token in MEANINGFUL_EVENTS)

def _failed_break_pending(e4: dict[str, Any]) -> bool:
    event = _text(e4.get("event") or e4.get("finding")); state = _text(e4.get("auction_state") or e4.get("auction_phase") or e4.get("state"))
    return "FAILED_BREAK_RECLAIM" in event and state in PENDING_AUCTION_STATES

def _space(e5: dict[str, Any], direction: str) -> float:
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    try:
        value = float(e5.get(key) or 0.0); return value if value == value else 0.0
    except (TypeError, ValueError): return 0.0

def _event_direction(e4: dict[str, Any]) -> str:
    event = _text(e4.get("event") or e4.get("finding"))
    # Event semantics outrank E4's generic direction field because for sweep
    # events that field may describe the sweep leg rather than the response.
    if "HIGH_SWEEP_REJECTION" in event or "HIGH_REJECTION" in event: return "SELL"
    if "LOW_SWEEP_REJECTION" in event or "LOW_REJECTION" in event: return "BUY"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event: return "BUY"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event: return "SELL"
    if "FAILED_BREAK_RECLAIM" in event:
        response = _direction(e4.get("response_actor"))
        if response != "NEUTRAL": return response
    direct = _direction(e4.get("directional_implication"))
    if direct != "NEUTRAL": return direct
    direct = _direction(e4.get("direction"))
    if direct != "NEUTRAL": return direct
    return _direction(e4.get("response_actor"))

def _generic_candidate(upstream: dict[str, EngineResult]) -> dict[str, Any] | None:
    e1, e2, e3, e4, e5 = (_payload(upstream, key) for key in ("E1", "E2", "E3", "E4", "E5"))
    if _is_invalidated(e3) or not _pending_event(e4): return None
    pressure = _direction(e1.get("directional_pressure") or e1.get("pressure")); external = _direction(e3.get("external_state") or e3.get("structure_direction") or e3.get("direction")); internal = _direction(e3.get("internal_state")); e2_direction = _direction(e2.get("direction") or e2.get("opportunity_direction")); event_direction = _event_direction(e4)
    direction = event_direction if event_direction in DIRECTIONS else e2_direction if e2_direction in DIRECTIONS else external if external in DIRECTIONS else pressure if pressure in DIRECTIONS else "NEUTRAL"
    if direction not in DIRECTIONS: return None
    counter: list[str] = ["E4_PENDING_AUCTION_EVENT"]
    for label, value in (("E1", pressure), ("E2", e2_direction), ("E3_EXTERNAL", external), ("E3_INTERNAL", internal)):
        if value in DIRECTIONS and value != direction: counter.append(f"{label}_COUNTERFLOW")
    finding5 = _text(e5.get("finding")); preferred = _text(e5.get("preferred_location")); preferred_direction = "BUY" if preferred == "LONG" else "SELL" if preferred == "SHORT" else "NEUTRAL"; space = _space(e5, direction)
    continuation_risk = "CONTINUATION_RISK" in finding5 or ("ACCEPTED" in finding5 and "REVERSAL" in finding5)
    support = ["E4_DIRECTIONAL_EVENT_EVIDENCE"]
    if pressure == direction: support.append("E1_DIRECTIONAL_CORE")
    if external == direction: support.append("E3_EXTERNAL_STRUCTURE_SUPPORT")
    if e2_direction == direction: support.append("E2_DIRECTIONAL_ANCHOR")
    if space > 0: support.append("E5_SPACE_EVIDENCE")
    missing = ["E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"]
    maturity = _text(e2.get("opportunity_maturity") or e2.get("state") or e2.get("opportunity_state"))
    if maturity in {"DEVELOPING", "EMERGING", "PENDING", "UNRESOLVED", "AMBIGUOUS", "UNPROVEN"}: missing.insert(0, "E2_OPPORTUNITY_CONFIRMATION")
    if internal == "MIXED" or (internal in DIRECTIONS and internal != direction): missing.append("E3_INTERNAL_STRUCTURE_ALIGNMENT")
    if preferred_direction in DIRECTIONS and preferred_direction != direction:
        counter.append("E5_OPPOSITE_DIRECTIONAL_LOCATION"); missing.append("E5_DIRECTIONAL_LOCATION_CONFLICT")
    if continuation_risk: counter.append("E5_CONTINUATION_RISK_AGAINST_REVERSAL")
    if space < 0.75: missing.append("STRUCTURAL_SPACE_INSUFFICIENT")
    return {"direction": direction, "family": "LIQUIDITY_RESPONSE", "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""), "space": round(space, 4), "support": list(dict.fromkeys(support)), "counter": list(dict.fromkeys(counter)), "missing": list(dict.fromkeys(missing)), "direction_source": "E4_EVENT" if event_direction in DIRECTIONS else "UPSTREAM_FALLBACK"}

def _candidate(upstream: dict[str, EngineResult]) -> dict[str, Any] | None:
    return _generic_candidate(upstream)

def _watch(original: EngineResult, candidate: dict[str, Any]) -> EngineResult:
    out = dict(original.output or {}); direction = candidate["direction"]; missing = list(dict.fromkeys(candidate["missing"])); contested = bool(candidate.get("counter")) or "STRUCTURAL_SPACE_INSUFFICIENT" in missing or "E5_DIRECTIONAL_LOCATION_CONFLICT" in missing; event_id = candidate["event_id"]
    out.update({"architecture": VERSION, "state": "CONTESTED_WATCH" if contested else "FORMING_WATCH", "setup_state": "CONTESTED_WATCH" if contested else "FORMING_WATCH", "opportunity_stage": "CONTESTED_WATCH", "setup": "OPPORTUNITY_WATCH", "setup_family": candidate["family"], "candidate_type": "OPPORTUNITY_CANDIDATE", "candidate_setup": "OPPORTUNITY_WATCH", "direction": direction, "direction_thesis": direction, "thesis_direction": direction, "thesis_status": "CONTESTED" if contested else "FORMING", "setup_exists": False, "watch_only": True, "trade_ready": False, "trade_permission": False, "gate_passed": False, "e6_thesis_proven": False, "e6_causal_gate": "WATCH_ONLY", "finding": f"{direction} opportunity is {'contested' if contested else 'forming'} watch; pending E4 auction event is not yet confirmed and no trade setup is proven.", "thesis": f"{direction} opportunity is watchable from E1-E5 closed-candle evidence; E4 resolution and E7 confirmation remain mandatory.", "supporting_evidence": candidate["support"], "counter_evidence": candidate["counter"], "hard_conflicts": [], "missing_proof": missing, "missing_evidence": missing, "next_required_event": "NEXT_CLOSED_M5_CANDLE", "wait_for": ",".join(missing), "candidate_identity": f"OPPORTUNITY_WATCH:{direction}:LIQUIDITY_RESPONSE:{event_id}", "opportunity_id": f"{direction}|OPPORTUNITY_WATCH|{event_id}", "event_id": event_id, "available_space_atr": candidate["space"], "reason_codes": missing, "reasons": missing, "execution_authority": "E9", "invalidated": False, "upstream_evidence_lost": False, "causal_evidence_lost": False, "lifecycle_state": "OPPORTUNITY_WATCH", "pending_event_authority": VERSION, "watch_direction_source": candidate.get("direction_source", "UPSTREAM")})
    return EngineResult("E6", "Setup Brain", False, 0.0, out, tuple(missing))

def _align_existing_watch(result: EngineResult, upstream: dict[str, EngineResult]) -> EngineResult:
    out = _out(result)
    if not _is_existing_watch(out): return result
    direction = _direction(out.get("direction") or out.get("direction_thesis") or out.get("thesis_direction"))
    if direction not in DIRECTIONS: return result
    e5 = _payload(upstream, "E5"); preferred = _text(e5.get("preferred_location")); preferred_direction = "BUY" if preferred == "LONG" else "SELL" if preferred == "SHORT" else "NEUTRAL"
    if preferred_direction not in DIRECTIONS or preferred_direction == direction: return result
    support = [x for x in (out.get("supporting_evidence") or []) if _text(x) != "E5_LOCATION_VALUE_SUPPORT"]; counter = list(out.get("counter_evidence") or []); missing = list(out.get("missing_proof") or out.get("reason_codes") or [])
    if "E5_OPPOSITE_DIRECTIONAL_LOCATION" not in counter: counter.append("E5_OPPOSITE_DIRECTIONAL_LOCATION")
    if "E5_DIRECTIONAL_LOCATION_CONFLICT" not in missing: missing.append("E5_DIRECTIONAL_LOCATION_CONFLICT")
    out["supporting_evidence"] = support; out["counter_evidence"] = list(dict.fromkeys(counter)); out["missing_proof"] = list(dict.fromkeys(missing)); out["missing_evidence"] = list(dict.fromkeys(missing)); out["reason_codes"] = list(dict.fromkeys(missing)); out["reasons"] = list(dict.fromkeys(missing)); out["e5_directional_location"] = preferred_direction
    return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, out, tuple(out["reason_codes"]))

def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_E6_PENDING_EVENT_SURGERY_INSTALLED", False): return
    original = pipeline_module.analyze_e6
    def patched_analyze_e6(market_data: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
        result = original(market_data, upstream)
        if not isinstance(result, EngineResult): return result
        result = _align_existing_watch(result, upstream); current = _out(result)
        if _is_existing_watch(current) or not _is_no_setup(current): return result
        candidate = _candidate(upstream)
        if candidate is None: return result
        print(f"[PRODUCTION V2] E6_PENDING_EVENT_SURGERY version={VERSION} action=WATCH direction={candidate['direction']} event_id={candidate['event_id']} source={candidate.get('direction_source')}", flush=True)
        return _watch(result, candidate)
    pipeline_module.analyze_e6 = patched_analyze_e6
    pipeline_module._E6_PENDING_EVENT_SURGERY_INSTALLED = True
    print(f"[PRODUCTION V2] E6_PENDING_EVENT_SURGERY_BINDING version={VERSION} module={pipeline_module.__name__} analyze={pipeline_module.analyze_e6.__module__}.{pipeline_module.analyze_e6.__name__}", flush=True)
