from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .e1_brain import analyze_e1
from .e2_brain import analyze_e2
from .e3_brain import analyze_e3
from .e4_brain import analyze_e4
from .e5_brain import analyze_e5
from .e6_brain import analyze_e6
from .e7_brain import analyze_e7
from .e8_brain import analyze_e8
from .e9_brain import analyze_e9
from .nine_brain_surgery import harden_engine
from .opportunity_layer import enrich_opportunity, recover_e9
from .professional_governance import audit_engines, enforce_final_authority
from .professional_opportunity import consolidate, enrich_engine
from .professional_brain_audit import audit_all
from .shared_market_picture import attach_brain_view, build_shared_market_picture

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")
EVIDENCE_INPUTS = {
    "E1": (), "E2": ("E1",), "E3": (), "E4": ("E1", "E3"),
    "E5": ("E1", "E3", "E4"), "E6": ("E1", "E2", "E3", "E4", "E5"),
    "E7": ("E4", "E6"), "E8": ("E5", "E6", "E7"),
    "E9": ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"),
}
NAMES = {
    "E1": "Market State Brain", "E2": "Opportunity / Regime Brain",
    "E3": "Market Structure Brain", "E4": "Liquidity Brain",
    "E5": "Location / Value Brain", "E6": "Setup Brain",
    "E7": "Confirmation Brain", "E8": "Trade Economics Brain", "E9": "Master Decision Brain",
}


def _dict_result(engine_id: str, output: dict[str, Any]) -> EngineResult:
    confidence = output.get("confidence", output.get("evidence_strength", 0.0))
    try:
        score = float(confidence) * 100.0
    except (TypeError, ValueError):
        score = 0.0
    reasons = output.get("reason_codes", output.get("reasons", output.get("conflicts", ())))
    if isinstance(reasons, dict):
        reasons = tuple(str(k) for k, v in reasons.items() if v)
    elif isinstance(reasons, str):
        reasons = (reasons,)
    else:
        reasons = tuple(str(x) for x in (reasons or ()))
    return EngineResult(engine_id, NAMES[engine_id], output.get("gate_passed"), score, output, reasons)


def _enrich(engine_id: str, result: EngineResult, snapshot: dict[str, Any]) -> EngineResult:
    output = enrich_opportunity(engine_id, result.output, snapshot)
    output = enrich_engine(engine_id, output)
    output = harden_engine(engine_id, output)
    shared = snapshot.get("shared_market_picture")
    if isinstance(shared, dict):
        output = attach_brain_view(engine_id, output, shared)
    return EngineResult(result.engine_id, result.name, result.gate_passed, result.score, output, result.reason_codes)


def _scalarize(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key}={_scalarize(child)}" for key, child in sorted(value.items(), key=lambda item: str(item[0])))
    if isinstance(value, (list, tuple, set)):
        return " ".join(_scalarize(child) for child in value)
    return str(value if value is not None else "").upper().strip()


def _prepare_e9_boundary(results: dict[str, EngineResult]) -> None:
    """Expose only current evidence to E9; preserve future failure rules separately."""
    for engine_id, engine in tuple(results.items()):
        if not engine or not isinstance(engine.output, dict):
            continue
        output = harden_engine(engine_id, dict(engine.output))
        output["invalidations"] = list(output.get("active_invalidations") or [])
        if engine_id == "E4":
            for key in ("event", "auction_event", "liquidity_event"):
                value = output.get(key)
                if isinstance(value, (dict, list, tuple, set)):
                    output.setdefault("event_detail", value)
                    output[key] = _scalarize(value)
        results[engine_id] = EngineResult(engine.engine_id, engine.name, engine.gate_passed, engine.score, output, engine.reason_codes)


