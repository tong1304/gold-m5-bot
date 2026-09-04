from __future__ import annotations

from typing import Any
from .contracts import EngineResult

ARCHITECTURE = "E6_OPPORTUNITY_THESIS_ENGINE_V56"
VERSION = "56.0"
WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
TERMINAL_AUCTION_STATES = {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "REJECTED", "RECLAIMED"}
MIN_SPACE_ATR = 0.75


def _text(v: Any) -> str:
    return str(v or "").upper().strip()


def _direction_value(v: Any) -> str:
    t = _text(v)
    if t in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "BUYER", "TREND_UP"} or t.startswith("BUY ") or t.startswith("BUY_"):
        return "BUY"
    if t in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "SELLER", "TREND_DOWN"} or t.startswith("SELL ") or t.startswith("SELL_"):
        return "SELL"
    return "NEUTRAL"


def _direction(v: Any, *others: Any) -> str:
    for value in (v, *others):
        d = _direction_value(value)
        if d != "NEUTRAL":
            return d
    return "NEUTRAL"


def _out(result: Any) -> dict[str, Any]:
    value = getattr(result, "output", {})
    return dict(value) if isinstance(value, dict) else {}


def _payload(upstream: dict[str, Any], key: str) -> dict[str, Any]:
    return _out(upstream.get(key))


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
        or "OPPORTUNITY IS UNPROVEN" in finding
    )


def _e2_direction(e2: dict[str, Any]) -> str:
    for key in ("direction", "opportunity_direction", "auction_direction"):
        d = _direction_value(e2.get(key))
        if d != "NEUTRAL":
            return d
    finding = _text(e2.get("finding", e2.get("state")))
    if "DOWN OPPORTUNITY" in finding or "SELL OPPORTUNITY" in finding:
        return "SELL"
    if "UP OPPORTUNITY" in finding or "BUY OPPORTUNITY" in finding:
        return "BUY"
    return "NEUTRAL"


def _e3_invalidated(e3: dict[str, Any]) -> bool:
    return bool(
        e3.get("structure_invalidated") is True
        or e3.get("active_invalidation") is True
        or _text(e3.get("lifecycle")) == "INVALIDATED"
        or "STRUCTURE_INVALIDATED" in _text(e3.get("finding"))
        or "STRUCTURE_INVALIDATED" in _text(e3.get("invalidation"))
    )


def _e4_direction(e4: dict[str, Any]) -> str:
    d = _direction_value(e4.get("direction"))
    if d != "NEUTRAL":
        return d
    event = _text(e4.get("event", e4.get("finding")))
    actor = _direction_value(e4.get("response_actor"))
    if "FAILED_BREAK_RECLAIM" in event and actor != "NEUTRAL":
        return actor
    if "HIGH_SWEEP_REJECTION" in event or "HIGH_REJECTION" in event:
        return "SELL"
    if "LOW_SWEEP_REJECTION" in event or "LOW_REJECTION" in event:
        return "BUY"
    if "HIGH_ACCEPTANCE" in event or "HIGH_BREAK" in event:
        return "BUY"
    if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event:
        return "SELL"
    if "LIQUIDITY_INTERACTION" in event:
        return _direction_value(e4.get("liquidity_taker"))
    return "NEUTRAL"


def _e5_space(e5: dict[str, Any], direction: str) -> float:
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    try:
        value = float(e5.get(key, 0.0) or 0.0)
        return value if value == value else 0.0
    except (TypeError, ValueError):
        return 0.0


