from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
import re

from .contracts import DecisionResult, EngineResult
from .professional_brain import run_professional_e9
from .engines import ENGINE_IDS, EVIDENCE_INPUTS, run_engine

ENGINE_ORDER = ENGINE_IDS
_DIRECTION_WORDS = {"BUY":"UP","SELL":"DOWN","LONG":"UP","SHORT":"DOWN"}
_DIRECTION_KEYS = {"direction","bias","orientation","market_direction"}
_DECISION_KEYS = {"decision","trade_decision"}


def _sanitize_directional_text(text: str) -> str:
    """Remove execution semantics while preserving market-direction semantics.

    Specialist evidence may describe directional market evidence as UP/DOWN. The
    previous sanitizer converted DIRECTION/BIASES to UNRESOLVED, so authoritative
    E1 direction was lost after the peer-analysis pass. Only execution vocabulary
    is normalized now; analytical direction is retained.
    """
    result = text
    for old, new in sorted(_DIRECTION_WORDS.items(), key=lambda item: -len(item[0])):
        result = re.sub(rf"(?<![A-Z0-9_]){re.escape(old)}(?![A-Z0-9_])", new, result, flags=re.IGNORECASE)
    return result


def _sanitize_specialist_value(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for k, v in value.items():
            lk = str(k).lower()
            if lk in _DECISION_KEYS or lk in {"decision_score", "score", "gate", "gate_passed", "specialist_gate", "handoff"}:
                continue
            # Direction is analytical evidence, not an execution decision.
            if lk in _DIRECTION_KEYS and isinstance(v, str):
                v = _sanitize_directional_text(v)
            cleaned[k] = _sanitize_specialist_value(v, lk)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_sanitize_specialist_value(v, key) for v in value]
    if isinstance(value, str):
        return _sanitize_directional_text(value)
    return value


def _sanitize_specialist_result(result: EngineResult) -> EngineResult:
    output = _sanitize_specialist_value(dict(result.output or {}))
    output.update({"trade_decision_authority":False,"specialist_gate":"NONE","gate":None,"reasoning_role":"SPECIALIST_EVIDENCE","analysis_complete":True})
    return EngineResult(result.engine_id,result.name,None,None,output,result.reason_codes)


def _run_wave(engine_ids,snapshot,evidence_bus):
    results={}
    with ThreadPoolExecutor(max_workers=len(engine_ids),thread_name_prefix="prod-v2-specialist") as pool:
        futures={pool.submit(run_engine,e,snapshot,evidence_bus):e for e in engine_ids}
        for future in as_completed(futures): results[futures[future]]=future.result()
    return results


def _evidence_package(result):
    return {"engine_id":result.engine_id,"name":result.name,"evidence":result.output,"reason_codes":list(result.reason_codes),"role":"SPECIALIST_EVIDENCE_ONLY","decision":None,"gate":None}


def _normalize_e8_execution_boundary(e8):
    if e8 is None: return None
    output=dict(e8.output or {}); specialists=output.get("specialists") or {}; risk_specialist=specialists.get("8G") if isinstance(specialists,dict) else None; risk_output=risk_specialist.get("output") if isinstance(risk_specialist,dict) else None
    if isinstance(risk_output,dict):
        for key in ("trade_plan","trade_plan_candidates","candidate_errors","plan_status","risk_gate","risk_basis","direction","direction_source","peer_direction_score"):
            if key in risk_output: output[key]=risk_output[key]
    output.update({"decision":None,"trade_decision_authority":False,"specialist_gate":"NONE"})
    return EngineResult(e8.engine_id,e8.name,None,e8.score,output,e8.reason_codes)


