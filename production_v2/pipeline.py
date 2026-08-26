from __future__ import annotations

from typing import Any
import re

from .contracts import DecisionResult, EngineResult
from .professional_brain import run_professional_e9
from .engines import ENGINE_IDS, run_engine

ENGINE_ORDER = ENGINE_IDS


def _sanitize_directional_text(text: str) -> str:
    result = text
    for old, new in (("BUY", "TRADE_DECISION"), ("SELL", "TRADE_DECISION"), ("LONG", "UPSIDE_EXPOSURE"), ("SHORT", "DOWNSIDE_EXPOSURE")):
        result = re.sub(rf"(?<![A-Z0-9_]){old}(?![A-Z0-9_])", new, result)
    return re.sub(r"\b(?:DIRECTION|BIAS|ORIENTATION|MARKET_DIRECTION)\s*=\s*(?:UP|DOWN|BUY|SELL|BULLISH|BEARISH|LONG|SHORT)\b", "direction=UNRESOLVED", result, flags=re.IGNORECASE)


def _sanitize_specialist_value(value: Any) -> Any:
    if isinstance(value, dict):
        blocked = {"direction", "bias", "orientation", "market_direction", "decision", "score", "gate", "handoff"}
        return {k: _sanitize_specialist_value(v) for k, v in value.items() if str(k).lower() not in blocked}
    if isinstance(value, (list, tuple)):
        return [_sanitize_specialist_value(v) for v in value]
    if isinstance(value, str):
        return _sanitize_directional_text(value)
    return value


def _sanitize_engine_result(result: EngineResult) -> EngineResult:
    output = _sanitize_specialist_value(dict(result.output or {}))
    output.update({"trade_decision_authority": False, "specialist_gate": "NONE", "gate": None, "analysis_complete": True})
    return EngineResult(result.engine_id, result.name, None, result.score, output, result.reason_codes)


def _evidence_package(result: EngineResult) -> dict[str, Any]:
    return {
        "engine_id": result.engine_id,
        "name": result.name,
        "evidence": result.output,
        "reason_codes": list(result.reason_codes),
        "role": "INDEPENDENT_ENGINE_OUTPUT",
        "decision": None,
        "gate": None,
    }


def _trade_plan_complete(result: EngineResult | None, direction: str | None = None) -> bool:
    if result is None:
        return False
    output = result.output or {}
    plan = output.get("trade_plan")
    if not isinstance(plan, dict) and direction in {"BUY", "SELL"}:
        candidates = output.get("trade_plan_candidates")
        plan = candidates.get(direction) if isinstance(candidates, dict) else None
    if not isinstance(plan, dict):
        return False
    required = ("entry", "stop_loss", "take_profit_1", "take_profit_2", "rr_tp2")
    if any(plan.get(key) is None for key in required):
        return False
    try:
        return float(plan["rr_tp2"]) > 0
    except (TypeError, ValueError):
        return False


def _exact_tokens(value: Any) -> set[str]:
    return set(re.findall(r"(?<![A-Z0-9_])[A-Z][A-Z0-9_]*(?![A-Z0-9_])", str(value).upper()))


def _walk_tokens(value: Any):
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _walk_tokens(v)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _walk_tokens(item)
    elif value is not None:
        yield str(value)


def _specialist_has_negative_execution_state(e8: EngineResult | None) -> list[str]:
    if e8 is None:
        return ["E8_MISSING"]
    tokens = _exact_tokens(" ".join(_walk_tokens(e8.output)))
    blockers = []
    for token, reason in (("INVALIDATION_PENDING", "E8_INVALIDATION_NOT_DEFINED"), ("RISK_NOT_READY", "E8_RISK_NOT_READY"),
                          ("INCOMPLETE_PLAN", "E8_PLAN_INCOMPLETE"), ("EXECUTION_PLAN_NOT_READY", "E8_PLAN_INCOMPLETE"),
                          ("MISSING_PLAN", "E8_PLAN_MISSING"), ("INVALID_RR", "E8_INVALID_RR"), ("RR_BELOW_MINIMUM", "E8_INVALID_RR"),
                          ("INVALID_RISK", "E8_INVALID_RISK"), ("INVALID_RISK_GEOMETRY", "E8_INVALID_RISK"),
                          ("SUB_ENGINES_PAUSED", "E8_SUB_ENGINES_PAUSED")):
        if token in tokens and reason not in blockers:
            blockers.append(reason)
    return blockers


def _specialist_confirmation_ready(e7: EngineResult | None) -> bool:
    if e7 is None:
        return False
    tokens = _exact_tokens(" ".join(_walk_tokens(e7.output)))
    negative = {"NO_TRIGGER", "NO_FOLLOW_THROUGH", "WAIT", "CONFIRMATION_WAIT", "TRIGGER_NOT_OBSERVED", "CONFIRMATION_NOT_PROVEN", "QUALITY_NOT_PROVEN", "SUB_ENGINES_PAUSED"}
    positive = {"CONFIRMATION_PASS", "CONFIRMED", "FOLLOW_THROUGH_OBSERVED", "TRIGGER_OBSERVED"}
    return not (tokens & negative) and bool(tokens & positive)


