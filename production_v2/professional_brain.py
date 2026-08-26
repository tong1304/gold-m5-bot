from __future__ import annotations

import re
from typing import Any

from .contracts import EngineResult
from .e9_learning import build_advisory
from .engines import ENGINE_NAMES, run_engine as _engine_analyzer

SPECIALIST_QUESTIONS = {"E1":"What market state is present right now?","E2":"What opportunity/regime is the market offering?","E3":"What does market structure say?","E4":"Where is liquidity and what did price do with it?","E5":"Is current price in an advantageous location?","E6":"What setup, if any, is forming?","E7":"Is the setup thesis confirmed by price action?","E8":"What are the trade economics, invalidation and asymmetry?"}
EVIDENCE_WEIGHTS = {"E1":1.0,"E2":1.0,"E3":1.2,"E4":1.15,"E5":1.1,"E6":1.2,"E7":1.3,"E8":1.25}
DIRECTIONS = {"BUY","SELL"}


def run_professional_engine(engine_id: str, context: dict[str, Any]) -> EngineResult:
    raw = _engine_analyzer(engine_id, dict(context)); output = dict(raw.output)
    normalized_direction = _structured_direction(raw)
    if normalized_direction in DIRECTIONS:
        output["direction"] = normalized_direction
        output["evidence_direction"] = normalized_direction
    output.update({"analysis_status":"COMPLETE","analysis_complete":True,"specialist_question":SPECIALIST_QUESTIONS.get(engine_id),"trade_decision_authority":False,"specialist_gate":"NONE","gate":None,"reasoning_role":"SPECIALIST_EVIDENCE"})
    return EngineResult(raw.engine_id, raw.name, None, raw.score, output, raw.reason_codes)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float: return max(lo, min(hi, float(value)))
def _text(value: Any) -> str: return str(value).upper()
def _has(blob: str, *terms: str) -> bool: return any(term in blob for term in terms)


