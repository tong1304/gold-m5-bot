from __future__ import annotations
"""Production-V2 engine dispatcher.

E1-E4 are qualitative analysts. E4 uses the canonical professional E4 brain
entrypoint while legacy 4A-4F specialists remain paused. E9 remains the only
trade-decision authority.
"""
import importlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean
from typing import Any
from .contracts import EngineResult
from .e1_brain import analyze_e1
from .e2_brain import analyze_e2
from .e2_repricing import preserve_repricing_thesis
from .e3_brain import analyze_e3
from .professional_e4_brain_v15 import analyze_e4

ENGINE_NAMES={"E1":"Market State Brain","E2":"Opportunity / Regime Brain","E3":"Market Structure Brain","E4":"Liquidity Brain","E5":"Location / Value Brain","E6":"Setup Brain","E7":"Confirmation Brain","E8":"Trade Economics Brain","E9":"Master Decision Brain"}
SUB_ENGINE_CODES={"E1":["1A","1B","1C","1D","1E","1F","1G"],"E2":[],"E3":[],"E4":["4A","4B","4C","4D","4E","4F"],"E5":["5A","5B","5C","5D","5E","5F"],"E6":["6A","6B","6C","6D","6E","6F"],"E7":["7A","7B","7C","7D","7E","7F"],"E8":["8A","8B","8C","8D","8E","8F","8G"]}
SUFFIX={"1A":"a_data_quality","1B":"b_volatility_state","1C":"c_trend_state","1D":"d_range_state","1E":"e_compression","1F":"f_expansion","1G":"g_transition","2A":"a_trend_regime","2B":"b_range_regime","2C":"c_mean_reversion_behavior","2D":"d_breakout_regime","2E":"e_regime_phase","2F":"f_regime_transition","3A":"a_swing_detection","3B":"b_structure_classification","3C":"c_break_of_structure","3D":"d_structural_failure","3E":"e_structure_strength","3F":"f_internal_external_structure","4A":"a_liquidity_zone_detection","4B":"b_sweep_detection","4C":"c_reaction_rejection","4D":"d_acceptance","4E":"e_reclaim_failed_break","4F":"f_liquidity_strength_quality","5A":"a_equilibrium_value","5B":"b_structural_location","5C":"c_liquidity_location","5D":"d_extension","5E":"e_available_space","5F":"f_location_quality","6A":"a_setup_context","6B":"b_setup_archetype","6C":"c_setup_formation_state_machine","6D":"d_setup_invalidation","6E":"e_setup_quality","6F":"f_setup_maturity","7A":"a_trigger_detection","7B":"b_trigger_quality","7C":"c_follow_through","7D":"d_failure_invalidation","7E":"e_execution_conditions","7F":"f_confirmation_quality","8A":"a_invalidation_model","8B":"b_stop_placement","8C":"c_target_liquidity_objective","8D":"d_r_multiple","8E":"e_position_size","8F":"f_exposure_limits","8G":"g_risk_gate"}
ENGINE_IDS=tuple(SUB_ENGINE_CODES)
EVIDENCE_INPUTS={engine_id: tuple(other for other in ENGINE_IDS if other != engine_id) for engine_id in ENGINE_IDS}

def _module(code:str): return importlib.import_module(f"trading_system.engines.e{code[0]}.{SUFFIX[code]}")
def _qualitative(value:Any,key:str|None=None):
    if isinstance(value,dict):
        result={}
        for k,v in value.items():
            lk=str(k).lower()
            if lk in {"decision","trade_decision","decision_score","score","gate","gate_passed","specialist_gate"}: continue
            if lk in {"direction","bias","orientation","market_direction"} and isinstance(v,str):
                uv=v.upper().strip(); v="UP" if uv in {"BUY","LONG"} else "DOWN" if uv in {"SELL","SHORT"} else v
            result[k]=_qualitative(v,lk)
        return result
    if isinstance(value,(list,tuple)): return [_qualitative(v,key) for v in value]
    return value

def _legacy_context(permitted):
    ctx={}
    for engine_id,package in permitted.items():
        if not isinstance(package,dict): continue
        specialists=package.get("evidence") or package.get("specialists") or {}; clean={}
        if isinstance(specialists,dict):
            for sid,item in specialists.items():
                if isinstance(item,dict): clean[sid]=_qualitative(item)
        ctx[f"{engine_id}_result"]=clean
    return ctx

