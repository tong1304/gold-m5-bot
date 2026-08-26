from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .contracts import DecisionResult, EngineResult
from .professional_brain import run_professional_e9
from .engines import EVIDENCE_INPUTS, run_engine

# Engines in the same wave are independent of each other.
# Later waves receive immutable evidence packages from the Evidence Bus.
ANALYSIS_WAVES = (
    ("E1", "E3"),
    ("E4",),
    ("E2", "E5"),
    ("E6",),
    ("E7",),
    ("E8",),
)
ENGINE_ORDER = tuple(e for wave in ANALYSIS_WAVES for e in wave)


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
        """Run one closed-M5 cycle through the controlled Evidence Bus.

        E1/E3 are roots. E4/E2/E5/E6/E7/E8 receive only explicitly permitted
        evidence packages. No engine receives another engine's final decision.
        E9 receives the complete evidence set and is the sole decision authority.
        """
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        timeframe = str(market_data.get("timeframe") or "M5")
        snapshot = dict(market_data)
        engines_by_id: dict[str, EngineResult] = {}
        evidence_bus: dict[str, Any] = {}

        for wave in ANALYSIS_WAVES:
            with ThreadPoolExecutor(max_workers=len(wave), thread_name_prefix="prod-v2-wave") as pool:
                futures = {
                    pool.submit(run_engine, engine_id, snapshot, evidence_bus): engine_id
                    for engine_id in wave
                }
                for future in as_completed(futures):
                    engine_id = futures[future]
                    result = future.result()
                    engines_by_id[engine_id] = result
                    evidence_bus[engine_id] = {
                        "engine_id": result.engine_id,
                        "name": result.name,
                        "score": float(result.score),
                        "evidence": result.output,
                        "reason_codes": list(result.reason_codes),
                        "decision": None,
                        "gate": None,
                    }

        engines = [engines_by_id[engine_id] for engine_id in ENGINE_ORDER]
        calibration = historical_calibration or snapshot.get("historical_calibration")
        e9 = run_professional_e9(
            {**snapshot, "evidence_bus": evidence_bus},
            engines,
            calibration,
        )
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
                "risk_gate": bool(trade_plan.get("valid")),
                "trade_plan": trade_plan,
                "engine_state": "TRADE_APPROVED" if e9.gate_passed else "ANALYSIS_COMPLETE_NO_TRADE",
                "blocked_by": None,
                "cycle_complete": True,
                "analysis_architecture": "CONTROLLED_EVIDENCE_BUS:E1-E8->E9",
                "evidence_flow": {k: list(EVIDENCE_INPUTS.get(k, ())) for k in ENGINE_ORDER},
                "learning_mode": "ADVISORY_ONLY",
                "next_evaluation": "NEXT_CLOSED_M5_CANDLE",
                "wait_bars": 0,
                "decision_reasons": list(e9.reason_codes),
                "evidence_score": e9.output.get("evidence_score", e9.score),
            },
            tuple(e9.reason_codes),
        )
