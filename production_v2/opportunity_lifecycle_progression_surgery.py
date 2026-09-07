from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .opportunity_lifecycle_progression import advance_lifecycle_stage
from .trade_alert_boundary import build_trade_alert
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


def _symbol(result: DecisionResult, market_data: dict[str, Any], lifecycle: dict[str, Any]) -> str:
    return _text(market_data.get("symbol") or market_data.get("asset") or lifecycle.get("symbol") or getattr(result, "symbol", None)) or "UNKNOWN"


def lifecycle_telemetry(symbol: str, lifecycle: dict[str, Any]) -> str:
    terminal = _text(lifecycle.get("terminal_stage")) or "NONE"
    alert = _text((lifecycle.get("trade_alert") or {}).get("state")) or "NONE"
    return ("[PRODUCTION V2] OPPORTUNITY_LIFECYCLE " f"symbol={_text(symbol) or 'UNKNOWN'} " f"opportunity_id={lifecycle.get('opportunity_id') or 'NONE'} " f"origin_event_id={lifecycle.get('origin_event_id') or 'NONE'} " f"event_id={lifecycle.get('event_id') or 'NONE'} " f"candle={lifecycle.get('last_progression_candle') or lifecycle.get('last_evaluated_candle') or lifecycle.get('stage_candle') or 'NONE'} " f"stage={_text(lifecycle.get('lifecycle_stage')) or 'IDLE'} " f"state={_text(lifecycle.get('state')) or 'UNKNOWN'} " f"wait_for={_text(lifecycle.get('wait_for_stage')) or 'NONE'} " f"terminal={terminal} " f"alert={alert} " f"user_action={_text((lifecycle.get('trade_alert') or {}).get('user_action')) or 'NONE'}")


def _current_stage_input(result: DecisionResult, lifecycle: dict[str, Any], market_data: dict[str, Any]) -> dict[str, Any]:
    e3 = _out(result, "E3"); e4 = _out(result, "E4"); e6 = _out(result, "E6"); e7 = _out(result, "E7"); e8 = _out(result, "E8"); e9 = _out(result, "E9")
    geometry = e9.get("execution_geometry") if isinstance(e9.get("execution_geometry"), dict) else {}
    e4_state = _text(e4.get("auction_state") or e4.get("auction_phase") or e4.get("state"))
    e7_state = _text(e7.get("confirmation_state") or e7.get("confirmation") or e7.get("proof_state") or e7.get("trigger_state"))
    e8_state = _text(e8.get("economic_state") or e8.get("risk_state") or (e8.get("profit_edge") or {}).get("state"))
    e9_decision = _text(e9.get("decision") or result.decision)
    geometry_state = _text(e9.get("opportunity_execution_state") or geometry.get("state"))
    invalidation_reason = _text(e6.get("invalidation_reason")) or e3_invalidation(e4, e6, e3)
    candle = market_data.get("candle_close_timestamp") or market_data.get("current_candle_timestamp") or market_data.get("candle")
    event_id = e4.get("event_id") or e4.get("auction_event_id") or e4.get("event_candle_id") or lifecycle.get("event_id") or lifecycle.get("origin_event_id")
    origin_event_id = lifecycle.get("origin_event_id") or event_id
    direction = _text(e6.get("direction") or e6.get("direction_thesis") or e6.get("thesis_direction") or lifecycle.get("direction") or e4.get("direction") or e3.get("direction"))
    return {"symbol": _symbol(result, market_data, lifecycle), "direction": direction, "candidate": bool(lifecycle.get("opportunity_id")) or _bool(e6.get("watch_only")) or _text(e6.get("candidate_type")) in {"OPPORTUNITY_CANDIDATE", "SETUP_CANDIDATE"} or bool(event_id), "confirmed": e4_state in {"CONFIRMED", "TERMINALLY_CONFIRMED", "ACCEPTED", "RECLAIMED"}, "e4_state": e4_state, "thesis_proven": _bool(e6.get("e6_thesis_proven")) or _text(e6.get("thesis_state") or e6.get("maturity") or e6.get("setup_state")) in {"MATURE", "CONFIRMED", "VALIDATED", "TRADE_READY", "ESTABLISHED"}, "e7_confirmed": e7_state in {"PASS", "PASSED", "CONFIRMED", "TRIGGER_CONFIRMED", "PROVEN", "VALIDATED", "TRADE_READY"}, "e7_confirmation_state": e7_state, "e8_ready": bool(_engine(result, "E8") and _engine(result, "E8").gate_passed) or e8_state in {"PASS", "PASSED", "READY", "APPROVED", "POSITIVE", "RISK_READY", "ECONOMICALLY_ACCEPTABLE", "TRADE_READY"}, "e8_economic_state": e8_state, "e9_trade": e9_decision in {"BUY", "SELL", "TRADE"} and bool(result.gate_passed) and geometry_state not in {"TOO_LATE", "EXPIRED", "INVALID_GEOMETRY", "UNFAVORABLE_RR"}, "execution_state": geometry_state or _text(lifecycle.get("execution_state")), "invalidated": _bool(e6.get("invalidated")) or _text(lifecycle.get("state")) == "INVALIDATED" or bool(invalidation_reason), "invalidation_reason": invalidation_reason, "event_id": event_id, "origin_event_id": origin_event_id, "candle": candle}


