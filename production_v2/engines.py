from __future__ import annotations
"""Production-V2: controlled evidence architecture.

E1-E8 remain specialist analysts. They do not consume another engine's
DECISION or gate. Selected downstream specialists receive immutable evidence
from the Evidence Bus so they can reason with context. E9 remains the sole
trade-decision authority.
"""
import importlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean
from typing import Any
from .contracts import EngineResult

ENGINE_NAMES={"E1":"Market State Brain","E2":"Opportunity / Regime Brain","E3":"Market Structure Brain","E4":"Liquidity Brain","E5":"Location / Value Brain","E6":"Setup Brain","E7":"Confirmation Brain","E8":"Trade Economics Brain","E9":"Master Decision Brain"}
SUB_ENGINE_CODES={"E1":["1A","1B","1C","1D","1E","1F","1G"],"E2":["2A","2B","2C","2D","2E","2F"],"E3":["3A","3B","3C","3D","3E","3F"],"E4":["4A","4B","4C","4D","4E","4F"],"E5":["5A","5B","5C","5D","5E","5F"],"E6":["6A","6B","6C","6D","6E","6F"],"E7":["7A","7B","7C","7D","7E","7F"],"E8":["8A","8B","8C","8D","8E","8F","8G"]}
SUFFIX={"1A":"a_data_quality","1B":"b_volatility_state","1C":"c_trend_state","1D":"d_range_state","1E":"e_compression","1F":"f_expansion","1G":"g_transition","2A":"a_trend_regime","2B":"b_range_regime","2C":"c_mean_reversion_behavior","2D":"d_breakout_regime","2E":"e_regime_phase","2F":"f_regime_transition","3A":"a_swing_detection","3B":"b_structure_classification","3C":"c_break_of_structure","3D":"d_structural_failure","3E":"e_structure_strength","3F":"f_internal_external_structure","4A":"a_liquidity_zone_detection","4B":"b_sweep_detection","4C":"c_reaction_rejection","4D":"d_acceptance","4E":"e_reclaim_failed_break","4F":"f_liquidity_strength_quality","5A":"a_equilibrium_value","5B":"b_structural_location","5C":"c_liquidity_location","5D":"d_extension","5E":"e_available_space","5F":"f_location_quality","6A":"a_setup_context","6B":"b_setup_archetype","6C":"c_setup_formation_state_machine","6D":"d_setup_invalidation","6E":"e_setup_quality","6F":"f_setup_maturity","7A":"a_trigger_detection","7B":"b_trigger_quality","7C":"c_follow_through","7D":"d_failure_invalidation","7E":"e_execution_conditions","7F":"f_confirmation_quality","8A":"a_invalidation_model","8B":"b_stop_placement","8C":"c_target_liquidity_objective","8D":"d_r_multiple","8E":"e_position_size","8F":"f_exposure_limits","8G":"g_risk_gate"}

# Explicit information-flow policy. Values are evidence packages, never decisions.
EVIDENCE_INPUTS={
    "E1":(),
    "E2":("E1","E3","E4"),
    "E3":(),
    "E4":("E3",),
    "E5":("E3","E4"),
    "E6":("E1","E2","E3","E4","E5"),
    "E7":("E3","E4","E5","E6"),
    "E8":("E3","E4","E5","E6","E7"),
}

def _module(code:str): return importlib.import_module(f"trading_system.engines.e{code[0]}.{SUFFIX[code]}")
def _run(code:str,snapshot:dict[str,Any],evidence_bus:dict[str,Any]|None=None):
    local=dict(snapshot)
    if evidence_bus:
        local["evidence_bus"]={k:evidence_bus[k] for k in evidence_bus if k in evidence_bus}
    return _module(code).SubEngine().run(local)

