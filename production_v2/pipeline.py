from __future__ import annotations
from typing import Any
from .contracts import DecisionResult
from .engines import ENGINE_IDS, run_engine

ENGINE_ORDER=ENGINE_IDS

class ProductionPipeline:
    ENGINE_ORDER=ENGINE_ORDER
    def run(self,market_data: dict[str, Any],*,wait_bars=0,resume_state=None,historical_calibration=None):
        snapshot=dict(market_data); results={}
        for engine_id in ENGINE_ORDER:
            results[engine_id]=run_engine(engine_id,snapshot,results)
        e9=results["E9"]
        plan=(e9.output.get("trade_plan") or {})
        approved=bool(e9.gate_passed and e9.output.get("decision") in {"BUY","SELL"} and plan.get("valid"))
        decision=e9.output.get("decision") if approved else "NO_TRADE"
        engines=tuple(results[e] for e in ENGINE_ORDER)
        return DecisionResult(
            str(snapshot.get("symbol") or "UNKNOWN"),str(snapshot.get("timeframe") or "M5"),decision,approved,e9.score,engines,
            {"risk_gate":bool(plan.get("valid")),"trade_plan":plan,"engine_state":"TRADE_APPROVED" if approved else "ANALYSIS_COMPLETE_NO_TRADE",
             "cycle_complete":True,"analysis_architecture":"SINGLE_AXIS: E1 -> E2 -> E3 -> E4 -> E5 -> E6 -> E7 -> E8 -> E9",
             "sub_engines":False,"parallel_peer_analysis":False,"learning_mode":"ADVISORY_ONLY","next_evaluation":"NEXT_CLOSED_M5_CANDLE","wait_bars":0,
             "decision_reasons":list(e9.reason_codes)},tuple(e9.reason_codes))
