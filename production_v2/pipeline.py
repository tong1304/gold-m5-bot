from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .professional_brain import run_professional_e9, run_professional_engine

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")


class ProductionPipeline:
    ENGINE_ORDER = ENGINE_ORDER

    def run(self, market_data: dict[str, Any], *, wait_bars: int = 0, resume_state: dict[str, Any] | None = None) -> DecisionResult:
        """Run one complete closed-M5 professional decision cycle.

        Every candle starts a fresh E1->E9 cycle. E1-E8 are specialist analysts:
        each receives all prior evidence, answers its own question, and hands its
        conclusion forward. Their conclusions do not themselves approve/reject
        a trade. E9 alone decides BUY, SELL, or NO_TRADE.
        """
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        timeframe = str(market_data.get("timeframe") or "M5")
        context = dict(market_data)
        engines: list[EngineResult] = []

        for engine_id in ENGINE_ORDER:
            result = run_professional_engine(engine_id, context)
            engines.append(result)
            context[f"{engine_id}_result"] = result.output

        e9 = run_professional_e9(context, engines)
        engines.append(e9)
        trade_plan = e9.output.get("trade_plan", {})
        return DecisionResult(
            symbol,
            timeframe,
            e9.output.get("decision", "NO_TRADE"),
            e9.gate_passed,
            e9.score,
            tuple(engines),
            {
                "risk_gate": bool(e9.output.get("trade_plan", {}).get("valid")),
                "trade_plan": trade_plan,
                "engine_state": "TRADE_APPROVED" if e9.gate_passed else "ANALYSIS_COMPLETE_NO_TRADE",
                "blocked_by": e9.output.get("blocked_by"),
                "cycle_complete": True,
                "next_evaluation": "NEXT_CLOSED_M5_CANDLE",
                "wait_bars": 0,
                "decision_reasons": list(e9.reason_codes),
                "evidence_score": e9.output.get("evidence_score", e9.score),
            },
            tuple(e9.reason_codes),
        )
