from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .opportunity_lifecycle_progression import advance_lifecycle_stage
from . import opportunity_memory


def _engine(result: DecisionResult, engine_id: str) -> EngineResult | None:
    return next((item for item in result.engines if item.engine_id == engine_id), None)


def _out(result: DecisionResult, engine_id: str) -> dict[str, Any]:
    engine = _engine(result, engine_id)
    return dict(engine.output or {}) if engine else {}


def _text(value: Any) -> str:
    return str(value or "").upper().strip()


def _bool(value: Any) -> bool:
    if isinstance(value, str):
        return _text(value) in {"1", "TRUE", "YES", "PASS", "PASSED", "CONFIRMED", "READY", "TRADE"}
    return bool(value)


def _current_stage_input(result: DecisionResult, lifecycle: dict[str, Any], market_data: dict[str, Any]) -> dict[str, Any]:
    e4 = _out(result, "E4")
    e6 = _out(result, "E6")
    e7 = _out(result, "E7")
    e8 = _out(result, "E8")
    e9 = _out(result, "E9")
    execution_geometry = e9.get("execution_geometry") if isinstance(e9.get("execution_geometry"), dict) else {}
    e4_state = _text(e4.get("auction_state") or e4.get("state"))
    e7_state = _text(e7.get("confirmation_state") or e7.get("confirmation") or e7.get("state"))
    e8_state = _text(e8.get("economic_state") or e8.get("risk_state") or (e8.get("profit_edge") or {}).get("state"))
    e9_decision = _text(e9.get("decision") or result.decision)
    geometry_state = _text(e9.get("opportunity_execution_state") or execution_geometry.get("state"))
    invalidation_reason = _text(e6.get("invalidation_reason") or e3_invalidation(e4, e6, _out(result, "E3")))
    candle = market_data.get("candle_close_timestamp") or market_data.get("candle")
    event_id = e4.get("event_id") or e4.get("auction_event_id") or lifecycle.get("event_id") or lifecycle.get("origin_event_id")
    return {
        "direction": _text(e6.get("direction") or e6.get("direction_thesis") or lifecycle.get("direction")),
        "candidate": _bool(e6.get("candidate_type") in {"OPPORTUNITY_CANDIDATE", "SETUP_CANDIDATE"}) or _bool(e6.get("watch_only")) or bool(lifecycle.get("opportunity_id")),
        "confirmed": e4_state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "RECLAIMED"},
        "e4_state": e4_state,
        "thesis_proven": _bool(e6.get("e6_thesis_proven")),
        "e7_confirmed": e7_state in {"PASS", "PASSED", "CONFIRMED", "TRIGGER_CONFIRMED"},
        "e7_confirmation_state": e7_state,
        "e8_ready": bool(_engine(result, "E8") and _engine(result, "E8").gate_passed) or e8_state in {"PASS", "PASSED", "READY", "APPROVED", "POSITIVE"},
        "e8_economic_state": e8_state,
        "e9_trade": e9_decision in {"BUY", "SELL", "TRADE"} and bool(result.gate_passed) and geometry_state not in {"TOO_LATE", "EXPIRED", "INVALID_GEOMETRY", "UNFAVORABLE_RR"},
        "execution_state": geometry_state or _text(lifecycle.get("execution_state")),
        "invalidated": _bool(e6.get("invalidated")) or _text(lifecycle.get("state")) == "INVALIDATED" or bool(invalidation_reason),
        "invalidation_reason": invalidation_reason,
        "event_id": event_id,
        "origin_event_id": lifecycle.get("origin_event_id") or event_id,
        "candle": candle,
    }


def e3_invalidation(e4: dict[str, Any], e6: dict[str, Any], e3: dict[str, Any]) -> str:
    if _text(e3.get("lifecycle")) == "INVALIDATED" or _bool(e3.get("structure_invalidated")) or _bool(e3.get("active_invalidation")):
        return _text(e3.get("invalidation") or e3.get("invalidation_reason") or "STRUCTURE_INVALIDATED")
    if _text(e4.get("lifecycle")) == "INVALIDATED":
        return _text(e4.get("invalidation_reason") or "AUCTION_INVALIDATED")
    return ""