def _causal_opportunity(upstream: dict[str, EngineResult]) -> dict[str, Any] | None:
    e1, e2, e3, e4, e5 = (_payload(upstream, k) for k in ("E1", "E2", "E3", "E4", "E5"))
    e1d = _direction_value(e1.get("directional_pressure", e1.get("pressure")))
    e2d = _e2_direction(e2)
    internal = _direction_value(e3.get("internal_state"))
    external = _direction_value(e3.get("external_state", e3.get("direction")))
    e4d = _e4_direction(e4)
    event = _text(e4.get("event", e4.get("finding")))
    auction_state = _text(e4.get("auction_state", e4.get("state")))
    unresolved = _e2_unresolved(e2)

    if _e3_invalidated(e3):
        return None
    if not any(token in event for token in ("ACCEPTANCE", "REJECTION", "SWEEP", "FAILED_BREAK", "BREAK", "RECLAIM", "LIQUIDITY_INTERACTION")):
        return None

    # Direction is resolved hierarchically from the strongest causal evidence
    # available: E1 directional core, then E3 external structure, then E2
    # opportunity anchor, then E4's actual auction response. This allows a
    # genuine E4 sweep/rejection to create a WATCH even when the broader regime
    # is neutral, while E2/E4 disagreement remains a hard rejection once E2 is
    # actually confirmed.
    if e1d in {"BUY", "SELL"}:
        direction = e1d
    elif external in {"BUY", "SELL"}:
        direction = external
    elif e2d in {"BUY", "SELL"}:
        direction = e2d
    else:
        direction = e4d
    counter: list[str] = []

    # E1/E3 disagreement is allowed only as a developing counterflow when E2 is unresolved
    # and E4 independently supports the E3 direction. It never becomes a hidden override.
    if e1d in {"BUY", "SELL"} and external in {"BUY", "SELL"} and e1d != external:
        if not (unresolved and e4d == external):
            return None
        direction = external
        counter.append("E1_COUNTER_EVIDENCE")

    if direction not in {"BUY", "SELL"}:
        return None
    if e2d not in {"NEUTRAL", direction}:
        return None
    if e4d not in {"NEUTRAL", direction}:
        return None

    internal_status = "ALIGNED" if internal == direction else "UNRESOLVED"
    missing_internal: list[str] = []
    if internal == "MIXED":
        internal_status = "UNRESOLVED_COUNTERFLOW"
        counter.append("E3_INTERNAL_COUNTER_EVIDENCE")
        missing_internal.extend(["E3_INTERNAL_EVIDENCE_UNRESOLVED", "E3_INTERNAL_STRUCTURE_ALIGNMENT"])
    elif internal in {"BUY", "SELL"} and internal != direction:
        internal_status = "COUNTERFLOW"
        counter.append("E3_INTERNAL_COUNTER_EVIDENCE")
        missing_internal.append("E3_INTERNAL_STRUCTURE_ALIGNMENT")
    elif internal == "NEUTRAL":
        missing_internal.append("E3_INTERNAL_STRUCTURE_ALIGNMENT")

    space = _e5_space(e5, direction)
    value = _text(e5.get("value_state"))
    location = _text(e5.get("structural_location"))
    finding5 = _text(e5.get("finding"))
    favorable = "FAVORABLE_LOCATION" in finding5 or location in {"AT_SUPPORT", "AT_RESISTANCE"} or value in {"DISCOUNT", "PREMIUM", "EQUILIBRIUM"}
    if not favorable and space <= 0.0:
        return None

    terminal = auction_state in TERMINAL_AUCTION_STATES or "TERMINAL" in auction_state
    missing: list[str] = []
    if unresolved:
        missing.append("E2_OPPORTUNITY_CONFIRMATION")
    if not terminal:
        missing.append("E4_AUCTION_FOLLOW_THROUGH")
    missing.extend(missing_internal)
    if space < MIN_SPACE_ATR:
        missing.append("STRUCTURAL_SPACE_INSUFFICIENT")
    missing.append("E7_CONFIRMATION")

    family = (
        "AUCTION_ACCEPTANCE_CONTINUATION" if "ACCEPTANCE" in event
        else "LIQUIDITY_RESPONSE" if any(x in event for x in ("REJECTION", "SWEEP", "FAILED_BREAK", "RECLAIM", "LIQUIDITY_INTERACTION"))
        else "STRUCTURAL_OPPORTUNITY"
    )
    support = ["E4_DIRECTIONAL_AUCTION_EVIDENCE"]
    if e1d == direction:
        support.insert(0, "E1_DIRECTIONAL_CORE")
    if external == direction:
        support.append("E3_EXTERNAL_STRUCTURE_SUPPORT")
    if internal == direction:
        support.append("E3_INTERNAL_STRUCTURE_SUPPORT")
    if e2d == direction:
        support.append("E2_DIRECTIONAL_ANCHOR")
    if favorable:
        support.append("E5_LOCATION_VALUE_SUPPORT")
    return {
        "direction": direction,
        "family": family,
        "space": round(space, 4),
        "support": list(dict.fromkeys(support)),
        "missing": list(dict.fromkeys(missing)),
        "counter": list(dict.fromkeys(counter)),
        "event": event,
        "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""),
        "internal_status": internal_status,
        "terminal": terminal,
        "e2_confirmed": not unresolved and e2d == direction,
    }


