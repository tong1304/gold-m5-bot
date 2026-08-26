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
        futures = {pool.submit(run_engine, engine_id, snapshot, evidence_bus): engine_id for engine_id in engine_ids}
        for future in as_completed(futures):
            engine_id = futures[future]
            results[engine_id] = future.result()
    return results


def _evidence_package(result: EngineResult) -> dict[str, Any]:
    """Publish specialist reasoning only; no score, decision or gate is a decision input."""
    return {
        "engine_id": result.engine_id,
        "name": result.name,
        "evidence": result.output,
        "reason_codes": list(result.reason_codes),
        "role": "SPECIALIST_EVIDENCE_ONLY",
        "decision": None,
        "gate": None,
    }


def _normalize_e8_execution_boundary(e8: EngineResult | None) -> EngineResult | None:
    """Expose E8 risk observations without making E8 a trade decision authority."""
    if e8 is None:
        return None
    output = dict(e8.output or {})
    specialists = output.get("specialists") or {}
    risk_specialist = specialists.get("8G") if isinstance(specialists, dict) else None
    risk_output = risk_specialist.get("output") if isinstance(risk_specialist, dict) else None
    if isinstance(risk_output, dict):
        for key in ("trade_plan", "plan_status", "risk_gate", "risk_basis"):
            if key in risk_output:
                output[key] = risk_output[key]
    # Explicitly prevent E8 from publishing a BUY/SELL decision or direction.
    output["direction"] = None
    output["decision"] = None
    output["trade_decision_authority"] = False
    output["specialist_gate"] = "NONE"
    return EngineResult(e8.engine_id, e8.name, None, e8.score, output, e8.reason_codes)


def _e8_trade_plan_complete(e8: EngineResult | None) -> bool:
    if e8 is None:
        return False
    plan = (e8.output or {}).get("trade_plan")
    if not isinstance(plan, dict):
        return False
    required = ("entry", "stop_loss", "take_profit_1", "take_profit_2", "rr_tp2")
    if any(plan.get(key) is None for key in required):
        return False
    try:
        return float(plan["rr_tp2"]) > 0
    except (TypeError, ValueError):
        return False


def _enforce_e9_execution_invariant(e9: EngineResult, e8: EngineResult | None) -> EngineResult:
    """Execution incompleteness produces NO_TRADE, never a runtime exception."""
    if not e9.gate_passed or _e8_trade_plan_complete(e8):
        return e9
    output = dict(e9.output or {})
    reasoning = dict(output.get("professional_reasoning") or {})
    reasons = list(e9.reason_codes)
    diagnostic = "EXECUTION_PLAN_NOT_READY"
    if "E9_EXECUTION_NOT_READY" not in reasons:
        reasons.append("E9_EXECUTION_NOT_READY")
    if diagnostic not in reasons:
        reasons.append(diagnostic)
    output.update({
        "decision": "NO_TRADE",
        "execution_readiness_score": 0.0,
        "decision_score": 0.0,
        "trade_plan": {},
        "invariant_blocked": True,
        "invariant": "E9_EXECUTION_NOT_READY",
    })
    reasoning.update({
        "final_decision": "NO_TRADE",
        "execution_ready": False,
        "decision_authority": "E9",
        "invariant": "E9_EXECUTION_NOT_READY",
    })
    output["professional_reasoning"] = reasoning
    return EngineResult(e9.engine_id, e9.name, False, 0.0, output, tuple(reasons))


class ProductionPipeline:
    ENGINE_ORDER = ENGINE_ORDER

    def run(self, market_data: dict[str, Any], *, wait_bars: int = 0, resume_state: dict[str, Any] | None = None, historical_calibration: dict[str, Any] | None = None) -> DecisionResult:
        symbol = str(market_data.get("symbol") or "UNKNOWN")
        timeframe = str(market_data.get("timeframe") or "M5")
        snapshot = dict(market_data)

        baseline = _run_wave(ENGINE_ORDER, snapshot, None)
        baseline_bus = {engine_id: _evidence_package(result) for engine_id, result in baseline.items()}

        enriched: dict[str, EngineResult] = {}
        with ThreadPoolExecutor(max_workers=len(ENGINE_ORDER), thread_name_prefix="prod-v2-peer") as pool:
            futures = {}
            for engine_id in ENGINE_ORDER:
                peer_bus = {k: v for k, v in baseline_bus.items() if k in EVIDENCE_INPUTS[engine_id]}
                futures[pool.submit(run_engine, engine_id, snapshot, peer_bus)] = engine_id
            for future in as_completed(futures):
                engine_id = futures[future]
                enriched[engine_id] = future.result()

        normalized_e8 = _normalize_e8_execution_boundary(enriched.get("E8"))
        if normalized_e8 is not None:
            enriched["E8"] = normalized_e8

        engines = [enriched[engine_id] for engine_id in ENGINE_ORDER]
        calibration = historical_calibration or snapshot.get("historical_calibration")
        e9 = run_professional_e9(
            {**snapshot, "evidence_bus": {k: _evidence_package(v) for k, v in enriched.items()}},
            engines,
            calibration,
        )
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
