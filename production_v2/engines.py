from __future__ import annotations
"""Production-V2 orchestration.
E1-E8 are parallel specialist brains. Sub-engines provide evidence only.
E9 is the sole trade decision authority; no upstream gate can directly block it.
"""
import importlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean
from typing import Any
from .contracts import EngineResult

ENGINE_NAMES={"E1":"Market State Brain","E2":"Opportunity / Regime Brain","E3":"Market Structure Brain","E4":"Liquidity Brain","E5":"Location / Value Brain","E6":"Setup Brain","E7":"Confirmation Brain","E8":"Trade Economics Brain","E9":"Master Decision Brain"}
SUB_ENGINE_CODES={"E1":["1A","1B","1C","1D","1E","1F","1G"],"E2":["2A","2B","2C","2D","2E","2F"],"E3":["3A","3B","3C","3D","3E","3F"],"E4":["4A","4B","4C","4D","4E","4F"],"E5":["5A","5B","5C","5D","5E","5F"],"E6":["6A","6B","6C","6D","6E","6F"],"E7":["7A","7B","7C","7D","7E","7F"],"E8":["8A","8B","8C","8D","8E","8F","8G"]}
SUFFIX={"1A":"a_data_quality","1B":"b_volatility_state","1C":"c_trend_state","1D":"d_range_state","1E":"e_compression","1F":"f_expansion","1G":"g_transition","2A":"a_trend_regime","2B":"b_range_regime","2C":"c_mean_reversion_behavior","2D":"d_breakout_regime","2E":"e_regime_phase","2F":"f_regime_transition","3A":"a_swing_detection","3B":"b_structure_classification","3C":"c_break_of_structure","3D":"d_structural_failure","3E":"e_structure_strength","3F":"f_internal_external_structure","4A":"a_liquidity_zone_detection","4B":"b_sweep_detection","4C":"c_reaction_rejection","4D":"d_acceptance","4E":"e_reclaim_failed_break","4F":"f_liquidity_strength_quality","5A":"a_equilibrium_value","5B":"b_structural_location","5C":"c_liquidity_location","5D":"d_extension","5E":"e_available_space","5F":"f_location_quality","6A":"a_setup_context","6B":"b_setup_archetype","6C":"c_setup_formation_state_machine","6D":"d_setup_invalidation","6E":"e_setup_quality","6F":"f_setup_maturity","7A":"a_trigger_detection","7B":"b_trigger_quality","7C":"c_follow_through","7D":"d_failure_invalidation","7E":"e_execution_conditions","7F":"f_confirmation_quality","8A":"a_invalidation_model","8B":"b_stop_placement","8C":"c_target_liquidity_objective","8D":"d_r_multiple","8E":"e_position_size","8F":"f_exposure_limits","8G":"g_risk_gate"}

def _module(code:str): return importlib.import_module(f"trading_system.engines.e{code[0]}.{SUFFIX[code]}")

def _run_specialist(code,context):
    return _module(code).SubEngine().run(context)

def run_engine(engine_id:str,context:dict[str,Any])->EngineResult:
    """One brain: all specialists receive the same snapshot; failures become evidence."""
    codes=SUB_ENGINE_CODES[engine_id]
    results=[]
    with ThreadPoolExecutor(max_workers=len(codes)) as pool:
        futures={pool.submit(_run_specialist,c,context):c for c in codes}
        for f in as_completed(futures):
            code=futures[f]
            try: results.append(f.result())
            except Exception as exc: results.append(EngineResult(code,code,False,0.0,{"error":str(exc)},("SPECIALIST_EXCEPTION",)))
    results.sort(key=lambda r:r.sub_engine_id)
    scores=[float(r.score) for r in results]
    evidence={r.sub_engine_id:{"output":r.output,"score":r.score,"observations":r.trace.get("observations",[]),"reason_codes":r.trace.get("reason_codes",[]),"gate_result_diagnostic":r.gate_passed} for r in results}
    output={"architecture":"PARALLEL_SPECIALISTS_SHARED_SNAPSHOT","specialists":evidence,"decision_authority":"E9_ONLY","gate_semantics":"E1_E8_OUTPUT_ONLY","evidence_quality":round(mean(scores),2) if scores else 0.0}
    output["professional_reasoning"]={"question":_question(engine_id),"conclusion":_conclusion(engine_id,evidence),"evidence_count":len(evidence),"observations":[f"{k}: specialist result collected" for k in evidence]}
    # Compatibility: gate_passed remains a diagnostic field for the contract, never an execution authority.
    return EngineResult(engine_id,ENGINE_NAMES[engine_id],True,output["evidence_quality"],output,())

