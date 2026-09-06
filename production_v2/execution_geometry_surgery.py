from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .opportunity_execution import evaluate_execution_geometry


def _out(result: EngineResult | None) -> dict[str, Any]:
    return dict(result.output or {}) if result else {}


def _plan(e8: dict[str, Any]) -> dict[str, Any]:
    plan = e8.get("trade_plan")
    return plan if isinstance(plan, dict) else e8


def _event(e4: dict[str, Any]) -> str:
    return str(e4.get("event") or e4.get("event_type") or e4.get("auction_event") or "").upper().strip()


def _event_age(e4: dict[str, Any], lifecycle: dict[str, Any]) -> int:
    for value in (e4.get("event_age_bars"), lifecycle.get("bars_waited"), lifecycle.get("age_bars")):
        try:
            if value is not None:
                return max(0, int(value))
        except (TypeError, ValueError):
            pass
    return 0


def enrich(result: DecisionResult, market_data: dict[str, Any]) -> DecisionResult:
    engines = list(result.engines)
    e4 = _out(next((x for x in engines if x.engine_id == "E4"), None))
    e8_engine = next((x for x in engines if x.engine_id == "E8"), None)
    e9_engine = next((x for x in engines if x.engine_id == "E9"), None)
    e8 = _out(e8_engine); e9 = _out(e9_engine)
    lifecycle = e9.get("opportunity_lifecycle") if isinstance(e9.get("opportunity_lifecycle"), dict) else {}
    direction = str(result.decision or e9.get("decision") or lifecycle.get("direction") or "").upper().strip()
    if direction not in {"BUY", "SELL"}:
        direction = str(lifecycle.get("leader") or "").upper().strip()
    bars = list(market_data.get("bars") or [])
    current_price = bars[-1].get("close") if bars and isinstance(bars[-1], dict) else market_data.get("price")
    plan = _plan(e8)
    geometry = evaluate_execution_geometry(
        direction=direction,
        entry=plan.get("entry", plan.get("entry_price")),
        stop=plan.get("stop_loss", plan.get("stop")),
        target=plan.get("take_profit_2", plan.get("take_profit", plan.get("tp2"))),
        current_price=current_price,
        atr=plan.get("atr") or e8.get("atr") or e8.get("atr_value"),
        bars_since_event=_event_age(e4, lifecycle),
        event_type=_event(e4),
    )
    geometry["entry_classification"] = {
        "ACTIONABLE": "OPTIMAL_OR_ACCEPTABLE",
        "WAIT_ENTRY": "WAIT_FOR_BETTER_PRICE",
        "TOO_LATE": "DO_NOT_CHASE",
        "EXPIRED": "WAIT_FOR_NEW_CAUSAL_EVENT",
        "INVALID_GEOMETRY": "DO_NOT_TRADE",
        "UNFAVORABLE_RR": "WAIT_FOR_BETTER_GEOMETRY",
    }.get(geometry["state"], "WAIT")
    for i, engine in enumerate(engines):
        output = dict(engine.output or {})
        output["execution_geometry"] = geometry
        if engine.engine_id == "E9":
            output["opportunity_execution_state"] = geometry["state"]
            output["opportunity_thesis_status"] = geometry["thesis_status"]
            if geometry["state"] in {"TOO_LATE", "EXPIRED", "INVALID_GEOMETRY", "UNFAVORABLE_RR"} and result.decision in {"BUY", "SELL", "TRADE"}:
                output["decision"] = "NO_TRADE"
                output["trade_ready"] = False
                output["execution_blocked"] = True
                output["decision_reasons"] = list(dict.fromkeys(list(output.get("decision_reasons") or []) + [f"EXECUTION_GEOMETRY_{geometry['state']}"]))
                output["reason_codes"] = list(dict.fromkeys(list(output.get("reason_codes") or []) + [f"EXECUTION_GEOMETRY_{geometry['state']}" ]))
                engines[i] = EngineResult(engine.engine_id, engine.name, False, engine.score, output, tuple(dict.fromkeys(list(engine.reason_codes) + [f"EXECUTION_GEOMETRY_{geometry['state']}" ])))
                continue
        engines[i] = EngineResult(engine.engine_id, engine.name, engine.gate_passed, engine.score, output, engine.reason_codes)
    decision = result.decision
    gate = result.gate_passed
    if geometry["state"] in {"TOO_LATE", "EXPIRED", "INVALID_GEOMETRY", "UNFAVORABLE_RR"} and decision in {"BUY", "SELL", "TRADE"}:
        decision, gate = "NO_TRADE", False
    risk = dict(result.risk or {})
    risk["execution_geometry"] = geometry
    risk["opportunity_state"] = geometry["state"]
    return DecisionResult(result.symbol, result.timeframe, decision, gate, result.score, tuple(engines), risk, tuple(dict.fromkeys(list(result.reason_codes) + ([f"EXECUTION_GEOMETRY_{geometry['state']}"] if decision == "NO_TRADE" and geometry["state"] != "ACTIONABLE" else []))))


def install(pipeline_module: Any) -> None:
    if getattr(pipeline_module, "_EXECUTION_GEOMETRY_SURGERY_INSTALLED", False):
        return
    original = pipeline_module.ProductionPipeline.run
    def wrapped(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
        result = original(self, market_data, wait_bars=wait_bars, resume_state=resume_state, historical_calibration=historical_calibration)
        return enrich(result, market_data)
    pipeline_module.ProductionPipeline.run = wrapped
    pipeline_module._EXECUTION_GEOMETRY_SURGERY_INSTALLED = True