def e3_invalidation(e4: dict[str, Any], e6: dict[str, Any], e3: dict[str, Any]) -> str:
    if _text(e3.get("lifecycle")) == "INVALIDATED" or _bool(e3.get("structure_invalidated")) or _bool(e3.get("active_invalidation")): return _text(e3.get("invalidation") or e3.get("invalidation_reason") or "STRUCTURE_INVALIDATED")
    if _text(e4.get("lifecycle")) == "INVALIDATED": return _text(e4.get("invalidation_reason") or "AUCTION_INVALIDATED")
    if _text(e6.get("lifecycle_state")) == "INVALIDATED": return _text(e6.get("invalidation_reason") or "E6_THESIS_INVALIDATED")
    return ""


def _direction_item(lifecycle: dict[str, Any], direction: str) -> dict[str, Any]:
    opportunities = lifecycle.get("opportunities") if isinstance(lifecycle.get("opportunities"), dict) else {}
    item = opportunities.get(direction)
    return dict(item) if isinstance(item, dict) else dict(lifecycle)


def _write_direction_item(lifecycle: dict[str, Any], direction: str, item: dict[str, Any]) -> dict[str, Any]:
    updated = dict(lifecycle); opportunities = dict(updated.get("opportunities") or {}) if isinstance(updated.get("opportunities"), dict) else {}; opportunities[direction] = dict(item); updated["opportunities"] = opportunities; return updated