def enrich(result: DecisionResult, market_data: dict[str, Any]) -> DecisionResult:
    e9_engine = _engine(result, "E9")
    if not e9_engine:
        return result
    e9 = dict(e9_engine.output or {})
    lifecycle = e9.get("opportunity_lifecycle") if isinstance(e9.get("opportunity_lifecycle"), dict) else {}
    current = _current_stage_input(result, lifecycle, market_data)
    progressed = advance_lifecycle_stage(lifecycle, current)
    progressed["opportunity_id"] = lifecycle.get("opportunity_id") or progressed.get("opportunity_id")
    progressed["event_id"] = progressed.get("event_id") or lifecycle.get("event_id") or current.get("event_id")
    progressed["origin_event_id"] = progressed.get("origin_event_id") or lifecycle.get("origin_event_id") or current.get("origin_event_id")
    progressed["direction"] = progressed.get("direction") or lifecycle.get("direction") or current.get("direction")
    progressed["e6_thesis_proven"] = bool(current.get("thesis_proven"))
    progressed["e7_confirmation_state"] = current.get("e7_confirmation_state") or "UNKNOWN"
    progressed["e8_economic_state"] = current.get("e8_economic_state") or "UNKNOWN"
    progressed["e9_final_decision"] = result.decision
    progressed["execution_geometry_state"] = current.get("execution_state") or "UNKNOWN"

    e9["opportunity_lifecycle"] = progressed
    e9["lifecycle_stage"] = progressed.get("lifecycle_stage")
    e9["lifecycle_stage_history"] = progressed.get("stage_history") or []
    e9["lifecycle_wait_for_stage"] = progressed.get("wait_for_stage")
    e9["lifecycle_terminal_state"] = progressed.get("terminal_stage")
    e9["lifecycle_terminal_reason"] = progressed.get("terminal_reason")
    engines = []
    for engine in result.engines:
        if engine.engine_id == "E9":
            engines.append(EngineResult(engine.engine_id, engine.name, engine.gate_passed, engine.score, e9, engine.reason_codes))
        else:
            engines.append(engine)

    risk = dict(result.risk or {})
    risk["opportunity_lifecycle"] = progressed
    risk["lifecycle_stage"] = progressed.get("lifecycle_stage")
    risk["lifecycle_stage_history"] = progressed.get("stage_history") or []
    risk["lifecycle_wait_for_stage"] = progressed.get("wait_for_stage")

    decision = result.decision
    gate = result.gate_passed
    if progressed.get("lifecycle_stage") in {"TOO_LATE", "EXPIRED", "INVALIDATED", "REPLACED"}:
        decision, gate = "NO_TRADE", False
    elif progressed.get("lifecycle_stage") == "TRADE":
        e9["execution_intent"] = "ORDER_INTENT"

    updated = DecisionResult(
        result.symbol,
        result.timeframe,
        decision,
        gate,
        result.score,
        tuple(engines),
        risk,
        tuple(dict.fromkeys(list(result.reason_codes) + ([f"LIFECYCLE_{progressed.get('lifecycle_stage')}" ] if progressed.get("lifecycle_stage") else []))),
        result.state,
        result.blocked_by,
        result.wait_bars,
        result.execution_state,
    )
    opportunity_memory.save(result.symbol, progressed)
    return updated


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_OPPORTUNITY_LIFECYCLE_PROGRESSION_INSTALLED", False):
        return
    original = pipeline_module.ProductionPipeline.run

    def wrapped(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
        result = original(self, market_data, wait_bars=wait_bars, resume_state=resume_state, historical_calibration=historical_calibration)
        return enrich(result, market_data)

    pipeline_module.ProductionPipeline.run = wrapped
    pipeline_module._OPPORTUNITY_LIFECYCLE_PROGRESSION_INSTALLED = True
