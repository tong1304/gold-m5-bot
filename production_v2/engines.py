from __future__ import annotations

import importlib
from statistics import mean
from typing import Any
from .contracts import EngineResult

ENGINE_NAMES={"E1":"Market State Engine","E2":"Market Regime Engine","E3":"Market Structure Engine","E4":"Liquidity Engine","E5":"Location Engine","E6":"Setup Engine","E7":"Confirmation Engine","E8":"Risk Engine","E9":"Execution Decision Engine"}
SUB_ENGINE_CODES={"E1":["1A","1B","1C","1D","1E","1F","1G"],"E2":["2A","2B","2C","2D","2E","2F"],"E3":["3A","3B","3C","3D","3E","3F"],"E4":["4A","4B","4C","4D","4E","4F"],"E5":["5A","5B","5C","5D","5E","5F"],"E6":["6A","6B","6C","6D","6E","6F"],"E7":["7A","7B","7C","7D","7E","7F"],"E8":["8A","8B","8C","8D","8E","8F","8G"],"E9":["9A","9B","9C","9D","9E","9F","9G","9H"]}
SUFFIX={"1A":"a_data_quality","1B":"b_volatility_state","1C":"c_trend_state","1D":"d_range_state","1E":"e_compression","1F":"f_expansion","1G":"g_transition","2A":"a_trend_regime","2B":"b_range_regime","2C":"c_mean_reversion_behavior","2D":"d_breakout_regime","2E":"e_regime_phase","2F":"f_regime_transition","3A":"a_swing_detection","3B":"b_structure_classification","3C":"c_break_of_structure","3D":"d_structural_failure","3E":"e_structure_strength","3F":"f_internal_external_structure","4A":"a_liquidity_zone_detection","4B":"b_sweep_detection","4C":"c_reaction_rejection","4D":"d_acceptance","4E":"e_reclaim_failed_break","4F":"f_liquidity_strength_quality","5A":"a_equilibrium_value","5B":"b_structural_location","5C":"c_liquidity_location","5D":"d_extension","5E":"e_available_space","5F":"f_location_quality","6A":"a_setup_context","6B":"b_setup_archetype","6C":"c_setup_formation_state_machine","6D":"d_setup_invalidation","6E":"e_setup_quality","6F":"f_setup_maturity","7A":"a_trigger_detection","7B":"b_trigger_quality","7C":"c_follow_through","7D":"d_failure_invalidation","7E":"e_execution_conditions","7F":"f_confirmation_quality","8A":"a_invalidation_model","8B":"b_stop_placement","8C":"c_target_liquidity_objective","8D":"d_r_multiple","8E":"e_position_size","8F":"f_exposure_limits","8G":"g_risk_gate","9A":"a_data_gate","9B":"b_context_gate","9C":"c_setup_gate","9D":"d_confirmation_gate","9E":"e_risk_gate","9F":"f_execution_gate","9G":"g_final_decision","9H":"h_decision_logging"}
ENGINE_WEIGHTS={"E1":.12,"E2":.10,"E3":.16,"E4":.10,"E5":.14,"E6":.12,"E7":.16,"E8":.10}
SHORT_TERM_EDGE_THRESHOLD=78.0

def _module(code:str): return importlib.import_module(f"trading_system.engines.e{code[0]}.{SUFFIX[code]}")
def _state(output:dict[str,Any],code:str,key:str="state"): return output.get(code,{}).get(key)
def _direction(output:dict[str,Any],code:str)->str: return str(output.get(code,{}).get("direction","NEUTRAL")).upper()