def _walk(value: Any):
    if isinstance(value, dict):
        for key, item in value.items(): yield str(key); yield from _walk(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value: yield from _walk(item)
    else: yield str(value)


def _blob(engine: EngineResult | None) -> str: return " | ".join(_text(x) for x in _walk(engine.output)) if engine else ""
def _exact(engine: EngineResult | None, token: str) -> bool: return bool(re.search(rf"(?<![A-Z0-9_]){re.escape(token)}(?![A-Z0-9_])", _blob(engine)))


def _find_key(value: Any, keys: set[str]):
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in keys: return item
            found = _find_key(item, keys)
            if found is not None: return found
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            found = _find_key(item, keys)
            if found is not None: return found
    return None


def _state_values(engine: EngineResult | None) -> set[str]:
    if not engine: return set()
    values=set(); tracked={"state","direction","evidence_direction","bias","orientation","market_direction","classification","regime","setup","confirmation","trigger_state","confirmation_state","follow_through_state","risk_gate","phase"}
    def rec(value):
        if isinstance(value, dict):
            for key,item in value.items():
                if str(key).lower() in tracked and isinstance(item,(str,int,float,bool)): values.add(_text(item).strip())
                rec(item)
        elif isinstance(value,(list,tuple,set)):
            for item in value: rec(item)
    rec(engine.output); return values


def _direction_hints(engine: EngineResult | None) -> set[str]:
    states=_state_values(engine); blob=_blob(engine); hints=set()
    for state in states:
        if state in {"UP","BULLISH","LONG","BUY","TREND_UP","BULLISH_BOS","STRUCTURAL_DISCOUNT","LIQUIDITY_ABOVE"}: hints.add("BUY")
        if state in {"DOWN","BEARISH","SHORT","SELL","TREND_DOWN","BEARISH_BOS","STRUCTURAL_PREMIUM","LIQUIDITY_BELOW"}: hints.add("SELL")
    if re.search(r"TREND[_ ]?UP|DIRECTION\s*[=:]\s*UP|STRUCTURE\s*[=:]\s*UP|BULLISH", blob): hints.add("BUY")
    if re.search(r"TREND[_ ]?DOWN|DIRECTION\s*[=:]\s*DOWN|STRUCTURE\s*[=:]\s*DOWN|BEARISH", blob): hints.add("SELL")
    return hints


def _structured_direction(engine: EngineResult | None) -> str | None:
    if not engine: return None
    value=_find_key(engine.output,{"direction","bias","orientation","market_direction","evidence_direction"})
    if isinstance(value,str):
        value=_text(value).strip()
        if value in DIRECTIONS: return value
        if value in {"BULLISH","UP","LONG","TREND_UP"}: return "BUY"
        if value in {"BEARISH","DOWN","SHORT","TREND_DOWN"}: return "SELL"
    hints=_direction_hints(engine); return next(iter(hints)) if len(hints)==1 else None


def _direction(evidence: dict[str, EngineResult]) -> str:
    buy=sell=0.0
    for engine in evidence.values():
        hints=_direction_hints(engine); weight=EVIDENCE_WEIGHTS.get(engine.engine_id,1.0)
        if len(hints)==1:
            buy += weight if "BUY" in hints else 0.0; sell += weight if "SELL" in hints else 0.0
        else:
            direction=_structured_direction(engine)
            if direction=="BUY": buy+=weight
            elif direction=="SELL": sell+=weight
    return "BUY" if buy>sell else "SELL" if sell>buy else "NEUTRAL"


def _weighted_alignment(upstream):
    weights=[EVIDENCE_WEIGHTS.get(e.engine_id,1.0) for e in upstream]; total=sum(weights)
    return round(sum(_clamp(e.score)*w for e,w in zip(upstream,weights))/total,2) if total else 0.0


def _dimension_state(by):
    blobs={k:_blob(by.get(k)) for k in SPECIALIST_QUESTIONS}; states={k:_state_values(by.get(k)) for k in SPECIALIST_QUESTIONS}
    return {"market_context":bool(blobs["E1"] or blobs["E2"]),"structure_support":bool(states["E3"]&{"BULLISH","BEARISH","ALIGNED","STRONG","MODERATE"}) or _has(blobs["E3"],"BOS","BREAK_OF_STRUCTURE","HIGHER_HIGH","LOWER_LOW"),"liquidity_event":bool(states["E4"]&{"SWEEP_HIGH","SWEEP_LOW","REJECTION","ACCEPTANCE","RECLAIM","HIGH_QUALITY"}) or _has(blobs["E4"],"SWEEP","RECLAIM","REJECTION","LIQUIDITY"),"location_quality":bool(states["E5"]&{"LOCATION_QUALITY_PASS","DISCOUNT","PREMIUM","EQUILIBRIUM","SPACE_AVAILABLE"}) or _has(blobs["E5"],"ADVANTAGEOUS","FAVORABLE","DISCOUNT","PREMIUM","GOOD_LOCATION"),"setup_mature":bool(states["E6"]&{"MATURE"}) or _has(blobs["E6"],"MATURE","VALID_SETUP","CONTINUATION_SETUP","REVERSAL_SETUP"),"trigger_observed":bool(states["E7"]&{"TRIGGER_OBSERVED","FOLLOW_THROUGH_OBSERVED"}) or _has(blobs["E7"],"TRIGGER_OBSERVED","FOLLOW_THROUGH"),"confirmation":bool(states["E7"]&{"CONFIRMATION_PASS","CONFIRMED"}) or _has(blobs["E7"],"CONFIRMED","CONFIRMATION_PASS"),"economics":bool(states["E8"]&{"RISK_READY","RR_OK","POSITIVE_EXPECTANCY","ATTRACTIVE","RISK_CANDIDATES_READY"}) or _has(blobs["E8"],"ATTRACTIVE","RISK_GATE_READY","RR_OK","POSITIVE_EXPECTANCY","CANDIDATES_READY")}


def _conflicts(by):
    conflicts=[]
    for first,second,code in (("E1","E3","E1_E3_DIRECTION_CONFLICT"),("E6","E7","E6_E7_DIRECTION_CONFLICT")):
        d1,d2=_structured_direction(by.get(first)),_structured_direction(by.get(second))
        if d1 and d2 and d1!=d2: conflicts.append(code)
    return conflicts


def _hard_invalidations(by):
    invalidations=[]
    for engine_id in ("E3","E6","E7","E8"):
        if any(_exact(by.get(engine_id),t) for t in ("INVALIDATED","HARD_INVALIDATION","STRUCTURE_INVALIDATED","SETUP_INVALIDATED")): invalidations.append(f"{engine_id}_THESIS_INVALIDATED")
    if any(_exact(by.get("E8"),t) for t in ("INVALID_RISK","INVALID_RISK_GEOMETRY","NEGATIVE_RR","RR_BELOW_MINIMUM")): invalidations.append("E8_RISK_GEOMETRY_INVALID")
    return sorted(set(invalidations))


def _validate_execution_plan(plan, output, *, candidate: bool):
    required=("entry","stop_loss","take_profit_1","take_profit_2","rr_tp2")
    if not isinstance(plan,dict) or any(plan.get(k) is None for k in required): return {"ready":False,"state":"INCOMPLETE","reasons":["EXECUTION_PLAN_NOT_READY"],"plan":None,"risk_basis":"INCOMPLETE_PLAN"}
    try: rr=float(plan["rr_tp2"])
    except (TypeError,ValueError): return {"ready":False,"state":"INVALID","reasons":["E8_INVALID_RR"],"plan":None,"risk_basis":"INVALID_RR"}
    if rr<=0: return {"ready":False,"state":"INVALID","reasons":["E8_INVALID_RR"],"plan":None,"risk_basis":"INVALID_RR"}
    risk_gate=_text(output.get("risk_gate", "")).strip()
    if risk_gate not in {"RISK_READY","PASS","READY","TRUE","RISK_CANDIDATES_READY"}: return {"ready":False,"state":"NOT_READY","reasons":["EXECUTION_RISK_NOT_READY"],"plan":None,"risk_basis":"RISK_NOT_READY"}
    return {"ready":True,"state":"READY","reasons":[],"plan":plan,"risk_basis":"E8_VERIFIED_CANDIDATE" if candidate else "E8_VERIFIED_PLAN"}


def _execution_readiness(by,direction):
    if direction not in DIRECTIONS: return {"ready":False,"state":"NO_DIRECTION","reasons":["NO_ACTIONABLE_DIRECTION"],"plan":None,"risk_basis":"UNRESOLVED"}
    e8=by.get("E8")
    if not e8: return {"ready":False,"state":"MISSING","reasons":["E8_MISSING"],"plan":None,"risk_basis":"MISSING"}
    output=e8.output or {}; plan=_find_key(output,{"trade_plan"})
    if isinstance(plan,dict): return _validate_execution_plan(plan,output,candidate=False)
    candidates=_find_key(output,{"trade_plan_candidates"})
    if isinstance(candidates,dict) and isinstance(candidates.get(direction),dict): return _validate_execution_plan(candidates[direction],output,candidate=True)
    return {"ready":False,"state":"INCOMPLETE","reasons":["EXECUTION_PLAN_NOT_READY"],"plan":None,"risk_basis":"MISSING_PLAN"}


def _independent_setup_maturity(by,direction):
    """Require E6 to explicitly declare a mature setup before E9 calls it mature.

    Structure and location are supporting evidence, not substitutes for setup maturity.
    A forming/developing setup must remain non-mature even when E3/E5 are strong.
    """
    e3,e5,e6,e7=by.get("E3"),by.get("E5"),by.get("E6"),by.get("E7")
    structure=bool(e3 and (e3.score>=60 or _has(_blob(e3),"BOS","BREAK_OF_STRUCTURE","HIGHER_HIGH","LOWER_HIGH","LOWER_LOW","BULLISH","BEARISH")))
    location=bool(e5 and (e5.score>=60 or _has(_blob(e5),"ADVANTAGEOUS","FAVORABLE","DISCOUNT","PREMIUM","SPACE_AVAILABLE","GOOD_LOCATION")))
    setup_mature=bool(e6 and _has(_blob(e6),"MATURE"))
    setup_evidence=bool(e6 and (_has(_blob(e6),"VALID_SETUP","CONTINUATION_SETUP","REVERSAL_SETUP","SETUP_FORMING","MATURE") or e6.score>=60))
    trigger=bool(e7 and _has(_blob(e7),"TRIGGER_OBSERVED","FOLLOW_THROUGH_OBSERVED"))
    confirmation=bool(e7 and (e7.score>=60 or _has(_blob(e7),"CONFIRMED","CONFIRMATION_PASS")))
    supporting=sum((structure,location,setup_evidence))
    mature=direction in DIRECTIONS and setup_mature and structure and location and not _has(_blob(e6),"INVALIDATED","SETUP_INVALIDATED","HARD_INVALIDATION")
    if mature:
        state="MATURE"
    elif setup_evidence and supporting>=2:
        state="DEVELOPING"
    elif setup_evidence or supporting>=1:
        state="FORMING"
    else:
        state="UNRESOLVED"
    return {"state":state,"mature":mature,"structure":structure,"location":location,"setup_evidence":setup_evidence,"explicit_e6_maturity":setup_mature,"trigger":trigger,"confirmation":confirmation,"supporting_dimensions":supporting}


def _confirmation_state(engine):
    if not engine: return "UNRESOLVED"
    states=_state_values(engine); blob=_blob(engine)
    if _has(blob,"HARD_INVALIDATION","THESIS_INVALIDATED","CONFIRMATION_FAILED","TRIGGER_FAILED"): return "FAILED"
    if "CONFIRMED" in states or "CONFIRMATION_PASS" in states or _has(blob,"CONFIRMED","CONFIRMATION_PASS"): return "CONFIRMED"
    if "TRIGGER_OBSERVED" in states or "FOLLOW_THROUGH_OBSERVED" in states or _has(blob,"TRIGGER_OBSERVED","FOLLOW_THROUGH_OBSERVED"): return "WAIT"
    return "UNRESOLVED"


def _engine_theses(by):
    result={}
    for engine_id in SPECIALIST_QUESTIONS:
        engine=by.get(engine_id); result[engine_id]={"direction":_structured_direction(engine) or "NEUTRAL","score":round(float(engine.score),2) if engine else 0.0,"state":sorted(_state_values(engine))[:8],"reason_codes":list(engine.reason_codes) if engine else [],"analyst_conclusion":(_find_key(engine.output,{"conclusion"}) if engine else None) or "UNRESOLVED","role":SPECIALIST_QUESTIONS[engine_id]}
    return result


def run_professional_e9(context,upstream,historical_calibration=None):
    by={engine.engine_id:engine for engine in upstream}; direction=_direction(by); dimensions=_dimension_state(by); conflicts=_conflicts(by); invalidations=_hard_invalidations(by); alignment=_weighted_alignment(upstream); execution=_execution_readiness(by,direction); setup=_independent_setup_maturity(by,direction); theses=_engine_theses(by)
    e7_confirmation=_confirmation_state(by.get("E7")); dimensions["confirmation"]=e7_confirmation=="CONFIRMED"; dimensions["trigger_observed"]=e7_confirmation=="WAIT" or dimensions["trigger_observed"]
    thesis_quality=0.0 if direction=="NEUTRAL" else round(_clamp(alignment+sum(3.5 for k in ("structure_support","liquidity_event","location_quality") if dimensions[k])+sum(4.0 for k in ("setup_mature","confirmation") if dimensions[k])+(5.0 if execution["ready"] else 0.0)-min(24.0,len(conflicts)*8.0)-min(30.0,len(invalidations)*15.0)),2)
    reasons=list(invalidations)+list(conflicts)
    if direction=="NEUTRAL": reasons.append("DIRECTIONAL_THESIS_UNRESOLVED")
    if setup["state"]!="MATURE": reasons.append("SETUP_NOT_MATURE")
    if e7_confirmation=="UNRESOLVED": reasons.append("ENTRY_CONFIRMATION_NOT_PROVEN")
    elif e7_confirmation=="WAIT": reasons.append("WAITING_FOR_CONFIRMATION")
    elif e7_confirmation=="FAILED": reasons.append("ENTRY_CONFIRMATION_FAILED")
    reasons.extend(execution["reasons"])
    ready=bool(direction in DIRECTIONS and setup["mature"] and e7_confirmation=="CONFIRMED" and execution["ready"] and thesis_quality>=70 and not conflicts and not invalidations)
    decision=direction if ready else "NO_TRADE"; plan=execution["plan"] or {}
    out={"decision":decision,"decision_authority":"E9","trade_decision_authority":True,"architecture":"PROFESSIONAL_THESIS_REASONING","analysis_complete":True,"direction":direction,"evidence_alignment":alignment,"thesis_quality":thesis_quality,"execution_readiness_score":100.0 if execution["ready"] else 0.0,"decision_score":thesis_quality if ready else 0.0,"score_semantics":"DECISION_SCORE_ONLY; THESIS_QUALITY_REPORTED_SEPARATELY","professional_reasoning":{"question":"Is there a clear, asymmetric, confirmed opportunity worth risking capital on now?","primary_thesis":direction,"alternative_thesis":"Opposite direction only if primary structure/setup thesis fails","invalidation":"; ".join(invalidations) if invalidations else "Structural/setup/confirmation premise failure","dimensions":dimensions,"setup_state":setup["state"],"setup":setup,"trigger_state":"TRIGGER_OBSERVED" if setup["trigger"] else "NO_TRIGGER","confirmation_state":e7_confirmation,"conflicts":conflicts,"hard_invalidations":invalidations,"execution_state":execution["state"],"execution_ready":execution["ready"],"risk_basis":execution["risk_basis"],"decision_process":"THESIS -> DIRECTION -> SETUP MATURITY -> TRIGGER -> CONFIRMATION -> EXECUTION -> DECISION"},"engine_theses":theses,"decision_reasons":sorted(set(reasons)),"evidence_conflicts":conflicts,"hard_invalidations":invalidations,"trade_plan":plan,"gate":ready,"upstream_gates_ignored":True,"gate_semantics":"E9_MASTER_ONLY","learning_policy":"ADVISORY_ONLY_NO_OVERRIDE","professional_decision":"APPROVE_TRADE" if ready else "NO_TRADE"}
    advisory=build_advisory(context,historical_calibration) if historical_calibration is not None else None
    if advisory is not None: out["learning_advisory"]=advisory
    return EngineResult("E9","Master Decision Brain",ready,thesis_quality,out,tuple(sorted(set(reasons))))