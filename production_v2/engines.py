from __future__ import annotations

from .contracts import EngineResult
from .e3_brain import analyze_e3

# E3 is intentionally a single professional brain. Historical sub-engine
# extension points remain visible but parked so no hidden parallel authority exists.
SUB_ENGINE_CODES = {"E1": [], "E2": [], "E3": [], "E4": [], "E5": [], "E6": [], "E7": [], "E8": [], "E9": []}


def run_engine(engine_id: str, payload: dict) -> EngineResult:
    eid = str(engine_id or "").upper().strip()
    if eid == "E3":
        output = analyze_e3((payload or {}).get("bars") or [])
        score = float(output.get("confidence") or output.get("structure_strength") or 0.0)
        return EngineResult("E3", "Market Structure Analyst", False, score, output, ())
    raise ValueError(f"Unsupported engine: {engine_id}")