def _professional_gate(engine_id:str,output:dict[str,Any],context:dict[str,Any])->tuple[bool,tuple[str,...]]:
    if engine_id=="E1":
        if _state(output,"1A","data_quality")!="VALID": return False,("E1_DATA_INVALID",)
        state=_state(output,"1G")
        direction=_direction(output,"1C")
        # TRANSITION is a context, not a trade-killer. E2 must resolve it.
        if state=="TRANSITION": return direction!="NEUTRAL",(("E1_TRANSITION_HANDOFF",) if direction!="NEUTRAL" else ("E1_DIRECTION_UNCLEAR",))
        if state=="NON_DOMINANT": return direction!="NEUTRAL",(("E1_NON_DOMINANT_HANDOFF",) if direction!="NEUTRAL" else ("E1_DIRECTION_UNCLEAR",))
        if direction=="NEUTRAL": return False,("E1_DIRECTION_UNCLEAR",)
        return True,()
    if engine_id=="E2":
        regime=_state(output,"2F","regime")
        direction=next((v.get("direction") for v in output.values() if isinstance(v,dict) and v.get("direction") in {"UP","DOWN"}),"NEUTRAL")
        # A transition can be a profitable breakout/reversal candidate. Pass it downstream;
        # E3/E4/E6/E7 decide whether the move actually formed a tradeable structure/setup.
        if regime=="TRANSITION": return direction!="NEUTRAL",(("E2_TRANSITION_CANDIDATE",) if direction!="NEUTRAL" else ("E2_REGIME_UNCLEAR",))
        if regime not in {"TREND","RANGE","BREAKOUT","MEAN_REVERSION"}: return False,("E2_REGIME_UNCLEAR",)
        return True,()
    if engine_id=="E3":
        if _state(output,"3D")!="NO_FAILURE": return False,("E3_STRUCTURE_INVALIDATED",)
        if _state(output,"3B") not in {"BULLISH","BEARISH"}: return False,("E3_STRUCTURE_UNRESOLVED",)
        # Internal/external misalignment is information for the setup engine, not an automatic ban.
        if _state(output,"3F")!="INTERNAL_EXTERNAL_ALIGNED": return True,("E3_STRUCTURE_MIXED_ALIGNMENT",)
        return True,()
    if engine_id=="E4":
        quality=_state(output,"4F")
        # Liquidity quality is a score/filter. Only explicit adverse liquidity invalidates the trade.
        if quality in {"LOW_QUALITY","INVALID","UNRESOLVED"}: return False,("E4_LIQUIDITY_ADVERSE",)
        return True,()
    if engine_id=="E5":
        if _state(output,"5D")=="EXTENDED": return False,("E5_LOCATION_DISADVANTAGED",)
        if _state(output,"5E")=="LIMITED_SPACE": return False,("E5_SPACE_INSUFFICIENT",)
        if _state(output,"5F")!="LOCATION_QUALITY_PASS": return False,("E5_LOCATION_UNCONFIRMED",)
        return True,()
    if engine_id=="E6":
        if _state(output,"6D")!="NOT_INVALIDATED": return False,("E6_SETUP_INVALIDATED",)
        if _state(output,"6B") not in {"TREND_PULLBACK","BREAKOUT_RETEST","LIQUIDITY_REVERSAL","RANGE_REJECTION","MEAN_REVERSION"}: return False,("E6_SETUP_NOT_FORMED",)
        if _state(output,"6F")!="MATURE": return False,("E6_SETUP_NOT_MATURE",)
        return True,()
    if engine_id=="E7":
        if _state(output,"7D")=="FAILURE": return False,("E7_CONFIRMATION_INVALIDATED",)
        if all(_state(output,c)==expected for c,expected in (("7A","TRIGGER_OBSERVED"),("7B","QUALITY_PASS"),("7C","FOLLOW_THROUGH_OBSERVED"),("7F","CONFIRMATION_PASS"))): return True,()
        return False,("E7_CONFIRMATION_INSUFFICIENT",)
    if engine_id=="E8":
        plan=output.get("trade_plan",{}); policy=context.get("risk_policy") or {}
        if not plan.get("valid"): return False,(plan.get("reason","E8_RISK_PLAN_INVALID"),)
        if _state(output,"8G")!="RISK_GATE_READY": return False,("E8_RISK_GATE_NOT_READY",)
        if float(plan.get("rr_tp2",0))<float(policy.get("min_rr",1.5)): return False,("E8_RR_BELOW_MINIMUM",)
        if float(plan.get("risk_atr",999))>float(policy.get("max_stop_atr",3.0)): return False,("E8_STOP_TOO_WIDE",)
        return True,()
    return True,()