def _dependency_report(engine_id,permitted):
    required=sorted(EVIDENCE_INPUTS.get(engine_id,())); received=sorted(k for k in permitted if k in required)
    return {"required":required,"received":received,"missing":sorted(set(required)-set(received)),"complete":set(required).issubset(received),"decisions_received":False,"gates_received":False,"channel":"QUALITATIVE_EVIDENCE_ONLY"}

def _upstream_analysis(permitted):
    report={}
    for engine_id in sorted(permitted):
        package=permitted.get(engine_id)
        if not isinstance(package,dict): continue
        specialists=package.get("evidence") or package.get("specialists") or {}
        report[engine_id]={"engine_id":package.get("engine_id",engine_id),"specialist_count":len(specialists) if isinstance(specialists,dict) else 0,"reason_codes":list(package.get("reason_codes") or []),"interpretation":"Peer observations available; no score, decision or gate is consumed."}
    return report

def _run(code,snapshot,evidence_bus=None):
    local=dict(snapshot); permitted=evidence_bus or {}; local["evidence_bus"]={k:_qualitative(v) for k,v in permitted.items()}; local.update(_legacy_context(permitted)); local["upstream_analysis"]=_upstream_analysis(permitted); local["evidence_context_meta"]={"source_engines":sorted(permitted),"decisions_excluded":True,"gates_excluded":True,"scores_excluded":True,"analysis_mode":"PEER_REINTERPRETATION" if permitted else "INDEPENDENT_BASELINE"}
    return _module(code).SubEngine().run(local)

def _value_observations(value):
    observations=[]
    if isinstance(value,dict):
        for key,item in value.items():
            if str(key).lower() in {"score","decision","trade_decision","gate","gate_passed","specialist_gate"}: continue
            if isinstance(item,(str,int,float,bool)) and str(item).strip(): observations.append(f"{key}={item}")
    elif isinstance(value,(list,tuple)): observations.extend(str(x) for x in value[:8] if str(x).strip())
    return observations[:12]

def _reason_statements(result):
    trace=getattr(result,"trace",{}) or {}; reasons=list(getattr(result,"reason_codes",()) or [])
    for key in ("reasons","reason","findings","finding","observations","observation"):
        value=trace.get(key)
        if isinstance(value,(list,tuple)): reasons.extend(str(x) for x in value if x)
        elif value: reasons.append(str(value))
    return list(dict.fromkeys(str(x) for x in reasons if str(x).strip()))[:12]

def _e1_contract_normalize(brain):
    out=dict(brain); pressure=str(out.get("directional_pressure") or "BALANCED").upper(); out["directional_pressure"]="BULLISH" if pressure=="UP" else "BEARISH" if pressure=="DOWN" else pressure; out["analysis_status"]="COMPLETE"; return out

def _e2_e1_context(permitted):
    package=permitted.get("E1") or {}; evidence=package.get("evidence") if isinstance(package,dict) else {}; brain=evidence.get("output") if isinstance(evidence,dict) else None
    return brain if isinstance(brain,dict) else {}

def _e3_contract(brain):
    output={"architecture":"E3_SINGLE_PROFESSIONAL_BRAIN_V2","specialists":{},"specialists_active":False,"specialists_status":"PAUSED",**brain,"decision":None,"gate":None,"trade_decision_authority":False,"decision_authority":"E9_ONLY","reasoning_role":"MARKET_STRUCTURE_ANALYST"}
    return EngineResult("E3",ENGINE_NAMES["E3"],None,float(brain.get("confidence",0.0))*100.0,output,tuple(brain.get("reason_codes",())))

def _e4_contract(brain):
    output={"architecture":"E4_SINGLE_PROFESSIONAL_BRAIN_V15","professional_brain":True,"specialists":{},"specialists_active":False,"specialists_status":"PAUSED",**brain,"decision":None,"gate":None,"trade_decision_authority":False,"decision_authority":"E9_ONLY","reasoning_role":"LIQUIDITY_EVENT_ANALYST","upstream_decisions_used":False,"upstream_gates_used":False,"score_used":False}
    output["score"] = None
    return EngineResult("E4",ENGINE_NAMES["E4"],None,float(brain.get("evidence_strength",brain.get("confidence",0.0)))*100.0,output,tuple(brain.get("reasons",())))

