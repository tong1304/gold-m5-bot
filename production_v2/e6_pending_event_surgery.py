from __future__ import annotations

from typing import Any

from .contracts import EngineResult

VERSION = "E6_PENDING_EVENT_SURGERY_V1"
PENDING_AUCTION_STATES = {"PENDING", "DEVELOPING", "FORMING", "AWAITING_CONFIRMATION", "CONFIRMATION_PENDING"}
WATCH_SETUPS = {"OPPORTUNITY_WATCH", "OPPORTUNITY_CANDIDATE", "OPPORTUNITY_THESIS"}
DIRECTIONS = {"BUY", "SELL"}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _direction(value: Any) -> str:
    text = _text(value)
    if text in {"BUY", "BULLISH", "UP", "LONG", "BUYERS", "BUYER", "TREND_UP", "BUY_CONTROLLED"} or text.startswith(("BUY ", "BUY_", "BUY:")):
        return "BUY"
    if text in {"SELL", "BEARISH", "DOWN", "SHORT", "SELLERS", "SELLER", "TREND_DOWN", "SELL_CONTROLLED"} or text.startswith(("SELL ", "SELL_", "SELL:")):
        return "SELL"
    return "NEUTRAL"


def _out(result: Any) -> dict[str, Any]:
    value = getattr(result, "output", {})
    return dict(value) if isinstance(value, dict) else {}


def _payload(upstream: dict[str, EngineResult], key: str) -> dict[str, Any]:
    result = upstream.get(key)
    return _out(result) if result else {}


def _is_invalidated(e3: dict[str, Any]) -> bool:
    return bool(
        e3.get("structure_invalidated") is True
        or e3.get("active_invalidation") is True
        or _text(e3.get("lifecycle")) == "INVALIDATED"
        or "STRUCTURE_INVALIDATED" in _text(e3.get("finding"))
        or "STRUCTURE_INVALIDATED" in _text(e3.get("invalidation"))
    )


def _is_existing_watch(e6: dict[str, Any]) -> bool:
    setup = _text(e6.get("setup") or e6.get("setup_family"))
    candidate = _text(e6.get("candidate_type"))
    return (
        setup in WATCH_SETUPS
        or candidate == "OPPORTUNITY_CANDIDATE"
        or e6.get("watch_only") is True
    ) and e6.get("trade_ready") is not True


def _is_no_setup(e6: dict[str, Any]) -> bool:
    setup = _text(e6.get("setup") or e6.get("setup_family"))
    finding = _text(e6.get("finding"))
    reasons = {_text(x) for x in (e6.get("reason_codes") or e6.get("reasons") or [])}
    return (
        setup in {"", "NO_SETUP", "UNKNOWN", "NONE"}
        and (
            "NO_CAUSAL_OPPORTUNITY" in reasons
            or "NO SURVIVING CAUSAL OPPORTUNITY THESIS" in finding
            or "NO CAUSAL SETUP HYPOTHESIS" in finding
        )
    )


def _failed_break_pending(e4: dict[str, Any]) -> bool:
    event = _text(e4.get("event") or e4.get("finding"))
    state = _text(e4.get("auction_state") or e4.get("auction_phase") or e4.get("state"))
    return "FAILED_BREAK_RECLAIM" in event and state in PENDING_AUCTION_STATES


def _space(e5: dict[str, Any], direction: str) -> float:
    key = "available_space_atr_long" if direction == "BUY" else "available_space_atr_short"
    try:
        value = float(e5.get(key) or 0.0)
        return value if value == value else 0.0
    except (TypeError, ValueError):
        return 0.0


