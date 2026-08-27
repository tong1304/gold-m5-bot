from __future__ import annotations
from typing import Any
from .contracts import EngineResult
from .e1_brain import analyze_e1
from .e2_brain import analyze_e2
from .e3_brain import analyze_e3
from .e4_brain import analyze_e4
from .e5_brain import analyze_e5
from .e6_brain import analyze_e6
from .e7_brain import analyze_e7
from .e8_brain import analyze_e8
from .e9_brain import analyze_e9

ENGINE_IDS=("E1","E2","E3","E4","E5","E6","E7","E8","E9")
ENGINE_NAMES={"E1":"Market State Brain","E2":"Opportunity / Regime Brain","E3":"Market Structure Brain","E4":"Liquidity Brain","E5":"Location / Value Brain","E6":"Setup Brain","E7":"Confirmation Brain","E8":"Trade Economics Brain","E9":"Master Decision Brain"}


def run_engine(engine_id: str, snapshot: dict[str, Any], upstream: dict[str, EngineResult] | None = None) -> EngineResult:
    upstream=upstream or {}; bars=list(snapshot.get("bars") or [])
    if engine_id=="E1":
        brain=analyze_e1(bars); return EngineResult("E1",ENGINE_NAMES["E1"],None,float(brain.get("confidence",0))*100,brain,tuple(brain.get("conflicts",())))
    if engine_id=="E2":
        local=dict(snapshot); local["E1_result"]=(upstream.get("E1").output if upstream.get("E1") else {})
        brain=analyze_e2(local); return EngineResult("E2",ENGINE_NAMES["E2"],None,float(brain.get("confidence",0))*100,brain,tuple(brain.get("reason_codes",())))
    if engine_id=="E3":
        brain=analyze_e3(bars); return EngineResult("E3",ENGINE_NAMES["E3"],None,float(brain.get("confidence",0))*100,brain,tuple(brain.get("reason_codes",())))
    if engine_id=="E4":
        brain=analyze_e4({**snapshot,"bars":bars},upstream); return EngineResult("E4",ENGINE_NAMES["E4"],None,float(brain.get("evidence_strength",brain.get("confidence",0)))*100,brain,tuple(brain.get("reasons",())))
    if engine_id=="E5":
        brain=analyze_e5(dict(snapshot),upstream); return EngineResult("E5",ENGINE_NAMES["E5"],None,float(brain.get("confidence",0))*100,brain,tuple(brain.get("reason_codes",())))
    if engine_id=="E6": return analyze_e6(snapshot,upstream)
    if engine_id=="E7": return analyze_e7(snapshot,upstream)
    if engine_id=="E8": return analyze_e8(snapshot,upstream)
    if engine_id=="E9": return analyze_e9(snapshot,upstream)
    raise ValueError(f"Unknown engine: {engine_id}")
