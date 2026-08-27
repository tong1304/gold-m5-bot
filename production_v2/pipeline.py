from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .engines import ENGINE_IDS, EVIDENCE_INPUTS, run_engine

ENGINE_ORDER = ENGINE_IDS


class ProductionPipeline:
    ENGINE_ORDER = ENGINE_ORDER

    def run(self, market_data: dict[str, Any], *, wait_bars=0, resume_state=None, historical_calibration=None):
        snapshot = dict(market_data)
        results: dict[str, EngineResult] = {}

        # One cognitive axis, but evidence flows only along declared relationships.
        for engine_id in ENGINE_ORDER:
            related = {
                source_id: results[source_id]
                for source_id in EVIDENCE_INPUTS.get(engine_id, ())
                if source_id in results
            }
            results[engine_id] = run_engine(engine_id, snapshot, related)

        e9 = results["E9"]
        plan = (e9.output.get("trade_plan") or {})
        approved = bool(
            e9.gate_passed
            and e9.output.get("decision") in {"BUY", "SELL"}
            and (plan.get("valid", True) if isinstance(plan, dict) else False)
        )
        decision = e9.output.get("decision") if approved else "NO_TRADE"
        engines = tuple(results[e] for e in ENGINE_ORDER)

        return DecisionResult(
            str(snapshot.get("symbol") or "UNKNOWN"),
            str(snapshot.get("timeframe") or "M5"),
            decision,
            approved,
            e9.score,
            engines,
            {
                "risk_gate": bool(plan.get("valid")) if isinstance(plan, dict) else False,
                "trade_plan": plan,
                "engine_state": "TRADE_APPROVED" if approved else "ANALYSIS_COMPLETE_NO_TRADE",
                "cycle_complete": True,
                "analysis_architecture": "ONE_BRAIN_AXIS + RELATION_BASED_EVIDENCE_FLOW",
                "evidence_inputs": {k: list(EVIDENCE_INPUTS.get(k, ())) for k in ENGINE_ORDER},
                "sub_engines": False,
                "parallel_peer_analysis": False,
                "e9_decision_authority": True,
                "learning_mode": "ADVISORY_ONLY",
                "next_evaluation": "NEXT_CLOSED_M5_CANDLE",
                "wait_bars": 0,
                "decision_reasons": list(e9.reason_codes),
            },
            tuple(e9.reason_codes),
        )