def _watch(original: EngineResult, candidate: dict[str, Any]) -> EngineResult:
    direction = candidate["direction"]
    missing = list(dict.fromkeys(candidate.get("missing", [])))
    contested = bool(candidate.get("counter")) or "STRUCTURAL_SPACE_INSUFFICIENT" in missing or candidate.get("internal_status") in {"COUNTERFLOW", "UNRESOLVED_COUNTERFLOW"}
    stage = "CONTESTED" if contested else "FORMING"
    out = dict(original.output or {})
    out.update({
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "state": "CONTESTED_WATCH" if contested else "FORMING",
        "setup_state": "CONTESTED_WATCH" if contested else "FORMING",
        "opportunity_stage": "CONTESTED_WATCH" if contested else "OPPORTUNITY_WATCH",
        "setup": "OPPORTUNITY_WATCH",
        "setup_family": candidate["family"],
        "candidate_type": "OPPORTUNITY_CANDIDATE",
        "direction": direction,
        "direction_thesis": direction,
        "thesis_direction": direction,
        "thesis_status": stage,
        "setup_exists": False,
        "watch_only": True,
        "trade_ready": False,
        "trade_permission": False,
        "gate_passed": False,
        "finding": f"{direction} opportunity is {stage.lower()}; causal setup is not yet proven.",
        "thesis": f"{direction} causal opportunity is watchable; E4/E7 proof remains pending.",
        "supporting_evidence": candidate["support"],
        "counter_evidence": candidate["counter"],
        "hard_conflicts": [],
        "missing_proof": missing,
        "next_required_event": "NEXT_CLOSED_M5_CANDLE",
        "wait_for": ",".join(missing) if missing else "NEXT_CLOSED_M5_CANDLE",
        "candidate_identity": f"OPPORTUNITY_WATCH:{direction}:{candidate['family']}",
        "opportunity_id": f"{direction}|OPPORTUNITY_WATCH",
        "event_id": candidate["event_id"],
        "available_space_atr": candidate["space"],
        "execution_authority": "E9",
        "reason_codes": missing,
        "reasons": missing,
        "e6_causal_gate": "WATCH_ONLY",
        "e6_thesis_proven": False,
    })
    return EngineResult("E6", "Setup Brain", False, 0.0, out, tuple(missing))


