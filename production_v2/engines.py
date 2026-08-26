from __future__ import annotations

import importlib
from statistics import mean
from typing import Any

from .contracts import EngineResult

ENGINE_NAMES = {"E1":"Market State Engine","E2":"Market Regime / Playbook Engine","E3":"Market Structure Engine","E4":"Liquidity Engine","E5":"Location Engine","E6":"Trade Setup Engine","E7":"Confirmation Engine","E8":"Risk / Trade Economics Engine","E9":"Professional Decision Engine"}
SUB_ENGINE_CODES = {"E1":["1A","1B","1C","1D","1E","1F","1G"],"E2":["2A","2B","2C","2D","2E","2F"],"E3":["3A","3B","3C","3D","3E","3F"],"E4":["4A","4B","4C","4D","4E","4F"],"E5":["5A","5B","5C","5D","5E","5F"],"E6":["6A","6B","6C","6D","6E","6F"],"E7":["7A","7B","7C","7D","7E","7F"],"E8":["8A","8B","8C","8D","8E","8F","8G"],"E9":["9A","9B","9C","9D","9E","9F","9G","9H"]}
SUFFIX = {"1A":"a_data_quality","1B":"b_volatility_state","1C":"c_trend_state","1D":"d_range_state","1E":"e_compression","1F":"f_expansion","1G":"g_transition","2A":"a_trend_regime","2B":"b_range_regime","2C":"c_mean_reversion_behavior","2D":"d_breakout_regime","2E":"e_regime_phase","2F":"f_regime_transition","3A":"a_swing_detection","3B":"b_structure_classification","3C":"c_break_of_structure","3D":"d_structural_failure","3E":"e_structure_strength","3F":"f_internal_external_structure","4A":"a_liquidity_zone_detection","4B":"b_sweep_detection","4C":"c_reaction_rejection","4D":"d_acceptance","4E":"e_reclaim_failed_break","4F":"f_liquidity_strength_quality","5A":"a_equilibrium_value","5B":"b_structural_location","5C":"c_liquidity_location","5D":"d_extension","5E":"e_available_space","5F":"f_location_quality","6A":"a_setup_context","6B":"b_setup_archetype","6C":"c_setup_formation_state_machine","6D":"d_setup_invalidation","6E":"e_setup_quality","6F":"f_setup_maturity","7A":"a_trigger_detection","7B":"b_trigger_quality","7C":"c_follow_through","7D":"d_failure_invalidation","7E":"e_execution_conditions","7F":"f_confirmation_quality","8A":"a_invalidation_model","8B":"b_stop_placement","8C":"c_target_liquidity_objective","8D":"d_r_multiple","8E":"e_position_size","8F":"f_exposure_limits","8G":"g_risk_gate","9A":"a_data_gate","9B":"b_context_gate","9C":"c_setup_gate","9D":"d_confirmation_gate","9E":"e_risk_gate","9F":"f_execution_gate","9G":"g_final_decision","9H":"h_decision_logging"}
ENGINE_WEIGHTS = {"E1":.10,"E2":.10,"E3":.15,"E4":.12,"E5":.13,"E6":.15,"E7":.15,"E8":.10}
EDGE_THRESHOLD = 68.0

def _module(code:str): return importlib.import_module(f"trading_system.engines.e{code[0]}.{SUFFIX[code]}")
def _state(output:dict[str,Any],code:str,key:str="state"): return output.get(code,{}).get(key)
def _direction(output:dict[str,Any],code:str)->str: return str(output.get(code,{}).get("direction","NEUTRAL")).upper()

def _professional_context(engine_id:str, output:dict[str,Any], context:dict[str,Any])->dict[str,Any]:
    if engine_id=="E1": r={"question":"WHAT_IS_MARKET_DOING","market_state":_state(output,"1G") or _state(output,"1C") or "UNKNOWN","direction_bias":_direction(output,"1C"),"handoff":"E2_SELECT_PLAYBOOK"}
    elif engine_id=="E2": r={"question":"WHAT_GAME_TO_PLAY","regime":_state(output,"2F") or _state(output,"2E") or "UNKNOWN","preferred_direction":_direction(output,"2A"),"handoff":"E3_VALIDATE_STRUCTURE"}
    elif engine_id=="E3": r={"question":"WHAT_IS_PRICE_STRUCTURE_SAYING","structure":_state(output,"3B") or "UNRESOLVED","structure_direction":_direction(output,"3B"),"alignment":_state(output,"3F"),"handoff":"E4_MAP_LIQUIDITY"}
    elif engine_id=="E4": r={"question":"WHERE_IS_LIQUIDITY_AND_WHAT_DID_PRICE_DO","liquidity_quality":_state(output,"4F"),"sweep":_state(output,"4B"),"reclaim":_state(output,"4E"),"handoff":"E5_EVALUATE_LOCATION"}
    elif engine_id=="E5": r={"question":"IS_THIS_A_GOOD_LOCATION","location_quality":_state(output,"5F"),"extension":_state(output,"5D"),"space":_state(output,"5E"),"handoff":"E6_BUILD_SETUP"}
    elif engine_id=="E6":
        direction=_direction(output,"6B")
        if direction not in {"UP","DOWN"}: direction=_direction(output,"3B")
        r={"question":"WHAT_TRADE_SETUP_EXISTS","setup_type":_state(output,"6B") or "NONE","direction":direction,"formation":_state(output,"6C"),"invalidation":_state(output,"6D"),"setup_quality":_state(output,"6E"),"handoff":"E7_PROVE_THESIS"}
    elif engine_id=="E7": r={"question":"IS_THE_THESIS_HAPPENING_NOW","trigger":_state(output,"7A"),"trigger_quality":_state(output,"7B"),"follow_through":_state(output,"7C"),"failure":_state(output,"7D"),"confirmation":_state(output,"7F"),"handoff":"E8_PRICE_THE_TRADE"}
    elif engine_id=="E8": r={"question":"IS_THE_TRADE_ECONOMICALLY_WORTH_IT","trade_plan":output.get("trade_plan",{}),"risk_gate":_state(output,"8G"),"handoff":"E9_FINAL_DECISION"}
    else: r={}
    output["professional_reasoning"]=r
    return output