def _candidate(upstream: dict[str, EngineResult]) -> dict[str, Any] | None:
    e1, e2, e3, e4, e5 = (_payload(upstream, key) for key in ("E1", "E2", "E3", "E4", "E5"))
    if _is_invalidated(e3) or not _failed_break_pending(e4):
        return None

    pressure = _direction(e1.get("directional_pressure") or e1.get("pressure"))
    external = _direction(e3.get("external_state") or e3.get("structure_direction") or e3.get("direction"))
    e2_direction = _direction(e2.get("direction") or e2.get("opportunity_direction"))

    # A pending failed-break reclaim is an unresolved auction event, not a
    # directional verdict. Use the independent market/structure anchor for the
    # watch direction and preserve E4's opposing response as counter-evidence.
    direction = pressure if pressure in DIRECTIONS else external if external in DIRECTIONS else e2_direction
    if direction not in DIRECTIONS:
        return None

    finding5 = _text(e5.get("finding"))
    value_state = _text(e5.get("value_state"))
    location = _text(e5.get("structural_location"))
    favorable_location = (
        "FAVORABLE_LOCATION" in finding5
        or location in {"AT_SUPPORT", "AT_RESISTANCE"}
        or value_state in {"DISCOUNT", "PREMIUM", "EQUILIBRIUM"}
    )
    space = _space(e5, direction)
    if not favorable_location and space <= 0.0:
        return None

    event_id = str(e4.get("event_id") or e4.get("event_candle_id") or "")
    counter: list[str] = ["E4_FAILED_BREAK_RECLAIM_PENDING"]
    if external in DIRECTIONS and external != direction:
        counter.append("E3_EXTERNAL_COUNTERFLOW")
    if e2_direction in DIRECTIONS and e2_direction != direction:
        counter.append("E2_DIRECTION_COUNTERFLOW")

    missing = ["E4_AUCTION_FOLLOW_THROUGH", "E7_CONFIRMATION"]
    if _text(e2.get("opportunity_maturity") or e2.get("state") or e2.get("opportunity_state")) in {"DEVELOPING", "EMERGING", "PENDING", "UNRESOLVED"}:
        missing.insert(0, "E2_OPPORTUNITY_CONFIRMATION")
    if _text(e3.get("internal_state")) == "MIXED":
        missing.append("E3_INTERNAL_STRUCTURE_ALIGNMENT")
    if space < 0.75:
        missing.append("STRUCTURAL_SPACE_INSUFFICIENT")

    return {
        "direction": direction,
        "family": "LIQUIDITY_RESPONSE",
        "event_id": event_id,
        "space": round(space, 4),
        "support": list(dict.fromkeys([
            "E1_DIRECTIONAL_CORE" if pressure == direction else "E3_EXTERNAL_STRUCTURE_SUPPORT",
            "E4_FAILED_BREAK_RECLAIM_EVENT",
            "E5_LOCATION_VALUE_SUPPORT" if favorable_location else "E5_SPACE_EVIDENCE",
        ])),
        "counter": list(dict.fromkeys(counter)),
        "missing": list(dict.fromkeys(missing)),
    }


def _watch(original: EngineResult, candidate: dict[str, Any]) -> EngineResult:
    out = dict(original.output or {})
    direction = candidate["direction"]
    missing = list(dict.fromkeys(candidate["missing"]))
    out.update({
        "architecture": VERSION,
        "state": "CONTESTED_WATCH",
        "setup_state": "CONTESTED_WATCH",
        "opportunity_stage": "CONTESTED_WATCH",
        "setup": "OPPORTUNITY_WATCH",
        "setup_family": candidate["family"],
        "candidate_type": "OPPORTUNITY_CANDIDATE",
        "candidate_setup": "OPPORTUNITY_WATCH",
        "direction": direction,
        "direction_thesis": direction,
        "thesis_direction": direction,
        "thesis_status": "CONTESTED",
        "setup_exists": False,
        "watch_only": True,
        "trade_ready": False,
        "trade_permission": False,
        "gate_passed": False,
        "e6_thesis_proven": False,
        "e6_causal_gate": "WATCH_ONLY",
        "finding": f"{direction} opportunity is contested watch; E4 failed-break auction remains pending and no trade setup is proven.",
        "thesis": f"{direction} opportunity is watchable from E1-E5 closed-candle evidence; E4 resolution and E7 confirmation remain mandatory.",
        "supporting_evidence": candidate["support"],
        "counter_evidence": candidate["counter"],
        "hard_conflicts": [],
        "missing_proof": missing,
        "missing_evidence": missing,
        "next_required_event": "NEXT_CLOSED_M5_CANDLE",
        "wait_for": ",".join(missing),
        "candidate_identity": f"OPPORTUNITY_WATCH:{direction}:LIQUIDITY_RESPONSE:{candidate['event_id']}",
        "opportunity_id": f"{direction}|OPPORTUNITY_WATCH|{candidate['event_id']}",
        "event_id": candidate["event_id"],
        "available_space_atr": candidate["space"],
        "reason_codes": missing,
        "reasons": missing,
        "execution_authority": "E9",
        "invalidated": False,
        "upstream_evidence_lost": False,
        "causal_evidence_lost": False,
        "lifecycle_state": "OPPORTUNITY_WATCH",
        "pending_event_authority": VERSION,
    })
    return EngineResult("E6", "Setup Brain", False, 0.0, out, tuple(missing))


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_E6_PENDING_EVENT_SURGERY_INSTALLED", False):
        return
    original = pipeline_module.analyze_e6

    def patched_analyze_e6(market_data: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
        result = original(market_data, upstream)
        if not isinstance(result, EngineResult):
            return result
        current = _out(result)
        if _is_existing_watch(current) or not _is_no_setup(current):
            return result
        candidate = _candidate(upstream)
        if candidate is None:
            return result
        print(
            f"[PRODUCTION V2] E6_PENDING_EVENT_SURGERY version={VERSION} action=WATCH "
            f"direction={candidate['direction']} event_id={candidate['event_id']}",
            flush=True,
        )
        return _watch(result, candidate)

    pipeline_module.analyze_e6 = patched_analyze_e6
    pipeline_module._E6_PENDING_EVENT_SURGERY_INSTALLED = True