def _trade_plan(context:dict[str,Any],direction:str)->dict[str,Any]:
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
    if risk<=0 or risk/atr>max_stop:return {"valid":False,"reason":"STOP_TOO_WIDE_FOR_SHORT_TERM" if risk>0 else "INVALID_STOP"}
    tp1=entry+risk if direction=="UP" else entry-risk; tp2=entry+target_rr*risk if direction=="UP" else entry-target_rr*risk
    return {"valid":True,"direction":"BUY" if direction=="UP" else "SELL","entry":round(entry,8),"stop_loss":round(stop,8),"take_profit_1":round(tp1,8),"take_profit_2":round(tp2,8),"risk_distance":round(risk,8),"atr":round(atr,8),"risk_atr":round(risk/atr,3),"rr_tp1":1.0,"rr_tp2":round(abs(tp2-entry)/risk,3),"min_rr":min_rr,"stop_model":"STRUCTURAL_INVALIDATION","target_model":"R_MULTIPLE","short_term":True}

def _edge_score(upstream:list[EngineResult],plan:dict[str,Any])->tuple[float,list[str]]:
    if not plan.get("valid"): return 0.0,["EDGE_NO_VALID_TRADE_PLAN"]
    scores={e.engine_id:float(e.score) for e in upstream if e.engine_id in ENGINE_WEIGHTS}; weighted=sum(scores.get(k,0)*w for k,w in ENGINE_WEIGHTS.items()); reasons=[]
    if float(plan.get("risk_atr",999))>3: reasons.append("EDGE_RISK_TOO_WIDE")
    if float(plan.get("rr_tp2",0))<1.5: reasons.append("EDGE_RR_TOO_LOW")
    return round(max(0,min(100,weighted)),2),reasons

def run_engine(engine_id:str,context:dict[str,Any])->EngineResult:
    results=[_module(code).SubEngine().run(context) for code in SUB_ENGINE_CODES[engine_id]]; score=mean(r.score for r in results) if results else 0; output={r.sub_engine_id:r.output for r in results}; output["sub_engine_failures"]=[{"id":r.sub_engine_id,"reason_codes":r.trace.get("reason_codes",[])} for r in results if not r.gate_passed]
    if engine_id=="E8":
        direction=context.get("E1_result",{}).get("1C",{}).get("direction","NEUTRAL"); plan=_trade_plan(context,direction); output["trade_plan"]=plan
        if not plan.get("valid"): return EngineResult(engine_id,ENGINE_NAMES[engine_id],False,score,output,(plan.get("reason","RISK_PLAN_INVALID"),))
    gate,reasons=_professional_gate(engine_id,output,context); output["professional_gate"]="PASS" if gate else "FAIL"; output["professional_reason_codes"]=list(reasons); output["evidence_quality"]=round(score,2)
    return EngineResult(engine_id,ENGINE_NAMES[engine_id],gate,score,output,reasons)

def run_e9_decision(context:dict[str,Any],upstream:list[EngineResult])->EngineResult:
    failed=[e.engine_id for e in upstream if not e.gate_passed]
    if failed:return EngineResult("E9",ENGINE_NAMES["E9"],False,0,{"decision":"NO_TRADE","blocked_by":failed,"decision_authority":"E9"},("UPSTREAM_GATE_FAILED",))
    e1=next(e for e in upstream if e.engine_id=="E1"); e8=next(e for e in upstream if e.engine_id=="E8"); plan=e8.output.get("trade_plan",{}); edge,reasons=_edge_score(upstream,plan); decision=plan.get("direction","NO_TRADE")
    final=edge>=SHORT_TERM_EDGE_THRESHOLD and decision in {"BUY","SELL"} and not reasons
    out={"decision":decision if final else "NO_TRADE","decision_authority":"E9","pipeline":"E1>E2>E3>E4>E5>E6>E7>E8>E9","trade_plan":plan,"upstream_direction":e1.output.get("1C",{}).get("direction","NEUTRAL"),"edge_score":edge,"edge_threshold":SHORT_TERM_EDGE_THRESHOLD,"gate_passed":final}
    return EngineResult("E9",ENGINE_NAMES["E9"],final,edge,out,tuple(reasons+["E9_EDGE_BELOW_THRESHOLD"] if not final and edge<SHORT_TERM_EDGE_THRESHOLD else reasons))
