from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .engines import run_e9_decision, run_engine


class ProductionPipeline:
    """Single production decision path: E1 -> E2 -> ... -> E9.

    Each engine consumes the shared Decision Context produced by upstream
    engines. A failed gate stops the decision path; no trade notification is
    emitted for NO_TRADE results.
    """

    ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")

    def run(self, market_data: dict[str, Any]) -> DecisionResult:
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        timeframe = str(market_data.get("timeframe") or "M5")
        context = dict(market_data)
        engines: list[EngineResult] = []

        for engine_id in self.ENGINE_ORDER:
            result = run_engine(engine_id, context)
            engines.append(result)
            context[f"{engine_id}_result"] = result.output
            if not result.gate_passed:
                e9 = EngineResult(
                    "E9", "Execution Decision Engine", False, result.score,
                    {
                        "decision": "NO_TRADE",
                        "blocked_by": engine_id,
                        "decision_authority": "E9",
                        "trade_plan": context.get("E8_result", {}).get("trade_plan", {}),
                    },
                    (f"{engine_id}_GATE_FAILED",),
                )
                engines.append(e9)
                return DecisionResult(
                    symbol, timeframe, "NO_TRADE", False, result.score,
                    tuple(engines),
                    {
                        "risk_gate": False,
                        "trade_plan": context.get("E8_result", {}).get("trade_plan", {}),
                    },
                    (f"{engine_id}_GATE_FAILED",),
                )

        e9 = run_e9_decision(context, engines)
        engines.append(e9)
        decision = e9.output.get("decision", "NO_TRADE")
        trade_plan = e9.output.get("trade_plan", {})
        return DecisionResult(
            symbol, timeframe, decision, e9.gate_passed, e9.score,
            tuple(engines),
            {
                "risk_gate": next(e.gate_passed for e in engines if e.engine_id == "E8"),
                "trade_plan": trade_plan,
            },
            tuple(e9.reason_codes),
        )
