from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .contracts import DecisionResult, EngineResult
from .professional_brain import run_professional_e9, run_professional_engine

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8")


class ProductionPipeline:
    ENGINE_ORDER = ENGINE_ORDER

    def run(
        self,
        market_data: dict[str, Any],
        *,
        wait_bars: int = 0,
        resume_state: dict[str, Any] | None = None,
        historical_calibration: dict[str, Any] | None = None,
    ) -> DecisionResult:
        """Run one closed-M5 decision cycle using a shared market snapshot.

        E1-E8 are independent specialist brains. They receive the same immutable
        market snapshot and analyze it in parallel. E9 is the sole final decision
        authority. Historical calibration is optional advisory evidence only.
        """
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        timeframe = str(market_data.get("timeframe") or "M5")
        snapshot = dict(market_data)
        engines_by_id: dict[str, EngineResult] = {}

        with ThreadPoolExecutor(max_workers=len(ENGINE_ORDER), thread_name_prefix="prod-v2-e") as pool:
            futures = {
                pool.submit(run_professional_engine, engine_id, snapshot): engine_id
                for engine_id in ENGINE_ORDER
            }
            for future in as_completed(futures):
                engine_id = futures[future]
                engines_by_id[engine_id] = future.result()

        engines = [engines_by_id[engine_id] for engine_id in ENGINE_ORDER]
        calibration = historical_calibration or snapshot.get("historical_calibration")
        e9 = run_professional_e9(snapshot, engines, calibration)
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
                "blocked_by": None,
                "cycle_complete": True,
                "analysis_architecture": "PARALLEL_E1_E8_SNAPSHOT_TO_E9",
                "learning_mode": "ADVISORY_ONLY",
                "next_evaluation": "NEXT_CLOSED_M5_CANDLE",
                "wait_bars": 0,
                "decision_reasons": list(e9.reason_codes),
                "evidence_score": e9.output.get("evidence_score", e9.score),
            },
            tuple(e9.reason_codes),
        )