def run_engine(engine_id:str,snapshot:dict[str,Any],evidence_bus:dict[str,Any]|None=None)->EngineResult:
    """Run one specialist using raw market data plus its permitted evidence inputs."""
    allowed=set(EVIDENCE_INPUTS.get(engine_id,()))
    permitted={k:evidence_bus[k] for k in allowed if evidence_bus and k in evidence_bus}
    codes=SUB_ENGINE_CODES[engine_id]; results=[]
    with ThreadPoolExecutor(max_workers=len(codes)) as pool:
        fs={pool.submit(_run,c,snapshot,permitted):c for c in codes}
        for f in as_completed(fs):
            code=fs[f]
            try: results.append(f.result())
            except Exception as exc: results.append(EngineResult(code,code,False,0.0,{"error":str(exc)},("SPECIALIST_EXCEPTION",)))
    results.sort(key=lambda r:r.sub_engine_id)
    evidence={r.sub_engine_id:{"output":r.output,"score":float(r.score),"observations":r.trace.get("observations",[]),"reason_codes":r.trace.get("reason_codes",[]),"legacy_gate_diagnostic":r.gate_passed} for r in results}
    score=mean(x["score"] for x in evidence.values()) if evidence else 0.0
    output={"architecture":"CONTROLLED_EVIDENCE_BUS","specialists":evidence,"evidence_quality":round(score,2),"decision_authority":"E9_ONLY","gate_semantics":"DISABLED_FOR_E1_E8","evidence_inputs":sorted(allowed),"professional_reasoning":{"question":_question(engine_id),"conclusion":_conclusion(evidence),"evidence_count":len(evidence)}}
    return EngineResult(engine_id,ENGINE_NAMES[engine_id],True,score,output,())

def _question(e): return {"E1":"What is the market doing right now?","E2":"What opportunity is being offered?","E3":"What is price structure communicating?","E4":"Where is liquidity and what did price do with it?","E5":"Is current location advantageous?","E6":"What setup is forming?","E7":"Has the thesis been confirmed?","E8":"Is the trade economically attractive?"}[e]
def _conclusion(evidence):
    vals=[]
    for x in evidence.values():
        o=x.get("output") or {}
        vals.extend(str(o[k]) for k in ("state","regime","direction","classification","quality","phase","setup","confirmation","risk_gate") if k in o)
    return ";".join(vals[-8:]) or "UNRESOLVED"

def run_all_parallel(snapshot:dict[str,Any])->list[EngineResult]:
    """Compatibility helper: independent E1-E8 snapshot analysis only."""
    results=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        fs={pool.submit(run_engine,e,snapshot,None):e for e in SUB_ENGINE_CODES}
        for f in as_completed(fs): results.append(f.result())
    return sorted(results,key=lambda r:r.engine_id)

def run_e9_decision(snapshot:dict[str,Any],upstream:list[EngineResult])->EngineResult:
    """Compatibility helper. E9 converts specialist evidence into a decision."""
    by={r.engine_id:r for r in upstream}; blobs={k:str(v.output).upper() for k,v in by.items()}; all_blob=" ".join(blobs.values())
    buy=sum(all_blob.count(x) for x in ("BUY","BULLISH","TREND_UP","LONG")); sell=sum(all_blob.count(x) for x in ("SELL","BEARISH","TREND_DOWN","SHORT"))
    direction="BUY" if buy>sell else "SELL" if sell>buy else "NO_TRADE"
    setup=any(x in blobs.get("E6","") for x in ("MATURE","FORMED","VALID_SETUP","TREND_CONTINUATION","LIQUIDITY_REVERSAL"))
    confirmation=any(x in blobs.get("E7","") for x in ("CONFIRMED","CONFIRMATION_PASS","TRIGGER_OBSERVED"))
    economics=any(x in blobs.get("E8","") for x in ("ATTRACTIVE","RISK_GATE_READY","RR_OK"))
    scores=[r.score for r in upstream]; alignment=round(mean(scores),2) if scores else 0.0
    reasons=[]
    if not setup: reasons.append("SETUP_EVIDENCE_NOT_MATURE")
    if not confirmation: reasons.append("CONFIRMATION_EVIDENCE_WEAK")
    if not economics: reasons.append("TRADE_ECONOMICS_EVIDENCE_WEAK")
    if direction=="NO_TRADE": reasons.append("DIRECTIONAL_CONFLUENCE_UNRESOLVED")
    final=direction in {"BUY","SELL"} and setup and confirmation and economics and alignment>=68
    out={"decision":direction if final else "NO_TRADE","decision_authority":"E9","architecture":"CONTROLLED_EVIDENCE_BUS→E9","evidence_alignment":alignment,"directional_evidence":{"buy":buy,"sell":sell},"confluence":{"setup":setup,"confirmation":confirmation,"economics":economics},"decision_reasons":reasons,"all_evidence_received":sorted(by),"upstream_gates_ignored":True,"gate_semantics":"E9_MASTER_ONLY"}
    return EngineResult("E9",ENGINE_NAMES["E9"],True,alignment,out,())