def _professional_gate(engine_id:str, output:dict[str,Any], context:dict[str,Any])->tuple[bool,tuple[str,...]]:
    if engine_id=="E1":
        ok=_state(output,"1A","data_quality")=="VALID"; return ok,(() if ok else ("E1_DATA_INVALID",))
    if engine_id=="E2": return True,(("E2_REGIME_UNCLEAR_HANDOFF",) if (_state(output,"2F") or _state(output,"2E")) in {None,"UNKNOWN",""} else ())
    if engine_id=="E3":
        if _state(output,"3D")=="FAILURE": return False,("E3_STRUCTURE_INVALIDATED",)
        return True,(("E3_STRUCTURE_MIXED_ALIGNMENT",) if _state(output,"3F")!="INTERNAL_EXTERNAL_ALIGNED" else ())
    if engine_id=="E4":
        q=_state(output,"4F"); return True,(("E4_LIQUIDITY_ADVERSE",) if q in {"LOW_QUALITY","INVALID","UNRESOLVED"} else ())
    if engine_id=="E5":
        if _state(output,"5D")=="EXTENDED": return False,("E5_LOCATION_DISADVANTAGED",)
        if _state(output,"5E")=="LIMITED_SPACE": return False,("E5_SPACE_INSUFFICIENT",)
        return True,(("E5_LOCATION_WEAK_HANDOFF",) if _state(output,"5F")!="LOCATION_QUALITY_PASS" else ())
    if engine_id=="E6":
        if _state(output,"6D")=="INVALIDATED": return False,("E6_SETUP_INVALIDATED",)
        setup=_state(output,"6B"); formed=_state(output,"6C")
        if setup in {None,"NONE","NO_SETUP"} or formed in {"INVALID","NOT_FORMED","NO_SETUP"}: return False,("E6_NO_VALID_SETUP",)
        return True,(("E6_SETUP_EARLY",) if _state(output,"6F")!="MATURE" else ())
    if engine_id=="E7":
        if _state(output,"7D")=="FAILURE": return False,("E7_CONFIRMATION_INVALIDATED",)
        passed=all(_state(output,c)==expected for c,expected in (("7A","TRIGGER_OBSERVED"),("7B","QUALITY_PASS"),("7C","FOLLOW_THROUGH_OBSERVED"),("7F","CONFIRMATION_PASS")))
        return passed,(() if passed else ("E7_CONFIRMATION_INSUFFICIENT",))
    if engine_id=="E8":
        plan=output.get("trade_plan",{}); policy=context.get("risk_policy") or {}
        if not plan.get("valid"): return False,(plan.get("reason","E8_RISK_PLAN_INVALID"),)
        if _state(output,"8G") not in {"RISK_GATE_READY","PASS",None}: return False,("E8_RISK_GATE_NOT_READY",)
        if float(plan.get("rr_tp2",0))<float(policy.get("min_rr",1.5)): return False,("E8_RR_BELOW_MINIMUM",)
        if float(plan.get("risk_atr",999))>float(policy.get("max_stop_atr",3.0)): return False,("E8_STOP_TOO_WIDE",)
        return True,()
    return True,()

