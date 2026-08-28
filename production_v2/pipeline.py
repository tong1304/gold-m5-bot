from __future__ import annotations

from typing import Any

from .contracts import DecisionResult, EngineResult
from .e1_professional_layer_v5 import analyze_e1_professional_v5
from .e2_brain import analyze_e2
from .e3_brain import analyze_e3
from .e4_brain import analyze_e4
from .e5_brain import analyze_e5
from .e6_brain import analyze_e6
from .e7_brain import analyze_e7
from .e8_brain import analyze_e8
from .e9_brain import analyze_e9

ENGINE_ORDER = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")

EVIDENCE_INPUTS = {
    "E1": (),
    "E2": ("E1",),
    "E3": (),
    "E4": ("E1", "E3"),
    "E5": ("E1", "E3", "E4"),
    "E6": ("E1", "E2", "E3", "E4", "E5"),
    "E7": ("E4", "E6"),
    "E8": ("E5", "E6", "E7"),
    "E9": ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"),
}

NAMES = {
    "E1": "Market State Brain", "E2": "Opportunity / Regime Brain",
    "E3": "Market Structure Brain", "E4": "Liquidity Brain",
    "E5": "Location / Value Brain", "E6": "Setup Brain",
    "E7": "Confirmation Brain", "E8": "Trade Economics Brain",
    "E9": "Master Decision Brain",
}


def _dict_result(engine_id: str, output: dict[str, Any]) -> EngineResult:
    confidence = output.get("confidence", output.get("evidence_strength", 0.0))
    try:
        score = float(confidence) * 100.0
    except (TypeError, ValueError):
        score = 0.0
    reasons = output.get("reason_codes", output.get("reasons", output.get("conflicts", ())))
    return EngineResult(
        engine_id, NAMES[engine_id], output.get("gate_passed"), score, output,
        tuple(str(x) for x in (reasons or ())),
    )


class ProductionPipeline:
    ENGINE_ORDER = ENGINE_ORDER

    def run(self, market_data: dict[str, Any], *, wait_bars=0, resume_state=None, historical_calibration=None):
        snapshot = dict(market_data)
        bars = list(snapshot.get("bars") or [])
        results: dict[str, EngineResult] = {}

        # E1 is the sole market-state brain. V5 evidence arbitration is owned
        # by E1 and never creates setup, entry, risk or trade decisions.
        e1 = _dict_result("E1", analyze_e1_professional_v5(bars))
        results["E1"] = e1

        e2_snapshot = dict(snapshot)
        e2_snapshot["E1_result"] = e1.output
        results["E2"] = _dict_result("E2", analyze_e2(e2_snapshot))
        results["E3"] = _dict_result("E3", analyze_e3(bars))
        results["E4"] = _dict_result("E4", analyze_e4(snapshot, results))
        results["E5"] = _dict_result("E5", analyze_e5(snapshot, results))
        results["E6"] = analyze_e6(snapshot, results)
        results["E7"] = analyze_e7(snapshot, results)
        results["E8"] = analyze_e8(snapshot, results)
        results["E9"] = analyze_e9(snapshot, results)

        e9 = results["E9"]
        plan = e9.output.get("trade_plan") or {}
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
            decision, approved, e9.score, engines,
            {
                "risk_gate": bool(plan.get("valid")) if isinstance(plan, dict) else False,
                "trade_plan": plan,
                "engine_state": "TRADE_APPROVED" if approved else "ANALYSIS_COMPLETE_NO_TRADE",
                "cycle_complete": True,
                "analysis_architecture": "ONE_BRAIN_PER_ENGINE + DIRECT_ANALYZER_INVOCATION",
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
