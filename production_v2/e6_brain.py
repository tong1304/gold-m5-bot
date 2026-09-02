from __future__ import annotations

from typing import Any

from .contracts import EngineResult
from .e6_brain_legacy import analyze_e6 as _legacy_analyze_e6

ARCHITECTURE = "E6_OPPORTUNITY_THESIS_ENGINE_V52"
VERSION = "52.0"


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(value: Any) -> str:
    text = _text(value)
    if text in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "TREND_UP"} or text.startswith("BUY "):
        return "BUY"
    if text in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "TREND_DOWN"} or text.startswith("SELL "):
        return "SELL"
    return "NEUTRAL"


def _out(result: Any) -> dict[str, Any]:
    return dict(getattr(result, "output", {}) or {})


def _payload(upstream: dict[str, Any], key: str) -> dict[str, Any]:
    item = upstream.get(key)
    return _out(item) if item else {}


def _e2_unresolved(e2: dict[str, Any]) -> bool:
    finding = _text(e2.get("finding", e2.get("state")))
    state = _text(e2.get("opportunity_state", e2.get("opportunity_decision")))
    maturity = _text(e2.get("opportunity_maturity"))
    return (
        finding in {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS", "WAIT", "EMERGING", "PENDING", "DEVELOPING"}
        or state in {"UNRESOLVED", "UNPROVEN", "AMBIGUOUS", "WAIT", "EMERGING", "PENDING", "DEVELOPING"}
        or maturity in {"UNPROVEN", "EMERGING", "DEVELOPING"}
        or "OPPORTUNITY IS DEVELOPING" in finding
        or "OPPORTUNITY IS EMERGING" in finding
        or "OPPORTUNITY IS EMERGING" in finding.replace("NEUTRAL ", "")
    )


def _e2_direction(e2: dict[str, Any]) -> str:
    for key in ("direction", "opportunity_direction", "auction_direction"):
        direction = _direction(e2.get(key))
        if direction != "NEUTRAL":
            return direction
    return "NEUTRAL"


def _e3_direction(e3: dict[str, Any], key: str) -> str:
    return _direction(e3.get(key))


def _e4_direction(e4: dict[str, Any]) -> str:
    direction = _direction(e4.get("direction"))
    if direction != "NEUTRAL":
        return direction

    event = _text(e4.get("event", e4.get("finding")))
    taker = _direction(e4.get("liquidity_taker"))
    actor = _direction(e4.get("response_actor"))

    if "HIGH_LIQUIDITY_INTERACTION" in event and taker != "NEUTRAL":
        return taker
    if "LOW_LIQUIDITY_INTERACTION" in event and taker != "NEUTRAL":
        return taker

    if "LOW_FAILED_BREAK_RECLAIM" in event or "HIGH_FAILED_BREAK_RECLAIM" in event:
        if actor != "NEUTRAL":
            return actor
        if "UP" in event:
            return "BUY"
        if "DOWN" in event:
            return "SELL"

    if "LOW_SWEEP_REJECTION" in event or "LOW_REJECTION" in event:
        return "BUY"
    if "HIGH_SWEEP_REJECTION" in event or "HIGH_REJECTION" in event:
        return "SELL"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
        return "SELL"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
        return "BUY"
    return actor if actor != "NEUTRAL" else "NEUTRAL"


def _e4_event(e4: dict[str, Any]) -> str:
    return _text(e4.get("event", e4.get("finding")))


def _e5_space(e5: dict[str, Any], direction: str) -> float:
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    try:
        value = float(e5.get(key, 0.0) or 0.0)
        return value if value == value else 0.0
    except (TypeError, ValueError):
        return 0.0


def _causal_opportunity(upstream: dict[str, Any]) -> dict[str, Any] | None:
    e1, e2, e3, e4, e5 = (_payload(upstream, key) for key in ("E1", "E2", "E3", "E4", "E5"))
    e1_direction = _direction(e1.get("directional_pressure", e1.get("pressure")))
    e2_direction = _e2_direction(e2)
    internal = _e3_direction(e3, "internal_state")
    external = _e3_direction(e3, "external_state")
    e4_direction = _e4_direction(e4)
    event = _e4_event(e4)
    unresolved = _e2_unresolved(e2)

    counter_evidence: list[str] = []
    hard_conflicts: list[str] = []
    missing_internal_proof: list[str] = []

    if e1_direction != "NEUTRAL" and external != "NEUTRAL" and e1_direction != external:
        if unresolved and e4_direction == external:
            core = external
            counter_evidence.append("E1_COUNTER_EVIDENCE")
        else:
            return None
    else:
        core = e1_direction if e1_direction != "NEUTRAL" else external

    if core == "NEUTRAL":
        return None

    if external != "NEUTRAL" and external != core:
        hard_conflicts.append("E3_EXTERNAL_STRUCTURE_CONFLICT")
        return None

    if internal == core:
        internal_status = "ALIGNED"
    elif internal in {"BUY", "SELL", "UP", "DOWN"} and internal != core:
        internal_status = "COUNTERFLOW"
        counter_evidence.append("E3_INTERNAL_COUNTER_EVIDENCE")
        missing_internal_proof.append("E3_INTERNAL_STRUCTURE_ALIGNMENT")
    elif internal == "MIXED":
        internal_status = "UNRESOLVED_COUNTERFLOW"
        counter_evidence.append("E3_INTERNAL_COUNTER_EVIDENCE")
        missing_internal_proof.extend(["E3_INTERNAL_EVIDENCE_UNRESOLVED", "E3_INTERNAL_STRUCTURE_ALIGNMENT"])
    else:
        internal_status = "UNRESOLVED"
        counter_evidence.append("E3_INTERNAL_EVIDENCE_UNRESOLVED")
        missing_internal_proof.append("E3_INTERNAL_STRUCTURE_ALIGNMENT")

    if e2_direction != "NEUTRAL" and e2_direction != core:
        hard_conflicts.append("E2_DIRECTIONAL_CONFLICT")
        return None
    if not unresolved:
        return None
    if e4_direction not in {"NEUTRAL", core}:
        hard_conflicts.append("E4_DIRECTIONAL_CONFLICT")
        return None

    directional_event = any(token in event for token in ("ACCEPTANCE", "REJECTION", "SWEEP", "FAILED_BREAK", "BREAK", "RECLAIM", "LIQUIDITY_INTERACTION"))
    if not directional_event:
        return None

    space = _e5_space(e5, core)
    value = _text(e5.get("value_state"))
    location = _text(e5.get("structural_location"))
    favorable = "FAVORABLE_LOCATION" in _text(e5.get("finding")) or location in {"AT_SUPPORT", "AT_RESISTANCE"} or value in {"DISCOUNT", "PREMIUM"}
    if not favorable and space <= 0.0:
        return None

    family = "AUCTION_ACCEPTANCE_CONTINUATION" if "ACCEPTANCE" in event else "LIQUIDITY_RESPONSE" if any(token in event for token in ("REJECTION", "SWEEP", "FAILED_BREAK", "RECLAIM", "LIQUIDITY_INTERACTION")) else "STRUCTURAL_OPPORTUNITY"
    missing = ["E2_OPPORTUNITY_CONFIRMATION", "E6_CAUSAL_SETUP_PROOF", "E7_CONFIRMATION"]
    if "PENDING" in _text(e4.get("auction_state", e4.get("state"))) or "CANDIDATE" in event or "LIQUIDITY_INTERACTION" in event:
        missing.insert(1, "E4_AUCTION_FOLLOW_THROUGH")
    if space < 0.75:
        missing.append("STRUCTURAL_SPACE_INSUFFICIENT")
    missing.extend(missing_internal_proof)
    support = ["E3_EXTERNAL_STRUCTURE_SUPPORT", "E4_DIRECTIONAL_AUCTION_EVIDENCE"]
    if e1_direction == core:
        support.insert(0, "E1_DIRECTIONAL_CORE")
    elif e1_direction != "NEUTRAL":
        counter_evidence.append("E1_COUNTER_EVIDENCE")
    if internal_status == "ALIGNED":
        support.append("E3_INTERNAL_STRUCTURE_SUPPORT")
    if favorable:
        support.append("E5_LOCATION_VALUE_SUPPORT")
    return {
        "direction": core,
        "family": family,
        "space": round(space, 4),
        "support": list(dict.fromkeys(support)),
        "missing": list(dict.fromkeys(missing)),
        "counter_evidence": list(dict.fromkeys(counter_evidence)),
        "hard_conflicts": list(dict.fromkeys(hard_conflicts)),
        "event": event,
        "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""),
        "internal_status": internal_status,
    }


def _watch_result(legacy: EngineResult, opportunity: dict[str, Any]) -> EngineResult:
    output = dict(legacy.output or {})
    direction = opportunity["direction"]
    missing = list(dict.fromkeys(opportunity["missing"]))
    counter_evidence = list(dict.fromkeys(opportunity.get("counter_evidence", [])))
    hard_conflicts = list(dict.fromkeys(opportunity.get("hard_conflicts", [])))

    contested = (
        "E1_COUNTER_EVIDENCE" in counter_evidence
        or "STRUCTURAL_SPACE_INSUFFICIENT" in missing
    )
    stage = "CONTESTED" if contested else "FORMING"
    state = "THESIS_CONTESTED" if contested else "FORMING"
    setup = "OPPORTUNITY_THESIS" if contested else "OPPORTUNITY_WATCH"

    output.update({
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "state": state,
        "setup_state": state,
        "opportunity_stage": stage,
        "setup": setup,
        "setup_family": opportunity["family"],
        "candidate_type": "OPPORTUNITY_CANDIDATE",
        "direction": direction,
        "direction_thesis": direction,
        "thesis_direction": direction,
        "trade_ready": False,
        "gate_passed": False,
        "thesis_status": stage,
        "finding": f"{direction} opportunity thesis is {stage.lower()}; internal structure is {opportunity['internal_status']} and trade setup is not yet proven.",
        "thesis": f"{direction} opportunity remains trackable while external directional evidence persists; counterflow and constrained space are retained as counter-evidence rather than erasing the thesis.",
        "supporting_evidence": opportunity["support"],
        "counter_evidence": counter_evidence,
        "hard_conflicts": hard_conflicts,
        "missing_proof": missing,
        "next_required_event": "E2_OPPORTUNITY_CONFIRMATION,E4_AUCTION_FOLLOW_THROUGH,E3_INTERNAL_STRUCTURE_ALIGNMENT,E6_CAUSAL_SETUP_PROOF,E7_CONFIRMATION",
        "wait_for": "E2_OPPORTUNITY_CONFIRMATION,E4_AUCTION_FOLLOW_THROUGH,E3_INTERNAL_STRUCTURE_ALIGNMENT,E6_CAUSAL_SETUP_PROOF,E7_CONFIRMATION",
        "candidate_identity": f"OPPORTUNITY_THESIS:{direction}:{opportunity['family']}" if contested else f"OPPORTUNITY_WATCH:{direction}:{opportunity['family']}",
        "opportunity_id": f"{direction}|OPPORTUNITY_THESIS" if contested else f"{direction}|OPPORTUNITY_WATCH",
        "event_id": opportunity["event_id"],
        "available_space_atr": opportunity["space"],
        "watch_only": True,
        "execution_authority": "E9",
        "reason_codes": missing,
        "reasons": missing,
    })
    return EngineResult(legacy.engine_id, legacy.name, False, legacy.score, output, tuple(missing))


def _no_surviving_causal_thesis(legacy: EngineResult) -> EngineResult:
    output = dict(legacy.output or {})
    output.update({
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "state": "NO_SETUP",
        "setup_state": "NO_SETUP",
        "opportunity_stage": "ABSENT",
        "setup": "NO_SETUP",
        "setup_family": "",
        "candidate_type": "NONE",
        "direction": "NEUTRAL",
        "direction_thesis": "NEUTRAL",
        "thesis_direction": "NEUTRAL",
        "trade_ready": False,
        "gate_passed": False,
        "thesis_status": "ABSENT",
        "finding": "No surviving causal opportunity thesis from E1-E5; legacy pattern output is suppressed.",
        "thesis": "E6 cannot create an independent setup when upstream causal evidence does not support an opportunity.",
        "supporting_evidence": [],
        "counter_evidence": [],
        "hard_conflicts": [],
        "missing_proof": ["E1_E2_E3_E4_E5_CAUSAL_OPPORTUNITY"],
        "next_required_event": "NEW_CAUSAL_OPPORTUNITY_FROM_E1_E5",
        "wait_for": "NEW_CAUSAL_OPPORTUNITY_FROM_E1_E5",
        "candidate_identity": "",
        "opportunity_id": "",
        "event_id": "",
        "available_space_atr": 0.0,
        "watch_only": False,
        "execution_authority": "E9",
        "reason_codes": ["NO_CAUSAL_OPPORTUNITY"],
        "reasons": ["NO_CAUSAL_OPPORTUNITY"],
    })
    return EngineResult(legacy.engine_id, legacy.name, False, legacy.score, output, ("NO_CAUSAL_OPPORTUNITY",))


def analyze_e6(market_data: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    legacy = _legacy_analyze_e6(market_data, upstream)
    opportunity = _causal_opportunity(upstream)

    # E1-E5 causal evidence is the gate. A legacy E6 pattern may enrich a
    # surviving causal thesis, but it must never manufacture one on its own.
    if opportunity is None:
        return _no_surviving_causal_thesis(legacy)

    current = _out(legacy)
    legacy_direction = _direction(current.get("direction"))
    legacy_setup = _text(current.get("setup"))
    legacy_has_setup = (
        _text(current.get("state")) not in {"ABSENT", "NO_SETUP"}
        and legacy_setup not in {"", "NONE", "NO_SETUP", "UNKNOWN"}
    )

    if legacy_has_setup and legacy_direction == opportunity["direction"]:
        return legacy

    return _watch_result(legacy, opportunity)
