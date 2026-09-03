from __future__ import annotations

from typing import Any

from .contracts import EngineResult


def _text(v: Any) -> str:
    return str(v or "").upper().strip()


def _direction(v: Any) -> str:
    t = _text(v)
    if t in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"}:
        return "BUY"
    if t in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"}:
        return "SELL"
    return "NEUTRAL"


def _out(r: Any) -> dict[str, Any]:
    return dict(getattr(r, "output", {}) or {})


def _payload(upstream: dict[str, EngineResult], key: str) -> dict[str, Any]:
    r = upstream.get(key)
    return _out(r) if r else {}


def _event_direction(e4: dict[str, Any]) -> str:
    d = _direction(e4.get("direction"))
    if d != "NEUTRAL":
        return d
    actor = _direction(e4.get("response_actor"))
    event = _text(e4.get("event", e4.get("finding")))
    if actor != "NEUTRAL" and "FAILED_BREAK_RECLAIM" in event:
        return actor
    if "HIGH_SWEEP_REJECTION" in event or "HIGH_REJECTION" in event:
        return "SELL"
    if "LOW_SWEEP_REJECTION" in event or "LOW_REJECTION" in event:
        return "BUY"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
        return "BUY"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
        return "SELL"
    if "HIGH_LIQUIDITY_INTERACTION" in event or "LOW_LIQUIDITY_INTERACTION" in event:
        return _direction(e4.get("liquidity_taker"))
    return "NEUTRAL"