def _trade_plan(context:dict[str,Any], direction:str)->dict[str,Any]:
    bars=context.get("bars") or []
    if len(bars)<30 or direction not in {"UP","DOWN"}: return {"valid":False,"reason":"INSUFFICIENT_RISK_DATA"}
    p=context.get("risk_policy") or {}; min_rr=float(p.get("min_rr",1.5)); target_rr=max(min_rr,float(p.get("target_rr",2.0))); max_stop=float(p.get("max_stop_atr",3.0)); buffer_atr=float(p.get("structure_buffer_atr",.2)); look=int(p.get("short_term_structure_lookback",8))
    recent=bars[-max(look,15):]; entry=float(recent[-1]["close"]); trs=[]; prev=None
    for b in recent:
        hi,lo,cl=map(float,(b["high"],b["low"],b["close"])); trs.append(hi-lo if prev is None else max(hi-lo,abs(hi-prev),abs(lo-prev))); prev=cl
    atr=mean(trs)
    if atr<=0:return {"valid":False,"reason":"INVALID_ATR"}
    buffer=atr*buffer_atr
    if direction=="UP": stop=min(float(b["low"]) for b in recent)-buffer; risk=entry-stop
    else: stop=max(float(b["high"]) for b in recent)+buffer; risk=stop-entry
    if risk<=0 or risk/atr>max_stop:return {"valid":False,"reason":"STOP_TOO_WIDE_FOR_SHORT_TERM"}
    tp1=entry+risk if direction=="UP" else entry-risk; tp2=entry+target_rr*risk if direction=="UP" else entry-target_rr*risk
    return {"valid":True,"direction":"BUY" if direction=="UP" else "SELL","entry":round(entry,8),"stop_loss":round(stop,8),"take_profit_1":round(tp1,8),"take_profit_2":round(tp2,8),"risk_distance":round(risk,8),"atr":round(atr,8),"risk_atr":round(risk/atr,3),"rr_tp1":1.0,"rr_tp2":round(abs(tp2-entry)/risk,3),"min_rr":min_rr,"stop_model":"STRUCTURAL_INVALIDATION","target_model":"LIQUIDITY_AND_R_MULTIPLE","short_term":True}

def _edge_score(upstream:list[EngineResult],plan:dict[str,Any])->tuple[float,list[str]]:
    if not plan.get("valid"): return 0.0,["EDGE_NO_VALID_TRADE_PLAN"]
    scores={e.engine_id:float(e.score) for e in upstream if e.engine_id in ENGINE_WEIGHTS}; weighted=sum(scores.get(k,0)*w for k,w in ENGINE_WEIGHTS.items())
    return round(max(0,min(100,weighted)),2),[]

def run_engine(engine_id:str, context:dict[str,Any])->EngineResult:
    results=[_module(code).SubEngine().run(context) for code in SUB_ENGINE_CODES[engine_id]]
    score=mean(r.score for r in results) if results else 0; output={r.sub_engine_id:r.output for r in results}
    output["sub_engine_failures"]=[{"id":r.sub_engine_id,"reason_codes":r.trace.get("reason_codes",[])} for r in results if not r.gate_passed]
    if engine_id=="E8":
        e6=context.get("E6_result",{}); direction=e6.get("professional_reasoning",{}).get("direction") or e6.get("6B",{}).get("direction") or context.get("E1_result",{}).get("1C",{}).get("direction","NEUTRAL"); output["trade_plan"]=_trade_plan(context,str(direction).upper())
    output=_professional_context(engine_id,output,context); gate,reasons=_professional_gate(engine_id,output,context); output["professional_gate"]="PASS" if gate else "FAIL"; output["professional_reason_codes"]=list(reasons); output["evidence_quality"]=round(score,2)
    return EngineResult(engine_id,ENGINE_NAMES[engine_id],gate,score,output,reasons)

def run_e9_decision(context:dict[str,Any], upstream:list[EngineResult])->EngineResult:
    by_id={e.engine_id:e for e in upstream}; hard=[e.engine_id for e in upstream if e.engine_id in {"E1","E3","E5","E6","E7","E8"} and not e.gate_passed]; e6=by_id.get("E6"); e8=by_id.get("E8"); plan=(e8.output.get("trade_plan",{}) if e8 else {}); edge,score_reasons=_edge_score(upstream,plan); decision=plan.get("direction","NO_TRADE"); final=not hard and decision in {"BUY","SELL"} and edge>=EDGE_THRESHOLD; reasons=list(score_reasons)
    if hard: reasons.append("E9_UPSTREAM_EVIDENCE_FAILED:"+",".join(hard))
    if edge<EDGE_THRESHOLD: reasons.append("E9_EDGE_BELOW_THRESHOLD")
    out={"decision":decision if final else "NO_TRADE","decision_authority":"E9","pipeline":"E1>E2>E3>E4>E5>E6>E7>E8>E9","trade_plan":plan,"edge_score":edge,"edge_threshold":EDGE_THRESHOLD,"gate_passed":final,"professional_decision":"APPROVE_TRADE" if final else "REJECT_TRADE","blocked_by":hard[0] if hard else None,"decision_reasons":reasons,"setup_thesis":(e6.output.get("professional_reasoning",{}) if e6 else {})}
    return EngineResult("E9",ENGINE_NAMES["E9"],final,edge,out,tuple(reasons))