def run_engine(engine_id,snapshot,evidence_bus=None):
    allowed=set(EVIDENCE_INPUTS.get(engine_id,())); permitted={k:evidence_bus[k] for k in allowed if evidence_bus and k in evidence_bus}
    if engine_id=="E2":
        local=dict(snapshot); local["E1_result"]=_e2_e1_context(permitted); brain=preserve_repricing_thesis(analyze_e2(local)); output={"architecture":"E2_PROFESSIONAL_CORE_ONLY","sub_engines_active":False,"sub_engines_status":"PAUSED","specialists":{},**brain,"decision":None,"entry":None,"trigger":None,"risk":None,"gate":None,"trade_decision_authority":"E9_ONLY","reasoning_role":"OPPORTUNITY_REGIME_ANALYST","upstream_decisions_used":False,"upstream_gates_used":False,"score_used":False}; return EngineResult("E2",ENGINE_NAMES["E2"],None,float(brain.get("confidence",0.0))*100.0,output,tuple(brain.get("reason_codes",())))
    if engine_id=="E3": return _e3_contract(analyze_e3(list(snapshot.get("bars") or [])))
    if engine_id=="E4":
        e4_snapshot=dict(snapshot); e4_snapshot["bars"]=list(snapshot.get("bars") or [])
        brain=analyze_e4(e4_snapshot, permitted)
        return _e4_contract(brain)
    codes=SUB_ENGINE_CODES[engine_id]; results=[]
    with ThreadPoolExecutor(max_workers=max(1,len(codes))) as pool:
        fs={pool.submit(_run,c,snapshot,permitted):c for c in codes}
        for f in as_completed(fs):
            code=fs[f]
            try: results.append(f.result())
            except Exception as exc: results.append(EngineResult(code,code,None,0.0,{"error":str(exc)},("SPECIALIST_EXCEPTION",)))
    results.sort(key=lambda r:r.sub_engine_id); evidence={}
    for r in results:
        output=_qualitative(r.output); observations=list(r.trace.get("observations",[]) if isinstance(r.trace,dict) else []); observations.extend(_value_observations(output)); evidence[r.sub_engine_id]={"output":output,"observations":list(dict.fromkeys(str(x) for x in observations))[:12],"reason_codes":_reason_statements(r)}
    if engine_id=="E1":
        brain=_e1_contract_normalize(analyze_e1(snapshot.get("bars") or [])); output={"architecture":"E1_PROFESSIONAL_MARKET_STATE_BRAIN_V2.1","specialists":evidence,**brain,"evidence_count":len(evidence),"peer_evidence_count":len(permitted),"upstream_decisions_used":False,"upstream_gates_used":False,"score_used":False,"reasoning_role":"MARKET_STATE_ANALYST"}; return EngineResult("E1",ENGINE_NAMES["E1"],None,float(brain["confidence"])*100.0,output,())
    score=mean(float(r.score) for r in results) if results else 0.0; used=[package.get("engine_id") for package in permitted.values() if isinstance(package,dict) and package.get("engine_id")]; dependency=_dependency_report(engine_id,permitted)
    output={"architecture":"PARALLEL_PEER_EVIDENCE_BUS","specialists":evidence,"decision_authority":"E9_ONLY","gate_semantics":"DISABLED_FOR_E1_E8","evidence_inputs":sorted(allowed),"evidence_used":sorted(used),"evidence_dependency":dependency,"upstream_analysis":_upstream_analysis(permitted),"professional_reasoning":{"question":_question(engine_id),"conclusion":_conclusion(evidence),"evidence_count":len(evidence),"peer_evidence_count":len(permitted),"upstream_decisions_used":False,"upstream_gates_used":False,"score_used":False,"reasoning_mode":"QUALITATIVE_EVIDENCE"}}
    return EngineResult(engine_id,ENGINE_NAMES[engine_id],None,score,output,())

def _question(e): return {"E1":"What is the market doing right now?","E2":"What opportunity is being offered?","E3":"What is price structure communicating?","E4":"Where is liquidity and what did price do with it?","E5":"Is current location advantageous?","E6":"What setup is forming?","E7":"Has the thesis been confirmed?","E8":"Is the trade economically attractive?"}[e]
def _conclusion(evidence):
    vals=[]
    for x in evidence.values():
        o=x.get("output") or {}; vals.extend(str(o[k]) for k in ("state","regime","direction","classification","quality","phase","setup","confirmation","risk_gate") if k in o)
    return (";".join(vals[-8:]) or "UNRESOLVED").replace("BUY","UP").replace("SELL","DOWN").replace("LONG","UP").replace("SHORT","DOWN")
def run_all_parallel(snapshot): return [run_engine(e,snapshot,None) for e in ENGINE_IDS]
