from __future__ import annotations

from typing import Any

from .contracts import EngineResult
from .e6_brain_legacy import analyze_e6 as _legacy_analyze_e6

ARCHITECTURE = "E6_OPPORTUNITY_THESIS_ENGINE_V46"
VERSION = "46.0"


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
    if any(token in event for token in ("LOW_ACCEPTANCE", "LOW_BREAK", "LOW_SWEEP_REJECTION", "LOW_FAILED_BREAK_RECLAIM", "LOW_REJECTION")):
        return "BUY" if "ACCEPTANCE" not in event and "BREAK" not in event else ("SELL" if "LOW_ACCEPTANCE" in event or "LOW_BREAK" in event else "BUY")
    if any(token in event for token in ("HIGH_ACCEPTANCE", "HIGH_BREAK")):
        return "BUY"
    if any(token in event for token in ("HIGH_SWEEP_REJECTION", "HIGH_FAILED_BREAK_RECLAIM", "HIGH_REJECTION")):
        return "SELL"
    return "NEUTRAL"


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

    # E2 opposition is a hard blocker for a forming thesis. E1/E3 core must
    # agree; E4 is treated as auction evidence, not an unconditional veto.
    core = e1_direction if e1_direction != "NEUTRAL" and internal == e1_direction and external in {e1_direction, "NEUTRAL"} else "NEUTRAL"
    if core == "NEUTRAL" and internal != "NEUTRAL" and external == internal:
        core = internal
    if core == "NEUTRAL":
        return None
    if e2_direction != "NEUTRAL" and e2_direction != core:
        return None
    if not unresolved:
        return None
    if e4_direction not in {"NEUTRAL", core}:
        return None
    directional_event = any(token in event for token in ("ACCEPTANCE", "REJECTION", "SWEEP", "FAILED_BREAK", "BREAK", "RECLAIM"))
    if not directional_event:
        return None

    space = _e5_space(e5, core)
    value = _text(e5.get("value_state"))
    location = _text(e5.get("structural_location"))
    favorable = "FAVORABLE_LOCATION" in _text(e5.get("finding")) or location in {"AT_SUPPORT", "AT_RESISTANCE"} or value in {"DISCOUNT", "PREMIUM"}
    if not favorable and space <= 0.0:
        return None

    family = "AUCTION_ACCEPTANCE_CONTINUATION" if "ACCEPTANCE" in event else "LIQUIDITY_RESPONSE" if any(token in event for token in ("REJECTION", "SWEEP", "FAILED_BREAK", "RECLAIM")) else "STRUCTURAL_OPPORTUNITY"
    missing = ["E2_OPPORTUNITY_CONFIRMATION", "E6_CAUSAL_SETUP_PROOF", "E7_CONFIRMATION"]
    if "PENDING" in _text(e4.get("auction_state", e4.get("state"))) or "CANDIDATE" in event:
        missing.insert(1, "E4_AUCTION_FOLLOW_THROUGH")
    if space < 0.75:
        missing.append("STRUCTURAL_SPACE_INSUFFICIENT")
    support = ["E1_DIRECTIONAL_CORE", "E3_STRUCTURE_SUPPORT", "E4_DIRECTIONAL_AUCTION_EVIDENCE"]
    if favorable:
        support.append("E5_LOCATION_VALUE_SUPPORT")
    return {
        "direction": core,
        "family": family,
        "space": round(space, 4),
        "support": support,
        "missing": list(dict.fromkeys(missing)),
        "event": event,
        "event_id": str(e4.get("event_id") or e4.get("event_candle_id") or ""),
    }


def _watch_result(legacy: EngineResult, opportunity: dict[str, Any]) -> EngineResult:
    output = dict(legacy.output or {})
    direction = opportunity["direction"]
    missing = list(dict.fromkeys(opportunity["missing"]))
    output.update({
        "architecture": ARCHITECTURE,
        "version": VERSION,
        "state": "FORMING",
        "setup_state": "FORMING",
        "opportunity_stage": "FORMING",
        "setup": "OPPORTUNITY_WATCH",
        "setup_family": opportunity["family"],
        "candidate_type": "OPPORTUNITY_CANDIDATE",
        "direction": direction,
        "direction_thesis": direction,
        "thesis_direction": direction,
        "trade_ready": False,
        "gate_passed": False,
        "thesis_status": "FORMING",
        "finding": f"{direction} opportunity thesis is forming; trade setup is not yet proven.",
        "thesis": f"{direction} opportunity is worth monitoring across closed M5 candles before execution proof is complete.",
        "supporting_evidence": opportunity["support"],
        "missing_proof": missing,
        "next_required_event": "E2_OPPORTUNITY_CONFIRMATION,E4_AUCTION_FOLLOW_THROUGH,E6_CAUSAL_SETUP_PROOF,E7_CONFIRMATION",
        "wait_for": "E2_OPPORTUNITY_CONFIRMATION,E4_AUCTION_FOLLOW_THROUGH,E6_CAUSAL_SETUP_PROOF,E7_CONFIRMATION",
        "candidate_identity": f"OPPORTUNITY_WATCH:{direction}:{opportunity['family']}",
        "opportunity_id": f"{direction}|OPPORTUNITY_WATCH",
        "event_id": opportunity["event_id"],
        "available_space_atr": opportunity["space"],
        "watch_only": True,
        "execution_authority": "E9",
        "reason_codes": missing,
        "reasons": missing,
    })
    return EngineResult(legacy.engine_id, legacy.name, False, legacy.score, output, tuple(missing))


def analyze_e6(market_data: dict[str, Any], upstream: dict[str, EngineResult]) -> EngineResult:
    legacy = _legacy_analyze_e6(market_data, upstream)
    current = _out(legacy)
    if _text(current.get("state")) not in {"ABSENT", "NO_SETUP"} and _text(current.get("setup")) not in {"NONE", "NO_SETUP", "UNKNOWN"}:
        return legacy
    opportunity = _causal_opportunity(upstream)
    if opportunity is None:
        return legacy
    return _watch_result(legacy, opportunity)