def _e2_unresolved(e2: dict[str, Any]) -> bool:
    text = _text(e2.get("finding", e2.get("state")))
    state = _text(e2.get("opportunity_state", e2.get("opportunity_decision")))
    return (
        "OPPORTUNITY IS EMERGING" in text
        or "OPPORTUNITY IS DEVELOPING" in text
        or text in {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS", "WAIT", "EMERGING", "PENDING", "DEVELOPING"}
        or state in {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS", "WAIT", "EMERGING", "PENDING", "DEVELOPING"}
    )


def _fallback_opportunity(upstream: dict[str, EngineResult]) -> dict[str, Any] | None:
    e1, e2, e3, e4, e5 = (_payload(upstream, k) for k in ("E1", "E2", "E3", "E4", "E5"))
    pressure = _direction(e1.get("directional_pressure", e1.get("pressure")))
    external = _direction(e3.get("external_state", e3.get("direction")))
    internal = _direction(e3.get("internal_state"))
    auction = _text(e4.get("auction_state", e4.get("state")))
    event = _text(e4.get("event", e4.get("finding")))
    event_direction = _event_direction(e4)
    finding = _text(e5.get("finding"))
    value = _text(e5.get("value_state"))
    location = _text(e5.get("structural_location"))
    favorable = "FAVORABLE_LOCATION" in finding or location in {"AT_SUPPORT", "AT_RESISTANCE"} or value in {"DISCOUNT", "PREMIUM", "EQUILIBRIUM"}
    causal_event = any(x in event for x in ("ACCEPTANCE", "REJECTION", "SWEEP", "FAILED_BREAK", "BREAK", "RECLAIM", "LIQUIDITY_INTERACTION"))
    if not favorable or not causal_event or event_direction == "NEUTRAL":
        return None

    # A pending acceptance that runs against the existing external structure is
    # a legitimate transition watch, not a confirmed reversal/continuation.
    # It is allowed only while E2 is unresolved and E4 has not been terminally
    # confirmed. This preserves the opportunity without promoting a trade.
    pending_counterflow_acceptance = (
        external != "NEUTRAL"
        and external != event_direction
        and _e2_unresolved(e2)
        and auction in {"PENDING", "DEVELOPING", "FORMING"}
        and "ACCEPTANCE" in event
    )
    counter: list[str] = []
    missing_structure: list[str] = []
    if external != "NEUTRAL" and external != event_direction:
        if not pending_counterflow_acceptance:
            return None
        counter.append("E3_EXTERNAL_COUNTERFLOW")
        missing_structure.append("E3_EXTERNAL_STRUCTURE_ALIGNMENT")
    if pressure != "NEUTRAL" and pressure != event_direction and not _e2_unresolved(e2):
        return None
    # A mixed/unfinished internal structure is not a hard conflict. It is a
    # missing proof item for the developing opportunity.
    if internal != "NEUTRAL" and internal != event_direction and external != "NEUTRAL":
        return None
    if _text(e3.get("lifecycle")) == "INVALIDATED" or e3.get("structure_invalidated") is True or e3.get("active_invalidation") is True:
        return None

    space_key = "available_space_atr_long" if event_direction == "BUY" else "available_space_atr_short"
    try:
        space = float(e5.get(space_key) or 0.0)
    except (TypeError, ValueError):
        space = 0.0
    family = "AUCTION_ACCEPTANCE_CONTINUATION" if "ACCEPTANCE" in event else "LIQUIDITY_RESPONSE"
    missing = ["E7_CONFIRMATION"]
    if _e2_unresolved(e2):
        missing.insert(0, "E2_OPPORTUNITY_CONFIRMATION")
    if auction in {"PENDING", "DEVELOPING", "FORMING"} or "CANDIDATE" in event:
        missing.insert(1 if missing and missing[0] == "E2_OPPORTUNITY_CONFIRMATION" else 0, "E4_AUCTION_FOLLOW_THROUGH")
    if space < 0.75:
        # Space is an execution/economics constraint, not an opportunity veto.
        missing.append("STRUCTURAL_SPACE_INSUFFICIENT")
    return {
        "direction": event_direction,
        "family": family,
        "space": round(space, 4),
        "missing": list(dict.fromkeys(missing)),
        "support": ["E4_DIRECTIONAL_AUCTION_EVIDENCE", "E5_LOCATION_VALUE_SUPPORT"],
        "counter": list(dict.fromkeys(counter + (["E1_COUNTER_EVIDENCE"] if pressure not in {"NEUTRAL", event_direction} else []))),
        "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""),
    }


def _watch(original: EngineResult, candidate: dict[str, Any]) -> EngineResult:
    out = dict(original.output or {})
    direction = candidate["direction"]
    missing = candidate["missing"]
    out.update({
        "state": "FORMING",
        "setup_state": "FORMING",
        "opportunity_stage": "FORMING",
        "setup": "OPPORTUNITY_WATCH",
        "setup_family": candidate["family"],
        "candidate_type": "OPPORTUNITY_CANDIDATE",
        "direction": direction,
        "direction_thesis": direction,
        "thesis_direction": direction,
        "thesis_status": "FORMING",
        "trade_ready": False,
        "trade_permission": False,
        "gate_passed": False,
        "watch_only": True,
        "finding": f"{direction} opportunity is forming; causal evidence exists but trade setup is not yet proven.",
        "thesis": f"{direction} causal opportunity is watchable; E7 confirmation and E8 economics remain pending.",
        "supporting_evidence": candidate["support"],
        "counter_evidence": candidate["counter"],
        "hard_conflicts": [],
        "missing_proof": missing,
        "next_required_event": "NEXT_CLOSED_M5_CANDLE",
        "wait_for": ",".join(missing),
        "candidate_identity": f"OPPORTUNITY_WATCH:{direction}:{candidate['family']}",
        "opportunity_id": f"{direction}|OPPORTUNITY_WATCH",
        "event_id": candidate["event_id"],
        "available_space_atr": candidate["space"],
        "reason_codes": missing,
        "reasons": missing,
        "execution_authority": "E9",
    })
    return EngineResult(original.engine_id, original.name, False, original.score, out, tuple(missing))


def _should_rescue_watch(result: EngineResult) -> bool:
    out = _out(result)
    setup = _text(out.get("setup"))
    stage = _text(out.get("opportunity_stage"))
    state = _text(out.get("state"))
    if setup in {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}:
        return False
    if out.get("trade_ready") is True or out.get("gate_passed") is True:
        return False
    # Some E6 paths already discovered the causal opportunity but leave the
    # public setup label unresolved because E7/structural proof is incomplete.
    # The guard may preserve only a watch; it never upgrades to a trade thesis.
    return setup in {"", "NO_SETUP", "UNKNOWN"} or stage in {"", "ABSENT", "UNKNOWN"} or state in {"", "NO_SETUP", "UNKNOWN"}


def install(e6_module) -> None:
    if getattr(e6_module, "_E6_OPPORTUNITY_GUARD_INSTALLED", False):
        return
    original = e6_module.analyze_e6

    def guarded(market_data, upstream):
        result = original(market_data, upstream)
        if not isinstance(result, EngineResult):
            return result
        if not _should_rescue_watch(result):
            return result
        candidate = _fallback_opportunity(upstream)
        if candidate is None:
            return result
        return _watch(result, candidate)

    e6_module.analyze_e6 = guarded
    e6_module._E6_OPPORTUNITY_GUARD_INSTALLED = True
