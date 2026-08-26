from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .engines import run_e9_decision, run_engine

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")


class ProductionPipeline:
    ENGINE_ORDER = ENGINE_ORDER

    def run(self, market_data: dict[str, Any], *, wait_bars: int = 0, resume_state: dict[str, Any] | None = None) -> DecisionResult:
        """One closed M5 candle is one complete E1->E9 decision cycle.

        No WAIT/resume state is carried between candles. Every engine receives the
        answers from engines before it and gets an opportunity to produce evidence.
        E9 is the only final decision authority.
        """
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        timeframe = str(market_data.get("timeframe") or "M5")
        context = dict(market_data)
        engines: list[EngineResult] = []

        for engine_id in ENGINE_ORDER:
            result = run_engine(engine_id, context)
            engines.append(result)
            context[f"{engine_id}_result"] = result.output

        e9 = run_e9_decision(context, engines)
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
                "risk_gate": next((e.gate_passed for e in engines if e.engine_id == "E8"), False),
                "trade_plan": trade_plan,
                "engine_state": "PASS" if e9.gate_passed else "FAIL",
                "blocked_by": e9.output.get("blocked_by"),
                "cycle_complete": True,
                "next_evaluation": "NEXT_CLOSED_M5_CANDLE",
                "wait_bars": 0,
            },
            tuple(e9.reason_codes),
        )