class ProductionPipeline:
    ENGINE_ORDER = ENGINE_ORDER

    def run(self, market_data: dict[str, Any], *, wait_bars=0, resume_state=None, historical_calibration=None):
        del resume_state, historical_calibration
        snapshot = dict(market_data)
        bars = list(snapshot.get("bars") or [])

        # One factual market picture is frozen for the whole nine-brain cycle.
        # Brains may interpret it differently, but may not replace its facts.
        shared_picture = build_shared_market_picture(snapshot)
        snapshot["shared_market_picture"] = shared_picture
        results: dict[str, EngineResult] = {}

        e1 = _enrich("E1", _dict_result("E1", analyze_e1(bars)), snapshot)
        results["E1"] = e1

        e2_snapshot = dict(snapshot)
        e2_snapshot["E1_result"] = e1.output
        results["E2"] = _enrich("E2", _dict_result("E2", analyze_e2(e2_snapshot)), snapshot)
        results["E3"] = _enrich("E3", _dict_result("E3", analyze_e3(bars)), snapshot)
        results["E4"] = _enrich("E4", _dict_result("E4", analyze_e4(snapshot, results)), snapshot)
        results["E5"] = _enrich("E5", _dict_result("E5", analyze_e5(snapshot, results)), snapshot)
        results["E6"] = _enrich("E6", analyze_e6(snapshot, results), snapshot)
        results["E7"] = _enrich("E7", analyze_e7(snapshot, results), snapshot)
        results["E8"] = _enrich("E8", analyze_e8(snapshot, results), snapshot)

        _prepare_e9_boundary(results)
        try:
            e9 = _enrich("E9", analyze_e9(snapshot, results), snapshot)
        except Exception as exc:
            recovery = recover_e9(results)
            recovery["e9_exception_type"] = type(exc).__name__
            recovery["e9_exception"] = str(exc)
            recovered = _dict_result("E9", enrich_opportunity("E9", recovery, snapshot))
            recovered_output = harden_engine("E9", enrich_engine("E9", recovered.output))
            recovered_output = attach_brain_view("E9", recovered_output, shared_picture)
            e9 = EngineResult(recovered.engine_id, recovered.name, recovered.gate_passed, recovered.score, recovered_output, recovered.reason_codes)
        results["E9"] = e9

        audit = audit_all({engine_id: results[engine_id].output for engine_id in ENGINE_ORDER})
        for engine_id in ENGINE_ORDER:
            engine = results[engine_id]
            output = dict(engine.output)
            output["professional_audit"] = audit["per_engine"][engine_id]
            results[engine_id] = EngineResult(engine.engine_id, engine.name, engine.gate_passed, engine.score, output, engine.reason_codes)
        results["E9"] = EngineResult(
            results["E9"].engine_id,
            results["E9"].name,
            results["E9"].gate_passed,
            results["E9"].score,
            {**results["E9"].output, "nine_brain_audit": audit},
            results["E9"].reason_codes,
        )

        governance = audit_engines(results)
        decision, approved, governance_reasons = enforce_final_authority(results["E9"].output, governance)
        if governance_reasons:
            merged_reasons = tuple(dict.fromkeys((*results["E9"].reason_codes, *governance_reasons)))
            e9_output = harden_engine("E9", dict(results["E9"].output))
            e9_output["governance"] = governance
            e9_output["decision"] = decision
            e9_output["execution"] = "APPROVED" if approved else "BLOCKED"
            e9_output["governance_blockers"] = governance_reasons
            results["E9"] = EngineResult("E9", NAMES["E9"], False if not approved else results["E9"].gate_passed, results["E9"].score, e9_output, merged_reasons)

        e9 = results["E9"]
        plan = e9.output.get("trade_plan") or {}
        approved = bool(approved and e9.gate_passed and decision in {"BUY", "SELL"} and (plan.get("valid", True) if isinstance(plan, dict) else False))
        decision = decision if approved else "NO_TRADE"
        engines = tuple(results[e] for e in ENGINE_ORDER)
        radar = consolidate(results)
        risk = {
            "risk_gate": bool(plan.get("valid")) if isinstance(plan, dict) else False,
            "trade_plan": plan,
            "engine_state": "TRADE_APPROVED" if approved else "ANALYSIS_COMPLETE_NO_TRADE",
            "cycle_complete": True,
            "analysis_architecture": "SHARED_MARKET_PICTURE + ONE_BRAIN_PER_ENGINE + PROFESSIONAL_OPPORTUNITY_RADAR + NINE_BRAIN_GOVERNANCE",
            "shared_market_picture": shared_picture,
            "evidence_inputs": {k: list(EVIDENCE_INPUTS.get(k, ())) for k in ENGINE_ORDER},
            "sub_engines": False,
            "parallel_peer_analysis": False,
            "shared_picture_frozen_per_cycle": True,
            "brain_boundaries_explicit": True,
            "e9_decision_authority": True,
            "e9_market_control_authority": True,
            "nine_brain_governance": governance,
            "nine_brain_audit": audit,
            "learning_mode": "ADVISORY_ONLY",
            "next_evaluation": "NEXT_CLOSED_M5_CANDLE",
            "wait_bars": 0,
            "decision_reasons": list(e9.reason_codes),
            "opportunity_radar": radar,
            "opportunity_potential": audit["opportunity"],
            "opportunity_summary": {e: {"direction": results[e].output.get("opportunity_direction"), "state": results[e].output.get("opportunity_state"), "stage": results[e].output.get("opportunity_stage"), "score": results[e].output.get("opportunity_score"), "next_event": results[e].output.get("opportunity_next_event")} for e in ENGINE_ORDER},
        }
        return DecisionResult(str(snapshot.get("symbol") or "UNKNOWN"), str(snapshot.get("timeframe") or "M5"), decision, approved, e9.score, engines, risk, tuple(e9.reason_codes))
