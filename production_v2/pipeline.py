from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .engines import run_e9_decision, run_engine

# Every closed M5 candle is a fresh decision cycle.
# There is intentionally no WAIT state in the trading decision vocabulary.
HARD_FAIL_REASONS = {
    "E1_DATA_INVALID",
    "E3_STRUCTURE_INVALIDATED",
    "E5_LOCATION_DISADVANTAGED",
    "E5_SPACE_INSUFFICIENT",
    "E5_CHASING_PRICE",
    "E6_SETUP_INVALIDATED",
    "E7_CONFIRMATION_INVALIDATED",
    "E8_RISK_PLAN_INVALID",
    "E8_RISK_GATE_NOT_READY",
    "E8_RR_BELOW_MINIMUM",
    "E8_STOP_TOO_WIDE",
    "STOP_TOO_WIDE_FOR_SHORT_TERM",
}

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")
ENGINE_INDEX = {engine_id: i for i, engine_id in enumerate(ENGINE_ORDER)}


def resolve_engine_state(gate_passed: bool, reason_codes: tuple[str, ...] = (), *, score: float | None = None) -> str:
    """Only PASS/FAIL exists. A failed engine starts a new cycle on the next candle."""
    return "PASS" if gate_passed else "FAIL"


def _structure_signature(result: EngineResult | None) -> tuple[Any, ...] | None:
    if result is None:
        return None
    output = result.output or {}
    return (
        output.get("3B", {}).get("state"),
        output.get("3C", {}).get("state"),
        output.get("3F", {}).get("state"),
        output.get("3B", {}).get("direction"),
        output.get("3F", {}).get("direction"),
    )


class ProductionPipeline:
    ENGINE_ORDER = ENGINE_ORDER

    def _blocked_result(self, symbol: str, timeframe: str, result: EngineResult, context: dict[str, Any], engines: list[EngineResult]) -> DecisionResult:
        reason = f"{result.engine_id}_GATE_FAILED"
        e9 = EngineResult(
            "E9", "Execution Decision Engine", False, result.score,
            {
                "decision": "NO_TRADE",
                "decision_authority": "E9",
                "blocked_by": result.engine_id,
                "engine_state": "FAIL",
                "cycle_complete": True,
                "next_evaluation": "NEXT_CLOSED_M5_CANDLE",
                "trade_plan": context.get("E8_result", {}).get("trade_plan", {}),
            },
            (reason,),
        )
        engines.append(e9)
        return DecisionResult(
            symbol, timeframe, "NO_TRADE", False, result.score, tuple(engines),
            {
                "risk_gate": False,
                "trade_plan": context.get("E8_result", {}).get("trade_plan", {}),
                "engine_state": "FAIL",
                "blocked_by": result.engine_id,
                "cycle_complete": True,
                "next_evaluation": "NEXT_CLOSED_M5_CANDLE",
            },
            (reason,),
        )

    def _run_from(self, market_data: dict[str, Any], *, start_engine: str, engines: list[EngineResult]) -> DecisionResult:
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        timeframe = str(market_data.get("timeframe") or "M5")
        context = dict(market_data)
        start_index = ENGINE_INDEX[start_engine]
        for cached in engines:
            context[f"{cached.engine_id}_result"] = cached.output

        for engine_id in ENGINE_ORDER[start_index:]:
            result = run_engine(engine_id, context)
            engines[:] = [e for e in engines if e.engine_id != engine_id]
            engines.append(result)
            context[f"{engine_id}_result"] = result.output
            if not result.gate_passed:
                return self._blocked_result(symbol, timeframe, result, context, engines)

        e9 = run_e9_decision(context, engines)
        engines[:] = [e for e in engines if e.engine_id != "E9"]
        engines.append(e9)
        decision = e9.output.get("decision", "NO_TRADE")
        return DecisionResult(
            symbol, timeframe, decision, e9.gate_passed, e9.score, tuple(engines),
            {
                "risk_gate": next(e.gate_passed for e in engines if e.engine_id == "E8"),
                "trade_plan": e9.output.get("trade_plan", {}),
                "engine_state": "PASS" if e9.gate_passed else "FAIL",
                "cycle_complete": True,
                "next_evaluation": "NEXT_CLOSED_M5_CANDLE",
            },
            tuple(e9.reason_codes),
        )

    def run(self, market_data: dict[str, Any], *, wait_bars: int = 0, resume_state: dict[str, Any] | None = None) -> DecisionResult:
        # Legacy resume state is deliberately ignored: every closed candle is a new
        # full E1->E9 analysis cycle. This prevents stale WAIT/cached decisions from
        # carrying into a new market state.
        return self._run_from(market_data, start_engine="E1", engines=[])