def _trade_plan_complete(result: EngineResult | None, direction: str | None = None) -> bool:
    if result is None: return False
    output=result.output or {}; plan=output.get("trade_plan")
    if not isinstance(plan,dict) and direction in {"BUY","SELL"}:
        candidates=output.get("trade_plan_candidates")
        plan=candidates.get(direction) if isinstance(candidates,dict) else None
    if not isinstance(plan,dict): return False
    required=("entry","stop_loss","take_profit_1","take_profit_2","rr_tp2")
    if any(plan.get(k) is None for k in required): return False
    try: return float(plan["rr_tp2"])>0
    except (TypeError,ValueError): return False


def _exact_tokens(value):
    return set(re.findall(r"(?<![A-Z0-9_])[A-Z][A-Z0-9_]*(?![A-Z0-9_])",str(value).upper()))


def _walk_tokens(value):
    if isinstance(value,dict):
        for k,v in value.items(): yield str(k); yield from _walk_tokens(v)
    elif isinstance(value,(list,tuple,set)):
        for item in value: yield from _walk_tokens(item)
    elif value is not None: yield str(value)


def _specialist_has_negative_execution_state(e8):
    if e8 is None: return ["E8_MISSING"]
    tokens=_exact_tokens(" ".join(_walk_tokens(e8.output))); blockers=[]
    for token,reason in (("INVALIDATION_PENDING","E8_INVALIDATION_NOT_DEFINED"),("RISK_NOT_READY","E8_RISK_NOT_READY"),("NO_RISK_READY","E8_RISK_NOT_READY"),("INCOMPLETE_PLAN","E8_PLAN_INCOMPLETE"),("EXECUTION_PLAN_NOT_READY","E8_PLAN_INCOMPLETE"),("MISSING_PLAN","E8_PLAN_MISSING"),("INVALID_RR","E8_INVALID_RR"),("RR_BELOW_MINIMUM","E8_INVALID_RR"),("INVALID_RISK","E8_INVALID_RISK"),("INVALID_RISK_GEOMETRY","E8_INVALID_RISK")):
        if token in tokens and reason not in blockers: blockers.append(reason)
    return blockers


def _specialist_confirmation_ready(e7):
    if e7 is None: return False
    tokens=_exact_tokens(" ".join(_walk_tokens(e7.output))); negative={"NO_TRIGGER","NO_FOLLOW_THROUGH","WAIT","CONFIRMATION_WAIT","TRIGGER_NOT_OBSERVED","CONFIRMATION_NOT_PROVEN","QUALITY_NOT_PROVEN"}; positive={"CONFIRMATION_PASS","CONFIRMED","FOLLOW_THROUGH_OBSERVED","TRIGGER_OBSERVED"}
    return not (tokens&negative) and bool(tokens&positive)


def _specialist_setup_ready(e6):
    if e6 is None: return False
    tokens=_exact_tokens(" ".join(_walk_tokens(e6.output))); return not (tokens&{"QUALITY_WEAK","DEVELOPING"}) and "MATURE" in tokens


def _enforce_e9_execution_invariant(e9,e8,e6=None,e7=None):
    output=dict(e9.output or {}); reasoning=dict(output.get("professional_reasoning") or {}); reasons=list(e9.reason_codes); direction=str(output.get("direction") or "").upper()
    e8_plan_ready=_trade_plan_complete(e8,direction); e9_plan_ready=_trade_plan_complete(e9,direction); e8_blockers=_specialist_has_negative_execution_state(e8); confirmation_ready=_specialist_confirmation_ready(e7); setup_ready=_specialist_setup_ready(e6)
    if not e8_plan_ready: e8_blockers.append("E8_PLAN_INCOMPLETE")
    if not e9_plan_ready: e8_blockers.append("E9_PLAN_INCOMPLETE")
    if not confirmation_ready: e8_blockers.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    if not setup_ready: e8_blockers.append("SETUP_NOT_MATURE")
    e8_blockers=sorted(set(e8_blockers)); contract_ready=bool(e8_plan_ready and e9_plan_ready and not e8_blockers)
    if e9.gate_passed and contract_ready: return e9
    for diagnostic in e8_blockers or ["E9_EXECUTION_NOT_READY"]:
        if diagnostic not in reasons: reasons.append(diagnostic)
    output.update({"decision":"NO_TRADE","execution_readiness_score":0.0,"decision_score":0.0,"trade_plan":{},"invariant_blocked":True,"invariant":"E9_EXECUTION_CONTRACT_NOT_READY","trade_decision_authority":True,"decision_authority":"E9","gate":False})
    reasoning.update({"final_decision":"NO_TRADE","execution_ready":False,"decision_authority":"E9","invariant":"E9_EXECUTION_CONTRACT_NOT_READY","e8_plan_complete":e8_plan_ready,"e9_plan_complete":e9_plan_ready,"setup_state":"MATURE" if setup_ready else "NOT_MATURE","confirmation_state":"CONFIRMED" if confirmation_ready else "NOT_CONFIRMED","execution_state":"READY" if contract_ready else "NOT_READY","contract_blockers":e8_blockers})
    output["professional_reasoning"]=reasoning
    return EngineResult("E9",e9.name,False,0.0,output,tuple(sorted(set(reasons))))