def enrich(result: DecisionResult, market_data: dict[str, Any]) -> DecisionResult:
    e9_engine = _engine(result, "E9")
    if not e9_engine: return result
    e9 = dict(e9_engine.output or {}); lifecycle = e9.get("opportunity_lifecycle") if isinstance(e9.get("opportunity_lifecycle"), dict) else {}; symbol = _symbol(result, market_data, lifecycle); current = _current_stage_input(result, lifecycle, market_data); direction = current.get("direction") or _text(lifecycle.get("direction")); previous_item = _direction_item(lifecycle, direction) if direction in {"BUY", "SELL"} else dict(lifecycle); progressed = advance_lifecycle_stage(previous_item, current)
    progressed["symbol"] = symbol; progressed["opportunity_id"] = previous_item.get("opportunity_id") or lifecycle.get("opportunity_id") or progressed.get("opportunity_id"); progressed["event_id"] = progressed.get("event_id") or previous_item.get("event_id") or lifecycle.get("event_id") or current.get("event_id"); progressed["origin_event_id"] = progressed.get("origin_event_id") or previous_item.get("origin_event_id") or lifecycle.get("origin_event_id") or current.get("origin_event_id"); progressed["direction"] = progressed.get("direction") or previous_item.get("direction") or lifecycle.get("direction") or direction
    progressed["e6_thesis_proven"] = bool(current.get("thesis_proven")); progressed["e7_confirmation_state"] = current.get("e7_confirmation_state") or "UNKNOWN"; progressed["e8_economic_state"] = current.get("e8_economic_state") or "UNKNOWN"; progressed["e9_final_decision"] = result.decision; progressed["execution_geometry_state"] = current.get("execution_state") or "UNKNOWN"
    lifecycle = _write_direction_item(lifecycle, direction, progressed) if direction in {"BUY", "SELL"} else progressed; lifecycle["symbol"] = symbol; lifecycle["lifecycle_stage"] = progressed.get("lifecycle_stage"); lifecycle["lifecycle_stage_history"] = progressed.get("stage_history") or []; lifecycle["lifecycle_wait_for_stage"] = progressed.get("wait_for_stage"); lifecycle["lifecycle_terminal_state"] = progressed.get("terminal_stage"); lifecycle["lifecycle_terminal_reason"] = progressed.get("terminal_reason")
    lifecycle["execution_candidate"] = {"direction": direction, "opportunity_id": progressed.get("opportunity_id"), "state": progressed.get("state"), "lifecycle_stage": progressed.get("lifecycle_stage"), "selected_by": "E9" if progressed.get("lifecycle_stage") == "TRADE" else "OPPORTUNITY_LIFECYCLE"}
    lifecycle["execution_boundary_state"] = "NONE"
    lifecycle["execution_boundary_history"] = []
    lifecycle["execution_authorized_by"] = None
    alert = build_trade_alert(result, progressed)
    lifecycle["trade_alert"] = alert
    e9["opportunity_lifecycle"] = lifecycle; e9["lifecycle_stage"] = progressed.get("lifecycle_stage"); e9["lifecycle_stage_history"] = progressed.get("stage_history") or []; e9["lifecycle_wait_for_stage"] = progressed.get("wait_for_stage"); e9["lifecycle_terminal_state"] = progressed.get("terminal_stage"); e9["lifecycle_terminal_reason"] = progressed.get("terminal_reason"); e9["opportunity_symbol"] = symbol; e9["execution_boundary_state"] = "NONE"; e9["execution_boundary_history"] = []; e9["trade_alert"] = alert
    if progressed.get("lifecycle_stage") == "TRADE": e9["execution_intent"] = None
    engines = [EngineResult(e.engine_id, e.name, e.gate_passed, e.score, e9 if e.engine_id == "E9" else e.output, e.reason_codes) for e in result.engines]
    risk = dict(result.risk or {}); risk["opportunity_lifecycle"] = lifecycle; risk["lifecycle_stage"] = progressed.get("lifecycle_stage"); risk["lifecycle_stage_history"] = progressed.get("stage_history") or []; risk["lifecycle_wait_for_stage"] = progressed.get("wait_for_stage"); risk["opportunity_symbol"] = symbol; risk["execution_boundary_state"] = "NONE"; risk["execution_boundary_history"] = []; risk["trade_alert"] = alert
    decision = result.decision; gate = result.gate_passed
    if progressed.get("lifecycle_stage") in {"TOO_LATE", "EXPIRED", "INVALIDATED", "REPLACED"}: decision, gate = "NO_TRADE", False
    updated = DecisionResult(symbol, result.timeframe, decision, gate, result.score, tuple(engines), risk, tuple(dict.fromkeys(list(result.reason_codes) + ([f"LIFECYCLE_{progressed.get('lifecycle_stage')}"] if progressed.get("lifecycle_stage") else []))), result.state, result.blocked_by, result.wait_bars, {"state": "NOT_REQUESTED", "order_id": None, "position_id": None, "error": None})
    opportunity_memory.save(symbol, lifecycle); print(lifecycle_telemetry(symbol, progressed), flush=True); return updated


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_OPPORTUNITY_LIFECYCLE_PROGRESSION_INSTALLED", False): return
    original = pipeline_module.ProductionPipeline.run
    def wrapped(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
        result = original(self, market_data, wait_bars=wait_bars, resume_state=resume_state, historical_calibration=historical_calibration); updated = enrich(result, market_data); lifecycle = dict(updated.risk.get("opportunity_lifecycle") or {}); symbol = str(market_data.get("symbol") or market_data.get("asset") or updated.symbol or "UNKNOWN").upper();
        if lifecycle: self._opportunity_lifecycle[symbol] = lifecycle
        return updated
    pipeline_module.ProductionPipeline.run = wrapped; pipeline_module._OPPORTUNITY_LIFECYCLE_PROGRESSION_INSTALLED = True
    print("[PRODUCTION V2] OPPORTUNITY_LIFECYCLE_PROGRESSION_BINDING stages=WATCH>CONFIRMED>E6_THESIS>E7_CONFIRMED>E8_READY>TRADE terminals=TOO_LATE|EXPIRED|INVALIDATED alert=TRADE_ALERT>USER_ACTION_REQUIRED", flush=True)