def _thesis(original: EngineResult, candidate: dict[str, Any]) -> EngineResult:
    out = dict(original.output or {})
    direction = candidate["direction"]
    missing = list(dict.fromkeys(candidate.get("missing", [])))
    out.update({
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "state": "SETUP_THESIS",
        "setup_state": "SETUP_THESIS",
        "opportunity_stage": "SETUP_THESIS",
        "setup": candidate["family"],
        "setup_family": candidate["family"],
        "candidate_type": "SETUP_CANDIDATE",
        "direction": direction,
        "direction_thesis": direction,
        "thesis_direction": direction,
        "thesis_status": "FORMING",
        "setup_exists": True,
        "watch_only": False,
        "trade_ready": False,
        "trade_permission": False,
        "gate_passed": False,
        "finding": f"{direction} causal setup thesis is established from closed-candle E1-E5 evidence; E7 confirmation and E8 economics remain pending.",
        "thesis": f"{direction} setup thesis: {candidate['family']} supported by closed-candle upstream evidence.",
        "supporting_evidence": candidate["support"],
        "counter_evidence": candidate["counter"],
        "hard_conflicts": [],
        "missing_proof": [x for x in missing if x != "E2_OPPORTUNITY_CONFIRMATION" and x != "E4_AUCTION_FOLLOW_THROUGH"],
        "next_required_event": "E7_CONFIRMATION",
        "wait_for": "E7_CONFIRMATION",
        "candidate_identity": f"SETUP_THESIS:{direction}:{candidate['family']}",
        "opportunity_id": f"{direction}|SETUP_THESIS",
        "event_id": candidate["event_id"],
        "available_space_atr": candidate["space"],
        "execution_authority": "E9",
        "reason_codes": ["E7_CONFIRMATION"],
        "reasons": ["E7_CONFIRMATION"],
        "e6_causal_gate": "PASSED",
        "e6_thesis_proven": True,
    })
    return EngineResult("E6", "Setup Brain", False, 0.0, out, ("E7_CONFIRMATION",))


def _invalidated(original: EngineResult, reason: str) -> EngineResult:
    out = dict(original.output or {})
    out.update({
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "state": "INVALIDATED",
        "setup_state": "INVALIDATED",
        "opportunity_stage": "INVALIDATED",
        "setup": "NO_SETUP",
        "setup_family": "",
        "candidate_type": "NONE",
        "direction": "NEUTRAL",
        "direction_thesis": "NEUTRAL",
        "thesis_direction": "NEUTRAL",
        "thesis_status": "INVALIDATED",
        "setup_exists": False,
        "watch_only": False,
        "trade_ready": False,
        "gate_passed": False,
        "finding": f"E6 invalidated: {reason}.",
        "thesis": "Prior E6 state cannot survive invalid upstream structure.",
        "supporting_evidence": [],
        "counter_evidence": [reason],
        "hard_conflicts": [reason],
        "missing_proof": ["NEW_VALID_STRUCTURE"],
        "next_required_event": "NEW_VALID_STRUCTURE",
        "wait_for": "NEW_VALID_STRUCTURE",
        "candidate_identity": "",
        "opportunity_id": "",
        "event_id": "",
        "available_space_atr": 0.0,
        "reason_codes": [reason],
        "reasons": [reason],
        "e6_causal_gate": "INVALIDATED",
        "e6_thesis_proven": False,
    })
    return EngineResult("E6", "Setup Brain", False, 0.0, out, (reason,))


def _absent(original: EngineResult) -> EngineResult:
    out = dict(original.output or {})
    out.update({
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
        "thesis_status": "ABSENT",
        "setup_exists": False,
        "watch_only": False,
        "trade_ready": False,
        "gate_passed": False,
        "finding": "No surviving causal opportunity thesis from E1-E5; legacy setup output is suppressed.",
        "thesis": "E6 cannot create an independent setup without surviving upstream causal evidence.",
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
        "reason_codes": ["NO_CAUSAL_OPPORTUNITY"],
        "reasons": ["NO_CAUSAL_OPPORTUNITY"],
        "e6_causal_gate": "ABSENT",
        "e6_thesis_proven": False,
    })
    return EngineResult("E6", "Setup Brain", False, 0.0, out, ("NO_CAUSAL_OPPORTUNITY",))


def analyze_e6(market_data: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    del market_data
    base = EngineResult("E6", "Setup Brain", False, 0.0, {}, ())
    e3 = _payload(upstream, "E3")
    if _e3_invalidated(e3):
        return _invalidated(base, "E3_STRUCTURE_INVALIDATED")
    candidate = _causal_opportunity(upstream)
    if candidate is None:
        return _absent(base)
    thesis_ready = (
        candidate["terminal"]
        and candidate["e2_confirmed"]
        and candidate["internal_status"] == "ALIGNED"
        and candidate["space"] >= MIN_SPACE_ATR
        and not candidate["counter"]
    )
    return _thesis(base, candidate) if thesis_ready else _watch(base, candidate)