class ProductionPipeline:
    ENGINE_ORDER=ENGINE_ORDER
    def run(self,market_data,*,wait_bars=0,resume_state=None,historical_calibration=None):
        symbol=str(market_data.get("symbol") or "UNKNOWN"); timeframe=str(market_data.get("timeframe") or "M5"); snapshot=dict(market_data)
        baseline=_run_wave(ENGINE_ORDER,snapshot,None); baseline_bus={e:_evidence_package(r) for e,r in baseline.items()}; enriched={}
        with ThreadPoolExecutor(max_workers=len(ENGINE_ORDER),thread_name_prefix="prod-v2-peer") as pool:
            futures={pool.submit(run_engine,e,snapshot,{k:v for k,v in baseline_bus.items() if k in EVIDENCE_INPUTS[e]}):e for e in ENGINE_ORDER}
            for future in as_completed(futures): enriched[futures[future]]=future.result()
        normalized_e8=_normalize_e8_execution_boundary(enriched.get("E8"))
        if normalized_e8 is not None: enriched["E8"]=normalized_e8
        internal_engines=[enriched[e] for e in ENGINE_ORDER]; calibration=historical_calibration or snapshot.get("historical_calibration")
        e9=run_professional_e9({**snapshot,"evidence_bus":{k:_evidence_package(v) for k,v in enriched.items()}},internal_engines,calibration)
        e9=_enforce_e9_execution_invariant(e9,enriched.get("E8"),enriched.get("E6"),enriched.get("E7"))
        engines=[_sanitize_specialist_result(enriched[e]) for e in ENGINE_ORDER]+[e9]; trade_plan=e9.output.get("trade_plan",{}); final_gate=bool(e9.gate_passed and e9.output.get("decision") in {"BUY","SELL"} and _trade_plan_complete(e9,e9.output.get("decision"))); final_decision=e9.output.get("decision","NO_TRADE") if final_gate else "NO_TRADE"
        return DecisionResult(symbol,timeframe,final_decision,final_gate,e9.score,tuple(engines),{"risk_gate":bool(trade_plan.get("valid")) if isinstance(trade_plan,dict) else False,"trade_plan":trade_plan,"engine_state":"TRADE_APPROVED" if final_gate else "ANALYSIS_COMPLETE_NO_TRADE","blocked_by":None,"cycle_complete":True,"analysis_architecture":"PARALLEL_BASELINE -> PARALLEL_PEER_REANALYSIS -> E9","evidence_flow":{k:list(EVIDENCE_INPUTS.get(k,())) for k in ENGINE_ORDER},"learning_mode":"ADVISORY_ONLY","next_evaluation":"NEXT_CLOSED_M5_CANDLE","wait_bars":0,"decision_reasons":list(e9.reason_codes),"evidence_score":None},tuple(e9.reason_codes))