def _specialist_setup_ready(e6: EngineResult | None) -> bool:
    if e6 is None:
        return False
    tokens = _exact_tokens(" ".join(_walk_tokens(e6.output)))
    return not (tokens & {"QUALITY_WEAK", "DEVELOPING", "SUB_ENGINES_PAUSED"}) and "MATURE" in tokens


def _enforce_e9_execution_invariant(e9: EngineResult, e8: EngineResult | None, e6: EngineResult | None = None, e7: EngineResult | None = None) -> EngineResult:
    output = dict(e9.output or {})
    reasoning = dict(output.get("professional_reasoning") or {})
    reasons = list(e9.reason_codes)
    direction = str(output.get("direction") or "").upper()
    e8_plan_ready = _trade_plan_complete(e8, direction)
    e9_plan_ready = _trade_plan_complete(e9, direction)
    blockers = _specialist_has_negative_execution_state(e8)
    confirmation_ready = _specialist_confirmation_ready(e7)
    setup_ready = _specialist_setup_ready(e6)
    if not e8_plan_ready:
        blockers.append("E8_PLAN_INCOMPLETE")
    if not e9_plan_ready:
        blockers.append("E9_PLAN_INCOMPLETE")
    if not confirmation_ready:
        blockers.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not setup_ready:
        blockers.append("SETUP_NOT_MATURE")
    blockers = sorted(set(blockers))
    contract_ready = bool(e8_plan_ready and e9_plan_ready and not blockers)
    if e9.gate_passed and contract_ready:
        return e9
    reasons.extend(x for x in blockers if x not in reasons)
    output.update({"decision": "NO_TRADE", "execution_readiness_score": 0.0, "decision_score": 0.0, "trade_plan": {},
                   "invariant_blocked": True, "invariant": "E9_EXECUTION_CONTRACT_NOT_READY", "trade_decision_authority": True,
                   "decision_authority": "E9", "gate": False})
    reasoning.update({"final_decision": "NO_TRADE", "execution_ready": False, "decision_authority": "E9",
                      "invariant": "E9_EXECUTION_CONTRACT_NOT_READY", "e8_plan_complete": e8_plan_ready,
                      "e9_plan_complete": e9_plan_ready, "setup_state": "MATURE" if setup_ready else "NOT_MATURE",
                      "confirmation_state": "CONFIRMED" if confirmation_ready else "NOT_CONFIRMED",
                      "execution_state": "READY" if contract_ready else "NOT_READY", "contract_blockers": blockers})
    output["professional_reasoning"] = reasoning
    return EngineResult("E9", e9.name, False, 0.0, output, tuple(sorted(set(reasons))))


class ProductionPipeline:
    ENGINE_ORDER = ENGINE_ORDER

    def run(self, market_data, *, wait_bars=0, resume_state=None, historical_calibration=None):
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        timeframe = str(market_data.get("timeframe") or "M5")
        snapshot = dict(market_data)

        # ONE WAVE ONLY. There is intentionally no peer re-analysis wave.
        # Every engine receives only raw market data. E1 is fully independent.
        baseline = {engine_id: run_engine(engine_id, snapshot, None) for engine_id in ENGINE_ORDER}
        internal_engines = [baseline[engine_id] for engine_id in ENGINE_ORDER]
        calibration = historical_calibration or snapshot.get("historical_calibration")
        e9 = run_professional_e9({**snapshot, "evidence_bus": {k: _evidence_package(v) for k, v in baseline.items()}}, internal_engines, calibration)
        e9 = _enforce_e9_execution_invariant(e9, baseline.get("E8"), baseline.get("E6"), baseline.get("E7"))

        engines = [_sanitize_engine_result(baseline[engine_id]) for engine_id in ENGINE_ORDER] + [e9]
        trade_plan = e9.output.get("trade_plan", {})
        final_gate = bool(e9.gate_passed and e9.output.get("decision") in {"BUY", "SELL"} and _trade_plan_complete(e9, e9.output.get("decision")))
        final_decision = e9.output.get("decision", "NO_TRADE") if final_gate else "NO_TRADE"
        return DecisionResult(
            symbol, timeframe, final_decision, final_gate, e9.score, tuple(engines),
            {
                "risk_gate": bool(trade_plan.get("valid")) if isinstance(trade_plan, dict) else False,
                "trade_plan": trade_plan,
                "engine_state": "TRADE_APPROVED" if final_gate else "ANALYSIS_COMPLETE_NO_TRADE",
                "blocked_by": None,
                "cycle_complete": True,
                "analysis_architecture": "INDEPENDENT_ENGINES -> E9",
                "sub_engines_enabled": False,
                "peer_reanalysis_enabled": False,
                "evidence_flow": {engine_id: [] for engine_id in ENGINE_ORDER},
                "learning_mode": "ADVISORY_ONLY",
                "next_evaluation": "NEXT_CLOSED_M5_CANDLE",
                "wait_bars": 0,
                "decision_reasons": list(e9.reason_codes),
                "evidence_score": None,
            },
            tuple(e9.reason_codes),
        )
