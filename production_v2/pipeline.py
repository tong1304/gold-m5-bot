from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .contracts import DecisionResult, EngineResult
from .professional_brain import run_professional_e9
from .engines import ENGINE_IDS, EVIDENCE_INPUTS, run_engine


ENGINE_ORDER = ENGINE_IDS


def _run_wave(engine_ids: tuple[str, ...], snapshot: dict[str, Any], evidence_bus: dict[str, Any] | None) -> dict[str, EngineResult]:
    """Run specialist engines concurrently against one immutable evidence snapshot."""
    results: dict[str, EngineResult] = {}
    with ThreadPoolExecutor(max_workers=len(engine_ids), thread_name_prefix="prod-v2-specialist") as pool:
        futures = {
            pool.submit(run_engine, engine_id, snapshot, evidence_bus): engine_id
            for engine_id in engine_ids
        }
        for future in as_completed(futures):
            engine_id = futures[future]
            results[engine_id] = future.result()
    return results


def _evidence_package(result: EngineResult) -> dict[str, Any]:
    return {
        "engine_id": result.engine_id,
        "name": result.name,
        "score": float(result.score),
        "evidence": result.output,
        "reason_codes": list(result.reason_codes),
        # Specialist decisions/gates are intentionally never propagated.
        "decision": None,
        "gate": None,
    }


def _e8_trade_plan_complete(e8: EngineResult | None) -> bool:
    """Return True only for a fully verified E8 execution plan.

    This is a pipeline-level safety invariant. E9 may synthesize and decide,
    but it may never approve an actionable trade when E8 has not supplied the
    complete trade economics and risk readiness required for execution.
    """
    if e8 is None:
        return False
    output = e8.output or {}
    plan = output.get("trade_plan")
    if not isinstance(plan, dict):
        return False
    required = ("entry", "stop_loss", "take_profit_1", "take_profit_2", "rr_tp2")
    if any(plan.get(key) is None for key in required):
        return False
    try:
        if float(plan["rr_tp2"]) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    risk_gate = str(output.get("risk_gate", "")).upper().strip()
    return risk_gate in {"RISK_READY", "PASS", "READY", "TRUE"}


def _enforce_e9_execution_invariant(e9: EngineResult, e8: EngineResult | None) -> EngineResult:
    """Hard-stop any E9 approval that lacks an independently verified E8 plan."""
    if not e9.gate_passed or _e8_trade_plan_complete(e8):
        return e9

    output = dict(e9.output or {})
    reasoning = dict(output.get("professional_reasoning") or {})
    reasons = list(e9.reason_codes)
    if "E8_TRADE_PLAN_INCOMPLETE" not in reasons:
        reasons.append("E8_TRADE_PLAN_INCOMPLETE")
    if "E9_EXECUTION_INVARIANT_BLOCK" not in reasons:
        reasons.append("E9_EXECUTION_INVARIANT_BLOCK")

    output.update({
        "decision": "NO_TRADE",
        "execution_readiness_score": 0.0,
        "decision_score": 0.0,
        "trade_plan": {},
        "invariant_blocked": True,
        "invariant": "E8_TRADE_PLAN_REQUIRED",
    })
    reasoning.update({
        "final_decision": "NO_TRADE",
        "execution_ready": False,
        "decision_authority": "E9",
        "invariant": "E8_TRADE_PLAN_REQUIRED",
    })
    output["professional_reasoning"] = reasoning
    return EngineResult(
        e9.engine_id,
        e9.name,
        False,
        0.0,
        output,
        tuple(reasons),
    )


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
        """Run one closed-M5 cycle with parallel peer analysis and E9 synthesis.

        Pass 1: E1-E8 independently analyze the market snapshot in parallel.
        Pass 2: every E1-E8 independently re-analyzes the same snapshot while
        reading the immutable peer evidence from Pass 1. Peer decisions and
        gates are stripped from the evidence bus, so no specialist can become
        a gatekeeper or inherit another specialist's authority.
        E9 then receives only the final specialist evidence packages and is the
        sole trade-decision authority.
        """
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        timeframe = str(market_data.get("timeframe") or "M5")
        snapshot = dict(market_data)

        baseline = _run_wave(ENGINE_ORDER, snapshot, None)
        baseline_bus = {engine_id: _evidence_package(result) for engine_id, result in baseline.items()}

        # Each specialist receives every other specialist's baseline evidence.
        # The engine-level dependency map controls which peer observations are
        # visible; no peer decision or gate is ever transmitted.
        enriched: dict[str, EngineResult] = {}
        with ThreadPoolExecutor(max_workers=len(ENGINE_ORDER), thread_name_prefix="prod-v2-peer") as pool:
            futures = {}
            for engine_id in ENGINE_ORDER:
                peer_bus = {k: v for k, v in baseline_bus.items() if k in EVIDENCE_INPUTS[engine_id]}
                futures[pool.submit(run_engine, engine_id, snapshot, peer_bus)] = engine_id
            for future in as_completed(futures):
                engine_id = futures[future]
                enriched[engine_id] = future.result()

        engines = [enriched[engine_id] for engine_id in ENGINE_ORDER]
        calibration = historical_calibration or snapshot.get("historical_calibration")
        e9 = run_professional_e9(
            {**snapshot, "evidence_bus": {k: _evidence_package(v) for k, v in enriched.items()}},
            engines,
            calibration,
        )

        # Hard invariant at the final authority boundary. Even if a future
        # E9 implementation accidentally reports gate=True, E9 cannot approve
        # a trade without a complete E8 trade plan.
        e9 = _enforce_e9_execution_invariant(e9, enriched.get("E8"))

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
                "analysis_architecture": "PARALLEL_BASELINE -> PARALLEL_PEER_REANALYSIS -> E9",
                "evidence_flow": {k: list(EVIDENCE_INPUTS.get(k, ())) for k in ENGINE_ORDER},
                "learning_mode": "ADVISORY_ONLY",
                "next_evaluation": "NEXT_CLOSED_M5_CANDLE",
                "wait_bars": 0,
                "decision_reasons": list(e9.reason_codes),
                "evidence_score": e9.output.get("evidence_score", e9.score),
            },
            tuple(e9.reason_codes),
        )