def _question(e): return {"E1":"What is the market doing right now?","E2":"What opportunity/regime is being offered?","E3":"What is price structure communicating?","E4":"Where is liquidity and what did price do with it?","E5":"Is current location advantageous?","E6":"What setup is forming, if any?","E7":"Has the thesis actually been confirmed?","E8":"Is the trade economically attractive?"}[e]
def _conclusion(e,evidence):
    vals=[]
    for x in evidence.values():
        o=x.get("output") or {}
        for key in ("state","regime","direction","classification","quality","phase","setup","confirmation","risk_gate"):
            if key in o: vals.append(str(o[key]))
    return ";".join(vals[-8:]) or "UNRESOLVED"

def run_all_parallel(context:dict[str,Any])->list[EngineResult]:
    """E1-E8 all see the identical market snapshot; no engine consumes another engine's result."""
    results=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(run_engine,e,context):e for e in ENGINE_NAMES if e!="E9"}
        for f in as_completed(futures): results.append(f.result())
    return sorted(results,key=lambda r:r.engine_id)

def run_e9_decision(context:dict[str,Any],upstream:list[EngineResult])->EngineResult:
    """Master brain synthesizes all evidence. E1-E8 gate fields are intentionally ignored."""
    evidence={e.engine_id:e.output for e in upstream}
    scores=[e.score for e in upstream]
    def blob(eid): return str(evidence.get(eid,{})).upper()
    all_blob=" ".join(blob(e) for e in evidence)
    buy=sum(1 for x in ("TREND_UP","BULLISH","BUY","LONG") if x in all_blob)
    sell=sum(1 for x in ("TREND_DOWN","BEARISH","SELL","SHORT") if x in all_blob)
    direction="BUY" if buy>sell else "SELL" if sell>buy else "NO_TRADE"
    setup=any(x in blob("E6") for x in ("MATURE","FORMED","VALID_SETUP","TREND_CONTINUATION","LIQUIDITY_REVERSAL"))
    confirmation=any(x in blob("E7") for x in ("CONFIRMED","CONFIRMATION_PASS","TRIGGER_OBSERVED"))
    economics=any(x in blob("E8") for x in ("ATTRACTIVE","RISK_GATE_READY","RR_OK","PASS"))
    edge=round(mean(scores),2) if scores else 0.0
    reasons=[]
    if not setup: reasons.append("SETUP_EVIDENCE_NOT_MATURE")
    if not confirmation: reasons.append("CONFIRMATION_EVIDENCE_WEAK")
    if not economics: reasons.append("TRADE_ECONOMICS_EVIDENCE_WEAK")
    if direction=="NO_TRADE": reasons.append("DIRECTIONAL_CONFLUENCE_UNRESOLVED")
    final=direction in {"BUY","SELL"} and setup and confirmation and economics and edge>=68
    out={"decision":direction if final else "NO_TRADE","decision_authority":"E9","evidence_alignment":edge,"directional_evidence":{"buy":buy,"sell":sell},"confluence":{"setup":setup,"confirmation":confirmation,"economics":economics},"decision_reasons":reasons,"all_evidence_received":sorted(evidence),"gate_semantics":"E9_MASTER_SYNTHESIS_ONLY"}
    return EngineResult("E9",ENGINE_NAMES["E9"],True,edge,out,())
